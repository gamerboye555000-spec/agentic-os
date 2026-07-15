"""Backup-first schema migrations (U-M1; contract:
agentic-os-v0.2-u-m1-migration-contract.md).

This module is the machinery, and — deliberately — carries zero production
migrations. `MIGRATIONS` is empty and `LATEST_VERSION` is derived from
`db.SCHEMA_VERSION` rather than typed as a second literal, so the registry
and the schema can never drift apart. U-M2 adds the first real step.

Three facts shaped the design, each measured rather than assumed:

- `db.open_db()` refuses any version != SCHEMA_VERSION, so a database that
  is *pending migration* cannot be opened through it. The version gate is
  the door migration must walk through, so this module reads the ledger
  itself and applies migration-specific version policy. The gate is not
  relaxed for anyone else: normal commands still refuse, which is what
  "normal commands never auto-migrate" means.

- `conn.backup(dest)` HANGS FOREVER when `conn` holds its own open
  BEGIN IMMEDIATE (backup_step sees SQLITE_BUSY against the connection's own
  write transaction and CPython retries on an unbounded sleep loop). So the
  write lock is held on one connection while the snapshot is sourced from a
  second reader connection — under WAL the reader is not blocked, and since
  the holder has written nothing, it observes exactly the committed
  pre-migration state. Other writers stay locked out the whole time, so
  there is no window between snapshot and first mutation.

- A URI `mode=ro` open of a WAL database leaves -shm/-wal behind forever (a
  read-only connection cannot clean up on close), and a plain read-write
  open checkpoints a dirty -wal on close, changing aos.db's bytes. A
  read-write handle with PRAGMA query_only=ON does neither, and still reads
  through the -wal so the version is never stale. That is the read path for
  status/plan.
"""

from __future__ import annotations

import os
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import db, events, ops, secretscan, utils
from .utils import AosError

#: The highest schema version this build understands. Derived from the one
#: canonical declaration so a bump cannot land in only one of two places.
LATEST_VERSION: int = int(db.SCHEMA_VERSION)

MIGRATION_EVENT_ACTION = "migrate"
MIGRATION_EVENT_ENTITY = "system"


@dataclass(frozen=True)
class Migration:
    """One stepwise schema transition: exactly from_version → from_version+1.

    `apply` receives the migration connection inside an already-open
    transaction. It must issue schema/data changes only — never COMMIT,
    ROLLBACK, or touch meta.schema_version, both of which this module owns.
    """

    from_version: int
    to_version: int
    migration_id: str
    apply: Callable[[sqlite3.Connection], None]


#: The canonical production registry. EMPTY AT U-M1 BY CONTRACT (M1.0): the
#: framework ships before the first schema change. Never populated by
#: importing arbitrary files or by evaluating names read from the database —
#: a literal tuple in source is the whole discovery mechanism.
MIGRATIONS: tuple[Migration, ...] = ()


# ---------------------------------------------------------------------------
# Schema version reading (M1.1)

def _safe_version_repr(raw: str) -> str:
    """A malformed version is still a database VALUE, and a value can be
    secret-shaped (U-C3). Quote it for the human through the same redaction
    choke point every event write uses, and bound its length so a corrupted
    megabyte-long cell cannot become the error message.
    """
    shown = secretscan.redact_tree(raw)
    if shown != raw:
        return shown
    return repr(raw if len(raw) <= 40 else raw[:40] + "…")


def _parse_version(raw: object) -> int:
    """Canonical non-negative base-10 integer, or AosError.

    Strict on purpose: int() alone accepts " 1 ", "+1", and "1_0", turning a
    corrupted value into a plausible version and then migrating from the
    wrong place. Round-tripping through str() accepts only the canonical
    spelling.
    """
    if raw is None:
        raise AosError(
            "Database schema_version is null. Refusing to guess a version. "
            "See TROUBLESHOOTING.md; restore from a verified backup."
        )
    if not isinstance(raw, str):
        raise AosError(
            f"Database schema_version is not text (found "
            f"{type(raw).__name__}). Refusing to guess a version. "
            "See TROUBLESHOOTING.md."
        )
    try:
        value = int(raw)
    except ValueError:
        raise AosError(
            f"Database schema_version {_safe_version_repr(raw)} is not an "
            "integer. Refusing to guess a version. See TROUBLESHOOTING.md."
        )
    if str(value) != raw:
        raise AosError(
            f"Database schema_version {_safe_version_repr(raw)} is not "
            f"canonical (expected {str(value)!r}). Refusing to reinterpret "
            "it. See TROUBLESHOOTING.md."
        )
    if value < 0:
        raise AosError(
            f"Database schema_version {value} is negative. Refusing to "
            "reinterpret it. See TROUBLESHOOTING.md."
        )
    return value


