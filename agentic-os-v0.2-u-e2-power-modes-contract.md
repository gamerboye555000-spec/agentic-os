# Agentic OS v0.2 — U-E2 runtime power modes (contract)

Task: T-0012 · Branch: `v0.2-u-e2-power-modes` · Baseline: `c635456`

Runtime power modes govern **local CLI execution policy** for one workspace.
They never choose an LLM, call a model, start a daemon, execute background
work, or grant autonomy. Suggestions are deterministic and advisory; the human
is the only actor that changes the configured mode.

This contract is pinned before production edits. Every deviation found while
implementing is recorded in "Deviations and findings" at the bottom rather than
silently resolved.

---

## 1. Modes

| mode | intent |
|---|---|
| `eco` | do the asked-for work; defer optional implicit derived refresh |
| `standard` | baseline behavior, byte-for-byte (the default) |
| `deep` | bounded read-only integrity + secret preflight around authoritative writes |
| `recovery` | fail-closed: authoritative and derived mutation refused |

Automatic mode switching never happens, in any mode. `power suggest` prints
advice; only `power set` changes state.

## 2. Authoritative mode state

Path: `<workspace>/.agentic-os/power.json` — one small operational sidecar,
**not** the SQLite schema or `meta` table (D-v0.2.51). Recovery control must be
reachable when the database is unopenable, version-mismatched, or corrupt;
storing the mode in the ledger would make the control depend on the thing it
exists to recover.

Exact serialized form (compact, key order fixed, newline-terminated, UTF-8):

```
{"version":1,"mode":"standard"}
```

Rules:

- **Missing file means `standard`.** Absence is a valid, expected state.
- Missing state **must not create a file** during `status`, `suggest`, `doctor`,
  or any other read-only command. Only `power set` creates or replaces it.
- The schema version of the ledger is **not** changed by U-E2. No migration.
- `power set` emits **no ledger event** — see Deviation D-1.

### 2.1 Accepted state

A power state is valid only when **all** hold:

- the path is an **existing regular file** (`lstat`, never `stat` — a symlink
  is seen as a symlink, never followed);
- size ≤ `MAX_STATE_BYTES` (4096);
- bytes decode as **strict UTF-8**;
- the text is exactly one JSON document (trailing data rejected by `json.loads`);
- the document is a JSON **object** with **no duplicate keys**
  (`object_pairs_hook`);
- keys are exactly `{"version", "mode"}` — no unknown fields, no missing fields;
- `version` is `1` and is a real `int` (`type(v) is int`, so `true` is rejected);
- `mode` is a `str` and one of the four modes.

Anything else is **malformed or unsafe**. Diagnostics name the failing
condition only — never the file content, never a raw path.

### 2.2 Fail-closed posture of a malformed state

A malformed or unsafe power state means **the mode is unknown**. Defaulting to
`standard` would silently ignore a configured `recovery`, so:

- `read_only` and `recovery_safe` commands **proceed** and can report the
  problem (`doctor`, `power status`, `power suggest` stay usable);
- `derived_write` and `authoritative_write` commands **refuse** through
  `AosError`;
- **every** `power set` transition refuses, without replacement. The state is
  never silently repaired.

Recovery is manual and documented: delete `power.json` (absence = `standard`),
then re-set the mode. This is the only case where deletion guidance is given.

### 2.3 Write protocol

1. `lstat` the final path; refuse any existing non-regular object (symlink,
   directory, FIFO, socket, block/char device) **unchanged**.
2. `mkstemp` a same-directory temporary regular file (`.power-*.tmp`).
3. Write the complete payload, `flush`, `fsync` the file.
4. `os.replace` onto the final path (atomic, same filesystem).
5. `fsync` the parent directory where supported (best-effort over a fixed errno
   allowlist; a platform without directory fsync is not an error).

On any failure: the previous bytes are preserved (the destination is never
opened for writing), and the temporary file is unlinked in a `finally` — no
partial file, no debris.

### 2.4 Concurrency — no lock file

`power set MODE` is an **absolute assignment**, not a read-modify-write delta.
`os.replace` is the serialization point: every writer renames one complete,
already-valid file, so two concurrent sets can never interleave into malformed
or mixed JSON, and the final file is always exactly one valid requested state.
Therefore **no lock file, no lock table, no daemon, no third-party library**.

The only read-before-write is the idempotence probe and the validity/safety
gate, and both **fail closed** (they can skip a write or refuse, never widen
what is written). Known bounded behavior, accepted deliberately: if A observes
`eco` and requests `eco` (no-op) while B concurrently sets `standard`, A
truthfully reports the state it observed and B's value lands. The file still
holds one complete valid state; nothing is corrupted or half-applied.

