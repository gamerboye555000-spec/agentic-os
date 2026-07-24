# Agentic OS v0.4 — U-K1/U-T1: governed skill and tool foundations

Contract-freeze plus integrated implementation pass. Baseline
`224d2cd0b98766e52865f8b4752446adb71af850` (U-P2 delivery gate merged, schema
version 5, milestone `milestone/v0.4-u-p2-delivery-gate`). Branch
`v0.4-u-k1-u-t1-governed-foundations`. Decisions: D-v0.4.51 – D-v0.4.58.
Extends the U-X1 protocol spine (`agentic-os-v0.3-u-x1-protocol-spine-contract.md`)
and the U-A1 passport contract (`agentic-os-v0.4-u-a1-agent-passports-contract.md`);
it resolves the requirement strings U-A1 froze as "a stored string — U-A1
ships no resolver (deferred to U-K1/U-T1)".

The implementation and tests must mechanically agree with this document. A
sentence here that the code cannot demonstrate is a defect in one of the two.

## 0. Scope

### 0.1 In scope

- Two new inert protocol artifacts in the U-X1 registry:
  `beast.skill-manifest/v1` (U-K1) and `beast.tool-manifest/v1` (U-T1).
- Closed vocabularies for component lifecycle, skill evaluation state, tool
  side effects, compensation strategy, idempotency mode, cancellation mode,
  and recovery action, frozen in `agentic_os/protocols.py` beside the schemas
  that carry them.
- Deterministic in-memory skill/tool registries with closed rejection
  reasons: duplicate identity, malformed or wrong-schema document, missing
  dependency, unknown dependency version, and skill dependency cycle all
  refuse at build time (case-ambiguous identities are unrepresentable —
  the id pattern is lowercase-only).
- A deterministic implementation-binding registry: explicit in-code
  registration only, digest over the canonical binding record, fail-closed
  verification against the digest each manifest declares.
- A pure eligibility evaluator returning a typed decision
  (`allow | deny | needs_approval | unavailable | invalid`) with closed
  reason codes. Code computes the decision; no model output participates.
- A governed invocation protocol: validated execution context, single-attempt
  runner over verified in-process bindings, typed result envelope with a
  closed status vocabulary, deterministically derived `retryable`, truthful
  termination outcome, and a digest-only evidence record
  (`aos.governed-invocation-evidence/v1`) with optional hash chaining.
- A read-only projection resolving an agent passport's
  `skill_requirements` / `tool_requirements` strings against the registries.
- Focused tests (`tests/test_v04_governed_foundations.py`), regenerated
  `protocols/` projection, DECISIONS/README updates, and the three updated
  registry-count assertions in `tests/test_v03_protocol_spine.py` (the
  identity list, `len(REGISTRY)`, and the `protocol list` line count).

### 0.2 NOT in scope (mechanically absent, not merely discouraged)

- Atomic Agents, Claude Agent SDK, MCP, or any framework adapter; no
  provider, model, or network call; no subprocess sandbox; no remote
  cancellation transport; no dynamic import, plugin discovery, filesystem
  scan for manifests, package installation, or remote retrieval.
- No real side-effecting tool execution: the only executable bindings are
  safe in-process test callables registered explicitly in code.
- No persistence: no new table, no migration, no schema-version bump, no new
  ledger ID prefix, no doctor check, no event emission.
- No CLI addition: `aos protocol validate` / `verify-registry` / `digest`
  already cover the two new artifacts through the registry, so no new verbs
  and no `power.COMMAND_POLICY` change (§15).
- No retry executor: retries stay bounded declarations plus a derived
  `retryable` flag. The outer attempt loop is U-W1's.
- No production idempotency cache, no budget arithmetic, no token counting.
- No U-W1 WorkSpec orchestration, no U-A4 multi-agent expansion, no
  autonomous promotion, no semantic skill generation, no marketplace.

### 0.3 Untouched

`db.py`, `migrations.py`, `models.py`, `cli.py`, `power.py`, `doctor.py`,
`secretscan.py`, `catalog.py` and `agentic_os/catalog/*`, `hooks.py`,
`ingest.py`, `ops.py`, `routing.py`, `agent_handoffs.py`, `passports.py`,
all delivery-control files (`.github/workflows/ci.yml`,
`tools/verify_ci_workflow.py`, `tests/test_v04_delivery_gate.py`), and every
existing fixture. Existing artifacts remain valid without edits.

