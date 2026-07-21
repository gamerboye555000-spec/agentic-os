"""SQLite layer: one connection helper used everywhere, schema init, and the
transaction helper that carries the domain-row + event-row invariant.

Rules honored here:
- WAL journal mode set at init.
- PRAGMA foreign_keys=ON on EVERY connection; busy_timeout >= 3000ms.
- meta.schema_version = "5" at init; a different version is a hard stop.
  Normal commands NEVER auto-migrate: an older database is refused here and
  the human is pointed at `migrate status/plan/apply` (U-M2 M2.5; U-M3 M3.1).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .utils import DB_FILENAME, AosError

SCHEMA_VERSION = "5"

#: The v3 memory claim (U-M2 M2.2; U-M3 M3.2). The table name is parameterized
#: for exactly one reason: the 1→2 and 2→3 migrations build the new table
#: under a temporary name and rename it, so a MIGRATED table is created from
#: this same DDL as a freshly initialized one and the two cannot drift.
#:
#: `content_sha256` has NO default on purpose — a claim without its integrity
#: hash must be impossible to insert, so there is nothing for a careless
#: writer to fall into. `sensitivity` sits before it for the same reason the
#: U-M2 columns do: the hash column stays last.
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
  sensitivity TEXT NOT NULL DEFAULT 'internal'
    CHECK (sensitivity IN ('public','internal','confidential','restricted')),
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

#: Normalized provenance sources (U-M3, M3.3).
#:
#: The structural CHECK is the point of the table: `evidence` sources name a
#: ledger row and NOTHING else about it, every other kind carries an inert
#: locator string. Enforcing that at the storage boundary as well as in `ops`
#: means a row that copied an evidence ref into `locator`, or invented a
#: locator for an evidence source, cannot exist — not even via raw SQL.
#:
#: `valid_from <= valid_until` is a CHECK for the same reason: an inverted
#: window is not a claim anyone can make about time.
MEMORY_SOURCES_DDL = """CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  project_id INTEGER,
  source_kind TEXT NOT NULL
    CHECK (source_kind IN
      ('evidence','file','url','command','human','agent','artifact')),
  evidence_id INTEGER,
  locator TEXT,
  provenance TEXT NOT NULL,
  sensitivity TEXT NOT NULL
    CHECK (sensitivity IN ('public','internal','confidential','restricted')),
  observed_at TEXT NOT NULL,
  valid_from TEXT,
  valid_until TEXT,
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  CHECK (
    (source_kind = 'evidence' AND evidence_id IS NOT NULL AND locator IS NULL)
    OR
    (source_kind <> 'evidence' AND evidence_id IS NULL AND locator IS NOT NULL)
  ),
  CHECK (valid_from IS NULL OR valid_until IS NULL OR valid_from <= valid_until),
  FOREIGN KEY(project_id) REFERENCES projects(id),
  FOREIGN KEY(evidence_id) REFERENCES evidence(id)
)"""

#: Claim↔source links (U-M3, M3.4). Two ids, a relation, a timestamp, a hash:
#: no source or claim text can live here.
#:
#: UNIQUE(memory_id, source_id, relation) is what makes a duplicate LOGICAL
#: link impossible at the storage layer (D-v0.3.35). Plain REFERENCES (NO
#: ACTION) matches every other FK in this schema: with foreign_keys=ON,
#: deleting a linked claim or source is REFUSED. No cascade — the ledger is
#: append-only and has no delete path, so a cascade would only be a silent
#: deletion mechanism for a caller that does not exist.
MEMORY_SOURCE_LINKS_DDL = """CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  memory_id INTEGER NOT NULL,
  source_id INTEGER NOT NULL,
  relation TEXT NOT NULL
    CHECK (relation IN ('supports','disputes','context','derived_from')),
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  UNIQUE(memory_id, source_id, relation),
  FOREIGN KEY(memory_id) REFERENCES memory(id),
  FOREIGN KEY(source_id) REFERENCES memory_sources(id)
)"""

#: Typed claim↔claim relationships (U-M3, M3.5).
#:
#: Four CHECKs, each pinning one rule the domain layer also enforces — so a
#: writer that bypassed `ops` still cannot store a self-edge, an inverted
#: window, or a symmetric edge written the wrong way round (D-v0.3.36). The
#: last one is why a reverse-duplicate `contradicts` collides with the UNIQUE
#: constraint instead of quietly becoming a second row for the same fact.
MEMORY_EDGES_DDL = """CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  from_memory_id INTEGER NOT NULL,
  to_memory_id INTEGER NOT NULL,
  relation TEXT NOT NULL
    CHECK (relation IN
      ('supports','contradicts','refines','depends_on','related')),
  valid_from TEXT,
  valid_until TEXT,
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  UNIQUE(from_memory_id, to_memory_id, relation),
  CHECK (from_memory_id <> to_memory_id),
  CHECK (valid_from IS NULL OR valid_until IS NULL OR valid_from <= valid_until),
  CHECK (relation NOT IN ('contradicts','related')
         OR from_memory_id < to_memory_id),
  FOREIGN KEY(from_memory_id) REFERENCES memory(id),
  FOREIGN KEY(to_memory_id) REFERENCES memory(id)
)"""

#: The v4 governed agent identity table (U-A1). The table name is
#: parameterized for the same one reason the memory DDLs are: the 3→4
#: migration builds the new table under a temporary name and renames it, so a
#: MIGRATED table and a freshly initialized one are built from this same DDL
#: and their schemas are structurally identical (the D-v0.3.43 rule, applied
#: a third time) — not byte-identical, since SQLite's ALTER TABLE RENAME may
#: add identifier quoting the original CREATE TABLE lacked.
#:
#: The five v3 columns (kind, invoke_hint, capabilities_json, trust_level,
#: notes) survive as INERT legacy history: they lose their NOT NULL/DEFAULT
#: because they are historical facts about legacy rows, not fields of a
#: governed agent — new rows store NULL. They carry no CHECK on purpose:
#: damaged history must remain storable and reportable, never unstorable.
#:
#: The composite FOREIGN KEY is the current-passport pointer's structural
#: guarantee: it must name an existing (agent_id, version) of THIS agent, so
#: a pointer can never name another agent's passport or a missing version.
#: A NULL pointer disables the check (SQLite's composite-FK NULL rule),
#: which is what makes a draft or legacy agent legal.
#:
#: `content_sha256` has NO default, like every hashed record in this schema:
#: an identity row without its integrity hash must be impossible to insert.
AGENTS_DDL = """CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  agent_class TEXT NOT NULL DEFAULT 'custom'
    CHECK (agent_class IN ('system','specialist','custom','temporary')),
  scope TEXT NOT NULL DEFAULT 'global'
    CHECK (scope IN ('global','project')),
  project_id INTEGER,
  lifecycle TEXT NOT NULL DEFAULT 'draft'
    CHECK (lifecycle IN ('draft','active','suspended','archived','revoked')),
  protected INTEGER NOT NULL DEFAULT 0 CHECK (protected IN (0,1)),
  owner TEXT NOT NULL DEFAULT 'human'
    CHECK (owner IN ('human','system')),
  origin TEXT NOT NULL
    CHECK (origin IN ('legacy','create','import')),
  current_passport_version INTEGER,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  kind TEXT,
  invoke_hint TEXT,
  capabilities_json TEXT,
  trust_level INTEGER,
  notes TEXT,
  content_sha256 TEXT NOT NULL,
  CHECK ((scope = 'global' AND project_id IS NULL)
      OR (scope = 'project' AND project_id IS NOT NULL)),
  CHECK (current_passport_version IS NULL OR current_passport_version >= 1),
  FOREIGN KEY(project_id) REFERENCES projects(id),
  FOREIGN KEY(id, current_passport_version)
    REFERENCES agent_passports(agent_id, version)
)"""

#: The immutable passport versions (U-A1). `document` holds the exact
#: canonical bytes of a valid beast.agent-passport/v1 artifact (bounded by
#: U-X1 before storage); `content_sha256` is the ROW record hash — the
#: document's own content digest lives inside the document per U-X1.
#: UNIQUE(agent_id, version) doubles as the composite-FK parent key for the
#: agents pointer. Published rows are never UPDATEd or DELETEd; the only
#: delete path anywhere is `agent discard`, which removes a (draft, v1) row
#: together with its draft agent.
AGENT_PASSPORTS_DDL = """CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  agent_id INTEGER NOT NULL,
  version INTEGER NOT NULL CHECK (version >= 1),
  status TEXT NOT NULL CHECK (status IN ('draft','published')),
  created_at TEXT NOT NULL,
  published_at TEXT,
  document TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  UNIQUE(agent_id, version),
  CHECK ((status = 'draft' AND published_at IS NULL)
      OR (status = 'published' AND published_at IS NOT NULL)),
  FOREIGN KEY(agent_id) REFERENCES agents(id)
)"""

#: The v5 governed routing plan (U-A3). Post-commit immutable: the only UPDATE
#: it ever receives is the hash finalization inside its own creating
#: transaction, between INSERT and COMMIT. The table name is parameterized like
#: every other DDL here — but the 4→5 migration creates it DIRECTLY under its
#: real name (no temp-table rename), so a migrated schema is BYTE-identical to
#: a fresh one, not merely structurally identical (D-v0.4.22).
#:
#: `content_sha256` has NO default, like every hashed record in this schema: a
#: plan row without its integrity hash must be impossible to insert.
#:
#: The three result_status biconditional CHECKs pin the whole `(status,
#: eligible_count, unresolved_count)` truth table (any two imply the third
#: given the enum CHECK; all three are written independently, the
#: MEMORY_EDGES_DDL precedent). `CHECK (supersedes_id IS NULL OR supersedes_id
#: < id)` makes every supersession cycle unrepresentable, not merely
#: self-supersession — a cycle needs a forward edge, and rowids strictly
#: increase with no DELETE path (D-v0.4.27).
ROUTING_PLANS_DDL = """CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  task_id INTEGER,
  project_id INTEGER,
  scope TEXT NOT NULL CHECK (scope IN ('global','project')),
  actor TEXT NOT NULL,
  request_schema TEXT NOT NULL,
  algorithm_version TEXT NOT NULL,
  request_document TEXT NOT NULL,
  request_sha256 TEXT NOT NULL,
  result_status TEXT NOT NULL
    CHECK (result_status IN
      ('resolved','no_eligible_candidates','unresolved')),
  eligible_count INTEGER NOT NULL CHECK (eligible_count >= 0),
  unresolved_count INTEGER NOT NULL CHECK (unresolved_count >= 0),
  excluded_count INTEGER NOT NULL CHECK (excluded_count >= 0),
  supersedes_id INTEGER UNIQUE,
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  CHECK ((scope='global' AND project_id IS NULL)
      OR (scope='project' AND project_id IS NOT NULL)),
  CHECK ((result_status='resolved') = (eligible_count > 0)),
  CHECK ((result_status='unresolved')
       = (eligible_count = 0 AND unresolved_count > 0)),
  CHECK ((result_status='no_eligible_candidates')
       = (eligible_count = 0 AND unresolved_count = 0)),
  CHECK (supersedes_id IS NULL OR supersedes_id < id),
  FOREIGN KEY(task_id) REFERENCES tasks(id),
  FOREIGN KEY(project_id) REFERENCES projects(id),
  FOREIGN KEY(supersedes_id) REFERENCES routing_plans(id)
)"""

#: One post-commit-immutable candidate row per evaluated agent (U-A3). The five
#: `= (verdict='eligible')` biconditionals make rank, ordering_json and the
#: three pins EXACTLY co-extensive with eligibility — a non-eligible row cannot
#: carry pins, and an eligible one cannot lack them.
#:
#: The composite `FOREIGN KEY(agent_id, passport_version) REFERENCES
#: agent_passports(agent_id, version)` (BLOCKER-1) pins an eligible candidate
#: to a REAL immutable passport row — SQLite disables the composite FK when
#: passport_version IS NULL, which is exactly what keeps excluded/unresolved
#: rows (NULL pin) legal, the same NULL rule AGENTS_DDL relies on.
#:
#: `content_sha256` has NO default, like every hashed record here.
ROUTING_PLAN_CANDIDATES_DDL = """CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  plan_id INTEGER NOT NULL,
  agent_id INTEGER NOT NULL,
  verdict TEXT NOT NULL CHECK (verdict IN ('eligible','unresolved','excluded')),
  rank INTEGER CHECK (rank IS NULL OR rank >= 1),
  passport_version INTEGER
    CHECK (passport_version IS NULL OR passport_version >= 1),
  passport_sha256 TEXT,
  identity_sha256 TEXT,
  reasons_json TEXT NOT NULL,
  warnings_json TEXT NOT NULL,
  ordering_json TEXT,
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  UNIQUE(plan_id, agent_id),
  UNIQUE(plan_id, rank),
  CHECK ((verdict='eligible') = (rank IS NOT NULL)),
  CHECK ((verdict='eligible') = (ordering_json IS NOT NULL)),
  CHECK ((verdict='eligible') = (passport_version IS NOT NULL)),
  CHECK ((verdict='eligible') = (passport_sha256 IS NOT NULL)),
  CHECK ((verdict='eligible') = (identity_sha256 IS NOT NULL)),
  FOREIGN KEY(plan_id) REFERENCES routing_plans(id),
  FOREIGN KEY(agent_id) REFERENCES agents(id),
  FOREIGN KEY(agent_id, passport_version)
    REFERENCES agent_passports(agent_id, version)
)"""

#: One row per delegation declaration (U-A3). Append-only transition history
#: plus a mutable, hash-coupled current-state projection: `state`,
#: `updated_at` and `content_sha256` are the only mutable columns, and they
#: only ever move together with one transition row and one event, in one
#: transaction. `decision_id` is a NON-authoritative rationale pointer to an
#: ADR row — never an approval, never read to permit anything (D-v0.4.24).
#:
#: The two composite participant FKs pin each side to a real immutable passport
#: row; `CHECK (from_agent_id <> to_agent_id)` forbids self-handoff; the
#: supersession CHECK mirrors routing_plans' cycle guard (D-v0.4.27).
#:
#: `content_sha256` has NO default, like every hashed record here.
AGENT_HANDOFFS_DDL = """CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  task_id INTEGER NOT NULL,
  plan_id INTEGER,
  from_agent_id INTEGER NOT NULL,
  to_agent_id INTEGER NOT NULL,
  actor TEXT NOT NULL,
  objective_md TEXT NOT NULL,
  expected_evidence_json TEXT NOT NULL,
  min_evidence_count INTEGER NOT NULL DEFAULT 0
    CHECK (min_evidence_count BETWEEN 0 AND 32),
  constraints_md TEXT,
  data_classification TEXT NOT NULL DEFAULT 'internal'
    CHECK (data_classification IN ('public','internal','confidential','restricted')),
  decision_id INTEGER,
  from_passport_version INTEGER NOT NULL CHECK (from_passport_version >= 1),
  from_passport_sha256 TEXT NOT NULL,
  to_passport_version INTEGER NOT NULL CHECK (to_passport_version >= 1),
  to_passport_sha256 TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'proposed'
    CHECK (state IN ('proposed','accepted','refused',
                     'clarification_required','cancelled','superseded')),
  supersedes_id INTEGER UNIQUE,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  CHECK (from_agent_id <> to_agent_id),
  CHECK (supersedes_id IS NULL OR supersedes_id < id),
  FOREIGN KEY(task_id) REFERENCES tasks(id),
  FOREIGN KEY(plan_id) REFERENCES routing_plans(id),
  FOREIGN KEY(from_agent_id) REFERENCES agents(id),
  FOREIGN KEY(to_agent_id) REFERENCES agents(id),
  FOREIGN KEY(decision_id) REFERENCES decisions(id),
  FOREIGN KEY(supersedes_id) REFERENCES agent_handoffs(id),
  FOREIGN KEY(from_agent_id, from_passport_version)
    REFERENCES agent_passports(agent_id, version),
  FOREIGN KEY(to_agent_id, to_passport_version)
    REFERENCES agent_passports(agent_id, version)
)"""

#: The immutable, append-only transition rows behind a handoff's mutable
#: current-state projection (U-A3). `UNIQUE(handoff_id, seq)` makes the
#: sequence total; the from/to-state enums and the reason enum are closed here
#: AND in models.py. Three CHECKs pin domain rules storage-side: from_state <>
#: to_state (no self-edge); accepted may only advance to cancelled/superseded
#: (D-v0.4.26 MAJOR-3); refused/clarification_required require a reason_code.
#:
#: `content_sha256` has NO default, like every hashed record here.
AGENT_HANDOFF_TRANSITIONS_DDL = """CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  handoff_id INTEGER NOT NULL,
  seq INTEGER NOT NULL CHECK (seq >= 1),
  from_state TEXT NOT NULL
    CHECK (from_state IN ('proposed','accepted','clarification_required')),
  to_state TEXT NOT NULL
    CHECK (to_state IN ('accepted','refused','clarification_required',
                        'cancelled','superseded')),
  actor TEXT NOT NULL,
  reason_code TEXT
    CHECK (reason_code IS NULL OR reason_code IN
      ('out_of_scope','missing_capability','conflicting_work',
       'data_classification','objective_unclear','constraints_unclear',
       'evidence_unclear','operator_judgment')),
  note_md TEXT,
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  UNIQUE(handoff_id, seq),
  CHECK (from_state <> to_state),
  CHECK (from_state <> 'accepted'
      OR to_state IN ('cancelled','superseded')),
  CHECK (to_state NOT IN ('refused','clarification_required')
      OR reason_code IS NOT NULL),
  FOREIGN KEY(handoff_id) REFERENCES agent_handoffs(id)
)"""

MEMORY_TABLE = "memory"
MEMORY_EVIDENCE_TABLE = "memory_evidence"
MEMORY_SOURCES_TABLE = "memory_sources"
MEMORY_SOURCE_LINKS_TABLE = "memory_source_links"
MEMORY_EDGES_TABLE = "memory_edges"
AGENTS_TABLE = "agents"
AGENT_PASSPORTS_TABLE = "agent_passports"
ROUTING_PLANS_TABLE = "routing_plans"
ROUTING_PLAN_CANDIDATES_TABLE = "routing_plan_candidates"
AGENT_HANDOFFS_TABLE = "agent_handoffs"
AGENT_HANDOFF_TRANSITIONS_TABLE = "agent_handoff_transitions"

#: The three tables U-M3 adds, paired with their DDL. The 2→3 migration
#: iterates this rather than repeating the CREATEs, so a fresh v3 schema and a
#: migrated one cannot carry different graph tables (M3.12).
MEMORY_GRAPH_TABLES: tuple[tuple[str, str], ...] = (
    (MEMORY_SOURCES_TABLE, MEMORY_SOURCES_DDL),
    (MEMORY_SOURCE_LINKS_TABLE, MEMORY_SOURCE_LINKS_DDL),
    (MEMORY_EDGES_TABLE, MEMORY_EDGES_DDL),
)

#: The four tables U-A3 adds, paired with their DDL, in FK-parent-first order:
#: plans → candidates → handoffs → transitions. The 4→5 migration iterates this
#: rather than repeating the CREATEs, so a fresh v5 schema and a migrated one
#: cannot carry different routing tables — the MEMORY_GRAPH_TABLES shape,
#: applied a second time (D-v0.4.22).
ROUTING_HANDOFF_TABLES: tuple[tuple[str, str], ...] = (
    (ROUTING_PLANS_TABLE, ROUTING_PLANS_DDL),
    (ROUTING_PLAN_CANDIDATES_TABLE, ROUTING_PLAN_CANDIDATES_DDL),
    (AGENT_HANDOFFS_TABLE, AGENT_HANDOFFS_DDL),
    (AGENT_HANDOFF_TRANSITIONS_TABLE, AGENT_HANDOFF_TRANSITIONS_DDL),
)

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
"""