### 2.5 Idempotent set

`power set X` is a no-op when the file **exists and already holds** `X`:
success, `power.json` **not rewritten**, bytes and metadata preserved.

When the file is **absent** and `X` is `standard`, the file **is** created: the
human explicitly asked to pin the mode, and pinning is observable (`doctor`
then reports `configured` rather than `default`). A second identical set is
then the no-op above.

## 3. Transitions

- `power set recovery` is available **whenever the initialized workspace and
  the power-state path are safely inspectable** — including while `doctor`
  reports hard failures, and including when the database cannot be opened at
  all. It never consults the ledger.
- `power set eco|standard|deep` requires **all hard doctor checks to pass**
  (warn-only checks never block). A ledger that cannot be opened counts as a
  hard failure, so leaving `recovery` is impossible until the ledger is
  healthy — which is the point.
- A malformed/unsafe existing state refuses **all** transitions (§2.2).
- `power` commands never call `db.open_db` — the schema-version gate would make
  recovery control unreachable on exactly the databases that need it.

## 4. Central command classification

One canonical table in `agentic_os/power.py` maps **every** CLI leaf, keyed by
its argparse path tuple, to exactly one class. Mutability is never inferred
from a command name or its help prose.

| class | meaning | recovery |
|---|---|---|
| `read_only` | reads only; writes nothing durable | allow |
| `derived_write` | writes only regenerable artifacts **outside** the ledger | block |
| `recovery_safe` | explicitly safe under recovery (no live mutation) | allow |
| `authoritative_write` | writes ledger rows, or durable state outside it | block |

The classifying rule, applied mechanically:

> **A command that writes any row to `aos.db` — including an audit event — is
> `authoritative_write`.** Writing a derived *artifact* does not soften that.

A `ledger` flag rides alongside the class. Deep preflight/post-verification
apply **only** to `authoritative_write` commands with `ledger=True`, so
`hooks install` and `init` (which touch no existing ledger) receive no
unnecessary ledger preflight.

A test walks the live argparse tree and fails on any unclassified leaf, and on
any classification entry with no matching leaf. Coverage is proved by
construction, never by prose.

## 5. Mode semantics

### eco
Authoritative commands remain available. Explicit derived commands remain
available. Only **already-implicit, already-optional** derived refresh is
deferred; nothing new is invented to distinguish eco from standard.

Audit finding: the baseline has **exactly one** such site —
`ops.init_workspace()` re-heals the Obsidian mirror on an
**already-initialized** workspace (`created=False`) while `init` reports
"nothing to do". That refresh is implicit, optional, and fully regenerable via
`sync`. Eco defers it and says so on stdout. The `created=True` path always
heals (a new workspace must be usable) and is never deferred.

Never deferred in eco: authoritative SQLite writes, evidence, events, backups
requested explicitly, safety validation.

### standard
Baseline behavior byte-for-byte wherever U-E2 does not explicitly add power
reporting or gating. No new deep preflight. No automatic doctor after commands.

### deep
Before each authoritative ledger write, a **bounded read-only** preflight:

1. `PRAGMA integrity_check` through the existing `db.connect` primitive;
2. the existing U-C3 ledger secret sweep (`doctor.secret_sweep_findings`).

A hard integrity failure or any secret-shaped ledger finding **refuses the
write**. Diagnostics name the **check name and a count only** — never a row
value, database content, SQL, secret, exception internals, or unbounded data.
The human is pointed at `doctor` for the (already bounded and safe) detail.

After a successful authoritative ledger write the same two checks re-run. On
failure the command reports, honestly, that it **already committed** and that
deep verification failed, recommends `power set recovery`, and exits 1 through
`AosError`. It **never** claims a rollback and **never** performs one.

Read-only and derived-write commands receive no deep preflight.

### recovery
Fail-closed for authoritative and derived change. Allowed: `read_only` +
`recovery_safe` only. The refusal exits through the existing `AosError` path
(exit 1), leaves **stdout empty** (it fires before dispatch), names the blocked
command path and the current mode, and gives a safe hint. It echoes no payload,
file content, secret, ID, or arbitrary exception text.

## 6. Doctor integration

One new check, `runtime power state`, appended as **check 21**. Reports the
current mode, whether it came from the default or `power.json`, and a concise
degradation summary. Never prints raw JSON or an unsafe path. Doctor stays
runnable — and reports rather than crashes — when the file is malformed.