## 1. Decisions

- **D-v0.4.51** — manifests are inert U-X1 registry artifacts; the kernel
  stays framework-neutral. Atomic Agents: adapter candidate, not kernel.
- **D-v0.4.52** — descriptive metadata never grants authority; eligibility
  requires `required_capabilities ⊆ granted_capabilities` plus every other
  gate; decisions are typed and code-computed.
- **D-v0.4.53** — runtime-only foundation: no persistence, no CLI, no doctor
  change; schema version stays `"5"`.
- **D-v0.4.54** — implementation binding is an explicit, digest-verified
  in-code registration; unknown or mismatched bindings fail closed.
- **D-v0.4.55** — a deadline is not a cancellation; termination outcomes are
  a closed truth vocabulary and this unit produces only `not_started` and
  `completed`.
- **D-v0.4.56** — unsafe retry combinations are unrepresentable: a mutating
  tool with `max_attempts > 1` must declare an idempotency key requirement
  or a compensating action; `retryable` is derived, never asserted.
- **D-v0.4.57** — invocation evidence is digest-only: no raw inputs, outputs,
  idempotency references, or free text; optional chaining by record hash.
- **D-v0.4.58** — passport requirement resolution is a read-only projection;
  the passport schema, routing, and handoffs are unchanged.

## 2. Threat and failure model; trust boundary

Threats this unit must refuse mechanically:

- **Authority laundering**: a manifest that "declares" itself permitted,
  approved, budgeted, promoted, or bound to an implementation it does not
  match. Manifests carry requirements and declarations only; every grant
  lives in the execution context or an external policy input.
- **Descriptive influence**: display names, descriptions, and recovery notes
  steering policy. Only closed enum fields and pattern-bound identifiers
  participate in any decision.
- **Model-controlled governance**: a callable's return value overwriting
  status, retryability, termination, decision, or recovery fields. Envelope
  governance fields are computed by the runner; output data rides under
  `output` and is otherwise inert.
- **Ghost execution**: a manifest naming a module/command/URL and something
  importing or running it. Execution happens only through a registered
  binding whose canonical record digest equals the digest the manifest
  declares.
- **Deadline overclaim**: reporting `deadline_exceeded` as if work stopped.
  The result carries a separate truthful termination outcome.
- **Unsafe replay**: automatically retrying a mutating tool without an
  idempotency or compensation strategy.
- **Secret leakage**: evidence embedding raw inputs, outputs, or idempotency
  references. Evidence binds digests only.

Trust boundary: manifest documents, execution contexts, and binding records
are untrusted input and are validated fail-closed (unknown field, unknown
enum member, unknown capability shape, unknown policy/lifecycle state,
malformed binding, missing authority context all refuse). Registered Python
callables are trusted code supplied by the embedding test/process — this
unit governs *whether* they may run and *what is recorded*, not what
arbitrary Python can do; sandboxing is future work and is not claimed.

## 3. Canonical entities and closed vocabularies

New entities:

| Entity | Form | Home |
| --- | --- | --- |
| Skill manifest | `beast.skill-manifest/v1` artifact | U-X1 registry |
| Tool manifest | `beast.tool-manifest/v1` artifact | U-X1 registry |
| Component registry | frozen in-memory index | `governance.py` |
| Implementation binding | canonical record + explicit callable | `governance.py` |
| Execution context | validated canonical dict | `governance.py` |
| Governance decision | frozen dataclass | `governance.py` |
| Invocation result | frozen dataclass + canonical envelope | `governance.py` |
| Invocation evidence | canonical record `aos.governed-invocation-evidence/v1` | `governance.py` |
| Requirement resolution | frozen dataclass projection | `governance.py` |

Closed vocabularies frozen in `protocols.py` (schema-carried):

