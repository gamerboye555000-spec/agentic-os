"""U-M1 migration kit (agentic-os-v0.2-u-m1-migration-contract.md).

Almost every proof here runs against a *synthetic* registry injected into
`apply_migrations`, so the machinery is tested independently of whatever
production happens to carry. Synthetic steps must never become production
schema migrations — the guard test at the top pins the production registry
and LATEST_VERSION against the one version declared in db.py.

U-M2 filled that registry with the first production step (1 → 2,
`u-m2-memory-claims-v2`), so the tests that once assumed "apply is a no-op
on the fixture" now migrate the fixture first and then assert the same
property. The v1 fixture is still v1; it is just no longer current. U-M2's
own proofs live in tests/test_v03_memory_claims.py.

The v1 fixture (tests/fixtures/v1_workspace.py) is a real historical v1
database built with production CLI commands, with representative rows in
every table. Each test copies the whole workspace to a temp directory, so
nothing here can touch a real ledger.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from fixtures.v1_workspace import build_v1_workspace, table_contents
from weekend_harness import run_cli

from agentic_os import backup, db, migrations, utils
from agentic_os.utils import AosError

REPO_ROOT = Path(__file__).resolve().parent.parent

# A secret and a SQL fragment planted where a careless implementation would
# echo them back out (M1.10).
PLANTED_SECRET = "sk-live-m1planted00000000000000000000000000000000"  # noqa: S105
PLANTED_SQL = "SELECT value FROM meta WHERE key = 'schema_version'"


# --- synthetic migrations (TEST ONLY — never production) -------------------

def _add_v2_table(conn: sqlite3.Connection) -> None:
    # No IF NOT EXISTS on purpose: a double-apply must fail loudly rather
    # than silently succeed and hide a concurrency bug.
    conn.execute("CREATE TABLE synthetic_v2(id INTEGER PRIMARY KEY, note TEXT)")
    conn.execute("INSERT INTO synthetic_v2 (note) VALUES ('migrated')")


def _add_v3_table(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE TABLE synthetic_v3(id INTEGER PRIMARY KEY)")


def _boom(conn: sqlite3.Connection) -> None:
    """A step that fails AFTER writing, so rollback has something to undo."""
    conn.execute("CREATE TABLE synthetic_v2(id INTEGER PRIMARY KEY)")
    raise RuntimeError(f"planted failure {PLANTED_SECRET} while running {PLANTED_SQL}")


V1_TO_V2 = migrations.Migration(1, 2, "0001-synthetic-v2", _add_v2_table)
V2_TO_V3 = migrations.Migration(2, 3, "0002-synthetic-v3", _add_v3_table)
V1_TO_V2_FAILING = migrations.Migration(1, 2, "0001-synthetic-v2", _boom)
V2_TO_V3_FAILING = migrations.Migration(2, 3, "0002-synthetic-v3", _boom)

SYNTHETIC_1_2 = (V1_TO_V2,)
SYNTHETIC_1_2_3 = (V1_TO_V2, V2_TO_V3)


class MigrationTestCase(unittest.TestCase):
    """A disposable copy of the historical v1 fixture workspace."""

    #: Built once — the fixture is deterministic and read-only to tests.
    _fixture_root: Path | None = None

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.mkdtemp(prefix="aos-m1-fixture-")
        cls._fixture_tmp = tmp
        cls._fixture_root = Path(tmp) / "v1"
        build_v1_workspace(cls._fixture_root)

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

    # --- probes

    def db_bytes(self) -> bytes:
        return self.db_path.read_bytes()

    def aos_listing(self) -> list[str]:
        return sorted(
            p.relative_to(self.aos_dir).as_posix()
            for p in self.aos_dir.rglob("*")
        )

    def version(self) -> str | None:
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def migrate_events(self) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT payload_json FROM events WHERE entity = ? AND action = ?",
                (migrations.MIGRATION_EVENT_ENTITY, migrations.MIGRATION_EVENT_ACTION),
            ).fetchall()
            return [json.loads(row[0]) for row in rows]
        finally:
            conn.close()

    def event_count(self) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        finally:
            conn.close()

    def table_names(self) -> set[str]:
        conn = sqlite3.connect(self.db_path)
        try:
            return {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        finally:
            conn.close()

    def set_version_raw(self, value) -> None:
        """Write a version a migration never would — for refusal proofs."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE meta SET value = ? WHERE key = 'schema_version'", (value,)
            )
            conn.commit()
        finally:
            conn.close()

    def aos(self, *argv: str) -> tuple[int, str, str]:
        return run_cli("--root", str(self.root), *argv)

    def fresh_v1_copy(self) -> Path:
        """Another pristine, UNMIGRATED copy of the v1 fixture. For the few
        tests that need both a v1 database and a current one."""
        target = Path(tempfile.mkdtemp(prefix="aos-m1-v1-")) / "ws"
        self.addCleanup(shutil.rmtree, target.parent, True)
        shutil.copytree(self._fixture_root, target, symlinks=True)
        return target

    def migrate_to_current(self) -> None:
        """Bring the v1 fixture up to the version this build supports.

        For every test below whose subject is NOT the schema version — the
        backup machinery, the read-only guarantees of a no-op apply, the
        rest of the CLI — the fixture just needs to be current. Since U-M2 it
        is not, so they say so explicitly instead of relying on an empty
        registry.
        """
        code, _, err = self.aos("migrate", "apply")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.version(), db.SCHEMA_VERSION)


# ---------------------------------------------------------------------------
# 1. The production registry carries exactly the U-M2 step.

class ProductionRegistryTest(MigrationTestCase):
    def test_latest_version_is_derived_from_the_one_schema_declaration(self):
        # If this fails, a migration was added without raising SCHEMA_VERSION
        # with it — or the reverse.
        self.assertEqual(migrations.LATEST_VERSION, int(db.SCHEMA_VERSION))
        self.assertEqual(migrations.LATEST_VERSION, 3)

    def test_production_registry_is_the_two_production_steps(self):
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

    def test_no_synthetic_step_ever_reached_production(self):
        # The synthetic steps below exist to exercise the machinery. If one
        # of them shows up here, a test fixture became a schema migration.
        ids = {m.migration_id for m in migrations.MIGRATIONS}
        self.assertNotIn("0001-synthetic-v2", ids)
        self.assertNotIn("0002-synthetic-v3", ids)

    def test_production_registry_reports_the_pending_migrations(self):
        report = migrations.status(self.db_path)
        self.assertEqual(report["current_version"], 1)
        self.assertEqual(report["latest_version"], 3)
        self.assertTrue(report["pending"])
        self.assertEqual(
            report["plan"],
            [
                {"from": 1, "to": 2, "migration_id": "u-m2-memory-claims-v2"},
                {"from": 2, "to": 3, "migration_id": "u-m3-memory-graph-v3"},
            ],
        )

    def test_nothing_is_pending_once_the_fixture_is_current(self):
        self.migrate_to_current()
        report = migrations.status(self.db_path)
        self.assertEqual(report["current_version"], int(db.SCHEMA_VERSION))
        self.assertFalse(report["pending"])
        self.assertEqual(report["plan"], [])

    def test_status_and_plan_agree_about_what_is_pending(self):
        code, out, _ = self.aos("migrate", "status")
        self.assertEqual(code, 0)
        self.assertIn("pending:         yes", out)
        code, out, _ = self.aos("migrate", "plan")
        self.assertEqual(code, 0)
        self.assertIn("1 → 2", out)

        self.migrate_to_current()
        code, out, _ = self.aos("migrate", "status")
        self.assertEqual(code, 0)
        self.assertIn("pending:         no", out)
        code, out, _ = self.aos("migrate", "plan")
        self.assertEqual(code, 0)
        self.assertIn("No migrations pending", out)


