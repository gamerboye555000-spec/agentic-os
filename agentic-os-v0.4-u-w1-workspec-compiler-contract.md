# Agentic OS v0.4 — U-W1: deterministic WorkSpec compiler (Wave 0 architecture freeze)

Architecture freeze only. Baseline
`8cf82432d4c137d4a1513f9daee39cc3ee0be92b` (U-K1/U-T1 governed foundations
merged, ledger schema version `"5"`, milestone
`milestone/v0.4-u-k1-u-t1-governed-foundations`). Branch
`v0.4-u-w1-workspec-compiler`; worktree `/home/daksh/Projects/agentic-os-u-w1`;
primary checkout `/home/daksh/Projects/agentic-os`. Future PR title:
`feat(v0.4): U-W1 — deterministic WorkSpec compiler`. Future tag:
`milestone/v0.4-u-w1-workspec-compiler`. Decisions: D-v0.4.59 – D-v0.4.70.

U-W1 is the static half of the workflow story: it compiles, lints, resolves,
decompiles, and semantically diffs inert `beast.work-spec/v1` artifacts. It
executes zero attempts and schedules zero work. This document freezes the
architecture; a later wave implements it. The implementation and tests must
mechanically agree with this document — a sentence here that the code cannot
demonstrate is a defect in one of the two.

Extends: the U-X1 protocol spine
(`agentic-os-v0.3-u-x1-protocol-spine-contract.md`), the U-A1 passport
contract (`agentic-os-v0.4-u-a1-agent-passports-contract.md`), the U-A2
catalog contract (`agentic-os-v0.4-u-a2-specialist-catalog-contract.md`), the
U-A3 routing/handoff contract
(`agentic-os-v0.4-u-a3-routing-handoffs-contract.md`), and the U-K1/U-T1
governed foundations contract
(`agentic-os-v0.4-u-k1-u-t1-governed-foundations-contract.md`). Delivery flows
through the U-P2 gate (`agentic-os-v0.4-u-p2-delivery-gate-contract.md`, as
amended by `agentic-os-v0.4-u-p2-trust-boundary-amendment.md`).

## 0. Scope

### 0.1 In scope (frozen here, implemented in a later wave)

- One new standard-library-only module, `agentic_os/workspecs.py`: a pure,
  deterministic compiler from a closed authoring input to a canonical
  `beast.work-spec/v1` artifact plus a self-digested compile/resolution
  report; a semantic linter with a closed reason-code vocabulary and a
  six-status precedence; deterministic resolution of requested
  agents/skills/tools against an immutable registry snapshot; a
  deterministic, bounded, secret-safe decompiler; and a deterministic
  semantic diff with typed change kinds.
- One new focused test file, `tests/test_v04_workspec_compiler.py`, covering
  the §20 matrix.
- `DECISIONS.md` (prepended D-v0.4.59–70, this wave) and `README.md` (one new
  unit section, implementation wave).

### 0.2 NOT in scope (mechanically absent, not merely discouraged)

- No execution of any kind: zero attempts run, zero tasks are scheduled or
  enqueued, no `governance.invoke()` call, no binding callable, no retry
  loop, no compensation action, no checkpoint, no resume. U-W1 output is
  inert data.
- No workflow state engine, no queue integration, no workflow lifecycle
  states (U-W2); no runtime retry, checkpoint, resume, or compensation
  executor (U-W3); no manager/fork-join/blackboard patterns (U-A4); no
  natural-language-to-IR compilation (U-N1); no context sharding or
  hydration receipts (U-M6).
- No protocol change: `beast.work-spec/v1` is reused exactly as shipped. No
  v2 identity, no second WorkSpec schema, no registry growth, no
  `protocols/` projection change, no edit to `agentic_os/protocols.py`.
- No persistence: no table, no migration, no `SCHEMA_VERSION` bump (stays
  `"5"`), no ledger ID prefix, no event emission, no doctor check, no
  `power.COMMAND_POLICY` entry.
- No CLI verb and no `agentic_os/cli.py` change.
- No dependency: `pyproject.toml` untouched; stock Python standard library
  only.
- No network, no filesystem access in the compiler surface (documents in,
  documents out), no dynamic import, no `exec`, no subprocess, no
  environment variable read, no locale-dependent behavior, no wall-clock
  read, no randomness.
- No MCP, no A2A, no provider adapter, no framework integration.

### 0.3 Untouched

`agentic_os/protocols.py`, `protocols/**`, `agentic_os/governance.py`,
`agentic_os/passports.py`, `agentic_os/catalog.py` and
`agentic_os/catalog/*`, `agentic_os/routing.py`,
`agentic_os/agent_handoffs.py`, `agentic_os/models.py`,
`agentic_os/secretscan.py`, `agentic_os/db.py`, `agentic_os/migrations.py`,
`agentic_os/cli.py`, `agentic_os/power.py`, `agentic_os/doctor.py`,
`tests/test_v03_protocol_spine.py` and every other existing test, all
delivery-control files (`.github/workflows/ci.yml`,
`tools/verify_ci_workflow.py`, `tests/test_v04_delivery_gate.py`),
`pyproject.toml`, and every existing fixture. Existing artifacts remain
valid without edits.

## 1. Decisions (index)

- **D-v0.4.59** — U-W1 is static; the runtime boundary is
  U-W1 = compile/lint/resolve/decompile/diff, U-W2 = workflow state engine
  and queue integration, U-W3 = checkpoints, resume, runtime retry, and
  compensation. Earlier "outer retry loop is U-W1's" wording is narrowed to
  static attempt-constraint validation.
- **D-v0.4.60** — `beast.work-spec/v1` is reused unchanged: no v2, no second
  schema, no registry growth, no projection change.
- **D-v0.4.61** — the authoring input is a closed, bounded, inert contract
  (`aos.work-spec-authoring/v1`) with four frozen field classes and no
  executable, ambient, or authority-bearing surface.
- **D-v0.4.62** — compilation is a pure function to a canonical artifact
  plus a self-digested report (`aos.work-spec-compile-report/v1`) carrying
  provenance, findings, resolutions, and exact registry-snapshot digests;
  compilation grants nothing.
- **D-v0.4.63** — semantic lint has a closed reason-code vocabulary in
  canonical order with the six-status precedence
  `invalid > unresolved > ineligible > requires_external_authority >
  warning > valid`; lint never duplicates a governance authority decision.
- **D-v0.4.64** — resolution is deterministic and snapshot-local: numeric
  version ordering, exact pin or highest version, lifecycle-blind resolve
  then lifecycle-visible findings; the compiler never installs, activates,
  fetches, imports, binds, or executes.
- **D-v0.4.65** — a WorkSpec describes requested work; it grants nothing.
  Policy, approval, budget, capability, identity, and secret references
  remain opaque and non-authoritative in U-W1.