```text
COMPONENT_LIFECYCLES        = draft | active | deprecated | revoked
SKILL_EVALUATION_STATES     = unevaluated | candidate | promoted | rejected
TOOL_SIDE_EFFECTS           = pure | read_only | mutating
TOOL_COMPENSATION_STRATEGIES= not_applicable | none | compensating_action
TOOL_IDEMPOTENCY_MODES      = not_required | required_key
TOOL_CANCELLATION_MODES     = not_supported | cooperative
RECOVERY_ACTIONS            = none | retry_after_backoff | request_approval |
                              manual_intervention | invoke_compensation
COMPONENT_ID_PATTERN        = ^[a-z][a-z0-9._-]{1,63}$
```

Requirement refs (dependencies, `replaced_by`, registry resolution) reuse
the existing `REQUIREMENT_PATTERN` (slug, optional `/vN` pin) directly — no
new constant.

Closed vocabularies frozen in `governance.py` (runtime-only):

```text
GOVERNANCE_DECISIONS   = allow | deny | needs_approval | unavailable | invalid
GOVERNANCE_REASON_CODES (canonical order) =
  context_malformed, unknown_component, unknown_version,
  lifecycle_not_active, not_promoted, binding_unknown,
  binding_kind_mismatch, binding_digest_mismatch, dependency_blocked,
  missing_capability, agent_class_mismatch, approval_required
INVOCATION_STATUSES    = success | denied | invalid_input | deadline_exceeded |
                         transient_failure | permanent_failure |
                         recovery_required | dependency_blocked
TERMINATION_OUTCOMES   = not_started | completed | cooperative_cancelled |
                         subprocess_terminated |
                         remote_cancellation_requested | abandoned |
                         not_supported
BINDING_KINDS          = in_process | metadata
INVOCATION_ERROR_CODES (closed; see §10.4)
```

Reused exactly, never duplicated: `CAPABILITY_PATTERN`,
`REQUIREMENT_PATTERN`, `PROVENANCE_PATTERN`, `AGENT_PROVENANCE_METHODS`,
`AGENT_CLASSES`, `EVIDENCE_KINDS`, `DATA_CLASSIFICATIONS`, `OpaqueRef`,
`Timestamp`, `Sha256`, `Issuer`, `IDEMPOTENCY_KEY_PATTERN`,
`UUID_PATTERN`, `TRACE_ID_PATTERN`, `AOS_TASK_ID_PATTERN`, canonical JSON
v1, `content_sha256` self-excluding digest, and `utils.utc_now_iso()`
timestamps. `models.py` is deliberately untouched: every new vocabulary is
schema-adjacent and lives beside the schemas in `protocols.py`, or is
runtime-only and lives in `governance.py` (`models` cannot import
`protocols`, the D-v0.4.23 constraint).

## 4. `beast.skill-manifest/v1` (U-K1)

A reduced-envelope artifact (like the agent passport): required envelope
`schema, protocol_version, content_hash_alg, content_sha256, created_at,
issuer`; optional `expires_at, data_classification`. No task fields
(`aos_task_id`, `trace`, `idempotency_key`, `audience`, `scope`,
`permitted_destinations`) — a manifest is a declaration, not a message.

Body (required unless marked optional):

- `skill` — `COMPONENT_ID_PATTERN`; hash-bound into the body so a digest
  cannot be transplanted between skills.
- `component_version` — integer 1..9999 (the range `/vN` pins can name).
- `display_name` (1..128), `description` (1..2048) — display-only; nothing
  reads them for any decision.
- `lifecycle` — `COMPONENT_LIFECYCLES`.
- `evaluation` — `SKILL_EVALUATION_STATES`; promotion is recorded state,
  never inferred and never self-granted by prose.
- `io_contracts` — `{input_ref, output_ref}`, both required `OpaqueRef`
  declared references. Never resolved, fetched, or dereferenced here.
- `required_capabilities` — optional array (1..16) of `CAPABILITY_PATTERN`.
- `tool_dependencies`, `skill_dependencies` — optional arrays (1..16) of
  `REQUIREMENT_PATTERN` refs (`slug` or `slug/vN`).
- `agent_constraints` — optional `{agent_classes: [AGENT_CLASSES…]}` (1..4,
  unique): the passport classes permitted to invoke this skill.
