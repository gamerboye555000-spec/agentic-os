# Agentic OS v0.4 — U-W3 workflow runtime recovery (architecture contract)

Unit: **U-W3 — bounded workflow retry, checkpoint persistence, state-restoration
resume, and compensation under transition-policy version 2.**

Wave: 0 (architecture freeze). Architecture only — no production code, tests,
DDL, migrations, fixtures, CLI handlers, power entries, protocol schemas or
README prose ship in the Wave-0 commit.

Branch: `v0.4-u-w3-runtime-recovery`. Worktree:
`/home/daksh/Projects/agentic-os-u-w3`. Base:
`fef0c2b3fd8e881776b33e7a2c5d204f8e8d34c1` (= HEAD = the merge-base =
`milestone/v0.4-u-w2-3-workflow-cli^{}`). Decisions: D-v0.4.103 … D-v0.4.117,
recorded in `DECISIONS.md`.

Depends on, and consumes as landed: U-W1 (`agentic-os-v0.4-u-w1-workspec-compiler-contract.md`),
U-W2 (`agentic-os-v0.4-u-w2-workflow-state-engine-contract.md`, including
governed amendments A1, A2 and A3 carried inside that file), U-W2.2
(`agentic-os-v0.4-u-w2-2-workflow-store-contract.md`, including addendum B1),
U-W2.3 (`agentic-os-v0.4-u-w2-3-workflow-cli-contract.md`).

*This contract is the audit surface for U-W3: an implementation behavior the
sections below do not license is a defect, whichever file it lives in.*

---

## 1. Authority and historical supersessions

### 1.1 Where U-W3's authority comes from

U-W3 does not invent its licence. Three landed clauses grant it, verbatim:

- **U-W2 §5.3** — "Transitions reserved for U-W3: the three `R` edges, plus
  reinterpreting `partial`/`unknown` outcomes (§12) — all activate only via
  transition-policy version 2."
- **U-W2 §15** — "**Transition policy**: `TRANSITION_POLICY_VERSION = 1`
  (integer). The §5.2 matrix with the three reserved edges IS version 1.
  U-W3's activation of `compensating`/`compensated` (and any widening of
  `partial`/`unknown` handling) is version 2. … **State additions**: additive
  only — a new state or edge requires a new policy version, a widened storage
  CHECK via a migration, and frozen retention of every prior version's table."
