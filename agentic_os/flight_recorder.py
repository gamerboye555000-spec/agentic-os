"""U-E6 flight recorder: deterministic, secret-free flight record bundles.

Contract: agentic-os-v0.4-u-e6-flight-recorder-replay-contract.md.

The flight record is a DERIVED, exportable artifact (D-v0.4.146): every byte is
reconstructible from the seven workflow tables + `work_spec_document` digest +
relevant base-journal rows. U-E6 adds NO new tables and never writes `aos.db`.

Format (D-v0.4.153, D-v0.4.154, D-v0.4.160): a file is

    {"canonical_payload": {...}, "wrapper": {...}}

where `canonical_payload` is the integrity-manifested, byte-identical JSON that
`verify` and `replay` consume, and `wrapper` (`created_at`, `secret_scan`) is
non-manifested metadata that may differ between creates.

Canonical payload members (contract §4.1): schema_version, protocol_version,
workflow_id, work_spec_digest, the seven workflow table arrays (document bodies
excluded per D-v0.4.137), journal_rows (closed-vocabulary payload members only),
and integrity_manifest. The `workflows` row itself is NOT an array member: its
identity is carried by the top-level `workflow_id` and `work_spec_digest`, and
contract §4.1's explicit member list — the format definition — enumerates the
seven derived tables only. That is the strongest textual anchor (the §7 "all
eight" phrasing is descriptive), and it keeps the manifest and every digest
recomputable without a body.

Row digests recompute exactly as the store sealed them (§8 row-level):
- events are the canonical `aos.workflow-event/v1` records (`content_sha256` =
  `protocols.content_digest(record)`);
- the six row-hash tables recompute through `workflow_store`'s own §5.8 payload
  builders, so a bundle digest and the ledger digest agree by construction;
- the intent row is the one case whose body the store's builder re-digests, so
  the bundle carries the recomputed `document_sha256` + `payload_bytes` and
  verify rebuilds the hash payload from those members directly.

The manifest is `table_name -> {row_count, sha256(concat(sorted(row hashes)))}`
(contract §8). journal_rows carry no stored `content_sha256`; their manifest
preimage is the concatenation of each journal row's canonical JSON bytes, in
row_id order — the only sensible, deterministic stand-in, and it is what lets a
tampered journal row surface in the manifest.

Secret handling (D-v0.4.148): creation runs `secretscan` over the ENTIRE
canonical JSON byte sequence; any hit refuses with `secret_in_flight_record`
and lists finding TYPES only, never values, and writes no file.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from . import db, ids, protocols, secretscan, utils
from .utils import AosError
from . import workflow_store

PROTOCOL_VERSION = "1"
BUNDLE_SCHEMA_VERSION = db.SCHEMA_VERSION

#: The closed journal payload members carried into `journal_rows`, transcribed
#: from `observability._JOURNAL_PAYLOAD_ATTRIBUTES`. Values are untrusted data
#: copied verbatim — the scanner is the guard on them.
_JOURNAL_PAYLOAD_MEMBERS = (
    "seq", "revision", "policy_version", "from_state", "to_state", "command",
    "command_id", "command_sha256", "event_sha256", "work_spec_sha256",
    "reason",
)

#: The seven table arrays, in §6's natural-key order, with the column lists in
#: the exact order `workflow_store`'s SELECTs and §5.8 builders expect.
_TABLE_KEYS = (
    "workflow_events", "workflow_commands", "workflow_intents",
    "workflow_receipts", "workflow_facts", "workflow_attempts",
    "workflow_checkpoints",
)

_EVENT_COLUMNS = (
    "seq", "event", "from_state", "to_state", "revision", "policy_version",
    "command_id", "command_sha256", "actor", "payload_json", "created_at",
    "content_sha256",
)
_COMMAND_COLUMNS = (
    "id", "workflow_id", "command_id", "command", "command_sha256",
    "expected_revision", "resulting_revision", "event_seq_first",
    "event_seq_last", "created_at", "content_sha256",
)
_INTENT_COLUMNS = (
    "id", "workflow_id", "intent_id", "intent_kind", "idempotency_key",
    "queue_route", "document", "status", "resolved_receipt_id", "created_at",
    "content_sha256",
)
_RECEIPT_COLUMNS = (
    "id", "workflow_id", "receipt_id", "receipt_kind", "intent_id",
    "runtime_task_uuid", "document", "receipt_sha256", "created_at",
    "content_sha256",
)
_FACT_COLUMNS = (
    "id", "workflow_id", "fact_kind", "fact_scope", "document",
    "document_sha256", "recorded_at", "content_sha256",
)
_ATTEMPT_COLUMNS = (
    "id", "workflow_id", "attempt_no", "state", "runtime_task_uuid",
    "dispatch_intent_id", "idempotency_key", "result_sha256", "opened_seq",
    "closed_seq", "created_at", "updated_at", "content_sha256",
)
_CHECKPOINT_COLUMNS = (
    "id", "workflow_id", "attempt_no", "checkpoint_id", "checkpoint_seq",
    "runtime_task_uuid", "document", "document_sha256", "payload_bytes",
    "recorded_at", "content_sha256",
)

_SQL_SCHEMA_VERSION = "SELECT value FROM meta WHERE key = 'schema_version'"
_SQL_WORKFLOW = (
    f"SELECT id, task_id, work_spec_sha256 FROM {db.WORKFLOWS_TABLE} "
    "WHERE id = ?"
)
_SQL_EVENTS = (
    f"SELECT {', '.join(_EVENT_COLUMNS)} FROM {db.WORKFLOW_EVENTS_TABLE} "
    "WHERE workflow_id = ? ORDER BY seq"
)
_SQL_COMMANDS = (
    f"SELECT {', '.join(_COMMAND_COLUMNS)} FROM {db.WORKFLOW_COMMANDS_TABLE} "
    "WHERE workflow_id = ? ORDER BY id"
)
_SQL_INTENTS = (
    f"SELECT {', '.join(_INTENT_COLUMNS)} FROM {db.WORKFLOW_INTENTS_TABLE} "
    "WHERE workflow_id = ? ORDER BY id"
)
_SQL_RECEIPTS = (
    f"SELECT {', '.join(_RECEIPT_COLUMNS)} FROM {db.WORKFLOW_RECEIPTS_TABLE} "
    "WHERE workflow_id = ? ORDER BY id"
)
_SQL_FACTS = (
    f"SELECT {', '.join(_FACT_COLUMNS)} FROM {db.WORKFLOW_FACTS_TABLE} "
    "WHERE workflow_id = ? ORDER BY id"
)
_SQL_ATTEMPTS = (
    f"SELECT {', '.join(_ATTEMPT_COLUMNS)} FROM {db.WORKFLOW_ATTEMPTS_TABLE} "
    "WHERE workflow_id = ? ORDER BY attempt_no"
)
_SQL_CHECKPOINTS = (
    f"SELECT {', '.join(_CHECKPOINT_COLUMNS)} "
    f"FROM {db.WORKFLOW_CHECKPOINTS_TABLE} "
    "WHERE workflow_id = ? ORDER BY checkpoint_seq"
)
_SQL_JOURNAL = (
    "SELECT id, ts, actor, entity, entity_id, action, payload_json "
    "FROM events WHERE entity = 'workflow' AND entity_id = ? ORDER BY id"
)


def _refusal(message: str, exit_code: int) -> AosError:
    """An `AosError` carrying a contract exit code (§11)."""
    error = AosError(message)
    error.exit_code = exit_code
    return error


def _require_schema(conn: sqlite3.Connection) -> None:
    row = conn.execute(_SQL_SCHEMA_VERSION).fetchone()
    if row is None or row[0] != db.SCHEMA_VERSION:
        raise AosError(
            f"The ledger schema ({row[0] if row is not None else 'unknown'}) "
            f"is not the {db.SCHEMA_VERSION} schema this flight recorder "
            "supports; nothing was created."
        )


def _row_to_dict(columns, row) -> dict:
    return dict(zip(columns, row))


def _intent_bundle_row(row) -> dict:
    """The intent row with its document body excluded (D-v0.4.137): the body's
    recomputed digest and canonical byte length take its place."""
    body = json.loads(row[6])
    out = _row_to_dict(_INTENT_COLUMNS, row)
    out.pop("document", None)
    out["workflow_id"] = _render_workflow_id(out["workflow_id"])
    out["document_sha256"] = protocols.content_digest(body)
    out["payload_bytes"] = len(protocols.serialize_canonical(body))
    return out


_DOCUMENT_SLOT_TABLES = {
    "workflow_receipts": (_RECEIPT_COLUMNS, "document"),
    "workflow_facts": (_FACT_COLUMNS, "document"),
    "workflow_checkpoints": (_CHECKPOINT_COLUMNS, "document"),
    "workflow_intents": (_INTENT_COLUMNS, "document"),
}


def _render_workflow_id(value) -> str:
    """Render a row's `workflow_id` column as the identity string, the same
    spelling the engine freezes (the canonical JSON integer bound is smaller
    than the derived identity, so the string is the only canonical form)."""
    if isinstance(value, str) and value.startswith("WF-"):
        return value
    return workflow_store._render(value)


def _bundle_row(columns, row) -> dict:
    """A row dict with the document body slot removed, for the tables whose
    §5.8 payload binds the body only by digest column."""
    out = _row_to_dict(columns, row)
    if "document" in out:
        out.pop("document", None)
    if "workflow_id" in out:
        out["workflow_id"] = _render_workflow_id(out["workflow_id"])
    return out


def _journal_bundle_row(row) -> dict:
    """One base-journal row for this workflow: identity columns plus the closed
    payload members present in the stored payload (§4.1, §9.4 of the flight
    record's own vocabulary — the `observability._JOURNAL_PAYLOAD_ATTRIBUTES`
    member set). Values are copied verbatim and are untrusted."""
    out = {
        "row_id": row[0],
        "ts": row[1],
        "actor": row[2],
        "entity": row[3],
        # A workflow's `entity_id` is the DERIVED workflow identity (up to
        # 2**62), which exceeds the canonical JSON integer bound; it is
        # rendered as the identity string, exactly as the observability
        # projection renders `aos.workflow.id` (D-v0.4.122).
        "entity_id": f"WF-{row[4]}",
        "action": row[5],
    }
    payload = json.loads(row[6]) if isinstance(row[6], str) else {}
    for member in _JOURNAL_PAYLOAD_MEMBERS:
        if member in payload:
            out[member] = payload[member]
    return out


def _manifest_for(table: str, rows: list) -> dict:
    if table == "journal_rows":
        hashes = [
            hashlib.sha256(protocols.serialize_canonical(row)).hexdigest()
            for row in rows
        ]
    else:
        hashes = [row["content_sha256"] for row in rows]
    return {
        "row_count": len(rows),
        "sha256_of_concatenated_content_sha256s": hashlib.sha256(
            "".join(sorted(hashes)).encode("utf-8")
        ).hexdigest(),
    }


def assemble(conn: sqlite3.Connection, workflow_id: str) -> dict:
    """The canonical payload for one workflow, or a refusal.

    Reads every row as stored — never recomputes, never repairs, never writes.
    Raises `AosError` with the create exit codes when the workflow is missing
    (2) or the ledger is unusable (1).
    """
    _require_schema(conn)
    row_id = ids.parse_id(workflow_id, "workflow")
    workflow = conn.execute(_SQL_WORKFLOW, (row_id,)).fetchone()
    if workflow is None:
        raise _refusal(
            f"No workflow {workflow_id}. Run: python aos.py workflow list", 2
        )

    work_spec_sha256 = workflow[2]
    events = [
        workflow_store._event_record(row, workflow[0], work_spec_sha256)
        for row in conn.execute(_SQL_EVENTS, (row_id,))
    ]
    commands = [
        _bundle_row(_COMMAND_COLUMNS, row)
        for row in conn.execute(_SQL_COMMANDS, (row_id,))
    ]
    intents = [
        _intent_bundle_row(row)
        for row in conn.execute(_SQL_INTENTS, (row_id,))
    ]
    receipts = [
        _bundle_row(_RECEIPT_COLUMNS, row)
        for row in conn.execute(_SQL_RECEIPTS, (row_id,))
    ]
    facts = [
        _bundle_row(_FACT_COLUMNS, row)
        for row in conn.execute(_SQL_FACTS, (row_id,))
    ]
    attempts = [
        _bundle_row(_ATTEMPT_COLUMNS, row)
        for row in conn.execute(_SQL_ATTEMPTS, (row_id,))
    ]
    checkpoints = [
        _bundle_row(_CHECKPOINT_COLUMNS, row)
        for row in conn.execute(_SQL_CHECKPOINTS, (row_id,))
    ]
    journal_rows = [
        _journal_bundle_row(row)
        for row in conn.execute(_SQL_JOURNAL, (row_id,))
    ]

    payload = {
        "schema_version": db.SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        # The canonical JSON bound (INT_MAX, 2**53-1) is smaller than the
        # derived workflow identity (up to 2**62-1), so the identity is
        # carried as the rendered string — the same resolution the store's §5.8
        # row hashes use (`_leaf(_render(id))`), and the one spelling the
        # engine freezes (D-v0.4.122's identity discipline).
        "workflow_id": workflow_store._render(row_id),
        "work_spec_digest": work_spec_sha256,
        "workflow_events": events,
        "workflow_commands": commands,
        "workflow_intents": intents,
        "workflow_receipts": receipts,
        "workflow_facts": facts,
        "workflow_attempts": attempts,
        "workflow_checkpoints": checkpoints,
        "journal_rows": journal_rows,
        "integrity_manifest": {
            "workflow_events": _manifest_for("workflow_events", events),
            "workflow_commands": _manifest_for("workflow_commands", commands),
            "workflow_intents": _manifest_for("workflow_intents", intents),
            "workflow_receipts": _manifest_for("workflow_receipts", receipts),
            "workflow_facts": _manifest_for("workflow_facts", facts),
            "workflow_attempts": _manifest_for("workflow_attempts", attempts),
            "workflow_checkpoints": _manifest_for(
                "workflow_checkpoints", checkpoints
            ),
            "journal_rows": _manifest_for("journal_rows", journal_rows),
        },
    }
    return payload


def create(
    conn: sqlite3.Connection, workflow_id: str
) -> tuple[dict, dict]:
    """Scan and seal: returns (canonical_payload, wrapper).

    Runs `secretscan` over the ENTIRE canonical JSON byte sequence; any hit
    refuses with `secret_in_flight_record` (exit 3). The wrapper's `created_at`
    is the ONLY wall-clock read in this module.
    """
    payload = assemble(conn, workflow_id)
    canonical = protocols.serialize_canonical(payload)
    findings = secretscan.scan_secrets(canonical.decode("utf-8"))
    if findings:
        raise _refusal(
            "secret_in_flight_record: the flight record for workflow "
            f"{workflow_id} would contain secret-shaped data "
            f"({', '.join(findings)}). Nothing was written.", 3
        )
    wrapper = {
        "created_at": utils.utc_now_iso(),
        "secret_scan": {"scanned": True, "findings": 0},
    }
    return payload, wrapper


def write_bundle(path: Path, payload: dict, wrapper: dict) -> None:
    """Write the bundle file. Raises AosError (exit 4) on I/O failure."""
    body = protocols.serialize_canonical(
        {"canonical_payload": payload, "wrapper": wrapper}
    ) + b"\n"
    try:
        path.write_bytes(body)
    except OSError as exc:
        raise _refusal(
            f"Could not write flight record {path}: {exc.__class__.__name__}."
            " Nothing else was written.", 4
        )


def read_bundle(path: Path) -> dict:
    """Load a bundle file's canonical payload, refusing malformed files."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise AosError(
            f"Could not read flight record {path}: "
            f"{exc.__class__.__name__}."
        )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise AosError(f"Flight record {path} is not valid UTF-8.")
    try:
        document = json.loads(text)
    except ValueError:
        raise AosError(f"Flight record {path} is not valid JSON.")
    if not isinstance(document, dict) or "canonical_payload" not in document:
        raise AosError(
            f"Flight record {path} has no canonical_payload member; not an "
            "aos.flight-record/v1 bundle."
        )
    payload = document["canonical_payload"]
    if not isinstance(payload, dict):
        raise AosError(f"Flight record {path} has a malformed canonical_payload.")
    return payload


