"""U-K1/U-T1 governed skill and tool foundations — acceptance tests.

Contract: agentic-os-v0.4-u-k1-u-t1-governed-foundations-contract.md

Everything here runs in memory: no workspace, no SQLite, no network, no
subprocess, no filesystem beyond reading this repository's own source for
the hygiene audit. That is itself part of the contract under test — the
foundation is pure validation, registries, decisions and records.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agentic_os import governance, protocols  # noqa: E402

UTC0 = "2026-07-23T00:00:00Z"
HEX0 = "0" * 64
UUID1 = "12345678-1234-1234-1234-123456789abc"


def seal(document: dict) -> dict:
    document["content_sha256"] = protocols.content_digest(document)
    return document


def tool_manifest(**overrides) -> dict:
    document = {
        "schema": "beast.tool-manifest/v1",
        "protocol_version": 1,
        "content_hash_alg": protocols.CONTENT_HASH_ALG,
        "content_sha256": HEX0,
        "created_at": UTC0,
        "issuer": "aos.test",
        "tool": "fs.read",
        "component_version": 1,
        "display_name": "Read file",
        "description": "Reads a declared input.",
        "lifecycle": "active",
        "io_contracts": {
            "input_ref": "aos.io.read-input/v1",
            "output_ref": "aos.io.read-output/v1",
        },
        "side_effect": "read_only",
        "compensation": {"strategy": "not_applicable"},
        "idempotency": "not_required",
        "cancellation": "not_supported",
        "retry": {"max_attempts": 3},
        "recovery": {"action": "none"},
        "binding": {"binding_id": "fs.read.impl", "binding_sha256": HEX0},
        "provenance": {"created_by": "human", "method": "create"},
    }
    document.update(overrides)
    return seal(document)


def mutating_tool_manifest(**overrides) -> dict:
    base = {
        "tool": "repo.write",
        "side_effect": "mutating",
        "compensation": {"strategy": "none"},
        "idempotency": "required_key",
        "retry": {"max_attempts": 1},
        "binding": {"binding_id": "repo.write.impl", "binding_sha256": HEX0},
    }
    base.update(overrides)
    return tool_manifest(**base)


def skill_manifest(**overrides) -> dict:
    document = {
        "schema": "beast.skill-manifest/v1",
        "protocol_version": 1,
        "content_hash_alg": protocols.CONTENT_HASH_ALG,
        "content_sha256": HEX0,
        "created_at": UTC0,
        "issuer": "aos.test",
        "skill": "research.summarize",
        "component_version": 1,
        "display_name": "Summarize",
        "description": "Summarizes declared inputs.",
        "lifecycle": "active",
        "evaluation": "promoted",
        "io_contracts": {
            "input_ref": "aos.io.sum-input/v1",
            "output_ref": "aos.io.sum-output/v1",
        },
        "required_capabilities": ["research.read"],
        "tool_dependencies": ["fs.read"],
        "binding": {
            "binding_id": "research.summarize.impl",
            "binding_sha256": HEX0,
        },
        "provenance": {"created_by": "human", "method": "create"},
    }
    document.update(overrides)
    return seal(document)


def binding_record(**overrides) -> dict:
    record = {
        "schema": governance.BINDING_RECORD_SCHEMA,
        "binding_id": "fs.read.impl",
        "kind": "in_process",
        "component_kind": "tool",
        "component_id": "fs.read",
        "component_version": 1,
        "config": {},
    }
    record.update(overrides)
    return record


def make_context(**overrides) -> dict:
    context = {
        "invocation_id": UUID1,
        "principal": "agent:codex",
        "granted_capabilities": ["research.read"],
        "max_attempts": 3,
        "attempt": 1,
    }
    context.update(overrides)
    return context


def passport_document(**overrides) -> dict:
    document = {
        "schema": "beast.agent-passport/v1",
        "protocol_version": 1,
        "content_hash_alg": protocols.CONTENT_HASH_ALG,
        "content_sha256": HEX0,
        "created_at": UTC0,
        "issuer": "human",
        "agent": "codex",
        "passport_version": 1,
        "agent_class": "custom",
        "agent_scope": {"level": "global"},
        "role": "developer",
        "mission": "test subject",
        "autonomy": "declare_only",
        "escalation": "ask_human",
        "provenance": {"created_by": "human", "method": "create"},
    }
    document.update(overrides)
    return seal(document)


class ScriptedClock:
    """Deterministic clock: yields the scripted instants in order, then
    repeats the last one forever."""

    def __init__(self, *instants: str) -> None:
        self._instants = list(instants)

    def __call__(self) -> str:
        if len(self._instants) > 1:
            return self._instants.pop(0)
        return self._instants[0]


def build_world(
    *,
    skill_overrides: dict | None = None,
    tool_overrides: dict | None = None,
    tool_callable=None,
    skill_callable=None,
):
    """A minimal governed universe: one read-only tool, one skill depending
    on it, both bound to verified in-process fakes."""
    bindings = governance.BindingRegistry()
    tool_rec = binding_record()
    tool_digest = governance.binding_digest(tool_rec)
    bindings.register(
        tool_rec,
        tool_callable if tool_callable is not None else (lambda value: {"read": True}),
    )
    skill_rec = binding_record(
        binding_id="research.summarize.impl",
        component_kind="skill",
        component_id="research.summarize",
    )
    skill_digest = governance.binding_digest(skill_rec)
    bindings.register(
        skill_rec,
        skill_callable
        if skill_callable is not None
        else (lambda value: {"summary": "ok"}),
    )
    tool_doc = tool_manifest(
        binding={"binding_id": "fs.read.impl", "binding_sha256": tool_digest},
        **(tool_overrides or {}),
    )
    skill_doc = skill_manifest(
        binding={
            "binding_id": "research.summarize.impl",
            "binding_sha256": skill_digest,
        },
        **(skill_overrides or {}),
    )
    tools = governance.build_tool_registry([tool_doc])
    skills = governance.build_skill_registry([skill_doc], tools)
    return skills, tools, bindings


class GovernanceCase(unittest.TestCase):
    def assertRefusesProtocol(self, code, fn, *args, **kwargs):
        with self.assertRaises(protocols.ProtocolError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(
            caught.exception.code,
            code,
            f"expected {code}, got {caught.exception.code}",
        )
        return caught.exception

    def assertRefusesGovernance(self, reason, fn, *args, **kwargs):
        with self.assertRaises(governance.GovernanceError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(
            caught.exception.reason,
            reason,
            f"expected {reason}, got {caught.exception.reason}",
        )
        return caught.exception


# ---------------------------------------------------------------------------
# Closed vocabularies (contract §3): pinned exactly, so a drifted constant is
# a loud failure rather than a silently widened protocol.

class VocabularyTests(unittest.TestCase):
    def test_schema_carried_vocabularies_are_pinned(self):
        self.assertEqual(
            protocols.COMPONENT_LIFECYCLES,
            ("draft", "active", "deprecated", "revoked"),
        )
        self.assertEqual(
            protocols.SKILL_EVALUATION_STATES,
            ("unevaluated", "candidate", "promoted", "rejected"),
        )
        self.assertEqual(
            protocols.TOOL_SIDE_EFFECTS, ("pure", "read_only", "mutating")
        )
        self.assertEqual(
            protocols.TOOL_COMPENSATION_STRATEGIES,
            ("not_applicable", "none", "compensating_action"),
        )
        self.assertEqual(
            protocols.TOOL_IDEMPOTENCY_MODES, ("not_required", "required_key")
        )
        self.assertEqual(
            protocols.TOOL_CANCELLATION_MODES, ("not_supported", "cooperative")
        )
        self.assertEqual(
            protocols.RECOVERY_ACTIONS,
            (
                "none",
                "retry_after_backoff",
                "request_approval",
                "manual_intervention",
                "invoke_compensation",
            ),
        )

    def test_runtime_vocabularies_are_pinned(self):
        self.assertEqual(
            governance.GOVERNANCE_DECISIONS,
            ("allow", "deny", "needs_approval", "unavailable", "invalid"),
        )
        self.assertEqual(
            governance.INVOCATION_STATUSES,
            (
                "success",
                "denied",
                "invalid_input",
                "deadline_exceeded",
                "transient_failure",
                "permanent_failure",
                "recovery_required",
                "dependency_blocked",
            ),
        )
        self.assertEqual(
            governance.TERMINATION_OUTCOMES,
            (
                "not_started",
                "completed",
                "cooperative_cancelled",
                "subprocess_terminated",
                "remote_cancellation_requested",
                "abandoned",
                "not_supported",
            ),
        )
        self.assertEqual(
            governance.LOCAL_TERMINATION_OUTCOMES, ("not_started", "completed")
        )
        self.assertEqual(
            governance.BINDING_KINDS, ("in_process", "metadata")
        )
        self.assertEqual(
            governance.RETRYABLE_STATUSES,
            ("deadline_exceeded", "transient_failure"),
        )
        self.assertEqual(
            governance.RESOLUTION_CODES,
            ("resolved", "unknown_component", "unknown_version"),
        )

    def test_reason_code_classes_partition_the_reason_vocabulary(self):
        union = (
            governance._INVALID_REASONS
            | governance._DENY_REASONS
            | governance._APPROVAL_REASONS
            | governance._UNAVAILABLE_REASONS
        )
        self.assertEqual(union, set(governance.GOVERNANCE_REASON_CODES))
        classes = [
            governance._INVALID_REASONS,
            governance._DENY_REASONS,
            governance._APPROVAL_REASONS,
            governance._UNAVAILABLE_REASONS,
        ]
        for i, left in enumerate(classes):
            for right in classes[i + 1 :]:
                self.assertEqual(left & right, set())

    def test_registry_holds_the_six_required_identities(self):
        self.assertIn("beast.skill-manifest/v1", protocols.REGISTRY)
        self.assertIn("beast.tool-manifest/v1", protocols.REGISTRY)
        self.assertEqual(
            sorted(protocols.REQUIRED_IDENTITIES), sorted(protocols.REGISTRY)
        )

    def test_component_id_pattern_matches_the_requirement_slug_half(self):
        # REQUIREMENT_PATTERN is COMPONENT_ID_PATTERN plus an optional pin.
        self.assertEqual(
            protocols.REQUIREMENT_PATTERN,
            protocols.COMPONENT_ID_PATTERN[:-1] + r"(/v[1-9][0-9]{0,3})?$",
        )


# ---------------------------------------------------------------------------
# Manifest integrity (contract §4, §5, §6, §17 "Manifest integrity")

class ManifestIntegrityTests(GovernanceCase):
    def test_canonical_round_trip_both_manifests(self):
        for document in (skill_manifest(), tool_manifest()):
            with self.subTest(schema=document["schema"]):
                data = json.dumps(document, indent=2).encode("utf-8")
                parsed, entry = protocols.validate_bytes(data)
                self.assertEqual(parsed, document)
                self.assertEqual(entry.identity, document["schema"])
                canonical = protocols.serialize_canonical(document)
                self.assertEqual(protocols.parse_canonical(canonical), document)

    def test_digest_is_stable_under_key_insertion_order(self):
        document = skill_manifest()
        reversed_document = dict(reversed(list(document.items())))
        self.assertEqual(
            protocols.content_digest(document),
            protocols.content_digest(reversed_document),
        )

    def test_unknown_field_is_refused(self):
        for base in (skill_manifest, tool_manifest):
            with self.subTest(base=base.__name__):
                document = base()
                document["approved"] = True
                seal(document)
                self.assertRefusesProtocol(
                    "unknown_field", protocols.validate_document, document
                )

    def test_manifests_carry_the_reduced_envelope_only(self):
        # Task-message fields are unrepresentable on a manifest.
        for field, value in (
            ("aos_task_id", "T-0001"),
            ("idempotency_key", "abcdefgh"),
            ("audience", ["aos.test"]),
            ("permitted_destinations", ["local"]),
            (
                "trace",
                {"trace_id": "1" * 32, "correlation_id": UUID1},
            ),
        ):
            with self.subTest(field=field):
                document = skill_manifest()
                document[field] = value
                seal(document)
                self.assertRefusesProtocol(
                    "unknown_field", protocols.validate_document, document
                )

    def test_unknown_schema_and_major_are_refused(self):
        document = skill_manifest()
        document["schema"] = "beast.skill-manifest/v2"
        seal(document)
        self.assertRefusesProtocol(
            "unsupported_major", protocols.validate_document, document
        )
        document["schema"] = "beast.skillmanifest/v1"
        seal(document)
        self.assertRefusesProtocol(
            "unknown_schema", protocols.validate_document, document
        )

    def test_unknown_enum_members_are_refused(self):
        cases = [
            (skill_manifest, "lifecycle", "enabled"),
            (skill_manifest, "evaluation", "shipped"),
            (tool_manifest, "lifecycle", "enabled"),
            (tool_manifest, "side_effect", "destructive"),
            (tool_manifest, "idempotency", "maybe"),
            (tool_manifest, "cancellation", "kill"),
        ]
        for base, field, value in cases:
            with self.subTest(field=field, value=value):
                document = base(**{field: value})
                self.assertRefusesProtocol(
                    "enum_mismatch", protocols.validate_document, document
                )
        document = tool_manifest(recovery={"action": "reboot"})
        self.assertRefusesProtocol(
            "enum_mismatch", protocols.validate_document, document
        )
        document = tool_manifest(
            compensation={"strategy": "undo"}, side_effect="mutating"
        )
        self.assertRefusesProtocol(
            "enum_mismatch", protocols.validate_document, document
        )

    def test_component_version_bounds(self):
        for bad in (0, protocols.COMPONENT_VERSION_MAX + 1):
            with self.subTest(version=bad):
                self.assertRefusesProtocol(
                    "out_of_range",
                    protocols.validate_document,
                    skill_manifest(component_version=bad),
                )

    def test_hash_mismatch_is_refused(self):
        document = skill_manifest()
        document["display_name"] = "Tampered after sealing"
        self.assertRefusesProtocol(
            "hash_mismatch", protocols.validate_document, document
        )

    def test_case_ambiguous_component_ids_are_unrepresentable(self):
        # The id pattern is lowercase-only ASCII, so two ids differing only
        # by case cannot both validate — ambiguity has no representation.
        self.assertRefusesProtocol(
            "pattern_mismatch",
            protocols.validate_document,
            tool_manifest(tool="FS.Read"),
        )

    def test_replaced_by_requires_deprecated_or_revoked(self):
        self.assertRefusesProtocol(
            "replacement_lifecycle_mismatch",
            protocols.validate_document,
            skill_manifest(replaced_by="research.summarize2"),
        )
        for lifecycle in ("deprecated", "revoked"):
            with self.subTest(lifecycle=lifecycle):
                document = skill_manifest(
                    lifecycle=lifecycle, replaced_by="research.summarize2/v2"
                )
                self.assertEqual(
                    protocols.validate_document(document).identity,
                    "beast.skill-manifest/v1",
                )

    def test_compensation_must_match_side_effect(self):
        for side_effect in ("pure", "read_only"):
            with self.subTest(side_effect=side_effect):
                self.assertRefusesProtocol(
                    "compensation_side_effect_mismatch",
                    protocols.validate_document,
                    tool_manifest(
                        side_effect=side_effect,
                        compensation={"strategy": "none"},
                    ),
                )
        self.assertRefusesProtocol(
            "compensation_side_effect_mismatch",
            protocols.validate_document,
            tool_manifest(
                side_effect="mutating",
                compensation={"strategy": "not_applicable"},
            ),
        )

    def test_compensation_ref_biconditional(self):
        self.assertRefusesProtocol(
            "compensation_ref_mismatch",
            protocols.validate_document,
            tool_manifest(
                side_effect="mutating",
                compensation={"strategy": "compensating_action"},
            ),
        )
        self.assertRefusesProtocol(
            "compensation_ref_mismatch",
            protocols.validate_document,
            tool_manifest(
                side_effect="mutating",
                compensation={"strategy": "none", "ref": "undo.write/v1"},
            ),
        )
        document = tool_manifest(
            side_effect="mutating",
            compensation={
                "strategy": "compensating_action",
                "ref": "undo.write/v1",
            },
        )
        protocols.validate_document(document)

    def test_unsafe_retry_policy_is_unrepresentable(self):
        # Mutating + multi-attempt with neither an idempotency-key
        # requirement nor a compensating action refuses validation.
        self.assertRefusesProtocol(
            "unsafe_retry_policy",
            protocols.validate_document,
            mutating_tool_manifest(
                idempotency="not_required", retry={"max_attempts": 3}
            ),
        )
        # Each safety valve independently legalizes the same retry budget.
        protocols.validate_document(
            mutating_tool_manifest(retry={"max_attempts": 3})
        )
        protocols.validate_document(
            mutating_tool_manifest(
                idempotency="not_required",
                retry={"max_attempts": 3},
                compensation={
                    "strategy": "compensating_action",
                    "ref": "undo.write/v1",
                },
            )
        )
        # A single attempt needs no valve.
        protocols.validate_document(
            mutating_tool_manifest(idempotency="not_required")
        )

    def test_unbounded_retry_is_unrepresentable(self):
        self.assertRefusesProtocol(
            "out_of_range",
            protocols.validate_document,
            tool_manifest(retry={"max_attempts": 11}),
        )
        self.assertRefusesProtocol(
            "wrong_type",
            protocols.validate_document,
            tool_manifest(retry={"max_attempts": None}),
        )

    def test_invoke_compensation_recovery_requires_a_compensating_action(self):
        # A recovery that names a compensation the manifest never declares
        # is an internal contradiction and refuses validation.
        self.assertRefusesProtocol(
            "recovery_compensation_mismatch",
            protocols.validate_document,
            tool_manifest(recovery={"action": "invoke_compensation"}),
        )
        # A mutating tool too: with the retry policy safe via required_key,
        # the recovery/compensation contradiction is what refuses.
        self.assertRefusesProtocol(
            "recovery_compensation_mismatch",
            protocols.validate_document,
            mutating_tool_manifest(recovery={"action": "invoke_compensation"}),
        )
        protocols.validate_document(
            tool_manifest(
                side_effect="mutating",
                compensation={
                    "strategy": "compensating_action",
                    "ref": "undo.write/v1",
                },
                recovery={"action": "invoke_compensation"},
            )
        )

    def test_skill_self_dependency_is_refused(self):
        for dep in ("research.summarize", "research.summarize/v1"):
            with self.subTest(dep=dep):
                self.assertRefusesProtocol(
                    "self_dependency",
                    protocols.validate_document,
                    skill_manifest(skill_dependencies=[dep]),
                )

    def test_existing_artifacts_are_untouched_by_the_new_semantics(self):
        # A passport still validates, and the four legacy schema digests are
        # exactly the checked-in projection's (gen_protocols verifies bytes;
        # this pins the schemas' continued presence and validity).
        document = passport_document()
        self.assertEqual(
            protocols.validate_document(document).identity,
            "beast.agent-passport/v1",
        )


# ---------------------------------------------------------------------------
# Registries (contract §7, §17 "Skills")

class RegistryTests(GovernanceCase):
    def test_build_and_resolve_exact_and_latest(self):
        v1 = tool_manifest()
        v2 = tool_manifest(component_version=2, display_name="Read file v2")
        registry = governance.build_tool_registry([v1, v2])
        self.assertEqual(registry.resolve("fs.read/v1").component_version, 1)
        self.assertEqual(registry.resolve("fs.read").component_version, 2)
        self.assertEqual(registry.ids(), ["fs.read"])
        self.assertEqual(registry.versions("fs.read"), (1, 2))

    def test_latest_is_numeric_not_lexicographic_and_order_independent(self):
        # A bare slug resolves the numerically highest component_version
        # (contract §7). v10 must outrank v2 — a lexicographic "latest" would
        # pick "2" — and insertion order must not change the answer.
        docs = [tool_manifest(component_version=v) for v in (1, 2, 10)]
        forward = governance.build_tool_registry(docs)
        reverse = governance.build_tool_registry(list(reversed(docs)))
        self.assertEqual(forward.resolve("fs.read").component_version, 10)
        self.assertEqual(reverse.resolve("fs.read").component_version, 10)
        self.assertEqual(forward.versions("fs.read"), (1, 2, 10))
        self.assertEqual(forward.resolve("fs.read/v2").component_version, 2)

    def test_resolution_never_consults_lifecycle(self):
        v1 = tool_manifest()
        v2 = tool_manifest(component_version=2, lifecycle="deprecated")
        registry = governance.build_tool_registry([v1, v2])
        # The deprecated latest still resolves; eligibility denies it later,
        # so deprecation is visible instead of silently skipped.
        self.assertEqual(registry.resolve("fs.read").lifecycle, "deprecated")

    def test_duplicate_component_is_refused(self):
        self.assertRefusesGovernance(
            "duplicate_component",
            governance.build_tool_registry,
            [tool_manifest(), tool_manifest(display_name="Other body")],
        )

    def test_wrong_schema_is_refused(self):
        self.assertRefusesGovernance(
            "wrong_schema", governance.build_tool_registry, [skill_manifest()]
        )
        self.assertRefusesGovernance(
            "wrong_schema",
            governance.build_skill_registry,
            [tool_manifest()],
            governance.build_tool_registry([]),
        )
        self.assertRefusesGovernance(
            "wrong_schema", governance.build_tool_registry, ["not a dict"]
        )

    def test_malformed_document_refuses_with_the_protocol_code(self):
        document = tool_manifest()
        document["display_name"] = "Tampered"
        self.assertRefusesProtocol(
            "hash_mismatch", governance.build_tool_registry, [document]
        )

    def test_missing_tool_dependency_is_refused_at_build(self):
        tools = governance.build_tool_registry([])
        self.assertRefusesGovernance(
            "missing_dependency",
            governance.build_skill_registry,
            [skill_manifest()],
            tools,
        )

    def test_unknown_dependency_version_is_refused_at_build(self):
        tools = governance.build_tool_registry([tool_manifest()])
        self.assertRefusesGovernance(
            "unknown_dependency_version",
            governance.build_skill_registry,
            [skill_manifest(tool_dependencies=["fs.read/v9"])],
            tools,
        )

    def test_missing_skill_dependency_is_refused_at_build(self):
        tools = governance.build_tool_registry([tool_manifest()])
        self.assertRefusesGovernance(
            "missing_dependency",
            governance.build_skill_registry,
            [skill_manifest(skill_dependencies=["research.plan"])],
            tools,
        )

    def test_skill_dependency_cycle_is_refused_at_build(self):
        tools = governance.build_tool_registry([tool_manifest()])
        a = skill_manifest(
            skill="research.a", skill_dependencies=["research.b"]
        )
        b = skill_manifest(
            skill="research.b",
            binding={"binding_id": "research.b.impl", "binding_sha256": HEX0},
            skill_dependencies=["research.a"],
        )
        self.assertRefusesGovernance(
            "dependency_cycle", governance.build_skill_registry, [a, b], tools
        )

    def test_skill_dependency_chain_builds(self):
        tools = governance.build_tool_registry([tool_manifest()])
        a = skill_manifest(
            skill="research.a", skill_dependencies=["research.b"]
        )
        b = skill_manifest(
            skill="research.b",
            binding={"binding_id": "research.b.impl", "binding_sha256": HEX0},
        )
        registry = governance.build_skill_registry([a, b], tools)
        self.assertEqual(registry.ids(), ["research.a", "research.b"])

    def test_resolve_refusals_are_closed(self):
        registry = governance.build_tool_registry([tool_manifest()])
        self.assertRefusesGovernance(
            "unknown_component", registry.resolve, "fs.write"
        )
        self.assertRefusesGovernance(
            "unknown_version", registry.resolve, "fs.read/v2"
        )
        self.assertRefusesGovernance(
            "malformed_requirement", registry.resolve, "FS.READ"
        )
        self.assertRefusesGovernance(
            "malformed_requirement", registry.resolve, "fs.read/v01"
        )

    def test_skill_registry_requires_a_tool_registry(self):
        self.assertRefusesGovernance(
            "registry_required", governance.build_skill_registry, [], None
        )

    def test_registry_projection_is_deterministic_and_canonical(self):
        v1 = tool_manifest()
        v2 = tool_manifest(component_version=2)
        first = governance.registry_projection(
            governance.build_tool_registry([v1, v2])
        )
        second = governance.registry_projection(
            governance.build_tool_registry([v2, v1])
        )
        self.assertEqual(first, second)
        protocols.serialize_canonical(first)
        self.assertEqual(
            [c["component_version"] for c in first["components"]], [1, 2]
        )

    def test_undeclared_governance_reason_code_is_a_programming_error(self):
        with self.assertRaises(KeyError):
            governance.GovernanceError("made_up_code")

    def test_post_build_mutation_cannot_alter_decisions_or_digests(self):
        # Registries and the binding registry snapshot their inputs: a
        # caller-retained reference mutated after the build changes nothing
        # the governed flow reads or attests.
        bindings = governance.BindingRegistry()
        record = binding_record()
        digest = bindings.register(record, lambda value: value)
        document = tool_manifest(
            required_capabilities=["fs.metadata"],
            binding={"binding_id": "fs.read.impl", "binding_sha256": digest},
        )
        tools = governance.build_tool_registry([document])
        skills = governance.build_skill_registry([], tools)
        context = make_context(granted_capabilities=[])
        before = governance.evaluate_eligibility(
            "tool", "fs.read", skills=skills, tools=tools,
            bindings=bindings, context=context,
        )
        self.assertEqual(before.decision, "deny")
        self.assertEqual(before.reasons, ("missing_capability",))

        document["required_capabilities"] = []  # caller-side tamper
        record["config"] = {"tampered": True}  # binding-side tamper

        after = governance.evaluate_eligibility(
            "tool", "fs.read", skills=skills, tools=tools,
            bindings=bindings, context=context,
        )
        self.assertEqual(after, before)
        entry = tools.resolve("fs.read")
        self.assertEqual(
            entry.document["required_capabilities"], ["fs.metadata"]
        )
        self.assertEqual(protocols.content_digest(entry.document), entry.digest)


# ---------------------------------------------------------------------------
# Implementation bindings (contract §8, §17 "Tools")

class BindingTests(GovernanceCase):
    def test_digest_is_stable_under_key_insertion_order(self):
        record = binding_record(config={"a": 1, "b": 2})
        reordered = dict(reversed(list(record.items())))
        self.assertEqual(
            governance.binding_digest(record),
            governance.binding_digest(reordered),
        )

    def test_malformed_records_are_refused(self):
        good = binding_record()
        bad_records = [
            {k: v for k, v in good.items() if k != "config"},
            {**good, "extra": 1},
            {**good, "schema": "aos.other/v1"},
            {**good, "kind": "shell"},
            {**good, "component_kind": "plugin"},
            {**good, "binding_id": "Bad Id"},
            {**good, "component_id": "Bad Id"},
            {**good, "component_version": 0},
            {**good, "component_version": True},
            {**good, "config": {"rate": 1.5}},
            {**good, "config": "not a dict"},
            "not a dict",
        ]
        for record in bad_records:
            with self.subTest(record=str(record)[:60]):
                self.assertRefusesGovernance(
                    "malformed_binding", governance.binding_digest, record
                )

    def test_registration_refusals_are_closed(self):
        bindings = governance.BindingRegistry()
        bindings.register(binding_record(), lambda value: value)
        self.assertRefusesGovernance(
            "duplicate_binding",
            bindings.register,
            binding_record(),
            lambda value: value,
        )
        self.assertRefusesGovernance(
            "binding_callable_required",
            bindings.register,
            binding_record(binding_id="other.impl"),
        )
        self.assertRefusesGovernance(
            "binding_callable_required",
            bindings.register,
            binding_record(binding_id="other.impl"),
            "not callable",
        )
        self.assertRefusesGovernance(
            "binding_callable_forbidden",
            bindings.register,
            binding_record(binding_id="meta.impl", kind="metadata"),
            lambda value: value,
        )

    def test_metadata_binding_registers_without_a_callable(self):
        bindings = governance.BindingRegistry()
        digest = bindings.register(
            binding_record(binding_id="meta.impl", kind="metadata")
        )
        self.assertEqual(len(digest), 64)
        self.assertIsNone(bindings.callable_for("meta.impl"))


# ---------------------------------------------------------------------------
# Execution context (contract §10.1)

class ExecutionContextTests(GovernanceCase):
    def test_minimal_and_full_contexts_validate(self):
        governance.validate_execution_context(make_context())
        governance.validate_execution_context(
            make_context(
                caller_agent="codex",
                caller_agent_class="custom",
                caller_passport_sha256=HEX0,
                aos_task_id="T-0001",
                deadline_at="2026-07-23T01:00:00Z",
                idempotency_ref="inv-12345678",
                approval_ref="approval.record/v1",
                policy_ref="policy.record/v1",
                budget_ref="budget.record/v1",
                trace={
                    "trace_id": "1" * 32,
                    "correlation_id": UUID1,
                    "causation_id": UUID1,
                },
            )
        )

    def test_malformed_contexts_are_refused_by_field_name(self):
        bad_contexts = [
            ("context", "not a dict"),
            ("context", make_context(surprise=1)),
            ("invocation_id", {k: v for k, v in make_context().items()
                               if k != "invocation_id"}),
            ("invocation_id", make_context(invocation_id="not-a-uuid")),
            ("principal", make_context(principal="robot")),
            ("granted_capabilities", make_context(granted_capabilities="x")),
            ("granted_capabilities",
             make_context(granted_capabilities=["UPPER"])),
            ("granted_capabilities",
             make_context(granted_capabilities=["a.b", "a.b"])),
            ("granted_capabilities",
             make_context(granted_capabilities=[1])),
            ("granted_capabilities",
             make_context(granted_capabilities=["c" + str(i) for i in range(65)])),
            ("max_attempts", make_context(max_attempts=0)),
            ("max_attempts", make_context(max_attempts=11)),
            ("max_attempts", make_context(max_attempts=True)),
            ("attempt", make_context(attempt=0)),
            ("attempt", make_context(attempt=4)),
            ("caller_agent", make_context(caller_agent="-bad")),
            ("caller_agent_class", make_context(caller_agent_class="root")),
            ("caller_passport_sha256",
             make_context(caller_passport_sha256="ABC")),
            ("aos_task_id", make_context(aos_task_id="TASK-1")),
            ("deadline_at", make_context(deadline_at="2026-07-23")),
            ("deadline_at", make_context(deadline_at="2026-02-30T00:00:00Z")),
            ("idempotency_ref", make_context(idempotency_ref="short")),
            ("approval_ref", make_context(approval_ref="no-version")),
            ("trace", make_context(trace={"trace_id": "1" * 32})),
            ("trace", make_context(
                trace={"trace_id": "0" * 32, "correlation_id": UUID1})),
            ("trace", make_context(
                trace={"trace_id": "1" * 32, "correlation_id": "nope"})),
        ]
        for field, raw in bad_contexts:
            with self.subTest(field=field):
                refusal = self.assertRefusesGovernance(
                    "context_malformed",
                    governance.validate_execution_context,
                    raw,
                )
                self.assertEqual(refusal.where, field)

    def test_refusal_never_echoes_a_value(self):
        secret = "sk-ant-api03-abcdefghijklmnop"
        with self.assertRaises(governance.GovernanceError) as caught:
            governance.validate_execution_context(
                make_context(invocation_id=secret)
            )
        self.assertNotIn(secret, str(caught.exception))

    def test_unknown_keys_fail_closed_and_never_echo(self):
        # An unknown KEY is caller-controlled text too: the refusal names
        # the fixed field "context", never the key.
        secret_key = "sk-ant-api03-secretshapedkey"
        refusal = self.assertRefusesGovernance(
            "context_malformed",
            governance.validate_execution_context,
            {**make_context(), secret_key: 1},
        )
        self.assertEqual(refusal.where, "context")
        self.assertNotIn(secret_key, str(refusal))
        # Mixed-type unknown keys refuse instead of crashing.
        refusal = self.assertRefusesGovernance(
            "context_malformed",
            governance.validate_execution_context,
            {**make_context(), 1: "x", "zzz": 2},
        )
        self.assertEqual(refusal.where, "context")


# ---------------------------------------------------------------------------
# Eligibility (contract §9, §17 "Authority separation")

class EligibilityTests(GovernanceCase):
    def decide(self, kind="skill", ref="research.summarize", *, world=None,
               context=None):
        skills, tools, bindings = world if world else build_world()
        return governance.evaluate_eligibility(
            kind,
            ref,
            skills=skills,
            tools=tools,
            bindings=bindings,
            context=context if context is not None else make_context(),
        )

    def test_exact_required_capabilities_allow_when_all_gates_pass(self):
        decision = self.decide()
        self.assertEqual(decision.decision, "allow")
        self.assertEqual(decision.reasons, ())
        self.assertEqual(decision.component, "skill:research.summarize/v1")

    def test_a_manifest_alone_grants_nothing(self):
        # The manifest declares required_capabilities; an empty external
        # grant refuses. Nothing inside the document can change that.
        decision = self.decide(
            context=make_context(granted_capabilities=[])
        )
        self.assertEqual(decision.decision, "deny")
        self.assertEqual(decision.reasons, ("missing_capability",))
        self.assertEqual(
            decision.diagnostics["missing_capabilities"], ["research.read"]
        )

    def test_unknown_capability_shape_fails_closed(self):
        decision = self.decide(
            context=make_context(granted_capabilities=["NOT-A-CAPABILITY!"])
        )
        self.assertEqual(decision.decision, "invalid")
        self.assertEqual(decision.reasons, ("context_malformed",))

    def test_lifecycle_gates(self):
        for lifecycle in ("draft", "deprecated", "revoked"):
            with self.subTest(lifecycle=lifecycle):
                world = build_world(skill_overrides={"lifecycle": lifecycle})
                decision = self.decide(world=world)
                self.assertEqual(decision.decision, "unavailable")
                self.assertIn("lifecycle_not_active", decision.reasons)

    def test_unpromoted_skill_is_denied(self):
        for evaluation in ("unevaluated", "candidate", "rejected"):
            with self.subTest(evaluation=evaluation):
                world = build_world(skill_overrides={"evaluation": evaluation})
                decision = self.decide(world=world)
                self.assertEqual(decision.decision, "unavailable")
                self.assertIn("not_promoted", decision.reasons)

    def test_agent_class_constraint(self):
        world = build_world(
            skill_overrides={"agent_constraints": {"agent_classes": ["system"]}}
        )
        decision = self.decide(
            world=world, context=make_context(caller_agent_class="custom")
        )
        self.assertEqual(decision.decision, "deny")
        self.assertIn("agent_class_mismatch", decision.reasons)
        # An absent caller class cannot satisfy a declared constraint.
        decision = self.decide(world=world)
        self.assertEqual(decision.decision, "deny")
        self.assertIn("agent_class_mismatch", decision.reasons)
        decision = self.decide(
            world=world, context=make_context(caller_agent_class="system")
        )
        self.assertEqual(decision.decision, "allow")

    def test_approval_declaration_does_not_fabricate_approval(self):
        world = build_world(
            tool_overrides={"approvals_required": ["human sign-off"]}
        )
        context = make_context(granted_capabilities=[])
        decision = governance.evaluate_eligibility(
            "tool", "fs.read", skills=world[0], tools=world[1],
            bindings=world[2], context=context,
        )
        self.assertEqual(decision.decision, "needs_approval")
        self.assertEqual(decision.reasons, ("approval_required",))
        # An approval REFERENCE (owned by another system) satisfies the
        # gate; the manifest itself never can.
        approved = governance.evaluate_eligibility(
            "tool", "fs.read", skills=world[0], tools=world[1],
            bindings=world[2],
            context=make_context(
                granted_capabilities=[], approval_ref="approval.record/v1"
            ),
        )
        self.assertEqual(approved.decision, "allow")

    def test_binding_gates(self):
        # Unknown binding id.
        skills, tools, _ = build_world()
        empty = governance.BindingRegistry()
        decision = governance.evaluate_eligibility(
            "skill", "research.summarize", skills=skills, tools=tools,
            bindings=empty, context=make_context(),
        )
        self.assertEqual(decision.decision, "unavailable")
        self.assertIn("binding_unknown", decision.reasons)
        # Digest mismatch: a registered binding whose record digest is not
        # the one the manifest declares.
        bindings = governance.BindingRegistry()
        bindings.register(
            binding_record(
                binding_id="research.summarize.impl",
                component_kind="skill",
                component_id="research.summarize",
                config={"drifted": True},
            ),
            lambda value: value,
        )
        bindings.register(binding_record(), lambda value: value)
        decision = governance.evaluate_eligibility(
            "skill", "research.summarize", skills=skills, tools=tools,
            bindings=bindings, context=make_context(),
        )
        self.assertEqual(decision.decision, "unavailable")
        self.assertIn("binding_digest_mismatch", decision.reasons)
        # Component mismatch: right id, wrong component.
        bindings = governance.BindingRegistry()
        bindings.register(
            binding_record(
                binding_id="research.summarize.impl",
                component_kind="skill",
                component_id="research.other",
            ),
            lambda value: value,
        )
        decision = governance.evaluate_eligibility(
            "skill", "research.summarize", skills=skills, tools=tools,
            bindings=bindings, context=make_context(),
        )
        self.assertIn("binding_kind_mismatch", decision.reasons)

    def test_dependency_blocked(self):
        world = build_world(tool_overrides={"lifecycle": "deprecated"})
        decision = self.decide(world=world)
        self.assertEqual(decision.decision, "unavailable")
        self.assertIn("dependency_blocked", decision.reasons)
        self.assertEqual(
            decision.diagnostics["blocked_dependencies"], ["fs.read"]
        )

    def test_unknown_component_and_version(self):
        self.assertEqual(
            self.decide(ref="research.missing").reasons,
            ("unknown_component",),
        )
        self.assertEqual(
            self.decide(ref="research.summarize/v9").reasons,
            ("unknown_version",),
        )

    def test_decision_precedence_and_reason_collection(self):
        # Inactive AND missing capability: both reasons are reported, and
        # the authority answer (deny) outranks unavailability.
        world = build_world(skill_overrides={"lifecycle": "draft"})
        decision = self.decide(
            world=world, context=make_context(granted_capabilities=[])
        )
        self.assertEqual(decision.decision, "deny")
        self.assertEqual(
            decision.reasons, ("lifecycle_not_active", "missing_capability")
        )
        # Approval outranks unavailability.
        world = build_world(
            tool_overrides={
                "approvals_required": ["sign-off"],
                "lifecycle": "draft",
            }
        )
        decision = governance.evaluate_eligibility(
            "tool", "fs.read", skills=world[0], tools=world[1],
            bindings=world[2],
            context=make_context(granted_capabilities=[]),
        )
        self.assertEqual(decision.decision, "needs_approval")
        self.assertEqual(
            decision.reasons, ("lifecycle_not_active", "approval_required")
        )

    def test_malformed_context_is_invalid(self):
        decision = self.decide(context={"invocation_id": UUID1})
        self.assertEqual(decision.decision, "invalid")
        self.assertEqual(decision.reasons, ("context_malformed",))

    def test_evaluator_is_pure(self):
        world = build_world()
        first = self.decide(world=world)
        second = self.decide(world=world)
        self.assertEqual(first, second)

    def test_registry_and_kind_guards_raise(self):
        skills, tools, bindings = build_world()
        with self.assertRaises(governance.GovernanceError):
            governance.evaluate_eligibility(
                "plugin", "x", skills=skills, tools=tools,
                bindings=bindings, context=make_context(),
            )
        with self.assertRaises(governance.GovernanceError):
            governance.evaluate_eligibility(
                "skill", "research.summarize", skills=None, tools=tools,
                bindings=bindings, context=make_context(),
            )


# ---------------------------------------------------------------------------
# Invocation protocol (contract §10, §11, §12; §17 "Protocol/results")

class InvokeTests(GovernanceCase):
    def run_skill(self, *, world=None, context=None, input_value=None,
                  clock=None):
        skills, tools, bindings = world if world else build_world()
        return governance.invoke(
            "skill",
            "research.summarize",
            skills=skills,
            tools=tools,
            bindings=bindings,
            context=context if context is not None else make_context(),
            input_value=input_value if input_value is not None else {"text": "x"},
            clock=clock,
        )

    def run_tool(self, ref="fs.read", *, world=None, context=None,
                 input_value=None, clock=None):
        skills, tools, bindings = world if world else build_world()
        return governance.invoke(
            "tool",
            ref,
            skills=skills,
            tools=tools,
            bindings=bindings,
            context=context if context is not None else make_context(),
            input_value=input_value if input_value is not None else {"path": "x"},
            clock=clock,
        )

    def test_success_with_verified_binding(self):
        result = self.run_skill()
        self.assertEqual(result.status, "success")
        self.assertIsNone(result.error_code)
        self.assertEqual(result.decision, "allow")
        self.assertEqual(result.termination_outcome, "completed")
        self.assertEqual(result.recovery_action, "none")
        self.assertFalse(result.retryable)
        self.assertEqual(result.output, {"summary": "ok"})
        self.assertEqual(result.component_id, "research.summarize")
        self.assertEqual(result.component_version, 1)
        self.assertEqual(len(result.manifest_sha256), 64)
        self.assertEqual(len(result.envelope_sha256), 64)
        self.assertEqual(len(result.input_sha256), 64)
        self.assertEqual(len(result.output_sha256), 64)

    def test_input_and_output_digests_are_stable(self):
        first = self.run_skill(input_value={"a": 1, "b": 2})
        second = self.run_skill(input_value={"b": 2, "a": 1})
        self.assertEqual(first.input_sha256, second.input_sha256)
        self.assertEqual(first.output_sha256, second.output_sha256)

    def test_policy_denial_result(self):
        result = self.run_skill(
            context=make_context(granted_capabilities=[])
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "governance_denied")
        self.assertEqual(result.decision, "deny")
        self.assertEqual(result.reasons, ("missing_capability",))
        self.assertEqual(result.termination_outcome, "not_started")
        self.assertFalse(result.retryable)
        self.assertIsNone(result.output)

    def test_needs_approval_result_carries_request_approval_recovery(self):
        world = build_world(
            tool_overrides={"approvals_required": ["sign-off"]}
        )
        result = self.run_tool(world=world)
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "approval_required")
        self.assertEqual(result.recovery_action, "request_approval")

    def test_dependency_blocked_result(self):
        world = build_world(tool_overrides={"lifecycle": "draft"})
        result = self.run_skill(world=world)
        self.assertEqual(result.status, "dependency_blocked")
        self.assertEqual(result.error_code, "dependency_blocked")
        self.assertEqual(result.termination_outcome, "not_started")

    def test_denied_authority_is_not_masked_by_blocked_dependencies(self):
        # Decision tier first: with a capability missing AND a dependency
        # blocked, the result reports the authority denial; the dependency
        # reason still rides along.
        world = build_world(tool_overrides={"lifecycle": "draft"})
        result = self.run_skill(
            world=world, context=make_context(granted_capabilities=[])
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "governance_denied")
        self.assertEqual(result.decision, "deny")
        self.assertIn("missing_capability", result.reasons)
        self.assertIn("dependency_blocked", result.reasons)

    def test_unknown_component_result(self):
        skills, tools, bindings = build_world()
        result = governance.invoke(
            "skill", "research.missing", skills=skills, tools=tools,
            bindings=bindings, context=make_context(), input_value={},
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "unknown_component")

    def test_unknown_version_result(self):
        # The invoke-level `unknown_version` -> denied/unknown_version mapping
        # is a distinct status branch from unknown_component (governance.py
        # decision-tier mapping); a bare-slug latest exists but the /vN pin
        # names no registered version.
        skills, tools, bindings = build_world()
        result = governance.invoke(
            "skill", "research.summarize/v9", skills=skills, tools=tools,
            bindings=bindings, context=make_context(), input_value={},
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.error_code, "unknown_version")

    def test_binding_digest_mismatch_denies_invocation(self):
        skills, tools, _ = build_world()
        bindings = governance.BindingRegistry()
        bindings.register(binding_record(), lambda value: value)
        bindings.register(
            binding_record(
                binding_id="research.summarize.impl",
                component_kind="skill",
                component_id="research.summarize",
                config={"drifted": True},
            ),
            lambda value: {"summary": "evil"},
        )
        result = governance.invoke(
            "skill", "research.summarize", skills=skills, tools=tools,
            bindings=bindings, context=make_context(), input_value={},
        )
        self.assertEqual(result.status, "denied")
        self.assertIn("binding_digest_mismatch", result.reasons)
        self.assertIsNone(result.output)

    def test_metadata_binding_cannot_execute(self):
        bindings = governance.BindingRegistry()
        record = binding_record(kind="metadata")
        digest = bindings.register(record)
        tools = governance.build_tool_registry(
            [
                tool_manifest(
                    binding={
                        "binding_id": "fs.read.impl",
                        "binding_sha256": digest,
                    }
                )
            ]
        )
        skills = governance.build_skill_registry([], tools)
        decision = governance.evaluate_eligibility(
            "tool", "fs.read", skills=skills, tools=tools, bindings=bindings,
            context=make_context(),
        )
        self.assertEqual(decision.decision, "allow")
        result = governance.invoke(
            "tool", "fs.read", skills=skills, tools=tools, bindings=bindings,
            context=make_context(), input_value={},
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.reasons, ("binding_kind_mismatch",))
        self.assertEqual(result.termination_outcome, "not_started")

    def test_skill_metadata_binding_cannot_execute(self):
        # Parity with the tool case above: a skill bound to a `metadata`
        # record is eligible (`allow`) yet the runner refuses to execute it,
        # since only an `in_process` binding carries a callable (contract
        # §8, §10.3.5). Ghost execution is impossible for either kind.
        bindings = governance.BindingRegistry()
        tool_rec = binding_record()
        tool_digest = bindings.register(tool_rec, lambda value: {"read": True})
        tool_doc = tool_manifest(
            binding={"binding_id": "fs.read.impl", "binding_sha256": tool_digest}
        )
        skill_rec = binding_record(
            binding_id="research.summarize.impl",
            component_kind="skill",
            component_id="research.summarize",
            kind="metadata",
        )
        skill_digest = bindings.register(skill_rec)
        skill_doc = skill_manifest(
            binding={
                "binding_id": "research.summarize.impl",
                "binding_sha256": skill_digest,
            }
        )
        tools = governance.build_tool_registry([tool_doc])
        skills = governance.build_skill_registry([skill_doc], tools)
        decision = governance.evaluate_eligibility(
            "skill", "research.summarize", skills=skills, tools=tools,
            bindings=bindings, context=make_context(),
        )
        self.assertEqual(decision.decision, "allow")
        result = governance.invoke(
            "skill", "research.summarize", skills=skills, tools=tools,
            bindings=bindings, context=make_context(), input_value={},
        )
        self.assertEqual(result.status, "denied")
        self.assertEqual(result.reasons, ("binding_kind_mismatch",))
        self.assertEqual(result.termination_outcome, "not_started")

    def test_context_malformed_result(self):
        result = self.run_skill(context={"nope": 1})
        self.assertEqual(result.status, "invalid_input")
        self.assertEqual(result.error_code, "context_malformed")
        self.assertEqual(result.decision, "invalid")
        self.assertIsNone(result.attempt)

    def test_input_gates(self):
        result = self.run_skill(input_value={"rate": 1.5})
        self.assertEqual(result.status, "invalid_input")
        self.assertEqual(result.error_code, "input_not_canonical")
        self.assertIsNone(result.input_sha256)

        world = build_world(
            skill_overrides={"limits": {"max_input_bytes": 8}}
        )
        result = self.run_skill(world=world, input_value={"text": "too long"})
        self.assertEqual(result.status, "invalid_input")
        self.assertEqual(result.error_code, "input_limit_exceeded")

    def test_mutating_tool_requires_idempotency_ref_at_invoke(self):
        bindings = governance.BindingRegistry()
        record = binding_record(
            binding_id="repo.write.impl", component_id="repo.write"
        )
        digest = bindings.register(record, lambda value: {"wrote": True})
        tools = governance.build_tool_registry(
            [
                mutating_tool_manifest(
                    binding={
                        "binding_id": "repo.write.impl",
                        "binding_sha256": digest,
                    }
                )
            ]
        )
        skills = governance.build_skill_registry([], tools)
        world = (skills, tools, bindings)
        result = self.run_tool("repo.write", world=world)
        self.assertEqual(result.status, "invalid_input")
        self.assertEqual(result.error_code, "idempotency_ref_required")
        result = self.run_tool(
            "repo.write",
            world=world,
            context=make_context(idempotency_ref="write-0001-key"),
        )
        self.assertEqual(result.status, "success")

    def test_attempt_budget_is_owned_by_the_context_and_manifest(self):
        # The context bound refuses at validation.
        result = self.run_skill(context=make_context(attempt=4))
        self.assertEqual(result.error_code, "context_malformed")
        # The manifest bound refuses before execution.
        world = build_world(tool_overrides={"retry": {"max_attempts": 2}})
        result = self.run_tool(
            world=world, context=make_context(max_attempts=10, attempt=3)
        )
        self.assertEqual(result.status, "invalid_input")
        self.assertEqual(result.error_code, "attempt_budget_exhausted")

    def test_deadline_before_start_is_not_a_termination_claim(self):
        clock = ScriptedClock(
            "2026-07-23T02:00:00Z",  # started_at
            "2026-07-23T02:00:00Z",  # deadline gate
            "2026-07-23T02:00:01Z",  # ended_at
        )
        result = self.run_skill(
            context=make_context(deadline_at="2026-07-23T01:00:00Z"),
            clock=clock,
        )
        self.assertEqual(result.status, "deadline_exceeded")
        self.assertEqual(result.error_code, "deadline_before_start")
        self.assertEqual(result.termination_outcome, "not_started")
        self.assertTrue(result.retryable)

    def test_deadline_after_completion_reports_completed_work(self):
        clock = ScriptedClock(
            "2026-07-23T00:59:59Z",  # started_at
            "2026-07-23T00:59:59Z",  # deadline gate (still before)
            "2026-07-23T01:00:05Z",  # ended_at (after the deadline)
        )
        result = self.run_skill(
            context=make_context(deadline_at="2026-07-23T01:00:00Z"),
            clock=clock,
        )
        self.assertEqual(result.status, "deadline_exceeded")
        self.assertEqual(result.error_code, "deadline_after_completion")
        # The truthful outcome: the work mechanically finished — late.
        self.assertEqual(result.termination_outcome, "completed")
        self.assertIsNone(result.output)
        self.assertIsNone(result.output_sha256)
        self.assertEqual(result.duration_seconds, 6)

    def test_transient_and_permanent_failures(self):
        def transient(value):
            raise governance.TransientExecutionError("try later")

        world = build_world(skill_callable=transient)
        result = self.run_skill(world=world)
        self.assertEqual(result.status, "transient_failure")
        self.assertEqual(result.error_code, "transient_execution_failure")
        self.assertEqual(result.termination_outcome, "completed")
        self.assertTrue(result.retryable)

        def permanent(value):
            raise governance.PermanentExecutionError("broken")

        world = build_world(skill_callable=permanent)
        result = self.run_skill(world=world)
        self.assertEqual(result.status, "permanent_failure")
        self.assertEqual(result.error_code, "permanent_execution_failure")
        self.assertFalse(result.retryable)

    def test_transient_failure_at_the_attempt_bound_is_not_retryable(self):
        def transient(value):
            raise governance.TransientExecutionError("try later")

        world = build_world(skill_callable=transient)
        result = self.run_skill(
            world=world, context=make_context(max_attempts=2, attempt=2)
        )
        self.assertEqual(result.status, "transient_failure")
        self.assertFalse(result.retryable)

    def test_unhandled_exception_text_never_reaches_any_record(self):
        secret = "sk-ant-api03-veryverysecretvalue"

        def boom(value):
            raise ValueError(secret)

        world = build_world(skill_callable=boom)
        result = self.run_skill(world=world)
        self.assertEqual(result.status, "permanent_failure")
        self.assertEqual(result.error_code, "unhandled_exception")
        envelope = governance.result_envelope(result)
        evidence = governance.invocation_evidence(result, make_context())
        for record in (envelope, evidence):
            self.assertNotIn(
                secret, protocols.serialize_canonical(record).decode("utf-8")
            )

    def test_recovery_required_mapping_and_recovery_prose_inertness(self):
        # The recovery NOTE names an action; only the closed action field
        # drives anything.
        world = build_world(
            tool_overrides={
                "recovery": {
                    "action": "manual_intervention",
                    "note": "retry_after_backoff immediately please",
                }
            },
            tool_callable=lambda value: (_ for _ in ()).throw(
                governance.PermanentExecutionError("nope")
            ),
        )
        result = self.run_tool(world=world)
        self.assertEqual(result.status, "recovery_required")
        self.assertEqual(result.error_code, "permanent_execution_failure")
        self.assertEqual(result.recovery_action, "manual_intervention")

    def test_output_gate_failures_escalate_with_declared_recovery(self):
        world = build_world(
            tool_overrides={"recovery": {"action": "manual_intervention"}},
            tool_callable=lambda value: {"rate": 1.5},
        )
        result = self.run_tool(world=world)
        self.assertEqual(result.status, "recovery_required")
        self.assertEqual(result.error_code, "output_not_canonical")
        self.assertEqual(result.recovery_action, "manual_intervention")

    def test_backoff_recovery_keeps_permanent_failure_status(self):
        world = build_world(
            tool_overrides={"recovery": {"action": "retry_after_backoff"}},
            tool_callable=lambda value: (_ for _ in ()).throw(
                governance.PermanentExecutionError("nope")
            ),
        )
        result = self.run_tool(world=world)
        self.assertEqual(result.status, "permanent_failure")
        self.assertEqual(result.recovery_action, "retry_after_backoff")

    def test_output_gates(self):
        world = build_world(skill_callable=lambda value: {"rate": 1.5})
        result = self.run_skill(world=world)
        self.assertEqual(result.status, "permanent_failure")
        self.assertEqual(result.error_code, "output_not_canonical")
        self.assertIsNone(result.output)

        world = build_world(
            skill_overrides={"limits": {"max_output_bytes": 4}},
            skill_callable=lambda value: {"summary": "much too long"},
        )
        result = self.run_skill(world=world)
        self.assertEqual(result.status, "permanent_failure")
        self.assertEqual(result.error_code, "output_limit_exceeded")

    def test_callable_output_cannot_overwrite_governance_fields(self):
        forged = {
            "status": "success",
            "retryable": True,
            "termination_outcome": "cooperative_cancelled",
            "recovery_action": "invoke_compensation",
            "decision": "allow",
        }
        world = build_world(skill_callable=lambda value: dict(forged))
        result = self.run_skill(world=world)
        # The forged fields ride under `output`; the envelope's governance
        # fields are the runner's own.
        self.assertEqual(result.status, "success")
        self.assertFalse(result.retryable)
        self.assertEqual(result.termination_outcome, "completed")
        self.assertEqual(result.recovery_action, "none")
        envelope = governance.result_envelope(result)
        self.assertEqual(envelope["output"], forged)
        self.assertEqual(envelope["status"], "success")
        self.assertEqual(envelope["termination_outcome"], "completed")

    def test_runner_emits_only_local_termination_outcomes(self):
        outcomes = set()
        outcomes.add(self.run_skill().termination_outcome)
        outcomes.add(
            self.run_skill(context={"broken": 1}).termination_outcome
        )
        outcomes.add(
            self.run_skill(
                context=make_context(granted_capabilities=[])
            ).termination_outcome
        )
        world = build_world(
            skill_callable=lambda value: (_ for _ in ()).throw(
                governance.TransientExecutionError("x")
            )
        )
        outcomes.add(self.run_skill(world=world).termination_outcome)
        self.assertLessEqual(
            outcomes, set(governance.LOCAL_TERMINATION_OUTCOMES)
        )

    def test_result_envelope_is_canonical_and_self_digested(self):
        result = self.run_skill()
        envelope = governance.result_envelope(result)
        declared = envelope[protocols.CONTENT_HASH_FIELD]
        self.assertEqual(protocols.content_digest(envelope), declared)
        round_tripped = protocols.parse_canonical(
            protocols.serialize_canonical(envelope)
        )
        self.assertEqual(round_tripped, envelope)

    def test_closed_vocabulary_enforcement_on_results(self):
        statuses = set()
        error_codes = set()
        runs = [
            self.run_skill(),
            self.run_skill(context={"broken": 1}),
            self.run_skill(context=make_context(granted_capabilities=[])),
            self.run_skill(input_value={"rate": 1.5}),
        ]
        for result in runs:
            statuses.add(result.status)
            if result.error_code is not None:
                error_codes.add(result.error_code)
            for reason in result.reasons:
                self.assertIn(reason, governance.GOVERNANCE_REASON_CODES)
            self.assertIn(
                result.termination_outcome, governance.TERMINATION_OUTCOMES
            )
            self.assertIn(result.recovery_action, protocols.RECOVERY_ACTIONS)
            self.assertIn(result.decision, governance.GOVERNANCE_DECISIONS)
        self.assertLessEqual(statuses, set(governance.INVOCATION_STATUSES))
        self.assertLessEqual(
            error_codes, set(governance.INVOCATION_ERROR_CODES)
        )

    def test_retryable_is_derived_by_code_alone(self):
        world = build_world()
        skills, tools, _ = world
        entry = tools.resolve("fs.read")
        context = governance.validate_execution_context(make_context())
        self.assertTrue(
            governance.derive_retryable(
                entry, "transient_failure", 1, context
            )
        )
        self.assertFalse(
            governance.derive_retryable(entry, "success", 1, context)
        )
        self.assertFalse(
            governance.derive_retryable(entry, "permanent_failure", 1, context)
        )
        self.assertFalse(
            governance.derive_retryable(entry, "transient_failure", 3, context)
        )

    def test_retryable_mutating_gate(self):
        bindings = governance.BindingRegistry()
        record = binding_record(
            binding_id="repo.write.impl", component_id="repo.write"
        )
        digest = bindings.register(record, lambda value: value)
        tools = governance.build_tool_registry(
            [
                mutating_tool_manifest(
                    retry={"max_attempts": 3},
                    binding={
                        "binding_id": "repo.write.impl",
                        "binding_sha256": digest,
                    },
                )
            ]
        )
        entry = tools.resolve("repo.write")
        with_ref = governance.validate_execution_context(
            make_context(idempotency_ref="write-0001-key")
        )
        without_ref = governance.validate_execution_context(make_context())
        self.assertTrue(
            governance.derive_retryable(
                entry, "transient_failure", 1, with_ref
            )
        )
        # No idempotency reference: a mutating replay is refused however
        # transient the failure was.
        self.assertFalse(
            governance.derive_retryable(
                entry, "transient_failure", 1, without_ref
            )
        )


# ---------------------------------------------------------------------------
# Evidence (contract §13, §17 "Protocol/results")

class EvidenceTests(GovernanceCase):
    def build(self, **kwargs):
        skills, tools, bindings = build_world()
        context = make_context(
            caller_agent="codex",
            aos_task_id="T-0001",
            idempotency_ref="inv-12345678",
            trace={"trace_id": "1" * 32, "correlation_id": UUID1},
        )
        result = governance.invoke(
            "skill", "research.summarize", skills=skills, tools=tools,
            bindings=bindings, context=context,
            input_value={"text": "hello"},
        )
        return result, context

    def test_evidence_establishes_the_contract_fields(self):
        result, context = self.build()
        evidence = governance.invocation_evidence(result, context)
        self.assertEqual(evidence["schema"], governance.EVIDENCE_RECORD_SCHEMA)
        self.assertEqual(evidence["invocation_id"], UUID1)
        self.assertEqual(evidence["component_kind"], "skill")
        self.assertEqual(evidence["component_id"], "research.summarize")
        self.assertEqual(evidence["component_version"], 1)
        self.assertEqual(evidence["manifest_sha256"], result.manifest_sha256)
        self.assertEqual(evidence["binding_id"], "research.summarize.impl")
        self.assertEqual(evidence["binding_sha256"], result.binding_sha256)
        self.assertEqual(evidence["principal"], "agent:codex")
        self.assertEqual(evidence["caller_agent"], "codex")
        self.assertEqual(evidence["aos_task_id"], "T-0001")
        self.assertEqual(evidence["decision"], "allow")
        self.assertEqual(evidence["status"], "success")
        self.assertIsNone(evidence["error_code"])
        self.assertEqual(evidence["attempt"], 1)
        self.assertEqual(evidence["termination_outcome"], "completed")
        self.assertEqual(evidence["recovery_action"], "none")
        self.assertEqual(evidence["trace_id"], "1" * 32)
        self.assertEqual(evidence["correlation_id"], UUID1)
        self.assertEqual(evidence["input_sha256"], result.input_sha256)
        self.assertEqual(evidence["output_sha256"], result.output_sha256)
        self.assertEqual(
            protocols.content_digest(evidence),
            evidence[protocols.CONTENT_HASH_FIELD],
        )

    def test_evidence_never_carries_raw_payloads_or_references(self):
        result, context = self.build()
        evidence = governance.invocation_evidence(result, context)
        text = protocols.serialize_canonical(evidence).decode("utf-8")
        self.assertNotIn("hello", text)  # the input value
        self.assertNotIn("summary", text)  # the output value
        self.assertNotIn("inv-12345678", text)  # the raw idempotency ref
        from agentic_os.utils import sha256_text

        self.assertEqual(
            evidence["idempotency_ref_sha256"], sha256_text("inv-12345678")
        )

    def test_evidence_is_deterministic_and_chains(self):
        result, context = self.build()
        first = governance.invocation_evidence(result, context)
        second = governance.invocation_evidence(result, context)
        self.assertEqual(first, second)
        chained = governance.invocation_evidence(
            result, context,
            previous_sha256=first[protocols.CONTENT_HASH_FIELD],
        )
        self.assertEqual(
            chained["previous_sha256"], first[protocols.CONTENT_HASH_FIELD]
        )
        self.assertNotEqual(
            chained[protocols.CONTENT_HASH_FIELD],
            first[protocols.CONTENT_HASH_FIELD],
        )
        self.assertRefusesGovernance(
            "malformed_previous_hash",
            governance.invocation_evidence,
            result,
            context,
            previous_sha256="not-a-hash",
        )

    def test_evidence_reports_the_runner_not_the_model(self):
        # A callable that CLAIMS success inside its output changes nothing
        # about the recorded status of a failing run.
        def liar(value):
            raise governance.PermanentExecutionError("failed but lies")

        skills, tools, bindings = build_world(skill_callable=liar)
        context = make_context()
        result = governance.invoke(
            "skill", "research.summarize", skills=skills, tools=tools,
            bindings=bindings, context=context, input_value={},
        )
        evidence = governance.invocation_evidence(result, context)
        self.assertEqual(evidence["status"], "permanent_failure")
        self.assertIsNone(evidence["output_sha256"])

    def test_invalid_context_contributes_no_caller_fields(self):
        result, _ = self.build()
        evidence = governance.invocation_evidence(result, {"broken": True})
        self.assertIsNone(evidence["principal"])
        self.assertIsNone(evidence["caller_agent"])
        self.assertIsNone(evidence["idempotency_ref_sha256"])


# ---------------------------------------------------------------------------
# Passport requirement resolution (contract §14, §17 "Compatibility")

class PassportProjectionTests(GovernanceCase):
    def test_mixed_resolution_report(self):
        skills, tools, _ = build_world()
        passport = passport_document(
            skill_requirements=["research.summarize", "research.missing"],
            tool_requirements=["fs.read/v1", "fs.read/v9"],
        )
        report = governance.resolve_passport_requirements(
            passport, skills, tools
        )
        codes = [(r.kind, r.requirement, r.code) for r in report.resolutions]
        self.assertEqual(
            codes,
            [
                ("skill", "research.summarize", "resolved"),
                ("skill", "research.missing", "unknown_component"),
                ("tool", "fs.read/v1", "resolved"),
                ("tool", "fs.read/v9", "unknown_version"),
            ],
        )
        self.assertFalse(report.all_resolved)
        self.assertEqual(len(report.unresolved), 2)
        resolved = report.resolutions[0]
        self.assertEqual(resolved.component_id, "research.summarize")
        self.assertEqual(resolved.component_version, 1)
        self.assertEqual(len(resolved.manifest_sha256), 64)

    def test_passport_without_requirements_resolves_vacuously(self):
        skills, tools, _ = build_world()
        report = governance.resolve_passport_requirements(
            passport_document(), skills, tools
        )
        self.assertEqual(report.resolutions, ())
        self.assertTrue(report.all_resolved)

    def test_non_passport_document_is_refused(self):
        skills, tools, _ = build_world()
        self.assertRefusesGovernance(
            "wrong_schema",
            governance.resolve_passport_requirements,
            skill_manifest(),
            skills,
            tools,
        )

    def test_projection_mutates_nothing(self):
        skills, tools, _ = build_world()
        passport = passport_document(
            skill_requirements=["research.summarize"]
        )
        before = json.loads(json.dumps(passport))
        governance.resolve_passport_requirements(passport, skills, tools)
        self.assertEqual(passport, before)


# ---------------------------------------------------------------------------
# Inertness and hygiene (contract §2, §8; the U-X1 no-execution posture)

class NoExecutionTests(GovernanceCase):
    def test_the_whole_flow_never_touches_filesystem_or_network(self):
        boom = AssertionError("governance touched the outside world")
        with mock.patch("os.open", side_effect=boom), mock.patch(
            "builtins.open", side_effect=boom
        ), mock.patch("os.stat", side_effect=boom), mock.patch(
            "os.lstat", side_effect=boom
        ), mock.patch("io.open", side_effect=boom), mock.patch(
            "socket.socket", side_effect=boom
        ):
            skills, tools, bindings = build_world()
            context = make_context()
            decision = governance.evaluate_eligibility(
                "skill", "research.summarize", skills=skills, tools=tools,
                bindings=bindings, context=context,
            )
            self.assertEqual(decision.decision, "allow")
            result = governance.invoke(
                "skill", "research.summarize", skills=skills, tools=tools,
                bindings=bindings, context=context, input_value={"text": "x"},
            )
            self.assertEqual(result.status, "success")
            governance.result_envelope(result)
            governance.invocation_evidence(result, context)
            governance.resolve_passport_requirements(
                passport_document(
                    skill_requirements=["research.summarize"]
                ),
                skills,
                tools,
            )

    def test_source_contains_no_execution_or_import_machinery(self):
        source = (REPO_ROOT / "agentic_os" / "governance.py").read_text(
            encoding="utf-8"
        )
        # "subprocess"/"socket" appear only inside the truthful termination
        # vocabulary ("subprocess_terminated") and prose; the tokens below
        # target the executable forms. " eval(" and "exec(" are audited as
        # string fragments, never executed.
        for token in (
            "importlib",
            "__import__",
            "import subprocess",
            "subprocess.",
            "import socket",
            "socket.",
            "urllib",
            "http.client",
            "os.system",
            "os.popen",
            "exec(",
            " eval(",
            "open(",
            "Path(",
        ):
            self.assertNotIn(token, source, f"forbidden token {token!r}")

    def test_manifest_schemas_refuse_credential_shaped_properties(self):
        # The registry linter would refuse a manifest schema that declared a
        # secret-shaped field; the shipped schemas therefore carry none.
        for identity in ("beast.skill-manifest/v1", "beast.tool-manifest/v1"):
            entry = protocols.REGISTRY[identity]
            names: list[str] = []

            def walk(node):
                if isinstance(node, dict):
                    for key, value in node.get("properties", {}).items():
                        names.append(key)
                        walk(value)
                    if "items" in node:
                        walk(node["items"])

            walk(entry.schema)
            for name in names:
                self.assertIsNone(
                    protocols._SECRET_NAME_RE.search(name),
                    f"{identity} declares credential-shaped field {name!r}",
                )


# ---------------------------------------------------------------------------
# Positive integration demonstration (contract §17 end; build prompt §18)

class IntegrationDemonstrationTests(GovernanceCase):
    def test_passport_to_skill_to_tool_to_result_to_evidence(self):
        skills, tools, bindings = build_world()
        passport = passport_document(
            skill_requirements=["research.summarize"],
            tool_requirements=["fs.read"],
            capabilities=["research.read"],
        )
        report = governance.resolve_passport_requirements(
            passport, skills, tools
        )
        self.assertTrue(report.all_resolved)

        # The external grant mirrors the passport's declared capabilities —
        # the declaration itself granted nothing until this context did.
        context = make_context(
            caller_agent="codex",
            caller_agent_class="custom",
            granted_capabilities=["research.read"],
            trace={"trace_id": "2" * 32, "correlation_id": UUID1},
        )

        skill_result = governance.invoke(
            "skill", "research.summarize", skills=skills, tools=tools,
            bindings=bindings, context=context,
            input_value={"text": "governed"},
        )
        self.assertEqual(skill_result.status, "success")

        tool_result = governance.invoke(
            "tool", "fs.read", skills=skills, tools=tools,
            bindings=bindings, context=context,
            input_value={"ref": "declared-input"},
        )
        self.assertEqual(tool_result.status, "success")
        tool_entry = tools.resolve("fs.read")
        self.assertEqual(tool_entry.document["side_effect"], "read_only")

        first = governance.invocation_evidence(skill_result, context)
        second = governance.invocation_evidence(
            tool_result, context,
            previous_sha256=first[protocols.CONTENT_HASH_FIELD],
        )
        self.assertEqual(
            second["previous_sha256"], first[protocols.CONTENT_HASH_FIELD]
        )
        for record in (first, second):
            self.assertEqual(
                protocols.content_digest(record),
                record[protocols.CONTENT_HASH_FIELD],
            )

    def test_denial_demonstrations(self):
        skills, tools, bindings = build_world()
        # Missing capability -> deterministic denial.
        denied = governance.invoke(
            "skill", "research.summarize", skills=skills, tools=tools,
            bindings=bindings,
            context=make_context(granted_capabilities=[]),
            input_value={},
        )
        self.assertEqual(
            (denied.status, denied.error_code),
            ("denied", "governance_denied"),
        )
        # Binding digest mismatch -> deterministic denial.
        drifted = governance.BindingRegistry()
        drifted.register(binding_record(), lambda value: value)
        drifted.register(
            binding_record(
                binding_id="research.summarize.impl",
                component_kind="skill",
                component_id="research.summarize",
                config={"tampered": True},
            ),
            lambda value: value,
        )
        mismatch = governance.invoke(
            "skill", "research.summarize", skills=skills, tools=tools,
            bindings=drifted, context=make_context(), input_value={},
        )
        self.assertEqual(mismatch.status, "denied")
        self.assertIn("binding_digest_mismatch", mismatch.reasons)
        # Dependency unavailable -> dependency_blocked.
        blocked_world = build_world(
            tool_overrides={"lifecycle": "deprecated"}
        )
        blocked = governance.invoke(
            "skill", "research.summarize",
            skills=blocked_world[0], tools=blocked_world[1],
            bindings=blocked_world[2], context=make_context(),
            input_value={},
        )
        self.assertEqual(blocked.status, "dependency_blocked")


if __name__ == "__main__":
    unittest.main()
