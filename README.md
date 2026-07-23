# Agentic OS

A local-first system of record for a solo developer coordinating multiple AI
agents. It is a governance and memory ledger, **not** an agent framework and
not an orchestrator:

- **SQLite remembers.** One database (`.agentic-os/aos.db`) is the source of
  truth; every mutation also writes an append-only event row in the same
  transaction.
- **Markdown/Obsidian shows.** `.agentic-os/obsidian-vault/AOS/` is a
  generated, one-way mirror — open it as (or inside) an Obsidian vault.
- **Agents act in their own tools.** Agentic OS never spawns agents, never
  executes shell work on your behalf, and makes no network calls. You run the
  agents; it carries state in and proof out.
- **Evidence proves.** `done` refuses to close a task with zero evidence.
- **Nothing claims done without proof.**

## Requirements

Python 3.12+. Standard library only — nothing to install.

**Zero runtime dependencies.** Every entrypoint below runs on a stock Python
3.12 with nothing outside the standard library — no pip install, no virtualenv,
no third-party package at runtime.

## Running it (three equivalent entrypoints)

All three run the same CLI — same commands, flags, output, and exit codes.
There is one implementation (`agentic_os.cli:main`); each entrypoint is a
three-line shim that calls it.

```bash
# 1. From a source checkout:
python3 aos.py --help

# 2. As a module (anywhere the agentic_os package is importable):
python3 -m agentic_os --help

# 3. As a standalone archive — one file, no checkout, no PYTHONPATH:
python3 tools/build_zipapp.py          # builds dist/aos.pyz
python3 dist/aos.pyz --help
./dist/aos.pyz --help                  # executable, #!/usr/bin/env python3
```

### The standalone archive (`aos.pyz`)

