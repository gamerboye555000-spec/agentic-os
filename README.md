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
`memory list`, and `search` accept `--json`.

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

# Scoped memory rows (M-0001): add, list, retire, supersede:
python aos.py memory add --scope project --project agentic-os \
    --kind constraint --key storage --value "SQLite is source of truth" \
    --source human --confidence confirmed
python aos.py memory list --json
python aos.py memory add --scope project --project agentic-os \
    --kind constraint --key storage --value "SQLite, WAL mode" \
    --source human --confidence confirmed --supersedes M-0001
python aos.py memory retire M-0002

# Search tasks, decisions, evidence, handoffs, and memory:
python aos.py search "SQLite" --json

# Build (or refresh) today's review note — everything you write from the
# "## Notes" line down survives every rebuild byte-for-byte:
python aos.py review build

# Backups: JSONL event export + a WAL-safe database snapshot:
python aos.py export events --jsonl
python aos.py snapshot
```

Memory in context packs: the pack MEMORY section carries live rows only
(not retired, not superseded, latest per key), global scope plus the pinned
project. Retired and superseded rows stay in the ledger and in
`memory list` forever — they only stop being fed to agents.

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

## Layout

`python aos.py init` creates, under the current directory:

```
.agentic-os/
  aos.db            # SQLite ledger (source of truth)
  packs/            # compiled context packs (T-0001-claude-code.md, ...)
  exports/          # events-*.jsonl exports, aos-*.db snapshots, agent dropfiles
  adapters/         # per-agent PROTOCOL.md (claude-code, codex, gemini, generic)
  obsidian-vault/
    AOS/            # generated mirror: Home.md, CONVENTIONS.md, Tasks/, Runs/,
                    # Decisions/, Evidence/, Handoffs/, Memory/, Reviews/, ...
```

Human-facing IDs are stable and zero-padded: tasks `T-0001`, runs `R-0001`,
decisions `D-0001`, evidence `E-0001`, handoffs `H-0001`, packs `P-0001`,
memory `M-0001`.

## Rules of the road

- The vault is generated: never rename generated notes; edit data via the CLI
  and re-run `python aos.py sync` (see `AOS/CONVENTIONS.md`).
- Context packs are secret-scanned at build time and refuse to compile if
  anything credential-shaped is found.
- The only subprocess Agentic OS ever runs is read-only `git rev-parse` to
  anchor runs to a commit; failures degrade to a note, never a crash.

## Tests

```bash
python -m unittest discover -s tests
```

## Status

Weekend MVP, extending the committed Night-1 MVP — a database created by the
Night-1 build works with Weekend code unmodified (no schema change, no
migration). Deliberately deferred: agent CLI commands, dropfile ingest, git
evidence ingest, MCP server, Obsidian plugin, vector search, any autonomous
execution.
