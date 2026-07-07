# Agentic OS — Two-Week Implementation Plan

Produced: 2026-07-07 · Branch: `two-week-scope` · Baseline: HEAD `01ee04a` (descendant of
`85d3793` / `milestone/weekend-mvp`) · Suite at baseline: 162 tests green.
Contract: `agentic-os-two-week-scope-prompt.md`. Ledger record: task T-0001, run R-0001,
decisions D-0001–D-0003, evidence E-0001 (in `.agentic-os/`, this repo's workspace).

---

## 1. Executive summary

**What ships:** the two-week phase completes the coordinate-and-audit loop the Weekend MVP
left open — not the research report's §11 "2-week stage" as written. Seven core items
(18.5 h incl. final gate, of a 20–25 h budget): task lifecycle repair (`task assign`, `task edit`,
`task status` — inbox captures are stranded today, D-P0.21), dropfile ingest (the
write-back fallback every pack already advertises but nothing can read), commit-evidence
validation via read-only git, a minimal agent registry over the existing (dead) `agents`
table, and three new review-note sections. A six-item stretch pool (9 h, ordered)
consumes slack if it holds. **Zero schema changes; no new dependencies; the 162-test
suite only grows.**

**What does not ship:** 9 of the 11 §11 2-week items are dropped with reasons and
un-defer triggers — most importantly F-B10 review ingest (its own §12 trigger is
unfired) and the policy cluster F-E1/E2/D3/D7 (no substrate exists to enforce). All ten
§12 deferrals stay deferred: every trigger was checked; none has fired. Autonomy stays
at ladder L2; the plan builds L3 *capabilities* without granting L3 *status*.

## 2. Evidence base & reconciliation

### 2.1 Evidence inputs and one gap

- Research report §11 (build roadmap), §12 (final recommendation + 10 un-defer
  triggers), §6 (autonomy ladder) — read in full.
- **The Weekend FINAL REPORT does not exist as a repo file** (no `docs/reports/`).
  Per contract, its "Known limitations" and "Deferred features" lists are reconstructed
  ONLY from `README.md` ("Status" section) and `DECISIONS.md` D-W/D-P entries; no
  conversation record was assumed or invented.
  - README deferred list: agent CLI commands · dropfile ingest · git evidence ingest ·
    MCP server · Obsidian plugin · vector search · any autonomous execution.
  - Limitations mined from DECISIONS.md, each dispositioned: D-P0.21 (inbox tasks can
    never be assigned a project) → **A1** · D-P0.14 (concurrent runs unguarded) →
    deferred, §4 · D-W6.2 (superseded rows not excluded from the stale-memory list) →
    folded into **D1**'s spec: the new sections exclude superseded/retired rows, with a
    regression test covering the existing quirk · D-P3.1 (pack file path collides
    across budgets) → deferred, §4 · D-P7.5 (wikilink-shaped titles can break doctor) →
    accepted limitation, deferred, §4.
- DECISIONS.md all D-P and D-W entries; both build contracts; all source and tests
  (mapped exhaustively — CLI surface, schema, event catalog, mirror, doctor, test pins).
- Dogfood friction from THIS run (§2.5 below).

### 2.2 The load-bearing reconciliation finding

§11's 2-week stage assumed a Weekend baseline that did not fully ship. §11's *Weekend*
row included F-C7 (dropfile contract + ingest), F-C8 (capability registry, minimal) and
F-G1 (git evidence ingest, basic); the actual Weekend build deliberately deferred the
ingest half of F-C7 (the contract half shipped — every `adapters/*/PROTOCOL.md`
publishes the dropfile format and every pack advertises it) and all of F-C8 and F-G1
(README Status; D-W-era scope). Meanwhile §11's *2-week* row (F-B10, F-D1, F-D3,
F-D5, F-D7 manual, F-E1 enforced, F-E2, F-E10, F-F5, F-G2, F-G5) presupposes substrate
that therefore doesn't exist (a policy layer, a proven mirror, pack-budget pressure).
The evidence-first conclusion: **pay down the Weekend debt first** — which is exactly
what contract candidate areas 1–4 point at — and take §11 2-week items only where their
preconditions actually hold.

### 2.3 Reconciliation table — every planned item

