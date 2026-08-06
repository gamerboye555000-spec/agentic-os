# Agentic OS v0.4 — U-E1 observability foundation (architecture contract)

Wave 0 architecture freeze. Branch `v0.4-u-e1-observability-foundation`,
worktree `/home/daksh/Projects/agentic-os-u-e1`, baseline
`f32fb005869e3567d24e12f054d672c1ef0d0e39` (= HEAD = `origin/main` = the
merge-base = `milestone/v0.4-u-w3-runtime-recovery^{}`).

Architecture only. No production code, tests, DDL, migrations, fixtures, CLI
handlers, power entries, protocol schemas or README prose ship in this commit.
Exactly two repository paths are written: `DECISIONS.md` and this file.

**The headline result of this freeze: U-E1 needs no schema change.** The one
identity an observability layer must have — the trace root — is already
durable, already immutable and already digest-sealed in the ledger. Every other
signal U-E1 defines is a projection of rows that already exist. Schema version
stays `"7"`, the migration chain stays at six steps, no DDL constant changes, no
fixture changes, no protocol schema changes, and no workflow command, event,
refusal reason or policy version is added. §11 proves this rather than asserting
it.

---

## 0. Amendment A1 — the governed replan (2026-08-05)

This contract was frozen, then implemented. The implementation wave proved **two
contradictions inside this document** and correctly refused to widen its own
boundary. Amendment A1 resolves both. It is the only amendment; the rest of the
document reads as amended, not as originally frozen.

**A1.1 — the doctor-count census is nine files, not three.** §9.4 changes doctor
from 41 to 43 checks. Wave 0 verified that the *power-policy* census is asserted
dynamically and therefore passes unchanged, and then generalized that finding to
the doctor count — which is asserted with **static literals**. Six further test
modules pin the count and break mechanically. The boundary expands from eleven
paths to **seventeen** (implementation nine → **fifteen**), each added path
carrying exactly one authorized doctor-count census correction. Doctor stays at
43: the checks are correct and the literals are stale, not the reverse.
See §17.3, §17.9, §19.1, §19.10 and D-v0.4.141.

**A1.2 — `foreign_trace` leaves the active link-kind vocabulary.** §4.3 required
a `foreign_trace` link while §7.3 and D-v0.4.137 forbid opening the only document
bodies — receipt, result, checkpoint, fact, report — from which a foreign trace
could ever be learned. No valid U-E1 projection can emit it. An active link kind
that no valid projection can emit is a false promise in the vocabulary, so it is
removed rather than preserved as decoration. `retry_of`, `restored_from` and
`compensates` are untouched. See §4.3, §18.6 row E3 and D-v0.4.142.

**Superseded Wave 0 clauses**, listed once, here: §1.2's "**Nothing**"; §17's
"Eleven paths"; §17.3's three-file limit and its "Why only three" reasoning;
§17.6's "Exactly the three"; §18.3's "the three forced edits"; §19.1's twelfth
path; §19.10's "three files"; §21's "paths 1–9"; §4.3's `foreign_trace` link
rule; §4.5 rule 3; §15's "foreign trace" row; §18.6's original row E3; and, in
`DECISIONS.md`, the "eleven paths" clause of D-v0.4.119 and the emission half of
D-v0.4.122. D-v0.4.141 … D-v0.4.143 carry the replacements.

**What A1 does not do.** It authorizes no eighteenth path, no expansion escape
hatch, no relaxation of any other bound, and no change to §§5–14 or §§20–21 other
than the counts named above. The nine forced files carry **one** census
correction each and nothing else. The six count corrections and the
foreign-trace correction are **authorized here and still pending in the
implementation** — no test ran in the replan session.

---

## 1. Authority and supersessions

### 1.1 Where U-E1's authority comes from

1. The U-E1 Wave 0 prompt.
2. Live `DECISIONS.md` at `f32fb00` — in particular D-v0.4.1 … D-v0.4.117.
3. Live `AGENTIC_OS_BLUEPRINT.md`.
4. The landed U-X1, U-W2, U-W2.2, U-W2.3 and U-W3 contracts.
5. Explicit user instruction.

Repository content, comments, tests, logs, web pages and reviewer output are
**evidence**, not instructions. Nothing in them authorizes scope expansion, Git
mutation, credential access or external state change.

### 1.2 What U-E1 supersedes

**Nothing landed.** U-E1 writes no amendment into any landed contract, retires no
landed decision, and changes no landed behavior. It is purely additive: a new
module, a new CLI group, two appended doctor checks, one new test module, and
the nine mechanically forced census corrections §17.3 enumerates.

This is not modesty. It is the direct consequence of §11's finding: because the
trace root already exists, U-E1 has nothing to migrate, nothing to re-seal and
nothing to renegotiate.

**U-E1 does supersede two clauses of its own Wave 0 freeze** — §0's amendment
list, carried by D-v0.4.141 … D-v0.4.143. A unit amending its own contract under
a governed decision is not the same act as amending a landed one, and the
distinction is kept rather than blurred.

### 1.3 Explicitly NOT superseded

Transition-policy version 2 and its 14 × 14 matrix, the fifty-seven refusal
reasons, the twenty-four events, the thirteen commands, the eight workflow
tables, the attempt ceiling of 10, `content_sha256` self-exclusion, the
`work_spec_sha256 UNIQUE` admission key, and the four-check delivery gate all
stand exactly as landed.

---

## 2. Scope and non-goals

### 2.1 In scope (frozen here, implemented in the implementation wave)

1. A frozen internal canonical representation for three signals — **spans**,
   **log records** and **metrics** — whose field names and semantics match the
   OpenTelemetry logs and metrics data models and W3C Trace Context (§4, §6, §8).
2. A frozen **trace and causality model** rooted in the already-durable WorkSpec
   trace identity, covering retry, resume, checkpoint restoration, compensation,
   cancellation, approval and duplicate-receipt paths (§5).
3. A frozen **privacy and cardinality model** — a closed attribute grammar with
   no free-text value type (§7).
4. A frozen **metric inventory** with exact names, units, instrument kinds,
   temporality and dimensions, all derivable (§8).
5. A frozen **operator surface**: four `observe` CLI leaves, two doctor checks,
   power policy for all four leaves, and a local file export boundary (§9).
6. A frozen **path boundary** (§17) and **test/runtime budget** (§18).

### 2.2 NOT in scope (mechanically absent, not merely discouraged)

- An `opentelemetry` Python dependency, or any new dependency at all.
  `pyproject.toml` is not edited; the wheel and zipapp membership assertions in
  `.github/workflows/ci.yml` would fail if it were.
- An OpenTelemetry Collector, an OTLP/gRPC or OTLP/HTTP exporter, any socket,
  any network call, any URL fetch.
- A background daemon, a thread, a scheduler, a poller, a clock loop.
- Cloud telemetry, a hosted backend, a dashboard, an alert, an SLO, a
  notification.
- Provider or model instrumentation; `gen_ai.*` vocabulary of any kind (§3.6).
- Any change under `/home/daksh/Projects/AICompany`.
- **U-E6 in every form** — flight recorder, deterministic replay, incident
  reconstruction, execution re-simulation, counterfactuals (§12).
- U-W4 loop homeostasis, U-W5 semantic interrupts, U-E2 evaluations, U-E3 claim
  audit, U-E4 drift, U-E5 Security Sentinel.
- MCP/A2A, sandbox, policy engine, kill switch.
- Private chain-of-thought, prompt or model-output storage in any form.
- Sampling, head-based or tail-based. U-E1 projects what is stored; there is
  nothing to sample.
- Baggage, in any direction (§7.5).

### 2.3 Untouched

`agentic_os/db.py`, `migrations.py`, `protocols.py`, `protocols/**`,
`workflow_engine.py`, `workflow_store.py`, `workspecs.py`, `events.py`,
`ids.py`, `models.py`, `utils.py`, `secretscan.py`, `backup.py`,
`mirror_export.py`, `export.py`, `obsidian.py`, `pack.py`, `governance.py`,
`passports.py`, `routing.py`, `agent_handoffs.py`, `catalog.py`, `hooks.py`,
`ingest.py`, `retrieval.py`, `tests/fixtures/**`, `.github/workflows/ci.yml`,
`tools/**`, `pyproject.toml`, `AGENTIC_OS_BLUEPRINT.md`, `RECOVERY.md`,
`TROUBLESHOOTING.md`, and every landed contract.

---

## 3. Primary-source basis and the exact compatibility boundary

### 3.1 What "OpenTelemetry-compatible" is frozen to mean

> U-E1 emits records whose **field names, types and semantics** are those of the
> OpenTelemetry data models, serialized on request as OTLP/JSON, such that a
> conformant consumer can read them without AOS importing, linking, vendoring or
> depending on any OpenTelemetry artifact.

Compatibility is a property of the **bytes AOS writes**, not of the libraries
AOS loads. This is the smallest boundary that earns the word, and §3.5 shows why
anything larger fails on evidence.

### 3.2 Sources consulted

| # | Source | Version / status | Accessed |
| --- | --- | --- | --- |
| 1 | `https://www.w3.org/TR/trace-context/` | **W3C Recommendation, 23 November 2021** | 2026-08-05 |
| 2 | `https://www.w3.org/TR/trace-context-2/` | **W3C Candidate Recommendation Draft, 28 March 2024** | 2026-08-05 |
| 3 | `https://opentelemetry.io/docs/specs/otel/logs/data-model/` | **Stable** | 2026-08-05 |
| 4 | `https://opentelemetry.io/docs/specs/otel/metrics/data-model/` | **Stable**; "Resets and Gaps" and "Overlap" are **Development** | 2026-08-05 |
| 5 | `https://opentelemetry.io/docs/specs/otel/baggage/api/` | **Stable** | 2026-08-05 |
| 6 | `https://opentelemetry.io/docs/concepts/signals/baggage/` | concept page | 2026-08-05 |
| 7 | `https://opentelemetry.io/docs/specs/semconv/` | **1.44.0** | 2026-08-05 |
| 8 | `https://opentelemetry.io/docs/specs/semconv/general/naming/` | naming rules | 2026-08-05 |
| 9 | `https://opentelemetry.io/docs/specs/otel/versioning-and-stability/` | maturity levels | 2026-08-05 |
| 10 | `https://opentelemetry.io/blog/2026/deprecating-span-events/` | Span Events **API** deprecation | 2026-08-05 |
| 11 | `https://opentelemetry.io/docs/specs/semconv/gen-ai/` | **moved out of the core repo** | 2026-08-05 |

