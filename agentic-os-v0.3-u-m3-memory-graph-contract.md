# Agentic OS v0.3 — U-M3: provenance, temporal, relationship and contradiction memory graph

Status: pinned before implementation.
Baseline: 481709a9e162971b2098fda04d0a9bf6fe92f965 (U-M2, schema version 2).
Supersedes nothing. Extends U-M1 (migration kit), U-M2 (memory claims),
U-X1 (protocol spine / canonical JSON), U-E2 (power modes), U-C3 (secret
safety), U-P1 (packaging).

U-M3 adds the second production migration, `2 → 3`, and with it: claim
sensitivity, normalized provenance sources, claim↔source links, typed
claim↔claim relationships, first-class contradiction edges, temporal validity
on sources and edges, deterministic integrity hashes for every new record,
bounded graph traversal, contradiction inspection, and safe pack/search/mirror
handling.

SQLite remains canonical. Any visual graph, graph engine or index is derived
and rebuildable from these tables.

---

## M3.0 Scope

### In scope

Schema version 3; migration `u-m3-memory-graph-v3`; `memory.sensitivity`;
`memory_sources`; `memory_source_links`; `memory_edges`; four versioned hash
payloads; `memory classify`; `memory source add|list|show|link`;
`memory edge add|list`; `memory graph`; `memory contradictions`; doctor graph
checks; restricted-claim exclusion from packs, search snippets and mirror
bodies; command classification for every new leaf; documentation.

### Explicitly NOT in scope (deferred, and refused if asked for)

- **U-M4**: memory proposal, approval, rejection, contest workflows.
- **U-M5**: retrieval evaluation, graph ranking, embeddings, vector stores.
- **U-M6**: Context Hydration Receipts.
- **U-S6**: authorization policy, sensitivity DOWN-classification.
- Automatic contradiction detection or inference of any kind.
- Automatic source extraction; interviews; onboarding questionnaires.
- Agent-written memory; remote execution; AICompany integration.
- Canvas, Bases, graph visualization, dashboards.

### Untouched (D-v0.3.30)

U-X1 schema identities and the canonical JSON contract; WorkSpec / Result
Envelope / Interrupt schemas; U-M2 status and evidence-link semantics (except
that the v3 claim hash now binds `sensitivity`); task/run/evidence completion
semantics; hooks and dropfile ingest; backup/restore; export containment; the
agent registry; networking.

---

## M3.1 Schema version

`db.SCHEMA_VERSION` becomes `"3"`. `migrations.LATEST_VERSION` stays derived
from it (`int(db.SCHEMA_VERSION)`) — one declaration, never two.

Fresh workspaces initialize **directly at version 3**. There is no
initialize-then-migrate path.

The canonical production registry contains **exactly two** steps, in order:

| from | to | migration_id |
|------|----|--------------|
| 1 | 2 | `u-m2-memory-claims-v2` |
| 2 | 3 | `u-m3-memory-graph-v3` |

No version 4 or any other transition is added.

Normal commands still refuse any version != 3 through `db._check_schema_version`
and point the operator at `migrate status` / `plan` / `apply`. Only the
migration commands read the ledger's version themselves and so may open an
older schema. That rule is U-M2's, unchanged.

---

## M3.2 Sensitivity

### D-v0.3.31 — the vocabulary is closed and ordered

```
public < internal < confidential < restricted
```

`models.MEMORY_SENSITIVITIES = ("public", "internal", "confidential", "restricted")`
plus `sensitivity_rank(level) -> int` (0..3). The order is authoritative: it is
what "increase only" and "source must not exceed claim" are expressed in.

### Column

```sql
sensitivity TEXT NOT NULL DEFAULT 'internal'
  CHECK (sensitivity IN ('public','internal','confidential','restricted'))
```

Added to `memory`, between `pinned` and `content_sha256` — the U-M2 rule that
the hash column is last is preserved. The domain vocabulary and the storage
CHECK agree, so neither a careless caller nor a direct SQL writer can invent a
level.

### D-v0.3.32 — sensitivity defaults to internal

A claim recorded with no explicit level is `internal`. `public` is a
deliberate act of publication, not a default; `internal` is the honest
description of "the operator typed it into their own ledger".

### D-v0.3.33 — pinned never overrides sensitivity