- `limits` — optional `{max_input_bytes?, max_output_bytes?,
  max_context_tokens?}` (byte limits 1..999999999; `max_context_tokens`
  1..99999999, the passport's bound). Input/output limits are enforced at
  invocation (§10); `max_context_tokens` is declaration-only in this unit
  (no token counting exists).
- `budget` — optional `{max_task_seconds? (1..604800), max_cost_microusd?
  (0..1000000000000)}` — passport `limits` vocabulary reused. Declaration
  plus opaque `budget_ref` context only; no live budget protocol exists yet.
- `evidence_expectations` — optional `{evidence_kinds, min_evidence_count}`,
  exact passport/WorkSpec shape over `models.EVIDENCE_KINDS`.
- `binding` — required `{binding_id: COMPONENT_ID_PATTERN, binding_sha256:
  Sha256}`: the identity and canonical-record digest of the only
  implementation this manifest may execute through (§8).
- `replaced_by` — optional `REQUIREMENT_PATTERN`; permitted only when
  `lifecycle` is `deprecated` or `revoked` (cross-field, §6).
- `provenance` — required `{created_by: PROVENANCE_PATTERN, method:
  AGENT_PROVENANCE_METHODS}`. Source metadata; grants nothing.

## 5. `beast.tool-manifest/v1` (U-T1)

Same reduced envelope. Body (required unless marked optional):

- `tool`, `component_version`, `display_name`, `description`, `lifecycle`,
  `io_contracts`, `binding`, `provenance` — as §4 (no `evaluation` field:
  the evaluation ladder is skill vocabulary; tools gate on lifecycle).
- `side_effect` — required, `TOOL_SIDE_EFFECTS`.
- `compensation` — required `{strategy, ref?}`:
  `pure`/`read_only` ⇔ `strategy = not_applicable`; `mutating` ⇔ strategy in
  `none | compensating_action`; `ref` (OpaqueRef) present ⇔ strategy is
  `compensating_action`. Cross-field enforced (§6).
- `idempotency` — required, `TOOL_IDEMPOTENCY_MODES`. `required_key` means
  an invocation may not be auto-retried without an idempotency reference in
  its execution context.
- `cancellation` — required, `TOOL_CANCELLATION_MODES`. This unit ships no
  cancellation transport; the field is the declared mode future adapters
  must honor.
- `retry` — required `{max_attempts: 1..10}`. Bounded by schema; an
  unbounded retry is unrepresentable. Hidden framework retries are not
  trusted, not counted, and not representable: Agentic OS owns the outer
  attempt budget (§11).
- `approvals_required` — optional array (1..16) of strings (1..128), the
  exact passport field shape: declared actions needing human approval.
  There is no field that can claim approval was granted.
- `required_capabilities`, `evidence_expectations`, `replaced_by` — as §4.
- `recovery` — required `{action: RECOVERY_ACTIONS, note?: string 1..512}`.
  `note` is display-only prose; nothing parses or executes it (§12).

Retry-safety invariant (cross-field, §6): `side_effect = mutating` with
`retry.max_attempts > 1` requires `idempotency = required_key` or
`compensation.strategy = compensating_action`; otherwise the document
refuses validation.

## 6. Serialization, digests, and cross-field rules

Both manifests are canonical JSON v1 artifacts under every U-X1 rule:
sorted keys, UTF-8, no floats, bounded sizes, unknown fields refused,
`content_sha256` = sha256 over the canonical body with only the top-level
hash member removed, digest independent of insertion order, round-trip
stable. The digest covers `schema`, `protocol_version`, the component id,
and `component_version` because they are body fields — schema and component
version are inside the hash by construction.

Cross-field rules live in `protocols._check_semantics`, presence-guarded so
no existing schema's behavior changes, with new closed reason codes:

```text
replacement_lifecycle_mismatch  replaced_by outside deprecated/revoked
compensation_side_effect_mismatch  strategy inconsistent with side_effect
compensation_ref_mismatch       ref presence ⇄ compensating_action broken
unsafe_retry_policy             mutating + max_attempts>1 + no idempotency
                                key requirement + no compensating action
recovery_compensation_mismatch  invoke_compensation recovery without a
                                declared compensating action
self_dependency                 a skill depending on its own id
```

`aos protocol validate` therefore validates both new artifacts end-to-end
with no new CLI. JSON-Schema use stays inside the U-X1 local registry
subset; there is no external schema resolution.

## 7. Registries and version resolution

`governance.build_tool_registry(documents)` and
`governance.build_skill_registry(documents, tool_registry)` return frozen
registries. Build refuses, via `GovernanceError` (closed reason + `where`
naming only validated identifiers, `KeyError` on an undeclared code — the
`CatalogError` idiom):

- `wrong_schema` — a document of any other identity;
- `duplicate_component` — same `(id, component_version)` twice. Ambiguity
  by case is unrepresentable rather than checked: the component id pattern
  is lowercase-only ASCII, so two ids differing only by case cannot both
  validate;
- `missing_dependency` — a declared dependency slug absent from the
  relevant registry (tools resolve against the tool registry; skills
  against tools and skills);
- `unknown_dependency_version` — a `/vN` pin naming no registered version;
- `dependency_cycle` — a cycle in resolved skill→skill dependencies
  (self-dependency is already refused at document level).

Version resolution is the established deterministic rule (passport
`current`, catalog `latest`): an exact `slug/vN` pin resolves that version
or refuses; a bare `slug` resolves the highest registered
`component_version`. Resolution never consults lifecycle — a deprecated
latest resolves and is then *denied* by eligibility, so deprecation is
visible instead of silently skipped. Registries are inert indexes: nothing
is imported, opened, or executed at build time. Each entry holds a
canonical-round-trip SNAPSHOT of its validated document — the entry aliases
nothing the caller passed in, so mutating the document the caller passed into
the build can neither alter a decision nor stale an attested digest. Untrusted
documents are snapshotted on the way in and never reach a stored entry; the
snapshot an entry exposes for reading is not re-verified on read (unlike a
binding record, whose digest §8 recomputes at every evaluation so even a
returned reference cannot desync it), so an in-process caller must treat a
document it reads back from an entry as read-only.

## 8. Implementation binding

A binding is a canonical record plus, for `in_process` kind, an explicitly
registered Python callable:

```text
{schema: "aos.implementation-binding/v1", binding_id, kind,
 component_kind: skill|tool, component_id, component_version, config: {…}}
```

`binding_digest(record)` = sha256 over `serialize_canonical(record)`. A
`BindingRegistry` registers records in code (`register(record,
callable=None)`); `metadata` kind carries no callable and can never
execute. Refusals: duplicate `binding_id`, malformed record, callable
supplied for `metadata`, callable missing for `in_process`, and any
non-canonical `config`. Registration stores a canonical-round-trip
snapshot of the record, and verification RECOMPUTES the stored record's
digest at every evaluation — no cache — so no retained or returned
reference can desync a record from the digest a manifest declares. Lookups
are live by design: registering a binding later makes a
previously-`binding_unknown` manifest eligible on the next evaluation.

Verification at eligibility time, fail-closed in this order: the manifest's
`binding.binding_id` must be registered (`binding_unknown`), the record
must bind the same component kind/id/version (`binding_kind_mismatch`),
and the record's recomputed digest must equal the manifest's declared
`binding_sha256` (`binding_digest_mismatch`). There is no import path, no
module string, no shell string, no URL anywhere in the record vocabulary —
naming code is unrepresentable, so "manifest names it, something runs it"
cannot happen.

## 9. Authority separation and the eligibility decision

The conceptual split is literal in the code:

```text
manifest.required_capabilities      (declaration, untrusted)
execution_context.granted_capabilities  (external grant)
external policy input               (approval_ref/policy_ref/budget_ref,
                                     caller passport facts)
deterministic policy decision       (governance.evaluate_eligibility)
```

`evaluate_eligibility(kind, ref, registries, bindings, context)` is pure:
same inputs, same `GovernanceDecision(decision, reasons, component,
diagnostics)`. All gates are evaluated; all applicable reason codes are
collected in canonical order; the decision is the highest-precedence
failing class:

```text
invalid  >  deny  >  needs_approval  >  unavailable  >  allow
```

- `invalid` — malformed context (`context_malformed`).
- `deny` — `required_capabilities ⊄ granted_capabilities`
  (`missing_capability`), or `agent_constraints.agent_classes` declared and
  the caller's class is absent or not permitted (`agent_class_mismatch`).
  Grants are exact set membership over pattern-valid capability strings; a
  malformed grant string is `context_malformed`, never a partial match.
- `needs_approval` — `approvals_required` declared non-empty and the
  context carries no `approval_ref` (`approval_required`). An
  `approval_ref` is an opaque reference to a record another system owns;
  this unit never fabricates or verifies approval truth, and a manifest
  cannot fabricate it either.
- `unavailable` — `unknown_component`, `unknown_version`,
  `lifecycle_not_active` (anything but `active`), `not_promoted` (skills:
  anything but `promoted`), `binding_unknown`, `binding_kind_mismatch`,
  `binding_digest_mismatch`, or `dependency_blocked` (a dependency resolves
  but is itself inactive/unpromoted/unverified — evaluated recursively,
  depth-bounded by registry acyclicity).
- `allow` — every gate passed. Exactly the declared requirements under an
  exact grant is allowed when all other gates pass.

The evaluator returns a typed decision, never a bare Boolean, and no model
output is an input to it.

## 10. Execution protocol

### 10.1 Execution context

`validate_execution_context(raw) -> dict` (fail-closed, unknown keys
refused, every value pattern/enum-checked):

```text
invocation_id  (UUID, required)      principal (PROVENANCE_PATTERN, required)
granted_capabilities ([CAPABILITY_PATTERN], required, may be empty)
max_attempts (1..10, required)       attempt (1..max_attempts, required)
caller_agent? (agent-name pattern)   caller_agent_class? (AGENT_CLASSES)
caller_passport_sha256? (Sha256)     aos_task_id? (T-…)
deadline_at? (Timestamp)             idempotency_ref? (IDEMPOTENCY_KEY_PATTERN)
approval_ref? / policy_ref? / budget_ref? (OpaqueRef)
trace? {trace_id, correlation_id, causation_id?} (U-X1 Trace shape)
```

### 10.2 Invocation envelope

`invocation_envelope(...)` binds manifest identity and version, manifest
`content_sha256`, binding id and digest, the canonical input value's
sha256, the full context, and the attempt — then self-digests
(`content_sha256`, U-X1 rule). It is a record of what was asked, built by
code.

### 10.3 Runner

`invoke(kind, ref, registries, bindings, context, input_value, *,
now=utils.utc_now_iso)` executes at most one attempt:

1. context validation — refusal returns an `invalid_input` result
   (`context_malformed`), termination `not_started`;
2. eligibility (§9) — mapped by decision tier FIRST, so an authority
   denial is never reported under an availability status:
   `needs_approval` → `denied`/`approval_required`; `deny` →
   `denied`/`governance_denied`; then, for `unavailable`, dependency
   reasons → `dependency_blocked` and the rest → `denied`; `invalid` →
   `invalid_input`. Reason codes ride in the result. An `allow` over a
   `metadata` binding is refused here, before any input gate (`denied`,
   reason `binding_kind_mismatch`) — a non-executable binding has no
   input worth gating, and saying so beats pretending;
3. input gate — non-canonical input (`input_not_canonical`) or canonical
   bytes over `limits.max_input_bytes` (`input_limit_exceeded`) →
   `invalid_input`; a mutating tool whose `idempotency = required_key`
   with no `idempotency_ref` in context → `invalid_input`
   (`idempotency_ref_required`); `attempt > retry.max_attempts` →
   `invalid_input` (`attempt_budget_exhausted`);
4. deadline gate — `now() >= deadline_at` before the callable starts →
   `deadline_exceeded`, termination `not_started`;
5. execution — the verified `in_process` callable runs.
   `TransientExecutionError` → `transient_failure`;
   `PermanentExecutionError` and any unexpected exception →
   `permanent_failure` (`unhandled_exception`; the exception's text is
   never copied into the envelope), escalated per §12;
6. output gate — non-canonical output (`output_not_canonical`) or over
   `limits.max_output_bytes` (`output_limit_exceeded`) →
   `permanent_failure`, escalated per §12;
7. completion — deadline passed during execution → `deadline_exceeded`
   with termination `completed` (the work mechanically finished; §11);
   otherwise `success`, termination `completed`.

### 10.4 Result envelope

`InvocationResult` (frozen dataclass) + `result_envelope(result)` canonical
projection. Fields: `status` (INVOCATION_STATUSES), `error_code` (closed:
`context_malformed, governance_denied, approval_required,
dependency_blocked, unknown_component, unknown_version,
input_not_canonical, input_limit_exceeded, idempotency_ref_required,
attempt_budget_exhausted, deadline_before_start, deadline_after_completion,
transient_execution_failure, permanent_execution_failure,
unhandled_exception, output_not_canonical, output_limit_exceeded`; absent
on success), `reasons` (governance codes), `retryable` (derived, §11),
`termination_outcome` (TERMINATION_OUTCOMES; this unit emits only
`not_started`/`completed`), `recovery_action` (§12), `attempt`,
`max_attempts`, `input_sha256`, `output_sha256` (success only), `output`
(success only; carried data, inert), manifest/binding identity + digests,
`invocation_id`, `started_at`/`ended_at`/`duration_seconds`.

The callable's return value cannot set any governance field: output rides
under `output`, and a dict that *looks* like an envelope stays data.

## 11. Retry, idempotency, deadline, cancellation

- `derive_retryable(manifest, status, attempt, context)` is the only
  producer of `retryable`: status must be `transient_failure` or
  `deadline_exceeded`, `attempt < min(retry.max_attempts,
  context.max_attempts)`, and — for mutating tools — the §5 retry-safety
  gate again at runtime (idempotency ref present when `required_key`, or a
  declared compensating action). Everything else derives `False`.
- Attempts are bounded twice: schema (1..10) and context (`attempt ≤
  max_attempts` else refusal). There is no loop here to hide a retry in.
- `deadline_exceeded` is a *status about lateness*, never a claim that work
  stopped: termination `not_started` (gate 4) and `completed` (gate 7) are
  the only truths this unit can honestly emit, and the vocabulary keeps
  `cooperative_cancelled | subprocess_terminated |
  remote_cancellation_requested | abandoned | not_supported` for adapters
  that can prove them. No sandbox or transport is implemented or claimed.

## 12. Recovery

`recovery.action` is the closed vocabulary; the runner copies the
manifest's declared action into failing results (`none` on success, and
`request_approval` on `approval_required` denials). When a
`permanent_failure` carries a declared recovery action that requires an
actor (`request_approval`, `manual_intervention`, `invoke_compensation`),
the status escalates to `recovery_required`; `none` and
`retry_after_backoff` keep `permanent_failure`. `recovery.note` is
display prose: nothing tokenizes, matches, or branches on it, and the test
suite proves a note that *names* an action does not change the recovery
action.

