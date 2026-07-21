"""Weekend P5–P8 tests: search, review build, export/snapshot, doctor
hardening — all proven against the Night-1-shaped workspace fixture.

Every test runs inside its own TemporaryDirectory and never touches this
repo's .agentic-os or any global state.
"""

from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path
from unittest import mock

from weekend_harness import Night1BackCompatCase

from agentic_os import db, ops, search


class SearchFixtureCase(Night1BackCompatCase):
    """Night-1 fixture + one row per searchable entity type sharing the
    token 'zebrafish' (whole-word queries keep FTS5 and LIKE membership
    aligned — FTS matches tokens, LIKE matches substrings)."""

    def setUp(self):
        super().setUp()
        self.aos("task", "add", "Catalogue the zebrafish tank", "-p", "demo")
        self.aos(
            "decision", "add", "Adopt zebrafish naming", "-p", "demo",
            "--decision", "All fixtures are named after zebrafish strains",
        )
        self.aos(
            "evidence", "add", "T-0002", "--kind", "note",
            "--ref", "zebrafish census", "--claim", "zebrafish counted",
        )
        self.aos(
            "handoff", "create", "T-0002", "--from", "claude-code",
            "--to", "codex", "--state", "Remaining: feed the zebrafish",
        )
        self.aos(
            "memory", "add", "--scope", "project", "--project", "demo",
            "--kind", "fact", "--key", "fish",
            "--value", "the zebrafish memory row",
            "--source", "human", "--confidence", "confirmed",
        )

    def search_json(self, *argv: str) -> dict:
        return json.loads(self.aos("search", *argv, "--json"))

    def open_db(self) -> sqlite3.Connection:
        return db.connect(self.db_path)