def read_schema_version(conn: sqlite3.Connection) -> int:
    """The live schema version, or AosError naming what is wrong.

    Fetches ALL matching rows rather than LIMIT 1: a `meta` table built
    without its PRIMARY KEY could otherwise smuggle an ambiguous version
    past the check.
    """
    try:
        rows = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            raise AosError(
                "Database has no `meta` table, so it carries no schema "
                "version. This is not an Agentic OS ledger (or it is "
                "damaged). Refusing to migrate. See TROUBLESHOOTING.md."
            )
        raise
    if not rows:
        raise AosError(
            "Database has no schema_version row. Refusing to assume a "
            "version. See TROUBLESHOOTING.md; restore from a verified "
            "backup."
        )
    if len(rows) > 1:
        raise AosError(
            f"Database has {len(rows)} schema_version rows; exactly one is "
            "required. Refusing to pick one. See TROUBLESHOOTING.md."
        )
    return _parse_version(rows[0][0])


# ---------------------------------------------------------------------------
# Registry validation (M1.4)

def _is_version(value: object) -> bool:
    # bool is an int subclass; True would otherwise pass as version 1.
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def validate_registry(
    registry: tuple[Migration, ...] = MIGRATIONS,
    latest: int = LATEST_VERSION,
) -> None:
    """Refuse a malformed registry BEFORE any snapshot or mutation.

    An empty registry is valid — that is the production state at U-M1.
    """
    if not _is_version(latest):
        raise AosError(
            f"Migration registry is invalid: latest version {latest!r} is "
            "not a non-negative integer."
        )
    seen_from: dict[int, str] = {}
    seen_to: dict[int, str] = {}
    seen_ids: set[str] = set()
    for migration in registry:
        if not isinstance(migration, Migration):
            raise AosError(
                "Migration registry is invalid: entry is not a Migration."
            )
        ident = migration.migration_id
        if not isinstance(ident, str) or not ident.strip():
            raise AosError(
                "Migration registry is invalid: a migration has an empty or "
                "non-string identifier."
            )
        if not _is_version(migration.from_version) or not _is_version(
            migration.to_version
        ):
            raise AosError(
                f"Migration registry is invalid: migration {ident!r} has "
                "non-integer or negative versions."
            )
        if migration.to_version != migration.from_version + 1:
            raise AosError(
                f"Migration registry is invalid: migration {ident!r} goes "
                f"{migration.from_version} → {migration.to_version}; every "
                "step must advance by exactly one version."
            )
        if not callable(migration.apply):
            raise AosError(
                f"Migration registry is invalid: migration {ident!r} has no "
                "callable apply."
            )
        if migration.to_version > latest:
            raise AosError(
                f"Migration registry is invalid: migration {ident!r} targets "
                f"version {migration.to_version}, beyond the supported "
                f"latest version {latest}."
            )
        if migration.from_version in seen_from:
            raise AosError(
                f"Migration registry is invalid: migrations "
                f"{seen_from[migration.from_version]!r} and {ident!r} both "
                f"start at version {migration.from_version} (ambiguous path)."
            )
        if migration.to_version in seen_to:
            raise AosError(
                f"Migration registry is invalid: migrations "
                f"{seen_to[migration.to_version]!r} and {ident!r} both "
                f"target version {migration.to_version} (ambiguous path)."
            )
        if ident in seen_ids:
            raise AosError(
                f"Migration registry is invalid: duplicate migration "
                f"identifier {ident!r}."
            )
        seen_from[migration.from_version] = ident
        seen_to[migration.to_version] = ident
        seen_ids.add(ident)

    if not registry:
        return
    # One contiguous chain: no gaps between the lowest and highest step.
    lowest = min(seen_from)
    highest = max(seen_to)
    for version in range(lowest, highest):
        if version not in seen_from:
            raise AosError(
                f"Migration registry is invalid: no migration from version "
                f"{version} (gap in the chain {lowest} → {highest})."
            )


