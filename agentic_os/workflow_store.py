"""U-W2.2 deterministic workflow store: the SQLite shell around the landed
U-W2.1 pure reducer.

Contract: agentic-os-v0.4-u-w2-2-workflow-store-contract.md

It stores an authoritative append-only workflow history, a derived snapshot
projection under revision compare-and-swap, an outbox of queue intents, an
inbox of queue receipts, and the verbatim external facts a success or approval
claim rests on. It decides nothing the reducer has not already decided,
executes nothing, retries nothing, delivers nothing, and grants nothing.

The store's entire decision authority is the set of judgments that REQUIRE
stored rows (§4.2): does this workflow exist, has this command_id been accepted
before and with this digest, has this receipt_id been stored before and with
this digest, does the named task exist and is it open, does the stored
projection agree with the stored history, and did the compare-and-swap win.
Every other judgment is `decide`'s, and this module neither anticipates nor
second-guesses it.

Import discipline (§8.5, enforced by the §20 row S24 AST test): `re`,
`sqlite3`, `dataclasses`, `hashlib`, and from the package `db`, `events`,
`ids`, `models`, `protocols`, `workflow_engine`, and `utils.AosError` — and
nothing else. NO `json` (`events.emit` serializes its own payload), NEITHER
`datetime` NOR `time` (§10.7: the whole write path reads no clock; every
timestamp is the accepted command's own `created_at`), and no `ops`, `cli`,
`power`, `doctor`, `backup`, `governance` or `workspecs` (the reducer owns the
acceptance seam).

Trust model (§3, §18): every persisted row is UNTRUSTED INPUT. A row may have
been written by direct SQL, corrupted by hardware, or restored from a tampered
backup, so this module re-derives rather than trusts — every digest is
recomputed from the stored bytes at every use, the workflow identity is
re-derived from the admitted artifact digest, the history is re-verified before
it is folded, and the reducer's own `_verify_snapshot` runs the stored WorkSpec
back through the U-W1 acceptance gate on every command. Stored text is DATA:
it never becomes SQL (every statement is parameterized and the only
interpolated identifiers are the six frozen `db.py` table-name constants),
never becomes a message (§18.5), and never becomes a path, a command, or a
tool input — this module opens nothing, spawns nothing, and imports nothing
dynamically.

Integrity is REPORTED, never repaired (§7.6, §15): `verify` writes nothing,
`rebuild` returns a value, `submit` refuses. There is no `--repair`, no
`--force`, no re-seal and no re-stamp anywhere in this slice.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass, field

from . import db, events, ids, models, protocols, workflow_engine
from .utils import AosError

# ---------------------------------------------------------------------------
# Closed vocabularies (§8.1). Tuples, frozen at import.

#: The four statuses `submit` can return. `conflict` is a distinct status
#: rather than a refusal code so a caller can branch on "stored state
#: disagrees with the delivered document" without string-matching (§9.2).
STORE_STATUSES = ("accepted", "replay", "refused", "conflict")

#: The five integrity verdicts a read path can report (§15.2). Four of them are
#: members of the reducer's own refusal vocabulary; `ok` is the absence of a
#: verdict, so the store mints no new integrity language.
STORE_INTEGRITY = (
    "ok",
    "history_corrupt",
    "history_unknown_event",
    "policy_version_unsupported",
    "snapshot_divergence",
)

#: Three INFRASTRUCTURE codes — facts about the ledger, never facts about a
#: workflow, which is why none of them enters the frozen 43-member workflow
#: refusal vocabulary (§8.4).
STORE_ERROR_CODES = (
    "store_schema_unsupported",
    "store_argument_invalid",
    "store_unavailable",
)

#: The four §5.8 ROW-hash identities. They are this module's own frozen
#: constants in the `aos.*` house style, exactly as `routing.py` and
#: `agent_handoffs.py` define theirs — NOT document schemas, and they touch
#: neither U-W2 §13.4's six minted record schemas nor the U-X1 registry.
COMMAND_ROW_SCHEMA = "aos.workflow-command-row/v1"
INTENT_ROW_SCHEMA = "aos.workflow-intent-row/v1"
RECEIPT_ROW_SCHEMA = "aos.workflow-receipt-row/v1"
FACT_ROW_SCHEMA = "aos.workflow-fact-row/v1"

#: The one `tasks` status that closes a task (§10.4). Pinned by §20 row S20 to
#: be a `models.TASK_STATUSES` member and the status `ops.mark_done` sets.
_TASK_CLOSED_STATUS = models.TASK_STATUSES[-1]

_HINTS = {
    "store_schema_unsupported": (
        "This build does not support that ledger schema version; migrate the "
        "database deliberately."
    ),
    "store_argument_invalid": (
        "That argument is not a value this store accepts."
    ),
    "store_unavailable": (
        "The ledger could not be read or written; nothing was changed."
    ),
}


class WorkflowStoreError(AosError):
    """One of three closed INFRASTRUCTURE codes (§8.4).

    Inherits `AosError`, so the CLI's single refusal choke point exits 1 with a
    bounded, value-free message. The message names the code and a fixed hint
    and never carries SQL text, a file path, a column value, or an exception's
    string — an undeclared code is a KeyError programming failure, not a
    runtime path.
    """

    def __init__(self, code: str) -> None:
        if code not in _HINTS:
            raise KeyError(f"undeclared workflow store code: {code!r}")
        self.code = code
        super().__init__(f"Workflow store [{code}]: {_HINTS[code]}")


# ---------------------------------------------------------------------------
# Pattern gates. The engine's compiled patterns are private, so the two the
# §10.2 P2 subset needs are compiled here; `re` is imported for exactly this.

_UUID_RE = re.compile(protocols.UUID_PATTERN, re.ASCII)
_WORKFLOW_ID_RE = re.compile(r"^WF-[0-9]{1,19}$", re.ASCII)
_AOS_TASK_ID_RE = re.compile(protocols.AOS_TASK_ID_PATTERN, re.ASCII)

#: A diagnostics KEY is a closed lowercase name; a diagnostics VALUE is a
#: bounded integer or a member of a closed vocabulary. Anything else is dropped
#: rather than copied, so no stored column value, no document excerpt and no
#: exception string can reach a caller through `StoreOutcome.diagnostics`
#: (§18.5). Membership, not shape: a shape rule would admit a lowercase
#: credential token, which is one refactor away from a leak.
_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$", re.ASCII)

_CLOSED_DIAGNOSTIC_VALUES = frozenset(
    workflow_engine.WORKFLOW_REFUSAL_REASONS
    + workflow_engine.WORKFLOW_STATES
    + workflow_engine.WORKFLOW_COMMANDS
    + workflow_engine.WORKFLOW_EVENTS
    + workflow_engine.WORKFLOW_RECEIPT_KINDS
    + workflow_engine.WORKFLOW_INTENT_KINDS
    + workflow_engine.APPROVAL_SCOPES
    + tuple(protocols.REASON_HINTS)
    + ("valid", "warning", "requires_external_authority",
       "invalid", "unresolved", "ineligible", "success", "fail",
       "partial", "unknown")
)


# ---------------------------------------------------------------------------
# SQL. Every statement is a module-level constant; every value binds through a
# `?` placeholder; the ONLY interpolated identifiers are the six frozen
# table-name constants from `db.py` (§18.5, pinned by §20 row S18).

_SQL_SCHEMA_VERSION = "SELECT value FROM meta WHERE key = 'schema_version'"
_SQL_TASK_STATUS = "SELECT status FROM tasks WHERE id = ?"

_WORKFLOW_COLUMNS = (
    "id, task_id, work_spec_sha256, report_sha256, snapshot_sha256, "
    "registry_version, compile_status, work_spec_document, report_document, "
    "state, revision, policy_version, approval_required, dispatch_intent_id, "
    "cancel_intent_id, runtime_task_uuid, queue_route, created_at, "
    "updated_at, content_sha256"
)
_SQL_SELECT_WORKFLOW = (
    f"SELECT {_WORKFLOW_COLUMNS} FROM {db.WORKFLOWS_TABLE} WHERE id = ?"
)
_SQL_SELECT_WORKFLOWS = (
    f"SELECT {_WORKFLOW_COLUMNS} FROM {db.WORKFLOWS_TABLE} ORDER BY id ASC"
)
_SQL_SELECT_WORKFLOW_IDS = f"SELECT id FROM {db.WORKFLOWS_TABLE} ORDER BY id ASC"
_SQL_WORKFLOW_EXISTS = (
    f"SELECT 1 FROM {db.WORKFLOWS_TABLE} WHERE id = ? OR work_spec_sha256 = ?"
)
_SQL_INSERT_WORKFLOW = (
    f"INSERT INTO {db.WORKFLOWS_TABLE} ("
    "id, task_id, work_spec_sha256, report_sha256, snapshot_sha256, "
    "registry_version, compile_status, work_spec_document, report_document, "
    "state, revision, policy_version, approval_required, dispatch_intent_id, "
    "cancel_intent_id, runtime_task_uuid, queue_route, created_at, "
    "updated_at, content_sha256"
    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
_SQL_CAS_WORKFLOW = (
    f"UPDATE {db.WORKFLOWS_TABLE} SET state = ?, revision = ?, "
    "dispatch_intent_id = ?, cancel_intent_id = ?, runtime_task_uuid = ?, "
    "queue_route = ?, policy_version = ?, updated_at = ?, content_sha256 = ? "
    "WHERE id = ? AND revision = ?"
)

_EVENT_COLUMNS = (
    "seq, event, from_state, to_state, revision, policy_version, command_id, "
    "command_sha256, actor, payload_json, created_at, content_sha256"
)
_SQL_SELECT_EVENTS = (
    f"SELECT {_EVENT_COLUMNS} FROM {db.WORKFLOW_EVENTS_TABLE} "
    "WHERE workflow_id = ? ORDER BY seq"
)
_SQL_INSERT_EVENT = (
    f"INSERT INTO {db.WORKFLOW_EVENTS_TABLE} ("
    "workflow_id, seq, event, from_state, to_state, revision, policy_version, "
    "command_id, command_sha256, actor, payload_json, created_at, "
    "content_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_SQL_SELECT_COMMAND = (
    "SELECT workflow_id, command, command_sha256, resulting_revision, "
    f"event_seq_first, event_seq_last FROM {db.WORKFLOW_COMMANDS_TABLE} "
    "WHERE command_id = ?"
)
_SQL_SELECT_COMMAND_ROWS = (
    "SELECT id, workflow_id, command_id, command, command_sha256, "
    "expected_revision, resulting_revision, event_seq_first, event_seq_last, "
    f"created_at, content_sha256 FROM {db.WORKFLOW_COMMANDS_TABLE} "
    "WHERE workflow_id = ? ORDER BY id ASC"
)
_SQL_INSERT_COMMAND = (
    f"INSERT INTO {db.WORKFLOW_COMMANDS_TABLE} ("
    "workflow_id, command_id, command, command_sha256, expected_revision, "
    "resulting_revision, event_seq_first, event_seq_last, created_at, "
    "content_sha256) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
_SQL_FINALIZE_COMMAND = (
    f"UPDATE {db.WORKFLOW_COMMANDS_TABLE} SET content_sha256 = ? WHERE id = ?"
)

_INTENT_COLUMNS = (
    "id, workflow_id, intent_id, intent_kind, idempotency_key, queue_route, "
    "document, status, resolved_receipt_id, created_at, content_sha256"
)
_SQL_SELECT_INTENT = (
    f"SELECT {_INTENT_COLUMNS} FROM {db.WORKFLOW_INTENTS_TABLE} "
    "WHERE intent_id = ?"
)
_SQL_SELECT_INTENT_ROWS = (
    f"SELECT {_INTENT_COLUMNS} FROM {db.WORKFLOW_INTENTS_TABLE} "
    "WHERE workflow_id = ? ORDER BY id ASC"
)
_SQL_SELECT_OUTSTANDING = (
    f"SELECT {_INTENT_COLUMNS} FROM {db.WORKFLOW_INTENTS_TABLE} "
    "WHERE status = 'outstanding' ORDER BY id ASC"
)
_SQL_SELECT_OUTSTANDING_FOR = (
    f"SELECT {_INTENT_COLUMNS} FROM {db.WORKFLOW_INTENTS_TABLE} "
    "WHERE status = 'outstanding' AND workflow_id = ? ORDER BY id ASC"
)
_SQL_INSERT_INTENT = (
    f"INSERT INTO {db.WORKFLOW_INTENTS_TABLE} ("
    "workflow_id, intent_id, intent_kind, idempotency_key, queue_route, "
    "document, status, resolved_receipt_id, created_at, content_sha256"
    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
_SQL_FINALIZE_INTENT = (
    f"UPDATE {db.WORKFLOW_INTENTS_TABLE} SET content_sha256 = ? WHERE id = ?"
)
_SQL_CLOSE_INTENT = (
    f"UPDATE {db.WORKFLOW_INTENTS_TABLE} SET status = ?, "
    "resolved_receipt_id = ?, content_sha256 = ? "
    "WHERE intent_id = ? AND status = 'outstanding'"
)

_RECEIPT_COLUMNS = (
    "id, workflow_id, receipt_id, receipt_kind, intent_id, runtime_task_uuid, "
    "document, receipt_sha256, created_at, content_sha256"
)
_SQL_SELECT_RECEIPT = (
    "SELECT workflow_id, receipt_sha256 "
    f"FROM {db.WORKFLOW_RECEIPTS_TABLE} WHERE receipt_id = ?"
)
_SQL_SELECT_RECEIPT_ROWS = (
    f"SELECT {_RECEIPT_COLUMNS} FROM {db.WORKFLOW_RECEIPTS_TABLE} "
    "WHERE workflow_id = ? ORDER BY id ASC"
)
_SQL_INSERT_RECEIPT = (
    f"INSERT INTO {db.WORKFLOW_RECEIPTS_TABLE} ("
    "workflow_id, receipt_id, receipt_kind, intent_id, runtime_task_uuid, "
    "document, receipt_sha256, created_at, content_sha256"
    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
_SQL_FINALIZE_RECEIPT = (
    f"UPDATE {db.WORKFLOW_RECEIPTS_TABLE} SET content_sha256 = ? WHERE id = ?"
)

_FACT_COLUMNS = (
    "id, workflow_id, fact_kind, fact_scope, document, document_sha256, "
    "recorded_at, content_sha256"
)
_SQL_SELECT_FACT_ROWS = (
    f"SELECT {_FACT_COLUMNS} FROM {db.WORKFLOW_FACTS_TABLE} "
    "WHERE workflow_id = ? ORDER BY id ASC"
)
_SQL_INSERT_FACT = (
    f"INSERT INTO {db.WORKFLOW_FACTS_TABLE} ("
    "workflow_id, fact_kind, fact_scope, document, document_sha256, "
    "recorded_at, content_sha256) VALUES (?, ?, ?, ?, ?, ?, ?) "
    "ON CONFLICT(workflow_id, fact_kind, document_sha256) DO NOTHING"
)
_SQL_FINALIZE_FACT = (
    f"UPDATE {db.WORKFLOW_FACTS_TABLE} SET content_sha256 = ? WHERE id = ?"
)

#: Written into a row-hash column between its INSERT and the finalization
#: UPDATE of §5.8. It never survives the transaction: the finalization is the
#: next statement, and any exception in between rolls the whole row away.
_PENDING_HASH = "0" * 64


# ---------------------------------------------------------------------------
# Public record types (§8.2). Frozen dataclasses over fresh values.

@dataclass(frozen=True)
class StoreOutcome:
    """One `submit` call's whole result (§9.1). A refusal never raises out of
    `submit`: it is RETURNED, with a closed four-status vocabulary."""

    status: str
    replay: bool
    workflow_id: str | None
    command_id: str | None
    revision: int | None
    events: tuple
    intent: dict | None
    snapshot: dict | None
    reason: str | None
    where: str | None
    diagnostics: dict = field(default_factory=dict)
    refusal: workflow_engine.WorkflowRefusal | None = None


@dataclass(frozen=True)
class WorkflowRecord:
    """The `workflows` projection plus an integrity verdict (§8.2).

    `task_id` is the INTEGER ledger row id, never a rendered `T-<n>` string:
    the artifact's `aos_task_id` is stored verbatim inside the snapshot and the
    `workflow_admitted` payload, and `T-7` and `T-0007` are both pattern-valid,
    so re-rendering from the integer would state a different string than the
    one that was admitted.
    """

    workflow_id: str
    id: int
    task_id: int
    state: str
    revision: int
    policy_version: int
    compile_status: str
    approval_required: bool
    work_spec_sha256: str
    report_sha256: str
    snapshot_sha256: str
    registry_version: int
    dispatch_intent_id: str | None
    cancel_intent_id: str | None
    runtime_task_uuid: str | None
    queue_route: str | None
    created_at: str
    updated_at: str
    content_sha256: str
    integrity: str


@dataclass(frozen=True)
class HistoryView:
    """Reconstituted events in `seq` order plus the integrity verdict and the
    first unreadable `seq` (§8.3). Total on a damaged workflow."""

    workflow_id: str
    events: tuple
    integrity: str
    unreadable_seq: int | None


@dataclass(frozen=True)
class IntentView:
    """One outbox row, readable or not (§8.3). An unreadable row is reported
    with `readable=False` and `document=None`, never silently dropped."""

    workflow_id: str
    intent_id: str
    intent_kind: str
    idempotency_key: str
    queue_route: str
    status: str
    resolved_receipt_id: str | None
    created_at: str
    document: dict | None
    content_sha256: str
    readable: bool


@dataclass(frozen=True)
class RebuildResult:
    """`fold` + splice + seal, WITHOUT comparing against the projection
    (§8.3). `snapshot` is non-`None` exactly when `integrity == "ok"`."""

    workflow_id: str
    snapshot: dict | None
    integrity: str
    reason: str | None
    where: str | None


@dataclass(frozen=True)
class VerifyReport:
    """One workflow's integrity comparison (§15.4). `divergent_rows` is a
    tuple of `(table_name, row_id)` pairs whose §5.8 row hash does not
    recompute."""

    workflow_id: str
    integrity: str
    reason: str | None
    where: str | None
    stored_content_sha256: str
    rebuilt_content_sha256: str | None
    divergent_fields: tuple
    divergent_rows: tuple
    last_seq: int | None
    revision: int | None


# ---------------------------------------------------------------------------
# Internal control flow. None of these escapes a public function.

class _RowUnreadable(Exception):
    """A stored row does not hold what the schema requires — a BLOB where text
    is required, a NULL in a NOT NULL column reached through a damaged file, a
    document that will not parse canonically.

    Raised by the explicit type checks BELOW every access, never by catching a
    `KeyError`/`TypeError`/`AttributeError` after the fact (§18.4). Carries a
    schema-safe path only, never the value.
    """

    def __init__(self, where: str) -> None:
        self.where = where
        super().__init__(where)


class _Refused(Exception):
    """Carries a CONSTRUCTED `workflow_engine.WorkflowRefusal` out of the
    locked section so the transaction rolls back with nothing in it.

    The refusal object is built, never raised as itself — `submit` returns it
    inside a `StoreOutcome` (§8.3, §9.2).
    """

    def __init__(self, refusal, *, command_id=None, workflow_id=None) -> None:
        self.refusal = refusal
        self.command_id = command_id
        self.workflow_id = workflow_id
        super().__init__(refusal.reason)


class _Replay(Exception):
    """An exact duplicate was recognised: carries the original outcome parts
    out of the locked section so the empty transaction rolls back (§10.3 C3,
    §11.2)."""

    def __init__(self, *, workflow_id, row_id, revision, events) -> None:
        self.workflow_id = workflow_id
        self.row_id = row_id
        self.revision = revision
        self.events = events
        super().__init__("replay")


def _refusal(reason: str, where: str = "", **diagnostics):
    """Construct — never raise — a closed reducer refusal (§9.2)."""
    return workflow_engine.WorkflowRefusal(reason, where, **diagnostics)


def _refuse(reason: str, where: str = "", **diagnostics) -> _Refused:
    return _Refused(_refusal(reason, where, **diagnostics))


# ---------------------------------------------------------------------------
# Untrusted-row accessors. Every one type-checks BEFORE it reads.

def _req_text(value, where: str) -> str:
    if not isinstance(value, str):
        raise _RowUnreadable(where)
    return value


def _opt_text(value, where: str):
    if value is None:
        return None
    return _req_text(value, where)


def _req_int(value, where: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise _RowUnreadable(where)
    # SQLite stores a full 64-bit integer, but every payload this module
    # digests goes through `protocols.serialize_canonical`, whose `INT_MAX` is
    # 2**53-1. A column outside that range is therefore UNREADABLE rather than
    # a raw `ProtocolError` escaping a public boundary later (§18.3, §18.4).
    if not -protocols.INT_MAX <= value <= protocols.INT_MAX:
        raise _RowUnreadable(where)
    return value


def _req_row_id(value, where: str) -> int:
    """A ledger ROW id, bounded by SQLite's 64-bit range rather than the
    canonical `INT_MAX`.

    The workflow row id is the reducer's DERIVED identity (§5.1) and routinely
    exceeds `protocols.INT_MAX`; it is never serialized as an integer — it is
    rendered `"WF-<n>"` or bound by its sha256 leaf — so the canonical bound
    does not apply to it, while the storage bound still does.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise _RowUnreadable(where)
    if not 1 <= value <= ids.MAX_ID:
        raise _RowUnreadable(where)
    return value


