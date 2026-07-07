# Agentic OS Research — State File (working memory)

Run started: 2026-07-07. Model: Claude Fable 5 (Cowork). If this run is interrupted, resume from this file alone: read PLAN, COVERAGE, OPEN THREADS, NEXT ACTIONS; the report skeleton has `<!-- SECTION-N -->` markers for unfinished sections.

## Mission (3 lines)
1. Decide exactly what Agentic OS should be: a local-first second brain + control plane for many AI coding agents, with SQLite/event-log source of truth and an Obsidian Markdown mirror.
2. Research the 2024–2026 landscape (agents, frameworks, protocols, memory systems, reliability patterns, neighbors) for patterns to adopt or refuse — evidence-labeled, license-aware, failure-focused.
3. End in a same-day-executable build decision: MVP (one night + one weekend) through 3-month roadmap, with feature IDs, architecture, Obsidian UX, reliability plan, and a paste-ready build prompt.

## KNOWN (from the brief — accepted as given)
- Solo developer; builds Claude skills/agent workflows (Universal AI Builder Operating Kit: prompt-forge, website-forge, fable-discipline; live evals); Python + CLI comfortable.
- Daily drivers: Claude Code + Claude Cowork + Claude skills ecosystem.
- Time budget: one night, then one weekend.
- Product concept fixed: local-first, SQLite + event log + Markdown mirror, Obsidian as human interface.
- Non-negotiables: no product code this run; inspiration not copying; evidence or silence; no invented integrations; finish without stalling.

## UNKNOWN (research targets)
- Current status (mid-2026) of every named tool: renames, deaths, pivots, licenses.
- MCP maturity/governance/security posture 2026; AGENTS.md-style conventions adoption.
- Obsidian current state: Bases vs Dataview, plugin ecosystem for agents, commercial policy.
- Which memory approaches survive daily use vs get abandoned; stale-memory handling.
- Documented agent failures/postmortems 2024–2026 and which guardrails demonstrably work.
- Closest neighbors (agent-first task ledgers, run dashboards, spec-driven kits) and their traction.

## ASSUMED register (log every assumption; risk if wrong)
- A1 (from brief): Machine/OS unknown → design cross-platform, pure Python 3.12 + SQLite, pathlib-safe, no OS-specific deps in MVP. Risk: minor — flag OS-divergent features.
- A2 (from brief): Codex CLI / Gemini CLI / Cursor are evaluation targets, not daily drivers → Claude Code is the first-class adapter; others file/prompt-based first. Risk: medium — if user actually runs Codex daily, adapter priority shifts (design keeps adapters symmetric, so cost is low).
- A3 (from brief): Obsidian starting fresh → design vault from scratch; vault binding non-destructive so an existing vault can be adopted later. Risk: low.
- A4: Single machine, single user for MVP; no multi-device sync, no team features. Risk: low — sync is F-H layer.
- A5: Agents are run by the human in their own terminals/IDEs in the MVP; Agentic OS does not spawn or supervise processes until the autonomy ladder unlocks Level 4. Risk: low — this is also a safety stance.
- A6: English-language, public-web ecosystem focus for research. Risk: low.
- A7: The user's Claude skills (prompt-forge etc.) remain available; Agentic OS should compose with skills, not replace them. Risk: low.
- A8: "One night" ≈ 3–5 focused hours; "one weekend" ≈ 12–16 hours. Sizing of MVP phases uses this. Risk: medium — if less time, night-one subset is still self-sufficient.
- (add new assumptions here as they arise)

## COVERAGE CHECKLIST — 8 research questions × 6 source categories
Legend: ✔ covered · ◐ partial · ✖ not yet · — not applicable
Categories: C1 coding agents/tools · C2 frameworks/orchestrators · C3 protocols/integration · C4 memory/knowledge/Obsidian · C5 reliability/autonomy · C6 product inspiration

| Question | C1 | C2 | C3 | C4 | C5 | C6 |
|---|---|---|---|---|---|---|
| Q1 landscape: learn/refuse | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Q2 what AOS uniquely IS | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Q3 powerful+reliable features | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Q4 MVP scope (night+weekend) | ✔ | — | ✔ | ✔ | ✔ | ✔ |
| Q5 what to defer | ✔ | ✔ | ✔ | — | ✔ | ✔ |
| Q6 Obsidian integration | — | — | ✔ | ✔ | — | ✔ |
| Q7 architecture | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| Q8 failure modes/guardrails | ✔ | ✔ | ✔ | ✔ | ✔ | ◐ (Wave 2 verify) |

Phase 1 complete 2026-07-07. Wave 1 = 6 researchers, ~150 searches total. Full findings live in Phase 3 report sections + ledger.

