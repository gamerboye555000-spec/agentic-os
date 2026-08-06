"""U-E1 observability: an OpenTelemetry-compatible PROJECTION over stored rows.

Compatibility here is a property of the BYTES this module writes, not of any
library it loads (contract §3.1, D-v0.4.118). Nothing is imported, linked or
vendored from OpenTelemetry; the field names, types and semantics below are
those of the OTel logs and metrics data models and W3C Trace Context, and
`otlp_*` renders them as OTLP/JSON.

Three invariants shape every line of this module:

1. **Nothing is persisted** (§6.8, D-v0.4.120). Every span, span id, link, log
   record, metric point and exported document is recomputed from stored rows on
   every call. There is no accumulator, no cache and NO WRITE PATH INTO
   `aos.db` at all — this module issues SELECT and nothing else.
2. **Privacy is structural, not filtered** (§7.2, D-v0.4.136). An attribute
   value must be a member of a closed vocabulary frozen in code, an identity
   matching a frozen pattern, a sha256 digest, a bounded integer, an RFC3339
   instant, or a boolean. There is no free-text value type, so a prompt, a
   goal, an acceptance criterion, a `reason.message`, a checkpoint payload or a
   model output CANNOT BE EXPRESSED here. A value that fails its declared type
   is dropped, never coerced and never truncated into a preview.
3. **Totality** (§10). Every stored value is type-checked BEFORE it is read;
   an unreadable row is reported under `unreadable` and the projection
   continues. No public function in this module raises a bare Python exception
   on a damaged row, and none of them repairs one.

Which stored bytes are opened, exactly (§7.3, §12.1):

- `workflows.work_spec_document` is parsed, and exactly FOUR members are read:
  `trace.trace_id`, `trace.correlation_id`, `trace.causation_id` and
  `data_classification`. Nothing else in that document is read.
- `report_document` and `workflow_intents.document` are NEVER opened at all.
- `workflow_receipts.document`, `workflow_facts.document` and
  `workflow_checkpoints.document` are referenced BY DIGEST AND BYTE LENGTH
  ONLY. No member of any of them is ever read, and none of them contributes a
  single attribute, log field or exported value. `verify` alone touches their
  bytes, and only to RECOMPUTE the self-excluding digest §10.2 requires it to
  recompute rather than trust — the same idiom `workflow_store` uses to
  re-digest its own rows. What escapes that comparison is one closed code
  (`digest_divergent`, `document_unparseable`, `row_unreadable`), never a
  value.
- `workflow_events.payload_json` and the base `events.payload_json` ARE read,
  through the CLOSED key allowlist in `_EVENT_PAYLOAD_ATTRIBUTES` /
  `_JOURNAL_PAYLOAD_ATTRIBUTES`. Both are the engine's own closed, typed,
  already-redacted journal vocabulary (`workflow_engine._EVENT_PAYLOAD_*`,
  `workflow_store._journal`) — they are not opaque bodies, and §4.1 requires
  several of their members (`reason_code`, `aos_task_id`, `checkpoint_id`,
  `intent_id`) as attributes. A key outside the allowlist is never read, and an
  allowlisted value that fails its declared type is dropped.

A FOREIGN TRACE (§4.3, as amended by A1.2 / D-v0.4.142) is a `trace_id`
observed anywhere other than `work_spec_document.trace`. It is NEITHER ADOPTED
NOR EMITTED: it never becomes a span's `trace_id`, a link's trace, an attribute,
a log field or an exported value, and there is no link kind for one. The only
columns where a foreign trace could be observed are the receipt, result-fact,
checkpoint and intent document bodies, and §7.3 forbids opening them — so a
foreign trace is unobservable here by construction, and a vocabulary entry for
a link nothing can produce would only mislead. Both halves therefore hold
structurally: this module has exactly one source of `trace_id`.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from . import db, protocols, secretscan
from .utils import AosError


class ObservabilityError(AosError):
    """A refusal at a public boundary: an unknown workflow, a malformed
    identity, an unwritable or non-empty output directory.

    Never raised for a damaged STORED row — those are reported (§10.3).
    """


# ---------------------------------------------------------------------------
# Frozen vocabularies (§4.4, §5, §6.4)

SPAN_WORKFLOW = "workflow"
SPAN_ATTEMPT = "attempt"
SPAN_COMPENSATION = "compensation"

#: The three span kinds. There is no fourth: a task is an ATTRIBUTE, never a
#: span (§5.1), and U-E1 does not own task lifetime.
SPAN_KINDS = (SPAN_WORKFLOW, SPAN_ATTEMPT, SPAN_COMPENSATION)

LINK_RETRY_OF = "retry_of"
LINK_RESTORED_FROM = "restored_from"
LINK_COMPENSATES = "compensates"

#: The three link kinds §5 names, and the whole active vocabulary. There is no
#: `foreign_trace` kind: A1.2 (D-v0.4.142) removed it, because §7.3 makes a
#: foreign trace unobservable here, so no valid projection could ever produce
#: one. Every emitted link carries the workflow's own root trace.
LINK_KINDS = (LINK_RETRY_OF, LINK_RESTORED_FROM, LINK_COMPENSATES)

STATUS_UNSET = "unset"
STATUS_OK = "ok"
STATUS_ERROR = "error"

SPAN_STATUSES = (STATUS_UNSET, STATUS_OK, STATUS_ERROR)

#: §5.6 verbatim. `abandoned` is deliberately NOT Error: an attempt abandoned
#: by cancellation did not fail, and marking it Error would make every
#: cancelled workflow read as a failure downstream (D-v0.4.130).
ATTEMPT_SPAN_STATUS = {
    "open": STATUS_UNSET,
    "succeeded": STATUS_OK,
    "failed": STATUS_ERROR,
    "abandoned": STATUS_UNSET,
}

#: The workflow span's status, by the same "only a real failure is Error" rule
#: §5.6 states for attempts. `compensated` and `cancelled` are Unset: neither
#: is a failure of the work AOS was asked to observe.
WORKFLOW_SPAN_STATUS = {"succeeded": STATUS_OK, "failed": STATUS_ERROR}

#: §6.4 — four values, not twenty-four. A severity scale finer than the
#: decisions it records is noise.
SEVERITY_INFO = (9, "INFO")
SEVERITY_WARN = (13, "WARN")
SEVERITY_ERROR = (17, "ERROR")

SEVERITIES = (SEVERITY_INFO, SEVERITY_WARN, SEVERITY_ERROR)

_WARN_EVENTS = frozenset({
    "dispatch_rejected", "dispatch_revoked", "attempt_failed",
    "compensation_failed",
})
_ERROR_EVENTS = frozenset({"workflow_failed"})

#: The CLI's own refusal journal row (`cli._journal_workflow_refusal`). It is
#: deliberately OUTSIDE `workflow_engine.WORKFLOW_EVENTS`, and §6.4 gives it
#: WARN.
JOURNAL_REFUSAL_ACTION = "workflow_command_refused"

#: `EventName` prefix for a projected workflow event (§6.2). Everything U-E1
#: mints is under `aos.`; `otel.*` is reserved by the semantic conventions and
#: is never used.
EVENT_NAME_PREFIX = "aos.workflow."

#: A base-journal row that is not a workflow event still becomes a log record
#: (§6.6). Its `EventName` names the journal, not a workflow transition.
JOURNAL_EVENT_NAME_PREFIX = "aos.journal."

#: `TraceFlags`: the sampled bit is clear (U-E1 does not sample — there is
#: nothing to sample, §2.2) and the `random-trace-id` bit is clear, ALWAYS
#: (§4.6, D-v0.4.125). Our identifiers are a domain-separated SHA-256 prefix;
#: asserting randomness would be a false claim about our own data.
TRACE_FLAGS = 0x00

#: The instrumentation scope every emitted record carries (§6.2).
SCOPE_NAME = "agentic_os.observability"

#: The one new `aos.*` record schema, and it is never stored (§13).
EXPORT_SCHEMA = "aos.observability-export/v1"

#: The three OTLP/JSON documents plus the manifest (§9.5).
EXPORT_TRACES = "traces.json"
EXPORT_LOGS = "logs.json"
EXPORT_METRICS = "metrics.json"
EXPORT_MANIFEST = "manifest.json"
EXPORT_FILES = (EXPORT_TRACES, EXPORT_LOGS, EXPORT_METRICS, EXPORT_MANIFEST)

TRACE_ROOT_WORK_SPEC = "work_spec"
TRACE_ROOT_UNRESOLVABLE = "unresolvable"

#: The closed diagnostic codes §10.4 permits. NEVER an excerpt, an offset, a
#: length of the offending text, or a hash of it.
UNREADABLE_CODES = (
    "work_spec_document_unparseable",
    "trace_member_absent",
    "trace_id_malformed",
    "data_classification_unknown",
    "event_row_unreadable",
    "event_payload_unreadable",
    "attempt_row_unreadable",
    "journal_row_unreadable",
    "instant_unparseable",
)

TRUNCATION_CODES = (
    "attributes_per_record",
    "links_per_span",
    "spans_per_workflow",
    "log_records_per_document",
)


# ---------------------------------------------------------------------------
# Bounds (§6.10). EVERY one is derived from a constant already frozen
# elsewhere; U-E1 introduces no tuned number.

#: `protocols.ERROR_CODE_PATTERN`'s ceiling.
MAX_ATTRIBUTE_KEY_CHARS = 63

#: The spine's `_string` default maximum.
MAX_ATTRIBUTE_VALUE_CHARS = 256

#: `protocols.MAX_OBJECT_MEMBERS / 8`.
MAX_ATTRIBUTES_PER_RECORD = protocols.MAX_OBJECT_MEMBERS // 8

#: The frozen attempt ceiling — a workflow cannot have more attempts to link to.
MAX_LINKS_PER_SPAN = 10

#: 1 workflow + 10 attempts + 1 compensation.
MAX_SPANS_PER_WORKFLOW = 12

#: The existing artifact bound, per exported document.
MAX_EXPORT_DOCUMENT_BYTES = protocols.MAX_ARTIFACT_BYTES

#: Canonical JSON's own array ceiling. A workflow's `workflow_events` row count
#: is the natural bound on its log records (§6.10), and this is the frozen
#: constant that bound has to live inside for the capsule to serialize at all.
#: Overflow is TRUNCATED AT THE BOUND AND REPORTED — never silently dropped and
#: never expanded past it (§10).
MAX_LOG_RECORDS_PER_DOCUMENT = protocols.MAX_ARRAY_ITEMS

#: §8.4, computed rather than asserted: 14 + 24 + 4 + 1 + 24.
MAX_METRIC_SERIES = 67


# ---------------------------------------------------------------------------
# Identity (§4.4)

_TAG_SPAN_WORKFLOW = b"aos-observability-span-workflow/v1"
_TAG_SPAN_ATTEMPT = b"aos-observability-span-attempt/v1"
_TAG_SPAN_COMPENSATION = b"aos-observability-span-compensation/v1"

_SPAN_TAGS = {
    SPAN_WORKFLOW: _TAG_SPAN_WORKFLOW,
    SPAN_ATTEMPT: _TAG_SPAN_ATTEMPT,
    SPAN_COMPENSATION: _TAG_SPAN_COMPENSATION,
}

_TRACE_ID_RE = re.compile(protocols.TRACE_ID_PATTERN, re.ASCII)
_SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$", re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.ASCII
)
_WORKFLOW_ID_RE = re.compile(r"^WF-[0-9]{1,19}$", re.ASCII)
_TASK_ID_RE = re.compile(r"^T-[0-9]{1,19}$", re.ASCII)
_SLUG_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$", re.ASCII)
_CODE_RE = re.compile(protocols.ERROR_CODE_PATTERN, re.ASCII)

# §7.2 admits "an identity matching a FROZEN pattern", so the writer's own
# frozen pattern is what is reused here — never a narrower copy minted in this
# module. A narrower copy would drop a LEGALLY STORED value (an `agent:Name`
# actor, a `team.build` queue route) and, because a dropped value sets
# `_Attributes.rejected`, report the row as `event_payload_unreadable` — a
# false integrity alarm on an undamaged ledger, which is exactly what §10's
# closed diagnostic codes must never be.
_COMPONENT_ID_RE = re.compile(protocols.COMPONENT_ID_PATTERN, re.ASCII)
_IDEMPOTENCY_RE = re.compile(protocols.IDEMPOTENCY_KEY_PATTERN, re.ASCII)
_PROVENANCE_RE = re.compile(protocols.PROVENANCE_PATTERN, re.ASCII)
_INSTANT_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z", re.ASCII
)

#: §7.2's key grammar: lowercase, `.`-namespaced, snake_case components, under
#: `aos.` (source 8's naming rules; `otel.*` is reserved and never used).
ATTRIBUTE_KEY_PATTERN = r"^aos\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){0,3}$"
_ATTRIBUTE_KEY_RE = re.compile(ATTRIBUTE_KEY_PATTERN, re.ASCII)


def _guard_zero(text: str) -> str:
    """The all-zero guard, mirroring `workspecs._guard_trace_id` exactly.

    Unreachable from sha256 output in practice; guarded anyway, because W3C
    Trace Context makes an all-zero span-id invalid.
    """
    if text == "0" * len(text):
        return text[:-1] + "1"
    return text


def span_id(kind: str, material: str) -> str:
    """16 lowercase hex from a domain-separated SHA-256 prefix (§4.4).

    NO RNG AND NO CLOCK IS READ: the same ledger yields the same span ids
    forever, which is what makes §4.6's cleared `random-trace-id` flag the
    honest statement rather than a missing feature.
    """
    tag = _SPAN_TAGS.get(kind)
    if tag is None:
        raise ObservabilityError(f"Unknown span kind: {kind}")
    digest = hashlib.sha256(tag + b"\0" + material.encode("utf-8")).hexdigest()
    return _guard_zero(digest[:16])


def span_id_ok(value) -> bool:
    """16 lowercase hex and not all zeros — W3C Trace Context's own rule for a
    span-id, applied to the ids this module mints."""
    return (
        isinstance(value, str)
        and _SPAN_ID_RE.match(value) is not None
        and value != "0" * 16
    )


def workflow_span_id(trace_id: str, workflow_id: str) -> str:
    return span_id(SPAN_WORKFLOW, f"{trace_id}:{workflow_id}")


def attempt_span_id(trace_id: str, workflow_id: str, attempt_no: int) -> str:
    return span_id(SPAN_ATTEMPT, f"{trace_id}:{workflow_id}:{attempt_no}")


def compensation_span_id(trace_id: str, workflow_id: str, opened_seq: int) -> str:
    return span_id(SPAN_COMPENSATION, f"{trace_id}:{workflow_id}:{opened_seq}")


# ---------------------------------------------------------------------------
# The closed attribute grammar (§7.2). Six value types, no free text.

VOCAB = "vocab"
IDENTITY = "identity"
DIGEST = "digest"
INTEGER = "integer"
INSTANT = "instant"
BOOLEAN = "boolean"

#: The six admitted value types, and there is no seventh.
VALUE_TYPES = (VOCAB, IDENTITY, DIGEST, INTEGER, INSTANT, BOOLEAN)


_VOCABULARY_CACHE: dict | None = None


def _vocabularies() -> dict:
    """The closed vocabularies an attribute value may be drawn from.

    Built once and reused: `attribute_ok` is called for every attribute of
    every record of every span, and rebuilding this map per call would make the
    bounds check quadratic in a ledger's size for no gain. Every member is a
    tuple frozen in code, so the cache can never go stale within a process.
    """
    global _VOCABULARY_CACHE
    if _VOCABULARY_CACHE is not None:
        return _VOCABULARY_CACHE

    from . import workflow_engine

    _VOCABULARY_CACHE = {
        "workflow_state": workflow_engine.WORKFLOW_STATES,
        "workflow_event": workflow_engine.WORKFLOW_EVENTS,
        "workflow_command": workflow_engine.WORKFLOW_COMMANDS,
        "attempt_state": workflow_engine.WORKFLOW_ATTEMPT_STATES,
        "compensation_state": workflow_engine.WORKFLOW_COMPENSATION_STATES,
        "approval_scope": workflow_engine.APPROVAL_SCOPES,
        "intent_kind": ("dispatch", "cancel", "compensate"),
        "intent_status": ("outstanding", "resolved", "revoked"),
        "refusal_reason": workflow_engine.WORKFLOW_REFUSAL_REASONS,
        "classification": protocols.DATA_CLASSIFICATIONS,
        "trace_root": (TRACE_ROOT_WORK_SPEC, TRACE_ROOT_UNRESOLVABLE),
        "span_kind": SPAN_KINDS,
        "link_kind": LINK_KINDS,
    }
    return _VOCABULARY_CACHE


#: (type, extra) per attribute key. `extra` is a vocabulary name for VOCAB, a
#: compiled pattern for IDENTITY, and `None` otherwise. The table is CLOSED:
#: `_attribute` refuses a key it does not name, so a later edit cannot smuggle
#: a free-text attribute in through a new key.
_ATTRIBUTE_TYPES: dict[str, tuple[str, object]] = {
    "aos.span.kind": (VOCAB, "span_kind"),
    "aos.link.kind": (VOCAB, "link_kind"),
    "aos.trace.root": (VOCAB, "trace_root"),
    "aos.trace.correlation_id": (IDENTITY, _UUID_RE),
    "aos.trace.causation_id": (IDENTITY, _UUID_RE),
    "aos.data.classification": (VOCAB, "classification"),
    "aos.clock.inconsistent": (BOOLEAN, None),

    "aos.workflow.id": (IDENTITY, _WORKFLOW_ID_RE),
    "aos.workflow.state": (VOCAB, "workflow_state"),
    "aos.workflow.from_state": (VOCAB, "workflow_state"),
    "aos.workflow.to_state": (VOCAB, "workflow_state"),
    "aos.workflow.event": (VOCAB, "workflow_event"),
    "aos.workflow.command": (VOCAB, "workflow_command"),
    "aos.workflow.command_id": (IDENTITY, _UUID_RE),
    "aos.workflow.command_sha256": (DIGEST, None),
    "aos.workflow.event_sha256": (DIGEST, None),
    "aos.workflow.seq": (INTEGER, None),
    "aos.workflow.revision": (INTEGER, None),
    "aos.workflow.policy_version": (INTEGER, None),
    "aos.workflow.intent_id": (IDENTITY, _UUID_RE),
    "aos.workflow.intent_kind": (VOCAB, "intent_kind"),
    "aos.workflow.intent_status": (VOCAB, "intent_status"),
    "aos.workflow.idempotency_key": (IDENTITY, _IDEMPOTENCY_RE),
    "aos.workflow.queue_route": (IDENTITY, _COMPONENT_ID_RE),
    "aos.workflow.actor": (IDENTITY, _PROVENANCE_RE),
    "aos.workflow.created_at": (INSTANT, None),
    "aos.workflow.observed_at": (INSTANT, None),

    "aos.workspec.id": (IDENTITY, _UUID_RE),
    "aos.workspec.sha256": (DIGEST, None),
    "aos.task.id": (IDENTITY, _TASK_ID_RE),

    "aos.attempt.no": (INTEGER, None),
    "aos.attempt.state": (VOCAB, "attempt_state"),
    "aos.attempt.budget": (INTEGER, None),
    "aos.attempt.used": (INTEGER, None),
    "aos.attempt.opened_seq": (INTEGER, None),
    "aos.attempt.closed_seq": (INTEGER, None),
    "aos.attempt.runtime_task_uuid": (IDENTITY, _UUID_RE),
    "aos.attempt.dispatch_intent_id": (IDENTITY, _UUID_RE),
    "aos.attempt.result_sha256": (DIGEST, None),

    "aos.checkpoint.id": (IDENTITY, _UUID_RE),
    "aos.checkpoint.seq": (INTEGER, None),
    "aos.checkpoint.sha256": (DIGEST, None),
    "aos.checkpoint.payload_bytes": (INTEGER, None),

    "aos.receipt.id": (IDENTITY, _UUID_RE),
    "aos.receipt.sha256": (DIGEST, None),
    "aos.result.sha256": (DIGEST, None),

    "aos.reason.code": (IDENTITY, _CODE_RE),
    "aos.reason.retryable": (BOOLEAN, None),
    "aos.refusal.reason": (VOCAB, "refusal_reason"),

    "aos.approval.scope": (VOCAB, "approval_scope"),
    "aos.compensation.state": (VOCAB, "compensation_state"),

    "aos.restore.from_attempt_no": (INTEGER, None),
    "aos.restore.into_attempt_no": (INTEGER, None),
    "aos.restore.restored_by": (IDENTITY, _PROVENANCE_RE),

    "aos.policy.from_version": (INTEGER, None),
    "aos.policy.to_version": (INTEGER, None),

    "aos.journal.row_id": (INTEGER, None),
    "aos.journal.entity": (IDENTITY, _SLUG_RE),
    "aos.journal.entity_id": (INTEGER, None),
    "aos.journal.action": (IDENTITY, _SLUG_RE),
}

#: Forbidden as a METRIC DIMENSION, by name (§7.6). Every one of these is
#: unbounded cardinality, an operator- or runtime-chosen string, or both.
FORBIDDEN_METRIC_DIMENSIONS = (
    "aos.workflow.id", "aos.task.id", "trace_id", "span_id",
    "aos.trace.correlation_id", "aos.trace.causation_id",
    "aos.workflow.command_id", "aos.workflow.intent_id", "aos.receipt.id",
    "aos.checkpoint.id", "aos.attempt.runtime_task_uuid",
    "aos.workspec.sha256", "aos.workflow.command_sha256",
    "aos.workflow.event_sha256", "aos.result.sha256",
    "aos.attempt.result_sha256", "aos.checkpoint.sha256", "aos.receipt.sha256",
    "aos.workflow.actor", "aos.workflow.queue_route", "aos.reason.code",
    "aos.attempt.no", "aos.workflow.created_at", "aos.workflow.observed_at",
)


def attribute_key_ok(key) -> bool:
    return (
        isinstance(key, str)
        and len(key) <= MAX_ATTRIBUTE_KEY_CHARS
        and _ATTRIBUTE_KEY_RE.match(key) is not None
    )


def _value_ok(kind: str, extra, value) -> bool:
    """One declared type, checked explicitly. `bool` is tested BEFORE `int`
    because `isinstance(True, int)` is true in Python and a boolean must never
    satisfy the integer type by accident."""
    if kind == BOOLEAN:
        return isinstance(value, bool)
    if kind == INTEGER:
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and protocols.INT_MIN <= value <= protocols.INT_MAX
        )
    if not isinstance(value, str) or len(value) > MAX_ATTRIBUTE_VALUE_CHARS:
        return False
    if kind == VOCAB:
        return value in _vocabularies()[extra]
    if kind == DIGEST:
        return _SHA256_RE.match(value) is not None
    if kind == INSTANT:
        return _INSTANT_RE.match(value) is not None
    if kind == IDENTITY:
        return extra.match(value) is not None
    return False  # pragma: no cover - VALUE_TYPES is closed


def attribute_ok(key, value) -> bool:
    """True iff `(key, value)` is admissible under §7.2's grammar."""
    declared = _ATTRIBUTE_TYPES.get(key) if isinstance(key, str) else None
    if declared is None or not attribute_key_ok(key):
        return False
    return _value_ok(declared[0], declared[1], value)


