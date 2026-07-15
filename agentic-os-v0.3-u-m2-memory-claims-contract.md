# Agentic OS v0.3 — U-M2: typed memory claims and curation state

Contract. Written before the production code. Everything below is pinned:
data shape, migration, hashing, retrieval, CLI, events, recovery and
compatibility. Where this contract departs from the unit brief, the departure
is stated explicitly with its reason (§16).

Baseline: `9b2f43d` (U-X1 protocol spine). Branch: `v0.3-u-m2-memory-claims`.

## M2.0 — Scope

U-M2 turns the existing v1 `memory` row into a governed **memory claim** and
ships the first production schema migration (1 → 2).

In scope: curation status · pinning · deterministic claim hash · normalized
evidence links · live-only normal retrieval · deterministic legacy mapping ·
backup-first migration through the U-M1 framework.

Explicitly NOT in scope (deferred): graph/triple store, subject-predicate-object
modeling, relationship or contradiction tables, source-document tables, vector
store, semantic retrieval, automatic extraction, proposal/approval workflow,
distillation, agent memory writers, AICompany bridge, Memory Galaxy /
Canvas views.

`kind` remains the closed claim type. `key` remains the stable claim
key/subject. `value_md` remains the human-readable claim value. Generalized
relationship modeling is **U-M3**; approve/reject/contest/quarantine workflow
is **U-M4**.

## M2.1 — Schema version 2

`db.SCHEMA_VERSION` becomes `"2"`. `migrations.LATEST_VERSION` stays derived
from it (`int(db.SCHEMA_VERSION)`), so the two can never drift.

A freshly initialized workspace is created **directly at version 2** and never
runs a migration.

The canonical production registry contains **exactly one** entry:

| from | to | migration_id |
|------|----|--------------|
| 1 | 2 | `u-m2-memory-claims-v2` |

No version 3. No second production transition.

## M2.2 — The v2 memory claim (exact DDL)

Every v1 column survives, byte-for-byte, in place. Three columns are added.

```sql
CREATE TABLE IF NOT EXISTS memory(
  id INTEGER PRIMARY KEY,
  scope TEXT NOT NULL,
  project_id INTEGER,
  kind TEXT NOT NULL,
  key TEXT NOT NULL,
  value_md TEXT NOT NULL,
  source TEXT NOT NULL,
  confidence TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_until TEXT,
  superseded_by INTEGER,
  updated_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'live'
    CHECK (status IN ('proposed','live','contested','quarantined','retired')),
  pinned INTEGER NOT NULL DEFAULT 0
    CHECK (pinned IN (0, 1)),
  content_sha256 TEXT NOT NULL
);
```

- **status** — closed vocabulary, exactly:
  `proposed` · `live` · `contested` · `quarantined` · `retired`.
  Enforced twice: `models.MEMORY_STATUSES` at the domain boundary and the
  SQLite `CHECK` at the storage boundary.
- **pinned** — SQLite integer boolean. Only `0` or `1`; default `0`.
  `CHECK (pinned IN (0,1))` rejects `2`, `-1`, `'yes'` (INTEGER affinity turns
  `'1'` into `1`, which is the honest reading of an integer boolean) and NULL.
- **content_sha256** — lowercase 64-hex claim hash (§M2.6). `NOT NULL`, **no
  default**: a claim without a hash must be impossible to insert, so there is
  no default for a careless writer to fall into.

No `project_id`/`superseded_by` foreign keys are added: v1 had none, and
adding them is a data-integrity change U-M2 did not agree to make (doctor
already audits both pointers).

### Evidence link table

One stable name, pinned here: **`memory_evidence`**.

```sql
CREATE TABLE IF NOT EXISTS memory_evidence(
  memory_id INTEGER NOT NULL,
  evidence_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (memory_id, evidence_id),
  FOREIGN KEY(memory_id) REFERENCES memory(id),
  FOREIGN KEY(evidence_id) REFERENCES evidence(id)
);
```

