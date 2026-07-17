# Agentic OS v0.4 — U-A2: Governed specialist-agent catalog contract

Contract-freeze pass. Baseline `d06df1b673c43ba226fbbecdc343deef480ec0d0`
(U-A1, schema v4). Branch `v0.4-u-a2-specialist-catalog`. This document
freezes the approved design
(`agentic-os-v0.4-u-a2-specialist-catalog-design.md`) into an implementation-ready
contract. Nothing in this document is implemented by writing it; it is the
gate later steps must satisfy.

---

## 1. UNIT IDENTITY

- **Unit**: U-A2 — the governed specialist-agent catalog.
- **Baseline**: `d06df1b673c43ba226fbbecdc343deef480ec0d0` (U-A1, schema v4).
- **Schema version**: stays **4**. This unit performs no migration and adds
  no DDL.
- **Boundary**: explicit-install-only. No command other than
  `agent catalog install` may create or modify a catalog-managed row, in any
  power mode, in `init`, `migrate apply`, `doctor`, or `sync`.

## 2. PURPOSE

U-A2 ships **twelve inert `beast.agent-passport/v1` artifacts**, checked in
under `agentic_os/catalog/` and indexed by a deterministic `manifest.json`,
installable only through an explicit `agent catalog install`. Each artifact
is a **declaration**, not a capability grant: it states a role's mission,
task families, evidence expectations and limitations. This unit adds no
execution, routing, orchestration, or runtime authority of any kind.

## 3. NON-GOALS

U-A2 explicitly excludes:

- agent execution;
- routing;
- scheduling;
- workflows;
- a skills runtime;
- a tools runtime;
- providers;
- credentials;
- MCP/A2A;
- spend behavior;
- autonomous loops;
- AICompany integration.

Any implementation step that touches one of the above is out of scope for
this unit and must be rejected or deferred (§19).

## 4. SPECIALIST CATALOG

Twelve identities are frozen. Eleven are `maturity: stable`; one is
`maturity: provisional`.

| Identity | Maturity |
|---|---|
| `aos.architect` | stable |
| `aos.planner` | stable |
| `aos.builder` | stable |
| `aos.verifier` | stable |
| `aos.reviewer` | stable |
| `aos.security-auditor` | stable |
| `aos.debugger` | stable |
| `aos.release-engineer` | stable |
| `aos.researcher` | stable |
| `aos.curator` | stable |
| `aos.analyst` | **provisional** |
| `aos.technical-writer` | stable |

`maturity` is manifest index metadata (§7), not a passport field. No
thirteenth identity, no bare reserved name (`governor`, `planner`, `builder`,
`verifier`, `security-sentinel`) is minted as a row in this unit.

## 5. NAMESPACE CONTRACT

- Built-ins live exclusively in the already-reserved `aos.` prefix
  (`models.RESERVED_AGENT_PREFIXES`).
- `agent create` / `agent import` continue to refuse any `aos.*` name,
  unchanged.
- `agent catalog install` requires every entry name to start with `aos.`.
- Name comparison is **exact byte comparison**: no case folding, no Unicode
  normalization, no aliases.
- Zero new prefixes or generic occupational names are reserved by this unit.
  `RESERVED_AGENT_PREFIXES` and `RESERVED_AGENT_NAMES` are not edited.

The user-name gate and the catalog-name gate are complementary and total:
every string either starts with `aos.` (catalog-only) or does not
(user-only). No string is valid on both paths, and no string is invalid on
both.

## 6. PASSPORT CONTRACT

Every catalog entry is a `beast.agent-passport/v1` document, and every
declaration in it is **inert** — no code path reads `autonomy`,
`skill_requirements`, `tool_requirements`, or `model_requirements` to grant
capability, spend, or execution.

Uniform across all twelve:

| Field | Value |
|---|---|
| `agent_scope` | `{"level": "global"}` |
| `agent_class` | `specialist` |
| `autonomy` | `declare_only` |
| `issuer` | `aos.catalog` |
| `data_classification` | `public` |
| `provider_compat` | omitted |
| `limits` | omitted |

`skill_requirements`, `tool_requirements`, and `model_requirements` remain
inert, vendor-neutral, unversioned requirement strings — declarations with no
resolver, not references to a registry that does not exist.

Passports are **canonical authored JSON artifacts**, not embedded Python
literals: a passport is hashed internally (`content_sha256` is a field
`validate_document` checks), so a document generated at import time would
make verification circular, and hand-typing a 64-hex digest into a Python
dict is strictly worse than authoring the canonical file directly. A
built-in passport must be the same kind of object `agent export` prints and
`agent import` accepts.

## 7. MANIFEST CONTRACT

The manifest is an **index and integrity map only**. It does not duplicate
mission, capabilities, requirements, or limits — those live exclusively in
the passport bodies.

- `manifest_version`: **1**.
- `catalog_version`: **1**.
- `canonical_json`: `aos-canonical-json/v1`.
- `content_hash_alg`: `aos-sha256-canonical/v1`.
- `entries` sorted by `agent` (code point order).
- Each entry's `versions` sorted by `passport_version`, **contiguous from
  1**.