class TestSearch(SearchFixtureCase):
    def test_all_five_entity_types_found(self):
        doc = self.search_json("zebrafish")
        self.assertEqual(set(doc.keys()), {"query", "backend", "results"})
        self.assertEqual(doc["query"], "zebrafish")
        self.assertIn(doc["backend"], ("fts5", "like"))
        types = {r["type"] for r in doc["results"]}
        self.assertEqual(
            types, {"task", "decision", "evidence", "handoff", "memory"}
        )
        by_type = {r["type"]: r for r in doc["results"]}
        self.assertEqual(by_type["task"]["id"], "T-0004")
        self.assertEqual(by_type["decision"]["id"], "D-0001")
        self.assertEqual(by_type["evidence"]["id"], "E-0002")
        self.assertEqual(by_type["handoff"]["id"], "H-0001")
        self.assertEqual(by_type["memory"]["id"], "M-0001")
        for result in doc["results"]:
            self.assertIn("zebrafish", result["snippet"].lower())
        self.assert_no_schema_drift()

    def test_text_output_reports_backend_and_one_line_per_hit(self):
        out = self.aos("search", "zebrafish")
        lines = out.strip().splitlines()
        self.assertRegex(lines[0], r"^backend: (fts5|like)$")
        self.assertEqual(len(lines), 6)  # backend line + five hits
        for line in lines[1:]:
            self.assertRegex(
                line, r"^(task|decision|evidence|handoff|memory)\s+[TDEHM]-\d{4,}\s+"
            )

    def test_like_fallback_forced(self):
        with mock.patch.object(search, "fts5_available", lambda: False):
            doc = self.search_json("zebrafish")
        self.assertEqual(doc["backend"], "like")
        types = {r["type"] for r in doc["results"]}
        self.assertEqual(
            types, {"task", "decision", "evidence", "handoff", "memory"}
        )
        for result in doc["results"]:
            self.assertIn("zebrafish", result["snippet"].lower())

    @unittest.skipUnless(
        search.fts5_available(), "this SQLite build has no FTS5"
    )
    def test_membership_parity_between_backends(self):
        for query in ("zebrafish", "zebrafish memory", "SQLite", "nothing-here"):
            with self.subTest(query=query):
                native = self.search_json(query)
                self.assertEqual(native["backend"], "fts5")
                with mock.patch.object(search, "fts5_available", lambda: False):
                    fallback = self.search_json(query)
                self.assertEqual(fallback["backend"], "like")
                self.assertEqual(
                    {(r["type"], r["id"]) for r in native["results"]},
                    {(r["type"], r["id"]) for r in fallback["results"]},
                )

    @unittest.skipUnless(
        search.fts5_available(), "this SQLite build has no FTS5"
    )
    def test_watermark_written_and_rebuild_on_new_events(self):
        self.aos("search", "zebrafish")
        conn = self.open_db()
        try:
            watermark = db.get_meta(conn, search.WATERMARK_KEY)
            max_event = conn.execute(
                "SELECT MAX(id) AS n FROM events"
            ).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(watermark, str(max_event))
        # New data arrives (new events) → the index is stale → next search
        # rebuilds and finds the new row.
        self.aos("task", "add", "A second zebrafish task", "-p", "demo")
        doc = self.search_json("zebrafish")
        task_ids = [r["id"] for r in doc["results"] if r["type"] == "task"]
        self.assertIn("T-0005", task_ids)
        conn = self.open_db()
        try:
            watermark = db.get_meta(conn, search.WATERMARK_KEY)
            max_event = conn.execute(
                "SELECT MAX(id) AS n FROM events"
            ).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(watermark, str(max_event))

    @unittest.skipUnless(
        search.fts5_available(), "this SQLite build has no FTS5"
    )
    def test_index_is_safely_droppable(self):
        before = self.search_json("zebrafish")
        conn = self.open_db()
        try:
            with conn:
                conn.execute(f"DROP TABLE {search.FTS_TABLE}")
        finally:
            conn.close()
        after = self.search_json("zebrafish")
        self.assertEqual(before["results"], after["results"])

    def test_search_emits_no_events(self):
        conn = self.open_db()
        try:
            before = conn.execute(
                "SELECT COUNT(*) AS n FROM events"
            ).fetchone()["n"]
        finally:
            conn.close()
        self.aos("search", "zebrafish")
        self.aos("search", "zebrafish")
        conn = self.open_db()
        try:
            after = conn.execute(
                "SELECT COUNT(*) AS n FROM events"
            ).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(before, after)

    def test_empty_query_exits_1(self):
        code, out, err = self.aos_fails("search", "   ")
        self.assertIn("must not be empty", err)

    def test_no_results_exit_0(self):
        code, out, err = self.run_cli(
            "--root", str(self.root), "search", "xyzzy-not-there"
        )
        self.assertEqual(code, 0)
        self.assertIn("(no results)", out)

    def test_like_snippet_survives_length_changing_lowercase(self):
        # Regression (review finding): 'İ' (U+0130) lowers to two chars, so
        # a position found in body.lower() desyncs against the original —
        # the snippet must still show the actual hit.
        self.aos(
            "memory", "add", "--scope", "global", "--kind", "fact",
            "--key", "exotic", "--value", "İ" * 50 + " zebrafish tail",
            "--source", "human", "--confidence", "single",
        )
        with mock.patch.object(search, "fts5_available", lambda: False):
            doc = self.search_json("zebrafish")
        exotic = [r for r in doc["results"] if r["id"] == "M-0002"]
        self.assertEqual(len(exotic), 1)
        self.assertIn("zebrafish", exotic[0]["snippet"])


