"""U-W1 deterministic WorkSpec compiler, linter, decompiler, and semantic diff.

Contract: agentic-os-v0.4-u-w1-workspec-compiler-contract.md

Everything here is INERT and pure. This module compiles a closed authoring
input into a canonical ``beast.work-spec/v1`` artifact plus a self-digested
compile report, lints artifacts under a closed 25-code vocabulary with the
six-status precedence, resolves requested agents/skills/tools against an
immutable snapshot, decompiles artifacts into a bounded secret-safe display
text, and semantically diffs two artifacts. It executes zero attempts,
schedules zero work, persists nothing, and grants nothing: no capability,
approval, policy decision, budget, credential, power mode, route authority,
or execution permission is created, implied, or recorded (D-v0.4.65).

Determinism (D-v0.4.62): every function is a pure function of its explicit
arguments. No clock is read (``created_at`` is explicit and the one clock
helper in ``utils`` is deliberately not imported), no randomness, no locale,
no environment, no filesystem, no network, no dynamic import, and no
database participates. Real-instant checks are pure calendar arithmetic, so
even the ``datetime`` module stays outside this file. Identical inputs yield
byte-identical outputs on every platform.

Runtime boundary (D-v0.4.59): U-W1 is the static half. U-W2 owns the
workflow state engine and queue integration; U-W3 owns checkpoints, resume,
runtime retry, and compensation; U-K1/U-T1's governed single-attempt runner
is untouched and is never called from here — this module reads only the
inert registry/resolution surfaces of ``governance``.
"""

import hashlib
import re
from dataclasses import dataclass

from . import governance, protocols, secretscan
from .models import AGENT_LIFECYCLES
from .utils import AosError

# ---------------------------------------------------------------------------
# Closed vocabularies (contract §4). Tuples, frozen at import.

WORKSPEC_AUTHORING_SCHEMA = "aos.work-spec-authoring/v1"
WORKSPEC_ALGORITHM_VERSION = "aos-workspec-compile/v1"
REPORT_RECORD_SCHEMA = "aos.work-spec-compile-report/v1"
SNAPSHOT_RECORD_SCHEMA = "aos.work-spec-registry-snapshot/v1"
DIFF_RECORD_SCHEMA = "aos.work-spec-semantic-diff/v1"

#: Six statuses in precedence order: the status of a lint/compile result is
#: the highest-precedence class with at least one finding, else ``valid``.
WORKSPEC_LINT_STATUSES = (
    "invalid",
    "unresolved",
    "ineligible",
    "requires_external_authority",
    "warning",
    "valid",
)

#: The 25 closed finding codes in canonical emission order (the
#: GOVERNANCE_REASON_CODES idiom): findings sort by this order first, then
#: by path code-point order, then by canonical diagnostics bytes.
WORKSPEC_LINT_CODES = (
    "malformed_input",
    "forbidden_field",
    "schema_invalid",
    "contradictory_limits",
    "malformed_authority_ref",
    "duplicate_item",
    "secret_shaped_content",
    "unsupported_dynamic_behavior",
    "unknown_agent",
    "unknown_skill",
    "unknown_tool",
    "unknown_version",
    "ambiguous_component",
    "lifecycle_not_active",
    "not_promoted",
    "dependency_blocked",
    "agent_class_mismatch",
    "capability_mismatch",
    "classification_mismatch",
    "scope_mismatch",
    "retry_idempotency_incompatible",
    "result_contract_mismatch",
    "approval_reference_required",
    "unpinned_requirement",
    "redundant_explicit_default",
)

#: code -> status class. Every code maps to exactly one class.
WORKSPEC_LINT_CODE_CLASSES = {
    "malformed_input": "invalid",
    "forbidden_field": "invalid",
    "schema_invalid": "invalid",
    "contradictory_limits": "invalid",
    "malformed_authority_ref": "invalid",
    "duplicate_item": "invalid",
    "secret_shaped_content": "invalid",
    "unsupported_dynamic_behavior": "invalid",
    "unknown_agent": "unresolved",
    "unknown_skill": "unresolved",
    "unknown_tool": "unresolved",
    "unknown_version": "unresolved",
    "ambiguous_component": "unresolved",
    "lifecycle_not_active": "ineligible",
    "not_promoted": "ineligible",
    "dependency_blocked": "ineligible",
    "agent_class_mismatch": "ineligible",
    "capability_mismatch": "ineligible",
    "classification_mismatch": "ineligible",
    "scope_mismatch": "ineligible",
    "retry_idempotency_incompatible": "ineligible",
    "result_contract_mismatch": "ineligible",
    "approval_reference_required": "requires_external_authority",
    "unpinned_requirement": "warning",
    "redundant_explicit_default": "warning",
}

PROVENANCE_CLASSES = ("explicit", "defaulted", "resolved")
DIFF_CHANGE_KINDS = ("added", "removed", "changed")
DIFF_CATEGORIES = (
    "metadata",
    "requirements",
    "authority_references",
    "budgets_limits",
    "retry_idempotency",
    "classification",
    "resolutions",
    "result_contract",
)

#: Per-item resolution codes (governance.RESOLUTION_CODES, reused verbatim).
RESOLUTION_CODES = governance.RESOLUTION_CODES

#: Frozen sha256 domain-separation tags for the content-derived identifier
#: defaults (contract §6). The tag and a NUL byte prefix the derivation
#: material so no two derivations can collide across purposes.
_TAG_WORK_SPEC_ID = b"aos-workspec-id/v1"
_TAG_IDEMPOTENCY = b"aos-workspec-idem/v1"
_TAG_TRACE = b"aos-workspec-trace/v1"
_TAG_CORRELATION = b"aos-workspec-corr/v1"

#: Frozen defaults (contract §6). The least-authority destination floor and
#: the weakest honest result-contract floor.
_DEFAULT_DESTINATIONS = ("aos-ledger", "local")
_DEFAULT_EXPECTED_RESULT = {
    "result_schema": "beast.result-envelope/v1",
    "evidence_kinds": ["note"],
    "min_evidence_count": 1,
}

_WORK_SPEC_IDENTITY = "beast.work-spec/v1"

#: Decompiler bound (contract §12): free-text values longer than this many
#: code points truncate with the fixed ``...(+N chars)`` marker.
_DISPLAY_TEXT_LIMIT = 120

# ---------------------------------------------------------------------------
# Errors (the GovernanceError idiom: closed reasons, value-free hints).

_REASON_HINTS = {
    "snapshot_required": "This operation requires a WorkSpecSnapshot.",
    "registry_required": "The snapshot slot requires a registry of that kind.",
    "malformed_snapshot": (
        "Snapshot agent entries must be (name, lifecycle, document) triples."
    ),
    "unknown_lifecycle": "An attested agent lifecycle is not a known state.",
    "wrong_schema": "The document is not the schema this operation accepts.",
    "agent_name_mismatch": (
        "A snapshot passport must declare the agent name it is entered under."
    ),
    "duplicate_agent_version": (
        "The snapshot already holds this agent name and passport version."
    ),
    "folded_name_collision": (
        "Two snapshot agent names differ only by case; one reference would "
        "answer to both."
    ),
    "malformed_report": (
        "The supplied compile report does not match the closed report shape."
    ),
    "report_mismatch": (
        "The supplied compile report does not digest-bind this artifact; an "
        "absent, unbound, or mismatched report is no report at all."
    ),
}


class WorkSpecError(AosError):
    """One bounded, actionable, value-free line. Exits 1 through AosError.

    ``where`` may carry only already-validated identifiers (an agent name, a
    requirement ref, a field NAME). No caller passes free text or a field
    value.
    """

    def __init__(self, reason: str, where: str = "") -> None:
        if reason not in _REASON_HINTS:
            raise KeyError(f"undeclared workspec reason code: {reason!r}")
        self.reason = reason
        self.where = where
        prefix = f"workspecs: {where}: " if where else "workspecs: "
        super().__init__(prefix + _REASON_HINTS[reason])


# ---------------------------------------------------------------------------
# Pattern gates. Compiled from the frozen protocol patterns; matched with
# fullmatch so a trailing newline can never sneak through (D-v0.2.3).

_RFC3339_RE = re.compile(protocols.RFC3339_PATTERN, re.ASCII)
_UUID_RE = re.compile(protocols.UUID_PATTERN, re.ASCII)
_TRACE_ID_RE = re.compile(protocols.TRACE_ID_PATTERN, re.ASCII)
_AOS_TASK_ID_RE = re.compile(protocols.AOS_TASK_ID_PATTERN, re.ASCII)
_IDEMPOTENCY_RE = re.compile(protocols.IDEMPOTENCY_KEY_PATTERN, re.ASCII)
_ISSUER_RE = re.compile(protocols.ISSUER_PATTERN, re.ASCII)
_OPAQUE_REF_RE = re.compile(protocols.OPAQUE_REF_PATTERN, re.ASCII)
_PROJECT_RE = re.compile(protocols.PROJECT_SCOPE_PATTERN, re.ASCII)
_CAPABILITY_RE = re.compile(protocols.CAPABILITY_PATTERN, re.ASCII)
_SHA256_RE = re.compile(protocols.SHA256_PATTERN, re.ASCII)
_AGENT_NAME_RE = re.compile(protocols.AGENT_NAME_PATTERN, re.ASCII)
_REQUIREMENT_RE = re.compile(protocols.REQUIREMENT_PATTERN, re.ASCII)

_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _is_real_instant(text: str) -> bool:
    """A pattern-valid RFC3339 Z instant -> is it a real UTC moment?

    Pure calendar arithmetic, equivalent to the spine's strptime acceptance
    for this fixed format — used instead of ``datetime`` so this module
    imports no time machinery at all (the no-clock claim stays structural).
    """
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


def _join(path: str, segment: str) -> str:
    return f"/{segment}" if path == "/" else f"{path}/{segment}"


# ---------------------------------------------------------------------------
# Typed results (contract §4). Frozen dataclasses over fresh values.

@dataclass(frozen=True)
class LintFinding:
    """One closed finding: code, its status class, a schema-safe path, and
    bounded diagnostics (closed keys; enum members, validated identifiers,
    bounded counts, and secretscan pattern names only — never a field value,
    a document excerpt, or exception text)."""

    code: str
    status_class: str
    path: str
    diagnostics: dict


