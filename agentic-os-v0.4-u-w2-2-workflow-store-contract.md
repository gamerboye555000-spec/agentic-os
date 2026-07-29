# Agentic OS v0.4 — U-W2.2: deterministic workflow store (Wave 0 architecture freeze)

Architecture freeze only. Baseline
`63de8c953f2613a79d6e1bb6052646c669894863` (U-W2.1 deterministic workflow
state engine merged, ledger schema version `"5"`, milestone
`milestone/v0.4-u-w2-workflow-state-engine`; HEAD, `origin/main`, and the
merge-base are this same commit). Branch `v0.4-u-w2-2-workflow-store`;
worktree `/home/daksh/Projects/agentic-os-u-w2-2`; primary checkout
`/home/daksh/Projects/agentic-os`. Future PR title:
`feat(v0.4): U-W2.2 — deterministic workflow persistence`. Future commits:
exactly the two frozen by U-W2 amendment §A.7 — `docs: adopt U-W2 path
amendment and freeze U-W2.2 store architecture`, then
`feat(v0.4): add deterministic workflow store` (§19.5). Future tag:
`milestone/v0.4-u-w2-2-workflow-store`. Decisions: D-v0.4.83 – D-v0.4.95.

U-W2.2 is the persistence half of U-W2: the SQLite shell that gives the
landed pure reducer a durable home. It stores an authoritative append-only
workflow history, a derived snapshot projection under revision
compare-and-swap, an outbox of queue intents, an inbox of queue receipts,
and the verbatim external facts a success or approval claim rests on. It
decides nothing the reducer has not already decided, executes nothing,
retries nothing, delivers nothing, and grants nothing. This document
freezes the architecture; a later wave implements it. The implementation
and tests must mechanically agree with this document — a sentence here that
the code cannot demonstrate is a defect in one of the two.

Extends and is subordinate to the landed U-W2 contract
(`agentic-os-v0.4-u-w2-workflow-state-engine-contract.md`), which froze
§14's persistence model and named this slice in its §18, and which — as of
this wave — carries governed amendment A1, appended by this wave with the
landed body byte-preserved as the file's exact prefix. Amendment A1
supersedes the original five-path slice table and authorizes the closed
nineteen-path inventory this contract's §19 restates; references written
`U-W2 §A.n` point at it. It further extends the U-X1 protocol spine
(`agentic-os-v0.3-u-x1-protocol-spine-contract.md`), the U-M1 migration
contract (`agentic-os-v0.2-u-m1-migration-contract.md`), and the U-W1
compiler contract (`agentic-os-v0.4-u-w1-workspec-compiler-contract.md`).
Delivery flows through the U-P2 gate
(`agentic-os-v0.4-u-p2-delivery-gate-contract.md`, as amended by
`agentic-os-v0.4-u-p2-trust-boundary-amendment.md`).

Section references written `U-W2 §n` point at the landed U-W2 contract;
plain `§n` points at this document.

## 0. Scope

### 0.1 In scope (frozen here, implemented in a later wave of this slice)

- One new persistence module, `agentic_os/workflow_store.py`: the SQLite
  shell that reads a workflow's history, rebuilds the reducer's snapshot,
  submits one accepted command per transaction under revision
  compare-and-swap, appends workflow events, writes the outbox/inbox/fact
  rows, journals through `events.emit`, and reports integrity without ever
  repairing it (§8–§18).
- Schema version `"6"`: six new tables in `agentic_os/db.py` under their
  frozen names, composed into `SCHEMA_SQL` from one new table tuple (§5).
- One purely additive migration `u-w2-workflow-state-v6` (5 → 6) in
  `agentic_os/migrations.py`, the U-A3 4 → 5 idiom applied again (§6).
- One new ledger ID prefix in `agentic_os/ids.py`: `"workflow": "WF"`,
  for `ids.parse_id` only (§5.1, D-v0.4.85).
- One new focused test module `tests/test_v04_workflow_store.py` (§20).
- The mechanical schema-version-pin and fixture updates in eight existing
  test modules and three existing fixtures, authorized for this one
  delivery — and no other — by U-W2 amendment §A.4.3 (§19.3, D-v0.4.94,
  D-v0.4.95). The authorization is not standing: a future
  `db.SCHEMA_VERSION` bump requires its own governed amendment.

### 0.2 NOT in scope (mechanically absent, not merely discouraged)

- No change to `agentic_os/workflow_engine.py`. The landed reducer is
  consumed byte-unchanged; U-W2.2 adds no state, command, event, receipt
  kind, refusal reason, or matrix edge, and never widens
  `WORKFLOW_REFUSAL_REASONS` (§7.4, §20 row S23).
- No CLI verb, no `power.COMMAND_POLICY` entry, no `README.md` section —
  all U-W2.3 (`agentic_os/cli.py`, `agentic_os/power.py`, `README.md`,
  `tests/test_v04_workflow_cli.py`).
- No transport of any kind: no file export, no directory walk, no network,
  no socket, no subprocess, no MCP, no A2A. The store hands intent records
  to a caller; writing them anywhere is U-W2.3's `export-intents`.
- No queue authority: no lease, no attempt counter, no worker, no
  heartbeat, no delivery tracking beyond an intent's three-valued
  `status`, no cancellation the runtime has not acknowledged (§16.2).
- No retry, checkpoint, resume, or compensation machinery (U-W3). The
  store contains no loop that re-issues a command, no sleep, and no
  automatic re-decision (§12.6).
- No loop-health monitor (U-W4), no semantic interrupt kernel (U-W5), no
  durable-engine adoption (U-W6).
- No repair: nothing in this slice updates or deletes a `workflow_events`
  row ever, nothing updates or deletes a `workflow_commands`,
  `workflow_receipts`, or `workflow_facts` row after its creating
  transaction commits (the §5.8 hash finalization is the sole
  in-transaction `UPDATE`), and nothing rewrites history to make a
  divergent snapshot agree (§15.4).
- No approval, policy, budget, credential, or capability decision.
- No shared database: `workflow_store` opens no connection of its own and
  touches no path; it operates on the `aos.db` connection its caller
  supplies and issues SQL against the six new tables, the two read-only
  `tasks` columns (`id` keyed, `status` selected), read-only `meta`, and
  write-only `events` through `events.emit` (§4.4, §17.1, §20 row S21).
- No protocol change: `agentic_os/protocols.py` and `protocols/**` are
  untouched; the six `aos.*` record schemas minted by U-W2.1 are reused
  exactly (§5.9).
- No doctor, backup, export, mirror, obsidian, retrieval, or memory
  change.

### 0.3 Untouched

`agentic_os/workflow_engine.py`, `agentic_os/workspecs.py`,
`agentic_os/protocols.py`, `protocols/**`, `agentic_os/models.py`,
`agentic_os/events.py`, `agentic_os/ops.py`, `agentic_os/utils.py`,
`agentic_os/governance.py`, `agentic_os/passports.py`,
`agentic_os/catalog.py` and `agentic_os/catalog/*`,
`agentic_os/routing.py`, `agentic_os/agent_handoffs.py`,
`agentic_os/secretscan.py`, `agentic_os/doctor.py`, `agentic_os/hooks.py`,
`agentic_os/ingest.py`, `agentic_os/backup.py`, `agentic_os/export.py`,
`agentic_os/mirror_export.py`, `agentic_os/cli.py`, `agentic_os/power.py`,
all delivery-control files (`.github/workflows/ci.yml`,
`tools/verify_ci_workflow.py`, `tests/test_v04_delivery_gate.py`),
`pyproject.toml`, `README.md`, `tests/test_v04_workflow_engine.py`, and
`tests/test_v04_workspec_compiler.py`. The eleven existing test and
fixture files named in §19.3 receive ONLY the edits enumerated there under
U-W2 amendment §A.4.3; no test is deleted, skipped, or weakened, and
exactly one assertion — the `test_no_version_six_transition_exists`
ceiling guard — is re-scoped and renamed, declared in §19.3.

## 1. Decisions (index)

- **D-v0.4.83** — slice identity: U-W2.2 is persistence only; the landed
  U-W2.1 reducer is consumed byte-unchanged and re-verified rather than
  re-implemented; U-W2.3 owns CLI/docs, U-W2.R owns the private runtime
  adapter, U-W3 owns retry/checkpoint/resume/compensation, and the local
  and runtime databases are never shared (§4).
- **D-v0.4.84** — schema version `"6"` is exactly the six frozen tables
  under their frozen names, with the columns, CHECKs, UNIQUEs and foreign
  keys of §5; the 5 → 6 migration is purely additive, iterated from one
  `db.WORKFLOW_TABLES` constant, created FK-parent-first under real names,
  and byte-identical to a fresh init for those six tables (§5, §6).
- **D-v0.4.85** — the `workflows` row is a PROJECTION, not the snapshot:
  the reducer's `aos.workflow-snapshot/v1` value is rebuilt by
  `fold(events)` plus the two stored bodies on every command, and the
  stored `content_sha256` is the agreement gate. Seven derived snapshot
  fields therefore need no column, and the identity is derived, never
  allocated (§7.2, §7.3).
- **D-v0.4.86** — events are reconstituted from their columns rather than
  stored twice, and the sealed event digest is the proof the
  reconstitution is faithful; the four row-hash tables
  (`workflow_commands`, `workflow_intents`, `workflow_receipts`,
  `workflow_facts`) carry `record_schema` row hashes in the U-A3 idiom,
  while `workflows` and `workflow_events` carry the record digests U-W2
  §9/§14.2 already assign them (§5.8, §7.4).
- **D-v0.4.87** — `StoreOutcome` is a RETURNED, closed four-status record
  (`accepted`, `replay`, `refused`, `conflict`); a refusal never raises out
  of `submit`, persists nothing in any of the six tables, and writes no
  AOS journal row — journaling a refusal is U-W2.3's (§9).
- **D-v0.4.88** — the public store API is exactly seven functions and six
  types; `WorkflowStoreError` carries exactly three infrastructure codes
  and never adds a member to the frozen 43-reason workflow vocabulary
  (§8).
- **D-v0.4.89** — one `BEGIN IMMEDIATE` transaction per accepted command,
  in one frozen mutation order per path, routed through nine named
  mutation helpers; the CAS is `WHERE id = ? AND revision = ?` with a
  required rowcount of 1, the admission gate is the `workflows` INSERT,
  and the whole write path reads no clock (§10, §11, §12).
- **D-v0.4.90** — two dedupe axes, both evaluated before `decide`: commands
  by `command_id` + recomputed digest, receipts by `receipt_id` +
  recomputed digest; exact duplicates replay the original events, digest
  disagreements are the distinct `conflict` status, nothing is merged, and
  nothing is ever pruned (§14).
- **D-v0.4.91** — contention handling is SQLite's already-configured
  bounded busy timeout and nothing else: no loop, no sleep, no re-issue,
  no automatic re-decision — which is why it is a storage primitive and
  not U-W3 retry behavior (§12.6).
- **D-v0.4.92** — integrity is REPORTED, never repaired: a closed
  five-member `STORE_INTEGRITY` vocabulary, read paths that stay total on
  a damaged workflow, mutating commands that refuse on one, and a `verify`
  that writes nothing (§15).
- **D-v0.4.93** — persisted rows are untrusted input: every digest is
  recomputed from stored bytes at use, every statement is parameterized
  with frozen table-name constants, no stored value reaches a refusal
  message or a journal payload un-redacted, and no stored text is ever
  executed, imported, or treated as an instruction (§18).
- **D-v0.4.94** — the exact implementation boundary is the nineteen paths
  of §19 — the closed inventory U-W2 amendment §A.4 authorizes: four
  production paths, one new test module, the eleven mechanical
  test/fixture paths whose edit class every prior schema bump exhibits
  (U-A3 commit `7c5fea4`), and the three Wave-0 architecture documents
  (§19.3, §19.5).
- **D-v0.4.95** — governed amendment A1 to the landed U-W2 contract:
  appended to that contract file with the landed body byte-preserved as
  the exact prefix; supersedes exactly the clauses its §A.3.1 enumerates
  (the five-path slice table, the closure rule's table binding, §0.3's
  every-test/fixture clause for the eleven files, §19.22's byte-unchanged
  clause, D-v0.4.81's exhaustiveness and one-PR claims, the per-event
  journal reading); extends D-v0.4.81 without rewording it; authorizes
  this one delivery over the nineteen paths and creates no standing
  expansion authority (U-W2 §A.1–§A.10).

## 2. Dependencies, live surfaces, and evidence

Proven present at the baseline. Every path is the exact live path and
every digest was computed in this session (`sha256sum`, worktree
`/home/daksh/Projects/agentic-os-u-w2-2` at
`63de8c953f2613a79d6e1bb6052646c669894863`).

| Needed surface | Exact live equivalent | SHA-256 |
| --- | --- | --- |
| Pure reducer (U-W2.1) | `agentic_os/workflow_engine.py` — `decide`, `fold`, `verify_history`, `AdmissionFacts`, `WorkflowDecision`, `WorkflowRefusal`, `WORKFLOW_STATES/COMMANDS/EVENTS/REFUSAL_REASONS/RECEIPT_KINDS`, `TRANSITION_MATRIX`, `TRANSITION_POLICY_VERSION`, `SUPPORTED_POLICY_VERSIONS`, the six `aos.*` record-schema constants | `da2499baac50c6812d4ee74e2308825c48bea7833d2c07b94389d6d737089952` |
| Acceptance seam (U-W1) | `agentic_os/workspecs.py` — `accept_work_spec`, `accept_compile_report`, `WorkSpecError`, `WORKSPEC_LINT_CODES` | `873b90caf0bfac5738f3154ae0aa4b37cc11b4d6724c0c0229d30eb22477f101` |
| Canonical serialization | `agentic_os/protocols.py` — `serialize_canonical` (→ bytes), `parse_canonical` (bytes →), `content_digest`, `CONTENT_HASH_FIELD`, `MAX_ARTIFACT_BYTES=262144`, `MAX_ARRAY_ITEMS=256`, `MAX_STRING_CHARS=8192`, `INT_MAX=2**53-1`, `ProtocolError` | `6a380328cd6af70120de7874db66f5146a9d89927ccef54b872ab13e9a393c70` |
| Schema, connection, transaction | `agentic_os/db.py` — `SCHEMA_VERSION = "5"`, parameterized `{table}` DDL constants, table-name constants, `MEMORY_GRAPH_TABLES`/`ROUTING_HANDOFF_TABLES` tuples, `SCHEMA_SQL` composition, `connect` (`foreign_keys=ON`, `busy_timeout=5000`, `timeout=5.0`), `transaction`, `_check_schema_version` | `6e52b8670f4ac5c405bf5fa180208ea5abc709640bb5b53e3db39dfe274bddd7` |
| Migration framework | `agentic_os/migrations.py` — `Migration(from_version, to_version, migration_id, apply)`, `MIGRATIONS` 1→2→3→4→5, `LATEST_VERSION = int(db.SCHEMA_VERSION)`, `_routing_handoffs_v5` (the additive precedent), backup-first `apply_migrations`, frozen-history rule, per-step whole-database `foreign_key_check` | `47968ca945e6b73660f2e0533a2403d410f3e01b59243cde6d650bc18c986db3` |
| Append-only journal | `agentic_os/events.py` — `emit(conn, *, actor, entity, entity_id: int|None, action, payload)`, `PAYLOAD_SCHEMA_VERSION = 1`, `redact_tree` choke point | `02d7cda983a0fbf533e0deff68010516f98f42c5929da7ba39afe47fb2c6c448` |
| Ledger identifiers | `agentic_os/ids.py` — `PREFIXES` (12 entries, no `workflow`), `MAX_ID = 2**63-1`, `parse_id`, `render_id` | `5f0c35f0de3f56ae53075cf9a2ecb65212ef4575616f2c0392c9d507a56810d7` |
| Task vocabulary | `agentic_os/models.py` — `TASK_STATUSES = ("inbox","ready","in_progress","done")`, `RUN_OUTCOMES` | `03c0c6a9fbcd57319da79cd4bf922e3d438906806de7911c475c2b5073703ef8` |
| Task/run behavior | `agentic_os/ops.py` — `get_task`, `set_task_status`, `start_run`, `end_run`, `mark_done`, `add_evidence`, `add_git_evidence`; `LEGAL_TASK_TRANSITIONS` | `591ce3e1968259a0319fc2e924cda929906f3db8731ee85b04c9fe01ed277c7f` |
| Row-hash idiom | `agentic_os/agent_handoffs.py` `_digest`/`handoff_payload`/`transition_payload` (`record_schema` key, sha256 text leaves, direct ints, `content_sha256` excluded), `HandoffHashError` (unreadable row, field name only) | — |
| Write-lock idiom | `agentic_os/routing.py:1252`, `agentic_os/agent_handoffs.py:835,1017` — `with db.transaction(conn): conn.execute("BEGIN IMMEDIATE")` before every re-read | — |
| Migration equivalence idiom | `tests/test_v04_routing_handoffs.py:373-401` — fresh vs migrated `sqlite_master.sql` byte-identical for the NEW tables, `events`/`meta` excluded, built from `build_v3_workspace` | `62236a410de347fcb3575f66aabef1187e788ffeac6a0b012473ebb625694b58` |
| Historical fixtures | `tests/fixtures/v1_workspace.py`, `v2_workspace.py`, `v3_workspace.py` — build a current-schema database, then DROP every table newer than the target version (children first, iterated from the `db.py` table tuples) | — |
| Persistence module | NONE. `agentic_os/workflow_store.py` does not exist; no repository file outside the landed U-W2 contract, `DECISIONS.md`, and one `workflow_engine.py` docstring line mentions it (verified) | — |
| Explicit index | NONE anywhere in the schema. `tests/test_v04_agent_passports.py:229-240` and `tests/test_v04_routing_handoffs.py:850-869` pin that UNIQUE constraints carry the implicit indexes and no explicit `CREATE INDEX` exists | — |

Boundary reconciliation with the landed contract (frozen):

- U-W2.1 owns the lifecycle vocabulary, the transition matrix, the closed
  command/event/refusal/receipt vocabularies, all document verification,
  the derived identifiers, `decide`, `fold`, and `verify_history`. U-W2.2
  calls them and re-implements none of them.
- U-W2.2 owns the schema, the migration, the transaction, the
  compare-and-swap, the dedupe/replay/conflict decisions that need stored
  rows, and the integrity report.
- U-W2.3 owns every CLI verb, every power-policy entry, the README
  section, and the observability journal row for a REFUSED command.
- U-W2.R owns the private-runtime queue adapter, in another repository,
  against another database.
- U-W3 owns retries, checkpoints, resume, and compensation; U-W4 loop
  health; U-W5 semantic interrupts and approval revocation; U-W6 the
  durable-engine trigger.

## 3. Threat and failure model; trust boundary

- **Every persisted row is untrusted input.** A `workflows` row, a
  `workflow_events` row, a stored intent, receipt, or fact document may
  have been written by direct SQL, corrupted by hardware, or restored from
  a tampered backup. The store therefore re-derives rather than trusts:
  every digest is recomputed from the stored bytes at every use, the
  workflow identity is re-derived from the admitted artifact digest, the
  history is re-verified before it is folded, and the reducer's own
  `_verify_snapshot` runs the stored WorkSpec back through the U-W1
  acceptance gate on every command (U-W2 §9, restated at §7.3 here).
- **The command document is untrusted cross-boundary input.** It is
  canonically round-tripped on intake, and the store's own pre-lock
  extraction reads only four fields, each checked, before the
  reducer performs the authoritative verification (§10.2).
- **Refusals are closed, bounded, value-free one-liners.** They carry a
  code from the frozen 43-member vocabulary, a schema-safe path or an
  already-validated identifier, and a fixed hint. No column value, stored
  document excerpt, SQL text, or exception string ever enters a message
  (§18.5).
- **No raw exception crosses the public boundary.** `sqlite3.Error`,
  `protocols.ProtocolError`, and the shape errors a hostile row can
  provoke (`KeyError`, `TypeError`, `ValueError`, `AttributeError`) are
  caught at their exact call sites and re-expressed as a `StoreOutcome`,
  an integrity verdict, or one of the three `WorkflowStoreError` codes;
  `workspecs.WorkSpecError` is reached only through the reducer, which
  maps it (§8.4, §18.4).
- **Crash safety is transactional.** One accepted command is one
  `BEGIN IMMEDIATE` transaction: every row commits together or none does,
  at every enumerated crash point (§13).
- **Fail closed everywhere.** An unknown schema version, an unverifiable
  history, a snapshot that disagrees with its history, an unreadable
  document, a row hash that does not recompute — every one of them refuses
  or reports; nothing guesses, nothing auto-repairs, nothing rewrites.
- **Worst case a hostile writer can achieve.** With direct SQL access to
  `aos.db` an attacker can already do anything; the store's guarantee is
  narrower and exact: no tampered row can make the store ACCEPT a command
  it would otherwise refuse, because every gate re-derives from bytes the
  same row supplies and the reducer re-runs the full admission gate on the
  stored artifact. A tampered row can only move a workflow from `ok` to a
  reported integrity failure, which freezes its mutations (§15.3).

