"""U-A3 routing: canonical request validation, per-agent eligibility, and —
from Wave 3 — deterministic ordering, governed routing-plan persistence, plan
reads, verification and derived staleness.

Contract: agentic-os-v0.4-u-a3-routing-handoffs-contract.md §6-12, §17.

Two layers live here, deliberately together:

- **Pure functions** (Wave 2): `validate_request`/`canonicalize_request`/
  `request_digest` close and hash the request document; `evaluate_candidate`
  takes one normalized request and one explicit `CandidateSnapshot` and
  returns a closed verdict — no SQL, no clock, no mutation. These stay pure.
- **The database-owning plan layer** (Wave 3): `create_plan` owns exactly one
  `db.transaction`, re-reads every fact under `BEGIN IMMEDIATE`, enumerates
  and evaluates every governed identity, orders the eligible ones by the
  frozen tuple (§8), persists the plan and its candidate rows with the
  `_PENDING_HASH` two-step (§12), and emits one audit event; `list_plans`,
  `plan_public`, `verify_plan` and `plan_staleness` are read-only and never
  write, rehash, repair or emit. Routing is advisory: a plan grants nothing,
  executes nothing, installs nothing.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from . import db, events, ids, models, ops, passports, protocols, utils
from .ids import MAX_ID
from .models import Agent, AgentPassport, RoutingPlan, RoutingPlanCandidate
from .ops import _PENDING_HASH
from .utils import AosError

#: Pinned constants (§6, canonical_request_identity). Both are required in
#: every normalized request and both affect canonical bytes and the digest;
#: no other value is accepted in this build.
REQUEST_SCHEMA = "aos.routing-request/v1"
ALGORITHM_VERSION = "aos-routing-order/v1"

#: Preference vocabularies (§6C). New to U-A3's request surface — not part of
#: Wave 1's stored vocabulary, so they live here rather than in models.py.
SCOPE_PREFERENCES = ("specific_first", "none")
SURPLUS_POLICIES = ("minimal", "ignore")

DEFAULT_SCOPE_PREFERENCE = "specific_first"
DEFAULT_SURPLUS_POLICY = "minimal"
DEFAULT_MAX_CANDIDATES = 5
DEFAULT_INCLUDE_DIAGNOSTICS = True

_MODEL_CAPABILITY_KEYS = frozenset({"min_context_tokens", "modalities"})
_MAX_MIN_CONTEXT_TOKENS = 99_999_999
_MAX_MAX_CANDIDATES = 32

_IDENTITY_KEYS = frozenset(
    {"request_schema", "algorithm_version", "task", "project"}
)
_HARD_REQUIREMENT_KEYS = frozenset(
    {
        "task_families",
        "capabilities",
        "evidence_kinds",
        "required_data_classification",
        "required_autonomy",
        "required_scope",
        "required_agent_class",
        "skills",
        "tools",
        "model_capabilities",
    }
)
_PREFERENCE_KEYS = frozenset(
    {"preferred_agent", "scope_preference", "surplus_policy"}
)
_OUTPUT_KEYS = frozenset({"max_candidates", "include_diagnostics"})
_ALLOWED_REQUEST_KEYS = (
    _IDENTITY_KEYS | _HARD_REQUIREMENT_KEYS | _PREFERENCE_KEYS | _OUTPUT_KEYS
)


class RoutingRequestError(AosError):
    """A routing request document fails validation. One actionable line."""


# ---------------------------------------------------------------------------
# Request validation, normalization, canonicalization, digest (§6).

def _require_bounded_int(value, *, field: str, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise RoutingRequestError(f"{field} must be an integer.")
    if not (minimum <= value <= maximum):
        raise RoutingRequestError(
            f"{field} must be between {minimum} and {maximum}."
        )
    return value


def _require_enum_scalar(value, *, field: str, allowed: tuple[str, ...]) -> str:
    if not isinstance(value, str):
        raise RoutingRequestError(f"{field} must be a string.")
    if value not in allowed:
        raise RoutingRequestError(
            f"Unknown {field} {value!r}. Allowed: {'|'.join(allowed)}"
        )
    return value


def _require_bounded_array(
    value,
    *,
    field: str,
    min_items: int,
    max_items: int,
    pattern: str | None = None,
    allowed: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    """A closed, bounded, duplicate-refusing string array, canonically
    sorted by code point (§6 normalization_rules). Exactly one of `pattern`
    (a free-form but shape-bound requirement) or `allowed` (a closed enum)
    is meaningful per field; both are optional so a caller can pass neither."""
    if not isinstance(value, list):
        raise RoutingRequestError(f"{field} must be an array.")
    if not (min_items <= len(value) <= max_items):
        raise RoutingRequestError(
            f"{field} must contain between {min_items} and {max_items} items."
        )
    compiled = re.compile(pattern, re.ASCII) if pattern else None
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise RoutingRequestError(f"{field} items must be strings.")
        if compiled is not None and not compiled.fullmatch(item):
            raise RoutingRequestError(
                f"{field} item {item!r} has an invalid format."
            )
        if allowed is not None and item not in allowed:
            raise RoutingRequestError(
                f"Unknown {field} item {item!r}. Allowed: {'|'.join(allowed)}"
            )
        if item in seen:
            raise RoutingRequestError(
                f"{field} contains a duplicate item: {item!r}."
            )
        seen.add(item)
    return tuple(sorted(value))


def _validate_model_capabilities(value) -> dict:
    if not isinstance(value, dict):
        raise RoutingRequestError("model_capabilities must be an object.")
    unknown = set(value) - _MODEL_CAPABILITY_KEYS
    if unknown:
        raise RoutingRequestError(
            "Unknown model_capabilities field(s): " + ", ".join(sorted(unknown))
        )
    if not value:
        raise RoutingRequestError(
            "model_capabilities must declare at least one of: "
            + ", ".join(sorted(_MODEL_CAPABILITY_KEYS))
        )
    normalized: dict = {}
    if "min_context_tokens" in value:
        normalized["min_context_tokens"] = _require_bounded_int(
            value["min_context_tokens"],
            field="min_context_tokens",
            minimum=1,
            maximum=_MAX_MIN_CONTEXT_TOKENS,
        )
    if "modalities" in value:
        normalized["modalities"] = _require_bounded_array(
            value["modalities"],
            field="modalities",
            min_items=1,
            max_items=len(protocols.AGENT_MODALITIES),
            allowed=protocols.AGENT_MODALITIES,
        )
    return normalized


def validate_request(raw: dict) -> dict:
    """Validate and normalize one routing request document (§6).

    Refuses: a non-object input, an unknown key, a wrong-constant
    `request_schema`/`algorithm_version`, a duplicate array value, an
    out-of-bound array or integer, a bool where an integer or enum string is
    required, and a `model_capabilities` object with zero or unrecognized
    keys.

    Returns a fresh, closed-key dict. Absent optional hard-requirement
    fields are omitted entirely (the dimension is unconstrained); the four
    fields with defaults (`scope_preference`, `surplus_policy`,
    `max_candidates`, `include_diagnostics`) always appear, defaulted or not
    — so two logically equivalent requests (key/array order shuffled,
    defaults left implicit or spelled out) normalize, canonicalize and
    digest identically. Never mutates `raw`. Does not resolve whether
    `task`/`project`/`preferred_agent` actually exist — that is a later,
    database-owning layer's job.
    """
    if not isinstance(raw, dict):
        raise RoutingRequestError("A routing request must be a JSON object.")

    unknown = set(raw) - _ALLOWED_REQUEST_KEYS
    if unknown:
        raise RoutingRequestError(
            "Unknown routing request field(s): " + ", ".join(sorted(unknown))
        )

    if raw.get("request_schema") != REQUEST_SCHEMA:
        raise RoutingRequestError(f"request_schema must be {REQUEST_SCHEMA!r}.")
    if raw.get("algorithm_version") != ALGORITHM_VERSION:
        raise RoutingRequestError(
            f"algorithm_version must be {ALGORITHM_VERSION!r}."
        )

    normalized: dict = {
        "request_schema": REQUEST_SCHEMA,
        "algorithm_version": ALGORITHM_VERSION,
    }

    if "task" in raw:
        normalized["task"] = _require_bounded_int(
            raw["task"], field="task", minimum=1, maximum=MAX_ID
        )

    if "project" in raw:
        project = raw["project"]
        if not isinstance(project, str):
            raise RoutingRequestError("project must be a string.")
        if len(project) > 64:
            raise RoutingRequestError("project must be at most 64 characters.")
        try:
            models.validate_slug(project)
        except AosError as exc:
            raise RoutingRequestError(str(exc)) from None
        normalized["project"] = project

    if "task_families" in raw:
        normalized["task_families"] = _require_bounded_array(
            raw["task_families"],
            field="task_families",
            min_items=1,
            max_items=16,
            pattern=protocols.TASK_FAMILY_PATTERN,
        )

    if "capabilities" in raw:
        normalized["capabilities"] = _require_bounded_array(
            raw["capabilities"],
            field="capabilities",
            min_items=1,
            max_items=16,
            pattern=protocols.CAPABILITY_PATTERN,
        )

    if "evidence_kinds" in raw:
        normalized["evidence_kinds"] = _require_bounded_array(
            raw["evidence_kinds"],
            field="evidence_kinds",
            min_items=1,
            max_items=len(models.EVIDENCE_KINDS),
            allowed=models.EVIDENCE_KINDS,
        )

    if "required_data_classification" in raw:
        normalized["required_data_classification"] = _require_enum_scalar(
            raw["required_data_classification"],
            field="required_data_classification",
            allowed=models.MEMORY_SENSITIVITIES,
        )

    if "required_autonomy" in raw:
        normalized["required_autonomy"] = _require_bounded_array(
            raw["required_autonomy"],
            field="required_autonomy",
            min_items=1,
            max_items=len(models.AGENT_AUTONOMY_LEVELS),
            allowed=models.AGENT_AUTONOMY_LEVELS,
        )

    if "required_scope" in raw:
        normalized["required_scope"] = _require_enum_scalar(
            raw["required_scope"], field="required_scope", allowed=models.AGENT_SCOPES
        )

    if "required_agent_class" in raw:
        normalized["required_agent_class"] = _require_enum_scalar(
            raw["required_agent_class"],
            field="required_agent_class",
            allowed=models.AGENT_CLASSES,
        )

    if "skills" in raw:
        normalized["skills"] = _require_bounded_array(
            raw["skills"],
            field="skills",
            min_items=1,
            max_items=16,
            pattern=protocols.REQUIREMENT_PATTERN,
        )

    if "tools" in raw:
        normalized["tools"] = _require_bounded_array(
            raw["tools"],
            field="tools",
            min_items=1,
            max_items=16,
            pattern=protocols.REQUIREMENT_PATTERN,
        )

    if "model_capabilities" in raw:
        normalized["model_capabilities"] = _validate_model_capabilities(
            raw["model_capabilities"]
        )

    if "preferred_agent" in raw:
        preferred = raw["preferred_agent"]
        if not isinstance(preferred, str):
            raise RoutingRequestError("preferred_agent must be a string.")
        try:
            models.validate_agent_name(preferred)
        except AosError as exc:
            raise RoutingRequestError(str(exc)) from None
        normalized["preferred_agent"] = preferred

    normalized["scope_preference"] = _require_enum_scalar(
        raw.get("scope_preference", DEFAULT_SCOPE_PREFERENCE),
        field="scope_preference",
        allowed=SCOPE_PREFERENCES,
    )
    normalized["surplus_policy"] = _require_enum_scalar(
        raw.get("surplus_policy", DEFAULT_SURPLUS_POLICY),
        field="surplus_policy",
        allowed=SURPLUS_POLICIES,
    )
    normalized["max_candidates"] = _require_bounded_int(
        raw.get("max_candidates", DEFAULT_MAX_CANDIDATES),
        field="max_candidates",
        minimum=1,
        maximum=_MAX_MAX_CANDIDATES,
    )
    include_diagnostics = raw.get("include_diagnostics", DEFAULT_INCLUDE_DIAGNOSTICS)
    if not isinstance(include_diagnostics, bool):
        raise RoutingRequestError("include_diagnostics must be a boolean.")
    normalized["include_diagnostics"] = include_diagnostics

    return normalized


def canonicalize_request(normalized: dict) -> bytes:
    """The exact canonical bytes a later plan stores/hashes, reusing U-X1's
    serializer rather than a second canonicalization implementation."""
    return protocols.serialize_canonical(normalized)


def request_digest(normalized: dict) -> str:
    """Lowercase 64-hex sha256 over `canonicalize_request(normalized)`
    (`request_sha256`)."""
    return hashlib.sha256(canonicalize_request(normalized)).hexdigest()


# ---------------------------------------------------------------------------
# Eligibility (§7). Pure: every fact below is an explicit caller-supplied
# value. No database access, no clock read, no mutation of either argument.

def _declared_coverage(
    container: dict, key: str, requested, *, vocabulary: tuple[str, ...] | None = None
):
    """Whether `container[key]` (an array-shaped passport declaration) covers
    every item in `requested`.

    Returns `(status, declared, missing)`:
    - `status` is `"malformed"` (impossible type/shape), `"unknown"` (a
      syntactically valid value outside `vocabulary`, only when one is
      given) or `"ok"`;
    - `declared` is whether `key` is present in `container` at all;
    - `missing` is the requested items not covered — meaningful only when
      `status == "ok"`.

    Absence is a normal, valid outcome (`declared=False`, everything
    requested counts as missing) — never malformed or unknown; this is what
    lets an absent optional passport declaration fall straight through to a
    `missing_*`/`_mismatch` code instead of an unresolved one.
    """
    if key not in container:
        return "ok", False, list(requested)
    value = container[key]
    if not isinstance(value, list) or not all(
        isinstance(item, str) for item in value
    ):
        return "malformed", True, []
    if vocabulary is not None and any(item not in vocabulary for item in value):
        return "unknown", True, []
    declared_set = set(value)
    missing = [item for item in requested if item not in declared_set]
    return "ok", True, missing


#: Every routing-relevant passport declaration this build reasons about, and how
#: it is structurally closed. Array-shaped declarations that carry no closed
#: vocabulary (task/capability/skill/tool requirements are pattern-bound, open
#: strings at the passport layer) map to `None`; `data_classifications` is
#: vocabulary-closed. `autonomy`, `evidence_expectations` and
#: `model_requirements` are shaped differently and are validated explicitly
#: below. This is the closed set §7 permits — no arbitrary passport prose.
_ROUTING_ARRAY_DECLARATIONS = (
    ("task_families", None),
    ("capabilities", None),
    ("skill_requirements", None),
    ("tool_requirements", None),
    ("data_classifications", models.MEMORY_SENSITIVITIES),
)


def _declaration_structure_defects(document: dict) -> set[str]:
    """Structural verdict over EVERY routing-relevant declaration *present* in a
    parsed passport document, independent of what this request constrains.

    Returns a subset of ``{"malformed_declaration", "unknown_declaration_value"}``
    — the same two codes the request-specific gates raise — so a dimension the
    request never touches is judged by the identical closed rules as one it
    does. An absent declaration contributes nothing: absence is a normal, valid
    outcome (a `missing_*`/`_mismatch` path, never an unresolved one), so this
    only inspects keys actually present. It reuses `_declared_coverage`'s closed
    list/vocabulary checks and never reads a raw declaration value into its
    result — only the two closed codes escape. Pure: no I/O, no mutation.
    """
    defects: set[str] = set()

    def _absorb(status: str) -> None:
        if status == "malformed":
            defects.add("malformed_declaration")
        elif status == "unknown":
            defects.add("unknown_declaration_value")

    for key, vocabulary in _ROUTING_ARRAY_DECLARATIONS:
        status, _, _ = _declared_coverage(document, key, (), vocabulary=vocabulary)
        _absorb(status)

    if "autonomy" in document:
        autonomy_value = document["autonomy"]
        if not isinstance(autonomy_value, str):
            defects.add("malformed_declaration")
        elif autonomy_value not in models.AGENT_AUTONOMY_LEVELS:
            defects.add("unknown_declaration_value")

    if "evidence_expectations" in document:
        expectations = document["evidence_expectations"]
        if not isinstance(expectations, dict):
            defects.add("malformed_declaration")
        else:
            status, _, _ = _declared_coverage(
                expectations, "evidence_kinds", (), vocabulary=models.EVIDENCE_KINDS
            )
            _absorb(status)

    if "model_requirements" in document:
        model_reqs = document["model_requirements"]
        if not isinstance(model_reqs, dict):
            defects.add("malformed_declaration")
        else:
            if "min_context_tokens" in model_reqs:
                value = model_reqs["min_context_tokens"]
                if not isinstance(value, int) or isinstance(value, bool):
                    defects.add("malformed_declaration")
            status, _, _ = _declared_coverage(
                model_reqs, "modalities", (), vocabulary=protocols.AGENT_MODALITIES
            )
            _absorb(status)

    return defects


@dataclass(frozen=True)
class CandidateSnapshot:
    """One agent identity's explicit, caller-supplied eligibility facts.

    Every field is a value the caller already read — a later,
    database-owning routing-plan layer reads `agents`/`agent_passports` and
    passes the results here; this module never opens a connection. A
    corrupted or synthetic snapshot (a mismatched row, a non-text document)
    is exactly as evaluable as a real one — the malformed/unknown/BLOB-like
    tests build one directly.
    """

    agent: Agent
    identity_integrity: str
    history_problems: tuple[str, ...] = ()
    current_passport: AgentPassport | None = None
    project_slug: str | None = None
    catalog_upgrade_available: bool = False


@dataclass(frozen=True)
class EligibilityResult:
    """One candidate's closed verdict (§7).

    A pure value object: callers own the returned instance and may read,
    project or mutate its `diagnostics` freely — every field is freshly built
    per call and aliases nothing the caller passed in, so a later evaluation
    is never affected.

    `reasons`/`warnings` are already in `models.ROUTING_REASON_CODES`
    canonical order and carry every applicable code, never truncated —
    `render_reason_summary` is the bounded text-display helper.
    `diagnostics` is a bounded, privacy-safe, JSON-compatible dict: closed
    field names mapping to bounded JSON scalars (str, int, bool, None) or
    bounded nested dicts of the same — closed reason codes, bounded counts,
    booleans, the lifecycle enum and the passport version integer only, never
    a requested/declared string, a passport body fragment, a path or prose. It
    contains no `MappingProxyType`, set, bytes, exception, sqlite row, `Agent`,
    `AgentPassport` or document fragment, so `json.dumps(result.diagnostics)`
    — and any projection built from these fields — serializes directly.
    """

    agent_name: str
    verdict: str
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    diagnostics: dict


def render_reason_summary(codes) -> str:
    """A bounded, human-readable reason-code line: at most
    `models.ROUTING_REASON_DISPLAY_LIMIT` (8) codes, `(+N more)` beyond
    that. Display-only — `EligibilityResult.reasons`/`.warnings` (and any
    `--json` projection of them) always carry every stored code."""
    codes = list(codes)
    limit = models.ROUTING_REASON_DISPLAY_LIMIT
    shown = codes[:limit]
    remaining = len(codes) - len(shown)
    text = ", ".join(shown)
    if remaining > 0:
        text = f"{text} (+{remaining} more)" if text else f"(+{remaining} more)"
    return text


def evaluate_candidate(
    request: dict, candidate: CandidateSnapshot, *, now: str | None = None
) -> EligibilityResult:
    """One candidate's verdict against one normalized request (§7).

    Pure: no SQL, no transaction, no event, no clock read (`now` is an
    explicit, optional comparison instant consulted only for
    `passport_expired`), no mutation of `request` or `candidate`. Evaluates
    every applicable dimension independently and records every applicable
    reason code; the resulting set's precedence — any `hard_ineligible` ⇒
    `excluded`, else any `unresolved` ⇒ `unresolved`, else `eligible` —
    decides the verdict, never the other way round. Implements no candidate
    ordering.
    """
    agent = candidate.agent
    hard: set[str] = set()
    unresolved: set[str] = set()
    warning_codes: set[str] = set()
    diagnostics: dict = {
        "lifecycle": agent.lifecycle,
        "passport_version": agent.current_passport_version,
    }

    if candidate.identity_integrity != "ok":
        hard.add("identity_tampered")
    if candidate.history_problems:
        hard.add("passport_history_tampered")

    if agent.lifecycle == "draft":
        hard.add("draft_only")
    elif agent.lifecycle == "suspended":
        hard.add("suspended")
    elif agent.lifecycle == "archived":
        hard.add("archived")
    elif agent.lifecycle == "revoked":
        hard.add("revoked")

    has_passport = agent.current_passport_version is not None
    document: dict | None = None
    if has_passport:
        passport = candidate.current_passport
        if passport is None or not isinstance(passport.document, str):
            unresolved.add("malformed_declaration")
        else:
            try:
                document = protocols.parse_canonical(
                    passport.document.encode("utf-8")
                )
            except (protocols.ProtocolError, UnicodeError):
                unresolved.add("malformed_declaration")
    elif agent.origin == "legacy":
        hard.add("legacy_without_passport")
    elif agent.lifecycle == "active":
        hard.add("no_current_published_passport")

    requested_project = request.get("project")
    if (
        requested_project is not None
        and agent.scope == "project"
        and candidate.project_slug != requested_project
    ):
        hard.add("project_mismatch")

    required_scope = request.get("required_scope")
    if required_scope is not None and agent.scope != required_scope:
        hard.add("scope_mismatch")

    required_agent_class = request.get("required_agent_class")
    if required_agent_class is not None and agent.agent_class != required_agent_class:
        hard.add("agent_class_mismatch")

    if document is not None:
        # Global structural validation (§7): every routing-relevant declaration
        # present in the passport is judged for structural validity BEFORE any
        # request-specific gate, regardless of whether this request constrains
        # that dimension. An impossible type/shape or an out-of-vocabulary value
        # makes the candidate unresolved on its own — unless a hard-ineligible
        # reason also applies, in which case precedence keeps the verdict
        # excluded while both codes survive in canonical order.
        unresolved |= _declaration_structure_defects(document)

        required_classification = request.get("required_data_classification")
        if required_classification is not None:
            status, declared, missing = _declared_coverage(
                document,
                "data_classifications",
                [required_classification],
                vocabulary=models.MEMORY_SENSITIVITIES,
            )
            if status == "malformed":
                unresolved.add("malformed_declaration")
            elif status == "unknown":
                unresolved.add("unknown_declaration_value")
            else:
                diagnostics["data_classification"] = {"declared": declared}
                if missing:
                    hard.add("data_classification_mismatch")

        required_autonomy = request.get("required_autonomy")
        if required_autonomy is not None:
            autonomy_value = document.get("autonomy")
            if "autonomy" not in document or not isinstance(autonomy_value, str):
                unresolved.add("malformed_declaration")
            elif autonomy_value not in models.AGENT_AUTONOMY_LEVELS:
                unresolved.add("unknown_declaration_value")
            elif autonomy_value not in required_autonomy:
                hard.add("autonomy_mismatch")

        for req_key, doc_key, code in (
            ("task_families", "task_families", "missing_task_family"),
            ("capabilities", "capabilities", "missing_capability"),
            ("skills", "skill_requirements", "missing_skill_declaration"),
            ("tools", "tool_requirements", "missing_tool_declaration"),
        ):
            requested = request.get(req_key)
            if requested is None:
                continue
            status, declared, missing = _declared_coverage(
                document, doc_key, requested
            )
            if status == "malformed":
                unresolved.add("malformed_declaration")
            else:
                diagnostics[req_key] = {
                    "declared": declared,
                    "requested_count": len(requested),
                    "missing_count": len(missing),
                }
                if missing:
                    hard.add(code)

        requested_evidence = request.get("evidence_kinds")
        if requested_evidence is not None:
            expectations_present = "evidence_expectations" in document
            expectations_raw = document.get("evidence_expectations")
            if expectations_present and not isinstance(expectations_raw, dict):
                unresolved.add("malformed_declaration")
            else:
                expectations = (
                    expectations_raw if isinstance(expectations_raw, dict) else {}
                )
                status, declared, missing = _declared_coverage(
                    expectations,
                    "evidence_kinds",
                    requested_evidence,
                    vocabulary=models.EVIDENCE_KINDS,
                )
                if status == "malformed":
                    unresolved.add("malformed_declaration")
                elif status == "unknown":
                    unresolved.add("unknown_declaration_value")
                else:
                    diagnostics["evidence_kinds"] = {
                        "declared": declared,
                        "requested_count": len(requested_evidence),
                        "missing_count": len(missing),
                    }
                    if missing:
                        hard.add("missing_evidence_kind")

        requested_model = request.get("model_capabilities")
        if requested_model is not None:
            model_declared = "model_requirements" in document
            model_reqs_raw = document.get("model_requirements")
            if model_declared and not isinstance(model_reqs_raw, dict):
                unresolved.add("malformed_declaration")
            else:
                model_reqs = (
                    model_reqs_raw if isinstance(model_reqs_raw, dict) else {}
                )
                sub_requested = 0
                sub_missing = 0
                bad = False

                if "min_context_tokens" in requested_model:
                    sub_requested += 1
                    if "min_context_tokens" not in model_reqs:
                        sub_missing += 1
                    else:
                        value = model_reqs["min_context_tokens"]
                        if not isinstance(value, int) or isinstance(value, bool):
                            unresolved.add("malformed_declaration")
                            bad = True
                        elif value < requested_model["min_context_tokens"]:
                            sub_missing += 1

                if "modalities" in requested_model:
                    sub_requested += 1
                    status, _, missing = _declared_coverage(
                        model_reqs,
                        "modalities",
                        requested_model["modalities"],
                        vocabulary=protocols.AGENT_MODALITIES,
                    )
                    if status == "malformed":
                        unresolved.add("malformed_declaration")
                        bad = True
                    elif status == "unknown":
                        unresolved.add("unknown_declaration_value")
                        bad = True
                    elif missing:
                        sub_missing += 1

                if not bad:
                    diagnostics["model_capabilities"] = {
                        "declared": model_declared,
                        "requested_count": sub_requested,
                        "missing_count": sub_missing,
                    }
                    if sub_missing:
                        hard.add("missing_model_capability")

        if now is not None:
            expires_at = document.get("expires_at")
            if isinstance(expires_at, str) and expires_at < now:
                warning_codes.add("passport_expired")

    if candidate.catalog_upgrade_available:
        warning_codes.add("catalog_upgrade_available")

    if hard:
        verdict = "excluded"
    elif unresolved:
        verdict = "unresolved"
    else:
        verdict = "eligible"

    preference: set[str] = set()
    preferred_agent = request.get("preferred_agent")
    if (
        verdict == "eligible"
        and preferred_agent is not None
        and agent.name != preferred_agent
    ):
        preference.add("preferred_agent_mismatch")

    reason_set = hard | unresolved | preference
    reasons = tuple(code for code in models.ROUTING_REASON_CODES if code in reason_set)
    warnings = tuple(
        code for code in models.ROUTING_REASON_CODES if code in warning_codes
    )

    return EligibilityResult(
        agent_name=agent.name,
        verdict=verdict,
        reasons=reasons,
        warnings=warnings,
        diagnostics=diagnostics,
    )


# ===========================================================================
# Wave 3 — deterministic ordering, plan persistence, reads, verification and
# derived staleness. From here down the module owns a database connection and
# a single transaction boundary; the functions above stay pure.
# ===========================================================================

#: Record-hash payload schemas — each names itself, house style (§11/§12.2).
PLAN_RECORD_SCHEMA = "aos.routing-plan/v1"
CANDIDATE_RECORD_SCHEMA = "aos.routing-candidate/v1"

#: The audit event this unit emits: exactly one, on successful plan creation.
ROUTING_PLAN_ENTITY = "routing_plan"
ROUTING_PLAN_ACTION_CREATE = "create"

#: The frozen event payload allowlist (§19), the catalog.EVENT_PAYLOAD_KEYS
#: idiom. Only bounded, safe metadata: ids, a scope enum, the pinned algorithm
#: version, a 12-char request-digest prefix, the closed result status, and the
#: three counts. No request prose (none exists), no passport body, no reasons,
#: no ordering tuple, no full hash. Secret metadata keys (secret_warning,
#: secret_fields, secret_patterns) may also appear, exactly as on every event.
ROUTING_PLAN_EVENT_KEYS = (
    "plan",
    "task",
    "scope",
    "algorithm_version",
    "request_sha256_prefix",
    "result_status",
    "eligible_count",
    "excluded_count",
    "unresolved_count",
    "supersedes",
)

#: Derived plan-staleness reason codes (§10). Closed, read-time only, never
#: stored, never a clock reading, never a hash value. One code per §10
#: condition over any *eligible* candidate row; `superseded` (a successor
#: exists) is the separate derived fact, kept distinct from pin/reference
#: drift exactly as the contract's asymmetry requires (§10, D-v0.4.27).
ROUTING_STALENESS_REASONS = (
    "passport_version_changed",   # (1) current_passport_version != pinned
    "lifecycle_not_active",       # (2) lifecycle != 'active'
    "integrity_broken",           # (3) agent_integrity != 'ok' or history problems
    "passport_digest_changed",    # (4) pinned passport row's digest != pin (tamper)
    "identity_changed",           # (5) recomputed identity digest != pin
)

#: The exact scanned request fields (§6E): the pattern-bound values that can
#: carry a secret shape, each under an EXISTING secretscan label. Warn-on-
#: write, never blocking; the event carries safe metadata only.
_SCANNED_REQUEST_FIELDS = (
    ("task_families", "task_family"),
    ("capabilities", "capabilities"),
)


class RoutingHashError(AosError):
    """A stored routing plan/candidate row cannot be hashed at all — a BLOB in
    a TEXT column, a non-integer pin, a NULL where the record requires text.
    Distinct from a mismatch: the row holds something no honest write could
    have produced. Carries the field name only, never the value."""


# ---------------------------------------------------------------------------
# Record-hash construction (§12.2). Text fields bind by sha256 leaf, ints
# direct, content_sha256 excluded — the M2.6 discipline, applied to routing.

def _digest(payload: dict) -> str:
    return hashlib.sha256(protocols.serialize_canonical(payload)).hexdigest()


def _req_int(value, field: str):
    if not isinstance(value, int) or isinstance(value, bool):
        raise RoutingHashError(f"routing record {field} is not an integer")
    return value


def _opt_int(value, field: str):
    return None if value is None else _req_int(value, field)


def _req_text(value, field: str):
    if not isinstance(value, str):
        raise RoutingHashError(f"routing record {field} is not text")
    return utils.sha256_text(value)


def _opt_text(value, field: str):
    return None if value is None else _req_text(value, field)


def candidate_payload(candidate: RoutingPlanCandidate) -> dict:
    """The exact `aos.routing-candidate/v1` payload (§12.2). Binds every
    non-hash column; excludes `content_sha256`."""
    return {
        "record_schema": CANDIDATE_RECORD_SCHEMA,
        "id": _req_int(candidate.id, "id"),
        "plan_id": _req_int(candidate.plan_id, "plan_id"),
        "agent_id": _req_int(candidate.agent_id, "agent_id"),
        "rank": _opt_int(candidate.rank, "rank"),
        "passport_version": _opt_int(candidate.passport_version, "passport_version"),
        "verdict_sha256": _req_text(candidate.verdict, "verdict"),
        "passport_sha256_sha256": _opt_text(candidate.passport_sha256, "passport_sha256"),
        "identity_sha256_sha256": _opt_text(candidate.identity_sha256, "identity_sha256"),
        "reasons_json_sha256": _req_text(candidate.reasons_json, "reasons_json"),
        "warnings_json_sha256": _req_text(candidate.warnings_json, "warnings_json"),
        "ordering_json_sha256": _opt_text(candidate.ordering_json, "ordering_json"),
        "created_at_sha256": _req_text(candidate.created_at, "created_at"),
    }


def candidate_digest(candidate: RoutingPlanCandidate) -> str:
    return _digest(candidate_payload(candidate))


def plan_payload(plan: RoutingPlan, candidate_chain: list[str]) -> dict:
    """The exact `aos.routing-plan/v1` payload (§12.2). Binds every non-hash
    column plus the ordered chain of RECOMPUTED candidate digests; excludes
    `content_sha256`."""
    return {
        "record_schema": PLAN_RECORD_SCHEMA,
        "id": _req_int(plan.id, "id"),
        "task_id": _opt_int(plan.task_id, "task_id"),
        "project_id": _opt_int(plan.project_id, "project_id"),
        "eligible_count": _req_int(plan.eligible_count, "eligible_count"),
        "unresolved_count": _req_int(plan.unresolved_count, "unresolved_count"),
        "excluded_count": _req_int(plan.excluded_count, "excluded_count"),
        "supersedes_id": _opt_int(plan.supersedes_id, "supersedes_id"),
        "scope_sha256": _req_text(plan.scope, "scope"),
        "actor_sha256": _req_text(plan.actor, "actor"),
        "request_schema_sha256": _req_text(plan.request_schema, "request_schema"),
        "algorithm_version_sha256": _req_text(plan.algorithm_version, "algorithm_version"),
        "request_document_sha256": _req_text(plan.request_document, "request_document"),
        "request_sha256_sha256": _req_text(plan.request_sha256, "request_sha256"),
        "result_status_sha256": _req_text(plan.result_status, "result_status"),
        "created_at_sha256": _req_text(plan.created_at, "created_at"),
        "candidate_chain": list(candidate_chain),
    }


def plan_digest(plan: RoutingPlan, candidate_chain: list[str]) -> str:
    return _digest(plan_payload(plan, candidate_chain))


# ---------------------------------------------------------------------------
# Deterministic ordering (§8). The exact lexicographic tuple over eligible
# candidates only: no weights, no scores, no floating point.

def _surplus(document: dict, key: str, requested) -> int:
    """T3-T6 component: `len(declared) - len(matched required)`. For an
    eligible candidate the gate has already proven the declaration covers
    every requested item, so matched == len(requested). Request dimension
    absent ⇒ 0; declaration absent (impossible for an eligible candidate on a
    requested dimension) ⇒ 0."""
    if not requested:
        return 0
    declared = document.get(key)
    if not isinstance(declared, list):
        return 0
    return len(declared) - len(requested)


def ordering_components(
    request: dict, agent: Agent, agent_project_slug: str | None, document: dict
) -> list[int]:
    """The `[t1, t2, t3, t4, t5, t6]` array stored in `ordering_json` (§8). T7
    (canonical name) is implicit in the row's agent reference. Independently
    recomputable from the stored request and the pinned passport facts alone —
    it reads no row id, timestamp, insertion order, owner, protection, origin,
    catalog membership, maturity, usage, price, clock or randomness."""
    preferred = request.get("preferred_agent")
    t1 = 1 if (preferred is not None and agent.name == preferred) else 0

    scope_preference = request.get("scope_preference", DEFAULT_SCOPE_PREFERENCE)
    requested_project = request.get("project")
    if scope_preference == "none" or requested_project is None:
        t2 = 0
    else:
        t2 = (
            1
            if (agent.scope == "project" and agent_project_slug == requested_project)
            else 0
        )

    if request.get("surplus_policy", DEFAULT_SURPLUS_POLICY) == "ignore":
        t3 = t4 = t5 = t6 = 0
    else:
        t3 = _surplus(document, "task_families", request.get("task_families"))
        t4 = _surplus(document, "capabilities", request.get("capabilities"))
        t5 = _surplus(document, "skill_requirements", request.get("skills"))
        t6 = _surplus(document, "tool_requirements", request.get("tools"))
    return [t1, t2, t3, t4, t5, t6]


def _order_key(components: list[int], name: str):
    """The frozen lexicographic key: T1 desc, T2 desc, T3-T6 asc, T7 (name)
    asc. T7 is the final byte-level tie-break over a UNIQUE NOT NULL column,
    so the order is total and unique — no two candidates compare equal."""
    t1, t2, t3, t4, t5, t6 = components
    return (-t1, -t2, t3, t4, t5, t6, name)


# ---------------------------------------------------------------------------
# Database enumeration and snapshot assembly (§ database_enumeration). Reads
# every governed identity deterministically and assembles one explicit
# CandidateSnapshot per agent from existing passport/catalog helpers.

def _catalog_index() -> dict:
    """Every shipped catalog entry, by agent name — the only catalog fact
    routing consults. A broken catalog contributes no advisory rather than
    failing an evaluation; nothing is ever installed."""
    from . import catalog

    try:
        return {entry.agent: entry for entry in catalog.catalog().entries}
    except AosError:
        return {}


def _catalog_upgrade_available(conn, agent: Agent, catalog_index: dict) -> bool:
    """The derived catalog-upgrade advisory (§7 code 24): the agent is
    catalog-managed and `catalog.installed_state` says `upgradable`. Reads
    only; changes nothing about the catalog."""
    entry = catalog_index.get(agent.name)
    if entry is None:
        return False
    from . import catalog

    try:
        return catalog.installed_state(conn, entry)["state"] == "upgradable"
    except AosError:
        return False


def _build_snapshot(conn, agent: Agent, catalog_index: dict) -> CandidateSnapshot:
    """Assemble one candidate's explicit eligibility facts from the exact
    in-transaction rows, using the existing passport integrity/history/current-
    passport helpers and project context."""
    current_passport = None
    if agent.current_passport_version is not None:
        current_passport = passports.get_passport(
            conn, agent.id, agent.current_passport_version
        )
    return CandidateSnapshot(
        agent=agent,
        identity_integrity=passports.agent_integrity(agent),
        history_problems=tuple(passports.history_problems(conn, agent)),
        current_passport=current_passport,
        project_slug=passports._project_slug(conn, agent.project_id),
        catalog_upgrade_available=_catalog_upgrade_available(
            conn, agent, catalog_index
        ),
    )


# ---------------------------------------------------------------------------
# Request resolution (§ request_resolution). Authoritative task/project/
# preferred-agent resolution, run inside the plan transaction.

def _resolve_context(conn, request: dict) -> tuple[dict, int | None, int | None, str]:
    """Resolve `task`/`project` references and derive the plan's scope.

    Refuses (before any write) an unresolved task or project and a
    task/explicit-project disagreement. Returns `(request, task_id,
    project_id, scope)`; when the task carries a project and none was given,
    the returned request is re-normalized with the derived project so the
    stored request document and the plan's `project_id` agree.
    """
    task_id = request.get("task")
    task_project_slug: str | None = None
    if task_id is not None:
        task = ops.get_task(conn, task_id)  # raises AosError (exit 1) if absent
        if task.project_id is not None:
            project = ops.get_project(conn, task.project_id)
            task_project_slug = project.slug if project else None

    explicit_slug = request.get("project")
    if (
        task_project_slug is not None
        and explicit_slug is not None
        and explicit_slug != task_project_slug
    ):
        raise AosError(
            f"--task's project '{task_project_slug}' and --project "
            f"'{explicit_slug}' disagree; pass one, or the same slug. "
            "Nothing was changed."
        )

    final_slug = explicit_slug if explicit_slug is not None else task_project_slug
    project_id: int | None = None
    scope = "global"
    if final_slug is not None:
        project = ops.get_project_by_slug(conn, final_slug)
        if project is None:
            raise AosError(
                f"No project '{final_slug}'. Nothing was changed. "
                "Run: python aos.py project list"
            )
        project_id = project.id
        scope = "project"

    if final_slug is not None and request.get("project") != final_slug:
        request = validate_request({**request, "project": final_slug})
    return request, task_id, project_id, scope


def _resolve_preferred_agent(conn, request: dict) -> None:
    """Preferred-agent existence (§6C/§7). An absent name is a request-level
    refusal (`agent_absent`), an uninstalled catalog name another
    (`catalog_not_installed`) — both raise before any row is written, both
    creating zero rows and zero events, and neither installs anything."""
    name = request.get("preferred_agent")
    if name is None or passports.get_agent(conn, name) is not None:
        return
    from . import catalog

    try:
        entry = catalog.catalog().get(name)
    except AosError:
        entry = None
    if entry is not None:
        raise AosError(
            f"Preferred agent '{name}' is a catalog entry that is not "
            "installed in this workspace (catalog_not_installed). Install it "
            f"first: python aos.py agent catalog install {name} — routing "
            "never installs. Nothing was changed."
        )
    raise AosError(
        f"No agent '{name}' (preferred_agent; agent_absent). Nothing was "
        "changed. Run: python aos.py agent list"
    )


def _resolve_supersedes(conn, supersedes_id: int) -> None:
    """The supersedes target re-read under BEGIN IMMEDIATE (§10): it must
    exist and have no successor yet. `UNIQUE(supersedes_id)` is the storage
    backstop for a race; this is the friendly, named refusal."""
    row = conn.execute(
        "SELECT id FROM routing_plans WHERE id = ?", (supersedes_id,)
    ).fetchone()
    if row is None:
        raise AosError(
            f"No routing plan {ids.render_id('routing_plan', supersedes_id)} "
            "to supersede. Nothing was changed. Run: python aos.py agent "
            "route list"
        )
    successor = conn.execute(
        "SELECT id FROM routing_plans WHERE supersedes_id = ?", (supersedes_id,)
    ).fetchone()
    if successor is not None:
        raise AosError(
            f"Routing plan {ids.render_id('routing_plan', supersedes_id)} is "
            f"already superseded by {ids.render_id('routing_plan', successor['id'])}. "
            "Nothing was changed."
        )


# ---------------------------------------------------------------------------
# Plan creation (§9, §12.2). One function owns the whole write.

def _reasons_text(codes) -> str:
    return protocols.serialize_canonical(list(codes)).decode("utf-8")


def _evaluate_registry(conn, request: dict, *, now: str) -> list[dict]:
    """Evaluate every governed identity in deterministic (name) order and,
    for each eligible candidate, recompute its pins and ordering tuple from
    the exact in-transaction rows. Returns one dict per agent in name order —
    the canonical emission order candidate ids will follow."""
    catalog_index = _catalog_index()
    records: list[dict] = []
    for row in conn.execute("SELECT * FROM agents ORDER BY name").fetchall():
        agent = Agent.from_row(row)
        snapshot = _build_snapshot(conn, agent, catalog_index)
        result = evaluate_candidate(request, snapshot, now=now)
        record: dict = {
            "agent_id": agent.id,
            "name": agent.name,
            "verdict": result.verdict,
            "reasons_json": _reasons_text(result.reasons),
            "warnings_json": _reasons_text(result.warnings),
            "passport_version": None,
            "passport_sha256": None,
            "identity_sha256": None,
            "ordering_json": None,
            "ordering": None,
            "rank": None,
        }
        if result.verdict == "eligible":
            passport = snapshot.current_passport
            document = protocols.parse_canonical(passport.document.encode("utf-8"))
            components = ordering_components(
                request, agent, snapshot.project_slug, document
            )
            record["passport_version"] = agent.current_passport_version
            record["passport_sha256"] = passports.document_digest(passport.document)
            record["identity_sha256"] = passports.agent_identity_digest(agent)
            record["ordering"] = components
            record["ordering_json"] = protocols.serialize_canonical(
                components
            ).decode("utf-8")
        records.append(record)

    eligible = [r for r in records if r["verdict"] == "eligible"]
    for rank, record in enumerate(
        sorted(eligible, key=lambda r: _order_key(r["ordering"], r["name"])), start=1
    ):
        record["rank"] = rank
    return records


def _result_status(eligible_count: int, unresolved_count: int) -> str:
    """Derived from `(eligible_count, unresolved_count)` alone (§9/§11);
    `excluded_count` never participates."""
    if eligible_count > 0:
        return "resolved"
    if unresolved_count > 0:
        return "unresolved"
    return "no_eligible_candidates"


def create_plan(
    conn, request: dict, *, supersedes_id: int | None = None, actor: str = ops.ACTOR_HUMAN
) -> int:
    """Create one governed routing plan and its candidate rows (§12.2).

    `request` is an already validated/normalized document (`validate_request`
    ran outside the transaction — purely syntactic). This function owns the
    ONE `db.transaction` boundary: it acquires `BEGIN IMMEDIATE`, re-reads
    task/project/preferred-agent/supersedes/agent-count authoritatively,
    evaluates and orders entirely in-transaction, inserts the plan and every
    candidate row with `content_sha256=_PENDING_HASH`, finalizes each
    candidate hash immediately after its INSERT, builds the chain from the
    recomputed candidate digests ordered by id, finalizes the plan hash over
    that chain, and emits exactly one `routing_plan`/`create` event. Any
    exception rolls the whole boundary back — no rows, no event, no
    `_PENDING_HASH` survivor. Returns the new plan id.
    """
    now = utils.utc_now_iso()
    warning: str | None = None
    with db.transaction(conn):
        conn.execute("BEGIN IMMEDIATE")

        request, task_id, project_id, scope = _resolve_context(conn, request)
        _resolve_preferred_agent(conn, request)

        agent_count = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        if agent_count > models.MAX_ROUTING_EVALUATED_AGENTS:
            raise AosError(
                f"This workspace has {agent_count} agents; routing evaluates "
                f"at most {models.MAX_ROUTING_EVALUATED_AGENTS} to keep the "
                "explanation set bounded (nothing was truncated, nothing was "
                "changed). Narrow the registry before planning."
            )
        if supersedes_id is not None:
            _resolve_supersedes(conn, supersedes_id)

        request_document = protocols.serialize_canonical(request).decode("utf-8")
        request_sha256 = hashlib.sha256(
            request_document.encode("utf-8")
        ).hexdigest()

        records = _evaluate_registry(conn, request, now=now)
        eligible_count = sum(1 for r in records if r["verdict"] == "eligible")
        unresolved_count = sum(1 for r in records if r["verdict"] == "unresolved")
        excluded_count = sum(1 for r in records if r["verdict"] == "excluded")
        result_status = _result_status(eligible_count, unresolved_count)

        secret_meta, warning = ops._scan_trusted_write(
            "routing_plan", _request_scan_fields(request)
        )

        plan_id = conn.execute(
            "INSERT INTO routing_plans (task_id, project_id, scope, actor, "
            "request_schema, algorithm_version, request_document, "
            "request_sha256, result_status, eligible_count, unresolved_count, "
            "excluded_count, supersedes_id, created_at, content_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task_id,
                project_id,
                scope,
                actor,
                request["request_schema"],
                request["algorithm_version"],
                request_document,
                request_sha256,
                result_status,
                eligible_count,
                unresolved_count,
                excluded_count,
                supersedes_id,
                now,
                _PENDING_HASH,
            ),
        ).lastrowid

        for record in records:
            cid = conn.execute(
                "INSERT INTO routing_plan_candidates (plan_id, agent_id, "
                "verdict, rank, passport_version, passport_sha256, "
                "identity_sha256, reasons_json, warnings_json, ordering_json, "
                "created_at, content_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    plan_id,
                    record["agent_id"],
                    record["verdict"],
                    record["rank"],
                    record["passport_version"],
                    record["passport_sha256"],
                    record["identity_sha256"],
                    record["reasons_json"],
                    record["warnings_json"],
                    record["ordering_json"],
                    now,
                    _PENDING_HASH,
                ),
            ).lastrowid
            digest = candidate_digest(_get_candidate(conn, cid))
            conn.execute(
                "UPDATE routing_plan_candidates SET content_sha256 = ? WHERE id = ?",
                (digest, cid),
            )

        chain = [
            candidate_digest(candidate)
            for candidate in get_candidates(conn, plan_id)
        ]
        plan_row = get_plan(conn, plan_id)
        conn.execute(
            "UPDATE routing_plans SET content_sha256 = ? WHERE id = ?",
            (plan_digest(plan_row, chain), plan_id),
        )

        payload = {
            "plan": ids.render_id("routing_plan", plan_id),
            "task": ids.render_id("task", task_id) if task_id is not None else None,
            "scope": scope,
            "algorithm_version": request["algorithm_version"],
            "request_sha256_prefix": models.hash_prefix(request_sha256),
            "result_status": result_status,
            "eligible_count": eligible_count,
            "excluded_count": excluded_count,
            "unresolved_count": unresolved_count,
            "supersedes": (
                ids.render_id("routing_plan", supersedes_id)
                if supersedes_id is not None
                else None
            ),
        }
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=actor,
            entity=ROUTING_PLAN_ENTITY,
            entity_id=plan_id,
            action=ROUTING_PLAN_ACTION_CREATE,
            payload=payload,
        )

    ops._warn_secret(warning)
    return plan_id


def _request_scan_fields(request: dict) -> list[tuple[str, str | None]]:
    """The pattern-bound request values, joined per field, under existing
    secretscan labels (§6E). `preferred_agent`/`project` reuse the `agent`/
    `slug` labels the passport writers already use."""
    fields: list[tuple[str, str | None]] = []
    for key, label in _SCANNED_REQUEST_FIELDS:
        value = request.get(key)
        if isinstance(value, (list, tuple)):
            joined = "\n".join(str(item) for item in value) or None
            fields.append((label, joined))
    preferred = request.get("preferred_agent")
    if isinstance(preferred, str):
        fields.append(("agent", preferred))
    project = request.get("project")
    if isinstance(project, str):
        fields.append(("slug", project))
    return fields


# ---------------------------------------------------------------------------
# Reads (§17). Never write, rehash, repair or emit.

def get_plan(conn, plan_id: int) -> RoutingPlan | None:
    row = conn.execute(
        "SELECT * FROM routing_plans WHERE id = ?", (plan_id,)
    ).fetchone()
    return RoutingPlan.from_row(row) if row else None


def _get_candidate(conn, candidate_id: int) -> RoutingPlanCandidate:
    row = conn.execute(
        "SELECT * FROM routing_plan_candidates WHERE id = ?", (candidate_id,)
    ).fetchone()
    return RoutingPlanCandidate.from_row(row)


def get_candidates(conn, plan_id: int) -> list[RoutingPlanCandidate]:
    """Every candidate row of a plan, ordered by id ascending — the canonical
    chain order (§12.2)."""
    return [
        RoutingPlanCandidate.from_row(row)
        for row in conn.execute(
            "SELECT * FROM routing_plan_candidates WHERE plan_id = ? ORDER BY id",
            (plan_id,),
        ).fetchall()
    ]


def _successor_id(conn, plan_id: int) -> int | None:
    row = conn.execute(
        "SELECT id FROM routing_plans WHERE supersedes_id = ?", (plan_id,)
    ).fetchone()
    return row["id"] if row else None


@dataclass(frozen=True)
class PlanStaleness:
    """A derived, read-time staleness verdict (§10). Never stored, never a
    clock reading. `stale`/`superseded` are independent facts; `reasons` are
    closed codes from `ROUTING_STALENESS_REASONS` in canonical order; `agent`
    names the first (top-ranked) stale eligible candidate, for the refusal
    message. No hash value ever appears."""

    stale: bool
    reasons: tuple[str, ...]
    agent: str | None
    superseded: bool
    successor: str | None


def _candidate_stale_reasons(conn, candidate: RoutingPlanCandidate) -> set[str]:
    """The §10 conditions this one eligible candidate satisfies, as closed
    codes. Pure reads; never raises on a damaged row — a digest that cannot
    be recomputed reads as changed."""
    reasons: set[str] = set()
    agent_row = conn.execute(
        "SELECT * FROM agents WHERE id = ?", (candidate.agent_id,)
    ).fetchone()
    if agent_row is None:
        return set(ROUTING_STALENESS_REASONS)
    agent = Agent.from_row(agent_row)

    if agent.current_passport_version != candidate.passport_version:
        reasons.add("passport_version_changed")
    if agent.lifecycle != models.AGENT_LIFECYCLE_ACTIVE:
        reasons.add("lifecycle_not_active")
    if passports.agent_integrity(agent) != "ok" or passports.history_problems(
        conn, agent
    ):
        reasons.add("integrity_broken")

    passport = None
    if candidate.passport_version is not None:
        passport = passports.get_passport(
            conn, agent.id, candidate.passport_version
        )
    try:
        pinned_digest = (
            passports.document_digest(passport.document)
            if passport is not None
            else None
        )
    except (passports.PassportHashError, protocols.ProtocolError):
        pinned_digest = None
    if pinned_digest != candidate.passport_sha256:
        reasons.add("passport_digest_changed")

    try:
        identity_digest = passports.agent_identity_digest(agent)
    except passports.PassportHashError:
        identity_digest = None
    if identity_digest != candidate.identity_sha256:
        reasons.add("identity_changed")
    return reasons


def plan_staleness(conn, plan: RoutingPlan) -> PlanStaleness:
    """Derive a plan's staleness and supersession from current ledger facts
    (§10). Reads only — mutates nothing, refreshes nothing, rewrites no
    history. A historically stale plan stays a valid record."""
    reasons: set[str] = set()
    first_agent: str | None = None
    eligible = [
        c
        for c in get_candidates(conn, plan.id)
        if c.verdict == "eligible"
    ]
    for candidate in sorted(eligible, key=lambda c: (c.rank if c.rank else 0)):
        candidate_reasons = _candidate_stale_reasons(conn, candidate)
        if candidate_reasons and first_agent is None:
            agent_row = conn.execute(
                "SELECT name FROM agents WHERE id = ?", (candidate.agent_id,)
            ).fetchone()
            first_agent = agent_row["name"] if agent_row else None
        reasons |= candidate_reasons

    successor = _successor_id(conn, plan.id)
    return PlanStaleness(
        stale=bool(reasons),
        reasons=tuple(r for r in ROUTING_STALENESS_REASONS if r in reasons),
        agent=first_agent,
        superseded=successor is not None,
        successor=(
            ids.render_id("routing_plan", successor) if successor is not None else None
        ),
    )


def _candidate_public(candidate: RoutingPlanCandidate) -> dict:
    """The §7 per-candidate JSON shape. `rank`, `pinned` and `ordering` are
    simultaneously non-null iff the verdict is `eligible`."""
    pinned = None
    ordering = None
    if candidate.verdict == "eligible":
        pinned = {
            "passport_version": candidate.passport_version,
            "passport_sha256": candidate.passport_sha256,
            "identity_sha256": candidate.identity_sha256,
        }
        ordering = _parse_json_list(candidate.ordering_json)
    return {
        "agent": _candidate_agent_name(candidate),
        "verdict": candidate.verdict,
        "reasons": _parse_code_list(candidate.reasons_json),
        "warnings": _parse_code_list(candidate.warnings_json),
        "rank": candidate.rank,
        "pinned": pinned,
        "ordering": ordering,
    }


def _candidate_agent_name(candidate: RoutingPlanCandidate) -> str:
    return f"agent #{candidate.agent_id}"


def _parse_json_list(text):
    """Read one of the list-valued JSON columns (`reasons_json`,
    `warnings_json`, `ordering_json`). These are stored as canonical JSON
    ARRAYS, so `protocols.parse_canonical` (which requires a top-level object)
    cannot read them; a damaged/non-array value reads as `None`."""
    if not isinstance(text, str):
        return None
    try:
        value = json.loads(text)
    except ValueError:
        return None
    return value if isinstance(value, list) else None


def _parse_code_list(text) -> list:
    value = _parse_json_list(text)
    return value if value is not None else []


def _plan_candidate_public(conn, candidate: RoutingPlanCandidate) -> dict:
    public = _candidate_public(candidate)
    row = conn.execute(
        "SELECT name FROM agents WHERE id = ?", (candidate.agent_id,)
    ).fetchone()
    if row is not None:
        public["agent"] = row["name"]
    return public


def plan_public(conn, plan: RoutingPlan) -> dict:
    """The complete `route show`/`--json` projection: the full plan plus every
    stored candidate (never capped, never diagnostics-filtered — `--json`
    always carries everything). Show-class output, so full hashes appear."""
    staleness = plan_staleness(conn, plan)
    return {
        "plan": ids.render_id("routing_plan", plan.id),
        "task": ids.render_id("task", plan.task_id) if plan.task_id else None,
        "project": passports._project_slug(conn, plan.project_id),
        "scope": plan.scope,
        "actor": plan.actor,
        "request_schema": plan.request_schema,
        "algorithm_version": plan.algorithm_version,
        "request_sha256": plan.request_sha256,
        "result_status": plan.result_status,
        "eligible_count": plan.eligible_count,
        "unresolved_count": plan.unresolved_count,
        "excluded_count": plan.excluded_count,
        "supersedes": (
            ids.render_id("routing_plan", plan.supersedes_id)
            if plan.supersedes_id
            else None
        ),
        "superseded_by": staleness.successor,
        "stale": staleness.stale,
        "staleness_reasons": list(staleness.reasons),
        "created_at": plan.created_at,
        "content_sha256": plan.content_sha256,
        "candidates": [
            _plan_candidate_public(conn, candidate)
            for candidate in get_candidates(conn, plan.id)
        ],
    }


def list_plans(conn, *, task_id: int | None = None) -> list[dict]:
    """Every plan newest-first (§17): id, created_at, result_status, counts,
    and the derived stale/superseded flags. Read-only."""
    if task_id is None:
        rows = conn.execute(
            "SELECT * FROM routing_plans ORDER BY id DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM routing_plans WHERE task_id = ? ORDER BY id DESC",
            (task_id,),
        ).fetchall()
    listing = []
    for row in rows:
        plan = RoutingPlan.from_row(row)
        staleness = plan_staleness(conn, plan)
        listing.append(
            {
                "plan": ids.render_id("routing_plan", plan.id),
                "task": (
                    ids.render_id("task", plan.task_id) if plan.task_id else None
                ),
                "scope": plan.scope,
                "result_status": plan.result_status,
                "eligible_count": plan.eligible_count,
                "unresolved_count": plan.unresolved_count,
                "excluded_count": plan.excluded_count,
                "created_at": plan.created_at,
                "stale": staleness.stale,
                "superseded": staleness.superseded,
            }
        )
    return listing


# ---------------------------------------------------------------------------
# Verification (§12.2, § reads_and_verification). Recomputes every hash from
# columns and builds the parent chain from the RECOMPUTED child digests, so a
# tampered stored child hash cannot launder itself. Reads only; closed
# verdicts; exit 0 for a stale-but-intact plan, 1 only on integrity failure.

def verify_plan(conn, plan_id: int) -> dict:
    """Verify one plan and its candidates. Returns a bounded, value-free
    report: `ok` (no integrity failure), the derived `stale`/`superseded`
    flags, and a list of closed `problems`. Never raises on a damaged row,
    never writes, never rehashes."""
    rp = ids.render_id("routing_plan", plan_id)
    problems: list[str] = []
    plan_row = conn.execute(
        "SELECT * FROM routing_plans WHERE id = ?", (plan_id,)
    ).fetchone()
    if plan_row is None:
        return {"plan": rp, "ok": False, "stale": False, "superseded": False,
                "problems": [f"{rp}: not_found"]}
    try:
        plan = RoutingPlan.from_row(plan_row)
    except (TypeError, ValueError):
        return {"plan": rp, "ok": False, "stale": False, "superseded": False,
                "problems": [f"{rp}: malformed"]}

    candidates = get_candidates(conn, plan_id)
    problems.extend(_verify_request(plan, rp))
    problems.extend(_verify_candidates(conn, plan, candidates, rp))
    problems.extend(_verify_counts(plan, candidates, rp))
    problems.extend(_verify_plan_hash(plan, candidates, rp))
    problems.extend(_verify_references(conn, plan, rp))

    staleness = plan_staleness(conn, plan)
    return {
        "plan": rp,
        "ok": not problems,
        "stale": staleness.stale,
        "superseded": staleness.superseded,
        "staleness_reasons": list(staleness.reasons),
        "problems": problems,
    }


def _verify_request(plan: RoutingPlan, rp: str) -> list[str]:
    if not isinstance(plan.request_document, str):
        return [f"{rp}: request_mismatch"]
    try:
        parsed = protocols.parse_canonical(plan.request_document.encode("utf-8"))
    except protocols.ProtocolError:
        return [f"{rp}: request_mismatch"]
    if protocols.serialize_canonical(parsed).decode("utf-8") != plan.request_document:
        return [f"{rp}: request_mismatch"]
    if (
        hashlib.sha256(plan.request_document.encode("utf-8")).hexdigest()
        != plan.request_sha256
    ):
        return [f"{rp}: request_mismatch"]
    if (
        parsed.get("request_schema") != plan.request_schema
        or parsed.get("algorithm_version") != plan.algorithm_version
    ):
        return [f"{rp}: request_mismatch"]
    return []


def _verify_candidates(
    conn, plan: RoutingPlan, candidates: list[RoutingPlanCandidate], rp: str
) -> list[str]:
    problems: list[str] = []
    eligible_ranks: list[int] = []
    for candidate in candidates:
        cid = f"{rp} candidate #{candidate.id}"
        if not models.is_claim_hash(candidate.content_sha256):
            problems.append(f"{cid}: malformed")
            continue
        try:
            recomputed = candidate_digest(candidate)
        except RoutingHashError:
            problems.append(f"{cid}: unhashable")
            continue
        if recomputed != candidate.content_sha256:
            problems.append(f"{cid}: mismatch")
        for code in _parse_code_list(candidate.reasons_json) + _parse_code_list(
            candidate.warnings_json
        ):
            if code not in models.ROUTING_REASON_CODES:
                problems.append(f"{cid}: malformed")
                break
        if not _is_canonical_code_order(candidate.reasons_json) or not (
            _is_canonical_code_order(candidate.warnings_json)
        ):
            problems.append(f"{cid}: malformed")
        if candidate.verdict == "eligible":
            eligible_ranks.append(candidate.rank if candidate.rank else -1)
            problems.extend(_verify_ordering(conn, plan, candidate, cid))
    if eligible_ranks and sorted(eligible_ranks) != list(
        range(1, len(eligible_ranks) + 1)
    ):
        problems.append(f"{rp}: rank_gap")
    return problems


def _verify_ordering(
    conn, plan: RoutingPlan, candidate: RoutingPlanCandidate, cid: str
) -> list[str]:
    agent_row = conn.execute(
        "SELECT * FROM agents WHERE id = ?", (candidate.agent_id,)
    ).fetchone()
    if agent_row is None:
        return [f"{cid}: reference_invalid"]
    agent = Agent.from_row(agent_row)
    passport = passports.get_passport(conn, agent.id, candidate.passport_version)
    if passport is None:
        return [f"{cid}: reference_invalid"]
    try:
        request = protocols.parse_canonical(plan.request_document.encode("utf-8"))
        document = protocols.parse_canonical(passport.document.encode("utf-8"))
    except protocols.ProtocolError:
        return [f"{cid}: malformed"]
    expected = ordering_components(
        request, agent, passports._project_slug(conn, agent.project_id), document
    )
    stored = _parse_code_list(candidate.ordering_json)
    if stored != expected:
        return [f"{cid}: malformed"]
    return []


def _verify_counts(
    plan: RoutingPlan, candidates: list[RoutingPlanCandidate], rp: str
) -> list[str]:
    eligible = sum(1 for c in candidates if c.verdict == "eligible")
    unresolved = sum(1 for c in candidates if c.verdict == "unresolved")
    excluded = sum(1 for c in candidates if c.verdict == "excluded")
    if (
        plan.eligible_count != eligible
        or plan.unresolved_count != unresolved
        or plan.excluded_count != excluded
        or plan.result_status != _result_status(eligible, unresolved)
    ):
        return [f"{rp}: counts_incoherent"]
    return []


def _verify_plan_hash(
    plan: RoutingPlan, candidates: list[RoutingPlanCandidate], rp: str
) -> list[str]:
    if not models.is_claim_hash(plan.content_sha256):
        return [f"{rp}: malformed"]
    try:
        chain = [candidate_digest(candidate) for candidate in candidates]
        recomputed = plan_digest(plan, chain)
    except RoutingHashError:
        return [f"{rp}: unhashable"]
    if recomputed != plan.content_sha256:
        return [f"{rp}: mismatch"]
    return []


def _verify_references(conn, plan: RoutingPlan, rp: str) -> list[str]:
    problems: list[str] = []
    for candidate in get_candidates(conn, plan.id):
        if candidate.verdict != "eligible":
            continue
        cid = f"{rp} candidate #{candidate.id}"
        passport = passports.get_passport(
            conn, candidate.agent_id, candidate.passport_version
        )
        if passport is None:
            problems.append(f"{cid}: reference_invalid")
            continue
        try:
            if passports.document_digest(passport.document) != candidate.passport_sha256:
                problems.append(f"{cid}: pin_mismatch")
        except (passports.PassportHashError, protocols.ProtocolError):
            problems.append(f"{cid}: pin_mismatch")
    if plan.supersedes_id is not None:
        row = conn.execute(
            "SELECT id FROM routing_plans WHERE id = ?", (plan.supersedes_id,)
        ).fetchone()
        if row is None:
            problems.append(f"{rp}: reference_invalid")
    return problems


def _is_canonical_code_order(text: str) -> bool:
    """A stored reason/warning list is in canonical `ROUTING_REASON_CODES`
    order (and carries no duplicate/unknown code)."""
    codes = _parse_code_list(text)
    order = {code: i for i, code in enumerate(models.ROUTING_REASON_CODES)}
    seen = -1
    for code in codes:
        if code not in order or order[code] <= seen:
            return False
        seen = order[code]
    return True


# ---------------------------------------------------------------------------
# Text rendering (§7). Display-only: respects the plan's stored max_candidates
# and include_diagnostics; --json always carries everything.

def render_plan_lines(conn, plan: RoutingPlan) -> list[str]:
    """The human text for `route plan`/`route show`: a summary line, the
    ranked eligible rows (capped at the stored `max_candidates`), and — when
    the stored `include_diagnostics` is true — the excluded/unresolved rows."""
    try:
        request = protocols.parse_canonical(plan.request_document.encode("utf-8"))
    except protocols.ProtocolError:
        request = {}
    max_candidates = request.get("max_candidates", DEFAULT_MAX_CANDIDATES)
    include_diagnostics = request.get(
        "include_diagnostics", DEFAULT_INCLUDE_DIAGNOSTICS
    )
    staleness = plan_staleness(conn, plan)

    flags = []
    if staleness.stale:
        flags.append("stale")
    if staleness.superseded:
        flags.append(f"superseded by {staleness.successor}")
    suffix = f"  [{', '.join(flags)}]" if flags else ""
    lines = [
        f"{ids.render_id('routing_plan', plan.id)}  {plan.result_status}  "
        f"eligible {plan.eligible_count} · unresolved {plan.unresolved_count} · "
        f"excluded {plan.excluded_count}{suffix}"
    ]

    candidates = get_candidates(conn, plan.id)
    by_name = {
        c.agent_id: (row["name"] if row else f"agent #{c.agent_id}")
        for c in candidates
        for row in [
            conn.execute(
                "SELECT name FROM agents WHERE id = ?", (c.agent_id,)
            ).fetchone()
        ]
    }
    eligible = sorted(
        (c for c in candidates if c.verdict == "eligible"),
        key=lambda c: c.rank or 0,
    )
    for candidate in eligible[:max_candidates]:
        version = candidate.passport_version
        prefix = models.hash_prefix(candidate.passport_sha256)
        lines.append(
            f"  {candidate.rank}. {by_name[candidate.agent_id]}  v{version}  {prefix}"
        )
    if len(eligible) > max_candidates:
        lines.append(f"  … (+{len(eligible) - max_candidates} more eligible)")

    if include_diagnostics:
        for candidate in candidates:
            if candidate.verdict == "eligible":
                continue
            codes = render_reason_summary(_parse_code_list(candidate.reasons_json))
            lines.append(
                f"  - {by_name[candidate.agent_id]}  {candidate.verdict}: {codes}"
            )
    return lines
