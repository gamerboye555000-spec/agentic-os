"""v0.2 U-C2 backup/verify/restore tests
(agentic-os-v0.2-u-c2-backup-restore-contract.md).

U-C2.1 `backup create` writes a manifest-carrying backup via the sqlite3
backup API under `.agentic-os/backups/` ·
U-C2.2 the manifest carries created_at, source_db_path, schema_version,
size_bytes, sha256, and a tool/version label ·
U-C2.3 `backup verify` checks file, manifest, sha256, SQLite openability,
schema_version, and PRAGMA integrity_check — corrupted copies fail clearly,
and verify never needs (or touches) the live ledger ·
U-C2.4 `backup restore` writes to a NEW path only, refuses to overwrite,
and has no overwrite flag ·
U-C2.5 RECOVERY.md documents the full drill.

Corruption modes pinned here mirror what SQLite actually detects: a single
flipped bit passes PRAGMA integrity_check (no page checksums), so the
manifest sha256 catches it; a zeroed page passes a sha256 that was
regenerated to match, so integrity_check catches it. Both checks are
load-bearing and each has a test that the other cannot pass.

Fixture reminder (Night-1 shape): project `demo`; T-0001 done (note
evidence); T-0002 ready in demo; T-0003 projectless inbox capture.
"""

from __future__ import annotations

import json
import re
import sqlite3
import unittest
from pathlib import Path

from weekend_harness import Night1BackCompatCase, WeekendOpsTestCase, run_cli

import agentic_os
from agentic_os import db, utils

REPO_ROOT = Path(__file__).resolve().parent.parent

BACKUP_NAME_RE = re.compile(r"aos-backup-[0-9]{8}T[0-9]{6}Z(-[0-9]+)?\.db\Z")

VERIFY_CHECK_NAMES = (
    "backup file exists",
    "manifest file exists",
    "manifest well-formed",
    "size matches manifest",
    "sha256 matches manifest",
    "backup opens as SQLite",
    "schema_version supported",
    "integrity_check passes",
)


def _grow_db(db_path: Path, rows: int = 800) -> None:
    """Bulk-pad the events table so the db spans many pages (raw SQL on a
    throwaway fixture, the class's established pattern for states the CLI
    can't reach quickly)."""
    conn = sqlite3.connect(db_path)
    try:
        payload = json.dumps({"schema_version": 1, "pad": "x" * 120})
        with conn:
            conn.executemany(
                "INSERT INTO events (ts, actor, entity, entity_id, action, "
                "payload_json) VALUES ('2026-07-08T00:00:00Z', 'human', "
                "'system', NULL, 'pad', ?)",
                [(payload,)] * rows,
            )
    finally:
        conn.close()


def _zero_last_page(path: Path, page: int = 4096) -> None:
    data = bytearray(path.read_bytes())
    assert len(data) > page * 3, "fixture db too small to corrupt safely"
    data[-page:] = b"\x00" * page
    path.write_bytes(bytes(data))


def _flip_middle_byte(path: Path) -> None:
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0xFF
    path.write_bytes(bytes(data))


