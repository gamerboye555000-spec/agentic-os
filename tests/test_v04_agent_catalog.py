"""U-A2 Wave 1: the deterministic built-in specialist catalog substrate
(agentic-os-v0.4-u-a2-specialist-catalog-contract.md).

Wave 1 only: vocabulary, the twelve shipped passport artifacts, the
manifest, the loader/verifier, and read-only installed-state/status/plan.
There is no `agent catalog install` in this build — nothing here ever
writes an `agents` or `agent_passports` row, and every test that exercises
a governed row does so by direct SQL, exactly like test_v04_agent_passports.py's
TamperTests, to simulate a state a later wave's installer will actually
produce.

Never opens or mutates a real ledger: every workspace here is a disposable
temp directory (V4WorkspaceTestCase), and the shipped catalog under
agentic_os/catalog/ is read-only in every test — synthetic-catalog tests
point the loader at a throwaway temp root instead of editing the real one.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_v04_agent_passports import V4WorkspaceTestCase
from weekend_harness import core_schema, run_cli

from agentic_os import catalog, cli, db, doctor, models, passports, power, protocols, secretscan
from agentic_os.utils import AosError

REPO_ROOT = Path(__file__).resolve().parent.parent

CATALOG_NAMES = (
    "aos.architect",
    "aos.planner",
    "aos.builder",
    "aos.verifier",
    "aos.reviewer",
    "aos.security-auditor",
    "aos.debugger",
    "aos.release-engineer",
    "aos.researcher",
    "aos.curator",
    "aos.analyst",
    "aos.technical-writer",
)

#: Planted where a careless implementation would echo it back out (U-C3),
#: matching the sk-* shape secretscan.scan_secrets detects.
FAKE_SECRET = "sk-catalogtestfake00000000000000"  # noqa: S105


def _ok(fn) -> bool:
    try:
        fn()
        return True
    except AosError:
        return False


# ---------------------------------------------------------------------------
# Synthetic document/manifest builders (group 1 & 2 fixtures — never touch
# the real agentic_os/catalog/ files).

def _seal(document: dict) -> dict:
    document = dict(document)
    document.pop(protocols.CONTENT_HASH_FIELD, None)
    document[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(document)
    return document


def _stub_document(agent: str = "aos.stub", version: int = 1, **overrides) -> dict:
    """A minimal, valid, catalog-shaped beast.agent-passport/v1 document."""
    document = {
        "schema": "beast.agent-passport/v1",
        "protocol_version": 1,
        "content_hash_alg": protocols.CONTENT_HASH_ALG,
        "created_at": "2026-07-17T00:00:00Z",
        "issuer": catalog.CATALOG_ISSUER,
        "agent": agent,
        "passport_version": version,
        "agent_class": "specialist",
        "agent_scope": {"level": "global"},
        "role": "Stub role for tests.",
        "mission": "Stub mission for tests, long enough to be plausible prose.",
        "autonomy": "declare_only",
        "escalation": "ask_human",
        "provenance": {"created_by": "human", "method": "import"},
        "data_classification": "public",
    }
    document.update(overrides)
    return _seal(document)


def _stub_catalog(entries_spec) -> tuple[dict, dict[str, bytes]]:
    """entries_spec: [(agent, category, maturity, [document, ...]), ...],
    in the exact order given (NOT auto-sorted) -> (manifest, {relpath: bytes})."""
    entries = []
    artifacts: dict[str, bytes] = {}
    for agent, category, maturity, documents in entries_spec:
        versions = []
        for doc in documents:
            path = f"{agent}.v{doc['passport_version']}.passport.json"
            artifacts[path] = protocols.serialize_canonical_file_bytes(doc)
            versions.append(
                {
                    "document_sha256": protocols.content_digest(doc),
                    "passport_version": doc["passport_version"],
                    "path": path,
                }
            )
        entries.append(
            {"agent": agent, "category": category, "maturity": maturity, "versions": versions}
        )
    manifest = {
        "canonical_json": protocols.CANONICAL_JSON,
        "catalog_version": 1,
        "content_hash_alg": protocols.CONTENT_HASH_ALG,
        "entries": entries,
        "issuer": catalog.CATALOG_ISSUER,
        "manifest_version": 1,
    }
    manifest = _reseal_manifest_body(manifest)
    artifacts[catalog.MANIFEST_FILENAME] = protocols.serialize_canonical_file_bytes(manifest)
    return manifest, artifacts


def _reseal_manifest_body(manifest: dict) -> dict:
    manifest = dict(manifest)
    manifest.pop(protocols.CONTENT_HASH_FIELD, None)
    manifest[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(manifest)
    return manifest


def _reseal_manifest(manifest: dict) -> dict:
    return _reseal_manifest_body(manifest)


def _retarget_digest(manifest: dict, new_digest: str) -> dict:
    """Deep-copy a single-entry/single-version manifest and repoint its one
    version's document_sha256 at `new_digest`, then reseal the self-digest —
    used to keep the ARTIFACT digest check separate from whatever OTHER
    check (binding, secret-shape) a test wants to isolate."""
    manifest = json.loads(json.dumps(manifest))
    manifest["entries"][0]["versions"][0]["document_sha256"] = new_digest
    return _reseal_manifest_body(manifest)


@contextlib.contextmanager
def synthetic_catalog(files: dict[str, bytes]):
    """Point agentic_os.catalog at a throwaway package-resource root holding
    exactly `files` under a catalog/ subdirectory, in place of the real
    shipped agentic_os/catalog/. Clears the loader's cache on both ends so
    no state leaks either direction."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        catalog_dir = root / catalog.CATALOG_DIRNAME
        catalog_dir.mkdir()
        for relpath, data in files.items():
            path = catalog_dir / relpath
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        catalog.load_manifest.cache_clear()
        try:
            with mock.patch("importlib.resources.files", lambda _pkg: root):
                yield
        finally:
            catalog.load_manifest.cache_clear()


def _table_snapshot(query) -> dict:
    return {
        table: [tuple(row) for row in query(f"SELECT * FROM {table} ORDER BY id")]
        for table in ("agents", "agent_passports", "events")
    }


# ---------------------------------------------------------------------------
# (1) Vocabulary: the disjoint, total user/catalog name gates

class VocabularyTests(unittest.TestCase):
    def test_catalog_names_pass_the_catalog_gate(self):
        for name in CATALOG_NAMES:
            with self.subTest(name=name):
                self.assertEqual(models.validate_catalog_agent_name(name), name)

    def test_catalog_names_are_refused_by_the_user_gate(self):
        for name in CATALOG_NAMES:
            with self.subTest(name=name):
                with self.assertRaises(AosError):
                    models.validate_new_agent_name(name)

    def test_user_names_are_refused_by_the_catalog_gate(self):
        for name in ("mybot", "codex", "human-reviewer", "x"):
            with self.subTest(name=name):
                with self.assertRaises(AosError):
                    models.validate_catalog_agent_name(name)

    def test_gates_are_disjoint_and_total_over_every_name(self):
        names = list(CATALOG_NAMES) + ["mybot", "codex", "aos.made-up-future-entry"]
        for name in names:
            with self.subTest(name=name):
                catalog_ok = _ok(lambda n=name: models.validate_catalog_agent_name(n))
                user_ok = _ok(lambda n=name: models.validate_new_agent_name(n))
                self.assertNotEqual(catalog_ok, user_ok, name)

    def test_no_case_folding_or_unicode_normalization(self):
        # A differently-cased lookalike is simply a different, non-catalog
        # name: refused by the catalog gate, legal on the user gate.
        with self.assertRaises(AosError):
            models.validate_catalog_agent_name("AOS.architect")
        self.assertEqual(models.validate_new_agent_name("AOS.architect"), "AOS.architect")

    def test_reserved_vocabulary_is_untouched(self):
        self.assertEqual(models.RESERVED_AGENT_PREFIXES, ("aos.", "beast."))
        self.assertEqual(
            models.RESERVED_AGENT_NAMES,
            ("governor", "planner", "builder", "verifier", "security-sentinel"),
        )

    def test_validate_new_agent_name_still_refuses_reserved_bare_names(self):
        for name in models.RESERVED_AGENT_NAMES:
            with self.subTest(name=name):
                with self.assertRaises(AosError):
                    models.validate_new_agent_name(name)

    def test_validate_new_agent_name_still_refuses_beast_prefix(self):
        with self.assertRaises(AosError):
            models.validate_new_agent_name("beast.something")

    def test_vocabulary_constants(self):
        self.assertEqual(models.CATALOG_AGENT_PREFIX, "aos.")
        self.assertEqual(models.CATALOG_ISSUER, "aos.catalog")


# ---------------------------------------------------------------------------
# (2) Manifest structural validation — synthetic manifests, direct calls to
# catalog._validate_manifest. Never touches the real shipped manifest.

class ManifestValidationTests(unittest.TestCase):
    def setUp(self):
        self.doc = _stub_document()
        self.manifest, self.artifacts = _stub_catalog(
            [("aos.stub", "design", "stable", [self.doc])]
        )

    def test_valid_manifest_round_trips(self):
        cat = catalog._validate_manifest(self.manifest)
        self.assertEqual(cat.names(), ["aos.stub"])
        self.assertEqual(cat.catalog_version, 1)
        self.assertEqual(cat.manifest_sha256, self.manifest["content_sha256"])

    def test_unknown_top_level_key_refuses(self):
        bad = _reseal_manifest(dict(self.manifest, extra="nope"))
        with self.assertRaises(catalog.CatalogError):
            catalog._validate_manifest(bad)

    def test_missing_top_level_key_refuses(self):
        bad = dict(self.manifest)
        del bad["issuer"]
        with self.assertRaises(catalog.CatalogError):
            catalog._validate_manifest(bad)

    def test_bad_top_level_vocabulary_refuses(self):
        for field, value in (
            ("canonical_json", "nope/v1"),
            ("content_hash_alg", "nope/v1"),
            ("issuer", "human"),
            ("manifest_version", 2),
            ("catalog_version", 0),
            ("catalog_version", "1"),
        ):
            with self.subTest(field=field, value=value):
                bad = dict(self.manifest, **{field: value})
                with self.assertRaises(catalog.CatalogError):
                    catalog._validate_manifest(bad)

    def test_wrong_self_digest_refuses(self):
        bad = dict(self.manifest, content_sha256="0" * 64)
        with self.assertRaises(catalog.CatalogError):
            catalog._validate_manifest(bad)

    def test_malformed_top_level_hash_refuses(self):
        for bad_hash in ("0" * 63, "0" * 65, "G" * 64, self.manifest["content_sha256"].upper(), ""):
            with self.subTest(bad_hash=bad_hash):
                bad = dict(self.manifest, content_sha256=bad_hash)
                with self.assertRaises(catalog.CatalogError):
                    catalog._validate_manifest(bad)

    def test_duplicate_agent_refuses(self):
        bad = _reseal_manifest(dict(self.manifest, entries=self.manifest["entries"] * 2))
        with self.assertRaises(catalog.CatalogError):
            catalog._validate_manifest(bad)

    def test_duplicate_digest_across_different_entries_refuses(self):
        doc_a = _stub_document(agent="aos.alpha")
        doc_b = _stub_document(agent="aos.beta")
        manifest, _artifacts = _stub_catalog(
            [
                ("aos.alpha", "design", "stable", [doc_a]),
                ("aos.beta", "design", "stable", [doc_b]),
            ]
        )
        shared_digest = manifest["entries"][0]["versions"][0]["document_sha256"]
        manifest["entries"][1]["versions"][0]["document_sha256"] = shared_digest
        manifest = _reseal_manifest(manifest)
        with self.assertRaises(catalog.CatalogError):
            catalog._validate_manifest(manifest)

    def test_non_contiguous_versions_refuses(self):
        doc1 = _stub_document(version=1)
        doc3 = _stub_document(version=3)
        manifest, _artifacts = _stub_catalog([("aos.stub", "design", "stable", [doc1, doc3])])
        with self.assertRaises(catalog.CatalogError):
            catalog._validate_manifest(manifest)

    def test_versions_not_starting_at_one_refuses(self):
        doc2 = _stub_document(version=2)
        manifest, _artifacts = _stub_catalog([("aos.stub", "design", "stable", [doc2])])
        with self.assertRaises(catalog.CatalogError):
            catalog._validate_manifest(manifest)

    def test_bad_entry_sort_order_refuses(self):
        doc_z = _stub_document(agent="aos.zzz")
        doc_a = _stub_document(agent="aos.aaa")
        manifest, _artifacts = _stub_catalog(
            [
                ("aos.zzz", "design", "stable", [doc_z]),
                ("aos.aaa", "design", "stable", [doc_a]),
            ]
        )
        with self.assertRaises(catalog.CatalogError):
            catalog._validate_manifest(manifest)

    def test_bad_category_or_maturity_refuses(self):
        for field, value in (("category", "nope"), ("maturity", "nope")):
            with self.subTest(field=field):
                manifest, _artifacts = _stub_catalog(
                    [("aos.stub", "design", "stable", [self.doc])]
                )
                manifest["entries"][0][field] = value
                manifest = _reseal_manifest(manifest)
                with self.assertRaises(catalog.CatalogError):
                    catalog._validate_manifest(manifest)

    def test_agent_outside_catalog_namespace_refuses(self):
        doc = _stub_document(agent="not-catalog")
        manifest, _artifacts = _stub_catalog([("not-catalog", "design", "stable", [doc])])
        with self.assertRaises(catalog.CatalogError):
            catalog._validate_manifest(manifest)

    def test_path_mismatch_refuses(self):
        manifest, _artifacts = _stub_catalog([("aos.stub", "design", "stable", [self.doc])])
        manifest["entries"][0]["versions"][0]["path"] = "aos.stub.v1.passport.json.evil"
        manifest = _reseal_manifest(manifest)
        with self.assertRaises(catalog.CatalogError):
            catalog._validate_manifest(manifest)

    def test_path_traversal_shaped_value_refuses(self):
        manifest, _artifacts = _stub_catalog([("aos.stub", "design", "stable", [self.doc])])
        manifest["entries"][0]["versions"][0]["path"] = "../../etc/passwd"
        manifest = _reseal_manifest(manifest)
        with self.assertRaises(catalog.CatalogError):
            catalog._validate_manifest(manifest)

    def test_malformed_version_hash_refuses(self):
        for bad_hash in ("0" * 63, "G" * 64, "0" * 64 + "x", ""):
            with self.subTest(bad_hash=bad_hash):
                manifest, _artifacts = _stub_catalog(
                    [("aos.stub", "design", "stable", [self.doc])]
                )
                manifest["entries"][0]["versions"][0]["document_sha256"] = bad_hash
                manifest = _reseal_manifest(manifest)
                with self.assertRaises(catalog.CatalogError):
                    catalog._validate_manifest(manifest)

    def test_uppercase_version_hash_refuses(self):
        manifest, _artifacts = _stub_catalog([("aos.stub", "design", "stable", [self.doc])])
        manifest["entries"][0]["versions"][0]["document_sha256"] = manifest["entries"][0][
            "versions"
        ][0]["document_sha256"].upper()
        manifest = _reseal_manifest(manifest)
        with self.assertRaises(catalog.CatalogError):
            catalog._validate_manifest(manifest)

    def test_unknown_entry_key_refuses(self):
        manifest, _artifacts = _stub_catalog([("aos.stub", "design", "stable", [self.doc])])
        manifest["entries"][0]["extra"] = "x"
        manifest = _reseal_manifest(manifest)
        with self.assertRaises(catalog.CatalogError):
            catalog._validate_manifest(manifest)

    def test_unknown_version_key_refuses(self):
        manifest, _artifacts = _stub_catalog([("aos.stub", "design", "stable", [self.doc])])
        manifest["entries"][0]["versions"][0]["extra"] = "x"
        manifest = _reseal_manifest(manifest)
        with self.assertRaises(catalog.CatalogError):
            catalog._validate_manifest(manifest)


