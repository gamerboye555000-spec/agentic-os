"""U-K1/U-T1 governed skill and tool foundations.

Contract: agentic-os-v0.4-u-k1-u-t1-governed-foundations-contract.md

The authority split is literal here and everything downstream of it is
deterministic code:

    manifest.required_capabilities          (declaration, untrusted)
    execution_context.granted_capabilities  (external grant)
    external policy input                   (approval/policy/budget refs,
                                             caller passport facts)
    deterministic policy decision           (evaluate_eligibility)

A manifest declares; it never grants. Eligibility requires
``required_capabilities ⊆ granted_capabilities`` plus every other gate, and
the decision is a typed value computed by this module — no model output is an
input to it, and no descriptive field (display_name, description,
recovery.note) participates.

Execution happens only through an implementation binding registered
explicitly in code and verified against the digest the manifest declares.
There is no import path, module string, command or URL anywhere in the
binding vocabulary, so "the manifest names it, something runs it" is
unrepresentable — this module performs no dynamic import, no exec, no shell,
no network and no filesystem access.

A deadline is not a cancellation: ``deadline_exceeded`` is a status about
lateness, and the separate termination outcome tells the truth about whether
work mechanically stopped. This unit's in-process runner can honestly emit
only ``not_started`` and ``completed``; the rest of the closed vocabulary
exists for future adapters that can prove more.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from types import MappingProxyType

from . import protocols
from .models import AGENT_CLASSES
from .utils import AosError, sha256_text, utc_now_iso

# ---------------------------------------------------------------------------
# Closed runtime vocabularies (contract §3). The schema-carried vocabularies
# (lifecycles, evaluation states, side effects, recovery actions, …) live in
# protocols.py beside the schemas; these are the runtime-only ones.

SKILL_KIND = "skill"
TOOL_KIND = "tool"
COMPONENT_KINDS = (SKILL_KIND, TOOL_KIND)

#: kind -> the registry schema its documents must validate against.
_MANIFEST_IDENTITIES = {
    SKILL_KIND: "beast.skill-manifest/v1",
    TOOL_KIND: "beast.tool-manifest/v1",
}

GOVERNANCE_DECISIONS = ("allow", "deny", "needs_approval", "unavailable", "invalid")

#: Closed eligibility reason codes. This order IS the canonical emission
#: order (the ROUTING_REASON_CODES rule): a decision's `reasons` tuple is
#: always this tuple filtered by membership, never set order.
GOVERNANCE_REASON_CODES = (
    "context_malformed",
    "unknown_component",
    "unknown_version",
    "lifecycle_not_active",
    "not_promoted",
    "binding_unknown",
    "binding_kind_mismatch",
    "binding_digest_mismatch",
    "dependency_blocked",
    "missing_capability",
    "agent_class_mismatch",
    "approval_required",
)

#: Decision precedence (contract §9): the decision is the highest-precedence
#: class with at least one reason. Reasons -> class membership:
_INVALID_REASONS = frozenset({"context_malformed"})
_DENY_REASONS = frozenset({"missing_capability", "agent_class_mismatch"})
_APPROVAL_REASONS = frozenset({"approval_required"})
_UNAVAILABLE_REASONS = frozenset(
    {
        "unknown_component",
        "unknown_version",
        "lifecycle_not_active",
        "not_promoted",
        "binding_unknown",
        "binding_kind_mismatch",
        "binding_digest_mismatch",
        "dependency_blocked",
    }
)

INVOCATION_STATUSES = (
    "success",
    "denied",
    "invalid_input",
    "deadline_exceeded",
    "transient_failure",
    "permanent_failure",
    "recovery_required",
    "dependency_blocked",
)

#: The only statuses `retryable` can ever derive True for.
RETRYABLE_STATUSES = ("deadline_exceeded", "transient_failure")

#: The truthful termination vocabulary (contract §11). The full set is the
#: protocol; LOCAL_TERMINATION_OUTCOMES is what this unit's in-process runner
#: can honestly produce — nothing here can prove a subprocess died or a
#: remote accepted a cancellation, so nothing here may say so.
TERMINATION_OUTCOMES = (
    "not_started",
    "completed",
    "cooperative_cancelled",
    "subprocess_terminated",
    "remote_cancellation_requested",
    "abandoned",
    "not_supported",
)
LOCAL_TERMINATION_OUTCOMES = ("not_started", "completed")

#: Closed invocation error codes (contract §10.4). Every failing result
#: carries exactly one; success carries none.
INVOCATION_ERROR_CODES = (
    "context_malformed",
    "governance_denied",
    "approval_required",
    "dependency_blocked",
    "unknown_component",
    "unknown_version",
    "input_not_canonical",
    "input_limit_exceeded",
    "idempotency_ref_required",
    "attempt_budget_exhausted",
    "deadline_before_start",
    "deadline_after_completion",
    "transient_execution_failure",
    "permanent_execution_failure",
    "unhandled_exception",
    "output_not_canonical",
    "output_limit_exceeded",
)

BINDING_KINDS = ("in_process", "metadata")
BINDING_KIND_IN_PROCESS = "in_process"
BINDING_KIND_METADATA = "metadata"

#: Record payload schemas (the aos.* record-hash house style).
BINDING_RECORD_SCHEMA = "aos.implementation-binding/v1"
ENVELOPE_RECORD_SCHEMA = "aos.governed-invocation/v1"
RESULT_RECORD_SCHEMA = "aos.governed-invocation-result/v1"
EVIDENCE_RECORD_SCHEMA = "aos.governed-invocation-evidence/v1"

#: Per-item codes of a passport requirement resolution (contract §14).
RESOLUTION_CODES = ("resolved", "unknown_component", "unknown_version")

#: Bound on granted_capabilities in one execution context — twice a
#: passport's 32-capability bound, so a grant assembled from two sources
#: still fits; anything larger is not an honest grant list.
MAX_GRANTED_CAPABILITIES = 64

#: The recovery actions that turn a permanent failure into
#: `recovery_required` (contract §12): the declared recovery needs an actor,
#: not merely a backoff.
_ESCALATING_RECOVERY_ACTIONS = frozenset(
    {"request_approval", "manual_intervention", "invoke_compensation"}
)


# ---------------------------------------------------------------------------
# Errors (the CatalogError idiom: closed reasons, value-free hints)

#: Closed reason vocabulary for governance refusals. Diagnostics are built
#: ONLY from these codes and a validated-identifier `where` — never from a
#: field value or an exception's text.
_REASON_HINTS: dict[str, str] = {
    "wrong_schema": "The document is not the manifest schema this registry holds.",
    "duplicate_component": "The registry already holds this component id and version.",
    "missing_dependency": "A declared dependency names no registered component.",
    "unknown_dependency_version": "A dependency pin names no registered version.",
    "dependency_cycle": "Skill dependencies form a cycle.",
    "malformed_requirement": (
        "A requirement ref must be a lowercase slug with an optional /vN pin."
    ),
    "unknown_component": "No such component id is registered.",
    "unknown_version": "No such component version is registered.",
    "duplicate_binding": "The binding registry already holds this binding id.",
    "malformed_binding": "The binding record does not match the closed binding shape.",
    "binding_callable_required": "An in_process binding must register exactly one callable.",
    "binding_callable_forbidden": "A metadata binding cannot register a callable.",
    "context_malformed": "The execution context does not match the closed context shape.",
    "registry_required": "This operation requires the named registry.",
    "unknown_component_kind": "Component kind must be 'skill' or 'tool'.",
    "malformed_previous_hash": "previous_sha256 must be 64 lowercase hex characters.",
}


class GovernanceError(AosError):
    """One bounded, actionable, value-free line. Exits 1 through AosError.

    `where` may carry only already-validated identifiers (a component ref, a
    binding id, a field NAME). No caller passes free text or a field value.
    """

    def __init__(self, reason: str, where: str = "") -> None:
        if reason not in _REASON_HINTS:
            raise KeyError(f"undeclared governance reason code: {reason!r}")
        self.reason = reason
        self.where = where
        prefix = f"governance: {where}: " if where else "governance: "
        super().__init__(prefix + _REASON_HINTS[reason])


class TransientExecutionError(Exception):
    """Raised by an in-process binding callable to report a transient
    failure. Its message is never copied into any envelope or evidence."""


class PermanentExecutionError(Exception):
    """Raised by an in-process binding callable to report a permanent
    failure. Its message is never copied into any envelope or evidence."""


# ---------------------------------------------------------------------------
# Pattern gates. All compiled from the frozen protocol patterns; all matched
# with fullmatch so a trailing newline can never sneak through (D-v0.2.3).

_REQUIREMENT_RE = re.compile(protocols.REQUIREMENT_PATTERN, re.ASCII)
_COMPONENT_ID_RE = re.compile(protocols.COMPONENT_ID_PATTERN, re.ASCII)
_CAPABILITY_RE = re.compile(protocols.CAPABILITY_PATTERN, re.ASCII)
_UUID_RE = re.compile(protocols.UUID_PATTERN, re.ASCII)
_SHA256_RE = re.compile(protocols.SHA256_PATTERN, re.ASCII)
_TIMESTAMP_RE = re.compile(protocols.RFC3339_PATTERN, re.ASCII)
_TRACE_ID_RE = re.compile(protocols.TRACE_ID_PATTERN, re.ASCII)
_AOS_TASK_ID_RE = re.compile(protocols.AOS_TASK_ID_PATTERN, re.ASCII)
_IDEMPOTENCY_RE = re.compile(protocols.IDEMPOTENCY_KEY_PATTERN, re.ASCII)
_OPAQUE_REF_RE = re.compile(protocols.OPAQUE_REF_PATTERN, re.ASCII)
_PROVENANCE_RE = re.compile(protocols.PROVENANCE_PATTERN, re.ASCII)
_AGENT_NAME_RE = re.compile(protocols.AGENT_NAME_PATTERN, re.ASCII)


def parse_requirement(ref: str) -> tuple[str, int | None]:
    """'slug' -> ('slug', None); 'slug/v3' -> ('slug', 3). Strict."""
    if not isinstance(ref, str) or not _REQUIREMENT_RE.fullmatch(ref):
        raise GovernanceError("malformed_requirement")
    if "/" not in ref:
        return ref, None
    slug, version = ref.split("/", 1)
    return slug, int(version[1:])


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _instant_seconds(text: str) -> int:
    """A validated RFC3339 instant -> epoch seconds. Callers validate first."""
    moment = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    return int(moment.replace(tzinfo=timezone.utc).timestamp())


def _digest(payload: dict) -> str:
    return hashlib.sha256(protocols.serialize_canonical(payload)).hexdigest()


# ---------------------------------------------------------------------------
# Component registries (contract §7)

@dataclass(frozen=True)
class ComponentEntry:
    """One validated manifest, indexed. `document` is the exact validated
    artifact; `digest` is its verified content_sha256."""

    kind: str
    component_id: str
    component_version: int
    lifecycle: str
    evaluation: str | None
    binding_id: str
    binding_sha256: str
    document: dict
    digest: str

    @property
    def ref(self) -> str:
        return f"{self.component_id}/v{self.component_version}"


class ComponentRegistry:
    """A frozen, inert index of validated manifests. Nothing is imported,
    opened or executed at build time; building one is pure validation."""

    def __init__(self, kind: str, entries: dict[tuple[str, int], ComponentEntry]):
        self.kind = kind
        self._entries = MappingProxyType(dict(entries))
        versions: dict[str, list[int]] = {}
        for component_id, version in entries:
            versions.setdefault(component_id, []).append(version)
        self._versions = MappingProxyType(
            {cid: tuple(sorted(v)) for cid, v in versions.items()}
        )

    def ids(self) -> list[str]:
        return sorted(self._versions)

    def versions(self, component_id: str) -> tuple[int, ...]:
        return self._versions.get(component_id, ())

    def get(self, component_id: str, version: int) -> ComponentEntry | None:
        return self._entries.get((component_id, version))

    def entries(self) -> list[ComponentEntry]:
        """Every entry, ordered by (id, version). Stable across runs."""
        return [self._entries[key] for key in sorted(self._entries)]

    def resolve(self, ref: str) -> ComponentEntry:
        """Resolve a requirement ref (contract §7): an exact `/vN` pin or the
        highest registered version for a bare slug. Resolution never
        consults lifecycle — a deprecated latest resolves and is then
        DENIED by eligibility, so deprecation stays visible."""
        slug, version = parse_requirement(ref)
        known = self._versions.get(slug)
        if known is None:
            raise GovernanceError("unknown_component", where=ref)
        if version is None:
            version = known[-1]
        entry = self._entries.get((slug, version))
        if entry is None:
            raise GovernanceError("unknown_version", where=ref)
        return entry


def _try_resolve(
    registry: ComponentRegistry, ref: str
) -> tuple[ComponentEntry | None, str | None]:
    try:
        return registry.resolve(ref), None
    except GovernanceError as refusal:
        return None, refusal.reason


def _entry_from_document(kind: str, document) -> ComponentEntry:
    """Validate one manifest document and index it. A malformed document
    refuses with the U-X1 closed reason (ProtocolError); a valid document of
    the wrong identity refuses here."""
    if not isinstance(document, dict):
        raise GovernanceError("wrong_schema")
    entry = protocols.validate_document(document)
    expected = _MANIFEST_IDENTITIES[kind]
    if entry.identity != expected:
        raise GovernanceError("wrong_schema", where=expected)
    # Snapshot: the entry must alias nothing the caller passed in (the
    # routing EligibilityResult rule). A canonical round trip yields a
    # fresh, canonical-safe copy, so a caller-retained reference mutated
    # after the build can never alter a decision or stale the digest.
    document = protocols.parse_canonical(protocols.serialize_canonical(document))
    binding = document["binding"]
    return ComponentEntry(
        kind=kind,
        component_id=document[kind],
        component_version=document["component_version"],
        lifecycle=document["lifecycle"],
        evaluation=document.get("evaluation"),
        binding_id=binding["binding_id"],
        binding_sha256=binding["binding_sha256"],
        document=document,
        digest=document[protocols.CONTENT_HASH_FIELD],
    )


def _collect_entries(kind: str, documents) -> dict[tuple[str, int], ComponentEntry]:
    entries: dict[tuple[str, int], ComponentEntry] = {}
    for document in documents:
        candidate = _entry_from_document(kind, document)
        key = (candidate.component_id, candidate.component_version)
        if key in entries:
            raise GovernanceError("duplicate_component", where=candidate.ref)
        # Ambiguity-by-case is unrepresentable, not merely checked: the
        # component id pattern is lowercase-only ASCII, so two ids differing
        # only by case cannot both validate.
        entries[key] = candidate
    return entries


def _check_dependency(
    dependents: ComponentRegistry | dict[tuple[str, int], ComponentEntry],
    ref: str,
    *,
    where: str,
) -> tuple[str, int]:
    """Resolve a declared dependency during a registry build. Refuses with
    build-time codes; returns the resolved (id, version) key."""
    slug, version = parse_requirement(ref)
    if isinstance(dependents, ComponentRegistry):
        known = dependents.versions(slug)
    else:
        known = tuple(sorted(v for (cid, v) in dependents if cid == slug))
    if not known:
        raise GovernanceError("missing_dependency", where=f"{where}: {ref}")
    if version is None:
        version = known[-1]
    if version not in known:
        raise GovernanceError("unknown_dependency_version", where=f"{where}: {ref}")
    return slug, version


def build_tool_registry(documents) -> ComponentRegistry:
    """Validated tool manifests -> a frozen registry (contract §7)."""
    return ComponentRegistry(TOOL_KIND, _collect_entries(TOOL_KIND, documents))


def build_skill_registry(documents, tool_registry: ComponentRegistry) -> ComponentRegistry:
    """Validated skill manifests -> a frozen registry (contract §7).

    Every declared tool dependency must resolve in `tool_registry`, every
    skill dependency must resolve among the documents being registered, and
    the resolved skill->skill edges must be acyclic. All refusals are
    build-time and closed; nothing is deferred to a runtime surprise.
    """
    if not isinstance(tool_registry, ComponentRegistry) or (
        tool_registry.kind != TOOL_KIND
    ):
        raise GovernanceError("registry_required", where=TOOL_KIND)
    entries = _collect_entries(SKILL_KIND, documents)

    edges: dict[tuple[str, int], list[tuple[str, int]]] = {}
    for key in sorted(entries):
        entry = entries[key]
        for ref in entry.document.get("tool_dependencies", ()):
            _check_dependency(tool_registry, ref, where=entry.ref)
        resolved: list[tuple[str, int]] = []
        for ref in entry.document.get("skill_dependencies", ()):
            resolved.append(_check_dependency(entries, ref, where=entry.ref))
        edges[key] = resolved

    # Iterative three-color DFS in sorted order: deterministic detection,
    # no recursion limit to hit, and a cycle refuses with the entry it was
    # first seen from.
    state: dict[tuple[str, int], int] = {}  # 1 = on stack, 2 = done
    for root in sorted(edges):
        if state.get(root) == 2:
            continue
        stack: list[tuple[tuple[str, int], int]] = [(root, 0)]
        state[root] = 1
        while stack:
            node, index = stack[-1]
            children = edges[node]
            if index >= len(children):
                stack.pop()
                state[node] = 2
                continue
            stack[-1] = (node, index + 1)
            child = children[index]
            mark = state.get(child)
            if mark == 1:
                raise GovernanceError(
                    "dependency_cycle", where=entries[child].ref
                )
            if mark != 2:
                state[child] = 1
                stack.append((child, 0))

    return ComponentRegistry(SKILL_KIND, entries)


def registry_projection(registry: ComponentRegistry) -> dict:
    """A deterministic, canonical-serializable projection of a registry —
    the registry_index() idiom. Inert: ids, versions, states and digests
    only; never a document body and never a callable."""
    components = []
    for entry in registry.entries():
        item = {
            "component_id": entry.component_id,
            "component_version": entry.component_version,
            "lifecycle": entry.lifecycle,
            "manifest_sha256": entry.digest,
            "binding_id": entry.binding_id,
        }
        if entry.evaluation is not None:
            item["evaluation"] = entry.evaluation
        components.append(item)
    return {"kind": registry.kind, "components": components}


# ---------------------------------------------------------------------------
# Implementation bindings (contract §8)

_BINDING_REQUIRED_KEYS = frozenset(
    {
        "schema",
        "binding_id",
        "kind",
        "component_kind",
        "component_id",
        "component_version",
        "config",
    }
)


def validate_binding_record(record) -> dict:
    """Fail-closed validation of one binding record. Returns the record.

    The closed key set is exact — no extra key, no missing key — and every
    value is pattern- or enum-checked. The record shape carries no import
    path, module string, command, or URL field, so naming code is
    unrepresentable; `config` is free-form but must be canonical JSON v1
    material (no float, NaN, or non-representable value). `config` keys are
    not secret-name-linted — the record is trusted embedding input and is
    never emitted (only its digest is), so a credential-shaped config key
    leaks nowhere.
    """
    if not isinstance(record, dict) or set(record) != _BINDING_REQUIRED_KEYS:
        raise GovernanceError("malformed_binding")
    binding_id = record["binding_id"]
    if not isinstance(binding_id, str) or not _COMPONENT_ID_RE.fullmatch(binding_id):
        raise GovernanceError("malformed_binding")
    if record["schema"] != BINDING_RECORD_SCHEMA:
        raise GovernanceError("malformed_binding", where=binding_id)
    if record["kind"] not in BINDING_KINDS:
        raise GovernanceError("malformed_binding", where=binding_id)
    if record["component_kind"] not in COMPONENT_KINDS:
        raise GovernanceError("malformed_binding", where=binding_id)
    component_id = record["component_id"]
    if not isinstance(component_id, str) or not _COMPONENT_ID_RE.fullmatch(
        component_id
    ):
        raise GovernanceError("malformed_binding", where=binding_id)
    version = record["component_version"]
    if not _is_int(version) or not (
        1 <= version <= protocols.COMPONENT_VERSION_MAX
    ):
        raise GovernanceError("malformed_binding", where=binding_id)
    if not isinstance(record["config"], dict):
        raise GovernanceError("malformed_binding", where=binding_id)
    try:
        protocols.serialize_canonical(record)
    except protocols.ProtocolError:
        raise GovernanceError("malformed_binding", where=binding_id) from None
    return record


def binding_digest(record: dict) -> str:
    """sha256 over the canonical binding record — the digest a manifest's
    `binding.binding_sha256` must declare. The whole record is hashed; a
    binding record carries no self-hash field."""
    return _digest(validate_binding_record(record))


class BindingRegistry:
    """Explicit in-code registration only (contract §8). There is no
    discovery, no scan, no import-by-name and no way to register from data:
    a callable arrives as a Python object handed to register().

    Lookups are live by design — registering a binding later makes a
    previously-`binding_unknown` manifest eligible on the next evaluation.
    Records are snapshotted at registration, and verification recomputes
    the record digest at every evaluation, so no retained or returned
    reference can desync a record from the digest a manifest declares."""

    def __init__(self) -> None:
        self._records: dict[str, dict] = {}
        self._callables: dict[str, object] = {}

    def register(self, record: dict, callable_=None) -> str:
        """Register one binding; returns its record digest."""
        record = validate_binding_record(record)
        # The same snapshot rule as manifests: store a fresh canonical copy.
        record = protocols.parse_canonical(protocols.serialize_canonical(record))
        binding_id = record["binding_id"]
        if binding_id in self._records:
            raise GovernanceError("duplicate_binding", where=binding_id)
        if record["kind"] == BINDING_KIND_METADATA:
            if callable_ is not None:
                raise GovernanceError("binding_callable_forbidden", where=binding_id)
        else:
            if not callable(callable_):
                raise GovernanceError("binding_callable_required", where=binding_id)
        self._records[binding_id] = record
        if callable_ is not None:
            self._callables[binding_id] = callable_
        return _digest(record)

    def record(self, binding_id: str) -> dict | None:
        return self._records.get(binding_id)

    def callable_for(self, binding_id: str):
        return self._callables.get(binding_id)


def _binding_reason(
    entry: ComponentEntry, bindings: BindingRegistry
) -> str | None:
    """The single closed reason a manifest's binding fails verification, or
    None. Order (contract §8): registered -> binds this exact component ->
    digest matches the manifest's declaration. The digest is RECOMPUTED
    from the stored record here, never read from a cache, so a record
    tampered through any retained reference is a mismatch, not a pass."""
    record = bindings.record(entry.binding_id)
    if record is None:
        return "binding_unknown"
    if (
        record["component_kind"] != entry.kind
        or record["component_id"] != entry.component_id
        or record["component_version"] != entry.component_version
    ):
        return "binding_kind_mismatch"
    if _digest(record) != entry.binding_sha256:
        return "binding_digest_mismatch"
    return None


# ---------------------------------------------------------------------------
# Execution context (contract §10.1)

_CONTEXT_REQUIRED_KEYS = ("invocation_id", "principal", "granted_capabilities",
                          "max_attempts", "attempt")
_CONTEXT_OPTIONAL_KEYS = (
    "caller_agent",
    "caller_agent_class",
    "caller_passport_sha256",
    "aos_task_id",
    "deadline_at",
    "idempotency_ref",
    "approval_ref",
    "policy_ref",
    "budget_ref",
    "trace",
)
_CONTEXT_KEYS = frozenset(_CONTEXT_REQUIRED_KEYS) | frozenset(_CONTEXT_OPTIONAL_KEYS)


def _refuse_context(field: str) -> GovernanceError:
    # The refusal names the FIELD, never the value.
    return GovernanceError("context_malformed", where=field)


def _require_pattern(context: dict, field: str, regex) -> None:
    value = context[field]
    if not isinstance(value, str) or not regex.fullmatch(value):
        raise _refuse_context(field)


def validate_execution_context(raw) -> dict:
    """Fail-closed validation of an execution context. Returns a fresh dict
    holding exactly the accepted keys.

    The grant lives here and only here: `granted_capabilities` is the
    external authority input, and an unknown key, unknown enum member or
    malformed value refuses rather than defaulting.
    """
    if not isinstance(raw, dict):
        raise _refuse_context("context")
    for key in raw:
        # A non-string or undeclared key refuses with the FIXED name
        # "context": the key text is caller-controlled and never enters a
        # message, a `where`, or a diagnostics value.
        if not isinstance(key, str) or key not in _CONTEXT_KEYS:
            raise _refuse_context("context")
    for field in _CONTEXT_REQUIRED_KEYS:
        if field not in raw:
            raise _refuse_context(field)

    context = {key: raw[key] for key in raw}
    _require_pattern(context, "invocation_id", _UUID_RE)
    _require_pattern(context, "principal", _PROVENANCE_RE)

    granted = context["granted_capabilities"]
    if not isinstance(granted, list) or len(granted) > MAX_GRANTED_CAPABILITIES:
        raise _refuse_context("granted_capabilities")
    seen: set[str] = set()
    for capability in granted:
        if not isinstance(capability, str) or not _CAPABILITY_RE.fullmatch(capability):
            raise _refuse_context("granted_capabilities")
        if capability in seen:
            raise _refuse_context("granted_capabilities")
        seen.add(capability)

    max_attempts = context["max_attempts"]
    if not _is_int(max_attempts) or not (1 <= max_attempts <= 10):
        raise _refuse_context("max_attempts")
    attempt = context["attempt"]
    if not _is_int(attempt) or not (1 <= attempt <= max_attempts):
        raise _refuse_context("attempt")

    if "caller_agent" in context:
        _require_pattern(context, "caller_agent", _AGENT_NAME_RE)
    if "caller_agent_class" in context:
        if context["caller_agent_class"] not in AGENT_CLASSES:
            raise _refuse_context("caller_agent_class")
    if "caller_passport_sha256" in context:
        _require_pattern(context, "caller_passport_sha256", _SHA256_RE)
    if "aos_task_id" in context:
        _require_pattern(context, "aos_task_id", _AOS_TASK_ID_RE)
    if "deadline_at" in context:
        _require_pattern(context, "deadline_at", _TIMESTAMP_RE)
        try:
            _instant_seconds(context["deadline_at"])
        except ValueError:
            raise _refuse_context("deadline_at") from None
    if "idempotency_ref" in context:
        _require_pattern(context, "idempotency_ref", _IDEMPOTENCY_RE)
    for field in ("approval_ref", "policy_ref", "budget_ref"):
        if field in context:
            _require_pattern(context, field, _OPAQUE_REF_RE)

    if "trace" in context:
        trace = context["trace"]
        if not isinstance(trace, dict) or not (
            set(trace) <= {"trace_id", "correlation_id", "causation_id"}
        ):
            raise _refuse_context("trace")
        for field in ("trace_id", "correlation_id"):
            if field not in trace:
                raise _refuse_context("trace")
        trace_id = trace["trace_id"]
        if (
            not isinstance(trace_id, str)
            or not _TRACE_ID_RE.fullmatch(trace_id)
            or trace_id == "0" * 32
        ):
            raise _refuse_context("trace")
        for field in ("correlation_id", "causation_id"):
            if field in trace:
                value = trace[field]
                if not isinstance(value, str) or not _UUID_RE.fullmatch(value):
                    raise _refuse_context("trace")

    return context


# ---------------------------------------------------------------------------
# Eligibility (contract §9)

@dataclass(frozen=True)
class GovernanceDecision:
    """A typed policy decision. Never a bare Boolean, never model output."""

    decision: str
    reasons: tuple[str, ...]
    component: str
    diagnostics: dict


def _canonical_reasons(reasons: set[str]) -> tuple[str, ...]:
    return tuple(code for code in GOVERNANCE_REASON_CODES if code in reasons)


def _decide(reasons: set[str]) -> str:
    if reasons & _INVALID_REASONS:
        return "invalid"
    if reasons & _DENY_REASONS:
        return "deny"
    if reasons & _APPROVAL_REASONS:
        return "needs_approval"
    if reasons & _UNAVAILABLE_REASONS:
        return "unavailable"
    return "allow"


def _registry_for(kind: str, skills, tools) -> ComponentRegistry:
    if kind not in COMPONENT_KINDS:
        raise GovernanceError("unknown_component_kind")
    registry = skills if kind == SKILL_KIND else tools
    if not isinstance(registry, ComponentRegistry) or registry.kind != kind:
        raise GovernanceError("registry_required", where=kind)
    return registry


def _dependency_problems(
    entry: ComponentEntry,
    skills: ComponentRegistry | None,
    tools: ComponentRegistry | None,
    bindings: BindingRegistry,
) -> list[str]:
    """Every declared dependency (transitively, for skills) must itself be
    active, promoted (skills), and bound to a verified implementation.
    Returns the refs that are not, in deterministic order. A visited set
    bounds the walk even over a registry someone rebuilt with a cycle."""
    problems: list[str] = []
    seen: set[tuple[str, str, int]] = set()
    queue: list[ComponentEntry] = [entry]
    while queue:
        current = queue.pop(0)
        deps: list[tuple[str, ComponentRegistry | None]] = []
        if current.kind == SKILL_KIND:
            deps.extend(
                (ref, tools)
                for ref in current.document.get("tool_dependencies", ())
            )
            deps.extend(
                (ref, skills)
                for ref in current.document.get("skill_dependencies", ())
            )
        for ref, registry in deps:
            if registry is None:
                problems.append(ref)
                continue
            dependency, _ = _try_resolve(registry, ref)
            if dependency is None:
                problems.append(ref)
                continue
            key = (dependency.kind, dependency.component_id,
                   dependency.component_version)
            if key in seen:
                continue
            seen.add(key)
            blocked = dependency.lifecycle != protocols.COMPONENT_LIFECYCLE_ACTIVE
            if dependency.kind == SKILL_KIND and (
                dependency.evaluation != protocols.SKILL_EVALUATION_PROMOTED
            ):
                blocked = True
            if _binding_reason(dependency, bindings) is not None:
                blocked = True
            if blocked:
                problems.append(ref)
            queue.append(dependency)
    return problems


def evaluate_eligibility(
    kind: str,
    ref: str,
    *,
    skills: ComponentRegistry | None = None,
    tools: ComponentRegistry | None = None,
    bindings: BindingRegistry,
    context,
) -> GovernanceDecision:
    """The deterministic policy decision (contract §9). Pure: same inputs,
    same decision. All gates are evaluated where their inputs exist; every
    applicable reason is collected in canonical order; the decision is the
    highest-precedence failing class (invalid > deny > needs_approval >
    unavailable > allow)."""
    if kind == SKILL_KIND:
        registry = _registry_for(kind, skills, tools)
        _registry_for(TOOL_KIND, skills, tools)
    else:
        registry = _registry_for(kind, skills, tools)

    reasons: set[str] = set()
    diagnostics: dict = {}
    component = f"{kind}:{ref}" if isinstance(ref, str) else kind

    try:
        validated = validate_execution_context(context)
    except GovernanceError as refusal:
        reasons.add("context_malformed")
        diagnostics["malformed_field"] = refusal.where
        return GovernanceDecision(
            decision="invalid",
            reasons=_canonical_reasons(reasons),
            component=component,
            diagnostics=diagnostics,
        )

    entry, code = _try_resolve(registry, ref)
    if entry is None:
        # `malformed_requirement` folds into unknown_component: a ref that
        # cannot name a component names no component. Fail closed, never
        # filtered out.
        if code not in ("unknown_component", "unknown_version"):
            code = "unknown_component"
        reasons.add(code)
        return GovernanceDecision(
            decision=_decide(reasons),
            reasons=_canonical_reasons(reasons),
            component=component,
            diagnostics=diagnostics,
        )
    component = f"{kind}:{entry.ref}"

    if entry.lifecycle != protocols.COMPONENT_LIFECYCLE_ACTIVE:
        reasons.add("lifecycle_not_active")
        diagnostics["lifecycle"] = entry.lifecycle
    if kind == SKILL_KIND and entry.evaluation != protocols.SKILL_EVALUATION_PROMOTED:
        reasons.add("not_promoted")
        diagnostics["evaluation"] = entry.evaluation

    binding_reason = _binding_reason(entry, bindings)
    if binding_reason is not None:
        reasons.add(binding_reason)

    blocked = _dependency_problems(entry, skills, tools, bindings)
    if blocked:
        reasons.add("dependency_blocked")
        diagnostics["blocked_dependencies"] = blocked[:16]

    required = entry.document.get("required_capabilities", [])
    granted = set(validated["granted_capabilities"])
    missing = sorted(set(required) - granted)
    if missing:
        reasons.add("missing_capability")
        diagnostics["missing_capabilities"] = missing

    constraints = entry.document.get("agent_constraints")
    if constraints is not None:
        permitted = constraints["agent_classes"]
        caller_class = validated.get("caller_agent_class")
        if caller_class is None or caller_class not in permitted:
            reasons.add("agent_class_mismatch")
            diagnostics["permitted_agent_classes"] = list(permitted)

    approvals = entry.document.get("approvals_required")
    if approvals and "approval_ref" not in validated:
        reasons.add("approval_required")

    return GovernanceDecision(
        decision=_decide(reasons),
        reasons=_canonical_reasons(reasons),
        component=component,
        diagnostics=diagnostics,
    )


# ---------------------------------------------------------------------------
# Invocation protocol (contract §10)

@dataclass(frozen=True)
class InvocationResult:
    """One attempt's typed outcome. Every governance field here is computed
    by invoke(); a binding callable's return value can populate `output` and
    nothing else."""

    kind: str
    requested_ref: str
    invocation_id: str | None
    component_id: str | None
    component_version: int | None
    manifest_sha256: str | None
    binding_id: str | None
    binding_sha256: str | None
    envelope_sha256: str | None
    decision: str
    reasons: tuple[str, ...]
    status: str
    error_code: str | None
    retryable: bool
    termination_outcome: str
    recovery_action: str
    attempt: int | None
    max_attempts: int | None
    input_sha256: str | None
    output_sha256: str | None
    output: object
    started_at: str
    ended_at: str
    duration_seconds: int


def invocation_envelope(
    entry: ComponentEntry, context: dict, input_sha256: str
) -> dict:
    """The record of what was asked (contract §10.2): manifest identity and
    digest, binding identity and declared digest, canonical input digest,
    the validated context, and the attempt — self-digested."""
    envelope = {
        "schema": ENVELOPE_RECORD_SCHEMA,
        "invocation_id": context["invocation_id"],
        "component_kind": entry.kind,
        "component_id": entry.component_id,
        "component_version": entry.component_version,
        "manifest_sha256": entry.digest,
        "binding_id": entry.binding_id,
        "binding_sha256": entry.binding_sha256,
        "input_sha256": input_sha256,
        "attempt": context["attempt"],
        "max_attempts": context["max_attempts"],
        "context": context,
    }
    envelope[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(envelope)
    return envelope


def derive_retryable(
    entry: ComponentEntry | None, status: str, attempt: int | None, context
) -> bool:
    """The ONLY producer of `retryable` (contract §11). Deterministic code;
    no manifest field, callable output or model text can assert it."""
    if status not in RETRYABLE_STATUSES:
        return False
    if not isinstance(context, dict) or attempt is None:
        return False
    bounds = [context.get("max_attempts", 1)]
    if entry is not None and entry.kind == TOOL_KIND:
        bounds.append(entry.document["retry"]["max_attempts"])
    if attempt >= min(bounds):
        return False
    if entry is not None and entry.kind == TOOL_KIND:
        document = entry.document
        if document["side_effect"] == protocols.TOOL_SIDE_EFFECT_MUTATING:
            has_key = (
                document["idempotency"] == protocols.TOOL_IDEMPOTENCY_REQUIRED_KEY
                and "idempotency_ref" in context
            )
            has_compensation = (
                document["compensation"]["strategy"]
                == protocols.TOOL_COMPENSATION_ACTION
            )
            if not (has_key or has_compensation):
                return False
    return True


def _declared_recovery(entry: ComponentEntry | None) -> str:
    if entry is not None and entry.kind == TOOL_KIND:
        return entry.document["recovery"]["action"]
    return "none"


def invoke(
    kind: str,
    ref: str,
    *,
    skills: ComponentRegistry | None = None,
    tools: ComponentRegistry | None = None,
    bindings: BindingRegistry,
    context,
    input_value,
    clock=None,
) -> InvocationResult:
    """Execute at most ONE governed attempt (contract §10.3). The outer
    attempt loop belongs to Agentic OS (U-W1); there is no loop here to hide
    a retry in. `clock` is injectable for deterministic tests and defaults
    to the single wall-clock reader."""
    read_clock = utc_now_iso if clock is None else clock
    started_at = read_clock()
    requested_ref = ref if isinstance(ref, str) else ""

    def _finish(
        *,
        status: str,
        error_code: str | None,
        decision: str,
        reasons: tuple[str, ...],
        entry: ComponentEntry | None,
        validated: dict | None,
        termination: str,
        recovery: str | None = None,
        input_sha256: str | None = None,
        output_sha256: str | None = None,
        output=None,
        envelope_sha256: str | None = None,
        ended_at: str | None = None,
    ) -> InvocationResult:
        finished = ended_at if ended_at is not None else read_clock()
        try:
            duration = max(
                0, _instant_seconds(finished) - _instant_seconds(started_at)
            )
        except ValueError:
            duration = 0
        attempt = validated["attempt"] if validated else None
        max_attempts = validated["max_attempts"] if validated else None
        return InvocationResult(
            kind=kind,
            requested_ref=requested_ref,
            invocation_id=validated["invocation_id"] if validated else None,
            component_id=entry.component_id if entry else None,
            component_version=entry.component_version if entry else None,
            manifest_sha256=entry.digest if entry else None,
            binding_id=entry.binding_id if entry else None,
            binding_sha256=entry.binding_sha256 if entry else None,
            envelope_sha256=envelope_sha256,
            decision=decision,
            reasons=reasons,
            status=status,
            error_code=error_code,
            retryable=derive_retryable(entry, status, attempt, validated),
            termination_outcome=termination,
            recovery_action=(
                recovery
                if recovery is not None
                else (_declared_recovery(entry) if status != "success" else "none")
            ),
            attempt=attempt,
            max_attempts=max_attempts,
            input_sha256=input_sha256,
            output_sha256=output_sha256,
            output=output,
            started_at=started_at,
            ended_at=finished,
            duration_seconds=duration,
        )

    # Gate 1: context (contract §10.3.1).
    try:
        validated = validate_execution_context(context)
    except GovernanceError:
        return _finish(
            status="invalid_input",
            error_code="context_malformed",
            decision="invalid",
            reasons=("context_malformed",),
            entry=None,
            validated=None,
            termination="not_started",
            recovery="none",
        )

    # Gate 2: eligibility (contract §10.3.2). evaluate_eligibility raises
    # GovernanceError for a missing registry or unknown kind (a caller bug,
    # not a governed refusal), so past this call both are known-good.
    decision = evaluate_eligibility(
        kind, ref, skills=skills, tools=tools, bindings=bindings, context=validated
    )
    registry = skills if kind == SKILL_KIND else tools
    entry, _ = _try_resolve(registry, ref)
    if decision.decision != "allow":
        # Decision tier first (contract §10.3.2): an authority denial is
        # never reported under an availability status, however many
        # unavailability reasons co-occur.
        reason_set = set(decision.reasons)
        if decision.decision == "needs_approval":
            status, error_code = "denied", "approval_required"
        elif decision.decision == "deny":
            status, error_code = "denied", "governance_denied"
        elif "dependency_blocked" in reason_set:
            status, error_code = "dependency_blocked", "dependency_blocked"
        elif "unknown_component" in reason_set:
            status, error_code = "denied", "unknown_component"
        elif "unknown_version" in reason_set:
            status, error_code = "denied", "unknown_version"
        else:
            status, error_code = "denied", "governance_denied"
        return _finish(
            status=status,
            error_code=error_code,
            decision=decision.decision,
            reasons=decision.reasons,
            entry=entry,
            validated=validated,
            termination="not_started",
            recovery=(
                "request_approval"
                if decision.decision == "needs_approval"
                else None
            ),
        )

    # Eligible: the entry and its verified binding exist by construction
    # (an allow decision required both).
    record = bindings.record(entry.binding_id)
    document = entry.document

    if record["kind"] != BINDING_KIND_IN_PROCESS:
        # A metadata binding proves the contract; it cannot execute, and
        # saying so beats pretending (contract §10.3.5).
        return _finish(
            status="denied",
            error_code="governance_denied",
            decision="deny",
            reasons=("binding_kind_mismatch",),
            entry=entry,
            validated=validated,
            termination="not_started",
        )

    # Gate 3: input (contract §10.3.3).
    try:
        input_bytes = protocols.serialize_canonical(input_value)
    except protocols.ProtocolError:
        return _finish(
            status="invalid_input",
            error_code="input_not_canonical",
            decision="allow",
            reasons=(),
            entry=entry,
            validated=validated,
            termination="not_started",
        )
    input_sha256 = hashlib.sha256(input_bytes).hexdigest()
    limits = document.get("limits", {})
    max_input = limits.get("max_input_bytes")
    if max_input is not None and len(input_bytes) > max_input:
        return _finish(
            status="invalid_input",
            error_code="input_limit_exceeded",
            decision="allow",
            reasons=(),
            entry=entry,
            validated=validated,
            termination="not_started",
            input_sha256=input_sha256,
        )
    if (
        kind == TOOL_KIND
        and document["side_effect"] == protocols.TOOL_SIDE_EFFECT_MUTATING
        and document["idempotency"] == protocols.TOOL_IDEMPOTENCY_REQUIRED_KEY
        and "idempotency_ref" not in validated
    ):
        return _finish(
            status="invalid_input",
            error_code="idempotency_ref_required",
            decision="allow",
            reasons=(),
            entry=entry,
            validated=validated,
            termination="not_started",
            input_sha256=input_sha256,
        )
    if kind == TOOL_KIND and (
        validated["attempt"] > document["retry"]["max_attempts"]
    ):
        return _finish(
            status="invalid_input",
            error_code="attempt_budget_exhausted",
            decision="allow",
            reasons=(),
            entry=entry,
            validated=validated,
            termination="not_started",
            input_sha256=input_sha256,
        )

    envelope = invocation_envelope(entry, validated, input_sha256)
    envelope_sha256 = envelope[protocols.CONTENT_HASH_FIELD]

    # Gate 4: deadline before start (contract §10.3.4).
    deadline = validated.get("deadline_at")
    if deadline is not None and read_clock() >= deadline:
        return _finish(
            status="deadline_exceeded",
            error_code="deadline_before_start",
            decision="allow",
            reasons=(),
            entry=entry,
            validated=validated,
            termination="not_started",
            input_sha256=input_sha256,
            envelope_sha256=envelope_sha256,
        )

    # Gate 5: execution (contract §10.3.5). From here on the attempt RAN, so
    # termination is truthfully `completed` — the callable returned control,
    # whether by value or by raising. That is a mechanical fact, not a
    # success claim; `status` carries the judgment.
    callable_ = bindings.callable_for(entry.binding_id)
    try:
        output = callable_(input_value)
        failure: str | None = None
    except TransientExecutionError:
        output, failure = None, "transient_execution_failure"
    except PermanentExecutionError:
        output, failure = None, "permanent_execution_failure"
    except Exception:
        # Never copy the exception's text anywhere: an unexpected error may
        # be secret-shaped. The closed code is the whole story.
        output, failure = None, "unhandled_exception"
    ended_at = read_clock()

    if failure is not None:
        status = (
            "transient_failure"
            if failure == "transient_execution_failure"
            else "permanent_failure"
        )
        recovery = _declared_recovery(entry)
        if status == "permanent_failure" and recovery in _ESCALATING_RECOVERY_ACTIONS:
            status = "recovery_required"
        return _finish(
            status=status,
            error_code=failure,
            decision="allow",
            reasons=(),
            entry=entry,
            validated=validated,
            termination="completed",
            recovery=recovery,
            input_sha256=input_sha256,
            envelope_sha256=envelope_sha256,
            ended_at=ended_at,
        )

    # Gate 6: output (contract §10.3.6).
    try:
        output_bytes = protocols.serialize_canonical(output)
    except protocols.ProtocolError:
        recovery = _declared_recovery(entry)
        status = (
            "recovery_required"
            if recovery in _ESCALATING_RECOVERY_ACTIONS
            else "permanent_failure"
        )
        return _finish(
            status=status,
            error_code="output_not_canonical",
            decision="allow",
            reasons=(),
            entry=entry,
            validated=validated,
            termination="completed",
            recovery=recovery,
            input_sha256=input_sha256,
            envelope_sha256=envelope_sha256,
            ended_at=ended_at,
        )
    max_output = limits.get("max_output_bytes")
    if max_output is not None and len(output_bytes) > max_output:
        recovery = _declared_recovery(entry)
        status = (
            "recovery_required"
            if recovery in _ESCALATING_RECOVERY_ACTIONS
            else "permanent_failure"
        )
        return _finish(
            status=status,
            error_code="output_limit_exceeded",
            decision="allow",
            reasons=(),
            entry=entry,
            validated=validated,
            termination="completed",
            recovery=recovery,
            input_sha256=input_sha256,
            envelope_sha256=envelope_sha256,
            ended_at=ended_at,
        )
    output_sha256 = hashlib.sha256(output_bytes).hexdigest()

    # Gate 7: completion (contract §10.3.7). Late completion is a status,
    # not a termination lie: the work mechanically finished.
    if deadline is not None and ended_at >= deadline:
        return _finish(
            status="deadline_exceeded",
            error_code="deadline_after_completion",
            decision="allow",
            reasons=(),
            entry=entry,
            validated=validated,
            termination="completed",
            input_sha256=input_sha256,
            envelope_sha256=envelope_sha256,
            ended_at=ended_at,
        )

    return _finish(
        status="success",
        error_code=None,
        decision="allow",
        reasons=(),
        entry=entry,
        validated=validated,
        termination="completed",
        recovery="none",
        input_sha256=input_sha256,
        output_sha256=output_sha256,
        output=output,
        envelope_sha256=envelope_sha256,
        ended_at=ended_at,
    )


def result_envelope(result: InvocationResult) -> dict:
    """The canonical projection of a result (contract §10.4), self-digested.
    Built only from the typed result — the callable's output rides under
    `output` and cannot reach any governance field."""
    envelope = {
        "schema": RESULT_RECORD_SCHEMA,
        "component_kind": result.kind,
        "requested_ref": result.requested_ref,
        "invocation_id": result.invocation_id,
        "component_id": result.component_id,
        "component_version": result.component_version,
        "manifest_sha256": result.manifest_sha256,
        "binding_id": result.binding_id,
        "binding_sha256": result.binding_sha256,
        "envelope_sha256": result.envelope_sha256,
        "decision": result.decision,
        "reasons": list(result.reasons),
        "status": result.status,
        "error_code": result.error_code,
        "retryable": result.retryable,
        "termination_outcome": result.termination_outcome,
        "recovery_action": result.recovery_action,
        "attempt": result.attempt,
        "max_attempts": result.max_attempts,
        "input_sha256": result.input_sha256,
        "output_sha256": result.output_sha256,
        "started_at": result.started_at,
        "ended_at": result.ended_at,
        "duration_seconds": result.duration_seconds,
    }
    if result.status == "success":
        envelope["output"] = result.output
    envelope[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(envelope)
    return envelope


# ---------------------------------------------------------------------------
# Evidence (contract §13)

def invocation_evidence(
    result: InvocationResult, context, *, previous_sha256: str | None = None
) -> dict:
    """A digest-only evidence record of what the runner did.

    Every field is an enum member, bounded integer, validated identifier or
    digest — there is no free-text field to leak a secret through, which is
    stronger than redaction. The idempotency reference is bound by sha256
    leaf, never raw. Caller/trace fields come from the VALIDATED context
    only; a context that does not validate contributes nothing.
    """
    if previous_sha256 is not None and (
        not isinstance(previous_sha256, str)
        or not _SHA256_RE.fullmatch(previous_sha256)
    ):
        raise GovernanceError("malformed_previous_hash")

    validated: dict | None
    try:
        validated = validate_execution_context(context)
    except GovernanceError:
        validated = None

    trace = validated.get("trace", {}) if validated else {}
    idempotency_ref = validated.get("idempotency_ref") if validated else None
    record = {
        "schema": EVIDENCE_RECORD_SCHEMA,
        "invocation_id": result.invocation_id,
        "component_kind": result.kind,
        "component_id": result.component_id,
        "component_version": result.component_version,
        "manifest_sha256": result.manifest_sha256,
        "binding_id": result.binding_id,
        "binding_sha256": result.binding_sha256,
        "envelope_sha256": result.envelope_sha256,
        "principal": validated["principal"] if validated else None,
        "caller_agent": validated.get("caller_agent") if validated else None,
        "aos_task_id": validated.get("aos_task_id") if validated else None,
        "decision": result.decision,
        "reasons": list(result.reasons),
        "attempt": result.attempt,
        "max_attempts": result.max_attempts,
        "idempotency_ref_sha256": (
            sha256_text(idempotency_ref) if idempotency_ref is not None else None
        ),
        "started_at": result.started_at,
        "ended_at": result.ended_at,
        "duration_seconds": result.duration_seconds,
        "status": result.status,
        "error_code": result.error_code,
        "retryable": result.retryable,
        "input_sha256": result.input_sha256,
        "output_sha256": result.output_sha256,
        "termination_outcome": result.termination_outcome,
        "recovery_action": result.recovery_action,
        "trace_id": trace.get("trace_id"),
        "correlation_id": trace.get("correlation_id"),
        "causation_id": trace.get("causation_id"),
        "previous_sha256": previous_sha256,
    }
    record[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(record)
    return record


# ---------------------------------------------------------------------------
# Passport requirement resolution (contract §14)

@dataclass(frozen=True)
class RequirementResolution:
    """One passport requirement string, resolved or not. `code` is a
    RESOLUTION_CODES member; the three identity fields are populated exactly
    when code is 'resolved'."""

    kind: str
    requirement: str
    code: str
    component_id: str | None
    component_version: int | None
    manifest_sha256: str | None


@dataclass(frozen=True)
class RequirementResolutionReport:
    resolutions: tuple[RequirementResolution, ...]

    @property
    def all_resolved(self) -> bool:
        return all(item.code == "resolved" for item in self.resolutions)

    @property
    def unresolved(self) -> tuple[RequirementResolution, ...]:
        return tuple(
            item for item in self.resolutions if item.code != "resolved"
        )


def resolve_passport_requirements(
    document: dict,
    skills: ComponentRegistry,
    tools: ComponentRegistry,
) -> RequirementResolutionReport:
    """Resolve a valid passport's skill/tool requirement strings (contract
    §14). Read-only: the passport schema is untouched, nothing is mutated,
    and an unresolved requirement is a reported fact, never an error."""
    entry = protocols.validate_document(document)
    if entry.identity != "beast.agent-passport/v1":
        raise GovernanceError("wrong_schema", where="beast.agent-passport/v1")
    _registry_for(SKILL_KIND, skills, tools)
    _registry_for(TOOL_KIND, skills, tools)

    resolutions: list[RequirementResolution] = []
    for kind, field, registry in (
        (SKILL_KIND, "skill_requirements", skills),
        (TOOL_KIND, "tool_requirements", tools),
    ):
        for requirement in document.get(field, ()):
            resolved, code = _try_resolve(registry, requirement)
            if resolved is None:
                # The same fail-closed fold as eligibility: anything that is
                # not a closed resolution code reports unknown_component.
                if code not in RESOLUTION_CODES:
                    code = "unknown_component"
                resolutions.append(
                    RequirementResolution(
                        kind=kind,
                        requirement=requirement,
                        code=code,
                        component_id=None,
                        component_version=None,
                        manifest_sha256=None,
                    )
                )
            else:
                resolutions.append(
                    RequirementResolution(
                        kind=kind,
                        requirement=requirement,
                        code="resolved",
                        component_id=resolved.component_id,
                        component_version=resolved.component_version,
                        manifest_sha256=resolved.digest,
                    )
                )
    return RequirementResolutionReport(resolutions=tuple(resolutions))