## 4. Slice identity and dependency (D-v0.4.83)

### 4.1 U-W2.1 is landed and supplies the pure reducer

Proven mechanically at this baseline:

- `git log` shows `aedbc49 feat(v0.4): add deterministic workflow state
  engine`, merged as `63de8c9` (PR #20), tagged
  `milestone/v0.4-u-w2-workflow-state-engine` (`git rev-parse
  'milestone/v0.4-u-w2-workflow-state-engine^{}'` = the baseline commit).
- That commit added exactly the U-W2 §18 slice-1 paths:
  `agentic_os/workflow_engine.py` (2265 lines, new),
  `agentic_os/workspecs.py` (+20, the two public acceptance wrappers),
  `tests/test_v04_workflow_engine.py` (4921 lines, new), plus the two
  Wave-0 documents (`DECISIONS.md` +407,
  `agentic-os-v0.4-u-w2-workflow-state-engine-contract.md` 1648 lines).
- The public reducer surface exists and is closed: `decide(snapshot,
  command, facts) -> WorkflowDecision`, `fold(events) -> dict`,
  `verify_history(events) -> WorkflowRefusal | None`, `AdmissionFacts`,
  `WorkflowDecision(snapshot_after, events, intent)`, `WorkflowRefusal`,
  and the frozen vocabularies (13 states, 9 commands, 17 events, 43
  refusal reasons, 9 receipt kinds, 2 intent kinds, the 13×13
  `TRANSITION_MATRIX`, `TRANSITION_POLICY_VERSION = 1`,
  `SUPPORTED_POLICY_VERSIONS = (1,)`).
- The reducer's own docstring names this slice's obligation: "U-W2.2
  therefore takes the `workflows` row id from
  `snapshot_after['workflow_id']` instead of allocating a sequence" and
  "`command_conflict`, `receipt_conflict`, and `workflow_unknown` need
  stored rows to detect, so the vocabulary declares them here and
  `workflow_store` (U-W2.2) raises them."

### 4.2 U-W2.2 owns only local persistence

The store's entire decision authority is the set of judgments that
**require stored rows** and therefore cannot live in a pure function:

1. does a workflow with this identity exist (`workflow_unknown`);
2. has this `command_id` been accepted before, and with this digest
   (`command_conflict`, replay);
3. has this `receipt_id` been stored before, and with this digest
   (`receipt_conflict`, replay);
4. does the task named by the artifact exist and is it open
   (`AdmissionFacts`);
5. does the stored projection agree with the stored history
   (`snapshot_divergence`);
6. did the compare-and-swap win.

Every other judgment — legality, revision arithmetic, document
verification, evidence, binding, ordering, identifier derivation — is
`decide`'s, and the store neither anticipates nor second-guesses it.

### 4.3 The other slices

| Slice | Owns | Repository |
| --- | --- | --- |
| U-W2.1 (landed) | pure reducer, vocabularies, matrix, record shapes, fold/verify | `agentic-os` |
| **U-W2.2 (this)** | schema v6, migration 5→6, `workflow_store.py`, `WF` prefix | `agentic-os` |
| U-W2.3 | `aos workflow` CLI group (13 leaves), `power.COMMAND_POLICY`, `README.md`, refusal journaling | `agentic-os` |
| U-W2.R | intent/receipt file adapter onto the private Postgres queue | `ai-company-runtime` (private) |
| U-W3 | retry loops, checkpoints, resume, compensation, transition policy v2 | later unit |

### 4.4 The databases are never shared

`workflow_store` never calls `sqlite3.connect`, `db.connect`, `db.open_db`,
`db.init_db`, or `pathlib` anything. It receives an open `aos.db`
connection and issues SQL against exactly nine tables: the six frozen
workflow tables (read/write), `tasks` (read only — `id` is the lookup key,
`status` the selected value), `meta` (read only, one row), and `events`
(write only, through `events.emit`). It opens no second database, reads no
environment variable, and knows nothing of Postgres, DSNs, or the
runtime's schema. Pinned by §20 rows S21 and S22.

## 5. Schema version 6 (D-v0.4.84)

`db.SCHEMA_VERSION` becomes `"6"`. `migrations.LATEST_VERSION` follows
automatically (it is `int(db.SCHEMA_VERSION)`; the one-declaration rule is
preserved, not duplicated).

The landed U-W2 §14.1 proposed six tables under exactly these names. They
are verified frozen and implementable, with one column-level resolution
recorded as D-v0.4.85 and detailed in §7.2: the seven `aos.workflow-
snapshot/v1` fields U-W2 §14.1 gives no column to
(`admission_approval_satisfied`, `intent_seq`, `revoked_intent_ids`,
`resolved_intent_ids`, `last_seq`, `last_wait_entry_seq`,
`last_runtime_approval_seq`) are NOT added as columns; they are rebuilt by
`fold(events)`, which is exactly what U-W2 §14.2 already declares the
`workflows` row to be. No column is added to, or removed from, the landed
enumeration.

New `db.py` constants, in this order:

```text
WORKFLOWS_DDL, WORKFLOW_EVENTS_DDL, WORKFLOW_COMMANDS_DDL,
WORKFLOW_INTENTS_DDL, WORKFLOW_RECEIPTS_DDL, WORKFLOW_FACTS_DDL
WORKFLOWS_TABLE = "workflows"
WORKFLOW_EVENTS_TABLE = "workflow_events"
WORKFLOW_COMMANDS_TABLE = "workflow_commands"
WORKFLOW_INTENTS_TABLE = "workflow_intents"
WORKFLOW_RECEIPTS_TABLE = "workflow_receipts"
WORKFLOW_FACTS_TABLE = "workflow_facts"
WORKFLOW_TABLES: tuple[tuple[str, str], ...]   # FK-parent-first
```

`WORKFLOW_TABLES` pairs each table name with its DDL in FK-parent-first
order — `workflows`, `workflow_events`, `workflow_commands`,
`workflow_intents`, `workflow_receipts`, `workflow_facts` — and is the ONLY
enumeration: `SCHEMA_SQL` composition, the 5 → 6 migration step, and the
three historical fixtures all iterate it, so a seventh table cannot be
added in one place and forgotten in the others (the `MEMORY_GRAPH_TABLES`
/ `ROUTING_HANDOFF_TABLES` rule, applied a third time). `SCHEMA_SQL` gains
`";\n\n".join(ddl.format(table=table) for table, ddl in WORKFLOW_TABLES)`
followed by `";\n"`, appended after the U-A3 block.

### 5.1 `workflows` — the derived snapshot projection

```sql
CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL,
  work_spec_sha256 TEXT NOT NULL UNIQUE,
  report_sha256 TEXT NOT NULL,
  snapshot_sha256 TEXT NOT NULL,
  registry_version INTEGER NOT NULL CHECK (registry_version >= 1),
  compile_status TEXT NOT NULL
    CHECK (compile_status IN ('valid','warning','requires_external_authority')),
  work_spec_document TEXT NOT NULL,
  report_document TEXT NOT NULL,
  state TEXT NOT NULL
    CHECK (state IN ('compiled','validated','awaiting_approval','scheduled',
                     'running','waiting_input','waiting_approval','paused',
                     'compensating','succeeded','failed','cancelled',
                     'compensated')),
  revision INTEGER NOT NULL CHECK (revision >= 1),
  policy_version INTEGER NOT NULL CHECK (policy_version >= 1),
  approval_required INTEGER NOT NULL CHECK (approval_required IN (0,1)),
  dispatch_intent_id TEXT,
  cancel_intent_id TEXT,
  runtime_task_uuid TEXT,
  queue_route TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  CHECK (dispatch_intent_id IS NULL OR state = 'validated'),
  CHECK (cancel_intent_id IS NULL OR state IN
         ('scheduled','running','waiting_input','waiting_approval','paused')),
  CHECK (runtime_task_uuid IS NULL
      OR state NOT IN ('compiled','validated','awaiting_approval')),
  FOREIGN KEY(task_id) REFERENCES tasks(id)
)
```

- **`id`** is the integer of the reducer's derived `WF-<n>` identity, not a
  sequence: `workflow_engine._workflow_identity(work_spec_sha256)` renders
  `f"WF-{number or 1}"` where `number` is the first eight bytes of a
  domain-separated digest shifted right by one, so it always lies in
  `[1, 2**63-1]` = `ids.MAX_ID` and always fits a SQLite INTEGER. The
  store takes it from `decision.snapshot_after["workflow_id"]` and
  converts with `ids.parse_id(text, "workflow")`.
  **The store never calls `ids.render_id` for a workflow**: `render_id`
  zero-pads to width 4 and would produce `WF-0007` where the engine minted
  `WF-7`, breaking every event digest. The store's own renderer is
  `"WF-" + str(id)`, pinned byte-equal to the engine's derivation by §20
  row S3. `ids.PREFIXES["workflow"] = "WF"` exists so `ids.parse_id`
  accepts a human-typed identity at the U-W2.3 CLI, and for no other
  reason.
- **Source-of-truth role:** DERIVED. Every column except the two document
  bodies and the two row timestamps is reproducible from
  `fold(workflow_events)`; the bodies are admission-time immutables
  re-verified against the digests the `workflow_admitted` event recorded.
- **Immutable after admission:** `id`, `task_id`, `work_spec_sha256`,
  `report_sha256`, `snapshot_sha256`, `registry_version`,
  `compile_status`, `work_spec_document`, `report_document`,
  `approval_required`, `created_at`.
- **Mutable, only together, only inside one accepted command's
  transaction:** `state`, `revision`, `policy_version`, `dispatch_intent_id`,
  `cancel_intent_id`, `runtime_task_uuid`, `queue_route`, `updated_at`,
  `content_sha256`. Eleven immutable plus nine mutable classifies all
  twenty columns. `policy_version` is constant under transition policy v1:
  C14 writes it with the sealed snapshot's value so the projection always
  mirrors the snapshot, and U-W2 §14.1's mutable list — which enumerates
  the columns whose VALUES change under policy v1 — is not contradicted.
- **`content_sha256` is the SNAPSHOT RECORD digest**, not a row hash —
  U-W2 §9 says so in terms ("this IS `workflows.content_sha256`"). It is
  written verbatim from `decision.snapshot_after[content_sha256]` and is
  the agreement gate of §7.2 step 6.
- **`revision` is the CAS column.** No default; a row without it is
  unrepresentable.
- **Retention:** permanent. No `DELETE` path exists for any workflow row
  in this slice or any other.
- **Indexes:** none explicit. `id` is the PK (rowid alias) and
  `work_spec_sha256` carries the implicit UNIQUE index; those are the only
  two lookup keys the store uses. `list_workflows` is a declared full scan
  (§8.3), the U-A3 D-v0.4.28 precedent.

### 5.2 `workflow_events` — the authoritative append-only history

```sql
CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  workflow_id INTEGER NOT NULL,
  seq INTEGER NOT NULL CHECK (seq >= 1),
  event TEXT NOT NULL
    CHECK (event IN ('workflow_admitted','workflow_validated',
                     'approval_requested','approval_recorded',
                     'dispatch_requested','dispatch_rejected',
                     'dispatch_revoked','dispatch_accepted','run_started',
                     'run_waiting_input','run_waiting_approval','run_paused',
                     'run_resumed','cancel_requested','workflow_succeeded',
                     'workflow_failed','workflow_cancelled')),
  from_state TEXT
    CHECK (from_state IS NULL OR from_state IN
           ('compiled','validated','awaiting_approval','scheduled','running',
            'waiting_input','waiting_approval','paused','compensating',
            'succeeded','failed','cancelled','compensated')),
  to_state TEXT
    CHECK (to_state IS NULL OR to_state IN
           ('compiled','validated','awaiting_approval','scheduled','running',
            'waiting_input','waiting_approval','paused','compensating',
            'succeeded','failed','cancelled','compensated')),
  revision INTEGER NOT NULL CHECK (revision >= 1),
  policy_version INTEGER NOT NULL CHECK (policy_version >= 1),
  command_id TEXT NOT NULL,
  command_sha256 TEXT NOT NULL,
  actor TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  UNIQUE(workflow_id, seq),
  CHECK (from_state IS NULL OR to_state IS NULL OR from_state <> to_state),
  CHECK ((event = 'workflow_admitted') = (from_state IS NULL)),
  FOREIGN KEY(workflow_id) REFERENCES workflows(id)
)
```

- **Source-of-truth role:** AUTHORITATIVE. This table plus the two
  verbatim bodies in `workflows` and the documents in `workflow_facts` are
  the ledger's workflow truth; everything else is derived or auxiliary.
- **Immutable in full.** No code path in this slice or any other issues
  `UPDATE` or `DELETE` against this table (the
  `agent_handoff_transitions` discipline). `id` is insertion order,
  `(workflow_id, seq)` is the domain order, and `ORDER BY seq` is the
  canonical read.
- **`payload_json`** stores `protocols.serialize_canonical(event["payload"])
  .decode("utf-8")` — canonical bytes, so the read round-trips
  byte-identically and the digest recomputes.
- **`content_sha256` is the EVENT RECORD digest** the reducer sealed, not
  a row hash. Recomputed on every read; a mismatch is `history_corrupt`.
- **The two biconditional CHECKs** close two U-W2 §7 rules storage-side:
  `from_state` is null exactly on `workflow_admitted` (the creation
  pseudo-edge), and no event may claim a self-edge. The second is written
  with explicit NULL guards; under SQLite's NULL-CHECK rule the guards are
  redundant, and they are written anyway so the intent is readable rather
  than inferred.
- **The `event` CHECK makes `history_unknown_event` unreachable through
  storage.** That is deliberate: the code stays in the vocabulary because
  `verify_history` is also callable on a caller-supplied list (the engine
  tests exercise it there), and the store instead proves the CHECK rejects
  an unknown name (§20 row S15). This contract does not pretend to test a
  store-side path that cannot exist.
- **Retention:** permanent, and required to be. Deleting one event breaks
  `fold`, which is the only way the seven derived snapshot fields exist at
  all (§7.2).
- **Indexes:** none explicit; `UNIQUE(workflow_id, seq)` carries the
  implicit index that serves the only read (`WHERE workflow_id = ? ORDER
  BY seq`).

### 5.3 `workflow_commands` — accepted-command dedupe and replay

```sql
CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  workflow_id INTEGER NOT NULL,
  command_id TEXT NOT NULL UNIQUE,
  command TEXT NOT NULL
    CHECK (command IN ('admit_work_spec','validate','request_approval',
                       'record_approval','request_dispatch','revoke_dispatch',
                       'request_cancel','record_queue_receipt','record_result')),
  command_sha256 TEXT NOT NULL,
  expected_revision INTEGER NOT NULL CHECK (expected_revision >= 0),
  resulting_revision INTEGER NOT NULL CHECK (resulting_revision >= 1),
  event_seq_first INTEGER NOT NULL CHECK (event_seq_first >= 1),
  event_seq_last INTEGER NOT NULL CHECK (event_seq_last >= event_seq_first),
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  CHECK (resulting_revision = expected_revision + 1),
  CHECK ((command = 'admit_work_spec') = (expected_revision = 0)),
  FOREIGN KEY(workflow_id) REFERENCES workflows(id)
)
```

- **Source-of-truth role:** the dedupe index over accepted commands, and
  the `[event_seq_first, event_seq_last]` range that lets a replay return
  the original events without calling `decide` (U-W2 §10).
- **Accepted commands only.** A refused command stores nothing here or
  anywhere else (§9.4). The NOT NULL `event_seq_*` pair makes a
  zero-event command row unrepresentable, which is the storage-side proof
  of "every accepted command appends at least one event".
- **`CHECK (resulting_revision = expected_revision + 1)`** is U-W2 §10's
  "+1 per accepted command", closed storage-side for every verb including
  the stateless ones. **`CHECK ((command='admit_work_spec') =
  (expected_revision = 0))`** is the creation rule: admission asserts 0,
  and a non-admit command carrying 0 can never be accepted because
  `revision` starts at 1 and only grows.
- **`command_sha256`** is the RECOMPUTED canonical digest of the command
  record (`protocols.content_digest`), never the value the envelope
  declared.
- **Immutable after its creating transaction commits**: the §5.8 hash
  finalization is the sole in-transaction `UPDATE`; thereafter no
  `UPDATE`, no `DELETE`, ever.
- **Retention:** permanent, and required to be. Deleting a row would make
  a redelivered duplicate re-apply, destroying the end-to-end idempotence
  U-W2 §10 promises.
- **`content_sha256`** is the row hash of §5.8.
- **Indexes:** none explicit; `command_id UNIQUE` carries the dedupe
  index. `workflow_id` is read only through the range lookup that already
  has the `command_id`, so no second index is needed.

### 5.4 `workflow_intents` — the outbox

```sql
CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  workflow_id INTEGER NOT NULL,
  intent_id TEXT NOT NULL UNIQUE,
  intent_kind TEXT NOT NULL CHECK (intent_kind IN ('dispatch','cancel')),
  idempotency_key TEXT NOT NULL,
  queue_route TEXT NOT NULL,
  document TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('outstanding','resolved','revoked')),
  resolved_receipt_id TEXT,
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  CHECK ((status = 'resolved') = (resolved_receipt_id IS NOT NULL)),
  FOREIGN KEY(workflow_id) REFERENCES workflows(id)
)
```

- **Source-of-truth role:** the record of what AOS asked the queue for.
  `workflows.dispatch_intent_id` / `cancel_intent_id` are pending POINTERS
  (a fast path); this table is the record, and every intent ever emitted
  stays here with its status.
- **`document`** is the canonical `aos.workflow-queue-intent/v1` record
  verbatim (`serialize_canonical(...).decode("utf-8")`); `intent_id`,
  `intent_kind`, `idempotency_key`, `queue_route` are projections of it,
  cross-checked on read.
- **Mutable columns:** `status`, `resolved_receipt_id`, `content_sha256`,
  and only together, only inside an accepted command's transaction, only
  from `outstanding` (the `_resolve_intent` guard of §10.5 requires
  `WHERE intent_id = ? AND status = 'outstanding'` and rowcount 1, so a
  second close is impossible and no reverse transition exists).
- **The biconditional CHECK** pins that `resolved` means "a receipt closed
  it": every `resolved` transition is driven by `dispatch_accepted`,
  `dispatch_rejected`, or `workflow_cancelled` with an `intent_id`, and
  all three carry `receipt_id` in their event payload. `revoked` means
  `dispatch_revoked` withdrew it and no receipt will ever come.
- **Retention:** permanent. A resolved or revoked intent is the audit
  record of a dispatch decision; pruning one would erase the only local
  evidence of what was asked of the queue.
- **Indexes:** none explicit; `intent_id UNIQUE` carries the lookup index.
  `list_outstanding_intents` is a declared full scan filtered on `status`,
  ordered by `id` (§16.2).

### 5.5 `workflow_receipts` — the inbox

```sql
CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  workflow_id INTEGER NOT NULL,
  receipt_id TEXT NOT NULL UNIQUE,
  receipt_kind TEXT NOT NULL
    CHECK (receipt_kind IN ('accepted','rejected','started','waiting_input',
                            'waiting_approval','paused','resumed','cancelled',
                            'failed')),
  intent_id TEXT,
  runtime_task_uuid TEXT,
  document TEXT NOT NULL,
  receipt_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  CHECK (intent_id IS NOT NULL
      OR receipt_kind NOT IN ('accepted','rejected')),
  CHECK (intent_id IS NULL
      OR receipt_kind IN ('accepted','rejected','cancelled')),
  CHECK (runtime_task_uuid IS NOT NULL
      OR receipt_kind NOT IN ('accepted','started','waiting_input',
                              'waiting_approval','paused','resumed')),
  CHECK (runtime_task_uuid IS NULL OR receipt_kind <> 'rejected'),
  FOREIGN KEY(workflow_id) REFERENCES workflows(id)
)
```

- **Source-of-truth role:** the verbatim record of what the runtime
  reported, so even a runtime that misreports is auditable.
- **Insert-once: a stored receipt IS an applied receipt.** A refused
  receipt stores nothing, so presence in this table means "this receipt
  drove an accepted command". That is what makes the receipt dedupe axis
  of §14.3 sound.
- **The four CHECKs mirror `workflow_engine._RECEIPT_INTENT_REQUIRED`,
  `_RECEIPT_INTENT_ALLOWED`, `_RECEIPT_UUID_REQUIRED`, and
  `_RECEIPT_UUID_FORBIDDEN` exactly**, so the storage boundary and the
  reducer's closed vocabulary cannot disagree (the `MEMORY_STATUSES`
  domain-plus-storage rule). §20 row S6 data-compares the CHECK membership
  against those engine tuples.
- **`receipt_sha256`** is the RECOMPUTED canonical digest of the receipt
  document — the conflict discriminator of §14.3, never read from the
  document's own `content_sha256` member.
- **Immutable after its creating transaction commits**: the §5.8 hash
  finalization is the sole in-transaction `UPDATE`; thereafter no
  `UPDATE`, no `DELETE`, ever.
- **Retention:** permanent, and required to be. Deleting a row would let a
  redelivered receipt apply a second time, which is exactly the
  at-least-once hazard the inbox exists to close.