# ---------------------------------------------------------------------------
# (3) The real shipped catalog: exact count, order, vocabulary, and a deep
# per-artifact proof (canonical bytes, protocol validation, both digests,
# uniform fields, no secret-shaped prose).

class ShippedCatalogTests(unittest.TestCase):
    def setUp(self):
        catalog.load_manifest.cache_clear()

    def tearDown(self):
        catalog.load_manifest.cache_clear()

    def test_exactly_twelve_entries(self):
        cat = catalog.catalog()
        self.assertEqual(len(cat.entries), 12)
        self.assertEqual(set(cat.names()), set(CATALOG_NAMES))

    def test_entries_sorted_by_agent_code_point_order(self):
        names = catalog.catalog().names()
        self.assertEqual(names, sorted(names))

    def test_category_and_maturity_values(self):
        expected = {
            "aos.architect": ("design", "stable"),
            "aos.planner": ("design", "stable"),
            "aos.builder": ("delivery", "stable"),
            "aos.verifier": ("assurance", "stable"),
            "aos.reviewer": ("assurance", "stable"),
            "aos.security-auditor": ("assurance", "stable"),
            "aos.debugger": ("operations", "stable"),
            "aos.release-engineer": ("operations", "stable"),
            "aos.researcher": ("knowledge", "stable"),
            "aos.curator": ("knowledge", "stable"),
            "aos.analyst": ("knowledge", "provisional"),
            "aos.technical-writer": ("knowledge", "stable"),
        }
        for entry in catalog.catalog().entries:
            with self.subTest(agent=entry.agent):
                self.assertEqual((entry.category, entry.maturity), expected[entry.agent])

    def test_only_aos_analyst_is_provisional(self):
        provisional = [e.agent for e in catalog.catalog().entries if e.maturity == "provisional"]
        self.assertEqual(provisional, ["aos.analyst"])

    def test_every_entry_ships_exactly_one_version(self):
        for entry in catalog.catalog().entries:
            with self.subTest(agent=entry.agent):
                self.assertEqual([v.passport_version for v in entry.versions], [1])

    def test_verify_succeeds_on_the_shipped_catalog(self):
        self.assertEqual(catalog.verify(), [])

    def test_every_artifact_is_deeply_valid(self):
        for entry in catalog.catalog().entries:
            for version in entry.versions:
                with self.subTest(agent=entry.agent, version=version.passport_version):
                    document, text = catalog.load_document(entry, version)

                    self.assertTrue(text.endswith("\n"))
                    self.assertFalse(text.endswith("\n\n"))
                    self.assertEqual(protocols.serialize_canonical(document), text[:-1].encode("utf-8"))

                    schema_entry = protocols.validate_document(document)
                    self.assertEqual(schema_entry.identity, "beast.agent-passport/v1")

                    self.assertEqual(document["content_sha256"], protocols.content_digest(document))
                    self.assertEqual(protocols.content_digest(document), version.document_sha256)

                    self.assertEqual(document["agent"], entry.agent)
                    self.assertEqual(document["passport_version"], version.passport_version)
                    self.assertEqual(document["issuer"], "aos.catalog")
                    self.assertEqual(document["agent_class"], "specialist")
                    self.assertEqual(document["agent_scope"], {"level": "global"})
                    self.assertEqual(document["autonomy"], "declare_only")
                    self.assertEqual(document["data_classification"], "public")
                    self.assertNotIn("provider_compat", document)
                    self.assertNotIn("limits", document)

                    for key, _label in catalog._SCANNED_TEXT_FIELDS:
                        value = document.get(key)
                        if isinstance(value, list):
                            value = "\n".join(value)
                        if isinstance(value, str):
                            self.assertEqual(secretscan.scan_secrets(value), [])

    def test_entry_public_is_stable_across_reloads(self):
        first = [catalog.entry_public(e) for e in catalog.catalog().entries]
        catalog.load_manifest.cache_clear()
        second = [catalog.entry_public(e) for e in catalog.catalog().entries]
        self.assertEqual(first, second)


# ---------------------------------------------------------------------------
# (4) Artifact loading against a synthetic package-resource root: missing,
# extra, non-canonical, digest, binding, secret-shape.

class ArtifactLoadingTests(unittest.TestCase):
    def setUp(self):
        self.doc = _stub_document()
        self.manifest, self.artifacts = _stub_catalog(
            [("aos.stub", "design", "stable", [self.doc])]
        )
        self.entry = catalog._validate_manifest(self.manifest).entries[0]
        self.version = self.entry.versions[0]

    def test_well_formed_synthetic_catalog_verifies_clean(self):
        with synthetic_catalog(self.artifacts):
            self.assertEqual(catalog.verify(), [])
            document, _text = catalog.load_document(self.entry, self.version)
            self.assertEqual(document["agent"], "aos.stub")

    def test_missing_artifact_refuses(self):
        files = dict(self.artifacts)
        del files["aos.stub.v1.passport.json"]
        with synthetic_catalog(files):
            self.assertTrue(catalog.verify())
            with self.assertRaises(catalog.CatalogError):
                catalog.load_document(self.entry, self.version)

    def test_extra_unreferenced_artifact_is_reported(self):
        files = dict(self.artifacts)
        files["aos.rogue.v1.passport.json"] = b"{}\n"
        with synthetic_catalog(files):
            problems = catalog.verify()
            self.assertTrue(any("aos.rogue" in p for p in problems))

    def test_non_canonical_bytes_refuse(self):
        files = dict(self.artifacts)
        files["aos.stub.v1.passport.json"] = json.dumps(self.doc, indent=2).encode("utf-8") + b"\n"
        with synthetic_catalog(files):
            with self.assertRaises(catalog.CatalogError):
                catalog.load_document(self.entry, self.version)

    def test_missing_trailing_newline_refuses(self):
        files = dict(self.artifacts)
        files["aos.stub.v1.passport.json"] = files["aos.stub.v1.passport.json"].rstrip(b"\n")
        with synthetic_catalog(files):
            with self.assertRaises(catalog.CatalogError):
                catalog.load_document(self.entry, self.version)

    def test_wrong_internal_content_sha256_refuses(self):
        bad_doc = dict(self.doc, content_sha256="0" * 64)
        files = dict(self.artifacts)
        files["aos.stub.v1.passport.json"] = protocols.serialize_canonical_file_bytes(bad_doc)
        with synthetic_catalog(files):
            with self.assertRaises(catalog.CatalogError):
                catalog.load_document(self.entry, self.version)

    def test_digest_not_matching_manifest_refuses(self):
        different = _stub_document(agent="aos.stub", role="A completely different role text.")
        files = dict(self.artifacts)
        files["aos.stub.v1.passport.json"] = protocols.serialize_canonical_file_bytes(different)
        with synthetic_catalog(files):
            with self.assertRaises(catalog.CatalogError):
                catalog.load_document(self.entry, self.version)

    def test_malformed_utf8_refuses(self):
        files = dict(self.artifacts)
        files["aos.stub.v1.passport.json"] = b"\xff\xfe not utf-8\n"
        with synthetic_catalog(files):
            with self.assertRaises(catalog.CatalogError):
                catalog.load_document(self.entry, self.version)

    def test_binding_mismatches_refuse(self):
        cases = {
            "agent": dict(self.doc, agent="aos.other"),
            "passport_version": dict(self.doc, passport_version=2),
            "issuer": dict(self.doc, issuer="human"),
            "agent_class": dict(self.doc, agent_class="custom"),
            "agent_scope": dict(self.doc, agent_scope={"level": "project", "project": "x"}),
            "autonomy": dict(self.doc, autonomy="supervised"),
        }
        for field, overridden in cases.items():
            with self.subTest(field=field):
                bad_doc = _seal(overridden)
                manifest = _retarget_digest(self.manifest, protocols.content_digest(bad_doc))
                files = {
                    "aos.stub.v1.passport.json": protocols.serialize_canonical_file_bytes(bad_doc),
                    catalog.MANIFEST_FILENAME: protocols.serialize_canonical_file_bytes(manifest),
                }
                with synthetic_catalog(files):
                    entry = catalog._validate_manifest(manifest).entries[0]
                    with self.assertRaises(catalog.CatalogError):
                        catalog.load_document(entry, entry.versions[0])

    def test_secret_shaped_content_refuses_fail_closed(self):
        bad_doc = _seal(dict(self.doc, mission=f"Use {FAKE_SECRET} to authenticate."))
        manifest = _retarget_digest(self.manifest, protocols.content_digest(bad_doc))
        files = {
            "aos.stub.v1.passport.json": protocols.serialize_canonical_file_bytes(bad_doc),
            catalog.MANIFEST_FILENAME: protocols.serialize_canonical_file_bytes(manifest),
        }
        with synthetic_catalog(files):
            entry = catalog._validate_manifest(manifest).entries[0]
            with self.assertRaises(catalog.CatalogError) as ctx:
                catalog.load_document(entry, entry.versions[0])
            self.assertNotIn(FAKE_SECRET, str(ctx.exception))
            problems = catalog.verify()
            self.assertTrue(problems)
            self.assertFalse(any(FAKE_SECRET in p for p in problems))


class ResourcePathSafetyTests(unittest.TestCase):
    def test_unsafe_relpaths_refuse(self):
        for relpath in (
            "../manifest.json",
            "sub/dir.json",
            "AOS.stub.v1.passport.json",
            "aos.stub.v0.passport.json",
            "aos.stub.v01.passport.json",
            "manifest.json.bak",
            "aos.stub.v1.passport.json/",
        ):
            with self.subTest(relpath=relpath):
                with self.assertRaises(catalog.CatalogError):
                    catalog._resource(relpath)

    def test_traversal_path_reason_code(self):
        with self.assertRaises(catalog.CatalogError) as ctx:
            catalog._resource("../manifest.json")
        self.assertEqual(ctx.exception.reason, "unsafe_path")

    def test_missing_well_shaped_artifact_is_a_distinct_reason(self):
        with synthetic_catalog({catalog.MANIFEST_FILENAME: b"{}\n"}):
            with self.assertRaises(catalog.CatalogError) as ctx:
                catalog._resource("aos.doesnotexist.v1.passport.json")
            self.assertEqual(ctx.exception.reason, "missing")