## 13. Evidence

`invocation_evidence(result, context, *, previous_sha256=None)` builds an
`aos.governed-invocation-evidence/v1` canonical record establishing:
invocation id; component kind/id/version; manifest digest; binding id +
digest; principal and caller agent; decision + reasons; attempt +
max_attempts; `idempotency_ref_sha256` (sha256 of the reference — the raw
reference never appears); started/ended/duration; status; error code;
input/output digests; termination outcome; recovery action; trace ids;
`previous_sha256` chain link; and its own `content_sha256` (self-excluding
digest). Every field is an enum member, bounded integer, validated
identifier, or digest — there is no free-text field to leak a secret
through, which is stronger than redaction. Evidence records what the
runner did, not what any model claimed.

## 14. Passport, routing, and handoff compatibility

`resolve_passport_requirements(document, skill_registry, tool_registry)`
is a read-only projection over a valid passport: each
`skill_requirements`/`tool_requirements` string resolves per §7 into a
frozen `RequirementResolution` with closed per-item codes
(`resolved | unknown_component | unknown_version`) and the resolved
version + manifest digest when found. The passport schema, the routing
evaluator, handoffs, and every existing fixture are byte-unchanged; the
U-A1/U-A3 string-declaration surface keeps its meaning and gains a
resolver, exactly as deferred. Adding two registry identities is the one
versioned protocol change: `REQUIRED_IDENTITIES` grows to six,
`protocols/registry.json` and the two new projection files are
regenerated, and the three spine assertions that pinned "exactly four"
(the identity list, `len(REGISTRY)`, and the `protocol list` line count)
update to six — documented here, tested there.