def _rewrite_manifest(manifest_path: Path, **updates) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(updates)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def _open_backup(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


class BackupCase(Night1BackCompatCase):
    def create_backup(self) -> tuple[Path, Path]:
        out = self.aos("backup", "create")
        lines = out.strip().splitlines()
        self.assertGreaterEqual(len(lines), 2, out)
        backup_path = Path(lines[0])
        self.assertTrue(lines[1].startswith("manifest: "), out)
        manifest_path = Path(lines[1][len("manifest: "):])
        return backup_path, manifest_path

    def count(self, table: str) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# U-C2.1 — backup create

class TestBackupCreate(BackupCase):
    def test_create_writes_backup_and_manifest_under_backups_folder(self):
        backup_path, manifest_path = self.create_backup()
        self.assertEqual(backup_path.parent, self.aos_dir / "backups")
        self.assertEqual(manifest_path.parent, self.aos_dir / "backups")
        self.assertTrue(backup_path.is_file())
        self.assertTrue(manifest_path.is_file())
        self.assertRegex(backup_path.name, BACKUP_NAME_RE)
        self.assertEqual(
            manifest_path.name, backup_path.stem + ".manifest.json"
        )

    def test_backup_is_a_complete_database_without_its_own_event(self):
        live_tasks = self.count("tasks")
        live_events_before = self.count("events")
        backup_path, _ = self.create_backup()
        conn = _open_backup(backup_path)
        try:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
                live_tasks,
            )
            # sqlite3 backup semantics, not a torn live copy: the backup is
            # a consistent image taken BEFORE the backup_create event.
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
                live_events_before,
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM events WHERE action = 'backup_create'"
                ).fetchone()[0],
                0,
            )
        finally:
            conn.close()

    def test_manifest_fields_are_complete_and_accurate(self):
        backup_path, manifest_path = self.create_backup()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["aos_backup_manifest"], 1)
        self.assertRegex(
            manifest["created_at"],
            r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z",
        )
        self.assertEqual(
            manifest["source_db_path"],
            str(self.aos_dir / utils.DB_FILENAME),
        )
        self.assertEqual(manifest["schema_version"], db.SCHEMA_VERSION)
        self.assertEqual(manifest["size_bytes"], backup_path.stat().st_size)
        self.assertEqual(manifest["sha256"], utils.sha256_file(backup_path))
        self.assertIn("agentic-os", manifest["tool"])
        self.assertIn(agentic_os.__version__, manifest["tool"])

    def test_create_emits_backup_create_event_after_the_file_is_written(self):
        backup_path, manifest_path = self.create_backup()
        conn = _open_backup(self.db_path)
        try:
            row = conn.execute(
                "SELECT entity, action, payload_json FROM events "
                "WHERE action = 'backup_create'"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["entity"], "system")
        payload = json.loads(row["payload_json"])
        self.assertEqual(payload["path"], f"backups/{backup_path.name}")
        self.assertEqual(payload["manifest"], f"backups/{manifest_path.name}")
        self.assertEqual(payload["sha256"], utils.sha256_file(backup_path))
        self.assertEqual(payload["size_bytes"], backup_path.stat().st_size)

    def test_two_creates_coexist(self):
        first_db, first_manifest = self.create_backup()
        second_db, second_manifest = self.create_backup()
        self.assertNotEqual(first_db, second_db)
        self.assertNotEqual(first_manifest, second_manifest)
        for path in (first_db, first_manifest, second_db, second_manifest):
            self.assertTrue(path.is_file(), path)

    def test_create_before_init_exits_1(self):
        uninit = self.new_tmp_dir("uninit")
        code, out, err = self.run_cli(
            "--root", str(uninit), "backup", "create"
        )
        self.assertEqual(code, 1)
        self.assertIn("Not initialized", err)

    def test_create_refuses_a_corrupt_live_database(self):
        _grow_db(self.db_path)
        _zero_last_page(self.db_path)
        code, out, err = self.run_cli(
            "--root", str(self.root), "backup", "create"
        )
        self.assertEqual(code, 1, out + err)
        self.assertIn("integrity", err.lower())
        # The refusal happens before anything is written.
        self.assertFalse((self.aos_dir / "backups").exists())

    def test_no_schema_drift_after_create(self):
        self.create_backup()
        self.assert_no_schema_drift()


# ---------------------------------------------------------------------------
# U-C2.3 — backup verify