```
[PASS] runtime power state — standard (default)
[PASS] runtime power state — recovery (configured; authoritative writes blocked)
[FAIL] runtime power state — malformed or unsafe configuration
```

The mandated-check pin moves 20 → 21 (the D-W8.1 pattern: the pin moves up with
a mandated new check).

## 7. Deterministic suggestion policy

`power suggest` is read-only, never writes `power.json`, and uses a fixed
priority with no model call, no scoring model, no natural-language heuristic,
no environment telemetry, and no CPU/RAM probing:

1. any hard doctor failure → `recovery`
2. else any doctor warning → `deep`
3. else any active ledger work (runs with `ended_at IS NULL`) → `standard`
4. else clean and idle → `eco`

Doctor runs through `db.connect` (not `open_db`) so a version-mismatched
database surfaces as doctor check 7 failing — priority 1 — instead of an
exception. A database that cannot be read at all is priority 1 with the fixed
phrase `doctor could not complete`.

Output states only the **signal category** and a bounded count. No ledger
content, titles, summaries, refs, claims, secrets, paths, or free text.

## 8. Degradation-matrix output

`power status` prints a stable, bounded, fixed-width matrix for all four modes,
with no terminal-width-dependent formatting. Columns: authoritative writes ·
explicit derived writes · implicit derived work · deep preflight · safe
recovery utilities · automatic mode switching (always `no`). The active row is
marked `*` with a legend.

## 9. Entrypoint and zipapp

The zipapp allowlist is `*.py` under `agentic_os/` (U-P1), so `power.py` is
included **automatically** — no builder change. Script / module / zipapp parity
is proved for `power status`, `power suggest`, `power set`, and the recovery
refusal, and the archive runs outside the repository with `PYTHONPATH` cleared.
No `power.json`, workspace, database, fixture, or local state is embedded.

## 10. Exclusions (unchanged by U-E2)

Schema version and migration registry · memory schema/behavior · hook protocol
and installer semantics · ingest/evidence rules · backup/restore contracts ·
export containment · U-E1 pack effort tiers · orchestration, autonomy, MCP/A2A,
routing, AICompany, CI, releases.

---

## Deviations and findings

**D-1 — `power set` writes no ledger event.** Every other mutation in this
codebase journals an event. `power set` cannot: it must work when the database
is unopenable, which is precisely the state in which `recovery` is set. Emitting
an event would reintroduce the dependency the sidecar exists to remove. Cost:
mode changes have no audit trail. Accepted deliberately; recorded in DECISIONS.

**D-2 — `backup create` and `snapshot` are blocked in recovery.** The mission's
allow-list permits "backup creation *where it reads the live DB without
mutating it*". Both commands emit a ledger audit event (`backup_create`,
`snapshot`) inside `db.transaction`, so they **mutate** and fail that condition.
They are classified `authoritative_write` and blocked. `backup verify` and
`backup restore` remain allowed (they never touch the live ledger).
`backup.write_backup_pair()` is eventless but has no CLI surface; exposing one
would be scope creep and is not done.

**D-3 — `review build|weekly|project` are blocked in recovery.** The allow-list
covers "read-only show/list/search/**review** commands"; the `review`
subcommands all *write* a note file, so the "read-only" qualifier excludes them.
They are `derived_write`.

**D-4 — eco's deferral set is one site.** See §5/eco. Reported rather than
padded: inventing automatic derived refresh purely to make eco visibly differ
from standard is explicitly forbidden.

**D-5 — Recovery can stall on a mirror-level hard failure, by mandate.** Both
mission rules are implemented exactly as written: recovery blocks `sync`/mirror
regeneration, and leaving recovery requires all hard doctor checks to pass. When
the failing hard checks are the mirror ones (`Home.md exists`, `wikilinks
resolve…`, `required folders exist`), the only repair is `sync` — which recovery
blocks. Verified in the disposable dogfood; not a bug in the implementation but
a consequence of the two mandates meeting.

Not resolved by widening the classification: making `sync` recovery-safe would
contradict the explicit block-list, and dropping mirror checks from the
transition gate would contradict "all hard doctor checks". Resolved instead by
documenting the manual escape, which is the same one a malformed state uses and
is provably safe: `rm .agentic-os/power.json` (absence means `standard`) →
`sync` → `power set <mode>`. `power.json` holds no ledger data, and the mirror
is regenerable from the ledger. TROUBLESHOOTING carries the drill, including the
warning NOT to use it when the failing check is `database integrity_check` or
`schema_version supported` — that is real ledger damage, and `sync` will not fix
it.