Pinning is ordering among eligible claims (U-M2, D-v0.3.19). It does not
override sensitivity, lifecycle, expiry, supersession or integrity. A pinned
`restricted` claim is still excluded from every automatic context surface.

### Automatic context surfaces

- `public`, `internal`, `confidential` remain eligible under the existing
  U-M2 local rules — no behavior change.
- `restricted` claims **never** enter context packs, automatic search
  snippets, generated context summaries, or mirror bodies.

Explicit administrative surfaces (`memory list`, `memory show`, doctor) may
expose restricted **metadata** — id, scope, project, kind, status, pin,
sensitivity, timestamps, counts, hash — but must not print its `key`,
`value_md`, `source`, or evidence refs.

This is a safe local baseline, not the U-S6 authorization system.

### Migration mapping

Every valid schema-v2 claim becomes `internal`. IDs and every other field are
unchanged. No claim is reclassified by inspecting its text — U-M3 infers
nothing from content, ever.

---

## M3.3 `memory_sources`

```sql
CREATE TABLE memory_sources(
  id INTEGER PRIMARY KEY,
  project_id INTEGER,
  source_kind TEXT NOT NULL
    CHECK (source_kind IN
      ('evidence','file','url','command','human','agent','artifact')),
  evidence_id INTEGER,
  locator TEXT,
  provenance TEXT NOT NULL,
  sensitivity TEXT NOT NULL
    CHECK (sensitivity IN ('public','internal','confidential','restricted')),
  observed_at TEXT NOT NULL,
  valid_from TEXT,
  valid_until TEXT,
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  CHECK (
    (source_kind = 'evidence' AND evidence_id IS NOT NULL AND locator IS NULL)
    OR
    (source_kind <> 'evidence' AND evidence_id IS NULL AND locator IS NOT NULL)
  ),
  CHECK (valid_from IS NULL OR valid_until IS NULL OR valid_from <= valid_until),
  FOREIGN KEY(project_id) REFERENCES projects(id),
  FOREIGN KEY(evidence_id) REFERENCES evidence(id)
)
```

`content_sha256` has no default: a source without its integrity hash must be
impossible to insert (the U-M2 rule).

### D-v0.3.34 — a source row copies no text from what it references

`source_kind='evidence'` carries `evidence_id` **only**. The evidence row's
`claim`, `ref`, `sha256`, body, and any file it points at are never copied
into a source row. The structural CHECK enforces the shape at the storage
boundary as well as in `ops`:

- `source_kind='evidence'` **requires** `evidence_id`, **forbids** `locator`;
- every other kind **requires** `locator`, **forbids** `evidence_id`.

### `provenance`

Reuses the existing codebase meaning (`models.PROVENANCE_RE`): `human` or
`agent:<name>`. U-M3 does not invent a second meaning for a word this ledger
already defines. It is still treated as sensitive text on every output path
(never printed, digest-leafed in the hash) — the `<name>` component is
operator-supplied and a bounded charset is not a promise about content.

### Project scope

- `project_id IS NULL` means global.
- A **project** source may link only to claims in the **same** project.
- A **global** source may link to global or project claims.
- No project-A source may link to a project-B claim.

### Temporal invariants

- All timestamps use the existing UTC spelling (M3.7).
- `valid_from <= valid_until` when both exist (CHECK + `ops`).
- `observed_at` and `created_at` are immutable record facts.
- Expired source rows remain historical and queryable, but are **not active
  provenance**.

---

## M3.4 `memory_source_links`

```sql
CREATE TABLE memory_source_links(
  id INTEGER PRIMARY KEY,
  memory_id INTEGER NOT NULL,
  source_id INTEGER NOT NULL,
  relation TEXT NOT NULL
    CHECK (relation IN ('supports','disputes','context','derived_from')),
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  UNIQUE(memory_id, source_id, relation),
  FOREIGN KEY(memory_id) REFERENCES memory(id),
  FOREIGN KEY(source_id) REFERENCES memory_sources(id)
)
```

### D-v0.3.35 — a link's logical identity is (memory, source, relation)

`UNIQUE(memory_id, source_id, relation)` makes a duplicate logical link
impossible at the storage layer. The same source linked to the same claim
under a *different* relation is a different fact, not a duplicate — U-M3
records what the operator asserts and judges none of it.