class TestBackupVerify(BackupCase):
    def setUp(self):
        super().setUp()
        self.backup_path, self.manifest_path = self.create_backup()

    def verify(self, path: Path | None = None) -> tuple[int, str, str]:
        return self.run_cli("backup", "verify", str(path or self.backup_path))

    def test_verify_passes_and_prints_every_check(self):
        code, out, err = self.verify()
        self.assertEqual(code, 0, out + err)
        positions = []
        for name in VERIFY_CHECK_NAMES:
            self.assertIn(f"[PASS] {name}", out)
            positions.append(out.index(f"[PASS] {name}"))
        self.assertEqual(positions, sorted(positions), "check order drifted")
        self.assertNotIn("[FAIL]", out)

    def test_verify_is_eventless_and_needs_no_workspace(self):
        events_before = self.count("events")
        # cwd is an unrelated temp dir (class setUp) and no --root is passed:
        # verify must not require — or touch — any workspace.
        code, out, err = self.verify()
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("Not initialized", err)
        self.assertEqual(self.count("events"), events_before)

    def test_verify_leaves_no_stray_files_beside_the_backup(self):
        siblings_before = sorted(p.name for p in self.backup_path.parent.iterdir())
        code, out, err = self.verify()
        self.assertEqual(code, 0, out + err)
        siblings_after = sorted(p.name for p in self.backup_path.parent.iterdir())
        self.assertEqual(siblings_after, siblings_before)

    def test_verify_detects_a_bit_flipped_copy(self):
        # Acceptance line: "verify detects corrupted copy". A single flipped
        # bit preserves size and passes integrity_check — only the manifest
        # sha256 can catch it.
        _flip_middle_byte(self.backup_path)
        code, out, err = self.verify()
        self.assertEqual(code, 1, out + err)
        self.assertIn("[PASS] size matches manifest", out)
        self.assertIn("[FAIL] sha256 matches manifest", out)
        # Fail-fast: the checks after the failed one never ran.
        self.assertNotIn("[PASS] backup opens as SQLite", out)
        self.assertNotIn("[PASS] integrity_check passes", out)
        self.assertNotIn("[FAIL] integrity_check passes", out)
        self.assertIn("sha256 matches manifest", err)

    def test_verify_detects_truncation(self):
        data = self.backup_path.read_bytes()
        self.backup_path.write_bytes(data[: len(data) // 2])
        code, out, err = self.verify()
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] size matches manifest", out)

    def test_verify_detects_structural_corruption_the_manifest_blesses(self):
        # A zeroed page with a manifest regenerated to match passes the
        # sha256 check — PRAGMA integrity_check is what catches it.
        _grow_db(self.db_path)
        backup_path, manifest_path = self.create_backup()
        _zero_last_page(backup_path)
        _rewrite_manifest(
            manifest_path,
            sha256=utils.sha256_file(backup_path),
            size_bytes=backup_path.stat().st_size,
        )
        code, out, err = self.verify(backup_path)
        self.assertEqual(code, 1, out + err)
        self.assertIn("[PASS] sha256 matches manifest", out)
        self.assertIn("[FAIL] integrity_check passes", out)

    def test_verify_missing_backup_file(self):
        code, out, err = self.verify(self.backup_path.with_name("nope.db"))
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] backup file exists", out)

    def test_verify_missing_manifest(self):
        self.manifest_path.unlink()
        code, out, err = self.verify()
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] manifest file exists", out)

    def test_verify_rejects_malformed_manifests(self):
        cases = {
            "not json": "not json {",
            "not an object": json.dumps(["a", "list"]),
            "missing sha256": json.dumps(
                {
                    "aos_backup_manifest": 1,
                    "created_at": "2026-07-08T00:00:00Z",
                    "source_db_path": "/x",
                    "schema_version": "1",
                    "size_bytes": 1,
                    "tool": "agentic-os",
                }
            ),
            "unsupported format": json.dumps(
                {
                    "aos_backup_manifest": 99,
                    "created_at": "2026-07-08T00:00:00Z",
                    "source_db_path": "/x",
                    "schema_version": "1",
                    "size_bytes": 1,
                    "sha256": "0" * 64,
                    "tool": "agentic-os",
                }
            ),
            # JSON true/1.0 must not pass as format 1 (Python True == 1).
            "bool format": json.dumps(
                {
                    "aos_backup_manifest": True,
                    "created_at": "2026-07-08T00:00:00Z",
                    "source_db_path": "/x",
                    "schema_version": "1",
                    "size_bytes": 1,
                    "sha256": "0" * 64,
                    "tool": "agentic-os",
                }
            ),
            "float format": json.dumps(
                {
                    "aos_backup_manifest": 1.0,
                    "created_at": "2026-07-08T00:00:00Z",
                    "source_db_path": "/x",
                    "schema_version": "1",
                    "size_bytes": 1,
                    "sha256": "0" * 64,
                    "tool": "agentic-os",
                }
            ),
        }
        for label, text in cases.items():
            with self.subTest(label=label):
                self.manifest_path.write_text(text, encoding="utf-8")
                code, out, err = self.verify()
                self.assertEqual(code, 1)
                self.assertIn("[FAIL] manifest well-formed", out)

    def test_verify_rejects_wrong_schema_version_in_manifest(self):
        _rewrite_manifest(self.manifest_path, schema_version="999")
        code, out, err = self.verify()
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] schema_version supported", out)
        self.assertIn("999", out)

    def test_verify_rejects_a_backup_from_an_unsupported_schema(self):
        # Manifest and backup AGREE on schema 999, so the manifest-mismatch
        # branch stays quiet — only the supported-by-this-build branch can
        # catch a future-schema backup fed to this build.
        conn = sqlite3.connect(self.backup_path)
        try:
            with conn:
                conn.execute(
                    "UPDATE meta SET value = '999' WHERE key = 'schema_version'"
                )
        finally:
            conn.close()
        _rewrite_manifest(
            self.manifest_path,
            schema_version="999",
            sha256=utils.sha256_file(self.backup_path),
            size_bytes=self.backup_path.stat().st_size,
        )
        code, out, err = self.verify()
        self.assertEqual(code, 1, out + err)
        self.assertIn("[FAIL] schema_version supported", out)
        self.assertIn("this build supports", out)

    def test_verify_rejects_a_non_database_file_with_a_consistent_manifest(self):
        garbage = b"this is not a sqlite database" * 100
        self.backup_path.write_bytes(garbage)
        _rewrite_manifest(
            self.manifest_path,
            sha256=utils.sha256_bytes(garbage),
            size_bytes=len(garbage),
        )
        code, out, err = self.verify()
        self.assertEqual(code, 1)
        self.assertIn("[PASS] sha256 matches manifest", out)
        self.assertIn("[FAIL] backup opens as SQLite", out)

    def test_verify_moved_pair_passes_even_in_odd_directory_names(self):
        # The pair travels together; '%', '#', and spaces exercise the
        # read-only URI open's percent-encoding.
        odd = self.new_tmp_dir("back ups %#odd")
        moved_db = odd / self.backup_path.name
        moved_manifest = odd / self.manifest_path.name
        moved_db.write_bytes(self.backup_path.read_bytes())
        moved_manifest.write_bytes(self.manifest_path.read_bytes())
        code, out, err = self.verify(moved_db)
        self.assertEqual(code, 0, out + err)