class TestReviewBuild(Night1BackCompatCase):
    """Contract feature 6: review build — content sections, byte-for-byte
    Notes preservation, idempotency, eventless."""

    def build(self, *extra: str) -> Path:
        return Path(self.aos("review", "build", *extra).strip())

    def open_db(self) -> sqlite3.Connection:
        return db.connect(self.db_path)

    def event_count(self) -> int:
        conn = self.open_db()
        try:
            return conn.execute(
                "SELECT COUNT(*) AS n FROM events"
            ).fetchone()["n"]
        finally:
            conn.close()

    def test_review_sections_and_content(self):
        # An override-closed done task (listed) next to the fixture's
        # evidenced done task (not listed)...
        self.aos("task", "add", "Overridden task", "-p", "demo")
        self.aos(
            "done", "T-0004", "--no-evidence",
            "--reason", "review fixture override",
        )
        # ...a done task with no evidence and no override, forced via SQL as
        # if written outside the CLI's done gate...
        conn = self.open_db()
        try:
            with conn:
                conn.execute(
                    "UPDATE tasks SET status = 'done', closed_at = created_at "
                    "WHERE title = 'Second task'"
                )
        finally:
            conn.close()
        # ...one stale memory row (valid_until passed) and one live one.
        self.aos(
            "memory", "add", "--scope", "project", "--project", "demo",
            "--kind", "fact", "--key", "old-fact", "--value", "expired",
            "--source", "human", "--confidence", "single",
            "--valid-until", "2001-01-01",
        )
        self.aos(
            "memory", "add", "--scope", "global", "--kind", "preference",
            "--key", "fresh-fact", "--value", "still valid",
            "--source", "human", "--confidence", "confirmed",
        )
        path = self.build()
        text = path.read_text("utf-8")
        self.assertEqual(path.parent.name, "Reviews")
        for heading in (
            "## Done tasks needing attention",
            "## Open tasks",
            "## Recent evidence",
            "## Stale memory",
            "## Recent runs",
            "## Notes",
        ):
            self.assertIn(heading, text)
        head = text.split("## Notes")[0]
        attention = head.split("## Done tasks needing attention")[1].split(
            "## Open tasks"
        )[0]
        self.assertIn("[[T-0004]]", attention)  # override
        self.assertIn("override", attention)
        self.assertIn("[[T-0002]]", attention)  # forced, no evidence
        self.assertIn("no evidence", attention)
        self.assertNotIn("[[T-0001]]", attention)  # evidenced done task
        open_section = head.split("## Open tasks")[1].split(
            "## Recent evidence"
        )[0]
        self.assertIn("[[T-0003]]", open_section)  # inbox capture
        evidence_section = head.split("## Recent evidence")[1].split(
            "## Stale memory"
        )[0]
        self.assertIn("[[E-0001]]", evidence_section)  # created today
        stale_section = head.split("## Stale memory")[1].split(
            "## Recent runs"
        )[0]
        self.assertIn("[[M-0001]]", stale_section)
        self.assertIn("valid_until", stale_section)
        self.assertNotIn("[[M-0002]]", stale_section)
        runs_section = head.split("## Recent runs")[1]
        self.assertIn("[[R-0001]]", runs_section)
        # Wikilinks resolve once the mirror is synced: the review-note
        # checks pass; only the SQL-forced unevidenced done (planted above
        # on purpose) fails doctor — exactly the check that should.
        self.aos("sync")
        code, doctor_out, err = self.run_cli("--root", str(self.root), "doctor")
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] done tasks have evidence", doctor_out)
        self.assertIn("[PASS] wikilinks resolve to generated notes", doctor_out)
        self.assertIn(
            "[PASS] mirror contains only generated AOS/ notes", doctor_out
        )
        self.assert_no_schema_drift()

    def test_notes_and_everything_below_preserved_byte_for_byte(self):
        path = self.build()
        appended = (
            b"\nmanual note for preservation check\r\n"
            b"CR bytes and no trailing newline survive"
        )
        with open(path, "ab") as fh:
            fh.write(appended)
        tail_before = path.read_bytes().split(b"## Notes", 1)[1]
        self.aos("task", "add", "Head must regenerate", "-p", "demo")
        rebuilt = self.build()
        self.assertEqual(rebuilt, path)
        data = path.read_bytes()
        head, tail_after = data.split(b"## Notes", 1)
        self.assertEqual(tail_after, tail_before)  # byte-for-byte incl. \r
        self.assertIn(b"Head must regenerate", head)  # head DID regenerate

    def test_idempotent_without_data_change(self):
        path = self.build()
        first = path.read_bytes()
        second_path = self.build()
        self.assertEqual(second_path, path)
        self.assertEqual(path.read_bytes(), first)

    def test_notes_heading_restored_when_missing(self):
        path = self.build()
        path.write_bytes(b"# hand-rolled file with no notes heading\n")
        self.build()
        self.assertIn(b"## Notes\n", path.read_bytes())

    def test_date_parameter_and_validation(self):
        path = self.build("--date", "2001-01-01")
        self.assertEqual(path.name, "2001-01-01.md")
        text = path.read_text("utf-8")
        evidence_section = text.split("## Recent evidence")[1].split(
            "## Stale memory"
        )[0]
        self.assertIn("*(none)*", evidence_section)  # today's rows not recent then
        runs_section = text.split("## Recent runs")[1].split("## Notes")[0]
        self.assertIn("*(none)*", runs_section)
        for bad in ("07/07/2026", "2026-7-7", "2026-13-40", "tomorrow"):
            with self.subTest(bad=bad):
                code, out, err = self.aos_fails("review", "build", "--date", bad)
                self.assertTrue(
                    "Expected format: YYYY-MM-DD" in err
                    or "not a real calendar date" in err
                )

    def test_review_build_is_eventless(self):
        before = self.event_count()
        self.build()
        self.build()
        self.assertEqual(self.event_count(), before)

    def test_sync_idempotent_with_review_note_present(self):
        self.build()
        self.aos("sync")
        vault_aos = self.aos_dir / "obsidian-vault" / "AOS"
        from agentic_os import utils as agentic_utils

        hash1 = agentic_utils.tree_hash(vault_aos)
        out = self.aos("sync")
        self.assertIn("(0 written", out)
        self.assertEqual(agentic_utils.tree_hash(vault_aos), hash1)

    def test_multiline_agent_name_cannot_corrupt_the_notes_anchor(self):
        # Regression (review finding): an agent name carrying CR/LF and a
        # fake "## Notes" line must not reach the generated head raw — it
        # would hijack the preserved-region anchor and break idempotency.
        self.aos(
            "run", "start", "T-0002",
            "--agent", "evil\r\n## Notes\ninjected",
        )
        path = self.build()
        first = path.read_bytes()
        second = self.build().read_bytes()
        self.assertEqual(first, second)  # idempotent despite the hostile name
        self.assertNotIn(b"\r", first)  # LF-only generated content
        notes_lines = [
            line for line in first.split(b"\n") if line == b"## Notes"
        ]
        self.assertEqual(len(notes_lines), 1)  # exactly one anchor LINE
        # The hostile name is collapsed onto the run bullet — mid-line, so
        # it can never anchor the preserved region.
        self.assertIn("evil ## Notes injected · open".encode("utf-8"), first)