# ---------------------------------------------------------------------------
# 2/3. status and plan are read-only; no-op apply changes nothing.

class ReadOnlyTest(MigrationTestCase):
    def test_status_is_byte_for_byte_read_only(self):
        before, listing = self.db_bytes(), self.aos_listing()
        self.assertEqual(self.aos("migrate", "status")[0], 0)
        self.assertEqual(self.aos("migrate", "status", "--json")[0], 0)
        self.assertEqual(self.db_bytes(), before)
        # No -wal/-shm droppings, no backups dir, no temp file.
        self.assertEqual(self.aos_listing(), listing)

    def test_plan_is_byte_for_byte_read_only(self):
        before, listing = self.db_bytes(), self.aos_listing()
        self.assertEqual(self.aos("migrate", "plan")[0], 0)
        self.assertEqual(self.aos("migrate", "plan", "--json")[0], 0)
        self.assertEqual(self.aos("migrate", "plan", "--target", "1")[0], 0)
        self.assertEqual(self.db_bytes(), before)
        self.assertEqual(self.aos_listing(), listing)

    def test_read_path_refuses_writes_at_the_engine(self):
        # The read-only guarantee is SQLite's, not ours-by-convention.
        conn = migrations.open_readonly(self.db_path)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("INSERT INTO meta VALUES ('x', 'y')")
                conn.commit()
        finally:
            conn.close()

    def test_noop_apply_writes_no_backup_no_event_and_no_byte(self):
        # A no-op apply is only reachable on a CURRENT database now.
        self.migrate_to_current()
        migrate_events_before = len(self.migrate_events())
        before, listing = self.db_bytes(), self.aos_listing()
        events_before = self.event_count()

        code, out, err = self.aos("migrate", "apply")
        self.assertEqual(code, 0, err)
        self.assertIn("No migrations pending", out)

        self.assertEqual(self.db_bytes(), before)
        self.assertEqual(self.aos_listing(), listing)
        self.assertEqual(self.event_count(), events_before)
        self.assertEqual(len(self.migrate_events()), migrate_events_before)
        self.assertEqual(self.version(), db.SCHEMA_VERSION)

    def test_noop_apply_never_opens_the_database_read_write(self):
        # The no-op path's byte guarantee comes from never taking a
        # read-write handle at all, not from being careful once it has one.
        self.migrate_to_current()
        real_connect = db.connect
        rw_opens = []

        def spy(path):
            if Path(path) == self.db_path:
                rw_opens.append(path)
            return real_connect(path)

        with mock.patch.object(db, "connect", side_effect=spy) as spied:
            result = migrations.apply_migrations(self.aos_dir)
        self.assertFalse(result["migrated"])
        # Only the query_only pre-flight read; no read-write handle.
        self.assertEqual(len(rw_opens), 1)
        self.assertEqual(spied.call_count, 1)

    def test_normal_commands_never_auto_migrate(self):
        for argv in (
            ("status",), ("doctor",), ("task", "list"), ("sync",),
            ("in", "a thought"), ("log",),
        ):
            with self.subTest(argv=argv):
                self.aos(*argv)
                # No command but `migrate apply` may move the version, take a
                # snapshot, or write a migrate event — no matter what it does
                # to the ledger otherwise.
                self.assertEqual(self.version(), "1")
                self.assertEqual(self.migrate_events(), [])
                self.assertFalse(self.backups_dir.exists())


# ---------------------------------------------------------------------------
# 4-8. A synthetic v1→v2 migration: success, preservation, snapshot, event.