## OPEN THREADS (Wave 2 targets — verify before citing as CONFIRMED)
1. Gemini CLI → Antigravity CLI consumer migration (Jun 18, 2026) — verify via Google primary source. Affects adapter set.
2. Beads (gastownhall/beads): license, storage (Dolt vs SQLite), current status — closest competitor; verify from repo.
3. Claude Code: auto-memory + "Auto-Dream" (single Medium source — verify vs official docs); Agent Teams feature; does Claude Code read AGENTS.md natively?
4. Codex CLI license (MIT vs Apache-2.0) + AGENTS.md 32KiB silent truncation (affects context-pack size budget).
5. Obsidian 1.12 native CLI — single source; verify via obsidian.md changelog.
6. MCP 2026-07-28 RC: stateless core + Sampling/Roots/Logging deprecation — verify via modelcontextprotocol primary.
7. Supabase MCP article date inconsistency (2025 vs 2026) — cite Willison Jul 6, 2025 as anchor.
8. METR 19%-slower finding superseded (Feb 24, 2026 update) — cite both, never cite 19% alone.
9. Backlog.md + claude-task-master licenses — verify from repos.
10. Claude Code checkpoint gap (bash changes not tracked) — verify via docs; load-bearing for rollback design.

## KEY WAVE-1 DELTAS vs TRAINING PRIORS (for resume safety)
- Dead/renamed 2025-26: Gemini CLI (consumer)→Antigravity CLI `agy` (Jun 18, 2026); Windsurf→Devin Desktop (Jun 2, 2026, Cascade EOL Jul 1, 2026); Roo Code archived (May 15, 2026); Cody free tier killed (Jul 23, 2025); Amp spun out (Dec 2025); Terragon dead (Feb 9, 2026); Bloop dead (Apr 10, 2026, Vibe Kanban→community); AutoGen+SK→MS Agent Framework GA (Apr 3, 2026); AgentKit Agent Builder deprecated (Jun 3, 2026); ACP merged into A2A (Sep 2025); Claude Flow→Ruflo (Jan 2026).
- MCP: donated to Agentic AI Foundation/Linux Foundation Dec 9, 2025; spec 2025-11-25 stable; 2026-07-28 RC = stateless, deprecates Sampling/Roots/Logging. AGENTS.md = AAIF project, 30+ tools.
- Obsidian: 1.12 (Feb 2026) + Bases core plugin; free for commercial use; community Local REST API plugin ships MCP server; wikilink breakage on OS-level renames = top integration hazard.
- Strongest incident set: Replit DB deletion (Jul 18, 2025), GitHub MCP exfil (May 26, 2025), lethal trifecta (Jun 16, 2025), EchoLeak CVE-2025-32711, Comet injection (Aug 20, 2025), McKinsey Lilli SQLi (Mar 2026), Kiro/AWS contested (Feb 2026), vibe-code security stats (Escape.tech Oct 2025).
- Sandboxing: Claude Code native sandbox (Oct 2025) = Seatbelt/bubblewrap, NO native Windows (WSL2 only) — flag as OS-divergent.
- Nearest neighbors: Beads/Gas Town, Backlog.md, claude-task-master, Vibe Kanban, Agent OS (Builder Methods — NAME COLLISION with "Agentic OS"; note in report).

