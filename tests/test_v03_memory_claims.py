"""U-M2 typed memory claims and curation state
(agentic-os-v0.3-u-m2-memory-claims-contract.md).

Two kinds of proof live here:

- MIGRATION proofs run against the real historical v1 fixture
  (tests/fixtures/v1_workspace.py), copied to a temp workspace, and drive the
  PRODUCTION registry — this is the first unit where that registry is not
  empty, so no synthetic step is needed or wanted.
- CLAIM proofs run against a fresh v2 workspace through the CLI.

Nothing here touches a real ledger: every workspace is a temp directory.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fixtures.v1_workspace import build_v1_workspace, table_contents
from weekend_harness import run_cli

from agentic_os import backup, db, migrations, models, ops, power, utils
from agentic_os.utils import AosError

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Planted where a careless implementation would echo it back out: a claim
#: body, a key and a source that all look like credentials (U-C3).
FAKE_SECRET = "sk-live-m2planted00000000000000000000000000000000"  # noqa: S105


# ---------------------------------------------------------------------------
# Bases

class V1FixtureTestCase(unittest.TestCase):
    """A disposable copy of the historical v1 fixture workspace."""

    _fixture_root: Path | None = None

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.mkdtemp(prefix="aos-m2-fixture-")
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


class V2WorkspaceTestCase(unittest.TestCase):
    """A fresh v2 workspace with one project and one task carrying evidence."""

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

    def add_memory(self, *extra: str, key="storage", value="sqlite only") -> str:
        return self.ok(
            "memory", "add", "--scope", "project", "--project", "demo",
            "--kind", "constraint", "--key", key, "--value", value,
            "--source", "human", "--confidence", "confirmed", *extra,
        ).strip()

    def show(self, memory_hid: str) -> dict:
        return json.loads(self.ok("memory", "show", memory_hid, "--json"))

    def listing(self, *extra: str) -> list[dict]:
        return json.loads(self.ok("memory", "list", "--json", *extra))["memories"]

    def query(self, sql: str, params=()) -> list[sqlite3.Row]:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def write(self, sql: str, params=()) -> None:
        """Tamper directly with the ledger — the thing the hash exists to
        catch. Deliberately bypasses every ops-layer guard."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    def memory_events(self) -> list[dict]:
        return [
            {"action": row["action"], "payload": json.loads(row["payload_json"])}
            for row in self.query(
                "SELECT action, payload_json FROM events WHERE entity='memory' "
                "ORDER BY id"
            )
        ]

    def pack_memory_section(self) -> str:
        self.ok("pack", "build", "T-0001", "--for", "claude-code")
        path = self.query("SELECT path FROM packs ORDER BY id DESC LIMIT 1")[0][0]
        text = (self.aos_dir / path).read_text(encoding="utf-8")
        return text.split("## MEMORY")[1].split("## ")[0]


# ---------------------------------------------------------------------------
# 1/2. Schema version 2 and the production registry

class SchemaVersionTest(V2WorkspaceTestCase):
    def test_fresh_init_creates_the_current_schema_version(self):
        """(1) U-M3 moved the current version to 3. What U-M2 pins here is
        that a fresh workspace is born AT it, whatever it is — the literal
        lives in db.py and is asserted against 3 in the U-M3 suite."""
        self.assertEqual(db.SCHEMA_VERSION, "4")
        self.assertEqual(self.query(
            "SELECT value FROM meta WHERE key='schema_version'"
        )[0][0], db.SCHEMA_VERSION)

    def test_fresh_init_never_migrates(self):
        """(1) A new workspace is BORN current — no migration event, nothing
        pending."""
        self.assertEqual(
            self.query(
                "SELECT COUNT(*) FROM events WHERE entity='system' "
                "AND action='migrate'"
            )[0][0],
            0,
        )
        report = migrations.status(self.db_path)
        self.assertFalse(report["pending"])

    def test_fresh_memory_table_shape(self):
        """(1/16) Every v1 column survives; U-M2 added exactly three, and
        U-M3 added exactly one more (`sensitivity`)."""
        columns = {
            row["name"]: row for row in self.query("PRAGMA table_info(memory)")
        }
        for legacy in (
            "id", "scope", "project_id", "kind", "key", "value_md", "source",
            "confidence", "valid_from", "valid_until", "superseded_by",
            "updated_at",
        ):
            self.assertIn(legacy, columns)
        self.assertEqual(
            set(columns) - {
                "id", "scope", "project_id", "kind", "key", "value_md",
                "source", "confidence", "valid_from", "valid_until",
                "superseded_by", "updated_at",
            },
            {"status", "pinned", "sensitivity", "content_sha256"},
        )
        self.assertEqual(columns["status"]["dflt_value"], "'live'")
        self.assertEqual(columns["pinned"]["dflt_value"], "0")
        self.assertEqual(columns["pinned"]["notnull"], 1)
        self.assertEqual(columns["content_sha256"]["notnull"], 1)
        # No default for the hash: a claim without one must be impossible.
        self.assertIsNone(columns["content_sha256"]["dflt_value"])

    def test_evidence_link_table_exists_with_its_pinned_name(self):
        """(1)"""
        self.assertIn("memory_evidence", self.table_names())
        columns = [row["name"] for row in self.query(
            "PRAGMA table_info(memory_evidence)"
        )]
        self.assertEqual(columns, ["memory_id", "evidence_id", "created_at"])

    def table_names(self) -> set[str]:
        return {
            row[0]
            for row in self.query("SELECT name FROM sqlite_master WHERE type='table'")
        }


class ProductionRegistryTest(unittest.TestCase):
    def test_registry_still_holds_the_one_to_two_migration_first(self):
        """(2) U-M3 appended a second step; U-M2's remains the FIRST, with
        its identifier unchanged. A shipped migration id is a permanent
        fact — renaming one would orphan every database that ran it."""
        step = migrations.MIGRATIONS[0]
        self.assertEqual(
            (step.from_version, step.to_version, step.migration_id),
            (1, 2, "u-m2-memory-claims-v2"),
        )
        migrations.validate_registry()

    def test_latest_version_still_derives_from_the_schema(self):
        """(2) One declaration; a bump cannot land in only one place."""
        self.assertEqual(migrations.LATEST_VERSION, int(db.SCHEMA_VERSION))

    def test_the_one_to_two_step_is_the_only_thing_targeting_version_two(self):
        """(2) U-M2 adds ONE production step. Whatever later units append,
        exactly one migration may target version 2."""
        self.assertEqual(
            [m.migration_id for m in migrations.MIGRATIONS if m.to_version == 2],
            ["u-m2-memory-claims-v2"],
        )


# ---------------------------------------------------------------------------
# 3/4/5. Status, plan, and snapshot-before-mutation

class StatusAndPlanTest(V1FixtureTestCase):
    def test_v1_fixture_reports_the_one_to_two_step_first(self):
        """(3) The v1 fixture is two steps behind since U-M3, and the U-M2
        step is still the FIRST thing that runs on it."""
        report = migrations.status(self.db_path)
        self.assertEqual(report["current_version"], 1)
        self.assertEqual(report["latest_version"], int(db.SCHEMA_VERSION))
        self.assertTrue(report["pending"])
        self.assertEqual(
            report["plan"][0],
            {"from": 1, "to": 2, "migration_id": "u-m2-memory-claims-v2"},
        )

    def test_plan_is_read_only_and_shows_one_to_two(self):
        """(4)"""
        before = self.db_path.read_bytes()
        listing_before = sorted(
            p.relative_to(self.aos_dir).as_posix()
            for p in self.aos_dir.rglob("*")
        )
        code, out, _ = self.aos("migrate", "plan")
        self.assertEqual(code, 0)
        self.assertIn("1 → 2  u-m2-memory-claims-v2", out)
        self.assertIn("u-m2-memory-claims-v2", out)
        self.assertEqual(self.db_path.read_bytes(), before)
        self.assertEqual(
            sorted(
                p.relative_to(self.aos_dir).as_posix()
                for p in self.aos_dir.rglob("*")
            ),
            listing_before,
        )
        self.assertEqual(self.version(), "1")

    def test_status_cli_reports_pending(self):
        """(3)"""
        code, out, _ = self.aos("migrate", "status")
        self.assertEqual(code, 0)
        self.assertIn("schema version:  1", out)
        self.assertIn(f"build supports:  {db.SCHEMA_VERSION}", out)
        self.assertIn("pending:         yes", out)