@dataclass(frozen=True)
class ResolutionRecord:
    """One requested component, resolved or not. ``code`` is a
    RESOLUTION_CODES member; the resolved fields are populated exactly when
    code is ``resolved``. ``resolved_sha256`` is the manifest digest for
    skills/tools and the passport digest for agents."""

    kind: str
    requested: str
    code: str
    resolved_id: str | None
    resolved_version: int | None
    resolved_sha256: str | None


@dataclass(frozen=True)
class LintReport:
    """The typed lint result: derived status, findings in canonical order,
    and resolution records sorted by (kind, requested)."""

    status: str
    findings: tuple
    resolutions: tuple


@dataclass(frozen=True)
class CompileResult:
    """The typed compile result. ``artifact`` exists exactly when ``status``
    is not ``invalid``; ``report`` always exists."""

    status: str
    findings: tuple
    artifact: dict | None
    report: dict


@dataclass(frozen=True)
class SnapshotAgentEntry:
    """One validated snapshot passport with its caller-attested lifecycle.
    ``digest`` is recomputed from the document body at build time."""

    name: str
    passport_version: int
    lifecycle: str
    document: dict
    digest: str


@dataclass(frozen=True)
class WorkSpecSnapshot:
    """The immutable resolution universe: validated agent passports plus
    governance-built skill/tool registries. Data only — resolving against
    it touches no file, no database, and no binding."""

    agents: tuple
    skills: governance.ComponentRegistry
    tools: governance.ComponentRegistry


def _finding(code: str, path: str, **diagnostics) -> LintFinding:
    return LintFinding(
        code=code,
        status_class=WORKSPEC_LINT_CODE_CLASSES[code],
        path=path,
        diagnostics=dict(diagnostics),
    )


def _sorted_findings(findings) -> tuple:
    """Canonical order with duplicates removed: code order, then path
    code-point order, then canonical diagnostics bytes as a total tiebreak."""
    unique: dict = {}
    for finding in findings:
        key = (
            WORKSPEC_LINT_CODES.index(finding.code),
            finding.path,
            protocols.serialize_canonical(finding.diagnostics),
        )
        unique.setdefault(key, finding)
    return tuple(unique[key] for key in sorted(unique))


def _derive_status(findings) -> str:
    present = {finding.status_class for finding in findings}
    for status in WORKSPEC_LINT_STATUSES[:-1]:
        if status in present:
            return status
    return "valid"


# ---------------------------------------------------------------------------
# Snapshot build, projection, and digest (contract §9).

def _registry_for(slot, kind: str, tool_registry=None):
    if isinstance(slot, governance.ComponentRegistry):
        if slot.kind != kind:
            raise WorkSpecError("registry_required", where=kind)
        return slot
    documents = list(slot)
    if kind == governance.TOOL_KIND:
        return governance.build_tool_registry(documents)
    return governance.build_skill_registry(documents, tool_registry)


def build_snapshot(agents=(), skills=(), tools=()) -> WorkSpecSnapshot:
    """Validate and freeze one resolution universe.

    ``agents`` is a sequence of ``(name, lifecycle, document)`` triples where
    ``document`` is a valid ``beast.agent-passport/v1`` artifact and
    ``lifecycle`` is a caller-attested AGENT_LIFECYCLES member (the
    routing.CandidateSnapshot rule: reading the ledger is the caller's job).
    ``skills``/``tools`` are governance.ComponentRegistry values accepted
    as-is, or iterables of raw manifest documents built through the
    governance builders — which refuse duplicates, missing dependencies,
    unknown dependency versions, and dependency cycles at build time with
    their closed reasons. Nothing is imported, fetched, bound, or executed.
    """
    tool_registry = _registry_for(tools, governance.TOOL_KIND)
    skill_registry = _registry_for(
        skills, governance.SKILL_KIND, tool_registry=tool_registry
    )

    entries: dict = {}
    folded: dict = {}
    for item in agents:
        if not isinstance(item, (tuple, list)) or len(item) != 3:
            raise WorkSpecError("malformed_snapshot")
        name, lifecycle, document = item
        if not isinstance(name, str) or not _AGENT_NAME_RE.fullmatch(name):
            raise WorkSpecError("malformed_snapshot")
        if lifecycle not in AGENT_LIFECYCLES:
            raise WorkSpecError("unknown_lifecycle", where=name)
        entry = protocols.validate_document(document)
        if entry.identity != "beast.agent-passport/v1":
            raise WorkSpecError("wrong_schema", where=name)
        # Snapshot on intake: a caller-retained reference mutated after the
        # build can neither alter a resolution nor stale a digest.
        document = protocols.parse_canonical(
            protocols.serialize_canonical(document)
        )
        if document["agent"] != name:
            raise WorkSpecError("agent_name_mismatch", where=name)
        version = document["passport_version"]
        if (name, version) in entries:
            raise WorkSpecError(
                "duplicate_agent_version", where=f"{name}/v{version}"
            )
        fold = name.casefold()
        if fold in folded and folded[fold] != name:
            raise WorkSpecError("folded_name_collision", where=name)
        folded[fold] = name
        entries[(name, version)] = SnapshotAgentEntry(
            name=name,
            passport_version=version,
            lifecycle=lifecycle,
            document=document,
            digest=protocols.content_digest(document),
        )
    return WorkSpecSnapshot(
        agents=tuple(entries[key] for key in sorted(entries)),
        skills=skill_registry,
        tools=tool_registry,
    )


def _require_snapshot(snapshot) -> WorkSpecSnapshot:
    if not isinstance(snapshot, WorkSpecSnapshot):
        raise WorkSpecError("snapshot_required")
    return snapshot


def snapshot_projection(snapshot: WorkSpecSnapshot) -> dict:
    """The deterministic canonical record of a snapshot: names, versions,
    lifecycles, and digests only — never a document body."""
    _require_snapshot(snapshot)
    return {
        "schema": SNAPSHOT_RECORD_SCHEMA,
        "agents": [
            {
                "name": entry.name,
                "passport_version": entry.passport_version,
                "lifecycle": entry.lifecycle,
                "passport_sha256": entry.digest,
            }
            for entry in snapshot.agents
        ],
        "skills": governance.registry_projection(snapshot.skills),
        "tools": governance.registry_projection(snapshot.tools),
    }


def snapshot_digest(snapshot: WorkSpecSnapshot) -> str:
    """sha256 over the canonical projection bytes; recorded in every report."""
    return hashlib.sha256(
        protocols.serialize_canonical(snapshot_projection(snapshot))
    ).hexdigest()


def _agent_versions(snapshot: WorkSpecSnapshot, name: str) -> list:
    return sorted(
        entry.passport_version
        for entry in snapshot.agents
        if entry.name == name
    )


def _agent_entry(snapshot: WorkSpecSnapshot, name: str, version: int):
    for entry in snapshot.agents:
        if entry.name == name and entry.passport_version == version:
            return entry
    return None


# ---------------------------------------------------------------------------
# Identifier derivations (contract §6). Domain-separated, total, and
# independent of the supplied derived keys.

def _derivation_material(normalized: dict) -> bytes:
    body = {
        key: value
        for key, value in normalized.items()
        if key not in ("work_spec_id", "idempotency_key", "trace")
    }
    return protocols.serialize_canonical(body)


def _uuid8_from_digest(digest: bytes) -> str:
    """RFC 9562 UUIDv8 over the first 16 digest bytes: version nibble 8, RFC
    variant bits, lowercase hex. The version nibble makes an all-zero UUID
    unconstructible."""
    raw = bytearray(digest[:16])
    raw[6] = (raw[6] & 0x0F) | 0x80
    raw[8] = (raw[8] & 0x3F) | 0x80
    text = raw.hex()
    return (
        f"{text[0:8]}-{text[8:12]}-{text[12:16]}-{text[16:20]}-{text[20:32]}"
    )


def _guard_trace_id(text: str) -> str:
    """The all-zero trace guard: not reachable from sha256 output in
    practice, guarded anyway — the spine refuses an all-zero trace id."""
    if text == "0" * len(text):
        return text[:-1] + "1"
    return text


def _tagged_digest(tag: bytes, material: bytes) -> bytes:
    return hashlib.sha256(tag + b"\0" + material).digest()


def _derive_defaults(normalized: dict) -> dict:
    material = _derivation_material(normalized)
    return {
        "work_spec_id": _uuid8_from_digest(
            _tagged_digest(_TAG_WORK_SPEC_ID, material)
        ),
        "idempotency_key": "ws-"
        + _tagged_digest(_TAG_IDEMPOTENCY, material).hex()[:40],
        "trace": {
            "trace_id": _guard_trace_id(
                _tagged_digest(_TAG_TRACE, material).hex()[:32]
            ),
            "correlation_id": _uuid8_from_digest(
                _tagged_digest(_TAG_CORRELATION, material)
            ),
        },
    }


# ---------------------------------------------------------------------------
# Authoring shape validation and normalization (contract §5).

_FORBIDDEN_AUTHORING_KEYS = (
    "schema",
    "protocol_version",
    "content_hash_alg",
    "content_sha256",
)

_REQUIRED_AUTHORING_KEYS = (
    "created_at",
    "issuer",
    "audience",
    "scope",
    "aos_task_id",
    "data_classification",
    "goal",
    "acceptance_criteria",
)

_OPTIONAL_AUTHORING_KEYS = (
    "expires_at",
    "constraints",
    "required_capabilities",
    "inputs",
    "policy_refs",
    "retry",
    "expected_result",
    "permitted_destinations",
    "runtime_task_uuid",
    "work_spec_id",
    "idempotency_key",
    "trace",
    "requested",
)

_ALLOWED_AUTHORING_KEYS = frozenset(
    ("authoring_schema", "algorithm_version")
    + _REQUIRED_AUTHORING_KEYS
    + _OPTIONAL_AUTHORING_KEYS
)

#: The authorable field order used when reconstructing an authoring view.
_AUTHORABLE_FIELDS = _REQUIRED_AUTHORING_KEYS + (
    "expires_at",
    "constraints",
    "required_capabilities",
    "inputs",
    "policy_refs",
    "retry",
    "expected_result",
    "permitted_destinations",
    "runtime_task_uuid",
    "work_spec_id",
    "idempotency_key",
    "trace",
)