# ---------------------------------------------------------------------------
# (5) Read-only CLI: list / show / verify — no workspace needed for any of
# the three.

class CliListShowVerifyTests(unittest.TestCase):
    def test_no_workspace_required_for_list_show_verify(self):
        for argv in (
            ("agent", "catalog", "list"),
            ("agent", "catalog", "show", "aos.architect"),
            ("agent", "catalog", "verify"),
        ):
            with self.subTest(argv=argv):
                code, _out, err = run_cli(*argv)
                self.assertEqual(code, 0, err)

    def test_list_text_lists_all_twelve_sorted(self):
        code, out, err = run_cli("agent", "catalog", "list")
        self.assertEqual(code, 0, err)
        lines = [line for line in out.splitlines() if line.startswith("aos.")]
        self.assertEqual(len(lines), 12)
        names = [line.split()[0] for line in lines]
        self.assertEqual(names, sorted(names))
        self.assertIn("12 entry(ies), catalog v1", out)

    def test_list_json_shape(self):
        code, out, err = run_cli("agent", "catalog", "list", "--json")
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        entries = data["catalog"]["entries"]
        self.assertEqual(len(entries), 12)
        for entry in entries:
            self.assertEqual(
                set(entry),
                {"agent", "category", "maturity", "passport_version", "document_sha256", "versions"},
            )

    def test_list_is_byte_identical_across_repeated_runs(self):
        _, out1, _ = run_cli("agent", "catalog", "list")
        _, out2, _ = run_cli("agent", "catalog", "list")
        self.assertEqual(out1, out2)

    def test_show_normal_view(self):
        code, out, err = run_cli("agent", "catalog", "show", "aos.security-auditor")
        self.assertEqual(code, 0, err)
        self.assertIn("aos.security-auditor", out)
        self.assertIn("escalation:", out)
        self.assertIn("halt", out)

    def test_show_document_is_the_exact_stored_bytes(self):
        code, out, err = run_cli("agent", "catalog", "show", "aos.architect", "--document")
        self.assertEqual(code, 0, err)
        path = REPO_ROOT / "agentic_os" / "catalog" / "aos.architect.v1.passport.json"
        self.assertEqual(out.encode("utf-8"), path.read_bytes())

    def test_show_fragment_excludes_exactly_the_forbidden_fields(self):
        code, out, err = run_cli("agent", "catalog", "show", "aos.architect", "--fragment")
        self.assertEqual(code, 0, err)
        fragment = json.loads(out)
        self.assertEqual(set(fragment) & passports._FRAGMENT_FORBIDDEN, set())
        path = REPO_ROOT / "agentic_os" / "catalog" / "aos.architect.v1.passport.json"
        full = json.loads(path.read_bytes())
        expected = {k: v for k, v in full.items() if k not in passports._FRAGMENT_FORBIDDEN}
        self.assertEqual(fragment, expected)

    def test_show_json_shape(self):
        code, out, err = run_cli("agent", "catalog", "show", "aos.architect", "--json")
        self.assertEqual(code, 0, err)
        data = json.loads(out)
        self.assertEqual(set(data), {"entry", "document"})
        self.assertEqual(data["document"]["agent"], "aos.architect")

    def test_show_rejects_incompatible_flag_combinations(self):
        for flags in (
            ["--document", "--fragment"],
            ["--document", "--json"],
            ["--fragment", "--json"],
            ["--document", "--fragment", "--json"],
        ):
            with self.subTest(flags=flags):
                code, out, err = run_cli("agent", "catalog", "show", "aos.architect", *flags)
                self.assertEqual(code, 1)
                self.assertEqual(out, "")
                self.assertIn("at most one", err)

    def test_show_unknown_name_exits_one_with_one_actionable_line(self):
        code, out, err = run_cli("agent", "catalog", "show", "aos.nonexistent")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(len(err.strip().splitlines()), 1)
        self.assertIn("aos.nonexistent", err)

    def test_fragment_round_trips_through_create_from_file_for_every_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "ws"
            root.mkdir()
            code, _out, err = run_cli("--root", str(root), "init")
            self.assertEqual(code, 0, err)
            for name in CATALOG_NAMES:
                code, frag, err = run_cli("agent", "catalog", "show", name, "--fragment")
                self.assertEqual(code, 0, err)
                frag_path = Path(tmp) / f"{name}.json"
                frag_path.write_text(frag, encoding="utf-8")
                derived = "my-" + name.split(".", 1)[1]
                code, out, err = run_cli(
                    "--root", str(root), "agent", "create", derived, "--from-file", str(frag_path)
                )
                self.assertEqual(code, 0, (name, err, out))

    def test_verify_succeeds_with_no_stderr(self):
        code, out, err = run_cli("agent", "catalog", "verify")
        self.assertEqual(code, 0, err)
        self.assertEqual(err, "")
        self.assertIn("OK", out)

    def test_verify_json_shape_on_success(self):
        code, out, err = run_cli("agent", "catalog", "verify", "--json")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"problems": []})

    def test_verify_reports_problems_and_exits_one(self):
        with mock.patch("agentic_os.catalog.verify", return_value=["fake problem: x"]):
            code, out, err = run_cli("agent", "catalog", "verify")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("fake problem: x", err)

    def test_verify_json_reports_problems(self):
        with mock.patch("agentic_os.catalog.verify", return_value=["fake problem: x"]):
            code, out, err = run_cli("agent", "catalog", "verify", "--json")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out), {"problems": ["fake problem: x"]})


# ---------------------------------------------------------------------------
# (6) status / plan: require a workspace, read-only, deterministic.

class StatusPlanCliTests(V4WorkspaceTestCase):
    def test_status_requires_a_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty_root = Path(tmp) / "empty"
            empty_root.mkdir()
            code, out, err = run_cli("--root", str(empty_root), "agent", "catalog", "status")
            self.assertEqual(code, 1)
            self.assertEqual(out, "")
            self.assertIn("Not initialized", err)

    def test_plan_requires_a_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            empty_root = Path(tmp) / "empty"
            empty_root.mkdir()
            code, out, err = run_cli(
                "--root", str(empty_root), "agent", "catalog", "plan", "--all"
            )
            self.assertEqual(code, 1)
            self.assertIn("Not initialized", err)

    def test_fresh_workspace_status_is_all_not_installed(self):
        code, out, err = self.aos("agent", "catalog", "status")
        self.assertEqual(code, 0, err)
        lines = [line for line in out.splitlines() if line.startswith("aos.")]
        self.assertEqual(len(lines), 12)
        self.assertTrue(all("not_installed" in line for line in lines))
        self.assertIn("12 entry(ies): 12 not_installed", out)

    def test_status_json_shape(self):
        out = self.ok("agent", "catalog", "status", "--json")
        rows = json.loads(out)["status"]
        self.assertEqual(len(rows), 12)
        for row in rows:
            self.assertEqual(
                set(row), {"agent", "state", "installed_version", "available_version", "detail"}
            )
            self.assertEqual(row["state"], "not_installed")
            self.assertIsNone(row["installed_version"])
            self.assertEqual(row["available_version"], 1)

    def test_plan_all_proposes_install_for_everything(self):
        out = self.ok("agent", "catalog", "plan", "--all", "--json")
        actions = json.loads(out)["plan"]
        self.assertEqual(len(actions), 12)
        self.assertTrue(all(a["action"] == "install" for a in actions))

    def test_plan_named_subset_preserves_selection(self):
        out = self.ok("agent", "catalog", "plan", "aos.architect", "aos.builder", "--json")
        actions = json.loads(out)["plan"]
        self.assertEqual([a["agent"] for a in actions], ["aos.architect", "aos.builder"])

    def test_plan_rejects_names_and_all_together(self):
        err = self.fails("agent", "catalog", "plan", "aos.architect", "--all")
        self.assertIn("not both", err)

    def test_plan_rejects_neither_names_nor_all(self):
        err = self.fails("agent", "catalog", "plan")
        self.assertIn("--all", err)

    def test_plan_unknown_name_refuses(self):
        err = self.fails("agent", "catalog", "plan", "aos.nonexistent")
        self.assertIn("aos.nonexistent", err)

    def test_plan_is_deterministic(self):
        out1 = self.ok("agent", "catalog", "plan", "--all")
        out2 = self.ok("agent", "catalog", "plan", "--all")
        self.assertEqual(out1, out2)

    def test_zero_mutation_for_every_wave_1_command(self):
        before = _table_snapshot(self.query)
        self.ok("agent", "catalog", "list")
        self.ok("agent", "catalog", "show", "aos.architect")
        self.ok("agent", "catalog", "verify")
        self.ok("agent", "catalog", "status")
        self.ok("agent", "catalog", "plan", "--all")
        self.ok("agent", "catalog", "plan", "aos.architect", "aos.debugger")
        after = _table_snapshot(self.query)
        self.assertEqual(before, after)

    def test_schema_stays_version_four(self):
        self.ok("agent", "catalog", "status")
        self.ok("agent", "catalog", "plan", "--all")
        self.assertEqual(
            self.query("SELECT value FROM meta WHERE key='schema_version'")[0][0], "4"
        )


# ---------------------------------------------------------------------------
# (7) The read-only state model: not_installed / installed / upgradable /
# blocked / diverged / tampered — each reached exactly as a later wave's
# `install` would produce it, via direct SQL (there is no installer yet).