# ---------------------------------------------------------------------------
# Planning (M1.5)

def plan_migrations(
    current: int,
    target: int | None = None,
    registry: tuple[Migration, ...] = MIGRATIONS,
    latest: int = LATEST_VERSION,
) -> tuple[Migration, ...]:
    """The ordered steps from `current` to `target` (default: `latest`).

    Deterministic and side-effect free: same inputs, same plan, no I/O.
    """
    validate_registry(registry, latest)
    if current > latest:
        raise AosError(
            f"Database schema version {current} is newer than this build "
            f"supports ({latest}). Upgrade Agentic OS; this build will not "
            "touch a database from the future. See TROUBLESHOOTING.md."
        )
    if target is None:
        target = latest
    if not _is_version(target):
        raise AosError(f"Invalid target version {target!r}.")
    if target > latest:
        raise AosError(
            f"Target version {target} is not supported by this build "
            f"(latest: {latest})."
        )
    if target < current:
        raise AosError(
            f"Refusing to downgrade: database is at version {current}, "
            f"target {target} is lower. Migrations are forward-only; to go "
            "back, restore a verified pre-migration backup. See RECOVERY.md."
        )
    by_from = {m.from_version: m for m in registry}
    plan: list[Migration] = []
    version = current
    while version < target:
        migration = by_from.get(version)
        if migration is None:
            raise AosError(
                f"No migration path from version {version} to {target}: no "
                f"migration starts at {version}. See TROUBLESHOOTING.md."
            )
        plan.append(migration)
        version = migration.to_version
    return tuple(plan)


# ---------------------------------------------------------------------------
# Filesystem + connection safety (M1.9, M1.3)

def _object_kind(mode: int) -> str:
    if stat.S_ISLNK(mode):
        return "a symlink"
    if stat.S_ISDIR(mode):
        return "a directory"
    if stat.S_ISFIFO(mode):
        return "a FIFO"
    if stat.S_ISSOCK(mode):
        return "a socket"
    if stat.S_ISBLK(mode):
        return "a block device"
    if stat.S_ISCHR(mode):
        return "a character device"
    return "not a regular file"


def require_regular_db_file(db_path: Path) -> None:
    """Refuse any live database path that is not a regular file.

    lstat, never stat: stat would follow a symlink and defeat the check.
    Fail-closed — the object is left exactly as found.
    """
    try:
        st = os.lstat(db_path)
    except FileNotFoundError:
        raise AosError(
            f"No database at {db_path}. Run: python aos.py init"
        )
    except OSError as exc:
        raise AosError(f"Cannot inspect {db_path}: {exc.strerror}")
    if not stat.S_ISREG(st.st_mode):
        raise AosError(
            f"Refusing to migrate {db_path}: it is {_object_kind(st.st_mode)}, "
            "not a regular file. The live ledger must be a real database "
            "file. Nothing was changed."
        )


def open_readonly(db_path: Path) -> sqlite3.Connection:
    """A connection that SQLite itself will not let us write.

    query_only=ON rather than URI mode=ro: a read-only connection cannot
    clean up the -shm/-wal it must create to read a WAL database, so mode=ro
    leaves lock artifacts behind forever. immutable=1 would avoid that but
    ignores the -wal and hands back a STALE version — the exact hazard the
    stale-state rules exist to prevent. query_only reads through the -wal,
    refuses writes at the engine, and does not checkpoint on close, so
    aos.db's bytes cannot change.
    """
    conn = db.connect(db_path)
    try:
        conn.execute("PRAGMA query_only=ON")
    except BaseException:
        conn.close()
        raise
    return conn


# ---------------------------------------------------------------------------
# Status / plan (read-only)