def _data_shape_findings(value, path: str, depth: int, findings: list) -> None:
    """Refuse non-JSON-data values (``unsupported_dynamic_behavior``) and
    canonical-bound violations (``malformed_input``) anywhere in the tree,
    BEFORE any canonical serialization could crash on them."""
    if depth > protocols.MAX_DEPTH:
        findings.append(_finding("malformed_input", path))
        return
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if not (protocols.INT_MIN <= value <= protocols.INT_MAX):
            findings.append(_finding("unsupported_dynamic_behavior", path))
        return
    if isinstance(value, str):
        if len(value) > protocols.MAX_STRING_CHARS:
            findings.append(_finding("malformed_input", path))
            return
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            findings.append(_finding("unsupported_dynamic_behavior", path))
        return
    if isinstance(value, (list, tuple)):
        if len(value) > protocols.MAX_ARRAY_ITEMS:
            findings.append(_finding("malformed_input", path))
            return
        for index, item in enumerate(value):
            _data_shape_findings(item, _join(path, str(index)), depth + 1, findings)
        return
    if isinstance(value, dict):
        if len(value) > protocols.MAX_OBJECT_MEMBERS:
            findings.append(_finding("malformed_input", path))
            return
        for key, item in value.items():
            if not isinstance(key, str):
                findings.append(
                    _finding("unsupported_dynamic_behavior", path)
                )
                continue
            _data_shape_findings(item, _join(path, key), depth + 1, findings)
        return
    findings.append(_finding("unsupported_dynamic_behavior", path))


def _check_string(
    value, path: str, findings: list, *, min_len=1, max_len, pattern=None
):
    if not isinstance(value, str):
        findings.append(_finding("malformed_input", path))
        return None
    if not (min_len <= len(value) <= max_len):
        findings.append(_finding("malformed_input", path))
        return None
    if pattern is not None and not pattern.fullmatch(value):
        findings.append(_finding("malformed_input", path))
        return None
    return value


def _check_instant(value, path: str, findings: list):
    text = _check_string(value, path, findings, min_len=20, max_len=20,
                         pattern=_RFC3339_RE)
    if text is not None and not _is_real_instant(text):
        findings.append(_finding("malformed_input", path))
        return None
    return text


def _check_string_array(
    value,
    path: str,
    findings: list,
    *,
    min_items,
    max_items,
    item_min=1,
    item_max,
    pattern=None,
    enum=None,
):
    """A closed, bounded, duplicate-refusing string array, canonically sorted
    by code point (the routing ``validate_request`` idiom)."""
    if not isinstance(value, list):
        findings.append(_finding("malformed_input", path))
        return None
    if not (min_items <= len(value) <= max_items):
        findings.append(_finding("malformed_input", path))
        return None
    ok = True
    seen = set()
    duplicate = False
    for index, item in enumerate(value):
        item_path = _join(path, str(index))
        if not isinstance(item, str):
            findings.append(_finding("malformed_input", item_path))
            ok = False
            continue
        if not (item_min <= len(item) <= item_max):
            findings.append(_finding("malformed_input", item_path))
            ok = False
            continue
        if pattern is not None and not pattern.fullmatch(item):
            findings.append(_finding("malformed_input", item_path))
            ok = False
            continue
        if enum is not None and item not in enum:
            findings.append(_finding("malformed_input", item_path))
            ok = False
            continue
        if item in seen:
            duplicate = True
        seen.add(item)
    if duplicate:
        findings.append(_finding("duplicate_item", path))
    if not ok or duplicate:
        return None
    return sorted(value)


def _check_closed_object(value, path: str, findings: list, *, allowed):
    if not isinstance(value, dict):
        findings.append(_finding("malformed_input", path))
        return None
    if any(key not in allowed for key in value):
        # The path names the PARENT, never the unknown key (the spine rule).
        findings.append(_finding("malformed_input", path))
        return None
    return value


def _check_scope(value, findings: list):
    scope = _check_closed_object(
        value, "/scope", findings, allowed=("project", "tenant")
    )
    if scope is None:
        return None
    normalized = {}
    if "project" not in scope:
        findings.append(_finding("malformed_input", "/scope/project"))
        return None
    project = _check_string(
        scope["project"], "/scope/project", findings, max_len=64,
        pattern=_PROJECT_RE,
    )
    if project is None:
        return None
    normalized["project"] = project
    if "tenant" in scope:
        tenant = _check_string(
            scope["tenant"], "/scope/tenant", findings, max_len=64,
            pattern=_PROJECT_RE,
        )
        if tenant is None:
            return None
        normalized["tenant"] = tenant
    return normalized


def _check_inputs(value, findings: list):
    if not isinstance(value, list):
        findings.append(_finding("malformed_input", "/inputs"))
        return None
    if len(value) > 32:
        findings.append(_finding("malformed_input", "/inputs"))
        return None
    normalized = []
    ok = True
    seen_pairs = set()
    duplicate = False
    for index, item in enumerate(value):
        item_path = _join("/inputs", str(index))
        item_dict = _check_closed_object(
            item, item_path, findings,
            allowed=("ref_kind", "ref", "sha256", "note"),
        )
        if item_dict is None:
            ok = False
            continue
        entry = {}
        if "ref_kind" not in item_dict or "ref" not in item_dict:
            findings.append(_finding("malformed_input", item_path))
            ok = False
            continue
        ref_kind = item_dict["ref_kind"]
        if ref_kind not in protocols.INPUT_REF_KINDS:
            findings.append(
                _finding("malformed_input", _join(item_path, "ref_kind"))
            )
            ok = False
            continue
        ref = _check_string(
            item_dict["ref"], _join(item_path, "ref"), findings, max_len=1024
        )
        if ref is None:
            ok = False
            continue
        entry["ref_kind"] = ref_kind
        entry["ref"] = ref
        if "sha256" in item_dict:
            sha = _check_string(
                item_dict["sha256"], _join(item_path, "sha256"), findings,
                min_len=64, max_len=64, pattern=_SHA256_RE,
            )
            if sha is None:
                ok = False
                continue
            entry["sha256"] = sha
        if "note" in item_dict:
            note = _check_string(
                item_dict["note"], _join(item_path, "note"), findings,
                max_len=512,
            )
            if note is None:
                ok = False
                continue
            entry["note"] = note
        if (ref_kind, ref) in seen_pairs:
            duplicate = True
        seen_pairs.add((ref_kind, ref))
        normalized.append(entry)
    if duplicate:
        findings.append(_finding("duplicate_item", "/inputs"))
    if not ok or duplicate:
        return None
    normalized.sort(key=protocols.serialize_canonical)
    return normalized


def _check_policy_refs(value, findings: list):
    refs = _check_closed_object(
        value, "/policy_refs", findings,
        allowed=("policy_ref", "approval_ref", "budget_ref"),
    )
    if refs is None:
        return None
    normalized = {}
    ok = True
    for key in ("approval_ref", "budget_ref", "policy_ref"):
        if key in refs:
            ref = _check_string(
                refs[key], _join("/policy_refs", key), findings,
                min_len=3, max_len=132, pattern=_OPAQUE_REF_RE,
            )
            if ref is None:
                ok = False
                continue
            normalized[key] = ref
    return normalized if ok else None


def _check_retry(value, findings: list):
    retry = _check_closed_object(
        value, "/retry", findings, allowed=("max_attempts", "deadline_at")
    )
    if retry is None:
        return None
    if "max_attempts" not in retry:
        findings.append(_finding("malformed_input", "/retry/max_attempts"))
        return None
    attempts = retry["max_attempts"]
    if (
        not isinstance(attempts, int)
        or isinstance(attempts, bool)
        or not (1 <= attempts <= 10)
    ):
        findings.append(_finding("malformed_input", "/retry/max_attempts"))
        return None
    normalized = {"max_attempts": attempts}
    if "deadline_at" in retry:
        deadline = _check_instant(
            retry["deadline_at"], "/retry/deadline_at", findings
        )
        if deadline is None:
            return None
        normalized["deadline_at"] = deadline
    return normalized


def _check_expected_result(value, findings: list):
    contract = _check_closed_object(
        value, "/expected_result", findings,
        allowed=("result_schema", "evidence_kinds", "min_evidence_count"),
    )
    if contract is None:
        return None
    for key in ("result_schema", "evidence_kinds", "min_evidence_count"):
        if key not in contract:
            findings.append(
                _finding("malformed_input", _join("/expected_result", key))
            )
            return None
    if contract["result_schema"] != "beast.result-envelope/v1":
        findings.append(
            _finding("malformed_input", "/expected_result/result_schema")
        )
        return None
    kinds = _check_string_array(
        contract["evidence_kinds"], "/expected_result/evidence_kinds",
        findings, min_items=1, max_items=len(protocols.EVIDENCE_KINDS),
        item_max=64, enum=protocols.EVIDENCE_KINDS,
    )
    if kinds is None:
        return None
    count = contract["min_evidence_count"]
    if (
        not isinstance(count, int)
        or isinstance(count, bool)
        or not (0 <= count <= 32)
    ):
        findings.append(
            _finding("malformed_input", "/expected_result/min_evidence_count")
        )
        return None
    return {
        "result_schema": "beast.result-envelope/v1",
        "evidence_kinds": kinds,
        "min_evidence_count": count,
    }


def _check_trace(value, findings: list):
    trace = _check_closed_object(
        value, "/trace", findings,
        allowed=("trace_id", "correlation_id", "causation_id"),
    )
    if trace is None:
        return None
    for key in ("trace_id", "correlation_id"):
        if key not in trace:
            findings.append(_finding("malformed_input", _join("/trace", key)))
            return None
    trace_id = _check_string(
        trace["trace_id"], "/trace/trace_id", findings, min_len=32,
        max_len=32, pattern=_TRACE_ID_RE,
    )
    if trace_id is None:
        return None
    if trace_id == "0" * 32:
        findings.append(_finding("malformed_input", "/trace/trace_id"))
        return None
    normalized = {"trace_id": trace_id}
    for key in ("correlation_id", "causation_id"):
        if key in trace:
            uuid_value = _check_string(
                trace[key], _join("/trace", key), findings, min_len=36,
                max_len=36, pattern=_UUID_RE,
            )
            if uuid_value is None:
                return None
            normalized[key] = uuid_value
    return normalized


