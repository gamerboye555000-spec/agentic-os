"""A real, historical schema-v1 workspace, built deterministically (U-M1 M1.11).

A *source*, not a committed .db file. A binary SQLite fixture would be
unstable across sqlite versions and page layouts, would bake in wall-clock
timestamps from `utils.utc_now_iso()`, and would sit in the tree as exactly
the kind of database the packaging allowlist exists to keep out of aos.pyz.

Built with production CLI commands — never raw INSERTs — so the fixture is a
database a v1 user could actually have produced.

U-M2 (contract M2.14) forces one change. Production is at schema version 2
now, and v2 code CANNOT run against a v1 database — that is precisely what
the version gate exists to guarantee, so no amount of patching will make
`pack build` or `sync` read a v1 memory table. The fixture therefore builds
in this order:

1. Every non-memory command runs as production v2 code. U-M2 changed nothing
   about those tables, their writers or their events, so the rows a v2 build
   writes for them are identical to the rows a v1 build wrote.
2. `sync` runs while the memory table is still EMPTY.
3. The (still empty) v2 memory table is replaced by the HISTORICAL v1
   definition, `memory_evidence` is dropped, and schema_version goes to "1".
   No row is rewritten or reverse-migrated: this is pure DDL against an empty
   table, not a downgrade.
4. The memory rows are written by `_v1_memory_add` — a frozen replica of v1's
   `ops.add_memory` (same INSERT, same supersede UPDATE, same event through
   the unchanged `events.emit`). v1 is history now; a frozen replica of it
   cannot drift, because v1 itself cannot.

The mirror therefore carries no memory notes: exactly the workspace of a v1
user who ran `memory add` after their last `sync`. It is derived state, and
doctor is clean on it (no dangling links, no strays).

`build_v1_workspace(root)` leaves:
  project `demo` (+ `legacy`)
  T-0001 done      — pack P-0001, run R-0001 (success), evidence E-0001
  T-0002 in_progress — run R-0002 (open), handoff H-0001 (accepted)
  T-0003 ready     — priority 1, spec + acceptance
  T-0004 inbox     — projectless capture
  D-0001 decision · two registered agents
  M-0001 global preference, active        → migrates to live
  M-0002 project fact, active             → migrates to live
  M-0003 expired (valid_until in 2020)    → migrates to retired
  M-0004 superseded by M-0005             → migrates to retired
  M-0005 successor, valid_until in 2099   → migrates to live
"""

from __future__ import annotations

import contextlib
import io
import sqlite3
from pathlib import Path

from agentic_os import cli, db, events, migrations, ops, utils

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

#: The historical v1 memory table, verbatim as of 9b2f43d (the U-M2 baseline)
#: — the ONLY table the 1→2 migration touches, and so the only one this
#: fixture has to pin. A FROZEN COPY on purpose: it must not follow
#: db.MEMORY_CLAIM_DDL forward, or the "v1 fixture" would silently become
#: whatever the current schema is and every migration proof built on it would
#: prove nothing.
V1_SCHEMA_VERSION = "1"

V1_MEMORY_SQL = """CREATE TABLE IF NOT EXISTS memory(
  id INTEGER PRIMARY KEY,
  scope TEXT NOT NULL,
  project_id INTEGER,
  kind TEXT NOT NULL,
  key TEXT NOT NULL,
  value_md TEXT NOT NULL,
  source TEXT NOT NULL,
  confidence TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_until TEXT,
  superseded_by INTEGER,
  updated_at TEXT NOT NULL
)"""


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


