"""U-E6 incident reconstruction documents.

Contract: agentic-os-v0.4-u-e6-flight-recorder-replay-contract.md §1, §4.4,
§11.

An incident reconstruction document (`aos.incident-report/v1`) correlates the
flight record with the observability projection, the verification report, and
the operator's question. It cites evidence by row identity (table, row_id,
content_sha256) and NEVER infers causation the ledger does not support
(D-v0.4.151): the document is a correlation, not an explanation.

`incident create` writes the report document; `incident export` writes the
report alongside the flight record bundle, the projection document and the
verification document into an empty directory. Both surfaces are read-only
with respect to `aos.db` (DERIVED_WRITE — they write only operator-requested
files).
"""

from __future__ import annotations

import hashlib
import os
import stat as stat_module
import sqlite3
from pathlib import Path

from . import db, flight_recorder, ids, observability, protocols, utils
from .utils import AosError

PROTOCOL_VERSION = "1"
SCHEMA = "aos.incident-report/v1"

EXPORT_INCIDENT = "incident.json"
EXPORT_FLIGHT_RECORD = "flight-record.json"
EXPORT_OBSERVABILITY = "observability.json"
EXPORT_VERIFICATION = "verification.json"
EXPORT_FILES = (
    EXPORT_INCIDENT,
    EXPORT_FLIGHT_RECORD,
    EXPORT_OBSERVABILITY,
    EXPORT_VERIFICATION,
)

_EVIDENCE_TABLES = (
    ("workflow_events", "workflow_events"),
    ("workflow_commands", "workflow_commands"),
    ("workflow_intents", "workflow_intents"),
    ("workflow_receipts", "workflow_receipts"),
    ("workflow_facts", "workflow_facts"),
    ("workflow_attempts", "workflow_attempts"),
    ("workflow_checkpoints", "workflow_checkpoints"),
)


def _refusal(message: str, exit_code: int) -> AosError:
    error = AosError(message)
    error.exit_code = exit_code
    return error


def _require_workflow(conn: sqlite3.Connection, workflow_id: str) -> int:
    row_id = ids.parse_id(workflow_id, "workflow")
    row = conn.execute(
        f"SELECT 1 FROM {db.WORKFLOWS_TABLE} WHERE id = ?", (row_id,)
    ).fetchone()
    if row is None:
        raise _refusal(
            f"No workflow {workflow_id}. Run: python aos.py workflow list", 2
        )
    return row_id


def _evidence_index(payload: dict) -> list:
    """Every row the flight record cites, by table, row identity and
    content_sha256. The six store tables carry an integer `id`; the event
    array carries no `id` (events are keyed by dense `seq`), so its natural
    row identity is cited instead. journal_rows are the operator's journal,
    not workflow rows, and carry no content_sha256 — they are not evidence
    entries."""
    out = []
    for table in ("workflow_events", "workflow_commands", "workflow_intents",
                  "workflow_receipts", "workflow_facts", "workflow_attempts",
                  "workflow_checkpoints"):
        rows = payload.get(table) or []
        for row in rows:
            row_id = row.get("id")
            if table == "workflow_events":
                row_id = row.get("seq")
            digest = row.get("content_sha256")
            if isinstance(row_id, int) and isinstance(digest, str):
                out.append({
                    "table": table,
                    "row_id": row_id,
                    "content_sha256": digest,
                })
    return out


def _bundle_digest(payload: dict) -> str:
    return hashlib.sha256(protocols.serialize_canonical(payload)).hexdigest()


def create_report(
    conn: sqlite3.Connection, workflow_id: str, context: str,
) -> dict:
    """The `aos.incident-report/v1` document for one workflow."""
    _require_workflow(conn, workflow_id)
    payload = flight_recorder.assemble(conn, workflow_id)
    projection = observability.project_workflow(
        conn, observability.render_workflow_id(ids.parse_id(workflow_id, "workflow"))
    )
    reports = observability.verify(conn, workflow_id)
    document = {
        "schema": SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "workflow_id": workflow_id,
        "flight_record_sha256": _bundle_digest(payload),
        "observability": observability.projection_document(projection),
        "verification": observability.verify_document(reports),
        "evidence": _evidence_index(payload),
        "created_at": utils.utc_now_iso(),
    }
    if context:
        document["context"] = context
    return document


def write_report(path: Path, document: dict) -> None:
    try:
        path.write_bytes(protocols.serialize_canonical_file_bytes(document))
    except OSError as exc:
        raise _refusal(
            f"Could not write incident report {path}: "
            f"{exc.__class__.__name__}. Nothing else was written.", 4
        )


def export(
    conn: sqlite3.Connection, workflow_id: str, context: str,
    directory: Path,
) -> list:
    """Write the four-file incident bundle into an EMPTY directory.

    Refuses (exit 2) when the target is not a directory or is not empty —
    the `observe export` §9.5 discipline: a bundle is a set, never a patch.
    """
    target = Path(directory)
    try:
        info = os.lstat(target)
    except OSError:
        info = None
    if info is None or not stat_module.S_ISDIR(info.st_mode):
        raise _refusal(
            f"Not an existing directory: {target}. Create it first, then "
            "re-run: python aos.py incident export WF-n --out DIR", 2
        )
    with os.scandir(target) as entries:
        occupied = any(True for _entry in entries)
    if occupied:
        raise _refusal(
            f"Refused: {target} is not empty. An incident export is never "
            "merged into existing files. Name an empty directory, then "
            "re-run: python aos.py incident export WF-n --out DIR", 2
        )

    payload = flight_recorder.assemble(conn, workflow_id)
    _, wrapper = flight_recorder.create(conn, workflow_id)
    report = create_report(conn, workflow_id, context)
    projection = observability.project_workflow(
        conn, observability.render_workflow_id(ids.parse_id(workflow_id, "workflow"))
    )
    verification = observability.verify(conn, workflow_id)

    written = []
    bundle_bytes = protocols.serialize_canonical(
        {"canonical_payload": payload, "wrapper": wrapper}
    ) + b"\n"
    for name, body in (
        (EXPORT_INCIDENT,
         protocols.serialize_canonical_file_bytes(report)),
        (EXPORT_FLIGHT_RECORD, bundle_bytes),
        (EXPORT_OBSERVABILITY, protocols.serialize_canonical_file_bytes(
            observability.projection_document(projection))),
        (EXPORT_VERIFICATION, protocols.serialize_canonical_file_bytes(
            observability.verify_document(verification))),
    ):
        try:
            (target / name).write_bytes(body)
        except OSError as exc:
            raise _refusal(
                f"Could not write {target / name}: {exc.__class__.__name__}.",
                4,
            )
        written.append((name, len(body)))
    return written