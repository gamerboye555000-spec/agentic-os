"""U-A3 Wave 2: canonical routing-request validation and deterministic
per-agent eligibility.

Contract: agentic-os-v0.4-u-a3-routing-handoffs-contract.md §6-7.

Two independent, pure surfaces — no SQL, no transaction, no event, no
filesystem, no network, no provider call, no wall clock:

- the canonical routing REQUEST document: `validate_request` closes and
  normalizes it; `canonicalize_request` reuses U-X1's canonical JSON
  serializer (`protocols.serialize_canonical`) rather than a second
  canonicalization implementation; `request_digest` is the sha256 over
  those exact bytes (`request_sha256`, pinned on a later plan row);
- per-agent eligibility: `evaluate_candidate` takes one normalized request
  and one explicit `CandidateSnapshot` — every fact it reasons about is a
  value the caller already read — and returns a closed verdict plus reason
  and warning codes from `models.ROUTING_REASON_CODES`, in that vocabulary's
  own canonical order. It never orders candidates against each other, never
  persists anything, and never resolves whether a `task`/`project`/
  `preferred_agent` reference actually exists — those are a later,
  database-owning routing-plan layer's job (Wave 3).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from . import models, protocols
from .ids import MAX_ID
from .models import Agent, AgentPassport
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