class _Attributes:
    """An ordered, bounded, type-checked attribute set.

    A value that fails its declared type is DROPPED — never coerced, never
    truncated into a preview, never replaced by a placeholder that would state
    something the ledger does not. Overflow past `MAX_ATTRIBUTES_PER_RECORD` is
    reported to the caller rather than silently discarded (§10's truncation
    rule).
    """

    __slots__ = ("_items", "truncated", "rejected")

    def __init__(self) -> None:
        self._items: list[tuple[str, object]] = []
        self.truncated = False
        self.rejected = False

    def add(self, key: str, value) -> None:
        if value is None:
            return
        if not attribute_ok(key, value):
            self.rejected = True
            return
        if len(self._items) >= MAX_ATTRIBUTES_PER_RECORD:
            self.truncated = True
            return
        self._items.append((key, value))

    def frozen(self) -> tuple:
        return tuple(self._items)


# ---------------------------------------------------------------------------
# Time (§6.5). Honest by construction: second-precision in, second-precision
# out, and the low nine digits of every nanosecond value are ALWAYS ZERO.

_NANOS_PER_SECOND = 1_000_000_000


def to_unix_nano(text) -> int | None:
    """RFC3339 second-precision → uint64 nanoseconds, or `None`.

    Total: a value that is not a real instant returns `None` rather than
    raising, so §6.3's "use Timestamp if present, otherwise ObservedTimestamp"
    can resolve it.
    """
    if not isinstance(text, str) or _INSTANT_RE.match(text) is None:
        return None
    try:
        moment = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return int(moment.replace(tzinfo=timezone.utc).timestamp()) * _NANOS_PER_SECOND