class StateModelTests(V4WorkspaceTestCase):
    def _insert_row(
        self,
        name,
        *,
        owner,
        agent_class,
        protected,
        lifecycle,
        origin,
        document_text,
        version=1,
        current_version: int | None = 1,
        status="published",
    ):
        now = "2026-07-17T00:00:00Z"
        conn = db.connect(self.db_path)
        try:
            with conn:
                cur = conn.execute(
                    "INSERT INTO agents (name, agent_class, scope, project_id, lifecycle, "
                    "protected, owner, origin, current_passport_version, created_at, "
                    "updated_at, content_sha256) VALUES (?,?,?,?,?,?,?,?,NULL,?,?,'')",
                    (name, agent_class, "global", None, lifecycle, protected, owner, origin, now, now),
                )
                agent_id = cur.lastrowid
                assert agent_id is not None
                pcur = conn.execute(
                    "INSERT INTO agent_passports (agent_id, version, status, created_at, "
                    "published_at, document, content_sha256) VALUES (?,?,?,?,?,?,'')",
                    (agent_id, version, status, now, now if status == "published" else None, document_text),
                )
                passport_id = pcur.lastrowid
                assert passport_id is not None
            with conn:
                passports._rehash_passport(conn, passport_id)
                if current_version is not None:
                    conn.execute(
                        "UPDATE agents SET current_passport_version=? WHERE id=?",
                        (current_version, agent_id),
                    )
                passports._rehash_agent(conn, agent_id)
        finally:
            conn.close()
        return agent_id

    @staticmethod
    def _document_text(name: str) -> str:
        entry = catalog.catalog().get(name)
        _document, text = catalog.load_document(entry, entry.latest)
        return text.rstrip("\n")

    def _state(self, agent_or_entry):
        entry = (
            agent_or_entry
            if not isinstance(agent_or_entry, str)
            else catalog.catalog().get(agent_or_entry)
        )
        conn = db.connect(self.db_path)
        try:
            return catalog.installed_state(conn, entry)
        finally:
            conn.close()

    def test_not_installed_when_no_row_exists(self):
        state = self._state("aos.architect")
        self.assertEqual(state["state"], "not_installed")
        self.assertIsNone(state["installed_version"])
        self.assertEqual(state["available_version"], 1)

    def test_installed_when_digest_and_version_match(self):
        self._insert_row(
            "aos.architect",
            owner="system",
            agent_class="specialist",
            protected=1,
            lifecycle="active",
            origin="import",
            document_text=self._document_text("aos.architect"),
        )
        state = self._state("aos.architect")
        self.assertEqual(state["state"], "installed")
        self.assertEqual(state["installed_version"], 1)
        self.assertEqual(state["available_version"], 1)
        self.assertIsNone(state["detail"])

    def test_upgradable_with_a_synthetic_v2_catalog_entry(self):
        # Proves the state model needs no change to the shipped catalog to
        # exercise "upgradable": a hand-built CatalogEntry stands in for a
        # future v2 without touching agentic_os/catalog/ at all.
        self._insert_row(
            "aos.architect",
            owner="system",
            agent_class="specialist",
            protected=1,
            lifecycle="active",
            origin="import",
            document_text=self._document_text("aos.architect"),
        )
        real_v1 = catalog.catalog().get("aos.architect").latest
        synthetic_v2 = catalog.CatalogVersion(
            passport_version=2, path="aos.architect.v2.passport.json", document_sha256="0" * 64
        )
        synthetic_entry = catalog.CatalogEntry(
            agent="aos.architect",
            category="design",
            maturity="stable",
            versions=(real_v1, synthetic_v2),
        )
        state = self._state(synthetic_entry)
        self.assertEqual(state["state"], "upgradable")
        self.assertEqual(state["installed_version"], 1)
        self.assertEqual(state["available_version"], 2)

    def test_blocked_on_a_legacy_name_collision(self):
        self._insert_row(
            "aos.planner",
            owner="human",
            agent_class="custom",
            protected=0,
            lifecycle="draft",
            origin="legacy",
            document_text="{}",
            current_version=None,
            status="draft",
        )
        state = self._state("aos.planner")
        self.assertEqual(state["state"], "blocked")
        self.assertIn("legacy", state["detail"])

    def test_diverged_on_hand_edited_shared_version(self):
        text = self._document_text("aos.builder")
        document = protocols.parse_canonical(text.encode("utf-8"))
        document["mission"] = document["mission"] + " (hand-edited, diverging from the catalog)"
        bad_text = protocols.serialize_canonical(_seal(document)).decode("utf-8")
        self._insert_row(
            "aos.builder",
            owner="system",
            agent_class="specialist",
            protected=1,
            lifecycle="active",
            origin="import",
            document_text=bad_text,
        )
        state = self._state("aos.builder")
        self.assertEqual(state["state"], "diverged")
        self.assertEqual(state["installed_version"], 1)

    def test_tampered_on_identity_hash_tamper(self):
        self._insert_row(
            "aos.debugger",
            owner="system",
            agent_class="specialist",
            protected=1,
            lifecycle="active",
            origin="import",
            document_text=self._document_text("aos.debugger"),
        )
        self.execute(
            "UPDATE agents SET content_sha256 = 'deadbeef' || content_sha256 "
            "WHERE name='aos.debugger'"
        )
        state = self._state("aos.debugger")
        self.assertEqual(state["state"], "tampered")

    def test_tampered_on_lifecycle_tamper(self):
        self._insert_row(
            "aos.verifier",
            owner="system",
            agent_class="specialist",
            protected=1,
            lifecycle="active",
            origin="import",
            document_text=self._document_text("aos.verifier"),
        )
        self.execute("UPDATE agents SET lifecycle='suspended' WHERE name='aos.verifier'")
        state = self._state("aos.verifier")
        self.assertEqual(state["state"], "tampered")

    def test_tampered_on_incoherent_but_correctly_rehashed_provenance(self):
        # Flips `protected` to 0 and REHASHES, so the identity hash stays
        # 'ok' — proving the coherence branch, not the hash-mismatch
        # branch, is what catches this class of corruption.
        self._insert_row(
            "aos.curator",
            owner="system",
            agent_class="specialist",
            protected=1,
            lifecycle="active",
            origin="import",
            document_text=self._document_text("aos.curator"),
        )
        conn = db.connect(self.db_path)
        try:
            with conn:
                conn.execute("UPDATE agents SET protected=0 WHERE name='aos.curator'")
                agent_id = conn.execute(
                    "SELECT id FROM agents WHERE name='aos.curator'"
                ).fetchone()[0]
                passports._rehash_agent(conn, agent_id)
        finally:
            conn.close()
        state = self._state("aos.curator")
        self.assertEqual(state["state"], "tampered")
        self.assertEqual(state["detail"], "provenance incoherent")

    def test_tampered_when_no_published_passport_exists(self):
        self._insert_row(
            "aos.researcher",
            owner="system",
            agent_class="specialist",
            protected=1,
            lifecycle="active",
            origin="import",
            document_text=self._document_text("aos.researcher"),
        )
        # Null the pointer FIRST: leaving it at 1 would make history_problems
        # report 'pointer_invalid' (pointing at a version that no longer
        # exists) before ever reaching the dedicated no-published-passport
        # branch this test targets.
        self.execute("UPDATE agents SET current_passport_version=NULL WHERE name='aos.researcher'")
        self.execute("DELETE FROM agent_passports")
        conn = db.connect(self.db_path)
        try:
            with conn:
                agent_id = conn.execute(
                    "SELECT id FROM agents WHERE name='aos.researcher'"
                ).fetchone()[0]
                passports._rehash_agent(conn, agent_id)
        finally:
            conn.close()
        state = self._state("aos.researcher")
        self.assertEqual(state["state"], "tampered")
        self.assertEqual(state["detail"], "no published passport")

    def test_installed_state_and_status_never_modify_a_row(self):
        self._insert_row(
            "aos.curator",
            owner="system",
            agent_class="specialist",
            protected=1,
            lifecycle="active",
            origin="import",
            document_text=self._document_text("aos.curator"),
        )
        before = _table_snapshot(self.query)
        conn = db.connect(self.db_path)
        try:
            catalog.status(conn)
            for entry in catalog.catalog().entries:
                catalog.installed_state(conn, entry)
        finally:
            conn.close()
        after = _table_snapshot(self.query)
        self.assertEqual(before, after)


# ---------------------------------------------------------------------------
# (8) Power classification and recovery access

class PowerCoverageTests(unittest.TestCase):
    CATALOG_LEAVES = (
        ("agent", "catalog", "list"),
        ("agent", "catalog", "show"),
        ("agent", "catalog", "verify"),
        ("agent", "catalog", "status"),
        ("agent", "catalog", "plan"),
    )
    INSTALL_LEAF = ("agent", "catalog", "install")

    def test_all_five_leaves_classified_read_only(self):
        for path in self.CATALOG_LEAVES:
            with self.subTest(path=path):
                self.assertEqual(power.COMMAND_POLICY[path].kind, power.READ_ONLY)
                self.assertFalse(power.COMMAND_POLICY[path].ledger)

    def test_all_five_leaves_are_recovery_allowed(self):
        for path in self.CATALOG_LEAVES:
            with self.subTest(path=path):
                self.assertIn(power.COMMAND_POLICY[path].kind, power.RECOVERY_ALLOWED_KINDS)

    def test_all_five_leaves_appear_in_the_live_parser(self):
        leaves = set(power.iter_command_paths(cli.build_parser()))
        for path in self.CATALOG_LEAVES:
            with self.subTest(path=path):
                self.assertIn(path, leaves)

    def test_install_is_the_authoritative_write_leaf(self):
        policy = power.COMMAND_POLICY[self.INSTALL_LEAF]
        self.assertEqual(policy.kind, power.AUTHORITATIVE_WRITE)
        self.assertTrue(policy.ledger)

    def test_install_is_the_only_catalog_leaf_that_is_not_recovery_allowed(self):
        self.assertNotIn(
            power.COMMAND_POLICY[self.INSTALL_LEAF].kind, power.RECOVERY_ALLOWED_KINDS
        )

    def test_install_leaf_appears_in_the_live_parser(self):
        leaves = set(power.iter_command_paths(cli.build_parser()))
        self.assertIn(self.INSTALL_LEAF, leaves)

    def test_the_catalog_ships_exactly_six_leaves(self):
        leaves = [
            path
            for path in power.iter_command_paths(cli.build_parser())
            if path[:2] == ("agent", "catalog")
        ]
        self.assertEqual(
            set(leaves), set(self.CATALOG_LEAVES) | {self.INSTALL_LEAF}
        )


class RecoveryAccessTests(V4WorkspaceTestCase):
    LEAVES = (
        ("agent", "catalog", "list"),
        ("agent", "catalog", "show", "aos.architect"),
        ("agent", "catalog", "verify"),
        ("agent", "catalog", "status"),
        ("agent", "catalog", "plan", "--all"),
    )

    def test_all_five_leaves_usable_in_recovery(self):
        self.ok("power", "set", "recovery")
        for argv in self.LEAVES:
            with self.subTest(argv=argv):
                code, _out, err = self.aos(*argv)
                self.assertEqual(code, 0, err)

    def test_zero_mutation_under_recovery(self):
        self.ok("power", "set", "recovery")
        before = _table_snapshot(self.query)
        for argv in self.LEAVES:
            self.aos(*argv)
        after = _table_snapshot(self.query)
        self.assertEqual(before, after)


# ---------------------------------------------------------------------------
# (10) Wave 2: installation, upgrade, refusal, rollback, events, modes.
#
# Every test below runs against a disposable temp workspace. The shipped
# catalog under agentic_os/catalog/ is never edited: "future v2" is a
# synthetic catalog served from a throwaway temp root (synthetic_catalog).

def _stub_v2(agent: str = "aos.stub") -> dict:
    """A v2 that differs from _stub_document(agent, 1) in body as well as
    version, so the two carry genuinely different digests."""
    return _stub_document(
        agent,
        2,
        mission="Second mission, revised for v2, long enough to be plausible prose.",
    )


class InstallTests(V4WorkspaceTestCase):
    def _agents(self) -> list[str]:
        return [r["name"] for r in self.query("SELECT name FROM agents ORDER BY name")]

    def _catalog_events(self) -> list[dict]:
        return [
            dict(r)
            for r in self.query(
                "SELECT * FROM events WHERE action IN "
                "('catalog_install','catalog_upgrade') ORDER BY id"
            )
        ]

    def test_install_one_entry(self):
        out = self.ok("agent", "catalog", "install", "aos.architect")
        self.assertIn("Installed 1 agent(s), upgraded 0, unchanged 0 (catalog v1).", out)
        self.assertEqual(self._agents(), ["aos.architect"])

    def test_install_multiple_explicit_entries(self):
        self.ok("agent", "catalog", "install", "aos.architect", "aos.builder")
        self.assertEqual(self._agents(), ["aos.architect", "aos.builder"])

    def test_install_all(self):
        out = self.ok("agent", "catalog", "install", "--all")
        self.assertIn("Installed 12 agent(s)", out)
        self.assertEqual(self._agents(), sorted(CATALOG_NAMES))

    def test_execution_follows_manifest_order_not_cli_argument_order(self):
        # Reversed on the command line; the rows, the ids and the events must
        # still land in manifest order (U-A2 §7: manifest order IS install
        # order, and a human's typing is not a fact about the catalog).
        manifest_order = [
            e.agent
            for e in catalog.catalog().entries
            if e.agent in {"aos.architect", "aos.builder", "aos.verifier"}
        ]
        self.ok(
            "agent", "catalog", "install",
            *reversed(manifest_order),
        )
        by_id = [
            r["name"] for r in self.query("SELECT name FROM agents ORDER BY id")
        ]
        self.assertEqual(by_id, manifest_order)
        self.assertEqual(
            [json.loads(e["payload_json"])["agent"] for e in self._catalog_events()],
            manifest_order,
        )

    def test_duplicate_explicit_names_produce_one_identity(self):
        out = self.ok(
            "agent", "catalog", "install",
            "aos.architect", "aos.architect", "aos.architect",
        )
        self.assertIn("Installed 1 agent(s)", out)
        self.assertEqual(self._agents(), ["aos.architect"])
        self.assertEqual(len(self._catalog_events()), 1)

    def test_same_version_reinstall_is_a_true_no_op(self):
        self.ok("agent", "catalog", "install", "--all")
        out = self.ok("agent", "catalog", "install", "--all")
        self.assertEqual(
            out.strip(),
            "Nothing to do: 12 entry(ies) already installed at catalog v1.",
        )

    def test_no_op_changes_no_row_no_event_and_no_updated_at(self):
        self.ok("agent", "catalog", "install", "--all")
        before = _table_snapshot(self.query)
        self.ok("agent", "catalog", "install", "--all")
        self.ok("agent", "catalog", "install", "aos.architect")
        self.assertEqual(_table_snapshot(self.query), before)

    def test_no_op_opens_no_transaction(self):
        # The §9 promise is stronger than "no net change": a no-op must not
        # open a transaction at all. Proven by making db.transaction explode.
        self.ok("agent", "catalog", "install", "--all")
        conn = db.connect(self.db_path)
        try:
            def _boom(_conn):
                raise AssertionError("a true no-op must not open a transaction")

            with mock.patch.object(catalog.db, "transaction", _boom):
                result = catalog.install(conn, None)
        finally:
            conn.close()
        self.assertFalse(result["changed"])
        self.assertEqual(result["unchanged"], 12)

    def test_fresh_install_row_shape(self):
        self.ok("agent", "catalog", "install", "aos.architect")
        row = self.query("SELECT * FROM agents WHERE name='aos.architect'")[0]
        self.assertEqual(row["owner"], "system")
        self.assertEqual(row["origin"], "import")
        self.assertEqual(row["protected"], 1)
        self.assertEqual(row["lifecycle"], "active")
        self.assertEqual(row["agent_class"], "specialist")
        self.assertEqual(row["scope"], "global")
        self.assertIsNone(row["project_id"])
        self.assertEqual(row["current_passport_version"], 1)

    def test_fresh_install_publishes_v1_with_valid_hashes(self):
        self.ok("agent", "catalog", "install", "aos.architect")
        conn = db.connect(self.db_path)
        try:
            agent = passports.get_agent(conn, "aos.architect")
            self.assertEqual(passports.agent_integrity(agent), "ok")
            self.assertEqual(passports.history_problems(conn, agent), [])
            history = passports.list_passports(conn, agent.id)
            self.assertEqual([p.version for p in history], [1])
            self.assertEqual(history[0].status, "published")
            self.assertIsNotNone(history[0].published_at)
            self.assertEqual(passports.passport_integrity(history[0]), "ok")
        finally:
            conn.close()

    def test_installed_document_is_byte_identical_to_the_shipped_artifact(self):
        self.ok("agent", "catalog", "install", "aos.architect")
        entry = catalog.catalog().get("aos.architect")
        document, text = catalog.load_document(entry, entry.latest)
        stored = self.query(
            "SELECT document FROM agent_passports ORDER BY id"
        )[0]["document"]
        self.assertEqual(stored, text[:-1])
        self.assertEqual(
            protocols.content_digest(protocols.parse_canonical(stored.encode("utf-8"))),
            entry.latest.document_sha256,
        )

    def test_install_reaches_the_installed_state(self):
        self.ok("agent", "catalog", "install", "--all")
        out = self.ok("agent", "catalog", "status")
        self.assertIn("12 entry(ies): 12 installed", out)

    def test_json_success_shape(self):
        out = self.ok("agent", "catalog", "install", "aos.architect", "--json")
        self.assertEqual(
            json.loads(out),
            {
                "result": {
                    "changed": True,
                    "installed": 1,
                    "upgraded": 0,
                    "unchanged": 0,
                    "catalog_version": 1,
                }
            },
        )

    def test_unknown_catalog_name_refuses(self):
        err = self.fails("agent", "catalog", "install", "aos.not-a-real-entry")
        self.assertIn("No catalog entry", err)
        self.assertEqual(self._agents(), [])

    def test_explicit_names_plus_all_refuses(self):
        err = self.fails("agent", "catalog", "install", "aos.architect", "--all")
        self.assertIn("not both", err)
        self.assertEqual(self._agents(), [])

    def test_no_selection_refuses(self):
        err = self.fails("agent", "catalog", "install")
        self.assertIn("at least one NAME", err)

    def test_schema_stays_4_and_migration_state_is_untouched(self):
        before_meta = [tuple(r) for r in self.query("SELECT * FROM meta ORDER BY key")]
        before_schema = core_schema(self.db_path)
        self.ok("agent", "catalog", "install", "--all")
        self.assertEqual(
            [tuple(r) for r in self.query("SELECT * FROM meta ORDER BY key")],
            before_meta,
        )
        self.assertEqual(core_schema(self.db_path), before_schema)
        conn = db.connect(self.db_path)
        try:
            self.assertEqual(db.get_meta(conn, "schema_version"), "4")
        finally:
            conn.close()

    def test_install_leaves_unrelated_agents_byte_identical(self):
        self.ok("agent", "create", "mybot", "--role", "A human's own agent.")
        self.ok("agent", "passport", "publish", "mybot")
        before = [
            tuple(r) for r in self.query("SELECT * FROM agents WHERE name='mybot'")
        ]
        before_p = [
            tuple(r)
            for r in self.query(
                "SELECT p.* FROM agent_passports p JOIN agents a ON a.id=p.agent_id "
                "WHERE a.name='mybot'"
            )
        ]
        self.ok("agent", "catalog", "install", "--all")
        self.assertEqual(
            [tuple(r) for r in self.query("SELECT * FROM agents WHERE name='mybot'")],
            before,
        )
        self.assertEqual(
            [
                tuple(r)
                for r in self.query(
                    "SELECT p.* FROM agent_passports p JOIN agents a ON a.id=p.agent_id "
                    "WHERE a.name='mybot'"
                )
            ],
            before_p,
        )