def status(
    db_path: Path,
    registry: tuple[Migration, ...] = MIGRATIONS,
    latest: int = LATEST_VERSION,
) -> dict:
    """Read-only migration status. Never mutates a byte."""
    require_regular_db_file(db_path)
    conn = open_readonly(db_path)
    try:
        current = read_schema_version(conn)
    finally:
        conn.close()
    validate_registry(registry, latest)
    if current > latest:
        raise AosError(
            f"Database schema version {current} is newer than this build "
            f"supports ({latest}). Upgrade Agentic OS; this build will not "
            "touch a database from the future. See TROUBLESHOOTING.md."
        )
    plan = plan_migrations(current, latest, registry, latest)
    return {
        "db_path": str(db_path),
        "current_version": current,
        "latest_version": latest,
        "pending": bool(plan),
        "plan": [
            {
                "from": m.from_version,
                "to": m.to_version,
                "migration_id": m.migration_id,
            }
            for m in plan
        ],
    }


def plan_report(
    db_path: Path,
    target: int | None = None,
    registry: tuple[Migration, ...] = MIGRATIONS,
    latest: int = LATEST_VERSION,
) -> dict:
    """Read-only plan. Creates no backup, event, temp file, or mutation."""
    require_regular_db_file(db_path)
    conn = open_readonly(db_path)
    try:
        current = read_schema_version(conn)
    finally:
        conn.close()
    plan = plan_migrations(current, target, registry, latest)
    return {
        "db_path": str(db_path),
        "current_version": current,
        "latest_version": latest,
        "target_version": latest if target is None else target,
        "steps": [
            {
                "from": m.from_version,
                "to": m.to_version,
                "migration_id": m.migration_id,
            }
            for m in plan
        ],
    }


# ---------------------------------------------------------------------------
# Apply (M1.6)

class MigrationStepError(AosError):
    """A step failed. Carries the safe, bounded facts a human needs.

    `applied` is the steps that COMMITTED before the failure: non-empty means
    the database is partially advanced and the human must decide between a
    corrected retry and restoring the snapshot.
    """

    def __init__(
        self,
        message: str,
        *,
        applied: tuple[dict, ...] = (),
        snapshot: Path | None = None,
    ):
        super().__init__(message)
        self.applied = applied
        self.snapshot = snapshot


def restore_hint(snapshot: Path, db_path: Path) -> str:
    return (
        f"The verified pre-migration snapshot is intact:\n"
        f"  {snapshot}\n"
        f"Restore it to a NEW path, then adopt it yourself:\n"
        f"  python aos.py backup restore {snapshot} --to {db_path}.restored\n"
        f"See RECOVERY.md for the full drill. Do NOT edit schema_version by "
        f"hand."
    )


