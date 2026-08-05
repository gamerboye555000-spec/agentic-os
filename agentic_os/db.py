"""SQLite layer: one connection helper used everywhere, schema init, and the
transaction helper that carries the domain-row + event-row invariant.

Rules honored here:
- WAL journal mode set at init.
- PRAGMA foreign_keys=ON on EVERY connection; busy_timeout >= 3000ms.
- meta.schema_version = "7" at init; a different version is a hard stop.
  Normal commands NEVER auto-migrate: an older database is refused here and
  the human is pointed at `migrate status/plan/apply` (U-M2 M2.5; U-M3 M3.1).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .utils import DB_FILENAME, AosError

SCHEMA_VERSION = "7"

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

#: The v6 derived snapshot PROJECTION (U-W2.2 §5.1, D-v0.4.85). Not the
#: snapshot: the reducer's `aos.workflow-snapshot/v1` value is rebuilt by
#: `fold(workflow_events)` plus the two stored bodies on every command, and
#: `content_sha256` — the snapshot RECORD digest, not a row hash — is the
#: agreement gate. Seven derived snapshot fields therefore need no column.
#:
#: `id` is the integer of the reducer's DERIVED `WF-<n>` identity, never an
#: allocated sequence, so re-admitting the same artifact lands on the same
#: primary key and `UNIQUE(work_spec_sha256)` agrees by construction.
#:
#: `revision` is the compare-and-swap column and `content_sha256` the record
#: digest; neither carries a default, like every hashed record in this schema —
#: a row without them must be impossible to insert.
#:
#: The three structural CHECKs mirror the reducer's own `_verify_snapshot`
#: cross-field rules, so a projection the reducer would refuse cannot be
#: stored: a pending dispatch pointer only in `validated` or `retrying`
#: (U-W3 §11.2 — a retry is a dispatch issued from `retrying`), a pending
#: cancel pointer only post-dispatch, and no runtime task before the queue
#: accepted. `retrying` is deliberately ABSENT from the third CHECK's list,
#: which is what lets a retrying workflow keep the runtime task binding of the
#: attempt that failed; and absent from the second, because `retrying` is not
#: a post-dispatch state and cancellation from it is local.
#:
#: The table name is parameterized like every other DDL here — and the 5→6
#: migration creates it DIRECTLY under its real name (no temp-table rename),
#: so a migrated schema is BYTE-identical to a fresh one (the D-v0.4.22 rule,
#: applied a third time).
WORKFLOWS_DDL = """CREATE TABLE {table}(
  id INTEGER PRIMARY KEY CHECK (id >= 1),
  task_id INTEGER NOT NULL,
  work_spec_sha256 TEXT NOT NULL UNIQUE,
  report_sha256 TEXT NOT NULL,
  snapshot_sha256 TEXT NOT NULL,
  registry_version INTEGER NOT NULL CHECK (registry_version >= 1),
  compile_status TEXT NOT NULL
    CHECK (compile_status IN ('valid','warning','requires_external_authority')),
  work_spec_document TEXT NOT NULL,
  report_document TEXT NOT NULL,
  state TEXT NOT NULL
    CHECK (state IN ('compiled','validated','awaiting_approval','scheduled',
                     'running','waiting_input','waiting_approval','paused',
                     'retrying','compensating','succeeded','failed',
                     'cancelled','compensated')),
  revision INTEGER NOT NULL CHECK (revision >= 1),
  policy_version INTEGER NOT NULL CHECK (policy_version >= 1),
  approval_required INTEGER NOT NULL CHECK (approval_required IN (0,1)),
  dispatch_intent_id TEXT,
  cancel_intent_id TEXT,
  runtime_task_uuid TEXT,
  queue_route TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  CHECK (dispatch_intent_id IS NULL OR state IN ('validated','retrying')),
  CHECK (cancel_intent_id IS NULL OR state IN
         ('scheduled','running','waiting_input','waiting_approval','paused')),
  CHECK (runtime_task_uuid IS NULL
      OR state NOT IN ('compiled','validated','awaiting_approval')),
  FOREIGN KEY(task_id) REFERENCES tasks(id)
)"""

#: The AUTHORITATIVE append-only workflow history (U-W2.2 §5.2, D-v0.4.86).
#: Immutable in full: no code path in this slice or any other issues UPDATE or
#: DELETE against this table (the `agent_handoff_transitions` discipline).
#:
#: The record's fields are stored as columns rather than the record stored
#: twice; `content_sha256` is the EVENT RECORD digest the reducer sealed, and
#: recomputing it from the reconstituted columns is the proof the
#: reconstitution is faithful.
#:
#: The two biconditional CHECKs close two U-W2 §7 rules storage-side:
#: `from_state` is null exactly on `workflow_admitted` (the creation
#: pseudo-edge), and no event may claim a self-edge. The self-edge guard is
#: written with explicit NULL guards; under SQLite's NULL-CHECK rule they are
#: redundant, and they are written anyway so the intent is readable rather
#: than inferred.
#:
#: The `event` CHECK makes `history_unknown_event` unreachable through
#: storage — deliberately: the code stays in the reducer's vocabulary because
#: `verify_history` is also callable on a caller-supplied list.
WORKFLOW_EVENTS_DDL = """CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  workflow_id INTEGER NOT NULL,
  seq INTEGER NOT NULL CHECK (seq >= 1),
  event TEXT NOT NULL
    CHECK (event IN ('workflow_admitted','workflow_validated',
                     'approval_requested','approval_recorded',
                     'dispatch_requested','dispatch_rejected',
                     'dispatch_revoked','dispatch_accepted','run_started',
                     'run_waiting_input','run_waiting_approval','run_paused',
                     'run_resumed','cancel_requested','workflow_succeeded',
                     'workflow_failed','workflow_cancelled',
                     'policy_version_adopted','attempt_failed',
                     'checkpoint_recorded','checkpoint_restored',
                     'compensation_started','compensation_applied',
                     'compensation_failed')),
  from_state TEXT
    CHECK (from_state IS NULL OR from_state IN
           ('compiled','validated','awaiting_approval','scheduled','running',
            'waiting_input','waiting_approval','paused','retrying',
            'compensating','succeeded','failed','cancelled','compensated')),
  to_state TEXT
    CHECK (to_state IS NULL OR to_state IN
           ('compiled','validated','awaiting_approval','scheduled','running',
            'waiting_input','waiting_approval','paused','retrying',
            'compensating','succeeded','failed','cancelled','compensated')),
  revision INTEGER NOT NULL CHECK (revision >= 1),
  policy_version INTEGER NOT NULL CHECK (policy_version >= 1),
  command_id TEXT NOT NULL,
  command_sha256 TEXT NOT NULL,
  actor TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  UNIQUE(workflow_id, seq),
  CHECK (from_state IS NULL OR to_state IS NULL OR from_state <> to_state),
  CHECK ((event = 'workflow_admitted') = (from_state IS NULL)),
  FOREIGN KEY(workflow_id) REFERENCES workflows(id)
)"""

#: Accepted-command dedupe and replay (U-W2.2 §5.3, D-v0.4.90). ACCEPTED
#: commands only: a refused command stores nothing here or anywhere else, and
#: the NOT NULL `event_seq_*` pair makes a zero-event command row
#: unrepresentable — the storage-side proof that every accepted command
#: appends at least one event.
#:
#: `CHECK (resulting_revision = expected_revision + 1)` is U-W2 §10's "+1 per
#: accepted command", closed storage-side for every verb including the
#: stateless ones. `CHECK ((command='admit_work_spec') = (expected_revision =
#: 0))` is the creation rule: admission asserts 0, and a non-admit command
#: carrying 0 can never be accepted because `revision` starts at 1 and only
#: grows.
#:
#: `command_id UNIQUE` carries the dedupe index; no explicit index exists.
WORKFLOW_COMMANDS_DDL = """CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  workflow_id INTEGER NOT NULL,
  command_id TEXT NOT NULL UNIQUE,
  command TEXT NOT NULL
    CHECK (command IN ('admit_work_spec','validate','request_approval',
                       'record_approval','request_dispatch','revoke_dispatch',
                       'request_cancel','record_queue_receipt','record_result',
                       'adopt_policy_version','record_checkpoint',
                       'record_restore','record_compensation')),
  command_sha256 TEXT NOT NULL,
  expected_revision INTEGER NOT NULL CHECK (expected_revision >= 0),
  resulting_revision INTEGER NOT NULL CHECK (resulting_revision >= 1),
  event_seq_first INTEGER NOT NULL CHECK (event_seq_first >= 1),
  event_seq_last INTEGER NOT NULL CHECK (event_seq_last >= event_seq_first),
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  CHECK (resulting_revision = expected_revision + 1),
  CHECK ((command = 'admit_work_spec') = (expected_revision = 0)),
  FOREIGN KEY(workflow_id) REFERENCES workflows(id)
)"""

#: The outbox (U-W2.2 §5.4): the record of what AOS asked the queue for.
#: `workflows.dispatch_intent_id`/`cancel_intent_id` are pending POINTERS;
#: this table is the record, and every intent ever emitted stays here with its
#: status. There is no `delivered_at`, no `attempts`, no `next_visible_at` and
#: no worker column, because every one of those is the private runtime's or
#: U-W3's — the store claims no transport authority.
#:
#: The biconditional CHECK pins that `resolved` means "a receipt closed it";
#: `revoked` means a revocation withdrew it and no receipt will ever come.
WORKFLOW_INTENTS_DDL = """CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  workflow_id INTEGER NOT NULL,
  intent_id TEXT NOT NULL UNIQUE,
  intent_kind TEXT NOT NULL
    CHECK (intent_kind IN ('dispatch','cancel','compensate')),
  idempotency_key TEXT NOT NULL,
  queue_route TEXT NOT NULL,
  document TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('outstanding','resolved','revoked')),
  resolved_receipt_id TEXT,
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  CHECK ((status = 'resolved') = (resolved_receipt_id IS NOT NULL)),
  FOREIGN KEY(workflow_id) REFERENCES workflows(id)
)"""

#: The inbox (U-W2.2 §5.5): the verbatim record of what the runtime reported,
#: so even a runtime that misreports is auditable. INSERT-ONCE — a stored
#: receipt IS an applied receipt, because a refused receipt stores nothing;
#: that is what makes the receipt dedupe axis sound.
#:
#: The four CHECKs mirror `workflow_engine._RECEIPT_INTENT_REQUIRED`,
#: `_RECEIPT_INTENT_ALLOWED`, `_RECEIPT_UUID_REQUIRED` and
#: `_RECEIPT_UUID_FORBIDDEN` exactly, so the storage boundary and the
#: reducer's closed vocabulary cannot disagree (the MEMORY_STATUSES
#: domain-plus-storage rule).
WORKFLOW_RECEIPTS_DDL = """CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  workflow_id INTEGER NOT NULL,
  receipt_id TEXT NOT NULL UNIQUE,
  receipt_kind TEXT NOT NULL
    CHECK (receipt_kind IN ('accepted','rejected','started','waiting_input',
                            'waiting_approval','paused','resumed','cancelled',
                            'failed')),
  intent_id TEXT,
  runtime_task_uuid TEXT,
  document TEXT NOT NULL,
  receipt_sha256 TEXT NOT NULL,
  created_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  CHECK (intent_id IS NOT NULL
      OR receipt_kind NOT IN ('accepted','rejected')),
  CHECK (intent_id IS NULL
      OR receipt_kind IN ('accepted','rejected','cancelled')),
  CHECK (runtime_task_uuid IS NOT NULL
      OR receipt_kind NOT IN ('accepted','started','waiting_input',
                              'waiting_approval','paused','resumed')),
  CHECK (runtime_task_uuid IS NULL OR receipt_kind <> 'rejected'),
  FOREIGN KEY(workflow_id) REFERENCES workflows(id)
)"""

#: The verbatim external facts a success or approval claim rests on (U-W2.2
#: §5.6). The EVENT is the authoritative fact that it happened; this table
#: holds the body the event records only by digest. Identity is
#: `(workflow_id, fact_kind, document_sha256)` with the digest RECOMPUTED from
#: the stored bytes, so an exact duplicate is a no-op insert while the command
#: that carried it still appends its event and consumes its revision.
WORKFLOW_FACTS_DDL = """CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  workflow_id INTEGER NOT NULL,
  fact_kind TEXT NOT NULL CHECK (fact_kind IN ('approval','result')),
  fact_scope TEXT
    CHECK (fact_scope IS NULL OR fact_scope IN ('admission','runtime')),
  document TEXT NOT NULL,
  document_sha256 TEXT NOT NULL,
  recorded_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  UNIQUE(workflow_id, fact_kind, document_sha256),
  CHECK ((fact_kind = 'approval') = (fact_scope IS NOT NULL)),
  FOREIGN KEY(workflow_id) REFERENCES workflows(id)
)"""

#: The U-W3 workflow-attempt ledger (§11.2). ONE row per CONSUMED workflow
#: attempt: the row is inserted when an `accepted` receipt opens the attempt,
#: never at reservation, so a queue rejection or an operator revocation burns
#: no budget slot. Exactly two writes reach a row — the opening INSERT and one
#: compare-and-swap that closes it.
#:
#: `attempt_no BETWEEN 1 AND 10` is the protocol's own frozen ceiling closed
#: storage-side (`beast.result-envelope/v1`'s `attempt`, `beast.work-spec/v1`'s
#: `retry.max_attempts`); the artifact's own budget is the tighter live bound
#: and belongs to the reducer. `UNIQUE(workflow_id, runtime_task_uuid)` makes
#: one runtime task serving two attempts of the same workflow UNSTORABLE — the
#: storage backstop for the §6.5 acceptance gate. The column is NOT NULL (a row
#: exists only because an `accepted` receipt supplied the binding), so SQLite's
#: NULL-distinct UNIQUE semantics can never arise.
#:
#: The biconditional pairs `open` with an absent `closed_seq`, so a closed
#: attempt with no closing event and an open attempt claiming one are both
#: unstorable. `content_sha256` carries no default, like every hashed record
#: in this schema.
WORKFLOW_ATTEMPTS_DDL = """CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  workflow_id INTEGER NOT NULL,
  attempt_no INTEGER NOT NULL CHECK (attempt_no BETWEEN 1 AND 10),
  state TEXT NOT NULL
    CHECK (state IN ('open','succeeded','failed','abandoned')),
  runtime_task_uuid TEXT NOT NULL,
  dispatch_intent_id TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  result_sha256 TEXT,
  opened_seq INTEGER NOT NULL CHECK (opened_seq >= 1),
  closed_seq INTEGER CHECK (closed_seq IS NULL OR closed_seq >= opened_seq),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  UNIQUE(workflow_id, attempt_no),
  UNIQUE(workflow_id, runtime_task_uuid),
  UNIQUE(workflow_id, dispatch_intent_id),
  CHECK ((state = 'open') = (closed_seq IS NULL)),
  CHECK (result_sha256 IS NULL OR state IN ('succeeded','failed')),
  FOREIGN KEY(workflow_id) REFERENCES workflows(id),
  FOREIGN KEY(dispatch_intent_id) REFERENCES workflow_intents(intent_id)
)"""

#: The U-W3 checkpoint store (§11.2). INSERT-ONCE in full: no code path in
#: this slice or any other issues UPDATE or DELETE against this table after
#: the creating transaction's own row-hash finalization (the `workflow_events`
#: / `agent_handoff_transitions` discipline).
#:
#: The composite foreign key pins every checkpoint to a REAL, CONSUMED
#: attempt, so a checkpoint for an attempt that never opened is
#: unrepresentable; the parent columns carry `workflow_attempts`'
#: `UNIQUE(workflow_id, attempt_no)` index, which is what makes the composite
#: reference legal. `payload_bytes` is the RECOMPUTED canonical length, stored
#: so `verify` can re-check the bound without re-serializing and CHECKed
#: against the frozen limit — `2` is the canonical length of the empty
#: object, the smallest legal payload.
WORKFLOW_CHECKPOINTS_DDL = """CREATE TABLE {table}(
  id INTEGER PRIMARY KEY,
  workflow_id INTEGER NOT NULL,
  attempt_no INTEGER NOT NULL CHECK (attempt_no BETWEEN 1 AND 10),
  checkpoint_id TEXT NOT NULL,
  checkpoint_seq INTEGER NOT NULL CHECK (checkpoint_seq BETWEEN 1 AND 8),
  runtime_task_uuid TEXT NOT NULL,
  document TEXT NOT NULL,
  document_sha256 TEXT NOT NULL,
  payload_bytes INTEGER NOT NULL
    CHECK (payload_bytes BETWEEN 2 AND 65536),
  recorded_at TEXT NOT NULL,
  content_sha256 TEXT NOT NULL,
  UNIQUE(workflow_id, checkpoint_id),
  UNIQUE(workflow_id, attempt_no, checkpoint_seq),
  FOREIGN KEY(workflow_id) REFERENCES workflows(id),
  FOREIGN KEY(workflow_id, attempt_no)
    REFERENCES workflow_attempts(workflow_id, attempt_no)
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
WORKFLOWS_TABLE = "workflows"
WORKFLOW_EVENTS_TABLE = "workflow_events"
WORKFLOW_COMMANDS_TABLE = "workflow_commands"
WORKFLOW_INTENTS_TABLE = "workflow_intents"
WORKFLOW_RECEIPTS_TABLE = "workflow_receipts"
WORKFLOW_FACTS_TABLE = "workflow_facts"
WORKFLOW_ATTEMPTS_TABLE = "workflow_attempts"
WORKFLOW_CHECKPOINTS_TABLE = "workflow_checkpoints"

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

#: The eight workflow tables — U-W2.2's six plus U-W3's two — paired with
#: their DDL, in FK-parent-first order: workflows → events → commands →
#: intents → receipts → facts → attempts → checkpoints. This is the ONLY
#: enumeration — `SCHEMA_SQL` composition, the 5→6 migration step (through its
#: FROZEN v6 copy, `migrations._V6_WORKFLOW_TABLES`), the 6→7 step, and the
#: three historical fixtures all iterate it, so a ninth table cannot be added
#: in one place and forgotten in the others (the MEMORY_GRAPH_TABLES /
#: ROUTING_HANDOFF_TABLES rule, applied a third time; D-v0.4.84).
#:
#: `workflow_attempts` follows `workflow_intents` because it holds a foreign
#: key into it, and `workflow_checkpoints` follows `workflow_attempts` for the
#: same reason — the reversed order the fixtures drop by is therefore
#: children-first with no edit (U-W3 §11.7).
WORKFLOW_TABLES: tuple[tuple[str, str], ...] = (
    (WORKFLOWS_TABLE, WORKFLOWS_DDL),
    (WORKFLOW_EVENTS_TABLE, WORKFLOW_EVENTS_DDL),
    (WORKFLOW_COMMANDS_TABLE, WORKFLOW_COMMANDS_DDL),
    (WORKFLOW_INTENTS_TABLE, WORKFLOW_INTENTS_DDL),
    (WORKFLOW_RECEIPTS_TABLE, WORKFLOW_RECEIPTS_DDL),
    (WORKFLOW_FACTS_TABLE, WORKFLOW_FACTS_DDL),
    (WORKFLOW_ATTEMPTS_TABLE, WORKFLOW_ATTEMPTS_DDL),
    (WORKFLOW_CHECKPOINTS_TABLE, WORKFLOW_CHECKPOINTS_DDL),
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

#: The canonical v6 schema. Composed rather than typed as one literal so the
#: memory tables have exactly ONE definition in the codebase, shared with the
#: 1→2 (M2.3) and 2→3 (M3.11) migrations; the agent tables have exactly one,
#: shared with the 3→4 migration (U-A1); and the four routing/handoff tables
#: have exactly one, shared with the 4→5 migration (U-A3, D-v0.4.22); and the
#: eight workflow tables have exactly one, shared with the 6→7 migration and
#: the three historical fixtures (U-W2.2 D-v0.4.84; U-W3 §11.5 — the 5→6 step
#: builds from `migrations._V6_WORKFLOW_TABLES`, the frozen copy of these
#: constants as they stood at `fef0c2b`).
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
    + "\n"
    + ";\n\n".join(
        ddl.format(table=table) for table, ddl in WORKFLOW_TABLES
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
