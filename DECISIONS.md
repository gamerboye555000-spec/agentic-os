# DECISIONS — Agentic OS v0.4 U-E6 flight recorder, deterministic replay, and incident forensics (governed replan A1)

This section continues the `D-v0.4.*` series for the U-E6 **governed replan**,
which resolves one contradiction the implementation wave proved inside the U-E6
Wave 0 freeze itself. Architecture only — exactly two repository paths are
written, `DECISIONS.md` and
`agentic-os-v0.4-u-e6-flight-recorder-replay-contract.md`, and no implementation
or test byte is touched in this session. Branch `v0.4-u-e6-flight-recorder-replay`,
worktree `/home/daksh/Projects/agentic-os-u-e6`, baseline
`6da12ed251011f8597afc9495aa7c2f8da568234` (= HEAD). Prepended per the same
precedent the Wave 0 section cites (D-W0.4, D-v0.2.7, D-v0.4.4, D-v0.4.103) and
the U-E1 replan made concrete (D-v0.4.141 … D-v0.4.143); everything below stays
byte-identical, including the whole Wave 0 section D-v0.4.144 … D-v0.4.162 and
D-v0.4.1 … D-v0.4.143.

The Wave 0 section's §14 (D-v0.4.161) fixed the implementation boundary at
exactly fourteen paths and forbade every other path. That remains true of every
**landed** contract and decision. It is no longer true of U-E6's own freeze:
D-v0.4.163 retires the fourteen-path clause because §5's own mandated leaves
force two baseline test files to move, and D-v0.4.164 records the supersession
boundary so a later reader is not left to infer which text still governs.

## D-v0.4 decisions (U-E6, governed replan A1)

- **D-v0.4.163 — the recovery guard and the CLI census are static pins, and
  the six frozen leaves move both, so the U-E6 boundary expands from fourteen
  to sixteen implementation paths.** Wave 0 verified that the
  `power.COMMAND_POLICY` versus `power.iter_command_paths` classification
  census is asserted *dynamically* in a dozen modules and therefore absorbs
  U-E6's five new leaves unchanged — correct, and still true. It then
  generalized that finding to two other censuses, which are **not** dynamic:
  both are pinned with static literals, and both break mechanically the moment
  §5's six leaves are wired into `cli.py` and `power.py` per §5's own power
  classifications.

  The first is the recovery guard. `tests/test_v02_power_modes.py`'s
  `RecoveryTests.BLOCKED` tuple is asserted by
  `test_every_blockable_command_is_covered_by_the_block_list` to cover **every**
  live CLI leaf whose kind is not in `power.RECOVERY_ALLOWED_KINDS`, and the
  same bidirectionality is re-asserted by
  `tests/test_v04_workflow_cli.py:PowerTests.test_the_blocked_list_covers_the_new_leaves`
  (which imports `RecoveryTests.BLOCKED`). §5 classifies `flight-record create`,
  `incident create` and `incident export` as `DERIVED_WRITE`, which is
  intentionally not recovery-allowed — so the guard requires all three to appear
  in `BLOCKED`, and `test_v02_power_modes.py` is not on the frozen U-E6 §14
  list.

  The second is the CLI leaf census. `tests/test_v04_observability.py`'s
  `test_e24_the_cli_leaf_census_moved_from_112_to_116` pins
  `len(leaves) == 116` and `len(power.COMMAND_POLICY) == 116` with static
  integer literals. U-E6 adds five parser leaves — `("flight-record", "create")`,
  `("flight-record", "verify")`, `("replay",)`, `("incident", "create")`,
  `("incident", "export")` (`replay --resimulate` is a flag on `("replay",)`,
  not a leaf) — so the census moves to **121**, and `test_v04_observability.py`
  is also not on the frozen U-E6 §14 list.

  These two pins cannot be satisfied by §5's own deliverable without editing
  their files, and the frozen §14 (D-v0.4.161) forbids editing them. The ruling,
  mirroring D-v0.4.141's census correction: the boundary expands from fourteen
  implementation paths to **sixteen**, and each added path carries exactly **one**
  authorized correction class:
  - `tests/test_v02_power_modes.py` — add exactly the three non-recovery-safe
    leaves to `RecoveryTests.BLOCKED`, each with an argv following the existing
    pattern: `(("flight-record", "create"), ("flight-record", "create", "WF-1",
    "--out", "SELF"))`, `(("incident", "create"), ("incident", "create", "WF-1",
    "--out", "SELF"))`, `(("incident", "export"), ("incident", "export", "WF-1",
    "--out", "SELF"))`. Nothing else in the file may be edited; no existing
    entry, bound or assertion changes. The paired
    `test_recovery_blocks_every_authoritative_and_derived_mutation` iterates
    `BLOCKED` and needs no separate edit.
  - `tests/test_v04_observability.py` — in
    `test_e24_the_cli_leaf_census_moved_from_112_to_116`: the count literals
    `116` → `121`, the test method name where it spells the count
    (`_moved_from_112_to_116` → `_moved_from_116_to_121`), and the co-located
    census comment or docstring. Nothing else in the file may be edited, no
    assertion is deleted and no bound is loosened.

  `tests/test_v04_workflow_cli.py` needs **no** edit: its guard imports
  `RecoveryTests.BLOCKED` from `test_v02_power_modes` and is satisfied
  automatically once `BLOCKED` is extended, and its own
  `test_recovery_blocks_ten_and_permits_three` `blocked` list is
  workflow-prefixed only. This decision authorizes **no seventeenth path and no
  expansion escape hatch**: the frozen §14 clause now fires on a seventeenth
  implementation path, and on any edit to a census or guard file that is not a
  member of the named correction class. The count moved once, under this
  decision, and the trigger exists to stop it moving again. §5's classifications
  are not re-litigated: the three file-writing leaves stay `DERIVED_WRITE` (and
  therefore blocked in recovery), `flight-record verify` and `replay` stay
  `READ_ONLY`.

- **D-v0.4.164 — the replan supersedes only U-E6's own clauses, and the
  corrections it authorizes are pending, not done.** The clauses retired are,
  in the contract: §14's "No other paths", its "exactly these 14 paths"
  enumeration and its closed twelve-path block, §15's "None at freeze"; and in
  this file, the "fourteen authorized implementation paths" clause of
  D-v0.4.161. Every other clause of the Wave 0 freeze stands, and **no landed
  contract, decision or behavior is touched** — amending one's own freeze under
  a governed decision is not the same act as amending a landed one, and the
  distinction is kept rather than blurred. Two obligations are authorized here
  and **outstanding in the implementation**: the three-entry `BLOCKED`
  extension in `tests/test_v02_power_modes.py`, and the `116` → `121` census
  correction in `tests/test_v04_observability.py`. No test ran in the replan
  session and no implementation byte changed, so the build wave is **not** PASS
  and is not recorded as one. An architecture that has been re-frozen is not an
  implementation that has been re-verified.

---

# DECISIONS — Agentic OS v0.4 U-E1 observability foundation (governed replan A1)

This section continues the `D-v0.4.*` series for the U-E1 **governed replan**,
which resolves two contradictions the implementation wave proved inside the U-E1
Wave 0 freeze itself. Architecture only — exactly two repository paths are
written, `DECISIONS.md` and
`agentic-os-v0.4-u-e1-observability-foundation-contract.md`, and no
implementation or test byte is touched in this session. Branch
`v0.4-u-e1-observability-foundation`, worktree
`/home/daksh/Projects/agentic-os-u-e1`, baseline
`f32fb005869e3567d24e12f054d672c1ef0d0e39` (= HEAD). Prepended per the same
precedent the Wave 0 section cites (D-W0.4, D-v0.2.7, D-v0.4.4, D-v0.4.103);
everything below stays byte-identical, including the whole Wave 0 section
D-v0.4.118 … D-v0.4.140 and D-v0.4.1 … D-v0.4.117.

The Wave 0 section states that U-E1 supersedes nothing at all. That remains true
of every **landed** contract and decision. It is no longer true of U-E1's own
freeze: D-v0.4.141 and D-v0.4.142 each retire a clause the implementation wave
proved unsatisfiable, and D-v0.4.143 records the supersession boundary so a later
reader is not left to infer which text still governs.

## D-v0.4 decisions (U-E1, governed replan A1)

- **D-v0.4.141 — the doctor-count census is nine files, not three, so the closed
  boundary is seventeen paths.** Wave 0 verified that the `power.COMMAND_POLICY`
  versus `power.iter_command_paths` census is asserted *dynamically* in eight
  modules and therefore absorbs U-E1's four new leaves unchanged — correct, and
  still true. It then generalized that finding to the **doctor** count, which is
  not dynamic: it is pinned with static integer literals. §9.4 moves doctor from
  41 to 43 checks, and six modules Wave 0 never enumerated break mechanically on
  that literal — `tests/test_cli.py:837`, `test_v02_secret_safety.py:932`,
  `test_v03_memory_claims.py:1536`, `test_v03_memory_graph.py:2063`,
  `test_v04_agent_passports.py:1155` and `test_weekend_views.py:671`, each one
  assertion, each `43 != 41`. The boundary therefore expands from eleven paths to
  **seventeen** — fifteen implementation paths plus the two architecture
  documents — and each added path carries exactly **one** authorized doctor-count
  census correction: the count literal, the test method name where it spells the
  count, the co-located census comment or docstring, and (only where the same
  test asserts a tail-relative window) that identical assertion retargeted to
  positive indices. Nothing else in those files may be edited, no assertion is
  deleted and no bound is loosened. Doctor stays at **43**: the two appended
  checks are a frozen deliverable that appends at the end and moves no existing
  index, and the failing literals are stale pins on a number a mandated new check
  is *supposed* to move — the D-W8.1 pattern, cited in the very docstrings being
  corrected. Reverting doctor to 41 would delete a deliverable to protect a
  census. This decision authorizes **no eighteenth path and no expansion escape
  hatch**: §19.1 now fires on an eighteenth total or sixteenth implementation
  path, and §19.10 fires on any edit to a census file that is not a member of the
  named correction class. The count moved once, under this decision, and the
  trigger exists to stop it moving again.

- **D-v0.4.142 — `foreign_trace` leaves the active link-kind vocabulary, because
  no valid U-E1 projection can emit it.** D-v0.4.122 required a `trace_id`
  observed outside `work_spec_document.trace` to be represented as a span link.
  D-v0.4.137 forbids U-E1 from parsing `workflow_receipts.document`,
  `workflow_facts.document`, `workflow_intents.document`,
  `workflow_checkpoints.document` and `report_document` — which are the **only**
  places a foreign trace could ever be learned. The two decisions cannot both be
  satisfied: the emission half of D-v0.4.122 is unreachable by construction, and
  the implementation correctly declined to invent a reachable path to it. The
  ruling, seven clauses: the authoritative trace root remains
  `work_spec_document.trace.trace_id`; U-E1 inspects no receipt, result,
  checkpoint, fact or report body for trace identities; a trace outside that root
  is **neither adopted nor emitted** — not as a span's `trace_id`, a link's
  trace, an attribute, a log field or an exported value; `foreign_trace` is
  **removed** from the active vocabulary, leaving exactly `retry_of`,
  `restored_from` and `compensates`; §18.6 row E3 proves **both** halves,
  non-adoption and non-emission, plus the single-source property; the three
  preserved kinds are unchanged, since narrowing the vocabulary changes no link
  that is actually produced; and a future governed cross-runtime adapter may
  introduce verified foreign-trace links under a separate contract, which will
  have to supply the two things U-E1 lacks — an authorized read path to the body
  carrying the foreign trace, and a rule for verifying it. **An active link kind
  that no valid projection can emit is not preserved as decoration.** It is a
  false promise to every consumer that reads the vocabulary as a feature list,
  and a standing invitation to a later implementer to "finish" it by opening a
  document body §7.3 forbids. The term "foreign trace" survives as terminology,
  because operators still need a name for what U-E1 refuses to read; naming a
  refusal is not keeping a link kind for it. This narrows D-v0.4.122 and leaves
  D-v0.4.121, D-v0.4.123 and D-v0.4.137 intact — indeed D-v0.4.137 is the reason
  the narrowing is forced.

- **D-v0.4.143 — the replan supersedes only U-E1's own clauses, and the
  corrections it authorizes are pending, not done.** The clauses retired are, in
  the contract: §1.2's "Nothing", §17's "Eleven paths", §17.3's three-file limit
  and its "Why only three" reasoning, §17.6's "Exactly the three", §18.3's "the
  three forced edits", §19.1's twelfth path, §19.10's "three files", §21's "paths
  1–9", §4.3's `foreign_trace` link rule, §4.5 rule 3, §15's "foreign trace" row
  and the original §18.6 row E3; and in this file, the "eleven paths" clause of
  D-v0.4.119 and the emission half of D-v0.4.122. Every other clause of the Wave 0
  freeze stands, and **no landed contract, decision or behavior is touched** —
  amending one's own freeze under a governed decision is not the same act as
  amending a landed one, and the distinction is kept rather than blurred. Two
  obligations are authorized here and **outstanding in the implementation**: the
  six doctor-count census corrections, and the A1.2 correction removing
  `foreign_trace` from `observability.LINK_KINDS` and retargeting row E3's
  assertion off `assertIn("foreign_trace", LINK_KINDS)` onto non-adoption and
  non-emission. No test ran in the replan session and no implementation byte
  changed, so the build wave is **not** PASS and is not recorded as one. An
  architecture that has been re-frozen is not an implementation that has been
  re-verified.

---

# DECISIONS — Agentic OS v0.4 U-E1 observability foundation (Wave 0)

This section continues the `D-v0.4.*` series for the U-E1 Wave 0 architecture
freeze: OpenTelemetry-compatible traces, metrics and structured logs for the
local Agentic OS control plane, grounded in U-X1 identities and U-W3 workflow
attempt semantics. Architecture only — no production code, tests, DDL,
migrations, fixtures, CLI handlers, power entries, protocol schemas or README
prose ship in this commit. Branch `v0.4-u-e1-observability-foundation`, worktree
`/home/daksh/Projects/agentic-os-u-e1`, baseline
`f32fb005869e3567d24e12f054d672c1ef0d0e39` (= HEAD = `origin/main` = the
merge-base = `milestone/v0.4-u-w3-runtime-recovery^{}`). Prepended per the
established precedent (D-W0.4, reaffirmed in D-v0.2.7, D-v0.4.4, D-v0.4.103);
everything below stays byte-identical, including D-v0.4.1 … D-v0.4.117.

Like U-W3, this freeze writes **no amendment into any landed contract file**.
Unlike U-W3, it also supersedes nothing at all: every supersession U-E1 might
have needed was dissolved by D-v0.4.119, which found the identity U-E1 requires
already durable in the ledger. The two authorized repository paths are
`DECISIONS.md` and `agentic-os-v0.4-u-e1-observability-foundation-contract.md`.

## D-v0.4 decisions (U-E1, Wave 0 architecture freeze)

- **D-v0.4.118 — "OpenTelemetry-compatible" means the bytes, not the
  dependency.** U-E1 freezes an internal canonical representation whose field
  names, types and semantics are those of the OpenTelemetry data models and W3C
  Trace Context, serialized on request as OTLP/JSON, such that a conformant
  consumer can read it without this project importing, linking, vendoring or
  depending on any OpenTelemetry artifact. Compatibility is a property of what
  we write, not of what we load. The alternative — taking the SDK — would add
  the first third-party runtime dependency this project has ever had, and the
  distribution smoke job currently proves the wheel and zipapp contain exactly
  the source tree and nothing else. A telemetry library is not worth spending
  that proof on, and it buys nothing the byte format does not already buy.

- **D-v0.4.119 — the trace root already exists, so U-E1 needs no schema
  change.** `trace` is in `protocols._ENVELOPE_REQUIRED`, so every valid WorkSpec
  carries one; when the author supplies none, `workspecs._derive_defaults` mints
  `trace_id` as a domain-separated SHA-256 prefix guarded against all-zeros; and
  `workflows.work_spec_document` stores the admitted artifact verbatim under
  `work_spec_sha256 UNIQUE`. The trace identity an observability layer must have
  is therefore already durable, immutable, digest-bound and tamper-evident
  before U-E1 exists. `db.SCHEMA_VERSION` stays `"7"`, the migration chain stays
  at six steps, no DDL constant changes, `db.WORKFLOW_TABLES` stays at eight, and
  `tests/fixtures/**` stays byte-unchanged. This decision is the reason the whole
  unit is eleven paths instead of twenty-one: a new table would have stored a
  second copy of a value the ledger already seals.

- **D-v0.4.120 — U-E1 persists nothing, and that is a design, not a
  shortcut.** Every span, span id, link, log record, metric point and exported
  document is recomputed from stored rows on every invocation. The consequences
  are all deliberate: no cache to invalidate, no accumulator to reset, no
  divergence between stored and computed telemetry, no retention or pruning
  policy, no unbounded growth, and no new failure mode in any write path —
  because U-E1 has no write path into `aos.db` at all. The one durable/derived
  boundary that matters was settled by D-v0.4.119; everything on the derived side
  stays there.

- **D-v0.4.121 — one workflow, one trace, fixed at admission.** A workflow's
  trace identity is `work_spec_document.trace.trace_id` for the whole life of the
  workflow, and every span of that workflow shares it. A `trace` legally appears
  on commands, receipts, result envelopes and intent bodies too, and those values
  are independent of each other — one workflow can accumulate four different
  trace identities. Choosing the WorkSpec's is not arbitrary: it is the only one
  sealed by a content digest at admission and incapable of being rewritten
  afterwards.

- **D-v0.4.122 — a foreign trace is a link, never an adoption.** A `trace_id`
  observed anywhere other than `work_spec_document.trace` is represented as a
  span link carrying that foreign trace, and never as the AOS span's own
  `trace_id`. U-E1 never merges, re-roots, reconciles or prefers a foreign trace.
  Links across traces are exactly what the OpenTelemetry link concept is for;
  adoption would silently splice unrelated traces together and would hand any
  caller the ability to attach its own trace to somebody else's workflow.

- **D-v0.4.123 — identity laundering is prevented by making the identifier
  decide nothing.** No U-E1 trace, correlation, causation or span value ever
  selects a row, authorizes an action, dedupes a command, gates a transition,
  orders history or changes any output other than its own rendering. An
  identifier that decides nothing cannot launder anything. The other four rules —
  root fixed at admission, foreign traces as links, all-zero guards on both axes,
  and no baggage — are hygiene around that one load-bearing property.

- **D-v0.4.124 — W3C's own rule for an invalid traceparent is adopted:
  restart, never repair.** The Recommendation of 23 November 2021 says a vendor
  receiving an invalid `traceparent` "creates a new `traceparent` header and
  deletes `tracestate`". U-E1 follows it: a `trace_id` that fails the 32-hex
  pattern or is all zeros is never patched, re-derived, substituted or partially
  accepted. The workflow projects with an unresolvable trace root, no span is
  emitted for it, and doctor reports it. Repairing a malformed identity would be
  inventing provenance, which D-v0.3.43 already refused in another form.

- **D-v0.4.125 — span ids are derived, and the `random-trace-id` flag is
  therefore never set.** `span_id` is the first 16 lowercase hex characters of a
  domain-separated SHA-256, with an all-zero guard mirroring
  `workspecs._guard_trace_id`, and one frozen tag per span kind. No RNG and no
  clock is read, so the same ledger yields the same span ids forever. Trace
  Context Level 2 (Candidate Recommendation Draft, 28 March 2024) requires that
  when the `random-trace-id` flag is set, "at least the right-most 7 bytes of the
  `trace-id` MUST be selected randomly". Our identifiers are deterministic by
  construction, so the flag stays clear — asserting it would be a false claim
  about our own data, and a later implementer who "improves" this would be adding
  a lie, not a feature.

- **D-v0.4.126 — retry is a sibling with a link, not a child.** Attempt 2 is
  not work performed inside attempt 1; it is work performed because attempt 1
  ended. Nesting would make attempt 1's duration include attempt 2's, which is
  false, and would make a ten-attempt workflow a ten-deep tree, which is
  unreadable. A sibling attempt span carrying a `retry_of` link states the causal
  edge without lying about containment.

- **D-v0.4.127 — checkpoint restoration is a link, because it is
  cross-attempt.** `checkpoint_restored` may restore a checkpoint belonging to a
  different `attempt_no` than the attempt restoring it. Recording it only as an
  event on the restoring attempt would erase the single causal edge connecting
  attempt N+1 back to attempt N's checkpoint — the exact edge an operator opens
  a trace to find. A cross-attempt restore emits a `restored_from` link in
  addition to its log record; a same-attempt restore emits only the record.

- **D-v0.4.128 — every event is a log record; U-E1 mints no span events.** All
  twenty-four workflow events, plus every projected base-journal row, become
  OpenTelemetry LogRecords carrying `TraceId` and `SpanId`. OpenTelemetry
  deprecated the span-event API and its guidance is "Prefer the Logs API for new
  events and exceptions." Both shapes serialize into OTLP today and both carry
  trace and span identity, so choosing log records costs nothing now and avoids
  founding a brand-new contract on a deprecated surface. Following the logs data
  model, a record with a non-empty `EventName` **is** an Event — there is no
  fourth signal and none is implemented.

- **D-v0.4.129 — a replay observes as nothing.** A duplicate command, a
  redelivered receipt, a redelivered intent, a lock wait and a private-runtime
  task-attempt retry each emit no span, no log record and no metric increment.
  U-W3 already establishes that none of them appends an event or changes state.
  Telemetry that manufactured a signal for them would claim more things happened
  than happened, which is the specific way observability layers start lying.

- **D-v0.4.130 — an abandoned attempt is not an error.** A `workflow_attempts`
  row in state `abandoned` gets span status **Unset**, not Error. It was
  abandoned by cancellation; nothing failed. Marking it Error would make every
  cancelled workflow read as a failure in every downstream tool, which is the
  same category mistake D-v0.3.22 and D-v0.3.44 refused for doctor checks.

- **D-v0.4.131 — both times are exposed, and neither is dressed up.**
  `workflow_events.created_at` is **copied from the caller's command** and is the
  OpenTelemetry `Timestamp`; the base `events.ts` row that `workflow_store._journal`
  writes in the same transaction comes from `utils.utc_now_iso()`, the codebase's
  only wall-clock read, and is the `ObservedTimestamp`. Both are second-precision
  RFC3339. They are converted to nanoseconds because the data model requires it,
  and the contract states outright that the low nine digits are always zero
  rather than implying a precision this system does not have.

- **D-v0.4.132 — no monotonic duration exists, and none is invented.** This
  codebase has no monotonic clock. Duration is `end − start` over caller-asserted
  second-precision instants, clamped at zero. A span whose end precedes its start
  carries `aos.clock.inconsistent = true` and duration 0; a negative duration is
  unrepresentable. Exposing the skew is honest; hiding it behind a fabricated
  monotonic reading would not be.

- **D-v0.4.133 — metrics are cumulative from ledger genesis, which designs the
  three hard problems out.** Every metric is a scan of an append-only ledger, so
  a reset is impossible (there is no accumulator), a gap is impossible (every
  point covers genesis-to-now), and a double count is impossible
  (`UNIQUE(workflow_id, seq)` plus D-v0.4.129). Delta temporality was refused
  because it requires a durable accumulator and therefore a reset model, and the
  OpenTelemetry resets-and-gaps machinery is still Development-status — and their
  own versioning policy says long-term dependencies should not be taken against
  signals in Development.

- **D-v0.4.134 — the metric inventory is five metrics and sixty-seven series,
  computed rather than asserted.** `aos.workflow.count` (14 states),
  `aos.workflow.event.count` (24 events), `aos.workflow.attempt.count` (4 attempt
  states), `aos.workflow.checkpoint.count` (no dimensions) and
  `aos.workflow.transition.duration` (24 events) sum to sixty-seven series at
  most. Every dimension is drawn from a vocabulary already frozen in code, so the
  ceiling cannot grow with the number of workflows, tasks, attempts, agents,
  projects or operators — only a governed decision adding a vocabulary member can
  move it.

- **D-v0.4.135 — `reason_code` is never a metric dimension.** It is not one of
  the fifty-seven frozen refusal reasons; it is a slug the runtime chooses,
  bounded only by `^[a-z][a-z0-9_]{2,63}$`. As a dimension it would be unbounded
  cardinality and, worse, a sixty-four-character channel through which an
  external system could write arbitrary content into AOS telemetry. It stays a
  span and log attribute, alongside `queue_route` and `actor`, which are
  classified for the same reason and excluded from dimensions on the same rule.

- **D-v0.4.136 — privacy is structural, not filtered.** The attribute grammar
  admits exactly six value types: a member of a closed vocabulary already frozen
  in code, an identity matching a frozen pattern, a SHA-256 digest, a bounded
  integer, an RFC3339 instant, and a boolean. **There is no free-text value
  type.** A prompt, a goal, an acceptance criterion, a `reason.message`, a
  checkpoint payload or a model output cannot be expressed — not "is filtered
  out", but cannot be expressed. `secretscan.redact_tree` still runs at the
  export boundary as defence in depth, and log record `Body` is always empty.
  There is no flag that reveals more, because a flag is exactly how this control
  would be lost.

- **D-v0.4.137 — no document column is opened, with one four-member
  exception.** `report_document`, `workflow_intents.document`,
  `workflow_receipts.document`, `workflow_facts.document` and
  `workflow_checkpoints.document` are never parsed by U-E1. `work_spec_document`
  is parsed to read exactly `trace.trace_id`, `trace.correlation_id`,
  `trace.causation_id` and `data_classification`, and nothing else. Everything
  else is referenced by its digest. This is what makes D-v0.4.136 checkable by a
  reviewer rather than merely promised.

- **D-v0.4.138 — no baggage, in either direction.** U-E1 defines, reads, writes
  and propagates none, and treats no caller-supplied value as an authorization,
  trust or access-control input. OpenTelemetry's own documentation states there
  are no built-in integrity checks to ensure baggage items are yours, and that
  baggage is unassociated with span, metric and log attributes unless explicitly
  copied. It therefore offers no integrity and no automatic benefit to offset the
  risk — and treating it as trusted would be precisely the laundering D-v0.4.123
  exists to prevent.

- **D-v0.4.139 — the U-E6 line is four clauses, because "derives a view from
  history" would prove too much.** `workflow_store` already rebuilds every
  snapshot by folding `workflow_events`, so folding cannot be the discriminator.
  U-E1 may project over rows as stored, and must never: materialize an
  intermediate state at a sequence no stored row asserts; open any document or
  payload body beyond its digest and byte length, save D-v0.4.137's exception;
  impose cross-process ordering or assert a runtime-side timeline AOS never
  observed; or answer what would have happened. Flight recording, deterministic
  replay, incident reconstruction, re-simulation, payload capture, time-travel
  query and retention policy stay reserved to U-E6 by name.

- **D-v0.4.140 — the runtime budget is measured, and the inherited margin is
  reported rather than absorbed.** The full suite was timed module by module at
  this baseline: 3215 tests, 1532.0 s serial, against a protected 1800 s job
  timeout pinned in three places by the delivery gate — 85 % consumed, 268 s
  left. The session pack's "about 18 minutes" is not reproduced and the
  measurement governs. `tests/test_v04_observability.py` is therefore capped at
  60 s with at most four subprocess cases, because `test_v04_workflow_cli` spends
  198.7 s on 43 tests — 4.6 s each — proving that subprocess CLI cases are the
  expensive class and that a pure projection has no excuse to use many. U-E1
  neither caused the thin margin nor repairs it: raising the timeout would mean
  editing the protected delivery gate, which is out of scope.

---

# DECISIONS — Agentic OS v0.4 U-W3 workflow runtime recovery (Wave 0)

This section continues the `D-v0.4.*` series for the U-W3 Wave 0 architecture
freeze: bounded workflow retry, checkpoint persistence, state-restoration
resume, and compensation under transition-policy version 2. Architecture only —
no production code, tests, DDL, migrations, fixtures, CLI handlers, power
entries, protocol schemas or README prose ship in this commit. Branch
`v0.4-u-w3-runtime-recovery`, worktree `/home/daksh/Projects/agentic-os-u-w3`,
baseline `fef0c2b3fd8e881776b33e7a2c5d204f8e8d34c1` (= HEAD = the merge-base =
`milestone/v0.4-u-w2-3-workflow-cli^{}`). Prepended per the established
precedent (D-W0.4, reaffirmed in D-v0.2.7, D-v0.4.4); everything below stays
byte-identical, including D-v0.4.1 … D-v0.4.102, which the decisions here
supersede only where they quote them and never reword.

Unlike U-W2.2's A1 and U-W2.3's A3, this freeze writes **no amendment into any
landed contract file**. U-W3 is a different unit, not a later U-W2 wave, and the
U-W3 session is authorized to write exactly two repository paths — `DECISIONS.md`
and `agentic-os-v0.4-u-w3-runtime-recovery-contract.md`. Every supersession U-W3
needs is therefore declared inside its own contract's §1.2, and the superseded
documents are left byte-identical. That is not a weaker mechanism: U-W2 §5.3 and
§15 already pre-authorised transition-policy version 2, its state additions and
its storage widening, so U-W3 is exercising a licence rather than overriding a
clause.

## D-v0.4 decisions (U-W3 Wave 0)

- **D-v0.4.103 — U-W3's authority is a pre-granted licence, and the three
  attempt namespaces are separated by name, by source of truth, and by owner
  before anything else is decided.**

  Three landed clauses grant the whole unit: U-W2 §5.3 ("Transitions reserved
  for U-W3: the three `R` edges, plus reinterpreting `partial`/`unknown`
  outcomes — all activate only via transition-policy version 2"), U-W2 §15
  (policy version 2 is U-W3's, state additions are additive under a new policy
  version plus a widened storage CHECK plus frozen retention of every prior
  version's table), and U-W2 §12.2 gate 4 (a failing envelope "is stored
  verbatim as a fact and NOT acted on (compensation is U-W3's)"). U-W3 ships
  what those clauses reserved and nothing else.

  Three attempt concepts were previously one word. Frozen apart: a
  **runtime task attempt** is a row in the private runtime's `task_attempts`,
  numbered by `attempt_number`, produced by its `QueueWorker`, retried by
  `_is_retryable_failure` and delayed by `retry_backoff_seconds` (30 s doubling,
  capped at 300 s) — none of which AOS counts, bounds, mirrors or models. A
  **workflow attempt** is one AOS-decided, AOS-recorded execution of the
  admitted WorkSpec, ordinal `attempt_no`, whose source of truth is
  `workflow_events` and whose projection is the new `workflow_attempts` table.
  The **attempt budget** is `work_spec_document.retry.max_attempts`, digest-bound
  and admission-immutable, defaulting to 1 — the landed `_handle_record_result`
  default, unchanged.

  The rule that resolves every collision between them: **AOS counts what AOS
  observed.** A runtime requeue on a transient failure or a lease expiry moves
  `running → pending → running` inside the runtime's plane, emits no AOS receipt,
  and consumes no workflow attempt. U-W3 therefore adds no `attempts`,
  `next_visible_at`, `lease`, `worker`, `locked_by` or `backoff` column anywhere
  in `aos.db`, and duplicates nothing the private runtime already owns.

  The private-runtime facts were reproduced directly against
  `d6f4a82aeb3e08d8067250489343e4242b35d07d`, not assumed: a production
  `QueueWorker` exists; `task_queue`/`task_attempts` persistence, lease ownership
  (`locked_by`, `locked_at`, `lease_expires_at`) and fencing
  (`claim_next_task`, `finalize_task`, `schedule_task_retry`,
  `requeue_expired_tasks`, `fail_exhausted_tasks`) exist; task-attempt retry and
  backoff exist; approval (`park_task_for_approval`, `resume_approved_task`,
  `reject_task_for_rejected_approval`) and spend planes exist; and there is **no
  AOS intent reader, no AOS receipt writer, no U-W2.R adapter, no checkpoint
  machinery, no compensation machinery and no cancellation implementation** —
  zero matches for `work_spec`, `agentic_os`, `checkpoint` or `cancel` across
  `libs/`, `services/` and `agents/`, and `TASK_STATUSES` is
  `pending, running, succeeded, failed, rejected, requires_approval` with
  `ck_task_queue_status` admitting nothing else. **What is absent is the AOS
  intent/receipt translation adapter — not the worker.** The superseded
  "no worker" claim is not repeated anywhere in this freeze.

- **D-v0.4.104 — transition-policy version 2 is a fourteen-state matrix with
  thirty-five active edges and zero reserved edges; policy v1's thirteen-state
  tuple and 13×13 table are frozen verbatim as history; `partial`/`unknown` are
  deliberately NOT activated; and adoption of v2 is GATED, never unconditional.**

  `TRANSITION_POLICY_VERSION = 2`, `SUPPORTED_POLICY_VERSIONS = (1, 2)`.
  `_POLICY_MATRICES` carries `(version, state tuple, matrix)` triples so every
  lookup indexes with its own version's states and a v1 event can never
  re-derive under v2 rules — the `_V2_MEMORY_CLAIM_DDL` frozen-history trade,
  applied to policy data exactly as U-W2 §15 requires.

  All **three** reserved edges activate, and the count is three, not two:
  `running → compensating` (`res:compensable`), `compensating → compensated`
  (`cmp:applied`), and `compensating → failed` (`cmp:failed` / `rcp:failed`) —
  the last being the one edge a v1 caller could attempt, which is why
  `transition_reserved` stays reachable for policy-v1 snapshots and is never
  emitted for a v2 one. `compensating → cancelled` remains illegal in every
  frozen version, verbatim.

  Ten new edges: five `* → retrying` (from `scheduled`, `running`,
  `waiting_input`, `waiting_approval`, `paused`), `retrying → scheduled`,
  `retrying → cancelled`, plus the three activations. v2's active-edge set is a
  **strict superset** of v1's — every v1 edge survives with the same driver —
  asserted cell by cell. That property establishes exactly one thing, and the
  earlier draft of this decision over-claimed from it: the superset makes
  adoption **transition-safe**, meaning no move that was legal under v1 becomes
  illegal under v2. It says **nothing** about the attempt ledger, which is a
  second and independent obligation, so "adoption is always safe" is withdrawn
  and replaced by the gate below.

  **`partial` and `unknown` are not activated.** §5.3 reserved the
  reinterpretation to v2; it did not require v2 to exercise it. They are honest
  statements of ignorance, U-W3 cannot know what was partially done, and
  retrying partial non-idempotent work is exactly the hazard U-W1's
  `retry_idempotency_incompatible` lint exists to flag. Turning a producer's
  uncertainty into an AOS claim about the world is the one thing this
  architecture never does. They still refuse `result_outcome_inconclusive` and
  mutate nothing; reinterpreting them later is a declared replan trigger.
  U-W2 §12.2's forward-looking wording that policy v2 "will widen"
  `partial`/`unknown` handling is explicitly and narrowly superseded (contract
  §1.2 row S15): v2 activates neither, both remain refused, activating either
  requires a governed replan, and no other §12.2 behavior is superseded by that
  row.

  **The fourteenth state, `retrying`, is mechanically forced, not a naming
  preference.** A workflow whose attempt N failed retryably with attempts
  remaining cannot be `failed` (terminal, structurally immutable), cannot be
  `running` (it would claim a live runtime task that does not exist), and cannot
  be `validated` — because the landed `workflows` DDL carries
  `CHECK (runtime_task_uuid IS NULL OR state NOT IN ('compiled','validated','awaiting_approval'))`,
  so storing it as `validated` requires destroying the only record of which
  runtime task attempt N was. Reusing `validated` would also re-open
  `request_approval` mid-retry and conflate "never attempted" with "attempt 1
  failed". `retrying` is added under §15's additive rule: new policy version,
  widened storage CHECK via a migration, frozen retention of v1's table.

  A workflow's policy version is fixed at admission and is moved only by an
  explicit, forward-only, non-terminal-only `adopt_policy_version` command that
  changes no state, appends one `policy_version_adopted` event carrying both
  versions, and consumes one revision. Without it every landed v1 workflow would
  be permanently un-retryable, because the identity is derived from the WorkSpec
  digest and re-admission refuses `workflow_exists`; with a silent upgrade
  instead, the ledger would rewrite what a workflow was decided under. There is
  no downgrade, no `--force`, no batch adopt and no implicit adoption inside any
  other verb.

  **Adoption is additionally gated by a three-condition safety predicate**
  (contract §5.2.1), because policy v2 decides retry, checkpoint, restore and
  compensation against an authoritative record of which attempt is open, which
  runtime task it bound and how many attempts are used — a record policy v1
  never kept. Adoption is permitted only when the workflow **(A1)** is
  pre-dispatch **as folded** — `runtime_task_uuid` NULL, `attempts_used` 0, no
  `workflow_attempts` row, and no outstanding `dispatch_intent_id`, so nothing is
  reserved-and-pending, opened or consumed (a *revoked* or *rejected* dispatch
  materialised nothing and `fold` clears the binding, so it leaves the workflow
  pre-dispatch again); or **(A2)** is terminal and can consume no further
  attempt; or **(A3)** already carries complete, internally consistent policy-v2
  `workflow_attempts` history. Anything else refuses
  `policy_version_not_upgradable` — no new code, the existing policy-adoption
  vocabulary.

  The refusal this creates is deliberate and is the point of the correction: a
  **landed policy-v1 workflow in an active post-dispatch state must refuse
  adoption when authoritative workflow-attempt history is absent** — `scheduled`,
  `running`, `waiting_input`, `waiting_approval`, `paused`, and for totality
  `retrying` and `compensating`, which no v1 workflow can reach because
  `retrying` is not in the v1 state tuple and no v1 driver targeted
  `compensating`. Adopting there would fold `attempts_used` to 0 for work already
  performed, renumber the next dispatch as attempt 1, orphan the live runtime
  task, and leave every attempt-fenced fact refusing with no honest way forward.
  Under the shipped `SUPPORTED_POLICY_VERSIONS = (1, 2)`, A1 is the only live
  path: A2 is stated for totality but is reached by nothing, since the landed
  non-terminal conjunct refuses first with `workflow_terminal`; and A3 is
  unreachable, since attempt rows exist only under v2 and there is no forward
  step out of 2 — which is also why the predicate needs no stored-row judgment
  and no new `ShellFacts` member.

  **Nothing may be manufactured to satisfy it.** `workflow_attempts` rows are
  never synthesized from historical events, and `attempt_no` is never inferred
  from event sequence, receipt sequence, `runtime_task_uuid` or current workflow
  state. A v1 history records that a dispatch was accepted; it does not record
  which ordinal that acceptance was, and no arithmetic recovers what was never
  written. The operator's path is `revoke-dispatch` then adopt for an outstanding
  reservation, and — for a workflow that already consumed an attempt — running to
  a terminal state under v1 and admitting new work as a new WorkSpec.

- **D-v0.4.105 — a workflow attempt is RESERVED at an accepted dispatch and
  CONSUMED only at an observed acceptance; the failed receipt that closes an
  attempt must carry that attempt's own runtime-task binding; one runtime task
  can never serve two attempts of one workflow; and the WorkSpec-vs-runtime
  budget divergence is declared and refused, never reconciled.**

  Reservation records `attempt_no = attempts_used + 1` and the budget in the
  `dispatch_requested` payload and emits the intent, but creates no
  `workflow_attempts` row and consumes nothing. The `accepted` receipt inserts
  the row (`state='open'`, `runtime_task_uuid`, `opened_seq`) and sets
  `attempts_used := attempt_no`. A `rejected` or `revoked` dispatch materialises
  nothing, so a re-dispatch reuses the same ordinal with a new `intent_id` and a
  new `idempotency_key`.

  Two reasons, both mechanical rather than stylistic. Burning a budget slot on a
  queue rejection would permanently strand a default-budget-1 workflow on a
  single adapter error. And assigning at acceptance is what keeps
  `attempt_no ≤ budget ≤ 10` always true, which is what makes the reported
  `attempt` satisfiable against `beast.result-envelope/v1`'s
  `{"minimum": 1, "maximum": 10}` — a monotone never-reused ordinal would not be.

  The four attempt-row states are `open`, `succeeded`, `failed`, `abandoned`;
  at most one row per workflow is `open`, and the biconditional
  `CHECK ((state = 'open') = (closed_seq IS NULL))` makes both halves of the
  contradiction unstorable. The row receives exactly two writes: the opening
  INSERT and one compare-and-swap fenced on `state = 'open'` with a required
  rowcount of 1 — the `_close_intent` discipline, so a second close is
  impossible and no reverse transition exists.

  **The budget divergence.** The WorkSpec defaults `max_attempts` to 1; the
  private runtime's `TaskQueueRecord` defaults it to 3. With U-W2.R absent
  nothing transports the artifact's value into `task_queue.max_attempts` — a
  human does, or does not. Frozen: AOS's budget is the artifact's, always; the
  v2 dispatch intent states `attempt_no` and `attempt_budget` explicitly so a
  human enqueuer has the number in front of them; AOS never asserts, checks or
  repairs the runtime row; a result reporting `attempt != open attempt_no`
  refuses `attempt_mismatch` and one reporting `attempt > budget` refuses the
  landed `result_attempt_exceeded`; nothing is recorded, no attempt is
  renumbered, no budget is widened, and the workflow parks for a human. **No
  automatic repair may fabricate authority or evidence.** This makes U-W2 §22's
  declared limitation stricter under v2, not looser, and that is deliberate: an
  attempt number that names nothing is not accounting.

  Two bindings close the attempt ledger. First, a `failed` receipt participates
  in the ledger only as the attempt it closes: whether it closes the open
  attempt, consumes it, drives retry classification, or concludes a
  compensation, it must carry `runtime_task_uuid` equal to the
  `workflow_attempts.runtime_task_uuid` binding recorded for that attempt — a
  receipt that binds no attempt of this workflow refuses `receipt_unbound`, one
  that names a different attempt's task refuses `runtime_uuid_mismatch`, both
  landed codes; the receipt record shape, the nine kinds and every database
  CHECK are unchanged, and policy-v1 replay stays unchanged and permissive for
  historical rows, because the binding is a policy-v2 acceptance gate, never a
  replay-time re-judgment. Second, one runtime task is one workflow attempt:
  `workflow_attempts` carries `UNIQUE(workflow_id, runtime_task_uuid)` — the
  column is NOT NULL, a row existing only because an `accepted` receipt
  supplied the binding, so NULL-distinct UNIQUE semantics never arise — and an
  `accepted` receipt offering a uuid already bound to a prior attempt of the
  same workflow refuses `runtime_uuid_mismatch` before anything is stored, the
  check made against the folded `dispatch_accepted` history so it is
  event-authoritative.

  **`dispatch_accepted` version compatibility, frozen**, because that event is
  the one landed name whose new member is load-bearing for this ledger. Under
  policy v2 `attempt_no` is **mandatory**: a v2 `dispatch_accepted` that could
  not carry it is not written at all. Under historical policy-v1 replay it may be
  **absent**, and that absence is correct, complete history — v1 never numbered
  workflow attempts — so the required-member set for this event is
  policy-version conditional. `fold` therefore reads the member through an
  explicit presence check and never `payload["attempt_no"]`: a v1
  `dispatch_accepted` binds the runtime task, moves the state, advances no
  counter, opens no attempt, and raises no `KeyError`, so a v1 history folds
  forever. An **absent** `attempt_no` under policy v2 refuses, using the existing
  policy-adoption and attempt-binding vocabulary — `receipt_unbound` for an
  acceptance with no recorded v2 reservation to number it,
  `policy_version_not_upgradable` for the adoption that would have created the
  situation — and **no value is fabricated**: not from event sequence, receipt
  sequence, `runtime_task_uuid`, current state, or a count of prior acceptances.
  No `workflow_attempts` row is ever synthesized from historical events either.
  A refusal that names the gap is worth more than an ordinal that names nothing.

- **D-v0.4.106 — retry identity reuses every landed derivation formula
  unchanged, and retry is distinguished from six things it is not.**

  D-v0.4.91's definition governs verbatim: U-W3 retry is re-execution of work
  that advances an attempt counter, is bounded by `retry.max_attempts`, and
  changes what the workflow claims about the world. U-W3 introduces **no new
  derivation formula**: `intent_id` stays
  `uuid8(sha256(TAG_INTENT ‖ 0x00 ‖ "<work_spec_sha256>:<intent_seq>"))` and the
  idempotency key stays `"wfd-" + sha256(TAG_DISPATCH_IDEM ‖ …).hex()[:40]`,
  both keyed on the per-workflow `intent_seq`.

  Because `intent_seq` advances, attempt 2 derives a different idempotency key
  and the runtime's `task_queue.idempotency_key UNIQUE` therefore admits it as a
  genuinely new task row. That is correct — a retry *is* a new runtime task —
  and it is exactly the situation that must never become invisible. Three
  defences: the v2 dispatch intent carries `attempt_no` and `attempt_budget` as
  required members, so a second file announces itself as "attempt 2 of N"; it
  carries `supersedes_runtime_task_uuid` whenever a prior attempt bound one, so
  the chain is readable from the files alone; and `workflow_attempts` records
  exactly one runtime task per consumed attempt, so a task AOS never accepted
  has no attempt row and reads as an orphan. Retry classification is
  attempt-fenced: the failing fact that parks a workflow in `retrying` — or
  exhausts its budget — must first bind the attempt it closes, an envelope
  through `attempt` equal to the open `attempt_no`, a `failed` receipt through
  `runtime_task_uuid` equal to that attempt's recorded binding
  (`receipt_unbound` / `runtime_uuid_mismatch`, per D-v0.4.105). A receipt from
  a task AOS never accepted for the attempt can therefore neither consume a
  budget slot nor drive a retry.

  Retry is distinguished, each with an explicit "no attempt, no event, no state
  change" row, from: SQLite lock waiting (the already-configured `timeout=5.0` +
  `PRAGMA busy_timeout=5000`, D-v0.4.91); duplicate command replay (the
  `command_id` axis, which re-verifies the original events under the full §7.2
  gate before answering); intent redelivery (content-addressed, idempotent, and
  collapsed runtime-side by `idempotency_key UNIQUE`); receipt redelivery (the
  `receipt_id` axis); private-runtime task-attempt retry (`attempt_count` plus
  backoff, invisible to the ledger); and `revision_mismatch`, which forces a new
  `command_id` and therefore a fresh recorded decision.

- **D-v0.4.107 — "checkpoint" is a different word from "snapshot", and a
  checkpoint is an append-only, bounded, attempt-bound, opaque document AOS
  never produces, never interprets and never prints.**

  `aos.workflow-snapshot/v1` stays U-W2.2's derived workflow projection. U-W3's
  artifact is `aos.workflow-checkpoint/v1`, bounded execution-restoration state
  produced outside AOS. The two words are never interchanged and U-W3 mints no
  second "snapshot".

  Frozen: identity is a **producer-supplied** UUID, because AOS mints no
  identity for a document it did not produce; ledger identity is
  `(workflow_id, checkpoint_id)`. Binding is fourfold — `workflow_id`,
  `work_spec_sha256`, the open `attempt_no`, and that attempt's
  `runtime_task_uuid`. Producer authority is the executing side only. The
  `payload` is an **opaque canonical object**: AOS validates canonical parse,
  the spine's bounds, the size limit and the secret scan, and never reads a key.
  Limits are derived rather than tuned — `MAX_CHECKPOINT_PAYLOAD_BYTES = 65536`
  is a quarter of `protocols.MAX_ARTIFACT_BYTES`,
  `MAX_CHECKPOINTS_PER_ATTEMPT = 8`, and `MAX_CHECKPOINTS_PER_WORKFLOW = 80` is
  `8 × 10`, the per-attempt bound times the protocol's frozen attempt ceiling, so
  no third number is introduced. The digest is the self-excluding
  `content_sha256` idiom, **recomputed from stored bytes at every use**.

  The table is **INSERT-ONCE**: no `UPDATE` and no `DELETE` targets it after its
  creating transaction's own row-hash finalization. An identical redelivery is a
  `replay`; a same-`checkpoint_id` different body refuses `checkpoint_conflict`;
  `checkpoint_seq` is monotone from 1 within an attempt. Nothing is ever pruned.

  **A secret-shaped payload is REFUSED at ingest and never stored** — not
  redacted, because a redacted checkpoint is an unrestorable lie, and not
  stored-then-warned, because that would put a plaintext credential in `aos.db`.
  AOS holds no key and neither encrypts nor decrypts; whole-database protection
  stays the operator's concern, and the scan is a prophylactic rather than a
  cryptographic guarantee. A corrupt checkpoint is **reported** in
  `divergent_rows` and made permanently `checkpoint_ineligible`, never repaired,
  re-sealed or deleted. No checkpoint payload is ever printed — not by `show`,
  not by `--json`, not in an event payload, not in a refusal, not in the
  journal.

- **D-v0.4.108 — three different things were all called "resume"; they are
  separated by fact, by event and by owner, and a `run_resumed` event is never
  proof that a checkpoint was restored.**

  **A. Queue resumption** is U-W2's landed `resumed` receipt and its
  `run_resumed` event: it proves the runtime left a wait state, and nothing
  more. **B. Checkpoint restoration** is U-W3's `aos.workflow-restore-fact/v1`,
  recorded by `record_restore`, evidenced by a `checkpoint_restored` event that
  carries `checkpoint_id`, `checkpoint_sha256`, `from_attempt_no`,
  `into_attempt_no` and `restored_by`. **C. The semantic resume instruction** is
  `beast.interrupt/v1`'s `kind: "resume_instruction"` and
  `resume_instruction_ref`, reserved to U-W5 and read by nothing in U-W3.

  Frozen rules: `fold` derives no restoration member from `run_resumed`, no
  U-W3 predicate reads it as one, and a `resumed` receipt with no preceding
  `checkpoint_restored` is a wait exit full stop; `checkpoint_restored` changes
  no state at all; and U-W3 reads no `beast.interrupt/v1` document, imports
  nothing that parses one, and never dereferences `resume_instruction_ref` —
  with `interrupt` and `resume` both staying banned tokens in the CLI region.

  A restore is *requested* in the dispatch that opens the next attempt
  (`request_dispatch`'s v2 payload key `restore_checkpoint_id`, resolved by the
  store into `ShellFacts` because a pure reducer cannot read a stored row) and
  *recorded* when the executing side reports it. Eligibility is five conjuncts,
  all required: the checkpoint belongs to this workflow; its stored digest
  recomputes; its `attempt_no` is **strictly less** than the attempt being
  opened; the workflow is under policy v2; and the workflow is non-terminal and
  in `retrying`, `scheduled` or `running`. Restoration is ineligible in
  `compensating` and in every terminal state — compensation undoes, it does not
  resume. Recording is additionally attempt-bound on both ends: the restore
  fact's `into_attempt_no` must equal the open attempt (`attempt_mismatch`),
  and its `from_attempt_no` must equal the stored checkpoint's own `attempt_no`
  (`restore_fact_unbound`) — the checkpoint digest alone is insufficient,
  because a digest proves which bytes were restored, not which attempt they
  captured.

- **D-v0.4.109 — compensation authority is a verified result envelope and
  nothing else; descriptive manifest metadata is never execution authority; and
  compensation has exactly two terminal outcomes, no retry and no partial
  record.**

  The reducer was structurally blind to compensation because U-W2 §12.2 gate 4
  deliberately stored the envelope's `compensation` block verbatim and left it
  unread. U-W3 reads it, and only it. **Explicitly and mechanically not
  authority**: `beast.tool-manifest/v1`'s `compensation.strategy =
  "compensating_action"` and `compensation.ref` (a reversibility *declaration*),
  its `recovery.action = "invoke_compensation"` (a declared hint, whose sibling
  `recovery.note` the schema itself calls "display-only prose … never parsed,
  matched or executed"), its `cancellation`, `idempotency` and `retry`, and
  U-W1's `retry_idempotency_incompatible` finding. No U-W3 code path reads a
  tool manifest, a skill manifest, an agent passport, a compile-report finding
  or a `recovery.action` to decide whether, when or how to compensate, and an
  AST import scan proves the absence.

  **Declaration versus execution.** `beast.work-spec/v1` has no `compensation`
  property at all, so a WorkSpec cannot declare compensability; only the
  executing side can report it. That asymmetry is declared as a known
  limitation, not papered over by inferring a declaration from a manifest.

  Trigger: `record_result` with `outcome = "fail"` and
  `compensation.state = "pending"` drives `running → compensating`, emits
  `compensation_started`, and emits one `compensate` intent — the third
  `WORKFLOW_INTENT_KINDS` member — carrying the failing result's digest and the
  envelope's own opaque `compensation.ref` when present, which AOS never
  dereferences. Entering compensation closes the ledger behind it:
  `res:compensable` closes the currently open attempt as `failed`, preserving
  the failing result digest as the authoritative trigger, so `compensating`
  never holds an open attempt. Compensation **outranks** retry: undoing a
  partial effect before re-running is the only safe order. `success` +
  `pending` is `result_inconsistent`; `applied`/`failed` on a first result is
  `compensation_state_inconsistent`.

  Exactly two terminal outcomes: `compensated` (`cmp:applied`, gated by the same
  §12.2 counted-evidence predicate as `succeeded`, applied to the compensation
  envelope — one rule, one existing code, no new vocabulary) or `failed`
  (`cmp:failed`, or a `failed` receipt), whose event is named
  `compensation_failed` so "the work failed" and "the undo failed" are never
  confused in the history. The conclusion is bound to the attempt it concludes:
  a compensation conclusion envelope's `attempt` is **mandatory and
  authoritative** — a required property of the shipped
  `beast.result-envelope/v1` — and must equal the attempt
  `compensation_started` recorded, the **compensating attempt**; a mismatch
  refuses `attempt_mismatch`, whose meaning there explicitly names the
  compensating attempt, not an open one.

  The earlier draft of this decision claimed the envelope "carries no
  `runtime_task_uuid` member". That is factually wrong and is corrected here:
  the **shipped** `beast.result-envelope/v1` lists `runtime_task_uuid` among its
  `properties` and omits it from `required`, so the protocol permits it as an
  **optional** property. Frozen semantics, reached without touching the
  protocol: the uuid is **corroborating evidence, never a selector**. When
  present it must equal the `workflow_attempts` binding for the compensating
  attempt — in reducer terms the binding folded from that attempt's
  `dispatch_accepted`, of which the row is the projection — and a present
  mismatch refuses `runtime_uuid_mismatch`, a landed code, recording nothing.
  When absent, nothing is refused and nothing is inferred, because an optional
  property left out is a legal envelope, not a defect. It never selects the
  attempt, never initiates compensation and never grants execution authority: an
  envelope carrying a correct uuid and a wrong `attempt` still refuses. And a
  present mismatching value is **never ignored** — silently dropping evidence
  that contradicts the ledger is the same failure as accepting evidence
  fabricated to agree with it. Uuid-level *binding*, the kind that closes an
  attempt, still exists only on the receipt path (D-v0.4.105); this is a
  contradiction check, not a second authority, and the same
  present-must-match / absent-is-fine rule governs the execution-result path so
  the model carries one rule rather than two.

  There is **no compensation retry** (a failed
  compensation is terminal), **no partial compensation** (the protocol's enum
  has no `partial` member; partial undo must be reported `failed`, and a
  producer that reports `applied` for partial work is making a false claim AOS
  cannot detect), and **no compensation checkpoint**. Interruption recovers by
  redelivering the same content-addressed intent file, never by emitting a
  second intent.

- **D-v0.4.110 — schema version 7 is two new tables plus four rebuilt closed
  enums; `workflow_facts` and `workflow_receipts` are byte-untouched and U-W3
  adds no fact kind; and the frozen-v6-DDL obligation the 5→6 step wrote down
  fires in full.**

  `workflow_attempts` and `workflow_checkpoints` are new; `workflow_attempts`
  additionally carries `UNIQUE(workflow_id, runtime_task_uuid)`, so one runtime
  task can never be stored as two attempts of the same workflow — the storage
  backstop for D-v0.4.105's acceptance gate, with no NULL ambiguity because the
  column is NOT NULL. `workflows`,
  `workflow_events`, `workflow_commands` and `workflow_intents` are rebuilt
  because SQLite cannot ALTER a CHECK and each carries a closed enum that must
  widen (`retrying`; the seven new event names; the four new verbs;
  `compensate`). Rows are copied **verbatim** with `content_sha256` carried
  across untouched, so every landed row hash and every sealed event digest stays
  valid by construction. `workflows`' `runtime_task_uuid` CHECK is deliberately
  left alone — `retrying` is absent from its exclusion list, which is precisely
  what lets a retrying workflow keep the runtime binding of its failed attempt.

  **No new fact kind.** A compensation conclusion *is* a
  `beast.result-envelope/v1`, so it is stored by the existing path as
  `fact_kind = 'result'`, and the `compensation_applied`/`compensation_failed`
  event's `result_sha256` identifies which stored body it is — D-v0.4.86's own
  "the event is the authoritative fact; the table holds the body the event
  records only by digest". `UNIQUE(workflow_id, 'result', document_sha256)`
  admits both bodies because their digests differ. Widening `fact_kind` would
  force a rebuild of a table U-W3 otherwise never touches and buy nothing the
  digest join does not already give. A restore fact needs no stored body either:
  every member the event does not already carry is a digest or a validated
  identifier, which U-W2 §7 permits in a payload.

  The 6→7 step rebuilds four tables and creates two **empty** ones directly
  under their real names; it reads no clock, stamps no row, derives nothing, and
  invents no attempt or checkpoint for any pre-existing workflow. The two new
  tables are therefore **byte-identical** fresh-vs-migrated; the four rebuilt
  ones are **structurally identical**, the same distinction D-v0.3.43 drew for
  `memory` and `agents`.

  `migrations._workflow_state_v6`'s docstring states the transfer rule — "A
  future unit that edits `db.WORKFLOW_TABLES` inherits the obligation to freeze a
  `_V6_WORKFLOW_*` copy here, exactly as `_V2_MEMORY_CLAIM_DDL` did" — and U-W3
  edits that tuple, so it fires. The freeze must cover **all six** v6 DDL texts,
  not only the four U-W3 amends, because the 5→6 step iterates the whole tuple
  and a partial freeze would still let it build v7-shaped `receipts`/`facts`
  tables and stamp `schema_version = 6`. `tests/fixtures/**` need **no edit**:
  all three fixtures drop the workflow tables by iterating
  `db.WORKFLOW_TABLES` in reverse and say so explicitly, so an eighth table is
  picked up automatically, children first.

- **D-v0.4.111 — the retry attempt ceiling of 10 remains normative in all five
  live places, and no protocol schema widens; the intent record gets a `/v2`
  and the private snapshot does not.**

  `10` stays exactly as shipped in `beast.work-spec/v1.retry.max_attempts`,
  `beast.result-envelope/v1.attempt`, `beast.tool-manifest/v1.retry.max_attempts`,
  `workspecs._check_retry` and `governance.validate_execution_context`. U-W3
  introduces **no sixth ceiling constant**: the reducer bounds `attempt_no` by
  the artifact's own budget, which admission already proved is ≤ 10, and the
  storage `CHECK (attempt_no BETWEEN 1 AND 10)` restates the protocol's number
  rather than inventing one. `protocols/**` and `agentic_os/protocols.py` are
  byte-unchanged and `tools/gen_protocols.py` must leave the tree clean.
  Changing 10 anywhere requires an explicit protocol compatibility decision, a
  `registry_version` bump and a new schema `/vN` — a replan trigger, never a
  silent widening.

  Among the `aos.*` internal records — which U-W2 §13.4 deliberately keeps out
  of the U-X1 registry — `aos.workflow-queue-intent` advances to `/v2` while
  `aos.workflow-snapshot` stays `/v1` despite gaining members. The distinction is
  not convenience: the intent is the one record that **crosses the trust boundary
  as a file** and that U-W2 §18 requires U-W2.R to pin by content hash, so
  changing its accepted member set is exactly what a version number announces;
  the snapshot never leaves the process that built it, has one producer and one
  consumer inside this repository, and is re-derived on every command. v1 intents
  keep being emitted for v1 workflows and keep being read forever.
  `aos.workflow-checkpoint/v1`, `aos.workflow-restore-fact/v1` and the two new
  `*-row/v1` hash identities are new; the nine receipt kinds stay frozen and
  U-W3 adds none.

- **D-v0.4.112 — U-W3 adds four flat leaves to the existing `aos workflow`
  group (seventeen total) and no retry leaf; SIX U-W2.3 test rows are
  superseded and exactly two are narrowed, with thirteen of C26's fifteen
  tokens kept region-wide and the exemption closed at SEVEN named functions.**

  Not a nested group: `power._PATH_DESTS` is
  `("command", "subcommand", "subsubcommand")`, so a third level would change how
  every leaf-path predicate in `tests/test_v02_power_modes.py` and U-W2.3 C1
  reads. Not "no CLI": with U-W2.R absent the CLI is the only way a record
  crosses the boundary, so a U-W3 with no CLI would be architecture nobody could
  run. The four are `adopt-policy`, `checkpoint`, `restore` and `compensate`,
  all `authoritative_write, ledger`, giving 13 / 3 / 1 across seventeen leaves
  and four new `RecoveryTests.BLOCKED` rows.

  **There is no retry leaf, deliberately**: a retry *is* `workflow dispatch`
  issued from `retrying`, and the existing leaf gains one optional
  `--restore CHECKPOINT_ID`. A second verb for a dispatch would create two ways
  to do one thing and would put the token `retry` into the CLI region for no
  gain. All four new leaves reuse the landed `_workflow_write` shell verbatim, so
  there is still **exactly one `workflow_store.submit(` call site**, and the
  region still calls exactly the same six store functions with `rebuild` still
  absent — `verify` covers the two new tables internally and reports through the
  existing `divergent_rows` tuple, so no `VerifyReport` field and no read
  function is added.

  Superseded, exactly **six** rows: C1 (thirteen leaves → seventeen), C2 (9/3/1
  → 13/3/1), C3 (four option rows plus `--restore`), C5 (`len(WORKFLOW_STATES)`
  13 → 14), **C10** (`len(record_fields)` 20 → **25**), and C11 (ten `BLOCKED`
  rows → fourteen). C10 was missed in the first accounting and is added here as
  a mechanical consequence, not a new decision: the landed CLI test pins the
  `show --json` / `list --json` projection at twenty fields, and the five
  already-frozen `WorkflowRecord` additions — `attempt_no`, `attempt_state`,
  `attempts_used`, `attempt_budget`, `checkpoint_count` — make the correct total
  twenty-five. **The `WorkflowRecord` shape itself is unchanged**; only the count
  the landed test pinned moves, and everything else in C10 is re-asserted
  verbatim. The supersession is carried in the contract's §1.2 row S10 and in the
  §13.5 disposition table.

  Narrowed, exactly two rows: C22, in exactly one place — its `_region_nodes()`
  floor `>= 13` → `>= 17`, carried explicitly in the contract's supersession
  table as row S14 — with everything else in C22 re-asserted unchanged; and C26.
  **C26 is narrowed, not repealed**: its landed forbidden-token list is fifteen
  tokens, of which thirteen stay banned across the whole region —
  `ai-company-runtime`, `postgres`, `psycopg`, `lease`, `heartbeat`, `worker`,
  `temporal`, `monitor`, `interrupt`, `.claude`, `aos.db`, **`resume`** and
  **`retry`**; `resume` because U-W3's verb is `restore`, `retry` because there
  is no retry leaf — and only the remaining two, `checkpoint` and `compensat`,
  become permitted, inside exactly **seven** enumerated functions:
  `cmd_workflow_checkpoint`, `cmd_workflow_restore`, `cmd_workflow_compensate`,
  `cmd_workflow_adopt_policy`, `_build_workflow_parser`, and — added here to
  close an exemption the first accounting left short — **`cmd_workflow_dispatch`**
  and **`cmd_workflow_show`**. `cmd_workflow_dispatch` builds the
  `request_dispatch` payload whose policy-v2 key is literally
  `restore_checkpoint_id`, so the token is in a frozen payload key and no
  synonym may be invented for it; `cmd_workflow_show` renders the human record,
  one of whose five new aligned label lines reports the checkpoint count from a
  literal tuple inside that function. Every other function in the workflow CLI
  region — the eleven remaining landed handlers and every helper — retains both
  prohibitions in full, and `temporal`, `worker`, `postgres`, `lease`,
  `heartbeat`, private-runtime implementation, durable-engine implementation and
  unrelated queue machinery stay prohibited outside their existing authorised
  boundaries. A test asserts the exemption set is exactly those seven names, so
  it can drift neither by addition nor by omission, and **no CLI leaf is added**
  to reach seven — the count stays four new and seventeen total. An **eighth**
  function needing one of the two exempted tokens is replan trigger 10.

- **D-v0.4.113 — `agentic_os/governance.py` is NOT modified, so its historical
  outer-attempt-loop docstring is superseded in place rather than retouched, and
  the U-K1/U-T1 contract stays byte-unchanged.**

  Two live sentences say the outer attempt loop "is U-W1's": the
  `governance.invoke()` docstring and U-K1/U-T1 §0.2 / D-v0.4.56. U-W1 §2.2
  already froze the binding meaning — "runtime looping is U-W3's" — and stated
  the retouch rule exactly: the docstring "is prose inside
  `agentic_os/governance.py`, which is outside this unit's file boundary; it is
  superseded by D-v0.4.59 and **may be retouched only by a unit that already
  modifies that file**."

  U-W3 does not modify that file and has no functional need to: it executes
  nothing, calls `governance.invoke()` nowhere, touches no `BindingRegistry` and
  reads no `InvocationResult`. Manufacturing a reason to modify it in order to
  unlock the edit would be exactly the escape hatch U-W2 amendment §A.9
  rejected, and retouching the landed U-K1/U-T1 contract to fix an attribution
  is unrelated documentation cleanup, which this unit's scope excludes.

  The authoritative interpretation, recorded here and nowhere else: the outer
  attempt loop is U-W3's, and it is not a loop at all — it is a sequence of
  separately-decided, separately-recorded workflow attempts, each opened by an
  accepted command and closed by a verified external fact, with no `while`
  anywhere in the unit. `governance.invoke()` remains single-attempt and
  byte-unchanged; its parenthetical `(U-W1)` misattributes the owner but does not
  misstate the behavior, which is "at most one attempt, no hidden retry" — true
  under every reading. The retouch obligation transfers unchanged to the first
  future unit that already modifies `governance.py` for a functional reason.

- **D-v0.4.114 — the crash matrix is twenty-one forced points, and no automatic
  repair may fabricate authority or evidence.**

  Every point below the commit boundary rolls back whole, because
  `db.transaction`'s `with conn:` rolls back on any exception and U-W3 adds no
  exception handling of its own around it. The twenty-one points cover: before
  reservation; after reservation before dispatch; after dispatch before
  acknowledgement; after acknowledgement before runtime completion; after failure
  before the retry decision; after the retry decision before redispatch; after a
  checkpoint write; checkpoint corruption; a stale checkpoint; a duplicate
  checkpoint; a duplicate id with a different body; resume before restore;
  restore before the resumed event; compensation start; compensation partially
  applied; compensation completed before its record reached AOS; a duplicate
  compensation record; attempt-budget exhaustion; projection divergence; a
  policy-adoption crash; and a 6→7 schema-migration interruption. The
  twenty-first is answered by ownership rather than by policy: the migration
  runs inside the U-M1 transaction framework, which owns atomicity — a
  mid-step crash rolls back the whole migration, `schema_version` is stamped
  only after the complete step succeeds, and no partial v7 schema is ever
  accepted.

  Three of them are answered by refusing to invent a policy rather than by
  machinery: a **stale** checkpoint is permitted because AOS has no clock with
  which to judge recency and refuses to invent one; **partial compensation** is
  undetectable and is therefore declared rather than guessed at; and a
  **completed-but-unreported** compensation leaves the workflow waiting, because
  inferring the act from its absence would be the fabrication this decision
  forbids. U-W3 contains no repair path, no re-seal, no re-stamp, no `--force`
  and no `--repair`; every recovery is a no-op, a refusal, or a human act —
  usually restoring a verified backup, per RECOVERY.md.

- **D-v0.4.115 — the exact implementation boundary is the closed twenty-one-path
  set, eleven of which are mechanically forced existing test files; the delivery
  identity is adopted unchanged.**

  Seven production paths (`workflow_engine.py`, `workflow_store.py`, `db.py`,
  `migrations.py`, `cli.py`, `power.py`, `README.md`), one new focused test
  (`tests/test_v04_workflow_recovery.py`, rows W1–W30), eleven forced existing
  test edits, and two architecture documents. The eleven were **measured, not
  estimated**: a `SCHEMA_VERSION` bump to `"7"` mechanically forces edits in
  `test_core.py`, `test_v02_migrations.py`, `test_v02_power_modes.py`,
  `test_v03_memory_claims.py`, `test_v03_memory_graph.py`,
  `test_v04_agent_catalog.py`, `test_v04_agent_passports.py` and
  `test_v04_routing_handoffs.py`; the superseded vocabulary and CLI rows force
  `test_v04_workflow_engine.py` and `test_v04_workflow_cli.py`; and
  `test_v04_workflow_store.py` is forced on several axes at once. That file
  stays **inside** the twenty-one-path boundary, and its licensed edit class is
  closed to exactly eleven mechanically forced changes, written out rather than
  described: the hand-transcribed **state**, **event** and **command**
  vocabularies; its **`CONTRACT_COLUMNS`**, **`NO_DEFAULT_COLUMNS`** and
  **tamper-corpus** entries for the two new tables; the one
  **`AdmissionFacts`→`ShellFacts`** construction touch; the **version**,
  **table-count** and **migration-chain** literals; **`_TABLE_CONSTANTS`
  additions** for `workflow_attempts` and `workflow_checkpoints`, so the
  SQL-interpolation scan keeps admitting exactly the frozen `db.py` table-name
  constants and nothing else; the **policy-v2 updates inside
  `test_engine_vocabularies_are_unchanged_and_unshadowed`** — intent kinds 2→3,
  refusal reasons 43→57, policy version 1→2, supported versions `(1,)`→`(1, 2)`,
  matrix dimension 13→14 — together with the **zero-reserved-edge** assertions
  that replace the `("reserved",)` expectation for `running → compensating`,
  **while policy-v1 replay coverage is preserved**: the frozen v1 tuple and
  matrix stay asserted, and a v1 snapshot still refuses `transition_reserved` on
  `compensating → failed`; and the **fresh-versus-migrated SQL equivalence**
  assertions.

  That last class is a **narrow supersession**, declared as contract §1.2 row
  S16, and not a weakening of unrelated migration integrity. `workflow_facts`
  and `workflow_receipts` stay **byte-identical** fresh-vs-migrated because U-W3
  never rebuilds them, and so do the two new tables, created directly under
  their real names. The four **rebuilt** tables — `workflows`,
  `workflow_events`, `workflow_commands`, `workflow_intents` — require
  **structural equivalence** instead, because `ALTER TABLE … RENAME` can requote
  an identifier the original `CREATE TABLE` did not, so raw `CREATE TABLE` text
  is not required to be byte-identical for those four. Structural equivalence is
  not a softer synonym for the same thing: it is a seven-way comparison covering
  table identity, columns and their ordering, defaults, CHECK behavior, foreign
  keys, indexes and uniqueness. Exactly one landed assertion —
  `test_fresh_and_migrated_sql_is_byte_identical_for_the_six_tables` — is
  narrowed; every row copy, row hash, event digest, frozen-v6 byte comparison
  and fixture assertion stands unchanged.

  Nothing else in that file may be edited: no assertion deleted, no `subTest`
  dropped, no tamper case weakened, no bound loosened. The licence does **not**
  authorise a twelfth existing test path — that stays replan trigger 14, and the
  forced set stays eleven files. This is the third consecutive unit to meet the
  same class of mechanical necessity (U-W2.2's A1, U-W2.3's A3), and it is
  declared up front here rather than discovered by an auditor. The licence is
  **not standing**: a future unit meeting it needs its own governed decision.

  There is no migration file, no `migrations/` directory and no SQL file — this
  repository has never had one and U-W3 introduces none; the DDL lives in
  `db.py` and the step in `migrations.py`. `tests/fixtures/**`,
  `agentic_os/governance.py`, `agentic_os/protocols.py`, `protocols/**`,
  `agentic_os/workspecs.py`, `agentic_os/ids.py`, `agentic_os/events.py`,
  `tools/**`, `.github/workflows/ci.yml`, `pyproject.toml`,
  `AGENTIC_OS_BLUEPRINT.md`, every landed contract and
  `/home/daksh/Projects/AICompany` are all deliberately unchanged, each with a
  stated reason. A twenty-second path is
  `FAIL — GOVERNED REPLAN REQUIRED`, not a quiet extension, and fifteen replan
  triggers are enumerated so the boundary is falsifiable rather than aspirational.

  Every provisional delivery identity is adopted unchanged, because no
  repository evidence proves any of them incompatible: branch
  `v0.4-u-w3-runtime-recovery`; contract
  `agentic-os-v0.4-u-w3-runtime-recovery-contract.md`; architecture commit
  `docs(v0.4): freeze U-W3 runtime recovery architecture`; implementation commit
  `feat(v0.4): add workflow retry, checkpoints, resume, and compensation`; PR
  title `feat(v0.4): U-W3 workflow runtime recovery`; milestone
  `milestone/v0.4-u-w3-runtime-recovery`. Two ordered commits inside one PR
  through the U-P2 gate, documentation first (the D-v0.4.50 landing model,
  applied a fourth time), the tag after the merge and never before. Wave 0
  stages nothing, commits nothing and pushes nothing; it writes exactly
  `DECISIONS.md` and the contract.

- **D-v0.4.116 — the hard audit and the adversarial verification that followed
  it found twenty-eight bounded defect groups; all twenty-eight are
  repaired inside the two architecture paths, and the one that mattered most
  was a documentation decision that would have bricked every pre-migration
  workflow.**

  The audit that preceded the implementation wave reproduced every U-W3 claim
  against the live tree and against `fef0c2b`; the verification that followed
  it attacked the shipped code. Twenty-eight corrections are recorded as §22
  A1 … A28 of the contract — A1 … A22 from the architecture audit, A23 … A26
  from implementing it, and A27 … A28 from attacking the result. None adds a repository path, a
  twelfth existing test file, a state, a policy version, a table, a CLI leaf or
  a protocol change, so none is a §21 replan trigger.

  Four came out of the implementation itself and are worth naming, because
  each was a place where the architecture had described a behavior the landed
  code does not have. **A23**: §14 row 19 claimed a planted attempt-row hash
  makes mutating commands refuse; it does not, because the per-command gate is
  the snapshot-and-history comparison and row hashes are deliberately outside
  it — which is precisely what the integrity-scope sentence `show` and `list`
  print tells every operator. Widening that gate would have been U-W3 quietly
  taking ownership of a landed boundary. **A24**: §6.2 made
  `runtime_task_uuid` mandatory on a `failed` receipt, which the frozen receipt
  shape does not require and the landed CHECK admits as NULL — the landed
  hostile-path tests emit exactly such a receipt, and they started failing the
  moment the rule was implemented. The fix collapses two rules into one: a
  present corroborating uuid must match, an absent one refuses nothing,
  everywhere in the unit. It loses nothing, because at most one attempt is ever
  open and the LEDGER decides which attempt a receipt closes. **A25**: the
  U-W2 README paragraph's five counts go stale and are deliberately not
  repaired, because path 7 licenses one new section and no other region; the
  U-W3 section states the superseding numbers and says which they supersede.
  **A26**: §17.8's focused-gate command form never worked for seven of
  the twelve modules, each importing a sibling under `tests/` without a path
  insert — true at `fef0c2b` too, so U-W3 states the working form and names the
  missing module for each, rather than editing seven test files outside their
  licences. The first draft of this correction said five, then six; it is
  recorded here as the MEASURED seven, because a correction that is itself
  estimated is not a correction.

  The verification round then attacked the shipped code and found six more,
  recorded as A27. One was serious: a spliced event carrying a U-W3 name but
  stamped `policy_version: 1` skipped its own required-payload row — the row
  applies at version 2 and up — so `verify_history` CERTIFIED it and `fold`
  then raised a raw `KeyError` that escaped `verify`, `read_workflow` and every
  mutating command. The version axis had only half of itself: it said which
  members a version requires, and not which event NAMES a version has at all.
  An event whose name did not exist at its own stamped version is now
  `history_corrupt`, refused before it is ever folded. The remaining five are
  smaller and are listed in A27; the one worth repeating is that the
  seven-function token exemption over-permits by two — only five functions
  actually carry a narrowly exempted token — so the measured carrier set is now
  asserted exactly in both directions while the frozen seven stay the ceiling
  an eighth would breach.

  **A28 is the one worth learning from, because the first pass created it.**
  The eight version-literal licences name each file's literal in the singular
  — "the one `db.SCHEMA_VERSION` literal", "the two `"6"` literals" — and four
  files carry SIBLING occurrences of the same fact that the cells do not
  enumerate. Eleven stale assertions survived the first pass, every one a real
  failing test. One was worse than stale: a chain row inserted into an
  `assertEqual(actual, expected)` call became a THIRD positional argument,
  which `assertEqual` accepts as the failure MESSAGE — so the test passed while
  comparing nothing about the new step. A green test that verifies less than it
  claims is exactly what §17.3's no-weakening rule exists to prevent, and the
  mechanism was not a deletion but a well-formed call that quietly stopped
  comparing. The discipline that catches this class is a tree-wide sweep for
  the FACT — every schema-shaped literal, chain row and count — run after the
  named edits and again after the repair; reading the diff does not find it,
  because nothing in the diff looks wrong.

  **A1 is the load-bearing one.** §12.3 justified keeping the snapshot record
  at `/v1` while widening its member set, on the true but irrelevant ground
  that the snapshot "never leaves the process that built it". The snapshot's
  DIGEST does leave: it is `workflows.content_sha256`, and the store compares
  it against the rebuilt snapshot on every command and inside `verify`. Adding
  members unconditionally would have changed that digest for every workflow
  admitted before U-W3 existed — each would refuse `snapshot_divergence` on its
  next command and read as tampered, with the migration forbidden to re-stamp
  it and `verify` forbidden to repair it. That is §21 trigger 12 reached
  through prose. The repair is the trade this architecture already makes for
  the transition matrix: the member set is frozen per policy version, a v1
  workflow seals over exactly U-W2's members forever, and
  `adopt_policy_version` is the one legitimate re-seal boundary.

  Four more were structural rather than cosmetic. **A2**: §11.2 widened the
  storage CHECK to admit a dispatch pointer in `retrying` but no section
  widened the reducer's three matching state gates, so a retrying workflow with
  a rejected reservation could neither revoke it, nor receive the rejection,
  nor re-dispatch — its remaining budget unreachable, which is the exact harm
  the reserve-at-acceptance design exists to prevent. **A3**: §5.5 named
  `_EVENT_PAYLOAD_OPTIONAL` as the mechanism for a policy-conditional required
  member, which would have let `verify_history` certify a policy-v2 acceptance
  carrying no ordinal — reproducing inside v2 the very state §5.2.1 refuses;
  the table gains a version axis instead. **A5**: `beast.work-spec/v1` carries
  an optional `runtime_task_uuid`, and the landed acceptance gate requires a
  declared value to match, so a WorkSpec declaring one together with
  `max_attempts > 1` could never retry at all; the declaration is frozen to
  bind attempt 1 only. **A20**: rows W2 and W23 specified `git show fef0c2b:…`
  parsed in-test, and CI checks out shallow with no `fetch-depth`, so both rows
  would have failed all four required checks with a tooling error rather than
  an assertion — they use hand-transcribed frozen sources instead.

  **A22 completes three forced-edit licences that were measured against count
  pins and missed landed token-scan guards.** `tests/test_v04_workflow_store.py`
  bans the tokens `checkpoint`, `compensate` and `attempts` in the store U-W3
  must extend; `tests/test_v04_workflow_engine.py` bans `compensat` in the
  command and event vocabularies and `checkpoint` in the engine source; and
  `tests/test_v03_memory_graph.py` carries a test whose NAME asserts that no
  version-seven transition exists. All three fail by construction. Each is
  narrowed rather than deleted, each narrowing is enumerated, and the eleven
  forced files are unchanged as a set — no twelfth is forced, which the audit
  confirmed by grepping every version, table-count and vocabulary literal in
  the tree.

  Six corrections make an unreachable path honest rather than pretending it
  fires: `attempt_budget_exhausted` (A6) and `MAX_CHECKPOINTS_PER_WORKFLOW`
  (A7) are structural backstops the shipped predicates and bounds can never
  reach through a real history, and `compensation_already_concluded` (A11) is
  unreachable because both compensation conclusions are terminal and §5.3.5
  forbids a second terminal carve-out. Each stays implemented as a total guard
  and is asserted as a refusal-by-construction, exactly as §8.4 already treats
  `waiting_input` and `paused`. The alternative — a contract that claims a
  branch fires when it cannot — is the thing this repository has consistently
  refused, and the audit's own rule applies to the audit's own output: a test
  that pretends an unreachable path is live is the defect, not the fix.

  One correction is a token collision worth naming because it would have fired
  a replan for a spelling: the fourteenth state is `retrying`, whose lowercase
  form contains `retry`, which stays banned across the whole CLI region. **A16**
  freezes that no state literal appears in that region at all — state names
  reach the CLI only through the engine's own vocabulary — and W28 asserts the
  absence.

- **D-v0.4.117 — the CI failure that followed the implementation wave was a
  quadratic TEST FIXTURE, not a production defect; it is repaired inside path
  10 alone, under one new licensed edit class, and no timeout, no production
  file and no byte of hostile-data coverage moves.**

  The observed authority is GitHub Actions run 30964552253. `tests-python-3.12`
  completed all 3,215 tests successfully in 1,796.706 s and the 30-minute job
  timeout then cancelled the remaining steps before protocol projection and the
  clean-tree check ever ran. `tests-python-3.14` reached the same timeout while
  the suite was still running. `workflow-integrity` and
  `distribution-smoke-python-3.12` passed. `unittest` reported OK: nothing
  asserted anything false, and the two jobs died of wall clock.

  The cause is `HostileRowTests::test_every_column_of_all_six_tables_tampered`
  in `tests/test_v04_workflow_store.py`. It builds a complete six-command
  `Journey` for **every one of its 740 hostile values**, and `StoreCase.setUp`
  gives the whole matrix ONE in-memory database — so the fixture grew that
  database to 740 workflows while calling `verify(conn)` and
  `list_workflows(conn)` once per value, both of which walk every workflow
  present. The matrix was therefore quadratic in its own scaffolding: roughly
  274,000 workflow-verifications, of which the hostile data needed 740. A
  measured profile puts `verify` at 63.6 % and `list_workflows` at 30.9 % of
  the matrix; the hostile values themselves cost almost nothing.

  **Three repairs were available and two are refused.** Raising
  `timeout-minutes` moves the wall without touching the defect, and
  `.github/workflows/ci.yml` is outside U-W3's boundary anyway (§17.7).
  Sampling the corpus — a "representative" subset of the ten hostile values, or
  of the 83 columns — would buy the time by deleting the coverage the row
  exists to provide, which is the weakening §17.3 has refused since it was
  written. The third is the one taken: keep every value and stop rebuilding the
  scaffolding. One `Journey` is reused per **(table, column) pair**, so 740
  constructions become 83 and the database the matrix makes `verify` walk stops
  at 83 workflows instead of 740.

  That reuse is sound only if each hostile value hands the journey back byte
  for byte, so the licence is written as a conditional and every half of it is
  PROVED rather than assumed: the baseline is captured before the pair's first
  value; each value proves the baseline present before it tampers; the tamper
  is still one `UPDATE` against the REAL persisted row; restoration runs
  through `finally`, so a failed assertion, an escaped exception and a
  storage-refused tamper all reach it; restoration is an unconditional rewrite
  of the workflow row, its rows in all seven child tables and its `events`
  journal rows, in foreign-key order, rather than a selective undo of what the
  value was expected to change; row equality against the baseline is re-proved
  after restoration; a whole-store comparison at the end of each pair catches
  anything that moved outside the journey; and a restoration failure sets a
  sticky flag that is re-raised OUTSIDE the `subTest` block, which is what
  makes it end the matrix instead of being recorded and stepped over. A
  restoration that only reverses what it expected is exactly the one that leaks
  the case it did not expect, which is why the rewrite is unconditional.

  The verified evidence, measured on the same machine and interpreter with
  nothing else running: `HostileRowTests` **1,186.5 s → 238.6 s**, a **4.97×**
  reduction; `Journey` constructions in the matrix **740 → 83**; the complete
  repository suite **942.3 s** for the same 3,215 tests CI counts. Nothing was
  removed to get there: the `(table, column, value, tag)` sequence and the
  `subTest` identity sequence are both identical, 740 for 740, across the
  change; `_exercise` is byte-identical; `HOSTILE_VALUES` and both column
  matrices are byte-identical; the assertion census moves only upward
  (`assertEqual` 5 → 9, every other kind unchanged, none lost). Four negative
  controls confirm the new guards are load-bearing rather than decorative —
  disabling restoration, omitting one table from it, corrupting one column
  after it, and making it raise all fail, and the raising case stops the matrix
  after exactly one value.

  **The licence is S17 and E16, and the numbering is forced.** S17 narrowly
  supersedes one statement and one only: that path 10 has exactly ELEVEN
  licensed edit classes. It is now twelve. The twelfth is numbered E16 rather
  than E12 because §22 A22 already added E12–E15 to the same enumeration and
  `tests/test_v04_workflow_store.py` cites `A22/E15` by name — renumbering
  those four would strand a live reference inside a file this amendment is
  forbidden to touch, and two rows called E12 would be worse than a gap. Path
  10's complete inventory is E1–E16: the twelve of §17.3 plus A22's four.

  Everything else is unchanged and was checked rather than assumed: the
  twenty-one implementation paths, the eleven forced existing test paths, W1–W30,
  the twenty-one crash rows, the fifteen replan triggers, and every policy,
  schema, CLI and protocol count. No production file, workflow file, protocol
  artifact or CI file is touched, so no §21 trigger fires — in particular
  trigger 1 (a twenty-second path) and trigger 14 (a twelfth existing test
  file) are both untouched, because this amendment writes only paths 10, 20 and
  21.

# DECISIONS — Agentic OS v0.4 U-W2.3 workflow CLI, power policy, and docs (Wave 0)

This section continues the `D-v0.4.*` series for the U-W2.3 Wave 0 architecture
freeze and the governed U-W2 contract amendment it required: one `aos workflow`
command group over the landed reducer and store, thirteen power-policy entries,
one observability row for a refused command, and one README section. Architecture
only — no production code, tests, CLI handlers, power entries, or README prose
ship in this commit. Branch `v0.4-u-w2-3-workflow-cli`, worktree
`/home/daksh/Projects/agentic-os-u-w2-3`, baseline
`de10deaf181b99a05415370d65149b83685af979` (= HEAD = `origin/main` = the
merge-base = `milestone/v0.4-u-w2-2-workflow-store^{}`). Prepended per the
established precedent (D-W0.4, reaffirmed in D-v0.2.7, D-v0.4.4); everything
below stays byte-identical, including D-v0.4.1 … D-v0.4.96, which D-v0.4.97
supersedes only where it quotes them and never rewords.

## D-v0.4 decisions (U-W2.3 Wave 0)

- **D-v0.4.97 — governed amendment A3 to the landed U-W2 contract: the U-W2.3
  slice inventory is the closed EIGHT-path set; six clauses are superseded and
  four silences are closed; the delivery is two ordered commits; no standing
  authority of any kind is created.**

  **The contradiction.** Five landed statements are jointly unsatisfiable, and
  the impossibility lives in the contract rather than in any candidate. (1) U-W2
  §16 freezes thirteen `aos workflow` leaves and their power classes — nine
  `authoritative_write, ledger`, three `read_only`, one `derived_write` — and A1
  §A.2 preserved §16 unchanged. Ten of the thirteen therefore carry a class
  outside `power.RECOVERY_ALLOWED_KINDS`, which is
  `frozenset({READ_ONLY, RECOVERY_SAFE})`. (2)
  `tests/test_v02_power_modes.py::RecoveryTests.BLOCKED` is a HAND-KEPT tuple of
  51 `(command_path, argv)` pairs, and
  `test_every_blockable_command_is_covered_by_the_block_list` asserts BOTH
  directions of coverage against the LIVE parser, so the thirteen leaves
  mechanically force exactly ten new rows in an existing test file. Measured with
  the leaves and their policy entries present in memory only:
  `should_block - covered` is exactly the nine writers plus `export-intents`, and
  `covered - should_block` is empty — ten rows forced, nothing to remove, and
  every other leaf-set-dependent predicate in the tree still passing
  (`len(leaves) > 40` → 108, bidirectional classification coverage, the
  ledger-flag rule, and every prefix-scoped count). (3) §0.3 declares every
  existing test and fixture untouched; A1 §A.3.1 item 3 superseded that clause for
  exactly eleven files and exactly their edit classes, and A1 §A.5 states the
  licence is not standing, naming this unit: "A future mechanical necessity —
  including the same class of version-pin edit **in U-W2.3** or any later unit —
  requires its own governed amendment through this same mechanism."
  `tests/test_v02_power_modes.py` is one of A1's eleven, but only for the
  schema-version literal and only for that one delivery. (4) §19 row 22 as
  rewritten by A1 §A.3.1 item 4 requires every existing test file outside A1's
  eleven to be byte-unchanged. (5) §18's U-W2.3 table names four implementation
  paths and §18's closing rule makes a fifth `FAIL — REPLAN REQUIRED`. Items 3–5
  forbid exactly the edit item 1 forces. This is A1 §A.1's pattern one wave later,
  and the lawful resolution is the same mechanism.

  Two further defects are folded into the same amendment rather than
  reinterpreted silently. §16's closing sentence — "`expected_revision` is read
  from the live row by the CLI shell immediately before deciding, **inside the
  same transaction as the CAS**" — is unimplementable: `workflow_store.submit`
  owns the ONLY transaction (`with db.transaction(conn):` then
  `conn.execute("BEGIN IMMEDIATE")` as its first statement, pinned by U-W2.2 §20
  row S12), `db.transaction` is the sqlite3 connection context manager, and a
  caller-opened transaction around `submit` makes that statement raise
  `cannot start a transaction within a transaction`, which `submit` maps to
  `store_unavailable`; `expected_revision` is moreover sealed under the envelope
  digest, so it must be chosen BEFORE `submit`. By U-W2's own closing rule that
  sentence is a defect. And U-W2.3 had no authorised path for its own Wave-0
  documents at all: A1 §A.6 defers U-W2.3's branch, PR title, tag and commit
  identity to "its own Wave 0 against this amended contract — not silently, and
  not here", and explicitly discharges the §18 two-Wave-0-documents clause, while
  A1 §A.5 authorises no documentation file beyond A1's own named paths.

  **The supersession set**, exactly and no others. S1 — §0.3's "every existing
  test, and every existing fixture", superseded for EXACTLY ONE further file,
  `tests/test_v02_power_modes.py`, and EXACTLY ONE edit class: one contiguous
  insertion of ten `RecoveryTests.BLOCKED` rows plus their comment header, at a
  named position, and nothing else in that file; for every other existing test
  and fixture §0.3 stands verbatim. S2 — §19 row 22's byte-unchanged clause, as
  already rewritten by A1, extended to name that one further file, with no test
  deleted, skipped, renamed or weakened and no assertion's meaning rebased. S3 —
  §18 slice U-W2.3's "Paths:" list, superseded by the closed eight-path
  inventory; the four implementation paths remain unchanged in content and
  responsibility, and the trailing two-Wave-0-documents clause stays discharged.
  S4 — §18's closing rule, superseded ONLY in what "the tables above" denotes
  (the §18 tables as amended by A1 §A.4 and by A3); the rule itself is preserved
  verbatim and keeps firing. S5 — D-v0.4.81's "the exact file table in §18 is
  exhaustive", re-read as "…, as amended by A1 §A.4 and A3, is exhaustive"; the
  landed D-v0.4.81, D-v0.4.95 and D-v0.4.96 entries stay byte-identical history
  and this decision extends them without rewording. S6 — §16's transaction claim,
  superseded by the only implementable shape: the CLI reads the live revision
  with `workflow_store.read_workflow` IMMEDIATELY BEFORE `workflow_store.submit`,
  and the compare-and-swap runs inside `submit`'s single `BEGIN IMMEDIATE`
  transaction; a writer that advances the revision in between makes the command
  refuse `revision_mismatch` and write nothing. The clause's intent — the CLI is
  a convenience wrapper and the engine still enforces the guard — is preserved
  exactly; only the impossible transaction claim is withdrawn, and nothing else
  in §16 is touched. S7 — U-W2.3's delivery identity, which is a RESOLUTION
  exercising the authority A1 §A.6 granted rather than the supersession of a
  clause still in force; §18's own commit subject for this slice was never
  superseded (A1 §A.3.1 item 6 superseded U-W2.2's subject only) and is adopted
  verbatim.

  **Four silences closed**, because an unlicensed behavior is a defect by U-W2's
  own closing sentence: the refusal-journal row's `entity`, `entity_id`, `action`
  and payload members (C-A); the CLI's command-envelope assembly discipline,
  since U-W2.1 shipped no public record-builder (C-B); the accepted workflow-ID
  form family and its canonical rendering at the CLI edge (C-C); and
  `export-intents`' filename scheme, idempotence rule and unreadable-row
  behaviour (C-D). Their frozen content is the subordinate U-W2.3 contract.

  **The closed inventory**: `DECISIONS.md`,
  `agentic-os-v0.4-u-w2-workflow-state-engine-contract.md` and
  `agentic-os-v0.4-u-w2-3-workflow-cli-contract.md` in commit 1; `agentic_os/cli.py`,
  `agentic_os/power.py`, `README.md`, `tests/test_v04_workflow_cli.py` and
  `tests/test_v02_power_modes.py` in commit 2. Eight paths, two commits, and a
  ninth path is `FAIL — REPLAN REQUIRED`.

  **Rejected**: extending §18's README scope to also rebase the file's stale
  global schema-version paragraph (it predates U-W2, §18 scopes the edit to one
  new section word for word, and an amendment that reaches beyond its forcing
  cause is the escape hatch A1 §A.9 already rejected); a general mechanical-edit
  licence for future CLI additions (a standing licence is an escape hatch — each
  future necessity earns its own amendment); deriving `RecoveryTests.BLOCKED`
  from the parser instead of adding ten rows (it would rewrite an existing
  assertion's meaning and make the guard vacuous, since the row exists to be an
  independent hand-kept cross-check of the parser-derived predicate); folding the
  per-command detail into A3 and shipping seven paths (per-path detail belongs in
  a subordinate contract, the A1 §A.4 precedent); reinterpreting §16's
  transaction sentence charitably in the implementation (that is the
  self-amendment A1 §A.1 found unlawful); adding a store or engine function so
  the CLI could read the revision inside the transaction (U-W2.2 §8 makes that a
  replan trigger and the reducer is byte-frozen); rewriting the landed contract
  or this file in place; a sibling amendment document (a ninth path); and
  deferring the matter to a later unit (U-W2.3 cannot land at all under the
  contradiction).

  A3 adds no state, command, event, receipt kind, intent kind, refusal reason,
  matrix edge, policy version, table, column, CHECK, index, migration, store or
  engine API function, transaction step, record schema, or registry identity, and
  removes none. A1's nineteen-path U-W2.2 inventory, §A.5's no-expansion rule, A2
  and B1 are unchanged. No standing authority of any kind is created.

- **D-v0.4.98 — the U-W2.3 CLI surface: thirteen leaves under one `aos workflow`
  group, mapped onto SIX landed public store functions; `workflow_store.rebuild`
  is deliberately never called; the CLI assembles the command envelope itself;
  the workflow identity is normalised exactly once at the CLI edge.**

  The group registers two levels — `workflow` then the verb — so
  `power._PATH_DESTS` resolves the classification key to exactly
  `("workflow", <verb>)`. The thirteen leaves, their arguments, and their entire
  option surface are U-W2 §16's, unchanged: `--route` on `dispatch`, `--json` on
  `show` and `list`, `--state` on `list`, and nothing else. `--state`'s choices
  are `workflow_engine.WORKFLOW_STATES` read through the module, the live
  `_retrieval_candidate_choices` idiom, so a state cannot exist that `--state`
  refuses and vice versa.

  Six store functions carry all thirteen leaves: `submit`, `read_workflow`,
  `read_history`, `list_workflows`, `list_outstanding_intents` and `verify`. The
  seventh, `rebuild`, is **deliberately never called**, and that is a security
  boundary rather than a preference: `RebuildResult.snapshot` embeds
  `work_spec_document` and `report_document` VERBATIM, so calling it would put
  untrusted stored bodies on a surface `show` prints.
  `StoreOutcome.snapshot` is read for its `state` member only and is never
  emitted. No store function is added, so U-W2.2 §8's replan trigger does not
  fire.

  U-W2.1 shipped no public record-builder — the engine's only public functions
  are `decide`, `fold` and `verify_history` — so the CLI assembles the
  `aos.workflow-command/v1` record itself from public constants plus
  `protocols.content_digest`. This is licensed: §6 defines the envelope,
  `COMMAND_SOURCES` contains `"cli"` precisely so the CLI can be its source, and
  §16 calls the CLI a convenience wrapper. The assembly is frozen: `schema` from
  the constant and never a literal; `command_id` a fresh `uuid.uuid4()` per
  invocation, so re-running a verb is a NEW command and not a forced replay;
  `actor` the constant `"human"`; `source` the constant `"cli"` and never
  `"runtime_adapter"`, so the ledger's account of who submitted a command stays
  truthful even when the payload came from the runtime; `created_at` from
  `utils.utc_now_iso()`; `trace` OMITTED, because the CLI mints no trace it did
  not receive; `workflow_id` present except on `admit`; and `content_sha256`
  recomputed over the body, never copied.

  The workflow identity is normalised ONCE, at the CLI edge, to A2 §A2.2's
  canonical `"WF-" + str(ids.parse_id(text, "workflow"))`. That is mandatory, not
  cosmetic: the store's READERS accept every spelling `ids.parse_id` accepts,
  while `submit`'s envelope gate is the strict `^WF-[0-9]{1,19}$`, so an
  un-normalised zero-padded or lower-cased argument would succeed on `show` and
  refuse `command_malformed` on every write verb — the same identity behaving
  differently on two leaves of one group. `ids.render_id` is NEVER used for a
  workflow: it zero-pads to width 4 and would produce `WF-0007` where the engine
  minted `WF-7`, breaking every event digest.

- **D-v0.4.99 — the refusal journal: `action = "workflow_command_refused"`,
  deliberately outside the seventeen workflow events; emitted on `refused` and
  `conflict` only, in its own transaction, and never for a `WorkflowStoreError`.**

  U-W2 §8 assigns the row to the CLI shell and U-W2.2 §9.4 places it outside the
  transaction that declined the work, stating that until U-W2.3 ships "a refusal
  leaves no trace in `aos.db` at all". No document froze its shape. Frozen here:
  `actor="human"`, `entity="workflow"`, `entity_id` the INTEGER `workflows.id`
  (matching the store's own `_journal`) or `None` when no identity exists,
  `action="workflow_command_refused"`, and a payload of exactly
  `{workflow_id, command, command_id, command_sha256, status, reason, where,
  expected_revision, revision, diagnostics}`.

  `action` is deliberately OUTSIDE `workflow_engine.WORKFLOW_EVENTS`: U-W2 §8
  says the workflow history records accepted transitions only, and a journal row
  whose `action` were one of the seventeen event names could be mistaken for a
  transition that never happened. The row is emitted on `refused` and `conflict`
  ONLY — never on `accepted`, because the store already journals one row per
  appended event, and never on `replay`, because nothing was declined. A
  `WorkflowStoreError` out of `submit` is NOT journaled: it is an infrastructure
  fact about the ledger, not a fact about a workflow, and a workflow-scoped row
  for it would state something untrue. The write takes its own
  `db.transaction`, outside the one that declined the work, so a journalled
  refusal can never be rolled back with the work it declined. Every payload
  member is a closed code, a validated identifier, a digest, a bounded integer,
  or the store's own bounded `diagnostics`; there is no free-text member at all,
  so `events.emit`'s `secretscan.redact_tree` choke point is a second line of
  defence rather than the only one.

- **D-v0.4.100 — output and integrity scope: `show` and `list` state the
  read-verdict caveat; `--json` exists on `show` and `list` only; `verify` exits
  0 iff every report is `ok`; no stored body is ever printed.**

  B1 §B1.14 names an explicit U-W2.3 obligation: the readers' verdict "is the
  snapshot-and-history one … what is lost is prompt DETECTION, until someone runs
  `workflow verify` … and U-W2.3's CLI is expected to say so where it displays a
  read verdict." One fixed sentence, held in a single module constant, is emitted
  by `show` and by `list` in human mode and carried as `integrity_scope` in both
  `--json` documents — including when the list is empty, because the caveat is
  about the verdict's scope and not about the rows.

  §16 grants `--json` to `show` and `list` and to nothing else, so `verify` and
  `export-intents` have none. `verify` exits 0 iff every `VerifyReport.integrity`
  is `ok` and 1 otherwise, with the problem lines on stderr — the live
  `agent route verify` precedent — so it is usable as a gate. `show` exits 0
  whenever the row exists, INCLUDING when integrity is not `ok`, because U-W2.2
  §15.3 keeps read paths total and `verify` carries the verdict.

  Nothing the CLI prints can carry a stored document body, a receipt
  `reason.message`, an `approval_ref`, or an evidence `ref`/`claim`: `show`
  renders only `WorkflowRecord` fields and reconstituted `aos.workflow-event/v1`
  records, whose payloads U-W2 §7 closes to enum members, validated identifiers,
  bounded integers and digests. A refusal is exactly one line on stderr,
  BYTE-EQUAL to `str(StoreOutcome.refusal)`, with nothing on stdout and no
  CLI-authored prefix or suffix — the store already builds the house-format
  bounded, value-free line. Because no stored free text is printed, no terminal
  control byte from an untrusted document can reach a terminal.

- **D-v0.4.101 — `export-intents` is `derived_write`, content-addressed and
  idempotent, and reports an unreadable outbox row rather than dropping it.**

  §16 says "idempotent, content-addressed filenames" and no document said what
  the name is, what happens when it already exists, or what happens to an
  unreadable row. Frozen: DIR must ALREADY exist and be a directory — the CLI
  creates neither it nor its parents, because writing records into a directory
  presupposes the directory. The filename is
  `f"{intent_kind}-{content_digest(document)}.json"`, matching
  `^(dispatch|cancel)-[0-9a-f]{64}\.json$` BY CONSTRUCTION, so no byte of any
  stored document can influence it and traversal, absolute paths, NUL bytes and
  `..` segments are structurally unrepresentable. The address is computed by the
  CLI from the bytes it is about to write, never read from the stored
  `content_sha256` column, so a tampered column cannot redirect a write.
  Creation is `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW`; on `FileExistsError` the
  existing file is opened `O_RDONLY|O_NOFOLLOW`, `fstat`ed for regular-file and
  exact size, read and byte-compared — identical reports `unchanged`, and
  anything else refuses naming only the safe basename. A content-addressed name
  whose bytes differ is a foreign or tampered file and is never overwritten or
  truncated.

  An unreadable outbox row (`IntentView.readable is False`) is reported on stderr
  and forces exit 1 after the readable rows are written, never silently dropped;
  re-running after repair completes the job, because the write is idempotent.
  `export-intents` is `derived_write` and therefore blocked in recovery: it
  writes no ledger row and emits no event, but it does write files that hand work
  to the runtime, and a damaged workspace must not dispatch.

- **D-v0.4.102 — the README edit is exactly one new unit section; the file's
  pre-existing stale global schema-version paragraph is a declared limitation,
  not U-W2.3's to repair.**

  U-W2 §18 scopes `README.md` to "one new unit section", word for word. The new
  section sits after the U-W1 section and before `## Weekend commands`, covers
  all thirteen commands in three frozen bash blocks, states that the wave-1
  transport is explicit file exchange with no network and no queue, carries the
  B1 §B1.14 integrity-scope caveat and the U-W2.R / U-W3 / U-W4 / U-W5 / U-W6
  boundaries and the no-shared-database rule, declares the five known limitations
  (post-dispatch cancellation is dormant; revocation before observed acceptance
  is advisory; a WorkSpec may declare zero required evidence; cancel intents can
  remain outstanding forever; three receipt kinds have no live source), and
  points at the two frozen contract files.

  The file's existing global schema-version paragraph is NOT edited. It was
  introduced at `d06df1b` (U-A1) and was already false after U-A3 shipped schema
  5, before U-W2 existed, so it is neither U-W2's creation nor U-W2.3's
  responsibility; extending A3 to reach it would be exactly the escape hatch A1
  §A.9 rejected, and U-W2.2 §22's description of the live bytes is itself
  inaccurate, which makes it a weak basis for authority over them. The new
  section makes no global current-version claim, so U-W2.3 introduces no
  contradiction; the pre-existing one is carried as a declared known limitation
  and named as work for a future documentation unit. Editing any other region of
  `README.md` is a stop condition, not a judgment call.

# DECISIONS — Agentic OS v0.4 U-W2.2 governed identity-binding amendment

This section continues the `D-v0.4.*` series for the governed amendment the
U-W2.2 implementation wave required when it reported
`FAIL — REPLAN REQUIRED` on finding F-001. Architecture only — no
production code, tests, DDL, migrations, fixtures, CLI, workers, or
adapters ship in this commit. Branch `v0.4-u-w2-2-workflow-store`
(amendment 2026-07-28), worktree `/home/daksh/Projects/agentic-os-u-w2-2`,
baseline `63de8c953f2613a79d6e1bb6052646c669894863`, amended above the
landed U-W2.2 Wave 0 documentation commit
`91075d7cb3b94013242b36c777baa59ee37500f9`, which is preserved
byte-for-byte and is NOT rewritten, amended, squashed, reset, or rebased.
Prepended per the established precedent (D-W0.4, reaffirmed in D-v0.2.7,
D-v0.4.4); everything below stays byte-identical, including D-v0.4.83 …
D-v0.4.95, which D-v0.4.96 supersedes only where it quotes them and never
rewords.

## D-v0.4 decisions (U-W2.2 governed identity-binding amendment)

- **D-v0.4.96 — the canonical workflow identity representation is the
  rendered string `"WF-" + str(workflows.id)`, bound into all four §5.8 row
  hashes by its sha256 leaf; the direct-integer binding that made almost
  every workflow unsealable is superseded, together with nine further
  confirmed contract contradictions and silences; commit `91075d7…` is
  preserved and the U-W2.2 delivery becomes three ordered commits.**

  **The contradiction.** U-W2.2 §5.1 makes `workflows.id` the reducer's
  DERIVED identity, "always … in `[1, 2**63-1]` = `ids.MAX_ID`". §5.8 binds
  `workflow_id` as a direct INTEGER in all four row-hash payloads
  ("integers bound directly"). §5.8 also freezes the digest as
  `sha256(protocols.serialize_canonical(payload)).hexdigest()`, and
  `protocols.serialize_canonical` refuses every integer outside
  `±(2**53-1)` with `ProtocolError[integer_out_of_range]`
  (`agentic_os/protocols.py:60,188`). Any two clauses hold; all three
  cannot. `workflow_engine._workflow_identity`
  (`agentic_os/workflow_engine.py:623-644`) derives
  `int.from_bytes(tagged_digest[:8], "big") >> 1` with `0 → 1`, so
  `P(identity ≤ protocols.INT_MAX) = 2**53 / 2**63 = 2**-10`: 1023 of every
  1024 valid identities are unsealable. Measured independently in the
  replan session on 2000 real WorkSpec digests, 1998 exceeded the bound,
  and bound exactly as §5.8 freezes it the FIRST accepted
  `admit_work_spec` raises `WorkflowStoreError("store_unavailable")` and
  persists nothing. This was a defect in the frozen architecture, not in
  the implementation, which is why the wave reported a replan rather than
  landing a byte-unfaithful store.

  **The representation.** One canonical representation, and it is the one
  the architecture already froze five times over: the rendered identity
  string `"WF-" + str(workflows.id)` — byte-identical to
  `workflow_engine._workflow_identity`'s output, to the store's §5.1
  renderer, to the `workflow_id` §7.4 reconstitutes into every event
  record, to the `workflow_id` §7.2 step 6 compares, and to the `WF-<n>`
  every public store type carries. It is total over `[1, 2**63-1]`,
  injective, pure, `ids.parse_id`-round-trippable, at most 22 characters,
  single-spelled, and closed. Being TEXT, it binds into a §5.8 payload the
  way §5.8 already binds every text column — by its sha256 leaf, as
  `workflow_id_sha256`. No new identity algorithm, no new serializer, no
  relaxed bound, no new path: the digest function, the `record_schema` key,
  direct binding for the small rowid columns, `None` pass-through, and
  `content_sha256` exclusion are all unchanged.

  **The superseded clauses**, exactly and no others: §5.8's `workflow_id`
  (int) member in all four payloads; §7.2 step 6's inclusion of `id` (as
  `workflow_id`) among seventeen LIVE comparisons, which is a tautology
  because §7.4 reconstitutes the identity from that same column — the real
  binding is the sealed event digest and the comparison is retained as a
  declared backstop, reducing step 6 to sixteen live comparisons; §8.4's
  "the one deliberate non-exception trigger", replaced by an exhaustive
  six-trigger table over the module's ten raise sites — four deliberate
  non-exception triggers where the text claimed one, plus a deliberate
  mapping of a non-`sqlite3` exception the text did not mention; §13.3's
  three injection mechanisms, which cannot express K4 ("inside
  `_insert_command`, before its row-hash finalization"), K13 ("inside
  `_journal`, after the first of two `events.emit` calls") or KA8 ("inside
  `_journal`") because patching a named helper raises before the helper
  acts — a fourth mechanism wraps a NAMED internal callee (`_row_digest`
  for K4, `events.emit` for K13 and KA8), the crash POINTS are unchanged,
  and three test-side label errors that followed from the same gap (KA7
  labelled KA8 with KA8 unexercised, KA1 injected before its task read
  rather than after it, and a K12 instant labelled K13) are corrected with
  it; §3's
  unqualified worst-case claim, scoped to the six workflow tables because
  `tasks.status` is the shell-verified `AdmissionFacts` input by design
  (§4.2, §9.5) and flipping it by direct SQL was reproduced turning
  `refused/admission_task_closed` into `accepted`; §5.1's unconstrained
  `id`, which gains `CHECK (id >= 1)` — the only DDL change — making a
  declared invariant structural without replacing the code's failing
  closed; §8.3/§15.3/§15.4's integrity scope, where `read_workflow`
  reported `ok` and `submit` kept ACCEPTING on a database `verify` reported
  divergent (both reproduced), now declared as deliberately different
  verdicts — the readers and the write gate carry the snapshot-and-history
  verdict, `verify` alone is total, and §15.4 step 4 is extended to
  re-digest the two documents its row hashes bind only by column leaf.
  Rows-only divergence deliberately does NOT freeze mutations: the four
  row-hash tables feed no acceptance decision, so gating on them would deny
  service without protecting one, and what is lost is prompt detection
  rather than soundness. §14.2's unqualified exact-duplicate rule is
  superseded in the fail-closed direction: a replay is a mutating command's
  answer (§15.3) and is now held to the FULL §7.2 gate, not the
  history-only check the wave shipped — reproduced, a workflow with an
  intact history and a tampered projection refused a fresh command with
  `snapshot_divergence` while a duplicate still replayed with events, and
  the two now agree. Also superseded: §18.1's "at every use" as applied to
  `workflow_receipts.receipt_sha256` and `workflow_facts.document_sha256`;
  and the two-commit delivery identity of U-W2 §A.6/§A.7 and U-W2.2 §19.5.

  **Four silences closed**, because the U-W2.2 contract's own closing
  sentence makes an unlicensed behavior a defect: `rebuild` / `verify` /
  `read_workflow` / `read_history` on a workflow identity with no row
  (`rebuild` reports `integrity="history_corrupt"` with the precise
  `reason="workflow_unknown"`, because `STORE_INTEGRITY` is a frozen
  five-member public vocabulary with no "no such workflow" member and
  widening it for one case is rejected); the `where` a rows-only divergence
  carries (`"/rows"`, a schema-safe fixed token); the positional derivation
  of the closed-task status constant, whose frozen VALUE `"done"` (§10.4)
  is unchanged and is now pinned three ways so an appended `TASK_STATUSES`
  member fails a test rather than silently redefining "closed"; and the
  snapshot a refusal carries on an unverifiable history (`None`).

  **Implementation and test consequence**, inside the existing sixteen
  paths and no others: `agentic_os/workflow_store.py`'s four row-hash
  payload builders bind `workflow_id_sha256` from the rendered identity
  rather than the wave's unauthorised bare-decimal leaf, and the intent
  close rebuilds the same member; the replay path runs the full §7.2 gate;
  `agentic_os/db.py`'s `WORKFLOWS_DDL` gains `CHECK (id >= 1)`, which
  reaches fresh and migrated databases through the one `WORKFLOW_TABLES`
  enumeration with no extra migration step;
  `tests/test_v04_workflow_store.py` gains the frozen rows S25–S33 and the
  eleven frozen mutations M-A … M-K, and its crash matrix is corrected to
  the amended labels and mechanisms. `agentic_os/workflow_engine.py`
  and `agentic_os/workspecs.py` stay byte-identical: editing the landed
  reducer is a replan (§19.4), and every U-W2.1 event digest was sealed
  over its identity derivation.

  **Delivery.** Commit `91075d7…` is preserved exactly; this amendment
  lands as a second, independently visible documentation-only commit over
  the same three architecture paths, and the implementation lands as a
  third over the sixteen implementation paths — the U-P2 D-v0.4.50 landing
  model applied a second time, because a governed amendment arrived after
  the first documentation commit rather than before it. No amend, squash,
  reset, or rebase. The closed nineteen-path inventory and U-W2 §A.5's
  no-expansion rule are unchanged; a twentieth path is
  `FAIL — REPLAN REQUIRED`; no standing authority of any kind is created.

  **Rejected alternatives.** Raising `protocols.INT_MAX` — it is the
  IEEE-754-double round-trip guarantee of the whole repository (D-v0.3.5)
  and raising it would silently widen every canonical document in every
  unit. A second serializer for row-hash payloads — §5.8 itself calls a
  competing integrity claim over the same bytes a defect. Reducing the
  identity to 53 bits at minting, or allocating `workflows.id` from a
  sequence — both rewrite a landed unit, invalidate stored history, and
  break the structural "one instance per WorkSpec" agreement between the
  primary key and `UNIQUE(work_spec_sha256)`. Binding the bare decimal
  `str(id)` or its leaf, which is what the wave's unauthorised deviation
  D1 did — a spelling that appears nowhere else in the architecture, and
  freezing two spellings of one identity reintroduces the ambiguity this
  decision removes. Binding the rendered identity as a RAW string member —
  a second deviation from the leaf convention inside the clause being
  repaired, against both live row-hash precedents (`routing.py`,
  `agent_handoffs.py`). Making `read_workflow` recompute every row hash —
  it would turn `list_workflows`, a declared full scan, into an O(total
  rows) integrity sweep of the ledger, and U-W2 §17 already settled that
  integrity is `verify`'s surface. Rewriting commit `91075d7…` or folding
  A2 into A1's bytes — frozen commits and frozen contract text are
  immutable history; amendments supersede and history stays byte-identical
  (D-v0.4.33, D-v0.4.45, D-v0.4.50, and A1's own precedent). Leaving the
  four silences undeclared, or deferring the repair to U-W2.3 — U-W2.2
  cannot land at all under the contradiction, and deferring would land an
  implementation its own contract forbids.

# DECISIONS — Agentic OS v0.4 U-W2.2 deterministic workflow store (Wave 0)

This section continues the `D-v0.4.*` series for the U-W2.2 Wave 0
architecture freeze and the governed U-W2 contract amendment it required:
deterministic local workflow persistence and store semantics, frozen in
`agentic-os-v0.4-u-w2-2-workflow-store-contract.md`, plus governed
amendment A1 appended to the landed
`agentic-os-v0.4-u-w2-workflow-state-engine-contract.md` with the landed
body byte-preserved as that file's exact prefix (D-v0.4.95). Architecture
only — no production code, tests, DDL, migrations, fixtures, CLI, workers,
or adapters ship in this wave. Branch `v0.4-u-w2-2-workflow-store`
(2026-07-25; replan re-freeze 2026-07-26), worktree
`/home/daksh/Projects/agentic-os-u-w2-2`, baseline
`63de8c953f2613a79d6e1bb6052646c669894863` (U-W2.1 deterministic workflow
state engine merged, ledger schema version `"5"`, milestone
`milestone/v0.4-u-w2-workflow-state-engine`; HEAD = `origin/main` =
merge-base = this commit). Future PR title:
`feat(v0.4): U-W2.2 — deterministic workflow persistence`; future commits:
`docs: adopt U-W2 path amendment and freeze U-W2.2 store architecture`,
then `feat(v0.4): add deterministic workflow store` (U-W2 amendment §A.7);
future tag: `milestone/v0.4-u-w2-2-workflow-store`. Prepended per the
established precedent (D-W0.4, reaffirmed in D-v0.2.7, D-v0.4.4);
everything below stays byte-identical, including D-v0.4.81, which
D-v0.4.95 extends and never rewords.

## D-v0.4 decisions (U-W2.2, Wave 0 architecture freeze)

- **D-v0.4.83 — U-W2.2 is persistence only: the landed U-W2.1 reducer is
  consumed byte-unchanged, and the store's whole authority is the set of
  judgments that need stored rows.** U-W2.1 landed at `aedbc49` (merged
  `63de8c9`, tagged `milestone/v0.4-u-w2-workflow-state-engine`) with
  `agentic_os/workflow_engine.py` (2265 lines), the two `workspecs.py`
  acceptance wrappers, and `tests/test_v04_workflow_engine.py` (4921
  lines); `decide`, `fold`, `verify_history`, `AdmissionFacts`,
  `WorkflowDecision`, `WorkflowRefusal`, the thirteen states, nine
  commands, seventeen events, forty-three refusal reasons, nine receipt
  kinds and the 13×13 matrix are all present and closed (verified). The
  store therefore decides exactly six things, all of which a pure
  function provably cannot: does this workflow exist; has this
  `command_id` been accepted, and with this digest; has this `receipt_id`
  been stored, and with this digest; does the artifact's task exist and
  is it open; does the stored projection agree with the stored history;
  did the compare-and-swap win. Legality, revision arithmetic, document
  verification, evidence, binding, ordering and identifier derivation
  stay the reducer's, and the store neither anticipates nor
  second-guesses them. U-W2.3 owns the thirteen CLI leaves, the power
  policy, `README.md` and the observability journal row for a REFUSED
  command; U-W2.R owns the private-runtime adapter in another repository
  against another database; U-W3 owns retry, checkpoint, resume and
  compensation. `workflow_store` never opens a connection, never touches
  a path, and issues SQL against the six new tables plus read-only
  `tasks`/`meta` and write-only `events` — so the local and runtime
  databases cannot be shared even by accident.
- **D-v0.4.84 — Schema version `"6"` is exactly the six frozen tables,
  built from one `db.WORKFLOW_TABLES` constant, with a purely additive
  5 → 6 migration that fabricates no history.** The landed contract's six
  names (`workflows`, `workflow_events`, `workflow_commands`,
  `workflow_intents`, `workflow_receipts`, `workflow_facts`) are verified
  frozen and implementable; the contract's §5 gives each its complete
  column list, CHECK set, UNIQUE set, foreign keys, mutability class,
  retention rule, source-of-truth role and index decision. The
  storage-side closures are the point: thirteen-state and
  seventeen-event enums, biconditionals pinning `from_state IS NULL`
  exactly to `workflow_admitted`, `resulting_revision =
  expected_revision + 1`, `admit_work_spec` exactly to
  `expected_revision = 0`, `resolved` exactly to a receipt id, and
  `fact_scope` exactly to `fact_kind = 'approval'` — plus the four
  receipt CHECKs that mirror `workflow_engine._RECEIPT_*` so the storage
  boundary and the reducer's closed vocabulary cannot disagree between
  builds. No explicit index is added: every hot path is a PK or a UNIQUE
  lookup, and `list_workflows`/`list_outstanding_intents` are declared
  scans (the D-v0.4.28 precedent). `u-w2-workflow-state-v6` creates six
  empty tables FK-parent-first under their real names by iterating
  `db.WORKFLOW_TABLES`, so a migrated schema is BYTE-identical to a fresh
  one and a seventh table cannot be added in one place and forgotten in
  the others. It reads no existing table, rebuilds nothing, re-stamps
  nothing, reads no clock, and — because no table anywhere models a
  workflow today — has nothing to derive history from and derives none:
  a pre-existing task or run gets no workflow, no admission event, and no
  synthetic snapshot. The 3 → 4 / 4 → 5 freeze obligation does not fire,
  because this slice edits none of the constants a shipped step builds
  from.
- **D-v0.4.85 — The `workflows` row is a PROJECTION and the reducer's
  snapshot is rebuilt by `fold(events)` plus the two stored bodies, so
  the seven derived fields need no column.** `decide` requires a sealed
  26-member `aos.workflow-snapshot/v1`; the landed §14.1 column list
  supplies eighteen — the nineteenth, `schema`, is the frozen
  record-identity constant with no column — and gives no column to
  `admission_approval_satisfied`, `intent_seq`, `revoked_intent_ids`,
  `resolved_intent_ids`, `last_seq`, `last_wait_entry_seq` or
  `last_runtime_approval_seq`. Rejected: adding seven columns — it would
  contradict the landed enumeration and its mutable-column list, and it
  would create a second source of truth for values the contract already
  calls derived. Rejected: storing the whole canonical snapshot in a
  column — same objection, plus a body that would drift from the columns
  beside it. Chosen: `_load_snapshot` reads the row, reads the history,
  folds it, splices the two verbatim bodies, re-seals with the engine's
  own two-line idiom, and requires the resulting digest AND the seventeen
  member-backed projection columns (contract §7.2's enumeration; the two
  row timestamps have no snapshot counterpart) to agree with the stored
  row (`snapshot_divergence` otherwise). Consequences, all wanted: the row is exactly what U-W2
  §14.2 calls it; snapshot/history agreement is checked on EVERY command
  rather than only at `verify`; no column is added to a frozen table; and
  the cost is one indexed range read that the reducer's own re-acceptance
  of the stored artifact already dominates. The identity is likewise
  derived, never allocated: `workflows.id` is
  `_workflow_identity(work_spec_sha256)` parsed to an integer, and the
  store renders it back as unpadded `"WF-" + str(id)` because
  `ids.render_id` would zero-pad to `WF-0007` and break every event
  digest — `ids.PREFIXES["workflow"] = "WF"` exists for `parse_id` at the
  U-W2.3 CLI and for nothing else.
- **D-v0.4.86 — Events are reconstituted from their columns, and the
  sealed record digest is the proof the reconstitution is faithful; the
  four row-hash tables (`workflow_commands`, `workflow_intents`,
  `workflow_receipts`, `workflow_facts`) carry `record_schema` row hashes
  while `workflows` and `workflow_events` carry record digests.** The landed
  §14.1 gives `workflow_events` columns, not a `document` column, so the
  store rebuilds each `aos.workflow-event/v1` record from
  `WORKFLOW_EVENT_SCHEMA`, the rendered identity, the row's
  `work_spec_sha256` parent, the same-named columns and the canonically
  parsed `payload_json`. Because the sealed digest covers `workflow_id`
  and `work_spec_sha256`, a spliced parent row makes every event digest
  fail and the workflow reads `history_corrupt` rather than folding
  silently under a false identity — the columns ARE the record, with no
  dual representation to drift. `workflows.content_sha256` and
  `workflow_events.content_sha256` stay the CANONICAL RECORD digests U-W2
  §9 and §7 already assign them, because those two rows are records and a
  second integrity claim over the same bytes would be a defect, not a
  defence. The other four carry ordinary row hashes in the live U-A3
  idiom (`record_schema` key, sha256 text leaves, direct integers,
  `content_sha256` excluded, `sha256(serialize_canonical(payload))`)
  under four new `aos.workflow-*-row/v1` payload identities — which are
  row-hash names, not document schemas, and touch neither U-W2 §13.4's
  six minted record schemas nor the U-X1 registry. They bind `id`, so
  they are finalized by one `UPDATE` inside their own creating
  transaction, the `routing_plans` post-commit-immutable precedent.
- **D-v0.4.87 — `StoreOutcome` is a RETURNED, closed four-status record,
  and a refusal persists nothing anywhere.** `submit` returns
  `accepted`, `replay`, `refused` or `conflict` for every closed outcome
  and never raises `WorkflowRefusal`, because the landed §18's "or a
  refusal" plus the demand to freeze `StoreOutcome`'s meanings for all
  four make refusals statuses of the record rather than exceptions past
  it; the exact refusal object rides along so the CLI's single choke
  point can still exit 1 with a bounded message. `conflict` is a distinct
  status exactly for `command_conflict` and `receipt_conflict` — the one
  refusal class caused by STORED state disagreeing with a delivered
  document, and the one that redelivery can never make legal — so a
  caller branches on a field rather than string-matching a code.
  `replay` is a first-class boolean because the landed §10 and §19 name
  it; `intent is None` off the accepted path because an intent is
  delivered from the outbox, never from a command result; `revision` on
  a replay is the ORIGINAL resulting revision while `snapshot` is the
  CURRENT one, and the possible disagreement is stated rather than
  discovered. A refused or conflicting `submit` writes NO row in any of
  the six tables and NO `events` row: journalling a refusal belongs
  outside the transaction that declined it, which makes it U-W2.3's, and
  the declared consequence is that until U-W2.3 ships a refusal leaves no
  trace in `aos.db` at all.
- **D-v0.4.88 — The public store API is exactly seven functions and six
  types, and `WorkflowStoreError` carries three infrastructure codes that
  never widen the frozen 43-reason vocabulary.** `submit`,
  `read_workflow`, `list_workflows`, `read_history`,
  `list_outstanding_intents`, `rebuild`, `verify` — with `StoreOutcome`,
  `WorkflowRecord`, `HistoryView`, `IntentView`, `RebuildResult` and
  `VerifyReport`. U-W2.3 may add none; needing one is a replan trigger
  rather than a quiet edit to a U-W2.2 file. The three codes —
  `store_schema_unsupported`, `store_argument_invalid`,
  `store_unavailable` — are facts about the LEDGER, not about a workflow,
  which is why they cannot be members of a vocabulary the pure reducer
  owns; every workflow-scoped failure, including a hostile row, still
  lands on one of the forty-three. `WorkflowRecord.task_id` is the
  integer row id rather than a rendered `T-<n>`, because `T-7` and
  `T-0007` are both pattern-valid and the admitted string lives verbatim
  in the snapshot and the admission payload — re-rendering would state a
  string nobody wrote.
- **D-v0.4.89 — One `BEGIN IMMEDIATE` transaction per accepted command,
  in one frozen mutation order per path, through nine named helpers, and
  the whole write path reads no clock.** `BEGIN IMMEDIATE` is the first
  statement inside the single `db.transaction` block (the live
  `routing.py`/`agent_handoffs.py` "write lock before the re-reads"
  idiom), so dedupe, snapshot read, decision, writes and journal form one
  serialized critical section and a deferred begin's wasted-decision
  failure mode never exists. The non-admission order is command row →
  events → intent → intent closures → receipt → fact → snapshot CAS →
  journal; the admission order differs and is frozen separately, because
  `workflow_commands.workflow_id` is an immediate foreign key and the
  parent row must exist first. The CAS is `UPDATE workflows … WHERE id =
  ? AND revision = ?` with a required rowcount of 1 (`revision_mismatch`
  otherwise, the code the landed §10 pairs with it); the admission gate
  is the `workflows` INSERT under `UNIQUE(work_spec_sha256)`, pre-checked
  deterministically under the lock so the `IntegrityError` mapping is a
  backstop rather than a control path; each intent closure is itself a
  `WHERE status = 'outstanding'` CAS, so a second close is impossible.
  The nine mutation helpers (`_insert_workflow`, `_insert_command`,
  `_insert_events`, `_insert_intent`, `_resolve_intent`,
  `_insert_receipt`, `_insert_fact`, `_cas_snapshot`, `_journal`) are
  frozen ARCHITECTURE because the crash matrix injects at them. Every
  timestamp in all six tables is the accepted command's own `created_at`,
  so the store imports no time module, the six-table write is a pure
  function of the command and the prior rows, and a crash-and-retry
  writes byte-identical rows; the only wall clock in the transaction is
  `events.emit`'s `ts`, which the journal framework owns. One journal row
  is written PER APPENDED EVENT, not per command, because `action` is the
  event name and one row would have to drop the other.
- **D-v0.4.90 — Two dedupe axes, both evaluated before `decide`:
  commands by `command_id` + recomputed digest, receipts by `receipt_id`
  + recomputed digest.** An exact command duplicate returns the original
  events and resulting revision from the
  `[event_seq_first, event_seq_last]` range without calling `decide`; a
  digest disagreement is `command_conflict`; a duplicate of a REFUSED
  command is re-evaluated and refuses identically, because refusals store
  nothing. The receipt axis is load-bearing and its ORDERING is the
  discriminating decision: a redelivered `accepted` receipt arrives after
  the workflow has moved to `scheduled`, so handing it to the reducer
  would produce `receipt_out_of_order` for a receipt that was in fact
  applied — dedupe first turns it into the accepted no-op the landed
  §13.3 promises, and the original events are recoverable because every
  receipt-driven event payload carries `receipt_id` and `receipt_sha256`.
  Both digests are RECOMPUTED from the stored or delivered bytes, never
  read from a document's own member, and a same-digest row naming a
  different workflow is a conflict rather than a replay, because the
  digest covers `workflow_id` and that pair can only exist through
  tampering. Nothing is merged, nothing is guessed, and nothing is ever
  pruned: the contract's §14.4 states, table by table, exactly which
  guarantee a deletion would break, which is why no `DELETE` statement
  and no prune surface exists anywhere in the slice.
- **D-v0.4.91 — Contention handling is SQLite's already-configured
  bounded busy timeout and nothing else, which is why it is a storage
  primitive and not U-W3 retry.** `db.connect` already sets
  `timeout=5.0` and `PRAGMA busy_timeout=5000`; the store adds no loop,
  no sleep, no backoff, no re-issue and no automatic re-decision, and a
  post-timeout `OperationalError` becomes `store_unavailable` for a human
  to retry. The distinction is exact rather than rhetorical: lock waiting
  carries no workflow semantics, consumes no attempt budget, appends no
  event and changes no state, and the same command produces the same
  decision once the lock frees; U-W3 retry is re-EXECUTION of work that
  advances an attempt counter, is bounded by the artifact's
  `retry.max_attempts`, and changes what the workflow claims about the
  world. A `revision_mismatch` refusal is not a retry either — the caller
  must mint a NEW `command_id`, which is a fresh recorded decision. If
  the slice contained any automatic re-issue, U-W2 §0.2's "no retry loop
  of any kind" would be false; it contains none, and an AST test proving
  the absence of `while`, `sleep` and recursive `submit` is what keeps
  that honest.
- **D-v0.4.92 — Integrity is REPORTED, never repaired, under a closed
  five-member `STORE_INTEGRITY` vocabulary.** `ok`, `history_corrupt`,
  `history_unknown_event`, `policy_version_unsupported` and
  `snapshot_divergence` are the only verdicts; the contract's §15.2 maps
  every corruption — seq gap, duplicate seq, reordering, digest mismatch,
  chain break, misplaced admission event, broken revision arithmetic,
  unknown event name, unsupported policy version, unparseable payload,
  non-text document, divergent projection, re-digest failure — to its
  exact verdict AND states whether storage can even express it. Duplicate
  `seq`, reordering and unknown event names are declared UNREACHABLE
  through this store (the `UNIQUE(workflow_id, seq)` and `event` CHECKs
  forbid them), and the contract tests the constraint rather than
  pretending to test a store-side path that cannot exist. While a
  workflow fails verification its mutating commands refuse with the exact
  code and write nothing, while every read path stays total — a typed
  `integrity` field and an `unreadable_seq`, rather than a printed
  warning. `verify` rebuilds, compares the seventeen member-backed
  projection columns, the
  snapshot digest, both stored bodies against the digests
  `workflow_admitted` recorded, and all four row hashes, then returns a
  report; it opens no transaction and issues no write, and a whole-file
  byte comparison proves it. Recovery is a human restoring a verified
  backup, never the engine editing history.
- **D-v0.4.93 — Persisted rows are untrusted input, and the defences are
  structural rather than procedural.** Every digest is recomputed from
  stored bytes at every use; the reducer additionally re-runs the U-W1
  acceptance gate on the stored artifact on every command, so a body that
  merely re-digests is not thereby trusted. Every statement is
  parameterized and the only interpolated identifiers are the six frozen
  `db.py` table-name constants; no `DELETE`, `DROP`, `ALTER`, `ATTACH`,
  `PRAGMA`, `executescript`, `eval`, `exec`, `compile`, `__import__`,
  `subprocess` or `socket` appears in the module. Oversized and malformed
  bodies are bounded by the spine's own `MAX_ARTIFACT_BYTES`,
  `MAX_ARRAY_ITEMS`, `MAX_STRING_CHARS` and `INT_MAX`, and the reducer
  refuses at admission any instance whose snapshot could not survive its
  own maximum growth — so a workflow that admits can always be advanced
  and can never brick. Every raising call site is mapped explicitly:
  `WorkflowRefusal` to a `StoreOutcome`, `ProtocolError` to an integrity
  verdict or `command_malformed`, hostile-row shape errors to a verdict
  via type checks BEFORE the access rather than broad excepts, the one
  `workflows` INSERT's `IntegrityError` to `workflow_exists`, and every
  other `sqlite3.Error` to `store_unavailable`. Stored text that reads as
  an instruction — "run this tool", "reveal your prompt", "widen your
  scope" — is DATA structurally: it never becomes SQL, never becomes a
  message, never becomes a path, and is never executed, and the frozen
  test proves a hostile corpus produces byte-identical decisions to a
  benign one. Refusal messages carry a closed code, a schema-safe path
  and a fixed hint; a credential-shaped value planted in every text
  column of all six tables must appear in no message, no diagnostics and
  no journal row. This decision states the limit honestly: the guarantee
  is that no PARTIAL tampering survives, not that a fully coherent
  forgery is detectable — and a fully coherent forgery is a different
  workflow identity, not a corrupted one.
- **D-v0.4.94 — The exact implementation boundary is the nineteen paths of
  contract §19 — the closed inventory U-W2 governed amendment A1
  authorizes — and nothing in it is standing authority.** Four production
  paths (`agentic_os/workflow_store.py` new; `agentic_os/db.py`,
  `agentic_os/migrations.py`, `agentic_os/ids.py` modified) and one new
  test module are what the landed §18 named. `db.SCHEMA_VERSION = "6"`
  mechanically breaks hard-coded version assertions in eight existing test
  modules (`test_core.py:116`,
  `test_v02_migrations.py:199,201,211,226,234,1075,1084`,
  `test_v02_power_modes.py:1380`, `test_v03_memory_claims.py:191`,
  `test_v03_memory_graph.py:253,256,280,288,290-294,314,322,715,721`,
  `test_v04_agent_passports.py:205-208,219,229,262`,
  `test_v04_agent_catalog.py:851-855,1381-1394`,
  `test_v04_routing_handoffs.py:343-346,348,358,363-372,379,433,1062,1063,1065`),
  and the three historical fixtures must drop the six new tables or a
  "v1"/"v2"/"v3" workspace would carry v6 tables and the 5 → 6 step's
  `CREATE TABLE` would fail when the fixture was migrated forward. This
  is not novel: commit `7c5fea4`, the U-A3 4 → 5 bump, touched exactly
  this class of file for exactly these reasons (verified by
  `git show --stat`). The landed §18 forbade these paths three ways
  (§0.3, the five-path table with its closure rule, §19.22), so the
  audited candidate's attempt to declare them from inside this
  subordinate contract was an unauthorized amendment — the replan
  trigger. U-W2 governed amendment A1 (D-v0.4.95) now supersedes exactly
  those clauses and authorizes exactly these edits, in six frozen classes
  restated per file in contract §19.3: version-literal rebase;
  registry/plan-list step addition; nine enumerated ordinal-bearing
  method renames; ONE meaning-rebased assertion
  (`test_no_version_six_transition_exists`, re-scoped to the new ceiling
  and renamed — declared, not hidden under "no meaning changes"); one
  migration-target rebase (`migrate(target="5")` → `"6"`); and one
  fixture drop loop per fixture. No test is deleted, skipped or
  weakened; `FIXTURE_TABLES` is not extended (it enumerates tables whose
  CONTENTS a migration compares, and the six do not exist before); no
  new fixture module is added because the equivalence test migrates
  `build_v3_workspace` forward exactly as U-A3's does. The three Wave-0
  architecture documents (`DECISIONS.md`, the amended landed contract,
  this contract) are paths 17–19, per the landed §18's own
  Wave-0-documents rule. Nine further paths are named as deliberately
  UNCHANGED with their reasons — the reducer, the compiler seam, the
  spine, `models.py`, `ops.py`, doctor, backup/export/mirror, packaging
  and CI — so that "not in the table" is a decision rather than an
  omission. Rejected: a standing licence for future bumps ("has always
  required and always will" — an escape hatch; each future bump earns its
  own governed amendment).
- **D-v0.4.95 — Governed amendment A1 to the landed U-W2 contract:
  appended, byte-preserving, minimal, and one-shot; D-v0.4.81 is
  extended, never reworded.** The U-P2 trust-boundary mechanism
  (D-v0.4.45–50) applied to U-W2: amendment A1 names the audit finding it
  resolves, quotes every superseded clause verbatim with its replacement
  (U-W2 §A.3.1: the five-path U-W2.2 slice table; the closure rule's
  table binding; §0.3's every-test/fixture clause for exactly the eleven
  files; §19.22's byte-unchanged clause; the §1-index exhaustiveness
  claim of D-v0.4.81 and its one-PR delivery identity, already superseded
  in ratified practice by the U-W2.1 merge as PR #20; and the per-event
  reading of §14.2's journal clause), enumerates everything NOT
  superseded (§A.3.2), replaces the five-path set with the closed
  nineteen-path inventory (§A.4), and re-attaches the exhaustiveness rule
  over the amended tables with an explicit negative boundary: no
  production, packaging, protocol, CLI, migration, delivery-control, or
  unrelated documentation file beyond the nineteen named paths, no edit
  class beyond the six frozen ones, one delivery only, and no standing
  authority for any future wave, bump, or unit (§A.5). Representation,
  forced and documented: the replan session's write boundary is exactly
  three repository paths, so A1 is an append-only addendum INSIDE the
  landed contract file — the landed body stays byte-identical as the
  file's exact prefix (original-body SHA-256
  `409745bbba541cb81a40da5384a97127db40c38f8f8e116f334706c70dc53aaf`,
  machine-checked against `git show` at the baseline), where U-P2's
  amendment was a sibling file. Landing mirrors U-P2's D-v0.4.50 model:
  the amendment lands first as one documentation-only commit (`docs:
  adopt U-W2 path amendment and freeze U-W2.2 store architecture`,
  exactly the three Wave-0 documents), then the implementation commit
  (`feat(v0.4): add deterministic workflow store`, exactly the sixteen
  implementation paths), both inside the one U-W2.2 PR through the U-P2
  gate; U-W2.1's landed bytes are not retroactively modified. Rejected:
  rewriting the landed contract in place (frozen history — amendments
  supersede, per D-v0.4.33/D-v0.4.45); a sibling amendment file (a fourth
  repository path outside the session's authorized writes); the audited
  candidate's self-amendment (a subordinate contract cannot amend its
  landed parent); dropping schema v6 from U-W2.2 (strands the landed §14
  persistence architecture and only defers the same amendment); landing
  the test edits as a quiet extension (exactly what §18 forbids).

# DECISIONS — Agentic OS v0.4 U-W2 deterministic workflow state engine (Wave 0)

This section continues the `D-v0.4.*` series for the U-W2 Wave 0
architecture freeze: the deterministic workflow state engine and
runtime-queue integration unit, frozen in
`agentic-os-v0.4-u-w2-workflow-state-engine-contract.md`. Architecture
only — no production code, tests, CLI, persistence, scheduling, or
execution ship in this wave. Branch `v0.4-u-w2-workflow-state-engine`
(2026-07-24), worktree `/home/daksh/Projects/agentic-os-u-w2`, baseline
`0a69a1c1654671cd48577e23252a9c06e2cffba9` (U-W1 deterministic WorkSpec
compiler merged, ledger schema version `"5"`, milestone
`milestone/v0.4-u-w1-workspec-compiler`; HEAD = `origin/main` =
merge-base = this commit). Future PR title:
`feat(v0.4): U-W2 — deterministic workflow state engine`; future tag:
`milestone/v0.4-u-w2-workflow-state-engine`. Prepended per the
established precedent (D-W0.4, reaffirmed in D-v0.2.7, D-v0.4.4);
everything below stays byte-identical.

## D-v0.4 decisions (U-W2, Wave 0 architecture freeze)

- **D-v0.4.71 — Workflow ownership is outcome B: public kernel in
  `agentic-os` plus a transport-neutral queue-adapter contract; the
  runtime adapter is an explicit cross-repository slice.** The
  authoritative workflow lifecycle lives in `agentic-os` (the governance
  plane already owns tasks, approvals, evidence, and decisions —
  blueprint §5.1 — and every lifecycle gate here is a governance gate).
  Queue integration is a record contract:
  `aos.workflow-queue-intent/v1` out, `aos.workflow-queue-receipt/v1`
  in; the runtime-side adapter (slice U-W2.R, contract §18) lives in the
  private `ai-company-runtime` repository, pins both record shapes by
  content hash at the U-W2 milestone tag, and never shares a database
  with agentic-os. Rejected: A (single-repository U-W2) — the live tree
  contains no queue, lease, or dispatch abstraction at all (verified;
  the only "queue" occurrences are BFS work-list variables and a test
  fixture string), the working queue is the private runtime's Postgres
  queue which blueprint §9.5 preserves and §5.1 forbids agentic-os to
  own, so a truthful single-repository queue integration does not
  exist. Rejected: C (cross-repository U-W2A/U-W2B/U-W2C split) — a
  third protocol repository is explicitly premature below three
  independent consumers (blueprint §5.1), and splitting the kernel
  itself would move authoritative lifecycle state out of the governance
  plane and make the private repository a build dependency of the
  public one; B places the split at the actual trust boundary (records,
  not code) while still naming the required cross-repository change
  instead of hiding it inside one worktree.
- **D-v0.4.72 — Lifecycle vocabulary: thirteen authoritative states;
  `proposed` stays authoring-plane; four immutable terminals; the
  complete matrix is frozen as data; `compensating` edges are reserved
  to U-W3 under transition-policy v1.** The blueprint §9.2 vocabulary
  is adopted in full; `proposed` names pre-compile authoring (a task
  plus an `aos.work-spec-authoring/v1` input — U-W1's domain) and is
  never a `workflows.state` value, because no instance can exist before
  an artifact digest exists to bind state to. States: `compiled`,
  `validated`, `awaiting_approval`, `scheduled`, `running`,
  `waiting_input`, `waiting_approval`, `paused`, `compensating`,
  `succeeded`, `failed`, `cancelled`, `compensated`; terminals are the
  last four and accept no command (the `revoked`/closed-task
  precedent). The complete 13×13 matrix (contract §5.2) has 25 active
  edges, 3 reserved edges (`running → compensating`,
  `compensating → compensated`, `compensating → failed`, refused
  `transition_reserved` until U-W3 ships policy v2 — the
  `TERMINATION_OUTCOMES`/`LOCAL_TERMINATION_OUTCOMES` honesty split
  applied to transitions), and one creation pseudo-edge
  (`∅ → compiled` via admission). Cancellation is local and immediate
  from `compiled`/`validated`/`awaiting_approval` (AOS is source of
  truth before queue acceptance) and two-phase
  (`cancel_requested` intent → verified `cancelled` receipt) from every
  post-dispatch nonterminal state; `compensating → cancelled` is
  illegal in every frozen version (abandoning a compensation mid-flight
  would be a silent cleanup failure). Two scoping rules keep the matrix
  exact: it governs STATE-CHANGING edges only (an accepted stateless
  command traverses no cell and records `to_state` null), and under
  policy v1 no command or receipt kind targets `compensating`/
  `compensated`, so two of the three reserved cells have no driver and
  cannot be attempted at all — `transition_reserved` is a reducer-level
  refusal v2 activates, not a claim that a v1 caller can reach them.
  Rejected: inventing a `dispatching` or `cancel_requested` state (the
  vocabulary is closed; pending intents are snapshot facts, not states);
  immediate local cancellation after dispatch (AOS cannot truthfully
  claim `cancelled` while a worker may be running); adopting blueprint
  §9.2's `awaiting_approval → scheduled` arrow as an edge — the
  blueprint sentence is a reading order, while `scheduled` means "the
  runtime holds the work" and is reachable only through a queue
  `accepted` receipt, so a satisfied admission approval returns the
  instance to `validated` and dispatch proceeds from there. The
  deviation is declared in contract §5.1 rather than left for an
  implementer to discover.
- **D-v0.4.73 — Closed command/event/refusal/intent/receipt
  vocabularies; a typed command envelope; all new records are `aos.*`
  canonical records with a named registry-promotion trigger.** Nine
  commands (`admit_work_spec`, `validate`, `request_approval`,
  `record_approval`, `request_dispatch`, `revoke_dispatch`,
  `request_cancel`, `record_queue_receipt`, `record_result`), seventeen
  events, forty-three refusal reasons in canonical emission order (the
  `GOVERNANCE_REASON_CODES` idiom), two intent kinds
  (`dispatch`/`cancel`), nine receipt kinds (`accepted`, `rejected`,
  `started`, `waiting_input`, `waiting_approval`, `paused`, `resumed`,
  `cancelled`, `failed`). Every command carries `schema`
  (`aos.workflow-command/v1`), `command`, `command_id` (UUID dedupe
  identity), `workflow_id` (`WF-n`; absent exactly on admission),
  `expected_revision`, `actor` (`PROVENANCE_PATTERN`), `source`
  (`cli` | `runtime_adapter`), `created_at` (caller-supplied instant —
  the no-clock rule), optional `trace`, a closed per-verb `payload`,
  and a recomputed `content_sha256`. The six record schemas
  (`aos.workflow-command/v1`, `aos.workflow-event/v1`,
  `aos.workflow-snapshot/v1`, `aos.workflow-queue-intent/v1`,
  `aos.workflow-queue-receipt/v1`, `aos.workflow-approval-fact/v1`) are
  internal canonical records in the established `aos.*` house style —
  deliberately not U-X1 registry artifacts: the queue records cross to
  exactly one known counterparty that vendors them by hash; promotion
  to registry artifacts is triggered by three independent consumers or
  a signature/attestation need across a trust domain, and would be
  additive new identities. The nine receipt kinds and nine of the
  seventeen events form a bijection frozen as a table in contract §7
  (`accepted → dispatch_accepted` … `failed → workflow_failed`); the
  other eight events are command-driven, and exactly two names
  (`workflow_cancelled`, `workflow_failed`) carry a second driver. Every
  refusal reason likewise has one stated trigger: the seven that no
  other section names are tabulated in §8. Rejected: growing the U-X1
  registry now (edits the frozen spine for a two-party exchange);
  free-form event payloads (closed enum/identifier/digest payloads
  only); leaving the receipt→event mapping implicit because it is
  derivable (a test cannot be written against a surface no section
  freezes).
- **D-v0.4.74 — The reducer is a pure function: snapshot + typed
  command + verified facts → next snapshot + events + optional queue
  intent.** `workflow_engine.decide(snapshot, command, facts)` performs
  no clock, filesystem, network, database, queue, environment, locale,
  randomness, or model read; the module imports `protocols`,
  `workspecs` (the public acceptance seam), `secretscan`, `utils`
  (`AosError`, the refusal base), `dataclasses`, `hashlib`, and `re`
  only, with `datetime` excluded (the workspecs calendar-arithmetic
  rule), enforced by an AST import-discipline test over the module's own
  import statements — never the transitive closure, since `protocols`
  legitimately imports `os` and `datetime`. The reducer's first argument
  is the `aos.workflow-snapshot/v1` record, whose field list contract §9
  freezes (including `intent_seq`, the revoked/resolved intent id
  tuples, `last_seq`, and the two approval-ordering seqs) — without it
  the derived intent identifiers, `receipt_superseded`, and
  `approval_fact_missing` would not be computable from a pure function.
  `replay` is NOT a reducer output: exact-duplicate detection is a
  `workflow_commands` lookup plus an event-range read, so the store
  answers it before calling `decide` and reports it on `StoreOutcome`. Document verification (artifact, report,
  approval fact, result envelope, receipt) is pure computation inside
  the engine; the only shell-verified inputs are the two admission
  ledger facts (`task_exists`, `task_open`). Companions `fold(events)`
  and `verify_history(events)` are pure; every accepted document is
  snapshotted by canonical round-trip on intake and every return is
  freshly built (the U-W1 §15 mutation-isolation rule). Rejected:
  letting the store pass open connections or clocks into the reducer;
  verifying documents in the shell (it would split one trust gate into
  two half-gates).
- **D-v0.4.75 — Revision compare-and-swap and dedupe: +1 per accepted
  command, exact-duplicate replay, conflicting-duplicate refusal,
  out-of-order refusal.** `revision` starts at 1 at admission and
  increments by exactly one per accepted command — stateless commands
  included, since every accepted command appends at least one event.
  `expected_revision` is mandatory; mismatch refuses
  `revision_mismatch`, and for every command except `admit_work_spec`
  the store enforces the same guard as a literal SQL compare-and-swap so
  the semantic gate and the storage gate must agree. `admit_work_spec`
  has no row to update: its storage gate is the
  `UNIQUE(work_spec_sha256)` INSERT refusing `workflow_exists`, and its
  `expected_revision = 0` is a semantic assertion only. An exact
  duplicate (same `command_id`, same recomputed canonical digest)
  replays the original outcome (`StoreOutcome.replay=True`, no new
  event, no revision change, no new intent, and `intent is None` — the
  outbox, not a command result, is the delivery channel); a
  conflicting duplicate (same id, different digest) refuses
  `command_conflict`; a repeat of a refused command re-evaluates and
  refuses identically (refusals store nothing). Receipts dedupe by
  `receipt_id` with the same replay/conflict rules. Rejected: engine-
  side command queueing or reordering (the caller re-reads and retries
  deliberately); last-writer-wins on conflicting duplicates.
- **D-v0.4.76 — WorkSpec admission verifies five things fail-closed;
  blocking statuses never create an instance;
  `requires_external_authority` admits but cannot dispatch without an
  approval fact; one instance per WorkSpec digest.** Admission
  verifies, in order: artifact (spine validation via
  `workspecs.accept_work_spec`; refusal wraps the closed spine code as
  `admission_artifact_invalid`), report self-digest and
  report→artifact binding (`workspecs.accept_compile_report` — the
  frozen sidecar rule), registry binding
  (`registry_state.registry_version` = live `REGISTRY_VERSION` and
  `work_spec_schema_sha256` = the live WorkSpec schema digest;
  `snapshot_sha256` is recorded as the compiler's digest-sealed
  attestation, not re-derived), compile status (`invalid`,
  `unresolved`, `ineligible` refuse `admission_status_blocking`;
  `requires_external_authority` admits with `approval_required=true`;
  `warning`/`valid` admit), and the shell-verified task facts (the
  artifact's `aos_task_id` must name an existing, non-`done` task).
  `work_spec_sha256` is UNIQUE — re-admission refuses
  `workflow_exists`; a revised WorkSpec is a new digest and a new
  instance. Both documents are stored verbatim (the
  `agent_passports.document` precedent) because `verify_binding`
  against result envelopes needs the exact body; digests are recomputed
  from stored bodies at every use.
  `approval_required := (status = requires_external_authority) OR
  (artifact declares policy_refs.approval_ref)` — a declared approval
  reference obliges a recorded fact before dispatch and is never itself
  treated as satisfaction. Rejected: admitting blocking statuses as
  parked instances (a blocking status that exists as a row is one bug
  away from scheduling); deriving `succeeded`-side facts at admission.
- **D-v0.4.77 — Approval and evidence are recorded external facts;
  U-W2 generates neither; the `succeeded` evidence predicate is exact;
  revocation is deferred to U-W5.** Approval facts are
  `aos.workflow-approval-fact/v1` records binding `work_spec_sha256`,
  with scope `admission` (drives `awaiting_approval → validated`; when
  the artifact declares `policy_refs.approval_ref` the fact must repeat
  it byte-exact, because that reference names the pre-authored admission
  authority) or `runtime` (stateless record in `waiting_approval`,
  binding by digest and scope only and carrying the approving system's
  OWN opaque reference — a mid-run approval is a distinct, later-minted
  record, so demanding the artifact's authored reference would either
  refuse every honest runtime fact or make the engine record an approval
  nobody issued). The exit edge is the runtime's `resumed` receipt,
  which refuses `approval_fact_missing` unless a runtime-scope
  `approval_recorded` EVENT carries a `seq` above the most recent
  `run_waiting_approval` event — the ordering lives on the event
  history, since `workflow_facts` has no `seq`. Who may approve is a
  governance policy this
  unit does not judge; approval revocation has no v1 path (U-W5's
  semantic interrupts own `approval.revoked`). `succeeded` requires:
  spine-valid result envelope, `verify_binding` against the stored
  WorkSpec (digest and `work_spec_id`), `attempt` within the artifact's
  declared budget, outcome `success` with `retryable=false`
  (`result_inconsistent` otherwise), and `counted ≥
  expected_result.min_evidence_count` where an item counts iff its kind
  is in `expected_result.evidence_kinds` AND `ref.strip()` and
  `claim.strip()` are non-empty (the D-v0.2.36 blank-proof rule);
  `fail` maps to `failed` with no evidence minimum; `partial`/`unknown`
  refuse `result_outcome_inconclusive` and mutate nothing (retry and
  salvage are U-W3's). There is deliberately no `--no-evidence`
  counterpart on the workflow plane; the THRESHOLD, however, is the
  artifact's own digest-bound declaration, and the live schema admits
  `min_evidence_count = 0` as `valid`, so such a WorkSpec succeeds with
  no evidence — the author's admitted declaration, not an engine
  override, and without the journaled reason the task plane demands
  (declared in contract §5.3, §12.2, §22). Rejected: requiring coverage
  of every declared evidence kind (`evidence_kinds` enumerates
  acceptable kinds, not mandatory ones — the U-W1 subset reading);
  treating `partial` as terminal failure (dishonest about salvageable
  work); imposing a U-W2 evidence floor of 1 (it would admit `valid`
  WorkSpecs whose success is unreachable — a silent trap worse than the
  declared behavior).
- **D-v0.4.78 — The queue handshake is two typed records with derived
  identifiers, at-least-once delivery, verbatim inbox storage, and a
  frozen source-of-truth split.** Dispatch intents embed the full
  canonical WorkSpec document (bounded by the spine's 256 KiB artifact
  bound; the receiver re-verifies it against `work_spec_sha256`) plus
  `report_sha256`, `snapshot_sha256`, `compile_status`, a validated
  `queue_route` slug (default `default`), and derived identifiers that
  are pure functions of history (`intent_id` = UUIDv8 of a
  domain-separated digest over `work_spec_sha256` and the per-workflow
  intent sequence; `idempotency_key` = `wfd-` + 40 hex of a second
  domain-separated digest — distinct per re-dispatch, stable under
  replay). Receipts are runtime-minted (`receipt_id` UUID),
  kind-closed, stored verbatim on acceptance; `accepted`/`rejected`
  must bind an outstanding `intent_id` (`receipt_unbound` /
  `receipt_superseded` otherwise); `runtime_task_uuid` is minted by the
  runtime at acceptance (must match any artifact-declared value) and
  every later receipt must carry it (`runtime_uuid_mismatch`).
  Rejection returns the workflow to `validated` (stateless
  `dispatch_rejected`; re-dispatch mints a NEW intent). The adapter
  delivers receipts per workflow in causal order; the reducer's
  legality gate enforces it (`receipt_out_of_order` refusals are
  redeliverable — refusal-then-redeliver IS the ordering protocol,
  though redelivery is the remedy only for a receipt that arrived EARLY;
  one that can never become legal refuses permanently and is dropped).
  Each kind's meaning is frozen in contract §13.2 so two adapter authors
  cannot read it differently: `accepted` is a durably committed queue
  row (so AOS `scheduled` maps to the live queue's `pending`, never to
  its `scheduled_at`/`available_at` columns), `started`/`resumed` assert
  occupancy of the runtime's EXECUTION PLANE rather than that a worker
  is executing this instant — which is why runtime-internal retry and
  lease requeue emit no receipt and stay invisible to the ledger — and
  `rejected` names only a queue's refusal to ADMIT an intent, a terminal
  rejection of already-started work being reported as `failed`. Because
  the intent embeds the full WorkSpec, the adapter must enqueue with the
  artifact's `retry.max_attempts` (default 1) so the two attempt budgets
  agree; enqueue parameters are the adapter's to choose, so this needs
  no runtime change. Revocation before AOS has OBSERVED acceptance is
  advisory, not authoritative: AOS cannot un-enqueue a committed row,
  so the task may keep running and a re-dispatch may produce a second
  runtime task for the same WorkSpec (declared, contract §22).
  Source of truth: the AOS ledger for lifecycle state, admission,
  approvals, success judgment, and intents; the runtime for queue
  membership, leases, workers, attempts, and the `runtime_task_uuid`
  namespace; records are the only channel in either direction.
  Rejected: digest-only dispatch intents (the runtime would need a
  second channel to fetch the work, which does not exist); exactly-once
  delivery pretenses (at-least-once with idempotent replay is what the
  outbox/inbox pattern can honestly provide).
- **D-v0.4.79 — Persistence is layered: pure kernel; local append-only
  `workflow_events` plus a derived hash-coupled `workflows` snapshot;
  `workflow_intents` outbox and `workflow_receipts` inbox;
  `workflow_facts` and `workflow_commands`; schema v6 purely additive;
  one transaction per accepted command; verification reports and never
  rewrites.** Six new tables (contract §14.1) land via migration
  `u-w2-workflow-state-v6` (5 → 6), the U-A3 idiom: empty,
  FK-parent-first, built from the same `db.py` constants as a fresh
  init; `db.SCHEMA_VERSION` becomes `"6"` and the normal-command version
  gate is unchanged. Byte-identity and purity are scoped as the live
  U-A3 precedent scopes them: fresh and migrated `sqlite_master.sql`
  match FOR THE SIX NEW TABLES, and the step function touches no
  existing row and reads no clock — the framework's own
  `meta.schema_version` bump and per-step `events.emit` journal row are
  excluded, exactly as `tests/test_v04_routing_handoffs.py` excludes
  them. The authoritative record is `workflow_events` (plus verbatim
  stored documents); the `workflows` row is a derived snapshot whose
  every field except the two document bodies is rebuildable by `fold`
  (the bodies are deliberately absent from event payloads, which carry
  digests only, so they are admission-time immutable columns re-verified
  against the recorded digests), guarded by revision CAS, with
  `state`/`revision`/pending-intent/uuid/`updated_at`/`content_sha256`
  moving only together inside one transaction that also appends the
  event row(s), the accepted-command row, any intent/receipt/fact row,
  and one redacted `events.emit` journal row — commit together or roll
  back together (the ops invariant). Crash points: pre-commit leaves
  nothing; post-commit pre-delivery leaves a re-driveable outstanding
  intent (outbox pattern; the queue dedupes deliveries on the
  idempotency key); post-commit pre-output makes the retried command an
  exact-duplicate replay. Corrupt, reordered, or unknown-version
  history refuses (`history_corrupt`, `history_unknown_event`,
  `policy_version_unsupported`); `workflow verify` re-folds and
  compares (`snapshot_divergence`), reporting only — recovery is a
  human restoring a verified backup, never the engine rewriting
  history. `ids.py` gains `"workflow": "WF"` (the two-letter U-M3/U-A3
  precedent). Rejected: a pure in-memory-only kernel (workflow state
  must survive a process exit to be a system of record); sharing any
  table with the runtime (forbidden across the plane boundary);
  mutable history with snapshot-only truth (unauditable).
- **D-v0.4.80 — Updateability: integer `TRANSITION_POLICY_VERSION`
  starting at 1 with U-W3 as version 2; versioned `/v1` record schemas;
  stable strings, never ordinals; frozen per-version replay;
  unknown-version refusal; schema changes migrate, history never
  does.** Every workflow row and event records the policy version it
  was decided under; a build refuses commands it cannot honor
  (`policy_version_unsupported`) and replays every shipped version
  forever via frozen per-version transition tables (the
  `_V2_MEMORY_CLAIM_DDL` frozen-history trade applied to policy data).
  State/edge additions require a new policy version plus an additive
  CHECK-widening migration; removals never happen (states can stop
  being reachable, never stop being readable). A new receipt kind
  requires a new receipt schema version (closed CHECKs and closed
  vocabularies must not disagree between builds); new refusal reasons
  are emission-side and may grow within a version. Rejected: enum
  ordinals or implicit ordering anywhere; auto-migrating old histories
  to new policy semantics (replay must be byte-stable across
  upgrades).
- **D-v0.4.81 — Implementation slices and exact paths: three ordered
  commits in the one frozen agentic-os PR, plus the explicit U-W2.R
  adapter delivery in `ai-company-runtime`.** U-W2.1 pure kernel
  (`agentic_os/workflow_engine.py` new;
  `tests/test_v04_workflow_engine.py` new; `agentic_os/workspecs.py`
  modified ONLY to add the behavior-identical public wrappers
  `accept_work_spec`/`accept_compile_report` over the existing private
  gates — the one U-W1-file edit, pinned by test). U-W2.2 persistence
  (`agentic_os/workflow_store.py` new; `agentic_os/db.py`,
  `agentic_os/migrations.py`, `agentic_os/ids.py` modified;
  `tests/test_v04_workflow_store.py` new). U-W2.3 CLI/docs
  (`agentic_os/cli.py`, `agentic_os/power.py`, `README.md` modified;
  `tests/test_v04_workflow_cli.py` new) with the thirteen frozen
  CLI leaves and their power classes (contract §16), and — since Wave 0
  commits nothing — the two Wave-0 documents themselves, `DECISIONS.md`
  (this section) and
  `agentic-os-v0.4-u-w2-workflow-state-engine-contract.md`. Naming them
  is load-bearing, not bookkeeping: every prior unit landed its
  decisions, README, and contract document inside the implementation
  commit (U-W1 `65e8be1`, U-K1/U-T1 `009e984`), so omitting them would
  make the exhaustiveness rule below fire on this unit's own delivery.
  U-W2.R (runtime
  repository, separate branch/PR named in contract §18) consumes
  intent files and produces receipt files against the private Postgres
  queue, pinning both record shapes by content hash at the U-W2
  milestone tag — the compatibility milestone; it never reads or
  writes `aos.db` and nothing in the agentic-os PR depends on it. Any
  other path in any later U-W2 wave is `FAIL — REPLAN REQUIRED`.
  Untouched (partial list; contract §0.3 is exact):
  `agentic_os/protocols.py`, `protocols/**`, `agentic_os/models.py`,
  `agentic_os/governance.py`, `agentic_os/ops.py`,
  `agentic_os/events.py`, `agentic_os/doctor.py`, delivery-control
  files, `pyproject.toml`. Rejected: putting the state vocabulary in
  `models.py` (the U-W1 self-contained-module idiom keeps the file
  boundary tight; DDL CHECK literals are pinned equal by test, the
  D-v0.4.23 pattern); a second U-W2 PR for CLI (one unit, one PR, one
  tag).
- **D-v0.4.82 — Exclusions are mechanical, not aspirational.** No retry
  loop, no checkpoint/resume implementation, no compensation
  execution, no loop-health monitor, no semantic interrupt kernel, no
  Temporal adoption, no tool/skill/model execution, no approval or
  policy grant, no credential selection, no cross-cloud failover, no
  MCP/A2A work, no queue implementation in agentic-os, no shared
  database, no protocol change. Each is enforced by the §19 test
  matrix: the import-discipline test proves the reducer's I/O absence;
  `result_outcome_inconclusive` on `partial` proves no second attempt
  exists; the compensation edges are frozen shut by the stronger fact
  that no member of either closed vocabulary targets them under policy
  v1 (`transition_reserved` itself is only observable on the one
  attemptable reserved edge); byte-unchanged neighbor suites prove the
  blast radius;
  and the store's audited SQL/filesystem surface proves no foreign
  database is touched. Rejected: shipping "just a minimal" retry or
  compensation path (execution semantics without U-W3's checkpoint
  and compensation machinery would be an untestable half-runtime — the
  D-v0.4.59 rationale, applied one unit later).

# DECISIONS — Agentic OS v0.4 U-W1 deterministic WorkSpec compiler (Wave 0)

This section continues the `D-v0.4.*` series for the U-W1 Wave 0
architecture freeze: the deterministic WorkSpec
compiler/linter/resolver/decompiler/semantic-diff unit, frozen in
`agentic-os-v0.4-u-w1-workspec-compiler-contract.md`. Architecture only —
no production code, tests, CLI, persistence, scheduling, or execution ship
in this wave. Branch `v0.4-u-w1-workspec-compiler` (2026-07-24), worktree
`/home/daksh/Projects/agentic-os-u-w1`, baseline
`8cf82432d4c137d4a1513f9daee39cc3ee0be92b` (U-K1/U-T1 governed foundations
merged, ledger schema version `"5"`, milestone
`milestone/v0.4-u-k1-u-t1-governed-foundations`). Future PR title:
`feat(v0.4): U-W1 — deterministic WorkSpec compiler`; future tag:
`milestone/v0.4-u-w1-workspec-compiler`. The Atomic Agents evaluation
repository is not read in this wave. Prepended per the established
precedent (D-W0.4, reaffirmed in D-v0.2.7, D-v0.4.4); everything below
stays byte-identical.

## D-v0.4 decisions (U-W1, Wave 0 architecture freeze)

- **D-v0.4.59 — U-W1 is the static half; the U-W1/U-W2/U-W3 runtime
  boundary is frozen.** U-W1 compiles, lints, resolves, decompiles, and
  semantically diffs inert `beast.work-spec/v1` WorkSpecs; it executes
  zero attempts, schedules zero work, and persists no workflow state.
  U-W2 owns the deterministic workflow state engine and queue integration
  (the blueprint §9.2 lifecycle vocabulary is U-W2's). U-W3 owns
  checkpoints, resume, runtime retry, and compensation. U-K1/U-T1
  `invoke()` remains single-attempt and byte-unchanged. The two live
  sentences saying the outer attempt loop "is U-W1's" (the
  `governance.invoke()` docstring and the U-K1/U-T1 contract §0.2 /
  D-v0.4.56) are narrowed, not contradicted: U-W1 compiles and statically
  validates attempt constraints (`retry.max_attempts`,
  `retry.deadline_at`, and their compatibility with resolved tool
  manifests); runtime looping is U-W3's. No code changes for this; the
  docstring prose sits outside U-W1's file boundary and is retouched only
  by a unit that already modifies `governance.py`. Rejected: shipping
  even a "minimal" retry loop in U-W1 (execution semantics without a
  state engine, checkpoints, or compensation would be an untestable
  half-runtime); editing `governance.py` from this unit just to rephrase
  a comment.

- **D-v0.4.60 — `beast.work-spec/v1` is reused unchanged.** The live
  schema — closed fields, static `retry` intent, opaque `policy_refs`,
  approval booleans/credentials/environment maps/executable fields
  unrepresentable — was verified sufficient for the whole U-W1 surface.
  No v2 identity, no second WorkSpec schema, no registry growth
  (`REQUIRED_IDENTITIES` stays six), no `protocols/` projection change
  (the checked-in work-spec schema digest
  `07ac96ba08a1579bbd681ab4087156e9d8facf849f3348e0e494658f3acceab9`
  remains exact), no edit to `agentic_os/protocols.py`. A protocol change
  any later U-W1 wave proves necessary is a replan condition (`FAIL —
  REPLAN REQUIRED`), never an in-flight amendment. Rejected: a richer v2
  toward the blueprint §9.1 table ahead of any consumer; embedding
  resolution results in the artifact (`additionalProperties: false` and
  inertness both forbid it — resolutions ride in the compile report).

- **D-v0.4.61 — The authoring input is a closed, bounded, inert
  contract.** `aos.work-spec-authoring/v1` with the pinned
  `aos-workspec-compile/v1` algorithm version (the `aos.routing-request/v1`
  idiom; not a registry artifact). Four frozen field classes: explicit
  (`created_at`, `issuer`, `audience`, `scope`, `aos_task_id`,
  `data_classification`, `goal`, `acceptance_criteria`, plus optional
  schema-validated pass-throughs), mechanically defaulted (content-derived
  `work_spec_id`/`idempotency_key`/`trace` via frozen sha256 domain-tag
  derivations; the least-authority `permitted_destinations` floor
  `["aos-ledger", "local"]`; the weakest honest `expected_result` floor;
  the protocol constants), mechanically resolved (`content_sha256` and all
  report content), and forbidden (`schema`, `protocol_version`,
  `content_hash_alg`, `content_sha256` in authoring input →
  `forbidden_field`). No executable expression, import path, command,
  callable, ambient filesystem scan, network lookup, credential,
  randomness, locale or environment dependence, or model-granted authority
  is representable, and the compiler reads no clock (`created_at` is
  explicit). Requested agents/skills/tools are authoring-only analysis
  input and are never serialized into the artifact. Rejected: clock or
  randomness in the compiler (hidden inputs break determinism); defaulting
  `data_classification`, `issuer`, `audience`, or `aos_task_id`
  (fabricated facts).

- **D-v0.4.62 — Compilation is a pure function emitting a canonical
  artifact plus a self-digested report; it grants nothing.**
  `compile_work_spec(authoring, snapshot)`: normalize (sorted set-arrays,
  spelled-out defaults) → derive → assemble → validate through
  `protocols.validate_document` (the same engine every consumer uses) →
  resolve → lint → status. The artifact is emitted for every status
  except `invalid`; the report (`aos.work-spec-compile-report/v1`,
  canonical, self-digested) carries status, findings in canonical order,
  resolutions, per-field provenance (`explicit | defaulted | resolved`),
  the applied-defaults list, and exact registry pins (registry version,
  work-spec schema digest, snapshot digest). Compilation creates no
  capability, approval, policy decision, budget reservation, secret
  selection, route authority, or execution permission. Identical
  `(authoring, snapshot)` yields byte-identical outputs across runs,
  platforms, and input orderings. Rejected: emitting an artifact for
  `invalid` input (it either cannot be schema-valid or must not embed the
  content); free-text report fields; trusting any embedded
  `content_sha256`.

- **D-v0.4.63 — Semantic lint is closed statics under a six-status
  precedence and never duplicates a governance decision.** 25 closed
  reason codes in canonical emission order (the `GOVERNANCE_REASON_CODES`
  idiom), each mapped to exactly one class; the status is the
  highest-precedence class with a finding: `invalid > unresolved >
  ineligible > requires_external_authority > warning > valid`. Findings
  are value-free: closed code, schema-safe path, enum members, bounded
  counts, and `secretscan` pattern names — never a field value, document
  excerpt, or exception text. Secret-shaped free text refuses compile
  fail-closed (the D-v0.4.19 shipped-content class: a cross-boundary
  document, not a trusted human's live keystrokes). Lint consumes no
  `granted_capabilities`, evaluates no execution context, and emits no
  `allow`/`deny`; `evaluate_eligibility` and `invoke()` re-decide
  authority at runtime with their own inputs. Rejected: mirroring the
  governance decision vocabulary in lint (two authorities that can
  disagree); warn-and-embed handling of secret-shaped compile input.

- **D-v0.4.64 — Resolution is deterministic and snapshot-local.**
  `WorkSpecSnapshot` = validated `beast.agent-passport/v1` documents with
  caller-attested ledger lifecycles, plus governance-built skill/tool
  registries; its canonical projection
  (`aos.work-spec-registry-snapshot/v1`) digests into every report.
  Numeric version ordering (integers, never lexicographic); an exact pin
  resolves exactly or yields `unknown_version`; a bare name resolves the
  highest version and earns the `unpinned_requirement` warning.
  Resolution never consults lifecycle or evaluation state — a deprecated
  or unpromoted latest resolves and then earns its `ineligible` finding,
  so deprecation stays visible (the governance §7 rule). Duplicate
  requests and contradictory pins are closed findings; case-folded
  snapshot name collisions refuse at build (the `build_registry` folded
  rule); dependency cycles refuse at registry build with governance's
  `dependency_cycle`, so they cannot reach lint. The compiler never
  installs, activates, fetches, imports, binds, or executes. Rejected:
  ledger or database reads inside the compiler; silently skipping
  ineligible versions during resolution.

- **D-v0.4.65 — A WorkSpec describes requested work; it grants nothing.**
  `policy_refs.policy_ref`/`approval_ref`/`budget_ref` stay opaque,
  undereferenced, and non-authoritative until evaluated by their owning
  subsystem. U-W1 must not approve, reserve or account spend, grant or
  check capabilities, select credentials, override power mode, construct
  an execution context, or turn routing/handoff advice into permission —
  none of these are representable in any U-W1 signature, record schema,
  or report field. `approval_reference_required` states that external
  authority will be needed; it never checks it, and a WorkSpec-carried
  `approval_ref` satisfies nothing at runtime, where governance evaluates
  its own execution-context inputs. Compile success, `valid` status, and
  `resolved` codes are consistency statements against a snapshot, never
  eligibility grants. Rejected: any compile-time "approved"/"funded"
  status (authority laundering); auto-copying WorkSpec policy refs into
  an execution context.

- **D-v0.4.66 — Classification and scope are ordered, preserved, and
  fail-closed.** The `DATA_CLASSIFICATIONS` tuple order is the total
  order `public < internal < confidential < restricted`.
  `data_classification` is explicit, required, and emitted exactly as
  authored — no default, coercion, upgrade, or silent downgrade path
  exists, and the semantic diff reports any classification change under
  its own category. A resolved agent must declare the artifact's class in
  `data_classifications`; an absent declaration fails closed
  (`classification_mismatch`, the routing rule). A project-scoped
  resolved agent must match `scope.project` exactly (`scope_mismatch`);
  global agents are compatible with every project; `scope.tenant` is
  format-validated and uninterpreted in v1. Diagnostics name paths and
  enum members only. Rejected: guessing a classification in either
  direction (too low leaks, too high lies); scope inference from snapshot
  content.

- **D-v0.4.67 — The decompiler is deterministic, bounded, and
  secret-safe, and its round-trip claim is semantic only.** Fixed ASCII
  framing, LF newlines, frozen section order, code-point-sorted paths; no
  terminal-width probing, locale formatting, or clock stamp. Free-text
  values truncate at 120 code points with the fixed marker
  `...(+N chars)`. Every string leaf passes `secretscan.redact_tree`, so
  an external artifact that never met the compile-time refusal still
  cannot leak a secret-shaped value. With a digest-matched report
  (mismatch refuses), fields carry `[explicit]`/`[defaulted]`/`[resolved]`
  markers. The frozen claim:
  `compile_work_spec(authoring_view(artifact, report), same snapshot)`
  reproduces an identical `content_sha256` and report body. Display text
  is never parsed back, and reconstruction of the author's original input
  bytes is not claimed — normalization legitimately collapses equivalent
  spellings, and no U-W1 sentence claims more than this semantic fixed
  point. Rejected: claiming display-text reversibility; width- or
  locale-aware rendering.

- **D-v0.4.68 — The semantic diff is typed, closed, and digest-safe.**
  Change kinds `added | removed | changed` under eight canonical
  categories (`metadata`, `requirements`, `authority_references`,
  `budgets_limits`, `retry_idempotency`, `classification`, `resolutions`,
  `result_contract`); the spine's `/` path grammar with set semantics for
  uniqueItems string arrays and `(ref_kind, sha256-of-ref)` keys for
  `inputs`; deterministic order (category, then path, then kind);
  `from_sha256`/`to_sha256` recomputed from each body, never read from an
  embedded hash. Raw `from`/`to` values appear only on the frozen
  allowlist of enum/constant/integer/timestamp/identifier paths;
  `goal`, `acceptance_criteria[]`, `constraints[]`, `inputs[].ref`,
  `inputs[].note`, and `idempotency_key` diff by sha256 digest and length
  only, so no raw secret value can appear. Rejected: raw free-text
  diffs; order-sensitive diffs of set-semantics arrays (spurious changes
  from reordering).

- **D-v0.4.69 — Mutation/digest safety and compatibility are frozen.**
  Every accepted document snapshots by canonical round trip on intake
  (the `ComponentRegistry`/`EligibilityResult` rule); every return is
  fresh and unshared, so mutating any input or output after a call
  changes nothing observable; digests are recomputed over final values at
  emission — no stale attestation and no trust in embedded hashes;
  vocabularies are tuples and result types are frozen dataclasses.
  Existing WorkSpec fixtures, Result Envelope binding
  (`protocols.verify_binding`), passports, catalog, routing, handoffs,
  U-K1/U-T1 governance, `secretscan`, packaging (the
  `packages = ["agentic_os"]` allowlist already ships the one new
  module), and CI (`unittest discover`, `compileall`,
  `gen_protocols.py` verify) all remain byte-unchanged. Rejected:
  caching digests across mutations; touching any existing module to
  accommodate the compiler.

- **D-v0.4.70 — No persistence, no CLI, no dependency; the implementation
  boundary is exactly five paths.** No table, migration,
  `SCHEMA_VERSION` bump (stays `"5"`), event, doctor check, or
  `power.COMMAND_POLICY` change (the D-v0.4.6 anticipatory-row rule:
  U-W2 mints its own storage when it exists). No CLI verb — `aos
  protocol validate` already validates compiled artifacts through
  registry dispatch, and a compile/lint CLI would require an
  authoring-file format decision no consumer yet justifies. No dependency
  of any kind (`pyproject.toml` untouched; stock standard library). The
  U-W1 boundary is frozen to exactly:
  `agentic-os-v0.4-u-w1-workspec-compiler-contract.md` (new),
  `DECISIONS.md` (modified), `agentic_os/workspecs.py` (new),
  `tests/test_v04_workspec_compiler.py` (new), `README.md` (modified).
  Any additional path in any later U-W1 wave — including the disfavored
  `agentic_os/protocols.py`, `protocols/**`,
  `tests/test_v03_protocol_spine.py`, `agentic_os/cli.py`,
  `agentic_os/db.py`, `agentic_os/migrations.py`, `agentic_os/power.py`,
  `.github/**`, and `pyproject.toml` — is `FAIL — REPLAN REQUIRED`, not a
  quiet extension. Rejected: pre-minting a CLI or storage for U-W2;
  treating the boundary as advisory.

# DECISIONS — Agentic OS v0.4 U-K1/U-T1 governed skill and tool foundations

This section continues the `D-v0.4.*` series for the integrated U-K1/U-T1
unit: framework-neutral, deterministic manifest contracts and runtime
governance for skills and tools, frozen in
`agentic-os-v0.4-u-k1-u-t1-governed-foundations-contract.md`. Branch
`v0.4-u-k1-u-t1-governed-foundations` (2026-07-23), baseline
`224d2cd0b98766e52865f8b4752446adb71af850` (U-P2 delivery gate merged and
closed, which unblocks this unit per D-v0.4.50). The completed Atomic Agents
evaluation is research evidence only: its runtime loop is a plausible future
adapter target and its BaseIOSchema a useful IO mapping reference, while
Atomic Agents as kernel is rejected and BaseTool is not a governance
boundary; no evaluation source is copied or imported, and no dependency is
added. Prepended per the established precedent (D-W0.4, reaffirmed in
D-v0.2.7, D-v0.4.4); everything below stays byte-identical.

## D-v0.4 decisions (U-K1/U-T1, integrated foundations)

- **D-v0.4.51 — Skill and tool manifests are inert U-X1 registry artifacts;
  the kernel stays framework-neutral.** `beast.skill-manifest/v1` and
  `beast.tool-manifest/v1` join the embedded schema registry with the
  passport's reduced envelope; `REQUIRED_IDENTITIES` grows from four to
  six, the `protocols/` projection is regenerated, and the three spine
  assertions that pinned "exactly four" (the identity list,
  `len(REGISTRY)`, and the `protocol list` line count) update to six — the
  one versioned protocol change, documented in the frozen contract (§14). Every U-X1 rule
  applies unchanged: canonical JSON v1, self-excluding `content_sha256`,
  strict unknown-field refusal, credential-shaped property names
  unrepresentable. Cross-field manifest rules (`unsafe_retry_policy`,
  `compensation_*`, `recovery_compensation_mismatch`,
  `replacement_lifecycle_mismatch`, `self_dependency`) live in the spine's
  `_check_semantics`, presence-guarded so no existing schema's behavior
  changes. Rejected: adopting Atomic Agents, Claude Agent
  SDK, or MCP as the kernel (adapters are subordinate, later units); a
  second manifest format outside the registry — the U-A2 internal-index
  precedent covers a file with one consumer, while manifests are authored
  cross-system declarations like passports.

- **D-v0.4.52 — Descriptive metadata never grants authority.** A manifest
  declares `required_capabilities`; the execution context carries
  `granted_capabilities`; eligibility requires the subset relation plus
  every other gate, computed by `governance.evaluate_eligibility` into a
  typed decision over the closed vocabulary `allow | deny | needs_approval
  | unavailable | invalid` with closed reason codes in canonical emission
  order and pinned precedence (invalid > deny > needs_approval >
  unavailable). Display fields (`display_name`, `description`,
  `recovery.note`) are read by nothing; `approvals_required` and
  `approval_ref` are declarations and opaque references — no field
  anywhere can claim approval was granted. No model output is an input to
  any governance decision. Rejected: bare-Boolean eligibility; partial or
  fuzzy capability matching; reading autonomy/eligibility out of prose.

- **D-v0.4.53 — U-K1/U-T1 is a runtime-only foundation: no persistence, no
  CLI, no doctor change.** Manifests are documents, registries are frozen
  in-memory values, evidence is a returned record; `SCHEMA_VERSION` stays
  `"5"`, no table, no migration, no ID prefix, no event, no
  `power.COMMAND_POLICY` entry. `aos protocol validate` and `aos protocol
  verify-registry` already cover the new artifacts through registry
  dispatch. Rejected: manifest tables and a 5→6 migration (anticipatory
  storage for U-W1 — the D-v0.4.6 rule against pre-minting the next
  unit's rows); a governance-decision CLI that would invent an
  authority-context file format ahead of any consumer.

- **D-v0.4.54 — Implementation binding is explicit, digest-verified in-code
  registration.** A binding is a closed canonical record
  (`aos.implementation-binding/v1`) plus, for `in_process` kind, a Python
  callable handed to `BindingRegistry.register` in code; `metadata`
  bindings prove the contract and can never execute. The manifest declares
  the binding id and the record's sha256; eligibility verifies registered
  → binds this exact component → digest equals declaration, failing closed
  on each. No import path, module string, command, or URL is representable
  anywhere in the vocabulary, so naming code cannot run code. Rejected:
  dotted-path dynamic import (the Atomic Agents evaluation's central
  hazard); hashing Python code objects (not deterministic across builds —
  the digest covers the canonical record).

- **D-v0.4.55 — A deadline is not a cancellation, and termination is a
  separate truth.** Results carry `deadline_exceeded` as a status about
  lateness plus a closed termination outcome; this unit's in-process
  runner honestly emits only `not_started` and `completed` (a callable
  that returned control — by value or by raising — mechanically
  finished). `cooperative_cancelled`, `subprocess_terminated`,
  `remote_cancellation_requested`, `abandoned`, and `not_supported` exist
  in the vocabulary for adapters that can prove them; no sandbox or
  cancellation transport is implemented or claimed, and a manifest's
  `cancellation` field is a declared mode, not a behavior. Rejected:
  reporting deadline expiry as termination; pretending a userspace guard
  is a sandbox.

- **D-v0.4.56 — Unsafe retry combinations are unrepresentable, and
  `retryable` is derived, never asserted.** Schema-level:
  `retry.max_attempts` is bounded 1–10 and a mutating tool with
  `max_attempts > 1` must declare `idempotency: required_key` or a
  compensating action (`unsafe_retry_policy` refusal). Runtime:
  `idempotency_ref_required` and `attempt_budget_exhausted` refuse before
  execution; `derive_retryable` is the only producer of `retryable`
  (status ∈ {transient_failure, deadline_exceeded}, attempt below both
  the context and manifest bounds, and the mutating gate again). Agentic
  OS owns the outer attempt budget — invoke() executes exactly one
  attempt, hidden framework retries are neither representable nor
  trusted, and the retry loop itself is U-W1's. Rejected: an in-memory
  replay cache pretending to be durable idempotency; trusting a
  framework's internal retry counter.

- **D-v0.4.57 — Invocation evidence is digest-only.**
  `aos.governed-invocation-evidence/v1` binds invocation id, component
  identity/version, manifest and binding digests, principal and caller,
  decision and reasons, attempt accounting, timing, status, error code,
  input/output digests, termination outcome, recovery action, trace ids,
  and an optional `previous_sha256` chain link, then self-digests. The
  idempotency reference is bound as a sha256 leaf; raw inputs, outputs,
  references, and exception text are never copied in — there is no
  free-text field to leak through, which is stronger than redaction.
  Evidence records what the runner did, not what any model claimed.
  Rejected: embedding "redacted" payload excerpts; trusting
  caller-supplied evidence fields.

- **D-v0.4.58 — Passport requirement resolution is a read-only
  projection.** `resolve_passport_requirements` resolves the
  `skill_requirements`/`tool_requirements` strings U-A1 froze (and
  explicitly deferred to this unit) against the registries, yielding
  per-item closed codes (`resolved | unknown_component |
  unknown_version`) plus resolved version and manifest digest. The
  passport schema, routing evaluator, handoffs, and every existing
  fixture are byte-unchanged. Rejected: widening the passport schema;
  installing or activating anything as a side effect of resolution.

# DECISIONS — Agentic OS v0.4 U-P2 trust-boundary amendment (Wave 0.5)

This section continues the `D-v0.4.*` series for the U-P2 Wave 0.5
trust-boundary replan: adopting the solo-maintainer honest-authority boundary
in `agentic-os-v0.4-u-p2-trust-boundary-amendment.md` after the independent
Wave 1 audit found the delivery checks self-modifiable from a pull-request
head. Branch `v0.4-u-p2-delivery-gate` (2026-07-22), amendment baseline
`184ec247067c7d05c0eb3d56916450cff66218f9`; the three untracked Wave 1 files
remain byte-identical and unstaged, and no implementation changed. The
amendment supersedes only the conflicting security and enforcement claims of
the frozen Wave 0 contract — §19's enforcement sentence, the §16/§17
characterizations, D-v0.4.43's unqualified evidence language, and any
adversarial reading of D-v0.4.34/D-v0.4.41 — and the contract file itself is
not edited. Prepended per the established precedent (D-W0.4, reaffirmed in
D-v0.2.7, D-v0.4.4); everything below stays byte-identical.

## D-v0.4 decisions (U-P2, Wave 0.5 trust-boundary amendment)

- **D-v0.4.45 — U-P2 adopts the solo-maintainer honest-authority boundary:
  honest-maintainer protection, with no adversarial tamper-resistance
  claim.** The audit finding is accepted as correct: the workflow, the
  canonical verifier, and the verifier's tests are all sourced from and
  modifiable on the pull-request head, so a repository writer can modify all
  three together, preserve the four public check names, and produce four
  green checks. The response reduces the claim, never the checks — every
  pin, permission, timeout, membership law, and assertion stands. U-P2
  guarantees: deterministic CI execution of the checked-in workflow,
  least-privilege permissions, immutable action pins, full test and
  distribution-smoke checks, detection of accidental or isolated drift,
  required checks that block ordinary failures, and a reproducible,
  auditable delivery process for an honest maintainer. U-P2 does not
  guarantee: tamper resistance against a writer who co-edits workflow,
  verifier, and tests; semantic immutability of a same-named check;
  protection against a repository administrator; an external or
  base-controlled authority; second-human approval; organization/enterprise
  required workflows; or a trusted GitHub App / external status provider.
  Rejected: rewriting the frozen contract in place (amendments supersede;
  history stays byte-identical — the rule D-v0.4.33 applied to U-P1);
  discarding or "fixing" the Wave 1 implementation (the checks are correct;
  the claim was wrong).

- **D-v0.4.46 — Self-modifiable required checks are identities, not
  independent authority.** Branch rules match check runs by name and enforce
  the conclusions reported under those names; for `pull_request` events
  every reporting byte — workflow, verifier, and verifier tests alike —
  is sourced from the PR head. An unchanged name therefore proves nothing
  about unchanged semantics, and a green `workflow-integrity` proves only
  that the head's verifier accepted the head's workflow. Isolated or
  accidental drift is still detected — each of the three files is caught by
  the other two when edited alone — while a simultaneous self-consistent
  edit of all three passes by construction. The chain never leaves the head,
  so no Wave 2 refinement of the three files can close it; closing it
  requires an authority the head cannot modify (D-v0.4.48). This supersedes
  any reading of D-v0.4.34 or D-v0.4.41 under which frozen names or the
  verifier constitute independent enforcement. Rejected: treating the
  finding as a Wave 1 defect (self-attestation from modifiable content is
  structural, not a bug); silently keeping the stronger claim (an overclaim
  no probe can witness).

- **D-v0.4.47 — Solo topology: zero required approvals stand; code-owner
  review is deferred, not partially adopted.** The repository is public,
  owner type User, one active maintainer; pull-request authors cannot
  approve their own pull requests, so CODEOWNERS + required code-owner
  review would deadlock every owner-authored PR against a reviewer who does
  not exist. The `main-delivery-gate` ruleset keeps its frozen shape — pull
  request required, four required checks, branch up to date, force-push and
  deletion restrictions, conversation resolution, merge-commit only, zero
  required approvals — reclassified as ordinary failure enforcement and
  accidental-change governance, never independent tamper resistance.
  Rejected: requiring one approval now (permanent self-deadlock, or a
  rubber-stamp second account — both worse than the honest zero);
  `pull_request_target` as an improvised base authority (a privileged
  base-context workflow needs its own threat model and has no proven
  latest-head required-check semantics; the D-v0.4.35 ban stands).

- **D-v0.4.48 — External or base-controlled authority is trigger-gated
  future work, never hidden U-P2 scope.** Adversarial tamper resistance
  becomes a separate follow-on unit — its own contract, decisions, and
  proofs — when any one trigger is met. Trigger A, second trusted human:
  collaborator with write access; base-branch `.github/CODEOWNERS`
  protecting the workflows tree, the verifier, the delivery-gate tests, and
  the delivery contract/amendments; at least one required approval with
  code-owner review; stale-approval dismissal; approval by someone other
  than the most recent pusher; proof the author cannot self-satisfy the
  rule. Trigger B, organization/enterprise topology: the authority workflow
  placed outside the modifiable head, required through org/enterprise
  rulesets, verified to evaluate the latest PR commit, with proof a PR
  cannot replace or suppress it. Trigger C, trusted GitHub App or external
  check: a separately administered provider bound as the required-check
  source, evaluating the latest head, with isolated credentials and hosting;
  incident, key-rotation, availability, and recovery procedures; and proof a
  repository writer cannot forge the check. Rejected: building the App
  inside U-P2 (credentials, hosting, webhook, deployment, incident, and
  operator scope disproportionate to a delivery-gate unit); pre-implementing
  fragments of A/B/C now (a half-authority invites exactly the false trust
  this amendment removes).

- **D-v0.4.49 — Probe evidence is limited to ordinary failure
  enforcement.** The frozen failing-test probe proves exactly three things:
  a real failing test creates failed required checks on the exact probe
  head; the merge is blocked while those checks fail; the probe closes
  without merging. It does not prove that same-name check semantics are
  immutable, that a co-edited workflow cannot report green, or that an
  administrator cannot bypass or change the ruleset. D-v0.4.43's "the only
  accepted enforcement evidence is the probe" is qualified to: the only
  accepted evidence of ordinary failure enforcement. Every other D-v0.4.43
  element — bootstrap order, ruleset shape, probe procedure, close-unmerged
  discipline, ABSENT never reported as GREEN — stands. No malicious or
  same-name-neutering probe PR is created or merged in Wave 0.5 or later:
  the neutering case is analyzed on paper in the amendment (§7) because a
  live rehearsal against the real repository would prove nothing the
  analysis does not already establish. Rejected: a live neutering
  demonstration (an attack rehearsal normalized into repository history,
  with no governed value).

- **D-v0.4.50 — Wave 0.5 landing sequence, commit-sequence extension, and
  file/delivery-boundary extension; D-v0.4.44 extended, not rewritten.** The
  independent audit that produced this amendment also fixes the order in which
  the remaining U-P2 work lands, and extends the frozen delivery metadata of
  D-v0.4.44 without touching it. Landing sequence, frozen normative: Wave 0.5
  lands first as one documentation-only commit containing exactly `DECISIONS.md`
  and `agentic-os-v0.4-u-p2-trust-boundary-amendment.md`; no Wave 1 file is
  staged or committed before that Wave 0.5 commit exists; after it, the three
  Wave 1 files receive a renewed independent technical audit under the
  honest-maintainer boundary (D-v0.4.45), and only a PASS — or a
  corrected-and-re-audited PASS — permits Wave 1 staging; Wave 2 and Wave 3
  remain blocked until Wave 0.5 is committed, the renewed Wave 1 audit passes,
  and Wave 1 is committed; ruleset activation and the failing-test probe remain
  post-workflow-bootstrap activities (D-v0.4.43, as qualified by D-v0.4.49);
  and U-K1, U-T1, U-W1, and U-A4 remain blocked until U-P2 is fully merged and
  closed. Commit sequence: D-v0.4.44's four-item, one-per-wave sequence is
  extended — not replaced — by inserting exactly one Wave 0.5 commit, `docs:
  adopt U-P2 solo-maintainer trust boundary`, at position 2, between Wave 0's
  `docs: freeze U-P2 protected delivery contract` and Wave 1's `ci: add
  immutable read-only validation workflow`; the other three original messages
  are preserved verbatim, giving five ordered commits, and the claim that the
  complete U-P2 history is four commits no longer holds. File and delivery
  boundary: D-v0.4.44's "nothing else" boundary applied to its original
  Wave 0/1/2/3 table; this decision adds exactly one governed wave — Wave 0.5 —
  authorizing exactly two paths (`DECISIONS.md`,
  `agentic-os-v0.4-u-p2-trust-boundary-amendment.md`) and one commit, and no
  production, packaging, protocol, schema, migration, or unrelated
  documentation file. The amendment (§13, §14, §15) carries the extended
  sequencing and boundary; D-v0.4.44 and the original contract stay
  byte-identical history, neither reworded nor erased. Rejected: rewriting
  D-v0.4.44 in place (frozen Wave 0 history — amendments supersede, history
  stays byte-identical, per D-v0.4.33/D-v0.4.45); folding Wave 0.5 into the
  Wave 1 commit (the audit finding is a governed documentation change that must
  land and be independently visible before any Wave 1 file is staged); staging
  any Wave 1 file now (the renewed audit gate has not run).

# DECISIONS — Agentic OS v0.4 U-P2 continuous integration and protected delivery gate

This section continues the `D-v0.4.*` series for the U-P2 Wave 0
contract-freeze pass: freezing the delivery-gate architecture of
`agentic-os-v0.4-u-p2-delivery-gate-contract.md` on branch
`v0.4-u-p2-delivery-gate` (2026-07-22), from baseline
`ef66fd4297491a5856b6d2602da8e3994e5359bd`. All mutable facts below were
resolved from primary sources on 2026-07-22 and cross-checked against two
independent signals; none were frozen from memory. Prepended per the
established precedent (D-W0.4, reaffirmed in D-v0.2.7, D-v0.4.4); everything
below stays byte-identical.

## D-v0.4 decisions (U-P2, Wave 0 contract freeze)

- **D-v0.4.33 — U-P2 is a new unit that closes U-P1's explicitly deferred
  delivery gap.** The U-P1 contract's scope section reads, verbatim: "Out of
  scope (explicitly not done in this pass): CI, release publishing, branch
  protection, …". U-P2 closes CI and branch protection; release publishing
  stays excluded (no PyPI, no GitHub Release, no signing, no SBOM, no
  containers, no auto-tagging). U-P1 remains a historically correct,
  unmodified record. Rejected: amending U-P1 (frozen contracts are immutable
  history); starting U-A4 first — `agentic_os/protocols.py:1005` records
  that passport skill/tool requirement resolvers are deferred to U-K1/U-T1,
  so U-A4 would build on contracts that do not exist. The dependency-safe
  sequence after U-P2 is U-K1/U-T1 (either order) → U-W1 → U-A4.
  **Non-goal**: no runtime, schema, protocol, CLI, power, or doctor change —
  the doctor count (41), test count (2,275) and schema version (5) verified
  at baseline must be identical after U-P2.

- **D-v0.4.34 — Four stable public check identities, with an explicit job
  id / job name split.** The frozen required-check names are
  `workflow-integrity`, `tests-python-3.12`, `tests-python-3.14`,
  `distribution-smoke-python-3.12`. GitHub job ids cannot contain `.`
  (alphanumerics, `-`, `_` only), so the dotted public names are carried by
  the jobs' `name:` values — which is what required-status-check rules match
  — while the ids use hyphens (`tests-python-3-12`, …). Once the ruleset
  depends on these names, any rename is a governed migration touching
  ruleset, workflow, verifier and docs in one reviewed change. Rejected: a
  Python-version job matrix (renders `tests (3.12)`-style names, surrendering
  the frozen identities); `needs:` chaining (a failed early job leaves later
  required checks skipped rather than independently reported — four
  independent jobs report four independent truths on every run).

- **D-v0.4.35 — Least-privilege workflow law.** Exactly one top-level
  `permissions: contents: read` block; job-level `permissions:` blocks are
  forbidden entirely (an elevation is a violation, and a "redundant
  read-only" block is shape noise the verifier would have to special-case —
  both are refused). No secret contexts, no `pull_request_target` in any
  form, `persist-credentials: false` on every checkout, no artifact
  upload/download, no `continue-on-error`, no `curl`/`wget`, no `sudo`, no
  repository writes, no branch/tag commands. This is least-privilege, not
  isolation: no repository secrets are exposed to jobs; the workflow
  receives a read-only `GITHUB_TOKEN`; `persist-credentials: false` keeps
  that token out of on-disk Git configuration; the token is not explicitly
  passed to test shell steps; the pinned actions may internally receive the
  read-only token where they require it. GitHub-hosted runners retain
  outbound network access and U-P2 provides no egress sandbox, so the
  `curl`/`wget` ban is canonical workflow-shape hygiene, not a network
  isolation control — untrusted PR code can transmit anything it can read
  from the runner, and no artifact-upload action is configured. Stating
  these limits honestly does not weaken the least-privilege law.

- **D-v0.4.36 — Immutable two-entry action allowlist with frozen full-SHA
  pins.** Every `uses:` reference must be one of exactly:
  `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` (v7.0.1,
  published 2026-07-20) and
  `actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97` (v7.0.0,
  published 2026-07-20). Release names may appear in comments only; `@vN`,
  `@main`, and release-tag refs are forbidden in the executable field.
  Provenance: each tag→SHA mapping was resolved on 2026-07-22 via two
  independent primary-source signals in agreement — `git ls-remote` against
  the official repository and the GitHub REST `git/ref/tags/…` object —
  with release identity from the official releases endpoint. Wave 1
  re-resolves both mappings before writing `ci.yml`; any mismatch is a stop
  condition (possible tag retarget), never a silent update. checkout v7's
  headline change (blocking fork-PR checkout under `pull_request_target`) is
  hardening that cannot affect a workflow where `pull_request_target` is
  banned outright.

- **D-v0.4.37 — Interpreter matrix: 3.12 floor plus 3.14 current stable
  line; lines frozen, patches logged.** Resolved 2026-07-22 from two official
  sources in agreement: python.org/downloads (latest stable 3.14.6,
  2026-06-10) and devguide.python.org/versions (3.14 status `bugfix`; 3.15
  `prerelease` due 2026-10-01; 3.12 `security`). `setup-python` receives the
  feature-line strings `"3.12"` and `"3.14"`; every job prints `python3 -VV`
  so the exact resolved patch is recorded per run. Rejected: pinning exact
  patch versions (CI would test a stale patch instead of the line users
  install, and patch churn would require constant governed edits); adding
  3.13 (neither the floor nor the current stable line). Python 3.15 adoption
  after its stable release is a future governed change.

- **D-v0.4.38 — Exact-pinned CI-only build tools, build isolation disabled,
  yanked release refused.** The distribution-smoke job installs exactly
  `pip==26.1.2`, `build==1.5.0`, `setuptools==83.0.0`, `packaging==26.2`,
  `pyproject_hooks==1.2.0`, then logs `pip freeze`, then builds with
  `python -m build --wheel --no-isolation` so the exact-pinned backend is
  the one that builds (isolation would re-resolve setuptools from the
  network at build time — precisely the drift this unit exists to prevent).
  The cross-check rule earned its keep immediately: pypa/build's newest
  GitHub release is 1.5.1 (2026-07-09), but 1.5.1 **is yanked on PyPI**, so
  1.5.0 — the newest non-yanked release — is frozen instead; pinning a
  yanked release is forbidden. The `wheel` package is deliberately not
  installed (setuptools ≥ 70.1 provides native `bdist_wheel`; current wheel
  0.47.0 recorded for reference); if Wave 1's smoke disproves this, adding
  `wheel==0.47.0` is a recorded amendment. Runtime dependencies remain
  `[]`. **Deferred**: `--require-hashes` artifact-hash pinning, to a future
  supply-chain unit.

- **D-v0.4.39 — Runner pinned to the explicit `ubuntu-24.04` label.**
  `ubuntu-latest` is a mutable alias (it retargets when GitHub promotes a
  new LTS image) and is forbidden for the same reason mutable action tags
  are. Verified 2026-07-22 from the official actions/runner-images source:
  `ubuntu-latest` currently maps to 24.04; `ubuntu-26.04` exists but is
  preview (no Actions SLA) and is rejected; arm and slim variants rejected
  (the gate proves the supported x64 environment). Moving to a newer image
  is a governed change.

- **D-v0.4.40 — No artifact upload; disposable `$RUNNER_TEMP` roots;
  fail-closed membership law; clean-tree assertion.** CI uploads nothing —
  no database, vault, workspace, log, coverage, wheel, or zipapp artifact
  ever leaves the runner. The wheel and zipapp final artifacts and the
  disposable smoke workspaces live under `$RUNNER_TEMP`, outside the
  checkout, with `PYTHONPATH` unset and smoke commands run from outside the
  repository; but `python -m build --wheel --no-isolation` may create
  `build/` and `agentic_os.egg-info/` inside the checkout — build
  intermediates, gitignored at baseline (`build/`, `*.egg-info/`), never
  permitted wheel members except the built wheel's legitimate `.dist-info`
  metadata. Because ignored residue is invisible to `git status
  --porcelain`, cleanliness cannot rely on porcelain alone: the smoke job
  removes exactly those known intermediates in a bounded cleanup step (never
  `git clean`) and asserts their absence, checking the known paths both
  before and after cleanup; unexpected ignored residue is still a failure
  and source files must stay byte-identical. Wheel and zipapp membership are
  asserted against allowlists (wheel: `agentic_os/**/*.py`,
  `agentic_os/catalog/*.json`, dist-info; zipapp: root `__main__.py`,
  `agentic_os/**/*.py`, the individually-validated catalog files per
  D-v0.4.14) so an unexpected new name fails closed; no ledger, backup,
  vault, credential, cache, repo-metadata, prompt-pack, or test content can
  ship. Every job ends by asserting `git diff --exit-code` and an empty
  `git status --porcelain`, and the smoke job additionally asserts the known
  build intermediates are absent.

- **D-v0.4.41 — A stdlib-only workflow-integrity verifier enforcing a frozen
  canonical byte-grammar, with a closed 20-reason vocabulary.**
  `tools/verify_ci_workflow.py` enforces the one frozen canonical workflow
  contract by canonical byte-grammar recognition, not substring scanning: it
  is deliberately not a general YAML parser or Actions linter, and it
  affirmatively recognizes the full frozen workflow shape rather than
  searching for banned substrings, so `.github/workflows/ci.yml` is accepted
  only when every byte and construct belongs to the single frozen canonical
  grammar and any unrecognized construct fails closed with
  `unexpected_workflow_shape`. The frozen representation fixes one
  deterministic form — UTF-8, LF only, no BOM, exact key ordering where the
  verifier depends on ordering, exact job ids and `name:` values, exact
  allowed steps and command blocks, and the exact action allowlist with full
  SHAs — and classifies as non-canonical and refusing every YAML anchor,
  alias, custom tag, duplicate key, document start/end marker,
  multiple-document stream, flow-style mapping or sequence, quoted or escaped
  mapping key, alternate boolean spelling, job-level `permissions:` block,
  local action, reusable workflow, multiline/folded `uses:`, unexpected block
  scalar, unknown job/step/key/ordering, and shell indirection that replaces
  a frozen command. Interface: default target `.github/workflows/ci.yml`,
  `--workflow PATH` override; exit 0 only with zero findings, 1 with findings,
  2 on usage error; one finding per line, deterministically ordered by
  (reason, locus). Diagnostics are value-free and bounded: a reason code from
  the closed vocabulary (`missing_workflow`, `invalid_utf8`, `crlf_present`,
  `mutable_action_ref`, `unapproved_action`, `credential_persistence`,
  `write_permission`, `pull_request_target`, `secret_reference`,
  `continue_on_error`, `missing_timeout`, `missing_required_job`,
  `missing_required_trigger`, `missing_python_line`, `missing_full_suite`,
  `missing_distribution_smoke`, `artifact_upload`, `shell_download`,
  `unexpected_workflow_shape`, `internal_error`) plus at most a closed-set
  locus (frozen job id, frozen trigger name, or `line:<n>`); arbitrary
  workflow content is never echoed, so a hostile workflow cannot use the
  verifier as an output channel, and malformed bytes yield findings, never
  tracebacks. `internal_error` is the twentieth code: a top-level exception
  guard wraps the whole run so any unexpected internal failure exits 1 with
  one fixed, value-free diagnostic — no traceback, no exception message, and
  no file content echoed — ordered deterministically with the other findings.
  Rejected: a third-party linter (violates the zero-dependency law and imports
  someone else's policy); free-text diagnostics (a leak channel and an
  unstable test surface). Tests must prove every reason reachable and the
  output value-free, and Wave 1 must add a mutation test for every bypass
  class named above.

- **D-v0.4.42 — Bounded timeout ceilings and ref-scoped concurrency with
  PR-only cancellation.** `timeout-minutes`: 10 for `workflow-integrity`, 30
  for each remaining job. Timeout basis, recorded with the evidence that does
  exist: the known local final U-A3 full-suite runtime is 2,275 tests in
  763.307 seconds (~12.72 minutes). That is local hardware evidence, not
  GitHub-hosted-runner evidence; the 30-minute test-job ceiling is
  approximately 2.35 times that local runtime, and the 10-minute integrity
  ceiling remains separate. No hosted-runner CI duration exists yet (no prior
  workflow ever ran), so the ceilings are deliberately generous runaway
  bounds, not performance targets: the first live U-P2 runs must record the
  actual hosted durations, any timeout change requires a governed amendment,
  and a timeout must never be increased merely to hide a hang. Tightening from
  observed data is a normal governed change; raising a ceiling is a red flag
  requiring investigation first. Concurrency: `group: ci-${{ github.ref }}`
  with `cancel-in-progress: ${{ github.event_name == 'pull_request' }}`. PR
  runs for the same PR may be canceled when superseded; `main` runs use
  `cancel-in-progress: false`. This does not guarantee a completed run for
  every mainline commit: GitHub may still cancel an older *pending* run in the
  same concurrency group when a newer `main` run is queued, and only the
  newest queued `main` run is guaranteed to complete, so an intermediate main
  commit may lack a completed run. A missing historical run can be re-created
  with `workflow_dispatch` against the relevant commit or ref where GitHub
  permits. U-P2 therefore does not claim immutable CI evidence for every
  `main` commit, and never claims queue preservation GitHub does not provide.

- **D-v0.4.43 — Bootstrap sequence, `main-delivery-gate` ruleset, and the
  failing-probe enforcement proof.** Order is fixed: workflow merges first
  (checks must exist before rules can require them), then the operator
  creates repository ruleset `main-delivery-gate` targeting `main`:
  enforcement Active; bypass list empty (the administrator is subject to the
  rules; the accepted escape hatch is editing the ruleset itself, which is
  documented rather than pre-weakened); restrict deletions; block force
  pushes; require a pull request (0 required approvals — one active
  maintainer, no unavailable external approver; conversation resolution
  required; merge-commit only); require the four frozen checks with
  branch-up-to-date. Availability was triangulated on 2026-07-22 (public
  repository; GitHub Free provides the full feature set on public
  repositories; the live rulesets endpoint answers normally) — but
  configuration is never trusted on faith: the only accepted enforcement
  evidence is the probe. Frozen probe: branch `probe/u-p2-required-check`
  from post-merge `main`; a single new deliberately-failing test file
  `tests/test_probe_delivery_gate.py`; PR titled
  `probe(v0.4): U-P2 failing required-check probe — do not merge`; observe
  both test checks FAILED on the exact probe head and merge blocked; close
  unmerged; delete the branch; record the evidence. Protection is never
  weakened to complete a proof, and ABSENT is never reported as GREEN.

- **D-v0.4.44 — Frozen delivery metadata and exact file boundary.** PR
  title: `ci(v0.4): U-P2 — add protected deterministic delivery gates`;
  merge mode: normal merge commit (repository convention, API-confirmed
  enabled); milestone: annotated tag `milestone/v0.4-u-p2-delivery-gate` on
  the merge commit after post-merge tree-equality verification
  (`origin/main^{tree}` must equal the feature head's tree); never renamed
  after push. There are 19 existing `milestone/*` tags at the Wave 0
  baseline: 13 annotated and 6 lightweight; U-P2 deliberately uses an
  annotated milestone tag, following the newer annotated convention, and
  historical tags are not rewritten. File
  boundary: Wave 0 touches exactly this contract and DECISIONS.md; Wave 1
  adds exactly `.github/workflows/ci.yml`, `tools/verify_ci_workflow.py`,
  `tests/test_v04_delivery_gate.py`; Wave 2 refines only those three; Wave 3
  touches exactly `README.md`, `CONTRIBUTING.md` (new — confirmed absent at
  baseline), `TROUBLESHOOTING.md`. Every other path — all of `agentic_os/`,
  `aos.py`, `aos_hooks.py`, `pyproject.toml`, `protocols/`, the existing
  tools and tests, schema and migrations — is untouchable; a production
  module entering the diff is a stop condition, and a pre-existing
  entrypoint defect exposed by CI becomes a separate maintenance unit, never
  a fix-forward inside U-P2.

# DECISIONS — Agentic OS v0.4 U-A3 governed agent routing and handoff contracts

This section begins the continuation of the `D-v0.4.*` series for the U-A3
Wave 0 contract-freeze pass: reconciling the approved design
(`U-A3-routing-handoffs-design.md`) with the independent audit
(`U-A3-routing-handoffs-audit.md`, verdict ADOPT WITH REQUIRED CORRECTIONS —
3 blockers, 6 majors, 9 minors) into
`agentic-os-v0.4-u-a3-routing-handoffs-contract.md`, on branch
`v0.4-u-a3-routing-handoffs` (2026-07-17). Prepended per the established
precedent (D-W0.4, reaffirmed in D-v0.2.7, D-v0.4.4); everything below stays
byte-identical.

## D-v0.4 decisions (U-A3, Wave 0 contract freeze)

- **D-v0.4.21 — Distinct governed agent-handoff tables, separate from
  legacy `handoffs`.** `agent_handoffs` + `agent_handoff_transitions` are
  new tables, not an extension of the existing free-text `handoffs` table.
  The legacy table's `from_agent`/`to_agent` are unvalidated free text,
  carry no CHECK, no hash, and a mutable `accepted_at` — none of which its
  historical rows could satisfy under governed rules without the migration
  fabricating identities and pins for names that were never validated,
  which D-v0.4.4 already forbids. Rejected: extending the legacy table
  (fabrication); canonical artifacts with no relational state (loses FK
  integrity, SQLite's compare-and-swap concurrency, and the backup/snapshot
  perimeter). The legacy table, its two CLI leaves, its events, its mirror
  notes and its `H` id prefix stay byte-identical — D-v0.4.20 reserved this
  ground for U-A3 explicitly, and this decision is how that reservation is
  spent. **Deferred**: any future unification of the two handoff concepts.
  **Non-goal**: no migration path from a legacy handoff row to a governed
  one is provided or implied.

- **D-v0.4.22 — Schema v5: four additive tables, zero new protocols, DDL
  hardened past the original design.** `routing_plans`,
  `routing_plan_candidates`, `agent_handoffs`, `agent_handoff_transitions`
  are added under migration `u-a3-routing-handoffs-v5` (4→5), built from
  the same `{table}`-parameterized DDL constants a fresh `init` composes
  (D-v0.3.42), so fresh and migrated schemas are byte-identical for these
  four tables. Every table carries constraints no existing table could
  express: `routing_plan_candidates` gains a composite
  `FOREIGN KEY(agent_id, passport_version) REFERENCES
  agent_passports(agent_id, version)` — without it, an eligible candidate
  could pin a passport version that does not exist or belongs to another
  agent, and nothing would refuse it until doctor caught it after the fact;
  `routing_plans` gains two additional `result_status` CHECKs so
  `resolved`/`unresolved`/`no_eligible_candidates` are all biconditional in
  `(eligible_count, unresolved_count)`, closing a hole where a plan could
  claim `no_eligible_candidates` while genuinely unresolved candidates
  existed; both `routing_plans` and `agent_handoffs` gain
  `CHECK (supersedes_id IS NULL OR supersedes_id < id)`, making every self-
  and n-cycle structurally impossible, since rowids only increase and
  neither table has a DELETE path; `agent_handoff_transitions` gains
  `CHECK (from_state <> 'accepted' OR to_state IN ('cancelled','superseded'))`,
  closing the two illegal edges (`accepted→refused`,
  `accepted→clarification_required`) the enum CHECKs alone left
  representable. Precedent for all four: `MEMORY_EDGES_DDL` and
  `MEMORY_SOURCES_DDL` already establish that a domain rule the application
  enforces should also be unstorable by raw SQL wherever a CHECK can
  express it; doctor remains the backstop only for what SQLite genuinely
  cannot express (sequence contiguity, chain replay, cross-row
  equivalence). No new U-X1 protocol identity is introduced: routing
  requests, plans, handoffs and transitions are workspace-local records
  pinned to local ids and digests that cannot travel between workspaces, so
  there is no interoperability surface to justify one — `protocols.py` and
  every protocol artifact stay byte-identical. **Deferred**: a
  cross-workspace handoff-exchange protocol (`beast.agent-handoff/vN`) if a
  future unit ever needs one. **Non-goal**: no index is added in this pass
  (D-v0.4.28).

- **D-v0.4.23 — Autonomy is unordered membership, never a ladder.**
  `AGENT_AUTONOMY_LEVELS = ("declare_only","suggest","supervised","scoped")`
  is a closed, **unordered** vocabulary; the routing request's
  `required_autonomy` field is an array of 1..4 unique values matched
  against the agent's declared passport `autonomy` by set membership only,
  producing `autonomy_mismatch` on a miss. No `autonomy_rank` function is
  written, and none may be. This reverses an `autonomy_ceiling` (a single
  value compared by rank ≤) considered during Wave 0 review and rejected:
  U-A1 published `autonomy` as an inert declaration ("nothing in U-A1 reads
  it"), so ranking it now would retroactively redefine every value already
  stored in every published passport; `supervised` and `scoped` name
  orthogonal properties (supervision presence vs. scope boundedness) with
  no forced order, so a ceiling would have to guess an answer for the one
  comparison that matters most; and a rank is rank inference over a
  declaration — exactly what this same request schema refuses one field
  over, for `data_classification` (D-v0.4.32). Precedent for the
  unordered-and-say-so shape: `MEMORY_SENSITIVITIES` carries an explicit
  authoritative-order warrant because its order is load-bearing;
  `AGENT_AUTONOMY_LEVELS` carries the deliberate inverse comment because
  its order is not. **Deferred**: an autonomy ladder remains possible in a
  future unit, but only with its own decision record and its own evidence
  that the levels are genuinely comparable — evidence that does not exist
  today. **Non-goal**: U-A3 does not read, write, or reinterpret any
  previously published passport's `autonomy` value; existing declarations
  are unaffected.

- **D-v0.4.24 — `decision_id` is a rationale reference, not an approval.**
  `agent_handoffs.decision_id` is an optional FK to `decisions(id)`, read
  only as a pointer to the architecture-decision record that explains *why*
  a delegation was declared. It is not an approval, not authorization, not
  consent, not a grant, not a policy decision, and not an execution
  permission, and no U-A3 code reads it as a condition for allowing any
  operation — a handoff with `decision_id` NULL and one with `decision_id`
  set behave identically on every verb. This is forced by what `decisions`
  actually is: an ADR table (`title`, `decision_md`, `alternatives_md`,
  `status`, `decided_at`) with no approver column, no subject, no grant, no
  scope, and no foreign keys at all; `status` carries no CHECK constraint
  and is hardcoded to `'accepted'` by its one writer (`ops.add_decision`),
  and no CLI verb ever changes it. Describing a pointer into that table as
  an "approval reference" — language considered during Wave 0 review and
  rejected — would have manufactured an authorization primitive the system
  does not have, inviting a future orchestration unit to gate execution on
  `decision_id IS NOT NULL` over a column that is, in truth, unconstrained
  free text defaulted to `accepted`. **Agentic OS currently has no governed
  approval primitive for these handoffs**, and this decision records that
  fact rather than papering over it. **Deferred**: any future unit that
  wants real approval semantics must build a dedicated approval primitive
  and must not repurpose `decision_id` to mean one. **Non-goal**: this
  decision does not change the `decisions` table, `ops.add_decision`, or
  any existing consumer of a `decisions` row.

- **D-v0.4.25 — Routing-plan post-commit immutability, built on the
  `_PENDING_HASH` precedent.** `routing_plans` and `routing_plan_candidates`
  rows are immutable after commit — no command reaches them with an UPDATE
  or DELETE once their creating transaction has closed. Within that one
  creating transaction only, the parent plan row is inserted with
  `content_sha256=_PENDING_HASH` (the empty string), each candidate row is
  inserted the same way, each candidate's hash is finalized by an UPDATE
  immediately after its insert (needed because a record hash binds its own
  row id, which SQLite only assigns at INSERT), the ordered chain of
  recomputed candidate digests is built by `routing_plan_candidates.id`
  ascending, and the plan's own hash is finalized last, over that chain.
  This is the exact `_PENDING_HASH` two-step already established for
  memory claims (`ops.py`: "the id is only known after the INSERT — so the
  two-step is unavoidable … invisible: no other connection can observe an
  open transaction"), applied to routing for the first time. No digest
  input ever includes a `content_sha256` column, so the construction is
  acyclic: plan-id → candidate rows → candidate digests → plan hash. A
  `_PENDING_HASH` value that survived a crash does not have the 64-hex-
  character shape a real hash has, and is reported as `malformed` by
  doctor and by `route verify`, never mistaken for a real one.
  **Deferred**: nothing — this is the complete, permanent hash-construction
  rule for both tables. **Non-goal**: this decision does not create any
  UPDATE path reachable from a normal command after commit; the
  hash-finalization UPDATEs are internal to `routing.create_plan` alone.

- **D-v0.4.26 — A handoff is an append-only transition history plus a
  mutable, hash-coupled current-state projection.**
  `agent_handoff_transitions` rows are immutable and append-only; on
  `agent_handoffs`, every column is likewise immutable except `state`,
  `updated_at` and `content_sha256`, which move together — always in the
  same transaction as the transition row that justifies them, always with
  exactly one event — and never otherwise. A freshly created handoff has
  zero transition rows, `state='proposed'`, and a hash bound over an empty
  chain; every subsequent verb appends exactly one transition row
  (chain-ordered by `seq`, not by row id) and recomputes the projection
  over the intended new state in one UPDATE, so no intermediate "state
  moved but hash didn't" row can exist even inside the transaction. The
  projection is fully derivable by replaying the chain from `proposed`; it
  is stored because it is what compare-and-swap reads and what `list`
  filters on, and doctor 39 is what proves the stored projection and the
  replayed history agree. This is chosen over deriving `state` purely from
  the event log (events are audit projections, deliberately not
  authoritative) and over one immutable successor row per transition
  (which reintroduces a moving-pointer integrity problem at higher cost
  than the composite-FK pattern already solves for passports).
  **Deferred**: nothing about the shape; a future unit may add a
  `completed` state to this same machine once it has execution-outcome
  facts to bind it to. **Non-goal**: this decision does not make any
  `agent_handoffs` column other than the three named ones mutable.

- **D-v0.4.27 — Supersession is expressed only at successor creation;
  plans derive it, handoffs also store it.** `supersedes_id` on both
  `routing_plans` and `agent_handoffs` is written only when a successor is
  created and is never updated afterward; `UNIQUE(supersedes_id)` permits
  at most one successor per row, making every chain linear;
  `CHECK (supersedes_id IS NULL OR supersedes_id < id)` makes every
  self-supersession and every longer cycle structurally impossible, because
  rowids only increase and neither table has a DELETE path, so an honest
  successor always has the larger id. There is no standalone supersede
  mutation on either table. The two tables are asymmetric on purpose: a
  routing plan has no lifecycle, so "superseded" is purely a derived fact
  about it (a successor exists), and deriving it is both cheaper and
  strictly stronger than storing a fact that could drift; a handoff has a
  lifecycle, and `superseded` must be a terminal state the same `state`
  column and compare-and-swap logic already read, reached through the same
  append-only transition history as every other terminal state — so it is
  both derived (a successor names it) and stored (the state column says
  so), and doctor 39 is what keeps the two readings honest via a
  `supersession_incoherent` verdict on divergence. **Deferred**: nothing;
  the asymmetry is permanent, not a placeholder. **Non-goal**: no
  `agent handoff supersede` or `agent route select`-style standalone leaf
  exists; supersession is reachable only through `create --supersedes`.

- **D-v0.4.28 — No indexes on the four U-A3 tables; three scan paths
  accepted by measurement, not by imitation.** `routing_plans`,
  `routing_plan_candidates`, `agent_handoffs` and
  `agent_handoff_transitions` carry no `CREATE INDEX`, continuing
  D-v0.3.45's rule. The UNIQUE constraints already supply the implicit
  indexes for every plan-scoped and handoff-scoped lookup: candidates by
  plan, candidates by plan and rank, transitions by handoff and sequence,
  and successor lookup by `supersedes_id` on both tables. Three paths are
  left as full scans, each accepted on its own evidence:
  `routing_plan_candidates` by `agent_id`, reached only by the `agent
  discard` guard, a rare interactive command on a draft identity whose
  parent DELETE forces the same child-table scan for foreign-key
  enforcement regardless of whether an index exists; `agent_handoffs` by
  task/state/plan, a human-authored table bounded by operator effort at
  hundreds of rows; and doctor checks 38 through 41, which walk every plan
  and handoff by design regardless of any index. Should the first path
  ever measurably matter, `CREATE INDEX routing_plan_candidates(agent_id)`
  is named as the answer and is additive — it is **not** added in this
  pass. **Deferred**: that one index, pending measured evidence.
  **Non-goal**: this decision does not claim the three scans are free at
  unbounded scale, only that they are bounded by realistic ledger sizes
  today.

- **D-v0.4.29 — The 3→4 migration step keeps building from the live agent
  DDL at v5; the freeze obligation transfers, guarded by a test.**
  `migrations.py`'s `_agent_passports_v4` step docstring records that a
  frozen copy of the v4 agent DDL "becomes v5's obligation" once v4 stops
  being current — and U-A3 is the unit that makes v4 historical. This
  obligation is deferred, deliberately and once, rather than discharged
  now: U-A3 changes neither `AGENTS_DDL`, `AGENT_PASSPORTS_DDL`, nor
  `agent_identity_payload`, so the live constants the 3→4 step builds from
  are still the genuine v4 constants, and no drift materializes. The
  precedent for deferring is the 2→3 step, which still builds from the
  live memory-claim DDL today, at v4 — this codebase has historically
  frozen a migration step's DDL only when a later change would actually
  cause it to drift (U-M3's DDL change forced 1→2 to freeze; U-A1's
  agents-table change forced the v3 step to freeze), not mechanically at
  every version bump. The obligation therefore transfers unchanged to the
  first future unit that edits `AGENTS_DDL`, `AGENT_PASSPORTS_DDL`, or
  `agent_identity_payload`, which must freeze the v4-named copies of those
  symbols before it edits any of them. A guard test — byte-comparing
  `db.AGENTS_DDL` and `db.AGENT_PASSPORTS_DDL` against literals frozen at
  this baseline (`80b7e82577cbed19aa1823934df44ae09a644ac5`), and pinning
  the sorted key list of `passports.agent_identity_payload` for a fixed
  agent — converts the silent trap the bare deferral would otherwise be
  into a loud one: its failure is the signal that this decision's
  obligation has come due. **Deferred**: the freeze itself, to whichever
  future unit trips the guard test. **Non-goal**: this decision does not
  touch any historical migration step body; U-A3's own migration step is
  purely additive and reads no existing table.

- **D-v0.4.30 — No `route select` leaf; no `completed` handoff state.**
  U-A3 ships no `agent route select` command and no `completed` value in
  the handoff state vocabulary. A selection that grants nothing and
  executes nothing is, in substance, already a delegation declaration —
  and U-A3 has that record: the handoff, which references a plan and names
  a recipient. A second record for the same fact would be duplicate state
  with its own divergence risk, and the plan is honestly finished doing its
  job — presenting an ordered, explainable, pinned candidate list — the
  moment a human reads it; "which one did the human pick" belongs to
  whatever declares the delegation. Completion is refused for a different
  reason: `completed` asserts that work was executed and verified, which is
  an execution-outcome fact, and U-A3 ships no runs or evidence binding
  that could make such a claim honestly. Both rejections keep the unit's
  advisory boundary exact: nothing in the schema can be read as "and then
  this happened." **Deferred**: a `completed` state, with its own evidence
  binding, is explicitly left to a future orchestration unit that has runs
  and evidence to point at; that unit may also revisit whether a
  lightweight selection record is still unnecessary once real orchestration
  exists. **Non-goal**: `agent handoff accept` is not, and must never be
  read as, a stand-in for completion — it executes nothing.

- **D-v0.4.31 — `agent_absent` and `catalog_not_installed` are
  request-level refusal codes, never candidate reasons.**
  `ROUTING_REQUEST_REFUSAL_CODES = ("agent_absent", "catalog_not_installed")`
  is a vocabulary disjoint from `ROUTING_REASON_CODES`. Both codes describe
  `preferred_agent` naming something that has no `agents` row — an
  unregistered name, or an uninstalled catalog entry — and
  `routing_plan_candidates.agent_id` is `NOT NULL` with a foreign key into
  `agents(id)`, so no candidate row can ever carry either code: the schema
  itself proves the vocabulary split is not stylistic. A request that
  trips either refusal creates zero rows and zero events; `agent route
  plan` exits 1 and prints a message naming the resolution path (`agent
  catalog install` for the uninstalled-catalog case), and nothing is
  installed as a side effect of the refusal. Filing the two codes alongside
  genuine candidate reasons, as considered during Wave 0 review and
  rejected, would let doctor 38 and `route verify` accept a stored
  `reasons_json` value that no honest write could ever produce, silently
  widening the set of "valid-looking" damage those checks would fail to
  catch. **Deferred**: nothing; the split is permanent and the two
  vocabularies must remain disjoint by test. **Non-goal**: this decision
  does not change how `preferred_agent` resolution behaves, only how its
  two failure codes are classified and validated.

- **D-v0.4.32 — `required_data_classification` is exact-set membership
  against a passport's declared classifications, never a ceiling.** The
  routing request's classification field is named `required_data_classification`
  and is evaluated as membership only: the requested level must be an
  element of the agent's declared `data_classifications` set, including
  the case where the agent declared no set at all, else
  `data_classification_mismatch`; the diagnostic's `declared: false` flag
  distinguishes the two failure shapes. The name avoids a byte-identical
  collision with the passport's own, unrelated envelope-level
  `data_classification` field (the classification of the passport document
  itself, not of anything the agent handles), and the word "ceiling" names
  nothing in this contract: a ceiling implies a rank comparison, and this
  gate's own justification is "membership, not rank inference: declarations
  are not extrapolated" — the identical principle D-v0.4.23 applies to
  autonomy. The vocabulary itself is not new: it is `models.MEMORY_SENSITIVITIES`,
  reused by value and pinned equal as a set, by test, to both
  `protocols.DATA_CLASSIFICATIONS` and the passport schema's own
  `data_classifications` item enum, since `models.py` cannot import
  `protocols` and no single-definition fix exists across that boundary.
  The handoff's own `data_classification` column (on `agent_handoffs`,
  distinct from the request field) keeps its name and its meaning
  unchanged: the declared classification of the data involved in a
  delegation, enforced only as vocabulary, an advisory unstored warning at
  creation, and `RESTRICTED_PLACEHOLDER` privacy in list output — never a
  clearance and never an authority grant. **Deferred**: nothing;
  membership is the permanent semantics for this dimension. **Non-goal**:
  this decision does not add a `missing_data_classification` code — the
  existing `data_classification_mismatch` code already covers both the
  "declared without this value" and "declared nothing" cases via the
  `declared` diagnostic flag.

# DECISIONS — Agentic OS v0.4 U-A1 agent passports

This section begins the `D-v0.4.*` series for the U-A1 pass executed per
`agentic-os-v0.4-u-a1-agent-passports-contract.md` on branch
`v0.4-u-a1-agent-passports` (2026-07-16). Prepended per the established
precedent (D-W0.4, reaffirmed in D-v0.2.7); everything below stays
byte-identical.

## D-v0.4 decisions (U-A1)

- **D-v0.4.1 — One canonical identity table, rebuilt in place.** `agents`
  keeps its name and becomes the governed identity table; a second table
  would have left two authorities answering to `FROM agents`. The rebuild
  follows the D-v0.3.43 recipe a third time: `{table}`-parameterized DDL
  constants in `db.py`, shared by fresh init and the 3→4 step, so a migrated
  schema and a fresh one are identical by construction. The current-passport
  pointer is a composite FOREIGN KEY `(id, current_passport_version) →
  agent_passports(agent_id, version)`: a pointer can never name another
  agent's passport or a missing version, and NULL (draft/legacy) disables
  the check by SQLite's rule rather than by convention.

- **D-v0.4.2 — Create publishes nothing; publish freezes everything.**
  `agent create`/`agent import` produce a DRAFT identity plus a draft v1
  passport — the operator's own pending declaration, discardable, editable
  only by discarding and recreating. `agent passport publish` is the single
  moment a declaration becomes immutable history and the identity becomes
  `active`. This is how "published passports are immutable" and "a draft
  that was never used can be discarded" coexist without exceptions.

- **D-v0.4.3 — Three hash bindings, one per substitution attack.** The
  document's own U-X1 content digest breaks on content tamper; the passport
  ROW hash (binding the recomputed document digest to agent_id + version +
  status + timestamps) breaks on status/reparent tamper; the identity hash
  (binding lifecycle, pointer, and the five inert legacy fields) breaks on
  pointer/lifecycle tamper. Every authoritative agent write walks the
  no-laundering gate first — identity hash, every row hash, every document,
  contiguity 1..N, draft shape, pointer resolution — so a corrupted history
  cannot receive a new version on top. The only exits are restore-from-backup
  or deliberate repair, both outside normal commands (the U-M2 verify_claim
  posture, applied to identities).

- **D-v0.4.4 — The migration synthesizes no passports.** 3→4 carries every
  v3 field verbatim — `kind` outside today's vocabulary, `capabilities_json`
  that does not parse, secret-shaped `notes`, all of it — into permanently
  inert legacy columns, and creates `agent_passports` EMPTY. Parsing
  `capabilities_json` or mapping `trust_level` into declarations would put a
  guess into the ledger wearing the same clothes as a fact (the D-v0.3.44
  rule). A legacy agent has no current passport until a human publishes one;
  doctor's WARN-only coverage line says so without calling history an error.
  The new facts are constants plus ONE clock reading, and `origin='legacy'`
  is what makes the stamped timestamps honest.

- **D-v0.4.5 — Legacy agents migrate to `active`, not to a sixth state.**
  They were live, referenceable identities the moment before the migration;
  `origin='legacy'` plus a NULL pointer already distinguishes the ungoverned
  population permanently. A dedicated `legacy` lifecycle state would force a
  mass adoption ceremony on upgrade day and complicate every transition
  table for nothing the origin column doesn't say.

- **D-v0.4.6 — Reservation is a namespace rule, not a set of rows.**
  `governor`, `planner`, `builder`, `verifier`, `security-sentinel` and the
  `aos.`/`beast.` prefixes are refused at create/import from frozen tuples in
  `models.py`. No row exists until U-A2's bootstrap mints the system agents —
  a reserved row created today would be U-A1 guessing U-A2's shape. For the
  same reason `protected` ships as a column with refusal semantics and
  doctor coverage but NO setter: marking noise as protected is exactly what
  an operator flag would invite, and minting protected system identities is
  U-A2's job.

- **D-v0.4.7 — `revoked` is terminal, and parked identities cannot gain
  versions.** No command leaves `revoked`, ever — permanent distrust with
  the full history retained. `publish` requires draft or active: letting a
  suspended or archived agent quietly accumulate declarations would launder
  a parked identity back into circulation without the deliberate `restore`.
  Same-state transitions are refusals naming the current state, never
  silent no-ops.

- **D-v0.4.8 — Discard is the system's only DELETE, and it cannot delete
  history.** Legal only for a draft with exactly one (draft, v1) passport,
  origin create/import, unprotected, pointer NULL, and ZERO textual
  references anywhere (`runs.agent`, `handoffs.from_agent/to_agent`,
  `evidence.provenance`, `memory_sources.provenance`). Everything else is
  pointed at archive/revoke. The discard event itself survives, so even a
  discarded draft's existence stays journaled.

- **D-v0.4.9 — A passport is not a task message.** The schema carries a
  REDUCED envelope — no `aos_task_id`, no `trace`, no `idempotency_key`, no
  `audience`, no `permitted_destinations` — because requiring them would
  force fabricated data into every declaration. `_check_semantics` guards
  its field-specific checks on PRESENCE rather than schema identity, so the
  three task-message schemas (which require those fields structurally) keep
  byte-identical behavior, proven by regression.

- **D-v0.4.10 — Everything a passport declares is inert.** `autonomy` is a
  stored enum no code path reads; skill/tool requirements and provider
  compatibility are pattern-bounded strings with no resolver (U-K1/U-T1);
  `approvals_required` declares what needs approval and cannot grant one;
  credential-shaped property names are unrepresentable (the registry lint
  refuses the schema; instances refuse as unknown_field). Import is bytes →
  dict → refusal-or-rows: nothing an artifact names is opened, fetched,
  resolved or executed. Signing is deferred to U-S5/U-Q1 — the digest and
  provenance fields are the substrate a signature will later cover, and no
  field pretends to be one today.

- **D-v0.4.11 — `agent add`/`agent update` retired, not aliased.** A
  deprecated alias would have kept a second, ungoverned write path into the
  legacy columns alive — the exact thing this unit exists to end. In-place
  mutation of capability text is incompatible with immutable versioned
  declarations; the muscle-memory cost is bounded and the fixtures now seed
  historical rows through frozen v1/v2/v3 replica writers, exactly as the
  memory fixtures already did.

- **D-v0.4.12 — Version 3 is history now, and history is pinned by bytes.**
  The v3 `agents` DDL is frozen verbatim in `migrations._V3_AGENTS_DDL`
  (fixtures build from it, so fixture and migration agree about v3 by
  construction), and a regression test migrates the v2 fixture to target 3
  and byte-compares both the memory DDL and the agents DDL in sqlite_master
  against the expected text — so a future edit to the live constants that
  would silently rewrite what 2→3 produces fails loudly. The 3→4 step uses
  the LIVE v4 constants (correct while 4 is current; the frozen copy becomes
  v5's obligation — the established trade).

- **D-v0.4.13 — Doctor gained exactly three checks, and the sweep followed
  the text.** Check 13 validates the governed v4 shape (still reporting the
  legacy hazards it always reported); 32/33 verify identity hashes and
  passport histories with the same closed verdict vocabulary the gate
  refuses on — both FAIL, both feed the recovery gate, so a tampered
  registry blocks leaving recovery; 34 is WARN-only coverage. The U-C3
  sweep now scans stored passport documents leaf-by-leaf under
  `agent #id passport vN` labels, because role and mission are exactly the
  prose an operator pastes a credential into. Diagnostics stay
  name-or-`agent #id`, verdicts and counts — never a value.

- **D-v0.4.14 — Packaging: the zipapp allowlist becomes manifest-driven, not
  broadened by pattern.** D-v0.3.61 declined a `*.json` branch precisely
  because a denylist-shaped widening can be defeated by an unanticipated new
  file; U-A2 needs JSON passports in the archive anyway, so the allowlist is
  strengthened instead of loosened: the builder reads
  `agentic_os/catalog/manifest.json` and archives exactly that file plus the
  passport paths its entries reference, verifying each referenced artifact's
  digest before archiving it. A schema (D-v0.3.2) is hashed externally and
  is code; a passport is hashed internally (`content_sha256` is a required,
  checked field) and is authored content, so embedding it as a Python
  literal would make verification circular — the rejected fallback. An
  unreferenced `agentic_os/catalog/*.json` stays excluded by construction, a
  tampered referenced artifact fails the build outright, and
  `test_v02_packaging.py`'s `.py`-only pin moves to reflect the new rule.
  Signing (U-S5/U-Q1) will cover these same referenced artifacts later; this
  decision only establishes what ships.

- **D-v0.4.15 — Catalog provenance is `owner='system'` + `issuer` +
  digest match, with no schema change.** `agents.owner` already permits
  `'system'` and no U-A1 writer has ever emitted it — D-v0.4.6 reserved the
  pairing for this unit. Bound together with the hash-bound passport
  `issuer='aos.catalog'` and a recomputed-digest match against the
  checked-in manifest, the three independent bindings make forged catalog
  authenticity structurally impossible without inventing a fourth. Adding an
  `origin='catalog'` value to `origin`'s CHECK was rejected: it would force
  a table rebuild and a schema v5 bump for a fact the existing fields
  already carry more strongly, and an import of a checked-in artifact is a
  truthful `import` regardless of who authored the artifact. Name is used
  only for lookup and collision refusal, never as the ownership test.

- **D-v0.4.16 — The catalog reuses the existing `aos.` reservation; zero
  new names are reserved.** `RESERVED_AGENT_PREFIXES` has refused `aos.*` at
  create/import since U-A1 shipped (D-v0.4.6), so the catalog's namespace
  and the user's namespace are structurally disjoint — no catalog write can
  land on a user name, and no user write can land on a catalog name, by
  construction rather than by a new check. The bare reserved names
  (`governor`, `planner`, `builder`, `verifier`, `security-sentinel`) stay
  row-less on purpose: the catalog lives entirely at `aos.*`, and `governor`
  specifically is never minted, because no policy engine, router, or
  scheduler exists for it to have authority over. Name comparison is exact
  bytes — no case folding, no Unicode normalization, no aliases — so a
  lookalike name is simply a different, non-colliding, non-catalog name.

- **D-v0.4.17 — The catalog ships every passport version, never only the
  latest.** A passport's `passport_version` is hash-bound and must equal its
  row's version, so a catalog that shipped only "the newest" per role could
  never reconstruct a gap-free history on a fresh install. Synthesizing a
  plausible intermediate version to close that gap was rejected on the same
  ground D-v0.4.4 already established for the 3→4 migration: a guess does
  not get to wear history's clothes. Shipping versions 1..N for all twelve
  entries (N=1 at this unit's ship date) means a fresh install and an
  upgrade-chain converge on byte-identical documents and identical version
  numbers, and the manifest's version-list shape needs no change at the
  first future upgrade.

- **D-v0.4.18 — `agent catalog install --all` is one transaction, not
  one per entry.** Empirical verification showed `db.transaction()` commits
  early when nested, so the two new row-writing primitives
  (`create_catalog_identity`, `append_catalog_version`) are written as
  transaction participants that never open their own, and `catalog.py` owns
  the single rollback boundary around the whole `--all` operation.
  Per-entry transactions were rejected: a partially installed catalog is a
  state nobody requested and no command can describe, every realistic
  refusal (collision, divergence, tamper) is already detected during
  verify-then-plan before the transaction opens, and twelve entries at
  roughly two rows each is too small to need splitting. Consequently every
  foreseeable refusal costs zero writes, every fact is re-read inside the
  transaction against TOCTOU, and one failing entry rolls back the entire
  operation with the refusal naming the entry that blocked it.

- **D-v0.4.19 — Shipped catalog artifacts are fail-closed on secret shape,
  not warn-on-write.** D-v0.2.15's warn-on-write posture governs the
  trusted human CLI boundary: a human typed it, so the ledger stays honest
  and the human is warned rather than blocked. A checked-in catalog artifact
  is not user input — it is reviewed content the project ships — so a
  secret-shaped string appearing in one is a defect, not a user's choice.
  Reusing warn-on-write for catalog content was rejected because it would
  let a defect in reviewed, shipped content reach the ledger and only be
  flagged afterward, exactly the laundering U-C3 exists to prevent for less
  trusted input. `catalog.verify()` therefore FAILs and `install` refuses
  before any write. No catalog-specific reader is invented: every byte still
  passes through the same `parse_canonical` + `validate_document` path
  `agent import` uses, so catalog install events stay unconditionally clean.

- **D-v0.4.20 — No handoff graph or dependency block in U-A2.** A
  preferred-inbound/outbound-handoff field on a passport, or a `dependencies`
  block in the manifest, would encode a routing structure — exactly the
  router this unit's non-goals forbid building. A manifest `dependencies`
  list expressing install ordering was rejected on its own terms too:
  passports are inert with no inter-entry dependency, installation order is
  already manifest order, and a separate ordering field would be duplicate
  state carrying no meaning. Where a boundary is genuinely part of a role's
  own limit, it is prose in that role's `mission`/`limitations` field, never
  a structured, machine-followed one. Routing and handoff graphs remain
  explicitly assigned to a future unit (U-A3), which starts from a clean
  slate rather than an informally-encoded graph it would have to honor or
  break.

# DECISIONS — Agentic OS v0.3 U-M5 retrieval evaluations

This section continues the `D-v0.3.*` series for the U-M5 pass executed per
`agentic-os-v0.3-u-m5-retrieval-evals-contract.md` on branch
`v0.3-u-m5-retrieval-evals` (2026-07-16). Prepended per the established
precedent (D-W0.4, reaffirmed in D-v0.2.7); everything below stays
byte-identical.

## D-v0.3 decisions (U-M5)

- **D-v0.3.52 — U-M5 measures; it does not adopt.** The unit ships an explicit
  candidate retriever, datasets, a report and a gate. It ships no switch.
  `search.py` and `pack.py` were not modified — not one line, verified by a
  test that diffs them against the baseline commit. A pass that both proposed a
  retriever and wired it into `pack build` would be a pass whose benchmark
  could never fail in a way anyone acted on: the code would already be in
  production while the report was still being read. `benchmark run` prints a
  recommendation and changes nothing. Adoption is a human decision, taken after
  this report, in a later unit.

- **D-v0.3.53 — The baseline is measured as it is, not rewritten to be easy.**
  The baseline candidate re-expresses the LIKE backend's memory semantics over
  the shared corpus, and a test proves it returns the same memory result SET as
  the live `search.search()` for a matrix of queries against a real workspace.
  Reimplementing rather than importing was the only honest option available:
  `search.search()` needs a `sqlite3.Connection` and returns rendered snippets,
  and the benchmark corpus is deliberately not a database (D-v0.3.60).
  Reimplementing *and asserting equivalence* is a proof; editing production so
  the benchmark can call it is a way of making the baseline whatever the
  candidate needs it to be. The baseline reproduces the LIKE fallback's
  ascending-id order rather than FTS5's `rank`, because a benchmark whose
  ranking depends on which SQLite the runner happens to have is not a
  benchmark; the fidelity test compares SETS, which is the backend-independent
  part.

- **D-v0.3.54 — Integers, ordinals and rationals. No float ever.** Every score
  component is an integer, the sort key is a tuple of three integers, and every
  metric is a `fractions.Fraction` rendered by integer arithmetic to a
  fixed-width decimal STRING. Strings and not JSON numbers, because a JSON
  number is a float to almost every consumer — the no-float rule has to survive
  the reader too, not just the writer. A test re-parses the real `--json`
  stdout with a hook that rejects every float literal. A benchmark whose digits
  depend on the platform's libm is not a benchmark.

- **D-v0.3.55 — nDCG's log2 discounts are a checked-in table, not
  `math.log2`.** `math.log2` is a libm call: correctly rounded on most
  platforms, not guaranteed identical on all. `_LOG2_SCALED` pins log2(2) …
  log2(11) as integers scaled by 10^12, written out as source literals, and the
  discount is the exact rational `Fraction(10**12, _LOG2_SCALED[i])`. The table
  is a *definition* of this metric, not an approximation of another one: two
  runs on two platforms agree because they compute the same rational number,
  not because their libms happened to. A test compares the table to
  `math.log2` on the local platform to catch a transcription typo — that is the
  table checking the transcription, not the transcription trusting the
  platform. (Two of the eleven values were mistranscribed by hand on the first
  attempt; the test caught both, which is the argument for the test.)

- **D-v0.3.56 — Eligibility is one predicate, strictly stricter than the
  pack's.** `retrieval.eligibility()` returns a reason code from a closed,
  ORDERED set, applies U-M2/U-M3's lifecycle rules with the same spelling
  `ops.claim_is_eligible` uses, and reuses `ops.window_is_active` for the
  window. It adds three things ordinary pack inclusion does not need:
  hash validity (`memory_for_project` deliberately does not re-verify —
  D-v0.3.21: one damaged row must not block every pack; retrieval can afford to
  be stricter because its pool is bounded and its exclusions are counted and
  reported), `valid_from <= as-of` (a claim whose window has not opened is not
  a fact about the requested instant), and project compatibility. A test proves
  the implication that matters over the whole fixture matrix:
  `retrieval_eligible(c, t)` ⟹ `ops.claim_is_eligible(c, t)`. U-M5 can refuse
  what the pack would carry; it can never carry what the pack would refuse.

- **D-v0.3.57 — Every expanded result ranks below every primary result.** The
  sort key's first element is the origin ordinal. This makes "a graph neighbour
  must not outrank a strong direct lexical match" true by construction rather
  than by weight-tuning, and it makes the property testable with one assertion
  instead of a tournament of fixtures. Expansion in U-M5 is a **recall
  instrument**: it appends to the tail, it never reorders the head. If a later
  unit wants interleaved ranking, it will have this report to argue from.

- **D-v0.3.58 — A primary hit is conjunctive; a graph neighbour needs one
  token.** Primary inclusion requires every query token — the semantics both
  live backends already have (FTS5 ANDs its terms; the LIKE fallback requires
  each as a substring). Expansion's documented minimum relevance signal is at
  least one token. That gap is the whole point of expansion: a claim that
  partially matches and is connected by an active edge to a full match is
  exactly the recall a lexical retriever loses. A neighbour with zero query
  tokens is graph noise and is never included, whatever its degree — the
  graph-expansion fixture's noise claim has the highest degree of any
  non-anchor in it, and a test asserts that fact before asserting its
  exclusion.

- **D-v0.3.59 — Disputes and contradictions rank; they never judge and never
  exclude.** An active `disputes` source link and an active `contradicts` edge
  each subtract a bounded, pinned number of points. Neither makes a claim
  ineligible, neither hides it, neither resolves anything. U-M3 pinned that a
  contradiction records that a human said two claims disagree, not which one is
  true (D-v0.3.38); a retriever that dropped a contradicted claim would be
  answering that question by omission. Provenance and graph signals are capped
  at three occurrences each, so link count cannot become the ranking.

- **D-v0.3.60 — The benchmark corpus is memory, never a database.**
  `benchmark run` builds its corpus from the embedded fixture definitions and
  never opens `aos.db`. This is what makes "creates no database rows, files,
  ledger events or workspace state" a structural fact rather than a promise:
  there is no connection to write through, proven by a test that patches
  `db.open_db` to raise and watches the run succeed anyway. It also makes the
  run byte-identical inside a workspace, outside one, in recovery mode, and
  inside `aos.pyz`. `retrieval query` is the surface that reads a real ledger,
  and it only reads — it does not even touch the derived FTS index or its
  watermark, which `search` legitimately does.

- **D-v0.3.61 — The embedded datasets are canonical; `retrieval_benchmarks/`
  is a projection.** Exactly the U-X1 mechanic (D-v0.3.2/D-v0.3.3), for exactly
  the U-X1 reason: `aos.pyz` carries `.py` files and nothing else, so a JSON
  file could not be the source of truth without either breaking the zipapp or
  widening its allowlist. The Python definitions are the one editable registry;
  `tools/gen_retrieval_benchmarks.py --write` projects them; doctor and the
  tests verify byte-for-byte. There is no second editable registry, and
  `tools/` is outside the package allowlist so the writer never ships. No
  packaging change was needed or made — the existing `.py`-under-package
  allowlist already excludes the JSON by construction.

- **D-v0.3.62 — `baseline` is reported, never gated.** `benchmark run`'s exit
  code is driven by validation plus the promotion gate of the CANDIDATES.
  `baseline` is the measured reference: it is what production does today, it
  cannot be "promoted", and gating it would make `--candidate all` exit 1
  forever the moment the baseline was measured to leak — which is the finding,
  not a malfunction. And it does leak: on the core benchmark the baseline
  returns 8 wrong-project, 2 restricted, 8 lifecycle and 2 hash-invalid
  results. Every one of those numbers is printed, at full severity. One number
  is simply not wired to the exit code.

- **D-v0.3.63 — Truncation is reported, never silent, and never averaged.**
  Every bound truncates deterministically and increments a named counter that
  appears next to the metric it affected. Leakage counters are integer sums
  over cases and are never divided by anything: an average is how a leak in one
  case out of forty disappears. The counters are also computed from the CLAIMS
  themselves rather than from the case's `forbidden` list — a leak is counted
  because the claim IS restricted, not because the dataset author remembered to
  list its id. An author's omission cannot hide a leak, which is the only way
  the number is worth printing.

- **D-v0.3.64 — `--show-key` shows a key, and only for claims already
  eligible.** Human output defaults to metadata only. The one administrative
  content flag prints the claim `key` — never `value_md`, a source locator,
  provenance text or an evidence ref. It is consistent with `memory show`,
  which prints key AND value unredacted for exactly this population, because
  every result is eligible by construction and `restricted` is an eligibility
  exclusion: a restricted claim cannot reach the renderer to be redacted by it.
  The flag shows strictly less than the command that already exists, and the
  protection is structural rather than a redaction pass that could be forgotten.

# DECISIONS — Agentic OS v0.2 U-P1 packaging run

This section continues the `D-v0.2.*` series for the U-P1 pass executed per
`agentic-os-v0.2-u-p1-packaging-contract.md` on branch `v0.2-u-p1-packaging`
(2026-07-15). Prepended per the established precedent (D-W0.4, reaffirmed in
D-v0.2.7); everything below stays byte-identical.

## D-v0.2 decisions (U-P1)

- **D-v0.2.40 — One canonical CLI, shared by every entrypoint.**
  `agentic_os.cli.main(argv=None) -> int` is the single implementation of the
  argparse tree, command dispatch, exit-code mapping, and exception handling.
  All three entrypoints — `aos.py`, `agentic_os/__main__.py` (`python3 -m
  agentic_os`), and the zipapp's archive-root `__main__.py` — are three-line
  shims that call it and `sys.exit()` its return value. No entrypoint may
  restate a flag, a subcommand, or a dispatch rule: a second parser would be a
  second product, silently drifting from the first. What this pass did NOT
  have to change is the load-bearing part: `build_parser()` already pins
  `prog="aos"`, so usage/help text derives from the pinned prog rather than
  `sys.argv[0]`, and `--help` is byte-identical across all three entrypoints by
  construction — no `cli.py` change was needed, and none was made. `aos.py` was
  already a thin shim at baseline and was likewise not modified. Verified, not
  assumed: `python3 aos.py --help`, `python3 -m agentic_os --help`, and
  `python3 dist/aos.pyz --help` produce identical stdout and identical exit
  codes, and a domain error (`status` outside a workspace) exits 1 with
  byte-empty stdout from all three.

- **D-v0.2.41 — The archive entrypoint is the module entrypoint, verbatim.**
  The builder copies `agentic_os/__main__.py` byte-for-byte to the archive root
  as `__main__.py` rather than generating a third shim. This makes D-v0.2.40
  mechanically true instead of a convention maintained by hand — there is no
  third copy to drift — and a test asserts the byte-identity of both archive
  members against the on-disk file. The cost is one constraint, documented in
  the file itself: `agentic_os/__main__.py` must use the absolute import `from
  agentic_os.cli import main`, never a relative `from .cli import main`, so the
  same bytes are valid both inside the package (under `-m`) and at the archive
  root (where there is no parent package). Corollary:
  `zipapp.create_archive(main=...)` is deliberately NOT used — its generated
  stub calls `fn()` and discards the return value, which would force exit code 0
  for every command and silently break the exit-code contract (D-P0.9). The
  shim is explicit precisely so exit codes survive.

- **D-v0.2.42 — Zero runtime dependencies, stated and tested.**
  `aos.pyz` runs on a stock Python 3.12 with nothing outside the standard
  library. `pyproject.toml` declares `dependencies = []` (asserted by test, as
  is the absence of optional runtime extras), `requires-python = ">=3.12"`, and
  an `aos` console script bound to `agentic_os.cli:main` — the same canonical
  CLI, so an installed copy cannot behave differently. The builder is itself
  stdlib-only (`zipapp`, `pathlib`, `shutil`, `tempfile`, `os`, `stat`,
  `argparse`, `sys`; a test asserts every top-level import is in
  `sys.stdlib_module_names`). `setuptools` under `[build-system] requires` is a
  build-time requirement and is not a runtime dependency; it is the only one.
  Nothing was installed globally in this pass.

- **D-v0.2.43 — The archive carries the runtime package only, by allowlist.**
  Archive membership is exactly: `agentic_os/**/*.py` (excluding any path with
  a `__pycache__` component) plus the root `__main__.py`. This is an allowlist
  by construction, not a denylist of bad names. Every required exclusion —
  `.git`, `.agentic-os`, `tests/`, `__pycache__`, `*.pyc`, ledger and backup
  DBs, exports, local settings, credentials, `*.md` doc trees, `adapters/`,
  `research/`, `aos_hooks.py` — follows because those are either not under the
  package, or not `.py`, or under `__pycache__`. The reason is the failure
  mode: a denylist is defeated by any new file whose name nobody anticipated,
  and the thing being shipped is a file that may be copied to other machines. A
  user's ledger, vault, backup, or credential embedded in a distributed archive
  is not a cosmetic defect. Proven adversarially rather than by inspecting a
  clean tree: a synthetic contaminated source tree (containing `.env`,
  `credentials.json`, `aos.db`, a `.agentic-os/` ledger with backups, `.pyc`
  files, `__pycache__/`, `tests/`, `.git/`, docs) builds an archive whose member
  list is exactly the four legitimate `.py` files and whose concatenated bytes
  contain no `sk-live-SECRET`, no `SQLite format 3`, no ledger and no backup
  content. `[tool.setuptools] packages = ["agentic_os"]` applies the same
  explicit-allowlist posture to the sdist/wheel path instead of auto-discovery.

- **D-v0.2.44 — Output safety: `lstat`, and fail-closed refusal.**
  The builder refuses any existing output object that is not a regular file —
  symlink, directory, FIFO, socket, block/char device — exiting nonzero with
  one concise diagnostic and leaving the object exactly as found. The check
  uses `os.lstat`, never `os.stat`, and `build()` resolves only the output's
  *parent*, never its final component: resolving the final component would
  follow a symlink and defeat the check. A symlink is therefore refused even
  when it points at a regular file — writing through a link into a target the
  user did not name is the exact accident this prevents. Tested per object
  kind, each asserting the object survives unchanged (symlink still a symlink
  pointing at the same target, with the target's bytes intact; directory still
  holding its contents; FIFO still a FIFO; socket still a socket). Diagnostics
  name paths and conditions only — a test writes a secret into a refused
  directory and asserts the one-line diagnostic contains neither the secret nor
  a traceback. An existing *regular* file is a legal destination and is
  replaced only on success (D-v0.2.45).

- **D-v0.2.45 — Atomic replacement: the destination is never opened for
  writing.** The archive is staged in a `TemporaryDirectory` outside the source
  tree, written to a temp file *in the destination's parent* (same filesystem,
  so the rename is atomic), chmod'd `0o755`, and only then `os.replace`d over
  the destination. Because the destination is never opened for writing, a
  failure at any earlier step cannot truncate or corrupt it — there is no
  partial-write window to reason about. Consequences, each tested by injecting
  a real failure into the production branch and then inspecting the filesystem
  (not by matching error text): an existing valid archive survives a failed
  rebuild byte-identically, with mode intact and still a valid zipapp; a failed
  first build leaves no destination at all; a staging failure leaves the prior
  archive intact; and the temp file is removed in a `finally`, so no
  `.aos-pyz-*.tmp` debris survives either path. The builder does not modify the
  source tree (tested: package `.py` mtimes are unchanged across a build) —
  only the requested artifact and its short-lived sibling temp file.

- **D-v0.2.46 — Generated artifacts are not committed.**
  `dist/`, `build/`, `*.pyz`, and `*.egg-info/` are gitignored, and `aos.pyz`
  is not committed. A committed binary is a second copy of the runtime that
  goes stale silently the moment source changes, and reviewing it is not
  possible. The archive is reproducible from source with one stdlib-only
  command; that is the distribution story, and rebuilding is documented in
  README and TROUBLESHOOTING.

- **D-v0.2.47 — Packaging changes reach behavior, not semantics.**
  U-P1 adds ways to *reach* the CLI and changes nothing about what it *does*:
  database schema, CLI commands and flags, hook behavior, dropfile behavior,
  evidence rules, backup/export behavior, doctor semantics, migration behavior,
  and AICompany are untouched. `agentic_os/cli.py` was not modified (no
  incompatibility required it) and `aos.py` was not modified (already a thin
  shim). Evidence beyond the new tests: the pre-existing 736-test suite passes
  unchanged, and the archive's `doctor` reports the same 20 checks PASS on a
  fresh `init` as the script entrypoint does. Root resolution was verified to
  be entrypoint-independent at baseline — `--root PATH`, else cwd-upward
  discovery from `Path.cwd()`; it never consults `__file__` or `sys.argv[0]` —
  which is why the archive works from any directory, outside the repository,
  with `PYTHONPATH` cleared.

- **D-v0.2.48 — Known limitation: `hooks install` is unsupported from the
  archive; not fixed here.** `hooks.default_runner_path()` resolves the hook
  runner as `Path(__file__).resolve().parent.parent / "aos_hooks.py"` — the
  `aos_hooks.py` that ships beside `aos.py` in a checkout. Inside a zipapp,
  `__file__` is a path within the archive, so that resolves to
  `<...>/aos.pyz/aos_hooks.py`, which does not exist; there is no `--runner`
  override flag. So `hooks install` / `hooks status` / `hooks uninstall` are
  not supported from `aos.pyz` — manage hooks from a source checkout. Left
  unfixed deliberately: `aos_hooks.py` is not part of the `agentic_os` runtime
  package, so shipping it would violate D-v0.2.43; a Claude Code settings hook
  must point at a stable on-disk script path, which a zipapp's interior path is
  not, so shipping it would not actually help; and fixing it means changing
  `hooks.py`, which this pass forbids absent an incompatibility blocking a
  shared entrypoint. This blocks one command from one entrypoint — it does not
  block the shared entrypoint. The required archive paths are unaffected:
  `init`, `status`, and `doctor` never call `default_runner_path()` (it is
  reached only from the hooks install/status/uninstall handlers). Documented in
  README and TROUBLESHOOTING rather than papered over.

- **D-v0.2.49 — CI and release publication remain deferred.**
  No GitHub Actions, no release publishing, no branch-protection automation, no
  Docker, no global installation, and no third-party runtime library was added.
  U-P1 delivers the build and the entrypoints; publishing them is a separate
  decision with separate consequences (registry namespace, signing, versioning
  cadence) and is out of scope for this pass.

- **D-v0.2.50 — Gate U-P1 result.** 40 focused tests green
  (`tests/test_v02_packaging.py`), 776 green across the full suite (736
  pre-existing, unchanged; 736 + 40 = 776). Covered: module delegation to the canonical CLI via
  `runpy` with `main()` patched (proving both delegation and exit-code
  propagation); module/script `--help` and error-path stdout/stderr/exit-code
  equality; archive validity (regular file, execute bit, `#!/usr/bin/env
  python3`, `is_zipfile`); archive `--help` outside the repository with
  `PYTHONPATH` cleared, asserted equal to the script's, with a probe proving
  the checkout is genuinely absent from `sys.path`; archive and module
  `init`/`status`/`doctor` in disposable workspaces (doctor: every line
  `[PASS]`, exit 0); shebang execution; exact archive membership; adversarial
  exclusion from a contaminated tree; failure atomicity and destination
  preservation; per-kind unsafe-output refusals; custom and relative output
  paths; pyproject metadata; and `aos.py` behavior unchanged.

# DECISIONS — Agentic OS v0.2 U-H2 evidence-bearing success claims run

This section continues the `D-v0.2.*` series for the U-H2 pass executed per
`agentic-os-v0.2-u-h2-success-proof-contract.md` on branch
`v0.2-u-h2-success-proof` (2026-07-15). Prepended per the established
precedent (D-W0.4, reaffirmed in D-v0.2.7); everything below stays
byte-identical.

## D-v0.2 decisions (U-H2)

- **D-v0.2.35 — Success-dropfile ingest gate: in-file proof, after every
  other check, before the transaction.** A dropfile whose structured
  `outcome` is `success` must carry at least one acceptable evidence row
  in that same file — pre-existing task evidence never satisfies the gate.
  Acceptable means: vocabulary kind, ref non-blank after the one-line
  collapse (Python whitespace semantics, so NBSP/U+3000 count), and the
  explicitly present claim non-blank after the same collapse; the target
  of the evidence is never verified — U-H2 enforces presence and
  structural non-blankness, not truth, and no free-text classification
  exists anywhere (only the structured outcome field is judged). The gate
  runs after size, UTF-8, parse, task, secret-scan, and duplicate checks
  (a file ingested before U-H2 reaches the duplicate refusal first) and
  before the ingest transaction opens, so refusal is trivially atomic:
  exit 1 via `AosError`, stdout byte-empty, one bounded stderr diagnostic
  naming only the validated task ID and the recovery rule (add evidence,
  or use the honest `partial`/`fail`/`unknown`), zero rows and zero
  events written, and no model-controlled value echoed. `partial`,
  `fail`, and `unknown` remain valid with an empty evidence section; no
  outcome is added. The U-H1/U-H2 boundary, pinned: the hooks stay
  transport-only — a structurally valid success envelope with an EMPTY
  evidence section still stages and publishes exactly as D-v0.2.29
  records — and the gate refuses that file at ingest, where the ledger is
  actually written. (A blank-ref evidence row, by contrast, is now
  structurally malformed per the shared parser, so the hook refuses to
  stage it — parser parity, unchanged posture, not new hook policy.)

- **D-v0.2.36 — The evidence-only slice of D-v0.2.20.** U-H2 takes
  exactly the evidence items of the approved-for-later hardening list:
  post-collapse dropfile evidence validation (a ref or claim that
  collapses to empty refuses as a malformed evidence line, named by line
  number and field, never by value — with the honest grammar note that a
  whitespace-only claim is right-stripped off the line and refuses as an
  evidence-line shape mismatch at the same line, since strip and collapse
  share Python's Unicode whitespace definition) and non-blank evidence
  refs/claims at the trusted CLI write (`ops.add_evidence` refuses a
  whitespace-only ref, and a whitespace-only explicitly supplied claim,
  before any lookup, hashing, mutation, or event; `claim=None` stays
  legal; file-sha256 and evidence-git behavior is unchanged for non-blank
  values). The rest of D-v0.2.20 (priority bounds, task text, agent-name
  grammar, run summaries) remains deferred. Legacy blank-ref rows
  admitted through the pre-U-H2 regex hole are surfaced by a new
  warn-only doctor line naming bounded `E-XXXX` IDs and counts only —
  they are never rewritten or deleted, and `mark_done`/the done gate
  still count them exactly as before.

- **D-v0.2.37 — Run-bounded recovery window; `evidence.run_id` stays
  dormant.** Doctor gains a warn-only check for ended runs with outcome
  `success` that no acceptable evidence is attributable to. Evidence is
  attributable to run R when: same `task_id`; ref non-blank after
  normalization; `created_at >= R.started_at`; and, when a next run
  exists for the task (the earliest strictly later run in the
  `(started_at, id)` total order), `created_at` strictly earlier than
  that next run's `started_at`. So: evidence during the run counts;
  evidence added after a successful end still counts until the next run
  starts (the recovery window); evidence belonging to a later run cannot
  heal an earlier one; evidence created before the run never counts; and
  two sequential runs sharing one second-precision `started_at` are
  judged conservatively — the earlier run's window is empty, so
  shared-timestamp evidence never heals it. Deliberately rejected
  alternatives: populating `evidence.run_id` (a schema-semantics change
  and a new write path U-H2 does not need), any schema change, and a new
  evidence-linking CLI. The warning names run IDs only — total count plus
  at most the first 10 (`(+N more)`) — never a ref, claim, summary, or
  agent value, and stays warn-only (doctor exit 0 when hard checks pass).

- **D-v0.2.38 — Direct run endings and `mark_done` stay untouched.**
  `run end --outcome success` remains accepted with no evidence check and
  no warning — CLI surface, stdout, stderr, summary semantics, and event
  shape are byte-identical to pre-U-H2. It is the documented human
  recovery path after a gate refusal (the human verifies, records
  evidence via the CLI, and ends the run honestly), and doctor's
  D-v0.2.37 window is the audit that closes the loop afterwards.
  `mark_done` and the done-override flow (D-v0.2.5) are unchanged.

- **D-v0.2.39 — Gate U-H2 result.** Focused suite
  (`tests/test_v02_success_proof.py`) 42 green; U-H1 hook suite 91 green
  (unchanged count); full suite 736 green (694 pre-existing, none
  weakened or deleted); `compileall` clean; `git diff --check` clean.
  Renderer and all four checked-in `adapters/*/PROTOCOL.md` stay
  byte-identical; the one concise success rule lives in the SHARED
  dropfile section (the gate judges every adapter's dropfiles), so the
  codex/gemini/generic protocols were regenerated alongside claude-code —
  a reported deviation from the expected file list, forced by the
  existing all-adapters parity invariant. Four existing test pins moved,
  each the minimal mandated edit, also reported: the U-H1 dogfood
  scenario 5 body gained one evidence row (its identity is duplicate/
  retry + dedupe; the old success/empty ingest-accepts assertion is
  exactly what U-H2 forbids, and the refusal is pinned in the U-H2
  suite), and three doctor line-count pins moved 18 → 20 under the
  D-W8.1 "pin moves up with mandated new checks" pattern
  (test_cli, test_weekend_views, test_v02_secret_safety).

# DECISIONS — Agentic OS v0.2 U-H1 SessionEnd hook + installer run

This section continues the `D-v0.2.*` series for the U-H1 pass executed per
`agentic-os-v0.2-u-h1-sessionend-hook-contract.md` on branch
`v0.2-u-h1-sessionend-hook` (2026-07-14). Prepended per the established
precedent (D-W0.4, reaffirmed in D-v0.2.7); everything below stays
byte-identical.

## D-v0.2 decisions (U-H1)

- **D-v0.2.28 — Two-stage bridge: Stop captures the official
  `last_assistant_message` only; SessionEnd publishes.** The Stop hook is
  the only stage that sees session text, and it sees exactly one field of
  the official hook JSON — never the transcript. `transcript_path`
  (supplied to SessionEnd) is metadata and is never opened, so the bridge
  has zero dependency on the transcript JSONL format and cannot break when
  that format changes. Splitting capture from publication buys three
  things: the envelope is validated while the session is still alive (the
  agent sees the refusal diagnostic on its own Stop and can correct
  itself in the next turn — latest envelope wins); publication happens
  exactly once per session at a well-defined lifecycle point with a
  documented `reason` vocabulary (`clear|logout|prompt_input_exit|other`;
  anything else refuses rather than guesses); and a crashed session
  leaves an inert staged record instead of a half-published dropfile.
  The Stop handler never blocks: stdout stays empty in every outcome (no
  decision JSON can exist on an empty stream) and exit 2 — the Stop-hook
  blocking signal — is never used; refusals are exit-1 diagnostics.
  Compatibility is capability-based (Stop/SessionEnd command hooks, JSON
  on stdin, `last_assistant_message` present); no Claude Code minimum
  version is invented anywhere.

- **D-v0.2.29 — The envelope IS the dropfile protocol; one schema, two
  transports.** The write-back envelope is a fenced ```` ```aos-dropfile ````
  block (both fences at column 0) whose content is byte-for-byte the
  existing dropfile format. The hook reuses `ingest.parse_dropfile`, the
  U-C1 `MAX_DROPFILE_BYTES` cap, and the U-C3 detector via the new shared
  `ingest.secret_findings` (extracted from `_scan_for_secrets`, same
  behavior) — no competing schema, no new validators, and every field the
  manual path supports (task, agent, outcome, summary, evidence rows,
  open questions) flows through unchanged. U-H2 is explicitly NOT smuggled
  in: a success outcome with zero evidence rows stages and publishes.
  Exactly one envelope per message; two or more refuse (with one staged
  record per session, picking a winner would silently drop the rest). An
  unterminated or indented fence is "no envelope" (silent no-op), as is a
  session outside any initialized workspace — the hooks are safe to
  install user-wide. Hook stdin itself is capped (16 MiB) in the U-C1
  bounded-input posture. Diagnostics name conditions, counts, and line
  numbers, never untrusted values — a session id, reason string, or
  envelope value is never echoed.

- **D-v0.2.30 — Staging/publication identity and the deterministic
  recovery rule.** The staged record
  (`exports/hook-staging/stop-<session>.json`) binds a format marker
  (`aos-u-h1-staged/1`), the session id (charset-fenced
  `[A-Za-z0-9-]{8,128}` — it becomes a filename component, so the fence is
  also the traversal guard), the envelope text, and its sha256. SessionEnd
  re-validates ALL of it immediately before publication (marker, binding,
  digest, size caps, parse, secret scan): a tampered, replaced,
  secret-bearing, or malformed record refuses with the record retained;
  only ENOENT reads as absence — any other inspection error refuses
  (U-C4's fail-closed lesson). The published name
  `dropfile-<task>-<agent>-hook-<session8>-<sha12>.md` is deterministic
  and carries the dedupe identity: the sha256 of the published bytes is
  exactly the hash `ingest` journals for its own dedupe, closing the loop
  end-to-end. Publication is a same-directory temp file + `os.link`
  (never overwrites) + temp unlink; retries converge — identical bytes at
  the name are idempotent success, different bytes refuse. Recovery rule,
  pinned: a staged record is removed ONLY after verified publication
  (fresh or identical); every refusal retains it byte-for-byte; a
  post-publication removal failure warns at exit 0 (the deterministic
  name makes the leftover harmless). Stale records from crashed sessions
  are inert and documented as safe to delete or salvage by hand. Honest
  limit, stated: owned-path checks are lstat/O_NOFOLLOW (symlinked
  `exports/`/`hook-staging/` and non-regular files refuse before any read
  or write), not the U-C4 descriptor-pinned depth — a same-directory race
  inside the check-to-write window is documented, not defended.

- **D-v0.2.31 — Hook handlers run via a dedicated root runner, not the
  CLI; the prohibition list is structural.** Claude Code invokes
  `python3 <checkout>/aos_hooks.py stop|session-end` — a thin sibling of
  `aos.py` that imports `agentic_os.hooks` (script-directory sys.path,
  works from any hook cwd). The handlers therefore reuse the package's
  validators without ever invoking the `aos` CLI, and the module's runtime
  path contains no subprocess, SQLite, git, or network call to misuse —
  the test suite additionally hard-patches `subprocess.*`, `os.system`,
  `sqlite3.connect`, and `socket.socket` to prove none is reached, records
  every file open to prove nothing under the workspace outside
  `exports/` is read (transcript included), and pins stdout-empty across
  all outcomes.

- **D-v0.2.32 — Installer: documented user settings file, dry-run
  default, marker-based ownership, semantic idempotency.** Target is the
  documented Claude Code user settings file `~/.claude/settings.json`
  (`--settings PATH` overrides; tests and the build never touch the real
  one). Dry-run is the default posture and prints the exact deterministic
  unified diff; `--apply` demands a typed `yes`, writes a byte-exact
  collision-suffixed backup (`settings.json.aos-backup-<stamp>`,
  documented restore: `cp <backup> <settings>`), validates the exact
  resulting bytes, and lands via same-directory temp file + fsync +
  atomic `os.replace` with the original file mode preserved (0600 fresh).
  Ownership is the `aos_hooks.py` token in a command entry: install heals
  to exactly one AOS-owned group per event (appended last), uninstall
  removes only owned entries and drops only containers its own removal
  emptied; unrelated settings, events, and hooks survive semantically via
  the JSON round-trip (a reformat of an untouched file never happens —
  idempotency is judged on the parsed document, so an already-merged file
  is never rewritten). Unsupported shapes (non-object root, non-list
  event arrays, non-object groups, non-list group hooks), invalid JSON,
  symlinked/irregular settings paths, and missing parent directories all
  refuse with zero mutation. `status` reports
  absent/installed(version+digest)/drifted, where the digest is the
  sha256 over the exact expected handler commands and protocol version
  `u-h1/1`. The installer opens no ledger and records no evidence — the
  human records merge evidence per repo convention.

- **D-v0.2.33 — Accelerated dogfood gate.** Instead of five repetitive
  manual sessions: an automated five-scenario matrix (normal success,
  failure outcome, no envelope/no evidence, secret-shaped refusal,
  duplicate/retry) driven against a REAL initialized workspace all the
  way through manual `ingest dropfile` of the published file — plus ONE
  real live smoke (hooks installed into a disposable settings file, one
  real Claude Code session, manual ingest) to be performed by the human
  before merge. The matrix also proves the ledger's own sha256 dedupe
  refuses a second ingest of the same published bytes.

- **D-v0.2.34 — Gate U-H1 result (audit-corrected 2026-07-15).** Focused
  suite (`tests/test_v02_hooks.py`) 91 green; full suite 694 green (603
  pre-existing, none weakened or deleted); `compileall` clean;
  `git diff --check` clean. Audit correction, history preserved: this
  entry originally recorded 67 focused / 670 full, but the branch as
  shipped before the 2026-07-15 bounded corrective pass actually carried
  70 focused / 673 full; the totals above add that pass's 21 regression
  tests (superseded-staging invalidation, linear envelope scanner with
  end-of-message fence rule, bounded published-name components, agent
  secret-shape scan shared with manual ingest, settings lost-update
  guard, exact-command hook ownership, `"hooks": null` refusal,
  SessionEnd workspace-gate-before-reason ordering, unpaired-surrogate
  refusals on both validation paths, and uniform staged-record recovery
  pointers — including the retargeted uninspectable-staging test).
  Renderer and checked-in `adapters/claude-code/PROTOCOL.md` stay
  byte-identical (existing U-C3 parity test now also covers the envelope
  section); codex/gemini/generic adapters unchanged.

# DECISIONS — Agentic OS v0.2 U-C4 Windows read-only export run

This section continues the `D-v0.2.*` series for the U-C4 pass executed per
`agentic-os-v0.2-u-c4-windows-export-contract.md` on branch
`v0.2-u-c4-windows-export` (2026-07-13). Prepended per the established
precedent (D-W0.4, reaffirmed in D-v0.2.7); everything below stays
byte-identical.

## D-v0.2 decisions (U-C4)

- **D-v0.2.27 — U-C4 sixth corrective pass (rollback identity guard R1,
  2026-07-14).** A sixth review confirmed one remaining defect of the
  fourth/fifth passes' own class: the rollback rename (`PREV → AOS`) —
  reached when the post-move-aside fsync or the promotion rename
  fails — renamed whatever sat at the previous name onto the
  AUTHORITATIVE name with no identity proof, although the run already
  held the PREV identity pinned right after the move-aside. A racer
  substituting PREV inside the promotion window therefore had its
  never-validated tree promoted to `PATH/AOS`, the validated staging
  was then discarded, and the failure reported "the previous
  generation was restored and the destination is unchanged" — false on
  every count (witnessed on the production path before the fix).
  Corrected minimally (R1): both rollback sites pass the pinned PREV
  identity, and the rollback rename runs only after a fresh
  fd-relative lstat of the previous name proves exactly that identity
  (the held PREV descriptor keeps the inode alive, so the proof cannot
  be forged by inode recycling). A never-pinned, uninspectable (only
  ENOENT reads as absence, per F4), or replaced PREV refuses the
  rollback: the entry is retained untouched, the complete staged
  generation is kept, and the export strands with the exact live state
  and shell-quoted `mv` recovery commands; a vanished PREV strands
  without instructing inspection of a nonexistent tree. Residue,
  stated honestly: the guard-lstat-to-rename gap is the same
  irreducible window as the move-aside guard's. Two regression tests
  pin the mechanism, each written first and watched fail against the
  unguarded rename (focused suite 213, full suite 603 green).

- **D-v0.2.26 — U-C4 fifth corrective pass (race-condition corrections
  Q1–Q5, 2026-07-14).** A fifth review confirmed five race-condition
  defects in the uncommitted U-C4 code; all five are corrected without
  widening scope, each pinned by regression tests proven to fail against
  the surgically reverted mechanism (28 new tests; focused suite 211,
  full suite 601 green). A multi-agent adversarial re-review of the
  corrections then confirmed and closed five further defects in the new
  code itself — an interior cleanup ENOENT masquerading as "staging
  genuinely absent" (Python maps errno.ENOENT to FileNotFoundError at
  construction, so absence is now signalled by a dedicated exception
  raised only by the pre-mutation pin-open), a spurious removal WARN for
  a PREV that had already vanished, a source-descriptor leak on the
  os.fdopen failure path (a directory raced onto a note's name), a
  RecursionError from a hostile deeply-nested tree escaping as an
  exit-2 internal error that masked the original failure, and
  replacement-retention messages omitting the exact retained quarantine
  location — plus documentation overclaims (the rename-overwrite
  residue also covers regular files, the staging-content window is per
  file, child quarantine names nest inside their parent directory) and
  test-soundness gaps (the file-level source device check was untested,
  one alias assertion was tautological, hardlink skip guards were
  unreachable). Where an earlier claim was too strong, it is narrowed
  honestly rather than kept. Policies pinned:
  (a) *Quarantine-based cleanup (Q1, amends C1).* The fourth pass still
  deleted by NAME (lstat-classify then `unlink(name)`/`rmdir(name)`),
  so a replacement raced in between classification and deletion was
  deleted — that claim is retracted. Cleanup now never names a
  meaningful entry for deletion: the identity-proven ROOT is ATOMICALLY
  renamed to a fresh single-use private cleanup name at PATH level
  (`PATH/.aos-export-cleanup-<pid>-<n>`); every CHILD is atomically
  renamed to a `.aos-export-cleanup-<pid>-<n>` name INSIDE ITS OWN
  parent directory (nested within the quarantined tree, never a direct
  child of PATH); each captured entry is re-proven against the
  inspected identity (roots against the HELD descriptor), a captured
  mismatch is restored to its public name and the cleanup refuses, and
  the final unlink/rmdir targets only the just-re-proven private name.
  Failures restore the in-flight subtree and root toward their public
  names (a failed intermediate restore is itself reported, never
  silently discarded); only the initial pin-open's ENOENT reads as
  "genuinely absent" (a dedicated exception type — errno mapping makes
  an interior ENOENT a FileNotFoundError, which must surface as a
  reported retention instead), a RecursionError from a hostile
  deeply-nested tree becomes a reported retention rather than an
  internal error, and a PREV that vanished before cleanup warns
  accurately without instructing removal of a nonexistent tree. The
  reserved PATH-level cleanup names join the mutation roots; a leftover
  one (interrupted cleanup) is detected by a names-only listing of PATH
  and refuses the next run in both modes. NARROWED GUARANTEE: stdlib
  has no delete-by-descriptor and no no-replace rename, so an entry
  raced onto a just-verified single-use PRIVATE name in the
  pre-deletion syscall gap (for rmdir: only an empty directory), or a
  TYPE-COMPATIBLE entry raced onto a probe-fresh quarantine/restore
  target name before the rename (an empty directory for a directory
  move; a regular file or symlink for a file move — on the restore path
  that target is the entry's PUBLIC name), remains deletable — entries
  at meaningful names outside those windows are never deleted without
  an identity proof.
  (b) *Descriptor-anchored copy source (Q2, amends C4).* The build's
  payload copy opened an absolute source pathname (O_NOFOLLOW protects
  only the final component; a swapped source entity directory could
  redirect the read). The plan now records per-file source identities
  and the source-root identity; the build pins the source root for its
  complete run; every copy (creates, updates, unchanged fallback) opens
  entity dirs O_DIRECTORY|O_NOFOLLOW relative to the pin, the basename
  O_RDONLY|O_NOFOLLOW|O_NONBLOCK relative to the entity descriptor,
  requires S_ISREG + samestat with the plan record, copies only from
  the descriptor, and re-fstats after the copy. No absolute source open
  remains in the copy path (regression-forbidden).
  (c) *Final hardlink check without intermediate symlinks (Q3, amends
  F3).* The live side of the final hardlink verification was probed via
  "AOS/<rel>" under the destination descriptor — intermediate
  components followed symlinks, so a moved entity directory plus a
  symlink back to it passed samestat while retaining an external alias
  into the promoted generation. The held aos_fd now flows into the
  final verification; entity directories open O_DIRECTORY|O_NOFOLLOW
  relative to it and must carry exactly the identity the pinned rescan
  recorded; basenames are lstat'ed fd-relative; the live file must
  samestat the staged link AND have st_nlink == 2. The staged-alias
  tolerance probe is anchored the same way under the staging
  descriptor.
  (d) *Freshest-last final verification (Q4, amends F2).* A live
  destination write through a staged hardlink could mutate staged bytes
  after they were hashed while source verification still ran. Order is
  now: fresh source scan+hash FIRST, complete destination recheck
  second, complete staging rescan + content hash LAST (hardlink counts
  and identities re-checked in that last scan), then only identity
  lstats (structural guard, move-aside guard) and the renames — no
  content is read or hashed after the final staging scan, and the
  documented unobservable window is per file: from that file's read in
  the final rescan to the renames.
  (e) *Source mount containment (Q5).* Every source scan compares each
  non-hidden entry's st_dev with the source root (plus the additive
  mount probe for directories) and refuses mounted or cross-device
  source subtrees before any copy or hash; the same-filesystem
  bind-mount limitation of F6 applies unchanged.
- **D-v0.2.25 — U-C4 fourth corrective pass (reliability corrections
  C1–C6, 2026-07-14).** A fourth review confirmed six implementation
  defects in the uncommitted U-C4 code; all six are corrected without
  widening scope, each pinned by deterministic regression tests (31 new
  tests; full suite 570 green). Policies pinned:
  (a) *Identity-safe cleanup (C1).* Recursive STG/PREV cleanup runs
  through `_rmtree_pinned`: pin the root `O_RDONLY|O_DIRECTORY|
  O_NOFOLLOW` relative to the pinned PATH descriptor → prove the pinned
  identity equals the identity THIS run recorded (staging at creation;
  PREV pinned by an open descriptor taken immediately after the
  AOS→PREV rename, chained to the verified AOS root identity) → apply
  the C3 containment checks → delete children bottom-up with
  descriptor-relative operations only → re-check the named root before
  the final `os.rmdir`. `shutil.rmtree` is never used on STG or PREV,
  and the mutable root pathname is never reopened for deletion. The
  identity chain is descriptor-pinned end to end: staging (held from
  creation across every discard path), the verified AOS root (pinned at
  the recheck BEFORE its content rescan and held through promotion —
  the move-aside guard and the PREV proof compare against this held
  descriptor), and PREV (pinned immediately after the move-aside, held
  until cleanup). An open descriptor keeps the inode alive, so a freed
  inode number cannot be recycled into a foreign directory and defeat a
  samestat proof (observed live on tmpfs during this pass — tests and
  an adversarial reproduction caught recorded-stat versions deleting a
  substituted tree; both closed by the held-descriptor chain). Any root
  whose identity cannot be proven is retained byte-for-byte and
  reported (exit-0 WARN for PREV after successful promotion).
  (b) *Pinned hardlink source (C2).* Unchanged-file reuse links through
  the descriptor chain PATH-fd → AOS fd → entity fd (each
  O_DIRECTORY|O_NOFOLLOW), requires the source to be a regular file
  whose identity equals the plan-time record (`ExportPlan.
  base_identity`), calls `os.link(src, dst, src_dir_fd=…, dst_dir_fd=…,
  follow_symlinks=False)`, and verifies the staged link's type AND
  identity afterwards. `target.dest_aos / rel` is forbidden as a link
  source; a replacement PATH never has a link count changed.
  (c) *Cleanup-root containment (C3).* Before any deletion the pinned
  cleanup root must sit on the pinned destination's device, must not be
  a mount point (additive probe), and every descendant is swept for
  device/mount transitions through the pinned descriptor; a rejected
  root is retained with nothing beneath it modified. Same-filesystem
  bind mounts stay a documented stdlib limitation.
  (d) *Vetted reads (C4).* One shared reader (`_read_vetted_file`)
  performs every enforcement-critical read: descriptor-relative
  O_RDONLY|O_NOFOLLOW|O_NONBLOCK open, fstat of the opened descriptor,
  S_ISREG required, samestat against the inspected identity when
  provided, pre- and post-read fstat with identity/size stability, and
  actionable AosError refusals. Used for plan comparison, base-snapshot
  hashing, source scanning/hashing, and final source verification;
  `Path.read_bytes` is regression-forbidden for these. The build's
  payload-copy source open carries the same O_NOFOLLOW|O_NONBLOCK +
  S_ISREG vetting (a FIFO raced into a source note cannot block the
  copy), and the protected-root existence probe fails closed (an
  uninspectable candidate stays protected; EACCES/EIO surface as exit-1
  refusals, never exit-2 internal errors; an ELOOP no longer silently
  drops repository protection) — both found by this pass's adversarial
  review.
  (e) *Actual execution statistics (C5).* `apply_plan` returns a frozen
  `ApplyResult` (created/updated/deleted/unchanged, hardlinked vs
  fallback-copied unchanged, `payload_bytes_written`, `cleanup_warning`)
  measured during execution — copies report the fstat'ed size of the
  flushed staged file, hardlinks contribute zero bytes, fallback copies
  count in full; the CLI prints exclusively from it.
  (f) *Directory-visible dry-run (C6).* `ExportPlan.dir_creates` /
  `dir_deletes` are deterministic sorted differences; dry-run prints
  `create-dir REL/` / `delete-dir REL/` lines and a summary that counts
  files and directories separately, so a directory-only plan never
  shows zero visible operations.
- **D-v0.2.24 — U-C4 third corrective pass (filesystem-consistency
  findings F1–F6).** A third review confirmed six local
  filesystem-consistency issues in the uncommitted U-C4 implementation;
  all six are fixed without widening scope, each with regression tests
  proven to fail against the uncorrected mechanism. An adversarial
  multi-lens re-review of the fix itself then confirmed a further round
  of pathname/descriptor divergences and untested clauses; those are
  folded in below and each is pinned by a mutation-verified test.
  Policies pinned:
  (a) *Pinned destination descriptor (F1).* Before its first mutation the
  apply opens PATH `O_RDONLY|O_DIRECTORY|O_NOFOLLOW` (where available),
  fstats it, and requires identity equality with the destination identity
  recorded in the plan; the descriptor stays open for the COMPLETE apply.
  Staging is created and opened (O_NOFOLLOW) relative to it, every
  AOS/STG/PREV rename passes `src_dir_fd`/`dst_dir_fd`, every PATH-level
  durability fsync syncs the pinned descriptor itself, STG/PREV cleanup
  deletes fd-relative, and the enforcement rescans of destination and
  staging content walk and read descriptor-anchored (`os.fwalk` with
  `dir_fd`; per-file O_NOFOLLOW+O_NONBLOCK opens with an fstat samestat
  against the vetted lstat). After the pin, PATH-derived pathnames are
  consulted only to verify the pathname still reaches the pinned
  directory, to re-derive containment refusals, and for an additive
  best-effort mount probe — never for a mutation, an enforcement read,
  or a cleanup. Staging is discarded only after a samestat identity
  proof against the pinned staging descriptor; anything else at the
  staging name is RETAINED and reported. A replaced PATH, or a staging
  entry swapped between mkdir and open, refuses before any generated
  entry can appear outside the originally approved destination.
  (b) *Complete staged-generation re-verification (F2).* Validation
  returns an immutable `StagingSnapshot` (root identity, sentinel state,
  directory set, file set with sizes, length-framed content hash, entry
  types enforced by the scan, recorded hardlink relationships).
  Immediately before promotion — after the destination recheck — the
  ENTIRE staging generation is rescanned through the pinned staging
  descriptor and must equal the snapshot and a fresh source scan exactly;
  any stable post-validation change (bytes, file or directory add/remove,
  sentinel, symlink or special entry, root identity, hardlink
  relationship) refuses. The verification ends with a structural
  destination guard (PATH pathname identity, AOS root identity, PREV
  absence), so the unobservable interval for staging content and
  destination structure begins after it returns and ends at the
  promotion rename. Precisely stated limits: a destination CONTENT
  change during the staging verification itself is within the accepted
  window (the full content recheck runs immediately before it), and
  metadata-only destination changes (permissions, timestamps) are never
  part of the base snapshot.
  (c) *Constrained staged hardlinks (F3).* The build RECORDS which
  unchanged rels it intentionally hardlinked (with the staged link's
  device/inode identity); ownership is never inferred from link count.
  Validation and the final verification require st_nlink == 1 for every
  created, updated, or copied-unchanged staged file, and for every
  recorded link exactly st_nlink == 2 with the recorded identity — plus,
  at the final verification, `os.path.samestat` against the corresponding
  CURRENT AOS file. Any extra link, wrong identity, or missing expected
  source refuses; the pre-promotion destination rescan tolerates the
  staged alias only for rels the build recorded.
  (d) *Inspection errors are errors (F4).* One explicit `_lstat_or_absent`
  helper replaces `os.path.lexists` for the initial STG/PREV stale checks,
  the mutation-root probes, and the final PREV/STG verification:
  FileNotFoundError means absent; every other OSError (EIO, EACCES,
  EPERM, ...) produces an actionable refusal naming the path and cause.
  An uninspectable STG at the final recheck is additionally RETAINED —
  it is no longer provably ours.
  (e) *Sentinel durability (F5).* The ownership-sentinel directory is
  opened O_NOFOLLOW relative to the pinned staging descriptor and fsynced
  under the existing directory-fsync errno policy. Durability order:
  staged file writes (flush+fsync) → staging root → sentinel → entity
  directories → the PATH-level rename fsyncs.
  (f) *Mount containment (F6).* Mounted or cross-device subtrees inside
  AOS or STG refuse before adoption, validation, or promotion (per-entry
  st_dev vs the root device, plus `os.path.ismount` for directories; the
  AOS root itself must sit on PATH's filesystem), and every recursive
  STG/PREV cleanup sweeps for mount boundaries first — never inspected
  means never deleted. The sweep is descriptor-anchored (`os.fwalk` with
  `dir_fd`), so it inspects exactly the tree the fd-relative delete
  would recurse into; the pathname `os.path.ismount` probe is
  additive-only (its errors read as "no extra evidence", never as
  clearance). Documented limitation, stated wherever the claim
  appears: a bind mount of the SAME filesystem has the same st_dev and is
  invisible to `os.path.ismount`, so the standard library cannot
  distinguish it from a plain directory; cross-device mounts are the
  enforced class.
- **D-v0.2.23 — U-C4 post-review hardening.** Independent review of the
  D-v0.2.22 implementation confirmed four blockers and five hardening
  gaps; all nine are fixed without widening U-C4 scope. Policies pinned:
  (a) *Fresh plan + destination base snapshot.* check_destination's
  adoption inspection stays the refusal-first gate before any local work,
  but the plan is computed from a FRESH destination scan taken after the
  mirror regenerates (dry-run prints from that fresh state), and
  `ExportPlan` records an exact base snapshot — AOS existence and
  directory identity, directory set, file set with sizes, sentinel
  presence, and a length-framed content hash (relpath + NUL + length +
  NUL + bytes per file, sha256). The pre-promotion recheck rescans and
  requires an exact match; any addition, deletion, content edit,
  directory change, root replacement, or identity change exits 1 with
  "Refusing to export: destination changed during export; rerun to
  compute a fresh plan." — a late destination file can no longer be
  silently swept by the whole-tree swap (the rerun's fresh plan SEES it
  as an explicit, previewable delete).
  (b) *Ownership sentinel.* Recognized filename shape is NOT proof of
  ownership (a human `Home.md` or `Tasks/T-9999.md` is not ours to
  delete). `PATH/AOS/.aos-export-owned` — one exact reserved EMPTY
  internal directory, invisible to file-based tree hashes — is created in
  staging, required by validation, preserved through promotion, excluded
  from note counts and comparisons, and demanded on every repeat export.
  First exports adopt only an absent or genuinely empty AOS; a nonempty
  AOS without the exact sentinel, any content inside it, or any other
  hidden entry refuses.
  (c) *Lexical workspace derivation.* The live workspace and the upward
  `.git` search derive from `aos_dir.parent.resolve()` (lexical parent,
  then resolve), never `aos_dir.resolve().parent`: with `repo/.agentic-os`
  symlinked elsewhere the latter protected only the link target's parent
  and permitted `repo/AOS` as an export root. The `.agentic-os` target,
  database parent, vault, and source mirror stay independently resolved
  and protected.
  (d) *Complete final recheck with a pinned staging identity.* The
  recheck re-lstats AOS, STG, and PREV (symlinks refuse for all three),
  confirms `PATH` identity, requires PREV absent, repeats containment,
  and holds AOS to the base snapshot — never resolve-and-accept of a
  replacement real directory. STG must be the same real directory this
  run created, verified via an O_DIRECTORY descriptor held open since
  mkdir: the open descriptor pins the inode, closing the rmtree+mkdir
  inode-reuse hole that defeats a samestat-only check. The STG check runs
  first — staging is only discarded while provably ours; a removed or
  replaced STG is RETAINED with instructions. The post-recheck/pre-rename
  interval remains the only accepted TOCTOU exclusion.
  (e) *Rollback durability.* `rename(PREV, AOS)` is followed by a PATH
  fsync. If the rollback fsync fails, no durable-restoration claim is
  made and the complete staging tree is NOT discarded: the error reports
  the exact live state (AOS = previous generation, new generation at STG)
  and the possible post-crash state (AOS missing, previous generation at
  PREV — the existing drill row).
  (f) *Reported staging cleanup.* No `ignore_errors=True`: a failed
  staging cleanup appends "staging … could not be removed …; remove it
  before rerunning" to the original error instead of masking either.
  (g) *Shell-quoted recovery commands.* Every emitted `mv` recovery path
  goes through `shlex.quote` (destination paths routinely contain
  spaces).
  (h) *Hardlink-alias refusal.* Adopted regular destination files must
  have link count 1 — an alias means the bytes are shared with something
  outside AOS, which full ownership cannot claim (and staging's own
  `os.link` reuse would propagate the alias into every future
  generation). During the pre-promotion rescan exactly one extra link per
  file is tolerated: this run's own staged hardlink, verified by
  samestat against the staged path.
  (i) *lstat-typed staging validation.* Every staged entry is lstat'ed;
  only real directories and regular files pass — staged symlinks (even to
  byte-identical content) and special files refuse before any content
  read (a FIFO must not hang validation).
  (j) *Descriptor-anchored staging build (self-review addendum).* An
  adversarial re-review found one build-phase escape the post-build
  recheck could not catch: a same-user racer swapping a just-created,
  still-empty staging entity directory for a symlink, so the subsequent
  O_EXCL note writes land outside AOS/STG/PREV. Closed by building every
  file through pinned directory descriptors — entity dirs created relative
  to the pinned STG-root fd and reopened O_NOFOLLOW; files created relative
  to those fds (O_CREAT|O_EXCL, `os.link` with `dst_dir_fd`) — so a raced
  symlink swap is refused (ELOOP/EEXIST), never followed. The same review
  also collapsed the plan's destination reads to one per file (the bytes
  feed both change-detection and the base-snapshot hash) and corrected the
  contract's tree-hash formula to record the length framing the code
  already used.
- **D-v0.2.22 — U-C4 implementation policies.** Baseline gate: branch
  `v0.2-u-c4-windows-export`, HEAD `70aac05`, clean tree, 390 tests OK.
  `aos sync --export-to PATH [--dry-run]` lands in
  `agentic_os/mirror_export.py`; policies pinned during implementation:
  (a) *Whole-tree generation swap, never per-file live replacement.* The
  destination `PATH/AOS` always holds one complete generation: the next
  generation is built and validated in `PATH/.aos-export-staging`, the
  current one moves aside to `PATH/.aos-export-previous`, staging is
  renamed in, and PREV is removed only after durability is confirmed.
  A failed promotion rolls back to PREV; a failed rollback leaves both
  complete generations with exact `mv` recovery commands. Per-file
  replacement of a live tree was REJECTED: an interruption would leave a
  mixed-generation mirror, which the contract forbids outright. The
  update path has a two-rename window with no `PATH/AOS`; the first
  export is a single atomic rename.
  (b) *Full ownership of `PATH/AOS`.* Nothing inside it is preserved —
  adoption refuses any hidden, symlinked, non-regular, or unrecognized
  entry (the doctor note-recognizer doubles as the provenance test, and
  the export refuses to ship anything the recognizer would not
  re-accept). Preservation applies only outside the three mutation roots;
  docs direct Obsidian at PATH as the vault root, never PATH/AOS.
  (c) *Copy-if-changed.* An identical source (file set, bytes, dir set)
  performs zero mutation — no staging, no rename, no write. Changed
  exports hardlink unchanged destination files into staging and copy only
  changed/new files; `os.link` falls back to copying ONLY on the
  recognized unsupported-link errnos {EPERM, EACCES, EOPNOTSUPP/ENOTSUP,
  ENOSYS, EXDEV, EMLINK} — any other errno (EIO, …) aborts with the old
  generation intact. Change detection is size-then-byte, never mtime.
  (d) *Existence-aware mutation-root containment.* Only the three
  mutation roots are checked (PATH may be an ancestor of the repository):
  PATH resolves strictly first; each root, when present, is lstat'ed
  (symlink ⇒ refusal) and strictly resolved, and when absent its
  candidate is the resolved parent plus the fixed child name. Overlap
  with the independently resolved protected set (workspace, .agentic-os,
  db parent, vault, source mirror, enclosing git root — a `.git` file
  counts, for worktrees) uses normalized equal/inside/contains always
  plus `os.path.samestat` whenever both sides exist; the checks repeat
  immediately before promotion.
  (e) *Durability.* Staged copied files are flushed+fsynced; staged
  directories and PATH (after each rename and after PREV cleanup) are
  fsynced with directory-fsync failures skipped ONLY for {EINVAL,
  ENOTSUP/EOPNOTSUPP, ENOSYS} (9P/DrvFS reject directory fsync); any
  other errno is fatal and lands in the documented recovery state for
  that phase. File-fsync failures are always fatal.
  (f) *Stale state refuses in dry-run too.* Existing staging or previous
  directories mean an interrupted or concurrent export — both modes exit
  1 with the recovery instructions and compute no plan; nothing is ever
  auto-cleaned (it could be a live run's staging or the only last-good
  copy).
  (g) *Windows representability, deterministic on all platforms.*
  Refusals for reserved device stems, illegal characters, control
  characters, trailing dot/space, source casefold collisions (mixed-case
  agent names are the only generated source), and components above 255
  UTF-16 code units — the accurate NTFS limit; no invented total-path
  limit, and source-side POSIX limits surface as the real OS error.
  (h) *Boundaries.* The export is EVENTLESS (extends D-P0.6/D-W7.1);
  nonexistent PATH refuses (typo protection); `sync --export-to`
  regenerates the local mirror first in both modes — dry-run purity
  protects the destination only.
  (i) *Shared rules extraction.* The note-recognizer, hidden-entry rule,
  and wikilink regex moved from doctor privates to public
  `obsidian.recognized_note_rel` / `obsidian.is_hidden_rel` /
  `obsidian.WIKILINK_RE` (doctor keeps thin aliases), so doctor and the
  export consume one definition of "a file sync generates".

# DECISIONS — Agentic OS v0.2 U-C3 secret warn-on-write run

This section continues the `D-v0.2.*` series for the U-C3 pass executed per
`agentic-os-v0.2-u-c3-secret-safety-contract.md` on branch
`v0.2-u-c3-secret-safety` (2026-07-12). D-v0.2.15 remains the behavioral
decision; this section records only the implementation policies the build
surfaced. Prepended per the established precedent (D-W0.4, reaffirmed in
D-v0.2.7); everything below stays byte-identical.

## D-v0.2 decisions (U-C3)

- **D-v0.2.21 — U-C3 implementation policies.** Baseline gate: branch
  `v0.2-u-c3-secret-safety`, HEAD `410289f`, clean tree, 336 tests OK,
  doctor 17/17 on a fresh workspace. The detector moved verbatim to
  `agentic_os/secretscan.py` (side-effect-free; `pack.scan_secrets` and
  `pack.SECRET_PATTERNS` stay as re-exports because pack was its
  historical home). Policies pinned during implementation:
  (a) *Metadata keys, sparsity, and payload redaction.* An affected
  successful mutation's normal event payload gains `secret_warning`
  (true), `secret_fields` (canonical field labels, input order), and
  `secret_patterns` (detector order, deduplicated) — and never the
  matched value: every event payload passes `secretscan.redact_tree`
  inside `events.emit`, replacing each secret-shaped string leaf (nested
  lists/dicts included) with the one fixed placeholder
  `secretscan.REDACTED_VALUE` — no hash, fingerprint, preview, excerpt,
  or offset. The emit choke point also keeps a previously accepted
  secret-shaped identifier (an agent name on `agent update`, a project
  slug or repo path copied forward) out of every later event, and applies
  the same fixed placeholder to the top-level `events.actor` column: a
  syntactically valid `agent:<name>` evidence provenance can be
  credential-shaped and flows directly into the actor, so no matched
  value may remain anywhere in the event record — payload OR actor —
  while benign actors are stored byte-identical. The canonical domain
  row keeps the accepted value (the ledger stays honest). Redaction is
  the identity on benign strings and the metadata keys are absent on
  unaffected writes, so every pre-U-C3 payload shape AND value stays
  byte-identical. No second event. Scan labels are enforced against the
  fixed `secretscan.TRUSTED_FIELD_LABELS` allowlist; `project add` scans
  the validated slug, display name, and resolved repo path,
  `agent update` re-scans the reused name, and `evidence add` scans ref,
  claim, and the validated provenance — a trusted mirror/export-bearing
  field (rendered in the evidence note, passed as the event actor).
  (b) *Warn after commit.* The stderr WARNING prints only after the
  mutation's transaction commits — a rolled-back write must never warn,
  and a warned write is always a real one. One line per command, fields
  and pattern names only, value never repeated.
  (c) *Override reason included.* `done --no-evidence --reason` stores the
  reason verbatim in the `done_override` payload, so the reason is scanned
  and that payload (the one carrying the text) gets the safe metadata —
  the minimum-coverage list did not name it, but an unscanned journaled
  free-text field would be a hole in the sweep.
  (d) *Doctor sweep shape.* One warn-only check (#18) scans the canonical
  text columns of projects/tasks/runs/decisions/evidence/handoffs/memory/
  agents — including `slug`, `repo_path`, `conventions_md`,
  `invoke_hint`, evidence `provenance`, and the task `assignee` and
  `branch_hint` columns (rendered task frontmatter and pack REPO & BRANCH
  content), which have no CLI write path yet or arrive validated but are
  pack/mirror-bearing. Legacy raw `events.actor` values are raw-scanned
  with the shared detector and reported as `event #id` under the fixed
  safe label `actor` with canonical pattern names only; post-U-C3 events
  never hold a matched actor (emit redacts it), so their visibility comes
  from the safe metadata. Event payloads are covered two ways: doctor
  reads well-formed U-C3 metadata (`secret_warning` is `true` plus
  list-typed `secret_fields`/`secret_patterns`) so redacted historical
  events stay visible, accepting field names only from
  `secretscan.TRUSTED_FIELD_LABELS` and pattern names only from
  `secretscan.PATTERN_NAMES` — malformed or tampered metadata is ignored,
  never echoed — and still raw-scans every legacy payload string value,
  each string individually so a JSON key (`key`, `token_estimate`) can
  never lend keyword context to a neighboring value. A payload key is
  echoed as a finding label only when it looks like one of our snake_case
  keys and is itself negative under the detector; anything else reports
  as `payload`. Findings name entity + public ID (or `event #id`) + field
  + pattern names; distinct findings are deduplicated deterministically
  in first-seen order and display is bounded to 10 findings plus a
  `(+N more)` count. Projects and agents are identified by ROW id
  (`project #1`, `agent #1`), never slug or name: those fields are
  themselves scanned, and a secret-shaped one must not be echoed as the
  identifier of another field's finding. Domain hits normally also appear
  as event-metadata hits (the add event marks the same fields): accepted
  as honest double visibility, not deduplicated across sources. Doctor's
  exit semantics are unchanged.
  (e) *Value-echo policy scope.* Canonical domain rows retain accepted
  trusted-human values, and ordinary user-requested ledger readbacks
  (`task list`/`show`, `log`, `--json` documents) and the generated
  mirror may reflect them. Warnings, event payloads, the event actor
  column, doctor findings, U-C3 refusal/exception text, and this unit's
  test failure diagnostics never echo a matched value. Context packs and
  untrusted dropfile ingest
  keep their atomic hard refusals. This is a targeted no-echo rule at the
  listed surfaces, not general output redaction.

# DECISIONS — Agentic OS v0.2 release-readiness audit

This section records the 2026-07-11 continuation audit across the public
`agentic-os` control plane and private `ai-company-runtime` execution plane.
It prepends new decisions without changing the historical sections below.

## D-v0.2 decisions (release readiness)

- **D-v0.2.14 — Two repositories, one artifact boundary.** `agentic-os`
  remains the local governance/memory ledger (SQLite); `ai-company-runtime`
  remains the operational execution plane (Postgres). They will not share or
  synchronize tables. Future integration uses a versioned result envelope
  carrying AOS/runtime task references, evidence hashes, and trace/correlation/
  causation ids. This prevents two mutable sources of truth while preserving
  end-to-end auditability.
- **D-v0.2.15 — Warn-on-write secret posture (U-C3).** U-C3 preserves
  the existing hard refusals for pack construction and untrusted dropfile
  ingest. Trusted human CLI writes to mirror-bearing project/task/run/decision/
  evidence/handoff/memory/agent fields remain non-blocking; an affected
  successful mutation will print a warning and store pattern/field names only
  in its normal event. Doctor will report identifiers and safe metadata only,
  never matching values. Rationale: do not silently falsify the append-only
  record, but make exposure visible and actionable.
- **D-v0.2.16 — Success claims require proof (approved later U-H2
  unit).** A separate U-H2 contract will require a dropfile declaring
  `outcome: success` to carry evidence or be refused atomically. Direct run
  endings will remain available for honest/manual recovery, while doctor will
  warn when a successful run has no evidence created inside its run window.
  This behavior is not part of the U-C2 baseline or the U-C3 implementation.
- **D-v0.2.17 — Distribution boundary approved for later U-P1.**
  A separate U-P1 unit may add `pyproject.toml`, an `aos` console script,
  `python -m agentic_os`, build metadata, version `0.2.0`, and a Python 3.12
  floor. None of that packaging behavior is present in the verified U-C2
  baseline or included in U-C3.
- **D-v0.2.18 — GitHub delivery gate approved for later U-P1.**
  A separate delivery unit will add PR/push CI for supported Python versions,
  including unittest, compile, wheel, installed-entrypoint, fresh-init, and
  doctor smoke gates with official actions pinned to immutable full commit
  SHAs. Branch protection and reviewed-PR requirements remain human repository
  settings. No CI implementation is claimed by this audit.
- **D-v0.2.19 — Blueprint authority without roadmap erasure.** The canonical
  near-term sequence remains the user's existing plan: U-C1 input hardening →
  U-C2 backup/verify/restore → U-C3 secret warn-on-write + doctor sweep → U-C4
  Windows Obsidian export → U-H1 SessionEnd dropfile hook + trust-gated
  installer. U-C1 and U-C2 are complete, so U-C3 is next. The broader
  `AGENTIC_OS_BLUEPRINT.md` extends that spine with cross-repository architecture
  and later milestones; it does not supersede, reorder, or erase it. Older
  research and two-week documents remain evidence/history, while newer explicit
  decisions may amend individual items without silently rewriting the sequence.
- **D-v0.2.20 — Proof and identifier hardening approved for a later
  bounded unit.** A separate contract may enforce priority 1–5, non-blank
  optional task text, non-blank evidence refs/claims, safe agent-name grammar,
  non-blank run summaries, and post-collapse dropfile evidence validation.
  These changes are not present in the verified U-C2 baseline and are excluded
  from U-C3.

# DECISIONS — Agentic OS v0.2 U-C2 backup/verify/restore run

This section continues the `D-v0.2.*` series for the U-C2 pass executed per
`agentic-os-v0.2-u-c2-backup-restore-contract.md` on branch
`v0.2-u-c2-backup-restore` (2026-07-08). That contract wins over the
two-week plan and the v2 research report where they differ. Prepended above
the earlier sections per the established precedent (D-W0.4, reaffirmed in
D-v0.2.7); everything below stays byte-identical.

## D-v0.2 decisions (U-C2)

- **D-v0.2.8 — U-C2 baseline gate results.** Branch
  `v0.2-u-c2-backup-restore`; HEAD `1ed30a3` ("docs: add v0.2 U-C2 backup
  restore contract"). Working tree clean. Python 3.12.3. Baseline suite:
  **300 tests, OK**; doctor: **17/17 PASS** (incl. the warn-only check).
  `CLAUDE.md` in the contract's read-first list still does not exist —
  recorded, nothing to read. Behavior pinned by prototype before writing
  code: a single flipped bit in a backup copy passes
  `PRAGMA integrity_check` (SQLite pages carry no checksums) but fails a
  sha256; a zeroed page or truncation makes `integrity_check` *raise*
  `sqlite3.DatabaseError` rather than return a row; and a plain read-only
  open of a WAL-marked backup file creates `-shm`/`-wal` droppings beside
  it, which `immutable=1` prevents. These three facts shaped U-C2.2–U-C2.3.
- **D-v0.2.9 — Backup format and location (U-C2.1).** `backup create`
  writes `backups/aos-backup-<UTCSTAMP>Z.db` inside the workspace via the
  sqlite3 backup API (`conn.backup`, the D-W7.2 rule — never a raw copy of
  a live WAL database), then a sibling manifest, then emits one
  `system/backup_create` event carrying the sha256/size/paths — event
  after files, so a backup never contains its own event (the `snapshot`
  precedent). Name collisions bump `-2, -3, …` pair-aware (a lone stale
  manifest also blocks its stem). The `backups/` folder is created lazily
  on first use and deliberately NOT added to the required workspace layout
  (`obsidian.WORKSPACE_DIRS`) — adding it would fail doctor's
  required-folders check on every existing workspace, breaking Night-1
  back-compat for a folder most workspaces won't have yet. `create`
  refuses (exit 1, before any write) when the live database fails
  `PRAGMA integrity_check`: a nightly `backup create` must be a health
  check, not a machine for archiving corruption. No `--output` override
  and no retention policy in v0.2 (noted as limitations; RECOVERY.md tells
  humans to copy the pair off-machine).
- **D-v0.2.10 — Manifest fields (U-C2.2).** Sibling file
  `<stem>.manifest.json` (the pair moves together; verify refuses a lone
  backup): `aos_backup_manifest` (format version, `1`), `created_at`
  (UTC-Z, single clock), `source_db_path`, `schema_version` (read from the
  source meta table), `size_bytes`, `sha256` (of the backup db file), and
  `tool` (`agentic-os <version> (aos.py backup create)` — the contract's
  "where practical" label). JSON via the canonical `utils.json_dumps` +
  `write_text_lf` (LF-only guarantee). Unknown extra keys are tolerated on
  read (forward compat); an unknown `aos_backup_manifest` value is refused.
  Field types are validated on verify (sha256 must be 64 lowercase hex —
  `\Z`-anchored per D-v0.2.3; `size_bytes` a non-negative non-bool int).
- **D-v0.2.11 — Verify semantics (U-C2.3).** `backup verify PATH` runs
  eight ordered checks and stops at the first failure (each later check
  assumes the earlier ones): file exists · manifest exists · manifest
  well-formed · size matches · sha256 matches · opens as SQLite ·
  schema_version supported (backup ↔ manifest ↔ build) ·
  `PRAGMA integrity_check` passes (its `DatabaseError` raise is caught and
  reported as the check's failure). Output is doctor-style `[PASS]`/
  `[FAIL]` lines, exit 1 + a one-line stderr verdict on failure. Both hash
  and structure checks are load-bearing per D-v0.2.8, and each has a test
  the other cannot pass (bit-flip vs zeroed-page-with-regenerated-
  manifest). Verify (and restore) deliberately never open the live ledger
  and are eventless (extends D-P0.6): recovery tooling must work exactly
  when the workspace is damaged or absent, so unlike every other
  later-phase command they do not go through `_ledger` and work pre-init
  (a deliberate, journaled exception to the D-P2.4 pattern). The backup is
  opened `mode=ro&immutable=1` with a percent-encoded URI (`%`, `#`,
  spaces in paths covered by test), so verifying cannot write anything —
  pinned by a directory-snapshot test.
- **D-v0.2.12 — Restore overwrite policy (U-C2.4).** `backup restore PATH
  --to NEW_DB_PATH` targets a database file path (restore-into-a-fresh-root
  is documented in RECOVERY.md as db-restore + the drill, since a db alone
  is not a workspace). It verifies the backup first (a corrupt backup
  refuses before any write, naming the failed check), creates the target
  with `open(..., "xb")` — an atomic, TOCTOU-free refusal of any existing
  file/directory including the live `aos.db`, with **no overwrite flag by
  design** (the contract's preferred v0.2 behavior; pinned by a test that
  `--force`/`--overwrite` are unrecognized) — streams the copy with an
  in-flight sha256, and on any post-copy mismatch removes the partial file.
  A byte copy is correct here (unlike create) because the source is a cold
  verified file, and it makes the restored file provably bit-identical to
  the manifest. Adopting the restored db as the live ledger is the human's
  manual `mv`, mirroring human-controlled git; RECOVERY.md's drill has the
  human move the damaged db (and its `-wal`/`-shm`) aside first.
- **D-v0.2.13 — Adversarial review round.** Before final validation, a
  five-lens review (correctness, contract compliance, test integrity, docs
  accuracy, adversarial bypass) with two independent refuters per finding
  ran over the diff. Confirmed and fixed: a mid-copy `OSError` during
  restore left a partial target file that blocked its own retry with a
  misleading overwrite refusal and leaked as exit 2 (now unlinked +
  refused as a one-line exit-1 error, pinned failing-then-passing); this
  run's first DECISIONS.md edit deleted the U-C1 section's H1 heading —
  not a pure prepend (restored; `git diff` now shows zero deleted lines);
  no test could distinguish backup-API creation from a raw live-file copy
  — a `shutil.copyfile` mutant survived all 333 tests (now killed by a
  WAL-discriminator test: `wal_autocheckpoint=0`, committed marker row
  living only in `-wal`, raw main-file copy proven blind to it, backup
  proven to contain it); verify's supported-by-this-build schema branch
  was unexercised — deleting it survived the suite (now killed by a test
  where backup db and manifest AGREE on schema `999`); RECOVERY.md
  overstated the exit-1 refusal of `backup create` on corruption (gross
  corruption dies in the workspace open with a database error before the
  guard — reworded). Also hardened from technically-true-but-refuted
  findings: manifest format check is now type-strict (JSON `true`/`1.0`
  no longer pass as format 1 via Python's `True == 1`; pinned by tests)
  and RECOVERY.md's inspection step no longer assumes a `sqlite3` CLI
  this machine doesn't have (stdlib `python3 -c` one-liner). Refuted, no
  change (recorded as known limitations): a write-locked live db makes
  `backup create` exit 2 after writing a valid-but-unjournaled backup
  pair (busy_timeout makes this a >5s-contention corner; the pair is
  harmless and verifiable); empty `--to` resolves to cwd and refuses with
  a literal-but-safe message; verify blesses any structurally-valid
  schema-1 SQLite file with a consistent manifest (verify proves
  integrity and provenance-by-hash, not ledger-shape — matches the
  contract's check list exactly).

# DECISIONS — Agentic OS v0.2 U-C1 input-hardening run

This section (`D-v0.2.*`) journals the U-C1 pass executed per
`agentic-os-v0.2-u-c1-hardening-contract.md` on branch
`v0.2-u-c1-input-hardening` (2026-07-08). That contract wins over the
two-week plan and the v2 research report where they differ. Prepended above
the earlier sections per the established precedent (D-W0.4); everything
below stays byte-identical.

## D-v0.2 decisions

- **D-v0.2.1 — P0 baseline gate results.** Branch
  `v0.2-u-c1-input-hardening`; HEAD `5dc5971` ("docs: add v0.2 U-C1
  hardening contract"). Working tree clean (ignored: `.agentic-os/`,
  `__pycache__/`). Python 3.12.3. Baseline suite: **256 tests, OK**;
  doctor: **17/17 PASS** (incl. the warn-only check). The contract's
  read-first list names `CLAUDE.md`, which does not exist in this repo —
  recorded here, nothing to read. Pre-fix defects reproduced live before
  any edit: `T-0000` reached the DB lookup; a 32-digit id exited 2
  (`OverflowError` on the SQLite bind, W-1); a 5000-digit id exited 2
  (CPython int-conversion limit — a failure mode the research report did
  not list); `project add $'proj\n'` succeeded, writing a newline-bearing
  slug (W-2's INFERRED exploit, now CONFIRMED end-to-end).
- **D-v0.2.2 — ID maximum (U-C1.1).** `ids.MAX_ID = 2**63 - 1`, the SQLite
  INTEGER (signed 64-bit) bound already used by the dropfile parser — no
  row can ever carry a bigger rowid, so anything above it is refused
  *before* any DB lookup, as are zero-equivalent ids (`T-0`, `T-0000`, …;
  ids start at 1). Magnitude is judged after stripping leading zeros, so
  zero-padding stays legal (as it always was) at any length; a digit-length
  pre-check on the stripped digits (`> 19` refuses without converting)
  keeps CPython's ~4300-digit int-conversion limit unreachable. The
  over-maximum message does not echo the oversized input back. Round-trip
  behavior for all real ids (1…MAX_ID) is unchanged.
- **D-v0.2.3 — Strict validator anchors (U-C1.2).** Every regex that
  validates user/filesystem input now anchors with `\Z`, never `$` (which
  admits a trailing newline): `ids._ID_RE`, `models.SLUG_RE`,
  `models.PROVENANCE_RE`, `utils._DATE_RE`, `ingest._TASK_RE`,
  `ingest._AGENT_RE`, all nine `doctor._NOTE_PATTERNS`, and
  `render._PLAIN_SAFE` (with `$`, a trailing-newline value was written
  *plain* into note frontmatter — mirror corruption, found during this
  run's audit; `models.AGENT_NAME_RE` already used `\Z`). Audited and
  deliberately left on `$`: per-line parsers whose input is split on
  newlines first and so cannot contain one (`ingest._EVIDENCE_BULLET_RE`,
  `doctor._FRONTMATTER_LINE`) and `pack._HEX_ONLY` (input pre-filtered to
  `[A-Za-z0-9+/=]` runs) — behaviorally identical there, and the diff
  stays surgical. `parse_id` still strips *surrounding* whitespace by
  design (pinned by an existing test); `\Z` guards the match itself.
- **D-v0.2.4 — Run-start lifecycle policy (U-C1.3).** `run start` requires
  task status `ready`, consuming the legal `ready→in_progress` transition;
  `inbox` (untriaged), `in_progress` (already running), and `done` tasks
  refuse (done keeps its specific closed-task message). The refusal names
  the fix (`task status T-XXXX ready`) and writes no rows and no events.
  Two existing tests used the closed loophole as *setup* and were re-routed
  without weakening their assertions: the projectless-in_progress assign
  test now forces the legacy state via raw SQL (this class's established
  pattern for unreachable states), and the multiple-open-runs ingest test
  reaches two open runs via the legal ladder (start → status ready →
  start). A projectless run-start is now impossible via the CLI (ready
  implies a project); the ops-layer degradation note for legacy projectless
  rows remains.
- **D-v0.2.5 — no-evidence reason policy (U-C1.4).** `done --no-evidence`
  without `--reason TEXT` (or with a blank reason) refuses; with a reason
  it closes and journals the text in the `done_override` event payload as
  `{"task", "reason": TEXT, "via": "--no-evidence"}` (formerly the payload
  carried the constant `"reason": "--no-evidence"`; no test pinned it).
  `--reason` without `--no-evidence` is flag misuse and refuses, and so is
  `--no-evidence` on a task that turns out to have evidence (previously the
  flag was silently ignored and the reason silently discarded; now the
  refusal names the plain `done` command to run instead). Evidence-gated
  done is byte-for-byte unchanged. Four existing test call sites that
  passed the bare flag gained a reason argument; their assertions are
  untouched.
- **D-v0.2.6 — Dropfile ingest caps (U-C1.5).** `MAX_DROPFILE_BYTES` = 1
  MiB (checked via `stat` before the file is read, then re-checked on the
  bytes actually read — the writer is an untrusted agent process that may
  still be appending between stat and read), `MAX_EVIDENCE_ROWS` = 200,
  `MAX_QUESTIONS` = 100 (checked during parsing, naming the first line
  beyond the cap) — the research report §10 values. Refusals exit 1 before
  the write transaction opens, so no partial rows ever land, and a refused
  file records no ingest event (dedupe behavior intact). Boundary behavior
  pinned: exactly-at-cap ingests. The parser's task-id bound now also
  refuses `T-0000` and applies the D-v0.2.2 magnitude rule (leading zeros
  stripped, digit-length checked before `int()`), reusing `ids.MAX_ID` and
  keeping the pinned "task id out of range" message.
- **D-v0.2.7 — Adversarial review round.** Before final validation, a
  four-lens review (correctness, contract compliance, test integrity,
  remaining bypasses) with two independent refuters per finding ran over
  the diff. Confirmed-and-fixed: `--no-evidence` with existing evidence
  silently discarded the reason (now refuses, D-v0.2.5); byte cap was
  stat-only (now re-checked on read, D-v0.2.6); zero-padded >19-digit ids
  refused with a wrong message (now magnitude-based, D-v0.2.2); D-v0.2.x
  code-comment cross-references were off by one (renumbered); two anchor
  tests didn't discriminate pre/post fix (regex-level assertions added);
  ingest no-partial-write assertions now also count the tasks and
  decisions tables the contract names. Refuted (no change): DECISIONS.md
  prepend-not-append (follows the file's own D-W0.4 precedent; old
  sections byte-identical), and a claimed second open run on T-0005
  (factually false — R-0003 was ended before R-0004 started).

# DECISIONS — Agentic OS complete-today BUILD run

This section (`D-C.*`) journals the build pass executed per
`agentic-os-complete-today-build-prompt.md` on branch `two-week-scope`
(2026-07-07). That contract WINS over the two-week plan where they differ;
the plan stays detail authority elsewhere. Prepended above the planning
section per the established precedent (D-W0.4); everything below stays
byte-identical.

## D-C decisions

- **D-C.1 — P0 baseline gate results.** Branch `two-week-scope`; HEAD
  `114c882` ("docs: add complete-today build contract"), a descendant of
  `85d3793`. Working tree clean; the only ignored entry is `.agentic-os/`
  (runtime state). No `*Zone.Identifier` junk existed (nothing to delete).
  Python 3.12.3. Baseline suite: **162 tests, OK** (matches the expected
  162+). Dogfood loop opened in this repo's ledger before any edit:
  task **T-0003** ("Complete-today build", kind code, project agentic-os),
  run **R-0002** (agent claude-code) — actual IDs, not assumed.
- **D-C.2 — Contract-over-plan reconciliations (the contract wins).**
  (1) `task assign` may MOVE a non-done task between projects (plan §3.1
  refused moves). (2) `task assign` does NOT auto-promote `inbox→ready`
  (plan A1 promoted): the contract's own smoke test runs `task status
  T-0001 ready` immediately after assign — auto-promotion would make that
  a `ready→ready` illegal transition and fail the smoke. Status changes
  belong exclusively to `task status`. (3) `task edit` priority range is
  1–5 (plan said 0–9). (4) Dropfile dedupe: sha256 recorded in the ingest
  EVENT payload and duplicates REFUSED with exit 1 (plan: meta-key +
  no-op exit 0). (5) Dropfile runs ladder: exactly one open run for the
  task+agent is ended with the dropfile outcome (plan/D-0003: never
  auto-end — superseded by this contract's pinned ladder). (6) P3 is a NEW
  command `evidence git T-# COMMIT [--repo] [--claim]`; `evidence add
  --kind commit` keeps its Night-1 store-as-is behavior (plan B2 wanted
  validation inside `evidence add`). (7) Agent kinds are
  `local|cloud|human|generic` with repeatable `--capability` and generated
  `AOS/Agents/<name>.md` notes (plan C1: `cli|api|ide|other`, CSV flag, no
  vault notes). (8) `review weekly` ships (the plan deferred it).
- **D-C.3 — `task assign` semantics.** Same-project re-assign is a no-op:
  exit 0, prints a note, no event (mirrors `project add` idempotency,
  D-P0.12). Done tasks refuse (terminal). Event `(task, assign)` payload:
  {task, project, from_project} — from_project is null for a first assign.
- **D-C.4 — `task edit` details.** Editable set is closed: title, kind,
  priority, accept, spec. `task add --spec` included (plan A2 bundles it
  into the same item; no contract conflict — the `add` event payload is
  unchanged). Event payload lists the changed field NAMES only, in the
  fixed order title/kind/priority/accept/spec; "changed" means "provided"
  (values are not compared — the ledger journals intent, values live in
  the row). Empty values refuse: clearing a field is out of scope.
- **D-C.5 — `task status` refusal precedence.** (1) target `done` → points
  at `python aos.py done X` (the evidence gate is sacred), (2) source is
  done → frozen, (3) transition legality (legal set named), (4) projectless
  `inbox→ready` → "assign a project first" naming `task assign`.
- **D-C.6 — `task list` filters.** `--kind` (validated) and
  `--missing-evidence` (zero evidence rows, any status, composable with
  `--status`/`--project`). `--assignee` skipped per the contract's "unless
  trivially supported": `tasks.assignee` is write-never, so the filter
  would be dead surface over an always-NULL column.
- **D-C.7 — Dropfile parser strictness.** Exact `# AOS DROPFILE` header;
  `task:`/`agent:`/`outcome:`/`summary:` in that order; both `## evidence`
  and `## open questions` headings required (each may have zero bullets);
  blank lines are skipped between elements; CRLF files are normalized for
  parsing (the dedupe hash is over the RAW bytes); a bare CR inside a value
  splits the line and is refused (injection defense, D-W9.1 lineage); every
  stored value is one-line-collapsed. Malformed errors name the line
  NUMBER, never the content — a bad line could be exactly the secret-shaped
  text the scanner keeps off stderr.
- **D-C.8 — Dropfile evidence never touches the filesystem.** `kind: file`
  rows from a dropfile store sha256 NULL: an untrusted path is never
  opened, unlike CLI `evidence add --kind file` which hashes a file the
  human named. Deliberate asymmetry, journaled here.
- **D-C.9 — Dropfile event grain.** All rows in ONE transaction: per-row
  `(evidence, add)` events, the ladder's `(run, end)` when it fires, the
  open-questions `(handoff, create)`, then one `(system, dropfile_ingest)`
  sealing event carrying {file, sha256, task, agent, outcome, one-lined
  truncated summary, evidence ids, run_ended, open_runs, handoff}. Actor
  for every one of them is `agent:<name>` (the provenance-actor rule
  extended). An empty open-questions list creates no handoff. Ingest is
  allowed on done tasks — evidence-after-close matches `evidence add`.
- **D-C.10 — `evidence git` details.** Repo defaults to the task's project
  repo; `--repo` overrides; projectless without `--repo` refuses. Refs
  starting with '-' refuse before git runs (option-smuggling guard).
  Read-only queries only (`rev-parse --is-inside-work-tree`, `rev-parse
  --verify <ref>^{commit}`, `show -s --format=%s`, `show --stat
  --format=`), list-form args, 5 s timeout, graceful exit 1 on missing
  git/non-repo/unknown commit/timeout. Full sha stored as ref; claim
  defaults to the commit subject; subject/diffstat captured best-effort
  (truncated to 200 chars) into the event payload via the existing
  `add_evidence` path (optional extra_payload). Tests use temp git repos —
  the contract's P3 gate explicitly authorizes this, superseding D-P4.1
  for this command only. `evidence git` is NOT in the central event-sweep
  seal (keeping that test git-independent); its event is proven in its own
  test class.
- **D-C.11 — Agent registry semantics.** Default kind `generic`. Names
  validated against `^[A-Za-z0-9][A-Za-z0-9._-]*$` — the `agent:<name>`
  provenance charset plus a leading alnum so names are safe, stable note
  filenames (no hidden files, no path tricks). Capabilities stored as a
  JSON array in the existing `capabilities_json` column (`[]` when none);
  `agent update --capability` REPLACES the whole list. No `--trust-level`
  and no `--invoke-hint` surface anywhere: trust stays 0 (autonomy is
  earned via the ladder, never set by hand).
- **D-C.12 — Review engine decisions.** The four new sections land AFTER
  `## Recent runs` (the plan's D1 placement — an existing test pins the
  earlier content slices). "Stale in-progress" = `in_progress` AND (no
  open run OR no run started/ended inside the recent window), reasons
  joined. "Memory needing refresh" = LIVE rows (not superseded, not
  retired at the review date) not updated for 30 days — the D-W6.2 quirk
  (superseded rows in "Stale memory") is deliberately preserved there
  under its regression pin and fixed only in the new section. `review
  weekly` = ISO week Mon–Sun containing `--date`, filename `YYYY-Www.md`,
  windows span the week, point-in-time sections as of the week's end.
  `review project` = `Reviews/project-<slug>.md`, every section filtered
  to the project (global-scope memory excluded — not project-tied); takes
  the same optional `--date` as `build` (determinism for tests; the
  contract names `--date` only for weekly, adding it to project is a
  strict superset). All three builds share one engine and the byte-exact
  `## Notes` splice; all are eventless (D-P0.6/D-W6.1 lineage).
- **D-C.13 — Index notes.** Exactly the seven the contract lists (Tasks,
  Decisions, Evidence, Handoffs, Memory, Agents, Reviews) as top-level
  `AOS/<Name>.md` notes — stable wikilink stems, no frontmatter (like
  Home). Projects/Runs have no index (not in the contract's list). The
  Reviews index derives from the `Reviews/` directory listing — reviews
  live on disk, not in the DB — which keeps sync deterministic and
  idempotent for a given workspace state. Memory index shows superseded/
  valid_until as stored facts, never computed liveness (no clock in the
  mirror). Doctor's containment allowlist gains the seven filenames.
- **D-C.14 — Doctor pins moved 12 → 17 (D-W8.1 pattern, both sites).**
  Four new checks (agent rows well-formed · dropfile ingest events carry
  their sha256 · entity-note frontmatter parses · PRAGMA integrity_check)
  plus one WARN-ONLY line (code tasks done without commit evidence) that
  prints `[WARN]` and never affects the exit code. The weekend pin test
  was renamed `..._passes_all_checks` with the move documented inline; no
  assertion was weakened — the all-green requirement now also accepts the
  expected `[WARN]` line, which the Night-1 fixture legitimately triggers
  (its code task closed with note evidence). The frontmatter check covers
  the eight entity folders only (Reviews/Home/CONVENTIONS/index notes have
  no frontmatter by design); non-UTF-8 stays check 5's finding. No
  deliberate-corruption test for integrity_check: flipping page bytes
  deterministically without also breaking `open_db`'s meta read is not
  reliable across SQLite builds — the check's clean pass is pinned and its
  failure path is a one-line comparison. Every other new check has a
  corruption test asserting exactly one failure.
- **D-C.15 — Adversarial review pass (D-P7.3/D-W9.1 practice continued).**
  Seven independent dimension reviewers (hard constraints · P1 lifecycle ·
  P2 dropfile-as-adversary · P3+P4 · P5+P6 · P7+weakened-test scan · deep
  correctness) reviewed the full working diff; every finding was then
  attacked by three separate refutation agents (correctness / reproduce-it
  / spec-reading lenses, majority rules). Result: 3 findings, 3 confirmed
  (each reproduced live by all three verifiers), 0 refuted. Fixed with
  regression tests: (1) `AGENT_NAME_RE` anchored with `$`, which matches
  before a string-final newline — `agent add $'codex\n'` passed validation
  and wrote an unrecoverable `Agents/codex\n.md` mirror note; fixed with
  `\Z` (doctor check 13 shares the regex and is fixed with it), test pins
  the trailing-newline refusal. (2) `_run_git` decoded git output as
  strict UTF-8, so a commit subject re-encoded via i18n.logOutputEncoding
  crashed `evidence git` with exit 2 on a perfectly valid commit; fixed
  with errors='replace' (graceful degradation), test commits a non-ASCII
  subject under latin1 output encoding. (3) a dropfile task id above
  SQLite's INTEGER bound slipped past `_TASK_RE` into an OverflowError
  exit 2 — untrusted input reaching the internal-error path; fixed with a
  range check in the parser ("task id out of range", exit 1), test pins
  it. The same overflow via CLI-typed ids (e.g. `task show T-<25 nines>`)
  predates this build and is recorded as a known limitation, not churned
  here.
- **D-C.16 — Final gate results.** Recorded after the FINAL VERIFICATION
  GATE: suite 162 → 256 (all green; 254 at the P7 gate + 2 new regression
  tests and 1 extended refusal matrix from the adversarial review pass),
  smoke green including the deliberate duplicate
  refusal, repo doctor clean, nothing staged/committed/pushed. Dogfood
  loop closed: evidence attached to T-0003, run R-0002 ended success,
  T-0003 done, sync + doctor clean. Exact outputs live in the FINAL
  REPORT.

# DECISIONS — Agentic OS two-week scope PLANNING run

This section (`D-2W-P.*`) journals the planning pass executed per
`agentic-os-two-week-scope-prompt.md` on branch `two-week-scope` (2026-07-07).
It is a planning journal only — no source or tests were touched; the build
journal for the implementation phase (`D-2W-A.*` etc.) comes later, under its
own contract. Prepended above the Weekend section per that section's own
precedent (D-W0.4); everything below stays byte-identical.

## D-2W-P decisions

- **D-2W-P.1 — Baseline gate results.** Branch `two-week-scope`; HEAD `01ee04a`
  ("docs: add two-week scope planning contract"), a descendant of `85d3793`
  (= tag `milestone/weekend-mvp`; `milestone/night-1` = `59da161`, both
  verified via `git show-ref`). Working tree clean, nothing staged, no
  untracked files (the contract was pre-committed). No `*Zone.Identifier`
  junk files existed (nothing to delete). Python 3.12.3. Baseline suite:
  **162 tests, OK** (expected 162). `.agentic-os/` did not exist at start;
  it was created during this run exclusively via the aos CLI (dogfood
  bootstrap mandated by the contract).
- **D-2W-P.2 — Weekend final report handled as absent.** No
  `docs/reports/weekend-final-report.md` (or any report file) exists in the
  repo. Per the contract, the Weekend "Known limitations" and "Deferred
  features" lists were reconstructed ONLY from README.md ("Status" section)
  and this file's D-W/D-P entries; no conversation record was assumed. The
  plan states this explicitly (plan §2.1).
- **D-2W-P.3 — Reconciliation verdicts.** The two-week phase is re-anchored
  to Weekend debt (§11 MVP-stage items the Weekend build deferred: dropfile
  ingest F-C7, git evidence ingest F-G1, agent registry F-C8) plus task
  lifecycle UX (D-P0.21), instead of research §11's 2-week list (ledger
  decision D-0001). All ten §12 un-defer triggers were checked: none has
  fired; all ten deferrals stand. The §11-vs-§12 conflict on F-B10 (listed in
  the 2-week stage AND deferred with a trigger) is resolved in §12's favor —
  the trigger ("one-way mirror proven idempotent for 2+ weeks of daily use")
  is unfired. Counts: 13 planned items, all traced; of the 11 §11 2-week
  items, 9 dropped with reasons + triggers, 2 adapted (F-E10 → goldens,
  F-G5 → soft warning + review section, because a hard refusal would break
  the Night-1 back-compat fixture).
- **D-2W-P.4 — Capacity model.** 17.5 h of core items + 1 h final gate =
  18.5 h planned against the contract's 20–25 h budget; slack stated per
  endpoint (7.5% / 18% / 26%); ordered 9 h stretch pool intentionally exceeds
  maximum slack (tail lands only on under-run). Cut line if capacity halves:
  task assign/edit/status + dropfile ingest (10.5 h); everything else falls
  out, D first, then C, then B2.
- **D-2W-P.5 — Dogfood loop record and friction.** Fresh workspace: `init`,
  `project add agentic-os`, task **T-0001** ("Two-week scope plan", kind
  research), pack `packs/T-0001-claude-code.md`, run **R-0001**, scoping
  decisions **D-0001..D-0003** via `decision add`, evidence **E-0001** (this
  plan file, kind file) attached at close, run ended success, T-0001 done,
  sync + doctor clean. **T-0002** (`in` capture noting the dropfile dead-end)
  is deliberately left open and projectless: it is live evidence for Phase A
  (no command can assign or triage it — D-P0.21 verified against the current
  CLI). Friction harvested into the plan (§2.6): stranded inbox capture; no
  `--spec` flag anywhere; dropfile fallback advertised by every pack with no
  reader; research-kind pack suggesting `--kind test` evidence and a branch
  convention; `in` defaulting captures to kind=code.
- **D-2W-P.6 — Adversarial verification of the plan.** Four independent
  reviewers (contract compliance · fact-check against evidence files and
  code · implementation feasibility against the mapped tests/pins · internal
  consistency), each instructed to refute the draft. 19 findings; all
  addressed. The two blockers were sequencing gaps this journal and the
  closed dogfood loop now resolve (D-2W-P entries cited before being written;
  evidence cited before being attached). Substantive fixes adopted: A1 gains
  a done-guard (assign could otherwise reopen a closed projectless task); the
  A1/A3 projectless-ready ordering trap is pinned; B2's acceptance criterion
  was untestable as written (D-P4.1 forbids git repos in tests) → mocked-
  boundary strategy with manual final-gate verification (D-P7.2b pattern);
  dropfile dedupe meta-key distinguished from the D-W5.1 eventless precedent
  (written in-transaction); dropfile event payload carries outcome/one-lined
  summary; agent names validated against the provenance charset; D1 sections
  placed after `## Recent runs` to respect a pinned content slice; stretch
  arithmetic, trigger-wording ("in substance", not verbatim), F-C7 scope
  ("ingest half"), and test-count projections corrected. Final self-scores
  all ≥ 8 (plan, end).

# DECISIONS — Agentic OS Weekend MVP build

This section (`D-W*`) records every simplification, interpretation, and
deviation made while executing `agentic-os-weekend-mvp-build-prompt.md` (the
Weekend contract) on branch `weekend-mvp`. The contract asks for the Weekend
plan "up front", so this section sits above the Night-1 journal; nothing below
the Night-1 heading is ever rewritten (append-only holds at the entry level).
Format: `D-W<phase>.<n>`.

## Weekend plan (D-W0) — mapped to phase gates

- [ ] **P0** Baseline gate (branch/HEAD/tree/python/suite) + this plan.
- [ ] **P1** Global `--root` + discovery pinned by test first + Night-1-shaped
      workspace fixture (init → project → task → pack → run → evidence → done
      → sync) that later phases reuse for back-compat proofs.
- [ ] **P2** `decision add` ops + CLI (+ task show / pack DECISIONS / sync
      already wired in Night-1 — proven by tests, not rebuilt).
- [ ] **P3** `handoff create|accept` ops + CLI (+ pack PRIOR RUNS & HANDOFF
      STATE / task show / sync proofs; double-accept exit 1).
- [ ] **P4** `memory add|list|retire` (+ `--supersedes`) + M- prefix in ids.py
      + pack MEMORY live-only inclusion rule + Memory notes in sync.
- [ ] **P5** `search` (FTS5 detect at runtime, LIKE fallback force-tested,
      watermark rebuild from source tables, `--json`).
- [ ] **P6** `review build` (+ `## Notes` byte-for-byte preservation +
      idempotency; eventless).
- [ ] **P7** `export events --jsonl` + `snapshot` (backup API, never raw file
      copy; event-only audit record after the file is written).
- [ ] **P8** Doctor hardening (schema_version · status vocabulary ·
      done-evidence/override · handoff/decision/memory/pack referential and
      file checks) + corrupted-workspace failure tests.
- [ ] **P9** README + DECISIONS + full validation + Weekend smoke + FINAL
      GATE + FINAL REPORT.

Rule per gate (unchanged from Night-1): that phase's tests written AND the
full suite green before moving on; test count never shrinks.

## W0 decisions

- **D-W0.1 — Baseline gate results.** Branch `weekend-mvp`; HEAD is exactly
  `59da161` ("feat: add Agentic OS night-1 MVP"); `python3 --version` =
  3.12.3; baseline suite green: **89 tests, OK** (this is the P0 count).
  Working tree: no modified tracked files, nothing staged; the only untracked
  file is the Weekend contract itself
  (`agentic-os-weekend-mvp-build-prompt.md`) — it is this run's input,
  recorded here and left unstaged. A Windows→WSL copy artifact
  (`agentic-os-weekend-mvp-build-prompt.md:Zone.Identifier`) was deleted
  before any check ran. `.agentic-os/` is gitignored and absent from status.
- **D-W0.2 — Research files re-read as data only; refusals renewed.**
  Rejected again (per contract + D-P0.1): pytest (stdlib unittest only),
  PyYAML (stdlib only), any `--allow-secret` override (packs refuse, full
  stop), the research schema's 8-value task status enum (vocabulary stays
  `inbox|ready|in_progress|done`), `generated_at` in pack headers or note
  bodies (no wall-clock in generated files), and contentless FTS tables with
  write triggers (the contract prescribes a derived index with a
  `fts_event_watermark` staleness rebuild instead — triggers would be schema
  surface on core tables).
- **D-W0.3 — New modules.** Weekend code lands in three new cohesive modules
  — `agentic_os/search.py`, `agentic_os/review.py`, `agentic_os/export.py` —
  plus targeted extensions to `ops.py`, `cli.py`, `ids.py`, `models.py`,
  `render.py`, `obsidian.py`, `doctor.py`. The Night-1 module list was that
  contract's scope, not a cap on this one. New tests live in
  `tests/test_weekend_core.py` and `tests/test_weekend_views.py` (plus a
  shared fixture helper); existing test files are only ever extended.
- **D-W0.4 — DECISIONS.md structure.** This Weekend section is prepended
  above the Night-1 journal per the contract's "up front"; every historical
  Night-1 entry below stays byte-identical. New D-W entries append to this
  section as phases complete.

## W1 decisions

- **D-W1.1 — Explicit `--root` never searches.** Global `--root PATH` means
  exactly `PATH/.agentic-os`; there is no upward walk from PATH. Uninitialized
  PATH → exit 1 with a remedy that names the flag
  (`Not initialized at PATH. Run: python aos.py --root PATH init`). Without
  `--root`, discovery is byte-for-byte the Night-1 behavior (cwd-upward walk,
  pinned by TestDiscoveryPinned before the parser was touched).
- **D-W1.2 — Separate argparse dests.** The global option stores to
  `global_root`; `init --root` keeps its own `root` dest. argparse subparsers
  re-apply their own defaults after the main parser runs, so sharing one dest
  would let the subparser's `None` default silently clobber a global value.
  `cmd_init` reconciles the two (differ → exit 1; equal or single → proceed).
- **D-W1.3 — Back-compat harness design.** The fixture builds a
  Night-1-shaped workspace using ONLY Night-1 commands under cwd discovery
  (init → project → task ×2 → pack → run → evidence → done → in → sync),
  then every back-compat test drives it purely via `--root` from an unrelated
  cwd. "No migration / no drift" is proven against `sqlite_master`: the
  CREATE TABLE SQL of all 11 core tables must be identical before and after
  Weekend commands run.
- **D-W1.4 — Gate P1 result.** 101 tests green (89 baseline + 12: discovery
  pins ×4, global-root semantics ×6, Night-1 fixture shape + Night-1 commands
  via --root with schema-drift oracle).

## W2 decisions

- **D-W2.1 — `decision add` semantics.** Status is always `'accepted'`
  (Night-1 schema default; no proposal workflow in Weekend scope);
  `decided_at` comes from the single clock utility. `--task` must belong to
  the `-p` project — a mismatch (including project-less inbox tasks) exits 1,
  keeping `related_decisions`' task/project scoping coherent. Empty title or
  `--decision` text exits 1. One event `(decision, add)` per D-P0.5 with
  payload {decision, title, project, task, status}. Task show, the pack
  DECISIONS section, and `Decisions/D-*.md` sync were already wired in
  Night-1 (D-P0.7); P2 proves them with CLI-created rows instead of
  rebuilding them.
- **D-W2.2 — Gate P2 result.** 109 tests green (task-scoped decision flows
  through task show → pack → synced note with bidirectional wikilinks;
  project-scoped decision appears on all project tasks; event payload;
  unknown project / cross-project task / malformed id / empty text
  refusals; ops-layer atomicity; sequence test and pre-init guard extended).

## W3 decisions

- **D-W3.1 — Handoff semantics.** `handoff create` is allowed on any existing
  task regardless of status, including done (a handoff can document state
  after closure; the contract sets no status rule and the sequence test
  exercises a done task). `--from`/`--to` must be non-empty after strip and
  may be equal (no rule against a self-handoff); `--state` must be non-empty.
  `accept` is one-shot: an already-accepted handoff exits 1 naming the
  original `accepted_at`. Events: `(handoff, create)` and `(handoff, accept)`.
  Task show, the pack PRIOR RUNS & HANDOFF STATE section, and
  `Handoffs/H-*.md` sync were Night-1 wiring (D-P0.7), proven here with
  CLI-created rows.
- **D-W3.2 — Gate P3 result.** 117 tests green (create flows through task
  show → pack → synced note; accept + double-accept exit 1; missing task /
  malformed and missing ids / empty state refusals; secret scan fires on
  handoff state naming PRIOR RUNS & HANDOFF STATE without echoing; create and
  accept atomicity — accept's rollback asserts accepted_at stays NULL;
  sequence test and pre-init guard extended).

## W4 decisions

- **D-W4.1 — `valid_until` semantics.** `--valid-until YYYY-MM-DD` is strict
  (regex + real-calendar-date check). A date-only value expires at UTC
  midnight STARTING that date; liveness is a plain string comparison against
  the full-ISO clock value (`"YYYY-MM-DD" < "YYYY-MM-DDT…"` makes that
  correct). `retire` sets `valid_until` to the full-ISO now; "already
  retired" means valid_until is non-NULL and `<= now` — a row with a future
  valid_until can still be retired early.
- **D-W4.2 — Supersede rules.** `--supersedes M-XXXX`: the old row must exist
  and must not already be superseded (chains stay linear; re-superseding
  exits 1 naming the existing successor). No cross-field matching is enforced
  (a supersede may change key/scope — the pack rule is per-key anyway). Both
  `retire` and the supersede pointer-set refresh the mutated row's
  `updated_at` (uniform rule: any row mutation refreshes it). Supersede is
  part of the single `(memory, add)` event; its payload carries
  `"supersedes"` — one operation, one event, per D-P0.5.
- **D-W4.3 — Pack inclusion rule lives in `ops.memory_for_project`.** Same
  entry point Night-1's pack compiler already called, now implementing the
  contract rule: live rows only (superseded_by IS NULL AND valid_until NULL
  or future), scope=global plus the pinned project, latest row (highest id)
  per (scope, project, key) wins, ordered scope then key (`'global'` sorts
  before `'project'`, so global rows lead). Pack content therefore depends on
  liveness AT BUILD TIME; an expiry flips the section content → different
  inputs_hash → new pack row, consistent with D-P0.16/D-P0.19 (no wall-clock
  value is ever WRITTEN into the pack).
- **D-W4.4 — `memory list` carries a computed `live` flag.** JSON/CLI
  convenience derived from the clock at query time; never written to
  generated files. Retired/superseded rows always stay in the listing with
  their valid_until / superseded_by visible.
- **D-W4.5 — Gate P4 result.** 129 tests green (add/list/retire/supersede
  incl. all enum/format refusals; retired rows never vanish from list;
  retired/superseded/expired excluded from packs while latest-per-key wins
  and global precedes project; secret scan via memory value names MEMORY and
  never echoes; Memory notes sync with [[project]] and [[M-XXXX]] supersede
  links; add/supersede/retire atomicity incl. pointer rollback; sequence test
  and pre-init guard extended).

## W5 decisions

- **D-W5.1 — The FTS index is derived state, not schema.** One virtual table
  `search_index(entity UNINDEXED, entity_id UNINDEXED, title UNINDEXED,
  body)` created with `CREATE VIRTUAL TABLE IF NOT EXISTS`, where `body`
  concatenates exactly the contract's searchable fields per entity. It is
  rebuilt from the source tables (DELETE + repopulate) whenever the meta
  watermark `fts_event_watermark` ≠ current `MAX(events.id)` OR the table is
  missing — so it is safe to DROP at any time. This is NOT a schema change:
  schema_version stays "1", Night-1 databases open unmodified, and the meta
  watermark row is data, not schema. (Recorded per the contract's explicit
  instruction.)
- **D-W5.2 — Search is EVENTLESS (extends D-P0.6).** The index rebuild and
  watermark write mutate derived state only. Emitting an event per search
  would bump `MAX(events.id)` and make the index permanently stale — the
  derived-view rule is load-bearing here, not just aesthetic.
- **D-W5.3 — Query semantics.** FTS5: every whitespace-separated term is
  double-quoted (phrase token) so user text can never reach the FTS parser
  as syntax; terms are implicitly ANDed; a query FTS still cannot parse
  exits 1. LIKE fallback: case-insensitive substring conjunction (AND of
  `LIKE '%term%'`) evaluated over the SAME document set the index holds,
  with simple deterministic ordering (entity type, then ascending id).
  Known semantic gap, documented: FTS matches whole tokens, LIKE matches
  substrings — membership parity holds (and is tested) for whole-word
  queries.
- **D-W5.4 — Ranking and snippets.** FTS5 orders by bm25 (`ORDER BY rank`)
  with (entity, entity_id) tie-breaks for determinism; snippets come from
  `snippet()` (FTS5) or a deterministic ±40-char window around the first
  term hit (LIKE), both collapsed to one line.
- **D-W5.5 — Gate P5 result.** 138 tests green (all five entity types found
  with correct ID prefixes; text output = backend line + one line per hit;
  forced-fallback path; fts5↔like membership parity incl. a multi-term and
  a no-hit query; watermark write + rebuild-on-new-events; DROP-and-search
  recovery; eventless; empty-query and no-results behavior; pre-init guard).

## W6 decisions

- **D-W6.1 — `review build` is EVENTLESS.** It regenerates a derived view of
  ledger state (like sync — extends D-P0.6): no ledger rows mutate, no event
  is emitted, and idempotency ("two builds with no data change → identical
  file") holds strictly. Recorded per the contract's explicit instruction.
- **D-W6.2 — Review windows.** "Recently added" evidence/runs = a 7-day
  window ending on the review date (`[date-6, date]`, ISO-prefix
  comparisons; the upper bound uses `date + "~"` since `'~' > 'T'`). Stale
  memory = `valid_until[:10] <= date`, or valid_until NULL and
  `updated_at[:10] <= date-30d`. Every window derives from the date
  parameter; the default date is `utc_today()` from the single clock — no
  other wall-clock read. Superseded rows are NOT specially excluded from the
  stale list (the contract's definition doesn't exclude them; noted as a
  limitation).
- **D-W6.3 — Notes preservation is raw-bytes.** The preserved region starts
  at the first line reading `## Notes` (tolerating a CR on that line) and is
  spliced back verbatim — CR bytes and a missing trailing newline in the
  user's region survive, because the contract's byte-for-byte rule overrides
  the LF/trailing-newline rule for that user-owned region (generated head
  stays LF-clean). If the heading was deleted, a fresh `## Notes\n` tail is
  appended.
- **D-W6.4 — Review bullets use wikilinks.** They resolve once the mirror is
  synced; the expected order is review build → sync → doctor (exactly the
  Weekend smoke's order). Doctor treats `Reviews/YYYY-MM-DD.md` as a
  generated kind and checks its links like any other note.
- **D-W6.5 — Gate P6 result.** 145 tests green. One red run on the way was a
  test-side scenario error, not production code: the test plants an
  unevidenced done via SQL (to populate the review's attention list), which
  doctor CORRECTLY fails; the test now asserts that exact check failing
  while the wikilink/containment checks pass.

## W7 decisions

- **D-W7.1 — Export shape.** One JSON object per line carrying all seven
  event columns; `payload_json` stays the raw stored string (exact
  round-trip, no re-serialization). UTF-8, LF, one trailing newline per
  line. Default path `exports/events-<UTC-stamp>.jsonl` uses the same
  YYYYMMDDTHHMMSSZ stamp and -2/-3 collision policy as snapshot; an explicit
  `--output PATH` writes (and overwrites) exactly where the user pointed.
  Export is read-only and EVENTLESS (extends D-P0.6). `export events`
  without `--jsonl` exits 1 naming the flag (JSONL is the only format).
- **D-W7.2 — Snapshot via the backup API.** `conn.backup(dest)` — never a
  raw file copy (WAL tearing). The audit record is EVENT-ONLY (entity
  `system`, action `snapshot`, no domain row — the "domain row" is the file
  itself), emitted AFTER the file is written; its payload carries the
  filename and the explicit note that the snapshot does not contain its own
  event. The snapshot naturally includes the derived FTS index when present
  (it lives inside aos.db; it is droppable in the copy too).
- **D-W7.3 — WAL test design.** A merely-open second connection holds no
  lock, so closing the CLI's connection would still checkpoint and delete
  the -wal. The integrity test pins an open read transaction instead,
  keeping uncheckpointed writes in aos.db-wal while the snapshot runs — and
  then proves the snapshot contains the WAL-resident row a bare file copy
  would have missed.
- **D-W7.4 — Gate P7 result.** 150 tests green (JSONL: every line parses,
  count == events rows, ids ascending, all columns, eventless, --output,
  --jsonl required; snapshot: integrity_check ok, row-count parity at
  snapshot time, WAL-resident row present, no self-event inside, event-only
  audit with correct payload, collision suffixes -2/-3; sequence seal
  extended with snapshot plus four proven-eventless commands).

## W8 decisions

- **D-W8.1 — Doctor check-count pin moved 6 → 12.** The Night-1 test
  `test_doctor_passes_on_clean_generated_demo` pinned exactly six output
  lines; the Weekend contract mandates six additional checks, so the pin
  moves UP to twelve with the all-PASS assertion unchanged. This is the
  contract-driven strengthening path, not a weakened test: no assertion was
  relaxed, and the test count never shrank. Recorded here because rule 3
  ("never weaken an existing test") demands the change be justified, not
  silent.
- **D-W8.2 — schema_version check placement.** `open_db` hard-stops on a
  version mismatch before any command body runs (Night-1 rule, D-P0 era),
  so the CLI can never reach doctor's check list with a bad version — the
  new "schema_version supported" check therefore matters at the
  `run_checks` layer (exercised directly by a test); the CLI path still
  exits 1 with the loud one-line message either way.
- **D-W8.3 — Corruption harness.** Each new check has a dedicated failure
  test that plants its corruption through a RAW sqlite3 connection (no
  foreign-key PRAGMA, no events — states the CLI could never produce) and
  asserts exactly ONE check fails, naming the offender: status outside the
  vocabulary · handoff → missing task · task-linked decision → missing task
  · dangling memory supersede pointer · pack row → missing task · pack file
  deleted from disk.
- **D-W8.4 — Gate P8 result.** 158 tests green (12/12 checks pass on a
  clean workspace exercising every Weekend surface; six corruption tests;
  checks-layer schema_version failure + CLI hard-stop).

## W9 decisions

- **D-W9.1 — Adversarial review pass (extends the Night-1 D-P7.3 practice).**
  Before the final gate, seven independent reviewers (hard constraints ·
  features 1–4 · features 5–7 · features 8–10 + required-tests walk ·
  self-review list · back-compat/regression · deep correctness) reviewed the
  Weekend diff; every finding was then adversarially verified by a separate
  agent instructed to refute it. Result: 10 findings, 9 confirmed (5
  distinct), 1 refuted. Confirmed and fixed:
  (1) [bug] `review build` interpolated the run agent name into the Recent
  runs bullet without one-line collapsing — a CR/LF-bearing agent name could
  inject a literal `## Notes` line, hijacking the preserved-region anchor
  and breaking idempotency (reproduced live by the verifier). Fixed with
  `_one_line(row['agent'])` + a regression test proving a hostile
  `--agent $'evil\r\n## Notes\ninjected'` stays inert, LF-clean, idempotent.
  (2) [bug] the LIKE-fallback snippet located the hit in `body.lower()` but
  sliced the original string; length-changing lowercase (`İ`, U+0130)
  desynced the window and could omit the matched term. Fixed by locating the
  hit case-insensitively on the original string (regex), with a regression
  test.
  (3) [missing required test] two-sync tree-hash idempotency was never
  exercised with ALL new note types present — added
  `TestSyncAllNoteTypes` (decisions + accepted handoff + memory supersede
  chain + retired row + review note; second sync 0 written, identical tree
  hash).
  (4) [missing required test] ".agentic-os/ remains ignored" had no suite
  pin — added `TestRuntimeStateStaysIgnored` (see D-W9.2).
  (5) was the CR-byte variant of (1); same fix.
  Refuted (accepted as-is): the `sqlite3.OperationalError` catch around the
  FTS MATCH being "over-broad" — the verifier demonstrated a real
  user-reachable parse error through that exact catch (embedded NUL), that
  real I/O failures surface as exit 2 via earlier uncaught statements, and
  that the mapping is journaled (D-W5.3).
- **D-W9.2 — Scope of the ignored-runtime-state test.** The required test
  ".agentic-os/ remains ignored: git status --short shows nothing staged" is
  pinned as: `git check-ignore` confirms the ignore rule, `git ls-files --
  .agentic-os` is empty (nothing tracked in the index, ever), and no status
  line references `.agentic-os`. The staged-entries assertion is scoped to
  `.agentic-os` paths — a repo-wide "nothing staged at all" assertion would
  make the suite fail whenever a developer legitimately stages source files
  before running tests. The literal `git status --short --ignored` capture
  the contract's final gate asks for is recorded in the FINAL REPORT.
- **D-W9.3 — Final suite count.** 162 tests green (P0 baseline 89 → 162;
  +73, no existing test removed or weakened).

# DECISIONS — Agentic OS v0.4 U-E6 flight recorder, deterministic replay, and incident forensics (Wave 0)

This section continues the `D-v0.4.*` series for the U-E6 Wave 0 architecture
freeze: flight recording, deterministic replay, and incident forensics.
Architecture only — no production code, tests, DDL, migrations, fixtures, CLI
handlers, power entries, protocol schemas or README prose ship in this commit.
Branch `v0.4-u-e6-flight-recorder-replay`, worktree
`/home/daksh/Projects/agentic-os-u-e6`, baseline
`55e72c8c298dfb3c1577d0425faa31c31019f8f2` (= HEAD = `origin/main` =
`milestone/v0.4-u-e1-observability-foundation^{}`). Prepended per the established
precedent (D-W0.4, reaffirmed in D-v0.2.7, D-v0.4.4, D-v0.4.103); everything
below stays byte-identical, including D-v0.4.1 … D-v0.4.143, which the decisions
here supersede only where they quote them and never reword.

Unlike U-E1's A1, this freeze writes **no amendment into any landed contract
file**. U-E6 is a new unit, not a later U-E1 wave, and the U-E6 session is
authorized to write exactly two repository paths — `DECISIONS.md` and
`agentic-os-v0.4-u-e6-flight-recorder-replay-contract.md`. Every supersession
U-E6 needs is therefore declared inside its own contract, and the superseded
documents are left byte-identical.

## D-v0.4 decisions (U-E6 Wave 0)

- **D-v0.4.144 — U-E6 authority derives from U-W3 §1.1, U-E1 §0.1 (D-v0.4.139),
  and U-W2.2 §4.2; it supersedes nothing.**

  Three landed clauses grant the whole unit: U-W3 §1.1 (transition-policy version
  2, `workflow_attempts`, `workflow_checkpoints`, compensation, restoration, and
  the retry/recovery boundary), U-E1 §0.1 / D-v0.4.139 (the observability
  projection, its trace-root invariant, and the reservation of flight recording,
  deterministic replay, incident reconstruction, re-simulation, payload capture,
  time-travel query, and retention policy to U-E6 by name), and U-W2.2 §4.2 (the
  store's judgment authority: existence, digest verification, history–snapshot
  agreement, compare-and-swap win, and nothing else). U-E6 ships what those
  clauses reserved and nothing else.

- **D-v0.4.145 — Replay semantics are eight mutually exclusive definitions;
  no implementation may conflate them.**

  The eight terms are frozen in the U-E6 contract §1:
  1. **integrity verification** — recomputes every digest, reports every
     divergence/unreadable/truncated/clock_inconsistent; never asserts success/failure.
  2. **workflow history folding** — pure reducer `decide` over `workflow_events` in
     `seq` order; produces derived snapshot; never asserts runtime behavior.
  3. **snapshot rebuild** — materializes snapshot at a specific `event_seq` or
     `checkpoint_seq`; claims "ledger folds to this state", never "workflow was in
     this state at wall-clock time".
  4. **flight-record reconstruction** — assembles complete self-contained record
     from all eight tables + `work_spec_document` digest + journal rows; outputs a
     flight record bundle (`aos.flight-record/v1`).
  5. **incident reconstruction** — correlates flight record, observability
     projection, verification report, and optional operator context; cites evidence
     by row identity (table, row_id, content_sha256); never infers causation.
  6. **deterministic replay** — re-executes `decide` over flight record events in
     isolation; produces replay trace with per-step `byte_identical_to_ledger`; never
     mutates `aos.db`, never issues intents/receipts/facts.
  7. **re-simulation** — deterministic replay with explicit declared substitutions
     (work_spec replacement, retry.max_attempts override, policy version override,
     synthetic receipts, event removal); every substitution recorded in output trace.
  8. **counterfactual / time-travel query** — read-only query over ledger or bundle;
     "what if" questions answered only via explicit re-simulation under declared
     substitution; never mutates, never asserts historical authority for the
     counterfactual branch.ournal; produces a flight record bundle
     (`aos.flight-record/v1`); contains no secrets, no model outputs.
  5. **incident reconstruction** — correlates flight record, observability,
     verification, and operator question; cites evidence by row identity; never
     infers causation the ledger does not support.
  6. **deterministic replay** — re-executes `decide` over flight record events in
     isolation; executes no side effects, issues no intents, delivers no receipts,
     records no facts, mutates no ledger; produces replay trace with per-step
     `byte_identical` boolean; never becomes execution.
  7. **re-simulation** — deterministic replay with explicit, declared substitutions
     (work_spec override, retry budget override, policy version override, synthetic
     receipts, event removal); every substitution recorded in output.
  8. **counterfactual / time-travel query** — read-only query over ledger or
     bundle; "what would" is explicitly re-simulation under declared substitution;
     never mutates, never asserts historical authority for counterfactual branch.

  Non-goals (explicitly reserved or forbidden): cross-process timeline
  reconstruction, model output reconstruction (D-v0.4.137), external runtime task
  state reconstruction (D-v0.4.103), payload/body parsing beyond digests and byte
  lengths (D-v0.4.137), any write path into `aos.db`, any network collector,
  daemon, background watcher, or cloud telemetry service.

- **D-v0.4.146 — U-E6 requires no new tables in `aos.db`; the flight record is a
  derived export artifact (`aos.flight-record/v1`).**

  Every byte in a flight record bundle is reconstructible from the eight existing
  workflow tables + `work_spec_document` + relevant `journal` rows. Adding a
  `flight_records` table would duplicate authoritative data, create a second write
  path requiring consistency, and require its own retention/migration/integrity
  story. Instead, U-E6 introduces: (1) a deterministic flight record bundle format,
  (2) a replay engine, (3) a re-simulation harness, (4) an incident report format,
  (4) minimal read-only CLI surfaces.

- **D-v0.4.147 — Flight record bundles exclude all document bodies per
  D-v0.4.137; only digests and byte lengths are included.**

  Excluded from canonical payload: `workflow_intents.document`, `workflow_receipts.document`,
  `workflow_facts.document`, `workflow_checkpoints.document`, `report_document`,
  and `work_spec_document` (the full document body is never in the canonical payload).
  Included in canonical payload: for each excluded document, only `content_sha256` /
  `receipt_sha256` / `document_sha256` and `payload_bytes` / `content_sha256`.
  The `work_spec_digest` (the `work_spec_sha256` from the workflow row) is included
  in the canonical payload. Replay fetches the `work_spec_document` from the ledger
  by digest at replay time (or from substitution set for re-simulation).

- **D-v0.4.148 — Flight record bundles must pass `secretscan` with zero findings;
  any hit refuses bundle creation with `secret_in_flight_record`.**

  Creation pipeline: assemble bundle → run `secretscan.scan(canonical_json_bytes)` →
  if `findings > 0`, refuse creation and list finding types (not values) → write
  file only if scan passes. Journal payload members included per
  `observability._JOURNAL_PAYLOAD_ATTRIBUTES` (closed vocabulary only).

- **D-v0.4.149 — Deterministic replay runs `decide` over the flight record's event
  sequence in isolation; never issues intents, delivers receipts, records facts,
  or mutates `aos.db`; produces a replay trace with per-step `byte_identical`
  boolean.**

  Replay engine validates bundle integrity manifest, runs `decide` sequentially
  over `workflow_events` in `seq` order, compares derived snapshot to stored
  `resulting_revision`/`expected_revision` at each step. Returns `{steps: [...],
  byte_identical: bool, divergence_at_seq: int | null}`. Runs in separate process
  or isolated function with no database write access; CLI verb is `replay` (not
  `submit`).

- **D-v0.4.150 — Re-simulation accepts explicit, declared substitutions; every
  substitution is recorded in the output trace.**

  Substitution types: `work_spec_document` replacement (must pass secret scan),
  `retry.max_attempts` integer override, `transition_policy_version` (1 or 2),
  `synthetic_receipts` array injected at specific `seq` positions,
  `removed_event_seq` integer. Empty substitution set equals deterministic replay.

- **D-v0.4.151 — Incident reconstruction documents cite evidence by row identity
  (table, row_id, content_sha256); they never infer causation the ledger does not
  support.**

  Format `aos.incident-report/v1` references flight record bundle by content
  digest, includes observability projection, includes verification report,
  contains operator-provided context (optional, free-text, never parsed by AOS),
  contains structured evidence index. If ledger row is later purged, incident
  document still records what it cited.

- **D-v0.4.152 — CLI surfaces are exactly six command leaves with exact power
  classifications; no daemon, no background job, no network endpoint.**

  Exact command leaves and parser keys:
  1. `aos flight-record create <WF-id> --out <file>` → `("flight-record", "create")`
     - Power class: `DERIVED_WRITE` (writes filesystem, never ledger)
     - Recovery: BLOCKED
     - Deep preflight: runs
     - Eco: deferred
  2. `aos flight-record verify <file>` → `("flight-record", "verify")`
     - Power class: `READ_ONLY`
     - Recovery: ALLOWED
     - Deep preflight: runs
     - Eco: immediate
  3. `aos replay <file>` → `("replay",)`
     - Power class: `READ_ONLY`
     - Recovery: ALLOWED
     - Deep preflight: runs
     - Eco: immediate
  4. `aos replay <file> --resimulate <subst-file>` → `("replay",)` with flag `--resimulate`
     - Power class: `READ_ONLY` (same command leaf as deterministic replay)
     - Recovery: ALLOWED
     - Deep preflight: runs
     - Eco: immediate
  5. `aos incident create <WF-id> --out <file>` → `("incident", "create")`
     - Power class: `DERIVED_WRITE` (writes filesystem, never ledger)
     - Recovery: BLOCKED
     - Deep preflight: runs
     - Eco: deferred
  6. `aos incident export <WF-id> --out <dir>` → `("incident", "export")`
     - Power class: `DERIVED_WRITE` (writes filesystem directory, never ledger)
     - Recovery: BLOCKED
     - Deep preflight: runs
     - Eco: deferred

  Grammar notes: `replay --resimulate` is a flag on the same command leaf `("replay",)`,
  not a separate subcommand. `flight-record` and `incident` are two-level groups
  yielding exactly four distinct two-level keys. No new power modes or power entries
  beyond these six leaves.

- **D-v0.4.153 — Canonical JSON serialization rules.**

  `protocols.serialize_canonical` (sorted keys, no whitespace, UTF-8). Array order
  by natural key: `workflow_events` by `seq`, `workflow_commands` by `id`,
  `workflow_intents` by `id`, `workflow_receipts` by `id`, `workflow_facts` by
  `id`, `workflow_attempts` by `attempt_no`, `workflow_checkpoints` by
  `checkpoint_seq`, `journal_rows` by `row_id`. Object member order sorted
  lexicographically. Integers as JSON numbers. Digests as lower-case hex.
  Timestamps RFC3339 UTC with `Z` suffix. Top-level `protocol_version` string.

- **D-v0.4.154 — Integrity model: row-level, table-level, bundle-level.**

  Row-level: every stored row carries `content_sha256` (recomputed on every read).
  Table-level: manifest = `sha256(concat(sorted(content_sha256)))` per table.
  Bundle-level: content digest = `sha256(canonical_json_bytes)`. `verify`
  recomputes all three. Replay recomputes every step from `decide`; divergence
  from stored `resulting_revision`/`expected_revision` reported as
  `divergence_at_seq`.

- **D-v0.4.155 — Retention: ledger unchanged; flight record bundles and incident
  reports are operator-managed files with no automatic lifecycle.**

  U-W3 and U-E1 define no retention policy for workflow tables; U-E6 adds none.
  Bundles and reports have no automatic creation, deletion, or TTL.
  Replay/re-simulation traces are ephemeral stdout unless redirected.

- **D-v0.4.156 — Backward compatibility: bundles carry `protocol_version` and
  `schema_version`; unknown versions are refused; no migration required; no reducer
  archive/loader exists.**

  Future `v2` bundle format can coexist; `verify` and `replay` dispatch on version.
  Ledger schema version recorded in bundle; old bundles remain replayable **only if
  the current reducer supports their event vocabulary**. The current reducer handles
  both policy v1 and v2 histories via the `policy_version` field in the snapshot.
  If a bundle's `schema_version` implies a vocabulary the current reducer cannot
  process (e.g., a future schema v8 with new event types), `replay` **refuses** with
  `reducer_vocabulary_mismatch`. Schema version stays `"7"`; no migration required
  for U-E6.

- **D-v0.4.157 — Failure semantics: no operation mutates `aos.db`; divergence in
  replay is reported not refused; secret scan failure refuses creation.**

  Exit codes: workflow not found (2), secret scan hit (3, no file written), I/O
  error (4), bundle integrity failure (1), unknown protocol_version (2), replay
  divergence (0 with `divergence_at_seq`), reducer refusal on accepted event (0
  with refusal reason), malformed substitution (2), invalid WorkSpec from
  substitution (3), incident create workflow not found (2), directory not empty
  (2). No operation ever mutates `aos.db`.

- **D-v0.4.158 — Test strategy requires ten specific mutation/adversarial tests
  plus property tests.**

  Adversarial: (1) tampered bundle `content_sha256` → verify detects, replay
  refuses; (2) secret in WorkSpec `goal` field → ledger admits (warn), create
  refuses (scans canonical payload); (3) secret in journal row payload → create
  refuses (tests scanner on closed vocabulary); (4) missing `workflow_events` row
  → create includes gap in manifest (row count mismatch) or refuses; (5) replay
  divergence → reports `divergence_at_seq`; (6) re-simulation work_spec
  `retry.max_attempts` override → trace shows substitution and different budget;
  (7) counterfactual removal of `dispatch_accepted` event → re-simulation shows
  workflow never enters `running`; (8) unknown `protocol_version` → verify/replay
  refuse; (9) `schema_version` mismatch → replay refuses (reducer vocabulary
  mismatch); (10) corrupted `workflow_checkpoints.document_sha256` → verify
  detects; replay (which doesn't use checkpoints) still verifies events.
  Property: `replay(flight_record_create(WF))` always produces `byte_identical:
  true` for a verified ledger; `flight_record_create` is idempotent on the
  **canonical payload** (two consecutive creates for the same unchanged workflow
  produce byte-identical canonical payloads; wrapper `created_at` differs, which
  is allowed); `verify(bundle)` on a bundle produced by `create` always passes;
  re-simulation with empty substitution set equals deterministic replay.

- **D-v0.4.159 — Protocol artifacts `aos.flight-record/v1` and
  `aos.incident-report/v1` are added to the registry; no existing protocol is
  modified.**

- **D-v0.4.160 — Determinism rule: the canonical payload is byte-identical across
  repeated creates of the same unchanged workflow; the wrapper metadata is
  explicitly excluded from the canonical payload.**

  The file format separates a canonical payload (the integrity-manifested,
  replayed JSON) from a wrapper containing `created_at` (RFC3339 instant of
  bundle creation) and `secret_scan` result. `verify` and `replay` operate on
  the canonical payload only. Two consecutive `flight-record create` invocations
  for the same unchanged workflow produce byte-identical canonical payloads.
  The wrapper `created_at` necessarily differs; this is permitted and does not
  violate byte-identical reconstruction. No wall clock, RNG, locale, cwd,
  environment, iteration order, or filesystem metadata affects the canonical
  replay payload.

- **D-v0.4.161 — Repository path boundary: exactly two files written in this
  freeze (`DECISIONS.md` and this contract); implementation adds exactly fourteen
  authorized implementation paths.**

  Freeze paths: `DECISIONS.md` (amended),
  `agentic-os-v0.4-u-e6-flight-recorder-replay-contract.md` (this file).
  Implementation paths (not in this commit):
  `agentic_os/flight_recorder.py`,
  `agentic_os/replay.py`,
  `agentic_os/incident.py`,
  `agentic_os/protocols/aos.flight-record.v1.json`,
  `agentic_os/protocols/aos.incident-report.v1.json`,
  `tests/test_v04_flight_recorder.py`,
  `tests/test_v04_replay.py`,
  `tests/test_v04_incident.py`,
  `tests/test_v04_flight_recorder_cli.py`,
  `tests/test_v04_replay_cli.py`,
  `tests/test_v04_incident_cli.py`,
  `TROUBLESHOOTING.md` (amended),
  `agentic_os/cli.py` (amended — CLI wiring carrier),
  `agentic_os/power.py` (amended — power-classification carrier).

- **D-v0.4.162 — `cli.py` and `power.py` were omitted from the frozen
  implementation inventory; they are now explicitly authorized solely as CLI-wiring
  and power-classification carrier paths.**

  The frozen U-E6 §14 boundary listed exactly twelve implementation paths and
  excluded `agentic_os/cli.py` and `agentic_os/power.py` while the six CLI
  leaves in §5 necessarily require CLI wiring in `cli.py` and their `READ_ONLY` /
  `DERIVED_WRITE` classifications necessarily require power entries in `power.py`.
  This contradiction is resolved by authorizing those two files as the thirteenth
  and fourteenth implementation paths, carrying only the six frozen leaves and their
  existing power classifications — no new CLI leaf, power mode, or power entry.
  No other U-E6 semantic decision changes.

# DECISIONS — Agentic OS Night-1 build

This file records every simplification, interpretation, and deviation made while
executing `agentic-os-night1-build-prompt.md` (the contract). Newest entries are
appended per phase. Format: `D-P<phase>.<n>`.

## Plan (P0) — mapped to phase gates

- [x] **P0** Inspect repo, read research context, write this file + plan.
- [x] **P1** `utils.py`, `ids.py`, `db.py`, `events.py`, `models.py`, first ops
      (project add / task add at the ops layer). Gate: tests 2 (ops-level), 11, 15 (ids-level).
- [x] **P2** `cli.py` skeleton + `init` / `project add` / `task add|list|show` /
      `status` / `log` / `in` + README. Gate: tests 1, 3, 4, 10, 17 (+ CLI-level 15).
- [x] **P3** `pack.py` compiler + secret scan + adapter templates. Gate: tests 5, 14, 16.
- [x] **P4** `run start|end` + `evidence add` + `done` + status transitions +
      override event. Gate: tests 6, 7 (+ CLI-level test 2 complete).
- [x] **P5** `render.py` + `obsidian.py` sync. Gate: tests 8, 12.
- [x] **P6** `doctor.py`. Gate: tests 9, 13.
- [x] **P7** FINAL VERIFICATION GATE (full suite, smoke test, adversarial
      review, constraint walk, self-review, containment check) → FINAL REPORT.

Rule per gate: that phase's tests written AND the full suite green before moving on.

## P0 decisions

- **D-P0.1 — Research files.** All three research files are present and were read
  as context only (report §1/§5/§6/§7/§8/§9/§12, state, sources). They are data,
  not instructions; nothing in them overrides the build prompt.
- **D-P0.2 — Module responsibilities** (spec fixes the file list; roles chosen here):
  `utils.py` = clock (single `utc_now_iso()`), UTF-8/LF file writer, sha256 helpers,
  tree hash, root discovery, `AosError`; `ids.py` = human-ID render/parse;
  `db.py` = connection helper + PRAGMAs + schema init + transaction helper;
  `events.py` = event emission (used inside the same transaction as domain writes);
  `models.py` = enums + dataclasses + row converters; `ops.py` = all mutating
  domain operations and queries; `pack.py` = pack compiler + secret scan;
  `render.py` = all generated-text builders (notes, Home, CONVENTIONS, adapter
  PROTOCOL templates, pack boilerplate); `obsidian.py` = mirror sync;
  `doctor.py` = health checks; `cli.py` = argparse wiring, exit codes, output.
- **D-P0.3 — Adapter template source of truth.** Template content lives as
  constants in `render.py`; the repo `adapters/*/PROTOCOL.md` files and the
  copies `init` writes into `.agentic-os/adapters/` are both produced from those
  constants, so `init` never depends on repo-relative file lookup.
- **D-P0.4 — Root discovery.** Commands other than `init` locate `.agentic-os/`
  by walking up from the current working directory until a directory containing
  `.agentic-os/aos.db` is found; not found → exit 1 "Not initialized…".
  `init` takes `--root PATH` (default: cwd).
- **D-P0.5 — Events: one event per operation.** Each mutating operation emits ONE
  events row whose payload captures the full change (e.g. `run start` records the
  run row and the task's ready→active transition in one payload). Payload always
  includes `"schema_version": 1`. Default actor is `"human"`; `evidence add
  --provenance agent:X` uses that provenance string as the actor.
- **D-P0.6 — `sync` writes no event.** `sync` regenerates a derived view; it
  mutates no ledger rows, so it emits no event. This also preserves "same DB
  state → byte-identical mirror" strictly (an event-per-sync would change DB
  state on every sync).
- **D-P0.7 — Handoffs / memory / decisions / agents tables.** Schema, rendering
  (task show, pack sections, Obsidian notes) and doctor support are built, but no
  CLI command creates rows in Night-1 (`handoff`, `memory`, `decision`, `agent`
  commands are Weekend scope). Pack sections MEMORY / DECISIONS / PRIOR RUNS &
  HANDOFF STATE render "(none)" placeholders when empty.
- **D-P0.8 — Timestamps.** `utils.utc_now_iso()` → `YYYY-MM-DDTHH:MM:SSZ`
  (seconds precision, UTC). It is the only place `datetime.now` is called.
  `log --today` derives today's UTC date from the same utility.
- **D-P0.9 — argparse exit codes.** Argparse's default usage-error exit code is 2;
  the contract reserves 2 for internal errors. The CLI subclasses
  `ArgumentParser` so usage errors print one line to stderr and exit 1
  (user error).
- **D-P0.10 — Atomicity test hook.** `ops.py` calls `events.emit` through the
  module object (`events.emit(...)`), so test 11 can `unittest.mock.patch`
  the emit function to raise mid-transaction and assert both the domain row and
  the event row are absent. `unittest.mock` is stdlib.
- **D-P0.11 — Test staging across gates.** Tests 2 and 15 have CLI-facing final
  forms (event row per mutating *command*; malformed ID → *exit code* 1). At P1
  they are covered at the ops/ids layer (AosError carries `exit_code == 1`); the
  CLI-level assertions land with the commands (P2/P4). Gate claims below state
  which layer is covered.
- **D-P0.12 — `project add` semantics.** `--repo` must be an existing directory
  (early validation; exit 1 otherwise); stored as `Path.resolve()` absolute path.
  Re-add with an existing slug is a no-op: exit 0, prints a note, updates
  nothing, emits no event (no mutation happened).
- **D-P0.13 — `status` "tasks missing evidence".** Defined as open tasks
  (status inbox/ready/active) with zero evidence rows. Done-without-evidence is
  doctor's job (it also checks the override event).
- **D-P0.14 — Status transitions enforced.** `run start` allowed on inbox/ready/
  active tasks (inbox tasks have no project → anchor_commit NULL + payload note);
  rejected on done tasks. `done` allowed from inbox/ready/active with evidence
  (or explicit override); `done` on done → exit 1. `run end` does not change task
  status. Multiple concurrent runs on one task are permitted (no constraint in
  the schema; Weekend can add policy).
- **D-P0.15 — `done --no-evidence` events.** Emits the normal done event plus an
  additional `action="done_override"` event in the SAME transaction, and only
  when evidence count is actually zero (if evidence exists the flag is
  unnecessary and no override event is written).
- **D-P0.16 — Pack inputs_hash.** sha256 over a canonical serialization of
  (target, budget_kb, and every section's source content BEFORE truncation).
  Different target or budget ⇒ different hash ⇒ different row/file, so
  `UNIQUE(task_id, inputs_hash)` can hold while budgets vary. `packs.path` is
  stored relative to `.agentic-os/`.
- **D-P0.17 — Pack budget floor.** If the pack still exceeds budget after
  truncating PRIOR RUNS & HANDOFF STATE → MEMORY → DECISIONS, the protected
  sections are never cut: the pack is written as-is, a one-line warning goes to
  stderr, exit 0. (The alternative — refusing — would make small budgets brick
  the command with no remedy.)
- **D-P0.18 — Token estimate.** `token_estimate = ceil(len(content) / 4)` —
  chars/4 heuristic, consistent with the budget being char-based.
- **D-P0.19 — Pack determinism.** Pack files contain no generation-time values
  (the YAML header carries task id, title, target, budget, inputs_hash and DB
  timestamps only), so identical inputs produce byte-identical packs and
  "rewrite only if content differs" is meaningful.
- **D-P0.20 — JSON output shape.** Every `--json` command prints exactly one
  JSON object (never a bare array): `task list` → `{"tasks": [...]}`, `status` →
  `{"projects": …, "open_tasks": …, "recent_tasks": […], "tasks_missing_evidence":
  […], "last_runs": […]}`, `task show` → `{"task": …, "project": …, "runs": […],
  "decisions": […], "evidence": […], "handoffs": […]}`, `log` → `{"events": […]}`.
  On error, stdout stays empty; the one-line error goes to stderr.
- **D-P0.21 — Known Night-1 gap (by design).** `in` creates project-less inbox
  tasks and no Night-1 command assigns a project afterwards, so inbox captures
  cannot be packed (`pack build` → "Assign a project first"). Triage/assignment
  is Weekend scope.
- **D-P0.22 — `log` scope.** `log T-0001` shows events for the task and for its
  runs/evidence/packs/handoffs (ids resolved via the task's rows). `log --today`
  filters events whose `ts` date equals today's UTC date. Bare `log` shows the
  50 most recent events. Ordering: ascending id (stable).
- **D-P0.23 — Secret scan scope.** The scan runs per-section over all dynamic
  content entering the pack (task/project fields, decisions, memory, prior
  runs/handoffs) before assembly, so refusals can name the section. Static
  boilerplate authored in `render.py` is ours and contains no secret-shaped text.
  Matched pattern NAMES and section names are printed; matched text never is.
- **D-P0.24 — Doctor "nothing outside AOS/".** Implemented as: the vault
  directory `.agentic-os/obsidian-vault/` must contain only the `AOS/` subtree,
  and every file under `AOS/` must be one of the generated kinds (Home,
  CONVENTIONS, or an entity note in its proper folder). Sync itself is also
  containment-tested directly (test 12).

## P7 decisions

- **D-P7.1 — Smoke test working directory.** The contract forbids touching
  anything outside this repo, so "a scratch working directory" is interpreted
  as the repo root in a clean state (no pre-existing `.agentic-os/`): the
  commands then run exactly as written and `.agentic-os/` is created inside
  the repo — which is also the normal runtime layout. A preliminary smoke run
  was executed and then its `.agentic-os/` was removed so the final captured
  run starts from scratch.
- **D-P7.2 — `python` vs `python3`.** This WSL environment ships no `python`
  shim. The smoke commands are run exactly as written after defining a
  session-local shell function `python() { python3 "$@"; }` (Python 3.12.3);
  no global config was touched.
- **D-P7.2b — Git-anchor happy path verified manually.** Complementing
  D-P4.1: in a throwaway sandbox (session scratchpad, outside this repo, since
  the test suite must not create git repos), `run start` against a git repo
  with one commit — and a space in its path — recorded `anchor_commit` equal
  to `git rev-parse HEAD` exactly. Sandbox deleted afterwards.
- **D-P7.3 — Adversarial review pass.** Before the final gate captures, the
  build was reviewed by independent reviewers (one per spec dimension: hard
  constraints, DB rules, CLI contract, pack spec, mirror+doctor, self-review
  items, tests walk, structure/docs), each finding then adversarially
  verified. Confirmed findings and their fixes are recorded below as they
  land.

- **D-P7.4 — Review findings fixed (7 confirmed).** (1) [major] secret-scan
  credential-assignment regex now allows an optional quote between keyword and
  separator, catching JSON/dict/YAML quoted keys (`{"password": "…"}`);
  (2) [major] CONVENTIONS.md no longer contains a literal `[[T-0001]]`
  example, which dangled and failed doctor on a fresh workspace; (3) CR bytes
  in user-supplied text are normalized to LF at the single file-writing choke
  point in utils (ledger keeps the raw text; generated files honor the
  LF-only constraint); (4) project-scoped decision notes now link back to the
  same tasks whose notes link them (bidirectional wikilinks); (5) doctor
  reports a non-UTF-8 vault note as a failed check instead of crashing with
  exit 2; (6) `log ""` now rejects the malformed empty id (identity check on
  the argparse default instead of truthiness); (7) db.get_meta only swallows
  the "no such table" OperationalError, so real I/O/lock failures surface as
  internal errors. Each fix has a regression test; suite: 87 green.
- **D-P7.5 — Review findings refuted (4, accepted with two courtesy edits).**
  Wikilink-shaped user titles breaking doctor (not a contract violation —
  noted as a known limitation); TestIds/TestSecretScan lacking tempdirs (pure
  functions, no FS access); README mentioning `git status --short` the code
  never runs (reworded anyway); connection not closed on the schema-mismatch
  error path (harmless, closed anyway).

## P4–P6 decisions

- **D-P4.1 — Git anchor happy path not unit-tested.** Testing anchor capture
  would require creating git repos (write operations) from the test suite;
  the suite tests the degraded path only (no repo → anchor NULL + journaled
  note), which is also what this repo exercises (it has no commits yet). The
  subprocess policy itself (list-form args, timeout, read-only, graceful
  failure) is enforced in `ops._git_anchor`.
- **D-P4.2 — Gate P4 result.** 70 tests green (done-gate refusal with
  actionable message; evidence→done; double-done; override event pair;
  run lifecycle incl. double-end; file-evidence sha256; missing-file exit 1;
  enum/provenance rejections; the CLI-layer event-per-mutating-command sweep
  across all ten mutating commands with exact expected (entity, action)
  sequences and a total-count seal).
- **D-P5.1 — Frontmatter scalar quoting.** Values matching
  `[A-Za-z0-9][A-Za-z0-9._:/@+-]*` are written plain (covers ISO timestamps,
  slugs, enums, `agent:x`); anything else is JSON-quoted (valid YAML); empty →
  bare `key:` (spec's "assignee or empty").
- **D-P5.2 — Doctor tolerates Obsidian's own files.** Hidden entries (any
  path component starting with `.`, e.g. `.obsidian/` created when the user
  opens the vault) are ignored by containment/wikilink checks — they are the
  user's, not sync's.
- **D-P5.3 — Gate P5 result.** 76 tests green (tree-hash idempotency; 0
  rewrites on second sync; containment via full outside-the-mirror snapshot
  diff; bidirectional wikilinks; exact task-note frontmatter field order;
  title change regenerates without rename; sync emits no events per D-P0.6).
- **D-P6.1 — Doctor check set.** Six checks: DB exists · required folders ·
  Home.md exists · done⇒evidence-or-override · wikilinks resolve to generated
  notes (all `[[...]]` in generated notes are ours, so all are checked) ·
  mirror contains only generated AOS/ notes (fails on strays outside AOS/ or
  unrecognized files inside it).
- **D-P6.2 — Gate P6 result.** 81 tests green (clean demo passes all six;
  SQL-forced unevidenced done fails; CLI `--no-evidence` override passes;
  planted broken wikilink detected; stray vault files flagged while
  `.obsidian/` config is tolerated).

## P3 decisions

- **D-P3.1 — Pack file path collides across budgets by design.** The pack file
  is always `packs/T-XXXX-<target>.md`; rebuilding the same task+target with a
  different budget (different inputs_hash) creates a new `packs` row but
  overwrites the same file. The rows keep the history; the file shows the
  latest build. Weekend can version filenames if needed.
- **D-P3.2 — High-entropy detector thresholds.** Shannon entropy over
  40+ char `[A-Za-z0-9+/=]` runs: ≥ 3.0 bits/char for hex-only runs, ≥ 4.0
  otherwise, with a key/secret/token word within ±40 chars. Standard base64
  charset only — base64url (`-`,`_`) is excluded to avoid false positives on
  kebab-case paths/slugs.
- **D-P3.3 — Secret scan input set.** Dynamic content per section (title,
  spec, acceptance, project conventions, branch hint, repo path, decisions,
  memory, run summaries, handoff state). Static boilerplate authored in
  pack.py/render.py is not scanned (it is ours and credential-free); the
  WRITE-BACK and UNTRUSTED sections are fully static.
- **D-P3.4 — Gate P3 result.** 56 tests green (per-pattern scan units incl.
  benign negatives; section order; truncation priority chain at three budget
  levels with byte-budget assertions; protected sections under an impossible
  budget + warning; inputs_hash row reuse; byte-determinism; project-less and
  unknown-target refusals; CLI refusal never echoes the secret; no partial
  artifacts on refusal).

## P1–P2 decisions

- **D-P2.1 — Gate P1 result.** 24 tests green (ids round-trip/rejection incl.
  unicode-digit rejection; PRAGMAs; WAL; schema_version; FK enforcement; event
  invariant at ops layer; atomicity in both directions — failure before AND
  after the event insert).
- **D-P2.2 — Repo adapter files are generated.** `adapters/*/PROTOCOL.md` in
  the repo were written by running `render.adapter_templates()` once, so they
  are byte-identical to what `init` copies into `.agentic-os/adapters/`
  (single source of truth per D-P0.3).
- **D-P2.3 — `init` regenerates Home.md from live DB state** (same renderer
  sync uses), so re-init after data exists shows correct data and stays
  byte-stable. CONVENTIONS.md and adapter templates are static and rewritten
  only when content differs.
- **D-P2.4 — Lazy imports for later-phase modules** (`pack`, `doctor`) happen
  inside the `_ledger()` context so pre-init invocations correctly exit 1
  ("Not initialized…") for every command. (Caught by a P2 test that saw
  exit 2.)
- **D-P2.5 — argparse usage errors exit 1** via an ArgumentParser subclass
  whose error() raises AosError (per D-P0.9); `--help` still exits 0 via
  SystemExit.
- **D-P2.6 — Gate P2 result.** 40 tests green (init layout/idempotency/LF
  bytes; pre-init guard on six commands; project idempotency; T-0001 format;
  malformed-ID exit codes at the CLI; JSON contracts for task list/show,
  status, log incl. filters).

## P8 decisions (post-review amendments)

- **D-P8.1 — Task status `active` renamed to `in_progress`.** The canonical
  task status vocabulary is now `inbox | ready | in_progress | done`, and
  `run start` sets its task `in_progress` (event payload
  `{"to": "in_progress"}`). What changed: `models.TASK_STATUSES`, the
  `run start` transition in `ops.py`, the tests pinning that transition (plus
  two new regression tests: one pins `TASK_STATUSES` exactly, one proves at
  the CLI layer that `run start` → `in_progress`), the CLI status column
  width, and the contract's enum/transition lines — code and contract move
  together. Why: `active` was ambiguous — it also names the project status
  (`projects.status` schema default `'active'`), so one word carried two
  unrelated meanings; after the rename, `active` is exclusively a project
  status. The pre-rename code was NOT a bug — it faithfully implemented the
  contract's original enum. The canonical naming was decided during
  pre-commit review, and adopts the research report's task-status vocabulary
  (its schema uses `in_progress` for a task being worked; Night-1 keeps its
  four-status subset). This decision supersedes the contract's original enum
  line (`inbox | ready | active | done`) in
  `agentic-os-night1-build-prompt.md`; the amended lines there are marked
  "(amended post-review, see D-P8.1)". Earlier entries in this file that say
  `active` for a task status (D-P0.5, D-P0.13, D-P0.14) are historical
  records written under the old vocabulary and are not rewritten; read
  `active` there as `in_progress`. The events ledger is append-only:
  historical payloads containing `"active"` are immutable audit records and
  were not touched. Live data was checked: the runtime DB had zero task rows
  with status `active` (the only task is `done`), so no data migration was
  needed or performed.

## U-M1 decisions (migration kit, T-0011)

Contract: `agentic-os-v0.2-u-m1-migration-contract.md`. U-M1 ships the
migration framework and **zero production migrations**. Appended without
rewriting prior entries.

- **D-v0.2.30 — The migration kit ships before the first migration.**
  `agentic_os/migrations.py` lands with `MIGRATIONS = ()` and
  `LATEST_VERSION == 1`, unchanged from `db.SCHEMA_VERSION`. Why: a schema
  change and the machinery to survive it are two different risks, and
  landing them together means the first migration is also the first test of
  every guarantee protecting it. U-M2 (memory v2) is blocked until U-M1
  merges, and adds exactly one step to the registry plus the matching
  `SCHEMA_VERSION` bump.

- **D-v0.2.31 — `LATEST_VERSION` is derived, never re-declared.**
  `LATEST_VERSION = int(db.SCHEMA_VERSION)`. A second literal would let the
  registry and the schema drift apart — a build could then support a version
  it cannot write, or write one it will not migrate. A guard test pins both
  the derivation and today's values (`1`, `()`), so raising either is a
  deliberate, visible act.

- **D-v0.2.32 — The version lives in `meta.schema_version`, and U-M1 did not
  move it.** The task brief called for a `schema_version` *table*; no such
  table exists — the version is one TEXT row in the generic `meta` key/value
  table, written by `ops.initialize()`. Introducing a table would itself be
  a schema change, which is precisely what U-M1 must not do. The brief's
  refusal cases were mapped onto the real storage (contract M1.1). The
  reader fetches ALL matching rows rather than `LIMIT 1`, so a `meta` table
  rebuilt without its primary key cannot smuggle an ambiguous version past
  the check.

- **D-v0.2.33 — Version parsing is canonical-strict.** A value parses only
  if `value == str(int(value))` and is non-negative: `"1"` yes; `"01"`,
  `" 1"`, `"+1"`, `"1.0"`, `"1_0"`, `"0x1"` no. Why: `int()` alone accepts
  the whole second list, which turns a corrupted cell into a plausible
  version and then migrates from the wrong place. Refusing is cheap;
  migrating from a misread version is unrecoverable.

- **D-v0.2.34 — `migrate` reads the ledger itself instead of `db.open_db()`.**
  `open_db` refuses any version != `SCHEMA_VERSION`, so a database *pending
  migration* — by definition at a lower version — cannot be opened through
  it. The version gate is the door migration must walk through. The gate is
  NOT relaxed for anyone else: `db.open_db` is untouched, every normal
  command still refuses exactly as before, and a test pins that. This is the
  mechanism behind "normal commands never auto-migrate": migration lives
  behind one explicit command and nothing else calls it.

- **D-v0.2.35 — `status`/`plan` read through `PRAGMA query_only=ON`, not URI
  `mode=ro`.** Measured, not assumed (contract M1.3): a `mode=ro` open of a
  WAL database creates `-shm`/`-wal` and **cannot remove them on close**,
  leaving lock artifacts behind forever; a plain read-write open checkpoints
  a dirty `-wal` on close, changing `aos.db`'s bytes. A read-write handle
  with `query_only=ON` does neither — SQLite itself rejects writes, reads
  still resolve through the `-wal` (no stale version), close does not
  checkpoint, and a quiescent workspace is left exactly as found.
  `immutable=1` was rejected outright: it would ignore the `-wal` and return
  a stale version — the exact hazard the stale-state rules exist to prevent.
  It remains correct in `backup.py`, where the file genuinely is immutable.

- **D-v0.2.36 — The write lock is held on one connection; the snapshot is
  sourced from a second.** `conn.backup(dest)` **hangs forever** when `conn`
  holds its own open `BEGIN IMMEDIATE`: `backup_step` returns `SQLITE_BUSY`
  against the connection's own write transaction and CPython retries on an
  unbounded sleep loop. So the literal reading of "lock, then snapshot"
  deadlocks. Instead the lock holder stays open while a second reader
  connection sources the snapshot — under WAL a reader is not blocked, and
  because the holder has written nothing it observes exactly the committed
  pre-migration state. This is *stronger* than releasing the lock to
  snapshot and re-taking it: no writer can commit between the snapshot and
  the first step, so the snapshot is provably the pre-migration state.

- **D-v0.2.37 — The pre-migration snapshot emits no `backup_create` event.**
  Emitting one requires a commit, which would release the write lock taken
  moments earlier and reopen the race it exists to close. `backup.py` was
  split instead: `write_backup_pair()` (files + manifest, no event) is the
  eventless half, and `create_backup()` is now that plus the existing event —
  `backup create` behavior is byte-identical to baseline. The snapshot's
  identity is recorded inside the `system/migrate` event, committed
  atomically with the step it protects. This extends U-C2's own rule (a
  backup never contains its own event) rather than contradicting it. A
  migration that fails before any step commits leaves a verified snapshot
  with no event referencing it; that is the safe outcome, and the failure
  message names the file.

- **D-v0.2.38 — `verify_backup` gained `expected_schema_version`.**
  It previously hard-failed unless a backup's version equalled
  `db.SCHEMA_VERSION`. The moment U-M2 ships (`SCHEMA_VERSION = "2"`), a
  *correct* pre-migration snapshot of a v1 database would fail that check
  and `migrate apply` would refuse to proceed — the framework would deadlock
  on the first real migration it was built for. The snapshot is now verified
  against the version it was actually taken at. Default `None` keeps the
  current meaning ("can this build use this backup?") and the current
  diagnostic string exactly, so U-C2 is unchanged. Today `current ==
  SCHEMA_VERSION == "1"`, so this is a no-op in production and is proved by
  direct test — it is not dead code, it is the one line that makes U-M2
  possible.

- **D-v0.2.39 — A no-op apply never opens the database read-write.** With
  nothing pending, `apply` returns after the `query_only` pre-flight. Why:
  "not one byte changed" should be true by construction, not by being
  careful with a handle that could write. A test spies on `db.connect` and
  pins exactly one (read-only) open.

- **D-v0.2.40 — Rollback across committed steps is restore, never
  automatic.** A failed step rolls back completely (its schema change,
  version bump, and event die together) and no later step runs. If an
  earlier step already committed, the database is reported PARTIALLY
  ADVANCED — a real, consistent state — with the exact `backup restore`
  command for the pre-migration snapshot. No automatic destructive rollback
  is attempted: un-applying a committed schema change programmatically is
  guesswork, and doing it automatically would silently bypass the snapshot
  taken to protect the user. A corrected retry resumes from the version
  actually committed and never replays completed steps.

- **D-v0.2.41 — Migration diagnostics print an exception's class, never its
  text.** A step body's `str(exc)` can embed SQL and row values; the
  diagnostic carries only the failed transition, the safe migration id, the
  exception class name, and the snapshot's relative path. Likewise the
  `system/migrate` payload carries exactly `{from, to, migration_id,
  snapshot}` with `snapshot` **relative** to the workspace — never an
  absolute, user-identifying path — and still passes through
  `events.emit`'s `secretscan.redact_tree` choke point (U-C3).

- **D-v0.2.42 — A malformed version is a database value, so it is redacted
  before it is quoted.** Found by a test, not by review: the first draft
  echoed the raw value (`schema_version 'sk-live-…' is not an integer`),
  which would print a secret-shaped cell straight to the terminal. Malformed
  versions now go through `secretscan.redact_tree` and are length-bounded,
  so a corrupted megabyte-long cell cannot become the error message either.

- **D-v0.2.43 — The v1 fixture is a builder, not a committed `.db`.**
  `tests/fixtures/v1_workspace.py` builds a real historical v1 workspace
  through production CLI commands only — never raw INSERTs — so it cannot
  drift from what v1 code actually writes, and it carries representative
  rows in every table (all four task statuses, runs, packs, evidence,
  decisions, handoffs, memory, agents, 20 events). A committed binary would
  be unstable across sqlite versions and page layouts, would bake in
  wall-clock timestamps from `utils.utc_now_iso()`, and would sit in the
  tree as exactly the kind of file the packaging allowlist exists to keep
  out of `aos.pyz`.

- **D-v0.2.44 — Synthetic registries are injectable, and test-only.**
  `plan_migrations`/`apply_migrations` accept `registry` + `latest` so tests
  can prove v1→v2 and multi-step behavior without a production schema
  change. Production callers pass neither, so the empty registry always
  applies; the CLI never threads them through. Synthetic steps must never
  become production migrations — D-v0.2.30's guard test is what enforces it.

- **D-v0.2.45 — The version `UPDATE` asserts it matched exactly one row.**
  An `UPDATE` matching zero rows succeeds silently in SQLite. A step whose
  own body removed or duplicated the `meta.schema_version` row would then
  commit a `system/migrate` event announcing a bump that never happened, and
  the ledger would lie about its own shape — the one thing the version row
  exists to prevent. The step fails and rolls back instead. Unreachable
  today (`read_schema_version` runs immediately before, in the same
  transaction); the assertion is what keeps it unreachable once real
  migrations exist.

- **D-v0.2.46 — One documented deviation from the one-line error rule.**
  `cli.py`'s contract is "errors are ONE actionable line on stderr", and
  every other `AosError` in the tree obeys it — including every other
  migration refusal. The PARTIALLY ADVANCED message is the single exception:
  it carries the state explanation plus a copy-pasteable `backup restore …
  --to …` command. Folding a command the user must run at the worst possible
  moment into a prose line would make the error that most needs clarity the
  hardest to act on. The rule's intent (no tracebacks, no walls of text for
  ordinary failures) holds: the message is bounded, fixed-shape, and carries
  no SQL, row values, or secrets.

- **D-v0.2.51 — The runtime power mode lives in an operational sidecar, not
  the schema or `meta`.** `.agentic-os/power.json` is a small file beside the
  ledger, deliberately outside it. Recovery control must be reachable when the
  database is unopenable, version-mismatched, or corrupt — that is precisely
  when a human reaches for `power set recovery`. Storing the mode in `meta`
  would make the control depend on the very thing it exists to recover:
  `db.open_db` refuses any `schema_version` other than the build's, so a
  version-mismatched database would lock the human out of the escape hatch. No
  `power` command calls `open_db`, no schema version changed, and no migration
  was registered.

- **D-v0.2.52 — A missing `power.json` means `standard`, and reading it never
  creates it.** Absence is a valid, expected state, not an error and not a
  first-run initialization step. `status`, `suggest`, `doctor`, and every other
  read-only command leave the workspace byte-identical; only `power set`
  creates or replaces the file. The alternative — writing a default on first
  read — would make every read-only command a writer, and would silently take
  a position (`configured standard`) the human never took.

- **D-v0.2.53 — Command classification is an explicit allowlist, walked and
  enforced by a test.** Every CLI leaf is classified `read_only`,
  `derived_write`, `recovery_safe`, or `authoritative_write` in one table in
  `power.py`, keyed by its argparse path. Mutability is never inferred from a
  command's name or help prose — `backup create` sounds read-ish and writes an
  event; `review build` sounds derived and is. A test walks the LIVE argparse
  tree and fails on any unclassified leaf and on any stale entry, so a new
  command cannot inherit a permissive default by being forgotten. An
  unclassified path fails closed to `authoritative_write` at runtime.

- **D-v0.2.54 — Suggestions never auto-apply.** `power suggest` prints advice
  and exits; it never writes `power.json`, and no command switches modes on its
  own. The degradation matrix reports `auto-switch: no` for all four modes, by
  construction. A system that quietly downgraded itself into `recovery`, or
  quietly left it, would make the mode a thing that happens to the human rather
  than a thing the human decides — and leaving `recovery` is exactly the
  decision that must not be automatic.

- **D-v0.2.55 — Recovery is fail-closed for authoritative and derived change.**
  Only `read_only` and `recovery_safe` commands run. The refusal fires in
  `power.dispatch` BEFORE `args.func`, so stdout stays empty and no partial
  mutation is possible; it names the command path and the mode, and echoes no
  payload, row, secret, path, or exception text. Entering recovery works while
  doctor has hard failures (and while the database cannot be opened at all);
  leaving it requires every hard check to pass. Warn-only checks never gate a
  transition — a warning is not a reason to trap someone in recovery.

- **D-v0.2.56 — Deep verifies around authoritative writes and never rolls
  back.** Before each authoritative ledger write, a bounded read-only preflight
  runs `PRAGMA integrity_check` and the existing U-C3 secret sweep through the
  same primitives doctor uses; a hard failure refuses the write before anything
  is written. After a successful write the same checks re-run, and on failure
  the command reports — honestly — that it ALREADY COMMITTED and that
  verification failed, recommends recovery, and exits 1. It never claims a
  rollback and never performs one: automatically undoing a committed, journaled
  write is the opposite of what an append-only system of record is for.
  Diagnostics name check names and counts only; `doctor` remains the place that
  shows the (already bounded, already value-free) detail.

- **D-v0.2.57 — No model calls, no host-resource heuristics.** The suggestion
  is a fixed four-step priority over signals the system already computes:
  hard doctor failure → `recovery`; warning → `deep`; active runs → `standard`;
  clean and idle → `eco`. No LLM call, no scoring model, no natural-language
  heuristic over ledger content, no CPU/RAM/battery probing, no environment
  telemetry. Identical ledger state yields an identical suggestion, and the
  output carries a fixed signal phrase plus a bounded count — never a title,
  summary, ref, claim, path, or secret. "Power mode" here means local execution
  policy; it never chooses a model or starts anything.

- **D-v0.2.58 — U-E1 pack effort tiers stay separate and deferred.** Context
  packs keep their own `--for` / `--budget-kb` knobs. Runtime power modes govern
  CLI execution policy for a workspace; pack effort tiers govern what goes into
  one artifact. Fusing the two vocabularies because both say "power" would tie
  an unrelated future decision to this one.

- **D-v0.2.59 — `power set` emits no ledger event.** Every other mutation in
  this tree journals one. This cannot: it must work when the database is
  unopenable, which is exactly when `recovery` is set — emitting an event would
  reintroduce the dependency D-v0.2.51 exists to remove. The cost is real and
  accepted: mode changes have no audit trail. `doctor` and `power status` report
  the CURRENT mode and whether it was configured, so the state is always
  visible even though its history is not.

- **D-v0.2.60 — `backup create` and `snapshot` are blocked in recovery.** Both
  write their file and then emit a ledger audit event inside `db.transaction`,
  so both mutate the live database and fail the "reads without mutating" test
  that would have made them recovery-safe. `backup verify` and `backup restore`
  remain available — they never touch the live ledger, and restore writes a
  distinct NEW path (U-C2). `backup.write_backup_pair()` is eventless but has
  no CLI surface; exposing one to soften this would be scope creep, and the
  honest answer is that a recovery-mode backup is not currently available.

- **D-v0.2.61 — Eco defers exactly one site, and none was invented.** An audit
  of every command path found one piece of implicit, optional derived work in
  the baseline: `init` re-heals the Obsidian mirror on an ALREADY-initialized
  workspace while reporting "nothing to do". Eco defers that and says so;
  `sync` regenerates it. Everything else the mirror/review/pack code does is
  explicitly requested by the human, and a freshly created workspace always
  heals (a new workspace with no mirror is not usable). Inventing automatic
  refresh work purely so eco could visibly differ from standard would have made
  the system do MORE by default in order to advertise doing less.

- **D-v0.2.62 — A malformed power state fails closed for writers and open for
  readers.** A power state that does not parse means the mode is UNKNOWN, and
  an unknown mode could be hiding a configured `recovery` — so
  `authoritative_write` and `derived_write` commands refuse. `read_only` and
  `recovery_safe` commands proceed, because reporting the problem is how the
  human sees it: `doctor` FAILs its power line rather than crashing, and
  `power status` prints it. Nothing repairs the file automatically — silent
  repair would resolve an ambiguity in the writer's favor. The documented way
  out is manual: delete it (absence means `standard`) and re-set the mode.

- **D-v0.2.63 — No lock file; `os.replace` is the serialization point.**
  `power set MODE` is an absolute assignment, not a read-modify-write delta, so
  concurrent setters cannot interleave: each writes a complete, already-valid
  temp file and atomically renames it, and the result is always exactly one
  valid state. A lock file would add its own staleness, its own symlink
  surface, and its own recovery story to protect an operation that is already
  atomic. One bounded consequence is documented rather than papered over: an
  idempotent no-op reports the state it observed, and a concurrent set may land
  after it — the file is still one complete valid state.

## v0.3 — U-X1: WorkSpec and Result Envelope protocol spine

- **D-v0.3.1 — Agentic OS owns the initial protocol registry.** The registry
  ships in this repository, not in AICompany and not in a shared package. AOS is
  the system of record, and the protocol spine is part of that record. Consumers
  vendor it by digest later; nothing in U-X1 reaches across a repository
  boundary. Building the registry where the first consumer happens to live would
  have made the second consumer a fork.

- **D-v0.3.2 — The Python embedded definitions are canonical.** `aos.pyz` is one
  file with no data directory, so a registry that lived in `protocols/*.json`
  would make the zipapp non-functional the moment it left the checkout. The
  embedded definitions in `agentic_os/protocols.py` are the single source of
  truth, and `agentic_os/protocols.py` enters the archive through the existing
  U-P1 allowlist with no packaging change at all — the allowlist design working
  as intended.

- **D-v0.3.3 — Checked-in JSON artifacts are deterministic projections.**
  `protocols/` exists so the schemas are reviewable in a diff and vendorable by a
  future consumer. It is a projection, never a second editable source:
  `protocol verify-registry` and a focused test compare it byte-for-byte against
  the embedded definitions, and `verify_source_artifacts` additionally refuses a
  stray `.json` under `protocols/` that projects no embedded schema. Editing
  `protocols/` without editing the Python fails both.

- **D-v0.3.4 — No general-purpose JSON Schema claim.** The validator supports an
  explicit, small, enumerated subset, and every unsupported keyword is named. The
  registry lint refuses a schema that uses any of them, so the guarantee is
  structural rather than aspirational: the registry cannot drift into relying on
  a keyword the engine silently ignores. A partial implementation that quietly
  skips `oneOf` is worse than no claim at all, because it validates less than a
  reader believes it does.

- **D-v0.3.5 — No floats in protocol v1.** Floating point has no canonical
  decimal form that survives a round trip across languages, so a float field
  would make the content hash unstable by construction. Numbers are integers in
  the IEEE-754 safe range (±(2⁵³−1)) — the range that survives a consumer whose
  JSON parser has no integer type. Durations, budgets and sizes are integers in
  explicit units.

- **D-v0.3.6 — The content hash excludes exactly its own field.** The digest is
  computed over the canonical serialization of the document with the *top-level*
  `content_sha256` member removed and nothing else removed. A `content_sha256`
  nested inside a sub-object is ordinary body content and stays in. No recursive
  self-hashing, no placeholder value, no ordering dependence: what gets hashed
  never contains the hash.

- **D-v0.3.7 — Protocol validation is inert and read-only.** Validation parses
  bytes and compares them to a schema. It never executes, imports, evals,
  resolves, fetches, opens or stats anything an artifact *references*. A `sha256`
  inside a WorkSpec is a declared reference, and the validator does not go hash
  the file it names — hashing a path an untrusted artifact chose is a read
  primitive handed to the artifact's author. All five leaves are `read_only` and
  open no SQLite connection.

- **D-v0.3.8 — AICompany vendoring and cross-repository replay are deferred.** A
  Result Envelope is a report produced by a party whose claims are not yet
  trusted, not an instruction. Nothing in U-X1 marks a task done, ends a run,
  creates evidence or authorizes spend. Import and replay are a later bounded
  unit, and the honest place to draw that line is before the ledger, not inside
  it.

- **D-v0.3.9 — v1 reserves no extension object.** The unit's brief permitted one
  bounded extension object; v1 declines it. Every schema rejects unknown
  top-level fields with no exceptions. An extension object would be an
  unvalidated pocket inside a signed body — the one region of the document where
  "we bound everything" stops being true. Forward compatibility is bought by
  minting `/v2`, which the registry is already built to carry.

- **D-v0.3.10 — Existing vocabularies are reused exactly, or not at all.** The
  Result Envelope `outcome` enum IS `models.RUN_OUTCOMES` and evidence `kind` IS
  `models.EVIDENCE_KINDS` — asserted by test against the production tuples rather
  than copied, so the two cannot drift apart silently. Protocol-only concepts
  (data classification, permitted destinations, compensation state) get new
  closed vocabularies. No existing domain vocabulary is broadened.

- **D-v0.3.11 — Key ordering is by Unicode code point, and that is stated rather
  than dressed up as RFC 8785.** RFC 8785 sorts by UTF-16 code unit; the two
  orders differ for non-BMP keys. AOS sorts by code point because that is what
  Python's native string comparison already does, and hand-rolling a UTF-16
  re-implementation would be a correctness risk taken purely to earn a compliance
  badge this unit does not claim. The format is named `aos-canonical-json/v1`,
  and all four known divergences from RFC 8785 are written down.

- **D-v0.3.12 — Generation lives in `tools/`, never in the CLI.** The CLI is
  read-only by classification, so it cannot regenerate `protocols/`.
  `tools/gen_protocols.py` writes the projection (and verifies it by default,
  writing only with `--write`), mirroring the existing `tools/build_zipapp.py`
  convention. It is excluded from the zipapp for free, because `tools/` is not
  under the package allowlist.

- **D-v0.3.13 — Schema patterns anchor with `^…$` and are applied with
  `fullmatch`: a deliberate, narrow departure from D-v0.2.3.** The existing rule
  ("anchor with `\Z`, never `$`") exists because Python's `$` also matches
  *before* a trailing newline, so `^slug$` would accept `"proj\n"`. That hole is
  closed here by a different mechanism: `re.fullmatch` requires the pattern to
  consume the whole string, so `fullmatch(r"^abc$", "abc\n")` fails — `$` consumes
  nothing and the `\n` is left over. The reason to prefer `$` is that these
  patterns are *exported* in `protocols/*.schema.json` for future consumers, and
  `\Z` is not ECMA-262: a JavaScript-side validator would read it as a literal
  `Z` and silently enforce the wrong grammar. `^…$` means exactly fullmatch in
  ECMA-262. So: `$` in the artifact, `fullmatch` in the engine, D-v0.2.3's
  guarantee intact, and a focused test pinning the trailing-newline refusal.

- **D-v0.3.14 — The protocol id grammar is a strict narrowing of the ledger's
  parser, not a copy of it.** `ids.parse_id()` is deliberately lenient at the CLI
  boundary: it upper-cases the prefix and strips surrounding whitespace, so
  `t-0002`, `T-0002 ` and `\tT-0002\n` all mean task 2 to a human typing at a
  terminal. The protocol accepts only `T-0002`. Leniency is right for a human
  boundary and wrong for a wire format, where two spellings of one id are two
  idempotency keys, two correlation targets and two audit trails. Narrowing stays
  compatible (every id the protocol accepts, `parse_id` accepts identically);
  broadening would not have.

- **D-v0.3.15 — U-M2 is key/value claim storage, not a graph.** `kind` stays
  the closed claim type, `key` the stable claim key/subject, `value_md` the
  human-readable claim value. The temptation at a "typed memory" unit is to
  generalize into subject/predicate/object and call it future-proofing; that
  would rewrite every reader (packs, search, mirror, doctor) and every v1 row's
  meaning in the same breath as the first production migration. Two risky
  changes at once is how a migration eats a ledger. Graph relationships are
  U-M3, on top of a claim table that already carries curation, integrity and
  evidence.

- **D-v0.3.16 — Schema version 2 is the first production U-M1 migration, and
  U-M2 adds no migration machinery.** The registry stayed empty at U-M1 exactly
  so this step could be the first thing it carried. U-M2 supplies a
  `Migration.apply` callable and nothing else: validation, the write lock, the
  version re-read under it, the snapshot, its verification as v1, the version
  bump and the `system/migrate` event are all U-M1's, untouched. A schema change
  that brings its own safety net is a schema change whose safety net has never
  been tested.

- **D-v0.3.17 — Legacy curation is derived from what v1 already knew, never
  inferred from text.** A superseded row → `retired`; an expired row →
  `retired`; everything else → `live`; everything unpinned; no evidence links
  invented. The expiry test is the *existing* live predicate verbatim, so a row
  v1 already kept out of packs is exactly a row v2 calls retired — the
  migration changes what the ledger can express, not what it says. Guessing
  `proposed` or `contested` from a claim's wording would be inventing curation
  history no human performed.

- **D-v0.3.18 — Pinned never overrides lifecycle or safety; it is a sort key.**
  A pinned claim must still be live, unexpired and unsuperseded to be
  retrieved, and `pin` refuses anything that is not. The alternative — pin as
  "always include" — makes pinning a second, competing lifecycle that quietly
  outranks retirement, which is precisely the bug where an agent keeps being
  told a thing the human retired six months ago.

- **D-v0.3.19 — Evidence uses normalized links, not copied evidence text.**
  `memory_evidence` is two ids and a timestamp. Copying an evidence claim or
  ref into the link would duplicate content that can be edited on one side and
  not the other, and would put evidence text — the thing U-C3 works to keep out
  of derived surfaces — into a second table with its own privacy story. Links
  are also why the claim hash binds evidence by *id*: the claim commits to
  which evidence backs it, not to a snapshot of what that evidence said.

  One consequence, accepted deliberately: the pre-existing `memory/add` event
  keeps its `key` field. The blanket "events carry no key" rule is right for
  every event U-M2 adds (`pin`, `unpin`, `link_evidence` carry ids,
  transitions, counts and a hash prefix — nothing else), but removing `key`
  from `add` would break the U-C3 warn-on-write behavior this unit is required
  to preserve. That field is already governed: `events.emit` redacts every
  secret-shaped string through `secretscan.redact_tree`, and the U-C3 metadata
  records what was withheld.

- **D-v0.3.20 — Claim hashes reuse U-X1 canonicalization, with every stored
  text field bound as a SHA-256 digest rather than as raw text.** The structure
  is canonical JSON v1 (`protocols.serialize_canonical`); U-M2 defines no
  competing canonicalization. But the leaves are digests, for two measured
  reasons. First, U-X1 caps a canonical string at `MAX_STRING_CHARS` (8192) and
  `memory add --value` has never had a length limit — a real 20 KB pasted claim
  would be *refused by its own migration*, breaking the one guarantee the
  legacy mapping must keep. Relaxing the protocol bound to fit a database row
  would be modifying the protocol spine to suit its first consumer. Second, a
  damaged row must stay reportable: with digest leaves, no stored value of any
  length or shape can trip a bound, so `doctor` prints one bounded line instead
  of dying inside the serializer that was supposed to help it. `sha256(text)`
  binds the text exactly; the binding is Merkle-shaped, not weaker.

  The payload also binds `id` (so a valid hash cannot be transplanted onto
  another row) and `updated_at` (every write that touches it recomputes the
  hash anyway). Only `content_sha256` itself is excluded — what gets hashed
  never contains the hash (D-v0.3.6).

- **D-v0.3.21 — Normal retrieval includes live claims only; hashes are
  enforced at write time and audited by doctor, not re-verified on read.**
  Packs filter on lifecycle (`status='live'`, unexpired, unsuperseded) with
  plain SQL. Verifying hashes on the read path sounds stricter but buys a worse
  system: it either drops a claim silently (context vanishes with no
  explanation — the worst outcome available) or refuses the whole pack, letting
  one damaged row block every pack in the workspace. Instead, *every*
  authoritative write against an existing claim verifies the stored hash first
  and refuses on mismatch — so a tampered claim can never be laundered into a
  valid-looking one by a later pin or retire — and doctor reports the damage by
  id. Integrity is enforced where it can be acted on.

- **D-v0.3.22 — Status is curation; expiry is time. They are independent
  axes.** A live claim crosses its own `valid_until` with no write at all, and
  `--valid-until` accepts a past date, so "expired but not retired" is honestly
  reachable and doctor reports it as a WARNING, never a failure. A check that
  turns red because a day passed is a broken check. The same reasoning makes
  "pinned but ineligible" (pin, then retire) a warning: reachable, harmless,
  and worth saying out loud.

- **D-v0.3.23 — The 1 → 2 step rebuilds the memory table instead of
  `ALTER TABLE ADD COLUMN`.** `ADD COLUMN` cannot add `content_sha256 TEXT NOT
  NULL` without a non-NULL default, and a `DEFAULT ''` would leave every future
  insert able to store a hashless claim: a migrated database would be
  permanently weaker than a freshly initialized one, and the difference would
  be invisible until it mattered. A rebuild from the one shared DDL constant
  (`db.MEMORY_CLAIM_DDL`) makes a migrated table identical to a born-v2 table,
  and routes every mapped row through the new CHECK constraints — so the
  migration cannot commit a value the schema forbids.

- **D-v0.3.24 — U-M3 (graph) and U-M4 (curation workflow) remain deferred.**
  U-M2 ships the storage those units need — `proposed`/`contested`/
  `quarantined` are storable, evidence links are normalized, every claim is
  hashed — and none of their behavior: no approve, reject, contest, quarantine,
  automatic promotion, contradiction detection, distillation, or agent memory
  writer. Storage that anticipates a workflow is cheap; a workflow invented
  ahead of its unit is a design nobody reviewed.

## U-M3 — provenance, temporal, relationship and contradiction memory graph

Contract: `agentic-os-v0.3-u-m3-memory-graph-contract.md`. Schema version 3.

- **D-v0.3.31 — Sensitivity is a closed, ORDERED vocabulary:
  `public < internal < confidential < restricted`.** The order is not
  cosmetic; it is what "classification increases only" and "a source must not
  be more sensitive than the claim it backs" are expressed in. Both a CHECK
  constraint and the domain enum enforce membership, so neither a careless
  caller nor a direct SQL writer can invent a level.

- **D-v0.3.32 — Sensitivity defaults to `internal`, and `restricted` is the
  only level excluded from automatic context.** `public` is a deliberate act
  of publication, not something a claim falls into by omission. Public,
  internal and confidential claims keep exactly the pack, search and mirror
  behavior they had; restricted claims never enter a context pack, a search
  snippet, a generated summary or a mirror body. Administrative surfaces still
  LIST them — metadata only, never their key, value, source or evidence refs.
  This is a safe local baseline, not the U-S6 authorization system.

- **D-v0.3.33 — The exclusion lives in the eligibility predicate, not in the
  renderers.** `ops.claim_is_eligible` and `ops.memory_for_project` both learned
  about `restricted`, so `memory show`'s "retrieved: yes", the pin gate and the
  pack builder cannot disagree about who sees what. A filter added at the pack
  renderer would hold only for that renderer, and the next caller would
  reopen the hole without noticing. Pinning still never overrides sensitivity:
  it is ordering among eligible claims, and it always was.

- **D-v0.3.34 — A source row copies no text from what it references.** An
  `evidence` source carries an evidence id and nothing else about that row —
  not its claim, ref, sha or body. Every other kind carries an inert `locator`.
  A structural CHECK enforces the split at the storage boundary as well as in
  `ops`, so a row that copied a ref into `locator` cannot exist.

- **D-v0.3.35 — Contradictions are typed edges, not a second table and not a
  verdict.** A contradiction IS an active `contradicts` edge. There is no
  resolution column, no winner, and no truth decision anywhere in U-M3:
  `memory contradictions` reports that a human declared two claims to
  disagree, shows both claims' lifecycle and sensitivity, and stops. Nothing
  is ever inferred — not from keys, values, dates, sources or models. A tool
  that guessed here would be believed.

- **D-v0.3.36 — Graph relations are descriptive and trigger no workflow.**
  Adding a `contradicts` edge does not quarantine, retire, contest or reorder
  anything. `memory.superseded_by` remains the one lifecycle supersession
  mechanism and is deliberately NOT duplicated as a graph relation — two
  mechanisms for one truth is how a ledger starts disagreeing with itself.

- **D-v0.3.37 — Symmetric relations canonicalize their endpoints (lower id
  first).** `contradicts` and `related` are symmetric, so A↔B and B↔A are one
  logical edge; the endpoints are ordered before every lookup and insert, and
  a CHECK pins the canonical form in storage. A reverse duplicate therefore
  collides with the UNIQUE constraint instead of quietly becoming a second row
  for the same fact.

- **D-v0.3.38 — Every graph reference is inert.** No command follows a file
  locator, resolves a URL, executes a command string, reads an evidence ref,
  or opens an artifact path. They are strings the ledger agreed to remember.
  This is what keeps the graph inspection commands genuinely read-only rather
  than read-mostly.

- **D-v0.3.39 — SQLite graph records are canonical; graph engines are
  derived.** The three tables are ledger data with integrity hashes, not a
  disposable visual index. Any external graph engine, visualization or index
  is rebuildable from them and carries no truth of its own.

- **D-v0.3.40 — Traversal caps truncate deterministically and say so.**
  `memory graph` is bounded at depth 2, 64 nodes and 128 edges. It truncates
  rather than refusing — an inspector that gives up on a large graph is
  useless exactly when it matters — and reports `truncated`, because a silent
  stop reads as "that is the whole neighbourhood".

- **D-v0.3.41 — A shipped migration is history and gets frozen in place.**
  U-M2 wrote the 1→2 step against the shared `db.MEMORY_CLAIM_DDL` so a
  migrated table could not drift from a fresh one. That was right while v2 was
  current and stopped being right the moment v3 existed: a shared constant
  follows the schema FORWARD, so 1→2 would have built a v3-shaped table,
  stamped `schema_version = 2` on it, and hashed its claims under the v3
  payload — and U-M1's guarantee that a failure inside 2→3 leaves a valid v2
  database would have been false, because there would never have been one. The
  v2 DDL and the v2 claim-hash payload are now frozen copies in
  `migrations.py`. The cost is one duplication per schema version; each step
  now leaves a database that genuinely is what it says it is.

- **D-v0.3.42 — The 2→3 step rebuilds the memory table, and the migration
  connection runs with `foreign_keys=OFF` plus a `foreign_key_check` before
  every commit.** The rebuild is D-v0.3.23's reasoning applied again: building
  from the one fresh-v3 DDL constant is what makes a migrated table and a
  born-v3 table the same table. But `memory_evidence` now holds foreign keys
  into `memory`, so DROPping the old table is an instant violation.
  `PRAGMA foreign_keys=OFF` inside a transaction is a silent no-op, and
  `PRAGMA defer_foreign_keys=ON` looks like the subtler answer and is not one
  — it counts the violations the DROP causes and never decrements them when
  the RENAME puts the table back, so the COMMIT fails anyway (measured, not
  assumed). So the pragma is set before the transaction opens, and the
  compensating control is strictly broader than what was switched off: EVERY
  step, present and future, is followed by a `foreign_key_check` over the whole
  database inside its own transaction, before its commit. Per-statement
  enforcement would have refused the legal intermediate state; this refuses any
  illegal final one.

- **D-v0.3.43 — No provenance is invented during migration.** The three graph
  tables come out of 2→3 EMPTY, and every migrated claim becomes `internal` by
  constant, never by inspecting its text. A v2 claim has no recorded
  provenance; deriving one from `memory.source` or from linked evidence would
  put a guess into the ledger wearing the same clothes as a fact. Existing
  evidence links survive untouched — the step does not address that table at
  all.

- **D-v0.3.44 — Doctor's restricted-in-context check warns, never fails.** A
  pack built BEFORE a claim was classified restricted legitimately contains
  it: the operator did nothing wrong and no invariant was violated at the
  time. It is still a real leak on disk worth surfacing, and `pack build` /
  `sync` regenerate it away. Same rule as D-v0.3.22 — a check that turns red
  because history happened is a broken check.

- **D-v0.3.45 — No explicit indexes are added.** This schema has never carried
  a `CREATE INDEX`; every hot column is scanned. The graph tables follow that
  established design rather than introducing a new one: the UNIQUE constraints
  already provide the implicit indexes the traversal's outbound lookups use,
  the caps bound every traversal, and a personal ledger lacks the row count
  that would make this matter. Fewer objects also means fewer things the
  migration must replicate exactly — fresh/upgrade identity is preserved by
  construction rather than by vigilance.

- **D-v0.3.46 — Classification increases only; downgrades and authorization
  policy belong to U-S6.** `memory classify` raises a claim's sensitivity,
  treats same-state as a no-op that writes nothing and emits no event, and
  REFUSES to lower one. Reducing the protection on a claim is an authorization
  decision, and U-M3 ships no authorization system to answer it with.

- **D-v0.3.47 — U-M4 (workflow), U-M5 (retrieval evaluation) and U-M6
  (receipts) remain deferred.** U-M3 ships the graph those units need and none
  of their behavior: no proposal/approve/reject/contest, no automatic
  contradiction detection, no automatic source extraction, no interviews, no
  embeddings or vector retrieval, no graph ranking, no Context Hydration
  Receipts, and no agent-written memory. Packs do no graph expansion at all.
  Storage that anticipates a workflow is cheap; a workflow invented ahead of
  its unit is a design nobody reviewed.