class UpgradeTests(V4WorkspaceTestCase):
    """Append-only upgrades, proven against a SYNTHETIC v2 catalog — the
    shipped catalog ships one version per entry at this unit's ship date, and
    no test here edits it."""

    AGENT = "aos.stub"

    def setUp(self):
        super().setUp()
        self.v1 = _stub_document(self.AGENT, 1)
        self.v2 = _stub_v2(self.AGENT)
        _m1, self.files_v1 = _stub_catalog(
            [(self.AGENT, "design", "stable", [self.v1])]
        )
        _m2, self.files_v2 = _stub_catalog(
            [(self.AGENT, "design", "stable", [self.v1, self.v2])]
        )

    def _install(self, files, *argv):
        with synthetic_catalog(files):
            return self.ok("agent", "catalog", "install", *argv)

    def _passport_rows(self):
        return [
            tuple(r)
            for r in self.query("SELECT * FROM agent_passports ORDER BY version")
        ]

    def test_synthetic_v2_catalog_appends_v2(self):
        self._install(self.files_v1, self.AGENT)
        out = self._install(self.files_v2, self.AGENT)
        self.assertIn("Installed 0 agent(s), upgraded 1", out)
        self.assertEqual(
            [r["version"] for r in self.query(
                "SELECT version FROM agent_passports ORDER BY version"
            )],
            [1, 2],
        )

    def test_existing_v1_row_is_byte_identical_after_upgrade(self):
        self._install(self.files_v1, self.AGENT)
        before_v1 = self._passport_rows()[0]
        self._install(self.files_v2, self.AGENT)
        self.assertEqual(self._passport_rows()[0], before_v1)

    def test_pointer_advances_to_v2_and_v2_is_published(self):
        self._install(self.files_v1, self.AGENT)
        self._install(self.files_v2, self.AGENT)
        agent_row = self.query("SELECT * FROM agents")[0]
        self.assertEqual(agent_row["current_passport_version"], 2)
        v2_row = self.query("SELECT * FROM agent_passports WHERE version=2")[0]
        self.assertEqual(v2_row["status"], "published")
        self.assertIsNotNone(v2_row["published_at"])

    def test_upgrade_preserves_protection_and_ownership(self):
        # A protected, active catalog identity upgrades THROUGH the catalog
        # path — protection refuses lifecycle verbs, never the catalog's own
        # append.
        self._install(self.files_v1, self.AGENT)
        self._install(self.files_v2, self.AGENT)
        row = self.query("SELECT * FROM agents")[0]
        self.assertEqual(row["protected"], 1)
        self.assertEqual(row["owner"], "system")
        self.assertEqual(row["lifecycle"], "active")
        self.assertEqual(row["agent_class"], "specialist")

    def test_upgrade_rehashes_identity_and_new_row_only(self):
        self._install(self.files_v1, self.AGENT)
        self._install(self.files_v2, self.AGENT)
        conn = db.connect(self.db_path)
        try:
            agent = passports.get_agent(conn, self.AGENT)
            self.assertEqual(passports.agent_integrity(agent), "ok")
            self.assertEqual(passports.history_problems(conn, agent), [])
        finally:
            conn.close()

    def test_catalog_upgrade_event_records_from_version_1_and_version_2(self):
        self._install(self.files_v1, self.AGENT)
        self._install(self.files_v2, self.AGENT)
        events = self.query(
            "SELECT * FROM events WHERE action='catalog_upgrade' ORDER BY id"
        )
        self.assertEqual(len(events), 1)
        payload = json.loads(events[0]["payload_json"])
        self.assertEqual(payload["from_version"], 1)
        self.assertEqual(payload["version"], 2)
        self.assertEqual(payload["from_lifecycle"], "active")
        self.assertEqual(payload["to_lifecycle"], "active")
        self.assertEqual(payload["result"], "upgraded")

    def test_fresh_install_of_a_v2_catalog_materializes_the_whole_history(self):
        # D-v0.4.17: a fresh install and an upgrade chain converge on
        # byte-identical documents and identical version numbers.
        self._install(self.files_v2, self.AGENT)
        self.assertEqual(
            [
                (r["version"], r["status"], r["document"])
                for r in self.query("SELECT * FROM agent_passports ORDER BY version")
            ],
            [
                (1, "published", protocols.serialize_canonical(self.v1).decode("utf-8")),
                (2, "published", protocols.serialize_canonical(self.v2).decode("utf-8")),
            ],
        )
        self.assertEqual(
            self.query("SELECT * FROM agents")[0]["current_passport_version"], 2
        )
        self.assertEqual(
            len(self.query("SELECT * FROM events WHERE action='catalog_install'")), 1
        )

    def test_installed_maximum_greater_than_catalog_maximum_refuses(self):
        self._install(self.files_v2, self.AGENT)
        with synthetic_catalog(self.files_v1):
            err = self.fails("agent", "catalog", "install", self.AGENT)
        self.assertIn("diverged", err)
        self.assertIn("Nothing was changed", err)
        self.assertEqual(
            [r["version"] for r in self.query(
                "SELECT version FROM agent_passports ORDER BY version"
            )],
            [1, 2],
        )


