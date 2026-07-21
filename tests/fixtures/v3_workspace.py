"""A real, historical schema-v3 workspace, built deterministically (U-A1).

A *source*, not a committed .db file — for every reason v1_workspace.py and
v2_workspace.py give: a binary SQLite fixture would be unstable across
sqlite versions and page layouts, would bake in wall-clock timestamps, and
would sit in the tree as exactly the kind of database the packaging
allowlist exists to keep out of aos.pyz.

The construction is v2_workspace.py's, one version later. Production is at
schema version 4 now, and v4 code CANNOT run against a v3 database — that is
what the version gate guarantees — so the fixture builds in this order:

1. Every non-agent command runs as production v4 code. U-A1 changed nothing
   about the projects/tasks/runs/evidence/handoffs/decisions/memory tables,
   their writers or their events, so the rows a v4 build writes for them are
   identical to the rows a v3 build wrote — INCLUDING the memory claims and
   graph rows, whose DDL and hash payloads U-A1 leaves byte-identical.
2. `sync` runs while the agents table is still EMPTY.
3. The (still empty) v4 `agents` table is replaced by the HISTORICAL v3
   definition — migrations._V3_AGENTS_DDL, the same frozen text the 3→4
   step documents as its input shape, so fixture and migration agree about
   v3 by construction — `agent_passports` is dropped, and schema_version
   goes to "3". No row is rewritten or reverse-migrated: pure DDL against an
   empty table.
4. The agent rows are written by `_v3_agent_add` — a frozen replica of v3's
   `ops.add_agent` (same INSERT, same event payload, through the unchanged
   events.emit). v3 is history now; a frozen replica of it cannot drift.

`build_v3_workspace(root)` leaves:
  project `demo` (+ `legacy`)
  T-0001 done      — pack P-0001, run R-0001 (success), evidence E-0001
  T-0002 in_progress — run R-0002 (open), handoff H-0001 (accepted)
  T-0003 inbox     — projectless capture
  D-0001 decision
  M-0001 global preference (live) · M-0002 project fact with source MS-0001
  agents:
    claude-code  local  — capabilities ["code"], notes
    reviewer     cloud  — notes
    legacy-bot   generic — SECRET-SHAPED notes (warn-only sweep fodder),
                 invoke_hint and trust_level=2 planted by direct SQL (v3
                 shipped no CLI writer for either; direct SQL was the only
                 v3 path, and the migration must carry them verbatim)
"""

from __future__ import annotations

import contextlib
import io
import sqlite3
from pathlib import Path

from agentic_os import cli, db, events, migrations, ops, utils

#: Every table whose contents the U-A1 preservation proof compares.
#: `agent_passports` is absent on purpose: a v3 database has none, and the
#: proof that 3→4 creates it EMPTY is a separate assertion about the
#: migrated database, not a comparison against this one. `agents` is also
#: deliberately absent — the 3→4 step rebuilds it, and the field-for-field
#: legacy-column comparison is its own assertion.
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
    "memory_evidence",
    "memory_sources",
    "memory_source_links",
    "memory_edges",
    "packs",
)

V3_SCHEMA_VERSION = "3"

#: Secret-shaped text a v3 operator could really have stored (the trusted
#: boundary warns, never blocks — D-v0.2.15). The migration must carry it
#: byte-identical; the sweep must find it; no diagnostic may echo it.
SECRET_NOTES = "handoff token = hunter2hunter2hunter2"


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


def _install_v3_agents_schema(db_path: Path) -> None:
    """Replace the empty v4 agent tables with the historical v3 `agents`
    definition and set schema_version back to 3.

    Runs while `agents` holds NO rows, so nothing is rewritten or
    reverse-migrated: DDL on an empty table, which is why it is honest.
    """
    conn = db.connect(db_path)
    try:
        with conn:
            rows = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
            if rows:
                raise AssertionError(
                    "v3 fixture: agents must be empty when the v3 schema is "
                    f"installed (found {rows} rows)"
                )
            # U-A3: a "v3" workspace with the four routing/handoff tables would
            # not be one, and the 4→5 step would fail on its CREATE when this
            # fixture was migrated forward. Dropped children-first via the
            # iterated db.ROUTING_HANDOFF_TABLES (before the agent tables they
            # reference), so a fifth cannot be added without this fixture
            # dropping it too.
            for table, _ddl in reversed(db.ROUTING_HANDOFF_TABLES):
                conn.execute(f"DROP TABLE {table}")
            conn.execute("DROP TABLE agent_passports")
            conn.execute("DROP TABLE agents")
            conn.execute(migrations._V3_AGENTS_DDL.format(table="agents"))
            conn.execute(
                "UPDATE meta SET value = ? WHERE key = 'schema_version'",
                (V3_SCHEMA_VERSION,),
            )
    finally:
        conn.close()