class SnapshotBeforeMutationTest(V1FixtureTestCase):
    def test_apply_snapshots_and_verifies_as_v1_before_touching_the_db(self):
        """(5) The snapshot must exist, verify AS SCHEMA 1, and still hold
        the v1 memory table — proving it was taken before the mutation, not
        after."""
        result = migrations.apply_migrations(self.aos_dir)
        snapshot = result["snapshot"]
        self.assertIsNotNone(snapshot)
        self.assertTrue(snapshot.is_file())

        checks = backup.verify_backup(snapshot, expected_schema_version="1")
        self.assertTrue(all(c.ok for c in checks), [c.detail for c in checks if not c.ok])

        conn = sqlite3.connect(snapshot)
        try:
            columns = [r[1] for r in conn.execute("PRAGMA table_info(memory)")]
            tables = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            conn.close()
        self.assertNotIn("status", columns)
        self.assertNotIn("content_sha256", columns)
        self.assertNotIn("memory_evidence", tables)

    def test_snapshot_is_verified_before_the_step_runs(self):
        """(5) If the snapshot cannot be verified, the migration must not
        have run at all."""
        real_verify = backup.verify_backup

        def failing(path, expected_schema_version=None):
            checks = real_verify(path, expected_schema_version=expected_schema_version)
            return [backup.VerifyCheck("sha256 matches", False, "planted")] + list(checks)

        with mock.patch.object(backup, "verify_backup", failing):
            with self.assertRaises(AosError) as caught:
                migrations.apply_migrations(self.aos_dir)
        self.assertIn("refusing to migrate", str(caught.exception))
        self.assertEqual(self.version(), "1")
        self.assertNotIn("memory_evidence", self.table_names())


# ---------------------------------------------------------------------------
# 6-12. Legacy preservation and mapping

class LegacyMigrationTest(V1FixtureTestCase):
    def setUp(self):
        super().setUp()
        self.before = table_contents(self.db_path)
        self.legacy_memory = {
            row["id"]: dict(row)
            for row in self.query("SELECT * FROM memory ORDER BY id")
        }
        # target=2, not "the latest": this class's SUBJECT is the 1 → 2 step,
        # and U-M3 appended a 2 → 3 that would otherwise run straight over it
        # and leave these assertions describing a v3 database. Stopping at the
        # step under test is also a real proof in its own right — each step
        # leaves a database that genuinely IS its own version. U-M3's suite
        # proves the rest of the chain.
        self.result = migrations.apply_migrations(self.aos_dir, target=2)

    def claims(self) -> dict[int, sqlite3.Row]:
        return {
            row["id"]: row
            for row in self.query("SELECT * FROM memory ORDER BY id")
        }

    def test_every_legacy_id_and_field_survives_unchanged(self):
        """(6)"""
        claims = self.claims()
        self.assertEqual(sorted(claims), sorted(self.legacy_memory))
        for memory_id, legacy in self.legacy_memory.items():
            row = claims[memory_id]
            for field in (
                "id", "scope", "project_id", "kind", "key", "value_md",
                "source", "confidence", "valid_from", "valid_until",
                "superseded_by", "updated_at",
            ):
                self.assertEqual(
                    row[field], legacy[field],
                    f"M-{memory_id:04d}.{field} was rewritten",
                )

    def test_every_other_table_is_untouched(self):
        """(6) The migration touches memory and nothing else."""
        after = table_contents(self.db_path)
        for table in ("projects", "tasks", "runs", "decisions", "evidence",
                      "handoffs", "packs", "agents"):
            self.assertEqual(after[table], self.before[table], table)

    def test_legacy_active_rows_become_live(self):
        """(7)"""
        claims = self.claims()
        self.assertEqual(claims[1]["status"], "live")   # global, no expiry
        self.assertEqual(claims[2]["status"], "live")   # project, no expiry
        self.assertEqual(claims[5]["status"], "live")   # expiry in 2099

    def test_legacy_expired_and_superseded_rows_become_retired(self):
        """(8)"""
        claims = self.claims()
        self.assertEqual(claims[3]["status"], "retired")  # valid_until 2020
        self.assertEqual(claims[4]["status"], "retired")  # superseded by M-0005
        self.assertEqual(claims[4]["superseded_by"], 5)

    def test_every_legacy_row_starts_unpinned(self):
        """(7/8)"""
        self.assertEqual(
            [row["pinned"] for row in self.claims().values()], [0] * 5
        )

    def test_no_evidence_links_are_invented(self):
        """(9)"""
        self.assertEqual(
            self.query("SELECT COUNT(*) FROM memory_evidence")[0][0], 0
        )

    def test_every_migrated_row_gets_the_correct_hash(self):
        """(10) A v2 hash, on a database stopped at v2.

        `ops.claim_integrity` computes the CURRENT payload, which is v3 since
        U-M3 — so it is the wrong oracle for a v2 row, and using it here would
        quietly prove nothing. The oracle is the frozen v2 payload the step
        itself writes with.
        """
        for row in self.query("SELECT * FROM memory ORDER BY id"):
            legacy = dict(row)
            self.assertTrue(
                models.is_claim_hash(legacy["content_sha256"]),
                f"M-{legacy['id']:04d} hash is malformed",
            )
            self.assertEqual(
                legacy["content_sha256"],
                migrations._v2_claim_digest(
                    legacy, legacy["status"], legacy["pinned"]
                ),
                f"M-{legacy['id']:04d} carries the wrong v2 hash",
            )

    def test_schema_version_advances_exactly_once(self):
        """(11)"""
        self.assertEqual(self.version(), "2")  # target=2: see setUp
        self.assertEqual(
            self.result["applied"],
            ({"from": 1, "to": 2, "migration_id": "u-m2-memory-claims-v2"},),
        )
        self.assertEqual(len(self.migrate_events()), 1)

    def test_one_privacy_safe_migration_event(self):
        """(12) The event names the step and the snapshot. It carries no row
        value, key, memory text, source or SQL."""
        events = self.migrate_events()
        self.assertEqual(len(events), 1)
        payload = events[0]
        self.assertEqual(payload["from"], 1)
        self.assertEqual(payload["to"], 2)
        self.assertEqual(payload["migration_id"], "u-m2-memory-claims-v2")
        self.assertEqual(
            set(payload), {"schema_version", "from", "to", "migration_id", "snapshot"}
        )
        blob = json.dumps(payload)
        for legacy in self.legacy_memory.values():
            self.assertNotIn(legacy["key"], blob)
            self.assertNotIn(legacy["value_md"], blob)
        self.assertNotIn("INSERT", blob.upper())
        self.assertNotIn("SELECT", blob.upper())

    def test_migrated_shape_matches_a_born_v2_table(self):
        """(11) A migrated table and a born-v2 table must be the same table,
        or the rebuild bought nothing.

        "Born v2" is now a FROZEN definition rather than `db.init_db` — v2 is
        history since U-M3, and a fresh init builds a v3 table. Comparing the
        1 → 2 step's output against anything else would be comparing it to a
        table it is not supposed to produce. (Fresh-vs-migrated identity for
        the CURRENT version is proven in the U-M3 suite, against a real
        `init_db`.)
        """
        scratch = sqlite3.connect(":memory:")
        try:
            scratch.execute(
                migrations._V2_MEMORY_CLAIM_DDL.format(table="born_v2")
            )
            scratch.execute(
                db.MEMORY_EVIDENCE_DDL.format(table="born_v2_evidence")
            )
            fresh = [
                tuple(r)[1:] for r in scratch.execute("PRAGMA table_info(born_v2)")
            ]
            fresh_links = [
                tuple(r)[1:]
                for r in scratch.execute("PRAGMA table_info(born_v2_evidence)")
            ]
        finally:
            scratch.close()
        migrated = [tuple(r)[1:] for r in self.query("PRAGMA table_info(memory)")]
        migrated_links = [
            tuple(r)[1:] for r in self.query("PRAGMA table_info(memory_evidence)")
        ]
        self.assertEqual(migrated, fresh)
        self.assertEqual(migrated_links, fresh_links)
        # And it really is the v2 shape: no U-M3 column got in.
        self.assertNotIn("sensitivity", [c[0] for c in migrated])

    def test_constraints_are_live_on_a_migrated_database(self):
        """(16) The CHECKs came across with the rebuild, not just the columns."""
        for sql, params in (
            ("UPDATE memory SET status = 'invented' WHERE id = 1", ()),
            ("UPDATE memory SET pinned = 2 WHERE id = 1", ()),
        ):
            with self.subTest(sql=sql):
                conn = sqlite3.connect(self.db_path)
                try:
                    with self.assertRaises(sqlite3.IntegrityError):
                        conn.execute(sql, params)
                finally:
                    conn.close()

    def test_migrated_claims_are_usable_immediately(self):
        """(6) The point of the migration: the CLI works on the result.

        The CLI runs against the CURRENT schema and nothing else, so this one
        finishes the chain the rest of the class deliberately stops short of.
        """
        code, _, err = self.aos("migrate", "apply")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.version(), db.SCHEMA_VERSION)
        code, out, err = self.aos("memory", "show", "M-0001", "--json")
        self.assertEqual(code, 0, err)
        doc = json.loads(out)
        self.assertEqual(doc["status"], "live")
        self.assertFalse(doc["pinned"])
        self.assertEqual(doc["evidence"], [])
        self.assertEqual(doc["integrity"], "ok")


