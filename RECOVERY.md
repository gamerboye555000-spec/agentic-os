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

## Rolling back a migration (U-M1)

**Rollback IS restore.** There is no `migrate down`, no automatic
un-migration, and there never will be one that runs on its own. Reversing a
schema change programmatically is guesswork, and doing it automatically
would silently bypass the snapshot taken to protect you. The snapshot is the
rollback.

This drill is no longer theoretical. There are three production migrations —
**1 → 2, `u-m2-memory-claims-v2`** (memory claims), **2 → 3,
`u-m3-memory-graph-v3`** (the memory graph) and **3 → 4,
`u-a1-agent-passports-v4`** (the governed agent registry) — so
`migrate apply` on an older workspace really does take a snapshot and really
does rebuild tables. Everything below applies to all three exactly.

A tampered agent registry deserves the same posture as a tampered memory
claim: doctor checks 32/33 name the damage, every `agent` write refuses on
it (the no-laundering gate), and the exit is this file's restore drill —
never a write that would recompute the hashes over the edit and hide it.

Each step leaves a database that genuinely **is** its own version: a snapshot
taken before 2 → 3 is a real v2 database, not a v3 database wearing a v2
label. That is what makes restoring one meaningful.

### What `migrate apply` guarantees before it changes anything

1. the whole migration path is validated (a bad registry is refused before
   any file is written);
2. the SQLite write lock is taken — no other writer can move underneath it;
3. the version is re-read and re-confirmed *under that lock*;
4. a snapshot is written into `.agentic-os/backups/` through the same
   machinery as `backup create` (SQLite backup API + manifest);
5. that snapshot is **verified** (sha256 + `integrity_check`);
6. only then does the first step run — and the lock is still held, so the
   snapshot is provably the pre-migration state.

If any of 1-5 fails, nothing is migrated and the database is untouched.
Each step then commits its schema change, its version bump, and its
`system/migrate` event as one transaction — all three, or none.

### Drill: a migration failed and you want to go back

```bash
# 0. Stop. Do not run more aos commands against the workspace.

# 1. Find out where you ACTUALLY are. A failed step rolls back completely,
#    so you may not have moved at all:
python3 aos.py migrate status

# 2. The failure message named the snapshot. Find it if you lost it — it is
#    the newest backup, written just before the migration:
ls -t .agentic-os/backups/*.db

# 3. Verify it BEFORE trusting it:
python3 aos.py backup verify .agentic-os/backups/aos-backup-<stamp>.db

# 4. Move the migrated database aside — never delete it, and take its WAL
#    companions with it (a stale -wal next to a restored db is poison):
mv .agentic-os/aos.db     .agentic-os/aos.db.migrated-$(date -u +%Y%m%dT%H%M%SZ)
mv .agentic-os/aos.db-wal .agentic-os/aos.db-wal.migrated 2>/dev/null
mv .agentic-os/aos.db-shm .agentic-os/aos.db-shm.migrated 2>/dev/null

# 5. Restore the pre-migration snapshot to the now-free live path:
python3 aos.py backup restore .agentic-os/backups/aos-backup-<stamp>.db \
    --to .agentic-os/aos.db

# 6. Prove the patient is alive, and that you are back where you started:
python3 aos.py doctor
python3 aos.py migrate status      # should report the ORIGINAL version
python3 aos.py sync
```

Anything written to the ledger *after* the snapshot — which means during the
migration itself — is gone. That is a very short window by design: the write
lock is held from the snapshot onward, so nothing else could have committed
during it.

### Restoring the v1 pre-migration snapshot (the 1 → 2 case), exactly

The snapshot `migrate apply` takes before the memory-claims migration is a
**schema v1 database**. That changes two steps of the drill above, and both
surprises are expected:

```bash
# 3'. `backup verify` with no arguments checks the snapshot against the
#     version THIS BUILD supports (2). A v1 pre-migration snapshot therefore
#     reports:
#
#       [FAIL] schema_version supported — backup is schema '1', this build
#              supports '2'
#       Backup verification failed: schema_version supported.
#
#     For a pre-migration snapshot that FAIL is not damage — it is the
#     snapshot being what it is supposed to be: the database as it was
#     BEFORE the migration. The checks that tell you whether the bytes are
#     good are the other six (file exists, manifest well-formed, size,
#     sha256, opens as SQLite, integrity_check). Read those. If they pass,
#     the snapshot is sound.
#
#     `migrate apply` itself verified this snapshot AS schema 1 before it
#     touched anything, which is the check that actually mattered.

# 6'. After restoring a v1 snapshot you are back on version 1, so every
#     normal command refuses again — correctly. `doctor` included:
python3 aos.py migrate status     # → schema version: 1, pending: yes
python3 aos.py doctor             # → refuses: schema_version is '1'

#     That is the ledger telling the truth. From here you either stay on the
#     older build, or migrate again once the reason for the failure is fixed:
python3 aos.py migrate apply
python3 aos.py doctor             # now it runs
```

