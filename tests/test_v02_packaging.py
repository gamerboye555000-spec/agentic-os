"""U-P1 packaging: `python -m agentic_os`, console script, and aos.pyz.

Contract: agentic-os-v0.2-u-p1-packaging-contract.md

These tests exercise the real production branches and then inspect the
resulting filesystem state. They never assert on generic error wording.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import runpy
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from agentic_os import protocols

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_DIR = REPO_ROOT / "agentic_os"
BUILDER_PATH = REPO_ROOT / "tools" / "build_zipapp.py"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"


def _load_builder():
    spec = importlib.util.spec_from_file_location("aos_build_zipapp", BUILDER_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {BUILDER_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


build_zipapp = _load_builder()


def _clean_env(**overrides) -> dict:
    """Environment with PYTHONPATH removed, so nothing leaks the checkout in."""
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update(overrides)
    return env


def _run(argv, cwd, env) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=120
    )


def _expected_members() -> set[str]:
    """The allowlist, derived from the real package: root shim + package .py
    + the manifest-driven catalog data allowlist (U-A2, D-v0.4.14)."""
    members = {"__main__.py"}
    for path in PACKAGE_DIR.rglob("*.py"):
        rel = path.relative_to(PACKAGE_DIR)
        if "__pycache__" in rel.parts:
            continue
        members.add(f"agentic_os/{rel.as_posix()}")
    for resource in build_zipapp.catalog_resources(PACKAGE_DIR):
        members.add(f"agentic_os/{resource.relative_to(PACKAGE_DIR).as_posix()}")
    return members


# ---------------------------------------------------------------------------
# Synthetic catalog fixture builders (U-A2) — never touch the real checked-in
# agentic_os/catalog/; every test below writes its own throwaway tree.

def _stub_passport(agent: str = "aos.stub", version: int = 1, **overrides) -> dict:
    document = {
        "schema": "beast.agent-passport/v1",
        "protocol_version": 1,
        "content_hash_alg": protocols.CONTENT_HASH_ALG,
        "created_at": "2026-07-17T00:00:00Z",
        "issuer": "aos.catalog",
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
    document.pop(protocols.CONTENT_HASH_FIELD, None)
    document[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(document)
    return document


def _write_stub_catalog(catalog_dir: Path, entries_spec) -> dict:
    """entries_spec: [(agent, category, maturity, [document, ...]), ...], in
    the EXACT order given (not auto-sorted) -> writes manifest.json plus
    every passport under catalog_dir, canonical bytes on disk throughout;
    returns the manifest dict."""
    catalog_dir.mkdir(parents=True, exist_ok=True)
    entries = []
    for agent, category, maturity, documents in entries_spec:
        versions = []
        for doc in documents:
            path = f"{agent}.v{doc['passport_version']}.passport.json"
            (catalog_dir / path).write_bytes(protocols.serialize_canonical_file_bytes(doc))
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
        "issuer": "aos.catalog",
        "manifest_version": 1,
    }
    manifest.pop(protocols.CONTENT_HASH_FIELD, None)
    manifest[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(manifest)
    (catalog_dir / "manifest.json").write_bytes(protocols.serialize_canonical_file_bytes(manifest))
    return manifest


def _retarget_document_digest(manifest: dict, new_digest: str) -> dict:
    """Deep-copy a single-entry/single-version manifest and repoint its one
    version's document_sha256 at `new_digest`, then reseal the self-digest —
    isolates the artifact-vs-manifest digest check from the manifest's own
    self-digest check."""
    manifest = json.loads(json.dumps(manifest))
    manifest["entries"][0]["versions"][0]["document_sha256"] = new_digest
    manifest.pop(protocols.CONTENT_HASH_FIELD, None)
    manifest[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(manifest)
    return manifest


class ModuleEntrypointTests(unittest.TestCase):
    """(1)(2) `python -m agentic_os` delegates to the canonical CLI."""

    def test_module_delegates_to_canonical_cli(self):
        """Runs the real __main__.py with the canonical main() patched: proves
        it calls agentic_os.cli.main and exits with its return value (a stub
        that discarded the return value would always exit 0)."""
        with mock.patch("agentic_os.cli.main", return_value=42) as fake_main:
            with self.assertRaises(SystemExit) as caught:
                runpy.run_module("agentic_os", run_name="__main__", alter_sys=True)
        self.assertEqual(caught.exception.code, 42)
        fake_main.assert_called_once_with()

    def test_module_entrypoint_defines_no_parser(self):
        """No duplicated argparse tree or dispatch in the shim."""
        source = (PACKAGE_DIR / "__main__.py").read_text()
        self.assertIn("from agentic_os.cli import main", source)
        for forbidden in ("ArgumentParser", "add_argument", "add_parser", "set_defaults"):
            self.assertNotIn(forbidden, source)

    def test_module_and_script_help_match(self):
        env = _clean_env(PYTHONPATH=str(REPO_ROOT))
        script = _run([sys.executable, "aos.py", "--help"], REPO_ROOT, env)
        module = _run([sys.executable, "-m", "agentic_os", "--help"], REPO_ROOT, env)

        self.assertEqual(script.returncode, 0, script.stderr)
        self.assertEqual(module.returncode, script.returncode)
        self.assertEqual(module.stdout, script.stdout)
        self.assertIn("usage: aos", script.stdout)

    def test_module_and_script_error_exit_codes_match(self):
        env = _clean_env(PYTHONPATH=str(REPO_ROOT))
        argv = ["task", "show", "T-0404-does-not-exist"]
        script = _run([sys.executable, "aos.py", *argv], REPO_ROOT, env)
        module = _run([sys.executable, "-m", "agentic_os", *argv], REPO_ROOT, env)

        self.assertEqual(script.returncode, module.returncode)
        self.assertEqual(script.stdout, module.stdout)
        self.assertEqual(script.stderr, module.stderr)


class ScriptEntrypointUnchangedTests(unittest.TestCase):
    """(17) Existing aos.py behavior is unchanged."""

    def test_aos_py_is_still_a_thin_shim(self):
        source = (REPO_ROOT / "aos.py").read_text()
        self.assertIn("from agentic_os.cli import main", source)
        self.assertIn("sys.exit(main())", source)
        for forbidden in ("ArgumentParser", "add_argument", "add_parser"):
            self.assertNotIn(forbidden, source)

    def test_aos_py_still_runs_init_status_doctor(self):
        env = _clean_env()
        with tempfile.TemporaryDirectory() as workspace:
            for argv in (["init"], ["status"], ["doctor"]):
                result = _run(
                    [sys.executable, str(REPO_ROOT / "aos.py"), *argv], workspace, env
                )
                self.assertEqual(result.returncode, 0, f"{argv}: {result.stderr}")

    def test_aos_py_exit_codes_preserved(self):
        env = _clean_env()
        result = _run([sys.executable, str(REPO_ROOT / "aos.py"), "--help"], REPO_ROOT, env)
        self.assertEqual(result.returncode, 0)
        with tempfile.TemporaryDirectory() as empty:
            # Uninitialized workspace is a user/domain error: exit 1, one line.
            result = _run([sys.executable, str(REPO_ROOT / "aos.py"), "status"], empty, env)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertTrue(result.stderr.strip())


class ZipappBuildTests(unittest.TestCase):
    """(3)(9) Builder output shape and archive membership."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="aos-pyz-build-"))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        cls.archive = build_zipapp.build(cls.tmp / "aos.pyz")

    def test_archive_is_a_regular_executable_zip_with_shebang(self):
        st = os.lstat(self.archive)
        self.assertTrue(stat.S_ISREG(st.st_mode))
        self.assertTrue(st.st_mode & stat.S_IXUSR, "owner execute bit missing")
        self.assertTrue(zipfile.is_zipfile(self.archive))
        with open(self.archive, "rb") as handle:
            self.assertEqual(handle.readline(), b"#!/usr/bin/env python3\n")

    def test_archive_runs(self):
        result = _run([sys.executable, str(self.archive), "--help"], self.tmp, _clean_env())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("usage: aos", result.stdout)

    def test_archive_membership_is_exactly_the_runtime_allowlist(self):
        with zipfile.ZipFile(self.archive) as archive:
            members = {n for n in archive.namelist() if not n.endswith("/")}
        self.assertEqual(members, _expected_members())
        self.assertIn("agentic_os/cli.py", members)
        self.assertIn("__main__.py", members)

    def test_archive_root_entrypoint_is_the_module_entrypoint_verbatim(self):
        """Contract 2.1: one shim, no third copy to drift."""
        with zipfile.ZipFile(self.archive) as archive:
            root_main = archive.read("__main__.py")
            package_main = archive.read("agentic_os/__main__.py")
        on_disk = (PACKAGE_DIR / "__main__.py").read_bytes()
        self.assertEqual(root_main, on_disk)
        self.assertEqual(root_main, package_main)

    def test_default_output_path_is_dist_aos_pyz(self):
        self.assertEqual(build_zipapp.DEFAULT_OUTPUT, REPO_ROOT / "dist" / "aos.pyz")

    def test_builder_imports_only_stdlib(self):
        stdlib = set(sys.stdlib_module_names)
        source = BUILDER_PATH.read_text()
        imported = {
            line.split()[1].split(".")[0]
            for line in source.splitlines()
            if line.startswith("import ")
        }
        self.assertTrue(imported)
        self.assertEqual(imported - stdlib, set())

    def test_builder_never_imports_agentic_os(self):
        """The builder must remain runnable standalone: it verifies the
        catalog with its own small stdlib-only duplicate of the canonical-
        JSON/digest rules, never by importing the package it is packaging."""
        for line in BUILDER_PATH.read_text().splitlines():
            stripped = line.strip()
            self.assertFalse(stripped.startswith("import agentic_os"), line)
            self.assertFalse(stripped.startswith("from agentic_os"), line)

    def test_archive_contains_exactly_thirteen_catalog_resources(self):
        manifest = build_zipapp.load_catalog_manifest(PACKAGE_DIR / "catalog")
        expected = {"agentic_os/catalog/manifest.json"}
        for entry in manifest["entries"]:
            for version in entry["versions"]:
                expected.add(f"agentic_os/catalog/{version['path']}")
        self.assertEqual(len(expected), 13)
        with zipfile.ZipFile(self.archive) as archive:
            members = {n for n in archive.namelist() if not n.endswith("/")}
        catalog_members = {n for n in members if n.startswith("agentic_os/catalog/")}
        self.assertEqual(catalog_members, expected)

    def test_catalog_resource_bytes_are_deterministic_across_builds(self):
        tmp2 = Path(tempfile.mkdtemp(prefix="aos-pyz-build2-"))
        self.addCleanup(shutil.rmtree, tmp2, ignore_errors=True)
        archive2 = build_zipapp.build(tmp2 / "aos.pyz")
        with zipfile.ZipFile(self.archive) as a1, zipfile.ZipFile(archive2) as a2:
            names1 = [n for n in a1.namelist() if n.startswith("agentic_os/catalog/")]
            names2 = [n for n in a2.namelist() if n.startswith("agentic_os/catalog/")]
            # zipapp.create_archive writes members in sorted(path) order —
            # deterministic by construction, proven here rather than assumed.
            self.assertEqual(names1, sorted(names1))
            self.assertEqual(names1, names2)
            for name in names1:
                self.assertEqual(a1.read(name), a2.read(name), name)