# ---------------------------------------------------------------------------
# 13/14. Failure and retry

def _boom_after_writing(conn: sqlite3.Connection) -> None:
    """Fail INSIDE the step, after it has already written — so the rollback
    has something real to undo. Carries a planted secret and SQL text the
    error path must not echo."""
    migrations._memory_claims_v2(conn)
    raise RuntimeError(
        f"planted failure {FAKE_SECRET} while running "
        "SELECT value FROM meta WHERE key = 'schema_version'"
    )


class MigrationFailureTest(V1FixtureTestCase):
    def test_injected_failure_rolls_back_schema_and_data_completely(self):
        """(13)"""
        before = table_contents(self.db_path)
        failing = (
            migrations.Migration(1, 2, "u-m2-memory-claims-v2", _boom_after_writing),
        )
        with self.assertRaises(migrations.MigrationStepError) as caught:
            migrations.apply_migrations(self.aos_dir, registry=failing, latest=2)

        self.assertEqual(self.version(), "1")
        self.assertEqual(table_contents(self.db_path), before)
        columns = [r["name"] for r in self.query("PRAGMA table_info(memory)")]
        self.assertNotIn("status", columns)
        self.assertNotIn("memory_evidence", self.table_names())
        self.assertNotIn("memory_v2_migrating", self.table_names())
        self.assertEqual(self.migrate_events(), [])

        # The snapshot survives, verified, and the message stays clean.
        snapshot = caught.exception.snapshot
        self.assertIsNotNone(snapshot)
        self.assertTrue(snapshot.is_file())
        self.assertTrue(
            all(c.ok for c in backup.verify_backup(snapshot, expected_schema_version="1"))
        )
        message = str(caught.exception)
        self.assertNotIn(FAKE_SECRET, message)
        self.assertNotIn("SELECT", message)
        self.assertIn("rolled back completely", message)

    def test_corrected_retry_migrates_exactly_once(self):
        """(14)"""
        failing = (
            migrations.Migration(1, 2, "u-m2-memory-claims-v2", _boom_after_writing),
        )
        with self.assertRaises(migrations.MigrationStepError):
            migrations.apply_migrations(self.aos_dir, registry=failing, latest=2)
        self.assertEqual(self.version(), "1")

        result = migrations.apply_migrations(self.aos_dir, target=2)
        self.assertTrue(result["migrated"])
        self.assertEqual(self.version(), "2")  # target=2: the step under test
        self.assertEqual(len(self.migrate_events()), 1)
        self.assertEqual(len(self.query("SELECT id FROM memory")), 5)

        # And a second apply is a no-op: exactly once, not once per attempt.
        again = migrations.apply_migrations(self.aos_dir, target=2)
        self.assertFalse(again["migrated"])
        self.assertIsNone(again["snapshot"])
        self.assertEqual(len(self.migrate_events()), 1)


# ---------------------------------------------------------------------------
# 15. Normal commands refuse an unmigrated database

class VersionGateTest(V1FixtureTestCase):
    NORMAL = (
        ("status",), ("doctor",), ("task", "list"), ("sync",),
        ("memory", "list"), ("memory", "show", "M-0001"),
        ("memory", "pin", "M-0001"), ("memory", "unpin", "M-0001"),
        ("memory", "link-evidence", "M-0001", "E-0001"),
        ("memory", "retire", "M-0001"),
        ("memory", "add", "--scope", "global", "--kind", "fact", "--key", "k",
         "--value", "v", "--source", "human", "--confidence", "confirmed"),
        ("pack", "build", "T-0001", "--for", "claude-code"),
        ("log",), ("search", "anything"),
    )

    def test_normal_commands_refuse_a_v1_database(self):
        """(15)"""
        for argv in self.NORMAL:
            with self.subTest(argv=argv):
                code, out, err = self.aos(*argv)
                self.assertEqual(code, 1, f"{argv} did not refuse: {out}")
                self.assertIn("schema_version is '1'", err)
                self.assertIn("never auto-migrate", err)
                self.assertIn("migrate status", err)
                self.assertIn("migrate plan", err)
                self.assertIn("migrate apply", err)

    def test_refusal_changes_nothing(self):
        """(15) A refusal is not a mutation."""
        before = self.db_path.read_bytes()
        for argv in self.NORMAL:
            self.aos(*argv)
        self.assertEqual(self.db_path.read_bytes(), before)
        self.assertEqual(self.version(), "1")

    def test_only_migration_commands_may_open_the_older_schema(self):
        """(15)"""
        for argv in (("migrate", "status"), ("migrate", "plan")):
            with self.subTest(argv=argv):
                self.assertEqual(self.aos(*argv)[0], 0)

    def test_the_same_commands_work_after_migrating(self):
        """(15) The gate is a door, not a wall."""
        self.assertEqual(self.aos("migrate", "apply")[0], 0)
        for argv in (("status",), ("doctor",), ("memory", "list"),
                     ("memory", "show", "M-0001"), ("sync",)):
            with self.subTest(argv=argv):
                code, _, err = self.aos(*argv)
                self.assertEqual(code, 0, f"{argv}: {err}")


# ---------------------------------------------------------------------------
# 16/17. Constraints and defaults