## 15. Persistence and CLI decisions

Nothing persists. Manifests are documents; registries are values; evidence
is a returned record. No table, no migration, no `SCHEMA_VERSION` bump, no
ID prefix, no event, no doctor check — the acceptance matrix needs none of
them, and D-v0.4.6's anticipatory-row prohibition counsels against
pre-minting storage for U-W1. No CLI verb is added: `aos protocol
validate FILE` already validates both new artifact kinds (registry
dispatch), `aos protocol verify-registry` already verifies their digests
and projections, and a governance-decision CLI would require inventing an
authority-context file format — deferred with the adapters. Consequently
`power.COMMAND_POLICY` is untouched.

## 16. Exclusions

The §0.2 list, verbatim, plus: no Atomic Agents source is copied or
imported (the evaluation repository is not read); no dependency of any
kind is added (`pyproject.toml` untouched); no GitHub state, plugin,
settings, or other worktree is modified.

## 17. Acceptance matrix

Manifest integrity: canonical round trip; digest stability under key
reordering; unknown field; unknown schema/major; unknown lifecycle,
evaluation, side effect, idempotency, cancellation, recovery action;
duplicate identity; ambiguous case-fold identity; malformed binding
declaration; binding digest mismatch; every §6 cross-field code positive
and negative.

Authority separation: manifest alone grants nothing (empty grant → deny);
missing capability → deny; exact capabilities + all gates → allow; unknown
capability shape fails closed; `approvals_required` never fabricates
approval; decision precedence pinned.