class ZipappExclusionTests(unittest.TestCase):
    """(10) The allowlist excludes non-runtime files even from a dirty tree."""

    def test_contaminated_source_tree_contributes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_root = Path(tmp) / "repo"
            package = fake_root / "agentic_os"
            package.mkdir(parents=True)

            # Real runtime sources.
            (package / "__init__.py").write_text("__version__ = '0.0.0'\n")
            (package / "cli.py").write_text("def main(argv=None):\n    return 0\n")
            shutil.copyfile(PACKAGE_DIR / "__main__.py", package / "__main__.py")

            # Contamination inside the package.
            (package / "__pycache__").mkdir()
            (package / "__pycache__" / "cli.cpython-312.pyc").write_bytes(b"\x00pyc")
            (package / "cli.pyc").write_bytes(b"\x00pyc")
            (package / "aos.db").write_bytes(b"SQLite format 3\x00")
            (package / ".env").write_text("AOS_TOKEN=sk-live-SECRET\n")
            (package / "credentials.json").write_text('{"token": "sk-live-SECRET"}\n')
            (package / "settings.local.json").write_text('{"local": true}\n')
            (package / "notes.md").write_text("# docs\n")
            ledger = package / ".agentic-os"
            ledger.mkdir()
            (ledger / "aos.db").write_bytes(b"SQLite format 3\x00LEDGER")

            # A legitimate minimal catalog (U-A2), PLUS catalog-local
            # contamination: an unreferenced passport and a credentials.json
            # sitting right next to the referenced files. Both must stay
            # excluded — never by name, only by absence from the manifest.
            catalog_dir = package / "catalog"
            _write_stub_catalog(catalog_dir, [("aos.stub", "design", "stable", [_stub_passport()])])
            (catalog_dir / "aos.unreferenced.v1.passport.json").write_bytes(
                protocols.serialize_canonical_file_bytes(_stub_passport("aos.unreferenced"))
            )
            (catalog_dir / "credentials.json").write_text('{"token": "sk-live-CATALOGSECRET"}\n')

            # Contamination at the repo root.
            for name in (".git", ".agentic-os", "tests", "adapters", "research"):
                (fake_root / name).mkdir()
            (fake_root / ".git" / "config").write_text("[core]\n")
            (fake_root / ".agentic-os" / "aos.db").write_bytes(b"SQLite format 3\x00")
            (fake_root / "tests" / "test_secret.py").write_text("SECRET = 1\n")
            (fake_root / "aos_hooks.py").write_text("# repo-only runner\n")
            (fake_root / "README.md").write_text("# docs\n")
            backups = fake_root / ".agentic-os" / "backups"
            backups.mkdir()
            (backups / "aos-2026.db").write_bytes(b"SQLite format 3\x00BACKUP")

            archive_path = build_zipapp.build(Path(tmp) / "out" / "aos.pyz", repo_root=fake_root)

            with zipfile.ZipFile(archive_path) as archive:
                members = [n for n in archive.namelist() if not n.endswith("/")]
                blob = b"".join(archive.read(n) for n in members)

        self.assertEqual(
            set(members),
            {
                "__main__.py", "agentic_os/__init__.py", "agentic_os/__main__.py",
                "agentic_os/cli.py", "agentic_os/catalog/manifest.json",
                "agentic_os/catalog/aos.stub.v1.passport.json",
            },
        )
        self.assertNotIn("agentic_os/catalog/aos.unreferenced.v1.passport.json", members)
        self.assertNotIn("agentic_os/catalog/credentials.json", members)
        self.assertNotIn(b"CATALOGSECRET", blob)

        # Nothing secret or stateful rode along, in name or in content.
        self.assertNotIn(b"sk-live-SECRET", blob)
        self.assertNotIn(b"SQLite format 3", blob)
        self.assertNotIn(b"LEDGER", blob)
        self.assertNotIn(b"BACKUP", blob)

        catalog_members = {
            "agentic_os/catalog/manifest.json",
            "agentic_os/catalog/aos.stub.v1.passport.json",
        }
        for member in members:
            parts = Path(member).parts
            if member not in catalog_members:
                self.assertTrue(member.endswith(".py"), member)
            self.assertFalse(member.endswith((".pyc", ".pyo")), member)
            for banned in ("__pycache__", ".git", ".agentic-os", "tests", "backups"):
                self.assertNotIn(banned, parts, member)
            self.assertNotIn(member, ("aos_hooks.py", "README.md"))