def apply_migrations(
    aos_dir: Path,
    target: int | None = None,
    registry: tuple[Migration, ...] = MIGRATIONS,
    latest: int = LATEST_VERSION,
) -> dict:
    """Migrate the live ledger, snapshotting first. See M1.6 for ordering.

    `registry`/`latest` are injectable so tests can prove v1→v2 and
    multi-step behavior against a synthetic registry. Production callers pass
    neither, so the empty production registry always applies.
    """
    from . import backup  # local: keeps the import graph acyclic

    db_path = aos_dir / utils.DB_FILENAME
    require_regular_db_file(db_path)

    # --- read-only pre-flight. A no-op apply must never open read-write:
    # that is what makes "not one byte changed" true rather than likely.
    conn = open_readonly(db_path)
    try:
        current = read_schema_version(conn)
    finally:
        conn.close()
    plan = plan_migrations(current, target, registry, latest)
    if not plan:
        return {
            "migrated": False,
            "current_version": current,
            "latest_version": latest,
            "snapshot": None,
            "applied": (),
        }

    conn = db.connect(db_path)
    applied: list[dict] = []
    snapshot_path: Path | None = None
    try:
        # Explicit transaction control; the legacy isolation_level would
        # begin/commit implicitly underneath us.
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")   # write lock: other writers blocked

        # Re-read INSIDE the lock. A plan computed before the lock is only a
        # hypothesis; this is where it becomes authoritative.
        locked_version = read_schema_version(conn)
        if locked_version != current:
            raise AosError(
                f"Schema version changed from {current} to {locked_version} "
                "while the migration was being planned; refusing to act on a "
                "stale plan. Nothing was changed — rerun: "
                "python aos.py migrate plan"
            )
        plan = plan_migrations(locked_version, target, registry, latest)
        if not plan:
            conn.execute("ROLLBACK")
            return {
                "migrated": False,
                "current_version": locked_version,
                "latest_version": latest,
                "snapshot": None,
                "applied": (),
            }

        # --- snapshot BEFORE the first mutation, sourced from a SECOND
        # connection: conn.backup() on the lock holder itself deadlocks
        # (SQLITE_BUSY against its own write transaction, retried forever).
        # The reader sees exactly the committed pre-migration state, and the
        # lock we hold means no other writer can move it.
        reader = db.connect(db_path)
        try:
            result = backup.write_backup_pair(reader, aos_dir)
        finally:
            reader.close()
        snapshot_path = result["path"]

        checks = backup.verify_backup(
            snapshot_path, expected_schema_version=str(locked_version)
        )
        bad = [check for check in checks if not check.ok]
        if bad:
            raise AosError(
                f"Pre-migration snapshot failed verification ({bad[0].name}: "
                f"{bad[0].detail}); refusing to migrate. The database was not "
                "changed. See TROUBLESHOOTING.md."
            )

        snapshot_ref = (
            f"{backup.BACKUPS_DIRNAME}/{snapshot_path.name}"  # relative: M1.10
        )

        for index, migration in enumerate(plan):
            if index > 0:
                conn.execute("BEGIN IMMEDIATE")
            # Every step re-confirms its own starting point under its own
            # lock, so neither a stale plan nor a racing apply can double-run.
            step_version = read_schema_version(conn)
            if step_version != migration.from_version:
                conn.execute("ROLLBACK")
                raise MigrationStepError(
                    f"Schema version is {step_version}, but the next "
                    f"migration starts at {migration.from_version}; another "
                    "process may have migrated concurrently. Refusing to "
                    "apply. Rerun: python aos.py migrate status",
                    applied=tuple(applied),
                    snapshot=snapshot_path,
                )
            try:
                migration.apply(conn)
                cursor = conn.execute(
                    "UPDATE meta SET value = ? WHERE key = 'schema_version'",
                    (str(migration.to_version),),
                )
                if cursor.rowcount != 1:
                    # Unreachable unless the step itself removed or duplicated
                    # the row. An UPDATE matching 0 rows "succeeds" silently,
                    # which would commit an event claiming a version bump that
                    # never happened — the ledger would lie. Fail the step.
                    raise AosError(
                        f"Migration {migration.migration_id!r} left "
                        f"{cursor.rowcount} schema_version row(s); exactly one "
                        "must exist. The step was rolled back."
                    )
                events.emit(
                    conn,
                    actor=ops.ACTOR_HUMAN,
                    entity=MIGRATION_EVENT_ENTITY,
                    entity_id=None,
                    action=MIGRATION_EVENT_ACTION,
                    payload={
                        "from": migration.from_version,
                        "to": migration.to_version,
                        "migration_id": migration.migration_id,
                        "snapshot": snapshot_ref,
                    },
                )
                conn.execute("COMMIT")
            except BaseException as exc:
                # BaseException, so the rollback runs even on Ctrl-C: this
                # step's schema change, version bump, and event die together
                # and no later step runs, whatever is propagating.
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                if isinstance(exc, MigrationStepError):
                    raise
                if not isinstance(exc, Exception):
                    # KeyboardInterrupt/SystemExit are the operator talking,
                    # not a migration failure. Rolled back; let it through.
                    raise
                # Only the exception CLASS name — never str(exc), which can
                # carry SQL text or row values out of a step body (M1.10).
                raise MigrationStepError(
                    f"Migration {migration.migration_id!r} "
                    f"({migration.from_version} → {migration.to_version}) "
                    f"failed ({exc.__class__.__name__}) and was rolled back "
                    "completely; no later migration ran.",
                    applied=tuple(applied),
                    snapshot=snapshot_path,
                ) from exc
            applied.append(
                {
                    "from": migration.from_version,
                    "to": migration.to_version,
                    "migration_id": migration.migration_id,
                }
            )
        final_version = read_schema_version(conn)
    except BaseException:
        # Roll back the lock-holding transaction if a pre-mutation step (the
        # snapshot, its verification) failed while it was still open.
        try:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        conn.close()
        raise
    conn.close()
    return {
        "migrated": True,
        "current_version": final_version,
        "latest_version": latest,
        "snapshot": snapshot_path,
        "applied": tuple(applied),
    }