class TestSyncAllNoteTypes(Night1BackCompatCase):
    """Required test: sync remains idempotent (two syncs, identical tree
    hash) with ALL new note types present — decisions, handoffs, memory
    (incl. a supersede chain), and a review note."""

    def test_two_syncs_identical_tree_hash_with_all_note_types(self):
        self.aos(
            "decision", "add", "Use SQLite", "-p", "demo",
            "--decision", "SQLite is the source of truth",
            "--alternatives", "Markdown as database", "--task", "T-0002",
        )
        self.aos(
            "handoff", "create", "T-0002", "--from", "claude-code",
            "--to", "codex", "--state", "Done: pack. Remaining: verify.",
        )
        self.aos("handoff", "accept", "H-0001")
        self.aos(
            "memory", "add", "--scope", "project", "--project", "demo",
            "--kind", "constraint", "--key", "storage",
            "--value", "SQLite only", "--source", "human",
            "--confidence", "confirmed",
        )
        self.aos(
            "memory", "add", "--scope", "global", "--kind", "preference",
            "--key", "storage", "--value", "SQLite, WAL mode",
            "--source", "human", "--confidence", "confirmed",
            "--supersedes", "M-0001",
        )
        self.aos("memory", "retire", "M-0002")
        self.aos("review", "build")
        vault_aos = self.aos_dir / "obsidian-vault" / "AOS"
        self.aos("sync")
        # Every new note type is actually present in the mirror.
        for rel in (
            "Decisions/D-0001.md",
            "Handoffs/H-0001.md",
            "Memory/M-0001.md",
            "Memory/M-0002.md",
        ):
            self.assertTrue((vault_aos / rel).is_file(), rel)
        self.assertTrue(list((vault_aos / "Reviews").glob("*.md")))
        from agentic_os import utils as agentic_utils

        hash1 = agentic_utils.tree_hash(vault_aos)
        out = self.aos("sync")
        self.assertIn("(0 written", out)
        self.assertEqual(agentic_utils.tree_hash(vault_aos), hash1)
        self.aos("doctor")
        self.assert_no_schema_drift()


