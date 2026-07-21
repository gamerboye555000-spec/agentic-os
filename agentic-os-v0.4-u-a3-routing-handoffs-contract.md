# Agentic OS v0.4 — U-A3: Governed Agent Routing and Handoff Contracts

Contract-freeze pass (Wave 0). Baseline `80b7e82577cbed19aa1823934df44ae09a644ac5`
(U-A2, schema v4). Branch `v0.4-u-a3-routing-handoffs`. This document reconciles
the approved design (`U-A3-routing-handoffs-design.md`, sha256
`58ae33340b0d28ff1e2a4dec78148b9b28dc8da0e45da7d05afa7971041b9cc4`) with the
independent audit (`U-A3-routing-handoffs-audit.md`, verdict **ADOPT WITH
REQUIRED CORRECTIONS** — 3 blockers, 6 majors, 9 minors) into a single
implementation-ready contract. Every blocker and major correction is
discharged in this text; §29 is the checklist proving it. Nothing in this
document is implemented by writing it — it is the gate later waves must
satisfy. No implementation model reading this contract should need to make an
architectural decision.

---

## 1. UNIT IDENTITY

- **Unit**: U-A3 — Governed Agent Routing and Handoff Contracts.
- **Baseline**: `80b7e82577cbed19aa1823934df44ae09a644ac5` (U-A2, schema v4).
- **Schema version**: 4 → **5**. One additive migration
  (`u-a3-routing-handoffs-v5`), four new tables, zero rows touched, zero rows
  fabricated.
- **Architecture retained from the design, verbatim**: a distinct governed
  agent-handoff model separate from the legacy `handoffs` table; schema v5;
  four new tables; zero new U-X1 protocols; deterministic advisory routing;
  post-commit immutable routing plans and candidate rows; append-only handoff
  transition history plus a mutable current-state projection; derived plan
  staleness; successor-created supersession; no `route select` leaf; no
  `completed` handoff state; no execution, provider, scheduler, workflow,
  tool or skill runtime.
- **Corrections applied**: all 3 blockers, all 6 majors, all 9 minors, and
  the structural corrections named in §29's checklist. None of them changes
  the architecture above — every one is a bounded DDL, vocabulary, or wording
  fix, exactly as the audit's verdict states.

## 2. PURPOSE AND NON-GOALS

**Purpose.** U-A3 adds the smallest governed substrate that can *declare*
routing and delegation without *performing* either:

1. **Routing plans** — an immutable-after-commit, deterministically ordered,
   fully explainable advisory record of which installed agent identities are
   eligible for a described task, and in what order they would be tried.
2. **Governed agent handoffs** — a human-authored delegation declaration
   between two logical agent identities, with an append-only transition
   history and a mutable, hash-coupled current-state projection.

**Non-goals** (explicit, structural, and permanent unless a future unit earns
a change with its own decision record):

- no execution, no provider access, no scheduler, no workflow engine, no
  tools runtime, no skills runtime, no credentials, no spend;
- no `agent route select` — explicit human selection *is* handoff creation
  referencing a plan; a second record for "selection" would duplicate state;
- no `completed` handoff state and no completion-evidence binding —
  completion is an execution-outcome fact, and U-A3 ships no runs/evidence
  binding to make that claim honestly;
- **no governed approval primitive.** `decision_id` on a handoff is an
  optional, non-authoritative pointer to the architecture-decision record
  that explains *why* a delegation was declared — never an approval, never
  authorization, never consent, never a grant, never a policy decision, never
  an execution permission. Agentic OS currently has no governed approval
  primitive for these handoffs, and this unit does not build one;
- no authority ladder over `autonomy` — it is a closed, **unordered**
  membership vocabulary; no rank function exists or is proposed;
- no new U-X1 protocol identity — routing requests, plans, handoffs and
  transitions are internal, workspace-local records that cannot travel
  between workspaces and therefore have no interoperability surface to
  justify one;
- no new indexes without measured evidence (§10, §17.1);
- no mutation of the legacy `handoffs` table, its two CLI leaves, its events,
  its mirror notes, or its `H-` id prefix — it remains byte-identical;
- no mutation of `protocols.py`, any `protocols/beast.*/v1.schema.json` file,
  `protocols/registry.json`, `catalog.py`, any catalog artifact, or the U-A1 /
  U-A2 contracts;
- no orchestration consumption of plans or handoffs by any hook, doctor path,
  sync path, or power transition — the eleven CLI leaves in §17 are the only
  code paths that touch the four new tables.

## 3. DISPOSITION OF THE EXISTING TASK-HANDOFF TABLE

The existing `handoffs` table (session-continuation notes on a task) is
**left byte-identical and untouched**. It has `from_agent`/`to_agent` as free
text never validated against `agents` (`ops.create_handoff` strips and
checks non-empty only, ops.py:813), no CHECK constraints, no content hash,
and a mutable `accepted_at`. Its two-state lifecycle carries no authority
meaning: nothing reads it to permit anything.

**Chosen: a distinct governed agent-handoff model** (`agent_handoffs` +
`agent_handoff_transitions`), justified against every alternative:

- **Extend the legacy table** — rejected. Adding FKs to `agents`, pinned
  passport versions, a state CHECK, a content hash, and transition history
  onto a table whose historical rows can satisfy none of them would either
  make every existing row permanently malformed under the new rules, or
  require the migration to fabricate identities and pins for free-text
  names — exactly the fabrication D-v0.4.4 forbids ("would put a guess into
  the ledger wearing the same clothes as a fact"). A mutable `accepted_at`
  also contradicts the durability principle this unit adopts (§4, clause 8).
- **Canonical artifacts, no relational state** — rejected. Loses FK
  integrity for participants/tasks/passports, loses SQLite's concurrency
  control for the accept/refuse compare-and-swap, turns doctor verification
  into a filesystem walk, and exits the backup/snapshot perimeter (`aos.db`
  is what backup and migration snapshot). Nothing here needs cross-workspace
  exchange to justify the cost.
- **Any other minimal design** — no cheaper alternative preserves FK
  integrity and CAS concurrency; events alone cannot carry either.

The legacy table, its two CLI leaves (`handoff create`/`accept`), its events,
its mirror notes (render.py, obsidian.py), and its `H` id prefix remain
byte-identical and continue to mean exactly what they mean today. D-v0.4.20
explicitly reserved this ground for U-A3 ("starts from a clean slate"); this
contract honors that literally.

## 4. INVARIANTS

All 24 mission invariants are adopted verbatim as contract clauses. The
following restatements are what this architecture enforces mechanically —
corrected against the audit where the design's wording drifted from its own
reasoning:

1. **Advisory-only routing.** No code path reads a plan or handoff to
   authorize anything. The only consumers beyond display and doctor are (a)
   handoff-create's check that the recipient is a member of the referenced
   plan's eligible set — a consistency rule the human can always bypass by
   omitting `--plan`, never a permission — and (b) accept's check that both
   participants' pins are still current, which blocks a stale accept, not an
   unapproved one.
2. **Eligibility is uniform.** Eligibility requires: row exists ∧
   `lifecycle='active'` ∧ `agent_integrity(agent)=='ok'` ∧
   `history_problems==[]` ∧ `current_passport_version` NOT NULL (invariant 3);
   identical for user-created, imported, legacy and catalog identities
   (invariant 4); `owner`, `protected`, `origin`, catalog membership and
   manifest maturity never enter eligibility or ordering (invariant 5).
3. **Determinism.** Eligibility and ordering are pure functions of
   (canonical request document, agent rows, passport documents) — never of
   row ids, insertion order, wall clock, usage, availability, price or
   randomness (invariants 8, 10). The same request against an equivalent
   snapshot yields the same ordered `(name, version, digest, reasons)`
   sequence in any workspace.
4. **Pinning, never rewriting.** Every eligible candidate row and both
   handoff sides pin an exact passport version, recomputed document digest,
   and identity digest at write time. Later changes are detected as
   *staleness* — a derived, read-time predicate — never rewritten into
   history (invariants 12, 13).
5. **No authority transfer.** The schema has no column any code path reads
   to permit execution, approval, spend, credential access, provider access,
   tool/skill grant, data access, or lifecycle control (invariant 15).
   `decision_id` is a rationale pointer to an existing `decisions` ADR row —
   descriptive only, never authoritative. **Agentic OS currently has no
   governed approval primitive for these handoffs.**
6. **Humans act; identities participate** (invariant 16). Every event actor
   is `ops.ACTOR_HUMAN`. "Accept" records the operating human's decision on
   behalf of the recipient *logical* identity; no participant ever "acts" by
   itself.
7. **Privacy.** Objective/constraints/note prose lives only in relational
   rows, is warn-on-write scanned, swept by doctor, and never enters events,
   doctor details, or diagnostics (invariant 17).
8. **Durability.** Routing plans and candidate rows are **post-commit**
   immutable: the only UPDATE either table ever receives is the hash
   finalization inside the row's own creating transaction, between INSERT
   and COMMIT (§12). A handoff's current-state projection
   (`state`/`updated_at`/`content_sha256`) is the one mutable surface on an
   otherwise immutable row, and it only ever moves together with one
   immutable transition row and one event, in one transaction (invariant 18).
   Recovery blocks all **six** write leaves before dispatch (invariant 19).
9. **Schema v5 is required, not convenience.** Four new governed tables with
   FKs and CHECKs are required because no existing table can express
   composite passport pins, transition chains, or candidate uniqueness
   (invariants 21/22). No new protocol identity is introduced (invariant
   23). Nothing installs catalog entries — `catalog_not_installed` is a
   refusal message, never an install trigger (invariant 24).
10. **Vocabulary honesty.** A closed enumeration is either genuinely ordered,
    carrying an explicit authoritative-order warrant (the
    `MEMORY_SENSITIVITIES` shape, models.py:36–41), or it is explicitly
    **unordered**, carrying a comment saying so. `AGENT_AUTONOMY_LEVELS` is
    the latter: its tuple order is presentation-only, matched by membership,
    and no rank function exists over it.
11. **Exact-match gates share one shape.** Every `required_*` request field
    (`required_scope`, `required_agent_class`, `required_autonomy`,
    `required_data_classification`) gates by set membership or exact
    equality — never by inferred rank. Where a dimension's passport
    declaration is optional, the JSON diagnostic distinguishes "declared
    without this value" from "declared nothing at all" via `declared: false`
    wherever that ambiguity can occur (§7).
12. **Structural completeness over after-the-fact detection.** Where a
    domain rule fits a CHECK constraint — the `result_status` biconditionals,
    the accepted-state's legal-target restriction, supersession acyclicity,
    candidate pin biconditionality — it is written as one, following
    `MEMORY_EDGES_DDL`/`MEMORY_SOURCES_DDL`'s precedent that a rule the
    domain layer enforces should also be unstorable by raw SQL. Doctor
    remains the backstop for what SQLite genuinely cannot express: sequence
    contiguity, chain replay, and cross-row equivalence.

## 5. VERIFIED EXTENSION POINTS

Every citation below was independently re-verified against this baseline
during this contract pass (§ preflight). Corrected against the audit's
MINOR-6 finding where noted.

1. **Identity + passport reads**: `passports.get_agent` (passports.py:298),
   `list_passports` (:303), `get_passport` (:313) — the only reads U-A3
   eligibility needs.
2. **Integrity verdicts**: `passports.agent_integrity` (:224),
   `passport_integrity` (:285), `history_problems` (:477) — reused verbatim
   as the tamper gates behind `identity_tampered` / `passport_history_tampered`.
3. **Document digest**: `passports.document_digest` (:239) recomputes a
   stored passport's U-X1 digest — the function used to pin `passport_sha256`
   in plans and handoffs.
4. **Canonical JSON + digest**: `protocols.serialize_canonical` (:203),
   `parse_canonical` (:315), bounds (`MAX_ARTIFACT_BYTES` 262144, string/array
   bounds :52–61) — the request document serializer and its limits.
5. **Transaction frame**: `db.transaction` (db.py:463, `with conn:` — commits
   on exit, never nested per D-v0.4.18) and the `BEGIN IMMEDIATE` +
   in-transaction re-read pattern (catalog.py:811 ff.).
6. **Events**: `events.emit` (events.py:30) — one choke point, `redact_tree`
   on payload and actor, `{"schema_version": 1}` envelope; U-A1 payload style
   (agent name, integer version, `passport_sha256_prefix`, from/to lifecycle).
7. **Secret boundary**: `ops._scan_trusted_write` (ops.py:74) with
   `secretscan.TRUSTED_FIELD_LABELS` (secretscan.py:58) — warn-on-write for
   trusted human prose; labels are a closed set doctor also trusts.
8. **Power**: `power.COMMAND_POLICY` (power.py:141) keyed by argparse path
   tuples; `RECOVERY_ALLOWED_KINDS` (:112); degradation `MATRIX` (:773); deep
   wrap via `deep_check` (:678) applied to `authoritative_write` +
   `ledger=True` leaves; coverage enforced by
   `test_v02_power_modes.py:441` (`test_every_cli_leaf_has_exactly_one_classification`).
9. **Doctor**: `Check` records with `warn_only`, bounded details via
   `UH2_DISPLAY_LIMIT` (doctor.py:115, value 10 — **not** reused for routing
   reason truncation, see §7's `ROUTING_REASON_DISPLAY_LIMIT`), single-purpose
   checks 32–34 (`_agent_registry_checks`, :905) and 35–37 (`_catalog_checks`,
   :1135); count pinned at 37 (`test_v04_agent_catalog.py:2220`,
   `test_v04_agent_passports.py:1127`).
10. **Migration frame**: `migrations.Migration` records
    (from_version/to_version/migration_id/apply), registry `MIGRATIONS`
    (migrations.py:515), apply frame with pre-mutation verified snapshot,
    `foreign_keys=OFF` + full `foreign_key_check`, single commit
    (`apply_migrations`, :917 ff.); shared-DDL rule is **D-v0.3.42** ("building
    from the one fresh-DDL constant is what makes a migrated table and a
    born table the same table") — **not** D-v0.3.43, which is the unrelated
    "no provenance is invented during migration" rule. Both apply to this
    unit; neither is the other.
11. **IDs**: `ids.PREFIXES` (ids.py:17) — two-letter prefixes already
    precedented (`MS`/`ML`/`ME`); strict parse with `MAX_ID`. Current entries
    (`T,R,D,E,H,P,M,MS,ML,ME`) do not collide with the new `RP`/`AH`.
12. **Vocabulary home**: `models.py` — closed tuples + CHECK-constraint
    pairing, ordered-ladder precedent `MEMORY_SENSITIVITIES` +
    `sensitivity_rank` (models.py:36–41, :141) — the pattern U-A3's
    `AGENT_AUTONOMY_LEVELS` deliberately does **not** follow (§7).
13. **Discard guard**: `passports._REFERENCE_QUERIES` (:1108) — documented as
    "every place a historical **textual** reference to an agent **name** can
    live"; its param builders receive only the name (`lambda n: (n,)`,
    passports.py:1166). U-A3 extends it with a **name-joined** query, not an
    id-based one (corrected from the design's "id-based" description —
    MINOR-6; §21).
14. **Contradiction check**: none found. D-v0.4.20 states routing/handoff
    graphs "remain explicitly assigned to a future unit (U-A3), which starts
    from a clean slate" — this contract follows that literally.

## 6. ROUTING REQUEST CONTRACT

One canonical request document per plan. **Requests may be standalone**
(`task` optional): routing is advisory exploration and may precede task
creation; a handoff, by contrast, requires a task (§13). The request is a
closed-key JSON object, canonicalized by `protocols.serialize_canonical`,
digested by sha256 over those bytes (`request_sha256`), stored verbatim in
the plan row. **No timestamp and no actor appear inside the document** — two
identical requests must hash identically; `created_at`/`actor` live on the
plan row.

Unknown keys refuse. Every array: sorted by code point at CLI-authoring
time; **duplicates refuse loudly**. No case folding, no Unicode
normalization anywhere. All fields optional unless marked required; an
absent hard-requirement field means "this dimension is unconstrained"
(neutral: it neither gates nor orders).

### A. Identity and snapshot

| field | type / vocabulary | req | default | bound | eligibility | ordering | display-only |
|---|---|---|---|---|---|---|---|
| `request_schema` | const `"aos.routing-request/v1"` | yes | CLI-authored | — | version gate | no | no |
| `algorithm_version` | const `"aos-routing-order/v1"` | yes | CLI-authored | — | no | pins the tuple | no |
| `task` | int (task id; from `--task T-…`) | no | absent | 1..MAX_ID; must resolve | no | no | no |
| `project` | slug (`models.SLUG_RE`) | no | derived from task's project when task given | ≤64; must resolve | scope context for `project_mismatch` / scope specificity | T2 context | no |

Request ID: there is none apart from the plan — a request exists only as the
document embedded in exactly one plan. Conflict rule: `--task` and
`--project` both given and disagreeing → refusal before any write.

### B. Hard requirements (each optional; present ⇒ gate)

| field | type / vocabulary | bound | normalization | eligibility effect |
|---|---|---|---|---|
| `task_families` | array of strings, passport `task_families` pattern `^[a-z][a-z0-9._-]{1,63}$` | 1..16 items | sorted, dup-refused | every item ∈ passport `task_families`, else `missing_task_family` |
| `capabilities` | array, passport `capabilities` pattern | 1..16 | sorted, dup-refused | ⊆ passport `capabilities` else `missing_capability` |
| `evidence_kinds` | array from `models.EVIDENCE_KINDS` | 1..6 | sorted, dup-refused | ⊆ passport `evidence_expectations.evidence_kinds` else `missing_evidence_kind` |
| `required_data_classification` **(renamed — MAJOR-4)** | enum, value-identical to `models.MEMORY_SENSITIVITIES` / `protocols.DATA_CLASSIFICATIONS` / the passport body's `data_classifications` item enum, pinned equal as a **set** across all three by test | — | — | requested level must be a **member** of the agent's declared `data_classifications` set — including when the agent declared no set at all — else `data_classification_mismatch`. Membership only; **never a ceiling, never clearance, never rank inference.** `declared: false` distinguishes "declared no set" from "declared a set without this level." |
| `required_autonomy` **(renamed — BLOCKER-2)** | array of 1..4 **unique** values from `AGENT_AUTONOMY_LEVELS` (closed, **unordered**) | 1..4 items, sorted, dup-refused | membership matching only | the agent's declared passport `autonomy` must be a **member** of the requested set, else `autonomy_mismatch`. `autonomy` is `required` in `beast.agent-passport/v1`, so it is never absent — no `declared: false` case exists for this dimension. **No ordering, no ranking, no ceiling; no `autonomy_rank` function exists anywhere in this codebase.** |
| `required_scope` | enum `AGENT_SCOPES` | — | — | `project` ⇒ agent must be project-scoped to the request project (`scope_mismatch` for global agents); `global` ⇒ agent must be global. Echoes the passport schema's own words for `agent_scope.project`: **"a filing statement, never an access grant."** |
| `required_agent_class` | enum `AGENT_CLASSES` | — | — | exact match else `agent_class_mismatch` |
| `skills` | array, passport `skill_requirements` pattern (incl. optional `/vN`) | 1..16 | sorted, dup-refused | byte-exact ⊆ passport `skill_requirements` else `missing_skill_declaration` |
| `tools` | array, passport `tool_requirements` pattern | 1..16 | sorted, dup-refused | ⊆ passport `tool_requirements` else `missing_tool_declaration` |
| `model_capabilities` | object `{min_context_tokens?: int 1..99999999, modalities?: array 1..4 of (text,code,image,audio)}`, closed keys, ≥1 key | — | modalities sorted, dup-refused | declared `model_requirements` must have `min_context_tokens ≥` requested and `modalities ⊇` requested; absent/insufficient declaration ⇒ `missing_model_capability` |

Absent *passport* declaration for a *present* request dimension ⇒ the
corresponding `missing_*` code, or `data_classification_mismatch` for that
one dimension (it has no `missing_data_classification` code — MAJOR-4: it is
the only optional declaration with a name collision risk, resolved by the
rename above, not by a new code). "Did not declare" and "declared without
it" both honestly fail the gate; the JSON diagnostic distinguishes them via
`declared: false`. This applies to the six `missing_*` codes and to
`data_classification_mismatch`; no other hard_ineligible code has this
ambiguity — `agent_class` and `scope` are NOT NULL columns on `agents`, and
`autonomy` is a required passport field, so none of the three can be absent.

### C. Preferences (never gates)

| field | type | default | effect |
|---|---|---|---|
| `preferred_agent` | agent name (`AGENT_NAME_RE`) | absent | must resolve at validation, **else a request-level refusal, never a stored candidate** (§7): plain "No agent" for unknown names (`agent_absent`); `catalog_not_installed` when the name is an uninstalled catalog entry — pointing at `agent catalog install`, never installing. Ordering component T1; non-preferred eligible candidates get `preferred_agent_mismatch` (preference_only, never changes verdict). |
| `scope_preference` | `specific_first` \| `none` | `specific_first` | enables/zeroes T2 |
| `surplus_policy` | `minimal` \| `ignore` | `minimal` | `ignore` zeroes T3–T6 |

Maturity preference: **rejected** (§8).

### D. Output controls (display-only; stored for reproducibility of display)

| field | type | default | bound | status |
|---|---|---|---|---|
| `max_candidates` | int | 5 | 1..32 | display-only: caps *printed* eligible rows; storage always keeps the full ranked set |
| `include_diagnostics` | bool | true | — | display-only: whether text output prints excluded/unresolved rows; `--json` always carries everything |

Tie-break policy field: **rejected** — exactly one tie-break exists and the
`algorithm_version` string pins it; a selectable field would be
configuration theater.

### E. Forbidden content — structurally unrepresentable

The request has **no free-prose field at all**: every value is a
closed-vocabulary enum, a pattern-bound short string, a bounded integer, or a
resolved reference. Executable prompts, credentials, provider configuration,
tool arguments and runtime instructions cannot be expressed because no key
accepts them and unknown keys refuse. All pattern-bound strings still pass
`ops._scan_trusted_write` (labels `task_family`, `capabilities`, `agent`,
`slug` — existing `TRUSTED_FIELD_LABELS` members) so a secret-shaped string
warns and is redacted from events exactly as everywhere else.

Evaluation bound: plan creation refuses when the `agents` table holds more
than `MAX_ROUTING_EVALUATED_AGENTS = 256` rows, with an actionable message —
never a silent truncation of the explanation set.

**Request-level refusals** (never part of the request document itself, never
stored — §7): `agent_absent`, `catalog_not_installed`, both triggered only by
`preferred_agent` resolution, both producing zero rows and zero events.

## 7. ELIGIBILITY MODEL AND REASON CODES

Two closed vocabularies, kept structurally separate because the DDL makes
them semantically separate (MAJOR-5): one names conditions an **existing
agent row** can earn; the other names refusals that mean **no agent row
exists to name**.

```python
# ── models.py ──────────────────────────────────────────────────────────────

#: Codes STORABLE in routing_plan_candidates.reasons_json / warnings_json.
#: This order IS the canonical emission order. 24 codes — exactly the codes
#: an EXISTING agent row can earn.
ROUTING_REASON_CODES = (
    # integrity (hard_ineligible)
    "identity_tampered", "passport_history_tampered",
    # lifecycle (hard_ineligible)
    "draft_only", "suspended", "archived", "revoked",
    "legacy_without_passport", "no_current_published_passport",
    # scope / class (hard_ineligible)
    "project_mismatch", "scope_mismatch", "agent_class_mismatch",
    # declarations (hard_ineligible)
    "data_classification_mismatch",          # incl. declaration ABSENT
    "autonomy_mismatch",                     # membership only, never a rank
    "missing_task_family", "missing_capability", "missing_evidence_kind",
    "missing_skill_declaration", "missing_tool_declaration",
    "missing_model_capability",
    # malformation (unresolved)
    "malformed_declaration", "unknown_declaration_value",
    # preference (preference_only)
    "preferred_agent_mismatch",
    # advisory (warning_only)
    "passport_expired", "catalog_upgrade_available",
)

#: REQUEST-level refusals. NEVER STORED. An absent agent and an uninstalled
#: catalog entry have no `agents` row, and routing_plan_candidates.agent_id is
#: NOT NULL with an FK to it — these are UNSTORABLE BY CONSTRUCTION, which is
#: why they are not in ROUTING_REASON_CODES. They select which refusal
#: message `agent route plan` prints, and name the refusal under --json. No
#: plan row is created; nothing is installed.
ROUTING_REQUEST_REFUSAL_CODES = ("agent_absent", "catalog_not_installed")

ROUTING_RESULT_STATUSES = ("resolved", "no_eligible_candidates", "unresolved")
ROUTING_CANDIDATE_VERDICTS = ("eligible", "unresolved", "excluded")

ROUTING_REASON_DISPLAY_LIMIT = 8    # named constant — NOT doctor.UH2_DISPLAY_LIMIT (10)
MAX_ROUTING_EVALUATED_AGENTS = 256
```

### Exact condition per code

| # | code | class | condition (exact) |
|---|---|---|---|
| 1 | `identity_tampered` | hard_ineligible | `agent_integrity(agent) != "ok"` |
| 2 | `passport_history_tampered` | hard_ineligible | `history_problems(conn, agent)` non-empty |
| 3 | `draft_only` | hard_ineligible | `lifecycle == 'draft'` |
| 4 | `suspended` | hard_ineligible | `lifecycle == 'suspended'` |
| 5 | `archived` | hard_ineligible | `lifecycle == 'archived'` |
| 6 | `revoked` | hard_ineligible | `lifecycle == 'revoked'` |
| 7 | `legacy_without_passport` | hard_ineligible | `origin == 'legacy'` ∧ pointer NULL |
| 8 | `no_current_published_passport` | hard_ineligible | active, non-legacy, pointer NULL |
| 9 | `project_mismatch` | hard_ineligible | agent project-scoped to a different project than the request's |
| 10 | `scope_mismatch` | hard_ineligible | `required_scope` present and agent's scope level violates it |
| 11 | `agent_class_mismatch` | hard_ineligible | `required_agent_class` present, `agent_class` differs |
| 12 | `data_classification_mismatch` | hard_ineligible | requested level ∉ passport `data_classifications` set — including an absent declaration |
| 13 | `autonomy_mismatch` | hard_ineligible | passport `autonomy` ∉ requested `required_autonomy` set |
| 14 | `missing_task_family` | hard_ineligible | requested item(s) not covered by the (possibly absent) declaration |
| 15 | `missing_capability` | hard_ineligible | same shape |
| 16 | `missing_evidence_kind` | hard_ineligible | same shape |
| 17 | `missing_skill_declaration` | hard_ineligible | same shape |
| 18 | `missing_tool_declaration` | hard_ineligible | same shape |
| 19 | `missing_model_capability` | hard_ineligible | same shape |
| 20 | `malformed_declaration` | unresolved | the stored current passport document fails `parse_canonical`/`validate_document` re-read, or a consulted declaration has an impossible shape |
| 21 | `unknown_declaration_value` | unresolved | a consulted declaration carries a value outside this build's closed vocabulary (plausibly a newer passport — not condemned, not trusted) |
| 22 | `preferred_agent_mismatch` | preference_only | eligible but not the preferred agent (recorded, ordering-only) |
| 23 | `passport_expired` | warning_only | envelope `expires_at` present and < plan `created_at` |
| 24 | `catalog_upgrade_available` | warning_only | candidate is catalog-managed and `catalog.installed_state` would say `upgradable` |

Request-level refusals (never stored):

| code | condition |
|---|---|
| `agent_absent` | `preferred_agent` names no `agents` row — refusal, zero rows created |
| `catalog_not_installed` | `preferred_agent` names a shipped catalog entry with no installed row — refusal names `agent catalog install`; never installs |

### Rules

- **Multiple reasons apply**; all applicable codes are recorded in canonical
  order. Storage is inherently bounded by the closed vocabulary (**≤24**);
  text rendering truncates at **`ROUTING_REASON_DISPLAY_LIMIT` (8)** with
  ` (+N more)`; `--json` carries all stored codes.
- **Verdict precedence**: any hard_ineligible ⇒ `excluded`; else any
  unresolved ⇒ `unresolved`; else `eligible`. `preference_only` never changes
  a verdict; `warning_only` attaches to any verdict.
- **Malformed optional declarations invalidate the complete candidate** to
  `unresolved` (not just the dimension): a half-evaluated candidate cannot be
  honestly ranked, and fabricating the missing dimension violates invariant
  11. This is the fail-closed-but-honest middle: never eligible, never
  definitively excluded.
- **No scoring penalties exist anywhere**: a missing hard requirement is a
  verdict, never a subtraction.
- **Storage split**: `reasons_json` carries hard_ineligible, unresolved and
  preference_only codes (canonical order); `warnings_json` carries
  warning_only codes only (canonical order). Both columns are independently
  `NOT NULL` — an eligible candidate with no preference and no warnings
  stores `'[]'` in both.
- **JSON representation**: per candidate `{"agent": name, "verdict":
  "eligible|unresolved|excluded", "reasons": [codes…], "warnings": [codes…],
  "rank": N|null, "pinned": {"passport_version": N, "passport_sha256": …,
  "identity_sha256": …}|null, "ordering": [t1,t2,t3,t4,t5,t6]|null}`. `rank`,
  `pinned` and `ordering` are simultaneously non-null **iff**
  `verdict='eligible'` — the JSON projection of the DDL's five pin
  biconditionals (§11).
- **Text rendering**: one line per candidate,
  `  <rank>. <name>  v<version>  <sha-prefix>` for eligible;
  `  - <name>  excluded: code, code (+N more)` for diagnostics.
- **Exit-code effect**: none — `agent route plan` exits 0 for any stored
  `result_status` (`resolved`, `no_eligible_candidates`, `unresolved`); the
  *outcome* is data. Only validation refusals (including
  `ROUTING_REQUEST_REFUSAL_CODES`) exit 1.

## 8. DETERMINISTIC ORDERING ALGORITHM

Algorithm version string: **`aos-routing-order/v1`** (stored per plan;
mismatch between a stored plan and a future build is display information,
never an error). Lexicographic tuple over eligible candidates only —
**no weights, no scores**:

| pos | component | source | encoding | direction | missing-value | max | explanation code | changes eligibility? |
|---|---|---|---|---|---|---|---|---|
| T1 | preferred match | request `preferred_agent` vs `agents.name` | 0/1 | desc | no preference ⇒ 0 for all | 1 | `preferred` | never |
| T2 | scope specificity | `agents.scope`+`project_id` vs request project | 1 = project-scoped to the request's project, else 0 | desc | no request project or `scope_preference:'none'` ⇒ 0 for all | 1 | `scope_specific` | never |
| T3 | task-family surplus | passport `task_families` | `len(declared) − len(matched required)`; request dimension absent ⇒ 0 | asc (minimal surplus wins) | declaration absent ∧ dimension unrequested ⇒ 0 | 32 | `surplus_task_families` | never |
| T4 | capability surplus | passport `capabilities` | same rule | asc | same | 32 | `surplus_capabilities` | never |
| T5 | skill surplus | passport `skill_requirements` | same rule | asc | same | 32 | `surplus_skills` | never |
| T6 | tool surplus | passport `tool_requirements` | same rule | asc | same | 32 | `surplus_tools` | never |
| T7 | canonical name | `agents.name` | UTF-8 byte sequence | asc | impossible (NOT NULL UNIQUE) | 64 chars | `name` | never |

`surplus_policy: "ignore"` forces T3–T6 to 0. `autonomy` and
`data_classification` were never ordering components and remain so — the
corrections in §6/§7 do not touch this section at all. Evaluated-and-rejected
dimensions:

- **Exact task-family / capability / evidence alignment as separate
  components** — rejected as redundant: gates guarantee every eligible
  candidate matches *all* required items, so "alignment count" is constant
  across eligible candidates; the only honest differentiator left is surplus.
- **Maturity** — rejected. Maturity exists only in the catalog manifest
  index (U-A2 §7, "manifest index metadata, not a passport field"); user
  agents have none, so any maturity component would rank catalog identities
  as a class against custom ones — invariant 5 forbids this, even as an
  opt-in preference.
- **Evidence-expectation distance (`min_evidence_count`)** — rejected:
  gate-only dimension; a distance metric would be an opaque score in
  disguise.

**Ordering proof**: T1–T6 are bounded integers with fixed directions; T7 is a
byte comparison over a column with a `UNIQUE NOT NULL` constraint, therefore
no two candidates can compare equal at T7 — the order is total and unique.
**Final byte-level tie-break** = T7 itself. **Canonical serialization**:
per-candidate `ordering_json` stores the exact array
`[t1, t2, t3, t4, t5, t6]` (T7 implicit in the row's agent reference) in
canonical JSON; ranks are assigned 1..N over the sorted sequence.

**Two-workspace determinism**: no component reads row ids, timestamps,
insertion order, or any mutable statistic — a test builds the same logical
registry in two workspaces in different insertion orders and asserts
identical `(rank, name, version, document-digest, reasons)` sequences and an
identical `request_sha256`. **This assertion excludes `content_sha256`**
(§12): row-hash payloads bind the row id, which is legitimately
workspace-specific — asserting `content_sha256` equality across two
independently-inserted workspaces would be asserting something false about
an honest hash.

Prohibited inputs (time, recency, usage, popularity, protection, origin,
provider state, pricing, randomness, LLM judgment): none has a code path —
the evaluation function's only inputs are the canonical request document and
the rows named above.

## 9. ROUTING PLAN CONTRACT

One post-commit-immutable plan row + N post-commit-immutable candidate rows
(exact DDL: §11; exact hash construction: §12).

- **Plan-embedded request**: the canonical request document is stored
  verbatim in `routing_plans.request_document` with its digest in
  `request_sha256`. There is **no standalone request table**: a request's
  lifetime is exactly one plan's, a 1:1 table pair would add a join and a
  second hash for zero queryability, and the plan hash binds the document
  anyway. A request that fails validation produces no row at all.
- **Preserved facts**: plan id; optional task id; scope + project snapshot;
  `request_sha256`; `request_schema`; `algorithm_version`; ordered eligible
  candidates (rank, agent, pinned passport version, pinned passport document
  digest, pinned identity digest, ordering tuple); excluded and unresolved
  candidates with bounded reason codes; actor; `created_at`;
  `supersedes_id`; `result_status`; counts; `content_sha256` (binds all of
  the above including the ordered chain of **recomputed** candidate row
  digests — the claim-binds-its-link-set pattern from U-M3, §12).
- **Passport bodies are never duplicated**: candidates pin
  `(agent_id, passport_version)` — **enforced** against the immutable
  `agent_passports` rows by a composite FOREIGN KEY (BLOCKER-1, §11) — plus
  the recomputed document digest; the document text stays where it lives.

Explicit answers:

- **Is plan creation an authoritative write?** Yes — it inserts ledger rows
  and an event; by the mechanical rule (power.py:137 comment) it is
  `AUTHORITATIVE_WRITE, ledger=True`, recovery-blocked, deep-verified.
- **Is candidate selection part of the plan?** No, and there is no separate
  selection record either: `agent route select` is **rejected**. A selection
  that grants nothing and executes nothing is materially a *delegation
  declaration*, and U-A3 already has that record — the handoff, which
  references the plan and names the recipient.
- **Can a plan be modified?** No **committed** plan or candidate row is ever
  updated or deleted; no command reaches them after commit. The sole UPDATE
  is the hash-finalization step inside the *creating* transaction, between
  INSERT and COMMIT — invisible to every other connection, and a survivor of
  a crash mid-transaction is caught as `malformed` by doctor 38 rather than
  passing as a hash (MAJOR-1; full construction: §12). This is
  **post-commit** immutability, precisely.
- **Staleness** — computed at read time, never stored (§10).
- **Can a stale plan be inspected?** Yes — `route show`/`verify`/`list` all
  work and label it.
- **Can a stale plan create a handoff?** No (§10 refusal text).
- **Plan with no eligible candidates storable?** Yes — `result_status =
  'no_eligible_candidates'` is an honest, useful record (MAJOR-2 rename —
  the plan in this state *has* candidate rows, possibly many, all
  `excluded`; the old name `no_candidates` was a lie about that).
- **Unresolved plan storable?** Yes — `result_status = 'unresolved'`
  (invariant 11: explicitly unresolved beats fabricated certainty).
- **Can a plan be `resolved` while also holding `unresolved` candidates?**
  **Yes, and this is the common, correct case** — a plan has a ranked answer
  (`eligible_count > 0`) while separately recording diagnostic candidates
  that could not be honestly judged. `result_status` is a derived projection
  of `(eligible_count, unresolved_count)` alone; `excluded_count` never
  participates in it. Exact semantics and the three-way CHECK: §11.

## 10. ROUTING PLAN STALENESS AND SUPERSESSION

**Staleness (derived predicate, read-time, mutates nothing)** — a plan is
stale iff any *eligible* candidate row satisfies any of:

1. the agent's `current_passport_version` ≠ pinned version;
2. the agent's lifecycle ≠ `active`;
3. `agent_integrity(agent) != "ok"` or `history_problems` non-empty;
4. the pinned passport row's recomputed `document_digest` ≠ pinned
   `passport_sha256` (tamper — also a doctor FAIL);
5. the agent's identity hash ≠ pinned `identity_sha256` *because a governed
   field moved* (updated_at/lifecycle/pointer changes all rehash the
   identity — pin divergence is the cheap "something moved" test;
   conditions 1–3 name what moved).

A plan referencing a task whose row was later purged cannot occur (FK,
NO ACTION). **Plans do not expire by time**: `utc_now_iso` is the only clock
and time-based invalidation would make `route show` output nondeterministic
per invocation; staleness is defined by ledger facts only, never by a clock
reading compared against a stored timestamp.

**Supersession**: `route plan --supersedes RP-000N` stamps `supersedes_id`
on the **new** plan at creation (immutable thereafter, and structurally
acyclic — §11's `CHECK (supersedes_id IS NULL OR supersedes_id < id)`). The
old plan is not touched — "superseded" is **derived** by the existence of a
successor (`UNIQUE(supersedes_id)` makes chains linear; a second successor
refuses). Creation validates in-transaction that the target exists and has
no successor yet.

**The plan/handoff supersession asymmetry, stated explicitly** (previously
only implied): **plan supersession is derived; handoff supersession is both
derived and stored. This is deliberate, not an inconsistency.** A routing
plan has no lifecycle — "superseded" is a fact *about* it (a successor
exists), and the plan row stays byte-identical forever, so deriving the fact
is both cheaper and strictly stronger (nothing to keep in sync). A handoff
*has* a lifecycle, and `superseded` is a **terminal state that must block
`accept`** — so it must live in the same `state` column CAS reads, and it
must be reached through the same append-only transition history as every
other terminal state (§14). Doctor 39 is what keeps the two facts about a
handoff — the stored `state` and the derived "a successor names me" fact —
honest: `state='superseded'` ⇔ exactly one row names it in `supersedes_id`,
else `supersession_incoherent`.

**Exact refusal** (handoff create against a stale plan):

```
Routing plan RP-0007 is stale: agent 'NAME' has changed since the plan was
created (pinned v2, now v3 / lifecycle suspended / integrity mismatch).
The plan remains inspectable history; nothing was changed. Create a fresh
plan: python aos.py agent route plan ...
```

(one line per house style, first stale candidate named, closed verdict
vocabulary, no hash values).

## 11. EXACT DDL — ALL FOUR TABLES

Four DDL constants in `db.py`, each `{table}`-parameterized (the migration-
rename rule), composed into `SCHEMA_SQL` after the agent tables, and created
**directly under their real names** in the migration step — no temp-table +
`ALTER TABLE RENAME`, so a fresh v5 schema and a migrated one are
**byte-identical** for these four tables, not merely structurally identical
(§22). No indexes (§17.1). All hash columns have **no default** — a row
without its integrity hash must be uninsertable. Timestamps: `utils.utc_now_iso`
TEXT.

```sql
CREATE TABLE routing_plans(
  id INTEGER PRIMARY KEY,
  task_id INTEGER,
  project_id INTEGER,
  scope TEXT NOT NULL CHECK (scope IN ('global','project')),
  actor TEXT NOT NULL,
  request_schema TEXT NOT NULL,
  algorithm_version TEXT NOT NULL,
  request_document TEXT NOT NULL,
  request_sha256 TEXT NOT NULL,
  result_status TEXT NOT NULL
    CHECK (result_status IN
      ('resolved','no_eligible_candidates','unresolved')),
  eligible_count INTEGER NOT NULL CHECK (eligible_count >= 0),
  unresolved_count INTEGER NOT NULL CHECK (unresolved_count >= 0),
  excluded_count INTEGER NOT NULL CHECK (excluded_count >= 0),
  supersedes_id INTEGER UNIQUE,
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  CHECK ((scope='global' AND project_id IS NULL)
      OR (scope='project' AND project_id IS NOT NULL)),
  CHECK ((result_status='resolved') = (eligible_count > 0)),
  CHECK ((result_status='unresolved')
       = (eligible_count = 0 AND unresolved_count > 0)),
  CHECK ((result_status='no_eligible_candidates')
       = (eligible_count = 0 AND unresolved_count = 0)),
  CHECK (supersedes_id IS NULL OR supersedes_id < id),
  FOREIGN KEY(task_id) REFERENCES tasks(id),
  FOREIGN KEY(project_id) REFERENCES projects(id),
  FOREIGN KEY(supersedes_id) REFERENCES routing_plans(id)
);

CREATE TABLE routing_plan_candidates(
  id INTEGER PRIMARY KEY,
  plan_id INTEGER NOT NULL,
  agent_id INTEGER NOT NULL,
  verdict TEXT NOT NULL CHECK (verdict IN ('eligible','unresolved','excluded')),
  rank INTEGER CHECK (rank IS NULL OR rank >= 1),
  passport_version INTEGER
    CHECK (passport_version IS NULL OR passport_version >= 1),
  passport_sha256 TEXT,
  identity_sha256 TEXT,
  reasons_json TEXT NOT NULL,
  warnings_json TEXT NOT NULL,
  ordering_json TEXT,
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  UNIQUE(plan_id, agent_id),
  UNIQUE(plan_id, rank),
  CHECK ((verdict='eligible') = (rank IS NOT NULL)),
  CHECK ((verdict='eligible') = (ordering_json IS NOT NULL)),
  CHECK ((verdict='eligible') = (passport_version IS NOT NULL)),
  CHECK ((verdict='eligible') = (passport_sha256 IS NOT NULL)),
  CHECK ((verdict='eligible') = (identity_sha256 IS NOT NULL)),
  FOREIGN KEY(plan_id) REFERENCES routing_plans(id),
  FOREIGN KEY(agent_id) REFERENCES agents(id),
  FOREIGN KEY(agent_id, passport_version)
    REFERENCES agent_passports(agent_id, version)
);

CREATE TABLE agent_handoffs(
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL,
  plan_id INTEGER,
  from_agent_id INTEGER NOT NULL,
  to_agent_id INTEGER NOT NULL,
  actor TEXT NOT NULL,
  objective_md TEXT NOT NULL,
  expected_evidence_json TEXT NOT NULL,
  min_evidence_count INTEGER NOT NULL DEFAULT 0
    CHECK (min_evidence_count BETWEEN 0 AND 32),
  constraints_md TEXT,
  data_classification TEXT NOT NULL DEFAULT 'internal'
    CHECK (data_classification IN ('public','internal','confidential','restricted')),
  decision_id INTEGER,
  from_passport_version INTEGER NOT NULL CHECK (from_passport_version >= 1),
  from_passport_sha256 TEXT NOT NULL,
  to_passport_version INTEGER NOT NULL CHECK (to_passport_version >= 1),
  to_passport_sha256 TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'proposed'
    CHECK (state IN ('proposed','accepted','refused',
                     'clarification_required','cancelled','superseded')),
  supersedes_id INTEGER UNIQUE,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  CHECK (from_agent_id <> to_agent_id),
  CHECK (supersedes_id IS NULL OR supersedes_id < id),
  FOREIGN KEY(task_id) REFERENCES tasks(id),
  FOREIGN KEY(plan_id) REFERENCES routing_plans(id),
  FOREIGN KEY(from_agent_id) REFERENCES agents(id),
  FOREIGN KEY(to_agent_id) REFERENCES agents(id),
  FOREIGN KEY(decision_id) REFERENCES decisions(id),
  FOREIGN KEY(supersedes_id) REFERENCES agent_handoffs(id),
  FOREIGN KEY(from_agent_id, from_passport_version)
    REFERENCES agent_passports(agent_id, version),
  FOREIGN KEY(to_agent_id, to_passport_version)
    REFERENCES agent_passports(agent_id, version)
);

CREATE TABLE agent_handoff_transitions(
  id INTEGER PRIMARY KEY,
  handoff_id INTEGER NOT NULL,
  seq INTEGER NOT NULL CHECK (seq >= 1),
  from_state TEXT NOT NULL
    CHECK (from_state IN ('proposed','accepted','clarification_required')),
  to_state TEXT NOT NULL
    CHECK (to_state IN ('accepted','refused','clarification_required',
                        'cancelled','superseded')),
  actor TEXT NOT NULL,
  reason_code TEXT
    CHECK (reason_code IS NULL OR reason_code IN
      ('out_of_scope','missing_capability','conflicting_work',
       'data_classification','objective_unclear','constraints_unclear',
       'evidence_unclear','operator_judgment')),
  note_md TEXT,
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  UNIQUE(handoff_id, seq),
  CHECK (from_state <> to_state),
  CHECK (from_state <> 'accepted'
      OR to_state IN ('cancelled','superseded')),
  CHECK (to_state NOT IN ('refused','clarification_required')
      OR reason_code IS NOT NULL),
  FOREIGN KEY(handoff_id) REFERENCES agent_handoffs(id)
);
```

**Correction inventory against the design's original DDL** (all discharged
here; §29 cross-references each to its blocker/major):

1. `routing_plan_candidates` gains
   `FOREIGN KEY(agent_id, passport_version) REFERENCES agent_passports(agent_id, version)`
   — **BLOCKER-1**. Without it, an eligible candidate could pin a
   `(agent_id, passport_version)` pair that names no real passport, or
   another agent's passport, and nothing would refuse it; doctor 38 would
   only report it after the fact. The NULL rule (SQLite disables a composite
   FK when any child column is NULL) already makes excluded/unresolved rows
   — where `passport_version IS NULL` — legal, exactly as it does for a
   draft or legacy agent's NULL `current_passport_version` pointer in
   `AGENTS_DDL`. **Side effect, recorded so it is not later "discovered" as
   a bug**: `agent discard` becomes additionally FK-blocked whenever a
   candidate row pins one of the discarded agent's passport versions. This
   is unreachable in practice — pins exist only on `eligible` rows,
   eligibility requires `lifecycle='active'`, and discard requires
   `lifecycle='draft'` — so it changes nothing about the discard guard
   (§21).
2. `routing_plans.result_status` gains two CHECKs beyond the original
   `(result_status='resolved') = (eligible_count > 0)` — **MAJOR-2**. The
   original left the `unresolved` ↔ `no_eligible_candidates` boundary
   entirely unconstrained: `(status='no_eligible_candidates', eligible=0,
   unresolved>0)` and `(status='unresolved', eligible=0, unresolved=0)` both
   satisfied the one original CHECK and both are lies about the stored
   candidate rows. The two added CHECKs close both holes; any two of the
   three imply the third given the enum CHECK, and all three are written
   independently because `MEMORY_EDGES_DDL` sets exactly this precedent
   ("each pinning one rule the domain layer also enforces").
3. `routing_plans` and `agent_handoffs` each gain
   `CHECK (supersedes_id IS NULL OR supersedes_id < id)` — cycle prevention.
   `<` rather than `<>`: `<>` blocks only self-supersession, while `<` makes
   **every** cycle unrepresentable, because a cycle needs at least one
   forward edge. Sound because `INTEGER PRIMARY KEY` is the rowid, SQLite
   assigns `max(rowid)+1`, and neither table has a DELETE path, so ids
   strictly increase and an honest successor always has the larger id.
   Precedented by `MEMORY_EDGES_DDL`'s `CHECK (relation NOT IN
   ('contradicts','related') OR from_memory_id < to_memory_id)`.
4. `routing_plan_candidates` gains three more pin biconditionals
   (`passport_version`, `passport_sha256`, `identity_sha256`, each
   `= (verdict='eligible')`) beyond the original's one-directional
   `CHECK (verdict <> 'eligible' OR (… IS NOT NULL))`. The one-directional
   form permitted a non-eligible row to carry pins, contradicting §9's "every
   *eligible* candidate row … pins" and §7's JSON (`"pinned": …|null`
   alongside `"rank": N|null`). Biconditionals make pins exactly
   co-extensive with `rank`/`ordering_json`, which already used them.
5. `decision_id` on `agent_handoffs`: **column, type and FK unchanged** —
   only its *meaning*, stated in prose (§13, §15), is corrected. No DDL
   change discharges BLOCKER-3; the wording does.
6. `agent_handoff_transitions` gains
   `CHECK (from_state <> 'accepted' OR to_state IN ('cancelled','superseded'))`
   — **MAJOR-3**. Without it, `accepted → refused` and
   `accepted → clarification_required` are storable even though §14's verb
   table forbids both; they would replay as `chain_illegal` in doctor 39,
   reported after the fact, when one line makes them unstorable. Proof of
   completeness: `from_state='proposed'` → all five `to_state` values are
   legal and the enum admits exactly those five; `from_state=
   'clarification_required'` → accepted/refused/cancelled/superseded are
   legal, and the sixth value is already blocked by `from_state <>
   to_state`; `from_state='accepted'` → cancelled/superseded only, which
   this CHECK pins. The complete legal edge set (11 pairs) is now
   structurally exact.

All FKs are plain `REFERENCES` (NO ACTION): with `foreign_keys=ON`, deleting
a referenced row is refused — the append-only-ledger rule. The two composite
FKs on `agent_handoffs`, and the one on `routing_plan_candidates`, pin
passport versions to real immutable `agent_passports` rows (the
`AGENTS_DDL` current-passport-pointer trick, applied a third time).
Record-hash payload schemas (house style — each names itself):
`aos.routing-plan/v1`, `aos.routing-candidate/v1`, `aos.agent-handoff/v1`,
`aos.agent-handoff-transition/v1`; text bound by sha256 leaf, ints direct;
plan and handoff hashes additionally bind the ordered child-row digest chain
(§12).

## 12. EXACT HASH CONSTRUCTION

### 12.1 The circularity, and why it is not a contradiction

- `routing_plan_candidates.plan_id` is `NOT NULL` with an FK → the plan row
  must exist before any candidate row.
- `routing_plans.content_sha256` is `NOT NULL` with no default, and it binds
  the ordered candidate digest chain → the chain must exist before the
  plan's hash is known.
- Every record-hash payload in this tree binds the row id
  (`agent_identity_payload` binds `"id"`, `memory_source_link_payload` binds
  `"id"`), and a row id is only known after INSERT.

These three cannot all hold at INSERT time. The resolution is the
`_PENDING_HASH` pattern already in the tree (`ops.py:1227–1233`):

> `_PENDING_HASH = ""` — "The hash a brand-new claim carries between its
> INSERT and its hash UPDATE, microseconds later inside the same
> transaction. The claim hash binds the row id, and the id is only known
> after the INSERT — so the two-step is unavoidable. It is invisible: no
> other connection can observe an open transaction, and a placeholder that
> somehow survived would be caught by doctor's malformed-hash check rather
> than passing as a real hash."

U-A3 adopts this verbatim for both new record families. **Immutability here
is post-commit**: no committed row is ever modified, and no command reaches
these tables after commit. The in-transaction hash-finalization UPDATE is
invisible (`BEGIN IMMEDIATE` holds the write lock; no other connection can
observe an open transaction; `busy_timeout=5000` makes a concurrent writer
wait rather than read a partial state) and does not violate that claim.

### 12.2 Routing plan construction

**Payloads** — each names itself (house style):

```
candidate_payload(c) = {
  "record_schema": "aos.routing-candidate/v1",
  "id": int(c.id), "plan_id": int(c.plan_id), "agent_id": int(c.agent_id),
  "rank": int(c.rank) | null, "passport_version": int(c.passport_version) | null,
  "verdict_sha256": text(c.verdict),
  "passport_sha256_sha256": text(c.passport_sha256) | null,
  "identity_sha256_sha256": text(c.identity_sha256) | null,
  "reasons_json_sha256": text(c.reasons_json),
  "warnings_json_sha256": text(c.warnings_json),
  "ordering_json_sha256": text(c.ordering_json) | null,
  "created_at_sha256": text(c.created_at),
}                                    # excludes content_sha256, as everywhere

plan_payload(p, chain) = {
  "record_schema": "aos.routing-plan/v1",
  "id": int(p.id), "task_id": int|null, "project_id": int|null,
  "eligible_count": int, "unresolved_count": int, "excluded_count": int,
  "supersedes_id": int|null,
  "scope_sha256": text, "actor_sha256": text, "request_schema_sha256": text,
  "algorithm_version_sha256": text, "request_document_sha256": text,
  "request_sha256_sha256": text, "result_status_sha256": text,
  "created_at_sha256": text,
  "candidate_chain": chain,          # ordered list of RECOMPUTED candidate digests
}
```

**Chain order** — defined once, used everywhere it applies: **the
`candidate_chain` is each candidate's recomputed digest, ordered by
`routing_plan_candidates.id` ascending** — which equals canonical evaluation
order, because insertion follows it. Eligible rows have `rank`;
excluded/unresolved rows have `rank IS NULL`, so `rank` cannot order the
chain — `id` is the only total order available on all three verdict classes.

**Transaction sequence** (`routing.create_plan`, one owner, one boundary):

```
 1. validate all user input                       # outside the txn (D-v0.4.18)
 2. with db.transaction(conn):                     # the ONE boundary
 3.   BEGIN IMMEDIATE                              # write lock before re-reads
 4.   re-read task/project/preferred agent; re-read supersedes target
        (exists ∧ no successor); refuse if agents count > 256
 5.   evaluate eligibility + ordering              # entirely in-txn, authoritative
 6.   INSERT routing_plans(..., content_sha256 = _PENDING_HASH)
        → plan_id = lastrowid
 7.   for each candidate, in canonical emission order:
        INSERT routing_plan_candidates(plan_id, ..., content_sha256=_PENDING_HASH)
          → cid = lastrowid
        UPDATE routing_plan_candidates SET content_sha256 = digest(candidate_payload(re-read row))
          WHERE id = cid                           # the _rehash_claim shape
 8.   chain = [recomputed digest of each candidate ORDER BY id]
 9.   UPDATE routing_plans SET content_sha256 = digest(plan_payload(re-read row, chain))
        WHERE id = plan_id
10.   events.emit(entity="routing_plan", action="create", …)
11. # commit on context exit
```

**Non-circularity**: no digest input ever contains a `content_sha256`
column. Candidate digests are computed from candidate columns (which include
`plan_id` — a *value*, not a hash). The plan digest is computed from plan
columns plus recomputed candidate digests. The dependency graph is
plan-**id** → candidate rows → candidate digests → plan **hash**. Acyclic.

**Rollback**: `db.transaction` is `with conn:` — any exception rolls back
the whole boundary. Zero rows, zero events, no `_PENDING_HASH` survivor. A
process kill mid-transaction is rolled back by SQLite's journal on next
open. A `''` hash that somehow survived is `malformed` under
`models.is_claim_hash`-shaped validation (`^[0-9a-f]{64}\Z`) — reported by
doctor 38 and by `route verify` (exit 1), never mistaken for a hash.

**Verification** (`route verify`, doctor 38): read the plan row and its
candidates `ORDER BY id`; recompute each candidate digest from its columns
and compare to its stored `content_sha256`; build the chain from the
**recomputed** digests, never the stored ones — a tampered candidate hash
must not be able to launder itself into a valid chain (the
`document_digest` rule, applied again); recompute the plan digest and
compare. No circularity: the verifier reads only non-hash columns as digest
inputs.

### 12.3 Handoff and transition construction

**Exact semantics — the honest name: append-only transition history plus a
mutable, hash-coupled current-state projection.** Not a fully immutable
record.

- **Immutable**: `agent_handoff_transitions` rows (append-only, never
  updated, never deleted); every `agent_handoffs` column **except** the
  three below.
- **Mutable projection**: `state`, `updated_at`, `content_sha256` — always
  together, always in the same transaction as the transition row that
  justifies them, always accompanied by exactly one event. (Corrected from
  the design's "changes exactly: one `state` column, one transition row, one
  hash, one event" — that omitted `updated_at`. **Three columns** change,
  not two.)
- The projection is **derivable** from the immutable history (replay
  `proposed` through the chain). It is stored because it is what CAS reads,
  what `list` filters on, and what the storage layer constrains. Doctor 39
  is what proves projection and history agree.

**Initial state — zero transitions.** `create_handoff` writes
`state='proposed'` and **no** transition row. The chain is the **empty
tuple**, and the handoff digest binds it as such. Doctor 39's replay rule:
"`state` must equal `proposed` when the chain is empty, and the last
transition's `to_state` otherwise."

**Append sequence** (`agent_handoffs.transition`, verb=`accept`,
representative of all five verbs):

```
 1. validate CLI input                             # outside the txn
 2. with db.transaction(conn):
 3.   BEGIN IMMEDIATE
 4.   re-read the handoff row
 5.   VERIFY: row hash + transition chain intact    # no-laundering gate —
        # refuse to mutate a record whose stored hash does not verify, or
        # the write LAUNDERS the tamper
 6.   CAS: state ∈ AGENT_HANDOFF_TRANSITIONS['accept'].sources
        else refusal naming the current state (exit 1, nothing written)
 7.   accept only: re-read both participants — exist, active, integrity ok,
        history ok, and BOTH PINS CURRENT (pinned version ==
        current_passport_version, pinned digest == document_digest(stored
        passport)); else the §10-style refusal
 8.   seq = COALESCE(MAX(seq),0) + 1  WHERE handoff_id = ?
 9.   INSERT agent_handoff_transitions(handoff_id, seq, from_state=<re-read state>,
        to_state='accepted', actor=ACTOR_HUMAN, reason_code, note_md, created_at,
        content_sha256=_PENDING_HASH) → tid
10.   UPDATE agent_handoff_transitions SET content_sha256 = digest(transition_payload(re-read row))
        WHERE id = tid
11.   chain = [recomputed transition digests ORDER BY seq]     # seq, not id
12.   UPDATE agent_handoffs
        SET state='accepted', updated_at=now,
            content_sha256 = digest(handoff_payload(row-with-new-state, chain))
        WHERE id = ?                                # ONE update: all three columns together
13.   events.emit(entity="agent_handoff", action="accept", …)
14. # commit on context exit
```

Step 12 is a **single** UPDATE — the digest is computed in Python over the
*intended* new state, so no intermediate "state moved but hash didn't" row
exists even inside the transaction.

**Chain order for handoffs is `seq` ascending — not `id`.** `seq` is the
domain's own ordering, `UNIQUE(handoff_id, seq)` makes it total, and doctor
39 already checks contiguity over it.

**Doctor 39 replay** (exact): for each handoff: (a) recompute the row hash
over columns + recomputed chain, compare → `mismatch`/`unhashable`/
`malformed`; (b) transitions `ORDER BY seq` — seq contiguous from 1 →
`chain_gap`; (c) first transition's `from_state` == `'proposed'`, and each
subsequent `from_state` == the previous `to_state` → `chain_illegal`; (d)
each `(from_state, to_state)` ∈ the legal edge set → `chain_illegal`
(reachable only via out-of-band writes now that §11's CHECK is in place);
(e) replayed terminal state == stored `state`, or `state == 'proposed'` when
the chain is empty → `state_divergent`; (f) `reason_code` present where
required → `reason_missing`; (g) pins resolve and digests match →
`pin_mismatch`; (h) `state='superseded'` ⇔ exactly one row names it in
`supersedes_id` → `supersession_incoherent`.

**Rollback after an inserted transition but before the parent update
cannot commit.** Steps 9–13 share one `db.transaction(conn)` boundary; any
exception rolls back the transition row, the parent update and the event
together. A committed handoff whose transition exists but whose
`state`/hash did not move **cannot exist** — and if one ever did (an
out-of-band write), doctor 39 reports it as `state_divergent`, and every
write verb refuses it at step 5 before touching anything.

## 13. AGENT HANDOFF CONTRACT

One `agent_handoffs` row per delegation declaration (exact DDL: §11).
Field-by-field:

| field | type | req | semantics |
|---|---|---|---|
| `id` | int PK | — | rendered `AH-0001` |
| `task_id` | FK tasks, NOT NULL | yes | **a handoff requires a task**: evidence rows are task-scoped, so evidence requirements are meaningless without one; create refuses when `tasks.status = 'done'` |
| `plan_id` | FK routing_plans, NULL | no | optional advisory link; when present: plan must be intact, not stale, not superseded; recipient must be one of its *eligible* candidates; plan's `task_id` must be NULL or equal `task_id`. When the human wants a recipient outside the plan, they omit `--plan` — the reference stays honest, the plan stays advisory |
| `from_agent_id` / `to_agent_id` | FK agents, NOT NULL, CHECK ≠ | yes | logical sender / recipient identities; both must be installed, `active`, integrity-ok, with a current published passport at creation |
| `actor` | TEXT NOT NULL | yes | `ops.ACTOR_HUMAN` — the authoritative human creator |
| `objective_md` | TEXT NOT NULL | yes | bounded prose, 1..4096 chars (the passport `mission` bound), warn-on-write scanned, label `objective` |
| `expected_evidence_json` | TEXT NOT NULL | yes (may be `[]`) | canonical JSON array ⊆ `EVIDENCE_KINDS`, sorted, dup-refused — the expected output categories |
| `min_evidence_count` | INT 0..32 | yes (default 0) | mirrors passport `evidence_expectations` bounds |
| `constraints_md` | TEXT NULL | no | bounded prose ≤4096, scanned, label `constraint` |
| `data_classification` | enum ladder, default `internal` | yes | **the declared classification of the data involved in this delegation — not a ceiling, not a clearance, not an authority grant** (MAJOR-4). If the recipient's passport does not declare this level, create prints a one-line advisory **warning** — not stored, not blocking; routing stays advisory |
| `decision_id` | FK decisions, NULL | no | **an optional pointer to the architecture-decision record that explains *why* this delegation was declared. Descriptive only.** `decisions` is an ADR table (`title`, `decision_md`, `alternatives_md`) — it has no approver, no subject, no grant, and its `status` column carries no CHECK and is hardcoded to `'accepted'` by its only writer. **No code path reads this column to permit anything, and none ever may without a unit that first builds a real approval primitive.** (BLOCKER-3; full rationale §15) |
| `from_passport_version` + `from_passport_sha256`; `to_passport_version` + `to_passport_sha256` | INT + 64-hex, NOT NULL | yes | pins at creation; composite FKs `(agent_id, version) → agent_passports` make a dangling pin structurally impossible |
| `state` | enum CHECK, default `proposed` | yes | current state — the mutable projection column (§12.3, §14) |
| `supersedes_id` | FK agent_handoffs, NULL, UNIQUE, `< id` | no | stamped on the successor at creation |
| `created_at` / `updated_at` | TEXT NOT NULL | yes | `utc_now_iso`; `updated_at` moves on every transition (§12.3) |
| `content_sha256` | TEXT NOT NULL | yes | record hash `aos.agent-handoff/v1`, binds every column above (prose by sha256 leaf) plus the ordered transition-row digest chain (`seq` order) |

Completion evidence reference: **excluded** — `completed` is not a U-A3
state (§14), so no completion field exists.

**Actor vs participants**: the row separates the authoritative human
(`actor`, always the operating human — the system has no authenticated agent
actors; every existing write uses `ACTOR_HUMAN`) from the two logical
participants (FK identities). No text anywhere describes an agent
"accepting" by itself: `agent handoff accept` records *the human's*
acceptance decision for the recipient identity.

## 14. HANDOFF LIFECYCLE AND TRANSITION CONTRACT

**Representation**: mutable `state` column + immutable append-only
`agent_handoff_transitions` rows — an **append-only transition history with
a mutable, hash-coupled current-state projection** (§12.3's exact naming).
Chosen over deriving `state` purely from events (events are audit
projections, deliberately not authoritative, §19) and over immutable
successor records per transition (reintroduces a moving-pointer integrity
problem at higher cost than the composite-FK pattern already solves it for
passports).

Retained states — `completed` is **not** one of them: it asserts work was
executed and verified, which is execution-outcome territory a later
orchestration unit may add with runs/evidence to point at.

| state | meaning | predecessors | successors | terminal |
|---|---|---|---|---|
| `proposed` | created declaration awaiting a decision | (creation) | accepted, refused, clarification_required, cancelled, superseded | no |
| `accepted` | the human recorded acceptance for the recipient identity — **executes nothing** | proposed, clarification_required | cancelled, superseded | no (closeable) |
| `refused` | recorded refusal, with reason code | proposed, clarification_required | — | yes |
| `clarification_required` | the proposal needs operator clarification before a decision | proposed | accepted, refused, cancelled, superseded | no |
| `cancelled` | the human withdrew the delegation | proposed, clarification_required, accepted | — | yes |
| `superseded` | replaced by a named successor handoff | proposed, clarification_required, accepted | — | yes |

Verb table (`models.AGENT_HANDOFF_TRANSITIONS`, the `LIFECYCLE_TRANSITIONS`
idiom, passports.py:74):

```python
#: Keys are CLI verbs; values are (legal source states, target state).
#: `refused`, `cancelled` and `superseded` appear in NO source set: all three
#: are terminal, and the from_state CHECK (§11) is what makes that structural.
AGENT_HANDOFF_TRANSITIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "accept":    (("proposed", "clarification_required"), "accepted"),
    "refuse":    (("proposed", "clarification_required"), "refused"),
    "clarify":   (("proposed",), "clarification_required"),
    "cancel":    (("proposed", "clarification_required", "accepted"), "cancelled"),
    "supersede": (("proposed", "clarification_required", "accepted"), "superseded"),
}
```

```
                 ┌── accept ──────────────► accepted ──┬── cancel ───► cancelled ▣
                 │                             ▲       └── supersede ► superseded ▣
proposed ────────┼── refuse ─────────────► refused ▣    (successor creation only)
   │             ├── clarify ─► clarification_required ─┬─ accept ──► accepted
   │             ├── cancel ──────────────► cancelled ▣ ├─ refuse ──► refused ▣
   │             └── supersede ─────────► superseded ▣  ├─ cancel ──► cancelled ▣
   │                                                    └─ supersede ► superseded ▣
   └── (creation: state='proposed', ZERO transition rows, chain = ())

▣ terminal — appears in no source set; the from_state CHECK makes this structural.
No `completed`. No `reopen`. No standalone `supersede` leaf — it only happens
inside `agent handoff create --supersedes`. No automatic transition.
Complete legal edge set: 11 pairs. All 4 illegal pairs over the two enums
(accepted→refused, accepted→clarification_required, and the two already
blocked by the enum/self-edge CHECKs) are storage-refused (§11 MAJOR-3).
```

**Per-transition contract**:

- **Actor**: always the human operator (`ACTOR_HUMAN`).
- **Required fields**: `refuse`/`clarify` require `--reason CODE` from the
  closed `HANDOFF_REASON_CODES = (out_of_scope, missing_capability,
  conflicting_work, data_classification, objective_unclear,
  constraints_unclear, evidence_unclear, operator_judgment)`; all verbs
  accept optional `--note TEXT` (≤2048 chars, scanned, label `handoff_note`
  — not `note`, which would sit beside the existing `notes` label and invite
  confusion; §19), stored on the transition row only.
- **Preconditions**: every transition requires the handoff record itself to
  verify (row hash + chain intact — the no-laundering gate applied to
  handoffs, §12.3 step 5); `accept` additionally requires both participants
  to exist, be `active`, integrity-ok, history-ok, **and both pins current**
  (pinned version == `current_passport_version`, pinned digest ==
  recomputed digest) — accepting against a moved declaration refuses with
  the §10-style message. `refuse`/`clarify`/`cancel`/`supersede`
  deliberately do **not** require participant validity: closing a record
  must remain possible when a participant was suspended or revoked after
  creation. The complete legal source/target combination is now backstopped
  by §11's CHECK, not application logic alone.
- **Stale-plan behavior**: transitions ignore the plan (it was advisory at
  creation); only *creation* checks plan staleness.
- **Idempotent repeat** (verb whose target state already holds): refusal
  naming the state — "Handoff AH-0001 is already accepted; nothing was
  changed." (same-state transitions are refusals, never silent no-ops).
- **Conflicting repeat** (verb illegal from current state): refusal naming
  current state and the verb's legal sources, exit 1.
- **Expected-current-state**: enforced by in-transaction re-read (CAS,
  §16); the `UNIQUE(handoff_id, seq)` constraint is the storage-level
  backstop — two racing transitions cannot both append seq N+1.
- **Transaction boundary**: one per verb (§16). **Event action**: §19.

## 15. ACTOR, AUTHORITY AND RATIONALE MODEL

- **Authentication assumption**: unchanged from the whole system — one
  trusted local human operating the CLI; `events` rows carry `actor='human'`
  (`ops.ACTOR_HUMAN`). U-A3 introduces no agent authentication, no sessions,
  no identity claims by software.
- **Logical participants**: agent identities appear only as FK references
  and pinned digests. No participant "acts": all eleven CLI leaves are
  human-invoked; all six writes are human-invoked verbs.
- **Rationale references, not approval references.** `decision_id` is the
  only pointer near a `decisions` row, and it is non-authoritative: a
  `decisions` row is an architecture-decision record (`title`,
  `decision_md`, `alternatives_md`, `status`, `decided_at`) with no
  approver, no subject, no grant, and no scope; `status` carries no CHECK
  and is hardcoded to `'accepted'` by its only writer
  (`ops.add_decision`), and no CLI verb ever changes it. **Agentic OS
  currently has no governed approval primitive for these handoffs.** No
  U-A3 code reads `decision_id` as a condition for allowing any operation —
  a handoff with `decision_id=NULL` and one with `decision_id` set produce
  byte-identical behavior on every verb. Any future unit that wants real
  approval semantics must build a real approval primitive first, and must
  not repurpose this column to mean one.
- **Authority non-transfer proof**: the schema (§11) contains no column
  whose value any code path reads to permit execution, approval, spend,
  credential access, provider access, tool/skill grant, data access, or
  lifecycle control; grep-provable, and pinned by tests (no execution / no
  provider / no network / no install). A handoff row's acceptance changes
  exactly three columns (`state`, `updated_at`, `content_sha256`), plus one
  transition row and one event (§12.3 — corrected from the design's
  two-column undercount).
- **Data-classification enforcement**: `data_classification` on a handoff
  is a declaration; U-A3 enforces only (a) vocabulary, (b) the advisory
  recipient warning at create, and (c) privacy handling: like memory,
  `restricted` handoffs render objective/constraints/notes as
  `ops.RESTRICTED_PLACEHOLDER` in `list` output; full text is shown only by
  `agent handoff show` (administrative visibility, M3.2 precedent). The
  word **"ceiling" appears nowhere** in this contract.
- **Secret scanning**: `objective_md`, `constraints_md`, `note_md` pass
  `ops._scan_trusted_write` (warn-on-write, D-v0.2.15) with three new
  `TRUSTED_FIELD_LABELS`: `objective`, `constraint`, `handoff_note`. Doctor's
  stored-secret sweep extends over the three columns (§20).
- **Allowed prose fields + limits**: exactly three (objective ≤4096,
  constraints ≤4096, note ≤2048). Nothing else in U-A3 accepts prose.
- **Event payload allowlists**: §19 — ids, names (redacted-at-emit like all
  agent events), enums, integer versions, counts, reason codes, 12-char hash
  prefixes only. `decision_id` never appears in an event payload.
- **Doctor-detail allowlist**: ids (`RP-000N`/`AH-000N`), agent
  name-or-`agent #id` (`_agent_doctor_label` reused), `v<N>`, closed
  verdicts, counts. Never prose, paths, SQL, exception text, full hashes.
- **Hash-prefix policy**: `models.hash_prefix` (12 chars) everywhere except
  `show`-class output, where full hashes are permitted (M2.6 rule).
- **Malformed SQLite/BLOB handling**: every hash payload routes values
  through the `_text_leaf`/`_int_leaf` discipline; reads never raise on
  damaged rows — they report closed verdicts, and doctor reports
  `unreadable row` for rows that cannot construct dataclasses.
- **Tamper refusal**: any write against a plan/handoff whose hashes or chain
  fail verification refuses with the U-A1 no-laundering message shape and
  points at doctor + RECOVERY.md.
- **Lifecycle changes after plan creation**: never rewrite the plan — they
  make it *stale* (derived). **Revoked/suspended participants after handoff
  creation**: block only `accept`; closing verbs stay available; doctor
  check 40 WARNs.
- **Export/redaction**: `export events` output is safe by construction
  (payload allowlists); no new export surface is added.
- **Obsidian mirror**: deliberately **not extended** — no routing or
  handoff note is generated, no count line added; `obsidian.py`/`render.py`
  stay frozen, so no prose can leak into Markdown by construction (§23).
- Routing explanations print reason codes and tuple components — never
  passport prose (role/mission/limitations are not consulted by eligibility
  at all; only pattern-bound arrays and enums are read).

## 16. TRANSACTION OWNERSHIP AND CONCURRENCY

Universal shape (the `catalog.install` shape, D-v0.4.18): all user-input
validation **before** the transaction; the new domain module owns exactly
one `with db.transaction(conn):` whose first statement is `BEGIN IMMEDIATE`
(write lock before re-reads, making the re-read-then-write pair atomic);
**every fact re-read inside**; rows + hashes + event in the same boundary;
any failure rolls back everything. SQLite transactions are never nested
(participants would commit early); U-A3 adds no transaction participants —
each operation is single-owner.

| operation | owner (module fn) | in-txn re-reads / CAS | inserts | updates | event | idempotency / duplicate | concurrent conflict | error |
|---|---|---|---|---|---|---|---|---|
| create routing plan | `routing.create_plan` | re-resolve task/project/preferred agent; **authoritative eligibility evaluation runs entirely inside the txn** (≤256 agents); supersedes target re-read: exists ∧ no successor | 1 plan row + N candidate rows (hashed, chained by id) | 2 hash-finalization UPDATEs inside this same txn only (§12.2) | `routing_plan`/`create` | none — every invocation is a new plan | second `--supersedes` of the same target hits `UNIQUE(supersedes_id)` → refusal "already superseded by RP-xxxx" | AosError exit 1; internal 2 |
| supersede routing plan | same fn (`--supersedes`) | as above | as above | **none on the predecessor** (derived supersession) | same event, payload carries `supersedes` | — | as above | — |
| select candidate | — **rejected** (§9): no such operation | | | | | | | |
| create handoff | `agent_handoffs.create_handoff` | task (status ≠ done); both agents (active, integrity, history, pointer); pin recomputation; plan (intact ∧ ¬stale ∧ ¬superseded ∧ recipient eligible ∧ task match); supersedes target (state ∈ supersedable ∧ no successor) | 1 handoff row; if superseding: 1 transition row on predecessor | if superseding: predecessor `state`,`updated_at`,`content_sha256` (§12.3) | `agent_handoff`/`propose` (+ `supersede` on predecessor) | none — new declaration each time | `UNIQUE(supersedes_id)` + predecessor CAS | AosError 1 |
| accept | `agent_handoffs.transition` verb=accept | handoff re-read: hash+chain verify, state ∈ sources; participants re-read: full validity + pins current | 1 transition row (seq = max+1) | `state`,`updated_at`,`content_sha256` (one UPDATE, §12.3) | `agent_handoff`/`accept` | repeat on accepted → refusal naming state | racing writers: second `BEGIN IMMEDIATE` waits (busy_timeout 5000), then its CAS sees the moved state → refusal; `UNIQUE(handoff_id,seq)` is the backstop | AosError 1 |
| refuse | verb=refuse (+required reason) | handoff verify + CAS; no participant gate | same | same | `agent_handoff`/`refuse` | same pattern | same | — |
| request clarification | verb=clarify (+required reason) | same; sources = (proposed,) | same | same | `agent_handoff`/`clarify` | same | same | — |
| cancel | verb=cancel | same; sources incl. accepted | same | same | `agent_handoff`/`cancel` | same | same | — |
| supersede handoff | only inside create (`--supersedes`) | predecessor CAS (state supersedable) | successor + predecessor transition | predecessor state+updated_at+hash | `supersede` + `propose` (two events, one txn) | — | same | — |
| complete | — **rejected** (§14) | | | | | | | |

Idempotency keys: none stored — repeatability is handled by CAS refusals
that name the current state (deterministic, side-effect-free retries).
Privacy-safe diagnostics: every refusal names ids, states, closed verdicts,
and the recovery command — never row content.

## 17. CLI CONTRACT

**Eleven leaves; no aliases; every leaf `--json`-capable except pure verbs
where the JSON form is the result object. Exit codes: 0 success · 1 domain
refusal · 2 internal.** All under the existing `agent` parser, new subtrees
`route` and `handoff` (path tuples are distinct from the legacy top-level
`("handoff", …)` — no collision in `COMMAND_POLICY`). **Six authoritative
writes, five read-only leaves** (corrected from the design's "nine
leaves"/"four reads"/"ten writes" — MINOR-3).

| leaf | syntax | behavior | class | recovery | event |
|---|---|---|---|---|---|
| `agent route plan` | `[--task T-…] [--project SLUG] [--family F]… [--capability C]… [--evidence-kind K]… [--require-classification LVL] [--require-autonomy LVL]… [--require-scope global\|project] [--require-class CLASS] [--skill S]… [--tool T]… [--min-context-tokens N] [--modality M]… [--prefer NAME] [--scope-preference specific_first\|none] [--surplus-policy minimal\|ignore] [--max-candidates N] [--supersedes RP-…] [--json]` | validate → canonicalize → evaluate in-txn → store plan + candidates → print `RP-000N` + summary | AUTH_WRITE, ledger=True | blocked | `routing_plan`/`create` |
| `agent route list` | `[--task T-…] [--json]` | plans newest-first: id, created_at, result_status, counts, derived stale/superseded flags | READ_ONLY | allowed | — |
| `agent route show` | `RP-0001 [--json] [--request]` | full plan: candidates, reasons, tuples, pins (full hashes permitted — show-class), staleness verdict; `--request` prints the stored canonical request document | READ_ONLY | allowed | — |
| `agent route verify` | `RP-0001 [--json]` | recompute plan + candidate hashes, chain, pin consistency, staleness; prints closed verdicts; exit 0 intact (stale-but-intact still 0, labeled), 1 on integrity failure | READ_ONLY | allowed | — |
| `agent handoff create` | `--task T-0001 --from NAME --to NAME --objective TEXT [--plan RP-…] [--expect-evidence KIND]… [--min-evidence N] [--constraints TEXT] [--classification LVL] [--decision D-…] [--supersedes AH-…] [--json]` | gates per §13/§16; prints `AH-000N` | AUTH_WRITE, ledger=True | blocked | `propose` (+`supersede`) |
| `agent handoff list` | `[--task T-…] [--state STATE] [--json]` | id, task, from→to, state, created_at; restricted rows show placeholder prose | READ_ONLY | allowed | — |
| `agent handoff show` | `AH-0001 [--json]` | full record + transition history + integrity verdicts (never raises on damage) | READ_ONLY | allowed | — |
| `agent handoff accept` | `AH-0001 [--note TEXT] [--json]` | §14/§16 | AUTH_WRITE, ledger=True | blocked | `accept` |
| `agent handoff refuse` | `AH-0001 --reason CODE [--note TEXT]` | §14/§16 | AUTH_WRITE, ledger=True | blocked | `refuse` |
| `agent handoff clarify` | `AH-0001 --reason CODE [--note TEXT]` | §14/§16 | AUTH_WRITE, ledger=True | blocked | `clarify` |
| `agent handoff cancel` | `AH-0001 [--note TEXT]` | §14/§16 | AUTH_WRITE, ledger=True | blocked | `cancel` |

Rejected leaves: `agent route select` (§9), `agent handoff supersede`
(supersession is `create --supersedes` — a standalone supersede without a
successor is just `cancel`), `agent handoff complete` (§14).

IDs: `ids.PREFIXES` gains `"routing_plan": "RP"` and `"agent_handoff": "AH"`
(two-letter precedent `MS`/`ML`/`ME`; `H` stays the legacy handoff's — no
collision with `T,R,D,E,H,P,M,MS,ML,ME`).

## 17.1 INDEX DECISION

**No indexes on the four U-A3 tables.** The `UNIQUE` constraints already
supply the implicit indexes for every plan-scoped and handoff-scoped
lookup: candidates by plan (`UNIQUE(plan_id, agent_id)`), candidates by
plan/rank (`UNIQUE(plan_id, rank)`), transitions by handoff/sequence
(`UNIQUE(handoff_id, seq)`), successor lookup by `supersedes_id`
(`UNIQUE`, both tables). Three access paths scan, and are accepted on
evidence, not on imitation:

1. **`routing_plan_candidates` by `agent_id`** (the discard guard, §21) —
   the only uncovered path over the fastest-growing table. Reached only by
   `agent discard`, a rare interactive command on a draft identity; SQLite
   must scan the child table for FK enforcement on the parent DELETE
   regardless, indexed or not, so an index would not remove the scan from
   that command's critical path.
2. **`agent_handoffs` by task/state/plan** — handoffs are human-authored one
   at a time; the table is bounded by operator effort at hundreds of rows.
3. **Doctor 38–41 walk every plan and handoff by design** — full scans no
   index improves.

Should a real workspace ever make the first path matter, the answer is
`CREATE INDEX routing_plan_candidates(agent_id)` — additive, and named here
so a future implementer does not have to rediscover it. **It is not added
during U-A3.**

## 18. POWER AND RECOVERY CONTRACT

`power.COMMAND_POLICY` additions — **eleven entries** (mechanical rule —
writes rows ⇒ authoritative):

```
("agent","route","plan")      AUTHORITATIVE_WRITE, ledger=True
("agent","route","list")      READ_ONLY
("agent","route","show")      READ_ONLY
("agent","route","verify")    READ_ONLY
("agent","handoff","create")  AUTHORITATIVE_WRITE, ledger=True
("agent","handoff","list")    READ_ONLY
("agent","handoff","show")    READ_ONLY
("agent","handoff","accept")  AUTHORITATIVE_WRITE, ledger=True
("agent","handoff","refuse")  AUTHORITATIVE_WRITE, ledger=True
("agent","handoff","clarify") AUTHORITATIVE_WRITE, ledger=True
("agent","handoff","cancel")  AUTHORITATIVE_WRITE, ledger=True
```

- **Standard**: all leaves run normally.
- **Deep**: the existing wrap — `deep_check` preflight before and
  post-verification after every `authoritative_write ledger=True` leaf; no
  new deep logic.
- **Eco**: explicit operator requests are never deferred (U-A2 §13
  precedent); no U-A3 operation is an implicit derived refresh, so eco
  behavior is identical to standard for these leaves.
- **Recovery**: the **six** write leaves are blocked **before dispatch**
  (`RECOVERY_ALLOWED_KINDS`); all **five** read leaves remain available —
  inspecting malformed, stale, or tampered plans/handoffs is exactly what
  recovery is for. Recovery never creates, transitions, supersedes, or
  repairs anything. (Corrected counts — MINOR-3.)
- **No automatic planning / no automatic handoff mutation**: nothing outside
  the eleven leaves touches the new tables; no hook, no doctor path, no sync
  path, no power transition writes them (grep-provable; pinned by tests).

## 19. EVENT AND PRIVACY CONTRACT

Ownership rule stated explicitly: **relational rows own the facts**
(objective, constraints, notes, request documents, pins, tuples, reasons,
transition history); **events are audit projections only** — bounded
correlation records, never a source of truth and never sufficient to
reconstruct content.

New entities/actions (`events.emit` unchanged; frozen payload-key tuples in
the new modules, the `catalog.EVENT_PAYLOAD_KEYS` idiom):

- `entity="routing_plan"`, action **`create`** — allowlist:
  `plan`, `task`, `scope`, `algorithm_version`, `request_sha256_prefix`,
  `result_status`, `eligible_count`, `excluded_count`, `unresolved_count`,
  `supersedes`.
- `entity="agent_handoff"`, action **`propose`** — allowlist:
  `handoff`, `task`, `plan`, `from_agent`, `to_agent`, `from_version`,
  `to_version`, `from_passport_sha256_prefix`, `to_passport_sha256_prefix`,
  `data_classification`, `supersedes`. **No `decision_id` key** — the
  rationale reference stays purely relational, never surfaces in an event.
- `entity="agent_handoff"`, actions **`accept` / `refuse` / `clarify` /
  `cancel` / `supersede`** — allowlist: `handoff`, `task`, `seq`,
  `from_state`, `to_state`, `reason_code`.

Plus, on any payload, the existing secret metadata keys (`secret_warning`,
`secret_fields`, `secret_patterns`) exactly as every current event; agent
names are redacted at emit by `secretscan.redact_tree` like all U-A1
events. `schema_version: 1` envelope unchanged.

Events must not and structurally cannot contain: request prose (none
exists), objective/constraint/note text (never keyed), task bodies, passport
bodies, capability strings, skill/tool arguments, provider configuration,
prompts, filesystem paths, full hashes (only `hash_prefix` values are
keyed), SQL, exception text, credentials, restricted content, or the
substring `approval` in any form. A payload-allowlist test mirrors
`test_v04_agent_passports.py:1073` (subset assertion + no 64-hex run + no
prose substrings).

**Secret-scan labels** (`secretscan.TRUSTED_FIELD_LABELS` additions):
`objective`, `constraint`, `handoff_note` — **not** `note`, which would sit
beside the existing `notes` label and invite confusion (MINOR-9). None of
the three collide with the current set (`acceptance`, `agent`,
`alternatives`, `approval`, `capabilities`, `claim`, `decision`,
`from_agent`, `key`, `limitation`, `locator`, `mission`, `name`, `notes`,
`provenance`, `reason`, `ref`, `repo_path`, `role`, `slug`, `source`,
`spec`, `state`, `summary`, `task_family`, `title`, `to_agent`, `value`),
verified by direct inspection of `secretscan.py:58–91`.

## 20. DOCTOR CONTRACT

Four new checks, numbered 38–41; total **37 → 41**. Doctor remains
read-only: it never creates a request, generates a route, selects an agent,
creates/transitions/supersedes a handoff, repairs, or executes — every new
check is SELECT + recompute + compare (no-mutation proven by table-checksum
assertions in the new suite, the existing doctor-doesn't-mutate pattern).

Described as **four checks, one per record family, each reporting a closed
verdict from a fixed vocabulary in its bounded detail — the check-33 shape**
(`_agent_registry_checks`, doctor.py:938–985, which already bundles six
distinct conditions plus a cross-table orphan query into one check). This is
corrected from the design's "single-purpose" framing: checks 38 and 39 each
bundle roughly eight conditions, exactly as check 33 does — that is the
established shape, not an exception to it.

| # | name | verdict | PASS | FAIL/WARN condition | detail format |
|---|---|---|---|---|---|
| 38 | `routing plans verify` | **FAIL** | every plan: row hash matches recomputation; `request_document` parses canonically and matches `request_sha256`; `result_status`/counts coherent with candidate rows; candidate hashes verify; eligible ranks contiguous 1..N; unique (plan, agent); eligible pins match the referenced immutable passport row's recomputed digest; `supersedes_id` resolves | any violation | `RP-000N: <closed verdict>` (`malformed`, `mismatch`, `unhashable`, `request_mismatch`, `rank_gap`, `pin_mismatch`, `counts_incoherent`, `reference_invalid`), bounded by `ROUTING_REASON_DISPLAY_LIMIT` |
| 39 | `agent handoffs verify` | **FAIL** | every handoff: row hash; transition seq contiguous from 1; chain replays from `proposed` through legal edges to the stored current state; vocabulary valid; reason present where required; pins reference existing passport rows and match digests; `superseded` state ⇔ a successor row names it; `supersedes_id` resolves | any violation | `AH-000N: <closed verdict>` (`malformed`, `mismatch`, `unhashable`, `chain_gap`, `chain_illegal`, `state_divergent`, `pin_mismatch`, `reason_missing`, `supersession_incoherent`) |
| 40 | `open agent handoffs with ineligible participants` | **WARN** (actionable) | no handoff in (`proposed`, `clarification_required`, `accepted`) has a participant that is suspended/archived/revoked or integrity-broken | such a handoff exists | `AH-000N: <participant label> <condition>` via `_agent_doctor_label` |
| 41 | `open agent handoffs pinned to stale plans` | **WARN** (actionable) | no handoff in (`proposed`, `clarification_required`) references a stale or superseded plan | such a handoff exists — accept would refuse; re-plan is the action | `AH-000N: plan RP-000N stale` |

**Rejected as a check**: a blanket "stale plans exist" WARN. Staleness of an
unreferenced, historical routing plan is history happening, not damage
(D-v0.3.44's "a check that turns red because history happened is a broken
check" reasoning, applied here); it would train operators to ignore doctor.
Checks 40/41 are correctly scoped to **open** handoffs — exactly the ones
where the next verb would refuse.

**Stored-secret sweep additions**: `agent_handoffs.objective_md`,
`agent_handoffs.constraints_md`, `agent_handoff_transitions.note_md`.
`objective_md` and `constraints_md` fit the existing
`_SWEEP_DOMAIN_FIELDS` mechanism cleanly (rendered via `ids.render_id(entity,
row["id"])`). **`note_md` requires a bespoke sweep loop** (MINOR-9): it
lives on `agent_handoff_transitions`, whose `id` is not a handoff id and has
no `ids.PREFIXES` entry, so its label must be constructed by joining to the
parent handoff: `agent handoff AH-000N transition #<seq> note`. Secret
labels: `objective`, `constraint`, `handoff_note` (§19).

**Doctor 38/39 replay algorithm**: exact procedure specified in §12.2
(routing plans) and §12.3 (handoffs) — doctor implements exactly those
verification procedures, no more, no less.

**Pins requiring mechanical updates**: `test_v04_agent_passports.py:1127`
(`test_doctor_emits_exactly_37_checks` → 41),
`test_v04_agent_catalog.py:2220` (`len(checks) == 37` → 41),
`test_cli.py:830` (count-chain comment/assertion `21→25→30→34→37` → `…→41`),
`doctor.py` module docstring count narrative.

## 21. DISCARD-GUARD EXTENSION

`passports.py` receives **exactly one bounded change**: `_REFERENCE_QUERIES`
(passports.py:1108) gains one entry, and its docstring is updated. Nothing
else in the module moves.

**Reachability analysis, decided here so no implementation model has to
judge it**: a draft agent can appear as an `excluded` candidate (reason
`draft_only`), so `routing_plan_candidates.agent_id → agents(id)` (plus the
new composite passport FK, §11 correction 1) would make `discard_agent`'s
`DELETE FROM agents` raise `IntegrityError` (exit 2) instead of the guard's
documented exit-1 refusal — **this reference is reachable and must be
guarded.** A governed handoff participant reference is **not** reachable
from a draft-agent discard: `discard_agent` requires `lifecycle='draft'`,
`agent_handoffs` participants must be `active` at creation (§13), and
`LIFECYCLE_TRANSITIONS` (passports.py:74–79) has **no path back to `draft`**
from any state — a draft agent can therefore never be a handoff
participant. **Decision: extend the guard with `routing_plan_candidates`
only; do not add an `agent_handoffs` entry.** Adding a query over a
structurally-unreachable reference would be validation for a scenario that
cannot happen; a future unit is free to add it defensively if it ever
becomes reachable (e.g., if a lifecycle transition back to `draft` is ever
introduced), at which point it would earn its own decision record.

**Exact addition** — name-joined, matching the existing shape exactly
(corrected from "id-based" — MINOR-6; the guard's param builders receive
only the agent's name, `lambda n: (n,)`):

```python
("routing_plan_candidates",
 "SELECT COUNT(*) FROM routing_plan_candidates c "
 "JOIN agents a ON a.id = c.agent_id WHERE a.name = ?", lambda n: (n,)),
```

Docstring update: "every place a historical reference to an agent — textual
or by id — can live" (the join makes an id-keyed table reachable through
the existing name-based call signature without changing that signature).

## 22. MIGRATION AND SCHEMA CONTRACT

**Schema becomes v5.** Invariant 21/22 discharge: v4 is not preserved (new
governed durable records genuinely require DDL), and v5 is not convenience
(every new table carries constraints no existing table can express:
composite passport pins, transition chains, candidate uniqueness, cycle
freedom, three-way result-status coherence).

Migration: **`u-a3-routing-handoffs-v5`**, `from_version=4, to_version=5`,
appended to `migrations.MIGRATIONS` (registry grows 3 → 4 entries). The
step body is **purely additive**: it creates the four tables EMPTY from the
same `db.py` DDL constants `SCHEMA_SQL` composes (the **D-v0.3.42**
shared-DDL rule — corrected citation, §5 item 10 — applied a fourth time),
touches no existing table, reads no rows, fabricates nothing (there are no
legacy routing facts to carry, so there is nothing to fabricate), takes no
clock reading (no row is stamped), and runs inside the unchanged U-M1 frame:
`apply_migrations` owns the transaction, the verified pre-mutation snapshot
(v4-stamped), the `foreign_key_check`, the single commit, and the rollback +
restore-hint on injected failure.

```python
# db.py — four constants, {table}-parameterized (the migration-rename rule),
# each with the "no default on the hash column" comment the others carry.
ROUTING_PLANS_DDL = """CREATE TABLE {table}( … )"""              # §11
ROUTING_PLAN_CANDIDATES_DDL = """CREATE TABLE {table}( … )"""    # §11
AGENT_HANDOFFS_DDL = """CREATE TABLE {table}( … )"""              # §11
AGENT_HANDOFF_TRANSITIONS_DDL = """CREATE TABLE {table}( … )"""   # §11

ROUTING_PLANS_TABLE = "routing_plans"
ROUTING_PLAN_CANDIDATES_TABLE = "routing_plan_candidates"
AGENT_HANDOFFS_TABLE = "agent_handoffs"
AGENT_HANDOFF_TRANSITIONS_TABLE = "agent_handoff_transitions"

#: The four tables U-A3 adds, paired with their DDL, in FK-parent-first order.
#: The 4→5 migration iterates this rather than repeating the CREATEs, so a
#: fresh v5 schema and a migrated one cannot carry different routing tables —
#: the MEMORY_GRAPH_TABLES shape, applied a second time.
ROUTING_HANDOFF_TABLES: tuple[tuple[str, str], ...] = (
    (ROUTING_PLANS_TABLE, ROUTING_PLANS_DDL),
    (ROUTING_PLAN_CANDIDATES_TABLE, ROUTING_PLAN_CANDIDATES_DDL),
    (AGENT_HANDOFFS_TABLE, AGENT_HANDOFFS_DDL),
    (AGENT_HANDOFF_TRANSITIONS_TABLE, AGENT_HANDOFF_TRANSITIONS_DDL),
)

SCHEMA_VERSION = "5"

SCHEMA_SQL = (
    _SCHEMA_HEAD
    + …unchanged through AGENT_PASSPORTS_DDL…
    + AGENT_PASSPORTS_DDL.format(table=AGENT_PASSPORTS_TABLE)
    + ";\n\n"
    + ";\n\n".join(ddl.format(table=t) for t, ddl in ROUTING_HANDOFF_TABLES)
    + ";\n"
)


def _routing_handoffs_v5(conn: sqlite3.Connection) -> None:
    """Create the four U-A3 tables EMPTY. Purely additive.

    No existing table is read, rebuilt, renamed or re-stamped; no row is
    carried, parsed or invented; NO CLOCK IS READ, because no row is
    stamped. Built from the same db.py constants a fresh v5 init uses
    (D-v0.3.42, applied a fourth time), created in FK-parent-first order
    under their real names — so there is no temp-table rename, and a
    migrated schema is BYTE-identical to a fresh one, not merely
    structurally identical.

    Runs inside U-M1's already-open transaction: no COMMIT, no ROLLBACK, no
    touching meta.schema_version — all three belong to apply_migrations.
    """
    for table, ddl in db.ROUTING_HANDOFF_TABLES:
        conn.execute(ddl.format(table=table))


ROUTING_HANDOFFS_V5 = Migration(
    from_version=4, to_version=5,
    migration_id="u-a3-routing-handoffs-v5",
    apply=_routing_handoffs_v5,
)

MIGRATIONS = (MEMORY_CLAIMS_V2, MEMORY_GRAPH_V3, AGENT_PASSPORTS_V4,
              ROUTING_HANDOFFS_V5)   # 3 → 4 entries
```

`migrations.LATEST_VERSION` derives from `db.SCHEMA_VERSION`, so the bump
lands in one place. `_check_schema_version` then refuses v4 ledgers with the
standard three-command migrate message; normal commands still never
auto-migrate. Fresh `init` creates v5 directly via `SCHEMA_SQL`.
Migration-status output gains one pending row on v4 workspaces.

**Historical migration freeze — deferred obligation, recorded, not
discharged now (MAJOR-6).** `migrations.py:416–417`'s
`_agent_passports_v4` docstring records: "Builds from the LIVE
`db.AGENTS_DDL` — correct while 4 is current; a frozen copy becomes v5's
obligation." U-A3 is the unit that makes v4 historical, yet it changes
**neither `AGENTS_DDL`, `AGENT_PASSPORTS_DDL`, nor `agent_identity_payload`**
— so the live constants the 3→4 step builds from are still the v4
constants, and 3→4 still lands a genuine v4 database. No drift materializes.
The precedent for deferring rather than freezing-now is the 2→3 step, which
*still* builds from the live `db.MEMORY_CLAIM_DDL` today, at v4 — the freeze
has historically been discharged only when a constant would actually drift
(U-M3 changed the memory-claim DDL, so 1→2 was frozen; U-A1 changed the
agents table, so `_V3_AGENTS_DDL` was frozen), not mechanically at every
version bump. **The obligation transfers, unchanged, to the first future
unit that edits `AGENTS_DDL`, `AGENT_PASSPORTS_DDL`, or
`agent_identity_payload`**, which must freeze `_V4_AGENTS_DDL` /
`_V4_AGENT_PASSPORTS_DDL` / the v4 identity payload before it edits any of
the three. A guard test makes the deferral safe rather than merely recorded:

```
test_v4_migration_targets_are_unchanged_from_the_u_a1_baseline
  — byte-compare db.AGENTS_DDL and db.AGENT_PASSPORTS_DDL against literals
    frozen in the test at 80b7e82577cbed19aa1823934df44ae09a644ac5, and pin
    the sorted key list of passports.agent_identity_payload for a fixed
    Agent. Failing this test IS the signal that the deferred freeze
    obligation has come due.
```

This is strictly better than performing the freeze now: it costs one test,
changes no historical step body, and converts a silent trap into a loud one.
Recorded as decision D-v0.4.29 in DECISIONS.md.

**Migration hazard verification** (all five checked against this baseline):
creating tables twice cannot happen (fresh `init` and a v4 workspace's
3→4-then-4→5 path are disjoint, and the four DDL constants use plain
`CREATE TABLE`, not `IF NOT EXISTS`, so a double-create would raise);
diverging fresh/migrated SQL cannot happen, and more strongly than
structural identity — byte identity, because the new tables are created
directly under their real names; migration isolation holds (creates four
empty tables, touches nothing else, no clock read, no COMMIT/ROLLBACK/
schema_version write inside the step); mutating historical migration
definitions is the MAJOR-6 governance conflict, resolved above by deferral
+ guard test; foreign-key ordering holds (every external parent exists
before the four are composed; internally, plans → candidates → handoffs →
transitions satisfies every FK; `apply_migrations` runs with
`foreign_keys=OFF` + a whole-database `foreign_key_check` before the single
commit — four empty tables contribute zero violations).

## 23. BACKUP, EXPORT, SYNC, MIRROR AND PACKAGING IMPACT

- **Migration snapshots**: unchanged frame; the 4→5 apply snapshots the v4
  database first (verified, `expected_schema_version="4"` at lock time) — no
  code change beyond the registry entry.
- **Database backup**: `backup create/verify/restore` operate on the whole
  file — new tables are covered automatically; no change.
- **Export**: `export events` gains the new events, safe by §19
  construction; no new export surface.
- **Obsidian sync / generated notes**: **no change**. No routing or handoff
  note, no Home count line; `obsidian.py`, `render.py`, `mirror_export.py`
  frozen. The cheapest correct implementation of "no routing/handoff prose
  in Markdown by default" is generating nothing; mirror presentation is
  deferred work (§28).
- **Package data**: no new resources (no protocol artifact, no catalog
  file); `pyproject.toml` untouched.
- **Zipapp**: `tools/build_zipapp.py` carries the runtime package's `.py`
  files — the two new modules ride along; the D-v0.4.14 manifest-driven
  catalog allowlist is untouched.
- **Script/module/console/zipapp parity**: the new leaves join the existing
  parity assertions (identical stdout bytes across entrypoints for
  `route show`, `handoff show`, `doctor`).
- **Recovery documentation**: RECOVERY.md gains a bounded section: tampered
  plan/handoff → doctor names it → recovery mode → inspect via
  `route show/verify`, `handoff show` → restore from backup or accept the
  documented loss; TROUBLESHOOTING.md gains the stale-plan and
  pins-moved-on-accept entries.

## 24. EXACT FILE BOUNDARY

**Required new files**:

- `agentic_os/routing.py` — request validation/canonicalization, eligibility,
  ordering, plan creation/reads/verify/staleness (owns its transactions).
- `agentic_os/agent_handoffs.py` — handoff creation, transition engine,
  reads/verify (owns its transactions). A separate module avoids colliding
  with `ops.py`'s legacy handoff functions and gives each write path one
  obvious owner.
- `tests/test_v04_routing_handoffs.py` — the §26 matrix.
- `agentic-os-v0.4-u-a3-routing-handoffs-contract.md` — this document.

**Required modified files**:

| file | change |
|---|---|
| `agentic_os/models.py` | §7/§14 vocabularies + four dataclasses (`RoutingPlan`, `RoutingPlanCandidate`, `AgentHandoff`, `AgentHandoffTransition`). `AGENT_AUTONOMY_LEVELS` is **unordered; no rank function**. |
| `agentic_os/db.py` | `SCHEMA_VERSION="5"`, four DDL constants, `ROUTING_HANDOFF_TABLES`, `SCHEMA_SQL` append (§22). |
| `agentic_os/migrations.py` | `ROUTING_HANDOFFS_V5` + registry append. **Historical step bodies unchanged** — with the §22 deferral decision + guard test. |
| `agentic_os/ids.py` | `RP` / `AH`. Verified no collision. |
| `agentic_os/cli.py` | **eleven** handlers + parser wiring. |
| `agentic_os/power.py` | eleven `COMMAND_POLICY` entries. |
| `agentic_os/doctor.py` | checks 38–41, sweep extension (**incl. the bespoke transitions loop for `note_md`**), count narrative. |
| `agentic_os/secretscan.py` | `TRUSTED_FIELD_LABELS` += `objective`, `constraint`, `handoff_note`. |
| `agentic_os/passports.py` | **one bounded change**: `_REFERENCE_QUERIES` + docstring, `routing_plan_candidates` only, name-joined (§21). |
| docs | `README.md`, `RECOVERY.md`, `TROUBLESHOOTING.md`, `DECISIONS.md` (D-v0.4.21+). |
| test pins | `test_v04_agent_passports.py` (`:202` `"4"`→`"5"`, `:216` three→four registry steps, `:1127` 37→41), `test_v04_agent_catalog.py` (`:2220`), `test_cli.py` (`:830` chain `…→37→41`), `test_v02_migrations.py` (`:199` `LATEST_VERSION == 4` → `5`, registry length, status/plan target strings). |

**Corrections to the boundary itself** (MINOR-8):

- **No new v4 fixture.** `tests/fixtures/` holds `v1_workspace.py`,
  `v2_workspace.py`, `v3_workspace.py` only (verified by direct listing at
  this baseline) — chaining from `v3_workspace` through the existing frozen
  3→4 and 4→5 steps yields the `migrated` test fixture with **no new file**.
  The design's proposed "new v4 fixture" is dropped; no repository evidence
  requires it.
- **`test_v04_agent_passports.py:229` (`test_no_index_was_added`) needs no
  change** — verified scoped to `tbl_name IN ('agents','agent_passports')`,
  so it neither forbids nor requires updating for the four new tables.
- **`test_v02_backup.py` likely needs no change** — verified its version
  assertion is `manifest["schema_version"] == db.SCHEMA_VERSION` (derived);
  its other `"1"`/`"999"` literals are fixture/negative values, not baseline
  pins.

**Conditionally modified** (only if a grep at implementation time finds a
pinned `"4"`/table-set/entrypoint-list assertion): `tests/test_v02_hooks.py`,
`tests/test_v02_power_modes.py`, `tests/test_v02_packaging.py`,
`tests/test_core.py`, `tests/test_complete_today.py`,
`tests/test_v02_hardening.py`.

**Frozen** (must remain byte-identical; several already have byte-identity
tests): `agentic_os/protocols.py`, `agentic_os/catalog.py`,
`agentic_os/catalog/*`, `protocols/*` (registry + four schemas),
`agentic_os/events.py`, `agentic_os/ops.py` (verified: `_scan_trusted_write`
validates labels against `secretscan.TRUSTED_FIELD_LABELS`, so registering
labels in `secretscan.py` alone suffices; `ACTOR_HUMAN` and
`RESTRICTED_PLACEHOLDER` are read-only uses), `agentic_os/obsidian.py`,
`agentic_os/render.py`, `agentic_os/mirror_export.py`,
`agentic_os/search.py`, `agentic_os/pack.py`, `agentic_os/backup.py`,
`agentic_os/export.py`, `agentic_os/hooks.py`, `agentic_os/ingest.py`,
`agentic_os/retrieval.py`, `agentic_os/review.py`, `agentic_os/utils.py`,
`aos.py`, `aos_hooks.py`, `agentic_os/__main__.py`, `pyproject.toml`,
`tools/*`, `adapters/*`, all historical migration step bodies (§22).

**Forbidden**: `.agentic-os/` anywhere, any live ledger, any
`protocols/registry.json` edit, any catalog artifact edit, any
`RESERVED_AGENT_*` edit.

**Generated artifacts**: none. **Migration files**: the one registry entry
in `migrations.py` (no separate file — house layout). **Protocol
artifacts**: none.

## 25. SERIAL IMPLEMENTATION WAVES

Every wave: single branch, serial, stop at the gate; no wave invents
architecture beyond this contract.

- **Wave 0 — contract freeze** (this document). Files: this contract,
  DECISIONS.md (D-v0.4.21–32). No code. Gate: contract review against the
  audit's checklist (§29). Stop: docs committed.
- **Wave 1 — vocabulary, DDL, migration.** Files: `models.py`, `db.py`,
  `migrations.py`, `ids.py`, tests (migration + schema groups). **Runs the
  pin-update grep sweep first** (`schema_version`, `"4"` pins,
  `sqlite_master` table-set assertions) and updates them mechanically before
  any feature wave. Includes the §22 guard test and the §11 corrected DDL.
  Schema: v5. Protocol: none. Transactions: `apply_migrations` frame only.
  Gate: migration suite + full regression with mechanical pin updates. End:
  v5 workspaces, four empty tables, no commands.
- **Wave 2 — request + eligibility.** Files: `routing.py` (validation,
  canonicalization, digest, eligibility), test groups 1–19. Pure functions;
  no transaction. Implements `required_autonomy` /
  `required_data_classification` membership and the split reason
  vocabularies. Gate: eligibility matrix green (incl. the absent-
  `data_classifications` case), canonical-byte determinism.
- **Wave 3 — ordering + plans + route CLI.** Files: `routing.py` (ordering,
  `create_plan`, reads, verify, staleness), `cli.py` (four route leaves),
  `power.py` (four entries), test groups 20–27, 39-partial, 41-partial.
  Implements §12.2's `_PENDING_HASH` sequence and the `ORDER BY id` chain
  rule. Transaction owner: `routing.create_plan`. Gate: plan persistence,
  hash recomputation, two-workspace determinism — asserting `(rank, name,
  version, document-digest, reasons)` and `request_sha256`, **not**
  `content_sha256` (§8).
- **Wave 4 — handoffs + transitions.** Files: `agent_handoffs.py`,
  `passports.py` (discard guard, §21), `secretscan.py`, test groups 28–38.
  Includes the 15-pair direct-SQL edge matrix and the cycle-CHECK tests
  (§26). Owner: `agent_handoffs.create_handoff` / `.transition`. Gate: full
  lifecycle matrix + concurrency + rollback.
- **Wave 5 — handoff CLI, power, recovery.** Files: `cli.py` (seven handoff
  leaves), `power.py` (seven entries), test groups 41–44. Gate: eleven-
  classification coverage test, recovery blocks the six writes pre-dispatch
  and allows the five reads, deep wrap.
- **Wave 6 — events, doctor, sweep.** Files: `doctor.py`, test groups
  39–40, 48–49. Includes the bespoke transitions sweep loop. Gate: 41
  checks, allowlists, doctor-mutates-nothing (table checksums).
- **Wave 7 — packaging, parity, docs.** Files: README/RECOVERY/
  TROUBLESHOOTING, parity tests (50–51, 53–58). Gate: zipapp parity,
  byte-identity of every frozen surface.
- **Wave 8 — acceptance.** Full suite, dogfood drill (two workspaces + one
  migrated fixture), `git diff --check`, clean tree. Stop: report results,
  including any pre-existing failure by name.

## 26. DETAILED TEST MATRIX

Grouped per the mandated dimensions; every group runs against the standard
two fixtures — `fresh` (v5 init) and `migrated` (v3→v4→v5 chain via the
frozen steps, no new fixture file — §24) — unless stated. Assertions
abbreviated: P = persistence (row content asserted by direct SELECT), R =
rollback/no-mutation (table checksums or COUNTs unchanged), V = privacy (no
prose/full-hash/path in event payloads, doctor output, stderr), D =
deterministic output (byte-identical across repeats/workspaces).

1–4 **Request validation / normalization / canonical serialization /
hashing**: `routing.validate_request` unit tests — unknown key refusal,
duplicate array refusal, unsorted input → sorted document, bound overflow
refusals, task/project conflict refusal, absent-fields-neutral document;
identical logical requests (flag order shuffled) → identical canonical bytes
and `request_sha256` (D); document contains no timestamp/actor.
5–7 **Eligibility / reason ordering / reason bounds**: registry fixture with
one agent per condition (§7 rows 1–19) — verdict + exact reason list per
candidate; multi-reason candidate (suspended + missing_capability) emits
canonical order; >8 reasons render truncates with `(+N more)` (using
`ROUTING_REASON_DISPLAY_LIMIT`, not `doctor.UH2_DISPLAY_LIMIT`) while JSON
carries all (P, V).
8 **Global/project scope**: project-scoped agent vs other-project request
(`project_mismatch`), `required_scope` both directions, T2 specificity; a
`required_scope` refusal message echoes "a filing statement, never an
access grant."
9–11 **Lifecycle / identity-integrity / passport-history refusal**: draft,
suspended, archived, revoked, tampered identity (UPDATE name by SQL),
tampered history (document byte flip) → excluded with exact codes; handoff
accept blocked on tamper (R).
12–14 **Catalog/custom parity / uninstalled catalog / legacy**: same
requirements, catalog + derived custom twins → identical verdicts and
adjacent ranks by name only; empty catalog workspace plans fine;
`--prefer aos.builder` uninstalled → `catalog_not_installed` request-level
refusal naming install, and **no row created, no event** (R); `--prefer
NOSUCH` → `agent_absent`, same (R); legacy agent → `legacy_without_passport`.
15–17 **Missing requirements / malformed declarations / unknown vocabulary**:
declaration-absent vs declaration-lacking (`declared:false` diagnostic,
including for `data_classification_mismatch`); passport with hand-published
odd values → `unresolved` whole-candidate; unknown enum in consulted
declaration → `unknown_declaration_value`.
18–19 **Malformed SQLite values / BLOB containment**: BLOB in
`objective_md`, non-integer `rank` via raw SQL → reads report closed
verdicts without raising, doctor 38/39 FAIL value-free (V); `route verify`
exit 1.
20–22 **Ordering tuple / final tie-break / two-workspace determinism**:
constructed surplus ladders assert each component's direction and the exact
`ordering_json`; twins differing only in name assert T7; same logical
registry inserted in two workspaces in reversed order → identical ranked
`(name, version, digest, reasons)` and identical `request_sha256` (D) —
**assertion explicitly excludes `content_sha256`** (§8).
23–27 **Plan creation / pinning / staleness / supersession / selection**:
plan rows + candidate rows + hashes verified by recomputation (P); pins
equal the passport rows' recomputed digests; **direct-SQL insert of a
candidate pinning a non-existent `(agent_id, version)` raises
`IntegrityError`; the same pinning another agent's version raises; an
excluded candidate with NULL `passport_version` inserts cleanly** (BLOCKER-1);
publish v(N+1) → stale derived, `show`/`verify` label it, handoff create
refuses with the §10 message; `--supersedes` chains linear (second
successor refused, R); direct-SQL `supersedes_id = id` and `supersedes_id >
id` both raise `IntegrityError` on `routing_plans` (structural correction
3); *selection*: no `route select` leaf exists (parser test) — selection
expressed via handoff create `--plan` with recipient-not-in-plan refusal.
**Result-status truth table** (MAJOR-2): all nine `(status, eligible_count,
unresolved_count)` combinations driven by direct SQL — rows `(resolved,>0,0)`,
`(resolved,>0,>0)`, `(no_eligible_candidates,0,0)`, `(unresolved,0,>0)`
insert; the other five raise `IntegrityError`; the CLI produces exactly
those four rows across an eligible-only, mixed, all-excluded, and
unresolved-only registry.
28 **Handoff creation**: full-field row, pins, event; done-task refusal;
draft/suspended participant refusal; self-handoff refusal; plan/task
mismatch refusal (R each); direct-SQL `supersedes_id = id` /
`supersedes_id > id` raise on `agent_handoffs` too.
29–33 **Every legal / illegal transition / idempotent / conflicting /
concurrent**: **parametrized direct-SQL insert of all 15 `(from_state,
to_state)` pairs over the two enums — the 11 legal ones insert, the 4
illegal ones raise `IntegrityError`** (MAJOR-3, incl. `accepted→refused` and
`accepted→clarification_required`); the CLI matrix drives the same 11
through the verbs (P), illegal ones refuse naming state (R); repeat accept
refusal; two-connection race: first commits, second's CAS refuses; seq
uniqueness proven by direct duplicate insert failing.
34–36 **Clarification / cancellation / supersession**: reason-required
enforcement (CLI + CHECK), note storage under label `handoff_note` + scan,
cancel-from-accepted, create-with-supersedes atomically transitions
predecessor (both events, one txn — crash injection between the two rolls
back both, R); second successor of one target raises `IntegrityError` and
the CLI refuses with "already superseded by RP-xxxx"/"AH-xxxx" (R);
superseding an already-`refused` handoff refuses on CAS.
37 **Completion**: no `complete` leaf, no `completed` vocabulary (parser +
models assertions).
38 **Transaction rollback**: injected failure after candidate insert / after
transition insert → zero rows, zero events survive, **no row carries
`content_sha256 = ''` or any non-64-hex value after any successful create**
(R, MAJOR-1); a planted `''` hash is reported by doctor 38/39 as
`malformed` and by `route verify`/implicit handoff verify as exit 1; a
grep-test that no command module contains an UPDATE against `routing_plans`
or `agent_handoffs` outside `routing.create_plan` / the transition/create
functions.
39 **Event privacy**: allowlist-subset + no-64-hex + no-prose for all seven
actions (V); secret-shaped objective → `secret_warning` metadata, canonical
row keeps text, event doesn't; **grep-test: the substring `approval` appears
in this contract, `routing.py` and `agent_handoffs.py` only inside the
explicit "no approval primitive exists" negation, never describing
`decision_id`** (BLOCKER-3, adapted from the audit's stricter draft to match
this contract's required "no governed approval primitive" sentence, §2/§15);
`decision_id` is never read in any conditional in the two new modules; a
handoff with `decision_id=NULL` and one with `decision_id` set produce
byte-identical behavior on every verb.
40 **Doctor**: 41 checks exactly; each of 38–41 driven to FAIL/WARN by
targeted corruption; doctor mutates nothing (checksums); bespoke
`note_md` sweep loop finds a planted secret in a transition note under
label `agent handoff AH-000N transition #<seq> note`.
41–44 **Power / recovery / deep / eco**: eleven classifications present
(coverage test), recovery blocks the six writes pre-dispatch with empty
stdout and allows the five reads on a tampered fixture; deep preflights +
post-verifies `route plan` and `handoff accept`; eco runs explicit writes
immediately.
45–47 **Fresh / migrated / snapshot-status**: **fresh-vs-migrated
`sqlite_master` byte-identity** (not merely structural) for the four tables'
`CREATE TABLE` SQL text; migration preserves every pre-existing row
byte-identically; `migrate status/plan` narrate the one pending step;
snapshot exists, verifies at v4, restore-hint on injected failure;
`test_v4_migration_targets_are_unchanged_from_the_u_a1_baseline` guard test
(§22) passes at this baseline.
48–49 **Backup/export / sync-mirror**: backup round-trips the new tables;
`export events` includes new actions, payloads safe; `sync` output
byte-identical to baseline for a workspace with plans+handoffs (mirror
untouched proof).
50–51 **Packaging / entrypoint parity**: zipapp builds and runs `route
show`/`handoff show`/`doctor` byte-identically to script/module/console (D).
52–53 **Schema / protocol preservation**: v5 stamp; exactly four
`MIGRATIONS` entries; historical step bodies byte-identical to baseline;
`protocols/registry.json` + four schemas byte-identical; `REQUIRED_IDENTITIES`
unchanged.
54–57 **No network / no provider / no execution / no auto-install**: socket
guard active for all new code paths; grep-tests: no subprocess/exec/open-of-
declared-values in the two new modules; plan + handoff flows never create
catalog rows (COUNT before/after).
58 **Two-workspace isolation**: operations in workspace A leave workspace
B's tables and mirror untouched.

**Vocabulary-correctness tests (new, cross-cutting)**:

- `AGENT_AUTONOMY_LEVELS` equals the passport schema's `autonomy` enum, as a
  **set**; a symbol-absence test asserts no rank/ordering function exists
  over it; an agent declaring `scoped` is eligible under
  `--require-autonomy scoped` and `autonomy_mismatch`-excluded under
  `--require-autonomy suggest`; membership never consults tuple index
  (BLOCKER-2).
- `set(MEMORY_SENSITIVITIES) == set(protocols.DATA_CLASSIFICATIONS) ==` the
  passport schema's `data_classifications` item enum, pinned by test
  (MINOR-4); request against an agent declaring `["public","internal"]`
  asking `confidential` → `data_classification_mismatch, declared: true`;
  the same request against an agent declaring no set →
  `data_classification_mismatch, declared: false`; an agent declaring only
  `["confidential"]` is **excluded** for an `internal` request (proving
  membership, not clearance); grep-test that "ceiling" appears nowhere in
  the contract or the two new modules (MAJOR-4).
- `set(ROUTING_REASON_CODES) & set(ROUTING_REQUEST_REFUSAL_CODES) == set()`;
  doctor 38 FAILs a planted candidate whose `reasons_json` contains
  `agent_absent` (proving the storable set is the validated set) (MAJOR-5).

## 27. ACCEPTANCE GATE

All of: deterministic ordered results reproduced across two workspaces;
every stored plan and handoff hash-verifiable by recomputation; plan
post-commit immutability (no UPDATE/DELETE reaches a **committed** plan or
candidate row; the only in-transaction UPDATEs are the creating
transaction's hash finalization and the transition write's
state+updated_at+hash); complete rollback on injected mid-transaction
failure (zero rows, zero events); the full transition matrix enforced with
CAS refusals naming states, backstopped by the 15-pair structural CHECK;
recovery blocking all **six** writes pre-dispatch with empty stdout and
allowing all **five** reads; doctor exactly 41 checks, mutation-free; event
payload keys a subset of the §19 allowlists with no 64-hex run and no
prose; legacy `handoffs`, `protocols/*`, catalog artifacts and all frozen
modules byte-identical to baseline; schema v5 fresh/migrated
**byte-identity** for the four new tables; migration snapshot + rollback +
corrected retry proven; the migration-freeze guard test passing; entrypoint
parity; no network/subprocess/execution in new code; no ordering/rank
function over `AGENT_AUTONOMY_LEVELS`; no code path reads `decision_id` as a
condition for allowing an operation; focused suite green; full-suite result
reported honestly; `git diff --check` clean; clean tree.

## 28. DEFERRED WORK

- A `completed` state + completion evidence binding (needs execution-outcome
  facts; a future orchestration unit).
- **A real approval primitive.** None exists today; `decision_id` remains a
  non-authoritative rationale reference until a future unit builds one
  explicitly and earns its own decision record.
- **An autonomy ladder**, if ever justified — it would need its own decision
  record and its own evidence that the levels are genuinely comparable,
  which does not exist today for `supervised` vs. `scoped`.
- `CREATE INDEX routing_plan_candidates(agent_id)` — named as the answer if
  the `agent discard` scan path ever measurably matters; **not added during
  U-A3 without measured evidence** (§17.1).
- Orchestration consumption of plans/handoffs; any automation.
- Cross-workspace handoff exchange (would justify a `beast.agent-handoff/vN`
  protocol).
- Mirror notes / Home counts for plans and handoffs.
- Maturity-aware preferences (blocked on parity concerns, invariant 5).
- Search integration for the new tables.
- Catalog uninstall/park; signatures (U-S5); skills/tools resolution
  (U-K1/U-T1); providers, credentials, spend; MCP/A2A; AICompany.

## 29. CONTRACT-FREEZE CHECKLIST

**Blockers — all three discharged in this document:**

- [x] **B1 — Routing candidate passport pin.** `FOREIGN KEY(agent_id,
  passport_version) REFERENCES agent_passports(agent_id, version)` added to
  `routing_plan_candidates` (§11); the discard side effect recorded (§11,
  §21); §9's "enforceable" claim is now true.
- [x] **B2 — Autonomy is not a ladder.** Ladder deleted. `required_autonomy`
  (array, membership) replaces `autonomy_ceiling`; `autonomy_mismatch`
  replaces `autonomy_exceeds_ceiling`; `AGENT_AUTONOMY_LEVELS` is unordered
  with the anti-ladder comment (§7, §14); **no rank function exists** (§6,
  §7); §2 states "zero new semantic commitments."
- [x] **B3 — Decision is rationale, not approval.** Every phrase implying a
  `decisions` row represents approval is removed. `decision_id` is defined
  as a non-authoritative rationale reference to an ADR row (§13, §15); no
  U-A3 code reads it as a condition for allowing an operation (§15); §2 and
  §15 explicitly state Agentic OS has no governed approval primitive for
  these handoffs.

**Majors — all six discharged:**

- [x] **M1 — Post-commit immutability.** §9 and §27 restated as post-commit
  immutability; the `_PENDING_HASH` sequence and the `ORDER BY id` /
  `ORDER BY seq` chain rules are written into §12 in full.
- [x] **M2 — Result-status completeness.** Two additional `result_status`
  CHECKs added (§11); `no_candidates` renamed `no_eligible_candidates`
  everywhere.
- [x] **M3 — Complete legal handoff edge.**
  `CHECK (from_state <> 'accepted' OR to_state IN ('cancelled','superseded'))`
  added to `agent_handoff_transitions` (§11), with the completeness proof.
- [x] **M4 — Data classification is membership, not a ceiling.**
  `required_data_classification` renamed (§6); "ceiling" deleted everywhere
  in this contract; the absent-declaration case (`declared: false`) is
  specified for this dimension (§6, §7).
- [x] **M5 — Request refusals split from candidate reasons.**
  `ROUTING_REQUEST_REFUSAL_CODES` is a separate, never-stored vocabulary
  (§7); `ROUTING_REASON_CODES`' class column and bound are corrected to ≤24.
- [x] **M6 — Historical migration freeze deferred, with a guard.** §22
  records the deferral and the transfer of obligation to the first unit
  that edits `AGENTS_DDL`/`AGENT_PASSPORTS_DDL`/`agent_identity_payload`,
  plus the guard test.

**Minors — all nine discharged:**

- [x] Mn1 — shared-DDL citation corrected to D-v0.3.42 everywhere (§5, §22).
- [x] Mn2 — fabricated quotation removed; D-v0.4.4 is quoted accurately or
  paraphrased without quotation marks (§3).
- [x] Mn3 — eleven leaves / six writes / five reads corrected everywhere
  (§17, §18, §27).
- [x] Mn4 — classification vocabulary pinned equal by test across
  `MEMORY_SENSITIVITIES` / `protocols.DATA_CLASSIFICATIONS` / the passport
  enum (§6, §26).
- [x] Mn5 — `ROUTING_REASON_DISPLAY_LIMIT = 8` named explicitly, not
  attributed to `doctor.UH2_DISPLAY_LIMIT` (§7).
- [x] Mn6 — `_REFERENCE_QUERIES` extension described as name-joined, not
  id-based (§5, §21).
- [x] Mn7 — `agent_handoffs` discard-guard entry dropped with the
  unreachability rationale stated, rather than kept unjustified (§21).
- [x] Mn8 — the unnecessary new v4 fixture dropped; no repository evidence
  requires it (§24).
- [x] Mn9 — bespoke transitions sweep loop specified; label is
  `handoff_note`, not `note` (§19, §20).

**Additional structural corrections — all discharged:**

- [x] `CHECK (supersedes_id IS NULL OR supersedes_id < id)` added to both
  `routing_plans` and `agent_handoffs` (§11).
- [x] The plan/handoff supersession asymmetry (derived vs. derived-and-stored)
  is written in, with its rationale (§10).
- [x] The index decision is recorded with the three accepted scans named,
  and the one measured-optimization index named but not added (§17.1, §28).
- [x] Doctor's "single-purpose" language reworded to the check-33 shape
  (§20).
- [x] `required_scope` echoes the passport schema's "a filing statement,
  never an access grant" (§6).
- [x] The candidate pin CHECKs are biconditional (§11, correction 4).
- [x] Fresh-vs-migrated is asserted as byte-identical for the four tables,
  not merely structurally identical (§11, §22, §26).
- [x] The cross-workspace determinism test is specified to assert `(rank,
  name, version, document-digest, reasons)` + `request_sha256`, and
  explicitly **not** `content_sha256` (§8, §26).

---

*End of contract. §29 is the freeze checklist; all entries are checked.
Wave 0 stops here — no code, no tests, no migrations, no commits.*
