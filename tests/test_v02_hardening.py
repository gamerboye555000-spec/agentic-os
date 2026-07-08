"""v0.2 U-C1 input-hardening tests (agentic-os-v0.2-u-c1-hardening-contract.md).

Five fixes, each pinned failing-then-passing:
U-C1.1 id parser clamp (zero and oversized ids refused before any DB lookup) ·
U-C1.2 strict \\Z anchors on user-input validators ·
U-C1.3 run-start lifecycle gate (only ready tasks start runs) ·
U-C1.4 done --no-evidence requires a journaled --reason ·
U-C1.5 dropfile ingest caps (bytes, evidence rows, open questions).

Fixture reminder (Night-1 shape): project `demo`; T-0001 done (note
evidence); T-0002 ready in demo; T-0003 projectless inbox capture.
"""

from __future__ import annotations

import json
import sqlite3
import unittest

from weekend_harness import Night1BackCompatCase, WeekendOpsTestCase

from agentic_os import ids, ingest, ops, render, utils
from agentic_os.doctor import _NOTE_PATTERNS
from agentic_os.models import validate_provenance, validate_slug
from agentic_os.utils import AosError


class _CountingCase(Night1BackCompatCase):
    def count(self, table: str) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
        finally:
            conn.close()

    def row_counts(self) -> dict[str, int]:
        # tasks and decisions included: the contract says oversized ingest
        # input must "create no partial tasks, evidence, or decisions".
        return {
            table: self.count(table)
            for table in (
                "tasks", "decisions", "evidence", "runs", "handoffs", "events",
            )
        }


# ---------------------------------------------------------------------------
# U-C1.1 — id parser clamp

class TestIdClamp(unittest.TestCase):
    def test_documented_upper_bound_is_sqlite_integer_max(self):
        self.assertEqual(ids.MAX_ID, 2**63 - 1)

    def test_zero_equivalent_ids_refused(self):
        for text in ("T-0", "T-00", "T-0000", "T-000000000000"):
            with self.subTest(text=text):
                with self.assertRaises(AosError) as ctx:
                    ids.parse_id(text, "task")
                self.assertEqual(ctx.exception.exit_code, 1)

    def test_max_id_parses_and_max_plus_one_refused(self):
        self.assertEqual(ids.parse_id(f"T-{ids.MAX_ID}", "task"), ids.MAX_ID)
        with self.assertRaises(AosError) as ctx:
            ids.parse_id(f"T-{ids.MAX_ID + 1}", "task")
        self.assertEqual(ctx.exception.exit_code, 1)

    def test_huge_digit_string_is_a_domain_error_not_a_crash(self):
        # 5000 digits would trip CPython's int-conversion limit (ValueError,
        # exit 2) if converted before the digit-length check.
        for digits in ("9" * 30, "9" * 5000):
            with self.subTest(length=len(digits)):
                with self.assertRaises(AosError):
                    ids.parse_id(f"T-{digits}", "task")

    def test_clamp_applies_to_every_entity_prefix(self):
        for entity, prefix in ids.PREFIXES.items():
            with self.subTest(entity=entity):
                with self.assertRaises(AosError):
                    ids.parse_id(f"{prefix}-0", entity)
                with self.assertRaises(AosError):
                    ids.parse_id(f"{prefix}-{2**64}", entity)

    def test_valid_ids_still_parse(self):
        self.assertEqual(ids.parse_id("T-0001", "task"), 1)
        self.assertEqual(ids.parse_id("t-10000", "task"), 10000)
        self.assertEqual(ids.parse_id(" T-0001 ", "task"), 1)

    def test_zero_padding_never_counts_toward_the_magnitude_check(self):
        # 26 digits of text, value 7: zero-padding stays legal (as it always
        # was), only true magnitude is clamped.
        self.assertEqual(ids.parse_id("T-" + "0" * 25 + "7", "task"), 7)
        self.assertEqual(
            ids.parse_id(f"T-{'0' * 25}{ids.MAX_ID}", "task"), ids.MAX_ID
        )