- The composite `PRIMARY KEY` **prevents duplicate links** at the storage
  layer; `link-evidence` treats an existing link as an idempotent no-op above
  it, so the constraint is a backstop, not the UX.
- **Deletion behavior follows the existing schema exactly**: plain
  `REFERENCES` → `NO ACTION` → SQLite *refuses* to delete a referenced
  `memory` or `evidence` row while `PRAGMA foreign_keys=ON` (every connection).
  This matches every other FK in the ledger. No `ON DELETE CASCADE`: the
  ledger is append-only and has no delete path; a cascade would be a silent
  deletion mechanism invented for a caller that does not exist.
- `created_at` — deterministic, from the single clock (`utils.utc_now_iso()`).
- The row carries **no evidence body, claim, ref, sha256, provenance or any
  other copied text**. Two integers and a timestamp. Evidence content is read
  through the `evidence` table or not at all.

No relationship, contradiction, source-document or graph-edge tables (U-M3).

## M2.3 — Migration `u-m2-memory-claims-v2` (1 → 2)

**One explicit transactional step**, registered in `migrations.MIGRATIONS` and
applied through the existing U-M1 machinery. U-M2 adds **no** backup, locking,
planning or version-bump code — it supplies a `Migration.apply` callable and
nothing else.

The ordering U-M1 already guarantees, and which U-M2 relies on unchanged:

1. `validate_registry()` — refuse a malformed path before any I/O.
2. `require_regular_db_file()` + read-only pre-flight version read.
3. `BEGIN IMMEDIATE` on the migration connection; **re-read the version inside
   the lock**; refuse a stale plan.
4. `backup.write_backup_pair()` from a *second* reader connection — the
   pre-migration snapshot, taken **before the first mutation**, while the write
   lock excludes every other writer.
5. `backup.verify_backup(snapshot, expected_schema_version="1")` — a snapshot
   that does not verify **as schema version 1** aborts the migration with the
   database untouched.
6. Only then: `migration.apply(conn)` → `UPDATE meta SET schema_version='2'` →
   one `system/migrate` event → `COMMIT`.

### What the step does

The step **rebuilds the memory table** rather than `ALTER TABLE ADD COLUMN`.

Reason, measured not assumed: `ADD COLUMN` cannot add `content_sha256 TEXT NOT
NULL` without a non-NULL default, and a `DEFAULT ''` would leave every future
insert able to store a hashless claim — the migrated schema would be
permanently weaker than a freshly initialized one. A rebuild makes a migrated
v2 table **identical in shape and constraints to a fresh v2 table**, and it
runs every mapped row through the new `CHECK`s, so the migration cannot commit
a value the schema forbids.

Inside the one transaction, in order:

1. `CREATE TABLE memory_v2_migrating(...)` — the exact v2 claim DDL.
2. Read every v1 row (`SELECT * FROM memory ORDER BY id`), map it (§M2.4),
   compute its hash (§M2.6), and insert it with its **original `id`**.
3. `DROP TABLE memory`.
4. `ALTER TABLE memory_v2_migrating RENAME TO memory`.
5. `CREATE TABLE memory_evidence(...)` — created *after* the rename, so no FK
   reference is ever repointed by the rename.

Row identity: ids are inserted explicitly, so `INTEGER PRIMARY KEY` rowids are
preserved exactly and the next auto-assigned id continues from `max(id)`
exactly as before (no `AUTOINCREMENT`, so no `sqlite_sequence` to reconcile).

## M2.4 — Legacy mapping (deterministic)

Every valid v1 memory row survives with the **same** `id`, `scope`,
`project_id`, `kind`, `key`, `value_md`, `source`, `confidence`, `valid_from`,
`valid_until`, `superseded_by`, `updated_at`. Not one of them is rewritten,
normalized, trimmed, case-folded, re-timestamped or re-numbered.

Curation is derived, never guessed:

| legacy row | v2 status |
|---|---|
| `superseded_by IS NOT NULL` | `retired` |
| `valid_until` already expired | `retired` |
| every other valid row | `live` |