def duration_seconds(start_ns, end_ns) -> int:
    """`end − start`, CLAMPED AT 0 (§6.5).

    There is no monotonic clock in this codebase and U-E1 invents none. A
    negative duration is unrepresentable: the clamp is the representation.
    """
    if start_ns is None or end_ns is None or end_ns <= start_ns:
        return 0
    return (end_ns - start_ns) // _NANOS_PER_SECOND


def _clock_inconsistent(start_ns, end_ns) -> bool:
    return start_ns is not None and end_ns is not None and end_ns < start_ns


# ---------------------------------------------------------------------------
# Total readers. An explicit type check BEFORE every read (§10.1) — never a
# bare index or attribute access on a stored value.

def _text(value):
    return value if isinstance(value, str) else None


def _count(value):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


def _matching(value, pattern):
    text = _text(value)
    return text if text is not None and pattern.match(text) else None


def _parse_document(raw):
    """Stored bytes → a document, or `None`. Never raises."""
    text = _text(raw)
    if text is None:
        return None
    try:
        return protocols.parse_canonical(text.encode("utf-8"))
    except (protocols.ProtocolError, UnicodeEncodeError, ValueError):
        return None


def _parse_payload(raw):
    """A journal payload → a dict, or `None`. `json.loads` rather than
    `parse_canonical`: the payload column is written by `json.dumps`, not by
    the canonical serializer, and is bounded by the writer's own vocabulary."""
    text = _text(raw)
    if text is None:
        return None
    try:
        value = json.loads(text)
    except (ValueError, RecursionError):
        return None
    return value if isinstance(value, dict) else None


def _fetchall(conn, sql, params=()):
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        raise ObservabilityError(
            "The workspace ledger could not be read. Run: python aos.py doctor"
        ) from None


def _fetchone(conn, sql, params=()):
    try:
        return conn.execute(sql, params).fetchone()
    except sqlite3.Error:
        raise ObservabilityError(
            "The workspace ledger could not be read. Run: python aos.py doctor"
        ) from None


def render_workflow_id(row_id: int) -> str:
    return f"WF-{row_id}"


def parse_workflow_id(workflow_id) -> int:
    """`WF-n` → the ledger row id. The ONE accepted spelling family, and a
    malformed one is a refusal, never a guess."""
    text = _text(workflow_id)
    if text is None or _WORKFLOW_ID_RE.match(text) is None:
        raise ObservabilityError(
            f"Not a workflow id: {workflow_id!r}. Expected WF-n. "
            "Run: python aos.py workflow list"
        )
    return int(text[3:])


# ---------------------------------------------------------------------------
# The trace root (§4.2) — the one load-bearing read of a document column.

@dataclass(frozen=True)
class TraceRoot:
    """`work_spec_document`'s four readable members, and nothing else.

    `trace_id` is `None` exactly when the root is unresolvable, in which case
    `code` names the closed reason. THE VALUE IS NEVER REPAIRED, NEVER
    RE-DERIVED AND NEVER SUBSTITUTED (§4.5 rule 1, D-v0.4.124): W3C's own rule
    for an invalid inbound traceparent is restart, and U-E1 has nothing to
    restart, so it reports.
    """

    root: str
    trace_id: str | None
    correlation_id: str | None
    causation_id: str | None
    data_classification: str | None
    code: str | None


_UNRESOLVED_ROOT = TraceRoot(
    TRACE_ROOT_UNRESOLVABLE, None, None, None, None,
    "work_spec_document_unparseable",
)


def resolve_trace_root(work_spec_document_text) -> TraceRoot:
    """Parse `work_spec_document` and read EXACTLY four members (§7.3).

    Nothing else in that document is read — not the goal, not the acceptance
    criteria, not the constraints, not the inputs. This is what makes §7.2's
    grammar checkable by a reviewer rather than merely promised.
    """
    document = _parse_document(work_spec_document_text)
    if document is None:
        return _UNRESOLVED_ROOT
    trace = document.get("trace")
    if not isinstance(trace, dict):
        return TraceRoot(
            TRACE_ROOT_UNRESOLVABLE, None, None, None, None,
            "trace_member_absent",
        )
    trace_id = _matching(trace.get("trace_id"), _TRACE_ID_RE)
    if trace_id is None or trace_id == "0" * 32:
        return TraceRoot(
            TRACE_ROOT_UNRESOLVABLE, None, None, None, None,
            "trace_id_malformed",
        )
    classification = document.get("data_classification")
    if classification not in protocols.DATA_CLASSIFICATIONS:
        classification = None
    return TraceRoot(
        TRACE_ROOT_WORK_SPEC,
        trace_id,
        _matching(trace.get("correlation_id"), _UUID_RE),
        _matching(trace.get("causation_id"), _UUID_RE),
        classification,
        None if classification is not None else "data_classification_unknown",
    )


# ---------------------------------------------------------------------------
# Public record types. Frozen dataclasses over fresh values; nothing here is
# stored, so nothing here has an identity beyond this call (§6.8).

@dataclass(frozen=True)
class Link:
    kind: str
    trace_id: str
    span_id: str | None
    attributes: tuple = ()


@dataclass(frozen=True)
class Span:
    span_id: str
    parent_span_id: str | None
    trace_id: str
    name: str
    kind: str
    status: str
    start_unix_nano: int | None
    end_unix_nano: int | None
    duration_seconds: int
    attributes: tuple = ()
    links: tuple = ()


@dataclass(frozen=True)
class LogRecord:
    """§6.2's field mapping, with OTel's own field names.

    `body` is ALWAYS empty (§7.3): there is no flag, no mode and no
    configuration that fills it.
    """

    event_name: str
    timestamp_unix_nano: int | None
    observed_timestamp_unix_nano: int | None
    trace_id: str | None
    span_id: str | None
    severity_number: int
    severity_text: str
    attributes: tuple = ()
    trace_flags: int = TRACE_FLAGS
    body: str = ""

    @property
    def effective_timestamp_unix_nano(self):
        """§6.3 verbatim: use `Timestamp` if present, otherwise use
        `ObservedTimestamp`."""
        if self.timestamp_unix_nano is not None:
            return self.timestamp_unix_nano
        return self.observed_timestamp_unix_nano


@dataclass(frozen=True)
class WorkflowProjection:
    workflow_id: str
    trace_root: str
    trace_id: str | None
    task_id: str | None
    state: str | None
    revision: int | None
    policy_version: int | None
    data_classification: str | None
    work_spec_sha256: str | None
    spans: tuple = ()
    logs: tuple = ()
    unreadable: tuple = ()
    truncated: tuple = ()
    clock_inconsistent: bool = False


@dataclass(frozen=True)
class MetricPoint:
    attributes: tuple
    value: int = 0
    count: int = 0
    sum: int = 0
    bucket_counts: tuple = ()


@dataclass(frozen=True)
class Metric:
    name: str
    instrument: str
    unit: str
    monotonic: bool
    temporality: str
    dimensions: tuple
    points: tuple = ()


@dataclass(frozen=True)
class MetricsProjection:
    start_unix_nano: int | None
    time_unix_nano: int | None
    metrics: tuple = ()
    unreadable: tuple = ()

    @property
    def series(self) -> int:
        return sum(len(m.points) for m in self.metrics)


@dataclass(frozen=True)
class VerifyReport:
    workflow_id: str
    trace_root: str
    divergent: tuple = ()
    unreadable: tuple = ()
    truncated: tuple = ()
    clock_inconsistent: bool = False
    span_count: int = 0
    log_count: int = 0

    @property
    def ok(self) -> bool:
        return not (
            self.divergent or self.unreadable or self.truncated
            or self.clock_inconsistent
            or self.trace_root != TRACE_ROOT_WORK_SPEC
        )


# ---------------------------------------------------------------------------
# The event-payload allowlists (§7.3, §12.1(b)).
#
# CLOSED: a key that is not named here is NEVER read out of a payload, and an
# allowlisted value that fails its declared attribute type is dropped by
# `_Attributes.add`. Every member below is already constrained to one of §7.2's
# six value types by `workflow_engine._EVENT_PAYLOAD_REQUIRED` /
# `_EVENT_PAYLOAD_OPTIONAL`, so this reads the engine's own closed vocabulary
# rather than opening an opaque body.