class TestIdClampCli(_CountingCase):
    def test_zero_id_refused_before_db_lookup(self):
        code, out, err = self.aos_fails("task", "show", "T-0000")
        self.assertIn("T-0000", err)
        # The parser refuses it; the ledger is never asked.
        self.assertNotIn("No task", err)

    def test_oversized_id_is_exit_1_not_internal_error(self):
        code, out, err = self.aos_fails("task", "show", "T-" + "9" * 30)
        self.assertNotIn("Internal error", err)
        self.assertIn("maximum", err)

    def test_int_limit_sized_id_is_exit_1_not_internal_error(self):
        code, out, err = self.aos_fails("task", "show", "T-" + "9" * 5000)
        self.assertNotIn("Internal error", err)


# ---------------------------------------------------------------------------
# U-C1.2 — strict \Z anchors on user-input validators

class TestStrictAnchors(unittest.TestCase):
    def test_slug_with_trailing_newline_refused(self):
        self.assertEqual(validate_slug("demo"), "demo")
        for slug in ("demo\n", "demo\n\n", "de\nmo"):
            with self.subTest(slug=slug):
                with self.assertRaises(AosError):
                    validate_slug(slug)

    def test_provenance_with_trailing_newline_refused(self):
        self.assertEqual(validate_provenance("human"), "human")
        self.assertEqual(validate_provenance("agent:codex"), "agent:codex")
        for value in ("human\n", "agent:codex\n"):
            with self.subTest(value=value):
                with self.assertRaises(AosError):
                    validate_provenance(value)

    def test_date_with_trailing_newline_refused(self):
        self.assertEqual(
            utils.validate_date("2026-01-01", "--date"), "2026-01-01"
        )
        with self.assertRaises(AosError):
            utils.validate_date("2026-01-01\n", "--date")
        # The regex itself must refuse — before the \Z fix only the
        # fromisoformat backstop caught this.
        self.assertIsNone(utils._DATE_RE.match("2026-01-01\n"))

    def test_dropfile_field_regexes_refuse_trailing_newline(self):
        self.assertIsNotNone(ingest._TASK_RE.match("T-0002"))
        self.assertIsNone(ingest._TASK_RE.match("T-0002\n"))
        self.assertIsNotNone(ingest._AGENT_RE.match("codex"))
        self.assertIsNone(ingest._AGENT_RE.match("codex\n"))

    def test_id_regex_refuses_embedded_newline(self):
        # parse_id strips SURROUNDING whitespace by design; nothing with a
        # newline may survive the match itself (with $ it did).
        self.assertIsNone(ids._ID_RE.match("T-00\n01"))
        self.assertIsNone(ids._ID_RE.match("T-0001\n"))
        self.assertEqual(ids.parse_id("T-0001\n", "task"), 1)  # stripped

    def test_doctor_note_patterns_refuse_trailing_newline(self):
        samples = {
            "Tasks": "T-0001",
            "Runs": "R-0001",
            "Decisions": "D-0001",
            "Evidence": "E-0001",
            "Handoffs": "H-0001",
            "Memory": "M-0001",
            "Projects": "demo",
            "Reviews": "2026-07-08",
            "Agents": "codex",
        }
        self.assertEqual(set(samples), set(_NOTE_PATTERNS))
        for folder, stem in samples.items():
            with self.subTest(folder=folder):
                pattern = _NOTE_PATTERNS[folder]
                self.assertIsNotNone(pattern.match(stem))
                self.assertIsNone(pattern.match(stem + "\n"))

    def test_frontmatter_scalar_with_trailing_newline_is_quoted(self):
        # _PLAIN_SAFE decides plain-vs-JSON-quoted frontmatter scalars; a
        # newline written plain would corrupt every generated note.
        self.assertEqual(render._yaml_value("abc"), "abc")
        self.assertEqual(render._yaml_value("abc\n"), json.dumps("abc\n"))