- **Expired** uses the *existing* live predicate verbatim
  (`ops.memory_for_project`): expired ⟺ `valid_until IS NOT NULL AND NOT
  (valid_until > now)`, string-compared against one `utils.utc_now_iso()` read
  taken once per migration run. A row v1 already excluded from packs is
  therefore exactly a row v2 calls retired. No new time semantics are invented.
- `superseded_by` is checked **first**: a row that is both superseded and
  expired is retired either way, so the order is stated only to make the
  mapping total and deterministic.
- Every legacy row starts **unpinned** (`pinned = 0`).
- **No evidence links are invented.** `memory_evidence` is empty after the
  migration, always.
- Every migrated row receives a valid deterministic `content_sha256` computed
  over its *migrated* state (status included, evidence list empty).
- `proposed`, `contested` and `quarantined` are **never** inferred. There is no
  free-text analysis anywhere in this migration.

## M2.5 — Failure semantics

An injected failure anywhere inside the step (before, during or after its
writes; `Exception` or `BaseException`) must leave:

- the live database at **schema version 1**;
- the **v1 memory table intact**, every row byte-identical;
- **no** `memory_evidence` table;
- **no** `memory_v2_migrating` table;
- **no** surviving `system/migrate` event;
- the **verified pre-migration snapshot** present and intact.

This is the U-M1 guarantee, unmodified: the step's schema changes, the version
bump and the event live in one transaction and die together.

A corrected retry migrates **exactly once**: the version is re-read under the
lock at the start of the step, so a database already at 2 is a no-op and a
database at 1 migrates once.

The migration event stays the existing privacy-safe `system/migrate` event with
its existing payload (`from`, `to`, `migration_id`, `snapshot` as a relative
path). It carries **no** row values, keys, memory text, source strings, hashes
or SQL. U-M1 already refuses to put `str(exc)` into a failure message — only the
exception *class name* — so a step that raises with a planted secret cannot leak
it. U-M2 adds nothing to that payload.

## M2.6 — The claim hash

Lowercase SHA-256, in `content_sha256`.

**Canonicalization reuses U-X1 unchanged**: `protocols.serialize_canonical()`
(canonical JSON v1 — sorted keys, no whitespace, UTF-8, no floats). U-M2
defines **no** competing canonicalization and touches **no** U-X1 schema
identity, registry entry or hashing constant.

### The exact payload

```python
{
  "claim_schema":        "aos.memory-claim/v2",   # binds the payload shape
  "id":                  <int>,
  "project_id":          <int|null>,
  "superseded_by":       <int|null>,
  "pinned":              <int>,                   # the stored value, verbatim
  "evidence_ids":        [<int>, ...],            # ascending, de-duplicated
  "scope_sha256":        <64-hex>,
  "kind_sha256":         <64-hex>,
  "key_sha256":          <64-hex>,
  "value_sha256":        <64-hex>,
  "source_sha256":       <64-hex>,
  "confidence_sha256":   <64-hex>,
  "valid_from_sha256":   <64-hex>,
  "valid_until_sha256":  <64-hex|null>,
  "status_sha256":       <64-hex>,
  "updated_at_sha256":   <64-hex>,
}

content_sha256 = sha256(serialize_canonical(payload)).hexdigest()
```

Text leaves are bound by `utils.sha256_text(field)` — the existing primitive —
never by the raw string. **Why** (both reasons are load-bearing, not taste):

