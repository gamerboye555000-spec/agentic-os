# Agentic OS v0.4 — U-W2: deterministic workflow state engine (Wave 0 architecture freeze)

Architecture freeze only. Baseline
`0a69a1c1654671cd48577e23252a9c06e2cffba9` (U-W1 deterministic WorkSpec
compiler merged, ledger schema version `"5"`, milestone
`milestone/v0.4-u-w1-workspec-compiler`; HEAD, `origin/main`, and the
merge-base are this same commit). Branch `v0.4-u-w2-workflow-state-engine`;
worktree `/home/daksh/Projects/agentic-os-u-w2`; primary checkout
`/home/daksh/Projects/agentic-os`. Future PR title:
`feat(v0.4): U-W2 — deterministic workflow state engine`. Future tag:
`milestone/v0.4-u-w2-workflow-state-engine`. Decisions: D-v0.4.71 –
D-v0.4.82.

U-W2 is the runtime half of the workflow story that can be built honestly
today: a deterministic, pure workflow state engine over admitted
`beast.work-spec/v1` artifacts, a local append-only workflow ledger with a
derived snapshot and revision compare-and-swap, and a transport-neutral
queue handshake expressed as typed intent and receipt records. It executes
nothing, retries nothing, compensates nothing, and grants nothing. This
document freezes the architecture; a later wave implements it. The
implementation and tests must mechanically agree with this document — a
sentence here that the code cannot demonstrate is a defect in one of the
two.

Extends: the U-X1 protocol spine
(`agentic-os-v0.3-u-x1-protocol-spine-contract.md`), the U-K1/U-T1 governed
foundations contract
(`agentic-os-v0.4-u-k1-u-t1-governed-foundations-contract.md`), and the
U-W1 compiler contract
(`agentic-os-v0.4-u-w1-workspec-compiler-contract.md`). Delivery flows
through the U-P2 gate (`agentic-os-v0.4-u-p2-delivery-gate-contract.md`, as
amended by `agentic-os-v0.4-u-p2-trust-boundary-amendment.md`).

## 0. Scope

### 0.1 In scope (frozen here, implemented in later waves of this unit)

- One new standard-library-only pure module,
  `agentic_os/workflow_engine.py`: the closed lifecycle vocabulary, the
  complete transition matrix as data, the closed command/event/refusal
  vocabularies, the typed command envelope, the pure reducer
  (`decide(snapshot, command, facts)`), pure history fold and verification
  (`fold(events)`, `verify_history(events)`), WorkSpec admission
  verification, approval-fact and result-envelope fact verification, and
  the deterministic queue intent/receipt record shapes with their derived
  identifiers.
- One new persistence module, `agentic_os/workflow_store.py`: the SQLite
  shell that loads snapshots, verifies ledger-resident facts, commits one
  accepted command per transaction under revision compare-and-swap, appends
  workflow events, writes the outbox/inbox rows, and journals through
  `events.emit`.
- Schema version `"6"`: six new tables in `agentic_os/db.py` and one purely
  additive migration `u-w2-workflow-state-v6` (5 → 6) in
  `agentic_os/migrations.py`, the U-A3 4 → 5 idiom applied again (empty
  tables, FK-parent-first, no rebuild, byte-identical to a fresh init).
- One new ledger ID prefix in `agentic_os/ids.py`: `"workflow": "WF"`.
- A public acceptance seam in `agentic_os/workspecs.py`:
  `accept_work_spec(artifact)` and
  `accept_compile_report(report, artifact_digest)`, thin public wrappers
  over the existing private `_accept_workspec` / `_accept_report` gates —
  behavior-identical, no logic change, pinned by test.
- CLI verbs under one new `aos workflow` group in `agentic_os/cli.py` with
  matching `power.COMMAND_POLICY` entries in `agentic_os/power.py` (§16).
- Focused tests: `tests/test_v04_workflow_engine.py`,
  `tests/test_v04_workflow_store.py`, `tests/test_v04_workflow_cli.py`
  (§19).
- `DECISIONS.md` (prepended D-v0.4.71–82, this wave) and `README.md` (one
  new unit section, implementation wave).
- One explicit cross-repository slice, U-W2.R (§18): the queue adapter in
  the private `ai-company-runtime` repository that consumes
  `aos.workflow-queue-intent/v1` records and produces
  `aos.workflow-queue-receipt/v1` records against its own Postgres queue.
  It is named here so it cannot hide inside one worktree; it ships through
  that repository's own delivery process and is NOT part of the agentic-os
  PR.

### 0.2 NOT in scope (mechanically absent, not merely discouraged)

- No retry loop of any kind (U-W3). `record_result` accepts `success` and
  `fail` outcomes only; `partial`/`unknown` refuse as
  `result_outcome_inconclusive` and mutate nothing.
- No checkpoint or resume implementation (U-W3). `paused → running` and
  `waiting_* → running` record verified runtime receipts; no state capture
  or restoration machinery exists.
- No compensation execution (U-W3). The `compensating`/`compensated`
  vocabulary and their matrix edges are frozen but refuse under
  transition-policy version 1 with `transition_reserved`.
- No loop-health monitor (U-W4), no semantic interrupt kernel (U-W5), no
  Temporal or other durable-engine adoption (U-W6 is a future trigger).
- No tool, skill, model, or agent execution: `governance.invoke()` is never
  called, no `BindingRegistry` callable is touched, no subprocess, no
  network, no MCP, no A2A.
- No approval or policy grant: U-W2 records externally issued approval
  facts and judges nothing about approver authority; no field anywhere in
  this unit can state "approval granted" as U-W2's own claim.
- No credential selection, storage, or use; no budget reservation or
  spend.
- No cross-cloud or cross-cluster failover.
- No queue implementation: no Postgres, no lease, no worker, no heartbeat,
  no transport (HTTP, socket, file watcher) in agentic-os. Records cross
  the boundary as files fed to explicit CLI verbs in wave 1.
- No shared database: agentic-os never opens the runtime's database and
  the runtime never opens `aos.db`; the six new tables live in `aos.db`
  only.
- No protocol change: `beast.work-spec/v1` and the other five registry
  identities are reused exactly as shipped; `agentic_os/protocols.py` and
  `protocols/**` are untouched; the new record schemas are `aos.*`
  canonical records (§7, D-v0.4.73).

### 0.3 Untouched

`agentic_os/protocols.py`, `protocols/**`, `agentic_os/governance.py`,
`agentic_os/models.py`, `agentic_os/passports.py`, `agentic_os/catalog.py`
and `agentic_os/catalog/*`, `agentic_os/routing.py`,
`agentic_os/agent_handoffs.py`, `agentic_os/secretscan.py`,
`agentic_os/doctor.py`, `agentic_os/hooks.py`, `agentic_os/ingest.py`,
`agentic_os/events.py`, `agentic_os/ops.py`, all delivery-control files
(`.github/workflows/ci.yml`, `tools/verify_ci_workflow.py`,
`tests/test_v04_delivery_gate.py`), `pyproject.toml`, every existing test,
and every existing fixture. `agentic_os/workspecs.py` receives ONLY the two
public wrappers named in §0.1. Existing artifacts remain valid without
edits.

## 1. Decisions (index)

- **D-v0.4.71** — workflow ownership outcome B: the authoritative workflow
  lifecycle lives in agentic-os as a public deterministic kernel; queue
  integration is a transport-neutral record contract; the runtime-side
  adapter is an explicit cross-repository slice in `ai-company-runtime`.
  A and C rejected for stated reasons (§4).
- **D-v0.4.72** — lifecycle vocabulary: thirteen authoritative U-W2 states;
  `proposed` remains pre-compile authoring plane; four terminal states are
  immutable; the complete matrix is frozen as data; `compensating` edges
  are policy-frozen but command-refused under transition-policy v1
  (`transition_reserved`), the `LOCAL_TERMINATION_OUTCOMES` idiom (§5).
- **D-v0.4.73** — closed command (9), event (17), refusal (43), intent-kind
  (2), and receipt-kind (9) vocabularies; the command envelope's required
  identity/revision/dedupe/actor/source/trace/digest fields; all new record
  schemas are `aos.*` canonical records, not U-X1 registry artifacts, with
  a named promotion trigger (§6–§8, §13).
- **D-v0.4.74** — the pure reducer boundary: snapshot + typed command +
  verified facts → next snapshot + events + optional queue intent; no
  clock, filesystem, network, database, queue, environment, or model read;
  document verification is pure and lives inside the engine; the only
  shell-verified facts are the two ledger facts named in §9.
- **D-v0.4.75** — revision and dedupe semantics: `expected_revision`
  compare-and-swap, exactly +1 per accepted command, exact-duplicate
  replay by `command_id` + canonical digest, conflicting-duplicate refusal,
  out-of-order refusal; receipts dedupe by `receipt_id` + digest with
  legality-gated ordering (§10).
- **D-v0.4.76** — WorkSpec admission: five verifications (artifact,
  report self-digest and report→artifact binding, registry binding,
  compile status, ledger task facts);
  `invalid`/`unresolved`/`ineligible` refuse admission;
  `requires_external_authority` admits with a mandatory approval fact
  before dispatch; `warning`/`valid` admit; one instance per
  `work_spec_sha256`; both documents stored verbatim; every digest
  recomputed at use (§11).
- **D-v0.4.77** — approval and evidence facts: the
  `aos.workflow-approval-fact/v1` record and its binding rules; approval
  revocation deferred to U-W5; the evidence predicate for `succeeded`
  (spine-valid envelope, binding verification, `success` outcome,
  blank-proof-discounted evidence count, attempt budget); `fail` maps to
  `failed`; `partial`/`unknown` refuse (§12).
- **D-v0.4.78** — the queue handshake: `aos.workflow-queue-intent/v1` and
  `aos.workflow-queue-receipt/v1`; the dispatch intent embeds the canonical
  WorkSpec document; derived deterministic intent ids and idempotency keys;
  two-phase cancellation after dispatch, local cancellation before;
  at-least-once delivery with duplicate replay and refusal-then-redeliver
  ordering; the source-of-truth split (§13).
- **D-v0.4.79** — persistence: layered architecture (pure kernel; local
  append-only `workflow_events` + derived `workflows` snapshot; outbox
  `workflow_intents` / inbox `workflow_receipts`; verbatim `workflow_facts`
  and command dedupe `workflow_commands`); schema v6 purely additive
  migration; one transaction per accepted command; crash-point analysis;
  fold-and-compare verification that reports and never rewrites (§14).
- **D-v0.4.80** — updateability: `transition_policy_version` (integer,
  starts at 1; U-W3 activation is version 2), versioned record schemas
  (`…/v1`), stable string values everywhere, frozen per-version replay,
  unknown-version refusal, migration-versus-adapter rules (§15).
- **D-v0.4.81** — implementation slices and exact paths: U-W2.1 kernel,
  U-W2.2 persistence, U-W2.3 CLI/docs inside the single frozen agentic-os
  PR; U-W2.R runtime adapter as an explicit separate-repository delivery;
  the exact file table in §18 is exhaustive.
- **D-v0.4.82** — exclusions are mechanical: the §0.2 list is enforced by
  the §19 test matrix (no-I/O import discipline, absence of retry/
  checkpoint/compensation surfaces, byte-unchanged neighbors), not by
  intention.

## 2. Dependencies, live surfaces, and phase reconciliation

Proven present at the baseline (all paths are the exact live paths; none
was assumed):

| Needed surface | Exact live equivalent |
| --- | --- |
| U-W1 compiler | `agentic_os/workspecs.py` (`compile_work_spec`, `lint_work_spec`, `_accept_workspec`, `_accept_report`, `snapshot_digest`, six-status precedence, 25-code lint vocabulary); tests `tests/test_v04_workspec_compiler.py` |
| Protocol spine | `agentic_os/protocols.py` (`serialize_canonical`, `parse_canonical`, `content_digest`, `validate_document`, `verify_binding`, `read_artifact_bytes`, closed reason codes, six registry identities); projection `protocols/**` |
| Task lifecycle | `agentic_os/models.py` `TASK_STATUSES = ("inbox","ready","in_progress","done")`; `agentic_os/ops.py` `LEGAL_TASK_TRANSITIONS`, `set_task_status`, `mark_done` (evidence-gated, journaled override) |
| Run lifecycle | `agentic_os/models.py` `RUN_OUTCOMES = ("success","partial","fail","unknown")`; `agentic_os/ops.py` `start_run` (consumes ready→in_progress), `end_run` |
| Append-only events | `agentic_os/events.py` `emit` (same-transaction invariant, `redact_tree` choke point, payload `schema_version: 1`); `events` table in `agentic_os/db.py` |
| Database schema | `agentic_os/db.py` `SCHEMA_VERSION = "5"`, shared-DDL composition, `transaction()` helper, version gate `_check_schema_version` |
| Migration framework | `agentic_os/migrations.py` (`Migration`, `MIGRATIONS` 1→2→3→4→5, backup-first `apply_migrations`, frozen-history rule, per-step whole-database `foreign_key_check`) |
| Queue or dispatch abstraction | NONE in the live tree. Every occurrence of "queue" is a local BFS work-list variable (`governance.py:788`, `workspecs.py:1288`), a retrieval test-fixture string (`retrieval.py:1580`, `:1621`), or one forward-referencing docstring line (`workspecs.py:24`); no module, table, or type models a queue, and `power.dispatch()` routes CLI commands, not work. The live queue is the private `ai-company-runtime` Postgres queue (blueprint §5.1, §9.5), outside this repository |
| Approval records | No stored approval rows exist. Live approval vocabulary is reference-shaped and opaque: `policy_refs.approval_ref` (`beast.work-spec/v1`), `approval_ref` in the U-K1/U-T1 execution context, governance reason `approval_required`, lint code `approval_reference_required` |
| Evidence predicates | `agentic_os/ops.py` `mark_done` (refuses `done` with zero evidence; `--no-evidence` requires a journaled reason), `add_evidence` (blank `ref`/`claim` refusal, D-v0.2.36), `add_git_evidence` (verified commit); `expected_result` contract inside the WorkSpec schema |
| Canonical serialization and digests | `agentic_os/protocols.py` `CANONICAL_JSON`, `CONTENT_HASH_ALG`, `content_digest` (top-level `content_sha256` excluded) |
| Optimistic concurrency / CAS | NONE live. Existing writers rely on `BEGIN IMMEDIATE` transactions plus storage CHECKs (`agent_handoff_transitions` `UNIQUE(handoff_id, seq)` and its `from_state` CHECK are the nearest precedent). U-W2 introduces the first revision compare-and-swap |
| Runtime task UUID | `agentic_os/protocols.py` envelope field `runtime_task_uuid` (declared reference, "owned by a different system"); no generator and no consumer exist |
| WorkSpec / compile-report consumers | NONE. `agentic_os/cli.py` contains no WorkSpec verb (its only mention is a help-string example); U-W1 shipped a pure library. U-W2 is the first consumer of `CompileResult` artifacts and reports |

Boundary reconciliation (frozen):

- U-W1 owns compilation, static lint, local resolution, decompile, and
  semantic diff. U-W2 consumes its outputs through the public acceptance
  seam and re-runs none of its gates.
- U-W2 owns workflow state, legal transitions, revision/order checks,
  history reconstruction, and the queue handshake records on the
  agentic-os side.
- U-W3 owns retry loops, checkpoints, resume machinery, and compensation
  behavior; its vocabulary hooks are reserved here, never implemented.
- U-W4 owns loop-health monitoring; U-W5 owns semantic interrupts
  (including approval revocation); U-W6 is a future durable-engine
  trigger, evaluated only when real workflows need long waits, replay
  across process restarts, nested compensation, or operator signals the
  frozen design cannot satisfy (blueprint §9.5).
- Governance (U-K1/U-T1 and its successors) remains the sole owner of
  approval, policy, budget, capability, and credential decisions;
  `governance.invoke()` remains single-attempt and byte-unchanged.
- Local and runtime databases are never shared (blueprint §5.1); the
  handshake records are the entire interface.

## 3. Threat and failure model; trust boundary

- Every document reaching U-W2 is untrusted cross-boundary input: WorkSpec
  artifacts, compile reports, approval facts, result envelopes, queue
  receipts. Each is accepted only through full verification (canonical
  round-trip snapshot on intake, schema/shape validation, digest
  recomputation, binding checks); an embedded `content_sha256` is never
  trusted, always recomputed (the U-W1 §15 rule).
- Refusals are closed, bounded, value-free one-liners (the
  `ProtocolError`/`GovernanceError`/`WorkSpecError` idiom): a reason code,
  a schema-safe path or validated identifier, a fixed hint. No field
  value, document excerpt, or exception text ever enters a message.
- Workflow event payloads carry enum members, validated identifiers,
  bounded integers, and digests only; the AOS journal additionally passes
  through `events.emit`'s `redact_tree` choke point. There is no free-text
  event field to leak a secret through.
- A hostile runtime adapter can, at worst, report false execution facts
  about its own plane (a `started` receipt for work it never started). It
  cannot forge admission, approval, or success: admission and approval
  facts bind by digest to documents the ledger holds, and `succeeded`
  requires a result envelope that digest-binds the exact admitted WorkSpec
  and passes the evidence predicate. Receipts are stored verbatim so false
  reports are auditable.
- Crash safety is transactional: one accepted command commits atomically
  or not at all (§14 crash points); the outbox/inbox pattern makes
  redelivery safe in both directions.
- Fail closed everywhere: unknown command, unknown event in history,
  unknown policy version, gap or hash mismatch in history — all refuse;
  nothing guesses, nothing auto-repairs, nothing rewrites history.

## 4. Workflow ownership (decision 1: outcome B)

**Chosen: B — public kernel plus transport-neutral queue adapter**
(D-v0.4.71).

