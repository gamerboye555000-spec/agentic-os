"""A real, historical schema-v2 workspace, built deterministically (U-M3 M3.12).

A *source*, not a committed .db file — for every reason v1_workspace.py gives:
a binary SQLite fixture would be unstable across sqlite versions and page
layouts, would bake in wall-clock timestamps, and would sit in the tree as
exactly the kind of database the packaging allowlist exists to keep out of
aos.pyz. It is also never produced by mutating a real ledger.

The construction is v1_workspace.py's, one version later. Production is at
schema version 3 now, and v3 code CANNOT run against a v2 database — that is
what the version gate guarantees — so the fixture builds in this order:

1. Every non-memory command runs as production v3 code. U-M3 changed nothing
   about those tables, their writers or their events, so the rows a v3 build
   writes for them are identical to the rows a v2 build wrote.
2. `sync` runs while the memory table is still EMPTY.
3. The (still empty) v3 memory table is replaced by the HISTORICAL v2
   definition, the three v3 graph tables are dropped, and schema_version goes
   to "2". No row is rewritten or reverse-migrated: this is pure DDL against
   an empty table, not a downgrade.
4. The memory rows and their evidence links are written by `_v2_memory_add` /
   `_v2_link_evidence` — frozen replicas of v2's `ops.add_memory` and
   `ops.link_memory_evidence` (same INSERTs, same supersede UPDATE, same
   v2 claim hash, same events through the unchanged `events.emit`). v2 is
   history now; a frozen replica of it cannot drift, because v2 itself cannot.

The v2 claim hash comes from `migrations._v2_claim_digest`, which production
itself uses for the 1→2 step — so the fixture and the migration agree about
what a v2 hash is by construction rather than by coincidence. The one thing
that replica does not cover is claims WITH evidence links (the 1→2 step never
produces any), so `_v2_claim_digest_with_links` extends it here, in the
fixture, where the extension belongs.

The mirror therefore carries no memory notes: exactly the workspace of a v2
user who ran `memory add` after their last `sync`. It is derived state, and
doctor is clean on it.

`build_v2_workspace(root)` leaves:
  project `demo` (+ `legacy`)
  T-0001 done      — pack P-0001, run R-0001 (success), evidence E-0001
  T-0002 in_progress — run R-0002 (open), handoff H-0001 (accepted)
  T-0003 ready     — priority 1, spec + acceptance
  T-0004 inbox     — projectless capture
  D-0001 decision · two registered agents
  M-0001 global preference, live, PINNED
  M-0002 project fact, live, one evidence link (E-0001)
  M-0003 project constraint, retired (expired 2020)
  M-0004 global fact, retired, superseded by M-0005
  M-0005 global fact, live, valid_until 2099
  M-0006 project summary, quarantined — a status U-M2 can store but not create
"""

from __future__ import annotations

import contextlib
import io
import sqlite3
from pathlib import Path

from agentic_os import cli, db, events, migrations, ops, utils

#: Every table whose contents the U-M3 preservation proof compares. The three
#: graph tables are absent on purpose: a v2 database has none, and the proof
#: that 2→3 creates them EMPTY is a separate assertion about the migrated
#: database, not a comparison against this one.
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
    "packs",
    "agents",
)

V2_SCHEMA_VERSION = "2"

#: The historical v2 memory tables, verbatim as of 481709a (the U-M3
#: baseline). FROZEN COPIES on purpose: they must not follow
#: db.MEMORY_CLAIM_DDL forward, or the "v2 fixture" would silently become
#: whatever the current schema is and every migration proof built on it would
#: prove nothing.
V2_MEMORY_SQL = """CREATE TABLE memory(
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
  updated_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'live'
    CHECK (status IN ('proposed','live','contested','quarantined','retired')),
  pinned INTEGER NOT NULL DEFAULT 0
    CHECK (pinned IN (0, 1)),
  content_sha256 TEXT NOT NULL
)"""

