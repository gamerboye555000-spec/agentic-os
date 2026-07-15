"""v0.2 U-H1 session-hook tests (agentic-os-v0.2-u-h1-sessionend-hook-contract.md).

Two-stage bridge: the Stop handler stages exactly one fenced aos-dropfile
envelope from the official last_assistant_message; the SessionEnd handler
re-validates and publishes at most one protocol-valid dropfile under
`.agentic-os/exports/`. Ingest stays manual. Plus the trust-gated settings
installer (dry-run default, confirmed apply, backup, idempotency, status,
uninstall) and the five-scenario dogfood matrix the accelerated gate pins.

Every test runs against temporary directories; no real Claude settings file
is ever touched and no ledger outside a per-test workspace is opened.
"""

from __future__ import annotations

import builtins
import contextlib
import io
import json
import os
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from weekend_harness import run_cli

from agentic_os import hooks, ingest, render, utils

REPO_ROOT = Path(__file__).resolve().parent.parent

SID = "0f0e0d0c-1111-2222-3333-444455556666"
OTHER_SID = "9e9e9e9e-1111-2222-3333-444455556666"

#: Test-only fake credential (never a real secret).
FAKE_TOKEN = "ghp_" + "x1" * 12

VALID_DROPFILE = (
    "# AOS DROPFILE\n"
    "task: T-0009\n"
    "agent: claude-code\n"
    "outcome: success\n"
    "summary: Implemented and tested the change.\n"
    "\n"
    "## evidence\n"
    "- kind: test | ref: python -m unittest | claim: focused suite green\n"
    "\n"
    "## open questions\n"
    "- none for the next run\n"
)

VALID_SHA = utils.sha256_text(VALID_DROPFILE)
EXPECTED_NAME = (
    f"dropfile-T-0009-claude-code-hook-{SID[:8]}-{VALID_SHA[:12]}.md"
)

#: The 2026-07-14 live-smoke incident body (session 73f275be…): the smoke
#: prompt forbade the '## evidence' / '## open questions' sections, so this
#: exact write-back is MALFORMED per the canon parser and must refuse loudly.
LIVE_SECTIONLESS_BODY = (
    "# AOS DROPFILE\n"
    "task: T-0009\n"
    "agent: claude-code\n"
    "outcome: success\n"
    "summary: U-H1 disposable live hook smoke completed\n"
)

#: The same write-back with the protocol-required headings (both legitimately
#: empty) — a valid envelope in the exact live-smoke message shape.
LIVE_SHAPE_VALID_BODY = (
    LIVE_SECTIONLESS_BODY + "\n## evidence\n\n## open questions\n"
)


def fenced(body: str) -> str:
    return f"All done — summary below.\n\n```aos-dropfile\n{body}```\n"


def dropfile(task="T-0009", outcome="success", summary=None, evidence=None,
             questions=None) -> str:
    lines = [
        "# AOS DROPFILE",
        f"task: {task}",
        "agent: claude-code",
        f"outcome: {outcome}",
        f"summary: {summary or 'Scenario summary.'}",
        "",
        "## evidence",
    ]
    lines += evidence if evidence is not None else []
    lines += ["", "## open questions"]
    lines += questions if questions is not None else []
    return "\n".join(lines) + "\n"


def run_hook(argv: list[str], data=None, raw: bytes | None = None):
    stdin = raw if raw is not None else json.dumps(data).encode("utf-8")
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = hooks.main(argv, stdin_bytes=stdin)
    return code, out.getvalue(), err.getvalue()


def tree_snapshot(root: Path) -> dict:
    snap = {}
    for path in sorted(root.rglob("*")):
        st = os.lstat(path)
        key = str(path.relative_to(root))
        if stat.S_ISREG(st.st_mode):
            snap[key] = ("file", path.read_bytes())
        elif stat.S_ISDIR(st.st_mode):
            snap[key] = ("dir",)
        else:
            snap[key] = ("other",)
    return snap