# ---------------------------------------------------------------------------
# U-C2.4 — restore to a new path only

class TestBackupRestore(BackupCase):
    def setUp(self):
        super().setUp()
        self.backup_path, self.manifest_path = self.create_backup()

    def restore(self, target: Path, backup: Path | None = None):
        return self.run_cli(
            "backup", "restore", str(backup or self.backup_path),
            "--to", str(target),
        )

    def test_restore_writes_a_new_database_at_a_new_path(self):
        target = self.new_tmp_dir("restore-here") / "deep" / "sub" / "aos.db"
        code, out, err = self.restore(target)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(out.strip().splitlines()[0], str(target))
        self.assertIn("RECOVERY.md", out)
        self.assertTrue(target.is_file())
        manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(utils.sha256_file(target), manifest["sha256"])
        conn = _open_backup(target)
        try:
            self.assertEqual(
                conn.execute(
                    "SELECT value FROM meta WHERE key = 'schema_version'"
                ).fetchone()["value"],
                db.SCHEMA_VERSION,
            )
            titles = [
                r["title"]
                for r in conn.execute("SELECT title FROM tasks").fetchall()
            ]
            self.assertIn("Night-1 task", titles)
        finally:
            conn.close()

    def test_restore_is_eventless(self):
        events_before = self.count("events")
        target = self.new_tmp_dir("eventless") / "aos.db"
        code, out, err = self.restore(target)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.count("events"), events_before)

    def test_restore_refuses_an_existing_file_target(self):
        target = self.new_tmp_dir("occupied") / "aos.db"
        target.write_text("precious bytes\n", encoding="utf-8")
        code, out, err = self.restore(target)
        self.assertEqual(code, 1, out + err)
        self.assertIn("Refusing to overwrite", err)
        self.assertEqual(target.read_text(encoding="utf-8"), "precious bytes\n")

    def test_restore_refuses_an_existing_directory_target(self):
        target = self.new_tmp_dir("a-directory")
        code, out, err = self.restore(target)
        self.assertEqual(code, 1, out + err)
        self.assertIn("Refusing to overwrite", err)
        self.assertTrue(target.is_dir())

    def test_restore_refuses_the_live_database_path(self):
        live = self.aos_dir / utils.DB_FILENAME
        sha_before = utils.sha256_file(live)
        code, out, err = self.restore(live)
        self.assertEqual(code, 1, out + err)
        self.assertIn("Refusing to overwrite", err)
        self.assertEqual(utils.sha256_file(live), sha_before)

    def test_restore_has_no_overwrite_flag(self):
        target = self.new_tmp_dir("no-flag") / "aos.db"
        for flag in ("--overwrite", "--force"):
            with self.subTest(flag=flag):
                code, out, err = self.run_cli(
                    "backup", "restore", str(self.backup_path),
                    "--to", str(target), flag,
                )
                self.assertEqual(code, 1)
                self.assertIn("unrecognized arguments", err)

    def test_restore_refuses_a_corrupted_backup_and_writes_nothing(self):
        _flip_middle_byte(self.backup_path)
        target = self.new_tmp_dir("never-written") / "aos.db"
        code, out, err = self.restore(target)
        self.assertEqual(code, 1, out + err)
        self.assertIn("verif", err.lower())
        self.assertFalse(target.exists())

    def test_full_disaster_drill_restore_into_the_workspace(self):
        # The RECOVERY.md drill: live db lost → restore the verified backup
        # to the (now free) live path → doctor passes → data intact.
        live = self.aos_dir / utils.DB_FILENAME
        live.unlink()
        for stray in (live.with_name(live.name + "-wal"),
                      live.with_name(live.name + "-shm")):
            stray.unlink(missing_ok=True)
        code, out, err = self.restore(live)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.aos("doctor").count("[FAIL]"), 0)
        self.assertIn("Night-1 task", self.aos("task", "show", "T-0001"))

    def test_restore_removes_the_partial_file_when_the_copy_fails(self):
        # A mid-copy OSError (disk full) must not leave a partial target
        # that blocks the retry with a misleading overwrite refusal.
        from unittest import mock

        from agentic_os import backup
        from agentic_os.utils import AosError

        target = self.new_tmp_dir("io-error") / "aos.db"
        real_open = open

        class _ExplodingHandle:
            def __init__(self, handle):
                self._handle = handle

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self._handle.close()
                return False

            def write(self, data):
                raise OSError(28, "No space left on device")

        def exploding_open(path, mode="r", *args, **kwargs):
            handle = real_open(path, mode, *args, **kwargs)
            if mode == "xb":
                return _ExplodingHandle(handle)
            return handle

        with mock.patch("agentic_os.backup.open", exploding_open, create=True):
            with self.assertRaises(AosError) as ctx:
                backup.restore_backup(self.backup_path, target)
        self.assertEqual(ctx.exception.exit_code, 1)
        self.assertFalse(target.exists())

    def test_restore_relative_target_resolves_against_cwd(self):
        cwd = self.new_tmp_dir("rel-cwd")
        self.chdir(cwd)
        code, out, err = self.run_cli(
            "backup", "restore", str(self.backup_path),
            "--to", "restored/aos.db",
        )
        self.assertEqual(code, 0, out + err)
        self.assertTrue((cwd / "restored" / "aos.db").is_file())


