"""Verifiable backups: create / verify / restore (U-C2; drill in RECOVERY.md).

`backup create` copies aos.db through the sqlite3 backup API (`conn.backup`)
— NEVER a bare file copy: the database runs in WAL mode and a raw copy can
miss or tear transactions still living in the -wal file. Every backup gets a
sibling manifest (created_at, source_db_path, schema_version, size_bytes,
sha256, tool) so later verification can prove the bytes on disk are the
bytes that were written. The audit event (action=backup_create) is emitted
AFTER the files are written, so the backup never contains its own event
(same rule as `snapshot`). A source that fails PRAGMA integrity_check is
refused — silently archiving corruption is how backups turn out to be
worthless on the day they are needed.

`backup verify` and `backup restore` deliberately never open the live
ledger: recovery must work exactly when the live database is damaged or
gone. Both are eventless (extends D-P0.6). Verification needs BOTH hash and
structure checks: a single flipped bit passes PRAGMA integrity_check
(SQLite pages carry no checksums) but fails the manifest sha256, while a
zeroed page under a regenerated manifest passes sha256 but fails
integrity_check. Backups are opened read-only with immutable=1 — a plain
read-only open of a WAL-marked file would create -shm/-wal droppings next
to the backup.

`restore` verifies first, then copies to a NEW path only (open(..., "xb"));
there is no overwrite flag by design (v0.2). Adopting the restored file as
the live ledger is the human's move, mirroring human-controlled git.

U-M1 split `create_backup` into `write_backup_pair` (files + manifest, no
event) plus the event, and gave `verify_backup` an `expected_schema_version`
override. Both exist so migrations can reuse this machinery verbatim rather
than growing a second copy of it; see the U-M1 contract (M1.7) for why a
pre-migration snapshot must be eventless and must verify against the version
it was taken at. `backup create`/`verify` behavior is unchanged.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from . import __version__, db, events, ops, utils
from .utils import AosError

BACKUPS_DIRNAME = "backups"
MANIFEST_FORMAT = 1
MANIFEST_FIELDS = (
    "aos_backup_manifest",
    "created_at",
    "source_db_path",
    "schema_version",
    "size_bytes",
    "sha256",
    "tool",
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


@dataclass
class VerifyCheck:
    name: str
    ok: bool
    detail: str = ""


def _utc_stamp() -> str:
    """YYYYMMDDTHHMMSSZ, derived from the single clock utility."""
    return utils.utc_now_iso().replace("-", "").replace(":", "")


def manifest_path_for(backup_path: Path) -> Path:
    """The manifest lives beside its backup as <stem>.manifest.json.
    A backup moves as a pair — copy both files or verify fails."""
    return backup_path.with_name(backup_path.stem + ".manifest.json")


def _free_pair(backups_dir: Path, stamp: str) -> Path:
    """First name whose backup AND manifest are both free: plain, then
    -2, -3, … (the export module's collision convention, pair-aware)."""
    base = f"aos-backup-{stamp}"
    n = 1
    while True:
        name = base if n == 1 else f"{base}-{n}"
        candidate = backups_dir / f"{name}.db"
        if not candidate.exists() and not manifest_path_for(candidate).exists():
            return candidate
        n += 1


def _open_ro(path: Path) -> sqlite3.Connection:
    """Read-only, immutable open: never creates -shm/-wal next to the file.
    '%', '#', and '?' in the path are percent-encoded for SQLite's URI
    parser."""
    quoted = urllib.parse.quote(str(path), safe="/")
    conn = sqlite3.connect(f"file:{quoted}?mode=ro&immutable=1", uri=True)
    conn.row_factory = sqlite3.Row  # db.get_meta indexes rows by name
    return conn


def write_backup_pair(conn: sqlite3.Connection, aos_dir: Path) -> dict:
    """Write the backup + manifest pair. Files only — emits NO event.

    The eventless half of `create_backup`, exposed for U-M1: a migration
    takes its pre-migration snapshot while holding the write lock, and
    emitting an event here would require a commit that releases that lock
    and reopens the very race the lock closes. The migration records the
    snapshot inside its own `system/migrate` event instead, committed
    atomically with the step it protects.

    Returns {"path", "manifest_path", "manifest"}. The backups folder is
    created lazily on first use — it is not part of the required workspace
    layout, so doctor stays green on workspaces that never ran backup.
    """
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
    except sqlite3.DatabaseError as exc:
        integrity = f"error: {exc}"
    if integrity != "ok":
        raise AosError(
            "Live database fails PRAGMA integrity_check "
            f"({str(integrity)[:200]}); refusing to archive corruption. "
            "See RECOVERY.md."
        )
    backups_dir = aos_dir / BACKUPS_DIRNAME
    backups_dir.mkdir(parents=True, exist_ok=True)
    backup_path = _free_pair(backups_dir, _utc_stamp())
    dest = sqlite3.connect(backup_path)
    try:
        conn.backup(dest)
    finally:
        dest.close()
    sha256 = utils.sha256_file(backup_path)
    size_bytes = backup_path.stat().st_size
    manifest = {
        "aos_backup_manifest": MANIFEST_FORMAT,
        "created_at": utils.utc_now_iso(),
        "source_db_path": str(aos_dir / utils.DB_FILENAME),
        "schema_version": db.get_meta(conn, "schema_version"),
        "size_bytes": size_bytes,
        "sha256": sha256,
        "tool": f"agentic-os {__version__} (aos.py backup create)",
    }
    manifest_path = manifest_path_for(backup_path)
    utils.write_text_lf(manifest_path, utils.json_dumps(manifest))
    return {"path": backup_path, "manifest_path": manifest_path,
            "manifest": manifest}


def create_backup(conn: sqlite3.Connection, aos_dir: Path) -> dict:
    """Back up the live ledger into <aos_dir>/backups/ with a manifest, and
    record the audit event.

    The event is emitted AFTER the files are written, so the backup never
    contains its own event (same rule as `snapshot`).
    """
    result = write_backup_pair(conn, aos_dir)
    backup_path = result["path"]
    manifest_path = result["manifest_path"]
    manifest = result["manifest"]
    with db.transaction(conn):
        events.emit(
            conn,
            actor=ops.ACTOR_HUMAN,
            entity="system",
            entity_id=None,
            action="backup_create",
            payload={
                "filename": backup_path.name,
                "path": f"{BACKUPS_DIRNAME}/{backup_path.name}",
                "manifest": f"{BACKUPS_DIRNAME}/{manifest_path.name}",
                "sha256": manifest["sha256"],
                "size_bytes": manifest["size_bytes"],
                "schema_version": manifest["schema_version"],
                "note": (
                    "backup files were written before this event; "
                    "the backup does not contain its own event"
                ),
            },
        )
    return result


def _manifest_problem(manifest) -> str | None:
    """One line naming what disqualifies a parsed manifest, or None."""
    if not isinstance(manifest, dict):
        return "not a JSON object"
    missing = [field for field in MANIFEST_FIELDS if field not in manifest]
    if missing:
        return "missing field(s): " + ", ".join(missing)
    fmt = manifest["aos_backup_manifest"]
    # type-strict: JSON true/1.0 must not pass as format 1 (True == 1).
    if type(fmt) is not int or fmt != MANIFEST_FORMAT:
        return (
            f"unsupported manifest format {fmt!r} "
            f"(this build reads {MANIFEST_FORMAT})"
        )
    sha256 = manifest["sha256"]
    if not isinstance(sha256, str) or not _SHA256_RE.match(sha256):
        return "sha256 is not 64 lowercase hex characters"
    size = manifest["size_bytes"]
    if isinstance(size, bool) or not isinstance(size, int) or size < 0:
        return "size_bytes is not a non-negative integer"
    if not isinstance(manifest["schema_version"], str):
        return "schema_version is not a string"
    return None


def verify_backup(
    backup_path: Path, *, expected_schema_version: str | None = None
) -> list[VerifyCheck]:
    """Ordered checks, stopping at the first failure (each later check
    assumes the earlier ones). Read-only: never opens the live ledger,
    never writes a byte anywhere.

    `expected_schema_version` defaults to this build's SCHEMA_VERSION — the
    question `backup verify` answers is "can this build use this backup?".
    U-M1 passes the version the snapshot was actually taken at: once a build
    supports version N, a correct pre-migration snapshot of an N-1 database
    would otherwise fail this check and migration could never run.
    """
    checks: list[VerifyCheck] = []

    def passed(name: str, detail: str = "") -> None:
        checks.append(VerifyCheck(name, True, detail))

    def failed(name: str, detail: str) -> list[VerifyCheck]:
        checks.append(VerifyCheck(name, False, detail))
        return checks

    if not backup_path.is_file():
        return failed("backup file exists", f"no file at {backup_path}")
    passed("backup file exists", str(backup_path))

    manifest_path = manifest_path_for(backup_path)
    if not manifest_path.is_file():
        return failed(
            "manifest file exists",
            f"expected {manifest_path} (the pair moves together)",
        )
    passed("manifest file exists", str(manifest_path))

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        return failed("manifest well-formed", f"does not parse: {exc}")
    problem = _manifest_problem(manifest)
    if problem:
        return failed("manifest well-formed", problem)
    passed("manifest well-formed", f"aos_backup_manifest {MANIFEST_FORMAT}")

    actual_size = backup_path.stat().st_size
    if actual_size != manifest["size_bytes"]:
        return failed(
            "size matches manifest",
            f"file is {actual_size} bytes, manifest says "
            f"{manifest['size_bytes']}",
        )
    passed("size matches manifest", f"{actual_size} bytes")

    actual_sha = utils.sha256_file(backup_path)
    if actual_sha != manifest["sha256"]:
        return failed(
            "sha256 matches manifest",
            "backup bytes changed since creation (integrity_check alone "
            "cannot catch a flipped bit — do not trust this copy)",
        )
    passed("sha256 matches manifest", actual_sha[:12] + "…")

    try:
        conn = _open_ro(backup_path)
    except sqlite3.Error as exc:
        return failed("backup opens as SQLite", str(exc))
    try:
        try:
            conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
        except sqlite3.Error as exc:
            return failed("backup opens as SQLite", str(exc))
        passed("backup opens as SQLite")

        try:
            version = db.get_meta(conn, "schema_version")
        except sqlite3.Error as exc:
            return failed(
                "schema_version supported",
                f"cannot read schema_version: {exc}",
            )
        if version != manifest["schema_version"]:
            return failed(
                "schema_version supported",
                f"backup says {version!r}, manifest says "
                f"{manifest['schema_version']!r}",
            )
        if expected_schema_version is None:
            if version != db.SCHEMA_VERSION:
                return failed(
                    "schema_version supported",
                    f"backup is schema {version!r}, this build supports "
                    f"{db.SCHEMA_VERSION!r}",
                )
        elif version != expected_schema_version:
            return failed(
                "schema_version supported",
                f"backup is schema {version!r}, expected "
                f"{expected_schema_version!r}",
            )
        passed("schema_version supported", str(version))

        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        except sqlite3.DatabaseError as exc:
            integrity = f"error: {exc}"
        if integrity != "ok":
            return failed("integrity_check passes", str(integrity)[:200])
        passed("integrity_check passes")
    finally:
        conn.close()

    return checks


def restore_backup(backup_path: Path, target: Path) -> Path:
    """Copy a verified backup to `target`, which must not exist.

    Verification runs first (a corrupt backup is refused before any write);
    the copy is hashed in flight and compared to the manifest afterwards.
    Nothing is ever overwritten, and a failed copy is removed.
    """
    checks = verify_backup(backup_path)
    bad = [check for check in checks if not check.ok]
    if bad:
        raise AosError(
            f"Backup failed verification ({bad[0].name}: {bad[0].detail}); "
            "refusing to restore. Run: python aos.py backup verify "
            f"{backup_path}"
        )
    manifest = json.loads(
        manifest_path_for(backup_path).read_text(encoding="utf-8")
    )
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AosError(f"Cannot create parent directory for {target}: {exc}")
    try:
        out = open(target, "xb")
    except (FileExistsError, IsADirectoryError):
        raise AosError(
            f"Refusing to overwrite existing path: {target}. Restore writes "
            "to a new path only (no overwrite flag by design); move the "
            "existing file aside yourself first. See RECOVERY.md."
        )
    except OSError as exc:
        raise AosError(f"Cannot create {target}: {exc}")
    digest = hashlib.sha256()
    try:
        with out, open(backup_path, "rb") as src:
            for chunk in iter(lambda: src.read(65536), b""):
                digest.update(chunk)
                out.write(chunk)
    except OSError as exc:
        target.unlink(missing_ok=True)
        raise AosError(
            f"Copy failed mid-restore ({exc}); the partial file was removed "
            "and nothing was overwritten. Fix the cause and rerun."
        )
    if digest.hexdigest() != manifest["sha256"]:
        target.unlink(missing_ok=True)
        raise AosError(
            "Restored bytes do not match the manifest sha256 (did the "
            "backup change mid-copy?). The partial file was removed; "
            "nothing was overwritten."
        )
    return target
