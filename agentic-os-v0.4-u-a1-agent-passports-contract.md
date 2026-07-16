# Agentic OS v0.4 — U-A1: Agent Passport v1 and the governed agent registry

Status: executed.
Baseline: 2d242ab743f3456d7815f1f2fff6e82e2b8ca7f9 (U-M5, schema version 3).
Branch: `v0.4-u-a1-agent-passports`. Decisions: D-v0.4.1 – D-v0.4.13.
Extends U-X1 (protocol spine / canonical JSON), U-M1 (migrations),
U-M2/U-M3 (record-hash discipline), U-E2 (power modes), U-C3 (secret
safety), U-P1 (packaging).

U-A1 replaces the ungoverned v3 `agents` scratchpad with a **governed agent
registry**: one canonical identity table, an immutable history of versioned
**passports** (`beast.agent-passport/v1` protocol artifacts), a lifecycle
state machine, a 3→4 migration that carries legacy rows verbatim and
fabricates nothing, and the no-laundering integrity gate on every
authoritative agent write.

**Everything a passport declares is inert stored text.** No resolver, no
router, no scheduler, no executor, no credential field, no approval grant.
`autonomy` is consumed by no code path. Agentic OS still never executes
agents.

---

## A1.0 Scope

### In scope

`agentic_os/passports.py` (domain ops, hashes, gate); the v4 `agents` +
`agent_passports` schema (`db.py` constants shared by init and migration);
`beast.agent-passport/v1` embedded in `protocols.py` with its checked-in
projection; migration `u-a1-agent-passports-v4`; CLI verbs
`agent create|import|list|show|export|passport publish|passport history|
suspend|archive|restore|revoke|discard`; power classification for every new
leaf; doctor check 13 rewrite + checks 32–34 + passport-document secret
sweep; mirror agent notes; fixtures (v3 new; v1/v2 agents downgrade);
`tests/test_v04_agent_passports.py`; documentation.

### Explicitly NOT in scope (deferred, and refused if asked for)

- **U-A2**: specialist records, prompts, system-agent minting
  (`owner='system'`, `protected=1` setters, the reserved-name rows).
- **U-K1/U-T1**: skill/tool manifests and any resolution of a declared
  requirement. **U-A3**: routing. **U-R1**: scheduling/execution.
- **U-S5/U-Q1**: cryptographic signatures and signed packages — the content
  digests and provenance fields are the substrate they will sign; no field
  pretends to be a signature today.
- **U-S2**: credentials/secret storage. Credential-shaped property names are
  structurally unrepresentable in the schema instead.
- Any runs/handoffs/provenance FK retrofit: those stay free text.
- MCP/A2A (U-T2–U-T4); AICompany; autonomy execution of any kind.

### Untouched

`retrieval.py`, `hooks.py`, `ingest.py`, `pack.py`, `search.py`,
`backup.py`, `export.py`, `mirror_export.py`, `review.py`, `ids.py`,
`utils.py`, `events.py`, entrypoints, `tools/`; the three existing
`protocols/beast.*/v1.schema.json` files (byte-identical, tested); all
U-M1/M2/M3 migration step bodies; memory and retrieval behavior.

---

## A1.1 Data model

`agents` (v4): identity + governance columns (`agent_class`, `scope` +
`project_id`, `lifecycle`, `protected`, `owner`, `origin`,
`current_passport_version`, timestamps, identity `content_sha256`) plus the
five v3 columns carried verbatim as permanently inert history. CHECKs pin
every vocabulary; a composite FK pins the current-passport pointer to a real
`(agent_id, version)` of the same agent; NULL pointer = draft/legacy.

`agent_passports`: `(agent_id, version)` UNIQUE; `status` draft|published
with `published_at` iff published; `document` holds the exact canonical
bytes of a valid `beast.agent-passport/v1` artifact; `content_sha256` is the
ROW record hash. Published rows are never updated or deleted; the system's
only DELETE path is draft discard.

No `CREATE INDEX` (D-v0.3.45). Reserved names/prefixes are frozen tuples in
`models.py`, refused at create/import — no reserved rows exist until U-A2.

## A1.2 Protocol