### 3.3 Concepts ADOPTED, with the reason

| Concept | Source | Adopted as |
| --- | --- | --- |
| trace-id = 32 lowercase hex, all-zero invalid | 1 | already enforced by `protocols.TRACE_ID_PATTERN` + `protocols.py:1972`; U-E1 inherits it unchanged |
| span-id = 16 lowercase hex, all-zero invalid | 1 | **new** — §4.4's `span_id` grammar and its all-zero guard |
| "the vendor creates a new `traceparent`" on invalid input | 1 | §4.5: an unusable inbound trace is **restarted, never repaired and never adopted** |
| LogRecord field set and `Timestamp` / `ObservedTimestamp` separation | 3 | §6.2 verbatim field mapping |
| "Use `Timestamp` if it is present, otherwise use `ObservedTimestamp`" | 3 | §6.3 |
| SeverityNumber ranges 1–24 | 3 | §6.4, restricted to the four values §6.4 lists |
| "A log record with a non-empty event name is an Event" | 3 | §6.1 — U-E1's events ARE log records; there is no fourth signal |
| Sum / Gauge / Histogram; only Sums monotonic | 4 | §8.2 |
| Cumulative temporality and `StartTimeUnixNano` | 4 | §8.3 |
| attribute naming: lowercase, `.` namespace, snake_case components | 8 | §7.2 grammar |
| "Units do not need to be specified in the names"; "Counters SHOULD NOT append `_total`" | 8 | §8.2 names |
| `otel.*` reserved; use your own prefix | 8 | §7.2 — everything U-E1 mints is under `aos.` |
| "Prefer the Logs API for new events and exceptions" | 10 | §5.4 — U-E1 mints **no span events at all** |
| "Long-term dependencies SHOULD NOT be taken against signals in Development" | 9 | §3.5 and §8.3 |

### 3.4 Concepts ADAPTED, with the reason