class RefusalTests(V4WorkspaceTestCase):
    """Every predictable refusal costs ZERO writes (D-v0.4.18): each test
    asserts the refusal AND a byte-identical database."""

    def _insert_row(self, name, **kwargs):
        return StateModelTests._insert_row(self, name, **kwargs)

    @staticmethod
    def _document_text(name: str) -> str:
        entry = catalog.catalog().get(name)
        _document, text = catalog.load_document(entry, entry.latest)
        return text.rstrip("\n")

    def _install_system_row(self, name, **overrides):
        kwargs = dict(
            owner="system",
            agent_class="specialist",
            protected=1,
            lifecycle="active",
            origin="import",
            document_text=self._document_text(name),
        )
        kwargs.update(overrides)
        return self._insert_row(name, **kwargs)

    def _refuses_without_mutation(self, *argv):
        before = _table_snapshot(self.query)
        err = self.fails(*argv)
        self.assertEqual(_table_snapshot(self.query), before)
        self.assertIn("Nothing was changed", err)
        return err

    def test_human_collision_refuses(self):
        self.ok("agent", "create", "mybot", "--role", "x")
        self._insert_row(
            "aos.planner",
            owner="human",
            agent_class="custom",
            protected=0,
            lifecycle="active",
            origin="create",
            document_text="{}",
        )
        err = self._refuses_without_mutation("agent", "catalog", "install", "aos.planner")
        self.assertIn("aos.planner", err)
        self.assertIn("blocked", err)

    def test_imported_human_collision_refuses(self):
        self._insert_row(
            "aos.planner",
            owner="human",
            agent_class="specialist",
            protected=0,
            lifecycle="active",
            origin="import",
            document_text="{}",
        )
        err = self._refuses_without_mutation("agent", "catalog", "install", "aos.planner")
        self.assertIn("blocked", err)

    def test_legacy_collision_is_blocked_never_adopted(self):
        self._insert_row(
            "aos.planner",
            owner="human",
            agent_class="custom",
            protected=0,
            lifecycle="draft",
            origin="legacy",
            document_text="{}",
            current_version=None,
            status="draft",
        )
        err = self._refuses_without_mutation("agent", "catalog", "install", "aos.planner")
        self.assertIn("blocked", err)
        # Never adopted: still human-owned, still legacy, still unprotected.
        row = self.query("SELECT * FROM agents WHERE name='aos.planner'")[0]
        self.assertEqual(row["owner"], "human")
        self.assertEqual(row["origin"], "legacy")
        self.assertEqual(row["protected"], 0)

    def test_divergent_shared_digest_refuses(self):
        text = self._document_text("aos.builder")
        document = protocols.parse_canonical(text.encode("utf-8"))
        document["mission"] = document["mission"] + " (hand-edited, diverging)"
        self._install_system_row(
            "aos.builder",
            document_text=protocols.serialize_canonical(_seal(document)).decode("utf-8"),
        )
        err = self._refuses_without_mutation("agent", "catalog", "install", "aos.builder")
        self.assertIn("diverged", err)

    def test_tampered_identity_hash_refuses(self):
        self._install_system_row("aos.debugger")
        self.execute(
            "UPDATE agents SET content_sha256='deadbeef' || content_sha256 "
            "WHERE name='aos.debugger'"
        )
        err = self._refuses_without_mutation("agent", "catalog", "install", "aos.debugger")
        self.assertIn("tampered", err)

    def test_tampered_passport_hash_refuses(self):
        self._install_system_row("aos.debugger")
        self.execute(
            "UPDATE agent_passports SET content_sha256='deadbeef' || content_sha256"
        )
        err = self._refuses_without_mutation("agent", "catalog", "install", "aos.debugger")
        self.assertIn("tampered", err)

    def test_incoherent_pointer_refuses(self):
        # The composite FK already makes a pointer at a MISSING version
        # unstorable, so the reachable incoherence is a pointer at a row that
        # exists but is not a published one. Rehashed afterward, so the
        # pointer check — not the hash check — is what catches it.
        self._install_system_row("aos.curator")
        conn = db.connect(self.db_path)
        try:
            with conn:
                agent_id = conn.execute(
                    "SELECT id FROM agents WHERE name='aos.curator'"
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO agent_passports (agent_id, version, status, "
                    "created_at, published_at, document, content_sha256) "
                    "VALUES (?, 2, 'draft', '2026-07-17T00:00:00Z', NULL, '{}', '')",
                    (agent_id,),
                )
                conn.execute(
                    "UPDATE agents SET current_passport_version=2 WHERE id=?",
                    (agent_id,),
                )
                passports._rehash_agent(conn, agent_id)
        finally:
            conn.close()
        err = self._refuses_without_mutation("agent", "catalog", "install", "aos.curator")
        self.assertIn("tampered", err)

    def test_malformed_hash_value_refuses_without_crashing(self):
        self._install_system_row("aos.reviewer")
        self.execute("UPDATE agents SET content_sha256='not-a-hash' WHERE name='aos.reviewer'")
        err = self._refuses_without_mutation("agent", "catalog", "install", "aos.reviewer")
        self.assertIn("tampered", err)

    def test_blob_stored_value_refuses_without_crashing(self):
        self._install_system_row("aos.reviewer")
        self.execute("UPDATE agent_passports SET document = X'00FF'")
        err = self._refuses_without_mutation("agent", "catalog", "install", "aos.reviewer")
        self.assertIn("tampered", err)

    def test_blob_identity_hash_refuses_without_crashing(self):
        self._install_system_row("aos.reviewer")
        self.execute("UPDATE agents SET content_sha256 = X'00FF' WHERE name='aos.reviewer'")
        err = self._refuses_without_mutation("agent", "catalog", "install", "aos.reviewer")
        self.assertIn("tampered", err)

    def test_suspended_system_identity_refuses_as_tampered(self):
        self._install_system_row("aos.verifier", lifecycle="suspended")
        err = self._refuses_without_mutation("agent", "catalog", "install", "aos.verifier")
        self.assertIn("tampered", err)

    def test_archived_system_identity_refuses_as_tampered(self):
        self._install_system_row("aos.verifier", lifecycle="archived")
        err = self._refuses_without_mutation("agent", "catalog", "install", "aos.verifier")
        self.assertIn("tampered", err)

    def test_revoked_system_identity_refuses_as_tampered(self):
        self._install_system_row("aos.verifier", lifecycle="revoked")
        err = self._refuses_without_mutation("agent", "catalog", "install", "aos.verifier")
        self.assertIn("tampered", err)

    def test_unprotected_system_identity_refuses_as_tampered(self):
        self._install_system_row("aos.verifier", protected=0)
        err = self._refuses_without_mutation("agent", "catalog", "install", "aos.verifier")
        self.assertIn("tampered", err)

    def test_one_refusal_blocks_the_entire_selected_set(self):
        # The whole point of D-v0.4.18: `--all` with ONE bad entry installs
        # NOTHING, rather than eleven-of-twelve.
        self._insert_row(
            "aos.planner",
            owner="human",
            agent_class="custom",
            protected=0,
            lifecycle="active",
            origin="create",
            document_text="{}",
        )
        before = _table_snapshot(self.query)
        err = self.fails("agent", "catalog", "install", "--all")
        self.assertIn("aos.planner", err)
        self.assertIn("refusing the whole request", err)
        self.assertEqual(_table_snapshot(self.query), before)
        self.assertEqual(
            self.query("SELECT COUNT(*) c FROM agents")[0]["c"], 1
        )

    def test_refusal_names_the_entry_and_points_at_status(self):
        self._install_system_row("aos.verifier", lifecycle="suspended")
        err = self.fails("agent", "catalog", "install", "--all")
        self.assertIn("aos.verifier", err)
        self.assertIn("agent catalog status", err)

    def test_a_refusal_carries_no_document_prose_or_full_digest(self):
        self._install_system_row("aos.verifier", lifecycle="suspended")
        err = self.fails("agent", "catalog", "install", "--all")
        entry = catalog.catalog().get("aos.verifier")
        self.assertNotIn(entry.latest.document_sha256, err)
        document, _text = catalog.load_document(entry, entry.latest)
        self.assertNotIn(document["mission"], err)


class RollbackTests(V4WorkspaceTestCase):
    """A failure mid-transaction rolls back EVERY row this operation would
    have written — identities, passports, pointers, hashes and events."""

    class Boom(RuntimeError):
        pass

    def _install_all_failing_after(self, successes: int):
        """Fail deterministically after `successes` entries have already been
        written INSIDE the transaction. A narrow test-only patch at the write
        primitive: production carries no failure-injection hook."""
        real = passports.create_catalog_identity
        calls = {"n": 0}

        def flaky(conn, **kwargs):
            if calls["n"] >= successes:
                raise RollbackTests.Boom("injected mid-transaction failure")
            calls["n"] += 1
            return real(conn, **kwargs)

        conn = db.connect(self.db_path)
        try:
            with mock.patch.object(passports, "create_catalog_identity", flaky):
                with self.assertRaises(RollbackTests.Boom):
                    catalog.install(conn, None)
        finally:
            conn.close()
        return calls["n"]

    def test_failure_after_several_writes_rolls_back_everything(self):
        before = _table_snapshot(self.query)
        written = self._install_all_failing_after(3)
        self.assertEqual(written, 3)  # three entries really were written first
        after = _table_snapshot(self.query)
        self.assertEqual(after, before)
        self.assertEqual(self.query("SELECT COUNT(*) c FROM agents")[0]["c"], 0)
        self.assertEqual(
            self.query("SELECT COUNT(*) c FROM agent_passports")[0]["c"], 0
        )
        self.assertEqual(
            self.query(
                "SELECT COUNT(*) c FROM events WHERE action LIKE 'catalog_%'"
            )[0]["c"],
            0,
        )

    def test_rollback_preserves_a_pre_existing_human_agent(self):
        self.ok("agent", "create", "mybot", "--role", "x")
        self.ok("agent", "passport", "publish", "mybot")
        before = _table_snapshot(self.query)
        self._install_all_failing_after(2)
        self.assertEqual(_table_snapshot(self.query), before)

    def test_corrected_retry_succeeds(self):
        self._install_all_failing_after(3)
        out = self.ok("agent", "catalog", "install", "--all")
        self.assertIn("Installed 12 agent(s)", out)
        self.assertEqual(
            self.query("SELECT COUNT(*) c FROM agents")[0]["c"], 12
        )
        conn = db.connect(self.db_path)
        try:
            for name in CATALOG_NAMES:
                agent = passports.get_agent(conn, name)
                self.assertEqual(passports.agent_integrity(agent), "ok")
                self.assertEqual(passports.history_problems(conn, agent), [])
        finally:
            conn.close()

    def test_in_transaction_state_change_aborts_the_whole_operation(self):
        # The TOCTOU guard (U-A2 §9): a fact established during planning is
        # re-read inside the transaction, and a discrepancy aborts everything.
        real = passports.create_catalog_identity
        state = {"n": 0}

        # Manifest order is code-point order, so the LAST entry is the one
        # still unwritten after the first: planting a collision there makes a
        # planned `install` stop being true before its turn arrives.
        victim = catalog.catalog().entries[-1].agent

        def racing(conn, **kwargs):
            agent = real(conn, **kwargs)
            if state["n"] == 0:
                state["n"] = 1
                conn.execute(
                    "INSERT INTO agents (name, agent_class, scope, project_id, "
                    "lifecycle, protected, owner, origin, "
                    "current_passport_version, created_at, updated_at, "
                    "content_sha256) VALUES (?, 'custom', 'global', NULL, "
                    "'active', 0, 'human', 'create', NULL, ?, ?, 'x')",
                    (victim, "2026-07-17T00:00:00Z", "2026-07-17T00:00:00Z"),
                )
            return agent

        before = _table_snapshot(self.query)
        conn = db.connect(self.db_path)
        try:
            with mock.patch.object(passports, "create_catalog_identity", racing):
                with self.assertRaises(AosError) as caught:
                    catalog.install(conn, None)
        finally:
            conn.close()
        self.assertIn("changed while the install was preparing", str(caught.exception))
        self.assertEqual(_table_snapshot(self.query), before)


class EventPrivacyTests(V4WorkspaceTestCase):
    """U-A2 §14: bounded metadata and 12-char hash prefixes only."""

    #: The EXACT allowed key set. `schema_version` is the envelope every
    #: event in this system carries (events.emit adds it), not a payload
    #: field this unit chose.
    ALLOWED = set(catalog.EVENT_PAYLOAD_KEYS)

    def _payloads(self) -> list[dict]:
        return [
            json.loads(r["payload_json"])
            for r in self.query(
                "SELECT * FROM events WHERE action IN "
                "('catalog_install','catalog_upgrade') ORDER BY id"
            )
        ]

    def test_payload_key_set_matches_the_allowlist_exactly(self):
        self.ok("agent", "catalog", "install", "--all")
        payloads = self._payloads()
        self.assertEqual(len(payloads), 12)
        for payload in payloads:
            with self.subTest(agent=payload["agent"]):
                self.assertEqual(set(payload) - {"schema_version"}, self.ALLOWED)

    def test_event_action_entity_and_actor(self):
        self.ok("agent", "catalog", "install", "aos.architect")
        row = self.query(
            "SELECT * FROM events WHERE action='catalog_install'"
        )[0]
        self.assertEqual(row["entity"], "agent")
        self.assertEqual(row["actor"], "human")
        agent_id = self.query("SELECT id FROM agents WHERE name='aos.architect'")[0]["id"]
        self.assertEqual(row["entity_id"], agent_id)

    def test_hash_prefixes_are_12_lowercase_hex_characters(self):
        self.ok("agent", "catalog", "install", "--all")
        for payload in self._payloads():
            for key in ("manifest_sha256_prefix", "passport_sha256_prefix"):
                with self.subTest(agent=payload["agent"], key=key):
                    self.assertRegex(payload[key], r"^[0-9a-f]{12}\Z")

    def test_no_full_digest_reaches_an_event(self):
        self.ok("agent", "catalog", "install", "--all")
        blob = json.dumps(self._payloads())
        cat = catalog.catalog()
        self.assertNotIn(cat.manifest_sha256, blob)
        for entry in cat.entries:
            for version in entry.versions:
                with self.subTest(agent=entry.agent):
                    self.assertNotIn(version.document_sha256, blob)

    def test_no_passport_prose_or_declaration_fields_reach_an_event(self):
        self.ok("agent", "catalog", "install", "--all")
        blob = json.dumps(self._payloads())
        for entry in catalog.catalog().entries:
            document, _text = catalog.load_document(entry, entry.latest)
            with self.subTest(agent=entry.agent):
                for field in ("role", "mission"):
                    self.assertNotIn(document[field], blob)
                for field in (
                    "task_families",
                    "limitations",
                    "skill_requirements",
                    "tool_requirements",
                    "model_requirements",
                ):
                    for item in document.get(field, ()):
                        self.assertNotIn(item, blob)

    def test_no_path_or_issuer_declaration_reaches_an_event(self):
        self.ok("agent", "catalog", "install", "--all")
        blob = json.dumps(self._payloads())
        for entry in catalog.catalog().entries:
            for version in entry.versions:
                self.assertNotIn(version.path, blob)
        self.assertNotIn(".passport.json", blob)
        self.assertNotIn("declare_only", blob)

    def test_from_version_and_from_lifecycle_are_null_on_fresh_install(self):
        self.ok("agent", "catalog", "install", "--all")
        for payload in self._payloads():
            with self.subTest(agent=payload["agent"]):
                self.assertIsNone(payload["from_version"])
                self.assertIsNone(payload["from_lifecycle"])
                self.assertEqual(payload["to_lifecycle"], "active")
                self.assertEqual(payload["result"], "installed")
                self.assertEqual(payload["version"], 1)
                self.assertEqual(payload["catalog_version"], 1)


class PublishProtectionTests(V4WorkspaceTestCase):
    def test_ordinary_publish_refuses_owner_system_before_reading_the_file(self):
        self.ok("agent", "catalog", "install", "aos.architect")
        # The path does NOT exist: reaching a file-read would raise a
        # different error, so a clean catalog-managed refusal proves the
        # check fires BEFORE the input is read.
        missing = self.root / "nowhere" / "passport.json"
        self.assertFalse(missing.exists())
        err = self.fails(
            "agent", "passport", "publish", "aos.architect", "--file", str(missing)
        )
        self.assertIn("catalog-managed", err)
        self.assertIn("agent catalog show aos.architect --fragment", err)
        self.assertIn("agent create", err)

    def test_ordinary_publish_refusal_reads_no_file_at_all(self):
        self.ok("agent", "catalog", "install", "aos.architect")
        target = self.root / "passport.json"
        target.write_text("{}")
        with mock.patch.object(
            protocols, "read_artifact_bytes", side_effect=AssertionError("read the file")
        ):
            err = self.fails(
                "agent", "passport", "publish", "aos.architect", "--file", str(target)
            )
        self.assertIn("catalog-managed", err)

    def test_publish_refusal_changes_nothing(self):
        self.ok("agent", "catalog", "install", "aos.architect")
        before = _table_snapshot(self.query)
        self.fails(
            "agent", "passport", "publish", "aos.architect",
            "--file", str(self.root / "nope.json"),
        )
        self.assertEqual(_table_snapshot(self.query), before)

    def test_human_owned_publish_from_file_is_unchanged(self):
        self.ok("agent", "create", "mybot", "--role", "A human's own agent.")
        self.ok("agent", "passport", "publish", "mybot")
        document = protocols.parse_canonical(
            self.ok("agent", "export", "mybot").encode("utf-8")
        )
        document["passport_version"] = 2
        document["mission"] = "A revised mission, authored by the human who owns it."
        target = self.root / "v2.json"
        target.write_bytes(protocols.serialize_canonical_file_bytes(_seal(document)))
        self.ok("agent", "passport", "publish", "mybot", "--file", str(target))
        row = self.query("SELECT * FROM agents WHERE name='mybot'")[0]
        self.assertEqual(row["current_passport_version"], 2)
        self.assertEqual(row["owner"], "human")

    def test_human_owned_protected_agent_can_still_publish(self):
        # The boundary is owner=='system', NOT `protected`: a human-owned
        # protected identity keeps publishing exactly as it always has.
        self.ok("agent", "create", "mybot", "--role", "A human's own agent.")
        self.ok("agent", "passport", "publish", "mybot")
        conn = db.connect(self.db_path)
        try:
            with conn:
                agent_id = conn.execute(
                    "SELECT id FROM agents WHERE name='mybot'"
                ).fetchone()[0]
                conn.execute("UPDATE agents SET protected=1 WHERE id=?", (agent_id,))
                passports._rehash_agent(conn, agent_id)
        finally:
            conn.close()
        document = protocols.parse_canonical(
            self.ok("agent", "export", "mybot").encode("utf-8")
        )
        document["passport_version"] = 2
        document["mission"] = "A revised mission, authored by the human who owns it."
        target = self.root / "v2.json"
        target.write_bytes(protocols.serialize_canonical_file_bytes(_seal(document)))
        self.ok("agent", "passport", "publish", "mybot", "--file", str(target))
        self.assertEqual(
            self.query("SELECT * FROM agents WHERE name='mybot'")[0][
                "current_passport_version"
            ],
            2,
        )

    def test_lifecycle_verbs_remain_refused_against_a_catalog_identity(self):
        self.ok("agent", "catalog", "install", "aos.architect")
        before = _table_snapshot(self.query)
        for verb in ("suspend", "archive", "revoke", "discard"):
            with self.subTest(verb=verb):
                err = self.fails("agent", verb, "aos.architect")
                self.assertIn("protected", err)
        self.assertEqual(_table_snapshot(self.query), before)

    def test_agent_create_and_import_still_refuse_the_catalog_namespace(self):
        err = self.fails("agent", "create", "aos.architect")
        self.assertIn("reserved", err)


class ModeTests(V4WorkspaceTestCase):
    def test_recovery_blocks_install_with_a_byte_identical_database(self):
        self.ok("power", "set", "recovery")
        before = _table_snapshot(self.query)
        with mock.patch.object(
            catalog, "install", side_effect=AssertionError("dispatched")
        ):
            code, out, err = self.aos("agent", "catalog", "install", "--all")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")  # recovery leaves stdout empty
        self.assertIn("blocked in recovery mode", err)
        self.assertEqual(_table_snapshot(self.query), before)

    def test_deep_damaged_ledger_preflight_blocks_before_dispatch(self):
        # A secret-shaped value in the ledger is a deep_check hard finding.
        self.ok("agent", "create", "mybot", "--role", FAKE_SECRET)
        self.ok("power", "set", "deep")
        before = _table_snapshot(self.query)
        with mock.patch.object(
            catalog, "install", side_effect=AssertionError("dispatched")
        ):
            code, out, err = self.aos("agent", "catalog", "install", "--all")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("deep mode's preflight", err)
        self.assertIn("before `agent catalog install` wrote anything", err)
        self.assertEqual(_table_snapshot(self.query), before)

    def test_deep_installs_on_a_healthy_ledger(self):
        self.ok("power", "set", "deep")
        out = self.ok("agent", "catalog", "install", "--all")
        self.assertIn("Installed 12 agent(s)", out)

    def test_eco_performs_the_requested_install_immediately(self):
        self.ok("power", "set", "eco")
        out = self.ok("agent", "catalog", "install", "aos.architect")
        self.assertIn("Installed 1 agent(s)", out)
        self.assertEqual(
            self.query("SELECT COUNT(*) c FROM agents")[0]["c"], 1
        )

    def test_no_mode_auto_installs_or_auto_upgrades(self):
        for mode in ("eco", "standard", "deep"):
            with self.subTest(mode=mode):
                self.ok("power", "set", mode)
                for argv in (
                    ("status",),
                    ("doctor",),
                    ("agent", "catalog", "status"),
                    ("agent", "catalog", "plan", "--all"),
                    ("agent", "catalog", "verify"),
                    ("sync",),
                ):
                    self.aos(*argv)
                self.assertEqual(
                    self.query("SELECT COUNT(*) c FROM agents")[0]["c"], 0
                )

    def test_init_never_installs_the_catalog(self):
        fresh = self.root / "fresh"
        (fresh / "x").mkdir(parents=True)
        code, _out, err = run_cli("--root", str(fresh), "init")
        self.assertEqual(code, 0, err)
        conn = db.connect(fresh / ".agentic-os" / "aos.db")
        try:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0], 0
            )
        finally:
            conn.close()


