"""A real, historical schema-v1 workspace, built deterministically (U-M1 M1.11).

A *source*, not a committed .db file. A binary SQLite fixture would be
unstable across sqlite versions and page layouts, would bake in wall-clock
timestamps from `utils.utc_now_iso()`, and would sit in the tree as exactly
the kind of database the packaging allowlist exists to keep out of aos.pyz.

Built with production CLI commands only — never raw INSERTs — so the fixture
is a database a v1 user could actually have produced, and cannot drift from
what v1 code writes. Every table a migration might touch carries
representative rows: projects, tasks (all four statuses), runs, packs,
evidence, decisions, handoffs, memory, agents, and a populated events
journal.

`build_v1_workspace(root)` leaves:
  project `demo` (+ `legacy`)
  T-0001 done      — pack P-0001, run R-0001 (success), evidence E-0001
  T-0002 in_progress — run R-0002 (open), handoff H-0001 (accepted)
  T-0003 ready     — priority 1, spec + acceptance
  T-0004 inbox     — projectless capture
  D-0001 decision · M-0001/M-0002 memory rows · two registered agents
"""

from __future__ import annotations

import contextlib
import io
import sqlite3
from pathlib import Path

from agentic_os import cli, utils

#: Every table whose contents the preservation proof compares.
FIXTURE_TABLES = (
    "meta",
    "projects",
    "tasks",
    "runs",
    "events",
    "decisions",
    "evidence",
    "handoffs",
    "memory",
    "packs",
    "agents",
)


def _run(*argv: str) -> None:
    """Run a CLI command, failing loudly. Output is a fixture artifact, not
    something a test should have to read."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    if code != 0:
        raise AssertionError(
            f"fixture command failed ({code}): aos {' '.join(argv)}\n"
            f"{err.getvalue() or out.getvalue()}"
        )


def build_v1_workspace(root: Path) -> Path:
    """Build the v1 fixture workspace under `root`. Returns its aos.db path."""
    root = Path(root).resolve()
    repo = root / "repo with spaces"
    repo.mkdir(parents=True, exist_ok=True)
    legacy_repo = root / "legacy-repo"
    legacy_repo.mkdir(parents=True, exist_ok=True)

    with contextlib.chdir(root):
        _run("init")
        _run("project", "add", "demo", "--name", "Demo", "--repo", str(repo))
        _run(
            "project", "add", "legacy", "--name", "Legacy",
            "--repo", str(legacy_repo),
        )

        _run("agent", "add", "claude-code", "--kind", "local",
             "--notes", "primary coding agent", "--capability", "code")
        _run("agent", "add", "reviewer", "--kind", "cloud",
             "--notes", "review only")

        # T-0001: the full done-with-evidence flow.
        _run("task", "add", "Historical v1 task", "-p", "demo",
             "--accept", "pack + evidence flow works")
        _run("pack", "build", "T-0001", "--for", "claude-code")
        _run("run", "start", "T-0001", "--agent", "claude-code")
        _run("evidence", "add", "T-0001", "--kind", "note",
             "--ref", "v1 proof", "--claim", "it works")
        _run("run", "end", "R-0001", "--outcome", "success", "--summary", "ok")
        _run("done", "T-0001")

        # T-0002: in_progress, with an accepted handoff.
        _run("task", "add", "In-flight task", "-p", "demo", "--kind", "code")
        _run("run", "start", "T-0002", "--agent", "claude-code")
        _run("handoff", "create", "T-0002", "--from", "claude-code",
             "--to", "reviewer", "--state", "ready for review")
        _run("handoff", "accept", "H-0001")

        # T-0003: ready, richer fields.
        _run("task", "add", "Planned task", "-p", "legacy", "--priority", "1",
             "--kind", "writing", "--accept", "docs updated",
             "--spec", "write it")

        # T-0004: projectless inbox capture.
        _run("in", "an inbox thought from v1")

        _run("decision", "add", "Use SQLite", "-p", "demo",
             "--decision", "SQLite is the system of record",
             "--alternatives", "Postgres; flat files", "--task", "T-0001")

        _run("memory", "add", "--scope", "global", "--kind", "preference",
             "--key", "commit-style", "--value", "conventional commits",
             "--source", "human", "--confidence", "confirmed")
        _run("memory", "add", "--scope", "project", "-p", "demo",
             "--kind", "fact", "--key", "runtime",
             "--value", "python 3.13", "--source", "human",
             "--confidence", "inferred")

        _run("sync")

    return root / utils.AOS_DIR_NAME / utils.DB_FILENAME


def table_contents(db_path: Path, tables=FIXTURE_TABLES) -> dict[str, list]:
    """Every row of every fixture table, ordered deterministically — the
    ground truth a forward migration must preserve field-for-field."""
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        dump: dict[str, list] = {}
        for table in tables:
            rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            dump[table] = sorted(
                [tuple(row) for row in rows], key=lambda r: repr(r)
            )
        return dump
    finally:
        conn.close()
