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
Machine-readable output: `task list`, `task show`, `status`, and `log` accept
`--json`.

## Layout

`python aos.py init` creates, under the current directory:

```
.agentic-os/
  aos.db            # SQLite ledger (source of truth)
  packs/            # compiled context packs (T-0001-claude-code.md, ...)
  exports/          # agent dropfiles land here when aos is unavailable
  adapters/         # per-agent PROTOCOL.md (claude-code, codex, gemini, generic)
  obsidian-vault/
    AOS/            # generated mirror: Home.md, CONVENTIONS.md, Tasks/, Runs/, ...
```

Human-facing IDs are stable and zero-padded: tasks `T-0001`, runs `R-0001`,
decisions `D-0001`, evidence `E-0001`, handoffs `H-0001`, packs `P-0001`.

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

Night-1 MVP. Deliberately deferred: handoff/memory/decision/agent CLI
commands, dropfile ingest, pack search, MCP server, Obsidian plugin, any
autonomous execution.
