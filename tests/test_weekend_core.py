"""Weekend P1–P4 tests: --root targeting, discovery pinning, the Night-1
back-compat harness, and the decision/handoff/memory CLIs.

Every test runs inside its own TemporaryDirectory and never touches this
repo's .agentic-os or any global state.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from weekend_harness import (
    Night1BackCompatCase,
    WeekendOpsTestCase,
    WeekendTestCase,
)

from agentic_os import events, ops, utils

ISO_TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class TestDiscoveryPinned(WeekendTestCase):
    """Pin the CURRENT no-root discovery behavior (contract P1: verify what
    the code does and pin it with a test before touching the parser)."""

    def test_init_defaults_to_cwd(self):
        self.chdir(self.root)
        self.ok("init")
        self.assertTrue((self.aos_dir / utils.DB_FILENAME).is_file())

    def test_init_root_flag_targets_path_from_elsewhere(self):
        # Night-1 alias: `init --root PATH` initializes PATH, not cwd.
        elsewhere = self.new_tmp_dir()
        self.chdir(elsewhere)
        self.ok("init", "--root", str(self.root))
        self.assertTrue((self.aos_dir / utils.DB_FILENAME).is_file())
        self.assertFalse((elsewhere / utils.AOS_DIR_NAME).exists())

    def test_discovery_walks_up_from_cwd(self):
        self.chdir(self.root)
        self.ok("init")
        self.ok("project", "add", "demo", "--name", "Demo", "--repo", str(self.repo))
        nested = self.root / "a" / "b"
        nested.mkdir(parents=True)
        self.chdir(nested)
        self.ok("task", "add", "From nested dir", "-p", "demo")
        listing = json.loads(self.ok("task", "list", "--json"))
        self.assertEqual(listing["tasks"][0]["id"], "T-0001")
        # The task landed in the walked-up workspace, not a new one.
        self.assertFalse((nested / utils.AOS_DIR_NAME).exists())

    def test_discovery_not_initialized_exits_1(self):
        self.chdir(self.root)  # fresh dir, no workspace anywhere above tmp
        code, out, err = self.run_cli("task", "list")
        self.assertEqual(code, 1)
        self.assertIn("Not initialized. Run: python aos.py init", err)


class TestGlobalRoot(WeekendTestCase):
    """Contract feature 1: global --root before the subcommand targets
    PATH/.agentic-os for every command; explicit --root always wins."""

    def test_root_works_for_init_project_task_status(self):
        elsewhere = self.new_tmp_dir()
        self.chdir(elsewhere)  # cwd is unrelated and stays untouched
        self.ok("--root", str(self.root), "init")
        self.assertTrue((self.aos_dir / utils.DB_FILENAME).is_file())
        self.ok(
            "--root", str(self.root), "project", "add", "demo",
            "--name", "Demo", "--repo", str(self.repo),
        )
        out = self.ok("--root", str(self.root), "task", "add", "Via root", "-p", "demo")
        self.assertEqual(out.strip(), "T-0001")
        doc = json.loads(self.ok("--root", str(self.root), "status", "--json"))
        self.assertEqual(doc["projects"], 1)
        self.assertEqual(doc["open_tasks"], 1)
        self.assertFalse((elsewhere / utils.AOS_DIR_NAME).exists())

    def test_explicit_root_beats_discovery(self):
        # cwd sits inside workspace A; --root points at workspace B.
        workspace_b = self.new_tmp_dir("workspace-b")
        self.chdir(self.root)
        self.ok("init")
        self.ok("project", "add", "demo", "--name", "Demo", "--repo", str(self.repo))
        self.ok("--root", str(workspace_b), "init")
        self.ok(
            "--root", str(workspace_b), "project", "add", "bproj",
            "--name", "B", "--repo", str(self.repo),
        )
        self.ok("--root", str(workspace_b), "task", "add", "Lands in B", "-p", "bproj")
        in_b = json.loads(self.ok("--root", str(workspace_b), "task", "list", "--json"))
        self.assertEqual([t["title"] for t in in_b["tasks"]], ["Lands in B"])
        in_a = json.loads(self.ok("task", "list", "--json"))  # discovery: cwd = A
        self.assertEqual(in_a["tasks"], [])

    def test_root_uninitialized_exits_1(self):
        code, out, err = self.run_cli("--root", str(self.root), "task", "list")
        self.assertEqual(code, 1)
        self.assertIn("Not initialized at", err)
        self.assertIn("--root", err)  # the remedy names the flag

    def test_conflicting_init_roots_exit_1(self):
        other = self.new_tmp_dir("other-root")
        code, out, err = self.run_cli(
            "--root", str(self.root), "init", "--root", str(other)
        )
        self.assertEqual(code, 1)
        self.assertIn("Conflicting workspace roots", err)
        self.assertFalse((self.aos_dir / utils.DB_FILENAME).is_file())
        self.assertFalse((other / utils.AOS_DIR_NAME).exists())

    def test_same_root_given_twice_is_fine(self):
        self.ok("--root", str(self.root), "init", "--root", str(self.root))
        self.assertTrue((self.aos_dir / utils.DB_FILENAME).is_file())

    def test_init_root_alias_unchanged(self):
        # Night-1's `init --root PATH` stays a compatible alias.
        self.ok("init", "--root", str(self.root))
        self.assertTrue((self.aos_dir / utils.DB_FILENAME).is_file())
        second = self.ok("--root", str(self.root), "init")
        self.assertIn("nothing to do", second)


class TestNight1BackCompat(Night1BackCompatCase):
    def test_workspace_shape(self):
        listing = json.loads(self.aos("task", "list", "--json"))
        self.assertEqual(len(listing["tasks"]), 3)
        self.assertEqual(listing["tasks"][0]["status"], "done")
        self.assertTrue((self.aos_dir / "packs" / "T-0001-claude-code.md").is_file())
        vault = self.aos_dir / "obsidian-vault" / "AOS"
        self.assertTrue((vault / "Tasks" / "T-0001.md").is_file())

    def test_night1_commands_still_work_via_root(self):
        detail = json.loads(self.aos("task", "show", "T-0001", "--json"))
        self.assertEqual(detail["task"]["status"], "done")
        events = json.loads(self.aos("log", "--json"))
        self.assertGreater(len(events["events"]), 5)
        out = self.aos("sync")
        self.assertIn("(0 written", out)  # fixture already synced
        self.aos("doctor")
        self.assert_no_schema_drift()


class TestDecisionCli(Night1BackCompatCase):
    """Contract feature 2: decision add — IDs, events, task show, pack
    DECISIONS section, Obsidian sync — proven on the Night-1 fixture."""

    def add_decision(self, *extra: str) -> str:
        return self.aos(
            "decision", "add", "Use SQLite", "-p", "demo",
            "--decision", "SQLite is the source of truth",
            "--alternatives", "Markdown as database", *extra,
        )

    def test_task_scoped_decision_flows_everywhere(self):
        out = self.add_decision("--task", "T-0002")
        self.assertEqual(out.strip(), "D-0001")
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertEqual(detail["decisions"][0]["id"], "D-0001")
        self.assertEqual(detail["decisions"][0]["status"], "accepted")
        self.assertTrue(ISO_TS.match(detail["decisions"][0]["decided_at"]))
        pack_path = Path(self.aos("pack", "build", "T-0002").strip())
        section = pack_path.read_text("utf-8").split("## DECISIONS")[1].split(
            "## MEMORY"
        )[0]
        self.assertIn("D-0001", section)
        self.assertIn("[accepted]", section)
        self.assertIn("SQLite is the source of truth", section)
        self.aos("sync")
        vault = self.aos_dir / "obsidian-vault" / "AOS"
        note = (vault / "Decisions" / "D-0001.md").read_text("utf-8")
        self.assertIn("[[T-0002]]", note)
        self.assertIn("[[demo]]", note)
        self.assertIn("Markdown as database", note)
        task_note = (vault / "Tasks" / "T-0002.md").read_text("utf-8")
        self.assertIn("[[D-0001]]", task_note)
        self.aos("doctor")
        self.assert_no_schema_drift()

    def test_project_scoped_decision_shows_on_project_tasks(self):
        self.add_decision()
        for task_hid in ("T-0001", "T-0002"):
            detail = json.loads(self.aos("task", "show", task_hid, "--json"))
            self.assertEqual(
                [d["id"] for d in detail["decisions"]], ["D-0001"], task_hid
            )

    def test_decision_add_emits_event_with_payload(self):
        self.add_decision("--task", "T-0002")
        entries = json.loads(self.aos("log", "--json"))["events"]
        event = [
            e for e in entries
            if e["entity"] == "decision" and e["action"] == "add"
        ]
        self.assertEqual(len(event), 1)
        payload = event[0]["payload"]
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["decision"], "D-0001")
        self.assertEqual(payload["project"], "demo")
        self.assertEqual(payload["task"], "T-0002")

    def test_unknown_project_exits_1(self):
        code, out, err = self.aos_fails(
            "decision", "add", "X", "-p", "ghost", "--decision", "d"
        )
        self.assertIn("No project 'ghost'", err)

    def test_task_outside_project_exits_1(self):
        # T-0003 is the Night-1 inbox capture: it has no project.
        code, out, err = self.aos_fails(
            "decision", "add", "X", "-p", "demo",
            "--decision", "d", "--task", "T-0003",
        )
        self.assertIn("does not belong to project 'demo'", err)

    def test_malformed_task_id_exits_1(self):
        code, out, err = self.aos_fails(
            "decision", "add", "X", "-p", "demo",
            "--decision", "d", "--task", "X-1",
        )
        self.assertIn("Expected format: T-0001", err)

    def test_empty_decision_text_exits_1(self):
        code, out, err = self.aos_fails(
            "decision", "add", "X", "-p", "demo", "--decision", "   "
        )
        self.assertIn("must not be empty", err)


class TestHandoffCli(Night1BackCompatCase):
    """Contract feature 3: handoff create/accept — IDs, events, task show,
    pack PRIOR RUNS & HANDOFF STATE, sync; double-accept exits 1."""

    def create_handoff(self, state: str = "Done: pack built. Next: verify.") -> str:
        return self.aos(
            "handoff", "create", "T-0002",
            "--from", "claude-code", "--to", "codex", "--state", state,
        )

    def test_handoff_create_flows_everywhere(self):
        out = self.create_handoff()
        self.assertEqual(out.strip(), "H-0001")
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertEqual(detail["handoffs"][0]["id"], "H-0001")
        self.assertEqual(detail["handoffs"][0]["from_agent"], "claude-code")
        self.assertIsNone(detail["handoffs"][0]["accepted_at"])
        pack_path = Path(self.aos("pack", "build", "T-0002").strip())
        section = pack_path.read_text("utf-8").split(
            "## PRIOR RUNS & HANDOFF STATE"
        )[1].split("## WRITE-BACK PROTOCOL")[0]
        self.assertIn("H-0001", section)
        self.assertIn("claude-code → codex", section)
        self.assertIn("Done: pack built. Next: verify.", section)
        self.assertIn("not accepted", section)
        self.aos("sync")
        vault = self.aos_dir / "obsidian-vault" / "AOS"
        note = (vault / "Handoffs" / "H-0001.md").read_text("utf-8")
        self.assertIn("[[T-0002]]", note)
        self.assertIn("Done: pack built. Next: verify.", note)
        task_note = (vault / "Tasks" / "T-0002.md").read_text("utf-8")
        self.assertIn("[[H-0001]]", task_note)
        self.aos("doctor")
        self.assert_no_schema_drift()

    def test_accept_sets_accepted_at_and_double_accept_exits_1(self):
        self.create_handoff()
        out = self.aos("handoff", "accept", "H-0001")
        self.assertIn("H-0001 accepted at", out)
        detail = json.loads(self.aos("task", "show", "T-0002", "--json"))
        self.assertTrue(ISO_TS.match(detail["handoffs"][0]["accepted_at"]))
        code, out, err = self.aos_fails("handoff", "accept", "H-0001")
        self.assertIn("already accepted", err)
        entries = json.loads(self.aos("log", "--json"))["events"]
        actions = [
            e["action"] for e in entries if e["entity"] == "handoff"
        ]
        self.assertEqual(actions, ["create", "accept"])

    def test_create_on_missing_task_exits_1(self):
        code, out, err = self.aos_fails(
            "handoff", "create", "T-0042",
            "--from", "a", "--to", "b", "--state", "s",
        )
        self.assertIn("No task T-0042", err)

    def test_accept_malformed_or_missing_id_exits_1(self):
        code, out, err = self.aos_fails("handoff", "accept", "T-0001")
        self.assertIn("Expected format: H-0001", err)
        code, out, err = self.aos_fails("handoff", "accept", "H-0042")
        self.assertIn("No handoff H-0042", err)

    def test_empty_state_exits_1(self):
        code, out, err = self.aos_fails(
            "handoff", "create", "T-0002",
            "--from", "a", "--to", "b", "--state", "   ",
        )
        self.assertIn("must not be empty", err)

    def test_pack_secret_scan_fires_on_handoff_state(self):
        secret_value = "hunter22secret99"
        self.create_handoff(state=f'password = "{secret_value}"')
        code, out, err = self.run_cli(
            "--root", str(self.root), "pack", "build", "T-0002"
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("credential-assignment", err)
        self.assertIn("PRIOR RUNS & HANDOFF STATE", err)
        self.assertNotIn(secret_value, err)


class TestMemoryCli(Night1BackCompatCase):
    """Contract feature 4: memory add/list/retire, supersede chains, and the
    pack MEMORY live-only inclusion rule — proven on the Night-1 fixture."""

    def add_memory(self, *extra: str, key: str = "storage",
                   value: str = "SQLite is source of truth") -> str:
        return self.aos(
            "memory", "add", "--scope", "project", "--project", "demo",
            "--kind", "constraint", "--key", key, "--value", value,
            "--source", "human", "--confidence", "confirmed", *extra,
        )

    def pack_memory_section(self) -> str:
        pack_path = Path(self.aos("pack", "build", "T-0002").strip())
        text = pack_path.read_text("utf-8")
        return text.split("## MEMORY")[1].split(
            "## PRIOR RUNS & HANDOFF STATE"
        )[0]

    def test_memory_add_and_list_json(self):
        out = self.add_memory()
        self.assertEqual(out.strip(), "M-0001")
        self.aos(
            "memory", "add", "--scope", "global", "--kind", "preference",
            "--key", "style", "--value", "tabs not spaces",
            "--source", "human", "--confidence", "single",
        )
        doc = json.loads(self.aos("memory", "list", "--json"))
        self.assertEqual(set(doc.keys()), {"memories"})
        self.assertEqual(len(doc["memories"]), 2)
        first = doc["memories"][0]
        self.assertEqual(first["id"], "M-0001")
        self.assertEqual(first["scope"], "project")
        self.assertEqual(first["project"], "demo")
        self.assertEqual(first["kind"], "constraint")
        self.assertEqual(first["key"], "storage")
        self.assertTrue(first["live"])
        self.assertIsNone(first["valid_until"])
        self.assertTrue(ISO_TS.match(first["valid_from"]))
        second = doc["memories"][1]
        self.assertEqual(second["scope"], "global")
        self.assertIsNone(second["project"])
        # Filters.
        only_global = json.loads(
            self.aos("memory", "list", "--scope", "global", "--json")
        )
        self.assertEqual(
            [m["id"] for m in only_global["memories"]], ["M-0002"]
        )
        only_demo = json.loads(
            self.aos("memory", "list", "--project", "demo", "--json")
        )
        self.assertEqual([m["id"] for m in only_demo["memories"]], ["M-0001"])
        self.assert_no_schema_drift()

    def test_memory_add_validation(self):
        cases = [
            (
                ["--scope", "workspace", "--kind", "fact", "--key", "k",
                 "--value", "v", "--source", "s", "--confidence", "confirmed"],
                "global|project",
            ),
            (
                ["--scope", "global", "--kind", "vibe", "--key", "k",
                 "--value", "v", "--source", "s", "--confidence", "confirmed"],
                "preference|fact|constraint|summary",
            ),
            (
                ["--scope", "global", "--kind", "fact", "--key", "k",
                 "--value", "v", "--source", "s", "--confidence", "sure"],
                "confirmed|single|inferred|assumed",
            ),
            (
                ["--scope", "project", "--kind", "fact", "--key", "k",
                 "--value", "v", "--source", "s", "--confidence", "confirmed"],
                "--project is required",
            ),
            (
                ["--scope", "global", "--project", "demo", "--kind", "fact",
                 "--key", "k", "--value", "v", "--source", "s",
                 "--confidence", "confirmed"],
                "--project only applies",
            ),
            (
                ["--scope", "project", "--project", "ghost", "--kind", "fact",
                 "--key", "k", "--value", "v", "--source", "s",
                 "--confidence", "confirmed"],
                "No project 'ghost'",
            ),
            (
                ["--scope", "global", "--kind", "fact", "--key", "  ",
                 "--value", "v", "--source", "s", "--confidence", "confirmed"],
                "--key must not be empty",
            ),
            (
                ["--scope", "global", "--kind", "fact", "--key", "k",
                 "--value", "v", "--source", "s", "--confidence", "confirmed",
                 "--valid-until", "soon"],
                "Expected format: YYYY-MM-DD",
            ),
            (
                ["--scope", "global", "--kind", "fact", "--key", "k",
                 "--value", "v", "--source", "s", "--confidence", "confirmed",
                 "--valid-until", "2026-13-40"],
                "not a real calendar date",
            ),
            (
                ["--scope", "global", "--kind", "fact", "--key", "k",
                 "--value", "v", "--source", "s", "--confidence", "confirmed",
                 "--supersedes", "T-0001"],
                "Expected format: M-0001",
            ),
        ]
        for argv, expected in cases:
            with self.subTest(expected=expected):
                code, out, err = self.aos_fails("memory", "add", *argv)
                self.assertIn(expected, err)

    def test_retire_keeps_row_visible_and_double_retire_exits_1(self):
        self.add_memory()
        out = self.aos("memory", "retire", "M-0001")
        self.assertIn("M-0001 retired", out)
        doc = json.loads(self.aos("memory", "list", "--json"))
        self.assertEqual(len(doc["memories"]), 1)  # never silently disappears
        retired = doc["memories"][0]
        self.assertFalse(retired["live"])
        self.assertTrue(ISO_TS.match(retired["valid_until"]))
        code, out, err = self.aos_fails("memory", "retire", "M-0001")
        self.assertIn("already retired", err)
        entries = json.loads(self.aos("log", "--json"))["events"]
        actions = [e["action"] for e in entries if e["entity"] == "memory"]
        self.assertEqual(actions, ["add", "retire"])

    def test_supersede_links_old_row_in_same_transaction(self):
        self.add_memory(value="old value")
        out = self.add_memory("--supersedes", "M-0001", value="new value")
        self.assertEqual(out.strip(), "M-0002")
        doc = json.loads(self.aos("memory", "list", "--json"))
        old, new = doc["memories"]
        self.assertEqual(old["superseded_by"], "M-0002")
        self.assertFalse(old["live"])
        self.assertIsNone(new["superseded_by"])
        self.assertTrue(new["live"])
        # Superseding an already-superseded row is refused.
        code, out, err = self.aos_fails(
            "memory", "add", "--scope", "project", "--project", "demo",
            "--kind", "constraint", "--key", "storage", "--value", "x",
            "--source", "human", "--confidence", "confirmed",
            "--supersedes", "M-0001",
        )
        self.assertIn("already superseded by M-0002", err)

    def test_pack_includes_live_memory_only(self):
        self.add_memory(key="keep", value="live row stays")
        self.add_memory(key="retire-me", value="retired row goes")
        self.aos("memory", "retire", "M-0002")
        self.add_memory(key="superseded", value="old superseded value")
        self.add_memory(
            "--supersedes", "M-0003",
            key="superseded", value="winning successor value",
        )
        self.add_memory(
            "--valid-until", "2000-01-01",
            key="expired", value="expired row goes",
        )
        section = self.pack_memory_section()
        self.assertIn("keep: live row stays", section)
        self.assertIn("superseded: winning successor value", section)
        self.assertNotIn("retired row goes", section)
        self.assertNotIn("old superseded value", section)
        self.assertNotIn("expired row goes", section)
        # ... but none of them vanished from the ledger.
        doc = json.loads(self.aos("memory", "list", "--json"))
        self.assertEqual(len(doc["memories"]), 5)

    def test_pack_latest_per_key_wins_and_scope_ordering(self):
        self.add_memory(key="storage", value="first value")
        self.add_memory(key="storage", value="latest value")  # no supersede
        self.aos(
            "memory", "add", "--scope", "global", "--kind", "preference",
            "--key", "zz-global", "--value", "global rows lead",
            "--source", "human", "--confidence", "confirmed",
        )
        section = self.pack_memory_section()
        self.assertIn("storage: latest value", section)
        self.assertNotIn("first value", section)
        # Ordered by scope then key: the global row precedes project rows
        # even though its key sorts last.
        self.assertLess(
            section.index("zz-global"), section.index("storage")
        )

    def test_pack_secret_scan_fires_on_memory_value(self):
        secret_value = "hunter22secret99"
        self.add_memory(key="creds", value=f'password = "{secret_value}"')
        code, out, err = self.run_cli(
            "--root", str(self.root), "pack", "build", "T-0002"
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("credential-assignment", err)
        self.assertIn("MEMORY", err)
        self.assertNotIn(secret_value, err)

    def test_memory_syncs_to_obsidian(self):
        self.add_memory()
        self.aos(
            "memory", "add", "--scope", "global", "--kind", "preference",
            "--key", "style", "--value", "tabs", "--source", "human",
            "--confidence", "single",
        )
        self.add_memory("--supersedes", "M-0001", value="v2")
        self.aos("sync")
        vault = self.aos_dir / "obsidian-vault" / "AOS"
        note1 = (vault / "Memory" / "M-0001.md").read_text("utf-8")
        self.assertIn("type: memory", note1)
        self.assertIn("[[demo]]", note1)
        self.assertIn("superseded by: [[M-0003]]", note1)
        note2 = (vault / "Memory" / "M-0002.md").read_text("utf-8")
        self.assertIn("scope: global", note2)
        self.assertNotIn("[[demo]]", note2)
        self.aos("doctor")
        self.assert_no_schema_drift()

    def test_retire_missing_or_malformed_id_exits_1(self):
        code, out, err = self.aos_fails("memory", "retire", "M-0042")
        self.assertIn("No memory M-0042", err)
        code, out, err = self.aos_fails("memory", "retire", "T-0001")
        self.assertIn("Expected format: M-0001", err)


class TestRuntimeStateStaysIgnored(unittest.TestCase):
    """Required test: .agentic-os/ remains ignored — nothing under it is
    tracked or staged in THIS repo. Read-only git queries only (D-W9.2:
    the staged-entries assertion is scoped to .agentic-os paths so that
    legitimately staging source files never breaks the suite)."""

    def git(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.git_bin, "-C", str(self.repo_root), *argv],
            capture_output=True,
            text=True,
            timeout=10,
        )

    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]
        self.git_bin = shutil.which("git")
        if self.git_bin is None or not (self.repo_root / ".git").exists():
            self.skipTest("git or repo metadata unavailable")

    def test_agentic_os_is_ignored_and_never_tracked_or_staged(self):
        # The ignore rule holds (check-ignore exits 0 for ignored paths).
        probe = self.git("check-ignore", "-q", ".agentic-os/aos.db")
        self.assertEqual(probe.returncode, 0, probe.stderr)
        # Nothing under .agentic-os/ is in the index at all.
        tracked = self.git("ls-files", "--", ".agentic-os")
        self.assertEqual(tracked.returncode, 0, tracked.stderr)
        self.assertEqual(tracked.stdout.strip(), "")
        # And no status line — staged or otherwise — references it.
        status = self.git("status", "--porcelain")
        self.assertEqual(status.returncode, 0, status.stderr)
        for line in status.stdout.splitlines():
            self.assertNotIn(".agentic-os", line, line)


class TestWeekendAtomicity(WeekendOpsTestCase):
    """Every new mutating op writes its domain row(s) AND event row in one
    transaction — forced emit failure must roll back both."""

    def setUp(self):
        super().setUp()
        ops.add_project(self.conn, slug="demo", name="Demo", repo=str(self.repo))

    def assert_rolls_back(self, table: str, fn) -> None:
        rows_before = self.row_count(table)
        events_before = self.event_count()
        with mock.patch.object(
            events, "emit", side_effect=RuntimeError("forced failure")
        ):
            with self.assertRaises(RuntimeError):
                fn()
        self.assertEqual(self.row_count(table), rows_before)
        self.assertEqual(self.event_count(), events_before)

    def test_decision_add_atomicity(self):
        self.assert_rolls_back(
            "decisions",
            lambda: ops.add_decision(
                self.conn, title="X", project_slug="demo", decision="Y"
            ),
        )

    def test_handoff_create_atomicity(self):
        task = ops.add_task(self.conn, title="Work", project_slug="demo")
        self.assert_rolls_back(
            "handoffs",
            lambda: ops.create_handoff(
                self.conn, task_id=task.id,
                from_agent="a", to_agent="b", state="s",
            ),
        )

    def test_handoff_accept_atomicity(self):
        task = ops.add_task(self.conn, title="Work", project_slug="demo")
        handoff = ops.create_handoff(
            self.conn, task_id=task.id, from_agent="a", to_agent="b", state="s"
        )
        events_before = self.event_count()
        with mock.patch.object(
            events, "emit", side_effect=RuntimeError("forced failure")
        ):
            with self.assertRaises(RuntimeError):
                ops.accept_handoff(self.conn, handoff_id=handoff.id)
        self.assertEqual(self.event_count(), events_before)
        self.assertIsNone(
            ops.get_handoff(self.conn, handoff.id).accepted_at
        )  # the UPDATE rolled back with the failed event

    def _memory_kwargs(self, **overrides):
        kwargs = dict(
            scope="global", kind="fact", key="k", value="v",
            source="s", confidence="confirmed",
        )
        kwargs.update(overrides)
        return kwargs

    def test_memory_add_atomicity(self):
        self.assert_rolls_back(
            "memory",
            lambda: ops.add_memory(self.conn, **self._memory_kwargs()),
        )

    def test_memory_supersede_atomicity(self):
        old = ops.add_memory(self.conn, **self._memory_kwargs())
        rows_before = self.row_count("memory")
        events_before = self.event_count()
        with mock.patch.object(
            events, "emit", side_effect=RuntimeError("forced failure")
        ):
            with self.assertRaises(RuntimeError):
                ops.add_memory(
                    self.conn,
                    **self._memory_kwargs(value="v2"),
                    supersedes_id=old.id,
                )
        self.assertEqual(self.row_count("memory"), rows_before)
        self.assertEqual(self.event_count(), events_before)
        # The supersede pointer rolled back with the failed insert.
        self.assertIsNone(ops.get_memory(self.conn, old.id).superseded_by)

    def test_memory_retire_atomicity(self):
        item = ops.add_memory(self.conn, **self._memory_kwargs())
        events_before = self.event_count()
        with mock.patch.object(
            events, "emit", side_effect=RuntimeError("forced failure")
        ):
            with self.assertRaises(RuntimeError):
                ops.retire_memory(self.conn, memory_id=item.id)
        self.assertEqual(self.event_count(), events_before)
        self.assertIsNone(ops.get_memory(self.conn, item.id).valid_until)


if __name__ == "__main__":
    unittest.main()