- **`content_sha256`** is the row hash of §5.8.
- **Indexes:** none explicit; `receipt_id UNIQUE` carries the dedupe
  index.

### 5.6 `workflow_facts` — verbatim external facts

```sql
CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  workflow_id INTEGER NOT NULL,
  fact_kind TEXT NOT NULL CHECK (fact_kind IN ('approval','result')),
  fact_scope TEXT
    CHECK (fact_scope IS NULL OR fact_scope IN ('admission','runtime')),
  document TEXT NOT NULL,
  document_sha256 TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  UNIQUE(workflow_id, fact_kind, document_sha256),
  CHECK ((fact_kind = 'approval') = (fact_scope IS NOT NULL)),
  FOREIGN KEY(workflow_id) REFERENCES workflows(id)
)
```

- **Source-of-truth role:** the verbatim `aos.workflow-approval-fact/v1`
  and `beast.result-envelope/v1` documents behind an `approval_recorded`,
  `workflow_succeeded`, or `workflow_failed` event. The EVENT is the
  authoritative fact that it happened; this table holds the body the event
  records only by digest.
- **Identity** is `(workflow_id, fact_kind, document_sha256)`; the
  `document_sha256` is recomputed from the stored bytes.
- **Duplicate behavior:** an exact duplicate is a no-op — the insert is
  `ON CONFLICT(workflow_id, fact_kind, document_sha256) DO NOTHING`, while
  the command that carried it still appends its event and consumes its
  revision. That is U-W2 §12.1's "an exact duplicate fact replays as a
  no-op" read exactly: the history records that it was recorded twice, the
  fact table holds one body.
- **Immutable after its creating transaction commits**: the §5.8 hash
  finalization is the sole in-transaction `UPDATE`; thereafter no
  `UPDATE`, no `DELETE`, ever.
- **Retention:** permanent, and required to be. A `succeeded` workflow's
  claim rests on the stored envelope; deleting it would leave a success
  with no recoverable proof.
- **`content_sha256`** is the row hash of §5.8.
- **Indexes:** none explicit; the composite UNIQUE carries the only index
  the insert and the duplicate check need.

### 5.7 `ids.py`

`PREFIXES` gains `"workflow": "WF"`, and the module docstring gains a
workflows clause documenting the unpadded `WF-<n>` identity — the store's
renderer; `parse_id` accepts padded and unpadded digits, and `render_id`
is never used for workflows (§5.1). Two letters, following the U-M3/U-A3
precedent; `WF` collides with nothing (`W` is unused). Nothing else in
`ids.py` changes. §20 row S3 pins that no two entities share a prefix and
that the store's renderer is NOT `render_id`.

### 5.8 Row hashes (D-v0.4.86)

`workflows.content_sha256` and `workflow_events.content_sha256` are the
CANONICAL RECORD digests U-W2 §9 and §7 already assign them: those two
rows ARE records (`aos.workflow-snapshot/v1`, `aos.workflow-event/v1`), so
a second, competing integrity claim over the same bytes would be a defect,
not a defence.

The four remaining tables carry ordinary ROW hashes in the live U-A3
idiom (`agent_handoffs.handoff_payload` / `transition_payload`): a
`record_schema` key, text fields bound by their `sha256` leaf, integers
bound directly, `None` passed through, `content_sha256` excluded, digested
with `sha256(protocols.serialize_canonical(payload)).hexdigest()`. The
four payload identities are new `record_schema` names in the `aos.*` house
style; they are NOT new document schemas and do NOT touch U-W2 §13.4's
six minted record schemas or the U-X1 registry.