class TestExportSnapshot(Night1BackCompatCase):
    """Contract feature 7: JSONL event export (derived, eventless) and the
    backup-API snapshot with its event-only audit record."""

    def open_db(self) -> sqlite3.Connection:
        return db.connect(self.db_path)

    def counts(self, conn: sqlite3.Connection) -> dict[str, int]:
        return {
            table: conn.execute(
                f"SELECT COUNT(*) AS n FROM {table}"
            ).fetchone()["n"]
            for table in ("projects", "tasks", "runs", "evidence", "events")
        }

    def test_export_jsonl_shape(self):
        out = self.aos("export", "events", "--jsonl")
        path = Path(out.strip())
        self.assertTrue(path.is_file())
        self.assertEqual(path.parent, self.aos_dir / "exports")
        self.assertRegex(path.name, r"^events-\d{8}T\d{6}Z\.jsonl$")
        lines = path.read_text("utf-8").splitlines()
        conn = self.open_db()
        try:
            event_count = conn.execute(
                "SELECT COUNT(*) AS n FROM events"
            ).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(len(lines), event_count)
        seen_ids = []
        for line in lines:
            obj = json.loads(line)  # every line parses
            self.assertEqual(
                set(obj.keys()),
                {
                    "id", "ts", "actor", "entity", "entity_id",
                    "action", "payload_json",
                },
            )
            self.assertEqual(json.loads(obj["payload_json"])["schema_version"], 1)
            seen_ids.append(obj["id"])
        self.assertEqual(seen_ids, sorted(seen_ids))  # ascending ids
        self.assert_no_schema_drift()

    def test_export_is_eventless_and_output_flag(self):
        conn = self.open_db()
        try:
            before = conn.execute(
                "SELECT COUNT(*) AS n FROM events"
            ).fetchone()["n"]
        finally:
            conn.close()
        target = self.root / "custom" / "my-export.jsonl"
        out = self.aos("export", "events", "--jsonl", "--output", str(target))
        self.assertEqual(Path(out.strip()), target)
        self.assertTrue(target.is_file())
        conn = self.open_db()
        try:
            after = conn.execute(
                "SELECT COUNT(*) AS n FROM events"
            ).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(before, after)

    def test_export_requires_jsonl_flag(self):
        code, out, err = self.aos_fails("export", "events")
        self.assertIn("--jsonl", err)

    def fresh_counts(self) -> dict[str, int]:
        conn = self.open_db()
        try:
            return self.counts(conn)
        finally:
            conn.close()

    def test_snapshot_captures_uncheckpointed_wal_writes(self):
        # Pin an open read transaction so the CLI connections' closes cannot
        # checkpoint the WAL — the new task then lives ONLY in aos.db-wal
        # when the snapshot is taken. (A merely-open connection holds no
        # lock, so it would not prevent the checkpoint-on-close.)
        holder = self.open_db()
        try:
            holder.execute("BEGIN")
            holder.execute("SELECT COUNT(*) FROM tasks").fetchone()
            self.aos("task", "add", "WAL resident task", "-p", "demo")
            wal = Path(str(self.db_path) + "-wal")
            self.assertTrue(wal.is_file() and wal.stat().st_size > 0)
            source_counts = self.fresh_counts()  # latest state, incl. WAL
            out = self.aos("snapshot")
            snap_path = Path(out.strip())
            self.assertTrue(snap_path.is_file())
            self.assertEqual(snap_path.parent, self.aos_dir / "exports")
            self.assertRegex(snap_path.name, r"^aos-\d{8}T\d{6}Z\.db$")
            snap = sqlite3.connect(snap_path)
            snap.row_factory = sqlite3.Row
            try:
                self.assertEqual(
                    snap.execute("PRAGMA integrity_check").fetchone()[0], "ok"
                )
                # Row counts match the source AT snapshot time — including
                # the WAL-resident task a raw file copy would have missed.
                self.assertEqual(self.counts(snap), source_counts)
                titles = [
                    r["title"]
                    for r in snap.execute("SELECT title FROM tasks").fetchall()
                ]
                self.assertIn("WAL resident task", titles)
                # The snapshot never contains its own event...
                snap_actions = [
                    r["action"]
                    for r in snap.execute("SELECT action FROM events").fetchall()
                ]
                self.assertNotIn("snapshot", snap_actions)
            finally:
                snap.close()
            # ...but the live ledger gained exactly the audit event.
            holder.rollback()  # release the pinned read snapshot
            live = self.fresh_counts()
            self.assertEqual(live["events"], source_counts["events"] + 1)
            for table in ("projects", "tasks", "runs", "evidence"):
                self.assertEqual(live[table], source_counts[table], table)
            row = holder.execute(
                "SELECT actor, entity, payload_json FROM events "
                "WHERE action = 'snapshot'"
            ).fetchone()
            self.assertEqual(row["entity"], "system")
            payload = json.loads(row["payload_json"])
            self.assertEqual(payload["schema_version"], 1)
            self.assertEqual(payload["filename"], snap_path.name)
            self.assertIn("does not contain its own event", payload["note"])
        finally:
            holder.close()
        self.assert_no_schema_drift()

    def test_snapshot_collision_appends_suffix(self):
        from agentic_os import export as export_mod

        with mock.patch.object(
            export_mod, "_utc_stamp", return_value="20990101T000000Z"
        ):
            first = Path(self.aos("snapshot").strip())
            second = Path(self.aos("snapshot").strip())
            third = Path(self.aos("snapshot").strip())
        self.assertEqual(first.name, "aos-20990101T000000Z.db")
        self.assertEqual(second.name, "aos-20990101T000000Z-2.db")
        self.assertEqual(third.name, "aos-20990101T000000Z-3.db")
        for path in (first, second, third):
            self.assertTrue(path.is_file())