- **U-W2 §12.2 gate 4** — a `fail` result "is stored verbatim as a fact and NOT
  acted on (compensation is U-W3's)."

U-W3 therefore ships transition-policy version 2, one additional state, one
additional storage version, and the four command families the reserved edges
were reserved for. It ships nothing else.

### 1.2 What U-W3 supersedes, exactly

U-W3 writes no byte of any U-W1 or U-W2 contract file. Every supersession below
is declared **here**, in U-W3's own contract, and the superseded documents are
left byte-identical. Where this contract and a clause below conflict, this
contract is authoritative for U-W3's implementation wave only; the superseded
clause remains authoritative history for the unit that wrote it.

| # | Superseded clause | Where it lives | What U-W3 replaces it with | Why |
| --- | --- | --- | --- | --- |
| S1 | "Thirteen authoritative states (§5.1)" and `len(WORKFLOW_STATES) == 13` | U-W2 §5.1 | **Fourteen** states under policy v2; the v1 thirteen-state tuple is retained verbatim as frozen history | §5.3.4 below: reusing `validated` for a post-failure attempt violates a landed storage CHECK |
| S2 | The 13×13 matrix, 25 active / 3 reserved edges | U-W2 §5.2 | policy v1's matrix frozen verbatim; policy v2's 14×14 matrix with **35 active, 0 reserved** | U-W2 §15's own frozen-retention rule |
| S3 | `WORKFLOW_COMMANDS` is nine verbs | U-W2 §6 | **thirteen** verbs | the reserved edges need drivers |
| S4 | `WORKFLOW_EVENTS` is seventeen names | U-W2 §7 | **twenty-four** names | one event per new fact class |
| S5 | `WORKFLOW_REFUSAL_REASONS` is forty-three codes | U-W2 §8 | **fifty-seven** codes | closed vocabulary, no reuse of an inexact code |
| S6 | `WORKFLOW_INTENT_KINDS = ("dispatch", "cancel")` | U-W2 §13.1 | **three** kinds, adding `compensate` | the outbox is the only channel to the executing side |
| S7 | `AdmissionFacts` is "the two ledger booleans and nothing else" | U-W2 §9 | `ShellFacts`: the two booleans **plus** the two resolved-checkpoint fields | a pure reducer cannot read a stored checkpoint row |
| S8 | `record_result` gate 3 accepts any `attempt ≤ budget` | U-W2 §12.2 | under policy v2 the reported `attempt` must **equal** the open attempt's `attempt_no` | an attempt number that names nothing is not accounting |
| S9 | `workflow_facts.fact_kind IN ('approval','result')` is the complete fact vocabulary | U-W2.2 §5.6 | **unchanged** — U-W3 adds no fact kind (§11.4) | the compensation body IS a `beast.result-envelope/v1` |
| S10 | "the thirteen §16 leaves" (C1), "9 / 3 / 1" (C2), the option table (C3), `len(WORKFLOW_STATES) == 13` (C5), `len(record_fields) == 20` (C10), the ten `BLOCKED` rows (C11) | U-W2 §16, U-W2.3 §2.2, §8.1, §9 | **seventeen** leaves; **13 / 3 / 1**; four added option rows; fourteen states; **twenty-five** `WorkflowRecord` fields; **fourteen** `BLOCKED` rows | §13 |
| S11 | C26's region-wide **fifteen-token** ban, whose contested members are `retry`, `checkpoint`, `resume`, `compensat` | U-W2.3 §9 row C26 | **narrowed**, not deleted: `checkpoint` and `compensat` permitted only inside an enumerated **seven-function** set; `retry`, `resume` and the other eleven tokens stay banned region-wide | §13.5 |
| S12 | `SCHEMA_VERSION = "6"`, `db.WORKFLOW_TABLES` is six tables | U-W2.2 §5, D-v0.4.84 | `SCHEMA_VERSION = "7"`, **eight** tables | §11 |
| S13 | The 5→6 step builds from the live `db.WORKFLOW_TABLES` | `agentic_os/migrations.py` (`_workflow_state_v6` docstring) | the step builds from a **frozen** `_V6_WORKFLOW_TABLES` copy | the docstring's own transfer clause, quoted in §11.6 |
| S14 | C22's `len(_region_nodes()) >= 13` workflow-leaf floor | U-W2.3 §9 row C22 | `>= 17` — the only C22 change; every other C22 assertion is re-asserted unchanged | §13.5 |
| S15 | the forward promise that policy v2 "will widen" `partial`/`unknown` handling | U-W2 §12.2 | policy v2 activates **neither**: `partial` and `unknown` still refuse `result_outcome_inconclusive`, and activating either is a §21 replan trigger. No other §12.2 behavior is superseded by this row | §5.3.3 |
| S16 | `test_fresh_and_migrated_sql_is_byte_identical_for_the_six_tables` — one byte-identity assertion over the `sqlite_master.sql` text of all six workflow tables | U-W2.2 §6, `tests/test_v04_workflow_store.py` | **narrowly superseded**: byte-identity is **re-asserted** for the two tables U-W3 does not rebuild (`workflow_receipts`, `workflow_facts`) and for the two new ones; the four **rebuilt** tables require **structural equivalence** instead (§11.5) | `ALTER TABLE … RENAME` may requote an identifier the original `CREATE TABLE` did not. This row narrows exactly one assertion about four rebuilt tables and relaxes nothing else about migration integrity — no row, hash, digest, count or chain assertion changes |
| S17 | "closed edit class — exactly the **eleven** mechanically forced changes enumerated below and nothing else" | **this contract**, §17.1 row 10 and §17.3's path-10 enumeration | **narrowly superseded**: path 10's closed inventory is **twelve** classes — E1–E11 verbatim, plus **E16**, the CI-runtime repair of `HostileRowTests` (§17.3). This row narrows the CLASS COUNT and nothing else. Path 10 stays path 10 of twenty-one, stays forced by the same S-rows, and still admits no deleted assertion, no dropped `subTest`, no weakened tamper case, no sampled or skipped hostile value and no loosened bound | GitHub Actions run 30964552253: `tests-python-3.12` completed all 3,215 tests successfully in 1,796.706 s and the 30-minute job timeout then cancelled protocol projection and the clean-tree check; `tests-python-3.14` reached the same timeout while the suite was still running; `workflow-integrity` and `distribution-smoke-python-3.12` passed. The landed fixture builds one complete `Journey` per hostile value, and `verify` and `list_workflows` both walk every workflow, so the fixture made itself quadratic against a database it had grown to 740 workflows. That is a test-runtime defect, not a production assertion failure, and re-running the unchanged head does not repair it. Recorded in D-v0.4.117 |

### 1.3 Explicitly NOT superseded

- U-W2 §11 (WorkSpec admission), §12.1 (approval facts), §13.2 (receipt record
  shape and the nine kinds), §13.3 (handshake protocol), §14.2 (integrity is
  reported, never repaired), §17 (exclusions).
- U-W2.2 §7.6 ("no automatic repair — ever"), §12.6 (bounded lock handling),
  §14.4 (nothing may be pruned), §18 (untrusted rows), §15 (the five-verdict
  integrity vocabulary).
- U-W2.3 §5.2/§5.3 (byte-exact accepted and refusal output), §6 (the refusal
  journal), §7 (safety obligations), §5.18 (the exit-code table), C4, C6–C9,
  C12–C25.
- U-W2.2 §5.6's `workflow_facts` shape and `workflow_receipts`' shape: both
  tables are **byte-untouched** by U-W3.
- The U-K1/U-T1 contract §0.2 and D-v0.4.56, and the U-W1 §2.2 reconciliation
  of them. See §16.

### 1.4 The historical outer-attempt-loop prose (question 12, resolved)

Two live sentences say the outer attempt loop "is U-W1's": the
`governance.invoke()` docstring at `agentic_os/governance.py:1028-1030` ("The
outer attempt loop belongs to Agentic OS (U-W1); there is no loop here to hide
a retry in") and the U-K1/U-T1 contract §0.2 / D-v0.4.56 ("the retry loop
itself is U-W1's").

U-W1 §2.2 already froze the binding meaning — "U-W1 may compile and statically
validate attempt constraints …; **runtime looping is U-W3's**" — and stated the
retouch rule exactly: "The docstring phrase itself is prose inside
`agentic_os/governance.py`, which is outside this unit's file boundary; it is
superseded by D-v0.4.59 and **may be retouched only by a unit that already
modifies that file**."

**Frozen for U-W3: `agentic_os/governance.py` is NOT in U-W3's path boundary
(§17), so U-W3 does not retouch the docstring.** The condition that would
license the edit — already modifying the file — is not met, and manufacturing a
reason to modify it in order to unlock the edit would be exactly the escape
hatch U-W2 amendment §A.9 rejected. U-W3 has no functional need for
`governance.py`: U-W3 executes nothing, calls `governance.invoke()` nowhere,
touches no `BindingRegistry`, and reads no `InvocationResult`.

The authoritative U-W3 interpretation, recorded here and nowhere else:

- The **outer attempt loop is U-W3's**, and it is not a loop at all — it is a
  sequence of separately-decided, separately-recorded workflow attempts, each
  opened by an accepted command and closed by a verified external fact. There is
  no `while` anywhere in U-W3 (§18 row W29).
- `governance.invoke()` remains **single-attempt and byte-unchanged**, and its
  docstring's parenthetical `(U-W1)` is stale prose, not a live claim. It
  misattributes the owner; it does not misstate the behavior, which is
  "at most one attempt, no hidden retry" — true under every reading.
- The U-K1/U-T1 contract stays byte-untouched. Retouching a landed contract to
  fix an attribution is unrelated documentation cleanup, which §2.2 excludes.

The retouch obligation **transfers unchanged** to the first future unit that
already modifies `agentic_os/governance.py` for a functional reason.

---

## 2. Scope and non-goals

### 2.1 In scope (frozen here, implemented in the implementation wave)

1. **Transition-policy version 2**: the fourteenth state `retrying`, the frozen
   v1 policy data, the complete v2 matrix, the three activated reserved edges,
   and an explicit, recorded, forward-only policy adoption command.
2. **Bounded workflow retry**: a workflow attempt ledger; retry after a failed
   result or a retryable `failed` receipt, bounded by the artifact's
   `retry.max_attempts`.
3. **Checkpoint persistence**: `aos.workflow-checkpoint/v1`, stored verbatim,
   bounded, append-only, attempt-bound.
4. **State-restoration resume**: an `aos.workflow-restore-fact/v1` record and a
   `checkpoint_restored` event, precisely separated from U-W2's `run_resumed`
   and from U-W5's `resume_instruction`.
5. **Compensation**: entry from `running` on a verified result that reports
   `compensation.state = "pending"`, a `compensate` outbox intent, and exactly
   two terminal outcomes.
6. **Schema version 7**: two new tables, four rebuilt tables, the frozen v6
   copies, and the `u-w3-runtime-recovery-v7` migration.
7. **Four new CLI leaves** under the existing `aos workflow` group, four power
   entries, one README section.

### 2.2 NOT in scope (mechanically absent, not merely discouraged)

- **No U-W2.R implementation.** U-W3 writes nothing in `ai-company-runtime`,
  reads nothing from it, and adds no transport. Wave-1 transport stays explicit
  file exchange through the CLI (§4.3).
- **No private-runtime change of any kind**: no queue, lease, worker, backoff,
  heartbeat or cancellation change; no Postgres; no shared database.
- **No runtime lease or backoff redesign.** The private runtime's
  `retry_backoff_seconds` (30 s doubling, capped at 300 s) and its lease fencing
  are its own and are never modelled, mirrored or second-guessed in `aos.db`.
- **No semantic interrupts (U-W5).** No `beast.interrupt/v1` document is read,
  parsed, stored or acted on; `interrupt` remains a banned token in the CLI
  region (§13.5).
- **No approval revocation (U-W5).**
- **No loop-health or liveness monitoring (U-W4).** U-W3 reads no clock in the
  reducer and adds no timeout; a stalled attempt is still found by a human.
- **No durable-engine adoption (U-W6).** No Temporal, no workflow framework, no
  dependency added to `pyproject.toml`.
- **No autonomous cancellation.** Cancellation stays exactly as U-W2 froze it,
  plus one new **local** edge `retrying → cancelled` (§5.3.6). Post-dispatch
  cancellation remains dormant and advisory.
- **No U-E6 incident replay, no U-X2 continuity capsule.**
- **No unrelated documentation cleanup**: `AGENTIC_OS_BLUEPRINT.md`,
  `RECOVERY.md`, `TROUBLESHOOTING.md`, `CONTRIBUTING.md`, every landed contract
  and the README's pre-existing stale global schema-version paragraph
  (D-v0.4.102) are untouched.
- **No protocol change.** `protocols/**` and `agentic_os/protocols.py` are
  byte-unchanged; `python3 tools/gen_protocols.py` produces no diff (§12).
- **No compensation retry, no partial compensation, no compensation
  checkpoint** (§10.7, §10.9).
- **No execution.** U-W3 runs no tool, skill, model, agent, subprocess, socket,
  MCP or A2A call, and grants no approval, capability or spend.

### 2.3 Untouched

`agentic_os/protocols.py`, `protocols/**`, `agentic_os/governance.py`,
`agentic_os/models.py`, `agentic_os/passports.py`, `agentic_os/catalog.py` and
`agentic_os/catalog/*`, `agentic_os/routing.py`, `agentic_os/agent_handoffs.py`,
`agentic_os/secretscan.py`, `agentic_os/doctor.py`, `agentic_os/hooks.py`,
`agentic_os/ingest.py`, `agentic_os/events.py`, `agentic_os/ops.py`,
`agentic_os/ids.py`, `agentic_os/utils.py`, `agentic_os/workspecs.py`,
`tests/fixtures/**` (§11.7 proves why), all delivery-control files
(`.github/workflows/ci.yml`, `tools/verify_ci_workflow.py`,
`tests/test_v04_delivery_gate.py`), `tools/**`, `pyproject.toml`, and every
existing test not named in §17.

---

## 3. Terminology (the word list this contract never violates)

| Term | Means | Owner | Never means |
| --- | --- | --- | --- |
| **runtime task attempt** | a row in the private runtime's `task_attempts`, numbered by `attempt_number`, produced by its `QueueWorker` | private runtime | anything AOS counts, bounds or records |
| **workflow attempt** | one AOS-decided, AOS-recorded execution of the admitted WorkSpec, ordinal `attempt_no ∈ 1..budget` | Agentic OS / U-W3 | a runtime task attempt |
| **attempt budget** | `work_spec_document.retry.max_attempts`, default **1** when the artifact declares no `retry` block | the WorkSpec author, digest-bound | `task_queue.max_attempts` (live default **3**) |
| **runtime task binding** | the `runtime_task_uuid` AOS observed for one workflow attempt | AOS observation of a runtime fact | a claim about what the runtime did |
| **snapshot** | `aos.workflow-snapshot/v1`, the derived workflow projection U-W2.2 rebuilds by `fold` | U-W2.2 | a checkpoint |
| **checkpoint** | `aos.workflow-checkpoint/v1`, bounded execution-restoration state produced OUTSIDE AOS | the executing side | a snapshot; a workflow projection |
| **queue resumption** | a `resumed` receipt leaving a wait state; event `run_resumed` | U-W2 | proof that a checkpoint was restored |
| **checkpoint restoration** | a verified `aos.workflow-restore-fact/v1`; event `checkpoint_restored` | U-W3 | a state change |
| **resume instruction** | `beast.interrupt/v1` `kind: "resume_instruction"` / `resume_instruction_ref` | U-W5 | anything U-W3 reads |
| **retry** | re-execution of work that advances `attempt_no`, is bounded by `retry.max_attempts`, and changes what the workflow claims about the world (D-v0.4.91) | U-W3 | lock waiting, command replay, intent or receipt redelivery, runtime task-attempt retry |
| **compensation** | an undo episode entered only from `running`, concluding as `compensated` or `failed` | U-W3 decides the state; the executing side performs the act | anything a tool manifest authorizes |

---

## 4. Ownership matrix (frozen)

### 4.1 The three attempt namespaces (question 1)

| | private-runtime task attempt | **workflow attempt** | attempt budget |
| --- | --- | --- | --- |
| Source of truth | `task_attempts` (Postgres) | `workflow_events` (authoritative), projected into `workflow_attempts` | `work_spec_document.retry.max_attempts` inside the admitted, digest-bound artifact |
| Identity | `attempt_id` UUID; `UNIQUE(task_id, attempt_number)` | `(workflow_id, attempt_no)`; `UNIQUE(workflow_id, attempt_no)` | none — a scalar declaration |
| Numbered by | the runtime's `attempt_count` | AOS, monotone from 1 | the author |
| Advanced by | `claim_next_task` / `schedule_task_retry` | an observed `accepted` receipt (§6.2) | never |
| Bounded by | `task_queue.max_attempts` (row default **3**) | the attempt budget | `beast.work-spec/v1` `{"minimum": 1, "maximum": 10}` |
| Backoff | `retry_backoff_seconds`: 30 s `<<` (attempt−1), capped at 300 s | **none — AOS has no clock and schedules nothing** | n/a |
| Visible to the other side | no | no | only if the enqueuer transcribes it |

**The rule that resolves every collision:** AOS counts what AOS observed. A
runtime requeue (transient failure, lease expiry) moves `running → pending →
running` inside the runtime's own plane, emits no AOS receipt, and consumes
**no workflow attempt**. U-W3 does not duplicate, mirror, model or redesign
private-runtime task retry, and adds no `attempts`, `next_visible_at`,
`lease`, `worker` or `backoff` column anywhere in `aos.db`.

### 4.2 Plane ownership

| Concern | Owner | U-W3's relationship |
| --- | --- | --- |
| Workflow lifecycle, ledger, transition legality | Agentic OS | extends under policy v2 |
| Runtime tasks, queue leases, task attempts, task retry execution, backoff | private runtime | reads nothing, writes nothing, models nothing |
| Workflow-level retry after a failed result | **U-W3** | owns |
| Checkpoint persistence | **U-W3** (storage) / executing side (production) | stores verbatim; never produces one |
| Compensation state | **U-W3** | decides the state; never performs the act |
| Approval and spend planes | private runtime (its own) + U-W2 approval facts | untouched |
| Semantic interrupts, approval revocation | U-W5 | absent |
| Liveness / loop health | U-W4 | absent |

### 4.3 The manual file-exchange boundary (U-W2.R absent — verified)

U-W2.R is absent, and that absence is licensed by the landed U-W2 §18 ("Nothing
in the agentic-os PR depends on this slice existing; until it ships, the
file-exchange CLI is exercised by tests and by hand").

Reproduced directly against private-runtime `main` =
`d6f4a82aeb3e08d8067250489343e4242b35d07d`:

| Fact | Evidence |
| --- | --- |
| a production `QueueWorker` exists | `libs/company_runtime/company_runtime/queue_worker.py` |
| task and task-attempt persistence exist | `libs/runtime_db/runtime_db/task_queue.py`: `task_queue`, `task_attempts` |
| lease ownership and fencing exist | `locked_by`, `locked_at`, `lease_expires_at`; `claim_next_task`, `finalize_task`, `schedule_task_retry`, `requeue_expired_tasks`, `fail_exhausted_tasks` |
| task-attempt retry and backoff exist | `_is_retryable_failure` (status `failed` ∧ `error_kind == "transient"` ∧ `attempt_count < max_attempts`); `retry_backoff_seconds` |
| approval and spend planes exist | `park_task_for_approval`, `resume_approved_task`, `reject_task_for_rejected_approval`; `libs/runtime_db/runtime_db/spend_repository.py` |
| **no AOS intent reader** | zero matches for `work_spec`, `work-spec`, `workflow-queue-intent`, `agentic_os` across `libs/`, `services/`, `agents/` |
| **no AOS receipt writer** | as above |
| **no U-W2.R adapter** | as above |
| **no checkpoint machinery** | zero matches for `checkpoint` in `libs/`, `services/`, `agents/` |
| **no compensation machinery** | the only `compensat` matches are in `spend_repository.py` and are accounting entries for a budget insert race, not workflow compensation |
| **no cancellation implementation** | zero matches for `cancel` in `libs/runtime_db` and `libs/company_runtime`; `TASK_STATUSES` is `pending, running, succeeded, failed, rejected, requires_approval` and `ck_task_queue_status` admits nothing else |

**What is absent is the AOS intent/receipt translation adapter — not the
worker.** This contract states that once and never restates the superseded
"no worker" claim.

Consequences U-W3 accepts as the operating model, not as a defect:

1. Every U-W3 record crosses the boundary as a file. `workflow export-intents`
   writes the outbox; a human enqueues; a human authors or transcribes receipts,
   results, checkpoints, restore facts and compensation envelopes and feeds them
   to `workflow receipt` / `workflow result` / `workflow checkpoint` /
   `workflow restore` / `workflow compensate`.
2. The dispatch intent under policy v2 **states the budget and the attempt
   ordinal explicitly** (§9.2), so a human enqueuer has the number in front of
   them and never has to infer it.
3. AOS never assumes the runtime received or honoured the budget (§6.4).

---

## 5. Transition-policy version 2 (question 4)

### 5.1 Versioning mechanics

- `TRANSITION_POLICY_VERSION = 2`. `SUPPORTED_POLICY_VERSIONS = (1, 2)`.
- Policy version 1's **state tuple and matrix are frozen verbatim** as
  `_V1_WORKFLOW_STATES` (thirteen members, original order) and `_V1_TRANSITION_MATRIX`
  (13×13, 25 active / 3 reserved) — the `_V2_MEMORY_CLAIM_DDL` frozen-history
  trade, applied to policy data exactly as U-W2 §15 requires. `_POLICY_MATRICES`
  becomes `((1, _V1_WORKFLOW_STATES, _V1_TRANSITION_MATRIX), (2, WORKFLOW_STATES,
  TRANSITION_MATRIX))`; every lookup indexes with **its own version's** state
  tuple, so a v1 event can never be re-derived under v2 rules.
- A new admission stamps `policy_version = 2`.
- **Unknown-version behavior**: a snapshot or event whose `policy_version` is
  not in `SUPPORTED_POLICY_VERSIONS` refuses `policy_version_unsupported` and
  mutates nothing — unchanged from U-W2. A *future* version is refused, never
  guessed; a *past* version replays forever.
- **Replay**: `fold` applies each event's effect and carries that event's own
  `policy_version` forward, so a mixed history folds to the version of its last
  event. No event is ever rewritten, re-stamped or re-derived. A policy-v1 event
  carries none of policy v2's attempt members, and `fold` **invents none for
  it**: a v1 `dispatch_accepted` binds a runtime task and advances no attempt
  ordinal (§5.5). That absence is honest history, and it is exactly what §5.2's
  adoption gate exists to protect.

### 5.2 Adoption: how a v1 workflow reaches v2

Without an adoption path a workflow admitted under v1 could never retry, never
checkpoint and never compensate — and re-admission is structurally impossible
(the identity is derived from the WorkSpec digest and `UNIQUE(work_spec_sha256)`
refuses `workflow_exists`). Silently upgrading it would rewrite what it was
decided under. So adoption is an **explicit, recorded human decision**:

- Command `adopt_policy_version`, payload `{"policy_version": 2}`.
- Legal only when **all** of these hold: the workflow is **non-terminal**; its
  current `policy_version` is a supported version **strictly less** than the
  requested one; the requested version is in `SUPPORTED_POLICY_VERSIONS`; and
  the workflow satisfies the **adoption-safety predicate** below. Otherwise
  `policy_version_not_upgradable`, or `policy_version_unsupported` for an
  unshipped target, or `workflow_terminal`.
- **Stateless**: it traverses no matrix cell, changes no `state`, emits exactly
  one `policy_version_adopted` event, and consumes one revision.
- The adoption event is the one place `_build_event` stamps the **new** version
  rather than the snapshot's prior version; its payload carries
  `{"from_policy_version": <int>, "to_policy_version": <int>}`, so `fold`
  reconstructs the change from the history alone.
- Adoption is **forward-only and never automatic**. There is no downgrade, no
  `--force`, no batch adopt, and no implicit adoption inside any other verb.

#### 5.2.1 Adoption is NOT unconditionally safe

The edge-superset property is true and is asserted cell by cell by §18 row W3:
**policy v2's active-edge set is a strict superset of v1's**, every v1 edge
surviving with the same driver. What that property establishes is exactly one
thing — adoption is **transition-safe**: no move that was legal for the workflow
under v1 becomes illegal under v2, so adoption can never strand a workflow by
removing its next legal step.

It establishes **nothing about the attempt ledger**, and that is a second,
independent obligation. Policy v2 decides retry, checkpoint, restore and
compensation against an authoritative record of *which attempt is open, which
runtime task it bound, and how many attempts are used* — a record policy v1
never kept. Adopting v2 on a workflow whose attempt history is absent would put
it under a policy that reasons from accounting it does not have. Concretely, a
landed v1 workflow sitting in `running` with a live runtime task would fold to
`attempts_used = 0`; its next `request_dispatch` would reserve `attempt_no = 1`
for work already performed once, its live runtime task would have no attempt row
and would read as an orphan, and every attempt-fenced fact about it would refuse
(`receipt_unbound` / `attempt_mismatch`) with no honest way forward. An attempt
number that names nothing is not accounting (§6.4).

**Frozen adoption-safety predicate.** `adopt_policy_version` is permitted only
when at least one of these three conditions holds:

| # | Condition | Why it is safe |
| --- | --- | --- |
| A1 | The workflow is **pre-dispatch as folded**: `runtime_task_uuid` is `NULL`, `attempts_used == 0`, no `workflow_attempts` row exists, and `dispatch_intent_id` is `NULL` — nothing reserved and still pending, nothing opened, nothing consumed | there is no accounting to reconstruct, because no attempt has been reserved-and-outstanding, opened or closed; the first attempt this workflow ever has will be a policy-v2 attempt, numbered by AOS at acceptance (§6.2) |
| A2 | The workflow is **terminal** and can therefore consume no further attempt | nothing downstream will read the ledger to decide anything; adoption could not mis-account because no attempt-scoped decision remains |
| A3 | The workflow already carries **complete and internally consistent policy-v2 `workflow_attempts` history**: every `dispatch_accepted` in its folded history carries an `attempt_no`, the projection agrees with the events one for one, and the open/closed accounting is consistent | the accounting policy v2 requires already exists and was recorded under policy v2's own rules |

Any workflow satisfying none of A1–A3 refuses `policy_version_not_upgradable`
and mutates nothing.

A1 is a statement about the **folded** snapshot, not about which events the
history happens to contain, and that distinction is load-bearing in one
direction only: a `dispatch_requested` that was later **rejected or revoked**
materialised nothing (§6.2, the "abandoned" moment), and `fold` clears
`dispatch_intent_id` on `dispatch_revoked`, so such a workflow is pre-dispatch
again and satisfies A1 — its retracted reservation consumed no budget and left
no binding to reconstruct. A reservation that is **still outstanding** does not
satisfy A1, because a v1 reservation records no ordinal and an acceptance under
v2 would have nothing authoritative to number itself from (§5.5).

**Reachability of the three conditions, stated honestly.** Under the shipped
`SUPPORTED_POLICY_VERSIONS = (1, 2)`, the only adoption step is 1 → 2, so:

- **A1 is the live path** and the only one an operator exercises.
- **A2 is stated for totality and is never reached**, because the landed
  non-terminal conjunct refuses a terminal workflow first with
  `workflow_terminal`. A2 is the safety condition, not a permission: the
  legality conjuncts are stricter, and U-W3 does not loosen them.
- **A3 is stated for totality and is unreachable**, because a `workflow_attempts`
  row exists only where a policy-v2 `accepted` receipt created one (§6.2) and
  the 6→7 migration derives none (§11.5) — so no policy-v1 workflow can hold
  one — and there is no forward step out of version 2. A3 therefore requires **no
  stored-row judgment and no new `ShellFacts` member**: the predicate is decided
  from the folded history alone, and `ShellFacts` keeps the shape §1.2 row S7
  froze.

**The refusal this creates, named exactly.** A landed policy-v1 workflow in an
active post-dispatch state **must refuse adoption** whenever authoritative
workflow-attempt history is absent. The post-dispatch states, stated in full so
the gate is total: `scheduled`, `running`, `waiting_input`, `waiting_approval`,
`paused`, `retrying`, `compensating`. The last two cannot in fact hold a
policy-v1 workflow — `retrying` is not a member of the v1 state tuple and no v1
driver targeted `compensating` (§5.3.1) — so they are named for totality, not as
exercised paths, exactly as §8.4 names its unreachable states.

**What may never be done to satisfy the predicate.** Frozen prohibitions, each
an instance of "no automatic repair may fabricate authority or evidence" (§14):

- **`workflow_attempts` rows are never synthesized from historical events.**
  Adoption reads the folded history to observe *absence*; it never writes a row,
  and no U-W3 code path back-fills, reconstructs or seeds an attempt row for a
  pre-existing workflow. `workflow_store.rebuild` stays exactly what it is —
  `fold` + splice + seal, returning a snapshot document and writing no row — and
  `workflow_attempts` keeps the §11.3 cap of exactly two writes per row, the
  opening INSERT and the one closing compare-and-swap.
- **`attempt_no` is never inferred.** Not from event sequence, not from receipt
  sequence, not from `runtime_task_uuid`, and not from the current workflow
  state. A v1 history records that a dispatch was accepted; it does not record
  which ordinal that acceptance was, and no arithmetic over the ledger recovers
  what was never written.
- No `--force`, no `--repair`, no batch adopt and no implicit adoption inside
  another verb reaches around this predicate.

**The operator's path for a refused workflow.** A v1 workflow whose dispatch is
*outstanding but unaccepted* fails A1 — its `dispatch_intent_id` is set — so it
refuses; `revoke-dispatch` retracts the reservation and `fold` clears the
binding, after which the workflow satisfies A1, adopts, and re-dispatches under
policy v2 with a v2 intent that carries `attempt_no` and `attempt_budget`. A v1
workflow that has already *consumed* an attempt has no path to v2 at all: it
runs to a terminal state under policy v1, and new work is admitted as a new
WorkSpec with a new digest and a new identity. Declared in §20 item 5.

### 5.3 The complete policy-v2 transition matrix (14 × 14; frozen as data)

States, in order (index order is the matrix's row/column order):

```
compiled, validated, awaiting_approval, scheduled, running, waiting_input,
waiting_approval, paused, retrying, compensating, succeeded, failed,
cancelled, compensated
```

Terminal (unchanged, still exactly four): `succeeded`, `failed`, `cancelled`,
`compensated`.

Cell legend — `·` illegal (`illegal_transition`; from a terminal row,
`workflow_terminal`); a mark names the only legal driver: `cmd:` a command,
`rcp:` a verified queue receipt, `res:` a verified result envelope via
`record_result`, `cmp:` a verified compensation envelope via
`record_compensation`, `apr:` a verified approval fact. Creation is the one
pseudo-edge `∅ → compiled` via `admit_work_spec`.

| from \ to | compiled | validated | awaiting_approval | scheduled | running | waiting_input | waiting_approval | paused | retrying | compensating | succeeded | failed | cancelled | compensated |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| compiled | · | cmd:validate | · | · | · | · | · | · | · | · | · | · | cmd:request_cancel | · |
| validated | · | · | cmd:request_approval | rcp:accepted | · | · | · | · | · | · | · | · | cmd:request_cancel | · |
| awaiting_approval | · | apr:record_approval | · | · | · | · | · | · | · | · | · | · | cmd:request_cancel | · |
| scheduled | · | · | · | · | rcp:started | · | · | · | rcp:failed_retryable | · | · | rcp:failed | rcp:cancelled | · |
| running | · | · | · | · | · | rcp:waiting_input | rcp:waiting_approval | rcp:paused | res:fail_retryable / rcp:failed_retryable | res:compensable | res:success | res:fail / rcp:failed | rcp:cancelled | · |
| waiting_input | · | · | · | · | rcp:resumed | · | · | · | rcp:failed_retryable | · | · | rcp:failed | rcp:cancelled | · |
| waiting_approval | · | · | · | · | rcp:resumed (approval fact required) | · | · | · | rcp:failed_retryable | · | · | rcp:failed | rcp:cancelled | · |
| paused | · | · | · | · | rcp:resumed | · | · | · | rcp:failed_retryable | · | · | rcp:failed | rcp:cancelled | · |
| retrying | · | · | · | rcp:accepted | · | · | · | · | · | · | · | · | cmd:request_cancel | · |
| compensating | · | · | · | · | · | · | · | · | · | · | · | cmp:failed / rcp:failed | · | cmp:applied |
| succeeded | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| failed | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| cancelled | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| compensated | · | · | · | · | · | · | · | · | · | · | · | · | · | · |

**35 active edges, 0 reserved edges, 1 creation pseudo-edge.** Every cell not
named above is illegal in policy v2.

#### 5.3.1 Which reserved edges activate

All **three** of U-W2 §5.2's reserved edges activate under v2, and no more:

| v1 reserved edge | v2 driver | Attemptable under v1? |
| --- | --- | --- |
| `running → compensating` | `res:compensable` | no — no v1 driver targeted `compensating` |
| `compensating → compensated` | `cmp:applied` | no — no v1 driver targeted `compensated` |
| `compensating → failed` | `cmp:failed` / `rcp:failed` | yes — the one attemptable reserved edge |

`transition_reserved` stays in the refusal vocabulary and stays reachable: a
policy-v1 snapshot attempting `compensating → failed` still refuses it, because
policy v1 replays forever. It is never emitted for a v2 snapshot.

`compensating → cancelled` remains **illegal in every frozen version**, verbatim
per U-W2 §5.2: abandoning a compensation mid-flight would be a silent cleanup
failure.

#### 5.3.2 The ten new v2 edges

`scheduled → retrying`, `running → retrying`, `waiting_input → retrying`,
`waiting_approval → retrying`, `paused → retrying`, `retrying → scheduled`,
`retrying → cancelled`, plus the three activated reserved edges.

#### 5.3.3 Evidence predicates (which driver fires, exactly)

A driver name in a cell is a *classification*; the predicate below decides
which of a cell's drivers fires. Predicates read only the verified document and
the verified snapshot — never a manifest, never a compile-report finding, never
prose.

**The universal attempt fence.** Every attempt-scoped result or receipt
predicate below fires only after one shared precondition holds:

> **observed attempt == authoritative open or compensating attempt**

— that is, the attempt the document is observed to name must equal the
authoritative one: the open attempt, or, in `compensating`, the compensating
attempt recorded by `compensation_started`. A result, checkpoint or restore
fact names its attempt with an explicit integer (`attempt` / `attempt_no` /
`into_attempt_no`), and a mismatch refuses `attempt_mismatch`; a `failed`
receipt names its attempt through its `runtime_task_uuid`, which must equal
that attempt's recorded `workflow_attempts.runtime_task_uuid` binding —
`receipt_unbound` when it binds no attempt of this workflow,
`runtime_uuid_mismatch` when it names a different one (§6.2). The rows below
state the driver-specific discriminations on top of that fence; the fence is
not repeated in every cell. This is a restatement for clarity, not a new
behavior.

**Optional runtime-task corroboration on a result envelope.**
`beast.result-envelope/v1` ships `runtime_task_uuid` as an **optional**
property (the shipped schema's `required` list does not name it; its own
description calls it "the runtime's own task UUID … owned by a different
system"). U-W3 therefore treats it as **corroborating evidence and never as a
selector**:

- The **`attempt` integer alone** selects and binds the attempt. It is mandatory
  in the shipped schema, it is authoritative, and it is what the fence above
  compares.
- When `runtime_task_uuid` is **present**, it must equal the recorded binding of
  the attempt the envelope names — the open attempt for `res:*`, the
  compensating attempt for `cmp:*` (§10.8). A present value that does not match
  refuses `runtime_uuid_mismatch` and records nothing.
- When it is **absent**, nothing is refused and nothing is inferred: the
  property is optional in the shipped protocol, so its absence is a legal
  envelope, not a defect.
- A present, matching value grants **no additional authority**. It never selects
  an attempt, never resolves an ambiguity, never initiates a phase, and never
  substitutes for the `attempt` integer.

A present contradiction is never silently dropped: ignoring evidence that
disagrees with the ledger is the same class of error as fabricating evidence
that agrees with it. The comparison target is the binding folded from the
`dispatch_accepted` history — the §6.5 event-authoritative source, of which the
`workflow_attempts` row is the projection — so this gate needs no store read and
adds no `ShellFacts` member.

| Driver | Predicate |
| --- | --- |
| `res:success` | envelope spine-valid ∧ digest-bound ∧ `attempt == open attempt_no` ∧ `outcome == "success"` ∧ `retryable == false` ∧ `compensation.state ∈ {absent, "not_required"}` ∧ counted evidence ≥ `expected_result.min_evidence_count` |
| `res:fail_retryable` | `outcome == "fail"` ∧ `retryable == true` ∧ `compensation.state ∈ {absent, "not_required"}` ∧ `attempt_no < budget` |
| `res:fail` | `outcome == "fail"` ∧ `compensation.state ∈ {absent, "not_required"}` ∧ (`retryable == false` ∨ `attempt_no == budget`) |
| `res:compensable` | `outcome == "fail"` ∧ `compensation.state == "pending"` (the retry predicate is **not** consulted: compensation outranks retry) |
| `rcp:failed_retryable` | receipt kind `failed` ∧ `runtime_task_uuid` == the open attempt's recorded binding (`receipt_unbound` / `runtime_uuid_mismatch` otherwise, §6.2) ∧ `reason.retryable == true` ∧ `attempt_no < budget` ∧ an attempt is open |
| `rcp:failed` | receipt kind `failed` ∧ `runtime_task_uuid` == the recorded binding of the attempt it closes — the open attempt, or in `compensating` the attempt `compensation_started` recorded (`receipt_unbound` / `runtime_uuid_mismatch` otherwise, §6.2) — ∧ (`reason.retryable == false` ∨ `attempt_no == budget` ∨ no attempt is open) |
| `cmp:applied` | compensation envelope spine-valid ∧ digest-bound ∧ `attempt` == the compensating attempt recorded by `compensation_started` (`attempt_mismatch` otherwise, §10.8) ∧ (`runtime_task_uuid` absent ∨ == that attempt's recorded binding; `runtime_uuid_mismatch` otherwise) ∧ `outcome ∈ {"success","fail"}` ∧ `compensation.state == "applied"` ∧ counted evidence ≥ `expected_result.min_evidence_count` |
| `cmp:failed` | as above with `compensation.state == "failed"`; no evidence minimum |
| every v1 driver | unchanged, verbatim |

**`partial` and `unknown` are deliberately NOT activated under v2.** U-W2 §5.3
reserved "reinterpreting `partial`/`unknown`" to policy v2; it did not require
v2 to exercise the reservation. Frozen reasoning: `partial` and `unknown` are
honest statements of ignorance, and U-W3 cannot know *what* was partially done.
Retrying partial non-idempotent work is precisely the hazard U-W1's
`retry_idempotency_incompatible` lint exists to flag, and turning a producer's
uncertainty into an AOS claim about the world would violate the one rule this
architecture never bends. Under v2 they still refuse
`result_outcome_inconclusive` and mutate nothing; the workflow parks in
`running`. Reinterpreting them is a **replan trigger** (§21), not a silent
future widening. U-W2 §12.2's forward promise that policy v2 "will widen"
`partial`/`unknown` handling is explicitly and narrowly superseded by §1.2 row
S15: v2 activates neither, both remain refused, and no other §12.2 behavior is
superseded by that row.

#### 5.3.4 Why a fourteenth state, mechanically

A workflow whose attempt N failed retryably with attempts remaining cannot sit
in any landed state:

- `failed` is terminal, and terminal immutability is structural. Never.
- `running` would claim a live runtime task that does not exist.
- `validated` is refused by **storage**: the landed `workflows` DDL carries
  `CHECK (runtime_task_uuid IS NULL OR state NOT IN ('compiled','validated','awaiting_approval'))`,
  so a workflow that already bound a runtime task cannot be stored as
  `validated` without destroying the binding — and destroying it would erase the
  only record of which runtime task attempt 1 was. It would also re-open
  `request_approval` mid-retry and conflate "never attempted" with "attempt 1
  failed".

So `retrying` is not a naming preference; it is the only representable answer.
It is added under §15's additive rule: new policy version + widened storage
CHECK via migration + frozen retention of v1's table.

#### 5.3.5 Terminal-state invariants (unchanged and extended)

- Exactly four terminal states. Terminal rows accept no command
  (`workflow_terminal`) and no receipt, result, checkpoint, restore fact or
  compensation envelope mutates one.
- The one carve-out U-W2 §13.3 froze survives verbatim: a late receipt naming an
  intent this workflow **revoked** refuses `receipt_superseded`. U-W3 adds no
  second carve-out.
- `fold` clears `dispatch_intent_id` and `cancel_intent_id` on entering any
  terminal state, and additionally closes the open workflow attempt as
  `abandoned` when the terminal state is `cancelled` (§6.3).
- A `compensating` workflow is not cancellable and has exactly two exits.

#### 5.3.6 Stateless drivers under v2

An accepted stateless command traverses no cell, appends an event with
`to_state = null`, consumes its revision, and leaves `state` untouched. Under v2
the stateless set is: `request_dispatch`, `revoke_dispatch`, post-dispatch
`request_cancel`, runtime-scope `record_approval`, a `rejected` receipt,
**`adopt_policy_version`**, **`record_checkpoint`**, **`record_restore`**.
`record_compensation` is state-changing.

### 5.4 Refusal reasons (fifty-seven; the fourteen U-W3 adds)

The forty-three landed codes keep their spelling, their meaning and their
emission order. U-W3 appends fourteen, in canonical emission order:

| Code | Emitted when |
| --- | --- |
| `policy_version_not_upgradable` | the adoption target is not a strictly forward, supported step, **or** the workflow satisfies none of the §5.2.1 adoption-safety conditions A1–A3 — in particular an active post-dispatch policy-v1 workflow whose authoritative attempt history is absent |
| `attempt_budget_exhausted` | a dispatch is requested with `attempts_used >= budget` |
| `attempt_mismatch` | a result, checkpoint or restore fact reports an attempt that is not the open attempt — or a compensation conclusion reports an `attempt` that is not the **compensating attempt** recorded by `compensation_started` (§10.8) |
| `checkpoint_malformed` | the checkpoint record fails its closed shape, its size bound, or the secret scan |
| `checkpoint_unbound` | the checkpoint does not bind this workflow, WorkSpec digest, or runtime task |
| `checkpoint_conflict` | that `checkpoint_id` is stored with a different body (store-side) |
| `checkpoint_limit_exceeded` | the per-attempt or per-workflow checkpoint count bound is reached |
| `checkpoint_unknown` | a restore or dispatch names no stored checkpoint of this workflow (store-side) |
| `checkpoint_ineligible` | the named checkpoint may not be restored in this state / attempt, or its stored digest does not recompute |
| `restore_fact_malformed` | the restore record fails its closed shape |
| `restore_fact_unbound` | the restore record does not bind this workflow, the named checkpoint's digest, or the named checkpoint's attempt (`from_attempt_no` must equal the stored checkpoint's own `attempt_no` — §9.4) |
| `compensation_not_required` | `record_compensation` on a workflow that is not `compensating` |
| `compensation_already_concluded` | a second compensation conclusion |
| `compensation_state_inconsistent` | the envelope's `compensation.state` contradicts the phase (e.g. `applied` on `record_result`, `pending` on `record_compensation`) |

`command_conflict`, `receipt_conflict`, `checkpoint_conflict`,
`checkpoint_unknown` and `checkpoint_ineligible` need stored rows to detect, so
`workflow_engine` declares them and `workflow_store` raises them — the landed
U-W2 §9/§10 split, extended by three.

Two **landed** codes additionally take on the policy-v2 attempt-binding duty
without changing spelling, schema or CHECK. A `failed` receipt that closes an
open workflow attempt, consumes that attempt, drives retry classification, or
concludes a compensation must carry `runtime_task_uuid` equal to the
`workflow_attempts.runtime_task_uuid` binding recorded for the relevant
attempt: a failed receipt that binds no attempt of this workflow refuses
`receipt_unbound`, and one that names a different attempt's task refuses
`runtime_uuid_mismatch` (§6.2). `runtime_uuid_mismatch` additionally covers the
**present-and-contradicting** `runtime_task_uuid` of a result or compensation
envelope (§5.3.3, §10.8); an **absent** one refuses nothing, because the shipped
protocol makes the property optional. The receipt record shape and the nine
kinds stay frozen (§1.3), no database CHECK changes, and **policy-v1 replay
remains unchanged and permissive for historical rows**: the binding is a
policy-v2 acceptance gate applied when a receipt or envelope is offered, never a
replay-time re-judgment of stored history.

A third landed pairing carries the policy-v2 attempt-ordinal duty. Under policy
v2 a `dispatch_accepted` **must** be able to record an `attempt_no` (§5.5); when
it cannot — the acceptance answers a reservation made under policy v1, which
recorded no ordinal — the command refuses `receipt_unbound`, the exact landed
meaning being that the receipt binds no attempt of this workflow that AOS
authoritatively recorded. **No ordinal is fabricated to make the acceptance
succeed.** The operator's path is `revoke-dispatch` and a fresh policy-v2
dispatch (§5.2.1).

### 5.5 Events (twenty-four; the seven U-W3 adds)

The seventeen landed names keep their spelling, their meaning and their
position. U-W3 appends seven, each the sole event of exactly one driver class:

| Event | Driver | `to_state` | Payload members (closed) |
| --- | --- | --- | --- |
| `policy_version_adopted` | `cmd:adopt_policy_version` | `null` (stateless) | `from_policy_version`, `to_policy_version` |
| `attempt_failed` | `res:fail_retryable` / `rcp:failed_retryable` | `retrying` | `attempt_no`, `attempt_budget`, `attempts_used`, and either `result_sha256` or `{receipt_id, receipt_sha256, reason_code, retryable}` |
| `checkpoint_recorded` | `cmd:record_checkpoint` | `null` (stateless) | `checkpoint_id`, `checkpoint_sha256`, `attempt_no`, `checkpoint_seq`, `payload_bytes` |
| `checkpoint_restored` | `cmd:record_restore` | `null` (stateless) | `checkpoint_id`, `checkpoint_sha256`, `from_attempt_no`, `into_attempt_no`, `restored_by` |
| `compensation_started` | `res:compensable` | `compensating` | `result_sha256`, `attempt_no`, `compensation_ref?` |
| `compensation_applied` | `cmp:applied` | `compensated` | `result_sha256`, `compensation_state`, `attempt_no`, `evidence`, `evidence_counted`, `evidence_required` |
| `compensation_failed` | `cmp:failed` / `rcp:failed` from `compensating` | `failed` | `attempt_no`, and **either** `{result_sha256, compensation_state}` (the `cmp:failed` envelope path) **or** `{receipt_id, receipt_sha256, reason_code, retryable}` (the `rcp:failed` path, which carries no `compensation_state` because a queue receipt reports about the task, not about the undo) |

Three landed events gain payload members and no new name:
`dispatch_requested` gains `attempt_no` and `attempt_budget` (and
`restore_checkpoint_id`/`restore_checkpoint_sha256` when a restore was
requested); `dispatch_accepted` gains `attempt_no`; `workflow_failed` gains
`attempt_no` and `attempts_used`. Every added member is an enum member, a
validated identifier, a bounded integer or a digest — U-W2 §7's closed payload
rule, unbroken.

`_EVENT_PAYLOAD_REQUIRED` gains one row per new event so
"certified by `verify_history`" still implies "foldable", and
`_EVENT_PAYLOAD_OPTIONAL` gains the conditional members above. A `KeyError` out
of `fold` is not a report.

**`dispatch_accepted` compatibility, frozen.** `dispatch_accepted` is the one
landed event whose new member is load-bearing for attempt accounting, so its
version conditioning is stated exactly rather than left to the general rule:

1. **Under policy v2, `attempt_no` is mandatory.** A v2 `dispatch_accepted` that
   could not carry it is not written; the command refuses instead (§5.4).
2. **Under historical policy-v1 replay, `attempt_no` may be absent**, and that
   is correct, complete history — policy v1 never numbered workflow attempts.
   The required-member set for this event is therefore policy-version
   conditional: required at v2, absent at v1.
3. **`fold` must handle an absent v1 `attempt_no` without indexing failure.** It
   reads the member through an explicit presence check, never
   `payload["attempt_no"]`; a v1 `dispatch_accepted` binds `runtime_task_uuid`,
   moves the state, advances no `attempts_used`, and opens no attempt. A
   `KeyError` out of `fold` is not a report (above), and a v1 history must fold
   forever.
4. **An absent `attempt_no` under policy v2 refuses**, using the existing
   policy-adoption and attempt-binding vocabulary — `receipt_unbound` for an
   acceptance with no recorded v2 reservation to number it,
   `policy_version_not_upgradable` for the adoption that would have created the
   situation (§5.2.1). No new refusal code is minted.
5. **No value may be fabricated.** Not from event sequence, not from receipt
   sequence, not from `runtime_task_uuid`, not from the current state, and not
   from a count of prior `dispatch_accepted` events. A v1 acceptance's ordinal
   was never written and is not recoverable; the honest answer is a refusal.

**No U-W3 command emits more than two events**, so
`_MAX_EVENTS_PER_COMMAND` stays 2 (§11.4).

---

## 6. Workflow-attempt lifecycle (questions 1 and 2)

### 6.1 The one budget rule

`budget = work_spec_document.retry.max_attempts`, defaulting to **1** when the
artifact declares no `retry` block — the landed `_handle_record_result` default,
unchanged. The artifact is admission-immutable and digest-bound, so the budget
cannot drift.

### 6.2 The seven lifecycle moments, frozen

| Moment | Trigger | Effect | Refusal if illegal |
| --- | --- | --- | --- |
| **reserved** | accepted `request_dispatch` | `dispatch_requested` payload carries `attempt_no = attempts_used + 1` and `attempt_budget`; the outbox gains one v2 dispatch intent; **no `workflow_attempts` row, no budget consumption** | `attempt_budget_exhausted` when `attempts_used >= budget`; `dispatch_already_pending` |
| **opened / consumed** | `accepted` receipt | INSERT one `workflow_attempts` row `(workflow_id, attempt_no, state='open', runtime_task_uuid, opened_seq)`; `attempts_used := attempt_no`; state → `scheduled` | `receipt_unbound`; `runtime_uuid_mismatch` — including a `runtime_task_uuid` already bound to a prior attempt of this workflow (§6.5) |
| **executing** | `started` / `waiting_*` / `paused` / `resumed` receipts | workflow state moves; the attempt row is unchanged (execution phase lives in `workflows.state`, not duplicated) | as landed |
| **completed** | `record_result` `res:success` | attempt row CAS to `succeeded` with `closed_seq`, `result_sha256`; workflow → `succeeded` | `evidence_insufficient`, `result_inconsistent` |
| **failed** | `res:fail*`, `res:compensable`, or a bound `failed` receipt | attempt row CAS to `failed` with `closed_seq` and the failing digest or reason code; under `res:compensable` the row closes `failed` with the failing result's digest preserved as the authoritative compensation trigger while the workflow enters `compensating` (§10.3) | `attempt_mismatch`; for the receipt path also `receipt_unbound` / `runtime_uuid_mismatch` (below) |
| **made retryable** | the failing fact says `retryable == true` **and** `attempt_no < budget` | workflow → `retrying`; the next `request_dispatch` reserves `attempt_no + 1` | otherwise the workflow goes terminal `failed` |
| **abandoned** | `dispatch_rejected`, `dispatch_revoked`, or a terminal `cancelled` | the *reservation* materialised nothing (rejected/revoked), or the open row CAS to `abandoned` (cancelled) | — |

**Why the ordinal is assigned at acceptance and not at reservation.** A queue
rejection or an operator revocation means the work never ran. Burning a budget
slot on it would permanently strand a default-budget-1 workflow on a single
adapter error. Assigning at acceptance also keeps `attempt_no ≤ budget ≤ 10`
always true, which is what makes the reported `attempt` satisfiable against
`beast.result-envelope/v1`'s `{"minimum": 1, "maximum": 10}` — a monotone
never-reused ordinal would not be. Re-dispatch after a rejection reuses the same
`attempt_no` but derives a **new** `intent_id` and a **new** `idempotency_key`
from the advanced `intent_seq` (§7.2), so nothing is ambiguous.

**The failed-receipt binding.** A `failed` receipt participates in this ledger
only as the attempt it closes. Whether it closes the open attempt, consumes it,
drives the retry classification (§5.3.3), or concludes a compensation (§10.4),
it must carry `runtime_task_uuid` equal to the
`workflow_attempts.runtime_task_uuid` binding recorded for that attempt. A
failed receipt that binds no attempt of this workflow refuses
`receipt_unbound`; one that names a different attempt's task refuses
`runtime_uuid_mismatch` — both landed codes, no new vocabulary. The receipt
record shape and the nine kinds are unchanged, no database CHECK changes, and
policy-v1 replay stays unchanged and permissive for historical rows (§5.4).

### 6.3 Attempt row states

Exactly four: `open`, `succeeded`, `failed`, `abandoned`. `open` is the only
non-final value, and at most one row per workflow may be `open` — enforced by a
partial-unique discipline in code plus the §11.2 CHECK pairing `state = 'open'`
with `closed_seq IS NULL`.

### 6.4 Attempt-budget divergence, frozen (question 2)

The WorkSpec defaults `max_attempts` to **1**; the private runtime's
`TaskQueueRecord` defaults it to **3** (`libs/runtime_db/runtime_db/task_queue_repository.py:58`),
and `task_queue.max_attempts` is `NOT NULL` with only `CHECK (max_attempts > 0)`.
With U-W2.R absent, nothing transports the artifact's budget into that column;
a human does, or does not.

Frozen safe behavior:

1. **AOS's budget is the artifact's, always.** U-W3 never reads, infers or
   accepts a runtime budget.
2. **AOS states its budget explicitly.** The v2 dispatch intent carries
   `attempt_no` and `attempt_budget` as required members, so the enqueuer has
   the number in front of them and `export-intents` puts it in a file.
3. **AOS never assumes the runtime received or honoured it.** No U-W3 code path
   asserts, checks or repairs the runtime row.
4. **A disagreement refuses; it never reconciles.** A result reporting
   `attempt != open attempt_no` refuses `attempt_mismatch`; one reporting
   `attempt > budget` refuses `result_attempt_exceeded` (landed, unchanged).
   Nothing is recorded, no attempt is renumbered, no budget is widened, and the
   workflow parks in `running` for a human. **No automatic repair may fabricate
   authority or evidence.**
5. **Runtime-internal retry stays invisible and free.** It consumes no workflow
   attempt and produces no AOS record.
6. The declared failure mode: a WorkSpec with no `retry` block (budget 1)
   enqueued into a row that defaulted to 3, whose runtime retried internally and
   reported `attempt: 2`, is refused `result_attempt_exceeded` and parks. A
   human reconciles by authoring a truthful envelope or by accepting that the
   workflow has no honest terminal. This is U-W2 §22's declared limitation,
   inherited unchanged and made *stricter* under v2 by rule 4.

### 6.5 One runtime task, one workflow attempt

A `runtime_task_uuid` already bound to one workflow attempt is **never accepted
for another attempt of the same workflow**. A retry is a new runtime task by
construction (§7.2: the advanced `intent_seq` derives a new `idempotency_key`,
which the runtime's `UNIQUE` admits only as a new task row), so an `accepted`
receipt offering an already-bound uuid is evidence of a reused or replayed
task, not of a new attempt.

- **Acceptance gate**: on an `accepted` receipt, the reducer refuses
  `runtime_uuid_mismatch` when the offered `runtime_task_uuid` equals the
  recorded binding of **any** prior attempt of this workflow. The prior
  bindings are reconstructed from the folded `dispatch_accepted` history, so
  the check is event-authoritative and needs no store read.
- **Storage backstop**: `workflow_attempts` carries
  `UNIQUE(workflow_id, runtime_task_uuid)` (§11.2), so the reuse is unstorable
  even if a defective gate admitted it.
- **NULL handling** is defined by the lifecycle itself: the column is
  `NOT NULL` — a `workflow_attempts` row exists only because an `accepted`
  receipt supplied the binding (§6.2) — so SQLite's NULL-distinct UNIQUE
  semantics can never arise.
- **Receipt redelivery is unaffected**: an identical redelivered `accepted`
  receipt is answered by the `receipt_id` dedupe axis (`replay`, §7.3) before
  this gate is consulted.

---

## 7. Retry identity and deduplication (question 3)

### 7.1 The eight identities

| Thing | Identity | Derivation | Uniqueness enforced by |
| --- | --- | --- | --- |
| workflow attempt | `(workflow_id, attempt_no)` | assigned at acceptance, §6.2 | `UNIQUE(workflow_id, attempt_no)` |
| retry decision | the accepted command's `command_id` | caller-minted UUID; the CLI mints a fresh one per invocation | `workflow_commands.command_id UNIQUE` |
| retry command | `aos.workflow-command/v1` envelope, verb `request_dispatch` | unchanged envelope; `content_sha256` self-excluding | the command dedupe axis (§7.3) |
| dispatch intent | `intent_id = uuid8(sha256(TAG_INTENT ‖ 0x00 ‖ "<work_spec_sha256>:<intent_seq>"))` | **unchanged from U-W2 §13.1** | `workflow_intents.intent_id UNIQUE` |
| idempotency key | `"wfd-" + sha256(TAG_DISPATCH_IDEM ‖ 0x00 ‖ "<work_spec_sha256>:<intent_seq>").hex()[:40]` | **unchanged from U-W2 §13.1** | `task_queue.idempotency_key UNIQUE` (runtime side) |
| runtime task binding | `runtime_task_uuid`, recorded once per opened attempt | the `accepted` receipt | `UNIQUE(workflow_id, runtime_task_uuid)` on `workflow_attempts` (§6.5); `runtime_uuid_mismatch` guards every later receipt, including the `failed` receipt that closes the attempt (§6.2), and every **present** `runtime_task_uuid` on a result or compensation envelope (§5.3.3) |
| result / failure fact | `content_digest(envelope)` | recomputed from stored bytes at every use | `UNIQUE(workflow_id, fact_kind, document_sha256)` |
| checkpoint | `(workflow_id, checkpoint_id)` plus `document_sha256` | producer-supplied UUID; AOS mints no identity for a document it did not produce | `UNIQUE(workflow_id, checkpoint_id)` and `UNIQUE(workflow_id, attempt_no, checkpoint_seq)` |

U-W3 adds **no new derivation formula**. Every intent identity and idempotency
key stays exactly the landed one, keyed on the per-workflow `intent_seq`.

### 7.2 Preventing a silent second task for the same WorkSpec

`intent_seq` advances on every emitted intent, so attempt 2's dispatch derives a
different `intent_id` and a different `idempotency_key` than attempt 1's. On the
runtime side `task_queue.idempotency_key` is `UNIQUE`, so **attempt 2 enqueues
as a genuinely new runtime task row.** That is correct — a retry *is* a new
runtime task — and it is exactly the situation that must never become invisible.
Three frozen defences:

1. The v2 dispatch intent carries `attempt_no` and `attempt_budget` as required
   members, so a second file for the same WorkSpec announces itself as
   "attempt 2 of N" rather than looking like a duplicate first dispatch.
2. It carries `supersedes_runtime_task_uuid`, present exactly when a prior
   attempt bound a runtime task, so the chain of runtime tasks for one WorkSpec
   is readable from the files alone.
3. `workflow_attempts` records exactly one runtime task per consumed attempt, so
   `workflow show` and `workflow verify` can state the chain, and a second task
   AOS never accepted has no attempt row and is visible as an orphan.

The landed U-W2 §22 limitation — a revoked-but-already-committed dispatch
becoming a second runtime task that AOS neither prevents nor detects — is
**inherited unchanged**. U-W3 makes it more legible (defence 2) and does not
claim to fix it.

### 7.3 What retry is NOT (the D-v0.4.91 discrimination, extended to six)

D-v0.4.91's governing definition is adopted verbatim: *U-W3 retry is
re-execution of work that advances an attempt counter, is bounded by
`retry.max_attempts`, and changes what the workflow claims about the world.*

| Not retry | Why | Attempt consumed | Event appended | State changed |
| --- | --- | --- | --- | --- |
| **SQLite lock waiting** | `timeout=5.0` + `PRAGMA busy_timeout=5000`; the store adds no loop, sleep, backoff or re-issue; a post-timeout error is `store_unavailable` | no | no | no |
| **duplicate command replay** | the `command_id` dedupe axis returns `status="replay"` with the original events re-verified | no | no | no |
| **intent redelivery** | `export-intents` is content-addressed and idempotent; re-writing the same file changes nothing, and the runtime's `idempotency_key UNIQUE` collapses a re-enqueue | no | no | no |
| **receipt redelivery** | the `receipt_id` dedupe axis returns `replay`; a stored receipt is an applied receipt | no | no | no |
| **private-runtime task-attempt retry** | `task_queue.attempt_count` + `retry_backoff_seconds`; `running → pending → running` inside the runtime's plane; no AOS receipt exists for it | no | no | no |
| **`revision_mismatch`** | the caller must mint a NEW `command_id`, which is a fresh recorded decision | no | no | no |
| **U-W3 retry** | a new accepted command, a reserved attempt, a new intent with a new idempotency key, an observed acceptance, a new `attempt_no` | **yes** | **yes** | **yes** |

---

## 8. Checkpoint model (question 6)

### 8.1 Checkpoint is not snapshot

`aos.workflow-snapshot/v1` remains U-W2.2's **derived workflow projection**,
rebuilt by `fold` plus the two stored bodies on every command. U-W3's artifact
is a **checkpoint**: `aos.workflow-checkpoint/v1`, bounded execution-restoration
state produced outside AOS. The two words are never interchanged, U-W3 mints no
second "snapshot", and no U-W3 surface renders a snapshot body.

### 8.2 The frozen checkpoint model

| Facet | Frozen answer |
| --- | --- |
| **Identity** | `checkpoint_id`, a producer-supplied UUID. AOS mints no identity for a document it did not produce. Ledger identity is `(workflow_id, checkpoint_id)`. |
| **Workflow binding** | the record carries `workflow_id` and `work_spec_sha256`; both must equal the snapshot's, else `checkpoint_unbound`. |
| **Attempt binding** | the record carries `attempt_no` and `runtime_task_uuid`; `attempt_no` must equal the open attempt (`attempt_mismatch` otherwise) and `runtime_task_uuid` must equal that attempt's binding (`runtime_uuid_mismatch`). |
| **Producer authority** | only the executing side — the runtime, or a human acting as the adapter at the manual boundary. **AOS never creates, derives, synthesises, edits or completes a checkpoint.** |
| **Payload schema** | `payload` is an **opaque canonical JSON object**. AOS validates canonical parse, the spine's depth/member/string/integer bounds, the size bound below, and the secret scan. It never reads a key, never interprets a value, and never renders one. |
| **Size limit** | `MAX_CHECKPOINT_PAYLOAD_BYTES = 65536`, measured as `len(serialize_canonical(payload))`. Derived headroom, not a tuned number: it is a quarter of `protocols.MAX_ARTIFACT_BYTES`, leaving the envelope and the sealed digest inside the canonical bound with margin. |
| **Count limits** | `MAX_CHECKPOINTS_PER_ATTEMPT = 8`; `MAX_CHECKPOINTS_PER_WORKFLOW = 80` — derived as `8 × 10`, the per-attempt bound times the protocol's frozen attempt ceiling, so no third number is introduced. Exceeding either refuses `checkpoint_limit_exceeded`. |
| **Canonical digest** | `protocols.content_digest(document)` — the self-excluding `content_sha256` idiom, **recomputed from the stored bytes at every use**, never read from a column. |
| **Creation transaction** | one `record_checkpoint` command = one `BEGIN IMMEDIATE` transaction, in the landed C1–C16 order with the checkpoint INSERT and its §5.8 row-hash finalization at a new step C12b (§14.1). |
| **Replacement vs append** | **append-only. A checkpoint row is INSERT-ONCE and is never updated, replaced, truncated or deleted.** `checkpoint_seq` is monotone from 1 within an attempt. A second `record_checkpoint` with the same `checkpoint_id` and an **equal** digest is a `replay`; with a **different** digest it refuses `checkpoint_conflict`. |
| **Encryption / secret boundary** | AOS **neither encrypts nor decrypts**, and holds no key. Every checkpoint payload passes `secretscan.scan_secrets`; a secret-shaped payload is **REFUSED at ingest** (`checkpoint_malformed`, naming the schema-safe path only) and never stored — not redacted, because a redacted checkpoint is an unrestorable lie, and not stored-then-warned, because that would put a plaintext credential in `aos.db`. The producer keeps credentials out of checkpoints; a checkpoint that needs one is a design error in the producer. |
| **Corruption behavior** | a stored checkpoint whose digest does not recompute is **reported** — `workflow verify` lists it in `divergent_rows` — and is permanently **ineligible** for restoration (`checkpoint_ineligible`). It is never repaired, re-sealed, re-stamped or deleted. |
| **Compatibility** | `aos.workflow-checkpoint/v1`. An unknown `/vN` refuses `checkpoint_malformed`; there is no default-version resolution. Any additive member requires `/v2` and a new policy version. |
| **Retention** | nothing is pruned, ever (U-W2.2 §14.4). Checkpoints survive terminal states as audit history. |
| **Restore eligibility** | §9.3. |
| **Evidence of restoration** | the `checkpoint_restored` event, and nothing else (§9). |
| **Hostile persisted data** | every checkpoint row is untrusted input under the landed U-W2.2 §18 discipline verbatim: explicit type check **before** every read, re-digest from stored bytes at every use, `_RowUnreadable` never crossing a public boundary, bounded closed-code diagnostics only, and the payload never becoming a path, a command, SQL, a tool input or a message. |

### 8.3 The record shape

`aos.workflow-checkpoint/v1`, closed member set:

```
schema, checkpoint_id, workflow_id, work_spec_sha256, attempt_no,
checkpoint_seq, runtime_task_uuid, payload, created_at, [trace],
content_sha256
```

Patterns and bounds reuse the landed compiled gates exactly: `UUID_PATTERN`,
`^WF-[0-9]{1,19}$`, `SHA256_PATTERN`, `attempt_no ∈ 1..10`, `checkpoint_seq ∈
1..8`, `TRACE` per `_trace_ok`, `created_at` per the pure-calendar real-instant
check. U-W3 adds no new pattern constant.

### 8.4 When a checkpoint may be recorded

`record_checkpoint` is legal in exactly the states where a workflow attempt is
open and a runtime task is live: **`running`, `waiting_input`,
`waiting_approval`, `paused`**. In every other state it refuses
`illegal_transition`, and on a terminal row `workflow_terminal`. There is no
checkpoint in `compiled`, `validated`, `awaiting_approval`, `scheduled`,
`retrying`, `compensating` or any terminal state: before acceptance nothing is
executing, and after an attempt closes there is nothing left to capture.

Two of those four states — `waiting_input` and `paused` — have **no live
runtime fact producer** (§20 item 9) and are therefore unreachable in wave 1.
They are named here so the state gate is total and no future producer needs a
new policy version; U-W3 designs no resume, restore or recovery *from* them, and
§18 asserts them as refusals-by-absence rather than as exercised paths.

`record_checkpoint` traverses no matrix cell: it is stateless (§5.3.6).

### 8.5 What a checkpoint never does

- It never changes `workflows.state`. `record_checkpoint` is stateless.
- It never satisfies an evidence predicate, an approval, or an attempt.
- It is never read by AOS to make a decision other than restore eligibility,
  which reads only its identity, digest, attempt and workflow binding — never
  its payload.
- It is never printed. Not by `show`, not by `show --json`, not by `list`, not
  in an event payload, not in a refusal message, not in the journal.

---

## 9. Resume model (question 7)

### 9.1 The three-way separation, frozen

| | **A. queue resumption** | **B. checkpoint restoration** | **C. semantic resume instruction** |
| --- | --- | --- | --- |
| Owner | U-W2 (landed) | **U-W3** | U-W5 (absent) |
| Fact | `aos.workflow-queue-receipt/v1`, kind `resumed` | `aos.workflow-restore-fact/v1` via `record_restore` | `beast.interrupt/v1`, `kind: "resume_instruction"`, `resume_instruction_ref` |
| Command | `record_queue_receipt` | `record_restore` | none |
| Event | `run_resumed` | `checkpoint_restored` | none |
| State effect | `waiting_input`/`waiting_approval`/`paused` → `running` | **none — stateless** | none |
| Proves | the runtime left a wait state and is executing again | a named, digest-bound, stored checkpoint was loaded into a named attempt | nothing in U-W3 |

**Frozen rules:**

1. **A `run_resumed` event is NEVER proof that a checkpoint was restored.**
   `fold` derives no restoration fact from it, no snapshot member is set by it,
   and no U-W3 predicate reads it. A `resumed` receipt with no preceding
   `checkpoint_restored` is a wait exit and nothing more.
2. **A `checkpoint_restored` event NEVER changes state.** It is stateless,
   exactly like a runtime-scope `approval_recorded`.
3. **U-W3 reads no `beast.interrupt/v1` document.** It adds no command that
   accepts one, imports nothing that parses one, and never dereferences
   `resume_instruction_ref`. `interrupt` stays a banned token in the CLI region
   (§13.5). Those fields remain reserved to U-W5, unread.

### 9.2 Requesting a restore

A restore is *requested* in the dispatch that opens the next attempt, and
*recorded* when the executing side reports it:

- `request_dispatch`'s payload key set widens under policy v2 from
  `("queue_route",)` to `("queue_route", "restore_checkpoint_id")`. The reducer
  checks only that the value is a UUID; **whether it names a stored, eligible
  checkpoint is a stored-row judgment**, so the store resolves it before
  `decide` and hands the reducer the resolved `(checkpoint_sha256,
  checkpoint_attempt_no)` through `ShellFacts` (§1.2 S7). An unknown id refuses
  `checkpoint_unknown`; an ineligible one refuses `checkpoint_ineligible`.
- The emitted v2 dispatch intent then carries `restore_checkpoint_id` and
  `restore_checkpoint_sha256` as a required-together optional pair, so the file
  the operator carries names exactly what must be restored, by digest.

### 9.3 Restore eligibility predicate (all five conjuncts required)

1. The checkpoint row exists and belongs to **this** workflow.
2. Its stored `document_sha256` **recomputes** from its stored bytes.
3. Its `attempt_no` is **strictly less than** the attempt being opened — you
   restore from a previous attempt, never from the one you are in.
4. The workflow is under `policy_version = 2`.
5. The workflow is not terminal and is in `retrying` (for the dispatch request)
   or `scheduled`/`running` (for the restore record). Restoration is
   **ineligible in `compensating` and in every terminal state**: compensation
   undoes, it does not resume.

Any failed conjunct refuses `checkpoint_ineligible`, except conjunct 1's
"exists" which refuses `checkpoint_unknown`.

### 9.4 Recording a restore

`record_restore`'s payload carries one `aos.workflow-restore-fact/v1`:

```
schema, workflow_id, work_spec_sha256, checkpoint_id, checkpoint_sha256,
from_attempt_no, into_attempt_no, restored_by, restored_at, [trace],
content_sha256
```

Gates, in order: closed shape and self-digest (`restore_fact_malformed`) →
workflow and WorkSpec-digest binding (`restore_fact_unbound`) →
`checkpoint_sha256` equals the stored checkpoint's **recomputed** digest
(`restore_fact_unbound`) → `from_attempt_no` equals the stored checkpoint's own
`attempt_no` (`restore_fact_unbound`) — the checkpoint digest alone is
insufficient: it proves *which bytes* were restored, not *which attempt* they
captured → `into_attempt_no` equals the open attempt
(`attempt_mismatch`) → the §9.3 eligibility predicate → append
`checkpoint_restored` with payload `{checkpoint_id, checkpoint_sha256,
from_attempt_no, into_attempt_no, restored_by}` and consume one revision.

The restore fact needs **no stored body**: every member the event does not
already carry is either a digest or a validated identifier, and U-W2 §7 permits
exactly those in an event payload. `workflow_facts` is therefore untouched.

---

## 10. Compensation model (question 8)

### 10.1 Authority (the single rule)

**Compensation authority is a verified `beast.result-envelope/v1` bound to this
workflow's admitted WorkSpec digest, and nothing else.**

Explicitly and mechanically NOT authority:

- `beast.tool-manifest/v1` `compensation.strategy = "compensating_action"` and
  `compensation.ref` — a **reversibility declaration** about a component.
- `beast.tool-manifest/v1` `recovery.action = "invoke_compensation"` — a
  declared recovery *hint*; `recovery.note` is documented as "display-only prose,
  never parsed, matched or executed".
- `beast.tool-manifest/v1` `cancellation`, `idempotency`, `retry.max_attempts`.
- U-W1's `retry_idempotency_incompatible` finding and every other compile-report
  finding.
- The result envelope's own optional `runtime_task_uuid`. It is corroborating
  evidence about which runtime task produced the document (§10.8 rules 3–8); it
  never initiates compensation, never selects the attempt being concluded, and
  never grants execution authority. A conclusion that carried nothing but a
  matching uuid would still refuse.

**Frozen prohibition: no U-W3 code path reads a tool manifest, a skill manifest,
an agent passport, a compile-report finding, a `recovery.action` or any
descriptive metadata to decide whether, when or how to compensate.** U-W3
imports no catalog, no `governance`, no `passports` and no manifest reader; §18
row W27 proves it by AST.

### 10.2 Declaration versus execution

`beast.work-spec/v1` has **no `compensation` property at all** — verified
against the shipped schema. A WorkSpec therefore **cannot declare** that its
work is compensable. Only the executing side can *report* that a compensating
action is required, through the result envelope's optional `compensation`
block, whose `state` enum is `not_required | pending | applied | failed`.

This asymmetry is real and is declared as a known limitation (§20), not
papered over by inferring a declaration from a manifest.

### 10.3 Trigger conditions

`record_result` under policy v2:

| `outcome` | `compensation.state` | Result |
| --- | --- | --- |
| `fail` | `pending` | `running → compensating`; the open attempt closes `failed`, its `result_sha256` the failing envelope's digest — the authoritative trigger (§6.2); event `compensation_started`; one `compensate` intent emitted |
| `fail` | absent / `not_required` | the §5.3.3 retry-or-fail predicate |
| `fail` | `applied` / `failed` | `compensation_state_inconsistent` — a first result cannot report a conclusion |
| `success` | `pending` | `result_inconsistent` — a success that needs undoing is not an honest report |
| `success` | absent / `not_required` | the landed success path |
| `success` | `applied` / `failed` | `compensation_state_inconsistent` |
| `partial` / `unknown` | any | `result_outcome_inconclusive` (§5.3.3) |

Compensation **outranks** retry: a failing result that reports
`compensation.state = "pending"` enters `compensating` even when attempts
remain. Undoing a partial effect before re-running is the only safe order, and
the alternative — retrying over an un-undone effect — is the hazard the whole
model exists to prevent.

### 10.4 Transitions

- `running → compensating` (`res:compensable`), event `compensation_started`,
  payload `{result_sha256, attempt_no, compensation_ref?}`.
- `compensating → compensated` (`cmp:applied`), event `compensation_applied`.
- `compensating → failed` (`cmp:failed`, or a `failed` receipt), event
  `compensation_failed` — a distinct event name so "the work failed" and "the
  undo failed" are never confused in the history.
- `compensating → cancelled` is illegal in every frozen version.

### 10.5 The compensate intent

One `compensate` intent is emitted with `compensation_started`, on the next
`intent_seq`, using the **unchanged** `intent_id` and `idempotency_key`
formulas. Body (`aos.workflow-queue-intent/v2`, `intent_kind: "compensate"`):

```
schema, intent_kind, intent_id, workflow_id, work_spec_sha256, attempt_no,
failed_result_sha256, [compensation_ref], [runtime_task_uuid],
idempotency_key, queue_route, requested_at, [trace]
```

`compensation_ref` is copied verbatim from the failing envelope's
`compensation.ref` when present — an **opaque reference AOS never
dereferences**.

### 10.6 Ordering and idempotency

- Compensation is entered only from `running`, only once per workflow, and only
  in the same decision that records the failing result. There is no compensation
  before a failure and none after a terminal state.
- `record_compensation` deduplicates on `command_id` (the landed axis) and the
  envelope body is stored through `_insert_fact`'s `ON CONFLICT DO NOTHING`, so
  an exact duplicate body is a no-op while the command still appends its event
  and consumes its revision.
- A second `record_compensation` after a conclusion refuses
  `compensation_already_concluded`; on a non-`compensating` workflow it refuses
  `compensation_not_required`.

### 10.7 Retries, interruption, partiality — all three refused explicitly

- **No compensation retry.** A failed compensation concludes the workflow as
  `failed`. There is no second compensate intent, no compensation attempt
  counter, and no compensation budget. Adding one is a replan trigger (§21).
- **Interruption and resumption.** A crash mid-compensation leaves the workflow
  in `compensating` with the compensate intent still `outstanding`. Recovery is
  **redelivery of the same content-addressed intent file** — idempotent by
  construction and collapsed by the runtime's `idempotency_key UNIQUE`. AOS
  emits no second intent and re-decides nothing.
- **No partial compensation.** `beast.result-envelope/v1`'s `compensation.state`
  has no `partial` member. A compensation that only partly succeeded MUST be
  reported `failed`. AOS provides no way to record partial compensation, because
  inventing one would be a claim AOS cannot support. Declared in §20.

### 10.8 Terminal outcomes and evidence

Exactly two: `compensated` or `failed`.

**A conclusion is bound to the attempt it concludes**, by a mandatory ordinal
and an optional corroborating uuid. The eight rules are frozen:

1. **`attempt` is mandatory and authoritative.** It is a required property of
   the shipped `beast.result-envelope/v1`, and it is the member that binds the
   conclusion to an attempt.
2. **`attempt` must equal the attempt recorded by `compensation_started`** — the
   **compensating attempt** (no attempt is open in `compensating`: §6.2 closed
   it as `failed` at entry). A mismatch refuses `attempt_mismatch`, whose
   meaning here explicitly names the compensating attempt, not an open one
   (§5.4).
3. **`runtime_task_uuid` is optional corroborating evidence.** The shipped
   schema **does permit** the property — it is present in
   `beast.result-envelope/v1`'s `properties` and absent from its `required`
   list. Any claim that the envelope lacks the member is wrong and is not made
   anywhere in this contract.
4. **When present, it must equal the `workflow_attempts` binding for the
   compensating attempt** — in reducer terms, the binding folded from that
   attempt's `dispatch_accepted`, of which the row is the projection (§6.5).
5. **A present mismatch refuses `runtime_uuid_mismatch`** and records nothing.
6. **Absence does not invalidate the conclusion.** The property is optional in
   the shipped protocol, so an envelope without it is a legal envelope; nothing
   is inferred from the absence and nothing is refused for it.
7. **It never selects the attempt, never initiates compensation, and never
   grants execution authority.** Compensation is entered only by a verified
   failing result reporting `compensation.state = "pending"` (§10.1), the
   compensating attempt is fixed by `compensation_started`, and a uuid — however
   well-formed — decides nothing.
8. **A present mismatching value must not be ignored.** Silently dropping
   evidence that contradicts the ledger is the same failure as accepting
   evidence that was fabricated to agree with it; both would make the ledger say
   something no observation supports.

Uuid-level *binding* — the kind that closes an attempt — still exists only on
the receipt path (§6.2). What rules 3–8 add is a contradiction check, not a
second authority.

`compensated` is gated by the **same §12.2 evidence predicate as `succeeded`**,
applied to the compensation envelope: an item counts iff its `kind` is declared
in `expected_result.evidence_kinds` and its `ref` and `claim` are non-blank, and
`counted ≥ min_evidence_count`. One rule, one existing code
(`evidence_insufficient`), no new vocabulary. A WorkSpec declaring
`min_evidence_count: 0` reaches `compensated` with no evidence — by its author's
digest-bound declaration, exactly as it reaches `succeeded` with none.
`compensation_failed` needs no evidence minimum, exactly as `workflow_failed`
does not.

The `compensation_applied` event payload carries `{result_sha256,
compensation_state, attempt_no, evidence: [(kind, ref_sha256, provenance)],
evidence_counted, evidence_required}` — digests, never raw refs, the landed
`workflow_succeeded` shape.

### 10.9 Relationship to checkpoint restoration

**None, deliberately.** A checkpoint is never restored during or after
compensation; §9.3 conjunct 5 refuses `checkpoint_ineligible` in `compensating`
and in every terminal state. Compensation undoes work; restoration resumes it.
Allowing both would let a workflow resume from a state whose effects it had just
undone.

---

## 11. Persistence and migration (question 9)

### 11.1 The decision: two new tables, four rebuilt, no new fact kind

| Option | Verdict |
| --- | --- |
| additive `fact_kind` values only | **rejected** — `workflow_facts` has no attempt column, no sequence, no count bound and no per-attempt binding, so it cannot express a checkpoint; and widening its CHECK forces a rebuild of a table U-W3 otherwise never needs to touch |
| separate attempt / checkpoint / compensation tables | **partially adopted** — attempts and checkpoints get tables; compensation does not need one |
| both | **rejected** as stated |
| **another bounded design (adopted)** | **two** new tables (`workflow_attempts`, `workflow_checkpoints`); **four** landed tables rebuilt to widen closed enums (`workflows`, `workflow_events`, `workflow_commands`, `workflow_intents`); `workflow_receipts` and `workflow_facts` **byte-untouched**; **no new fact kind** |

**Why compensation needs no table and no fact kind.** A compensation conclusion
*is* a `beast.result-envelope/v1`. It is stored by the existing
`_insert_fact_for` path as `fact_kind = 'result'`, and the
`compensation_applied` / `compensation_failed` event's `result_sha256` is what
identifies which stored body is the compensation one. The event is the
authoritative fact that it happened; the table holds the body the event records
only by digest — D-v0.4.86's own rule. `UNIQUE(workflow_id, 'result',
document_sha256)` admits both the failing execution result and the compensation
result because their digests differ. Adding a `compensation` fact kind would
force a rebuild of `workflow_facts` and buy nothing the digest join does not
already give.

### 11.2 Schema version 7

`db.SCHEMA_VERSION = "7"`. `db.WORKFLOW_TABLES` grows to **eight** entries, in
FK-parent-first order:

```
workflows → workflow_events → workflow_commands → workflow_intents
→ workflow_receipts → workflow_facts → workflow_attempts
→ workflow_checkpoints
```

#### `workflow_attempts` (new)

```sql
CREATE TABLE workflow_attempts(
  id INTEGER PRIMARY KEY,
  workflow_id INTEGER NOT NULL,
  attempt_no INTEGER NOT NULL CHECK (attempt_no BETWEEN 1 AND 10),
  state TEXT NOT NULL
    CHECK (state IN ('open','succeeded','failed','abandoned')),
  runtime_task_uuid TEXT NOT NULL,
  dispatch_intent_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  result_sha256 TEXT,
  opened_seq INTEGER NOT NULL CHECK (opened_seq >= 1),
  closed_seq INTEGER CHECK (closed_seq IS NULL OR closed_seq >= opened_seq),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  UNIQUE(workflow_id, attempt_no),
  UNIQUE(workflow_id, runtime_task_uuid),
  UNIQUE(workflow_id, dispatch_intent_id),
  CHECK ((state = 'open') = (closed_seq IS NULL)),
  CHECK (result_sha256 IS NULL OR state IN ('succeeded','failed')),
  FOREIGN KEY(workflow_id) REFERENCES workflows(id),
  FOREIGN KEY(dispatch_intent_id) REFERENCES workflow_intents(intent_id)
)
```

`attempt_no BETWEEN 1 AND 10` is the protocol's own frozen ceiling closed
storage-side; the artifact's own budget is the tighter live bound and is checked
by the reducer. `UNIQUE(workflow_id, attempt_no)` makes a duplicate ordinal
unrepresentable. `UNIQUE(workflow_id, runtime_task_uuid)` makes one runtime
task serving two attempts of the same workflow unstorable — the storage
backstop for the §6.5 acceptance gate; the column is `NOT NULL`, a row existing
only because an `accepted` receipt supplied the binding, so SQLite's
NULL-distinct UNIQUE semantics never arise. The biconditional pairs `open` with
an absent `closed_seq`, so a closed attempt with no closing event and an open
attempt claiming one are both unstorable. `content_sha256` has no default, like
every hashed record in this schema.

#### `workflow_checkpoints` (new)

```sql
CREATE TABLE workflow_checkpoints(
  id INTEGER PRIMARY KEY,
  workflow_id INTEGER NOT NULL,
  attempt_no INTEGER NOT NULL CHECK (attempt_no BETWEEN 1 AND 10),
  checkpoint_id TEXT NOT NULL,
  checkpoint_seq INTEGER NOT NULL CHECK (checkpoint_seq BETWEEN 1 AND 8),
  runtime_task_uuid TEXT NOT NULL,
  document TEXT NOT NULL,
  document_sha256 TEXT NOT NULL,
  payload_bytes INTEGER NOT NULL
    CHECK (payload_bytes BETWEEN 2 AND 65536),
  recorded_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  UNIQUE(workflow_id, checkpoint_id),
  UNIQUE(workflow_id, attempt_no, checkpoint_seq),
  FOREIGN KEY(workflow_id) REFERENCES workflows(id),
  FOREIGN KEY(workflow_id, attempt_no)
    REFERENCES workflow_attempts(workflow_id, attempt_no)
)
```

INSERT-ONCE: no code path in U-W3 or any other slice issues `UPDATE` or
`DELETE` against this table after the creating transaction's own row-hash
finalization — the `workflow_events` / `agent_handoff_transitions` discipline.
The composite FK pins every checkpoint to a **real, consumed** attempt, so a
checkpoint for an attempt that never opened is unrepresentable. `payload_bytes`
is the recomputed canonical length, stored so `verify` can re-check the bound
without re-serializing, and CHECKed against the frozen limit (`2` is the
canonical length of `{}`, the smallest legal object).

#### The four rebuilt tables

| Table | Exact widening | Why a rebuild |
| --- | --- | --- |
| `workflows` | `state` enum gains `retrying`; `CHECK (dispatch_intent_id IS NULL OR state = 'validated')` becomes `… OR state IN ('validated','retrying')` | SQLite cannot ALTER a CHECK |
| `workflow_events` | `from_state`/`to_state` enums gain `retrying`; `event` enum gains the seven U-W3 names | as above |
| `workflow_commands` | `command` enum gains the four U-W3 verbs | as above |
| `workflow_intents` | `intent_kind` enum gains `compensate` | as above |

`workflows`' third CHECK — `runtime_task_uuid IS NULL OR state NOT IN
('compiled','validated','awaiting_approval')` — is **unchanged**: `retrying` is
deliberately absent from that list, which is what lets a retrying workflow keep
the runtime task binding of its failed attempt. `cancel_intent_id`'s CHECK is
**unchanged**: `retrying` is not a post-dispatch state, so cancellation from it
is local and emits no cancel intent.

Rows are copied **verbatim**, column for column, with `content_sha256` carried
across untouched. No hash is recomputed, no timestamp re-stamped, no value
normalized. Every landed row hash and every sealed event digest therefore stays
valid by construction, and a migrated database re-verifies identically to the
one it was made from.

### 11.3 Indexes, foreign keys, uniqueness, immutability

- **Indexes**: none beyond the implicit ones the UNIQUE constraints create.
  `workflow_attempts` is read by `(workflow_id, attempt_no)` and
  `workflow_checkpoints` by `(workflow_id, checkpoint_id)` and
  `(workflow_id, attempt_no, checkpoint_seq)`; all three are covered. No
  explicit `CREATE INDEX` exists anywhere in the workflow schema and U-W3 adds
  none.
- **Foreign keys**: plain `REFERENCES` (NO ACTION), matching every other FK in
  this schema. With `foreign_keys=ON`, deleting a referenced row is refused. No
  cascade — the ledger is append-only and has no delete path, so a cascade would
  only be a silent deletion mechanism for a caller that does not exist.
- **Immutability**: `workflow_checkpoints` is INSERT-ONCE.
  `workflow_attempts` receives exactly two writes: the INSERT that opens it and
  **one** compare-and-swap that closes it, fenced on `state = 'open'` with a
  required rowcount of 1 — the `_close_intent` discipline, so a second close is
  impossible and no reverse transition exists.
- **Row hashes**: both new tables carry a §5.8 row hash under new record
  schemas `aos.workflow-attempt-row/v1` and `aos.workflow-checkpoint-row/v1`,
  built with the live idiom — `record_schema` key, text fields bound by their
  sha256 leaf, integers bound directly, `None` passed through, `content_sha256`
  excluded, and the workflow identity bound as `_leaf(_render(row_id))`.
  `_ROW_HASH_TABLES` gains two entries; `_DOCUMENT_BOUND_TABLES` gains
  `workflow_checkpoints` so its stored body is re-digested independently of its
  digest column.

### 11.4 Replay and the reducer's own bounds

`fold` reconstructs, from events alone: `policy_version` (including adoptions),
`attempt_no`, `attempt_state`, `attempts_used`, `attempt_budget`,
`last_checkpoint_seq`, `checkpoint_count`, `compensation_state` and
`restored_checkpoint_sha256`. Every one is a pure function of the history; none
is read from a column.

Every one is also a pure function of what the history **actually recorded**. A
policy-v1 `dispatch_accepted` carries no `attempt_no` (§5.5), and `fold` reads
that member through an explicit presence check: the absent case advances no
counter, opens no attempt and raises no `KeyError`, so a v1 history folds
forever and a v1 workflow honestly folds to `attempts_used = 0`. `fold`
therefore never synthesizes a `workflow_attempts` row from historical events and
never infers an ordinal from event sequence, receipt sequence,
`runtime_task_uuid` or current state. The gate that keeps that honest zero from
being *misread* as "no attempt was ever consumed" is §5.2.1's adoption
predicate, not an inference inside `fold`.

Two landed reducer constants must be recomputed by the implementation, not
left as they are — an obligation, frozen here:

- `_SNAPSHOT_GROWTH_RESERVE` must cover **every new mutable snapshot member at
  its frozen bound** (the new counters at `protocols.INT_MAX`, the optional
  digest and state strings at their pattern maxima), so `_require_admissible_size`
  still guarantees that an admitted instance can reach any state without ever
  failing `_seal_snapshot` at `MAX_ARTIFACT_BYTES`.
- `_MAX_EVENTS_PER_COMMAND` stays **2**: no U-W3 command emits three events
  (§5.5), and the counter ceiling's headroom is unchanged. §18 row W12 pins it.

### 11.5 Migration 6 → 7

`Migration(from_version=6, to_version=7, migration_id="u-w3-runtime-recovery-v7")`,
appended to the literal `MIGRATIONS` tuple as the sixth step. Body, in order,
inside U-M1's already-open transaction (no COMMIT, no ROLLBACK, no
`meta.schema_version` touch — all three belong to `apply_migrations`):

1. Rebuild `workflows` (create under a temporary name from the live v7 DDL, copy
   every column verbatim ordered by `id`, `DROP`, `ALTER … RENAME`).
2. Rebuild `workflow_events` the same way.
3. Rebuild `workflow_commands` the same way.
4. Rebuild `workflow_intents` the same way.
5. Create `workflow_attempts` **empty**, directly under its real name.
6. Create `workflow_checkpoints` **empty**, directly under its real name.

- **No clock is read** — no row is stamped; every `created_at`/`updated_at` is
  carried across verbatim.
- **No row is derived, invented or interpreted.** There are no legacy attempt,
  checkpoint or compensation facts anywhere in the ledger, so the step has
  nothing to derive from and derives nothing. A pre-existing workflow gets no
  attempt row: `workflow_attempts` rows exist only because U-W3 observed an
  `accepted` receipt after this migration.
- The framework's `PRAGMA foreign_keys=OFF` plus its whole-database
  `foreign_key_check` before each step's commit is what makes the four
  DROP/RENAMEs legal while five sibling tables hold FKs into `workflows` — the
  2→3 precedent, applied a second time.
- **Fresh-versus-migrated equivalence**, frozen precisely across all eight
  workflow tables:

  | Tables | Requirement | Why |
  | --- | --- | --- |
  | `workflow_facts`, `workflow_receipts` | **byte-identical** `sqlite_master.sql` | U-W3 does not rebuild them; they are byte-untouched (§11.1) |
  | `workflow_attempts`, `workflow_checkpoints` | **byte-identical** `sqlite_master.sql` | created directly under their real names, from the same live DDL a fresh init uses; no rename occurs |
  | `workflows`, `workflow_events`, `workflow_commands`, `workflow_intents` | **structural equivalence** | they go through `ALTER TABLE … RENAME`, which may add identifier quoting the original `CREATE TABLE` lacked; raw `CREATE TABLE` **text** is therefore not required to be byte-identical for these four |

  **Structural equivalence is not a weaker synonym for "close enough".** It is
  the following seven-way comparison, and every one of them must hold: table
  identity; the column set **and its ordering**; every column's declared default;
  CHECK **behavior** (the same rows admitted and the same rows refused, not the
  same whitespace); foreign keys; indexes; and uniqueness constraints. Only the
  lexical form of the stored SQL text is allowed to differ, and only for the four
  rebuilt tables.

  This is the same distinction D-v0.3.43 drew for `memory` and `agents`, and it
  is declared as the **narrow supersession** §1.2 row S16 records — of exactly
  one landed assertion, `test_fresh_and_migrated_sql_is_byte_identical_for_the_six_tables`.
  Nothing else about migration integrity is relaxed: rows are still copied
  verbatim, `content_sha256` is still carried across untouched, every landed row
  hash and sealed event digest still verifies (§18 row W25), the frozen-v6 DDL
  comparison stays byte-exact (§11.6, row W23) and the fixtures stay byte-unchanged
  (§11.7, row W24). §18 row W22 implements the table above, with `events` and
  `meta` excluded exactly as the live routing/handoff scoping does.

**No migration implementation ships in Wave 0.**

### 11.6 The frozen v6 obligation, which fires here

`migrations._workflow_state_v6`'s own docstring states the rule:

> "A future unit that edits `db.WORKFLOW_TABLES` inherits the obligation to
> freeze a `_V6_WORKFLOW_*` copy here, exactly as `_V2_MEMORY_CLAIM_DDL` did."

U-W3 edits `db.WORKFLOW_TABLES` (four amended DDLs, two added), so the
obligation **fires in full**. The implementation must:

1. Freeze `_V6_WORKFLOW_TABLES` in `migrations.py` — a verbatim copy of all
   **six** v6 DDL texts as landed at `fef0c2b`, not only the four it amends. The
   5→6 step iterates the whole tuple, so a partial freeze would still let it
   build v7-shaped `receipts`/`facts` tables and stamp `schema_version = 6` —
   the exact drift `_V2_MEMORY_CLAIM_DDL` documents.
2. Repoint `_workflow_state_v6` at `_V6_WORKFLOW_TABLES`. Its behavior is
   unchanged; only its input constant moves from live to frozen.
3. Leave `_V2_MEMORY_CLAIM_DDL`, `_V3_AGENTS_DDL`, `db.MEMORY_CLAIM_DDL`,
   `db.MEMORY_GRAPH_TABLES`, `db.AGENTS_DDL`, `db.AGENT_PASSPORTS_DDL`,
   `db.ROUTING_HANDOFF_TABLES` and `passports.agent_identity_payload` untouched
   — U-W3 edits none of them, so D-v0.4.29's transfer clause does not fire for
   the 1→2, 2→3, 3→4 or 4→5 steps.

§18 row W23 byte-compares a migrated database's six workflow-table DDL texts
against `_V6_WORKFLOW_TABLES` at the moment `schema_version` reads `"6"`, so a
future edit to the live constants cannot silently rewrite history.

### 11.7 Why `tests/fixtures/**` needs no edit

The three historical fixtures drop the workflow tables by **iterating
`db.WORKFLOW_TABLES` in reverse**, and say so explicitly: "iterated from
`db.WORKFLOW_TABLES` so a seventh workflow table cannot be added without this
fixture dropping it too." Extending the tuple to eight is therefore picked up
automatically, and the reversed order drops `workflow_checkpoints` before
`workflow_attempts` before `workflows` — children first — with no edit.
`V1_SCHEMA_VERSION`/`V2_SCHEMA_VERSION`/`V3_SCHEMA_VERSION` are historical
literals unaffected by a v7 head. §18 row W24 asserts the fixtures are
byte-unchanged and still round-trip.

---

## 12. Protocols and compatibility (question 10)

### 12.1 The attempt ceiling of 10 remains normative

`10` is the frozen maximum in five live places, and **all five stay exactly as
they are**:

| Location | Value |
| --- | --- |
| `protocols/beast.work-spec/v1.schema.json` → `retry.max_attempts` | `{"minimum": 1, "maximum": 10}` |
| `protocols/beast.result-envelope/v1.schema.json` → `attempt` | `{"minimum": 1, "maximum": 10}` |
| `protocols/beast.tool-manifest/v1.schema.json` → `retry.max_attempts` | `{"minimum": 1, "maximum": 10}` |
| `agentic_os/workspecs.py::_check_retry` | `1 <= attempts <= 10` |
| `agentic_os/governance.py::validate_execution_context` | `1 <= max_attempts <= 10` |

U-W3 introduces **no sixth ceiling constant**: the reducer bounds `attempt_no`
by the artifact's own budget, which admission already proved is ≤ 10, and the
storage CHECK `attempt_no BETWEEN 1 AND 10` restates the protocol's number
rather than inventing one. Changing 10 anywhere requires an explicit protocol
compatibility decision, a `registry_version` bump and a new schema `/vN` — a
replan trigger (§21), never a silent widening.

### 12.2 No protocol schema widens

`protocols/**` and `agentic_os/protocols.py` are byte-unchanged.
`python3 tools/gen_protocols.py` produces no diff (§18 row W26). U-W3 reads
`beast.result-envelope/v1`'s already-shipped optional `compensation` block —
which the landed U-W2 §12.2 explicitly stored verbatim and left for U-W3 — and
adds nothing to it. It likewise reads that envelope's already-shipped optional
**`runtime_task_uuid`** property (§5.3.3, §10.8): the property is in the shipped
schema's `properties` and absent from its `required` list, so reading it adds
no member, changes no `required` list, and is not a protocol change.
`beast.result-envelope/v1` is not edited, and neither is `protocols.py`. The
`beast.interrupt/v1` `resume_instruction` surface is read by nothing.

### 12.3 The `aos.*` record schemas U-W3 mints or advances

These are internal canonical records in the `aos.*` house style, deliberately
not U-X1 registry artifacts (U-W2 §13.4), so minting them is not a protocol
change.

| Record | Status | Note |
| --- | --- | --- |
| `aos.workflow-command/v1` | **unchanged** | `request_dispatch`'s *payload* key set widens under policy v2; the envelope's field table does not |
| `aos.workflow-event/v1` | **unchanged** shape | seven new `event` values, all inside the existing field table |
| `aos.workflow-snapshot/v1` | **unchanged** schema string; **widened** member set | additive members only; the schema string stays `/v1` because the snapshot is a private projection with exactly one producer and one consumer inside this repository, and it is re-derived on every command rather than exchanged |
| `aos.workflow-queue-intent/**v2**` | **new version** | emitted only under policy v2; v1 intents keep being emitted for v1 workflows and keep being read forever |
| `aos.workflow-queue-receipt/v1` | **unchanged** | no new receipt kind; the nine stay frozen |
| `aos.workflow-approval-fact/v1` | **unchanged** | |
| `aos.workflow-checkpoint/v1` | **new** | §8.3 |
| `aos.workflow-restore-fact/v1` | **new** | §9.4 |
| `aos.workflow-attempt-row/v1`, `aos.workflow-checkpoint-row/v1` | **new** | §5.8 row-hash identities, like the four landed `*-row/v1` names |

**Why the intent gets a `/v2` and the snapshot does not.** The intent is the one
record that **crosses the trust boundary as a file** and that U-W2 §18 requires
U-W2.R to pin *by content hash*; changing its accepted member set is exactly
what a version number exists to announce. The snapshot never leaves the process
that built it.

---

## 13. CLI and power surface (question 11)

### 13.1 The decision: four new leaves, one flat group, seventeen total

Not a nested group: `power._PATH_DESTS` is `("command", "subcommand",
"subsubcommand")`, so `workflow recovery retry` would resolve to a three-tuple
path and change how every leaf-path predicate in `tests/test_v02_power_modes.py`
and U-W2.3 C1 reads the group. Not "no CLI": with U-W2.R absent, the CLI is the
**only** way a record crosses the boundary, so a U-W3 with no CLI would be
architecture nobody could run — which §4.3 forbids.

| Leaf | Verb submitted | Positionals | Options | Class | Ledger |
| --- | --- | --- | --- | --- | --- |
| `workflow adopt-policy WF-n` | `adopt_policy_version` | 1 | none | `authoritative_write` | yes |
| `workflow checkpoint WF-n CHECKPOINT_FILE` | `record_checkpoint` | 2 | none | `authoritative_write` | yes |
| `workflow restore WF-n FACT_FILE` | `record_restore` | 2 | none | `authoritative_write` | yes |
| `workflow compensate WF-n ENVELOPE_FILE` | `record_compensation` | 2 | none | `authoritative_write` | yes |

**There is no retry leaf, deliberately.** A retry *is* `workflow dispatch WF-n`
issued from `retrying`; the existing leaf gains one optional
`--restore CHECKPOINT_ID`. Minting a second verb for a dispatch would create two
ways to do one thing and put the token `retry` into the CLI region for no gain.

Seventeen leaves: **13 `authoritative_write` (ledger), 3 `read_only`, 1
`derived_write`.**

### 13.2 Writer / read-only behavior

All four new leaves are writers and reuse the landed `_workflow_write` shell
verbatim — same live `expected_revision` read immediately before `submit`, same
single `workflow_store.submit` call site, same byte-exact accepted/replay block,
same one-line stderr refusal, same refusal journal. **No new store function is
called from the CLI region** (§13.5).

`show` and `list` gain the new `WorkflowRecord` members automatically, because
`_workflow_record_public` iterates `__dataclass_fields__`. `verify` gains the two
new tables' row hashes inside `workflow_store.verify`, reported through the
existing `divergent_rows` tuple, so **no `VerifyReport` field is added and the
`verify` handler is unchanged**.

### 13.3 Output schemas and exit codes

- `show --json` / `list --json`: the same two documents, with `WorkflowRecord`
  carrying five additional members — `attempt_no`, `attempt_state`,
  `attempts_used`, `attempt_budget`, `checkpoint_count`. The record's field count
  therefore moves from **twenty to twenty-five**, which supersedes U-W2.3 row
  C10's `len(record_fields) == 20` pin (§1.2 row S10, §13.5). The already-frozen
  five-member shape is unchanged; only the count that the landed test pinned
  moves. No new top-level key. Key order stays canonical (dataclass order).
- Human `show` gains five aligned label lines in the existing `f"{label:<17}"`
  block, and the `_WORKFLOW_INTEGRITY_NOTE` caveat is emitted byte-unchanged.
  One of those labels reports the checkpoint count, which is why
  `cmd_workflow_show` is one of the seven functions §13.5 exempts from the
  `checkpoint` token ban.
- **No stored body is ever printed** — no checkpoint payload, no compensation
  envelope, no restore fact. The landed C18/C19/C20 obligations extend to the
  three new document classes unchanged.
- **Exit codes are unchanged**: 0 for accepted/replay and clean reads; 1 for any
  refusal, any failed verification, and any unreadable outbox row; never 2.

### 13.4 Power policy

Four new `COMMAND_POLICY` entries as one contiguous block appended to the
existing workflow block, all `_p(AUTHORITATIVE_WRITE, ledger=True)`. None is in
`RECOVERY_ALLOWED_KINDS`, so all four are blocked in recovery mode — a damaged
workspace must not decide a retry, store a checkpoint, claim a restoration or
conclude a compensation. `MODES`, `KINDS`, `RECOVERY_ALLOWED_KINDS`,
`MATRIX_COLUMNS`, every existing entry and every helper are unchanged.

`tests/test_v02_power_modes.py::RecoveryTests.BLOCKED` gains **four** rows
(`adopt-policy`, `checkpoint`, `restore`, `compensate`) in the existing
contiguous workflow block. Measured against the live parser, that makes
`should_block - covered` and `covered - should_block` both empty; the
`len(leaves) > 40` predicate rises from 108 to 112 and still holds; every
prefix-scoped count and the bidirectional classification coverage still pass.

### 13.5 Which U-W2.3 test exclusions are superseded, and which are narrowed

| Row | Landed obligation | U-W3 disposition |
| --- | --- | --- |
| **C1** | `CONTRACT_LEAVES` is thirteen; `leaves == [("workflow", v) …]`; `len(leaves) == 13` | **superseded**: the hand-transcribed constant gains four members; `len == 17`. Still hand-transcribed from this contract's §13.1 table, never read from `cli` |
| **C2** | 9 / 3 / 1 of 13 | **superseded**: 13 / 3 / 1 of 17 |
| **C3** | `CONTRACT_OPTIONS` / `CONTRACT_POSITIONALS` | **superseded**: four new rows; `dispatch` gains `--restore`; the `--actor` prohibition is re-asserted for all seventeen |
| **C5** | `len(WORKFLOW_STATES) == 13` | **superseded**: `== 14`, still member-by-member against the engine |
| **C10** | `len(record_fields) == 20` for the `show --json` / `list --json` `WorkflowRecord` projection | **superseded**: `== 25`, the landed twenty plus the five already-frozen §13.3 members. Everything else in C10 is re-asserted unchanged — the projection is still compared field-for-field against `WorkflowRecord.__dataclass_fields__`, `list --json` still matches `show --json` exactly, and no stored body enters either document |
| **C11** | ten `BLOCKED` rows | **superseded**: fourteen |
| **C21** | every README example runs | **unchanged obligation**, new content: the U-W3 README section's fenced blocks are parsed and run like U-W2.3's |
| **C22** | AST scan of the region | **narrowed in exactly one place**: the `len(_region_nodes()) >= 13` floor becomes `>= 17`. Everything else is **re-asserted unchanged** — no `subprocess`/`socket`/`importlib`/`time`/`sqlite3` import, no `while` loop, no `eval`/`exec`/`system`/`popen`/`urlopen` call, no bare `except`, no path expansion or normalisation, and **exactly one `workflow_store.submit(` call site** |
| **C22 (store mapping)** | the region calls exactly six store functions | **unchanged**: U-W3 adds no store function to the region; `rebuild` stays absent |
| **C26** | fifteen tokens banned across the whole region | **narrowed, not deleted** (below) |
| C4, C6–C9, C12–C20, C23–C25 | | **unchanged**, and extended in coverage to the four new leaves where they are leaf-parameterised |

**U-W2.3 accounting, exactly: six rows superseded, two rows narrowed.**
Superseded: **C1, C2, C3, C5, C10, C11**. Narrowed: **C22** (its
`_region_nodes()` floor only) and **C26** (its token set only). Every other
U-W2.3 row is unchanged. There is no third disposition and no row is silently
dropped.

**The C26 narrowing, exactly.** The row's real intent is that U-W2.3's own
surface carries no queue, retry, monitor or interrupt vocabulary. That intent is
preserved:

- **Still banned across the entire region**, unchanged: `ai-company-runtime`,
  `postgres`, `psycopg`, `lease`, `heartbeat`, `worker`, `temporal`, `monitor`,
  `interrupt`, `.claude`, `aos.db`, **`resume`**, and **`retry`**. `resume` stays
  banned because U-W3's verb is `restore`; `retry` stays banned because U-W3 has
  no retry leaf (§13.1). Keeping thirteen of the landed fifteen tokens
  region-wide — the eleven uncontested plus `retry` and `resume`, two of the
  four contested ones — is what makes this a narrowing rather than a repeal.
  Beyond the token scan, the substance those tokens stand for stays prohibited
  everywhere in U-W3 outside its existing authorised boundaries: `temporal`,
  `worker`, `postgres`, `lease` and `heartbeat` as tokens; and private-runtime
  implementation, durable-engine implementation and unrelated queue machinery as
  behavior (§2.2).
- **Permitted only inside an explicitly enumerated set of exactly SEVEN
  functions**: `checkpoint` and `compensat`, and nowhere else. The set, with the
  mechanical reason each member needs it:

  | # | Function | Why the token is unavoidable there |
  | --- | --- | --- |
  | 1 | `cmd_workflow_checkpoint` | submits `record_checkpoint` and reads the checkpoint document argument |
  | 2 | `cmd_workflow_restore` | submits `record_restore`, whose fact names a `checkpoint_id` and `checkpoint_sha256` |
  | 3 | `cmd_workflow_compensate` | submits `record_compensation` |
  | 4 | `cmd_workflow_adopt_policy` | its help and refusal surface name the checkpoint and compensation capabilities adoption unlocks |
  | 5 | `_build_workflow_parser` | declares the four leaves, their file positionals and `dispatch --restore CHECKPOINT_ID` |
  | 6 | **`cmd_workflow_dispatch`** | it builds the `request_dispatch` payload, whose policy-v2 key is **`restore_checkpoint_id`** (§9.2). The token is in the payload key itself; there is no way to submit a restore-carrying dispatch without it, and inventing a synonym would put a second name on a frozen payload key |
  | 7 | **`cmd_workflow_show`** | it renders the human record, one of whose five new aligned label lines reports the **checkpoint count** (§13.3). The `--json` projection is automatic through `_workflow_record_public`, but the human label block is a literal tuple inside this function |

  **Every other function in the workflow CLI region retains both token
  prohibitions in full**: the eleven remaining landed handlers
  (`cmd_workflow_admit`, `cmd_workflow_validate`,
  `cmd_workflow_request_approval`, `cmd_workflow_approve`,
  `cmd_workflow_revoke_dispatch`, `cmd_workflow_cancel`, `cmd_workflow_receipt`,
  `cmd_workflow_result`, `cmd_workflow_list`, `cmd_workflow_verify`,
  `cmd_workflow_export_intents`) and every helper (`_workflow_write`,
  `_workflow_command`, `_workflow_document`, `_workflow_identity`,
  `_workflow_state_choices`, `_workflow_record_public`,
  `_journal_workflow_refusal`, `_print_workflow_outcome`,
  `_workflow_export_refusal`) must still be free of both.

The exemption grows from five functions to seven and **no CLI leaf is added**:
the count stays four new leaves and seventeen total (§13.1). §18 row W28
implements the narrowed row and additionally asserts that the enumerated set is
exactly those seven names, so the exemption cannot silently spread. An **eighth**
function needing one of these two narrowly exempted tokens is §21 replan trigger
10.

---

## 14. Crash and failure matrix (question 13)

`db.transaction`'s `with conn:` rolls back on any exception, so the invariant
holds at every pre-commit point without exception handling of its own. Every row
below is a forced exception injected at the named boundary, or a forced state
planted before the named command.

**The governing rule, above every row: no automatic repair may fabricate
authority or evidence.** U-W3 contains no repair path, no re-seal, no re-stamp,
no `--force` and no `--repair`. Every recovery below is either a no-op, a
refusal, or a human act.

| # | Crash / hostile point | Committed state after | Next command's behavior | Recovery |
| --- | --- | --- | --- | --- |
| 1 | **before attempt reservation** (inside `request_dispatch`, before `decide`) | nothing | identical decision on re-issue | re-run the command |
| 2 | **after reservation, before dispatch** (after `decide`, before `_insert_intent`) | nothing — the whole transaction rolls back; no event, no intent, no revision | identical decision | re-run |
| 3 | **after dispatch, before acknowledgement** (committed intent, no receipt) | `dispatch_intent_id` set, intent `outstanding`, no attempt row, `attempts_used` unchanged | a second `request_dispatch` refuses `dispatch_already_pending` | export and deliver the intent file; or `revoke-dispatch` (advisory) |
| 4 | **after acknowledgement, before runtime completion** | attempt row `open`, workflow `scheduled`/`running` | receipts apply normally | none needed |
| 5 | **after failure, before the retry decision** | workflow `retrying`, attempt row `failed`, `attempts_used = attempt_no` | `request_dispatch` reserves `attempt_no + 1`, or refuses `attempt_budget_exhausted` | operator decides |
| 6 | **after the retry decision, before redispatch** (crash between the accepted `request_dispatch` and the file export) | committed intent, `outstanding` | re-running `export-intents` writes the identical content-addressed file (`unchanged`) | re-export |
| 7 | **after checkpoint write** (crash after COMMIT) | one checkpoint row + one `checkpoint_recorded` event | a redelivered identical `record_checkpoint` command is a `replay`; a same-`checkpoint_id` different body refuses `checkpoint_conflict` | none needed |
| 8 | **checkpoint corruption** (stored bytes tampered) | the row's digest no longer recomputes | `workflow verify` lists it in `divergent_rows` and exits 1; any restore naming it refuses `checkpoint_ineligible`; every mutating command on the workflow refuses `snapshot_divergence` if the row hash is also broken | human restores a verified backup; **nothing is rewritten** |
| 9 | **stale checkpoint** (a checkpoint from attempt 1 named while attempt 3 is open) | unchanged | permitted — §9.3 requires only `from_attempt_no < into_attempt_no`; staleness is the producer's judgment, and AOS refuses to invent a recency policy it cannot verify | declared in §20 |
| 10 | **duplicate checkpoint** (same body, same id, redelivered) | unchanged | `replay`; the `ON CONFLICT`-free INSERT-ONCE table is never written twice because the command dedupe axis answers first | none |
| 11 | **duplicate checkpoint id, different body** | unchanged | `checkpoint_conflict`; never made legal by redelivery | author a correct record |
| 12 | **resume before restore** (a `resumed` receipt with no `checkpoint_restored`) | workflow → `running` | accepted and correct: it is a **wait exit**, not a restoration, and no U-W3 predicate reads it as one | none — this is the normal U-W2 path |
| 13 | **restore before resumed event** (`record_restore` while `scheduled`) | `checkpoint_restored` appended, state unchanged | accepted: restoration is stateless and independent of wait exits | none |
| 14 | **compensation start** (crash after `compensation_started` COMMIT) | workflow `compensating`, the attempt row closed `failed` with the failing result digest (§6.2), compensate intent `outstanding` | `record_result` refuses `illegal_transition` (it is legal in `running` only); `request_cancel` refuses `illegal_transition` (`compensating → cancelled` is illegal in every version); `record_compensation` and a `failed` receipt are the only legal conclusions | export and deliver the compensate intent |
| 15 | **compensation partially applied** | unchanged in AOS | the producer MUST report `compensation.state = "failed"`; a report of `applied` for partial work is a false claim AOS cannot detect | declared in §20 |
| 16 | **compensation completed before receipt** (the act happened, no record reached AOS) | workflow still `compensating` | nothing is inferred; the workflow waits | a human authors the envelope |
| 17 | **duplicate compensation receipt / envelope** | unchanged | identical body + identical `command_id` → `replay`; identical body + new `command_id` → `compensation_already_concluded`; different body → `compensation_already_concluded` | none |
| 18 | **attempt budget exhaustion** | after the last attempt fails, the workflow is terminal `failed` — never `retrying` | every command refuses `workflow_terminal` | admit a new WorkSpec (a new digest, a new identity) |
| 19 | **`fold`/projection divergence** (a planted `workflow_attempts` row hash) | — | `verify` reports `snapshot_divergence` with the pair in `divergent_rows`; mutating commands refuse and write nothing; read paths stay total | human restores a verified backup |
| 20 | **policy adoption crash** (crash inside `adopt_policy_version`) | nothing | identical decision on re-issue | re-run |
| 21 | **schema-migration interruption** (crash at any point inside the 6→7 step — between rebuilds, mid-copy, or before the framework's commit) | nothing — the step runs inside the U-M1 transaction framework, which owns atomicity; a mid-step crash rolls back the whole migration and `schema_version` still reads `"6"` | re-running `apply_migrations` re-executes the complete 6→7 step from its start; `schema_version` is stamped `"7"` only after the complete step succeeds, so no partial v7 schema is ever accepted or observable | re-run the migration |

---

## 15. Security and hostile-data handling

Every rule is the landed U-W2.2 §18 / U-W2.3 §7 discipline, extended to the
three new document classes with no relaxation.

1. **Every persisted row is untrusted input.** Explicit type checks *before*
   every read, never a caught `KeyError`/`TypeError`/`AttributeError` after the
   fact. Every digest recomputed from stored bytes at every use.
2. **Stored text is data.** It never becomes SQL (every statement parameterized;
   the only interpolated identifiers are the frozen `db.py` table-name
   constants), never a path, never a command, never a tool input, never a
   message.
3. **No stored body surfaces.** A checkpoint payload, a compensation envelope
   and a restore fact are never printed to stdout or stderr, never journaled,
   never placed in an event payload, and never carried in a refusal. Event
   payloads stay closed to enum members, validated identifiers, bounded integers
   and digests.
4. **Refusals are bounded and value-free.** Code + schema-safe path + fixed
   hint. Diagnostics carry bounded integers and closed lowercase codes only;
   anything else is dropped by `_safe_diagnostics`, whose
   `_CLOSED_DIAGNOSTIC_VALUES` gains the fourteen new refusal codes, the new
   attempt states and the new intent kind.
5. **Secret-shaped checkpoint payloads are refused, never stored** (§8.2). The
   refusal names the path, never the value.
6. **Instruction-bearing and control text is inert**: a checkpoint payload
   containing an injection string, an ESC/CR/BEL byte or a bidi override changes
   no decision and reaches no terminal, because it is never rendered.
7. **No filesystem write except the landed `export-intents`**, which stays
   `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW`, content-addressed, and never
   overwrites. Compensate intents and restore-carrying dispatch intents export
   through the same path with names matching
   `^(dispatch|cancel|compensate)-[0-9a-f]{64}\.json$` **by construction**.
8. **No process, network, socket, subprocess, MCP or A2A surface**, and no
   second database handle. The store touches only `aos.db`.
9. **No credential, token or environment-variable read.**
10. **Optional corroborating members are checked when present and never
    imagined when absent.** A submitted `beast.result-envelope/v1` may carry
    `runtime_task_uuid`; the shipped schema makes it optional. A **present**
    value that contradicts the attempt's recorded binding refuses
    `runtime_uuid_mismatch` — a hostile or mistaken document does not get to
    have its contradicting evidence quietly discarded — while an **absent** one
    refuses nothing and is never replaced by a default, a lookup or an inferred
    value (§5.3.3, §10.8). The uuid is compared as an opaque validated
    identifier; it never becomes a path, a query filter beyond the parameterized
    equality, a message or a rendered value.

---

## 16. Ownership prose reconciliation

Recorded once, in §1.4, and not restated: `agentic_os/governance.py` and the
U-K1/U-T1 contract keep their historical prose byte-unchanged; the authoritative
U-W3 interpretation is frozen here; and the retouch obligation transfers to the
first future unit that already modifies `governance.py`.

---

## 17. Exact path boundary (question 15)

**The table below is CLOSED and EXHAUSTIVE. Twenty-one paths.** A path outside
it appearing in any U-W3 wave is `FAIL — GOVERNED REPLAN REQUIRED`, not a quiet
extension. Nothing here is standing authority for any later wave or unit. There
is no "as needed", no "related files", no "supporting paths".

### 17.1 Production (7)

| # | Path | New/modified | Exact responsibility |
| --- | --- | --- | --- |
| 1 | `agentic_os/workflow_engine.py` | modified | policy v2: the frozen v1 state tuple and matrix, the fourteen-state tuple, the v2 matrix, four new commands, seven new events, the third intent kind, fourteen new refusal reasons, `ShellFacts`, the checkpoint / restore / compensation record verifiers, the attempt lifecycle in `decide` and `fold`, and the recomputed `_SNAPSHOT_GROWTH_RESERVE` |
| 2 | `agentic_os/workflow_store.py` | modified | two new table SQL blocks and row-hash payloads, the attempt open/close and checkpoint insert helpers, checkpoint resolution into `ShellFacts`, the extended `WorkflowRecord`, and `verify` covering both new tables |
| 3 | `agentic_os/db.py` | modified | `SCHEMA_VERSION = "7"`, two new DDL constants, four amended DDL constants, `WORKFLOW_TABLES` extended to eight, schema composition |
| 4 | `agentic_os/migrations.py` | modified | the frozen `_V6_WORKFLOW_TABLES` copy and the repointed 5→6 step, the 6→7 step `u-w3-runtime-recovery-v7`, and its `MIGRATIONS` entry |
| 5 | `agentic_os/cli.py` | modified | four new leaves and handlers plus `dispatch --restore`, inside the existing `workflow` group — and no other region |
| 6 | `agentic_os/power.py` | modified | exactly four `COMMAND_POLICY` entries as one contiguous block; no existing entry, kind, constant or helper changes |
| 7 | `README.md` | modified | exactly one new U-W3 unit section, placed after the U-W2 section; no other region, and the pre-existing stale global schema-version paragraph is not repaired (D-v0.4.102) |

### 17.2 New focused test (1)

| # | Path | Kind | Exact responsibility |
| --- | --- | --- | --- |
| 8 | `tests/test_v04_workflow_recovery.py` | NEW | the §18 matrix, rows W1–W30 |

### 17.3 Forced existing-test edits (11)

Each is mechanically forced by a frozen count, a version pin or a superseded
row, and each is bounded to exactly the named class of edit.

| # | Path | Forced by | Exact edit |
| --- | --- | --- | --- |
| 9 | `tests/test_v04_workflow_engine.py` | S1–S8 | the vocabulary counts (13→14 states, 9→13 commands, 17→24 events, 43→57 reasons, 25→35 active / 3→0 reserved cells), the hand-transcribed matrix split into a frozen v1 expectation plus a v2 expectation, the `_PUBLIC` name list, and the `ShellFacts` rename |
| 10 | `tests/test_v04_workflow_store.py` | S1, **S2**, S3, S4, **S5**, **S6**, S7, S12, **S16**, **S17** | **closed edit class — exactly the twelve mechanically forced changes enumerated below and nothing else** (S17 raised the count from eleven) |
| 11 | `tests/test_v04_workflow_cli.py` | S10, S11 | C1, C2, C3, C5, **C10** (`len(record_fields)` 20 → 25), C11 constants; C22's `>= 13` floor → `>= 17`; C26's narrowed **seven-function** token rule |
| 12 | `tests/test_v02_migrations.py` | S12 | `LATEST_VERSION 6→7`, the chain tuple, the two `latest_version` literals, the two `migration_id` literals |
| 13 | `tests/test_v02_power_modes.py` | S10 | four `RecoveryTests.BLOCKED` rows in the existing contiguous workflow block, and the one `db.SCHEMA_VERSION` literal |
| 14 | `tests/test_core.py` | S12 | the one `db.SCHEMA_VERSION` literal |
| 15 | `tests/test_v03_memory_claims.py` | S12 | the one `db.SCHEMA_VERSION` literal |
| 16 | `tests/test_v03_memory_graph.py` | S12 | the `SCHEMA_VERSION`/`LATEST_VERSION`/`latest_version` literals and the chain rows |
| 17 | `tests/test_v04_agent_passports.py` | S12 | the version literal, the test name `…_is_version_six`, and the chain rows |
| 18 | `tests/test_v04_agent_catalog.py` | S12 | the two `"6"` literals and the test name `test_schema_stays_version_six` |
| 19 | `tests/test_v04_routing_handoffs.py` | S12 | the `SCHEMA_VERSION`/`LATEST_VERSION`/`latest_version`/`current_version` literals, the chain rows, and the `MIGRATIONS[-1].migration_id` literal |

#### Path 10's closed licensed edit class, enumerated

`tests/test_v04_workflow_store.py` stays **inside** the twenty-one-path boundary
and is forced on several axes at once, so its licence is written out in full
rather than described. The licensed edits are exactly these twelve classes:

| # | Licensed edit | Forced by |
| --- | --- | --- |
| E1 | the hand-transcribed **state vocabulary** (13 → 14) | S1 |
| E2 | the hand-transcribed **event vocabulary** (17 → 24) | S4 |
| E3 | the hand-transcribed **command vocabulary** (9 → 13) | S3 |
| E4 | **`CONTRACT_COLUMNS`** entries for `workflow_attempts` and `workflow_checkpoints` | S12 |
| E5 | **`NO_DEFAULT_COLUMNS`** entries for the two new tables | S12 |
| E6 | **tamper-corpus** entries for the two new tables | S12 |
| E7 | the one **`AdmissionFacts` → `ShellFacts`** construction touch | S7 |
| E8 | the **version, table-count and migration-chain literals** — `SCHEMA_VERSION "6"→"7"`, `SIX_TABLES`→`EIGHT_TABLES`, `test_fresh_bootstrap_stamps_version_six`→`…_seven`, the `(5,6,…)` chain row plus a `(6,7,"u-w3-runtime-recovery-v7")` row, and the `latest_version`/`current_version` literals | S12 |
| E9 | **`_TABLE_CONSTANTS` additions** for `WORKFLOW_ATTEMPTS_TABLE` and `WORKFLOW_CHECKPOINTS_TABLE`, so the §18.5 SQL-interpolation scan keeps admitting exactly the frozen `db.py` table-name constants and nothing else | S12 |
| E10 | the **policy-v2 updates inside `test_engine_vocabularies_are_unchanged_and_unshadowed`** — `WORKFLOW_INTENT_KINDS` 2 → 3, `len(WORKFLOW_REFUSAL_REASONS)` 43 → 57, `TRANSITION_POLICY_VERSION` 1 → 2, `SUPPORTED_POLICY_VERSIONS` `(1,)` → `(1, 2)`, and the matrix dimension 13 → 14 — together with the **zero-reserved-edge** assertions that replace the `("reserved",)` expectation for `running → compensating`, **while preserving policy-v1 replay coverage**: the frozen v1 tuple and matrix stay asserted, a v1 snapshot still refuses `transition_reserved` on `compensating → failed`, and the store's non-shadowing assertion is re-asserted unchanged | S2, S5, S6 |
| E11 | the **fresh-versus-migrated SQL equivalence** assertions: `test_fresh_and_migrated_sql_is_byte_identical_for_the_six_tables` splits into byte-identity for `workflow_receipts`, `workflow_facts`, `workflow_attempts` and `workflow_checkpoints`, and the seven-way **structural equivalence** of §11.5 for `workflows`, `workflow_events`, `workflow_commands` and `workflow_intents` | S16 |
| E16 | the **`HostileRowTests` CI-runtime repair** — a FIXTURE-SCOPE change and nothing else. One `Journey` may be reused per **(table, column) pair** instead of one per hostile value, so the matrix stops growing the database it makes `verify` and `list_workflows` walk. The licence is conditional on all of the following, each of which the repair must implement and prove: every existing hostile table, column and value and every `subTest` identity remains, in the same order and under the same tag; the tamper target remains the REAL persisted row, never a mock; every hostile value begins from a baseline PROVED clean before the tamper is applied; restoration runs through `finally`, so a failed assertion, an escaped exception and a storage-refused tamper all reach it; the complete affected persisted state is restored EXACTLY — the workflow row, its rows in all seven child tables and its `events` journal rows, rewritten unconditionally rather than un-done selectively; post-restore row equality against the baseline and a whole-store leakage check at the end of each pair are both MANDATORY; a restoration failure aborts the matrix visibly rather than being recorded and stepped over; `_exercise` and every behavioral assertion in it stay byte-unchanged. No sampling, no skipping, no `xfail`, no deletion, no assertion weakening, no smaller representative corpus and no CI timeout increase. No production, workflow, protocol or CI file changes | S17 |

E12–E15 are §22 A22's four extension rows and keep their labels: `A22/E15` is
cited by name inside `tests/test_v04_workflow_store.py`, so those four are
immovable and the twelfth class of this table is numbered **E16**. Path 10's
complete licensed inventory is therefore E1–E16 — the twelve of this table plus
A22's four — and no other edit to that file is licensed by anything.

Nothing else in that file may be edited. In particular no assertion is deleted,
no `subTest` is dropped, no tamper case is weakened, and no bound is loosened:
every change above is a count, a literal, a constant entry, the one narrow
equivalence split S16 declares, or the one fixture-scope repair S17 declares —
and that repair adds assertions rather than removing any. **This does not
authorise a twelfth existing test path** — §21 replan trigger 14 is unchanged.

### 17.4 Architecture documents (2)

| # | Path | Kind | Exact responsibility |
| --- | --- | --- | --- |
| 20 | `DECISIONS.md` | modified | the prepended U-W3 Wave 0 section, D-v0.4.103 … D-v0.4.117; everything below the prepend stays byte-identical |
| 21 | `agentic-os-v0.4-u-w3-runtime-recovery-contract.md` | NEW | this contract |

### 17.5 Migration and schema paths

Every migration and schema path is already inside the table: the DDL lives in
path 3, the migration step and its frozen v6 copy in path 4. **There is no
separate migration file, no `migrations/` directory, and no SQL file** — this
repository has never had one, and U-W3 introduces none.

### 17.6 Permitted mechanical paths

Exactly the eleven of §17.3, for exactly the edit classes named there. No other
mechanical path is permitted, and this licence is **not standing**: a future
unit meeting the same mechanical necessity needs its own governed decision.

### 17.7 Paths deliberately NOT changed, with the reason

| Path | Why not |
| --- | --- |
| `agentic_os/governance.py` | §1.4 — the retouch condition is not met |
| `agentic_os/protocols.py`, `protocols/**` | §12 — no protocol change |
| `agentic_os/workspecs.py` | the compiler's static attempt validation is U-W1's and is correct as landed |
| `agentic_os/ids.py` | `PREFIXES["workflow"] = "WF"` already landed; U-W3 mints no new entity id |
| `agentic_os/events.py`, `ops.py`, `models.py`, `utils.py`, `doctor.py` | no journal-framework, vocabulary or integrity-surface change; `events.emit` is called unchanged |
| `tests/fixtures/**` | §11.7 — the shared-tuple discipline makes them adapt with no edit |
| `.github/workflows/ci.yml`, `tools/**`, `tests/test_v04_delivery_gate.py` | CI runs `unittest discover` and `compileall`; a new test module is discovered without an edit |
| `pyproject.toml` | `packages = ["agentic_os"]` already includes the module; no dependency, no package data |
| `AGENTIC_OS_BLUEPRINT.md`, `RECOVERY.md`, `TROUBLESHOOTING.md`, every landed contract | §2.2 — unrelated documentation cleanup is excluded |
| `/home/daksh/Projects/AICompany` | §2.2 — no private-runtime change |

### 17.8 Exact validation commands

**Focused (the U-W3 row set and every forced file):**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_workflow_recovery
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_workflow_engine
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_workflow_store
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_workflow_cli
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v02_migrations
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v02_power_modes
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_core
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v03_memory_claims
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v03_memory_graph
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_agent_passports
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_agent_catalog
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_routing_handoffs
```

**Full (the implementation wave's acceptance):**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q agentic_os tests tools aos.py aos_hooks.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
python3 tools/gen_protocols.py
python3 tools/verify_ci_workflow.py
git status --porcelain
git diff --check
```

`python3 tools/gen_protocols.py` must leave the tree clean — that is the
mechanical proof of §12.2.

---

## 18. Test and acceptance matrix (frozen)

`tests/test_v04_workflow_recovery.py`, rows W1–W30. Conventions are the live
tree's: subprocess invocation through
`[sys.executable, str(REPO_ROOT / "aos.py"), "--root", str(root), *argv]` with
`PYTHONDONTWRITEBYTECODE=1`; parser and policy assertions in-process; canonical
fixtures built with a test-local `_seal()` helper so a drifting engine cannot
vouch for itself.

| # | Row | Independent expected-value source | Defect it kills |
| --- | --- | --- | --- |
| W1 | the fourteen states, thirteen commands, twenty-four events, fifty-seven reasons, three intent kinds, nine receipt kinds are exactly these tuples | this contract's §5, hand-transcribed | a silently added or renamed vocabulary member |
| W2 | `TRANSITION_POLICY_VERSION == 2`; `SUPPORTED_POLICY_VERSIONS == (1, 2)`; the frozen v1 tuple and matrix are byte-equal to the landed ones at `fef0c2b` | `git show fef0c2b:agentic_os/workflow_engine.py` parsed in-test | v1 history re-deriving under v2 rules |
| W3 | **v2's active-edge set is a strict superset of v1's**, cell by cell, same driver | both matrices as data | a v1 edge narrowed or removed by v2 |
| W4 | 35 active, 0 reserved cells in v2; `compensating → cancelled` is illegal, not reserved | a hand-transcribed §5.3 table | a miscounted or mis-typed cell |
| W5 | all three v1 reserved edges are drivable in v2; a v1 snapshot still refuses `transition_reserved` on `compensating → failed` | the §5.3.1 table | activating two edges and claiming three |
| W6 | `partial`/`unknown` still refuse `result_outcome_inconclusive` under v2 and mutate nothing | the §5.3.3 rule | a silent widening |
| W7 | `adopt_policy_version` is forward-only, non-terminal-only, stateless, one event, one revision; the event carries both versions and `fold` reconstructs the change. **And it is gated**: adoption is permitted only under §5.2.1's A1–A3, so a policy-v1 workflow in `scheduled`, `running`, `waiting_input`, `waiting_approval` or `paused` with no authoritative attempt history refuses `policy_version_not_upgradable` and mutates nothing, while a pre-dispatch v1 workflow with no reservation, no binding and no attempt history adopts; a v1 workflow whose reservation is outstanding refuses until `revoke-dispatch` retracts it | in-process reducer calls, one case per post-dispatch state | a downgrade, a silent adoption inside another verb, a state change, **an adoption that leaves a live runtime task with no attempt to belong to** |
| W8 | attempt reservation consumes nothing; a `rejected` or `revoked` dispatch consumes nothing; only an `accepted` receipt opens an attempt and sets `attempts_used`. **Version compatibility**: a policy-v1 `dispatch_accepted` folds with no `KeyError`, advances no `attempts_used` and opens no attempt; under policy v2 an acceptance with no recorded v2 reservation to number it refuses `receipt_unbound`; no ordinal is synthesized from event sequence, receipt sequence, `runtime_task_uuid` or state, and no `workflow_attempts` row is ever back-filled | the §6.2 table and a hand-built v1 history | burning a budget slot on an adapter rejection; **inventing an attempt number policy v1 never wrote** |
| W9 | `attempt_no` is bounded by the artifact's budget; the default with no `retry` block is 1; `attempt_budget_exhausted` fires at the bound | the artifact read directly | an off-by-one budget |
| W10 | a result whose `attempt` ≠ the open attempt refuses `attempt_mismatch`; one whose `attempt` > budget refuses `result_attempt_exceeded`; neither records anything | in-process | accepting the runtime's number |
| W11 | the six §7.3 non-retry discriminations append no event, consume no attempt and change no state — five driven in-process (lock wait, command replay, intent redelivery, receipt redelivery, `revision_mismatch`); the sixth, private-runtime task-attempt retry, is asserted structurally, since no AOS surface exists to observe it | the §7.3 table | a hidden re-issue |
| W12 | `_MAX_EVENTS_PER_COMMAND == 2` and no v2 command emits three events | every verb driven in-process | a counter-ceiling underflow |
| W13 | attempt 2's `intent_id` and `idempotency_key` differ from attempt 1's, derive from the unchanged formulas, and the intent carries `attempt_no`, `attempt_budget`, `supersedes_runtime_task_uuid` | the formulas recomputed in-test | a reused idempotency key; an invisible second runtime task |
| W14 | a checkpoint is bound to workflow, WorkSpec digest, attempt and runtime task, and a mismatch on each refuses its exact code; the §8.4 state gate admits exactly `running`/`waiting_input`/`waiting_approval`/`paused` and refuses every other state; `waiting_input` and `paused` are reached only by a hand-authored receipt and are asserted as declared-unreachable in wave 1, never as exercised paths | in-process, driving all fourteen states | a checkpoint accepted for another workflow, another attempt, or a state with no open attempt; a test that pretends an unreachable state is live |
| W15 | checkpoint bounds: payload > 65536 bytes, 9th per attempt, 81st per workflow each refuse; the limits are derived, not typed twice | `protocols.MAX_ARTIFACT_BYTES` and the protocol ceiling read as data | a tuned magic number |
| W16 | a secret-shaped checkpoint payload is **refused and not stored**; the refusal names the path only; no row appears | planted AKIA key, private-key header, bearer token | a stored plaintext credential; a silently redacted checkpoint |
| W17 | checkpoints are append-only: identical redelivery is `replay`; same id + different body is `checkpoint_conflict`; no `UPDATE`/`DELETE` targets the table anywhere in the tree | AST + SQL scan of `workflow_store.py` | an overwritten checkpoint |
| W18 | a tampered checkpoint body is reported in `divergent_rows`, is `checkpoint_ineligible` for restore, and is never repaired | direct SQL tamper | silent repair |
| W19 | **`run_resumed` is never restoration**: a `resumed` receipt sets no restoration member, and `fold` derives none | the folded snapshot compared field-by-field | conflating the two resumes |
| W20 | `checkpoint_restored` changes no state, and the five §9.3 eligibility conjuncts each refuse their exact code | in-process | restoring in `compensating` or from the current attempt |
| W21 | compensation authority: a result with `compensation.state = "pending"` drives `running → compensating`; **no tool manifest, compile finding or `recovery.action` can**. **And the conclusion binds by the §10.8 eight rules**: `attempt` is mandatory and must equal the attempt `compensation_started` recorded (`attempt_mismatch` otherwise); an envelope **omitting** `runtime_task_uuid` concludes normally, because the shipped schema makes it optional; one **carrying** it must match the compensating attempt's binding, and a mismatch refuses `runtime_uuid_mismatch` and records nothing; a matching uuid grants no authority — an envelope with a correct uuid and a wrong `attempt` still refuses | a WorkSpec whose resolved tool declares `compensating_action` and `invoke_compensation`, driven to failure with no `compensation` block → `failed`, not `compensating`; plus `beast.result-envelope/v1.schema.json` read as data to prove `runtime_task_uuid` is a property and is not in `required` | descriptive metadata becoming execution authority; **a contradicting runtime uuid silently ignored, or an absent optional one treated as a defect** |
| W22 | migration 6→7: **byte-identical** fresh-vs-migrated `sqlite_master.sql` for `workflow_receipts`, `workflow_facts` and the two new tables; **structural equivalence** for the four rebuilt tables across all seven facets of §11.5 — table identity, columns and ordering, defaults, CHECK behavior, foreign keys, indexes, uniqueness — with raw SQL text explicitly not required to match for those four; no row touched; no clock read; the step reads and writes no `meta` | `sqlite_master.sql` plus `PRAGMA table_info` / `index_list` / `foreign_key_list`, and CHECK behavior probed by insert, with `events`/`meta` excluded per the live scoping | drifting DDL; a re-stamped row; **a quoting difference passed off as a structural change, or a structural change hidden behind "structural"** |
| W23 | the frozen `_V6_WORKFLOW_TABLES` is byte-equal to `db.WORKFLOW_TABLES` at `fef0c2b`, and a database migrated to exactly v6 carries those six texts | `git show fef0c2b:agentic_os/db.py` | history following the schema forward |
| W24 | `tests/fixtures/**` are byte-unchanged and still round-trip v1/v2/v3 → v7 | file hashes + a full forward migration | a fixture silently carrying v7 tables |
| W25 | every landed row hash and every sealed event digest still verifies after the 6→7 migration | `workflow verify` on a pre-migration workflow | a rebuild that broke integrity |
| W26 | `protocols/**` and `agentic_os/protocols.py` are byte-unchanged; `tools/gen_protocols.py` leaves the tree clean; the ceiling is 10 in all five places | file hashes and the five sources read directly | a silently widened schema |
| W27 | U-W3 imports no manifest, catalog, passport, governance, routing or handoff surface; no `beast.interrupt/v1` is read anywhere | AST import scan of the two engine/store modules and the CLI region | an authority leak |
| W28 | the narrowed C26 rule: thirteen of the landed fifteen tokens (the eleven uncontested plus `retry` and `resume`) banned region-wide; `checkpoint`/`compensat` permitted in exactly **seven** enumerated functions — `cmd_workflow_checkpoint`, `cmd_workflow_restore`, `cmd_workflow_compensate`, `cmd_workflow_adopt_policy`, `_build_workflow_parser`, `cmd_workflow_dispatch`, `cmd_workflow_show` — asserted as an exact set, with every other function in the region proved free of both | the §13.5 lists, hand-transcribed | a spreading exemption; **an exemption set that drifts by addition or by omission** |
| W29 | no `while` loop, no `time.sleep`, no recursive `submit`, exactly one `workflow_store.submit(` call site, in the CLI region **and** in `workflow_store.py` **and** in `workflow_engine.py` | AST scan | a retry loop hiding in the shell |
| W30 | the twenty-one crash points of §14 each leave the committed state the table names, and no repair path exists | forced exceptions at the named boundaries | a partial write; a fabricated authority |

Rows W1–W13 and W19–W21 are engine-level and additionally run against
`tests/test_v04_workflow_engine.py`'s harness style; W14–W18, W22–W25 and W30
are store-level; W26–W29 are tree-level.

**U-W2 §19 rows 1–22 and U-W2.3 §9 rows C1–C26 remain the FLOOR**, with the
supersessions of §13.5 applied. A U-W3 that passes W1–W30 while breaking any
unsuperseded landed row is a defect.

---

## 19. Delivery identity (question 16)

Every provisional identity is **adopted unchanged**; no repository evidence
proves any of them incompatible.

| Item | Value |
| --- | --- |
| Branch | `v0.4-u-w3-runtime-recovery` |
| Worktree | `/home/daksh/Projects/agentic-os-u-w3` |
| Base | `fef0c2b3fd8e881776b33e7a2c5d204f8e8d34c1` |
| Milestone at the base | `milestone/v0.4-u-w2-3-workflow-cli` |
| Contract | `agentic-os-v0.4-u-w3-runtime-recovery-contract.md` |
| Architecture commit | `docs(v0.4): freeze U-W3 runtime recovery architecture` — exactly paths 20–21 |
| Implementation commit | `feat(v0.4): add workflow retry, checkpoints, resume, and compensation` — exactly paths 1–19 |
| PR title | `feat(v0.4): U-W3 workflow runtime recovery` |
| Tag after merge | `milestone/v0.4-u-w3-runtime-recovery` |

Exactly **two ordered commits** inside the one U-W3 PR, through the U-P2 gate.
No implementation path is staged before the documentation commit exists (the
D-v0.4.50 landing model, applied a fourth time).

Landing: PR, the four required checks (`workflow-integrity`,
`tests-python-3.12`, `tests-python-3.14`, `distribution-smoke-python-3.12`)
green on the exact pushed head, branch up to date, merge commit only, no
auto-merge, conversation resolution required, empty bypass list. The tag follows
the merge, never precedes it.

**Wave 0 stages nothing, commits nothing, and pushes nothing.** It writes
exactly the two paths 20–21.

---

## 20. Known limitations (declared, not discovered later)

1. **A WorkSpec cannot declare compensation.** `beast.work-spec/v1` has no
   `compensation` property, so compensability is only ever *reported* by the
   executing side. A producer that never reports `compensation.state` gets no
   compensation, however compensable the work was.
2. **No partial compensation.** The protocol's `compensation.state` enum has no
   `partial` member; partial undo must be reported `failed`. AOS cannot detect a
   producer that reports `applied` for partial work.
3. **No compensation retry.** A failed compensation is terminal `failed`.
4. **Staleness is the producer's judgment.** AOS restores from any earlier
   attempt's checkpoint and has no clock with which to judge recency (§14 row 9).
5. **A v1 workflow needs an explicit adoption, and an already-dispatched one
   cannot get it.** Until an operator runs `workflow adopt-policy`, a landed v1
   workflow cannot retry, checkpoint, restore or compensate. This is deliberate;
   a silent upgrade would rewrite what the workflow was decided under. The
   stronger consequence of §5.2.1: adoption is available **only** to a
   pre-dispatch v1 workflow. A v1 workflow that has already consumed an attempt
   — anything in `scheduled`, `running`, `waiting_input`, `waiting_approval` or
   `paused` — has no authoritative attempt history for policy v2 to reason from,
   so it refuses `policy_version_not_upgradable` **permanently**: it runs to a
   terminal state under policy v1, and further work is admitted as a new
   WorkSpec with a new digest and a new identity. A v1 workflow with an
   outstanding but unaccepted dispatch is recoverable — `revoke-dispatch`, then
   adopt, then re-dispatch under v2. Synthesizing the missing attempt history
   would be exactly the fabrication §14 forbids, so the declared limitation is
   the honest answer, not a gap to be closed later.
6. **The budget divergence is declared, not repaired** (§6.4). A WorkSpec with
   no `retry` block enqueued into a runtime row that defaulted to 3 can strand a
   workflow in `running` with no honest terminal.
7. **Runtime-internal retry stays invisible.** AOS sees requeues and lease
   expiries only as silence — U-W2 §22's limitation, inherited.
8. **Post-dispatch cancellation stays dormant**, and revocation before observed
   acceptance stays advisory — U-W2 §22, inherited verbatim. `retrying →
   cancelled` is a *local* cancellation and is not an exception to this.
9. **`waiting_input` and `paused` remain unreachable** (question 5). U-W2 §22
   established that of the nine receipt kinds, the live runtime can source
   `accepted`, `started`, `waiting_approval`, `resumed` and `failed`, and
   `rejected` comes from adapter-side validation; `waiting_input`, `paused` and
   `cancelled` have no runtime fact producer. **U-W3 makes them no more
   reachable and designs no resume from them.** The `* → retrying` edges are
   frozen for all four wait/execute states so the matrix is total and no future
   producer needs a new policy version — but only the reachable ones are
   exercised, and §18 asserts the unreachable rows are refusals-by-absence, not
   dead code claiming to work. Making them reachable is a **runtime** change, not
   a U-W3 change.
10. **No liveness detection.** A workflow stuck in `retrying`, `compensating` or
    `scheduled` is found by a human reading `aos workflow list`; U-W4 owns
    monitoring.
11. **Checkpoint payloads are opaque and unencrypted at rest.** AOS holds no key
    and does not encrypt `aos.db`. The secret-scan refusal (§8.2) is a
    prophylactic, not a cryptographic guarantee; whole-database protection is the
    operator's (`backup`/filesystem) concern.
12. **The `aos.workflow-snapshot/v1` schema string does not advance** despite
    gaining members (§12.3). Justified there; a future exchange of snapshots
    across a boundary would require a `/v2`.
13. **The README's pre-existing stale global schema-version paragraph is not
    repaired** — D-v0.4.102's declared limitation, carried unchanged.

---

## 21. Replan triggers

Any of the following, discovered in any U-W3 wave, is
`FAIL — GOVERNED REPLAN REQUIRED` rather than a judgment call:

1. A twenty-second repository path is required.
2. Any protocol schema under `protocols/**`, `agentic_os/protocols.py`, or the
   attempt ceiling of 10 must change.
3. `agentic_os/governance.py` must be modified for a functional reason (which
   would also fire §1.4's retouch obligation).
4. A `beast.interrupt/v1` document must be read, or approval revocation,
   semantic interrupts, loop-health monitoring, autonomous cancellation, U-E6
   replay or U-X2 capsule surface is required.
5. Any change is required in `/home/daksh/Projects/AICompany`, or U-W2.R turns
   out to be a prerequisite rather than an optional accelerator.
6. `partial` or `unknown` must drive a transition (§5.3.3), or a compensation
   retry, a partial-compensation record, or a compensation checkpoint is
   required (§10.7).
7. A fifteenth state, a fourth reserved-edge activation, or a transition-policy
   version 3 is required.
8. `workflow_facts` or `workflow_receipts` must be rebuilt or gain a member
   (§11.1), or a third new table is required.
9. A second `workflow_store.submit(` call site, a `while` loop, a sleep, or any
   automatic re-issue appears anywhere in the unit.
10. The C26 exemption must cover an **eighth** function — that is, a function
    outside the seven of §13.5 requires one of the two narrowly exempted tokens
    `checkpoint` or `compensat` — or `retry`/`resume`/`interrupt` must appear in
    the CLI region. Nothing smaller fires this trigger: the seven-function set is
    the frozen exemption, not a floor to be grown one function at a time.
11. A fifth CLI leaf, a nested group, or a new `power` kind or mode is required.
12. Fresh-versus-migrated **byte-identity** cannot be demonstrated for the two
    new tables, `workflow_receipts` or `workflow_facts`; or fresh-versus-migrated
    **structural equivalence** across all seven facets of §11.5 cannot be
    demonstrated for the four rebuilt tables; or a landed row hash or event
    digest does not survive the 6→7 rebuild.
13. Any repair, re-seal, re-stamp, `--force` or `--repair` path is proposed, or
    any automatic recovery would fabricate authority or evidence.
14. A twelfth existing test file must be edited, or `tests/fixtures/**` must
    change.
15. Any provisional delivery identity in §19 proves incompatible with repository
    evidence.

---

## 22. Governed audit corrections (A1 … A29)

The corrections below were found by the hard audit that preceded the
implementation wave and by the adversarial verification that followed it,
reproduced against the repository, and applied. A1 … A22 came from the
architecture audit; A23 … A26 from implementing it; A27 … A29 from attacking
the result. Each is
BOUNDED: it changes only this contract and `DECISIONS.md`, adds no repository
path, no twelfth existing test file, no state, no policy version, no table, no
CLI leaf and no protocol change. Where a correction supersedes an earlier row
of this contract, the earlier row stays in place as the frozen record of what
was believed, and the row here is authoritative. Recorded in D-v0.4.116.

### A1 — the sealed snapshot member set is POLICY-VERSION CONDITIONAL (supersedes §11.4 and §12.3)

§12.3 justified keeping `aos.workflow-snapshot/v1` at `/v1` on the grounds
that the snapshot "never leaves the process that built it". That is true and it
is not sufficient. The snapshot record's DIGEST is persisted — it is
`workflows.content_sha256` — and `workflow_store._divergent_fields` compares it
against the rebuilt snapshot's digest on **every command** and inside `verify`.
`_seal` digests the whole body, so adding members unconditionally would change
the digest of every workflow, including every workflow admitted, sealed and
stored before U-W3 existed. Each of those would refuse `snapshot_divergence` on
its next command and read as tampered — while §11.5 forbids the migration to
re-stamp it and §14.2 forbids `verify` to repair it. That is §21 trigger 12,
reached by a documentation decision rather than by a schema one.

**Frozen: the member set is versioned exactly as the transition matrix is.**
`_V1_SNAPSHOT_KEYS` is retained verbatim; `_V2_SNAPSHOT_KEYS` is that tuple
plus §11.4's eight members; `_verify_snapshot` selects by the snapshot's own
`policy_version`, and `_seal_snapshot` PROJECTS the working body onto that
version's members before measuring and sealing. A policy-v1 workflow therefore
seals over exactly U-W2's members forever and its stored digest keeps matching;
`adopt_policy_version` — which consumes a revision and rewrites the row through
the C14 compare-and-swap — is the one legitimate re-seal boundary. `decide` and
`fold` work on a body carrying every member so the handlers stay total, and the
v1 defaults are the honest zero, never an inference.

### A2 — the policy-v2 dispatch gates widen to `retrying` in the REDUCER, not only in the DDL (extends §5.3.6, §11.2)

§11.2 widened the storage CHECK to `state IN ('validated','retrying')` and
§14 row 3 offers `revoke-dispatch` as a recovery, but no section said the
reducer's three matching state gates widen too. Left unstated, a retrying
workflow with an outstanding reservation could neither revoke it
(`illegal_transition`), nor receive a `rejected` receipt
(`receipt_out_of_order`), nor re-dispatch (`dispatch_already_pending`) — and
`_verify_snapshot`'s own cross-field check would have refused the reservation
being made at all. Its remaining budgeted attempts would be unreachable, which
is precisely the harm §6.2 says the reserve-at-acceptance design exists to
prevent.

**Frozen: under policy v2, `request_dispatch`, `revoke_dispatch`, a `rejected`
receipt and `_verify_snapshot`'s `dispatch_intent_id` cross-field check all
read `state ∈ {validated, retrying}`.** Under policy v1 all four keep reading
`{validated}` verbatim. No new state, no new code path, no new refusal code.

### A3 — `_EVENT_PAYLOAD_REQUIRED` gains a VERSION axis (supersedes §5.5's mechanism sentence)

§5.5 requires `dispatch_accepted`'s required-member set to be policy-version
conditional and then names `_EVENT_PAYLOAD_OPTIONAL` as the mechanism. Those
two are incompatible: putting `attempt_no` in the optional table would let
`verify_history` CERTIFY a policy-v2 acceptance with no ordinal, which `fold`
would then fold to `attempts_used = 0` beside a bound `runtime_task_uuid` —
reproducing, inside policy v2 and with no adoption gate to catch it, exactly
the state §5.2.1 exists to refuse.

**Frozen: `_EVENT_PAYLOAD_REQUIRED` and `_EVENT_PAYLOAD_OPTIONAL` become
`(minimum policy version, event, rules)` triples** — the `_POLICY_MATRICES`
shape — and `_verify_event_shape` selects rows by the event's own recorded
`policy_version`. `attempt_no` is REQUIRED on a v2 `dispatch_accepted` and
absent-and-legal on a v1 one. The contradicting clause in §5.5 is superseded.

### A4 — `RECEIPT_EVENTS` is unchanged, and the `failed` mapping is state-conditional (clarifies §5.5, §1.3)

§5.5 gives `compensation_failed` the driver "`cmp:failed` / `rcp:failed` from
`compensating`", which makes a `failed` receipt map to two events. **Frozen:
`RECEIPT_EVENTS` and the nine receipt kinds are BYTE-UNCHANGED; the second
mapping is a state-conditional branch inside the receipt handler, not a second
table entry.** A `failed` receipt arriving in `compensating` reports that the
runtime task the compensating attempt was bound to failed, so it ends the undo
— which is why it carries no `compensation_state`. That path is reachable and
is exercised: the compensating attempt keeps the binding of the execution task
that was still live when compensation was entered.

### A5 — the WorkSpec's own declared `runtime_task_uuid` binds ATTEMPT 1 ONLY (extends §6.5)

`beast.work-spec/v1` carries an optional `runtime_task_uuid` property, and the
landed reducer requires a pre-declared value to match at acceptance. Combined
with §6.5's one-task-one-attempt fence and `retry.max_attempts > 1`, that made
retry structurally impossible: attempt 2's acceptance would refuse
`runtime_uuid_mismatch` whether it carried the declared uuid (already bound to
attempt 1) or any other value.

**Frozen: under policy v2 the artifact's declared `runtime_task_uuid` binds the
acceptance of attempt 1 and is NOT consulted for attempts ≥ 2.** A retry is a
new runtime task by construction (§7.2), so a declaration naming one task could
never be satisfied twice. Policy-v1 behavior is unchanged: the declaration
binds every acceptance, verbatim.

### A6 — `attempt_budget_exhausted` is a STRUCTURAL BACKSTOP (supersedes §14 row 5's disjunct and §18 W9's third clause)

Every path into `retrying` requires `attempt_no < budget` (§5.3.3), and §14 row
18 states that a budget-exhausting failure goes terminal `failed`, never
`retrying`. So `attempts_used >= budget` is unreachable in any non-terminal
state a history can produce, and a terminal row refuses `workflow_terminal`
first. **Frozen: the code is retained as a total guard against a spliced or
hostile snapshot and is asserted as a refusal-by-construction — driven in
process against a directly-constructed snapshot — exactly as §8.4 asserts its
unreachable states.** It is not deleted: a backstop that is dead by
construction is the right shape. The claim that it fires in normal operation is
withdrawn.

### A7 — `MAX_CHECKPOINTS_PER_WORKFLOW` is a derived backstop (supersedes §18 W15's "81st per workflow")

`attempt_no ∈ 1..10` and `checkpoint_seq ∈ 1..8` make 80 the maximum
representable checkpoint count for one workflow, so the per-workflow bound can
be REACHED but never EXCEEDED: the per-attempt bound always fires first.
**Frozen: the bound is a derived backstop, asserted in process against a
directly-constructed snapshot rather than through a history no ledger can
produce.**

### A8 — `checkpoint_limit_exceeded` fires when the bound WOULD BE EXCEEDED (corrects §5.4)

§5.4 says "is reached", which would refuse the eighth checkpoint; §18 W15 says
the ninth refuses. **Frozen: the ninth per attempt refuses.** The gate reads
the LEDGER's counters, not the submitted ordinal, so it is reachable at all —
a record naming `checkpoint_seq: 9` would otherwise fail the 1..8 shape gate
first and report the wrong code.

### A9 — `checkpoint_malformed` also covers a non-next `checkpoint_seq` (extends §5.4)

§8.2 requires `checkpoint_seq` to be monotone from 1 within an attempt and no
code was named for a record that violates it. **Frozen: a `checkpoint_seq` that
is not `last_checkpoint_seq + 1` refuses `checkpoint_malformed`** — a closed
judgment about a closed field, minting no fifteenth code.

### A10 — `record_compensation`'s refusal surface is made TOTAL (extends §10.8)

§10.3 gives `record_result` an exhaustive `outcome` × `compensation.state`
table; §10.8 gave `record_compensation` none, leaving an absent block,
`not_required`, and `partial`/`unknown` outcomes unnamed. **Frozen table** —
every cell names exactly one code, and `attempt`, uuid and phase gates run
before it:

| `outcome` | `compensation.state` | Result |
| --- | --- | --- |
| `success` / `fail` | `applied` | `compensated` (evidence gate applies) |
| `success` / `fail` | `failed` | terminal `failed` |
| `success` / `fail` | `pending` | `compensation_state_inconsistent` |
| `success` / `fail` | `not_required` | `compensation_state_inconsistent` |
| `success` / `fail` | block absent | `compensation_state_inconsistent` |
| `partial` / `unknown` | any | `result_outcome_inconclusive` |

### A11 — `compensation_already_concluded` precedence, stated honestly (supersedes §14 row 17)

Both conclusions are terminal, and §5.3.5 forbids a second terminal carve-out,
so a later `record_compensation` refuses `workflow_terminal` — not
`compensation_already_concluded`. **Frozen: §14 row 17's second and third
branches read `workflow_terminal`.** The code stays in the vocabulary and stays
implemented as a total in-handler guard, unreachable while both conclusions are
terminal, exactly as §5.2.1's A2/A3 are unreachable.

### A12 — a `retrying` cancellation with an outstanding reservation DOES emit a cancel intent (corrects §11.2's justification and §20 item 8)

The `cancel_intent_id` CHECK is correctly left unchanged, but not for the
reason §11.2 gives. The local-cancel branch emits a `cancel` intent and a
`dispatch_revoked` event whenever a dispatch pointer is outstanding, and under
policy v2 a `retrying` workflow may hold one. **Frozen: the CHECK is unchanged
because the local branch sets `cancel_intent_id` to NULL in the same decision,
not because no intent is emitted.** A `retrying` cancel with an outstanding
reservation emits exactly one `cancel` intent, exactly as a `validated` one
does, and `export-intents` will list it.

### A13 — the five new `WorkflowRecord` members: source and damaged-workflow value (extends §13.2, §13.3)

§13.2's "automatically" is withdrawn: none of the five is a `workflows` column.
**Frozen: all five are read from the REBUILT snapshot that the same call
already produced to decide the integrity verdict** — never by a direct read of
`workflow_attempts` or `workflow_checkpoints`, because reporting a projection
of a ledger the same command has just declared divergent is what U-W2.2 §18
forbids. **When `integrity != "ok"`, and for every policy-v1 workflow, all five
are `None`** — "unknown", never a fabricated zero, and never an attempt history
policy v1 did not keep.

### A14 — §5.2.1 A1's third conjunct is a FOLDED judgment (clarifies §5.2.1)

A1's "no `workflow_attempts` row exists" is not a stored-row read: a row exists
only where an `accepted` receipt set `attempts_used ≥ 1`, so the conjunct is
equivalent to `attempt_no is null` in the folded snapshot. **Frozen: A1 is
decided from the folded snapshot alone, exactly as A3 is, and `ShellFacts`
gains no fifth member.**

### A15 — §8.4's state criterion (corrects §8.4)

`scheduled` is AFTER acceptance and does have an open attempt and a bound
runtime task, so "before acceptance nothing is executing" does not cover it.
**Frozen criterion: `record_checkpoint` is legal exactly where the runtime has
reported that execution BEGAN and the attempt is still open** — `running`,
`waiting_input`, `waiting_approval`, `paused`. `scheduled` is excluded because
the task has not started; the enumerated four are unchanged.

### A16 — the state literal `retrying` may never appear in the CLI region (extends §13.5)

`retrying` contains `retry`, which §13.5 keeps banned across the entire region
and §21 trigger 10 fires on. **Frozen: no state literal appears in the workflow
CLI region at all.** State names reach the CLI only through
`_workflow_state_choices` and `WorkflowRecord`, both of which read the engine's
vocabulary. §18 row W28 asserts the absence of the literal.

### A17 — §13.5's non-exempt enumeration was short by two (corrects §13.5)

The parenthetical listing "every helper" omits `_compare_workflow_intent_file`
and `_write_workflow_intent_file`. **Both are added; both retain BOTH token
prohibitions in full.** W28's operative rule — every function outside the seven
is proved free of both — was already total and is unaffected.

### A18 — the `export-intents` two-member comment (extends §13.5)

`cmd_workflow_export_intents` carries a comment naming a "closed two-member
vocabulary" and the regex `^(dispatch|cancel)-…`, which U-W3 makes false. The
function is NOT one of the seven exempt, so it may not name `compensate`.
**Frozen: the comment is rewritten WITHOUT either narrowly exempted token** —
"a closed vocabulary of intent kinds", with the kind list left to the engine.
The exemption set stays at seven and no eighth function is created.

### A19 — §1.3's C-row range (corrects §1.3)

§1.3 lists "C12–C25" as not superseded while §1.2 row S14 and §13.5 narrow
C22. **Frozen: the range reads C12–C20, C23–C25.** §13.5's disposition table is
authoritative and was already correct.

### A20 — §18 rows W2 and W23 use HAND-TRANSCRIBED frozen sources, never `git show` (supersedes their "Independent expected-value source" column)

`.github/workflows/ci.yml` checks out with `actions/checkout` and no
`fetch-depth`, i.e. a depth-1 shallow clone, so `fef0c2b` is not present as an
object in any of the four required checks; no landed test invokes `git` at all,
and `ci.yml` is untouchable (§17.7). As specified, W2 and W23 would fail every
required check with a tooling error.

**Frozen: both rows use the C1 idiom instead** — the v1 state tuple and the v1
matrix cells hand-transcribed into `tests/test_v04_workflow_recovery.py`, and
the frozen v6 DDL texts pinned by a hand-transcribed sha256 literal of their
canonical concatenation (the `WORK_SPEC_SCHEMA_SHA256` precedent already in
`tests/test_v04_workflow_cli.py`). `git show fef0c2b:…` remains the auditor's
derivation of those literals; it is not a runtime dependency of any test.

### A21 — §18 row W29's submit-call-site assertion (corrects W29)

Live counts are 1 in the CLI region, 0 in `workflow_store.py`, 0 in
`workflow_engine.py`. **Frozen: exactly one `workflow_store.submit(` call site
ACROSS the three, distributed 1 / 0 / 0.** The distributive "one in each"
reading is unimplementable and is withdrawn.

### A22 — §17.3's forced-edit licences, completed (supersedes path 9's and path 16's "Exact edit" cells and extends path 10's enumeration)

The eleven forced files are correct and no twelfth is forced. Three of their
licences were measured against count pins only and missed landed token-scan
guards and version-named tests that fail BY CONSTRUCTION. The closed licences
are completed here; nothing outside them may be edited, no assertion is
deleted, no `subTest` dropped and no bound loosened.

**Path 9 (`tests/test_v04_workflow_engine.py`) — the licensed classes are
exactly F1–F9.** The phrase "the `_PUBLIC` name list" is withdrawn: no such
constant exists in that file.

| # | Licensed edit | Forced by |
| --- | --- | --- |
| F1 | the vocabulary counts and tuples (13→14 states, 9→13 commands, 17→24 events, 43→57 reasons, 2→3 intent kinds) | S1, S3, S4, S5, S6 |
| F2 | the hand-transcribed matrix split into a frozen v1 expectation (`V1_S`, `V1_CONTRACT_CELLS`) plus a v2 one, and the cell census 25/3/141 → 35/0/161 | S2 |
| F3 | `TRANSITION_POLICY_VERSION` 1→2 and `SUPPORTED_POLICY_VERSIONS` `(1,)`→`(1, 2)`, including the test's own name | S2 |
| F4 | the `AdmissionFacts` → `ShellFacts` rename and its frozen-field list, now four | S7 |
| F5 | the snapshot and dispatch-intent shape expectations (the eight §11.4 members under A1's versioned rule; the intent's `attempt_no`/`attempt_budget` and its `/v2` schema string) | S2, A1 |
| F6 | the `Journey`/`_drive` harness extended to the new drivers and to `retrying`/`compensating`, and the driven-triple count 26 → 38 | S2 |
| F7 | the result-attempt expectations, where a reported `attempt` must now EQUAL the open one | S8 |
| F8 | the unsupported-policy-version fixture, 2 → 3 | S2 |
| F10 | **`ResultTests::test_fail_maps_to_failed`** — its fixture carried `compensation={"state": "pending"}` while scripting `outcome="fail", retryable=True` and asserting terminal `failed`. Under §10.3 compensation OUTRANKS retry unconditionally, so that envelope now reaches `compensating` and the test's own premise is falsified. The field is dropped from the fixture; every assertion survives, including `assertNotIn("compensation", …)`, which still carries real content | §10.3 |
| F9 | **`test_no_compensation_execution_surface` and `test_no_monitor_interrupt_or_durable_engine_surface`** — both ban tokens U-W3's engine must carry. Narrowed, not deleted: the `compensat` guard becomes an EXACT enumeration of the one command and three events that may carry it and still proves no RECEIPT KIND does; the `checkpoint` token leaves the second list and every other token in it stays. The landed `retry`-in-vocabulary guard is re-asserted UNCHANGED and still passes — no U-W3 command or event carries that token | S3, S4 |

**Path 10 (`tests/test_v04_workflow_store.py`) — E1–E11 stand, and E12–E14 are
added.**

| # | Licensed edit | Forced by |
| --- | --- | --- |
| E12 | **`test_no_later_unit_surface_exists`** — narrowed: `checkpoint`, `compensate` and `attempts` leave the ban list because path 2 obligates the store to carry all three. Every private-runtime and future-unit token stays banned, and `backoff`, `postgres`, `psycopg`, `monitor` and `interrupt` are ADDED, so the guard is strictly wider than it was on the axis it exists to protect | §17.1 path 2 |
| E13 | the `finalize_sites` count 4 → 6, and the `test_transition_reserved_is_unreachable_through_the_store` premise, which policy v2 falsifies — re-scoped to assert that `compensating` is entered only from `running` and only by an envelope, plus that policy v1's reserved cell is retained verbatim so `transition_reserved` stays reachable | §11.3, S2 |
| E14 | the two 5→6-specific migration tests, which must now assert the SIX v6 tables the frozen copy builds rather than the live eight, and the unsupported-policy-version fixture 2 → 3 | S12, S13, S2 |
| E15 | the **`store_unavailable` raise-site census** — U-W2.2 addendum B1 §B1.5 froze ten sites classified `(4 sqlite, 2 other-exception, 4 non-exception)`. The two new tables need exactly three more, each a faithful MIRROR of a landed site: `_close_attempt`'s unreadable-row mapping and its rowcount guard mirror `_close_intent`'s two, and `_checkpoint_dedupe`'s stored-row-with-no-naming-event guard mirrors `_receipt_dedupe`'s. A fourth follows from §22 A29.3: `_open_attempt` narrowly maps an `IntegrityError` to `runtime_uuid_mismatch`, so like `_insert_workflow` it needs a residual `sqlite3.Error` arm for every OTHER storage error. The census stays CLOSED and stays exact — fourteen sites, `(5, 3, 6)` — and it is a widening of the same discipline, not a relaxation of it | §17.1 path 2, §22 A29.3 |

**Path 16 (`tests/test_v03_memory_graph.py`)** — the licence additionally
covers `test_no_version_seven_transition_exists`, whose name and `> 6` bound
are both falsified by a shipped 6→7 step; it is renamed and re-scoped to `> 7`,
the same re-scoping U-W2.2 applied to it.

**Path 11 (`tests/test_v04_workflow_cli.py`) additionally covers C21.** Row
11's cell lists C1, C2, C3, C5, C10, C11, C22 and C26 and omits C21 — but C1's
licensed extension of the shared `CONTRACT_LEAVES` constant mechanically forces
it: `ReadmeTests` iterates that constant against the U-W2 README section, which
documents thirteen leaves and not seventeen. The licensed edit is to SCOPE the
two landed assertions to the thirteen U-W2 leaves and to assert the U-W3
section's placement; C21's obligation itself is unchanged and is discharged for
the four new leaves by the fully-licensed
`tests/test_v04_workflow_recovery.py::ReadmeTests`, which parses and RUNS the
new section's fenced blocks. §22 A19 already removed C21 from §1.3's
not-superseded range, so nothing here contradicts §1.3.

**Path 17 (`tests/test_v04_agent_passports.py`)** and **path 10** additionally
cover the `…_five_steps…` test names, which a sixth step falsifies.

### A23 — §14 row 19's "mutating commands refuse" is scoped to the SNAPSHOT, not to a row hash (corrects §14 row 19)

Row 19 says a planted `workflow_attempts` row hash makes `verify` report the
pair AND makes mutating commands refuse. Only the first half is true, and the
second half would require widening a landed boundary U-W3 does not own: the
per-command gate is `_load_snapshot`'s snapshot-and-history comparison, and row
hashes are deliberately outside it — that is exactly what U-W2.2 addendum B1
§B1.14's integrity-scope sentence tells every operator, in the line `show` and
`list` print verbatim: "row hashes and stored receipt and fact bodies are
checked only by `python aos.py workflow verify`".

**Frozen: a planted ROW HASH alone is a `verify`-scope finding** — reported in
`divergent_rows`, never repaired, and stable across repeated reports. A broken
SNAPSHOT or history still refuses every mutating command with
`snapshot_divergence`, unchanged. U-W3 neither widens nor narrows the landed
scope, and §18 row W19 asserts both halves separately.

### A24 — ONE rule for every optional corroborating uuid (supersedes §5.4's and §6.2's failed-receipt binding)

§6.2 and §5.4 made `runtime_task_uuid` MANDATORY on a `failed` receipt under
policy v2, refusing `receipt_unbound` when absent. That is a behavioral break
the contract did not intend and §1.3 explicitly disclaims: `runtime_task_uuid`
is not a required member of a `failed` receipt in U-W2 §13.2's frozen record
shape, `workflow_receipts`' CHECK admits NULL for that kind, and the landed
hostile-path tests emit shape-legal `failed` receipts without one. An adapter
that has been correct since U-W2 would start refusing the moment its workflow
adopted policy v2, and its open attempt would never close.

**Frozen: the rule is the same one §5.3.3 and §10.8 already state for a result
envelope, and it is now the ONLY rule in the unit.** A **present**
`runtime_task_uuid` must equal the recorded binding of the attempt the document
concerns; a **present contradiction** refuses `runtime_uuid_mismatch` and
records nothing; an **absent** value refuses nothing and is never replaced by a
default, a lookup or an inference.

The fence loses nothing, because the receipt never needed to name its attempt:
**at most one attempt of a workflow is open at a time (§6.3)**, so which
attempt a `failed` receipt closes is decided by the LEDGER, not by the
document. A uuid that agreed would have added no information a hostile writer
could not also have copied from the intent file it was given. What the check
buys is the contradiction — and a contradiction is never silently dropped.

`receipt_unbound` keeps its landed meaning and its landed emissions (a receipt
naming no outstanding intent of this workflow, and a policy-v2 acceptance with
no recorded reservation to number itself from, §5.5 item 4); it is no longer
emitted for an absent uuid.

### A25 — the U-W2 README paragraph's counts go stale and are NOT repaired (extends §20)

`README.md`'s U-W2 section opens "thirteen states, a frozen 13×13 transition
matrix, nine commands, seventeen events, forty-three closed refusal reasons".
Policy v2 falsifies all five as statements about the shipped engine. §17.1 path
7 licenses "exactly one new U-W3 unit section … no other region", and §2.2
excludes unrelated documentation cleanup, so U-W3 does NOT edit that paragraph
— the same disposition D-v0.4.102 gave the stale global schema-version
paragraph, and §20 item 13 already carries.

**Frozen: the U-W2 paragraph is left byte-unchanged as the record of what U-W2
shipped, and the U-W3 section immediately below it states the superseding
numbers explicitly and says which they supersede.** A reader reaches the
correction in the next paragraph; no landed region is edited; and the
obligation to fold the two together transfers to the first future unit that
already rewrites the U-W2 section for a functional reason — the §1.4 retouch
discipline, applied a second time.

### A26 — §17.8's focused invocation form is wrong for SEVEN of the twelve modules, and has been since before U-W3 (corrects §17.8)

§17.8 lists twelve focused gates as `python3 -m unittest -v tests.<module>`.
That form fails with a `ModuleNotFoundError` for **seven** of them, because
each imports a sibling under `tests/` without putting `tests/` on `sys.path`.
Measured, not estimated — the missing module is named for each:

| Focused module | Missing import |
| --- | --- |
| `tests.test_v02_migrations` | `fixtures` |
| `tests.test_v03_memory_claims` | `fixtures` |
| `tests.test_v03_memory_graph` | `fixtures` |
| `tests.test_v04_agent_passports` | `fixtures` |
| `tests.test_v04_routing_handoffs` | `fixtures` |
| `tests.test_v04_agent_catalog` | `test_v04_agent_passports` |
| `tests.test_v02_power_modes` | `weekend_harness` |

Verified at `fef0c2b`: every one of those import lines is byte-identical
there, so the form never worked for those seven and U-W3 did not break it.
`tests/test_v04_workflow_store.py` works because it inserts its own directory
(line 31); CI is unaffected because it runs
`python3 -m unittest discover -s tests`, which puts `tests/` on the path.

**Frozen: the focused gate for any of those seven is
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p
<module>.py`.** The other five keep the direct form. U-W3 does NOT add a
`sys.path` insert to the seven: that edit is in none of their licensed edit
classes (§17.3 as completed by A22), it is unrelated cleanup under §2.2, and
the whole-suite gate CI actually runs already covers them.

### A27 — six defects the adversarial verification found in the SHIPPED code, and their repairs

The verification round attacked the implementation rather than the architecture.
Six findings were reproduced against the repository and repaired. The first is
the serious one.

**A27.1 — a history `verify_history` CERTIFIES could crash `fold`.** A3's
version axis keys each required-payload row at a *minimum* policy version, so a
spliced `checkpoint_recorded` or `checkpoint_restored` event stamped
`policy_version: 1` skipped its own required-payload row, was certified, and
then raised a raw `KeyError` out of `fold` — escaping `verify`, `read_workflow`
and every mutating command, because the store catches only `WorkflowRefusal`.
That breaks §5.5 and §11.4 ("a `KeyError` out of `fold` is not a report"),
§14.2 (integrity is REPORTED), §15 rule 1, and the landed, unsuperseded engine
invariant that a certified history never crashes `fold`.

**Frozen: an event whose NAME did not exist at its own stamped policy version
is `history_corrupt`.** `_EVENT_MIN_POLICY_VERSION` pins U-W3's seven events at
version 2, `_verify_event_shape` refuses before folding, and the version axis
now has both halves — which members a version requires, and which names a
version has at all. Reproduced before the fix and re-run after it.

**A27.2 — `_verify_snapshot`'s v1 gates were not version-conditional.** A2
froze that under policy v1 all four gates keep reading `{validated}` verbatim;
the shipped `dispatch_intent_id` cross-field check read
`{validated, retrying}` unconditionally, and the state-membership check judged
a v1 snapshot against the fourteen-state tuple. **Frozen: both now select by
the snapshot's own version** — `_DISPATCHABLE_STATES[version]` and
`_policy_for(version)`'s own state tuple — so a policy-v1 snapshot can neither
claim the fourteenth state nor hold a dispatch pointer in it.

**A27.3 — the seven-function exemption over-permits by two, and its test was
one-way.** Measured against the shipped CLI, exactly FIVE functions carry a
narrowly exempted token: `cmd_workflow_checkpoint`, `cmd_workflow_compensate`,
`_build_workflow_parser`, `cmd_workflow_dispatch`, `cmd_workflow_show`.
`cmd_workflow_restore` needs neither — the restore fact's `checkpoint_id` is
parsed by the engine, not named in the handler — and
`cmd_workflow_adopt_policy` needs neither, because its help string lives in the
parser builder. §13.5's mechanical-necessity cells for those two are therefore
false about the shipped code, and W28's "exact set" was asserted in one
direction only, so drift by omission went undetected.

**Frozen: the seven-name list stays the CEILING an eighth function would
breach (§21 trigger 10 is unchanged), and the MEASURED five-function carrier
set is asserted exactly, in both directions.** That is strictly stronger than
what §13.5 required: the exemption can now neither spread nor drift.

**A27.4 — §10.3's `partial`/`unknown` row.** The conclusion-shape gate ran
before the outcome gate, so an envelope with `outcome: "partial"` AND
`compensation.state: "applied"` refused `compensation_state_inconsistent`
where §10.3's table says `result_outcome_inconclusive` ("`partial`/`unknown` |
any | inconclusive"). Nothing was recorded either way; only the code selection
deviated. **Frozen: the outcome gate runs first**, so §10.3's table selects.

**A27.5 — checkpoint identity was keyed on `checkpoint_id` alone.** §7.1 fixes
ledger identity as `(workflow_id, checkpoint_id)` and the DDL's UNIQUE agrees,
but the store's dedupe and resolution selected on the id across ALL workflows,
so a producer reusing an id under a different workflow refused
`checkpoint_conflict` where the contract admits a new checkpoint. **Frozen:
both statements bind both halves of the identity.**

**A27.6 — declared, not repaired.** Three mappings the contract does not name,
each judged correct as shipped and recorded here rather than changed: the three
new verbs on a **policy-v1** workflow refuse `illegal_transition` at
`/policy_version` (the verb is not legal under that version, which is what that
code means); `attempt_budget_exhausted` has a second, dead-by-construction
emission at ACCEPTANCE as well as at request, guarding a spliced snapshot
exactly as A6 describes; and `WORKFLOW_COMPENSATION_STATES` joins
`_CLOSED_DIAGNOSTIC_VALUES` alongside the attempt states §15 rule 4 names —
closed enum members only, no behavior change.

### A28 — the forced version-literal edits were incomplete in FOUR files, and one of them shipped a silently-vacuous assertion (completes §17.3 rows 13, 16–19)

The eight version-literal licences of §17.3 name the literal each file carries
in the singular — "the one `db.SCHEMA_VERSION` literal", "the two `"6"`
literals". Four files carry SIBLING occurrences of the same fact that those
cells do not enumerate, and the first pass updated only the named one. Eleven
stale assertions survived, every one of them a real failing test:

| File | Stale fact |
| --- | --- |
| `tests/test_v04_routing_handoffs.py` | a second `db.SCHEMA_VERSION == "6"`; `_version(fresh_db()) == "6"`; two `current_version == 6`; `len(MIGRATIONS) == 5` |
| `tests/test_v04_agent_passports.py` | the migrate-EVENT count, `3`, which a sixth step makes `4` |
| `tests/test_v04_agent_catalog.py` | the second of its own licensed "two `"6"` literals" |
| `tests/test_v03_memory_graph.py` | a second `db.SCHEMA_VERSION == "6"`; the fresh-init stamp `"6"`; the CLI text `"build supports:  6"`; `migrate(target="6")`, whose own comment says "to current" |

**One was worse than stale.** In `test_v04_routing_handoffs.py` the new
`(6, 7, …)` chain row was inserted into an
`assertEqual(report["plan"][-1], {…v6…})` call as a THIRD positional argument
— which `assertEqual(first, second, msg=None)` accepts as the failure MESSAGE.
The comparison target was never updated, so the test passed while asserting
nothing about the new step. A green test that verifies less than it claims is
the exact failure mode §17.3's "no assertion is deleted, no bound is loosened"
exists to prevent, and it is worth recording that the mechanism here was not a
deletion but a well-formed call that quietly stopped comparing.

**Frozen: the licence for these four files covers EVERY occurrence of the
facts their cells name** — the schema version, the derived `LATEST_VERSION`,
the migration-chain rows, the registry length, the migrate-event count, the
migrate target, and the CLI's rendered version text — and the malformed call is
split into two assertions so both chain entries are compared. Nothing is
weakened: every repair replaces a stale value with the true one or restores a
comparison that had stopped happening.

**And the discipline that found it, recorded because the first pass did not
have it:** a per-file "the cell named this literal" edit is not sufficient for
a fact that appears more than once. The check that catches it is a tree-wide
sweep for the FACT — every `"6"`-shaped schema literal, every chain row, every
count — run after the named edits and again after the repair, not a reading of
the diff.

### A29 — four defects the adversarial safety attack found in the shipped code

The attack round built REAL policy-v1 workflows with the `fef0c2b` engine on a
real v6 schema and migrated them forward, then attacked the result with ~25,000
hostile calls. It could not break policy-v1 survival, the attempt ledger's
accounting, the checkpoint bounds, compensation authority, adoption, migration
atomicity, refusal totality or the no-stored-body rule. It found four defects,
three of them in code.

**A29.1 — a fully-rewritten checkpoint row was invisible to `verify` and became
the restore authority.** `checkpoint_recorded` seals the digest of the body it
accepted, which is an INDEPENDENT witness living under the event's own sealed
digest. Nothing consulted it: `_resolve_checkpoint` and `_divergent_rows` both
compared the stored body against the row's OWN `document_sha256` column, so
rewriting body, digest column and row hash together passed every check — and
the forged digest then flowed into `ShellFacts`, into the dispatch intent's
`restore_checkpoint_sha256` (which CROSSES THE TRUST BOUNDARY), into
`record_restore`'s binding gate and into the folded
`restored_checkpoint_sha256`. The sealed history ended up holding two different
digests for one `checkpoint_id` while `verify` reported `ok`.

This is not the landed receipt/fact pattern. For those, the folded snapshot
comes from the EVENT, so a forged row changes no decision; for a checkpoint the
row's digest IS the value fed into live decisions. U-W3 gave a stored row
authority the event history already pins.

**Frozen: a stored checkpoint body is bound to the digest its own
`checkpoint_recorded` event sealed** — in `verify` (reported in
`divergent_rows`), in restore resolution (`checkpoint_ineligible`, so a forged
row can never be restored from) and in the dedupe axis (so a redelivery over
corrupt bytes is a `checkpoint_conflict`, never a `replay` that tells the
producer its checkpoint is safely stored). This is the `_body_divergence`
idiom the two `workflows` bodies already use, applied a third time. A row
agreeing with itself is not an integrity check.

**A29.2 — a policy-v1 event could name the fourteenth state.**
`_verify_snapshot` judges `state` against the snapshot's own version's tuple
(A27.2) and `_event_available` judges the event NAME against its own version
(A27.1), but `_verify_event_shape` still judged `from_state`/`to_state` against
all fourteen. The three disagreed, and the disagreement produced exactly the
§21-trigger-12 harm A1 exists to prevent: a planted v1 event naming `retrying`
folded to a v1 snapshot sitting in `retrying`, every read surface — including
`workflow verify`, which the integrity note calls the total one — reported
`ok`, and every mutating command refused `snapshot_divergence` with no
diagnosis available anywhere. **Frozen: all three axes select by the record's
own policy version.**

**A29.3 — §6.5's fence saw only the LAST attempt's binding.** The reducer
compares against the folded `runtime_task_uuid`, which every acceptance
overwrites, so an `accepted` receipt replaying an OLDER attempt's task passed
the reducer and was caught only by `UNIQUE(workflow_id, runtime_task_uuid)` —
surfacing as `store_unavailable` ("the ledger could not be read or written"),
RAISED rather than returned, and therefore never journalled by
`_journal_workflow_refusal`. A correct-but-buggy adapter replaying an old task
id was told its database was broken, and the refusal left no observability row.

**Frozen: the `_open_attempt` INSERT is the SECOND statement that maps
`sqlite3.IntegrityError` to a workflow refusal**, and it maps to
`runtime_uuid_mismatch` — the same closed code the reducer's own gate uses. The
refusal is returned in a `StoreOutcome` and journalled like every other. §6.5's
description of the UNIQUE index as "the storage backstop" is now literally
true: the reducer catches the current binding, the index catches an older one,
and both report the same thing. Folding every prior uuid into the snapshot
would have been the alternative; it would have added a ninth §11.4 member for
a case the index already decides.

**A29.4 — declared, not repaired: the integrity-scope note under-enumerates.**
Adding `workflow_checkpoints` to `_DOCUMENT_BOUND_TABLES` makes a tampered
checkpoint BODY a `verify`-scope finding, but `_WORKFLOW_INTEGRITY_NOTE` — the
sentence `show` and `list` print verbatim and both `--json` documents carry —
still names only receipt and fact bodies. It under-states its own scope.

It is NOT changed, and the reason is a boundary rather than a preference: the
note is quoted verbatim inside the README's **U-W2** section, which §17.1 path
7 forbids U-W3 to touch, so editing the constant would force an edit outside
the licence — a twenty-second-path problem in miniature. The sentence remains
true in direction (it names `verify` as the total surface); it is incomplete in
enumeration. Declared here and in §20, with the retouch transferring to the
first future unit that already edits that README region — the §1.4 discipline,
applied a third time.