def _check_requested(value, findings: list, path: str = "/requested"):
    """Validate and normalize the requested-components block. Empty arrays
    and an empty block normalize to absence, so equivalent spellings compile
    identically."""
    requested = _check_closed_object(
        value, path, findings, allowed=("agent", "skills", "tools")
    )
    if requested is None:
        return None
    normalized = {}
    ok = True
    if "agent" in requested:
        agent = _check_closed_object(
            requested["agent"], _join(path, "agent"), findings,
            allowed=("name", "version"),
        )
        if agent is None:
            ok = False
        else:
            agent_normalized = {}
            if "name" not in agent:
                findings.append(
                    _finding("malformed_input", _join(path, "agent/name"))
                )
                ok = False
            else:
                name = _check_string(
                    agent["name"], _join(path, "agent/name"), findings,
                    max_len=64, pattern=_AGENT_NAME_RE,
                )
                if name is None:
                    ok = False
                else:
                    agent_normalized["name"] = name
            if "version" in agent:
                version = agent["version"]
                if (
                    not isinstance(version, int)
                    or isinstance(version, bool)
                    or not (1 <= version <= 999999)
                ):
                    findings.append(
                        _finding(
                            "malformed_input", _join(path, "agent/version")
                        )
                    )
                    ok = False
                else:
                    agent_normalized["version"] = version
            if ok and agent_normalized:
                normalized["agent"] = agent_normalized
    for key in ("skills", "tools"):
        if key in requested:
            values = _check_string_array(
                requested[key], _join(path, key), findings, min_items=0,
                max_items=16, item_min=2, item_max=70,
                pattern=_REQUIREMENT_RE,
            )
            if values is None:
                ok = False
            elif values:
                normalized[key] = values
    if not ok:
        return None
    return normalized or None


def _scan_free_text(fields, findings: list) -> None:
    """The fail-closed secret gate (D-v0.4.19 shipped-content class):
    diagnostics carry secretscan pattern names and the path only."""
    for path, text in fields:
        hits = secretscan.scan_secrets(text)
        if hits:
            findings.append(
                _finding("secret_shaped_content", path, patterns=hits)
            )


def _free_text_paths(document: dict, *, include_idempotency: bool) -> list:
    fields = [("/goal", document["goal"])]
    for index, item in enumerate(document.get("acceptance_criteria", [])):
        fields.append((f"/acceptance_criteria/{index}", item))
    for index, item in enumerate(document.get("constraints", [])):
        fields.append((f"/constraints/{index}", item))
    for index, item in enumerate(document.get("inputs", [])):
        fields.append((f"/inputs/{index}/ref", item["ref"]))
        if "note" in item:
            fields.append((f"/inputs/{index}/note", item["note"]))
    if include_idempotency and "idempotency_key" in document:
        fields.append(("/idempotency_key", document["idempotency_key"]))
    return fields


def _limit_findings(document: dict, findings: list) -> None:
    """``contradictory_limits`` (contract §8): lexicographic comparison is
    exact for fixed-width RFC3339 Z instants."""
    created = document.get("created_at")
    expires = document.get("expires_at")
    deadline = document.get("retry", {}).get("deadline_at")
    if created is None:
        return
    if expires is not None and expires < created:
        findings.append(_finding("contradictory_limits", "/expires_at"))
    if deadline is not None:
        if deadline < created:
            findings.append(
                _finding("contradictory_limits", "/retry/deadline_at")
            )
        if expires is not None and deadline > expires:
            findings.append(
                _finding("contradictory_limits", "/retry/deadline_at")
            )


def _validate_authoring(document):
    """Shape-validate and normalize one authoring input (§5). Returns
    ``(findings, normalized, requested)``; ``normalized`` spells out the
    frozen defaults and sorts every set-semantics array, and is meaningful
    only when no invalid-class finding was collected."""
    findings: list = []
    if not isinstance(document, dict):
        return [_finding("malformed_input", "/")], None, None

    _data_shape_findings(document, "/", 1, findings)
    for key in document:
        if isinstance(key, str) and key in _FORBIDDEN_AUTHORING_KEYS:
            findings.append(_finding("forbidden_field", f"/{key}"))
    unknown = [
        key
        for key in document
        if isinstance(key, str)
        and key not in _ALLOWED_AUTHORING_KEYS
        and key not in _FORBIDDEN_AUTHORING_KEYS
    ]
    if unknown:
        findings.append(
            _finding("malformed_input", "/", unknown_keys=len(unknown))
        )
    if findings:
        return findings, None, None

    normalized: dict = {
        "authoring_schema": WORKSPEC_AUTHORING_SCHEMA,
        "algorithm_version": WORKSPEC_ALGORITHM_VERSION,
    }
    if document.get("authoring_schema") != WORKSPEC_AUTHORING_SCHEMA:
        findings.append(_finding("malformed_input", "/authoring_schema"))
    if document.get("algorithm_version") != WORKSPEC_ALGORITHM_VERSION:
        findings.append(_finding("malformed_input", "/algorithm_version"))
    for key in _REQUIRED_AUTHORING_KEYS:
        if key not in document:
            findings.append(_finding("malformed_input", f"/{key}"))
    if findings:
        return findings, None, None

    value = _check_instant(document["created_at"], "/created_at", findings)
    if value is not None:
        normalized["created_at"] = value
    if "expires_at" in document:
        value = _check_instant(document["expires_at"], "/expires_at", findings)
        if value is not None:
            normalized["expires_at"] = value
    value = _check_string(
        document["issuer"], "/issuer", findings, min_len=3, max_len=64,
        pattern=_ISSUER_RE,
    )
    if value is not None:
        normalized["issuer"] = value
    value = _check_string_array(
        document["audience"], "/audience", findings, min_items=1, max_items=8,
        item_min=3, item_max=64, pattern=_ISSUER_RE,
    )
    if value is not None:
        normalized["audience"] = value
    value = _check_scope(document["scope"], findings)
    if value is not None:
        normalized["scope"] = value
    value = _check_string(
        document["aos_task_id"], "/aos_task_id", findings, min_len=3,
        max_len=21, pattern=_AOS_TASK_ID_RE,
    )
    if value is not None:
        normalized["aos_task_id"] = value
    if document["data_classification"] not in protocols.DATA_CLASSIFICATIONS:
        findings.append(_finding("malformed_input", "/data_classification"))
    else:
        normalized["data_classification"] = document["data_classification"]
    value = _check_string(document["goal"], "/goal", findings, max_len=4096)
    if value is not None:
        normalized["goal"] = value
    value = _check_string_array(
        document["acceptance_criteria"], "/acceptance_criteria", findings,
        min_items=1, max_items=32, item_max=1024,
    )
    if value is not None:
        normalized["acceptance_criteria"] = value
    if "constraints" in document:
        value = _check_string_array(
            document["constraints"], "/constraints", findings, min_items=0,
            max_items=32, item_max=1024,
        )
        if value is not None:
            normalized["constraints"] = value
    if "required_capabilities" in document:
        value = _check_string_array(
            document["required_capabilities"], "/required_capabilities",
            findings, min_items=0, max_items=16, item_min=2, item_max=64,
            pattern=_CAPABILITY_RE,
        )
        if value is not None:
            normalized["required_capabilities"] = value
    if "inputs" in document:
        value = _check_inputs(document["inputs"], findings)
        if value is not None:
            normalized["inputs"] = value
    if "policy_refs" in document:
        value = _check_policy_refs(document["policy_refs"], findings)
        if value is not None:
            normalized["policy_refs"] = value
    if "retry" in document:
        value = _check_retry(document["retry"], findings)
        if value is not None:
            normalized["retry"] = value
    if "expected_result" in document:
        value = _check_expected_result(document["expected_result"], findings)
        if value is not None:
            normalized["expected_result"] = value
    if "permitted_destinations" in document:
        value = _check_string_array(
            document["permitted_destinations"], "/permitted_destinations",
            findings, min_items=1, max_items=5, item_max=64,
            enum=protocols.PERMITTED_DESTINATIONS,
        )
        if value is not None:
            normalized["permitted_destinations"] = value
    if "runtime_task_uuid" in document:
        value = _check_string(
            document["runtime_task_uuid"], "/runtime_task_uuid", findings,
            min_len=36, max_len=36, pattern=_UUID_RE,
        )
        if value is not None:
            normalized["runtime_task_uuid"] = value
    if "work_spec_id" in document:
        value = _check_string(
            document["work_spec_id"], "/work_spec_id", findings, min_len=36,
            max_len=36, pattern=_UUID_RE,
        )
        if value is not None:
            normalized["work_spec_id"] = value
    if "idempotency_key" in document:
        value = _check_string(
            document["idempotency_key"], "/idempotency_key", findings,
            min_len=8, max_len=128, pattern=_IDEMPOTENCY_RE,
        )
        if value is not None:
            normalized["idempotency_key"] = value
    if "trace" in document:
        value = _check_trace(document["trace"], findings)
        if value is not None:
            normalized["trace"] = value

    requested = None
    if "requested" in document:
        requested = _check_requested(document["requested"], findings)
        if requested is not None:
            normalized["requested"] = requested

    if any(f.status_class == "invalid" for f in findings):
        return findings, None, None

    _scan_free_text(
        _free_text_paths(normalized, include_idempotency=True), findings
    )
    _limit_findings(normalized, findings)

    # Compile-path-only warnings (§8): an explicit value equal, after
    # normalization, to the frozen default. A bare artifact linted without
    # its authoring input never earns these — explicitness is provenance.
    if "permitted_destinations" in document and normalized.get(
        "permitted_destinations"
    ) == list(_DEFAULT_DESTINATIONS):
        findings.append(
            _finding("redundant_explicit_default", "/permitted_destinations")
        )
    if "expected_result" in document and normalized.get(
        "expected_result"
    ) == _DEFAULT_EXPECTED_RESULT:
        findings.append(
            _finding("redundant_explicit_default", "/expected_result")
        )

    if any(f.status_class == "invalid" for f in findings):
        return findings, None, None

    # Normalization spells the frozen defaults out (§5), so two logically
    # equivalent authorings — defaults implicit or explicit — normalize to
    # identical canonical bytes and identical derivation material (§6).
    if "permitted_destinations" not in normalized:
        normalized["permitted_destinations"] = list(_DEFAULT_DESTINATIONS)
    if "expected_result" not in normalized:
        normalized["expected_result"] = {
            "result_schema": _DEFAULT_EXPECTED_RESULT["result_schema"],
            "evidence_kinds": list(_DEFAULT_EXPECTED_RESULT["evidence_kinds"]),
            "min_evidence_count": _DEFAULT_EXPECTED_RESULT[
                "min_evidence_count"
            ],
        }
    return findings, normalized, requested