class TransactionOwnershipTests(V4WorkspaceTestCase):
    """The primitives are transaction PARTICIPANTS (D-v0.4.18): they open,
    commit and roll back nothing, and refuse to run outside a caller's
    already-open transaction."""

    def test_create_catalog_identity_refuses_outside_a_transaction(self):
        conn = db.connect(self.db_path)
        try:
            self.assertFalse(conn.in_transaction)
            with self.assertRaises(RuntimeError) as caught:
                passports.create_catalog_identity(
                    conn, name="aos.stub", agent_class="specialist",
                    documents=[(1, "{}")],
                )
        finally:
            conn.close()
        self.assertIn("transaction participant", str(caught.exception))
        self.assertEqual(self.query("SELECT COUNT(*) c FROM agents")[0]["c"], 0)

    def test_append_catalog_version_refuses_outside_a_transaction(self):
        self.ok("agent", "catalog", "install", "aos.architect")
        conn = db.connect(self.db_path)
        try:
            agent = passports.get_agent(conn, "aos.architect")
            with self.assertRaises(RuntimeError) as caught:
                passports.append_catalog_version(
                    conn, agent=agent, version=2, document_text="{}"
                )
        finally:
            conn.close()
        self.assertIn("transaction participant", str(caught.exception))

    def test_install_holds_exactly_one_transaction(self):
        opened = {"n": 0}
        real = catalog.db.transaction

        def counting(conn):
            opened["n"] += 1
            return real(conn)

        conn = db.connect(self.db_path)
        try:
            with mock.patch.object(catalog.db, "transaction", counting):
                catalog.install(conn, None)
        finally:
            conn.close()
        self.assertEqual(opened["n"], 1)
        self.assertEqual(self.query("SELECT COUNT(*) c FROM agents")[0]["c"], 12)

    def test_primitives_emit_no_event(self):
        conn = db.connect(self.db_path)
        try:
            with db.transaction(conn):
                conn.execute("BEGIN IMMEDIATE")
                entry = catalog.catalog().get("aos.architect")
                document, _text = catalog.load_document(entry, entry.latest)
                passports.create_catalog_identity(
                    conn,
                    name="aos.architect",
                    agent_class="specialist",
                    documents=[
                        (1, protocols.serialize_canonical(document).decode("utf-8"))
                    ],
                )
        finally:
            conn.close()
        self.assertEqual(self.query("SELECT COUNT(*) c FROM agents")[0]["c"], 1)
        self.assertEqual(
            self.query("SELECT COUNT(*) c FROM events WHERE action LIKE 'catalog_%'")[0]["c"],
            0,
        )


# ---------------------------------------------------------------------------
# (10) Doctor: checks 35-37 (U-A2 Wave 3). Every check is exercised directly
# via doctor.run_checks (fast, precise) and the end-to-end CLI count/order
# is proven once through `aos doctor` itself.