class CatalogAllowlistTests(unittest.TestCase):
    """(U-A2, D-v0.4.14) build_zipapp.catalog_resources()'s manifest and
    passport verification, exercised directly against synthetic package
    trees — never the real checked-in agentic_os/catalog/."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aos-catalog-allowlist-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package_dir = self.tmp / "agentic_os"
        self.catalog_dir = self.package_dir / "catalog"

    def _resources(self):
        return build_zipapp.catalog_resources(self.package_dir)

    # -- happy path -----------------------------------------------------

    def test_valid_single_entry_catalog_resolves_to_manifest_plus_one_passport(self):
        _write_stub_catalog(
            self.catalog_dir, [("aos.stub", "design", "stable", [_stub_passport()])]
        )
        names = {p.name for p in self._resources()}
        self.assertEqual(names, {"manifest.json", "aos.stub.v1.passport.json"})

    def test_multi_entry_catalog_resolves_deterministically_in_sorted_order(self):
        _write_stub_catalog(
            self.catalog_dir,
            [
                ("aos.aaa", "design", "stable", [_stub_passport("aos.aaa")]),
                ("aos.bbb", "design", "stable", [_stub_passport("aos.bbb")]),
            ],
        )
        names = [p.name for p in self._resources()]
        self.assertEqual(
            names, ["manifest.json", "aos.aaa.v1.passport.json", "aos.bbb.v1.passport.json"]
        )

    # -- exclusion --------------------------------------------------------

    def test_extra_unreferenced_passport_is_excluded(self):
        _write_stub_catalog(
            self.catalog_dir, [("aos.stub", "design", "stable", [_stub_passport()])]
        )
        (self.catalog_dir / "aos.other.v1.passport.json").write_bytes(
            protocols.serialize_canonical_file_bytes(_stub_passport("aos.other"))
        )
        names = {p.name for p in self._resources()}
        self.assertNotIn("aos.other.v1.passport.json", names)

    def test_credentials_json_under_catalog_is_excluded(self):
        _write_stub_catalog(
            self.catalog_dir, [("aos.stub", "design", "stable", [_stub_passport()])]
        )
        (self.catalog_dir / "credentials.json").write_text('{"token":"sk-live-x"}\n')
        names = {p.name for p in self._resources()}
        self.assertNotIn("credentials.json", names)

    # -- missing / unsafe ---------------------------------------------------

    def test_missing_manifest_fails_the_build(self):
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()

    def test_missing_referenced_passport_fails_the_build(self):
        _write_stub_catalog(
            self.catalog_dir, [("aos.stub", "design", "stable", [_stub_passport()])]
        )
        (self.catalog_dir / "aos.stub.v1.passport.json").unlink()
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()

    def test_symlinked_manifest_is_refused(self):
        _write_stub_catalog(
            self.catalog_dir, [("aos.stub", "design", "stable", [_stub_passport()])]
        )
        real = self.catalog_dir / "manifest.json"
        target = self.tmp / "manifest-target.json"
        target.write_bytes(real.read_bytes())
        real.unlink()
        real.symlink_to(target)
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()

    def test_symlinked_passport_is_refused(self):
        _write_stub_catalog(
            self.catalog_dir, [("aos.stub", "design", "stable", [_stub_passport()])]
        )
        real = self.catalog_dir / "aos.stub.v1.passport.json"
        target = self.tmp / "passport-target.json"
        target.write_bytes(real.read_bytes())
        real.unlink()
        real.symlink_to(target)
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()

    def test_oversized_referenced_passport_is_refused(self):
        _write_stub_catalog(
            self.catalog_dir, [("aos.stub", "design", "stable", [_stub_passport()])]
        )
        (self.catalog_dir / "aos.stub.v1.passport.json").write_bytes(
            b"{" + b" " * (build_zipapp.MAX_ARTIFACT_BYTES + 10) + b"}\n"
        )
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()

    def test_unsafe_manifest_path_is_refused(self):
        manifest = _write_stub_catalog(
            self.catalog_dir, [("aos.stub", "design", "stable", [_stub_passport()])]
        )
        bad_manifest = json.loads(json.dumps(manifest))
        bad_manifest["entries"][0]["versions"][0]["path"] = "../evil.json"
        bad_manifest.pop(protocols.CONTENT_HASH_FIELD, None)
        bad_manifest[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(bad_manifest)
        (self.catalog_dir / "manifest.json").write_bytes(
            protocols.serialize_canonical_file_bytes(bad_manifest)
        )
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()

    # -- malformed / duplicate-key / non-canonical ---------------------------

    def test_duplicate_json_key_in_manifest_is_refused(self):
        _write_stub_catalog(
            self.catalog_dir, [("aos.stub", "design", "stable", [_stub_passport()])]
        )
        (self.catalog_dir / "manifest.json").write_text('{"a":1,"a":2}\n')
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()

    def test_duplicate_json_key_in_passport_is_refused(self):
        _write_stub_catalog(
            self.catalog_dir, [("aos.stub", "design", "stable", [_stub_passport()])]
        )
        (self.catalog_dir / "aos.stub.v1.passport.json").write_text('{"a":1,"a":2}\n')
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()

    def test_malformed_manifest_json_is_refused(self):
        _write_stub_catalog(
            self.catalog_dir, [("aos.stub", "design", "stable", [_stub_passport()])]
        )
        (self.catalog_dir / "manifest.json").write_text("not json at all\n")
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()

    def test_non_canonical_manifest_bytes_are_refused(self):
        manifest = _write_stub_catalog(
            self.catalog_dir, [("aos.stub", "design", "stable", [_stub_passport()])]
        )
        pretty = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        (self.catalog_dir / "manifest.json").write_text(pretty)
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()

    def test_non_canonical_passport_bytes_are_refused(self):
        doc = _stub_passport()
        _write_stub_catalog(self.catalog_dir, [("aos.stub", "design", "stable", [doc])])
        pretty = json.dumps(doc, indent=2, sort_keys=True) + "\n"
        (self.catalog_dir / "aos.stub.v1.passport.json").write_text(pretty)
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()

    def test_missing_trailing_newline_is_refused(self):
        _write_stub_catalog(
            self.catalog_dir, [("aos.stub", "design", "stable", [_stub_passport()])]
        )
        path = self.catalog_dir / "aos.stub.v1.passport.json"
        path.write_bytes(path.read_bytes().rstrip(b"\n"))
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()

    def test_manifest_entries_out_of_order_are_refused(self):
        _write_stub_catalog(
            self.catalog_dir,
            [
                ("aos.bbb", "design", "stable", [_stub_passport("aos.bbb")]),
                ("aos.aaa", "design", "stable", [_stub_passport("aos.aaa")]),
            ],
        )
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()

    def test_manifest_duplicate_agent_is_refused(self):
        self.catalog_dir.mkdir(parents=True, exist_ok=True)
        doc = _stub_passport("aos.stub")
        (self.catalog_dir / "aos.stub.v1.passport.json").write_bytes(
            protocols.serialize_canonical_file_bytes(doc)
        )
        manifest = {
            "canonical_json": protocols.CANONICAL_JSON,
            "catalog_version": 1,
            "content_hash_alg": protocols.CONTENT_HASH_ALG,
            "entries": [
                {
                    "agent": "aos.stub", "category": "design", "maturity": "stable",
                    "versions": [
                        {
                            "document_sha256": protocols.content_digest(doc),
                            "passport_version": 1, "path": "aos.stub.v1.passport.json",
                        }
                    ],
                },
                {
                    "agent": "aos.stub", "category": "design", "maturity": "stable",
                    "versions": [
                        {
                            "document_sha256": protocols.content_digest(doc),
                            "passport_version": 1, "path": "aos.stub.v1.passport.json",
                        }
                    ],
                },
            ],
            "issuer": "aos.catalog",
            "manifest_version": 1,
        }
        manifest[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(manifest)
        (self.catalog_dir / "manifest.json").write_bytes(
            protocols.serialize_canonical_file_bytes(manifest)
        )
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()

    # -- digest / binding equalities -----------------------------------------

    def test_document_digest_mismatch_between_passport_and_manifest_is_refused(self):
        doc = _stub_passport()
        manifest = _write_stub_catalog(
            self.catalog_dir, [("aos.stub", "design", "stable", [doc])]
        )
        bad_manifest = _retarget_document_digest(manifest, "0" * 64)
        (self.catalog_dir / "manifest.json").write_bytes(
            protocols.serialize_canonical_file_bytes(bad_manifest)
        )
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()

    def test_tampered_internal_content_sha256_is_refused(self):
        doc = _stub_passport()
        _write_stub_catalog(self.catalog_dir, [("aos.stub", "design", "stable", [doc])])
        bad_doc = dict(doc)
        bad_doc["content_sha256"] = "0" * 64
        (self.catalog_dir / "aos.stub.v1.passport.json").write_bytes(
            protocols.serialize_canonical_file_bytes(bad_doc)
        )
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()

    def test_malformed_internal_content_sha256_format_is_refused(self):
        doc = _stub_passport()
        _write_stub_catalog(self.catalog_dir, [("aos.stub", "design", "stable", [doc])])
        bad_doc = dict(doc)
        bad_doc["content_sha256"] = "ABCDEF" + "0" * 58  # uppercase: not lowercase-hex
        (self.catalog_dir / "aos.stub.v1.passport.json").write_bytes(
            protocols.serialize_canonical_file_bytes(bad_doc)
        )
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()

    def test_agent_binding_mismatch_is_refused_even_when_digests_agree(self):
        # A self-consistent document for a DIFFERENT agent, swapped in at the
        # same path, with the manifest's recorded digest repointed at its
        # real hash — isolates the binding check from the (already-total)
        # digest-equality check.
        wrong_agent_doc = _stub_passport(agent="aos.other", version=1)
        stub_doc = _stub_passport(agent="aos.stub", version=1)
        manifest = _write_stub_catalog(
            self.catalog_dir, [("aos.stub", "design", "stable", [stub_doc])]
        )
        (self.catalog_dir / "aos.stub.v1.passport.json").write_bytes(
            protocols.serialize_canonical_file_bytes(wrong_agent_doc)
        )
        bad_manifest = _retarget_document_digest(
            manifest, protocols.content_digest(wrong_agent_doc)
        )
        (self.catalog_dir / "manifest.json").write_bytes(
            protocols.serialize_canonical_file_bytes(bad_manifest)
        )
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()

    def test_passport_version_binding_mismatch_is_refused_even_when_digests_agree(self):
        wrong_version_doc = _stub_passport(agent="aos.stub", version=2)
        stub_doc = _stub_passport(agent="aos.stub", version=1)
        manifest = _write_stub_catalog(
            self.catalog_dir, [("aos.stub", "design", "stable", [stub_doc])]
        )
        (self.catalog_dir / "aos.stub.v1.passport.json").write_bytes(
            protocols.serialize_canonical_file_bytes(wrong_version_doc)
        )
        bad_manifest = _retarget_document_digest(
            manifest, protocols.content_digest(wrong_version_doc)
        )
        (self.catalog_dir / "manifest.json").write_bytes(
            protocols.serialize_canonical_file_bytes(bad_manifest)
        )
        with self.assertRaises(build_zipapp.BuildError):
            self._resources()


class ZipappOutputSafetyTests(unittest.TestCase):
    """(13) Unsafe existing output objects are refused, untouched."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aos-pyz-safety-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def _assert_refused(self, output: Path):
        with self.assertRaises(build_zipapp.BuildError):
            build_zipapp.build(output)

    def test_symlink_output_refused_and_target_untouched(self):
        """lstat, not stat: a symlink pointing at a *regular file* is still
        refused, and the target is never written through."""
        target = self.tmp / "real.pyz"
        target.write_bytes(b"ORIGINAL TARGET")
        link = self.tmp / "link.pyz"
        link.symlink_to(target)

        self._assert_refused(link)

        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), str(target))
        self.assertEqual(target.read_bytes(), b"ORIGINAL TARGET")

    def test_dangling_symlink_output_refused(self):
        link = self.tmp / "dangling.pyz"
        link.symlink_to(self.tmp / "missing")
        self._assert_refused(link)
        self.assertTrue(link.is_symlink())
        self.assertFalse(link.exists())

    def test_directory_output_refused_and_untouched(self):
        output = self.tmp / "dir.pyz"
        output.mkdir()
        (output / "keep.txt").write_text("keep me")

        self._assert_refused(output)

        self.assertTrue(output.is_dir())
        self.assertEqual((output / "keep.txt").read_text(), "keep me")
        self.assertEqual([p.name for p in output.iterdir()], ["keep.txt"])

    def test_fifo_output_refused_and_untouched(self):
        output = self.tmp / "fifo.pyz"
        os.mkfifo(output)

        self._assert_refused(output)

        self.assertTrue(stat.S_ISFIFO(os.lstat(output).st_mode))

    def test_socket_output_refused_and_untouched(self):
        output = self.tmp / "sock.pyz"
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        sock.bind(str(output))

        self._assert_refused(output)

        self.assertTrue(stat.S_ISSOCK(os.lstat(output).st_mode))

    def test_unsafe_output_exits_nonzero_with_a_concise_secret_free_diagnostic(self):
        output = self.tmp / "dir2.pyz"
        output.mkdir()
        (output / "secrets.txt").write_text("AOS_TOKEN=sk-live-SECRET\n")

        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = build_zipapp.main(["--output", str(output)])

        self.assertEqual(code, 1)
        self.assertTrue(output.is_dir())
        self.assertEqual((output / "secrets.txt").read_text(), "AOS_TOKEN=sk-live-SECRET\n")

        diagnostic = err.getvalue()
        self.assertEqual(len(diagnostic.strip().splitlines()), 1, diagnostic)
        self.assertNotIn("sk-live-SECRET", diagnostic)
        self.assertNotIn("Traceback", diagnostic)

    def test_regular_file_output_is_replaced_on_success(self):
        output = self.tmp / "aos.pyz"
        output.write_bytes(b"STALE")
        build_zipapp.build(output)
        self.assertTrue(zipfile.is_zipfile(output))
        self.assertNotEqual(output.read_bytes()[:5], b"STALE")