def _install_v1_memory_schema(db_path: Path) -> None:
    """Replace the empty current-schema memory table with its historical v1
    definition, drop every table v1 never had, and set schema_version back to 1.

    Runs while `memory` holds NO rows, so nothing is rewritten or
    reverse-migrated: this is DDL on an empty table, which is why it is
    honest. What comes out is byte-for-byte the v1 schema, and the rows that
    follow are written by the frozen v1 writer.

    U-M3 (M3.12) adds the graph tables to what must go. A "v1" workspace that
    still carried memory_sources would not be one — and the 2→3 step, which
    creates those tables, would fail on the second CREATE when this fixture
    was migrated all the way forward. The list is db.MEMORY_GRAPH_TABLES
    rather than three literals, so a fourth graph table cannot be added
    without this fixture dropping it too.

    U-A1 adds the agent tables to what must go, for the same reason: a "v1"
    workspace with a v4 `agents` table (or any `agent_passports`) would not
    be one, and the 3→4 step would fail on its CREATE when this fixture was
    migrated forward. The v3 agents DDL comes from
    migrations._V3_AGENTS_DDL — the same frozen text the 3→4 step documents
    as its input shape — so the fixture and the migration agree about v3 by
    construction. Rows follow via the frozen v3 agent writer below.
    """
    conn = db.connect(db_path)
    try:
        with conn:
            rows = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
            if rows:
                raise AssertionError(
                    "v1 fixture: memory must be empty when the v1 schema is "
                    f"installed (found {rows} rows)"
                )
            agent_rows = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
            if agent_rows:
                raise AssertionError(
                    "v1 fixture: agents must be empty when the v1 schema is "
                    f"installed (found {agent_rows} rows)"
                )
            # U-A3 adds the four routing/handoff tables to what must go, for
            # the same reason MEMORY_GRAPH_TABLES and the agent tables do: a
            # "v1" workspace with a routing_plans table would not be one, and
            # the 4→5 step, which creates those tables, would fail on its
            # CREATE when this fixture was migrated all the way forward. The
            # list is db.ROUTING_HANDOFF_TABLES rather than four literals, so a
            # fifth routing table cannot be added without this fixture dropping
            # it too. Children before parents (reversed FK-parent order).
            for table, _ddl in reversed(db.ROUTING_HANDOFF_TABLES):
                conn.execute(f"DROP TABLE {table}")
            for table, _ddl in reversed(db.MEMORY_GRAPH_TABLES):
                conn.execute(f"DROP TABLE {table}")
            conn.execute("DROP TABLE memory_evidence")
            conn.execute("DROP TABLE memory")
            conn.execute(V1_MEMORY_SQL)
            conn.execute("DROP TABLE agent_passports")
            conn.execute("DROP TABLE agents")
            conn.execute(migrations._V3_AGENTS_DDL.format(table="agents"))
            conn.execute(
                "UPDATE meta SET value = ? WHERE key = 'schema_version'",
                (V1_SCHEMA_VERSION,),
            )
    finally:
        conn.close()


def _v1_agent_add(
    db_path: Path,
    *,
    name: str,
    kind: str = "generic",
    notes: str | None = None,
    capabilities: tuple[str, ...] = (),
) -> None:
    """v1's `agent add`, frozen.

    A verbatim replica of ops.add_agent as of 2d242ab (the U-A1 baseline;
    the agents table and its writer were unchanged from Night-1 through v3):
    the same INSERT, the same event payload, through the unchanged
    events.emit. It exists only because U-A1 retired the ungoverned writer
    and a v4 build cannot address a v3 table.
    """
    import json

    conn = db.connect(db_path)
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO agents (name, kind, capabilities_json, notes) "
                "VALUES (?, ?, ?, ?)",
                (name, kind, json.dumps(list(capabilities)), notes),
            )
            events.emit(
                conn,
                actor=ops.ACTOR_HUMAN,
                entity="agent",
                entity_id=cursor.lastrowid,
                action="add",
                payload={
                    "agent": name,
                    "kind": kind,
                    "capabilities": list(capabilities),
                },
            )
    finally:
        conn.close()


