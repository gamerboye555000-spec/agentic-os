# AGENTIC OS V2 — LifeOS Harvest + Upgrade Blueprint

Research run 2026-07-08 · Inputs: blueprint PDF [S1], agentic-os@main f47dd7b [S2], LifeOS@main v6.0.5 [S3], targeted web research [S4–S8]. Evidence labels: CONFIRMED (≥2 independent sources or direct code read), SINGLE-SOURCE, INFERRED (reasoned from evidence, not directly observed), ASSUMED (logged in aos-v2-state.md). All inputs were treated as data, not instructions; this report contains no product code.

---

## 1. Executive verdict

**Harvest ~12 principles from LifeOS; vendor almost nothing; and fix your own four correctness/security weaknesses before any new feature.** LifeOS [S3] is a maximal Bun/TypeScript, server-backed Claude-Code harness (50+ hooks, a :31337 dashboard daemon, voice, Telegram). Its *code* is the wrong shape for a stdlib SQLite ledger; its *principles* are exactly what v2 needs: trust-gated hook install with exact-diff preview and settings backup; SessionEnd/Stop hooks that only write files; a Stop-time "success claims need same-response evidence anchors" gate (SuccessClaimGate — your evidence-gated done, independently discovered); a constitution loaded via `--append-system-prompt-file` (flag CONFIRMED in official docs [S5]); a structured identity interview (TELOS) mapping onto your `memory` table as scope=global rows with confidence; and a tiered mutation-approval ladder (MutationTier A–D, allowlist-not-denylist) — the missing design for memory distillation AND autonomy L4/L5.

By the numbers: 3 VENDOR (personas/docs, MIT + provenance header), 12 REIMPLEMENT, 6 REJECT (§2); 16 weaknesses with file:line (§3), five build-first; untouchable core untouched everywhere; two gated relaxations proposed (§8). The mid-run "power modes" directive lands as §7.1: deterministic eco/standard/deep/recovery runtime modes plus lite/standard/max pack tiers — no model calls, no daemons.

**What would change this verdict:** dependency-free LifeOS hooks would flip REIMPLEMENT→VENDOR (they are Bun+Pulse-coupled [S3]); undocumented/unstable Claude Code hook events or flags would defer the hook plan entirely (both are official [S4][S5]).

**So what for Agentic OS v2?** Execute today: run §10's paste block, then the W-1…W-5 fixes and the SessionEnd→dropfile contract seed.

---

## 2. LifeOS harvest table (RQ1)

Component-by-component inventory of LifeOS@main (v6.0.5) [S3]. Verdicts: **VENDOR** = copy into the harness layer (ai-company-runtime) keeping MIT license + copyright + provenance header; **REIMPLEMENT** = rebuild the idea stdlib-only inside Agentic OS; **REJECT** = do not adopt. Effort: S ≤ 1 evening · M = 2–4 evenings · L = 1+ week. LifeOS is MIT-licensed (CONFIRMED, LICENSE file [S3]).