class TestStrictAnchorsCli(Night1BackCompatCase):
    def test_project_slug_with_trailing_newline_refused(self):
        code, out, err = self.aos_fails(
            "project", "add", "proj\n", "--name", "X", "--repo", str(self.repo)
        )
        self.assertIn("Invalid project slug", err)

    def test_evidence_provenance_with_trailing_newline_refused(self):
        code, out, err = self.aos_fails(
            "evidence", "add", "T-0002", "--kind", "note", "--ref", "x",
            "--provenance", "agent:codex\n",
        )
        self.assertIn("Invalid provenance", err)


# ---------------------------------------------------------------------------
# U-C1.3 — run-start lifecycle gate

class TestRunStartGateCli(_CountingCase):
    def test_inbox_task_cannot_start_a_run(self):
        before = self.row_counts()
        code, out, err = self.aos_fails(
            "run", "start", "T-0003", "--agent", "claude-code"
        )
        self.assertIn("inbox", err)
        self.assertIn("only ready tasks", err)
        detail = json.loads(self.aos("task", "show", "T-0003", "--json"))
        self.assertEqual(detail["task"]["status"], "inbox")
        self.assertEqual(detail["runs"], [])
        self.assertEqual(self.row_counts(), before)  # no rows, no events

    def test_in_progress_task_cannot_start_a_second_run(self):
        self.aos("run", "start", "T-0002", "--agent", "claude-code")
        code, out, err = self.aos_fails(
            "run", "start", "T-0002", "--agent", "claude-code"
        )
        self.assertIn("in_progress", err)
        self.assertIn("only ready tasks", err)
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertEqual(len(detail["runs"]), 1)

    def test_done_task_keeps_its_specific_refusal(self):
        code, out, err = self.aos_fails(
            "run", "start", "T-0001", "--agent", "claude-code"
        )
        self.assertIn("done", err)
        self.assertIn("closed task", err)

    def test_ready_task_still_starts_and_transitions(self):
        out = self.aos("run", "start", "T-0002", "--agent", "claude-code")
        self.assertEqual(out.strip(), "R-0002")
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertEqual(detail["task"]["status"], "in_progress")
        self.assert_no_schema_drift()

    def test_refusal_names_the_ready_transition_command(self):
        code, out, err = self.aos_fails(
            "run", "start", "T-0003", "--agent", "claude-code"
        )
        self.assertIn("task status T-0003 ready", err)


class TestRunStartGateOps(WeekendOpsTestCase):
    def test_start_run_refuses_inbox_at_the_ops_layer(self):
        task = ops.capture_inbox(self.conn, "captured thought")
        events_before = self.event_count()
        with self.assertRaises(AosError) as ctx:
            ops.start_run(self.conn, task_id=task.id, agent="claude-code")
        self.assertIn("only ready tasks", str(ctx.exception))
        self.assertEqual(self.event_count(), events_before)
        self.assertEqual(self.row_count("runs"), 0)


# ---------------------------------------------------------------------------
# U-C1.4 — done --no-evidence requires a journaled reason

class TestDoneReasonCli(_CountingCase):
    def test_no_evidence_without_reason_refused(self):
        code, out, err = self.aos_fails("done", "T-0002", "--no-evidence")
        self.assertIn("--reason", err)
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertEqual(detail["task"]["status"], "ready")

    def test_blank_reason_refused(self):
        code, out, err = self.aos_fails(
            "done", "T-0002", "--no-evidence", "--reason", "   "
        )
        self.assertIn("--reason", err)
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertEqual(detail["task"]["status"], "ready")

    def test_no_evidence_with_reason_succeeds_and_journals_it(self):
        reason = "spike run; nothing shippable to attach"
        out = self.aos("done", "T-0002", "--no-evidence", "--reason", reason)
        self.assertIn("T-0002 done", out)
        entries = json.loads(self.aos("log", "--json"))["events"]
        overrides = [e for e in entries if e["action"] == "done_override"]
        self.assertEqual(len(overrides), 1)
        self.assertEqual(overrides[0]["payload"]["reason"], reason)

    def test_reason_without_no_evidence_refused(self):
        self.aos("evidence", "add", "T-0002", "--kind", "note", "--ref", "x")
        code, out, err = self.aos_fails(
            "done", "T-0002", "--reason", "not an override"
        )
        self.assertIn("--no-evidence", err)
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertEqual(detail["task"]["status"], "ready")

    def test_no_evidence_flag_refused_when_evidence_exists(self):
        # The override must not silently swallow the flag (and discard the
        # reason) when the task turns out to have evidence.
        self.aos("evidence", "add", "T-0002", "--kind", "note", "--ref", "x")
        code, out, err = self.aos_fails(
            "done", "T-0002", "--no-evidence", "--reason", "operator misread"
        )
        self.assertIn("does not apply", err)
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertEqual(detail["task"]["status"], "ready")
        out = self.aos("done", "T-0002")  # the named fix works
        self.assertIn("T-0002 done", out)

    def test_evidence_gated_done_unchanged(self):
        self.aos("evidence", "add", "T-0002", "--kind", "note", "--ref", "x")
        out = self.aos("done", "T-0002")
        self.assertIn("T-0002 done", out)
        entries = json.loads(self.aos("log", "--json"))["events"]
        self.assertEqual(
            [e for e in entries if e["action"] == "done_override"], []
        )