class ConstraintTest(V2WorkspaceTestCase):
    def test_status_vocabulary_is_enforced_by_the_schema(self):
        """(16)"""
        self.add_memory()
        for value in ("invented", "LIVE", "", "live "):
            with self.subTest(value=value):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.write(
                        "UPDATE memory SET status = ? WHERE id = 1", (value,)
                    )

    def test_every_declared_status_is_storable(self):
        """(16) The vocabulary is exactly the five names."""
        self.add_memory()
        self.assertEqual(
            models.MEMORY_STATUSES,
            ("proposed", "live", "contested", "quarantined", "retired"),
        )
        for value in models.MEMORY_STATUSES:
            with self.subTest(value=value):
                self.write("UPDATE memory SET status = ? WHERE id = 1", (value,))

    def test_pinned_accepts_only_zero_and_one(self):
        """(16)"""
        self.add_memory()
        for value in (2, -1, "yes", None):
            with self.subTest(value=value):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.write("UPDATE memory SET pinned = ? WHERE id = 1", (value,))
        for value in (0, 1):
            self.write("UPDATE memory SET pinned = ? WHERE id = 1", (value,))

    def test_new_human_memory_defaults_to_live_and_unpinned(self):
        """(17)"""
        hid = self.add_memory()
        self.assertEqual(hid, "M-0001")
        doc = self.show(hid)
        self.assertEqual(doc["status"], "live")
        self.assertFalse(doc["pinned"])
        self.assertTrue(doc["live"])
        self.assertEqual(doc["evidence"], [])
        self.assertEqual(doc["integrity"], "ok")

    def test_duplicate_links_are_impossible_at_the_storage_layer(self):
        """(19)"""
        self.add_memory()
        self.write(
            "INSERT INTO memory_evidence (memory_id, evidence_id, created_at) "
            "VALUES (1, 1, '2026-01-01T00:00:00Z')"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.write(
                "INSERT INTO memory_evidence (memory_id, evidence_id, created_at) "
                "VALUES (1, 1, '2026-01-02T00:00:00Z')"
            )

    def test_link_table_carries_no_evidence_text(self):
        """(M2.2) Two ids and a timestamp. Nothing else can live here."""
        self.add_memory("--evidence", "E-0001")
        row = self.query("SELECT * FROM memory_evidence")[0]
        self.assertEqual(set(row.keys()), {"memory_id", "evidence_id", "created_at"})
        self.assertEqual(row["memory_id"], 1)
        self.assertEqual(row["evidence_id"], 1)

    def test_linked_rows_cannot_be_deleted_out_from_under_a_claim(self):
        """(M2.2) Existing deletion behavior: REFUSE, like every other FK."""
        self.add_memory("--evidence", "E-0001")
        conn = db.connect(self.db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM evidence WHERE id = 1")
                conn.commit()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 18-23. The claim commands

class AddWithPinAndEvidenceTest(V2WorkspaceTestCase):
    def test_add_with_pin_and_evidence_is_transactional(self):
        """(18)"""
        hid = self.add_memory("--pin", "--evidence", "E-0001")
        doc = self.show(hid)
        self.assertTrue(doc["pinned"])
        self.assertEqual(doc["evidence"], ["E-0001"])
        self.assertEqual(doc["integrity"], "ok")
        self.assertEqual(
            self.query("SELECT COUNT(*) FROM memory_evidence")[0][0], 1
        )

    def test_add_rolls_back_row_link_and_event_together(self):
        """(18) One transaction: if the event fails, the claim and its link
        never existed."""
        with mock.patch.object(
            ops.events, "emit", side_effect=RuntimeError("planted")
        ):
            with self.assertRaises(RuntimeError):
                conn = db.open_db(self.aos_dir)
                try:
                    ops.add_memory(
                        conn, scope="project", project_slug="demo",
                        kind="fact", key="k", value="v", source="human",
                        confidence="confirmed", pin=True, evidence_ids=[1],
                    )
                finally:
                    conn.close()
        self.assertEqual(self.query("SELECT COUNT(*) FROM memory")[0][0], 0)
        self.assertEqual(
            self.query("SELECT COUNT(*) FROM memory_evidence")[0][0], 0
        )

    def test_repeatable_evidence_is_deterministic(self):
        """(18/19) Order and duplicates cannot change the stored rows or the
        hash."""
        self.ok(
            "evidence", "add", "T-0001", "--kind", "note", "--ref", "second",
        )
        first = self.add_memory(
            "--evidence", "E-0002", "--evidence", "E-0001",
            "--evidence", "E-0002", key="a",
        )
        second = self.add_memory("--evidence", "E-0001", "--evidence", "E-0002", key="b")
        self.assertEqual(self.show(first)["evidence"], ["E-0001", "E-0002"])
        self.assertEqual(self.show(second)["evidence"], ["E-0001", "E-0002"])

    def test_add_pin_refuses_an_already_expired_claim(self):
        """(18) Pinning an unreachable claim is a lie, so it is refused —
        before anything is written."""
        _, err = self.fails(
            "memory", "add", "--scope", "global", "--kind", "fact",
            "--key", "k", "--value", "v", "--source", "human",
            "--confidence", "confirmed", "--valid-until", "2000-01-01", "--pin",
        )
        self.assertIn("already expired", err)
        self.assertEqual(self.query("SELECT COUNT(*) FROM memory")[0][0], 0)

    def test_missing_evidence_refuses_and_writes_nothing(self):
        """(20)"""
        _, err = self.fails("memory", "add", "--scope", "global", "--kind",
                            "fact", "--key", "k", "--value", "v", "--source",
                            "human", "--confidence", "confirmed",
                            "--evidence", "E-0404")
        self.assertIn("No evidence E-0404", err)
        self.assertEqual(self.query("SELECT COUNT(*) FROM memory")[0][0], 0)

    def test_cross_project_evidence_refuses_unchanged(self):
        """(20)"""
        self.ok("task", "add", "Other task", "-p", "other")
        self.ok("evidence", "add", "T-0002", "--kind", "note", "--ref", "elsewhere")
        _, err = self.fails(
            "memory", "add", "--scope", "project", "--project", "demo",
            "--kind", "fact", "--key", "k", "--value", "v",
            "--source", "human", "--confidence", "confirmed",
            "--evidence", "E-0002",
        )
        self.assertIn("must not name different projects", err)
        self.assertEqual(self.query("SELECT COUNT(*) FROM memory")[0][0], 0)

    def test_global_claims_may_cite_project_evidence(self):
        """(20) A NULL on either side is COMPATIBLE, not a violation."""
        hid = self.ok(
            "memory", "add", "--scope", "global", "--kind", "fact",
            "--key", "k", "--value", "v", "--source", "human",
            "--confidence", "confirmed", "--evidence", "E-0001",
        ).strip()
        self.assertEqual(self.show(hid)["evidence"], ["E-0001"])


class LinkEvidenceTest(V2WorkspaceTestCase):
    def test_link_updates_hash_and_emits_one_event_in_one_transaction(self):
        """(18)"""
        hid = self.add_memory()
        before = self.show(hid)["content_sha256"]
        out = self.ok("memory", "link-evidence", hid, "E-0001")
        self.assertIn("E-0001", out)
        doc = self.show(hid)
        self.assertEqual(doc["evidence"], ["E-0001"])
        self.assertNotEqual(doc["content_sha256"], before)
        self.assertEqual(doc["integrity"], "ok")
        actions = [e["action"] for e in self.memory_events()]
        self.assertEqual(actions, ["add", "link_evidence"])

    def test_duplicate_linking_is_an_idempotent_no_op(self):
        """(19)"""
        hid = self.add_memory()
        self.ok("memory", "link-evidence", hid, "E-0001")
        after_first = self.show(hid)
        out = self.ok("memory", "link-evidence", hid, "E-0001")
        self.assertIn("already linked", out)
        self.assertEqual(self.show(hid), after_first)  # hash and updated_at too
        self.assertEqual(
            self.query("SELECT COUNT(*) FROM memory_evidence")[0][0], 1
        )
        self.assertEqual(
            [e["action"] for e in self.memory_events()], ["add", "link_evidence"]
        )

    def test_missing_rows_refuse(self):
        """(20)"""
        hid = self.add_memory()
        _, err = self.fails("memory", "link-evidence", hid, "E-0404")
        self.assertIn("No evidence E-0404", err)
        _, err = self.fails("memory", "link-evidence", "M-0404", "E-0001")
        self.assertIn("No memory M-0404", err)
        self.assertEqual(
            self.query("SELECT COUNT(*) FROM memory_evidence")[0][0], 0
        )

    def test_cross_project_link_refuses_unchanged(self):
        """(20)"""
        self.ok("task", "add", "Other task", "-p", "other")
        self.ok("evidence", "add", "T-0002", "--kind", "note", "--ref", "elsewhere")
        hid = self.add_memory()
        before = self.show(hid)
        _, err = self.fails("memory", "link-evidence", hid, "E-0002")
        self.assertIn("must not name different projects", err)
        self.assertEqual(self.show(hid), before)
        self.assertEqual(
            self.query("SELECT COUNT(*) FROM memory_evidence")[0][0], 0
        )

    def test_link_event_carries_no_claim_or_evidence_text(self):
        """(M2.9)"""
        hid = self.add_memory()
        self.ok("memory", "link-evidence", hid, "E-0001")
        payload = self.memory_events()[-1]["payload"]
        self.assertEqual(
            set(payload),
            {"schema_version", "memory", "evidence", "evidence_count", "hash_prefix"},
        )
        self.assertEqual(payload["memory"], "M-0001")
        self.assertEqual(payload["evidence"], "E-0001")
        self.assertEqual(payload["evidence_count"], 1)


class PinTest(V2WorkspaceTestCase):
    def test_pin_and_unpin_are_authoritative_and_hash_consistent(self):
        """(21)"""
        hid = self.add_memory()
        before = self.show(hid)["content_sha256"]
        self.ok("memory", "pin", hid)
        pinned = self.show(hid)
        self.assertTrue(pinned["pinned"])
        self.assertNotEqual(pinned["content_sha256"], before)
        self.assertEqual(pinned["integrity"], "ok")

        self.ok("memory", "unpin", hid)
        unpinned = self.show(hid)
        self.assertFalse(unpinned["pinned"])
        self.assertEqual(unpinned["integrity"], "ok")
        self.assertNotEqual(unpinned["content_sha256"], pinned["content_sha256"])

    def test_same_state_pin_is_idempotent_and_emits_no_event(self):
        """(21) An audit journal that records non-events is one you stop
        trusting."""
        hid = self.add_memory()
        self.ok("memory", "pin", hid)
        after = self.show(hid)
        events_before = self.memory_events()

        out = self.ok("memory", "pin", hid)
        self.assertIn("already pinned", out)
        self.assertEqual(self.show(hid), after)  # hash and updated_at untouched
        self.assertEqual(self.memory_events(), events_before)

        out = self.ok("memory", "unpin", "M-0001")
        self.ok("memory", "unpin", "M-0001")
        actions = [e["action"] for e in self.memory_events()]
        self.assertEqual(actions, ["add", "pin", "unpin"])

    def test_pin_refuses_retired_expired_and_superseded_claims(self):
        """(21) Pinned never overrides lifecycle."""
        retired = self.add_memory(key="retire-me")
        self.ok("memory", "retire", retired)
        _, err = self.fails("memory", "pin", retired)
        self.assertIn("not eligible for normal retrieval", err)
        self.assertIn("status retired", err)

        expired = self.add_memory("--valid-until", "2000-01-01", key="expired")
        _, err = self.fails("memory", "pin", expired)
        self.assertIn("not eligible", err)

        old = self.add_memory(key="superseded", value="old")
        self.add_memory("--supersedes", old, key="superseded", value="new")
        _, err = self.fails("memory", "pin", old)
        self.assertIn("not eligible", err)

        self.assertEqual(
            [row["pinned"] for row in self.query("SELECT pinned FROM memory")],
            [0, 0, 0, 0],
        )

    def test_pin_events_name_the_transition_only(self):
        """(M2.9)"""
        hid = self.add_memory()
        self.ok("memory", "pin", hid)
        payload = self.memory_events()[-1]["payload"]
        self.assertEqual(
            set(payload),
            {"schema_version", "memory", "pinned", "from_pinned", "hash_prefix"},
        )
        self.assertTrue(payload["pinned"])
        self.assertFalse(payload["from_pinned"])
        self.assertEqual(len(payload["hash_prefix"]), models.HASH_PREFIX_CHARS)


class RetireAndSupersedeTest(V2WorkspaceTestCase):
    def test_retire_updates_status_validity_and_hash_atomically(self):
        """(22)"""
        hid = self.add_memory()
        before = self.show(hid)["content_sha256"]
        self.ok("memory", "retire", hid)
        doc = self.show(hid)
        self.assertEqual(doc["status"], "retired")
        self.assertIsNotNone(doc["valid_until"])
        self.assertFalse(doc["live"])
        self.assertNotEqual(doc["content_sha256"], before)
        self.assertEqual(doc["integrity"], "ok")

    def test_retire_keeps_the_row_and_its_links(self):
        """(22) Retiring is a curation decision, not a delete."""
        hid = self.add_memory("--evidence", "E-0001")
        self.ok("memory", "retire", hid)
        self.assertEqual(len(self.listing()), 1)
        self.assertEqual(self.show(hid)["evidence"], ["E-0001"])
        self.assertEqual(
            self.query("SELECT COUNT(*) FROM memory_evidence")[0][0], 1
        )

    def test_double_retire_still_refuses(self):
        """(22) Preserved behavior."""
        hid = self.add_memory()
        self.ok("memory", "retire", hid)
        _, err = self.fails("memory", "retire", hid)
        self.assertIn("already retired", err)

    def test_superseding_retires_the_prior_claim_atomically(self):
        """(23)"""
        old = self.add_memory(key="storage", value="old value")
        old_hash = self.show(old)["content_sha256"]
        new = self.add_memory("--supersedes", old, key="storage", value="new value")

        old_doc = self.show(old)
        self.assertEqual(old_doc["status"], "retired")
        self.assertEqual(old_doc["superseded_by"], new)
        self.assertFalse(old_doc["live"])
        # The superseded claim's status and pointer are BOUND: its hash had to
        # move with them, in the same transaction.
        self.assertNotEqual(old_doc["content_sha256"], old_hash)
        self.assertEqual(old_doc["integrity"], "ok")

        new_doc = self.show(new)
        self.assertEqual(new_doc["status"], "live")
        self.assertTrue(new_doc["live"])
        self.assertEqual(new_doc["integrity"], "ok")

    def test_supersede_rolls_back_both_claims_together(self):
        """(23)"""
        old = self.add_memory(key="storage", value="old value")
        before = self.show(old)
        with mock.patch.object(
            ops.events, "emit", side_effect=RuntimeError("planted")
        ):
            with self.assertRaises(RuntimeError):
                conn = db.open_db(self.aos_dir)
                try:
                    ops.add_memory(
                        conn, scope="project", project_slug="demo",
                        kind="constraint", key="storage", value="new",
                        source="human", confidence="confirmed",
                        supersedes_id=1,
                    )
                finally:
                    conn.close()
        self.assertEqual(self.show(old), before)
        self.assertEqual(len(self.listing()), 1)


class ShowAndListTest(V2WorkspaceTestCase):
    def test_show_reports_status_pin_hash_and_evidence(self):
        """(M2.8)"""
        hid = self.add_memory("--pin", "--evidence", "E-0001")
        out = self.ok("memory", "show", hid)
        self.assertIn("status:     live", out)
        self.assertIn("pinned:     yes", out)
        self.assertIn("evidence:   E-0001", out)
        self.assertIn("(ok)", out)
        doc = self.show(hid)
        self.assertEqual(doc["id"], hid)
        self.assertTrue(models.is_claim_hash(doc["content_sha256"]))

    def test_show_never_prints_evidence_claim_bodies(self):
        """(M2.8) Evidence is named by id. Its claim text is not shown."""
        self.ok(
            "evidence", "add", "T-0001", "--kind", "note",
            "--ref", "secret-ref-value", "--claim", "secret-claim-body",
        )
        hid = self.add_memory("--evidence", "E-0002")
        out = self.ok("memory", "show", hid)
        self.assertIn("E-0002", out)
        self.assertNotIn("secret-claim-body", out)
        self.assertNotIn("secret-ref-value", out)
        doc = self.show(hid)
        self.assertNotIn("secret-claim-body", json.dumps(doc))

    def test_show_is_read_only(self):
        """(M2.8)"""
        hid = self.add_memory()
        before = self.db_path.read_bytes()
        events_before = self.memory_events()
        self.ok("memory", "show", hid)
        self.ok("memory", "show", hid, "--json")
        self.assertEqual(self.db_path.read_bytes(), before)
        self.assertEqual(self.memory_events(), events_before)

    def test_list_still_shows_history_by_default(self):
        """(M2.8) Memory never silently disappears."""
        self.add_memory(key="keep")
        self.add_memory(key="gone")
        self.ok("memory", "retire", "M-0002")
        self.assertEqual([m["id"] for m in self.listing()], ["M-0001", "M-0002"])
        out = self.ok("memory", "list")
        self.assertIn("live", out)
        self.assertIn("retired", out)

    def test_list_json_exposes_status_pin_evidence_and_hash(self):
        """(M2.8)"""
        self.add_memory("--pin", "--evidence", "E-0001")
        item = self.listing()[0]
        self.assertEqual(item["status"], "live")
        self.assertTrue(item["pinned"])
        self.assertEqual(item["evidence"], ["E-0001"])
        self.assertTrue(models.is_claim_hash(item["content_sha256"]))

    def test_list_filters_by_status_and_pin(self):
        """(M2.8)"""
        self.add_memory(key="pinned-live")
        self.ok("memory", "pin", "M-0001")
        self.add_memory(key="plain")
        self.add_memory(key="retired")
        self.ok("memory", "retire", "M-0003")

        self.assertEqual(
            [m["id"] for m in self.listing("--status", "live")],
            ["M-0001", "M-0002"],
        )
        self.assertEqual(
            [m["id"] for m in self.listing("--status", "retired")], ["M-0003"]
        )
        self.assertEqual([m["id"] for m in self.listing("--pinned")], ["M-0001"])
        self.assertEqual(
            [m["id"] for m in self.listing("--unpinned")], ["M-0002", "M-0003"]
        )
        _, err = self.fails("memory", "list", "--status", "invented")
        self.assertIn("invalid choice", err)

    def test_list_does_not_hide_a_damaged_claim(self):
        """(M2.8) An invalid row is exactly what an operator came to find."""
        self.add_memory()
        self.write("UPDATE memory SET content_sha256 = 'nope' WHERE id = 1")
        self.assertEqual([m["id"] for m in self.listing()], ["M-0001"])
        self.assertEqual(self.show("M-0001")["integrity"], "malformed")

    def test_no_command_accepts_an_arbitrary_status(self):
        """(M2.8) U-M2 ships no way to set proposed/contested/quarantined."""
        from agentic_os import cli

        leaves = {
            path[1]
            for path in power.iter_command_paths(cli.build_parser())
            if path and path[0] == "memory"
        }
        # U-M2's own leaves, still exactly these. U-M3 added more (classify,
        # source, edge, graph, contradictions) and none of them sets a status
        # either — the assertion below is what actually pins that.
        self.assertLessEqual(
            {"add", "list", "show", "pin", "unpin", "link-evidence", "retire"},
            leaves,
        )
        for argv in (
            ("memory", "add", "--status", "quarantined"),
            ("memory", "show", "M-0001", "--status", "live"),
            ("memory", "retire", "M-0001", "--status", "live"),
        ):
            with self.subTest(argv=argv):
                self.assertEqual(self.aos(*argv)[0], 1)


# ---------------------------------------------------------------------------
# 24-26. Retrieval

class RetrievalTest(V2WorkspaceTestCase):
    def _set_status(self, memory_id: int, status: str) -> None:
        """Reach past the CLI: U-M2 deliberately ships no command that
        produces proposed/contested/quarantined, but retrieval must already
        exclude them."""
        conn = db.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE memory SET status = ? WHERE id = ?", (status, memory_id)
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM memory WHERE id = ?", (memory_id,)
            ).fetchone()
            conn.row_factory = sqlite3.Row
            item = models.MemoryItem.from_row(
                conn.execute(
                    "SELECT * FROM memory WHERE id = ?", (memory_id,)
                ).fetchone()
            )
            conn.execute(
                "UPDATE memory SET content_sha256 = ? WHERE id = ?",
                (ops.claim_digest(conn, item), memory_id),
            )
            conn.commit()
        finally:
            conn.close()

    def test_non_live_statuses_never_enter_packs(self):
        """(24)"""
        for index, status in enumerate(
            ("proposed", "contested", "quarantined", "retired"), start=1
        ):
            self.add_memory(key=f"k-{status}", value=f"{status} body text")
            self._set_status(index, status)
        self.add_memory(key="live-one", value="live body text")

        section = self.pack_memory_section()
        self.assertIn("live body text", section)
        for status in ("proposed", "contested", "quarantined", "retired"):
            self.assertNotIn(f"{status} body text", section)

    def test_quarantined_claims_stay_out_of_derived_context(self):
        """(24)"""
        self.add_memory(key="q", value="quarantined body text")
        self._set_status(1, "quarantined")
        self.ok("sync")
        home = (self.aos_dir / "AOS" / "Home.md")
        self.assertNotIn("quarantined body text", self.pack_memory_section())
        if home.is_file():
            self.assertNotIn("quarantined body text", home.read_text())

    def test_expired_and_superseded_claims_never_enter_packs(self):
        """(25) The v1 rules still hold on top of status."""
        self.add_memory(key="keep", value="live row stays")
        self.add_memory(key="retire-me", value="retired row goes")
        self.ok("memory", "retire", "M-0002")
        self.add_memory(key="superseded", value="old superseded value")
        self.add_memory(
            "--supersedes", "M-0003", key="superseded",
            value="winning successor value",
        )
        self.add_memory(
            "--valid-until", "2000-01-01", key="expired", value="expired row goes"
        )
        section = self.pack_memory_section()
        self.assertIn("keep: live row stays", section)
        self.assertIn("superseded: winning successor value", section)
        self.assertNotIn("retired row goes", section)
        self.assertNotIn("old superseded value", section)
        self.assertNotIn("expired row goes", section)
        self.assertEqual(len(self.listing()), 5)  # none of them vanished

    def test_pinned_eligible_claims_sort_before_unpinned(self):
        """(26)"""
        self.add_memory(key="aaa-first-alphabetically", value="unpinned A")
        self.add_memory(key="zzz-last-alphabetically", value="pinned Z")
        self.ok("memory", "pin", "M-0002")
        section = self.pack_memory_section()
        pinned_at = section.index("pinned Z")
        unpinned_at = section.index("unpinned A")
        self.assertLess(
            pinned_at, unpinned_at,
            "pinned claims must lead, even against the stable key ordering",
        )

    def test_ordering_inside_each_group_is_unchanged(self):
        """(26) Pinning changes the group, never the order within it."""
        for key in ("b-key", "a-key", "c-key"):
            self.add_memory(key=key, value=f"value for {key}")
        conn = db.open_db(self.aos_dir)
        try:
            items = ops.memory_for_project(conn, 1)
        finally:
            conn.close()
        self.assertEqual([i.key for i in items], ["a-key", "b-key", "c-key"])

    def test_pinning_never_resurrects_an_ineligible_claim(self):
        """(26/M2.7) Pin is ordering; it is not permission."""
        self.add_memory(key="k", value="pinned then retired")
        self.ok("memory", "pin", "M-0001")
        self.ok("memory", "retire", "M-0001")
        self.assertTrue(self.show("M-0001")["pinned"])
        self.assertNotIn("pinned then retired", self.pack_memory_section())


# ---------------------------------------------------------------------------
# 27/28. Tamper detection

class TamperTest(V2WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.hid = self.add_memory("--evidence", "E-0001")

    def integrity(self) -> str:
        return self.show(self.hid)["integrity"]

    def test_tampering_with_any_bound_field_fails_the_hash(self):
        """(27)"""
        cases = {
            "scope": "UPDATE memory SET scope = 'global' WHERE id = 1",
            "kind": "UPDATE memory SET kind = 'fact' WHERE id = 1",
            "key": "UPDATE memory SET key = 'other' WHERE id = 1",
            "value_md": "UPDATE memory SET value_md = 'rewritten' WHERE id = 1",
            "source": "UPDATE memory SET source = 'agent:x' WHERE id = 1",
            "confidence": "UPDATE memory SET confidence = 'assumed' WHERE id = 1",
            "valid_from": "UPDATE memory SET valid_from = '2000-01-01' WHERE id = 1",
            "valid_until": "UPDATE memory SET valid_until = '2000-01-01' WHERE id = 1",
            "project_id": "UPDATE memory SET project_id = 2 WHERE id = 1",
            "status": "UPDATE memory SET status = 'quarantined' WHERE id = 1",
            "pinned": "UPDATE memory SET pinned = 1 WHERE id = 1",
            "updated_at": "UPDATE memory SET updated_at = '2000-01-01T00:00:00Z' "
                          "WHERE id = 1",
        }
        for field, sql in cases.items():
            with self.subTest(field=field):
                snapshot = self.db_path.read_bytes()
                self.write(sql)
                self.assertEqual(
                    self.integrity(), "mismatch",
                    f"tampering with {field} went undetected",
                )
                self.db_path.write_bytes(snapshot)
                self.assertEqual(self.integrity(), "ok")

    def test_tampering_with_supersession_fails_the_hash(self):
        """(27)"""
        self.add_memory(key="second", value="second claim")
        self.write("UPDATE memory SET superseded_by = 2 WHERE id = 1")
        self.assertEqual(self.integrity(), "mismatch")

    def test_adding_or_removing_an_evidence_link_fails_the_hash(self):
        """(28)"""
        self.ok("evidence", "add", "T-0001", "--kind", "note", "--ref", "second")
        self.write(
            "INSERT INTO memory_evidence (memory_id, evidence_id, created_at) "
            "VALUES (1, 2, '2026-01-01T00:00:00Z')"
        )
        self.assertEqual(self.integrity(), "mismatch")
        self.write("DELETE FROM memory_evidence WHERE evidence_id = 2")
        self.assertEqual(self.integrity(), "ok")

        self.write("DELETE FROM memory_evidence WHERE evidence_id = 1")
        self.assertEqual(self.integrity(), "mismatch")

    def test_malformed_blank_and_uppercase_hashes_are_detected(self):
        """(27)"""
        good = self.show(self.hid)["content_sha256"]
        for label, value in (
            ("blank", ""),
            ("uppercase", good.upper()),
            ("truncated", good[:32]),
            ("prefixed", "sha256:" + good),
            ("not hex", "z" * 64),
        ):
            with self.subTest(label=label):
                self.write(
                    "UPDATE memory SET content_sha256 = ? WHERE id = 1", (value,)
                )
                self.assertEqual(self.integrity(), "malformed")

    def test_a_substituted_hash_from_another_row_is_detected(self):
        """(27) Binding the id makes a valid hash non-transplantable."""
        other = self.add_memory(key="other", value="other claim")
        stolen = self.show(other)["content_sha256"]
        self.write(
            "UPDATE memory SET content_sha256 = ? WHERE id = 1", (stolen,)
        )
        self.assertEqual(self.integrity(), "mismatch")

    def test_writes_refuse_to_launder_a_tampered_claim(self):
        """(27/M2.6) A mutation must not recompute the hash over tampering
        and bless it."""
        self.ok("evidence", "add", "T-0001", "--kind", "note", "--ref", "second")
        self.write("UPDATE memory SET value_md = 'rewritten' WHERE id = 1")
        for argv in (
            ("memory", "pin", self.hid),
            ("memory", "retire", self.hid),
            ("memory", "link-evidence", self.hid, "E-0002"),
        ):
            with self.subTest(argv=argv):
                code, out, err = self.aos(*argv)
                self.assertEqual(code, 1, out)
                self.assertIn("Refusing to change memory", err)
                self.assertIn("doctor", err)
        self.assertEqual(self.integrity(), "mismatch")  # still not laundered

    def test_an_idempotent_no_op_neither_launders_nor_refuses(self):
        """(21/27) A no-op writes nothing, so there is nothing to launder —
        and nothing to refuse. It reports the state and leaves the damage for
        doctor and `memory show` to name."""
        self.write("UPDATE memory SET value_md = 'rewritten' WHERE id = 1")
        before = self.db_path.read_bytes()
        out = self.ok("memory", "unpin", self.hid)       # already unpinned
        self.assertIn("already unpinned", out)
        out = self.ok("memory", "link-evidence", self.hid, "E-0001")  # linked
        self.assertIn("already linked", out)
        self.assertEqual(self.db_path.read_bytes(), before)
        self.assertEqual(self.integrity(), "mismatch")

    def test_integrity_reports_never_print_the_claim(self):
        """(M2.6) A mismatch names the claim; it never quotes it."""
        self.write(
            "UPDATE memory SET value_md = ? WHERE id = 1", (f"body {FAKE_SECRET}",)
        )
        code, out, err = self.aos("memory", "pin", self.hid)
        self.assertEqual(code, 1)
        self.assertNotIn(FAKE_SECRET, err + out)
        self.assertIn("M-0001", err)

    def test_a_long_claim_still_hashes(self):
        """(M2.6) `memory add --value` never had a length limit, and U-X1's
        canonical JSON caps a string at 8192 chars. A 20 KB claim must hash,
        or its own migration would refuse it."""
        big = "x" * 20000
        hid = self.add_memory(key="big", value=big)
        doc = self.show(hid)
        self.assertEqual(doc["integrity"], "ok")
        self.assertEqual(len(doc["value_md"]), 20000)

    def test_an_unhashable_row_is_reported_not_crashed(self):
        """(M2.6) A BLOB in a TEXT column must be REPORTABLE.

        `status` and `pinned` carry CHECKs, so a BLOB cannot reach them;
        `key` is free text, so it can. The verdict is asserted at the ops
        layer: `memory show --json` cannot serialize a bytes cell to JSON and
        exits 2, exactly as every other --json command does on a byte-mangled
        row — a pre-existing, ledger-wide property, not a memory-claim one.
        Doctor is what names the damage (see DoctorTest).
        """
        self.write("UPDATE memory SET key = CAST(x'00ff' AS BLOB) WHERE id = 1")
        conn = db.open_db(self.aos_dir)
        try:
            item = ops.get_memory(conn, 1)
            self.assertEqual(ops.claim_integrity(conn, item), "unhashable")
            # It refuses with a bounded message instead of raising anything
            # the CLI would report as an internal error.
            with self.assertRaises(models.ClaimHashError) as caught:
                ops.claim_digest(conn, item)
            self.assertIn("M-0001", str(caught.exception))
            self.assertIn("is not text", str(caught.exception))
        finally:
            conn.close()

    def test_an_unhashable_claim_cannot_be_mutated(self):
        """(M2.6) The write gate refuses what it cannot verify."""
        self.write("UPDATE memory SET key = CAST(x'00ff' AS BLOB) WHERE id = 1")
        code, _, err = self.aos("memory", "pin", self.hid)
        self.assertEqual(code, 1)
        self.assertIn("Refusing to change memory", err)
        self.assertIn("cannot be hashed", err)


class ClaimHashPayloadTest(V2WorkspaceTestCase):
    def test_payload_binds_every_authoritative_field_and_excludes_the_hash(self):
        """(M2.6) The exact payload, pinned."""
        hid = self.add_memory("--evidence", "E-0001")
        conn = db.open_db(self.aos_dir)
        try:
            item = ops.get_memory(conn, 1)
            payload = ops.memory_claim_payload(item, [1])
        finally:
            conn.close()
        self.assertEqual(
            set(payload),
            {
                "claim_schema", "id", "project_id", "superseded_by", "pinned",
                "evidence_ids", "scope_sha256", "kind_sha256", "key_sha256",
                "value_sha256", "source_sha256", "confidence_sha256",
                "valid_from_sha256", "valid_until_sha256", "status_sha256",
                # U-M3 added exactly one leaf and bumped the identity with it.
                "sensitivity_sha256",
                "updated_at_sha256",
            },
        )
        self.assertNotIn("content_sha256", payload)
        self.assertEqual(payload["claim_schema"], "aos.memory-claim/v3")
        self.assertEqual(payload["evidence_ids"], [1])
        self.assertEqual(
            payload["value_sha256"], utils.sha256_text(item.value_md)
        )
        # The payload carries no claim TEXT at all: every leaf is a digest.
        blob = json.dumps(payload)
        self.assertNotIn(item.value_md, blob)
        self.assertNotIn(item.key, blob)

    def test_digest_reuses_the_ux1_canonical_serializer(self):
        """(M2.6/D-v0.3.20)"""
        import hashlib

        from agentic_os import protocols

        conn = db.open_db(self.aos_dir)
        try:
            self.add_memory()
            item = ops.get_memory(conn, 1)
            payload = ops.memory_claim_payload(item, [])
            expected = hashlib.sha256(
                protocols.serialize_canonical(payload)
            ).hexdigest()
            self.assertEqual(ops.memory_claim_digest(item, []), expected)
        finally:
            conn.close()

    def test_evidence_link_ids_are_sorted_and_deduplicated(self):
        """(M2.6) Sorted identities: link order cannot change a hash."""
        self.ok("evidence", "add", "T-0001", "--kind", "note", "--ref", "second")
        self.add_memory()
        conn = db.open_db(self.aos_dir)
        try:
            item = ops.get_memory(conn, 1)
            self.assertEqual(
                ops.memory_claim_digest(item, [2, 1, 2]),
                ops.memory_claim_digest(item, [1, 2]),
            )
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# 29/30. Doctor and privacy

class DoctorTest(V2WorkspaceTestCase):
    def doctor_lines(self) -> str:
        code, out, _ = self.aos("doctor")
        return out

    def test_doctor_passes_on_a_healthy_workspace(self):
        """(29)"""
        self.add_memory("--pin", "--evidence", "E-0001")
        out = self.doctor_lines()
        self.assertEqual(out.count("[FAIL]"), 0, out)
        self.assertIn("memory claims are well-formed", out)
        self.assertIn("memory evidence links resolve", out)

    def test_doctor_check_count_is_thirty_four(self):
        """(29) 21 → 25 → 30 → 31: U-M2's four mandated memory-claim checks
        joined the set, then U-M3's five memory-graph checks, then U-M5's one
        retrieval-benchmark registry check (the D-W8.1 pattern — the pin moves
        UP with a mandated new check)."""
        out = self.doctor_lines()
        self.assertEqual(len([l for l in out.strip().splitlines() if l]), 34)

    def test_doctor_reports_damaged_claims_by_id_only(self):
        """(29/30) Bounded, ID-only diagnostics — and the planted secret in
        the claim never reaches the report."""
        self.add_memory(key=f"key {FAKE_SECRET}", value=f"body {FAKE_SECRET}")
        self.write("UPDATE memory SET value_md = 'rewritten' WHERE id = 1")
        code, out, err = self.aos("doctor")
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] memory claims are well-formed", out)
        self.assertIn("M-0001: content hash does not match the claim", out)
        self.assertNotIn(FAKE_SECRET, out + err)
        self.assertNotIn("rewritten", out)

    def test_doctor_detects_unknown_status_and_bad_pin(self):
        """(29) Constraints can only be bypassed by editing the file; doctor
        is what finds it afterwards."""
        self.add_memory()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA writable_schema=ON")
            conn.execute(
                "UPDATE sqlite_master SET sql = replace(sql, "
                "\"CHECK (status IN ('proposed','live','contested',"
                "'quarantined','retired'))\", '') WHERE name = 'memory'"
            )
            conn.execute("PRAGMA writable_schema=OFF")
            conn.commit()
        finally:
            conn.close()
        self.write("UPDATE memory SET status = 'invented' WHERE id = 1")
        code, out, _ = self.aos("doctor")
        self.assertEqual(code, 1)
        self.assertIn("M-0001: unknown status", out)
        self.assertNotIn("invented", out)  # the VALUE is never echoed

    def test_doctor_detects_a_retired_claim_with_no_retirement_state(self):
        """(29)"""
        self.add_memory()
        conn = db.connect(self.db_path)
        try:
            conn.execute("UPDATE memory SET status = 'retired' WHERE id = 1")
            conn.commit()
            conn.row_factory = sqlite3.Row
            item = models.MemoryItem.from_row(
                conn.execute("SELECT * FROM memory WHERE id = 1").fetchone()
            )
            conn.execute(
                "UPDATE memory SET content_sha256 = ? WHERE id = 1",
                (ops.claim_digest(conn, item),),
            )
            conn.commit()
        finally:
            conn.close()
        code, out, _ = self.aos("doctor")
        self.assertEqual(code, 1)
        self.assertIn("retired but neither superseded nor expired", out)

    def test_doctor_detects_a_broken_evidence_link(self):
        """(29)"""
        self.add_memory("--evidence", "E-0001")
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("DELETE FROM evidence WHERE id = 1")
            conn.commit()
        finally:
            conn.close()
        code, out, _ = self.aos("doctor")
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] memory evidence links resolve", out)
        self.assertIn("M-0001 → missing evidence E-0001", out)

    def test_pinned_but_ineligible_is_a_warning_not_a_failure(self):
        """(29) Honestly reachable: pin, then retire."""
        self.add_memory()
        self.ok("memory", "pin", "M-0001")
        self.ok("memory", "retire", "M-0001")
        code, out, _ = self.aos("doctor")
        self.assertEqual(code, 0, out)
        self.assertIn("[WARN] pinned claims eligible for retrieval", out)
        self.assertIn("M-0001", out)

    def test_expired_but_live_is_a_warning_not_a_failure(self):
        """(29) A check that turns red because a day passed is a broken
        check: expiry is temporal, and --valid-until accepts a past date."""
        self.add_memory("--valid-until", "2000-01-01")
        code, out, _ = self.aos("doctor")
        self.assertEqual(code, 0, out)
        self.assertIn("[WARN] non-retired claims past their valid_until", out)
        self.assertIn("M-0001", out)

    def test_doctor_never_crashes_on_an_unhashable_claim(self):
        """(29) Reporting the damage is the whole point."""
        self.add_memory()
        self.write("UPDATE memory SET key = CAST(x'00ff' AS BLOB) WHERE id = 1")
        code, out, err = self.aos("doctor")
        self.assertEqual(code, 1, err)  # a refusal, never an internal error
        self.assertNotIn("Internal error", err)
        self.assertIn("M-0001", out)