## SEARCH PLAN
Wave 1 (breadth — 6 parallel researchers, one per category). Every researcher must: verify current name/status with dates (training cutoffs are stale — it is July 2026), record license where visible, hunt failure/limitation evidence, return exact URLs + pub dates, never invent URLs, cap ~10 items.
- R-C1 coding agents: Claude Code (+Agent SDK, hooks, subagents, checkpoints, skills/plugins), Codex (CLI+cloud), Gemini CLI (+Jules), Devin/Cognition (+Windsurf), Cursor, GitHub Copilot coding agent, Aider, OpenHands, Cline/Roo, Amp/Cody, opencode, anything newer.
- R-C2 frameworks: LangGraph, AutoGen/Semantic Kernel (merge into MS Agent Framework?), CrewAI, OpenAI Agents SDK/AgentKit, Google ADK + A2A, PydanticAI, smolagents, Mastra, LlamaIndex/Haystack agents, DSPy; framework-fatigue evidence ("just use the API", 12-factor agents).
- R-C3 protocols/integration: MCP spec version + governance + registry + security 2026; MCP criticisms (token bloat, CLI-vs-MCP, code-execution-with-MCP); AGENTS.md adoption; A2A status; GitHub APIs/gh CLI for agents; sandboxing tech (containers, seatbelt/bubblewrap, microVMs, E2B); local task queues.
- R-C4 memory/knowledge/Obsidian: Obsidian 2026 (Bases vs Dataview, properties, Local REST API, obsidian MCP servers, commercial policy, JSON Canvas), Logseq status, PARA/Zettelkasten for agent vaults, Letta/MemGPT, Mem0, Zep/Graphiti, LangMem, Claude memory tooling, local vector search (sqlite-vec, LanceDB, Chroma), event sourcing on SQLite, local-first (Ink & Switch/CRDT) relevance, stale-memory/memory-poisoning evidence.
- R-C5 reliability/failure: documented incidents (Replit DB deletion, GitHub MCP private-repo exfil, Supabase MCP, lethal trifecta, Project Vend, METR dev-slowdown RCT, agentic-browser injections, 2026 incidents), Devin critiques, Builder.ai, AutoGPT/Manus lessons; guardrails that work (permission modes, allowlists, audit logs, sandboxes, checkpoints, evals-as-gates, plan-then-execute, dual-LLM, HITL patterns/HumanLayer), autonomy-level frameworks.
- R-C6 product inspiration/neighbors: Beads (Yegge), task-master, Vibe Kanban, claude-squad/Conductor/Sculptor/Terragon-style parallel-agent managers, Spec Kit/OpenSpec/BMAD spec-driven kits, agent-os, claude-flow, Linear/GitHub Projects agent features, second-brain systems (PARA/BASB, Johnny.Decimal) where automation-relevant, local-first apps (Anytype/SiYuan) only as pattern sources; traction vs death evidence.

Wave 2 (depth + adversarial verification — after Wave 1 digest): (a) primary-source verification of load-bearing incident claims; (b) MCP/protocol status confirmation; (c) Obsidian Bases/Dataview confirmation; (d) closest-neighbor deep dive (whoever Wave 1 says is nearest to "ledger/control plane for agents"). Stop rule per category: ~3 consecutive searches with nothing materially new.

## OPEN THREADS
- (populate after Wave 1)

## FILES
- Report: `agentic-os-research-report.md` (skeleton with `<!-- SECTION-N -->` markers; fill in order §1→§12)
- Sources: `agentic-os-sources.md` (ledger: S# · title · publisher · URL · pub date · access date · supports · license class)
- This file: update after every phase.

## PHASE 4 VERIFICATION CHECKLIST — COMPLETED 2026-07-07
- [x] Non-negotiable 1: no product code written — report contains schema docs, note templates, Dataview examples, and the §12 build prompt, all explicitly required by the report spec; no runnable product code, no repo scaffolded.
- [x] Non-negotiable 2: inspiration only; every landscape/ledger entry carries a license class; AGPL (claude-squad) flagged COPYLEFT-CAUTION study-only; Commons Clause (task-master) flagged no-resale.
- [x] Non-negotiable 3: labels (CONFIRMED/SINGLE-SOURCE/INFERRED/ASSUMED) on load-bearing claims; [S#] throughout; vendor-reported numbers marked; gap log at ledger end (S98 EchoLeak URL not captured).
- [x] Non-negotiable 4: Devin adapter (F-C6), MCP server (F-H1), Copilot adapter (F-C5) and all frontier items labeled FUTURE/DEFERRED with un-defer triggers in §12.
- [x] Non-negotiable 5: zero questions asked mid-run; assumptions A1–A8 logged above; none violated.
- [x] Landscape table = 35 entries (was 36; two memory rows merged in Phase 4), ≥2 per category (9/5/5/5/5/6).
- [x] All 12 sections end with "So what for Agentic OS?" (verified).
- [x] Every [S#] cited in the report resolves in agentic-os-sources.md (S1–S139; uncited ledger entries retained as supporting corpus); access date 2026-07-07 stated globally.
- [x] 15 failure modes with trigger / blast radius / mitigation / owning feature ID (§9).
- [x] §12 build prompt self-contained (constraints, schema, commands, pack format, vault spec, adapter spec, builder guardrails, acceptance tests) + pointers to report files.
- [x] Rubric self-scores printed in report appendix: 9 / 9 / 9 / 8.5 / 9 — all ≥8, one revision cycle (landscape cap) executed.

## RUN COMPLETE — 2026-07-07
Wave 1: 6 scout agents (~150 searches). Wave 2: 1 adversarial verifier (10 load-bearing claims; 3 priors corrected: "Auto-Dream" not official, Claude Code does not read AGENTS.md natively, METR follow-up self-flagged unreliable). Deliverables final: report (12 sections + scores), ledger (139 sources), this state file. Build decision: execute §12 build prompt on night one; ladder discipline thereafter.