# ---------------------------------------------------------------------------
# Resolution and the component gates (contract §8, §9).

def _record_sort_key(record: ResolutionRecord):
    return (record.kind, record.requested)


def _resolve_component(registry, requested: str):
    try:
        return registry.resolve(requested), None
    except governance.GovernanceError as refusal:
        code = refusal.reason
        if code not in RESOLUTION_CODES:
            # The eligibility fold: a ref that cannot name a component names
            # no component. Fail closed, never filtered out.
            code = "unknown_component"
        return None, code


def _blocked_dependencies(entry, snapshot: WorkSpecSnapshot) -> list:
    """The governance ``_dependency_problems`` walk, read-only and without
    its binding checks (the U-W1 snapshot holds no bindings): a transitive
    declared dependency is blocking when it is unresolvable in the snapshot,
    its lifecycle is not active, or (for a skill) it is not promoted."""
    problems: list = []
    seen: set = set()
    queue = [entry]
    while queue:
        current = queue.pop(0)
        if current.kind != governance.SKILL_KIND:
            continue
        deps = [
            (ref, snapshot.tools)
            for ref in current.document.get("tool_dependencies", ())
        ]
        deps += [
            (ref, snapshot.skills)
            for ref in current.document.get("skill_dependencies", ())
        ]
        for ref, registry in deps:
            dependency, _ = _resolve_component(registry, ref)
            if dependency is None:
                problems.append(ref)
                continue
            key = (
                dependency.kind,
                dependency.component_id,
                dependency.component_version,
            )
            if key in seen:
                continue
            seen.add(key)
            blocked = (
                dependency.lifecycle != protocols.COMPONENT_LIFECYCLE_ACTIVE
            )
            if dependency.kind == governance.SKILL_KIND and (
                dependency.evaluation != protocols.SKILL_EVALUATION_PROMOTED
            ):
                blocked = True
            if blocked:
                problems.append(ref)
            queue.append(dependency)
    return problems


def _component_gates(fields: dict, requested, snapshot: WorkSpecSnapshot):
    """Resolve the requested ensemble and run every component gate over the
    artifact-equivalent field view. Returns (records, findings). Component
    findings arise only when components were requested (§8)."""
    records: list = []
    findings: list = []
    if not requested:
        return records, findings

    resolved_agent = None
    resolved_skills: list = []
    resolved_tools: list = []

    agent_request = requested.get("agent")
    if agent_request is not None:
        name = agent_request["name"]
        version = agent_request.get("version")
        requested_str = name if version is None else f"{name}/v{version}"
        versions = _agent_versions(snapshot, name)
        agent_path = "/requested/agent"
        if not versions:
            findings.append(
                _finding("unknown_agent", agent_path, requested=requested_str)
            )
            records.append(
                ResolutionRecord(
                    kind="agent", requested=requested_str,
                    code="unknown_component", resolved_id=None,
                    resolved_version=None, resolved_sha256=None,
                )
            )
        elif version is not None and version not in versions:
            findings.append(
                _finding(
                    "unknown_version", agent_path, requested=requested_str
                )
            )
            records.append(
                ResolutionRecord(
                    kind="agent", requested=requested_str,
                    code="unknown_version", resolved_id=None,
                    resolved_version=None, resolved_sha256=None,
                )
            )
        else:
            picked = version if version is not None else versions[-1]
            entry = _agent_entry(snapshot, name, picked)
            resolved_agent = (requested_str, agent_path, entry)
            records.append(
                ResolutionRecord(
                    kind="agent", requested=requested_str, code="resolved",
                    resolved_id=name, resolved_version=picked,
                    resolved_sha256=entry.digest,
                )
            )
            if version is None:
                findings.append(
                    _finding(
                        "unpinned_requirement", agent_path,
                        requested=requested_str, resolved_version=picked,
                    )
                )

    for kind, registry, unknown_code, bucket in (
        ("skills", snapshot.skills, "unknown_skill", resolved_skills),
        ("tools", snapshot.tools, "unknown_tool", resolved_tools),
    ):
        refs = requested.get(kind, [])
        slugs: dict = {}
        for index, ref in enumerate(refs):
            slug, pinned = governance.parse_requirement(ref)
            slugs.setdefault(slug, set()).add(ref)
            ref_path = f"/requested/{kind}/{index}"
            entry, code = _resolve_component(registry, ref)
            if entry is None:
                record_kind = kind[:-1]
                findings.append(
                    _finding(
                        unknown_code if code == "unknown_component"
                        else "unknown_version",
                        ref_path,
                        requested=ref,
                    )
                )
                records.append(
                    ResolutionRecord(
                        kind=record_kind, requested=ref, code=code,
                        resolved_id=None, resolved_version=None,
                        resolved_sha256=None,
                    )
                )
                continue
            bucket.append((ref, ref_path, entry))
            records.append(
                ResolutionRecord(
                    kind=kind[:-1], requested=ref, code="resolved",
                    resolved_id=entry.component_id,
                    resolved_version=entry.component_version,
                    resolved_sha256=entry.digest,
                )
            )
            if pinned is None:
                findings.append(
                    _finding(
                        "unpinned_requirement", ref_path, requested=ref,
                        resolved_version=entry.component_version,
                    )
                )
        for slug, distinct in sorted(slugs.items()):
            if len(distinct) > 1:
                findings.append(
                    _finding(
                        "ambiguous_component", f"/requested/{kind}", slug=slug
                    )
                )

    # Per-component lifecycle/promotion/dependency gates (resolution stays
    # lifecycle-blind; findings make ineligibility visible, §9).
    if resolved_agent is not None:
        requested_str, agent_path, entry = resolved_agent
        if entry.lifecycle != "active":
            findings.append(
                _finding(
                    "lifecycle_not_active", agent_path,
                    requested=requested_str, lifecycle=entry.lifecycle,
                )
            )
    for ref, ref_path, entry in resolved_skills + resolved_tools:
        if entry.lifecycle != protocols.COMPONENT_LIFECYCLE_ACTIVE:
            findings.append(
                _finding(
                    "lifecycle_not_active", ref_path, requested=ref,
                    lifecycle=entry.lifecycle,
                )
            )
    for ref, ref_path, entry in resolved_skills:
        if entry.evaluation != protocols.SKILL_EVALUATION_PROMOTED:
            findings.append(
                _finding(
                    "not_promoted", ref_path, requested=ref,
                    evaluation=entry.evaluation,
                )
            )
        blocked = _blocked_dependencies(entry, snapshot)
        if blocked:
            findings.append(
                _finding(
                    "dependency_blocked", ref_path, requested=ref,
                    blocked_dependencies=blocked[:16],
                )
            )

    # Ensemble gates over the artifact-equivalent view.
    artifact_capabilities = fields.get("required_capabilities", [])
    if resolved_agent is not None:
        requested_str, agent_path, entry = resolved_agent
        document = entry.document

        declared = document.get("capabilities", [])
        missing = sorted(set(artifact_capabilities) - set(declared))
        if missing:
            findings.append(
                _finding(
                    "capability_mismatch", "/required_capabilities",
                    missing_capabilities=missing[:16],
                )
            )

        declared_classes = document.get("data_classifications")
        classification = fields["data_classification"]
        if declared_classes is None:
            # Absence fails closed (the routing rule).
            findings.append(
                _finding(
                    "classification_mismatch", "/data_classification",
                    declared=False,
                )
            )
        elif classification not in declared_classes:
            findings.append(
                _finding(
                    "classification_mismatch", "/data_classification",
                    declared=True,
                )
            )

        agent_scope = document["agent_scope"]
        if agent_scope["level"] == "project" and (
            agent_scope.get("project") != fields["scope"]["project"]
        ):
            # Never the passport's project slug (§11): paths and the level
            # enum only.
            findings.append(_finding("scope_mismatch", "/scope/project"))

        for ref, ref_path, entry_s in resolved_skills:
            constraints = entry_s.document.get("agent_constraints")
            if constraints is not None:
                permitted = constraints["agent_classes"]
                if document["agent_class"] not in permitted:
                    findings.append(
                        _finding(
                            "agent_class_mismatch", agent_path,
                            requested=ref,
                            agent_class=document["agent_class"],
                            permitted_agent_classes=sorted(permitted),
                        )
                    )

    component_required: set = set()
    for ref, ref_path, entry in resolved_skills + resolved_tools:
        component_required.update(
            entry.document.get("required_capabilities", ())
        )
    missing = sorted(component_required - set(artifact_capabilities))
    if missing:
        findings.append(
            _finding(
                "capability_mismatch", "/requested",
                missing_capabilities=missing[:16],
            )
        )

    retry = fields.get("retry")
    if retry is not None:
        attempts = retry["max_attempts"]
        for ref, ref_path, entry in resolved_tools:
            document = entry.document
            unsafe = (
                attempts > 1
                and document["side_effect"]
                == protocols.TOOL_SIDE_EFFECT_MUTATING
                and document["idempotency"]
                != protocols.TOOL_IDEMPOTENCY_REQUIRED_KEY
                and document["compensation"]["strategy"]
                != protocols.TOOL_COMPENSATION_ACTION
            )
            over_budget = attempts > document["retry"]["max_attempts"]
            if unsafe or over_budget:
                findings.append(
                    _finding(
                        "retry_idempotency_incompatible",
                        "/retry/max_attempts", requested=ref,
                    )
                )

    expected = fields["expected_result"]
    expected_kinds = set(expected["evidence_kinds"])
    resolved_components = list(resolved_skills) + list(resolved_tools)
    if resolved_agent is not None:
        requested_str, agent_path, entry = resolved_agent
        resolved_components.append((requested_str, agent_path, entry))
    for ref, ref_path, entry in resolved_components:
        expectations = entry.document.get("evidence_expectations")
        if expectations is not None:
            declared_kinds = set(expectations["evidence_kinds"])
            if not declared_kinds <= expected_kinds or (
                expected["min_evidence_count"]
                < expectations["min_evidence_count"]
            ):
                findings.append(
                    _finding(
                        "result_contract_mismatch", "/expected_result",
                        requested=ref,
                    )
                )

    approval_ref = fields.get("policy_refs", {}).get("approval_ref")
    approval_declarers = list(resolved_tools)
    if resolved_agent is not None:
        approval_declarers.append(resolved_agent)
    for ref, ref_path, entry in approval_declarers:
        document = entry.document
        if document.get("approvals_required") and approval_ref is None:
            # A statement that external authority will be needed — never a
            # check of it (§10).
            findings.append(
                _finding(
                    "approval_reference_required",
                    "/policy_refs/approval_ref", requested=ref,
                )
            )

    records.sort(key=_record_sort_key)
    return records, findings