class WarnOnWriteTest(V2WorkspaceTestCase):
    def test_existing_memory_warn_on_write_still_passes(self):
        """(31) U-C3 behavior is preserved exactly: the row keeps the value,
        the human is warned, the event carries safe metadata and no secret."""
        code, out, err = self.aos(
            "memory", "add", "--scope", "global", "--kind", "fact",
            "--key", f"deploy {FAKE_SECRET}", "--value", "v",
            "--source", "human", "--confidence", "confirmed",
        )
        self.assertEqual(code, 0)
        self.assertEqual(out, "M-0001\n")
        self.assertIn("WARNING: secret-shaped text in memory field(s)", err)
        self.assertIn("key", err)

        payload = self.memory_events()[-1]["payload"]
        self.assertTrue(payload["secret_warning"])
        self.assertIn("key", payload["secret_fields"])
        self.assertNotIn(FAKE_SECRET, json.dumps(payload))
        # The canonical row still holds the accepted value (the ledger stays
        # honest); only the event is redacted.
        self.assertIn(FAKE_SECRET, self.query("SELECT key FROM memory")[0][0])

    def test_secret_shaped_claims_never_reach_new_events(self):
        """(30)"""
        self.add_memory(key=f"k {FAKE_SECRET}", value=f"v {FAKE_SECRET}")
        self.ok("memory", "pin", "M-0001")
        self.ok("memory", "link-evidence", "M-0001", "E-0001")
        self.ok("memory", "unpin", "M-0001")
        self.ok("memory", "retire", "M-0001")
        blob = json.dumps(self.memory_events())
        self.assertNotIn(FAKE_SECRET, blob)

    def test_new_events_carry_no_claim_text_at_all(self):
        """(M2.9) pin/unpin/link events name ids, transitions and counts."""
        self.add_memory(key="a-distinctive-key", value="a distinctive value")
        self.ok("memory", "pin", "M-0001")
        self.ok("memory", "link-evidence", "M-0001", "E-0001")
        for event in self.memory_events():
            if event["action"] == "add":
                continue  # pre-existing U-C3-governed shape (D-v0.3.19)
            blob = json.dumps(event["payload"])
            self.assertNotIn("a distinctive value", blob)
            self.assertNotIn("a-distinctive-key", blob)
            self.assertNotIn("human", blob)