class TestDoctorHardening(Night1BackCompatCase):
    """Contract feature 8: every new doctor check passes on a clean Weekend
    workspace and fails on a deliberately corrupted one."""

    NEW_CHECKS = (
        "schema_version supported",
        "task statuses inside the vocabulary",
        "handoffs reference existing tasks",
        "task-linked decisions reference existing tasks",
        "memory supersede pointers resolve",
        "packs reference existing tasks and files",
    )

    def corrupt(self, sql: str, params=()) -> None:
        """Plant a corruption the CLI could never produce (raw connection:
        no foreign-key PRAGMA, no events, no guards)."""
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

    def test_clean_weekend_workspace_passes_all_checks(self):
        # Exercise every Weekend surface, then expect a fully green doctor.
        # (Pin moved 12 → 17 → 18 → 20 under the D-W8.1 pattern: 4
        # complete-today checks + 1 warn-only line, the U-C3 warn-only
        # secret sweep, then the two U-H2 warn-only checks joined the
        # mandated set. The fixture's T-0001 is a code task closed with
        # note evidence, so the warn-only commit-evidence line fires
        # without failing the run; the secret sweep and both U-H2 checks
        # stay [PASS] — R-0001's evidence is attributable, no ref is
        # blank.)
        self.aos(
            "decision", "add", "Use SQLite", "-p", "demo",
            "--decision", "SQLite is the source of truth", "--task", "T-0002",
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
        self.aos("review", "build")
        self.aos("search", "SQLite")
        self.aos("snapshot")
        self.aos("export", "events", "--jsonl")
        self.aos("sync")
        code, out = self.doctor()
        self.assertEqual(code, 0, out)
        lines = [l for l in out.strip().splitlines() if l]
        # 20 → 21 → 25 → 30 → 31 → 34 → 37 → 41: the mandated U-E2 runtime
        # power state check joined the set, then U-M2's four memory-claim
        # checks, then U-M3's five memory-graph checks, then U-M5's retrieval
        # benchmark registry check, then U-A1's three agent-registry
        # checks, then U-A2's three built-in catalog checks, then U-A3's four
        # routing/handoff checks (D-W8.1 pattern — the pin moves UP with a
        # mandated new check). The power line reports [PASS] "standard
        # (default)" here: this workspace has no power.json, and doctor must
        # never create one — which U-M5's read-only commands also honor. This
        # workspace never installs the catalog, so all three U-A2 lines stay
        # [PASS] and the warn count is unaffected.
        self.assertEqual(len(lines), 41)
        warn_lines = [l for l in lines if l.startswith("[WARN]")]
        self.assertEqual(len(warn_lines), 1)
        self.assertIn("T-0001", warn_lines[0])
        for line in lines:
            self.assertTrue(
                line.startswith("[PASS]") or line.startswith("[WARN]"), line
            )
        for name in self.NEW_CHECKS:
            self.assertIn(f"[PASS] {name}", out)
        self.assert_no_schema_drift()

    def test_fails_on_status_outside_vocabulary(self):
        self.corrupt("UPDATE tasks SET status = 'blocked' WHERE id = 2")
        self.assert_single_failure(
            "task statuses inside the vocabulary", "T-0002", "blocked"
        )

    def test_fails_on_handoff_to_missing_task(self):
        self.corrupt(
            "INSERT INTO handoffs (task_id, from_agent, to_agent, state_md, "
            "created_at) VALUES (999, 'a', 'b', 's', '2026-01-01T00:00:00Z')"
        )
        self.assert_single_failure("handoffs reference existing tasks", "H-0001")

    def test_fails_on_decision_to_missing_task(self):
        self.corrupt(
            "INSERT INTO decisions (project_id, task_id, title, decision_md, "
            "decided_at) VALUES (1, 999, 'X', 'Y', '2026-01-01T00:00:00Z')"
        )
        self.assert_single_failure(
            "task-linked decisions reference existing tasks", "D-0001"
        )

    def test_fails_on_dangling_memory_supersede_pointer(self):
        # The row is well-formed in every other respect — retired, as a
        # superseded claim must be, and carrying its correct claim hash — so
        # the ONLY thing wrong with it is the pointer. Otherwise the U-M2
        # claim check would fail too and "single failure" would be true for
        # the wrong reason.
        self.corrupt(
            "INSERT INTO memory (scope, kind, key, value_md, source, "
            "confidence, valid_from, superseded_by, updated_at, status, "
            "pinned, content_sha256) "
            "VALUES ('global', 'fact', 'k', 'v', 's', 'confirmed', "
            "'2026-01-01T00:00:00Z', 999, '2026-01-01T00:00:00Z', "
            "'retired', 0, '')"
        )
        self._rehash(1)
        self.assert_single_failure(
            "memory supersede pointers resolve", "M-0001", "M-0999"
        )

    def _rehash(self, memory_id: int) -> None:
        """Give a hand-planted claim the hash its own fields imply."""
        conn = db.connect(self.db_path)
        try:
            with conn:
                item = ops.get_memory(conn, memory_id)
                conn.execute(
                    "UPDATE memory SET content_sha256 = ? WHERE id = ?",
                    (ops.claim_digest(conn, item), memory_id),
                )
        finally:
            conn.close()

    def test_fails_on_pack_row_with_missing_task(self):
        self.corrupt("UPDATE packs SET task_id = 999 WHERE id = 1")
        self.assert_single_failure(
            "packs reference existing tasks and files", "P-0001", "missing task"
        )

    def test_fails_on_pack_file_deleted_from_disk(self):
        (self.aos_dir / "packs" / "T-0001-claude-code.md").unlink()
        self.assert_single_failure(
            "packs reference existing tasks and files",
            "P-0001",
            "missing file",
        )

    def test_schema_version_check_at_the_checks_layer(self):
        # The CLI cannot reach doctor with a wrong schema_version (open_db
        # hard-stops), so exercise run_checks directly.
        from agentic_os import doctor as doctor_mod

        self.corrupt(
            "UPDATE meta SET value = '999' WHERE key = 'schema_version'"
        )
        conn = db.connect(self.db_path)
        try:
            checks = doctor_mod.run_checks(conn, self.aos_dir)
        finally:
            conn.close()
        by_name = {check.name: check for check in checks}
        schema_check = by_name["schema_version supported"]
        self.assertFalse(schema_check.ok)
        self.assertIn("'999'", schema_check.detail)
        # And the CLI path still refuses loudly (exit 1, no traceback).
        code, out, err = self.aos_fails("doctor")
        self.assertIn("schema_version", err)


if __name__ == "__main__":
    unittest.main()