Rules:

- Two integers, a relation, a timestamp and a hash. No copied source or claim
  text.
- The link hash binds all authoritative fields.
- Source/claim project compatibility is enforced **before** mutation.
- **Source sensitivity must not exceed claim sensitivity**:
  `rank(source.sensitivity) <= rank(claim.sensitivity)`. Otherwise the link
  would be a downgrade channel — a restricted source reachable through a
  public claim.
- An **expired** source may be linked historically, but does not count as
  active support.
- Deleting canonical records is not introduced in U-M3. Plain `REFERENCES`
  (NO ACTION) matches every other FK: with `foreign_keys=ON`, deleting a
  linked row is REFUSED.

---

## M3.5 `memory_edges`

```sql
CREATE TABLE memory_edges(
  id INTEGER PRIMARY KEY,
  from_memory_id INTEGER NOT NULL,
  to_memory_id INTEGER NOT NULL,
  relation TEXT NOT NULL
    CHECK (relation IN
      ('supports','contradicts','refines','depends_on','related')),
  valid_from TEXT,
  valid_until TEXT,
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  UNIQUE(from_memory_id, to_memory_id, relation),
  CHECK (from_memory_id <> to_memory_id),
  CHECK (valid_from IS NULL OR valid_until IS NULL OR valid_from <= valid_until),
  CHECK (relation NOT IN ('contradicts','related')
         OR from_memory_id < to_memory_id),
  FOREIGN KEY(from_memory_id) REFERENCES memory(id),
  FOREIGN KEY(to_memory_id) REFERENCES memory(id)
)
```

Rules:

- **Self-edges refuse** (`ops` + CHECK).
- **Duplicate logical edges** are idempotent no-ops (`ops` returns
  `changed=False`, writes nothing, emits no event); the UNIQUE constraint is
  the storage-layer backstop.
- **Project-A → project-B edges refuse.** Global↔project edges are permitted.
- **Invalid or inverted validity windows refuse** (`ops` + CHECK).
- Expired edges remain historical but are inactive.
- Relation values are **descriptive only** and trigger no mutation or
  workflow.

### D-v0.3.36 — symmetric relations canonicalize endpoints

`contradicts` and `related` are symmetric: A↔B and B↔A are one logical edge.
Endpoints are canonicalized as **lower memory id first** before any lookup or
insert, so a reverse duplicate is the same row. The fourth CHECK enforces the
canonical form at the storage layer too, so a row that bypassed `ops` is
detectable rather than merely unlikely.

`supports`, `refines` and `depends_on` are directional and preserve the
requested direction exactly.

### D-v0.3.37 — supersession is not duplicated as a graph relation

U-M2's `memory.superseded_by` remains the canonical lifecycle supersession
mechanism. There is no `supersedes` edge relation. Two mechanisms for one
truth is how a ledger starts disagreeing with itself.

### D-v0.3.38 — contradictions are typed edges, not a second table

A contradiction **is** an active `contradicts` edge. There is no second
contradiction table carrying duplicate truth, no `resolved` flag, and no
verdict column. `memory contradictions` reports; it never decides which claim
is true.

### D-v0.3.39 — no contradiction is ever inferred

U-M3 never infers a contradiction from keys, values, dates, sources, models,
or anything else. Every edge in `memory_edges` was typed by a human at the
CLI. Automatic detection is U-M4's problem and is refused here.

---

## M3.6 Integrity hashes

Lowercase SHA-256 over U-X1 canonical JSON (`protocols.serialize_canonical`).
No competing canonicalization is created (D-v0.3.20, preserved).

### D-v0.3.40 — every text leaf is bound by its digest

Every stored text field is bound as `sha256(text)`, never as raw text. Three
reasons, all measured (the U-M2 rationale, extended):

1. U-X1 caps a string at `MAX_STRING_CHARS`; `--locator` and legacy claim
   values have no such limit, so a real long value would otherwise be refused
   by its own hash.
2. A tampered megabyte-long cell must stay **reportable** — a diagnostic that
   crashes on the row it exists to report is not a diagnostic.
3. Diagnostics never need the raw value. A byte-level change still changes the
   digest, so the binding is not weaker.

Every payload carries an explicit record-schema identity, so a future payload
revision cannot collide with a v3 one. These are **not** U-X1 registry
identities: U-M3 registers no protocol schema and changes none.

