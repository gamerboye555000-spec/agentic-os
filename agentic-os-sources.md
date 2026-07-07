# Agentic OS Research — Source Ledger

Rules: every [S#] cited in the report resolves here. Confidence labels used in the report: **CONFIRMED** (primary source or 2+ independent), **SINGLE-SOURCE** (one credible source), **INFERRED** (reasoned from evidence), **ASSUMED** (premise with risk if wrong). License classes: **PERMISSIVE-INSPIRATION** (MIT/Apache — patterns & code ideas safe to learn from; still no copying text) / **COPYLEFT-CAUTION** (GPL/AGPL — study behavior only, do not derive code) / **PROPRIETARY-NO-COPY** (closed products/docs — product lessons only) / **UNCLEAR**. All sources accessed 2026-07-07 via live web research (six scout passes + one adversarial verification pass). Pub dates as shown on page; "n.d." = none shown. Sources marked ⚠ are secondary/opinion — used for community-sentiment or convenience, never as sole support for a hard fact unless labeled SINGLE-SOURCE in the report.

## C1 — Coding agents & tools

| ID | Title | Publisher / repo | URL | Pub date | Supports | License class |
|---|---|---|---|---|---|---|
| S1 | Checkpointing (incl. bash-gap limitation) | Claude Code docs | https://code.claude.com/docs/en/checkpointing | n.d. | /rewind auto-checkpoints; bash-modified files NOT tracked (verified verbatim) | PROPRIETARY-NO-COPY |
| S2 | Hooks reference | Claude Code docs | https://code.claude.com/docs/en/hooks | n.d. | 18+ lifecycle events; PreToolUse can block/modify | PROPRIETARY-NO-COPY |
| S3 | Memory (CLAUDE.md + auto memory) | Claude Code docs | https://code.claude.com/docs/en/memory | n.d. | CLAUDE.md scopes; auto-memory dir; docs state Claude Code reads CLAUDE.md, NOT AGENTS.md | PROPRIETARY-NO-COPY |
| S4 | Agent teams (experimental) | Claude Code docs | https://code.claude.com/docs/en/agent-teams | n.d. | First-party multi-session orchestration behind env flag | PROPRIETARY-NO-COPY |
| S5 | Permissions | Claude Code docs | https://code.claude.com/docs/en/permissions | n.d. | deny→ask→allow evaluation; modes; hard-blocked destructive paths | PROPRIETARY-NO-COPY |
| S6 | Sandboxing | Claude Code docs | https://code.claude.com/docs/en/sandboxing | n.d. | Seatbelt/bubblewrap; **no native Windows — WSL2 required** | PROPRIETARY-NO-COPY |
| S7 | Making Claude Code more secure and autonomous with sandboxing | Anthropic engineering | https://www.anthropic.com/engineering/claude-code-sandboxing | 2025-10-20 | 84% reduction in permission prompts | PROPRIETARY-NO-COPY |
| S8 | Custom instructions with AGENTS.md | OpenAI developers | https://developers.openai.com/codex/guides/agents-md | n.d. | AGENTS.md layering; 32 KiB default cap (`project_doc_max_bytes`), silent truncation | PROPRIETARY-NO-COPY |
| S9 | openai/codex repo + LICENSE | GitHub | https://github.com/openai/codex | LICENSE (c) 2025 | Codex CLI open source, Apache-2.0; Rust; 67k+ stars (2026) | PERMISSIVE-INSPIRATION |
| S10 | CLI: implement Claude-Code-style /rewind (open issue #12558) | GitHub openai/codex | https://github.com/openai/codex/issues/12558 | open 2026 | Codex lacks native checkpoint/rewind | PERMISSIVE-INSPIRATION |
| S11 | Transitioning Gemini CLI to Antigravity CLI | Google Developers Blog | https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli/ | 2026-05-19 | Consumer-tier Gemini CLI ends 2026-06-18; `agy` migration; enterprise keeps access | PROPRIETARY-NO-COPY |
| S12 | Bye-bye, Gemini CLI | The Register | https://www.theregister.com/ai-ml/2026/05/20/bye-bye-gemini-cli-google-nudges-devs-toward-antigravity/5243605 | 2026-05-20 | Independent confirmation of S11; weekly quota regression | PROPRIETARY-NO-COPY |
| S13 | Introducing the Jules extension for Gemini CLI | Google Developers Blog | https://developers.googleblog.com/en/introducing-the-jules-extension-for-gemini-cli/ | n.d. | Jules async background VM agent | PROPRIETARY-NO-COPY |
| S14 | Build with Google Antigravity | Google Developers Blog | https://developers.googleblog.com/build-with-google-antigravity-our-new-agentic-development-platform/ | 2025-11 | Antigravity platform, Manager view, multi-model | PROPRIETARY-NO-COPY |
| S15 | Cognition's acquisition of Windsurf | Cognition | https://cognition.com/blog/windsurf | 2025-07 | Acquisition after Google acquihire | PROPRIETARY-NO-COPY |
| S16 | Cognition, maker of Devin, acquires Windsurf | TechCrunch | https://techcrunch.com/2025/07/14/cognition-maker-of-the-ai-coding-agent-devin-acquires-windsurf/ | 2025-07-14 | Independent confirmation of S15 | PROPRIETARY-NO-COPY |
| S17 ⚠ | Windsurf → Devin Desktop rename reports | webdeveloper.com; Medium (J. Njenga) | https://webdeveloper.com/news/windsurf-devin-desktop-cascade-eol/ | 2026-06 | Rename to Devin Desktop (2026-06-02); Cascade EOL 2026-07-01 — secondary sources only | PROPRIETARY-NO-COPY |
| S18 | Cursor 3 introduces agent-first interface | InfoQ | https://www.infoq.com/news/2026/04/cursor-3-agent-first-interface/ | 2026-04 | Cursor 3.0 (2026-04-02); CVE patches | PROPRIETARY-NO-COPY |
| S19 | Critical Cursor flaws could let prompt injection escape sandbox | The Hacker News | https://thehackernews.com/2026/07/critical-cursor-flaws-could-let-prompt.html | 2026-07 | CVE-2026-50548/50549, 9.8 severity | PROPRIETARY-NO-COPY |
| S20 ⚠ | Cursor problems 2026 | vibecoding.app | https://vibecoding.app/blog/cursor-problems-2026 | 2026 | Data-loss bug class (3 root causes ack'd Mar 2026); community complaints | PROPRIETARY-NO-COPY |
| S21 | About GitHub Copilot cloud agent | GitHub Docs | https://docs.github.com/copilot/concepts/agents/coding-agent/about-coding-agent | n.d. | Issue-assignment → autonomous PR; GitHub-hosted repos only; .copilotignore gap | PROPRIETARY-NO-COPY |
| S22 | "AI credits are unfair…" community discussion | GitHub #198015 | https://github.com/orgs/community/discussions/198015 | 2026 | Copilot billing backlash | PROPRIETARY-NO-COPY |
| S23 | Pick your agent: use Claude and Codex on Agent HQ | GitHub Blog | https://github.blog/news-insights/company-news/pick-your-agent-use-claude-and-codex-on-agent-hq/ | n.d. | Agent HQ real; multi-vendor agents inside GitHub | PROPRIETARY-NO-COPY |
| S24 | GitHub Agentic Workflows technical preview | GitHub Changelog | https://github.blog/changelog/2026-02-13-github-agentic-workflows-are-now-in-technical-preview/ | 2026-02-13 | `gh aw`: Markdown → SHA-pinned Actions; read-only default | PROPRIETARY-NO-COPY |
| S25 | GitHub Copilot CLI reaches GA | Visual Studio Magazine | https://visualstudiomagazine.com/articles/2026/03/02/github-copilot-cli-reaches-general-availability-bringing-agentic-coding-to-the-terminal.aspx | 2026-03-02 | Copilot CLI GA | PROPRIETARY-NO-COPY |
| S26 | Thoughts on future direction of aider (issue #4751) | GitHub Aider-AI/aider | https://github.com/Aider-AI/aider/issues/4751 | 2026 | Maintenance-mode signals | PERMISSIVE-INSPIRATION (Apache-2.0) |
| S27 | Aider release history | aider.chat | https://aider.chat/HISTORY.html | ongoing | v0.86.2 (2026-02-12); cadence slowdown | PERMISSIVE-INSPIRATION |
| S28 | OpenHands repo | GitHub OpenHands/OpenHands | https://github.com/OpenHands/OpenHands | ongoing | MIT; v1.6.0 (2026-03-30); 70k+ stars; SDK | PERMISSIVE-INSPIRATION |
| S29 | Roo Code vs Cline | Qodo | https://www.qodo.ai/blog/roo-code-vs-cline/ | 2026 | Roo Code archived 2026-05-15; Cline v3.83, 61k+ stars | PROPRIETARY-NO-COPY (article) |
| S30 | Cline repo | GitHub cline/cline | https://github.com/cline/cline | ongoing | Apache-2.0; Plan/Act approval-gated workflow | PERMISSIVE-INSPIRATION |
| S31 | Why Sourcegraph and Amp are becoming independent companies | Sourcegraph | https://sourcegraph.com/blog/why-sourcegraph-and-amp-are-becoming-independent-companies | 2025-12 | Amp spin-out | PROPRIETARY-NO-COPY |
| S32 | Changes to Cody Free, Pro, Enterprise Starter | Sourcegraph | https://sourcegraph.com/blog/changes-to-cody-free-pro-and-enterprise-starter-plans | 2025 | Cody free/Pro terminated by 2025-07-23 | PROPRIETARY-NO-COPY |
| S33 | Introducing Kiro | kiro.dev | https://kiro.dev/blog/introducing-kiro/ | 2025 | Spec-driven agentic IDE; AGENTS.md + MCP support | PROPRIETARY-NO-COPY |

## C2 — Frameworks & orchestrators

| ID | Title | Publisher / repo | URL | Pub date | Supports | License class |
|---|---|---|---|---|---|---|
| S34 | langchain-ai/langgraph | GitHub | https://github.com/langchain-ai/langgraph | ongoing | MIT; 1.0 GA Oct 2025; interrupt()/checkpointers; ~126k stars (2026-04, reported) | PERMISSIVE-INSPIRATION |
| S35 | Why checkpoints aren't durable execution | Diagrid | https://www.diagrid.io/blog/checkpoints-are-not-durable-execution-why-langgraph-crewai-google-adk-and-others-fall-short-for-production-agent-workflows | 2026-02-25 | No auto failure-detection/resume/dedupe in LangGraph/CrewAI/ADK/Strands (vendor-authored critique; corroborated by S52) | PROPRIETARY-NO-COPY |
| S36 | Microsoft ships production-ready Agent Framework 1.0 | Visual Studio Magazine | https://visualstudiomagazine.com/articles/2026/04/06/microsoft-ships-production-ready-agent-framework-1-0-for-net-and-python.aspx | 2026-04-06 | AutoGen+SK merged; GA 2026-04-03; predecessors in maintenance | PROPRIETARY-NO-COPY |
| S37 ⚠ | Is AutoGen deprecated? | aidevdayindia.org | https://aidevdayindia.org/blogs/ai-agent-framework-decision-matrix/is-autogen-deprecated-maintenance-mode-microsoft.html | 2026 | AG2 community fork of AutoGen v0.2 | UNCLEAR |
| S38 | crewAIInc/crewAI | GitHub | https://github.com/crewaiinc/crewai | ongoing | MIT; ~54k stars (2026-06, reported); @persist/from_pending | PERMISSIVE-INSPIRATION |
| S39 | OpenAI updates its Agents SDK | TechCrunch | https://techcrunch.com/2026/04/15/openai-updates-its-agents-sdk-to-help-enterprises-build-safer-more-capable-agents/ | 2026-04-15 | Handoffs/Guardrails primitives; TS parity | PROPRIETARY-NO-COPY |
| S40 | Deprecation notice: Agent Builder | OpenAI community | https://community.openai.com/t/deprecation-notice-agent-builder/1382650 | 2026-06 | Agent Builder + Evals deprecated 2026-06-03, shutoff 2026-11-30 | PROPRIETARY-NO-COPY |
| S41 | Linux Foundation launches the Agent2Agent protocol project | Linux Foundation | https://www.linuxfoundation.org/press/linux-foundation-launches-the-agent2agent-protocol-project-to-enable-secure-intelligent-communication-between-ai-agents | 2025-06 | A2A donated 2025-06-23; founding members | PERMISSIVE-INSPIRATION (open standard) |
| S42 | A2A protocol surpasses 150 organizations | Linux Foundation | https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year | 2026-04-09 | A2A v1.2; adoption claims (institutional; day-to-day depth contested) | PERMISSIVE-INSPIRATION |
| S43 ⚠ | Google ADK 1.0 and A2A protocol | n1n.ai | https://explore.n1n.ai/blog/google-adk-1-0-a2a-protocol-multi-agent-standard-2026-05-04 | 2026-05-04 | ADK 1.0 multi-language; event-sourced sessions; ResumabilityConfig | UNCLEAR |
| S44 | pydantic/pydantic-ai | GitHub | https://github.com/pydantic/pydantic-ai | ongoing | MIT; documented Temporal/DBOS/Prefect durable-execution integrations | PERMISSIVE-INSPIRATION |
| S45 | huggingface/smolagents | GitHub | https://github.com/huggingface/smolagents | ongoing | Apache-2.0; ~28k stars; minimal code-agent core | PERMISSIVE-INSPIRATION |
| S46 | mastra-ai/mastra | GitHub | https://github.com/mastra-ai/mastra | ongoing | Open-core (check per-package); v1.0 Jan 2026 | UNCLEAR |
| S47 | Agent Workflows | LlamaIndex | https://www.llamaindex.ai/workflows | n.d. | Event-driven workflows; founder's "framework era ending" stance | PERMISSIVE-INSPIRATION (MIT) |
| S48 | DSPy roadmap / stanfordnlp/dspy | dspy.ai / GitHub | https://dspy.ai/roadmap/ | ongoing | MIT; v3.3; orthogonal (prompt optimization) | PERMISSIVE-INSPIRATION |
| S49 | Building effective agents | Anthropic | https://www.anthropic.com/engineering/building-effective-agents | 2024-12 | Simple composable patterns > frameworks (foundational) | PROPRIETARY-NO-COPY |
| S50 | 12-Factor Agents | HumanLayer (GitHub) | https://github.com/humanlayer/humanlayer | 2025 | Own prompts/context/control-flow; stateless-reducer framing | PERMISSIVE-INSPIRATION |
| S51 | Building agents with the Claude Agent SDK | Anthropic | https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk | 2025 | SDK renamed from Claude Code SDK (2025-09); shared-filesystem coordination | PROPRIETARY-NO-COPY |
| S52 | Durable execution meets AI | Temporal | https://temporal.io/blog/durable-execution-meets-ai-why-temporal-is-the-perfect-foundation-for-ai | n.d. | Replay-based resumption concept (vendor; corroborates S35) | PROPRIETARY-NO-COPY |

## C3 — Protocols & integration

| ID | Title | Publisher / repo | URL | Pub date | Supports | License class |
|---|---|---|---|---|---|---|
| S53 | MCP joins the Agentic AI Foundation | MCP blog | https://blog.modelcontextprotocol.io/posts/2025-12-09-mcp-joins-agentic-ai-foundation/ | 2025-12-09 | MCP → AAIF/Linux Foundation; ~97M monthly SDK downloads, ~10k servers (vendor-reported) | PERMISSIVE-INSPIRATION (open spec) |
| S54 | The 2026-07-28 MCP specification release candidate | MCP blog | https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/ | 2026-05-21 | Stateless core; Extensions; deprecates Sampling/Roots/Logging (≥12-mo grace) | PERMISSIVE-INSPIRATION |
| S55 | MCP specification 2025-11-25 | modelcontextprotocol.io | https://modelcontextprotocol.io/specification/2025-11-25 | 2025-11-25 | Current stable spec | PERMISSIVE-INSPIRATION |
| S56 | Linux Foundation announces formation of the Agentic AI Foundation | Linux Foundation | https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation | 2025-12 | AAIF founders (Anthropic, Block, OpenAI); AGENTS.md + goose sibling projects | PERMISSIVE-INSPIRATION |
| S57 | GitHub MCP exploited | Invariant Labs | https://invariantlabs.ai/blog/mcp-github-vulnerability | 2025-05-26 | Prompt-injected private-repo exfiltration via GitHub MCP | PROPRIETARY-NO-COPY |
| S58 | MCP security notification: tool poisoning attacks | Invariant Labs | https://invariantlabs.ai/blog/mcp-security-notification-tool-poisoning-attacks | 2025-04-01 | Tool poisoning; rug-pull; shadowing | PROPRIETARY-NO-COPY |
| S59 | The lethal trifecta | Simon Willison | https://simonwillison.net/2025/Jun/16/the-lethal-trifecta/ | 2025-06-16 | Private data + untrusted content + exfil path framing | PROPRIETARY-NO-COPY |
| S60 | Supabase MCP can leak your entire SQL database | Simon Willison | https://simonwillison.net/2025/Jul/6/supabase-mcp-lethal-trifecta/ | 2025-07-06 | service_role over-privilege attack (anchor date for S116) | PROPRIETARY-NO-COPY |
| S61 | OWASP MCP Top 10 | OWASP | https://owasp.org/www-project-mcp-top-10/ | v0.1 beta | Canonical MCP risk list | PERMISSIVE-INSPIRATION |
| S62 | Code execution with MCP | Anthropic | https://www.anthropic.com/engineering/code-execution-with-mcp | 2025-11 | Filesystem/code-API presentation of tools beats schema-loading | PROPRIETARY-NO-COPY |
| S63 ⚠ | Why CLI tools are beating MCP for AI agents | jannikreinhard.com | https://jannikreinhard.com/2026/02/22/why-cli-tools-are-beating-mcp-for-ai-agents/ | 2026-02-22 | "CLI inner loop, MCP outer loop" consensus (opinion, representative) | UNCLEAR |
| S64 ⚠ | Do you symlink AGENTS.md | SSW Rules | https://www.ssw.com.au/rules/symlink-agents-to-claude | n.d. | Symlink pattern CLAUDE.md→AGENTS.md | UNCLEAR |
| S65 | Codex sandboxing docs | OpenAI developers | https://developers.openai.com/codex/concepts/sandboxing | n.d. | 3 sandbox tiers; Seatbelt/Landlock/bubblewrap/Windows sandbox | PROPRIETARY-NO-COPY |
| S66 ⚠ | AI agent sandbox infrastructure 2026 | AgentMarketCap | https://agentmarketcap.ai/blog/2026/04/07/ai-agent-sandbox-infrastructure-e2b-modal-daytona-fly-machines-secure-code-execution | 2026-04-07 | E2B/microVM landscape (secondary) | UNCLEAR |
| S67 | litequeue | GitHub litements/litequeue | https://github.com/litements/litequeue | ongoing | SQLite-as-queue pattern + crash-recovery sweep caveat | PERMISSIVE-INSPIRATION |

## C4 — Memory, knowledge, Obsidian, local-first

| ID | Title | Publisher / repo | URL | Pub date | Supports | License class |
|---|---|---|---|---|---|---|
| S68 | Obsidian changelog — desktop v1.12.4 | Obsidian | https://obsidian.md/changelog/2026-02-27-desktop-v1.12.4/ | 2026-02-27 | Official Obsidian CLI GA (early access 1.12.0, 2026-02-10) | PROPRIETARY-NO-COPY |
| S69 | Free for work | Obsidian | https://obsidian.md/blog/free-for-work/ | 2025-02-20 | Commercial license optional since 2025-02-20 | PROPRIETARY-NO-COPY |
| S70 | Properties | Obsidian Help | https://help.obsidian.md/Editing+and+formatting/Properties | n.d. | Typed YAML properties; ISO dates | PROPRIETARY-NO-COPY |
| S71 | Announcing JSON Canvas | Obsidian | https://obsidian.md/blog/json-canvas/ | 2024-03 | Open canvas spec | PERMISSIVE-INSPIRATION (open spec) |
| S72 | Local REST API plugin (with MCP endpoint) | coddingtonbear (community) | https://community.obsidian.md/plugins/obsidian-local-rest-api | ongoing | REST CRUD + built-in MCP server at 127.0.0.1:27124 (community plugin) | PERMISSIVE-INSPIRATION |
| S73 ⚠ | Obsidian MCP servers roundup | ChatForest | https://chatforest.com/reviews/obsidian-mcp-servers/ | ~2026-04 | 66 community servers; no official server; trademark takedown | UNCLEAR |
| S74 | Advanced URI plugin | Vinzent03 (GitHub) | https://github.com/Vinzent03/obsidian-advanced-uri | ongoing | Scripted open/create/edit/frontmatter ops | PERMISSIVE-INSPIRATION |
| S75 | Dataview vs Datacore vs Obsidian Bases | Obsidian Rocks | https://obsidian.rocks/dataview-vs-datacore-vs-obsidian-bases/ | 2025-26 | Bases = YAML-properties-only, faster; not full Dataview replacement | UNCLEAR |
| S76 ⚠ | Obsidian Dataview is dead. Long live Bases. | Medium (lennart.dde) | https://medium.com/@lennart.dde/obsidian-dataview-is-dead-long-live-bases-9750e8a92877 | 2025-26 | Dataview maintainer stepped back 2023; community-sustained | UNCLEAR |
| S77 | Wikilinks stopped breaking (OS-level rename hazard) | XDA Developers | https://www.xda-developers.com/added-one-thing-to-claude-obsidian-setup-and-wikilinks-stopped-breaking/ | 2025-26 | OS-level moves/renames break wikilinks; agents corrupt frontmatter/callouts | PROPRIETARY-NO-COPY |
| S78 | New plugin: Agent Client | Obsidian forum | https://forum.obsidian.md/t/new-plugin-agent-client-bring-claude-code-codex-gemini-cli-inside-obsidian/108448 | 2025-26 | Claude Code/Codex/Gemini inside Obsidian | UNCLEAR |
| S79 | What's new with Logseq DB — May 16 2026 | Logseq forum | https://discuss.logseq.com/t/whats-new-with-logseq-db-may-16th-2026/35020 | 2026-05-16 | DB version still beta; data-loss warnings | COPYLEFT-CAUTION (AGPL app) |
| S80 | johnny-decimal-zettelkasten | GitHub jabez007 | https://github.com/jabez007/johnny-decimal-zettelkasten | ongoing | JD + Zettelkasten + AI-librarian precedent | PERMISSIVE-INSPIRATION |
| S81 | Agent memory / Memory blocks | Letta | https://www.letta.com/blog/agent-memory/ | 2025-26 | Labeled memory blocks; 3-tier model | PROPRIETARY-NO-COPY (blog; core repo Apache-2.0) |
| S82 | Mem0 vs Zep (Graphiti) | vectorize.io | https://vectorize.io/articles/mem0-vs-zep | 2025-26 | LongMemEval: Zep 63.8% vs Mem0 49.0% (GPT-4o config) | UNCLEAR |
| S83 | State of AI agent memory 2026 | Mem0 (vendor) | https://mem0.ai/blog/state-of-ai-agent-memory-2026 | 2026 | Mem0 adoption claims (vendor-reported) | PERMISSIVE-INSPIRATION (repo Apache-2.0) |
| S84 | langchain-ai/langmem | GitHub | https://github.com/langchain-ai/langmem | ongoing | Releases stalled at 0.0.30 (2025-10) | PERMISSIVE-INSPIRATION |
| S85 | Memory tool | Claude Platform docs | https://platform.claude.com/docs/en/agents-and-tools/tool-use/memory-tool | n.d. | Memory tool GA for Claude 4+ | PROPRIETARY-NO-COPY |
| S86 ⚠ | Agentic memory poisoning (MINJA coverage) | Medium (InstaTunnel) | https://medium.com/@instatunnel/agentic-memory-poisoning-how-long-term-ai-context-can-be-weaponized-7c0eb213bd1a | 2025-26 | >95% injection success vs memory-augmented agents (secondary coverage of research) | UNCLEAR |
| S87 ⚠ | Why SQLite+FTS5 beats vector DBs for agent memory | DEV Community | https://dev.to/fex_beck_27bfd4dccd05f062/why-sqlitefts5-beats-vector-dbs-for-ai-agent-memory-4inj | 2025-26 | FTS5 sufficient at agent scale (representative of repeated practitioner conclusion) | UNCLEAR |
| S88 | sqlite-vec maintenance status (issue #226) | GitHub asg017/sqlite-vec | https://github.com/asg017/sqlite-vec/issues/226 | 2025-26 | Maintenance hiatus; pre-1.0 | PERMISSIVE-INSPIRATION |
| S89 ⚠ | Event sourcing with SQLite: append-only design | sqliteforum.com | https://www.sqliteforum.com/p/event-sourcing-with-sqlite | n.d. | Append-only events + snapshots pattern | UNCLEAR |
| S90 | Local-first software | Ink & Switch | https://www.inkandswitch.com/local-first-software/ | 2019 (foundational) | Local-first principles; CRDTs for multi-writer only | PERMISSIVE-INSPIRATION |

## C5 — Reliability, incidents, guardrails

| ID | Title | Publisher / repo | URL | Pub date | Supports | License class |
|---|---|---|---|---|---|---|
| S91 | Replit vibe-coding incident | The Register | https://www.theregister.com/2025/07/21/replit_saastr_vibe_coding_incident/ | 2025-07-21 | Prod DB deleted; false rollback claim; fabricated data | PROPRIETARY-NO-COPY |
| S92 | AI coding tool wiped database | Fortune | https://fortune.com/2025/07/23/ai-coding-tool-replit-wiped-database-called-it-a-catastrophic-failure/ | 2025-07-23 | Independent confirmation of S91 | PROPRIETARY-NO-COPY |
| S93 | AI Incident Database #1152 | incidentdatabase.ai | https://incidentdatabase.ai/cite/1152/ | 2025 | Replit incident record | PERMISSIVE-INSPIRATION |
| S94 | Gemini CLI issue #4586 (incl. reporter's retraction) | GitHub google-gemini/gemini-cli | https://github.com/google-gemini/gemini-cli/issues/4586 | 2025-07 | Hallucinated success states; "loss" partly walked back | PERMISSIVE-INSPIRATION |
| S95 | Claude Code destructive-action issues #29120, #4331 | GitHub anthropics/claude-code | https://github.com/anthropics/claude-code/issues/29120 | 2025-26 | Cross-repo deletion; rm -rf of working dir (also /issues/4331) | PROPRIETARY-NO-COPY |
| S96 | Comet prompt injection | Brave | https://brave.com/blog/comet-prompt-injection/ | 2025-08-20 | Agentic-browser injection → Gmail/OTP exfil | PROPRIETARY-NO-COPY |
| S97 | CometJacking | The Hacker News | https://thehackernews.com/2025/10/cometjacking-one-click-can-turn.html | 2025-10 | URL-parameter injection; vendor dismissed report | PROPRIETARY-NO-COPY |
| S98 ⚠ | EchoLeak CVE-2025-32711 (M365 Copilot zero-click) | Aim Security disclosure (2025-06-11) | (primary URL not captured this run — verify before external use) | 2025-06-11 | Zero-click exfiltration class exists; CVSS 9.3 | UNCLEAR |
| S99 | Measuring the impact of early-2025 AI on experienced OSS developers | METR | https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/ | 2025-07-10 | RCT: 19% slower, felt 20% faster (16 devs, 246 tasks) | PERMISSIVE-INSPIRATION |
| S100 | We are changing our developer productivity experiment design | METR | https://metr.org/blog/2026-02-24-uplift-update/ | 2026-02-24 | Newer data trends to speedup but METR flags it unreliable (self-selection, pay change) | PERMISSIVE-INSPIRATION |
| S101 | Project Vend 1 | Anthropic | https://www.anthropic.com/research/project-vend-1 | 2025-06-27 | Hallucinated accounts/identity; long-horizon drift | PROPRIETARY-NO-COPY |
| S102 | Project Vend 2 | Anthropic | https://www.anthropic.com/research/project-vend-2 | 2025-12-18 | Improved commerce; CEO-agent manipulation | PROPRIETARY-NO-COPY |
| S103 | Thoughts on Devin | Answer.AI | https://www.answer.ai/posts/2025-01-08-devin.html | 2025-01-08 | 14/20 real tasks failed; 3 successes | PROPRIETARY-NO-COPY |
| S104 | Builder.ai files for bankruptcy | Bloomberg | https://www.bloomberg.com/news/articles/2025-06-05/builder-ai-files-for-bankruptcy-after-creditors-seize-accounts | 2025-06-05 | "AI" product collapse | PROPRIETARY-NO-COPY |
| S105 | China blocks Meta's acquisition of Manus | SiliconANGLE | https://siliconangle.com/2026/04/27/china-blocks-metas-acquisition-ai-agent-developer-manus/ | 2026-04-27 | Manus trajectory 2026 | PROPRIETARY-NO-COPY |
| S106 | AWS service outage / Kiro rebuttal | About Amazon | https://www.aboutamazon.com/news/aws/aws-service-outage-ai-bot-kiro | 2026-02-20 | Contested: Amazon attributes to misconfigured access controls, not AI | PROPRIETARY-NO-COPY |
| S107 | How we hacked McKinsey's AI platform | CodeWall | https://codewall.ai/blog/how-we-hacked-mckinseys-ai-platform | 2026-03-09 | Agent-found SQLi; 46.5M messages; prompt layer as target | PROPRIETARY-NO-COPY |
| S108 | State of security of vibe-coded apps | Escape.tech | https://escape.tech/state-of-security-of-vibe-coded-apps | 2025-10 | 1,400+ apps: 65% security issues, 58% critical vuln | PROPRIETARY-NO-COPY |
| S109 | CSA research note: AI-generated code security | Cloud Security Alliance | https://labs.cloudsecurityalliance.org/research/csa-research-note-ai-generated-code-security-vibe-coding-202/ | 2026-03-31 | Aggregated vibe-code risk data; CVE growth | PROPRIETARY-NO-COPY |
| S110 | Demystifying evals for AI agents | Anthropic | https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents | 2026-01-09 | Regression evals as CI gates, near-100% pass | PROPRIETARY-NO-COPY |
| S111 | CaMeL: Defeating prompt injections by design | arXiv (DeepMind/ETH) | https://arxiv.org/abs/2503.18813 | 2025-03 | Capability-based control/data-flow separation; 77% AgentDojo solved securely | PERMISSIVE-INSPIRATION |
| S112 | The dual-LLM pattern | Simon Willison | https://simonwillison.net/2023/Apr/25/dual-llm-pattern/ | 2023-04-25 (foundational) | Privileged/quarantined LLM separation | PROPRIETARY-NO-COPY |
| S113 | humanlayer/humanlayer | GitHub | https://github.com/humanlayer/humanlayer | ongoing | Approval-gate tooling; 12-factor authors; → CodeLayer | PERMISSIVE-INSPIRATION |
| S114 | Levels of autonomy for AI agents | arXiv 2506.12469 | https://arxiv.org/abs/2506.12469 | 2025-06 | 5 levels by user role: operator→observer | PERMISSIVE-INSPIRATION |
| S115 ⚠ | Supabase MCP attack writeup | General Analysis | https://generalanalysis.com/blog/supabase-mcp-blog | date anomaly (metadata 2026-04 vs cited 2025-07) | Technical detail of S60 attack; date flagged, anchor to S60 | UNCLEAR |

## C6 — Neighbors & product inspiration

| ID | Title | Publisher / repo | URL | Pub date | Supports | License class |
|---|---|---|---|---|---|---|
| S116 | Beads (bd) — repo + LICENSE + README | GitHub gastownhall/beads | https://github.com/gastownhall/beads | 2025-10 launch | MIT; Dolt-backed embedded storage; JSONL export; agent-first issue graph; memory decay | PERMISSIVE-INSPIRATION |
| S117 | Beads discussion | Hacker News | https://news.ycombinator.com/item?id=46669791 | 2026 | 130k+ LOC size complaint; Rust reimplementation | UNCLEAR |
| S118 | Gas Town: from clown show to v1.0 | Steve Yegge (Medium) | https://steve-yegge.medium.com/gas-town-from-clown-show-to-v1-0-c239d9a407ec | 2026 | Gas Town orchestrator; Beads as substrate | PROPRIETARY-NO-COPY |
| S119 | claude-task-master + licensing.md | GitHub eyaltoledano | https://github.com/eyaltoledano/claude-task-master | ongoing | MIT + Commons Clause; JSON storage; PRD decomposition | PERMISSIVE-INSPIRATION (Commons-Clause caution for resale) |
| S120 | task-master failure issues (#1174; discussion #864) | GitHub | https://github.com/eyaltoledano/claude-task-master/issues/1174 | 2025-26 | JSON-parse crashes; concurrent-write data loss; PRD fidelity loss | PERMISSIVE-INSPIRATION |
| S121 | Backlog.md | GitHub MrLesk/Backlog.md | https://github.com/MrLesk/Backlog.md | ongoing | MIT; Markdown-as-primary task store; MCP server; Kanban UIs | PERMISSIVE-INSPIRATION |
| S122 | Vibe Kanban | GitHub BloopAI/vibe-kanban | https://github.com/BloopAI/vibe-kanban | ongoing | Apache-2.0; community-maintained post-Bloop; worktrees; MCP client+server; permission-skip default | PERMISSIVE-INSPIRATION |
| S123 ⚠ | Vibe Kanban after Bloop | Nimbalyst | https://nimbalyst.com/blog/vibe-kanban-after-bloop-whats-next/ | 2026-04 | Bloop shutdown 2026-04-10; hosted tier wound down | UNCLEAR |
| S124 ⚠ | Vibe Kanban honest review | solvedbycode.ai | https://solvedbycode.ai/blog/vibe-kanban-honest-review | 2026 | Semantic-merge limits; ~4-agent slowdown; consent issue | UNCLEAR |
| S125 | claude-squad | GitHub smtg-ai/claude-squad | https://github.com/smtg-ai/claude-squad | v1.0.19 2026-06-17 | AGPL-3.0; tmux+worktree state; terminal-native | COPYLEFT-CAUTION |
| S126 ⚠ | Conductor: running multiple AI coding agents | madewithlove | https://madewithlove.com/blog/conductor-running-multiple-ai-coding-agents-in-parallel/ | 2025-26 | Mac parallel-agent manager; diff-review UX | UNCLEAR |
| S127 ⚠ | Best multi-agent coding tools 2026 | Nimbalyst | https://nimbalyst.com/blog/best-multi-agent-coding-tools-2026/ | 2026 | Sculptor (Docker isolation); review-queue convergence | UNCLEAR |
| S128 | Terragon shutdown | terragonlabs.com | https://www.terragonlabs.com/ | 2026-02-09 | Cloud-hosted agent manager died | PROPRIETARY-NO-COPY |
| S129 ⚠ | Spec Kit vs BMAD vs OpenSpec: choosing an SDD framework in 2026 | DEV Community | https://dev.to/willtorber/spec-kit-vs-bmad-vs-openspec-choosing-an-sdd-framework-in-2026-d3j | 2026 | SDD landscape; spec-rot criticism; star counts (±) | UNCLEAR |
| S130 | "SpecKit creates the illusion of work" (discussion #1784) | GitHub github/spec-kit | https://github.com/github/spec-kit/discussions/1784 | 2025-26 | Ceremony-overhead critique for solo devs | PERMISSIVE-INSPIRATION (MIT repo) |
| S131 | Agent OS v3 migration | Builder Methods | https://buildermethods.com/agent-os/migration | 2026 | Agent OS retired own orchestration → defers to native plan modes; name collision | PERMISSIVE-INSPIRATION (repo open) |
| S132 ⚠ | Claude multi-agent ecosystem (Claude Flow→Ruflo) | codex.danielvaughan.com | https://codex.danielvaughan.com/2026/04/09/claude-multi-agent-ecosystem/ | 2026-04-09 | Ruflo rename (2026-01); heavyweight architecture; self-reported benchmarks | UNCLEAR |
| S133 | Linear adopts agentic AI as CEO declares issue tracking dead | The Register | https://www.theregister.com/software/2026/03/26/linear-adopts-agentic-ai-as-ceo-declares-issue-tracking-dead/5227428 | 2026-03-26 | Delegation-not-assignment model | PROPRIETARY-NO-COPY |
| S134 | Agents in Linear | Linear docs | https://linear.app/docs/agents-in-linear | n.d. | Human stays assignee-of-record; agent = contributor | PROPRIETARY-NO-COPY |
| S135 | Copilot coding agent for Jira public preview | GitHub Changelog | https://github.blog/changelog/2026-03-05-github-copilot-coding-agent-for-jira-is-now-in-public-preview/ | 2026-03-05 | PM-tool → agent delegation surface | PROPRIETARY-NO-COPY |
| S136 ⚠ | How we built an AI second brain for 60k knowledge workers | Medium (Analytics at Meta) | https://medium.com/@AnalyticsAtMeta/how-we-built-an-ai-second-brain-for-60k-knowledge-workers-78c507dd795b | 2025-26 | "Biggest usefulness drop at session boundary" | UNCLEAR |
| S137 | AI agents and JD | Johnny.Decimal forum | https://forum.johnnydecimal.com/t/ai-agents-and-jd/2882 | 2025-26 | Stable numeric addressing helps agents | UNCLEAR |
| S138 ⚠ | The SQLite renaissance | DEV Community | https://dev.to/pockit_tools/the-sqlite-renaissance-why-the-worlds-most-deployed-database-is-taking-over-production-in-2026-3jcc | 2026 | SQLite-as-production-store trend | UNCLEAR |
| S139 | Claude Cowork product page | Anthropic | https://claude.com/product/cowork | n.d. | First-party orchestration surface above Claude Code | PROPRIETARY-NO-COPY |

Gap log (honest): S98 (EchoLeak) lacks a captured primary URL — the CVE ID and disclosure narrative came from the failure-evidence scout; verify at aim.security or the NVD entry before citing externally. Star counts throughout are as-reported by cited pages on access date, precision ±5-10%; treat as adoption signals, not exact figures. No other pay-walled gaps encountered; Bloomberg (S104) may be paywalled — the bankruptcy fact is corroborated by widespread contemporaneous coverage.