class DoctorCatalogTests(V4WorkspaceTestCase):
    def _checks(self) -> list[doctor.Check]:
        conn = db.connect(self.db_path)
        try:
            return doctor.run_checks(conn, self.aos_dir)
        finally:
            conn.close()

    def _named(self, name: str) -> doctor.Check:
        for check in self._checks():
            if check.name == name:
                return check
        raise AssertionError(f"no doctor check named {name!r}")

    def test_doctor_emits_exactly_37_checks_with_the_three_catalog_checks_last(self):
        checks = self._checks()
        self.assertEqual(len(checks), 37)
        self.assertEqual(
            [c.name for c in checks[-3:]],
            [
                "built-in catalog verified",
                "installed catalog identities verified",
                "catalog entries available to install",
            ],
        )

    def test_doctor_check_count_matches_the_cli(self):
        out = self.ok("doctor")
        lines = [l for l in out.strip().splitlines() if l]
        self.assertEqual(len(lines), 37)
        self.assertTrue(lines[-3].startswith("[PASS] built-in catalog verified"))
        self.assertTrue(lines[-2].startswith("[PASS] installed catalog identities verified"))
        self.assertTrue(lines[-1].startswith("[PASS] catalog entries available to install"))

    # -- 35: built-in catalog verified -------------------------------------

    def test_35_passes_on_the_real_shipped_catalog(self):
        check = self._named("built-in catalog verified")
        self.assertTrue(check.ok)
        self.assertFalse(check.warn_only)
        self.assertEqual(check.detail, "12 entry(ies), 12 passport(s)")

    def test_35_fails_on_a_manifest_self_digest_mismatch(self):
        _manifest, files = _stub_catalog(
            [("aos.stub", "design", "stable", [_stub_document()])]
        )
        bad_files = dict(files)
        # Corrupts the self-digest without disturbing structure or vocabulary.
        bad_files[catalog.MANIFEST_FILENAME] = bad_files[catalog.MANIFEST_FILENAME].replace(
            b'"catalog_version":1', b'"catalog_version":2'
        )
        with synthetic_catalog(bad_files):
            check = self._named("built-in catalog verified")
        self.assertFalse(check.ok)
        self.assertFalse(check.warn_only)
        self.assertIn("1 problem(s):", check.detail)
        self.assertIn("manifest_digest_mismatch", check.detail)
        # Bounded reason codes only — never artifact text, a path, or a hash.
        self.assertNotIn("aos.stub", check.detail)
        self.assertNotIn("sha256", check.detail)

    def test_35_reports_a_secret_shaped_document_by_reason_code_only(self):
        document = _stub_document(mission="Investigate outages. Token: " + FAKE_SECRET)
        _manifest, files = _stub_catalog(
            [("aos.stub", "design", "stable", [document])]
        )
        with synthetic_catalog(files):
            check = self._named("built-in catalog verified")
        self.assertFalse(check.ok)
        self.assertIn("secret_shaped", check.detail)
        self.assertNotIn(FAKE_SECRET, check.detail)

    def test_35_reports_an_unreferenced_artifact_by_reason_code_only(self):
        _manifest, files = _stub_catalog(
            [("aos.stub", "design", "stable", [_stub_document()])]
        )
        files = dict(files)
        files["aos.extra.v1.passport.json"] = protocols.serialize_canonical_file_bytes(
            _stub_document("aos.extra")
        )
        with synthetic_catalog(files):
            check = self._named("built-in catalog verified")
        self.assertFalse(check.ok)
        self.assertIn("extra_artifact", check.detail)
        self.assertNotIn("aos.extra", check.detail)

    def test_35_never_crashes_doctor_on_an_unexpected_exception(self):
        with mock.patch.object(catalog, "verify", side_effect=RuntimeError("boom")):
            check = self._named("built-in catalog verified")
        self.assertFalse(check.ok)
        self.assertFalse(check.warn_only)
        self.assertNotIn("boom", check.detail)
        self.assertNotIn("RuntimeError", check.detail)

    # -- 36: installed catalog identities verified --------------------------

    def test_36_passes_with_zero_installed(self):
        check = self._named("installed catalog identities verified")
        self.assertTrue(check.ok)
        self.assertFalse(check.warn_only)
        self.assertEqual(check.detail, "0 installed")

    def test_36_passes_when_the_full_catalog_is_validly_installed(self):
        self.ok("agent", "catalog", "install", "--all")
        check = self._named("installed catalog identities verified")
        self.assertTrue(check.ok)
        self.assertEqual(check.detail, "12 installed")

    def test_36_fails_on_a_tampered_installed_identity(self):
        self.ok("agent", "catalog", "install", "aos.architect")
        self.execute("UPDATE agents SET lifecycle='suspended' WHERE name='aos.architect'")
        check = self._named("installed catalog identities verified")
        self.assertFalse(check.ok)
        self.assertFalse(check.warn_only)
        self.assertIn("1 problem(s):", check.detail)
        self.assertIn("aos.architect (tampered)", check.detail)

    def test_36_fails_on_a_diverged_installed_identity(self):
        # Diverged is a SELF-CONSISTENT installed history that simply does
        # not match the catalog — as opposed to tampered (an internally
        # broken row hash) — so the edited row must be REHASHED afterward,
        # exactly like StateModelTests.test_diverged_on_hand_edited_shared_version.
        self.ok("agent", "catalog", "install", "aos.builder")
        document = protocols.parse_canonical(
            self.query("SELECT document FROM agent_passports")[0]["document"].encode("utf-8")
        )
        document["mission"] = document["mission"] + " (diverged, hand-edited)"
        bad_text = protocols.serialize_canonical(_seal(document)).decode("utf-8")
        conn = db.connect(self.db_path)
        try:
            with conn:
                agent_id = conn.execute(
                    "SELECT id FROM agents WHERE name='aos.builder'"
                ).fetchone()[0]
                passport_id = conn.execute(
                    "SELECT id FROM agent_passports WHERE agent_id=?", (agent_id,)
                ).fetchone()[0]
                conn.execute(
                    "UPDATE agent_passports SET document=? WHERE id=?",
                    (bad_text, passport_id),
                )
            with conn:
                passports._rehash_passport(conn, passport_id)
                passports._rehash_agent(conn, agent_id)
        finally:
            conn.close()
        check = self._named("installed catalog identities verified")
        self.assertFalse(check.ok)
        self.assertIn("aos.builder (diverged)", check.detail)

    def test_36_does_not_fail_on_a_blocked_collision(self):
        # A name collision belongs to check 37, never 36 — it is not a
        # system-owned row at all.
        now = "2026-07-17T00:00:00Z"
        conn = db.connect(self.db_path)
        try:
            with conn:
                conn.execute(
                    "INSERT INTO agents (name, agent_class, scope, project_id, lifecycle, "
                    "protected, owner, origin, current_passport_version, created_at, "
                    "updated_at, content_sha256) VALUES (?,?,?,?,?,?,?,?,NULL,?,?,'')",
                    ("aos.planner", "custom", "global", None, "draft", 0, "human", "legacy",
                     now, now),
                )
        finally:
            conn.close()
        check = self._named("installed catalog identities verified")
        self.assertTrue(check.ok)
        self.assertEqual(check.detail, "0 installed")

    def test_36_output_is_bounded_when_many_identities_are_tampered(self):
        self.ok("agent", "catalog", "install", "--all")
        self.execute("UPDATE agents SET lifecycle='suspended' WHERE owner='system'")
        check = self._named("installed catalog identities verified")
        self.assertFalse(check.ok)
        self.assertIn("12 problem(s):", check.detail)
        shown = check.detail.count("(tampered)")
        self.assertEqual(shown, doctor.UH2_DISPLAY_LIMIT)
        self.assertIn(f"+{12 - doctor.UH2_DISPLAY_LIMIT} more", check.detail)

    def test_36_never_crashes_doctor_on_an_unexpected_exception(self):
        with mock.patch.object(catalog, "status", side_effect=RuntimeError("boom")):
            check = self._named("installed catalog identities verified")
        self.assertFalse(check.ok)
        self.assertFalse(check.warn_only)
        self.assertNotIn("boom", check.detail)

    # -- 37: catalog entries available to install ----------------------------

    def test_37_passes_silently_on_a_fresh_uninstalled_workspace(self):
        check = self._named("catalog entries available to install")
        self.assertTrue(check.ok)
        self.assertTrue(check.warn_only)
        self.assertEqual(check.detail, "no actionable catalog upgrades or collisions")

    def test_37_passes_silently_on_a_fully_installed_catalog(self):
        self.ok("agent", "catalog", "install", "--all")
        check = self._named("catalog entries available to install")
        self.assertTrue(check.ok)
        self.assertTrue(check.warn_only)

    def test_37_warns_on_a_legacy_name_collision(self):
        now = "2026-07-17T00:00:00Z"
        conn = db.connect(self.db_path)
        try:
            with conn:
                conn.execute(
                    "INSERT INTO agents (name, agent_class, scope, project_id, lifecycle, "
                    "protected, owner, origin, current_passport_version, created_at, "
                    "updated_at, content_sha256) VALUES (?,?,?,?,?,?,?,?,NULL,?,?,'')",
                    ("aos.planner", "custom", "global", None, "draft", 0, "human", "legacy",
                     now, now),
                )
        finally:
            conn.close()
        check = self._named("catalog entries available to install")
        self.assertFalse(check.ok)
        self.assertTrue(check.warn_only)
        self.assertIn("aos.planner (blocked)", check.detail)

    def test_37_warns_on_an_upgradable_entry(self):
        agent = "aos.stub"
        v1 = _stub_document(agent, 1)
        v2 = _stub_v2(agent)
        _m1, files_v1 = _stub_catalog([(agent, "design", "stable", [v1])])
        _m2, files_v2 = _stub_catalog([(agent, "design", "stable", [v1, v2])])
        with synthetic_catalog(files_v1):
            self.ok("agent", "catalog", "install", agent)
        with synthetic_catalog(files_v2):
            check = self._named("catalog entries available to install")
        self.assertFalse(check.ok)
        self.assertTrue(check.warn_only)
        self.assertIn(f"{agent} (upgradable)", check.detail)

    def test_37_never_fires_merely_because_the_catalog_was_never_installed(self):
        # All twelve entries absent must stay a healthy, silent workspace —
        # never a warning just for not having run `agent catalog install`.
        check = self._named("catalog entries available to install")
        self.assertTrue(check.ok)

    def test_37_never_crashes_doctor_on_an_unexpected_exception(self):
        with mock.patch.object(catalog, "status", side_effect=RuntimeError("boom")):
            check = self._named("catalog entries available to install")
        self.assertFalse(check.ok)
        self.assertTrue(check.warn_only)
        self.assertNotIn("boom", check.detail)

    # -- doctor never mutates -------------------------------------------------

    def test_doctor_never_mutates_the_database(self):
        # Tampered on purpose (doctor must legitimately FAIL check 36 here);
        # the point is the row snapshot, not the exit code.
        self.ok("agent", "catalog", "install", "aos.architect")
        self.execute("UPDATE agents SET lifecycle='suspended' WHERE name='aos.architect'")
        before = _table_snapshot(self.query)
        code, _out, _err = self.aos("doctor")
        self.assertEqual(code, 1)
        after = _table_snapshot(self.query)
        self.assertEqual(before, after)

    def test_doctor_never_auto_installs_or_upgrades_the_catalog(self):
        self._checks()
        self.assertEqual(self.query("SELECT COUNT(*) c FROM agents")[0]["c"], 0)


# ---------------------------------------------------------------------------
# (9) Source hygiene: no network, subprocess, or dynamic execution.

class SourceHygieneTests(unittest.TestCase):
    # Token strings to search FOR (negatively) in the target source files —
    # these are never called here; assertNotIn only checks the token is
    # absent from agentic_os/catalog.py and tools/gen_catalog.py themselves.
    FORBIDDEN = (
        "subprocess",
        "socket.",
        "urlopen",
        "urllib.request",
        "os.system",
        "os.popen",
        "eval(",
        "exec(",
        "__import__(",
    )

    def test_catalog_module_has_no_network_subprocess_or_dynamic_exec(self):
        source = (REPO_ROOT / "agentic_os" / "catalog.py").read_text()
        for token in self.FORBIDDEN:
            with self.subTest(token=token):
                self.assertNotIn(token, source)

    def test_gen_catalog_tool_has_no_network_subprocess_or_ledger_access(self):
        source = (REPO_ROOT / "tools" / "gen_catalog.py").read_text()
        for token in self.FORBIDDEN + ("sqlite3", "agentic_os.db", "agentic_os import db"):
            with self.subTest(token=token):
                self.assertNotIn(token, source)


# ---------------------------------------------------------------------------
# (11) Four-entrypoint parity + packaged-install smoke (U-A2 Wave 3)

class EntrypointParityTests(unittest.TestCase):
    """`agent catalog list/verify/show --document` and `doctor` produce
    byte-identical stdout/exit codes across script, module, console-script,
    and zipapp — and the zipapp can install one identity from its embedded
    resources. Never touches the real primary ledger; every workspace here
    is a disposable temp directory built fresh per test.

    This sandboxed environment has no `pip` executable, no `ensurepip`
    module, and no `wheel` package installed, and has no network access to
    fetch any of them (verified directly: `python3 -m pip` -> "No module
    named pip"; `python3 -m ensurepip` -> "No module named ensurepip";
    `import wheel` -> ModuleNotFoundError; setuptools is 68.1.2, which has
    no built-in `bdist_wheel`). A real `pip install` of a built wheel
    therefore cannot be exercised here — see the Wave 3 report for this
    exact blocker, reported rather than worked around per instruction.

    The "console_script" leg below is the closest offline-safe proxy: it
    invokes the EXACT function pyproject.toml's `aos = agentic_os.cli:main`
    names — proven identical to the canonical CLI object by
    test_v02_packaging.py's PyprojectTests.test_console_script_points_at_the_canonical_cli
    — through a one-line shim, with the checkout on PYTHONPATH exactly as a
    real console script's import machinery would resolve it. It is a
    faithful behavioral proxy for the entry point's own code path, not a
    substitute for a real wheel install onto a separate site-packages tree.
    """

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="aos-a2-parity-")
        cls.pyz = Path(cls._tmp) / "aos.pyz"
        result = subprocess.run(
            [
                sys.executable, str(REPO_ROOT / "tools" / "build_zipapp.py"),
                "--output", str(cls.pyz),
            ],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise AssertionError(f"zipapp build failed: {result.stderr}")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._tmp, ignore_errors=True)

    _ENTRYPOINT_ARGV = {
        "script": [sys.executable, str(REPO_ROOT / "aos.py")],
        "module": [sys.executable, "-m", "agentic_os"],
        "console_script": [
            sys.executable, "-c",
            "import sys\nfrom agentic_os.cli import main\nsys.exit(main())\n",
        ],
    }

    def _run_entrypoint(self, name: str, args: list[str], root: Path) -> tuple[int, str, str]:
        argv = self._ENTRYPOINT_ARGV[name] if name != "zipapp" else [sys.executable, str(self.pyz)]
        cwd = Path(self._tmp) if name == "zipapp" else REPO_ROOT
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        if name in ("module", "console_script"):
            # The one thing that differs from a real installed distribution:
            # resolution via PYTHONPATH rather than site-packages. The
            # reader agentic_os.catalog uses (importlib.resources.files) is
            # installation-method-agnostic, so this does not weaken the
            # resource-reading proof — only the "installed" framing.
            env["PYTHONPATH"] = str(REPO_ROOT)
        result = subprocess.run(
            [*argv, "--root", str(root), *args],
            capture_output=True, text=True, cwd=str(cwd), env=env,
        )
        return result.returncode, result.stdout, result.stderr

    def _assert_four_way(self, args: list[str], root: Path) -> tuple[int, str, str]:
        results = {
            name: self._run_entrypoint(name, args, root)
            for name in ("script", "module", "console_script", "zipapp")
        }
        script = results["script"]
        for name, result in results.items():
            self.assertEqual(result[0], script[0], f"{args}: {name} exit code")
            self.assertEqual(result[1], script[1], f"{args}: {name} stdout")
        return script

    def _fresh_root(self) -> Path:
        tmp = tempfile.mkdtemp(prefix="aos-a2-parity-ws-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        root = Path(tmp)
        code, _out, err = self._run_entrypoint("script", ["init"], root)
        self.assertEqual(code, 0, err)
        return root

    def test_catalog_list_is_byte_identical_across_all_four_entrypoints(self):
        root = self._fresh_root()
        code, out, _err = self._assert_four_way(["agent", "catalog", "list"], root)
        self.assertEqual(code, 0)
        self.assertIn("12 entry(ies), catalog v1", out)

    def test_catalog_verify_is_byte_identical_across_all_four_entrypoints(self):
        root = self._fresh_root()
        code, out, _err = self._assert_four_way(["agent", "catalog", "verify"], root)
        self.assertEqual(code, 0)
        self.assertIn("12 entry(ies), 12 passport(s): OK", out)

    def test_catalog_show_document_is_byte_identical_across_all_four_entrypoints(self):
        root = self._fresh_root()
        code, out, _err = self._assert_four_way(
            ["agent", "catalog", "show", "aos.architect", "--document"], root
        )
        self.assertEqual(code, 0)
        self.assertIn('"agent":"aos.architect"', out)

    def test_doctor_is_byte_identical_with_37_lines_across_all_four_entrypoints(self):
        root = self._fresh_root()
        code, out, _err = self._assert_four_way(["doctor"], root)
        self.assertEqual(code, 0)
        lines = [l for l in out.strip().splitlines() if l]
        self.assertEqual(len(lines), 37)
        self.assertNotIn("[FAIL]", out)

    def test_packaged_zipapp_install_smoke_creates_one_valid_catalog_identity(self):
        """The packaged entrypoint reads its EMBEDDED resources and creates
        one valid catalog identity. Never the real primary ledger; no
        network; no downloaded dependency."""
        tmp = tempfile.mkdtemp(prefix="aos-a2-pyz-smoke-")
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        root = Path(tmp)
        code, _out, err = self._run_entrypoint("zipapp", ["init"], root)
        self.assertEqual(code, 0, err)

        code, out, err = self._run_entrypoint(
            "zipapp", ["agent", "catalog", "install", "aos.architect"], root
        )
        self.assertEqual(code, 0, err)
        self.assertIn("Installed 1 agent(s)", out)

        code, out, err = self._run_entrypoint("zipapp", ["agent", "show", "aos.architect"], root)
        self.assertEqual(code, 0, err)
        self.assertIn("owner:        system", out)
        self.assertIn("protected:    yes", out)


if __name__ == "__main__":
    unittest.main()
