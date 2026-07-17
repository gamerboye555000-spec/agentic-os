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
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from test_v04_agent_passports import V4WorkspaceTestCase
from weekend_harness import run_cli

from agentic_os import catalog, cli, db, models, passports, power, protocols, secretscan
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

    def test_no_install_leaf_exists_in_this_wave(self):
        leaves = set(power.iter_command_paths(cli.build_parser()))
        self.assertNotIn(("agent", "catalog", "install"), leaves)
        self.assertNotIn(("agent", "catalog", "install"), power.COMMAND_POLICY)


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


if __name__ == "__main__":
    unittest.main()