def _require_protocol(payload: dict) -> None:
    """Unknown protocol_version is a distinct failure (exit 2, §11)."""
    if payload.get("protocol_version") != PROTOCOL_VERSION:
        raise _refusal(
            f"Unknown flight record protocol_version "
            f"{payload.get('protocol_version')!r}; this build supports "
            f"{PROTOCOL_VERSION!r}.", 2
        )


def _row_digest_from(payload_of, row: dict, columns) -> str:
    """Recompute a §5.8 row hash from a bundle row dict. The document slot is
    absent; the builders of the digest-bound tables read only digest columns.
    The bundle carries `workflow_id` as the identity string, so it is parsed
    back to the integer the builders expect."""
    row_list = [
        int(row["workflow_id"][3:]) if name == "workflow_id"
        else row.get(name)
        for name in columns
    ]
    return workflow_store._row_digest(payload_of(row_list))


def _intent_digest_from(row: dict) -> str:
    """The intent row hash, rebuilt from the bundle's members (the store's
    builder re-digests the body, which the bundle deliberately excludes)."""
    workflow_id = int(row["workflow_id"][3:])
    payload = {
        "record_schema": workflow_store.INTENT_ROW_SCHEMA,
        "id": row["id"],
        "workflow_id_sha256": workflow_store._leaf(
            workflow_store._render(workflow_id)
        ),
        "intent_id_sha256": workflow_store._leaf(row["intent_id"]),
        "intent_kind_sha256": workflow_store._leaf(row["intent_kind"]),
        "idempotency_key_sha256": workflow_store._leaf(
            row["idempotency_key"]
        ),
        "queue_route_sha256": workflow_store._leaf(row["queue_route"]),
        "document_sha256": row["document_sha256"],
        "status_sha256": workflow_store._leaf(row["status"]),
        "resolved_receipt_id_sha256": (
            None if row["resolved_receipt_id"] is None
            else workflow_store._leaf(row["resolved_receipt_id"])
        ),
        "created_at_sha256": workflow_store._leaf(row["created_at"]),
    }
    return workflow_store._row_digest(payload)