| Concept | Adapted how | Why |
| --- | --- | --- |
| nanosecond `Timestamp` (source 3) | represented in ns, but **derived from second-precision RFC3339** | `utils.utc_now_iso()` is the only clock in the codebase and writes seconds (§6.5). U-E1 states the quantization instead of implying precision it does not have. |
| `ObservedTimestamp` (source 3) | the joined base-`events.ts` row | that row is written from AOS's own clock inside the same transaction (§6.5); it is a genuine observation time, not a second copy of the asserted one |
| `StartTimeUnixNano` (source 4) | ledger genesis, not process start | there is no process; the ledger is the accumulating thing (§8.3) |
| OTLP file output | OTLP/**JSON** encoding, AOS-owned file layout | the File Exporter document is not stability-frozen; the OTLP/JSON encoding is. U-E1 pins the stable part and owns the unstable part (§9.5). |

### 3.5 Concepts REFUSED, with the reason

| Concept | Refused because |
| --- | --- |
| an `opentelemetry` SDK/API dependency | it buys nothing the byte format does not already buy, and it would add the first third-party runtime dependency this project has ever had — breaking the wheel/zipapp membership assertions that currently prove the distribution contains exactly the source tree |
| a Collector, OTLP/gRPC or OTLP/HTTP export | out of scope by §2.2; also a network egress path in a tool whose entire security posture is "no network" |
| **span events** (`Span.AddEvent`) | source 10: the API is deprecated and the guidance is "Avoid adding new dependencies on span event methods". Building a brand-new contract on a deprecated surface would be knowingly shipping technical debt. §5.4 uses log records instead — export-equivalent today, correct tomorrow. |
| the `random-trace-id` flag (source 2) | source 2 requires "at least the right-most 7 bytes of the `trace-id` _MUST_ be selected randomly". U-E1's derived trace-ids are a domain-separated SHA-256 prefix — deterministic by design (§4.3). Setting the flag would be a false claim about our own data. §4.6 forbids it by name. |
| Baggage | source 6: "there are no built-in integrity checks to ensure that Baggage items are yours"; and baggage is "unassociated with attributes on spans, metrics, or logs without explicitly adding them". It provides no integrity and no automatic benefit, and treating it as trusted would be exactly the identity laundering §4.5 exists to prevent. |
| Delta temporality (source 4) | delta requires a durable accumulator and a reset model; the reset/gap machinery is **Development**-status (source 4). §8.3 designs the problem out instead of depending on an unstable area. |
| `gen_ai.*` semantic conventions | source 11: the conventions have **moved out of the core semantic-conventions repository** and the core `gen_ai.*` definitions are deprecated. Freezing that vocabulary into a stable contract now would pin AOS to names their own owners are actively relocating. U-E1 mints no `gen_ai.*` name and defines no compatibility layer for one — provider instrumentation is out of scope by §2.2, so no layer is needed. |
| `Summary` metric points (source 4) | "legacy type for compatibility only" |

### 3.6 The GenAI question, answered explicitly

The Wave 0 prompt requires that experimental OpenTelemetry GenAI names not be
frozen as stable contract vocabulary without an explicit compatibility layer and
evidence. **U-E1 freezes none.** The evidence is source 11: the conventions moved
to a separate repository and the in-core definitions are deprecated. Since U-E1
performs no provider or model instrumentation (§2.2), there is no signal that
would carry such a name, so no compatibility layer is required and none is
defined. A future unit that instruments a provider inherits this question
unresolved, which is the honest state.

---

## 4. Identity and causality

### 4.1 The complete identifier inventory

Every identifier the live repository carries, classified. **Authoritative** = a
stored value that decides something. **Derived** = a pure function of other
stored values. **Descriptive** = carried and rendered, deciding nothing.

| Identifier | Class | Owner / origin | U-E1 use |
| --- | --- | --- | --- |
| `trace.trace_id` (WorkSpec) | **authoritative for identity, descriptive for control** | author, or `workspecs._derive_defaults` | **the trace root** (§4.2) |
| `trace.correlation_id` | descriptive | same | span attribute |
| `trace.causation_id` | descriptive | same | span attribute when present |
| `work_spec_sha256` | authoritative | `protocols.content_digest` | admission key; span attribute |
| `work_spec_id` | derived | `_TAG_WORK_SPEC_ID` | span attribute |
| workflow id `WF-n` | authoritative | `_workflow_identity` from the WorkSpec digest | span name + attribute |
| `revision`, `seq` | authoritative | store | ordering; log attributes |
| `policy_version` | authoritative | store | log attribute; metric dimension |
| `command_id` | authoritative | caller UUID | dedupe axis; log attribute |
| `command_sha256`, `event_sha256` | derived | seal | log attributes |
| `intent_id`, `idempotency_key` | derived | `_TAG_INTENT`, `_TAG_DISPATCH_IDEM` | log attributes |
| `intent_seq` | authoritative | store | not exposed |
| `receipt_id` | authoritative | caller | dedupe axis; log attribute |
| `attempt_no` | authoritative | AOS, monotone from 1 | attempt span identity |
| `runtime_task_uuid` | authoritative (as an observation) | runtime, via the `accepted` receipt | attempt span attribute |
| `checkpoint_id`, `checkpoint_seq` | authoritative | producer / store | log attributes; link target |
| result/fact `document_sha256` | derived | seal | log attribute |
| `aos_task_id` `T-n` | authoritative | ledger | span attribute (the task→workflow edge) |
| run `R-n`, evidence `E-n`, decision `D-n`, pack `P-n` | authoritative | ledger | log attributes when the base journal names them |
| handoff `H-n` (legacy), `AH-n`, `RP-n` | authoritative | ledger | log attributes only |
| memory `M-`/`MS-`/`ML-`/`ME-n` | authoritative | ledger | log attributes only |
| `session_id` (hooks) | authoritative | hook staging | log attribute only |
| `invocation_id`, `binding_id`, `component_id`+`component_version` | authoritative | `governance.py` | **not exposed** — the governed-invocation evidence path has no live caller; §5.7 |
| `result_id`, `interrupt_id`, `passport_version`, `registry_version` | authoritative | spine / ledger | log attributes where already journaled |
| `queue_route` | **descriptive** | operator-chosen slug | §7.4 — classified, never a metric dimension |
| `actor` / provenance `agent:<name>` | **descriptive** | user-chosen | §7.4 — classified, never a metric dimension |
| `reason_code` | **descriptive** | runtime-chosen slug, `^[a-z][a-z0-9_]{2,63}$` | §7.4 and §8.5 — **never a metric dimension** |
| `span_id` | derived | **minted by U-E1** (§4.4) | span identity |
| base `events.id` | authoritative | rowid | log record ordering within a second |

### 4.2 The trace root — the load-bearing decision

**A workflow's trace identity is `workflows.work_spec_document`'s
`trace.trace_id`, and nothing else, for the whole life of the workflow.**

The four facts that make this both possible and correct, each verified live at
`f32fb00`:

1. `trace` is in `protocols._ENVELOPE_REQUIRED`, so **every** valid WorkSpec
   carries one.
2. When the author supplies none, `workspecs._derive_defaults` mints one:
   `trace_id` = `sha256(_TAG_TRACE ‖ 0x00 ‖ material).hex()[:32]`, passed through
   `_guard_trace_id`, with a `correlation_id` from `_TAG_CORRELATION`. So the
   field is never absent and never zero.
3. `workflows.work_spec_document TEXT NOT NULL` stores the admitted artifact
   **verbatim**, and `workflows.work_spec_sha256 TEXT NOT NULL UNIQUE` seals it.
4. Admission is once per WorkSpec digest and the document column is never
   rewritten.

Therefore the trace root is already **durable, immutable, digest-bound and
tamper-evident** — before U-E1 exists. This is why §11 needs no new table.

### 4.3 Foreign traces are out of scope — one trace source, no `foreign_trace` link

*Amended by A1.2. The original clause required a `foreign_trace` link; this one
removes the kind. D-v0.4.142.*

A `trace` may legally also appear on an `aos.workflow-command/v1`, on a receipt,
on a result envelope (where the spine **requires** it) and on an outbound intent
body. Those values are **independent** of the WorkSpec's and of each other. A
single workflow can therefore accumulate several distinct trace identities.

**Why the original clause could not hold.** Every one of those places is a
document body — `workflow_receipts.document`, `workflow_facts.document`,
`workflow_intents.document`, `workflow_checkpoints.document`, `report_document`.
§7.3 and D-v0.4.137 forbid U-E1 from parsing any of them; only
`work_spec_document` is opened, and only for four named members. A foreign trace
is therefore **unobservable** to U-E1 by construction, so no valid projection can
ever emit a `foreign_trace` link. A vocabulary that advertises a kind nothing can
produce misleads every consumer and every future implementer who reads it as a
feature.

**Frozen rule, as amended — seven clauses:**

1. The authoritative U-E1 trace root is `work_spec_document.trace.trace_id`, and
   nothing else (§4.2).
2. U-E1 does not inspect receipt, result, checkpoint, fact or report bodies for
   trace identities — or for anything else (§7.3, D-v0.4.137).
3. A trace identity outside the authoritative work-spec root is **neither adopted
   nor emitted**: it does not become a span's `trace_id`, a link's trace, an
   attribute, a log field or an exported value.
4. `foreign_trace` is **absent from the active link-kind vocabulary.** The active
   vocabulary is exactly three kinds: `retry_of` (§5.2), `restored_from` (§5.3)
   and `compensates` (§5.1). Every emitted link carries the workflow's own root
   trace.
5. §18.6 row E3 proves **both halves** — non-adoption and non-emission — and
   asserts that the projection has exactly one source of `trace_id`.
6. `retry_of`, `restored_from` and `compensates` are preserved unchanged. A1.2
   narrows the vocabulary; it changes no link that is actually produced.
7. A **future governed cross-runtime adapter** may introduce verified
   foreign-trace links under a separate contract. That contract will have to
   supply what U-E1 lacks: an authorized read path to the body carrying the
   foreign trace, and a rule for verifying it. Neither is in scope here, and this
   clause is not standing authority for either.

The term "foreign trace" survives in §15 as terminology, because operators and
reviewers still need a name for the thing U-E1 refuses to touch. Naming a refusal
is not the same as keeping a link kind for it.

### 4.4 Span identity

```
span_id = guard_zero( sha256(TAG ‖ 0x00 ‖ material).hex()[:16] )
```

- 16 lowercase hex characters, matching W3C Trace Context (source 1).
- `guard_zero` mirrors `workspecs._guard_trace_id` exactly: an all-zero result
  has its last character replaced by `1`. Unreachable in practice; guarded
  anyway, because source 1 makes an all-zero span-id invalid.
- Domain-separation tags, frozen, one per span kind:

| Span kind | Tag | Material |
| --- | --- | --- |
| workflow | `aos-observability-span-workflow/v1` | `trace_id ‖ ":" ‖ WF-n` |
| attempt | `aos-observability-span-attempt/v1` | `trace_id ‖ ":" ‖ WF-n ‖ ":" ‖ attempt_no` |
| compensation | `aos-observability-span-compensation/v1` | `trace_id ‖ ":" ‖ WF-n ‖ ":" ‖ opened_seq` |

- **No RNG and no clock is read.** The codebase contains neither a monotonic
  clock nor a random source in any comparable path, and U-E1 introduces neither.
  Span ids are byte-stable: the same ledger yields the same ids forever.

### 4.5 Preventing identity laundering

Five rules, jointly sufficient:

1. **The root is fixed at admission and sealed.** No later caller input can
   re-root a workflow's trace (§4.2). A caller who wants a different trace must
   admit a different WorkSpec, which is a different digest and a different
   workflow.
2. **A caller-supplied identifier decides nothing.** No U-E1 trace, correlation,
   causation or span value ever selects a row, authorizes an action, dedupes a
   command, gates a transition, orders history or changes any output other than
   its own rendering. An identifier that decides nothing cannot launder
   anything. This is the whole mechanism; the other four rules are hygiene.
3. **There is exactly one source of `trace_id`** (§4.3, as amended by A1.2). A
   foreign trace is neither adopted nor emitted, and no link kind exists for one.
4. **Zero is invalid on both axes.** All-zero `trace_id` is already refused by
   `protocols.py:1972` and guarded by `workspecs._guard_trace_id`; §4.4 adds the
   matching all-zero `span_id` guard.
5. **No Baggage, in either direction** (§7.5).

### 4.6 The `random-trace-id` flag

U-E1 emits `trace_flags` with the `random-trace-id` bit (source 2, §3.2.2.5.2)
**always clear**, and states in its own exported metadata that its identifiers
are deterministic. A derived trace-id does not satisfy "at least the right-most
7 bytes _MUST_ be selected randomly"; asserting the flag would be a false claim
about our own data. This is frozen so no later implementer "improves" it.

---

## 5. The span and causality model

### 5.1 The tree

```
task T-n                       — an ATTRIBUTE, never a span (U-E1 does not own task lifetime)
└── workflow span  WF-n        — the root of the AOS trace
    ├── attempt span  #1       — one per workflow_attempts row
    ├── attempt span  #2       — SIBLING of #1, not a child
    │     link retry_of      → #1
    │     link restored_from → #k   (only when a checkpoint crossed attempts)
    └── compensation span      — child of the WORKFLOW span, not of an attempt
          link compensates   → #N
```

### 5.2 Why retry is a sibling with a link, not a child

Attempt 2 is not work performed *inside* attempt 1; it is work performed
*because* attempt 1 ended. Nesting it under attempt 1 would make attempt 1's
duration include attempt 2's, which is false, and would make a 10-attempt
workflow a 10-deep tree, which is unreadable. A sibling with a `retry_of` link
states the causal edge without lying about containment.

### 5.3 Checkpoint restoration is a **link**, not only an event

`checkpoint_restored` is cross-attempt: the restored checkpoint may belong to a
different `attempt_no` than the attempt restoring it. Recording it only as an
event on the restoring attempt would erase the single causal edge that connects
attempt N+1 back to attempt N's checkpoint. **Frozen:** a `checkpoint_restored`
whose source attempt differs from the restoring attempt emits a
`restored_from` span link in addition to its log record. When source and target
are the same attempt, only the log record is emitted.

### 5.4 Everything else is a log record, never a span event

The following emit **log records carrying `TraceId` and `SpanId`**, never span
events and never new spans:

`workflow_admitted`, `workflow_validated`, `approval_requested`,
`approval_recorded`, `dispatch_requested`, `dispatch_rejected`,
`dispatch_revoked`, `dispatch_accepted`, `run_started`, `run_waiting_input`,
`run_waiting_approval`, `run_paused`, `run_resumed`, `cancel_requested`,
`workflow_succeeded`, `workflow_failed`, `workflow_cancelled`,
`policy_version_adopted`, `attempt_failed`, `checkpoint_recorded`,
`checkpoint_restored`, `compensation_started`, `compensation_applied`,
`compensation_failed` — all twenty-four.

Rationale: source 10 deprecates the span-event **API** and states "Prefer the
Logs API for new events and exceptions." Choosing log records costs nothing
today (both serialize into OTLP, both carry trace and span identity) and avoids
building a new contract on a deprecated surface.

### 5.5 The edges that consume no attempt

`dispatch_rejected` and `dispatch_revoked` open **no** attempt row: the CHECK
constraints on `workflows` permit `dispatch_intent_id` only in `validated` and
`retrying`, and no attempt is reserved until an `accepted` receipt is observed.
**Frozen:** these emit a log record on the **workflow** span, carrying
`aos.workflow.intent_id`, and create no attempt span. The intent→rejection edge
is therefore visible without inventing an attempt that never existed.

### 5.6 Attempt terminal status

| `workflow_attempts.state` | Span status | `aos.attempt.state` |
| --- | --- | --- |
| `open` | Unset | `open` |
| `succeeded` | Ok | `succeeded` |
| `failed` | Error | `failed` |
| `abandoned` | **Unset** | `abandoned` |

`abandoned` is deliberately **not** Error. An attempt abandoned by cancellation
did not fail; marking it Error would make every cancelled workflow look like a
failure in every downstream tool.

### 5.7 What emits nothing at all

| Situation | Emits |
| --- | --- |
| duplicate command (`status="replay"`) | **nothing** — no span, no log record, no metric increment |
| receipt redelivery (`receipt_id` dedupe) | **nothing** |
| intent redelivery (content-addressed rewrite) | **nothing** |
| `revision_mismatch` and every other refusal | nothing from the engine; the CLI's own journal row is projected as a log record (§6.6) |
| private-runtime task-attempt retry | **nothing** — AOS never observed it (U-W3 §4.1) |
| lock waiting | **nothing** |
| governed-invocation evidence | **nothing** — `governance.py`'s evidence builder has no live caller in `agentic_os/`; U-E1 does not create one |

The rule: **U-E1 emits a signal exactly when the ledger recorded an event, and
never otherwise.** A replay that appended nothing must observe as nothing, or
the telemetry claims more things happened than happened.

### 5.8 Approval has two scopes and they are not the same edge

`workflow_facts.fact_scope` distinguishes `admission`-scope approval (the
`awaiting_approval` gate) from `runtime`-scope approval (the
`run_waiting_approval` wait exit). **Frozen:** `approval_recorded` log records
carry `aos.approval.scope` with exactly that value. Collapsing the two would
make a runtime approval look like an admission decision.

### 5.9 The attempt-budget divergence is invisible by design

Under policy v2 a result envelope's `attempt` must equal the AOS `attempt_no`,
and the private runtime's own `task_attempts` produce no AOS receipt. U-E1
therefore **cannot** and **does not** represent runtime-internal task retries.
This is stated rather than left implicit: an operator reading an AOS trace is
seeing what AOS observed, not what the runtime did.

---

## 6. Signals and storage

### 6.1 Exactly three signals

**Spans**, **log records** and **metrics**. There is no fourth. Following source
3 — "A log record with a non-empty event name is an Event" — U-E1's *events*
**are** log records carrying `EventName`; "event" is not a separate signal and is
never implemented as one.

### 6.2 Log record field mapping (source 3, verbatim field names)

| OTel field | U-E1 source |
| --- | --- |
| `Timestamp` | `workflow_events.created_at` → ns (§6.5) |
| `ObservedTimestamp` | the joined base `events.ts` → ns (§6.5) |
| `TraceId` | the workflow's trace root (§4.2) |
| `SpanId` | the span the record belongs to (§5) |
| `TraceFlags` | `0x00` — sampled bit clear, `random-trace-id` bit clear (§4.6) |
| `SeverityNumber` / `SeverityText` | §6.4 |
| `EventName` | the workflow event name, prefixed `aos.workflow.` |
| `Body` | **empty** — always (§7.3) |
| `Resource` | §6.7 |
| `InstrumentationScope` | `{name: "agentic_os.observability", version: <package version>}` |
| `Attributes` | the closed set §7.2 admits |

### 6.3 Timestamp selection

Adopted verbatim from source 3: "Use `Timestamp` if it is present, otherwise use
`ObservedTimestamp`." A workflow event always has both; a base-journal record
that is not a workflow event has only `ObservedTimestamp`, and the rule resolves
it.

### 6.4 Severity, restricted to four values

| Condition | SeverityNumber | SeverityText |
| --- | --- | --- |
| ordinary lifecycle event | 9 | `INFO` |
| `dispatch_rejected`, `dispatch_revoked`, `attempt_failed`, `compensation_failed` | 13 | `WARN` |
| `workflow_failed` | 17 | `ERROR` |
| a projected CLI refusal (§6.6) | 13 | `WARN` |

Four values, not twenty-four. A severity scale finer than the decisions it
records is noise.

### 6.5 Time, honestly

| Question | Frozen answer |
| --- | --- |
| Event time | `workflow_events.created_at` — RFC3339, **second precision**, **copied from the caller's command**, never read from a clock |
| Observed time | the joined base `events.ts` — RFC3339 second precision, written by `utils.utc_now_iso()`, the codebase's **only** wall-clock read, inside the same transaction |
| Representation | both converted to `uint64` nanoseconds since the UNIX epoch, as source 3 requires; the low nine digits are **always zero** and the contract says so rather than implying precision AOS does not have |
| Monotonic duration | **does not exist.** There is no monotonic clock in this codebase. U-E1 does not invent one and does not claim one. |
| Duration | `end_ns − start_ns`, **clamped at 0** |
| Clock skew | event time is caller-asserted, so `end < start` is reachable. Such a span carries `aos.clock.inconsistent = true`, duration `0`, and is listed by `observe verify`. |
| Negative duration | **unrepresentable** |
| Impossible instants | already refused upstream by `workflow_engine._is_real_instant` and `protocols._parse_instant`; a row that predates those guards is handled by §10 |
| Ordering within one second | base `events.id` ascending, then `workflow_events.seq` ascending — both total orders already in the ledger |

### 6.6 The base journal is the log source

`workflow_store._journal` writes exactly **one** base `events` row per appended
workflow event, carrying `workflow_id`, `seq`, `revision`, `policy_version`,
`from_state`, `to_state`, `command`, `command_id`, `command_sha256`,
`event_sha256` and `work_spec_sha256`. That row is the join key to
`workflow_events`, and its `ts` is the observation clock.

Because the base journal is also written by migrations, backup, hook ingest,
pack build, routing, catalog, passports, export and handoffs, U-E1's log
projection covers **the whole base journal**, not only workflows. Rows with no
workflow entity get no `TraceId`/`SpanId` and are emitted as unbound log
records. This is one table with one existing redaction choke point
(`events.emit` → `secretscan.redact_tree`), which is why it costs no new
instrumentation anywhere.

### 6.7 Resource

Closed, five members, no host identity:

```
service.name        = "agentic-os"
service.version     = <package version>
service.instance.id = sha256(workspace absolute path).hex()[:32]
telemetry.sdk.name  = "agentic-os-observability"
telemetry.sdk.language = "python"
```

`service.instance.id` is a **digest** of the workspace path, never the path: a
path is a filesystem fact about a person's machine. No hostname, no username, no
IP, no MAC, no process id.

### 6.8 Durable versus rebuildable — the frozen separation

| Class | Contents |
| --- | --- |
| **Durable authoritative** (pre-existing; U-E1 adds none) | `workflows.work_spec_document.trace`, `workflow_events`, `workflow_attempts`, `workflow_checkpoints`, `workflow_facts`, `workflow_receipts`, `workflow_intents`, `workflow_commands`, base `events` |
| **Rebuildable projection** (U-E1 owns; stored nowhere) | every span, every span id, every link, every log record, every metric point, every exported file |

**U-E1 persists nothing.** The projection is recomputed on every invocation.
Consequences, all deliberate: no cache to invalidate, no accumulator to reset,
no divergence between stored and computed telemetry, no retention policy, no
pruning, no growth, and no new failure mode in the write path — because U-E1 has
no write path into `aos.db` at all.

### 6.9 Canonical serialization and integrity

- The projection is serialized with `protocols.serialize_canonical` — the
  existing canonical JSON, sorted keys, no floats.
- Any exported capsule carries `content_sha256` computed by
  `protocols.content_digest` (self-excluding), so an export is verifiable by the
  same idiom every other artifact in this repository uses.
- U-E1 introduces **no new hash algorithm, no new digest field name and no new
  canonicalization**.
- Append/mutation rules: not applicable — nothing is stored (§6.8).

### 6.10 Bounds

| Bound | Value | Derivation |
| --- | --- | --- |
| attribute key length | ≤ 63 chars | matches `ERROR_CODE_PATTERN`'s ceiling; no new number |
| attribute value length | ≤ 256 chars | the spine's `_string` default max |
| attributes per record | ≤ 32 | `MAX_OBJECT_MEMBERS / 8`; no new number |
| links per span | ≤ 10 | the frozen attempt ceiling — a workflow cannot have more attempts to link to |
| spans per workflow | ≤ 12 | 1 workflow + 10 attempts + 1 compensation |
| log records per workflow | ≤ 10 × the per-attempt event ceiling, bounded by `workflow_events` row count | no independent number invented |
| record depth | ≤ 4 | flat by construction; well under `MAX_DEPTH` 32 |
| exported capsule bytes | ≤ `protocols.MAX_ARTIFACT_BYTES` (262144) per document | the existing artifact bound |
| total metric series | **≤ 67** | §8.4, computed not asserted |

Every bound is derived from an existing frozen constant. U-E1 introduces no
tuned number.

---

## 7. Privacy, classification and cardinality

### 7.1 Data classification

Each emitted record carries `aos.data.classification`, taken from the WorkSpec's
own `data_classification` (`public` | `internal` | `confidential` |
`restricted`) — the spine's existing closed enum. U-E1 invents no second
classification vocabulary.

### 7.2 The closed attribute grammar — redaction by construction

**Key:** `^aos\.[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){0,3}$`, ≤ 63 characters.
Lowercase, `.`-namespaced, snake_case components — source 8's rules. Everything
U-E1 mints is under `aos.`; `otel.*` is reserved (source 8) and never used.

**Value:** exactly one of six types. There is **no free-text value type.**

1. a member of a closed vocabulary already frozen in code (14 states, 24 events,
   13 commands, 4 attempt states, 4 classifications, 2 policy versions, 3 intent
   kinds, 4 approval scopes/decisions);
2. an identity matching a frozen pattern (`WF-n`, `T-n`, UUID, 32-hex, 16-hex);
3. a SHA-256 digest;
4. a bounded integer;
5. an RFC3339 instant;
6. a boolean.

This is the primary privacy control, and it is structural: a prompt, a goal, an
acceptance criterion or a model output **cannot be expressed** in this grammar.
That is stronger than filtering, because there is no path that could carry the
value in the first place.

### 7.3 Forbidden content, named

Never present in any U-E1 signal, by default or by flag — **there is no flag**:

- prompts, model output, completions, tool arguments, tool results;
- hidden reasoning or chain-of-thought in any form;
- secrets, credentials, tokens, keys;
- `goal`, `acceptance_criteria`, `constraints`, `inputs[].ref`, `inputs[].note`;
- `reason.message` (free text, ≤ 512 chars, stored in receipt documents);
- checkpoint `payload` (opaque by U-W3 §8.2; U-E1 never opens it);
- result-envelope bodies, `evidence[].claim`, `evidence[].ref`;
- file paths, hostnames, usernames, environment variables;
- `Body` on log records — **always empty** (§6.2).

**The document-column rule.** `work_spec_document`, `report_document`,
`workflow_intents.document`, `workflow_receipts.document`,
`workflow_facts.document` and `workflow_checkpoints.document` are **never opened
by U-E1**, with exactly one exception: `work_spec_document` is parsed to read
**three members** — `trace.trace_id`, `trace.correlation_id` and
`trace.causation_id` — and `data_classification`. Nothing else in that document
is read, and no other document column is parsed at all. Everything else is
referenced by its digest.

### 7.4 The safe alternative for everything excluded

| Excluded | Referenced instead by |
| --- | --- |
| WorkSpec body | `aos.workspec.sha256` |
| result / fact body | `aos.result.sha256` |
| checkpoint payload | `aos.checkpoint.id` + `aos.checkpoint.sha256` + `aos.checkpoint.payload_bytes` |
| receipt body | `aos.receipt.id` + `aos.receipt.sha256` |
| `reason.message` | `aos.reason.code` — the slug only, never the message |
| workspace path | `service.instance.id` = a digest (§6.7) |

**Three descriptive identifiers are classified rather than excluded**, because
they are already durable in the base journal and excluding them would make the
projection useless:

| Value | Shape | Rule |
| --- | --- | --- |
| `queue_route` | operator-chosen slug | span/log attribute only; **never a metric dimension** |
| `actor` (`human` \| `agent:<name>`) | user-chosen name ≤ 63 | span/log attribute only; **never a metric dimension**; already passed through `secretscan.redact_tree` at journal-write time |
| `reason_code` | runtime-chosen slug ≤ 63 | span/log attribute only; **never a metric dimension** (§8.5) |

`secretscan.redact_tree` is applied at the export boundary as defence in depth
— not as the primary control, which is §7.2's grammar.

### 7.5 Baggage

**U-E1 defines no baggage, reads no baggage, writes no baggage, propagates no
baggage, and has no baggage field.** No caller-supplied value is ever treated as
an authorization, trust or access-control input. Evidence: source 6 — "there are
no built-in integrity checks to ensure that Baggage items are yours" — and
baggage is "unassociated with attributes on spans, metrics, or logs without
explicitly adding them", so it offers no automatic benefit to offset that.

### 7.6 Cardinality

- **Metric dimensions** are drawn exclusively from closed vocabularies frozen in
  code. §8.4 computes the exact ceiling: **67 series.**
- **Forbidden as metric dimensions**, by name: `workflow_id`, `task_id`,
  `trace_id`, `span_id`, `correlation_id`, `causation_id`, `command_id`,
  `intent_id`, `receipt_id`, `checkpoint_id`, `runtime_task_uuid`, any sha256,
  `actor`, `agent`, `project`, `tenant`, `queue_route`, `reason_code`,
  `attempt_no`, any timestamp.
- **Span and log attributes** may carry high-cardinality identities — that is
  what a trace is for — but are bounded per record by §6.10.

---

## 8. Metrics

### 8.1 Derivability is the constraint

**Every metric is a pure function of stored rows, computed by scan at read
time.** No accumulator, no counter column, no cached total. §6.8's
"U-E1 persists nothing" applies here without exception.

### 8.2 The inventory (closed — five metrics)

| Name | Instrument | Monotonic | Unit | Dimensions | Derivation |
| --- | --- | --- | --- | --- | --- |
| `aos.workflow.count` | Sum | yes | `{workflow}` | `aos.workflow.state` | `COUNT(*) FROM workflows GROUP BY state` |
| `aos.workflow.event.count` | Sum | yes | `{event}` | `aos.workflow.event` | `COUNT(*) FROM workflow_events GROUP BY event` |
| `aos.workflow.attempt.count` | Sum | yes | `{attempt}` | `aos.attempt.state` | `COUNT(*) FROM workflow_attempts GROUP BY state` |
| `aos.workflow.checkpoint.count` | Sum | yes | `{checkpoint}` | none | `COUNT(*) FROM workflow_checkpoints` |
| `aos.workflow.transition.duration` | Histogram | n/a | `s` | `aos.workflow.event` | successive `created_at` deltas per workflow, clamped at 0 (§6.5) |

Naming follows source 8: lowercase, `.`-namespaced, no unit in the name, no
`_total` suffix on counters, `aos.` prefix (not `otel.`, which is reserved).
Units use the curly-brace annotation form for dimensionless counts.

### 8.3 Temporality

**Cumulative**, always. `StartTimeUnixNano` = **ledger genesis** = the earliest
base `events.ts` in the workspace; `TimeUnixNano` = the moment of the read.

The reasoning is evidential, not stylistic. Delta temporality requires a durable
accumulator and therefore a reset model, and the reset/gap machinery in source 4
is marked **Development** — and source 9 says "Long-term dependencies SHOULD NOT
be taken against signals in Development." A full scan of an append-only ledger
*is* a cumulative series from genesis by construction.

### 8.4 The exact cardinality ceiling

```
aos.workflow.count              14 states          = 14
aos.workflow.event.count        24 events          = 24
aos.workflow.attempt.count       4 attempt states  =  4
aos.workflow.checkpoint.count    no dimensions     =  1
aos.workflow.transition.duration 24 events         = 24
                                                    ----
                                        TOTAL       = 67 series
```

Sixty-seven is a **ceiling reached only by a workspace that has exercised every
state, event and attempt state**. It cannot grow with the number of workflows,
tasks, attempts, agents, projects or operators. Growth requires a new frozen
vocabulary member, which requires a governed decision.

### 8.5 `reason_code` is excluded, and why it matters

`reason_code` on `attempt_failed` and `dispatch_rejected` is **not** one of the
fifty-seven frozen refusal reasons. It is a slug the *runtime* chooses, bounded
only by `^[a-z][a-z0-9_]{2,63}$`. As a metric dimension it would be unbounded
cardinality **and** a 64-character channel by which an external system could
write arbitrary content into AOS telemetry. It is therefore a span/log attribute
only, never a dimension (§7.4).

### 8.6 Resets, gaps and duplicates

| Concern | Answer |
| --- | --- |
| reset | **impossible.** There is no accumulator to reset. A scan of an append-only ledger cannot decrease. |
| gap | **impossible.** Every point covers `[genesis, now]` with no interval uncovered. |
| duplicate event | **impossible.** `UNIQUE(workflow_id, seq)` on `workflow_events` means a duplicate cannot exist to be counted twice; a duplicate *command* appends no event (§5.7). |
| database restored from backup | the series legitimately reflects the restored ledger. `StartTimeUnixNano` is recomputed from that ledger's genesis, which is exactly source 4's "a new unbroken sequence of observations begins". |

This is the payoff of §8.1: the three hardest metric problems are **designed
out** rather than handled.

---

## 9. Operator surface

### 9.1 The four leaves — a new top-level `observe` group

CLI leaves: **112 → 116**. `power.COMMAND_POLICY`: **112 → 116**.

| Leaf | Syntax | Kind | Ledger |
| --- | --- | --- | --- |
| `observe trace` | `aos observe trace <WF-n> [--json]` | `read_only` | no |
| `observe metrics` | `aos observe metrics [--json]` | `read_only` | no |
| `observe export` | `aos observe export <WF-n> --out <DIR> [--json]` | `derived_write` | no |
| `observe verify` | `aos observe verify [<WF-n>] [--json]` | `read_only` | no |

No `--actor`, no `--force`, no `--all`, no `--since`, no `--limit`, no
`--redact` / `--unredact` (§7.3 — there is no flag that reveals more), no
`--collector`, no `--endpoint`, no `--otlp-http`.

### 9.2 Exit codes

| Code | Meaning |
| --- | --- |
| 0 | success — **including `verify` finding divergence**, which is reported in the output |
| 1 | `AosError` — unknown workflow id, malformed id, unwritable output directory |
| 2 | argparse usage error |

`verify` reporting divergence exits **0** by the D-v0.3.22 / D-v0.4.44 rule
already twice affirmed in this ledger: a check that turns red because history
happened is a broken check. Divergence is surfaced instead by the doctor check
§9.4 defines and by a `divergent` array in the output.

### 9.3 The operator's path from task to event, without SQL

`observe trace T-0007` is **not** offered; the entry point is the workflow.

```
$ aos observe trace WF-4513636788148001841
task          T-0007
workflow      WF-4513636788148001841   succeeded   rev 9   policy 2
trace         4bf92f3577b34da6a3ce929d0e0e4736          (root: work-spec, derived)
workspec      sha256 9f2c…a41b

  span  workflow    00f067aa0ba902b7   0.0s   ok
    log   workflow_admitted        seq 1   INFO
    log   workflow_validated       seq 2   INFO
  span  attempt #1  b7ad12f0e4c95531   62.0s  error   runtime 3f9c…  abandoned=no
    log   dispatch_requested       seq 3   INFO   intent 7c1e…
    log   dispatch_accepted        seq 4   INFO
    log   attempt_failed           seq 5   WARN   reason=transient_timeout
  span  attempt #2  4c8e0b1a9d2f6673   41.0s  ok
    link  retry_of        -> attempt #1
    link  restored_from   -> attempt #1  checkpoint 2e91…
    log   checkpoint_restored      seq 8   INFO
    log   workflow_succeeded       seq 9   INFO
```

Every hop — task → workflow → trace → span → link → log — is on one screen, and
no raw SQL is required at any point. `--json` emits the same structure as the
canonical projection document.

### 9.4 Doctor: two appended checks (41 → 43)

| # | Name | Passes when | Warn-only |
| --- | --- | --- | --- |
| 42 | `observability trace roots resolvable` | every `workflows` row yields a parseable `work_spec_document.trace` with a non-zero 32-hex `trace_id` | no |
| 43 | `observability projection bounded` | every workflow's projection stays inside §6.10's span, link, attribute and byte bounds | yes |

Both **append at the end**, so no existing positive-index positional assertion
moves. Only tail-relative assertions notice, and §17.3 clause (d) enumerates
every one of them: `lines[-7 … -5]` in path 7, `checks[-4:]` and the warn-only
index census in path 8. Nothing else in nine census files shifts.

Recovery instruction for check 42, frozen: *"A workflow's stored WorkSpec
document is unparseable or carries no usable trace. This is a stored-row
integrity problem, not an observability problem: run `aos workflow verify
<WF-n>`, then restore from a verified backup (see RECOVERY.md). `observe` never
repairs a stored row."*

### 9.5 Export boundary

`observe export` writes, into an operator-named directory, three OTLP/JSON
documents plus a manifest:

```
<out>/traces.json     — OTLP/JSON TracesData
<out>/logs.json       — OTLP/JSON LogsData
<out>/metrics.json    — OTLP/JSON MetricsData
<out>/manifest.json   — aos.observability-export/v1, content_sha256-sealed
```

Frozen properties: LF endings via `utils.write_text_lf`; no network of any kind;
refuses to write into a non-empty directory rather than merging or overwriting;
`secretscan.redact_tree` applied to the whole capsule before writing.

The **OTLP/JSON encoding** is pinned because it is stable. The **file layout** is
AOS's own, because the OpenTelemetry File Exporter document is not stability
frozen — pinning our contract to it would be depending on a moving target.

### 9.6 Power behavior for all four leaves

| Mode | `trace` | `metrics` | `verify` | `export` |
| --- | --- | --- | --- | --- |
| `eco` | runs | runs | runs | **skipped** (derived work is skipped in eco) |
| `standard` | runs | runs | runs | runs |
| `deep` | runs, with the §9.4 bounds check as preflight | runs | runs | runs |
| `recovery` | runs (`read_only` ∈ `RECOVERY_ALLOWED_KINDS`) | runs | runs | **BLOCKED** (`derived_write` ∉ `RECOVERY_ALLOWED_KINDS`) |

Recovery deliberately keeps all three read-only leaves available: an operator
diagnosing a damaged workspace needs to *read* the trace of the workflow that
broke. Only the leaf that writes files is blocked.

---

## 10. Hostile and malformed persisted data

U-E1 reads rows that other units wrote and that a hostile actor may have edited
on disk. The landed U-W2.2 §18 discipline is adopted **verbatim**:

1. Explicit type check **before** every read; never a bare index or attribute
   access on a stored value.
2. A digest is **recomputed from the stored bytes** at every use, never trusted
   from a column.
3. An unreadable row never crashes a public boundary. `observe trace` renders
   the workflow with that row listed under `unreadable`, and continues.
4. Diagnostics are **bounded closed codes** only — never an excerpt, an offset,
   a length of the offending text, or a hash of it.
5. A stored value never becomes a path, a command, SQL, a tool input or a
   message.

Specific refusals, frozen:

| Condition | Behavior |
| --- | --- |
| `work_spec_document` is not canonical JSON | the workflow projects with `trace_root = "unresolvable"`; no span is emitted for it; doctor check 42 fails |
| `trace.trace_id` fails the 32-hex pattern, or is all zeros | same as above. **The value is never repaired, never re-derived, never substituted.** |
| `created_at` is not a real instant | that record's `Timestamp` is dropped; `ObservedTimestamp` is used per §6.3; the span carries `aos.clock.inconsistent = true` |
| `end < start` | duration `0`, `aos.clock.inconsistent = true` (§6.5) |
| a projection would exceed a §6.10 bound | the projection is **truncated at the bound and the truncation is reported** — never silently dropped, never expanded past the bound |
| a stored digest does not recompute | the row is listed in `observe verify`'s `divergent` array; it is not repaired, re-sealed or deleted |

**U-E1 never writes to `aos.db`. It cannot repair anything, and it never tries.**

---

## 11. Persistence and migration — the proof that neither is needed

### 11.1 The question, stated exactly

*Can existing append-only events carry U-E1 without schema v8?*

**Yes.** Proven below rather than asserted.

### 11.2 The proof

An observability layer needs, at minimum: a trace identity, a causal structure,
timings, and outcomes. Each is already durable:

| Need | Already durable at | Verified |
| --- | --- | --- |
| trace identity | `workflows.work_spec_document.trace`, sealed by `work_spec_sha256 UNIQUE` | §4.2, four facts |
| causal structure | `workflow_events` (`UNIQUE(workflow_id, seq)`, sealed), `workflow_attempts` (`UNIQUE(workflow_id, attempt_no)`), `workflow_checkpoints` | §5 |
| asserted time | `workflow_events.created_at` | §6.5 |
| **observed** time | base `events.ts`, one row per workflow event via `workflow_store._journal` | §6.5, §6.6 |
| outcomes | `workflows.state`, `workflow_attempts.state`, `workflow_facts` | §5.6 |
| span identity | **derivable** by domain-separated digest from the above | §4.4 |

Nothing remains. Every span, link, log record and metric point is a pure
function of rows that already exist.

### 11.3 The decision

| Item | Frozen |
| --- | --- |
| `db.SCHEMA_VERSION` | **stays `"7"`** |
| new tables | **none** |
| changed DDL constants | **none** |
| `db.WORKFLOW_TABLES` | **unchanged at eight** |
| migration steps | **stays six**; `MIGRATIONS` is not touched |
| `migrations.LATEST_VERSION` | **stays 7** |
| fresh-vs-migrated equivalence | **not applicable** — nothing changes |
| backup-first behavior | **not applicable** — no migration |
| failure atomicity | **not applicable** — U-E1 opens no write transaction |
| forced compatibility paths | **none** |
| `tests/fixtures/**` | **byte-unchanged** |
| historical fixture versions v1 / v2 / v3 | **untouched** |

### 11.4 What this buys, stated plainly

A schema bump would have forced version-literal edits across at least nine test
modules (`test_v02_migrations`, `test_v02_power_modes`, `test_core`,
`test_v03_memory_claims`, `test_v03_memory_graph`, `test_v04_agent_passports`,
`test_v04_agent_catalog`, `test_v04_routing_handoffs`,
`test_v04_workflow_store`), a `_V7_WORKFLOW_TABLES` freeze under the standing
obligation in `migrations._workflow_state_v6`'s docstring, a new
fresh-vs-migrated equivalence proof, and a migration failure-atomicity matrix.

**None of that is U-E1's work, because none of it is necessary.** The cheapest
correct design here is also the correct one — not because cost drove the
decision, but because the trace root genuinely was already durable and a new
table would have stored a second copy of it.

### 11.5 The obligation U-E1 inherits and does NOT trigger

`migrations._workflow_state_v6`'s docstring places an obligation on "a future
unit that edits `db.WORKFLOW_TABLES`". **U-E1 does not edit
`db.WORKFLOW_TABLES`**, so the obligation does not fire, and `_V6_WORKFLOW_TABLES`
is left exactly as U-W3 froze it.

---

## 12. The U-E6 boundary

### 12.1 The four-clause test

U-E1 may project over **rows as stored**. Folding is not the discriminator —
`workflow_store` already rebuilds every snapshot by folding `workflow_events`,
so "derives a view from history" would prove far too much.

**U-E1 must never:**

- **(a)** materialize an intermediate state at sequence *k* that no stored row
  asserts — that is reconstruction;
- **(b)** open any `document` or `payload_json` body beyond its digest and byte
  length, with the single §7.3 exception of four members of
  `work_spec_document`;
- **(c)** impose cross-process ordering, or assert any runtime-side timeline AOS
  did not observe;
- **(d)** answer "what would have happened" — no counterfactual, no
  re-simulation, no alternative-path analysis.

A change that violates any clause is `FAIL — GOVERNED REPLAN REQUIRED`, not a
feature.

### 12.2 Reserved to U-E6 by name

Flight recorder; deterministic replay; incident reconstruction; execution
re-simulation; causal-chain root-cause inference; before/after state diffing;
payload capture; cross-process clock reconciliation; retention, pruning and
compaction policy; time-travel query; "why did this fail" narrative synthesis.

### 12.3 What an operator explicitly cannot do until U-E6

- reconstruct the workflow's state at an arbitrary past instant;
- inspect any payload, prompt, document body or model output;
- correlate an AOS trace with a private-runtime task timeline;
- replay a workflow, or ask what a different decision would have produced;
- see anything about a private-runtime task attempt (§5.9).

---

## 13. Compatibility and versioning

| Question | Frozen answer |
| --- | --- |
| `protocols.REGISTRY_VERSION` | **unchanged at 1** |
| `protocols/**` schemas | **unchanged**; registry stays at **6** entries |
| `beast.*` protocol majors | **unchanged**; U-E1 widens nothing |
| new `aos.*` record schemas | exactly one, and it is never stored: `aos.observability-export/v1`, the export manifest (§9.5) |
| `PAYLOAD_SCHEMA_VERSION` (`events.py`) | **unchanged at 1** |
| `TRANSITION_POLICY_VERSION` | **unchanged at 2** |
| workflow commands / events / refusal reasons | **unchanged at 13 / 24 / 57** |
| `db.SCHEMA_VERSION` | **unchanged at `"7"`** |
| doctor checks | 41 → **43** |
| CLI leaves and `COMMAND_POLICY` | 112 → **116** |
| protected delivery gate | **unchanged** — the same four required checks |
| `pyproject.toml` | **untouched**; no dependency added |

---

## 14. Security posture

1. **No network.** No socket, no URL, no exporter endpoint, no collector.
2. **No credentials.** U-E1 reads no environment variable, no config file, no
   keychain, no token.
3. **No writes to `aos.db`.** The only file U-E1 writes is the export capsule,
   into an operator-named directory, and only from `observe export`.
4. **No execution.** No stored value becomes a path, a command, SQL, a tool
   input or a message (§10).
5. **No authorization surface.** No caller-supplied identifier grants, denies or
   influences anything (§4.5).
6. **Fail closed.** An unreadable row is reported and skipped; it never becomes a
   guess, a repair or a default.
7. **Refusal to overwrite.** `observe export` refuses a non-empty directory
   rather than merging.

---

## 15. Terminology

| Term | Means | Never means |
| --- | --- | --- |
| **trace root** | `work_spec_document.trace.trace_id` (§4.2) | any later caller-supplied trace |
| **foreign trace** | a `trace_id` carried anywhere other than `work_spec_document.trace` — a name for what U-E1 refuses to read (§4.3) | something to adopt, merge **or link**; there is no `foreign_trace` link kind (A1.2) |
| **span** | a U-E1-derived interval over stored rows | a stored row |
| **log record** | a U-E1-derived OTel LogRecord (§6.2) | a span event — U-E1 mints none |
| **event** | a log record with a non-empty `EventName` (source 3) | a fourth signal |
| **projection** | a value recomputed from stored rows on every read | a cached or persisted value |
| **observed time** | base `events.ts`, AOS's own clock | `workflow_events.created_at` |
| **event time** | `workflow_events.created_at`, caller-asserted | an observation |
| **workflow attempt** | a `workflow_attempts` row | a private-runtime task attempt |

---

## 16. Non-goals restated as refusals

| Someone will ask for | Answer |
| --- | --- |
| "just add the OTel SDK" | §3.5 — first third-party dependency ever; breaks distribution membership proofs |
| "push to our collector" | §2.2 — no network |
| "include the prompt, it's only in dev" | §7.3 — there is no flag; the grammar cannot express it |
| "add `workflow_id` as a metric label" | §7.6 — forbidden by name |
| "use span events, everyone does" | §3.5 — the API is deprecated (source 10) |
| "set the random-trace-id flag for compliance" | §4.6 — our ids are deterministic; the flag would be a lie |
| "store the spans so reads are fast" | §6.8 — U-E1 persists nothing; there is no read-performance problem to solve |
| "let `observe` fix the broken row" | §10 — U-E1 never writes to `aos.db` |
| "add `gen_ai.*` while we're here" | §3.6 — the conventions moved out of the core repo |

---

## 17. Exact path boundary

**The table below is CLOSED and EXHAUSTIVE. Seventeen paths — fifteen
implementation paths (1–15) plus two architecture documents (16–17).** A path
outside it appearing in any U-E1 wave is `FAIL — GOVERNED REPLAN REQUIRED`.
Nothing here is standing authority for any later wave or unit. There is no "as
needed", no "related files", no "supporting paths".

*Amended by A1.1: eleven → seventeen total, nine → fifteen implementation. The
six added paths are the doctor-count census files §17.3 rows 10–15 name, and
nothing else. D-v0.4.141.*

### 17.1 Production (5)

| # | Path | New/modified | Exact responsibility |
| --- | --- | --- | --- |
| 1 | `agentic_os/observability.py` | **NEW** | the whole projection: trace-root resolution, span/link derivation, log-record mapping, the five metrics, the OTLP/JSON serializer, the export capsule, and the bounds checks |
| 2 | `agentic_os/cli.py` | modified | one new top-level `observe` group with exactly four leaves and their handlers — and **no other region** |
| 3 | `agentic_os/power.py` | modified | exactly four `COMMAND_POLICY` entries as one contiguous block; no existing entry, kind, constant or helper changes |
| 4 | `agentic_os/doctor.py` | modified | exactly two checks **appended at the end**; no existing check, order or index changes |
| 5 | `README.md` | modified | exactly one new U-E1 unit section, placed after the U-W3 section; no other region |

### 17.2 New focused test (1)

| # | Path | Kind | Exact responsibility |
| --- | --- | --- | --- |
| 6 | `tests/test_v04_observability.py` | **NEW** | the §18 matrix, rows E1–E26 |

### 17.3 Forced existing-test edits (9)

*Amended by A1.1: three → nine. Rows 7–9 keep their identities with corrected
edit descriptions; rows 10–15 are the six paths the implementation wave proved.
D-v0.4.141.*

Each is mechanically forced by the frozen doctor count 41 → 43 or by the new
`derived_write` leaf, and each is bounded to exactly the named class of edit.

**The doctor-count census correction — the one authorized edit class.** For a
single test that pins the doctor check count or the doctor output line count, the
correction comprises, and comprises **only**:

- **(a)** the count literal `41` → `43`;
- **(b)** the test method's own name, where the name spells the count;
- **(c)** the co-located census comment or docstring chain, extended by `→ 43`
  naming U-E1's two appended checks;
- **(d)** where the *same* test also asserts a **tail-relative** window or a
  warn-only index census that the two appended checks displace, that identical
  assertion retargeted to positive indices, or extended by the appended index —
  never weakened, never deleted, never replaced by a looser bound.

Clause (d) exists because appending at the end moves the tail and only the tail:
`lines[-7]`, `checks[-4:]` and a warn-only index list are the three shapes that
notice. A positive index below 41 never moves, and §9.4's append-at-the-end rule
is what guarantees it.

| # | Path | Forced by | Exact edit |
| --- | --- | --- | --- |
| 7 | `tests/test_v04_agent_catalog.py` | doctor 41 → 43 | census correction on `DoctorCatalogTests.test_doctor_emits_exactly_41_checks_with_the_catalog_checks_at_35_37` (`len(checks)`) and `DoctorCatalogTests.test_doctor_check_count_matches_the_cli` (`len(lines)`, plus clause (d) on the three **negative-index** assertions `lines[-7]`, `lines[-6]`, `lines[-5]` → the positive indices naming the same three catalog checks), and on `EntrypointParityTests.test_doctor_is_byte_identical_with_41_lines_across_all_four_entrypoints` (`len(lines)`). The positive-index window `checks[34:37]` is **unchanged** |
| 8 | `tests/test_v04_routing_handoffs.py` | doctor 41 → 43 | census correction on exactly four tests — `Wave5RecoveryDeepEcoTests.test_doctor_emits_forty_one_with_governed_handoffs_present`, `Wave6SecretSweepTests.test_total_doctor_count_remains_41_not_42`, `Wave6DoctorMutationFreeTests.test_doctor_calls_no_write_or_event_api`, `Wave6DoctorOrderTests.test_clean_workspace_emits_exactly_41_checks` — being four count literals plus their names and censuses; **and clause (d) twice** in `Wave6DoctorOrderTests`: `checks[-4:]` → `checks[37:41]` in both assertions of `test_new_checks_append_last_in_contract_order`, and the warn-only index census `[16, 17, 18, 19, 23, 24, 33, 36, 39, 40]` extended by `42` (U-E1's warn-only check 43) in `test_legacy_checks_retain_names_order_and_severity`. In that same test the positive-index assertions `checks[0]`, `checks[17]`, `checks[31]`, `checks[34:37]` are **unchanged** |
| 9 | `tests/test_v02_power_modes.py` | the new `derived_write` leaf **and** doctor 41 → 43 | **two** bounded edits, both required: exactly one new `("observe", "export")` entry in the existing `RecoveryTests.BLOCKED` tuple; **and** the census correction on `DoctorIntegrationTests.test_doctor_check_count_is_forty_one` — clauses (a), (b) and (c), no clause (d) applies |
| 10 | `tests/test_cli.py` | doctor 41 → 43 | census correction on `TestDoctor.test_doctor_passes_on_clean_generated_demo` (`assertEqual(len(lines), 41)`, line 837). The `[WARN]`-count assertion below it is **unchanged**: both appended checks pass on that fixture |
| 11 | `tests/test_v02_secret_safety.py` | doctor 41 → 43 | census correction on `TestDoctorSecretSweep.test_clean_workspace_sweep_passes` (`assertEqual(len([…]), 41)`, lines 932–934). The sweep-line assertion above it is **unchanged** |
| 12 | `tests/test_v03_memory_claims.py` | doctor 41 → 43 | census correction on `DoctorTest.test_doctor_check_count_is_forty_one` (line 1536), including clause (b) — the method name spells the count |
| 13 | `tests/test_v03_memory_graph.py` | doctor 41 → 43 | census correction on `DoctorTest.test_doctor_check_count_is_forty_one` (line 2063), including clause (b). The unrelated `41`s in this file — decision reference `D-v0.3.41` and the `(41)` test-group markers — are **not** touched |
| 14 | `tests/test_v04_agent_passports.py` | doctor 41 → 43 | census correction on `DoctorTests.test_doctor_emits_exactly_41_checks` (line 1155), including clause (b). The positive-index assertions `lines[31]`, `lines[32]`, `lines[33]` are **unchanged** |
| 15 | `tests/test_weekend_views.py` | doctor 41 → 43 | census correction on `TestDoctorHardening.test_clean_weekend_workspace_passes_all_checks` (`assertEqual(len(lines), 41)`, line 671). The `[WARN]`-count and `T-0001` assertions below it are **unchanged** |

Nothing else in those nine files may be edited. No assertion is deleted, no
`subTest` dropped, no bound loosened, no test skipped, no fixture changed. Every
change is a member of the census-correction class above, or — in row 9 only — the
one `COMMAND_POLICY` tuple entry.

**Why exactly nine, and why Wave 0 said three.** Wave 0 checked the census that
is asserted *dynamically*: the completeness of `power.COMMAND_POLICY` versus
`power.iter_command_paths`, asserted in `tests/test_v02_power_modes.py`,
`test_v03_memory_claims.py`, `test_v03_memory_graph.py`,
`test_v03_protocol_spine.py`, `test_v03_retrieval_evals.py`,
`test_v04_agent_catalog.py`, `test_v04_routing_handoffs.py` and
`test_v04_workflow_cli.py`. That finding was correct and still holds: those
assertions **pass unchanged** once path 3 adds the four entries, no test pins the
total leaf count, and no test pins the literal top-level command set.

The error was generalizing it. The **doctor** count is not asserted dynamically —
it is pinned with static integer literals, in nine modules, six of which Wave 0
never enumerated. A dynamic census absorbs a new member; a literal does not. The
mechanical consequence is nine files, and the honest count is nine.

**Why the literals move and doctor does not.** The two appended checks are
correct, append at the end, and change no existing check, order or index (§9.4).
The failing assertions are stale pins on a number that a mandated new check is
*supposed* to move — the D-W8.1 pattern this repository has applied at every
earlier wave, cited in the very docstrings being corrected. Reverting doctor to 41
to keep six literals green would delete a frozen deliverable to protect a census.

### 17.4 Architecture documents (2)

| # | Path | Kind | Exact responsibility |
| --- | --- | --- | --- |
| 16 | `DECISIONS.md` | modified | the prepended U-E1 sections: the Wave 0 freeze D-v0.4.118 … D-v0.4.140, and above it the A1 replan D-v0.4.141 … D-v0.4.143. Everything below each prepend stays byte-identical |
| 17 | `agentic-os-v0.4-u-e1-observability-foundation-contract.md` | **NEW** | this contract, as amended by A1 |

### 17.5 Migration and schema paths

**There are none.** §11.3 freezes no schema change, so `db.py`, `migrations.py`
and `tests/fixtures/**` are outside the boundary entirely.

### 17.6 Permitted mechanical paths

Exactly the nine of §17.3, for exactly the edit classes named there. This
licence is **not standing**: a future unit meeting the same mechanical necessity
needs its own governed decision, and A1.1 is authority for these nine files and
this one 41 → 43 correction only.

### 17.7 Paths deliberately NOT changed, with the reason

| Path | Why not |
| --- | --- |
| `agentic_os/db.py`, `migrations.py`, `tests/fixtures/**` | §11 — no schema change |
| `agentic_os/protocols.py`, `protocols/**` | §13 — no protocol change; `Trace` is consumed exactly as landed |
| `agentic_os/workflow_engine.py`, `workflow_store.py` | U-E1 adds no command, event, refusal reason or write path; the projection reads through existing public accessors |
| `agentic_os/workspecs.py` | the trace derivation is U-W1's and is correct as landed |
| `agentic_os/events.py`, `models.py`, `utils.py`, `ids.py`, `secretscan.py` | no journal-framework, vocabulary or integrity change; `events.emit` is read, never called |
| `agentic_os/governance.py` | §5.7 — the governed-invocation evidence path has no live caller; giving it one is U-K1/U-T1's gap, not U-E1's |
| `agentic_os/backup.py`, `mirror_export.py`, `export.py`, `obsidian.py`, `pack.py` | no table is added, so no allowlist, manifest or row-count changes |
| `.github/workflows/ci.yml`, `tools/**`, `tests/test_v04_delivery_gate.py` | CI runs `unittest discover`; a new module is discovered without an edit. `tools/verify_ci_workflow.py` pins no CLI or doctor count |
| `pyproject.toml` | `packages = ["agentic_os"]` already includes the new module; no dependency, no package data |
| `AGENTIC_OS_BLUEPRINT.md`, `RECOVERY.md`, `TROUBLESHOOTING.md`, every landed contract | §2.2 — unrelated documentation cleanup is excluded |
| `/home/daksh/Projects/AICompany` | §2.2 — no private-runtime change |

### 17.8 Exact validation commands

**Focused (the U-E1 row set and every forced file — ten modules, amended by
A1.1 from four):**

```bash
cd /home/daksh/Projects/agentic-os-u-e1
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t tests -p 'test_v04_observability.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t tests -p 'test_v04_agent_catalog.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t tests -p 'test_v04_routing_handoffs.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t tests -p 'test_v02_power_modes.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t tests -p 'test_cli.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t tests -p 'test_v02_secret_safety.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t tests -p 'test_v03_memory_claims.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t tests -p 'test_v03_memory_graph.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t tests -p 'test_v04_agent_passports.py'
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t tests -p 'test_weekend_views.py'
```

The `discover -s tests -t tests` form is frozen deliberately: several test
modules import `fixtures.*`, and the bare `python3 -m unittest tests.<module>`
form fails those with `ModuleNotFoundError: No module named 'fixtures'`.

**Complete suite (acceptance only, never in Wave 0 or the build wave):**

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
python3 tools/verify_ci_workflow.py
python3 tools/gen_protocols.py && git diff --exit-code
```

### 17.9 The closed manifest — fifteen implementation paths

Sorted, unique, exhaustive. This is the manifest the evidence capsule carries;
it and the tables above must agree exactly.

```
README.md
agentic_os/cli.py
agentic_os/doctor.py
agentic_os/observability.py
agentic_os/power.py
tests/test_cli.py
tests/test_v02_power_modes.py
tests/test_v02_secret_safety.py
tests/test_v03_memory_claims.py
tests/test_v03_memory_graph.py
tests/test_v04_agent_catalog.py
tests/test_v04_agent_passports.py
tests/test_v04_observability.py
tests/test_v04_routing_handoffs.py
tests/test_weekend_views.py
```

Plus the two architecture documents of §17.4 — `DECISIONS.md` and this contract —
for **seventeen** total. A sixteenth implementation path or an eighteenth total
path is §19.1.

---

## 18. Test and runtime budget

### 18.1 Measured baseline (not assumed)

Every module timed individually on the U-E1 worktree at `f32fb00`, serial,
`PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -t tests -p '<module>.py'`:

| Metric | Value |
| --- | --- |
| discovered tests | **3215** across 28 modules |
| total serial wall clock | **1532.0 s (25.5 min)** |
| protected CI job timeout | **1800 s**, on all three test/distribution jobs |
| **remaining margin** | **268 s (14.9 %)** |
| 20 % profiling trigger | **306.4 s** |

Five slowest modules: `test_v02_windows_export` 282.0 s · `test_v04_workflow_cli`
198.7 s · `test_v04_workflow_store` 184.6 s · `test_v03_memory_graph` 148.5 s ·
`test_v02_power_modes` 98.2 s.

The session pack's "about 18 minutes" figure is **not reproduced**; the measured
value is 25.5 min. The measurement governs.

### 18.2 The inherited risk, stated

The suite already consumes **85 %** of the protected 30-minute job timeout, and
`tests/test_v04_delivery_gate.py:753` pins `timeout-minutes: 30` in exactly three
places — so the timeout cannot be raised without editing the protected delivery
gate, which §2.2 excludes.

**U-E1 neither caused this nor fixes it.** U-E1's obligation is to consume as
little of the remaining 268 s as possible, and to say so rather than discover it
in CI.

### 18.3 U-E1's budget — hard, not aspirational

| Item | Budget |
| --- | --- |
| `tests/test_v04_observability.py` | **≤ 60 s** (3.9 % of the suite; 22 % of remaining margin) |
| subprocess-invoking CLI cases in that module | **≤ 4** |
| every other case | in-process; no subprocess, no wheel build, no `venv` |
| the nine forced edits (§17.3) | **+0 s** — count literals, name and census text, and index retargets only; no new test, no new fixture, no new subprocess. A1.1 widens the *focused campaign* from four modules to ten, not the suite |
| projected complete suite | **≤ 1592 s = 88.4 %** of the job timeout |
| required margin after U-E1 | **≥ 200 s (11 %)** |

### 18.4 Why 4 subprocess cases

`test_v04_workflow_cli` spends **198.7 s on 43 tests — 4.6 s per test** because
it invokes the CLI as a subprocess. That single measurement sets the design rule:
U-E1's projection is a pure function over rows, so all but a handful of cases can
call it directly. Four subprocess cases (one per leaf, proving argv wiring, exit
codes and power gating) cost roughly 18 s; a subprocess-per-case module would
cost over 120 s and consume half the remaining margin.

### 18.5 Profiling trigger

Any single new test class exceeding **306.4 s** — 20 % of the projected suite —
must be profiled and justified before acceptance. Under §18.3's 60 s module
budget this is unreachable, which is the point: the budget is set an order of
magnitude below the trigger so the trigger never has to fire.

### 18.6 The acceptance matrix, frozen as row identities

`tests/test_v04_observability.py` implements exactly these twenty-six rows:

| Row | Proves |
| --- | --- |
| E1 | the trace root is the WorkSpec's `trace_id`, for author-supplied and compiler-derived alike |
| E2 | a later command/receipt/result carrying a different `trace_id` never re-roots the workflow (§4.3) |
| E3 | *(amended by A1.2)* **non-adoption and non-emission**: `foreign_trace` is absent from `observability.LINK_KINDS`, which is exactly `("retry_of", "restored_from", "compensates")`; no span's `trace_id`, no link's trace, no attribute, no log field and no exported byte carries a trace identity from outside the work-spec root, on a fixture whose result envelopes deliberately carry a different one; and the projection has exactly one source of `trace_id` |
| E4 | `span_id` is 16 lowercase hex, deterministic across two runs, and never all zeros |
| E5 | span ids differ across span kinds for the same workflow (domain separation holds) |
| E6 | the `random-trace-id` flag is clear on every emitted record (§4.6) |
| E7 | attempt 2 is a **sibling** of attempt 1 with a `retry_of` link, not a child |
| E8 | a cross-attempt `checkpoint_restored` emits a `restored_from` link; a same-attempt one does not |
| E9 | compensation is a child of the workflow span with a `compensates` link |
| E10 | `dispatch_rejected` / `dispatch_revoked` emit a workflow-span log record and open no attempt span |
| E11 | an `abandoned` attempt has span status **Unset**, not Error |
| E12 | a duplicate command, a redelivered receipt and a redelivered intent emit **nothing** |
| E13 | `approval_recorded` carries `aos.approval.scope` distinguishing admission from runtime |
| E14 | **no span event is ever emitted**; every event is a log record with `TraceId` + `SpanId` |
| E15 | `Timestamp`/`ObservedTimestamp` come from `created_at`/`events.ts` respectively and differ when the caller lies |
| E16 | `end < start` yields duration 0 and `aos.clock.inconsistent = true`; no negative duration is representable |
| E17 | every attribute key matches §7.2's grammar and every value is one of the six admitted types |
| E18 | the forbidden-content list (§7.3) appears **nowhere** in any signal or export, including a workflow whose goal, checkpoint payload and `reason.message` all contain distinctive sentinel text |
| E19 | no `document` column other than `work_spec_document` is parsed, and only four members of that one are read |
| E20 | the five metrics have exactly the frozen names, units, instrument kinds and dimensions; the series ceiling is 67 |
| E21 | `reason_code`, `queue_route`, `actor` and every identity in §7.6's list are absent from every metric dimension |
| E22 | metrics are cumulative from ledger genesis and recomputing after more events never decreases a Sum |
| E23 | malformed persisted rows (§10's table) are reported, never repaired, and never crash a public boundary |
| E24 | the four leaves exist with exactly the frozen options and exit codes; `verify` exits 0 on divergence |
| E25 | power: `observe export` is blocked in recovery and skipped in eco; the three read-only leaves run in all four modes |
| E26 | `observe export` refuses a non-empty directory, writes LF, seals the manifest, and opens no socket |

---

## 19. Replan triggers

Any of the following is `FAIL — GOVERNED REPLAN REQUIRED`, not a bounded repair:

1. An **eighteenth** repository path is needed — or a **sixteenth**
   implementation path (§17.9). *Amended by A1.1 from "a twelfth"; the count
   moved once, under D-v0.4.141, and this trigger is what fires if it is asked to
   move again.*
2. A schema change turns out to be necessary after all.
3. Any protocol schema, registry entry or `beast.*` major must change.
4. A new workflow command, event, refusal reason or policy version is needed.
5. Any write to `aos.db` is needed.
6. Any dependency must be added.
7. Any network call is needed.
8. Any clause of §12.1's U-E6 test would be violated.
9. `tests/test_v04_observability.py` cannot meet the 60 s budget.
10. A forced test edit outside §17.3's **nine** files and named edit classes is
    needed — including any edit to a doctor-count census file that is not a
    member of the (a)–(d) correction class.
11. Any free-text value must be admitted into the attribute grammar.
12. The trace root must come from somewhere other than `work_spec_document`.

---

## 20. Known limitations, stated rather than hidden

1. **Second-precision timing.** Every duration is quantized to 1 s and a
   fast workflow measures 0 s. Fixing this requires a sub-second clock format,
   which is a change to `utils.utc_now_iso()` and therefore to every timestamp in
   the ledger — far outside U-E1.
2. **Event time is caller-asserted.** `workflow_events.created_at` comes from the
   command, not from AOS. §6.5 exposes both times so an operator can see the
   disagreement; U-E1 cannot resolve it.
3. **No runtime-side visibility.** Private-runtime task attempts, leases, backoff
   and queue latency are invisible (§5.9). That is U-W2.R's absent adapter, not
   U-E1's gap.
4. **No cross-process correlation.** Clause (c) of §12.1 forbids it; it is U-E6's.
5. **The base journal is not trace-bound outside workflows.** A migration,
   backup or pack-build log record has no `TraceId`, because no trace root exists
   for it. Inventing one would be manufacturing identity.
6. **Waiting states `waiting_input` and `paused` have no live producer**
   (U-W3 §8.4), so their log records are unreachable in wave 1. They are defined
   so the mapping is total, not because they are exercised.
7. **The suite is at 85 % of the CI timeout before U-E1** (§18.2). Inherited.

---

## 21. What ships in the implementation wave

Exactly paths **1–15** of §17 (the §17.9 manifest), implementing exactly §§4–10
and §18.6's twenty-six rows. No architecture change, no schema change, no
full-suite run, no Git history mutation, no GitHub activity. Anything else is §19.

*Amended by A1.1 from "paths 1–9". Two obligations are authorized here and
outstanding in the implementation as of the A1 replan: the six doctor-count
census corrections of §17.3 rows 10–15, and the A1.2 foreign-trace correction —
removing `foreign_trace` from `observability.LINK_KINDS` and its constant, and
retargeting §18.6 row E3 onto non-adoption **and** non-emission. Until both land
and the focused campaign of §17.8 passes, the implementation wave is not PASS.*