The authoritative workflow lifecycle lives in `agentic-os`: the governance
plane already owns tasks, approvals, evidence, and decisions (blueprint
§5.1), and the lifecycle's gates are governance gates (admission binds
compiler output; `awaiting_approval` binds approval facts; `succeeded`
binds evidence). The queue side is a record contract, not code: U-W2
defines `aos.workflow-queue-intent/v1` and `aos.workflow-queue-receipt/v1`
as transport-neutral canonical records, and the runtime's adapter — an
explicit, named, separate-repository slice (§18, U-W2.R) — converts them
to and from its own Postgres queue in its own database.

- **A (single-repository U-W2) rejected.** The live queue is in the
  private `ai-company-runtime` repository; this tree contains no queue,
  lease, or dispatch abstraction at all (§2). A single-repository design
  would either implement a second queue in agentic-os (forbidden:
  blueprint §9.5 preserves the working runtime queue; §5.1 says agentic-os
  never owns queue leases) or silently pretend the queue boundary does not
  exist. Truthful queue integration cannot be one repository.
- **C (cross-repository U-W2A/U-W2B/U-W2C split) rejected.** A separate
  protocol repository is explicitly premature ("do not create a third
  repository yet" — blueprint §5.1: split only at three or more
  independent consumers); the record vocabulary has exactly two consumers.
  Splitting the kernel itself across repositories would put the
  authoritative lifecycle partly outside the governance plane and make the
  private repository a hard build dependency of the public one. B keeps
  the split where the trust boundary actually is — records, not code —
  while still making the required cross-repository change explicit as
  U-W2.R rather than hiding it inside one worktree.

Source-of-truth consequence (frozen; elaborated in §13): the AOS ledger is
authoritative for lifecycle state, admission, approval facts, success
judgment, and emitted intents; the runtime is authoritative for queue
membership, leases, workers, attempt execution, and the
`runtime_task_uuid` namespace. Each side learns of the other only through
records.

## 5. Lifecycle vocabulary and the complete transition matrix

### 5.1 States (closed; stable strings)