_ROW_CHECKERS = {
    "workflow_events": (
        _EVENT_COLUMNS, lambda row: protocols.content_digest(row),
    ),
    "workflow_commands": (
        _COMMAND_COLUMNS,
        lambda row: _row_digest_from(workflow_store._command_row_payload,
                                    row, _COMMAND_COLUMNS),
    ),
    "workflow_intents": (_INTENT_COLUMNS, _intent_digest_from),
    "workflow_receipts": (
        _RECEIPT_COLUMNS,
        lambda row: _row_digest_from(workflow_store._receipt_row_payload,
                                     row, _RECEIPT_COLUMNS),
    ),
    "workflow_facts": (
        _FACT_COLUMNS,
        lambda row: _row_digest_from(workflow_store._fact_row_payload,
                                     row, _FACT_COLUMNS),
    ),
    "workflow_attempts": (
        _ATTEMPT_COLUMNS,
        lambda row: _row_digest_from(workflow_store._attempt_row_payload,
                                     row, _ATTEMPT_COLUMNS),
    ),
    "workflow_checkpoints": (
        _CHECKPOINT_COLUMNS,
        lambda row: _row_digest_from(workflow_store._checkpoint_row_payload,
                                     row, _CHECKPOINT_COLUMNS),
    ),
}


def verify(payload: dict) -> dict:
    """Recompute every row hash, every table manifest, and the bundle digest.

    Reports, never repairs. `protocol_version` is validated first; an unknown
    one is a refusal (exit 2). Everything else is a finding in the returned
    report; the CLI maps any finding to exit 1.
    """
    _require_protocol(payload)
    findings = []
    if payload.get("schema_version") != db.SCHEMA_VERSION:
        findings.append({
            "kind": "schema_version_mismatch",
            "where": "/schema_version",
            "detail": f"bundle {payload.get('schema_version')!r} vs ledger "
                      f"{db.SCHEMA_VERSION!r}",
        })

    for table in _TABLE_KEYS:
        rows = payload.get(table)
        if not isinstance(rows, list):
            findings.append({
                "kind": "table_missing", "where": f"/{table}",
                "detail": "table array absent",
            })
            continue
        if table == "workflow_events" and rows:
            # A deleted event row leaves a gap that row digests cannot expose
            # (the survivors still recompute), so the sequence itself must be
            # dense from 1 in BOTH seq and revision — the shape `fold` needs.
            seqs = [row.get("seq") for row in rows]
            revisions = [row.get("revision") for row in rows]
            dense = list(range(1, len(rows) + 1))
            if seqs != dense:
                findings.append({
                    "kind": "seq_gap", "where": "/workflow_events",
                    "detail": "event seq is not dense from 1",
                })
            if revisions != dense:
                findings.append({
                    "kind": "revision_gap", "where": "/workflow_events",
                    "detail": "event revision is not dense from 1",
                })
        _columns, checker = _ROW_CHECKERS[table]
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict) or not isinstance(
                row.get("content_sha256"), str
            ):
                findings.append({
                    "kind": "row_unreadable", "where": f"/{table}/{index}",
                    "detail": "row has no readable content_sha256",
                })
                continue
            stored = row["content_sha256"]
            try:
                recomputed = checker(row)
            except Exception:
                findings.append({
                    "kind": "row_unreadable", "where": f"/{table}/{index}",
                    "detail": "row payload could not be rebuilt",
                })
                continue
            if recomputed != stored:
                findings.append({
                    "kind": "digest_divergent",
                    "where": f"/{table}/{index}",
                    "detail": "content_sha256 does not recompute",
                })

    journal = payload.get("journal_rows")
    if isinstance(journal, list):
        seen = set()
        for index, row in enumerate(journal, start=1):
            if not isinstance(row, dict) or not isinstance(
                row.get("row_id"), int
            ):
                findings.append({
                    "kind": "row_unreadable", "where": f"/journal_rows/{index}",
                    "detail": "journal row has no readable row_id",
                })
                continue
            if row["row_id"] in seen:
                findings.append({
                    "kind": "duplicate_row", "where": f"/journal_rows/{index}",
                    "detail": f"duplicate row_id {row['row_id']}",
                })
            seen.add(row["row_id"])
    else:
        findings.append({
            "kind": "table_missing", "where": "/journal_rows",
            "detail": "journal_rows absent",
        })

    manifest = payload.get("integrity_manifest")
    for table, rows in (
        ("workflow_events", payload.get("workflow_events") or []),
        ("workflow_commands", payload.get("workflow_commands") or []),
        ("workflow_intents", payload.get("workflow_intents") or []),
        ("workflow_receipts", payload.get("workflow_receipts") or []),
        ("workflow_facts", payload.get("workflow_facts") or []),
        ("workflow_attempts", payload.get("workflow_attempts") or []),
        ("workflow_checkpoints", payload.get("workflow_checkpoints") or []),
        ("journal_rows", payload.get("journal_rows") or []),
    ):
        expected = _manifest_for(table, rows)
        declared = (
            manifest.get(table) if isinstance(manifest, dict) else None
        )
        if declared != expected:
            findings.append({
                "kind": "manifest_divergent", "where": f"/integrity_manifest/{table}",
                "detail": "row count or hash does not match",
            })

    return {
        "protocol_version": payload.get("protocol_version"),
        "schema_version": payload.get("schema_version"),
        "workflow_id": payload.get("workflow_id"),
        "work_spec_digest": payload.get("work_spec_digest"),
        "bundle_sha256": hashlib.sha256(
            protocols.serialize_canonical(payload)
        ).hexdigest(),
        "findings": findings,
        "ok": not findings,
    }