Skills: missing tool dependency; unknown pinned version; missing skill
dependency; dependency cycle; self-dependency; draft/deprecated/revoked
denied; unpromoted denied; agent-class mismatch; input-limit rejection.

Tools: invalid side-effect combinations; mutating+retryable without
idempotency/compensation unrepresentable; unbounded retry unrepresentable;
compensation ref biconditional; recovery note cannot drive execution;
digest-mismatched implementation denied; metadata binding cannot execute.

Protocol/results: callable output cannot overwrite governance fields;
`retryable` derived; `deadline_exceeded` ≠ termination claim (both
`not_started` and `completed` truths demonstrated); evidence contains no
raw input/output/idempotency reference; input/output digests stable;
closed status/error/reason vocabularies enforced; dependency-blocked,
policy-denial, invalid-input, and success-with-verified-binding results.

Compatibility: existing passport fixtures valid; routing/handoff suites
green; spine projection tests green with six schemas; full legacy suite
green; `python3 tools/gen_protocols.py` verify-clean.

Integration demonstration (§18 of the build prompt): passport → eligible
skill → eligible read-only tool → typed result → evidence record; missing
capability → denial; binding digest mismatch → denial; unavailable
dependency → `dependency_blocked` — all with in-process fakes, no network,
no shell, no filesystem outside `tempfile`.