_EVENT_PAYLOAD_ATTRIBUTES: tuple[tuple[str, str], ...] = (
    ("task_id", "aos.task.id"),
    ("scope", "aos.approval.scope"),
    ("intent_id", "aos.workflow.intent_id"),
    ("queue_route", "aos.workflow.queue_route"),
    ("idempotency_key", "aos.workflow.idempotency_key"),
    ("runtime_task_uuid", "aos.attempt.runtime_task_uuid"),
    ("attempt_no", "aos.attempt.no"),
    ("attempt_budget", "aos.attempt.budget"),
    ("attempts_used", "aos.attempt.used"),
    ("checkpoint_id", "aos.checkpoint.id"),
    ("checkpoint_sha256", "aos.checkpoint.sha256"),
    ("checkpoint_seq", "aos.checkpoint.seq"),
    ("payload_bytes", "aos.checkpoint.payload_bytes"),
    ("from_attempt_no", "aos.restore.from_attempt_no"),
    ("into_attempt_no", "aos.restore.into_attempt_no"),
    ("restored_by", "aos.restore.restored_by"),
    ("result_sha256", "aos.result.sha256"),
    ("compensation_state", "aos.compensation.state"),
    ("reason_code", "aos.reason.code"),
    ("retryable", "aos.reason.retryable"),
    ("from_policy_version", "aos.policy.from_version"),
    ("to_policy_version", "aos.policy.to_version"),
)

#: The members `workflow_store._journal` writes, plus the CLI refusal row's
#: `reason`. `where`, `diagnostics` and `status` are deliberately NOT read.
_JOURNAL_PAYLOAD_ATTRIBUTES: tuple[tuple[str, str], ...] = (
    ("seq", "aos.workflow.seq"),
    ("revision", "aos.workflow.revision"),
    ("policy_version", "aos.workflow.policy_version"),
    ("from_state", "aos.workflow.from_state"),
    ("to_state", "aos.workflow.to_state"),
    ("command", "aos.workflow.command"),
    ("command_id", "aos.workflow.command_id"),
    ("command_sha256", "aos.workflow.command_sha256"),
    ("event_sha256", "aos.workflow.event_sha256"),
    ("work_spec_sha256", "aos.workspec.sha256"),
    ("reason", "aos.refusal.reason"),
)

def _add_payload_attributes(attrs: _Attributes, payload: dict) -> None:
    for member, key in _EVENT_PAYLOAD_ATTRIBUTES:
        if member in payload:
            attrs.add(key, payload[member])


# ---------------------------------------------------------------------------
# SQL. SELECT ONLY — this module opens no write transaction and issues no DDL.

_SQL_WORKFLOW = (
    "SELECT id, task_id, work_spec_sha256, work_spec_document, state, "
    "revision, policy_version, queue_route, runtime_task_uuid, created_at, "
    f"updated_at FROM {db.WORKFLOWS_TABLE} WHERE id = ?"
)
_SQL_WORKFLOW_IDS = f"SELECT id FROM {db.WORKFLOWS_TABLE} ORDER BY id"
_SQL_EVENTS = (
    "SELECT seq, event, from_state, to_state, revision, policy_version, "
    "command_id, command_sha256, actor, payload_json, created_at, "
    f"content_sha256 FROM {db.WORKFLOW_EVENTS_TABLE} "
    "WHERE workflow_id = ? ORDER BY seq"
)
_SQL_ATTEMPTS = (
    "SELECT attempt_no, state, runtime_task_uuid, dispatch_intent_id, "
    "idempotency_key, result_sha256, opened_seq, closed_seq "
    f"FROM {db.WORKFLOW_ATTEMPTS_TABLE} WHERE workflow_id = ? "
    "ORDER BY attempt_no"
)
_SQL_CHECKPOINTS = (
    "SELECT attempt_no, checkpoint_id, checkpoint_seq, document, "
    f"document_sha256, payload_bytes FROM {db.WORKFLOW_CHECKPOINTS_TABLE} "
    "WHERE workflow_id = ? ORDER BY attempt_no, checkpoint_seq"
)
_SQL_FACTS = (
    "SELECT id, fact_kind, fact_scope, document, document_sha256 "
    f"FROM {db.WORKFLOW_FACTS_TABLE} WHERE workflow_id = ? ORDER BY id"
)
_SQL_RECEIPTS = (
    "SELECT id, receipt_id, document, receipt_sha256 "
    f"FROM {db.WORKFLOW_RECEIPTS_TABLE} WHERE workflow_id = ? ORDER BY id"
)
_SQL_JOURNAL_FOR = (
    "SELECT id, ts, actor, entity, entity_id, action, payload_json "
    "FROM events WHERE entity = 'workflow' AND entity_id = ? ORDER BY id"
)
_SQL_JOURNAL_ALL = (
    "SELECT id, ts, actor, entity, entity_id, action, payload_json "
    "FROM events ORDER BY id"
)
_SQL_GENESIS = "SELECT MIN(ts) FROM events"
_SQL_LATEST = "SELECT MAX(ts) FROM events"


# ---------------------------------------------------------------------------
# The workflow projection (§5)

def _severity(event_name) -> tuple[int, str]:
    if event_name in _ERROR_EVENTS:
        return SEVERITY_ERROR
    if event_name in _WARN_EVENTS:
        return SEVERITY_WARN
    return SEVERITY_INFO


class _Collector:
    """Accumulates the closed diagnostic codes a projection reports."""

    def __init__(self) -> None:
        self.unreadable: list[tuple[str, str]] = []
        self.truncated: list[tuple[str, int]] = []

    def unread(self, where: str, code: str) -> None:
        if code in UNREADABLE_CODES and (where, code) not in self.unreadable:
            self.unreadable.append((where, code))

    def truncate(self, what: str, bound: int) -> None:
        if what in TRUNCATION_CODES and (what, bound) not in self.truncated:
            self.truncated.append((what, bound))

    def note(self, where: str, attrs: _Attributes) -> None:
        if attrs.truncated:
            self.truncate("attributes_per_record", MAX_ATTRIBUTES_PER_RECORD)
        if attrs.rejected:
            self.unread(where, "event_payload_unreadable")


def project_workflow(conn, workflow_id) -> WorkflowProjection:
    """One workflow's whole projection: spans, links and log records.

    Total on a damaged ledger (§10.3): an unreadable row is listed under
    `unreadable` and the projection continues. A workflow whose trace root does
    not resolve emits NO SPAN AT ALL (§10's refusal table) — a span without a
    trace would be manufacturing the identity §4.5 exists to protect.
    """
    row_id = parse_workflow_id(workflow_id)
    identity = render_workflow_id(row_id)
    row = _fetchone(conn, _SQL_WORKFLOW, (row_id,))
    if row is None:
        raise ObservabilityError(
            f"No workflow {identity}. Run: python aos.py workflow list"
        )
    collector = _Collector()
    root = resolve_trace_root(row[3])
    if root.code is not None:
        collector.unread("/work_spec_document", root.code)

    state = _text(row[4])
    revision = _count(row[5])
    policy_version = _count(row[6])
    work_spec_sha256 = _matching(row[2], _SHA256_RE)

    events = _read_events(conn, row_id, collector)
    attempts = _read_attempts(conn, row_id, collector)
    task_id = _task_id_of(events)

    if root.trace_id is None:
        return WorkflowProjection(
            workflow_id=identity,
            trace_root=root.root,
            trace_id=None,
            task_id=task_id,
            state=state,
            revision=revision,
            policy_version=policy_version,
            data_classification=root.data_classification,
            work_spec_sha256=work_spec_sha256,
            spans=(),
            logs=(),
            unreadable=tuple(collector.unreadable),
            truncated=tuple(collector.truncated),
            clock_inconsistent=False,
        )

    spans, seq_to_span, inconsistent = _build_spans(
        identity, root, state, task_id, work_spec_sha256, revision,
        policy_version, row, events, attempts, collector,
    )
    logs = _build_logs(
        conn, row_id, identity, root, events, seq_to_span, spans, collector,
    )
    return WorkflowProjection(
        workflow_id=identity,
        trace_root=root.root,
        trace_id=root.trace_id,
        task_id=task_id,
        state=state,
        revision=revision,
        policy_version=policy_version,
        data_classification=root.data_classification,
        work_spec_sha256=work_spec_sha256,
        spans=spans,
        logs=logs,
        unreadable=tuple(collector.unreadable),
        truncated=tuple(collector.truncated),
        clock_inconsistent=inconsistent,
    )


def _read_events(conn, row_id, collector) -> tuple:
    """`workflow_events` in `seq` order, each reduced to the members §5 and
    §6 name. An unreadable row is reported and skipped."""
    from . import workflow_engine

    out = []
    for row in _fetchall(conn, _SQL_EVENTS, (row_id,)):
        seq = _count(row[0])
        event = _text(row[1])
        if seq is None or event not in workflow_engine.WORKFLOW_EVENTS:
            collector.unread("/workflow_events", "event_row_unreadable")
            continue
        payload = _parse_payload(row[9])
        if payload is None:
            collector.unread("/workflow_events", "event_payload_unreadable")
            payload = {}
        created_at = _text(row[10])
        if created_at is not None and to_unix_nano(created_at) is None:
            # §10: the record's Timestamp is dropped; §6.3 then resolves it
            # from ObservedTimestamp. The value is never repaired.
            collector.unread("/workflow_events/created_at", "instant_unparseable")
            created_at = None
        out.append({
            "seq": seq,
            "event": event,
            "from_state": _text(row[2]),
            "to_state": _text(row[3]),
            "revision": _count(row[4]),
            "policy_version": _count(row[5]),
            "command_id": _text(row[6]),
            "command_sha256": _text(row[7]),
            "actor": _text(row[8]),
            "payload": payload,
            "created_at": created_at,
            "content_sha256": _text(row[11]),
        })
    return tuple(out)


def _read_attempts(conn, row_id, collector) -> tuple:
    from . import workflow_engine

    out = []
    for row in _fetchall(conn, _SQL_ATTEMPTS, (row_id,)):
        attempt_no = _count(row[0])
        state = _text(row[1])
        opened_seq = _count(row[6])
        if (
            attempt_no is None
            or state not in workflow_engine.WORKFLOW_ATTEMPT_STATES
            or opened_seq is None
        ):
            collector.unread("/workflow_attempts", "attempt_row_unreadable")
            continue
        out.append({
            "attempt_no": attempt_no,
            "state": state,
            "runtime_task_uuid": _text(row[2]),
            "dispatch_intent_id": _text(row[3]),
            "idempotency_key": _text(row[4]),
            "result_sha256": _text(row[5]),
            "opened_seq": opened_seq,
            "closed_seq": _count(row[7]),
        })
    return tuple(out)


def _task_id_of(events):
    """`aos_task_id` is carried by the `workflow_admitted` payload as
    `task_id` — the task→workflow edge (§4.1). It is an ATTRIBUTE, never a
    span: U-E1 does not own task lifetime (§5.1)."""
    for record in events:
        if record["event"] == "workflow_admitted":
            return _matching(record["payload"].get("task_id"), _TASK_ID_RE)
    return None


def _event_at(events, seq):
    for record in events:
        if record["seq"] == seq:
            return record
    return None