class TestDoneReasonOps(WeekendOpsTestCase):
    def test_mark_done_requires_reason_with_no_evidence(self):
        project, _ = ops.add_project(
            self.conn, slug="demo", name="Demo", repo=str(self.repo)
        )
        task = ops.add_task(
            self.conn, title="Bare override", project_slug="demo"
        )
        with self.assertRaises(AosError) as ctx:
            ops.mark_done(self.conn, task_id=task.id, no_evidence=True)
        self.assertIn("--reason", str(ctx.exception))
        done = ops.mark_done(
            self.conn, task_id=task.id, no_evidence=True,
            reason="ops-layer override probe",
        )
        self.assertEqual(done.status, "done")


# ---------------------------------------------------------------------------
# U-C1.5 — dropfile ingest caps

def _dropfile(evidence_rows: int = 1, questions: int = 1,
              task: str = "T-0002") -> str:
    lines = [
        "# AOS DROPFILE",
        f"task: {task}",
        "agent: codex",
        "outcome: partial",
        "summary: caps probe",
        "",
        "## evidence",
    ]
    lines += [
        f"- kind: note | ref: r{i} | claim: c{i}" for i in range(evidence_rows)
    ]
    lines += ["", "## open questions"]
    lines += [f"- question {i}?" for i in range(questions)]
    return "\n".join(lines) + "\n"