# ---------------------------------------------------------------------------
# 32/33/34. Power modes

class PowerModeTest(V2WorkspaceTestCase):
    def test_every_new_memory_leaf_is_classified(self):
        """(32)"""
        self.assertEqual(
            power.COMMAND_POLICY[("memory", "show")].kind, power.READ_ONLY
        )
        for leaf in (("memory", "pin"), ("memory", "unpin"),
                     ("memory", "link-evidence")):
            with self.subTest(leaf=leaf):
                policy = power.COMMAND_POLICY[leaf]
                self.assertEqual(policy.kind, power.AUTHORITATIVE_WRITE)
                self.assertTrue(policy.ledger)

    def test_no_command_is_left_unclassified(self):
        """(32) Walks the real parser, so a new leaf cannot be forgotten."""
        from agentic_os import cli

        for path in power.iter_command_paths(cli.build_parser()):
            with self.subTest(path=path):
                self.assertIn(path, power.COMMAND_POLICY)

    def test_recovery_blocks_new_memory_writes_before_mutation(self):
        """(33)"""
        self.add_memory("--evidence", "E-0001")
        before = self.db_path.read_bytes()
        self.ok("power", "set", "recovery")
        after_mode = self.db_path.read_bytes()

        for argv in (
            ("memory", "pin", "M-0001"),
            ("memory", "unpin", "M-0001"),
            ("memory", "link-evidence", "M-0001", "E-0001"),
            ("memory", "retire", "M-0001"),
        ):
            with self.subTest(argv=argv):
                code, out, err = self.aos(*argv)
                self.assertEqual(code, 1)
                self.assertIn("recovery", err)
                self.assertEqual(out, "")  # refused before dispatch
        self.assertEqual(self.db_path.read_bytes(), after_mode)
        self.assertEqual(before, after_mode)

    def test_recovery_still_allows_reading_claims(self):
        """(33)"""
        self.add_memory()
        self.ok("power", "set", "recovery")
        self.assertEqual(self.aos("memory", "show", "M-0001")[0], 0)
        self.assertEqual(self.aos("memory", "list")[0], 0)

    def test_deep_verification_still_operates(self):
        """(34)"""
        self.ok("power", "set", "deep")
        code, out, err = self.aos("memory", "add", "--scope", "global",
                                  "--kind", "fact", "--key", "k",
                                  "--value", "v", "--source", "human",
                                  "--confidence", "confirmed")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.aos("memory", "pin", "M-0001")[0], 0)
        self.assertEqual(self.show("M-0001")["integrity"], "ok")
        code, out, err = self.aos("doctor")
        self.assertEqual(code, 0, out)