1. U-X1's canonical JSON has a pinned `MAX_STRING_CHARS = 8192` bound. `memory
   add --value` has never had a length limit, so a legitimate v1 row with a
   20 KB pasted summary exists in the wild. Feeding it raw to
   `serialize_canonical` would raise `string_too_long` and **the migration
   would refuse a valid legacy row** — violating the one thing the legacy
   mapping must guarantee. Relaxing U-X1's bound is out of scope and would be
   modifying the protocol spine.
2. A hostile or damaged row must be *reportable*, not fatal. A tampered
   megabyte-long `status` cell would otherwise make `doctor` raise out of
   canonical serialization (exit 2, a crash) instead of printing one bounded
   line (exit 1, a diagnosis). With digest leaves, **no stored text of any
   length can trip any bound**, ever.

`sha256(text)` binds the text exactly — any alteration changes the digest and
therefore the claim hash. This is a Merkle-style binding of the same fields,
not a weaker one.

**Bound fields** (all of them, per the brief): scope · project identity
(`project_id`) · kind · key · value_md · source · confidence · valid_from ·
valid_until · superseded_by · status · pinned · sorted evidence-link
identities. Plus, deliberately:

- **`id`** — the claim's identity. Binding it makes a valid hash
  non-transplantable: copying M-0007's hash onto M-0009 is a mismatch.
- **`updated_at`** — the authoritative write timestamp of this claim state.
  Every U-M2 write path that touches `updated_at` recomputes the hash in the
  same statement, so binding it costs nothing and detects timestamp tampering.

**Excluded** — exactly two, and both are documented here as required:

- `content_sha256` itself (there is no self-reference; what is hashed never
  contains the hash — the D-v0.3.6 rule).
- Nothing else. Every other column of the claim is bound. `memory_evidence`
  rows are bound through `evidence_ids`; their `created_at` is link bookkeeping
  (storage mechanics), not a claim assertion, and is excluded.

### Rules

- Any operation that changes a bound field **or** an evidence link recomputes
  `content_sha256` **in the same transaction** as the change and the event.
- `evidence_ids` is bounded at `protocols.MAX_ARRAY_ITEMS` (256) links per
  claim — U-X1's array bound, inherited rather than re-invented.
  `link-evidence` refuses the 257th link **before** mutating, with an
  ID-and-count-only message. The migration cannot reach this bound (it creates
  no links).
- Validation detects: altered claim text · altered metadata · altered status ·
  altered pin state · altered supersession · added or removed evidence links ·
  malformed / uppercase / blank / substituted hashes. A hash that is not
  exactly 64 lowercase hex characters is **malformed** and reported as such
  without recomputation.
- **Every authoritative write against an existing claim verifies the stored
  hash first and refuses on mismatch** (`retire`, `pin`, `unpin`,
  `link-evidence`, and the supersede side of `add --supersedes`). Without this,
  a mutation would recompute the hash over tampered fields and *launder* the
  tampering into a valid-looking claim. The refusal names the ID and directs to
  `doctor`; it prints no claim content.
- **No integrity report ever prints claim contents** — not the key, value,
  source, evidence ref or claim body; not the hash in full (a bounded 12-hex
  prefix only).

## M2.7 — Curation and retrieval semantics

**Normal retrieval means `status = 'live'` only.** The eligibility predicate,
one definition used everywhere:

```
eligible  ⟺  status = 'live'
          AND superseded_by IS NULL
          AND (valid_until IS NULL OR valid_until > now)