**Never** "fix" that refusal by editing `meta.schema_version` to 2. The
memory table would still be v1 — no `status`, no `pinned`, no
`content_sha256`, no `memory_evidence` — and every command that reads a
claim would fail against a database now claiming to be something it is not.
The version row describes the bytes; it does not change them.

**Never** hand-edit `content_sha256` either. It is a claim's integrity hash,
computed from the claim's own authoritative fields. Editing it to "make
doctor pass" does not repair the claim — it destroys the only evidence that
the claim was altered, and every write against that claim will still refuse.
If `doctor` reports a hash mismatch, see TROUBLESHOOTING.md: the answer is to
restore or to re-state the claim, never to launder it.

### Restoring the v2 pre-migration snapshot (the 2 → 3 case), exactly

Identical in shape to the v1 case above, one version along. The snapshot
`migrate apply` takes before the memory-graph migration is a **schema v2
database**, so:

```bash
# 3''. `backup verify` with no arguments checks the snapshot against the
#      version THIS BUILD supports (3). A v2 pre-migration snapshot therefore
#      reports:
#
#        [FAIL] schema_version supported — backup is schema '2', this build
#               supports '3'
#        Backup verification failed: schema_version supported.
#
#      Expected, and not damage: the snapshot is being exactly what it is
#      supposed to be — the database as it was BEFORE the migration. The
#      checks that tell you whether the BYTES are good are the other six
#      (file exists, manifest well-formed, size, sha256, opens as SQLite,
#      integrity_check). Read those. If they pass, the snapshot is sound.
#
#      `migrate apply` itself verified this snapshot AS schema 2 before it
#      touched anything, which is the check that actually mattered.

# 6''. After restoring a v2 snapshot you are back on version 2, so every
#      normal command refuses again — correctly:
python3 aos.py migrate status     # → schema version: 2, pending: yes (2 → 3)
python3 aos.py doctor             # → refuses: schema_version is '2'
python3 aos.py memory graph M-0001  # → refuses too: v3 command, v2 database

#      From here you either stay on the older build, or migrate again once the
#      reason for the failure is fixed:
python3 aos.py migrate apply
python3 aos.py doctor             # now it runs
```

**Never** "fix" that refusal by editing `meta.schema_version` to 3. The memory
table would still be v2 — no `sensitivity` column — and the three graph tables
would not exist at all, so every U-M3 command would fail against a database now
claiming to be something it is not.

**Never** hand-edit `sensitivity` either. It is a bound field of the claim
hash, so editing it directly breaks that hash — which is the system working:
the field that decides whether an agent ever sees a claim is not one you get to
change without leaving a trace. Every write against that claim will then refuse
rather than re-bless the edit. To change a claim's classification, use the
command that exists:

```bash
python3 aos.py memory classify M-0001 confidential
```

(That command raises a classification only. Lowering one is U-S6's decision and
this build refuses it — see TROUBLESHOOTING.md.)

### The graph tables are canonical ledger data, not a disposable index

`memory_sources`, `memory_source_links` and `memory_edges` are **canonical**.
They hold provenance, relationships and contradictions you recorded, each row
carrying its own integrity hash. They are not a cache, not a derived view, and
not rebuildable from anything else — unlike the FTS search index (droppable at
any time, rebuilt on demand) or the Obsidian mirror (regenerated by `sync`).

Any external graph engine, visualization or index you build later is the
derived thing; **SQLite stays the system of record**. So:

- Do not drop these tables to "reset the graph". Nothing will rebuild them.
- Back them up with the rest of the ledger — `backup create` already does.
- If they are damaged, restore, exactly as you would for `memory` itself.

### "PARTIALLY ADVANCED": an earlier step committed, a later one failed

This is a **real, consistent state**, not a corrupt one. Every committed
step was atomic; you are genuinely at the version reported. You choose:

- **Fix the migration and re-run** (usually right). `migrate apply` resumes
  from the version actually committed and never replays completed steps:
  ```bash
  python3 aos.py migrate status     # confirm the real version
  python3 aos.py migrate apply
  ```
- **Go all the way back.** Run the drill above with the snapshot named in
  the failure message — it is the *pre-migration* snapshot, so it returns
  you to the version you started at, not to the half-advanced state.

### Do not

- **Do not** hand-edit `meta.schema_version` to "fix" a partial migration.
  It is a claim about what the bytes on disk are, not a compatibility dial.
  Editing it makes every later check — including `backup verify` — certify
  a lie. The database keeps the old shape and the tool now believes the new
  one; that is worse than the failure you started with.
- **Do not** restore a snapshot without verifying it first (step 3).
- **Do not** delete the migrated database before the restore is proven
  (step 4 moves it aside for exactly this reason).

## Catalog tamper or divergence (U-A2)

The built-in specialist catalog (`agentic_os/catalog/`, twelve checked-in
passport artifacts) follows the same posture as everything else here:
**restore from a trusted source, never rewrite in place.**

**In recovery mode, the read-only catalog leaves stay available; only
`install` is blocked:**

```bash
python3 aos.py agent catalog list      # works in recovery
python3 aos.py agent catalog show NAME # works in recovery
python3 aos.py agent catalog verify    # works in recovery
python3 aos.py agent catalog status    # works in recovery
python3 aos.py agent catalog plan --all  # works in recovery

python3 aos.py agent catalog install --all
# → blocked BEFORE dispatch: stdout stays empty, no mutation is reachable
#   while the ledger is in recovery.
```

Inspecting the catalog while the ledger is damaged is exactly when `verify`
and `status` earn their keep — they need no write access and change nothing.

**Doctor never auto-installs, upgrades, or repairs the catalog.** Checks
35-37 are read-only: check 35 verifies the SHIPPED catalog (manifest +
twelve artifacts) against itself; check 36 verifies every INSTALLED catalog
identity against the shipped catalog; check 37 warns (never fails) on an
actionable upgrade or a name collision. Nothing here writes a row, and a
workspace that has never run `agent catalog install` reports healthy on all
three.

**If check 35 FAILs** (the shipped catalog itself does not verify): this is
a corrupted or tampered *installation of the software*, not a ledger
problem. Re-obtain `agentic_os/catalog/` from a trusted source (a clean
checkout, a clean wheel, or a clean `aos.pyz`) — never hand-edit a passport
or the manifest to make the check pass. Editing `content_sha256` to match a
changed body does not repair anything; it destroys the only evidence the
artifact was altered.

**If check 36 FAILs** (an installed catalog identity is `tampered` or
`diverged` from the shipped catalog): this is the same posture as a
tampered agent registry row (see "Rolling back a migration" above) — doctor
names the identity and the verdict, every further write against it refuses
(the no-laundering gate), and there is **no automatic repair path**.
`agent catalog install` will not "fix" it either: it refuses the whole
operation rather than writing over a divergent or tampered row. The
recovery is the same drill as any other tampered ledger row: restore the
database from a verified backup (see "Restore drill" above). There is no
narrower "just fix this one agent" repair, on purpose — a governed row's
history is either intact or it is not, and a partial rewrite would be a
guess wearing a fact's clothes.

**Never** hand-edit `owner`, `protected`, `lifecycle`, `agent_class`, or a
stored passport `document` to make a catalog identity look installed or
healthy again. Every one of those fields is bound into the identity or
passport hash; editing it without going through the governed write path is
exactly the tamper doctor exists to catch.

## Tampered routing plans or governed handoffs (U-A3)

Routing plans (`routing_plans` + `routing_plan_candidates`) and governed
handoffs (`agent_handoffs` + `agent_handoff_transitions`) follow the same
posture as every other governed row here: **restore from a verified backup,
never rewrite in place.** A committed plan is immutable; a handoff's only
mutable surface is its current-state projection, and that moves only through an
append-only transition. Neither has a repair path, on purpose.

This drill applies when `doctor` FAILs on:

```
[FAIL] routing plans verify — RP-0001: <verdict>
[FAIL] agent handoffs verify — AH-0001: <verdict>
```