def _parse_stored(text, where: str) -> dict:
    """A stored document column -> a validated canonical value.

    `parse_canonical` requires bytes, so a column holding a non-text value is
    marked unreadable by TYPE CHECK before any encode, never coerced (§18.3).
    """
    raw = _req_text(text, where)
    try:
        encoded = raw.encode("utf-8")
    except UnicodeError:
        raise _RowUnreadable(where) from None
    try:
        return protocols.parse_canonical(encoded)
    except protocols.ProtocolError:
        raise _RowUnreadable(where) from None


def _serialize(value) -> str:
    return protocols.serialize_canonical(value).decode("utf-8")


def _fresh(value):
    """The canonical round trip every returned structure passes through, so a
    caller mutating a result can never alter a stored row, a later read, or
    another returned record (§9.2, §20 row S19)."""
    return protocols.parse_canonical(protocols.serialize_canonical(value))


def _seal(body: dict) -> dict:
    """The engine's `_seal` two-liner, re-implemented locally because `_seal`
    is private; pinned byte-equal to the engine's output by §20 row S2."""
    record = _fresh(
        {k: v for k, v in body.items() if k != protocols.CONTENT_HASH_FIELD}
    )
    record[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(record)
    return record


def _render(workflow_row_id: int) -> str:
    """The store's workflow renderer (§5.1).

    NOT `ids.render_id`: that zero-pads to width 4 and would produce `WF-0007`
    where the engine minted `WF-7`, breaking every event digest. Pinned
    byte-equal to `workflow_engine._workflow_identity` by §20 row S3.
    """
    return "WF-" + str(workflow_row_id)


def _leaf(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _row_digest(payload: dict) -> str:
    return hashlib.sha256(protocols.serialize_canonical(payload)).hexdigest()


def _finalize(conn, sql, row_sql, row_id, payload_of) -> None:
    """Write a row's §5.8 hash, inside the creating transaction.

    A row that cannot be hashed at all — a rowid past the canonical `INT_MAX`
    because a hostile writer pre-seeded one, or a column holding something no
    honest write could have produced — is a DAMAGED LEDGER, not a caller
    error, so it closes as `store_unavailable` (§8.4). Without this guard the
    private `_RowUnreadable` would cross the public boundary (§18.4).
    """
    row = _fetchone(conn, row_sql, (row_id,))
    if row is None:
        raise WorkflowStoreError("store_unavailable")
    try:
        digest = _row_digest(payload_of(row))
    except (_RowUnreadable, protocols.ProtocolError):
        raise WorkflowStoreError("store_unavailable") from None
    _execute(conn, sql, (digest, row_id))


def _text_leaf(value, where: str) -> str:
    return _leaf(_req_text(value, where))


def _opt_leaf(value, where: str):
    return None if value is None else _text_leaf(value, where)


def _safe_diagnostics(raw) -> dict:
    """Bounded integers and closed lowercase codes ONLY (§18.5).

    A refusal's diagnostics may originate in a document a hostile writer
    supplied, so anything that is not an int, a bool, or a short closed-code
    string is DROPPED rather than copied — a value can never ride out of the
    store inside a diagnostics map.
    """
    if not isinstance(raw, dict):
        return {}
    safe = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not _CODE_RE.fullmatch(key):
            continue
        if isinstance(value, bool):
            safe[key] = value
        elif isinstance(value, int):
            if -protocols.INT_MAX <= value <= protocols.INT_MAX:
                safe[key] = value
        elif isinstance(value, str) and value in _CLOSED_DIAGNOSTIC_VALUES:
            safe[key] = value
    return safe


# ---------------------------------------------------------------------------
# §5.8 row-hash payloads. `record_schema` key, text fields bound by their
# sha256 leaf, integers bound directly, `None` passed through,
# `content_sha256` excluded — the live U-A3 idiom.

def _command_row_payload(row) -> dict:
    return {
        "record_schema": COMMAND_ROW_SCHEMA,
        "id": _req_int(row[0], "/id"),
        # The canonical workflow identity, bound by its sha256 leaf like
        # every other text member (U-W2 amendment A2 §A2.2, U-W2.2 addendum
        # B1 §B1.2). §5.8's superseded direct-int binding was unsatisfiable:
        # the row id is the reducer's DERIVED 63-bit identity (§5.1) and the
        # frozen digest function refuses integers above `protocols.INT_MAX`
        # (2**53-1), so 1023 of every 1024 identities could not be sealed.
        # The preimage is the RENDERED identity `_render(id)`, not its bare
        # decimal digits — one spelling, the one the architecture already
        # freezes. Pinned by §20 rows S25 and S26.
        "workflow_id_sha256": _leaf(_render(_req_row_id(row[1], "/workflow_id"))),
        "expected_revision": _req_int(row[5], "/expected_revision"),
        "resulting_revision": _req_int(row[6], "/resulting_revision"),
        "event_seq_first": _req_int(row[7], "/event_seq_first"),
        "event_seq_last": _req_int(row[8], "/event_seq_last"),
        "command_id_sha256": _text_leaf(row[2], "/command_id"),
        # The VERB string's leaf. Named `command_sha256` and the envelope
        # digest column `command_sha256_sha256` so the leaf convention's one
        # possible collision cannot occur (§5.8).
        "command_sha256": _text_leaf(row[3], "/command"),
        "command_sha256_sha256": _text_leaf(row[4], "/command_sha256"),
        "created_at_sha256": _text_leaf(row[9], "/created_at"),
    }


def _intent_row_payload(row) -> dict:
    return {
        "record_schema": INTENT_ROW_SCHEMA,
        "id": _req_int(row[0], "/id"),
        # The canonical workflow identity, bound by its sha256 leaf like
        # every other text member (U-W2 amendment A2 §A2.2, U-W2.2 addendum
        # B1 §B1.2). §5.8's superseded direct-int binding was unsatisfiable:
        # the row id is the reducer's DERIVED 63-bit identity (§5.1) and the
        # frozen digest function refuses integers above `protocols.INT_MAX`
        # (2**53-1), so 1023 of every 1024 identities could not be sealed.
        # The preimage is the RENDERED identity `_render(id)`, not its bare
        # decimal digits — one spelling, the one the architecture already
        # freezes. Pinned by §20 rows S25 and S26.
        "workflow_id_sha256": _leaf(_render(_req_row_id(row[1], "/workflow_id"))),
        "intent_id_sha256": _text_leaf(row[2], "/intent_id"),
        "intent_kind_sha256": _text_leaf(row[3], "/intent_kind"),
        "idempotency_key_sha256": _text_leaf(row[4], "/idempotency_key"),
        "queue_route_sha256": _text_leaf(row[5], "/queue_route"),
        # The RECOMPUTED digest of the stored document, never a value the row
        # declares about itself.
        "document_sha256": protocols.content_digest(
            _parse_stored(row[6], "/document")
        ),
        "status_sha256": _text_leaf(row[7], "/status"),
        "resolved_receipt_id_sha256": _opt_leaf(row[8], "/resolved_receipt_id"),
        "created_at_sha256": _text_leaf(row[9], "/created_at"),
    }


def _receipt_row_payload(row) -> dict:
    return {
        "record_schema": RECEIPT_ROW_SCHEMA,
        "id": _req_int(row[0], "/id"),
        # The canonical workflow identity, bound by its sha256 leaf like
        # every other text member (U-W2 amendment A2 §A2.2, U-W2.2 addendum
        # B1 §B1.2). §5.8's superseded direct-int binding was unsatisfiable:
        # the row id is the reducer's DERIVED 63-bit identity (§5.1) and the
        # frozen digest function refuses integers above `protocols.INT_MAX`
        # (2**53-1), so 1023 of every 1024 identities could not be sealed.
        # The preimage is the RENDERED identity `_render(id)`, not its bare
        # decimal digits — one spelling, the one the architecture already
        # freezes. Pinned by §20 rows S25 and S26.
        "workflow_id_sha256": _leaf(_render(_req_row_id(row[1], "/workflow_id"))),
        "receipt_id_sha256": _text_leaf(row[2], "/receipt_id"),
        "receipt_kind_sha256": _text_leaf(row[3], "/receipt_kind"),
        "intent_id_sha256": _opt_leaf(row[4], "/intent_id"),
        "runtime_task_uuid_sha256": _opt_leaf(row[5], "/runtime_task_uuid"),
        "receipt_sha256_sha256": _text_leaf(row[7], "/receipt_sha256"),
        "created_at_sha256": _text_leaf(row[8], "/created_at"),
    }


def _fact_row_payload(row) -> dict:
    return {
        "record_schema": FACT_ROW_SCHEMA,
        "id": _req_int(row[0], "/id"),
        # The canonical workflow identity, bound by its sha256 leaf like
        # every other text member (U-W2 amendment A2 §A2.2, U-W2.2 addendum
        # B1 §B1.2). §5.8's superseded direct-int binding was unsatisfiable:
        # the row id is the reducer's DERIVED 63-bit identity (§5.1) and the
        # frozen digest function refuses integers above `protocols.INT_MAX`
        # (2**53-1), so 1023 of every 1024 identities could not be sealed.
        # The preimage is the RENDERED identity `_render(id)`, not its bare
        # decimal digits — one spelling, the one the architecture already
        # freezes. Pinned by §20 rows S25 and S26.
        "workflow_id_sha256": _leaf(_render(_req_row_id(row[1], "/workflow_id"))),
        "fact_kind_sha256": _text_leaf(row[2], "/fact_kind"),
        "fact_scope_sha256": _opt_leaf(row[3], "/fact_scope"),
        "document_sha256_sha256": _text_leaf(row[5], "/document_sha256"),
        "recorded_at_sha256": _text_leaf(row[6], "/recorded_at"),
    }


#: `(table name, SELECT, payload builder, stored-hash index)` — the four
#: row-hash tables `verify` recomputes (§15.4 step 4).
_ROW_HASH_TABLES = (
    (db.WORKFLOW_COMMANDS_TABLE, _SQL_SELECT_COMMAND_ROWS,
     _command_row_payload, 10),
    (db.WORKFLOW_INTENTS_TABLE, _SQL_SELECT_INTENT_ROWS,
     _intent_row_payload, 10),
    (db.WORKFLOW_RECEIPTS_TABLE, _SQL_SELECT_RECEIPT_ROWS,
     _receipt_row_payload, 9),
    (db.WORKFLOW_FACTS_TABLE, _SQL_SELECT_FACT_ROWS, _fact_row_payload, 7),
)


# ---------------------------------------------------------------------------
# Connection helpers. Every `sqlite3.Error` the store did not deliberately map
# becomes `store_unavailable` (§8.4), at the exact call site.

def _execute(conn, sql, params=()):
    try:
        return conn.execute(sql, params)
    except sqlite3.Error:
        raise WorkflowStoreError("store_unavailable") from None


def _fetchone(conn, sql, params=()):
    return _execute(conn, sql, params).fetchone()


def _fetchall(conn, sql, params=()):
    return _execute(conn, sql, params).fetchall()


def _require_schema(conn) -> None:
    """P1: this module accepts a caller-supplied connection, so it cannot
    assume the connection came through `db.open_db`'s version gate (§6)."""
    row = _fetchone(conn, _SQL_SCHEMA_VERSION)
    value = row[0] if row is not None else None
    if value != db.SCHEMA_VERSION:
        raise WorkflowStoreError("store_schema_unsupported")


def _require_workflow_id(workflow_id) -> int:
    """A `WF-<n>` string -> the row id, or `store_argument_invalid` BEFORE any
    query touches a workflow table (§8.3)."""
    if not isinstance(workflow_id, str):
        raise WorkflowStoreError("store_argument_invalid")
    try:
        return ids.parse_id(workflow_id, "workflow")
    except AosError:
        raise WorkflowStoreError("store_argument_invalid") from None


# ---------------------------------------------------------------------------
# History reconstitution (§7.4) and the snapshot rebuild (§7.2)

def _event_record(row, workflow_row_id: int, work_spec_sha256) -> dict:
    """Rebuild one `aos.workflow-event/v1` record from its columns (§7.4).

    The sealed event digest is what proves the reconstitution faithful: it
    covers `workflow_id` and `work_spec_sha256`, so a spliced `workflows.id`
    or `work_spec_sha256` makes every event digest fail and the workflow reads
    `history_corrupt` rather than silently folding under a false identity.
    """
    record = {
        "schema": workflow_engine.WORKFLOW_EVENT_SCHEMA,
        "event": _req_text(row[1], "/event"),
        "workflow_id": _render(workflow_row_id),
        "work_spec_sha256": _req_text(work_spec_sha256, "/work_spec_sha256"),
        "seq": _req_int(row[0], "/seq"),
        "revision": _req_int(row[4], "/revision"),
        "policy_version": _req_int(row[5], "/policy_version"),
        "from_state": _opt_text(row[2], "/from_state"),
        "to_state": _opt_text(row[3], "/to_state"),
        "command_id": _req_text(row[6], "/command_id"),
        "command_sha256": _req_text(row[7], "/command_sha256"),
        "actor": _req_text(row[8], "/actor"),
        "payload": _parse_stored(row[9], "/payload_json"),
        "created_at": _req_text(row[10], "/created_at"),
        protocols.CONTENT_HASH_FIELD: _req_text(row[11], "/content_sha256"),
    }
    # Reconstitution must yield a CANONICAL record or report the row
    # unreadable. A column that is text but oversized passes every type check
    # above and would only be refused later — inside `fold`, or inside the
    # fresh copy a read path hands back, where a raw `ProtocolError` would
    # escape the public boundary (§18.4, §20 row S17).
    try:
        return _fresh(record)
    except protocols.ProtocolError:
        raise _RowUnreadable("/") from None


def _read_history(conn, workflow_row_id: int, work_spec_sha256):
    """(records, refusal, unreadable_seq). Reports; never repairs.

    `seq` is dense from 1 per workflow and always read `ORDER BY seq`, so a gap
    or a non-dense sequence is `history_corrupt` at the exact index (§15.1).
    """
    rows = _fetchall(conn, _SQL_SELECT_EVENTS, (workflow_row_id,))
    records = []
    for index, row in enumerate(rows):
        try:
            record = _event_record(row, workflow_row_id, work_spec_sha256)
        except _RowUnreadable as unreadable:
            seq = row[0] if isinstance(row[0], int) else index + 1
            return (
                tuple(records),
                _refusal("history_corrupt", f"/{index}{unreadable.where}"),
                seq,
            )
        if record["seq"] != index + 1:
            return (
                tuple(records),
                _refusal("history_corrupt", f"/{index}/seq"),
                record["seq"],
            )
        records.append(record)
    return tuple(records), None, None


def _fold(records):
    """`fold`, with its closed refusal returned rather than raised."""
    try:
        return workflow_engine.fold(records), None
    except workflow_engine.WorkflowRefusal as refusal:
        return None, refusal


def _splice_and_seal(folded: dict, work_spec_document, report_document) -> dict:
    """§7.2 steps 4-5: the two verbatim bodies replace the `None`s `fold`
    returns, then the record is resealed locally."""
    body = dict(folded)
    body["work_spec_document"] = work_spec_document
    body["report_document"] = report_document
    return _seal(body)


#: The seventeen member-backed projection columns of §7.2 step 6, paired with
#: the snapshot member each one must equal. `workflow_id`, `task_id` and
#: `approval_required` carry declared conversions and are handled separately.
_PROJECTION_FIELDS = (
    ("work_spec_sha256", 2),
    ("report_sha256", 3),
    ("snapshot_sha256", 4),
    ("registry_version", 5),
    ("compile_status", 6),
    ("state", 9),
    ("revision", 10),
    ("policy_version", 11),
    ("dispatch_intent_id", 13),
    ("cancel_intent_id", 14),
    ("runtime_task_uuid", 15),
    ("queue_route", 16),
)


def _body_divergence(row, records) -> tuple:
    """§15.4 step 5: re-digest both stored bodies against the digests the
    `workflow_admitted` event recorded.

    "Rebuildable by `fold`" means exactly what §7.2 says and not more: a
    `verify` that demanded the BODIES come out of history would report
    divergence on every healthy workflow, because U-W2 §7 permits digests only
    in event payloads.
    """
    if not records:
        return ()
    # Both digests come out of the `workflow_admitted` PAYLOAD, which lives in
    # `payload_json` and is covered by the sealed event digest — not out of the
    # `workflows` columns the bodies sit beside. That is what makes this an
    # independent check rather than a row agreeing with itself.
    admitted = records[0]["payload"]
    out = []
    for column, member, index in (
        ("work_spec_document", "work_spec_sha256", 7),
        ("report_document", "report_sha256", 8),
    ):
        expected = admitted.get(member)
        try:
            document = _parse_stored(row[index], f"/{column}")
        except _RowUnreadable:
            out.append(column)
            continue
        if protocols.content_digest(document) != expected:
            out.append(column)
    return tuple(out)


def _divergent_fields(row, snapshot: dict, records=()) -> tuple:
    """§7.2 step 6, as data: every member-backed column compared against its
    rebuilt counterpart under the declared conversions.

    The two row timestamps (`created_at`, `updated_at`) have no snapshot
    counterpart and are deliberately OUTSIDE this gate: `created_at` is
    admission-immutable and `updated_at` moves only with the C14 CAS.
    """
    divergent = []
    # §7.2 lists `workflow_id` among the member-backed columns, and it is
    # compared here for completeness — but it cannot diverge by construction:
    # §7.4 reconstitutes each event's identity FROM this same column, so the
    # rebuilt snapshot always agrees with it. The identity's REAL protection is
    # the sealed event digest, which covers `workflow_id`, so a spliced
    # `workflows.id` makes every digest fail and the workflow reads
    # `history_corrupt` instead of folding under a false identity (§7.4,
    # pinned by `test_a_spliced_identity_is_history_corrupt`). Declared, not
    # discovered: this member is a redundancy backstop, not a live check.
    if snapshot.get("workflow_id") != _render(row[0]):
        divergent.append("workflow_id")
    # The snapshot carries the artifact's VERBATIM admitted `T-<n>` string;
    # the column carries the integer. Compare through `parse_id`, never by
    # re-rendering, because `T-7` and `T-0007` are both pattern-valid.
    task_text = snapshot.get("task_id")
    task_id = None
    if isinstance(task_text, str) and _AOS_TASK_ID_RE.fullmatch(task_text):
        try:
            task_id = ids.parse_id(task_text, "task")
        except AosError:
            task_id = None
    if task_id is None or task_id != row[1]:
        divergent.append("task_id")
    for name, index in _PROJECTION_FIELDS:
        if snapshot.get(name) != row[index]:
            divergent.append(name)
    approval = snapshot.get("approval_required")
    if not isinstance(approval, bool) or int(approval) != row[12]:
        divergent.append("approval_required")
    # The sixteenth and seventeenth members: the two document bodies. Comparing
    # them against the SPLICED snapshot would be tautological — §7.2 step 4 put
    # the very same parse there — so the real binding is used instead: each
    # body is re-digested against the digest the `workflow_admitted` PAYLOAD
    # recorded, which lives in `payload_json` under the sealed event digest and
    # is therefore independent of the columns the bodies sit beside (§18.1).
    # This runs wherever the gate runs, not only inside `verify` (§15.2).
    divergent.extend(_body_divergence(row, records))
    if snapshot.get(protocols.CONTENT_HASH_FIELD) != row[19]:
        divergent.append(protocols.CONTENT_HASH_FIELD)
    return tuple(divergent)


def _rebuild_snapshot(conn, row):
    """(snapshot, refusal, unreadable_seq, records): §7.2 steps 2-5 for one row.

    Returns the rebuilt-and-sealed snapshot WITHOUT comparing it against the
    projection — that comparison is step 6, which `_load_snapshot` and
    `verify` apply differently.
    """
    try:
        work_spec_sha256 = _req_text(row[2], "/work_spec_sha256")
    except _RowUnreadable as unreadable:
        return None, _refusal("snapshot_divergence", unreadable.where), None, ()
    records, refusal, unreadable_seq = _read_history(
        conn, row[0], work_spec_sha256
    )
    if refusal is not None:
        return None, refusal, unreadable_seq, records
    folded, refusal = _fold(records)
    if refusal is not None:
        return None, refusal, None, records
    try:
        work_spec_document = _parse_stored(row[7], "/work_spec_document")
        report_document = _parse_stored(row[8], "/report_document")
    except _RowUnreadable as unreadable:
        return None, _refusal("snapshot_divergence", unreadable.where), None, records
    try:
        sealed = _splice_and_seal(folded, work_spec_document, report_document)
    except protocols.ProtocolError:
        return None, _refusal("snapshot_divergence", "/"), None, records
    return sealed, None, None, records


def _load_snapshot(conn, workflow_row_id: int):
    """§7.2, all six steps. Raises `_Refused` with the exact closed verdict.

    Snapshot/history agreement is therefore checked on EVERY command, not only
    at `verify`, so a tampered projection cannot survive one write.
    """
    row = _fetchone(conn, _SQL_SELECT_WORKFLOW, (workflow_row_id,))
    if row is None:
        raise _refuse("workflow_unknown", "/workflow_id")
    snapshot, refusal, _seq, records = _rebuild_snapshot(conn, row)
    if refusal is not None:
        raise _Refused(refusal)
    divergent = _divergent_fields(row, snapshot, records)
    if divergent:
        raise _refuse("snapshot_divergence", f"/{divergent[0]}")
    return row, snapshot


def _current_view(conn, workflow_row_id: int):
    """(revision, snapshot) for a refusal or replay outcome (§9.3).

    `revision` is the CURRENT stored revision when the workflow exists, else
    `None`; `snapshot` is the CURRENT snapshot when the history verifies, else
    `None`. Neither read can fail the call: this runs on paths that have
    already decided their status.
    """
    try:
        row = _fetchone(conn, _SQL_SELECT_WORKFLOW, (workflow_row_id,))
    except WorkflowStoreError:
        return None, None
    if row is None:
        return None, None
    revision = row[10] if isinstance(row[10], int) else None
    try:
        snapshot, refusal, _seq, records = _rebuild_snapshot(conn, row)
    except WorkflowStoreError:
        return revision, None
    if refusal is not None:
        return revision, None
    if _divergent_fields(row, snapshot, records):
        return revision, None
    return revision, snapshot


# ---------------------------------------------------------------------------
# P2: the pre-lock command identity (§10.2)
#
# A STRICT SUBSET of `workflow_engine`'s envelope verification: it checks only
# the four things the store itself needs — `command_id`, `workflow_id`, verb
# membership and the self-digest — and defers every other envelope rule to
# `decide`. §20 row S9 pins that the subset never accepts a command `decide`
# rejects on those four fields and never rejects one `decide` accepts.

def _command_identity(document):
    if not isinstance(document, dict):
        raise _refuse("command_malformed", "/")
    try:
        fresh = _fresh(document)
    except protocols.ProtocolError as refusal:
        raise _Refused(
            _refusal("command_malformed", "/", code=refusal.code)
        ) from None

    # `command_id` is read FIRST so a refusal can still echo it: §9.1 says it
    # is `None` only when it could not be read, and a readable id beside an
    # unknown verb is readable.
    command_id = fresh.get("command_id")
    if not isinstance(command_id, str) or not _UUID_RE.fullmatch(command_id):
        command_id = None

    verb = fresh.get("command")
    if not isinstance(verb, str):
        raise _Refused(
            _refusal("command_malformed", "/command"), command_id=command_id
        )
    if verb not in workflow_engine.WORKFLOW_COMMANDS:
        raise _Refused(
            _refusal("command_unknown", "/command"), command_id=command_id
        )
    if command_id is None:
        raise _Refused(_refusal("command_malformed", "/command_id"))

    creates = verb == "admit_work_spec"
    workflow_id = fresh.get("workflow_id")
    if creates:
        if "workflow_id" in fresh:
            raise _Refused(
                _refusal("command_malformed", "/workflow_id"),
                command_id=command_id,
            )
        workflow_id = None
    elif not isinstance(workflow_id, str) or not _WORKFLOW_ID_RE.fullmatch(
        workflow_id
    ):
        raise _Refused(
            _refusal("command_malformed", "/workflow_id"),
            command_id=command_id,
        )

    digest = protocols.content_digest(fresh)
    if fresh.get(protocols.CONTENT_HASH_FIELD) != digest:
        raise _Refused(
            _refusal(
                "command_malformed", f"/{protocols.CONTENT_HASH_FIELD}"
            ),
            command_id=command_id,
            workflow_id=workflow_id,
        )
    return fresh, verb, command_id, workflow_id, digest


def _receipt_identity(payload):
    """(receipt_id, receipt_sha256, document) or `None` (§11.2).

    When the payload is not a canonically serializable object carrying a UUID
    `receipt_id`, the store SKIPS the dedupe entirely and lets `decide` refuse
    `receipt_malformed`: the store adds no receipt validation of its own and
    duplicates none (§11.1).
    """
    if not isinstance(payload, dict):
        return None
    document = payload.get("receipt_document")
    if not isinstance(document, dict):
        return None
    receipt_id = document.get("receipt_id")
    if not isinstance(receipt_id, str) or not _UUID_RE.fullmatch(receipt_id):
        return None
    try:
        digest = protocols.content_digest(document)
    except protocols.ProtocolError:
        return None
    return receipt_id, digest, document


# ---------------------------------------------------------------------------
# The nine mutation helpers (§13.3). These names are frozen ARCHITECTURE, not
# implementation detail: the crash matrix injects at exactly these boundaries.

def _insert_workflow(conn, snapshot: dict, row_id: int, task_id: int,
                     created_at: str) -> None:
    """A6. `content_sha256` comes from the sealed snapshot, so the row is born
    with its digest — the column has no default and a hashless row is
    unrepresentable (KA4).

    `created_at` is NOT a clock read: it is the accepted command's own
    caller-supplied instant, which the reducer already real-instant-checked and
    already copied into every event, so the whole six-table write is a pure
    function of the command and the prior rows and a crash-and-retry writes
    byte-identical rows (§10.7).
    """
    try:
        conn.execute(
            _SQL_INSERT_WORKFLOW,
            (
                row_id,
                task_id,
                snapshot["work_spec_sha256"],
                snapshot["report_sha256"],
                snapshot["snapshot_sha256"],
                snapshot["registry_version"],
                snapshot["compile_status"],
                _serialize(snapshot["work_spec_document"]),
                _serialize(snapshot["report_document"]),
                snapshot["state"],
                snapshot["revision"],
                snapshot["policy_version"],
                int(snapshot["approval_required"]),
                snapshot["dispatch_intent_id"],
                snapshot["cancel_intent_id"],
                snapshot["runtime_task_uuid"],
                snapshot["queue_route"],
                created_at,
                created_at,
                snapshot[protocols.CONTENT_HASH_FIELD],
            ),
        )
    except sqlite3.IntegrityError:
        # ONLY this statement maps IntegrityError to a workflow refusal; from
        # anywhere else a constraint violation is `store_unavailable` (§10.4).
        raise _refuse("workflow_exists", "/work_spec_sha256") from None
    except sqlite3.Error:
        raise WorkflowStoreError("store_unavailable") from None


def _insert_command(conn, workflow_row_id, decision_events, verb, command_id,
                    command_sha256, expected_revision, resulting_revision,
                    created_at) -> None:
    """C8/A7, then the §5.8 hash finalization inside the same transaction."""
    cursor = _execute(
        conn,
        _SQL_INSERT_COMMAND,
        (
            workflow_row_id,
            command_id,
            verb,
            command_sha256,
            expected_revision,
            resulting_revision,
            decision_events[0]["seq"],
            decision_events[-1]["seq"],
            created_at,
            _PENDING_HASH,
        ),
    )
    _finalize(conn, _SQL_FINALIZE_COMMAND, _SQL_SELECT_COMMAND_ROW, cursor.lastrowid, _command_row_payload)


def _insert_events(conn, workflow_row_id, records) -> None:
    """C9/A8: one row per decision event, in `seq` order. `content_sha256` is
    the EVENT RECORD digest the reducer sealed, written verbatim."""
    for record in records:
        _execute(
            conn,
            _SQL_INSERT_EVENT,
            (
                workflow_row_id,
                record["seq"],
                record["event"],
                record["from_state"],
                record["to_state"],
                record["revision"],
                record["policy_version"],
                record["command_id"],
                record["command_sha256"],
                record["actor"],
                _serialize(record["payload"]),
                record["created_at"],
                record[protocols.CONTENT_HASH_FIELD],
            ),
        )


def _insert_intent(conn, workflow_row_id, intent, created_at) -> None:
    """C10: `decision.intent`, inserted ONCE, as `outstanding` (§10.5)."""
    cursor = _execute(
        conn,
        _SQL_INSERT_INTENT,
        (
            workflow_row_id,
            intent["intent_id"],
            intent["intent_kind"],
            intent["idempotency_key"],
            intent["queue_route"],
            _serialize(intent),
            "outstanding",
            None,
            created_at,
            _PENDING_HASH,
        ),
    )
    _finalize(conn, _SQL_FINALIZE_INTENT, _SQL_SELECT_INTENT_ROW, cursor.lastrowid, _intent_row_payload)


def _resolve_intent(conn, records) -> None:
    """C11: close the intents the EMITTED EVENT PAYLOADS name (§10.5).

    Never by diffing snapshots, and never the intent C10 just inserted. Each
    close is itself a compare-and-swap with a required rowcount of 1, so a
    second close is impossible and no reverse transition exists.
    """
    for record in records:
        name = record["event"]
        payload = record["payload"]
        if name == "dispatch_revoked":
            _close_intent(conn, payload.get("intent_id"), "revoked", None)
        elif name in ("dispatch_accepted", "dispatch_rejected"):
            _close_intent(
                conn, payload.get("intent_id"), "resolved",
                payload.get("receipt_id"),
            )
        elif name == "workflow_cancelled" and "intent_id" in payload:
            _close_intent(
                conn, payload.get("intent_id"), "resolved",
                payload.get("receipt_id"),
            )


def _close_intent(conn, intent_id, status, receipt_id) -> None:
    row = _fetchone(conn, _SQL_SELECT_INTENT, (intent_id,))
    if row is None:
        # The intent an emitted event names must exist and be outstanding, so
        # anything else is a damaged outbox, not a caller error (§12.2).
        raise WorkflowStoreError("store_unavailable")
    try:
        payload = _intent_row_payload(row)
    except _RowUnreadable:
        raise WorkflowStoreError("store_unavailable") from None
    payload["status_sha256"] = _leaf(status)
    payload["resolved_receipt_id_sha256"] = (
        None if receipt_id is None else _leaf(receipt_id)
    )
    cursor = _execute(
        conn,
        _SQL_CLOSE_INTENT,
        (status, receipt_id, _row_digest(payload), intent_id),
    )
    if cursor.rowcount != 1:
        raise WorkflowStoreError("store_unavailable")


def _insert_receipt(conn, workflow_row_id, document, receipt_sha256,
                    created_at) -> None:
    """C12: `intent_id` and `runtime_task_uuid` PROJECTED from the document,
    `document` verbatim, `receipt_sha256` RECOMPUTED (§11.4)."""
    cursor = _execute(
        conn,
        _SQL_INSERT_RECEIPT,
        (
            workflow_row_id,
            document["receipt_id"],
            document["receipt_kind"],
            document.get("intent_id"),
            document.get("runtime_task_uuid"),
            _serialize(document),
            receipt_sha256,
            created_at,
            _PENDING_HASH,
        ),
    )
    _finalize(conn, _SQL_FINALIZE_RECEIPT, _SQL_SELECT_RECEIPT_ROW, cursor.lastrowid, _receipt_row_payload)


def _insert_fact(conn, workflow_row_id, kind, scope, document,
                 created_at) -> None:
    """C13: `ON CONFLICT DO NOTHING`, then finalize the hash WHEN a row was
    inserted. An exact duplicate is a no-op while the command that carried it
    still appends its event and consumes its revision (§5.6)."""
    cursor = _execute(
        conn,
        _SQL_INSERT_FACT,
        (
            workflow_row_id,
            kind,
            scope,
            _serialize(document),
            protocols.content_digest(document),
            created_at,
            _PENDING_HASH,
        ),
    )
    if cursor.rowcount != 1:
        return
    _finalize(conn, _SQL_FINALIZE_FACT, _SQL_SELECT_FACT_ROW,
              cursor.lastrowid, _fact_row_payload)


def _cas_snapshot(conn, workflow_row_id, snapshot, expected_revision,
                  created_at) -> None:
    """C14. Under `BEGIN IMMEDIATE` a rowcount of 0 is unreachable from
    concurrency: it means the row was deleted or its revision changed outside
    any code path this repository contains. `revision_mismatch` is the honest
    code — the storage gate disagreed with the semantic gate (§12.2)."""
    cursor = _execute(
        conn,
        _SQL_CAS_WORKFLOW,
        (
            snapshot["state"],
            snapshot["revision"],
            snapshot["dispatch_intent_id"],
            snapshot["cancel_intent_id"],
            snapshot["runtime_task_uuid"],
            snapshot["queue_route"],
            snapshot["policy_version"],
            created_at,
            snapshot[protocols.CONTENT_HASH_FIELD],
            workflow_row_id,
            expected_revision,
        ),
    )
    if cursor.rowcount != 1:
        raise _refuse("revision_mismatch", "/expected_revision")


def _journal(conn, workflow_row_id, verb, actor, records) -> None:
    """C15/A9: ONE `events.emit` row per appended workflow event (§10.6).

    A two-event command writes two, because `action` IS the event name and one
    row would have to drop the other. Enums, validated identifiers, bounded
    integers and digests only — no free text, no document excerpt, no stored
    column value; `events.emit` adds `schema_version` and passes both the
    payload and the actor through `secretscan.redact_tree`.
    """
    workflow_id = _render(workflow_row_id)
    for record in records:
        try:
            events.emit(
                conn,
                actor=actor,
                entity="workflow",
                entity_id=workflow_row_id,
                action=record["event"],
                payload={
                    "workflow_id": workflow_id,
                    "seq": record["seq"],
                    "revision": record["revision"],
                    "policy_version": record["policy_version"],
                    "from_state": record["from_state"],
                    "to_state": record["to_state"],
                    "command": verb,
                    "command_id": record["command_id"],
                    "command_sha256": record["command_sha256"],
                    "event_sha256": record[protocols.CONTENT_HASH_FIELD],
                    "work_spec_sha256": record["work_spec_sha256"],
                },
            )
        except sqlite3.Error:
            raise WorkflowStoreError("store_unavailable") from None


_SQL_SELECT_COMMAND_ROW = (
    "SELECT id, workflow_id, command_id, command, command_sha256, "
    "expected_revision, resulting_revision, event_seq_first, event_seq_last, "
    f"created_at, content_sha256 FROM {db.WORKFLOW_COMMANDS_TABLE} WHERE id = ?"
)
_SQL_SELECT_INTENT_ROW = (
    f"SELECT {_INTENT_COLUMNS} FROM {db.WORKFLOW_INTENTS_TABLE} WHERE id = ?"
)
_SQL_SELECT_RECEIPT_ROW = (
    f"SELECT {_RECEIPT_COLUMNS} FROM {db.WORKFLOW_RECEIPTS_TABLE} WHERE id = ?"
)
_SQL_SELECT_FACT_ROW = (
    f"SELECT {_FACT_COLUMNS} FROM {db.WORKFLOW_FACTS_TABLE} WHERE id = ?"
)


# ---------------------------------------------------------------------------
# `submit` (§10, §11)

def _outcome_accepted(workflow_id, command_id, revision, records, intent,
                      snapshot) -> StoreOutcome:
    return StoreOutcome(
        status="accepted",
        replay=False,
        workflow_id=workflow_id,
        command_id=command_id,
        revision=revision,
        events=tuple(_fresh(record) for record in records),
        intent=None if intent is None else _fresh(intent),
        snapshot=None if snapshot is None else _fresh(snapshot),
        reason=None,
        where=None,
        diagnostics={},
        refusal=None,
    )


def _outcome_refused(refusal, workflow_id, command_id, revision,
                     snapshot) -> StoreOutcome:
    conflict = refusal.reason in ("command_conflict", "receipt_conflict")
    return StoreOutcome(
        status="conflict" if conflict else "refused",
        replay=False,
        workflow_id=workflow_id,
        command_id=command_id,
        revision=revision,
        events=(),
        intent=None,
        snapshot=None if snapshot is None else _fresh(snapshot),
        reason=refusal.reason,
        where=refusal.where or None,
        diagnostics=_safe_diagnostics(refusal.diagnostics),
        refusal=refusal,
    )


def _outcome_replay(workflow_id, command_id, revision, records,
                    snapshot) -> StoreOutcome:
    return StoreOutcome(
        status="replay",
        replay=True,
        workflow_id=workflow_id,
        command_id=command_id,
        revision=revision,
        events=tuple(_fresh(record) for record in records),
        intent=None,
        snapshot=None if snapshot is None else _fresh(snapshot),
        reason=None,
        where=None,
        diagnostics={},
        refusal=None,
    )


def _verified_range(conn, workflow_row_id, first, last):
    """The original events of an accepted command, RE-VERIFIED before replay.

    §18.1 recomputes every digest from the stored bytes at every use, and
    §15.3 refuses a mutating command on a workflow that fails verification. A
    replay is a mutating command's ANSWER, so it is held to the SAME gate a
    fresh command is held to — the whole §7.2 gate, not the history alone
    (U-W2 A2 §A2.5, U-W2.2 B1 §B1.8).

    Verifying the history alone is not enough: an intact history with a
    tampered projection refuses a fresh command with `snapshot_divergence`,
    and a replay that skipped step 6 would still answer from it. This runs at
    C2/C3, before `_load_snapshot`, which is exactly why it repeats the gate
    rather than relying on it.
    """
    row = _fetchone(conn, _SQL_SELECT_WORKFLOW, (workflow_row_id,))
    if row is None:
        raise _refuse("workflow_unknown", "/workflow_id")
    snapshot, refusal, _seq, records = _rebuild_snapshot(conn, row)
    if refusal is not None:
        raise _Refused(refusal)
    verdict = workflow_engine.verify_history(records)
    if verdict is not None:
        raise _Refused(verdict)
    divergent = _divergent_fields(row, snapshot, records)
    if divergent:
        raise _refuse("snapshot_divergence", f"/{divergent[0]}")
    return tuple(r for r in records if first <= r["seq"] <= last)


def _command_dedupe(conn, command_id, command_sha256, workflow_row_id):
    """C2/C3 and A2 (§14.2). Digest equal and same workflow -> REPLAY;
    digest different, or a different workflow -> `command_conflict`."""
    row = _fetchone(conn, _SQL_SELECT_COMMAND, (command_id,))
    if row is None:
        return
    stored_workflow_id, _verb, stored_digest, resulting_revision, first, last = row
    if stored_digest != command_sha256 or (
        workflow_row_id is not None and stored_workflow_id != workflow_row_id
    ):
        raise _refuse("command_conflict", "/command_id")
    raise _Replay(
        workflow_id=_render(stored_workflow_id),
        row_id=stored_workflow_id,
        revision=resulting_revision,
        events=_verified_range(conn, stored_workflow_id, first, last),
    )


def _receipt_dedupe(conn, workflow_row_id, work_spec_sha256, identity):
    """R1 (§11.2), and the ordering is load-bearing: a redelivered `accepted`
    receipt arrives when the workflow has already moved on, so handing it to
    the reducer would produce `receipt_out_of_order` for a receipt that was in
    fact applied. Dedupe first turns it into the accepted no-op."""
    receipt_id, receipt_sha256, _document = identity
    row = _fetchone(conn, _SQL_SELECT_RECEIPT, (receipt_id,))
    if row is None:
        return
    stored_workflow_id, stored_digest = row[0], row[1]
    if stored_digest != receipt_sha256 or stored_workflow_id != workflow_row_id:
        raise _refuse("receipt_conflict", "/receipt_id")
    records, refusal, _seq = _read_history(
        conn, workflow_row_id, work_spec_sha256
    )
    if refusal is not None:
        raise _Refused(refusal)
    verdict = workflow_engine.verify_history(records)
    if verdict is not None:
        raise _Refused(verdict)
    for record in records:
        if record["payload"].get("receipt_id") != receipt_id:
            continue
        command_id = record["command_id"]
        group = tuple(r for r in records if r["command_id"] == command_id)
        raise _Replay(
            workflow_id=_render(workflow_row_id),
            row_id=workflow_row_id,
            revision=record["revision"],
            events=group,
        )
    # A stored receipt is an APPLIED receipt (§5.5), so a row with no event
    # naming it is a damaged inbox rather than a caller error.
    raise WorkflowStoreError("store_unavailable")


def _admission_facts(conn, payload):
    """A3. A payload that is not a well-shaped object yields
    `AdmissionFacts(False, False)` and lets `decide` refuse with its own
    precise code — the store never refuses admission on its own (§9.5)."""
    empty = workflow_engine.AdmissionFacts(False, False)
    if not isinstance(payload, dict):
        return empty
    document = payload.get("work_spec_document")
    if not isinstance(document, dict):
        return empty
    task_text = document.get("aos_task_id")
    if not isinstance(task_text, str) or not _AOS_TASK_ID_RE.fullmatch(
        task_text
    ):
        return empty
    try:
        task_id = ids.parse_id(task_text, "task")
    except AosError:
        return empty
    row = _fetchone(conn, _SQL_TASK_STATUS, (task_id,))
    if row is None:
        return empty
    status = row[0]
    if not isinstance(status, str):
        return empty
    return workflow_engine.AdmissionFacts(True, status != _TASK_CLOSED_STATUS)


def _decide(snapshot, command, facts):
    try:
        return workflow_engine.decide(snapshot, command, facts)
    except workflow_engine.WorkflowRefusal as refusal:
        raise _Refused(refusal) from None


def submit(conn, command_document) -> StoreOutcome:
    """One accepted command is one `BEGIN IMMEDIATE` transaction (§10).

    Returns a `StoreOutcome` for every workflow-level outcome and never raises
    `WorkflowRefusal`; it raises only `WorkflowStoreError` for the three
    infrastructure codes of §8.4.
    """
    _require_schema(conn)                                            # P1
    try:
        fresh, verb, command_id, workflow_id, command_sha256 = (
            _command_identity(command_document)                      # P2
        )
    except _Refused as refused:
        return _outcome_refused(
            refused.refusal, refused.workflow_id, refused.command_id,
            None, None,
        )

    workflow_row_id = None
    if workflow_id is not None:
        try:
            workflow_row_id = ids.parse_id(workflow_id, "workflow")
        except AosError:
            return _outcome_refused(
                _refusal("command_malformed", "/workflow_id"),
                workflow_id, command_id, None, None,
            )

    try:
        with db.transaction(conn):
            conn.execute("BEGIN IMMEDIATE")                          # C1 / A1
            if verb == "admit_work_spec":
                result = _submit_admission(
                    conn, fresh, command_id, command_sha256
                )
            else:
                result = _submit_command(
                    conn, fresh, verb, command_id, workflow_row_id,
                    command_sha256,
                )
    except _Replay as replay:
        _revision, snapshot = _current_view(conn, replay.row_id)
        return _outcome_replay(
            replay.workflow_id, command_id, replay.revision, replay.events,
            snapshot,
        )
    except _Refused as refused:
        revision = snapshot = None
        if workflow_row_id is not None:
            revision, snapshot = _current_view(conn, workflow_row_id)
        return _outcome_refused(
            refused.refusal, workflow_id, command_id, revision, snapshot,
        )
    except sqlite3.Error:
        raise WorkflowStoreError("store_unavailable") from None
    return result


def _submit_admission(conn, command, command_id, command_sha256):
    """A2-A10 (§10.4). `admit_work_spec` carries no `workflow_id` and has no
    row to update, so its order differs and is frozen separately."""
    _command_dedupe(conn, command_id, command_sha256, None)          # A2
    facts = _admission_facts(conn, command.get("payload"))           # A3
    decision = _decide(None, command, facts)                         # A4
    snapshot = decision.snapshot_after
    row_id = ids.parse_id(snapshot["workflow_id"], "workflow")
    task_id = ids.parse_id(snapshot["task_id"], "task")
    if _fetchone(                                                    # A5
        conn, _SQL_WORKFLOW_EXISTS, (row_id, snapshot["work_spec_sha256"])
    ) is not None:
        raise _refuse("workflow_exists", "/work_spec_sha256")
    created_at = command["created_at"]
    _insert_workflow(conn, snapshot, row_id, task_id, created_at)    # A6
    _insert_command(                                                 # A7
        conn, row_id, decision.events, "admit_work_spec", command_id,
        command_sha256, command["expected_revision"], snapshot["revision"],
        created_at,
    )
    _insert_events(conn, row_id, decision.events)                    # A8
    _journal(conn, row_id, "admit_work_spec", command["actor"],
             decision.events)                                        # A9
    return _outcome_accepted(                                        # A10
        snapshot["workflow_id"], command_id, snapshot["revision"],
        decision.events, decision.intent, snapshot,
    )


def _submit_command(conn, command, verb, command_id, workflow_row_id,
                    command_sha256):
    """C2-C16 (§10.3), in exactly the frozen order."""
    _command_dedupe(conn, command_id, command_sha256, workflow_row_id)  # C2/C3
    row, snapshot = _load_snapshot(conn, workflow_row_id)               # C4
    payload = command.get("payload")
    receipt = None
    if verb == "record_queue_receipt":                                  # R1
        receipt = _receipt_identity(payload)
        if receipt is not None:
            _receipt_dedupe(conn, workflow_row_id, row[2], receipt)
    # C5 is deliberately absent: semantic revision validation is the
    # reducer's, inside C7; the storage gate is the C14 CAS.
    decision = _decide(snapshot, command, workflow_engine.AdmissionFacts())  # C7
    after = decision.snapshot_after
    created_at = command["created_at"]
    _insert_command(                                                    # C8
        conn, workflow_row_id, decision.events, verb, command_id,
        command_sha256, command["expected_revision"], after["revision"],
        created_at,
    )
    _insert_events(conn, workflow_row_id, decision.events)              # C9
    if decision.intent is not None:                                     # C10
        _insert_intent(conn, workflow_row_id, decision.intent, created_at)
    _resolve_intent(conn, decision.events)                              # C11
    if receipt is not None:                                             # C12
        _insert_receipt(
            conn, workflow_row_id, receipt[2], receipt[1], created_at
        )
    _insert_fact_for(conn, workflow_row_id, verb, payload, created_at)  # C13
    _cas_snapshot(                                                      # C14
        conn, workflow_row_id, after, command["expected_revision"], created_at
    )
    _journal(conn, workflow_row_id, verb, command["actor"], decision.events)
    return _outcome_accepted(                                           # C16
        after["workflow_id"], command_id, after["revision"], decision.events,
        decision.intent, after,
    )


def _insert_fact_for(conn, workflow_row_id, verb, payload, created_at) -> None:
    """C13: `fact_kind` is `approval` for an accepted `record_approval` and
    `result` for an accepted `record_result`; `fact_scope` is the approval
    document's own `scope` and NULL for a result (§16.1)."""
    if not isinstance(payload, dict):
        return
    if verb == "record_approval":
        document = payload.get("approval_document")
        if isinstance(document, dict):
            _insert_fact(
                conn, workflow_row_id, "approval", document.get("scope"),
                document, created_at,
            )
    elif verb == "record_result":
        document = payload.get("result_document")
        if isinstance(document, dict):
            _insert_fact(
                conn, workflow_row_id, "result", None, document, created_at
            )


# ---------------------------------------------------------------------------
# Read paths (§8.3, §15.3). Total on a damaged workflow; they open no
# transaction and issue no write.

def _record_from_row(row, integrity: str) -> WorkflowRecord:
    return WorkflowRecord(
        workflow_id=_render(row[0]),
        id=row[0],
        task_id=row[1],
        state=row[9],
        revision=row[10],
        policy_version=row[11],
        compile_status=row[6],
        approval_required=bool(row[12]),
        work_spec_sha256=row[2],
        report_sha256=row[3],
        snapshot_sha256=row[4],
        registry_version=row[5],
        dispatch_intent_id=row[13],
        cancel_intent_id=row[14],
        runtime_task_uuid=row[15],
        queue_route=row[16],
        created_at=row[17],
        updated_at=row[18],
        content_sha256=row[19],
        integrity=integrity,
    )


def _integrity_of(conn, row) -> str:
    snapshot, refusal, _seq, records = _rebuild_snapshot(conn, row)
    if refusal is not None:
        return refusal.reason
    divergent = _divergent_fields(row, snapshot, records)
    return "snapshot_divergence" if divergent else "ok"


def read_workflow(conn, workflow_id) -> WorkflowRecord | None:
    """The projection plus an integrity verdict; `None` iff no such row."""
    _require_schema(conn)
    row_id = _require_workflow_id(workflow_id)
    row = _fetchone(conn, _SQL_SELECT_WORKFLOW, (row_id,))
    if row is None:
        return None
    return _record_from_row(row, _integrity_of(conn, row))


def list_workflows(conn, *, state=None) -> tuple:
    """A declared full scan ordered by `id` ASC (§8.3)."""
    _require_schema(conn)
    if state is not None and state not in workflow_engine.WORKFLOW_STATES:
        raise WorkflowStoreError("store_argument_invalid")
    out = []
    for row in _fetchall(conn, _SQL_SELECT_WORKFLOWS):
        if state is not None and row[9] != state:
            continue
        out.append(_record_from_row(row, _integrity_of(conn, row)))
    return tuple(out)


def read_history(conn, workflow_id) -> HistoryView:
    """Reconstituted records in `seq` order, plus the integrity verdict and
    the first unreadable `seq`.

    A nonexistent workflow returns `(events=(), integrity="ok",
    unreadable_seq=None)`; an existing workflow with zero stored event rows
    reports `history_corrupt` (the engine refuses an empty history), which
    keeps the pair unambiguous and total (§8.3).
    """
    _require_schema(conn)
    row_id = _require_workflow_id(workflow_id)
    identity = _render(row_id)
    row = _fetchone(conn, _SQL_SELECT_WORKFLOW, (row_id,))
    if row is None:
        return HistoryView(identity, (), "ok", None)
    try:
        work_spec_sha256 = _req_text(row[2], "/work_spec_sha256")
    except _RowUnreadable:
        return HistoryView(identity, (), "history_corrupt", None)
    records, refusal, unreadable_seq = _read_history(
        conn, row_id, work_spec_sha256
    )
    if refusal is not None:
        return HistoryView(
            identity, tuple(_fresh(r) for r in records), refusal.reason,
            unreadable_seq,
        )
    verdict = workflow_engine.verify_history(records)
    return HistoryView(
        identity,
        tuple(_fresh(r) for r in records),
        "ok" if verdict is None else verdict.reason,
        None,
    )


def _intent_view(row) -> IntentView:
    """One outbox row. An unreadable row is REPORTED, never dropped (§8.3)."""
    identity = _render(row[1]) if isinstance(row[1], int) else ""
    try:
        document = _parse_stored(row[6], "/document")
    except _RowUnreadable:
        document = None
    readable = document is not None
    if readable:
        # `intent_id`, `intent_kind`, `idempotency_key` and `queue_route` are
        # PROJECTIONS of `document`, cross-checked on read (§5.4).
        for column, member in (
            (row[2], "intent_id"),
            (row[3], "intent_kind"),
            (row[4], "idempotency_key"),
            (row[5], "queue_route"),
        ):
            if document.get(member) != column:
                readable = False
                document = None
                break
    return IntentView(
        workflow_id=identity,
        intent_id=row[2],
        intent_kind=row[3],
        idempotency_key=row[4],
        queue_route=row[5],
        status=row[7],
        resolved_receipt_id=row[8],
        created_at=row[9],
        document=None if document is None else _fresh(document),
        content_sha256=row[10],
        readable=readable,
    )


def list_outstanding_intents(conn, *, workflow_id=None) -> tuple:
    """`status = 'outstanding'`, ordered by `id` ASC — insertion order, which
    within a workflow is exactly `intent_seq` order and across workflows is
    emission order. It never sorts by a document field, never dedupes, never
    batches, and never marks anything delivered (§16.2)."""
    _require_schema(conn)
    if workflow_id is None:
        rows = _fetchall(conn, _SQL_SELECT_OUTSTANDING)
    else:
        row_id = _require_workflow_id(workflow_id)
        rows = _fetchall(conn, _SQL_SELECT_OUTSTANDING_FOR, (row_id,))
    return tuple(_intent_view(row) for row in rows)


def rebuild(conn, workflow_id) -> RebuildResult:
    """`fold` + splice + seal, WITHOUT comparing against the projection."""
    _require_schema(conn)
    row_id = _require_workflow_id(workflow_id)
    identity = _render(row_id)
    row = _fetchone(conn, _SQL_SELECT_WORKFLOW, (row_id,))
    if row is None:
        return RebuildResult(
            identity, None, "history_corrupt", "workflow_unknown",
            "/workflow_id",
        )
    snapshot, refusal, _seq, _records = _rebuild_snapshot(conn, row)
    if refusal is not None:
        return RebuildResult(
            identity, None, refusal.reason, refusal.reason,
            refusal.where or None,
        )
    return RebuildResult(identity, _fresh(snapshot), "ok", None, None)


#: `(table, SELECT, document index, digest index)` — the two tables whose
#: stored DOCUMENT is bound by a digest COLUMN rather than by the row hash.
#: §5.8 binds `receipt_sha256` and `document_sha256` by their leaves, so a
#: forged body with an untouched digest column recomputes its row hash
#: perfectly; §18.1 nevertheless promises both are "recomputed from the stored
#: bytes at every use". That promise is kept here.
_DOCUMENT_BOUND_TABLES = (
    (db.WORKFLOW_RECEIPTS_TABLE, _SQL_SELECT_RECEIPT_ROWS, 6, 7),
    (db.WORKFLOW_FACTS_TABLE, _SQL_SELECT_FACT_ROWS, 4, 5),
)


def _divergent_rows(conn, workflow_row_id) -> tuple:
    """§15.4 step 4: recompute all four §5.8 row hashes, and re-digest the two
    stored documents their row hashes bind only by column (§18.1), without
    touching a row. Anything that does not recompute is `(table, row_id)`."""
    divergent = []
    for table, sql, payload_of, hash_index in _ROW_HASH_TABLES:
        for row in _fetchall(conn, sql, (workflow_row_id,)):
            try:
                digest = _row_digest(payload_of(row))
            except (_RowUnreadable, protocols.ProtocolError):
                divergent.append((table, row[0]))
                continue
            if digest != row[hash_index]:
                divergent.append((table, row[0]))
    seen = {pair for pair in divergent}
    for table, sql, document_index, digest_index in _DOCUMENT_BOUND_TABLES:
        for row in _fetchall(conn, sql, (workflow_row_id,)):
            if (table, row[0]) in seen:
                continue
            try:
                document = _parse_stored(row[document_index], "/document")
                recomputed = protocols.content_digest(document)
            except (_RowUnreadable, protocols.ProtocolError):
                divergent.append((table, row[0]))
                continue
            if recomputed != row[digest_index]:
                divergent.append((table, row[0]))
    return tuple(divergent)


def _verify_one(conn, row) -> VerifyReport:
    identity = _render(row[0])
    stored = row[19] if isinstance(row[19], str) else ""
    try:
        work_spec_sha256 = _req_text(row[2], "/work_spec_sha256")
    except _RowUnreadable:
        return VerifyReport(
            identity, "snapshot_divergence", "snapshot_divergence",
            "/work_spec_sha256", stored, None, ("work_spec_sha256",),
            _divergent_rows(conn, row[0]), None, None,
        )
    records, refusal, _seq = _read_history(conn, row[0], work_spec_sha256)
    rows = _divergent_rows(conn, row[0])
    revision = row[10] if isinstance(row[10], int) else None
    last_seq = records[-1]["seq"] if records else None
    if refusal is not None:
        return VerifyReport(
            identity, refusal.reason, refusal.reason, refusal.where or None,
            stored, None, (), rows, last_seq, revision,
        )
    folded, refusal = _fold(records)
    if refusal is not None:
        return VerifyReport(
            identity, refusal.reason, refusal.reason, refusal.where or None,
            stored, None, (), rows, last_seq, revision,
        )
    snapshot, rebuild_refusal, _unused, _recs = _rebuild_snapshot(conn, row)
    if rebuild_refusal is not None:
        return VerifyReport(
            identity, rebuild_refusal.reason, rebuild_refusal.reason,
            rebuild_refusal.where or None, stored,
            None, _body_divergence(row, records), rows, last_seq, revision,
        )
    fields = _divergent_fields(row, snapshot, records)
    rebuilt = snapshot[protocols.CONTENT_HASH_FIELD]
    integrity = "ok" if not fields and not rows else "snapshot_divergence"
    return VerifyReport(
        identity,
        integrity,
        None if integrity == "ok" else "snapshot_divergence",
        None if integrity == "ok" else f"/{fields[0]}" if fields else "/rows",
        stored,
        rebuilt,
        fields,
        rows,
        last_seq,
        revision,
    )


def verify(conn, workflow_id=None) -> tuple:
    """Rebuild each workflow, compare, and report — writing NOTHING, ever.

    Issues no `INSERT`, `UPDATE`, `DELETE` or `events.emit`, and opens no
    transaction (§20 row S16). One report per workflow, ordered by
    `workflows.id`.
    """
    _require_schema(conn)
    if workflow_id is None:
        row_ids = [row[0] for row in _fetchall(conn, _SQL_SELECT_WORKFLOW_IDS)]
    else:
        row_ids = [_require_workflow_id(workflow_id)]
    reports = []
    for row_id in row_ids:
        row = _fetchone(conn, _SQL_SELECT_WORKFLOW, (row_id,))
        if row is None:
            continue
        reports.append(_verify_one(conn, row))
    return tuple(reports)
