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

#: U-W3 §12.3. The intent is the ONE record that crosses the trust boundary as
#: a file and that U-W2 §18 requires the adapter to pin by content hash, so a
#: widened accepted member set announces itself with a version. Emitted only
#: under transition-policy v2; policy-v1 workflows keep emitting — and every
#: reader keeps reading — `/v1` forever.
WORKFLOW_INTENT_V2_SCHEMA = "aos.workflow-queue-intent/v2"

#: U-W3 §8.3 and §9.4. Both are produced OUTSIDE Agentic OS: a checkpoint by
#: the executing side, a restore fact by whoever performed the restoration.
#: AOS stores and binds them; it never creates, derives or completes one.
WORKFLOW_CHECKPOINT_SCHEMA = "aos.workflow-checkpoint/v1"
WORKFLOW_RESTORE_FACT_SCHEMA = "aos.workflow-restore-fact/v1"

#: Fourteen authoritative states under transition-policy v2 (U-W3 §5.3).
#: `proposed` is the pre-compile authoring plane and is never a workflow
#: state. `retrying` is the fourteenth and is not a naming preference: a
#: workflow whose attempt N failed retryably with attempts remaining cannot
#: sit in any landed state — `failed` is terminal, `running` would claim a
#: live runtime task that does not exist, and `validated` is refused by the
#: storage CHECK that forbids a bound `runtime_task_uuid` there (§5.3.4).
WORKFLOW_STATES = (
    "compiled", "validated", "awaiting_approval", "scheduled", "running",
    "waiting_input", "waiting_approval", "paused", "retrying", "compensating",
    "succeeded", "failed", "cancelled", "compensated",
)

#: Transition-policy version 1's state tuple, FROZEN VERBATIM as history
#: (U-W2 §15's own frozen-retention rule, the `_V2_MEMORY_CLAIM_DDL` trade
#: applied to policy data). Every matrix lookup indexes with its OWN version's
#: tuple, so a v1 event can never be re-derived under v2 rules.
_V1_WORKFLOW_STATES = (
    "compiled", "validated", "awaiting_approval", "scheduled", "running",
    "waiting_input", "waiting_approval", "paused", "compensating",
    "succeeded", "failed", "cancelled", "compensated",
)

#: The four states one workflow attempt row can hold (U-W3 §6.3). `open` is
#: the only non-final value, and at most one attempt per workflow may hold it.
WORKFLOW_ATTEMPT_STATES = ("open", "succeeded", "failed", "abandoned")

#: The compensation phase as AOS observes it, folded from the compensation
#: events. `None` is "no compensation episode"; the three members are the
#: subset of `beast.result-envelope/v1`'s `compensation.state` enum AOS can
#: itself be in — `not_required` is a producer statement, never a phase.
WORKFLOW_COMPENSATION_STATES = ("pending", "applied", "failed")

#: What the eight §11.4 members are before any of them has a fact behind it.
#: A freshly admitted instance and a folded history that recorded none of them
#: land on exactly this, which is what makes a policy-v1 workflow fold to an
#: HONEST `attempts_used = 0` rather than to a guess (§5.5 item 3).
_FRESH_RECOVERY_MEMBERS = {
    "attempt_no": None,
    "attempt_state": None,
    "attempts_used": 0,
    "attempt_budget": None,
    "last_checkpoint_seq": 0,
    "checkpoint_count": 0,
    "compensation_state": None,
    "restored_checkpoint_sha256": None,
}

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
    # U-W3 (§5.4, §8, §9, §10): the four drivers the reserved edges and the
    # bounded-attempt ledger were reserved for.
    "adopt_policy_version", "record_checkpoint", "record_restore",
    "record_compensation",
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
    # U-W3 (§5.5): seven names, each the sole event of exactly one driver
    # class. `compensation_failed` is a distinct name from `workflow_failed`
    # so "the work failed" and "the undo failed" are never confused.
    "policy_version_adopted", "attempt_failed",
    "checkpoint_recorded", "checkpoint_restored",
    "compensation_started", "compensation_applied", "compensation_failed",
)

#: Fifty-seven codes in canonical emission order (the GOVERNANCE_REASON_CODES
#: idiom): U-W2's forty-three, whose spelling, meaning and order are unchanged,
#: plus U-W3's fourteen appended (§5.4). A refusal mutates nothing, appends no
#: event, consumes no revision.
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
    # U-W3 §5.4 — policy adoption and the attempt ledger
    "policy_version_not_upgradable", "attempt_budget_exhausted",
    "attempt_mismatch",
    # U-W3 §5.4 — checkpoints
    "checkpoint_malformed", "checkpoint_unbound", "checkpoint_conflict",
    "checkpoint_limit_exceeded", "checkpoint_unknown",
    "checkpoint_ineligible",
    # U-W3 §5.4 — restoration
    "restore_fact_malformed", "restore_fact_unbound",
    # U-W3 §5.4 — compensation
    "compensation_not_required", "compensation_already_concluded",
    "compensation_state_inconsistent",
)

WORKFLOW_INTENT_KINDS = ("dispatch", "cancel", "compensate")

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

#: U-W2's §5.2 matrix IS version 1 (§15); U-W3 ships version 2 (§5.1).
TRANSITION_POLICY_VERSION = 2

#: Every shipped version replays forever; new decisions use the current one.
#: A version outside this tuple refuses `policy_version_unsupported` and
#: mutates nothing — a FUTURE version is refused, never guessed; a PAST
#: version replays forever.
SUPPORTED_POLICY_VERSIONS = (1, 2)


def _build_matrix(cells, states) -> tuple:
    """The complete N x N table as data, row/column order = `states`.

    A cell is a tuple of the drivers that may traverse it: `()` is the
    contract's `·` (illegal) and `("reserved",)` is its `R` (defined, but
    refused under the version whose table carries it). `"reserved"` is a
    classification, never a driver.
    """
    return tuple(
        tuple(cells.get((source, target), ()) for target in states)
        for source in states
    )


#: FROZEN VERBATIM as history (U-W2 §15, U-W3 §5.1): version 1's 13x13 table,
#: 25 active and 3 reserved cells, exactly as it landed at fef0c2b. It is
#: never regenerated from `WORKFLOW_STATES`, so a v1 event indexes v1's own
#: state tuple and can never re-derive under v2's.
_V1_TRANSITION_MATRIX = _build_matrix({
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
}, _V1_WORKFLOW_STATES)

#: Transition policy version 2 (U-W3 §5.3): 14x14, 35 ACTIVE cells, ZERO
#: reserved cells, 161 illegal cells, one creation pseudo-edge
#: (`∅ → compiled`, via `admit_work_spec`).
#:
#: v2's active-edge set is a strict SUPERSET of v1's — every v1 edge survives
#: with the same driver — which is what makes adoption transition-safe. All
#: three of v1's reserved edges activate and no more; `compensating →
#: cancelled` stays ILLEGAL in every frozen version, because abandoning a
#: compensation mid-flight would be a silent cleanup failure.
TRANSITION_MATRIX = _build_matrix({
    ("compiled", "validated"): ("cmd:validate",),
    ("compiled", "cancelled"): ("cmd:request_cancel",),
    ("validated", "awaiting_approval"): ("cmd:request_approval",),
    ("validated", "scheduled"): ("rcp:accepted",),
    ("validated", "cancelled"): ("cmd:request_cancel",),
    ("awaiting_approval", "validated"): ("apr:record_approval",),
    ("awaiting_approval", "cancelled"): ("cmd:request_cancel",),
    ("scheduled", "running"): ("rcp:started",),
    ("scheduled", "retrying"): ("rcp:failed_retryable",),
    ("scheduled", "failed"): ("rcp:failed",),
    ("scheduled", "cancelled"): ("rcp:cancelled",),
    ("running", "waiting_input"): ("rcp:waiting_input",),
    ("running", "waiting_approval"): ("rcp:waiting_approval",),
    ("running", "paused"): ("rcp:paused",),
    ("running", "retrying"): ("res:fail_retryable", "rcp:failed_retryable"),
    ("running", "compensating"): ("res:compensable",),
    ("running", "succeeded"): ("res:success",),
    ("running", "failed"): ("res:fail", "rcp:failed"),
    ("running", "cancelled"): ("rcp:cancelled",),
    ("waiting_input", "running"): ("rcp:resumed",),
    ("waiting_input", "retrying"): ("rcp:failed_retryable",),
    ("waiting_input", "failed"): ("rcp:failed",),
    ("waiting_input", "cancelled"): ("rcp:cancelled",),
    ("waiting_approval", "running"): ("rcp:resumed",),
    ("waiting_approval", "retrying"): ("rcp:failed_retryable",),
    ("waiting_approval", "failed"): ("rcp:failed",),
    ("waiting_approval", "cancelled"): ("rcp:cancelled",),
    ("paused", "running"): ("rcp:resumed",),
    ("paused", "retrying"): ("rcp:failed_retryable",),
    ("paused", "failed"): ("rcp:failed",),
    ("paused", "cancelled"): ("rcp:cancelled",),
    ("retrying", "scheduled"): ("rcp:accepted",),
    ("retrying", "cancelled"): ("cmd:request_cancel",),
    ("compensating", "failed"): ("cmp:failed", "rcp:failed"),
    ("compensating", "compensated"): ("cmp:applied",),
}, WORKFLOW_STATES)