V2_MEMORY_EVIDENCE_SQL = """CREATE TABLE memory_evidence(
  memory_id INTEGER NOT NULL,
  evidence_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (memory_id, evidence_id),
  FOREIGN KEY(memory_id) REFERENCES memory(id),
  FOREIGN KEY(evidence_id) REFERENCES evidence(id)
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


def _v2_claim_digest_with_links(legacy: dict, evidence_ids) -> str:
    """v2's claim hash for a claim that HAS evidence links.

    `migrations._v2_claim_digest` is production's frozen v2 payload and binds
    an empty link set, because the 1→2 step it serves provably creates no
    links. This fixture needs the one case that step cannot reach, so it
    reuses that frozen payload and substitutes the only leaf that differs.
    Reusing it — rather than retyping the payload — is what makes "the fixture
    and production agree about v2" a fact instead of a hope.
    """
    import hashlib

    from agentic_os import protocols

    payload = migrations._v2_claim_payload(
        legacy, legacy["status"], legacy["pinned"]
    )
    payload["evidence_ids"] = sorted(set(evidence_ids))
    return hashlib.sha256(protocols.serialize_canonical(payload)).hexdigest()


def _install_v2_memory_schema(db_path: Path) -> None:
    """Replace the empty v3 memory tables with their historical v2
    definitions, drop the v3 graph tables, and set schema_version back to 2.

    Runs while `memory` holds NO rows, so nothing is rewritten or
    reverse-migrated: DDL on an empty table, which is why it is honest.
    """
    conn = db.connect(db_path)
    try:
        with conn:
            rows = conn.execute("SELECT COUNT(*) FROM memory").fetchone()[0]
            if rows:
                raise AssertionError(
                    "v2 fixture: memory must be empty when the v2 schema is "
                    f"installed (found {rows} rows)"
                )
            agent_rows = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
            if agent_rows:
                raise AssertionError(
                    "v2 fixture: agents must be empty when the v2 schema is "
                    f"installed (found {agent_rows} rows)"
                )
            # Reverse order: memory_source_links references memory_sources.
            for table, _ddl in reversed(db.MEMORY_GRAPH_TABLES):
                conn.execute(f"DROP TABLE {table}")
            conn.execute("DROP TABLE memory_evidence")
            conn.execute("DROP TABLE memory")
            conn.execute(V2_MEMORY_SQL)
            conn.execute(V2_MEMORY_EVIDENCE_SQL)
            # U-A1: a "v2" workspace with a v4 agents table (or any
            # agent_passports) would not be one. The v3 agents DDL — which
            # IS the v2 agents DDL; the table was unchanged from Night-1
            # through v3 — comes from migrations._V3_AGENTS_DDL, the same
            # frozen text the 3→4 step documents as its input shape.
            conn.execute("DROP TABLE agent_passports")
            conn.execute("DROP TABLE agents")
            conn.execute(migrations._V3_AGENTS_DDL.format(table="agents"))
            conn.execute(
                "UPDATE meta SET value = ? WHERE key = 'schema_version'",
                (V2_SCHEMA_VERSION,),
            )
    finally:
        conn.close()


def _v2_agent_add(
    db_path: Path,
    *,
    name: str,
    kind: str = "generic",
    notes: str | None = None,
    capabilities: tuple[str, ...] = (),
) -> None:
    """v2's `agent add`, frozen — a verbatim replica of ops.add_agent as of
    2d242ab (the agents table and its writer were unchanged from Night-1
    through v3). It exists only because U-A1 retired the ungoverned writer
    and a v4 build cannot address a v2 table."""
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


def _v2_memory_add(
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
    status: str = "live",
    pinned: int = 0,
    evidence_ids: tuple[int, ...] = (),
) -> int:
    """v2's `memory add`, frozen.

    A replica of ops.add_memory as of 481709a: the same columns, the same
    evidence-link rows, the same supersede UPDATE (which retires the old claim
    and re-hashes it), the same v2 claim hash, through the unchanged
    events.emit. It exists only because v3's writer cannot address a v2 table.

    `status` is a parameter because U-M2 could STORE `quarantined` while
    shipping no command that produces it — the fixture carries one so the 2→3
    migration is proven to preserve a status, not just the two it is easy to
    make.
    """
    conn = db.connect(db_path)
    try:
        now = utils.utc_now_iso()
        with conn:
            cursor = conn.execute(
                "INSERT INTO memory (scope, project_id, kind, key, value_md, "
                "source, confidence, valid_from, valid_until, updated_at, "
                "status, pinned, content_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    scope, project_id, kind, key, value, source, confidence,
                    now, valid_until, now, status, pinned, "",
                ),
            )
            memory_id = cursor.lastrowid
            if memory_id is None:
                raise AssertionError("v2 fixture: memory INSERT returned no rowid")
            for evidence_id in sorted(set(evidence_ids)):
                conn.execute(
                    "INSERT INTO memory_evidence (memory_id, evidence_id, "
                    "created_at) VALUES (?, ?, ?)",
                    (memory_id, evidence_id, now),
                )
            if supersedes_id is not None:
                conn.execute(
                    "UPDATE memory SET superseded_by = ?, status = ?, "
                    "updated_at = ? WHERE id = ?",
                    (memory_id, "retired", now, supersedes_id),
                )
                _rehash_v2(conn, supersedes_id)
            _rehash_v2(conn, memory_id)
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
                    "status": status,
                    "pinned": bool(pinned),
                    "evidence": [f"E-{e:04d}" for e in sorted(set(evidence_ids))],
                },
            )
        return memory_id
    finally:
        conn.close()


def _rehash_v2(conn: sqlite3.Connection, memory_id: int) -> None:
    """Recompute a v2 claim's hash from its stored fields and links."""
    row = conn.execute("SELECT * FROM memory WHERE id = ?", (memory_id,)).fetchone()
    legacy = dict(row)
    links = [
        r["evidence_id"]
        for r in conn.execute(
            "SELECT evidence_id FROM memory_evidence WHERE memory_id = ? "
            "ORDER BY evidence_id",
            (memory_id,),
        )
    ]
    digest = _v2_claim_digest_with_links(legacy, links)
    conn.execute(
        "UPDATE memory SET content_sha256 = ? WHERE id = ?", (digest, memory_id)
    )