class ZipappAtomicityTests(unittest.TestCase):
    """(11)(12) Failure atomicity: no partial, no clobber, no debris."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="aos-pyz-atomic-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_existing_destination_survives_injected_failure_byte_identically(self):
        output = self.tmp / "aos.pyz"
        build_zipapp.build(output)  # a real, valid archive first
        before = output.read_bytes()
        before_mode = output.stat().st_mode

        with mock.patch.object(
            build_zipapp.zipapp, "create_archive", side_effect=RuntimeError("injected")
        ):
            with self.assertRaises(RuntimeError):
                build_zipapp.build(output)

        self.assertEqual(output.read_bytes(), before)
        self.assertEqual(output.stat().st_mode, before_mode)
        self.assertTrue(zipfile.is_zipfile(output), "destination still a valid zipapp")
        self.assertEqual([p.name for p in self.tmp.iterdir()], ["aos.pyz"])

    def test_first_build_failure_leaves_no_partial_destination(self):
        output = self.tmp / "nested" / "aos.pyz"

        with mock.patch.object(
            build_zipapp.zipapp, "create_archive", side_effect=RuntimeError("injected")
        ):
            with self.assertRaises(RuntimeError):
                build_zipapp.build(output)

        self.assertFalse(output.exists())
        self.assertFalse(output.is_symlink())
        self.assertEqual(list(output.parent.iterdir()), [], "temp debris left behind")

    def test_staging_failure_leaves_destination_and_no_debris(self):
        output = self.tmp / "aos.pyz"
        build_zipapp.build(output)
        before = output.read_bytes()

        with mock.patch.object(
            build_zipapp, "_stage_tree", side_effect=RuntimeError("injected")
        ):
            with self.assertRaises(RuntimeError):
                build_zipapp.build(output)

        self.assertEqual(output.read_bytes(), before)
        self.assertEqual([p.name for p in self.tmp.iterdir()], ["aos.pyz"])

    def test_build_does_not_touch_the_source_tree(self):
        before = {
            p.relative_to(PACKAGE_DIR).as_posix(): p.stat().st_mtime_ns
            for p in PACKAGE_DIR.rglob("*.py")
        }
        build_zipapp.build(self.tmp / "aos.pyz")
        after = {
            p.relative_to(PACKAGE_DIR).as_posix(): p.stat().st_mtime_ns
            for p in PACKAGE_DIR.rglob("*.py")
        }
        self.assertEqual(before, after)


class ZipappCustomOutputTests(unittest.TestCase):
    """(14) --output PATH, including parents that do not exist yet."""

    def test_custom_output_path_creates_parents_and_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "deep" / "nested" / "custom.pyz"
            with contextlib.redirect_stdout(io.StringIO()):
                code = build_zipapp.main(["--output", str(output)])
            self.assertEqual(code, 0)
            self.assertTrue(output.is_file())
            result = _run([sys.executable, str(output), "--help"], tmp, _clean_env())
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("usage: aos", result.stdout)

    def test_relative_custom_output_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = _run(
                [sys.executable, str(BUILDER_PATH), "--output", "out/rel.pyz"],
                tmp,
                _clean_env(),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((Path(tmp) / "out" / "rel.pyz").is_file())


class ZipappRuntimeEquivalenceTests(unittest.TestCase):
    """(4)(5)(6)(7) The archive runs standalone, outside the repository."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="aos-pyz-runtime-"))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        built = build_zipapp.build(cls.tmp / "build" / "aos.pyz")
        # Only the archive is copied out: nothing else from the checkout.
        cls.standalone = cls.tmp / "elsewhere" / "aos.pyz"
        cls.standalone.parent.mkdir(parents=True)
        shutil.copyfile(built, cls.standalone)
        cls.standalone.chmod(0o755)

    def _pyz(self, argv, cwd):
        return _run([sys.executable, str(self.standalone), *argv], cwd, _clean_env())

    def test_help_matches_script_outside_repo_without_pythonpath(self):
        with tempfile.TemporaryDirectory() as elsewhere:
            archive = self._pyz(["--help"], elsewhere)
            script = _run(
                [sys.executable, "aos.py", "--help"], REPO_ROOT, _clean_env()
            )
            self.assertEqual(archive.returncode, 0, archive.stderr)
            self.assertEqual(archive.returncode, script.returncode)
            self.assertEqual(archive.stdout, script.stdout)

    def test_repo_is_not_on_sys_path_for_the_archive(self):
        """Proves the archive is self-contained: the checkout is absent from
        sys.path, so agentic_os can only have come from inside the .pyz."""
        with tempfile.TemporaryDirectory() as elsewhere:
            result = self._pyz(["--help"], elsewhere)
            self.assertEqual(result.returncode, 0)
            probe = _run(
                [sys.executable, "-c", "import agentic_os"], elsewhere, _clean_env()
            )
            self.assertNotEqual(
                probe.returncode, 0, "checkout leaked onto sys.path; test is void"
            )

    def test_init_status_doctor_in_a_disposable_workspace(self):
        with tempfile.TemporaryDirectory() as workspace:
            init = self._pyz(["init"], workspace)
            self.assertEqual(init.returncode, 0, init.stderr)
            self.assertTrue((Path(workspace) / ".agentic-os" / "aos.db").is_file())

            status = self._pyz(["status"], workspace)
            self.assertEqual(status.returncode, 0, status.stderr)

            doctor = self._pyz(["doctor"], workspace)
            self.assertEqual(doctor.returncode, 0, doctor.stderr)
            lines = [ln for ln in doctor.stdout.splitlines() if ln.strip()]
            self.assertTrue(lines)
            self.assertNotIn("[FAIL]", doctor.stdout)
            for line in lines:
                self.assertTrue(line.startswith("[PASS]"), line)

    def test_archive_is_runnable_by_shebang(self):
        with tempfile.TemporaryDirectory() as workspace:
            result = _run([str(self.standalone), "--help"], workspace, _clean_env())
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("usage: aos", result.stdout)

    def test_archive_propagates_domain_error_exit_code(self):
        with tempfile.TemporaryDirectory() as empty:
            result = self._pyz(["status"], empty)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertTrue(result.stderr.strip())