The blueprint §9.2 STATE VOCABULARY is adopted in full; its narrative
arrow is not. Blueprint §9.2 reads
`proposed → compiled → validated → awaiting_approval → scheduled →
running` as a sentence about the usual order of events, and U-W2
deliberately does NOT freeze `awaiting_approval → scheduled` as an edge:
`scheduled` means "the runtime holds the work" and is reachable only
through a queue `accepted` receipt (§13.3), whereas approval is a
governance fact and never a dispatch. A satisfied admission approval
returns the instance to `validated`, from which `request_dispatch`
proceeds normally, so the reachable journey is the blueprint's with one
extra hop and no lost capability. The deviation is declared here rather
than discovered in implementation (D-v0.4.72). `proposed` is
**pre-compile authoring plane** (an AOS task plus an
`aos.work-spec-authoring/v1` input; U-W1's domain): a U-W2 instance cannot
exist before there is an artifact digest to bind state to, so U-W2's
history begins at admission and `proposed` is never a `workflows.state`
value (D-v0.4.72).

Thirteen authoritative U-W2 states:

```text
WORKFLOW_STATES = (
    "compiled", "validated", "awaiting_approval", "scheduled", "running",
    "waiting_input", "waiting_approval", "paused", "compensating",
    "succeeded", "failed", "cancelled", "compensated",
)
```

- Terminal (immutable; no command ever leaves them — the
  `AGENT_LIFECYCLE_REVOKED` / closed-task precedent):
  `succeeded`, `failed`, `cancelled`, `compensated`.
- Reserved to U-W3 under transition-policy v1: every edge touching
  `compensating`/`compensated`. The states and edges are frozen now (so
  the vocabulary never reopens) but commands attempting them refuse with
  `transition_reserved` until policy version 2 — exactly the
  `TERMINATION_OUTCOMES` / `LOCAL_TERMINATION_OUTCOMES` honesty split.
- `succeeded` is reachable only through the evidence predicate (§12);
  there is no other path and no override.

### 5.2 Complete transition matrix (13 × 13; frozen as data)

Cell legend — `·` illegal (refuses `illegal_transition`; from a terminal
row, `workflow_terminal`); `R` defined but reserved to U-W3 (refuses
`transition_reserved` under policy v1); a mark names the only legal
driver: `cmd:` a human/CLI command, `rcp:` a verified queue receipt via
`record_queue_receipt`, `res:` a verified result envelope via
`record_result`, `apr:` a verified approval fact via `record_approval`.
Creation is the one pseudo-edge `∅ → compiled` via `admit_work_spec`.

| from \ to | compiled | validated | awaiting_approval | scheduled | running | waiting_input | waiting_approval | paused | compensating | succeeded | failed | cancelled | compensated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| compiled | · | cmd:validate | · | · | · | · | · | · | · | · | · | cmd:request_cancel | · |
| validated | · | · | cmd:request_approval | rcp:accepted | · | · | · | · | · | · | · | cmd:request_cancel | · |
| awaiting_approval | · | apr:record_approval | · | · | · | · | · | · | · | · | · | cmd:request_cancel | · |
| scheduled | · | · | · | · | rcp:started | · | · | · | · | · | rcp:failed | rcp:cancelled | · |
| running | · | · | · | · | · | rcp:waiting_input | rcp:waiting_approval | rcp:paused | R | res:success | res:fail / rcp:failed | rcp:cancelled | · |
| waiting_input | · | · | · | · | rcp:resumed | · | · | · | · | · | rcp:failed | rcp:cancelled | · |
| waiting_approval | · | · | · | · | rcp:resumed (approval fact required) | · | · | · | · | · | rcp:failed | rcp:cancelled | · |
| paused | · | · | · | · | rcp:resumed | · | · | · | · | · | rcp:failed | rcp:cancelled | · |
| compensating | · | · | · | · | · | · | · | · | · | · | R | · | R |
| succeeded | · | · | · | · | · | · | · | · | · | · | · | · | · |
| failed | · | · | · | · | · | · | · | · | · | · | · | · | · |
| cancelled | · | · | · | · | · | · | · | · | · | · | · | · | · |
| compensated | · | · | · | · | · | · | · | · | · | · | · | · | · |

Every cell not named above is illegal in every currently frozen policy
version. 25 active edges, 3 reserved edges (`running → compensating`,
`compensating → compensated`, `compensating → failed`), 1 creation
pseudo-edge. `compensating → cancelled` is deliberately illegal in every
frozen version: abandoning a compensation mid-flight would be a silent
cleanup failure; a compensation concludes as `compensated` or `failed`
(U-W3 decides which, under policy v2).

Two scoping rules make the matrix exact:

- **The matrix governs STATE-CHANGING edges only.** An accepted stateless
  command (`request_dispatch`, `revoke_dispatch`, post-dispatch
  `request_cancel`, runtime-scope `record_approval`, and a `rejected`
  receipt) traverses no cell: it appends an event with `to_state` null,
  consumes its revision, and leaves `state` untouched. The diagonal is
  illegal for state-changing drivers and simply not addressed by
  stateless ones; `illegal_transition` is never the refusal for an
  otherwise-legal stateless command.
- **Two of the three reserved cells have no driver under policy v1.** No
  member of `WORKFLOW_COMMANDS` (§6) or `WORKFLOW_RECEIPT_KINDS` (§13.2)
  targets `compensating` or `compensated`, and `record_result` maps only
  to `succeeded`/`failed` (§12.2), so `running → compensating` and
  `compensating → compensated` are matrix-only reservations that cannot
  be attempted through any public entry point. Only `compensating →
  failed` is attemptable (a `failed` receipt), and only against a
  synthetic `compensating` snapshot the store can never produce.
  `transition_reserved` is therefore a reducer-level refusal that policy
  v2 activates along with U-W3's drivers; it is not a claim that a v1
  caller can reach those edges today.

### 5.3 Determinations required by the freeze

- `proposed`: pre-compile authoring; not authoritative in U-W2 (§5.1).
- Exact terminal states: `succeeded`, `failed`, `cancelled`,
  `compensated`; terminal rows accept no command (`workflow_terminal`),
  and a receipt or result arriving on a terminal workflow refuses without
  mutating anything.
- Cancellation from each nonterminal state: `compiled`, `validated`,
  `awaiting_approval` cancel locally and immediately (`request_cancel`;
  AOS is source of truth until it has OBSERVED queue acceptance — if a
  dispatch intent is outstanding the same decision emits a cancel intent
  and a `dispatch_revoked` event). The precondition is observational, not
  physical: AOS cannot know whether the queue committed a row it has not
  yet received a receipt for, so a local cancel can go terminal while a
  runtime task is already live (§13.3, §22). `scheduled`, `running`,
  `waiting_input`,
  `waiting_approval`, `paused` cancel in two phases: `request_cancel`
  emits a cancel intent and a `cancel_requested` event without changing
  state; only a verified `cancelled` receipt moves the workflow to
  `cancelled` (the runtime is source of truth for execution).
  `compensating` is not cancellable (above).
- Transitions reserved for U-W3: the three `R` edges, plus reinterpreting
  `partial`/`unknown` outcomes (§12) — all activate only via
  transition-policy version 2.
- Terminal-state immutability: structural (no legal edge exists) and
  storage-side (the v6 DDL's transition CHECKs; §14).
- Success evidence requirements: §12. U-W2 provides no evidence-free
  OVERRIDE — the `mark_done --no-evidence` escape is a task-plane device
  and deliberately has no workflow-plane counterpart. The evidence
  THRESHOLD, however, is the artifact's own digest-bound declaration, and
  the live schema permits `expected_result.min_evidence_count = 0`
  (`protocols.py`: `{"minimum": 0}`), which the U-W1 compiler accepts as
  `valid`. A WorkSpec that declares zero therefore succeeds with zero
  counted evidence: that is the author's admitted declaration, not an
  engine escape hatch, and unlike `mark_done --no-evidence` it carries no
  journaled reason (§12.2 gate 5, §22).

## 6. Commands (closed vocabulary; typed envelope)

```text
WORKFLOW_COMMANDS = (
    "admit_work_spec", "validate", "request_approval", "record_approval",
    "request_dispatch", "revoke_dispatch", "request_cancel",
    "record_queue_receipt", "record_result",
)
```

Command record schema: `aos.workflow-command/v1` — a canonical record (the
`aos.*` house style), self-digested. Required fields on EVERY command:

| Field | Rule |
| --- | --- |
| `schema` | const `aos.workflow-command/v1` (the `/v1` is the command schema version) |
| `command` | member of `WORKFLOW_COMMANDS` |
| `command_id` | UUID (pattern `UUID_PATTERN`); the dedupe identity |
| `workflow_id` | `WF-<n>` ledger id (pattern `^WF-[0-9]{1,19}$`); ABSENT exactly on `admit_work_spec`, which creates the identity |
| `expected_revision` | integer ≥ 0; the compare-and-swap guard; 0 exactly on `admit_work_spec` |
| `actor` | `PROVENANCE_PATTERN` (`human` or `agent:<name>`) |
| `source` | member of `("cli", "runtime_adapter")` — the transport origin |
| `created_at` | RFC3339 Z instant, caller-supplied (the workspecs no-clock rule); real-instant checked |
| `trace` | optional `Trace` (trace_id/correlation_id/causation_id, spine patterns; all-zero trace refused) |
| `payload` | the verb-specific closed object (§11–§13); unknown keys refuse `payload_malformed` |
| `content_sha256` | canonical digest of the record minus this field; recomputed on receipt, never trusted |

Verb → payload → effect summary (each fully specified in §11–§13):

| Command | Legal in state | Payload carries | Events | Intent emitted |
| --- | --- | --- | --- | --- |
| `admit_work_spec` | ∅ (creates) | work-spec document, compile report document | `workflow_admitted` | — |
| `validate` | compiled | (empty) | `workflow_validated` | — |
| `request_approval` | validated, approval required and unsatisfied | (empty) | `approval_requested` | — |
| `record_approval` | awaiting_approval (scope `admission`); waiting_approval (scope `runtime`, stateless) | approval-fact document | `approval_recorded` | — |
| `request_dispatch` | validated, approval satisfied, none pending | `queue_route` (optional; default `"default"`) | `dispatch_requested` | dispatch |
| `revoke_dispatch` | validated, dispatch pending | (empty) | `dispatch_revoked` | cancel |
| `request_cancel` | any nonterminal except compensating | (empty) | pre-dispatch: `workflow_cancelled` (+ `dispatch_revoked` if pending); post-dispatch: `cancel_requested` | cancel (post-dispatch, or pending pre-dispatch) |
| `record_queue_receipt` | per receipt kind (§13) | receipt document | per kind (§7) | — |
| `record_result` | running | result-envelope document | `workflow_succeeded` / `workflow_failed` | — |

## 7. Events (closed vocabulary)

Event record schema: `aos.workflow-event/v1` (the history schema version).
Seventeen event names:

```text
WORKFLOW_EVENTS = (
    "workflow_admitted", "workflow_validated",
    "approval_requested", "approval_recorded",
    "dispatch_requested", "dispatch_rejected", "dispatch_revoked",
    "dispatch_accepted",
    "run_started", "run_waiting_input", "run_waiting_approval",
    "run_paused", "run_resumed",
    "cancel_requested",
    "workflow_succeeded", "workflow_failed", "workflow_cancelled",
)
```

Every event record carries: `schema`, `event`, `workflow_id`,
`work_spec_sha256`, `seq` (total per workflow, starts at 1), `revision`
(the revision this event produced), `policy_version`, `from_state`,
`to_state` (null for the stateless events `approval_recorded` with runtime
scope, `dispatch_requested`, `dispatch_rejected`, `dispatch_revoked`,
`cancel_requested`), `command_id`, `command_sha256`, `actor`, `payload`
(closed per event: enum members, validated identifiers, bounded integers,
digests only), `created_at` (copied from the command — deterministic), and
`content_sha256`. Events are append-only facts; nothing updates or deletes
one, ever.

`from_state` is null exactly on `workflow_admitted` (the creation
pseudo-edge); `verify_history`'s chaining rule starts there.

Receipt kind → event (the complete mapping §6 defers to; a bijection over
the nine kinds of §13.2):

| Receipt kind | Event | Edge |
| --- | --- | --- |
| `accepted` | `dispatch_accepted` | validated → scheduled |
| `rejected` | `dispatch_rejected` | stateless (`to_state` null) |
| `started` | `run_started` | scheduled → running |
| `waiting_input` | `run_waiting_input` | running → waiting_input |
| `waiting_approval` | `run_waiting_approval` | running → waiting_approval |
| `paused` | `run_paused` | running → paused |
| `resumed` | `run_resumed` | waiting_input / waiting_approval / paused → running |
| `cancelled` | `workflow_cancelled` | scheduled / running / waiting_* / paused → cancelled |
| `failed` | `workflow_failed` | scheduled / running / waiting_* / paused → failed |

The other eight event names are command-driven: `workflow_admitted`
(`admit_work_spec`), `workflow_validated` (`validate`),
`approval_requested` (`request_approval`), `approval_recorded`
(`record_approval`; stateful for admission scope, stateless for runtime
scope), `dispatch_requested` (`request_dispatch`), `dispatch_revoked`
(`revoke_dispatch`, or pre-dispatch `request_cancel` with an outstanding
intent), `cancel_requested` (post-dispatch `request_cancel`), and
`workflow_succeeded` (`record_result`, `success`). Nine receipt-driven
names plus these eight is the full seventeen. Exactly two names carry a
second driver: `workflow_cancelled` is also emitted by pre-dispatch
`request_cancel` (the three `cmd:request_cancel` cells in the
`cancelled` column), and `workflow_failed` is also emitted by
`record_result` with a `fail` outcome — the one cell the matrix spells
with two drivers, `running → failed` (`res:fail / rcp:failed`).

Mapping notes: `dispatch_rejected` records no state change (`from_state`
`validated`, `to_state` null) and clears the pending intent;
`workflow_cancelled` names its initiator in the payload (`requested` —
our cancel intent acknowledged — or `runtime` — unilateral runtime
cancellation, which is legal without a pending intent, since a kill
switch on the runtime side is a fact, not a request).

## 8. Refusal reasons (closed vocabulary)

Forty-three codes, in canonical emission order (the
`GOVERNANCE_REASON_CODES` idiom). A refusal mutates nothing, appends no
workflow event, and consumes no revision; the CLI shell journals refusals
to the AOS `events` table for observability, but the workflow history
records accepted transitions only.

```text
WORKFLOW_REFUSAL_REASONS = (
    # envelope / shape
    "command_malformed", "command_unknown", "command_schema_unsupported",
    "payload_malformed",
    # identity / order / dedupe
    "workflow_unknown", "workflow_exists", "workflow_terminal",
    "revision_mismatch", "command_conflict", "illegal_transition",
    "transition_reserved", "policy_version_unsupported",
    # admission
    "admission_artifact_invalid", "admission_report_malformed",
    "admission_report_unbound", "admission_status_blocking",
    "admission_registry_mismatch", "admission_task_unknown",
    "admission_task_closed",
    # approval
    "approval_not_required", "approval_already_satisfied",
    "approval_pending", "approval_fact_malformed", "approval_fact_unbound",
    "approval_fact_missing",
    # dispatch / receipts
    "dispatch_already_pending", "dispatch_not_pending",
    "cancel_already_pending", "receipt_malformed", "receipt_unbound",
    "receipt_conflict", "receipt_out_of_order", "receipt_superseded",
    "runtime_uuid_mismatch",
    # results / evidence
    "result_malformed", "result_unbound", "result_inconsistent",
    "result_attempt_exceeded", "result_outcome_inconclusive",
    "evidence_insufficient",
    # history / rebuild
    "history_corrupt", "history_unknown_event", "snapshot_divergence",
)
```

Thirty-six of the forty-three have their trigger named in §9–§14. The
remaining seven are named here so every member has exactly one stated,
attainable trigger:

| Reason | Trigger |
| --- | --- |
| `command_malformed` | the envelope fails the §6 field table (missing, mistyped, or pattern-violating `command_id`/`workflow_id`/`expected_revision`/`actor`/`source`/`created_at`/`trace`, or a `content_sha256` that does not recompute) |
| `command_unknown` | `command` is a string outside `WORKFLOW_COMMANDS` |
| `workflow_unknown` | `workflow_id` is well-formed but names no `workflows` row (shell-detected before `decide`) |
| `approval_fact_malformed` | the approval document fails the §12.1 closed shape before any binding check |
| `dispatch_already_pending` | `request_dispatch` while `dispatch_intent_id` is set |
| `dispatch_not_pending` | `revoke_dispatch` while `dispatch_intent_id` is null |
| `receipt_malformed` | the receipt document fails the §13.2 closed shape (unknown `receipt_kind`, missing kind-required field, or a `content_sha256` that does not recompute) before any binding check |

Refusal messages follow the house pattern exactly: one bounded,
actionable, value-free line built from the code, a schema-safe path or
already-validated identifier, and a fixed hint; an undeclared code is a
`KeyError` programming failure, not a runtime path.

## 9. Pure reducer

Frozen boundary (D-v0.4.74), in `agentic_os/workflow_engine.py`:

```text
decide(snapshot, command, facts) -> WorkflowDecision
    snapshot : the typed aos.workflow-snapshot/v1 value (None for
               admit_work_spec)
    command  : a validated aos.workflow-command/v1 record
    facts    : AdmissionFacts(task_exists: bool, task_open: bool) —
               the ONLY shell-verified inputs; empty for every verb
               except admit_work_spec
    returns  : WorkflowDecision(
                   snapshot_after,   # fresh, never aliasing inputs
                   events,           # tuple of event records (≥ 1)
                   intent,           # aos.workflow-queue-intent/v1 or None
               )
    raises   : WorkflowRefusal(reason, where) — closed §8 reasons
```

`decide` never sees a duplicate: exact-duplicate detection is a
`command_id` lookup against `workflow_commands` and a range read of
`workflow_events`, neither of which a pure function can perform. The
store performs that lookup BEFORE calling `decide` and reports the result
on `workflow_store.StoreOutcome` (§10, §18) — `replay` is a store-level
fact, not a reducer-level one (D-v0.4.74/75).

**The snapshot record (`aos.workflow-snapshot/v1`; closed).** This is the
sixth minted schema (§13.4) and `decide`'s first argument; freezing it is
what makes the reducer total. Fields:

| Field | Rule |
| --- | --- |
| `schema` | const `aos.workflow-snapshot/v1` |
| `workflow_id`, `task_id` | the `WF-<n>` identity and the admitted `aos_task_id` |
| `work_spec_sha256`, `report_sha256`, `snapshot_sha256`, `registry_version`, `compile_status` | admission-time immutables |
| `work_spec_document`, `report_document` | the two verbatim canonical documents (§11), needed by `verify_binding` (§12.2) and the approval-ref check (§12.1) |
| `state`, `revision`, `policy_version` | the mutable core |
| `approval_required`, `admission_approval_satisfied` | the §11 flag and whether an admission-scope fact is on file |
| `dispatch_intent_id`, `cancel_intent_id`, `runtime_task_uuid`, `queue_route` | the pending-intent pointers and runtime identity (§14.1) |
| `intent_seq` | count of intents already emitted for this workflow; `+1` derives the next `intent_id`/`idempotency_key` (§13.1) |
| `revoked_intent_ids`, `resolved_intent_ids` | bounded tuples that let a receipt naming a known-but-closed intent refuse `receipt_superseded` rather than `receipt_unbound` (§13.3) |
| `last_seq` | the highest event `seq`; the next event is `last_seq + 1` |
| `last_wait_entry_seq`, `last_runtime_approval_seq` | the §12.1 ordering rule, as event seqs |
| `content_sha256` | canonical digest; this IS `workflows.content_sha256` (§14.1) |

Every field above is a pure function of the event history plus the two
admission-time documents, so `fold` reconstructs all of it except the
document bodies (§14.2).

- **No I/O of any kind**: no clock (`created_at` values arrive inside the
  command; event timestamps copy them), no filesystem, no network, no
  database, no queue, no environment, no locale, no randomness, no model
  read, no dynamic import. The module imports `protocols`, `workspecs`
  (the public acceptance seam), `secretscan` (pure scanning, the U-W1
  precedent), `utils` (`AosError`, the base every closed refusal inherits
  — the `ProtocolError`/`GovernanceError`/`WorkSpecError` idiom of §3 and
  the single `cli.py` refusal choke point), `dataclasses`, `hashlib`, and
  `re`, plus the house `from __future__ import annotations` header — and
  nothing else; the `datetime` module stays out (the workspecs
  calendar-arithmetic rule). Enforced by the §19 import-discipline test,
  which is an AST check over this module's OWN import statements (the
  live `test_import_graph_is_closed` precedent), not over the transitive
  closure — `protocols` legitimately imports `os` and `datetime` for its
  file reader and instant checks, and a transitive assertion would be
  unimplementable.
- Document verification (artifact, report, approval fact, result
  envelope, receipt) is pure computation and lives inside the engine;
  the shell verifies only the two ledger facts named above.
- Companion pure functions: `fold(events) -> snapshot` (rebuild),
  `verify_history(events) -> None | WorkflowRefusal` (seq totality,
  per-event digest recomputation, from-state chaining, known event names,
  known policy versions), and the record builders for intents, receipts
  acceptance, and event payloads.
- Determinism: identical `(snapshot, command, facts)` yield byte-identical
  decisions on every platform; derived identifiers (§13) are functions of
  history, not of any clock or RNG.
- Caller-mutation isolation: every accepted document is snapshotted by
  canonical round-trip on intake and every returned structure is freshly
  built (the U-W1 §15 rule).

## 10. Revision and dedupe semantics

- `workflows.revision` starts at 1 when `admit_work_spec` commits and
  increases by EXACTLY 1 per accepted command — including stateless
  commands (`request_dispatch`, `revoke_dispatch`, post-dispatch
  `request_cancel`, runtime-scope `record_approval`, and `rejected`
  receipts): every accepted command appends at least one event, and the
  revision counts accepted commands. Events within one command share the
  resulting revision.
- `expected_revision` is mandatory: a mismatch refuses
  `revision_mismatch` and mutates nothing. For every command EXCEPT
  `admit_work_spec` the store enforces it as a literal compare-and-swap
  (`UPDATE workflows SET revision = ?, … WHERE id = ? AND revision = ?`;
  rowcount ≠ 1 aborts the transaction), so two racing writers cannot both
  win — the reducer's check is the semantic gate, the CAS is the storage
  gate, and both must agree. `admit_work_spec` has no row to update: its
  storage gate is the `UNIQUE(work_spec_sha256)` INSERT, whose violation
  is `workflow_exists`, and its `expected_revision = 0` is a semantic
  assertion only.
- Exact duplicate replay: a command whose `command_id` matches a stored
  accepted command AND whose recomputed `content_sha256` equals the
  stored digest returns the ORIGINAL outcome — `StoreOutcome.replay =
  True`, the original events and resulting revision, no new event, no
  revision change, no new intent row. The store answers this from
  `workflow_commands` + the `[event_seq_first, event_seq_last]` range
  without calling `decide` (§9). `StoreOutcome.intent` is `None` on
  replay: an intent is delivered from the outbox, never from a command
  result, and `aos workflow export-intents` remains the sole retrieval
  path for a still-outstanding intent. Duplicate delivery of an accepted
  command is therefore idempotent end to end.
- Conflicting duplicate: same `command_id`, different digest →
  `command_conflict`. Nothing is merged, nothing is guessed.
- A duplicate of a REFUSED command is not replayed from storage (refusals
  store nothing); it is re-evaluated and — deterministically — refuses
  identically.
- Out-of-order commands: there is no queueing or reordering inside the
  engine; a command carrying a stale or future `expected_revision`
  refuses (`revision_mismatch`), and the caller re-reads and retries
  deliberately.
- Canonical digests: command and receipt digests are
  `protocols.content_digest` over the record (top-level `content_sha256`
  excluded) — one hashing rule for every record in this unit.
- Receipt dedupe is `receipt_id`-keyed with the same
  exact-duplicate-replay / conflicting-duplicate-refusal rules (§13).

## 11. WorkSpec admission

`admit_work_spec` payload carries the exact `beast.work-spec/v1` document
and its `aos.work-spec-compile-report/v1` document. Verification order
(fail closed at the first refusal; D-v0.4.76):

1. **Artifact**: `workspecs.accept_work_spec` (canonical round-trip,
   spine validation, identity check). Any spine refusal wraps as
   `admission_artifact_invalid` carrying the spine's closed code in
   bounded diagnostics. The artifact digest is recomputed here and is THE
   workflow identity.
2. **Report self-digest and binding**:
   `workspecs.accept_compile_report(report, artifact_digest)` — the
   frozen sidecar rule. The seam raises exactly two closed codes and they
   map 1:1: `malformed_report` (not an object, non-canonical, wrong
   `schema`, or failing the report shape check) →
   `admission_report_malformed`; `report_mismatch` →
   `admission_report_unbound`. Because the live seam raises
   `report_mismatch` BOTH for a report whose self-digest does not
   recompute (an edited report) and for one whose `work_spec_sha256`
   names a different artifact, `admission_report_unbound` covers both:
   U-W2 does not distinguish them, because the gate it delegates to does
   not, and inventing a distinction would mean re-implementing the gate.
   An absent report is a payload-shape failure (`payload_malformed`, §6),
   not an admission refusal.
3. **Registry binding**: `report.registry_state.registry_version` must
   equal `protocols.REGISTRY_VERSION` and
   `report.registry_state.work_spec_schema_sha256` must equal the live
   `REGISTRY["beast.work-spec/v1"].digest`; mismatch refuses
   `admission_registry_mismatch`. `registry_state.snapshot_sha256` is
   recorded verbatim as the compiler's digest-sealed attestation of its
   resolution universe (it cannot be re-derived without the snapshot and
   is not pretended to be).
4. **Compile status** (`report.status`):
   - `invalid`, `unresolved`, `ineligible` → refuse
     `admission_status_blocking`. No blocking status can create an
     instance, so no blocking status can ever schedule — structurally,
     not by convention.
   - `requires_external_authority` → admit with
     `approval_required = true`; the instance cannot pass
     `request_dispatch` without a recorded admission-scope approval fact
     (`approval_pending` otherwise). Nothing silently schedules.
   - `warning` → admit (findings are recorded facts in the admission
     event payload as code/path pairs).
   - `valid` → admit.
5. **Ledger facts** (shell-verified, passed as `AdmissionFacts`): the
   artifact's `aos_task_id` must name an existing task
   (`admission_task_unknown`) that is not `done`
   (`admission_task_closed`).

Additional admission rules:

- One instance per WorkSpec: `work_spec_sha256` is UNIQUE; re-admission
  of the same digest refuses `workflow_exists` (a revised WorkSpec is a
  new digest and a new instance; the semantic diff between them is
  U-W1's tool).
- Both documents are stored verbatim (canonical text) on the workflow row
  — the `agent_passports.document` precedent — because later gates
  (`verify_binding` against result envelopes) need the exact body, and
  digests are recomputed from these stored bodies at every use, never
  read from stored columns.
- `approval_required := (status == "requires_external_authority") OR
  (artifact.policy_refs.approval_ref is present)`. A declared approval
  reference is a declaration that external authority exists; U-W2
  requires the corresponding fact before dispatch and never treats the
  reference itself as satisfaction.
- The admission event payload records: compile status, the two document
  digests, `snapshot_sha256`, `registry_version`, finding code/path pairs
  (bounded at 32), `approval_required`, and the task id. No free text.

## 12. Approval and evidence facts

U-W2 records verified external facts; it never generates approval or
evidence (D-v0.4.77).

### 12.1 Approval facts

Record `aos.workflow-approval-fact/v1` (closed shape):

| Field | Rule |
| --- | --- |
| `schema` | const |
| `work_spec_sha256` | must equal the workflow's digest (else `approval_fact_unbound`) |
| `approval_ref` | `OPAQUE_REF_PATTERN`. When `scope = "admission"` AND the artifact declares `policy_refs.approval_ref`, it must equal that value byte-exact (else `approval_fact_unbound`): the artifact's declared reference names the pre-authored ADMISSION authority. A `scope = "runtime"` fact binds by `work_spec_sha256` and scope only, and carries the approving system's OWN opaque reference — a mid-run approval is a distinct, later-minted record (the live runtime mints one `approval_requests.approval_id` per park event), so demanding that it repeat the artifact's authored reference would either refuse every honest runtime fact or make the engine record an approval nobody issued |
| `scope` | `("admission", "runtime")` — which wait it satisfies |
| `approved_by` | `PROVENANCE_PATTERN`; recorded verbatim; U-W2 judges no approver authority (that is governance's, later) |
| `approved_at` | RFC3339 Z instant, real-instant checked |
| `content_sha256` | canonical digest, recomputed |

- `awaiting_approval --record_approval(scope=admission)--> validated`:
  the single approval-in path before dispatch. A second admission-scope
  fact after satisfaction refuses `approval_already_satisfied`;
  `record_approval` outside its legal states refuses
  `approval_not_required`.
- Mid-run approval waits: `running --rcp:waiting_approval-->
  waiting_approval`. A runtime-scope fact recorded there is a STATELESS
  `approval_recorded` event; the exit edge is the runtime's `resumed`
  receipt, and that receipt REFUSES (`approval_fact_missing`) unless a
  runtime-scope `approval_recorded` EVENT carries a `seq` greater than
  that of the most recent `run_waiting_approval` event. The ordering
  lives on the event history, not on `workflow_facts` (which has no `seq`
  column, §14.1); the snapshot carries the two values as
  `last_runtime_approval_seq` and `last_wait_entry_seq` (§9), which is
  what keeps the check inside the pure reducer. The engine will not
  record a resumption that claims an approval nobody recorded.
- Facts are stored verbatim in `workflow_facts` with
  `UNIQUE(workflow_id, fact_kind, document_sha256)`; an exact duplicate
  fact replays as a no-op.
- **Approval revocation is deferred to U-W5** (the semantic interrupt
  kernel owns `approval.revoked`); the vocabulary hook is a future
  command under transition-policy ≥ 2, and nothing in v1 accepts or
  simulates one.

### 12.2 Evidence predicate for `succeeded`

`record_result` payload carries the exact `beast.result-envelope/v1`
document. Gates, in order:

1. Spine-valid envelope (`protocols.validate_document`); refusal wraps as
   `result_malformed`.
2. `protocols.verify_binding(envelope, stored WorkSpec document)` — digest
   AND `work_spec_id` agreement; failure is `result_unbound`.
3. `attempt ≤ artifact.retry.max_attempts` (default 1 when the artifact
   declares no retry block); else `result_attempt_exceeded`. This budget
   is the artifact's, and the runtime queue keeps its own
   (`task_queue.max_attempts`, live default 3). The adapter MUST enqueue
   with the artifact's value (§13.1) so the two agree; if it does not, a
   task that legitimately succeeded on a later attempt reports an
   `attempt` this gate refuses, and the workflow parks in `running` with
   no honest terminal (§22).
4. Outcome mapping:
   - `success` with `retryable = true` → `result_inconsistent` (a claim
     of success that asks to be retried is not an honest report).
   - `success` → the evidence count gate (below); pass →
     `workflow_succeeded` (`running → succeeded`).
   - `fail` → `workflow_failed` (`running → failed`); failure needs no
     evidence minimum; the envelope (including any `compensation` block)
     is stored verbatim as a fact and NOT acted on (compensation is
     U-W3's).
   - `partial`, `unknown` → `result_outcome_inconclusive`; nothing is
     recorded (retry/salvage semantics are U-W3's; policy v2 will widen
     this).
5. Evidence count gate: an evidence item COUNTS iff its `kind` is a
   member of `expected_result.evidence_kinds` AND `ref.strip()` is
   non-empty AND `claim.strip()` is non-empty (the D-v0.2.36 blank-proof
   rule: NBSP/ideographic padding is whitespace). The predicate is
   `counted ≥ expected_result.min_evidence_count`; failure refuses
   `evidence_insufficient` with bounded diagnostics
   `{required, counted, discounted_kind, discounted_blank}` — counts
   only, never values. Coverage of every declared kind is NOT required:
   `evidence_kinds` enumerates acceptable kinds, not mandatory ones (the
   U-W1 `result_contract_mismatch` subset reading). The threshold is the
   artifact's own declaration and the live schema admits zero
   (`min_evidence_count` `{"minimum": 0}`), which the compiler accepts as
   `valid`; a WorkSpec declaring `0` therefore passes this gate with no
   evidence at all. That is the admitted, digest-bound declaration of the
   author — U-W2 adds no floor of its own and no `--no-evidence`-style
   override, and unlike the task plane's escape it records no journaled
   reason. Declared in §5.3 and §22; U-W1's own default remains 1, "the
   weakest honest result-contract floor".
6. On success, counted evidence items are recorded in the event payload
   as `(kind, sha256-of-ref, provenance)` triples — digests, never raw
   refs — and the full envelope is stored verbatim in `workflow_facts`.
   Writing task-ledger `evidence` rows from envelopes is a HUMAN act via
   the existing `aos evidence add` path and is out of U-W2's scope
   (import/replay stays deferred per D-v0.3.8).

## 13. Queue handshake

Transport-neutral records; at-least-once delivery both ways; no shared
database (D-v0.4.78).

### 13.1 Intents (outbox; AOS → runtime)

Record `aos.workflow-queue-intent/v1`; `intent_kind ∈ ("dispatch",
"cancel")`.

Dispatch intent fields: `schema`, `intent_kind`, `intent_id`,
`workflow_id`, `aos_task_id`, `work_spec_sha256`, `report_sha256`,
`snapshot_sha256`, `compile_status`, `idempotency_key`, `queue_route`,
`requested_at` (from the command), `trace`, `work_spec_document` (the
FULL canonical artifact embedded as a nested object — the runtime needs
the work and records are the only channel; the spine's 256 KiB artifact
bound keeps this bounded, and the receiver re-verifies the embedded
document against `work_spec_sha256`), `content_sha256`.

Cancel intent fields: `schema`, `intent_kind`, `intent_id`,
`workflow_id`, `work_spec_sha256`, `cancels_intent_id` (the dispatch
intent it revokes), `runtime_task_uuid` (when known), `idempotency_key`,
`queue_route`, `requested_at`, `trace`, `content_sha256`.

Derived identifiers (pure functions of history — the U-W1 §6
domain-separated derivation idiom; no clock, no RNG):

- `intent_seq` = 1 + number of prior intents for this workflow (from
  history; replays identically on rebuild).
- `intent_id` = UUIDv8 from
  `sha256("aos-workflow-intent/v1" ‖ 0x00 ‖ work_spec_sha256 ‖ ":" ‖
  intent_seq)`, spelled out here because `workspecs._uuid8_from_digest`
  is private and §0.1/§18 add no third public wrapper: take the first 16
  digest bytes, set `raw[6] = (raw[6] & 0x0F) | 0x80` (version 8) and
  `raw[8] = (raw[8] & 0x3F) | 0x80` (RFC variant), render lowercase
  8-4-4-4-12. `workflow_engine.py` re-implements it locally and a §19
  test pins it byte-equal to `workspecs._uuid8_from_digest` (the
  D-v0.4.23 pinned-equal pattern) — the copy is deliberate and guarded,
  not incidental drift.
- `idempotency_key` = `"wfd-"` + first 40 hex of
  `sha256("aos-workflow-dispatch-idem/v1" ‖ 0x00 ‖ work_spec_sha256 ‖
  ":" ‖ intent_seq)` — distinct per re-dispatch (a rejected dispatch is
  not replayed under the old key) yet stable under history replay; the
  queue dedupes duplicate DELIVERIES of one intent on this key.
- `queue_route`: a validated slug (`COMPONENT_ID_PATTERN`), default
  `"default"`; a route names a queue, grants nothing, and is recorded in
  intent and echoed in receipts.

Adapter obligation (U-W2.R, §18): because the intent embeds the FULL
canonical WorkSpec, the adapter has everything it needs to enqueue
coherently and MUST set the queue row's attempt budget from
`work_spec_document.retry.max_attempts`, defaulting to 1 when the
artifact declares no `retry` block — the same default §12.2 gate 3 uses.
Enqueue parameters are the adapter's to choose, so this needs no change
to the runtime; leaving the queue's own default in place is what would
desynchronise the two budgets.

### 13.2 Receipts (inbox; runtime → AOS)

Record `aos.workflow-queue-receipt/v1`:

```text
WORKFLOW_RECEIPT_KINDS = (
    "accepted", "rejected", "started", "waiting_input",
    "waiting_approval", "paused", "resumed", "cancelled", "failed",
)
```

Fields: `schema`, `receipt_kind`, `receipt_id` (UUID, runtime-minted; the
dedupe identity), `workflow_id`, `work_spec_sha256`, `intent_id`
(REQUIRED on `accepted`/`rejected`; on `cancelled` it names the cancel
intent when acknowledging one and is absent on unilateral runtime
cancellation), `idempotency_key` (echo; required on
`accepted`/`rejected`), `runtime_task_uuid` (REQUIRED on `accepted`,
`started`, `waiting_*`, `paused`, `resumed`; absent on `rejected`),
`queue_route`, `reason` (a `BoundedError`-shaped closed object
`{code, message ≤ 512, retryable}`; required on `rejected`/`failed`,
optional on `cancelled`), `reported_at` (instant), `trace` (optional),
`content_sha256`. Receipts are stored VERBATIM in the inbox on
acceptance, so even a runtime that misreports is auditable.

Kind semantics (frozen, so two adapter authors cannot read them
differently):

- `accepted` — the runtime has DURABLY COMMITTED a task row for this
  intent. The AOS state `scheduled` therefore means "the runtime holds
  the work"; it maps to the live queue's `pending` (or any pre-execution
  status) and NOT to that table's `scheduled_at`/`available_at` columns,
  which AOS does not model.
- `started` — the work has entered the runtime's EXECUTION PLANE for the
  first time. Correspondingly the AOS state `running` means "in the
  runtime's execution plane", not "a worker is executing this instant":
  AOS has no clock and no heartbeat (§22) and cannot distinguish the two.
  Runtime-internal churn that never leaves the execution plane — a
  transient-failure requeue, a lease-expiry requeue, a re-claim by
  another worker — is INVISIBLE to the ledger and emits no receipt. A
  second `started` for a `runtime_task_uuid` already `running` is
  therefore an adapter error, not a state change.
- `resumed` — the runtime has returned the work to its execution plane
  after a wait. It does not assert that a worker has picked it up: the
  live `resume_approved_task` returns the task to `pending`, and under
  the execution-plane definition above that is exactly `running`.
- `rejected` — a queue's refusal to ADMIT a dispatch intent, legal only
  against an outstanding intent. A runtime-side terminal rejection of
  work that already started (a rejected mid-run approval, which the live
  runtime records as task status `rejected`) is a different fact and is
  reported as `failed` with `reason.code` naming the rejection.
- `failed` — the work terminated unsuccessfully in the runtime's plane.
- `cancelled` — the runtime has stopped the work in response to a cancel
  intent (`cancels_intent_id` present) or unilaterally (absent). See §22:
  the live queue has no cancellation status, so this kind is dormant
  today.
- `waiting_input`, `waiting_approval`, `paused` — the work has left the
  execution plane and is waiting. Only `waiting_approval` has a live
  runtime source today (§22).

### 13.3 Handshake protocol (frozen)

```text
validated --request_dispatch--> intent(dispatch) outbox row + event
    queue accepts   --receipt accepted-->  scheduled   (binds intent_id +
                                           idempotency_key; records
                                           runtime_task_uuid)
    queue rejects   --receipt rejected-->  validated   (stateless event
                                           dispatch_rejected; pending
                                           intent cleared; re-dispatch
                                           mints a NEW intent)
scheduled --receipt started--> running
running   --receipt waiting_input|waiting_approval|paused--> waits
waits     --receipt resumed--> running
any post-dispatch nonterminal --receipt failed--> failed
any post-dispatch nonterminal --receipt cancelled--> cancelled
```

- **Dispatch identity and idempotency**: the dispatch is identified by
  `intent_id` and deduplicated by `idempotency_key` (§13.1); an
  `accepted`/`rejected` receipt must name an OUTSTANDING intent
  (`receipt_unbound` otherwise; a receipt for a revoked intent refuses
  `receipt_superseded`).
- **WorkSpec/report binding**: intents carry `work_spec_sha256` and
  `report_sha256`; every receipt carries `work_spec_sha256`; a receipt
  whose digest does not match the workflow refuses `receipt_unbound`.
- **Runtime task UUID**: minted by the runtime at acceptance (its
  namespace, per the spine's `runtime_task_uuid` description). If the
  artifact pre-declares `runtime_task_uuid`, the acceptance receipt must
  match it; otherwise the accepted value is recorded and every later
  receipt must carry the same value (`runtime_uuid_mismatch`).
- **Duplicate and delayed receipts**: exact duplicate (`receipt_id` +
  digest) replays as an accepted no-op; same `receipt_id` with a
  different digest refuses `receipt_conflict`. Delivery MAY be delayed
  and redelivered at-least-once; the adapter must deliver receipts for
  one workflow in causal order, and the reducer's legality gate enforces
  it: a receipt illegal in the current state refuses
  `receipt_out_of_order` (or `workflow_terminal`), mutates nothing, and
  is safely redeliverable after its predecessors. Redelivery is the
  remedy only for a receipt that ARRIVED EARLY; a receipt that can never
  become legal — one whose transition already happened, or any receipt on
  a terminal workflow — refuses permanently and is dropped. Refusal is
  the ledger declining to record a fact it cannot place, never a request
  for infinite retry.
- **Cancellation intent and acknowledgement**: §5.3 — local-immediate
  before acceptance; two-phase (`cancel_requested` event → `cancelled`
  receipt) after. A second `request_cancel` while one is pending refuses
  `cancel_already_pending`. The runtime may also cancel unilaterally
  (receipt without `cancels` linkage), which is recorded with initiator
  `runtime`.
- **Failure before observed acceptance**: `revoke_dispatch` withdraws an
  outstanding intent (event `dispatch_revoked`, cancel intent emitted so
  the adapter can drop the queued record if it still can); a `rejected`
  receipt clears it; local cancellation revokes it. In all three, any
  LATE `accepted` receipt for that intent refuses `receipt_superseded`.
  These three are ADVISORY on the runtime side, not authoritative: if the
  queue had already committed the row, the task keeps running, its later
  receipts land on a `validated` or terminal workflow and refuse, and a
  subsequent re-dispatch mints a NEW intent and a NEW idempotency key —
  which the queue, deduping on that key, accepts as a SECOND task for the
  same WorkSpec. AOS neither prevents nor detects this; §22 declares it
  and a human reconciles. At-least-once delivery makes redelivery safe;
  it does not make the revoke race safe, and this contract does not claim
  it does.
- **Source of truth**: the AOS ledger is authoritative for lifecycle
  state, admission, approvals, success judgment, and what was asked of
  the queue (intents). The runtime is authoritative for queue
  membership, leases, workers, attempts, and the `runtime_task_uuid`
  namespace. Receipts are the only path runtime facts enter the ledger;
  intents are the only path ledger decisions reach the queue.

### 13.4 Record schema status

All six record schemas minted here (`aos.workflow-command/v1`,
`aos.workflow-event/v1`, `aos.workflow-snapshot/v1`,
`aos.workflow-queue-intent/v1`, `aos.workflow-queue-receipt/v1`,
`aos.workflow-approval-fact/v1`) are internal canonical-record payloads in
the established `aos.*` house style — deliberately NOT U-X1 registry
artifacts (D-v0.4.73). The queue records cross a repository boundary, but
to exactly ONE known counterparty that pins them by content hash at the
U-W2 milestone tag (blueprint §5.1 vendoring rule); the registry-growth
threshold (three independent consumers, or signature/attestation across a
trust domain) is the named promotion trigger, and promotion would be
additive new identities, never a mutation of these.

## 14. Persistence, replay, and transactions

Layered choice (D-v0.4.79) — all four options from the freeze combine, in
their honest roles: a pure in-memory kernel (§9); a local append-only
workflow ledger plus derived snapshot; local outbox/inbox tables; and a
separate runtime adapter implementation (U-W2.R, other repository).

### 14.1 Schema version 6 (six new tables; frozen shapes)

`db.SCHEMA_VERSION` becomes `"6"`. Migration `u-w2-workflow-state-v6`
(5 → 6) is purely additive: six empty tables created FK-parent-first
under their real names from the same `db.py` constants a fresh init uses
(the 4 → 5 idiom; the 3 → 4 freeze obligation is NOT triggered because
none of the frozen-history constants is edited). The byte-identity and
purity claims are scoped exactly as the live U-A3 precedent scopes them
(`tests/test_v04_routing_handoffs.py`): fresh-init and migrated
`sqlite_master.sql` are byte-identical FOR THE SIX NEW TABLES — creating
them directly under their real names is what removes the `ALTER RENAME`
quoting artifact — and the step function `_workflow_state_v6(conn)`
reads no existing table, rebuilds nothing, re-stamps nothing, and reads
no clock. The FRAMEWORK around it does bump `meta.schema_version` and
write one `events.emit` journal row per step (which reads the clock);
those two tables are excluded from the comparison, exactly as the live
precedent excludes them. All existing U-M1 guarantees (backup-first,
re-read under lock, per-step whole-database `foreign_key_check`, one
event per step) apply unchanged.

1. `workflows` — the derived snapshot projection. Columns: `id` PK,
   `task_id` NOT NULL FK `tasks(id)`, `work_spec_sha256` UNIQUE NOT
   NULL, `report_sha256` NOT NULL, `snapshot_sha256` NOT NULL,
   `registry_version` NOT NULL, `compile_status` CHECK
   (`valid`,`warning`,`requires_external_authority`),
   `work_spec_document` NOT NULL, `report_document` NOT NULL, `state`
   CHECK (the thirteen states), `revision` NOT NULL CHECK ≥ 1,
   `policy_version` NOT NULL CHECK ≥ 1, `approval_required` CHECK (0,1),
   `dispatch_intent_id` NULL, `cancel_intent_id` NULL,
   `runtime_task_uuid` NULL, `queue_route` NULL, `created_at`,
   `updated_at`, `content_sha256` NOT NULL (no default — the house
   rule). Structural CHECKs: `dispatch_intent_id IS NULL OR state =
   'validated'`; `cancel_intent_id IS NULL OR state IN
   ('scheduled','running','waiting_input','waiting_approval','paused')`;
   `(state IN ('compiled','validated','awaiting_approval')) →
   runtime_task_uuid IS NULL` (spelled as a CHECK). Both intent columns
   are PENDING POINTERS, and only that: `dispatch_intent_id` holds an
   intent awaiting an `accepted`/`rejected` receipt and is CLEARED when
   either arrives or when the intent is revoked — which is why `scheduled`
   need not appear in its CHECK. `cancel_intent_id` holds ONLY a
   two-phase cancellation awaiting a `cancelled` receipt; the cancel
   intents emitted by `revoke_dispatch` and by pre-dispatch
   `request_cancel` are outbox-only and never set it, which is what makes
   its CHECK satisfiable in `validated` and `cancelled`. Every intent
   ever emitted remains in `workflow_intents` with its `status`; the two
   columns are the snapshot's fast path, not the record. Mutable columns
   (`state`, `revision`, the two pending-intent ids,
   `runtime_task_uuid`, `queue_route`, `updated_at`, `content_sha256`)
   move only together with event/command rows in one transaction — the
   `agent_handoffs` hash-coupled projection precedent; the snapshot
   hash is the canonical digest of the `aos.workflow-snapshot/v1`
   payload.
2. `workflow_events` — append-only history. `id` PK, `workflow_id` NOT
   NULL FK, `seq` NOT NULL CHECK ≥ 1, UNIQUE(`workflow_id`,`seq`),
   `event` CHECK (the seventeen names), `from_state` NULL, `to_state`
   NULL (both CHECK-bound to the state enum when present, plus a CHECK
   forbidding `from_state = to_state`), `revision` NOT NULL,
   `policy_version` NOT NULL, `command_id` NOT NULL, `command_sha256`
   NOT NULL, `actor` NOT NULL, `payload_json` NOT NULL, `created_at`
   NOT NULL, `content_sha256` NOT NULL. No code path updates or deletes
   a row (the `agent_handoff_transitions` discipline).
3. `workflow_commands` — accepted-command dedupe/replay. `id` PK,
   `workflow_id` NOT NULL FK, `command_id` UNIQUE NOT NULL, `command`
   CHECK (the nine verbs), `command_sha256` NOT NULL,
   `expected_revision` NOT NULL, `resulting_revision` NOT NULL,
   `event_seq_first` NOT NULL, `event_seq_last` NOT NULL, `created_at`,
   `content_sha256` NOT NULL. Accepted commands only; refusals store
   nothing.
4. `workflow_intents` — the outbox. `id` PK, `workflow_id` NOT NULL FK,
   `intent_id` UNIQUE NOT NULL, `intent_kind` CHECK
   (`dispatch`,`cancel`), `idempotency_key` NOT NULL, `queue_route` NOT
   NULL, `document` NOT NULL (canonical record verbatim), `status`
   CHECK (`outstanding`,`resolved`,`revoked`), `resolved_receipt_id`
   NULL, `created_at`, `content_sha256` NOT NULL. `status` +
   `resolved_receipt_id` + `content_sha256` are the only mutable
   columns, moved only inside an accepted command's transaction.
5. `workflow_receipts` — the inbox. `id` PK, `workflow_id` NOT NULL FK,
   `receipt_id` UNIQUE NOT NULL, `receipt_kind` CHECK (the nine kinds),
   `intent_id` NULL, `runtime_task_uuid` NULL, `document` NOT NULL
   (verbatim), `receipt_sha256` NOT NULL, `created_at`,
   `content_sha256` NOT NULL. Insert-once: a stored receipt IS an
   applied receipt (refused receipts store nothing).
6. `workflow_facts` — verbatim external facts. `id` PK, `workflow_id`
   NOT NULL FK, `fact_kind` CHECK (`approval`,`result`), `fact_scope`
   CHECK NULL-or-(`admission`,`runtime`) with a CHECK tying scope
   presence to `fact_kind = 'approval'`, `document` NOT NULL,
   `document_sha256` NOT NULL, `recorded_at`,
   UNIQUE(`workflow_id`,`fact_kind`,`document_sha256`),
   `content_sha256` NOT NULL.

`ids.py` gains `"workflow": "WF"` (two letters were the U-M3/U-A3
precedent; single-letter `W` is unused but `WF` reads unambiguously and
collides with nothing).

### 14.2 Authoritative rows, transactions, and crash points

- Authoritative record: `workflow_events` (plus the verbatim documents in
  `workflows` and `workflow_facts`). The `workflows` row is a DERIVED
  snapshot: every §9 snapshot field EXCEPT the two document bodies is
  rebuildable by `fold(events)`. The bodies are deliberately not in any
  event payload (§7 permits digests only), so they are admission-time
  immutable columns, re-verified against the digests the
  `workflow_admitted` event records rather than re-derived — a rebuild
  proves the stored body still hashes to the admitted digest, which is
  the tamper property that matters, and `workflows.content_sha256` covers
  those recomputed digests. "Rebuildable by `fold`" means exactly this
  and not more; a `verify` that demanded the bodies come out of history
  would report `snapshot_divergence` on every healthy workflow.
- One accepted command = ONE transaction (the `db.transaction` /
  same-transaction-event invariant, extended): CAS-update `workflows`,
  insert the event row(s), insert the `workflow_commands` row, insert
  any intent/receipt/fact row, update a resolved intent, and
  `events.emit` one AOS journal row (`entity="workflow"`, action = the
  event name; payload of digests/enums only, passed through
  `redact_tree`). All commit together or roll back together.
- Crash points: (a) before commit — nothing exists; the retried command
  re-decides identically. (b) after commit, before the adapter reads the
  outbox — the intent row persists as `outstanding`; delivery is
  re-driveable at any time (the outbox pattern); duplicate delivery is
  safe because the queue dedupes on `idempotency_key`. (c) after commit,
  before CLI output — the ledger is consistent; re-running the command
  is an exact-duplicate replay. There is no state in which a
  half-recorded transition is observable.
- Unknown/corrupt/reordered history: `verify_history` refuses on a seq
  gap or duplicate (`history_corrupt`), a recomputed event digest
  mismatch (`history_corrupt`), a from-state chain break
  (`history_corrupt`), an unknown event name (`history_unknown_event`),
  or an unknown `policy_version` (`policy_version_unsupported`). While a
  workflow's history fails verification, mutating commands on it refuse;
  read-only display remains available with an explicit integrity
  warning. `workflow verify` re-folds every history and compares against
  the stored snapshot (`snapshot_divergence` on mismatch) — it reports
  and NEVER rewrites (the doctor rule: recovery is a human restoring a
  verified backup, per RECOVERY.md, not the engine editing history).

## 15. Updateability and versioning

Frozen version surfaces (D-v0.4.80) — all stable strings or integers,
never enum ordinals:

- **Transition policy**: `TRANSITION_POLICY_VERSION = 1` (integer). The
  §5.2 matrix with the three reserved edges IS version 1. U-W3's
  activation of `compensating`/`compensated` (and any widening of
  `partial`/`unknown` handling) is version 2. Every workflow row and
  every event records the policy version it was decided under; a build
  refuses commands against a workflow whose `policy_version` it does not
  support (`policy_version_unsupported`) rather than guessing.
- **History schema**: `aos.workflow-event/v1`. **Command schema**:
  `aos.workflow-command/v1`. Unknown `/vN` refuses
  (`command_schema_unsupported` / `history_unknown_event` territory);
  there is no default-version resolution (the registry's one-identity
  rule).
- **Compatibility rules**: a build supports the current policy version
  for NEW decisions plus replay of every shipped policy version forever.
  When version 2 ships, version 1's transition table is FROZEN VERBATIM
  as history (the `_V2_MEMORY_CLAIM_DDL` frozen-history trade, applied
  to policy data): `fold` replays each event under the policy version it
  recorded, so old history never re-derives under new rules.
- **State additions**: additive only — a new state or edge requires a new
  policy version, a widened storage CHECK via a migration, and frozen
  retention of every prior version's table. **State removals**: never;
  history is immutable, and a state can only stop being REACHABLE (a
  later policy version with no inbound edges), never stop being
  readable.
- **Old-history replay**: `fold` + per-version frozen tables, above;
  `verify_history` accepts exactly the shipped versions.
- **Migration versus compatibility adapter**: SCHEMA changes ride the
  U-M1 migration framework (deliberate, backup-first, stepwise); HISTORY
  is never migrated — new engine versions adapt to old recorded versions
  at read time (frozen replay), which is what makes replay byte-stable
  across upgrades. Snapshots, being derived, may be re-folded at any
  time without a migration.
- Record vocabulary growth (new receipt kinds, new refusal reasons) is
  additive within `/v1` ONLY when old readers cannot misinterpret it —
  concretely: a new receipt kind requires a new record schema version,
  because the inbox CHECK and the reducer's closed vocabulary would
  otherwise disagree between builds; new refusal reasons are
  emission-side only and may grow with the engine.

## 16. CLI and power policy

Thirteen leaves under one new group (implementation wave, slice U-W2.3),
with `power.COMMAND_POLICY` entries in the same slice:

| Verb | Effect | Policy |
| --- | --- | --- |
| `aos workflow admit ARTIFACT_FILE REPORT_FILE` | `admit_work_spec` (files read via `protocols.read_artifact_bytes` §9 discipline) | authoritative_write, ledger |
| `aos workflow validate WF-n` | `validate` | authoritative_write, ledger |
| `aos workflow request-approval WF-n` | `request_approval` | authoritative_write, ledger |
| `aos workflow approve WF-n FACT_FILE` | `record_approval` | authoritative_write, ledger |
| `aos workflow dispatch WF-n [--route SLUG]` | `request_dispatch` | authoritative_write, ledger |
| `aos workflow revoke-dispatch WF-n` | `revoke_dispatch` | authoritative_write, ledger |
| `aos workflow cancel WF-n` | `request_cancel` | authoritative_write, ledger |
| `aos workflow receipt WF-n RECEIPT_FILE` | `record_queue_receipt` | authoritative_write, ledger |
| `aos workflow result WF-n ENVELOPE_FILE` | `record_result` | authoritative_write, ledger |
| `aos workflow show WF-n [--json]` | snapshot + history display (bounded, redacted) | read_only |
| `aos workflow list [--state S] [--json]` | list instances | read_only |
| `aos workflow verify [WF-n]` | fold-and-compare integrity check | read_only |
| `aos workflow export-intents DIR` | write outstanding outbox records as files for the adapter (idempotent, content-addressed filenames) | derived_write |

(The wave-1 transport is explicit file exchange — records out via
`export-intents`, records in via `receipt` — which is transport-neutral
by construction and implements no
network.) `expected_revision` is read from the live row by the CLI shell
immediately before deciding, inside the same transaction as the CAS — the
CLI is a convenience wrapper; the engine still enforces the guard.

## 17. Exclusions

The §0.2 list, verbatim, plus: no doctor change in this unit (workflow
integrity checking lives in `aos workflow verify`; folding it into doctor
is a later unit's decision); no Obsidian mirror rendering of workflow
rows; no memory claims written; no `.claude/**` content; no edits to
other worktrees or repositories from the agentic-os slices; the
Atomic Agents evaluation repository is not read.

## 18. Implementation slices and exact paths

All agentic-os slices land as ordered commits on
`v0.4-u-w2-workflow-state-engine` inside the ONE frozen PR
(`feat(v0.4): U-W2 — deterministic workflow state engine`), delivered
through the U-P2 gate; the tag `milestone/v0.4-u-w2-workflow-state-engine`
follows the merge. The runtime slice is a separate repository and a
separate PR, stated here so the cross-repository change is explicit.

### Slice U-W2.1 — pure kernel (repository `agentic-os`)

- Commit subject: `feat(v0.4): U-W2.1 — pure workflow reducer and record
  vocabulary`
- Paths: `agentic_os/workflow_engine.py` (new);
  `agentic_os/workspecs.py` (modified: ONLY the two public acceptance
  wrappers, behavior-identical); `tests/test_v04_workflow_engine.py`
  (new).
- Public API: `WORKFLOW_STATES`, `WORKFLOW_COMMANDS`, `WORKFLOW_EVENTS`,
  `WORKFLOW_REFUSAL_REASONS`, `WORKFLOW_RECEIPT_KINDS`,
  `TRANSITION_POLICY_VERSION`, `TRANSITION_MATRIX` (data),
  `WorkflowRefusal`, `WorkflowDecision`, `AdmissionFacts`, `decide`,
  `fold`, `verify_history`, the record-builder/verifier functions;
  `workspecs.accept_work_spec`, `workspecs.accept_compile_report`.
- Tests: §19 rows 1–14. Docs: none. Migration/CLI/protocol: none.
- Acceptance:
  `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v
  tests.test_v04_workflow_engine` plus the §20 suite-wide commands.

### Slice U-W2.2 — persistence (repository `agentic-os`)

- Commit subject: `feat(v0.4): U-W2.2 — workflow ledger, outbox/inbox,
  and revision CAS`
- Paths: `agentic_os/workflow_store.py` (new); `agentic_os/db.py`
  (modified: `SCHEMA_VERSION = "6"`, six DDL constants, table-list
  tuple, schema composition); `agentic_os/migrations.py` (modified: the
  5 → 6 step and registry entry); `agentic_os/ids.py` (modified: the
  `WF` prefix); `tests/test_v04_workflow_store.py` (new).
- Public API: `workflow_store.submit(conn, command_document) ->
  StoreOutcome` (decide + CAS + append + outbox/inbox + journal, or a
  refusal), `workflow_store.rebuild(conn, workflow_id)`,
  `workflow_store.verify(conn, workflow_id | None)`, read
  helpers.
- Tests: §19 rows 15–20. Migration decision: `u-w2-workflow-state-v6`,
  purely additive (§14.1). CLI/protocol: none.
- Acceptance: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v
  tests.test_v04_workflow_store` plus the §20 commands.

### Slice U-W2.3 — CLI, power policy, docs (repository `agentic-os`)

- Commit subject: `feat(v0.4): U-W2.3 — workflow CLI, power policy, and
  docs`
- Paths: `agentic_os/cli.py` (modified: the `workflow` group, §16);
  `agentic_os/power.py` (modified: thirteen `COMMAND_POLICY` entries);
  `README.md` (modified: one new unit section);
  `tests/test_v04_workflow_cli.py` (new); and the two Wave-0 documents
  this freeze already wrote — `DECISIONS.md` (modified: the prepended
  D-v0.4.71–82 section) and
  `agentic-os-v0.4-u-w2-workflow-state-engine-contract.md` (new). Wave 0
  commits nothing (§21), so these two land here; naming them is not
  optional bookkeeping — every prior unit's implementation commit carried
  its `DECISIONS.md`, `README.md`, and contract document together
  (U-W1 `65e8be1`, U-K1/U-T1 `009e984`), and the exhaustiveness rule
  below would otherwise declare this unit's own delivery a replan.
- Tests: §19 rows 21–22. Protocol: none.
- Acceptance: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v
  tests.test_v04_workflow_cli` plus the §20 commands.

### Slice U-W2.R — runtime queue adapter (repository `ai-company-runtime`; EXPLICIT cross-repository change)

- Repository: `ai-company-runtime` (private). Branch (theirs):
  `feat/aos-u-w2-queue-adapter`. PR title (theirs):
  `feat: AOS U-W2 workflow queue adapter (intent/receipt records v1)`.
- Boundary: consumes `aos.workflow-queue-intent/v1` files, enqueues onto
  the existing Postgres queue (setting the row's attempt budget from the
  embedded WorkSpec, §13.1), produces `aos.workflow-queue-receipt/v1`
  files from the runtime's queue, lease, and attempt TABLES (`task_queue`,
  `task_attempts`). Those tables and their repository functions exist
  today; the worker process that would populate the execution-phase rows
  does not yet (§22), so wave 1 exercises `accepted` plus hand-authored
  receipts. Pins both record shapes BY
  CONTENT HASH against the agentic-os tag
  `milestone/v0.4-u-w2-workflow-state-engine` (the blueprint §5.1
  vendor-by-hash rule) — that tag is the compatibility milestone; no
  separate compatibility tag is minted.
- Constraints: no read or write of `aos.db`; no import of `agentic_os`
  code; its own tests and delivery process. Nothing in the agentic-os PR
  depends on this slice existing; until it ships, the file-exchange CLI
  is exercised by tests and by hand.

Any path outside the tables above appearing in any later U-W2 wave is
`FAIL — REPLAN REQUIRED`, not a quiet extension.

## 19. Test matrix (frozen)

`tests/test_v04_workflow_engine.py` (rows 1–14),
`tests/test_v04_workflow_store.py` (15–20),
`tests/test_v04_workflow_cli.py` (21–22):

1. Every legal transition in §5.2 drives with its named driver and
   produces the frozen event named by the §7 receipt-kind → event
   mapping (a bijection over the nine kinds) or the §7 command mapping;
   the matrix in code equals the matrix in this contract (data-compared,
   cell by cell).
2. Every illegal cell refuses `illegal_transition` /
   `workflow_terminal` FOR STATE-CHANGING DRIVERS; the five stateless
   accepted commands of §5.2 traverse no cell and are asserted to be
   accepted, not refused. `compensating → failed` refuses
   `transition_reserved` against a synthetic `compensating` snapshot;
   `running → compensating` and `compensating → compensated` are
   asserted to have NO driver in either closed vocabulary (the
   §5.2 no-driver rule) rather than to refuse, because they cannot be
   attempted. Terminal-state immutability holds under every command
   including receipts and results.
3. Deterministic snapshots/events: identical `(snapshot, command,
   facts)` yield byte-identical decisions; derived intent ids and
   idempotency keys are pure functions of history.
4. Exact revision behavior: +1 per accepted command (stateless commands
   included); `revision_mismatch` on stale and future
   `expected_revision`.
5. Reducer-side determinism under repetition: `decide` is never handed a
   duplicate (§9), so the engine file asserts that re-deciding the same
   refused command refuses identically and that re-deciding the same
   accepted command from the same snapshot yields byte-identical events
   and intent. The store-side replay and `command_conflict` assertions
   are row 15's, where the `workflow_commands` lookup lives.
6. Queue intent/receipt binding: acceptance binds `intent_id` +
   `idempotency_key`; unbound, superseded, and conflicting receipts
   refuse with their exact reasons.
7. Delayed/out-of-order receipts: `started` before `accepted` refuses
   `receipt_out_of_order` and succeeds after redelivery in order;
   duplicates replay as no-ops.
8. WorkSpec admission: all five §11 verifications, each failure with its
   exact reason; both documents stored verbatim; digests recomputed;
   `workflow_exists` on same-digest re-admission; task facts enforced.
9. All six U-W1 compile statuses: three blocking statuses refuse;
   `requires_external_authority` admits and cannot dispatch without an
   approval fact; `warning` and `valid` admit; no blocking status can
   reach `scheduled` by any command sequence (property-style sweep).
10. Approval receipt binding: digest and declared-ref binding, scope
    rules, `approval_already_satisfied`, `approval_fact_missing` on a
    `resumed` receipt out of `waiting_approval` without a fact,
    revocation absent (no vocabulary path).
11. Evidence-gated success: the full §12.2 predicate including the
    blank-proof discount, attempt budget, `result_inconsistent`,
    `partial`/`unknown` refusal, `fail → failed`, binding refusal on a
    digest-mismatched envelope.
12. Cancellation races: local cancel with outstanding intent revokes and
    emits the cancel intent; late `accepted` refuses
    `receipt_superseded`; two-phase cancel end-to-end; unilateral
    runtime cancellation; `cancel_already_pending`.
13. Caller-mutation isolation: mutating any input document or any
    returned structure after the call changes nothing observable.
14. No direct I/O in the reducer: an AST import-discipline test over
    `workflow_engine.py`'s OWN import statements (the live
    `test_import_graph_is_closed` idiom), asserting the allowlist frozen
    in §9 — `protocols`, `workspecs`, `secretscan`, `utils`/`AosError`,
    `dataclasses`, `hashlib`, `re`, `annotations` — and the absence of
    `datetime`, `os`, `sqlite3`, `subprocess`, `socket`, `random`,
    `time`; plus a decide-under-monkeypatched-clock determinism check
    and the §13.1 pin asserting the local UUIDv8 construction is
    byte-equal to `workspecs._uuid8_from_digest`. The assertion is on
    direct imports, never the transitive closure (`protocols` imports
    `os` and `datetime` legitimately).
15. History replay, snapshot rebuild, and store-side dedupe:
    `fold(events)` equals every stored snapshot field except the two
    verbatim documents after every scripted journey, and those bodies
    re-hash to the digests the `workflow_admitted` event recorded;
    `verify` passes. Exact-duplicate `submit` returns
    `StoreOutcome.replay = True` with the original events and resulting
    revision, no new event, no revision change, no new intent row and
    `intent is None`; a same-`command_id`/different-digest duplicate
    refuses `command_conflict`.
16. Corrupt/reordered/unknown-version history: seq gap, digest
    mismatch, chain break, unknown event name, unknown policy version —
    each refuses with its exact reason; mutating commands refuse on a
    corrupt history; `snapshot_divergence` reported, nothing rewritten;
    `fold` replays every event under the `policy_version` it recorded,
    so a history recorded under a supported version folds identically
    after an engine upgrade (future policy-version compatibility).
17. Transactionality: a forced failure at each §14.2 crash point leaves
    no partial state (the patched-`events.emit` rollback proof, the ops
    precedent); CAS loses cleanly under a simulated concurrent writer.
18. Migration 5 → 6: fresh-init and migrated `sqlite_master.sql`
    byte-identical FOR THE SIX NEW TABLES; the step function touches no
    existing row and reads no clock, with `events` and `meta` excluded
    from the comparison because the framework itself bumps the version
    and journals one row per step (the live
    `tests/test_v04_routing_handoffs.py` scoping, reused verbatim);
    version gate refuses v5 databases in normal commands with the
    standard message.
19. No shared database access: the store touches only `aos.db`; intent
    export writes files only; nothing opens any other database
    (asserted by auditing the store's SQL and filesystem surface).
20. U-W3/U-W4/U-W5/U-W6 exclusions are mechanical: no retry loop
    (`partial` refusal proves no second attempt), no
    checkpoint/resume/compensation surface exists
    (`transition_reserved` proves the edges), no interrupt or monitor
    module, no Temporal import anywhere in the unit.
21. CLI: every §16 verb maps to its command; refusals exit 1 with the
    bounded message; `--json` output is canonical and value-safe; power
    modes degrade the thirteen leaves per their frozen classes.
22. Compatibility with the existing task/run lifecycle: admission
    requires an open task; task `done` still requires task-plane
    evidence (`mark_done` untouched); no workflow command mutates
    `tasks`/`runs` rows; the full existing suite passes byte-unchanged.

## 20. Verification (implementation waves)

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q agentic_os tests tools aos.py aos_hooks.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_workflow_engine
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_workflow_store
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_workflow_cli
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
python3 tools/gen_protocols.py
python3 tools/verify_ci_workflow.py
git diff --check
```

## 21. Delivery identity

- Branch: `v0.4-u-w2-workflow-state-engine`
- Worktree: `/home/daksh/Projects/agentic-os-u-w2`
- Base: `0a69a1c1654671cd48577e23252a9c06e2cffba9`
- PR title: `feat(v0.4): U-W2 — deterministic workflow state engine`
- Tag after merge: `milestone/v0.4-u-w2-workflow-state-engine`
- Delivery flows through the U-P2 protected gate (PR + required checks);
  Wave 0 itself stages nothing, commits nothing, and pushes nothing.
- The U-W2.R adapter ships separately in `ai-company-runtime` (§18) and
  is not part of this PR or tag.

## 22. Known limitations (declared, not discovered later)

- The engine records reported runtime facts; it cannot detect a runtime
  that stops reporting (no heartbeat, no timeout — no clock). Liveness
  monitoring is U-W4's; until then a stalled workflow is found by a
  human reading `aos workflow list`.
- `snapshot_sha256` from the compile report is recorded as the
  compiler's attestation, not re-derived (the snapshot itself is not
  presented at admission); a caller who compiled against a stale
  registry snapshot is visible only through the recorded digest.
- Approval facts bind an opaque `approval_ref` and a provenance string;
  WHO may approve is a governance policy this unit does not judge, and
  approval revocation has no v1 path (deferred to U-W5).
- `partial`/`unknown` outcomes park a workflow in `running` until the
  runtime reports a terminal fact or U-W3 ships richer semantics —
  deliberate, per the no-retry exclusion. A human cannot shortcut this:
  post-dispatch cancellation is advisory (next bullet).
- **Post-dispatch cancellation is dormant.** The live
  `ai-company-runtime` queue has no cancellation status — `TASK_STATUSES`
  is `pending|running|succeeded|failed|rejected|requires_approval` and
  the `ck_task_queue_status` CHECK admits nothing else — and the
  repository exposes no cancel path. Until the runtime grows one,
  `aos workflow cancel` on a post-dispatch workflow records
  `cancel_requested` and a cancel intent and nothing more: the workflow
  stays in its pre-cancel state until the task terminates on its own, a
  second cancel refuses `cancel_already_pending`, and the `cancelled`
  receipt kind and terminal state are unreachable after dispatch. Adding
  runtime cancellation is a named FUTURE RUNTIME change; it is not part
  of U-W2.R, and U-W2 deliberately claims no cancellation it cannot
  effect.
- **Three receipt kinds have no live source.** Of the nine frozen kinds,
  the runtime can source `accepted` (enqueue), `started` (claim),
  `waiting_approval` (park), `resumed` (approval resume) and `failed`
  (finalize/exhaust); `rejected` comes from adapter-side validation.
  `waiting_input`, `paused` and `cancelled` have no corresponding runtime
  fact today, so `waiting_input` and `paused` are unreachable states in
  wave 1. The kinds stay frozen in `/v1` on purpose: §15 makes a NEW
  receipt kind require a new record-schema version, so trimming them now
  would guarantee a `/v2` the moment the runtime grows those states.
- **Runtime-internal retry is invisible to the ledger.** The queue
  requeues transient failures and lease expiries `running → pending →
  running` without leaving its execution plane, and U-W2 emits no receipt
  for that churn (§13.2). The adapter must align budgets at enqueue
  (§13.1); if it does not, a task that succeeded on a later attempt
  reports an `attempt` §12.2 gate 3 refuses and the workflow parks in
  `running`. Conversely, a runtime that calls its retry path on a task
  enqueued with a budget of 1 strands that task in `pending` — the live
  claim query fences on `attempt_count < max_attempts` while the retry
  update does not — which AOS sees only as silence.
- **Revocation before observed acceptance is advisory.** `revoke_dispatch`
  and pre-dispatch `request_cancel` cannot un-enqueue a row the queue
  already committed. The task keeps running, its later receipts refuse
  and are dropped, and a re-dispatch mints a new idempotency key that the
  queue accepts as a SECOND task for the same WorkSpec. U-W2 neither
  prevents nor detects this; a human reconciles.
- **Runtime trace values cannot cross into the ledger.** AOS requires a
  32-hex W3C `trace_id` with UUID correlation/causation ids; the runtime
  mints prefixed opaque ids (`trace_<hex>`, `cause_<hex>`). A receipt
  therefore omits its `trace` — it is optional — and cross-plane
  correlation in wave 1 is by `work_spec_sha256` and `runtime_task_uuid`
  only.
- **The private runtime has the queue schema but no worker yet.**
  `task_queue`/`task_attempts` and their repository functions exist;
  `services/` is empty and no production caller claims or finalizes a
  task. Execution-phase receipts therefore have no producer until the
  runtime's own worker slice ships, and wave 1 exercises the handshake
  through `accepted` plus hand-authored receipt files.
- **The task check is admission-time only.** `ops.mark_done` and
  `ops.set_task_status` are untouched (§0.3) and workflow-blind, so a
  human may close a task while its workflow is `running` or holds an
  outstanding intent; U-W2 neither prevents nor detects it. Admission
  does not require the task to be `ready`, so a workflow may dispatch
  against an untriaged task that `start_run` would refuse. The workflow
  plane's `succeeded`/`failed` and the run plane's `RUN_OUTCOMES` are
  independent records of the same work and may disagree; reconciliation
  is the human act of §12.2 step 6.
- **A WorkSpec may declare zero required evidence.** The live schema
  admits `expected_result.min_evidence_count = 0` and the compiler calls
  it `valid`, so such a workflow reaches `succeeded` with no evidence —
  by the author's digest-bound declaration, not by any engine override,
  and without the journaled reason the task plane's `--no-evidence`
  demands (§5.3, §12.2).
- Wave-1 transport is explicit file exchange through the CLI; nothing
  pushes intents or pulls receipts automatically until U-W2.R exists in
  the runtime repository.
- The AOS `events` journal row for a workflow transition duplicates
  facts already in `workflow_events`; this redundancy is deliberate (one
  system-wide journal, one workflow-scoped history) and reconciled by
  digests, not by prose.

*This contract is the audit surface for U-W2: an implementation behavior
the sections above do not license is a defect, whichever file it lives
in.*

---

# Agentic OS v0.4 — U-W2 governed contract amendment A1 (U-W2.2 mechanical-path closure)

Unit: U-W2 — deterministic workflow state engine (landed). Amending wave:
U-W2.2 — deterministic workflow store, Wave 0.
Amends: the original contract body above (frozen 2026-07-25, decisions
D-v0.4.71 … D-v0.4.82), landed in commit
`aedbc499f9a45a8316cf62a55288b67165f881a3`, merged as PR #20 at
`63de8c953f2613a79d6e1bb6052646c669894863`, tagged
`milestone/v0.4-u-w2-workflow-state-engine`.
Original-body hash:
`409745bbba541cb81a40da5384a97127db40c38f8f8e116f334706c70dc53aaf`
(SHA-256 of this file as landed — 98,556 bytes, ending at the italic
audit-surface line and its newline; the first 98,556 bytes of this file
are byte-identical to the landed file, and one blank line plus the `---`
separator that opens this amendment follow them).
Amendment baseline: `63de8c953f2613a79d6e1bb6052646c669894863` (= HEAD =
`origin/main` = the merge-base = the milestone tag target at amendment
time).
Amendment frozen: 2026-07-26. Branch: `v0.4-u-w2-2-workflow-store`;
worktree: `/home/daksh/Projects/agentic-os-u-w2-2`.
Decisions: D-v0.4.95 (recorded in `DECISIONS.md` with the U-W2.2 Wave 0
decisions D-v0.4.83 … D-v0.4.94).
Provenance: the independent combined audit of the U-W2.2 Wave 0 candidate
(2026-07-25; lead auditor plus one independent read-only auditor; verdict
`FAIL — REPLAN REQUIRED`), finding accepted in full; resolved in the
governed U-W2.2 replan session of 2026-07-26 (one lead architect, one fresh
independent pre-amendment auditor, one fresh independent post-repair
verifier).

This is a governed amendment, not a rewrite — the mechanism of the U-P2
trust-boundary amendment (`agentic-os-v0.4-u-p2-trust-boundary-amendment.md`,
D-v0.4.45 … D-v0.4.50), applied to this contract. It supersedes **only** the
clauses enumerated in §A.3.1. Every other clause of the original contract
remains in force verbatim; the original body is not edited, deleted, or
reworded. Where this amendment and the original body conflict, this
amendment is authoritative; everything not named in §A.3.1 is not
superseded.

One representation difference from the U-P2 precedent, itself governed and
recorded here as the byte-level change it is: the U-P2 amendment is a
sibling document, but the governed U-W2.2 replan session is authorized to
write exactly three repository paths — `DECISIONS.md`, this file, and
`agentic-os-v0.4-u-w2-2-workflow-store-contract.md` — and no fourth. This
amendment is therefore carried INSIDE the amended contract file as an
append-only addendum. The preservation invariant is machine-checkable
rather than merely declared: the original body remains the exact byte
prefix of this file, equal to
`git show 63de8c953f2613a79d6e1bb6052646c669894863:agentic-os-v0.4-u-w2-workflow-state-engine-contract.md`,
and the landed commit itself is immutable history. The file-level hash
necessarily changes with this addendum; the original-body hash above is the
frozen reference.

## A.1 The audit finding this amendment resolves

Five landed statements are jointly unsatisfiable, and the impossibility
lives in this contract, not in the U-W2.2 candidate:

1. §0.1/§14.1 freeze `db.SCHEMA_VERSION = "6"` inside slice U-W2.2.
2. That bump mechanically falsifies hard schema-version assertions in
   eight existing test modules and requires one drop loop in each of the
   three historical fixtures (the complete inventory is §A.4.3; the
   necessity of every item and the absence of a twelfth file were verified
   against the live tree, and commit `7c5fea4` — the U-A3 4 → 5 bump —
   touched exactly this class of file for exactly these reasons).
3. §0.3 declares "every existing test, and every existing fixture"
   untouched.
4. §19 row 22 requires "the full existing suite passes byte-unchanged."
5. §18's slice U-W2.2 table names exactly five paths, §18 closes with
   "Any path outside the tables above appearing in any later U-W2 wave is
   `FAIL — REPLAN REQUIRED`, not a quiet extension.", and D-v0.4.81
   declares "the exact file table in §18 is exhaustive."

Items 3–5 forbid exactly the edits item 1 forces. The audited candidate
attempted to resolve this inside its own subordinate contract ("the loud
amendment U-W2 §18 demands"); the audit correctly found that reading
unlawful — the §18 sentence names a verdict and authorizes nothing, and a
subordinate contract cannot amend its landed parent. The lawful resolution
is this governed amendment to the landed contract itself, through the
established U-P2 mechanism.

## A.2 What this amendment changes, and what it does not

This amendment changes PATH AUTHORITY and DELIVERY IDENTITY only. It adds
no state, command, event, receipt kind, refusal reason, matrix edge, table,
column, CHECK, API function, transaction step, or record schema, and it
removes none. The reducer boundary (§9), revision and dedupe semantics
(§10), admission (§11), approval and evidence facts (§12), the queue
handshake (§13), persistence and crash-point rules (§14), updateability
(§15), the CLI table (§16, U-W2.3's), the exclusions (§0.2, §17), the test
matrix (§19), and the known limitations (§22) all stand unchanged.
Ownership is preserved exactly: U-W2.1 (landed) owns the pure kernel;
U-W2.2 owns local persistence; U-W2.3 owns CLI, power policy, README, and
refusal journaling; U-W2.R owns the private-runtime adapter in its own
repository against its own database; U-W3 owns retry, checkpoint, resume,
and compensation; U-W4/U-W5/U-W6 as frozen. The no-shared-database rule
stands: nothing here authorizes any CLI, queue-worker, retry, checkpoint,
or private-runtime work, and the local and runtime databases remain never
shared.

The distinction this amendment draws, and the whole of its new authority:

- A **semantic implementation path** carries new behavior (the five §18
  slice-table paths for U-W2.2, unchanged here).
- A **mechanical schema-pin edit** is a forced consequence of the frozen
  `SCHEMA_VERSION = "6"` inside an EXISTING test or fixture: a version
  literal rebased `5`/`"5"` → `6`/`"6"`, a migration-registry or plan-list
  equality gaining the one new step, an ordinal-bearing test-method name
  renamed to stay truthful, one guard assertion re-scoped to the new
  ceiling (§A.4.3, declared singly), one migration-target literal rebased,
  and one fixture drop loop. Such edits add no assertion, delete no test,
  skip nothing, and weaken nothing.
- An **architecture document** is the wave's own decision record and
  contract text, which every prior unit landed with its implementation
  commit.

Only the second and third categories are added to the closed U-W2.2 path
set, each by name in §A.4.

## A.3 Exact supersession scope

### A.3.1 Superseded clauses

1. **§18, slice U-W2.2, the "Paths:" list** — "Paths:
   `agentic_os/workflow_store.py` (new); `agentic_os/db.py` (modified:
   `SCHEMA_VERSION = "6"`, six DDL constants, table-list tuple, schema
   composition); `agentic_os/migrations.py` (modified: the 5 → 6 step and
   registry entry); `agentic_os/ids.py` (modified: the `WF` prefix);
   `tests/test_v04_workflow_store.py` (new)." — Superseded by §A.4: those
   five paths remain, unchanged in content and responsibility, and the
   closed slice inventory is extended to the nineteen paths of §A.4.
   Nothing else in the U-W2.1, U-W2.3, or U-W2.R slice definitions is
   touched.
2. **§18, the closing rule** — "Any path outside the tables above
   appearing in any later U-W2 wave is `FAIL — REPLAN REQUIRED`, not a
   quiet extension." — Superseded by §A.5 ONLY in what "the tables above"
   denotes: the §18 tables as amended by §A.4. The rule itself is
   preserved verbatim and continues to fire on every path outside the
   amended tables.
3. **§0.3, the closing clause of the untouched list** — "…`pyproject.toml`,
   every existing test, and every existing fixture." — Superseded by §A.4.3
   for EXACTLY the eleven files named there and EXACTLY their enumerated
   edit classes. For every other existing test and fixture — and for every
   other path §0.3 names — §0.3 remains in force verbatim, including
   "Existing artifacts remain valid without edits."
4. **§19 row 22, the final clause** — "the full existing suite passes
   byte-unchanged." — Superseded by: the full existing suite passes; every
   existing test and fixture file OUTSIDE the eleven §A.4.3 paths is
   byte-unchanged; the eleven receive exactly the §A.4.3 edits, no test is
   deleted, skipped, or weakened, and exactly one assertion is re-scoped
   and renamed (§A.4.3, `test_no_version_six_transition_exists`). Every
   other clause of row 22 stands.
5. **§1, the D-v0.4.81 index entry's closing claim** — "the exact file
   table in §18 is exhaustive." — Superseded by: the exact file table in
   §18, AS AMENDED BY §A.4, is exhaustive. The landed D-v0.4.81 ledger
   entry itself stays byte-identical history in `DECISIONS.md`; D-v0.4.95
   supersedes its five-path enumeration and its one-PR delivery clause,
   extending and never rewording it (the D-v0.4.44 → D-v0.4.50 precedent).
6. **§18 preamble and §21, the one-PR delivery identity, as applied to
   slices U-W2.2 and U-W2.3** — "All agentic-os slices land as ordered
   commits on `v0.4-u-w2-workflow-state-engine` inside the ONE frozen PR
   (`feat(v0.4): U-W2 — deterministic workflow state engine`), delivered
   through the U-P2 gate; the tag `milestone/v0.4-u-w2-workflow-state-engine`
   follows the merge." — and slice U-W2.2's "Commit subject: `feat(v0.4):
   U-W2.2 — workflow ledger, outbox/inbox, and revision CAS`". Superseded
   by §A.6, which records the supersession that ratified practice already
   made. §21 stands as the accurate record of the U-W2/U-W2.1 delivery
   that occurred.
7. **§14.2, one reading of the journal clause** — "and `events.emit` one
   AOS journal row (`entity="workflow"`, action = the event name; …)" —
   Any reading under which a multi-event command writes ONE journal row is
   superseded: `action` IS the event name, so the clause is read as one
   journal row PER APPENDED WORKFLOW EVENT. This resolves an ambiguity; no
   transaction semantics change.

### A.3.2 Explicitly not superseded

Everything else in the original body remains in force, including: the §0.1
in-scope list (schema version `"6"` itself — the cause stands; this
amendment makes it implementable); the §0.2 not-in-scope list in full;
§0.3 for every path outside §A.4.3; the §1 decision index apart from the
one D-v0.4.81 claim named above; §2–§17 in full (dependencies, threat
model, ownership outcome B, states and the 13×13 matrix, commands, events,
refusal reasons, the pure reducer and snapshot record, revision/dedupe,
admission, approval and evidence facts, the queue handshake and record
schemas, persistence/schema v6/transactions/crash points, updateability,
CLI, exclusions); §18's slice definitions for U-W2.1, U-W2.3, and U-W2.R,
including U-W2.3's own path list and its Wave-0-documents paragraph; §19
rows 1–21 and every clause of row 22 except the one named above; §20; §21
as historical record; §22 in full; and the closing audit-surface sentence.
D-v0.4.71 … D-v0.4.80 and D-v0.4.82 are untouched.

## A.4 The amended closed U-W2.2 path inventory (nineteen paths)

This table REPLACES the five-path slice list as the complete, closed,
exhaustive U-W2.2 inventory. Per-path detail — why each changes, the exact
edit class, whether it is semantic or mechanical, and the acceptance test
that covers it — is frozen in the U-W2.2 contract
(`agentic-os-v0.4-u-w2-2-workflow-store-contract.md` §19), which is
subordinate to this amendment and must enumerate exactly these paths.

### A.4.1 Production (4) — semantic; unchanged from the original slice list

```text
agentic_os/workflow_store.py    new       the store module (U-W2.2 §8–§18)
agentic_os/db.py                modified  SCHEMA_VERSION "6"; six DDL constants;
                                          six table-name constants; WORKFLOW_TABLES;
                                          SCHEMA_SQL composition
agentic_os/migrations.py        modified  _workflow_state_v6; WORKFLOW_STATE_V6;
                                          MIGRATIONS gains the one 5 → 6 entry
agentic_os/ids.py               modified  PREFIXES["workflow"] = "WF"; docstring clause
```

### A.4.2 New focused test (1) — semantic; unchanged from the original slice list

```text
tests/test_v04_workflow_store.py  new     the U-W2.2 §20 matrix, rows S1–S24
```

### A.4.3 Mechanical schema-pin and fixture edits (11) — forced by `SCHEMA_VERSION = "6"`

Frozen edit classes, and no others: (a) version-literal rebase `5`/`"5"` →
`6`/`"6"`; (b) migration-registry/plan-list equality gains exactly the
`(5, 6, "u-w2-workflow-state-v6")` step; (c) ordinal-bearing test-method
rename; (d) the single guard re-scope, declared here; (e) the single
migration-target rebase, declared here; (f) the fixture drop loop
`for table, _ddl in reversed(db.WORKFLOW_TABLES): DROP TABLE`, placed
before the existing `ROUTING_HANDOFF_TABLES` loop. Line numbers are
evidence anchors at the amendment baseline; the method names are the
stable identities.

```text
 6  tests/test_core.py                (a) test_schema_version_recorded (:116)
 7  tests/test_v02_migrations.py      (a) :199; (b) :211, :226, :234, :1075, :1084;
                                      (c) test_production_registry_is_the_four_production_steps (:201)
 8  tests/test_v02_power_modes.py     (a) test_schema_version_is_whatever_the_one_declaration_says (:1380)
 9  tests/test_v03_memory_claims.py   (a) test_fresh_init_creates_the_current_schema_version (:191)
10  tests/test_v03_memory_graph.py    (a) :253, :256; (b) :280, :314, :322; (a) :288;
                                      (d) test_no_version_six_transition_exists (:290-294) — the
                                          predicate re-scopes to the new ceiling (`> 5` → `> 6`), the
                                          method renames, and the docstring restates the guard: the
                                          suite then asserts the 5 → 6 step EXISTS and nothing
                                          transitions past 6. This is the one edit whose assertion
                                          meaning is rebased rather than re-literaled, declared here;
                                      (e) test_corrected_retry_succeeds_exactly_once —
                                          `self.migrate(target="5")` → `"6"` (:715), keeping the
                                          doctor exit-0 assertion (:721-722) true under a v6 build
11  tests/test_v04_agent_passports.py (a)+(c) test_fresh_init_is_version_five_with_both_agent_tables
                                      (:205-208); (b) :229, :262;
                                      (c) test_registry_is_exactly_the_four_steps_in_order (:219)
12  tests/test_v04_agent_catalog.py   (a)+(c) test_schema_stays_version_five (:851-855);
                                      (a)+(c) test_schema_stays_5_and_migration_state_is_untouched
                                      (:1381-1392)
13  tests/test_v04_routing_handoffs.py (a)+(c) test_schema_version_is_five (:343-346, three literals);
                                      (b)+(c) test_registry_has_the_new_fourth_step_in_exact_order
                                      (:348, :358); (a)+(b)+(c)
                                      test_migration_status_and_plan_report_four_to_five (:363-372);
                                      (a) :379, :433, :1062; (a) len(MIGRATIONS) 4 → 5 (:1063);
                                      (a) MIGRATIONS[-1].migration_id (:1065)
14  tests/fixtures/v1_workspace.py    (f) one loop (:156 region)
15  tests/fixtures/v2_workspace.py    (f) one loop (:179 region)
16  tests/fixtures/v3_workspace.py    (f) one loop (:120 region)
```

The nine method renames authorized by classes (c) and (d), exhaustively:
`test_production_registry_is_the_four_production_steps`,
`test_no_version_six_transition_exists`,
`test_fresh_init_is_version_five_with_both_agent_tables`,
`test_registry_is_exactly_the_four_steps_in_order`,
`test_schema_stays_version_five`,
`test_schema_stays_5_and_migration_state_is_untouched`,
`test_schema_version_is_five`,
`test_registry_has_the_new_fourth_step_in_exact_order`,
`test_migration_status_and_plan_report_four_to_five`. No other existing
test method is renamed, added, deleted, skipped, or weakened.

### A.4.4 Architecture documents (3)

```text
DECISIONS.md                                              modified  the prepended
    U-W2.2 Wave 0 section, decisions D-v0.4.83 … D-v0.4.95; everything below the
    prepend stays byte-identical
agentic-os-v0.4-u-w2-workflow-state-engine-contract.md    modified  THIS amendment,
    appended; the original body byte-preserved as the exact prefix
agentic-os-v0.4-u-w2-2-workflow-store-contract.md         new       the U-W2.2
    Wave 0 architecture contract
```

The landed §18 already settled that a wave's documents belong in its
implementation inventory ("Wave 0 commits nothing (§21), so these two land
here; naming them is not optional bookkeeping — … the exhaustiveness rule
below would otherwise declare this unit's own delivery a replan"); this
amendment applies that settled rule to U-W2.2's own documents.

### A.4.5 Completeness

No twentieth path exists. Verified at the amendment baseline,
independently by two auditors: the only literal schema-version pins in the
tree are in the eight §A.4.3 test modules; every remaining
`sqlite_master` enumeration is a membership, subset, or absence assertion
that six added tables cannot break; the fixtures are the only builders of
historical workspaces; `pyproject.toml` packages the `agentic_os` package
by allowlist and needs no edit; CI discovers tests by pattern and needs no
edit; no production module outside §A.4.1, no tool, and no documentation
file outside §A.4.4 requires any change.

## A.5 Closure — this amendment is not an expansion mechanism

The §18 rule continues in force over the amended tables, verbatim in
effect: any path outside the tables above, as amended by §A.4, appearing
in any later U-W2 wave is `FAIL — REPLAN REQUIRED`, not a quiet extension.

This amendment authorizes exactly one delivery: the U-W2.2 implementation
described by the U-W2.2 contract at this baseline, over exactly the
nineteen §A.4 paths, in exactly the two §A.7 commits. It grants no
standing authority of any kind: no future schema-version bump, no later
U-W2 wave, and no other unit inherits any path permission from it. A
future mechanical necessity — including the same class of version-pin edit
in U-W2.3 or any later unit — requires its own governed amendment through
this same mechanism. No production, packaging, protocol, CLI, migration,
delivery-control, or unrelated documentation file is authorized by this
amendment beyond the nineteen named paths, and within the eleven §A.4.3
paths nothing beyond the frozen edit classes (a)–(f) is authorized.

## A.6 Delivery-identity supersession (recording ratified practice)

The original §18/§21 delivery model — three ordered slice commits inside
one U-W2 PR with one tag at its merge — was superseded in ratified
practice when slice U-W2.1 landed ALONE: commit
`aedbc499f9a45a8316cf62a55288b67165f881a3` with subject `feat(v0.4): add
deterministic workflow state engine` (not the frozen slice subject),
merged as PR #20 (`63de8c95…`), with `milestone/v0.4-u-w2-workflow-state-engine`
minted at that merge. This amendment declares what that practice made
true: the remaining slices land as per-slice PRs.

- U-W2.2: branch `v0.4-u-w2-2-workflow-store`; PR title `feat(v0.4):
  U-W2.2 — deterministic workflow persistence`; tag after merge
  `milestone/v0.4-u-w2-2-workflow-store`; commits per §A.7. The original
  slice commit subject is superseded by the §A.7 subjects.
- U-W2.3: delivers as its own PR against the then-current base; its
  branch, PR title, tag, and commit identity are frozen at its own Wave 0
  against this amended contract — not silently, and not here. The two
  U-W2 Wave-0 documents the original §18 U-W2.3 paragraph expected to
  land with U-W2.3's commit in fact landed with U-W2.1 in `aedbc49…`
  (ratified practice, above), so that paragraph's two-documents clause is
  already discharged and U-W2.3 carries no Wave-0-document obligation
  from it.
- U-W2.R: unchanged (separate repository, separate PR, pins by content
  hash at the U-W2 milestone tag, exactly as §18 froze it).

## A.7 Landing

Mirroring the U-P2 Wave 0.5 landing model (D-v0.4.50: a governed amendment
lands as its own documentation-only commit, independently visible, before
any implementation file is staged), the U-W2.2 delivery is exactly two
ordered commits on `v0.4-u-w2-2-workflow-store`, inside the one U-W2.2 PR,
through the U-P2 gate:

1. `docs: adopt U-W2 path amendment and freeze U-W2.2 store architecture`
   — exactly the three §A.4.4 documents.
2. `feat(v0.4): add deterministic workflow store` — exactly the sixteen
   §A.4.1–§A.4.3 implementation paths.

No implementation path may be staged before commit 1 exists. Wave 0 of
U-W2.2 (the session that produced this amendment) stages nothing and
commits nothing. This amendment does not retroactively modify U-W2.1's
landed bytes: `agentic_os/workflow_engine.py`, `agentic_os/workspecs.py`,
and `tests/test_v04_workflow_engine.py` remain byte-identical at the
amendment baseline, and the landed history of this contract and
`DECISIONS.md` is preserved as frozen bytes (prefix and suffix
respectively).

## A.8 Verification that this amendment did not become an escape hatch

Checkable, and checked before landing:

1. Prefix identity: bytes 1–98,556 of this file equal the landed original
   (`git show 63de8c95…:agentic-os-v0.4-u-w2-workflow-state-engine-contract.md`).
2. `DECISIONS.md` suffix identity: the working file ends with the exact
   landed bytes; D-v0.4.1 … D-v0.4.82 byte-identical; new decisions are
   exactly D-v0.4.83 … D-v0.4.95, contiguous and unique.
3. Closed enumeration: the U-W2.2 contract §19 lists exactly the nineteen
   §A.4 paths; its §19.3 edit inventory matches §A.4.3 exactly, including
   the nine renames, the one guard re-scope, and the one target rebase.
4. No expansion language: this amendment and the U-W2.2 contract name
   every authorized path individually, contain no open path category, no
   related-files or as-needed phrasing, no non-exhaustive enumeration
   marker, and no standing licence for future bumps; §A.5's one-delivery
   clause is present.
5. The delivery is two commits over nineteen paths and nothing else; the
   repository state at freeze shows exactly the three §A.4.4 documents
   changed and nothing staged.

## A.9 Rejected alternatives

- **Rewriting the landed contract in place** — frozen contracts are
  immutable history; amendments supersede, history stays byte-identical
  (D-v0.4.33, D-v0.4.45, D-v0.4.50 precedent).
- **A sibling amendment document** (the literal U-P2 form) — a fourth
  repository path, outside the governed replan session's authorized write
  set; the append-only addendum preserves the same invariant
  machine-checkably (§ preamble).
- **The candidate's self-amendment** (`§19.3` of the audited U-W2.2
  candidate declaring the paths itself) — a subordinate contract cannot
  amend its landed parent; this was the audited defect.
- **Dropping schema v6 from U-W2.2** — it would strand the landed §14
  persistence architecture without a store, contradict §0.1, and merely
  move the same amendment to a later wave.
- **Landing the test edits as a quiet extension** — exactly what §18
  forbids; the amendment exists so the edits are loud, closed, and
  finite.
- **A general mechanical-edit licence for future bumps** — the audited
  candidate's "has always required and always will" phrasing; rejected
  because a standing licence is an escape hatch. Each future bump earns
  its own amendment.

## A.10 Decision index (added by this amendment)

D-v0.4.95 — governed amendment A1: the U-W2.2 slice inventory is the
closed nineteen-path set of §A.4; §0.3/§18/§19.22's application to the
eleven mechanical paths and the one-PR delivery identity are superseded as
enumerated in §A.3.1; D-v0.4.81 is extended, never reworded; no standing
expansion authority is created.

# Agentic OS v0.4 — U-W2 governed contract amendment A2 (canonical workflow identity binding)

Appended, not merged. Every byte above this line — the landed U-W2 contract
and governed amendment A1 — is preserved verbatim as this file's exact
prefix, exactly as A1 preserved the landed body. A2 supersedes only the
clauses it quotes, and only for the U-W2.2 delivery.

Baseline this amendment is written against:

```text
docs commit          91075d7cb3b94013242b36c777baa59ee37500f9
this file (prefix)   0b936635d4a4be44080c57b023ef43a23ae4feb07be95c4c2567fe7be09221fe
                     123,153 bytes, preserved as bytes 1–123,153
DECISIONS.md         2f02f7eaeecfe3851d89f10d498d2e684b94f6393f80368008aa9e34356bfaf7
U-W2.2 contract      261f4a82e721e8183336b30e35139d8d1ceb3c02a6eba3f91a112cb8f365ccf7
base                 63de8c953f2613a79d6e1bb6052646c669894863
```

Commit `91075d7…` is NOT rewritten, amended, squashed, or rebased. This
amendment lands as a second, independently visible documentation-only
commit above it (§A2.9), which is the same U-P2 D-v0.4.50 landing model A1
used, applied a second time.

The subordinate application of this amendment — the per-clause supersession
text, the exact new DDL, the exact new payload members, and the frozen new
test rows — is U-W2.2 governed contract addendum B1, appended to
`agentic-os-v0.4-u-w2-2-workflow-store-contract.md`. B1 is subordinate to
A2 and may add nothing A2 does not authorise, exactly as §19 is subordinate
to §A.4.

## A2.1 The audit finding this amendment resolves

The U-W2.2 implementation wave reported `FAIL — REPLAN REQUIRED` on finding
F-001. The finding is a three-clause contradiction inside the frozen
architecture, not an implementation defect, and it was reproduced
independently in the replan session against the bytes named above:

```text
1. U-W2.2 §5.1 — `workflows.id` is the reducer's DERIVED identity, and
   "always lies in [1, 2**63-1] = ids.MAX_ID".
2. U-W2.2 §5.8 — the four row-hash payloads bind `workflow_id` as a direct
   INTEGER ("integers bound directly"; the table reads
   "`id`, `workflow_id` (ints)").
3. U-W2.2 §5.8 — the digest is frozen as
   `sha256(protocols.serialize_canonical(payload)).hexdigest()`, and
   `protocols.serialize_canonical` refuses every integer outside
   ±(2**53-1) with `ProtocolError[integer_out_of_range]`
   (`agentic_os/protocols.py:60,188`).
```

Any two hold; all three cannot. `workflow_engine._workflow_identity`
(`agentic_os/workflow_engine.py:623-644`) derives the identity as
`int.from_bytes(tagged_digest[:8], "big") >> 1` with `0` mapped to `1`, so
the domain is exactly `[1, 2**63-1]` and

```text
P(identity <= protocols.INT_MAX) = 2**53 / 2**63 = 2**-10
```

— 1023 of every 1024 valid workflow identities are unsealable. Measured on
2000 real WorkSpec digests, 1998 exceeded the canonical bound. This is the
ordinary path, not an edge case, and it fires on the FIRST accepted
`admit_work_spec`: bound exactly as §5.8 freezes it, admission raises
`WorkflowStoreError("store_unavailable")` and persists nothing.

The implementation wave continued under one self-declared deviation ("D1")
that bound the identity by a sha256 leaf of its bare decimal digits. That
deviation was correct in kind and **unauthorised in fact** — no governed
document licensed it — which is precisely why the wave reported a replan
rather than landing. A2 ratifies a canonical binding, and B1's §B1.2 states
the exact form; the bare decimal representation D1 used is NOT that form
and is superseded along with the clause that provoked it.

## A2.2 The canonical workflow identity representation (frozen)

**There is exactly one canonical representation of a workflow identity in
this unit, and it is the one the architecture already froze: the rendered
identity string**

```text
"WF-" + str(workflows.id)
```

This is not a new representation. It is byte-identical to:

- `workflow_engine._workflow_identity(work_spec_sha256)`, the minting
  derivation (U-W2 §13.1 idiom), which is what every event digest was
  sealed over;
- the store's own renderer, pinned byte-equal to that derivation by U-W2.2
  §5.1 and §20 row S3;
- the `workflow_id` member U-W2.2 §7.4 reconstitutes into every
  `aos.workflow-event/v1` record;
- the `workflow_id` U-W2.2 §7.2 step 6 already compares;
- the `WF-<n>` string every public store type carries and every public
  store function accepts;
- the string `ids.parse_id(text, "workflow")` round-trips back to the
  integer for every value in `[1, ids.MAX_ID]`.

Its properties, each required and each checkable:

```text
total          defined for every identity in [1, 2**63-1]
unambiguous    injective; distinct ids render distinct strings
stable         a pure function of the id; identical across runs and builds
round-trip     ids.parse_id(render(n), "workflow") == n for all n in domain
bounded        at most 22 characters ("WF-" + 19 digits) << MAX_STRING_CHARS
canonical      one spelling; no padding, no separators, no alternates
compatible     the identity rendering already frozen by §5.1 and §7.4
closed         one frozen renderer; not a representation escape hatch
```

**Binding.** Because the canonical representation is TEXT, it binds into a
§5.8 row-hash payload exactly the way §5.8 already binds every other text
column — by its sha256 leaf, under the `<name>_sha256` member name:

```text
"workflow_id_sha256": sha256(("WF-" + str(workflows.id)).encode("utf-8")).hexdigest()
```

No new identity algorithm is introduced, no new serializer is introduced,
no bound is relaxed, and no repository path is added. The digest function
stays exactly `sha256(protocols.serialize_canonical(payload)).hexdigest()`,
and every other §5.8 rule — the `record_schema` key, direct integer binding
for the small rowid columns, `None` passed through, `content_sha256`
excluded — is preserved unchanged.

## A2.3 Exact supersession scope

A2 supersedes the following clauses, and no others. Each is quoted in B1
with its replacement text; the enumeration here is the authority, B1 is the
application.

### A2.3.1 Superseded clauses

```text
S1  U-W2.2 §5.8   the four row-hash payload rows' "`workflow_id` (int)"
                  member, and "integers bound directly" as applied to
                  `workflow_id`
S2  U-W2.2 §7.2   step 6's inclusion of `id` (as `workflow_id`) among the
                  SEVENTEEN live member-backed comparisons
S3  U-W2.2 §8.4   the `store_unavailable` row's "plus the one deliberate
                  non-exception trigger"
S4  U-W2.2 §13.3  "Injection is by three frozen mechanisms, together
                  covering every enumerated point"
S5  U-W2.2 §3     "no tampered row can make the store ACCEPT a command it
                  would otherwise refuse", as an unqualified claim
S6  U-W2.2 §5.1   the `workflows` DDL, which carries no `id` CHECK
S7  U-W2.2 §8.3   `read_workflow` / `list_workflows` "plus an integrity
                  verdict", as an unscoped claim; §15.4 step 4's
                  row-hash-only wording; and §15.3's "Mutating commands
                  refuse" read as covering a rows-only divergence
S8  U-W2.2 §14.2  "Exact duplicate … returns the ORIGINAL outcome", as an
                  unqualified claim
S9  U-W2.2 §18.1  "Every digest is recomputed from the stored bytes at
                  every use", as applied to `workflow_receipts.
                  receipt_sha256` and `workflow_facts.document_sha256`
S10 U-W2   §A.6   "commits per §A.7"
    U-W2   §A.7   "exactly two ordered commits"
    U-W2.2 §19.5  "Exactly two ordered commits inside the one U-W2.2 PR"
```

Four further clauses are not superseded but are CLOSED — they were silent,
and silence in this unit is a defect by the U-W2.2 contract's own closing
sentence ("an implementation behavior the sections above do not license is
a defect, whichever file it lives in"). B1 §B1.9 freezes them:

```text
C1  `rebuild`, `verify`, `read_workflow` and `read_history` on a workflow
    identity that has no row
C2  the `where` a `VerifyReport` carries when ONLY row hashes diverge
C3  the derivation of the store's closed-task status constant
C4  the `snapshot` a refusal carries when the workflow's history does not
    verify
```

### A2.3.2 Explicitly NOT superseded

```text
the thirteen states, nine commands, seventeen events, forty-three refusal
reasons, nine receipt kinds, two intent kinds, the 13x13 transition matrix,
TRANSITION_POLICY_VERSION and SUPPORTED_POLICY_VERSIONS

the six U-W2 §13.4 record schemas and the U-X1 registry

schema version 6, the six table NAMES, the six tables' column lists, and
every existing CHECK, UNIQUE, and FOREIGN KEY in them

the public API surface of U-W2.2 §8 — seven functions, six public
dataclasses, three infrastructure codes, the import allowlist

the transaction model (§10, §11), CAS (§12), the crash POINTS themselves
(§13.1, §13.2 — K0-K16 and KA0-KA9 are unchanged; only §13.3's mechanism
list is repaired), replay and dedupe identities (§14.1), retention (§14.4),
history verdicts (§15.2), and the runtime/queue boundary (§4, §7.1, §17)

the closed nineteen-path inventory of §A.4, unchanged in membership

D-v0.4.1 through D-v0.4.95, byte-identical, including D-v0.4.95
```

## A2.4 The real integrity binding, in place of a tautology

U-W2.2 §7.2 step 6 lists `id` (as `workflow_id`) among seventeen
member-backed projection columns "compared against its rebuilt
counterpart". That comparison cannot fail. §7.4 reconstitutes every event
record's `workflow_id` FROM the same `workflows.id` column, so `fold`
returns the identity the column supplied and step 6 compares
`"WF-" + str(id)` against `"WF-" + str(id)`. It is a tautology, and a
tautology stated as an integrity check is a defect, not a defence — the
same class of finding the audit already confirmed and repaired for the two
document bodies.

The identity's REAL integrity binding is stated by §7.4 and is retained
unchanged: the sealed `aos.workflow-event/v1` digest covers `workflow_id`,
so a spliced `workflows.id` makes every event digest fail to recompute and
the workflow reads `history_corrupt` rather than folding under a false
identity. A2 therefore:

- reduces step 6 to SIXTEEN live member-backed comparisons;
- retains the identity comparison as a DECLARED redundancy backstop that
  cannot diverge by construction, so a future refactor that breaks §7.4's
  reconstitution is still caught;
- requires the backstop to be labelled as such wherever it appears, so it
  is never again read as the identity's protection;
- requires a discriminating test that a spliced identity is
  `history_corrupt` (B1 §B1.10 row S27).

The identity is additionally bound into all four §5.8 row hashes by §A2.2,
which is a second independent binding the frozen text did not previously
have in any satisfiable form.

## A2.5 Confirmed contradictions repaired

Each was reproduced against the bytes named above before it was accepted.

**Receipt and fact document integrity (S9, S7).** §18.1 promises every
digest is recomputed "at every use", and §15.4 step 4 recomputes only the
four row hashes. But §5.8 binds `workflow_receipts.receipt_sha256` and
`workflow_facts.document_sha256` by their COLUMN leaf, so a row hash cannot
see a forged body: rewriting `workflow_facts.document` alone leaves every
row hash recomputing. A2 requires `verify` to re-digest both stored
documents against their digest columns beside the row hashes, and requires
§15.4 step 4 to say so.

**`store_unavailable` trigger count (S3).** §8.4 enumerates "the one
deliberate non-exception trigger". There are FOUR non-exception triggers,
and two further sources that are exceptions but are not `sqlite3.Error`.
A2 requires the trigger table to be exhaustive (B1 §B1.5).

**Crash-point attainability (S4).** §13.3 freezes three injection
mechanisms and claims they "together cover every enumerated point". They do
not. K4 is "inside `_insert_command`, BEFORE its row-hash finalization",
K13 is "inside `_journal`, AFTER the first of two `events.emit` calls", and
KA8 is "inside `_journal`"; patching a named helper raises before the
helper does anything, which is a different point in all three cases. A2
adds a fourth frozen mechanism — a wrapper on a NAMED internal callee of
the helper — and names the callee for each point. The crash POINTS are
unchanged; only the mechanism enumeration is repaired.

Three test-side label errors follow from the same gap and are repaired with
it: the admission matrix labels its `_journal`-entry injection KA8 when
that instant is KA7 and leaves KA8 unexercised; it patches
`_admission_facts` at entry, which is before the A3 task read rather than
KA1's "after A3, before A4"; and the receipt-bearing matrix labels a
`_journal`-entry injection K13 when that instant is K12. Every point named
by §13.1 and §13.2 must be injected at its own instant, under its own
label, by a frozen mechanism.

**The unqualified worst-case claim (S5).** §3 claims "no tampered row can
make the store ACCEPT a command it would otherwise refuse, because every
gate re-derives from bytes the same row supplies". `tasks.status` is not
such a row: §4.2 and §9.5 make it the shell-verified `AdmissionFacts` input
by design, and the store has nothing to re-derive it from. Reproduced —
flipping `tasks.status` by direct SQL turns `refused/admission_task_closed`
into `accepted` for the same envelope. A2 scopes the guarantee to the six
workflow tables and declares the `tasks` dependency explicitly.

**Missing `workflows.id` constraint (S6).** §5.1 states the invariant
("always lies in `[1, 2**63-1]`") and the DDL does not enforce it, unlike
the three sibling `>= 1` CHECKs in the same table. A `workflows.id = 0`
planted by direct SQL was a confirmed source of a leaked `AosError`. A2
authorises exactly one added constraint, `CHECK (id >= 1)`, making the
declared invariant structural. The code's totality under a hostile row is
retained, not replaced: a CHECK is not a substitute for failing closed.

**Integrity scope: readers, `submit`, and `verify` (S7).** `read_workflow`
reports `ok`, and `submit` ACCEPTS a new command, on a database where
`verify` reports `snapshot_divergence` with non-empty `divergent_rows`.
Both reproduced. §15.3's "Mutating commands refuse" is therefore false if
"fails verification" is read as `verify`'s verdict.

A2 does not widen the readers or the write gate. `list_workflows` is a
declared full scan, and recomputing four row hashes and two stored
documents per workflow inside it would make listing the ledger an O(total
rows) integrity sweep of it; adding the same work to the §7.2 gate would
put it on every command and falsify §7.2's declared cost. The decisive
reason is not cost, though: **the four row-hash tables feed no acceptance
decision.** Command dedupe compares a recomputed envelope digest against
`command_sha256`; receipt dedupe compares a recomputed receipt digest
against `receipt_sha256`; replayed events come from the re-verified
history; a fact body is recorded by the event's digest. Freezing mutations
on a divergent row hash would deny service without protecting any decision,
and §3's guarantee — as scoped by S5 — still holds under rows-only
tampering.

A2 therefore freezes the SCOPE of each verdict explicitly and scopes §15.3
to the snapshot-and-history verdict, so the difference is declared
architecture with a discriminating test rather than an undetected
divergence, and restates U-W2 §17's settled position that workflow
integrity is `workflow verify`'s surface.

**Replay on a workflow that does not verify (S8).** §14.2's exact-duplicate
rule is unqualified, and a replay returns stored events. A replay is a
mutating command's ANSWER, and §15.3 refuses mutating commands on a
workflow that fails verification, so a replay must be held to the SAME gate
a fresh command is held to — not a weaker one. The implementation verifies
the history before slicing the recorded range, which is half of it:
reproduced, a workflow with an intact history and a tampered projection
refuses a fresh command with `snapshot_divergence` while a duplicate of an
already-accepted command still returns `status="replay"` with events. A2
closes the gap in the fail-closed direction: a replay runs the full §7.2
gate — history reconstitution, `verify_history`, `fold`, splice, seal, and
the step-6 comparison — and refuses with the exact verdict when it does not
pass. Idempotence is unaffected on a healthy ledger, which is the only
ledger it was promised for.

## A2.6 Delivery identity (supersedes §A.6 and §A.7's commit count)

The U-W2.2 delivery is exactly THREE ordered commits on
`v0.4-u-w2-2-workflow-store`, inside the one U-W2.2 PR:

```text
1  91075d7cb3b94013242b36c777baa59ee37500f9
   docs: adopt U-W2 path amendment and freeze U-W2.2 store architecture
   exactly the three §A.4.4 architecture paths — ALREADY LANDED, preserved
   byte-for-byte, never rewritten

2  docs(v0.4): amend U-W2.2 workflow identity binding
   exactly the same three architecture paths — D-v0.4.96, this amendment
   A2, and U-W2.2 addendum B1

3  feat(v0.4): add deterministic workflow store
   exactly the sixteen §A.4.1–§A.4.3 implementation paths
```

Branch, PR title, tag, and base are unchanged from §A.6. No implementation
path may be staged before commit 2 exists. No amend, squash, reset, or
rebase touches commit 1 or commit 2.

Two commits became three because a governed amendment landed after the
first documentation commit rather than before it. The landing MODEL is
unchanged and is applied a second time: architecture changes land as their
own independently visible documentation-only commit, before any
implementation file is staged.

## A2.7 Path scope — unchanged, and still closed

A2 adds NO path. The inventory remains the closed nineteen paths of §A.4:
three architecture documents and sixteen implementation paths, extracted
from §A.4 and from U-W2.2 §19 and proven to normalise identically.

A twentieth path appearing in the U-W2.2 delivery is
`FAIL — REPLAN REQUIRED`, exactly as §A.5 froze it. A2 grants no standing
authority: not a future schema-version bump, not a later U-W2 wave, not
another unit, and not a further amendment to this one. The three
architecture paths are writable in commit 2 and frozen thereafter; the
sixteen implementation paths are writable in commit 3 and nowhere else.

A2 contains no open path category, no "related files" or "as needed"
phrasing, no non-exhaustive enumeration marker, and no licence for a future
quiet extension of §5.8, of the row-hash convention, of the identity
representation, or of anything else. A further representation change earns
its own amendment through this same mechanism.

## A2.8 Verification that this amendment did not become an escape hatch

Checkable, and checked before landing:

1. **Prefix identity** — bytes 1–123,153 of this file equal the file at
   `91075d7…` (sha256 `0b936635…`).
2. **`DECISIONS.md` suffix identity** — the working file ends with the
   exact bytes at `91075d7…` (sha256 `2f02f7ea…`); D-v0.4.1 … D-v0.4.95
   are byte-identical; the only new decision is D-v0.4.96, contiguous and
   unique.
3. **U-W2.2 prefix identity** — bytes 1–138,448 of the U-W2.2 contract
   equal the file at `91075d7…` (sha256 `261f4a82…`); B1 is appended.
4. **Closed enumeration** — the supersession set is exactly S1–S10 plus
   the four closures C1–C4; B1 quotes each superseded clause and adds
   nothing outside them.
5. **Full-domain feasibility** — the frozen representation is defined,
   bounded, and sealable for the minimum identity, `2**53-1`, `2**53`, and
   `2**63-1`, proven by an executable test rather than asserted.
6. **Path closure** — exactly nineteen paths; commit 2 changes exactly
   three of them; no twentieth path exists.
7. **No expansion language** — §A2.7.

## A2.9 Landing

Commit 2 stages exactly:

```text
DECISIONS.md
agentic-os-v0.4-u-w2-workflow-state-engine-contract.md
agentic-os-v0.4-u-w2-2-workflow-store-contract.md
```

and nothing else. The sixteen implementation paths remain unstaged working
changes across commit 2 and are committed once, afterwards, as commit 3.
Commit 1 is preserved exactly. Nothing is pushed, merged, tagged, or
opened as a PR by the session that creates commit 2 or commit 3.

## A2.10 Rejected alternatives

- **Binding the identity as a direct integer and raising
  `protocols.INT_MAX`** — `INT_MAX` is the integer range that survives a
  round trip through an IEEE-754 double (D-v0.3.5), a cross-boundary
  protocol guarantee of the whole repository. Raising it to fit one column
  would silently widen every canonical document in every unit. Rejected as
  disproportionate and unsafe.
- **A second serializer for row-hash payloads** — a competing canonical
  encoding is precisely the "second, competing integrity claim" §5.8
  itself calls a defect. Rejected.
- **Reducing the workflow identity to 53 bits at minting** —
  `workflow_engine._workflow_identity` is landed, frozen, byte-unchanged,
  and every U-W2.1 event digest was sealed over its output. Changing it
  would rewrite a landed unit and invalidate stored history. Rejected;
  U-W2.2 §19.4 already makes editing the reducer a replan.
- **Allocating `workflows.id` from a sequence instead** — contradicts
  §5.1, §7.5 and the reducer's own docstring, and would break the
  structural "one instance per WorkSpec" agreement between the primary key
  and `UNIQUE(work_spec_sha256)`. Rejected.
- **Binding the bare decimal string `str(workflows.id)`, or its leaf (the
  wave's unauthorised D1)** — a representation that appears nowhere else
  in the architecture. `WF-<n>` is the identity; `<n>` is an
  implementation detail of it. Freezing two spellings of the same identity
  is exactly the ambiguity this amendment exists to remove. Rejected, and
  superseded.
- **Binding the rendered identity as a RAW string member** — §5.8's
  convention is that text binds by its sha256 leaf, and every live
  row-hash precedent (`routing.py`, `agent_handoffs.py`) does exactly
  that. One raw text member would be a second deviation from the
  convention in the same clause the amendment is repairing. Rejected.
- **Rewriting commit `91075d7…` in place** — frozen commits are immutable
  history; amendments supersede and history stays byte-identical
  (D-v0.4.33, D-v0.4.45, D-v0.4.50, and A1's own precedent). Rejected.
- **Folding A2 into A1's bytes** — same reason, one level down: A1 is
  landed text. Appending A2 preserves A1 as prefix, machine-checkably.
  Rejected.
- **Making `read_workflow` recompute all four row hashes and both stored
  documents** — it would make `list_workflows`, a declared full scan, an
  O(total rows) integrity sweep of the entire ledger. `verify` exists for
  that, and U-W2 §17 already settled that integrity is `verify`'s surface.
  Rejected in favour of declaring the scope.
- **Leaving the four silences (C1–C4) undeclared** — the U-W2.2 contract's
  own closing sentence makes an unlicensed behavior a defect. Rejected.
- **Deferring the whole repair to U-W2.3** — U-W2.2 cannot land at all
  under the contradiction; deferring it would land an implementation that
  its own contract forbids. Rejected.

## A2.11 Decision index (added by this amendment)

D-v0.4.96 — governed amendment A2: the canonical workflow identity
representation is the rendered string `"WF-" + str(workflows.id)`, bound
into all four §5.8 row hashes by its sha256 leaf; §5.8's direct-integer
binding of `workflow_id`, §7.2 step 6's tautological identity member,
§8.4's trigger count, §13.3's mechanism list, §3's unqualified worst-case
claim, §5.1's unconstrained `id`, §8.3/§15.4's integrity scope, §14.2's
unqualified replay rule, §18.1's receipt/fact wording, and the two-commit
delivery identity are superseded exactly as enumerated in §A2.3.1; four
contract silences are closed; commit `91075d7…` is preserved and the
delivery becomes three ordered commits; the closed nineteen-path inventory
and §A.5's no-expansion rule are unchanged; no standing authority is
created.