- Each version's `path` is derived and verified as exactly
  `{agent}.v{version}.passport.json`; drift between the stored and derived
  path is a validation failure.
- No dependency graph field.
- No installation-order field: manifest order **is** installation order,
  and there is nothing to encode beyond it.
- No new protocol identity is introduced under U-X1. This is a small
  dedicated deterministic format with exactly one consumer (the catalog
  loader), never exchanged, and not a message — it does not enter
  `protocols._DEFINITIONS`, `REQUIRED_IDENTITIES`, or
  `protocols/registry.json`.

## 8. OWNERSHIP AND PROVENANCE

A catalog-managed identity is identified by **all three** of the following
holding simultaneously — no single field is sufficient and name is never the
test:

1. `agents.owner = 'system'`;
2. passport `issuer = 'aos.catalog'`;
3. the installed passport's recomputed digest matches the checked-in
   manifest's `document_sha256` for that version.

Also frozen, for every catalog row:

- `protected = 1`;
- `origin = 'import'` (an import of a checked-in artifact is a truthful
  `import`, not a new fact needing a new value);
- `lifecycle = 'active'`;
- `agent_class = 'specialist'`;
- schema version remains **4**.

No `origin = 'catalog'` value is added to the `origin` CHECK constraint.
Widening that CHECK would force a table rebuild and a schema bump for a fact
already carried, more strongly, by the three-way binding above (`owner` and
`issuer` are hash-bound; digest match requires no stored state at all).

## 9. INSTALLATION CONTRACT

- Only an explicit `agent catalog install` invocation writes catalog rows.
- `agent catalog install --all` is **one transaction**: every selected entry
  installs, upgrades, no-ops, or the whole operation refuses — there is no
  partially-installed catalog state.
- Every catalog artifact is verified **before the first write** of the
  operation (manifest + all twelve documents, or the exact subset named).
- Collisions (a non-catalog identity already owns the name) and divergence
  (an installed catalog identity's history does not match the checked-in
  catalog) are detected and refuse **before** any mutation.
- Identity and history state are **re-read inside the transaction**
  immediately before each write, so a fact established during planning
  cannot be stale at write time.
- Reinstalling an already-installed set of entries at matching digests is a
  **true no-op**: it opens no transaction and writes no row.
- A true no-op emits **no event**.
- An upgrade **appends** immutable versions; no published row is ever
  updated or deleted.
- The catalog ships its **full passport history** per entry (every version
  from 1 to the current maximum), so a fresh install and an upgrade chain to
  the same catalog version converge on byte-identical documents and version
  numbers.
- A failure anywhere inside the transaction **rolls back every row this
  operation would have written** — identities, passports, and events
  together. Nothing partially lands.

## 10. USER-AGENT PRESERVATION

- User-created, imported, legacy, and project-scoped agents are never
  adopted, overwritten, renamed, protected, revoked, or deleted by any
  catalog operation.
- A pre-existing row at an `aos.*` name (reachable only via legacy
  migration or out-of-band writes) is a **collision**: it is refused by
  name and left untouched. It is never adopted into catalog ownership.
- Users derive a customized variant of a catalog role through
  `agent catalog show NAME --fragment` piped into the existing
  `agent create --from-file`. No new clone command is added.
- A derived identity is human-owned (`owner='human'`, `origin='create'`,
  `issuer='human'`) from the moment it is created and is never touched by a
  later catalog upgrade — it does not share a name, a row, or a code path
  with the catalog entry it was derived from.

## 11. PROTECTION AND LIFECYCLE

- Every catalog identity is created `protected = 1`.
- Ordinary `suspend`, `archive`, `revoke`, and `discard` all refuse against a
  protected catalog identity, unchanged from U-A1's existing protection
  refusals.
- Ordinary `agent passport publish --file` refuses when the target agent's
  `owner = 'system'`: a catalog identity's history is exclusively the
  catalog's, and grafting a user-published version onto it would produce an
  ambiguous, permanently un-upgradable half-ours/half-yours history. The
  refusal names the fragment-then-create derivation route (§10).
- Catalog upgrades remain permitted, exclusively through the catalog install
  path (`agent catalog install` detecting an `upgradable` state).
- Protection grants no execution or runtime authority; it refuses ledger
  verbs only. Nothing reads `protected` for authorization.
- Uninstall and retirement semantics for a catalog identity are explicitly
  **deferred** (§19); this unit defines no route to remove or park one.

## 12. CLI CONTRACT

Six leaves are frozen under `("agent", "catalog", *)`:

- `agent catalog list`
- `agent catalog show`
- `agent catalog verify`
- `agent catalog status`
- `agent catalog plan`
- `agent catalog install`

Every existing U-A1 command keeps its current behavior unchanged; nothing is
renamed, aliased, or retired by this unit.

## 13. POWER CONTRACT

