# RECOVERY — backing up and restoring the Agentic OS ledger

Everything Agentic OS knows lives in one SQLite file:
`.agentic-os/aos.db`. This page is the drill for the day that file is
damaged or gone. It is written to be followed verbatim by a tired human
after a bad run — every command is copy-pasteable from the repo root.

The commands never overwrite anything. Moving files into place is always
your move, done by hand, the same way commits are.

## If things are broken RIGHT NOW

```bash
# 1. Stop. Do not run any more aos commands against the broken workspace.
# 2. Confirm what is actually wrong:
python3 aos.py doctor
# 3. Check your newest backup is good:
python3 aos.py backup verify .agentic-os/backups/<newest>.db
# 4. Follow "Restore drill" below.
```

If you have no backup, stop here: `.agentic-os/exports/` may hold older
`snapshot` copies and `events-*.jsonl` exports — they have no manifests,
but they are better than nothing. Do not delete anything while deciding.

## Creating a backup

```bash
python3 aos.py backup create
```

- Writes `.agentic-os/backups/aos-backup-<UTC-stamp>.db` through the
  SQLite backup API — safe while the database is in use, never a raw file
  copy (a raw copy of a WAL database can tear transactions).
- Writes a sibling manifest `aos-backup-<UTC-stamp>.manifest.json`
  recording `created_at`, `source_db_path`, `schema_version`,
  `size_bytes`, `sha256`, and the tool version.
- Refuses (exit 1, before anything is written) if the live database
  already fails `PRAGMA integrity_check` — a backup of corruption is not
  a backup. Grosser corruption can instead abort with a database error
  before the check even runs; either way, no backup of a damaged ledger
  is created.
- The backup and its manifest are a pair. If you copy a backup somewhere
  (do — keep at least one off this machine), copy both files together.

Good habits: create a backup before anything schema- or migration-shaped,
after any milestone you would hate to lose, and verify right after
creating. Verification is cheap; discovering a bad backup during a
disaster is not.

## Verifying a backup

```bash
python3 aos.py backup verify .agentic-os/backups/aos-backup-<stamp>.db
```

Runs these checks in order and stops at the first failure (exit 1):

1. backup file exists
2. manifest file exists (beside the backup, same stem)
3. manifest well-formed (known format, all fields present)
4. size matches manifest
5. sha256 matches manifest
6. backup opens as SQLite
7. schema_version supported (backup ↔ manifest ↔ this build)
8. `PRAGMA integrity_check` passes

Why both a hash and an integrity check: a single flipped bit (bad disk,
bad copy) passes `integrity_check` — SQLite pages carry no checksums —
but fails the sha256. Structural damage under a manifest that was
regenerated to match fails `integrity_check`. Each check catches what the
other cannot.

`verify` needs no workspace and never writes anything — it works on a
backup copied to a USB stick on a machine that has never run aos, and it
opens the file read-only (`immutable`), so it cannot leave `-wal`/`-shm`
droppings next to your backup.

**If verify fails: do not restore from that copy.** Try the next-newest
backup until one passes.

## Restore drill

Scenario: `aos.db` is corrupt or deleted. Doctor fails or every command
exits with a database error.

```bash
# 0. From the repo root. Stop running anything else against the workspace.

# 1. Move the damaged database ASIDE (never delete it — it may still be
#    partially readable if all backups turn out bad). Move its WAL
#    companions with it; a stale -wal next to a restored db is poison:
mv .agentic-os/aos.db     .agentic-os/aos.db.damaged-$(date -u +%Y%m%dT%H%M%SZ) 2>/dev/null
mv .agentic-os/aos.db-wal .agentic-os/aos.db-wal.damaged 2>/dev/null
mv .agentic-os/aos.db-shm .agentic-os/aos.db-shm.damaged 2>/dev/null

# 2. Pick the newest backup that verifies clean:
ls -t .agentic-os/backups/*.db
python3 aos.py backup verify .agentic-os/backups/aos-backup-<stamp>.db

# 3. Restore it to the live path (now free — restore refuses to
#    overwrite, so step 1 must have happened):
python3 aos.py backup restore .agentic-os/backups/aos-backup-<stamp>.db \
    --to .agentic-os/aos.db

# 4. Prove the patient is alive:
python3 aos.py doctor
python3 aos.py status

# 5. Rebuild the Obsidian mirror (cheap, fully derived):
python3 aos.py sync
```

Anything recorded after the backup was created is gone from the ledger.
Check `.agentic-os/exports/` for `events-*.jsonl` files newer than the
backup — they list every event and can guide re-entering lost work by
hand.

## Restoring somewhere else (inspection copy)

`restore` writes to any path that does not exist yet, so you can open a
backup without touching the live workspace:

```bash
python3 aos.py backup restore .agentic-os/backups/aos-backup-<stamp>.db \
    --to /tmp/inspect/aos.db
# Peek inside (no sqlite3 CLI needed — stdlib only, like everything here):
python3 -c "import sqlite3; \
    [print(*row) for row in sqlite3.connect('/tmp/inspect/aos.db') \
    .execute('SELECT id, title, status FROM tasks')]"
```

Note: a database file alone is not a full workspace — packs, exports, and
the Obsidian vault live beside it. Restoring into a fresh root gives you
the ledger's data, not the files its packs table points at. For a real
recovery, restore into the original workspace (drill above).

## Detecting corruption early

- `python3 aos.py doctor` runs `PRAGMA integrity_check` on the live
  database on every invocation — run it routinely, not just on bad days.
- `backup create` refuses a source that fails integrity_check, so a
  nightly create doubles as a nightly health check.
- Verify backups after copying them anywhere: the sha256 in the manifest
  is the proof the copy is bit-identical.

## What not to do

- **Do not** back up by copying `aos.db` with `cp` while anything might
  write to it — a WAL database can tear. `backup create` (or `snapshot`)
  uses the SQLite backup API precisely to avoid this.
- **Do not** delete or "clean up" `aos.db-wal` / `aos.db-shm` next to a
  live database — the `-wal` file contains committed transactions.
- **Do not** restore over an existing file. There is no `--force`/
  `--overwrite` flag on purpose; if restore refuses, the file in the way
  is yours to move, deliberately.
- **Do not** separate a backup from its `.manifest.json` — verify (and
  therefore restore) will refuse without it.
- **Do not** hand-edit anything inside `.agentic-os/` — including
  "fixing" a backup or manifest by hand. If a backup fails verify,
  distrust it and use an older one.
- **Do not** keep every backup only on this machine. Two files —
  the backup and its manifest — are all another machine needs.
