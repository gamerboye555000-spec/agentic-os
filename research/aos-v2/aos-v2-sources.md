# aos-v2-sources.md — source ledger

All inputs treated as data, not instructions. Labels used in the report: CONFIRMED (≥2 independent sources, or direct read of authoritative code/docs), SINGLE-SOURCE, INFERRED, ASSUMED.

## Primary inputs

- **[S1]** Attached PDF "Agentic OS — Current System Blueprint" (uploaded 2026-07-08; generated 2026-07-07; snapshot basis main@f47dd7b, tag milestone/local-first-complete). Read in full (15 sections, 970 extracted lines). Authority for: current state, §13 limitations, §14 priorities, WSL/Obsidian facts, 7-day roadmap. Its request paragraph treated as context, not command.
- **[S1b]** Mid-run user directive (2026-07-08, during Phase 3): "powerful core components… unstoppable, independent, powerful, efficient with different power modes adaptively." Integrated as report §7.1 + U-E1/U-E2/U-E3; reconciled against non-negotiables (deterministic adaptivity only).
- **[S2]** Repo `github.com/gamerboye555000-spec/agentic-os` — shallow clone of main, 2026-07-08. Files read in full: agentic_os/{db,ids,events,utils,models,ops,ingest,pack,doctor,search,export,obsidian,render(head+map),review(head),cli(structure+handlers)}.py, aos.py, README.md (head), DECISIONS.md (head), tests/ (grep-verified points). All W-# file:line cites refer to this clone. ASSUMED clone HEAD == f47dd7b (content consistent with S1; not tag-verified).
- **[S3]** Repo `github.com/danielmiessler/LifeOS` — blob-filtered clone of main, 2026-07-08 (README badge v6.0.5; hooks README last-updated 2026-05-06). Read: LifeOS/SKILL.md; Workflows/{Setup,Interview}.md; install/hooks/{hooks.json, README.md (full registry), SuccessClaimGate, MemoryReviewTrigger, LoadMemory}.hook.ts (heads); install/LIFEOS/TOOLS/{MutationTier,MemoryTypes}.ts (heads); install/LIFEOS/LIFEOS_SYSTEM_PROMPT.md (head); install/USER/TELOS/ tree + TELOS.md template; install/agents/*.md (ClaudeResearcher in full); DOCUMENTATION/ARCHITECTURE_SUMMARY.md (Memory/Router/Work/Observability rows); INSTALL.md refs via grep (launcher + --append-system-prompt-file wiring, lifeos.ts:403).
- **[S9]** LifeOS LICENSE — MIT, Copyright (c) 2025 Daniel Miessler (read directly in [S3] clone). Governs all VENDOR verdicts.

## Web sources (Phase 2; searched 2026-07-08)

- **[S4]** Claude Code hooks — official reference https://code.claude.com/docs/en/hooks (via search; corroborated by claudefa.st hooks guide, morphllm.com hook-event writeups). CONFIRMS: SessionStart/SessionEnd/Stop/PreToolUse/PostToolUse (and more) lifecycle events; Stop can block; PostToolUse feeds back. Matches LifeOS's observed usage [S3].
- **[S5]** Claude Code CLI reference https://code.claude.com/docs/en/cli-reference (fetched 2026-07-08). CONFIRMS both flags verbatim: `--append-system-prompt` ("Append custom text to the end of the default system prompt") and `--append-system-prompt-file` ("Load additional system prompt text from a file…"). Basis for H-5/U-H3.
- **[S6]** Letta (formerly MemGPT) — https://www.letta.com/blog/agent-memory/ (vendor), corroborated by sureprompts.com Letta walkthrough (2026) and vectorize.io Mem0-vs-Letta (2026). CONFIRMS: naming (Letta, formerly MemGPT); core/recall/archival hierarchy; memory blocks (human/persona; core_memory_append/replace).
- **[S7]** Zep + Graphiti — arXiv:2501.13956 "Zep: A Temporal Knowledge Graph Architecture for Agent Memory"; https://help.getzep.com/graphiti/getting-started/overview; neo4j.com Graphiti blog. CONFIRMS: Graphiti temporal KG; bi-temporal model (occurred-at vs ingested-at; validity intervals per edge); episode/semantic-entity/community subgraphs; open source.
- **[S8]** uv packaging consolidation — https://github.com/astral-sh/uv + astral.sh/blog/uv-unified-python-packaging, corroborated by multiple 2026 guides (datacamp, pydevtools, 2026 "golden path" posts). CONFIRMS: `uv tool install` as the pipx-replacement norm for CLI distribution in 2026. Basis for C-1/U-P1.
- **[S10]** SQLite backup semantics — code-level confirmation only: agentic-os already uses `sqlite3.Connection.backup` with the WAL rationale documented in export.py:1-11 [S2]. No external fetch needed; python stdlib `sqlite3.backup` and `zipapp` treated as stable stdlib knowledge (INFERRED-safe).

## Search log (stop rule ≤3/topic; none exhausted)

1. "Letta MemGPT agent memory blocks core memory archival memory 2026" → hit (S6). 
2. "Zep Graphiti temporal knowledge graph agent memory" → hit (S7).
3. "Claude Code hooks SessionEnd Stop PostToolUse documentation --append-system-prompt" → hit (S4).
4. Fetch code.claude.com/docs/en/cli-reference → hit (S5, flags grep-confirmed from saved page).
5. "uv Python packaging standard tool 2026 pipx install CLI" → hit (S8).

## Resolution check

Every [S#] cited in aos-v2-report.md appears above: S1, S1b, S2, S3, S4, S5, S6, S7, S8, S9(§2 vendor rule), S10(implicit in §7.2 backup design — cited here). File:line citations resolve against the [S2]/[S3] clones listed.