`tools/build_zipapp.py` builds a single-file [zipapp](https://docs.python.org/3/library/zipapp.html)
using only the standard library. Copy `dist/aos.pyz` anywhere — another
machine, a USB stick, `~/bin` — and it runs on its own:

```bash
python3 tools/build_zipapp.py --output ~/bin/aos.pyz
cd ~/some/project && ~/bin/aos.pyz init && ~/bin/aos.pyz doctor
```

The archive carries the `agentic_os` runtime package and nothing else — no
tests, no `.git`, no ledger, no vault, no backups, no exports, no credentials.
It finds your workspace the same way every entrypoint does (`--root PATH`, or
the nearest `.agentic-os/` walking up from the current directory), so it never
needs the repository it was built from. It is a build artifact and is **not**
committed; rebuild it from source whenever you need it.

One limitation: `hooks install` / `hooks status` / `hooks uninstall` are not
supported from the archive — Claude Code hooks must point at the `aos_hooks.py`
that ships beside `aos.py` in a checkout, which is not a file inside a zipapp.
Manage hooks from a source checkout. See TROUBLESHOOTING.md.

### Installed console script

`pyproject.toml` declares an `aos` console script that delegates to the same
CLI, so an installed copy behaves identically:

```bash
aos init && aos status && aos doctor
```

Packaging metadata declares no runtime dependencies. (Installation and release
publishing are deferred — nothing here installs itself.)

## Quickstart

```bash
python aos.py init
python aos.py project add agentic-os --name "Agentic OS" --repo .
python aos.py task add "Build auth flow" -p agentic-os --kind code \
    --accept "Context pack exists and task cannot close without evidence"

# Compile a context pack and hand it to your agent (in the agent's own tool):
python aos.py pack build T-0001 --for claude-code

# Record the work:
python aos.py run start T-0001 --agent claude-code
python aos.py evidence add T-0001 --kind note --ref "CLI smoke evidence" \
    --claim "Pack and run were created"
python aos.py run end R-0001 --outcome success --summary "Smoke run completed"
python aos.py done T-0001            # succeeds only because evidence exists

# Mirror + health:
python aos.py sync                   # regenerate the Obsidian mirror (idempotent)
python aos.py status
python aos.py doctor
python aos.py log T-0001
```

Quick capture without a project: `python aos.py in "some thought"`.
Machine-readable output: `task list`, `task show`, `status`, `log`,
`memory list`, `agent list`, `agent show`, and `search` accept `--json`.

## The coordination loop

The full workflow one task travels: capture → triage → pack → agent →
write-back → review → done.

```bash
python aos.py in "idea captured mid-flight"        # T-0007, projectless inbox
python aos.py task assign T-0007 -p agentic-os     # triage: give it a project
python aos.py task edit T-0007 --title "Real title" --spec "What & why" --priority 2
python aos.py task status T-0007 ready             # inbox→ready (legal moves only)
python aos.py pack build T-0007 --for claude-code  # context pack for the agent
python aos.py run start T-0007 --agent claude-code # R-0004; task → in_progress

# The agent works in its own tool, then writes back — either via the CLI
# (evidence add / run end), or by leaving a dropfile that you ingest:
python aos.py ingest dropfile .agentic-os/exports/dropfile-T-0007-claude-code-1.md

# Attach verified commit evidence (read-only git; full sha + subject captured):
python aos.py evidence git T-0007 HEAD

python aos.py review build                          # daily review note
python aos.py done T-0007                           # closes only with evidence
python aos.py sync                                  # refresh the Obsidian mirror
```

## Task lifecycle commands

```bash
python aos.py task assign T-0002 -p agentic-os   # project onto a projectless task
                                                 # (or move a non-done task)
python aos.py task edit T-0001 [--title TEXT] [--spec TEXT] [--accept TEXT]
                               [--kind code|research|writing|ops] [--priority 1-5]
python aos.py task status T-0001 ready           # legal: inbox→ready,
                                                 # ready→in_progress, in_progress→ready
python aos.py task list [--kind code] [--missing-evidence] [--status ready] [--json]
```

`task edit` refuses done tasks — closed means frozen; append evidence or
decisions instead. `task status X done` always refuses and points at
`python aos.py done X`: the evidence gate is the only path to done.

## Dropfile ingest

Every generated pack tells its agent: if the aos CLI is unavailable, write a
dropfile (`adapters/*/PROTOCOL.md` publishes the exact format). `ingest
dropfile PATH` reads it back into the ledger:

- Strict parser — any malformed line refuses the whole file (exit 1, nothing
  ingested) naming the first bad line by number.
- Dropfile content is untrusted data: nothing in it is executed, no path it
  names is opened, values are one-line-collapsed, and the same secret scanner
  that guards packs refuses secret-shaped content without echoing it.
- Evidence rows land with provenance `agent:<name>`; open questions become a
  handoff to `generic`.
- Runs ladder: exactly one open run for that task+agent is ended with the
  dropfile outcome; zero or several open runs ingest evidence only and say so.
- Dedupe by file sha256 (recorded in the ingest event): re-ingesting the same
  bytes is refused. The dropfile itself is never modified or deleted.
- **Success needs proof (U-H2).** A dropfile declaring `outcome: success`
  must carry at least one evidence row with a non-blank ref in that same
  file, or the whole ingest refuses atomically (exit 1, nothing written,
  no dedupe marker — a corrected retry is never "duplicate"). Evidence
  presence is enforced, never truth: no ref target is opened or verified.
  `partial`, `fail`, and `unknown` remain valid with no evidence — the
  recovery for an over-claiming agent is an honest outcome, not fabricated
  proof. Blank evidence refs and blank claims refuse as malformed lines
  (Unicode whitespace counts as blank), at the parser and at
  `evidence add` alike. `run end --outcome success` stays accepted without
  an evidence check — it is the human recovery path — and `doctor` warns
  (never fails) about ended success runs that no non-blank evidence can be
  attributed to between that run's start and the next run's start.

## Claude Code session hooks (U-H1)

Optional bridge: a Claude Code session can hand its write-back to the
dropfile path without running the CLI. Two AOS-owned command hooks do it in
two deterministic stages:

- **Stop (capture):** when Claude's final response ends with exactly one
  fenced ```` ```aos-dropfile ```` block — whose content is exactly the
  dropfile format above — the hook validates it with the same parser, size
  caps, and secret scanner as `ingest dropfile` and stages it under
  `.agentic-os/exports/hook-staging/`, bound to the session id and a sha256
  digest. At most one staged record per session; a later envelope replaces
  it, and a later envelope attempt that is refused (malformed, multiple,
  unterminated, oversized, secret-shaped) invalidates it — a superseded
  write-back is never published. No envelope at all, or a session outside
  an AOS workspace, is a silent no-op. The hook never blocks Claude from
  stopping.
- **SessionEnd (publish):** the hook re-validates its own session's staged
  record and publishes at most one dropfile at a deterministic,
  collision-safe name (`dropfile-<task>-<agent>-hook-<session8>-<sha12>.md`;
  a task/agent component longer than 40 chars is replaced by a bounded
  digest-tagged form so the name stays far below filesystem limits)
  under `.agentic-os/exports/`. Publication is atomic and idempotent — a
  retried SessionEnd never creates a duplicate. Refusals (tampered staging,
  secret-shaped content, name collisions) leave no partial file and retain
  the staged record for inspection.

**Ingest stays manual.** The hooks never run `aos`, never open the ledger,
never read transcripts or workspace files, never call git or the network —
they only write the two owned exports paths. The hooks are transport-only:
a structurally valid success envelope with an empty evidence section still
publishes, and the U-H2 success gate then refuses it at ingest — the
boundary where the ledger is actually written. You review and ingest:

```bash
python aos.py ingest dropfile .agentic-os/exports/dropfile-T-XXXX-claude-code-hook-*.md
```

Install is previewable and reversible (dry-run is the default; apply asks
for confirmation and backs up your settings file first):

```bash
python aos.py hooks install              # dry-run: exact settings diff, no writes
python aos.py hooks install --apply      # confirm with 'yes'; backup written first
python aos.py hooks status               # absent | installed (version, digest) | drifted
python aos.py hooks uninstall            # dry-run preview of the removal
python aos.py hooks uninstall --apply    # removes only the AOS-owned entries
```

The target is the documented Claude Code user settings file
(`~/.claude/settings.json`; override with `--settings PATH`). Only the exact
AOS-owned `Stop`/`SessionEnd` entries are added, healed, or removed —
unrelated settings and hooks are preserved. Restore any apply with the
printed backup: `cp <backup> <settings>`. Compatibility is capability-based:
the hooks need a Claude Code that provides Stop/SessionEnd command hooks
with JSON on stdin and `last_assistant_message` in the Stop input.

## Governed agent registry (U-A1)

Records and declarations only — Agentic OS never executes, routes, schedules
or authorizes agents. An agent is a governed IDENTITY row plus an immutable
history of **passports**: versioned `beast.agent-passport/v1` declarations
(role, mission, capabilities, requirements, limits) stored as canonical
protocol artifacts and bound by the same record-hash discipline as memory.

```bash
# Create a DRAFT identity with a draft v1 passport, then publish it:
python aos.py agent create codex --class specialist \
    --role "coding agent" --mission "ship the work"
python aos.py agent passport publish codex          # draft → active, v1 frozen

# Inspect, export, evolve:
python aos.py agent list --json
python aos.py agent show codex --json
python aos.py agent export codex > codex.json       # stored canonical bytes
python aos.py agent passport publish codex --file codex-v2.json   # version 2
python aos.py agent passport history codex

# Exchange between workspaces (the file is inert — nothing it names is
# opened, fetched, resolved or executed):
python aos.py agent import codex.json

# Lifecycle (published passports are immutable; `revoke` is terminal):
python aos.py agent suspend codex && python aos.py agent restore codex
python aos.py agent archive codex
python aos.py agent revoke codex
python aos.py agent discard scratch   # never-published, never-referenced drafts only
```

Everything a passport declares is inert stored text: `autonomy`, skill/tool
requirements and provider compatibility grant nothing and are consumed by no
code path in this unit. Credential-shaped fields are structurally
unrepresentable in the schema. Every authoritative agent write first verifies
the identity hash and the whole passport history — a tampered record cannot
receive a new version on top (doctor checks 32–33 report it; recovery mode
is the exit).

The ungoverned v3 verbs (`agent add`, `agent update`) are retired. Migrated
v3 agents survive with `origin=legacy` and their old fields (`kind`, `notes`,
`capabilities`, `trust_level`, `invoke_hint`) carried verbatim as permanently
inert history — no passport is fabricated for them; publish one when you are
ready to govern them. Registered agents get generated `AOS/Agents/<name>.md`
notes on sync. There is deliberately no `--trust-level` flag anywhere:
autonomy is earned through the ladder, never set by hand.

## Specialist agent catalog (U-A2)

Twelve built-in specialist identities ship inside the package under
`agentic_os/catalog/`, indexed by a checked-in `manifest.json`:

| Agent | Category | Maturity |
|---|---|---|
| `aos.architect` | design | stable |
| `aos.planner` | design | stable |
| `aos.builder` | delivery | stable |
| `aos.verifier` | assurance | stable |
| `aos.reviewer` | assurance | stable |
| `aos.security-auditor` | assurance | stable |
| `aos.debugger` | operations | stable |
| `aos.release-engineer` | operations | stable |
| `aos.researcher` | knowledge | stable |
| `aos.curator` | knowledge | stable |
| `aos.analyst` | knowledge | provisional |
| `aos.technical-writer` | knowledge | stable |

Each is a `beast.agent-passport/v1` **declaration** — a mission, task
families, evidence expectations and limitations — not a capability grant.
Like every U-A1 passport field, `autonomy`, `skill_requirements`,
`tool_requirements` and `model_requirements` are inert stored text: no code
path in this unit reads them to grant capability, spend, or execution. U-A2
adds no routing, execution, scheduling, provider, or credential behavior of
any kind, and the schema stays version 4 — this unit performs no migration.

```bash
# Inspect the catalog (no ledger required for list/show/verify):
python aos.py agent catalog list
python aos.py agent catalog show aos.architect              # rendered
python aos.py agent catalog show aos.architect --document    # exact canonical bytes
python aos.py agent catalog verify                            # catalog integrity, exit 1 on any problem

# Ledger-aware, still read-only:
python aos.py agent catalog status                            # per-entry install state
python aos.py agent catalog plan --all                        # what `install --all` would do

# The only writer in this unit — explicit, one leaf, one transaction:
python aos.py agent catalog install aos.architect
python aos.py agent catalog install --all
```

Installation is **explicit only**: no command other than `agent catalog
install` ever creates or modifies a catalog-managed row, in any power mode,
in `init`, `migrate apply`, `doctor`, or `sync`. A workspace that has never
run `agent catalog install` is a healthy workspace — `doctor` never warns or
fails merely because the catalog is uninstalled.

Reinstalling an already-installed set of entries at matching digests is a
**true no-op**: no transaction opens, no row is written, and no event is
emitted. `agent catalog install --all` a second time in a row prints
"Nothing to do" and leaves every table byte-identical to before.

Every catalog identity is `owner=system` and `protected=1`, so ordinary
`suspend`/`archive`/`revoke`/`discard` refuse it exactly as they refuse any
other protected identity. To build your own variant, derive it — no clone
command exists because none is needed:

```bash
python aos.py agent catalog show aos.architect --fragment > body.json
python aos.py agent create my-architect --class specialist --from-file body.json
```

The derived identity is `owner=human`, `origin=create`, from the moment it
is created, and is never touched by a later catalog upgrade — it shares no
row, name, or code path with the catalog entry it was derived from.

## Governed agent routing and handoffs (U-A3)

Records and declarations only — U-A3 adds the smallest governed substrate that
can *declare* routing and delegation without *performing* either. It routes
nothing, selects nothing, launches nothing, and grants nothing: a routing plan
is an advisory record a human reads, and a governed handoff is a human-authored
declaration a human decides on. The schema moves to version 5 — four additive
tables, no new protocol, and no change to any existing table.

### Advisory routing plans

`agent route plan` evaluates the installed agent identities against a described
task and stores a deterministic, fully explainable **routing plan**:

- a routing plan is an immutable-after-commit advisory record. Routing does not
  select, launch, invoke, or execute an agent, and no code path reads a plan to
  authorize anything;
- each plan captures the evaluated candidates, the closed eligibility reason
  code for every excluded or unresolved one, the deterministic ordering, the
  pinned passport version / document digest / identity digest of each eligible
  candidate, the record's integrity hashes, and a derived staleness state;
- eligibility and ordering are pure functions of the request and the current
  ledger — never of row ids, insertion order, wall clock, usage, price, or
  randomness;
- committed plan and candidate rows are never updated or deleted. `--supersedes
  RP-0001` records a successor at creation and leaves the old plan
  byte-identical;
- routing derives the project from the referenced task when `--project` is
  omitted (task-derived project routing);
- staleness is a read-time predicate, not a stored flag. A stale or superseded
  plan stays inspectable history, but it must not be used to create a governed
  handoff.

### Governed handoffs

`agent handoff create` declares a **governed handoff** — an explicit
human-authored delegation between two pinned participant identities:

- a governed handoff is a declaration, not an action. `accepted` means the
  human recorded acceptance for the recipient identity — never that work ran or
  completed;
- every handoff pins both participants' passport version and recomputed
  document digest at creation, and keeps an append-only transition history plus
  a hash-coupled current-state projection that integrity verification replays;
- the lifecycle verbs are `accept`, `refuse`, `clarify`, and `cancel`. A
  successor is created with `--supersedes AH-0001`, which is the only way a
  handoff reaches the `superseded` state — there is no standalone supersede
  command;
- there is no `completed` state. Completion asserts that work was executed and
  verified, and U-A3 binds no runs or evidence that could claim it honestly;
- `--decision D-0001` is an optional pointer to a decision record explaining
  *why* a delegation was declared — descriptive only, never an approval,
  authorization, or grant.

### Schema, doctor, and recovery

Schema **version 5** adds four governed tables — `routing_plans`,
`routing_plan_candidates`, `agent_handoffs`, and `agent_handoff_transitions` —
and no new protocol. Doctor gains four read-only checks (total **41 checks**):

- **routing plans verify** — plan and candidate hashes, chain, request digest,
  counts, ranks, pins, and references;
- **agent handoffs verify** — handoff hash, transition chain replay, state
  coherence, pins, and references;
- **open agent handoffs with ineligible participants** — a WARN when an open
  handoff names a suspended, archived, revoked, or integrity-broken participant;
- **open agent handoffs pinned to stale plans** — a WARN when an open handoff
  references a stale or superseded plan.

In **recovery mode** the six U-A3 write leaves (`route plan`, `handoff create`,
`accept`, `refuse`, `clarify`, `cancel`) are blocked before dispatch, while the
five read leaves (`route list` / `show` / `verify`, `handoff list` / `show`)
stay available so a damaged, stale, or superseded record can still be
inspected. Reads never repair or mutate anything.

### The eleven commands

```bash
# Routing — one authoritative write, three reads:
python aos.py agent route plan [--task T-…] [--project SLUG] [--family F]… \
    [--capability C]… [--evidence-kind K]… [--require-classification LVL] \
    [--require-autonomy LVL]… [--require-scope global|project] [--require-class CLASS] \
    [--skill S]… [--tool T]… [--min-context-tokens N] [--modality M]… [--prefer NAME] \
    [--scope-preference specific_first|none] [--surplus-policy minimal|ignore] \
    [--max-candidates N] [--supersedes RP-…] [--json]
python aos.py agent route list [--task T-…] [--json]
python aos.py agent route show RP-0001 [--request] [--json]
python aos.py agent route verify RP-0001 [--json]

# Handoffs — five authoritative writes, two reads:
python aos.py agent handoff create --task T-0001 --from NAME --to NAME \
    --objective TEXT [--plan RP-0001] [--expect-evidence KIND]… [--min-evidence N] \
    [--constraints TEXT] [--classification LVL] [--decision D-0001] \
    [--supersedes AH-0001] [--json]
python aos.py agent handoff list [--task T-0001] [--state STATE] [--json]
python aos.py agent handoff show AH-0001 [--json]
python aos.py agent handoff accept AH-0001 [--note TEXT] [--json]
python aos.py agent handoff refuse AH-0001 --reason CODE [--note TEXT]
python aos.py agent handoff clarify AH-0001 --reason CODE [--note TEXT]
python aos.py agent handoff cancel AH-0001 [--note TEXT]
```

### A small governed flow

```bash
# 1. Evaluate installed agents for a task and store the ranked advisory plan (RP-0001):
python aos.py agent route plan --task T-0001

# 2. Read and verify the plan — both are read-only, and neither selects nor
#    launches anyone:
python aos.py agent route show RP-0001
python aos.py agent route verify RP-0001

# 3. You, the human, read the ranked candidates and decide who receives the
#    work. Nothing was chosen or launched for you.

# 4. Declare a governed handoff to the recipient you chose, optionally citing
#    the plan as an advisory reference (AH-0001):
python aos.py agent handoff create --task T-0001 --from aos.planner --to aos.builder \
    --objective "Implement the parser fix" --plan RP-0001

# 5. Inspect the declaration and its (initially empty) transition history:
python aos.py agent handoff show AH-0001

# 6. Record one human decision. `accepted` means the declaration was accepted —
#    it executes nothing and completes nothing:
python aos.py agent handoff accept AH-0001
```

### Not added by U-A3

U-A3 is advisory and carries no authority. It adds none of the following, and
none may be inferred from a plan or a handoff:

- `agent route select` — explicit human selection *is* handoff creation, not a
  second record;
- `agent handoff complete`, any `completed` state, or completion-evidence
  binding;
- autonomous delegation, agent execution, or provider access;
- tool, skill, or MCP invocation;
- credential grants or spend;
- workflow scheduling or an orchestration engine;
- economic negotiation;
- AICompany integration.

`decision_id` is a rationale pointer, not an approval — Agentic OS currently
has no governed approval primitive for these handoffs. The full frozen contract
is `agentic-os-v0.4-u-a3-routing-handoffs-contract.md`.

## Weekend commands

Decisions, handoffs, and memory are first-class ledger rows (each mutation
writes its event in the same transaction); search, review, export, and
snapshot are derived views of them.

```bash
# Record an accepted decision (D-0001), optionally pinned to a task:
python aos.py decision add "Use SQLite" -p agentic-os --task T-0001 \
    --decision "SQLite is the source of truth" --alternatives "Markdown as database"

# Hand a task from one agent to another (H-0001), then accept the handoff:
python aos.py handoff create T-0001 --from claude-code --to codex \
    --state "Done: pack built. Remaining: verify evidence flow."
python aos.py handoff accept H-0001

# Scoped memory claims (M-0001): add, list, show, retire, supersede:
python aos.py memory add --scope project --project agentic-os \
    --kind constraint --key storage --value "SQLite is source of truth" \
    --source human --confidence confirmed
python aos.py memory list --json
python aos.py memory show M-0001
python aos.py memory add --scope project --project agentic-os \
    --kind constraint --key storage --value "SQLite, WAL mode" \
    --source human --confidence confirmed --supersedes M-0001
python aos.py memory retire M-0002

# Curation (U-M2): pin what should lead the pack, cite the evidence for it:
python aos.py memory pin M-0003
python aos.py memory link-evidence M-0003 E-0001
python aos.py memory add --scope project --project agentic-os \
    --kind fact --key runtime --value "python 3.13" --source human \
    --confidence confirmed --pin --evidence E-0001 --evidence E-0002
python aos.py memory list --status live --pinned
python aos.py memory unpin M-0003

# Search tasks, decisions, evidence, handoffs, and memory:
python aos.py search "SQLite" --json

# Build (or refresh) review notes — everything you write from the
# "## Notes" line down survives every rebuild byte-for-byte. Reviews cover
# open/attention tasks, recent evidence and runs, open handoffs, stale
# in-progress tasks, code tasks closed without commit evidence, and memory
# needing refresh:
python aos.py review build                     # daily  → Reviews/YYYY-MM-DD.md
python aos.py review weekly [--date 2026-07-07]  # ISO week → Reviews/YYYY-Www.md
python aos.py review project agentic-os        # one project → Reviews/project-<slug>.md

# Backups: JSONL event export + a WAL-safe database snapshot:
python aos.py export events --jsonl
python aos.py snapshot

# Verifiable backups (manifest: sha256, schema_version, size) — the full
# create/verify/restore drill lives in RECOVERY.md. Restore writes to a NEW
# path only and never overwrites:
python aos.py backup create
python aos.py backup verify .agentic-os/backups/aos-backup-<stamp>.db
python aos.py backup restore .agentic-os/backups/aos-backup-<stamp>.db \
    --to /somewhere/new/aos.db
```

## Memory claims and curation (U-M2)

A memory row is a **claim**: a `key` (what it is about), a `value_md` (what
it says), and — since schema v2 — the curation state that decides whether an
agent ever sees it.

**Status.** Every claim carries exactly one:

| status | meaning | in context packs? |
|---|---|---|
| `live` | curated, current | **yes** |
| `proposed` | suggested, not accepted | no |
| `contested` | disputed | no |
| `quarantined` | withheld | no |
| `retired` | superseded or no longer valid | no |

`memory add` creates a **live, unpinned** claim, exactly as it always did.
U-M2 stores the other four statuses for the U-M4 curation workflow but ships
no command that produces them — there is no approve, reject, contest or
quarantine yet, and no automatic promotion.

**Normal retrieval means live only.** A claim reaches a context pack only if
it is `live` **and** unexpired **and** unsuperseded. Everything else stays in
the ledger and in `memory list` forever — it just stops being fed to agents.

**Pinning is ordering, never permission.** `memory pin` makes a claim lead
the pack MEMORY section; that is all it does. A pinned claim must still be
live, unexpired and unsuperseded to be retrieved — pin a claim and then
retire it and it disappears from packs exactly like any other retired claim
(doctor will tell you it is pinned but unreachable). Order is: pinned claims
first, unpinned second, and inside each group the same stable scope/key/id
order as always.

**Evidence links.** `memory link-evidence M-0001 E-0001` records that a claim
is backed by an evidence row. The link is a normalized pair of ids — no copy
of the evidence's text lives in it, and `memory show` prints the ids, never
the evidence body or the file it points at. A claim and its evidence may not
name two different projects; a global claim citing project evidence is fine.

**Every claim carries a hash.** `content_sha256` binds every authoritative
field — scope, project, kind, key, value, source, confidence, validity,
supersession, status, pin state and the sorted evidence links. Any
authoritative write recomputes it in the same transaction. Change a claim
behind Agentic OS's back and `doctor` says so, and every write against that
claim refuses rather than quietly re-blessing the edit.

```bash
python aos.py memory show M-0001            # status, pin, hash, evidence ids
python aos.py memory show M-0001 --json
python aos.py memory list --status retired  # administrative: history included
python aos.py memory list --pinned
```

## The memory graph (U-M3)

Schema v3 adds four things to a claim: how sensitive it is, where it came
from, what it relates to, and what it contradicts. All four are recorded by
you and interpreted by nobody.

### Sensitivity

Every claim carries exactly one level, and they are ordered:

| level | in packs, search snippets and mirror bodies? |
|---|---|
| `public` | yes |
| `internal` | yes — **the default** |
| `confidential` | yes |
| `restricted` | **never** |

`memory add` defaults to `internal`; pass `--sensitivity` to say otherwise.
Public, internal and confidential claims behave exactly as they did before.

**`restricted` means restricted from automatic context, not hidden from you.**
A restricted claim never enters a context pack, a search snippet, a generated
summary or a mirror body. It still appears in `memory list`, `memory show`,
`memory graph` and `doctor` — as **metadata only**: its id, scope, kind,
status, sensitivity, timestamps, counts and hash are shown; its key, value,
source and evidence refs are not.

```bash
python aos.py memory add --scope global --kind fact --key salary-band \
    --value "..." --source human --confidence confirmed --sensitivity restricted

# Raise a claim's classification. Increases ONLY.
python aos.py memory classify M-0007 confidential
python aos.py memory classify M-0007 public   # refuses: see U-S6
```

Classification only ever goes **up** (`public → internal → confidential →
restricted`). Re-classifying to the level a claim already has changes nothing
and writes no event. Lowering one is an authorization decision and belongs to
U-S6, which this build does not ship — so it refuses, unchanged.

Pinning does not override any of this. A pin is ordering among claims that are
already eligible; it never forces a restricted claim into context.

### Sources: where a claim came from

A **source** is a normalized provenance record. It names where something came
from without copying it:

| kind | carries |
|---|---|
| `evidence` | an evidence id (`--evidence E-0001`), and nothing else about that row |
| `file` `url` `command` `human` `agent` `artifact` | an inert `--locator` string |

```bash
# An evidence-backed source, and an inert external one:
python aos.py memory source add --kind evidence --evidence E-0001
python aos.py memory source add --kind url --locator "https://example.com/rfc" \
    --observed-at 2026-07-16 --valid-until 2027-01-01

python aos.py memory source list --active-only
python aos.py memory source show MS-0001

# Attach a source to a claim: supports | disputes | context | derived_from
python aos.py memory source link M-0001 MS-0001 --relation supports
```

> **References are inert. Nothing follows them.** A locator is a string the
> ledger agreed to remember. No command opens that file, resolves that URL,
> runs that command string, reads that evidence row's text, or touches the
> network — not `source show`, not `graph`, not `doctor`, not `pack build`.
>
> `source list` and `source show` deliberately **never print the locator or
> the provenance**. A URL with a token in its query string, or a path through
> your home directory, does not belong in a listing you scroll past. The id is
> enough to correlate; the ledger holds the rest.

Two rules are enforced before any link is written: a **project** source may
back only claims in the same project (a **global** source may back anything),
and a source may **not be more sensitive than the claim it backs** — otherwise
the link would be a way to reach a restricted source through a public claim.

### Relationships and contradictions

An **edge** records that two claims relate:

| relation | direction |
|---|---|
| `supports` `refines` `depends_on` | directional — the order you give is kept |
| `contradicts` `related` | **symmetric** — A↔B and B↔A are one edge |

```bash
python aos.py memory edge add M-0001 M-0002 --relation refines
python aos.py memory edge add M-0003 M-0004 --relation contradicts \
    --valid-from 2026-07-16

python aos.py memory edge list --relation contradicts --active-only
python aos.py memory graph M-0001              # depth 1 (default)
python aos.py memory graph M-0001 --depth 2 --json
python aos.py memory contradictions            # active ones; --all for history
```

Because `contradicts` and `related` are symmetric, their endpoints are stored
lowest-id-first, so adding `B contradicts A` after `A contradicts B` is an
idempotent no-op rather than a second row for the same fact.

> **A contradiction is a record, not a verdict.** `memory contradictions`
> tells you that you declared two claims to disagree, and shows you both
> claims' status and sensitivity — usually enough to see that one is already
> retired. It does **not** decide which is true, resolve anything, or change a
> claim. **Nothing is ever inferred**: no contradiction is detected from keys,
> values, dates, sources or models. Every edge in the graph was typed by a
> human.
>
> More generally: **graph records do not automate truth decisions.** An edge
> triggers no workflow. Adding `contradicts` does not quarantine, retire,
> contest or reorder anything, and `superseded_by` remains the one mechanism
> that retires a claim.

`memory graph` is a bounded, read-only, deterministic view: depth 1 or 2 only,
at most 64 nodes and 128 edges. It prints ids, relations, direction, status,
sensitivity and active state — never a claim's key or value, never a locator,
never a full hash. If it hits a cap it truncates and says so, rather than
pretending you saw the whole neighbourhood.

Packs do **no graph expansion**: linking a source or an edge to a claim never
pulls its neighbours into an agent's context.

### Temporal validity

Sources and edges may carry `--valid-from` / `--valid-until` (`YYYY-MM-DD` or
`YYYY-MM-DDTHH:MM:SSZ`). An expired source or edge is **inactive, not gone**:
it stays queryable history, drops out of `--active-only` listings and out of
`memory contradictions` by default, and an expired source stops counting as
active support. Nothing is ever deleted.

### Integrity

Sources, links and edges each carry a `content_sha256` binding every
authoritative field, exactly as claims do — and the claim hash now binds
`sensitivity` too, so tampering with the field that decides whether an agent
sees a claim breaks its hash like any other. Every write against an existing
record verifies its stored hash first and refuses on mismatch, so no
mutation can quietly certify an edit made behind Agentic OS's back. `doctor`
reports damage by id and reason code, never by echoing what it found.

## Schema migrations (U-M1)

**Schema version 4 is current.** A workspace created by this build starts at
4 and never migrates. An older workspace has up to three migrations pending —
`u-m2-memory-claims-v2` (memory claims), `u-m3-memory-graph-v3` (the memory
graph) and `u-a1-agent-passports-v4` (the governed agent registry) — the
production migrations the U-M1 machinery carries.

```bash
# Where am I, what does this build support, is anything pending?
python aos.py migrate status

# What exactly would run, in order? (read-only; writes nothing)
python aos.py migrate plan
#   3 → 4  u-a1-agent-passports-v4

# Run it. Snapshots and verifies the database first.
python aos.py migrate apply
```

The 1 → 2 migration preserves every memory row exactly — same id, same text,
same timestamps — and derives curation from what v1 already knew: a
superseded or expired row becomes `retired`, every other row becomes `live`,
every row starts unpinned, no evidence link is invented, and every row gets a
valid hash. Nothing is inferred from your text.

The 2 → 3 migration does the same on the same terms: every claim keeps its id,
text, timestamps, status and pin; every evidence link survives untouched;
every claim becomes `internal`; every hash is recomputed under the v3 payload.
The three graph tables arrive **empty** — a v2 claim has no recorded
provenance, and inventing one from its `source` field or its evidence would be
a guess wearing a fact's clothes. Nothing is inferred from your text here
either.

The 3 → 4 migration rebuilds `agents` as the governed identity table. Every
v3 row survives with the same id and name and its old fields (`kind`,
`invoke_hint`, `capabilities_json`, `trust_level`, `notes`) carried verbatim
as permanently inert history; the new facts are constants (`origin=legacy`,
`lifecycle=active`, class `custom`, global scope) plus one clock reading.
`agent_passports` arrives **empty** — no passport is synthesized from
`capabilities_json` or `trust_level`, because interpreting untrusted legacy
text as a governed declaration would be the same guess in different clothes.
Legacy `trust_level` never gains behavior.

`status` and `plan` are read-only *byte-for-byte*: they open the database
through a connection SQLite itself refuses writes on, and leave no `-wal`,
`-shm`, or temporary file behind. With nothing pending, `apply` is a
successful no-op that never opens the database read-write at all — no
backup, no event, not one byte changed.

**Nothing auto-migrates.** No normal command will ever quietly change your
schema. A database at an unsupported version is refused by every command —
`memory list` on a v1 database tells you to run `migrate status` / `plan` /
`apply` and changes nothing. `migrate apply` is the only door, and you open
it deliberately. That refusal is a feature — an unexpected version means
something is wrong, and guessing is how data dies.

**Backup first, always.** Before the first schema change of a real
migration, `apply` acquires the SQLite write lock, re-confirms the version
*under that lock*, takes a snapshot through the same U-C2 backup machinery
`backup create` uses, and verifies it (sha256 + `integrity_check`). Only
then does the first step run. If the snapshot cannot be written or cannot be
verified, nothing is migrated. The lock is held from the snapshot through
the first step's commit, so the snapshot is provably the pre-migration state
— no other writer can slip in between.

**Every step is one transaction** carrying three things together: the schema
change, the exact version bump, and one `system/migrate` event naming the
transition, the migration id, and the snapshot. They commit together or they
all disappear. A failed step rolls back completely and no later step runs.

**Rollback is restore.** There is no automatic un-migration across committed
steps — a step that committed is a fact, and reversing schema changes
programmatically is how backups get quietly bypassed. If a later step fails
after an earlier one committed, `apply` says so plainly ("PARTIALLY
ADVANCED"), tells you the version you are actually at, and prints the exact
`backup restore` command for the pre-migration snapshot. Fixing the
migration and re-running resumes from the version actually committed —
completed steps never replay. See RECOVERY.md.

**Never hand-edit `schema_version`.** It is not a dial that makes a database
compatible; it is a claim about what the bytes on disk look like. Editing it
makes the ledger lie to every check that protects it. If `migrate status`
refuses, read TROUBLESHOOTING.md.

## Runtime power modes (U-E2)

Power modes govern **local CLI execution policy** for one workspace. They never
choose an LLM, call a model, start a daemon, run anything in the background, or
grant autonomy — "power" here means how careful the CLI is, not how much
compute anything gets.

```bash
python aos.py power status      # current mode + the degradation matrix
python aos.py power suggest     # deterministic advice; changes nothing
python aos.py power set eco
python aos.py power set standard
python aos.py power set deep
python aos.py power set recovery
```

### The four modes

| mode | what it does |
|---|---|
| `eco` | Everything you ask for still runs — authoritative writes, explicit `sync`/`review`/`backup`. Only *implicit, optional* derived refresh is deferred. In this build that is exactly one thing: `init` re-healing the Obsidian mirror on an already-initialized workspace. It says so, and `sync` regenerates it. |
| `standard` | **The default.** Baseline behavior, byte for byte. No preflight, no automatic doctor after commands. |
| `deep` | Before each authoritative ledger write, a bounded read-only preflight runs `PRAGMA integrity_check` and the U-C3 secret sweep, and refuses the write if either fails. After a successful write the same checks re-run; if they fail, the command tells you it **already committed** and points you at `recovery`. It never rolls anything back. |
| `recovery` | Fail-closed. Read-only and recovery-safe commands work; every authoritative and derived mutation is refused **before it runs**, so nothing is half-written. |

### Default and state

A workspace with no `.agentic-os/power.json` is in `standard`. That is a real,
expected state — `power status`, `power suggest`, and `doctor` all report it
and **never create the file**. Only `power set` writes it, and the whole file
is one line:

```json
{"version":1,"mode":"standard"}
```

It lives beside the ledger rather than inside it on purpose: `power set
recovery` has to work when the database is corrupt or its `schema_version` is
unsupported — which is exactly when you need it (D-v0.2.51). The mode is
per-workspace: two workspaces on one machine have independent modes.

### Suggestions are advice, never action

`power suggest` never switches anything. It applies a fixed priority — no
model call, no heuristics over your text, no CPU/RAM probing (D-v0.2.57):

1. any hard doctor failure → `recovery`
2. else any doctor warning → `deep`
3. else any active (unended) run → `standard`
4. else clean and idle → `eco`

It prints the signal category and a count — never a title, ref, claim, path, or
secret. Applying it is your call:

```
suggestion: deep
signal:     doctor warning (1)
Advice only — nothing was changed. Only you change the mode: python aos.py power set deep
```

### Entering and leaving recovery

`power set recovery` always works while the workspace and the state file are
safely inspectable — including while `doctor` is failing, and including when
the database will not open at all. **Leaving** recovery (to `eco`, `standard`,
or `deep`) requires every hard doctor check to pass; warn-only checks never
block a transition. `doctor` reports the mode as its own check:

```
[PASS] runtime power state — standard (default)
[PASS] runtime power state — recovery (configured; authoritative writes blocked)
[FAIL] runtime power state — malformed or unsafe configuration
```

Nothing here switches modes on its own, in any mode. See TROUBLESHOOTING.md for
a malformed `power.json`, and for what to do when deep verification fails after
a command already committed.

## Protocol spine (U-X1)

The protocol spine is the versioned, local vocabulary that Agentic OS and a
future agent runtime will use to talk about work: what was *asked for*, what
*came back*, and where a human needs to be *interrupted*. It is a wire format
and nothing else — a spine to hang later integration on, built and pinned
before there is anything on the other end of the wire.

```bash
# What schemas does this build know about, and at what digest?
python aos.py protocol list

# The exact schema, canonically serialized (identical bytes from any entrypoint):
python aos.py protocol show beast.work-spec/v1

# Validate an artifact: syntax, bounds, identity, content hash, cross-field rules.
# On success it prints only the schema and the digest it verified.
python aos.py protocol validate ./work-spec.json
#> beast.work-spec/v1 357b140bfca6029f5b3311ac3764962a2f3ddd259cedd164362a951aac6d2984

# What does this document's body hash to? (Reads only; never rewrites the file.)
python aos.py protocol digest ./work-spec.json

# Are the embedded definitions and the checked-in protocols/ still in agreement?
python aos.py protocol verify-registry
```

### The artifacts are inert

Four schemas, all of them declarations rather than actions:

| Schema | What it is |
|---|---|
| `beast.work-spec/v1` | An inert declaration of requested work: goal, acceptance criteria, constraints, declared input references, the expected result contract. |
| `beast.result-envelope/v1` | An inert, proof-carrying report bound to the exact WorkSpec content hash: honest outcome, evidence references, bounded errors, retryability. |
| `beast.interrupt/v1` | An inert request to pause, ask, seek approval, cancel, or resume — bound to an exact artifact hash. |
| `beast.agent-passport/v1` | An inert, versioned declaration of an agent's identity, mission and requirements (U-A1). A reduced envelope — a passport is not a task message — and no field that can carry a credential, an endpoint, or an approval. |

**Validation does not execute or import anything, and it does not import
results into the ledger.** That is the whole boundary, and it is worth stating
plainly:

- A WorkSpec cannot carry executable Python or shell, a connection string, a
  credential, or an environment map. These are not discouraged — every object
  in every schema is closed, so they are *unrepresentable*.
- A WorkSpec has no `approved: true`. It can carry an opaque `approval_ref`
  pointing at an approval record owned by some other system, which is a
  reference, not a claim. No artifact in this protocol can authorize itself.
- A Result Envelope does not mark a task done, end a run, create evidence,
  authorize spend, or mutate SQLite. Something reporting `outcome: success` is
  a claim by a party you have not yet decided to trust. Importing and replaying
  envelopes into the ledger is deliberately a later unit.
- An `input` reference, a `url`, or a declared `sha256` is never opened,
  fetched, stat'd or hashed. Hashing a path that an untrusted artifact chose
  would be a read primitive handed to whoever wrote the artifact.
- `protocol validate` on a hostile file is safe in the way `cat` is safe. It
  reads bytes and compares them to a schema.

### Canonical hashing

Every artifact carries `content_sha256` over its own body. The rule is exact:
serialize the document in **`aos-canonical-json/v1`** (UTF-8, no BOM, no
insignificant whitespace, keys sorted by code point, no floats, no duplicate
keys, bounded everywhere) with **only the top-level `content_sha256` member
removed**, then take lowercase SHA-256. Nothing else is excluded, and the body
being hashed never contains the hash.

That makes the digest independent of how the file is laid out — a
pretty-printed and a compact copy of the same artifact hash identically — and
makes tampering with the payload, the metadata, the schema identity, or the
hash itself all fail the same check. `aos-canonical-json/v1` is a local format;
it is deliberately **not** claimed to be RFC 8785, and the four divergences are
listed in the contract.

Bounds are pinned, not tuned: 256 KiB per artifact, depth 32, 256 object
members, 256 array items, 8192-character strings, and integers restricted to
the ±(2⁵³−1) range that survives a consumer whose JSON parser has no integer
type.

### Where the definitions live

The embedded Python definitions in `agentic_os/protocols.py` are canonical, so
`aos.pyz` carries the whole registry in one file with no data directory. The
checked-in JSON under `protocols/` is a deterministic projection of them, kept
for review and future vendoring, and verified byte-for-byte — never a second
place to edit. To regenerate it after changing a schema:

```bash
python3 tools/gen_protocols.py            # verify (default; writes nothing)
python3 tools/gen_protocols.py --write    # regenerate
```

All five `protocol` commands are `read_only`: none opens SQLite, creates
`power.json` or workspace state, emits a ledger event, or needs an initialized
workspace. They work from an empty directory, and from `aos.pyz` with no
checkout at all.

## Retrieval evaluation (U-M5)

U-M5 answers one question with measurements instead of opinion: do lexical,
temporal, provenance and bounded graph signals retrieve better than what this
system does today, without leaking anything?

**It changes nothing.** `aos search`, `pack build` and pack MEMORY inclusion
behave exactly as they did before this unit existed. `retrieval` is an
evaluation and inspection surface; adopting a candidate is a separate human
decision, taken after reading this report. There are no embeddings, no vector
store, no model call and no new dependency — deciding whether any of that is
warranted is the whole point, and shipping it here would assume the answer.

```bash
# What can be measured?
python aos.py retrieval benchmark list
python aos.py retrieval benchmark show core-retrieval

# Measure it. Read-only: opens no database, writes no file, emits no event.
python aos.py retrieval benchmark run core-retrieval
python aos.py retrieval benchmark run graph-expansion --candidate all --k 5

# Run the candidate retriever against YOUR workspace (read-only).
python aos.py retrieval query "deploy window" --project demo
python aos.py retrieval query "deploy window" --project demo --graph-depth 1
python aos.py retrieval query "deploy window" --as-of 2026-01-01T00:00:00Z
```

### The three candidates

| Candidate | What it is |
|---|---|
| `baseline` | The closest faithful representation of today's lexical memory retrieval: conjunctive substring matching over `key + value`, **no eligibility filter** — exactly what `aos search` does. |
| `candidate-0` | Eligibility + latest-per-key + deterministic integer scoring over lexical, phrase, key, pin, scope, freshness and provenance signals. No graph expansion. |
| `candidate-1` | `candidate-0` plus bounded depth-1 expansion over **active** edges. |

The baseline is measured as it is, not rewritten to be easy to measure: a test
proves it returns the same memory result set as the live `search` backend.

### What retrieval refuses to return

A claim is retrievable only if it is `live`, unsuperseded, unexpired at the
requested `--as-of`, not `restricted`, hash-valid, and either global or in the
requested project. One predicate decides, and it is strictly stricter than the
pack builder's: U-M5 can refuse what a pack would carry, never the reverse.

Graph expansion inherits every one of those rules — there is no second, weaker
gate on the expansion path — and a neighbour needs at least one query term to
be included at all. A well-connected claim that matches nothing is noise, and
degree buys it nothing. Every expanded result ranks below every primary one,
so expansion adds recall at the tail and never disturbs the head.

### Explainable, not magic

Every result carries its rank, its integer score, each score component, its
match reasons, its lifecycle and provenance metadata, and — when it arrived by
expansion — which claim and edge carried it. There are no learned weights;
every weight is pinned in the contract. Default output prints metadata only:
never a claim value, a source locator, provenance text, an evidence ref or a
full hash. `--show-key` additionally prints the claim key, which is strictly
less than `memory show` already prints for exactly these claims.

### The gate is advisory

`benchmark run` exits 0 only when every **candidate** passes its gate: zero
leakage of any class, deterministic byte-identical replay, thresholds met, no
regression against the baseline, and result/graph bounds held. Any single
forbidden, wrong-project, restricted, lifecycle or hash-invalid result fails
the gate regardless of how good the relevance numbers are — one is a bug, the
other is a score.

`baseline` is reported but never gated: it is what production does today, it
cannot be "promoted", and gating it would mean exiting 1 forever the moment
production was measured to leak. Its leakage counters are printed at full
severity, because they are the finding.

The printed recommendation (`promote candidate-1` · `promote candidate-0` ·
`keep baseline` · `insufficient evidence`) is a deterministic function of
those gates. **No command acts on it.**

### Where the benchmark definitions live

Same mechanic as the protocol spine: the embedded Python definitions in
`agentic_os/retrieval.py` are canonical, so `aos.pyz` carries every benchmark
with no data directory. The checked-in JSON under `retrieval_benchmarks/` is a
deterministic byte-for-byte projection — never a second place to edit. The
fixtures are entirely synthetic: two invented projects, invented claims, and
deliberately planted leakage bait.

```bash
python3 tools/gen_retrieval_benchmarks.py            # verify (writes nothing)
python3 tools/gen_retrieval_benchmarks.py --write    # regenerate
```

All four `retrieval` commands are `read_only` and permitted in recovery mode;
none creates `power.json`. The `benchmark` leaves need no workspace at all.

## Targeting a workspace (--root)

Every command accepts a global `--root PATH` placed **before** the command:

```bash
python aos.py --root /path/to/workspace init
python aos.py --root /path/to/workspace task add "Task" -p demo
```

`--root PATH` means exactly `PATH/.agentic-os` — no searching, and it always
wins over discovery. Without it, behavior is unchanged from Night-1:
commands walk upward from the current directory to the nearest initialized
workspace, and `init` uses the current directory. `init --root PATH` remains
a compatible alias; passing both forms with different paths exits 1.

## Search backends

`search` uses SQLite FTS5 (bm25-ranked) when the local SQLite build provides
it, otherwise a LIKE-style substring fallback — detected at runtime and named
in the output (`backend: fts5` or `backend: like`). The FTS index inside
`aos.db` is a **derived artifact**: not part of the versioned schema, safe to
drop at any time, and rebuilt automatically whenever it is stale (its
watermark is the last events id it indexed). Semantics differ slightly: FTS5
matches whole words; the fallback matches substrings.

## Windows / Obsidian export (one-way)

`sync --export-to` projects the generated mirror beneath a directory of your
choice — typically a Windows path mounted under WSL — as a read-only copy:

```bash
python aos.py sync --export-to "/mnt/c/Users/you/Vaults/AOS Mirror" --dry-run
python aos.py sync --export-to "/mnt/c/Users/you/Vaults/AOS Mirror"
```

- Open **PATH as the Obsidian vault root**, never `PATH/AOS` — your
  `.obsidian/` settings and any other files beside `AOS/` are never touched.
- `PATH/AOS` is fully owned by the export: it always holds one complete
  generation, replaced wholesale via a validated staging directory
  (`PATH/.aos-export-staging`) and atomic renames. Ownership is proven by
  the reserved empty marker directory `PATH/AOS/.aos-export-owned` (don't
  delete it); a tree without it — or content inside `AOS` that the export
  didn't generate, hidden files and hardlinked aliases included — refuses
  the export instead of being deleted.
- The plan is computed from a fresh destination scan, and the destination
  must still match it at swap time: any mid-export change to `PATH/AOS`
  content or structure (files, bytes, sizes, directories, the ownership
  marker, or the directories' identities) makes the run refuse with
  "destination changed during export" rather than sweep the change away —
  rerun to get a fresh plan. Metadata-only changes (permissions,
  timestamps) are not part of the comparison.
- Strictly one-way: edits made on the Windows side are never ingested; the
  next export overwrites them. The ledger stays the only authority.
- Copy-if-changed: an identical source performs zero writes, and unchanged
  notes keep their identity via hardlinks where the destination filesystem
  supports them (DrvFS does not — there a changed export recopies the tree).
- Contained: destinations resolving into the live workspace, its database,
  the source mirror, or the enclosing repository are refused — as are
  symlinked `AOS` directories and traversal-escaping paths. The apply
  additionally pins PATH by descriptor identity before its first write and
  performs every rename, fsync, cleanup, and pre-swap verification read
  relative to that descriptor, so a concurrently replaced PATH (or staging
  directory) refuses instead of receiving a single write.
- Verified twice: the staged generation is validated in full and then
  re-verified — bytes, file/directory sets, sentinel, and hardlink
  relationships — against an immutable snapshot immediately before the
  swap, in freshest-last order (source first, destination next, the
  complete staging rescan and hash last, right before the renames); state
  probes treat an inspection error (EIO, EACCES) as a refusal, never as
  "absent". The staging build reads its source bytes only through a
  pinned source-root descriptor with per-file identity proofs — a swapped
  source directory or file refuses instead of redirecting the copy.
- Mount boundaries: a mounted or cross-device subtree inside `PATH/AOS`,
  the staging directory, or the source mirror refuses the export, and
  cleanup never recurses a delete across one — the cleanup root itself is
  checked for device and mount transitions before anything beneath it is
  touched. Caveat: a bind mount of the *same* filesystem is
  indistinguishable from a plain directory with standard-library checks,
  so only cross-device mounts are detected.
- Cleanup is quarantine-based and identity-proven: a staging or
  previous-generation tree is deleted only after its pinned descriptor
  identity matches what this run created or moved aside; the tree is
  atomically moved to a reserved private `PATH/.aos-export-cleanup-*`
  name, every entry inside it is atomically moved to a
  `.aos-export-cleanup-*` name within its own directory (nested inside
  the quarantined tree), and each is re-proven before its deletion — no
  meaningful name is ever deleted without an identity proof, and a
  substituted entry is retained (restored where possible) and reported.
  A leftover cleanup name from an interrupted run refuses the next export
  until inspected. Honest limits: POSIX cannot make deletion conditional
  on identity, so a racer hitting a just-verified single-use private name
  in the microseconds before its unlink/rmdir is outside the guarantee;
  and POSIX rename overwrites a type-compatible entry, so one raced onto
  a quarantine or restore target name inside the probe-to-rename
  microseconds (an empty directory for a directory move; a regular file
  or symlink for a file move — for restores that target is the entry's
  public name) is also outside it. The contract documents both windows;
  no stronger claim is made.
- Dry run previews every file create/update/delete with byte totals AND
  every directory create/delete (`create-dir Reviews/`), performs no
  destination mutation of any kind, and summarizes files and directories
  separately.
- The apply report counts what actually happened: created, updated,
  deleted, unchanged (split into hardlinked vs copied), and the payload
  bytes actually written — a hardlinked unchanged note costs zero bytes,
  a fallback-copied one counts in full.

Refusal messages, interrupted-export recovery, and DrvFS specifics are
documented in `TROUBLESHOOTING.md`.

## Layout

`python aos.py init` creates, under the current directory:

```
.agentic-os/
  aos.db            # SQLite ledger (source of truth)
  packs/            # compiled context packs (T-0001-claude-code.md, ...)
  exports/          # events-*.jsonl exports, aos-*.db snapshots, agent dropfiles
                    # (hook-staging/ holds U-H1 staged session write-backs)
  adapters/         # per-agent PROTOCOL.md (claude-code, codex, gemini, generic)
  backups/          # created on first `backup create`: aos-backup-*.db + manifest
  obsidian-vault/
    AOS/            # generated mirror: Home.md, CONVENTIONS.md, index notes
                    # (Tasks.md, Decisions.md, ...), Tasks/, Runs/, Decisions/,
                    # Evidence/, Handoffs/, Memory/, Agents/, Reviews/, ...
```

Human-facing IDs are stable and zero-padded: tasks `T-0001`, runs `R-0001`,
decisions `D-0001`, evidence `E-0001`, handoffs `H-0001`, packs `P-0001`,
memory `M-0001`.

In the checkout itself, `python3 tools/build_zipapp.py` writes `dist/aos.pyz`.
`dist/` and `*.pyz` are gitignored: the archive is generated from source and is
never committed.

## Rules of the road

- The vault is generated: never rename generated notes; edit data via the CLI
  and re-run `python aos.py sync` (see `AOS/CONVENTIONS.md`).
- One shared secret detector guards three boundaries with three postures:
  context packs **refuse** to build on secret-shaped content (naming the
  section and pattern, never the value); untrusted dropfile ingest
  **refuses the whole file atomically** (no partial rows, no dedupe
  marker, no event); trusted human CLI writes are **accepted with a
  warning** — the append-only ledger is never silently falsified — printed
  on stderr with field and pattern names only. The mutation event records
  the same safe metadata and never the value itself (secret-shaped payload
  strings are replaced by a fixed placeholder; the canonical row keeps the
  accepted value), and `doctor` reads that metadata — plus legacy raw
  payloads — to list affected record IDs (never values) so a real
  credential can be rotated and removed.
- The only subprocesses Agentic OS ever runs are read-only git queries
  (`rev-parse` / `show`) — to anchor runs to a commit and to verify commit
  evidence. Failures degrade gracefully; nothing is ever written to a repo.

## Tests

```bash
python -m unittest discover -s tests
```

## Protected delivery (CI)

U-P2 adds a continuous-integration and delivery gate for changes to this
repository. It changes how commits are validated and merged; it does not
change what Agentic OS does at runtime. "Protected delivery" here means
exactly **ordinary failure enforcement and accidental-change governance** —
nothing stronger. The trust boundary below states what that does and does
not include.

One workflow (`.github/workflows/ci.yml`) defines four public checks — the
job `name:` values, frozen verbatim:

| Check | What it does |
|---|---|
| `workflow-integrity` | Runs `python3 tools/verify_ci_workflow.py`, which accepts only the byte-exact frozen canonical workflow and fails closed on any deviation. |
| `tests-python-3.12` | Compiles `agentic_os`, `tests`, `tools`, `aos.py`, and `aos_hooks.py`, runs full unittest discovery, verifies the protocol projection, and asserts a clean working tree — on Python 3.12. |
| `tests-python-3.14` | The identical gate on Python 3.14. |
| `distribution-smoke-python-3.12` | Builds the wheel and zipapp with exact-pinned build tools, asserts archive membership byte-for-byte against the source tree, smoke-runs both artifacts in disposable workspaces outside the checkout, and asserts all three entrypoints print byte-identical `--help`. |

Supported CI feature lines: **Python 3.12** (the `requires-python` floor)
and **Python 3.14** (the pinned upper CI feature line). Every job prints the exact
resolved patch (`python3 -VV`) in its log.

Local validation, mirroring the hosted gate:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q agentic_os tests tools aos.py aos_hooks.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
python3 tools/gen_protocols.py
python3 tools/verify_ci_workflow.py
git diff --check
git status --short --branch
```

Check states are reported as **ABSENT / RUNNING / FAILED / GREEN**, and they
mean different things for trust: ABSENT means no conclusion exists at all
(never treat it as a pass — ABSENT is never reported as GREEN); RUNNING is
not yet a conclusion; FAILED blocks a merge wherever the check is required;
GREEN is a reported success of a repository-hosted check — trust it
according to the boundary below, not beyond it.

### Delivery-control trust boundary

Agentic OS operates under the **solo-maintainer honest-authority boundary**
(trust-boundary amendment, D-v0.4.45). Read these six facts together; any
stronger reading is wrong:

1. **The delivery controls are repository-hosted and self-modifiable.** The
   workflow, its canonical verifier, and the verifier's tests are stored in
   this repository — `.github/workflows/ci.yml`,
   `tools/verify_ci_workflow.py`, and `tests/test_v04_delivery_gate.py` —
   so a repository writer can modify all three together in one pull request.
2. **What they protect is honest development**: ordinary failure enforcement
   (a real failing check blocks a merge), deterministic delivery, and
   detection of accidental or isolated drift — an edit to one control file
   alone is caught by the other two.
3. **They are not an external or independently administered security
   authority.** Every enforcing byte is part of the pull-request head being
   evaluated.
4. **A required check name by itself does not prove that the check's
   semantics are unchanged.** Names are identities; the conclusions reported
   under them are computed by head-controlled code.
5. **Changes to the delivery-control files require exceptional manual
   review** — the exact requirements are in
   [CONTRIBUTING.md](CONTRIBUTING.md).
6. **Future independent authority is deferred and trigger-gated.**
   Adversarial tamper resistance becomes its own governed unit when a
   trigger is met: a second trusted reviewer plus CODEOWNERS and required
   review; an organization/enterprise required workflow outside the
   modifiable PR head; or a separately administered GitHub App or external
   status provider. Nothing from those triggers is partially implemented
   today.

Branch-ruleset activation (requiring the four checks on `main`) and the
failing-test acceptance probe are **later bootstrap steps**: whether they
are active is live GitHub state and must be confirmed from the repository's
actual settings, never inferred from repository files alone — including
this one.

There is still **no release publishing**: no PyPI distribution, no GitHub
Release, no signing, no SBOM, no containers. The wheel and the zipapp are
built and verified — by CI and locally — and installation remains a local,
manual step.

The contribution flow, focused pre-PR commands, and delivery-control change
rules are in [CONTRIBUTING.md](CONTRIBUTING.md). Per-check failure
diagnosis is in [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Status

Complete-today build, extending the Weekend and Night-1 MVPs — a database
created by either earlier build works with this code unmodified (no schema
change, no migration; `schema_version` stays `"1"`). This phase closed the
coordinate-and-audit loop: task lifecycle (`assign`/`edit`/`status` + list
filters), dropfile ingest, verified commit evidence (`evidence git`), the
agent registry with vault notes, richer daily/weekly/project reviews, Home
dashboard + index notes, and doctor hardening (now 21 checks incl. the
non-fatal commit-evidence warning, the U-C3 secret sweep, the two
U-H2 warn-only lines — success runs without attributable evidence, and
legacy blank-ref evidence rows — and the U-E2 runtime power state line).

U-M1 adds the migration kit (`migrate status` / `plan` / `apply`) and no
schema change: the registry is empty, `schema_version` stays `"1"`, and
every database from every earlier build still works unmodified. U-M2 (memory
v2) is blocked until U-M1 is merged — the framework lands first, so the
first real schema change arrives into something that already snapshots,
verifies, and refuses.

Deliberately deferred (unchanged triggers, see `agentic-os-two-week-plan.md`
§4): MCP server, Obsidian plugin, vector search, background runs, two-way
review ingest, routing/scoring, multi-device sync, any autonomous execution.