class TestIngestCaps(_CountingCase):
    def write_dropfile(self, content: str, name: str = "drop.md"):
        path = self.root / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_oversized_dropfile_refused_with_no_partial_writes(self):
        path = self.write_dropfile("x" * (ingest.MAX_DROPFILE_BYTES + 1))
        before = self.row_counts()
        code, out, err = self.aos_fails("ingest", "dropfile", str(path))
        self.assertIn("too large", err)
        self.assertIn(str(ingest.MAX_DROPFILE_BYTES), err)
        self.assertNotIn("Malformed", err)
        self.assertEqual(self.row_counts(), before)

    def test_dropfile_at_exact_byte_cap_ingests(self):
        base = _dropfile()
        padding = ingest.MAX_DROPFILE_BYTES - len(base.encode("utf-8"))
        path = self.write_dropfile(base + "\n" * padding)
        out = self.aos("ingest", "dropfile", str(path))
        self.assertIn("Ingested dropfile for T-0002", out)

    def test_too_many_evidence_rows_refused(self):
        path = self.write_dropfile(
            _dropfile(evidence_rows=ingest.MAX_EVIDENCE_ROWS + 1)
        )
        before = self.row_counts()
        code, out, err = self.aos_fails("ingest", "dropfile", str(path))
        self.assertIn("Malformed dropfile at line", err)
        self.assertIn("too many evidence rows", err)
        self.assertIn(str(ingest.MAX_EVIDENCE_ROWS), err)
        self.assertEqual(self.row_counts(), before)

    def test_evidence_rows_at_cap_ingest(self):
        evidence_before = self.count("evidence")
        path = self.write_dropfile(
            _dropfile(evidence_rows=ingest.MAX_EVIDENCE_ROWS)
        )
        out = self.aos("ingest", "dropfile", str(path))
        self.assertIn("Ingested dropfile for T-0002", out)
        self.assertEqual(
            self.count("evidence"),
            evidence_before + ingest.MAX_EVIDENCE_ROWS,
        )

    def test_too_many_questions_refused(self):
        path = self.write_dropfile(
            _dropfile(questions=ingest.MAX_QUESTIONS + 1)
        )
        before = self.row_counts()
        code, out, err = self.aos_fails("ingest", "dropfile", str(path))
        self.assertIn("Malformed dropfile at line", err)
        self.assertIn("too many open questions", err)
        self.assertEqual(self.row_counts(), before)

    def test_questions_at_cap_ingest(self):
        path = self.write_dropfile(_dropfile(questions=ingest.MAX_QUESTIONS))
        out = self.aos("ingest", "dropfile", str(path))
        self.assertIn("Ingested dropfile for T-0002", out)
        self.assertEqual(self.count("handoffs"), 1)

    def test_zero_task_id_is_a_parse_refusal(self):
        path = self.write_dropfile(_dropfile(task="T-0000"))
        code, out, err = self.aos_fails("ingest", "dropfile", str(path))
        self.assertIn("Malformed dropfile at line 2", err)
        self.assertIn("task id out of range", err)

    def test_int_limit_sized_task_id_is_a_parse_refusal_not_a_crash(self):
        # Same digit-length lesson as U-C1.1: 5000 digits must not reach
        # int() (ValueError, exit 2); the parser refuses on length first.
        path = self.write_dropfile(_dropfile(task="T-" + "9" * 5000))
        code, out, err = self.aos_fails("ingest", "dropfile", str(path))
        self.assertIn("Malformed dropfile at line 2", err)
        self.assertIn("task id out of range", err)


class _GrowingPath:
    """stat() under-reports; read_bytes() returns the real (oversized)
    bytes — the shape of a dropfile still being appended to by its writer
    between the stat and the read."""

    name = "growing-drop.md"

    def __init__(self, data: bytes):
        self._data = data

    def is_file(self) -> bool:
        return True

    def stat(self):
        import types

        return types.SimpleNamespace(st_size=10)

    def read_bytes(self) -> bytes:
        return self._data


class TestIngestCapByteRecheck(WeekendOpsTestCase):
    def test_growth_between_stat_and_read_is_refused(self):
        ops.add_project(
            self.conn, slug="demo", name="Demo", repo=str(self.repo)
        )
        ops.add_task(self.conn, title="target", project_slug="demo")
        oversized = b"x" * (ingest.MAX_DROPFILE_BYTES + 1)
        with self.assertRaises(AosError) as ctx:
            ingest.ingest_dropfile(self.conn, _GrowingPath(oversized))
        self.assertIn("too large", str(ctx.exception))
        self.assertEqual(self.row_count("evidence"), 0)
        self.assertEqual(self.row_count("handoffs"), 0)


class TestIngestCapsParser(unittest.TestCase):
    def test_zero_padded_task_id_still_parses_by_magnitude(self):
        doc = ingest.parse_dropfile(_dropfile(task="T-" + "0" * 25 + "2"))
        self.assertEqual(doc["task_id"], 2)

    def test_evidence_cap_error_names_the_first_offending_line(self):
        with self.assertRaises(AosError) as ctx:
            ingest.parse_dropfile(
                _dropfile(evidence_rows=ingest.MAX_EVIDENCE_ROWS + 1)
            )
        message = str(ctx.exception)
        self.assertIn("Malformed dropfile at line", message)
        self.assertIn("too many evidence rows", message)

    def test_question_cap_error_names_the_first_offending_line(self):
        with self.assertRaises(AosError) as ctx:
            ingest.parse_dropfile(_dropfile(questions=ingest.MAX_QUESTIONS + 1))
        message = str(ctx.exception)
        self.assertIn("Malformed dropfile at line", message)
        self.assertIn("too many open questions", message)


if __name__ == "__main__":
    unittest.main()