class HookWorkspaceCase(unittest.TestCase):
    """A minimal fake workspace: the hooks only need `.agentic-os/aos.db`
    to exist as a file (discovery) and own `.agentic-os/exports/`."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.project = self.tmp / "project"
        self.exports = self.project / ".agentic-os" / "exports"
        self.exports.mkdir(parents=True)
        (self.project / ".agentic-os" / "aos.db").write_bytes(b"")
        self.transcript = self.tmp / "transcript.jsonl"
        self.transcript.write_text('{"never": "opened"}\n', encoding="utf-8")
        self.staging = self.exports / "hook-staging"
        self.staged = self.staging / f"stop-{SID}.json"

    def stop_data(self, message, **over):
        data = {
            "session_id": SID,
            "cwd": str(self.project),
            "hook_event_name": "Stop",
            "last_assistant_message": message,
            "stop_hook_active": False,
            "background_tasks": [],
            "session_crons": [],
        }
        data.update(over)
        return data

    def end_data(self, reason="other", **over):
        data = {
            "session_id": SID,
            "cwd": str(self.project),
            "hook_event_name": "SessionEnd",
            "transcript_path": str(self.transcript),
            "reason": reason,
        }
        data.update(over)
        return data

    def stage_valid(self) -> None:
        code, out, err = run_hook(["stop"], self.stop_data(fenced(VALID_DROPFILE)))
        self.assertEqual(code, 0, err)
        self.assertTrue(self.staged.is_file())

    def staged_record(self) -> dict:
        return json.loads(self.staged.read_text(encoding="utf-8"))

    def exports_files(self) -> list[str]:
        return sorted(
            str(p.relative_to(self.exports))
            for p in self.exports.rglob("*")
            if p.is_file()
        )


# ---------------------------------------------------------------------------
# Stage 1 — Stop capture


class TestStopCapture(HookWorkspaceCase):
    def test_valid_envelope_staged_and_bound(self):
        code, out, err = run_hook(["stop"], self.stop_data(fenced(VALID_DROPFILE)))
        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("staged write-back envelope for T-0009", err)
        record = self.staged_record()
        self.assertEqual(record["format"], hooks.STAGED_FORMAT)
        self.assertEqual(record["session_id"], SID)
        self.assertEqual(record["envelope"], VALID_DROPFILE)
        self.assertEqual(record["envelope_sha256"], VALID_SHA)
        # The staged envelope is exactly what the manual parser accepts.
        doc = ingest.parse_dropfile(record["envelope"])
        self.assertEqual(doc["task"], "T-0009")

    def test_fence_at_end_of_message_without_trailing_newline_staged(self):
        # 2026-07-14 live-smoke shape (session 73f275be…): the final message
        # IS the envelope — the fence opens at position 0 and the string ends
        # immediately after the closing fence, with no trailing newline.
        # MULTILINE `$` must accept end-of-string, not demand a final newline.
        message = f"```{hooks.ENVELOPE_FENCE}\n{LIVE_SHAPE_VALID_BODY}```"
        self.assertFalse(message.endswith("\n"))
        code, out, err = run_hook(["stop"], self.stop_data(message))
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "")
        self.assertIn("staged write-back envelope for T-0009", err)
        record = self.staged_record()
        self.assertEqual(record["envelope"], LIVE_SHAPE_VALID_BODY)
        self.assertEqual(
            record["envelope_sha256"],
            utils.sha256_text(LIVE_SHAPE_VALID_BODY),
        )

    def test_fence_followed_by_one_trailing_newline_staged_identically(self):
        # The same valid envelope with one normal newline after the closing
        # fence stages byte-identically (same digest → same published name).
        message = f"```{hooks.ENVELOPE_FENCE}\n{LIVE_SHAPE_VALID_BODY}```\n"
        code, out, err = run_hook(["stop"], self.stop_data(message))
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "")
        record = self.staged_record()
        self.assertEqual(record["envelope"], LIVE_SHAPE_VALID_BODY)
        self.assertEqual(
            record["envelope_sha256"],
            utils.sha256_text(LIVE_SHAPE_VALID_BODY),
        )

    def test_missing_envelope_is_silent_noop(self):
        before = tree_snapshot(self.project)
        code, out, err = run_hook(
            ["stop"], self.stop_data("Final message without any envelope.")
        )
        self.assertEqual((code, out, err), (0, "", ""))
        self.assertEqual(tree_snapshot(self.project), before)

    def test_indented_fence_is_no_envelope(self):
        # An indented fence is not a fence per the protocol (column 0 is
        # required), so this is no envelope attempt at all: silent no-op.
        message = "  ```aos-dropfile\n# AOS DROPFILE\n  ```"
        code, out, err = run_hook(["stop"], self.stop_data(message))
        self.assertEqual((code, out, err), (0, "", ""))
        self.assertFalse(self.staged.exists())

    def test_no_workspace_is_clean_noop(self):
        outside = self.tmp / "plain"
        outside.mkdir()
        code, out, err = run_hook(
            ["stop"],
            self.stop_data(fenced(VALID_DROPFILE), cwd=str(outside)),
        )
        self.assertEqual((code, out, err), (0, "", ""))
        self.assertEqual(list(outside.rglob("*")), [])

    def test_missing_last_assistant_message_is_noop(self):
        data = self.stop_data("x")
        del data["last_assistant_message"]
        code, out, err = run_hook(["stop"], data)
        self.assertEqual((code, out, err), (0, "", ""))

    def test_restaging_latest_envelope_wins(self):
        self.stage_valid()
        second = dropfile(summary="A better final summary.")
        code, _, err = run_hook(["stop"], self.stop_data(fenced(second)))
        self.assertEqual(code, 0, err)
        record = self.staged_record()
        self.assertEqual(record["envelope"], second)
        self.assertEqual(record["envelope_sha256"], utils.sha256_text(second))
        # Identical re-stage: still exit 0, still exactly one record.
        code, _, err = run_hook(["stop"], self.stop_data(fenced(second)))
        self.assertEqual(code, 0, err)
        self.assertIn("already staged", err)
        self.assertEqual(
            [p.name for p in self.staging.iterdir()], [f"stop-{SID}.json"]
        )

    def test_at_most_one_staged_record_per_session(self):
        self.stage_valid()
        run_hook(["stop"], self.stop_data(fenced(dropfile(summary="Two."))))
        run_hook(["stop"], self.stop_data(fenced(dropfile(summary="Three."))))
        self.assertEqual(len(list(self.staging.iterdir())), 1)

    def test_stop_never_blocks_stdout_empty_exit_never_2(self):
        scenarios = [
            self.stop_data(fenced(VALID_DROPFILE)),
            self.stop_data("no envelope"),
            self.stop_data(fenced(VALID_DROPFILE) + fenced(VALID_DROPFILE)),
            self.stop_data(fenced("# AOS DROPFILE\nbroken\n")),
            self.stop_data(fenced(dropfile(summary=f"token {FAKE_TOKEN}"))),
            self.stop_data(fenced(VALID_DROPFILE), hook_event_name="Nope"),
            self.stop_data(fenced(VALID_DROPFILE), session_id="../evil"),
        ]
        for index, data in enumerate(scenarios):
            with self.subTest(index=index):
                code, out, _ = run_hook(["stop"], data)
                self.assertEqual(out, "")
                self.assertIn(code, (0, 1))
        code, out, _ = run_hook(["stop"], raw=b"not json at all")
        self.assertEqual(out, "")
        self.assertEqual(code, 1)


class TestStopRefusals(HookWorkspaceCase):
    def assert_refused_nothing_staged(self, data=None, raw=None, expect=None):
        before = tree_snapshot(self.project)
        code, out, err = run_hook(["stop"], data=data, raw=raw)
        self.assertEqual(code, 1, err)
        self.assertEqual(out, "")
        if expect:
            self.assertIn(expect, err)
        self.assertEqual(tree_snapshot(self.project), before)
        return err

    def test_multiple_envelopes_refused(self):
        message = fenced(VALID_DROPFILE) + "\nand again\n" + fenced(VALID_DROPFILE)
        self.assert_refused_nothing_staged(
            data=self.stop_data(message), expect="2 aos-dropfile envelopes"
        )

    def test_unterminated_fence_is_a_refused_attempt(self):
        # A column-0 opening fence with no closing fence is an ATTEMPTED
        # envelope (e.g. a truncated write-back) — a loud refusal, never a
        # silent no-op that would drop the write-back on the floor.
        self.assert_refused_nothing_staged(
            data=self.stop_data("```aos-dropfile\n# AOS DROPFILE\nnever closed"),
            expect="never closed",
        )

    def test_content_after_closing_fence_refused(self):
        # The envelope must END the final message: closing fence at
        # end-of-string or before one final newline, nothing after it.
        for trailing in ("P.S. one more thing\n", "\n"):
            with self.subTest(trailing=trailing[:6]):
                self.assert_refused_nothing_staged(
                    data=self.stop_data(fenced(VALID_DROPFILE) + trailing),
                    expect="must end the final message",
                )

    def test_unterminated_fence_flood_refuses_in_bounded_time(self):
        # Adversarial input: many opening fences, none closed. Semantically
        # this is a refused multi-fence attempt (never a silent no-op) …
        message = "```aos-dropfile\n" * 5000
        code, out, err = run_hook(["stop"], self.stop_data(message))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("5000 aos-dropfile envelopes", err)
        self.assertFalse(self.staged.exists())
        # … and processing must stay LINEAR in the input size: at 16x the
        # size the old quadratic regex scan needed minutes; the ceiling
        # below is a deliberately loose upper bound (~1000x the observed
        # linear-scan time), not a tight timing assertion.
        flood = "```aos-dropfile\n" * 80000
        started = time.perf_counter()
        code, out, err = run_hook(["stop"], self.stop_data(flood))
        elapsed = time.perf_counter() - started
        self.assertEqual((code, out), (1, ""))
        self.assertIn("80000 aos-dropfile envelopes", err)
        self.assertLess(elapsed, 10.0)

    def test_refused_attempt_invalidates_previous_staging(self):
        # A later message that ATTEMPTS an envelope and is refused must
        # supersede the earlier staged envelope: SessionEnd never publishes
        # a result the session itself tried to replace.
        cases = {
            "malformed": fenced("# AOS DROPFILE\nbroken\n"),
            "secret": fenced(dropfile(summary=f"leak {FAKE_TOKEN}")),
            "multiple": fenced(VALID_DROPFILE) + "\nx\n" + fenced(VALID_DROPFILE),
            "incomplete": "```aos-dropfile\n# AOS DROPFILE\nnever closed",
            "oversized": fenced(
                dropfile(summary="a" * (ingest.MAX_DROPFILE_BYTES + 10))
            ),
        }
        for name, message in cases.items():
            with self.subTest(case=name):
                self.stage_valid()
                code, out, err = run_hook(["stop"], self.stop_data(message))
                self.assertEqual((code, out), (1, ""))
                self.assertIn("previously staged envelope", err)
                self.assertIn("invalidated", err)
                self.assertFalse(self.staged.exists())
                # The superseded envelope is never published:
                code, out, err = run_hook(["session-end"], self.end_data())
                self.assertEqual((code, out, err), (0, "", ""))
                self.assertEqual(self.exports_files(), [])

    def test_envelope_free_later_message_preserves_staging(self):
        # NO envelope in a later message stays a clean no-op — only an
        # attempted-and-refused (or valid) envelope supersedes the record.
        self.stage_valid()
        code, out, err = run_hook(
            ["stop"], self.stop_data("Just narration, no envelope at all.")
        )
        self.assertEqual((code, out, err), (0, "", ""))
        self.assertTrue(self.staged.is_file())
        code, _, err = run_hook(["session-end"], self.end_data())
        self.assertEqual(code, 0, err)
        self.assertEqual(self.exports_files(), [EXPECTED_NAME])

    def test_unpaired_surrogate_envelope_refused_as_diagnostic(self):
        # json may decode "\ud800" into a lone surrogate: the refusal must
        # be a deterministic HookRefusal, not an internal-error fallback.
        body = dropfile(summary="bad \ud800 char")
        err = self.assert_refused_nothing_staged(
            data=self.stop_data(fenced(body)),
            expect="unpaired Unicode surrogate",
        )
        self.assertNotIn("internal error", err)
        self.assertNotIn("Traceback", err)

    def test_malformed_stdin_refused(self):
        self.assert_refused_nothing_staged(raw=b"{ not json")
        self.assert_refused_nothing_staged(raw=b"\xff\xfe{}")
        self.assert_refused_nothing_staged(raw=b'["a", "list"]')

    def test_oversized_stdin_refused(self):
        raw = b'{"pad": "' + b"a" * (hooks.MAX_HOOK_INPUT_BYTES + 16) + b'"}'
        self.assert_refused_nothing_staged(raw=raw, expect="byte cap")

    def test_malformed_envelope_refused_without_echo(self):
        body = dropfile(outcome="excellent")
        err = self.assert_refused_nothing_staged(
            data=self.stop_data(fenced(body)), expect="not a valid dropfile"
        )
        self.assertNotIn("excellent", err)  # bad values are never echoed

    def test_live_smoke_sectionless_envelope_refuses_loudly(self):
        # The exact 2026-07-14 live-smoke payload: a well-fenced envelope
        # (no trailing newline after the closing fence) whose body omits the
        # required '## evidence' / '## open questions' headings. In an
        # initialized workspace this is a LOUD parse refusal — never a
        # silent exit 0, never a staged record. (The live run's silence had
        # a different cause: the smoke workspace lacked the
        # .agentic-os/aos.db discovery marker, so the documented workspace
        # no-op fired before extraction was even reached.)
        message = f"```{hooks.ENVELOPE_FENCE}\n{LIVE_SECTIONLESS_BODY}```"
        err = self.assert_refused_nothing_staged(
            data=self.stop_data(message), expect="not a valid dropfile"
        )
        self.assertIn("'## evidence'", err)  # names the missing heading
        self.assertNotIn("smoke completed", err)  # values never echoed

    def test_oversized_envelope_refused(self):
        body = dropfile(summary="a" * (ingest.MAX_DROPFILE_BYTES + 10))
        self.assert_refused_nothing_staged(
            data=self.stop_data(fenced(body)), expect="max"
        )

    def test_secret_envelope_refused_without_secret_echo(self):
        body = dropfile(summary=f"the token is {FAKE_TOKEN}")
        err = self.assert_refused_nothing_staged(
            data=self.stop_data(fenced(body)), expect="secret-shaped"
        )
        self.assertIn("github-token", err)  # pattern NAME only
        self.assertNotIn(FAKE_TOKEN, err)

    def test_secret_shaped_agent_refused_by_both_boundaries(self):
        # The agent field lands in diagnostics and the published filename,
        # so it gets the same secret-shape judgment as every other
        # model-controlled field — at the hook AND at manual ingest (shared
        # secret_findings), so everything ingest accepts still publishes.
        body = dropfile().replace("agent: claude-code", f"agent: {FAKE_TOKEN}")
        err = self.assert_refused_nothing_staged(
            data=self.stop_data(fenced(body)), expect="secret-shaped"
        )
        self.assertIn("in agent", err)
        self.assertNotIn(FAKE_TOKEN, err)  # named by field, never by value
        # Manual-ingest parity: the same document is refused there too.
        doc = ingest.parse_dropfile(body)
        self.assertTrue(
            any("in agent" in finding for finding in ingest.secret_findings(doc))
        )

    def test_secret_in_evidence_and_question_refused(self):
        for body in (
            dropfile(evidence=[f"- kind: note | ref: {FAKE_TOKEN} | claim: c"]),
            dropfile(questions=[f"- rotate {FAKE_TOKEN}?"]),
        ):
            with self.subTest(body=body[:60]):
                err = self.assert_refused_nothing_staged(
                    data=self.stop_data(fenced(body))
                )
                self.assertNotIn(FAKE_TOKEN, err)

    def test_official_event_name_and_type_validation(self):
        self.assert_refused_nothing_staged(
            data=self.stop_data(fenced(VALID_DROPFILE), hook_event_name="SessionEnd"),
            expect="expected a Stop event",
        )
        data = self.stop_data(fenced(VALID_DROPFILE))
        del data["hook_event_name"]
        self.assert_refused_nothing_staged(data=data)
        self.assert_refused_nothing_staged(
            data=self.stop_data("x", last_assistant_message=["not", "a", "string"]),
            expect="not a string",
        )
        data = self.stop_data(fenced(VALID_DROPFILE))
        del data["cwd"]
        self.assert_refused_nothing_staged(data=data, expect="cwd")

    def test_path_traversal_session_ids_refused(self):
        for bad in ("../../evil", "a/b", "..", "x", "", 42, None, "a" * 300,
                    "dot.dot", "under_score"):
            with self.subTest(session_id=bad):
                err = self.assert_refused_nothing_staged(
                    data=self.stop_data(fenced(VALID_DROPFILE), session_id=bad),
                    expect="session_id",
                )
                if isinstance(bad, str) and bad:
                    self.assertNotIn(bad, err)  # never echoed

    def test_symlinked_staging_dir_refused(self):
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        self.staging.symlink_to(elsewhere)
        code, out, err = run_hook(["stop"], self.stop_data(fenced(VALID_DROPFILE)))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("not a real directory", err)
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_symlinked_exports_dir_refused(self):
        elsewhere = self.tmp / "elsewhere"
        elsewhere.mkdir()
        self.exports.rmdir()
        self.exports.symlink_to(elsewhere)
        code, _, err = run_hook(["stop"], self.stop_data(fenced(VALID_DROPFILE)))
        self.assertEqual(code, 1)
        self.assertIn("not a real directory", err)
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_staging_write_failure_leaves_no_partial(self):
        with mock.patch("os.replace", side_effect=PermissionError("denied")):
            code, out, err = run_hook(
                ["stop"], self.stop_data(fenced(VALID_DROPFILE))
            )
        self.assertEqual((code, out), (1, ""))
        self.assertIn("no partial record", err)
        self.assertFalse(self.staged.exists())
        leftovers = [p for p in self.staging.iterdir()]
        self.assertEqual(leftovers, [])


# ---------------------------------------------------------------------------
# Stage 2 — SessionEnd publication


class TestSessionEndPublish(HookWorkspaceCase):
    def test_valid_publication(self):
        self.stage_valid()
        code, out, err = run_hook(["session-end"], self.end_data())
        self.assertEqual(code, 0, err)
        self.assertEqual(out, "")
        self.assertIn("published", err)
        self.assertIn("Ingest stays manual", err)
        final = self.exports / EXPECTED_NAME
        self.assertTrue(final.is_file())
        self.assertEqual(final.read_bytes(), VALID_DROPFILE.encode("utf-8"))
        self.assertFalse(self.staged.exists())  # verified publication → removed
        self.assertEqual(self.exports_files(), [EXPECTED_NAME])

    def test_every_documented_reason_publishes(self):
        for reason in hooks.SESSION_END_REASONS:
            with self.subTest(reason=reason):
                self.stage_valid()
                code, _, err = run_hook(
                    ["session-end"], self.end_data(reason=reason)
                )
                self.assertEqual(code, 0, err)
                (self.exports / EXPECTED_NAME).unlink()

    def test_no_staged_record_is_silent_noop(self):
        before = tree_snapshot(self.project)
        code, out, err = run_hook(["session-end"], self.end_data())
        self.assertEqual((code, out, err), (0, "", ""))
        self.assertEqual(tree_snapshot(self.project), before)

    def test_no_workspace_is_clean_noop(self):
        outside = self.tmp / "plain"
        outside.mkdir()
        code, out, err = run_hook(
            ["session-end"], self.end_data(cwd=str(outside))
        )
        self.assertEqual((code, out, err), (0, "", ""))

    def test_outside_workspace_unknown_reason_is_clean_noop(self):
        # The workspace no-op gate fires BEFORE workspace-specific content
        # validation: outside any initialized workspace, even an unknown
        # reason is a clean silent no-op.
        outside = self.tmp / "plain"
        outside.mkdir()
        for reason in ("shutdown-xyzzy", "", None, 5):
            with self.subTest(reason=reason):
                code, out, err = run_hook(
                    ["session-end"],
                    self.end_data(cwd=str(outside), reason=reason),
                )
                self.assertEqual((code, out, err), (0, "", ""))
        self.assertEqual(list(outside.rglob("*")), [])
        # Reason validation is NOT weakened for initialized workspaces:
        code, _, err = run_hook(
            ["session-end"], self.end_data(reason="shutdown-xyzzy")
        )
        self.assertEqual(code, 1)
        self.assertIn("unsupported SessionEnd reason", err)

    def test_duplicate_retry_is_idempotent(self):
        self.stage_valid()
        self.assertEqual(run_hook(["session-end"], self.end_data())[0], 0)
        # Retry after successful publication: staged record gone → no-op.
        code, out, err = run_hook(["session-end"], self.end_data())
        self.assertEqual((code, out, err), (0, "", ""))
        # Retry with the staged record still present (removal raced): the
        # identical published bytes count as success, not a duplicate.
        self.stage_valid()
        code, _, err = run_hook(["session-end"], self.end_data())
        self.assertEqual(code, 0, err)
        self.assertIn("already published", err)
        self.assertFalse(self.staged.exists())
        self.assertEqual(self.exports_files(), [EXPECTED_NAME])

    def test_deterministic_filename_carries_dedupe_identity(self):
        self.stage_valid()
        run_hook(["session-end"], self.end_data())
        final = self.exports / EXPECTED_NAME
        digest = utils.sha256_bytes(final.read_bytes())
        self.assertEqual(digest, VALID_SHA)
        self.assertIn(digest[:12], final.name)
        self.assertIn(SID[:8], final.name)
        # Same session + same envelope in a fresh workspace → same name.
        doc = ingest.parse_dropfile(VALID_DROPFILE)
        self.assertEqual(hooks.dropfile_name(doc, SID, digest), EXPECTED_NAME)

    def test_overlong_task_and_agent_publish_bounded_names_without_echo(self):
        # Protocol-valid envelopes with very long task/agent values (the
        # parser bounds their charset, not their length) must publish at a
        # deterministic name bounded far below filesystem NAME_MAX, and the
        # raw values must never be echoed in diagnostics.
        long_agent = "a" * 300
        long_task = "T-" + "0" * 300 + "9"
        cases = (
            ("agent", "T-0009", long_agent, long_agent),
            ("task", long_task, "claude-code", long_task),
        )
        for label, task, agent, overlong in cases:
            with self.subTest(component=label):
                body = (
                    "# AOS DROPFILE\n"
                    f"task: {task}\n"
                    f"agent: {agent}\n"
                    "outcome: success\n"
                    "summary: Bounded published-name regression.\n"
                    "\n## evidence\n\n## open questions\n"
                )
                code, _, err = run_hook(["stop"], self.stop_data(fenced(body)))
                self.assertEqual(code, 0, err)
                self.assertNotIn(overlong, err)  # raw value never echoed
                code, _, err = run_hook(["session-end"], self.end_data())
                self.assertEqual(code, 0, err)
                self.assertNotIn(overlong, err)
                digest = utils.sha256_text(body)
                doc = ingest.parse_dropfile(body)
                name = hooks.dropfile_name(doc, SID, digest)
                # Deterministic, bounded independently of field lengths,
                # still carrying the session and dedupe identities:
                self.assertLessEqual(len(name.encode("utf-8")), 160)
                self.assertIn(SID[:8], name)
                self.assertIn(digest[:12], name)
                final = self.exports / name
                self.assertTrue(final.is_file(), name)
                self.assertEqual(final.read_bytes(), body.encode("utf-8"))
                self.assertFalse(self.staged.exists())
                # Idempotent retry at the same deterministic name:
                code, _, err = run_hook(["stop"], self.stop_data(fenced(body)))
                self.assertEqual(code, 0, err)
                code, _, err = run_hook(["session-end"], self.end_data())
                self.assertEqual(code, 0, err)
                self.assertIn("already published", err)

    def test_short_names_keep_the_documented_format(self):
        # The visible format is unchanged for every normal-length value:
        # dropfile-<task>-<agent>-hook-<session8>-<sha12>.md
        doc = ingest.parse_dropfile(VALID_DROPFILE)
        self.assertEqual(
            hooks.dropfile_name(doc, SID, VALID_SHA), EXPECTED_NAME
        )

    def test_success_with_zero_evidence_still_publishes(self):
        # U-H2 is excluded: no new evidence-for-success rule exists here.
        body = dropfile(outcome="success", evidence=[])
        code, _, err = run_hook(["stop"], self.stop_data(fenced(body)))
        self.assertEqual(code, 0, err)
        code, _, err = run_hook(["session-end"], self.end_data())
        self.assertEqual(code, 0, err)
        self.assertEqual(len(self.exports_files()), 1)

    def test_transcript_never_opened_and_no_foreign_reads(self):
        self.stage_valid()
        (self.project / "decoy-notes.md").write_text("workspace file")
        opened: list[str] = []
        real_open, real_os_open = builtins.open, os.open

        def rec_open(file, *args, **kwargs):
            opened.append(str(file))
            return real_open(file, *args, **kwargs)

        def rec_os_open(path, *args, **kwargs):
            if not isinstance(path, int):
                opened.append(os.fsdecode(path))
            return real_os_open(path, *args, **kwargs)

        with mock.patch("builtins.open", rec_open), \
                mock.patch("io.open", rec_open), \
                mock.patch("os.open", rec_os_open):
            code, _, err = run_hook(["session-end"], self.end_data())
        self.assertEqual(code, 0, err)
        self.assertNotIn(str(self.transcript), opened)
        exports_prefix = str(self.exports) + os.sep
        for path in opened:
            if path.startswith(str(self.project)):
                self.assertTrue(
                    path == str(self.exports)  # the dir itself (fsync)
                    or path.startswith(exports_prefix),
                    f"read outside owned exports paths: {path}",
                )

    def test_no_subprocess_sqlite_or_network(self):
        with mock.patch("subprocess.Popen", side_effect=AssertionError("popen")), \
                mock.patch("subprocess.run", side_effect=AssertionError("run")), \
                mock.patch("os.system", side_effect=AssertionError("system")), \
                mock.patch("sqlite3.connect", side_effect=AssertionError("sqlite")), \
                mock.patch("socket.socket", side_effect=AssertionError("socket")):
            code, _, err = run_hook(
                ["stop"], self.stop_data(fenced(VALID_DROPFILE))
            )
            self.assertEqual(code, 0, err)
            code, _, err = run_hook(["session-end"], self.end_data())
            self.assertEqual(code, 0, err)
        self.assertEqual(self.exports_files(), [EXPECTED_NAME])


class TestSessionEndRefusals(HookWorkspaceCase):
    def assert_refused_retained(self, data=None, expect=None):
        before = tree_snapshot(self.project)
        code, out, err = run_hook(["session-end"], data or self.end_data())
        self.assertEqual(code, 1, err)
        self.assertEqual(out, "")
        if expect:
            self.assertIn(expect, err)
        self.assertEqual(tree_snapshot(self.project), before)
        return err

    def test_wrong_event_name_refused(self):
        self.stage_valid()
        self.assert_refused_retained(
            data=self.end_data(hook_event_name="Stop"),
            expect="expected a SessionEnd event",
        )

    def test_undocumented_reason_refused_without_echo(self):
        self.stage_valid()
        for reason in ("shutdown-xyzzy", "", 5, None, ["clear"]):
            with self.subTest(reason=reason):
                err = self.assert_refused_retained(
                    data=self.end_data(reason=reason),
                    expect="unsupported SessionEnd reason",
                )
                if isinstance(reason, str) and reason:
                    self.assertNotIn(reason, err)

    def test_session_binding_mismatch_refused(self):
        self.stage_valid()
        record = self.staged_record()
        record["session_id"] = OTHER_SID
        self.staged.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n"
        )
        self.assert_refused_retained(expect="not bound to this session")

    def test_other_sessions_record_untouched(self):
        self.stage_valid()
        code, out, err = run_hook(
            ["session-end"], self.end_data(session_id=OTHER_SID)
        )
        self.assertEqual((code, out, err), (0, "", ""))  # no record for B
        self.assertTrue(self.staged.is_file())  # A's record untouched

    def test_replaced_staging_digest_refused(self):
        self.stage_valid()
        record = self.staged_record()
        record["envelope"] = dropfile(summary="Swapped after staging.")
        self.staged.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n"
        )
        self.assert_refused_retained(expect="digest does not match")

    def test_unrecognized_format_marker_refused(self):
        self.stage_valid()
        record = self.staged_record()
        record["format"] = "somebody-else/9"
        self.staged.write_text(json.dumps(record) + "\n")
        self.assert_refused_retained(expect="format marker")

    def test_malformed_staged_json_refused(self):
        self.staging.mkdir(parents=True, exist_ok=True)
        self.staged.write_text("{ not json")
        self.assert_refused_retained(expect="not valid JSON")

    def test_secret_smuggled_into_staging_refused_at_publication(self):
        # Digest-valid but secret-bearing: the pre-publication re-validation
        # must catch what a tampered staging tries to smuggle through.
        self.stage_valid()
        record = self.staged_record()
        bad = dropfile(summary=f"leak {FAKE_TOKEN}")
        record["envelope"] = bad
        record["envelope_sha256"] = utils.sha256_text(bad)
        self.staged.write_text(
            json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        )
        err = self.assert_refused_retained(expect="secret-shaped")
        self.assertNotIn(FAKE_TOKEN, err)

    def test_surrogate_in_staged_envelope_refused_with_recovery_pointer(self):
        # A tampered staged record can smuggle a "\ud800" JSON escape past
        # decoding; the SessionEnd re-validation must refuse it as a
        # deterministic diagnostic (never an internal-error traceback),
        # retain the record, and point at it for manual recovery.
        self.stage_valid()
        record = self.staged_record()
        record["envelope"] = "# AOS DROPFILE\nbad \ud800\n"
        self.staged.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        err = self.assert_refused_retained(expect="unpaired Unicode surrogate")
        self.assertIn(f"Inspect and remove it manually: {self.staged}", err)
        self.assertNotIn("internal error", err)
        self.assertNotIn("Traceback", err)

    def test_staged_symlink_refused(self):
        target = self.tmp / "outside.json"
        target.write_text("{}")
        self.staging.mkdir(parents=True, exist_ok=True)
        self.staged.symlink_to(target)
        self.assert_refused_retained(expect="not a regular file")

    def recovery_pointer(self) -> str:
        return f"Inspect and remove it manually: {self.staged}"

    def test_uninspectable_staging_refuses_not_noop(self):
        # The failure is injected for the STAGED RECORD's path only — the
        # owned exports/hook-staging directories still inspect fine, so
        # this exercises the staged-record ENOENT-versus-other-error branch
        # itself (a wholesale os.lstat patch would trip the exports
        # directory check first and never reach that branch).
        self.stage_valid()
        real_lstat = os.lstat

        def lstat_denying_staged(path, *args, **kwargs):
            if os.fsdecode(path) == str(self.staged):
                raise PermissionError(13, "denied")
            return real_lstat(path, *args, **kwargs)

        with mock.patch("os.lstat", side_effect=lstat_denying_staged):
            code, out, err = run_hook(["session-end"], self.end_data())
        self.assertEqual((code, out), (1, ""))
        self.assertIn("cannot inspect the staged record", err)
        self.assertIn(self.recovery_pointer(), err)
        self.assertTrue(self.staged.is_file())  # retained
        self.assertEqual(
            self.exports_files(), [f"hook-staging/stop-{SID}.json"]
        )  # no dropfile was published

        # Only ENOENT reads as absence — that branch stays a clean no-op:
        def lstat_vanishing_staged(path, *args, **kwargs):
            if os.fsdecode(path) == str(self.staged):
                raise FileNotFoundError(2, "gone")
            return real_lstat(path, *args, **kwargs)

        with mock.patch("os.lstat", side_effect=lstat_vanishing_staged):
            code, out, err = run_hook(["session-end"], self.end_data())
        self.assertEqual((code, out, err), (0, "", ""))
        self.assertTrue(self.staged.is_file())  # untouched either way

    def test_unopenable_staged_record_refuses_with_recovery_pointer(self):
        # A staged-record OPEN failure retains the record and must carry
        # the same recovery pointer as every other staged-record refusal.
        self.stage_valid()
        real_os_open = os.open

        def open_denying_staged(path, *args, **kwargs):
            if not isinstance(path, int) and os.fsdecode(path) == str(self.staged):
                raise PermissionError(13, "denied")
            return real_os_open(path, *args, **kwargs)

        with mock.patch("os.open", side_effect=open_denying_staged):
            code, out, err = run_hook(["session-end"], self.end_data())
        self.assertEqual((code, out), (1, ""))
        self.assertIn("cannot open the staged record", err)
        self.assertIn(self.recovery_pointer(), err)
        self.assertTrue(self.staged.is_file())
        self.assertEqual(
            self.exports_files(), [f"hook-staging/stop-{SID}.json"]
        )

    def test_oversized_staged_record_refuses_with_recovery_pointer(self):
        # A staged-record OVERSIZE failure likewise retains and points.
        self.staging.mkdir(parents=True, exist_ok=True)
        self.staged.write_bytes(b"x" * (hooks.MAX_STAGED_RECORD_BYTES + 1))
        code, out, err = run_hook(["session-end"], self.end_data())
        self.assertEqual((code, out), (1, ""))
        self.assertIn("byte cap", err)
        self.assertIn(self.recovery_pointer(), err)
        self.assertTrue(self.staged.is_file())
        self.assertEqual(
            self.exports_files(), [f"hook-staging/stop-{SID}.json"]
        )

    def test_atomic_write_failure_leaves_no_partial_dropfile(self):
        self.stage_valid()
        with mock.patch("os.link", side_effect=PermissionError("denied")):
            code, out, err = run_hook(["session-end"], self.end_data())
        self.assertEqual((code, out), (1, ""))
        self.assertIn("no partial file", err)
        self.assertFalse((self.exports / EXPECTED_NAME).exists())
        self.assertEqual(
            [p.name for p in self.exports.iterdir()], ["hook-staging"]
        )  # no temp litter
        self.assertTrue(self.staged.is_file())  # retained for retry

    def test_existing_different_file_at_name_refused(self):
        self.stage_valid()
        final = self.exports / EXPECTED_NAME
        final.write_bytes(b"something else entirely\n")
        self.assert_refused_retained(expect="different file already exists")

    def test_existing_symlink_at_name_refused(self):
        self.stage_valid()
        target = self.tmp / "outside.md"
        target.write_bytes(VALID_DROPFILE.encode("utf-8"))
        (self.exports / EXPECTED_NAME).symlink_to(target)
        self.assert_refused_retained(expect="not a regular file")
        self.assertEqual(target.read_bytes(), VALID_DROPFILE.encode("utf-8"))


# ---------------------------------------------------------------------------
# Runner entrypoint (process-level smoke: the exact wiring install uses)


class TestRunnerProcess(HookWorkspaceCase):
    def test_aos_hooks_runner_stages_and_publishes(self):
        runner = REPO_ROOT / "aos_hooks.py"
        stop = subprocess.run(
            [sys.executable, str(runner), "stop"],
            input=json.dumps(self.stop_data(fenced(VALID_DROPFILE))).encode(),
            capture_output=True,
            cwd=self.tmp,
            timeout=60,
        )
        self.assertEqual(stop.returncode, 0, stop.stderr)
        self.assertEqual(stop.stdout, b"")  # never a decision on stdout
        end = subprocess.run(
            [sys.executable, str(runner), "session-end"],
            input=json.dumps(self.end_data()).encode(),
            capture_output=True,
            cwd=self.tmp,
            timeout=60,
        )
        self.assertEqual(end.returncode, 0, end.stderr)
        self.assertEqual(end.stdout, b"")
        self.assertTrue((self.exports / EXPECTED_NAME).is_file())

    def test_runner_rejects_unknown_stage(self):
        code, out, err = run_hook(["unknown-stage"], raw=b"{}")
        self.assertEqual((code, out), (1, ""))
        self.assertIn("usage", err)


# ---------------------------------------------------------------------------
# Installer


class InstallerCase(unittest.TestCase):
    BASE_SETTINGS = {
        "model": "opus",
        "permissions": {"allow": ["Bash(ls:*)"]},
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "echo pre"}],
                }
            ],
            "Stop": [
                {"hooks": [{"type": "command", "command": "echo user-stop"}]}
            ],
        },
    }

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.claude_dir = self.tmp / "claude"
        self.claude_dir.mkdir()
        self.settings = self.claude_dir / "settings.json"

    def write_settings(self, doc) -> bytes:
        text = json.dumps(doc, indent=2) + "\n"
        self.settings.write_text(text, encoding="utf-8")
        return text.encode("utf-8")

    def cli(self, *argv, stdin_reply=None):
        if stdin_reply is None:
            return run_cli(*argv)
        with mock.patch("builtins.input", return_value=stdin_reply):
            return run_cli(*argv)

    def hooks_cmd(self, *argv, stdin_reply=None):
        return self.cli(*argv, "--settings", str(self.settings),
                        stdin_reply=stdin_reply)

    def backups(self) -> list[Path]:
        return sorted(self.claude_dir.glob("settings.json.aos-backup-*"))

    def parsed(self) -> dict:
        return json.loads(self.settings.read_text(encoding="utf-8"))

    def owned_commands(self, doc, event) -> list[str]:
        return [
            entry["command"]
            for group in doc.get("hooks", {}).get(event, [])
            for entry in group.get("hooks", [])
            if hooks.RUNNER_FILENAME in entry.get("command", "")
        ]


class TestInstallerDryRun(InstallerCase):
    def test_dry_run_is_default_prints_exact_diff_and_mutates_nothing(self):
        original = self.write_settings(self.BASE_SETTINGS)
        before = tree_snapshot(self.claude_dir)
        code, out, err = self.hooks_cmd("hooks", "install")
        self.assertEqual(code, 0, err)
        self.assertIn("Dry run: nothing was changed", out)
        self.assertIn(hooks.hook_command("Stop"), out)
        self.assertIn(hooks.hook_command("SessionEnd"), out)
        self.assertIn("+++", out)  # unified diff format
        self.assertEqual(tree_snapshot(self.claude_dir), before)
        self.assertEqual(self.settings.read_bytes(), original)
        self.assertEqual(self.backups(), [])
        # Deterministic: a second dry run prints the identical plan.
        code2, out2, _ = self.hooks_cmd("hooks", "install")
        self.assertEqual((code, out), (code2, out2))

    def test_explicit_dry_run_flag_matches_default(self):
        self.write_settings(self.BASE_SETTINGS)
        _, default_out, _ = self.hooks_cmd("hooks", "install")
        _, flagged_out, _ = self.hooks_cmd("hooks", "install", "--dry-run")
        self.assertEqual(default_out, flagged_out)

    def test_both_modes_refused(self):
        self.write_settings(self.BASE_SETTINGS)
        code, _, err = self.hooks_cmd("hooks", "install", "--dry-run", "--apply")
        self.assertEqual(code, 1)
        self.assertIn("not both", err)


class TestInstallerApply(InstallerCase):
    def test_apply_requires_explicit_confirmation(self):
        original = self.write_settings(self.BASE_SETTINGS)
        for reply in ("no", "", "y", "YES please"):
            with self.subTest(reply=reply):
                code, _, err = self.hooks_cmd(
                    "hooks", "install", "--apply", stdin_reply=reply
                )
                self.assertEqual(code, 1)
                self.assertIn("Not confirmed", err)
                self.assertEqual(self.settings.read_bytes(), original)
                self.assertEqual(self.backups(), [])
        with mock.patch("builtins.input", side_effect=EOFError):
            code, _, err = run_cli(
                "hooks", "install", "--apply", "--settings", str(self.settings)
            )
        self.assertEqual(code, 1)
        self.assertEqual(self.settings.read_bytes(), original)

    def test_apply_backs_up_merges_and_preserves_unrelated_settings(self):
        original = self.write_settings(self.BASE_SETTINGS)
        code, out, err = self.hooks_cmd(
            "hooks", "install", "--apply", stdin_reply="yes"
        )
        self.assertEqual(code, 0, err)
        backups = self.backups()
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertIn("backup:", out)
        doc = self.parsed()
        self.assertEqual(doc["model"], "opus")
        self.assertEqual(doc["permissions"], self.BASE_SETTINGS["permissions"])
        self.assertEqual(
            doc["hooks"]["PreToolUse"],
            self.BASE_SETTINGS["hooks"]["PreToolUse"],
        )
        # User's Stop hook first and intact; ours appended last.
        self.assertEqual(
            doc["hooks"]["Stop"][0],
            self.BASE_SETTINGS["hooks"]["Stop"][0],
        )
        self.assertEqual(
            self.owned_commands(doc, "Stop"), [hooks.hook_command("Stop")]
        )
        self.assertEqual(
            self.owned_commands(doc, "SessionEnd"),
            [hooks.hook_command("SessionEnd")],
        )

    def test_repeated_install_is_idempotent(self):
        self.write_settings(self.BASE_SETTINGS)
        self.hooks_cmd("hooks", "install", "--apply", stdin_reply="yes")
        after_first = self.settings.read_bytes()
        code, out, err = self.hooks_cmd(
            "hooks", "install", "--apply", stdin_reply="yes"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("nothing to do", out)
        self.assertEqual(self.settings.read_bytes(), after_first)
        self.assertEqual(len(self.backups()), 1)  # no second backup
        doc = self.parsed()
        self.assertEqual(len(self.owned_commands(doc, "Stop")), 1)
        self.assertEqual(len(self.owned_commands(doc, "SessionEnd")), 1)

    def test_apply_creates_fresh_settings_when_absent(self):
        code, out, err = self.hooks_cmd(
            "hooks", "install", "--apply", stdin_reply="yes"
        )
        self.assertEqual(code, 0, err)
        self.assertNotIn("backup:", out)  # nothing existed to back up
        doc = self.parsed()
        self.assertEqual(set(doc), {"hooks"})
        mode = stat.S_IMODE(os.lstat(self.settings).st_mode)
        self.assertEqual(mode, 0o600)

    def test_missing_parent_directory_refused(self):
        missing = self.tmp / "nowhere" / "settings.json"
        code, _, err = self.cli(
            "hooks", "install", "--apply", "--settings", str(missing),
            stdin_reply="yes",
        )
        self.assertEqual(code, 1)
        self.assertIn("does not exist", err)
        self.assertFalse(missing.parent.exists())


class TestInstallerStatus(InstallerCase):
    def test_absent_installed_drifted(self):
        # absent: no file at all
        code, out, _ = self.hooks_cmd("hooks", "status")
        self.assertEqual(code, 0)
        self.assertIn("state: absent", out)
        # absent: file without AOS entries
        self.write_settings(self.BASE_SETTINGS)
        _, out, _ = self.hooks_cmd("hooks", "status")
        self.assertIn("state: absent", out)
        # installed (with version + digest)
        self.hooks_cmd("hooks", "install", "--apply", stdin_reply="yes")
        _, out, _ = self.hooks_cmd("hooks", "status")
        self.assertIn("state: installed", out)
        self.assertIn(f"version: {hooks.HOOK_PROTOCOL_VERSION}", out)
        self.assertIn(f"digest: {hooks.install_digest()}", out)
        # drifted: owned command differs from this checkout's expected one
        doc = self.parsed()
        for group in doc["hooks"]["Stop"]:
            for entry in group["hooks"]:
                if hooks.RUNNER_FILENAME in entry["command"]:
                    entry["command"] += " --extra-flag"
        self.write_settings(doc)
        _, out, _ = self.hooks_cmd("hooks", "status")
        self.assertIn("state: drifted", out)
        # drifted: one owned handler missing entirely
        doc = self.parsed()
        del doc["hooks"]["SessionEnd"]
        self.write_settings(doc)
        _, out, _ = self.hooks_cmd("hooks", "status")
        self.assertIn("state: drifted", out)

    def test_drifted_install_heals_to_exactly_one_entry_per_event(self):
        self.write_settings(self.BASE_SETTINGS)
        self.hooks_cmd("hooks", "install", "--apply", stdin_reply="yes")
        doc = self.parsed()
        doc["hooks"]["Stop"].append(
            {"hooks": [{"type": "command",
                        "command": "python3 /old/checkout/aos_hooks.py stop"}]}
        )
        self.write_settings(doc)
        self.hooks_cmd("hooks", "install", "--apply", stdin_reply="yes")
        healed = self.parsed()
        self.assertEqual(
            self.owned_commands(healed, "Stop"), [hooks.hook_command("Stop")]
        )
        _, out, _ = self.hooks_cmd("hooks", "status")
        self.assertIn("state: installed", out)


class TestInstallerUninstall(InstallerCase):
    def test_uninstall_dry_run_mutates_nothing(self):
        self.write_settings(self.BASE_SETTINGS)
        self.hooks_cmd("hooks", "install", "--apply", stdin_reply="yes")
        installed = self.settings.read_bytes()
        code, out, err = self.hooks_cmd("hooks", "uninstall")
        self.assertEqual(code, 0, err)
        self.assertIn("Dry run: nothing was changed", out)
        self.assertEqual(self.settings.read_bytes(), installed)

    def test_uninstall_removes_only_owned_handlers(self):
        self.write_settings(self.BASE_SETTINGS)
        self.hooks_cmd("hooks", "install", "--apply", stdin_reply="yes")
        code, _, err = self.hooks_cmd(
            "hooks", "uninstall", "--apply", stdin_reply="yes"
        )
        self.assertEqual(code, 0, err)
        # Semantic round-trip: exactly the pre-install document again
        # (our removal also drops the SessionEnd array it emptied).
        self.assertEqual(self.parsed(), self.BASE_SETTINGS)

    def test_uninstall_on_clean_settings_is_noop(self):
        original = self.write_settings(self.BASE_SETTINGS)
        code, out, err = self.hooks_cmd(
            "hooks", "uninstall", "--apply", stdin_reply="yes"
        )
        self.assertEqual(code, 0, err)
        self.assertIn("nothing to do", out)
        self.assertEqual(self.settings.read_bytes(), original)


class TestInstallerOwnership(InstallerCase):
    """F12: ownership is the exact AOS-generated command shape
    (`python3 <path>/aos_hooks.py stop|session-end`), never a substring —
    user commands that merely mention the filename are never claimed."""

    LOOKALIKES = [
        {"type": "command", "command": "python3 /home/user/my-aos_hooks.py stop"},
        {"type": "command", "command": "echo aos_hooks.py run finished"},
    ]

    def lookalike_settings(self) -> dict:
        return {"hooks": {"Stop": [{"hooks": [dict(e) for e in self.LOOKALIKES]}]}}

    def test_ownership_requires_the_exact_generated_command_shape(self):
        self.assertTrue(hooks.is_owned(hooks.owned_entry("Stop")))
        self.assertTrue(hooks.is_owned(hooks.owned_entry("SessionEnd")))
        # A moved/old checkout is still ours: healing must converge it.
        self.assertTrue(hooks.is_owned(
            {"type": "command",
             "command": "python3 /old/checkout/aos_hooks.py stop"}
        ))
        # A drifted-but-ours command (extra args) is still recognized, so
        # `status` can report drift instead of misreading it as absent.
        self.assertTrue(hooks.is_owned(
            {"type": "command",
             "command": hooks.hook_command("Stop") + " --extra-flag"}
        ))
        for command in (
            "echo aos_hooks.py run finished",
            "echo remember aos_hooks.py stop",
            "python3 /home/user/my-aos_hooks.py stop",
            "bash aos_hooks.py stop",
            "python3 /x/aos_hooks.py",
            "python3 /x/aos_hooks.py backup",
            "python3 'unterminated quote aos_hooks.py stop",
            "",
        ):
            with self.subTest(command=command):
                self.assertFalse(
                    hooks.is_owned({"type": "command", "command": command})
                )

    def test_install_healing_preserves_lookalike_user_commands(self):
        self.write_settings(self.lookalike_settings())
        code, _, err = self.hooks_cmd(
            "hooks", "install", "--apply", stdin_reply="yes"
        )
        self.assertEqual(code, 0, err)
        merged = self.parsed()
        kept = [
            entry["command"]
            for group in merged["hooks"]["Stop"]
            for entry in group["hooks"]
        ]
        for entry in self.LOOKALIKES:
            self.assertIn(entry["command"], kept)
        owned = [
            command for command in kept
            if hooks.is_owned({"type": "command", "command": command})
        ]
        self.assertEqual(owned, [hooks.hook_command("Stop")])

    def test_uninstall_preserves_lookalike_user_commands(self):
        original = self.lookalike_settings()
        self.write_settings(original)
        self.hooks_cmd("hooks", "install", "--apply", stdin_reply="yes")
        code, _, err = self.hooks_cmd(
            "hooks", "uninstall", "--apply", stdin_reply="yes"
        )
        self.assertEqual(code, 0, err)
        # Semantic round-trip: the lookalike user commands are untouched.
        self.assertEqual(self.parsed(), original)

    def test_status_reads_lookalike_user_commands_as_absent(self):
        self.write_settings(self.lookalike_settings())
        code, out, _ = self.hooks_cmd("hooks", "status")
        self.assertEqual(code, 0)
        self.assertIn("state: absent", out)


class TestInstallerConcurrentEdit(InstallerCase):
    """F2: the plan's bytes must still be the file's bytes immediately
    before any mutation — a concurrent edit made while the confirmation
    prompt was pending survives untouched (no rewrite, no backup)."""

    CONCURRENT = json.dumps({"model": "haiku"}, indent=2) + "\n"

    def edit_then_confirm(self, prompt=""):
        self.settings.write_text(self.CONCURRENT, encoding="utf-8")
        return "yes"

    def test_concurrent_edit_during_install_confirmation_survives(self):
        self.write_settings(self.BASE_SETTINGS)
        with mock.patch("builtins.input", side_effect=self.edit_then_confirm):
            code, out, err = self.hooks_cmd("hooks", "install", "--apply")
        self.assertEqual(code, 1, out + err)
        self.assertIn("changed while confirmation was pending", err)
        self.assertIn("Nothing was changed", err)
        self.assertEqual(
            self.settings.read_text(encoding="utf-8"), self.CONCURRENT
        )
        self.assertEqual(self.backups(), [])  # zero mutation: no backup

    def test_concurrent_edit_during_uninstall_confirmation_survives(self):
        self.write_settings(self.BASE_SETTINGS)
        self.hooks_cmd("hooks", "install", "--apply", stdin_reply="yes")
        for stale in self.backups():
            stale.unlink()
        with mock.patch("builtins.input", side_effect=self.edit_then_confirm):
            code, out, err = self.hooks_cmd("hooks", "uninstall", "--apply")
        self.assertEqual(code, 1, out + err)
        self.assertIn("changed while confirmation was pending", err)
        self.assertEqual(
            self.settings.read_text(encoding="utf-8"), self.CONCURRENT
        )
        self.assertEqual(self.backups(), [])

    def test_file_created_while_confirmation_pending_refused(self):
        # The plan was computed against an ABSENT file; a file that appears
        # before 'yes' lands must not be clobbered.
        with mock.patch("builtins.input", side_effect=self.edit_then_confirm):
            code, out, err = self.hooks_cmd("hooks", "install", "--apply")
        self.assertEqual(code, 1, out + err)
        self.assertIn("changed while confirmation was pending", err)
        self.assertEqual(
            self.settings.read_text(encoding="utf-8"), self.CONCURRENT
        )
        self.assertEqual(self.backups(), [])


class TestInstallerRefusals(InstallerCase):
    MALFORMED = (
        b"{ not json",
        b'["a", "list"]',
        b'{"hooks": []}',
        b'{"hooks": {"Stop": {}}}',
        b'{"hooks": {"Stop": ["not-an-object"]}}',
        b'{"hooks": {"Stop": [{"hooks": "not-a-list"}]}}',
    )

    def test_malformed_settings_refused_with_zero_mutation(self):
        for raw in self.MALFORMED:
            with self.subTest(raw=raw[:30]):
                self.settings.write_bytes(raw)
                for argv in (
                    ("hooks", "install"),
                    ("hooks", "install", "--apply"),
                    ("hooks", "uninstall", "--apply"),
                    ("hooks", "status"),
                ):
                    code, _, err = self.hooks_cmd(*argv, stdin_reply="yes")
                    self.assertEqual(code, 1, f"{argv} on {raw!r}: {err}")
                    self.assertIn("Nothing was changed", err)
                self.assertEqual(self.settings.read_bytes(), raw)
                self.assertEqual(self.backups(), [])

    def test_explicit_hooks_null_refused_without_mutation(self):
        # F5: `"hooks": null` is an unsupported settings shape — refused
        # exactly like every other non-object value (documented choice:
        # refuse, never crash, never reinterpret), consistently across
        # install, status, and uninstall.
        raw = b'{"model": "opus", "hooks": null}\n'
        self.settings.write_bytes(raw)
        for argv in (
            ("hooks", "install"),
            ("hooks", "install", "--apply"),
            ("hooks", "uninstall"),
            ("hooks", "uninstall", "--apply"),
            ("hooks", "status"),
        ):
            with self.subTest(argv=argv):
                code, out, err = self.hooks_cmd(*argv, stdin_reply="yes")
                self.assertEqual(code, 1, f"{argv}: {out}{err}")
                self.assertIn("Unsupported settings structure", err)
                self.assertIn("Nothing was changed", err)
                self.assertNotIn("Traceback", err)
        self.assertEqual(self.settings.read_bytes(), raw)
        self.assertEqual(self.backups(), [])

    def test_symlinked_settings_refused(self):
        real = self.tmp / "real-settings.json"
        real.write_text("{}\n")
        self.settings.symlink_to(real)
        for argv in (("hooks", "install"), ("hooks", "install", "--apply")):
            code, _, err = self.hooks_cmd(*argv, stdin_reply="yes")
            self.assertEqual(code, 1)
            self.assertIn("symlink", err)
        self.assertEqual(real.read_text(), "{}\n")


# ---------------------------------------------------------------------------
# Protocol renderer parity


class TestAdapterProtocolParity(unittest.TestCase):
    def test_checked_in_adapters_match_renderer(self):
        for name in render.ADAPTER_NAMES:
            with self.subTest(adapter=name):
                disk = (
                    REPO_ROOT / "adapters" / name / "PROTOCOL.md"
                ).read_text(encoding="utf-8")
                self.assertEqual(disk, render.adapter_protocol_md(name))

    def test_envelope_documented_for_claude_code_only(self):
        claude = render.adapter_protocol_md("claude-code")
        self.assertIn("```aos-dropfile", claude)
        self.assertIn("Session write-back envelope", claude)
        self.assertIn("Ingest stays manual", claude)
        for name in ("codex", "gemini", "generic"):
            self.assertNotIn("aos-dropfile", render.adapter_protocol_md(name))

    def test_documented_fence_is_what_the_handler_accepts(self):
        # The protocol's own example block shape must round-trip through
        # the exact extraction the Stop handler uses.
        message = fenced(VALID_DROPFILE)
        self.assertEqual(hooks._extract_envelope(message), VALID_DROPFILE)


# ---------------------------------------------------------------------------
# Dogfood matrix (accelerated gate: the five scenarios, automated, against a
# REAL workspace — publication is proven all the way through manual ingest)


class TestDogfoodMatrix(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()
        self.root = self.tmp / "workspace"
        self.root.mkdir()
        repo = self.tmp / "repo"
        repo.mkdir()
        self.aos = lambda *argv: run_cli("--root", str(self.root), *argv)
        code, out, err = self.aos("init")
        self.assertEqual(code, 0, err)
        self.aos("project", "add", "demo", "--name", "Demo", "--repo", str(repo))
        self.aos("task", "add", "Hook dogfood", "-p", "demo")
        self.aos("run", "start", "T-0001", "--agent", "claude-code")
        self.exports = self.root / ".agentic-os" / "exports"
        self.transcript = self.tmp / "transcript.jsonl"
        self.transcript.write_text("{}\n")

    def stop_data(self, message):
        return {
            "session_id": SID,
            "cwd": str(self.root),
            "hook_event_name": "Stop",
            "last_assistant_message": message,
            "stop_hook_active": False,
            "background_tasks": [],
            "session_crons": [],
        }

    def end_data(self, reason="other"):
        return {
            "session_id": SID,
            "cwd": str(self.root),
            "hook_event_name": "SessionEnd",
            "transcript_path": str(self.transcript),
            "reason": reason,
        }

    def published(self) -> list[Path]:
        return sorted(self.exports.glob("dropfile-*.md"))

    def run_session(self, message) -> tuple[int, int]:
        stop_code, out, _ = run_hook(["stop"], self.stop_data(message))
        self.assertEqual(out, "")
        end_code, out, _ = run_hook(["session-end"], self.end_data())
        self.assertEqual(out, "")
        return stop_code, end_code

    def test_scenario_1_normal_success_publishes_and_ingests(self):
        body = dropfile(
            task="T-0001",
            summary="Dogfood success run.",
            evidence=["- kind: test | ref: unittest | claim: matrix green"],
            questions=["- hand the next session the ingest step"],
        )
        stop_code, end_code = self.run_session(fenced(body))
        self.assertEqual((stop_code, end_code), (0, 0))
        published = self.published()
        self.assertEqual(len(published), 1)
        # Manual ingest of the published dropfile is the whole point:
        code, out, err = self.aos("ingest", "dropfile", str(published[0]))
        self.assertEqual(code, 0, err)
        self.assertIn("Ingested dropfile for T-0001", out)
        code, out, _ = self.aos("task", "show", "T-0001", "--json")
        detail = json.loads(out)
        self.assertEqual(detail["runs"][0]["outcome"], "success")
        self.assertEqual(len(detail["evidence"]), 1)
        self.assertEqual(len(detail["handoffs"]), 1)

    def test_scenario_2_failure_outcome_publishes_honestly(self):
        body = dropfile(
            task="T-0001", outcome="fail",
            summary="Approach did not work; details in open questions.",
            questions=["- try plan B next session"],
        )
        stop_code, end_code = self.run_session(fenced(body))
        self.assertEqual((stop_code, end_code), (0, 0))
        published = self.published()
        self.assertEqual(len(published), 1)
        code, _, err = self.aos("ingest", "dropfile", str(published[0]))
        self.assertEqual(code, 0, err)
        code, out, _ = self.aos("task", "show", "T-0001", "--json")
        self.assertEqual(json.loads(out)["runs"][0]["outcome"], "fail")

    def test_scenario_3_no_envelope_no_evidence_is_a_clean_noop(self):
        stop_code, end_code = self.run_session(
            "Session ended without any write-back; nothing was claimed."
        )
        self.assertEqual((stop_code, end_code), (0, 0))
        self.assertEqual(self.published(), [])
        self.assertFalse((self.exports / "hook-staging").exists())

    def test_scenario_4_secret_shaped_output_refused_without_echo(self):
        body = dropfile(task="T-0001", summary=f"deploy key {FAKE_TOKEN}")
        code, out, err = run_hook(["stop"], self.stop_data(fenced(body)))
        self.assertEqual((code, out), (1, ""))
        self.assertIn("github-token", err)
        self.assertNotIn(FAKE_TOKEN, err)
        code, out, err = run_hook(["session-end"], self.end_data())
        self.assertEqual((code, out, err), (0, "", ""))  # nothing staged
        self.assertEqual(self.published(), [])
        # The fake token never landed anywhere in the workspace.
        for path in self.exports.rglob("*"):
            if path.is_file():
                self.assertNotIn(FAKE_TOKEN.encode(), path.read_bytes())

    def test_scenario_5_duplicate_retry_never_double_publishes(self):
        body = dropfile(task="T-0001", summary="Retry scenario.")
        stop_code, end_code = self.run_session(fenced(body))
        self.assertEqual((stop_code, end_code), (0, 0))
        # SessionEnd retries (hook re-fired) and a full re-staged replay:
        for _ in range(2):
            code, out, err = run_hook(["session-end"], self.end_data())
            self.assertEqual((code, out, err), (0, "", ""))
        run_hook(["stop"], self.stop_data(fenced(body)))
        code, _, err = run_hook(["session-end"], self.end_data())
        self.assertEqual(code, 0, err)
        published = self.published()
        self.assertEqual(len(published), 1)
        # And the ledger's own dedupe closes the loop: same bytes cannot
        # be ingested twice.
        code, _, err = self.aos("ingest", "dropfile", str(published[0]))
        self.assertEqual(code, 0, err)
        code, _, err = self.aos("ingest", "dropfile", str(published[0]))
        self.assertEqual(code, 1)
        self.assertIn("Duplicate dropfile", err)


if __name__ == "__main__":
    unittest.main()