def _instant_of(record):
    return None if record is None else record["created_at"]


def _build_spans(identity, root, state, task_id, work_spec_sha256, revision,
                 policy_version, row, events, attempts, collector):
    """§5.1's tree: one workflow root, attempts as SIBLINGS with `retry_of`
    links, and compensation as a child of the WORKFLOW span."""
    trace_id = root.trace_id
    spans: list[Span] = []
    seq_to_span: dict[int, str] = {}
    inconsistent = False

    first_instant = events[0]["created_at"] if events else None
    last_instant = events[-1]["created_at"] if events else None
    start_ns = to_unix_nano(first_instant)
    end_ns = to_unix_nano(last_instant)
    skewed = _clock_inconsistent(start_ns, end_ns)
    inconsistent = inconsistent or skewed

    wf_span_id = workflow_span_id(trace_id, identity)
    attrs = _Attributes()
    attrs.add("aos.span.kind", SPAN_WORKFLOW)
    attrs.add("aos.trace.root", root.root)
    attrs.add("aos.workflow.id", identity)
    attrs.add("aos.workflow.state", state)
    attrs.add("aos.workflow.revision", revision)
    attrs.add("aos.workflow.policy_version", policy_version)
    attrs.add("aos.workspec.sha256", work_spec_sha256)
    attrs.add("aos.task.id", task_id)
    attrs.add("aos.trace.correlation_id", root.correlation_id)
    attrs.add("aos.trace.causation_id", root.causation_id)
    attrs.add("aos.data.classification", root.data_classification)
    attrs.add("aos.workflow.queue_route", _text(row[7]))
    if skewed:
        attrs.add("aos.clock.inconsistent", True)
    collector.note("/workflow_span", attrs)
    spans.append(Span(
        span_id=wf_span_id,
        parent_span_id=None,
        trace_id=trace_id,
        name=identity,
        kind=SPAN_WORKFLOW,
        status=WORKFLOW_SPAN_STATUS.get(state, STATUS_UNSET),
        start_unix_nano=start_ns,
        end_unix_nano=end_ns,
        duration_seconds=duration_seconds(start_ns, end_ns),
        attributes=attrs.frozen(),
        links=(),
    ))

    restores = _restore_edges(events)
    attempt_ids = {
        a["attempt_no"]: attempt_span_id(trace_id, identity, a["attempt_no"])
        for a in attempts
    }

    for attempt in attempts:
        if len(spans) >= MAX_SPANS_PER_WORKFLOW:
            collector.truncate("spans_per_workflow", MAX_SPANS_PER_WORKFLOW)
            break
        number = attempt["attempt_no"]
        opened = _event_at(events, attempt["opened_seq"])
        closed = (
            _event_at(events, attempt["closed_seq"])
            if attempt["closed_seq"] is not None else None
        )
        a_start = to_unix_nano(_instant_of(opened))
        # An OPEN attempt has no closing event, so it has no observed end.
        # Its end is its start and its duration is 0: claiming it ran until
        # "now" would assert a timeline AOS never observed (§12.1(c)).
        a_end = to_unix_nano(_instant_of(closed)) if closed is not None else a_start
        skewed = _clock_inconsistent(a_start, a_end)
        inconsistent = inconsistent or skewed

        attrs = _Attributes()
        attrs.add("aos.span.kind", SPAN_ATTEMPT)
        attrs.add("aos.workflow.id", identity)
        attrs.add("aos.attempt.no", number)
        attrs.add("aos.attempt.state", attempt["state"])
        attrs.add("aos.attempt.opened_seq", attempt["opened_seq"])
        attrs.add("aos.attempt.closed_seq", attempt["closed_seq"])
        attrs.add("aos.attempt.runtime_task_uuid", attempt["runtime_task_uuid"])
        attrs.add("aos.attempt.dispatch_intent_id", attempt["dispatch_intent_id"])
        attrs.add("aos.workflow.idempotency_key", attempt["idempotency_key"])
        attrs.add("aos.attempt.result_sha256", attempt["result_sha256"])
        attrs.add("aos.data.classification", root.data_classification)
        if skewed:
            attrs.add("aos.clock.inconsistent", True)
        collector.note("/attempt_span", attrs)

        links: list[Link] = []
        # §5.2: attempt N+1 is a SIBLING of attempt N carrying a `retry_of`
        # link — not a child. Nesting would make attempt N's duration include
        # attempt N+1's, which is false.
        previous = attempt_ids.get(number - 1)
        if previous is not None:
            links.append(Link(LINK_RETRY_OF, trace_id, previous, (
                ("aos.link.kind", LINK_RETRY_OF),
                ("aos.attempt.no", number - 1),
            )))
        # §5.3: a CROSS-ATTEMPT restore emits `restored_from` in addition to
        # its log record; a same-attempt restore emits only the record.
        for restore in restores:
            if restore["into"] != number or restore["from"] == restore["into"]:
                continue
            target = attempt_ids.get(restore["from"])
            link_attrs = _Attributes()
            link_attrs.add("aos.link.kind", LINK_RESTORED_FROM)
            link_attrs.add("aos.attempt.no", restore["from"])
            link_attrs.add("aos.checkpoint.id", restore["checkpoint_id"])
            link_attrs.add("aos.checkpoint.sha256", restore["checkpoint_sha256"])
            collector.note("/restored_from", link_attrs)
            links.append(
                Link(LINK_RESTORED_FROM, trace_id, target, link_attrs.frozen())
            )
        if len(links) > MAX_LINKS_PER_SPAN:
            collector.truncate("links_per_span", MAX_LINKS_PER_SPAN)
            links = links[:MAX_LINKS_PER_SPAN]

        seq_to_span[attempt["opened_seq"]] = attempt_ids[number]
        if attempt["closed_seq"] is not None:
            seq_to_span[attempt["closed_seq"]] = attempt_ids[number]
        for seq in range(
            attempt["opened_seq"] + 1,
            (attempt["closed_seq"] or attempt["opened_seq"]) + 1,
        ):
            seq_to_span.setdefault(seq, attempt_ids[number])

        spans.append(Span(
            span_id=attempt_ids[number],
            parent_span_id=wf_span_id,
            trace_id=trace_id,
            name=f"attempt #{number}",
            kind=SPAN_ATTEMPT,
            status=ATTEMPT_SPAN_STATUS[attempt["state"]],
            start_unix_nano=a_start,
            end_unix_nano=a_end,
            duration_seconds=duration_seconds(a_start, a_end),
            attributes=attrs.frozen(),
            links=tuple(links),
        ))

    compensation = _compensation_span(
        identity, root, events, attempts, attempt_ids, wf_span_id, collector,
    )
    if compensation is not None:
        if len(spans) >= MAX_SPANS_PER_WORKFLOW:
            collector.truncate("spans_per_workflow", MAX_SPANS_PER_WORKFLOW)
        else:
            span, covered = compensation
            inconsistent = inconsistent or _clock_inconsistent(
                span.start_unix_nano, span.end_unix_nano
            )
            for seq in covered:
                seq_to_span[seq] = span.span_id
            spans.append(span)

    return tuple(spans), seq_to_span, inconsistent


def _restore_edges(events) -> tuple:
    """`checkpoint_restored` payload members, read through the allowlist."""
    out = []
    for record in events:
        if record["event"] != "checkpoint_restored":
            continue
        payload = record["payload"]
        source = _count(payload.get("from_attempt_no"))
        target = _count(payload.get("into_attempt_no"))
        if source is None or target is None:
            continue
        out.append({
            "from": source,
            "into": target,
            "seq": record["seq"],
            "checkpoint_id": _matching(payload.get("checkpoint_id"), _UUID_RE),
            "checkpoint_sha256": _matching(
                payload.get("checkpoint_sha256"), _SHA256_RE
            ),
        })
    return tuple(out)


def _compensation_span(identity, root, events, attempts, attempt_ids,
                       parent_span_id, collector):
    """§5.1: compensation is a child of the WORKFLOW span, not of an attempt,
    and carries a `compensates` link to the attempt whose failure opened it."""
    opened = None
    closed = None
    state = None
    for record in events:
        if record["event"] == "compensation_started" and opened is None:
            opened = record
        elif record["event"] in ("compensation_applied", "compensation_failed"):
            closed = record
            state = _text(record["payload"].get("compensation_state"))
    if opened is None:
        return None

    trace_id = root.trace_id
    identity_seq = opened["seq"]
    c_span_id = compensation_span_id(trace_id, identity, identity_seq)
    start_ns = to_unix_nano(opened["created_at"])
    end_ns = (
        to_unix_nano(closed["created_at"]) if closed is not None else start_ns
    )

    attrs = _Attributes()
    attrs.add("aos.span.kind", SPAN_COMPENSATION)
    attrs.add("aos.workflow.id", identity)
    attrs.add("aos.workflow.seq", identity_seq)
    attrs.add("aos.compensation.state", state)
    attrs.add("aos.data.classification", root.data_classification)
    attrs.add("aos.result.sha256", _matching(
        opened["payload"].get("result_sha256"), _SHA256_RE
    ))
    if _clock_inconsistent(start_ns, end_ns):
        attrs.add("aos.clock.inconsistent", True)
    collector.note("/compensation_span", attrs)

    links: list[Link] = []
    compensated_attempt = _count(opened["payload"].get("attempt_no"))
    if compensated_attempt is None and attempts:
        compensated_attempt = attempts[-1]["attempt_no"]
    target = attempt_ids.get(compensated_attempt)
    if target is not None:
        links.append(Link(LINK_COMPENSATES, trace_id, target, (
            ("aos.link.kind", LINK_COMPENSATES),
            ("aos.attempt.no", compensated_attempt),
        )))

    covered = [identity_seq]
    if closed is not None:
        covered.append(closed["seq"])
    status = STATUS_UNSET
    if closed is not None:
        status = (
            STATUS_ERROR if closed["event"] == "compensation_failed"
            else STATUS_OK
        )
    return Span(
        span_id=c_span_id,
        parent_span_id=parent_span_id,
        trace_id=trace_id,
        name=SPAN_COMPENSATION,
        kind=SPAN_COMPENSATION,
        status=status,
        start_unix_nano=start_ns,
        end_unix_nano=end_ns,
        duration_seconds=duration_seconds(start_ns, end_ns),
        attributes=attrs.frozen(),
        links=tuple(links),
    ), tuple(covered)