| Leaf | Classification |
|---|---|
| `agent catalog list` | READ_ONLY |
| `agent catalog show` | READ_ONLY |
| `agent catalog verify` | READ_ONLY |
| `agent catalog status` | READ_ONLY |
| `agent catalog plan` | READ_ONLY |
| `agent catalog install` | AUTHORITATIVE_WRITE, `ledger=True` |

- **Recovery** blocks `install` in `enforce`, before dispatch: no mutation
  is reachable while the ledger is in recovery.
- **Deep** mode runs the existing preflight and post-verification around
  `install`; no new deep logic is added.
- **Eco** mode never defers an explicit `install`: an operator-requested
  installation is not a background operation eco is entitled to skip.
- **No power mode auto-installs or auto-upgrades** the catalog under any
  circumstance. The only writer is the explicit `install` leaf.

## 14. EVENTS AND PRIVACY

- Exactly two new event actions: `catalog_install` and `catalog_upgrade`.
- Both are emitted **inside** the installation transaction, one per entry
  that actually changed.
- Payloads carry only bounded metadata and hash **prefixes** (12-character,
  matching the existing `hash_prefix`/`_passport_prefix` convention) —
  never full 64-character digests.
- Payloads never carry: mission text, role text, capability text, a
  passport body or fragment, a filesystem path, a provider name, a model
  name, a skill or tool string, exception text, a credential, or any
  unbounded count.
- No event is emitted for a true no-op (§9).

## 15. DOCTOR CONTRACT

Three new checks are frozen:

| # | Name | Verdict |
|---|---|---|
| 35 | built-in catalog verified | **FAIL** |
| 36 | installed catalog identities verified | **FAIL** |
| 37 | catalog entries available to install | **WARN**, actionable states only |

Check 37 fires only on an actionable condition (an upgradable entry, or a
name collision with a non-catalog identity). **Not installing the catalog
is a healthy state** and must never itself produce a WARN or a FAIL on a
workspace that has never run `agent catalog install`.

Doctor's total check count moves from **34 to 37**.

## 16. PACKAGING CONTRACT

- Catalog artifacts live under `agentic_os/catalog/`, inside the package,
  never at the repository root.
- Runtime code reads catalog artifacts only as package resources
  (`importlib.resources`); it never reads from the current working
  directory and never fetches from a URL.
- `pyproject.toml`'s package-data declaration includes the catalog JSON so
  the console-script and wheel installs carry it.
- The zipapp builder includes exactly `agentic_os/catalog/manifest.json`
  plus the passport artifact paths that manifest's entries reference — nothing
  more. It does not use a broad `*.json` inclusion rule.
- A file under `agentic_os/catalog/` that no manifest entry references is
  **excluded** from the archive.
- A referenced artifact whose recomputed digest does not match the
  manifest's recorded `document_sha256` **fails the build** — the build
  does not silently drop it or silently include stale content.
- No ledger file, backup, export, credential, or user-generated data enters
  the archive through this mechanism.

## 17. COMPATIBILITY

- `agentic_os/db.py` and `agentic_os/migrations.py` are not edited by this
  unit: no DDL change, no new migration step.
- `agentic_os/protocols.py` and all four existing checked-in protocol
  artifacts remain byte-identical: no fifth protocol identity, no change to
  `REQUIRED_IDENTITIES` or `protocols/registry.json`.
- Schema version stays **4**.
- Every historical migration step (1→2, 2→3, 3→4) stays frozen exactly as
  it exists at baseline.
- Legacy and custom agents remain valid and untouched by any catalog
  operation.
- A fresh workspace and a migrated (legacy v3→v4) workspace both remain
  fully supported; the catalog installs identically into either.

## 18. ACCEPTANCE GATE

Completion of this unit's implementation requires, at minimum, all of the
measurable conditions the approved design report states in its own
acceptance gate: deterministic verification of every artifact and the
manifest; installation only through the explicit `install` leaf; a
byte-identical no-op on reinstall (zero rows, zero events); strictly
append-only upgrades with prior versions byte-identical afterward; complete
rollback of a mid-`--all` failure (zero identities, zero passports, zero
events survive); byte-identical preservation of every custom, imported,
draft, and legacy agent across an `install --all`; privacy-safe events whose
payload keys are a subset of the §14 allowlist; doctor reporting exactly 37
checks with no mutation; identical stdout for `list`/`verify`/`show
--document`/`doctor` across the script, module, console-script, and zipapp
entrypoints; no network call, socket, subprocess, or executed/opened path in
any catalog code; a focused test suite that passes; an accurately reported
full-suite result including any pre-existing failure, named rather than
hidden; `git diff --check` passing; and a clean working tree at completion.

## 19. DEFERRED WORK

Explicitly out of scope for this unit and left for a later one:

- execution;
- routing;
- handoff graphs;
- skills/tools resolution;
- providers;
- uninstall (or park) of a catalog identity;
- catalog entry retirement/renaming;
- signatures;
- a governor identity;
- AICompany integration.

---

*This contract is the audit surface for U-A2. An implementation step that
contradicts a numbered statement above is out of contract and must either be
rejected or brought back here for an explicit amendment before it proceeds.*