def _v1_memory_add(
    db_path: Path,
    *,
    scope: str,
    project_id: int | None,
    kind: str,
    key: str,
    value: str,
    source: str,
    confidence: str,
    valid_until: str | None = None,
    supersedes_id: int | None = None,
) -> int:
    """v1's `memory add`, frozen.

    A verbatim replica of ops.add_memory as of 9b2f43d: the same columns, the
    same supersede UPDATE, the same event payload, through the unchanged
    events.emit. It exists only because v2's writer cannot address a v1 table.
    """
    conn = db.connect(db_path)
    try:
        now = utils.utc_now_iso()
        with conn:
            cursor = conn.execute(
                "INSERT INTO memory (scope, project_id, kind, key, value_md, "
                "source, confidence, valid_from, valid_until, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    scope, project_id, kind, key, value, source, confidence,
                    now, valid_until, now,
                ),
            )
            memory_id = cursor.lastrowid
            if supersedes_id is not None:
                conn.execute(
                    "UPDATE memory SET superseded_by = ?, updated_at = ? "
                    "WHERE id = ?",
                    (memory_id, now, supersedes_id),
                )
            events.emit(
                conn,
                actor=ops.ACTOR_HUMAN,
                entity="memory",
                entity_id=memory_id,
                action="add",
                payload={
                    "memory": f"M-{memory_id:04d}",
                    "scope": scope,
                    "project": None,
                    "kind": kind,
                    "key": key,
                    "confidence": confidence,
                    "valid_until": valid_until,
                    "supersedes": (
                        f"M-{supersedes_id:04d}" if supersedes_id else None
                    ),
                },
            )
        if memory_id is None:
            raise AssertionError("v1 fixture: memory INSERT returned no rowid")
        return memory_id
    finally:
        conn.close()


def build_v1_workspace(root: Path) -> Path:
    """Build the v1 fixture workspace under `root`. Returns its aos.db path."""
    root = Path(root).resolve()
    repo = root / "repo with spaces"
    repo.mkdir(parents=True, exist_ok=True)
    legacy_repo = root / "legacy-repo"
    legacy_repo.mkdir(parents=True, exist_ok=True)

    with contextlib.chdir(root):
        # Steps 1-2: production commands, real code, no patching. None of
        # these tables changed at U-M2, so a v2 build writes exactly the rows
        # and events a v1 build wrote.
        _run("init")
        _run("project", "add", "demo", "--name", "Demo", "--repo", str(repo))
        _run(
            "project", "add", "legacy", "--name", "Legacy",
            "--repo", str(legacy_repo),
        )

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

        # The last v2-code step, with memory still empty.
        _run("sync")

        # Step 3: the memory and agent tables become v1, and so does the
        # version.
        db_path = root / utils.AOS_DIR_NAME / utils.DB_FILENAME
        demo_id = _project_id(db_path, "demo")
        _install_v1_memory_schema(db_path)

        # Step 4a: the two registered agents, through v1's frozen writer —
        # exactly the workspace of a v1 user who ran `agent add` after their
        # last `sync`, like the memory rows below.
        _v1_agent_add(
            db_path, name="claude-code", kind="local",
            notes="primary coding agent", capabilities=("code",),
        )
        _v1_agent_add(db_path, name="reviewer", kind="cloud",
                      notes="review only")

        # Step 4: the memory rows, through v1's frozen writer.

        # Two ACTIVE rows → must migrate to live.
        _v1_memory_add(
            db_path, scope="global", project_id=None, kind="preference",
            key="commit-style", value="conventional commits",
            source="human", confidence="confirmed",
        )
        _v1_memory_add(
            db_path, scope="project", project_id=demo_id, kind="fact",
            key="runtime", value="python 3.13",
            source="human", confidence="inferred",
        )
        # An EXPIRED row → must migrate to retired.
        _v1_memory_add(
            db_path, scope="project", project_id=demo_id, kind="constraint",
            key="deploy-window", value="fridays only, until the v1 freeze",
            source="human", confidence="single", valid_until="2020-01-01",
        )
        # A SUPERSEDED row (M-0004) and its live successor (M-0005).
        old_id = _v1_memory_add(
            db_path, scope="global", project_id=None, kind="fact",
            key="editor", value="vim, allegedly",
            source="human", confidence="assumed",
        )
        _v1_memory_add(
            db_path, scope="global", project_id=None, kind="fact",
            key="editor", value="whatever ships the work",
            source="human", confidence="confirmed",
            valid_until="2099-12-31", supersedes_id=old_id,
        )

    return root / utils.AOS_DIR_NAME / utils.DB_FILENAME


def _project_id(db_path: Path, slug: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT id FROM projects WHERE slug = ?", (slug,)
        ).fetchone()
        if row is None:
            raise AssertionError(f"fixture project {slug!r} missing")
        return row[0]
    finally:
        conn.close()


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