| Table | `record_schema` | Bound members (in addition to `record_schema`) |
| --- | --- | --- |
| `workflow_commands` | `aos.workflow-command-row/v1` | `id`, `workflow_id`, `expected_revision`, `resulting_revision`, `event_seq_first`, `event_seq_last` (ints); `command_id_sha256`, `command_sha256_sha256`, `command_sha256` *(the verb string's leaf)*, `created_at_sha256` |
| `workflow_intents` | `aos.workflow-intent-row/v1` | `id`, `workflow_id` (ints); `intent_id_sha256`, `intent_kind_sha256`, `idempotency_key_sha256`, `queue_route_sha256`, `document_sha256` *(recomputed digest of the stored document)*, `status_sha256`, `resolved_receipt_id_sha256` (nullable), `created_at_sha256` |
| `workflow_receipts` | `aos.workflow-receipt-row/v1` | `id`, `workflow_id` (ints); `receipt_id_sha256`, `receipt_kind_sha256`, `intent_id_sha256` (nullable), `runtime_task_uuid_sha256` (nullable), `receipt_sha256_sha256`, `created_at_sha256` |
| `workflow_facts` | `aos.workflow-fact-row/v1` | `id`, `workflow_id` (ints); `fact_kind_sha256`, `fact_scope_sha256` (nullable), `document_sha256_sha256`, `recorded_at_sha256` |

To avoid the one collision the leaf convention can produce, the verb
column of `workflow_commands` is bound as `command_sha256` and the
envelope digest column as `command_sha256_sha256`; the names are frozen
exactly as written above.

Because `id` is bound, the row hash is finalized by a second `UPDATE` of
`content_sha256` inside the same transaction, immediately after the
`INSERT` that assigns the rowid — the `routing_plans` post-commit-immutable
idiom ("the only UPDATE it ever receives is the hash finalization inside
its own creating transaction, between INSERT and COMMIT"). That single
finalization is the sole in-transaction `UPDATE` that `workflow_commands`,
`workflow_receipts`, and `workflow_facts` ever receive, and it is why
those three sections state their immutability as "after its creating
transaction commits" (§5.3, §5.5, §5.6).

`verify` recomputes all four row hashes and reports disagreements without
touching a row (§15.4).

### 5.9 Record schemas

No new document schema is minted. The store reads and writes exactly the
six U-W2 §13.4 identities — `aos.workflow-command/v1`,
`aos.workflow-event/v1`, `aos.workflow-snapshot/v1`,
`aos.workflow-queue-intent/v1`, `aos.workflow-queue-receipt/v1`,
`aos.workflow-approval-fact/v1` — plus `beast.result-envelope/v1` as an
opaque stored fact body. The six `aos.*` identity strings are read from
`workflow_engine` constants, never typed as literals in
`workflow_store.py`; `beast.result-envelope/v1` is stored without the
store ever naming its identity (the reducer verifies it — §16.1 — and the
live tree carries no named constant for it). The four §5.8 row-hash
`record_schema` identities are NOT document schemas: they are the store's
own module-level frozen constants, exactly as the live row-hash
precedents define theirs (`routing.py`, `agent_handoffs.py`). Pinned by
§20 row S24.

## 6. Migration 5 → 6

```text
migration_id : "u-w2-workflow-state-v6"
from_version : 5
to_version   : 6
apply        : migrations._workflow_state_v6
registered   : MIGRATIONS = (..., ROUTING_HANDOFFS_V5, WORKFLOW_STATE_V6)
```

```python
def _workflow_state_v6(conn: sqlite3.Connection) -> None:
    for table, ddl in db.WORKFLOW_TABLES:
        conn.execute(ddl.format(table=table))
```

- **Purely additive.** Six empty tables. No existing table is read,
  rebuilt, renamed, re-stamped, or copied; no row is carried, parsed, or
  invented; NO CLOCK IS READ, because no row is stamped.
- **No fabricated history.** There are no legacy workflow facts anywhere
  in the ledger — `workflow_store` does not exist yet and no table models a
  workflow — so the step has nothing to derive from and derives nothing. A
  pre-existing task or run gets no workflow, no admission event, and no
  synthetic snapshot. A workflow exists only because a human ran
  `admit_work_spec` against a real WorkSpec artifact after this migration.
- **Built from the same `db.py` constants a fresh v6 init uses**, created
  directly under their real names in FK-parent-first order, so there is no
  `ALTER TABLE RENAME` quoting artifact and a migrated schema is
  BYTE-identical to a fresh one for the six new tables.
- **The 3 → 4 / 4 → 5 freeze obligation is NOT triggered.** This slice
  edits none of the constants a shipped step builds from
  (`db.MEMORY_CLAIM_DDL`, `db.MEMORY_GRAPH_TABLES`, `db.AGENTS_DDL`,
  `db.AGENT_PASSPORTS_DDL`, `db.ROUTING_HANDOFF_TABLES`,
  `passports.agent_identity_payload`), so no historical DDL needs freezing
  and D-v0.4.29's transfer clause does not fire. A future unit that edits
  `db.WORKFLOW_TABLES` inherits the obligation to freeze a
  `_V6_WORKFLOW_*` copy in `migrations.py`, exactly as
  `_V2_MEMORY_CLAIM_DDL` did.
- **All existing U-M1 guarantees apply unchanged:** validate, lock
  (`BEGIN IMMEDIATE`), re-read under lock, backup-first snapshot from a
  second reader connection, verify at the starting version, then mutate;
  per-step whole-database `foreign_key_check`; one `events.emit` journal
  row per step; `meta.schema_version` owned by `apply_migrations` alone.
  Six empty tables contribute zero foreign-key violations.
- **Fixture consequence (mandatory).** The three historical fixtures build
  a CURRENT-schema database and then drop every table newer than their
  target version. Each gains one loop, placed FIRST (newest layer first),
  before the existing `ROUTING_HANDOFF_TABLES` loop:

  ```python
  for table, _ddl in reversed(db.WORKFLOW_TABLES):
      conn.execute(f"DROP TABLE {table}")
  ```

  `reversed` is children-before-parent, so `workflows` drops last.
  Without this, a "v1"/"v2"/"v3" workspace would carry v6 tables and the
  5 → 6 step's `CREATE TABLE` would fail on an existing table when the
  fixture was migrated forward — precisely the failure U-A3 pre-empted in
  commit `7c5fea4`. `FIXTURE_TABLES` is NOT extended: it enumerates the
  tables whose CONTENTS a migration test compares before and after, and
  the six new tables do not exist before.
- **Equivalence test reuses `build_v3_workspace`** and migrates v3 → v6 in
  one `apply_migrations` call; no new fixture module is added, exactly as
  U-A3 added none.
- **Version gate:** `db._check_schema_version` is untouched and refuses a
  v5 database in every normal command with the standard three-command
  message. `workflow_store` additionally re-checks
  `meta.schema_version == db.SCHEMA_VERSION` on entry to every public
  function, because it accepts a caller-supplied connection and must not
  assume it came through `db.open_db` (§8.4).

## 7. Store authority and invariants

### 7.1 What is authoritative

| Fact | Authoritative row | Derived / auxiliary |
| --- | --- | --- |
| That a transition happened | `workflow_events` | `workflows.state` |
| The revision counter | `workflow_events.revision` (last row) | `workflows.revision` |
| The admitted WorkSpec and report bodies | `workflows.work_spec_document` / `report_document` (admission-time immutables, digest-bound to `workflow_admitted`) | — |
| That a command was accepted | `workflow_commands` | — |
| What was asked of the queue | `workflow_intents.document` | `workflows.dispatch_intent_id` / `cancel_intent_id` |
| What the runtime reported | `workflow_receipts.document` | `workflows.runtime_task_uuid` |
| The approval and result bodies | `workflow_facts.document` | event payload digests |
| Lifecycle state, admission, approvals, success judgment | this ledger | — |
| Queue membership, leases, workers, attempts, `runtime_task_uuid` namespace | the private runtime | — |

### 7.2 The snapshot is rebuilt, not stored (D-v0.4.85)

`workflow_engine.decide` requires a complete, sealed
`aos.workflow-snapshot/v1` record with 26 members. The frozen `workflows`
column list supplies eighteen of them, and the nineteenth — `schema` — is
the frozen record-identity constant, carried by no column; seven —
`admission_approval_satisfied`, `intent_seq`, `revoked_intent_ids`,
`resolved_intent_ids`, `last_seq`, `last_wait_entry_seq`,
`last_runtime_approval_seq` — have no column, deliberately: U-W2 §14.2
already declares the row "a DERIVED snapshot: every §9 snapshot field
EXCEPT the two document bodies is rebuildable by `fold(events)`", and
U-W2 §14.1's mutable-column list names none of the seven.

So the store rebuilds. `_load_snapshot(conn, workflow_id)`:

1. `SELECT * FROM workflows WHERE id = ?` — absent → `workflow_unknown`.
2. `SELECT ... FROM workflow_events WHERE workflow_id = ? ORDER BY seq` and
   reconstitute each event record (§7.4).
3. `workflow_engine.fold(records)` — raises the closed refusal
   `verify_history` would return (`history_corrupt`,
   `history_unknown_event`, `policy_version_unsupported`,
   `snapshot_divergence`) on a damaged history; the store returns it as a
   `refused` outcome and writes nothing.
4. Splice the two verbatim bodies:
   `parse_canonical(row["work_spec_document"].encode("utf-8"))` and the
   same for the report, replacing the `None`s `fold` returns.
5. Seal: `record = parse_canonical(serialize_canonical(body without
   content_sha256))`, then `record["content_sha256"] =
   content_digest(record)` — the engine's `_seal` two-liner, re-implemented
   locally because `_seal` is private, and pinned by §20 row S2.
6. **Agreement gate.** The sealed digest must equal
   `workflows.content_sha256`, and every OTHER member-backed projection
   column — seventeen: `id` (as `workflow_id`), `task_id`,
   `work_spec_sha256`, `report_sha256`, `snapshot_sha256`,
   `registry_version`, `compile_status`, the two document bodies,
   `state`, `revision`, `policy_version`, `approval_required`,
   `dispatch_intent_id`, `cancel_intent_id`, `runtime_task_uuid`,
   `queue_route` — must equal its rebuilt counterpart under the declared
   conversions: `workflow_id` compares as `"WF-" + str(workflows.id)`
   (§5.1); `task_id` compares the snapshot's verbatim admitted string
   against the integer column via `ids.parse_id`; `approval_required`
   compares bool against 0/1; the two document bodies enter the rebuilt
   snapshot as the spliced verbatim texts of step 4 (their integrity is
   the separate digest re-verification of §15.4 step 5); every other
   column compares as its stored value. The two row timestamps
   (`created_at`, `updated_at`) have no snapshot counterpart and are
   outside this gate: `created_at` is admission-immutable and
   `updated_at` moves only with the C14 CAS. Any disagreement is
   `snapshot_divergence`, naming the field, and the command is refused.

Consequences, all of them wanted:

- The `workflows` row is exactly what U-W2 §14.1 calls it — a projection
  and a fast path — and never a second source of truth.
- Snapshot/history agreement is checked on EVERY command, not only at
  `verify`, so a tampered projection cannot survive one write.
- No column is added to the landed enumeration, so the frozen schema is
  implementable as written.
- Cost is one indexed range read of a short history per command; the
  reducer's own `_verify_snapshot`, which re-runs the U-W1 acceptance gate
  on the stored artifact, dominates it.
- `fold` is the only producer of the seven derived fields, which is why
  `workflow_events` retention is mandatory rather than merely preferred.

### 7.3 What the reducer re-checks anyway

The store passes the rebuilt snapshot to `decide`, which independently
re-verifies it: closed key set, every pattern, the three structural
CHECKs, both bodies re-digested, the stored artifact re-accepted through
`workspecs.accept_work_spec`, the identity re-derived from
`work_spec_sha256`, all five counters bounded against `protocols.INT_MAX`,
both intent collections bounded against `protocols.MAX_ARRAY_ITEMS`, the
pending pointers re-derived, and the record digest recomputed. The store's
agreement gate and the reducer's verification are independent and both
must pass; neither is trusted to cover the other.

### 7.4 Event reconstitution (D-v0.4.86)

`workflow_events` stores the record's fields as columns, not the record as
a document. The store rebuilds each `aos.workflow-event/v1` record as:

| Record member | Source |
| --- | --- |
| `schema` | `workflow_engine.WORKFLOW_EVENT_SCHEMA` (constant) |
| `workflow_id` | `"WF-" + str(workflows.id)` (§5.1) |
| `work_spec_sha256` | `workflows.work_spec_sha256` |
| `event`, `seq`, `revision`, `policy_version`, `from_state`, `to_state`, `command_id`, `command_sha256`, `actor`, `created_at` | the same-named columns |
| `payload` | `parse_canonical(payload_json.encode("utf-8"))` |
| `content_sha256` | the `content_sha256` column |

The sealed event digest is what proves the reconstitution faithful: it
covers `workflow_id` and `work_spec_sha256`, so a spliced `workflows.id`
or `work_spec_sha256` makes every event digest fail and the workflow reads
`history_corrupt` rather than silently folding under a false identity. A
column whose stored value is not text where text is required, or whose
`payload_json` does not parse canonically, yields the same verdict; no
value is ever coerced, defaulted, or repaired.

### 7.5 One workflow per identity

Three independent gates agree by construction:

1. `_workflow_identity(work_spec_sha256)` is a pure function, so
   re-admitting the same artifact derives the same `WF-<n>`.
2. `workflows.id` is the primary key.
3. `workflows.work_spec_sha256` is UNIQUE.

The store additionally SELECTs by both keys under the write lock before
inserting, so `workflow_exists` is returned deterministically rather than
caught (§10.4). The UNIQUE INSERT remains the storage gate U-W2 §10 names,
and an `sqlite3.IntegrityError` raised by that ONE statement is mapped to
`workflow_exists` as the backstop.

### 7.6 No automatic repair — ever

Nothing in this slice writes to make a divergent workflow agree. `verify`
reports. `rebuild` returns a value. `submit` refuses. There is no
`--repair`, no `--force`, no re-seal, no re-stamp, and no code path that
updates `workflows.content_sha256` outside an accepted command's
transaction. Recovery is a human restoring a verified backup (RECOVERY.md,
the doctor rule).

## 8. Public API (D-v0.4.88)

`agentic_os/workflow_store.py` exports exactly the names below. U-W2.3 may
add no function here; needing one is a replan trigger, not a quiet
extension.

### 8.1 Vocabularies

```text
STORE_STATUSES  = ("accepted", "replay", "refused", "conflict")
STORE_INTEGRITY = ("ok", "history_corrupt", "history_unknown_event",
                   "policy_version_unsupported", "snapshot_divergence")
STORE_ERROR_CODES = ("store_schema_unsupported", "store_argument_invalid",
                     "store_unavailable")
```

### 8.2 Types

```text
StoreOutcome     (frozen dataclass; §9)
WorkflowRecord   (frozen dataclass; the workflows projection + integrity)
HistoryView      (frozen dataclass; reconstituted events + integrity)
IntentView       (frozen dataclass; one outbox row, readable or not)
RebuildResult    (frozen dataclass; the rebuilt snapshot or the refusal)
VerifyReport     (frozen dataclass; one workflow's integrity comparison)
WorkflowStoreError(AosError)   (three closed infrastructure codes)
```

```text
WorkflowRecord(
    workflow_id: str,          # "WF-<n>"
    id: int, task_id: int,     # ledger row ids
    state: str, revision: int, policy_version: int,
    compile_status: str, approval_required: bool,
    work_spec_sha256: str, report_sha256: str, snapshot_sha256: str,
    registry_version: int,
    dispatch_intent_id: str | None, cancel_intent_id: str | None,
    runtime_task_uuid: str | None, queue_route: str | None,
    created_at: str, updated_at: str, content_sha256: str,
    integrity: str,            # STORE_INTEGRITY member
)

HistoryView(workflow_id: str, events: tuple, integrity: str,
            unreadable_seq: int | None)

IntentView(workflow_id: str, intent_id: str, intent_kind: str,
           idempotency_key: str, queue_route: str, status: str,
           resolved_receipt_id: str | None, created_at: str,
           document: dict | None, content_sha256: str, readable: bool)

RebuildResult(workflow_id: str, snapshot: dict | None, integrity: str,
              reason: str | None, where: str | None)

VerifyReport(workflow_id: str, integrity: str,
             reason: str | None, where: str | None,
             stored_content_sha256: str,
             rebuilt_content_sha256: str | None,
             divergent_fields: tuple, divergent_rows: tuple,
             last_seq: int | None, revision: int | None)
```

`WorkflowRecord.task_id` is the INTEGER ledger row id, never a rendered
`T-<n>` string: the artifact's `aos_task_id` is stored verbatim inside the
snapshot and the `workflow_admitted` payload, and `T-7` and `T-0007` are
both pattern-valid, so re-rendering from the integer would state a
different string than the one that was admitted. `VerifyReport.
divergent_rows` is a tuple of `(table_name, row_id)` pairs whose §5.8 row
hash does not recompute.

### 8.3 Functions

| Function | Returns | Behavior |
| --- | --- | --- |
| `submit(conn, command_document) -> StoreOutcome` | a `StoreOutcome` for every workflow-level outcome | The whole command transaction (§10). Never raises `WorkflowRefusal`; raises only `WorkflowStoreError` (§8.4) for the three infrastructure codes. |
| `read_workflow(conn, workflow_id) -> WorkflowRecord \| None` | `None` iff no such row | The projection plus an integrity verdict. Total on a damaged workflow. |
| `list_workflows(conn, *, state=None) -> tuple[WorkflowRecord, ...]` | possibly empty | Full scan ordered by `id` ASC. `state` must be `None` or a `WORKFLOW_STATES` member. |
| `read_history(conn, workflow_id) -> HistoryView` | empty `events` with `integrity == "ok"` iff no such workflow | Reconstituted records in `seq` order, plus the integrity verdict and the first unreadable `seq`. A nonexistent workflow returns `(events=(), integrity="ok", unreadable_seq=None)`; an existing workflow with zero stored event rows reports `history_corrupt` (the engine refuses an empty history), keeping the pair unambiguous and total. |
| `list_outstanding_intents(conn, *, workflow_id=None) -> tuple[IntentView, ...]` | possibly empty | `status = 'outstanding'`, ordered by `id` ASC (emission order). Never silently drops an unreadable row. |
| `rebuild(conn, workflow_id) -> RebuildResult` | `snapshot` non-`None` iff `integrity == "ok"` | `fold` + splice + seal, without comparing against the projection. |
| `verify(conn, workflow_id=None) -> tuple[VerifyReport, ...]` | one report per workflow | Rebuild, compare against the projection and the four row hashes, report. Writes nothing, ever. |

`workflow_id` arguments are the `WF-<n>` string; a value that
`ids.parse_id(..., "workflow")` rejects raises
`WorkflowStoreError("store_argument_invalid")` before any query.

### 8.4 `WorkflowStoreError`

Three closed codes, and they are infrastructure facts about the ledger,
never facts about a workflow — which is why none of them enters the frozen
43-member workflow refusal vocabulary:

| Code | Trigger |
| --- | --- |
| `store_schema_unsupported` | `meta.schema_version != db.SCHEMA_VERSION` on entry to any public function |
| `store_argument_invalid` | a `workflow_id` that is not a parseable `WF-<n>`, or a `state` filter outside `WORKFLOW_STATES` |
| `store_unavailable` | any `sqlite3.Error` the store did not deliberately map — a locked, missing, or damaged database file, an I/O failure, or a constraint violation outside the one mapped `workflows` INSERT — plus the one deliberate non-exception trigger: an intent-close CAS whose rowcount is not 1 (§12.2, a damaged outbox) |

It inherits `AosError`, so the CLI's single refusal choke point exits 1
with a bounded, value-free message. Its message names the code and a fixed
hint and never carries SQL text, a file path, a column value, or an
exception string.

### 8.5 Import discipline

`workflow_store.py` imports exactly: `re` (compiling
`protocols.UUID_PATTERN` and the `WF-<n>` pattern for the §10.2 P2 subset
— the engine's compiled patterns are private), `sqlite3` (for
`sqlite3.Error` and row access), `dataclasses`, `hashlib`, and from the
package `db`, `events`, `ids`, `models`, `protocols`, `workflow_engine`,
and `utils.AosError`. It imports NO `json` (`events.emit` serializes its
own payload — events.py hands `json.dumps` the dict itself), NEITHER
`datetime` NOR `time`, calls `utils.utc_now_iso` nowhere, and imports
`ops`, `cli`, `power`, `doctor`, `backup`, `governance`, and `workspecs`
nowhere. Pinned by §20 row S24 (an AST check over this module's own
import statements, the live `test_import_graph_is_closed` idiom).

## 9. `StoreOutcome` (D-v0.4.87)

### 9.1 The record

```text
@dataclass(frozen=True)
class StoreOutcome:
    status: str                  # STORE_STATUSES member
    replay: bool                 # == (status == "replay")
    workflow_id: str | None      # "WF-<n>"; None only when no identity exists
    command_id: str | None       # echo; None only when it could not be read
    revision: int | None         # see the table below
    events: tuple                # canonical event records; fresh copies
    intent: dict | None          # canonical intent record; fresh copy
    snapshot: dict | None        # the workflow's snapshot at end of call
    reason: str | None           # closed §8 code; None iff accepted/replay
    where: str | None            # schema-safe path; None iff reason is None
    diagnostics: dict            # bounded counts and closed codes; {} if none
    refusal: WorkflowRefusal | None   # the exact closed refusal object
```

### 9.2 Invariants

Each pinned by §20 row S8:

- `replay == (status == "replay")`.
- `reason is None` **iff** `status in ("accepted", "replay")`, and
  `reason == (refusal.reason if refusal else None)`. `refusal` is
  non-`None` on EVERY refused or conflicting outcome: for reducer-raised
  refusals it is the caught object, and for the store-originated codes —
  `command_malformed`/`command_unknown` at P2, `workflow_unknown`,
  `command_conflict`, `receipt_conflict`, and a CAS-detected
  `revision_mismatch` — the store CONSTRUCTS the same closed
  `workflow_engine.WorkflowRefusal` value (never raising it; the
  constructor enforces the closed vocabulary), so the invariant holds
  unqualified.
- `status == "conflict"` **iff**
  `reason in ("command_conflict", "receipt_conflict")`; every other
  refusal is `status == "refused"`. A conflict is the one refusal class
  caused by STORED state disagreeing with the delivered document, and it
  is never made legal by redelivery — which is why it is a distinct
  status a caller can branch on without string-matching.
- `intent is None` whenever `status != "accepted"`. An intent is delivered
  from the outbox, never from a command result; U-W2 §10 freezes this and
  `list_outstanding_intents` (U-W2.3's `export-intents`) is the sole
  retrieval path for a still-outstanding intent.
- `events == ()` whenever `status in ("refused", "conflict")`.
- Every returned structure is a FRESH canonical round trip. Mutating a
  returned record cannot alter a stored row, a later read, or another
  returned record; mutating the caller's input document after the call
  cannot alter what was stored (§20 row S19).

### 9.3 Per-status field meanings

| Field | `accepted` | `replay` (command) | `replay` (receipt) | `refused` / `conflict` |
| --- | --- | --- | --- | --- |
| `revision` | the resulting revision | the ORIGINAL `resulting_revision` from `workflow_commands` | the `revision` of the event that first applied this receipt | the CURRENT stored revision when the workflow exists, else `None` |
| `events` | the newly appended events, in `seq` order | the original events in `[event_seq_first, event_seq_last]` | the events of the command that first applied this receipt | `()` |
| `snapshot` | the snapshot the command produced | the CURRENT snapshot when the history verifies, else `None` | the CURRENT snapshot when the history verifies, else `None` | the CURRENT snapshot when the workflow exists and its history verifies, else `None` |

The `replay` row deliberately reports the original revision alongside the
current snapshot, and those two may disagree if the workflow advanced
after the original acceptance. That is the truthful pair — "this command
produced revision 4; the workflow is now at 7" — and it is stated here so
it is never discovered as a surprise.

### 9.4 Refusals persist nothing

A refused or conflicting `submit` writes NO row in any of the six tables
and NO row in `events`. The write lock is taken, every read is performed,
and the transaction is rolled back with nothing in it — or, on the paths
that refuse before any mutation, nothing was ever issued. U-W2 §8's "the
CLI shell journals refusals to the AOS `events` table for observability"
is U-W2.3's obligation, deliberately placed outside this transaction so a
journalled refusal cannot be rolled back with the work it declined.
Consequence, declared: until U-W2.3 ships, a refusal leaves no trace in
`aos.db` at all.

### 9.5 Where each of the forty-three reasons comes from

The vocabulary is the reducer's and U-W2.2 adds nothing to it. This
partition is what makes `StoreOutcome` total: every member has a named
raiser and a determined status.

| Origin | Count | Members | `status` |
| --- | --- | --- | --- |
| **Store only** — needs stored rows, so a pure function cannot detect it | 3 | `command_conflict`, `receipt_conflict`, `workflow_unknown` (the store detects the missing row before `decide`; `decide` additionally fails closed with it when handed no snapshot) | `conflict` for the two `*_conflict` codes, `refused` for `workflow_unknown` |
| **Both** — the reducer holds the semantic gate, the store holds the storage gate, and they must agree | 8 | `command_malformed` and `command_unknown` (the store's §10.2 four-field subset, then the reducer's full envelope check); `workflow_exists` (the store's pre-check plus the `UNIQUE(work_spec_sha256)` INSERT, and the reducer's `snapshot is not None` twin); `revision_mismatch` (the reducer's `expected_revision` check, then the CAS rowcount); `snapshot_divergence` (the store's §7.2 agreement gate, then the reducer's `_verify_snapshot`); `history_corrupt`, `history_unknown_event`, `policy_version_unsupported` (raised out of `fold`/`verify_history`, which only the store calls against stored rows) | `refused` |
| **Reducer only** — pure judgments over documents the store merely carries | 32 | `command_schema_unsupported`, `payload_malformed`, `workflow_terminal`, `illegal_transition`, `transition_reserved`, `admission_artifact_invalid`, `admission_report_malformed`, `admission_report_unbound`, `admission_status_blocking`, `admission_registry_mismatch`, `admission_task_unknown`, `admission_task_closed`, `approval_not_required`, `approval_already_satisfied`, `approval_pending`, `approval_fact_malformed`, `approval_fact_unbound`, `approval_fact_missing`, `dispatch_already_pending`, `dispatch_not_pending`, `cancel_already_pending`, `receipt_malformed`, `receipt_unbound`, `receipt_out_of_order`, `receipt_superseded`, `runtime_uuid_mismatch`, `result_malformed`, `result_unbound`, `result_inconsistent`, `result_attempt_exceeded`, `result_outcome_inconclusive`, `evidence_insufficient` | `refused` |

`admission_task_unknown` and `admission_task_closed` are reducer-raised
even though the FACTS behind them are the store's two `tasks` reads: the
store supplies `AdmissionFacts(task_exists, task_open)` and the reducer
decides, exactly as U-W2 §9 freezes. That split is why the store never
refuses admission on its own.

`transition_reserved` is declared UNREACHABLE through this store: only a
`failed` receipt against a `compensating` snapshot can attempt a reserved
edge, no command or receipt kind can move a workflow INTO `compensating`
under policy v1, and the storage CHECK would accept a hand-written
`compensating` row only for a workflow whose history could not fold to it.
§20 row S23 asserts the unreachability rather than fabricating a path.

## 10. The command transaction (D-v0.4.89)

### 10.1 Transaction mode

```python
with db.transaction(conn):
    conn.execute("BEGIN IMMEDIATE")
    ...
```

`BEGIN IMMEDIATE` is the FIRST statement, so the write lock is acquired
before every read — the live `routing.py` / `agent_handoffs.py` idiom
("write lock before the re-reads"). The read-decide-write sequence is
therefore serialized against every other writer, and no other connection
can change the row between the snapshot read and the compare-and-swap.
`db.transaction` commits on clean exit and rolls back on any exception.
There is exactly one `conn.execute("BEGIN IMMEDIATE")` in
`workflow_store.py` (§20 row S12, the live counting idiom).

### 10.2 Pre-lock steps (pure, no transaction)

| Step | Action | Failure |
| --- | --- | --- |
| P1 | `_require_schema(conn)`: `SELECT value FROM meta WHERE key='schema_version'` | `WorkflowStoreError("store_schema_unsupported")` |
| P2 | `_command_identity(document)`: canonical round trip, then read `command_id` (UUID pattern), `workflow_id` (`WF-<n>` pattern, absent iff `command == "admit_work_spec"`), and recompute `command_sha256 = protocols.content_digest(record)`; also read `command` against `WORKFLOW_COMMANDS` and require the embedded `content_sha256` to recompute | `StoreOutcome(status="refused", reason="command_malformed")`, or `"command_unknown"` for a verb outside the vocabulary |

P2 is a STRICT SUBSET of `workflow_engine`'s envelope verification: it
checks only the four things the store itself needs and defers every other
envelope rule to `decide`. §20 row S9 pins that the subset never accepts a
command `decide` rejects on those four fields and never rejects one
`decide` accepts, over a frozen corpus. Precedence, declared: because P2
runs first, a document failing several gates may report P2's subset code
where `decide` alone would report a more specific one — a non-constant
`schema` alongside a malformed `command_id` reports `command_malformed`
from P2 where `decide` would report `command_schema_unsupported`. Both are
closed refusals; S9 pins accept/reject agreement on the four subset
fields, not code identity.

### 10.3 Locked steps, in exact order (non-admission verbs)

| Step | Action | Refusal on failure |
| --- | --- | --- |
| C1 | `BEGIN IMMEDIATE` | — |
| C2 | Command dedupe: `SELECT workflow_id, command, command_sha256, resulting_revision, event_seq_first, event_seq_last FROM workflow_commands WHERE command_id = ?` | — |
| C3 | Replay/conflict decision (§14.2): digest equal and same workflow → REPLAY (read the event range, roll back, return); digest different, or a different workflow → `command_conflict` (status `conflict`) | — |
| C4 | Snapshot read: `_load_snapshot` (§7.2) — projection row, history, `fold`, splice, seal, agreement gate | `workflow_unknown`, `history_corrupt`, `history_unknown_event`, `policy_version_unsupported`, `snapshot_divergence` |
| R1 | *(`record_queue_receipt` only)* receipt dedupe (§11.2) | `receipt_conflict` (status `conflict`), or REPLAY |
| C5 | — deliberately no store-side step: semantic revision validation is the reducer's, inside C7 (`decide` refuses `revision_mismatch` when `expected_revision` disagrees with the snapshot's `revision`); the storage gate is the C14 CAS (§4.2, §9.5) | — |
| C6 | *(`admit_work_spec` only — see §10.4)* | — |
| C7 | `decision = workflow_engine.decide(snapshot, document, AdmissionFacts())` | any closed §8 reason the reducer raises |
| C8 | `_insert_command(...)` → `workflow_commands`, then finalize its row hash | — |
| C9 | `_insert_events(...)` → one `workflow_events` row per decision event, in `seq` order | — |
| C10 | `_insert_intent(...)` → `workflow_intents` when `decision.intent is not None` (status `outstanding`), then finalize its row hash | — |
| C11 | `_resolve_intent(...)` → close intents named by the emitted events (§10.5), re-finalizing each row hash | — |
| C12 | `_insert_receipt(...)` → `workflow_receipts` for `record_queue_receipt`, then finalize its row hash | — |
| C13 | `_insert_fact(...)` → `workflow_facts` for `record_approval` / `record_result`, `ON CONFLICT DO NOTHING`, then finalize its row hash when a row was inserted | — |
| C14 | `_cas_snapshot(...)` → `UPDATE workflows SET state=?, revision=?, dispatch_intent_id=?, cancel_intent_id=?, runtime_task_uuid=?, queue_route=?, policy_version=?, updated_at=?, content_sha256=? WHERE id=? AND revision=?` — rowcount MUST be 1 | `revision_mismatch` (§12.2) |
| C15 | `_journal(...)` → one `events.emit` row per appended workflow event (§10.6) | — |
| C16 | COMMIT (implicit, on clean exit of `db.transaction`) | — |

### 10.4 The admission path

`admit_work_spec` carries no `workflow_id` and has no row to update, so its
order differs and is frozen separately:

| Step | Action | Refusal on failure |
| --- | --- | --- |
| A1 | `BEGIN IMMEDIATE` | — |
| A2 | Command dedupe (C2/C3, unchanged) | `command_conflict` / REPLAY |
| A3 | Peek the artifact's task: canonically parse `payload.work_spec_document`, read `aos_task_id` if present and pattern-valid, `SELECT status FROM tasks WHERE id = ?`, and build `AdmissionFacts(task_exists, task_open)`. A payload that is not a well-shaped object yields `AdmissionFacts(False, False)` and lets `decide` refuse with its own precise code | — |
| A4 | `decision = decide(None, document, facts)` | any closed §8 reason, including `admission_task_unknown` / `admission_task_closed` |
| A5 | Derive `id = ids.parse_id(decision.snapshot_after["workflow_id"], "workflow")`; `SELECT 1 FROM workflows WHERE id = ? OR work_spec_sha256 = ?` — a hit is `workflow_exists` | `workflow_exists` |
| A6 | `_insert_workflow(...)` → the `workflows` row (`revision = 1`, `state = 'compiled'`, both bodies verbatim, `content_sha256` from the sealed snapshot). An `sqlite3.IntegrityError` from THIS statement maps to `workflow_exists`; from anywhere else it is `store_unavailable` | `workflow_exists` |
| A7 | `_insert_command(...)` — after the parent row, because the FK is immediate | — |
| A8 | `_insert_events(...)` (exactly one: `workflow_admitted`) | — |
| A9 | `_journal(...)` | — |
| A10 | COMMIT | — |

`task_open` is `status != _TASK_CLOSED_STATUS` where `_TASK_CLOSED_STATUS
= "done"`, pinned by §20 row S20 to be a member of `models.TASK_STATUSES`
and the status `ops.mark_done` sets. The store reads two columns of
`tasks` and writes none.

### 10.5 Intent status transitions

Driven by the EMITTED EVENT PAYLOADS, never by diffing snapshots — a
frozen, total table:

| Emitted event | Intent named by | New status | `resolved_receipt_id` |
| --- | --- | --- | --- |
| `dispatch_requested` | `payload.intent_id` | inserted as `outstanding` | NULL |
| `cancel_requested` | `payload.cancel_intent_id` | inserted as `outstanding` | NULL |
| `dispatch_revoked` | `payload.intent_id` → `revoked`; `payload.cancel_intent_id` → inserted as `outstanding` | `revoked` / `outstanding` | NULL |
| `dispatch_accepted` | `payload.intent_id` | `resolved` | `payload.receipt_id` |
| `dispatch_rejected` | `payload.intent_id` | `resolved` | `payload.receipt_id` |
| `workflow_cancelled` with `intent_id` | `payload.intent_id` | `resolved` | `payload.receipt_id` |
| every other event | — | — | — |

The table's INSERT entries ("inserted as `outstanding`") are step C10's:
each is exactly `decision.intent`, inserted once. Its status-change
entries (`revoked`, `resolved`) are step C11's, and C11 executes ONLY
those — the cancel intent a `cancel_requested` or `dispatch_revoked`
event names is inserted at C10 and never twice.

Each close is itself a compare-and-swap: `UPDATE workflow_intents SET
status=?, resolved_receipt_id=?, content_sha256=? WHERE intent_id=? AND
status='outstanding'` with a required rowcount of 1. A second close is
therefore impossible and no reverse transition exists.

### 10.6 The journal

One `events.emit` row per appended workflow event — a two-event command
writes two, because `action` IS the event name and one row would have to
drop the other. U-W2 §14.2's "one AOS journal row" is read as one row per
appended event — the reading U-W2 amendment §A.3.1 item 7 records.

```text
events.emit(conn,
    actor    = command["actor"],
    entity   = "workflow",
    entity_id= workflows.id,               # INTEGER
    action   = event["event"],
    payload  = {"workflow_id": "WF-<n>", "seq": int, "revision": int,
                "policy_version": int, "from_state": str|None,
                "to_state": str|None, "command": str, "command_id": uuid,
                "command_sha256": sha256, "event_sha256": sha256,
                "work_spec_sha256": sha256})
```

Enums, validated identifiers, bounded integers and digests only; no free
text, no document excerpt, no stored column value. `events.emit` adds
`schema_version: 1` and passes both the payload and the actor through
`secretscan.redact_tree`, so a secret-shaped actor or identifier cannot
reach the journal (§18.5).

### 10.7 The write path reads no clock

`workflows.created_at`, `workflows.updated_at`,
`workflow_commands.created_at`, `workflow_intents.created_at`,
`workflow_receipts.created_at`, and `workflow_facts.recorded_at` are ALL
the accepted command's `created_at` — the caller-supplied RFC3339 Z
instant the reducer already real-instant-checked and already copied into
every event. The store therefore imports no time module and calls no clock
(§8.5), the entire six-table write is a pure function of the command and
the prior rows, and a crash-and-retry writes byte-identical rows. The only
wall-clock read in the transaction is `events.emit`'s own `ts`, which the
journal framework owns. Declared consequence: a caller that supplies a
wrong `created_at` mis-stamps its own rows — already true of every event
in this unit — and the AOS journal's `ts` is the authoritative wall-clock
record of when the write actually happened.

## 11. The receipt transaction

`record_queue_receipt` is the command transaction of §10.3 with two extra
steps. It is not a second entry point: there is one `submit`, one
transaction shape, and one revision rule, because a second entry point
would be a second authority.

### 11.1 Canonical receipt validation

Performed entirely by the reducer (`_verify_receipt`): closed key set,
`schema` constant, `receipt_kind` membership, `receipt_id`/`workflow_id`/
`work_spec_sha256`/`reported_at` patterns, optional `trace` and
`queue_route`, the four per-kind required/allowed/forbidden field rules,
and the recomputed self-digest. Any failure is `receipt_malformed`. The
store adds no validation of its own and duplicates none.

### 11.2 Receipt dedupe (step R1)

`_receipt_identity(payload)` reads `payload.receipt_document` and, when it
is a canonically serializable object carrying a UUID `receipt_id`,
computes `receipt_sha256 = protocols.content_digest(document)` — RECOMPUTED,
never read from the document's own member. When it is not, the store skips
the dedupe entirely and lets `decide` refuse `receipt_malformed`; the
store never refuses on its own here.

```text
SELECT workflow_id, receipt_sha256 FROM workflow_receipts WHERE receipt_id = ?
```

| Result | Outcome |
| --- | --- |
| no row | continue to C7 |
| row, `receipt_sha256` equal, same `workflow_id` | REPLAY: locate the event whose `payload.receipt_id` equals this id (every receipt-driven event carries `receipt_id` and `receipt_sha256` in its payload), return that event's whole command group as `events`, that event's `revision` as `revision`, `intent=None`, roll back, return `status="replay"` |
| row, `receipt_sha256` different | `receipt_conflict`, status `conflict` |
| row, digest equal but a DIFFERENT `workflow_id` | `receipt_conflict`, status `conflict` — the digest covers `workflow_id`, so this pair can only exist if the column was tampered with, and the store refuses rather than replaying a foreign history |

**R1 runs before `decide`, and that ordering is load-bearing.** A
redelivered `accepted` receipt arrives when the workflow has already moved
to `scheduled`; handing it to the reducer would produce
`receipt_out_of_order` for a receipt that was in fact applied. Dedupe
first turns it into the accepted no-op U-W2 §13.3 promises.

### 11.3 Delayed, superseded, and terminal receipts

All decided by the reducer, all `status="refused"`, all writing nothing:

| Situation | Reason |
| --- | --- |
| arrived early (its predecessor has not been applied) | `receipt_out_of_order` — safely redeliverable after its predecessor |
| names an intent this workflow revoked | `receipt_superseded` — permanent; drop it |
| names an intent that was already resolved, or no known intent | `receipt_superseded` / `receipt_unbound` |
| workflow already terminal | `workflow_terminal`, except a receipt naming a REVOKED intent, which earns the more specific `receipt_superseded` |
| reports a different `runtime_task_uuid` | `runtime_uuid_mismatch` |
| binds a different workflow or work-spec digest | `receipt_unbound` |
| a `resumed` out of `waiting_approval` with no later runtime approval event | `approval_fact_missing` |

Refusal is the ledger declining to record a fact it cannot place, never a
request for infinite retry: the store neither queues, defers, nor
re-attempts a refused receipt.

### 11.4 Storage and CAS

An accepted receipt inserts exactly one `workflow_receipts` row (step C12)
with `intent_id` and `runtime_task_uuid` projected from the document,
`document` verbatim, and `receipt_sha256` recomputed; then the intent
closures of §10.5 run; then the CAS of C14. Under transition policy v1 a
receipt NEVER emits an intent — every branch of the reducer's receipt
handler returns `None` — so step C10 is a no-op on this path, and §20 row
S7 pins that no receipt-driven `submit` ever produces a
`StoreOutcome.intent`.

## 12. CAS and concurrency (D-v0.4.89, D-v0.4.91)

### 12.1 SQL transaction mode

`BEGIN IMMEDIATE` inside `db.transaction`. Deferred mode is not used
anywhere in this slice: with a deferred begin the read that decides would
run outside the write lock and the CAS could lose after the reducer had
already been consulted, which is a wasted decision and a second failure
mode to explain. Immediate mode makes the whole
read-decide-write-journal-commit sequence a single serialized critical
section.

### 12.2 Expected rowcount

| Statement | Required rowcount | Otherwise |
| --- | --- | --- |
| `UPDATE workflows ... WHERE id=? AND revision=?` | exactly 1 | roll back; `StoreOutcome(status="refused", reason="revision_mismatch")` |
| `UPDATE workflow_intents ... WHERE intent_id=? AND status='outstanding'` | exactly 1 | roll back; `WorkflowStoreError("store_unavailable")` — the intent the emitted event names must exist and be outstanding, so anything else is a damaged outbox, not a caller error |
| `INSERT INTO workflows` | exactly 1 | see A6 |
| `INSERT INTO workflow_facts ... ON CONFLICT DO NOTHING` | 0 or 1 | both are correct (§5.6) |

Under `BEGIN IMMEDIATE` a `workflows` rowcount of 0 is unreachable from
concurrency; it means the row was deleted or its revision changed outside
any code path this repository contains. `revision_mismatch` is the honest
code — the storage gate disagreed with the semantic gate — and it is the
one U-W2 §10 pairs with the CAS.

### 12.3 Identical concurrent commands

Two processes submitting the SAME `command_id` and digest: the write lock
serializes them. The first commits. The second's C2 dedupe finds the row
and returns `status="replay"` with the original events and resulting
revision, `intent=None`. Both callers observe a consistent, idempotent
result and exactly one set of rows exists.

### 12.4 Conflicting concurrent commands

Two processes submitting DIFFERENT commands against the same
`expected_revision`: the first commits and the revision advances. The
second's C4 snapshot read (inside its own lock, after the first committed)
sees the new revision, C7's `decide` refuses `revision_mismatch`, and nothing is
written. The caller re-reads and issues a NEW command with a NEW
`command_id` — a fresh decision, deliberately, not an automatic retry.

### 12.5 Command / receipt races

Two DIFFERENT commands carrying the SAME receipt: the first commits and
stores the receipt row. The second's R1 dedupe finds it with an equal
digest and returns `replay`; the receipt cannot apply twice. Two different
commands carrying DIFFERENT receipts with the same `receipt_id`: the
second gets `receipt_conflict` and is never made legal by redelivery.

### 12.6 Bounded lock handling, and why it is not U-W3 retry

`db.connect` already sets `sqlite3.connect(timeout=5.0)` and
`PRAGMA busy_timeout=5000`, so a contended `BEGIN IMMEDIATE` waits up to
five seconds inside SQLite's own busy handler and then fails. **The store
adds nothing**: no loop, no sleep, no backoff, no re-issue, no
re-decision. A `sqlite3.OperationalError` after the busy timeout becomes
`WorkflowStoreError("store_unavailable")` and the human retries the
command.

That is a storage primitive, not retry behavior, and the distinction is
exact:

- Lock waiting is bounded by a PRAGMA already configured for every
  connection in this repository; it carries no workflow semantics,
  consumes no attempt budget, appends no event, and changes no state. The
  same command, once the lock is free, produces the same decision.
- U-W3 retry is RE-EXECUTION of work after a failed attempt: it advances
  an attempt counter, is bounded by the artifact's `retry.max_attempts`,
  and changes what the workflow claims about the world.
- A `revision_mismatch` refusal is likewise not a retry: the store does
  not re-read and re-issue. The caller must mint a new `command_id`,
  which is a new decision by a human or an adapter, recorded as such.

If this slice contained any automatic re-issue, the "no retry loop of any
kind" exclusion of U-W2 §0.2 would be false. It contains none, and §20 row
S23 proves it by AST: no `while` loop, no `time.sleep`, and no recursive
`submit` call exist in `workflow_store.py`.

## 13. Complete crash matrix

Every point is a forced exception injected at the named boundary. `db.
transaction`'s `with conn:` rolls back on any exception, so the invariant
below holds at every pre-commit point without exception handling of its
own.

### 13.1 Command transaction (non-admission)

| # | Crash point | Visible rows afterwards |
| --- | --- | --- |
| K0 | before `BEGIN IMMEDIATE` | nothing; no lock was taken |
| K1 | after C2/C3 dedupe reads, before C4 | nothing |
| K2 | after C4 snapshot read, before C7 | nothing |
| K3 | inside C7 `decide` | nothing |
| K4 | inside `_insert_command`, before its row-hash finalization | nothing |
| K5 | after `_insert_command`, before `_insert_events` | nothing |
| K6 | between the first and second `workflow_events` insert of a two-event command | nothing — including no half-recorded event pair |
| K7 | after `_insert_events`, before `_insert_intent` | nothing |
| K8 | after `_insert_intent`, before `_resolve_intent` | nothing |
| K9 | after `_resolve_intent`, before `_insert_receipt` | nothing |
| K10 | after `_insert_receipt`, before `_insert_fact` | nothing |
| K11 | after `_insert_fact`, before `_cas_snapshot` | nothing |
| K12 | after `_cas_snapshot`, before `_journal` | nothing — the snapshot does NOT advance without its events |
| K13 | inside `_journal`, after the first of two `events.emit` calls | nothing, in all six tables AND in `events` |
| K14 | after `_journal`, before COMMIT | nothing |
| K15 | after COMMIT, before the caller observes the return value | everything, consistently; re-running the identical command is an exact-duplicate replay |
| K16 | after COMMIT, before U-W2.3 exports the outbox | everything; the intent row persists as `outstanding` and delivery is re-driveable at any time (the outbox pattern), safely, because the queue dedupes on `idempotency_key` |

### 13.2 Admission transaction

| # | Crash point | Visible rows afterwards |
| --- | --- | --- |
| KA0 | before `BEGIN IMMEDIATE` | nothing |
| KA1 | after A3 task read, before A4 | nothing |
| KA2 | inside A4 `decide` | nothing |
| KA3 | after A5 existence check, before `_insert_workflow` | nothing |
| KA4 | inside `_insert_workflow`, before its `content_sha256` is written | nothing — the column has no default, so a hashless row is unrepresentable |
| KA5 | after `_insert_workflow`, before `_insert_command` | nothing — no orphan `workflows` row |
| KA6 | after `_insert_command`, before `_insert_events` | nothing — no command row without its `workflow_admitted` event |
| KA7 | after `_insert_events`, before `_journal` | nothing |
| KA8 | inside `_journal` | nothing |
| KA9 | after COMMIT | the complete instance at `revision = 1`, `state = 'compiled'`, `last_seq = 1` |

### 13.3 The invariant every acceptance test proves

At K0–K14 and KA0–KA8, for the workflow under test:

```text
SELECT COUNT(*) FROM workflows          WHERE id = ?           -- unchanged
SELECT COUNT(*) FROM workflow_events    WHERE workflow_id = ?  -- unchanged
SELECT COUNT(*) FROM workflow_commands  WHERE workflow_id = ?  -- unchanged
SELECT COUNT(*) FROM workflow_intents   WHERE workflow_id = ?  -- unchanged
SELECT COUNT(*) FROM workflow_receipts  WHERE workflow_id = ?  -- unchanged
SELECT COUNT(*) FROM workflow_facts     WHERE workflow_id = ?  -- unchanged
SELECT COUNT(*) FROM events             WHERE entity='workflow' -- unchanged
```

and every column of the surviving `workflows` row (including `revision`,
`updated_at`, and `content_sha256`) is byte-identical to its pre-command
value. Then the same command is re-submitted and succeeds, producing
exactly the rows a clean run would have produced. Injection is by three
frozen mechanisms, together covering every enumerated point: (i) patching
the nine named mutation helpers — `_insert_workflow`, `_insert_command`,
`_insert_events`, `_insert_intent`, `_resolve_intent`, `_insert_receipt`,
`_insert_fact`, `_cas_snapshot`, `_journal` — for K4, K5, K7–K14, and
KA3–KA8; (ii) patching the transaction entry and the pre-mutation
boundaries — the `BEGIN IMMEDIATE` statement, the C2/A2 dedupe read,
`_load_snapshot`, `workflow_engine.decide`, and the A3 task read — for
K0–K3 and KA0–KA2; (iii) a wrapper on `_insert_events` that raises between
the first and second row inserts of a two-event command, for K6. The nine
helper names are frozen architecture and not implementation detail (§20
row S13).

## 14. Replay, dedupe, and conflict (D-v0.4.90)

### 14.1 Identities

| Axis | Identity | Discriminator | Storage gate |
| --- | --- | --- | --- |
| Command | `workflow_commands.command_id` | `command_sha256`, recomputed | `command_id TEXT NOT NULL UNIQUE` |
| Receipt | `workflow_receipts.receipt_id` | `receipt_sha256`, recomputed | `receipt_id TEXT NOT NULL UNIQUE` |
| Fact | `(workflow_id, fact_kind, document_sha256)` | the digest itself | composite UNIQUE |
| Intent | `workflow_intents.intent_id` | derived by the reducer from `(work_spec_sha256, intent_seq)` | `intent_id TEXT NOT NULL UNIQUE` |
| Workflow | `workflows.id` | `work_spec_sha256` | PK + UNIQUE |

### 14.2 Command dedupe

- **Exact duplicate** — same `command_id`, recomputed digest equal, same
  `workflow_id`: returns the ORIGINAL outcome. `status="replay"`,
  `replay=True`, the original events read from
  `[event_seq_first, event_seq_last]`, the original `resulting_revision`,
  no new event, no revision change, no new intent row, and
  `intent is None`. `decide` is never called. Duplicate delivery of an
  accepted command is idempotent end to end.
- **Conflicting duplicate** — same `command_id`, different digest:
  `command_conflict`, status `conflict`. Nothing is merged, nothing is
  guessed, nothing is stored.
- **Cross-workflow duplicate** — same `command_id`, equal digest, but the
  stored row names another workflow: `command_conflict`. The digest covers
  `workflow_id`, so this pair is only producible by tampering.
- **Duplicate of a REFUSED command**: not replayable, because refusals
  store nothing. It is re-evaluated and — the reducer being pure and the
  store's reads being deterministic — refuses identically.
- **Out-of-order commands**: there is no queue and no reordering. A stale
  or future `expected_revision` refuses `revision_mismatch` and the caller
  re-reads and re-issues deliberately.

### 14.3 Receipt dedupe

As §11.2. The same exact-duplicate-replay and conflicting-duplicate-
refusal rules as commands, keyed on `receipt_id`, evaluated before
`decide`, and answered from the event payload that recorded the original
application.

### 14.4 Retention, and why nothing may be pruned

| Table | Deletion allowed | What deletion would break |
| --- | --- | --- |
| `workflow_events` | never | `fold` is the only producer of the seven derived snapshot fields (§7.2); one missing event makes the workflow permanently `history_corrupt` and its snapshot unreproducible |
| `workflow_commands` | never | a redelivered duplicate would re-apply, and the +1-per-command revision arithmetic would no longer be provable from storage |
| `workflow_receipts` | never | a redelivered receipt would apply twice; the inbox exists precisely to make at-least-once delivery safe |
| `workflow_facts` | never | a `succeeded` claim would lose the verbatim envelope it rests on, and an approval would lose the document that satisfied it |
| `workflow_intents` | never | the local record of what was asked of the queue would disappear while the queue still holds the work |
| `workflows` | never | the two verbatim bodies are admission-time immutables no event payload carries (§7 permits digests only) |

There is consequently no `DELETE` statement and no `--prune` surface
anywhere in this slice, and §20 row S18 asserts the module's SQL contains
no `DELETE` and no `DROP`.

## 15. History, corruption, and unknown versions (D-v0.4.92)

### 15.1 Canonical event sequence

`seq` is dense from 1 per workflow, `UNIQUE(workflow_id, seq)`, always read
`ORDER BY seq`. `_read_history` requires `seq == index + 1`, so a gap or a
non-dense sequence is `history_corrupt` at the exact index.

### 15.2 The verdict table

| Condition | Verdict | Reachable through storage? |
| --- | --- | --- |
| `seq` gap | `history_corrupt` | yes — a deleted row (only by direct SQL) |
| duplicate `seq` | `history_corrupt` | NO — `UNIQUE(workflow_id, seq)` forbids it even from raw SQL |
| reordered rows | `history_corrupt` | NO — the read is `ORDER BY seq`; reordering is not expressible |
| recomputed event digest mismatch | `history_corrupt` | yes — any tampered column or payload |
| from-state chain break | `history_corrupt` | yes |
| first row is not `workflow_admitted`, or a later row is | `history_corrupt` | partly — the `(event='workflow_admitted') = (from_state IS NULL)` CHECK narrows it |
| revision arithmetic broken across commands | `history_corrupt` | yes |
| unknown event name | `history_unknown_event` | NO — the `event` CHECK forbids it |
| `policy_version` outside `SUPPORTED_POLICY_VERSIONS` | `policy_version_unsupported` | yes — the column carries a `>= 1` CHECK but no enum |
| unparseable `payload_json`, or a non-text document column | `history_corrupt` (events) / `snapshot_divergence` (bodies) | yes |
| rebuilt snapshot disagrees with the projection or its digest | `snapshot_divergence` | yes |
| stored body no longer hashes to its admitted digest | `snapshot_divergence` | yes |

Rows marked "NO" are declared unreachable rather than tested through the
store; §20 row S15 proves the constraint that makes them unreachable, and
the engine's own tests exercise the codes on caller-supplied lists.

### 15.3 Behavior while a workflow fails verification

- **Mutating commands refuse.** `submit` returns `status="refused"` with
  the exact verdict code and writes nothing. There is no override.
- **Read paths stay total.** `read_workflow` returns the projection with
  `integrity` set; `read_history` returns every record it could
  reconstitute in `seq` order plus `unreadable_seq`; `list_workflows`
  includes the workflow; `list_outstanding_intents` still lists its
  outbox with `readable` flags. This is U-W2 §14.2's "read-only display
  remains available with an explicit integrity warning", made a typed
  field rather than a printed sentence.
- **Nothing is repaired.** See §7.6.

### 15.4 `verify`

`verify(conn, workflow_id=None)` rebuilds each workflow, compares, and
returns one `VerifyReport` each, ordered by `workflows.id`:

1. reconstitute and `verify_history` the events → `integrity`, `reason`,
   `where`;
2. `fold` + splice + seal → `rebuilt_content_sha256`;
3. compare against `stored_content_sha256` and the seventeen §7.2
   member-backed columns → `divergent_fields`;
4. recompute the four §5.8 row hashes for every command, intent, receipt
   and fact row of the workflow → `divergent_rows`;
5. re-digest both stored bodies against the digests the `workflow_admitted`
   event recorded → folded into `divergent_fields` as
   `work_spec_document` / `report_document`.

`verify` issues no `INSERT`, `UPDATE`, `DELETE`, or `events.emit`, and
opens no transaction (§20 row S16). "Rebuildable by `fold`" means exactly
what §7.2 says and not more: a `verify` that demanded the BODIES come out
of history would report divergence on every healthy workflow, because
U-W2 §7 permits digests only in event payloads.

### 15.5 Old-history replay

`fold` replays every event under the `policy_version` the event itself
recorded. When transition policy v2 ships, version 1's matrix is retained
verbatim in the engine and old history re-derives under the rules it was
written by. The store's contribution is only that it stores
`policy_version` per event and never rewrites it, and that it refuses to
mutate a workflow whose history carries a version this build does not
support. HISTORY IS NEVER MIGRATED: schema changes ride U-M1; recorded
history is adapted at read time.

## 16. Facts and intents

### 16.1 Facts

- Identity, binding, immutability and duplicate behavior: §5.6.
- `fact_kind` is `approval` for a `record_approval` command and `result`
  for a `record_result` command that was ACCEPTED. A refused
  `record_result` (inconclusive outcome, insufficient evidence, exceeded
  attempt budget, unbound envelope) stores no fact, because it appended no
  event.
- `fact_scope` is the approval document's own `scope` for an approval and
  NULL for a result; the biconditional CHECK makes any other combination
  unrepresentable.
- A `fail` result's envelope — including any `compensation` block — is
  stored verbatim and NOT acted on. Compensation is U-W3's.
- U-W2.2 writes no `evidence` row in the task plane. Importing an
  envelope's evidence into the ledger stays a human act through
  `aos evidence add` (D-v0.3.8).

### 16.2 Intents

- Identity, binding, mutability and the status CAS: §5.4, §10.5.
- **Pending-intent ordering is `workflow_intents.id` ASC** — insertion
  order, which within a workflow is exactly `intent_seq` order, and across
  workflows is emission order. Deterministic, total, and stable under
  concurrent writers because every insert happens under the write lock.
- `list_outstanding_intents` filters `status = 'outstanding'` and applies
  an optional `workflow_id`. It never sorts by a document field, never
  dedupes, never batches, and never marks anything delivered.
- **The store claims no transport authority.** It does not know whether an
  intent was delivered, leased, retried, or dropped; `status` records only
  what the LEDGER learned — that a receipt closed it or that a revocation
  withdrew it. There is no `delivered_at`, no `attempts`, no
  `next_visible_at`, and no worker column, because every one of those is
  the private runtime's or U-W3's.
- Declared consequence: a cancel intent can remain `outstanding` forever
  on two path classes. (1) Outbox-only: `revoke_dispatch` and pre-dispatch
  `request_cancel` emit cancel intents that never set `cancel_intent_id`,
  and no receipt kind acknowledges them. (2) Terminal race: a TWO-PHASE
  cancel intent (pointer set) is stranded when the workflow terminates by
  a `failed` receipt, by `record_result` (`success` or `fail`), or by a
  UNILATERAL `cancelled` receipt — each clears the pointer while its event
  payload names no cancel intent, so the §10.5 table closes nothing.
  Re-export is idempotent by content-addressed filename, so permanent
  outstanding status is a truthful "the queue may still need to be told",
  not a leak.

## 17. Existing task and run compatibility

### 17.1 The exact separation

| Existing surface | U-W2.2 relationship |
| --- | --- |
| `models.TASK_STATUSES` | READ as a vocabulary only, to pin `_TASK_CLOSED_STATUS = "done"` |
| `ops.LEGAL_TASK_TRANSITIONS` | not imported, not referenced, not mirrored |
| `models.RUN_OUTCOMES` | not imported; `workflows.state` is a disjoint vocabulary |
| `ops.start_run`, `ops.end_run` | untouched; the store never reads or writes `runs` |
| `ops.mark_done`, `ops.set_task_status` | untouched; the store never writes `tasks` |
| `events.emit` | called, unchanged, with `entity="workflow"` |
| `tasks` table | READ ONLY, exactly `SELECT status FROM tasks WHERE id = ?`, once per `admit_work_spec` |
| `runs`, `evidence`, `decisions`, `handoffs`, `memory*`, `agents*`, `routing*` tables | never read, never written |

`workflows.task_id REFERENCES tasks(id)` is the one structural coupling:
a workflow cannot name a task that does not exist, and (the ledger having
no delete path) the task cannot later vanish.

### 17.2 Why this is not a competing state machine

`workflows.state` has thirteen members, none of which is a
`TASK_STATUSES` member; no mapping between the two vocabularies exists in
code or in this document; no workflow command mutates a task or a run; no
task transition mutates a workflow. The task check is admission-time only
(U-W2 §22), so a human may close a task while its workflow is `running`,
and the workflow plane's `succeeded`/`failed` and the run plane's
`RUN_OUTCOMES` are independent records of the same work that may disagree.
Reconciliation is a human act; U-W2.2 neither prevents nor detects the
divergence, and says so rather than implying a coupling it does not have.
Pinned by §20 row S20: the §21 suite-wide run passes with every existing
test and fixture file outside the eleven §19.3 paths byte-unchanged (the
amended U-W2 §19.22 clause; rows 21–22 acceptance remains U-W2.3's),
`mark_done` still refuses a `done` with zero evidence, and no workflow
command changes any `tasks` or `runs` row.

## 18. Hostile persistence and injection resistance (D-v0.4.93)

Persisted rows and canonical bodies are DATA. The store's guarantees:

### 18.1 Body and digest substitution

Every digest is recomputed from the stored bytes at every use and compared
against the value the SAME untrusted row supplies: `workflows.
content_sha256` against the resealed snapshot, `workflow_events.
content_sha256` against the reconstituted record, `workflow_receipts.
receipt_sha256` and `workflow_facts.document_sha256` against their stored
documents, and both `workflows` bodies against the digests the
`workflow_admitted` event recorded. Agreement is agreement, not
provenance — a coherently spliced row states both halves — which is why the
reducer additionally runs the stored artifact back through
`workspecs.accept_work_spec` on every command. Substituting a body without
substituting every digest that covers it yields `snapshot_divergence` or
`history_corrupt`; substituting all of them consistently is indistinguishable
from a legitimate re-admission of a different artifact, which is a
different workflow identity and therefore a different row.

### 18.2 Unknown fields and schema versions

Closed key sets everywhere: the reducer refuses an unknown key in a
command envelope, payload, snapshot, event, receipt, approval fact, or
registry-state object. The store adds no lenient parse of its own. A
`schema` member that is not the frozen constant refuses
(`command_schema_unsupported`, `receipt_malformed`, `history_corrupt`).
`meta.schema_version` that is not `db.SCHEMA_VERSION` refuses
`store_schema_unsupported` before any query touches a workflow table.
`policy_version` outside `SUPPORTED_POLICY_VERSIONS` refuses
`policy_version_unsupported`.

### 18.3 Invalid canonical JSON, oversized values, and limits

`protocols.parse_canonical` enforces `MAX_ARTIFACT_BYTES` (262144),
`MAX_ARRAY_ITEMS` (256), `MAX_STRING_CHARS` (8192), `INT_MAX` (2**53-1),
BOM rejection, and duplicate-key rejection. Every stored document is read
through it, so an oversized or malformed body raises `ProtocolError` at a
known call site and becomes an integrity verdict, never a propagated
exception. The reducer additionally refuses at admission any instance
whose snapshot could not survive its own maximum growth
(`_require_admissible_size`), and refuses `snapshot_divergence` at either
bounded intent collection's ceiling and at every counter's ceiling — so a
workflow that admits can always be advanced and can never brick.
`parse_canonical` requires bytes; a document column holding a non-text
value is marked unreadable by type check BEFORE any encode, never coerced.

### 18.4 Raw exception closure

Every call site that can raise is wrapped and mapped:

| Raised | Mapped to |
| --- | --- |
| `workflow_engine.WorkflowRefusal` | `StoreOutcome(status="refused"\|"conflict")` |
| `protocols.ProtocolError` (stored document) | the integrity verdict for that row |
| `protocols.ProtocolError` (command document) | `command_malformed` |
| `workspecs.WorkSpecError` | reached only through the reducer, which maps it |
| `TypeError`, `ValueError`, `KeyError`, `AttributeError` from a tampered row | the integrity verdict, by explicit type checks BEFORE the access, not by broad excepts |
| `sqlite3.IntegrityError` from the one `workflows` INSERT | `workflow_exists` |
| any other `sqlite3.Error` | `WorkflowStoreError("store_unavailable")` |

§20 row S17 asserts, over a matrix of tampered rows covering every column
of all six tables, that no `sqlite3.Error`, `ProtocolError`, `KeyError`,
`TypeError`, `ValueError`, or `AttributeError` escapes any public
function.

### 18.5 Parameterized SQL and message safety

Every statement uses `?` placeholders for every value. The only
interpolated identifiers are the six frozen table-name constants from
`db.py`; no caller value, column value, or document field is ever
concatenated, `%`-formatted, or f-string-interpolated into SQL. §20 row
S18 AST-scans `workflow_store.py` and asserts that every `conn.execute`
first argument is a string literal or a module-level constant built only
from `db.*_TABLE` names, and that no `DELETE`, `DROP`, `ALTER`, `ATTACH`,
`PRAGMA`, or `executescript` appears anywhere.

Refusal and error messages are built from a closed code, a schema-safe
path or an already-validated identifier, and a fixed hint. No stored
column value, document excerpt, SQL fragment, file path, or exception
string enters a message; `diagnostics` carries bounded integers and closed
codes only. Journal payloads carry enums, validated identifiers, bounded
integers and digests, and pass through `events.emit`'s `redact_tree`
choke point, which also redacts a secret-shaped actor. §20 row S18 plants
a credential-shaped value in every text column of all six tables and
asserts it appears in no message, no `diagnostics`, no `StoreOutcome`
field other than the verbatim document a caller explicitly asked for, and
no `events` row.

### 18.6 Stored text that instructs the agent

A `workflow_facts.document`, a `workflow_events.payload_json`, a stored
WorkSpec `objective`, or a receipt `reason.message` may contain text that
reads as an instruction — "ignore your contract", "run this tool",
"reveal your prompt", "widen your scope". Such text is DATA and this slice
treats it as such structurally, not by policy:

- The store never executes, `eval`s, `exec`s, imports dynamically, or
  spawns anything; §20 row S18 asserts `eval`, `exec`, `compile`,
  `__import__`, `importlib`, `subprocess`, `os.system`, and `socket`
  appear nowhere in the module.
- Stored text never becomes SQL (§18.5), never becomes a message (§18.5),
  and never becomes a filesystem path (the store touches no path).
- The only stored strings the store ever COMPARES are pattern-validated
  identifiers and digests; the only stored strings it ever COPIES are
  whole verbatim documents handed back to an explicit reader.

§20 row S18 stores an artifact, an approval fact, a receipt, and a result
envelope whose free-text fields contain tool-invocation and
scope-widening instructions, and asserts every store decision is
byte-identical to the same journey with benign text.

## 19. Exact implementation paths (D-v0.4.94, D-v0.4.95)

The tables below are EXHAUSTIVE — the closed nineteen-path inventory
U-W2 amendment §A.4 authorizes, restated per path. A path outside them
appearing in the implementation wave is `FAIL — REPLAN REQUIRED`, and
nothing here is standing authority for any later wave or unit (U-W2
amendment §A.5).

### 19.1 Production

| # | Path | New/modified | Why it changes | Exact responsibility | Compatibility |
| --- | --- | --- | --- | --- | --- |
| 1 | `agentic_os/workflow_store.py` | NEW (production) | the slice has no other home | the entire §8 API, §10–§11 transactions, §12 CAS, §15 integrity | nothing imports it yet; U-W2.3 is its first caller |
| 2 | `agentic_os/db.py` | modified (production) | the schema is declared in exactly one place | `SCHEMA_VERSION = "6"`; six `{table}`-parameterized DDL constants; six table-name constants; `WORKFLOW_TABLES`; `SCHEMA_SQL` composition | purely additive: no existing DDL constant, table name, tuple, helper or PRAGMA changes |
| 3 | `agentic_os/migrations.py` | modified (migration) | a version bump requires its step | `_workflow_state_v6`, `WORKFLOW_STATE_V6 = Migration(5, 6, "u-w2-workflow-state-v6", …)`, appended to `MIGRATIONS` | `LATEST_VERSION` derives from `db.SCHEMA_VERSION`; no shipped step, id, or frozen DDL copy changes |
| 4 | `agentic_os/ids.py` | modified (production) | the CLI must parse a typed `WF-<n>` | `PREFIXES["workflow"] = "WF"` and the docstring clause | additive dict entry; `render_id`/`parse_id` logic untouched; no existing prefix moves |

### 19.2 Tests, new

| # | Path | New/modified | Exact responsibility |
| --- | --- | --- | --- |
| 5 | `tests/test_v04_workflow_store.py` | NEW (test) | the complete §20 matrix, rows S1–S24 |

### 19.3 Tests and fixtures, modified — authorized by U-W2 amendment §A.4.3

A `db.SCHEMA_VERSION` bump has required exactly this class of edit in
every prior schema unit: commit `7c5fea4` ("feat: add U-A3 routing and
handoff storage foundation"), which bumped `"4"` → `"5"`, touched
`tests/test_core.py`, `tests/test_v02_migrations.py`,
`tests/test_v02_power_modes.py`, `tests/test_v03_memory_claims.py`,
`tests/test_v03_memory_graph.py`, `tests/test_v04_agent_catalog.py`,
`tests/test_v04_agent_passports.py`, `tests/fixtures/v1_workspace.py`,
`tests/fixtures/v2_workspace.py`, and `tests/fixtures/v3_workspace.py`
for exactly these reasons. The landed U-W2 §18 slice table named five
paths and its §0.3 kept "every existing test" untouched — unsatisfiable
alongside `SCHEMA_VERSION = "6"` — and U-W2 governed amendment A1
resolves that contradiction by superseding exactly those clauses (U-W2
§A.3.1) and authorizing exactly these edits (U-W2 §A.4.3), for this one
delivery and no other. The frozen edit classes, restated per file below:
(a) version-literal rebase `5`/`"5"` → `6`/`"6"`; (b) migration-registry
or plan-list equality gains exactly `(5, 6, "u-w2-workflow-state-v6")`;
(c) one of the nine enumerated ordinal-bearing method renames; (d) the
single ceiling-guard re-scope; (e) the single migration-target rebase;
(f) the fixture drop loop. No test is deleted, skipped, or weakened, and
exactly one assertion — (d) — is re-scoped and renamed rather than
re-literaled.

| # | Path | Kind | Exact edits (classes per §A.4.3) | Evidence at this baseline |
| --- | --- | --- | --- | --- |
| 6 | `tests/test_core.py` | test | (a) `test_schema_version_recorded`: `"5"` → `"6"` | line 116 |
| 7 | `tests/test_v02_migrations.py` | test | (a) `LATEST_VERSION == 6`; (b) the registry equality and both plan/id lists gain the step; (c) `test_production_registry_is_the_four_production_steps` → `..._five_production_steps` | lines 199, 201, 211, 226, 234, 1075, 1084 |
| 8 | `tests/test_v02_power_modes.py` | test | (a) `test_schema_version_is_whatever_the_one_declaration_says`: `"5"` → `"6"` | line 1380 |
| 9 | `tests/test_v03_memory_claims.py` | test | (a) `test_fresh_init_creates_the_current_schema_version`: `"5"` → `"6"` | line 191 |
| 10 | `tests/test_v03_memory_graph.py` | test | (a) both fresh-init literals and `LATEST_VERSION == 6`; (b) registry list, `latest_version`, plan list; (d) `test_no_version_six_transition_exists`: predicate `> 5` → `> 6`, renamed `test_no_version_seven_transition_exists`, docstring restated — the suite then asserts the 5 → 6 step EXISTS and nothing transitions past 6 (the one meaning-rebased assertion, declared); (e) `test_corrected_retry_succeeds_exactly_once`: `migrate(target="5")` → `"6"`, keeping the doctor exit-0 assertion true under a v6 build | lines 253, 256, 280, 288, 290–294, 314, 322, 715, 721 |
| 11 | `tests/test_v04_agent_passports.py` | test | (a)+(c) `test_fresh_init_is_version_five_with_both_agent_tables` → `..._six_...`, value `"6"`; (b) both registry/plan lists gain the step; (c) `test_registry_is_exactly_the_four_steps_in_order` → `..._five_steps_...` | lines 205–208, 219, 229, 262 |
| 12 | `tests/test_v04_agent_catalog.py` | test | (a)+(c) `test_schema_stays_version_five` → `..._six`, value `"6"`; (a)+(c) `test_schema_stays_5_and_migration_state_is_untouched` → `..._6_...`, value `"6"` | lines 851–855, 1381–1394 |
| 13 | `tests/test_v04_routing_handoffs.py` | test | (a)+(c) `test_schema_version_is_five` → `..._six` (three literals); (b)+(c) `test_registry_has_the_new_fourth_step_in_exact_order` → `..._fifth_...`, list gains the step; (a)+(b)+(c) `test_migration_status_and_plan_report_four_to_five` → `..._five_to_six`, `latest_version == 6`, `plan[-1]` becomes the 5 → 6 step; (a) two migrated `current_version == 6` assertions; (a) `db.SCHEMA_VERSION == "6"`, `len(migrations.MIGRATIONS) == 5`, `MIGRATIONS[-1].migration_id == "u-w2-workflow-state-v6"` | lines 343–346, 348, 358, 363–372, 379, 433, 1062, 1063, 1065 |
| 14 | `tests/fixtures/v1_workspace.py` | fixture | (f) one `for table, _ddl in reversed(db.WORKFLOW_TABLES): DROP TABLE` loop, placed before the existing `ROUTING_HANDOFF_TABLES` loop | the U-A3 loop it mirrors, line 156 region |
| 15 | `tests/fixtures/v2_workspace.py` | fixture | (f) the same loop | line 179 region |
| 16 | `tests/fixtures/v3_workspace.py` | fixture | (f) the same loop | line 120 region |

The nine renames of classes (c) and (d), exhaustively (no other existing
method is renamed): `test_production_registry_is_the_four_production_steps`,
`test_no_version_six_transition_exists`,
`test_fresh_init_is_version_five_with_both_agent_tables`,
`test_registry_is_exactly_the_four_steps_in_order`,
`test_schema_stays_version_five`,
`test_schema_stays_5_and_migration_state_is_untouched`,
`test_schema_version_is_five`,
`test_registry_has_the_new_fourth_step_in_exact_order`,
`test_migration_status_and_plan_report_four_to_five`.

### 19.4 Paths deliberately NOT changed, with the reason

| Path | Why not |
| --- | --- |
| `agentic_os/workflow_engine.py` | the reducer is consumed byte-unchanged; any need to edit it is a replan |
| `agentic_os/workspecs.py`, `agentic_os/protocols.py`, `protocols/**` | no new seam and no protocol change; the store calls only existing public functions |
| `agentic_os/models.py` | `workflows` rows are returned as frozen store dataclasses, not `models` row objects, so the domain-vocabulary module keeps its single responsibility and gains no workflow enum it does not enforce |
| `agentic_os/ops.py`, `agentic_os/events.py` | `events.emit` is called unchanged; no task or run behavior moves |
| `agentic_os/doctor.py` | U-W2 §17: workflow integrity lives in `workflow verify`; folding it into doctor is a later unit's decision |
| `agentic_os/backup.py`, `export.py`, `mirror_export.py`, `obsidian.py` | none enumerates tables; the backup path copies the whole database file |
| `agentic_os/cli.py`, `agentic_os/power.py`, `README.md`, `tests/test_v04_workflow_cli.py` | U-W2.3 |
| `pyproject.toml` | `packages = ["agentic_os"]` already includes a new module; no dependency, no package data |
| `.github/workflows/ci.yml`, `tools/verify_ci_workflow.py`, `tests/test_v04_delivery_gate.py` | CI runs `python3 -m unittest discover -s tests` and `compileall` over the package; a new module and a new test module are discovered without a workflow edit |
| `tests/fixtures/FIXTURE_TABLES` | it enumerates tables whose CONTENTS a migration test compares before and after; the six new tables do not exist before |
| any new fixture module | the 5 → 6 equivalence test migrates `build_v3_workspace` forward, exactly as U-A3's 4 → 5 test does |

### 19.5 Architecture documents and delivery

The three Wave-0 documents are paths 17–19 of the exhaustive inventory:

| # | Path | Kind | Exact responsibility |
| --- | --- | --- | --- |
| 17 | `DECISIONS.md` | modified (document) | the prepended U-W2.2 Wave 0 section, D-v0.4.83–95; everything below the prepend stays byte-identical |
| 18 | `agentic-os-v0.4-u-w2-workflow-state-engine-contract.md` | modified (document) | U-W2 governed amendment A1, appended; the landed body byte-preserved as the file's exact prefix |
| 19 | `agentic-os-v0.4-u-w2-2-workflow-store-contract.md` | NEW (document) | this contract |

Delivery identity (per U-W2 amendment §A.6–§A.7, which supersede the
landed one-PR model already superseded in ratified practice):

- Branch: `v0.4-u-w2-2-workflow-store`
- PR title: `feat(v0.4): U-W2.2 — deterministic workflow persistence`
- Tag after merge: `milestone/v0.4-u-w2-2-workflow-store`
- Base: `63de8c953f2613a79d6e1bb6052646c669894863`
- Exactly two ordered commits inside the one U-W2.2 PR, through the U-P2
  gate: first `docs: adopt U-W2 path amendment and freeze U-W2.2 store
  architecture` — exactly paths 17–19; then `feat(v0.4): add
  deterministic workflow store` — exactly paths 1–16. No implementation
  path is staged before the documentation commit exists (the U-P2
  D-v0.4.50 landing model).
- Wave 0 itself stages nothing, commits nothing, and pushes nothing.

## 20. Exact test matrix (frozen)

`tests/test_v04_workflow_store.py`, rows S1–S24. Rows 15–20 of the landed
U-W2 §19 map onto S1, S4, S5, S10, S11, S13, S14, S15, S16, S21, S23; the
remainder are this slice's own discriminating obligations.

| # | Row | Discriminating assertion |
| --- | --- | --- |
| S1 | DDL and constraints | The six tables exist with exactly the §5 columns (`PRAGMA table_info`); every CHECK is exercised by a rejected direct INSERT — each of the thirteen `state` values accepted and a fourteenth rejected, `revision`/`policy_version`/`registry_version` `< 1` rejected, `approval_required` outside `(0,1)` rejected, each of the three `workflows` structural CHECKs rejected, `from_state = to_state` rejected, a non-`workflow_admitted` event with NULL `from_state` rejected and the converse rejected, `resulting_revision <> expected_revision + 1` rejected, a non-admit verb with `expected_revision = 0` rejected, each of the four receipt CHECKs rejected, the intent `resolved`/`resolved_receipt_id` biconditional rejected both ways, the fact scope biconditional rejected both ways, an unknown enum member rejected in every enum column, and each UNIQUE and FK violated and refused |
| S2 | Snapshot rebuild equals the seal | For a scripted journey through every reachable state, `_load_snapshot` reproduces `decision.snapshot_after` byte-identically, including `content_sha256`; the store's local sealer is pinned equal to the engine's output for every step |
| S3 | Identity rendering | `"WF-" + str(workflows.id)` equals `workflow_engine._workflow_identity(work_spec_sha256)` for a corpus of real digests; the renderer divergence is pinned on synthetic integers — `ids.render_id("workflow", 7) == "WF-0007"` while the store's renderer yields `"WF-7"` — and `render_id` is asserted unused by the module; `ids.PREFIXES` has no duplicate value |
| S4 | Fresh initialization | `db.init_db` creates all six tables; `sqlite_master.sql` for each equals `db.WORKFLOW_TABLES` DDL formatted with its real name; `meta.schema_version` is `"6"` |
| S5 | Migration 5 → 6 | The registry is exactly the five steps in order ending `(5, 6, "u-w2-workflow-state-v6")`; `LATEST_VERSION == int(db.SCHEMA_VERSION) == 6`; `status`/`plan` from a v3 fixture list all three pending steps; `apply_migrations` reaches 6; the step reads no existing row (`table_contents` before == after, `events`/`meta` excluded) and reads no clock (a patched clock is asserted uncalled by the step body); an injected mid-step failure rolls back all six tables and a retry succeeds |
| S6 | Fresh/migrated equivalence | `sqlite_master.sql` is BYTE-identical between a fresh v6 init and a `build_v3_workspace` migrated to v6, for all six tables; the three fixtures still build valid v1/v2/v3 workspaces (each asserted to lack all six tables); the receipt and event CHECK membership data-compares equal to the engine's `WORKFLOW_RECEIPT_KINDS`, `_RECEIPT_*` tuples, `WORKFLOW_EVENTS`, `WORKFLOW_STATES`, `WORKFLOW_COMMANDS` |
| S7 | End-to-end journeys | Admission → validate → (approval) → dispatch → accepted → started → wait → resumed → result, and the failure, rejection, revocation, local-cancel and two-phase-cancel journeys, each producing exactly the frozen events, revisions, intents, receipts and facts; no receipt-driven `submit` ever returns a non-`None` `intent` |
| S8 | `StoreOutcome` totality | Every §9 invariant holds for every status across the full journey corpus: the `replay` biconditional, the `reason`/`refusal` agreement, the conflict/refused partition, `intent is None` off the accepted path, `events == ()` on refusal, and the field table's per-status meanings |
| S9 | Envelope subset agreement | Over a frozen corpus of malformed envelopes, `_command_identity` and `decide` agree on accept/reject for `command_id`, `workflow_id`, verb membership and the self-digest, and disagree nowhere |
| S10 | Command replay and conflict | An exact duplicate returns `replay=True` with the ORIGINAL events and `resulting_revision`, no new event, no revision change, no new intent row and `intent is None`; a same-`command_id`/different-digest duplicate returns `conflict`/`command_conflict`; a duplicate of a REFUSED command re-refuses identically and stores nothing; a tampered cross-workflow `command_id` row returns `command_conflict` |
| S11 | Receipt replay and conflict | A redelivered receipt in a NEW envelope returns `replay=True` with the original command's events even though the workflow has advanced; the same `receipt_id` with a different digest returns `conflict`/`receipt_conflict`; a receipt whose stored row names another workflow returns `receipt_conflict`; `receipt_out_of_order`, `receipt_superseded`, `receipt_unbound`, `runtime_uuid_mismatch`, `approval_fact_missing` and `workflow_terminal` each refuse with nothing written |
| S12 | Transaction mode | `workflow_store.py` contains exactly one `conn.execute("BEGIN IMMEDIATE")`; it is the first statement inside the only `db.transaction` block; `verify`, `rebuild` and the four readers open no transaction and issue no write |
| S13 | Complete crash matrix | Every K0–K14 and KA0–KA8 point of §13, injected by the three §13.3 mechanisms (the nine mutation helpers; the `BEGIN IMMEDIATE`/dedupe-read/`_load_snapshot`/`decide`/task-read boundaries; the mid-`_insert_events` wrapper for K6), leaves the §13.3 invariant intact — six table counts unchanged, every `workflows` column byte-identical, no `events` row — and the retried command then succeeds with exactly the rows a clean run produces; K15/K16 assert the committed state and the still-`outstanding` outbox row |
| S14 | CAS and concurrency | A simulated concurrent writer that advances the revision between read and update makes the CAS lose cleanly with `revision_mismatch` and no partial state; two identical concurrent commands yield one write and one replay; two conflicting ones yield one write and one `revision_mismatch`; two commands carrying the same receipt yield one application and one replay; the intent-close CAS refuses a second close |
| S15 | History corruption | A deleted middle event, a tampered `payload_json`, a tampered `actor`, a tampered `from_state`, a tampered `command_sha256`, a tampered `policy_version = 2`, a non-text `payload_json` and a tampered stored body each produce their exact verdict (`history_corrupt`, `policy_version_unsupported`, `snapshot_divergence`); mutating commands refuse on each; read paths stay total and report `integrity` and `unreadable_seq`; the `UNIQUE(workflow_id, seq)` and `event` CHECKs are shown to make duplicate-seq and unknown-event unrepresentable |
| S16 | `verify` reports, never repairs | `verify` on a healthy corpus returns `integrity == "ok"` with empty `divergent_fields`/`divergent_rows`; on each tampered database it names the exact divergent field or `(table, row_id)`; before/after byte comparison of the whole database file shows `verify` changed nothing; `rebuild` returns `snapshot is None` exactly when `integrity != "ok"` |
| S17 | Hostile rows / raw exception closure | Over a matrix that tampers every column of all six tables (wrong type, NULL, oversized, non-canonical, BOM, duplicate keys, `INT_MAX` overflow, 257-element arrays), no public function raises `sqlite3.Error`, `ProtocolError`, `KeyError`, `TypeError`, `ValueError` or `AttributeError`; every call returns a `StoreOutcome`, a view with an integrity verdict, or a `WorkflowStoreError` with one of the three closed codes |
| S18 | SQL, message and text safety | AST scan: every `conn.execute` first argument is a literal or a constant built only from `db.*_TABLE`; no `DELETE`, `DROP`, `ALTER`, `ATTACH`, `PRAGMA`, `executescript`, `eval`, `exec`, `compile`, `__import__`, `importlib`, `subprocess`, `os.system` or `socket` appears. A credential-shaped value planted in every text column appears in no message, no `diagnostics` and no `events` row. Documents whose free text carries tool-invocation and scope-widening instructions produce byte-identical decisions to benign text |
| S19 | Caller mutation isolation | Mutating the submitted command document, or any returned `StoreOutcome` / view / snapshot / event / intent, after the call changes nothing stored and nothing later read; two successive reads return equal but non-identical structures |
| S20 | Task/run compatibility | Admission requires an existing, non-`done` task (`admission_task_unknown` / `admission_task_closed`); `_TASK_CLOSED_STATUS` is a `models.TASK_STATUSES` member and is what `ops.mark_done` sets; no workflow command changes any `tasks` or `runs` row (full before/after row comparison); `mark_done` still refuses zero-evidence completion; the store's SQL names no ledger table outside the six plus `tasks`, `meta` and `events` |
| S21 | No shared database | The module never calls `sqlite3.connect`, `db.connect`, `db.open_db`, `db.init_db`, `open`, or any `pathlib` constructor; it reads no environment variable; a filesystem-write spy over a full journey records zero writes outside the supplied connection |
| S22 | Clock freedom | The module imports neither `datetime` nor `time` and never calls `utils.utc_now_iso`; every one of the six tables' timestamp columns equals the command's `created_at`; running the same journey twice under different wall clocks produces byte-identical rows in all six tables |
| S23 | Exclusions are mechanical | The module contains no `while` loop, no `sleep`, and no recursive `submit`; `partial`/`unknown` results refuse with nothing written (no second attempt exists); `transition_reserved` is unreachable through the store because no stored `compensating` snapshot can be produced; no checkpoint, resume, compensation, monitor, interrupt or Temporal surface exists anywhere in the slice; nothing in the module writes a memory claim, a `.claude` path, or an Obsidian file |
| S24 | Reducer and vocabulary integrity | `WORKFLOW_STATES`, `WORKFLOW_COMMANDS`, `WORKFLOW_EVENTS`, `WORKFLOW_REFUSAL_REASONS` (43, in order), `WORKFLOW_RECEIPT_KINDS`, `WORKFLOW_INTENT_KINDS`, `RECEIPT_EVENTS`, `RECEIPT_TARGET_STATES`, `TRANSITION_MATRIX` (cell by cell), `TRANSITION_POLICY_VERSION == 1` and `SUPPORTED_POLICY_VERSIONS == (1,)` are unchanged from the landed engine; `workflow_store` adds no member to any of them; every DOCUMENT schema identity string it uses comes from a `workflow_engine` constant rather than a literal, the store never names `beast.result-envelope/v1`, and the four §5.8 row-hash `record_schema` identities are the module's own frozen constants; the module's own import statements match the §8.5 allowlist exactly (AST) |

## 21. Verification (implementation wave)

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q agentic_os tests tools aos.py aos_hooks.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_workflow_store
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_workflow_engine
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v02_migrations
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
python3 tools/gen_protocols.py
python3 tools/verify_ci_workflow.py
git diff --check
```

## 22. Known limitations (declared, not discovered later)

- **The landed U-W2 §18 path table for this slice was incomplete**, and
  the audited Wave 0 candidate's attempt to amend it from inside this
  subordinate contract was itself the replan trigger. The contradiction is
  resolved by U-W2 governed amendment A1, appended to the landed contract
  with its original body byte-preserved as the exact prefix (U-W2
  §A.1–§A.10); this contract's §19 restates the amended closed inventory
  and adds nothing to it.
- **`README.md` stays at its landed text until U-W2.3.** Its narrative
  describes schema version 5; between this slice's merge and U-W2.3's,
  that narrative is stale against the shipped `"6"`. `README.md` is
  U-W2.3's path (§19.4), and the window is declared here rather than
  discovered.
- **The `workflows` row cannot alone reconstruct the reducer's snapshot.**
  Seven derived fields come only from `fold(workflow_events)`, so a
  workflow whose history is damaged has no usable snapshot at all, not
  merely a stale one. That is the honest cost of keeping the row a
  projection, and it is why event retention is mandatory rather than
  advisory.
- **Every command reads the whole history of its workflow.** Cost grows
  linearly with a workflow's event count, which is bounded in practice by
  the lifecycle but not by any constraint. A workflow that oscillates
  `running → waiting_input → running` indefinitely will slow down. No
  cache, no incremental fold, and no compaction is frozen here; adding one
  is a later unit's decision and would need its own integrity argument.
- **A refusal leaves no trace in `aos.db` until U-W2.3 ships.** The store
  deliberately writes nothing on refusal so a journalled refusal cannot be
  rolled back with the work it declined; the observability row is the CLI
  shell's.
- **Row hashes bind `id`, so they are finalized by one in-transaction
  `UPDATE`.** That is the `routing_plans` precedent, and it means
  "immutable" for those three tables precisely means "immutable after its
  creating transaction commits".
- **Cancel intents can remain `outstanding` forever** (§16.2): the
  outbox-only intents of `revoke_dispatch` and pre-dispatch
  `request_cancel`, and a two-phase cancel intent stranded by a terminal
  race — a `failed` receipt, a `record_result`, or a unilateral
  `cancelled` receipt clears the pointer without naming the intent.
  Re-export is idempotent, but an operator reading the outbox will see
  them permanently.
- **`history_unknown_event` and duplicate-`seq` corruption are unreachable
  through this store** (§15.2). The codes remain in the vocabulary because
  `verify_history` is also callable on caller-supplied lists; this
  contract does not claim store-side tests for paths that cannot exist.
- **Agreement is not provenance.** A coherently spliced set of rows —
  every body, every digest, every row hash rewritten consistently — is
  indistinguishable from a legitimate write. The store's guarantee is that
  no PARTIAL tampering survives, and that a fully coherent forgery is a
  different workflow identity, not a corrupted one (§18.1).
- **`store_unavailable` is coarse.** A locked database, a missing file, an
  I/O error, and an unexpected constraint violation share one code,
  because distinguishing them would mean parsing SQLite message text into
  a message the house style forbids from carrying it.
- **The store never verifies that an exported intent was delivered.** It
  records only what the ledger learned. Delivery, leasing, attempts and
  worker liveness are the private runtime's; discovering that nothing is
  consuming the outbox is a human act until U-W4.
- **The task check remains admission-time only.** A human may close a task
  while its workflow is `running`; U-W2.2 neither prevents nor detects it
  (§17.2).

*This contract is the audit surface for U-W2.2: an implementation behavior
the sections above do not license is a defect, whichever file it lives in.*

---

# Agentic OS v0.4 — U-W2.2 governed contract addendum B1 (canonical workflow identity binding)

Appended, not merged. Every byte above this line is preserved verbatim as
this file's exact prefix (138,448 bytes, sha256 `261f4a82e721e8183336b30e
35139d8d1ceb3c02a6eba3f91a112cb8f365ccf7`, as committed at
`91075d7cb3b94013242b36c777baa59ee37500f9`).

B1 is the subordinate application of U-W2 governed contract amendment A2.
A2 is the authority; B1 quotes each superseded clause and states its
replacement, and adds nothing A2 does not authorise — exactly the
relationship §19 has to U-W2 §A.4. Where B1 and A2 could be read as
disagreeing, A2 governs and B1 is the defect.

Reading rule: a superseded clause stays where it is, byte-unchanged, and is
read THROUGH its replacement here. Nothing above this line is edited.

## B1.1 What this addendum is for

The U-W2.2 implementation wave reported `FAIL — REPLAN REQUIRED` on F-001:
§5.8 binds `workflow_id` as a direct integer, §5.1 makes that integer a
63-bit derived identity, and the frozen digest function refuses integers
above `protocols.INT_MAX` (2**53-1). The three clauses are mutually
unsatisfiable, ~99.9% of valid identities are affected, and the first
accepted `admit_work_spec` closes as `store_unavailable` with nothing
persisted. Full reproduction, evaluation of alternatives, and the
supersession authority: U-W2 §A2.1–§A2.3.

B1 also closes nine further contradictions and silences the same audit
confirmed, so the amendment resolves the wave at once rather than one round
per finding.

## B1.2 §5.8 — the canonical identity binding (supersedes S1)

**Superseded text**, §5.8, the row-hash convention sentence:

> a `record_schema` key, text fields bound by their `sha256` leaf, integers
> bound directly, `None` passed through, `content_sha256` excluded

and, in the §5.8 table, the `workflow_id` member of all four payload rows,
written there as part of "`id`, `workflow_id` (ints)".

**Replacement.** The convention is unchanged for every column except the
workflow identity. The workflow identity is not an ordinary integer column:
it is the reducer's derived identity, whose canonical representation is
frozen by U-W2 §A2.2 as the rendered string `"WF-" + str(workflows.id)`.
Being text, it binds like every other text column — by its sha256 leaf:

```text
"workflow_id_sha256": sha256(("WF-" + str(workflows.id)).encode("utf-8")).hexdigest()
```

The amended §5.8 payload table, in full:

| Table | `record_schema` | Bound members (in addition to `record_schema`) |
| --- | --- | --- |
| `workflow_commands` | `aos.workflow-command-row/v1` | `id`, `expected_revision`, `resulting_revision`, `event_seq_first`, `event_seq_last` (ints); `workflow_id_sha256`, `command_id_sha256`, `command_sha256_sha256`, `command_sha256` *(the verb string's leaf)*, `created_at_sha256` |
| `workflow_intents` | `aos.workflow-intent-row/v1` | `id` (int); `workflow_id_sha256`, `intent_id_sha256`, `intent_kind_sha256`, `idempotency_key_sha256`, `queue_route_sha256`, `document_sha256` *(recomputed digest of the stored document)*, `status_sha256`, `resolved_receipt_id_sha256` (nullable), `created_at_sha256` |
| `workflow_receipts` | `aos.workflow-receipt-row/v1` | `id` (int); `workflow_id_sha256`, `receipt_id_sha256`, `receipt_kind_sha256`, `intent_id_sha256` (nullable), `runtime_task_uuid_sha256` (nullable), `receipt_sha256_sha256`, `created_at_sha256` |
| `workflow_facts` | `aos.workflow-fact-row/v1` | `id` (int); `workflow_id_sha256`, `fact_kind_sha256`, `fact_scope_sha256` (nullable), `document_sha256_sha256`, `recorded_at_sha256` |

Unchanged by this addendum: the four `record_schema` identity strings; the
digest function `sha256(protocols.serialize_canonical(payload)).hexdigest()`;
`content_sha256` exclusion; `None` pass-through; the `command_sha256` /
`command_sha256_sha256` naming that avoids the leaf convention's one
collision; the in-transaction `UPDATE` finalization and its consequence for
what "immutable" means in §5.3, §5.5 and §5.6; and `verify` recomputing all
four (§15.4, as amended by §B1.7).

`workflows.content_sha256` and `workflow_events.content_sha256` remain the
CANONICAL RECORD digests, not row hashes, exactly as §5.8's first paragraph
states.

**Why the leaf and not the raw string:** §5.8's own convention, and both
live row-hash precedents (`routing.py`, `agent_handoffs.py`), bind text by
leaf. One raw text member would be a second deviation from the convention
inside the very clause being repaired. **Why the rendered string and not
the bare decimal:** `WF-<n>` is the identity the architecture already
freezes in five places; `<n>` is an implementation detail of it, and
freezing two spellings reintroduces the ambiguity this amendment removes.

## B1.3 §5.1 — `workflows.id` gains one CHECK (supersedes S6)

**Superseded text**, §5.1, the DDL's first column line:

> ```sql
> id INTEGER PRIMARY KEY,
> ```

**Replacement:**

```sql
id INTEGER PRIMARY KEY CHECK (id >= 1),
```

That is the ONLY change to the `workflows` DDL. Every other column, CHECK,
UNIQUE, and FOREIGN KEY is byte-unchanged, and no other table's DDL
changes.

§5.1 already declares the invariant — the identity "always lies in
`[1, 2**63-1]` = `ids.MAX_ID`" — while the DDL left it unenforced, unlike
the three sibling `>= 1` CHECKs in the same table (`registry_version`,
`revision`, `policy_version`). A `workflows.id = 0` planted by direct SQL
was a confirmed source of a leaked `AosError` at a public boundary. The
CHECK makes the declared invariant structural.

The CHECK does NOT replace failing closed. A row can still arrive from a
restored backup, from a build without constraint enforcement, or from a
direct file write, so `_req_row_id`'s `1 <= value <= ids.MAX_ID` bound and
every path that maps an unreadable row to a closed verdict are retained
exactly. Storage enforcement and code totality are independent, and the
amended §20 row S25 requires both.

Migration consequence: the 5 → 6 step composes its DDL from
`db.WORKFLOW_TABLES`, so the constraint reaches fresh and migrated
databases through the one enumeration, and §20 row S6's byte-identity
between a fresh v6 and a migrated v3 continues to hold with no additional
step. No existing row anywhere can violate it: the six tables do not exist
before version 6.

## B1.4 §7.2 — the identity comparison is a declared backstop (supersedes S2)

**Superseded text**, §7.2 step 6:

> every OTHER member-backed projection column — seventeen: `id` (as
> `workflow_id`), `task_id`, …

**Replacement.** Step 6 compares SIXTEEN live member-backed projection
columns — `task_id`, `work_spec_sha256`, `report_sha256`,
`snapshot_sha256`, `registry_version`, `compile_status`, the two document
bodies, `state`, `revision`, `policy_version`, `approval_required`,
`dispatch_intent_id`, `cancel_intent_id`, `runtime_task_uuid`,
`queue_route` — plus the sealed-digest comparison, under the conversions
§7.2 already declares.

`id` (as `workflow_id`) is retained in the gate as a DECLARED REDUNDANCY
BACKSTOP and is not a live check. It cannot diverge by construction: §7.4
reconstitutes each event record's `workflow_id` FROM this same column, so
`fold` returns exactly what the column supplied and the comparison is
`"WF-" + str(id)` against `"WF-" + str(id)`. It is retained so that a
future change to §7.4's reconstitution is still caught, and it must be
labelled as a backstop wherever it appears so it is never again read as the
identity's protection.

**The identity's real integrity binding is §7.4, unchanged:** the sealed
`aos.workflow-event/v1` digest covers `workflow_id` and
`work_spec_sha256`, so a spliced `workflows.id` makes every event digest
fail to recompute and the workflow reads `history_corrupt` rather than
folding under a false identity. Since §B1.2 the identity is additionally
bound into all four row hashes — a second independent binding the frozen
text did not previously have in any satisfiable form.

## B1.5 §8.4 — the exhaustive `store_unavailable` trigger table (supersedes S3)

**Superseded text**, §8.4, the `store_unavailable` row:

> any `sqlite3.Error` the store did not deliberately map — … — plus the one
> deliberate non-exception trigger: an intent-close CAS whose rowcount is
> not 1 (§12.2, a damaged outbox)

**Replacement.** `store_unavailable` has exactly these triggers, and the
enumeration is exhaustive:

| # | Kind | Trigger |
| --- | --- | --- |
| 1 | `sqlite3.Error` | any `sqlite3.Error` the store did not deliberately map — a locked, missing, or damaged database file, an I/O failure, or a constraint violation outside the one mapped `workflows` INSERT |
| 2 | deliberate, non-`sqlite3` exception | a `_RowUnreadable` or `protocols.ProtocolError` raised while building a §5.8 row-hash payload for hash finalization, or while rebuilding an intent's payload to close it — a row the ledger itself produced that can no longer be read is a damaged ledger, not a caller error, and the private `_RowUnreadable` must not cross the public boundary (§18.4) |
| 3 | non-exception | an intent-close CAS whose rowcount is not 1 (§12.2, a damaged outbox) |
| 4 | non-exception | the row just INSERTed is not readable back for its hash finalization |
| 5 | non-exception | an intent named by an emitted event has no row (a damaged outbox) |
| 6 | non-exception | a stored receipt has no event naming it, so its replay has no answer (a damaged inbox; §5.5 makes a stored receipt an APPLIED receipt) |

Counted by raise site rather than by trigger class, `workflow_store.py`
raises `store_unavailable` at exactly ten sites: four under trigger 1, two
under trigger 2, and one each under triggers 3–6. Triggers 3–6 are the four
deliberate NON-EXCEPTION triggers, where the superseded text claimed one;
trigger 2 is a deliberate mapping of an exception that is not a
`sqlite3.Error`, a class the superseded text did not mention at all. §20
row S28 pins the classification and the site count, so a new raise site
cannot appear without failing a test.

All six are ledger facts, never facts about a workflow, so none enters the
frozen 43-member refusal vocabulary and none is reachable by any
caller-supplied document alone — each requires a ledger that is already
damaged.

§22's "`store_unavailable` is coarse" limitation is unchanged and now
covers six triggers rather than two.

## B1.6 §13.3 — the fourth frozen injection mechanism (supersedes S4)

**Superseded text**, §13.3:

> Injection is by three frozen mechanisms, together covering every
> enumerated point: (i) … (ii) … (iii) …

**Replacement.** Injection is by FOUR frozen mechanisms, which together
cover every enumerated point:

```text
(i)   patching one of the nine named mutation helpers — `_insert_workflow`,
      `_insert_command`, `_insert_events`, `_insert_intent`,
      `_resolve_intent`, `_insert_receipt`, `_insert_fact`,
      `_cas_snapshot`, `_journal` — for K5, K7-K12, K14, and KA3-KA8
(ii)  patching the transaction entry and the pre-mutation boundaries — the
      `BEGIN IMMEDIATE` statement, the C2/A2 dedupe read, `_load_snapshot`,
      `workflow_engine.decide`, and the A3 task read — for K0-K3 and
      KA0-KA2
(iii) a wrapper on `_insert_events` that raises between the first and
      second row inserts of a two-event command, for K6
(iv)  a wrapper on a NAMED INTERNAL CALLEE of a mutation helper, which
      raises after the helper's own write and before the helper returns:
      `_row_digest` for K4 (inside `_insert_command`, after its INSERT and
      before its row-hash finalization) and `events.emit` for K13 (inside
      `_journal`, after the first of two emit calls) and for KA8 (inside
      `_journal`, after admission's single emit call). The two callee names
      are frozen architecture for this purpose, exactly as the nine helper
      names are.
```

Mechanism (iv) exists because (i) cannot express those points. Patching a
named helper raises BEFORE the helper does anything, which is the point
before it, not a point inside it — K4 would collapse into "before
`_insert_command`", and K13 and KA8 into "before `_journal`" (which are
K12 and KA7). The crash POINTS of §13.1 and §13.2 are unchanged; only the
mechanism enumeration is repaired, and the §13.3 invariant every point must
satisfy is unchanged.

**Point/label discipline.** Every point named by §13.1 and §13.2 is
injected at its own instant, under its own label, by exactly one frozen
mechanism, and no two labels share an instant. Three consequences for the
acceptance tests, each a correction rather than a new obligation:

```text
KA7  "after `_insert_events`, before `_journal`" IS the `_journal`-entry
     injection by mechanism (i); it must carry the KA7 label
KA8  "inside `_journal`" needs mechanism (iv), and must be exercised
KA1  "after A3 task read, before A4" needs an AFTER-wrapper on the task
     read, not an entry patch — an entry patch is the instant before A3
K12  a `_journal`-entry injection on a receipt-bearing command is K12,
     not a second K13
```

KA4 ("inside `_insert_workflow`, before its `content_sha256` is written")
remains as §13.2 states it, and is proven the way §13.2 already states the
outcome — the column has no default, so a hashless row is unrepresentable
and the acceptance test asserts no row survives at all. That is the
invariant, not a weaker substitute for it.

## B1.7 §15.4 and §8.3 — the exact scope of each integrity verdict (supersedes S7, S9)

**Superseded text**, §15.4 step 4:

> recompute the four §5.8 row hashes for every command, intent, receipt and
> fact row of the workflow → `divergent_rows`

and, §8.3, `read_workflow` / `list_workflows`, "plus an integrity verdict"
read as an unscoped claim; and §18.1's "at every use" as applied to
`workflow_receipts.receipt_sha256` and `workflow_facts.document_sha256`.

**Replacement — §15.4 step 4:** recompute the four §5.8 row hashes for
every command, intent, receipt and fact row of the workflow, AND re-digest
the two stored documents whose digests those row hashes bind only by column
leaf — `workflow_receipts.document` against `receipt_sha256`, and
`workflow_facts.document` against `document_sha256` — reporting either
failure as `(table, row_id)` in `divergent_rows`.

That second half is not optional detail. §5.8 binds those two digest
COLUMNS by leaf, so rewriting `workflow_facts.document` alone leaves every
row hash recomputing: without the document re-digest a forged body reports
`integrity == "ok"`, which was confirmed by reproduction. §18.1's promise
that a substituted body without every covering digest yields a reported
divergence is what this step makes true for those two tables.

**Replacement — the scope of each verdict.** These are different verdicts,
deliberately, and each is now stated:

| Surface | Covers | Does NOT cover |
| --- | --- | --- |
| `read_workflow`, `list_workflows` (`integrity`) | §7.2 steps 1–5 (history reconstitution, `verify_history`, `fold`, splice, seal) and step 6's sixteen live comparisons, INCLUDING the §15.4 step 5 re-digest of both stored bodies against the `workflow_admitted` payload | the four §5.8 row hashes; the two document-bound digests of step 4 |
| `submit` (the §7.2 write gate) | exactly the same set | exactly the same set |
| `verify` (`VerifyReport`) | everything above, PLUS §15.4 step 4 in full | — |

**§15.3's "Mutating commands refuse" is scoped to this same verdict.** A
workflow whose ONLY damage is a divergent row hash or a forged receipt or
fact body still accepts commands, and that is deliberate, not an oversight.
The four row-hash tables feed no acceptance decision: command dedupe
compares a RECOMPUTED envelope digest against `command_sha256`, receipt
dedupe compares a RECOMPUTED receipt digest against `receipt_sha256`,
replayed events come from the re-verified history (§B1.8), and a fact body
is recorded by the event's own sealed digest. Freezing mutations on them
would deny service without protecting a single decision, while §3's
guarantee — as scoped by §B1.8 — continues to hold under rows-only
tampering. §20 row S30 requires that to be proven over the tamper corpus,
not assumed.

`verify` is therefore the only TOTAL integrity surface, which is what
U-W2 §17 already settled ("workflow integrity lives in `workflow verify`").
The readers and the write gate are not widened: `list_workflows` is a
declared full scan (§8.3), and recomputing every row hash and every stored
document inside it would make listing the ledger an O(total rows) integrity
sweep of it, while the same work on the §7.2 gate would put it on every
command and falsify §7.2's declared cost. A `read_workflow` reporting `ok`,
and a `submit` accepting, while `verify` reports `snapshot_divergence` with
non-empty `divergent_rows` is therefore correct, declared, and pinned by
§20 row S29 — not a divergence.

`workflow_intents.document` needs no separate step: §5.8 binds it as the
RECOMPUTED digest of the stored document, so an intent's row hash already
fails on a forged body.

## B1.8 §14.2, §3 — replay verification and the scoped worst case (supersedes S8, S5)

**Superseded text**, §14.2, first bullet:

> **Exact duplicate** — same `command_id`, recomputed digest equal, same
> `workflow_id`: returns the ORIGINAL outcome.

**Replacement.** Same `command_id`, recomputed digest equal, same
`workflow_id`, AND the workflow PASSES the §7.2 gate as scoped by §B1.7:
returns the ORIGINAL outcome, with everything else in that bullet
unchanged. Otherwise the replay REFUSES with the exact verdict
(`history_corrupt`, `history_unknown_event`, `policy_version_unsupported`,
or `snapshot_divergence`), returns no events, and writes nothing.

A replay is a mutating command's ANSWER, and §15.3 refuses mutating
commands on a workflow that fails verification, so a replay is held to the
SAME gate a fresh command is held to — not a weaker one. Returning stored
events from an unverified workflow would hand a caller records from a
damaged ledger under an `accepted`-class status.

Verifying the history alone is NOT sufficient, and the distinction is
reproducible: a workflow with an intact history and a tampered projection
refuses a fresh command with `snapshot_divergence` while a duplicate of an
already-accepted command would still replay. The whole history is therefore
reconstituted, `verify_history`-checked, folded, spliced, sealed and
compared against the projection BEFORE the recorded
`[event_seq_first, event_seq_last]` range is sliced out of the verified
records. The identical rule applies to the receipt-replay path of §11.2 and
§14.3.

Idempotence is unaffected where it was promised: on a healthy ledger a
duplicate still returns the original outcome, `decide` is still never
called, and no event, revision, or intent row is produced.

**Superseded text**, §3, final bullet:

> no tampered row can make the store ACCEPT a command it would otherwise
> refuse, because every gate re-derives from bytes the same row supplies

**Replacement.** No tampered row IN THE SIX WORKFLOW TABLES can make the
store accept a command it would otherwise refuse, because every gate
re-derives from bytes the same row supplies and the reducer re-runs the
full admission gate on the stored artifact. A tampered workflow row can
only move a workflow from `ok` to a reported integrity failure, which
freezes its mutations (§15.3).

The guarantee is explicitly NOT extended to `tasks.status`. §4.2 and §9.5
make `AdmissionFacts(task_exists, task_open)` the store's shell-verified
input by design — the store supplies the facts and the reducer decides, and
the store has nothing to re-derive `tasks.status` from. Reproduced:
flipping `tasks.status` by direct SQL turns
`refused / admission_task_closed` into `accepted` for a byte-identical
envelope. That is the task plane's trust boundary, not a store defect, and
§17 already places task-status authority outside this slice. It is declared
here rather than discovered later, and pinned by §20 row S30.

## B1.9 Closed silences (C1–C4)

Frozen behavior, previously unlicensed:

**C1 — a workflow identity with no row.** For a well-formed `WF-<n>` that
names no `workflows` row:

```text
read_workflow  -> None
read_history   -> HistoryView(workflow_id, events=(), integrity="ok",
                              unreadable_seq=None)          [already §8.3]
verify         -> ()   (no report is fabricated for a workflow that
                        does not exist; verify(None) likewise omits it)
rebuild        -> RebuildResult(workflow_id, snapshot=None,
                                integrity="history_corrupt",
                                reason="workflow_unknown",
                                where="/workflow_id")
```

`rebuild`'s `integrity` is `history_corrupt` because `STORE_INTEGRITY` is
the frozen five-member vocabulary of §8.1 and has no "no such workflow"
member, while §8.3's invariant requires a non-`ok` verdict whenever
`snapshot is None`. The PRECISE verdict is carried by `reason`, which is
`workflow_unknown` — a member of the frozen 43-reason vocabulary. Widening
`STORE_INTEGRITY` would change a public vocabulary for one case and is
rejected; the pair `(integrity, reason)` is total and unambiguous as
frozen here.

**C2 — rows-only divergence.** When `divergent_fields` is empty and
`divergent_rows` is not, a `VerifyReport` carries
`integrity="snapshot_divergence"`, `reason="snapshot_divergence"`, and
`where="/rows"`. When both are non-empty, `where` names the first divergent
FIELD. `"/rows"` is a schema-safe fixed token, never a table name, a row
id, or a value.

**C3 — the closed-task status constant.** §10.4 freezes the VALUE
(`_TASK_CLOSED_STATUS = "done"`). The store derives it as
`models.TASK_STATUSES[-1]` rather than typing the literal, so it cannot
drift from the task plane's one declaration. The two are consistent today,
and because a positional derivation would silently change meaning if a
status were ever appended, §20 row S20 pins it three ways — that it equals
`"done"`, that it is a `models.TASK_STATUSES` member, and that it equals
the value `ops.mark_done` writes. An appended status therefore fails a test
rather than silently redefining "closed". This is a clarification of a
frozen value, not a change to it.

**C4 — the snapshot on a refusal.** §9.3's "the CURRENT snapshot when the
workflow exists and its history verifies, else `None`" is exact and
unchanged; it is restated here because it was read as ambiguous: a refusal
on a workflow whose history does NOT verify carries `snapshot=None` and
`revision` from the stored column when it is readable, never a partial or
rebuilt-from-damaged snapshot.

## B1.10 §20 — frozen additional test rows

Rows S1–S24 are unchanged in intent. Row S1 additionally exercises the new
`workflows.id` CHECK; row S13 additionally uses mechanism (iv); rows S16
and S20 are unchanged in wording and pinned more strictly below. The
following rows are added and are as frozen as S1–S24.

| # | Row | Discriminating assertion |
| --- | --- | --- |
| S25 | Canonical identity binding over the full domain | The frozen representation is total and sealable across the whole positive 63-bit domain: for the minimum identity `1`, for `protocols.INT_MAX`, for `protocols.INT_MAX + 1`, and for `ids.MAX_ID`, `"WF-" + str(n)` is canonical, at most 22 characters, `ids.parse_id`-round-trips to `n`, and a §5.8 payload carrying its leaf serializes and digests; the SAME payload with `workflow_id` bound as a direct int is proven to raise `ProtocolError[integer_out_of_range]` for every value above `protocols.INT_MAX`, which is the F-001 contradiction pinned as an executable fact; the leaf is asserted to be `sha256("WF-" + str(n))` and NOT `sha256(str(n))`, so neither the superseded direct binding nor the wave's unauthorised decimal form can return silently |
| S26 | All four row hashes bind the same representation | For a journey that writes a command, an intent, a receipt and a fact, all four §5.8 payloads carry `workflow_id_sha256` with the identical value, no payload carries a `workflow_id` member, each payload's member set equals the §B1.2 table exactly, and every stored `content_sha256` recomputes; a real above-`INT_MAX` identity is used, which is the ordinary case |
| S27 | The identity's real binding is the sealed event digest | Splicing `workflows.id` to another value makes every event digest fail and the workflow reads `history_corrupt`, not a silent fold under a false identity; the §7.2 step-6 identity comparison is asserted to be the declared backstop — it cannot diverge while §7.4 reconstitutes from the same column — so the test discriminates §7.4's binding, not the tautology |
| S28 | `store_unavailable` triggers are exactly the six | Each of the six §B1.5 triggers is exercised or proven, each closes as `WorkflowStoreError("store_unavailable")` with a value-free message, and no `_RowUnreadable`, `ProtocolError`, or `sqlite3.Error` escapes any public function on any of them; an AST census of `workflow_store.py` asserts exactly ten `WorkflowStoreError("store_unavailable")` raise sites, so a new trigger cannot appear undeclared |
| S29 | Read, write-gate and `verify` scopes are exactly as declared | On a forged `workflow_facts.document` and on a tampered row `content_sha256`, `verify` reports `snapshot_divergence` with the exact `(table, row_id)` in `divergent_rows`, `read_workflow` and `list_workflows` report `ok`, AND a following legitimate command is still ACCEPTED — the declared §15.3 scope; on a body substitution and on a tampered projection column all three report `snapshot_divergence` and the command refuses; rows-only divergence carries `where == "/rows"` (C2) |
| S30 | The worst-case guarantee, scoped | No tampered row in the six workflow tables turns a refusal into an acceptance across the tamper corpus, INCLUDING the rows-only tampering S29 shows does not freeze mutations; `tasks.status` is shown to be the declared exception — the same envelope refuses `admission_task_closed` with the task closed and is accepted with it open — and the declaration is asserted to be exactly that one input |
| S31 | Replay is held to the full write gate | An accepted command whose history is then tampered replays as `refused` with the exact history verdict and `events == ()`; an accepted command whose PROJECTION alone is then tampered likewise replays as `refused` with `snapshot_divergence`, agreeing with what a fresh command does on the same database; both hold for the command-replay and receipt-replay paths; nothing is written; and on a healthy ledger the duplicate still returns the original outcome unchanged |
| S32 | The closed silences are the frozen behavior | C1's four surfaces on a nonexistent workflow return exactly the frozen values, including `rebuild`'s `(integrity="history_corrupt", reason="workflow_unknown", where="/workflow_id")` pair; C3's constant equals `"done"`, is a `TASK_STATUSES` member, and equals what `ops.mark_done` writes; C4's refusal on an unverifiable history carries `snapshot is None` |
| S33 | Crash points, labels and mechanisms agree | Every K0–K14 and KA0–KA8 label is injected at its OWN instant by exactly one §B1.6 mechanism and no two labels share an instant: K4 and K13 and KA8 by mechanism (iv), K6 by (iii), KA1 by an after-wrapper on the A3 task read, KA7 by the `_journal`-entry patch under its own label, and K12 by the `_journal`-entry patch on a receipt-bearing command; the set of exercised labels equals the §13.1/§13.2 enumeration exactly |

## B1.11 Frozen mutations

Every claim B1 repairs must be killed by a named test in the consolidated
mutation campaign, alongside the campaign's existing categories:

```text
M-A  workflow_id_sha256 leaf built from str(id) instead of "WF-" + str(id)
M-B  workflow_id bound as a direct int in any of the four payloads
M-C  the workflows.id >= 1 CHECK removed from the DDL
M-D  the §7.4 event-record workflow_id sourced from anything but the column
M-E  verify's document re-digest of receipts/facts removed
M-F  any one of the six store_unavailable triggers softened or removed
M-G  _verified_range's whole-history verification removed before slicing
M-H  _verified_range's projection-gate comparison removed, leaving the
     history-only check the wave shipped
M-I  the intent-close CAS rowcount guard relaxed
M-J  _TASK_CLOSED_STATUS pointed at a different TASK_STATUSES member
M-K  rows-only divergence reporting "ok" instead of snapshot_divergence
```

## B1.12 §19.5 — delivery identity (supersedes S10)

**Superseded text**, §19.5:

> Exactly two ordered commits inside the one U-W2.2 PR, through the U-P2
> gate: first `docs: adopt U-W2 path amendment and freeze U-W2.2 store
> architecture` — exactly paths 17–19; then `feat(v0.4): add deterministic
> workflow store` — exactly paths 1–16.

**Replacement.** Exactly THREE ordered commits inside the one U-W2.2 PR,
through the U-P2 gate:

```text
1  91075d7cb3b94013242b36c777baa59ee37500f9
   docs: adopt U-W2 path amendment and freeze U-W2.2 store architecture
   exactly paths 17-19 — ALREADY LANDED, never rewritten
2  docs(v0.4): amend U-W2.2 workflow identity binding
   exactly paths 17-19 again — D-v0.4.96, U-W2 amendment A2, this addendum
3  feat(v0.4): add deterministic workflow store
   exactly paths 1-16
```

Branch, PR title, tag, and base are unchanged. No implementation path is
staged before commit 2 exists.

## B1.13 Path scope — unchanged

B1 adds no path. The inventory is the closed nineteen paths of §19 and
U-W2 §A.4, unchanged in membership. A twentieth path is
`FAIL — REPLAN REQUIRED`. B1 grants no standing authority and licenses no
future quiet extension of §5.8, of the row-hash convention, of the identity
representation, or of the path set.

## B1.14 §22 — additional known limitations (declared, not discovered later)

- **Neither the readers nor the write gate recompute row hashes or the two
  document-bound digests.** Their verdict is the snapshot-and-history one
  (§B1.7). A ledger whose only damage is a forged receipt or fact body, or
  a tampered row `content_sha256`, reads `ok`, keeps accepting commands,
  and verifies `snapshot_divergence`. Those rows feed no acceptance
  decision, so nothing is decided on damaged data; what is lost is prompt
  DETECTION, until someone runs `workflow verify`. That is the declared
  cost of keeping a declared full scan a scan and the §7.2 gate one range
  read, and U-W2.3's CLI is expected to say so where it displays a read
  verdict.
- **`tasks.status` is trusted verbatim.** It is the store's shell-verified
  admission input by design (§4.2, §9.5, §B1.8). Anything with write
  access to the `tasks` table can flip an admission decision. The task
  plane's integrity is the task plane's.
- **The identity binds by leaf, so a row hash names no identity in the
  clear.** Recomputation compares leaves; a reader cannot read the
  workflow identity out of a row-hash payload. That is true of every text
  column under §5.8's convention and is stated here because the identity
  is the one such column a human might expect to read.
- **`workflows.id >= 1` is enforced by SQLite, and SQLite constraint
  enforcement can be disabled.** The CHECK is defence in depth over a code
  path that already fails closed; it narrows the hostile-row surface and
  does not eliminate it (§B1.3).
- **Four mutation-helper injection points needed a fourth mechanism.**
  K4 and K13 are reachable only by wrapping a named internal callee
  (§B1.6). A future helper whose interesting crash point is likewise
  mid-body will need its callee frozen the same way, by amendment.

## B1.15 Verification of this addendum

1. The bytes above the B1 heading equal the file at `91075d7…`
   (sha256 `261f4a82…`, 138,448 bytes).
2. Every superseded clause S1–S10 is quoted here with a replacement, and
   no clause outside S1–S10 and C1–C4 is superseded.
3. The frozen representation is total over `[1, 2**63-1]`, proven by
   S25 rather than asserted.
4. The path inventory is unchanged at nineteen; no twentieth path exists.
5. `agentic_os/workflow_engine.py` and `agentic_os/workspecs.py` are
   byte-identical to their landed bytes.
6. D-v0.4.96 is the only new decision, contiguous and unique.

*This addendum joins §1–§22 as the audit surface for U-W2.2: an
implementation behavior neither licenses is a defect, whichever file it
lives in.*
