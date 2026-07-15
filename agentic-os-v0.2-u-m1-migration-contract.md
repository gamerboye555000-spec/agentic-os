# Agentic OS v0.2 — U-M1 migration kit contract

Task: **T-0011 — U-M1 migration kit before any schema v2**
Baseline: `c0de5cf18842ff588fff6a6206748c52fabeaa70`
Branch: `v0.2-u-m1-migrations`

U-M1 builds the backup-first migration framework that must exist **before**
any schema change is ever written. It ships the machinery and zero
production migrations. U-M2 (the actual memory-v2 schema) stays blocked
until U-M1 is merged.

This contract is pinned before production code changes. Where the task
brief's vocabulary and the codebase disagree, the codebase wins and the
deviation is recorded here (see M1.1).

---

## M1.0 — Current production schema version (discovered)

`agentic_os/db.py` declares:

```python
SCHEMA_VERSION = "1"
```

**The current production schema version is 1.** It is written once by
`ops.initialize()` into the `meta` table:

```sql
INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)
```

`LATEST_VERSION` after U-M1 is therefore **1**, and the production registry
is **empty**. U-M1 does not raise the production latest version and does not
introduce the memory-v2 schema.

`migrations.LATEST_VERSION` is **derived** from `db.SCHEMA_VERSION`, not
typed as a second literal, so the two can never drift apart. A guard test
pins `LATEST_VERSION == 1` and `MIGRATIONS == ()` so that raising either one
is a deliberate, visible act.

## M1.1 — Deviation: there is no `schema_version` table

The task brief says "schema_version table". **No such table exists.** The
version is one row in the generic `meta` key/value table
(`key TEXT PRIMARY KEY, value TEXT`), stored as **TEXT**, not INTEGER.

The brief's refusal cases map onto the real storage as:

| Brief wording | Real condition |
|---|---|
| schema_version table is missing | `meta` table absent, or no `schema_version` row |
| contains zero rows | no `schema_version` row in `meta` |
| contains multiple rows | more than one `schema_version` row (only reachable if `meta` was built without its PRIMARY KEY — read defensively anyway) |
| version is null | `meta.value IS NULL` |
| malformed / negative / non-integer | value is not a canonical non-negative base-10 integer string |

The reader fetches **all** matching rows rather than `LIMIT 1`, so a `meta`
table lacking its primary key cannot smuggle an ambiguous version past the
check.

**Version parsing is canonical-strict.** A value parses only if
`value == str(int(value))` and `int(value) >= 0`. Accepted: `"0"`, `"1"`,
`"12"`. Refused: `"01"`, `" 1"`, `"+1"`, `"1.0"`, `"1 "`, `"0x1"`, `"-1"`,
`""`, `None`, `"one"`. Rationale: a lenient parser turns a corrupted value
into a plausible-looking version and then migrates from the wrong place.
`int()` alone accepts `" 1 "`, `"+1"`, and `"1_0"` — canonical round-trip
does not.

**Never reinterpret or rewrite a version.** The only write to
`meta.schema_version` outside `ops.initialize()` is a migration step's own
exact `from → to` update, inside that step's transaction.

## M1.2 — Why `migrate` cannot use `db.open_db()`

`db.open_db()` (and therefore `cli._ledger`) calls `_check_schema_version`,
which raises when `meta.schema_version != db.SCHEMA_VERSION`. A database
that is *pending migration* is by definition at a version below the build's
latest — so `open_db` would refuse it, and migration could never run. The
version gate is exactly the door migration must be able to walk through.

`migrate` therefore uses its own connection path in `migrations.py` and
applies **migration-specific** version policy (M1.7). It does **not** relax
the gate for anyone else: `db.open_db()` is untouched, so every normal
command keeps refusing unsupported versions exactly as it does today.

This is the mechanism behind "normal commands never auto-migrate": migration
lives behind one explicit command, and nothing else calls it.

## M1.3 — Read path: `PRAGMA query_only=ON` (measured, not assumed)

`migrate status` and `migrate plan` must be read-only *byte-for-byte* and
must leave no temporary file or lock artifact. Three candidate read paths
were measured against a real workspace before choosing:

| Read path | `aos.db` bytes | Droppings after close | Stale reads |
|---|---|---|---|
| URI `mode=ro` | unchanged | **leaves `-shm`/`-wal` forever** (a read-only connection cannot clean up) | no |
| URI `mode=ro&immutable=1` | unchanged | none | **yes — ignores `-wal`** |
| plain read-write | unchanged at rest | none (last closer cleans up) | no; **but checkpoints a dirty `-wal` on close → bytes change** |
| **read-write + `query_only=ON`** | **unchanged** | **none** | **no** |

Chosen: **read-write file handle + `PRAGMA query_only=ON`.** Measured
properties:

- any write is rejected by SQLite itself (`attempt to write a readonly
  database`) — the guarantee does not depend on us remembering not to write;
- reads resolve through `-wal`, so the version read is never stale;
- close does **not** checkpoint, so `aos.db` bytes cannot change even when a
  dirty `-wal` exists;
- on a quiescent workspace the directory is left exactly as found.

`immutable=1` is rejected outright: it would ignore the `-wal` and hand back
a stale version — the precise hazard M1.8 exists to prevent. It is correct
in `backup.py` (a backup file genuinely is immutable) and wrong here.

## M1.4 — Migration registry

One canonical registry in `agentic_os/migrations.py`. Migrations are
**never** discovered by importing arbitrary files or by evaluating names
read out of the database — the registry is a literal tuple in source.

```python
@dataclass(frozen=True)
class Migration:
    from_version: int
    to_version: int          # == from_version + 1, always
    migration_id: str        # stable, safe to print
    apply: Callable[[sqlite3.Connection], None]

MIGRATIONS: tuple[Migration, ...] = ()   # production: empty at U-M1
LATEST_VERSION: int = int(db.SCHEMA_VERSION)   # 1
```

`validate_registry(migrations, latest)` runs **before** any snapshot or
mutation and refuses:

- non-integer / bool / negative versions;
- `to_version != from_version + 1` (no skips, no backward steps, no
  self-loops);
- duplicate `from_version` (ambiguous path);
- duplicate `to_version` (ambiguous path);
- any step whose `to_version` exceeds `latest`;
- gaps: the union of steps must form one contiguous chain;
- empty or non-string `migration_id`; duplicate `migration_id`;
- a non-callable `apply`.

An empty registry is **valid** — it is the production state at U-M1.

**Synthetic registries are test-only.** `plan_migrations` / `apply_migrations`
accept an injected `registry` + `latest` for tests to prove v1→v2 and
multi-step behavior. The production code path passes neither, so the
defaults (`MIGRATIONS`, `LATEST_VERSION`) always apply. Synthetic test
migrations must never become production schema migrations; a guard test pins
the production registry as empty.

## M1.5 — CLI contract

Added to the existing canonical CLI (so `python3 aos.py`,
`python3 -m agentic_os`, and `python3 aos.pyz` are identical by
construction — all three import the same `agentic_os.cli`):

```
aos migrate status [--json]
aos migrate plan [--target N] [--json]
aos migrate apply [--target N]
```

**`migrate status`** — read-only. Reports the database path, current schema
version, supported latest version, and whether migrations are pending.
Refuses missing/malformed/duplicate/negative/newer-than-supported versions.
Bounded output; never prints SQL, database contents, secrets, or row values.

**`migrate plan`** — read-only. Prints the ordered version transitions that
would run. With no pending production migration, reports an empty plan
clearly (`No migrations pending.`) and exits 0. Creates no backup, event,
temporary file, lock artifact, or database mutation. `--target` is accepted
only when supported and not below current; downgrade planning refuses.

**`migrate apply`** — requires an initialized workspace and a regular SQLite
file. No pending migration ⇒ successful no-op: no backup, no migration
event, no database-byte mutation (and, per M1.6, no read-write open at all).

## M1.6 — Apply ordering, and the deadlock that shaped it

Required order: validate path → acquire write lock → re-read version →
snapshot → verify → only then mutate.

**Measured obstacle:** `conn.backup(dest)` **hangs forever** when `conn`
itself holds an open `BEGIN IMMEDIATE`. `sqlite3_backup_step` returns
`SQLITE_BUSY` against its own connection's write transaction and CPython's
`Connection.backup` retries on a sleep loop with no bound. The naive
"lock then snapshot on the same connection" reading of the order deadlocks.

