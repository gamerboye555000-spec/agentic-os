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
they only write the two owned exports paths. You review and ingest:

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

## Agent registry

Records only — Agentic OS never executes agents.

```bash
python aos.py agent add codex --kind cloud --notes "cloud runner" \
    --capability code --capability review
python aos.py agent update codex --notes "new notes" --capability docs
python aos.py agent list --json
python aos.py agent show codex --json
```

Registered agents get generated `AOS/Agents/<name>.md` notes on sync. There
is deliberately no `--trust-level` flag anywhere: autonomy is earned through
the ladder, never set by hand.

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

## Status

Complete-today build, extending the Weekend and Night-1 MVPs — a database
created by either earlier build works with this code unmodified (no schema
change, no migration; `schema_version` stays `"1"`). This phase closed the
coordinate-and-audit loop: task lifecycle (`assign`/`edit`/`status` + list
filters), dropfile ingest, verified commit evidence (`evidence git`), the
agent registry with vault notes, richer daily/weekly/project reviews, Home
dashboard + index notes, and doctor hardening (now 18 checks incl. the
non-fatal commit-evidence warning and the U-C3 secret sweep).

Deliberately deferred (unchanged triggers, see `agentic-os-two-week-plan.md`
§4): MCP server, Obsidian plugin, vector search, background runs, two-way
review ingest, routing/scoring, multi-device sync, any autonomous execution.