def build_v2_workspace(root: Path) -> Path:
    """Build the v2 fixture workspace under `root`. Returns its aos.db path."""
    root = Path(root).resolve()
    repo = root / "repo with spaces"
    repo.mkdir(parents=True, exist_ok=True)
    legacy_repo = root / "legacy-repo"
    legacy_repo.mkdir(parents=True, exist_ok=True)

    with contextlib.chdir(root):
        # Steps 1-2: production commands, real code, no patching. None of
        # these tables changed at U-M3, so a v3 build writes exactly the rows
        # and events a v2 build wrote.
        _run("init")
        _run("project", "add", "demo", "--name", "Demo", "--repo", str(repo))
        _run(
            "project", "add", "legacy", "--name", "Legacy",
            "--repo", str(legacy_repo),
        )

        _run("task", "add", "Historical v2 task", "-p", "demo",
             "--accept", "pack + evidence flow works")
        _run("pack", "build", "T-0001", "--for", "claude-code")
        _run("run", "start", "T-0001", "--agent", "claude-code")
        _run("evidence", "add", "T-0001", "--kind", "note",
             "--ref", "v2 proof", "--claim", "it works")
        _run("run", "end", "R-0001", "--outcome", "success", "--summary", "ok")
        _run("done", "T-0001")

        _run("task", "add", "In-flight task", "-p", "demo", "--kind", "code")
        _run("run", "start", "T-0002", "--agent", "claude-code")
        _run("handoff", "create", "T-0002", "--from", "claude-code",
             "--to", "reviewer", "--state", "ready for review")
        _run("handoff", "accept", "H-0001")

        _run("task", "add", "Planned task", "-p", "legacy", "--priority", "1",
             "--kind", "writing", "--accept", "docs updated",
             "--spec", "write it")

        _run("in", "an inbox thought from v2")

        _run("decision", "add", "Use SQLite", "-p", "demo",
             "--decision", "SQLite is the system of record",
             "--alternatives", "Postgres; flat files", "--task", "T-0001")

        # The last v3-code step, with memory still empty.
        _run("sync")

        # Step 3: the memory and agent tables become v2, and so does the
        # version.
        db_path = root / utils.AOS_DIR_NAME / utils.DB_FILENAME
        demo_id = _project_id(db_path, "demo")
        _install_v2_memory_schema(db_path)

        # Step 4a: the two registered agents, through v2's frozen writer.
        _v2_agent_add(
            db_path, name="claude-code", kind="local",
            notes="primary coding agent", capabilities=("code",),
        )
        _v2_agent_add(db_path, name="reviewer", kind="cloud",
                      notes="review only")

        # Step 4: the memory rows, through v2's frozen writer.

        # M-0001: live, PINNED — proves pin survives 2→3.
        _v2_memory_add(
            db_path, scope="global", project_id=None, kind="preference",
            key="commit-style", value="conventional commits",
            source="human", confidence="confirmed", pinned=1,
        )
        # M-0002: live, WITH an evidence link — the row memory_evidence
        # preservation is proven against.
        _v2_memory_add(
            db_path, scope="project", project_id=demo_id, kind="fact",
            key="runtime", value="python 3.13",
            source="human", confidence="inferred", evidence_ids=(1,),
        )
        # M-0003: retired by expiry.
        _v2_memory_add(
            db_path, scope="project", project_id=demo_id, kind="constraint",
            key="deploy-window", value="fridays only, until the v2 freeze",
            source="human", confidence="single", valid_until="2020-01-01",
            status="retired",
        )
        # M-0004 retired by supersession, M-0005 its live successor.
        old_id = _v2_memory_add(
            db_path, scope="global", project_id=None, kind="fact",
            key="editor", value="vim, allegedly",
            source="human", confidence="assumed",
        )
        _v2_memory_add(
            db_path, scope="global", project_id=None, kind="fact",
            key="editor", value="whatever ships the work",
            source="human", confidence="confirmed",
            valid_until="2099-12-31", supersedes_id=old_id,
        )
        # M-0006: a status U-M2 stores but ships no command to produce.
        _v2_memory_add(
            db_path, scope="project", project_id=demo_id, kind="summary",
            key="review-notes", value="held for the U-M4 workflow",
            source="human", confidence="assumed", status="quarantined",
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