**Resolution (measured to work):** the write lock is held on the migration
connection while the snapshot is sourced from a **second, separate reader
connection**. Under WAL, a reader is not blocked by the holder's `RESERVED`
lock, and because the holder has written nothing yet, the reader observes
exactly the committed pre-migration state. Other writers stay blocked
throughout (verified: `database is locked`).

This is *stronger* than releasing the lock to snapshot and re-taking it:
there is no window in which another writer can commit between the snapshot
and the first step, so the snapshot is provably the pre-migration state.

Final ordering:

1. `_require_regular_db_file(db_path)` — lstat gate (M1.9).
2. Read version + validate registry + compute plan on a `query_only`
   connection (M1.3). **If the plan is empty → print the no-op and return.
   No read-write open ever happens** — that is what makes "no byte
   mutation" true rather than merely likely.
3. Open the migration connection (`isolation_level=None`) and
   `BEGIN IMMEDIATE` → acquires the write lock.
4. Re-read the version **inside the lock**. If it differs from step 2, the
   plan is stale → refuse before any mutation (M1.8).
5. Snapshot via a second reader connection through the existing U-C2 backup
   writer; verify it (M1.7). Failure here → `ROLLBACK` → live database
   untouched.
6. Execute step 1 **inside the transaction opened at step 3** — the lock is
   never released between verify and first mutation. Steps 2..N each open
   their own `BEGIN IMMEDIATE`.

## M1.7 — Snapshot reuse (no duplicated backup logic)

`backup.py` is refactored to **expose** what it already does, not to grow a
second implementation:

- `write_backup_pair(conn, aos_dir)` — the existing body of `create_backup`
  minus the event: integrity_check, `conn.backup(dest)` through the SQLite
  backup API, sha256, manifest write. Returns `{path, manifest_path,
  manifest}`.
- `create_backup(conn, aos_dir)` — now `write_backup_pair(...)` + the
  existing `backup_create` event. **Behavior is byte-identical to baseline.**
- `verify_backup(path, *, expected_schema_version=None)` — `None` keeps the
  current meaning ("this build's `SCHEMA_VERSION`") and the current
  diagnostic string exactly; a caller-supplied version is compared with its
  own accurate wording.

**Why the snapshot emits no `backup_create` event.** Emitting it would need
a commit, which would release the write lock acquired in M1.6 step 3 and
reopen the very window the lock exists to close. Instead the snapshot's
identity is recorded inside the `system/migrate` event, committed atomically
with the step it protects. This extends U-C2's own rule (a backup never
contains its own event) rather than contradicting it.

If a migration fails before any step commits, a verified snapshot is left on
disk with no event referencing it. That is the safe outcome, and the failure
diagnostic names the file.

**Why `expected_schema_version` had to be added now.** `verify_backup`
currently hard-fails unless the backup's version equals `db.SCHEMA_VERSION`.
The moment U-M2 ships (`SCHEMA_VERSION = "2"`), a *correct* pre-migration
snapshot of a v1 database would fail that check and migration would refuse
to proceed — the framework would deadlock on the first real migration it was
built for. The snapshot is verified against the version it was actually
taken at. Today `current == SCHEMA_VERSION == "1"`, so this is a no-op in
production and provable only by direct test; it is not dead code, it is the
one line that makes U-M2 possible.

## M1.8 — Transactions, failure, concurrency, stale state

Each step runs in one explicit transaction containing **all three** of:

1. the schema change;
2. the exact `meta.schema_version` update `from → to`;
3. exactly one `system` / `migrate` event.

The version `UPDATE` asserts `rowcount == 1`. An `UPDATE` matching zero rows
"succeeds" silently, so a step that removed or duplicated the row (a buggy
migration touching `meta`) would otherwise commit an event announcing a bump
that never happened — the ledger would lie about its own shape. Unreachable
today; the assertion is what keeps it unreachable.

Every step re-reads and re-confirms `from_version` inside its own lock
before mutating, so a stale plan can never authorize a mutation and two
concurrent applies cannot both perform the same transition — the loser finds
the version already advanced (or blocks on the write lock and then finds it)
and refuses.