# ---------------------------------------------------------------------------
# U-C2.1 hard invariant — sqlite3 backup semantics, not a raw file copy

class TestBackupApiSemantics(WeekendOpsTestCase):
    """With WAL auto-checkpointing off, committed rows live only in
    aos.db-wal: a raw copy of the main file misses them, the backup API
    reads through the WAL. This is the test a naive shutil.copyfile
    implementation cannot pass."""

    def test_backup_contains_committed_rows_a_raw_file_copy_misses(self):
        from agentic_os import backup

        self.conn.execute("PRAGMA wal_autocheckpoint=0")
        marker = "wal-only marker task"
        with self.conn:
            self.conn.execute(
                "INSERT INTO tasks (title, created_at, updated_at) VALUES "
                "(?, '2026-07-08T00:00:00Z', '2026-07-08T00:00:00Z')",
                (marker,),
            )
        aos_dir = self.root / utils.AOS_DIR_NAME
        db_path = aos_dir / utils.DB_FILENAME

        def marker_count(path: Path) -> int:
            conn = sqlite3.connect(path)
            try:
                try:
                    return conn.execute(
                        "SELECT COUNT(*) FROM tasks WHERE title = ?",
                        (marker,),
                    ).fetchone()[0]
                except sqlite3.OperationalError:
                    return 0  # raw copy may not even hold the schema yet
            finally:
                conn.close()

        raw_copy = self.root / "raw-copy.db"
        raw_copy.write_bytes(db_path.read_bytes())
        # Precondition that makes this test discriminating: the committed
        # row is NOT in the main database file.
        self.assertEqual(marker_count(raw_copy), 0)

        result = backup.create_backup(self.conn, aos_dir)
        self.assertEqual(marker_count(result["path"]), 1)


