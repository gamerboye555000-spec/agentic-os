"""U-M3 provenance, temporal, relationship and contradiction memory graph
(agentic-os-v0.3-u-m3-memory-graph-contract.md).

Two kinds of proof live here:

- MIGRATION proofs run against the real historical v2 fixture
  (tests/fixtures/v2_workspace.py), copied to a temp workspace, and drive the
  PRODUCTION registry — no synthetic step is needed or wanted.
- GRAPH proofs run against a fresh v3 workspace through the CLI.

Nothing here touches a real ledger: every workspace is a temp directory, and
no test opens, fetches or executes anything a source points at.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fixtures.v2_workspace import build_v2_workspace, table_contents
from weekend_harness import run_cli

from agentic_os import backup, db, migrations, models, ops, power, utils

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Planted in a locator and a claim, where a careless implementation would
#: echo it back out (U-C3).
FAKE_SECRET = "sk-live-m3planted00000000000000000000000000000000"  # noqa: S105

#: A locator that would be catastrophic to follow, and a URL that would be
#: catastrophic to fetch. Nothing in U-M3 may touch either (D-v0.3.47).
BOOBY_TRAP_NAME = "aos-m3-must-never-be-read.txt"


# ---------------------------------------------------------------------------
# Bases

class V2FixtureTestCase(unittest.TestCase):
    """A disposable copy of the historical v2 fixture workspace."""

    _fixture_root: Path | None = None

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.mkdtemp(prefix="aos-m3-fixture-")
        cls._fixture_tmp = tmp
        cls._fixture_root = Path(tmp) / "v2"
        build_v2_workspace(cls._fixture_root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._fixture_tmp, ignore_errors=True)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "ws"
        shutil.copytree(self._fixture_root, self.root, symlinks=True)
        self.aos_dir = self.root / utils.AOS_DIR_NAME
        self.db_path = self.aos_dir / utils.DB_FILENAME
        self.backups_dir = self.aos_dir / backup.BACKUPS_DIRNAME

    def aos(self, *argv: str) -> tuple[int, str, str]:
        return run_cli("--root", str(self.root), *argv)

    def query(self, sql: str, params=()) -> list[sqlite3.Row]:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def version(self) -> str:
        return self.query("SELECT value FROM meta WHERE key='schema_version'")[0][0]

    def table_names(self) -> set[str]:
        return {
            row[0]
            for row in self.query("SELECT name FROM sqlite_master WHERE type='table'")
        }

    def migrate_events(self) -> list[dict]:
        return [
            json.loads(row[0])
            for row in self.query(
                "SELECT payload_json FROM events WHERE entity=? AND action=?",
                (migrations.MIGRATION_EVENT_ENTITY, migrations.MIGRATION_EVENT_ACTION),
            )
        ]

    def migrate(self) -> None:
        code, _, err = self.aos("migrate", "apply")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.version(), "3")


class V3WorkspaceTestCase(unittest.TestCase):
    """A fresh v3 workspace: two projects, a task with evidence, and a file
    on disk that no command may ever open."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.other_repo = self.root / "other"
        self.other_repo.mkdir()
        self.aos_dir = self.root / utils.AOS_DIR_NAME
        self.db_path = self.aos_dir / utils.DB_FILENAME
        # The booby trap: a real file, at a real path, that a `file` source
        # will name. Reading it is the failure this fixture exists to detect.
        self.trap = self.root / BOOBY_TRAP_NAME
        self.trap.write_text("if this text ever appears in output, U-M3 leaked\n")
        self.ok("init")
        self.ok("project", "add", "demo", "--name", "Demo", "--repo", str(self.repo))
        self.ok(
            "project", "add", "other", "--name", "Other",
            "--repo", str(self.other_repo),
        )
        self.ok("task", "add", "Demo task", "-p", "demo", "--accept", "works")
        self.ok(
            "evidence", "add", "T-0001", "--kind", "note",
            "--ref", "proof", "--claim", "it works",
        )

    # --- CLI

    def aos(self, *argv: str) -> tuple[int, str, str]:
        return run_cli("--root", str(self.root), *argv)

    def ok(self, *argv: str) -> str:
        code, out, err = self.aos(*argv)
        self.assertEqual(code, 0, f"{argv} failed: {err}")
        return out

    def fails(self, *argv: str) -> tuple[str, str]:
        code, out, err = self.aos(*argv)
        self.assertEqual(code, 1, f"{argv} unexpectedly exited {code}: {out}{err}")
        return out, err

    # --- builders

    def add_memory(
        self, *extra: str, key="storage", value="sqlite only", scope="project"
    ) -> str:
        argv = ["memory", "add", "--scope", scope]
        if scope == "project":
            argv += ["--project", "demo"]
        argv += [
            "--kind", "constraint", "--key", key, "--value", value,
            "--source", "human", "--confidence", "confirmed", *extra,
        ]
        return self.ok(*argv).strip()

    def add_source(self, *extra: str, kind="url", locator="https://example.test/a") -> str:
        argv = ["memory", "source", "add", "--kind", kind]
        if locator is not None:
            argv += ["--locator", locator]
        return self.ok(*argv, *extra).strip()

    def add_edge(self, a: str, b: str, relation: str, *extra: str) -> str:
        return self.ok("memory", "edge", "add", a, b, "--relation", relation, *extra)

    # --- probes

    def show(self, memory_hid: str) -> dict:
        return json.loads(self.ok("memory", "show", memory_hid, "--json"))

    def listing(self, *extra: str) -> list[dict]:
        return json.loads(self.ok("memory", "list", "--json", *extra))["memories"]

    def sources(self, *extra: str) -> list[dict]:
        return json.loads(self.ok("memory", "source", "list", "--json", *extra))[
            "sources"
        ]

    def edges(self, *extra: str) -> list[dict]:
        return json.loads(self.ok("memory", "edge", "list", "--json", *extra))["edges"]

    def graph(self, memory_hid: str, *extra: str) -> dict:
        return json.loads(self.ok("memory", "graph", memory_hid, "--json", *extra))

    def contradictions(self, *extra: str) -> list[dict]:
        return json.loads(
            self.ok("memory", "contradictions", "--json", *extra)
        )["contradictions"]

    def query(self, sql: str, params=()) -> list[sqlite3.Row]:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def write(self, sql: str, params=()) -> None:
        """Tamper directly with the ledger — the thing the hashes exist to
        catch. Deliberately bypasses every ops-layer guard."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    def events(self, entity: str) -> list[dict]:
        return [
            {"action": row["action"], "payload": json.loads(row["payload_json"])}
            for row in self.query(
                "SELECT action, payload_json FROM events WHERE entity=? ORDER BY id",
                (entity,),
            )
        ]

    def all_event_text(self) -> str:
        return "\n".join(
            row[0] for row in self.query("SELECT payload_json FROM events")
        )

    def pack_memory_section(self) -> str:
        self.ok("pack", "build", "T-0001", "--for", "claude-code")
        path = self.query("SELECT path FROM packs ORDER BY id DESC LIMIT 1")[0][0]
        text = (self.aos_dir / path).read_text(encoding="utf-8")
        return text.split("## MEMORY")[1].split("## ")[0]

    def doctor_lines(self) -> str:
        code, out, err = self.aos("doctor")
        self.assertIn(code, (0, 1), err)
        return out


# ---------------------------------------------------------------------------
# (1)(2) Schema version 3 and the production registry

class SchemaVersionTest(V3WorkspaceTestCase):
    def test_fresh_init_creates_schema_version_three(self):
        """(1)"""
        self.assertEqual(db.SCHEMA_VERSION, "3")
        self.assertEqual(
            self.query("SELECT value FROM meta WHERE key='schema_version'")[0][0],
            "3",
        )

    def test_fresh_init_creates_the_three_graph_tables(self):
        """(1)"""
        names = {
            row[0]
            for row in self.query("SELECT name FROM sqlite_master WHERE type='table'")
        }
        self.assertLessEqual(
            {"memory_sources", "memory_source_links", "memory_edges"}, names
        )

    def test_production_registry_is_exactly_the_two_steps_in_order(self):
        """(2)"""
        self.assertEqual(
            [
                (m.from_version, m.to_version, m.migration_id)
                for m in migrations.MIGRATIONS
            ],
            [
                (1, 2, "u-m2-memory-claims-v2"),
                (2, 3, "u-m3-memory-graph-v3"),
            ],
        )
        migrations.validate_registry()

    def test_latest_version_is_derived_from_the_one_schema_declaration(self):
        """(2) A bump that lands in only one of two places fails here."""
        self.assertEqual(migrations.LATEST_VERSION, int(db.SCHEMA_VERSION))
        self.assertEqual(migrations.LATEST_VERSION, 3)

    def test_no_version_four_transition_exists(self):
        """(2)"""
        self.assertEqual(
            [m.to_version for m in migrations.MIGRATIONS if m.to_version > 3], []
        )

    def test_fresh_v3_memory_table_carries_sensitivity(self):
        """(1)(17)"""
        columns = {
            row["name"]: row for row in self.query("PRAGMA table_info(memory)")
        }
        self.assertIn("sensitivity", columns)
        self.assertEqual(columns["sensitivity"]["notnull"], 1)
        self.assertEqual(columns["sensitivity"]["dflt_value"], "'internal'")


# ---------------------------------------------------------------------------
# (3)(4)(5) Status, plan and the pre-mutation snapshot

class StatusAndPlanTest(V2FixtureTestCase):
    def test_v2_fixture_reports_exactly_one_pending_migration(self):
        """(3)"""
        report = migrations.status(self.db_path)
        self.assertEqual(report["current_version"], 2)
        self.assertEqual(report["latest_version"], 3)
        self.assertTrue(report["pending"])
        self.assertEqual(
            report["plan"],
            [{"from": 2, "to": 3, "migration_id": "u-m3-memory-graph-v3"}],
        )

    def test_plan_shows_exactly_two_to_three_and_writes_nothing(self):
        """(4) Read-only means byte-for-byte, not 'probably fine'."""
        before = self.db_path.read_bytes()
        listing_before = sorted(
            p.name for p in self.aos_dir.rglob("*")
        )
        code, out, err = self.aos("migrate", "plan")
        self.assertEqual(code, 0, err)
        self.assertIn("2 → 3  u-m3-memory-graph-v3", out)
        self.assertNotIn("1 → 2", out)
        self.assertEqual(self.db_path.read_bytes(), before)
        self.assertEqual(sorted(p.name for p in self.aos_dir.rglob("*")), listing_before)

    def test_status_cli_reports_pending(self):
        """(3)"""
        code, out, err = self.aos("migrate", "status")
        self.assertEqual(code, 0, err)
        self.assertIn("schema version:  2", out)
        self.assertIn("build supports:  3", out)
        self.assertIn("pending:         yes", out)

    def test_apply_verifies_a_v2_snapshot_before_it_mutates(self):
        """(5) The snapshot must be a real v2 database, verified AS v2."""
        self.assertFalse(self.backups_dir.exists())
        self.migrate()
        snapshots = sorted(self.backups_dir.glob("*.db"))
        self.assertEqual(len(snapshots), 1)
        checks = backup.verify_backup(snapshots[0], expected_schema_version="2")
        self.assertTrue(all(c.ok for c in checks), [c.detail for c in checks if not c.ok])
        # And it really is pre-migration: no sensitivity column in it.
        conn = sqlite3.connect(snapshots[0])
        try:
            columns = {r[1] for r in conn.execute("PRAGMA table_info(memory)")}
            tables = {
                r[0]
                for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
        finally:
            conn.close()
        self.assertNotIn("sensitivity", columns)
        self.assertNotIn("memory_sources", tables)

    def test_snapshot_is_taken_before_the_first_mutation(self):
        """(5) Not 'a snapshot exists afterwards' — one existed BEFORE the
        step body ran, and verified AS v2. The spy asserts it from inside the
        step, which is the only moment that proves ordering.

        The registry is INJECTED, not patched onto the module: apply_migrations
        binds MIGRATIONS as a default argument, so a module-level patch would
        be silently ignored and this test would pass by not running.
        """
        seen: dict = {}
        real = migrations.MEMORY_GRAPH_V3.apply

        def spy(conn):
            seen["snapshots"] = sorted(self.backups_dir.glob("*.db"))
            seen["verified"] = [
                backup.verify_backup(path, expected_schema_version="2")
                for path in seen["snapshots"]
            ]
            return real(conn)

        result = migrations.apply_migrations(
            self.aos_dir,
            registry=(migrations.Migration(2, 3, "u-m3-memory-graph-v3", spy),),
            latest=3,
        )
        self.assertTrue(result["migrated"])
        self.assertEqual(self.version(), "3")
        self.assertEqual(len(seen["snapshots"]), 1)
        self.assertTrue(all(c.ok for checks in seen["verified"] for c in checks))


# ---------------------------------------------------------------------------
# (6)-(13) What the 2 → 3 migration preserves, adds, and refuses to invent

class MigrationPreservationTest(V2FixtureTestCase):
    def setUp(self):
        super().setUp()
        self.before = table_contents(self.db_path)
        self.legacy_memory = {
            row["id"]: dict(row)
            for row in self.query("SELECT * FROM memory ORDER BY id")
        }
        self.legacy_links = [
            tuple(row) for row in self.query("SELECT * FROM memory_evidence")
        ]

    def test_every_claim_id_and_field_survives_unchanged(self):
        """(6)"""
        self.migrate()
        after = {
            row["id"]: dict(row)
            for row in self.query("SELECT * FROM memory ORDER BY id")
        }
        self.assertEqual(sorted(after), sorted(self.legacy_memory))
        for memory_id, legacy in self.legacy_memory.items():
            for field in (
                "scope", "project_id", "kind", "key", "value_md", "source",
                "confidence", "valid_from", "valid_until", "superseded_by",
                "updated_at", "status", "pinned",
            ):
                self.assertEqual(
                    after[memory_id][field], legacy[field],
                    f"M-{memory_id:04d}.{field} changed",
                )

    def test_every_migrated_claim_is_internal(self):
        """(7)"""
        self.migrate()
        levels = {
            row["id"]: row["sensitivity"]
            for row in self.query("SELECT id, sensitivity FROM memory")
        }
        self.assertEqual(set(levels.values()), {"internal"})
        self.assertEqual(len(levels), len(self.legacy_memory))

    def test_a_quarantined_claim_keeps_its_status(self):
        """(6) Not just the two statuses that are easy to make."""
        self.migrate()
        statuses = {
            row["key"]: row["status"]
            for row in self.query("SELECT key, status FROM memory")
        }
        self.assertEqual(statuses["review-notes"], "quarantined")

    def test_memory_evidence_survives_byte_for_byte(self):
        """(8)"""
        self.migrate()
        after = [tuple(row) for row in self.query("SELECT * FROM memory_evidence")]
        self.assertEqual(after, self.legacy_links)
        self.assertTrue(self.legacy_links, "fixture must carry at least one link")

    def test_no_source_link_or_edge_row_is_invented(self):
        """(9) D-v0.3.44 — the graph tables come out EMPTY."""
        self.migrate()
        for table in ("memory_sources", "memory_source_links", "memory_edges"):
            self.assertEqual(
                self.query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"], 0, table
            )

    def test_every_migrated_claim_gets_the_correct_v3_hash(self):
        """(10) Recomputed under the v3 payload, and the v2 hash is gone."""
        v2_hashes = {
            mid: legacy["content_sha256"]
            for mid, legacy in self.legacy_memory.items()
        }
        self.migrate()
        conn = db.connect(self.db_path)
        try:
            for row in conn.execute("SELECT * FROM memory ORDER BY id"):
                item = models.MemoryItem.from_row(row)
                self.assertEqual(ops.claim_integrity(conn, item), "ok")
                self.assertEqual(
                    item.content_sha256, ops.claim_digest(conn, item)
                )
                # A v3 hash is not a v2 hash: the payload gained a leaf.
                self.assertNotEqual(item.content_sha256, v2_hashes[item.id])
        finally:
            conn.close()

    def test_claim_with_evidence_links_hashes_its_links_after_migration(self):
        """(10) The v3 hash binds the link set the claim ALREADY had — no
        link invented, none dropped."""
        self.migrate()
        conn = db.connect(self.db_path)
        try:
            item = ops.get_memory(conn, 2)
            self.assertEqual(ops.memory_evidence_ids(conn, 2), [1])
            self.assertEqual(ops.claim_integrity(conn, item), "ok")
        finally:
            conn.close()

    def test_every_other_table_is_untouched(self):
        """(6)(8) Only `memory`, `meta` and `events` may differ."""
        self.migrate()
        after = table_contents(self.db_path)
        for table in self.before:
            if table in ("meta", "memory", "events"):
                continue
            self.assertEqual(after[table], self.before[table], table)

    def test_schema_advances_exactly_once(self):
        """(12)"""
        self.migrate()
        rows = self.query("SELECT value FROM meta WHERE key='schema_version'")
        self.assertEqual([tuple(r) for r in rows], [("3",)])
        code, out, _ = self.aos("migrate", "apply")
        self.assertEqual(code, 0)
        self.assertIn("No migrations pending", out)
        self.assertEqual(len(self.migrate_events()), 1)

    def test_exactly_one_privacy_safe_migration_event(self):
        """(13)"""
        self.migrate()
        events = self.migrate_events()
        self.assertEqual(len(events), 1)
        payload = events[0]
        self.assertEqual(payload["from"], 2)
        self.assertEqual(payload["to"], 3)
        self.assertEqual(payload["migration_id"], "u-m3-memory-graph-v3")
        blob = json.dumps(payload)
        for legacy in self.legacy_memory.values():
            self.assertNotIn(legacy["key"], blob)
            self.assertNotIn(legacy["value_md"], blob)
        self.assertNotIn("INSERT", blob.upper())
        self.assertNotIn("SELECT", blob.upper())

    def test_migrated_shape_matches_a_freshly_initialized_v3(self):
        """(11) Columns, and then the SQL itself — every CHECK and FK
        clause — for the memory table AND all three graph tables."""
        self.migrate()
        fresh_dir = self.root.parent / "fresh"
        fresh_dir.mkdir()
        conn, _ = db.init_db(fresh_dir / utils.AOS_DIR_NAME / utils.DB_FILENAME)
        try:
            fresh_info = {
                table: [tuple(r)[1:] for r in conn.execute(f"PRAGMA table_info({table})")]
                for table in _GRAPH_SCHEMA_TABLES
            }
            fresh_sql = _schema_objects(conn)
        finally:
            conn.close()
        migrated_info = {
            table: [tuple(r)[1:] for r in self.query(f"PRAGMA table_info({table})")]
            for table in _GRAPH_SCHEMA_TABLES
        }
        self.assertEqual(migrated_info, fresh_info)

        conn = sqlite3.connect(self.db_path)
        try:
            migrated_sql = _schema_objects(conn)
        finally:
            conn.close()
        self.assertEqual(migrated_sql, fresh_sql)

    def test_migrated_indexes_match_a_freshly_initialized_v3(self):
        """(11) Including the implicit UNIQUE indexes — D-v0.3.45 adds no
        explicit ones, and this is what proves it stayed that way."""
        self.migrate()
        fresh_dir = self.root.parent / "fresh-idx"
        fresh_dir.mkdir()
        conn, _ = db.init_db(fresh_dir / utils.AOS_DIR_NAME / utils.DB_FILENAME)
        try:
            fresh = _index_shape(conn)
        finally:
            conn.close()
        conn = sqlite3.connect(self.db_path)
        try:
            migrated = _index_shape(conn)
        finally:
            conn.close()
        self.assertEqual(migrated, fresh)
        # No explicit index: every index here is one SQLite created itself.
        self.assertEqual([name for name, sql, _ in fresh if sql is not None], [])

    def test_constraints_are_live_on_a_migrated_database(self):
        """(11)(17) The CHECKs came across with the rebuild."""
        self.migrate()
        for sql in (
            "UPDATE memory SET sensitivity = 'invented' WHERE id = 1",
            "INSERT INTO memory_edges (from_memory_id, to_memory_id, relation, "
            "created_at, content_sha256) VALUES (1, 1, 'related', 'x', 'y')",
            "INSERT INTO memory_sources (source_kind, evidence_id, locator, "
            "provenance, sensitivity, observed_at, created_at, content_sha256) "
            "VALUES ('evidence', 1, 'both', 'human', 'internal', 'x', 'y', 'z')",
        ):
            with self.subTest(sql=sql[:40]):
                conn = db.connect(self.db_path)
                try:
                    with self.assertRaises(sqlite3.IntegrityError):
                        conn.execute(sql)
                        conn.commit()
                finally:
                    conn.close()


#: The memory-and-graph tables the fresh/migrated identity proof compares.
_GRAPH_SCHEMA_TABLES = (
    "memory",
    "memory_evidence",
    "memory_sources",
    "memory_source_links",
    "memory_edges",
)


def _normalize_table_sql(sql: str) -> str:
    """Strip the ONE documented storage mechanic (D-v0.3.51).

    `ALTER TABLE x RENAME TO memory` makes SQLite store `CREATE TABLE
    "memory"(...)` where a fresh init stores `CREATE TABLE memory(...)`. That
    quoting is a rename artifact, not a schema difference — and it is the only
    thing normalized here. Every column, type, default, CHECK and FOREIGN KEY
    clause is compared verbatim.
    """
    return sql.replace('CREATE TABLE "', "CREATE TABLE ", 1).replace(
        '"(', "(", 1
    ) if sql.startswith('CREATE TABLE "') else sql


def _schema_objects(conn) -> list[tuple]:
    return [
        (row[0], row[1], _normalize_table_sql(row[2]) if row[2] else None)
        for row in conn.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE name LIKE 'memory%' ORDER BY type, name"
        )
    ]


def _index_shape(conn) -> list[tuple]:
    return sorted(
        (row[0], row[1], row[2])
        for row in conn.execute(
            "SELECT name, sql, tbl_name FROM sqlite_master WHERE type='index' "
            "AND tbl_name LIKE 'memory%'"
        )
    )


# ---------------------------------------------------------------------------
# (14)(15)(16) Failure, retry, and the version gate

class MigrationFailureTest(V2FixtureTestCase):
    def _boom(self, conn):
        # Fails AFTER the real work, so rollback has everything to undo.
        migrations.MEMORY_GRAPH_V3.apply(conn)
        raise RuntimeError(f"planted failure {FAKE_SECRET}")

    def _failing_registry(self):
        """The 2 → 3 step, replaced by one that fails after doing the work.

        Injected rather than patched onto the module: apply_migrations binds
        MIGRATIONS as a DEFAULT argument, so `mock.patch.object(migrations,
        "MIGRATIONS", ...)` is silently ignored — the real step would run and
        every assertion below would pass for the wrong reason.
        """
        return (migrations.Migration(2, 3, "u-m3-memory-graph-v3", self._boom),)

    def _apply_failing(self) -> migrations.MigrationStepError:
        with self.assertRaises(migrations.MigrationStepError) as caught:
            migrations.apply_migrations(
                self.aos_dir, registry=self._failing_registry(), latest=3
            )
        return caught.exception

    def test_injected_failure_leaves_schema_two_intact(self):
        """(14)"""
        before = table_contents(self.db_path)
        self._apply_failing()
        self.assertEqual(self.version(), "2")
        after = table_contents(self.db_path)
        for table in before:
            if table == "events":
                continue
            self.assertEqual(after[table], before[table], table)

    def test_injected_failure_leaves_no_graph_table_and_no_event(self):
        """(14)"""
        self._apply_failing()
        names = self.table_names()
        for table in ("memory_sources", "memory_source_links", "memory_edges"):
            self.assertNotIn(table, names)
        self.assertEqual(self.migrate_events(), [])
        columns = {r["name"] for r in self.query("PRAGMA table_info(memory)")}
        self.assertNotIn("sensitivity", columns)

    def test_injected_failure_leaves_a_verified_v2_snapshot(self):
        """(14)"""
        error = self._apply_failing()
        snapshots = sorted(self.backups_dir.glob("*.db"))
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(error.snapshot, snapshots[0])
        checks = backup.verify_backup(snapshots[0], expected_schema_version="2")
        self.assertTrue(all(c.ok for c in checks))

    def test_failure_message_never_echoes_the_planted_secret(self):
        """(14)(49) The class name only — never str(exc)."""
        message = str(self._apply_failing())
        self.assertNotIn(FAKE_SECRET, message)
        self.assertIn("RuntimeError", message)
        self.assertIn("rolled back", message)

    def test_corrected_retry_succeeds_exactly_once(self):
        """(15)"""
        self._apply_failing()
        self.assertEqual(self.version(), "2")
        self.migrate()  # the real step, unpatched
        self.assertEqual(len(self.migrate_events()), 1)
        self.assertEqual(
            self.query("SELECT COUNT(*) AS n FROM memory")[0]["n"], 6
        )
        code, out, _ = self.aos("doctor")
        self.assertEqual(code, 0, out)

    def test_normal_v3_commands_refuse_an_unmigrated_v2_database(self):
        """(16)"""
        for argv in (
            ("memory", "list"),
            ("memory", "graph", "M-0001"),
            ("memory", "source", "list"),
            ("memory", "edge", "list"),
            ("memory", "contradictions"),
            ("memory", "classify", "M-0001", "confidential"),
            ("doctor",),
            ("status",),
        ):
            with self.subTest(argv=argv):
                code, _, err = self.aos(*argv)
                self.assertEqual(code, 1)
                self.assertIn("schema_version is '2'", err)
                self.assertIn("migrate", err)
        self.assertEqual(self.version(), "2")


# ---------------------------------------------------------------------------
# (17)-(22) Sensitivity and classification

class SensitivityTest(V3WorkspaceTestCase):
    def test_vocabulary_is_closed_at_both_boundaries(self):
        """(17)"""
        self.assertEqual(
            models.MEMORY_SENSITIVITIES,
            ("public", "internal", "confidential", "restricted"),
        )
        _, err = self.fails(
            "memory", "add", "--scope", "global", "--kind", "fact",
            "--key", "k", "--value", "v", "--source", "human",
            "--confidence", "confirmed", "--sensitivity", "invented",
        )
        self.assertIn("invalid choice", err.lower())

    def test_check_constraint_refuses_an_unknown_level(self):
        """(17) The storage boundary, independent of the CLI."""
        self.add_memory()
        conn = db.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE memory SET sensitivity = 'secret' WHERE id = 1")
                conn.commit()
        finally:
            conn.close()

    def test_new_memory_defaults_to_internal(self):
        """(18)"""
        hid = self.add_memory()
        self.assertEqual(self.show(hid)["sensitivity"], "internal")

    def test_memory_add_accepts_an_explicit_sensitivity(self):
        """(19)"""
        for level in models.MEMORY_SENSITIVITIES:
            with self.subTest(level=level):
                hid = self.add_memory("--sensitivity", level, key=f"k-{level}")
                self.assertEqual(self.show(hid)["sensitivity"], level)

    def test_classify_permits_only_monotonic_increases(self):
        """(20)"""
        hid = self.add_memory("--sensitivity", "public")
        for level in ("internal", "confidential", "restricted"):
            out = self.ok("memory", "classify", hid, level)
            self.assertIn(f"classified {level}", out)
            self.assertEqual(self.show(hid)["sensitivity"], level)

    def test_classify_same_state_is_an_idempotent_no_op(self):
        """(21) No write, no rehash, and NO event."""
        hid = self.add_memory()
        before = self.show(hid)
        before_events = len(self.events("memory"))
        out = self.ok("memory", "classify", hid, "internal")
        self.assertIn("already internal", out)
        self.assertIn("nothing changed", out)
        self.assertEqual(self.show(hid), before)
        self.assertEqual(len(self.events("memory")), before_events)

    def test_classify_downgrade_refuses_unchanged(self):
        """(22)"""
        hid = self.add_memory("--sensitivity", "confidential")
        before = self.show(hid)
        _, err = self.fails("memory", "classify", hid, "internal")
        self.assertIn("down-classify", err)
        self.assertIn("U-S6", err)
        self.assertEqual(self.show(hid), before)

    def test_classify_updates_the_claim_hash_and_emits_one_safe_event(self):
        """(20)"""
        hid = self.add_memory(key=f"key {FAKE_SECRET}", value=f"body {FAKE_SECRET}")
        self.ok("memory", "classify", hid, "confidential")
        doc = self.show(hid)
        self.assertEqual(doc["integrity"], "ok")
        classify = [e for e in self.events("memory") if e["action"] == "classify"]
        self.assertEqual(len(classify), 1)
        payload = classify[0]["payload"]
        self.assertEqual(payload["from_sensitivity"], "internal")
        self.assertEqual(payload["sensitivity"], "confidential")
        blob = json.dumps(payload)
        self.assertNotIn(FAKE_SECRET, blob)
        self.assertNotIn("sqlite only", blob)

    def test_classify_verifies_the_old_hash_before_mutating(self):
        """(20) No laundering — D-v0.3.41."""
        hid = self.add_memory()
        self.write("UPDATE memory SET value_md = 'rewritten' WHERE id = 1")
        _, err = self.fails("memory", "classify", hid, "confidential")
        self.assertIn("Refusing to change memory", err)
        self.assertEqual(
            self.query("SELECT sensitivity FROM memory WHERE id=1")[0][0], "internal"
        )

    def test_sensitivity_is_bound_into_the_claim_hash(self):
        """(25-analogue for claims) Tampering with the field that decides
        who sees a claim breaks its hash like any other."""
        hid = self.add_memory()
        self.assertEqual(self.show(hid)["integrity"], "ok")
        self.write("UPDATE memory SET sensitivity = 'public' WHERE id = 1")
        self.assertEqual(self.show(hid)["integrity"], "mismatch")

    def test_claim_schema_identity_is_v3(self):
        """(10)"""
        self.assertEqual(ops.CLAIM_SCHEMA, "aos.memory-claim/v3")
        conn = db.connect(self.db_path)
        try:
            self.add_memory()
            payload = ops.memory_claim_payload(ops.get_memory(conn, 1), ())
        finally:
            conn.close()
        self.assertEqual(payload["claim_schema"], "aos.memory-claim/v3")
        self.assertIn("sensitivity_sha256", payload)
        self.assertNotIn("content_sha256", payload)

    def test_pinning_a_restricted_claim_refuses(self):
        """(D-v0.3.33) Pin never overrides sensitivity."""
        _, err = self.fails(
            "memory", "add", "--scope", "global", "--kind", "fact",
            "--key", "k", "--value", "v", "--source", "human",
            "--confidence", "confirmed", "--sensitivity", "restricted", "--pin",
        )
        self.assertIn("restricted", err)
        self.assertEqual(self.query("SELECT COUNT(*) AS n FROM memory")[0]["n"], 0)


# ---------------------------------------------------------------------------
# (23)-(26) Sources

class SourceTest(V3WorkspaceTestCase):
    def test_source_kind_structural_rules_enforce_at_the_cli(self):
        """(23)"""
        _, err = self.fails("memory", "source", "add", "--kind", "evidence")
        self.assertIn("--evidence", err)
        _, err = self.fails(
            "memory", "source", "add", "--kind", "evidence",
            "--evidence", "E-0001", "--locator", "x",
        )
        self.assertIn("must not carry --locator", err)
        _, err = self.fails("memory", "source", "add", "--kind", "url")
        self.assertIn("--locator", err)
        _, err = self.fails(
            "memory", "source", "add", "--kind", "url",
            "--locator", "x", "--evidence", "E-0001",
        )
        self.assertIn("must not carry --evidence", err)
        self.assertEqual(
            self.query("SELECT COUNT(*) AS n FROM memory_sources")[0]["n"], 0
        )

    def test_source_kind_structural_rules_enforce_at_the_database(self):
        """(23) Independently of the CLI."""
        conn = db.connect(self.db_path)
        try:
            for values in (
                "('evidence', NULL, 'loc', 'human', 'internal', 'x', 'y', 'z')",
                "('evidence', 1, 'loc', 'human', 'internal', 'x', 'y', 'z')",
                "('url', 1, NULL, 'human', 'internal', 'x', 'y', 'z')",
                "('url', NULL, NULL, 'human', 'internal', 'x', 'y', 'z')",
            ):
                with self.subTest(values=values):
                    with self.assertRaises(sqlite3.IntegrityError):
                        conn.execute(
                            "INSERT INTO memory_sources (source_kind, evidence_id, "
                            "locator, provenance, sensitivity, observed_at, "
                            f"created_at, content_sha256) VALUES {values}"
                        )
                        conn.commit()
        finally:
            conn.close()

    def test_all_source_kinds_are_storable(self):
        """(23)"""
        self.assertEqual(
            models.MEMORY_SOURCE_KINDS,
            ("evidence", "file", "url", "command", "human", "agent", "artifact"),
        )
        self.ok(
            "memory", "source", "add", "--kind", "evidence", "--evidence", "E-0001"
        )
        for kind in ("file", "url", "command", "human", "agent", "artifact"):
            with self.subTest(kind=kind):
                self.add_source(kind=kind, locator=f"{kind}://x")
        self.assertEqual(len(self.sources()), 7)

    def test_evidence_source_stores_the_id_and_no_evidence_text(self):
        """(D-v0.3.34) No claim, ref, sha or body is copied."""
        self.ok(
            "memory", "source", "add", "--kind", "evidence", "--evidence", "E-0001"
        )
        row = dict(self.query("SELECT * FROM memory_sources WHERE id=1")[0])
        self.assertEqual(row["evidence_id"], 1)
        self.assertIsNone(row["locator"])
        blob = json.dumps({k: v for k, v in row.items() if isinstance(v, str)})
        self.assertNotIn("proof", blob)      # the evidence ref
        self.assertNotIn("it works", blob)   # the evidence claim

    def test_source_project_and_timestamp_invariants_enforce(self):
        """(24)"""
        _, err = self.fails(
            "memory", "source", "add", "--kind", "url", "--locator", "x",
            "--project", "nope",
        )
        self.assertIn("No project", err)
        _, err = self.fails(
            "memory", "source", "add", "--kind", "url", "--locator", "x",
            "--observed-at", "not-a-date",
        )
        self.assertIn("--observed-at", err)
        _, err = self.fails(
            "memory", "source", "add", "--kind", "url", "--locator", "x",
            "--valid-from", "2027-01-01", "--valid-until", "2026-01-01",
        )
        self.assertIn("inverted validity window", err)
        self.assertEqual(
            self.query("SELECT COUNT(*) AS n FROM memory_sources")[0]["n"], 0
        )

    def test_inverted_window_also_refuses_at_the_database(self):
        """(24)"""
        conn = db.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO memory_sources (source_kind, locator, provenance, "
                    "sensitivity, observed_at, valid_from, valid_until, created_at, "
                    "content_sha256) VALUES ('url', 'x', 'human', 'internal', 'a', "
                    "'2027-01-01', '2026-01-01', 'c', 'd')"
                )
                conn.commit()
        finally:
            conn.close()

    def test_timestamps_accept_both_utc_spellings(self):
        """(24) A date and a full instant, and nothing else."""
        self.add_source(
            "--observed-at", "2026-07-16", "--valid-until", "2027-01-01T00:00:00Z",
            locator="https://a.test",
        )
        doc = self.sources()[0]
        self.assertEqual(doc["observed_at"], "2026-07-16")
        self.assertEqual(doc["valid_until"], "2027-01-01T00:00:00Z")
        _, err = self.fails(
            "memory", "source", "add", "--kind", "url", "--locator", "y",
            "--observed-at", "2026-07-16T00:00:00+01:00",
        )
        self.assertIn("Expected format", err)

    def test_source_hashes_detect_every_bound_field_mutation(self):
        """(25)"""
        self.add_source(locator="https://a.test", kind="url")
        conn = db.connect(self.db_path)
        try:
            self.assertEqual(
                ops.source_integrity(ops.get_memory_source(conn, 1)), "ok"
            )
        finally:
            conn.close()
        mutations = (
            "UPDATE memory_sources SET locator = 'https://evil.test' WHERE id=1",
            "UPDATE memory_sources SET provenance = 'agent:x' WHERE id=1",
            "UPDATE memory_sources SET sensitivity = 'public' WHERE id=1",
            "UPDATE memory_sources SET observed_at = '2000-01-01' WHERE id=1",
            "UPDATE memory_sources SET valid_until = '2000-01-01' WHERE id=1",
            "UPDATE memory_sources SET created_at = '2000-01-01' WHERE id=1",
            "UPDATE memory_sources SET project_id = 1 WHERE id=1",
            "UPDATE memory_sources SET source_kind = 'file' WHERE id=1",
        )
        for sql in mutations:
            with self.subTest(sql=sql[:50]):
                self.setUp()
                self.add_source(locator="https://a.test", kind="url")
                self.write(sql)
                conn = db.connect(self.db_path)
                try:
                    self.assertEqual(
                        ops.source_integrity(ops.get_memory_source(conn, 1)),
                        "mismatch",
                    )
                finally:
                    conn.close()

    def test_source_hash_detects_evidence_target_substitution(self):
        """(25)"""
        self.ok("task", "add", "Second", "-p", "demo")
        self.ok(
            "evidence", "add", "T-0002", "--kind", "note", "--ref", "other",
            "--claim", "different",
        )
        self.ok(
            "memory", "source", "add", "--kind", "evidence", "--evidence", "E-0001"
        )
        self.write("UPDATE memory_sources SET evidence_id = 2 WHERE id = 1")
        conn = db.connect(self.db_path)
        try:
            self.assertEqual(
                ops.source_integrity(ops.get_memory_source(conn, 1)), "mismatch"
            )
        finally:
            conn.close()

    def test_malformed_hashes_are_malformed_not_equivalent(self):
        """(25)"""
        for bad in ("", "  ", "ABC", "a" * 63, "A" * 64, "sha256:" + "a" * 64):
            with self.subTest(bad=bad):
                self.setUp()
                self.add_source(locator="https://a.test")
                self.write(
                    "UPDATE memory_sources SET content_sha256 = ? WHERE id=1", (bad,)
                )
                conn = db.connect(self.db_path)
                try:
                    self.assertEqual(
                        ops.source_integrity(ops.get_memory_source(conn, 1)),
                        "malformed",
                    )
                finally:
                    conn.close()

    def test_transplanted_hash_is_detected(self):
        """(25) `id` is bound, so a valid hash from another row is not valid
        here."""
        self.add_source(locator="https://a.test")
        self.add_source(locator="https://b.test")
        stolen = self.query("SELECT content_sha256 FROM memory_sources WHERE id=2")[0][0]
        self.write(
            "UPDATE memory_sources SET content_sha256 = ? WHERE id=1", (stolen,)
        )
        conn = db.connect(self.db_path)
        try:
            self.assertEqual(
                ops.source_integrity(ops.get_memory_source(conn, 1)), "mismatch"
            )
        finally:
            conn.close()

    def test_source_list_and_show_never_reveal_locator_or_provenance(self):
        """(26) The whole point of the command's shape."""
        self.add_source(
            "--provenance", "agent:leaky",
            locator=f"https://example.test/x?token={FAKE_SECRET}",
        )
        for argv in (
            ("memory", "source", "list"),
            ("memory", "source", "list", "--json"),
            ("memory", "source", "show", "MS-0001"),
            ("memory", "source", "show", "MS-0001", "--json"),
        ):
            with self.subTest(argv=argv):
                code, out, err = self.aos(*argv)
                self.assertEqual(code, 0, err)
                self.assertNotIn(FAKE_SECRET, out)
                self.assertNotIn("example.test", out)
                self.assertNotIn("agent:leaky", out)
                self.assertNotIn("locator", out.lower())
        doc = json.loads(self.ok("memory", "source", "show", "MS-0001", "--json"))
        self.assertNotIn("locator", doc)
        self.assertNotIn("provenance", doc)
        self.assertEqual(doc["integrity"], "ok")

    def test_source_events_never_carry_locator_or_provenance(self):
        """(49)"""
        self.add_source(
            "--provenance", "agent:leaky",
            locator=f"https://example.test/x?token={FAKE_SECRET}",
        )
        blob = self.all_event_text()
        self.assertNotIn(FAKE_SECRET, blob)
        self.assertNotIn("example.test", blob)
        self.assertNotIn("agent:leaky", blob)
        payload = self.events("memory_source")[0]["payload"]
        self.assertEqual(payload["kind"], "url")
        self.assertEqual(payload["sensitivity"], "internal")

    def test_doctor_secret_sweep_finds_a_locator_by_id_only(self):
        """(49) The other half of warn-on-write: the sweep finds the
        canonical row later — including one written directly, or written
        before the detector knew the pattern."""
        self.add_source(locator=f"https://x.test/?token={FAKE_SECRET}")
        code, out, err = self.aos("doctor")
        self.assertIn(code, (0, 1), err)
        line = [
            l for l in out.splitlines()
            if "secret-shaped text in ledger rows" in l
        ][0]
        self.assertTrue(line.startswith("[WARN]"), line)
        self.assertIn("memory_source MS-0001 locator", line)
        self.assertNotIn(FAKE_SECRET, out + err)
        self.assertNotIn("x.test", out)

    def test_secret_shaped_locator_warns_with_field_names_only(self):
        """(49) U-C3 warn-on-write, preserved."""
        code, out, err = self.aos(
            "memory", "source", "add", "--kind", "url",
            "--locator", f"https://x.test/?token={FAKE_SECRET}",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("WARNING", err)
        self.assertIn("locator", err)
        self.assertNotIn(FAKE_SECRET, err)
        payload = self.events("memory_source")[0]["payload"]
        self.assertTrue(payload["secret_warning"])
        self.assertIn("locator", payload["secret_fields"])

    def test_source_list_is_deterministic_and_filters(self):
        """(26)"""
        self.add_source(kind="url", locator="https://a.test")
        self.add_source(kind="file", locator="/tmp/a", **{})
        self.ok(
            "memory", "source", "add", "--kind", "url", "--locator", "https://b.test",
            "--project", "demo",
        )
        self.assertEqual([d["id"] for d in self.sources()], ["MS-0001", "MS-0002", "MS-0003"])
        self.assertEqual([d["id"] for d in self.sources("--kind", "file")], ["MS-0002"])
        self.assertEqual(
            [d["id"] for d in self.sources("--project", "demo")], ["MS-0003"]
        )
        self.assertEqual(self.sources(), self.sources())

    def test_expired_source_is_inactive_but_queryable(self):
        """(24)"""
        self.add_source("--valid-until", "2020-01-01", locator="https://old.test")
        self.add_source(locator="https://now.test")
        docs = self.sources()
        self.assertEqual([d["active"] for d in docs], [False, True])
        self.assertEqual([d["id"] for d in self.sources("--active-only")], ["MS-0002"])


# ---------------------------------------------------------------------------
# (27)-(30) Source links

class SourceLinkTest(V3WorkspaceTestCase):
    def test_link_records_provenance_without_touching_the_claim(self):
        """(27)"""
        hid = self.add_memory()
        self.add_source(locator="https://a.test")
        before = self.show(hid)
        out = self.ok("memory", "source", "link", hid, "MS-0001", "--relation", "supports")
        self.assertIn("ML-0001", out)
        after = self.show(hid)
        for field in ("status", "pinned", "sensitivity", "content_sha256", "live"):
            self.assertEqual(after[field], before[field], field)

    def test_all_source_relations_are_storable(self):
        """(27)"""
        self.assertEqual(
            models.MEMORY_SOURCE_RELATIONS,
            ("supports", "disputes", "context", "derived_from"),
        )
        hid = self.add_memory()
        self.add_source(locator="https://a.test")
        for relation in models.MEMORY_SOURCE_RELATIONS:
            with self.subTest(relation=relation):
                self.ok(
                    "memory", "source", "link", hid, "MS-0001", "--relation", relation
                )

    def test_links_enforce_project_compatibility(self):
        """(27)"""
        demo_claim = self.add_memory()  # project demo
        self.ok(
            "memory", "source", "add", "--kind", "url", "--locator", "https://o.test",
            "--project", "other",
        )
        _, err = self.fails(
            "memory", "source", "link", demo_claim, "MS-0001", "--relation", "supports"
        )
        self.assertIn("project source may back only claims in the same project", err)
        self.assertEqual(
            self.query("SELECT COUNT(*) AS n FROM memory_source_links")[0]["n"], 0
        )

    def test_a_project_source_may_not_back_a_global_claim(self):
        """(27) Stricter than the U-M2 evidence rule, deliberately."""
        global_claim = self.add_memory(scope="global", key="g")
        self.ok(
            "memory", "source", "add", "--kind", "url", "--locator", "https://d.test",
            "--project", "demo",
        )
        _, err = self.fails(
            "memory", "source", "link", global_claim, "MS-0001", "--relation", "supports"
        )
        self.assertIn("global scope", err)

    def test_a_global_source_may_back_a_project_or_global_claim(self):
        """(27)"""
        project_claim = self.add_memory()
        global_claim = self.add_memory(scope="global", key="g")
        self.add_source(locator="https://a.test")  # global
        self.ok(
            "memory", "source", "link", project_claim, "MS-0001", "--relation", "supports"
        )
        self.ok(
            "memory", "source", "link", global_claim, "MS-0001", "--relation", "context"
        )

    def test_links_enforce_sensitivity_monotonicity(self):
        """(28)"""
        hid = self.add_memory("--sensitivity", "internal")
        self.add_source("--sensitivity", "restricted", locator="https://a.test")
        _, err = self.fails(
            "memory", "source", "link", hid, "MS-0001", "--relation", "supports"
        )
        self.assertIn("more sensitive than the claim", err)
        self.assertIn("memory classify", err)
        self.assertEqual(
            self.query("SELECT COUNT(*) AS n FROM memory_source_links")[0]["n"], 0
        )

    def test_link_succeeds_once_the_claim_is_raised(self):
        """(28) The refusal names the fix, and the fix works."""
        hid = self.add_memory("--sensitivity", "internal")
        self.add_source("--sensitivity", "confidential", locator="https://a.test")
        self.fails("memory", "source", "link", hid, "MS-0001", "--relation", "supports")
        self.ok("memory", "classify", hid, "confidential")
        self.ok("memory", "source", "link", hid, "MS-0001", "--relation", "supports")

    def test_a_less_sensitive_source_may_back_a_more_sensitive_claim(self):
        """(28) Monotonic, not equal."""
        hid = self.add_memory("--sensitivity", "restricted")
        self.add_source("--sensitivity", "public", locator="https://a.test")
        self.ok("memory", "source", "link", hid, "MS-0001", "--relation", "supports")

    def test_duplicate_source_links_are_idempotent(self):
        """(29)"""
        hid = self.add_memory()
        self.add_source(locator="https://a.test")
        self.ok("memory", "source", "link", hid, "MS-0001", "--relation", "supports")
        before_events = len(self.events("memory_source_link"))
        out = self.ok("memory", "source", "link", hid, "MS-0001", "--relation", "supports")
        self.assertIn("already linked", out)
        self.assertIn("nothing changed", out)
        self.assertEqual(
            self.query("SELECT COUNT(*) AS n FROM memory_source_links")[0]["n"], 1
        )
        self.assertEqual(len(self.events("memory_source_link")), before_events)

    def test_the_same_source_under_a_different_relation_is_a_new_link(self):
        """(29) D-v0.3.35 — identity is (memory, source, relation)."""
        hid = self.add_memory()
        self.add_source(locator="https://a.test")
        self.ok("memory", "source", "link", hid, "MS-0001", "--relation", "supports")
        self.ok("memory", "source", "link", hid, "MS-0001", "--relation", "context")
        self.assertEqual(
            self.query("SELECT COUNT(*) AS n FROM memory_source_links")[0]["n"], 2
        )

    def test_duplicate_link_refuses_at_the_database_too(self):
        """(29)"""
        hid = self.add_memory()
        self.add_source(locator="https://a.test")
        self.ok("memory", "source", "link", hid, "MS-0001", "--relation", "supports")
        conn = db.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO memory_source_links (memory_id, source_id, "
                    "relation, created_at, content_sha256) "
                    "VALUES (1, 1, 'supports', 'x', 'y')"
                )
                conn.commit()
        finally:
            conn.close()

    def test_source_link_hashes_detect_tampering(self):
        """(30)"""
        hid = self.add_memory()
        self.add_memory(key="second")
        self.add_source(locator="https://a.test")
        self.add_source(locator="https://b.test")
        self.ok("memory", "source", "link", hid, "MS-0001", "--relation", "supports")
        for sql in (
            "UPDATE memory_source_links SET memory_id = 2 WHERE id=1",
            "UPDATE memory_source_links SET source_id = 2 WHERE id=1",
            "UPDATE memory_source_links SET relation = 'disputes' WHERE id=1",
            "UPDATE memory_source_links SET created_at = '2000-01-01' WHERE id=1",
        ):
            with self.subTest(sql=sql[:45]):
                conn = sqlite3.connect(self.db_path)
                try:
                    conn.row_factory = sqlite3.Row
                    original = dict(
                        conn.execute(
                            "SELECT * FROM memory_source_links WHERE id=1"
                        ).fetchone()
                    )
                    conn.execute(sql)
                    conn.commit()
                    row = conn.execute(
                        "SELECT * FROM memory_source_links WHERE id=1"
                    ).fetchone()
                    link = models.MemorySourceLink.from_row(row)
                    self.assertEqual(ops.source_link_integrity(link), "mismatch")
                    conn.execute(
                        "UPDATE memory_source_links SET memory_id=?, source_id=?, "
                        "relation=?, created_at=? WHERE id=1",
                        (
                            original["memory_id"], original["source_id"],
                            original["relation"], original["created_at"],
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

    def test_link_verifies_both_hashes_before_writing(self):
        """(30) No laundering, from either end."""
        hid = self.add_memory()
        self.add_source(locator="https://a.test")
        self.write("UPDATE memory SET value_md = 'rewritten' WHERE id=1")
        _, err = self.fails(
            "memory", "source", "link", hid, "MS-0001", "--relation", "supports"
        )
        self.assertIn("Refusing to change memory", err)

        self.setUp()
        hid = self.add_memory()
        self.add_source(locator="https://a.test")
        self.write("UPDATE memory_sources SET locator = 'https://evil.test' WHERE id=1")
        _, err = self.fails(
            "memory", "source", "link", hid, "MS-0001", "--relation", "supports"
        )
        self.assertIn("Refusing to use memory source MS-0001", err)
        self.assertEqual(
            self.query("SELECT COUNT(*) AS n FROM memory_source_links")[0]["n"], 0
        )

    def test_an_expired_source_may_be_linked_historically(self):
        """(27) Expired is inactive, not forbidden."""
        hid = self.add_memory()
        self.add_source("--valid-until", "2020-01-01", locator="https://old.test")
        self.ok("memory", "source", "link", hid, "MS-0001", "--relation", "supports")
        payload = self.events("memory_source_link")[0]["payload"]
        self.assertFalse(payload["active_source"])

    def test_deleting_a_linked_claim_is_refused(self):
        """(M3.4) No delete path is introduced; the FK is NO ACTION."""
        hid = self.add_memory()
        self.add_source(locator="https://a.test")
        self.ok("memory", "source", "link", hid, "MS-0001", "--relation", "supports")
        conn = db.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM memory_sources WHERE id=1")
                conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# (31)-(37) Edges

class EdgeTest(V3WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.a = self.add_memory(key="a")
        self.b = self.add_memory(key="b")

    def test_self_edges_refuse(self):
        """(31)"""
        _, err = self.fails(
            "memory", "edge", "add", self.a, self.a, "--relation", "related"
        )
        self.assertIn("self-edge", err)
        self.assertEqual(self.query("SELECT COUNT(*) AS n FROM memory_edges")[0]["n"], 0)

    def test_self_edges_refuse_at_the_database_too(self):
        """(31)"""
        conn = db.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO memory_edges (from_memory_id, to_memory_id, "
                    "relation, created_at, content_sha256) "
                    "VALUES (1, 1, 'related', 'x', 'y')"
                )
                conn.commit()
        finally:
            conn.close()

    def test_cross_project_edges_refuse(self):
        """(32)"""
        other = self.ok(
            "memory", "add", "--scope", "project", "--project", "other",
            "--kind", "fact", "--key", "o", "--value", "v", "--source", "human",
            "--confidence", "confirmed",
        ).strip()
        _, err = self.fails(
            "memory", "edge", "add", self.a, other, "--relation", "related"
        )
        self.assertIn("different projects", err)
        self.assertEqual(self.query("SELECT COUNT(*) AS n FROM memory_edges")[0]["n"], 0)

    def test_global_to_project_edges_are_permitted(self):
        """(32)"""
        g = self.add_memory(scope="global", key="g")
        self.add_edge(g, self.a, "related")
        self.add_edge(self.b, g, "supports")
        self.assertEqual(len(self.edges()), 2)

    def test_symmetric_edges_canonicalize_endpoints(self):
        """(33)"""
        self.assertEqual(models.MEMORY_EDGE_SYMMETRIC, ("contradicts", "related"))
        self.add_edge(self.b, self.a, "contradicts")  # 2 → 1, stored 1 → 2
        row = self.query("SELECT * FROM memory_edges WHERE id=1")[0]
        self.assertEqual((row["from_memory_id"], row["to_memory_id"]), (1, 2))
        payload = self.events("memory_edge")[0]["payload"]
        self.assertTrue(payload["canonicalized"])

    def test_reverse_duplicate_symmetric_edges_are_idempotent(self):
        """(34)"""
        self.add_edge(self.a, self.b, "contradicts")
        before = len(self.events("memory_edge"))
        out = self.add_edge(self.b, self.a, "contradicts")
        self.assertIn("already records", out)
        self.assertIn("nothing changed", out)
        self.assertEqual(self.query("SELECT COUNT(*) AS n FROM memory_edges")[0]["n"], 1)
        self.assertEqual(len(self.events("memory_edge")), before)

    def test_non_canonical_symmetric_edges_refuse_at_the_database(self):
        """(33)"""
        conn = db.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO memory_edges (from_memory_id, to_memory_id, "
                    "relation, created_at, content_sha256) "
                    "VALUES (2, 1, 'contradicts', 'x', 'y')"
                )
                conn.commit()
        finally:
            conn.close()

    def test_directional_edges_preserve_direction(self):
        """(35)"""
        for relation in ("supports", "refines", "depends_on"):
            with self.subTest(relation=relation):
                self.setUp()
                self.add_edge(self.b, self.a, relation)
                row = self.query("SELECT * FROM memory_edges WHERE id=1")[0]
                self.assertEqual((row["from_memory_id"], row["to_memory_id"]), (2, 1))

    def test_directional_edges_in_both_directions_are_two_edges(self):
        """(35)"""
        self.add_edge(self.a, self.b, "supports")
        self.add_edge(self.b, self.a, "supports")
        self.assertEqual(self.query("SELECT COUNT(*) AS n FROM memory_edges")[0]["n"], 2)

    def test_edge_temporal_intervals_enforce(self):
        """(36)"""
        _, err = self.fails(
            "memory", "edge", "add", self.a, self.b, "--relation", "related",
            "--valid-from", "2027-01-01", "--valid-until", "2026-01-01",
        )
        self.assertIn("inverted validity window", err)
        _, err = self.fails(
            "memory", "edge", "add", self.a, self.b, "--relation", "related",
            "--valid-from", "nonsense",
        )
        self.assertIn("--valid-from", err)
        self.assertEqual(self.query("SELECT COUNT(*) AS n FROM memory_edges")[0]["n"], 0)

    def test_expired_edges_are_inactive_but_present(self):
        """(36)"""
        self.add_edge(self.a, self.b, "related", "--valid-until", "2020-01-01")
        self.add_edge(self.a, self.b, "supports")
        docs = self.edges()
        self.assertEqual([d["active"] for d in docs], [False, True])
        self.assertEqual([d["id"] for d in self.edges("--active-only")], ["ME-0002"])

    def test_a_future_edge_is_not_yet_active(self):
        """(36) valid_from is a real bound, not decoration."""
        self.add_edge(self.a, self.b, "related", "--valid-from", "2099-01-01")
        self.assertFalse(self.edges()[0]["active"])

    def test_edge_hashes_detect_endpoint_relation_and_time_tampering(self):
        """(37)"""
        self.add_memory(key="c")
        self.add_edge(self.a, self.b, "supports")
        for sql in (
            "UPDATE memory_edges SET to_memory_id = 3 WHERE id=1",
            "UPDATE memory_edges SET from_memory_id = 3 WHERE id=1",
            "UPDATE memory_edges SET relation = 'contradicts' WHERE id=1",
            "UPDATE memory_edges SET valid_until = '2000-01-01' WHERE id=1",
            "UPDATE memory_edges SET valid_from = '2000-01-01' WHERE id=1",
            "UPDATE memory_edges SET created_at = '2000-01-01' WHERE id=1",
        ):
            with self.subTest(sql=sql[:45]):
                self.setUp()
                self.add_memory(key="c")
                self.add_edge(self.a, self.b, "supports")
                conn = db.connect(self.db_path)
                try:
                    self.assertEqual(
                        ops.edge_integrity(ops.get_memory_edge(conn, 1)), "ok"
                    )
                finally:
                    conn.close()
                self.write(sql)
                conn = db.connect(self.db_path)
                try:
                    self.assertEqual(
                        ops.edge_integrity(ops.get_memory_edge(conn, 1)), "mismatch"
                    )
                finally:
                    conn.close()

    def test_edge_add_verifies_both_claims_before_writing(self):
        """(37) No laundering."""
        self.write("UPDATE memory SET value_md = 'rewritten' WHERE id=2")
        _, err = self.fails(
            "memory", "edge", "add", self.a, self.b, "--relation", "supports"
        )
        self.assertIn("Refusing to change memory M-0002", err)
        self.assertEqual(self.query("SELECT COUNT(*) AS n FROM memory_edges")[0]["n"], 0)

    def test_edge_add_refuses_an_unknown_claim(self):
        """(37)"""
        _, err = self.fails(
            "memory", "edge", "add", "M-0099", self.a, "--relation", "related"
        )
        self.assertIn("No memory M-0099", err)

    def test_relations_trigger_no_workflow(self):
        """(39) D-v0.3.49 — an edge changes nothing about either claim."""
        before = [self.show(self.a), self.show(self.b)]
        self.add_edge(self.a, self.b, "contradicts")
        self.assertEqual([self.show(self.a), self.show(self.b)], before)

    def test_supersession_is_not_a_graph_relation(self):
        """(D-v0.3.37)"""
        self.assertNotIn("supersedes", models.MEMORY_EDGE_RELATIONS)
        self.assertNotIn("superseded_by", models.MEMORY_EDGE_RELATIONS)
        self.assertEqual(
            models.MEMORY_EDGE_RELATIONS,
            ("supports", "contradicts", "refines", "depends_on", "related"),
        )

    def test_edge_list_filters_are_bounded_and_deterministic(self):
        """(35)"""
        g = self.add_memory(scope="global", key="g")
        self.add_edge(self.a, self.b, "contradicts")
        self.add_edge(g, self.a, "supports")
        self.assertEqual([d["id"] for d in self.edges()], ["ME-0001", "ME-0002"])
        self.assertEqual(
            [d["id"] for d in self.edges("--relation", "contradicts")], ["ME-0001"]
        )
        self.assertEqual(
            [d["id"] for d in self.edges("--project", "demo")], ["ME-0001", "ME-0002"]
        )
        self.assertEqual(self.edges(), self.edges())


# ---------------------------------------------------------------------------
# (38)(39) Contradictions

class ContradictionTest(V3WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.a = self.add_memory(key="a", value="fridays only")
        self.b = self.add_memory(key="b", value="never on fridays")

    def test_listing_returns_only_active_contradictions_by_default(self):
        """(38)"""
        self.add_edge(self.a, self.b, "contradicts")
        self.add_memory(key="c")
        self.add_edge(self.a, "M-0003", "contradicts", "--valid-until", "2020-01-01")
        self.add_edge(self.b, "M-0003", "related")
        docs = self.contradictions()
        self.assertEqual([d["id"] for d in docs], ["ME-0001"])
        self.assertEqual([d["id"] for d in self.contradictions("--all")],
                         ["ME-0001", "ME-0002"])

    def test_listing_shows_both_claims_metadata_only(self):
        """(39)(42)"""
        self.add_edge(self.a, self.b, "contradicts")
        code, out, err = self.aos("memory", "contradictions")
        self.assertEqual(code, 0, err)
        self.assertIn("M-0001", out)
        self.assertIn("M-0002", out)
        self.assertNotIn("fridays only", out)
        self.assertNotIn("never on fridays", out)
        doc = self.contradictions()[0]
        for claim in doc["claims"]:
            self.assertNotIn("key", claim)
            self.assertNotIn("value_md", claim)
            self.assertIn("status", claim)
            self.assertIn("sensitivity", claim)

    def test_listing_never_judges_truth_or_mutates_anything(self):
        """(39)"""
        self.add_edge(self.a, self.b, "contradicts")
        before = [self.show(self.a), self.show(self.b)]
        before_events = len(self.query("SELECT id FROM events"))
        doc = self.contradictions()[0]
        self.assertNotIn("winner", doc)
        self.assertNotIn("resolved", doc)
        self.assertNotIn("verdict", doc)
        self.assertNotIn("true", doc)
        self.assertEqual([self.show(self.a), self.show(self.b)], before)
        self.assertEqual(len(self.query("SELECT id FROM events")), before_events)

    def test_contradictions_are_not_inferred(self):
        """(39) D-v0.3.39 — two claims that plainly disagree produce nothing
        until a human says so."""
        self.add_memory(key="deploy", value="deploy on fridays")
        self.add_memory(key="deploy", value="never deploy on fridays")
        self.assertEqual(self.contradictions(), [])
        self.assertEqual(self.edges(), [])

    def test_project_filter(self):
        """(38)"""
        self.add_edge(self.a, self.b, "contradicts")
        self.assertEqual(len(self.contradictions("--project", "demo")), 1)
        self.assertEqual(len(self.contradictions("--project", "other")), 0)

    def test_there_is_no_second_contradiction_table(self):
        """(D-v0.3.38)"""
        names = {
            row[0]
            for row in self.query("SELECT name FROM sqlite_master WHERE type='table'")
        }
        self.assertNotIn("memory_contradictions", names)
        self.assertNotIn("contradictions", names)


# ---------------------------------------------------------------------------
# (40)(41)(42) Graph traversal

class GraphTraversalTest(V3WorkspaceTestCase):
    def test_traversal_is_deterministic_and_depth_bounded(self):
        """(40)"""
        a = self.add_memory(key="a")
        b = self.add_memory(key="b")
        c = self.add_memory(key="c")
        self.add_edge(a, b, "supports")
        self.add_edge(b, c, "supports")
        depth1 = self.graph(a)
        self.assertEqual([n["id"] for n in depth1["nodes"]], ["M-0001", "M-0002"])
        self.assertEqual([e["id"] for e in depth1["edges"]], ["ME-0001"])
        depth2 = self.graph(a, "--depth", "2")
        self.assertEqual(
            [n["id"] for n in depth2["nodes"]], ["M-0001", "M-0002", "M-0003"]
        )
        self.assertEqual([e["id"] for e in depth2["edges"]], ["ME-0001", "ME-0002"])
        self.assertEqual(self.graph(a, "--depth", "2"), depth2)

    def test_depth_accepts_only_one_or_two(self):
        """(40)"""
        self.add_memory(key="a")
        self.assertEqual(ops.MAX_GRAPH_DEPTH, 2)
        for bad in ("0", "3", "-1"):
            with self.subTest(bad=bad):
                _, err = self.fails("memory", "graph", "M-0001", "--depth", bad)
                self.assertIn("invalid choice", err.lower())
        self.assertEqual(self.graph("M-0001")["depth"], 1)

    def test_traversal_reports_direction_and_state(self):
        """(40)"""
        a = self.add_memory(key="a")
        b = self.add_memory(key="b", value="v")
        self.ok("memory", "classify", b, "confidential")
        self.add_edge(b, a, "supports")
        doc = self.graph(a)
        edge = doc["edges"][0]
        self.assertEqual(edge["direction"], "in")
        self.assertEqual(edge["from"], "M-0002")
        self.assertEqual(edge["to"], "M-0001")
        self.assertTrue(edge["active"])
        neighbour = [n for n in doc["nodes"] if n["id"] == "M-0002"][0]
        self.assertEqual(neighbour["sensitivity"], "confidential")
        self.assertEqual(neighbour["status"], "live")
        self.assertEqual(neighbour["depth"], 1)

    def test_traversal_enforces_the_hard_node_cap(self):
        """(41)"""
        self.assertEqual(ops.MAX_GRAPH_NODES, 64)
        hub = self.add_memory(key="hub")
        for i in range(ops.MAX_GRAPH_NODES + 5):
            other = self.add_memory(key=f"n{i}")
            self.add_edge(hub, other, "supports")
        doc = self.graph(hub)
        self.assertTrue(doc["truncated"])
        self.assertEqual(len(doc["nodes"]), ops.MAX_GRAPH_NODES)
        self.assertEqual(doc["limits"]["nodes"], ops.MAX_GRAPH_NODES)
        # Every edge reported points at a node that IS in the document.
        ids = {n["id"] for n in doc["nodes"]}
        for edge in doc["edges"]:
            self.assertIn(edge["from"], ids)
            self.assertIn(edge["to"], ids)

    def test_traversal_enforces_the_hard_edge_cap(self):
        """(41) Many relations between few claims: edges outrun nodes."""
        self.assertEqual(ops.MAX_GRAPH_EDGES, 128)
        hub = self.add_memory(key="hub")
        # 4 directional relations per neighbour pair, both directions.
        for i in range(40):
            other = self.add_memory(key=f"n{i}")
            for relation in ("supports", "refines", "depends_on"):
                self.add_edge(hub, other, relation)
                self.add_edge(other, hub, relation)
        doc = self.graph(hub)
        self.assertTrue(doc["truncated"])
        self.assertLessEqual(len(doc["edges"]), ops.MAX_GRAPH_EDGES)
        self.assertEqual(doc["limits"]["edges"], ops.MAX_GRAPH_EDGES)

    def test_a_small_graph_is_not_truncated(self):
        """(41) The caps must not fire on ordinary use."""
        a = self.add_memory(key="a")
        b = self.add_memory(key="b")
        self.add_edge(a, b, "related")
        self.assertFalse(self.graph(a, "--depth", "2")["truncated"])

    def test_truncation_is_announced_in_text_output(self):
        """(41) D-v0.3.42 — bounded AND honest about it."""
        hub = self.add_memory(key="hub")
        for i in range(ops.MAX_GRAPH_NODES + 2):
            other = self.add_memory(key=f"n{i}")
            self.add_edge(hub, other, "supports")
        out = self.ok("memory", "graph", hub)
        self.assertIn("truncated", out)
        self.assertIn("bounded view", out)

    def test_graph_output_never_exposes_claim_or_source_text(self):
        """(42)"""
        a = self.add_memory(key=f"key {FAKE_SECRET}", value=f"body {FAKE_SECRET}")
        b = self.add_memory(key="b", value="neighbour body")
        self.add_edge(a, b, "contradicts")
        self.add_source(locator=f"https://x.test/{FAKE_SECRET}")
        self.ok("memory", "source", "link", a, "MS-0001", "--relation", "supports")
        for argv in (
            ("memory", "graph", a),
            ("memory", "graph", a, "--json"),
            ("memory", "graph", a, "--depth", "2"),
        ):
            with self.subTest(argv=argv):
                out = self.ok(*argv)
                self.assertNotIn(FAKE_SECRET, out)
                self.assertNotIn("neighbour body", out)
                self.assertNotIn("x.test", out)
        doc = self.graph(a)
        for node in doc["nodes"]:
            self.assertNotIn("key", node)
            self.assertNotIn("value_md", node)
            self.assertNotIn("source", node)

    def test_graph_never_prints_a_full_hash(self):
        """(42)"""
        a = self.add_memory(key="a")
        b = self.add_memory(key="b")
        self.add_edge(a, b, "related")
        full = self.query("SELECT content_sha256 FROM memory_edges WHERE id=1")[0][0]
        out = self.ok("memory", "graph", a, "--json")
        self.assertNotIn(full, out)
        self.assertIn(full[:12], self.edges()[0]["hash_prefix"])

    def test_graph_refuses_an_unknown_starting_memory(self):
        """(40)"""
        _, err = self.fails("memory", "graph", "M-0099")
        self.assertIn("No memory M-0099", err)

    def test_graph_modifies_nothing(self):
        """(40)"""
        a = self.add_memory(key="a")
        b = self.add_memory(key="b")
        self.add_edge(a, b, "related")
        before = self.db_path.read_bytes()
        self.graph(a, "--depth", "2")
        self.assertEqual(self.db_path.read_bytes(), before)

    def test_graph_shows_a_missing_endpoint_rather_than_hiding_it(self):
        """(40) An edge pointing at nothing is a fact about the graph."""
        a = self.add_memory(key="a")
        b = self.add_memory(key="b")
        self.add_edge(a, b, "related")
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("DELETE FROM memory WHERE id=2")
            conn.commit()
        finally:
            conn.close()
        doc = self.graph(a)
        missing = [n for n in doc["nodes"] if n["id"] == "M-0002"][0]
        self.assertTrue(missing["missing"])


# ---------------------------------------------------------------------------
# (43)-(46) Packs, search and the mirror

class RestrictedSurfaceTest(V3WorkspaceTestCase):
    def test_restricted_claims_never_enter_context_packs(self):
        """(43)"""
        self.add_memory(key="ok-key", value="ordinary body")
        self.add_memory(
            "--sensitivity", "restricted", key="secret-key", value="secret body"
        )
        section = self.pack_memory_section()
        self.assertIn("ordinary body", section)
        self.assertNotIn("secret body", section)
        self.assertNotIn("secret-key", section)

    def test_restricted_claim_does_not_shadow_a_live_claim_sharing_its_key(self):
        """(43) Excluded BEFORE the per-key dedupe: a restricted claim must
        not be able to blank out context by being excluded from it."""
        self.add_memory(key="storage", value="ordinary body")
        self.add_memory(
            "--sensitivity", "restricted", key="storage", value="secret body"
        )
        section = self.pack_memory_section()
        self.assertIn("ordinary body", section)
        self.assertNotIn("secret body", section)

    def test_public_internal_confidential_still_reach_packs(self):
        """(46)"""
        for level in ("public", "internal", "confidential"):
            with self.subTest(level=level):
                self.setUp()
                self.add_memory("--sensitivity", level, key="k", value=f"{level} body")
                self.assertIn(f"{level} body", self.pack_memory_section())

    def test_restricted_search_snippets_are_suppressed(self):
        """(44)"""
        self.add_memory(
            "--sensitivity", "restricted", key="salaryband", value="everyone earns"
        )
        doc = json.loads(self.ok("search", "everyone", "--json"))
        hits = [r for r in doc["results"] if r["type"] == "memory"]
        self.assertEqual(len(hits), 1, "must still MATCH administratively")
        self.assertEqual(hits[0]["id"], "M-0001")
        self.assertEqual(hits[0]["snippet"], "(restricted)")
        self.assertEqual(hits[0]["title"], "(restricted)")
        self.assertNotIn("everyone earns", self.ok("search", "everyone"))
        self.assertNotIn("salaryband", self.ok("search", "everyone"))

    def test_search_suppression_survives_a_later_classify(self):
        """(44) The FTS index is derived; suppression reads the ledger."""
        hid = self.add_memory(key="salaryband", value="everyone earns")
        self.assertIn("everyone earns", self.ok("search", "everyone"))
        self.ok("memory", "classify", hid, "restricted")
        out = self.ok("search", "everyone")
        self.assertNotIn("everyone earns", out)
        self.assertIn("(restricted)", out)

    def test_non_restricted_search_results_are_unchanged(self):
        """(46)"""
        self.add_memory(key="storage", value="sqlite only")
        doc = json.loads(self.ok("search", "sqlite", "--json"))
        hit = [r for r in doc["results"] if r["type"] == "memory"][0]
        self.assertIn("storage", hit["title"])
        self.assertIn("sqlite", hit["snippet"])

    def test_restricted_mirror_output_contains_metadata_only(self):
        """(45)"""
        self.add_memory(
            "--sensitivity", "restricted", key="salaryband", value="everyone earns"
        )
        self.ok("sync")
        note = (
            self.aos_dir / "obsidian-vault" / "AOS" / "Memory" / "M-0001.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn("everyone earns", note)
        self.assertNotIn("salaryband", note)
        self.assertIn("M-0001", note)
        self.assertIn("sensitivity: restricted", note)
        self.assertIn("aos/restricted", note)

    def test_restricted_claim_is_absent_from_the_mirror_index(self):
        """(45)"""
        self.add_memory(
            "--sensitivity", "restricted", key="salaryband", value="everyone earns"
        )
        self.ok("sync")
        index = (
            self.aos_dir / "obsidian-vault" / "AOS" / "Memory.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn("salaryband", index)
        self.assertIn("[[M-0001]]", index)
        self.assertIn("(restricted)", index)

    def test_non_restricted_mirror_notes_keep_their_body(self):
        """(46)"""
        self.add_memory(key="storage", value="sqlite only")
        self.ok("sync")
        note = (
            self.aos_dir / "obsidian-vault" / "AOS" / "Memory" / "M-0001.md"
        ).read_text(encoding="utf-8")
        self.assertIn("sqlite only", note)
        self.assertIn("storage", note)
        self.assertIn("sensitivity: internal", note)

    def test_restricted_listing_shows_metadata_and_suppresses_text(self):
        """(43) Listed, never hidden."""
        self.add_memory(
            "--sensitivity", "restricted", key="salaryband",
            value="everyone earns", scope="global",
        )
        item = self.listing()[0]
        self.assertEqual(item["id"], "M-0001")
        self.assertEqual(item["sensitivity"], "restricted")
        self.assertEqual(item["key"], "(restricted)")
        self.assertEqual(item["value_md"], "(restricted)")
        self.assertEqual(item["source"], "(restricted)")
        self.assertEqual(item["evidence"], [])
        self.assertFalse(item["live"])
        out = self.ok("memory", "list")
        self.assertIn("live·restricted", out)
        self.assertNotIn("salaryband", out)

    def test_restricted_claim_hides_its_evidence_refs_but_keeps_the_count(self):
        """(43)"""
        hid = self.add_memory("--evidence", "E-0001")
        self.assertEqual(self.show(hid)["evidence"], ["E-0001"])
        self.ok("memory", "classify", hid, "restricted")
        doc = self.show(hid)
        self.assertEqual(doc["evidence"], [])
        self.assertEqual(doc["evidence_count"], 1)

    def test_restricted_add_event_carries_no_key(self):
        """(43)"""
        self.add_memory(
            "--sensitivity", "restricted", key="salaryband", value="everyone earns"
        )
        blob = self.all_event_text()
        self.assertNotIn("salaryband", blob)
        self.assertNotIn("everyone earns", blob)
        payload = self.events("memory")[0]["payload"]
        self.assertEqual(payload["key"], "(restricted)")
        self.assertEqual(payload["sensitivity"], "restricted")

    def test_restricted_claims_are_suppressed_in_generated_reviews(self):
        """(45) A review note is a generated context summary that lands in the
        vault — a restricted claim's key must not reach one."""
        self.add_memory(
            "--sensitivity", "restricted", key="salaryband",
            value="everyone earns", scope="global",
        )
        self.add_memory(key="ordinary", value="ordinary body", scope="global")
        for argv in (
            ("review", "build"),
            ("review", "weekly"),
            ("review", "project", "demo"),
        ):
            with self.subTest(argv=argv):
                self.ok(*argv)
        reviews = self.aos_dir / "obsidian-vault" / "AOS" / "Reviews"
        texts = [p.read_text(encoding="utf-8") for p in reviews.glob("*.md")]
        self.assertTrue(texts, "no review note was generated")
        for text in texts:
            self.assertNotIn("salaryband", text)
            self.assertNotIn("everyone earns", text)

    def test_reviews_still_name_a_restricted_claim_by_id(self):
        """(45) Suppressed, not hidden: a restricted claim that has gone stale
        is exactly what the operator needs told."""
        self.add_memory(
            "--sensitivity", "restricted", key="salaryband",
            value="everyone earns", scope="global",
        )
        self.write("UPDATE memory SET updated_at = '2020-01-01T00:00:00Z' WHERE id=1")
        self.ok("review", "build")
        text = "\n".join(
            p.read_text(encoding="utf-8")
            for p in (self.aos_dir / "obsidian-vault" / "AOS" / "Reviews").glob("*.md")
        )
        self.assertIn("M-0001", text)
        self.assertIn("(restricted)", text)
        self.assertNotIn("salaryband", text)

    def test_packs_do_no_graph_expansion(self):
        """(43) A neighbour is not context."""
        a = self.add_memory(key="a", value="in the pack")
        b = self.add_memory(key="b", value="neighbour body", scope="global")
        self.ok("memory", "classify", b, "restricted")
        self.add_edge(a, b, "related")
        section = self.pack_memory_section()
        self.assertIn("in the pack", section)
        self.assertNotIn("neighbour body", section)
        self.assertNotIn("ME-0001", section)


# ---------------------------------------------------------------------------
# (47)(48)(50) Doctor and the inert-reference boundary

class DoctorTest(V3WorkspaceTestCase):
    def test_doctor_passes_on_a_healthy_v3_graph(self):
        """(47)"""
        a = self.add_memory(key="a")
        b = self.add_memory(key="b")
        self.add_source(locator="https://a.test")
        self.ok("memory", "source", "link", a, "MS-0001", "--relation", "supports")
        self.add_edge(a, b, "contradicts")
        out = self.doctor_lines()
        self.assertEqual(out.count("[FAIL]"), 0, out)
        for name in (
            "memory sensitivity values are known",
            "memory sources are well-formed",
            "memory source links resolve",
            "memory edges are well-formed",
            "restricted claims absent from generated context",
        ):
            self.assertIn(name, out)

    def test_doctor_check_count_is_thirty_one(self):
        """(47) 25 → 30 → 31: five mandated memory-graph checks joined the
        set, then U-M5's one retrieval-benchmark registry check."""
        out = self.doctor_lines()
        self.assertEqual(len([l for l in out.strip().splitlines() if l]), 31)

    def test_doctor_reports_damaged_records_by_safe_ids_only(self):
        """(47)"""
        a = self.add_memory(key=f"key {FAKE_SECRET}", value=f"body {FAKE_SECRET}")
        b = self.add_memory(key="b")
        self.add_source(locator=f"https://x.test/{FAKE_SECRET}")
        self.ok("memory", "source", "link", a, "MS-0001", "--relation", "supports")
        self.add_edge(a, b, "supports")
        self.write("UPDATE memory_sources SET locator = 'https://evil.test' WHERE id=1")
        self.write("UPDATE memory_edges SET relation = 'related' WHERE id=1")
        self.write("UPDATE memory_source_links SET relation = 'context' WHERE id=1")
        code, out, err = self.aos("doctor")
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] memory sources are well-formed", out)
        self.assertIn("MS-0001: content hash does not match the record", out)
        self.assertIn("[FAIL] memory edges are well-formed", out)
        self.assertIn("ME-0001", out)
        self.assertIn("[FAIL] memory source links resolve", out)
        self.assertIn("ML-0001", out)
        self.assertNotIn(FAKE_SECRET, out + err)
        self.assertNotIn("evil.test", out)

    def test_doctor_detects_an_unknown_sensitivity(self):
        """(47)"""
        self.add_memory()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(
                "PRAGMA writable_schema=ON;"
                "UPDATE sqlite_master SET sql = replace(sql, "
                "\"CHECK (sensitivity IN ('public','internal','confidential',"
                "'restricted'))\", 'CHECK (1)') WHERE name = 'memory';"
                "PRAGMA writable_schema=OFF;"
            )
            conn.close()
            conn = sqlite3.connect(self.db_path)
            conn.execute("UPDATE memory SET sensitivity = 'invented' WHERE id=1")
            conn.commit()
        finally:
            conn.close()
        code, out, _ = self.aos("doctor")
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] memory sensitivity values are known", out)
        self.assertIn("M-0001: unknown sensitivity", out)
        self.assertNotIn("invented", out)

    def test_doctor_detects_cross_project_and_sensitivity_violations(self):
        """(47) Reachable only by bypassing ops — which is why it is checked."""
        self.add_memory()  # demo, internal
        self.ok(
            "memory", "source", "add", "--kind", "url", "--locator", "https://o.test",
            "--project", "other", "--sensitivity", "restricted",
        )
        self.write(
            "INSERT INTO memory_source_links (memory_id, source_id, relation, "
            "created_at, content_sha256) VALUES (1, 1, 'supports', '2026-01-01', "
            "'" + "0" * 64 + "')"
        )
        code, out, _ = self.aos("doctor")
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] memory source links resolve", out)
        self.assertIn("project source linked outside its project", out)
        self.assertIn("source is more sensitive than its claim", out)

    def test_doctor_detects_a_missing_source_target(self):
        """(47)"""
        self.add_memory()
        self.add_source(locator="https://a.test")
        self.ok("memory", "source", "link", "M-0001", "MS-0001", "--relation", "supports")
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("DELETE FROM memory_sources WHERE id=1")
            conn.commit()
        finally:
            conn.close()
        code, out, _ = self.aos("doctor")
        self.assertEqual(code, 1)
        self.assertIn("missing source MS-0001", out)

    def _seed_graph(self) -> None:
        self.add_memory()
        self.add_source(locator="https://a.test")
        self.add_memory(key="b")
        self.add_edge("M-0001", "M-0002", "supports")
        self.ok(
            "memory", "source", "link", "M-0001", "MS-0001", "--relation", "supports"
        )

    def test_doctor_blob_and_malformed_rows_never_crash(self):
        """(48) Every plant has exactly one of two acceptable outcomes: a
        constraint refuses it, or doctor REPORTS it without crashing.

        Both are proofs, so neither is skipped. A plant that a CHECK refuses
        has demonstrated the storage boundary holding; one that lands has to
        be survivable by the diagnostic that exists to report it — a check
        that crashes on a damaged row is not a check.
        """
        refused, reported = 0, 0
        for sql, params in (
            ("UPDATE memory_sources SET locator = ? WHERE id=1", (b"\x00\xff\xfe",)),
            ("UPDATE memory_sources SET provenance = ? WHERE id=1", (b"\x00",)),
            ("UPDATE memory_sources SET observed_at = ? WHERE id=1", (12345,)),
            ("UPDATE memory_sources SET valid_until = ? WHERE id=1", (b"\xfe",)),
            ("UPDATE memory_edges SET relation = ? WHERE id=1", (b"\x00",)),
            ("UPDATE memory_edges SET created_at = ? WHERE id=1", (None,)),
            ("UPDATE memory_edges SET valid_from = ? WHERE id=1", (3.5,)),
            ("UPDATE memory_source_links SET relation = ? WHERE id=1", (b"\xff",)),
            ("UPDATE memory_source_links SET created_at = ? WHERE id=1", (b"\x01",)),
            ("UPDATE memory SET sensitivity = ? WHERE id=1", (b"\xff",)),
            ("UPDATE memory_sources SET content_sha256 = ? WHERE id=1", (b"\x00",)),
        ):
            with self.subTest(sql=sql[:48]):
                self.setUp()
                self._seed_graph()
                conn = sqlite3.connect(self.db_path)
                landed = True
                try:
                    conn.execute(sql, params)
                    conn.commit()
                except sqlite3.IntegrityError:
                    landed = False  # the storage boundary held: a real proof
                finally:
                    conn.close()
                if not landed:
                    refused += 1
                    continue
                reported += 1
                code, out, err = self.aos("doctor")
                self.assertIn(code, (0, 1), err)
                self.assertNotIn("Traceback", out + err)
                # And the damaged value never reaches the report.
                self.assertNotIn("\\x00", out)
                self.assertNotIn("bytearray", out)
        # Both halves must actually have happened, or this proves one thing
        # and silently stopped proving the other.
        self.assertGreater(refused, 0, "no plant was refused by a constraint")
        self.assertGreater(reported, 0, "no plant survived for doctor to report")

    def test_doctor_warns_when_a_stale_pack_holds_restricted_text(self):
        """(47) D-v0.3.46 — WARN, never FAIL: the pack predates the
        classification and nothing was violated at the time."""
        hid = self.add_memory(key="salaryband", value="everyone earns")
        self.pack_memory_section()  # builds a pack containing the claim
        self.ok("memory", "classify", hid, "restricted")
        code, out, _ = self.aos("doctor")
        self.assertEqual(code, 0, "a stale pack must not fail the run")
        line = [
            l for l in out.splitlines()
            if "restricted claims absent from generated context" in l
        ][0]
        self.assertTrue(line.startswith("[WARN]"), line)
        self.assertIn("M-0001", line)
        self.assertNotIn("everyone earns", line)
        # And regenerating fixes it.
        self.ok("pack", "build", "T-0001", "--for", "claude-code")
        self.ok("sync")
        code, out, _ = self.aos("doctor")
        self.assertEqual(out.count("[WARN] restricted claims"), 0, out)


class InertReferenceTest(V3WorkspaceTestCase):
    """(50) Referenced files, URLs and commands are never followed."""

    def test_no_graph_command_opens_a_referenced_file(self):
        marker = self.trap.read_text()
        self.ok("memory", "source", "add", "--kind", "file",
                "--locator", str(self.trap))
        hid = self.add_memory()
        self.ok("memory", "source", "link", hid, "MS-0001", "--relation", "supports")
        for argv in (
            ("memory", "source", "list"),
            ("memory", "source", "show", "MS-0001"),
            ("memory", "source", "show", "MS-0001", "--json"),
            ("memory", "graph", hid, "--depth", "2"),
            ("memory", "contradictions"),
            ("memory", "edge", "list"),
            ("doctor",),
            ("sync",),
        ):
            with self.subTest(argv=argv):
                code, out, err = self.aos(*argv)
                self.assertIn(code, (0, 1), err)
                self.assertNotIn(marker.strip(), out + err)
                self.assertNotIn(BOOBY_TRAP_NAME, out)

    def test_a_source_locator_is_not_resolved_or_required_to_exist(self):
        """A path that does not exist is a perfectly good locator: nothing
        stats it, so nothing can refuse it."""
        self.ok(
            "memory", "source", "add", "--kind", "file",
            "--locator", "/nowhere/at/all/really.txt",
        )
        self.ok(
            "memory", "source", "add", "--kind", "command",
            "--locator", "rm -rf / --no-preserve-root",
        )
        self.assertEqual(len(self.sources()), 2)

    def test_no_graph_command_touches_the_network(self):
        """Not 'no URL was fetched by accident' — no socket may be opened at
        all, whatever the implementation does."""
        import socket

        self.ok(
            "memory", "source", "add", "--kind", "url",
            "--locator", "https://example.test/should-never-be-fetched",
        )
        hid = self.add_memory()
        self.ok("memory", "source", "link", hid, "MS-0001", "--relation", "supports")

        def explode(*args, **kwargs):
            raise AssertionError("a U-M3 command opened a socket")

        with mock.patch.object(socket, "socket", explode), \
                mock.patch.object(socket, "create_connection", explode):
            from agentic_os import cli

            for argv in (
                ["memory", "source", "list"],
                ["memory", "source", "show", "MS-0001"],
                ["memory", "graph", hid],
                ["memory", "contradictions"],
            ):
                with self.subTest(argv=argv):
                    code = cli.main(["--root", str(self.root), *argv])
                    self.assertEqual(code, 0)

    def test_no_graph_command_executes_a_command_locator(self):
        import subprocess as sp

        sentinel = self.root / "executed"
        self.ok(
            "memory", "source", "add", "--kind", "command",
            "--locator", f"touch {sentinel}",
        )
        hid = self.add_memory()
        self.ok("memory", "source", "link", hid, "MS-0001", "--relation", "supports")

        def explode(*args, **kwargs):
            raise AssertionError("a U-M3 command spawned a subprocess")

        with mock.patch.object(sp, "run", explode), \
                mock.patch.object(sp, "Popen", explode):
            from agentic_os import cli

            for argv in (
                ["memory", "source", "list"],
                ["memory", "source", "show", "MS-0001"],
                ["memory", "graph", hid],
            ):
                with self.subTest(argv=argv):
                    self.assertEqual(
                        cli.main(["--root", str(self.root), *argv]), 0
                    )
        self.assertFalse(sentinel.exists())

    def test_no_command_rewrites_a_referenced_file(self):
        before = self.trap.read_bytes()
        stat_before = self.trap.stat().st_mtime_ns
        self.ok("memory", "source", "add", "--kind", "file",
                "--locator", str(self.trap))
        self.ok("memory", "source", "list")
        self.ok("doctor")
        self.assertEqual(self.trap.read_bytes(), before)
        self.assertEqual(self.trap.stat().st_mtime_ns, stat_before)
        # And no adjacent derived object was created next to it.
        siblings = {p.name for p in self.root.iterdir()}
        self.assertEqual(
            {n for n in siblings if n.startswith(BOOBY_TRAP_NAME) and n != BOOBY_TRAP_NAME},
            set(),
        )


# ---------------------------------------------------------------------------
# (51)(52)(53) Command classification and power modes

class ClassificationTest(unittest.TestCase):
    def test_every_new_leaf_is_classified_exactly_once(self):
        """(51) Walks the REAL parser, so a forgotten leaf fails here."""
        from agentic_os import cli

        parser = cli.build_parser()
        for path in power.iter_command_paths(parser):
            with self.subTest(path=path):
                self.assertIn(path, power.COMMAND_POLICY)
                self.assertIn(power.COMMAND_POLICY[path].kind, power.KINDS)

    def test_no_stale_policy_entry_survives(self):
        """(51) The reverse direction: every classified path is a real leaf."""
        from agentic_os import cli

        paths = set(power.iter_command_paths(cli.build_parser()))
        self.assertEqual(set(power.COMMAND_POLICY) - paths, set())

    def test_the_new_leaves_have_the_contracted_kinds(self):
        """(51) M3.9, verbatim."""
        expected = {
            ("memory", "source", "list"): power.READ_ONLY,
            ("memory", "source", "show"): power.READ_ONLY,
            ("memory", "edge", "list"): power.READ_ONLY,
            ("memory", "graph"): power.READ_ONLY,
            ("memory", "contradictions"): power.READ_ONLY,
            ("memory", "classify"): power.AUTHORITATIVE_WRITE,
            ("memory", "source", "add"): power.AUTHORITATIVE_WRITE,
            ("memory", "source", "link"): power.AUTHORITATIVE_WRITE,
            ("memory", "edge", "add"): power.AUTHORITATIVE_WRITE,
        }
        for path, kind in expected.items():
            with self.subTest(path=path):
                self.assertEqual(power.COMMAND_POLICY[path].kind, kind)
        for path in expected:
            if expected[path] == power.AUTHORITATIVE_WRITE:
                self.assertTrue(power.COMMAND_POLICY[path].ledger, path)

    def test_command_path_resolves_three_levels(self):
        """(51) A two-deep key would collapse every `memory source` leaf into
        one command — including the read-only ones into the writes."""
        from agentic_os import cli

        parser = cli.build_parser()
        args = parser.parse_args(
            ["memory", "source", "list"]
        )
        self.assertEqual(power.command_path(args), ("memory", "source", "list"))
        args = parser.parse_args(["memory", "graph", "M-0001"])
        self.assertEqual(power.command_path(args), ("memory", "graph"))
        args = parser.parse_args(["doctor"])
        self.assertEqual(power.command_path(args), ("doctor",))


class PowerModeTest(V3WorkspaceTestCase):
    def test_recovery_blocks_graph_writes_before_mutation(self):
        """(52)"""
        a = self.add_memory(key="a")
        self.add_memory(key="b")
        self.add_source(locator="https://a.test")
        before = self.db_path.read_bytes()
        self.ok("power", "set", "recovery")
        after_set = self.db_path.read_bytes()
        for argv in (
            ("memory", "classify", a, "confidential"),
            ("memory", "source", "add", "--kind", "url", "--locator", "https://b.test"),
            ("memory", "source", "link", a, "MS-0001", "--relation", "supports"),
            ("memory", "edge", "add", "M-0001", "M-0002", "--relation", "related"),
        ):
            with self.subTest(argv=argv):
                code, _, err = self.aos(*argv)
                self.assertEqual(code, 1)
                self.assertIn("blocked in recovery mode", err)
                self.assertIn("authoritative_write", err)
                self.assertEqual(self.db_path.read_bytes(), after_set)
        self.assertEqual(after_set, before)

    def test_recovery_allows_graph_reads(self):
        """(52)"""
        a = self.add_memory(key="a")
        self.add_memory(key="b")
        self.add_edge("M-0001", "M-0002", "contradicts")
        self.ok("power", "set", "recovery")
        for argv in (
            ("memory", "source", "list"),
            ("memory", "edge", "list"),
            ("memory", "graph", a),
            ("memory", "contradictions"),
        ):
            with self.subTest(argv=argv):
                code, _, err = self.aos(*argv)
                self.assertEqual(code, 0, err)

    def test_deep_preflight_refuses_a_graph_write_on_a_damaged_ledger(self):
        """(53) Deep's preflight is U-E2's — integrity_check plus the U-C3
        secret sweep — so this plants what it actually looks at. (A broken
        claim hash is caught by the per-write verify gate instead, which the
        no-laundering tests above cover; deep does not re-check hashes and is
        not supposed to.)"""
        a = self.add_memory(key="a")
        # A warned trusted write: the value lands in the canonical row and the
        # sweep will find it.
        self.aos(
            "memory", "add", "--scope", "global", "--kind", "fact", "--key", "k",
            "--value", FAKE_SECRET, "--source", "human", "--confidence", "confirmed",
        )
        self.ok("power", "set", "deep")
        before = self.db_path.read_bytes()
        for argv in (
            ("memory", "classify", a, "confidential"),
            ("memory", "source", "add", "--kind", "url", "--locator", "https://a.test"),
            ("memory", "edge", "add", "M-0001", "M-0002", "--relation", "related"),
        ):
            with self.subTest(argv=argv):
                code, out, err = self.aos(*argv)
                self.assertEqual(code, 1)
                self.assertIn("deep mode's preflight", err)
                self.assertIn("Nothing was written", err)
                self.assertNotIn(FAKE_SECRET, out + err)
        self.assertEqual(self.db_path.read_bytes(), before)

    def test_deep_preflight_skips_graph_reads(self):
        """(53) Read-only leaves get no preflight gate of their own."""
        a = self.add_memory(key="a")
        self.aos(
            "memory", "add", "--scope", "global", "--kind", "fact", "--key", "k",
            "--value", FAKE_SECRET, "--source", "human", "--confidence", "confirmed",
        )
        self.ok("power", "set", "deep")
        for argv in (
            ("memory", "graph", a),
            ("memory", "source", "list"),
            ("memory", "edge", "list"),
            ("memory", "contradictions"),
        ):
            with self.subTest(argv=argv):
                code, _, err = self.aos(*argv)
                self.assertEqual(code, 0, err)

    def test_deep_post_verification_reports_a_committed_but_unhealthy_write(self):
        """(53) The honest half: it reports that the write COMMITTED and that
        verification then failed. It never claims a rollback."""
        self.ok("power", "set", "deep")
        a = self.add_memory(key="a")

        real = power.deep_check
        calls = {"n": 0}

        def once_healthy_then_not(aos_dir):
            calls["n"] += 1
            return [] if calls["n"] == 1 else ["ledger secret sweep (1 finding(s))"]

        with mock.patch.object(power, "deep_check", once_healthy_then_not):
            from agentic_os import cli

            code = cli.main(
                ["--root", str(self.root), "memory", "classify", a, "confidential"]
            )
        self.assertEqual(code, 1)
        # The write really did commit — that is what makes the report honest.
        self.assertEqual(
            self.query("SELECT sensitivity FROM memory WHERE id=1")[0][0],
            "confidential",
        )

    def test_deep_mode_allows_a_graph_write_on_a_healthy_ledger(self):
        """(53)"""
        a = self.add_memory(key="a")
        self.ok("power", "set", "deep")
        self.ok("memory", "classify", a, "confidential")
        self.ok("memory", "source", "add", "--kind", "url", "--locator", "https://a.test")
        self.ok("memory", "source", "link", a, "MS-0001", "--relation", "supports")


# ---------------------------------------------------------------------------
# (54) Script / module / zipapp parity

class EntrypointParityTest(V2FixtureTestCase):
    """(54) The three entrypoints must agree, including on a v2 database."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._pyz_tmp = tempfile.mkdtemp(prefix="aos-m3-pyz-")
        cls.pyz = Path(cls._pyz_tmp) / "aos.pyz"
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "build_zipapp.py"),
             "--output", str(cls.pyz)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise AssertionError(f"zipapp build failed: {result.stderr}")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._pyz_tmp, ignore_errors=True)
        super().tearDownClass()

    def _run(self, argv: list[str], *, cwd: Path) -> tuple[int, str, str]:
        env = {
            k: v for k, v in __import__("os").environ.items()
            if k != "PYTHONPATH"
        }
        result = subprocess.run(
            argv, capture_output=True, text=True, cwd=str(cwd), env=env
        )
        return result.returncode, result.stdout, result.stderr

    #: A UTC instant and a bounded hash prefix, as they appear in output.
    _TIMESTAMP_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
    _HASH_RE = re.compile(r"\b[0-9a-f]{12,64}\b")

    @classmethod
    def _normalize_clock(cls, text: str, root: Path) -> str:
        """Blank what the WALL CLOCK and the WORKSPACE PATH decide — nothing
        else.

        Write parity gives each entrypoint its own workspace, seconds apart:
        `created_at` differs by construction, every record hash binds
        `created_at` so the prefixes differ with it, and `doctor` prints the
        absolute path of the database it checked. None of the three is a
        parity failure, and leaving them in would fail this test every run for
        reasons that have nothing to do with the entrypoints.

        What survives normalization is exactly what parity is about: ids,
        relations, sensitivity, statuses, counts, structure and exit codes. If
        an entrypoint got any of those wrong, this still catches it.
        """
        text = text.replace(str(root), "<root>")
        return cls._HASH_RE.sub("<hash>", cls._TIMESTAMP_RE.sub("<ts>", text))

    def _entrypoint(self, name: str) -> tuple[list[str], Path]:
        """How to invoke one entrypoint, and from where. The zipapp runs from
        OUTSIDE the checkout so it cannot lean on the source tree next door."""
        argv = {
            "script": [sys.executable, str(REPO_ROOT / "aos.py")],
            "module": [sys.executable, "-m", "agentic_os"],
            "zipapp": [sys.executable, str(self.pyz)],
        }[name]
        cwd = Path(self._pyz_tmp) if name == "zipapp" else REPO_ROOT
        return argv, cwd

    def _migrated_copy(self, name: str) -> Path:
        """A fresh copy of the v2 fixture, migrated to v3 by `name`'s own
        entrypoint. For write parity, where the three cannot share a
        workspace."""
        target = Path(self._pyz_tmp) / f"m3-write-{name}"
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(self._fixture_root, target, symlinks=True)
        self.addCleanup(shutil.rmtree, target, True)
        argv, cwd = self._entrypoint(name)
        code, _, err = self._run(
            [*argv, "--root", str(target), "migrate", "apply"], cwd=cwd
        )
        self.assertEqual(code, 0, err)
        return target

    def _three_ways(self, args: list[str], root: Path):
        """The same command, three entrypoints."""
        results = []
        for name in ("script", "module", "zipapp"):
            argv, cwd = self._entrypoint(name)
            results.append(self._run([*argv, "--root", str(root), *args], cwd=cwd))
        return results

    def _assert_parity(self, args: list[str], root: Path) -> tuple[int, str, str]:
        script, module, zipapp = self._three_ways(args, root)
        self.assertEqual(script[0], module[0], f"{args}: script/module exit")
        self.assertEqual(script[0], zipapp[0], f"{args}: script/zipapp exit")
        self.assertEqual(script[1], module[1], f"{args}: script/module stdout")
        self.assertEqual(script[1], zipapp[1], f"{args}: script/zipapp stdout")
        return script

    def test_parity_on_a_v2_database_and_through_the_migration(self):
        """(54) migrate status/plan on v2, then apply, then the graph."""
        code, out, _ = self._assert_parity(["migrate", "status"], self.root)
        self.assertEqual(code, 0)
        self.assertIn("schema version:  2", out)

        code, out, _ = self._assert_parity(["migrate", "plan"], self.root)
        self.assertEqual(code, 0)
        self.assertIn("2 → 3  u-m3-memory-graph-v3", out)

        # apply is not idempotent, so each entrypoint gets its own copy.
        applied = []
        for name in ("script", "module", "zipapp"):
            target = Path(self._pyz_tmp) / f"m3-apply-{name}"
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(self._fixture_root, target, symlinks=True)
            self.addCleanup(shutil.rmtree, target, True)
            argv, cwd = self._entrypoint(name)
            code, out, err = self._run(
                [*argv, "--root", str(target), "migrate", "apply"], cwd=cwd
            )
            self.assertEqual(code, 0, err)
            # The snapshot filename carries a timestamp; the rest must match.
            applied.append(
                [l for l in out.splitlines() if not l.startswith("Snapshot:")]
            )
        self.assertEqual(applied[0], applied[1])
        self.assertEqual(applied[0], applied[2])
        self.assertIn("applied 2 → 3  u-m3-memory-graph-v3", "\n".join(applied[0]))

    def test_parity_on_the_read_only_graph_commands(self):
        """(54) Reads are naturally repeatable, so all three run against the
        same workspace and must agree byte for byte."""
        self.migrate()
        self.aos("memory", "classify", "M-0001", "confidential")
        self.aos(
            "memory", "source", "add", "--kind", "url", "--locator", "https://a.test"
        )
        self.aos(
            "memory", "source", "link", "M-0001", "MS-0001", "--relation", "supports"
        )
        self.aos("memory", "edge", "add", "M-0001", "M-0002", "--relation", "contradicts")
        for args in (
            ["memory", "source", "list", "--json"],
            ["memory", "source", "show", "MS-0001", "--json"],
            ["memory", "edge", "list", "--json"],
            ["memory", "graph", "M-0001", "--json"],
            ["memory", "graph", "M-0001", "--depth", "2", "--json"],
            ["memory", "contradictions", "--json"],
            ["memory", "list", "--json"],
        ):
            with self.subTest(args=args):
                self._assert_parity(args, self.root)

    def test_parity_on_the_graph_writes(self):
        """(54) Writes are NOT repeatable — `source add` allocates a new id
        every time — so each entrypoint gets its own migrated copy and the
        three results are compared against each other.
        """
        script, module, zipapp = (
            self._migrated_copy(name) for name in ("script", "module", "zipapp")
        )
        outputs: dict[str, list[str]] = {}
        for name, root in (
            ("script", script), ("module", module), ("zipapp", zipapp)
        ):
            argv, cwd = self._entrypoint(name)
            lines = []
            for args in (
                ["memory", "classify", "M-0001", "confidential"],
                ["memory", "source", "add", "--kind", "url",
                 "--locator", "https://b.test"],
                ["memory", "source", "link", "M-0001", "MS-0001",
                 "--relation", "supports"],
                ["memory", "edge", "add", "M-0001", "M-0002",
                 "--relation", "contradicts"],
                ["memory", "contradictions", "--json"],
                ["memory", "graph", "M-0001", "--depth", "2", "--json"],
                ["doctor"],
            ):
                code, out, err = self._run(
                    [*argv, "--root", str(root), *args], cwd=cwd
                )
                lines.append(
                    f"$ {' '.join(args)} → {code}\n"
                    + self._normalize_clock(out, root)
                )
            outputs[name] = lines
        self.assertEqual(outputs["script"], outputs["module"])
        self.assertEqual(outputs["script"], outputs["zipapp"])
        self.assertIn("MS-0001", "\n".join(outputs["script"]))
        self.assertIn("ME-0001", "\n".join(outputs["script"]))

    def test_parity_on_doctor_after_migration(self):
        """(54)"""
        self.migrate()
        self._assert_parity(["doctor"], self.root)

    def test_zipapp_contains_implementation_but_no_data(self):
        """(54) The allowlist needs no change; this proves it."""
        import zipfile

        with zipfile.ZipFile(self.pyz) as archive:
            names = archive.namelist()
        self.assertIn("agentic_os/ops.py", names)
        self.assertIn("agentic_os/migrations.py", names)
        for name in names:
            self.assertFalse(name.endswith(".db"), name)
            self.assertNotIn("fixtures", name)
            self.assertNotIn("tests/", name)
            self.assertNotIn("backups", name)
            self.assertNotIn(".agentic-os", name)


if __name__ == "__main__":
    unittest.main()