def _build_logs(conn, row_id, identity, root, events, seq_to_span, spans,
                collector):
    """§5.4: EVERY workflow event becomes a LOG RECORD carrying `TraceId` and
    `SpanId`. U-E1 MINTS NO SPAN EVENTS AT ALL — the span-event API is
    deprecated and the guidance is "Prefer the Logs API" (D-v0.4.128).

    `ObservedTimestamp` comes from the base journal row `workflow_store._journal`
    wrote in the same transaction (§6.6); `Timestamp` comes from the event's
    own caller-asserted `created_at` (§6.5).
    """
    workflow_span = spans[0].span_id if spans else None
    observed = _observed_instants(conn, row_id, collector)
    out = []
    for record in events:
        severity_number, severity_text = _severity(record["event"])
        attrs = _Attributes()
        attrs.add("aos.workflow.id", identity)
        attrs.add("aos.workflow.event", record["event"])
        attrs.add("aos.workflow.seq", record["seq"])
        attrs.add("aos.workflow.revision", record["revision"])
        attrs.add("aos.workflow.policy_version", record["policy_version"])
        attrs.add("aos.workflow.from_state", record["from_state"])
        attrs.add("aos.workflow.to_state", record["to_state"])
        attrs.add("aos.workflow.command_id", record["command_id"])
        attrs.add("aos.workflow.command_sha256", record["command_sha256"])
        attrs.add("aos.workflow.event_sha256", record["content_sha256"])
        attrs.add("aos.workflow.actor", record["actor"])
        attrs.add("aos.data.classification", root.data_classification)
        _add_payload_attributes(attrs, record["payload"])
        collector.note("/log_record", attrs)
        # §5.5: `dispatch_rejected` and `dispatch_revoked` open NO attempt row,
        # so their record belongs to the WORKFLOW span. `seq_to_span` has no
        # entry for them, which is exactly the fallback below.
        bound_span = seq_to_span.get(record["seq"], workflow_span)
        out.append(LogRecord(
            event_name=EVENT_NAME_PREFIX + record["event"],
            timestamp_unix_nano=to_unix_nano(record["created_at"]),
            observed_timestamp_unix_nano=to_unix_nano(
                observed.get(record["seq"])
            ),
            trace_id=root.trace_id,
            span_id=bound_span,
            severity_number=severity_number,
            severity_text=severity_text,
            attributes=attrs.frozen(),
        ))
    return tuple(out)


def _observed_instants(conn, row_id, collector) -> dict:
    """seq → the base `events.ts` of the journal row for that workflow event.

    `workflow_store._journal` writes exactly ONE base row per appended workflow
    event, and its `ts` comes from `utils.utc_now_iso()` — the codebase's only
    wall-clock read — inside the same transaction. That is a genuine
    observation time, not a second copy of the asserted one (§6.5).
    """
    from . import workflow_engine

    out: dict[int, str] = {}
    for row in _fetchall(conn, _SQL_JOURNAL_FOR, (row_id,)):
        action = _text(row[5])
        if action not in workflow_engine.WORKFLOW_EVENTS:
            continue
        payload = _parse_payload(row[6])
        if payload is None:
            collector.unread("/events/payload_json", "journal_row_unreadable")
            continue
        seq = _count(payload.get("seq"))
        instant = _text(row[1])
        if seq is None or instant is None or to_unix_nano(instant) is None:
            continue
        out.setdefault(seq, instant)
    return out


# ---------------------------------------------------------------------------
# The whole-base-journal log projection (§6.6)

def project_journal(conn) -> tuple:
    """Every base `events` row as a log record.

    The base journal is written by migrations, backup, hook ingest, pack
    build, routing, catalog, passports, export and handoffs as well as by
    workflows, so this covers ALL of it. A row with no workflow entity gets no
    `TraceId`/`SpanId` and is emitted UNBOUND — inventing a trace root for a
    migration would be manufacturing identity (§20.5).

    One table, one existing redaction choke point (`events.emit` →
    `secretscan.redact_tree`), and no new instrumentation anywhere.
    """
    from . import workflow_engine

    roots: dict[int, TraceRoot] = {}
    out = []
    for row in _fetchall(conn, _SQL_JOURNAL_ALL):
        row_id = _count(row[0])
        action = _text(row[5])
        if row_id is None or action is None:
            # An unreadable journal row is SKIPPED, not guessed. There is no
            # per-workflow report to attach it to — this projection spans the
            # whole journal — and a fabricated placeholder row would claim
            # something happened that the ledger does not record.
            continue
        payload = _parse_payload(row[6]) or {}
        entity = _text(row[3])
        entity_id = _count(row[4])

        trace_id = None
        span = None
        if entity == "workflow" and entity_id is not None:
            root = roots.get(entity_id)
            if root is None:
                stored = _fetchone(conn, _SQL_WORKFLOW, (entity_id,))
                root = (
                    resolve_trace_root(stored[3]) if stored is not None
                    else _UNRESOLVED_ROOT
                )
                roots[entity_id] = root
            trace_id = root.trace_id
            if trace_id is not None:
                span = workflow_span_id(
                    trace_id, render_workflow_id(entity_id)
                )

        is_workflow_event = action in workflow_engine.WORKFLOW_EVENTS
        if is_workflow_event:
            severity_number, severity_text = _severity(action)
            event_name = EVENT_NAME_PREFIX + action
        elif action == JOURNAL_REFUSAL_ACTION:
            # §6.4's fourth row: a projected CLI refusal is WARN.
            severity_number, severity_text = SEVERITY_WARN
            event_name = JOURNAL_EVENT_NAME_PREFIX + action
        else:
            severity_number, severity_text = SEVERITY_INFO
            event_name = JOURNAL_EVENT_NAME_PREFIX + action

        attrs = _Attributes()
        attrs.add("aos.journal.row_id", row_id)
        attrs.add("aos.journal.entity", entity)
        attrs.add("aos.journal.entity_id", entity_id)
        attrs.add("aos.journal.action", action)
        attrs.add("aos.workflow.actor", _text(row[2]))
        if entity == "workflow" and entity_id is not None:
            attrs.add("aos.workflow.id", render_workflow_id(entity_id))
        if is_workflow_event:
            attrs.add("aos.workflow.event", action)
        for member, key in _JOURNAL_PAYLOAD_ATTRIBUTES:
            if member in payload:
                attrs.add(key, payload[member])

        out.append(LogRecord(
            event_name=event_name,
            timestamp_unix_nano=None,
            observed_timestamp_unix_nano=to_unix_nano(_text(row[1])),
            trace_id=trace_id,
            span_id=span,
            severity_number=severity_number,
            severity_text=severity_text,
            attributes=attrs.frozen(),
        ))
    return tuple(out)


# ---------------------------------------------------------------------------
# Metrics (§8). EVERY metric is a pure function of stored rows, computed by
# scan at read time. No accumulator, no counter column, no cached total.

METRIC_WORKFLOW_COUNT = "aos.workflow.count"
METRIC_EVENT_COUNT = "aos.workflow.event.count"
METRIC_ATTEMPT_COUNT = "aos.workflow.attempt.count"
METRIC_CHECKPOINT_COUNT = "aos.workflow.checkpoint.count"
METRIC_TRANSITION_DURATION = "aos.workflow.transition.duration"

INSTRUMENT_SUM = "sum"
INSTRUMENT_HISTOGRAM = "histogram"

#: §8.3: CUMULATIVE, always. Delta needs a durable accumulator and therefore a
#: reset model, and the reset/gap machinery is Development-status.
TEMPORALITY_CUMULATIVE = "cumulative"

#: §8.2, closed. Names follow the semantic-convention rules: lowercase,
#: `.`-namespaced, no unit in the name, no `_total` suffix on counters, `aos.`
#: prefix (`otel.*` is reserved). Units use the curly-brace annotation form for
#: dimensionless counts.
METRIC_INVENTORY: tuple[tuple[str, str, bool, str, tuple], ...] = (
    (METRIC_WORKFLOW_COUNT, INSTRUMENT_SUM, True, "{workflow}",
     ("aos.workflow.state",)),
    (METRIC_EVENT_COUNT, INSTRUMENT_SUM, True, "{event}",
     ("aos.workflow.event",)),
    (METRIC_ATTEMPT_COUNT, INSTRUMENT_SUM, True, "{attempt}",
     ("aos.attempt.state",)),
    (METRIC_CHECKPOINT_COUNT, INSTRUMENT_SUM, True, "{checkpoint}", ()),
    (METRIC_TRANSITION_DURATION, INSTRUMENT_HISTOGRAM, False, "s",
     ("aos.workflow.event",)),
)

#: Explicit histogram bucket boundaries, in seconds. Second precision is all
#: the ledger has (§20.1), so the first boundary is 0 — a workflow faster than
#: one second measures 0 s and lands there rather than being rounded up into a
#: bucket it did not earn.
HISTOGRAM_BOUNDS = (0, 1, 5, 15, 60, 300, 1800, 7200, 86400)


def _bucket_index(value: int) -> int:
    for index, bound in enumerate(HISTOGRAM_BOUNDS):
        if value <= bound:
            return index
    return len(HISTOGRAM_BOUNDS)


def project_metrics(conn) -> MetricsProjection:
    """The five metrics, recomputed by scan (§8.1).

    `StartTimeUnixNano` is LEDGER GENESIS — the earliest base `events.ts` in
    the workspace — not process start, because there is no process; the ledger
    is the accumulating thing (§8.3). A database restored from backup
    legitimately reports that ledger's genesis, which is exactly the data
    model's "a new unbroken sequence of observations begins".
    """
    from . import workflow_engine

    collector = _Collector()
    genesis = _fetchone(conn, _SQL_GENESIS)
    latest = _fetchone(conn, _SQL_LATEST)
    start_ns = to_unix_nano(_text(genesis[0]) if genesis else None)
    now_ns = to_unix_nano(_text(latest[0]) if latest else None)

    states = {state: 0 for state in workflow_engine.WORKFLOW_STATES}
    for row in _fetchall(conn, f"SELECT state FROM {db.WORKFLOWS_TABLE}"):
        state = _text(row[0])
        if state in states:
            states[state] += 1

    event_counts = {name: 0 for name in workflow_engine.WORKFLOW_EVENTS}
    durations: dict[str, list[int]] = {
        name: [] for name in workflow_engine.WORKFLOW_EVENTS
    }
    previous: dict[int, str] = {}
    for row in _fetchall(
        conn,
        "SELECT workflow_id, seq, event, created_at FROM "
        f"{db.WORKFLOW_EVENTS_TABLE} ORDER BY workflow_id, seq",
    ):
        workflow_row = _count(row[0])
        event = _text(row[2])
        instant = _text(row[3])
        if event not in event_counts or workflow_row is None:
            collector.unread("/workflow_events", "event_row_unreadable")
            continue
        event_counts[event] += 1
        if instant is None or to_unix_nano(instant) is None:
            previous.pop(workflow_row, None)
            continue
        earlier = previous.get(workflow_row)
        if earlier is not None:
            # Successive `created_at` deltas per workflow, clamped at 0 — the
            # same clamp §6.5 applies to every duration in this module.
            durations[event].append(
                duration_seconds(to_unix_nano(earlier), to_unix_nano(instant))
            )
        previous[workflow_row] = instant

    attempt_states = {
        state: 0 for state in workflow_engine.WORKFLOW_ATTEMPT_STATES
    }
    for row in _fetchall(
        conn, f"SELECT state FROM {db.WORKFLOW_ATTEMPTS_TABLE}"
    ):
        state = _text(row[0])
        if state in attempt_states:
            attempt_states[state] += 1

    checkpoints = _fetchone(
        conn, f"SELECT COUNT(*) FROM {db.WORKFLOW_CHECKPOINTS_TABLE}"
    )
    checkpoint_total = _count(checkpoints[0]) if checkpoints else 0

    metrics = (
        _sum_metric(METRIC_WORKFLOW_COUNT, "{workflow}",
                    "aos.workflow.state", states),
        _sum_metric(METRIC_EVENT_COUNT, "{event}",
                    "aos.workflow.event", event_counts),
        _sum_metric(METRIC_ATTEMPT_COUNT, "{attempt}",
                    "aos.attempt.state", attempt_states),
        Metric(
            name=METRIC_CHECKPOINT_COUNT,
            instrument=INSTRUMENT_SUM,
            unit="{checkpoint}",
            monotonic=True,
            temporality=TEMPORALITY_CUMULATIVE,
            dimensions=(),
            points=(MetricPoint((), value=checkpoint_total or 0),),
        ),
        _histogram_metric(durations),
    )
    return MetricsProjection(
        start_unix_nano=start_ns,
        time_unix_nano=now_ns,
        metrics=metrics,
        unreadable=tuple(collector.unreadable),
    )