class ForwardMigrationTest(MigrationTestCase):
    def test_synthetic_v1_to_v2_succeeds(self):
        result = migrations.apply_migrations(
            self.aos_dir, registry=SYNTHETIC_1_2, latest=2
        )
        self.assertTrue(result["migrated"])
        self.assertEqual(result["current_version"], 2)
        self.assertEqual(len(result["applied"]), 1)
        self.assertIn("synthetic_v2", self.table_names())
        self.assertEqual(self.version(), "2")

    def test_schema_version_advances_exactly_once(self):
        migrations.apply_migrations(self.aos_dir, registry=SYNTHETIC_1_2, latest=2)
        self.assertEqual(self.version(), "2")
        # And exactly one meta row still holds it.
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual(rows, [("2",)])

    def test_historical_rows_survive_field_equivalently(self):
        before = table_contents(self.db_path)
        migrations.apply_migrations(self.aos_dir, registry=SYNTHETIC_1_2, latest=2)
        after = table_contents(self.db_path)

        # Every table but meta (version bump) and events (one new migrate
        # event) must be identical, field for field.
        for table in before:
            if table in ("meta", "events"):
                continue
            self.assertEqual(after[table], before[table], f"{table} changed")
        self.assertTrue(before["projects"], "fixture must not be empty")
        self.assertEqual(len(before["tasks"]), 4)

        # Every pre-existing event row survives byte-identically.
        for row in before["events"]:
            self.assertIn(row, after["events"])
        self.assertEqual(len(after["events"]), len(before["events"]) + 1)

    def test_exactly_one_safe_migration_event_is_emitted(self):
        result = migrations.apply_migrations(
            self.aos_dir, registry=SYNTHETIC_1_2, latest=2
        )
        events = self.migrate_events()
        self.assertEqual(len(events), 1)
        payload = events[0]
        self.assertEqual(
            set(payload),
            {"schema_version", "from", "to", "migration_id", "snapshot"},
        )
        self.assertEqual(payload["from"], 1)
        self.assertEqual(payload["to"], 2)
        self.assertEqual(payload["migration_id"], "0001-synthetic-v2")
        # A safe RELATIVE reference — never an absolute, user-identifying path.
        self.assertTrue(payload["snapshot"].startswith(f"{backup.BACKUPS_DIRNAME}/"))
        self.assertFalse(Path(payload["snapshot"]).is_absolute())
        self.assertEqual(
            payload["snapshot"], f"{backup.BACKUPS_DIRNAME}/{result['snapshot'].name}"
        )

    def test_snapshot_exists_and_verifies_before_the_first_mutation(self):
        """The strongest form of the proof: inspect the world from *inside*
        the migration step, before its schema change can commit."""
        observed = {}

        def observing_step(conn):
            snapshots = sorted(self.backups_dir.glob("aos-backup-*.db"))
            observed["count"] = len(snapshots)
            observed["checks"] = backup.verify_backup(
                snapshots[0], expected_schema_version="1"
            )
            # The live database has not been advanced yet, and a separate
            # reader still sees v1 (this step's transaction is uncommitted).
            observed["live_version"] = self.version()
            _add_v2_table(conn)

        migrations.apply_migrations(
            self.aos_dir,
            registry=(migrations.Migration(1, 2, "0001-observe", observing_step),),
            latest=2,
        )
        self.assertEqual(observed["count"], 1)
        self.assertTrue(
            all(check.ok for check in observed["checks"]),
            [c for c in observed["checks"] if not c.ok],
        )
        self.assertEqual(observed["live_version"], "1")

    def test_snapshot_is_the_pre_migration_state_and_verifies_afterwards(self):
        before = table_contents(self.db_path)
        result = migrations.apply_migrations(
            self.aos_dir, registry=SYNTHETIC_1_2, latest=2
        )
        snapshot = result["snapshot"]
        self.assertTrue(snapshot.is_file())
        self.assertTrue(backup.manifest_path_for(snapshot).is_file())

        checks = backup.verify_backup(snapshot, expected_schema_version="1")
        self.assertTrue(all(c.ok for c in checks), [c for c in checks if not c.ok])

        # It holds v1, not the migrated schema.
        self.assertEqual(table_contents(snapshot), before)
        conn = sqlite3.connect(snapshot)
        try:
            names = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            conn.close()
        self.assertNotIn("synthetic_v2", names)

    def test_snapshot_carries_no_migrate_event_of_its_own(self):
        # U-C2's rule extended: the snapshot cannot contain the event that
        # names it, and no backup_create event is written either.
        result = migrations.apply_migrations(
            self.aos_dir, registry=SYNTHETIC_1_2, latest=2
        )
        conn = sqlite3.connect(result["snapshot"])
        try:
            actions = {
                r[0] for r in conn.execute("SELECT action FROM events")
            }
        finally:
            conn.close()
        self.assertNotIn("migrate", actions)
        self.assertNotIn("backup_create", actions)

        conn = sqlite3.connect(self.db_path)
        try:
            live = {r[0] for r in conn.execute("SELECT action FROM events")}
        finally:
            conn.close()
        self.assertIn("migrate", live)
        self.assertNotIn("backup_create", live)

    def test_multi_step_v1_to_v3_runs_in_order(self):
        result = migrations.apply_migrations(
            self.aos_dir, registry=SYNTHETIC_1_2_3, latest=3
        )
        self.assertEqual(result["current_version"], 3)
        self.assertEqual(
            [(s["from"], s["to"]) for s in result["applied"]], [(1, 2), (2, 3)]
        )
        self.assertEqual(self.version(), "3")
        self.assertLessEqual({"synthetic_v2", "synthetic_v3"}, self.table_names())
        events = self.migrate_events()
        self.assertEqual([(e["from"], e["to"]) for e in events], [(1, 2), (2, 3)])
        # Both steps reference the ONE pre-migration snapshot.
        self.assertEqual(len({e["snapshot"] for e in events}), 1)

    def test_status_reports_a_pending_plan(self):
        # The pending branch is unreachable in production today (empty
        # registry), so it is proved against a synthetic one instead.
        report = migrations.status(self.db_path, registry=SYNTHETIC_1_2_3, latest=3)
        self.assertTrue(report["pending"])
        self.assertEqual(
            [(s["from"], s["to"]) for s in report["plan"]], [(1, 2), (2, 3)]
        )
        self.assertEqual(report["current_version"], 1)
        self.assertEqual(report["latest_version"], 3)

    def test_cli_renders_a_pending_status_and_plan(self):
        real_status, real_plan = migrations.status, migrations.plan_report

        def status(db_path, registry=SYNTHETIC_1_2_3, latest=3):
            return real_status(db_path, registry=registry, latest=latest)

        def plan_report(db_path, target=None, registry=SYNTHETIC_1_2_3, latest=3):
            return real_plan(db_path, target=target, registry=registry, latest=latest)

        with mock.patch.object(migrations, "status", status):
            code, out, err = self.aos("migrate", "status")
        self.assertEqual(code, 0, err)
        self.assertIn("pending:         yes (2 migration(s))", out)

        with mock.patch.object(migrations, "plan_report", plan_report):
            code, out, err = self.aos("migrate", "plan")
        self.assertEqual(code, 0, err)
        self.assertIn("2 migration(s) would run, in order:", out)
        self.assertIn("1 → 2  0001-synthetic-v2", out)
        self.assertIn("2 → 3  0002-synthetic-v3", out)
        # Planning still wrote nothing.
        self.assertFalse(self.backups_dir.exists())
        self.assertEqual(self.version(), "1")

    def test_cli_reports_a_successful_apply(self):
        real = migrations.apply_migrations

        def patched(aos_dir, target=None, registry=SYNTHETIC_1_2, latest=2):
            return real(aos_dir, target=target, registry=registry, latest=latest)

        with mock.patch.object(migrations, "apply_migrations", patched):
            code, out, err = self.aos("migrate", "apply")
        self.assertEqual(code, 0, err)
        self.assertIn("Snapshot:", out)
        self.assertIn("applied 1 → 2  0001-synthetic-v2", out)
        self.assertIn("Schema version is now 2.", out)

    def test_explicit_target_stops_early(self):
        result = migrations.apply_migrations(
            self.aos_dir, target=2, registry=SYNTHETIC_1_2_3, latest=3
        )
        self.assertEqual(result["current_version"], 2)
        self.assertEqual(self.version(), "2")
        self.assertNotIn("synthetic_v3", self.table_names())


# ---------------------------------------------------------------------------
# 9-12. Failure atomicity.