- **D-v0.4.66** — classification order is the `DATA_CLASSIFICATIONS` tuple
  order; compilation is classification-preserving with no silent downgrade;
  scope compatibility follows the passport scope rules; diagnostics are
  value-free.
- **D-v0.4.67** — the decompiler is deterministic, bounded, and secret-safe,
  with explicit/defaulted/resolved provenance markers; the round-trip claim
  is semantic (via `authoring_view` reconstruction to an identical artifact
  digest), and reconstruction of original authoring bytes is not claimed.
- **D-v0.4.68** — the semantic diff has typed change kinds, closed
  categories, a canonical path grammar, deterministic order, and a frozen
  raw-value allowlist; free-text fields diff by digest only.
- **D-v0.4.69** — mutation and digest safety: canonical-round-trip snapshots
  on intake, fresh unshared returns, digests recomputed over final values,
  no stale attestation; every existing surface is byte-unchanged.
- **D-v0.4.70** — no persistence, no CLI, no dependency; the implementation
  boundary is exactly five paths, and any additional path in any later
  U-W1 wave is a replan condition.

## 2. Dependencies and phase reconciliation

### 2.1 Present-dependency proof (live tree at the baseline)

| Unit | Live evidence at `8cf82432d4c137d4a1513f9daee39cc3ee0be92b` |
| --- | --- |
| U-X1 | `agentic_os/protocols.py` (canonical JSON v1, content digests, frozen six-schema registry), `protocols/**`, `tools/gen_protocols.py`, `tests/test_v03_protocol_spine.py`, contract file, tag `milestone/v0.3-u-x1-protocol-spine` |
| U-A1 | `agentic_os/passports.py`, `beast.agent-passport/v1` in the registry, `tests/test_v04_agent_passports.py`, contract file, tag `milestone/v0.4-u-a1-agent-passports` |
| U-A2 | `agentic_os/catalog.py`, `agentic_os/catalog/*` (manifest + twelve passports), `tests/test_v04_agent_catalog.py`, contract file, tag `milestone/v0.4-u-a2-specialist-catalog` |
| U-A3 | `agentic_os/routing.py`, `agentic_os/agent_handoffs.py`, `tests/test_v04_routing_handoffs.py`, contract file, tag `milestone/v0.4-u-a3-routing-handoffs` |
| U-K1/U-T1 | `agentic_os/governance.py`, `beast.skill-manifest/v1` + `beast.tool-manifest/v1` in the registry, `tests/test_v04_governed_foundations.py`, contract file, tag `milestone/v0.4-u-k1-u-t1-governed-foundations` (peels to the baseline) |
| U-P2 | `.github/workflows/ci.yml`, `tools/verify_ci_workflow.py`, `tests/test_v04_delivery_gate.py`, contract + trust-boundary amendment, tag `milestone/v0.4-u-p2-delivery-gate` |

### 2.2 The U-W1 / U-W2 / U-W3 boundary (frozen)

- **U-W1** compiles, lints, resolves, decompiles, and semantically diffs
  inert WorkSpecs. It executes zero attempts and schedules zero work. No
  workflow state persists anywhere in U-W1.
- **U-W2** owns the deterministic workflow state engine and queue
  integration: the `proposed → compiled → validated → …` lifecycle of the
  blueprint (§9.2) is U-W2 vocabulary, not U-W1's.
- **U-W3** owns checkpoints, resume, runtime retry, and compensation
  execution.
- **U-K1/U-T1 `invoke()` remains single-attempt**, byte-unchanged.