Excluded from every payload: **only** `content_sha256` itself (what gets
hashed must never contain the hash — D-v0.3.6), and SQLite storage mechanics
(rowid aliasing; the `id` value itself IS bound).

### Claim — `aos.memory-claim/v3`

The U-M2 v2 payload with exactly one addition, `sensitivity_sha256`:

```
claim_schema        = "aos.memory-claim/v3"
id                  : int
project_id          : int|null
superseded_by       : int|null
pinned              : int          (stored value, verbatim)
evidence_ids        : [int] sorted, deduped
scope_sha256        : sha256(scope)
kind_sha256         : sha256(kind)
key_sha256          : sha256(key)
value_sha256        : sha256(value_md)
source_sha256       : sha256(source)
confidence_sha256   : sha256(confidence)
valid_from_sha256   : sha256(valid_from)
valid_until_sha256  : sha256(valid_until) | null
status_sha256       : sha256(status)
sensitivity_sha256  : sha256(sensitivity)      <-- U-M3
updated_at_sha256   : sha256(updated_at)
```

### Source — `aos.memory-source/v1`

```
source_schema       = "aos.memory-source/v1"
id                  : int
project_id          : int|null
evidence_id         : int|null
source_kind_sha256  : sha256(source_kind)
locator_sha256      : sha256(locator) | null
provenance_sha256   : sha256(provenance)
sensitivity_sha256  : sha256(sensitivity)
observed_at_sha256  : sha256(observed_at)
valid_from_sha256   : sha256(valid_from) | null
valid_until_sha256  : sha256(valid_until) | null
created_at_sha256   : sha256(created_at)
```

### Source link — `aos.memory-source-link/v1`

```
link_schema         = "aos.memory-source-link/v1"
id                  : int
memory_id           : int
source_id           : int
relation_sha256     : sha256(relation)
created_at_sha256   : sha256(created_at)
```

### Edge — `aos.memory-edge/v1`

```
edge_schema         = "aos.memory-edge/v1"
id                  : int
from_memory_id      : int
to_memory_id        : int
relation_sha256     : sha256(relation)
valid_from_sha256   : sha256(valid_from) | null
valid_until_sha256  : sha256(valid_until) | null
created_at_sha256   : sha256(created_at)
```

### The write invariant

Every authoritative mutation writes **domain row + integrity hash +
privacy-safe event inside one transaction**.

### D-v0.3.41 — no laundering

Before mutating an existing claim, source, link or edge, its stored hash is
verified. Without that gate, any benign update would recompute the hash over
whatever the row now says and CERTIFY prior tampering. The refusal names the
id and the reason code — never a key, value, locator, provenance or hash.

Integrity checks detect: field tampering; sensitivity tampering; project
reassignment; timestamp tampering; endpoint substitution; relation
substitution; locator/evidence target substitution; added or removed links;
and malformed, blank, uppercase, truncated or transplanted hashes.

---

## M3.7 Timestamps

New temporal fields (`observed_at`, `valid_from`, `valid_until`, `created_at`)
accept the existing UTC spellings and nothing else:

- a full instant — `YYYY-MM-DDTHH:MM:SSZ`, exactly what `utils.utc_now_iso()`
  produces; or
- a calendar date — `YYYY-MM-DD`, exactly what `memory add --valid-until`
  has always accepted.