## 18. Future adapter boundaries

Atomic Agents (runtime loop, BaseIOSchema mapping), Claude Agent SDK, and
MCP integrate — if ever — as subordinate adapters in separate units: an
adapter receives a verified manifest + binding and a governance decision it
cannot alter, maps IO at its boundary, and reports truthful termination.
Hidden adapter/framework retries must be disabled or fenced; Agentic OS
owns the attempt budget. `BaseTool` (or any framework's tool class) is
never a governance boundary. Component and status names are identities,
not immutable semantics; userspace network guards are not a sandbox;
deadline is not cancellation.

## 19. File boundary

Created: this contract; `agentic_os/governance.py`;
`tests/test_v04_governed_foundations.py`;
`protocols/beast.skill-manifest/v1.schema.json`;
`protocols/beast.tool-manifest/v1.schema.json`.
Modified: `agentic_os/protocols.py`; `protocols/registry.json`;
`tests/test_v03_protocol_spine.py` (three registry-count assertions);
`DECISIONS.md` (prepended D-v0.4.51–58); `README.md` (new unit section +
spine counts). Nothing else.

## 20. Verification

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q agentic_os tests tools aos.py aos_hooks.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_governed_foundations
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
python3 tools/gen_protocols.py
python3 tools/verify_ci_workflow.py
git diff --check
```

*This contract is the audit surface for U-K1/U-T1: an implementation
behavior the sections above do not license is a defect, whichever file it
lives in.*