def _sum_metric(name, unit, dimension, counts) -> Metric:
    points = tuple(
        MetricPoint(((dimension, key),), value=value)
        for key, value in counts.items()
        if value
    )
    return Metric(
        name=name,
        instrument=INSTRUMENT_SUM,
        unit=unit,
        monotonic=True,
        temporality=TEMPORALITY_CUMULATIVE,
        dimensions=(dimension,),
        points=points,
    )


def _histogram_metric(durations) -> Metric:
    points = []
    for event, values in durations.items():
        if not values:
            continue
        buckets = [0] * (len(HISTOGRAM_BOUNDS) + 1)
        for value in values:
            buckets[_bucket_index(value)] += 1
        points.append(MetricPoint(
            (("aos.workflow.event", event),),
            count=len(values),
            sum=sum(values),
            bucket_counts=tuple(buckets),
        ))
    return Metric(
        name=METRIC_TRANSITION_DURATION,
        instrument=INSTRUMENT_HISTOGRAM,
        unit="s",
        monotonic=False,
        temporality=TEMPORALITY_CUMULATIVE,
        dimensions=("aos.workflow.event",),
        points=tuple(points),
    )


# ---------------------------------------------------------------------------
# Resource (§6.7) — closed, five members, NO HOST IDENTITY.

def resource(workspace_path) -> dict:
    """`service.instance.id` is a DIGEST of the workspace path, never the path:
    a path is a filesystem fact about a person's machine. No hostname, no
    username, no IP, no MAC, no process id, ever."""
    from . import __version__

    return {
        "service.name": "agentic-os",
        "service.version": __version__,
        "service.instance.id": hashlib.sha256(
            str(workspace_path).encode("utf-8")
        ).hexdigest()[:32],
        "telemetry.sdk.name": "agentic-os-observability",
        "telemetry.sdk.language": "python",
    }


def scope() -> dict:
    from . import __version__

    return {"name": SCOPE_NAME, "version": __version__}


# ---------------------------------------------------------------------------
# OTLP/JSON (§9.5). The ENCODING is pinned because it is stable; the FILE
# LAYOUT is AOS's own, because the File Exporter document is not stability
# frozen and pinning to it would be depending on a moving target.

_OTLP_STATUS_CODE = {STATUS_UNSET: 0, STATUS_OK: 1, STATUS_ERROR: 2}

#: OTLP/JSON maps 64-bit integers to STRINGS. Nanosecond instants exceed
#: `protocols.INT_MAX` (2**53-1), so the string mapping is both the spec's rule
#: and the only representation canonical JSON will accept.
def _u64(value) -> str:
    return "0" if value is None else str(value)


def _otlp_attributes(attributes) -> list:
    out = []
    for key, value in attributes:
        if isinstance(value, bool):
            body = {"boolValue": value}
        elif isinstance(value, int):
            body = {"intValue": str(value)}
        else:
            body = {"stringValue": value}
        out.append({"key": key, "value": body})
    return out


def _otlp_resource(workspace_path) -> dict:
    return {
        "attributes": _otlp_attributes(
            tuple(sorted(resource(workspace_path).items()))
        )
    }


def _otlp_link(link: Link) -> dict:
    return {
        "traceId": link.trace_id,
        "spanId": link.span_id or "",
        "attributes": _otlp_attributes(link.attributes),
    }


def _otlp_span(span: Span) -> dict:
    body = {
        "traceId": span.trace_id,
        "spanId": span.span_id,
        "name": span.name,
        # SPAN_KIND_INTERNAL: AOS observes its own ledger. There is no remote
        # peer, no client, no server and no messaging system here.
        "kind": 1,
        "startTimeUnixNano": _u64(span.start_unix_nano),
        "endTimeUnixNano": _u64(span.end_unix_nano),
        "attributes": _otlp_attributes(span.attributes),
        "status": {"code": _OTLP_STATUS_CODE[span.status]},
        "flags": TRACE_FLAGS,
    }
    if span.parent_span_id is not None:
        body["parentSpanId"] = span.parent_span_id
    if span.links:
        body["links"] = [_otlp_link(link) for link in span.links]
    return body


def otlp_traces(spans, workspace_path) -> dict:
    return {
        "resourceSpans": [{
            "resource": _otlp_resource(workspace_path),
            "scopeSpans": [{
                "scope": scope(),
                "spans": [_otlp_span(span) for span in spans],
            }],
        }]
    }


def _otlp_log(record: LogRecord) -> dict:
    body = {
        "timeUnixNano": _u64(record.effective_timestamp_unix_nano),
        "observedTimeUnixNano": _u64(record.observed_timestamp_unix_nano),
        "severityNumber": record.severity_number,
        "severityText": record.severity_text,
        "eventName": record.event_name,
        # ALWAYS empty (§7.3). There is no flag that fills it.
        "body": {},
        "attributes": _otlp_attributes(record.attributes),
        "flags": record.trace_flags,
    }
    if record.trace_id is not None:
        body["traceId"] = record.trace_id
    if record.span_id is not None:
        body["spanId"] = record.span_id
    return body


def otlp_logs(records, workspace_path) -> dict:
    return {
        "resourceLogs": [{
            "resource": _otlp_resource(workspace_path),
            "scopeLogs": [{
                "scope": scope(),
                "logRecords": [_otlp_log(record) for record in records],
            }],
        }]
    }


#: AGGREGATION_TEMPORALITY_CUMULATIVE.
_OTLP_CUMULATIVE = 2


def _otlp_metric(metric: Metric, start_ns, now_ns) -> dict:
    body: dict = {"name": metric.name, "unit": metric.unit}
    if metric.instrument == INSTRUMENT_SUM:
        body["sum"] = {
            "dataPoints": [
                {
                    "attributes": _otlp_attributes(point.attributes),
                    "startTimeUnixNano": _u64(start_ns),
                    "timeUnixNano": _u64(now_ns),
                    "asInt": str(point.value),
                }
                for point in metric.points
            ],
            "aggregationTemporality": _OTLP_CUMULATIVE,
            "isMonotonic": metric.monotonic,
        }
        return body
    body["histogram"] = {
        "dataPoints": [
            {
                "attributes": _otlp_attributes(point.attributes),
                "startTimeUnixNano": _u64(start_ns),
                "timeUnixNano": _u64(now_ns),
                "count": str(point.count),
                "sum": point.sum,
                "bucketCounts": [str(c) for c in point.bucket_counts],
                "explicitBounds": list(HISTOGRAM_BOUNDS),
            }
            for point in metric.points
        ],
        "aggregationTemporality": _OTLP_CUMULATIVE,
    }
    return body


def otlp_metrics(projection: MetricsProjection, workspace_path) -> dict:
    return {
        "resourceMetrics": [{
            "resource": _otlp_resource(workspace_path),
            "scopeMetrics": [{
                "scope": scope(),
                "metrics": [
                    _otlp_metric(
                        metric,
                        projection.start_unix_nano,
                        projection.time_unix_nano,
                    )
                    for metric in projection.metrics
                ],
            }],
        }]
    }


# ---------------------------------------------------------------------------
# The export capsule (§9.5)

