"""Dropfile ingest: the read side of the write-back fallback every adapter
protocol advertises.

Dropfile content is UNTRUSTED DATA. Nothing in it is ever executed, no path
it names is ever opened, and every value is one-line-collapsed before it can
reach the ledger (the D-W9.1 injection lesson). The parser is strict: the
first bad line is named by NUMBER (never echoed — a bad line could be
secret-shaped) and nothing is ingested on failure. All writes — evidence
rows, the runs-ladder end, the open-questions handoff, and the ingest event —
happen in ONE transaction.

Runs ladder (pinned by the contract): exactly one open run for the dropfile's
task+agent is ended with the dropfile outcome/summary; zero or multiple open
runs still ingest evidence and open questions but create/end no run, and say
so in the output and the event payload.

Dedupe (pinned): the ingest event payload stores the dropfile's sha256; a
prior ingest event with the same hash refuses the ingest (exit 1).
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from . import db, events, ids, ops, pack, utils
from .models import EVIDENCE_KINDS, RUN_OUTCOMES
from .utils import AosError

HEADER_LINE = "# AOS DROPFILE"
EVIDENCE_HEADING = "## evidence"
QUESTIONS_HEADING = "## open questions"

_TASK_RE = re.compile(r"^T-[0-9]+$")
_AGENT_RE = re.compile(r"^[A-Za-z0-9._-]+$", re.ASCII)
_EVIDENCE_BULLET_RE = re.compile(
    r"^- kind: (.+?) \| ref: (.+?) \| claim: (.+)$"
)

#: Payload summaries are capped so a giant dropfile cannot bloat the journal.
SUMMARY_PAYLOAD_LIMIT = 300


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _malformed(line_no: int, reason: str) -> AosError:
    """Name the line NUMBER, never the content — a bad line could carry
    exactly the secret-shaped text the scanner exists to keep off stderr."""
    return AosError(f"Malformed dropfile at line {line_no}: {reason}")


def parse_dropfile(text: str) -> dict:
    """Parse EXACTLY the format `adapters/*/PROTOCOL.md` advertises.

    Returns {task, agent, outcome, summary, evidence: [(kind, ref, claim)],
    questions: [str]}. Raises AosError naming the first bad line on any
    deviation. All values are one-line-collapsed.
    """
    lines = text.split("\n")
    pos = 0

    def next_content_line() -> tuple[int, str] | tuple[None, None]:
        nonlocal pos
        while pos < len(lines):
            line = lines[pos]
            pos += 1
            if line.strip():
                return pos, line.strip()
        return None, None

    line_no, line = next_content_line()
    if line != HEADER_LINE:
        raise _malformed(line_no or 1, f"expected '{HEADER_LINE}' first")

    fields: dict[str, str] = {}
    field_lines: dict[str, int] = {}
    for key in ("task", "agent", "outcome", "summary"):
        line_no, line = next_content_line()
        if line is None or not line.startswith(f"{key}: "):
            raise _malformed(
                line_no or len(lines), f"expected '{key}: <value>'"
            )
        value = _one_line(line[len(key) + 2 :])
        if not value:
            raise _malformed(line_no, f"'{key}:' value must not be empty")
        fields[key] = value
        field_lines[key] = line_no

    if not _TASK_RE.match(fields["task"]):
        raise _malformed(field_lines["task"], "task must look like T-0001")
    task_number = int(fields["task"].split("-", 1)[1])
    if task_number > 2**63 - 1:  # SQLite INTEGER bound; untrusted input
        raise _malformed(field_lines["task"], "task id out of range")
    if not _AGENT_RE.match(fields["agent"]):
        raise _malformed(
            field_lines["agent"], "agent name must match [A-Za-z0-9._-]+"
        )
    if fields["outcome"] not in RUN_OUTCOMES:
        raise _malformed(
            field_lines["outcome"],
            f"outcome must be one of {'|'.join(RUN_OUTCOMES)}",
        )

    line_no, line = next_content_line()
    if line != EVIDENCE_HEADING:
        raise _malformed(
            line_no or len(lines), f"expected '{EVIDENCE_HEADING}'"
        )

    evidence: list[tuple[str, str, str]] = []
    while True:
        line_no, line = next_content_line()
        if line is None:
            raise _malformed(len(lines), f"missing '{QUESTIONS_HEADING}'")
        if line == QUESTIONS_HEADING:
            break
        match = _EVIDENCE_BULLET_RE.match(line)
        if not match:
            raise _malformed(
                line_no, "expected '- kind: K | ref: R | claim: C'"
            )
        kind = _one_line(match.group(1))
        if kind not in EVIDENCE_KINDS:
            raise _malformed(
                line_no,
                f"evidence kind must be one of {'|'.join(EVIDENCE_KINDS)}",
            )
        evidence.append(
            (kind, _one_line(match.group(2)), _one_line(match.group(3)))
        )

    questions: list[str] = []
    while True:
        line_no, line = next_content_line()
        if line is None:
            break
        if not line.startswith("- ") or not _one_line(line[2:]):
            raise _malformed(line_no, "expected '- <open question>'")
        questions.append(_one_line(line[2:]))

    return {
        **fields,
        "task_id": task_number,
        "evidence": evidence,
        "questions": questions,
    }


def _scan_for_secrets(doc: dict) -> None:
    findings = []
    targets = [("summary", doc["summary"])]
    for index, (kind, ref, claim) in enumerate(doc["evidence"], start=1):
        targets.append((f"evidence row {index} ref", ref))
        targets.append((f"evidence row {index} claim", claim))
    for index, question in enumerate(doc["questions"], start=1):
        targets.append((f"open question {index}", question))
    for where, value in targets:
        for pattern_name in pack.scan_secrets(value):
            findings.append(f"{pattern_name} in {where}")
    if findings:
        raise AosError(
            "Refusing to ingest dropfile: secret-shaped content detected — "
            + "; ".join(findings)
            + ". Nothing was ingested."
        )


def _refuse_duplicate(conn: sqlite3.Connection, sha: str) -> None:
    for row in conn.execute(
        "SELECT id, payload_json FROM events "
        "WHERE entity = 'system' AND action = 'dropfile_ingest' ORDER BY id"
    ):
        try:
            payload = json.loads(row["payload_json"])
        except ValueError:
            continue
        if payload.get("sha256") == sha:
            raise AosError(
                f"Duplicate dropfile: sha256 {sha} was already ingested "
                f"(event #{row['id']})."
            )


def ingest_dropfile(conn: sqlite3.Connection, path: Path) -> dict:
    """Ingest one dropfile. The file itself is never modified or deleted."""
    if not path.is_file():
        raise AosError(f"Dropfile not found: {path}")
    raw = path.read_bytes()
    sha = utils.sha256_bytes(raw)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise AosError(f"Dropfile is not valid UTF-8: {path}")
    doc = parse_dropfile(text.replace("\r\n", "\n").replace("\r", "\n"))
    task = ops.get_task(conn, doc["task_id"])
    task_hid = ids.render_id("task", task.id)
    _scan_for_secrets(doc)
    _refuse_duplicate(conn, sha)

    agent = doc["agent"]
    actor = f"agent:{agent}"
    open_runs = conn.execute(
        "SELECT id FROM runs WHERE task_id = ? AND agent = ? "
        "AND ended_at IS NULL ORDER BY id",
        (task.id, agent),
    ).fetchall()

    now = utils.utc_now_iso()
    evidence_hids: list[str] = []
    run_ended_hid = None
    handoff_hid = None
    with db.transaction(conn):
        for kind, ref, claim in doc["evidence"]:
            # Untrusted content: no path named by a dropfile is ever opened,
            # so kind=file rows carry no sha256 (unlike CLI `evidence add`).
            cursor = conn.execute(
                "INSERT INTO evidence (task_id, claim, kind, ref, sha256, "
                "provenance, created_at) VALUES (?, ?, ?, ?, NULL, ?, ?)",
                (task.id, claim, kind, ref, actor, now),
            )
            evidence_hid = ids.render_id("evidence", cursor.lastrowid)
            evidence_hids.append(evidence_hid)
            events.emit(
                conn,
                actor=actor,
                entity="evidence",
                entity_id=cursor.lastrowid,
                action="add",
                payload={
                    "task": task_hid,
                    "kind": kind,
                    "ref": ref,
                    "claim": claim,
                    "sha256": None,
                    "via": "dropfile",
                },
            )
        if len(open_runs) == 1:
            run_id = open_runs[0]["id"]
            conn.execute(
                "UPDATE runs SET ended_at = ?, outcome = ?, summary_md = ? "
                "WHERE id = ?",
                (now, doc["outcome"], doc["summary"], run_id),
            )
            run_ended_hid = ids.render_id("run", run_id)
            events.emit(
                conn,
                actor=actor,
                entity="run",
                entity_id=run_id,
                action="end",
                payload={
                    "task": task_hid,
                    "outcome": doc["outcome"],
                    "via": "dropfile",
                },
            )
        if doc["questions"]:
            state_md = "\n".join(f"- {q}" for q in doc["questions"])
            cursor = conn.execute(
                "INSERT INTO handoffs (task_id, from_agent, to_agent, "
                "state_md, created_at) VALUES (?, ?, 'generic', ?, ?)",
                (task.id, agent, state_md, now),
            )
            handoff_hid = ids.render_id("handoff", cursor.lastrowid)
            events.emit(
                conn,
                actor=actor,
                entity="handoff",
                entity_id=cursor.lastrowid,
                action="create",
                payload={
                    "handoff": handoff_hid,
                    "task": task_hid,
                    "from_agent": agent,
                    "to_agent": "generic",
                    "via": "dropfile",
                },
            )
        events.emit(
            conn,
            actor=actor,
            entity="system",
            entity_id=None,
            action="dropfile_ingest",
            payload={
                "file": path.name,
                "sha256": sha,
                "task": task_hid,
                "agent": agent,
                "outcome": doc["outcome"],
                "summary": doc["summary"][:SUMMARY_PAYLOAD_LIMIT],
                "evidence": evidence_hids,
                "run_ended": run_ended_hid,
                "open_runs": len(open_runs),
                "handoff": handoff_hid,
            },
        )
    return {
        "task": task_hid,
        "agent": agent,
        "outcome": doc["outcome"],
        "evidence": evidence_hids,
        "run_ended": run_ended_hid,
        "open_runs": len(open_runs),
        "handoff": handoff_hid,
        "sha256": sha,
    }