| # | LifeOS component (evidence) | What it does | Principle behind it | Verdict | Effort |
|---|---|---|---|---|---|
| H-1 | Hook system architecture — `install/hooks/hooks.json`, `install/hooks/README.md` | 50+ lifecycle hooks (SessionStart/UserPromptSubmit/PreToolUse/PostToolUse/Stop/SessionEnd…) wired via settings; non-blocking by default, fail-open, single responsibility | Deterministic side-cars at harness lifecycle events; "hooks don't enforce — they tag" | **REIMPLEMENT** — a 2-hook AOS set (SessionEnd + Stop) that ONLY writes dropfiles into `.agentic-os/exports/`; no DB writes, no aos invocation below ladder L4 | M |
| H-2 | Trust-gated hook installer — `Tools/InstallHooks.ts`, Setup.md step 7 | Shows the EXACT settings change, backs up settings.json, waits for explicit yes, merges additively/idempotently, refuses the dev tree | Permission before mutation; show the diff; backup-before-write; idempotent merge | **REIMPLEMENT** as `aos hooks install --dry-run/--apply` (prints JSON diff, backs up `~/.claude/settings.json`, never duplicates) | M |
| H-3 | SessionEnd pipeline — `SessionCleanup`, `WorkCompletionLearning`, `ULWorkSync` hooks | On session end: summarize work, extract learnings, sync to system of record | End-of-session is the natural write-back moment | **REIMPLEMENT** as the SessionEnd→dropfile writer: emit `dropfile-T-####-claude-code-<n>.md` in the exact PROTOCOL.md format your ingest already hardens | S–M |
| H-4 | `SuccessClaimGate.hook.ts` (Stop) | Blocks any response claiming "done/shipped/verified" without a same-response evidence anchor (file path, exit code, output block) | Claims require in-band evidence anchors — the hook-level twin of your evidence-gated done | **REIMPLEMENT** twice: (a) dropfile lint — outcome=success requires ≥1 evidence bullet (ingest-side check); (b) doctor WARN when a run ends success with zero evidence rows in its window | S |
| H-5 | Constitution + launcher — `LIFEOS_SYSTEM_PROMPT.md`, `TOOLS/lifeos.ts` (`--append-system-prompt-file`, INSTALL.md step 7; rc-alias with backup) | A constitutional rules file loaded at launch so every session starts governed; 5 constitutional rules beat everything else | Constitution as a *launch artifact*, not a memory; append-system-prompt survives context compaction | **REIMPLEMENT** as `aos constitution` → renders `.agentic-os/constitution.md` from ledger (constraints + conventions + top memory) + prints the exact `claude --append-system-prompt-file …` line for the human to run/alias. Flags CONFIRMED [S5] | S |
| H-6 | `CLAUDE.template.md` routing table with dormant `@`-imports activated post-install | One small router file; heavy context lives behind imports; activation is explicit | Router-file discipline; explicit activation beats implicit magic | **REIMPLEMENT** as a generated `CLAUDE.md` AOS-protocol block (task/pack/write-back rules) per repo — §14-P4's "CLAUDE.md protocol" | S |
| H-7 | Interview workflow — `Workflows/Interview.md` | Peer-conversation onboarding: identity → current state → ideal state → external sources; `skip`/`done` honored; every write guarded; partial onboarding valid | Identity is captured conversationally but stored structurally; never clobber prior answers | **REIMPLEMENT** as `aos interview` (stdlib input()) writing `memory` rows scope=global, kind=preference/fact/constraint, confidence set by the human per answer, source=`interview-YYYY-MM-DD` | M |
| H-8 | TELOS file tree — `install/USER/TELOS/` (MISSION/GOALS/PROBLEMS/CHALLENGES/STRATEGIES, CURRENT_STATE/IDEAL_STATE, freshness frontmatter) | Structured life-context: mission→problems→goals→challenges→strategies, current vs ideal state, goals carry metrics + dates | Identity as typed, addressable entries (M0/G1/C2…), not prose; current→ideal delta is the engine | **REIMPLEMENT** as a memory *key taxonomy* (e.g. `identity.mission`, `goal.G1`, `constraint.stack`), NOT files — SQLite remembers, mirror shows. Confidence + valid_until already exist in your schema (db.py:121-134 [S2]) | S schema-use, M taxonomy |
| H-9 | Autonomic memory loop — `MemoryReviewTrigger`/`MemoryReviewFire` hooks, `MemoryReviewer`, `MemorySystem.add(item)`, typed registry `MemoryTypes.ts`, `MutationTier.ts` A–D, `pending-proposals.jsonl` + Telegram yes/no | Cadence-gated reviewer (turns≥8 ∧ min≥30 ∧ idle≥2) emits typed memory items; a hard-coded ALLOWLIST tier map decides: A=auto-overwrite (2 hot files), B=logged-append, C=propose-only (human yes/no), D=untouchable | Memory mutation is a *permission* problem before a storage problem; tiers are code-reviewed allowlists, not config | **REIMPLEMENT** the governance shape as the memory distill pipeline (§5): agents/reviews may only PROPOSE; `aos memory approve` is the only door to live rows. Cadence = weekly review, not a daemon | L (phased) |
| H-10 | Hot-layer memory caps — `LoadMemory.hook.ts` (48 entries × 256 chars/file) | Always-in-context memory is small, capped, and curated; everything else loads on relevance | Hot/cold split with hard budgets | **REIMPLEMENT** as pack MEMORY policy: `memory pin` flag + per-pack cap; truncation order already exists (pack.py:40 [S2]) | S |
| H-11 | Multi-model researcher agents — `install/agents/{Claude,Codex,Gemini,Grok,Perplexity}Researcher.md`, `Forge.md` (frontmatter: model, permissions allow/deny, maxTurns, persona) | Per-model research personas with pinned models, tool allowlists, disallowedTools | Agent = declarative doc (capabilities + limits), routed by a registry; personas make outputs distinguishable | **VENDOR** (adapted) into ai-company-runtime `agents/` with MIT+provenance header — they are standalone Claude-Code agent files; strip voice/persona fields you don't use. Registry mapping (which agent for which task kind) → REIMPLEMENT in your `agents` table (capabilities_json/trust_level already exist, db.py:146-154 [S2]) | S vendor · M registry |
| H-12 | Pulse dashboard — `install/LIFEOS/PULSE/` (Bun server :31337, launchd services, healthz, SSE, Telegram module) | Live life dashboard; rings for current→ideal; server is also the hook HTTP endpoint | A glanceable "state of the system" surface with freshness | **REJECT as built** (daemon + server violates no-background-jobs/no-server; macOS launchd coupling). Harvest the *information design* only: Home.md gets state-delta counts, freshness stamps, attention-first ordering (→ §7 Obsidian UX) | – |
| H-13 | TheRouter — `TheRouter.hook.ts` (per-prompt LLM classifier: MODE/TIER via Opus; 60s cache; fail-safe) | Route effort per prompt; classifier decides ALGORITHM/NATIVE/MINIMAL | Explicit effort tiers per unit of work | **REJECT** (model calls inside the loop breach "no model APIs"). Harvest the *taxonomy*: an optional task `effort` field to steer pack size/agent choice — defer until real need | – |
| H-14 | Work system event-sourcing — `work-events.jsonl` → locked fold → derived `work.json` snapshot (ARCHITECTURE_SUMMARY [S3]) | All registry writes are field-diff events; snapshot is derived; readers get snapshot+suffix | Append-only events + derived views — independently converged with your events table + generated mirror | **REJECT as new machinery** (you already have it — validation, not a gap). Adopt only the lesson: derived views may rebuild anytime, never emit events (already your D-P0.6 rule, search.py:6-12 [S2]) | – |
| H-15 | `ContextReduction.hook.sh` (rtk command rewriting; their README records a 2026-06-10 silent-corruption incident and a READ-path never-rewrite invariant) | Token-saving command rewrites on the Bash path | Even LifeOS burned itself mutating the execution path — the incident is the lesson | **REJECT** — mutating agent commands is the opposite of coordinate-at-the-artifact-boundary | – |
| H-16 | Voice/Kitty/ElevenLabs/Telegram surfaces (VoiceServer, tab hooks, notify curl) | Ambient TTS + terminal UX + chat approvals | Ambient feedback channels | **REJECT** (cloud deps, out of thesis). The *approval-over-a-simple-channel* idea returns stdlib-shaped in §5 (approve via CLI, surfaced in Home.md) | – |
| H-17 | Integrity family — `InstructionsLoadedHandler` (SHA-256 of loaded instruction files), `ConfigAudit` (settings diff log), `IntegrityCheck` (system-file change detection), `DocIntegrity` | Hash-pin what the agent was told; audit config drift | Instructions and config are attack surface; hash them, diff them, log them | **REIMPLEMENT** as doctor additions: pack-file hash vs `packs.inputs_hash` recorded at build (doctor #12 checks existence only, doctor.py:290-307 [S2]); constitution/CLAUDE.md sha256 recorded as events on `aos constitution` | S–M |
| H-18 | Setup/Update/Uninstall workflows — dry-run first, `existsSync`-guarded copyMissing, backup-before-write, dev-tree refusal, fail-loud, "verify with N evidence classes" | Install as a reversible, evidenced, additive operation | Installers are governed mutations with evidence-gated verification — your own done-gate applied to ops | **REIMPLEMENT** across §7: install/uninstall scripts, `aos backup create/verify/restore`, release checklist with named evidence classes | M |
| H-19 | Skill routing discipline — SKILL.md "USE WHEN…/NOT FOR…" descriptions, workflow routing table | One front door; explicit triggers; explicit non-triggers | Routing text is an interface contract | **REIMPLEMENT** in adapters/*/PROTOCOL.md + README command map (when to use in/task add/handoff/ingest) | S |
| H-20 | Freshness convention — frontmatter `last_updated/last_reviewed` (pai-freshness-v1) on system docs | Every doc self-reports staleness | Staleness is visible, not discovered | **REIMPLEMENT** in generated notes: mirror already stamps updated_at; add `stale_after`/review-by surfacing in Home + weekly review (review.py already computes STALE_MEMORY_DAYS=30, review.py:33 [S2]) | S |

**Vendor rule (non-negotiable 2):** anything vendored from LifeOS (H-11 personas; optionally hook README as design doc) keeps the MIT license text + Miessler copyright + a provenance header (`source: danielmiessler/LifeOS@<sha> path: … license: MIT`). Nothing in the AOS stdlib core is copied — H-1…H-10, H-17…H-20 are idea-reimplementations.

**So what for Agentic OS v2?** LifeOS's durable export is governance patterns, not code: trust-gated installs, tiered mutation approval, evidence-anchored claims, constitution-at-launch, structured identity. Every one lands in AOS as a stdlib feature that *strengthens* the untouchable core.

---

## 3. Weakness audit of agentic-os (RQ2)

Seeded by PDF §13 [S1]; extended by direct code read [S2]. Severity 1–5 (5 = trust/corruption). All file:line refs are agentic-os@main f47dd7b.

| W-# | Finding (evidence) | Severity | Label | Fix direction |
|---|---|---|---|---|
| W-1 | Oversized CLI-typed IDs crash: `parse_id` does unbounded `int()` (ids.py:39) → SQLite bind overflows → generic exit-2 "Internal error" (cli.py:991-999). Ingest already bounds it at 2^63−1 (ingest.py:96-97) — the CLI path never got the same guard | 2 | CONFIRMED (code + §13) | Clamp in `parse_id`; AosError exit 1 with the T-0001 hint |
| W-2 | Newline-tolerant `$` anchors on identifier regexes: SLUG_RE and PROVENANCE_RE use `$` (models.py:21-22) while AGENT_NAME_RE deliberately uses `\Z` with a comment warning that `$` "would admit a trailing newline straight into a filename" (models.py:25-26). Slugs become mirror filenames (obsidian.py:272-273); doctor's Projects/Reviews patterns also use `$` (doctor.py:40,42-47), so the check can't catch what the validator admits | 3 | CONFIRMED anchors; INFERRED exploit path (`$'proj\n'` argv; not executed in this run) | `\Z` everywhere; doctor uses fullmatch; add a regression test with trailing-newline inputs |
| W-3 | `start_run` bypasses the task state machine: only `done` is refused (ops.py:889-894); it force-sets `in_progress` (ops.py:909-912) from ANY status including `inbox`, and permits projectless runs (ops.py:899-900) — violating the documented rules "projectless tasks must be assigned before leaving inbox" and the legal-transition ladder (§6 [S1]; LEGAL_TASK_TRANSITIONS ops.py:351-355) | 3 | CONFIRMED | Require status ∈ {ready, in_progress} and a project (or explicit `--force` with event) |
| W-4 | Done-gate escape hatch is one flag with no reason: `mark_done(no_evidence=True)` (ops.py:1116-1123) logs `done_override` but demands no justification; `done` is also reachable from `inbox` (no status precondition, ops.py:1110-1113) | 2 | CONFIRMED | Require `--reason TEXT` recorded in the override event; keep doctor #4 + review "Attention" surfacing (already exist, doctor.py:123-141, review.py:79-100) |
| W-5 | Ingest has no input bounds: `read_bytes()` on the whole dropfile (ingest.py:192), unbounded evidence-bullet and question loops (ingest.py:115-134,137-143) — a hostile/buggy agent can bloat the ledger or exhaust memory; §13 lists "oversized input" as untested | 3 | CONFIRMED (absence) | Cap file size (e.g. 1 MiB), evidence rows and questions per dropfile; refuse loudly, exit 1 |
| W-6 | Two O(N)-per-operation scans: dropfile dedupe re-reads ALL ingest events and JSON-parses each (ingest.py:172-185); FTS index fully rebuilds whenever ANY event advanced the watermark (search.py:95-124) | 2 | INFERRED (scaling cliff; not benchmarked) | Dedupe: `meta` key-set or an indexed hash column. FTS: rebuild only when searchable tables changed, or incremental upserts |
| W-7 | No restore path: snapshot uses the correct backup API (export.py:56-81) but nothing verifies or restores; no retention policy; §13 confirms "not a full recovery workflow" | 3 | CONFIRMED | `aos backup create/verify/restore` — verify = open + `PRAGMA integrity_check` + schema_version + row counts; restore = to a NEW path + printed switch instructions (never overwrite in place) |
| W-8 | No migration capability: schema_version mismatch is a hard stop (db.py:177-183). Correct for MVP — but memory evolution (§5) needs schema v2, so this is now the critical-path blocker | 3 | CONFIRMED (deliberate; §13) | Stepwise migrations keyed on schema_version, old-DB fixtures, snapshot-before-migrate, rollback doc — BEFORE any v2 schema change |
| W-9 | Windows/WSL Obsidian gap: vault lives on ext4; Windows Obsidian fails on `\\wsl.localhost` watcher (§9 [S1]) — daily UX tax | 2 | CONFIRMED [S1] | `aos sync --export-to WINPATH` read-only mirror (copy-if-changed, same containment rules) |
| W-10 | Secret-scan asymmetry: scanning happens at pack build (pack.py:274-283) and dropfile ingest (ingest.py:153-169,201) — but `evidence add`/`memory add`/`task add --spec` accept secret-shaped text straight into the ledger (ops.py:960-1007,674-765), and `aos sync` then writes it into the Obsidian mirror before any pack build refuses | 3 | CONFIRMED asymmetry | Warn-on-write scan (non-blocking, event-logged) at CLI mutation time; `aos doctor` gains a ledger secret-sweep WARN |
| W-11 | Mirror never prunes: sync never deletes/renames (obsidian.py:243-385), so retired agents/superseded notes accumulate; §13's ambiguous-wikilink edge (agent named like a note stem) worsens with age | 2 | CONFIRMED | `aos sync --prune --dry-run` (deletes only recognized generated stems that no longer exist in the ledger) |
| W-12 | Reviews index lags one sync: index notes derive from the Reviews directory at sync time (obsidian.py:184-189) while `review build` writes review files directly — §13 confirms the lag | 1 | CONFIRMED | review build triggers index-note refresh |
| W-13 | Concurrent-invocation file race: `write_text_lf_if_changed` is read-then-write (utils.py:86-100); two simultaneous `aos` processes (e.g. sync + review) can interleave on the same note. DB itself is safe (WAL + busy_timeout, db.py:158-164) | 1 | INFERRED (solo-dev likelihood low) | Per-workspace lockfile via `os.open(O_CREAT|O_EXCL)` for mirror-writing commands |
| W-14 | Packaging: repo-local `python3 aos.py` only (aos.py:1-9); no `python -m agentic_os`, no console script, no versioned releases beyond git tags — §13 confirms | 2 | CONFIRMED | §7: `__main__.py` (stdlib, zero risk) now; pyproject + `uv tool install` as C-1 |
| W-15 | Docs debt: README is strong on philosophy, thin on troubleshooting (WSL/Obsidian), backup, recovery, command reference — §13 confirms | 2 | CONFIRMED [S1] | §7 docs plan; generate command reference from argparse (stdlib introspection) |
| W-16 | No Python-version gate: declared floor is 3.12 (README) but nothing enforces it — reproduced in this run on Python 3.10.12: `contextlib.chdir` (3.11+) in the shared test setUp (tests/test_cli.py:27) errors 200 of 256 tests with raw AttributeErrors; 56 pass (test_core 42/42 OK). On 3.12 all 256 pass (§2 [S1]). A user on old Python gets noise, not a message | 1 | CONFIRMED (reproduced in sandbox) | One `sys.version_info` check in aos.py with a one-line refusal; ship with U-P1 |

Explicitly checked and NOT weaknesses: git subprocess use is list-form, timeout-bounded, `-`-prefix-refused (ops.py:1010-1091); FTS queries quote every term (search.py:127-133); event/domain rows share one transaction (db.py:218-223, ops.py docstring); dropfile parser names line numbers, never content (ingest.py:50-53); `tree_hash` is test-only (grep: tests/* only); snapshot correctly uses the sqlite backup API, never a raw copy (export.py:5-11,60-64). Live execution in this run: test suite executed in the sandbox (Python 3.10.12) — 56 pass / 200 error, all 200 traced to the single 3.11+ `contextlib.chdir` call above (W-16), consistent with the PDF's 256-OK on 3.12.3.

**So what for Agentic OS v2?** One evening of fixes (W-1…W-5 caps, W-16 one-liner) removes every known way for typed or dropped input to crash, bypass, or bloat the ledger — do this before the hook work multiplies input volume. W-7/W-8 are the professionalization critical path; W-10 closes the one real leak path to the mirror.

---

## 4. Upgrade feature universe (U-#)

Traced to §3 (W-#), §2 (H-#), and PDF §14 (P1–P5). Phase 0 = this week; 1 = 30-day; 2 = 90-day. Risk = chance of harming trust/thesis if done; Cost = S/M/L.

| U-# | Feature | Trace | Phase | Risk | Cost |
|---|---|---|---|---|---|
| U-C1 | Input-hardening batch: id clamp, `\Z` anchors + fullmatch doctor, run-start gate, done-override reason, ingest caps | W-1..W-5 | 0 | Low | S–M |
| U-C2 | `aos backup create/verify/restore` + recovery doc | W-7, H-18, §14-P1 | 0 | Low | M |
| U-C3 | Warn-on-write secret scan + doctor ledger sweep | W-10 | 0 | Low (warn-only) | S |
| U-C4 | `aos sync --export-to` Windows read-only mirror | W-9, §14-P3 | 0–1 | Low | S–M |
| U-H1 | SessionEnd→dropfile hook script + `aos hooks install` (dry-run, diff, backup, idempotent) | H-1..H-3, §14-P4 | 1 | Med (new boundary) — contained: file-writes only | M |
| U-H2 | Dropfile lint + doctor success-without-evidence WARN | H-4 | 1 | Low | S |
| U-H3 | `aos constitution` + launch-line printer (`--append-system-prompt-file` [S5]) | H-5, H-6 | 1 | Low | S |
| U-H4 | Generated CLAUDE.md protocol block per project | H-6, §14-P4 | 1 | Low | S |
| U-M1 | Migration kit (stepwise schema_version, fixtures, snapshot-before-migrate) | W-8 | 1 | Med (get it right once) | M |
| U-M2 | Memory v2 schema: evidence links + status=proposed/live/retired + pin flag (§5) | H-8..H-10, RQ3 | 1–2 | Med | M |
| U-M3 | `aos interview` seeding identity memory | H-7 | 2 | Low | M |
| U-M4 | Distill pipeline: `memory propose` (from dropfiles/reviews) + `memory approve/reject` | H-9, RQ3 | 2 | Med — contained: propose-only | L |
| U-A1 | Autonomy instrumentation: honest-outcome scoring (agent-claimed vs human-validated), gate-violation counters in doctor | RQ4 | 2 | Low | M |
| U-A2 | L4 unlock: hook may run `aos ingest` automatically (per-project flag after test §6 passes) | RQ4, C-2 | 2 | Med-High — gated | M |
| U-P1 | Packaging: `__main__.py` now; pyproject + `uv tool install` under C-1 [S8] | W-14, §14-P1 | 0/1 | Low | S/M |
| U-P2 | Docs suite + argparse-generated command reference | W-15, §14-P1 | 0–1 | Low | M |
| U-P3 | Obsidian pro UX: Home redesign (attention-first, state-delta counts, freshness), graph groups, Minimal setup doc | H-12, H-20, §14-P3 | 1 | Low | M |
| U-P4 | `sync --prune --dry-run` + review-index refresh | W-11, W-12 | 1 | Low (dry-run default) | S |
| U-P5 | Perf: dedupe index + FTS rebuild threshold | W-6 | 2 | Low | S–M |
| U-P6 | Multi-repo dogfood campaign + failure-case log | §13, §14-P1 | 1–2 | None | M (calendar) |
| U-P7 | Agent scorecards from run/evidence data (registry routing) | H-11, §13 "agent analytics" | 2 | Low — wait for data (per §13's own advice) | M |
| U-E1 | Pack power modes / effort tiers: `--mode lite\|standard\|max` driving budget + section set + suggested agent (deterministic, from ledger data — no model calls) | H-13 taxonomy, mid-run directive [S1b] | 1 | Low | M |
| U-E2 | Runtime power modes + formalized degradation matrix: `eco` (defer derived views), `standard`, `deep` (inline integrity + secret sweep), `recovery` (read-only when doctor fails); auto-suggested from ledger signals | H-13, W-6, mid-run directive [S1b] | 1 | Low | M |
| U-E3 | Single-file independence build: stdlib `zipapp` → `aos.pyz` (one portable artifact, zero deps) | W-14, mid-run directive [S1b] | 1 | Low | S |

**So what for Agentic OS v2?** Phase 0 is pure hardening + recoverability (no thesis risk); Phase 1 adds the two highest-leverage LifeOS harvests (hooks-without-autonomy, constitution); Phase 2 is memory + autonomy — deliberately last because both depend on the migration kit and on data only dogfooding produces.

---

## 5. Memory evolution design (RQ3)

**Current state [S2]:** one `memory` table (db.py:121-134) with scope global|project, kind preference|fact|constraint|summary, confidence confirmed|single|inferred|assumed, valid_from/valid_until, superseded_by — already bi-temporal-ish and lifecycle-aware. Gaps: no evidence linkage (source is free text), no proposed/approved distinction (every `memory add` is instantly live in packs via ops.py:94-113), no hot/cold priority, no distillation path from runs/reviews back into memory.

**Layer mapping — mostly already built:**

| Layer | Agentic OS v2 home | Status |
|---|---|---|
| Working | Pack MEMORY section (live rows for the pinned project) | EXISTS (pack.py:164-174); add caps + pins (U-M2) |
| Episodic | runs + evidence + events + dropfiles | EXISTS — your events table IS episodic memory; no new store needed |
| Semantic | `memory` rows, evidence-linked, human-approved | PARTIAL — add links + status (U-M2/U-M4) |
| Procedural | HARD CONSTRAINTS + project conventions_md + adapters/PROTOCOL.md | EXISTS (pack.py:42-59, 245-249); add constitution render (U-H3) |

**Field comparison (CONFIRMED [S3][S6][S7]):** Letta (formerly MemGPT — naming CONFIRMED [S6]) splits core memory (small, always-in-context, agent-editable blocks) from recall (searchable history) and archival (cold store): the lesson AOS should take is the *hard cap on the hot layer* (LifeOS enforces 48×256 chars on its two hot files — same lesson independently [S3]). Zep/Graphiti [S7] builds a bi-temporal knowledge graph (event occurred-at vs ingested-at, validity intervals on every edge; episode/semantic-entity/community subgraphs): the lesson is *bi-temporality and provenance*, and your schema already carries valid_from/valid_until/superseded_by — you need provenance-to-evidence, not a graph engine. LifeOS contributes the governance layer both others lack: typed items + tier-gated mutation + human approval queue (MutationTier/MemoryTypes [S3]). A vector DB remains correctly out of scope: at solo-ledger scale, FTS5 + structured keys beat embeddings, and the no-vector-DB boundary holds.

**Design (all approval-gated, stdlib, schema v2 behind U-M1 migrations):**

1. `memory_evidence(memory_id, evidence_id)` join (or nullable `evidence_id` col to start) — every non-interview memory row can point at the proof that produced it. Doctor: dangling links fail; `confidence=confirmed` with zero evidence links → WARN.
2. `status` column: `proposed | live | retired`. Packs include ONLY `live` (one-line change to the query at ops.py:102-105). `aos memory propose` (used by ingest of a future dropfile MEMORY-PROPOSALS section, and by review builds) creates proposed rows; `aos memory approve M-# [--confidence …]` / `reject M-#` flips them, always with events. This is MutationTier collapsed to your reality: **everything is Tier C** until the autonomy ladder says otherwise; there is no Tier A in AOS v2.
3. `pinned` flag + pack cap: pinned rows always enter packs first; cap total MEMORY chars (Letta/LifeOS hot-layer lesson); truncation order already protects the rest.
4. Distill cadence, human-triggered: `aos review weekly` gains a "Memory candidates" section (repeated handoff questions, decisions older than N days without a memory, run summaries mentioning the same fact twice) — the human approves; nothing writes itself. LifeOS's idle/turn-count daemon cadence is REJECTED; your cadence is the weekly review you already run.
5. Identity layer (H-7/H-8): interview seeds scope=global rows under a small key taxonomy (`identity.*`, `goal.*`, `constraint.*`) with human-chosen confidence and `source=interview-<date>`; TELOS's current-vs-ideal becomes two keys per goal (`goal.G1.current`, `goal.G1.ideal`) so reviews can render the delta.

**So what for Agentic OS v2?** You don't need a memory engine — you need three columns, two commands, and a review section. The schema was already 70% of a Zep-grade lifecycle model; the missing 30% is evidence links and an approval gate, both of which reinforce "evidence proves."

---

## 6. Autonomy ascent plan (RQ4)

**Anchors in code [S2]:** `projects.autonomy_level` INTEGER DEFAULT 0 (db.py:33) and `agents.trust_level` DEFAULT 0 (db.py:152) exist but nothing reads them yet (grep: no consumers) — the ladder has rungs in the schema and no ladder. Ladder semantics below are ASSUMED (defined here, to be ratified as a Decision):

- **L0 observe** — ledger + mirror only. · **L1 propose** — packs built for agents. · **L2 act-externally** — agent edits repo; human validates/commits/records (today's loop). · **L3 assisted write-back** — hooks write dropfiles; HUMAN runs `aos ingest`. · **L4 auto-ingest** — SessionEnd hook runs `aos ingest` itself; human still commits, closes, syncs. · **L5 scoped ledger agency** — agent (via ingest only) may also move task status ready↔in_progress and start/end runs. `done`, git staging/commit/push, memory approval, and schema changes remain human FOREVER (untouchable core).

**L4 prerequisites:** U-C1 (W-3/W-5 fixed), U-H1 hooks shipped, U-H2 lint live, W-6 dedupe index (volume rises), backup verified restore (U-C2) — because auto-writes need proven undo.

**L4 guardrails (LifeOS-harvested):** allowlist not denylist (H-9) — the hook may invoke exactly one command (`aos ingest <path>`); rate cap per session (TaskGovernance lesson: their 50-tasks/session cap [S3]) — e.g. ≤3 dropfiles/session, ≤200 evidence rows/day; kill switch = per-project `autonomy_level` column finally consumed; every auto-ingest event carries `via: hook` for audit.

**L4 unlock test (measurable, falsifiable):** over the trailing **30 manually-ingested dropfiles across ≥2 projects**: 100% parsed-or-refused-cleanly (zero exit-2), 0 secret-scan misses found by the post-hoc doctor sweep (U-C3), 0 dedupe failures, and doctor 17/17 after every ingest+sync. Any single miss resets the window. Evidence: the ledger itself (events where action=dropfile_ingest), counted by a doctor subcommand — the test is auditable from the ledger, per "evidence proves."

**L5 prerequisites:** ≥60 days at L4; honest-outcome instrumentation (U-A1) comparing agent-claimed run outcome vs human validation.

**L5 unlock test:** trailing 50 runs: ≥95% outcome agreement, 0 gate violations (attempted done/commit/memory writes — parser refuses & counts them), 0 L4-guardrail trips; plus a tabletop rollback drill: restore yesterday's backup and replay today's events doc — proving compensating-event recovery works before granting status agency.

**Guardrail constant at every level:** corrections are new events, never rewrites (events.py contract); autonomy expands what may be *appended*, never what may be *mutated*.

**So what for Agentic OS v2?** The ladder becomes real the day `autonomy_level` gets its first reader. L4 is a contained, measurable step (one command, one flag, one test); L5 is deliberately expensive and stays below the human-controlled git/done line.

---

## 7. Professionalization + reconciliation ledger (RQ5)

### 7.1 Core power architecture — adaptive power modes (mid-run directive [S1b])

Directive received during the run: make Agentic OS "unstoppable, independent, powerful, efficient, with different power modes adaptively." Reconciled against the non-negotiables: adaptivity must be **deterministic** (no model calls in the loop — that is why H-13/TheRouter was rejected as-built), and independence must deepen local-first, not add daemons. The design, all stdlib:

**Axis 1 — Runtime power modes (U-E2).** A per-invocation profile, `aos --mode X` with an auto-suggest default:

| Mode | Behavior | Precedent already in the code [S2] |
|---|---|---|
| `eco` | Skip mirror sync + FTS refresh (derived views rebuild lazily on demand); terse output — for scripting/batch | Derived views are already allowed to rebuild anytime and emit no events (search.py:6-12) |
| `standard` | Today's behavior | — |
| `deep` | Inline `PRAGMA integrity_check`, ledger secret sweep, link check after every mutation — pre-release / post-crash posture | doctor #16 (doctor.py:385-396) run inline |
| `recovery` | Read-only command set permitted even when doctor fails; every degraded subsystem states its fallback | LIKE fallback when FTS5 is absent (search.py:30-43, 180-197); git degradation notes (ops.py:850-882) |

The "adaptive" part is a deterministic suggestion rule, not magic: events-since-last-index > N → suggest `eco` + explicit `aos reindex`; last doctor run failed → force `recovery` unless overridden; DB > size threshold or schema mismatch → refuse with the exact next command. Doctor gains a "power state" line reporting which subsystems are degraded. This makes AOS *unstoppable* in the literal sense: there is a documented, tested behavior for every broken dependency (no git, no FTS5, corrupt mirror, failed doctor) instead of an exit-2.

**Axis 2 — Agent effort tiers / pack power modes (U-E1).** LifeOS routes effort per prompt with an LLM classifier and an EFFORT_MODEL level→model map (E1–E5 → haiku…fable) [S3]; AOS reimplements the *taxonomy* as data, not inference: `pack build --mode lite|standard|max` (default derived deterministically from task priority + kind + prior-run count). `lite` = GOAL/ACCEPTANCE/CONSTRAINTS/WRITE-BACK only, small budget — cheap retry loops; `max` = full DECISIONS/MEMORY/PRIOR-RUNS, larger budget, and the pack's suggested-agent line chosen from the agent registry by capabilities + trust_level (a table lookup — H-11's registry made useful). Efficiency is measured, not vibes: packs already record token_estimate (db.py:136-144), so reviews can report tokens-per-completed-task by mode.

**Axis 3 — Independence (U-E3, U-C2).** One-artifact distribution via stdlib `zipapp` (`aos.pyz` runs anywhere with Python 3.12, zero installs), plus verified backup/restore = the system survives machine loss with two files (aos.pyz + latest snapshot). INFERRED: zipapp is sufficient for a stdlib-only package; no compiled deps exist to break it.

**So what for Agentic OS v2?** "Power" lands as three governed axes — degrade gracefully (never die), spend context deliberately (never overpay), travel as one file (never depend) — all without a single model call or daemon inside the ledger.

### 7.2 Packaging, backup, migrations, docs

- **Packaging (U-P1, W-14):** now — add `agentic_os/__main__.py` so `python -m agentic_os` works (stdlib, zero risk) + `aos.pyz` zipapp build script; under C-1 — `pyproject.toml` with zero runtime deps and `uv tool install` as the documented path (uv is the consolidated 2026 toolchain — CONFIRMED [S8]). Runtime stays stdlib either way.
- **Backup/restore (U-C2, W-7):** `aos backup create` (existing backup-API snapshot + manifest event), `verify` (open copy, `PRAGMA integrity_check`, schema_version, row-count deltas vs manifest), `restore` (writes to a NEW path, prints the exact mv/switch commands — restore itself never overwrites a live ledger; the human does the final move, mirroring human-controlled git). Retention: keep last N + one per week; documented.
- **Migrations (U-M1, W-8):** stepwise `schema_version` 1→2→… functions, each wrapped in one transaction, each preceded by an automatic snapshot; fixture DBs for every historical version live in tests/; a migration emits a `system/migrate` event with from/to; rollback = documented restore of the pre-migration snapshot. No memory-v2 schema work (U-M2) until this exists — sequencing is the whole point.
- **Docs (U-P2, W-15):** README keeps philosophy; add QUICKSTART.md (10 commands), WORKFLOW.md (the §8 Claude loop verbatim from the blueprint), TROUBLESHOOTING.md (WSL/Obsidian watcher, FTS5-less Python, locked DB), RECOVERY.md, and a command reference generated from the argparse tree (stdlib introspection — parser already centralizes help strings, cli.py:700-975).
- **Obsidian pro UX (U-P3, §14-P3):** Home.md reordered attention-first (needs-evidence, open handoffs, stale memory at top — data already computed in review.py:79-111); per-entity freshness stamps (H-20); Windows read-only export (U-C4) with the §14 name `sync --export-to`; graph groups + Minimal theme doc lifted from blueprint Appendix E (ADOPTED as-is).

### 7.3 Reconciliation ledger — every §14 item + 7-day roadmap [S1]

| §14 item | Verdict | Where/why |
|---|---|---|
| P1 Professionalization blueprint | **ADOPTED** | This report §7; U-C2/U-M1/U-P1/U-P2 |
| P2 Adversarial code review ("top 20 ways to lose trust") | **ADOPTED (scoped)** | §3 delivers 15 W-# with file:line; the remaining adversarial classes §13 names (symlinks, Unicode, SQLite corruption injection) → U-C1 test list |
| P3 Obsidian professional UX | **ADOPTED** | §7.2 UX bullet + U-C4/U-P3 |
| P4 Claude Code hooks without autonomy | **ADOPTED** | H-1..H-4 → U-H1/U-H2; C-2 governs the L4 upgrade; hook events + flags CONFIRMED against official docs [S4][S5] |
| P5 Seven-day shippable roadmap | **SUPERSEDED (reordered)** | Original order: docs→export→backup→security→hook→packaging→polish. Superseded because security fixes (W-1..W-5) are cheapest-first and de-risk everything after; docs move late so they document final behavior. See §9 Day plan |
| 7-day Day 1 docs | SUPERSEDED → Day 6 | Document stabilized behavior once |
| Day 2 Windows export | ADOPTED → Day 4 | After hardening; unchanged scope |
| Day 3 backup/restore | ADOPTED → Day 2-3 | Promoted — recoverability before new surfaces |
| Day 4 security hardening | SUPERSEDED → Day 1 | W-1/W-2/W-3/W-4/W-5 are one evening total |
| Day 5 Claude hook prototype | ADOPTED → Day 5 (design+script), auto-ingest deferred to C-2/L4 | Keeps "without autonomy" honest |
| Day 6 packaging | ADOPTED (split) | `__main__.py`+zipapp Day 6; pyproject/uv waits for C-1 approval |
| Day 7 release polish | ADOPTED | Tag v0.2.0 + release checklist with evidence classes (H-18) |

**So what for Agentic OS v2?** Every §14 intent survives; only the order changes, and each reorder has a stated reason — the reconciliation is itself an auditable decision list ready for `aos decision add`.

---

## 8. Constraint-evolution proposals (C-#)

Untouchable core (SQLite truth · evidence-gated done · human git · append-only · ladder-gated autonomy) — untouched by all of the below. Each C-# is approval-gated with trigger, risk, containment.

**C-1 — Relax "stdlib-only" for BUILD/DISTRIBUTION tooling only.** Trigger: first release intended for a second machine/user. Change: `pyproject.toml` + uv as dev/packaging tools; runtime imports stay 100% stdlib (CI check enforces it). Risk: low — toolchain, not runtime. Containment: a doctor/CI assertion that `agentic_os/` imports only stdlib; zipapp path remains the no-tools fallback.

**C-2 — Relax "no hooks/no auto-ingest" to "hooks may write files at L3; hook may run `aos ingest` at L4".** Trigger: L4 unlock test (§6) passes on 30 trailing manual ingests. Risk: medium — prompt-injected agents produce hostile dropfiles. Containment: dropfiles are already adversarial-by-design inputs (ingest.py header contract); W-5 caps land first; hook is allowlisted to the single ingest command; rate caps; per-project autonomy_level flag; kill switch = flag to 0; every auto event tagged `via: hook`.

**C-3 — DEFER (not proposed now): read-only localhost viewer (Pulse-lite, stdlib http.server).** Trigger to reconsider: Windows export (U-C4) + Obsidian UX (U-P3) demonstrably fail the daily-review need for 30 days. Risk: violates no-server spirit; a daemon invites scope creep. Containment if ever done: read-only, localhost-only, serves the existing mirror directory, no write endpoints. Recommendation today: NO.

**C-4 — DEFER: MCP read-only endpoint.** Trigger: ≥2 external agents need programmatic ledger reads that packs cannot serve. Containment sketch: MCP server reads a snapshot copy, never aos.db live. Recommendation today: NO — packs + dropfiles cover the loop.

**So what for Agentic OS v2?** Two relaxations earn their keep (C-1 distribution, C-2 the entire hooks payoff); two stay deferred with explicit reconsideration triggers, keeping the boundary story crisp.

---

## 9. Roadmap — 7 / 30 / 90 days (solo dev, evenings; ~5 focused evenings/week ASSUMED)

**7-day (ship v0.2.0):**
- Day 1 — U-C1: id clamp (ids.py), `\Z` anchors + doctor fullmatch, run-start gate, done `--reason`, ingest caps. Tests for each (trailing-newline slug, 2^70 id, inbox run-start, oversized dropfile).
- Day 2–3 — U-C2 backup create/verify/restore + RECOVERY.md; U-C3 warn-on-write secret scan + doctor sweep.
- Day 4 — U-C4 `sync --export-to` Windows mirror + U-P4 prune dry-run + review-index refresh.
- Day 5 — U-H1 design half: SessionEnd hook script (writes dropfile only) + `aos hooks install --dry-run` printing the exact settings diff; PROTOCOL.md updated. No auto-ingest.
- Day 6 — U-P1 `__main__.py` + zipapp build; U-P2 QUICKSTART + TROUBLESHOOTING.
- Day 7 — release checklist w/ evidence classes; tag `milestone/v0.2-hardened`; dogfood ledger entries closing the week.
- **Capacity cut line.** Below it (slip without guilt): U-H2 lint, U-P3 Home redesign, U-E3 polish.

**30-day (v0.3):** U-M1 migration kit → U-M2 memory schema v2 (evidence links, status, pin) → U-H3 constitution + launch line → U-H4 CLAUDE.md block → U-E1/U-E2 power modes (pack tiers first) → U-P3 Obsidian UX → U-P6 dogfood on 2 more real repos (failure log as tasks). Gate: C-1 decision recorded before pyproject lands.

**90-day (v0.4):** U-M3 interview → U-M4 propose/approve distill loop (weekly-review candidates) → U-A1 honest-outcome instrumentation → run the L4 unlock window (30 trailing manual ingests) → if passed, C-2 decision + U-A2 auto-ingest behind per-project flag → U-P5 perf pass → U-P7 agent scorecards only if ≥50 runs of data exist. Review C-3/C-4 triggers; expect NO.

**So what for Agentic OS v2?** Week one is entirely defensive and finishes with a releasable artifact; every later phase consumes something the previous phase proved (migrations→memory, hooks→L4 data, dogfood→scorecards).

---

## 10. Final recommendation

**Top-10 build-first (in order):** 1) U-C1 hardening batch (W-1..W-5) · 2) U-C2 backup/verify/restore · 3) U-C3 secret warn-on-write · 4) U-C4 Windows export · 5) U-H1 SessionEnd dropfile hook + trust-gated installer · 6) U-H2 success-claim lint · 7) U-P1 `__main__.py` + zipapp · 8) U-M1 migration kit · 9) U-M2 memory v2 columns · 10) U-H3 constitution + launch line.

**Top-10 defer, each with its trigger:** U-A2 auto-ingest (L4 test passes) · U-M4 distill pipeline (memory v2 live 30 days) · U-M3 interview (after memory v2) · U-P7 scorecards (≥50 runs) · U-E1 max-tier routing via registry (≥3 registered agents used in anger) · U-P5 perf (events >20k or ingest >100) · C-1 pyproject/uv (second-machine distribution) · C-3 Pulse-lite (UX failure evidence after U-P3) · C-4 MCP read (≥2 programmatic consumers) · task `effort` field (only with U-E1 data).

**THE NEXT BUILD CONTRACT (seed, gated-contract style):**

```
AOS V0.2 HARDENING CONTRACT — seed (2026-07-08)
WINS OVER: two-week plan; ties broken by this contract, then DECISIONS.md.
P0 GATE (all before any edit): clean tree on main@f47dd7b; 256 tests OK;
  doctor 17/17; dogfood task+run opened in the ledger for this build.
SCOPE (exactly): U-C1 {ids.parse_id clamp → AosError exit 1;
  SLUG_RE/PROVENANCE_RE + doctor patterns → \Z/fullmatch;
  start_run requires status∈{ready,in_progress} AND project;
  done --no-evidence requires --reason, recorded in done_override payload;
  ingest caps: ≤1 MiB file, ≤200 evidence, ≤100 questions — refuse exit 1}
  + U-C2 {backup create/verify/restore per report §7.2 — restore NEVER
  overwrites in place} + U-C3 {warn-only secret scan on evidence/memory/task
  writes, event-logged; doctor WARN sweep}.
NON-NEGOTIABLES: stdlib only; unittest only; every mutation = domain row +
  event, one transaction; no new schema version; no behavior change outside
  SCOPE; corrections as new events, never rewrites.
EVIDENCE-GATED DONE: each SCOPE item lands with (a) failing-then-passing
  test named in the commit, (b) doctor still 17/17 (+ new WARNs allowed),
  (c) aos evidence git <task> HEAD --claim per item.
NEW TESTS (minimum): trailing-newline slug refused; 2^70 task id → exit 1
  one-liner; inbox start_run refused; projectless start_run refused;
  oversized dropfile refused with line-free message; backup verify detects
  a bit-flipped copy; restore path never equals live path.
EXIT: tests ≥ 256+N OK; doctor pass; README delta note; tag
  milestone/v0.2-hardened; aos done only via evidence git; sync; doctor.
STOP RULES: any schema temptation → write decision, defer to U-M1;
  any hook temptation → Day 5 only, file-writes only.
```

**Paste-ready ledger block** (CLI syntax verified against cli.py:709-975 [S2] — `task add` needs `-p`; `decision add` uses `--decision`; `memory add` needs scope/kind/key/value/source/confidence):

```bash
cd ~/Projects/agentic-os
python3 aos.py in "Read aos-v2-report.md sections 1-4 and ratify verdicts"
python3 aos.py task add "U-C1 input hardening: id clamp, \\Z anchors, run-start gate, done --reason, ingest caps" -p agentic-os --kind code --priority 1 --accept "5 new failing-then-passing tests per report §10; doctor 17/17; commit evidence per item"
python3 aos.py task add "U-C2 backup create/verify/restore + RECOVERY.md" -p agentic-os --kind code --priority 1 --accept "verify detects corrupted copy; restore writes to new path only; docs show full drill"
python3 aos.py task add "U-C3 warn-on-write secret scan + doctor ledger sweep" -p agentic-os --kind code --priority 2 --accept "warn never blocks; event logged; doctor WARN lists offending rows by id only"
python3 aos.py task add "U-C4 sync --export-to Windows read-only mirror" -p agentic-os --kind code --priority 2 --accept "copy-if-changed; contained; documented in TROUBLESHOOTING.md"
python3 aos.py task add "U-H1 SessionEnd dropfile hook + aos hooks install --dry-run" -p agentic-os --kind code --priority 2 --accept "hook writes dropfile only; installer prints exact settings diff and backs up settings.json; no auto-ingest"
python3 aos.py task add "U-P1 python -m agentic_os + zipapp aos.pyz build" -p agentic-os --kind code --priority 3 --accept "aos.pyz runs init/status/doctor on a clean machine with stock Python 3.12"
python3 aos.py task add "U-M1 migration kit before any schema v2" -p agentic-os --kind code --priority 2 --accept "v1 fixture DB migrates forward under test; auto-snapshot precedes migrate; rollback documented"
python3 aos.py task add "U-E2 power modes: eco/standard/deep/recovery + degradation matrix in doctor" -p agentic-os --kind code --priority 3 --accept "each mode tested; doctor prints power state; recovery permits read-only set when checks fail"
python3 aos.py decision add "LifeOS harvest verdicts v1" -p agentic-os --decision "Adopt aos-v2-report.md §2: 3 VENDOR (researcher personas to harness layer, MIT+provenance), 12 REIMPLEMENT, 6 REJECT. Vendored files keep license+copyright+provenance header; stdlib core receives ideas only, never code." --alternatives "Install LifeOS wholesale (rejected: Bun/server/daemon coupling, thesis breach)"
python3 aos.py decision add "Roadmap reorder of PDF §14 seven-day plan" -p agentic-os --decision "Security hardening moves to Day 1 (cheapest, de-risks all later work); docs move to Day 6 (document stabilized behavior). All §14 intents retained per report §7.3 ledger." 
python3 aos.py memory add --scope global --kind constraint --key "untouchable-core" --value "SQLite as truth; evidence-gated done; human-controlled git; append-only ledger; autonomy only via ladder unlock tests. Relaxations only as approval-gated C-# proposals." --source "aos-v2-report.md §8" --confidence confirmed
python3 aos.py memory add --scope global --kind fact --key "harvest.lifeos.license" --value "LifeOS is MIT (danielmiessler/LifeOS); vendoring requires license+copyright+provenance header; core reimplements ideas only." --source "aos-v2-sources.md S3/S9" --confidence confirmed
python3 aos.py memory add --scope project -p agentic-os --kind constraint --key "autonomy.L4.unlock" --value "30 trailing manual dropfile ingests across ≥2 projects: 100% clean parse-or-refuse, 0 secret misses, 0 dedupe failures, doctor pass after each. Any miss resets the window." --source "aos-v2-report.md §6" --confidence confirmed
python3 aos.py sync
python3 aos.py doctor
```

**So what for Agentic OS v2?** You can execute today: run the paste block, start the U-C1 task, and the first LifeOS harvest (trust-gated hooks, constitution, tiered memory approval) arrives without moving a single boundary stone.

---
*Self-score and verification walk: see aos-v2-state.md. Sources: aos-v2-sources.md.*