class FailureAtomicityTest(MigrationTestCase):
    def test_failure_before_mutation_leaves_the_database_unchanged(self):
        before, listing = self.db_bytes(), self.aos_listing()
        with mock.patch.object(
            backup, "write_backup_pair", side_effect=OSError("disk full")
        ):
            with self.assertRaises(OSError):
                migrations.apply_migrations(
                    self.aos_dir, registry=SYNTHETIC_1_2, latest=2
                )
        self.assertEqual(self.db_bytes(), before)
        self.assertEqual(self.aos_listing(), listing)
        self.assertEqual(self.version(), "1")
        self.assertEqual(self.migrate_events(), [])

    def test_unverifiable_snapshot_refuses_before_any_mutation(self):
        before = self.db_bytes()
        failing = [backup.VerifyCheck("sha256 matches manifest", False, "bad bytes")]
        with mock.patch.object(backup, "verify_backup", return_value=failing):
            with self.assertRaises(AosError) as ctx:
                migrations.apply_migrations(
                    self.aos_dir, registry=SYNTHETIC_1_2, latest=2
                )
        self.assertIn("snapshot failed verification", str(ctx.exception))
        self.assertEqual(self.db_bytes(), before)
        self.assertEqual(self.version(), "1")
        self.assertNotIn("synthetic_v2", self.table_names())
        self.assertEqual(self.migrate_events(), [])

    def test_failure_inside_a_step_rolls_that_step_back_completely(self):
        with self.assertRaises(migrations.MigrationStepError) as ctx:
            migrations.apply_migrations(
                self.aos_dir, registry=(V1_TO_V2_FAILING,), latest=2
            )
        exc = ctx.exception
        # The step's schema change, version bump, and event died together.
        self.assertEqual(self.version(), "1")
        self.assertNotIn("synthetic_v2", self.table_names())
        self.assertEqual(self.migrate_events(), [])
        self.assertEqual(exc.applied, ())
        # The verified snapshot survives.
        self.assertIsNotNone(exc.snapshot)
        self.assertTrue(exc.snapshot.is_file())
        checks = backup.verify_backup(exc.snapshot, expected_schema_version="1")
        self.assertTrue(all(c.ok for c in checks))

    def test_failure_after_a_committed_step_reports_partial_advancement(self):
        with self.assertRaises(migrations.MigrationStepError) as ctx:
            migrations.apply_migrations(
                self.aos_dir, registry=(V1_TO_V2, V2_TO_V3_FAILING), latest=3
            )
        exc = ctx.exception
        # Step 1 committed and stays committed; step 2 left nothing behind.
        self.assertEqual(self.version(), "2")
        self.assertIn("synthetic_v2", self.table_names())
        self.assertNotIn("synthetic_v3", self.table_names())
        self.assertEqual([(s["from"], s["to"]) for s in exc.applied], [(1, 2)])
        self.assertEqual([(e["from"], e["to"]) for e in self.migrate_events()], [(1, 2)])
        self.assertIn("0002-synthetic-v3", str(exc))
        self.assertIn("2 → 3", str(exc))

        # The ORIGINAL pre-migration snapshot is still usable.
        checks = backup.verify_backup(exc.snapshot, expected_schema_version="1")
        self.assertTrue(all(c.ok for c in checks), [c for c in checks if not c.ok])

    def test_partial_advancement_gives_an_exact_restore_instruction(self):
        code, out, err = self.aos_apply_with(
            registry=(V1_TO_V2, V2_TO_V3_FAILING), latest=3
        )
        self.assertEqual(code, 1)
        self.assertIn("PARTIALLY ADVANCED", err)
        self.assertIn("backup restore", err)
        self.assertIn("--to", err)
        self.assertIn("RECOVERY.md", err)
        self.assertIn("Do NOT edit schema_version by hand", err)
        # The named snapshot exists and verifies.
        named = [
            tok for tok in err.split() if tok.endswith(".db") and "aos-backup-" in tok
        ]
        self.assertTrue(named)
        snapshot = Path(named[0])
        self.assertTrue(snapshot.is_file())
        self.assertTrue(all(c.ok for c in backup.verify_backup(
            snapshot, expected_schema_version="1")))

    def aos_apply_with(self, registry, latest):
        """`migrate apply` at the CLI, but against a synthetic registry."""
        real = migrations.apply_migrations

        def patched(aos_dir, target=None, registry=registry, latest=latest):
            return real(aos_dir, target=target, registry=registry, latest=latest)

        with mock.patch.object(migrations, "apply_migrations", patched):
            return self.aos("migrate", "apply")

    def test_no_automatic_destructive_rollback_across_committed_steps(self):
        with self.assertRaises(migrations.MigrationStepError):
            migrations.apply_migrations(
                self.aos_dir, registry=(V1_TO_V2, V2_TO_V3_FAILING), latest=3
            )
        # v2 was NOT undone: rollback is the human's restore workflow.
        self.assertEqual(self.version(), "2")
        self.assertIn("synthetic_v2", self.table_names())

    def test_corrected_retry_resumes_from_the_committed_version(self):
        with self.assertRaises(migrations.MigrationStepError):
            migrations.apply_migrations(
                self.aos_dir, registry=(V1_TO_V2, V2_TO_V3_FAILING), latest=3
            )
        self.assertEqual(self.version(), "2")
        snapshots_after_first = sorted(self.backups_dir.glob("*.db"))

        # Retry with the corrected registry: step 1 must NOT replay (it would
        # fail on CREATE TABLE synthetic_v2 if it did).
        result = migrations.apply_migrations(
            self.aos_dir, registry=SYNTHETIC_1_2_3, latest=3
        )
        self.assertTrue(result["migrated"])
        self.assertEqual([(s["from"], s["to"]) for s in result["applied"]], [(2, 3)])
        self.assertEqual(self.version(), "3")
        self.assertEqual(
            [(e["from"], e["to"]) for e in self.migrate_events()], [(1, 2), (2, 3)]
        )
        # The retry snapshotted the v2 state it actually found.
        new = sorted(set(self.backups_dir.glob("*.db")) - set(snapshots_after_first))
        self.assertEqual(len(new), 1)
        self.assertTrue(all(c.ok for c in backup.verify_backup(
            new[0], expected_schema_version="2")))

    def test_a_step_that_destroys_the_version_row_fails_instead_of_lying(self):
        # An UPDATE matching zero rows succeeds silently; without the
        # rowcount check the step would commit an event announcing a bump
        # that never happened.
        def rogue(conn):
            conn.execute("DELETE FROM meta WHERE key = 'schema_version'")

        with self.assertRaises(migrations.MigrationStepError) as ctx:
            migrations.apply_migrations(
                self.aos_dir,
                registry=(migrations.Migration(1, 2, "0001-rogue", rogue),),
                latest=2,
            )
        self.assertIn("0001-rogue", str(ctx.exception))
        # Rolled back completely: the row is back and no event survived.
        self.assertEqual(self.version(), "1")
        self.assertEqual(self.migrate_events(), [])

    def test_interrupting_a_step_still_rolls_it_back(self):
        # Ctrl-C is the operator talking, not a migration failure: it
        # propagates unwrapped — but only after the step is rolled back.
        def interrupted(conn):
            conn.execute("CREATE TABLE synthetic_v2(id INTEGER PRIMARY KEY)")
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            migrations.apply_migrations(
                self.aos_dir,
                registry=(migrations.Migration(1, 2, "0001-interrupted", interrupted),),
                latest=2,
            )
        self.assertEqual(self.version(), "1")
        self.assertNotIn("synthetic_v2", self.table_names())
        self.assertEqual(self.migrate_events(), [])

    def test_a_failed_step_cannot_report_success(self):
        code, out, err = self.aos_apply_with(registry=(V1_TO_V2_FAILING,), latest=2)
        self.assertEqual(code, 1)
        self.assertNotIn("Schema version is now", out)
        self.assertEqual(self.version(), "1")