def _v3_agent_add(
    db_path: Path,
    *,
    name: str,
    kind: str = "generic",
    notes: str | None = None,
    capabilities: tuple[str, ...] = (),
) -> int:
    """v3's `agent add`, frozen — a verbatim replica of ops.add_agent as of
    2d242ab (the U-A1 baseline): the same INSERT, the same event payload,
    through the unchanged events.emit. It exists only because U-A1 retired
    the ungoverned writer and a v4 build cannot address a v3 table."""
    import json

    conn = db.connect(db_path)
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO agents (name, kind, capabilities_json, notes) "
                "VALUES (?, ?, ?, ?)",
                (name, kind, json.dumps(list(capabilities)), notes),
            )
            agent_id = cursor.lastrowid
            events.emit(
                conn,
                actor=ops.ACTOR_HUMAN,
                entity="agent",
                entity_id=agent_id,
                action="add",
                payload={
                    "agent": name,
                    "kind": kind,
                    "capabilities": list(capabilities),
                },
            )
        return agent_id
    finally:
        conn.close()


def build_v3_workspace(root: Path) -> Path:
    """Build the v3 fixture workspace under `root`. Returns its aos.db path."""
    root = Path(root).resolve()
    repo = root / "repo with spaces"
    repo.mkdir(parents=True, exist_ok=True)
    legacy_repo = root / "legacy-repo"
    legacy_repo.mkdir(parents=True, exist_ok=True)

    with contextlib.chdir(root):
        # Steps 1-2: production commands, real code, no patching. None of
        # these tables changed at U-A1, so a v4 build writes exactly the rows
        # and events a v3 build wrote — memory included.
        _run("init")
        _run("project", "add", "demo", "--name", "Demo", "--repo", str(repo))
        _run(
            "project", "add", "legacy", "--name", "Legacy",
            "--repo", str(legacy_repo),
        )

        _run("task", "add", "Historical v3 task", "-p", "demo",
             "--accept", "pack + evidence flow works")
        _run("pack", "build", "T-0001", "--for", "claude-code")
        _run("run", "start", "T-0001", "--agent", "claude-code")
        _run("evidence", "add", "T-0001", "--kind", "note",
             "--ref", "v3 proof", "--claim", "it works")
        _run("run", "end", "R-0001", "--outcome", "success", "--summary", "ok")
        _run("done", "T-0001")

        _run("task", "add", "In-flight task", "-p", "demo", "--kind", "code")
        _run("run", "start", "T-0002", "--agent", "claude-code")
        _run("handoff", "create", "T-0002", "--from", "claude-code",
             "--to", "reviewer", "--state", "ready for review")
        _run("handoff", "accept", "H-0001")

        _run("in", "an inbox thought from v3")

        _run("decision", "add", "Use SQLite", "-p", "demo",
             "--decision", "SQLite is the system of record",
             "--alternatives", "Postgres; flat files", "--task", "T-0001")

        _run("memory", "add", "--scope", "global", "--kind", "preference",
             "--key", "commit-style", "--value", "conventional commits",
             "--source", "human", "--confidence", "confirmed")
        _run("memory", "add", "--scope", "project", "--project", "demo",
             "--kind", "fact", "--key", "runtime", "--value", "python 3.13",
             "--source", "human", "--confidence", "inferred")
        _run("memory", "source", "add", "--kind", "file",
             "--locator", "pyproject.toml", "--provenance", "human")
        _run("memory", "source", "link", "M-0002", "MS-0001",
             "--relation", "supports")

        # The last step before the downgrade, with agents still empty.
        _run("sync")

        # Step 3: the agents table becomes v3, and so does the version.
        db_path = root / utils.AOS_DIR_NAME / utils.DB_FILENAME
        _install_v3_agents_schema(db_path)

        # Step 4: the agent rows, through v3's frozen writer.
        _v3_agent_add(
            db_path, name="claude-code", kind="local",
            notes="primary coding agent", capabilities=("code",),
        )
        _v3_agent_add(db_path, name="reviewer", kind="cloud",
                      notes="review only")
        bot_id = _v3_agent_add(db_path, name="legacy-bot", kind="generic",
                               notes=SECRET_NOTES)

        # invoke_hint and trust_level had NO CLI writer at v3 — direct SQL
        # was the only path that ever populated them, so that is how the
        # fixture plants them. The migration must carry both verbatim, and
        # they must stay permanently inert.
        conn = db.connect(db_path)
        try:
            with conn:
                conn.execute(
                    "UPDATE agents SET invoke_hint = ?, trust_level = ? "
                    "WHERE id = ?",
                    ("claude --agent legacy-bot", 2, bot_id),
                )
        finally:
            conn.close()

    return root / utils.AOS_DIR_NAME / utils.DB_FILENAME


def table_contents(db_path: Path, tables=FIXTURE_TABLES) -> dict[str, list]:
    """Every row of every fixture table, ordered deterministically — the
    ground truth the 3→4 migration must preserve field-for-field."""
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


def agents_contents(db_path: Path) -> list[tuple]:
    """The v3 agent rows (or, post-migration, the carried legacy columns) in
    their pinned historical column order."""
    conn = sqlite3.connect(db_path)
    try:
        columns = ", ".join(migrations._V3_AGENTS_COLUMNS)
        return [
            tuple(row)
            for row in conn.execute(
                f"SELECT {columns} FROM agents ORDER BY id"
            ).fetchall()
        ]
    finally:
        conn.close()