def _artifact_field_view(document: dict) -> dict:
    """The gate-relevant field view shared by the compile and lint paths."""
    return {
        "data_classification": document["data_classification"],
        "scope": document["scope"],
        "required_capabilities": document.get("required_capabilities", []),
        "retry": document.get("retry"),
        "expected_result": document["expected_result"],
        "policy_refs": document.get("policy_refs", {}),
    }


# ---------------------------------------------------------------------------
# Compile report (contract §7).

def _record_dict(record: ResolutionRecord) -> dict:
    payload = {
        "kind": record.kind,
        "requested": record.requested,
        "code": record.code,
    }
    if record.code == "resolved":
        payload["resolved_id"] = record.resolved_id
        payload["resolved_version"] = record.resolved_version
        payload["resolved_sha256"] = record.resolved_sha256
    return payload


def _finding_dict(finding: LintFinding) -> dict:
    return {
        "code": finding.code,
        "class": finding.status_class,
        "path": finding.path,
        "diagnostics": dict(finding.diagnostics),
    }


def _build_report(
    *,
    status: str,
    findings,
    records,
    provenance: dict,
    defaults,
    snapshot: WorkSpecSnapshot,
    artifact,
) -> dict:
    report: dict = {
        "schema": REPORT_RECORD_SCHEMA,
        "algorithm_version": WORKSPEC_ALGORITHM_VERSION,
        "status": status,
    }
    if artifact is not None:
        report["work_spec_id"] = artifact["work_spec_id"]
        # Recomputed from the artifact body at emission time — never copied
        # from the embedded field (§15).
        report["work_spec_sha256"] = protocols.content_digest(artifact)
    report["findings"] = [_finding_dict(finding) for finding in findings]
    report["resolutions"] = [_record_dict(record) for record in records]
    report["provenance"] = {
        path: provenance[path] for path in sorted(provenance)
    }
    report["defaults_applied"] = sorted(defaults)
    report["registry_state"] = {
        "registry_version": protocols.REGISTRY_VERSION,
        "work_spec_schema_sha256": protocols.REGISTRY[
            _WORK_SPEC_IDENTITY
        ].digest,
        "snapshot_sha256": snapshot_digest(snapshot),
    }
    report[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(report)
    return report


def _spine_refusal_finding(refusal: protocols.ProtocolError) -> LintFinding:
    """The §8 refinement rule: exactly two spine refusals are refined and
    never co-emitted with ``schema_invalid``."""
    if refusal.code == "expires_before_created":
        return _finding("contradictory_limits", "/expires_at")
    if refusal.path == "/policy_refs" or refusal.path.startswith(
        "/policy_refs/"
    ):
        return _finding(
            "malformed_authority_ref", refusal.path, reason=refusal.code
        )
    return _finding("schema_invalid", refusal.path, reason=refusal.code)


# ---------------------------------------------------------------------------
# Public API — compile (contract §7).

def compile_work_spec(authoring, snapshot) -> CompileResult:
    """A pure function: closed authoring input + snapshot -> CompileResult.

    Pipeline (§7): shape-validate and normalize; inject the frozen defaults
    and content-derived identifiers; assemble the candidate and compute its
    digest; validate through ``protocols.validate_document`` (the engine
    every consumer uses); resolve requested components; run every lint gate;
    derive the status and build the self-digested report. The artifact is
    emitted for every status except ``invalid``. Compilation grants nothing.
    """
    _require_snapshot(snapshot)
    findings, normalized, requested = _validate_authoring(authoring)

    def _invalid_result(all_findings) -> CompileResult:
        ordered = _sorted_findings(all_findings)
        report = _build_report(
            status="invalid", findings=ordered, records=(), provenance={},
            defaults=(), snapshot=snapshot, artifact=None,
        )
        return CompileResult(
            status="invalid", findings=ordered, artifact=None, report=report
        )

    if normalized is None:
        return _invalid_result(findings)

    derived = _derive_defaults(normalized)
    defaults_applied = ["schema", "protocol_version", "content_hash_alg"]
    provenance: dict = {
        "/schema": "defaulted",
        "/protocol_version": "defaulted",
        "/content_hash_alg": "defaulted",
        "/content_sha256": "resolved",
    }

    artifact: dict = {
        "schema": _WORK_SPEC_IDENTITY,
        "protocol_version": 1,
        "content_hash_alg": protocols.CONTENT_HASH_ALG,
    }
    for field in (
        "created_at",
        "expires_at",
        "issuer",
        "audience",
        "scope",
        "aos_task_id",
        "runtime_task_uuid",
        "data_classification",
        "goal",
        "acceptance_criteria",
        "constraints",
        "required_capabilities",
        "inputs",
        "policy_refs",
        "retry",
        "expected_result",
        "permitted_destinations",
        "work_spec_id",
        "idempotency_key",
        "trace",
    ):
        if field in normalized:
            artifact[field] = normalized[field]
            # Explicitness is what the AUTHOR supplied; a normalization-
            # spelled default is still a default (§6 provenance).
            if field in authoring:
                provenance[f"/{field}"] = "explicit"
            else:
                provenance[f"/{field}"] = "defaulted"
                defaults_applied.append(field)
    for field, value in (
        ("work_spec_id", derived["work_spec_id"]),
        ("idempotency_key", derived["idempotency_key"]),
        ("trace", derived["trace"]),
    ):
        if field not in artifact:
            artifact[field] = value
            provenance[f"/{field}"] = "defaulted"
            defaults_applied.append(field)
    for sub in ("trace_id", "correlation_id", "causation_id"):
        if sub in artifact["trace"]:
            provenance[f"/trace/{sub}"] = provenance["/trace"]
    for sub in ("result_schema", "evidence_kinds", "min_evidence_count"):
        provenance[f"/expected_result/{sub}"] = provenance["/expected_result"]
    artifact[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(artifact)

    try:
        protocols.validate_document(artifact)
    except protocols.ProtocolError as refusal:
        # Unreachable for a shape-valid authoring input; kept as a
        # fail-closed refusal, not an assert.
        return _invalid_result(
            list(findings) + [_spine_refusal_finding(refusal)]
        )

    records, component_findings = _component_gates(
        _artifact_field_view(artifact), requested, snapshot
    )
    ordered = _sorted_findings(list(findings) + component_findings)
    status = _derive_status(ordered)
    report = _build_report(
        status=status,
        findings=ordered,
        records=records,
        provenance=provenance,
        defaults=defaults_applied,
        snapshot=snapshot,
        artifact=artifact,
    )
    return CompileResult(
        status=status, findings=ordered, artifact=artifact, report=report
    )


# ---------------------------------------------------------------------------
# Public API — lint (contract §8).

def _accept_workspec(artifact) -> dict:
    """Canonical round-trip snapshot + registry validation + identity check.
    Raises the spine's ProtocolError (closed, value-free) or a closed
    WorkSpecError for a valid document of the wrong schema."""
    if not isinstance(artifact, dict):
        raise protocols.ProtocolError("not_an_object")
    document = protocols.parse_canonical(
        protocols.serialize_canonical(artifact)
    )
    entry = protocols.validate_document(document)
    if entry.identity != _WORK_SPEC_IDENTITY:
        raise WorkSpecError("wrong_schema", where=_WORK_SPEC_IDENTITY)
    return document


def lint_work_spec(artifact, snapshot, requested=None) -> LintReport:
    """Apply the semantic lint gates to an existing artifact (compile runs
    the same gates inline). Component findings arise only when ``requested``
    names components; an artifact linted alone earns only the
    artifact-static gates."""
    _require_snapshot(snapshot)
    if not isinstance(artifact, dict):
        ordered = (_finding("malformed_input", "/"),)
        return LintReport(status="invalid", findings=ordered, resolutions=())
    try:
        document = protocols.parse_canonical(
            protocols.serialize_canonical(artifact)
        )
        entry = protocols.validate_document(document)
    except protocols.ProtocolError as refusal:
        ordered = (_spine_refusal_finding(refusal),)
        return LintReport(
            status=_derive_status(ordered), findings=ordered, resolutions=()
        )
    if entry.identity != _WORK_SPEC_IDENTITY:
        ordered = (
            _finding("schema_invalid", "/schema", reason="wrong_schema"),
        )
        return LintReport(status="invalid", findings=ordered, resolutions=())

    findings: list = []
    seen_pairs = set()
    duplicate = False
    for item in document.get("inputs", []):
        pair = (item["ref_kind"], item["ref"])
        if pair in seen_pairs:
            duplicate = True
        seen_pairs.add(pair)
    if duplicate:
        findings.append(_finding("duplicate_item", "/inputs"))
    _scan_free_text(
        _free_text_paths(document, include_idempotency=True), findings
    )
    _limit_findings(document, findings)

    requested_normalized = None
    if requested is not None:
        requested_normalized = _check_requested(requested, findings)

    records: tuple = ()
    if not any(f.status_class == "invalid" for f in findings):
        record_list, component_findings = _component_gates(
            _artifact_field_view(document), requested_normalized, snapshot
        )
        findings += component_findings
        records = tuple(record_list)
    ordered = _sorted_findings(findings)
    return LintReport(
        status=_derive_status(ordered), findings=ordered, resolutions=records
    )


# ---------------------------------------------------------------------------
# Report acceptance (the frozen sidecar rule, §7): digest-bind before use,
# then enforce the closed report shape. A digest-bound report is still an
# untrusted cross-boundary document (§3) — an artifact holder can seal any
# body — so every field a consumer dereferences or renders is validated
# here, and every deviation is the closed ``malformed_report`` refusal,
# never an uncontrolled exception and never rendered output.

#: The closed key set of a compile report (§7). ``work_spec_id`` and
#: ``work_spec_sha256`` exist exactly when an artifact exists; only
#: digest-bound reports reach this gate, so both are present here.
_REPORT_KEYS = frozenset((
    "schema",
    "algorithm_version",
    "status",
    "work_spec_id",
    "work_spec_sha256",
    "findings",
    "resolutions",
    "provenance",
    "defaults_applied",
    "registry_state",
    protocols.CONTENT_HASH_FIELD,
))

_REPORT_REQUIRED_KEYS = (
    "schema",
    "algorithm_version",
    "status",
    "work_spec_sha256",
    "findings",
    "resolutions",
    "provenance",
    "defaults_applied",
    "registry_state",
)

_RESOLUTION_RECORD_KINDS = ("agent", "skill", "tool")
_RESOLUTION_RECORD_KEYS = frozenset((
    "kind",
    "requested",
    "code",
    "resolved_id",
    "resolved_version",
    "resolved_sha256",
))
_RESOLVED_FIELD_KEYS = ("resolved_id", "resolved_version", "resolved_sha256")
#: One agent request plus 16 skills and 16 tools bound what compile emits.
_MAX_RESOLUTION_RECORDS = 33
#: The agent-record pin spelling ``_component_gates`` emits: ``v`` plus a
#: passport version 1..999999.
_AGENT_PIN_RE = re.compile(r"^v[1-9][0-9]{0,5}$", re.ASCII)


def _requested_ref_shape_ok(kind: str, requested) -> bool:
    if not isinstance(requested, str):
        return False
    if kind == "agent":
        name, sep, pin = requested.partition("/")
        if not _AGENT_NAME_RE.fullmatch(name):
            return False
        if not sep:
            return True
        return bool(_AGENT_PIN_RE.fullmatch(pin))
    return bool(_REQUIREMENT_RE.fullmatch(requested))


def _resolution_record_shape_ok(record) -> bool:
    if not isinstance(record, dict) or any(
        key not in _RESOLUTION_RECORD_KEYS for key in record
    ):
        return False
    kind = record.get("kind")
    if kind not in _RESOLUTION_RECORD_KINDS:
        return False
    if record.get("code") not in RESOLUTION_CODES:
        return False
    if not _requested_ref_shape_ok(kind, record.get("requested")):
        return False
    if record["code"] != "resolved":
        # The resolved fields are populated exactly when code is resolved.
        return not any(key in record for key in _RESOLVED_FIELD_KEYS)
    if any(key not in record for key in _RESOLVED_FIELD_KEYS):
        return False
    resolved_id = record["resolved_id"]
    if not isinstance(resolved_id, str):
        return False
    if kind == "agent":
        id_ok = bool(_AGENT_NAME_RE.fullmatch(resolved_id))
    else:
        id_ok = "/" not in resolved_id and bool(
            _REQUIREMENT_RE.fullmatch(resolved_id)
        )
    version = record["resolved_version"]
    version_ok = (
        isinstance(version, int)
        and not isinstance(version, bool)
        and 1 <= version <= 999999
    )
    sha = record["resolved_sha256"]
    sha_ok = isinstance(sha, str) and bool(_SHA256_RE.fullmatch(sha))
    return id_ok and version_ok and sha_ok


def _check_report_shape(fresh: dict) -> None:
    if any(key not in _REPORT_KEYS for key in fresh):
        raise WorkSpecError("malformed_report")
    if any(key not in fresh for key in _REPORT_REQUIRED_KEYS):
        raise WorkSpecError("malformed_report")
    if fresh["algorithm_version"] != WORKSPEC_ALGORITHM_VERSION:
        raise WorkSpecError("malformed_report")
    if fresh["status"] not in WORKSPEC_LINT_STATUSES:
        raise WorkSpecError("malformed_report")
    if "work_spec_id" in fresh:
        work_spec_id = fresh["work_spec_id"]
        if not isinstance(work_spec_id, str) or not _UUID_RE.fullmatch(
            work_spec_id
        ):
            raise WorkSpecError("malformed_report")
    if not isinstance(fresh["findings"], list) or any(
        not isinstance(item, dict) for item in fresh["findings"]
    ):
        raise WorkSpecError("malformed_report")
    if not isinstance(fresh["defaults_applied"], list) or any(
        not isinstance(item, str) for item in fresh["defaults_applied"]
    ):
        raise WorkSpecError("malformed_report")
    if not isinstance(fresh["registry_state"], dict):
        raise WorkSpecError("malformed_report")
    provenance = fresh["provenance"]
    if not isinstance(provenance, dict):
        raise WorkSpecError("malformed_report")
    for path, marker in provenance.items():
        if not path.startswith("/") or marker not in PROVENANCE_CLASSES:
            raise WorkSpecError("malformed_report")
    resolutions = fresh["resolutions"]
    if not isinstance(resolutions, list) or (
        len(resolutions) > _MAX_RESOLUTION_RECORDS
    ):
        raise WorkSpecError("malformed_report")
    for record in resolutions:
        if not _resolution_record_shape_ok(record):
            raise WorkSpecError("malformed_report")


def _accept_report(report, artifact_digest: str) -> dict:
    if not isinstance(report, dict):
        raise WorkSpecError("malformed_report")
    try:
        fresh = protocols.parse_canonical(protocols.serialize_canonical(report))
    except protocols.ProtocolError:
        raise WorkSpecError("malformed_report") from None
    if fresh.get("schema") != REPORT_RECORD_SCHEMA:
        raise WorkSpecError("malformed_report")
    declared = fresh.get(protocols.CONTENT_HASH_FIELD)
    if protocols.content_digest(fresh) != declared:
        # An edited report is no report at all.
        raise WorkSpecError("report_mismatch")
    if fresh.get("work_spec_sha256") != artifact_digest:
        raise WorkSpecError("report_mismatch")
    _check_report_shape(fresh)
    return fresh


# ---------------------------------------------------------------------------
# Public API — decompiler (contract §12).

_DECOMPILE_SECTIONS = (
    ("identity", (
        "schema", "protocol_version", "content_hash_alg", "content_sha256",
        "work_spec_id", "aos_task_id", "runtime_task_uuid", "created_at",
        "expires_at", "issuer", "audience", "idempotency_key",
    )),
    ("intent", (
        "goal", "acceptance_criteria", "constraints", "required_capabilities",
    )),
    ("classification-scope", ("data_classification", "scope")),
    ("destinations", ("permitted_destinations",)),
    ("inputs", ("inputs",)),
    ("authority-references", ("policy_refs",)),
    ("retry", ("retry",)),
    ("result-contract", ("expected_result",)),
    ("trace", ("trace",)),
)


def _ascii_string(text: str) -> str:
    """A deterministic ASCII rendering of one string value: quoted, escaped,
    and truncated at the frozen 120-code-point bound with the fixed
    ``...(+N chars)`` marker."""
    marker = ""
    if len(text) > _DISPLAY_TEXT_LIMIT:
        marker = f"...(+{len(text) - _DISPLAY_TEXT_LIMIT} chars)"
        text = text[:_DISPLAY_TEXT_LIMIT]
    parts = []
    for ch in text:
        cp = ord(ch)
        if ch in ('"', "\\"):
            parts.append("\\" + ch)
        elif 0x20 <= cp <= 0x7E:
            parts.append(ch)
        elif cp <= 0xFFFF:
            parts.append(f"\\u{cp:04x}")
        else:
            cp -= 0x10000
            parts.append(
                f"\\u{0xD800 + (cp >> 10):04x}\\u{0xDC00 + (cp & 0x3FF):04x}"
            )
    return '"' + "".join(parts) + '"' + marker


def _render_value(value) -> str:
    if isinstance(value, str):
        return _ascii_string(value)
    return str(value)


def _leaf_paths(field: str, value) -> list:
    leaves: list = []
    base = f"/{field}"
    if isinstance(value, dict):
        for key in sorted(value):
            leaves.append((_join(base, key), value[key]))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            item_path = _join(base, str(index))
            if isinstance(item, dict):
                for key in sorted(item):
                    leaves.append((_join(item_path, key), item[key]))
            else:
                leaves.append((item_path, item))
    else:
        leaves.append((base, value))
    return leaves


def decompile_work_spec(artifact, report=None) -> str:
    """Deterministic, bounded, secret-safe display text (display-only; the
    output is never parsed back). With a digest-bound report, fields carry
    their provenance markers and the resolution records render as an
    advisory section; an unbound or edited report refuses."""
    document = _accept_workspec(artifact)
    digest = protocols.content_digest(document)
    bound_report = None
    if report is not None:
        bound_report = _accept_report(report, digest)
    # Redaction before rendering: an external artifact that never met the
    # compile-time refusal still cannot leak a secret-shaped value.
    safe = secretscan.redact_tree(document)
    provenance = bound_report.get("provenance", {}) if bound_report else {}

    lines = [f"work-spec {_WORK_SPEC_IDENTITY}", f"content_sha256 {digest}"]
    if bound_report is not None:
        lines.append(f"status {bound_report.get('status')}")
    for section, fields in _DECOMPILE_SECTIONS:
        leaves: list = []
        for field in fields:
            if field in safe:
                leaves.extend(_leaf_paths(field, safe[field]))
        if not leaves:
            continue
        lines.append(f"section {section}")
        for path, value in sorted(leaves, key=lambda leaf: leaf[0]):
            line = f"  {path}: {_render_value(value)}"
            if bound_report is not None:
                top = "/" + path[1:].split("/", 1)[0]
                marker = provenance.get(path, provenance.get(top))
                if marker is not None:
                    line += f" [{marker}]"
            lines.append(line)
    if bound_report is not None and bound_report.get("resolutions"):
        lines.append("section resolutions")
        for record in bound_report["resolutions"]:
            row = f"  {record['kind']} {record['requested']} {record['code']}"
            if record.get("code") == "resolved":
                row += (
                    f" {record['resolved_id']}/v{record['resolved_version']}"
                    f" {record['resolved_sha256']}"
                )
            lines.append(row)
    return "\n".join(lines) + "\n"


def authoring_view(artifact, report) -> dict:
    """Reconstruct a normalized authoring input from an artifact and its
    digest-bound report: explicit fields from the artifact, requested
    components from the resolution records. The frozen semantic fixed point:
    compiling this view against the same snapshot reproduces an identical
    ``content_sha256`` and an identical report body. Reconstruction of the
    author's original input bytes is not claimed."""
    document = _accept_workspec(artifact)
    bound = _accept_report(report, protocols.content_digest(document))
    provenance = bound.get("provenance", {})
    view: dict = {
        "authoring_schema": WORKSPEC_AUTHORING_SCHEMA,
        "algorithm_version": WORKSPEC_ALGORITHM_VERSION,
    }
    for field in _AUTHORABLE_FIELDS:
        if provenance.get(f"/{field}") == "explicit" and field in document:
            view[field] = document[field]
    requested: dict = {}
    skills: list = []
    tools: list = []
    for record in bound.get("resolutions", []):
        kind = record.get("kind")
        requested_str = record.get("requested")
        if kind == "agent" and isinstance(requested_str, str):
            if "/" in requested_str:
                name, _, pin = requested_str.partition("/")
                requested["agent"] = {"name": name, "version": int(pin[1:])}
            else:
                requested["agent"] = {"name": requested_str}
        elif kind == "skill" and isinstance(requested_str, str):
            skills.append(requested_str)
        elif kind == "tool" and isinstance(requested_str, str):
            tools.append(requested_str)
    if skills:
        requested["skills"] = skills
    if tools:
        requested["tools"] = tools
    if requested:
        view["requested"] = requested
    return view


# ---------------------------------------------------------------------------
# Public API — semantic diff (contract §13).

_RAW = "raw"
_DIGEST = "digest"

_DIFF_SCALARS = (
    ("schema", "metadata", _RAW),
    ("protocol_version", "metadata", _RAW),
    ("content_hash_alg", "metadata", _RAW),
    ("created_at", "metadata", _RAW),
    ("work_spec_id", "metadata", _RAW),
    ("aos_task_id", "metadata", _RAW),
    ("runtime_task_uuid", "metadata", _RAW),
    ("issuer", "metadata", _RAW),
    ("expires_at", "budgets_limits", _RAW),
    ("data_classification", "classification", _RAW),
    ("goal", "requirements", _DIGEST),
    ("idempotency_key", "retry_idempotency", _DIGEST),
)

_DIFF_SUBSCALARS = (
    ("scope", "project", "classification", _RAW),
    ("scope", "tenant", "classification", _RAW),
    ("trace", "trace_id", "metadata", _RAW),
    ("trace", "correlation_id", "metadata", _RAW),
    ("trace", "causation_id", "metadata", _RAW),
    ("policy_refs", "policy_ref", "authority_references", _RAW),
    ("policy_refs", "approval_ref", "authority_references", _RAW),
    ("policy_refs", "budget_ref", "authority_references", _RAW),
    ("retry", "max_attempts", "retry_idempotency", _RAW),
    ("retry", "deadline_at", "retry_idempotency", _RAW),
    ("expected_result", "result_schema", "result_contract", _RAW),
    ("expected_result", "min_evidence_count", "result_contract", _RAW),
)

_DIFF_SET_ARRAYS = (
    ("audience", "metadata", _RAW),
    ("permitted_destinations", "metadata", _RAW),
    ("required_capabilities", "requirements", _RAW),
    ("acceptance_criteria", "requirements", _DIGEST),
    ("constraints", "requirements", _DIGEST),
)


def _text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _side_fields(entry: dict, side: str, value, mode: str) -> None:
    """Populate one side of a diff entry: raw for allowlisted paths, sha256
    digest + code-point length for free text (no free-text value can appear,
    so no raw secret value can appear)."""
    if mode == _RAW:
        entry[side] = value
    else:
        entry[f"{side}_sha256"] = _text_digest(value)
        entry[f"{side}_chars"] = len(value)


def _scalar_entry(category: str, path: str, a_value, b_value, mode: str):
    if a_value == b_value:
        return None
    entry: dict = {"category": category, "path": path}
    if a_value is None:
        entry["kind"] = "added"
        _side_fields(entry, "to", b_value, mode)
    elif b_value is None:
        entry["kind"] = "removed"
        _side_fields(entry, "from", a_value, mode)
    else:
        entry["kind"] = "changed"
        _side_fields(entry, "from", a_value, mode)
        _side_fields(entry, "to", b_value, mode)
    return entry


def _set_array_entries(category: str, path: str, a_items, b_items, mode: str):
    entries: list = []
    a_set, b_set = set(a_items or ()), set(b_items or ())
    for item in sorted(b_set - a_set):
        entry = {"category": category, "kind": "added", "path": path}
        _side_fields(entry, "to", item, mode)
        entries.append(entry)
    for item in sorted(a_set - b_set):
        entry = {"category": category, "kind": "removed", "path": path}
        _side_fields(entry, "from", item, mode)
        entries.append(entry)
    return entries


_INPUT_FIELD_MODES = (
    ("ref_kind", _RAW),
    ("ref", _DIGEST),
    ("sha256", _RAW),
    ("note", _DIGEST),
)


def _input_key(item: dict):
    return (item["ref_kind"], _text_digest(item["ref"]))


def _whole_input_entries(kind: str, side: str, index: int, item: dict):
    entries: list = []
    for field, mode in _INPUT_FIELD_MODES:
        if field in item:
            entry = {
                "category": "metadata",
                "kind": kind,
                "path": f"/inputs/{index}/{field}",
            }
            _side_fields(entry, side, item[field], mode)
            entries.append(entry)
    return entries


def _input_entries(a_inputs, b_inputs):
    """Inputs key by (ref_kind, sha256-of-ref) (§13): matched keys diff their
    ``sha256``/``note`` sub-fields at the to-side index; unmatched items emit
    per-field added/removed entries at their own side's index."""
    entries: list = []
    a_by_key: dict = {}
    b_by_key: dict = {}
    for index, item in enumerate(a_inputs or []):
        a_by_key.setdefault(_input_key(item), []).append((index, item))
    for index, item in enumerate(b_inputs or []):
        b_by_key.setdefault(_input_key(item), []).append((index, item))
    for key in sorted(set(a_by_key) | set(b_by_key)):
        a_list = a_by_key.get(key, [])
        b_list = b_by_key.get(key, [])
        for (a_index, a_item), (b_index, b_item) in zip(a_list, b_list):
            if protocols.serialize_canonical(a_item) == (
                protocols.serialize_canonical(b_item)
            ):
                continue
            for field, mode in _INPUT_FIELD_MODES[1:]:
                path = f"/inputs/{b_index}/{field}"
                a_value = a_item.get(field)
                b_value = b_item.get(field)
                entry = _scalar_entry("metadata", path, a_value, b_value, mode)
                if entry is not None:
                    entries.append(entry)
        for a_index, a_item in a_list[len(b_list):]:
            entries.extend(
                _whole_input_entries("removed", "from", a_index, a_item)
            )
        for b_index, b_item in b_list[len(a_list):]:
            entries.extend(
                _whole_input_entries("added", "to", b_index, b_item)
            )
    return entries


def _resolution_entries(report_a: dict, report_b: dict):
    a_records = {
        (r["kind"], r["requested"]): (i, r)
        for i, r in enumerate(report_a.get("resolutions", []))
    }
    b_records = {
        (r["kind"], r["requested"]): (i, r)
        for i, r in enumerate(report_b.get("resolutions", []))
    }
    entries: list = []
    for key in sorted(set(a_records) | set(b_records)):
        a_pair = a_records.get(key)
        b_pair = b_records.get(key)
        if a_pair is None:
            index, record = b_pair
            entries.append(
                {
                    "category": "resolutions",
                    "kind": "added",
                    "path": f"/resolutions/{index}",
                    "to": dict(record),
                }
            )
        elif b_pair is None:
            index, record = a_pair
            entries.append(
                {
                    "category": "resolutions",
                    "kind": "removed",
                    "path": f"/resolutions/{index}",
                    "from": dict(record),
                }
            )
        elif protocols.serialize_canonical(a_pair[1]) != (
            protocols.serialize_canonical(b_pair[1])
        ):
            entries.append(
                {
                    "category": "resolutions",
                    "kind": "changed",
                    "path": f"/resolutions/{b_pair[0]}",
                    "from": dict(a_pair[1]),
                    "to": dict(b_pair[1]),
                }
            )
    return entries


def _entry_sort_key(entry: dict):
    return (
        DIFF_CATEGORIES.index(entry["category"]),
        entry["path"],
        DIFF_CHANGE_KINDS.index(entry["kind"]),
        protocols.serialize_canonical(entry),
    )


def semantic_diff(a, b, report_a=None, report_b=None) -> dict:
    """Deterministic semantic diff over two schema-valid WorkSpec artifacts.

    ``from_sha256``/``to_sha256`` are recomputed from each body — a lying
    embedded ``content_sha256`` refuses at validation and can never steer
    the diff. A supplied report must digest-bind its artifact, else the diff
    refuses; the ``resolutions`` category exists exactly when both reports
    are supplied and bound.
    """
    doc_a = _accept_workspec(a)
    doc_b = _accept_workspec(b)
    from_sha256 = protocols.content_digest(doc_a)
    to_sha256 = protocols.content_digest(doc_b)
    bound_a = _accept_report(report_a, from_sha256) if report_a is not None \
        else None
    bound_b = _accept_report(report_b, to_sha256) if report_b is not None \
        else None

    entries: list = []
    for field, category, mode in _DIFF_SCALARS:
        entry = _scalar_entry(
            category, f"/{field}", doc_a.get(field), doc_b.get(field), mode
        )
        if entry is not None:
            entries.append(entry)
    for field, sub, category, mode in _DIFF_SUBSCALARS:
        entry = _scalar_entry(
            category,
            f"/{field}/{sub}",
            doc_a.get(field, {}).get(sub),
            doc_b.get(field, {}).get(sub),
            mode,
        )
        if entry is not None:
            entries.append(entry)
    for field, category, mode in _DIFF_SET_ARRAYS:
        entries.extend(
            _set_array_entries(
                category, f"/{field}", doc_a.get(field), doc_b.get(field),
                mode,
            )
        )
    entries.extend(
        _set_array_entries(
            "result_contract",
            "/expected_result/evidence_kinds",
            doc_a["expected_result"]["evidence_kinds"],
            doc_b["expected_result"]["evidence_kinds"],
            _RAW,
        )
    )
    entries.extend(_input_entries(doc_a.get("inputs"), doc_b.get("inputs")))
    if bound_a is not None and bound_b is not None:
        entries.extend(_resolution_entries(bound_a, bound_b))

    record: dict = {
        "schema": DIFF_RECORD_SCHEMA,
        "algorithm_version": WORKSPEC_ALGORITHM_VERSION,
        "from_sha256": from_sha256,
        "to_sha256": to_sha256,
        "changes": sorted(entries, key=_entry_sort_key),
    }
    record[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(record)
    return record