def export_documents(conn, workflow_id, workspace_path) -> dict:
    """The three OTLP/JSON documents plus a sealed manifest, as a mapping of
    file name → document.

    `secretscan.redact_tree` is applied to the whole capsule before it is
    returned — DEFENCE IN DEPTH, not the primary control, which is §7.2's
    grammar. The manifest's `content_sha256` is computed by
    `protocols.content_digest` over the redacted bytes, so the seal covers
    exactly what is written.
    """
    projection = project_workflow(conn, workflow_id)
    metrics = project_metrics(conn)
    records = projection.logs
    truncated = list(projection.truncated)
    if len(records) > MAX_LOG_RECORDS_PER_DOCUMENT:
        records = records[:MAX_LOG_RECORDS_PER_DOCUMENT]
        truncated.append(
            ("log_records_per_document", MAX_LOG_RECORDS_PER_DOCUMENT)
        )
    traces = secretscan.redact_tree(
        otlp_traces(projection.spans, workspace_path)
    )
    logs = secretscan.redact_tree(otlp_logs(records, workspace_path))
    metrics_document = secretscan.redact_tree(
        otlp_metrics(metrics, workspace_path)
    )
    manifest = {
        "schema": EXPORT_SCHEMA,
        "workflow_id": projection.workflow_id,
        "trace_root": projection.trace_root,
        "generator": SCOPE_NAME,
        "generator_version": scope()["version"],
        # §4.6, stated in our own exported metadata so no consumer has to
        # infer it: our identifiers are derived, and the flag is never set.
        "deterministic_identifiers": True,
        "random_trace_id_flag": False,
        "resource": resource(workspace_path),
        "span_count": len(projection.spans),
        "log_record_count": len(records),
        "metric_count": len(metrics.metrics),
        "metric_series_count": metrics.series,
        # `canonical_sha256`/`canonical_bytes` describe the CANONICAL BODY, not
        # the file: the single trailing newline a file gets is not part of the
        # hashed body (`protocols.serialize_canonical_file_bytes`). Naming them
        # `sha256`/`bytes` would invite a consumer to hash the file and get a
        # mismatch, so they say what they are.
        "files": [
            {
                "name": name,
                "canonical_sha256": hashlib.sha256(
                    protocols.serialize_canonical(document)
                ).hexdigest(),
                "canonical_bytes": len(protocols.serialize_canonical(document)),
            }
            for name, document in (
                (EXPORT_TRACES, traces),
                (EXPORT_LOGS, logs),
                (EXPORT_METRICS, metrics_document),
            )
        ],
        "unreadable": [
            {"where": where, "code": code}
            for where, code in projection.unreadable
        ],
        "truncated": [
            {"bound": what, "limit": limit} for what, limit in truncated
        ],
    }
    if projection.trace_id is not None:
        manifest["trace_id"] = projection.trace_id
    manifest[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(manifest)
    return {
        EXPORT_TRACES: traces,
        EXPORT_LOGS: logs,
        EXPORT_METRICS: metrics_document,
        EXPORT_MANIFEST: manifest,
    }


def document_bytes(document) -> bytes:
    """Canonical bytes plus the single trailing newline a file gets."""
    return protocols.serialize_canonical_file_bytes(document)


def oversize_documents(documents) -> tuple:
    """Names of documents exceeding `MAX_EXPORT_DOCUMENT_BYTES` (§6.10)."""
    return tuple(
        name for name, document in documents.items()
        if len(document_bytes(document)) > MAX_EXPORT_DOCUMENT_BYTES
    )


# ---------------------------------------------------------------------------
# Verification (§9.2, §10)

def verify(conn, workflow_id=None) -> tuple:
    """Report — never repair (§10, §14.6).

    Divergence is a REPORT, not a failure: `observe verify` exits 0 when it
    finds it (D-v0.3.22 / D-v0.4.44 — a check that turns red because history
    happened is a broken check). A digest that does not recompute is listed and
    left exactly as stored.
    """
    if workflow_id is not None:
        row_ids = [parse_workflow_id(workflow_id)]
        if _fetchone(conn, _SQL_WORKFLOW, (row_ids[0],)) is None:
            raise ObservabilityError(
                f"No workflow {render_workflow_id(row_ids[0])}. "
                "Run: python aos.py workflow list"
            )
    else:
        row_ids = [
            _count(row[0]) for row in _fetchall(conn, _SQL_WORKFLOW_IDS)
        ]
        row_ids = [value for value in row_ids if value is not None]

    reports = []
    for row_id in row_ids:
        identity = render_workflow_id(row_id)
        projection = project_workflow(conn, identity)
        divergent = _divergent_rows(conn, row_id)
        reports.append(VerifyReport(
            workflow_id=identity,
            trace_root=projection.trace_root,
            divergent=divergent,
            unreadable=projection.unreadable,
            truncated=projection.truncated,
            clock_inconsistent=projection.clock_inconsistent,
            span_count=len(projection.spans),
            log_count=len(projection.logs),
        ))
    return tuple(reports)


def _divergent_rows(conn, row_id) -> tuple:
    """Digests RECOMPUTED FROM THE STORED BYTES at every use, never trusted
    from a column (§10.2). The rows checked are exactly the three whose stored
    body is bound by a digest column rather than by a row hash."""
    out = []
    for table, sql, doc_index, digest_index in (
        (db.WORKFLOW_CHECKPOINTS_TABLE, _SQL_CHECKPOINTS, 3, 4),
        (db.WORKFLOW_FACTS_TABLE, _SQL_FACTS, 3, 4),
        (db.WORKFLOW_RECEIPTS_TABLE, _SQL_RECEIPTS, 2, 3),
    ):
        for index, row in enumerate(_fetchall(conn, sql, (row_id,)), start=1):
            stored = row[doc_index]
            declared = _matching(row[digest_index], _SHA256_RE)
            if not isinstance(stored, str):
                out.append((table, index, "row_unreadable"))
                continue
            document = _parse_document(stored)
            if document is None:
                out.append((table, index, "document_unparseable"))
                continue
            if declared is None or protocols.content_digest(document) != declared:
                out.append((table, index, "digest_divergent"))
    return tuple(out)


# ---------------------------------------------------------------------------
# Doctor support (§9.4)

def unresolvable_trace_roots(conn) -> tuple:
    """Check 42's finding: every `workflows` row must yield a parseable
    `work_spec_document.trace` with a non-zero 32-hex `trace_id`.

    This is a STORED-ROW integrity problem, not an observability problem, which
    is why the recovery instruction points at `workflow verify` and RECOVERY.md
    rather than at anything `observe` could do. `observe` never repairs a
    stored row.
    """
    out = []
    for row in _fetchall(conn, _SQL_WORKFLOW_IDS):
        row_id = _count(row[0])
        if row_id is None:
            continue
        stored = _fetchone(conn, _SQL_WORKFLOW, (row_id,))
        if stored is None:  # pragma: no cover - the id came from this table
            continue
        root = resolve_trace_root(stored[3])
        if root.trace_id is None:
            out.append((render_workflow_id(row_id), root.code))
    return tuple(out)


def bound_violations_for(projection: WorkflowProjection) -> tuple:
    """Check 43's finding for ONE projection (§6.10's span, link, attribute
    and record bounds).

    Factored out so that check 43 and §9.6's deep-mode preflight on
    `observe trace` share ONE predicate: a preflight that could disagree with
    the doctor check it claims to be would be worse than no preflight.
    """
    identity = projection.workflow_id
    out = [
        (identity, what, limit) for what, limit in projection.truncated
    ]
    if len(projection.spans) > MAX_SPANS_PER_WORKFLOW:
        out.append((identity, "spans_per_workflow", MAX_SPANS_PER_WORKFLOW))
    for span in projection.spans:
        if len(span.links) > MAX_LINKS_PER_SPAN:
            out.append((identity, "links_per_span", MAX_LINKS_PER_SPAN))
        if len(span.attributes) > MAX_ATTRIBUTES_PER_RECORD:
            out.append((
                identity, "attributes_per_record", MAX_ATTRIBUTES_PER_RECORD,
            ))
    for record in projection.logs:
        if len(record.attributes) > MAX_ATTRIBUTES_PER_RECORD:
            out.append((
                identity, "attributes_per_record", MAX_ATTRIBUTES_PER_RECORD,
            ))
    return tuple(out)


def bound_violations(conn) -> tuple:
    """Check 43's finding (warn-only): every workflow's projection stays
    inside §6.10's span, link, attribute and byte bounds."""
    out = []
    for row in _fetchall(conn, _SQL_WORKFLOW_IDS):
        row_id = _count(row[0])
        if row_id is None:
            continue
        out.extend(bound_violations_for(
            project_workflow(conn, render_workflow_id(row_id))
        ))
    return tuple(out)


# ---------------------------------------------------------------------------
# Rendering (§9.3). Every hop — task → workflow → trace → span → link → log —
# on one screen, and no raw SQL at any point.

def render_trace(projection: WorkflowProjection) -> list:
    lines = [
        f"{'task':<14}{projection.task_id or '-'}",
        f"{'workflow':<14}{projection.workflow_id}   "
        f"{projection.state or '-'}   rev {projection.revision or '-'}   "
        f"policy {projection.policy_version or '-'}",
        f"{'trace':<14}{projection.trace_id or '-'}"
        f"          (root: {projection.trace_root}, derived)",
        f"{'workspec':<14}sha256 {projection.work_spec_sha256 or '-'}",
        "",
    ]
    logs_by_span: dict[str, list] = {}
    for record in projection.logs:
        logs_by_span.setdefault(record.span_id or "", []).append(record)
    for span in projection.spans:
        # The workflow span's `name` is its WF id (§4.1); the render shows the
        # kind there instead, because the id is already on the header line.
        label = SPAN_WORKFLOW if span.kind == SPAN_WORKFLOW else span.name
        lines.append(
            f"  span  {label:<14} {span.span_id}   "
            f"{span.duration_seconds}s   {span.status}"
        )
        for link in span.links:
            lines.append(
                f"    link  {link.kind:<14} -> {link.span_id or '-'}"
            )
        for record in logs_by_span.get(span.span_id, ()):
            attributes = dict(record.attributes)
            suffix = ""
            reason = attributes.get("aos.reason.code")
            if reason is not None:
                suffix = f"   reason={reason}"
            lines.append(
                f"    log   {record.event_name[len(EVENT_NAME_PREFIX):]:<24} "
                f"seq {attributes.get('aos.workflow.seq', '-')}   "
                f"{record.severity_text}{suffix}"
            )
    for where, code in projection.unreadable:
        lines.append(f"  unreadable  {where}  {code}")
    for what, limit in projection.truncated:
        lines.append(f"  truncated   {what}  at {limit}")
    return lines


def projection_document(projection: WorkflowProjection) -> dict:
    """The canonical projection document `--json` prints (§9.3)."""
    return {
        "workflow_id": projection.workflow_id,
        "trace_root": projection.trace_root,
        "trace_id": projection.trace_id,
        "task_id": projection.task_id,
        "state": projection.state,
        "revision": projection.revision,
        "policy_version": projection.policy_version,
        "data_classification": projection.data_classification,
        "work_spec_sha256": projection.work_spec_sha256,
        "clock_inconsistent": projection.clock_inconsistent,
        "spans": [
            {
                "span_id": span.span_id,
                "parent_span_id": span.parent_span_id,
                "trace_id": span.trace_id,
                "name": span.name,
                "kind": span.kind,
                "status": span.status,
                "duration_seconds": span.duration_seconds,
                "attributes": [
                    {"key": key, "value": value}
                    for key, value in span.attributes
                ],
                "links": [
                    {
                        "kind": link.kind,
                        "trace_id": link.trace_id,
                        "span_id": link.span_id,
                        "attributes": [
                            {"key": key, "value": value}
                            for key, value in link.attributes
                        ],
                    }
                    for link in span.links
                ],
            }
            for span in projection.spans
        ],
        "logs": [
            {
                "event_name": record.event_name,
                "timestamp_unix_nano": _u64(record.timestamp_unix_nano),
                "observed_timestamp_unix_nano": _u64(
                    record.observed_timestamp_unix_nano
                ),
                "trace_id": record.trace_id,
                "span_id": record.span_id,
                "trace_flags": record.trace_flags,
                "severity_number": record.severity_number,
                "severity_text": record.severity_text,
                "body": record.body,
                "attributes": [
                    {"key": key, "value": value}
                    for key, value in record.attributes
                ],
            }
            for record in projection.logs
        ],
        "unreadable": [
            {"where": where, "code": code}
            for where, code in projection.unreadable
        ],
        "truncated": [
            {"bound": what, "limit": limit}
            for what, limit in projection.truncated
        ],
    }


def metrics_document(projection: MetricsProjection) -> dict:
    return {
        "start_unix_nano": _u64(projection.start_unix_nano),
        "time_unix_nano": _u64(projection.time_unix_nano),
        "temporality": TEMPORALITY_CUMULATIVE,
        "series_ceiling": MAX_METRIC_SERIES,
        "series": projection.series,
        "metrics": [
            {
                "name": metric.name,
                "instrument": metric.instrument,
                "unit": metric.unit,
                "monotonic": metric.monotonic,
                "temporality": metric.temporality,
                "dimensions": list(metric.dimensions),
                "points": [
                    {
                        "attributes": [
                            {"key": key, "value": value}
                            for key, value in point.attributes
                        ],
                        "value": point.value,
                        "count": point.count,
                        "sum": point.sum,
                        "bucket_counts": list(point.bucket_counts),
                    }
                    for point in metric.points
                ],
            }
            for metric in projection.metrics
        ],
        "unreadable": [
            {"where": where, "code": code}
            for where, code in projection.unreadable
        ],
    }


def verify_document(reports) -> dict:
    return {
        "workflows": [
            {
                "workflow_id": report.workflow_id,
                "trace_root": report.trace_root,
                "ok": report.ok,
                "span_count": report.span_count,
                "log_count": report.log_count,
                "clock_inconsistent": report.clock_inconsistent,
                "divergent": [
                    {"table": table, "row": row, "code": code}
                    for table, row, code in report.divergent
                ],
                "unreadable": [
                    {"where": where, "code": code}
                    for where, code in report.unreadable
                ],
                "truncated": [
                    {"bound": what, "limit": limit}
                    for what, limit in report.truncated
                ],
            }
            for report in reports
        ]
    }