Reconciliation of earlier wording. Two live sentences say the outer attempt
loop "is U-W1's": the `governance.invoke()` docstring ("The outer attempt
loop belongs to Agentic OS (U-W1); there is no loop here to hide a retry
in") and the U-K1/U-T1 contract §0.2 / D-v0.4.56 ("the retry loop itself is
U-W1's"). Both were written before the U-W2/U-W3 split was frozen. Their
binding meaning, frozen here: U-W1 may compile and statically validate
attempt constraints (`retry.max_attempts`, `retry.deadline_at`, and their
compatibility with resolved tool manifests); **runtime looping is U-W3's**.
Nothing behavioral changes: `invoke()` already executes at most one attempt,
and U-W1 ships no loop. The docstring phrase itself is prose inside
`agentic_os/governance.py`, which is outside this unit's file boundary; it
is superseded by D-v0.4.59 and may be retouched only by a unit that already
modifies that file. No live evidence contradicts this split, so no replan is
required.

### 2.3 Adjacent-unit boundaries (frozen)

- **U-A4** (manager/handoff/fork-join/blackboard patterns) consumes compiled
  WorkSpecs and routing/handoff advice; U-W1 ships no multi-agent pattern,
  and no U-W1 output selects, launches, or coordinates an agent.
- **U-N1** (neural → typed IR compiler) owns natural-language authoring; the
  U-W1 authoring input is already-typed data, and U-W1 performs no language
  interpretation. U-N4's human decompiler/semantic diff over neural IR is a
  separate future surface; U-W1's decompiler/diff cover
  `beast.work-spec/v1` artifacts only.
- **U-M6** (context sharding + hydration receipts) may bind shards to
  WorkSpec digests later; U-W1 defines no shard, receipt, or token-budget
  arithmetic.
- **U-M4** (memory workflow) is untouched; U-W1 reads and writes no memory
  rows.

## 3. Threat and failure model; trust boundary

Threats U-W1 must refuse mechanically:

- **Authority laundering**: an authoring input or artifact "declaring"
  itself approved, budgeted, credentialed, routed, or execution-eligible.
  The protocol makes approval booleans, credentials, environment maps, and
  executable fields unrepresentable; U-W1 adds no field, default, or report
  entry that could carry authority (§10).
- **Fabricated facts**: the compiler inventing classifications, audiences,
  task bindings, or evidence expectations the author never stated. Defaults
  exist only for content-derived identifiers, the least-authority
  destination floor, and the weakest honest result-contract floor (§6).
- **Hidden inputs**: wall clock, randomness, environment, locale, filesystem
  scans, or network lookups influencing output. The compiler is a pure
  function of (authoring input, snapshot); identical inputs produce
  identical bytes on every platform (§7).
- **Snapshot tampering and aliasing**: a caller-retained reference mutating
  what was compiled against, or a stale digest attesting to changed content.
  Canonical-round-trip snapshots on intake; digests recomputed over final
  values (§15).
- **Secret leakage**: secret-shaped content entering an artifact, report,
  decompiled view, or diff. Compile refuses secret-shaped free text
  (fail-closed, the D-v0.4.19 shipped-content rule — the authoring document
  is a cross-boundary input, not a trusted human's live keystrokes);
  diagnostics carry closed codes, paths, counts, and pattern names, never
  values; decompile redacts; diff digests free text (§8, §12, §13).
- **Ambiguity**: two snapshot entries answering one reference, or one
  request naming two versions of one component. Case-folded agent-name
  collisions refuse at snapshot build; contradictory version requests are a
  closed finding (§9).

Trust boundary: authoring inputs, artifacts presented for lint/decompile/
diff, and snapshot documents are untrusted and validated fail-closed.
Snapshot lifecycle facts (an agent's ledger lifecycle) are caller-attested
inputs: U-W1 validates their vocabulary and treats them as facts, exactly as
`routing.CandidateSnapshot` does; reading them from the ledger is the
caller's job (CLI and U-W2, later units). Lint findings are advisory
statics: they never grant, and runtime governance (`evaluate_eligibility`,
`invoke()`) re-decides authority at execution time with its own inputs.

## 4. Canonical entities and closed vocabularies

New entities (all in `agentic_os/workspecs.py`; every record is canonical
JSON v1 material):

| Entity | Form |
| --- | --- |
| Authoring input | closed dict, `aos.work-spec-authoring/v1` |
| Registry snapshot | frozen dataclass `WorkSpecSnapshot` + canonical projection `aos.work-spec-registry-snapshot/v1` |
| Compiled WorkSpec | `beast.work-spec/v1` document (existing protocol, unchanged) |
| Compile result | frozen dataclass `CompileResult` (status, findings, artifact, report) |
| Compile/resolution report | canonical record `aos.work-spec-compile-report/v1`, self-digested |
| Lint finding | frozen dataclass (code, status class, path, bounded diagnostics) |
| Resolution record | frozen dataclass (kind, requested, code, resolved id/version/digest) |
| Decompiled view | deterministic `str` (display-only) |
| Semantic diff | canonical record `aos.work-spec-semantic-diff/v1`, self-digested |

Closed vocabularies frozen here (module constants):

```text
WORKSPEC_AUTHORING_SCHEMA   = "aos.work-spec-authoring/v1"
WORKSPEC_ALGORITHM_VERSION  = "aos-workspec-compile/v1"
REPORT_RECORD_SCHEMA        = "aos.work-spec-compile-report/v1"
SNAPSHOT_RECORD_SCHEMA      = "aos.work-spec-registry-snapshot/v1"
DIFF_RECORD_SCHEMA          = "aos.work-spec-semantic-diff/v1"

WORKSPEC_LINT_STATUSES = invalid | unresolved | ineligible |
                         requires_external_authority | warning | valid

WORKSPEC_LINT_CODES (canonical emission order; class in parentheses):
  malformed_input                (invalid)
  forbidden_field                (invalid)
  schema_invalid                 (invalid)
  contradictory_limits           (invalid)
  malformed_authority_ref        (invalid)
  duplicate_item                 (invalid)
  secret_shaped_content          (invalid)
  unsupported_dynamic_behavior   (invalid)
  unknown_agent                  (unresolved)
  unknown_skill                  (unresolved)
  unknown_tool                   (unresolved)
  unknown_version                (unresolved)
  ambiguous_component            (unresolved)
  lifecycle_not_active           (ineligible)
  not_promoted                   (ineligible)
  dependency_blocked             (ineligible)
  agent_class_mismatch           (ineligible)
  capability_mismatch            (ineligible)
  classification_mismatch        (ineligible)
  scope_mismatch                 (ineligible)
  retry_idempotency_incompatible (ineligible)
  result_contract_mismatch       (ineligible)
  approval_reference_required    (requires_external_authority)
  unpinned_requirement           (warning)
  redundant_explicit_default     (warning)

PROVENANCE_CLASSES = explicit | defaulted | resolved
DIFF_CHANGE_KINDS  = added | removed | changed
DIFF_CATEGORIES (canonical order) = metadata | requirements |
  authority_references | budgets_limits | retry_idempotency |
  classification | resolutions | result_contract
```

Reused exactly, never duplicated: canonical JSON v1
(`protocols.serialize_canonical` / `parse_canonical`), the self-excluding
`content_sha256` digest (`protocols.content_digest`),
`protocols.validate_document`, the frozen `protocols.REGISTRY` (six
identities, `REGISTRY_VERSION` 1), `DATA_CLASSIFICATIONS`,
`PERMITTED_DESTINATIONS`, `INPUT_REF_KINDS`, `EVIDENCE_KINDS`,
`AGENT_CLASSES`, `AGENT_LIFECYCLES`, `COMPONENT_LIFECYCLES`,
`SKILL_EVALUATION_STATES`, `TOOL_SIDE_EFFECTS`,
`TOOL_IDEMPOTENCY_MODES`, `TOOL_COMPENSATION_STRATEGIES`, every U-X1
pattern constant (`ISSUER_PATTERN`, `CAPABILITY_PATTERN`,
`REQUIREMENT_PATTERN`, `OPAQUE_REF_PATTERN`, `AGENT_NAME_PATTERN`,
`AOS_TASK_ID_PATTERN`, `IDEMPOTENCY_KEY_PATTERN`, `UUID_PATTERN`,
`TRACE_ID_PATTERN`, `RFC3339_PATTERN`, `SHA256_PATTERN`),
`governance.ComponentRegistry` / `build_skill_registry` /
`build_tool_registry` / `parse_requirement`, and
`secretscan.scan_secrets` / `redact_tree`. `utils.AosError` is the error
base. `utils.utc_now_iso()` is deliberately NOT imported: the compiler
reads no clock.

## 5. Authoring input contract (`aos.work-spec-authoring/v1`)

A closed, bounded dict — the `aos.routing-request/v1` idiom. Unknown keys
refuse (`malformed_input`); the four compiler-owned protocol keys refuse
with the dedicated code (`forbidden_field`); non-data values anywhere in
the tree (a callable, a float, bytes, a non-string key) refuse
(`unsupported_dynamic_behavior` for non-JSON values, `malformed_input` for
shape violations). There is no executable expression, import path, command,
callable, filesystem path to scan, network lookup, credential, environment
map, randomness, locale dependence, or model-granted authority anywhere in
the surface — unrepresentable, not merely discouraged.

Required pins:

- `authoring_schema` — const `aos.work-spec-authoring/v1`.
- `algorithm_version` — const `aos-workspec-compile/v1`.

Field classes (frozen; every emitted artifact field belongs to exactly one):

**Explicit (required)** — stated by the author, never invented:
`created_at` (Timestamp; the compiler reads no clock), `issuer` (Issuer),
`audience` (1..8 Issuers), `scope` (`{project, tenant?}`), `aos_task_id`,
`data_classification` (`DATA_CLASSIFICATIONS`), `goal` (1..4096),
`acceptance_criteria` (1..32 strings).

**Explicit (optional)** — pass-through when present, schema-validated:
`expires_at`, `constraints` (0..32), `required_capabilities` (0..16),
`inputs` (0..32 declared references; never opened, fetched, or hashed),
`policy_refs` (`{policy_ref?, approval_ref?, budget_ref?}`, each an
OpaqueRef), `retry` (`{max_attempts 1..10, deadline_at?}`),
`expected_result`, `permitted_destinations`, `runtime_task_uuid`
(format-validated only; owned by the runtime and never interpreted here),
`work_spec_id`, `idempotency_key`, `trace`.

**Mechanically defaulted** — deterministic, content-derived or frozen
constants, injected only when absent (§6): `work_spec_id`,
`idempotency_key`, `trace`, `permitted_destinations`, `expected_result`,
plus the compiler-owned constants `schema`, `protocol_version`,
`content_hash_alg`.

**Mechanically resolved** — computed, never authorable: `content_sha256`
(the U-X1 self-excluding digest) and every report entry (findings,
resolutions, provenance, snapshot digests).

**Forbidden** — refused when present in authoring input: `schema`,
`protocol_version`, `content_hash_alg`, `content_sha256`
(`forbidden_field`). Approval booleans, credentials, environment maps,
capability grants, and resolution results are not representable at all: no
key exists for them.

**Requested components** (optional, authoring-only; never serialized into
the artifact — the v1 protocol carries no assignment fields, and assignment
stays advisory per U-A3):

```text
requested: {
  agent?:  { name: AGENT_NAME_PATTERN, version?: int 1..999999 }
  skills?: [ REQUIREMENT_PATTERN … ]   (0..16, duplicates refused)
  tools?:  [ REQUIREMENT_PATTERN … ]   (0..16, duplicates refused)
}
```

Normalization (frozen; the `validate_request` idiom): every uniqueItems
string array (`audience`, `acceptance_criteria`, `constraints`,
`required_capabilities`, `permitted_destinations`,
`expected_result.evidence_kinds`, `requested.skills`, `requested.tools`)
sorts by code point; `inputs` sorts by the canonical bytes of each item;
defaults are spelled out; two logically equivalent authorings (key order or
array order shuffled, defaults implicit or explicit) compile to identical
canonical bytes and an identical digest.

## 6. Defaults and provenance

The frozen default table. `derivation material` = the canonical bytes of the
normalized authoring input with the keys `work_spec_id`,
`idempotency_key`, and `trace` removed (present or not), so each derivation
is total, order-independent, and independent of the other derivable fields.

| Field | Default when absent |
| --- | --- |
| `schema` | `beast.work-spec/v1` (constant) |
| `protocol_version` | `1` (constant) |
| `content_hash_alg` | `aos-sha256-canonical/v1` (constant) |
| `work_spec_id` | RFC 9562 UUIDv8 formatted from `sha256(b"aos-workspec-id/v1\0" + material)` (version nibble 8, RFC variant bits, lowercase hex) |
| `idempotency_key` | `"ws-" + sha256(b"aos-workspec-idem/v1\0" + material)[:40]` |
| `trace.trace_id` | `sha256(b"aos-workspec-trace/v1\0" + material)[:32]`; if all zeros (not reachable in practice, guarded anyway) the final character becomes `"1"` |
| `trace.correlation_id` | RFC 9562 UUIDv8 from `sha256(b"aos-workspec-corr/v1\0" + material)` |
| `permitted_destinations` | `["aos-ledger", "local"]` — the least-authority floor; an explicit wider list is the author's declaration, and a declaration is not a grant |
| `expected_result` | `{result_schema: "beast.result-envelope/v1", evidence_kinds: ["note"], min_evidence_count: 1}` — the weakest honest result-contract floor; §8 findings surface when a resolved component declares stronger expectations |
| `content_sha256` | computed digest (mechanically resolved, never defaulted from input) |

No other field has a default. `created_at` is explicit because the compiler
reads no clock; `data_classification`, `issuer`, `audience`, `scope`,
`aos_task_id`, `goal`, and `acceptance_criteria` are explicit because
inventing any of them would fabricate a fact.

Provenance: the report maps every top-level emitted field (and
`trace`/`expected_result` sub-fields) to exactly one of
`explicit | defaulted | resolved`, sorted by path. The decompiler prints
these markers (§12).

## 7. Compilation

`compile_work_spec(authoring, snapshot) -> CompileResult` — a pure function.
Pipeline, frozen:

1. shape-validate and normalize the authoring input (§5);
2. inject defaults and derivations (§6);
3. assemble the candidate document and compute `content_sha256`;
4. validate the candidate through `protocols.validate_document` — the same
   engine every consumer uses, so compiler output can never drift from the
   registry schema;
5. resolve requested components against the snapshot (§9);
6. run every semantic lint gate (§8), collecting findings;
7. derive the status (§8 precedence) and build the report.

Outputs:

- **Artifact**: the canonical `beast.work-spec/v1` document. Emitted for
  every status except `invalid` (an `invalid` input either cannot form a
  schema-valid document or carries content that must not be embedded, so
  no artifact exists). `unresolved`, `ineligible`,
  `requires_external_authority`, and `warning` artifacts are still valid,
  inert protocol documents — the findings ride in the report.
- **Report** (`aos.work-spec-compile-report/v1`, canonical, self-digested):
  `schema`, `algorithm_version`, `status`, `work_spec_id` and
  `work_spec_sha256` (recomputed from the artifact body; absent when no
  artifact exists), `findings` (canonical order), `resolutions` (§9),
  `provenance` (§6), `defaults_applied` (sorted field list), and
  `registry_state`: the protocol registry pins
  (`registry_version` 1, the `beast.work-spec/v1` schema digest
  `07ac96ba08a1579bbd681ab4087156e9d8facf849f3348e0e494658f3acceab9`) plus
  the snapshot digest (§9). Report content is closed: codes, paths, enum
  members, bounded integers, identifiers, and digests — no free text and no
  echoed field values.

Compilation grants nothing: no capability, approval, policy decision,
budget reservation, secret selection, route authority, power-mode change,
execution context, or execution permission is created, implied, or
recorded. A compile result is advisory input to U-W2 and human review.

Downstream sidecar rule, frozen now for U-W2 consumption: a report's
resolutions and findings are meaningful only while the report digest-binds
what it describes — its `work_spec_sha256` must equal the consumed
artifact's recomputed digest, and its `registry_state` snapshot digest
names the exact resolution universe. U-W2 must verify that binding before
honoring a report, must treat an absent, unbound, or mismatched report as
no report at all (its remedy is recompiling against its own snapshot —
never silently substituting, repairing, or honoring one), and must not
silently discard a bound report while acting on its artifact. An unbound
sidecar is never authoritative for anything.

Determinism: identical `(authoring, snapshot)` yields byte-identical
artifact and report (digest-stable across process runs, platforms, key
order, and array order). Compilation is idempotent: `authoring_view` of the
output recompiles to the identical artifact digest (§12).

## 8. Semantic lint

`lint_work_spec(artifact, snapshot, requested=None) -> LintReport` applies
the same gates to an existing artifact (compile runs them inline). Findings
are `(code, class, path, bounded diagnostics)`; emission order is canonical:
`WORKSPEC_LINT_CODES` order first, then path code-point order. The status is
the highest-precedence class with at least one finding
(`invalid > unresolved > ineligible > requires_external_authority >
warning`), else `valid` — the `GOVERNANCE_REASON_CODES`/`_decide` idiom.

Gates, frozen (code — condition):

- `malformed_input` — non-object input, unknown key, wrong JSON type,
  pattern violation, bound violation in the authoring shape.
- `forbidden_field` — a compiler-owned protocol key present in authoring
  input (§5).
- `schema_invalid` — an artifact presented for lint fails
  `protocols.validate_document` for any reason without a refined code
  below; the spine's closed reason code and path ride in diagnostics,
  value-free. Exactly two spine refusals are refined instead of reported
  here (never co-emitted with this code): an `expires_before_created`
  refusal surfaces as `contradictory_limits`, and a refusal at or under
  `/policy_refs` surfaces as `malformed_authority_ref` — so the three
  triggers stay disjoint and each stays attainable on the lint path.
- `contradictory_limits` — `expires_at` earlier than `created_at` (also a
  spine refusal; on the lint path the `schema_invalid` refinement rule
  surfaces it as this code), `retry.deadline_at` earlier than
  `created_at`, or `retry.deadline_at` later than `expires_at` when both
  are present.
- `malformed_authority_ref` — a `policy_refs` member that is not a
  schema-valid OpaqueRef (on the lint path via the `schema_invalid`
  refinement rule — the spine refuses the member and this code carries
  it; on the compile path the same defect is `malformed_input` at shape
  time).
- `duplicate_item` — a repeated item in any uniqueItems-equivalent authoring
  array, a repeated `(ref_kind, ref)` input pair, or the same requirement
  string requested twice.
- `secret_shaped_content` — `secretscan.scan_secrets` matches in any
  free-text authoring field (`goal`, `acceptance_criteria[]`,
  `constraints[]`, `inputs[].ref`, `inputs[].note`, explicit
  `idempotency_key`). Fail-closed refusal (D-v0.4.19 class); diagnostics
  carry pattern names and the path only.
- `unsupported_dynamic_behavior` — a non-JSON-data value anywhere in the
  input tree (callable, float, bytes, or any object canonical JSON v1
  cannot represent).
- `unknown_agent` / `unknown_skill` / `unknown_tool` — a requested name/slug
  absent from the snapshot (name matching is exact; a case-fold near-match
  is still unknown).
- `unknown_version` — a requested exact version pin naming no snapshot
  entry for a known component.
- `ambiguous_component` — one request set naming two different versions of
  the same component (e.g. `fmt/v1` and `fmt/v2`).
- `lifecycle_not_active` — a resolved agent whose caller-attested lifecycle
  is not `active`, or a resolved skill/tool manifest whose `lifecycle` is
  not `active`.
- `not_promoted` — a resolved skill whose `evaluation` is not `promoted`.
- `dependency_blocked` — a resolved skill/tool whose transitive declared
  dependencies contain an entry that is unresolvable in the snapshot,
  whose lifecycle is not `active`, or (for a skill) whose `evaluation` is
  not `promoted` — a closed three-condition list: the shape of the
  `governance._dependency_problems` walk, reimplemented read-only without
  its binding checks (the U-W1 snapshot holds no bindings, so binding
  verification is not part of this gate). Dependency cycles cannot reach
  lint: snapshot construction builds registries through
  `governance.build_skill_registry`, which refuses cycles at build time
  with its closed `dependency_cycle` reason.
- `agent_class_mismatch` — a resolved skill declares
  `agent_constraints.agent_classes` and the resolved agent's class is not
  in it.
- `capability_mismatch` — (a) the artifact's `required_capabilities` are
  not covered by the resolved agent's declared `capabilities`, or (b) the
  union of resolved skills'/tools' `required_capabilities` is not covered
  by the artifact's `required_capabilities`. The two directions carry
  distinct paths.
- `classification_mismatch` — a resolved agent passport whose
  `data_classifications` declaration is absent or does not contain the
  artifact's `data_classification` (fail-closed on absence, the routing
  rule).
- `scope_mismatch` — a resolved project-scoped agent whose declared project
  differs from the artifact's `scope.project`.
- `retry_idempotency_incompatible` — `retry.max_attempts > 1` with a
  resolved mutating tool that neither requires an idempotency key nor
  declares a compensating action (the D-v0.4.56 rule, statically applied),
  or `retry.max_attempts` exceeding a resolved tool's declared
  `retry.max_attempts`.
- `result_contract_mismatch` — a resolved component's
  `evidence_expectations` not covered by the artifact's `expected_result`
  (`evidence_kinds` not a superset, or `min_evidence_count` lower than
  declared).
- `approval_reference_required` — a resolved component (agent passport or
  tool manifest) declares `approvals_required` and the artifact carries no
  `policy_refs.approval_ref`. This is a statement that external authority
  will be needed — never a check of it: carrying an `approval_ref` in a
  WorkSpec satisfies nothing at runtime, where governance evaluates its own
  execution-context inputs.
- `unpinned_requirement` — a requested bare slug (or unversioned agent)
  resolved to the highest version; advisory, with the resolved version in
  the resolution record.
- `redundant_explicit_default` — compile-path only: an explicit
  `permitted_destinations` or `expected_result` in the authoring input
  equal, after §5 normalization, to the frozen default. A bare artifact
  linted without its authoring input never earns it: explicitness is
  provenance, a standalone artifact carries none, and a defaulted
  artifact's values legitimately equal the defaults.

Lint never duplicates a governance authority decision: it emits no
`allow`/`deny`, consumes no `granted_capabilities`, evaluates no execution
context, and its findings carry no authority. Component findings arise only
when components were requested; an artifact linted without requests earns
only the artifact-static gates (the v1 protocol intentionally carries no
assignment fields).

Diagnostics discipline (the `ProtocolError` rule): every finding is built
from a closed code, a schema-safe path, closed enum members, bounded
counts, and pattern names — never a field value, a document excerpt, or
exception text.

## 9. Resolution

`WorkSpecSnapshot` — the immutable resolution universe:

- **Agents**: a sequence of entries `(name, lifecycle, document)` where
  `document` is a valid `beast.agent-passport/v1` artifact and `lifecycle`
  is a caller-attested `AGENT_LIFECYCLES` member. Build validates every
  document through `protocols.validate_document`, requires
  `document["agent"] == name`, snapshots each document by canonical round
  trip, indexes by `(name, passport_version)`, refuses duplicate
  `(name, passport_version)` pairs and case-folded name collisions (the
  `build_registry` folded-identity rule), and records the highest
  `passport_version` per name.
- **Skills / tools**: `governance.ComponentRegistry` values, accepted
  as-is or built from raw manifest documents via
  `governance.build_tool_registry` / `build_skill_registry` (which refuse
  duplicates, missing dependencies, unknown dependency versions, and
  dependency cycles at build time with their closed reasons).
- **Projection and digest**: `snapshot_projection(snapshot)` is a
  deterministic canonical record (`aos.work-spec-registry-snapshot/v1`):
  sorted agent entries (name, passport_version, lifecycle, document
  digest) plus the `governance.registry_projection` of each registry —
  ids, versions, states, and digests only, never a document body.
  `snapshot_digest` = sha256 over its canonical bytes; recorded in every
  report.

Resolution rules, frozen:

- **Numeric version ordering**: versions are integers
  (`passport_version` 1..999999, `component_version` 1..9999) compared
  numerically, never lexicographically.
- **Exact pin**: a requested version resolves that version or yields
  `unknown_version`.
- **Unpinned**: a bare name/slug resolves the highest registered version
  (the `ComponentRegistry.resolve` / passport-`current` rule) and earns the
  `unpinned_requirement` warning.
- **Lifecycle-blind resolve, lifecycle-visible findings**: resolution never
  consults lifecycle or evaluation state; a deprecated or unpromoted latest
  resolves and then earns its `ineligible` finding, so deprecation stays
  visible instead of silently skipped (the governance §7 rule).
- **Duplicates and ambiguity**: duplicate requests are `duplicate_item`;
  contradictory version requests are `ambiguous_component`; ambiguous
  snapshot identities are unrepresentable (refused at build).
- **Stable ordering**: resolution records sort by (kind, requested string);
  each carries the closed per-item code
  (`resolved | unknown_component | unknown_version`, the
  `RESOLUTION_CODES` idiom) plus resolved id, version, and manifest or
  passport digest when resolved.

The compiler never installs, activates, fetches, imports, binds, or
executes anything during resolution. A snapshot is data; resolving against
it opens no file, touches no database, and calls no binding.

## 10. Authority separation

Frozen sentence: **a WorkSpec describes requested work; it grants
nothing.**

- `policy_refs.policy_ref` / `approval_ref` / `budget_ref` are opaque
  references to records owned by other systems. U-W1 validates their shape
  and never dereferences, verifies, or interprets them; no U-W1 output
  claims any of them is satisfied, granted, or funded.
- U-W1 must not approve, reserve or account spend, grant or check
  capabilities, select credentials, override power mode, construct an
  execution context, or turn routing/handoff advice into permission. None
  of these appear in any U-W1 signature, record schema, or report field.
- Compilation success, `valid` lint status, and `resolved` resolution codes
  are statements about internal consistency against a snapshot — never
  eligibility grants. Runtime governance re-decides with its own inputs;
  U-K1/U-T1's split (`required_capabilities` declared vs
  `granted_capabilities` granted) is untouched and unmirrored.

## 11. Classification and scope

- **Ordering**: `DATA_CLASSIFICATIONS` tuple order is the total order
  `public < internal < confidential < restricted`.
- **Preservation, no silent downgrade**: `data_classification` is explicit,
  required, and emitted exactly as authored. No default, coercion, or
  transformation exists that could raise or lower it; the diff reports any
  classification change between two artifacts under its own category.
- **Compatibility**: a resolved agent must declare the artifact's
  classification in `data_classifications`, else `classification_mismatch`
  (absence fails closed, §8).
- **Scope**: `scope.project` is explicit and required; a project-scoped
  resolved agent must match it exactly, else `scope_mismatch`. Global
  agents are compatible with every project. Cross-project references are
  unrepresentable: one artifact carries one `scope.project`, and snapshot
  passports bind their own scope declarations. `scope.tenant` is
  format-validated and otherwise uninterpreted in v1 (§23).
- **Secret-safe diagnostics**: classification and scope findings name
  paths and enum members only — never the project slug of a mismatching
  passport, and never any field value.

## 12. Decompiler

`decompile_work_spec(artifact, report=None) -> str` — deterministic,
bounded, display-only.

- **Deterministic layout**: fixed ASCII framing, LF newlines, two-space
  indentation, fields in a frozen section order (identity, intent,
  classification/scope, destinations, inputs, authority references, retry,
  result contract, trace) with paths sorted by code point inside each
  section. No terminal-width probing, no locale-dependent formatting, no
  wall-clock stamp: identical inputs render identical bytes on every
  platform.
- **Bounded**: free-text values longer than 120 code points truncate at 120
  with the fixed marker `...(+N chars)`; array rendering is bounded by the
  schema's own item bounds. Output size is a pure function of the bounded
  input.
- **Secret-safe**: every string leaf passes `secretscan.redact_tree` before
  rendering, so an external artifact that was never compiled here (and so
  never hit the §8 refusal) still cannot leak a secret-shaped value into a
  terminal or log.
- **Provenance**: when the matching report is supplied (its
  `work_spec_sha256` must equal the artifact's recomputed digest, else the
  decompiler refuses with a closed error), each field carries its
  `[explicit]` / `[defaulted]` / `[resolved]` marker and the resolution
  records render as an advisory section.
- **Round-trip claims, precise**: `authoring_view(artifact, report) ->
  dict` reconstructs a normalized authoring input (explicit fields from the
  artifact, requested components from the report's resolution records).
  Frozen claim: `compile_work_spec(authoring_view(a, r), same snapshot)`
  reproduces an artifact with an identical `content_sha256` and an
  identical report body. The display text itself is never parsed back, and
  reconstruction of the author's original input bytes is not claimed —
  normalization legitimately collapses equivalent spellings. No claim
  stronger than this semantic fixed point is made anywhere in U-W1.

## 13. Semantic diff

`semantic_diff(a, b, report_a=None, report_b=None) -> dict` over two
schema-valid WorkSpec artifacts (each validated first; the record binds
`from_sha256` / `to_sha256` recomputed from each body). A supplied report
must digest-bind its artifact — its `work_spec_sha256` must equal that
artifact's recomputed digest, else the diff refuses with a closed error
(the §12 rule) — and the `resolutions` category exists exactly when both
reports are supplied and bound.

- **Typed entries**: `{category, kind, path, from?, to?, from_sha256?,
  to_sha256?}` with `kind` in `added | removed | changed`.
- **Closed categories** (canonical order): `metadata` (identity, envelope,
  timestamps, trace, destinations, inputs), `requirements` (goal,
  acceptance criteria, constraints, required capabilities),
  `authority_references` (`policy_refs.*`), `budgets_limits` (`expires_at`
  and every bound-carrying field), `retry_idempotency` (`retry.*`,
  `idempotency_key`), `classification` (`data_classification`,
  `scope.*`), `resolutions` (present only when both artifacts' compile
  reports are supplied; diffs resolved ids/versions/digests), and
  `result_contract` (`expected_result.*`).
- **Canonical path grammar**: the spine's `_join` grammar — `/`-rooted,
  segments are declared field names and array indices; set-semantics arrays
  (uniqueItems string arrays) diff as item `added`/`removed` at the array
  path; `inputs` entries key by `(ref_kind, sha256-of-ref)`.
- **Deterministic order**: category canonical order, then path code-point
  order, then kind.
- **Secret safety — frozen raw-value allowlist**: raw `from`/`to` values
  appear only for closed-enum, constant, integer, timestamp, and
  structurally-bound identifier paths (`schema`, `protocol_version`,
  `content_hash_alg`, `created_at`, `expires_at`, `issuer`, `audience[]`,
  `scope.project`, `scope.tenant`, `aos_task_id`, `data_classification`,
  `permitted_destinations[]`, `work_spec_id`, `runtime_task_uuid`,
  `trace.*`, `expected_result.result_schema`,
  `expected_result.evidence_kinds[]`, `expected_result.min_evidence_count`,
  `retry.max_attempts`, `retry.deadline_at`, `required_capabilities[]`,
  `inputs[].ref_kind`, `inputs[].sha256`, `policy_refs.*`). Every other
  path — `goal`, `acceptance_criteria[]`, `constraints[]`, `inputs[].ref`,
  `inputs[].note`, `idempotency_key` — diffs by sha256 digest and length
  only. No raw secret value can appear because no free-text value can
  appear.

## 14. Runtime boundary

Frozen, verbatim requirements on the implementation:

- static retry intent (`retry.max_attempts`, `retry.deadline_at`) may be
  validated and cross-checked against resolved manifests (§8);
- zero attempts execute — `workspecs.py` never calls
  `governance.invoke()`, never touches a `BindingRegistry` callable, and
  imports no execution surface;
- zero tasks schedule — no queue, no cron, no event, no run row, no
  handoff row;
- no workflow state persists — no lifecycle field, no state machine, no
  database row of any kind;
- U-W2 owns the deterministic workflow state engine and queue integration;
- U-W3 owns checkpoints, resume, runtime retry, and compensation;
- U-K1/U-T1 `invoke()` remains single-attempt and byte-unchanged.

## 15. Mutation and digest safety

- **Snapshots on intake**: every accepted document (authoring input,
  snapshot passport, artifact presented for lint/decompile/diff) is
  snapshotted by canonical round trip
  (`parse_canonical(serialize_canonical(x))`) before use — the
  `ComponentRegistry`/`EligibilityResult` rule — so a caller-retained
  reference mutated after the call can neither alter a result nor stale a
  digest.
- **Fresh returns**: every returned dict/tuple is freshly built and aliases
  nothing the caller passed in and nothing the module retains; frozen
  dataclasses hold the typed results. Mutating a returned report cannot
  affect a later call.
- **Digest recomputation, no stale attestation**: `work_spec_sha256` in a
  report, `from_sha256`/`to_sha256` in a diff, and the digest a decompiler
  binds provenance to are recomputed from the exact body at emission time
  — never copied from a field the input document carried (`content_sha256`
  inside an input is the thing an attacker would edit; the
  `document_digest` rule).
- **Immutability where practical**: module vocabularies are tuples;
  registries arrive frozen; `WorkSpecSnapshot` is a frozen dataclass over
  immutable indexes.

## 16. Compatibility (all byte-unchanged, proven by the existing suites)

- Existing WorkSpec fixtures (`tests/test_v03_protocol_spine.py::work_spec`
  and every sealed variant) validate and lint exactly as before; the
  compiler emits documents the same fixtures' consumers accept.
- Result Envelope binding (`protocols.verify_binding`) is untouched: a
  compiled artifact binds to result envelopes and interrupts exactly as any
  valid WorkSpec always has.
- Passports, catalog, routing, handoffs, and U-K1/U-T1 governance are
  untouched in code and behavior; U-W1 only reads their public,
  already-frozen surfaces.
- Evidence and secret safety: `secretscan` is reused, not modified; no new
  event payload exists to redact.
- Packaging: `pyproject.toml` untouched — `packages = ["agentic_os"]`
  already ships the one new module; no data file is added.
- CI: `.github/workflows/ci.yml` untouched — `unittest discover` picks up
  the new test file, `compileall` covers the new module, and
  `python3 tools/gen_protocols.py` stays verify-clean because the
  projection does not change.

## 17. Persistence, CLI, and protocol decisions

- **No database**: no table, no migration, no `SCHEMA_VERSION` bump (stays
  `"5"`), no event, no doctor change, no power-policy change. The
  D-v0.4.6 anticipatory-row prohibition applies: U-W2 mints its own
  storage when it exists.
- **No CLI verb**: `aos protocol validate` already validates compiled
  artifacts through registry dispatch; a compile/lint/decompile/diff CLI
  requires an authoring-file format decision and belongs to the wave that
  can justify it. `power.COMMAND_POLICY` is untouched.
- **No dependency**: standard library only, like every unit before it.
- **Protocol reuse**: `beast.work-spec/v1` unchanged — no v2 identity, no
  second WorkSpec schema, no registry growth (`REQUIRED_IDENTITIES` stays
  six), no projection change (the checked-in schema digest
  `07ac96ba08a1579bbd681ab4087156e9d8facf849f3348e0e494658f3acceab9`
  remains exact). The live schema surface (closed fields, static
  `retry` intent, opaque `policy_refs`, inert-by-construction guarantees)
  was verified sufficient for every §5–§13 requirement, so no protocol
  change is needed; if any later U-W1 wave finds one necessary, that is a
  replan condition, not an amendment.

Record schemas minted here (`aos.work-spec-authoring/v1`,
`aos.work-spec-compile-report/v1`, `aos.work-spec-registry-snapshot/v1`,
`aos.work-spec-semantic-diff/v1`) are internal canonical-record payloads in
the established `aos.*` house style (`aos.routing-request/v1`,
`aos.implementation-binding/v1`, `aos.governed-invocation-evidence/v1`) —
deliberately not U-X1 registry artifacts, exactly as those precedents are
not.

## 18. Exclusions

The §0.2 list, verbatim, plus: the Atomic Agents evaluation repository is
not read; no GitHub state, plugin, hook, memory, settings, or other
worktree is modified; no `.claude/**` content is written; scratch material
stays outside the repository.

## 19. Implementation boundary (frozen; exact and exhaustive)

| Path | Status class | Wave |
| --- | --- | --- |
| `agentic-os-v0.4-u-w1-workspec-compiler-contract.md` | new | 0 (this document) |
| `DECISIONS.md` | modified (prepend D-v0.4.59–70) | 0 |
| `agentic_os/workspecs.py` | new | implementation |
| `tests/test_v04_workspec_compiler.py` | new | implementation |
| `README.md` | modified (one new unit section) | implementation |

Disfavored and expected untouched (necessity would be live-evidence-proven,
and none was found): `agentic_os/protocols.py`, `protocols/**`,
`tests/test_v03_protocol_spine.py`, `agentic_os/cli.py`,
`agentic_os/db.py`, `agentic_os/migrations.py`, `agentic_os/power.py`,
`.github/**`, `pyproject.toml`.

Any path outside the five-row table above appearing in any later U-W1 wave
is `FAIL — REPLAN REQUIRED`, not a quiet extension.

## 20. Test matrix (frozen; `tests/test_v04_workspec_compiler.py`)

- **Deterministic compilation**: identical `(authoring, snapshot)` →
  byte-identical artifact and report across repeated calls; digest
  stability under authoring key reordering and array reordering
  (input-order independence).
- **Derivations**: defaulted `work_spec_id` / `idempotency_key` / `trace`
  are stable, schema-valid, independent of each other's explicit presence,
  and the all-zero trace guard is exercised directly.
- **Numeric version selection**: `v9` vs `v10` ordering; exact pin resolves
  exactly; unpinned resolves highest and warns `unpinned_requirement`.
- **Provenance**: every emitted field maps to exactly one class; explicit
  vs defaulted vs resolved proven per field; `defaults_applied` exact.
- **Malformed/unknown fields**: unknown key, wrong type, bound violation,
  forbidden compiler-owned key, non-data value
  (`unsupported_dynamic_behavior`), non-dict input.
- **Every reason code**: each of the 25 `WORKSPEC_LINT_CODES` produced at
  least once positively and once negatively; status precedence pinned
  (co-occurring classes yield the highest); canonical finding order pinned
  against a shuffled-input compile.
- **Duplicates/ambiguity**: duplicate array items, duplicate input refs,
  duplicate requests, contradictory version requests, case-folded snapshot
  collision refusal.
- **Lifecycle/promotion**: inactive agent, deprecated/draft/revoked
  manifest, unpromoted skill — each resolves and earns its finding.
- **Dependency blocking/cycles**: transitively blocked dependency →
  `dependency_blocked`; a cyclic skill set refuses at snapshot build with
  governance's `dependency_cycle`.
- **Authority separation**: compile output contains no grant field; report
  never marks approval/budget/policy satisfied;
  `approval_reference_required` appears exactly when declared expectations
  meet an absent reference; artifacts with `approval_ref` still earn no
  authority claim anywhere in any U-W1 output.
- **Classification monotonicity**: authored classification emitted exactly;
  mismatching and absent passport declarations fail closed; no path
  lowers or raises a classification.
- **Secret non-echo**: secret-shaped goal/criteria/input refuses compile
  with pattern names only; decompile of an external secret-shaped artifact
  renders the fixed redaction marker; diff of free-text changes carries
  digests, never values.
- **Decompile determinism/bounds**: byte-identical output across calls;
  truncation marker exact at the 120-code-point bound; report-mismatch
  refusal; provenance markers rendered.
- **Semantic-diff determinism/secret safety**: canonical order pinned;
  raw-value allowlist enforced path by path; digests recomputed (a lying
  embedded `content_sha256` cannot steer the diff); report-mismatch
  refusal pinned (a supplied report whose `work_spec_sha256` does not
  match its artifact refuses the diff).
- **Snapshot/alias safety**: mutating authoring input, snapshot documents,
  or returned reports after the call changes nothing observable.
- **Existing-fixture compatibility**: the spine's `work_spec()` fixture
  lints `valid` with no requests; a compiled artifact passes
  `protocols.validate_document` and `verify_binding` against a result
  envelope built on it.
- **No network/filesystem/dynamic import/execution**: `workspecs.py`
  imports no `socket`/`urllib`/`subprocess`/`importlib`; no `open()` in
  the compile path; module import performs no I/O (asserted by test).
- **No scheduling/invocation**: no call into `governance.invoke`,
  `events`, `db`, or any CLI surface (asserted by import graph).
- **Unchanged protocol projection**: `python3 tools/gen_protocols.py`
  verify-clean; `REQUIRED_IDENTITIES` still six; the work-spec schema
  digest still
  `07ac96ba08a1579bbd681ab4087156e9d8facf849f3348e0e494658f3acceab9`.

## 21. Verification (implementation wave)

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q agentic_os tests tools aos.py aos_hooks.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_workspec_compiler
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
python3 tools/gen_protocols.py
python3 tools/verify_ci_workflow.py
git diff --check
```

## 22. Delivery identity

- Branch: `v0.4-u-w1-workspec-compiler`
- Worktree: `/home/daksh/Projects/agentic-os-u-w1`
- Base: `8cf82432d4c137d4a1513f9daee39cc3ee0be92b`
- PR title: `feat(v0.4): U-W1 — deterministic WorkSpec compiler`
- Tag after merge: `milestone/v0.4-u-w1-workspec-compiler`
- Delivery flows through the U-P2 protected gate (PR + required checks);
  Wave 0 itself stages nothing, commits nothing, and pushes nothing.

## 23. Known limitations (declared, not discovered later)

- `scope.tenant` is format-validated and uninterpreted; multi-tenant
  semantics are a later unit's.
- Snapshot lifecycle facts are caller-attested; U-W1 ships no ledger
  reader, so a caller can attest a stale lifecycle — findings are advisory
  and runtime governance re-decides regardless.
- Lint statics cover the requested ensemble only; the v1 protocol carries
  no assignment fields, so an artifact linted without requests earns only
  artifact-static gates.
- The compile report and diff are `aos.*` canonical records, not U-X1
  registry artifacts; cross-system exchange of reports would need a later
  protocol decision.
- The `governance.invoke()` docstring's "(U-W1)" attempt-loop phrase
  remains in prose until a unit that modifies `governance.py` retouches
  it; D-v0.4.59 supersedes its meaning without a code edit.
- No natural-language authoring, no CLI, no persistence, no scheduling —
  by design, per §0.2 and §17.

*This contract is the audit surface for U-W1: an implementation behavior
the sections above do not license is a defect, whichever file it lives
in.*