# ---------------------------------------------------------------------------
# 35. Script / module / zipapp parity

class PackagingParityTest(V1FixtureTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._pyz_tmp = tempfile.mkdtemp(prefix="aos-m2-pyz-")
        cls.pyz = Path(cls._pyz_tmp) / "aos.pyz"
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "build_zipapp.py"),
             "--output", str(cls.pyz)],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            raise AssertionError(f"zipapp build failed: {proc.stderr}")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._pyz_tmp, ignore_errors=True)
        super().tearDownClass()

    def run_entry(self, entry: list[str], *argv: str) -> subprocess.CompletedProcess:
        """PYTHONPATH cleared and cwd outside the checkout: the zipapp must
        stand on its own, not on the source tree next door."""
        import os

        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        if entry[0] != str(self.pyz):
            env["PYTHONPATH"] = str(REPO_ROOT)
        return subprocess.run(
            [sys.executable, *entry, "--root", str(self.root), *argv],
            capture_output=True, text=True, timeout=120,
            cwd=str(Path(self.root).parent), env=env,
        )

    def entries(self) -> dict[str, list[str]]:
        return {
            "script": [str(REPO_ROOT / "aos.py")],
            "module": ["-m", "agentic_os"],
            "zipapp": [str(self.pyz)],
        }

    def test_zipapp_carries_the_migration_and_no_database(self):
        """(35)"""
        import zipfile

        with zipfile.ZipFile(self.pyz) as archive:
            names = archive.namelist()
        self.assertIn("agentic_os/migrations.py", names)
        self.assertIn("agentic_os/models.py", names)
        for name in names:
            self.assertFalse(name.endswith((".db", ".db-wal", ".db-shm")), name)
            self.assertNotIn("v1_workspace", name)
            self.assertNotIn("tests/", name)

    def test_every_entrypoint_migrates_and_inspects_identically(self):
        """(35) Each entrypoint gets its OWN copy of the v1 fixture, migrates
        it to the CURRENT version, and must produce the same answers.

        The CLI has no `--target`, so this exercises the whole chain a real v1
        user gets — 1 → 2 → 3 since U-M3. The U-M2 step being FIRST is what
        this asserts; the rest of the chain is U-M3's suite's business.
        """
        outputs = {}
        for name, entry in self.entries().items():
            with self.subTest(entry=name):
                self.setUp()  # a fresh v1 copy per entrypoint
                status = self.run_entry(entry, "migrate", "status", "--json")
                self.assertEqual(status.returncode, 0, status.stderr)
                report = json.loads(status.stdout)
                self.assertTrue(report["pending"])
                self.assertEqual(
                    report["plan"][0],
                    {"from": 1, "to": 2, "migration_id": "u-m2-memory-claims-v2"},
                )

                plan = self.run_entry(entry, "migrate", "plan")
                self.assertEqual(plan.returncode, 0, plan.stderr)
                self.assertIn("1 → 2", plan.stdout)

                applied = self.run_entry(entry, "migrate", "apply")
                self.assertEqual(applied.returncode, 0, applied.stderr)
                self.assertEqual(self.version(), db.SCHEMA_VERSION)

                shown = self.run_entry(entry, "memory", "show", "M-0001", "--json")
                self.assertEqual(shown.returncode, 0, shown.stderr)
                doc = json.loads(shown.stdout)
                self.assertEqual(doc["integrity"], "ok")

                listed = self.run_entry(entry, "memory", "list", "--json")
                self.assertEqual(listed.returncode, 0, listed.stderr)
                claims = json.loads(listed.stdout)["memories"]

                pinned = self.run_entry(entry, "memory", "pin", "M-0001")
                self.assertEqual(pinned.returncode, 0, pinned.stderr)

                outputs[name] = [
                    (c["id"], c["status"], c["pinned"], c["evidence"])
                    for c in claims
                ]
        self.assertEqual(outputs["script"], outputs["module"])
        self.assertEqual(outputs["script"], outputs["zipapp"])

    def test_zipapp_refuses_an_unmigrated_database_the_same_way(self):
        """(35)"""
        result = self.run_entry([str(self.pyz)], "memory", "list")
        self.assertEqual(result.returncode, 1)
        self.assertIn("never auto-migrate", result.stderr)


if __name__ == "__main__":
    unittest.main()