class ModuleWorkspaceTests(unittest.TestCase):
    """(8) The module entrypoint runs init/status/doctor for real."""

    def test_module_init_status_doctor_in_a_disposable_workspace(self):
        env = _clean_env(PYTHONPATH=str(REPO_ROOT))
        with tempfile.TemporaryDirectory() as workspace:
            init = _run([sys.executable, "-m", "agentic_os", "init"], workspace, env)
            self.assertEqual(init.returncode, 0, init.stderr)
            self.assertTrue((Path(workspace) / ".agentic-os" / "aos.db").is_file())

            status = _run([sys.executable, "-m", "agentic_os", "status"], workspace, env)
            self.assertEqual(status.returncode, 0, status.stderr)

            doctor = _run([sys.executable, "-m", "agentic_os", "doctor"], workspace, env)
            self.assertEqual(doctor.returncode, 0, doctor.stderr)
            self.assertNotIn("[FAIL]", doctor.stdout)
            for line in [ln for ln in doctor.stdout.splitlines() if ln.strip()]:
                self.assertTrue(line.startswith("[PASS]"), line)


class PyprojectTests(unittest.TestCase):
    """(15)(16) Packaging metadata."""

    @classmethod
    def setUpClass(cls):
        with open(PYPROJECT_PATH, "rb") as handle:
            cls.config = tomllib.load(handle)

    def test_console_script_points_at_the_canonical_cli(self):
        scripts = self.config["project"]["scripts"]
        self.assertEqual(scripts, {"aos": "agentic_os.cli:main"})

        module_name, _, attr = scripts["aos"].partition(":")
        module = importlib.import_module(module_name)
        entry = getattr(module, attr)
        self.assertTrue(callable(entry))

        # The console script and every other entrypoint share one implementation.
        from agentic_os.cli import main as canonical

        self.assertIs(entry, canonical)

    def test_no_runtime_dependencies(self):
        project = self.config["project"]
        self.assertEqual(project["dependencies"], [])
        self.assertEqual(project.get("optional-dependencies", {}), {})

    def test_build_requirements_are_minimal_and_not_runtime(self):
        requires = self.config["build-system"]["requires"]
        self.assertEqual([r.split(">=")[0].strip() for r in requires], ["setuptools"])

    def test_requires_python_allows_3_12(self):
        self.assertEqual(self.config["project"]["requires-python"], ">=3.12")

    def test_package_discovery_is_an_explicit_allowlist(self):
        self.assertEqual(self.config["tool"]["setuptools"]["packages"], ["agentic_os"])

    def test_version_is_sourced_from_the_package(self):
        self.assertIn("version", self.config["project"]["dynamic"])
        self.assertEqual(
            self.config["tool"]["setuptools"]["dynamic"]["version"],
            {"attr": "agentic_os.__version__"},
        )

    def test_package_data_declares_only_the_catalog_json_subtree(self):
        """(U-A2, D-v0.4.14) A restricted, repo-subtree-scoped pattern, never
        a repository-wide *.json rule: only agentic_os/catalog/*.json."""
        self.assertEqual(
            self.config["tool"]["setuptools"]["package-data"],
            {"agentic_os": ["catalog/*.json"]},
        )