# ---------------------------------------------------------------------------
# Module helpers (pure functions)

class TestBackupHelpers(unittest.TestCase):
    def test_manifest_path_derivation(self):
        from agentic_os import backup

        cases = {
            "/x/aos-backup-1.db": "/x/aos-backup-1.manifest.json",
            "/x/a.b.db": "/x/a.b.manifest.json",
            "/x/plainname": "/x/plainname.manifest.json",
        }
        for given, expected in cases.items():
            with self.subTest(given=given):
                self.assertEqual(
                    backup.manifest_path_for(Path(given)), Path(expected)
                )

    def test_free_pair_skips_existing_names(self):
        import tempfile

        from agentic_os import backup

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        backups_dir = Path(tmp.name)
        stamp = "20260708T000000Z"
        first = backup._free_pair(backups_dir, stamp)
        self.assertEqual(first.name, f"aos-backup-{stamp}.db")
        first.touch()
        second = backup._free_pair(backups_dir, stamp)
        self.assertEqual(second.name, f"aos-backup-{stamp}-2.db")
        # A lone stale manifest also blocks its stem.
        backup.manifest_path_for(second).touch()
        third = backup._free_pair(backups_dir, stamp)
        self.assertEqual(third.name, f"aos-backup-{stamp}-3.db")


# ---------------------------------------------------------------------------
# U-C2.5 — RECOVERY.md

class TestRecoveryDoc(unittest.TestCase):
    def test_recovery_md_exists_at_repo_root(self):
        path = REPO_ROOT / "RECOVERY.md"
        self.assertTrue(path.is_file(), path)
        self.assertGreater(len(path.read_text(encoding="utf-8")), 500)

    def test_recovery_md_documents_the_full_drill(self):
        text = (REPO_ROOT / "RECOVERY.md").read_text(encoding="utf-8")
        for needle in (
            "backup create",
            "backup verify",
            "backup restore",
            "--to",
            "integrity_check",
            "sha256",
            "manifest",
            "doctor",
            "What not to do",
        ):
            with self.subTest(needle=needle):
                self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
