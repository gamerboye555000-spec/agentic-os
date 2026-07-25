"""U-W2.1 pure deterministic workflow state engine.

Contract: agentic-os-v0.4-u-w2-workflow-state-engine-contract.md

Everything here is PURE. `decide(snapshot, command, facts)` maps a typed
snapshot, a validated command record, and the two shell-verified ledger facts
to a fresh snapshot, one or more append-only events, and at most one queue
intent. It reads no clock, no filesystem, no network, no database, no queue,
no environment, no locale, and no randomness; it executes nothing, retries
nothing, compensates nothing, and grants nothing (D-v0.4.74). Identical
inputs yield byte-identical decisions on every platform.

Import discipline (contract §9, enforced by the §19 row-14 AST test): this
module imports `protocols`, `workspecs` (the public acceptance seam),
`secretscan`, `utils.AosError`, `dataclasses`, `hashlib`, and `re` — and
nothing else. `datetime` stays out, so the real-instant check is pure
calendar arithmetic (the U-W1 rule), and the UUIDv8 construction of §13.1 is
re-implemented locally because `workspecs._uuid8_from_digest` is private and
§0.1 adds no third public wrapper; a §19 test pins the copy byte-equal.

Four readings the contract states in more than one place, resolved here once
and pinned by test:

- **Terminal immutability is about mutation, not about one code.** Terminal
  rows accept no command (§5.2, §5.3, §19 row 2) and refuse
  `workflow_terminal` — except for the case §13.3 names twice and §19 row 12
  freezes: a late receipt for an intent this workflow REVOKED refuses
  `receipt_superseded`, which is the signal that tells an operator the queue
  committed a row they revoked. Both codes mutate nothing, so both readings
  hold (`_refuse_on_terminal`).
- **Receipts spell illegality `receipt_out_of_order`.** §19 row 2 names
  `illegal_transition`/`workflow_terminal` for state-changing drivers, while
  §13.3 and §19 row 7 make refusal-then-redeliver the receipt ordering
  protocol. Command and result drivers therefore refuse `illegal_transition`;
  receipts refuse `receipt_out_of_order`.
- **`record_result` is state-gated, not matrix-scanned.** §6 makes it legal
  in `running` only, and §5.2 names the `failed` receipt as the one
  attemptable reserved edge, so `transition_reserved` is reachable through
  that receipt alone.
- **The workflow identity is derived, not supplied.** §9 freezes `facts` as
  the two ledger booleans and passes `None` for the snapshot on admission,
  §6 forbids `workflow_id` on that envelope, and §7 requires it on every
  event — so `_workflow_identity` derives it from the admitted digest using
  §13.1's domain-separated idiom. U-W2.2 therefore takes the `workflows` row
  id from `snapshot_after["workflow_id"]` instead of allocating a sequence;
  `ids.py` still registers the `WF` prefix so §16's CLI can parse a typed id.

Integrity the reducer re-establishes on every call, because the `workflows`
row is untrusted input like any other document (§3, §11, §14.2): both stored
bodies are re-digested against their columns, the identity is re-derived, the
pending intent pointers are re-derived, and every counter and bounded
collection is checked against the frozen canonical limits. That is what keeps
the reducer's later reads total — a body that re-digests is byte-identical to
the one admission spine-validated — and what keeps a raw spine error out of
`_seal`.

Store-side by construction (§9, §10): `command_conflict`, `receipt_conflict`,
and `workflow_unknown` need stored rows to detect, so the vocabulary declares
them here and `workflow_store` (U-W2.2) raises them. `decide` still fails
closed with `workflow_unknown` when it is handed no snapshot at all.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from . import protocols, secretscan, workspecs
from .utils import AosError

# ---------------------------------------------------------------------------
# Closed vocabularies (contract §5-§8, §13). Tuples, frozen at import.

#: The record schemas minted by this unit (§13.4). Internal canonical records
#: in the `aos.*` house style, deliberately not U-X1 registry artifacts.
WORKFLOW_COMMAND_SCHEMA = "aos.workflow-command/v1"
WORKFLOW_EVENT_SCHEMA = "aos.workflow-event/v1"
WORKFLOW_SNAPSHOT_SCHEMA = "aos.workflow-snapshot/v1"
WORKFLOW_INTENT_SCHEMA = "aos.workflow-queue-intent/v1"
WORKFLOW_RECEIPT_SCHEMA = "aos.workflow-queue-receipt/v1"
WORKFLOW_APPROVAL_FACT_SCHEMA = "aos.workflow-approval-fact/v1"

#: Thirteen authoritative states (§5.1). `proposed` is the pre-compile
#: authoring plane and is never a workflow state.
WORKFLOW_STATES = (
    "compiled", "validated", "awaiting_approval", "scheduled", "running",
    "waiting_input", "waiting_approval", "paused", "compensating",
    "succeeded", "failed", "cancelled", "compensated",
)

#: Immutable: no legal edge leaves these rows, and no command is considered.
TERMINAL_STATES = ("succeeded", "failed", "cancelled", "compensated")

#: The states a two-phase cancellation applies to (§5.3): AOS has observed
#: queue acceptance, so the runtime is the source of truth for execution.
_POST_DISPATCH_STATES = (
    "scheduled", "running", "waiting_input", "waiting_approval", "paused",
)

WORKFLOW_COMMANDS = (
    "admit_work_spec", "validate", "request_approval", "record_approval",
    "request_dispatch", "revoke_dispatch", "request_cancel",
    "record_queue_receipt", "record_result",
)

#: The transport origin of a command (§6).
COMMAND_SOURCES = ("cli", "runtime_adapter")

WORKFLOW_EVENTS = (
    "workflow_admitted", "workflow_validated",
    "approval_requested", "approval_recorded",
    "dispatch_requested", "dispatch_rejected", "dispatch_revoked",
    "dispatch_accepted",
    "run_started", "run_waiting_input", "run_waiting_approval",
    "run_paused", "run_resumed",
    "cancel_requested",
    "workflow_succeeded", "workflow_failed", "workflow_cancelled",
)

#: Forty-three codes in canonical emission order (the GOVERNANCE_REASON_CODES
#: idiom). A refusal mutates nothing, appends no event, consumes no revision.
WORKFLOW_REFUSAL_REASONS = (
    # envelope / shape
    "command_malformed", "command_unknown", "command_schema_unsupported",
    "payload_malformed",
    # identity / order / dedupe
    "workflow_unknown", "workflow_exists", "workflow_terminal",
    "revision_mismatch", "command_conflict", "illegal_transition",
    "transition_reserved", "policy_version_unsupported",
    # admission
    "admission_artifact_invalid", "admission_report_malformed",
    "admission_report_unbound", "admission_status_blocking",
    "admission_registry_mismatch", "admission_task_unknown",
    "admission_task_closed",
    # approval
    "approval_not_required", "approval_already_satisfied",
    "approval_pending", "approval_fact_malformed", "approval_fact_unbound",
    "approval_fact_missing",
    # dispatch / receipts
    "dispatch_already_pending", "dispatch_not_pending",
    "cancel_already_pending", "receipt_malformed", "receipt_unbound",
    "receipt_conflict", "receipt_out_of_order", "receipt_superseded",
    "runtime_uuid_mismatch",
    # results / evidence
    "result_malformed", "result_unbound", "result_inconsistent",
    "result_attempt_exceeded", "result_outcome_inconclusive",
    "evidence_insufficient",
    # history / rebuild
    "history_corrupt", "history_unknown_event", "snapshot_divergence",
)

WORKFLOW_INTENT_KINDS = ("dispatch", "cancel")

WORKFLOW_RECEIPT_KINDS = (
    "accepted", "rejected", "started", "waiting_input", "waiting_approval",
    "paused", "resumed", "cancelled", "failed",
)

#: Which wait an approval fact satisfies (§12.1).
APPROVAL_SCOPES = ("admission", "runtime")

#: Receipt kind -> event: the §7 bijection over the nine kinds.
RECEIPT_EVENTS = (
    ("accepted", "dispatch_accepted"),
    ("rejected", "dispatch_rejected"),
    ("started", "run_started"),
    ("waiting_input", "run_waiting_input"),
    ("waiting_approval", "run_waiting_approval"),
    ("paused", "run_paused"),
    ("resumed", "run_resumed"),
    ("cancelled", "workflow_cancelled"),
    ("failed", "workflow_failed"),
)

#: Receipt kind -> the state it targets (§7). `None` is the one stateless
#: kind, which traverses no matrix cell (§5.2).
RECEIPT_TARGET_STATES = (
    ("accepted", "scheduled"),
    ("rejected", None),
    ("started", "running"),
    ("waiting_input", "waiting_input"),
    ("waiting_approval", "waiting_approval"),
    ("paused", "paused"),
    ("resumed", "running"),
    ("cancelled", "cancelled"),
    ("failed", "failed"),
)

#: The §5.2 matrix IS version 1 (§15). U-W3 ships version 2.
TRANSITION_POLICY_VERSION = 1

#: Every shipped version replays forever; new decisions use the current one.
SUPPORTED_POLICY_VERSIONS = (1,)


def _build_matrix(cells) -> tuple:
    """The complete 13x13 table as data, row/column order = WORKFLOW_STATES.

    A cell is a tuple of the drivers that may traverse it: `()` is the
    contract's `·` (illegal) and `("reserved",)` is its `R` (defined, but
    refused under transition-policy v1). `"reserved"` is a classification,
    never a driver.
    """
    return tuple(
        tuple(cells.get((source, target), ()) for target in WORKFLOW_STATES)
        for source in WORKFLOW_STATES
    )


TRANSITION_MATRIX = _build_matrix({
    ("compiled", "validated"): ("cmd:validate",),
    ("compiled", "cancelled"): ("cmd:request_cancel",),
    ("validated", "awaiting_approval"): ("cmd:request_approval",),
    ("validated", "scheduled"): ("rcp:accepted",),
    ("validated", "cancelled"): ("cmd:request_cancel",),
    ("awaiting_approval", "validated"): ("apr:record_approval",),
    ("awaiting_approval", "cancelled"): ("cmd:request_cancel",),
    ("scheduled", "running"): ("rcp:started",),
    ("scheduled", "failed"): ("rcp:failed",),
    ("scheduled", "cancelled"): ("rcp:cancelled",),
    ("running", "waiting_input"): ("rcp:waiting_input",),
    ("running", "waiting_approval"): ("rcp:waiting_approval",),
    ("running", "paused"): ("rcp:paused",),
    ("running", "compensating"): ("reserved",),
    ("running", "succeeded"): ("res:success",),
    ("running", "failed"): ("res:fail", "rcp:failed"),
    ("running", "cancelled"): ("rcp:cancelled",),
    ("waiting_input", "running"): ("rcp:resumed",),
    ("waiting_input", "failed"): ("rcp:failed",),
    ("waiting_input", "cancelled"): ("rcp:cancelled",),
    ("waiting_approval", "running"): ("rcp:resumed",),
    ("waiting_approval", "failed"): ("rcp:failed",),
    ("waiting_approval", "cancelled"): ("rcp:cancelled",),
    ("paused", "running"): ("rcp:resumed",),
    ("paused", "failed"): ("rcp:failed",),
    ("paused", "cancelled"): ("rcp:cancelled",),
    ("compensating", "failed"): ("reserved",),
    ("compensating", "compensated"): ("reserved",),
})

#: Frozen per-version replay (§15): version 1's table is retained verbatim
#: when version 2 ships, so old history never re-derives under new rules.
_POLICY_MATRICES = ((1, TRANSITION_MATRIX),)

_RESERVED_CELL = ("reserved",)

#: Statuses that may create an instance (§11 gate 4); the other three are
#: blocking, so no blocking status can ever schedule.
_ADMISSIBLE_STATUSES = ("valid", "warning", "requires_external_authority")
_BLOCKING_STATUSES = ("invalid", "unresolved", "ineligible")


# ---------------------------------------------------------------------------
# Refusals (§8). One bounded, actionable, value-free line built from a closed
# code, a schema-safe path or already-validated identifier, and a fixed hint.

_REASON_HINTS = {
    "command_malformed": (
        "The command envelope does not match the frozen field table."
    ),
    "command_unknown": "That verb is not a workflow command.",
    "command_schema_unsupported": (
        "This build does not support that command record version."
    ),
    "payload_malformed": (
        "The payload does not match the closed shape this verb accepts."
    ),
    "workflow_unknown": "No workflow instance carries that identity.",
    "workflow_exists": (
        "A workflow instance already exists for that WorkSpec digest."
    ),
    "workflow_terminal": (
        "The workflow reached a terminal state; terminal states accept no "
        "command."
    ),
    "revision_mismatch": (
        "The expected revision does not match the instance; re-read and "
        "retry."
    ),
    "command_conflict": (
        "That command id was accepted with a different body."
    ),
    "illegal_transition": "That transition is not legal from this state.",
    "transition_reserved": (
        "That transition is reserved to a later transition-policy version."
    ),
    "policy_version_unsupported": (
        "This build does not support that transition-policy version."
    ),
    "admission_artifact_invalid": (
        "The WorkSpec artifact failed protocol admission."
    ),
    "admission_report_malformed": (
        "The compile report does not match the closed report shape."
    ),
    "admission_report_unbound": (
        "The compile report does not digest-bind this artifact."
    ),
    "admission_status_blocking": (
        "A blocking compile status cannot create a workflow instance."
    ),
    "admission_registry_mismatch": (
        "The report was compiled against a different protocol registry."
    ),
    "admission_task_unknown": (
        "The artifact names a task the ledger does not hold."
    ),
    "admission_task_closed": "The artifact names a closed task.",
    "approval_not_required": (
        "No approval of that scope is awaited in this state."
    ),
    "approval_already_satisfied": (
        "An approval fact of that scope is already on file."
    ),
    "approval_pending": (
        "Dispatch requires a recorded admission-scope approval fact."
    ),
    "approval_fact_malformed": (
        "The approval fact does not match its closed record shape."
    ),
    "approval_fact_unbound": (
        "The approval fact does not bind this workflow's declared authority."
    ),
    "approval_fact_missing": (
        "Resumption claims an approval no recorded fact carries."
    ),
    "dispatch_already_pending": "A dispatch intent is already outstanding.",
    "dispatch_not_pending": "No dispatch intent is outstanding.",
    "cancel_already_pending": "A cancellation is already outstanding.",
    "receipt_malformed": (
        "The queue receipt does not match its closed record shape."
    ),
    "receipt_unbound": (
        "The queue receipt does not bind this workflow or an outstanding "
        "intent."
    ),
    "receipt_conflict": (
        "That receipt id was recorded with a different body."
    ),
    "receipt_out_of_order": (
        "The queue receipt is not legal in this state; deliver its "
        "predecessors first."
    ),
    "receipt_superseded": (
        "The queue receipt names an intent that is no longer outstanding."
    ),
    "runtime_uuid_mismatch": (
        "The receipt names a different runtime task than this workflow "
        "carries."
    ),
    "result_malformed": (
        "The result envelope failed protocol validation."
    ),
    "result_unbound": (
        "The result envelope does not bind the admitted WorkSpec."
    ),
    "result_inconsistent": (
        "The result envelope contradicts itself."
    ),
    "result_attempt_exceeded": (
        "The reported attempt exceeds the artifact's declared budget."
    ),
    "result_outcome_inconclusive": (
        "An inconclusive outcome records nothing under this policy version."
    ),
    "evidence_insufficient": (
        "Counted evidence is below the artifact's declared minimum."
    ),
    "history_corrupt": (
        "The workflow history does not verify; nothing is rewritten."
    ),
    "history_unknown_event": "The history carries an unknown event name.",
    "snapshot_divergence": (
        "The snapshot does not match its closed record shape or digest."
    ),
}


class WorkflowRefusal(AosError):
    """A closed §8 refusal. Exits 1 through AosError.

    The message carries the code, a schema-safe path or already-validated
    identifier, and a fixed hint — never a field value, a document excerpt,
    or an exception's text. `diagnostics` holds bounded structured counts and
    closed codes for callers that want them; they never enter the message.
    An undeclared code is a KeyError programming failure, not a runtime path.
    """

    def __init__(self, reason: str, where: str = "", **diagnostics) -> None:
        if reason not in _REASON_HINTS:
            raise KeyError(f"undeclared workflow refusal reason: {reason!r}")
        self.reason = reason
        self.where = where
        self.diagnostics = dict(diagnostics)
        super().__init__(
            f"Refused workflow [{reason}] at {where or '/'}: "
            f"{_REASON_HINTS[reason]}"
        )


def _refuse(reason: str, where: str = "", **diagnostics) -> WorkflowRefusal:
    return WorkflowRefusal(reason, where, **diagnostics)


# ---------------------------------------------------------------------------
# Typed results (§9). Frozen dataclasses over fresh values.

@dataclass(frozen=True)
class AdmissionFacts:
    """The two ledger facts of §9 — the ONLY shell-verified inputs.

    Empty for every verb except `admit_work_spec`. The workflow identity is
    NOT a fact: it is derived from the admitted digest (`_workflow_identity`),
    which is what keeps this shape exactly the one §9 freezes.
    """

    task_exists: bool = False
    task_open: bool = False


@dataclass(frozen=True)
class WorkflowDecision:
    """One accepted command's whole effect: a fresh snapshot, the events it
    appends (at least one), and at most one queue intent."""

    snapshot_after: dict
    events: tuple
    intent: dict | None


# ---------------------------------------------------------------------------
# Pattern gates and canonical helpers. Matched with fullmatch so a trailing
# newline can never sneak through (D-v0.2.3).

_RFC3339_RE = re.compile(protocols.RFC3339_PATTERN, re.ASCII)
_UUID_RE = re.compile(protocols.UUID_PATTERN, re.ASCII)
_TRACE_ID_RE = re.compile(protocols.TRACE_ID_PATTERN, re.ASCII)
_SHA256_RE = re.compile(protocols.SHA256_PATTERN, re.ASCII)
_PROVENANCE_RE = re.compile(protocols.PROVENANCE_PATTERN, re.ASCII)
_OPAQUE_REF_RE = re.compile(protocols.OPAQUE_REF_PATTERN, re.ASCII)
_COMPONENT_ID_RE = re.compile(protocols.COMPONENT_ID_PATTERN, re.ASCII)
_IDEMPOTENCY_RE = re.compile(protocols.IDEMPOTENCY_KEY_PATTERN, re.ASCII)
_ERROR_CODE_RE = re.compile(protocols.ERROR_CODE_PATTERN, re.ASCII)
_AOS_TASK_ID_RE = re.compile(protocols.AOS_TASK_ID_PATTERN, re.ASCII)

#: The `WF-<n>` ledger identity (§6). `ids.py` renders it; nothing here mints
#: one, because a pure function cannot allocate a ledger sequence.
_WORKFLOW_ID_RE = re.compile(r"^WF-[0-9]{1,19}$", re.ASCII)

#: A schema-safe path: what U-W1 emits as a finding path. Bounded, and the
#: only report-derived string this unit copies into an event payload.
_SCHEMA_PATH_RE = re.compile(
    r"^/(?:[A-Za-z0-9_.-]{1,64}(?:/[A-Za-z0-9_.-]{1,64})*)?$", re.ASCII
)
_MAX_PATH_CHARS = 256

#: The admission event records at most this many finding pairs (§11).
_MAX_RECORDED_FINDINGS = 32

_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _is_real_instant(text) -> bool:
    """A pattern-valid RFC3339 Z instant -> is it a real UTC moment?

    Pure calendar arithmetic, equivalent to the spine's strptime acceptance
    for this fixed format — used instead of `datetime` so this module imports
    no time machinery at all (the U-W1 no-clock rule, restated in §9).
    """
    if not isinstance(text, str) or not _RFC3339_RE.fullmatch(text):
        return False
    year = int(text[0:4])
    month = int(text[5:7])
    day = int(text[8:10])
    if year < 1 or not (1 <= month <= 12):
        return False
    limit = _DAYS_IN_MONTH[month - 1]
    if month == 2 and year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
        limit = 29
    if not (1 <= day <= limit):
        return False
    return (
        int(text[11:13]) <= 23
        and int(text[14:16]) <= 59
        and int(text[17:19]) <= 59
    )


def _text(value, pattern) -> bool:
    return isinstance(value, str) and bool(pattern.fullmatch(value))


def _count(value, minimum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum


def _fresh(value):
    """Canonical round-trip snapshot on intake (the U-W1 §15 rule).

    A caller-retained reference mutated after the call can neither alter a
    decision nor stale a digest. Raises the spine's ProtocolError, which every
    caller maps to its own closed code.
    """
    return protocols.parse_canonical(protocols.serialize_canonical(value))


def _seal(body: dict) -> dict:
    """A canonical record plus its self-excluding digest (§10).

    The body goes through the canonical round trip first, so every returned
    record is deep-fresh: nothing it carries aliases an input document, the
    snapshot it was derived from, or another returned record (§9).
    """
    record = _fresh(
        {k: v for k, v in body.items() if k != protocols.CONTENT_HASH_FIELD}
    )
    record[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(record)
    return record


def _seal_snapshot(body: dict) -> dict:
    """`_seal` for the §9 snapshot, refusing closed at the canonical bound.

    `_seal` measures the body WITHOUT the digest member it then adds, so a
    record sized only by that measurement can still cross
    `MAX_ARTIFACT_BYTES` once sealed — and a snapshot that crosses it can no
    longer be parsed, which is a raw spine `too_large` on the next use rather
    than a refusal. §9 makes `decide` and `fold` raise closed §8 reasons
    only, so the bound is checked here, before the seal, exactly as the other
    counters and collections are checked before they are advanced.
    """
    try:
        measured = len(protocols.serialize_canonical(
            {k: v for k, v in body.items()
             if k != protocols.CONTENT_HASH_FIELD}
        ))
    except protocols.ProtocolError as refusal:
        raise _refuse("snapshot_divergence", "/", code=refusal.code) from None
    if measured + _DIGEST_MEMBER_BYTES > protocols.MAX_ARTIFACT_BYTES:
        raise _refuse("snapshot_divergence", "/")
    return _seal(body)


def _digest_matches(record: dict) -> bool:
    return record.get(protocols.CONTENT_HASH_FIELD) == protocols.content_digest(
        record
    )


def _trace_ok(trace) -> bool:
    if not isinstance(trace, dict):
        return False
    if set(trace) - {"trace_id", "correlation_id", "causation_id"}:
        return False
    if "trace_id" not in trace or "correlation_id" not in trace:
        return False
    if not _text(trace["trace_id"], _TRACE_ID_RE):
        return False
    if trace["trace_id"] == "0" * 32:
        return False
    if not _text(trace["correlation_id"], _UUID_RE):
        return False
    if "causation_id" in trace and not _text(trace["causation_id"], _UUID_RE):
        return False
    return True


# ---------------------------------------------------------------------------
# Derived identifiers (§13.1). Domain-separated pure functions of history:
# no clock, no RNG, and byte-stable under replay.

_TAG_INTENT = b"aos-workflow-intent/v1"
_TAG_DISPATCH_IDEM = b"aos-workflow-dispatch-idem/v1"
_TAG_IDENTITY = b"aos-workflow-identity/v1"

#: The most events one accepted command appends (pre-dispatch `request_cancel`
#: with an outstanding intent emits `dispatch_revoked` + `workflow_cancelled`).
#: Used only as the headroom the counter ceiling must leave.
_MAX_EVENTS_PER_COMMAND = 2

#: A canonical UUID string plus its quotes and separator: the per-item cost of
#: an intent-id array, used to reserve headroom at admission.
_INTENT_ID_BYTES = 39

#: The canonical width the self-excluding digest member adds to a sealed
#: record. `_seal` sizes the body without it, so this is what a record at the
#: ceiling still owes; derived from the frozen field name and digest width
#: rather than written out as a number. Measured against a NON-EMPTY object,
#: because the member a sealed record gains also carries its separator, and
#: every record this module seals already has other keys.
_DIGEST_MEMBER_BYTES = (
    len(protocols.serialize_canonical(
        {"": 0, protocols.CONTENT_HASH_FIELD: "0" * 64}
    ))
    - len(protocols.serialize_canonical({"": 0}))
)

#: Everything the mutable half of a §9 snapshot can add over the instance's
#: whole life, so admission can refuse a pair the snapshot could not carry:
#: BOTH bounded intent collections at `MAX_ARRAY_ITEMS` (§9 freezes two, and
#: `_append_intent_id` bounds each independently), the optional pointer and
#: route fields at their pattern maxima, the five counters at `INT_MAX`, and
#: the digest member above. Every term is a frozen canonical limit or a
#: frozen pattern bound — nothing here is tuned.
_SNAPSHOT_GROWTH_RESERVE = (
    2 * protocols.MAX_ARRAY_ITEMS * _INTENT_ID_BYTES
    + len(protocols.serialize_canonical({
        "cancel_intent_id": "0" * 36,
        "dispatch_intent_id": "0" * 36,
        "runtime_task_uuid": "0" * 36,
        "queue_route": "q" * 64,
        "intent_seq": protocols.INT_MAX,
        "last_runtime_approval_seq": protocols.INT_MAX,
        "last_seq": protocols.INT_MAX,
        "last_wait_entry_seq": protocols.INT_MAX,
        "revision": protocols.INT_MAX,
        protocols.CONTENT_HASH_FIELD: "0" * 64,
    }))
)


def _workflow_identity(work_spec_sha256: str) -> str:
    """The `WF-<n>` ledger identity, derived from the admitted digest.

    §6 forbids `workflow_id` on the admit envelope, §9 passes `None` for the
    snapshot and freezes `facts` as the two ledger booleans, and §7 requires
    the id on every event — so the only channel left is the command's own
    content, and this unit's frozen derivation idiom (§13.1) is what supplies
    it. Consequences, all of them wanted: the identity is deterministic and
    replay-stable, it is a pure function of `work_spec_sha256`, and §11's "one
    instance per WorkSpec" becomes structural — re-admission derives the same
    id, so the `workflows` primary key and the `UNIQUE(work_spec_sha256)` gate
    agree by construction. The number stays inside `ids.MAX_ID` so a human can
    type it at the CLI (§16) and `ids.parse_id` accepts it.
    """
    number = (
        int.from_bytes(
            _tagged_digest(_TAG_IDENTITY, work_spec_sha256.encode("utf-8"))[:8],
            "big",
        )
        >> 1
    )
    return f"WF-{number or 1}"


def _uuid8_from_digest(digest: bytes) -> str:
    """RFC 9562 UUIDv8 over the first 16 digest bytes: version nibble 8, RFC
    variant bits, lowercase hex. Pinned byte-equal to the private U-W1 helper
    by a §19 test; the copy is deliberate and guarded, not incidental drift."""
    raw = bytearray(digest[:16])
    raw[6] = (raw[6] & 0x0F) | 0x80
    raw[8] = (raw[8] & 0x3F) | 0x80
    text = raw.hex()
    return (
        f"{text[0:8]}-{text[8:12]}-{text[12:16]}-{text[16:20]}-{text[20:32]}"
    )


def _tagged_digest(tag: bytes, material: bytes) -> bytes:
    return hashlib.sha256(tag + b"\0" + material).digest()


def _intent_material(work_spec_sha256: str, intent_seq: int) -> bytes:
    return f"{work_spec_sha256}:{intent_seq}".encode("utf-8")


def _intent_id(work_spec_sha256: str, intent_seq: int) -> str:
    return _uuid8_from_digest(
        _tagged_digest(_TAG_INTENT, _intent_material(work_spec_sha256, intent_seq))
    )


def _idempotency_key(work_spec_sha256: str, intent_seq: int) -> str:
    """One frozen formula for both intent kinds: §13.1 mints exactly one, and
    the per-workflow intent sequence already separates dispatch from cancel."""
    return (
        "wfd-"
        + _tagged_digest(
            _TAG_DISPATCH_IDEM, _intent_material(work_spec_sha256, intent_seq)
        ).hex()[:40]
    )


# ---------------------------------------------------------------------------
# Matrix lookups. The matrix data IS the legality rule, per policy version.

def _matrix_for(policy_version: int):
    for version, matrix in _POLICY_MATRICES:
        if version == policy_version:
            return matrix
    raise _refuse("policy_version_unsupported", "/policy_version")


def _cell(matrix, source: str, target: str) -> tuple:
    return matrix[WORKFLOW_STATES.index(source)][WORKFLOW_STATES.index(target)]


def _require_edge(matrix, source: str, target: str, driver: str, *, receipt: bool):
    """Refuse unless `driver` may traverse (source -> target) under `matrix`."""
    cell = _cell(matrix, source, target)
    if driver in cell:
        return
    if cell == _RESERVED_CELL:
        raise _refuse("transition_reserved", f"/{source}/{target}")
    raise _refuse(
        "receipt_out_of_order" if receipt else "illegal_transition",
        f"/{source}/{target}",
    )


def _receipt_target(kind: str):
    for name, target in RECEIPT_TARGET_STATES:
        if name == kind:
            return target
    raise _refuse("receipt_malformed", "/receipt_kind")


def _receipt_event(kind: str) -> str:
    for name, event in RECEIPT_EVENTS:
        if name == kind:
            return event
    raise _refuse("receipt_malformed", "/receipt_kind")


# ---------------------------------------------------------------------------
# Command envelope (§6)

_COMMAND_KEYS = frozenset((
    "schema", "command", "command_id", "workflow_id", "expected_revision",
    "actor", "source", "created_at", "trace", "payload",
    protocols.CONTENT_HASH_FIELD,
))
_COMMAND_REQUIRED_KEYS = (
    "schema", "command", "command_id", "expected_revision", "actor", "source",
    "created_at", "payload", protocols.CONTENT_HASH_FIELD,
)
_COMMAND_SCHEMA_PREFIX = "aos.workflow-command/v"


def _verify_command(command) -> dict:
    """The §6 field table, fail-closed, on a canonical snapshot of the input."""
    if not isinstance(command, dict):
        raise _refuse("command_malformed", "/")
    try:
        fresh = _fresh(command)
    except protocols.ProtocolError as refusal:
        raise _refuse("command_malformed", "/", code=refusal.code) from None

    identity = fresh.get("schema")
    if not isinstance(identity, str) or not identity.startswith(
        _COMMAND_SCHEMA_PREFIX
    ):
        raise _refuse("command_malformed", "/schema")
    if identity != WORKFLOW_COMMAND_SCHEMA:
        raise _refuse("command_schema_unsupported", "/schema")

    if set(fresh) - _COMMAND_KEYS:
        raise _refuse("command_malformed", "/")
    for key in _COMMAND_REQUIRED_KEYS:
        if key not in fresh:
            raise _refuse("command_malformed", f"/{key}")

    name = fresh["command"]
    if not isinstance(name, str):
        raise _refuse("command_malformed", "/command")
    if name not in WORKFLOW_COMMANDS:
        raise _refuse("command_unknown", "/command")

    if not _text(fresh["command_id"], _UUID_RE):
        raise _refuse("command_malformed", "/command_id")
    if not _count(fresh["expected_revision"], 0):
        raise _refuse("command_malformed", "/expected_revision")
    if not _text(fresh["actor"], _PROVENANCE_RE):
        raise _refuse("command_malformed", "/actor")
    if fresh["source"] not in COMMAND_SOURCES:
        raise _refuse("command_malformed", "/source")
    if not _is_real_instant(fresh["created_at"]):
        raise _refuse("command_malformed", "/created_at")
    if "trace" in fresh and not _trace_ok(fresh["trace"]):
        raise _refuse("command_malformed", "/trace")

    creates = name == "admit_work_spec"
    if creates and "workflow_id" in fresh:
        raise _refuse("command_malformed", "/workflow_id")
    if not creates and not _text(fresh.get("workflow_id"), _WORKFLOW_ID_RE):
        raise _refuse("command_malformed", "/workflow_id")

    if not isinstance(fresh["payload"], dict):
        raise _refuse("command_malformed", "/payload")
    if not _digest_matches(fresh):
        raise _refuse("command_malformed", f"/{protocols.CONTENT_HASH_FIELD}")
    return fresh


_PAYLOAD_KEYS = (
    ("admit_work_spec", ("work_spec_document", "report_document"),
     ("work_spec_document", "report_document")),
    ("validate", (), ()),
    ("request_approval", (), ()),
    ("record_approval", ("approval_document",), ("approval_document",)),
    ("request_dispatch", ("queue_route",), ()),
    ("revoke_dispatch", (), ()),
    ("request_cancel", (), ()),
    ("record_queue_receipt", ("receipt_document",), ("receipt_document",)),
    ("record_result", ("result_document",), ("result_document",)),
)


def _verify_payload(name: str, payload: dict) -> dict:
    """Closed per verb (§6); an unknown key refuses `payload_malformed`."""
    for verb, allowed, required in _PAYLOAD_KEYS:
        if verb != name:
            continue
        if set(payload) - set(allowed):
            raise _refuse("payload_malformed", "/payload")
        for key in required:
            if key not in payload:
                raise _refuse("payload_malformed", f"/payload/{key}")
            if not isinstance(payload[key], dict):
                raise _refuse("payload_malformed", f"/payload/{key}")
        return payload
    raise _refuse("payload_malformed", "/payload")


# ---------------------------------------------------------------------------
# Snapshot record (§9)

_SNAPSHOT_KEYS = (
    "schema", "workflow_id", "task_id", "work_spec_sha256", "report_sha256",
    "snapshot_sha256", "registry_version", "compile_status",
    "work_spec_document", "report_document", "state", "revision",
    "policy_version", "approval_required", "admission_approval_satisfied",
    "dispatch_intent_id", "cancel_intent_id", "runtime_task_uuid",
    "queue_route", "intent_seq", "revoked_intent_ids", "resolved_intent_ids",
    "last_seq", "last_wait_entry_seq", "last_runtime_approval_seq",
    protocols.CONTENT_HASH_FIELD,
)


def _optional(value, pattern) -> bool:
    return value is None or _text(value, pattern)


def _uuid_list_ok(value) -> bool:
    return isinstance(value, list) and all(
        _text(item, _UUID_RE) for item in value
    )


def _verify_snapshot(snapshot) -> dict:
    """The closed §9 record, on a canonical snapshot of the caller's value.

    A structurally invalid snapshot — including the bodies-are-null value
    `fold` returns (§14.2) — refuses `snapshot_divergence`, which keeps the
    reducer inside the closed §8 vocabulary and fails closed.
    """
    if not isinstance(snapshot, dict):
        raise _refuse("snapshot_divergence", "/")
    try:
        fresh = _fresh(snapshot)
    except protocols.ProtocolError as refusal:
        raise _refuse("snapshot_divergence", "/", code=refusal.code) from None
    if set(fresh) != set(_SNAPSHOT_KEYS):
        raise _refuse("snapshot_divergence", "/")
    if fresh["schema"] != WORKFLOW_SNAPSHOT_SCHEMA:
        raise _refuse("snapshot_divergence", "/schema")

    checks = (
        ("workflow_id", _text(fresh["workflow_id"], _WORKFLOW_ID_RE)),
        ("task_id", _text(fresh["task_id"], _AOS_TASK_ID_RE)),
        ("work_spec_sha256", _text(fresh["work_spec_sha256"], _SHA256_RE)),
        ("report_sha256", _text(fresh["report_sha256"], _SHA256_RE)),
        ("snapshot_sha256", _text(fresh["snapshot_sha256"], _SHA256_RE)),
        ("registry_version", _count(fresh["registry_version"], 1)),
        ("compile_status", fresh["compile_status"] in _ADMISSIBLE_STATUSES),
        ("work_spec_document", isinstance(fresh["work_spec_document"], dict)),
        ("report_document", isinstance(fresh["report_document"], dict)),
        ("state", fresh["state"] in WORKFLOW_STATES),
        ("revision", _count(fresh["revision"], 1)),
        ("policy_version", _count(fresh["policy_version"], 1)),
        ("approval_required", isinstance(fresh["approval_required"], bool)),
        ("admission_approval_satisfied",
         isinstance(fresh["admission_approval_satisfied"], bool)),
        ("dispatch_intent_id", _optional(fresh["dispatch_intent_id"], _UUID_RE)),
        ("cancel_intent_id", _optional(fresh["cancel_intent_id"], _UUID_RE)),
        ("runtime_task_uuid", _optional(fresh["runtime_task_uuid"], _UUID_RE)),
        ("queue_route", _optional(fresh["queue_route"], _COMPONENT_ID_RE)),
        ("intent_seq", _count(fresh["intent_seq"], 0)),
        ("revoked_intent_ids", _uuid_list_ok(fresh["revoked_intent_ids"])),
        ("resolved_intent_ids", _uuid_list_ok(fresh["resolved_intent_ids"])),
        ("last_seq", _count(fresh["last_seq"], 1)),
        ("last_wait_entry_seq", _count(fresh["last_wait_entry_seq"], 0)),
        ("last_runtime_approval_seq",
         _count(fresh["last_runtime_approval_seq"], 0)),
    )
    for name, ok in checks:
        if not ok:
            raise _refuse("snapshot_divergence", f"/{name}")

    # The §14.1 structural CHECKs, enforced here too so the reducer never acts
    # on a projection the storage layer would refuse.
    state = fresh["state"]
    if fresh["dispatch_intent_id"] is not None and state != "validated":
        raise _refuse("snapshot_divergence", "/dispatch_intent_id")
    if fresh["cancel_intent_id"] is not None and state not in _POST_DISPATCH_STATES:
        raise _refuse("snapshot_divergence", "/cancel_intent_id")
    if (
        state in ("compiled", "validated", "awaiting_approval")
        and fresh["runtime_task_uuid"] is not None
    ):
        raise _refuse("snapshot_divergence", "/runtime_task_uuid")

    # §11: digests are recomputed from the STORED bodies at every use, never
    # read from the stored columns.
    if protocols.content_digest(fresh["work_spec_document"]) != fresh[
        "work_spec_sha256"
    ]:
        raise _refuse("snapshot_divergence", "/work_spec_document")
    if protocols.content_digest(fresh["report_document"]) != fresh[
        "report_sha256"
    ]:
        raise _refuse("snapshot_divergence", "/report_document")

    # Re-digesting proves the body agrees with a column the SAME untrusted row
    # supplies, which is agreement, not provenance: a spliced or corrupted
    # `workflows` row states both. §3 admits every document reaching U-W2 only
    # through FULL verification, so the stored artifact goes back through the
    # §11 gate it was admitted by. That — not the digest — is what makes the
    # reducer's later reads of `policy_refs`, `expected_result` and `retry`
    # total, and what keeps an AttributeError/KeyError/TypeError out of a
    # handler (§8: a raw exception is never a refusal path).
    try:
        workspecs.accept_work_spec(fresh["work_spec_document"])
    except protocols.ProtocolError as refusal:
        raise _refuse(
            "snapshot_divergence", "/work_spec_document", code=refusal.code
        ) from None
    except workspecs.WorkSpecError as refusal:
        raise _refuse(
            "snapshot_divergence", "/work_spec_document", code=refusal.reason
        ) from None

    # The identity is a pure function of the admitted digest (§6, §13.1), so a
    # snapshot that disagrees with its own derivation is spliced, not stale.
    if fresh["workflow_id"] != _workflow_identity(fresh["work_spec_sha256"]):
        raise _refuse("snapshot_divergence", "/workflow_id")

    # Counters: every emitted intent is recorded by an event (§9, §10), so
    # `intent_seq <= last_seq`, and the closed intent sets can never name more
    # intents than were emitted. The upper bounds are the canonical limits the
    # record must survive (`protocols.INT_MAX`, `protocols.MAX_ARRAY_ITEMS`);
    # a snapshot at the ceiling cannot be advanced and refuses here rather than
    # letting a raw spine error escape the next `_seal`.
    counters = (
        ("revision", fresh["revision"]),
        ("last_seq", fresh["last_seq"]),
        ("intent_seq", fresh["intent_seq"]),
        ("last_wait_entry_seq", fresh["last_wait_entry_seq"]),
        ("last_runtime_approval_seq", fresh["last_runtime_approval_seq"]),
    )
    for name, value in counters:
        if value >= protocols.INT_MAX - _MAX_EVENTS_PER_COMMAND:
            raise _refuse("snapshot_divergence", f"/{name}")
    if fresh["intent_seq"] > fresh["last_seq"]:
        raise _refuse("snapshot_divergence", "/intent_seq")
    for name in ("revoked_intent_ids", "resolved_intent_ids"):
        if len(fresh[name]) > protocols.MAX_ARRAY_ITEMS:
            raise _refuse("snapshot_divergence", f"/{name}")
    if (
        len(fresh["revoked_intent_ids"]) + len(fresh["resolved_intent_ids"])
        > fresh["intent_seq"]
    ):
        raise _refuse("snapshot_divergence", "/resolved_intent_ids")

    # A pending pointer is the intent the LAST emitted seq derives: no further
    # intent can be emitted while either pointer is set (§5.2 legality plus
    # `dispatch_already_pending`/`cancel_already_pending`), so the pointer is
    # verifiable in constant time and needs no search.
    for name in ("dispatch_intent_id", "cancel_intent_id"):
        pointer = fresh[name]
        if pointer is not None and pointer != _intent_id(
            fresh["work_spec_sha256"], fresh["intent_seq"]
        ):
            raise _refuse("snapshot_divergence", f"/{name}")
    if not _digest_matches(fresh):
        raise _refuse("snapshot_divergence", f"/{protocols.CONTENT_HASH_FIELD}")
    return fresh


# ---------------------------------------------------------------------------
# Admission (§11)

_REGISTRY_STATE_KEYS = (
    "registry_version", "work_spec_schema_sha256", "snapshot_sha256",
)


def _admitted_findings(report: dict) -> list:
    """Finding code/path pairs for the admission payload (§11), bounded at 32.

    The compile report is untrusted cross-boundary input and the U-W1 seam
    validates only its outer shape, so every string this unit copies into a
    closed event payload is re-checked here: the code must be a member of the
    frozen lint vocabulary and the path must be a bounded schema-safe path
    that carries no secret-shaped content (§3, §7).
    """
    pairs = []
    for finding in report["findings"][:_MAX_RECORDED_FINDINGS]:
        code = finding.get("code")
        path = finding.get("path")
        if code not in workspecs.WORKSPEC_LINT_CODES:
            raise _refuse("admission_report_malformed", "/findings")
        if not isinstance(path, str) or len(path) > _MAX_PATH_CHARS:
            raise _refuse("admission_report_malformed", "/findings")
        if not _SCHEMA_PATH_RE.fullmatch(path):
            raise _refuse("admission_report_malformed", "/findings")
        if secretscan.scan_secrets(path):
            raise _refuse("admission_report_malformed", "/findings")
        pairs.append({"code": code, "path": path})
    return pairs


def _verify_registry_state(report: dict) -> dict:
    registry_state = report["registry_state"]
    if set(registry_state) != set(_REGISTRY_STATE_KEYS):
        raise _refuse("admission_report_malformed", "/registry_state")
    if not _count(registry_state["registry_version"], 1):
        raise _refuse("admission_report_malformed", "/registry_state")
    for key in ("work_spec_schema_sha256", "snapshot_sha256"):
        if not _text(registry_state[key], _SHA256_RE):
            raise _refuse("admission_report_malformed", f"/registry_state/{key}")
    return registry_state


def _require_admissible_size(snapshot: dict) -> None:
    """The admitted snapshot must leave room for everything it can become.

    Measured on the real record rather than on the two bodies alone, because
    the snapshot also carries the §9 field table around them; the reserve is
    every mutable field at its frozen bound. An instance that passes here can
    reach any state, emit intents until both collections are full, and still
    seal inside `MAX_ARTIFACT_BYTES` — which is what makes `_seal_snapshot`'s
    guard a backstop rather than a workflow that bricks after admission.
    """
    if (
        len(protocols.serialize_canonical(snapshot)) + _SNAPSHOT_GROWTH_RESERVE
        >= protocols.MAX_ARTIFACT_BYTES
    ):
        raise _refuse(
            "admission_artifact_invalid", "/payload", code="too_large"
        )


def _admit(command: dict, facts: AdmissionFacts) -> WorkflowDecision:
    if command["expected_revision"] != 0:
        raise _refuse("revision_mismatch", "/expected_revision")
    payload = _verify_payload("admit_work_spec", command["payload"])

    # 1. Artifact: the public U-W1 acceptance seam (canonical round trip,
    #    spine validation, identity check). The digest is recomputed here and
    #    is THE workflow identity.
    try:
        artifact = workspecs.accept_work_spec(payload["work_spec_document"])
    except protocols.ProtocolError as refusal:
        raise _refuse(
            "admission_artifact_invalid", "/payload/work_spec_document",
            code=refusal.code
        ) from None
    except workspecs.WorkSpecError as refusal:
        raise _refuse(
            "admission_artifact_invalid", "/schema", code=refusal.reason
        ) from None
    work_spec_sha256 = protocols.content_digest(artifact)

    # 2. Report self-digest and report -> artifact binding: the frozen sidecar
    #    rule. The seam's two closed codes map 1:1.
    try:
        report = workspecs.accept_compile_report(
            payload["report_document"], work_spec_sha256
        )
    except workspecs.WorkSpecError as refusal:
        raise _refuse(
            "admission_report_malformed"
            if refusal.reason == "malformed_report"
            else "admission_report_unbound",
            "/report_document",
        ) from None
    registry_state = _verify_registry_state(report)
    findings = _admitted_findings(report)

    # 3. Registry binding.
    if registry_state["registry_version"] != protocols.REGISTRY_VERSION:
        raise _refuse("admission_registry_mismatch", "/registry_state")
    if (
        registry_state["work_spec_schema_sha256"]
        != protocols.REGISTRY["beast.work-spec/v1"].digest
    ):
        raise _refuse("admission_registry_mismatch", "/registry_state")

    # 4. Compile status.
    status = report["status"]
    if status in _BLOCKING_STATUSES:
        raise _refuse("admission_status_blocking", "/status", status=status)
    if status not in _ADMISSIBLE_STATUSES:
        raise _refuse("admission_report_malformed", "/status")

    # 5. Ledger facts (shell-verified).
    if not facts.task_exists:
        raise _refuse("admission_task_unknown", "/aos_task_id")
    if not facts.task_open:
        raise _refuse("admission_task_closed", "/aos_task_id")

    report_sha256 = protocols.content_digest(report)
    approval_required = status == "requires_external_authority" or bool(
        artifact.get("policy_refs", {}).get("approval_ref")
    )
    snapshot = {
        "schema": WORKFLOW_SNAPSHOT_SCHEMA,
        "workflow_id": _workflow_identity(work_spec_sha256),
        "task_id": artifact["aos_task_id"],
        "work_spec_sha256": work_spec_sha256,
        "report_sha256": report_sha256,
        "snapshot_sha256": registry_state["snapshot_sha256"],
        "registry_version": registry_state["registry_version"],
        "compile_status": status,
        "work_spec_document": artifact,
        "report_document": report,
        "state": "compiled",
        "revision": 1,
        "policy_version": TRANSITION_POLICY_VERSION,
        "approval_required": approval_required,
        "admission_approval_satisfied": False,
        "dispatch_intent_id": None,
        "cancel_intent_id": None,
        "runtime_task_uuid": None,
        "queue_route": None,
        "intent_seq": 0,
        "revoked_intent_ids": [],
        "resolved_intent_ids": [],
        "last_seq": 1,
        "last_wait_entry_seq": 0,
        "last_runtime_approval_seq": 0,
    }
    event = _build_event(
        snapshot,
        command,
        event="workflow_admitted",
        seq=1,
        revision=1,
        from_state=None,
        to_state="compiled",
        payload={
            "compile_status": status,
            "work_spec_sha256": work_spec_sha256,
            "report_sha256": report_sha256,
            "snapshot_sha256": registry_state["snapshot_sha256"],
            "registry_version": registry_state["registry_version"],
            "findings": findings,
            "approval_required": approval_required,
            "task_id": artifact["aos_task_id"],
        },
    )
    # Both documents are admission-time immutables the snapshot embeds
    # verbatim (§11); refuse here, closed, if the instance could not carry
    # them through every mutation §9 permits.
    _require_admissible_size(snapshot)
    return WorkflowDecision(_seal_snapshot(snapshot), (event,), None)


# ---------------------------------------------------------------------------
# Approval facts (§12.1)

_APPROVAL_KEYS = (
    "schema", "work_spec_sha256", "approval_ref", "scope", "approved_by",
    "approved_at", protocols.CONTENT_HASH_FIELD,
)


def _verify_approval_fact(fresh: dict) -> dict:
    # `fresh` is already a canonical, freshly-parsed value: `_verify_command`
    # round-tripped the whole command envelope on intake (§15).
    if set(fresh) != set(_APPROVAL_KEYS):
        raise _refuse("approval_fact_malformed", "/")
    if fresh["schema"] != WORKFLOW_APPROVAL_FACT_SCHEMA:
        raise _refuse("approval_fact_malformed", "/schema")
    checks = (
        ("work_spec_sha256", _text(fresh["work_spec_sha256"], _SHA256_RE)),
        ("approval_ref", _text(fresh["approval_ref"], _OPAQUE_REF_RE)),
        ("scope", fresh["scope"] in APPROVAL_SCOPES),
        ("approved_by", _text(fresh["approved_by"], _PROVENANCE_RE)),
        ("approved_at", _is_real_instant(fresh["approved_at"])),
    )
    for name, ok in checks:
        if not ok:
            raise _refuse("approval_fact_malformed", f"/{name}")
    if not _digest_matches(fresh):
        raise _refuse(
            "approval_fact_malformed", f"/{protocols.CONTENT_HASH_FIELD}"
        )
    return fresh


# ---------------------------------------------------------------------------
# Queue receipts (§13.2)

_RECEIPT_KEYS = frozenset((
    "schema", "receipt_kind", "receipt_id", "workflow_id", "work_spec_sha256",
    "intent_id", "idempotency_key", "runtime_task_uuid", "queue_route",
    "reason", "reported_at", "trace", protocols.CONTENT_HASH_FIELD,
))
_RECEIPT_REQUIRED_KEYS = (
    "schema", "receipt_kind", "receipt_id", "workflow_id", "work_spec_sha256",
    "reported_at", protocols.CONTENT_HASH_FIELD,
)
#: Per-kind field obligations (§13.2): required, then forbidden.
_RECEIPT_INTENT_REQUIRED = ("accepted", "rejected")
_RECEIPT_INTENT_ALLOWED = ("accepted", "rejected", "cancelled")
_RECEIPT_UUID_REQUIRED = (
    "accepted", "started", "waiting_input", "waiting_approval", "paused",
    "resumed",
)
_RECEIPT_UUID_FORBIDDEN = ("rejected",)
_RECEIPT_REASON_REQUIRED = ("rejected", "failed")
_RECEIPT_REASON_ALLOWED = ("rejected", "failed", "cancelled")
_REASON_KEYS = ("code", "message", "retryable")
_MAX_REASON_MESSAGE_CHARS = 512


def _reason_ok(reason) -> bool:
    if not isinstance(reason, dict) or set(reason) != set(_REASON_KEYS):
        return False
    if not _text(reason["code"], _ERROR_CODE_RE):
        return False
    message = reason["message"]
    if not isinstance(message, str) or not (
        1 <= len(message) <= _MAX_REASON_MESSAGE_CHARS
    ):
        return False
    return isinstance(reason["retryable"], bool)


def _verify_receipt(fresh: dict) -> dict:
    # Already canonical and fresh: see `_verify_approval_fact`.
    if set(fresh) - _RECEIPT_KEYS:
        raise _refuse("receipt_malformed", "/")
    for key in _RECEIPT_REQUIRED_KEYS:
        if key not in fresh:
            raise _refuse("receipt_malformed", f"/{key}")
    if fresh["schema"] != WORKFLOW_RECEIPT_SCHEMA:
        raise _refuse("receipt_malformed", "/schema")
    kind = fresh["receipt_kind"]
    if kind not in WORKFLOW_RECEIPT_KINDS:
        raise _refuse("receipt_malformed", "/receipt_kind")
    checks = (
        ("receipt_id", _text(fresh["receipt_id"], _UUID_RE)),
        ("workflow_id", _text(fresh["workflow_id"], _WORKFLOW_ID_RE)),
        ("work_spec_sha256", _text(fresh["work_spec_sha256"], _SHA256_RE)),
        ("reported_at", _is_real_instant(fresh["reported_at"])),
    )
    for name, ok in checks:
        if not ok:
            raise _refuse("receipt_malformed", f"/{name}")
    if "trace" in fresh and not _trace_ok(fresh["trace"]):
        raise _refuse("receipt_malformed", "/trace")
    if "queue_route" in fresh and not _text(
        fresh["queue_route"], _COMPONENT_ID_RE
    ):
        raise _refuse("receipt_malformed", "/queue_route")

    for field_name, required, allowed, valid in (
        ("intent_id", _RECEIPT_INTENT_REQUIRED, _RECEIPT_INTENT_ALLOWED,
         _text(fresh.get("intent_id"), _UUID_RE)),
        # §13.2 requires the echo on accepted/rejected and forbids it nowhere,
        # so any kind may carry it; the pattern still applies.
        ("idempotency_key", _RECEIPT_INTENT_REQUIRED, WORKFLOW_RECEIPT_KINDS,
         _text(fresh.get("idempotency_key"), _IDEMPOTENCY_RE)),
        ("runtime_task_uuid", _RECEIPT_UUID_REQUIRED,
         tuple(k for k in WORKFLOW_RECEIPT_KINDS
               if k not in _RECEIPT_UUID_FORBIDDEN),
         _text(fresh.get("runtime_task_uuid"), _UUID_RE)),
        ("reason", _RECEIPT_REASON_REQUIRED, _RECEIPT_REASON_ALLOWED,
         _reason_ok(fresh.get("reason"))),
    ):
        present = field_name in fresh
        if present and kind not in allowed:
            raise _refuse("receipt_malformed", f"/{field_name}")
        if not present and kind in required:
            raise _refuse("receipt_malformed", f"/{field_name}")
        if present and not valid:
            raise _refuse("receipt_malformed", f"/{field_name}")

    if not _digest_matches(fresh):
        raise _refuse("receipt_malformed", f"/{protocols.CONTENT_HASH_FIELD}")
    return fresh


# ---------------------------------------------------------------------------
# Result envelopes and the evidence predicate (§12.2)

def _count_evidence(envelope: dict, expected: dict):
    """An item counts iff its kind is declared AND its ref and claim are
    non-blank (the D-v0.2.36 rule; `str.strip()` judges blankness, so NBSP and
    ideographic padding are whitespace). Declared kinds are acceptable kinds,
    not mandatory ones — coverage of every kind is NOT required."""
    kinds = tuple(expected["evidence_kinds"])
    counted = []
    discounted_kind = 0
    discounted_blank = 0
    for item in envelope["evidence"]:
        if item["kind"] not in kinds:
            discounted_kind += 1
            continue
        if not item["ref"].strip() or not item["claim"].strip():
            discounted_blank += 1
            continue
        counted.append(item)
    return counted, discounted_kind, discounted_blank


def _verify_result(fresh: dict, snapshot: dict) -> dict:
    # Already canonical and fresh: see `_verify_approval_fact`.
    try:
        entry = protocols.validate_document(fresh)
    except protocols.ProtocolError as refusal:
        raise _refuse(
            "result_malformed", "/payload/result_document", code=refusal.code
        ) from None
    if entry.identity != "beast.result-envelope/v1":
        raise _refuse("result_malformed", "/schema")
    try:
        protocols.verify_binding(fresh, snapshot["work_spec_document"])
    except protocols.ProtocolError as refusal:
        raise _refuse(
            "result_unbound", "/payload/result_document", code=refusal.code
        ) from None
    return fresh


# ---------------------------------------------------------------------------
# Intent builders (§13.1)

def _dispatch_intent(
    snapshot: dict, command: dict, intent_seq: int, queue_route: str
) -> dict:
    body = {
        "schema": WORKFLOW_INTENT_SCHEMA,
        "intent_kind": "dispatch",
        "intent_id": _intent_id(snapshot["work_spec_sha256"], intent_seq),
        "workflow_id": snapshot["workflow_id"],
        "aos_task_id": snapshot["task_id"],
        "work_spec_sha256": snapshot["work_spec_sha256"],
        "report_sha256": snapshot["report_sha256"],
        "snapshot_sha256": snapshot["snapshot_sha256"],
        "compile_status": snapshot["compile_status"],
        "idempotency_key": _idempotency_key(
            snapshot["work_spec_sha256"], intent_seq
        ),
        "queue_route": queue_route,
        "requested_at": command["created_at"],
        # The FULL canonical artifact: records are the only channel, and the
        # receiver re-verifies it against work_spec_sha256.
        "work_spec_document": snapshot["work_spec_document"],
    }
    if "trace" in command:
        body["trace"] = command["trace"]
    return _seal(body)


def _cancel_intent(
    snapshot: dict, command: dict, intent_seq: int, cancels_intent_id
) -> dict:
    body = {
        "schema": WORKFLOW_INTENT_SCHEMA,
        "intent_kind": "cancel",
        "intent_id": _intent_id(snapshot["work_spec_sha256"], intent_seq),
        "workflow_id": snapshot["workflow_id"],
        "work_spec_sha256": snapshot["work_spec_sha256"],
        "cancels_intent_id": cancels_intent_id,
        "idempotency_key": _idempotency_key(
            snapshot["work_spec_sha256"], intent_seq
        ),
        "queue_route": snapshot["queue_route"],
        "requested_at": command["created_at"],
    }
    if snapshot["runtime_task_uuid"] is not None:
        body["runtime_task_uuid"] = snapshot["runtime_task_uuid"]
    if "trace" in command:
        body["trace"] = command["trace"]
    return _seal(body)


# ---------------------------------------------------------------------------
# Event builder (§7)

def _build_event(
    snapshot: dict,
    command: dict,
    *,
    event: str,
    seq: int,
    revision: int,
    from_state,
    to_state,
    payload: dict,
) -> dict:
    return _seal({
        "schema": WORKFLOW_EVENT_SCHEMA,
        "event": event,
        "workflow_id": snapshot["workflow_id"],
        "work_spec_sha256": snapshot["work_spec_sha256"],
        "seq": seq,
        "revision": revision,
        "policy_version": snapshot["policy_version"],
        "from_state": from_state,
        "to_state": to_state,
        "command_id": command["command_id"],
        "command_sha256": command[protocols.CONTENT_HASH_FIELD],
        "actor": command["actor"],
        "payload": payload,
        # Copied from the command: deterministic, and the engine has no clock.
        "created_at": command["created_at"],
    })


# ---------------------------------------------------------------------------
# The verb handlers. Each returns (updates, emissions, intent) where an
# emission is (event_name, to_state, payload); `from_state` and `seq` are
# stamped by `decide`, which owns ordering.

def _handle_validate(snapshot, command, matrix, payload):
    _require_edge(matrix, snapshot["state"], "validated", "cmd:validate",
                  receipt=False)
    return {"state": "validated"}, [("workflow_validated", "validated", {})], None


def _handle_request_approval(snapshot, command, matrix, payload):
    _require_edge(matrix, snapshot["state"], "awaiting_approval",
                  "cmd:request_approval", receipt=False)
    if not snapshot["approval_required"]:
        raise _refuse("approval_not_required", "/approval_required")
    if snapshot["admission_approval_satisfied"]:
        raise _refuse("approval_already_satisfied", "/approval_required")
    declared = snapshot["work_spec_document"].get("policy_refs", {}).get(
        "approval_ref"
    )
    event_payload = {"approval_ref": declared} if declared else {}
    return (
        {"state": "awaiting_approval"},
        [("approval_requested", "awaiting_approval", event_payload)],
        None,
    )


def _handle_record_approval(snapshot, command, matrix, payload):
    fact = _verify_approval_fact(payload["approval_document"])
    if fact["work_spec_sha256"] != snapshot["work_spec_sha256"]:
        raise _refuse("approval_fact_unbound", "/work_spec_sha256")
    state = snapshot["state"]
    scope = fact["scope"]
    fact_sha256 = protocols.content_digest(fact)
    event_payload = {
        "scope": scope,
        "approval_ref": fact["approval_ref"],
        "approved_by": fact["approved_by"],
        "fact_sha256": fact_sha256,
    }
    if scope == "admission":
        # Satisfaction is checked before the state gate: a second
        # admission-scope fact necessarily arrives in `validated`, and §12.1
        # names `approval_already_satisfied` for exactly that case.
        if snapshot["admission_approval_satisfied"]:
            raise _refuse("approval_already_satisfied", "/scope")
        if state != "awaiting_approval":
            raise _refuse("approval_not_required", "/scope")
        _require_edge(matrix, state, "validated", "apr:record_approval",
                      receipt=False)
        declared = snapshot["work_spec_document"].get("policy_refs", {}).get(
            "approval_ref"
        )
        # The artifact's declared reference names the pre-authored ADMISSION
        # authority, so an admission-scope fact must repeat it byte-exact.
        if declared is not None and fact["approval_ref"] != declared:
            raise _refuse("approval_fact_unbound", "/approval_ref")
        return (
            {"state": "validated", "admission_approval_satisfied": True},
            [("approval_recorded", "validated", event_payload)],
            None,
        )
    # A runtime-scope fact binds by digest and scope only and carries the
    # approving system's OWN opaque reference; the record is stateless.
    if state != "waiting_approval":
        raise _refuse("approval_not_required", "/scope")
    return {}, [("approval_recorded", None, event_payload)], None


def _handle_request_dispatch(snapshot, command, matrix, payload):
    if snapshot["state"] != "validated":
        raise _refuse("illegal_transition", "/state")
    if snapshot["approval_required"] and not snapshot[
        "admission_approval_satisfied"
    ]:
        raise _refuse("approval_pending", "/approval_required")
    if snapshot["dispatch_intent_id"] is not None:
        raise _refuse("dispatch_already_pending", "/dispatch_intent_id")
    queue_route = payload.get("queue_route", "default")
    if not _text(queue_route, _COMPONENT_ID_RE):
        raise _refuse("payload_malformed", "/payload/queue_route")
    intent_seq = snapshot["intent_seq"] + 1
    intent = _dispatch_intent(snapshot, command, intent_seq, queue_route)
    return (
        {
            "dispatch_intent_id": intent["intent_id"],
            "queue_route": queue_route,
            "intent_seq": intent_seq,
        },
        [(
            "dispatch_requested",
            None,
            {
                "intent_id": intent["intent_id"],
                "idempotency_key": intent["idempotency_key"],
                "queue_route": queue_route,
            },
        )],
        intent,
    )


def _handle_revoke_dispatch(snapshot, command, matrix, payload):
    if snapshot["state"] != "validated":
        raise _refuse("illegal_transition", "/state")
    outstanding = snapshot["dispatch_intent_id"]
    if outstanding is None:
        raise _refuse("dispatch_not_pending", "/dispatch_intent_id")
    intent_seq = snapshot["intent_seq"] + 1
    intent = _cancel_intent(snapshot, command, intent_seq, outstanding)
    return (
        {
            "dispatch_intent_id": None,
            "intent_seq": intent_seq,
            "revoked_intent_ids": _append_intent_id(
                snapshot["revoked_intent_ids"], outstanding,
                "/revoked_intent_ids",
            ),
        },
        [(
            "dispatch_revoked",
            None,
            {"intent_id": outstanding, "cancel_intent_id": intent["intent_id"]},
        )],
        intent,
    )


def _handle_request_cancel(snapshot, command, matrix, payload):
    state = snapshot["state"]
    local = "cmd:request_cancel" in _cell(matrix, state, "cancelled")
    if local:
        # AOS is the source of truth until it has OBSERVED queue acceptance.
        updates = {
            "state": "cancelled",
            "dispatch_intent_id": None,
            "cancel_intent_id": None,
        }
        emissions = []
        intent = None
        outstanding = snapshot["dispatch_intent_id"]
        if outstanding is not None:
            intent_seq = snapshot["intent_seq"] + 1
            intent = _cancel_intent(snapshot, command, intent_seq, outstanding)
            updates["intent_seq"] = intent_seq
            updates["revoked_intent_ids"] = _append_intent_id(
                snapshot["revoked_intent_ids"], outstanding,
                "/revoked_intent_ids",
            )
            emissions.append((
                "dispatch_revoked",
                None,
                {
                    "intent_id": outstanding,
                    "cancel_intent_id": intent["intent_id"],
                },
            ))
        emissions.append(
            ("workflow_cancelled", "cancelled", {"initiator": "requested"})
        )
        return updates, emissions, intent
    if state not in _POST_DISPATCH_STATES:
        raise _refuse("illegal_transition", "/state")
    if snapshot["cancel_intent_id"] is not None:
        raise _refuse("cancel_already_pending", "/cancel_intent_id")
    resolved = snapshot["resolved_intent_ids"]
    intent_seq = snapshot["intent_seq"] + 1
    intent = _cancel_intent(
        snapshot, command, intent_seq, resolved[-1] if resolved else None
    )
    return (
        {"cancel_intent_id": intent["intent_id"], "intent_seq": intent_seq},
        [("cancel_requested", None, {"cancel_intent_id": intent["intent_id"]})],
        intent,
    )


def _append_intent_id(current: list, intent_id: str, where: str) -> list:
    """Append to a §9 bounded intent set, or refuse closed at the bound.

    The bound is the spine's frozen `MAX_ARRAY_ITEMS`: past it the snapshot
    record cannot be serialized at all, so refusing here is what keeps a raw
    spine error out of `_seal`. `where` names the collection that filled, so
    the refusal points at the field rather than at the whole record.
    """
    if len(current) >= protocols.MAX_ARRAY_ITEMS:
        raise _refuse("snapshot_divergence", where)
    return current + [intent_id]


def _closed_intent(snapshot, intent_id) -> bool:
    """An intent this workflow emitted and already closed (§13.3)."""
    return (
        intent_id in snapshot["revoked_intent_ids"]
        or intent_id in snapshot["resolved_intent_ids"]
    )


def _bind_dispatch_receipt(snapshot, receipt):
    """An accepted/rejected receipt must name the OUTSTANDING dispatch intent
    and echo its idempotency key; a closed intent refuses `receipt_superseded`
    and an unknown one `receipt_unbound` (§13.3).

    The outstanding intent is always the one the current `intent_seq` derives —
    no other intent can be emitted while a dispatch is pending — and
    `_verify_snapshot` has already proved the pointer matches, so the key is a
    constant-time derivation rather than a search.
    """
    intent_id = receipt["intent_id"]
    if intent_id != snapshot["dispatch_intent_id"]:
        if _closed_intent(snapshot, intent_id):
            raise _refuse("receipt_superseded", "/intent_id")
        raise _refuse("receipt_unbound", "/intent_id")
    if receipt["idempotency_key"] != _idempotency_key(
        snapshot["work_spec_sha256"], snapshot["intent_seq"]
    ):
        raise _refuse("receipt_unbound", "/idempotency_key")
    return intent_id


def _handle_record_queue_receipt(snapshot, command, matrix, payload):
    receipt = _verify_receipt(payload["receipt_document"])
    if receipt["workflow_id"] != snapshot["workflow_id"]:
        raise _refuse("receipt_unbound", "/workflow_id")
    if receipt["work_spec_sha256"] != snapshot["work_spec_sha256"]:
        raise _refuse("receipt_unbound", "/work_spec_sha256")

    kind = receipt["receipt_kind"]
    state = snapshot["state"]
    target = _receipt_target(kind)
    if target is None:
        # `rejected` is a queue's refusal to ADMIT an intent: stateless, and
        # legal only where a dispatch intent can be outstanding.
        if state != "validated":
            raise _refuse("receipt_out_of_order", "/receipt_kind")
    else:
        _require_edge(matrix, state, target, f"rcp:{kind}", receipt=True)

    receipt_id = receipt["receipt_id"]
    receipt_sha256 = protocols.content_digest(receipt)
    base_payload = {"receipt_id": receipt_id, "receipt_sha256": receipt_sha256}
    declared_uuid = snapshot["work_spec_document"].get("runtime_task_uuid")
    reported_uuid = receipt.get("runtime_task_uuid")

    if kind in ("accepted", "rejected"):
        intent_id = _bind_dispatch_receipt(snapshot, receipt)
        updates = {
            "dispatch_intent_id": None,
            "resolved_intent_ids": _append_intent_id(
                snapshot["resolved_intent_ids"], intent_id,
                "/resolved_intent_ids",
            ),
        }
        if kind == "rejected":
            return (
                updates,
                [(
                    "dispatch_rejected",
                    None,
                    {
                        **base_payload,
                        "intent_id": intent_id,
                        "reason_code": receipt["reason"]["code"],
                        "retryable": receipt["reason"]["retryable"],
                    },
                )],
                None,
            )
        # The runtime mints the task UUID at acceptance; a pre-declared value
        # must match, and every later receipt must repeat it.
        if declared_uuid is not None and reported_uuid != declared_uuid:
            raise _refuse("runtime_uuid_mismatch", "/runtime_task_uuid")
        updates["state"] = "scheduled"
        updates["runtime_task_uuid"] = reported_uuid
        return (
            updates,
            [(
                "dispatch_accepted",
                "scheduled",
                {
                    **base_payload,
                    "intent_id": intent_id,
                    "idempotency_key": receipt["idempotency_key"],
                    "runtime_task_uuid": reported_uuid,
                },
            )],
            None,
        )

    if reported_uuid is not None and snapshot["runtime_task_uuid"] is not None:
        if reported_uuid != snapshot["runtime_task_uuid"]:
            raise _refuse("runtime_uuid_mismatch", "/runtime_task_uuid")

    if kind == "resumed" and state == "waiting_approval":
        # The engine will not record a resumption that claims an approval
        # nobody recorded, nor one an earlier wait already consumed.
        if (
            snapshot["last_runtime_approval_seq"]
            <= snapshot["last_wait_entry_seq"]
        ):
            raise _refuse("approval_fact_missing", "/receipt_kind")

    if kind == "cancelled":
        intent_id = receipt.get("intent_id")
        updates = {
            "state": "cancelled",
            "dispatch_intent_id": None,
            "cancel_intent_id": None,
        }
        event_payload = {**base_payload, "initiator": "runtime"}
        if intent_id is not None:
            if intent_id != snapshot["cancel_intent_id"]:
                if intent_id in snapshot["revoked_intent_ids"] or (
                    intent_id in snapshot["resolved_intent_ids"]
                ):
                    raise _refuse("receipt_superseded", "/intent_id")
                raise _refuse("receipt_unbound", "/intent_id")
            updates["resolved_intent_ids"] = _append_intent_id(
                snapshot["resolved_intent_ids"], intent_id,
                "/resolved_intent_ids",
            )
            event_payload["intent_id"] = intent_id
            event_payload["initiator"] = "requested"
        return updates, [("workflow_cancelled", "cancelled", event_payload)], None

    if kind == "failed":
        return (
            {
                "state": "failed",
                "dispatch_intent_id": None,
                "cancel_intent_id": None,
            },
            [(
                "workflow_failed",
                "failed",
                {
                    **base_payload,
                    "reason_code": receipt["reason"]["code"],
                    "retryable": receipt["reason"]["retryable"],
                },
            )],
            None,
        )

    return (
        {"state": target},
        [(
            _receipt_event(kind),
            target,
            {**base_payload, "runtime_task_uuid": reported_uuid},
        )],
        None,
    )


def _handle_record_result(snapshot, command, matrix, payload):
    # §6 makes record_result legal in `running` only; the matrix's reserved
    # cells are unreachable from here by construction (§5.2).
    if snapshot["state"] != "running":
        raise _refuse("illegal_transition", "/state")
    envelope = _verify_result(payload["result_document"], snapshot)
    artifact = snapshot["work_spec_document"]

    budget = artifact.get("retry", {}).get("max_attempts", 1)
    if envelope["attempt"] > budget:
        raise _refuse(
            "result_attempt_exceeded",
            "/attempt",
            attempt=envelope["attempt"],
            budget=budget,
        )

    outcome = envelope["outcome"]
    result_sha256 = protocols.content_digest(envelope)
    if outcome not in ("success", "fail"):
        # Retry and salvage semantics are U-W3's; policy v2 will widen this.
        raise _refuse("result_outcome_inconclusive", "/outcome", outcome=outcome)

    if outcome == "fail":
        _require_edge(matrix, "running", "failed", "res:fail", receipt=False)
        return (
            {
                "state": "failed",
                "dispatch_intent_id": None,
                "cancel_intent_id": None,
            },
            [(
                "workflow_failed",
                "failed",
                {
                    "result_sha256": result_sha256,
                    "attempt": envelope["attempt"],
                    "outcome": outcome,
                },
            )],
            None,
        )

    if envelope["retryable"]:
        # A claim of success that asks to be retried is not an honest report.
        raise _refuse("result_inconsistent", "/retryable")
    _require_edge(matrix, "running", "succeeded", "res:success", receipt=False)

    expected = artifact["expected_result"]
    counted, discounted_kind, discounted_blank = _count_evidence(
        envelope, expected
    )
    required = expected["min_evidence_count"]
    if len(counted) < required:
        raise _refuse(
            "evidence_insufficient",
            "/evidence",
            required=required,
            counted=len(counted),
            discounted_kind=discounted_kind,
            discounted_blank=discounted_blank,
        )
    return (
        {
            "state": "succeeded",
            "dispatch_intent_id": None,
            "cancel_intent_id": None,
        },
        [(
            "workflow_succeeded",
            "succeeded",
            {
                "result_sha256": result_sha256,
                "attempt": envelope["attempt"],
                # Digests, never raw refs.
                "evidence": [
                    {
                        "kind": item["kind"],
                        "ref_sha256": hashlib.sha256(
                            item["ref"].encode("utf-8")
                        ).hexdigest(),
                        "provenance": item["provenance"],
                    }
                    for item in counted
                ],
                "evidence_counted": len(counted),
                "evidence_required": required,
            },
        )],
        None,
    )


def _refuse_on_terminal(snapshot, name: str, payload) -> None:
    """Terminal rows accept no command — but a receipt naming an intent this
    workflow already CLOSED earns the more specific `receipt_superseded`.

    §13.3 states twice, and §19 row 12 freezes as a test obligation, that a
    late `accepted` refuses `receipt_superseded` after all three revocation
    paths — and one of those three (local cancellation) IS terminal. The two
    readings reconcile because both codes mutate nothing: §19 row 2's
    obligation is terminal IMMUTABILITY, and §5.3 names `workflow_terminal`
    for commands, saying only that a receipt on a terminal workflow "refuses
    without mutating anything".

    The carve-out is exactly as wide as §13.3's sentence: an intent this
    workflow REVOKED. A stale receipt for an intent that was resolved
    normally — a duplicate `accepted` on a `succeeded` workflow — is not a
    revocation race, so it still refuses `workflow_terminal`.
    """
    if name == "record_queue_receipt" and isinstance(payload, dict):
        document = payload.get("receipt_document")
        if isinstance(document, dict):
            intent_id = document.get("intent_id")
            if (
                _text(intent_id, _UUID_RE)
                and intent_id in snapshot["revoked_intent_ids"]
            ):
                raise _refuse("receipt_superseded", "/intent_id")
    raise _refuse("workflow_terminal", "/state")


_HANDLERS = (
    ("validate", _handle_validate),
    ("request_approval", _handle_request_approval),
    ("record_approval", _handle_record_approval),
    ("request_dispatch", _handle_request_dispatch),
    ("revoke_dispatch", _handle_revoke_dispatch),
    ("request_cancel", _handle_request_cancel),
    ("record_queue_receipt", _handle_record_queue_receipt),
    ("record_result", _handle_record_result),
)


# ---------------------------------------------------------------------------
# The reducer (§9)

def decide(snapshot, command, facts: AdmissionFacts) -> WorkflowDecision:
    """snapshot + typed command + verified facts -> the next snapshot, the
    events it appends, and at most one queue intent.

    `snapshot` is None exactly for `admit_work_spec`. `facts` is empty for
    every other verb. Refuses with a closed §8 `WorkflowRefusal`; a refusal
    mutates nothing, appends no event, and consumes no revision.
    """
    fresh_command = _verify_command(command)
    name = fresh_command["command"]

    if name == "admit_work_spec":
        if snapshot is not None:
            # One instance per WorkSpec digest (§11); the storage gate is the
            # UNIQUE INSERT, and this is its semantic twin.
            raise _refuse("workflow_exists", "/work_spec_sha256")
        return _admit(fresh_command, facts)

    if snapshot is None:
        raise _refuse("workflow_unknown", "/workflow_id")

    state = _verify_snapshot(snapshot)
    matrix = _matrix_for(state["policy_version"])
    if fresh_command["workflow_id"] != state["workflow_id"]:
        raise _refuse("command_malformed", "/workflow_id")
    if state["state"] in TERMINAL_STATES:
        _refuse_on_terminal(state, name, fresh_command["payload"])
    if fresh_command["expected_revision"] != state["revision"]:
        raise _refuse("revision_mismatch", "/expected_revision")

    payload = _verify_payload(name, fresh_command["payload"])
    for verb, handler in _HANDLERS:
        if verb == name:
            updates, emissions, intent = handler(
                state, fresh_command, matrix, payload
            )
            break
    else:  # pragma: no cover - _verify_command closed the vocabulary
        raise _refuse("command_unknown", "/command")

    revision = state["revision"] + 1
    seq = state["last_seq"]
    from_state = state["state"]
    after = dict(state)
    after.update(updates)
    events = []
    for event_name, to_state, event_payload in emissions:
        seq += 1
        events.append(
            _build_event(
                state,
                fresh_command,
                event=event_name,
                seq=seq,
                revision=revision,
                from_state=from_state,
                to_state=to_state,
                payload=event_payload,
            )
        )
        if to_state is not None:
            from_state = to_state
        # The §12.1 ordering rule lives on the event history, which is what
        # keeps the resumption check inside the pure reducer.
        if event_name == "run_waiting_approval":
            after["last_wait_entry_seq"] = seq
        elif (
            event_name == "approval_recorded"
            and event_payload["scope"] == "runtime"
        ):
            after["last_runtime_approval_seq"] = seq
    after["revision"] = revision
    after["last_seq"] = seq
    return WorkflowDecision(_seal_snapshot(after), tuple(events), intent)


# ---------------------------------------------------------------------------
# History verification and fold (§9, §14.2)

_EVENT_KEYS = (
    "schema", "event", "workflow_id", "work_spec_sha256", "seq", "revision",
    "policy_version", "from_state", "to_state", "command_id",
    "command_sha256", "actor", "payload", "created_at",
    protocols.CONTENT_HASH_FIELD,
)

#: What `fold` reads out of each event payload. Verifying it is what makes
#: "certified by `verify_history`" imply "foldable": §14.2 requires the
#: integrity path to REPORT, and a `KeyError` out of `fold` is not a report.
_EVENT_PAYLOAD_REQUIRED = (
    ("workflow_admitted", (
        ("task_id", "task"), ("report_sha256", "sha256"),
        ("snapshot_sha256", "sha256"), ("registry_version", "count"),
        ("compile_status", "status"), ("approval_required", "bool"),
    )),
    ("approval_recorded", (("scope", "scope"),)),
    ("dispatch_requested", (("intent_id", "uuid"), ("queue_route", "slug"))),
    ("dispatch_revoked", (("intent_id", "uuid"),)),
    ("dispatch_accepted", (
        ("intent_id", "uuid"), ("runtime_task_uuid", "uuid"),
    )),
    ("dispatch_rejected", (("intent_id", "uuid"),)),
    ("cancel_requested", (("cancel_intent_id", "uuid"),)),
)

#: Read conditionally by `fold`, so only the type is pinned when present.
_EVENT_PAYLOAD_OPTIONAL = (
    ("workflow_cancelled", (("intent_id", "uuid"),)),
)


def _payload_value_ok(kind: str, value) -> bool:
    if kind == "uuid":
        return _text(value, _UUID_RE)
    if kind == "sha256":
        return _text(value, _SHA256_RE)
    if kind == "task":
        return _text(value, _AOS_TASK_ID_RE)
    if kind == "slug":
        return _text(value, _COMPONENT_ID_RE)
    if kind == "status":
        return value in _ADMISSIBLE_STATUSES
    if kind == "scope":
        return value in APPROVAL_SCOPES
    if kind == "count":
        return _count(value, 1)
    if kind == "bool":
        return isinstance(value, bool)
    return False  # pragma: no cover - the table is closed


def _verify_event_payload(event: str, payload: dict) -> bool:
    for name, rules in _EVENT_PAYLOAD_REQUIRED:
        if name != event:
            continue
        for key, kind in rules:
            if key not in payload or not _payload_value_ok(kind, payload[key]):
                return False
    for name, rules in _EVENT_PAYLOAD_OPTIONAL:
        if name != event:
            continue
        for key, kind in rules:
            if key in payload and not _payload_value_ok(kind, payload[key]):
                return False
    return True


def _verify_event_shape(record, index: int):
    if not isinstance(record, dict):
        return _refuse("history_corrupt", f"/{index}")
    try:
        fresh = _fresh(record)
    except protocols.ProtocolError:
        return _refuse("history_corrupt", f"/{index}")
    if set(fresh) != set(_EVENT_KEYS):
        return _refuse("history_corrupt", f"/{index}")
    if fresh["schema"] != WORKFLOW_EVENT_SCHEMA:
        return _refuse("history_corrupt", f"/{index}/schema")
    if fresh["event"] not in WORKFLOW_EVENTS:
        return _refuse("history_unknown_event", f"/{index}/event")
    if not _count(fresh["policy_version"], 1):
        return _refuse("history_corrupt", f"/{index}/policy_version")
    if fresh["policy_version"] not in SUPPORTED_POLICY_VERSIONS:
        return _refuse("policy_version_unsupported", f"/{index}/policy_version")
    checks = (
        ("workflow_id", _text(fresh["workflow_id"], _WORKFLOW_ID_RE)),
        ("work_spec_sha256", _text(fresh["work_spec_sha256"], _SHA256_RE)),
        ("seq", _count(fresh["seq"], 1)),
        ("revision", _count(fresh["revision"], 1)),
        ("from_state", fresh["from_state"] is None
         or fresh["from_state"] in WORKFLOW_STATES),
        ("to_state", fresh["to_state"] is None
         or fresh["to_state"] in WORKFLOW_STATES),
        ("command_id", _text(fresh["command_id"], _UUID_RE)),
        ("command_sha256", _text(fresh["command_sha256"], _SHA256_RE)),
        ("actor", _text(fresh["actor"], _PROVENANCE_RE)),
        ("payload", isinstance(fresh["payload"], dict)),
        ("created_at", _is_real_instant(fresh["created_at"])),
    )
    for name, ok in checks:
        if not ok:
            return _refuse("history_corrupt", f"/{index}/{name}")
    if not _verify_event_payload(fresh["event"], fresh["payload"]):
        return _refuse("history_corrupt", f"/{index}/payload")
    if fresh["from_state"] == fresh["to_state"]:
        return _refuse("history_corrupt", f"/{index}/to_state")
    if not _digest_matches(fresh):
        return _refuse("history_corrupt", f"/{index}")
    return fresh


def _read_history(events):
    """(records, refusal): every §14.2 integrity rule, in one pass.

    Reports and never repairs — recovery is a human restoring a verified
    backup, not the engine editing history.
    """
    if not isinstance(events, (list, tuple)) or not events:
        return (), _refuse("history_corrupt", "/")
    records = []
    state = None
    revision = 0
    command_id = None
    for index, record in enumerate(events):
        fresh = _verify_event_shape(record, index)
        if isinstance(fresh, WorkflowRefusal):
            return (), fresh
        if fresh["seq"] != index + 1:
            return (), _refuse("history_corrupt", f"/{index}/seq")
        if index == 0:
            first_ok = (
                fresh["event"] == "workflow_admitted"
                and fresh["from_state"] is None
            )
            if not first_ok:
                return (), _refuse("history_corrupt", "/0")
            if fresh["revision"] != 1:
                return (), _refuse("history_corrupt", "/0/revision")
            state = fresh["to_state"]
            revision = fresh["revision"]
            command_id = fresh["command_id"]
            records.append(fresh)
            continue
        if fresh["event"] == "workflow_admitted":
            return (), _refuse("history_corrupt", f"/{index}/event")
        if fresh["workflow_id"] != records[0]["workflow_id"]:
            return (), _refuse("history_corrupt", f"/{index}/workflow_id")
        if fresh["work_spec_sha256"] != records[0]["work_spec_sha256"]:
            return (), _refuse("history_corrupt", f"/{index}/work_spec_sha256")
        if fresh["from_state"] != state:
            return (), _refuse("history_corrupt", f"/{index}/from_state")
        # The revision counts accepted commands: events of one command share
        # it, and a new command increments it by exactly one.
        if fresh["command_id"] == command_id:
            if fresh["revision"] != revision:
                return (), _refuse("history_corrupt", f"/{index}/revision")
        elif fresh["revision"] != revision + 1:
            return (), _refuse("history_corrupt", f"/{index}/revision")
        revision = fresh["revision"]
        command_id = fresh["command_id"]
        if fresh["to_state"] is not None:
            state = fresh["to_state"]
        records.append(fresh)
    return tuple(records), None


def verify_history(events):
    """None when the history verifies, else the closed refusal that explains
    why. Returns rather than raises: `workflow verify` reports and never
    rewrites (§14.2)."""
    _records, refusal = _read_history(events)
    return refusal


def fold(events) -> dict:
    """Rebuild the snapshot from history.

    Every §9 field EXCEPT the two verbatim document bodies is a pure function
    of the events; the bodies are deliberately absent from every payload
    (§7 carries digests only), so they come back as None and the store
    re-verifies its stored bodies against the recorded digests (§14.2).
    Raises the closed refusal `verify_history` would return.
    """
    records, refusal = _read_history(events)
    if refusal is not None:
        raise refusal
    first = records[0]
    admitted = first["payload"]
    snapshot = {
        "schema": WORKFLOW_SNAPSHOT_SCHEMA,
        "workflow_id": first["workflow_id"],
        "task_id": admitted["task_id"],
        "work_spec_sha256": first["work_spec_sha256"],
        "report_sha256": admitted["report_sha256"],
        "snapshot_sha256": admitted["snapshot_sha256"],
        "registry_version": admitted["registry_version"],
        "compile_status": admitted["compile_status"],
        "work_spec_document": None,
        "report_document": None,
        "state": first["to_state"],
        "revision": first["revision"],
        "policy_version": first["policy_version"],
        "approval_required": admitted["approval_required"],
        "admission_approval_satisfied": False,
        "dispatch_intent_id": None,
        "cancel_intent_id": None,
        "runtime_task_uuid": None,
        "queue_route": None,
        "intent_seq": 0,
        "revoked_intent_ids": [],
        "resolved_intent_ids": [],
        "last_seq": first["seq"],
        "last_wait_entry_seq": 0,
        "last_runtime_approval_seq": 0,
    }
    for record in records[1:]:
        name = record["event"]
        payload = record["payload"]
        seq = record["seq"]
        if name == "approval_recorded":
            if payload["scope"] == "admission":
                snapshot["admission_approval_satisfied"] = True
            else:
                snapshot["last_runtime_approval_seq"] = seq
        elif name == "dispatch_requested":
            snapshot["dispatch_intent_id"] = payload["intent_id"]
            snapshot["queue_route"] = payload["queue_route"]
            snapshot["intent_seq"] += 1
        elif name == "dispatch_revoked":
            snapshot["dispatch_intent_id"] = None
            # The same §9 bound `decide` appends under: a history carrying
            # more closures than the collection can hold is a history this
            # engine never wrote, and it earns the closed refusal rather than
            # a raw spine `too_many_items` out of the seal below.
            snapshot["revoked_intent_ids"] = _append_intent_id(
                snapshot["revoked_intent_ids"], payload["intent_id"],
                "/revoked_intent_ids",
            )
            snapshot["intent_seq"] += 1
        elif name in ("dispatch_accepted", "dispatch_rejected"):
            snapshot["dispatch_intent_id"] = None
            snapshot["resolved_intent_ids"] = _append_intent_id(
                snapshot["resolved_intent_ids"], payload["intent_id"],
                "/resolved_intent_ids",
            )
            if name == "dispatch_accepted":
                snapshot["runtime_task_uuid"] = payload["runtime_task_uuid"]
        elif name == "cancel_requested":
            snapshot["cancel_intent_id"] = payload["cancel_intent_id"]
            snapshot["intent_seq"] += 1
        elif name == "run_waiting_approval":
            snapshot["last_wait_entry_seq"] = seq
        elif name == "workflow_cancelled" and "intent_id" in payload:
            snapshot["resolved_intent_ids"] = _append_intent_id(
                snapshot["resolved_intent_ids"], payload["intent_id"],
                "/resolved_intent_ids",
            )
        if record["to_state"] is not None:
            snapshot["state"] = record["to_state"]
            if record["to_state"] in TERMINAL_STATES:
                snapshot["dispatch_intent_id"] = None
                snapshot["cancel_intent_id"] = None
        snapshot["revision"] = record["revision"]
        snapshot["policy_version"] = record["policy_version"]
        snapshot["last_seq"] = seq
    return _seal_snapshot(snapshot)