# ---------------------------------------------------------------------------
# 13/14. Concurrency and stale state.

class ConcurrencyTest(MigrationTestCase):
    def test_two_concurrent_applies_do_not_double_apply(self):
        second_started = threading.Event()
        in_step = threading.Event()
        second: dict = {}

        def slow_step(conn):
            in_step.set()
            # Hold the write lock until the second attempt is blocked on it.
            second_started.wait(timeout=10)
            _add_v2_table(conn)

        def second_attempt():
            in_step.wait(timeout=10)
            second_started.set()
            try:
                second["result"] = migrations.apply_migrations(
                    self.aos_dir, registry=SYNTHETIC_1_2, latest=2
                )
            except BaseException as exc:  # noqa: BLE001 — recorded, asserted below
                second["error"] = exc

        thread = threading.Thread(target=second_attempt)
        thread.start()
        first = migrations.apply_migrations(
            self.aos_dir,
            registry=(migrations.Migration(1, 2, "0001-synthetic-v2", slow_step),),
            latest=2,
        )
        thread.join(timeout=30)
        self.assertFalse(thread.is_alive())

        self.assertTrue(first["migrated"])
        self.assertEqual(self.version(), "2")
        # Exactly one transition happened, no matter which way the loser lost.
        self.assertEqual(len(self.migrate_events()), 1)
        self.assertEqual(
            self.table_names() & {"synthetic_v2"}, {"synthetic_v2"}
        )
        if "result" in second:
            self.assertFalse(
                second["result"]["migrated"],
                "second apply must not have migrated again",
            )
        else:
            self.assertIsInstance(second["error"], AosError)

    def test_readers_never_see_a_partially_applied_step(self):
        seen = []

        def observed_step(conn):
            _add_v2_table(conn)
            # A separate reader mid-step sees the state BEFORE this step.
            seen.append((self.version(), "synthetic_v2" in self.table_names()))

        migrations.apply_migrations(
            self.aos_dir,
            registry=(migrations.Migration(1, 2, "0001-observe", observed_step),),
            latest=2,
        )
        self.assertEqual(seen, [("1", False)])
        self.assertEqual(self.version(), "2")
        self.assertIn("synthetic_v2", self.table_names())

    def test_stale_version_between_planning_and_the_lock_refuses(self):
        # The pre-flight read sees 1; by the time the lock is held it is 2.
        real = migrations.read_schema_version
        calls = {"n": 0}

        def drifting(conn):
            calls["n"] += 1
            if calls["n"] == 1:
                return real(conn)
            return 2

        before = self.db_bytes()
        with mock.patch.object(migrations, "read_schema_version", drifting):
            with self.assertRaises(AosError) as ctx:
                migrations.apply_migrations(
                    self.aos_dir, registry=SYNTHETIC_1_2, latest=2
                )
        self.assertIn("stale plan", str(ctx.exception))
        self.assertEqual(self.db_bytes(), before)
        self.assertEqual(self.version(), "1")
        self.assertFalse(self.backups_dir.exists(), "refused before snapshotting")

    def test_step_refuses_when_its_from_version_no_longer_matches(self):
        # Drift AFTER the snapshot, at the per-step re-check.
        real = migrations.read_schema_version
        calls = {"n": 0}

        def drifting(conn):
            calls["n"] += 1
            if calls["n"] <= 2:      # pre-flight + under-lock confirm
                return real(conn)
            return 7                 # the per-step re-check

        with self.assertRaises(migrations.MigrationStepError) as ctx:
            with mock.patch.object(migrations, "read_schema_version", drifting):
                migrations.apply_migrations(
                    self.aos_dir, registry=SYNTHETIC_1_2, latest=2
                )
        self.assertIn("another process may have migrated", str(ctx.exception))
        self.assertEqual(self.version(), "1")
        self.assertNotIn("synthetic_v2", self.table_names())
        self.assertEqual(self.migrate_events(), [])


# ---------------------------------------------------------------------------
# 15. Schema-version safety.

class SchemaVersionSafetyTest(MigrationTestCase):
    def test_missing_schema_version_row_refuses(self):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM meta WHERE key = 'schema_version'")
            conn.commit()
        finally:
            conn.close()
        for argv in (("status",), ("plan",), ("apply",)):
            code, _, err = self.aos("migrate", *argv)
            self.assertEqual(code, 1)
            self.assertIn("no schema_version row", err)

    def test_missing_meta_table_refuses(self):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DROP TABLE meta")
            conn.commit()
        finally:
            conn.close()
        code, _, err = self.aos("migrate", "status")
        self.assertEqual(code, 1)
        self.assertIn("no `meta` table", err)

    def test_duplicate_schema_version_rows_refuse(self):
        # Reachable only via a meta table built without its PRIMARY KEY —
        # which is exactly why the reader fetches all rows, not LIMIT 1.
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(
                "ALTER TABLE meta RENAME TO meta_old;"
                "CREATE TABLE meta(key TEXT, value TEXT);"
                "INSERT INTO meta SELECT key, value FROM meta_old;"
                "INSERT INTO meta (key, value) VALUES ('schema_version', '2');"
                "DROP TABLE meta_old;"
            )
            conn.commit()
        finally:
            conn.close()
        code, _, err = self.aos("migrate", "status")
        self.assertEqual(code, 1)
        self.assertIn("2 schema_version rows", err)

    def test_malformed_versions_refuse(self):
        for raw in ("", " 1", "1 ", "01", "+1", "1.0", "0x1", "one", "1_0", "v1"):
            with self.subTest(raw=raw):
                self.set_version_raw(raw)
                code, _, err = self.aos("migrate", "status")
                self.assertEqual(code, 1, f"{raw!r} was accepted")
                self.assertTrue(
                    "not an integer" in err or "not canonical" in err, err
                )

    def test_null_version_refuses(self):
        self.set_version_raw(None)
        code, _, err = self.aos("migrate", "status")
        self.assertEqual(code, 1)
        self.assertIn("null", err)

    def test_negative_version_refuses(self):
        self.set_version_raw("-1")
        code, _, err = self.aos("migrate", "status")
        self.assertEqual(code, 1)
        self.assertIn("negative", err)

    def test_version_newer_than_supported_refuses(self):
        self.set_version_raw("99")
        for argv in (("status",), ("plan",), ("apply",)):
            code, _, err = self.aos("migrate", *argv)
            self.assertEqual(code, 1)
            self.assertIn("newer than this build supports", err)
        self.assertEqual(self.version(), "99", "refusal must not rewrite it")

    def test_refusal_never_rewrites_the_version_row(self):
        for raw in ("99", "banana", "-3"):
            self.set_version_raw(raw)
            self.aos("migrate", "status")
            self.aos("migrate", "plan")
            self.aos("migrate", "apply")
            self.assertEqual(self.version(), raw)

    def test_downgrade_target_refuses(self):
        with self.assertRaises(AosError) as ctx:
            migrations.plan_migrations(2, 1, SYNTHETIC_1_2, 2)
        self.assertIn("Refusing to downgrade", str(ctx.exception))

    def test_target_above_supported_refuses(self):
        with self.assertRaises(AosError) as ctx:
            migrations.plan_migrations(1, 5, SYNTHETIC_1_2, 2)
        self.assertIn("not supported by this build", str(ctx.exception))

    def test_no_complete_path_refuses(self):
        # latest says 3 but only 1→2 exists: 2→3 is missing.
        with self.assertRaises(AosError) as ctx:
            migrations.plan_migrations(1, 3, SYNTHETIC_1_2, 3)
        self.assertIn("No migration path", str(ctx.exception))

    def test_normal_commands_still_refuse_unsupported_versions_as_before(self):
        # U-M1 must not have opened a back door: the version gate migrate
        # walks through stays shut for everyone else.
        self.set_version_raw("99")
        for argv in (("status",), ("task", "list"), ("sync",), ("doctor",)):
            with self.subTest(argv=argv):
                code, _, err = self.aos(*argv)
                self.assertNotEqual(code, 0, f"{argv} accepted version 99")
                if argv != ("doctor",):
                    self.assertIn("this build supports", err)
        self.assertEqual(self.version(), "99", "a refusal must not rewrite it")