#: Frozen per-version replay (U-W2 §15, U-W3 §5.1): each entry is
#: `(version, that version's state tuple, that version's matrix)`, so every
#: lookup indexes with its OWN version's states and old history never
#: re-derives under new rules.
_POLICY_MATRICES = (
    (1, _V1_WORKFLOW_STATES, _V1_TRANSITION_MATRIX),
    (2, WORKFLOW_STATES, TRANSITION_MATRIX),
)

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
    "policy_version_not_upgradable": (
        "Transition-policy adoption must be a forward step this workflow's "
        "attempt history can support."
    ),
    "attempt_budget_exhausted": (
        "The artifact's declared attempt budget is already used up."
    ),
    "attempt_mismatch": (
        "The reported attempt is not the attempt this workflow has open."
    ),
    "checkpoint_malformed": (
        "The checkpoint record does not match its closed record shape, its "
        "size bound, or the secret scan."
    ),
    "checkpoint_unbound": (
        "The checkpoint does not bind this workflow, WorkSpec or runtime "
        "task."
    ),
    "checkpoint_conflict": (
        "That checkpoint id is stored with a different body."
    ),
    "checkpoint_limit_exceeded": (
        "The checkpoint count bound for this attempt or workflow is reached."
    ),
    "checkpoint_unknown": (
        "No stored checkpoint of this workflow carries that id."
    ),
    "checkpoint_ineligible": (
        "That checkpoint may not be restored in this state or attempt."
    ),
    "restore_fact_malformed": (
        "The restore record does not match its closed record shape."
    ),
    "restore_fact_unbound": (
        "The restore record does not bind this workflow, the named "
        "checkpoint's digest, or its attempt."
    ),
    "compensation_not_required": (
        "This workflow is not compensating; there is nothing to conclude."
    ),
    "compensation_already_concluded": (
        "This compensation already reached a conclusion."
    ),
    "compensation_state_inconsistent": (
        "The envelope's compensation state contradicts the phase it claims."
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
class ShellFacts:
    """The shell-verified inputs (U-W2 §9 as widened by U-W3 §1.2 row S7).

    U-W2 froze this as the two ledger booleans and nothing else, and named it
    `ShellFacts` because admission was the only verb that needed one.
    U-W3 adds two RESOLVED-CHECKPOINT members for the same structural reason
    the booleans exist: a pure reducer cannot read a stored checkpoint row, so
    whether a named `checkpoint_id` resolves — and to which digest and which
    attempt — is a stored-row judgment the shell makes and hands in.

    Both pairs are EMPTY unless the verb needs them: the booleans only for
    `admit_work_spec`, the checkpoint fields only for a `request_dispatch`
    that carries `restore_checkpoint_id` and for `record_restore`. Nothing
    here is a decision; each member is an observation the reducer then judges.
    The workflow identity is still NOT a fact — it is derived from the
    admitted digest (`_workflow_identity`).
    """

    task_exists: bool = False
    task_open: bool = False
    checkpoint_sha256: str | None = None
    checkpoint_attempt_no: int | None = None


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

    The body is first PROJECTED onto its own policy version's member set, so a
    policy-v1 workflow seals over exactly the members U-W2 sealed over and its
    stored `workflows.content_sha256` keeps matching forever (see
    `_V1_SNAPSHOT_KEYS`).

    `_seal` measures the body WITHOUT the digest member it then adds, so a
    record sized only by that measurement can still cross
    `MAX_ARTIFACT_BYTES` once sealed — and a snapshot that crosses it can no
    longer be parsed, which is a raw spine `too_large` on the next use rather
    than a refusal. §9 makes `decide` and `fold` raise closed §8 reasons
    only, so the bound is checked here, before the seal, exactly as the other
    counters and collections are checked before they are advanced.
    """
    record = _project_snapshot(body)
    try:
        measured = len(protocols.serialize_canonical(
            {k: v for k, v in record.items()
             if k != protocols.CONTENT_HASH_FIELD}
        ))
    except protocols.ProtocolError as refusal:
        raise _refuse("snapshot_divergence", "/", code=refusal.code) from None
    if measured + _DIGEST_MEMBER_BYTES > protocols.MAX_ARTIFACT_BYTES:
        raise _refuse("snapshot_divergence", "/")
    return _seal(record)


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
#:
#: U-W3 §11.4 makes recomputing this an OBLIGATION, not an option: the eight
#: additive snapshot members of §11.4 are each carried here at their frozen
#: bound — the five counters at `INT_MAX`, the two optional state strings at
#: their longest closed member, and the optional digest at its pattern width —
#: so `_require_admissible_size` still guarantees that an admitted instance
#: can reach ANY state, open every attempt its budget allows and record every
#: checkpoint its bounds allow, without ever failing `_seal_snapshot` at
#: `MAX_ARTIFACT_BYTES`.
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
        "attempt_no": protocols.INT_MAX,
        "attempts_used": protocols.INT_MAX,
        "attempt_budget": protocols.INT_MAX,
        "last_checkpoint_seq": protocols.INT_MAX,
        "checkpoint_count": protocols.INT_MAX,
        "attempt_state": max(WORKFLOW_ATTEMPT_STATES, key=len),
        "compensation_state": max(WORKFLOW_COMPENSATION_STATES, key=len),
        "restored_checkpoint_sha256": "0" * 64,
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

def _policy_for(policy_version: int) -> tuple:
    """`(version, states, matrix)` for a supported version, else refuse.

    The states come back WITH the matrix so every lookup indexes its own
    version's tuple: a policy-v1 snapshot is judged by v1's 13x13 table and
    v1's 13-member order, whatever `WORKFLOW_STATES` has grown to (§5.1).
    """
    for entry in _POLICY_MATRICES:
        if entry[0] == policy_version:
            return entry
    raise _refuse("policy_version_unsupported", "/policy_version")


def _cell(policy, source: str, target: str) -> tuple:
    _version, states, matrix = policy
    if source not in states or target not in states:
        # A state this version's tuple does not carry has no cell at all, and
        # asking for one is not a lookup failure to raise through: it is an
        # illegal transition under that version.
        return ()
    return matrix[states.index(source)][states.index(target)]


def _require_edge(policy, source: str, target: str, driver: str, *,
                  receipt: bool):
    """Refuse unless `driver` may traverse (source -> target) under `policy`."""
    cell = _cell(policy, source, target)
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
    # U-W3 §9.2: the key set widens under policy v2 from `("queue_route",)`.
    # `restore_checkpoint_id` stays OPTIONAL, so a v1 payload is byte-legal.
    ("request_dispatch", ("queue_route", "restore_checkpoint_id"), ()),
    ("revoke_dispatch", (), ()),
    ("request_cancel", (), ()),
    ("record_queue_receipt", ("receipt_document",), ("receipt_document",)),
    ("record_result", ("result_document",), ("result_document",)),
    # U-W3's four verbs. `policy_version` is an INTEGER, so it is declared
    # allowed-but-not-required here (the required list is the document list,
    # which this table type-checks as objects) and its presence and type are
    # checked by its own handler.
    ("adopt_policy_version", ("policy_version",), ()),
    ("record_checkpoint", ("checkpoint_document",), ("checkpoint_document",)),
    ("record_restore", ("restore_document",), ("restore_document",)),
    ("record_compensation", ("compensation_document",),
     ("compensation_document",)),
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

#: Policy version 1's snapshot member set, FROZEN VERBATIM as history.
#:
#: This freeze is not decoration; it is load-bearing, and for a reason the
#: record's own `/v1` schema string hides: the snapshot record's digest is
#: PERSISTED, in `workflows.content_sha256`, and `workflow_store` compares it
#: against the rebuilt snapshot's digest on EVERY command and in `verify`.
#: `_seal` digests the whole body, so ANY added member changes the digest of
#: every workflow — including workflows admitted, sealed and stored before
#: U-W3 existed. Widening the set unconditionally would make every
#: pre-migration workflow refuse `snapshot_divergence` on its next command and
#: read as tampered, while the 6→7 migration is forbidden to re-stamp it and
#: `verify` is forbidden to repair it.
#:
#: So the member set is policy-version conditional, exactly as the transition
#: matrix is (§5.1's `_POLICY_MATRICES` trade): a policy-v1 workflow seals
#: byte-identically forever, and `adopt_policy_version` — which consumes a
#: revision and rewrites the row through the C14 compare-and-swap — is the one
#: legitimate re-seal boundary.
_V1_SNAPSHOT_KEYS = (
    "schema", "workflow_id", "task_id", "work_spec_sha256", "report_sha256",
    "snapshot_sha256", "registry_version", "compile_status",
    "work_spec_document", "report_document", "state", "revision",
    "policy_version", "approval_required", "admission_approval_satisfied",
    "dispatch_intent_id", "cancel_intent_id", "runtime_task_uuid",
    "queue_route", "intent_seq", "revoked_intent_ids", "resolved_intent_ids",
    "last_seq", "last_wait_entry_seq", "last_runtime_approval_seq",
    protocols.CONTENT_HASH_FIELD,
)

#: U-W3 §11.4's eight additive members. Every one is a pure function of the
#: HISTORY — of what the history actually recorded — and none is read from a
#: column. The schema string stays `/v1` (§12.3): the snapshot is a private
#: projection with one producer and one consumer inside this repository,
#: re-derived on every command rather than exchanged across a boundary.
_V2_SNAPSHOT_MEMBERS = (
    "attempt_no", "attempt_state", "attempts_used", "attempt_budget",
    "last_checkpoint_seq", "checkpoint_count", "compensation_state",
    "restored_checkpoint_sha256",
)

_V2_SNAPSHOT_KEYS = (
    _V1_SNAPSHOT_KEYS[:-1] + _V2_SNAPSHOT_MEMBERS + (
        protocols.CONTENT_HASH_FIELD,
    )
)

_POLICY_SNAPSHOT_KEYS = (
    (1, _V1_SNAPSHOT_KEYS),
    (2, _V2_SNAPSHOT_KEYS),
)


def _snapshot_keys_for(policy_version) -> tuple:
    for version, keys in _POLICY_SNAPSHOT_KEYS:
        if version == policy_version:
            return keys
    raise _refuse("policy_version_unsupported", "/policy_version")


def _project_snapshot(body: dict) -> dict:
    """Restrict a working snapshot to its OWN policy version's member set.

    `decide` and `fold` both work on a body carrying every member, so the
    handlers stay total whatever version they are judging; this is where the
    body becomes the record that gets sealed and whose digest is stored.
    """
    keys = _snapshot_keys_for(body.get("policy_version"))
    return {key: body[key] for key in keys if key in body}


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
    # The member set is policy-version conditional, so the version is read
    # first — defensively, because it is untrusted like every other member —
    # and an unsupported one refuses before any member is judged against the
    # wrong shape.
    version = fresh.get("policy_version")
    if (
        not isinstance(version, int)
        or isinstance(version, bool)
        or version < 1
    ):
        raise _refuse("snapshot_divergence", "/policy_version")
    if set(fresh) != set(_snapshot_keys_for(version)):
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
        # Judged against the state tuple of the snapshot's OWN version, so a
        # policy-v1 snapshot cannot claim the fourteenth state.
        ("state", fresh["state"] in _policy_for(version)[1]),
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
    if version >= 2:
        # U-W3 §11.4's eight additive members, judged to the same standard as
        # the landed ones: closed vocabulary or bounded integer, `None` only
        # where the lifecycle genuinely has no value yet.
        checks += (
            ("attempt_no", fresh["attempt_no"] is None
             or _count(fresh["attempt_no"], 1)),
            ("attempt_state", fresh["attempt_state"] is None
             or fresh["attempt_state"] in WORKFLOW_ATTEMPT_STATES),
            ("attempts_used", _count(fresh["attempts_used"], 0)),
            ("attempt_budget", fresh["attempt_budget"] is None
             or _count(fresh["attempt_budget"], 1)),
            ("last_checkpoint_seq", _count(fresh["last_checkpoint_seq"], 0)),
            ("checkpoint_count", _count(fresh["checkpoint_count"], 0)),
            ("compensation_state", fresh["compensation_state"] is None
             or fresh["compensation_state"] in WORKFLOW_COMPENSATION_STATES),
            ("restored_checkpoint_sha256",
             _optional(fresh["restored_checkpoint_sha256"], _SHA256_RE)),
        )
    for name, ok in checks:
        if not ok:
            raise _refuse("snapshot_divergence", f"/{name}")

    # The §14.1 structural CHECKs, enforced here too so the reducer never acts
    # on a projection the storage layer would refuse.
    state = fresh["state"]
    if fresh["dispatch_intent_id"] is not None and state not in _DISPATCHABLE_STATES.get(
        version, ("validated",)
    ):
        # `retrying` joins `validated` UNDER POLICY V2 ONLY, because a retry IS
        # a dispatch issued from `retrying` (§11.2 widens the storage CHECK
        # identically). A policy-v1 snapshot keeps reading `{validated}`
        # verbatim, exactly as §22 A2 freezes it.
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
    if version >= 2:
        counters += (
            ("attempts_used", fresh["attempts_used"]),
            ("last_checkpoint_seq", fresh["last_checkpoint_seq"]),
            ("checkpoint_count", fresh["checkpoint_count"]),
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


def _admit(command: dict, facts: ShellFacts) -> WorkflowDecision:
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
        **_FRESH_RECOVERY_MEMBERS,
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
# Checkpoints (U-W3 §8) and restore facts (U-W3 §9)
#
# Both records are produced OUTSIDE Agentic OS and are UNTRUSTED input. AOS
# validates the closed shape, the bounds and the bindings; it never reads a
# checkpoint payload key, never interprets a value, and never renders one.

#: The protocol's frozen attempt ceiling, READ AS DATA from the shipped
#: `beast.result-envelope/v1` schema rather than typed again. §12.1 freezes
#: `10` in five places and forbids a sixth ceiling CONSTANT; this is not a
#: sixth number, it is the first one.
_PROTOCOL_ATTEMPT_CEILING = protocols.REGISTRY[
    "beast.result-envelope/v1"
].schema["properties"]["attempt"]["maximum"]

#: A quarter of the canonical artifact bound, so the envelope around the
#: payload and the sealed digest still fit inside `MAX_ARTIFACT_BYTES` with
#: margin. Derived headroom, not a tuned number.
MAX_CHECKPOINT_PAYLOAD_BYTES = protocols.MAX_ARTIFACT_BYTES // 4

#: Per-attempt and per-workflow checkpoint bounds (§8.2). The workflow bound
#: is the per-attempt bound times the protocol's attempt ceiling, so no third
#: number is introduced.
MAX_CHECKPOINTS_PER_ATTEMPT = 8
MAX_CHECKPOINTS_PER_WORKFLOW = (
    MAX_CHECKPOINTS_PER_ATTEMPT * _PROTOCOL_ATTEMPT_CEILING
)

#: The states in which a workflow attempt is open AND a runtime task is live,
#: which is exactly where a checkpoint can be produced (§8.4). `waiting_input`
#: and `paused` have no live runtime fact producer (§20 item 9) and are named
#: here for TOTALITY, so the gate is closed and no future producer needs a new
#: policy version — not as exercised paths.
_CHECKPOINTABLE_STATES = (
    "running", "waiting_input", "waiting_approval", "paused",
)

_CHECKPOINT_KEYS = frozenset((
    "schema", "checkpoint_id", "workflow_id", "work_spec_sha256",
    "attempt_no", "checkpoint_seq", "runtime_task_uuid", "payload",
    "created_at", "trace", protocols.CONTENT_HASH_FIELD,
))
_CHECKPOINT_REQUIRED_KEYS = (
    "schema", "checkpoint_id", "workflow_id", "work_spec_sha256",
    "attempt_no", "checkpoint_seq", "runtime_task_uuid", "payload",
    "created_at", protocols.CONTENT_HASH_FIELD,
)

_RESTORE_FACT_KEYS = frozenset((
    "schema", "workflow_id", "work_spec_sha256", "checkpoint_id",
    "checkpoint_sha256", "from_attempt_no", "into_attempt_no", "restored_by",
    "restored_at", "trace", protocols.CONTENT_HASH_FIELD,
))
_RESTORE_FACT_REQUIRED_KEYS = (
    "schema", "workflow_id", "work_spec_sha256", "checkpoint_id",
    "checkpoint_sha256", "from_attempt_no", "into_attempt_no", "restored_by",
    "restored_at", protocols.CONTENT_HASH_FIELD,
)


def _bounded_attempt(value) -> bool:
    """An attempt ordinal inside the PROTOCOL's frozen ceiling. The
    artifact's own budget is the tighter live bound and is applied by the
    handler that knows which workflow it is judging."""
    return _count(value, 1) and value <= _PROTOCOL_ATTEMPT_CEILING


def _checkpoint_payload_bytes(payload) -> int:
    """The canonical length of a checkpoint payload, or a refusal.

    The payload is an OPAQUE canonical object: this measures it and never
    reads a key. A payload the spine cannot serialize at all is malformed,
    not an exception to let escape.
    """
    if not isinstance(payload, dict):
        raise _refuse("checkpoint_malformed", "/payload")
    try:
        return len(protocols.serialize_canonical(payload))
    except protocols.ProtocolError as refusal:
        raise _refuse(
            "checkpoint_malformed", "/payload", code=refusal.code
        ) from None


def _verify_checkpoint(fresh) -> dict:
    """The §8.3 closed record, its size bound and its secret scan.

    Already canonical and fresh: `_verify_command` round-tripped the whole
    envelope on intake. Patterns and bounds REUSE the landed compiled gates
    exactly; U-W3 adds no new pattern constant.
    """
    if not isinstance(fresh, dict):
        raise _refuse("checkpoint_malformed", "/")
    if set(fresh) - _CHECKPOINT_KEYS:
        raise _refuse("checkpoint_malformed", "/")
    for key in _CHECKPOINT_REQUIRED_KEYS:
        if key not in fresh:
            raise _refuse("checkpoint_malformed", f"/{key}")
    if fresh["schema"] != WORKFLOW_CHECKPOINT_SCHEMA:
        # An unknown `/vN` refuses here; there is no default-version
        # resolution, and any additive member would require a `/v2` and a new
        # policy version (§8.2).
        raise _refuse("checkpoint_malformed", "/schema")
    checks = (
        ("checkpoint_id", _text(fresh["checkpoint_id"], _UUID_RE)),
        ("workflow_id", _text(fresh["workflow_id"], _WORKFLOW_ID_RE)),
        ("work_spec_sha256", _text(fresh["work_spec_sha256"], _SHA256_RE)),
        ("attempt_no", _bounded_attempt(fresh["attempt_no"])),
        ("checkpoint_seq",
         _count(fresh["checkpoint_seq"], 1)
         and fresh["checkpoint_seq"] <= MAX_CHECKPOINTS_PER_ATTEMPT),
        ("runtime_task_uuid", _text(fresh["runtime_task_uuid"], _UUID_RE)),
        ("created_at", _is_real_instant(fresh["created_at"])),
    )
    for name, ok in checks:
        if not ok:
            raise _refuse("checkpoint_malformed", f"/{name}")
    if "trace" in fresh and not _trace_ok(fresh["trace"]):
        raise _refuse("checkpoint_malformed", "/trace")

    measured = _checkpoint_payload_bytes(fresh["payload"])
    if measured > MAX_CHECKPOINT_PAYLOAD_BYTES:
        raise _refuse(
            "checkpoint_malformed", "/payload",
            payload_bytes=measured, limit=MAX_CHECKPOINT_PAYLOAD_BYTES,
        )
    # A secret-shaped payload is REFUSED at ingest and never stored — not
    # redacted, because a redacted checkpoint is an unrestorable lie, and not
    # stored-then-warned, because that would put a plaintext credential in
    # `aos.db`. The refusal names the schema-safe path only, never the value
    # and never which detector fired on which byte.
    if secretscan.scan_secrets(
        protocols.serialize_canonical(fresh["payload"]).decode("utf-8")
    ):
        raise _refuse("checkpoint_malformed", "/payload")
    if not _digest_matches(fresh):
        raise _refuse(
            "checkpoint_malformed", f"/{protocols.CONTENT_HASH_FIELD}"
        )
    return fresh


def _verify_restore_fact(fresh) -> dict:
    """The §9.4 closed record and its self-digest."""
    if not isinstance(fresh, dict):
        raise _refuse("restore_fact_malformed", "/")
    if set(fresh) - _RESTORE_FACT_KEYS:
        raise _refuse("restore_fact_malformed", "/")
    for key in _RESTORE_FACT_REQUIRED_KEYS:
        if key not in fresh:
            raise _refuse("restore_fact_malformed", f"/{key}")
    if fresh["schema"] != WORKFLOW_RESTORE_FACT_SCHEMA:
        raise _refuse("restore_fact_malformed", "/schema")
    checks = (
        ("workflow_id", _text(fresh["workflow_id"], _WORKFLOW_ID_RE)),
        ("work_spec_sha256", _text(fresh["work_spec_sha256"], _SHA256_RE)),
        ("checkpoint_id", _text(fresh["checkpoint_id"], _UUID_RE)),
        ("checkpoint_sha256", _text(fresh["checkpoint_sha256"], _SHA256_RE)),
        ("from_attempt_no", _bounded_attempt(fresh["from_attempt_no"])),
        ("into_attempt_no", _bounded_attempt(fresh["into_attempt_no"])),
        ("restored_by", _text(fresh["restored_by"], _PROVENANCE_RE)),
        ("restored_at", _is_real_instant(fresh["restored_at"])),
    )
    for name, ok in checks:
        if not ok:
            raise _refuse("restore_fact_malformed", f"/{name}")
    if "trace" in fresh and not _trace_ok(fresh["trace"]):
        raise _refuse("restore_fact_malformed", "/trace")
    if not _digest_matches(fresh):
        raise _refuse(
            "restore_fact_malformed", f"/{protocols.CONTENT_HASH_FIELD}"
        )
    return fresh


# ---------------------------------------------------------------------------
# Intent builders (§13.1)

def _intent_schema(snapshot: dict) -> str:
    """`/v2` for a policy-v2 workflow, `/v1` for every earlier one (§12.3).

    The intent is the ONE record that crosses the trust boundary as a file and
    that the adapter pins by content hash, so a widened accepted member set
    announces itself with a version rather than by surprise. The rule is per
    WORKFLOW, not per kind: one policy version, one intent version, no
    per-kind exception to reason about on the receiving side.
    """
    return (
        WORKFLOW_INTENT_V2_SCHEMA
        if snapshot["policy_version"] >= 2
        else WORKFLOW_INTENT_SCHEMA
    )


def _dispatch_intent(
    snapshot: dict, command: dict, intent_seq: int, queue_route: str,
    *, attempt_no=None, attempt_budget=None, supersedes=None,
    restore_checkpoint_id=None, restore_checkpoint_sha256=None,
) -> dict:
    body = {
        "schema": _intent_schema(snapshot),
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
    if attempt_no is not None:
        # Required members of a `/v2` dispatch (§6.4 rule 2): the enqueuer has
        # the ordinal and the budget IN FRONT OF THEM and never has to infer
        # either, and a second file for the same WorkSpec announces itself as
        # "attempt N of M" instead of looking like a duplicate first dispatch.
        body["attempt_no"] = attempt_no
        body["attempt_budget"] = attempt_budget
    if supersedes is not None:
        # Present exactly when a prior attempt bound a runtime task, so the
        # chain of runtime tasks for one WorkSpec is readable from the files
        # alone (§7.2 defence 2). It makes the landed U-W2 §22 limitation more
        # LEGIBLE; it does not claim to fix it.
        body["supersedes_runtime_task_uuid"] = supersedes
    if restore_checkpoint_id is not None:
        # A required-TOGETHER optional pair, so the file the operator carries
        # names exactly what must be restored, by digest (§9.2).
        body["restore_checkpoint_id"] = restore_checkpoint_id
        body["restore_checkpoint_sha256"] = restore_checkpoint_sha256
    if "trace" in command:
        body["trace"] = command["trace"]
    return _seal(body)


def _cancel_intent(
    snapshot: dict, command: dict, intent_seq: int, cancels_intent_id
) -> dict:
    body = {
        "schema": _intent_schema(snapshot),
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


def _compensate_intent(
    snapshot: dict, command: dict, intent_seq: int, attempt_no: int,
    failed_result_sha256: str, compensation_ref,
) -> dict:
    """The one `compensate` intent (§10.5), on the next `intent_seq`, using
    the UNCHANGED `intent_id` and `idempotency_key` formulas.

    `compensation_ref` is copied VERBATIM from the failing envelope's
    `compensation.ref` when present — an opaque reference AOS never
    dereferences, never parses, never matches and never executes.
    """
    body = {
        "schema": WORKFLOW_INTENT_V2_SCHEMA,
        "intent_kind": "compensate",
        "intent_id": _intent_id(snapshot["work_spec_sha256"], intent_seq),
        "workflow_id": snapshot["workflow_id"],
        "work_spec_sha256": snapshot["work_spec_sha256"],
        "attempt_no": attempt_no,
        "failed_result_sha256": failed_result_sha256,
        "idempotency_key": _idempotency_key(
            snapshot["work_spec_sha256"], intent_seq
        ),
        "queue_route": snapshot["queue_route"],
        "requested_at": command["created_at"],
    }
    if compensation_ref is not None:
        body["compensation_ref"] = compensation_ref
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
    policy_version=None,
) -> dict:
    return _seal({
        "schema": WORKFLOW_EVENT_SCHEMA,
        "event": event,
        "workflow_id": snapshot["workflow_id"],
        "work_spec_sha256": snapshot["work_spec_sha256"],
        "seq": seq,
        "revision": revision,
        "policy_version": (
            snapshot["policy_version"] if policy_version is None
            else policy_version
        ),
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

def _handle_validate(snapshot, command, policy, payload, facts):
    _require_edge(policy, snapshot["state"], "validated", "cmd:validate",
                  receipt=False)
    return {"state": "validated"}, [("workflow_validated", "validated", {})], None


def _handle_request_approval(snapshot, command, policy, payload, facts):
    _require_edge(policy, snapshot["state"], "awaiting_approval",
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


def _handle_record_approval(snapshot, command, policy, payload, facts):
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
        _require_edge(policy, state, "validated", "apr:record_approval",
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


def _budget_of(snapshot: dict) -> int:
    """The one budget rule (§6.1): the ADMITTED artifact's own
    `retry.max_attempts`, defaulting to 1 when it declares no `retry` block.

    Read from the digest-bound, admission-immutable artifact every time, never
    from a counter and never from anything the runtime reported, so the budget
    cannot drift and AOS never accepts a budget it did not derive itself.
    """
    return snapshot["work_spec_document"].get("retry", {}).get(
        "max_attempts", 1
    )


#: Where a dispatch may be requested, per policy version. Under v2 `retrying`
#: joins `validated`: a retry IS a dispatch issued from `retrying` (§13.1),
#: which is why there is no retry verb and no second way to do one thing.
_DISPATCHABLE_STATES = {1: ("validated",), 2: ("validated", "retrying")}


def _dispatchable(policy) -> tuple:
    return _DISPATCHABLE_STATES.get(policy[0], ("validated",))


def _handle_request_dispatch(snapshot, command, policy, payload, facts):
    if snapshot["state"] not in _dispatchable(policy):
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

    version = policy[0]
    attempt_no = attempt_budget = supersedes = None
    restore_id = restore_digest = None
    event_payload = {}
    if version >= 2:
        # RESERVATION, not consumption (§6.2): the ordinal is stated so the
        # enqueuer can read it, and nothing is written to the attempt ledger.
        # A queue rejection or an operator revocation therefore materialises
        # nothing and burns no budget slot — which is what keeps a
        # default-budget-1 workflow from being stranded by one adapter error.
        attempt_budget = _budget_of(snapshot)
        if snapshot["attempts_used"] >= attempt_budget:
            raise _refuse(
                "attempt_budget_exhausted", "/attempts_used",
                attempts_used=snapshot["attempts_used"],
                budget=attempt_budget,
            )
        attempt_no = snapshot["attempts_used"] + 1
        supersedes = snapshot["runtime_task_uuid"]
        restore_id = payload.get("restore_checkpoint_id")
        if restore_id is not None:
            restore_digest = _resolve_restore(
                snapshot, facts, restore_id, attempt_no
            )
        event_payload["attempt_no"] = attempt_no
        event_payload["attempt_budget"] = attempt_budget
    elif "restore_checkpoint_id" in payload:
        # The payload key exists only under policy v2 (§9.2). Offering it to a
        # v1 workflow is a payload this verb does not accept there.
        raise _refuse("payload_malformed", "/payload/restore_checkpoint_id")

    intent_seq = snapshot["intent_seq"] + 1
    intent = _dispatch_intent(
        snapshot, command, intent_seq, queue_route,
        attempt_no=attempt_no, attempt_budget=attempt_budget,
        supersedes=supersedes,
        restore_checkpoint_id=restore_id,
        restore_checkpoint_sha256=restore_digest,
    )
    if restore_id is not None:
        event_payload["restore_checkpoint_id"] = restore_id
        event_payload["restore_checkpoint_sha256"] = restore_digest
    return (
        {
            "dispatch_intent_id": intent["intent_id"],
            "queue_route": queue_route,
            "intent_seq": intent_seq,
            "attempt_budget": attempt_budget,
        },
        [(
            "dispatch_requested",
            None,
            {
                "intent_id": intent["intent_id"],
                "idempotency_key": intent["idempotency_key"],
                "queue_route": queue_route,
                **event_payload,
            },
        )],
        intent,
    )


def _resolve_restore(snapshot, facts, restore_id, into_attempt_no) -> str:
    """The §9.3 eligibility predicate for a restore REQUESTED in a dispatch.

    The reducer checks only that the value is a UUID; whether it names a
    stored, eligible checkpoint is a STORED-ROW judgment, so the shell
    resolved it before `decide` and handed the resolved digest and attempt in
    through `ShellFacts` (§1.2 row S7). An id the shell could not resolve
    arrives as an absent pair and refuses `checkpoint_unknown` there, never
    here — this function judges the resolved facts, it does not look anything
    up.
    """
    if not _text(restore_id, _UUID_RE):
        raise _refuse("payload_malformed", "/payload/restore_checkpoint_id")
    digest = facts.checkpoint_sha256
    from_attempt = facts.checkpoint_attempt_no
    if digest is None or from_attempt is None:
        raise _refuse("checkpoint_unknown", "/payload/restore_checkpoint_id")
    _require_restorable(snapshot, from_attempt, into_attempt_no,
                        ("retrying",))
    return digest


def _require_restorable(snapshot, from_attempt, into_attempt_no,
                        legal_states) -> None:
    """§9.3 conjuncts 3, 4 and 5. Conjuncts 1 and 2 are the shell's: an id it
    cannot find is `checkpoint_unknown`, and a stored digest that does not
    recompute is never handed over at all.

    Restoration is INELIGIBLE in `compensating` and in every terminal state:
    compensation undoes work, restoration resumes it, and allowing both would
    let a workflow resume from a state whose effects it had just undone.
    """
    if snapshot["policy_version"] < 2:
        raise _refuse("checkpoint_ineligible", "/policy_version")
    if snapshot["state"] not in legal_states:
        raise _refuse("checkpoint_ineligible", "/state")
    if not _count(from_attempt, 1) or from_attempt >= into_attempt_no:
        # You restore FROM a previous attempt, never from the one you are in.
        raise _refuse("checkpoint_ineligible", "/from_attempt_no")


def _handle_revoke_dispatch(snapshot, command, policy, payload, facts):
    if snapshot["state"] not in _dispatchable(policy):
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


def _handle_request_cancel(snapshot, command, policy, payload, facts):
    state = snapshot["state"]
    local = "cmd:request_cancel" in _cell(policy, state, "cancelled")
    if local:
        # AOS is the source of truth until it has OBSERVED queue acceptance.
        updates = {
            "state": "cancelled",
            "dispatch_intent_id": None,
            "cancel_intent_id": None,
            **_abandon_open_attempt(snapshot),
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


def _abandon_open_attempt(snapshot) -> dict:
    """§5.3.5: entering `cancelled` closes an attempt that is still open as
    `abandoned`. The work never concluded and never will, so the row closes as
    neither `succeeded` nor `failed` — the fourth attempt state exists for
    exactly this moment, and `fold` derives the same value from the history.
    """
    if snapshot["attempt_state"] != "open":
        return {}
    return {"attempt_state": "abandoned"}


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


def _bind_failed_receipt(snapshot, receipt):
    """The attempt a `failed` receipt closes, and the fence around it.

    ONE RULE for every optional corroborating uuid (§22 A24), the same one
    §5.3.3 and §10.8 apply to a result envelope: a PRESENT value must equal
    the binding recorded for the attempt this receipt closes, and an ABSENT
    one refuses nothing. The receipt record shape stays exactly what U-W2
    §13.2 froze — `runtime_task_uuid` is not a required member of a `failed`
    receipt and the storage CHECK admits NULL, so requiring it under policy v2
    would silently break every adapter already emitting shape-legal receipts.

    The receipt does not need to NAME its attempt, because at most one attempt
    of a workflow is ever open (§6.3): WHICH attempt it closes is decided by
    the ledger, not by the document. What a present uuid adds is a
    contradiction check — and a contradiction is never silently dropped.

    The comparison target is the binding folded from the `dispatch_accepted`
    history — the event-authoritative source, of which the `workflow_attempts`
    row is the projection — so this needs no store read and adds no
    `ShellFacts` member. Returns the attempt ordinal, or `None` when this
    workflow has no attempt for the receipt to close.
    """
    reported = receipt.get("runtime_task_uuid")
    bound = snapshot["runtime_task_uuid"]
    if reported is not None and bound is not None and reported != bound:
        raise _refuse("runtime_uuid_mismatch", "/runtime_task_uuid")
    return snapshot["attempt_no"]


def _receipt_retryable(snapshot, receipt, kind: str, version: int) -> bool:
    """Does this `failed` receipt classify as `rcp:failed_retryable`?

    Under policy v1 the answer is always no — v1 has no `retrying` state and
    numbered no workflow attempt, so there is nothing to classify against.
    Under v2 the receipt must first BIND its attempt (§6.2), and then the
    §5.3.3 predicate decides: `reason.retryable == true` and `attempt_no <
    budget` and an attempt is open. A `failed` receipt arriving in
    `compensating` closes the UNDO, never opens a retry (§10.7: there is no
    compensation retry), so it is never retryable there.
    """
    if kind != "failed" or version < 2:
        return False
    attempt_no = _bind_failed_receipt(snapshot, receipt)
    if snapshot["state"] == "compensating":
        return False
    if snapshot["attempt_state"] != "open" or attempt_no is None:
        return False
    return bool(receipt["reason"]["retryable"]) and attempt_no < _budget_of(
        snapshot
    )


def _handle_record_queue_receipt(snapshot, command, policy, payload, facts):
    receipt = _verify_receipt(payload["receipt_document"])
    if receipt["workflow_id"] != snapshot["workflow_id"]:
        raise _refuse("receipt_unbound", "/workflow_id")
    if receipt["work_spec_sha256"] != snapshot["work_spec_sha256"]:
        raise _refuse("receipt_unbound", "/work_spec_sha256")

    kind = receipt["receipt_kind"]
    state = snapshot["state"]
    target = _receipt_target(kind)
    version = policy[0]
    if target is None:
        # `rejected` is a queue's refusal to ADMIT an intent: stateless, and
        # legal only where a dispatch intent can be outstanding — which under
        # policy v2 is `retrying` as well as `validated`, because a retry is a
        # dispatch issued from `retrying` and the queue may refuse that one
        # exactly as it may refuse the first.
        if state not in _dispatchable(policy):
            raise _refuse("receipt_out_of_order", "/receipt_kind")
    else:
        # The landed gate runs FIRST and unchanged, so state legality still
        # outranks binding: a `failed` receipt in a state that admits none is
        # `receipt_out_of_order`, exactly as it was under v1.
        _require_edge(policy, state, target, f"rcp:{kind}", receipt=True)

    retryable = _receipt_retryable(snapshot, receipt, kind, version)
    if retryable:
        # `rcp:failed_retryable` is a DIFFERENT driver from `rcp:failed`, so
        # it is required against its own cell rather than the terminal one.
        target = "retrying"
        _require_edge(policy, state, target, "rcp:failed_retryable",
                      receipt=True)

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
        accepted_payload = {
            **base_payload,
            "intent_id": intent_id,
            "idempotency_key": receipt["idempotency_key"],
            "runtime_task_uuid": reported_uuid,
        }
        if version >= 2:
            # OPENED / CONSUMED (§6.2): the ordinal is assigned here, not at
            # reservation, so a queue rejection or an operator revocation
            # never burns a budget slot. It also keeps `attempt_no <= budget
            # <= 10` always true, which is what makes the reported `attempt`
            # satisfiable against the shipped envelope's 1..10 bound.
            attempt_no = snapshot["attempts_used"] + 1
            if snapshot["dispatch_intent_id"] is None:
                # No v2 reservation to number this acceptance from. The landed
                # code's exact meaning applies: the receipt binds no attempt of
                # this workflow that AOS authoritatively recorded. NO ORDINAL
                # IS FABRICATED to make the acceptance succeed (§5.5 item 5).
                raise _refuse("receipt_unbound", "/intent_id")
            if attempt_no > _budget_of(snapshot):
                raise _refuse("attempt_budget_exhausted", "/attempts_used")
            # §6.5, ONE RUNTIME TASK, ONE WORKFLOW ATTEMPT. A retry is a new
            # runtime task by construction (§7.2), so an `accepted` receipt
            # offering a uuid this workflow already bound is evidence of a
            # reused or replayed task, not of a new attempt. The prior binding
            # is the folded one, so the check is event-authoritative and needs
            # no store read; `UNIQUE(workflow_id, runtime_task_uuid)` is the
            # storage backstop behind it.
            if (
                snapshot["runtime_task_uuid"] is not None
                and reported_uuid == snapshot["runtime_task_uuid"]
            ):
                raise _refuse("runtime_uuid_mismatch", "/runtime_task_uuid")
            # The artifact may PRE-DECLARE the runtime task uuid, and under
            # v1 that declaration bound every acceptance. It cannot bind a
            # retry: a retry is a NEW runtime task by construction, so a
            # declaration naming one task could never be satisfied twice.
            # Frozen: the declaration binds ATTEMPT 1 ONLY (§6.5).
            if attempt_no == 1 and declared_uuid is not None and (
                reported_uuid != declared_uuid
            ):
                raise _refuse("runtime_uuid_mismatch", "/runtime_task_uuid")
            accepted_payload["attempt_no"] = attempt_no
            updates["attempt_no"] = attempt_no
            updates["attempt_state"] = "open"
            updates["attempts_used"] = attempt_no
            updates["attempt_budget"] = _budget_of(snapshot)
            updates["last_checkpoint_seq"] = 0
        elif declared_uuid is not None and reported_uuid != declared_uuid:
            # The runtime mints the task UUID at acceptance; a pre-declared
            # value must match, and every later receipt must repeat it.
            raise _refuse("runtime_uuid_mismatch", "/runtime_task_uuid")
        updates["state"] = "scheduled"
        updates["runtime_task_uuid"] = reported_uuid
        return (
            updates,
            [("dispatch_accepted", "scheduled", accepted_payload)],
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
            **_abandon_open_attempt(snapshot),
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
        reason_payload = {
            **base_payload,
            "reason_code": receipt["reason"]["code"],
            "retryable": receipt["reason"]["retryable"],
        }
        if retryable:
            return (
                {
                    "state": "retrying",
                    "attempt_state": "failed",
                    "cancel_intent_id": None,
                },
                [(
                    "attempt_failed",
                    "retrying",
                    {
                        **reason_payload,
                        "attempt_no": snapshot["attempt_no"],
                        "attempt_budget": _budget_of(snapshot),
                        "attempts_used": snapshot["attempts_used"],
                    },
                )],
                None,
            )
        if version >= 2 and state == "compensating":
            # The undo episode ends because the runtime reported the task it
            # was bound to failed. A distinct event name, so "the work failed"
            # and "the undo failed" are never confused in the history; it
            # carries no `compensation_state`, because a queue receipt reports
            # about the TASK, not about the undo (§5.5).
            return (
                {
                    "state": "failed",
                    "compensation_state": "failed",
                    "dispatch_intent_id": None,
                    "cancel_intent_id": None,
                },
                [(
                    "compensation_failed",
                    "failed",
                    {**reason_payload, "attempt_no": snapshot["attempt_no"]},
                )],
                None,
            )
        updates = {
            "state": "failed",
            "dispatch_intent_id": None,
            "cancel_intent_id": None,
        }
        if version >= 2:
            updates["attempt_state"] = "failed"
            reason_payload["attempt_no"] = snapshot["attempt_no"]
            reason_payload["attempts_used"] = snapshot["attempts_used"]
        return updates, [("workflow_failed", "failed", reason_payload)], None

    return (
        {"state": target},
        [(
            _receipt_event(kind),
            target,
            {**base_payload, "runtime_task_uuid": reported_uuid},
        )],
        None,
    )


def _handle_record_result(snapshot, command, policy, payload, facts):
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
    version = policy[0]
    compensation = _compensation_state(envelope)
    if version >= 2:
        # The universal attempt fence (§5.3.3): the `attempt` integer alone
        # selects and binds the attempt, and it must equal the OPEN one. An
        # attempt number that names nothing is not accounting.
        if envelope["attempt"] != snapshot["attempt_no"] or snapshot[
            "attempt_state"
        ] != "open":
            raise _refuse("attempt_mismatch", "/attempt")
        # Optional corroboration, never a selector: a PRESENT value must match
        # the recorded binding, an ABSENT one refuses nothing, and a matching
        # one grants no additional authority (§5.3.3).
        _require_uuid_corroboration(snapshot, envelope)
    if outcome not in ("success", "fail"):
        # `partial` and `unknown` are honest statements of ignorance and are
        # deliberately NOT activated under policy v2: U-W3 cannot know WHAT
        # was partially done, and turning a producer's uncertainty into an AOS
        # claim about the world is the one rule this architecture never bends.
        raise _refuse("result_outcome_inconclusive", "/outcome", outcome=outcome)

    if version >= 2 and compensation in ("applied", "failed"):
        # A FIRST result cannot report a CONCLUSION. Checked AFTER the outcome
        # gate, so §10.3's `partial`/`unknown` row — "any" compensation state —
        # keeps selecting `result_outcome_inconclusive` (§22 A27).
        raise _refuse("compensation_state_inconsistent", "/compensation/state")

    if outcome == "fail":
        if version >= 2 and compensation == "pending":
            # Compensation OUTRANKS retry, and the retry predicate is not even
            # consulted: undoing a partial effect before re-running is the only
            # safe order, and retrying over an un-undone effect is the hazard
            # the whole model exists to prevent (§10.3).
            return _enter_compensation(snapshot, command, policy, envelope,
                                       result_sha256)
        if version >= 2 and _result_retryable(snapshot, envelope):
            attempt_no = snapshot["attempt_no"]
            _require_edge(policy, "running", "retrying", "res:fail_retryable",
                          receipt=False)
            return (
                {
                    "state": "retrying",
                    "attempt_state": "failed",
                    "cancel_intent_id": None,
                },
                [(
                    "attempt_failed",
                    "retrying",
                    {
                        "attempt_no": attempt_no,
                        "attempt_budget": _budget_of(snapshot),
                        "attempts_used": snapshot["attempts_used"],
                        "result_sha256": result_sha256,
                    },
                )],
                None,
            )
        _require_edge(policy, "running", "failed", "res:fail", receipt=False)
        failed_payload = {
            "result_sha256": result_sha256,
            "attempt": envelope["attempt"],
            "outcome": outcome,
        }
        if version >= 2:
            failed_payload["attempt_no"] = snapshot["attempt_no"]
            failed_payload["attempts_used"] = snapshot["attempts_used"]
        return (
            {
                "state": "failed",
                "attempt_state": "failed",
                "dispatch_intent_id": None,
                "cancel_intent_id": None,
            },
            [("workflow_failed", "failed", failed_payload)],
            None,
        )

    if version >= 2 and compensation == "pending":
        # A success that needs undoing is not an honest report.
        raise _refuse("result_inconsistent", "/compensation/state")
    if envelope["retryable"]:
        # A claim of success that asks to be retried is not an honest report.
        raise _refuse("result_inconsistent", "/retryable")
    _require_edge(policy, "running", "succeeded", "res:success", receipt=False)

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
            "attempt_state": "succeeded",
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


def _compensation_state(envelope: dict):
    """The envelope's optional `compensation.state`, or `None`.

    `beast.result-envelope/v1` ships `compensation` as an optional object
    whose only required member is `state`, so the document has already been
    spine-validated by the time this reads it: a present block has a `state`
    from the shipped four-member enum, and there is nothing here to guess.
    """
    block = envelope.get("compensation")
    if not isinstance(block, dict):
        return None
    state = block.get("state")
    return state if isinstance(state, str) else None


def _require_uuid_corroboration(snapshot, envelope) -> None:
    """The §5.3.3 / §10.8 rule for a result or compensation envelope.

    `beast.result-envelope/v1` ships `runtime_task_uuid` as an OPTIONAL
    property, so U-W3 treats it as corroborating evidence and never as a
    selector: a PRESENT value must equal the recorded binding of the attempt
    the envelope names, an ABSENT one refuses nothing and is never replaced by
    a default or an inferred value, and a matching one grants no additional
    authority. A present contradiction is never silently dropped — ignoring
    evidence that disagrees with the ledger is the same class of error as
    fabricating evidence that agrees with it.
    """
    reported = envelope.get("runtime_task_uuid")
    if reported is None:
        return
    if reported != snapshot["runtime_task_uuid"]:
        raise _refuse("runtime_uuid_mismatch", "/runtime_task_uuid")


def _result_retryable(snapshot, envelope) -> bool:
    """§5.3.3 `res:fail_retryable`: the producer asked to be retried AND the
    artifact's own budget still has room."""
    return bool(envelope["retryable"]) and snapshot[
        "attempt_no"
    ] < _budget_of(snapshot)


def _enter_compensation(snapshot, command, policy, envelope, result_sha256):
    """`running → compensating` (§10.3, §10.4), the only entry there is.

    The open attempt closes `failed` with the FAILING result's digest
    preserved as the authoritative compensation trigger, and exactly one
    `compensate` intent is emitted. Compensation authority is this verified
    envelope and nothing else: no tool manifest, no skill manifest, no agent
    passport, no compile-report finding and no `recovery.action` reaches this
    decision, because no U-W3 code path reads one.
    """
    _require_edge(policy, "running", "compensating", "res:compensable",
                  receipt=False)
    block = envelope.get("compensation")
    reference = block.get("ref") if isinstance(block, dict) else None
    intent_seq = snapshot["intent_seq"] + 1
    attempt_no = snapshot["attempt_no"]
    intent = _compensate_intent(
        snapshot, command, intent_seq, attempt_no, result_sha256, reference
    )
    event_payload = {
        "result_sha256": result_sha256,
        "attempt_no": attempt_no,
    }
    if reference is not None:
        event_payload["compensation_ref"] = reference
    return (
        {
            "state": "compensating",
            "attempt_state": "failed",
            "compensation_state": "pending",
            "intent_seq": intent_seq,
            "dispatch_intent_id": None,
            "cancel_intent_id": None,
        },
        [("compensation_started", "compensating", event_payload)],
        intent,
    )


def _handle_adopt_policy_version(snapshot, command, policy, payload, facts):
    """§5.2. An EXPLICIT, RECORDED, forward-only human decision.

    Stateless: it traverses no matrix cell, changes no `state`, emits exactly
    one event and consumes one revision. There is no downgrade, no `--force`,
    no batch adopt and no implicit adoption inside any other verb.
    """
    requested = payload.get("policy_version")
    if not _count(requested, 1):
        raise _refuse("payload_malformed", "/payload/policy_version")
    current = snapshot["policy_version"]
    if requested not in SUPPORTED_POLICY_VERSIONS:
        # A version this build does not ship is refused, never guessed.
        raise _refuse("policy_version_unsupported", "/payload/policy_version")
    if requested <= current:
        raise _refuse(
            "policy_version_not_upgradable", "/payload/policy_version"
        )
    _require_adoption_safe(snapshot)
    return (
        {"policy_version": requested},
        [(
            "policy_version_adopted",
            None,
            {"from_policy_version": current, "to_policy_version": requested},
        )],
        None,
    )


def _require_adoption_safe(snapshot) -> None:
    """The §5.2.1 adoption-safety predicate: A1, A2 or A3.

    The edge-superset property makes adoption TRANSITION-safe — no move that
    was legal under the old version becomes illegal under the new one. It
    establishes nothing about the attempt ledger, and that is a second,
    independent obligation: policy v2 decides retry, checkpoint, restore and
    compensation against an authoritative record of which attempt is open,
    which runtime task it bound, and how many attempts are used — a record
    policy v1 never kept.

    Every conjunct is read from the FOLDED snapshot. No `workflow_attempts`
    row is ever synthesized from historical events, no `attempt_no` is ever
    inferred, and no `--force` or `--repair` reaches around this predicate.
    A1 is the live path; A2 and A3 are stated for totality — A2 because the
    non-terminal conjunct refuses a terminal workflow first with
    `workflow_terminal`, A3 because the 6→7 migration derives no attempt row,
    so no policy-v1 workflow can hold the complete v2 history it describes.
    """
    if snapshot["state"] in TERMINAL_STATES:  # A2, unreachable: see above
        return
    pre_dispatch = (
        snapshot["runtime_task_uuid"] is None
        and snapshot["attempts_used"] == 0
        and snapshot["attempt_no"] is None
        and snapshot["dispatch_intent_id"] is None
    )
    if pre_dispatch:  # A1
        return
    raise _refuse("policy_version_not_upgradable", "/state")


def _handle_record_checkpoint(snapshot, command, policy, payload, facts):
    """§8. Store a bounded, attempt-bound execution-restoration state the
    EXECUTING SIDE produced. Stateless: it traverses no matrix cell, changes
    no `state`, and never satisfies an evidence predicate or an attempt.

    AOS never creates, derives, synthesises, edits or completes a checkpoint,
    never reads a payload key, and never renders one.
    """
    if policy[0] < 2:
        raise _refuse("illegal_transition", "/policy_version")
    document = _verify_checkpoint(payload["checkpoint_document"])
    if document["workflow_id"] != snapshot["workflow_id"]:
        raise _refuse("checkpoint_unbound", "/workflow_id")
    if document["work_spec_sha256"] != snapshot["work_spec_sha256"]:
        raise _refuse("checkpoint_unbound", "/work_spec_sha256")
    if snapshot["state"] not in _CHECKPOINTABLE_STATES:
        raise _refuse("illegal_transition", "/state")
    if (
        document["attempt_no"] != snapshot["attempt_no"]
        or snapshot["attempt_state"] != "open"
    ):
        raise _refuse("attempt_mismatch", "/attempt_no")
    if document["runtime_task_uuid"] != snapshot["runtime_task_uuid"]:
        raise _refuse("runtime_uuid_mismatch", "/runtime_task_uuid")
    # The count bounds are read from the LEDGER, not from the submitted
    # ordinal, so the ninth checkpoint of an attempt refuses its own exact
    # code rather than failing the record's 1..8 shape gate.
    if snapshot["last_checkpoint_seq"] >= MAX_CHECKPOINTS_PER_ATTEMPT:
        raise _refuse("checkpoint_limit_exceeded", "/checkpoint_seq")
    if snapshot["checkpoint_count"] >= MAX_CHECKPOINTS_PER_WORKFLOW:
        raise _refuse("checkpoint_limit_exceeded", "/checkpoint_seq")
    if document["checkpoint_seq"] != snapshot["last_checkpoint_seq"] + 1:
        # Monotone from 1 WITHIN AN ATTEMPT (§8.2). A record naming any other
        # ordinal does not describe this ledger's next checkpoint.
        raise _refuse("checkpoint_malformed", "/checkpoint_seq")
    return (
        {
            "last_checkpoint_seq": document["checkpoint_seq"],
            "checkpoint_count": snapshot["checkpoint_count"] + 1,
        },
        [(
            "checkpoint_recorded",
            None,
            {
                "checkpoint_id": document["checkpoint_id"],
                "checkpoint_sha256": protocols.content_digest(document),
                "attempt_no": document["attempt_no"],
                "checkpoint_seq": document["checkpoint_seq"],
                "payload_bytes": _checkpoint_payload_bytes(
                    document["payload"]
                ),
            },
        )],
        None,
    )


def _handle_record_restore(snapshot, command, policy, payload, facts):
    """§9.4. Record that a named, digest-bound, STORED checkpoint was loaded
    into a named attempt.

    Stateless, exactly like a runtime-scope `approval_recorded`. A
    `run_resumed` event is NEVER proof that a checkpoint was restored, and
    this event NEVER changes state: the two resumes are separate facts and
    neither is derived from the other.
    """
    if policy[0] < 2:
        raise _refuse("illegal_transition", "/policy_version")
    document = _verify_restore_fact(payload["restore_document"])
    if document["workflow_id"] != snapshot["workflow_id"]:
        raise _refuse("restore_fact_unbound", "/workflow_id")
    if document["work_spec_sha256"] != snapshot["work_spec_sha256"]:
        raise _refuse("restore_fact_unbound", "/work_spec_sha256")
    if facts.checkpoint_sha256 is None or facts.checkpoint_attempt_no is None:
        raise _refuse("checkpoint_unknown", "/checkpoint_id")
    if document["checkpoint_sha256"] != facts.checkpoint_sha256:
        raise _refuse("restore_fact_unbound", "/checkpoint_sha256")
    # The checkpoint digest alone is insufficient: it proves WHICH BYTES were
    # restored, not WHICH ATTEMPT they captured.
    if document["from_attempt_no"] != facts.checkpoint_attempt_no:
        raise _refuse("restore_fact_unbound", "/from_attempt_no")
    if (
        document["into_attempt_no"] != snapshot["attempt_no"]
        or snapshot["attempt_state"] != "open"
    ):
        raise _refuse("attempt_mismatch", "/into_attempt_no")
    _require_restorable(
        snapshot, document["from_attempt_no"], document["into_attempt_no"],
        ("scheduled", "running"),
    )
    return (
        {"restored_checkpoint_sha256": document["checkpoint_sha256"]},
        [(
            "checkpoint_restored",
            None,
            {
                "checkpoint_id": document["checkpoint_id"],
                "checkpoint_sha256": document["checkpoint_sha256"],
                "from_attempt_no": document["from_attempt_no"],
                "into_attempt_no": document["into_attempt_no"],
                "restored_by": document["restored_by"],
            },
        )],
        None,
    )


#: The §10.8 conclusion table, exhaustive over `outcome` x
#: `compensation.state`. Every cell names EXACTLY ONE code or driver, so no
#: compensation envelope reaches a decision this contract did not name.
#: `None` is an absent `compensation` block.
_COMPENSATION_CONCLUSIONS = {
    ("success", "applied"): "applied",
    ("fail", "applied"): "applied",
    ("success", "failed"): "failed",
    ("fail", "failed"): "failed",
}


def _handle_record_compensation(snapshot, command, policy, payload, facts):
    """§10.8. The conclusion of a compensation episode: exactly two outcomes.

    AOS decides the STATE; the executing side performed the ACT. This reads a
    verified `beast.result-envelope/v1` and nothing else — no manifest, no
    finding, no `recovery.action`, and no uuid decides anything.
    """
    if policy[0] < 2:
        raise _refuse("illegal_transition", "/policy_version")
    if snapshot["state"] != "compensating":
        raise _refuse("compensation_not_required", "/state")
    if snapshot["compensation_state"] != "pending":
        # A second conclusion. Unreachable while both conclusions are terminal
        # (a terminal row refuses `workflow_terminal` first), and kept as a
        # total guard rather than an assumption.
        raise _refuse("compensation_already_concluded", "/compensation_state")
    envelope = _verify_result(payload["compensation_document"], snapshot)
    result_sha256 = protocols.content_digest(envelope)
    outcome = envelope["outcome"]
    reported = _compensation_state(envelope)

    # The conclusion is bound to the attempt it concludes by a MANDATORY
    # ordinal: the compensating attempt `compensation_started` recorded. No
    # attempt is open in `compensating` — §6.2 closed it `failed` at entry —
    # so this is deliberately not the "open attempt" comparison.
    if envelope["attempt"] != snapshot["attempt_no"]:
        raise _refuse("attempt_mismatch", "/attempt")
    _require_uuid_corroboration(snapshot, envelope)
    if outcome not in ("success", "fail"):
        raise _refuse("result_outcome_inconclusive", "/outcome", outcome=outcome)
    verdict = (
        None if reported is None
        else _COMPENSATION_CONCLUSIONS.get((outcome, reported))
    )
    if verdict is None:
        # An absent block, `not_required`, or `pending`: none of them is a
        # conclusion, and each is a contradiction between the envelope and the
        # phase it claims to end.
        raise _refuse(
            "compensation_state_inconsistent", "/compensation/state"
        )

    if verdict == "failed":
        _require_edge(policy, "compensating", "failed", "cmp:failed",
                      receipt=False)
        return (
            {
                "state": "failed",
                "compensation_state": "failed",
                "dispatch_intent_id": None,
                "cancel_intent_id": None,
            },
            [(
                "compensation_failed",
                "failed",
                {
                    "attempt_no": snapshot["attempt_no"],
                    "result_sha256": result_sha256,
                    "compensation_state": reported,
                },
            )],
            None,
        )

    _require_edge(policy, "compensating", "compensated", "cmp:applied",
                  receipt=False)
    # `compensated` is gated by the SAME §12.2 evidence predicate as
    # `succeeded`, applied to the compensation envelope. One rule, one
    # existing code, no new vocabulary.
    expected = snapshot["work_spec_document"]["expected_result"]
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
            "state": "compensated",
            "compensation_state": "applied",
            "dispatch_intent_id": None,
            "cancel_intent_id": None,
        },
        [(
            "compensation_applied",
            "compensated",
            {
                "result_sha256": result_sha256,
                "compensation_state": reported,
                "attempt_no": snapshot["attempt_no"],
                # Digests, never raw refs — the landed `workflow_succeeded`
                # shape.
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
    ("adopt_policy_version", _handle_adopt_policy_version),
    ("record_checkpoint", _handle_record_checkpoint),
    ("record_restore", _handle_record_restore),
    ("record_compensation", _handle_record_compensation),
)


# ---------------------------------------------------------------------------
# The reducer (§9)

def decide(snapshot, command, facts: ShellFacts) -> WorkflowDecision:
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
    # A policy-v1 snapshot carries none of §11.4's members. The handlers are
    # written once, for one shape, so the working value gets the fresh
    # defaults and `_seal_snapshot` projects them back off before the record
    # is sealed — a v1 workflow therefore keeps sealing over exactly U-W2's
    # member set. The defaults are the honest zero, never an inference: a v1
    # history recorded no ordinal and none is invented for it (§5.5 item 5).
    state = {**_FRESH_RECOVERY_MEMBERS, **state}
    policy = _policy_for(state["policy_version"])
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
                state, fresh_command, policy, payload, facts
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
                # The adoption event is the ONE place the stamp is the NEW
                # version rather than the snapshot's prior one, so `fold`
                # reconstructs the change from the history alone (§5.2).
                policy_version=(
                    after["policy_version"]
                    if event_name == "policy_version_adopted" else None
                ),
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
#: `(minimum policy version, event, rules)`. The version axis is the same
#: shape §5.1 freezes for `_POLICY_MATRICES`, and it exists for one
#: load-bearing reason: `dispatch_accepted` MUST carry `attempt_no` under
#: policy v2 and MUST be allowed to omit it under policy v1, because policy v1
#: never numbered workflow attempts and a v1 history is correct, complete
#: history that must fold forever. A row is enforced against an event whose
#: own recorded `policy_version` is at least the row's version.
_EVENT_PAYLOAD_REQUIRED = (
    (1, "workflow_admitted", (
        ("task_id", "task"), ("report_sha256", "sha256"),
        ("snapshot_sha256", "sha256"), ("registry_version", "count"),
        ("compile_status", "status"), ("approval_required", "bool"),
    )),
    (1, "approval_recorded", (("scope", "scope"),)),
    (1, "dispatch_requested", (
        ("intent_id", "uuid"), ("queue_route", "slug"),
    )),
    (1, "dispatch_revoked", (("intent_id", "uuid"),)),
    (1, "dispatch_accepted", (
        ("intent_id", "uuid"), ("runtime_task_uuid", "uuid"),
    )),
    (2, "dispatch_accepted", (("attempt_no", "attempt"),)),
    (1, "dispatch_rejected", (("intent_id", "uuid"),)),
    (1, "cancel_requested", (("cancel_intent_id", "uuid"),)),
    (2, "policy_version_adopted", (
        ("from_policy_version", "count"), ("to_policy_version", "count"),
    )),
    (2, "attempt_failed", (
        ("attempt_no", "attempt"), ("attempt_budget", "attempt"),
        ("attempts_used", "count"),
    )),
    (2, "checkpoint_recorded", (
        ("checkpoint_id", "uuid"), ("checkpoint_sha256", "sha256"),
        ("attempt_no", "attempt"), ("checkpoint_seq", "count"),
        ("payload_bytes", "count"),
    )),
    (2, "checkpoint_restored", (
        ("checkpoint_id", "uuid"), ("checkpoint_sha256", "sha256"),
        ("from_attempt_no", "attempt"), ("into_attempt_no", "attempt"),
        ("restored_by", "provenance"),
    )),
    (2, "compensation_started", (
        ("result_sha256", "sha256"), ("attempt_no", "attempt"),
    )),
    (2, "compensation_applied", (
        ("result_sha256", "sha256"), ("attempt_no", "attempt"),
        ("compensation_state", "compensation"),
    )),
    (2, "compensation_failed", (("attempt_no", "attempt"),)),
)

#: The policy version each event NAME became available at. U-W2's seventeen
#: are available at every version; U-W3's seven exist only under policy v2.
#:
#: This is the other half of the version axis, and it is load-bearing: without
#: it, a spliced `checkpoint_recorded` stamped `policy_version: 1` would skip
#: its own required-payload row (that row applies at version >= 2), be
#: CERTIFIED by `verify_history`, and then crash `fold` with a raw `KeyError`
#: on the member the row would have required. A `KeyError` out of `fold` is
#: not a report (§5.5, §11.4), and a history `verify_history` certifies must
#: never crash `fold` — so an event whose name did not exist at its own
#: stamped version is `history_corrupt`, refused before it is ever folded.
_EVENT_MIN_POLICY_VERSION = (
    ("policy_version_adopted", 2),
    ("attempt_failed", 2),
    ("checkpoint_recorded", 2),
    ("checkpoint_restored", 2),
    ("compensation_started", 2),
    ("compensation_applied", 2),
    ("compensation_failed", 2),
)


def _event_available(event: str, policy_version: int) -> bool:
    for name, minimum in _EVENT_MIN_POLICY_VERSION:
        if name == event:
            return policy_version >= minimum
    return True


#: Read conditionally by `fold`, so only the type is pinned when present.
_EVENT_PAYLOAD_OPTIONAL = (
    (1, "workflow_cancelled", (("intent_id", "uuid"),)),
    (2, "compensation_started", (("compensation_ref", "ref"),)),
    (2, "compensation_failed", (
        ("result_sha256", "sha256"), ("compensation_state", "compensation"),
    )),
    (2, "dispatch_requested", (
        ("attempt_no", "attempt"), ("attempt_budget", "attempt"),
        ("restore_checkpoint_id", "uuid"),
        ("restore_checkpoint_sha256", "sha256"),
    )),
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
    if kind == "attempt":
        return _bounded_attempt(value)
    if kind == "provenance":
        return _text(value, _PROVENANCE_RE)
    if kind == "ref":
        return _text(value, _OPAQUE_REF_RE)
    if kind == "compensation":
        return value in WORKFLOW_COMPENSATION_STATES
    return False  # pragma: no cover - the table is closed


def _verify_event_payload(event: str, payload: dict, policy_version: int) -> bool:
    for version, name, rules in _EVENT_PAYLOAD_REQUIRED:
        if name != event or policy_version < version:
            continue
        for key, kind in rules:
            if key not in payload or not _payload_value_ok(kind, payload[key]):
                return False
    for version, name, rules in _EVENT_PAYLOAD_OPTIONAL:
        if name != event or policy_version < version:
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
    if not _event_available(fresh["event"], fresh["policy_version"]):
        # An event name that did not exist at its own stamped version is a
        # history this engine never wrote. Refusing here is what keeps
        # "certified by `verify_history`" implying "foldable".
        return _refuse("history_corrupt", f"/{index}/event")
    checks = (
        ("workflow_id", _text(fresh["workflow_id"], _WORKFLOW_ID_RE)),
        ("work_spec_sha256", _text(fresh["work_spec_sha256"], _SHA256_RE)),
        ("seq", _count(fresh["seq"], 1)),
        ("revision", _count(fresh["revision"], 1)),
        # Judged against the state tuple of the EVENT's own version, exactly
        # as `_event_available` judges the event NAME and `_verify_snapshot`
        # judges the snapshot's `state`. Without this the three disagree: a
        # policy-v1 event could name the fourteenth state, `fold` would return
        # a v1 snapshot sitting in `retrying`, every read surface — including
        # `verify`, the one the integrity note calls total — would report
        # `ok`, and every mutating command would refuse `snapshot_divergence`
        # with no diagnosis available anywhere (§22 A29.2).
        ("from_state", fresh["from_state"] is None
         or fresh["from_state"] in _policy_for(fresh["policy_version"])[1]),
        ("to_state", fresh["to_state"] is None
         or fresh["to_state"] in _policy_for(fresh["policy_version"])[1]),
        ("command_id", _text(fresh["command_id"], _UUID_RE)),
        ("command_sha256", _text(fresh["command_sha256"], _SHA256_RE)),
        ("actor", _text(fresh["actor"], _PROVENANCE_RE)),
        ("payload", isinstance(fresh["payload"], dict)),
        ("created_at", _is_real_instant(fresh["created_at"])),
    )
    for name, ok in checks:
        if not ok:
            return _refuse("history_corrupt", f"/{index}/{name}")
    if not _verify_event_payload(
        fresh["event"], fresh["payload"], fresh["policy_version"]
    ):
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
        **_FRESH_RECOVERY_MEMBERS,
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
            if "attempt_budget" in payload:
                snapshot["attempt_budget"] = payload["attempt_budget"]
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
                # A policy-v1 `dispatch_accepted` carries NO `attempt_no`, and
                # this reads it through an explicit presence check: the absent
                # case binds the runtime task, advances no counter, opens no
                # attempt and raises no `KeyError`, so a v1 history folds
                # forever and a v1 workflow honestly folds to
                # `attempts_used = 0`. No ordinal is inferred from event
                # sequence, receipt sequence, `runtime_task_uuid` or state —
                # what was never written is not recoverable (§5.5 item 5).
                if "attempt_no" in payload:
                    snapshot["attempt_no"] = payload["attempt_no"]
                    snapshot["attempt_state"] = "open"
                    snapshot["attempts_used"] = payload["attempt_no"]
                    snapshot["last_checkpoint_seq"] = 0
        elif name == "attempt_failed":
            snapshot["attempt_state"] = "failed"
        elif name == "checkpoint_recorded":
            snapshot["last_checkpoint_seq"] = payload["checkpoint_seq"]
            snapshot["checkpoint_count"] += 1
        elif name == "checkpoint_restored":
            snapshot["restored_checkpoint_sha256"] = payload[
                "checkpoint_sha256"
            ]
        elif name == "compensation_started":
            snapshot["attempt_state"] = "failed"
            snapshot["compensation_state"] = "pending"
            # One `compensate` intent is emitted with this event (§10.5), so
            # the per-workflow intent sequence advances here exactly as it
            # does for the three landed intent-emitting events. `decide` and
            # `fold` must agree on `intent_seq` or every later command reads
            # `snapshot_divergence`.
            snapshot["intent_seq"] += 1
        elif name == "compensation_applied":
            snapshot["compensation_state"] = "applied"
        elif name == "compensation_failed":
            snapshot["compensation_state"] = "failed"
        elif name == "workflow_succeeded":
            if snapshot["attempt_state"] == "open":
                snapshot["attempt_state"] = "succeeded"
        elif name == "workflow_failed":
            if snapshot["attempt_state"] == "open":
                snapshot["attempt_state"] = "failed"
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
                # §5.3.5: entering `cancelled` ABANDONS an attempt that was
                # still open. The work never concluded and never will, so the
                # row closes as neither `succeeded` nor `failed` — the fourth
                # attempt state exists for exactly this moment.
                if (
                    record["to_state"] == "cancelled"
                    and snapshot["attempt_state"] == "open"
                ):
                    snapshot["attempt_state"] = "abandoned"
        snapshot["revision"] = record["revision"]
        snapshot["policy_version"] = record["policy_version"]
        snapshot["last_seq"] = seq
    return _seal_snapshot(snapshot)
