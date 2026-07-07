"""Review notes: a generated daily review at AOS/Reviews/YYYY-MM-DD.md.

Like sync, `review build` is a derived view of ledger state (plus the review
date): it mutates no ledger rows and emits no event (extends D-P0.6, see
D-W6.1). Everything ABOVE the "## Notes" line is regenerated; the "## Notes"
line and everything after it is preserved byte-for-byte — that region belongs
to the human, so it is spliced back verbatim (even CR bytes survive; the
LF-normalization rule applies to generated content only, D-W6.3).

All "recent"/"stale" windows are computed from the review date parameter —
the only wall-clock read is the default date, which comes from the single
clock utility.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

from . import ids, obsidian

NOTES_HEADING = b"## Notes"
DEFAULT_TAIL = b"## Notes\n"

RECENT_DAYS = 7
STALE_MEMORY_DAYS = 30


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _notes_tail(data: bytes) -> bytes | None:
    """The preserved region: from the first line reading '## Notes' (any
    line ending) to EOF, byte-for-byte. None when no such line exists."""
    pos = 0
    while True:
        line_end = data.find(b"\n", pos)
        line = data[pos: line_end if line_end != -1 else len(data)]
        if line.rstrip(b"\r") == NOTES_HEADING:
            return data[pos:]
        if line_end == -1:
            return None
        pos = line_end + 1


def _section_block(heading: str, bullet_lines: list[str]) -> list[str]:
    return [f"## {heading}", ""] + (bullet_lines or ["*(none)*"]) + [""]


def _head_text(conn: sqlite3.Connection, date_str: str) -> str:
    """Everything above '## Notes' — a pure function of DB state + date."""
    review_date = date.fromisoformat(date_str)
    recent_floor = (review_date - timedelta(days=RECENT_DAYS - 1)).isoformat()
    date_ceiling = date_str + "~"  # '~' > 'T', so any timestamp on date_str
    stale_floor = (review_date - timedelta(days=STALE_MEMORY_DAYS)).isoformat()

    slug_by_project_id = {
        row["id"]: row["slug"]
        for row in conn.execute("SELECT id, slug FROM projects")
    }

    attention = []
    for row in conn.execute(
        "SELECT t.id, t.title, "
        "NOT EXISTS (SELECT 1 FROM evidence e WHERE e.task_id = t.id) "
        "AS no_evidence, "
        "EXISTS (SELECT 1 FROM events ev WHERE ev.entity = 'task' "
        "AND ev.entity_id = t.id AND ev.action = 'done_override') "
        "AS overridden "
        "FROM tasks t WHERE t.status = 'done' ORDER BY t.id"
    ):
        reasons = []
        if row["no_evidence"]:
            reasons.append("no evidence")
        if row["overridden"]:
            reasons.append("closed via --no-evidence override")
        if reasons:
            task_hid = ids.render_id("task", row["id"])
            attention.append(
                f"- [[{task_hid}]] {_one_line(row['title'])} — "
                + "; ".join(reasons)
            )

    open_tasks = [
        f"- [[{ids.render_id('task', row['id'])}]] {_one_line(row['title'])} "
        f"· {row['status']} · "
        f"{slug_by_project_id.get(row['project_id']) or '-'}"
        for row in conn.execute(
            "SELECT id, title, status, project_id FROM tasks "
            "WHERE status != 'done' ORDER BY id"
        )
    ]

    recent_evidence = [
        f"- [[{ids.render_id('evidence', row['id'])}]] {row['kind']} · "
        f"{_one_line(row['ref'])} · [[{ids.render_id('task', row['task_id'])}]]"
        for row in conn.execute(
            "SELECT id, task_id, kind, ref FROM evidence "
            "WHERE created_at >= ? AND created_at <= ? ORDER BY id",
            (recent_floor, date_ceiling),
        )
    ]

    stale_memory = []
    for row in conn.execute(
        "SELECT id, key, confidence, valid_until, updated_at FROM memory "
        "WHERE (valid_until IS NOT NULL AND substr(valid_until, 1, 10) <= ?) "
        "OR (valid_until IS NULL AND substr(updated_at, 1, 10) <= ?) "
        "ORDER BY id",
        (date_str, stale_floor),
    ):
        memory_hid = ids.render_id("memory", row["id"])
        if row["valid_until"] is not None:
            detail = f"valid_until {row['valid_until']} passed"
        else:
            detail = f"not updated since {row['updated_at']}"
        stale_memory.append(
            f"- [[{memory_hid}]] {_one_line(row['key'])} "
            f"· [{row['confidence']}] · {detail}"
        )

    recent_runs = [
        f"- [[{ids.render_id('run', row['id'])}]] {_one_line(row['agent'])} · "
        f"{row['outcome'] or 'open'} · [[{ids.render_id('task', row['task_id'])}]]"
        for row in conn.execute(
            "SELECT id, task_id, agent, outcome FROM runs "
            "WHERE started_at >= ? AND started_at <= ? ORDER BY id",
            (recent_floor, date_ceiling),
        )
    ]

    lines = [f"# Review {date_str}", ""]
    lines += _section_block("Done tasks needing attention", attention)
    lines += _section_block("Open tasks", open_tasks)
    lines += _section_block("Recent evidence", recent_evidence)
    lines += _section_block("Stale memory", stale_memory)
    lines += _section_block("Recent runs", recent_runs)
    return "\n".join(lines) + "\n"


def build_review(conn: sqlite3.Connection, aos_dir: Path, date_str: str) -> Path:
    reviews_dir = obsidian.vault_aos_dir(aos_dir) / "Reviews"
    path = reviews_dir / f"{date_str}.md"
    tail = None
    if path.is_file():
        tail = _notes_tail(path.read_bytes())
    if tail is None:
        tail = DEFAULT_TAIL
    new_bytes = _head_text(conn, date_str).encode("utf-8") + tail
    if not path.is_file() or path.read_bytes() != new_bytes:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(new_bytes)
    return path