Both must be real calendar dates/times. `utils.validate_instant(text, what)`
is the one validator. Lexicographic comparison is correct across both
spellings (a date sorts as that day's start), which is what the existing
expiry predicate already relies on.

### The active predicate (M3.7a)

A source or edge is **active** at `now` iff:

```
(valid_from IS NULL OR valid_from <= now) AND
(valid_until IS NULL OR valid_until > now)
```

`> now` matches U-M2's claim-expiry predicate exactly. One definition,
`ops.window_is_active(valid_from, valid_until, now)`, used by every command
and by doctor — so "active" cannot mean two things in two places.

---

## M3.8 CLI

Every existing memory command is preserved. Human ids: `MS-0001` sources,
`ML-0001` source links, `ME-0001` edges (`ids.PREFIXES` additions; the strict
parser already refuses a wrong prefix, so `MS-0001` can never be read as
`M-0001`).

### Extended

```
aos memory add ... [--sensitivity public|internal|confidential|restricted]
```
Default `internal`.

### New

```
aos memory classify MEMORY_ID LEVEL
```

- authoritative write;
- **increases only**: `public → internal → confidential → restricted`;
- same-state is an idempotent no-op (no write, no hash change, **no event** —
  an audit journal that records non-events is one you stop trusting);
- **down-classification refuses unchanged** and names U-S6;
- verifies the old claim hash before mutation, updates the claim hash, emits
  exactly one safe event carrying the sensitivity transition.

```
aos memory source add --kind KIND [--project SLUG] [--evidence E-XXXX]
                      [--locator TEXT] [--provenance P] [--sensitivity LEVEL]
                      [--observed-at TS] [--valid-from TS] [--valid-until TS]
aos memory source list [--project SLUG] [--kind KIND] [--active-only] [--json]
aos memory source show SOURCE_ID [--json]
aos memory source link MEMORY_ID SOURCE_ID --relation RELATION
```

Structural source-kind rules are enforced by **both** CLI validation and
database CHECK constraints.

`source list` / `source show`:

- read-only; `--json`; deterministic ordering (by id);
- show source id, project, kind, sensitivity, timestamps, active/expired
  state, link count, bounded hash prefix, and (for `evidence` kind) the
  evidence **id**;
- **never** print locator, provenance, evidence claim/ref, or file contents.
  Administrative metadata only.

`source link`:

- authoritative write; duplicate logical link is an idempotent no-op;
- validates both hashes and project/sensitivity compatibility;
- emits a safe ID-only event; does not mutate claim status or lifecycle.

```
aos memory edge add FROM_MEMORY_ID TO_MEMORY_ID --relation RELATION
                    [--valid-from TS] [--valid-until TS]
aos memory edge list [--relation R] [--project SLUG] [--active-only] [--json]
aos memory graph MEMORY_ID [--depth 1|2] [--json]
aos memory contradictions [--project SLUG] [--all] [--json]
```

`memory graph`:

- read-only; deterministic bounded breadth-first traversal;
- `--depth` accepts **only 1 or 2**; default 1;
- hard caps (M3.8a): **`MAX_GRAPH_NODES = 64`**, **`MAX_GRAPH_EDGES = 128`**;
- stable ordering: frontier by ascending memory id, incident edges by
  ascending edge id, depth-major;
- includes ids, relation, direction, status, sensitivity, active state;
- **never** prints key, value_md, source, locator, evidence ref, or a full
  hash;
- refuses an unknown starting memory;
- modifies, heals and infers nothing.

#### D-v0.3.42 — the traversal caps truncate, they do not refuse

On reaching a cap the traversal stops deterministically and reports
`truncated: true` plus the cap that was hit. A read-only inspector that
refuses on a large graph is useless exactly when it is needed; a silent
truncation would read as "that's the whole neighbourhood". So: bounded,
deterministic, and honest about being bounded.

`memory contradictions`:

- read-only; lists **active** contradiction edges by default;
- `--project`, `--all`, `--json`;
- outputs the contradiction edge id and the two memory ids, plus lifecycle and
  sensitivity metadata only;
- **does not decide which claim is true**; resolves and mutates nothing.

No arbitrary status, relation, sensitivity-downgrade or graph-deletion command
is added.

---

## M3.9 Command classification

Every new leaf is classified exactly once in `power.COMMAND_POLICY`.
`power.command_path` is extended to a third level (`subsubcommand`) because
`memory source add` and `memory edge add` are three-deep; `iter_command_paths`
already walks the real argparse tree, so a new leaf cannot slip past the
classification test by being forgotten.

| leaf | kind |
|------|------|
| `memory source list` | read_only |
| `memory source show` | read_only |
| `memory edge list` | read_only |
| `memory graph` | read_only |
| `memory contradictions` | read_only |
| `memory classify` | authoritative_write (ledger) |
| `memory source add` | authoritative_write (ledger) |
| `memory source link` | authoritative_write (ledger) |
| `memory edge add` | authoritative_write (ledger) |

Recovery mode blocks all four authoritative graph writes **before** mutation.
Deep mode keeps its preflight and committed-but-unhealthy post-verification
semantics. Both fall out of the generic gate once the classification is right.

---

## M3.10 Events

An event may contain only: claim/source/link/edge ids; safe enum names
(kind, relation, sensitivity, status); the project slug where already
considered safe; a sensitivity transition; endpoint ids; active/inactive
counts; bounded hash prefixes.

An event must **never** contain: a memory key or value; source text; a
locator; provenance free text; an evidence claim or ref; a secret-shaped
value; SQL or arbitrary exception text.

U-C3 warn-on-write is preserved for trusted human text fields. Diagnostics and
events carry field and detector NAMES only, never matched values. `events.emit`
redacts every secret-shaped string leaf via `secretscan.redact_tree`, which
remains the choke point.

---

## M3.11 Migration `2 → 3` (`u-m3-memory-graph-v3`)

The step body supplies schema/data changes only. Every guarantee around it is
U-M1's, unchanged — no migration or backup machinery is duplicated.

Order:

1. validate the complete registry;
2. acquire the migration lock (`BEGIN IMMEDIATE`);
3. re-read schema version 2 **inside the lock**;
4. create and verify a schema-v2 snapshot (sourced from a second reader
   connection — `conn.backup()` on the lock holder deadlocks);
5. rebuild `memory` using the **exact fresh-v3 DDL** (`db.MEMORY_CLAIM_DDL`);
6. preserve all schema-v2 rows and ids;
7. set `sensitivity='internal'`;
8. preserve `memory_evidence` exactly (it is not touched at all);
9. create the three new **empty** graph tables;
10. recompute all claim hashes under the v3 payload;
11. update `schema_version` to 3;
12. emit exactly one privacy-safe migration event.

### D-v0.3.43 — a rebuild, not ALTER TABLE ADD COLUMN

`ADD COLUMN sensitivity TEXT NOT NULL DEFAULT 'internal'` would work, but it
would leave the migrated table's SQL textually different from the fresh-v3
table's forever — the fresh/upgrade identity in M3.12 would be false, and
`db.MEMORY_CLAIM_DDL` would stop being the single definition. Rebuilding from
the same DDL constant makes the two identical by construction. This is the
U-M2 rule (D-v0.3.16) applied a second time.

### D-v0.3.43a — a shipped migration is frozen, not shared

U-M2 wrote the 1→2 step against `db.MEMORY_CLAIM_DDL` so a migrated table
could not drift from a fresh one. Correct while v2 was current; wrong the
moment v3 exists, because a shared constant follows the schema **forward**:
1→2 would build a v3-shaped table, stamp `schema_version = 2` on it, and hash
its claims under the v3 payload. The database would be a v3 table calling
itself v2 — and M3.11's guarantee that a failure inside 2→3 leaves a **valid
v2 database** would be false, because there would never have been one.

So `migrations._V2_MEMORY_CLAIM_DDL` and `_v2_claim_payload` are frozen copies
of the v2 definitions, and the 1→2 step builds from them. Each step leaves a
database that genuinely is what it says it is. The cost is one duplication per
schema version.

### D-v0.3.43b — the migration connection runs with `foreign_keys=OFF` plus a `foreign_key_check` per step

A rebuild must DROP `memory` while `memory_evidence` holds foreign keys into
it. That is an immediate violation under `foreign_keys=ON` (which every
connection has). U-M2's 1→2 step never met this: `memory_evidence` did not
exist yet when it dropped the v1 table.

Two candidates were measured, not assumed:

- `PRAGMA foreign_keys=OFF` **inside** a transaction is a silent no-op, so it
  must be issued before `BEGIN IMMEDIATE`.
- `PRAGMA defer_foreign_keys=ON` looks like the subtler answer and is not one:
  it counts the violations the DROP causes and never decrements them when the
  RENAME puts the table back, so the COMMIT fails anyway.

`apply_migrations` therefore sets `foreign_keys=OFF` on the migration
connection before opening the transaction — SQLite's documented table-rebuild
recipe — and the compensating control is **broader than what was switched
off**: every step, present and future, is followed by a `foreign_key_check`
over the whole database inside its own transaction, before its commit, and a
violation fails the step. Per-statement enforcement would have refused the
legal intermediate state; this refuses any illegal final one. The check
reports a COUNT only — a `foreign_key_check` row names a table and a rowid,
and both are ledger data (M1.10).

This is a change to U-M1 machinery rather than a duplication of it, and it is
made once, generically, rather than inside the step that needed it.

### D-v0.3.44 — no provenance is invented during migration

The migration creates **no** source, source-link or edge rows. A legacy claim
has no recorded provenance; inventing one — from `memory.source`, from linked
evidence, from anything — would fabricate ledger truth. The three graph tables
come out of the migration **empty**, which is the truth about every v2
database.

### Failure behavior

An injected failure anywhere inside the `2 → 3` step leaves:

- live schema version **2**;
- the schema-v2 memory table and its hashes intact;
- `memory_evidence` intact;
- **no** surviving graph tables;
- **no** migration event;
- a verified pre-migration snapshot available.

A corrected retry succeeds exactly once, with no duplicate effects.

---

## M3.12 Fresh / upgrade identity

A freshly initialized v3 schema and a v2→v3 migrated schema have identical:
memory table SQL; graph table SQL; indexes; constraints; supported schema
version; doctor invariants.

### D-v0.3.51 — one documented storage mechanic is normalized before comparison

`ALTER TABLE x RENAME TO memory` makes SQLite store the table's SQL with the
name QUOTED — `CREATE TABLE "memory"(...)` — where a fresh `CREATE TABLE
memory(...)` is unquoted. This is a rename artifact, not a schema difference:
the columns, types, defaults, CHECKs and foreign keys are character-identical
after it, and `PRAGMA table_info` cannot tell the two apart. It predates U-M3
(U-M2's rebuild produces it too).

It is the one "SQLite storage mechanic" M3.6 excludes, and it is named here
rather than waved at: the identity proof normalizes exactly this — the
quoting of the leading table name — and compares everything else byte for
byte, including every CHECK and FK clause.

### D-v0.3.45 — no explicit indexes are added

This schema has never carried an explicit `CREATE INDEX`; `tasks.project_id`,
`evidence.task_id` and every other hot column is scanned. The graph tables
follow that established design rather than introducing a new one. The UNIQUE
constraints already provide the implicit indexes the traversal's outbound
lookups use, the caps in M3.8a bound every traversal, and a personal ledger
does not have the row count that would make this matter. Fewer objects also
means fewer things the migration must replicate exactly — the identity in
M3.12 is preserved by construction rather than by vigilance.

### Fixture

`tests/fixtures/v2_workspace.py` builds a deterministic schema-v2 workspace
the same way `v1_workspace.py` builds a v1 one: production commands for every
table U-M3 did not change, then the historical v2 memory DDL installed over an
empty table, then rows written by a frozen replica of v2's `add_memory`. A
*source*, never a committed `.db`. The real ledger is never mutated to produce
a fixture.

`tests/fixtures/v1_workspace.py` gains one mechanical change: it must drop the
three new graph tables alongside `memory_evidence` when it reinstalls the v1
schema, or a "v1" fixture would carry v3 tables and the 2→3 step would then
try to create them twice.

---

## M3.13 Packs, search, mirror

### Packs

- Existing U-M2 live/eligible/integrity rules preserved.
- **Restricted claims excluded**, at the one canonical inclusion predicate
  (`ops.memory_for_project`) — not at the pack renderer, so a future caller
  cannot re-open the hole.
- Pinned-first ordering preserved.
- **No graph expansion.** Graph neighbours are not automatically included.
  Optional bounded active provenance/relationship counts only.

### Search

- Memory result metadata carries `sensitivity`.
- Restricted claims may match administratively, but the rendered title and
  snippet are suppressed to a fixed placeholder — no key, no body, no value.
- Historical status remains visible.
- No semantic or graph ranking is added.

### Obsidian mirror

- `public` / `internal` / `confidential` retain their current body
  projections exactly.
- **Restricted claims render an ID-only metadata placeholder** — no key, no
  value, no source, no evidence links.
- Bounded source/edge/contradiction counts may be shown.
- New graph projections never render a source locator, provenance text, or an
  evidence ref.

### Generated reviews (file-boundary deviation: `agentic_os/review.py`)

Not named in the unit's expected-file list, but a real call path requires it:
`review build` / `weekly` / `project` render memory **keys** into
`AOS/Reviews/*.md`, which is a generated context summary that lands in the
vault and syncs wherever the vault syncs. A restricted claim's key must not
reach one, so the two memory sections there use the same placeholder as every
other surface. The claim is still LISTED by id — an operator whose restricted
claim has gone stale needs to be told, and the wikilink must still resolve.

---

## M3.14 Doctor

Five new bounded checks (26–30; the count pin moves 25 → **30**):

26. **memory sensitivity is known** — unknown sensitivity values (FAIL).
27. **memory sources are well-formed** — malformed/mismatched/unhashable
    hashes; unknown `source_kind`; invalid source-kind target shape; missing
    evidence or project target; invalid validity interval (FAIL).
28. **memory source links resolve** — missing memory/source targets;
    duplicate logical links; cross-project links; source sensitivity
    exceeding claim sensitivity; hash problems (FAIL).
29. **memory edges are well-formed** — self-edges; non-canonical symmetric
    edges; duplicate edges; cross-project edges; invalid intervals; unknown
    relations; missing endpoints; hash problems (FAIL).
30. **restricted claims absent from generated context** — restricted claim
    text present in pack files or mirror notes on disk (**WARN**).

#### D-v0.3.46 — check 30 warns, never fails

A pack built *before* a claim was classified restricted legitimately contains
it: the operator did nothing wrong and no invariant was violated at the time.
It is still a real leak on disk they must know about, and `pack build` /
`sync` regenerate it away. A check that turns red because history happened is
a broken check (the U-M2 D-v0.3.22 rule).

Diagnostics are **ID / count / reason-code only**. Never a claim key or value;
never a source locator or provenance; never an evidence ref or claim; never a
full hash; never secret-shaped content; never an arbitrary SQLite value. BLOB
and malformed text values are handled without crashing — a damaged row must be
REPORTABLE, which a diagnostic that crashes on it is not.

---

## M3.15 Filesystem and privacy

### D-v0.3.47 — every graph reference is inert

No graph command follows a file locator, a URL, a command string, an evidence
ref, or an artifact path. They are strings the operator asked the ledger to
remember. No graph command opens a referenced file, performs network access,
or executes content. No command rewrites source files or creates adjacent
derived objects.

---

## M3.16 Zipapp and entrypoint parity

Script (`python aos.py`), module (`python -m agentic_os`) and standalone
zipapp (`aos.pyz`, PYTHONPATH cleared) produce identical output and exit codes
for: `migrate status` on schema v2; `migrate plan` showing exactly 2→3;
`migrate apply`; `memory classify`; `source add/list/show/link`;
`edge add/list`; graph traversal; contradiction listing; doctor after
migration.

The zipapp carries implementation through the **existing** package allowlist
(root shim + `agentic_os/**/*.py`), which needs no change. It must not
contain: fixture databases, migration snapshots, test data, source locators,
user workspaces, or backups.

---

## M3.17 Decisions index

| id | decision |
|----|----------|
| D-v0.3.31 | Sensitivity is a closed, ORDERED vocabulary. |
| D-v0.3.32 | Sensitivity defaults to `internal`. |
| D-v0.3.33 | Pinned never overrides sensitivity. |
| D-v0.3.34 | A source row copies no text from what it references. |
| D-v0.3.35 | A link's logical identity is (memory, source, relation). |
| D-v0.3.36 | Symmetric relations canonicalize endpoints (lower id first). |
| D-v0.3.37 | Supersession is not duplicated as a graph relation. |
| D-v0.3.38 | Contradictions are typed edges, not a second table. |
| D-v0.3.39 | No contradiction is ever inferred. |
| D-v0.3.40 | Every text leaf is bound by its digest. |
| D-v0.3.41 | Verify before mutate: no write may launder tampering. |
| D-v0.3.42 | Traversal caps truncate deterministically and say so. |
| D-v0.3.43 | Migration rebuilds `memory` from the fresh DDL, not ADD COLUMN. |
| D-v0.3.44 | No provenance is invented during migration. |
| D-v0.3.45 | No explicit indexes are added. |
| D-v0.3.46 | Doctor's restricted-in-context check warns, never fails. |
| D-v0.3.47 | Every graph reference is inert. |
| D-v0.3.48 | SQLite graph records are canonical; graph engines are derived. |
| D-v0.3.49 | Graph relations trigger no workflow. |
| D-v0.3.50 | Classification increases only in U-M3; downgrades are U-S6. |