# ---------------------------------------------------------------------------
# 16. Registry validation, before any backup or mutation.

class RegistryValidationTest(MigrationTestCase):
    def _refuses(self, registry, latest, fragment):
        with self.assertRaises(AosError) as ctx:
            migrations.validate_registry(registry, latest)
        self.assertIn(fragment, str(ctx.exception))

    def test_empty_registry_is_valid(self):
        migrations.validate_registry((), 1)

    def test_gap_refuses(self):
        registry = (V1_TO_V2, migrations.Migration(3, 4, "gap", _add_v3_table))
        self._refuses(registry, 4, "gap in the chain")

    def test_duplicate_from_version_refuses(self):
        registry = (V1_TO_V2, migrations.Migration(1, 2, "dup-from", _add_v3_table))
        self._refuses(registry, 2, "ambiguous path")

    def test_duplicate_to_version_refuses(self):
        # Distinct from_versions, same target.
        registry = (
            migrations.Migration(1, 2, "a", _add_v2_table),
            migrations.Migration(0, 1, "b", _add_v3_table),
            migrations.Migration(1, 2, "c", _add_v3_table),
        )
        self._refuses(registry, 2, "ambiguous path")

    def test_backward_step_refuses(self):
        self._refuses(
            (migrations.Migration(2, 1, "backward", _add_v2_table),), 2,
            "must advance by exactly one version",
        )

    def test_skipped_version_refuses(self):
        self._refuses(
            (migrations.Migration(1, 3, "skip", _add_v2_table),), 3,
            "must advance by exactly one version",
        )

    def test_self_loop_refuses(self):
        self._refuses(
            (migrations.Migration(1, 1, "loop", _add_v2_table),), 1,
            "must advance by exactly one version",
        )

    def test_non_integer_versions_refuse(self):
        self._refuses(
            (migrations.Migration("1", "2", "text", _add_v2_table),), 2,
            "non-integer or negative versions",
        )

    def test_boolean_versions_refuse(self):
        # bool is an int subclass; True must not pass as version 1.
        self._refuses(
            (migrations.Migration(True, 2, "bool", _add_v2_table),), 2,
            "non-integer or negative versions",
        )

    def test_negative_version_refuses(self):
        self._refuses(
            (migrations.Migration(-1, 0, "neg", _add_v2_table),), 2,
            "non-integer or negative versions",
        )

    def test_step_beyond_supported_latest_refuses(self):
        self._refuses(SYNTHETIC_1_2_3, 2, "beyond the supported")

    def test_empty_identifier_refuses(self):
        self._refuses(
            (migrations.Migration(1, 2, "  ", _add_v2_table),), 2,
            "empty or non-string identifier",
        )

    def test_duplicate_identifier_refuses(self):
        registry = (
            migrations.Migration(1, 2, "same", _add_v2_table),
            migrations.Migration(2, 3, "same", _add_v3_table),
        )
        self._refuses(registry, 3, "duplicate migration identifier")

    def test_non_callable_apply_refuses(self):
        self._refuses(
            (migrations.Migration(1, 2, "notcallable", "DROP TABLE tasks"),), 2,
            "no callable apply",
        )

    def test_invalid_registry_refuses_before_backup_or_mutation(self):
        before, listing = self.db_bytes(), self.aos_listing()
        bad = (V1_TO_V2, migrations.Migration(3, 4, "gap", _add_v3_table))
        with self.assertRaises(AosError):
            migrations.apply_migrations(self.aos_dir, registry=bad, latest=4)
        self.assertEqual(self.db_bytes(), before)
        self.assertEqual(self.aos_listing(), listing)
        self.assertFalse(self.backups_dir.exists())
        self.assertEqual(self.version(), "1")

    def test_registry_is_not_discovered_from_the_database(self):
        # Migrations come from a literal tuple in source. A name planted in
        # the ledger must never become executable.
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('migration', 'os.system')"
            )
            conn.commit()
        finally:
            conn.close()
        # The planted name is inert: the registry is still exactly the steps
        # compiled into source.
        self.assertEqual(
            [m.migration_id for m in migrations.MIGRATIONS],
            ["u-m2-memory-claims-v2", "u-m3-memory-graph-v3"],
        )
        self.assertEqual(
            [s["migration_id"] for s in migrations.status(self.db_path)["plan"]],
            ["u-m2-memory-claims-v2", "u-m3-memory-graph-v3"],
        )


# ---------------------------------------------------------------------------
# 17. Filesystem safety.