#: The canonical v5 schema. Composed rather than typed as one literal so the
#: memory tables have exactly ONE definition in the codebase, shared with the
#: 1→2 (M2.3) and 2→3 (M3.11) migrations; the agent tables have exactly one,
#: shared with the 3→4 migration (U-A1); and the four routing/handoff tables
#: have exactly one, shared with the 4→5 migration (U-A3, D-v0.4.22).
SCHEMA_SQL = (
    _SCHEMA_HEAD
    + MEMORY_CLAIM_DDL.format(table=MEMORY_TABLE)
    + ";\n\n"
    + MEMORY_EVIDENCE_DDL.format(table=MEMORY_EVIDENCE_TABLE)
    + ";\n\n"
    + ";\n\n".join(
        ddl.format(table=table) for table, ddl in MEMORY_GRAPH_TABLES
    )
    + ";\n"
    + _SCHEMA_TAIL
    + "\n"
    + AGENTS_DDL.format(table=AGENTS_TABLE)
    + ";\n\n"
    + AGENT_PASSPORTS_DDL.format(table=AGENT_PASSPORTS_TABLE)
    + ";\n\n"
    + ";\n\n".join(
        ddl.format(table=table) for table, ddl in ROUTING_HANDOFF_TABLES
    )
    + ";\n"
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
