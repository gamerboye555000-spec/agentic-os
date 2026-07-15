"""SQLite layer: one connection helper used everywhere, schema init, and the
transaction helper that carries the domain-row + event-row invariant.

Rules honored here:
- WAL journal mode set at init.
- PRAGMA foreign_keys=ON on EVERY connection; busy_timeout >= 3000ms.
- meta.schema_version = "2" at init; a different version is a hard stop.
  Normal commands NEVER auto-migrate: an older database is refused here and
  the human is pointed at `migrate status/plan/apply` (U-M2, M2.5).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .utils import DB_FILENAME, AosError

SCHEMA_VERSION = "2"

#: The v2 memory claim (U-M2, contract M2.2). The table name is parameterized
#: for exactly one reason: the 1→2 migration builds the new table under a
#: temporary name and renames it, so a MIGRATED table is created from this
#: same DDL as a freshly initialized one and the two cannot drift.
#:
#: `content_sha256` has NO default on purpose — a claim without its integrity
#: hash must be impossible to insert, so there is nothing for a careless
#: writer to fall into.
MEMORY_CLAIM_DDL = """CREATE TABLE {table}(
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

#: Normalized evidence links (U-M2, M2.2). Two integers and a timestamp: no
#: evidence body, claim, ref or any other copied text can live here.
#:
#: The composite PRIMARY KEY is what makes a duplicate link impossible at the
#: storage layer. Plain REFERENCES (NO ACTION) matches every other FK in this
#: schema: with foreign_keys=ON, deleting a linked memory or evidence row is
#: REFUSED. No cascade — the ledger is append-only and has no delete path, so
#: a cascade would only be a silent deletion mechanism for a caller that does
#: not exist.
MEMORY_EVIDENCE_DDL = """CREATE TABLE {table}(
  memory_id INTEGER NOT NULL,
  evidence_id INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (memory_id, evidence_id),
  FOREIGN KEY(memory_id) REFERENCES memory(id),
  FOREIGN KEY(evidence_id) REFERENCES evidence(id)
)"""

MEMORY_TABLE = "memory"
MEMORY_EVIDENCE_TABLE = "memory_evidence"

_SCHEMA_HEAD = """
CREATE TABLE IF NOT EXISTS meta(
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS projects(
  id INTEGER PRIMARY KEY,
  slug TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  repo_path TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active',
  autonomy_level INTEGER NOT NULL DEFAULT 0,
  conventions_md TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks(
  id INTEGER PRIMARY KEY,
  project_id INTEGER,
  parent_id INTEGER,
  title TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'code',
  status TEXT NOT NULL DEFAULT 'ready',
  priority INTEGER NOT NULL DEFAULT 2,
  assignee TEXT,
  spec_md TEXT,
  acceptance_md TEXT,
  branch_hint TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  closed_at TEXT,
  FOREIGN KEY(project_id) REFERENCES projects(id),
  FOREIGN KEY(parent_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL,
  agent TEXT NOT NULL,
  pack_id INTEGER,
  anchor_commit TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  outcome TEXT,
  summary_md TEXT,
  transcript_path TEXT,
  FOREIGN KEY(task_id) REFERENCES tasks(id)
);

CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL,
  actor TEXT NOT NULL,
  entity TEXT NOT NULL,
  entity_id INTEGER,
  action TEXT NOT NULL,
  payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions(
  id INTEGER PRIMARY KEY,
  project_id INTEGER,
  task_id INTEGER,
  title TEXT NOT NULL,
  decision_md TEXT NOT NULL,
  alternatives_md TEXT,
  status TEXT NOT NULL DEFAULT 'accepted',
  supersedes_id INTEGER,
  decided_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence(
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL,
  run_id INTEGER,
  claim TEXT,
  kind TEXT NOT NULL,
  ref TEXT NOT NULL,
  sha256 TEXT,
  provenance TEXT NOT NULL DEFAULT 'human',
  created_at TEXT NOT NULL,
  verified INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY(task_id) REFERENCES tasks(id),
  FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS handoffs(
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL,
  from_agent TEXT NOT NULL,
  to_agent TEXT NOT NULL,
  state_md TEXT NOT NULL,
  pack_id INTEGER,
  created_at TEXT NOT NULL,
  accepted_at TEXT,
  FOREIGN KEY(task_id) REFERENCES tasks(id)
);

"""

_SCHEMA_TAIL = """
CREATE TABLE IF NOT EXISTS packs(
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL,
  path TEXT NOT NULL,
  token_estimate INTEGER NOT NULL,
  inputs_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(task_id, inputs_hash)
);

CREATE TABLE IF NOT EXISTS agents(
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  kind TEXT NOT NULL,
  invoke_hint TEXT,
  capabilities_json TEXT,
  trust_level INTEGER NOT NULL DEFAULT 0,
  notes TEXT
);
"""

#: The canonical v2 schema. Composed rather than typed as one literal so the
#: memory tables have exactly ONE definition in the codebase, shared with the
#: 1→2 migration (M2.3).
SCHEMA_SQL = (
    _SCHEMA_HEAD
    + MEMORY_CLAIM_DDL.format(table=MEMORY_TABLE)
    + ";\n\n"
    + MEMORY_EVIDENCE_DDL.format(table=MEMORY_EVIDENCE_TABLE)
    + ";\n"
    + _SCHEMA_TAIL
)


def connect(db_path: Path) -> sqlite3.Connection:
    """The one connection helper. Every connection gets the same PRAGMAs."""
    conn = sqlite3.connect(db_path, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return None  # uninitialized database
        raise  # real I/O or lock failure: surface as an internal error
    return row["value"] if row else None


def _check_schema_version(conn: sqlite3.Connection) -> None:
    """The version gate every NORMAL command walks through.

    Normal commands never auto-migrate (U-M2 M2.5): an older database is
    refused here, unchanged, and the human is handed the exact three commands
    that move it forward. Only the migration commands read the ledger's
    version themselves (migrations.read_schema_version) and so can open an
    older schema — deliberately, and only to migrate it.
    """
    version = get_meta(conn, "schema_version")
    if version == SCHEMA_VERSION:
        return
    raise AosError(
        f"Database schema_version is {version!r} but this build supports "
        f"{SCHEMA_VERSION!r}. Normal commands never auto-migrate; nothing "
        "was changed. Inspect and migrate it deliberately:\n"
        "  python aos.py migrate status\n"
        "  python aos.py migrate plan\n"
        "  python aos.py migrate apply\n"
        "`migrate apply` snapshots and verifies the database before it "
        "changes anything. See RECOVERY.md."
    )


def open_db(aos_dir: Path) -> sqlite3.Connection:
    """Open an existing workspace database, verifying the schema version."""
    conn = connect(aos_dir / DB_FILENAME)
    try:
        _check_schema_version(conn)
    except BaseException:
        conn.close()
        raise
    return conn


def init_db(db_path: Path) -> tuple[sqlite3.Connection, bool]:
    """Create (or re-open) the workspace database.

    Returns (connection, created). Re-init on the same schema version is an
    idempotent no-op; a different version raises AosError.
    """
    existed = db_path.is_file()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(db_path)
    try:
        if existed:
            _check_schema_version(conn)
            return conn, False
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA_SQL)
        return conn, True
    except BaseException:
        conn.close()
        raise


@contextmanager
def transaction(conn: sqlite3.Connection):
    """One transaction per mutating operation: domain row(s) + event row
    commit together or roll back together."""
    with conn:
        yield conn