class FilesystemSafetyTest(MigrationTestCase):
    def _refuse_unchanged(self, path: Path):
        """Every migrate subcommand refuses, and the object is untouched."""
        before = os.lstat(path)
        for argv in (("status",), ("plan",), ("apply",)):
            code, _, err = self.aos("migrate", *argv)
            self.assertEqual(code, 1, f"migrate {argv[0]} accepted {path}")
            self.assertNotIn("Traceback", err)
        after = os.lstat(path)
        self.assertEqual(before.st_mode, after.st_mode)
        self.assertEqual(before.st_ino, after.st_ino)

    def test_symlink_database_refuses_unchanged(self):
        real = self.root / "elsewhere.db"
        shutil.copyfile(self.db_path, real)
        real_before = real.read_bytes()
        self.db_path.unlink()
        self.db_path.symlink_to(real)

        self._refuse_unchanged(self.db_path)
        self.assertTrue(self.db_path.is_symlink())
        self.assertEqual(real.read_bytes(), real_before)
        code, _, err = self.aos("migrate", "apply")
        self.assertIn("symlink", err)

    def test_directory_database_refuses_unchanged(self):
        self.db_path.unlink()
        self.db_path.mkdir()
        self._refuse_unchanged(self.db_path)
        self.assertTrue(self.db_path.is_dir())

    def test_fifo_database_refuses_unchanged(self):
        self.db_path.unlink()
        os.mkfifo(self.db_path)
        self._refuse_unchanged(self.db_path)

    def test_socket_database_refuses_unchanged(self):
        self.db_path.unlink()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        sock.bind(str(self.db_path))
        self._refuse_unchanged(self.db_path)

    def test_missing_database_refuses(self):
        self.db_path.unlink()
        code, _, err = self.aos("migrate", "status")
        self.assertEqual(code, 1)
        self.assertIn("Not initialized", err)

    def test_require_regular_db_file_names_the_kind(self):
        for make, expected in (
            (lambda p: p.mkdir(), "a directory"),
            (lambda p: os.mkfifo(p), "a FIFO"),
        ):
            with self.subTest(expected=expected):
                target = self.root / f"probe-{expected.replace(' ', '-')}"
                make(target)
                with self.assertRaises(AosError) as ctx:
                    migrations.require_regular_db_file(target)
                self.assertIn(expected, str(ctx.exception))

    def test_lstat_not_stat_so_a_symlink_is_seen_as_a_symlink(self):
        link = self.root / "link.db"
        link.symlink_to(self.db_path)   # points at a REAL regular file
        with self.assertRaises(AosError) as ctx:
            migrations.require_regular_db_file(link)
        self.assertIn("symlink", str(ctx.exception))

    def test_backups_and_exports_are_never_migrated(self):
        # apply resolves the live ledger from the workspace and takes NO path
        # argument, so a backup, export, or fixture cannot be handed to it.
        self.migrate_to_current()
        self.aos("backup", "create")
        snapshot = next(self.backups_dir.glob("*.db"))
        before = snapshot.read_bytes()

        code, _, err = self.aos("migrate", "apply", str(snapshot))
        self.assertEqual(code, 1)
        self.assertIn("unrecognized arguments", err)
        self.assertEqual(snapshot.read_bytes(), before)


# ---------------------------------------------------------------------------
# 18. Privacy: no secrets, no SQL, no absolute paths.

class PrivacyTest(MigrationTestCase):
    def _assert_clean(self, text: str):
        self.assertNotIn(PLANTED_SECRET, text)
        self.assertNotIn("sk-live-", text)
        self.assertNotIn(PLANTED_SQL, text)
        self.assertNotIn("SELECT", text)
        self.assertNotIn("CREATE TABLE", text)
        self.assertNotIn("Traceback", text)

    def test_step_failure_diagnostic_echoes_no_secret_or_sql(self):
        with self.assertRaises(migrations.MigrationStepError) as ctx:
            migrations.apply_migrations(
                self.aos_dir, registry=(V1_TO_V2_FAILING,), latest=2
            )
        message = str(ctx.exception)
        self._assert_clean(message)
        # It still says what a human needs: the transition and safe id.
        self.assertIn("0001-synthetic-v2", message)
        self.assertIn("1 → 2", message)
        self.assertIn("RuntimeError", message)  # class name only, no payload

    def test_cli_failure_output_echoes_no_secret_or_sql(self):
        real = migrations.apply_migrations

        def patched(aos_dir, target=None, registry=(V1_TO_V2_FAILING,), latest=2):
            return real(aos_dir, target=target, registry=registry, latest=latest)

        with mock.patch.object(migrations, "apply_migrations", patched):
            code, out, err = self.aos("migrate", "apply")
        self.assertEqual(code, 1)
        self._assert_clean(out + err)

    def test_migration_event_payload_carries_no_secret_sql_or_absolute_path(self):
        migrations.apply_migrations(self.aos_dir, registry=SYNTHETIC_1_2, latest=2)
        payload = self.migrate_events()[0]
        blob = json.dumps(payload)
        self._assert_clean(blob)
        self.assertNotIn(str(self.root), blob)
        self.assertNotIn(str(Path.home()), blob)
        self.assertFalse(Path(payload["snapshot"]).is_absolute())

    def test_status_and_plan_print_no_row_values_or_sql(self):
        # A secret living in the ledger must not surface through migrate.
        code, _, _ = self.aos(
            "in", f"a capture mentioning {PLANTED_SECRET}"
        )
        for argv in (("status",), ("plan",), ("status", "--json"), ("apply",)):
            code, out, err = self.aos("migrate", *argv)
            self.assertEqual(code, 0, err)
            self._assert_clean(out + err)

    def test_planted_secret_in_a_version_value_is_not_echoed_verbatim(self):
        self.set_version_raw(PLANTED_SECRET)
        code, out, err = self.aos("migrate", "status")
        self.assertEqual(code, 1)
        # The value is secret-shaped; the diagnostic must not reprint it.
        self.assertNotIn(PLANTED_SECRET, out + err)


# ---------------------------------------------------------------------------
# 19. Script / module / zipapp parity.