`beast.agent-passport/v1`: reduced envelope (schema, protocol_version,
content_hash_alg, content_sha256, created_at, issuer; optional expires_at,
data_classification — deliberately no task fields); body identity
(`agent`, `passport_version` — both hash-bound), `agent_class`,
`agent_scope` (project iff level=project, cross-field checked), `role`,
`mission`, `autonomy`, `escalation`, `provenance`, and bounded optional
declarations (task_families, protocols, capabilities, skill/tool
requirements, provider_compat, model_requirements, memory_scopes,
data_classifications, approvals_required, evidence_expectations,
evaluation_refs, limitations, limits). All objects
`additionalProperties:false`; all arrays unique; credential-shaped names
unrepresentable. `_check_semantics` guards field-specific checks on
PRESENCE, so the three task-message schemas keep byte-identical behavior.

## A1.3 Migration 3→4 (`u-a1-agent-passports-v4`)

Inside the unchanged U-M1 frame. Rebuilds `agents` from the live v4 DDL;
carries every v3 field verbatim (no trimming, parsing, case-folding, or
length judgment); stamps constants + one clock reading; `origin='legacy'`;
computes identity hashes; creates `agent_passports` EMPTY — **no passport is
synthesized**. A row that cannot be hashed fails the step by `agent #id` +
field name (never a value) and rolls back completely. The v3 agents DDL is
frozen as `_V3_AGENTS_DDL` (fixtures build from it; a regression test
byte-compares a 2→3-migrated database against it and the live memory DDL).

## A1.4 Lifecycle

draft →(publish)→ active ↔ suspended; active|suspended → archived →
restore; active|suspended|archived → revoked (**terminal**). Publish
requires draft|active (parked identities cannot gain versions). Protected
refuses suspend/archive/revoke/discard; no U-A1 command sets the flag.
Discard: never-published, never-referenced drafts only; the event survives.
Same-state transitions are refusals naming the state.

## A1.5 Integrity (the no-laundering gate)

Three bindings — document digest (U-X1), passport row hash
(`aos.agent-passport-record/v1`, binding a recomputed document digest to
agent_id/version/status/timestamps), identity hash
(`aos.agent-identity/v1`, binding lifecycle/pointer/legacy fields). Every
authoritative agent write verifies all three plus history shape
(contiguity, ≤1 draft only as (v1, draft-lifecycle), pointer → published)
before mutating; verdicts are the closed set ok/malformed/mismatch/
unhashable/history_gap/draft_shape/pointer_invalid. Reads still display,
with verdicts; doctor FAILs; recovery is the exit.

## A1.6 Security

Import/export through `protocols.read_artifact_bytes` (lstat, O_NOFOLLOW,
size bounds, fd identity re-check); documents are bytes → dict →
refusal-or-rows — nothing an artifact names is opened, fetched, resolved or
executed. Free-text fields (role, mission, limitations, approvals, task
families) get the warn-on-write scan under new TRUSTED_FIELD_LABELS; event
payloads carry only names (redacted at emit), ids, closed enums, integer
versions and 12-char hash prefixes — never role/mission/documents/full
hashes. The doctor sweep scans stored passport documents under
`agent #id passport vN` labels.

## A1.7 Doctor

Check 13 validates the governed v4 shape (still reporting legacy kind /
capabilities_json hazards). New: 32 identity hashes verify (FAIL), 33
passport history intact (FAIL) — both feed the recovery gate — and 34
active agents without a published passport (WARN, never fatal). 31 → 34
checks; stdout stays entrypoint-identical.

## A1.8 Proof

`tests/test_v04_agent_passports.py` (64 tests): migration preservation and
governance-of-nothing, injected failure + rollback + corrected retry,
damaged-row refusal, frozen-history byte-comparison, fresh/migrated schema
identity, passport validation edges, registry semantics (create → publish →
export → import round-trip, N+1 versions, history), lifecycle matrix,
protected/reserved refusals, discard guards, tamper/no-laundering, event
allowlist, doctor at 34 with recovery-gate integration, classification and
entrypoint parity. Full regression green; zipapp parity proven; dogfood
drill (two workspaces + migrated v3 fixture) clean.