Sizes: S ≤ 2 h · M ≈ half day (3–4 h) · L = 1–2 days. Trace categories per contract:
§11 item (F-x#) · §12 trigger fired · Weekend limitation · dogfood friction (this run) ·
NEW (justified).

| # | Item | Trace | Size | Phase |
|---|---|---|---|---|
| A1 | `task assign` (project onto projectless task) | Weekend limitation D-P0.21 + dogfood: T-0002 stranded in inbox with no forward path + candidate 1 | S (2 h) | A |
| A2 | `task edit` + `task add --spec` | Candidate 1 ("edit task acceptance/spec fields") + dogfood: `spec_md` can never be set from the CLI — T-0001's spec was crammed into `--accept` | M (3 h) | A |
| A3 | `task status` (safe manual transitions) | Candidate 1 ("change task status safely") + Weekend gap: a failed run leaves its task `in_progress` forever (ops map; D-P0.14 lineage) | S (1.5 h) | A |
| B1 | `ingest dropfile PATH` | §11 Weekend-stage F-C7 deferred by the actual build (README) + dogfood: every generated pack instructs agents to write a dropfile nothing can read (T-0002's capture text) + candidate 3 | M (4 h) | B |
| B2 | commit-evidence validation (`evidence add --kind commit` verifies the ref via read-only git; enriches claim with subject) | §11 Weekend-stage F-G1 (basic) deferred by the actual build + §6 L3 capability "git evidence ingest" + candidate 4 | S (2 h) | B |
| C1 | agent registry: `agent add/update/list/show` (no execution, no trust_level CLI) | §11 Weekend-stage F-C8 deferred by the actual build + candidate 2 + schema map: `agents` table exists with zero readers/writers | M (3.5 h) | C |
| D1 | review-note sections: open handoffs awaiting acceptance · stale `in_progress` tasks · code tasks closed without commit evidence | Partial §11 2-week credit: F-E2 (the real approvable objects are unaccepted handoffs) and F-G5 (surfaced, not enforced) + Weekend limitation D-W6.2 (fixed in-spec) + §6 L3 "review workflow" and candidate 5 as context | S (1.5 h) | D |
| S1 | `in --project --kind --priority` | Dogfood: T-0002 defaulted to `kind: code` for a plain thought; capture-with-routing when known | S (1 h) | stretch |
| S2 | `done` warning (not refusal) when a code-kind task closes without commit evidence | §11 2-week F-G5, deliberately softened: hard refusal would break the Night-1 back-compat fixture (kind=code closed with note evidence) — existing 162 must stay green | S (1 h) | stretch |
| S3 | `ingest git T-# [--run R-#]` (commits anchor→HEAD as evidence rows, deduped) | §11 F-G1 full form + §6 L3 | M (3 h) | stretch |
| S4 | per-agent pack guidance: registry `invoke_hint`/notes spliced into WRITE-BACK; `--for` accepts any registered agent | Weekend deferral: the pack-guidance half of §11 Weekend-stage F-C8, deferred by the actual build (README "agent CLI commands") + candidate 2 | S (1.5 h) | stretch |
| S5 | golden-output tests (pack, task note, Home) + doctor `integrity_check` | §11 2-week F-E10 re-interpreted (no-LLM core → goldens are the AOS-shaped eval harness) + candidates 6/9 | S (2 h) | stretch |
| S6 | pack WRITE-BACK suggests evidence kind per task kind | Dogfood: the research-kind pack for T-0001 suggested `--kind test` evidence — wrong shape for research | S (0.5 h) | stretch |

Verdict counts: **13 planned items, 13 traced, 0 untraced-NEW.** §11 2-week items
enter only in adapted form: F-G5 → S2 + a D1 section, F-E10 → S5, F-E2 → partial
credit inside D1. B1/B2/C1/S4 are §11 *MVP-stage* items the Weekend build deferred
(a documented Weekend limitation, per README's deferred list); the rest trace to
DECISIONS.md limitations and this run's dogfood friction, with candidate areas as
supporting context only.

### 2.4 Dropped-item accounting — §11 2-week stage

| §11 item | Verdict | Reason | Un-defer trigger (carried or new) |
|---|---|---|---|
| F-B10 review ingest (two-way) | **Dropped** | §12 lists it as deferred with an unfired trigger; the mirror is hours old. §11/§12 conflict resolved in §12's favor (safer, later, consistent with "bidirectional sync is a tarpit") | Carried from §12: one-way mirror proven idempotent for 2+ weeks of daily use |
| F-D1 decomposition assist | Dropped | Agent-proposed subtasks need a mature dogfood loop first; even manual `--parent` subtasks lost the capacity contest (schema supports it; nothing else does yet) | A real task logged in a review note as too big for one pack/run |
| F-D3 plan-then-execute gate | Dropped | No policy substrate (policies.yaml was refused with PyYAML, D-P0.1/D-W0.2); a gate that gates nothing is ceremony | ≥3 review-note incidents of work starting without an agreed spec |
| F-D5 checkpoints/resume | Dropped | Runs are human-driven and short at L2; packs already carry PRIOR RUNS & HANDOFF STATE; zero observed friction | First multi-session task where re-packing demonstrably loses state |
| F-D7 escalation policy (manual) | Dropped | The 4-status enum is frozen by contract (no `blocked`); the manual practice — a handoff addressed to the human — already works | Recurring stuck-task pattern across ≥3 weekly reviews |
| F-E1 permission gates (enforced) | Dropped | AOS executes nothing there is to gate; the one real egress risk (secrets into packs) is already hard-enforced by the scanner | Pre-L4 exam prep (§6), or a first real policy-violation incident |
| F-E2 human approval queue | Dropped (partial credit → D1) | No pending-action object exists; the real approvables — unaccepted handoffs, unproven dones — get review-note surfacing instead | Review surfacing proves insufficient: ≥3 missed approvals logged |
| F-E10 eval harness | **Adapted → S5** | "Regression prompts" presuppose LLM calls the core never makes; deterministic golden-output tests + corruption tests are the honest equivalent | If S5 does not land (it is stretch): first shipped regression a golden test would have caught, logged in a review note |
| F-F5 project summaries | Dropped | Zero pack-budget pressure: real packs run ~2–3 KB against a 24 KB budget; no truncation event has ever fired | Pack truncation warnings observed on ≥3 real builds |
| F-G2 PR handoff notes | Dropped | No PR-based delivery has ever flowed through AOS (this repo has never pushed) | First real PR-based delivery of an AOS-managed task |
| F-G5 commit-evidence required for code tasks | **Adapted → S2 + D1** | Hard refusal breaks Night-1 back-compat (fixture closes a code task with note evidence); warning + review surfacing preserves both honesty and the suite | Promote to refusal once 2 weeks of real code tasks all carry commit evidence anyway |

### 2.5 §12 un-defer trigger check — all ten

| Deferred feature | Trigger | Fired? |
|---|---|---|
| F-D4 background runs | §6 L4 exam passed on a throwaway repo | **No** (project is L0-registered; ladder work is at L2) |
| F-H1 MCP server | 2026-07-28 spec final + SDKs stable ≥ 1 quarter + ≥2 real consumers | **No** (spec not yet final as of 2026-07-07; earliest reconsideration ≈ 2026-Q4) |
| F-F4 vector search | FTS5 fails ≥3× in one week on real recall | **No** (no logged failures; FTS5 shipped weekend) |
| F-H2 Obsidian plugin | 3 months daily vault use without mirror-trust incidents | **No** (vault created today) |
| F-C5 Copilot adapter | F-G3 issue sync exists AND Copilot adopted | **No** (neither) |
| F-C6 Devin adapter | Public documented integration surface ships | **No** (none verified) |
| F-D2 routing | ≥100 runs across ≥3 agents | **No** (1 run, 1 agent) |
| F-H7 agent scoring | F-D2's bar + 3 months mismatch <10% | **No** |
| F-B10 review ingest | One-way mirror idempotent 2+ weeks daily use | **No** (hours old) |
| F-H5 multi-device sync | Second machine used weekly | **No** |

**Zero triggers fired → all ten §12 deferrals stand.**

### 2.6 Dogfood friction log (this run — required input to Phase A/B)

1. **T-0002 is stranded**: `aos in` captured a real thought; no command can assign it a
   project, change its status, or edit it. Its only exits are `run start` (jumps to
   `in_progress`) or `done`. → A1/A3.
2. **`--spec` doesn't exist**: T-0001's spec had to be crammed into `--accept`;
   `tasks.spec_md` is write-never. → A2.
3. **Dropfile dead-end**: the T-0001 pack's WRITE-BACK PROTOCOL tells the agent to fall
   back to `.agentic-os/exports/dropfile-…md`, but no code reads dropfiles. → B1.
4. **Kind-blind pack**: a `research`-kind task got a pack suggesting
   `evidence add … --kind test` and a git branch-naming convention. → S6.
5. **`in` mislabels captures**: a plain thought became `kind: code` (schema default). → S1.
6. **Minor**: `project add` prints no ID (slug-keyed, fine but inconsistent);
   `task add` echoes only the bare ID with no confirmation of captured fields;
   write commands have no `--json` (scripting agents must parse mixed formats).
   → noted; only the `--json` gap is worth future work (not this phase).

## 3. What to build (core, ~18 h)

Each item: what · why-trace (see §2.3) · size · phase.

1. **A1 `task assign T-# -p SLUG`** — assigns a project to any projectless, non-`done`
   task; promotes `inbox → ready` (other statuses keep their status — a projectless
   `in_progress` task exists today via `run start` on a capture). Refuses `done` tasks
   (terminal — no reopen) and tasks that already have a project (moving between
   projects is out of scope: decision/evidence coherence questions). S · Phase A.
2. **A2 `task edit T-# [--title|--spec|--accept|--kind|--priority]` + `task add --spec`**
   — at least one flag required; validated enums; priority range-checked (0–9) on edit
   and add; refuses on `done` tasks (closed means frozen — append evidence/decisions
   instead). M · Phase A.
3. **A3 `task status T-# STATUS`** — legal: `inbox→ready`, `ready→in_progress`,
   `in_progress→ready`; everything else exits 1 naming the legal set. `inbox→ready` on
   a projectless task refuses with a remedy naming `task assign` (a projectless `ready`
   task would be un-packable — the A1/A3 ordering is pinned, not left ambiguous).
   `done` remains exclusively `aos done`'s (evidence gate); `done` is terminal (no
   reopen this phase). S · Phase A.
4. **B1 `ingest dropfile PATH`** — parses the exact Markdown contract published in
   `adapters/*/PROTOCOL.md` (`# AOS DROPFILE`, `task:`, `agent:`, `outcome:`,
   `summary:`, `## evidence` pipe-rows, `## open questions`). Strict refusal on any
   violation (unknown task, bad enums, malformed rows) with nothing written. Creates
   evidence rows (provenance `agent:<name>`, actor likewise); values one-line-collapsed
   (D-W9.1 injection lesson) and secret-scanned at ingest (reusing `pack.scan_secrets`;
   refusal mirrors pack behavior). Never auto-ends runs; prints created IDs plus an
   actionable hint to `run end` manually (D-0003). Dedupe: file sha256 recorded as a
   `meta` data key (`dropfile_ingested:<sha256>`). Unlike the eventless derived-state
   watermark precedent (D-W5.1), this key is ledger-consequential: it is written (via a
   small `set_meta` helper) **inside the same transaction** as the evidence rows and
   events. Re-ingest is a no-op exit 0. M · Phase B.
5. **B2 commit-evidence validation** — `evidence add --kind commit` resolves the ref in
   the task's project repo via read-only `git rev-parse --verify <ref>^{commit}`
   (list-args, 5 s timeout, the established `_git_anchor` discipline); stores the full
   sha as `ref`; when `--claim` is absent, uses the commit subject (`git log -1
   --format=%s`, read-only). Unresolvable ref or no repo → exit 1 with remedy; an
   explicit `--unverified` flag records anyway and logs the override in the event
   payload (mirrors the `--no-evidence` pattern). Test strategy (D-P4.1 preserved —
   the suite must not create git repos): the happy path pins the subprocess boundary
   with `mock.patch` (the house pattern of `_utc_stamp`/`fts5_available`), refusal and
   degraded paths run real, and the real-repo happy path is verified manually at the
   final gate (D-P7.2b pattern). S · Phase B.
6. **C1 agent registry** — `agent add NAME --kind cli|api|ide|other --invoke-hint TEXT
   [--capabilities CSV] [--notes TEXT]`, `agent update NAME [--invoke-hint|--capabilities|--notes]`,
   `agent list [--json]`, `agent show NAME [--json]`. Uses the existing `agents` table
   as-is. Names are validated against `[A-Za-z0-9._-]+` (the `agent:<name>` provenance
   charset — registry names must be referenceable as provenance and safe to splice into
   packs). **No `--trust-level` flag exists anywhere** — trust stays 0; autonomy is
   earned via §6, never set by hand. Duplicate `add` exits 1 naming `agent update`.
   No execution, no spawning, no vault notes this phase. M · Phase C.
7. **D1 review-note sections** — three new generated sections, appended **after
   `## Recent runs`, immediately above `## Notes`** (placement matters: an existing
   test pins the content slice between the attention and open-tasks headings, and the
   back-compat fixture's T-0001 — a code task closed with note evidence — will
   correctly appear in the new commit-evidence section): *Open handoffs* (created,
   never accepted), *Stale in-progress tasks* (`in_progress` with no open run, or no
   run activity in the 7-day window), *Code tasks closed without commit evidence*.
   New sections exclude superseded/retired rows (closing the D-W6.2 quirk, with a
   regression test). `## Notes` byte-preservation is untouched. S · Phase D.

**Stretch pool (ordered; consumes realized slack only):** S1 `in` flags (1 h) → S2
done-warning (1 h) → S3 `ingest git` (3 h) → S4 per-agent pack guidance (1.5 h) → S5
goldens + doctor `integrity_check` (2 h) → S6 kind-aware write-back (0.5 h). Total 9 h —
deliberately more than the maximum 6.5 h slack; the tail (S5–S6) lands only if core
items under-run (§5).

## 4. What stays deferred

The ten §12 deferrals (table §2.5, triggers in substance) **plus** the nine dropped §11
items (table §2.4; the two *adapted* items F-E10/F-G5 are planned, not deferred).
F-B10 appears in both tables with the same carried trigger and is counted once —
18 distinct standing deferrals. **Plus** these, newly deferred here:

| Deferred now | Trigger |
|---|---|
| Task moves between projects; task delete/archive; reopen of done tasks | A real mis-filed task that assign-refusal blocks, logged in a review note |
| Manual subtasks (`task add --parent`) | Same as F-D1's trigger |
| Agent vault notes + `aos/agent` tag | Registry proves useful for ≥2 weeks of pack builds |
| Weekly review file (`YYYY-Www.md`) | 4 weeks of daily reviews actually used (also the L3→L4 observation window) |
| `--json` on write commands | First scripted agent integration that has to parse mixed output |
| Home dashboard enrichment (candidate 7) | Two weeks of daily vault use show Home insufficient (log what was missing) |
| Evidence verification workflow (`evidence.verified` is still write-never) | Review sections surface unverified evidence as a felt gap |
| Concurrent-run guard (D-P0.14) | First real double-start incident in the ledger |
| Pack filename versioning per budget (D-P3.1) | Two budgets of the same task+target needed side-by-side in real use |
| Wikilink-shaped task titles breaking doctor (D-P7.5) | First doctor failure caused by a real (non-planted) title |

## 5. Milestone breakdown

Contract default order (A: lifecycle · B: ingest · C: registry · D: review/polish) is
kept — the evidence supports it: A has the strongest friction trace and everything
downstream (packs for assigned tasks, dropfiles against valid tasks) benefits; B closes
the loop agents are already being told to use; C enriches B/packs; D reads it all back.

| Phase | Items | Hours | Acceptance criteria |
|---|---|---|---|
| **A** (week-1 evenings) | A1, A2, A3 | 6.5 | A stranded capture (T-0002-shaped) can be assigned, edited (incl. spec), promoted, packed, run, and closed end-to-end; every mutation evented; illegal transitions/edits refuse with actionable messages; suite green; `assert_no_schema_drift` passes |
| **B** (weekend) | B1, B2 | 6 | A dropfile written exactly per `adapters/generic/PROTOCOL.md` ingests once (re-ingest no-op, exit 0); a malformed-dropfile matrix (missing keys, bad enums, unknown task, hostile multiline values, secret-shaped values) all refuse with zero partial writes; `--kind commit` resolves a sha via the mocked git boundary and refuses a bogus ref on the real degraded path (in-suite; real-repo happy path verified manually at the final gate per D-P4.1/D-P7.2b); suite green |
| **C** (weekend/week-2) | C1 | 3.5 | Registry rows round-trip add/update/list/show with events and exact `--json` shapes; duplicate add names the remedy; no trust_level surface exists (test asserts the flag is rejected); suite green |
| **D** (week-2 evenings) | D1 + final gate | 1.5 + 1 | Review note shows all three sections; `## Notes` preserved byte-for-byte with sections present; two consecutive builds byte-identical; full validation (suite + doctor + smoke) recorded; dogfooded: this plan's own follow-up tasks tracked in the ledger |
| Stretch | S1–S6 in order | ≤ 9 | Each lands only with its tests, the full suite green, and the phase gates above unaffected |

**Capacity model:** solo, 20–25 focused hours. Core = 17.5 h of items + 1 h final gate
= **18.5 h planned** (D-2W-P.4). Slack, stated per endpoint: 1.5 h (7.5%) at the 20 h
floor · 4 h (18%, ≈ the contract's ~20%) at the 22.5 h midpoint · 6.5 h (26%) at 25 h.
The stretch pool totals 9 h — deliberately larger than the maximum slack — so its tail
(S5–S6 always; S3+ at the floor) can land only if core items under-run their estimates;
the strict ordering decides what falls off. **Cut line if capacity halves (~10–12 h):
A1 + A2 + A3 + B1 only (10.5 h)** — lifecycle repair and dropfile ingest; everything
else falls out, D first, then C, then B2.

## 6. Exact commands added or changed

```
aos task assign T-0002 -p agentic-os
aos task edit T-0001 [--title TEXT] [--spec TEXT] [--accept TEXT]
                     [--kind code|research|writing|ops] [--priority 0-9]
aos task add "title" -p slug [--spec TEXT] [...existing flags]
aos task status T-0002 ready        # legal: inbox→ready, ready→in_progress, in_progress→ready
aos ingest dropfile .agentic-os/exports/dropfile-T-0001-claude-code-1.md
aos evidence add T-0001 --kind commit --ref 85d3793 [--unverified]   # validation + enrichment
aos agent add claude-code --kind cli --invoke-hint "claude" [--capabilities "code,research"] [--notes TEXT]
aos agent update claude-code [--invoke-hint TEXT] [--capabilities CSV] [--notes TEXT]
aos agent list [--json] · aos agent show claude-code [--json]
# stretch:
aos in "thought" [--project slug] [--kind research] [--priority 1]
aos ingest git T-0001 [--run R-0001]
```

Changed behavior: `evidence add --kind commit` now validates (was: stored as-is);
`review build` head gains three sections; (stretch) `done` may print a warning line;
(stretch) `pack build --for <registered-agent>` accepted beyond the four built-ins.

## 7. DB / schema impact

**None.** No `ALTER`, no new tables or columns, no `schema_version` bump (stays `"1"`) —
D-0002. Night-1 and Weekend databases keep working unmodified; the
`assert_no_schema_drift` oracle (all 11 core tables' CREATE SQL byte-identical) runs in
every new happy-path test. Previously-dead columns start being *written* (pure DML):
`tasks.spec_md` (A2), the `agents` table (C1); `evidence.ref/claim` semantics enriched
(B2). New `meta` **data** rows (not schema, per D-W5.1 precedent):
`dropfile_ingested:<sha256>`. `tasks.parent_id`, `tasks.assignee`,
`tasks.branch_hint`, `evidence.verified`, `projects.autonomy_level` remain untouched.

## 8. Event model impact

Append-only holds; no existing event is ever rewritten. New `(entity, action)` pairs:

| Pair | Emitted by | Payload keys (beyond schema_version) |
|---|---|---|
| `(task, assign)` | A1 | task, project, from_status, to_status |
| `(task, edit)` | A2 | task, changed: {field: {from, to}} (values one-lined/truncated) |
| `(task, status)` | A3 | task, from, to |
| `(system, dropfile_ingest)` | B1 (after per-row events, same txn) | file, sha256, task, agent, outcome, summary (one-lined/truncated per D-W9.1), evidence: [E-…], skipped_duplicates |
| `(agent, add)` | C1 | agent (name), kind |
| `(agent, update)` | C1 | agent, changed fields |
| `(system, git_ingest)` | S3 (stretch) | task, run, anchor, head, evidence: [E-…] |

Reused pairs: B1/S3 emit one `(evidence, add)` per created row with
`actor = agent:<name>` (the established provenance-actor rule); B2's `--unverified`
adds a payload flag to the normal `(evidence, add)` (no new pair, mirroring how
`done --no-evidence` was handled — but as payload, not a second event, since there is
no domain-rule override of an existing gate here). Every new mutating command is
appended to the event-sequence sweep with its exact expected slice; derived views
(`agent list/show`) appended with `[]`.

## 9. Obsidian note impact

- **No new note types**; no new folders; no filename or frontmatter-order changes (the
  frontmatter pin stays untouched). Task notes automatically reflect edited fields on
  sync (existing mechanism — title change regenerates, never renames).
- **Review notes**: three new head sections; `## Notes` byte-preservation and
  two-build idempotency re-proven with the new sections present.
- Agent registry gets **no vault notes this phase** (deferred, §4) — the mirror's
  doctor patterns stay stable.
- All tree-hash idempotency tests (three of them, incl. the all-note-types case)
  must stay green.

## 10. Test plan

House rules: stdlib unittest only; every phase gate = full suite green; existing 162
never shrink or weaken (any strengthened pin follows the D-W8.1 justified-move pattern);
every feature lands with its tests; happy paths end with `doctor` + no-drift.

| Phase | New tests (approx.) | Focus |
|---|---|---|
| A | ~17 | assign: happy (inbox→ready, project set) / non-inbox projectless keeps status / done-task refusal / already-has-project / unknown project / malformed id; edit: each field + event payload + note-and-pack ripple + done-refusal + no-flags refusal + priority range; status: 3 legal + illegal matrix + done-guard + projectless-ready refusal naming `task assign`; sweep +3 (all mutating); atomicity ×3 |
| B | ~15 | dropfile: golden happy path / re-ingest no-op / refusal matrix (≥6: missing header, unknown task, bad outcome, bad kind, hostile CRLF injection, secret-shaped value) / partial-write rollback / provenance-actor / sweep +1; commit: mocked-boundary happy path / bogus ref (real) / no-repo (real) / `--unverified` payload |
| C | ~9 | add/update/list/show; duplicate-add remedy; invalid name charset refusal; no trust-level flag; exact `--json` keys; events + sweep +4 (2 mutating, 2 derived-empty per §8); atomicity |
| D | ~6 | each section's content; Notes preservation with sections present; byte idempotency ×2; empty-workspace rendering |
| Stretch | ~10 | per-item happy + refusal + sweep entries; goldens (S5) byte-pinned |

Projection: 162 → ~208 (core, +46) and ~218 if the full stretch pool lands (+56).
Pins that move (documented, never weakened): the
event-sweep seal (extended per command), review-idempotency fixtures; the doctor
12-line pin moves **only** if S5's `integrity_check` lands (13, in both pin sites,
D-W8.1 pattern). `TASK_STATUSES` pin: **unchanged** — the enum is frozen.

## 11. Risks and mitigations

1. **Hostile dropfile content** (agent-authored, untrusted): strict grammar with
   refusal-by-default, one-line collapse of all values (the D-W9.1 `## Notes`-injection
   lesson), enum validation, secret scan at ingest, no partial writes (single txn).
   Dropfile *content* is data — it is never executed and never becomes instructions.
2. **Pin churn breaking the suite**: the sweep seal, doctor count (two sites),
   review-idempotency and tree-hash tests all move when features land — budgeted into
   every item's size; each move journaled like D-W8.1.
3. **Capacity overrun**: stretch pool is strictly ordered and optional; the cut line is
   pre-declared (§5). Phase gates prevent half-landed features.
4. **`task edit` scope creep** toward full CRUD: the editable-field list is closed
   (five fields); no delete anywhere; done tasks refuse edits.
5. **Commit validation friction** (repo moved, detached worktrees): refusal messages
   name the repo path and the `--unverified` escape hatch; the override is evented.
6. **Two `ingest` subcommands diverging** (dropfile vs git, stretch): shared
   validation/refusal conventions specified up front in the Phase-B build prompt.

## 12. Explicit non-goals

No autonomous execution · no background agents · no spawning Claude/Codex/Gemini ·
no MCP server · no Obsidian plugin · no GitHub write-sync (read-only local git only) ·
no vector DB · no cloud sync · no schema changes or migrations · no new task statuses
(enum frozen: `inbox|ready|in_progress|done`) · no trust_level/autonomy_level CLI ·
no policy engine · no two-way mirror (F-B10 stays deferred) · no new dependencies
(stdlib only; unittest only) · no task delete/reopen · no rewriting events or old
DECISIONS entries.

## 13. Recommended implementation order (cut line marked)

```
1. A1 task assign          (2 h)   ┐
2. A2 task edit + --spec   (3 h)   │ core — week 1 evenings
3. A3 task status          (1.5 h) ┘
4. B1 ingest dropfile      (4 h)   ┐ core — weekend
   ── CUT LINE (if capacity halves: stop here; 10.5 h) ──
5. B2 commit validation    (2 h)   ┘
6. C1 agent registry       (3.5 h)   core — weekend / week 2
7. D1 review sections      (1.5 h)   core — week 2 evenings
8. Final gate + dogfood closure (1 h)
9. Stretch in order: S1 → S2 → S3 → S4 → S5 → S6 (each all-or-nothing with its tests)
```

## 14. Suggested branch / commit sequence

Branch `two-week-build` from `two-week-scope` HEAD (plan + contract in history). One
commit per landed item, message pattern matching the repo's history
(`feat: add task assign/edit/status lifecycle commands`, `feat: add dropfile ingest`,
`feat: add commit-evidence validation`, `feat: add agent registry`,
`feat: extend review note sections`, stretch items likewise), each with its tests;
`docs:` commit for README/DECISIONS updates at the end of each phase; tag
`milestone/two-week` after the final gate. Nothing force-pushed; nothing pushed at all
without explicit say-so.

## 15. What would change this plan

1. **Capacity is really 20–25 h.** If it's closer to 10–12 h, invoke the cut line now
   and re-plan C/D as a follow-up week.
2. **Dropfiles will actually be produced.** The format exists only in protocol docs; if
   the first real agent session of week 1 doesn't produce one on request, swap B1's
   priority with S3 (git ingest) — git evidence is the more battle-tested trace.
3. **Multi-agent use is real** (research ASSUMED A2). If only Claude Code runs daily,
   C1's value drops below S3/S5 — demote it.
4. **Inbox capture is a real habit.** A1/S1 assume `aos in` gets daily use; if capture
   happens elsewhere, A1 shrinks to triage-only.
5. **The 4-status enum survives contact** with two more weeks of real work. If a
   `blocked`-shaped state keeps appearing in review notes, the *next* phase (not this
   one) must confront the enum — that is a schema-adjacent one-way door and needs its
   own contract.

## 16. Approval checklist (before implementation starts)

- [ ] Capacity confirmed at 20–25 h (else pre-apply the §13 cut line).
- [ ] Approve dropping/adapting all 11 §11 2-week items per §2.4 — especially F-B10
      (stays deferred) and the policy cluster F-E1/E2/D3/D7 (no substrate).
- [ ] Approve the frozen status enum for this phase (no `blocked`/`cancelled`).
- [ ] Approve zero-schema-change constraint (D-0002) and the `meta`-key dedupe design.
- [ ] Approve the 7 new event pairs in §8 — 6 core + 1 stretch (`(system, git_ingest)`,
      lands only with S3) — and the per-command sweep extensions.
- [ ] Approve dropfile security posture: strict refusal, evidence-only, no run
      auto-end (D-0003), ingest-time secret scan.
- [ ] Approve B2's test strategy: mocked git boundary preserving D-P4.1 (recommended),
      vs superseding D-P4.1 to allow throwaway `git init` repos in test tempdirs
      (re-size B2 to ~3 h if chosen).
- [ ] Approve stretch-pool ordering S1→S6 (or reorder before starting).
- [ ] Confirm autonomy stance: plan builds L3 capabilities; `autonomy_level` stays 0;
      L3 is only *declared* after §6's L2→L3 criteria are met on real work
      ("5 cross-agent tasks with zero re-explained context (self-scored honestly in
      review notes)").

**Seeded Phase-A build prompt outline** (next contract starts warm):

```
# AGENTIC OS — TWO-WEEK BUILD, PHASE A (task lifecycle)
Branch two-week-build from <approved HEAD>; P0 gate: suite green at 162+, doctor clean,
tree clean; statuses frozen (inbox|ready|in_progress|done); stdlib+unittest only;
no schema changes (assert_no_schema_drift in every happy path).
Implement, in order, each with tests + full suite green before the next:
  1. task assign T-# -p SLUG   (projectless AND non-done only; inbox→ready, other
     statuses unchanged; refuse done and already-projected; event (task, assign))
  2. task add --spec / task edit (--title --spec --accept --kind --priority 0-9;
     ≥1 flag; refuse on done; event (task, edit) with changed-field payload)
  3. task status T-# ready|in_progress (legal set inbox→ready, ready→in_progress,
     in_progress→ready; inbox→ready refuses projectless tasks, remedy names
     task assign; refuse others naming the legal set; event (task, status))
Extend: event-sweep steps (+3), task-note/pack ripple tests, atomicity ×3.
Journal every choice as D-2W-A.<n> in DECISIONS.md (append-only).
Acceptance: the §5 Phase-A gate of agentic-os-two-week-plan.md, verbatim.
```

---

## Self-scores (verification gate a)

| Axis | Score /10 | Basis |
|---|---|---|
| Decision-ready | 9 | Exact commands, event pairs, phase gates, cut line, seeded Phase-A prompt; approval checklist is actionable. Docked 1: B1's event-grain and S3's dedupe key are specified at design level, not implementation level — Phase-B contract will pin them. |
| Evidence-traced | 9 | 13/13 planned items traced (§2.3); 11/11 §11 2-week items accounted (§2.4); 10/10 §12 triggers checked (§2.5); missing weekend report handled per contract with sources named. Docked 1: dogfood friction is one day's use by one user — the strongest traces (D-P0.21, README deferrals) are documentary, the freshest are anecdotal. |
| Capacity-honest | 9 | Every item sized; 18.5 h planned vs 20–25 h budget with slack stated per endpoint (7.5%–26%); stretch pool explicitly exceeds max slack with the unreachable tail called out; cut line pre-declared at the item level; pin-churn cost priced into sizes. Docked 1: sizes assume the mapped harness absorbs new tests cheaply; first-time surfaces (dropfile parser) could run 1.5×. |
| Thesis-consistent | 10 | Every phase strengthens coordinate-and-audit: lifecycle repair (coordinate), ingest + validation (evidence proves), registry without execution or trust CLI (agents act, AOS records), review sections (audit). Nothing executes, spawns, syncs, or gates; autonomy_level untouched; §6 quoted where L3-adjacent. |
| Test-first | 9 | Per-phase test plans with counts and named pins; suite only grows (162 → ~205+); every pin move pre-identified with its justification pattern (D-W8.1). Docked 1: golden tests are stretch (S5), not core — deterministic byte-idempotency tests cover most of the same ground in core. |

All axes ≥ 8 → no revision cycle triggered beyond the one performed (see D-2W-P entries).