class CatalogPackageResourceReadingTests(unittest.TestCase):
    """(U-A2) The manifest and all twelve passports are readable through the
    SAME importlib.resources reader agentic_os/catalog.py uses at runtime —
    proving package-data actually reaches the resource-reading API, not just
    that pyproject.toml declares it.

    This environment has no pip/wheel/network available (verified: no `pip`
    binary, no `ensurepip` module, no `wheel` package, and setuptools 68.1.2
    has no built-in bdist_wheel), so a real `pip install` of a built wheel
    cannot be exercised here. importlib.resources.files() is installation-
    method-agnostic — it resolves the same way whether agentic_os came from
    a pip-installed site-packages copy or a checkout on sys.path — so reading
    through it against the live imported package is the offline-safe proxy
    for "the installed package exposes these resources."
    """

    def test_manifest_and_all_referenced_passports_are_readable_as_resources(self):
        import importlib.resources

        manifest_bytes = (
            importlib.resources.files("agentic_os") / "catalog" / "manifest.json"
        ).read_bytes()
        manifest = json.loads(manifest_bytes)
        self.assertEqual(len(manifest["entries"]), 12)
        for entry in manifest["entries"]:
            for version in entry["versions"]:
                data = (
                    importlib.resources.files("agentic_os")
                    / "catalog" / version["path"]
                ).read_bytes()
                self.assertGreater(len(data), 0)


class GitignoreTests(unittest.TestCase):
    """(contract 9) Generated artifacts stay out of git."""

    def test_dist_and_pyz_are_ignored(self):
        patterns = {
            line.strip()
            for line in (REPO_ROOT / ".gitignore").read_text().splitlines()
            if line.strip() and not line.startswith("#")
        }
        self.assertIn("dist/", patterns)
        self.assertIn("*.pyz", patterns)


if __name__ == "__main__":
    unittest.main()