or when `agent route verify` / `agent handoff show` report a closed integrity
verdict — `malformed`, `mismatch`, `unhashable`, `pin_mismatch`,
`request_mismatch`, `rank_gap`, `counts_incoherent`, or `reference_invalid`
for a plan, or `malformed`, `mismatch`, `unhashable`, `chain_gap`,
`chain_illegal`, `state_divergent`, `pin_mismatch`, `reason_missing`, or
`supersession_incoherent` for a handoff. Each names the record and a closed
verdict from a fixed vocabulary — never row content.

### The drill

```bash
# 0. From the repo root. Stop running authoritative commands against the
#    workspace.

# 1. Enter recovery (works even while doctor is failing). The six U-A3 write
#    leaves are now blocked before dispatch; the five read leaves still work:
python3 aos.py power set recovery

# 2. Inspect the damage. These reads never repair or mutate anything, so a
#    tampered, stale, or superseded plan or handoff stays fully inspectable:
python3 aos.py agent route list
python3 aos.py agent route show RP-0001
python3 aos.py agent route verify RP-0001
python3 aos.py agent handoff list
python3 aos.py agent handoff show AH-0001

# 3. Write down the affected public RP-/AH- ids and their closed verdicts.
#    Those ids and verdict names are the whole record of what was lost.

# 4. Compare against a known-good backup or a trusted external record, then
#    restore the ledger through the "Restore drill" above — move the damaged
#    db aside, verify the backup, restore to the now-free live path:
python3 aos.py backup verify .agentic-os/backups/aos-backup-<stamp>.db
python3 aos.py backup restore .agentic-os/backups/aos-backup-<stamp>.db \
    --to .agentic-os/aos.db

# 5. Re-prove integrity after restoring:
python3 aos.py doctor
python3 aos.py agent route verify RP-0001     # only if that id still exists
python3 aos.py agent handoff show AH-0001

# 6. Leave recovery only once every hard doctor check passes:
python3 aos.py power set standard
```

### There is no repair command — accepting documented loss

There is **no** rehash, repin, or repair command for a plan or a handoff, and
there is no way to "clear" a stale or superseded flag: staleness is derived at
read time, never stored, so there is nothing stored to clear. Therefore:

- **Do not** hand-edit `content_sha256`, a candidate rank, a transition `seq`,
  a handoff `state`, a pinned passport version or digest, or any
  `supersedes_id` / `plan_id` / task reference to make `doctor` pass. Editing a
  bound field does not repair the record — it destroys the only evidence the
  record was altered, and every write against it still refuses (the
  no-laundering gate).
- **Do not** delete an individual `routing_plans`, `routing_plan_candidates`,
  `agent_handoffs`, or `agent_handoff_transitions` row to silence a check. A
  governed row's history is either intact or it is not; a partial deletion is a
  guess wearing a fact's clothes.

If no verified backup preserves the record, the only honest option is to
**accept the documented loss**: use the restore drill above (or a clean
workspace) to reach a verified-good ledger, record the lost RP-/AH- ids
externally — a decision note, an issue, a run log — and recreate any future
routing plan or handoff through the normal governed commands (`agent route
plan`, `agent handoff create`). Historical integrity cannot be reconstructed by
guessing: a plan's ranked candidate chain and a handoff's transition chain each
bind their own hashes, and no after-the-fact input reproduces them.

### What recovery keeps available

- The six U-A3 authoritative writes — `route plan`, `handoff create`, `accept`,
  `refuse`, `clarify`, `cancel` — are blocked **before dispatch**: stdout stays
  empty and no mutation is reachable while the ledger is in recovery.
- `route list` / `route show` / `route verify` and `handoff list` /
  `handoff show` remain available — inspecting a malformed, stale, or tampered
  plan or handoff is exactly what recovery is for.
- Those reads change nothing. A damaged record stays inspectable; nothing
  recomputes a hash over it, and nothing repairs it.

### Reporting privately

The ids and verdicts are safe to share; the content is not. When you open a
public issue, **do not paste**:

- objectives, constraints, or transition notes;
- stored request documents;
- full hashes;
- the database file or a backup of it;
- credentials or any secret-shaped value.

Report only the public **RP-/AH- ids**, the **doctor check name** (`routing
plans verify` or `agent handoffs verify`), and the **closed verdict code**
(`malformed`, `pin_mismatch`, `chain_illegal`, and so on). Share anything more
only through a secure support channel that genuinely needs it.

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