**On step failure:** `ROLLBACK` — the schema change, the version update, and
the event all disappear together; no later step runs; no success is
reported; the verified snapshot remains.

**On failure after earlier steps committed:** the database is reported as
**partially advanced**, with the exact restore command for the pre-migration
snapshot. No automatic destructive rollback across committed steps is ever
attempted — rollback is the existing verified restore workflow (RECOVERY.md).
A corrected retry resumes from the version actually committed, replaying
nothing.

**Readers** are unaffected: each step is one transaction, so a concurrent
reader sees the state strictly before or strictly after it.

No daemon, no distributed lock, no new lock table — only SQLite's own
`BEGIN IMMEDIATE`.

## M1.9 — Filesystem safety

Before migrating, the live database path is `os.lstat`-ed (never `stat` —
`stat` would follow a symlink and defeat the check) and refused unless it is
a **regular file**: symlink, directory, FIFO, socket, block/char device, and
missing all refuse, leaving the object exactly as found. This mirrors
`tools/build_zipapp.check_output_path`, the repository's established posture.

Migration only ever touches the resolved live workspace database. Backup
files, exported mirrors, fixture databases outside an explicit test, and
paths sourced from database content are never migrated.

Directories/FIFOs/sockets at `aos.db` are refused *earlier*, by the existing
workspace resolver (`is_file()` is false ⇒ "Not initialized"); symlinks
reach the lstat gate because `is_file()` follows them. Both refuse with exit
1 and change nothing.

## M1.10 — Privacy of diagnostics and events

Event payload carries exactly:

```json
{"from": 1, "to": 2, "migration_id": "…", "snapshot": "backups/aos-backup-….db"}
```

`snapshot` is **relative to the workspace** — never an absolute,
user-identifying path. No SQL, no row values, no filesystem secrets, no
arbitrary exception text. Payloads still pass through `events.emit`'s
`secretscan.redact_tree` choke point (U-C3) like every other event.

Failure diagnostics name only: the failed transition (`1 → 2`), the safe
`migration_id`, the exception **class name** (bounded, data-free — e.g.
`OperationalError`), and the snapshot's relative path. Never `str(exc)` from
a step body, which could embed row values or SQL.

## M1.10a — Documented deviation: the partial-advancement error is multi-line

`cli.py`'s contract says errors are "ONE actionable line on stderr", and
every other `AosError` in the codebase obeys it. The PARTIALLY ADVANCED
message is the **single deliberate exception**: it carries a state
explanation plus a copy-pasteable `backup restore … --to …` command, and
folding a command the user must run at the worst possible moment into a
prose line would make the one error that most needs clarity the hardest to
act on. The rule's intent — no tracebacks, no walls of text for ordinary
failures — is preserved: every other migration refusal is one line, and this
one is bounded, fixed-shape, and contains no SQL, row values, or secrets.

## M1.11 — Fixture

A **deterministic fixture-building source**, not a committed `.db`. A binary
SQLite file is unstable across sqlite versions/page layouts and would embed
wall-clock timestamps from `utils.utc_now_iso()`; it would also collide with
the zipapp allowlist rule against shipping databases.

`tests/fixtures/v1_workspace.py` builds a **real historical v1 workspace
through Night-1 CLI commands only** — projects, tasks, runs, packs,
evidence, decisions, handoffs, memory, agents, and a populated events
journal. Not an empty database. Tests copy it to a temp directory.

## M1.12 — Zipapp

`tools/build_zipapp.runtime_sources` is an allowlist of `*.py` under
`agentic_os/`, so `agentic_os/migrations.py` is included **automatically**
with no builder change. Fixtures, snapshots, tests, and workspaces are `.py`
files outside the package or not `.py` at all, so none can enter the
archive. The archive must run `migrate status`, `plan`, and no-op `apply`
outside the repository with `PYTHONPATH` cleared.

## M1.13 — Exclusions

Untouched: memory schema/behavior, hooks and hook installer, ingest/evidence
semantics, export behavior, agent registry, power modes, workflows and
orchestration, AICompany, and the production schema latest version.