```

Never eligible, therefore never in an ordinary context pack, generated context
section or automatic derived summary: `proposed` · `contested` ·
`quarantined` · `retired` · expired · superseded.

**Pinning is ordering, never permission.** A pinned claim must still be live,
unexpired, unsuperseded and (at every write) hash-valid. Pin changes exactly
one thing — deterministic order:

1. pinned eligible claims first;
2. unpinned eligible claims second;
3. inside each group, the existing stable `(scope, key, id)` ordering, and the
   existing "latest row (highest id) per (scope, project, key) wins" dedupe,
   unchanged.

**Retrieval does not re-verify hashes.** Integrity is enforced where it can be
*acted on*: at write time (every mutation verifies before mutating) and in
`doctor` (which reports). A pack build must not fail, or silently drop context,
because of an unrelated damaged row — silent omission is the worst outcome of
the three, and a refusal at read time would make an unrelated tampered claim
block every pack in the workspace. This is stated so no reader mistakes
"live-only" for "verified-on-read".

**Status is curation; expiry is time.** They are independent axes. A live claim
whose `valid_until` passes becomes ineligible *without any write* — so a
non-retired expired claim is legal, reachable honestly (`--valid-until` with a
past date; or simply the passage of time), and is reported by doctor as a
**warning**, never a failure. A check that turns red because a day passed is a
broken check.

**Backward compatibility** (all preserved):

- trusted human `memory add` creates a **live**, **unpinned** claim by default;
- callers that pass no new options behave exactly as before;
- `memory retire` sets `status='retired'`, keeps its existing `valid_until=now`
  behavior, keeps the row and its links, and keeps refusing a double retire;
- `memory add --supersedes` retires the superseded claim **transactionally**
  (status + hash + the successor row + the event, one transaction).

`proposed`/`contested`/`quarantined` are storable for U-M4 workflows. U-M2 adds
**no** approve, reject, contest, quarantine, promotion or automated-curation
command, and **no** command that accepts an arbitrary status.

## M2.8 — CLI

Preserved unchanged: `memory add` · `memory list` · `memory retire`.

Added: `memory show` · `memory pin` · `memory unpin` · `memory link-evidence`.

```
aos memory show MEMORY_ID [--json]
aos memory pin MEMORY_ID
aos memory unpin MEMORY_ID
aos memory link-evidence MEMORY_ID EVIDENCE_ID
aos memory add ... [--pin] [--evidence EVIDENCE_ID ...]
aos memory list [--scope S] [-p PROJECT] [--status STATUS] [--pinned|--unpinned] [--json]
```

**memory show** — read-only. One claim: fields, curation status, pin state,
full hash, evidence IDs. `--json`. Never prints an evidence claim body, ref, or
any referenced file's contents — evidence appears as `E-XXXX` IDs only.

**memory pin / unpin** — authoritative writes. Idempotent: pinning a pinned
claim (or unpinning an unpinned one) rewrites nothing, recomputes nothing and
emits **no** event; it reports the current state and exits 0. Refuses to pin a
claim that is not live, is expired, or is superseded, and refuses any claim
whose stored hash does not verify. Domain row + event + new hash in one
transaction. `unpin` is always allowed on an eligible-or-not claim (removing a
pin is never the dangerous direction) but still verifies the hash first.

**memory link-evidence** — authoritative write. Verifies both rows exist.
Rejects cross-project linkage when **both** sides have a project identity and
they differ: the claim's identity is `memory.project_id`; the evidence's is
`evidence → task → tasks.project_id`. A NULL on either side (global-scope
claim, projectless task) is *compatible*, not a violation — global memory
legitimately cites project evidence, and an inbox task's evidence has no
project to disagree with. A duplicate link is an **idempotent no-op** (no
write, no event, exit 0). Updates the claim hash and emits one safe event in
the same transaction.

**memory list** — default output still shows **historical rows** (memory never
silently disappears). Adds status and pin state to the display. Bounded filters:
`--status` (closed vocabulary) and `--pinned`/`--unpinned` (mutually
exclusive). `--json` exposes `status`, `pinned`, `evidence` (E-IDs) and
`content_sha256`. **Never hides invalid rows** from explicit administrative
listing — a hash-broken or unknown-status row still lists, carrying its status.

**memory retire** — sets `status='retired'`, sets `valid_until` exactly as
today, updates the hash, deletes nothing (row and links stay).

## M2.9 — Events

The invariant holds for every authoritative memory mutation:
**domain change + safe event + new hash, in one transaction.**

New/extended payloads carry only: memory ID · status transition names · pin
transition · evidence ID · safe counts · a bounded 12-hex hash prefix.

| action | entity | payload |
|---|---|---|
| `add` (existing) | memory | existing keys + `status`, `pinned`, `evidence` (E-IDs), `hash_prefix`, and `supersedes_status` when superseding |
| `retire` (existing) | memory | existing keys + `from_status`, `status`, `hash_prefix` |
| `pin` | memory | `memory`, `pinned: true`, `from_pinned: false`, `hash_prefix` |
| `unpin` | memory | `memory`, `pinned: false`, `from_pinned: true`, `hash_prefix` |
| `link_evidence` | memory | `memory`, `evidence`, `evidence_count`, `hash_prefix` |

New events must not contain: `key` · `value_md` · `source` · evidence claim or
ref · secrets · arbitrary exception text · SQL. They do not.

**One documented exception, for compatibility** (D-v0.3.19, §16 deviation 4): the
*pre-existing* `memory/add` payload has always carried `key`, and it is
governed by U-C3 — `events.emit` passes every payload through
`secretscan.redact_tree`, so a secret-shaped key is stored as the fixed
placeholder and the U-C3 metadata (`secret_warning`/`secret_fields`/
`secret_patterns`) records what was withheld. Removing `key` would break the
preserved U-C3 behavior this unit is required to keep passing. U-M2 preserves
that field and adds no new text-bearing field to any memory event.

U-C3 warn-on-write for memory `key`/`value`/`source` is preserved exactly.

## M2.10 — Doctor

Four checks are added (21 → **25**), each single-purpose, each bounded to IDs
and counts. None prints a key, value, source text, evidence ref, or a hash in
full.

- **22. `memory claims are well-formed`** (FAIL) — unknown status · `pinned`
  not 0/1 · malformed `content_sha256` (not 64 lowercase hex, blank, uppercase)
  · hash mismatch · a `retired` claim with no consistent retirement state
  (neither superseded nor expired) · a non-retired claim that is already
  superseded (no honest path leaves one: supersession retires transactionally)
  · a self-referential supersede pointer. Dangling supersede pointers stay with
  the existing check 11.
- **23. `memory evidence links resolve`** (FAIL) — a link whose memory row or
  evidence row is missing · duplicate links (only reachable if the composite
  primary key was bypassed).
- **24. `pinned claims eligible for retrieval`** (WARN) — a pinned claim that
  is not eligible. Honestly reachable (pin, then retire; pin, then expiry
  passes), harmless, and worth saying out loud: *you pinned this and it will
  not be retrieved*.
- **25. `non-retired claims past their valid_until`** (WARN) — see §M2.7:
  legal, temporal, never fatal.

A row that cannot be hashed at all (a BLOB in a TEXT column, a link count past
the bound) is reported by check 22 as malformed, by ID. Doctor never crashes on
a damaged claim.

## M2.11 — Search, mirror and packs

- **Packs** — `ops.memory_for_project` filters to eligible claims (§M2.7) and
  orders pinned-first. This is the only pack-facing change.
- **Search** and **`memory list`** may expose historical claims; every memory
  result carries its `status` so it cannot be mistaken for live context.
  Quarantined claims never reach a normal pack, generated context section, or
  automatic derived summary.
- **Obsidian mirror** — memory notes and the memory index gain: status, pin
  state, evidence count, and a bounded 12-hex hash prefix. No graph, Canvas
  view, contradiction UI or Memory Galaxy.

## M2.12 — Power modes

Every new CLI leaf is classified explicitly in `power.COMMAND_POLICY`:

| command | classification |
|---|---|
| `memory show` | `read_only` |
| `memory pin` | `authoritative_write` (ledger) |
| `memory unpin` | `authoritative_write` (ledger) |
| `memory link-evidence` | `authoritative_write` (ledger) |

Recovery mode blocks all three writes **before dispatch**, therefore before any
mutation. Deep mode keeps its existing preflight/post-verification behavior
around them. No power-mode policy is changed beyond classifying new commands.

## M2.13 — Packaging parity

`tools/build_zipapp.py` allowlists `*.py` under `agentic_os/`, so the migration
implementation ships in `aos.pyz` **automatically**, with no builder change.
No database, snapshot, fixture or workspace may enter the archive — none is a
`.py` file under the package.

Script (`python3 aos.py`), module (`python3 -m agentic_os`) and standalone
zipapp (`python3 aos.pyz`, `PYTHONPATH` cleared, outside the checkout) must all
prove: `migrate status` on v1 · `migrate plan` showing 1→2 · `migrate apply` ·
`memory show`/`list` after migration · hash verification · the new commands.

## M2.14 — The v1 fixture

`tests/fixtures/v1_workspace.py` must keep producing a **real historical
schema-v1 workspace** after production moves to v2. It therefore pins the
historical v1 schema (`V1_SCHEMA_SQL`, `V1_SCHEMA_VERSION`) and builds the
workspace with **production CLI commands** running against those pinned
constants.

The one unavoidable exception: v1's memory writer no longer exists (v2's
inserts `content_sha256`), so the fixture pins a v1 memory writer that
replicates exactly what v1 `memory add` wrote — the same INSERT, the same
supersede UPDATE, the same event through the unchanged `events.emit`. Memory
rows are written after the last `sync`, which is exactly the state of a v1 user
who added memory after their last mirror refresh. See §16, deviation 3.

Representative legacy memory rows the migration proof needs:

| row | v1 state | expected v2 status |
|---|---|---|
| M-0001 | global preference, no expiry | `live` |
| M-0002 | project fact, no expiry | `live` |
| M-0003 | `valid_until` in the past | `retired` |
| M-0004 | superseded by M-0005 | `retired` |
| M-0005 | successor, `valid_until` in the future | `live` |

## M2.15 — Test matrix

`tests/test_v03_memory_claims.py` proves, at minimum: fresh init is v2 (1) ·
registry contains exactly 1→2 (2) · v1 fixture reports one pending migration
(3) · plan is read-only and shows 1→2 (4) · apply snapshots and verifies as v1
*before* mutation (5) · every legacy id and field survives (6) · active → live
(7) · expired/superseded → retired (8) · no invented links (9) · every migrated
row's hash is correct (10) · version advances exactly once (11) · one
privacy-safe migration event (12) · injected failure rolls back completely (13)
· corrected retry migrates once (14) · normal v2 commands refuse a v1 database
(15) · status/pin constraints enforce (16) · new claims default live+unpinned
(17) · add with pin and evidence is transactional (18) · duplicate link is
idempotent (19) · missing/incompatible evidence refuses unchanged (20) ·
pin/unpin idempotent and hash-consistent (21) · retire updates status+validity+
hash atomically (22) · supersede retires atomically (23) · non-live never packs
(24) · expired/superseded never pack (25) · pinned sorts first (26) · bound-field
tamper fails the hash (27) · link tamper fails the hash (28) · doctor reports
IDs/counts only (29) · secret-shaped claim text never appears in diagnostics or
events (30) · warn-on-write preserved (31) · every new leaf classified (32) ·
recovery blocks new writes before mutation (33) · deep verification still works
(34) · script/module/zipapp parity (35) · the existing suite still passes (36).

## M2.16 — Decisions and declared deviations

- **D-v0.3.15** — U-M2 stays key/value claim storage. Not a graph, not a triple
  store. `kind`/`key`/`value_md` keep their v1 meanings; relationships are U-M3.
- **D-v0.3.16** — Schema version 2 is the **first** production U-M1 migration.
  The framework shipped empty at U-M1 precisely so this step could be the first
  thing it carries, with no machinery invented here.
- **D-v0.3.17** — Legacy active rows map to `live`; legacy expired or
  superseded rows map to `retired`. Nothing is inferred from free text.
- **D-v0.3.18** — Pinned never overrides lifecycle or safety. It is a sort key.
- **D-v0.3.19** — Evidence uses **normalized links**, not copied evidence text.
- **D-v0.3.20** — Claim hashes reuse U-X1 canonicalization, with text leaves
  bound as SHA-256 digests (§M2.6) so that no legitimate legacy row can be
  refused by a protocol bound, and no damaged row can crash a diagnostic.
- **D-v0.3.21** — Normal retrieval includes **live claims only**; hash validity
  is enforced at write time and audited by doctor, not re-verified on read.
- **D-v0.3.22** — Status is curation, expiry is time: two independent axes, so
  "expired but not retired" and "pinned but ineligible" are WARNINGS, never
  failures (§M2.7).
- **D-v0.3.23** — The 1 → 2 step rebuilds the memory table rather than using
  `ALTER TABLE ADD COLUMN` (§M2.3), so a migrated table is identical to a
  born-v2 one.
- **D-v0.3.24** — U-M3 (graph) and U-M4 (curation workflow) remain deferred.

### Declared deviations from the unit brief

Every file below was changed because a real call path or a contract-mandated
behavior required it, and each is reported in the final report.

1. **`tests/test_v02_migrations.py`** — its `ProductionRegistryTest` pinned
   `MIGRATIONS == ()` / `LATEST_VERSION == 1`, documented in-source as the
   tripwire for exactly this event ("If this fails, a migration was added
   without raising SCHEMA_VERSION with it"). Updated to the 1→2 registry. The
   tests whose subject is not the schema version (backup machinery, no-op
   apply's byte guarantees, core CLI, entrypoint parity) now migrate the
   fixture first via a `migrate_to_current()` helper and assert the same
   properties. `test_migrate_did_not_change_the_core_schema` became
   `test_migrate_changed_only_what_the_step_declares`: since the fixture now
   really migrates, "no drift" means the one declared table changed, no other
   did, and the result equals a fresh v2 install. Every synthetic-registry
   proof is untouched.
2. **`tests/test_v02_power_modes.py`** — check count 21 → 25 (the D-W8.1
   pattern the test itself cites); the three new memory leaves added to the
   recovery `BLOCKED` list; `test_schema_version_is_unchanged` → follows the
   one declaration (`db.SCHEMA_VERSION == "2"`) instead of restating `"1"`.
3. **`tests/fixtures/v1_workspace.py`** — rewritten beyond "stronger
   representative memory rows". Unavoidable: once `db.SCHEMA_VERSION` is `"2"`,
   `init` produces a v2 workspace. It now builds with production code, installs
   the pinned v1 memory DDL while the table is EMPTY, and writes the memory
   rows through a frozen v1 writer (§M2.14).
4. **`memory/add` keeps its pre-existing `key` payload field** (§M2.9,
   D-v0.3.19), because removing it breaks the U-C3 behavior this unit must
   preserve. All *new* events comply with the no-key rule.
5. **`tests/test_core.py`, `tests/test_cli.py`, `tests/test_v02_backup.py`,
   `tests/test_v02_secret_safety.py`, `tests/test_weekend_views.py`** — all
   changed for the same three mechanical reasons: the doctor check count
   (21 → 25), `schema_version` `"1"` → `db.SCHEMA_VERSION`, and raw memory
   INSERTs that must now supply the claim hash the schema requires. The pack
   compiler's fixture row now goes through `ops.add_memory` rather than raw
   SQL; the dangling-supersede corruption is planted retired-and-hash-valid so
   the pointer stays the *only* thing wrong with it.
6. **`agentic_os/doctor.py`'s U-C3 sweep hands the detector text only.** A TEXT
   column can hold a BLOB (reachable only by editing the file outside Agentic
   OS), and the shared regex detector takes `str` — so an unfiltered value made
   doctor die (exit 2) inside the sweep instead of reporting the damage. This
   is a pre-existing, ledger-wide fragility, not one U-M2 introduced, but
   M2.10's "doctor never crashes on a damaged claim" cannot hold without it.
   The filter is the identity for every real value; U-C3 semantics are unchanged.
7. **`agentic_os/render.py`** — memory note projection (status, pin, evidence
   count, bounded hash prefix), required by M2.11.
8. **`agentic_os/pack.py` is NOT modified.** The brief expected it; no call
   path required it. Pack retrieval changes entirely through
   `ops.memory_for_project`, which pack.py already calls — the MEMORY section's
   line format is deliberately unchanged, since pinning affects ordering only.