class PackagingParityTest(MigrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._dist = tempfile.mkdtemp(prefix="aos-m1-pyz-")
        cls.pyz = Path(cls._dist) / "aos.pyz"
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "build_zipapp.py"),
             "-o", str(cls.pyz)],
            capture_output=True, text=True, timeout=120,
        )
        assert proc.returncode == 0, proc.stderr
        cls.outside = tempfile.mkdtemp(prefix="aos-m1-outside-")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._dist, ignore_errors=True)
        shutil.rmtree(cls.outside, ignore_errors=True)
        super().tearDownClass()

    def _clean_env(self, **overrides) -> dict:
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.update(overrides)
        return env

    def _run(self, argv, env) -> subprocess.CompletedProcess:
        return subprocess.run(
            argv, cwd=self.outside, env=env, capture_output=True,
            text=True, timeout=120,
        )

    def test_migrations_module_is_in_the_archive_via_the_allowlist(self):
        import zipfile

        with zipfile.ZipFile(self.pyz) as archive:
            members = set(archive.namelist())
        self.assertIn("agentic_os/migrations.py", members)
        # And nothing a fixture/workspace/test would drag in.
        self.assertFalse([m for m in members if m.endswith(".db")])
        self.assertFalse([m for m in members if "fixtures" in m])
        self.assertFalse([m for m in members if m.startswith("tests/")])
        self.assertFalse([m for m in members if "backups" in m])

    def test_script_module_and_zipapp_agree(self):
        # All three run against ONE workspace, so `apply` can only be
        # compared once the database is current — otherwise the first
        # entrypoint migrates it and the other two answer a different
        # question. The real 1→2 parity proof, with a fresh v1 copy per
        # entrypoint, is in tests/test_v03_memory_claims.py.
        self.migrate_to_current()
        repo_env = self._clean_env(PYTHONPATH=str(REPO_ROOT))
        clean = self._clean_env()
        root = str(self.root)
        for sub in (["status"], ["plan"], ["apply"], ["status", "--json"]):
            with self.subTest(sub=sub):
                script = self._run(
                    [sys.executable, str(REPO_ROOT / "aos.py"),
                     "--root", root, "migrate", *sub], repo_env)
                module = self._run(
                    [sys.executable, "-m", "agentic_os",
                     "--root", root, "migrate", *sub], repo_env)
                archive = self._run(
                    [sys.executable, str(self.pyz),
                     "--root", root, "migrate", *sub], clean)
                self.assertEqual(script.returncode, 0, script.stderr)
                self.assertEqual(module.stdout, script.stdout)
                self.assertEqual(archive.stdout, script.stdout)
                self.assertEqual(module.returncode, script.returncode)
                self.assertEqual(archive.returncode, script.returncode)

    def test_zipapp_noop_apply_outside_the_repo_changes_nothing(self):
        self.migrate_to_current()
        before, listing = self.db_bytes(), self.aos_listing()
        proc = self._run(
            [sys.executable, str(self.pyz), "--root", str(self.root),
             "migrate", "apply"], self._clean_env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("No migrations pending", proc.stdout)
        self.assertEqual(self.db_bytes(), before)
        self.assertEqual(self.aos_listing(), listing)

    def test_zipapp_refuses_an_unsupported_version_the_same_way(self):
        self.set_version_raw("99")
        proc = self._run(
            [sys.executable, str(self.pyz), "--root", str(self.root),
             "migrate", "status"], self._clean_env())
        self.assertEqual(proc.returncode, 1)
        self.assertIn("newer than this build supports", proc.stderr)
        self.assertEqual(self.version(), "99")


# ---------------------------------------------------------------------------
# 20. The rest of the system is untouched.

def _table_info(db_path: Path, table: str) -> list:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(f"PRAGMA table_info({table})").fetchall()
    finally:
        conn.close()


class NoRegressionTest(MigrationTestCase):
    def setUp(self):
        super().setUp()
        pristine = self.fresh_v1_copy()
        self.pristine_root = pristine
        self.pristine_aos_dir = pristine / utils.AOS_DIR_NAME
        self.pristine_db_path = self.pristine_aos_dir / utils.DB_FILENAME
        # These tests are about backup, doctor and the rest of the CLI — none
        # of which opens a database this build does not support. The fixture
        # is v1 by design, so bring it current first and let each test make
        # its own point.
        self.migrate_to_current()

    def test_backup_create_still_emits_its_event_after_the_refactor(self):
        conn = db.open_db(self.aos_dir)
        try:
            result = backup.create_backup(conn, self.aos_dir)
            rows = conn.execute(
                "SELECT payload_json FROM events WHERE action = 'backup_create'"
            ).fetchall()
        finally:
            conn.close()
        self.assertEqual(len(rows), 1)
        payload = json.loads(rows[0][0])
        self.assertEqual(payload["filename"], result["path"].name)
        self.assertEqual(payload["sha256"], result["manifest"]["sha256"])
        self.assertEqual(payload["schema_version"], db.SCHEMA_VERSION)

    def test_write_backup_pair_writes_files_but_no_event(self):
        conn = db.open_db(self.aos_dir)
        try:
            before = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            result = backup.write_backup_pair(conn, self.aos_dir)
            after = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(after, before)
        self.assertTrue(result["path"].is_file())
        self.assertTrue(result["manifest_path"].is_file())
        self.assertTrue(all(c.ok for c in backup.verify_backup(result["path"])))

    def test_verify_backup_default_still_means_this_build(self):
        conn = db.open_db(self.aos_dir)
        try:
            result = backup.create_backup(conn, self.aos_dir)
        finally:
            conn.close()
        checks = backup.verify_backup(result["path"])
        self.assertTrue(all(c.ok for c in checks))
        named = [c for c in checks if c.name == "schema_version supported"]
        self.assertEqual(len(named), 1)
        self.assertEqual(named[0].detail, db.SCHEMA_VERSION)

    def test_verify_backup_expected_version_is_load_bearing(self):
        # The line that made U-M2 possible, now load-bearing for real: a v1
        # pre-migration snapshot must verify against v1 and FAIL against 2.
        # This one needs the fixture as it was born, so it snapshots the
        # pristine v1 copy from the class fixture rather than the migrated
        # workspace this class sets up.
        snapshot = migrations.apply_migrations(self.pristine_aos_dir)["snapshot"]
        ok = backup.verify_backup(snapshot, expected_schema_version="1")
        self.assertTrue(all(c.ok for c in ok))

        bad = backup.verify_backup(snapshot, expected_schema_version="2")
        failed = [c for c in bad if not c.ok]
        self.assertEqual(len(failed), 1)
        self.assertEqual(failed[0].name, "schema_version supported")
        self.assertIn("expected '2'", failed[0].detail)

    def test_core_commands_still_work_on_the_fixture(self):
        # (The refusal on an UNMIGRATED fixture is U-M2's proof; see
        # tests/test_v03_memory_claims.py::VersionGateTest.)
        for argv in (
            ("status",), ("doctor",), ("task", "list"), ("task", "show", "T-0001"),
            ("log",), ("sync",), ("backup", "create"), ("memory", "list"),
            ("agent", "list"),
        ):
            with self.subTest(argv=argv):
                code, _, err = self.aos(*argv)
                self.assertEqual(code, 0, f"{argv}: {err}")

    def test_migrate_changed_only_what_the_step_declares(self):
        """Since U-M2 the fixture DOES migrate, so "no drift" can no longer
        mean "nothing changed". It means: the one declared table changed, no
        other core table did, and the result is the schema a fresh install
        would have built."""
        from weekend_harness import core_schema

        # self.setUp already migrated this workspace; compare against the
        # pristine v1 fixture and against a brand-new v2 workspace.
        before = core_schema(self.pristine_db_path)
        after = core_schema(self.db_path)
        self.assertEqual(set(after), set(before))
        for table, sql in before.items():
            if table == "memory":
                self.assertNotEqual(after[table], sql)
                continue
            self.assertEqual(after[table], sql, f"{table} drifted")

        fresh_root = Path(tempfile.mkdtemp(prefix="aos-m1-fresh-"))
        self.addCleanup(shutil.rmtree, fresh_root, True)
        conn, _ = db.init_db(
            fresh_root / utils.AOS_DIR_NAME / utils.DB_FILENAME
        )
        conn.close()
        fresh = core_schema(fresh_root / utils.AOS_DIR_NAME / utils.DB_FILENAME)
        self.assertEqual(
            [tuple(r) for r in _table_info(self.db_path, "memory")],
            [tuple(r) for r in _table_info(
                fresh_root / utils.AOS_DIR_NAME / utils.DB_FILENAME, "memory"
            )],
        )
        self.assertEqual(set(fresh), set(after))

    def test_help_lists_migrate(self):
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "aos.py"), "--help"],
            capture_output=True, text=True, timeout=60,
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("migrate", proc.stdout)


if __name__ == "__main__":
    unittest.main()
