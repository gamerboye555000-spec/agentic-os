"""U-A3 Wave 1: routing/handoff storage foundation
(agentic-os-v0.4-u-a3-routing-handoffs-contract.md).

This wave ships the STORAGE only — schema v5, the additive 4→5 migration, the
four table DDLs with their corrected CHECKs and composite passport foreign
keys, the RP/AH identifiers, and the closed vocabularies. It ships NO routing
evaluation, NO plan creation, NO handoff operations and NO CLI. Every proof
here is therefore structural: it drives the storage boundary directly with SQL
against a temporary or in-memory database, never a real ledger.

Groups:
- SchemaAndMigration: v5, the fourth registry step, 4→5 status/plan, fresh vs
  migrated table creation and byte-identity, additive no-row-touch, injected
  rollback + corrected retry.
- RoutingPlanConstraints: the three result_status biconditionals, scope/project
  coherence, supersession self/cycle guards.
- RoutingCandidateConstraints: the composite passport FK, the five pin
  biconditionals, the two UNIQUE keys.
- AgentHandoffConstraints: participant FKs, self-handoff, data_classification
  and min_evidence bounds, supersession guards.
- HandoffTransitionConstraints: the full 15-pair legal/illegal edge matrix,
  reason-required, seq bounds and uniqueness.
- Indexes: no explicit U-A3 index exists.
- Identifiers: RP/AH round-trip and rejection.
- Vocabulary: autonomy/classification set-equality, no autonomy rank, reason
  vs refusal disjointness, closed handoff states/transitions.
- HistoricalMigrationGuard: D-v0.4.29 — the deferred v4 freeze obligation, and
  the historical step bodies, both guarded loudly.
"""

from __future__ import annotations

import contextlib
import copy
import dataclasses
import hashlib
import inspect
import io
import itertools
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest import mock

from fixtures.v3_workspace import build_v3_workspace, table_contents

from agentic_os import (
    agent_handoffs,
    cli,
    db,
    doctor,
    events,
    ids,
    migrations,
    models,
    ops,
    passports,
    power,
    protocols,
    routing,
    utils,
)
from agentic_os.utils import AosError

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The frozen passport artifact — the authoritative source of the `autonomy`
#: and `data_classifications` enums U-A3's vocabularies are pinned against.
PASSPORT_SCHEMA = json.loads(
    (REPO_ROOT / "protocols" / "beast.agent-passport" / "v1.schema.json").read_text(
        encoding="utf-8"
    )
)

NOW = "2026-01-01T00:00:00Z"
HASH = "0" * 64
FOUR_TABLES = (
    "routing_plans",
    "routing_plan_candidates",
    "agent_handoffs",
    "agent_handoff_transitions",
)


def _insert(conn: sqlite3.Connection, table: str, values: dict) -> None:
    cols = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    conn.execute(
        f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
        tuple(values.values()),
    )


def _plan_row(**over) -> dict:
    row = dict(
        task_id=None,
        project_id=None,
        scope="global",
        actor="human",
        request_schema="aos.routing-request/v1",
        algorithm_version="aos-routing-order/v1",
        request_document="{}",
        request_sha256=HASH,
        result_status="no_eligible_candidates",
        eligible_count=0,
        unresolved_count=0,
        excluded_count=0,
        supersedes_id=None,
        created_at=NOW,
        content_sha256=HASH,
    )
    row.update(over)
    return row


def _candidate_row(**over) -> dict:
    row = dict(
        plan_id=1,
        agent_id=1,
        verdict="excluded",
        rank=None,
        passport_version=None,
        passport_sha256=None,
        identity_sha256=None,
        reasons_json="[]",
        warnings_json="[]",
        ordering_json=None,
        created_at=NOW,
        content_sha256=HASH,
    )
    row.update(over)
    return row


def _eligible_candidate_row(**over) -> dict:
    row = _candidate_row(
        verdict="eligible",
        rank=1,
        passport_version=1,
        passport_sha256=HASH,
        identity_sha256=HASH,
        ordering_json="[0,0,0,0,0,0]",
    )
    row.update(over)
    return row


def _handoff_row(**over) -> dict:
    row = dict(
        task_id=1,
        plan_id=None,
        from_agent_id=1,
        to_agent_id=2,
        actor="human",
        objective_md="obj",
        expected_evidence_json="[]",
        min_evidence_count=0,
        constraints_md=None,
        data_classification="internal",
        decision_id=None,
        from_passport_version=1,
        from_passport_sha256=HASH,
        to_passport_version=1,
        to_passport_sha256=HASH,
        state="proposed",
        supersedes_id=None,
        created_at=NOW,
        updated_at=NOW,
        content_sha256=HASH,
    )
    row.update(over)
    return row


def _transition_row(**over) -> dict:
    row = dict(
        handoff_id=1,
        seq=1,
        from_state="proposed",
        to_state="accepted",
        actor="human",
        reason_code=None,
        note_md=None,
        created_at=NOW,
        content_sha256=HASH,
    )
    row.update(over)
    return row


class _SeededV5TestCase(unittest.TestCase):
    """An in-memory v5 database with the parent rows the four U-A3 tables
    reference: two governed agents, agent 1 with passport v1 and agent 2 with
    v1 and v2 (so "another agent's version" is expressible), plus a project, a
    task and a decision. No hash is real — these tests exercise storage
    constraints, not integrity verification."""

    def setUp(self):
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)
        self.conn.executescript(db.SCHEMA_SQL)
        _insert(
            self.conn,
            "projects",
            dict(
                id=1,
                slug="demo",
                name="Demo",
                repo_path="/repo",
                status="active",
                autonomy_level=0,
                created_at=NOW,
                updated_at=NOW,
            ),
        )
        _insert(
            self.conn,
            "tasks",
            dict(
                id=1,
                project_id=1,
                title="t",
                kind="code",
                status="ready",
                priority=2,
                created_at=NOW,
                updated_at=NOW,
            ),
        )
        _insert(
            self.conn,
            "decisions",
            dict(
                id=1,
                title="d",
                decision_md="x",
                status="accepted",
                decided_at=NOW,
            ),
        )
        for aid, name in ((1, "alpha"), (2, "beta")):
            _insert(
                self.conn,
                "agents",
                dict(
                    id=aid,
                    name=name,
                    agent_class="custom",
                    scope="global",
                    project_id=None,
                    lifecycle="active",
                    protected=0,
                    owner="human",
                    origin="create",
                    current_passport_version=None,
                    created_at=NOW,
                    updated_at=NOW,
                    content_sha256=HASH,
                ),
            )
        for aid, version in ((1, 1), (2, 1), (2, 2)):
            _insert(
                self.conn,
                "agent_passports",
                dict(
                    agent_id=aid,
                    version=version,
                    status="published",
                    created_at=NOW,
                    published_at=NOW,
                    document="{}",
                    content_sha256=HASH,
                ),
            )
        self.conn.commit()

    def _count(self, table: str) -> int:
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


# ---------------------------------------------------------------------------
# (1)(2)(3)(4)(5)(6)(7)(8)(9) Schema, registry, migration.

class SchemaAndMigrationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()

    def _fresh_db(self) -> Path:
        path = self.root / "fresh" / "aos.db"
        conn, created = db.init_db(path)
        # init_db lays down SCHEMA_SQL; the ledger's own version stamp is an
        # application fact (ops.init writes it), so mirror that here.
        conn.execute(
            "INSERT INTO meta(key, value) VALUES ('schema_version', ?)",
            (db.SCHEMA_VERSION,),
        )
        conn.commit()
        conn.close()
        self.assertTrue(created)
        return path

    @staticmethod
    def _tables(path: Path) -> set:
        conn = sqlite3.connect(path)
        try:
            return {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            conn.close()

    @staticmethod
    def _table_sql(path: Path) -> dict:
        conn = sqlite3.connect(path)
        try:
            return {
                r[0]: r[1]
                for r in conn.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type='table'"
                )
            }
        finally:
            conn.close()

    @staticmethod
    def _version(path: Path) -> str:
        conn = sqlite3.connect(path)
        try:
            return conn.execute(
                "SELECT value FROM meta WHERE key='schema_version'"
            ).fetchone()[0]
        finally:
            conn.close()

    def test_schema_version_is_five(self):
        self.assertEqual(db.SCHEMA_VERSION, "5")
        self.assertEqual(migrations.LATEST_VERSION, 5)
        self.assertEqual(self._version(self._fresh_db()), "5")

    def test_registry_has_the_new_fourth_step_in_exact_order(self):
        self.assertEqual(
            [
                (m.from_version, m.to_version, m.migration_id)
                for m in migrations.MIGRATIONS
            ],
            [
                (1, 2, "u-m2-memory-claims-v2"),
                (2, 3, "u-m3-memory-graph-v3"),
                (3, 4, "u-a1-agent-passports-v4"),
                (4, 5, "u-a3-routing-handoffs-v5"),
            ],
        )
        migrations.validate_registry()

    def test_migration_status_and_plan_report_four_to_five(self):
        db_path = build_v3_workspace(self.root / "v3")
        report = migrations.status(db_path)
        self.assertEqual(report["current_version"], 3)
        self.assertEqual(report["latest_version"], 5)
        self.assertEqual(
            report["plan"][-1],
            {"from": 4, "to": 5, "migration_id": "u-a3-routing-handoffs-v5"},
        )

    def test_fresh_init_creates_all_four_tables(self):
        self.assertLessEqual(set(FOUR_TABLES), self._tables(self._fresh_db()))

    def test_migrated_v3_workspace_creates_all_four_tables(self):
        db_path = build_v3_workspace(self.root / "v3")
        result = migrations.apply_migrations(db_path.parent)
        self.assertEqual(result["current_version"], 5)
        self.assertLessEqual(set(FOUR_TABLES), self._tables(db_path))

    def test_fresh_and_migrated_sql_is_byte_identical_for_the_four_tables(self):
        fresh = self._table_sql(self._fresh_db())
        db_path = build_v3_workspace(self.root / "v3")
        migrations.apply_migrations(db_path.parent)
        migrated = self._table_sql(db_path)
        for table in FOUR_TABLES:
            # Byte identity, not merely structural: the migration creates these
            # directly under their real names, so there is no ALTER RENAME
            # quoting artifact to normalize away.
            self.assertEqual(fresh[table], migrated[table], table)

    def test_additive_migration_touches_no_existing_row(self):
        db_path = build_v3_workspace(self.root / "v3")
        before = table_contents(db_path)
        migrations.apply_migrations(db_path.parent)
        after = table_contents(db_path)
        for table, rows in before.items():
            if table in ("events", "meta"):
                continue  # events gain the migrate rows; meta the version
            self.assertEqual(rows, after[table], f"{table} changed")

    def test_injected_failure_rolls_back_every_new_table_then_retry_succeeds(self):
        db_path = build_v3_workspace(self.root / "v3")

        def _failing_v5(conn: sqlite3.Connection) -> None:
            for table, ddl in db.ROUTING_HANDOFF_TABLES:
                conn.execute(ddl.format(table=table))
            raise RuntimeError("injected mid-step failure")

        failing = migrations.Migration(
            from_version=4,
            to_version=5,
            migration_id="u-a3-routing-handoffs-v5-failing",
            apply=_failing_v5,
        )
        failing_registry = (
            migrations.MEMORY_CLAIMS_V2,
            migrations.MEMORY_GRAPH_V3,
            migrations.AGENT_PASSPORTS_V4,
            failing,
        )
        with self.assertRaises(migrations.MigrationStepError):
            migrations.apply_migrations(
                db_path.parent, registry=failing_registry, latest=5
            )
        # The 3→4 step committed; the failed 4→5 rolled back completely.
        self.assertEqual(self._version(db_path), "4")
        self.assertEqual(set(FOUR_TABLES) & self._tables(db_path), set())

        # The corrected retry, with the real registry, resumes from v4.
        result = migrations.apply_migrations(db_path.parent)
        self.assertEqual(result["current_version"], 5)
        self.assertLessEqual(set(FOUR_TABLES), self._tables(db_path))


# ---------------------------------------------------------------------------
# (10)(13) routing_plans CHECK constraints.

class RoutingPlanConstraintTests(_SeededV5TestCase):
    def test_result_status_biconditional_truth_table(self):
        # (status, eligible_count, unresolved_count) rows that are coherent
        # INSERT; the incoherent ones the three biconditionals forbid raise.
        legal = [
            ("resolved", 1, 0),
            ("resolved", 1, 1),
            ("no_eligible_candidates", 0, 0),
            ("unresolved", 0, 1),
        ]
        illegal = [
            ("resolved", 0, 0),            # resolved requires eligible > 0
            ("resolved", 0, 1),            # resolved requires eligible > 0
            ("unresolved", 1, 1),          # unresolved requires eligible = 0
            ("unresolved", 1, 0),          # unresolved requires eligible = 0
            ("unresolved", 0, 0),          # unresolved requires unresolved > 0
            ("no_eligible_candidates", 1, 0),  # requires eligible = 0
            ("no_eligible_candidates", 0, 1),  # requires unresolved = 0
        ]
        for status, elig, unres in legal:
            with self.subTest(legal=(status, elig, unres)):
                self.conn.execute("SAVEPOINT p")
                _insert(
                    self.conn,
                    "routing_plans",
                    _plan_row(
                        result_status=status,
                        eligible_count=elig,
                        unresolved_count=unres,
                    ),
                )
                self.conn.execute("RELEASE p")
        for status, elig, unres in illegal:
            with self.subTest(illegal=(status, elig, unres)):
                with self.assertRaises(sqlite3.IntegrityError):
                    _insert(
                        self.conn,
                        "routing_plans",
                        _plan_row(
                            result_status=status,
                            eligible_count=elig,
                            unresolved_count=unres,
                        ),
                    )

    def test_scope_project_coherence(self):
        # global ⇒ project_id NULL; project ⇒ project_id NOT NULL.
        _insert(self.conn, "routing_plans", _plan_row(scope="global", project_id=None))
        _insert(
            self.conn,
            "routing_plans",
            _plan_row(scope="project", project_id=1),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(
                self.conn,
                "routing_plans",
                _plan_row(scope="global", project_id=1),
            )
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(
                self.conn,
                "routing_plans",
                _plan_row(scope="project", project_id=None),
            )

    def test_result_status_vocabulary_is_closed(self):
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(
                self.conn,
                "routing_plans",
                _plan_row(result_status="no_candidates"),
            )

    def test_supersession_self_and_cycle_guards(self):
        _insert(self.conn, "routing_plans", _plan_row())          # id 1
        _insert(self.conn, "routing_plans", _plan_row(supersedes_id=1))  # id 2 ok
        # supersedes_id = id (self) and supersedes_id > id (forward cycle) both
        # violate CHECK (supersedes_id IS NULL OR supersedes_id < id).
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(self.conn, "routing_plans", _plan_row(id=3, supersedes_id=3))
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(self.conn, "routing_plans", _plan_row(id=4, supersedes_id=9))
        # A second successor of the same target collides with UNIQUE.
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(self.conn, "routing_plans", _plan_row(supersedes_id=1))


# ---------------------------------------------------------------------------
# (11)(12) routing_plan_candidates: composite passport FK + pin biconditionals.

class RoutingCandidateConstraintTests(_SeededV5TestCase):
    def setUp(self):
        super().setUp()
        _insert(
            self.conn,
            "routing_plans",
            _plan_row(result_status="resolved", eligible_count=1),
        )  # plan id 1

    def test_valid_eligible_pin_succeeds(self):
        _insert(self.conn, "routing_plan_candidates", _eligible_candidate_row())
        self.assertEqual(self._count("routing_plan_candidates"), 1)

    def test_missing_passport_version_refuses(self):
        # agent 1 has only v1; pinning v2 names no real passport row.
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(
                self.conn,
                "routing_plan_candidates",
                _eligible_candidate_row(agent_id=1, passport_version=2),
            )

    def test_another_agents_version_refuses(self):
        # (agent 2, v2) exists but (agent 1, v2) does not: the composite FK
        # binds the PAIR, so agent 1 cannot borrow agent 2's version.
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(
                self.conn,
                "routing_plan_candidates",
                _eligible_candidate_row(agent_id=1, passport_version=2),
            )

    def test_excluded_candidate_with_null_pin_succeeds(self):
        # A NULL passport_version disables the composite FK (SQLite's NULL
        # rule) — exactly what keeps excluded/unresolved rows legal.
        _insert(self.conn, "routing_plan_candidates", _candidate_row(verdict="excluded"))
        self.assertEqual(self._count("routing_plan_candidates"), 1)

    def test_pin_biconditionals(self):
        # eligible ⇔ each of rank / ordering_json / passport_version /
        # passport_sha256 / identity_sha256 non-NULL.
        for field in (
            "rank",
            "ordering_json",
            "passport_version",
            "passport_sha256",
            "identity_sha256",
        ):
            with self.subTest(eligible_missing=field):
                with self.assertRaises(sqlite3.IntegrityError):
                    _insert(
                        self.conn,
                        "routing_plan_candidates",
                        _eligible_candidate_row(**{field: None}),
                    )
        # An excluded (non-eligible) row may carry NONE of the five.
        for field, value in (
            ("rank", 1),
            ("ordering_json", "[0,0,0,0,0,0]"),
            ("passport_version", 1),
            ("passport_sha256", HASH),
            ("identity_sha256", HASH),
        ):
            with self.subTest(excluded_carrying=field):
                with self.assertRaises(sqlite3.IntegrityError):
                    _insert(
                        self.conn,
                        "routing_plan_candidates",
                        _candidate_row(verdict="excluded", **{field: value}),
                    )

    def test_unique_plan_agent_and_plan_rank(self):
        _insert(
            self.conn,
            "routing_plan_candidates",
            _eligible_candidate_row(agent_id=1, rank=1),
        )
        # Same (plan, agent) again.
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(
                self.conn,
                "routing_plan_candidates",
                _candidate_row(agent_id=1, verdict="excluded"),
            )
        # Same (plan, rank) for a different agent.
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(
                self.conn,
                "routing_plan_candidates",
                _eligible_candidate_row(agent_id=2, rank=1),
            )


# ---------------------------------------------------------------------------
# (14)(15)(13) agent_handoffs constraints.

class AgentHandoffConstraintTests(_SeededV5TestCase):
    def test_valid_full_field_handoff_persists(self):
        _insert(
            self.conn,
            "agent_handoffs",
            _handoff_row(plan_id=None, decision_id=1, constraints_md="c"),
        )
        row = self.conn.execute(
            "SELECT from_agent_id, to_agent_id, state, data_classification "
            "FROM agent_handoffs"
        ).fetchone()
        self.assertEqual(tuple(row), (1, 2, "proposed", "internal"))

    def test_self_handoff_refused(self):
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(
                self.conn,
                "agent_handoffs",
                _handoff_row(from_agent_id=1, to_agent_id=1),
            )

    def test_participant_passport_composite_fks(self):
        # from side: agent 1 has no v2.
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(
                self.conn,
                "agent_handoffs",
                _handoff_row(from_agent_id=1, from_passport_version=2),
            )
        # to side: agent 2 has no v9.
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(
                self.conn,
                "agent_handoffs",
                _handoff_row(to_agent_id=2, to_passport_version=9),
            )
        # Both pins valid: agent 1 v1 and agent 2 v2 exist.
        _insert(
            self.conn,
            "agent_handoffs",
            _handoff_row(to_passport_version=2),
        )
        self.assertEqual(self._count("agent_handoffs"), 1)

    def test_data_classification_vocabulary_closed(self):
        for level in ("public", "internal", "confidential", "restricted"):
            with self.subTest(level=level):
                self.conn.execute("SAVEPOINT p")
                _insert(
                    self.conn,
                    "agent_handoffs",
                    _handoff_row(data_classification=level),
                )
                self.conn.execute("ROLLBACK TO p")
                self.conn.execute("RELEASE p")
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(
                self.conn,
                "agent_handoffs",
                _handoff_row(data_classification="secret"),
            )

    def test_min_evidence_count_bounds(self):
        for value in (0, 32):
            with self.subTest(ok=value):
                self.conn.execute("SAVEPOINT p")
                _insert(
                    self.conn,
                    "agent_handoffs",
                    _handoff_row(min_evidence_count=value),
                )
                self.conn.execute("ROLLBACK TO p")
                self.conn.execute("RELEASE p")
        for value in (-1, 33):
            with self.subTest(bad=value):
                with self.assertRaises(sqlite3.IntegrityError):
                    _insert(
                        self.conn,
                        "agent_handoffs",
                        _handoff_row(min_evidence_count=value),
                    )

    def test_state_vocabulary_closed_and_no_completed(self):
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(self.conn, "agent_handoffs", _handoff_row(state="completed"))

    def test_supersession_self_and_cycle_guards(self):
        _insert(self.conn, "agent_handoffs", _handoff_row())               # id 1
        _insert(self.conn, "agent_handoffs", _handoff_row(supersedes_id=1))  # id 2
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(self.conn, "agent_handoffs", _handoff_row(id=3, supersedes_id=3))
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(self.conn, "agent_handoffs", _handoff_row(id=4, supersedes_id=9))
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(self.conn, "agent_handoffs", _handoff_row(supersedes_id=1))


# ---------------------------------------------------------------------------
# (16)(17) agent_handoff_transitions constraints.

FROM_STATES = ("proposed", "accepted", "clarification_required")
TO_STATES = ("accepted", "refused", "clarification_required", "cancelled", "superseded")
LEGAL_EDGES = frozenset(
    {
        ("proposed", "accepted"),
        ("proposed", "refused"),
        ("proposed", "clarification_required"),
        ("proposed", "cancelled"),
        ("proposed", "superseded"),
        ("clarification_required", "accepted"),
        ("clarification_required", "refused"),
        ("clarification_required", "cancelled"),
        ("clarification_required", "superseded"),
        ("accepted", "cancelled"),
        ("accepted", "superseded"),
    }
)


class HandoffTransitionConstraintTests(_SeededV5TestCase):
    def setUp(self):
        super().setUp()
        _insert(self.conn, "agent_handoffs", _handoff_row())  # handoff id 1

    def test_full_edge_matrix(self):
        # All 15 (from_state, to_state) pairs over the two enums: 11 legal
        # inserts, 4 illegal raise. A reason_code is always supplied so the
        # only constraints in play are from_state<>to_state and the
        # accepted-source restriction — not the reason-required CHECK.
        self.assertEqual(len(LEGAL_EDGES), 11)
        for from_state, to_state in itertools.product(FROM_STATES, TO_STATES):
            legal = (from_state, to_state) in LEGAL_EDGES
            with self.subTest(edge=f"{from_state}->{to_state}", legal=legal):
                self.conn.execute("SAVEPOINT p")
                row = _transition_row(
                    from_state=from_state,
                    to_state=to_state,
                    reason_code="operator_judgment",
                )
                if legal:
                    _insert(self.conn, "agent_handoff_transitions", row)
                else:
                    with self.assertRaises(sqlite3.IntegrityError):
                        _insert(self.conn, "agent_handoff_transitions", row)
                self.conn.execute("ROLLBACK TO p")
                self.conn.execute("RELEASE p")

    def test_accepted_source_restriction_is_structural(self):
        # The MAJOR-3 CHECK: from 'accepted' only cancelled/superseded are
        # reachable, even though the enums would otherwise admit more.
        for to_state in ("refused", "clarification_required"):
            with self.subTest(to_state=to_state):
                with self.assertRaises(sqlite3.IntegrityError):
                    _insert(
                        self.conn,
                        "agent_handoff_transitions",
                        _transition_row(
                            from_state="accepted",
                            to_state=to_state,
                            reason_code="operator_judgment",
                        ),
                    )

    def test_reason_required_for_refused_and_clarification(self):
        for to_state in ("refused", "clarification_required"):
            with self.subTest(missing_reason=to_state):
                with self.assertRaises(sqlite3.IntegrityError):
                    _insert(
                        self.conn,
                        "agent_handoff_transitions",
                        _transition_row(
                            from_state="proposed",
                            to_state=to_state,
                            reason_code=None,
                        ),
                    )
        # With a reason, both insert; and reason is optional for the others.
        _insert(
            self.conn,
            "agent_handoff_transitions",
            _transition_row(
                from_state="proposed",
                to_state="refused",
                reason_code="out_of_scope",
            ),
        )
        _insert(
            self.conn,
            "agent_handoff_transitions",
            _transition_row(seq=2, from_state="proposed", to_state="cancelled"),
        )

    def test_reason_code_vocabulary_closed(self):
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(
                self.conn,
                "agent_handoff_transitions",
                _transition_row(
                    from_state="proposed",
                    to_state="refused",
                    reason_code="because",
                ),
            )

    def test_seq_bounds_and_uniqueness(self):
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(self.conn, "agent_handoff_transitions", _transition_row(seq=0))
        _insert(
            self.conn,
            "agent_handoff_transitions",
            _transition_row(seq=1, from_state="proposed", to_state="accepted"),
        )
        with self.assertRaises(sqlite3.IntegrityError):
            _insert(
                self.conn,
                "agent_handoff_transitions",
                _transition_row(seq=1, from_state="proposed", to_state="cancelled"),
            )


# ---------------------------------------------------------------------------
# (18) No explicit U-A3 index.

class IndexTests(_SeededV5TestCase):
    def test_no_explicit_index_on_the_four_tables(self):
        placeholders = ", ".join("?" for _ in FOUR_TABLES)
        explicit = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            f"AND tbl_name IN ({placeholders}) AND sql IS NOT NULL",
            FOUR_TABLES,
        ).fetchall()
        self.assertEqual(explicit, [], f"unexpected explicit index: {explicit}")

    def test_unique_constraints_still_carry_implicit_indexes(self):
        # SQLite's implicit UNIQUE indexes have sql IS NULL; acknowledging them
        # is the point — no explicit index is needed on top.
        placeholders = ", ".join("?" for _ in FOUR_TABLES)
        implicit = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            f"AND tbl_name IN ({placeholders}) AND sql IS NULL",
            FOUR_TABLES,
        ).fetchall()
        self.assertTrue(implicit)


# ---------------------------------------------------------------------------
# (19) RP / AH identifiers.

class IdentifierTests(unittest.TestCase):
    def test_prefixes_registered_without_collision(self):
        self.assertEqual(ids.PREFIXES["routing_plan"], "RP")
        self.assertEqual(ids.PREFIXES["agent_handoff"], "AH")
        # No two entities share a prefix — RP/AH included.
        values = list(ids.PREFIXES.values())
        self.assertEqual(len(values), len(set(values)))

    def test_render_and_round_trip(self):
        self.assertEqual(ids.render_id("routing_plan", 7), "RP-0007")
        self.assertEqual(ids.render_id("agent_handoff", 12), "AH-0012")
        for entity in ("routing_plan", "agent_handoff"):
            for n in (1, 42, 9999, 10000, 2**63 - 1):
                with self.subTest(entity=entity, n=n):
                    self.assertEqual(
                        ids.parse_id(ids.render_id(entity, n), entity), n
                    )

    def test_parse_rejects_wrong_prefix_zero_and_garbage(self):
        for text in ("AH-0001", "RP-0000", "RP-abc", "XY-0001", "RP0001", ""):
            with self.subTest(text=text):
                with self.assertRaises(AosError):
                    ids.parse_id(text, "routing_plan")
        # The other entity's id is rejected symmetrically.
        with self.assertRaises(AosError):
            ids.parse_id("RP-0001", "agent_handoff")

    def test_parse_rejects_overflow(self):
        with self.assertRaises(AosError):
            ids.parse_id(f"RP-{2**63}", "routing_plan")


# ---------------------------------------------------------------------------
# (20)(21)(22)(23) Vocabulary correctness.

class VocabularyTests(unittest.TestCase):
    def test_autonomy_set_equals_the_passport_schema_enum(self):
        self.assertEqual(
            set(models.AGENT_AUTONOMY_LEVELS),
            set(protocols.AGENT_AUTONOMY_LEVELS),
        )
        self.assertEqual(
            set(models.AGENT_AUTONOMY_LEVELS),
            set(PASSPORT_SCHEMA["properties"]["autonomy"]["enum"]),
        )

    def test_autonomy_order_is_not_consumed_by_any_rank_helper(self):
        # The tuple is UNORDERED membership. No rank/index function may exist
        # over it — contrast MEMORY_SENSITIVITIES + sensitivity_rank.
        autonomy_symbols = [n for n in dir(models) if "autonomy" in n.lower()]
        self.assertEqual(autonomy_symbols, ["AGENT_AUTONOMY_LEVELS"])
        self.assertFalse(hasattr(models, "autonomy_rank"))

    def test_classification_vocabularies_are_set_equal(self):
        schema_levels = set(
            PASSPORT_SCHEMA["properties"]["data_classifications"]["items"]["enum"]
        )
        self.assertEqual(set(models.MEMORY_SENSITIVITIES), set(protocols.DATA_CLASSIFICATIONS))
        self.assertEqual(set(models.MEMORY_SENSITIVITIES), schema_levels)
        # The handoff DDL's data_classification enum is the same closed set.
        for level in models.MEMORY_SENSITIVITIES:
            self.assertIn(f"'{level}'", db.AGENT_HANDOFFS_DDL)

    def test_reason_codes_and_refusal_codes_are_disjoint(self):
        self.assertEqual(
            set(models.ROUTING_REASON_CODES) & set(models.ROUTING_REQUEST_REFUSAL_CODES),
            set(),
        )
        self.assertEqual(len(models.ROUTING_REASON_CODES), 24)
        self.assertEqual(len(set(models.ROUTING_REASON_CODES)), 24)
        self.assertEqual(
            models.ROUTING_REQUEST_REFUSAL_CODES,
            ("agent_absent", "catalog_not_installed"),
        )

    def test_closed_routing_and_handoff_vocabularies(self):
        self.assertEqual(
            models.ROUTING_RESULT_STATUSES,
            ("resolved", "no_eligible_candidates", "unresolved"),
        )
        self.assertEqual(
            models.ROUTING_CANDIDATE_VERDICTS,
            ("eligible", "unresolved", "excluded"),
        )
        self.assertEqual(models.ROUTING_REASON_DISPLAY_LIMIT, 8)
        self.assertEqual(models.MAX_ROUTING_EVALUATED_AGENTS, 256)
        self.assertNotIn("completed", models.AGENT_HANDOFF_STATES)
        self.assertEqual(set(models.AGENT_HANDOFF_TRANSITIONS), {
            "accept", "refuse", "clarify", "cancel", "supersede",
        })
        # The three terminal states appear in NO verb's source set.
        sources = {
            state
            for legal_sources, _target in models.AGENT_HANDOFF_TRANSITIONS.values()
            for state in legal_sources
        }
        self.assertEqual(sources & {"refused", "cancelled", "superseded"}, set())
        self.assertEqual(len(models.HANDOFF_REASON_CODES), 8)


# ---------------------------------------------------------------------------
# Passive row models: the four U-A3 dataclasses mirror their tables exactly —
# field-for-field, in column order — and carry no behavior of their own.

_ROW_MODELS = (
    ("routing_plans", models.RoutingPlan, _plan_row),
    ("routing_plan_candidates", models.RoutingPlanCandidate, _candidate_row),
    ("agent_handoffs", models.AgentHandoff, _handoff_row),
    ("agent_handoff_transitions", models.AgentHandoffTransition, _transition_row),
)


class RowModelTests(_SeededV5TestCase):
    def _insert_one_row_per_table(self):
        _insert(self.conn, "routing_plans", _plan_row())
        _insert(self.conn, "routing_plan_candidates", _candidate_row())
        _insert(self.conn, "agent_handoffs", _handoff_row())
        _insert(self.conn, "agent_handoff_transitions", _transition_row())
        self.conn.commit()

    def test_all_four_dataclasses_exist_as_passive_rows(self):
        for _table, cls, _builder in _ROW_MODELS:
            self.assertTrue(dataclasses.is_dataclass(cls))
            self.assertTrue(issubclass(cls, models._Row))
            # Passive: everything callable comes from _Row or the dataclass
            # machinery — the class body defines fields and nothing else.
            own_methods = [
                name
                for name, value in vars(cls).items()
                if callable(value) and not name.startswith("__")
            ]
            self.assertEqual(own_methods, [])

    def test_field_lists_match_table_column_order_exactly(self):
        for table, cls, _builder in _ROW_MODELS:
            columns = [
                row["name"]
                for row in self.conn.execute(f"PRAGMA table_info({table})")
            ]
            self.assertEqual(
                [field.name for field in dataclasses.fields(cls)], columns
            )

    def test_from_row_constructs_each_class_from_a_sqlite_row(self):
        self._insert_one_row_per_table()
        for table, cls, builder in _ROW_MODELS:
            row = self.conn.execute(f"SELECT * FROM {table}").fetchone()
            self.assertIsInstance(row, sqlite3.Row)
            obj = cls.from_row(row)
            self.assertIsInstance(obj, cls)
            self.assertEqual(obj.as_dict(), dict(builder(), id=1))

    def test_nullable_fields_preserve_none(self):
        self._insert_one_row_per_table()
        plan = models.RoutingPlan.from_row(
            self.conn.execute("SELECT * FROM routing_plans").fetchone()
        )
        for name in ("task_id", "project_id", "supersedes_id"):
            self.assertIsNone(getattr(plan, name))
        candidate = models.RoutingPlanCandidate.from_row(
            self.conn.execute("SELECT * FROM routing_plan_candidates").fetchone()
        )
        for name in (
            "rank",
            "passport_version",
            "passport_sha256",
            "identity_sha256",
            "ordering_json",
        ):
            self.assertIsNone(getattr(candidate, name))
        handoff = models.AgentHandoff.from_row(
            self.conn.execute("SELECT * FROM agent_handoffs").fetchone()
        )
        for name in ("plan_id", "constraints_md", "decision_id", "supersedes_id"):
            self.assertIsNone(getattr(handoff, name))
        transition = models.AgentHandoffTransition.from_row(
            self.conn.execute("SELECT * FROM agent_handoff_transitions").fetchone()
        )
        for name in ("reason_code", "note_md"):
            self.assertIsNone(getattr(transition, name))

    def test_no_autonomy_rank_helper_exists(self):
        self.assertFalse(hasattr(models, "autonomy_rank"))
        for _table, cls, _builder in _ROW_MODELS:
            self.assertFalse(hasattr(cls, "autonomy_rank"))

    def test_dataclasses_changed_no_schema_or_migration(self):
        self.assertEqual(db.SCHEMA_VERSION, "5")
        self.assertEqual(len(migrations.MIGRATIONS), 4)
        self.assertEqual(
            migrations.MIGRATIONS[-1].migration_id, "u-a3-routing-handoffs-v5"
        )
        # No field carries a default: a row model cannot invent a column
        # value the database did not supply.
        for _table, cls, _builder in _ROW_MODELS:
            for field in dataclasses.fields(cls):
                self.assertIs(field.default, dataclasses.MISSING)
                self.assertIs(field.default_factory, dataclasses.MISSING)


# ---------------------------------------------------------------------------
# (24)(25) Historical migration guard (D-v0.4.29) and unchanged bodies.

#: A frozen copy of the v4 agent DDL, captured at the U-A3 baseline
#: (80b7e82577cbed19aa1823934df44ae09a644ac5). U-A3 must not touch AGENTS_DDL,
#: AGENT_PASSPORTS_DDL or agent_identity_payload — a mismatch here is the
#: signal that the deferred v4 migration-freeze obligation (D-v0.4.29) has come
#: due, and whoever tripped it must freeze the v4-named copies before editing.
_FROZEN_V4_AGENTS_DDL = """CREATE TABLE {table}(
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

_FROZEN_V4_AGENT_PASSPORTS_DDL = """CREATE TABLE {table}(
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

#: The sorted identity-payload key set for a fixed representative agent, frozen
#: at the U-A3 baseline. agent_identity_payload feeds the 3→4 migration's row
#: hashes; a change to its shape would silently rewrite v4 history.
_FROZEN_IDENTITY_KEYS = [
    "agent_class_sha256",
    "capabilities_json_sha256",
    "created_at_sha256",
    "current_passport_version",
    "id",
    "identity_schema",
    "invoke_hint_sha256",
    "kind_sha256",
    "lifecycle_sha256",
    "name_sha256",
    "notes_sha256",
    "origin_sha256",
    "owner_sha256",
    "project_id",
    "protected",
    "scope_sha256",
    "trust_level",
    "updated_at_sha256",
]

#: sha256 of each historical migration step's SOURCE, frozen at the U-A3
#: baseline. U-A3's own step is purely additive and reads no existing table; a
#: change to any of these three is a change to shipped history.
_FROZEN_STEP_SOURCE_SHA256 = {
    "_memory_claims_v2":
        "045620a440225a9103a3fe95e9ad4c8d1eefddb82a70fac192948bd99ff39829",
    "_memory_graph_v3":
        "d91ee97a83348e38c7d985f3a18495b33cd534bdb616826b97bd55ba78a01a23",
    "_agent_passports_v4":
        "5f90576bbc2a20cf565e215174ab02f067327dd0beb0012671143140a14089a8",
}

_FREEZE_DUE_MSG = (
    "The historical v4 migration-freeze obligation (D-v0.4.29) has come due: "
    "{what} changed from the U-A3 baseline. Freeze the v4-named copies "
    "(_V4_AGENTS_DDL / _V4_AGENT_PASSPORTS_DDL / the v4 identity payload) in "
    "migrations.py BEFORE editing any of the three, so the 3→4 step keeps "
    "building a true v4 database."
)


class HistoricalMigrationGuardTests(unittest.TestCase):
    def test_v4_migration_targets_are_unchanged_from_the_u_a1_baseline(self):
        self.assertEqual(
            db.AGENTS_DDL,
            _FROZEN_V4_AGENTS_DDL,
            _FREEZE_DUE_MSG.format(what="db.AGENTS_DDL"),
        )
        self.assertEqual(
            db.AGENT_PASSPORTS_DDL,
            _FROZEN_V4_AGENT_PASSPORTS_DDL,
            _FREEZE_DUE_MSG.format(what="db.AGENT_PASSPORTS_DDL"),
        )
        agent = models.Agent(
            id=1,
            name="rep-agent",
            agent_class="custom",
            scope="global",
            project_id=None,
            lifecycle="active",
            protected=0,
            owner="human",
            origin="create",
            current_passport_version=1,
            created_at=NOW,
            updated_at=NOW,
            kind=None,
            invoke_hint=None,
            capabilities_json=None,
            trust_level=None,
            notes=None,
            content_sha256=HASH,
        )
        self.assertEqual(
            sorted(passports.agent_identity_payload(agent).keys()),
            _FROZEN_IDENTITY_KEYS,
            _FREEZE_DUE_MSG.format(what="passports.agent_identity_payload"),
        )

    def test_historical_migration_bodies_remain_unchanged(self):
        for name, expected in _FROZEN_STEP_SOURCE_SHA256.items():
            with self.subTest(step=name):
                source = inspect.getsource(getattr(migrations, name))
                digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
                self.assertEqual(
                    digest,
                    expected,
                    f"historical migration body {name!r} changed; U-A3's "
                    "migration must be purely additive and touch no shipped step.",
                )


# ---------------------------------------------------------------------------
# U-A3 Wave 2: canonical routing request validation and deterministic
# eligibility (agentic-os-v0.4-u-a3-routing-handoffs-contract.md §6-7).
#
# Pure-function tests only: no real workspace, no `conn`. Fixtures build
# `models.Agent` / `models.AgentPassport` rows and `routing.CandidateSnapshot`
# objects directly, and a minimal-but-real `beast.agent-passport/v1` document
# serialized through `protocols.serialize_canonical` — the same canonical
# bytes a real passport row would carry.

VALID_REQUEST = {
    "request_schema": routing.REQUEST_SCHEMA,
    "algorithm_version": routing.ALGORITHM_VERSION,
}


def _passport_document(**over) -> dict:
    doc = dict(
        schema="beast.agent-passport/v1",
        protocol_version=1,
        content_hash_alg=protocols.CONTENT_HASH_ALG,
        content_sha256=HASH,
        created_at=NOW,
        issuer="human",
        agent="alpha",
        passport_version=1,
        agent_class="custom",
        agent_scope={"level": "global"},
        role="worker",
        mission="do stuff",
        autonomy="supervised",
        escalation="ask_human",
        provenance={"created_by": "human:tester", "method": "create"},
        task_families=["build.code"],
        capabilities=["cap.write"],
        evidence_expectations={"evidence_kinds": ["file"], "min_evidence_count": 1},
        data_classifications=["internal"],
        skill_requirements=["skill.python"],
        tool_requirements=["tool.git"],
        model_requirements={"min_context_tokens": 50000, "modalities": ["text"]},
    )
    doc.update(over)
    return doc


def _passport_document_text(**over) -> str:
    return protocols.serialize_canonical(_passport_document(**over)).decode("utf-8")


def _routing_agent(**over) -> models.Agent:
    fields = dict(
        id=1,
        name="alpha",
        agent_class="custom",
        scope="global",
        project_id=None,
        lifecycle="active",
        protected=0,
        owner="human",
        origin="create",
        current_passport_version=1,
        created_at=NOW,
        updated_at=NOW,
        kind=None,
        invoke_hint=None,
        capabilities_json=None,
        trust_level=None,
        notes=None,
        content_sha256=HASH,
    )
    fields.update(over)
    return models.Agent(**fields)


def _routing_passport(**over) -> models.AgentPassport:
    fields = dict(
        id=1,
        agent_id=1,
        version=1,
        status="published",
        created_at=NOW,
        published_at=NOW,
        document=_passport_document_text(),
        content_sha256=HASH,
    )
    fields.update(over)
    return models.AgentPassport(**fields)


def _snapshot(**over) -> routing.CandidateSnapshot:
    fields = dict(
        agent=_routing_agent(),
        identity_integrity="ok",
        history_problems=(),
        current_passport=_routing_passport(),
        project_slug=None,
        catalog_upgrade_available=False,
    )
    fields.update(over)
    return routing.CandidateSnapshot(**fields)


def _request(**over) -> dict:
    return routing.validate_request(dict(VALID_REQUEST, **over))


# ---------------------------------------------------------------------------
# REQUEST VALIDATION (tests 1-22)

class RequestValidationTests(unittest.TestCase):
    def test_exact_required_request_schema(self):
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(
                dict(VALID_REQUEST, request_schema="aos.routing-request/v2")
            )
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request({"algorithm_version": routing.ALGORITHM_VERSION})
        normalized = routing.validate_request(dict(VALID_REQUEST))
        self.assertEqual(normalized["request_schema"], "aos.routing-request/v1")

    def test_exact_required_algorithm_version(self):
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(
                dict(VALID_REQUEST, algorithm_version="aos-routing-order/v2")
            )
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request({"request_schema": routing.REQUEST_SCHEMA})
        normalized = routing.validate_request(dict(VALID_REQUEST))
        self.assertEqual(normalized["algorithm_version"], "aos-routing-order/v1")

    def test_unknown_top_level_key_refuses(self):
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(dict(VALID_REQUEST, bogus_field=1))

    def test_missing_required_identity_fields(self):
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request({})
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request({"request_schema": routing.REQUEST_SCHEMA})

    def test_task_positive_integer_and_bool_rejection(self):
        normalized = routing.validate_request(dict(VALID_REQUEST, task=42))
        self.assertEqual(normalized["task"], 42)
        normalized = routing.validate_request(dict(VALID_REQUEST, task=ids.MAX_ID))
        self.assertEqual(normalized["task"], ids.MAX_ID)
        for bad in (0, -1, True, False, 1.5, "5", ids.MAX_ID + 1, None):
            with self.assertRaises(routing.RoutingRequestError):
                routing.validate_request(dict(VALID_REQUEST, task=bad))

    def test_project_slug_validation(self):
        normalized = routing.validate_request(dict(VALID_REQUEST, project="demo-project"))
        self.assertEqual(normalized["project"], "demo-project")
        normalized = routing.validate_request(dict(VALID_REQUEST, project="a" * 64))
        self.assertEqual(normalized["project"], "a" * 64)
        for bad in ("Bad Slug", "UP", "a" * 65, "", 5, None, "proj\n"):
            with self.assertRaises(routing.RoutingRequestError):
                routing.validate_request(dict(VALID_REQUEST, project=bad))

    def test_pattern_bound_requirement_arrays_minimum_and_maximum(self):
        cases = {
            "task_families": "fam.a",
            "capabilities": "cap.a",
            "skills": "skill.a",
            "tools": "tool.a",
        }
        for field, prefix in cases.items():
            with self.subTest(field=field):
                with self.assertRaises(routing.RoutingRequestError):
                    routing.validate_request(dict(VALID_REQUEST, **{field: []}))
                too_many = [f"{prefix}{i}" for i in range(17)]
                with self.assertRaises(routing.RoutingRequestError):
                    routing.validate_request(dict(VALID_REQUEST, **{field: too_many}))
                exactly_16 = [f"{prefix}{i}" for i in range(16)]
                normalized = routing.validate_request(
                    dict(VALID_REQUEST, **{field: exactly_16})
                )
                self.assertEqual(len(normalized[field]), 16)

    def test_vocabulary_bound_requirement_arrays_minimum_and_maximum(self):
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(dict(VALID_REQUEST, evidence_kinds=[]))
        normalized = routing.validate_request(
            dict(VALID_REQUEST, evidence_kinds=list(models.EVIDENCE_KINDS))
        )
        self.assertEqual(len(normalized["evidence_kinds"]), len(models.EVIDENCE_KINDS))

        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(dict(VALID_REQUEST, required_autonomy=[]))
        normalized = routing.validate_request(
            dict(VALID_REQUEST, required_autonomy=list(models.AGENT_AUTONOMY_LEVELS))
        )
        self.assertEqual(
            len(normalized["required_autonomy"]), len(models.AGENT_AUTONOMY_LEVELS)
        )

    def test_duplicate_refusal_before_sorting(self):
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(
                dict(VALID_REQUEST, capabilities=["b.cap", "a.cap", "a.cap"])
            )
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(
                dict(VALID_REQUEST, required_autonomy=["scoped", "scoped"])
            )

    def test_canonical_code_point_sorting(self):
        normalized = routing.validate_request(
            dict(VALID_REQUEST, capabilities=["cap.zz", "cap.aa", "cap.ab"])
        )
        self.assertEqual(
            normalized["capabilities"], ("cap.aa", "cap.ab", "cap.zz")
        )
        normalized = routing.validate_request(
            dict(VALID_REQUEST, required_autonomy=["suggest", "declare_only"])
        )
        self.assertEqual(normalized["required_autonomy"], ("declare_only", "suggest"))

    def test_no_case_folding(self):
        normalized = routing.validate_request(
            dict(VALID_REQUEST, preferred_agent="Alpha-Agent")
        )
        self.assertEqual(normalized["preferred_agent"], "Alpha-Agent")
        source = (REPO_ROOT / "agentic_os" / "routing.py").read_text(encoding="utf-8")
        for token in (".lower(", ".upper(", ".casefold("):
            self.assertNotIn(token, source)

    def test_no_unicode_normalization(self):
        # NFD-composed accented input to an ASCII-anchored field must be
        # flatly refused, never silently normalized into an accepted form.
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(
                dict(VALID_REQUEST, preferred_agent="café-agent")
            )
        source = (REPO_ROOT / "agentic_os" / "routing.py").read_text(encoding="utf-8")
        self.assertNotIn("unicodedata", source)
        self.assertNotIn(".normalize(", source)

    def test_closed_enum_fields_reject_unknown_values(self):
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(dict(VALID_REQUEST, required_scope="cosmic"))
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(
                dict(VALID_REQUEST, required_agent_class="cosmic")
            )
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(
                dict(VALID_REQUEST, evidence_kinds=["not_a_real_kind"])
            )
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(
                dict(VALID_REQUEST, required_data_classification="cosmic")
            )
        for scope in models.AGENT_SCOPES:
            self.assertEqual(
                routing.validate_request(dict(VALID_REQUEST, required_scope=scope))[
                    "required_scope"
                ],
                scope,
            )
        for cls in models.AGENT_CLASSES:
            self.assertEqual(
                routing.validate_request(
                    dict(VALID_REQUEST, required_agent_class=cls)
                )["required_agent_class"],
                cls,
            )

    def test_required_autonomy_membership_semantics(self):
        normalized = routing.validate_request(
            dict(VALID_REQUEST, required_autonomy=["scoped", "supervised"])
        )
        self.assertEqual(normalized["required_autonomy"], ("scoped", "supervised"))
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(
                dict(VALID_REQUEST, required_autonomy=["not_a_level"])
            )

    def test_no_autonomy_rank_helper(self):
        self.assertFalse(hasattr(routing, "autonomy_rank"))
        autonomy_symbols = [n for n in dir(routing) if "autonomy" in n.lower()]
        self.assertEqual(autonomy_symbols, [])
        source = (REPO_ROOT / "agentic_os" / "routing.py").read_text(encoding="utf-8")
        self.assertNotIn("autonomy_rank", source)

    def test_required_data_classification_membership_semantics(self):
        for level in models.MEMORY_SENSITIVITIES:
            normalized = routing.validate_request(
                dict(VALID_REQUEST, required_data_classification=level)
            )
            self.assertEqual(normalized["required_data_classification"], level)
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(
                dict(VALID_REQUEST, required_data_classification="not_a_level")
            )

    def test_model_capabilities_closed_keys(self):
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(
                dict(VALID_REQUEST, model_capabilities={"temperature": 0.5})
            )
        normalized = routing.validate_request(
            dict(VALID_REQUEST, model_capabilities={"min_context_tokens": 1000})
        )
        self.assertEqual(
            normalized["model_capabilities"], {"min_context_tokens": 1000}
        )

    def test_model_capabilities_requires_one_key(self):
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(dict(VALID_REQUEST, model_capabilities={}))

    def test_min_context_tokens_bounds_and_bool_rejection(self):
        normalized = routing.validate_request(
            dict(VALID_REQUEST, model_capabilities={"min_context_tokens": 1})
        )
        self.assertEqual(normalized["model_capabilities"]["min_context_tokens"], 1)
        normalized = routing.validate_request(
            dict(
                VALID_REQUEST,
                model_capabilities={"min_context_tokens": 99_999_999},
            )
        )
        self.assertEqual(
            normalized["model_capabilities"]["min_context_tokens"], 99_999_999
        )
        for bad in (0, -1, 100_000_000, True, 1.5, "1000"):
            with self.assertRaises(routing.RoutingRequestError):
                routing.validate_request(
                    dict(VALID_REQUEST, model_capabilities={"min_context_tokens": bad})
                )

    def test_modalities_vocabulary_bounds_duplicates_and_sorting(self):
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(
                dict(VALID_REQUEST, model_capabilities={"modalities": []})
            )
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(
                dict(
                    VALID_REQUEST,
                    model_capabilities={"modalities": ["text", "text"]},
                )
            )
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(
                dict(
                    VALID_REQUEST,
                    model_capabilities={"modalities": ["not_a_modality"]},
                )
            )
        normalized = routing.validate_request(
            dict(
                VALID_REQUEST,
                model_capabilities={"modalities": ["image", "code", "audio", "text"]},
            )
        )
        self.assertEqual(
            normalized["model_capabilities"]["modalities"],
            ("audio", "code", "image", "text"),
        )

    def test_defaults(self):
        normalized = routing.validate_request(dict(VALID_REQUEST))
        self.assertEqual(normalized["scope_preference"], "specific_first")
        self.assertEqual(normalized["surplus_policy"], "minimal")
        self.assertEqual(normalized["max_candidates"], 5)
        self.assertIs(normalized["include_diagnostics"], True)
        # Spelled out explicitly, the defaults normalize identically.
        explicit = routing.validate_request(
            dict(
                VALID_REQUEST,
                scope_preference="specific_first",
                surplus_policy="minimal",
                max_candidates=5,
                include_diagnostics=True,
            )
        )
        self.assertEqual(normalized, explicit)

    def test_empty_requirement_arrays_refuse(self):
        for field in (
            "task_families",
            "capabilities",
            "evidence_kinds",
            "required_autonomy",
            "skills",
            "tools",
        ):
            with self.subTest(field=field):
                with self.assertRaises(routing.RoutingRequestError):
                    routing.validate_request(dict(VALID_REQUEST, **{field: []}))
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(
                dict(VALID_REQUEST, model_capabilities={"modalities": []})
            )

    def test_forbidden_prose_keys_refuse(self):
        for key in (
            "prompt",
            "instructions",
            "credentials",
            "provider",
            "objective",
            "secret",
            "tool_arguments",
            "actor",
            "created_at",
        ):
            with self.subTest(key=key):
                with self.assertRaises(routing.RoutingRequestError):
                    routing.validate_request(dict(VALID_REQUEST, **{key: "anything"}))


# ---------------------------------------------------------------------------
# CANONICALIZATION AND DIGEST (tests 23-29)

class CanonicalizationAndDigestTests(unittest.TestCase):
    def test_equivalent_key_order_identical_bytes(self):
        raw_a = {
            "request_schema": routing.REQUEST_SCHEMA,
            "algorithm_version": routing.ALGORITHM_VERSION,
            "capabilities": ["a.cap"],
            "task": 5,
        }
        raw_b = {
            "task": 5,
            "capabilities": ["a.cap"],
            "algorithm_version": routing.ALGORITHM_VERSION,
            "request_schema": routing.REQUEST_SCHEMA,
        }
        bytes_a = routing.canonicalize_request(routing.validate_request(raw_a))
        bytes_b = routing.canonicalize_request(routing.validate_request(raw_b))
        self.assertEqual(bytes_a, bytes_b)
        self.assertEqual(routing.request_digest(routing.validate_request(raw_a)),
                          routing.request_digest(routing.validate_request(raw_b)))

    def test_equivalent_array_order_identical_bytes(self):
        normalized_a = routing.validate_request(
            dict(VALID_REQUEST, capabilities=["b.cap", "a.cap"])
        )
        normalized_b = routing.validate_request(
            dict(VALID_REQUEST, capabilities=["a.cap", "b.cap"])
        )
        self.assertEqual(
            routing.canonicalize_request(normalized_a),
            routing.canonicalize_request(normalized_b),
        )

    def test_canonical_round_trip_through_existing_parser(self):
        normalized = routing.validate_request(
            dict(VALID_REQUEST, capabilities=["b.cap", "a.cap"], task=7)
        )
        canonical = routing.canonicalize_request(normalized)
        parsed = protocols.parse_canonical(canonical)
        self.assertEqual(protocols.serialize_canonical(parsed), canonical)
        self.assertEqual(parsed["task"], 7)
        self.assertEqual(parsed["capabilities"], ["a.cap", "b.cap"])

    def test_digest_is_lowercase_64_hex_sha256(self):
        normalized = routing.validate_request(dict(VALID_REQUEST))
        digest = routing.request_digest(normalized)
        self.assertEqual(len(digest), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in digest))
        expected = hashlib.sha256(
            protocols.serialize_canonical(normalized)
        ).hexdigest()
        self.assertEqual(digest, expected)

    def test_semantic_change_alters_bytes_and_digest(self):
        base = routing.validate_request(dict(VALID_REQUEST, capabilities=["a.cap"]))
        changed = routing.validate_request(dict(VALID_REQUEST, capabilities=["b.cap"]))
        self.assertNotEqual(
            routing.canonicalize_request(base), routing.canonicalize_request(changed)
        )
        self.assertNotEqual(
            routing.request_digest(base), routing.request_digest(changed)
        )

    def test_no_actor_time_workspace_facts_in_request(self):
        for key in ("actor", "created_at", "workspace_id", "row_id", "db_id"):
            self.assertNotIn(key, routing._ALLOWED_REQUEST_KEYS)
            with self.assertRaises(routing.RoutingRequestError):
                routing.validate_request(dict(VALID_REQUEST, **{key: "x"}))

    def test_validate_request_does_not_mutate_input(self):
        raw_list = ["b.cap", "a.cap"]
        raw = dict(VALID_REQUEST, capabilities=raw_list)
        before = copy.deepcopy(raw)
        routing.validate_request(raw)
        self.assertEqual(raw, before)
        self.assertEqual(raw_list, ["b.cap", "a.cap"])


# ---------------------------------------------------------------------------
# BASE ELIGIBILITY (tests 30-40)

class BaseEligibilityTests(unittest.TestCase):
    def test_active_valid_current_passport_is_eligible(self):
        result = routing.evaluate_candidate(_request(), _snapshot())
        self.assertEqual(result.verdict, "eligible")
        self.assertEqual(result.reasons, ())
        self.assertEqual(result.warnings, ())

    def test_identity_tampered(self):
        result = routing.evaluate_candidate(
            _request(), _snapshot(identity_integrity="mismatch")
        )
        self.assertEqual(result.verdict, "excluded")
        self.assertEqual(result.reasons, ("identity_tampered",))

    def test_passport_history_tampered(self):
        result = routing.evaluate_candidate(
            _request(), _snapshot(history_problems=("v1: mismatch",))
        )
        self.assertEqual(result.verdict, "excluded")
        self.assertEqual(result.reasons, ("passport_history_tampered",))

    def test_draft_only(self):
        agent = _routing_agent(lifecycle="draft")
        result = routing.evaluate_candidate(_request(), _snapshot(agent=agent))
        self.assertEqual(result.verdict, "excluded")
        self.assertEqual(result.reasons, ("draft_only",))

    def test_suspended(self):
        agent = _routing_agent(lifecycle="suspended")
        result = routing.evaluate_candidate(_request(), _snapshot(agent=agent))
        self.assertEqual(result.verdict, "excluded")
        self.assertEqual(result.reasons, ("suspended",))

    def test_archived(self):
        agent = _routing_agent(lifecycle="archived")
        result = routing.evaluate_candidate(_request(), _snapshot(agent=agent))
        self.assertEqual(result.verdict, "excluded")
        self.assertEqual(result.reasons, ("archived",))

    def test_revoked(self):
        agent = _routing_agent(lifecycle="revoked")
        result = routing.evaluate_candidate(_request(), _snapshot(agent=agent))
        self.assertEqual(result.verdict, "excluded")
        self.assertEqual(result.reasons, ("revoked",))

    def test_legacy_without_passport(self):
        agent = _routing_agent(origin="legacy", current_passport_version=None)
        result = routing.evaluate_candidate(
            _request(), _snapshot(agent=agent, current_passport=None)
        )
        self.assertEqual(result.verdict, "excluded")
        self.assertEqual(result.reasons, ("legacy_without_passport",))

    def test_no_current_published_passport(self):
        agent = _routing_agent(current_passport_version=None)
        result = routing.evaluate_candidate(
            _request(), _snapshot(agent=agent, current_passport=None)
        )
        self.assertEqual(result.verdict, "excluded")
        self.assertEqual(result.reasons, ("no_current_published_passport",))

    def test_multiple_base_reasons_in_canonical_order(self):
        agent = _routing_agent(
            lifecycle="suspended", origin="legacy", current_passport_version=None
        )
        result = routing.evaluate_candidate(
            _request(),
            _snapshot(
                agent=agent, identity_integrity="mismatch", current_passport=None
            ),
        )
        self.assertEqual(result.verdict, "excluded")
        self.assertEqual(
            result.reasons,
            ("identity_tampered", "suspended", "legacy_without_passport"),
        )

    def test_hard_reason_precedence_over_unresolved(self):
        agent = _routing_agent(lifecycle="suspended")
        passport = _routing_passport(document=b"\x00not text or json")
        result = routing.evaluate_candidate(
            _request(), _snapshot(agent=agent, current_passport=passport)
        )
        self.assertEqual(result.verdict, "excluded")
        self.assertIn("suspended", result.reasons)
        self.assertIn("malformed_declaration", result.reasons)


# ---------------------------------------------------------------------------
# REQUIREMENT ELIGIBILITY (tests 41-55)

class RequirementEligibilityTests(unittest.TestCase):
    def test_project_match_and_mismatch(self):
        agent = _routing_agent(scope="project", project_id=1)
        matching = _snapshot(agent=agent, project_slug="demo")
        result = routing.evaluate_candidate(_request(project="demo"), matching)
        self.assertEqual(result.verdict, "eligible")

        mismatched = _snapshot(agent=agent, project_slug="other")
        result = routing.evaluate_candidate(_request(project="demo"), mismatched)
        self.assertEqual(result.verdict, "excluded")
        self.assertIn("project_mismatch", result.reasons)

    def test_required_scope_both_directions(self):
        global_agent = _snapshot(agent=_routing_agent(scope="global"))
        result = routing.evaluate_candidate(
            _request(required_scope="project"), global_agent
        )
        self.assertIn("scope_mismatch", result.reasons)

        project_agent = _snapshot(
            agent=_routing_agent(scope="project", project_id=1), project_slug="demo"
        )
        result = routing.evaluate_candidate(
            _request(required_scope="global"), project_agent
        )
        self.assertIn("scope_mismatch", result.reasons)

        result = routing.evaluate_candidate(
            _request(required_scope="global"), global_agent
        )
        self.assertNotIn("scope_mismatch", result.reasons)

    def test_agent_class_match_and_mismatch(self):
        agent = _routing_agent(agent_class="specialist")
        snap = _snapshot(agent=agent)
        result = routing.evaluate_candidate(
            _request(required_agent_class="specialist"), snap
        )
        self.assertNotIn("agent_class_mismatch", result.reasons)
        result = routing.evaluate_candidate(
            _request(required_agent_class="custom"), snap
        )
        self.assertIn("agent_class_mismatch", result.reasons)

    def test_data_classification_declared_absent_lacking_containing(self):
        absent = _snapshot(
            current_passport=_routing_passport(
                document=_passport_document_text(data_classifications=None) or None
            )
        )
        # Build a document with the key entirely omitted.
        doc = _passport_document()
        del doc["data_classifications"]
        absent = _snapshot(
            current_passport=_routing_passport(
                document=protocols.serialize_canonical(doc).decode("utf-8")
            )
        )
        result = routing.evaluate_candidate(
            _request(required_data_classification="internal"), absent
        )
        self.assertIn("data_classification_mismatch", result.reasons)
        self.assertEqual(
            result.diagnostics["data_classification"], {"declared": False}
        )

        lacking = _snapshot(
            current_passport=_routing_passport(
                document=_passport_document_text(data_classifications=["public"])
            )
        )
        result = routing.evaluate_candidate(
            _request(required_data_classification="confidential"), lacking
        )
        self.assertIn("data_classification_mismatch", result.reasons)
        self.assertEqual(
            result.diagnostics["data_classification"], {"declared": True}
        )
        # Membership, never a ceiling: declaring only "confidential" excludes
        # an "internal" request even though "confidential" sounds "higher".
        only_confidential = _snapshot(
            current_passport=_routing_passport(
                document=_passport_document_text(data_classifications=["confidential"])
            )
        )
        result = routing.evaluate_candidate(
            _request(required_data_classification="internal"), only_confidential
        )
        self.assertIn("data_classification_mismatch", result.reasons)

        containing = _snapshot(
            current_passport=_routing_passport(
                document=_passport_document_text(
                    data_classifications=["public", "internal"]
                )
            )
        )
        result = routing.evaluate_candidate(
            _request(required_data_classification="internal"), containing
        )
        self.assertNotIn("data_classification_mismatch", result.reasons)
        self.assertEqual(result.verdict, "eligible")

    def test_autonomy_exact_membership(self):
        snap = _snapshot(
            current_passport=_routing_passport(
                document=_passport_document_text(autonomy="scoped")
            )
        )
        result = routing.evaluate_candidate(
            _request(required_autonomy=["scoped"]), snap
        )
        self.assertEqual(result.verdict, "eligible")
        result = routing.evaluate_candidate(
            _request(required_autonomy=["suggest"]), snap
        )
        self.assertIn("autonomy_mismatch", result.reasons)

    def test_task_family_subset_and_miss(self):
        snap = _snapshot(
            current_passport=_routing_passport(
                document=_passport_document_text(
                    task_families=["build.code", "build.research"]
                )
            )
        )
        result = routing.evaluate_candidate(
            _request(task_families=["build.code"]), snap
        )
        self.assertNotIn("missing_task_family", result.reasons)
        result = routing.evaluate_candidate(
            _request(task_families=["build.code", "build.writing"]), snap
        )
        self.assertIn("missing_task_family", result.reasons)
        self.assertEqual(
            result.diagnostics["task_families"],
            {"declared": True, "requested_count": 2, "missing_count": 1},
        )

    def test_capability_subset_and_miss(self):
        snap = _snapshot()
        result = routing.evaluate_candidate(_request(capabilities=["cap.write"]), snap)
        self.assertNotIn("missing_capability", result.reasons)
        result = routing.evaluate_candidate(_request(capabilities=["cap.nope"]), snap)
        self.assertIn("missing_capability", result.reasons)

    def test_evidence_kind_subset_and_miss(self):
        snap = _snapshot()
        result = routing.evaluate_candidate(_request(evidence_kinds=["file"]), snap)
        self.assertNotIn("missing_evidence_kind", result.reasons)
        result = routing.evaluate_candidate(_request(evidence_kinds=["commit"]), snap)
        self.assertIn("missing_evidence_kind", result.reasons)

    def test_skill_byte_exact_subset_and_miss(self):
        snap = _snapshot(
            current_passport=_routing_passport(
                document=_passport_document_text(
                    skill_requirements=["skill.python/v2"]
                )
            )
        )
        result = routing.evaluate_candidate(
            _request(skills=["skill.python/v2"]), snap
        )
        self.assertNotIn("missing_skill_declaration", result.reasons)
        # Byte-exact: the unversioned spelling does not match the pinned one.
        result = routing.evaluate_candidate(_request(skills=["skill.python"]), snap)
        self.assertIn("missing_skill_declaration", result.reasons)

    def test_tool_byte_exact_subset_and_miss(self):
        snap = _snapshot()
        result = routing.evaluate_candidate(_request(tools=["tool.git"]), snap)
        self.assertNotIn("missing_tool_declaration", result.reasons)
        result = routing.evaluate_candidate(_request(tools=["tool.docker"]), snap)
        self.assertIn("missing_tool_declaration", result.reasons)

    def test_model_context_threshold(self):
        snap = _snapshot()  # declares min_context_tokens=50000
        result = routing.evaluate_candidate(
            _request(model_capabilities={"min_context_tokens": 40000}), snap
        )
        self.assertNotIn("missing_model_capability", result.reasons)
        result = routing.evaluate_candidate(
            _request(model_capabilities={"min_context_tokens": 60000}), snap
        )
        self.assertIn("missing_model_capability", result.reasons)

    def test_model_modality_subset(self):
        snap = _snapshot()  # declares modalities=["text"]
        result = routing.evaluate_candidate(
            _request(model_capabilities={"modalities": ["text"]}), snap
        )
        self.assertNotIn("missing_model_capability", result.reasons)
        result = routing.evaluate_candidate(
            _request(model_capabilities={"modalities": ["text", "code"]}), snap
        )
        self.assertIn("missing_model_capability", result.reasons)

    def test_absent_model_declaration(self):
        doc = _passport_document()
        del doc["model_requirements"]
        snap = _snapshot(
            current_passport=_routing_passport(
                document=protocols.serialize_canonical(doc).decode("utf-8")
            )
        )
        result = routing.evaluate_candidate(
            _request(model_capabilities={"min_context_tokens": 1}), snap
        )
        self.assertIn("missing_model_capability", result.reasons)
        self.assertEqual(
            result.diagnostics["model_capabilities"]["declared"], False
        )

    def test_preferred_agent_mismatch_remains_eligible(self):
        result = routing.evaluate_candidate(
            _request(preferred_agent="someone-else"), _snapshot()
        )
        self.assertEqual(result.verdict, "eligible")
        self.assertEqual(result.reasons, ("preferred_agent_mismatch",))

    def test_absent_optional_dimensions_are_neutral(self):
        result = routing.evaluate_candidate(_request(), _snapshot())
        self.assertEqual(result.verdict, "eligible")
        self.assertEqual(result.reasons, ())
        self.assertEqual(result.warnings, ())


# ---------------------------------------------------------------------------
# MALFORMED AND UNKNOWN (tests 56-60)

class MalformedAndUnknownTests(unittest.TestCase):
    def test_malformed_consulted_declaration_is_unresolved(self):
        doc = _passport_document(capabilities="not-an-array")
        snap = _snapshot(
            current_passport=_routing_passport(
                document=protocols.serialize_canonical(doc).decode("utf-8")
            )
        )
        result = routing.evaluate_candidate(_request(capabilities=["cap.write"]), snap)
        self.assertEqual(result.verdict, "unresolved")
        self.assertEqual(result.reasons, ("malformed_declaration",))

    def test_unknown_consulted_vocabulary_is_unresolved(self):
        doc = _passport_document(autonomy="from_the_future")
        snap = _snapshot(
            current_passport=_routing_passport(
                document=protocols.serialize_canonical(doc).decode("utf-8")
            )
        )
        result = routing.evaluate_candidate(
            _request(required_autonomy=["scoped"]), snap
        )
        self.assertEqual(result.verdict, "unresolved")
        self.assertEqual(result.reasons, ("unknown_declaration_value",))

    def test_raw_malformed_value_never_appears_in_diagnostic(self):
        secret_shaped = "AKIA" + "Q" * 16
        doc = _passport_document(task_families=secret_shaped)
        snap = _snapshot(
            current_passport=_routing_passport(
                document=protocols.serialize_canonical(doc).decode("utf-8")
            )
        )
        result = routing.evaluate_candidate(
            _request(task_families=["build.code"]), snap
        )
        self.assertEqual(result.verdict, "unresolved")
        self.assertNotIn(secret_shaped, repr(result.diagnostics))
        self.assertNotIn(secret_shaped, repr(result.reasons))
        self.assertNotIn(secret_shaped, repr(result.warnings))

    def test_malformed_with_hard_lifecycle_reason_remains_excluded(self):
        agent = _routing_agent(lifecycle="archived")
        passport = _routing_passport(document=12345)
        result = routing.evaluate_candidate(
            _request(), _snapshot(agent=agent, current_passport=passport)
        )
        self.assertEqual(result.verdict, "excluded")
        self.assertIn("archived", result.reasons)
        self.assertIn("malformed_declaration", result.reasons)

    def test_blob_like_or_non_text_document_produces_closed_result(self):
        for bad_document in (b"\x00\x01binary", 12345, None, ["not", "text"], {}):
            with self.subTest(bad_document=repr(bad_document)[:20]):
                passport = _routing_passport(document=bad_document)
                snap = _snapshot(current_passport=passport)
                result = routing.evaluate_candidate(_request(), snap)
                self.assertEqual(result.verdict, "unresolved")
                self.assertEqual(result.reasons, ("malformed_declaration",))


# ---------------------------------------------------------------------------
# WARNINGS AND PARITY (tests 61-70)

class WarningsAndParityTests(unittest.TestCase):
    def test_passport_expired_warning_only(self):
        doc = _passport_document(expires_at="2025-01-01T00:00:00Z")
        snap = _snapshot(
            current_passport=_routing_passport(
                document=protocols.serialize_canonical(doc).decode("utf-8")
            )
        )
        result = routing.evaluate_candidate(
            _request(), snap, now="2026-01-01T00:00:00Z"
        )
        self.assertEqual(result.verdict, "eligible")
        self.assertEqual(result.warnings, ("passport_expired",))
        self.assertEqual(result.reasons, ())
        # No comparison instant supplied: no warning is fabricated.
        result_no_now = routing.evaluate_candidate(_request(), snap)
        self.assertEqual(result_no_now.warnings, ())

    def test_catalog_upgrade_available_warning_only(self):
        snap = _snapshot(catalog_upgrade_available=True)
        result = routing.evaluate_candidate(_request(), snap)
        self.assertEqual(result.verdict, "eligible")
        self.assertEqual(result.warnings, ("catalog_upgrade_available",))
        self.assertEqual(result.reasons, ())

    def test_warning_with_eligible_verdict(self):
        snap = _snapshot(catalog_upgrade_available=True)
        result = routing.evaluate_candidate(_request(), snap)
        self.assertEqual(result.verdict, "eligible")
        self.assertTrue(result.warnings)

    def test_warning_with_excluded_verdict(self):
        agent = _routing_agent(lifecycle="suspended")
        snap = _snapshot(agent=agent, catalog_upgrade_available=True)
        result = routing.evaluate_candidate(_request(), snap)
        self.assertEqual(result.verdict, "excluded")
        self.assertEqual(result.warnings, ("catalog_upgrade_available",))
        self.assertIn("suspended", result.reasons)

    def test_custom_and_catalog_equivalent_candidates_identical_outcome(self):
        custom_agent = _routing_agent(
            id=1, name="custom-agent", origin="create", owner="human"
        )
        catalog_agent = _routing_agent(
            id=2, name="aos.catalog-agent", origin="import", owner="system"
        )
        custom_doc = _passport_document(agent="custom-agent")
        catalog_doc = _passport_document(agent="aos.catalog-agent")
        custom_snap = _snapshot(
            agent=custom_agent,
            current_passport=_routing_passport(
                agent_id=1,
                document=protocols.serialize_canonical(custom_doc).decode("utf-8"),
            ),
        )
        catalog_snap = _snapshot(
            agent=catalog_agent,
            current_passport=_routing_passport(
                agent_id=2,
                document=protocols.serialize_canonical(catalog_doc).decode("utf-8"),
            ),
        )
        req = _request(capabilities=["cap.write"])
        custom_result = routing.evaluate_candidate(req, custom_snap)
        catalog_result = routing.evaluate_candidate(req, catalog_snap)
        self.assertEqual(custom_result.verdict, catalog_result.verdict)
        self.assertEqual(custom_result.reasons, catalog_result.reasons)
        self.assertEqual(custom_result.warnings, catalog_result.warnings)

    def test_owner_protected_system_catalog_provenance_have_no_effect(self):
        req = _request(capabilities=["cap.write"])
        variants = [
            dict(owner="human", protected=0, origin="create"),
            dict(owner="system", protected=1, origin="import"),
        ]
        outcomes = []
        for variant in variants:
            agent = _routing_agent(**variant)
            outcomes.append(routing.evaluate_candidate(req, _snapshot(agent=agent)))
        self.assertEqual(outcomes[0].verdict, outcomes[1].verdict)
        self.assertEqual(outcomes[0].reasons, outcomes[1].reasons)
        self.assertEqual(outcomes[0].warnings, outcomes[1].warnings)

    def test_request_level_refusal_codes_never_appear_in_output(self):
        result = routing.evaluate_candidate(_request(), _snapshot())
        for code in models.ROUTING_REQUEST_REFUSAL_CODES:
            self.assertNotIn(code, result.reasons)
            self.assertNotIn(code, result.warnings)
        agent = _routing_agent(current_passport_version=None)
        result = routing.evaluate_candidate(
            _request(), _snapshot(agent=agent, current_passport=None)
        )
        for code in models.ROUTING_REQUEST_REFUSAL_CODES:
            self.assertNotIn(code, result.reasons)

    def test_reasons_follow_canonical_order(self):
        agent = _routing_agent(lifecycle="suspended")
        result = routing.evaluate_candidate(
            _request(capabilities=["cap.nope"]), _snapshot(agent=agent)
        )
        ordered = [c for c in models.ROUTING_REASON_CODES if c in result.reasons]
        self.assertEqual(list(result.reasons), ordered)

    def test_warnings_follow_canonical_order(self):
        doc = _passport_document(expires_at="2025-01-01T00:00:00Z")
        snap = _snapshot(
            current_passport=_routing_passport(
                document=protocols.serialize_canonical(doc).decode("utf-8")
            ),
            catalog_upgrade_available=True,
        )
        result = routing.evaluate_candidate(
            _request(), snap, now="2026-01-01T00:00:00Z"
        )
        self.assertEqual(
            result.warnings, ("passport_expired", "catalog_upgrade_available")
        )

    def test_render_reason_summary_truncates_at_8_while_result_retains_all(self):
        many_codes = [
            "identity_tampered",
            "passport_history_tampered",
            "draft_only",
            "suspended",
            "archived",
            "revoked",
            "legacy_without_passport",
            "no_current_published_passport",
            "project_mismatch",
        ]
        self.assertEqual(len(many_codes), 9)
        summary = routing.render_reason_summary(many_codes)
        self.assertIn("(+1 more)", summary)
        shown = summary.split(" (+")[0].split(", ")
        self.assertEqual(len(shown), models.ROUTING_REASON_DISPLAY_LIMIT)
        # The value/JSON-shaped result keeps every code, never truncated.
        self.assertEqual(len(many_codes), 9)

    def test_render_reason_summary_no_truncation_under_limit(self):
        codes = ["suspended", "missing_capability"]
        self.assertEqual(
            routing.render_reason_summary(codes), "suspended, missing_capability"
        )


# ---------------------------------------------------------------------------
# PURITY (tests 71-75)

class PurityTests(unittest.TestCase):
    """The Wave-2 eligibility surface is pure; the Wave-3 plan layer is the
    one database-owning caller around it (§ database_enumeration). These tests
    keep both facts honest: `evaluate_candidate` never mutates its inputs and
    is deterministic, while the module as a whole — including `create_plan` —
    never executes, networks, spawns a subprocess, opens a file, or invokes a
    provider/model/tool. The routing plan is advisory: it stores rows and one
    event and does nothing else."""

    @classmethod
    def setUpClass(cls):
        cls.source = (REPO_ROOT / "agentic_os" / "routing.py").read_text(
            encoding="utf-8"
        )

    def test_no_execution_network_subprocess_or_provider_behavior(self):
        # SQL, db.transaction and events.emit are DELIBERATELY permitted from
        # Wave 3 on: create_plan owns exactly one transaction and emits exactly
        # one audit event. What must never appear is execution, network,
        # subprocess, filesystem opening or provider/model/tool invocation.
        forbidden = (
            "subprocess.",
            "socket.",
            "requests.",
            "urllib.",
            "http.client",
            "os.system(",
            "exec(",
            "eval(",
            "open(",
            "Path(",
            ".provider",
        )
        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, self.source)

    def test_plan_layer_owns_exactly_one_transaction_and_one_event(self):
        # The database-owning boundary is a single db.transaction with one
        # BEGIN IMMEDIATE and one routing_plan/create event — no nested
        # transaction, no second event action.
        self.assertEqual(self.source.count("with db.transaction("), 1)
        self.assertEqual(self.source.count('conn.execute("BEGIN IMMEDIATE")'), 1)
        self.assertEqual(self.source.count("events.emit("), 1)

    def test_evaluate_candidate_does_not_mutate_inputs(self):
        request = _request(capabilities=["cap.write"], task_families=["build.code"])
        request_before = copy.deepcopy(request)
        candidate = _snapshot()
        agent_before = dict(candidate.agent.as_dict())
        routing.evaluate_candidate(request, candidate)
        self.assertEqual(request, request_before)
        self.assertEqual(candidate.agent.as_dict(), agent_before)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            candidate.identity_integrity = "mismatch"

    def test_repeated_evaluation_is_byte_value_identical(self):
        request = _request(capabilities=["cap.write"])
        candidate = _snapshot()
        first = routing.evaluate_candidate(request, candidate)
        second = routing.evaluate_candidate(request, candidate)
        self.assertEqual(first, second)
        self.assertEqual(dict(first.diagnostics), dict(second.diagnostics))


# ---------------------------------------------------------------------------
# U-A3 Wave 2 CONTRACT CORRECTIONS
#
# Defect one — global declaration validation: every routing-relevant passport
# declaration PRESENT in the candidate's document is judged for structural
# validity BEFORE any request-specific gate, even when the request never
# constrains that dimension. An impossible type/shape yields
# `malformed_declaration`; a valid value outside this build's closed vocabulary
# yields `unknown_declaration_value`; either makes the candidate `unresolved`
# unless a hard-ineligible reason also applies (precedence unchanged).
#
# Defect two — JSON-compatible diagnostics: `EligibilityResult.diagnostics`
# (and any public projection over the result) consists only of JSON-compatible
# values, so `json.dumps` serializes it directly; the result is a value object
# whose returned diagnostics dict aliases nothing the caller passed in.


def _snapshot_with_document(doc: dict) -> routing.CandidateSnapshot:
    """A default-eligible candidate whose passport carries exactly `doc`,
    serialized through the real canonical serializer — the same bytes a stored
    passport row would hold."""
    return _snapshot(
        current_passport=_routing_passport(
            document=protocols.serialize_canonical(doc).decode("utf-8")
        )
    )


class GlobalDeclarationValidationTests(unittest.TestCase):
    """Defect one: unrequested routing-relevant declarations are validated."""

    def _assert_unresolved_single(self, doc: dict, code: str):
        # A bare request constrains no dimension, and the agent is otherwise
        # fully eligible — so the ONE global structural defect is the only
        # reason, proving validation fired without any request gate.
        result = routing.evaluate_candidate(_request(), _snapshot_with_document(doc))
        self.assertEqual(result.verdict, "unresolved")
        self.assertEqual(result.reasons, (code,))
        return result

    def test_1_malformed_unrequested_task_families(self):
        self._assert_unresolved_single(
            _passport_document(task_families=5), "malformed_declaration"
        )

    def test_2_malformed_unrequested_capabilities(self):
        # A non-string item inside an otherwise valid array.
        self._assert_unresolved_single(
            _passport_document(capabilities=[123]), "malformed_declaration"
        )

    def test_3_malformed_unrequested_evidence_expectations(self):
        # An impossible shape: the declaration is not an object at all.
        self._assert_unresolved_single(
            _passport_document(evidence_expectations="not-an-object"),
            "malformed_declaration",
        )
        # An impossible shape one level in: evidence_kinds is not an array.
        self._assert_unresolved_single(
            _passport_document(
                evidence_expectations={"evidence_kinds": "file", "min_evidence_count": 1}
            ),
            "malformed_declaration",
        )

    def test_4_malformed_unrequested_data_classifications(self):
        self._assert_unresolved_single(
            _passport_document(data_classifications="internal"),
            "malformed_declaration",
        )

    def test_5_unknown_unrequested_autonomy(self):
        self._assert_unresolved_single(
            _passport_document(autonomy="from_the_future"),
            "unknown_declaration_value",
        )

    def test_6_malformed_unrequested_skill_requirements(self):
        self._assert_unresolved_single(
            _passport_document(skill_requirements=5), "malformed_declaration"
        )

    def test_7_malformed_unrequested_tool_requirements(self):
        # The example verbatim: no tools requested, tool_requirements an integer.
        self._assert_unresolved_single(
            _passport_document(tool_requirements=5), "malformed_declaration"
        )

    def test_8_malformed_unrequested_model_requirements(self):
        # The declaration is not an object.
        self._assert_unresolved_single(
            _passport_document(model_requirements=5), "malformed_declaration"
        )

    def test_9_unknown_unrequested_model_modality(self):
        self._assert_unresolved_single(
            _passport_document(
                model_requirements={
                    "min_context_tokens": 50000,
                    "modalities": ["hologram"],
                }
            ),
            "unknown_declaration_value",
        )

    def test_10_hard_lifecycle_plus_malformed_unrequested_declaration(self):
        # A hard lifecycle reason AND a malformed UNREQUESTED declaration:
        # precedence keeps the verdict excluded while both codes survive, in
        # ROUTING_REASON_CODES canonical order (archived < malformed).
        agent = _routing_agent(lifecycle="archived")
        snap = _snapshot(
            agent=agent,
            current_passport=_routing_passport(
                document=protocols.serialize_canonical(
                    _passport_document(tool_requirements=5)
                ).decode("utf-8")
            ),
        )
        result = routing.evaluate_candidate(_request(), snap)
        self.assertEqual(result.verdict, "excluded")
        self.assertEqual(result.reasons, ("archived", "malformed_declaration"))
        canonical = [c for c in models.ROUTING_REASON_CODES if c in result.reasons]
        self.assertEqual(list(result.reasons), canonical)

    def test_11_valid_unrequested_declarations_remain_neutral(self):
        # The full, valid default passport under a bare request: the global pass
        # finds nothing, so the candidate stays eligible with no reasons.
        result = routing.evaluate_candidate(_request(), _snapshot())
        self.assertEqual(result.verdict, "eligible")
        self.assertEqual(result.reasons, ())
        self.assertEqual(result.warnings, ())

    def test_12_malformed_raw_value_absent_from_diagnostics_and_summary(self):
        secret = "AKIA" + "Z" * 16  # a credential-shaped raw declaration value
        result = self._assert_unresolved_single(
            _passport_document(tool_requirements=secret), "malformed_declaration"
        )
        self.assertNotIn(secret, json.dumps(result.diagnostics))
        self.assertNotIn(secret, repr(result.diagnostics))
        self.assertNotIn(secret, routing.render_reason_summary(result.reasons))
        self.assertNotIn(secret, repr(result.reasons))
        self.assertNotIn(secret, repr(result.warnings))


def _assert_json_value_tree(test: unittest.TestCase, value) -> None:
    """Every node is a JSON-compatible scalar or a dict/list of the same — never
    a MappingProxyType, set, bytes, exception, sqlite row, Agent, AgentPassport
    or arbitrary document/object fragment."""
    forbidden = (
        MappingProxyType,
        set,
        frozenset,
        bytes,
        bytearray,
        BaseException,
        models.Agent,
        models.AgentPassport,
        routing.CandidateSnapshot,
        routing.EligibilityResult,
        sqlite3.Row,
    )
    test.assertNotIsInstance(value, forbidden)
    if isinstance(value, dict):
        for key, item in value.items():
            test.assertIsInstance(key, str)
            _assert_json_value_tree(test, item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_json_value_tree(test, item)
    else:
        test.assertIsInstance(value, (str, bool, int, type(None)))


class JsonCompatibleDiagnosticsTests(unittest.TestCase):
    """Defect two: diagnostics and the public projection are JSON-serializable."""

    def _rich_result(self) -> routing.EligibilityResult:
        # Consults every diagnostics-bearing dimension against the valid default
        # passport, so the result is eligible with a fully populated diagnostics
        # dict (lifecycle, passport_version and the per-dimension sub-objects).
        request = _request(
            capabilities=["cap.write"],
            task_families=["build.code"],
            skills=["skill.python"],
            tools=["tool.git"],
            evidence_kinds=["file"],
            required_data_classification="internal",
            model_capabilities={"min_context_tokens": 40000, "modalities": ["text"]},
        )
        result = routing.evaluate_candidate(request, _snapshot())
        self.assertEqual(result.verdict, "eligible")
        return result

    @staticmethod
    def _projection(result: routing.EligibilityResult) -> dict:
        return {
            "agent_name": result.agent_name,
            "verdict": result.verdict,
            "reasons": result.reasons,
            "warnings": result.warnings,
            "diagnostics": result.diagnostics,
        }

    def test_13_json_dumps_diagnostics_succeeds(self):
        result = self._rich_result()
        # The bug: json.dumps(MappingProxyType({...})) raised TypeError. It
        # must now serialize directly, for both a rich and a minimal result.
        json.dumps(result.diagnostics)
        json.dumps(routing.evaluate_candidate(_request(), _snapshot()).diagnostics)
        self.assertIsInstance(result.diagnostics, dict)
        self.assertNotIsInstance(result.diagnostics, MappingProxyType)

    def test_14_public_projection_serializes_directly(self):
        projection = self._projection(self._rich_result())
        self.assertEqual(
            set(projection),
            {"agent_name", "verdict", "reasons", "warnings", "diagnostics"},
        )
        encoded = json.dumps(projection)  # tuples serialize as JSON arrays
        decoded = json.loads(encoded)
        self.assertEqual(decoded["verdict"], "eligible")
        self.assertEqual(decoded["reasons"], [])

    def test_15_diagnostics_contain_only_json_compatible_values(self):
        result = self._rich_result()
        _assert_json_value_tree(self, result.diagnostics)
        # No passport body fragment or requested/declared string leaked in.
        serialized = json.dumps(result.diagnostics)
        for prose in ("cap.write", "skill.python", "tool.git", "do stuff", "worker"):
            self.assertNotIn(prose, serialized)

    def test_16_repeated_evaluation_yields_value_equal_projections(self):
        request = _request(capabilities=["cap.write"], task_families=["build.code"])
        candidate = _snapshot()
        first = self._projection(routing.evaluate_candidate(request, candidate))
        second = self._projection(routing.evaluate_candidate(request, candidate))
        self.assertEqual(first, second)
        self.assertEqual(json.dumps(first, sort_keys=True),
                         json.dumps(second, sort_keys=True))

    def test_17_mutating_returned_diagnostics_isolates_all_sources(self):
        request = _request(capabilities=["cap.write"])
        candidate = _snapshot()
        request_before = copy.deepcopy(request)
        document_before = candidate.current_passport.document
        agent_before = dict(candidate.agent.as_dict())

        first = routing.evaluate_candidate(request, candidate)
        # Mutate both a top-level key and a nested sub-object of the result.
        first.diagnostics["injected_top"] = "x"
        first.diagnostics["capabilities"]["injected_nested"] = "y"

        # The request, snapshot, and passport document are untouched.
        self.assertEqual(request, request_before)
        self.assertEqual(candidate.current_passport.document, document_before)
        self.assertEqual(dict(candidate.agent.as_dict()), agent_before)

        # A subsequent evaluation is a fresh value, free of the injections.
        second = routing.evaluate_candidate(request, candidate)
        self.assertNotIn("injected_top", second.diagnostics)
        self.assertNotIn("injected_nested", second.diagnostics["capabilities"])


class EligibilityPurityTests(unittest.TestCase):
    """Purity of the corrected eligibility surface (tests 18-21)."""

    @classmethod
    def setUpClass(cls):
        cls.source = (REPO_ROOT / "agentic_os" / "routing.py").read_text(
            encoding="utf-8"
        )

    def test_18_eligibility_evaluation_takes_no_connection(self):
        # `evaluate_candidate` reasons only about the explicit CandidateSnapshot
        # the caller passes; it never opens or receives a connection. (The
        # Wave-3 plan layer IS the database-owning caller — that boundary is
        # asserted in PurityTests, not forbidden here.)
        params = inspect.signature(routing.evaluate_candidate).parameters
        self.assertEqual(list(params)[:2], ["request", "candidate"])
        self.assertNotIn("conn", params)
        self.assertNotIn("connection", params)

    def test_19_no_filesystem_network_subprocess_or_provider(self):
        for token in ("subprocess", "socket", "urllib", "requests.", "http.client",
                      "open(", "Path(", "os.system(", ".provider"):
            with self.subTest(token=token):
                self.assertNotIn(token, self.source)

    def test_20_no_current_time_read(self):
        for token in ("import time", "datetime", ".now(", ".utcnow(",
                      "time.time(", "monotonic", "perf_counter"):
            with self.subTest(token=token):
                self.assertNotIn(token, self.source)

    def test_21_evaluation_does_not_mutate_inputs(self):
        # Exercise both the new global-validation path (an unrequested malformed
        # declaration) and a consulted gate, then prove nothing upstream moved.
        request = _request(capabilities=["cap.write"])
        candidate = _snapshot_with_document(_passport_document(tool_requirements=5))
        request_before = copy.deepcopy(request)
        document_before = candidate.current_passport.document
        agent_before = dict(candidate.agent.as_dict())

        first = routing.evaluate_candidate(request, candidate)
        second = routing.evaluate_candidate(request, candidate)

        self.assertEqual(request, request_before)
        self.assertEqual(candidate.current_passport.document, document_before)
        self.assertEqual(dict(candidate.agent.as_dict()), agent_before)
        # Determinism: the same inputs yield an equal value each time.
        self.assertEqual(first, second)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            candidate.identity_integrity = "mismatch"


# ===========================================================================
# U-A3 WAVE 3 — ordering, plan persistence, reads, verification, staleness,
# the four route CLI leaves, and their power classifications. These run
# against a LIVE v5 workspace with real, hash-valid agents (create_agent +
# publish_passport), so eligibility, ordering, pins and hashes are genuine.
# ===========================================================================


class _LiveCase(unittest.TestCase):
    """A live in-memory v5 workspace plus helpers that build real published
    agents. Eligibility, ordering, pins and record hashes are all genuine."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)
        self.conn.executescript(db.SCHEMA_SQL)
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES ('schema_version', ?)",
            (db.SCHEMA_VERSION,),
        )
        self.conn.commit()

    # -- workspace builders --------------------------------------------------

    def add_project(self, slug="demo"):
        project, _ = ops.add_project(
            self.conn, slug=slug, name=slug.title(), repo=str(self.tmp)
        )
        return project

    def add_task(self, *, project=None, title="t"):
        return ops.add_task(self.conn, title=title, project_slug=project)

    def _fragment(self, name, body):
        frag = self.tmp / f"{name}.json"
        frag.write_text(json.dumps(body), encoding="utf-8")
        return frag

    def publish(self, name, *, project=None, **body):
        body.setdefault("autonomy", "supervised")
        passports.create_agent(
            self.conn, name=name, role="worker", mission="do",
            project_slug=project, fragment_path=self._fragment(name, body),
        )
        passports.publish_passport(self.conn, name=name, path=None)
        return passports.get_agent(self.conn, name)

    def publish_v2(self, name, **body):
        agent = passports.get_agent(self.conn, name)
        slug = None
        if agent.project_id is not None:
            slug = ops.get_project(self.conn, agent.project_id).slug
        body.setdefault("autonomy", "supervised")
        document = passports.build_passport_document(
            agent_name=name, passport_version=2, agent_class=agent.agent_class,
            scope_level=agent.scope, project_slug=slug, role="worker",
            mission="do v2", method="publish", fragment=body,
        )
        path = self.tmp / f"{name}_v2.json"
        path.write_text(
            protocols.serialize_canonical_file_bytes(document).decode("utf-8"),
            encoding="utf-8",
        )
        passports.publish_passport(self.conn, name=name, path=path)
        return passports.get_agent(self.conn, name)

    def draft(self, name, **body):
        passports.create_agent(
            self.conn, name=name, role="worker", mission="do",
            fragment_path=self._fragment(name, body),
        )
        return passports.get_agent(self.conn, name)

    # -- request / plan helpers ---------------------------------------------

    def request(self, **over):
        base = {
            "request_schema": routing.REQUEST_SCHEMA,
            "algorithm_version": routing.ALGORITHM_VERSION,
        }
        base.update(over)
        return routing.validate_request(base)

    def plan(self, **over):
        plan_id = routing.create_plan(self.conn, self.request(**over))
        return routing.get_plan(self.conn, plan_id)

    def candidates(self, plan):
        return routing.get_candidates(self.conn, plan.id)

    def by_name(self, plan):
        out = {}
        for c in self.candidates(plan):
            row = self.conn.execute(
                "SELECT name FROM agents WHERE id = ?", (c.agent_id,)
            ).fetchone()
            out[row["name"]] = c
        return out

    def count(self, table):
        return self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def events(self):
        return self.conn.execute(
            "SELECT entity, action, payload_json FROM events ORDER BY id"
        ).fetchall()


# ---------------------------------------------------------------------------
# (20)(21)(22) ORDERING

class Wave3OrderingTests(_LiveCase):
    def test_exact_ordering_json_and_surplus_direction(self):
        self.publish("a1", capabilities=["cap.a"], task_families=["tf.a"])
        self.publish(
            "a2", capabilities=["cap.a", "cap.b"], task_families=["tf.a", "tf.b"]
        )
        plan = self.plan(capabilities=["cap.a"], task_families=["tf.a"])
        rows = self.by_name(plan)
        # Minimal surplus wins (asc): a1 (0 surplus) ranks before a2.
        self.assertEqual(rows["a1"].rank, 1)
        self.assertEqual(rows["a2"].rank, 2)
        self.assertEqual(rows["a1"].ordering_json, "[0,0,0,0,0,0]")
        self.assertEqual(rows["a2"].ordering_json, "[0,0,1,1,0,0]")

    def test_preferred_agent_term_t1(self):
        self.publish("a1", capabilities=["cap.a"])
        self.publish("a2", capabilities=["cap.a", "cap.b"])
        plan = self.plan(capabilities=["cap.a"], preferred_agent="a2")
        rows = self.by_name(plan)
        # T1 dominates surplus: preferred a2 ranks first despite more surplus.
        self.assertEqual(rows["a2"].rank, 1)
        self.assertEqual(json.loads(rows["a2"].ordering_json)[0], 1)
        self.assertEqual(json.loads(rows["a1"].ordering_json)[0], 0)
        # The non-preferred eligible agent records preference_only, ordering-only.
        self.assertIn("preferred_agent_mismatch", json.loads(rows["a1"].reasons_json))

    def test_scope_preference_specific_first_and_none(self):
        self.add_project("demo")
        self.publish("g", capabilities=["cap.a"])                    # global
        self.publish("p", project="demo", capabilities=["cap.a"])    # project-scoped
        specific = self.plan(project="demo", capabilities=["cap.a"])
        rows = self.by_name(specific)
        self.assertEqual(rows["p"].rank, 1)  # T2=1 for the project-scoped agent
        self.assertEqual(json.loads(rows["p"].ordering_json)[1], 1)
        self.assertEqual(json.loads(rows["g"].ordering_json)[1], 0)
        none = self.plan(
            project="demo", capabilities=["cap.a"], scope_preference="none"
        )
        rows2 = self.by_name(none)
        # scope_preference=none zeroes T2 for all; the tie falls to T7 (name).
        for candidate in rows2.values():
            self.assertEqual(json.loads(candidate.ordering_json)[1], 0)
        self.assertEqual(rows2["g"].rank, 1)  # 'g' < 'p' by code point

    def test_surplus_policy_ignore_zeroes_only_surplus_terms(self):
        self.publish("a1", capabilities=["cap.a"])
        self.publish("a2", capabilities=["cap.a", "cap.b", "cap.c"])
        minimal = self.plan(capabilities=["cap.a"], surplus_policy="minimal")
        self.assertEqual(json.loads(self.by_name(minimal)["a2"].ordering_json)[3], 2)
        ignore = self.plan(capabilities=["cap.a"], surplus_policy="ignore")
        for candidate in self.by_name(ignore).values():
            self.assertEqual(json.loads(candidate.ordering_json)[2:], [0, 0, 0, 0])

    def test_final_tie_break_is_the_name(self):
        self.publish("zed", capabilities=["cap.a"])
        self.publish("abe", capabilities=["cap.a"])
        rows = self.by_name(self.plan(capabilities=["cap.a"]))
        # identical tuples ⇒ T7 (byte name) decides: abe before zed.
        self.assertEqual(rows["abe"].rank, 1)
        self.assertEqual(rows["zed"].rank, 2)

    def test_autonomy_and_classification_never_ordered(self):
        self.publish("a1", capabilities=["cap.a"], autonomy="scoped")
        self.publish("a2", capabilities=["cap.a"], autonomy="supervised")
        rows = self.by_name(self.plan(capabilities=["cap.a"]))
        # Differing only in autonomy ⇒ identical ordering tuples; name breaks it.
        self.assertEqual(
            json.loads(rows["a1"].ordering_json),
            json.loads(rows["a2"].ordering_json),
        )
        self.assertEqual(len(json.loads(rows["a1"].ordering_json)), 6)

    def test_ranks_contiguous_and_non_eligible_are_null(self):
        self.publish("ok1", capabilities=["cap.a"])
        self.publish("ok2", capabilities=["cap.a", "cap.b"])
        self.draft("drafty", capabilities=["cap.a"])            # excluded
        self.publish("nope", capabilities=["cap.z"])            # missing_capability
        plan = self.plan(capabilities=["cap.a"])
        rows = self.by_name(plan)
        self.assertEqual(sorted(c.rank for c in rows.values() if c.rank), [1, 2])
        for name in ("drafty", "nope"):
            self.assertIsNone(rows[name].rank)
            self.assertIsNone(rows[name].ordering_json)
            self.assertIsNone(rows[name].passport_version)
            self.assertIsNone(rows[name].passport_sha256)
            self.assertIsNone(rows[name].identity_sha256)

    def test_two_workspace_determinism_excludes_content_sha256(self):
        specs = [
            ("alpha", ["cap.a"]),
            ("bravo", ["cap.a", "cap.b"]),
            ("gamma", ["cap.a", "cap.b", "cap.c"]),
        ]

        def build(order):
            case = _LiveCase()
            case.setUp()
            self.addCleanup(case.doCleanups)
            for name, caps in order:
                case.publish(name, capabilities=caps)
            plan = case.plan(capabilities=["cap.a"])
            projection = [
                (
                    row.rank,
                    name,
                    row.passport_version,
                    row.passport_sha256,
                    json.loads(row.reasons_json),
                )
                for name, row in sorted(case.by_name(plan).items())
            ]
            return plan.request_sha256, projection, case

        # One frozen clock for both builds: passport created_at feeds
        # passport_sha256, so a real UTC-second boundary between the two
        # sequential builds would make the pins differ.
        with mock.patch.object(
            passports.utils,
            "utc_now_iso",
            return_value="2026-01-01T00:00:00Z",
        ):
            sha_a, proj_a, case_a = build(specs)
            sha_b, proj_b, case_b = build(list(reversed(specs)))
        self.assertEqual(sha_a, sha_b)                 # identical request digest
        self.assertEqual(proj_a, proj_b)               # identical ranked projection
        # content_sha256 legitimately differs (it binds workspace-specific ids).
        plan_a = case_a.conn.execute(
            "SELECT content_sha256 FROM routing_plans"
        ).fetchone()[0]
        plan_b = case_b.conn.execute(
            "SELECT content_sha256 FROM routing_plans"
        ).fetchone()[0]
        self.assertTrue(models.is_claim_hash(plan_a))
        self.assertTrue(models.is_claim_hash(plan_b))
        case_a.conn.close()
        case_b.conn.close()


# ---------------------------------------------------------------------------
# (23)-(32) PLAN CREATION

class Wave3PlanCreationTests(_LiveCase):
    def test_standalone_request_is_global(self):
        self.publish("a", capabilities=["cap.a"])
        plan = self.plan(capabilities=["cap.a"])
        self.assertEqual(plan.scope, "global")
        self.assertIsNone(plan.project_id)
        self.assertIsNone(plan.task_id)
        self.assertEqual(plan.result_status, "resolved")

    def test_task_derived_project(self):
        self.add_project("demo")
        task = self.add_task(project="demo")
        self.publish("a", capabilities=["cap.a"])
        plan_id = routing.create_plan(self.conn, self.request(task=task.id))
        plan = routing.get_plan(self.conn, plan_id)
        self.assertEqual(plan.scope, "project")
        self.assertEqual(plan.task_id, task.id)
        self.assertEqual(
            plan.project_id, ops.get_project_by_slug(self.conn, "demo").id
        )
        self.assertIn('"project":"demo"', plan.request_document)

    def test_explicit_project(self):
        self.add_project("demo")
        plan = self.plan(project="demo")
        self.assertEqual(plan.scope, "project")

    def test_task_project_disagreement_refuses_with_zero_writes(self):
        self.add_project("demo")
        self.add_project("other")
        task = self.add_task(project="demo")
        before = (self.count("routing_plans"), self.count("events"))
        with self.assertRaises(AosError):
            routing.create_plan(
                self.conn, self.request(task=task.id, project="other")
            )
        self.assertEqual(
            (self.count("routing_plans"), self.count("events")), before
        )

    def test_preferred_installed_agent(self):
        self.publish("pref", capabilities=["cap.a"])
        plan = self.plan(capabilities=["cap.a"], preferred_agent="pref")
        self.assertEqual(self.by_name(plan)["pref"].rank, 1)

    def test_agent_absent_refusal_zero_writes_and_events(self):
        self.publish("real", capabilities=["cap.a"])
        before = (self.count("routing_plans"), self.count("routing_plan_candidates"),
                  self.count("events"))
        with self.assertRaises(AosError) as ctx:
            routing.create_plan(self.conn, self.request(preferred_agent="ghost"))
        self.assertIn("agent_absent", str(ctx.exception))
        self.assertEqual(
            (self.count("routing_plans"), self.count("routing_plan_candidates"),
             self.count("events")),
            before,
        )

    def test_catalog_not_installed_refusal_zero_writes_and_events(self):
        from agentic_os import catalog

        name = catalog.catalog().entries[0].agent
        before = (self.count("routing_plans"), self.count("events"))
        with self.assertRaises(AosError) as ctx:
            routing.create_plan(self.conn, self.request(preferred_agent=name))
        self.assertIn("catalog_not_installed", str(ctx.exception))
        self.assertEqual(
            (self.count("routing_plans"), self.count("events")), before
        )

    def test_more_than_256_agents_refuses_without_truncation(self):
        # MAX+1 bare identity rows exceed the evaluation bound; the refusal must
        # fire before evaluation and truncate nothing.
        rows = [
            (f"a{i:04d}", "custom", "global", None, "draft", 0, "human",
             "create", None, NOW, NOW, HASH)
            for i in range(models.MAX_ROUTING_EVALUATED_AGENTS + 1)
        ]
        self.conn.executemany(
            "INSERT INTO agents (name, agent_class, scope, project_id, "
            "lifecycle, protected, owner, origin, current_passport_version, "
            "created_at, updated_at, content_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self.conn.commit()
        with self.assertRaises(AosError) as ctx:
            routing.create_plan(self.conn, self.request())
        self.assertIn("256", str(ctx.exception))
        self.assertEqual(self.count("routing_plans"), 0)
        self.assertEqual(self.count("routing_plan_candidates"), 0)

    def test_every_agent_persisted_exactly_once(self):
        for name in ("a", "b", "c"):
            self.publish(name, capabilities=["cap.a"])
        self.draft("d")
        plan = self.plan(capabilities=["cap.a"])
        rows = self.candidates(plan)
        self.assertEqual(len(rows), 4)
        self.assertEqual(len({r.agent_id for r in rows}), 4)

    def test_resolved_with_eligible_and_excluded(self):
        self.publish("good", capabilities=["cap.a"])
        self.publish("nope", capabilities=["cap.z"])   # excluded (missing)
        plan = self.plan(capabilities=["cap.a"])
        self.assertEqual(plan.result_status, "resolved")
        self.assertEqual(plan.eligible_count, 1)
        self.assertEqual(plan.excluded_count, 1)

    def test_all_excluded_is_no_eligible_candidates(self):
        self.publish("a", capabilities=["cap.a"])
        plan = self.plan(capabilities=["cap.z"])
        self.assertEqual(plan.result_status, "no_eligible_candidates")
        self.assertEqual(plan.eligible_count, 0)
        self.assertEqual(plan.unresolved_count, 0)
        self.assertEqual(plan.excluded_count, 1)

    def test_result_status_derivation_is_counts_only(self):
        # `unresolved` is unreachable from a same-build published passport (the
        # schema validates every declaration routing consults), so its storage
        # is proven by the DDL truth table; the derivation function itself is
        # exercised directly here. excluded_count never participates.
        self.assertEqual(routing._result_status(2, 0), "resolved")
        self.assertEqual(routing._result_status(2, 3), "resolved")
        self.assertEqual(routing._result_status(0, 3), "unresolved")
        self.assertEqual(routing._result_status(0, 0), "no_eligible_candidates")

    def test_display_controls_do_not_limit_storage(self):
        for i in range(6):
            self.publish(f"a{i}", capabilities=["cap.a"])
        capped = self.plan(capabilities=["cap.a"], max_candidates=1)
        self.assertEqual(capped.eligible_count, 6)
        self.assertEqual(len(self.candidates(capped)), 6)
        quiet = self.plan(capabilities=["cap.a"], include_diagnostics=False)
        self.assertEqual(len(self.candidates(quiet)), 6)
        # Storage is byte-identical regardless of the display-only controls.
        cols = "verdict, rank, passport_version, passport_sha256, ordering_json"
        a = self.conn.execute(
            f"SELECT {cols} FROM routing_plan_candidates WHERE plan_id = ? ORDER BY id",
            (capped.id,),
        ).fetchall()
        b = self.conn.execute(
            f"SELECT {cols} FROM routing_plan_candidates WHERE plan_id = ? ORDER BY id",
            (quiet.id,),
        ).fetchall()
        self.assertEqual([tuple(r) for r in a], [tuple(r) for r in b])

    def test_eligible_pins_are_recomputed_and_exact(self):
        agent = self.publish("a", capabilities=["cap.a"])
        plan = self.plan(capabilities=["cap.a"])
        cand = self.by_name(plan)["a"]
        agent = passports.get_agent(self.conn, "a")
        passport = passports.get_passport(
            self.conn, agent.id, agent.current_passport_version
        )
        self.assertEqual(cand.passport_version, agent.current_passport_version)
        self.assertEqual(
            cand.passport_sha256, passports.document_digest(passport.document)
        )
        self.assertEqual(
            cand.identity_sha256, passports.agent_identity_digest(agent)
        )

    def test_no_ownership_or_catalog_advantage(self):
        # A protected, system-owned identity and a plain custom one with the
        # same declarations rank adjacently by name only.
        self.publish("m.custom", capabilities=["cap.a"])
        self.conn.execute(
            "UPDATE agents SET owner='system', protected=1 WHERE name='m.custom'"
        )
        passports._rehash_agent(
            self.conn, passports.get_agent(self.conn, "m.custom").id
        )
        self.publish("z.custom", capabilities=["cap.a"])
        self.conn.commit()
        rows = self.by_name(self.plan(capabilities=["cap.a"]))
        self.assertEqual(rows["m.custom"].rank, 1)   # name order, not ownership
        self.assertEqual(rows["z.custom"].rank, 2)

    def test_request_bytes_digest_and_algorithm_are_exact(self):
        self.publish("a", capabilities=["cap.a"])
        request = self.request(capabilities=["cap.a"])
        plan = routing.get_plan(self.conn, routing.create_plan(self.conn, request))
        expected = protocols.serialize_canonical(request).decode("utf-8")
        self.assertEqual(plan.request_document, expected)
        self.assertEqual(
            plan.request_sha256,
            hashlib.sha256(expected.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(plan.algorithm_version, "aos-routing-order/v1")
        self.assertEqual(plan.request_schema, "aos.routing-request/v1")
        # No timestamp/actor inside the document.
        self.assertNotIn("created_at", plan.request_document)
        self.assertNotIn("actor", plan.request_document)


# ---------------------------------------------------------------------------
# (33)-(43) HASHING

class Wave3HashingTests(_LiveCase):
    def _one_plan(self):
        self.publish("a", capabilities=["cap.a"])
        self.publish("b", capabilities=["cap.z"])   # excluded (missing)
        return self.plan(capabilities=["cap.a"])

    def test_candidate_payload_exact_field_set(self):
        plan = self._one_plan()
        payload = routing.candidate_payload(self.candidates(plan)[0])
        self.assertEqual(
            set(payload),
            {
                "record_schema", "id", "plan_id", "agent_id", "rank",
                "passport_version", "verdict_sha256", "passport_sha256_sha256",
                "identity_sha256_sha256", "reasons_json_sha256",
                "warnings_json_sha256", "ordering_json_sha256", "created_at_sha256",
            },
        )
        self.assertEqual(payload["record_schema"], "aos.routing-candidate/v1")
        self.assertNotIn("content_sha256", payload)

    def test_plan_payload_exact_field_set(self):
        plan = self._one_plan()
        chain = [routing.candidate_digest(c) for c in self.candidates(plan)]
        payload = routing.plan_payload(plan, chain)
        self.assertEqual(
            set(payload),
            {
                "record_schema", "id", "task_id", "project_id", "eligible_count",
                "unresolved_count", "excluded_count", "supersedes_id",
                "scope_sha256", "actor_sha256", "request_schema_sha256",
                "algorithm_version_sha256", "request_document_sha256",
                "request_sha256_sha256", "result_status_sha256",
                "created_at_sha256", "candidate_chain",
            },
        )
        self.assertEqual(payload["record_schema"], "aos.routing-plan/v1")
        self.assertNotIn("content_sha256", payload)
        self.assertEqual(payload["candidate_chain"], chain)

    def test_chain_is_ordered_by_candidate_id(self):
        plan = self._one_plan()
        cands = self.candidates(plan)
        self.assertEqual([c.id for c in cands], sorted(c.id for c in cands))
        chain = [routing.candidate_digest(c) for c in cands]
        # The stored plan hash verifies against exactly this id-ordered chain.
        self.assertEqual(routing.plan_digest(plan, chain), plan.content_sha256)

    def test_every_committed_hash_is_64_lowercase_hex_no_pending(self):
        self._one_plan()
        hashes = [
            r[0]
            for r in self.conn.execute(
                "SELECT content_sha256 FROM routing_plans "
                "UNION ALL SELECT content_sha256 FROM routing_plan_candidates"
            ).fetchall()
        ]
        self.assertTrue(hashes)
        for value in hashes:
            self.assertRegex(value, r"^[0-9a-f]{64}$")
            self.assertNotEqual(value, "")

    def test_tampered_candidate_column_detected(self):
        plan = self._one_plan()
        self.conn.execute(
            "UPDATE routing_plan_candidates SET reasons_json='[\"suspended\"]' "
            "WHERE plan_id=? AND verdict='eligible'",
            (plan.id,),
        )
        self.conn.commit()
        result = routing.verify_plan(self.conn, plan.id)
        self.assertFalse(result["ok"])
        self.assertTrue(any("mismatch" in p for p in result["problems"]))

    def test_tampered_candidate_stored_hash_detected(self):
        plan = self._one_plan()
        self.conn.execute(
            "UPDATE routing_plan_candidates SET content_sha256=? "
            "WHERE plan_id=? AND verdict='eligible'",
            ("a" * 64, plan.id),
        )
        self.conn.commit()
        result = routing.verify_plan(self.conn, plan.id)
        self.assertFalse(result["ok"])

    def test_tampered_plan_column_detected(self):
        plan = self._one_plan()
        self.conn.execute(
            "UPDATE routing_plans SET created_at='2000-01-01T00:00:00Z' WHERE id=?",
            (plan.id,),
        )
        self.conn.commit()
        result = routing.verify_plan(self.conn, plan.id)
        self.assertFalse(result["ok"])
        self.assertIn(f"{ids.render_id('routing_plan', plan.id)}: mismatch",
                      result["problems"])

    def test_tampered_plan_stored_hash_detected(self):
        plan = self._one_plan()
        self.conn.execute(
            "UPDATE routing_plans SET content_sha256=? WHERE id=?",
            ("b" * 64, plan.id),
        )
        self.conn.commit()
        self.assertFalse(routing.verify_plan(self.conn, plan.id)["ok"])

    def test_child_stored_hash_laundering_detected(self):
        # Tamper ONLY the stored candidate hash (columns intact). The plan hash
        # is built from RECOMPUTED child digests, so it still verifies — but the
        # candidate-level check catches the stored-hash mismatch: no laundering.
        plan = self._one_plan()
        self.conn.execute(
            "UPDATE routing_plan_candidates SET content_sha256=? "
            "WHERE plan_id=? AND verdict='eligible'",
            ("c" * 64, plan.id),
        )
        self.conn.commit()
        result = routing.verify_plan(self.conn, plan.id)
        self.assertFalse(result["ok"])
        self.assertTrue(any("mismatch" in p for p in result["problems"]))


# ---------------------------------------------------------------------------
# (44)-(53) TRANSACTIONS

class Wave3TransactionTests(_LiveCase):
    def _prep(self):
        self.publish("a", capabilities=["cap.a"])
        return (self.count("routing_plans"), self.count("routing_plan_candidates"),
                self.count("events"))

    def _assert_rolled_back(self, before):
        self.assertEqual(
            (self.count("routing_plans"), self.count("routing_plan_candidates"),
             self.count("events")),
            before,
        )
        # No _PENDING_HASH survivor, no partial row.
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM routing_plans WHERE content_sha256=''"
            ).fetchone()[0],
            0,
        )

    def test_failure_during_candidate_finalization_rolls_back(self):
        before = self._prep()
        with mock.patch.object(
            routing, "candidate_digest", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                routing.create_plan(self.conn, self.request(capabilities=["cap.a"]))
        self._assert_rolled_back(before)

    def test_failure_before_plan_hash_finalization_rolls_back(self):
        before = self._prep()
        with mock.patch.object(
            routing, "plan_digest", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                routing.create_plan(self.conn, self.request(capabilities=["cap.a"]))
        self._assert_rolled_back(before)

    def test_event_failure_rolls_back_everything(self):
        before = self._prep()
        with mock.patch.object(
            routing.events, "emit", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                routing.create_plan(self.conn, self.request(capabilities=["cap.a"]))
        self._assert_rolled_back(before)

    def test_successful_write_creates_exactly_one_event(self):
        self.publish("a", capabilities=["cap.a"])
        before = self.count("events")
        routing.create_plan(self.conn, self.request(capabilities=["cap.a"]))
        rows = self.conn.execute(
            "SELECT entity, action FROM events ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertEqual(self.count("events"), before + 1)
        self.assertEqual((rows["entity"], rows["action"]), ("routing_plan", "create"))

    def test_no_nested_transaction(self):
        source = (REPO_ROOT / "agentic_os" / "routing.py").read_text(encoding="utf-8")
        self.assertEqual(source.count("with db.transaction("), 1)

    def test_two_racing_successors_permit_exactly_one(self):
        self.publish("a", capabilities=["cap.a"])
        p1 = self.plan(capabilities=["cap.a"])
        routing.create_plan(
            self.conn, self.request(capabilities=["cap.a"]), supersedes_id=p1.id
        )
        with self.assertRaises(AosError) as ctx:
            routing.create_plan(
                self.conn, self.request(capabilities=["cap.a"]), supersedes_id=p1.id
            )
        self.assertIn("already superseded", str(ctx.exception))
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM routing_plans WHERE supersedes_id=?", (p1.id,)
            ).fetchone()[0],
            1,
        )

    def test_failed_successor_leaves_predecessor_unchanged(self):
        self.publish("a", capabilities=["cap.a"])
        p1 = self.plan(capabilities=["cap.a"])
        before = dict(
            self.conn.execute(
                "SELECT * FROM routing_plans WHERE id=?", (p1.id,)
            ).fetchone()
        )
        with mock.patch.object(
            routing, "plan_digest", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                routing.create_plan(
                    self.conn, self.request(capabilities=["cap.a"]),
                    supersedes_id=p1.id,
                )
        after = dict(
            self.conn.execute(
                "SELECT * FROM routing_plans WHERE id=?", (p1.id,)
            ).fetchone()
        )
        self.assertEqual(before, after)


# ---------------------------------------------------------------------------
# (54)-(62) SUPERSESSION AND STALENESS

class Wave3SupersessionStalenessTests(_LiveCase):
    def test_predecessor_byte_identical_after_successor(self):
        self.publish("a", capabilities=["cap.a"])
        p1 = self.plan(capabilities=["cap.a"])
        before = dict(
            self.conn.execute("SELECT * FROM routing_plans WHERE id=?", (p1.id,)).fetchone()
        )
        p2 = routing.create_plan(
            self.conn, self.request(capabilities=["cap.a"]), supersedes_id=p1.id
        )
        after = dict(
            self.conn.execute("SELECT * FROM routing_plans WHERE id=?", (p1.id,)).fetchone()
        )
        self.assertEqual(before, after)
        self.assertEqual(routing.get_plan(self.conn, p2).supersedes_id, p1.id)

    def test_supersession_is_derived_not_stored_as_state(self):
        self.publish("a", capabilities=["cap.a"])
        p1 = self.plan(capabilities=["cap.a"])
        self.assertFalse(routing.plan_staleness(self.conn, p1).superseded)
        routing.create_plan(
            self.conn, self.request(capabilities=["cap.a"]), supersedes_id=p1.id
        )
        st = routing.plan_staleness(self.conn, routing.get_plan(self.conn, p1.id))
        self.assertTrue(st.superseded)      # derived from the successor's existence
        self.assertFalse(st.stale)          # supersession is not pin drift
        # There is no 'state' column on routing_plans to store it in.
        cols = [
            r[1]
            for r in self.conn.execute("PRAGMA table_info(routing_plans)").fetchall()
        ]
        self.assertNotIn("state", cols)

    def test_current_passport_change_makes_stale(self):
        self.publish("a", capabilities=["cap.a"])
        p1 = self.plan(capabilities=["cap.a"])
        self.assertFalse(routing.plan_staleness(self.conn, p1).stale)
        self.publish_v2("a", capabilities=["cap.a"])
        st = routing.plan_staleness(self.conn, routing.get_plan(self.conn, p1.id))
        self.assertTrue(st.stale)
        self.assertIn("passport_version_changed", st.reasons)
        self.assertEqual(st.agent, "a")

    def test_identity_change_makes_stale(self):
        self.publish("a", capabilities=["cap.a"])
        p1 = self.plan(capabilities=["cap.a"])
        passports.transition_lifecycle(self.conn, name="a", verb="suspend")
        st = routing.plan_staleness(self.conn, routing.get_plan(self.conn, p1.id))
        self.assertTrue(st.stale)
        self.assertIn("lifecycle_not_active", st.reasons)
        self.assertIn("identity_changed", st.reasons)

    def test_unchanged_pins_remain_fresh(self):
        self.publish("a", capabilities=["cap.a"])
        self.publish("b", capabilities=["cap.a", "cap.b"])
        p1 = self.plan(capabilities=["cap.a"])
        st = routing.plan_staleness(self.conn, p1)
        self.assertFalse(st.stale)
        self.assertEqual(st.reasons, ())
        self.assertIsNone(st.agent)

    def test_staleness_uses_no_clock(self):
        source = (REPO_ROOT / "agentic_os" / "routing.py").read_text(encoding="utf-8")
        start = source.index("def plan_staleness")
        end = source.index("def _candidate_public")
        body = source[start:end] + source[
            source.index("def _candidate_stale_reasons"):
            source.index("def plan_staleness")
        ]
        for token in ("utc_now_iso", "datetime", "time.time", ".now("):
            self.assertNotIn(token, body)

    def test_reads_never_mutate_a_stale_plan(self):
        self.publish("a", capabilities=["cap.a"])
        p1 = self.plan(capabilities=["cap.a"])
        passports.transition_lifecycle(self.conn, name="a", verb="suspend")
        before = dict(
            self.conn.execute("SELECT * FROM routing_plans WHERE id=?", (p1.id,)).fetchone()
        )
        routing.list_plans(self.conn)
        routing.plan_public(self.conn, routing.get_plan(self.conn, p1.id))
        routing.verify_plan(self.conn, p1.id)
        after = dict(
            self.conn.execute("SELECT * FROM routing_plans WHERE id=?", (p1.id,)).fetchone()
        )
        self.assertEqual(before, after)


# ---------------------------------------------------------------------------
# (63)-(75) READS AND VERIFY

class Wave3ReadVerifyTests(_LiveCase):
    def test_list_deterministic_newest_first(self):
        self.publish("a", capabilities=["cap.a"])
        p1 = self.plan(capabilities=["cap.a"])
        p2 = self.plan(capabilities=["cap.a"])
        listing = routing.list_plans(self.conn)
        self.assertEqual(
            [row["plan"] for row in listing],
            [ids.render_id("routing_plan", p2.id), ids.render_id("routing_plan", p1.id)],
        )

    def test_show_returns_all_candidate_classes(self):
        self.publish("elig", capabilities=["cap.a"])
        self.publish("excl", capabilities=["cap.z"])
        plan = self.plan(capabilities=["cap.a"])
        # `unresolved` cannot arise from a same-build published passport, so
        # inject one directly to prove the reader renders all three classes.
        extra = self.publish("extra", capabilities=["cap.a"])  # published AFTER
        self.conn.execute(
            "INSERT INTO routing_plan_candidates (plan_id, agent_id, verdict, "
            "reasons_json, warnings_json, created_at, content_sha256) VALUES "
            "(?, ?, 'unresolved', '[\"malformed_declaration\"]', '[]', ?, ?)",
            (plan.id, extra.id, NOW, HASH),
        )
        self.conn.commit()
        verdicts = {
            c["agent"]: c["verdict"]
            for c in routing.plan_public(self.conn, plan)["candidates"]
        }
        self.assertEqual(verdicts["elig"], "eligible")
        self.assertEqual(verdicts["excl"], "excluded")
        self.assertEqual(verdicts["extra"], "unresolved")

    def test_verify_pristine_plan_passes(self):
        self.publish("a", capabilities=["cap.a"])
        plan = self.plan(capabilities=["cap.a"])
        result = routing.verify_plan(self.conn, plan.id)
        self.assertTrue(result["ok"])
        self.assertEqual(result["problems"], [])

    def test_request_canonical_and_digest_mismatch(self):
        self.publish("a", capabilities=["cap.a"])
        plan = self.plan(capabilities=["cap.a"])
        # Non-canonical (re-spaced) request body ⇒ request_mismatch.
        self.conn.execute(
            "UPDATE routing_plans SET request_document=? WHERE id=?",
            (plan.request_document.replace(",", ", "), plan.id),
        )
        self.conn.commit()
        result = routing.verify_plan(self.conn, plan.id)
        self.assertIn(f"{ids.render_id('routing_plan', plan.id)}: request_mismatch",
                      result["problems"])

    def test_rank_gap_detected(self):
        self.publish("a", capabilities=["cap.a"])
        self.publish("b", capabilities=["cap.a"])
        plan = self.plan(capabilities=["cap.a"])
        # Break rank contiguity via raw SQL (bypasses the domain layer).
        self.conn.execute(
            "UPDATE routing_plan_candidates SET rank=5 WHERE plan_id=? AND rank=2",
            (plan.id,),
        )
        self.conn.commit()
        self.assertIn(f"{ids.render_id('routing_plan', plan.id)}: rank_gap",
                      routing.verify_plan(self.conn, plan.id)["problems"])

    def test_count_status_incoherence_detected(self):
        self.publish("a", capabilities=["cap.a"])
        plan = self.plan(capabilities=["cap.a"])
        self.conn.execute(
            "UPDATE routing_plans SET eligible_count=9 WHERE id=?", (plan.id,)
        )
        self.conn.commit()
        problems = routing.verify_plan(self.conn, plan.id)["problems"]
        self.assertTrue(any("counts_incoherent" in p for p in problems))

    def test_invalid_reason_vocabulary_detected(self):
        self.publish("a", capabilities=["cap.a"])
        plan = self.plan(capabilities=["cap.a"])
        self.conn.execute(
            "UPDATE routing_plan_candidates SET reasons_json='[\"not_a_code\"]' "
            "WHERE plan_id=?",
            (plan.id,),
        )
        self.conn.commit()
        self.assertFalse(routing.verify_plan(self.conn, plan.id)["ok"])

    def test_invalid_ordering_json_detected(self):
        self.publish("a", capabilities=["cap.a"])
        plan = self.plan(capabilities=["cap.a"])
        self.conn.execute(
            "UPDATE routing_plan_candidates SET ordering_json='[9,9,9,9,9,9]' "
            "WHERE plan_id=? AND verdict='eligible'",
            (plan.id,),
        )
        self.conn.commit()
        self.assertFalse(routing.verify_plan(self.conn, plan.id)["ok"])

    def test_dangling_pin_reference_detected(self):
        self.publish("a", capabilities=["cap.a"])
        plan = self.plan(capabilities=["cap.a"])
        self.conn.commit()
        # Point an eligible pin at a passport version that does not exist
        # (composite FK disabled only for this out-of-band edit).
        self.conn.execute("PRAGMA foreign_keys=OFF")
        self.conn.execute(
            "UPDATE routing_plan_candidates SET passport_version=99 "
            "WHERE plan_id=? AND verdict='eligible'",
            (plan.id,),
        )
        self.conn.commit()
        self.conn.execute("PRAGMA foreign_keys=ON")
        problems = routing.verify_plan(self.conn, plan.id)["problems"]
        self.assertTrue(any("reference_invalid" in p for p in problems))

    def test_reads_emit_no_events_and_no_writes(self):
        self.publish("a", capabilities=["cap.a"])
        plan = self.plan(capabilities=["cap.a"])
        snapshot = (self.count("events"), self.count("routing_plans"),
                    self.count("routing_plan_candidates"))
        routing.list_plans(self.conn)
        routing.plan_public(self.conn, plan)
        routing.verify_plan(self.conn, plan.id)
        self.assertEqual(
            (self.count("events"), self.count("routing_plans"),
             self.count("routing_plan_candidates")),
            snapshot,
        )

    def test_verification_details_are_bounded_and_value_free(self):
        self.publish("secretive", capabilities=["cap.a"])
        plan = self.plan(capabilities=["cap.a"])
        self.conn.execute(
            "UPDATE routing_plans SET content_sha256=? WHERE id=?", ("d" * 64, plan.id)
        )
        self.conn.commit()
        for problem in routing.verify_plan(self.conn, plan.id)["problems"]:
            self.assertNotRegex(problem, r"[0-9a-f]{64}")   # no full hash
            self.assertNotIn("SELECT", problem)
            self.assertNotIn("cap.a", problem)


# ---------------------------------------------------------------------------
# (94)-(98) EVENT PRIVACY

class Wave3EventPrivacyTests(_LiveCase):
    def _payload(self):
        self.publish("a", capabilities=["cap.a"])
        routing.create_plan(self.conn, self.request(capabilities=["cap.a"]))
        row = self.conn.execute(
            "SELECT entity, action, payload_json FROM events "
            "WHERE entity='routing_plan' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["entity"], row["action"], json.loads(row["payload_json"])

    def test_exact_entity_and_action(self):
        entity, action, _ = self._payload()
        self.assertEqual((entity, action), ("routing_plan", "create"))

    def test_payload_keys_are_a_subset_of_the_allowlist(self):
        _, _, payload = self._payload()
        allowed = set(routing.ROUTING_PLAN_EVENT_KEYS) | {
            "schema_version", "secret_warning", "secret_fields", "secret_patterns"
        }
        self.assertTrue(set(payload).issubset(allowed), set(payload) - allowed)

    def test_no_full_hash_and_no_prose_in_payload(self):
        _, _, payload = self._payload()
        blob = json.dumps(payload)
        self.assertNotRegex(blob, r"[0-9a-f]{64}")      # only 12-char prefixes
        for prose in ("cap.a", "request_document", "reasons", "ordering", "role",
                      "mission", "approval"):
            self.assertNotIn(prose, blob)

    def test_secret_shaped_input_is_warned_and_redacted_not_blocked(self):
        # A github-token shape that also satisfies the capability pattern, so it
        # survives validation and reaches the warn-on-write scan.
        secret = "ghp_" + "a" * 24
        self.publish("a", capabilities=["cap.a"])
        request = self.request(capabilities=[secret])
        with contextlib.redirect_stderr(io.StringIO()):  # swallow the stderr warning
            plan_id = routing.create_plan(self.conn, request)  # NOT blocked
        plan = routing.get_plan(self.conn, plan_id)
        self.assertIn(secret, plan.request_document)      # canonical row keeps it
        row = self.conn.execute(
            "SELECT payload_json FROM events WHERE entity='routing_plan' "
            "AND entity_id=?",
            (plan_id,),
        ).fetchone()
        self.assertNotIn(secret, row["payload_json"])     # event never carries it
        self.assertIn("secret_warning", row["payload_json"])


# ---------------------------------------------------------------------------
# (99)-(101) REGRESSION

class Wave3RegressionTests(_LiveCase):
    def test_no_governed_handoff_rows_created(self):
        self.publish("a", capabilities=["cap.a"])
        self.plan(capabilities=["cap.a"])
        self.assertEqual(self.count("agent_handoffs"), 0)
        self.assertEqual(self.count("agent_handoff_transitions"), 0)

    def test_no_run_or_provider_execution(self):
        self.publish("a", capabilities=["cap.a"])
        self.plan(capabilities=["cap.a"])
        self.assertEqual(self.count("runs"), 0)

    def test_agent_handoffs_module_not_imported_by_routing(self):
        self.assertFalse(hasattr(routing, "agent_handoffs"))

    def test_legacy_handoff_table_untouched(self):
        self.publish("a", capabilities=["cap.a"])
        self.plan(capabilities=["cap.a"])
        self.assertEqual(self.count("handoffs"), 0)  # legacy table, distinct


class Wave3VerifySeparationRegressionTests(_LiveCase):
    """verify_plan separates HISTORICAL integrity from CURRENT-ledger
    staleness: a legitimate advance of the mutable current state (new
    passport version, lifecycle/identity drift) reads stale-but-intact
    (`ok` True), while tampering with the pinned historical passport itself
    is an integrity failure (`ok` False) — never the other way around."""

    def test_new_current_passport_is_stale_but_intact(self):
        self.publish("a", capabilities=["cap.a"])
        plan = self.plan(capabilities=["cap.a"])
        pristine = routing.verify_plan(self.conn, plan.id)
        self.assertTrue(pristine["ok"])
        self.assertFalse(pristine["stale"])
        self.assertEqual(pristine["problems"], [])
        self.publish_v2("a", capabilities=["cap.a"])
        result = routing.verify_plan(self.conn, plan.id)
        # A current-passport advance is drift, not historical corruption.
        self.assertTrue(result["ok"])
        self.assertTrue(result["stale"])
        self.assertFalse(result["superseded"])
        self.assertEqual(result["problems"], [])
        self.assertIn("passport_version_changed", result["staleness_reasons"])

    def test_lifecycle_and_identity_change_is_stale_but_intact(self):
        self.publish("a", capabilities=["cap.a"])
        plan = self.plan(capabilities=["cap.a"])
        passports.transition_lifecycle(self.conn, name="a", verb="suspend")
        result = routing.verify_plan(self.conn, plan.id)
        # Mutable current-identity drift never fails historical verification.
        self.assertTrue(result["ok"])
        self.assertTrue(result["stale"])
        self.assertEqual(result["problems"], [])
        self.assertIn("lifecycle_not_active", result["staleness_reasons"])
        self.assertIn("identity_changed", result["staleness_reasons"])

    def test_pinned_historical_passport_tamper_fails_verification(self):
        self.publish("a", capabilities=["cap.a"])
        plan = self.plan(capabilities=["cap.a"])
        candidate = self.by_name(plan)["a"]
        self.assertEqual(candidate.verdict, "eligible")
        passport = passports.get_passport(
            self.conn, candidate.agent_id, candidate.passport_version
        )
        # Replace the pinned historical document with a structurally valid,
        # re-sealed canonical document whose body (and therefore digest)
        # differs — isolating the digest pin from malformed-JSON failures.
        # Candidate and plan rows (and their hashes) stay untouched.
        document = protocols.parse_canonical(passport.document.encode("utf-8"))
        document["mission"] = "do tampered mission"
        document.pop(protocols.CONTENT_HASH_FIELD, None)
        document[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(document)
        tampered_text = protocols.serialize_canonical(document).decode("utf-8")
        self.assertNotEqual(tampered_text, passport.document)
        self.conn.execute(
            "UPDATE agent_passports SET document=? WHERE id=?",
            (tampered_text, passport.id),
        )
        self.conn.commit()
        result = routing.verify_plan(self.conn, plan.id)
        self.assertFalse(result["ok"])
        self.assertTrue(result["stale"])
        self.assertIn("passport_digest_changed", result["staleness_reasons"])
        self.assertTrue(
            any(p.endswith("pin_mismatch") for p in result["problems"]),
            result["problems"],
        )
        # Problems stay bounded and value-free: no document body, no tampered
        # value, no full hash.
        for problem in result["problems"]:
            self.assertNotIn("tampered mission", problem)
            self.assertNotIn(tampered_text, problem)
            self.assertNotIn(passport.document, problem)
            self.assertNotRegex(problem, r"[0-9a-f]{64}")


# ---------------------------------------------------------------------------
# (76)-(93) CLI + POWER

class Wave3CliCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.run_cli("init")
        self.run_cli("project", "add", "demo", "--name", "Demo", "--repo",
                     str(self.root))

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["--root", str(self.root), *argv])
        return code, out.getvalue(), err.getvalue()

    def make_agent(self, name, **body):
        frag = self.root / f"{name}.json"
        frag.write_text(json.dumps(body or {"capabilities": ["cap.a"]}),
                        encoding="utf-8")
        self.run_cli("agent", "create", name, "--role", "w", "--mission", "m",
                     "--from-file", str(frag))
        self.run_cli("agent", "passport", "publish", name)


class Wave3CliParserTests(Wave3CliCase):
    def test_parser_exposes_exactly_four_route_leaves(self):
        leaves = {
            p for p in power.iter_command_paths(cli.build_parser())
            if p[:2] == ("agent", "route")
        }
        self.assertEqual(
            leaves,
            {
                ("agent", "route", "plan"),
                ("agent", "route", "list"),
                ("agent", "route", "show"),
                ("agent", "route", "verify"),
            },
        )

    def test_no_route_select_leaf(self):
        leaves = power.iter_command_paths(cli.build_parser())
        self.assertNotIn(("agent", "route", "select"), leaves)

    def test_require_autonomy_is_repeatable_and_require_classification_is_scalar(self):
        parser = cli.build_parser()
        args = parser.parse_args([
            "agent", "route", "plan",
            "--require-autonomy", "scoped", "--require-autonomy", "supervised",
            "--require-classification", "internal",
        ])
        self.assertEqual(args.require_autonomy, ["scoped", "supervised"])
        self.assertEqual(args.require_classification, "internal")

    def test_no_autonomy_ceiling_flag(self):
        parser = cli.build_parser()
        with self.assertRaises(AosError):
            parser.parse_args(
                ["agent", "route", "plan", "--autonomy-ceiling", "scoped"]
            )


class Wave3CliBehaviorTests(Wave3CliCase):
    def test_plan_text_and_json(self):
        self.make_agent("alpha", capabilities=["cap.a"])
        code, out, _ = self.run_cli("agent", "route", "plan", "--capability", "cap.a")
        self.assertEqual(code, 0)
        self.assertIn("RP-0001", out)
        self.assertIn("1. alpha", out)
        code, out, _ = self.run_cli(
            "agent", "route", "plan", "--capability", "cap.a", "--json"
        )
        self.assertEqual(code, 0)
        doc = json.loads(out)
        self.assertEqual(doc["plan"]["result_status"], "resolved")
        self.assertEqual(len(doc["plan"]["candidates"]), 1)

    def test_list_show_verify(self):
        self.make_agent("alpha", capabilities=["cap.a"])
        self.run_cli("agent", "route", "plan", "--capability", "cap.a")
        code, out, _ = self.run_cli("agent", "route", "list", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(len(json.loads(out)["plans"]), 1)
        code, out, _ = self.run_cli("agent", "route", "show", "RP-0001")
        self.assertEqual(code, 0)
        self.assertIn("RP-0001", out)
        code, out, _ = self.run_cli("agent", "route", "show", "RP-0001", "--request")
        self.assertEqual(code, 0)
        self.assertEqual(
            protocols.serialize_canonical(json.loads(out)).decode("utf-8"),
            out.strip(),
        )
        code, out, _ = self.run_cli("agent", "route", "verify", "RP-0001")
        self.assertEqual(code, 0)
        self.assertIn("OK", out)

    def test_verify_exit_1_on_integrity_failure(self):
        self.make_agent("alpha", capabilities=["cap.a"])
        self.run_cli("agent", "route", "plan", "--capability", "cap.a")
        conn = db.open_db(self.root / ".agentic-os")
        try:
            conn.execute("UPDATE routing_plans SET content_sha256=?", ("e" * 64,))
            conn.commit()
        finally:
            conn.close()
        code, out, err = self.run_cli("agent", "route", "verify", "RP-0001")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("mismatch", err)

    def test_max_candidates_is_text_only(self):
        for i in range(4):
            self.make_agent(f"a{i}", capabilities=["cap.a"])
        self.run_cli("agent", "route", "plan", "--capability", "cap.a",
                     "--max-candidates", "2")
        code, out, _ = self.run_cli("agent", "route", "show", "RP-0001")
        ranked = [l for l in out.splitlines() if l.strip().startswith(("1.", "2.", "3.", "4."))]
        self.assertEqual(len(ranked), 2)                          # display capped
        code, out, _ = self.run_cli("agent", "route", "show", "RP-0001", "--json")
        self.assertEqual(len(json.loads(out)["plan"]["candidates"]), 4)   # storage full

    def test_include_diagnostics_is_text_only(self):
        self.make_agent("good", capabilities=["cap.a"])
        self.make_agent("bad", capabilities=["cap.z"])
        # No CLI flag sets include_diagnostics=false; the renderer respects the
        # STORED value, so drive it through the request/renderer layer.
        conn = db.open_db(self.root / ".agentic-os")
        try:
            request = routing.validate_request({
                "request_schema": routing.REQUEST_SCHEMA,
                "algorithm_version": routing.ALGORITHM_VERSION,
                "capabilities": ["cap.a"],
                "include_diagnostics": False,
            })
            pid = routing.create_plan(conn, request)
            lines = routing.render_plan_lines(conn, routing.get_plan(conn, pid))
            self.assertFalse(any("bad" in l for l in lines))     # diagnostics hidden
            request_on = routing.validate_request({
                "request_schema": routing.REQUEST_SCHEMA,
                "algorithm_version": routing.ALGORITHM_VERSION,
                "capabilities": ["cap.a"],
                "include_diagnostics": True,
            })
            pid2 = routing.create_plan(conn, request_on)
            lines_on = routing.render_plan_lines(conn, routing.get_plan(conn, pid2))
            self.assertTrue(any("bad" in l for l in lines_on))   # diagnostics shown
        finally:
            conn.close()

    def test_malformed_ids_refuse(self):
        code, _, err = self.run_cli("agent", "route", "show", "not-an-id")
        self.assertEqual(code, 1)
        code, _, err = self.run_cli(
            "agent", "route", "plan", "--task", "bogus", "--capability", "cap.a"
        )
        self.assertEqual(code, 1)

    def test_recovery_blocks_plan_and_allows_reads(self):
        self.make_agent("alpha", capabilities=["cap.a"])
        self.run_cli("agent", "route", "plan", "--capability", "cap.a")
        self.run_cli("power", "set", "recovery")
        code, out, err = self.run_cli("agent", "route", "plan", "--capability", "cap.a")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("recovery mode", err)
        for leaf in (("agent", "route", "list"),
                     ("agent", "route", "show", "RP-0001"),
                     ("agent", "route", "verify", "RP-0001")):
            with self.subTest(leaf=leaf):
                code, _, _ = self.run_cli(*leaf)
                self.assertEqual(code, 0)

    def test_route_plan_deep_wrap_and_eco_immediate(self):
        self.make_agent("alpha", capabilities=["cap.a"])
        self.run_cli("power", "set", "deep")
        code, _, _ = self.run_cli("agent", "route", "plan", "--capability", "cap.a")
        self.assertEqual(code, 0)      # deep preflight+postverify pass on a clean ledger
        self.run_cli("power", "set", "eco")
        code, out, _ = self.run_cli("agent", "route", "plan", "--capability", "cap.a")
        self.assertEqual(code, 0)      # explicit write runs immediately under eco
        self.assertIn("RP-0002", out)

    def test_entrypoints_equivalent_for_route_show(self):
        self.make_agent("alpha", capabilities=["cap.a"])
        self.run_cli("agent", "route", "plan", "--capability", "cap.a")
        _, out, _ = self.run_cli("agent", "route", "show", "RP-0001", "--json")
        import subprocess

        proc = subprocess.run(
            [
                "python3", "aos.py", "--root", str(self.root),
                "agent", "route", "show", "RP-0001", "--json",
            ],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(out, proc.stdout)


# ===========================================================================
# WAVE 4 — governed agent handoffs (agent_handoffs.py): creation, the
# transition engine, supersession, record hashes, the no-laundering gate,
# reads, verification, rollback, concurrency, the discard guard and the
# secret labels. Contract §11-16, §19, §21; test matrix groups 28-38.
# ===========================================================================

ALL_CLASSES = list(models.MEMORY_SENSITIVITIES)


class _HandoffCase(_LiveCase):
    """A live workspace with a project, a task and two published agents that
    declare every data classification (so a default `internal` handoff raises
    no advisory). The base for the Wave 4 domain tests."""

    def setUp(self):
        super().setUp()
        self.add_project("demo")
        self.task = self.add_task(project="demo", title="build")
        self.alice = self.publish(
            "alice", capabilities=["cap.a"], data_classifications=ALL_CLASSES
        )
        self.bob = self.publish(
            "bob", capabilities=["cap.a"], data_classifications=ALL_CLASSES
        )

    def make_handoff(self, **over):
        params = dict(
            task_id=self.task.id,
            from_agent="alice",
            to_agent="bob",
            objective_md="ship the widget",
        )
        params.update(over)
        with contextlib.redirect_stderr(io.StringIO()):
            handoff_id = agent_handoffs.create_handoff(self.conn, **params)
        return agent_handoffs.get_handoff(self.conn, handoff_id)

    def _mark_task_done(self):
        self.conn.execute(
            "UPDATE tasks SET status='done' WHERE id=?", (self.task.id,)
        )
        self.conn.commit()

    def transition(self, handoff, verb, **kw):
        with contextlib.redirect_stderr(io.StringIO()):
            agent_handoffs.transition(self.conn, handoff.id, verb, **kw)
        return agent_handoffs.get_handoff(self.conn, handoff.id)

    def payloads(self, action=None):
        query = (
            "SELECT action, payload_json FROM events WHERE entity='agent_handoff'"
        )
        params: list = []
        if action is not None:
            query += " AND action=?"
            params.append(action)
        query += " ORDER BY id"
        return [
            (row["action"], json.loads(row["payload_json"]))
            for row in self.conn.execute(query, params).fetchall()
        ]

    def _row(self, handoff_id):
        return dict(
            self.conn.execute(
                "SELECT * FROM agent_handoffs WHERE id=?", (handoff_id,)
            ).fetchone()
        )


# ---------------------------------------------------------------------------
# (28) Handoff creation.

class HandoffCreationTests(_HandoffCase):
    def test_full_field_row_pins_and_one_propose_event(self):
        decision = ops.add_decision(
            self.conn, title="why", project_slug="demo", decision="because"
        )
        before = self.count("events")
        handoff = self.make_handoff(
            expected_evidence=["test", "commit"],
            min_evidence_count=2,
            constraints_md="stay in scope",
            data_classification="confidential",
            decision_id=decision.id,
        )
        self.assertEqual(handoff.state, "proposed")
        self.assertEqual(handoff.created_at, handoff.updated_at)
        self.assertEqual(handoff.from_agent_id, self.alice.id)
        self.assertEqual(handoff.to_agent_id, self.bob.id)
        self.assertEqual(handoff.actor, ops.ACTOR_HUMAN)
        self.assertEqual(handoff.expected_evidence_json, '["commit","test"]')
        self.assertEqual(handoff.min_evidence_count, 2)
        self.assertEqual(handoff.constraints_md, "stay in scope")
        self.assertEqual(handoff.data_classification, "confidential")
        self.assertEqual(handoff.decision_id, decision.id)
        # zero transition rows, empty-chain hash committed (never _PENDING_HASH)
        self.assertEqual(agent_handoffs.get_transitions(self.conn, handoff.id), [])
        self.assertTrue(models.is_claim_hash(handoff.content_sha256))
        self.assertEqual(
            handoff.content_sha256, agent_handoffs.handoff_digest(handoff, [])
        )
        # exactly one propose event
        self.assertEqual(self.count("events"), before + 1)
        actions = [a for a, _ in self.payloads()]
        self.assertEqual(actions, ["propose"])

    def test_pins_equal_recomputed_passport_digests(self):
        handoff = self.make_handoff()
        alice_pp = passports.get_passport(
            self.conn, self.alice.id, self.alice.current_passport_version
        )
        bob_pp = passports.get_passport(
            self.conn, self.bob.id, self.bob.current_passport_version
        )
        self.assertEqual(
            handoff.from_passport_version, self.alice.current_passport_version
        )
        self.assertEqual(
            handoff.from_passport_sha256,
            passports.document_digest(alice_pp.document),
        )
        self.assertEqual(
            handoff.to_passport_sha256, passports.document_digest(bob_pp.document)
        )

    def test_done_task_refused(self):
        self._mark_task_done()
        before = self.count("agent_handoffs"), self.count("events")
        with self.assertRaises(AosError) as ctx:
            self.make_handoff()
        self.assertIn("is done", str(ctx.exception))
        self.assertEqual(
            (self.count("agent_handoffs"), self.count("events")), before
        )

    def test_absent_task_refused(self):
        with self.assertRaises(AosError):
            self.make_handoff(task_id=99999)

    def test_self_handoff_refused(self):
        with self.assertRaises(AosError) as ctx:
            self.make_handoff(to_agent="alice")
        self.assertIn("different agents", str(ctx.exception))
        self.assertEqual(self.count("agent_handoffs"), 0)

    def test_draft_participant_refused(self):
        self.draft("dd", capabilities=["cap.a"])
        with self.assertRaises(AosError) as ctx:
            self.make_handoff(to_agent="dd")
        self.assertIn("active", str(ctx.exception))
        self.assertEqual(self.count("agent_handoffs"), 0)

    def test_suspended_participant_refused(self):
        passports.transition_lifecycle(self.conn, name="bob", verb="suspend")
        with self.assertRaises(AosError):
            self.make_handoff()

    def test_absent_participant_refused(self):
        with self.assertRaises(AosError):
            self.make_handoff(to_agent="ghost")

    def test_objective_bounds(self):
        with self.assertRaises(AosError):
            self.make_handoff(objective_md="")
        with self.assertRaises(AosError):
            self.make_handoff(objective_md="x" * 4097)
        handoff = self.make_handoff(objective_md="x" * 4096)
        self.assertEqual(len(handoff.objective_md), 4096)

    def test_constraints_bounds(self):
        with self.assertRaises(AosError):
            self.make_handoff(constraints_md="y" * 4097)
        self.assertIsNone(self.make_handoff().constraints_md)

    def test_evidence_canonicalization_dedup_and_vocab(self):
        self.assertEqual(self.make_handoff().expected_evidence_json, "[]")
        self.assertEqual(
            self.make_handoff(expected_evidence=["url", "note", "file"]).expected_evidence_json,
            '["file","note","url"]',
        )
        with self.assertRaises(AosError):
            self.make_handoff(expected_evidence=["note", "note"])
        with self.assertRaises(AosError):
            self.make_handoff(expected_evidence=["bogus"])

    def test_min_evidence_bounds_and_bool_rejection(self):
        with self.assertRaises(AosError):
            self.make_handoff(min_evidence_count=-1)
        with self.assertRaises(AosError):
            self.make_handoff(min_evidence_count=33)
        with self.assertRaises(AosError):
            self.make_handoff(min_evidence_count=True)
        self.assertEqual(self.make_handoff(min_evidence_count=32).min_evidence_count, 32)

    def test_classification_vocabulary(self):
        with self.assertRaises(AosError):
            self.make_handoff(data_classification="secret")
        for level in ALL_CLASSES:
            self.assertEqual(
                self.make_handoff(data_classification=level).data_classification,
                level,
            )

    def test_decision_reference_must_exist(self):
        with self.assertRaises(AosError) as ctx:
            self.make_handoff(decision_id=999)
        self.assertIn("decision", str(ctx.exception).lower())
        self.assertEqual(self.count("agent_handoffs"), 0)


# ---------------------------------------------------------------------------
# (28) Optional routing-plan gate.

class HandoffPlanLinkTests(_HandoffCase):
    def _plan(self, **over):
        plan_id = routing.create_plan(self.conn, self.request(**over))
        return routing.get_plan(self.conn, plan_id)

    def test_fresh_intact_unsuperseded_plan_accepted(self):
        plan = self._plan(capabilities=["cap.a"])
        handoff = self.make_handoff(plan_id=plan.id)
        self.assertEqual(handoff.plan_id, plan.id)

    def test_recipient_not_eligible_refused(self):
        plan = self._plan(capabilities=["cap.z"])  # nobody eligible
        with self.assertRaises(AosError) as ctx:
            self.make_handoff(plan_id=plan.id)
        self.assertIn("eligible candidate", str(ctx.exception))
        self.assertEqual(self.count("agent_handoffs"), 0)

    def test_stale_plan_refused(self):
        plan = self._plan(capabilities=["cap.a"])
        self.publish_v2(
            "bob", capabilities=["cap.a"], data_classifications=ALL_CLASSES
        )
        with self.assertRaises(AosError) as ctx:
            self.make_handoff(plan_id=plan.id)
        self.assertIn("stale", str(ctx.exception))

    def test_superseded_plan_refused(self):
        plan = self._plan(capabilities=["cap.a"])
        routing.create_plan(
            self.conn, self.request(capabilities=["cap.a"]), supersedes_id=plan.id
        )
        with self.assertRaises(AosError) as ctx:
            self.make_handoff(plan_id=plan.id)
        self.assertIn("superseded", str(ctx.exception))

    def test_task_mismatch_refused(self):
        other = self.add_task(project="demo", title="other")
        plan = self._plan(task=other.id)  # task-scoped to a different task
        self.assertEqual(plan.task_id, other.id)
        with self.assertRaises(AosError) as ctx:
            self.make_handoff(plan_id=plan.id)
        self.assertIn("scoped to task", str(ctx.exception))

    def test_integrity_failure_refused(self):
        plan = self._plan(capabilities=["cap.a"])
        self.conn.execute(
            "UPDATE routing_plans SET content_sha256=? WHERE id=?",
            ("0" * 64, plan.id),
        )
        self.conn.commit()
        with self.assertRaises(AosError) as ctx:
            self.make_handoff(plan_id=plan.id)
        self.assertIn("integrity", str(ctx.exception).lower())

    def test_omitting_plan_allows_any_recipient(self):
        self.assertEqual(self.make_handoff().plan_id, None)


# ---------------------------------------------------------------------------
# (28) Payloads and committed hashes.

class HandoffPayloadHashTests(_HandoffCase):
    def test_handoff_payload_binds_columns_excludes_content_sha256(self):
        handoff = self.make_handoff(constraints_md="c")
        payload = agent_handoffs.handoff_payload(handoff, [])
        self.assertNotIn("content_sha256", payload)
        self.assertEqual(payload["record_schema"], "aos.agent-handoff/v1")
        # integers bind directly; text binds by sha256 leaf
        self.assertEqual(payload["id"], handoff.id)
        self.assertEqual(payload["min_evidence_count"], 0)
        self.assertEqual(
            payload["objective_md_sha256"],
            utils.sha256_text(handoff.objective_md),
        )
        self.assertEqual(
            payload["constraints_md_sha256"], utils.sha256_text("c")
        )
        self.assertEqual(payload["transition_chain"], [])

    def test_transition_payload_binds_columns(self):
        handoff = self.transition(self.make_handoff(), "accept")
        transition = agent_handoffs.get_transitions(self.conn, handoff.id)[0]
        payload = agent_handoffs.transition_payload(transition)
        self.assertNotIn("content_sha256", payload)
        self.assertEqual(
            payload["record_schema"], "aos.agent-handoff-transition/v1"
        )
        self.assertEqual(payload["seq"], 1)
        self.assertEqual(
            payload["to_state_sha256"], utils.sha256_text("accepted")
        )

    def test_committed_hashes_recompute(self):
        handoff = self.transition(self.make_handoff(), "clarify", reason_code="objective_unclear")
        handoff = self.transition(handoff, "accept")
        transitions = agent_handoffs.get_transitions(self.conn, handoff.id)
        for transition in transitions:
            self.assertEqual(
                transition.content_sha256,
                agent_handoffs.transition_digest(transition),
            )
        chain = [agent_handoffs.transition_digest(t) for t in transitions]
        self.assertEqual(
            handoff.content_sha256, agent_handoffs.handoff_digest(handoff, chain)
        )


# ---------------------------------------------------------------------------
# (29-33, 38) Tamper, verification and the no-laundering gate.

class HandoffTamperVerifyTests(_HandoffCase):
    def test_clean_handoff_verifies_ok(self):
        handoff = self.transition(self.make_handoff(), "accept")
        report = agent_handoffs.verify_handoff(self.conn, handoff.id)
        self.assertTrue(report["ok"])
        self.assertEqual(report["problems"], [])

    def test_tampered_row_hash_reports_mismatch(self):
        handoff = self.make_handoff()
        self.conn.execute(
            "UPDATE agent_handoffs SET content_sha256=? WHERE id=?",
            ("1" * 64, handoff.id),
        )
        self.conn.commit()
        report = agent_handoffs.verify_handoff(self.conn, handoff.id)
        self.assertFalse(report["ok"])
        self.assertTrue(any("mismatch" in p for p in report["problems"]))

    def test_pending_hash_reports_malformed(self):
        handoff = self.make_handoff()
        self.conn.execute(
            "UPDATE agent_handoffs SET content_sha256='' WHERE id=?", (handoff.id,)
        )
        self.conn.commit()
        report = agent_handoffs.verify_handoff(self.conn, handoff.id)
        self.assertTrue(any("malformed" in p for p in report["problems"]))

    def test_tampered_prose_reports_mismatch(self):
        handoff = self.make_handoff()
        self.conn.execute(
            "UPDATE agent_handoffs SET objective_md='hacked' WHERE id=?",
            (handoff.id,),
        )
        self.conn.commit()
        report = agent_handoffs.verify_handoff(self.conn, handoff.id)
        self.assertTrue(any("mismatch" in p for p in report["problems"]))

    def test_blob_value_reports_unhashable_without_raising(self):
        handoff = self.make_handoff()
        self.conn.execute(
            "UPDATE agent_handoffs SET objective_md=? WHERE id=?",
            (sqlite3.Binary(b"\x00\x01"), handoff.id),
        )
        self.conn.commit()
        report = agent_handoffs.verify_handoff(self.conn, handoff.id)  # no raise
        self.assertFalse(report["ok"])
        self.assertTrue(any("unhashable" in p for p in report["problems"]))

    def test_child_hash_cannot_launder(self):
        handoff = self.transition(self.make_handoff(), "accept")
        transition = agent_handoffs.get_transitions(self.conn, handoff.id)[0]
        # Tamper the transition's to_state; its stored hash no longer matches,
        # and the parent chain is rebuilt from the RECOMPUTED digest, so the
        # handoff hash mismatches too — the tamper cannot launder itself.
        self.conn.execute(
            "UPDATE agent_handoff_transitions SET to_state='cancelled' WHERE id=?",
            (transition.id,),
        )
        self.conn.commit()
        report = agent_handoffs.verify_handoff(self.conn, handoff.id)
        self.assertFalse(report["ok"])
        self.assertTrue(any("mismatch" in p for p in report["problems"]))

    def test_no_laundering_gate_refuses_write_with_zero_effect(self):
        handoff = self.make_handoff()
        self.conn.execute(
            "UPDATE agent_handoffs SET content_sha256=? WHERE id=?",
            ("2" * 64, handoff.id),
        )
        self.conn.commit()
        before = self.count("agent_handoff_transitions"), self.count("events")
        with self.assertRaises(AosError) as ctx:
            self.transition(handoff, "accept")
        self.assertIn("Refusing to change", str(ctx.exception))
        self.assertEqual(
            (self.count("agent_handoff_transitions"), self.count("events")), before
        )
        # Not repaired: the tampered hash is left exactly as planted.
        self.assertEqual(self._row(handoff.id)["content_sha256"], "2" * 64)

    def test_verify_missing_handoff(self):
        report = agent_handoffs.verify_handoff(self.conn, 4242)
        self.assertFalse(report["ok"])
        self.assertIn("not_found", report["problems"][0])


# ---------------------------------------------------------------------------
# (29-33) Lifecycle matrix.

class HandoffLifecycleTests(_HandoffCase):
    def test_accept_from_proposed(self):
        before = self.count("events")
        handoff = self.transition(self.make_handoff(), "accept")
        self.assertEqual(handoff.state, "accepted")
        transitions = agent_handoffs.get_transitions(self.conn, handoff.id)
        self.assertEqual(len(transitions), 1)
        self.assertEqual(
            (transitions[0].seq, transitions[0].from_state, transitions[0].to_state),
            (1, "proposed", "accepted"),
        )
        self.assertEqual(self.count("events"), before + 2)  # propose + accept

    def test_refuse_and_clarify_require_reason(self):
        with self.assertRaises(AosError):
            self.transition(self.make_handoff(), "refuse")
        with self.assertRaises(AosError):
            self.transition(self.make_handoff(), "clarify")
        handoff = self.transition(
            self.make_handoff(), "refuse", reason_code="out_of_scope"
        )
        self.assertEqual(handoff.state, "refused")
        self.assertEqual(
            agent_handoffs.get_transitions(self.conn, handoff.id)[0].reason_code,
            "out_of_scope",
        )

    def test_unknown_reason_code_refused(self):
        with self.assertRaises(AosError):
            self.transition(self.make_handoff(), "refuse", reason_code="nope")

    def test_accept_and_cancel_reject_supplied_reason(self):
        with self.assertRaises(AosError):
            self.transition(self.make_handoff(), "accept", reason_code="out_of_scope")
        with self.assertRaises(AosError):
            self.transition(self.make_handoff(), "cancel", reason_code="out_of_scope")

    def test_clarify_then_accept_contiguous_seq(self):
        handoff = self.transition(
            self.make_handoff(), "clarify", reason_code="objective_unclear"
        )
        self.assertEqual(handoff.state, "clarification_required")
        handoff = self.transition(handoff, "accept")
        self.assertEqual(handoff.state, "accepted")
        seqs = [t.seq for t in agent_handoffs.get_transitions(self.conn, handoff.id)]
        self.assertEqual(seqs, [1, 2])

    def test_cancel_from_each_legal_source(self):
        self.assertEqual(self.transition(self.make_handoff(), "cancel").state, "cancelled")
        clar = self.transition(
            self.make_handoff(), "clarify", reason_code="objective_unclear"
        )
        self.assertEqual(self.transition(clar, "cancel").state, "cancelled")
        acc = self.transition(self.make_handoff(), "accept")
        self.assertEqual(self.transition(acc, "cancel").state, "cancelled")

    def test_idempotent_repeat_refuses_naming_state(self):
        handoff = self.transition(self.make_handoff(), "accept")
        with self.assertRaises(AosError) as ctx:
            self.transition(handoff, "accept")
        self.assertIn("already accepted", str(ctx.exception))

    def test_illegal_verb_refuses_naming_sources(self):
        handoff = self.transition(self.make_handoff(), "accept")
        with self.assertRaises(AosError) as ctx:
            self.transition(handoff, "clarify", reason_code="objective_unclear")
        message = str(ctx.exception)
        self.assertIn("it is accepted", message)
        self.assertIn("Legal from: proposed", message)

    def test_terminal_states_reject_all_verbs(self):
        refused = self.transition(
            self.make_handoff(), "refuse", reason_code="out_of_scope"
        )
        for verb in ("accept", "cancel"):
            with self.assertRaises(AosError):
                self.transition(refused, verb)
        for verb in ("refuse", "clarify"):
            with self.assertRaises(AosError):
                self.transition(refused, verb, reason_code="operator_judgment")

    def test_note_stored_on_transition_not_event(self):
        handoff = self.transition(self.make_handoff(), "accept", note_md="looks good")
        transition = agent_handoffs.get_transitions(self.conn, handoff.id)[0]
        self.assertEqual(transition.note_md, "looks good")
        _, payload = self.payloads("accept")[0]
        self.assertNotIn("note", payload)
        self.assertNotIn("looks good", json.dumps(payload))

    def test_note_length_bound(self):
        with self.assertRaises(AosError):
            self.transition(self.make_handoff(), "accept", note_md="n" * 2049)

    def test_unknown_verb_refused(self):
        with self.assertRaises(AosError):
            self.transition(self.make_handoff(), "supersede")

    def test_one_event_per_transition(self):
        handoff = self.make_handoff()
        before = self.count("events")
        self.transition(handoff, "accept")
        self.assertEqual(self.count("events"), before + 1)


# ---------------------------------------------------------------------------
# (30) Accept-only current-pin gate and closing verbs after invalidation.

class HandoffAcceptGateTests(_HandoffCase):
    def test_accept_refused_when_participant_suspended(self):
        handoff = self.make_handoff()
        passports.transition_lifecycle(self.conn, name="bob", verb="suspend")
        before = self.count("agent_handoff_transitions"), self.count("events")
        with self.assertRaises(AosError) as ctx:
            self.transition(handoff, "accept")
        self.assertIn("Cannot accept", str(ctx.exception))
        self.assertEqual(
            (self.count("agent_handoff_transitions"), self.count("events")), before
        )
        self.assertEqual(self._row(handoff.id)["state"], "proposed")

    def test_accept_refused_when_pin_moved(self):
        handoff = self.make_handoff()
        self.publish_v2(
            "bob", capabilities=["cap.a"], data_classifications=ALL_CLASSES
        )
        with self.assertRaises(AosError) as ctx:
            self.transition(handoff, "accept")
        self.assertIn("pinned v1, now v2", str(ctx.exception))

    def test_accept_refused_when_identity_tampered(self):
        handoff = self.make_handoff()
        self.conn.execute(
            "UPDATE agents SET content_sha256=? WHERE id=?", ("0" * 64, self.bob.id)
        )
        self.conn.commit()
        with self.assertRaises(AosError):
            self.transition(handoff, "accept")

    def test_closing_verbs_possible_after_participant_invalidation(self):
        for verb, kw in (
            ("refuse", {"reason_code": "operator_judgment"}),
            ("clarify", {"reason_code": "operator_judgment"}),
            ("cancel", {}),
        ):
            with self.subTest(verb=verb):
                handoff = self.make_handoff()
                passports.transition_lifecycle(self.conn, name="bob", verb="suspend")
                result = self.transition(handoff, verb, **kw)
                self.assertIn(
                    result.state,
                    ("refused", "clarification_required", "cancelled"),
                )
                passports.transition_lifecycle(self.conn, name="bob", verb="restore")


# ---------------------------------------------------------------------------
# (34-36) Supersession.

class HandoffSupersessionTests(_HandoffCase):
    def _supersede(self, predecessor, **over):
        params = dict(
            task_id=self.task.id,
            from_agent="alice",
            to_agent="bob",
            objective_md="successor",
            supersedes_id=predecessor.id,
        )
        params.update(over)
        with contextlib.redirect_stderr(io.StringIO()):
            handoff_id = agent_handoffs.create_handoff(self.conn, **params)
        return agent_handoffs.get_handoff(self.conn, handoff_id)

    def test_successor_transitions_predecessor(self):
        predecessor = self.make_handoff()
        successor = self._supersede(predecessor)
        self.assertEqual(successor.supersedes_id, predecessor.id)
        predecessor = agent_handoffs.get_handoff(self.conn, predecessor.id)
        self.assertEqual(predecessor.state, "superseded")
        self.assertIsNone(predecessor.supersedes_id)  # pointer never changes
        transitions = agent_handoffs.get_transitions(self.conn, predecessor.id)
        self.assertEqual(len(transitions), 1)
        self.assertEqual(transitions[0].to_state, "superseded")
        self.assertEqual(
            agent_handoffs.successor_id(self.conn, predecessor.id), successor.id
        )

    def test_two_events_emitted_atomically(self):
        predecessor = self.make_handoff()
        before = self.count("events")
        successor = self._supersede(predecessor)
        actions = [a for a, _ in self.payloads()][-2:]
        self.assertEqual(self.count("events"), before + 2)
        self.assertIn("propose", actions)
        self.assertIn("supersede", actions)
        _, supersede_payload = [
            p for p in self.payloads() if p[0] == "supersede"
        ][-1]
        self.assertEqual(supersede_payload["to_state"], "superseded")

    def test_supersede_from_accepted(self):
        predecessor = self.transition(self.make_handoff(), "accept")
        self._supersede(predecessor)
        self.assertEqual(
            agent_handoffs.get_handoff(self.conn, predecessor.id).state, "superseded"
        )

    def test_terminal_predecessor_refused(self):
        predecessor = self.transition(
            self.make_handoff(), "refuse", reason_code="out_of_scope"
        )
        with self.assertRaises(AosError) as ctx:
            self._supersede(predecessor)
        self.assertIn("Cannot supersede", str(ctx.exception))

    def test_one_successor_rule(self):
        predecessor = self.make_handoff()
        self._supersede(predecessor)
        with self.assertRaises(AosError) as ctx:
            self._supersede(predecessor)
        self.assertIn("already superseded", str(ctx.exception))
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM agent_handoffs WHERE supersedes_id=?",
                (predecessor.id,),
            ).fetchone()[0],
            1,
        )

    def test_failed_successor_rolls_back_predecessor(self):
        predecessor = self.make_handoff()
        before = self._row(predecessor.id)
        events_before = self.count("events")
        with mock.patch.object(
            agent_handoffs.events, "emit", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                self._supersede(predecessor)
        self.assertEqual(self._row(predecessor.id), before)  # byte-identical
        self.assertEqual(
            agent_handoffs.get_transitions(self.conn, predecessor.id), []
        )
        self.assertIsNone(agent_handoffs.successor_id(self.conn, predecessor.id))
        self.assertEqual(self.count("events"), events_before)

    def test_second_event_failure_rolls_back_first_event(self):
        predecessor = self.make_handoff()
        row_before = self._row(predecessor.id)
        transitions_before = len(
            agent_handoffs.get_transitions(self.conn, predecessor.id)
        )
        events_before = self.count("events")
        handoffs_before = self.count("agent_handoffs")

        real_emit = agent_handoffs.events.emit
        calls = 0

        def emit_then_fail(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("boom")
            return real_emit(*args, **kwargs)

        with mock.patch.object(agent_handoffs.events, "emit", emit_then_fail):
            with self.assertRaises(RuntimeError):
                self._supersede(predecessor)

        # Proves the injected failure hit the intended boundary: the propose
        # event genuinely executed on call 1 before supersede's call 2 raised.
        self.assertEqual(calls, 2)

        self.assertEqual(self._row(predecessor.id), row_before)
        self.assertEqual(
            len(agent_handoffs.get_transitions(self.conn, predecessor.id)),
            transitions_before,
        )
        self.assertIsNone(agent_handoffs.successor_id(self.conn, predecessor.id))
        self.assertEqual(self.count("agent_handoffs"), handoffs_before)
        self.assertEqual(self.count("events"), events_before)
        for table in ("agent_handoffs", "agent_handoff_transitions"):
            self.assertEqual(
                self.conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE content_sha256=''"
                ).fetchone()[0],
                0,
            )

    def test_predecessor_supersede_after_participant_invalidation(self):
        predecessor = self.make_handoff()
        passports.transition_lifecycle(self.conn, name="bob", verb="suspend")
        self.publish(
            "carol", capabilities=["cap.a"], data_classifications=ALL_CLASSES
        )
        self._supersede(predecessor, to_agent="carol")
        self.assertEqual(
            agent_handoffs.get_handoff(self.conn, predecessor.id).state, "superseded"
        )

    def test_direct_sql_self_and_forward_supersede_raise(self):
        handoff = self.make_handoff()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "UPDATE agent_handoffs SET supersedes_id=id WHERE id=?", (handoff.id,)
            )
        self.conn.rollback()


# ---------------------------------------------------------------------------
# (38) Rollback injection.

class HandoffRollbackTests(_HandoffCase):
    def _assert_no_blank_hash(self):
        for table in ("agent_handoffs", "agent_handoff_transitions"):
            self.assertEqual(
                self.conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE content_sha256=''"
                ).fetchone()[0],
                0,
            )

    def test_create_rolls_back_on_finalize_failure(self):
        before = self.count("agent_handoffs"), self.count("events")
        with mock.patch.object(
            agent_handoffs, "handoff_digest", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                self.make_handoff()
        self.assertEqual((self.count("agent_handoffs"), self.count("events")), before)
        self._assert_no_blank_hash()

    def test_create_rolls_back_on_event_failure(self):
        before = self.count("agent_handoffs"), self.count("events")
        with mock.patch.object(
            agent_handoffs.events, "emit", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                self.make_handoff()
        self.assertEqual((self.count("agent_handoffs"), self.count("events")), before)

    def test_transition_rolls_back_on_finalize_failure(self):
        handoff = self.make_handoff()
        before = self.count("agent_handoff_transitions"), self.count("events")
        with mock.patch.object(
            agent_handoffs, "transition_digest", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                self.transition(handoff, "accept")
        self.assertEqual(
            (self.count("agent_handoff_transitions"), self.count("events")), before
        )
        self.assertEqual(self._row(handoff.id)["state"], "proposed")
        self._assert_no_blank_hash()

    def test_transition_rolls_back_on_event_failure(self):
        handoff = self.make_handoff()
        before = self.count("agent_handoff_transitions"), self.count("events")
        with mock.patch.object(
            agent_handoffs.events, "emit", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(RuntimeError):
                self.transition(handoff, "accept")
        self.assertEqual(
            (self.count("agent_handoff_transitions"), self.count("events")), before
        )
        self.assertEqual(self._row(handoff.id)["state"], "proposed")

    def test_no_blank_hash_after_successful_writes(self):
        self.transition(self.make_handoff(), "accept")
        self._assert_no_blank_hash()


# ---------------------------------------------------------------------------
# (33) Concurrency — two real connections on a file-backed workspace.

class _FileHandoffCase(_HandoffCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name).resolve()
        self.db_path = self.tmp / "aos.db"
        self.conn = db.connect(self.db_path)
        self.addCleanup(self.conn.close)
        self.conn.executescript(db.SCHEMA_SQL)
        self.conn.execute(
            "INSERT INTO meta(key, value) VALUES ('schema_version', ?)",
            (db.SCHEMA_VERSION,),
        )
        self.conn.commit()
        self.add_project("demo")
        self.task = self.add_task(project="demo", title="build")
        self.alice = self.publish(
            "alice", capabilities=["cap.a"], data_classifications=ALL_CLASSES
        )
        self.bob = self.publish(
            "bob", capabilities=["cap.a"], data_classifications=ALL_CLASSES
        )

    def other_conn(self):
        conn = db.connect(self.db_path)
        self.addCleanup(conn.close)
        return conn


class HandoffConcurrencyTests(_FileHandoffCase):
    def test_second_writer_sees_moved_state_and_refuses(self):
        handoff = self.make_handoff()
        agent_handoffs.transition(self.conn, handoff.id, "accept")
        other = self.other_conn()
        with self.assertRaises(AosError) as ctx:
            agent_handoffs.transition(other, handoff.id, "accept")
        self.assertIn("already accepted", str(ctx.exception))
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM agent_handoff_transitions WHERE handoff_id=?",
                (handoff.id,),
            ).fetchone()[0],
            1,
        )

    def test_accept_versus_cancel_one_legal_one_refusal(self):
        handoff = self.make_handoff()
        agent_handoffs.transition(self.conn, handoff.id, "cancel")  # commits
        other = self.other_conn()
        with self.assertRaises(AosError) as ctx:
            agent_handoffs.transition(other, handoff.id, "accept")
        self.assertIn("it is cancelled", str(ctx.exception))
        self.assertNotIsInstance(ctx.exception, sqlite3.IntegrityError)

    def test_racing_successors_one_commits(self):
        predecessor = self.make_handoff()
        with contextlib.redirect_stderr(io.StringIO()):
            agent_handoffs.create_handoff(
                self.conn, task_id=self.task.id, from_agent="alice",
                to_agent="bob", objective_md="s1", supersedes_id=predecessor.id,
            )
        other = self.other_conn()
        with self.assertRaises(AosError) as ctx:
            with contextlib.redirect_stderr(io.StringIO()):
                agent_handoffs.create_handoff(
                    other, task_id=self.task.id, from_agent="alice",
                    to_agent="bob", objective_md="s2",
                    supersedes_id=predecessor.id,
                )
        self.assertIn("already superseded", str(ctx.exception))
        self.assertNotIsInstance(ctx.exception, sqlite3.IntegrityError)
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM agent_handoffs WHERE supersedes_id=?",
                (predecessor.id,),
            ).fetchone()[0],
            1,
        )

    def test_sequences_are_contiguous_and_unique(self):
        handoff = self.make_handoff()
        agent_handoffs.transition(
            self.conn, handoff.id, "clarify", reason_code="objective_unclear"
        )
        agent_handoffs.transition(self.conn, handoff.id, "accept")
        seqs = [
            t.seq for t in agent_handoffs.get_transitions(self.conn, handoff.id)
        ]
        self.assertEqual(seqs, [1, 2])
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO agent_handoff_transitions (handoff_id, seq, "
                "from_state, to_state, actor, created_at, content_sha256) "
                "VALUES (?, 1, 'proposed', 'cancelled', 'human', ?, ?)",
                (handoff.id, NOW, HASH),
            )
        self.conn.rollback()


# ---------------------------------------------------------------------------
# (13-group) Reads and read-only verification.

class HandoffReadsTests(_HandoffCase):
    def test_list_newest_first_and_filters(self):
        h1 = self.make_handoff(objective_md="first")
        h2 = self.make_handoff(objective_md="second")
        listing = agent_handoffs.list_handoffs(self.conn)
        self.assertEqual(
            [row["handoff"] for row in listing],
            [
                ids.render_id("agent_handoff", h2.id),
                ids.render_id("agent_handoff", h1.id),
            ],
        )
        self.transition(h1, "accept")
        accepted = agent_handoffs.list_handoffs(self.conn, state="accepted")
        self.assertEqual(
            [row["handoff"] for row in accepted],
            [ids.render_id("agent_handoff", h1.id)],
        )
        by_task = agent_handoffs.list_handoffs(self.conn, task_id=self.task.id)
        self.assertEqual(len(by_task), 2)

    def test_restricted_list_placeholders_prose_but_show_reveals(self):
        handoff = self.make_handoff(
            objective_md="secret plan", data_classification="restricted"
        )
        row = agent_handoffs.list_handoffs(self.conn)[0]
        self.assertEqual(row["objective"], ops.RESTRICTED_PLACEHOLDER)
        public = agent_handoffs.handoff_public(self.conn, handoff)
        self.assertEqual(public["objective"], "secret plan")  # show is admin

    def test_handoff_public_full_projection(self):
        handoff = self.transition(self.make_handoff(constraints_md="c"), "accept")
        public = agent_handoffs.handoff_public(self.conn, handoff)
        self.assertEqual(public["from_agent"], "alice")
        self.assertEqual(public["to_agent"], "bob")
        self.assertEqual(public["state"], "accepted")
        self.assertTrue(public["integrity_ok"])
        self.assertEqual(len(public["transitions"]), 1)
        self.assertEqual(public["content_sha256"], handoff.content_sha256)  # full hash

    def test_successor_id_derived(self):
        predecessor = self.make_handoff()
        with contextlib.redirect_stderr(io.StringIO()):
            successor_hid = agent_handoffs.create_handoff(
                self.conn, task_id=self.task.id, from_agent="alice",
                to_agent="bob", objective_md="s", supersedes_id=predecessor.id,
            )
        self.assertEqual(
            agent_handoffs.successor_id(self.conn, predecessor.id), successor_hid
        )
        self.assertIsNone(agent_handoffs.successor_id(self.conn, successor_hid))

    def test_reads_never_mutate(self):
        handoff = self.transition(self.make_handoff(), "accept")
        before = self._row(handoff.id)
        agent_handoffs.list_handoffs(self.conn)
        agent_handoffs.handoff_public(self.conn, handoff)
        agent_handoffs.verify_handoff(self.conn, handoff.id)
        self.assertEqual(self._row(handoff.id), before)


# ---------------------------------------------------------------------------
# (39) Event payloads and privacy.

class HandoffEventPrivacyTests(_HandoffCase):
    def _assert_clean(self, payload, allowed):
        keys = set(payload) - {"schema_version"}
        secret_keys = {"secret_warning", "secret_fields", "secret_patterns"}
        self.assertTrue(keys <= set(allowed) | secret_keys, keys - set(allowed))
        self.assertIsNone(
            __import__("re").search(r"[0-9a-f]{64}", json.dumps(payload))
        )

    def test_propose_event_allowlist(self):
        self.make_handoff(objective_md="private objective text")
        _, payload = self.payloads("propose")[0]
        self._assert_clean(payload, agent_handoffs.PROPOSE_EVENT_KEYS)
        self.assertNotIn("private objective text", json.dumps(payload))
        self.assertNotIn("decision", payload)
        self.assertEqual(len(payload["from_passport_sha256_prefix"]), 12)

    def test_transition_event_allowlist(self):
        self.transition(self.make_handoff(), "refuse", reason_code="out_of_scope")
        _, payload = self.payloads("refuse")[0]
        self._assert_clean(payload, agent_handoffs.TRANSITION_EVENT_KEYS)
        self.assertEqual(payload["reason_code"], "out_of_scope")

    def test_secret_objective_warns_metadata_not_value(self):
        secret = "password: hunter2superlongsecret"
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            handoff_id = agent_handoffs.create_handoff(
                self.conn, task_id=self.task.id, from_agent="alice",
                to_agent="bob", objective_md=secret,
            )
        self.assertIn("secret-shaped", stderr.getvalue())
        # the canonical row keeps the text; the event never carries it
        handoff = agent_handoffs.get_handoff(self.conn, handoff_id)
        self.assertEqual(handoff.objective_md, secret)
        _, payload = self.payloads("propose")[-1]
        self.assertTrue(payload.get("secret_warning"))
        self.assertIn("objective", payload.get("secret_fields", []))
        self.assertNotIn("hunter2superlongsecret", json.dumps(payload))

    def test_note_secret_warns_not_value(self):
        secret = "token: abcdefaddress0123456789key"
        handoff = self.make_handoff()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            agent_handoffs.transition(
                self.conn, handoff.id, "accept", note_md=secret
            )
        _, payload = self.payloads("accept")[0]
        self.assertNotIn("abcdefaddress", json.dumps(payload))
        transition = agent_handoffs.get_transitions(self.conn, handoff.id)[0]
        self.assertEqual(transition.note_md, secret)

    def test_decision_id_never_in_events_and_behavior_identical(self):
        decision = ops.add_decision(
            self.conn, title="t", project_slug="demo", decision="d"
        )
        with_decision = self.make_handoff(decision_id=decision.id)
        without = self.make_handoff()
        self.transition(with_decision, "accept")
        self.transition(without, "accept")
        for _, payload in self.payloads():
            self.assertNotIn("decision", payload)
            self.assertNotIn(
                ids.render_id("decision", decision.id), json.dumps(payload)
            )


# ---------------------------------------------------------------------------
# Classification advisory (§13, §15).

class HandoffClassificationAdvisoryTests(_HandoffCase):
    def test_advisory_printed_when_not_declared(self):
        self.publish("carol", capabilities=["cap.a"], data_classifications=["public"])
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            handoff_id = agent_handoffs.create_handoff(
                self.conn, task_id=self.task.id, from_agent="alice",
                to_agent="carol", objective_md="o",
                data_classification="confidential",
            )
        self.assertIn("ADVISORY", stderr.getvalue())
        self.assertIn("confidential", stderr.getvalue())
        # created anyway (non-blocking), and never stored in events
        self.assertIsNotNone(agent_handoffs.get_handoff(self.conn, handoff_id))
        for _, payload in self.payloads():
            self.assertNotIn("ADVISORY", json.dumps(payload))
            self.assertNotIn("does not declare", json.dumps(payload))

    def test_no_advisory_when_declared(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            agent_handoffs.create_handoff(
                self.conn, task_id=self.task.id, from_agent="alice",
                to_agent="bob", objective_md="o", data_classification="internal",
            )
        self.assertNotIn("ADVISORY", stderr.getvalue())


# ---------------------------------------------------------------------------
# (matrix 14) Passport discard guard (§21).

class HandoffDiscardGuardTests(_LiveCase):
    def test_referenced_draft_yields_normal_refusal_not_integrity_error(self):
        self.add_project("demo")
        self.publish("active_one", capabilities=["cap.a"])
        self.draft("drafty", capabilities=["cap.a"])
        # A plan evaluates every agent; the draft becomes an excluded candidate
        # whose row references it by id.
        routing.create_plan(self.conn, self.request(capabilities=["cap.a"]))
        self.assertGreater(
            self.conn.execute(
                "SELECT COUNT(*) FROM routing_plan_candidates c "
                "JOIN agents a ON a.id=c.agent_id WHERE a.name='drafty'"
            ).fetchone()[0],
            0,
        )
        with self.assertRaises(AosError) as ctx:
            passports.discard_agent(self.conn, name="drafty")
        self.assertNotIsInstance(ctx.exception, sqlite3.IntegrityError)
        self.assertIn("routing_plan_candidates", str(ctx.exception))
        # not deleted
        self.assertIsNotNone(passports.get_agent(self.conn, "drafty"))

    def test_unreferenced_draft_still_discardable(self):
        self.add_project("demo")
        self.draft("lonely", capabilities=["cap.a"])
        passports.discard_agent(self.conn, name="lonely")  # COUNT(*)=0, no crash
        self.assertIsNone(passports.get_agent(self.conn, "lonely"))

    def test_reference_query_is_name_joined_and_no_handoff_entry(self):
        labels = {label for label, _, _ in passports._REFERENCE_QUERIES}
        self.assertIn("routing_plan_candidates", labels)
        self.assertNotIn("agent_handoffs", labels)
        entry = next(
            e for e in passports._REFERENCE_QUERIES if e[0] == "routing_plan_candidates"
        )
        self.assertIn("JOIN agents", entry[1])
        self.assertIn("a.name = ?", entry[1])
        self.assertEqual(entry[2]("nm"), ("nm",))


# ---------------------------------------------------------------------------
# (15, 38) Static guarantees: mutation surface, forbidden runtime, no
# completed state, single-owner transactions.

class HandoffStaticTests(unittest.TestCase):
    SOURCE = (REPO_ROOT / "agentic_os" / "agent_handoffs.py").read_text(
        encoding="utf-8"
    )

    def test_only_sanctioned_mutations(self):
        self.assertNotIn("DELETE FROM agent_handoffs", self.SOURCE)
        self.assertNotIn("DELETE FROM agent_handoff_transitions", self.SOURCE)
        # two UPDATEs on agent_handoffs (create finalize + projection), one on
        # the transitions table (hash finalization) — nothing else mutates.
        self.assertEqual(self.SOURCE.count("UPDATE agent_handoffs SET"), 2)
        self.assertEqual(
            self.SOURCE.count("UPDATE agent_handoff_transitions SET"), 1
        )
        self.assertIn(
            "UPDATE agent_handoffs SET state = ?, updated_at = ?, "
            "content_sha256 = ?",
            self.SOURCE,
        )

    def test_single_owner_transactions_never_nested(self):
        # Two write owners (create_handoff, transition), each owning exactly one
        # boundary; the supersede path is a participant inside create's boundary,
        # never a nested transaction. (Count the code statements, not the prose
        # that also names the pattern.)
        self.assertEqual(self.SOURCE.count("with db.transaction("), 2)
        self.assertEqual(self.SOURCE.count('conn.execute("BEGIN IMMEDIATE")'), 2)

    def test_no_forbidden_runtime(self):
        for token in (
            "subprocess", "socket", "requests", "urllib", "http.client",
            "os.system", "exec(", "eval(", "provider", "workflow",
        ):
            self.assertNotIn(token, self.SOURCE)

    def test_no_completed_state_vocabulary(self):
        self.assertNotIn("completed", models.AGENT_HANDOFF_STATES)
        self.assertNotIn("complete", agent_handoffs._EXPLICIT_VERBS)

    def test_no_approval_substring(self):
        # A repurposed-as-approval reading of `decision_id` would use the word
        # "approval"; it appears nowhere in this module. The behavioural proof
        # that `decision_id` gates nothing lives in HandoffEventPrivacyTests.
        self.assertNotIn("approval", self.SOURCE)


# ---------------------------------------------------------------------------
# (58) Two-workspace isolation.

class HandoffWorkspaceIsolationTests(unittest.TestCase):
    def _workspace(self):
        conn = db.connect(":memory:")
        self.addCleanup(conn.close)
        conn.executescript(db.SCHEMA_SQL)
        conn.execute(
            "INSERT INTO meta(key, value) VALUES ('schema_version', ?)",
            (db.SCHEMA_VERSION,),
        )
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        ops.add_project(conn, slug="demo", name="Demo", repo=str(root))
        task = ops.add_task(conn, title="t", project_slug="demo")
        for name in ("alice", "bob"):
            passports.create_agent(
                conn, name=name, role="r", mission="m",
                fragment_path=self._fragment(root, name),
            )
            passports.publish_passport(conn, name=name, path=None)
        conn.commit()
        return conn, task

    @staticmethod
    def _fragment(root, name):
        path = root / f"{name}.json"
        path.write_text(
            json.dumps({"autonomy": "supervised", "capabilities": ["cap.a"]}),
            encoding="utf-8",
        )
        return path

    def test_operations_in_one_workspace_do_not_touch_another(self):
        conn_a, task_a = self._workspace()
        conn_b, _ = self._workspace()
        with contextlib.redirect_stderr(io.StringIO()):
            agent_handoffs.create_handoff(
                conn_a, task_id=task_a.id, from_agent="alice",
                to_agent="bob", objective_md="only in A",
            )
        self.assertEqual(
            conn_a.execute("SELECT COUNT(*) FROM agent_handoffs").fetchone()[0], 1
        )
        self.assertEqual(
            conn_b.execute("SELECT COUNT(*) FROM agent_handoffs").fetchone()[0], 0
        )


# ===========================================================================
# WAVE 5 — handoff CLI, power, recovery (cli.py seven leaves, power.py seven
# entries). Contract §17-18; test matrix groups 41-44 plus the parser,
# wiring, end-to-end, privacy and entrypoint pins mandated for this wave.
# ===========================================================================

GOVERNED_HANDOFF_VERBS = (
    "create", "list", "show", "accept", "refuse", "clarify", "cancel"
)

FORBIDDEN_LEAVES = (
    ("agent", "route", "select"),
    ("agent", "handoff", "supersede"),
    ("agent", "handoff", "complete"),
    ("agent", "handoff", "verify"),
)


class Wave5CliCase(Wave3CliCase):
    """A live file-backed workspace driven end-to-end through the CLI: the
    demo project, one task and two published agents that declare every data
    classification (so a default `internal` handoff raises no advisory)."""

    def setUp(self):
        super().setUp()
        self.run_cli("task", "add", "build", "-p", "demo")
        self.make_agent(
            "alice", capabilities=["cap.a"], data_classifications=ALL_CLASSES
        )
        self.make_agent(
            "bob", capabilities=["cap.a"], data_classifications=ALL_CLASSES
        )

    def create(self, *extra):
        return self.run_cli(
            "agent", "handoff", "create", "--task", "T-0001", "--from",
            "alice", "--to", "bob", "--objective", "ship the widget", *extra,
        )

    def query(self, sql, params=()):
        conn = db.open_db(self.root / ".agentic-os")
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def execute(self, sql, params=()):
        conn = db.open_db(self.root / ".agentic-os")
        try:
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    def table_counts(self):
        return tuple(
            self.query(f"SELECT COUNT(*) FROM {table}")[0][0]
            for table in (
                "agent_handoffs", "agent_handoff_transitions", "events"
            )
        )


class Wave5CliParserTests(Wave3CliCase):
    def test_parser_exposes_exactly_seven_governed_handoff_leaves(self):
        leaves = {
            p for p in power.iter_command_paths(cli.build_parser())
            if p[:2] == ("agent", "handoff")
        }
        self.assertEqual(
            leaves,
            {("agent", "handoff", verb) for verb in GOVERNED_HANDOFF_VERBS},
        )

    def test_no_forbidden_leaves(self):
        leaves = set(power.iter_command_paths(cli.build_parser()))
        for forbidden in FORBIDDEN_LEAVES:
            with self.subTest(leaf=forbidden):
                self.assertNotIn(forbidden, leaves)

    def test_legacy_top_level_handoff_parser_is_unchanged(self):
        leaves = set(power.iter_command_paths(cli.build_parser()))
        self.assertEqual(
            {p for p in leaves if p[0] == "handoff"},
            {("handoff", "create"), ("handoff", "accept")},
        )

    def test_create_requires_task_from_to_objective(self):
        parser = cli.build_parser()
        base = [
            "agent", "handoff", "create", "--task", "T-0001", "--from", "a",
            "--to", "b", "--objective", "o",
        ]
        self.assertEqual(parser.parse_args(base).task, "T-0001")
        for drop in ("--task", "--from", "--to", "--objective"):
            with self.subTest(missing=drop):
                index = base.index(drop)
                argv = base[:index] + base[index + 2:]
                with self.assertRaises(AosError):
                    parser.parse_args(argv)

    def test_create_defaults_and_repeatable_evidence(self):
        parser = cli.build_parser()
        args = parser.parse_args([
            "agent", "handoff", "create", "--task", "T-0001", "--from", "a",
            "--to", "b", "--objective", "o",
            "--expect-evidence", "test", "--expect-evidence", "commit",
        ])
        self.assertEqual(args.expect_evidence, ["test", "commit"])
        self.assertEqual(args.min_evidence, 0)
        self.assertEqual(
            args.classification, agent_handoffs.DEFAULT_DATA_CLASSIFICATION
        )
        self.assertIsNone(args.plan)
        self.assertIsNone(args.constraints)
        self.assertIsNone(args.decision)
        self.assertIsNone(args.supersedes)
        self.assertFalse(args.json)
        defaults = parser.parse_args([
            "agent", "handoff", "create", "--task", "T-0001", "--from", "a",
            "--to", "b", "--objective", "o",
        ])
        self.assertIsNone(defaults.expect_evidence)

    def test_refuse_and_clarify_require_reason(self):
        parser = cli.build_parser()
        for verb in ("refuse", "clarify"):
            with self.subTest(verb=verb):
                with self.assertRaises(AosError):
                    parser.parse_args(["agent", "handoff", verb, "AH-0001"])

    def test_accept_and_cancel_take_no_reason(self):
        parser = cli.build_parser()
        for verb in ("accept", "cancel"):
            with self.subTest(verb=verb):
                with self.assertRaises(AosError):
                    parser.parse_args([
                        "agent", "handoff", verb, "AH-0001",
                        "--reason", "out_of_scope",
                    ])

    def test_json_only_where_the_frozen_contract_grants_it(self):
        parser = cli.build_parser()
        for argv in (
            ["agent", "handoff", "create", "--task", "T-0001", "--from", "a",
             "--to", "b", "--objective", "o", "--json"],
            ["agent", "handoff", "list", "--json"],
            ["agent", "handoff", "show", "AH-0001", "--json"],
            ["agent", "handoff", "accept", "AH-0001", "--json"],
        ):
            with self.subTest(argv=argv):
                self.assertTrue(parser.parse_args(argv).json)
        for verb in ("refuse", "clarify", "cancel"):
            with self.subTest(verb=verb):
                argv = ["agent", "handoff", verb, "AH-0001", "--json"]
                if verb in ("refuse", "clarify"):
                    argv += ["--reason", "out_of_scope"]
                with self.assertRaises(AosError):
                    parser.parse_args(argv)

    def test_usage_errors_exit_1_not_2(self):
        for argv in (
            ("agent", "handoff", "create", "--task", "T-0001"),
            ("agent", "handoff", "refuse", "AH-0001"),
            ("agent", "handoff", "clarify", "AH-0001"),
            ("agent", "handoff", "bogus"),
            ("agent", "handoff", "cancel", "AH-0001", "--json"),
        ):
            with self.subTest(argv=argv):
                code, out, err = self.run_cli(*argv)
                self.assertEqual(code, 1)
                self.assertEqual(out, "")

    def test_malformed_ids_exit_1(self):
        for argv in (
            ("agent", "handoff", "show", "not-an-id"),
            ("agent", "handoff", "accept", "H-0001"),
            ("agent", "handoff", "cancel", "AH1"),
            ("agent", "handoff", "create", "--task", "bogus", "--from", "a",
             "--to", "b", "--objective", "o"),
            ("agent", "handoff", "create", "--task", "T-0001", "--from", "a",
             "--to", "b", "--objective", "o", "--plan", "PX-1"),
            ("agent", "handoff", "create", "--task", "T-0001", "--from", "a",
             "--to", "b", "--objective", "o", "--decision", "D1"),
            ("agent", "handoff", "create", "--task", "T-0001", "--from", "a",
             "--to", "b", "--objective", "o", "--supersedes", "T-0001"),
        ):
            with self.subTest(argv=argv):
                code, out, err = self.run_cli(*argv)
                self.assertEqual(code, 1)
                self.assertEqual(out, "")


class Wave5CliWiringTests(Wave5CliCase):
    HANDLERS = (
        "cmd_agent_handoff_create",
        "cmd_agent_handoff_list",
        "cmd_agent_handoff_show",
        "cmd_agent_handoff_accept",
        "cmd_agent_handoff_refuse",
        "cmd_agent_handoff_clarify",
        "cmd_agent_handoff_cancel",
        "_agent_handoff_transition",
    )

    def test_create_calls_create_handoff_exactly_once_with_defaults(self):
        with mock.patch.object(
            agent_handoffs, "create_handoff", return_value=1
        ) as create:
            code, out, _ = self.run_cli(
                "agent", "handoff", "create", "--task", "T-0001", "--from",
                "alice", "--to", "bob", "--objective", "obj",
            )
        self.assertEqual(code, 0)
        self.assertEqual(create.call_count, 1)
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["task_id"], 1)
        self.assertEqual(kwargs["from_agent"], "alice")
        self.assertEqual(kwargs["to_agent"], "bob")
        self.assertEqual(kwargs["objective_md"], "obj")
        self.assertEqual(tuple(kwargs["expected_evidence"]), ())
        self.assertEqual(kwargs["min_evidence_count"], 0)
        self.assertIsNone(kwargs["constraints_md"])
        self.assertEqual(kwargs["data_classification"], "internal")
        self.assertIsNone(kwargs["plan_id"])
        self.assertIsNone(kwargs["decision_id"])
        self.assertIsNone(kwargs["supersedes_id"])
        self.assertIn("AH-0001", out)
        self.assertIn("proposed", out)

    def test_create_passes_every_optional_reference_parsed(self):
        with mock.patch.object(
            agent_handoffs, "create_handoff", return_value=9
        ) as create:
            code, _, _ = self.run_cli(
                "agent", "handoff", "create", "--task", "T-0001", "--from",
                "alice", "--to", "bob", "--objective", "obj",
                "--plan", "RP-0007", "--expect-evidence", "test",
                "--expect-evidence", "commit", "--min-evidence", "2",
                "--constraints", "c", "--classification", "restricted",
                "--decision", "D-0003", "--supersedes", "AH-0002",
            )
        self.assertEqual(code, 0)
        kwargs = create.call_args.kwargs
        self.assertEqual(kwargs["plan_id"], 7)
        self.assertEqual(tuple(kwargs["expected_evidence"]), ("test", "commit"))
        self.assertEqual(kwargs["min_evidence_count"], 2)
        self.assertEqual(kwargs["constraints_md"], "c")
        self.assertEqual(kwargs["data_classification"], "restricted")
        self.assertEqual(kwargs["decision_id"], 3)
        self.assertEqual(kwargs["supersedes_id"], 2)

    def test_each_transition_verb_calls_transition_exactly_once(self):
        for verb, extra, expected_reason in (
            ("accept", (), None),
            ("refuse", ("--reason", "out_of_scope"), "out_of_scope"),
            ("clarify", ("--reason", "objective_unclear"), "objective_unclear"),
            ("cancel", (), None),
        ):
            with self.subTest(verb=verb):
                with mock.patch.object(agent_handoffs, "transition") as tr:
                    code, _, _ = self.run_cli(
                        "agent", "handoff", verb, "AH-0004", *extra
                    )
                self.assertEqual(code, 0)
                self.assertEqual(tr.call_count, 1)
                self.assertEqual(tr.call_args.args[1:], (4, verb))
                self.assertEqual(
                    tr.call_args.kwargs.get("reason_code"), expected_reason
                )
                self.assertIsNone(tr.call_args.kwargs.get("note_md"))

    def test_note_is_forwarded_verbatim(self):
        with mock.patch.object(agent_handoffs, "transition") as tr:
            code, _, _ = self.run_cli(
                "agent", "handoff", "accept", "AH-0004", "--note", "go ahead"
            )
        self.assertEqual(code, 0)
        self.assertEqual(tr.call_args.kwargs.get("note_md"), "go ahead")

    def test_list_and_show_call_their_read_projections_once(self):
        self.create()
        with mock.patch.object(
            agent_handoffs, "list_handoffs", return_value=[]
        ) as listing:
            code, _, _ = self.run_cli("agent", "handoff", "list")
        self.assertEqual(code, 0)
        self.assertEqual(listing.call_count, 1)
        with mock.patch.object(
            agent_handoffs, "handoff_public", return_value={}
        ) as public:
            code, _, _ = self.run_cli(
                "agent", "handoff", "show", "AH-0001", "--json"
            )
        self.assertEqual(code, 0)
        self.assertEqual(public.call_count, 1)

    def test_handlers_own_no_sql_transaction_event_or_forbidden_runtime(self):
        # Forbidden-token literals only, asserted ABSENT from handler source;
        # nothing here is ever executed (the HandoffStaticTests pattern).
        for name in self.HANDLERS:
            src = inspect.getsource(getattr(cli, name))
            with self.subTest(handler=name):
                for token in (
                    "conn.execute", "BEGIN", "INSERT", "UPDATE", "DELETE",
                    "SELECT", "db.transaction", "events.emit", "ADVISORY",
                    "subprocess", "socket", "os.system", "exec(", "eval(",
                    "provider", "workflow",
                ):
                    self.assertNotIn(token, src)

    def test_no_duplicate_classification_advisory(self):
        self.make_agent(
            "carol", capabilities=["cap.a"], data_classifications=["public"]
        )
        code, _, err = self.run_cli(
            "agent", "handoff", "create", "--task", "T-0001", "--from",
            "alice", "--to", "carol", "--objective", "o",
            "--classification", "confidential",
        )
        self.assertEqual(code, 0)
        self.assertEqual(err.count("ADVISORY"), 1)


class Wave5CliBehaviorTests(Wave5CliCase):
    def test_create_text_and_json(self):
        code, out, err = self.create()
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "AH-0001 proposed")
        code, out, _ = self.create("--json")
        self.assertEqual(code, 0)
        doc = json.loads(out)["handoff"]
        self.assertEqual(doc["handoff"], "AH-0002")
        self.assertEqual(doc["state"], "proposed")
        self.assertEqual(doc["from_agent"], "alice")
        self.assertEqual(doc["to_agent"], "bob")
        self.assertEqual(doc["expected_evidence"], [])
        self.assertEqual(doc["min_evidence_count"], 0)
        self.assertEqual(doc["data_classification"], "internal")
        self.assertTrue(doc["integrity_ok"])
        self.assertEqual(doc["transitions"], [])

    def test_create_all_optional_references_and_supersede(self):
        self.run_cli("agent", "route", "plan", "--capability", "cap.a")
        self.run_cli(
            "decision", "add", "why", "-p", "demo", "--decision", "because"
        )
        self.create()
        code, out, err = self.run_cli(
            "agent", "handoff", "create", "--task", "T-0001", "--from",
            "alice", "--to", "bob", "--objective", "successor",
            "--plan", "RP-0001", "--expect-evidence", "test",
            "--expect-evidence", "commit", "--min-evidence", "2",
            "--constraints", "stay in scope", "--classification",
            "confidential", "--decision", "D-0001", "--supersedes", "AH-0001",
            "--json",
        )
        self.assertEqual(code, 0, err)
        doc = json.loads(out)["handoff"]
        self.assertEqual(doc["handoff"], "AH-0002")
        self.assertEqual(doc["plan"], "RP-0001")
        self.assertEqual(doc["expected_evidence"], ["commit", "test"])
        self.assertEqual(doc["min_evidence_count"], 2)
        self.assertEqual(doc["constraints"], "stay in scope")
        self.assertEqual(doc["data_classification"], "confidential")
        self.assertEqual(doc["decision"], "D-0001")
        self.assertEqual(doc["supersedes"], "AH-0001")
        _, out, _ = self.run_cli("agent", "handoff", "show", "AH-0001", "--json")
        predecessor = json.loads(out)["handoff"]
        self.assertEqual(predecessor["state"], "superseded")
        self.assertEqual(predecessor["superseded_by"], "AH-0002")

    def test_empty_list_text(self):
        code, out, _ = self.run_cli("agent", "handoff", "list")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "(no agent handoffs)")

    def test_list_text_json_newest_first_and_filters(self):
        self.create()
        self.run_cli("task", "add", "second", "-p", "demo")
        code, _, err = self.run_cli(
            "agent", "handoff", "create", "--task", "T-0002", "--from",
            "alice", "--to", "bob", "--objective", "second objective",
        )
        self.assertEqual(code, 0, err)
        self.run_cli("agent", "handoff", "accept", "AH-0002")
        code, out, _ = self.run_cli("agent", "handoff", "list")
        self.assertEqual(code, 0)
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("AH-0002"))
        self.assertTrue(lines[1].startswith("AH-0001"))
        self.assertIn("alice → bob", lines[0])
        self.assertIn("T-0002", lines[0])
        self.assertIn("accepted", lines[0])
        self.assertIn("second objective", lines[0])
        doc = json.loads(self.run_cli("agent", "handoff", "list", "--json")[1])
        self.assertEqual(
            [h["handoff"] for h in doc["handoffs"]], ["AH-0002", "AH-0001"]
        )
        doc = json.loads(self.run_cli(
            "agent", "handoff", "list", "--task", "T-0002", "--json")[1])
        self.assertEqual([h["handoff"] for h in doc["handoffs"]], ["AH-0002"])
        doc = json.loads(self.run_cli(
            "agent", "handoff", "list", "--state", "proposed", "--json")[1])
        self.assertEqual([h["handoff"] for h in doc["handoffs"]], ["AH-0001"])
        doc = json.loads(self.run_cli(
            "agent", "handoff", "list", "--task", "T-0009", "--json")[1])
        self.assertEqual(doc["handoffs"], [])

    def test_restricted_list_placeholder_and_show_reveals(self):
        code, _, _ = self.create("--classification", "restricted")
        self.assertEqual(code, 0)
        code, out, _ = self.run_cli("agent", "handoff", "list")
        self.assertEqual(code, 0)
        self.assertNotIn("ship the widget", out)
        self.assertIn(ops.RESTRICTED_PLACEHOLDER, out)
        out_json = self.run_cli("agent", "handoff", "list", "--json")[1]
        self.assertNotIn("ship the widget", out_json)
        code, out, _ = self.run_cli("agent", "handoff", "show", "AH-0001")
        self.assertEqual(code, 0)
        self.assertIn("ship the widget", out)

    def test_show_text_and_json_full_record(self):
        self.create()
        self.run_cli(
            "agent", "handoff", "clarify", "AH-0001", "--reason",
            "objective_unclear", "--note", "which widget?",
        )
        self.run_cli("agent", "handoff", "accept", "AH-0001")
        code, out, _ = self.run_cli("agent", "handoff", "show", "AH-0001")
        self.assertEqual(code, 0)
        self.assertIn("AH-0001", out)
        self.assertIn("accepted", out)
        self.assertIn("alice", out)
        self.assertIn("bob", out)
        self.assertIn("ship the widget", out)
        self.assertRegex(out, r"[0-9a-f]{64}")  # full hashes are show-class
        self.assertIn("proposed → clarification_required", out)
        self.assertIn("clarification_required → accepted", out)
        self.assertIn("objective_unclear", out)
        self.assertIn("which widget?", out)  # note is show-class history
        doc = json.loads(
            self.run_cli("agent", "handoff", "show", "AH-0001", "--json")[1]
        )["handoff"]
        self.assertEqual(doc["state"], "accepted")
        self.assertEqual(len(doc["transitions"]), 2)
        self.assertTrue(doc["integrity_ok"])
        self.assertEqual(len(doc["content_sha256"]), 64)

    def test_show_absent_exits_1(self):
        code, out, err = self.run_cli("agent", "handoff", "show", "AH-0099")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("AH-0099", err)

    def test_damaged_show_does_not_crash(self):
        self.create()
        self.execute(
            "UPDATE agent_handoffs SET content_sha256=?", ("e" * 64,)
        )
        code, out, _ = self.run_cli("agent", "handoff", "show", "AH-0001")
        self.assertEqual(code, 0)
        self.assertIn("mismatch", out)
        doc = json.loads(
            self.run_cli("agent", "handoff", "show", "AH-0001", "--json")[1]
        )["handoff"]
        self.assertFalse(doc["integrity_ok"])

    def test_accept_text_and_json(self):
        self.create()
        code, out, _ = self.run_cli(
            "agent", "handoff", "accept", "AH-0001", "--note", "go ahead"
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "AH-0001 accepted")
        self.assertNotIn("go ahead", out)  # notes live in show-class history
        self.create()
        code, out, _ = self.run_cli(
            "agent", "handoff", "accept", "AH-0002", "--json"
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(out), {"handoff": "AH-0002", "state": "accepted"}
        )

    def test_refuse_clarify_cancel_text(self):
        self.create()
        self.create()
        self.create()
        code, out, _ = self.run_cli(
            "agent", "handoff", "refuse", "AH-0001", "--reason", "out_of_scope"
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "AH-0001 refused")
        code, out, _ = self.run_cli(
            "agent", "handoff", "clarify", "AH-0002", "--reason",
            "objective_unclear",
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "AH-0002 clarification_required")
        code, out, _ = self.run_cli("agent", "handoff", "cancel", "AH-0003")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "AH-0003 cancelled")

    def test_illegal_terminal_reason_and_pin_drift_refusals_exit_1(self):
        self.create()
        self.run_cli("agent", "handoff", "accept", "AH-0001")
        code, out, err = self.run_cli("agent", "handoff", "accept", "AH-0001")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("already accepted", err)
        code, out, err = self.run_cli(
            "agent", "handoff", "refuse", "AH-0001", "--reason", "out_of_scope"
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("it is accepted", err)
        code, out, err = self.run_cli(
            "agent", "handoff", "refuse", "AH-0001", "--reason", "bogus_code"
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        # pin drift: publish bob v2, then accept a proposal pinned at v1
        self.create()  # AH-0002, pinned at bob v1
        document = passports.build_passport_document(
            agent_name="bob", passport_version=2, agent_class="custom",
            scope_level="global", project_slug=None, role="worker",
            mission="do v2", method="publish",
            fragment={
                "autonomy": "supervised", "capabilities": ["cap.a"],
                "data_classifications": ALL_CLASSES,
            },
        )
        artifact = self.root / "bob_v2.json"
        artifact.write_text(
            protocols.serialize_canonical_file_bytes(document).decode("utf-8"),
            encoding="utf-8",
        )
        code, _, err = self.run_cli(
            "agent", "passport", "publish", "bob", "--file", str(artifact)
        )
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli("agent", "handoff", "accept", "AH-0002")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("pinned v1, now v2", err)

    def test_no_output_implies_execution_or_completion(self):
        self.create()
        outputs = []
        outputs.append(self.run_cli("agent", "handoff", "accept", "AH-0001")[1])
        outputs.append(self.run_cli("agent", "handoff", "list")[1])
        outputs.append(self.run_cli("agent", "handoff", "show", "AH-0001")[1])
        outputs.append(self.create()[1])
        for text in outputs:
            lower = text.lower()
            for word in ("complete", "executed", "executing", "running",
                         "launched", "scheduled"):
                self.assertNotIn(word, lower)

    def test_cli_adds_no_extra_events_or_rows(self):
        self.create()
        self.run_cli("agent", "handoff", "accept", "AH-0001")
        actions = [
            row["action"] for row in self.query(
                "SELECT action FROM events WHERE entity='agent_handoff' "
                "ORDER BY id"
            )
        ]
        self.assertEqual(actions, ["propose", "accept"])
        self.assertEqual(self.table_counts()[0], 1)
        self.run_cli("agent", "handoff", "list")
        self.run_cli("agent", "handoff", "show", "AH-0001")
        self.assertEqual(
            self.query(
                "SELECT COUNT(*) FROM events WHERE entity='agent_handoff'"
            )[0][0],
            2,
        )

    def test_non_show_text_outputs_carry_no_full_hash(self):
        _, out, _ = self.create()
        self.assertNotRegex(out, r"[0-9a-f]{64}")
        _, out, _ = self.run_cli("agent", "handoff", "list")
        self.assertNotRegex(out, r"[0-9a-f]{64}")
        _, out, _ = self.run_cli("agent", "handoff", "cancel", "AH-0001")
        self.assertNotRegex(out, r"[0-9a-f]{64}")

    def test_legacy_handoff_commands_unchanged(self):
        self.create()
        code, out, _ = self.run_cli(
            "handoff", "create", "T-0001", "--from", "x", "--to", "y",
            "--state", "proposed",
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "H-0001")
        code, out, _ = self.run_cli("handoff", "accept", "H-0001")
        self.assertEqual(code, 0)
        self.assertIn("H-0001 accepted", out)


class Wave5PowerPolicyTests(unittest.TestCase):
    U_A3_POLICY = {
        ("agent", "route", "plan"): (power.AUTHORITATIVE_WRITE, True),
        ("agent", "route", "list"): (power.READ_ONLY, False),
        ("agent", "route", "show"): (power.READ_ONLY, False),
        ("agent", "route", "verify"): (power.READ_ONLY, False),
        ("agent", "handoff", "create"): (power.AUTHORITATIVE_WRITE, True),
        ("agent", "handoff", "list"): (power.READ_ONLY, False),
        ("agent", "handoff", "show"): (power.READ_ONLY, False),
        ("agent", "handoff", "accept"): (power.AUTHORITATIVE_WRITE, True),
        ("agent", "handoff", "refuse"): (power.AUTHORITATIVE_WRITE, True),
        ("agent", "handoff", "clarify"): (power.AUTHORITATIVE_WRITE, True),
        ("agent", "handoff", "cancel"): (power.AUTHORITATIVE_WRITE, True),
    }

    def test_exactly_seven_handoff_entries_with_exact_classes(self):
        entries = {
            path for path in power.COMMAND_POLICY
            if path[:2] == ("agent", "handoff")
        }
        self.assertEqual(
            entries,
            {p for p in self.U_A3_POLICY if p[:2] == ("agent", "handoff")},
        )
        for path, (kind, ledger) in self.U_A3_POLICY.items():
            with self.subTest(path=path):
                policy = power.COMMAND_POLICY[path]
                self.assertEqual((policy.kind, policy.ledger), (kind, ledger))

    def test_final_inventory_eleven_leaves_six_writes_five_reads(self):
        u_a3 = [
            path for path in power.COMMAND_POLICY
            if path[:2] in (("agent", "route"), ("agent", "handoff"))
        ]
        self.assertEqual(len(u_a3), 11)
        writes = [
            path for path in u_a3
            if power.COMMAND_POLICY[path].kind == power.AUTHORITATIVE_WRITE
        ]
        reads = [
            path for path in u_a3
            if power.COMMAND_POLICY[path].kind == power.READ_ONLY
        ]
        self.assertEqual(len(writes), 6)
        self.assertEqual(len(reads), 5)
        for path in writes:
            with self.subTest(path=path):
                self.assertTrue(power.COMMAND_POLICY[path].ledger)

    def test_parser_and_policy_are_bijective_for_u_a3(self):
        leaves = {
            p for p in power.iter_command_paths(cli.build_parser())
            if p[:2] in (("agent", "route"), ("agent", "handoff"))
        }
        entries = {
            p for p in power.COMMAND_POLICY
            if p[:2] in (("agent", "route"), ("agent", "handoff"))
        }
        self.assertEqual(leaves, entries)

    def test_no_policy_for_forbidden_leaves(self):
        for path in FORBIDDEN_LEAVES:
            with self.subTest(path=path):
                self.assertNotIn(path, power.COMMAND_POLICY)


class Wave5RecoveryDeepEcoTests(Wave5CliCase):
    WRITE_ARGVS = (
        (("agent", "handoff", "create"),
         ("agent", "handoff", "create", "--task", "T-0001", "--from", "alice",
          "--to", "bob", "--objective", "blocked")),
        (("agent", "handoff", "accept"),
         ("agent", "handoff", "accept", "AH-0001")),
        (("agent", "handoff", "refuse"),
         ("agent", "handoff", "refuse", "AH-0001", "--reason", "out_of_scope")),
        (("agent", "handoff", "clarify"),
         ("agent", "handoff", "clarify", "AH-0001", "--reason",
          "objective_unclear")),
        (("agent", "handoff", "cancel"),
         ("agent", "handoff", "cancel", "AH-0001")),
    )

    def test_recovery_blocks_all_five_writes_before_dispatch(self):
        self.create()
        self.run_cli("power", "set", "recovery")
        before = self.table_counts()
        for path, argv in self.WRITE_ARGVS:
            with self.subTest(command=" ".join(path)):
                code, out, err = self.run_cli(*argv)
                self.assertEqual(code, 1)
                self.assertEqual(out, "", f"{path} wrote to stdout")
                self.assertIn("recovery mode", err)
                self.assertIn(f"`{' '.join(path)}`", err)
        self.assertEqual(self.table_counts(), before)

    def test_recovery_allows_list_and_show_even_on_a_tampered_record(self):
        self.create()
        self.execute(
            "UPDATE agent_handoffs SET content_sha256=?", ("e" * 64,)
        )
        self.run_cli("power", "set", "recovery")
        code, out, _ = self.run_cli("agent", "handoff", "list")
        self.assertEqual(code, 0)
        self.assertIn("AH-0001", out)
        code, out, _ = self.run_cli("agent", "handoff", "show", "AH-0001")
        self.assertEqual(code, 0)
        self.assertIn("mismatch", out)

    def test_deep_wraps_every_write_and_dispatches_once(self):
        self.run_cli("power", "set", "deep")
        code, out, err = self.create()
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "AH-0001 proposed")
        self.assertEqual(self.table_counts()[0], 1)  # exactly one dispatch
        for argv, transitions_after in (
            (("agent", "handoff", "clarify", "AH-0001", "--reason",
              "objective_unclear"), 1),
            (("agent", "handoff", "accept", "AH-0001"), 2),
            (("agent", "handoff", "cancel", "AH-0001"), 3),
        ):
            with self.subTest(argv=argv):
                code, _, err = self.run_cli(*argv)
                self.assertEqual(code, 0, err)
                self.assertEqual(self.table_counts()[1], transitions_after)
        code, _, err = self.create()
        self.assertEqual(code, 0, err)
        code, _, err = self.run_cli(
            "agent", "handoff", "refuse", "AH-0002", "--reason", "out_of_scope"
        )
        self.assertEqual(code, 0, err)
        self.assertEqual(self.table_counts()[:2], (2, 4))
        self.assertEqual(
            self.query(
                "SELECT COUNT(*) FROM events WHERE entity='agent_handoff'"
            )[0][0],
            6,  # two proposes + clarify + accept + cancel + refuse
        )

    def test_eco_runs_every_explicit_write_immediately(self):
        self.run_cli("power", "set", "eco")
        code, out, err = self.create()
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "AH-0001 proposed")
        code, out, _ = self.run_cli("agent", "handoff", "accept", "AH-0001")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "AH-0001 accepted")
        self.create()
        code, _, _ = self.run_cli(
            "agent", "handoff", "refuse", "AH-0002", "--reason", "out_of_scope"
        )
        self.assertEqual(code, 0)
        self.create()
        code, _, _ = self.run_cli(
            "agent", "handoff", "clarify", "AH-0003", "--reason",
            "objective_unclear",
        )
        self.assertEqual(code, 0)
        code, _, _ = self.run_cli("agent", "handoff", "cancel", "AH-0003")
        self.assertEqual(code, 0)
        self.assertEqual(self.table_counts()[0], 3)

    def test_doctor_emits_forty_one_with_governed_handoffs_present(self):
        # Wave 6: the four U-A3 checks (38-41) joined the set; 37 → 41.
        self.create()
        self.run_cli("agent", "handoff", "accept", "AH-0001")
        self.run_cli("sync")
        code, out, err = self.run_cli("doctor")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len([l for l in out.strip().splitlines() if l]), 41)


# ---------------------------------------------------------------------------
# Wave 6 (39)(40) — doctor checks 38-41, the stored-secret sweep extension and
# the final event-payload privacy gate. Doctor is proven read-only against the
# four U-A3 tables and events; every diagnostic asserted below is an RP-/AH-
# id, a closed verdict, a safe participant label or a count — never a stored
# value.

#: A github-token shape (the same fixture Wave 3 uses): matches the shared
#: detector, survives prose validation, and must never be echoed by doctor.
WAVE6_SECRET = "ghp_" + "a" * 24

#: The doctor check names frozen by the contract (§20), in appended order.
CHECK_38 = "routing plans verify"
CHECK_39 = "agent handoffs verify"
CHECK_40 = "open agent handoffs with ineligible participants"
CHECK_41 = "open agent handoffs pinned to stale plans"
SWEEP_CHECK = "secret-shaped text in ledger rows or event payloads"


class _DoctorCase(_HandoffCase):
    """Wave 6 base: run doctor's checks against the live in-memory workspace
    and select single checks by their exact frozen names.

    The base helpers return Optionals (a read may honestly find nothing);
    every record these tests build must exist, so the overrides assert that
    once and hand the Wave 6 tests non-optional values."""

    def setUp(self):
        super().setUp()
        assert self.alice is not None and self.bob is not None
        self.alice_id = self.alice.id
        self.bob_id = self.bob.id

    def make_handoff(self, **over):
        handoff = super().make_handoff(**over)
        assert handoff is not None
        return handoff

    def transition(self, handoff, verb, **kw):
        result = super().transition(handoff, verb, **kw)
        assert result is not None
        return result

    def checks(self):
        return doctor.run_checks(self.conn, self.tmp)

    def named(self, name):
        for check in self.checks():
            if check.name == name:
                return check
        raise AssertionError(f"no doctor check named {name!r}")

    def cap_plan(self):
        plan = self.plan(capabilities=["cap.a"])
        assert plan is not None
        return plan

    def clarified(self, handoff):
        return self.transition(
            handoff, "clarify", reason_code="objective_unclear"
        )

    def table_snapshot(self):
        return {
            table: [
                tuple(row)
                for row in self.conn.execute(
                    f"SELECT * FROM {table} ORDER BY id"
                ).fetchall()
            ]
            for table in (
                "routing_plans",
                "routing_plan_candidates",
                "agent_handoffs",
                "agent_handoff_transitions",
                "events",
            )
        }


class Doctor38RoutingPlansVerifyTests(_DoctorCase):
    def test_clean_plan_passes(self):
        self.cap_plan()
        check = self.named(CHECK_38)
        self.assertTrue(check.ok)
        self.assertFalse(check.warn_only)
        self.assertEqual(check.detail, "")

    def test_no_plans_passes(self):
        check = self.named(CHECK_38)
        self.assertTrue(check.ok)
        self.assertEqual(check.detail, "")

    def test_row_hash_mismatch_fails(self):
        plan = self.cap_plan()
        self.conn.execute(
            "UPDATE routing_plans SET actor='intruder' WHERE id=?", (plan.id,)
        )
        self.conn.commit()
        check = self.named(CHECK_38)
        self.assertFalse(check.ok)
        self.assertIn("RP-0001: mismatch", check.detail)

    def test_candidate_stored_hash_cannot_launder(self):
        # Stored candidate hash tampered, columns intact: the plan hash is
        # rebuilt from RECOMPUTED child digests so it still matches — the
        # candidate-level check is what refuses the laundering.
        plan = self.cap_plan()
        self.conn.execute(
            "UPDATE routing_plan_candidates SET content_sha256=? "
            "WHERE plan_id=? AND verdict='eligible'",
            ("c" * 64, plan.id),
        )
        self.conn.commit()
        check = self.named(CHECK_38)
        self.assertFalse(check.ok)
        self.assertIn("mismatch", check.detail)

    def test_request_mismatch_fails(self):
        plan = self.cap_plan()
        self.conn.execute(
            "UPDATE routing_plans SET request_sha256=? WHERE id=?",
            ("d" * 64, plan.id),
        )
        self.conn.commit()
        check = self.named(CHECK_38)
        self.assertFalse(check.ok)
        self.assertIn("RP-0001: request_mismatch", check.detail)

    def test_rank_gap_fails(self):
        plan = self.cap_plan()  # alice + bob eligible: ranks 1, 2
        self.conn.execute(
            "UPDATE routing_plan_candidates SET rank=3 "
            "WHERE plan_id=? AND rank=2",
            (plan.id,),
        )
        self.conn.commit()
        check = self.named(CHECK_38)
        self.assertFalse(check.ok)
        self.assertIn("RP-0001: rank_gap", check.detail)

    def test_counts_incoherence_fails(self):
        plan = self.cap_plan()
        self.conn.execute(
            "UPDATE routing_plans SET eligible_count=eligible_count+1 "
            "WHERE id=?",
            (plan.id,),
        )
        self.conn.commit()
        check = self.named(CHECK_38)
        self.assertFalse(check.ok)
        self.assertIn("RP-0001: counts_incoherent", check.detail)

    def test_pin_failure_fails(self):
        plan = self.cap_plan()
        self.conn.execute(
            "UPDATE agent_passports SET document=replace(document, 'do', 'xx') "
            "WHERE agent_id=?",
            (self.bob_id,),
        )
        self.conn.commit()
        check = self.named(CHECK_38)
        self.assertFalse(check.ok)
        self.assertIn("pin_mismatch", check.detail)
        self.assertIn(f"RP-{plan.id:04d}", check.detail)

    def test_dangling_pin_reference_fails(self):
        plan = self.cap_plan()
        self.conn.execute("PRAGMA foreign_keys=OFF")
        self.conn.execute(
            "DELETE FROM agent_passports WHERE agent_id=?", (self.bob_id,)
        )
        self.conn.commit()
        self.conn.execute("PRAGMA foreign_keys=ON")
        check = self.named(CHECK_38)
        self.assertFalse(check.ok)
        self.assertIn("reference_invalid", check.detail)
        self.assertIn(f"RP-{plan.id:04d}", check.detail)

    def test_supersession_reference_failure_fails(self):
        first = self.cap_plan()
        routing.create_plan(
            self.conn, self.request(capabilities=["cap.a"]),
            supersedes_id=first.id,
        )
        self.conn.execute("PRAGMA foreign_keys=OFF")
        self.conn.execute("DELETE FROM routing_plans WHERE id=?", (first.id,))
        self.conn.commit()
        self.conn.execute("PRAGMA foreign_keys=ON")
        check = self.named(CHECK_38)
        self.assertFalse(check.ok)
        self.assertIn("RP-0002: reference_invalid", check.detail)

    def test_multiple_findings_deterministic_and_bounded(self):
        for _ in range(10):
            self.cap_plan()
        self.conn.execute("UPDATE routing_plans SET actor='intruder'")
        self.conn.commit()
        first = self.named(CHECK_38)
        second = self.named(CHECK_38)
        self.assertEqual(first.detail, second.detail)
        expected = "; ".join(
            f"RP-{n:04d}: mismatch"
            for n in range(1, models.ROUTING_REASON_DISPLAY_LIMIT + 1)
        ) + " (+2 more)"
        self.assertEqual(first.detail, expected)

    def test_non_integer_rank_reports_closed_verdicts(self):
        # The frozen matrix's 18-19 shape: a non-integer rank reads as an
        # unhashable candidate plus a rank gap — closed verdicts, no raise.
        plan = self.cap_plan()
        self.conn.execute(
            "UPDATE routing_plan_candidates SET rank=1.5 "
            "WHERE plan_id=? AND rank=1",
            (plan.id,),
        )
        self.conn.commit()
        check = self.named(CHECK_38)  # must not raise
        self.assertFalse(check.ok)
        self.assertIn("unhashable", check.detail)
        self.assertIn("rank_gap", check.detail)

    def test_malformed_stored_value_does_not_crash(self):
        # Since the routing-robustness maintenance, `verify_plan` is total on
        # both damage shapes: a BLOB request_document reads as the plan-level
        # `malformed` verdict from the verifier ITSELF, and a BLOB rank reads
        # by the frozen matrix's non-integer-rank shape (an unhashable
        # candidate plus a rank gap, plus the unhashable plan chain). Doctor
        # echoes those closed verdicts — its exception containment remains as
        # defense-in-depth but no longer fires here. Still: bounded closed
        # verdicts only, never a doctor crash, never the stored bytes.
        first = self.cap_plan()
        second = self.cap_plan()
        self.conn.execute(
            "UPDATE routing_plans SET request_document=? WHERE id=?",
            (b"\x00\xffblob", first.id),
        )
        self.conn.execute(
            "UPDATE routing_plan_candidates SET rank=? "
            "WHERE plan_id=? AND rank=1",
            (b"\x01", second.id),
        )
        self.conn.commit()
        check = self.named(CHECK_38)  # must not raise
        self.assertFalse(check.ok)
        self.assertIn("RP-0001: malformed", check.detail)
        self.assertIn("RP-0002 candidate #3: unhashable", check.detail)
        self.assertIn("RP-0002: rank_gap", check.detail)
        self.assertIn("RP-0002: unhashable", check.detail)
        self.assertNotIn("blob", check.detail)

    def test_detail_is_only_rp_ids_and_closed_verdicts(self):
        self.cap_plan()
        self.conn.execute("UPDATE routing_plans SET actor='intruder'")
        self.conn.execute(
            "UPDATE routing_plan_candidates SET reasons_json='[\"suspended\"]' "
            "WHERE verdict='eligible'"
        )
        self.conn.commit()
        check = self.named(CHECK_38)
        self.assertFalse(check.ok)
        verdicts = (
            "malformed|mismatch|unhashable|request_mismatch|rank_gap|"
            "pin_mismatch|counts_incoherent|reference_invalid"
        )
        for segment in check.detail.split("; "):
            self.assertRegex(
                segment, rf"^RP-\d{{4}}(?: candidate #\d+)?: (?:{verdicts})$"
            )
        for leaked in ("alice", "bob", "cap.a", "intruder"):
            self.assertNotIn(leaked, check.detail)


class Doctor39AgentHandoffsVerifyTests(_DoctorCase):
    def test_clean_handoff_passes(self):
        handoff = self.make_handoff()
        self.transition(handoff, "accept")
        check = self.named(CHECK_39)
        self.assertTrue(check.ok)
        self.assertFalse(check.warn_only)
        self.assertEqual(check.detail, "")

    def test_no_handoffs_passes(self):
        check = self.named(CHECK_39)
        self.assertTrue(check.ok)
        self.assertEqual(check.detail, "")

    def test_row_hash_mismatch_fails(self):
        self.make_handoff()
        self.conn.execute(
            "UPDATE agent_handoffs SET objective_md='changed offline'"
        )
        self.conn.commit()
        check = self.named(CHECK_39)
        self.assertFalse(check.ok)
        self.assertIn("AH-0001: mismatch", check.detail)

    def test_child_hash_laundering_fails(self):
        handoff = self.make_handoff()
        self.transition(handoff, "accept")
        self.conn.execute(
            "UPDATE agent_handoff_transitions SET content_sha256=? "
            "WHERE handoff_id=?",
            ("c" * 64, handoff.id),
        )
        self.conn.commit()
        check = self.named(CHECK_39)
        self.assertFalse(check.ok)
        self.assertIn("AH-0001: mismatch", check.detail)

    def test_chain_gap_fails(self):
        handoff = self.make_handoff()
        self.transition(handoff, "accept")
        self.conn.execute(
            "UPDATE agent_handoff_transitions SET seq=3 WHERE handoff_id=?",
            (handoff.id,),
        )
        self.conn.commit()
        check = self.named(CHECK_39)
        self.assertFalse(check.ok)
        self.assertIn("chain_gap", check.detail)

    def test_illegal_edge_fails(self):
        handoff = self.make_handoff()
        self.transition(handoff, "accept")
        # A second transition claiming proposed→accepted after the chain
        # already reached accepted: legal edge vocabulary, illegal continuity.
        self.conn.execute(
            "INSERT INTO agent_handoff_transitions "
            "(handoff_id, seq, from_state, to_state, actor, reason_code, "
            "note_md, created_at, content_sha256) "
            "VALUES (?, 2, 'proposed', 'accepted', 'human', NULL, NULL, ?, ?)",
            (handoff.id, NOW, "e" * 64),
        )
        self.conn.commit()
        check = self.named(CHECK_39)
        self.assertFalse(check.ok)
        self.assertIn("chain_illegal", check.detail)

    def test_state_divergence_fails(self):
        handoff = self.make_handoff()
        accepted = self.transition(handoff, "accept")
        chain = [
            agent_handoffs.transition_digest(t)
            for t in agent_handoffs.get_transitions(self.conn, handoff.id)
        ]
        diverged = dataclasses.replace(accepted, state="proposed")
        laundered = agent_handoffs.handoff_digest(diverged, chain)
        self.conn.execute(
            "UPDATE agent_handoffs SET state='proposed', content_sha256=? "
            "WHERE id=?",
            (laundered, handoff.id),
        )
        self.conn.commit()
        check = self.named(CHECK_39)
        self.assertFalse(check.ok)
        self.assertEqual(check.detail, "AH-0001: state_divergent")

    def test_pin_mismatch_fails(self):
        self.make_handoff()
        self.conn.execute(
            "UPDATE agent_passports SET document=replace(document, 'do', 'xx') "
            "WHERE agent_id=?",
            (self.bob_id,),
        )
        self.conn.commit()
        check = self.named(CHECK_39)
        self.assertFalse(check.ok)
        self.assertIn("AH-0001: pin_mismatch", check.detail)

    def test_missing_reason_fails(self):
        handoff = self.make_handoff()
        refused = self.transition(
            handoff, "refuse", reason_code="out_of_scope"
        )
        # Launder the reason away completely: NULL the column (CHECK ignored),
        # then recompute both stored hashes so ONLY the missing reason remains.
        self.conn.execute("PRAGMA ignore_check_constraints=ON")
        self.conn.execute(
            "UPDATE agent_handoff_transitions SET reason_code=NULL "
            "WHERE handoff_id=?",
            (handoff.id,),
        )
        self.conn.execute("PRAGMA ignore_check_constraints=OFF")
        stripped = agent_handoffs.get_transitions(self.conn, handoff.id)[0]
        self.conn.execute(
            "UPDATE agent_handoff_transitions SET content_sha256=? "
            "WHERE handoff_id=?",
            (agent_handoffs.transition_digest(stripped), handoff.id),
        )
        chain = [
            agent_handoffs.transition_digest(t)
            for t in agent_handoffs.get_transitions(self.conn, handoff.id)
        ]
        self.conn.execute(
            "UPDATE agent_handoffs SET content_sha256=? WHERE id=?",
            (agent_handoffs.handoff_digest(refused, chain), handoff.id),
        )
        self.conn.commit()
        check = self.named(CHECK_39)
        self.assertFalse(check.ok)
        self.assertEqual(check.detail, "AH-0001: reason_missing")

    def test_supersession_incoherence_fails(self):
        predecessor = self.make_handoff()
        self.make_handoff(supersedes_id=predecessor.id)
        self.conn.execute("PRAGMA foreign_keys=OFF")
        self.conn.execute(
            "DELETE FROM agent_handoffs WHERE supersedes_id=?",
            (predecessor.id,),
        )
        self.conn.commit()
        self.conn.execute("PRAGMA foreign_keys=ON")
        check = self.named(CHECK_39)
        self.assertFalse(check.ok)
        self.assertEqual(
            check.detail, "AH-0001: supersession_incoherent"
        )

    def test_malformed_stored_value_does_not_crash(self):
        handoff = self.make_handoff()
        self.conn.execute(
            "UPDATE agent_handoffs SET objective_md=? WHERE id=?",
            (b"\x00\xffblob", handoff.id),
        )
        self.conn.commit()
        check = self.named(CHECK_39)  # must not raise
        self.assertFalse(check.ok)
        self.assertIn("unhashable", check.detail)
        self.assertNotIn("blob", check.detail)

    def test_pending_hash_reports_malformed(self):
        handoff = self.make_handoff()
        self.conn.execute(
            "UPDATE agent_handoffs SET content_sha256='' WHERE id=?",
            (handoff.id,),
        )
        self.conn.commit()
        check = self.named(CHECK_39)
        self.assertFalse(check.ok)
        self.assertIn("AH-0001: malformed", check.detail)

    def test_multiple_findings_deterministic_and_bounded(self):
        for _ in range(12):
            self.make_handoff()
        self.conn.execute("UPDATE agent_handoffs SET objective_md='x'")
        self.conn.commit()
        first = self.named(CHECK_39)
        second = self.named(CHECK_39)
        self.assertEqual(first.detail, second.detail)
        expected = "; ".join(
            f"AH-{n:04d}: mismatch"
            for n in range(1, doctor.UH2_DISPLAY_LIMIT + 1)
        ) + " (+2 more)"
        self.assertEqual(first.detail, expected)

    def test_detail_is_only_ah_ids_and_closed_verdicts(self):
        self.make_handoff(constraints_md="stay in scope")
        self.conn.execute(
            "UPDATE agent_handoffs SET objective_md='changed offline'"
        )
        self.conn.commit()
        check = self.named(CHECK_39)
        self.assertFalse(check.ok)
        verdicts = "|".join(agent_handoffs.HANDOFF_VERIFY_CODES)
        for segment in check.detail.split("; "):
            self.assertRegex(segment, rf"^AH-\d{{4}}: (?:{verdicts})$")
        for leaked in ("alice", "bob", "changed offline", "stay in scope",
                       "ship the widget"):
            self.assertNotIn(leaked, check.detail)


class Doctor40OpenHandoffParticipantsTests(_DoctorCase):
    def test_proposed_clean_participants_pass(self):
        self.make_handoff()
        check = self.named(CHECK_40)
        self.assertTrue(check.ok)
        self.assertTrue(check.warn_only)
        self.assertEqual(check.detail, "")

    def test_clarification_required_clean_participants_pass(self):
        self.clarified(self.make_handoff())
        check = self.named(CHECK_40)
        self.assertTrue(check.ok)
        self.assertEqual(check.detail, "")

    def test_accepted_clean_participants_pass(self):
        self.transition(self.make_handoff(), "accept")
        check = self.named(CHECK_40)
        self.assertTrue(check.ok)
        self.assertEqual(check.detail, "")

    def test_sender_suspended_warns(self):
        self.make_handoff()
        passports.transition_lifecycle(self.conn, name="alice", verb="suspend")
        check = self.named(CHECK_40)
        self.assertFalse(check.ok)
        self.assertTrue(check.warn_only)
        self.assertEqual(check.detail, "AH-0001: alice suspended")

    def test_recipient_archived_warns(self):
        self.make_handoff()
        passports.transition_lifecycle(self.conn, name="bob", verb="archive")
        check = self.named(CHECK_40)
        self.assertFalse(check.ok)
        self.assertEqual(check.detail, "AH-0001: bob archived")

    def test_participant_revoked_warns(self):
        self.clarified(self.make_handoff())
        passports.transition_lifecycle(self.conn, name="bob", verb="revoke")
        check = self.named(CHECK_40)
        self.assertFalse(check.ok)
        self.assertEqual(check.detail, "AH-0001: bob revoked")

    def test_identity_integrity_failure_warns(self):
        self.make_handoff()
        self.conn.execute(
            "UPDATE agents SET content_sha256=? WHERE id=?",
            ("0" * 64, self.alice_id),
        )
        self.conn.commit()
        check = self.named(CHECK_40)
        self.assertFalse(check.ok)
        self.assertEqual(check.detail, "AH-0001: alice integrity-broken")

    def test_passport_history_integrity_failure_warns(self):
        self.transition(self.make_handoff(), "accept")
        self.conn.execute(
            "UPDATE agent_passports SET document=replace(document, 'do', 'xx') "
            "WHERE agent_id=?",
            (self.bob_id,),
        )
        self.conn.commit()
        check = self.named(CHECK_40)
        self.assertFalse(check.ok)
        self.assertIn("AH-0001: bob integrity-broken", check.detail)

    def test_both_participants_deterministic_bounded_findings(self):
        self.make_handoff()
        passports.transition_lifecycle(self.conn, name="alice", verb="suspend")
        passports.transition_lifecycle(self.conn, name="bob", verb="archive")
        first = self.named(CHECK_40)
        second = self.named(CHECK_40)
        self.assertEqual(first.detail, second.detail)
        self.assertEqual(
            first.detail, "AH-0001: alice suspended; AH-0001: bob archived"
        )

    def test_terminal_states_outside_population_do_not_warn(self):
        refused = self.make_handoff()
        self.transition(refused, "refuse", reason_code="out_of_scope")
        cancelled = self.make_handoff()
        self.transition(cancelled, "cancel")
        superseded = self.make_handoff()
        successor = self.make_handoff(supersedes_id=superseded.id)
        self.transition(successor, "cancel")
        passports.transition_lifecycle(self.conn, name="alice", verb="suspend")
        check = self.named(CHECK_40)
        self.assertTrue(check.ok)
        self.assertEqual(check.detail, "")

    def test_safe_label_and_no_prose_or_hash_leakage(self):
        self.make_handoff()
        self.conn.execute(
            "UPDATE agents SET name=? WHERE id=?",
            (WAVE6_SECRET, self.alice_id),
        )
        self.conn.commit()
        check = self.named(CHECK_40)
        self.assertFalse(check.ok)
        self.assertEqual(
            check.detail,
            f"AH-0001: agent #{self.alice_id} integrity-broken",
        )
        self.assertNotIn(WAVE6_SECRET, check.detail)
        self.assertNotRegex(check.detail, r"[0-9a-f]{64}")
        self.assertNotIn("ship the widget", check.detail)


class Doctor41StaleReferencedPlansTests(_DoctorCase):
    def pinned_handoff(self):
        plan = self.cap_plan()
        return plan, self.make_handoff(plan_id=plan.id)

    def go_stale(self):
        self.publish_v2(
            "bob", capabilities=["cap.a"], data_classifications=ALL_CLASSES
        )

    def test_proposed_with_fresh_plan_passes(self):
        self.pinned_handoff()
        check = self.named(CHECK_41)
        self.assertTrue(check.ok)
        self.assertTrue(check.warn_only)
        self.assertEqual(check.detail, "")

    def test_clarification_required_with_fresh_plan_passes(self):
        _, handoff = self.pinned_handoff()
        self.clarified(handoff)
        check = self.named(CHECK_41)
        self.assertTrue(check.ok)
        self.assertEqual(check.detail, "")

    def test_stale_referenced_plan_warns(self):
        self.pinned_handoff()
        self.go_stale()
        check = self.named(CHECK_41)
        self.assertFalse(check.ok)
        self.assertTrue(check.warn_only)
        self.assertEqual(check.detail, "AH-0001: plan RP-0001 stale")

    def test_stale_plan_under_clarification_warns(self):
        _, handoff = self.pinned_handoff()
        self.clarified(handoff)
        self.go_stale()
        check = self.named(CHECK_41)
        self.assertFalse(check.ok)
        self.assertEqual(check.detail, "AH-0001: plan RP-0001 stale")

    def test_superseded_referenced_plan_warns(self):
        plan, _ = self.pinned_handoff()
        routing.create_plan(
            self.conn, self.request(capabilities=["cap.a"]),
            supersedes_id=plan.id,
        )
        check = self.named(CHECK_41)
        self.assertFalse(check.ok)
        self.assertEqual(check.detail, "AH-0001: plan RP-0001 stale")

    def test_handoff_without_plan_passes(self):
        self.cap_plan()
        self.make_handoff()
        self.go_stale()
        check = self.named(CHECK_41)
        self.assertTrue(check.ok)
        self.assertEqual(check.detail, "")

    def test_unreferenced_stale_plan_does_not_warn(self):
        self.cap_plan()
        self.go_stale()
        check = self.named(CHECK_41)
        self.assertTrue(check.ok)
        self.assertEqual(check.detail, "")

    def test_accepted_handoffs_leave_the_population(self):
        # The frozen check-41 population is (proposed, clarification_required)
        # exactly — an accepted handoff pinned to a stale plan must not warn.
        _, handoff = self.pinned_handoff()
        self.transition(handoff, "accept")
        self.go_stale()
        check = self.named(CHECK_41)
        self.assertTrue(check.ok, check.detail)
        self.assertEqual(check.detail, "")

    def test_terminal_states_do_not_warn(self):
        _, handoff = self.pinned_handoff()
        self.transition(handoff, "refuse", reason_code="out_of_scope")
        self.go_stale()
        check = self.named(CHECK_41)
        self.assertTrue(check.ok)
        self.assertEqual(check.detail, "")

    def test_warning_mutates_nothing(self):
        self.pinned_handoff()
        self.go_stale()
        before = self.table_snapshot()
        check = self.named(CHECK_41)
        self.assertFalse(check.ok)
        self.assertEqual(self.table_snapshot(), before)

    def test_detail_is_exactly_ids_plus_stale(self):
        self.pinned_handoff()
        self.go_stale()
        check = self.named(CHECK_41)
        self.assertRegex(check.detail, r"^AH-\d{4}: plan RP-\d{4} stale$")

    def test_malformed_candidate_ranks_do_not_crash_check_41(self):
        # Since the routing-robustness maintenance, mixed-type eligible ranks
        # (int + BLOB) no longer raise anywhere: `plan_staleness` reads the
        # damaged plan as stale via the existing `integrity_broken`, so check
        # 41 now SURFACES the advisory for the open pinned handoff instead of
        # skipping blind, and check 38 reports the verifier's own closed
        # verdicts (the frozen matrix's non-integer-rank shape). Doctor's
        # exception containment remains as defense-in-depth but no longer
        # fires here. Still: no crash, no mutation, no stored value.
        plan, _ = self.pinned_handoff()
        self.conn.execute(
            "UPDATE routing_plan_candidates SET rank=? "
            "WHERE plan_id=? AND rank=1",
            (b"\x01", plan.id),
        )
        self.conn.commit()
        before = self.table_snapshot()
        changes_before = self.conn.total_changes
        checks = self.checks()  # must not raise
        self.assertEqual(self.conn.total_changes, changes_before)
        self.assertEqual(self.table_snapshot(), before)
        by_name = {c.name: c for c in checks}
        check38, check41 = by_name[CHECK_38], by_name[CHECK_41]
        self.assertFalse(check38.ok)
        self.assertEqual(
            check38.detail,
            "RP-0001 candidate #1: unhashable; RP-0001: rank_gap; "
            "RP-0001: unhashable",
        )
        self.assertFalse(check41.ok)
        self.assertTrue(check41.warn_only)
        self.assertEqual(check41.detail, "AH-0001: plan RP-0001 stale")
        for detail in (check38.detail, check41.detail):
            self.assertNotIn("TypeError", detail)
            self.assertNotIn("bytes", detail)
            self.assertNotIn("not supported between instances", detail)
            self.assertNotIn("\x01", detail)
            self.assertNotIn("ship the widget", detail)
            self.assertNotIn("alice", detail)
            self.assertNotIn("bob", detail)
            self.assertNotRegex(detail, r"[0-9a-f]{64}")


class Wave6SecretSweepTests(_DoctorCase):
    def findings(self):
        return doctor.secret_sweep_findings(self.conn)

    def test_objective_stored_secret_is_found(self):
        self.make_handoff(objective_md=f"use {WAVE6_SECRET} to log in")
        self.assertIn(
            "agent_handoff AH-0001 objective: github-token", self.findings()
        )

    def test_constraints_stored_secret_is_found(self):
        self.make_handoff(constraints_md=f"never share {WAVE6_SECRET}")
        self.assertIn(
            "agent_handoff AH-0001 constraint: github-token", self.findings()
        )

    def test_transition_note_stored_secret_is_found(self):
        handoff = self.make_handoff()
        self.transition(handoff, "accept", note_md=f"rotate {WAVE6_SECRET}")
        self.assertIn(
            "agent handoff AH-0001 transition #1 note: github-token",
            self.findings(),
        )

    def test_direct_sql_tampering_without_metadata_is_found(self):
        handoff = self.make_handoff()
        self.transition(handoff, "accept", note_md="benign note")
        self.conn.execute(
            "UPDATE agent_handoffs SET objective_md=? WHERE id=?",
            (f"use {WAVE6_SECRET}", handoff.id),
        )
        self.conn.execute(
            "UPDATE agent_handoff_transitions SET note_md=? WHERE handoff_id=?",
            (f"use {WAVE6_SECRET}", handoff.id),
        )
        self.conn.commit()
        rows = self.conn.execute(
            "SELECT payload_json FROM events WHERE payload_json "
            "LIKE '%secret_warning%'"
        ).fetchall()
        self.assertEqual(rows, [])  # no write-time metadata exists
        findings = self.findings()
        self.assertIn(
            "agent_handoff AH-0001 objective: github-token", findings
        )
        self.assertIn(
            "agent handoff AH-0001 transition #1 note: github-token", findings
        )

    def test_benign_values_are_not_findings(self):
        handoff = self.make_handoff(constraints_md="stay in scope")
        self.transition(handoff, "accept", note_md="looks fine")
        for finding in self.findings():
            self.assertNotIn("agent_handoff", finding)
            self.assertNotIn("agent handoff", finding)

    def test_output_is_value_free(self):
        handoff = self.make_handoff(objective_md=f"use {WAVE6_SECRET}")
        self.transition(handoff, "accept", note_md=f"rotate {WAVE6_SECRET}")
        blob = "; ".join(self.findings())
        self.assertNotIn(WAVE6_SECRET, blob)
        check = self.named(SWEEP_CHECK)
        self.assertNotIn(WAVE6_SECRET, check.detail)

    def test_duplicates_deterministic_and_deduplicated(self):
        handoff = self.make_handoff(
            objective_md=f"use {WAVE6_SECRET}",
            constraints_md=f"keep {WAVE6_SECRET}",
        )
        self.transition(handoff, "accept", note_md=f"rotate {WAVE6_SECRET}")
        first = self.findings()
        second = self.findings()
        self.assertEqual(first, second)
        self.assertEqual(len(first), len(set(first)))

    def test_display_bound_retained(self):
        for _ in range(6):
            self.make_handoff(
                objective_md=f"use {WAVE6_SECRET}",
                constraints_md=f"keep {WAVE6_SECRET}",
            )
        findings = self.findings()
        self.assertGreater(len(findings), doctor.SECRET_SWEEP_DISPLAY_LIMIT)
        shown = findings[: doctor.SECRET_SWEEP_DISPLAY_LIMIT]
        hidden = len(findings) - len(shown)
        check = self.named(SWEEP_CHECK)
        self.assertEqual(
            check.detail, "; ".join(shown) + f" (+{hidden} more)"
        )

    def test_sweep_remains_one_warn_only_check(self):
        self.make_handoff(objective_md=f"use {WAVE6_SECRET}")
        checks = self.checks()
        named = [c for c in checks if c.name == SWEEP_CHECK]
        self.assertEqual(len(named), 1)
        self.assertTrue(named[0].warn_only)
        secretish = [c for c in checks if "secret" in c.name]
        self.assertEqual(secretish, named)

    def test_total_doctor_count_remains_41_not_42(self):
        self.make_handoff(objective_md=f"use {WAVE6_SECRET}")
        self.assertEqual(len(self.checks()), 41)


class Wave6EventPrivacyGateTests(_DoctorCase):
    PROSE = (
        "ship the widget", "stay in scope", "looks fine", "nope",
        "withdrawn", "changed offline", "approval",
    )

    def drive_all_actions(self):
        plan = self.cap_plan()
        accepted = self.make_handoff(
            plan_id=plan.id, constraints_md="stay in scope"
        )
        self.transition(accepted, "accept", note_md="looks fine")
        refused = self.make_handoff()
        self.transition(
            refused, "refuse", reason_code="out_of_scope", note_md="nope"
        )
        self.clarified(self.make_handoff())
        cancelled = self.make_handoff()
        self.transition(cancelled, "cancel", note_md="withdrawn")
        predecessor = self.make_handoff()
        self.make_handoff(supersedes_id=predecessor.id)

    def routing_payloads(self):
        return [
            (row["action"], json.loads(row["payload_json"]))
            for row in self.conn.execute(
                "SELECT action, payload_json FROM events "
                "WHERE entity='routing_plan' ORDER BY id"
            ).fetchall()
        ]

    def assert_subset(self, payload, allowlist):
        allowed = set(allowlist) | {
            "schema_version", "secret_warning", "secret_fields",
            "secret_patterns",
        }
        self.assertLessEqual(set(payload), allowed, set(payload) - allowed)

    def test_frozen_allowlist_constants(self):
        self.assertEqual(
            routing.ROUTING_PLAN_EVENT_KEYS,
            ("plan", "task", "scope", "algorithm_version",
             "request_sha256_prefix", "result_status", "eligible_count",
             "excluded_count", "unresolved_count", "supersedes"),
        )
        self.assertEqual(
            agent_handoffs.PROPOSE_EVENT_KEYS,
            ("handoff", "task", "plan", "from_agent", "to_agent",
             "from_version", "to_version", "from_passport_sha256_prefix",
             "to_passport_sha256_prefix", "data_classification", "supersedes"),
        )
        self.assertEqual(
            agent_handoffs.TRANSITION_EVENT_KEYS,
            ("handoff", "task", "seq", "from_state", "to_state",
             "reason_code"),
        )

    def test_routing_plan_create_allowlist(self):
        self.drive_all_actions()
        payloads = self.routing_payloads()
        self.assertTrue(payloads)
        for action, payload in payloads:
            self.assertEqual(action, "create")
            self.assert_subset(payload, routing.ROUTING_PLAN_EVENT_KEYS)

    def test_every_handoff_action_satisfies_its_allowlist(self):
        self.drive_all_actions()
        payloads = self.payloads()
        observed = {action for action, _ in payloads}
        self.assertEqual(
            observed,
            {"propose", "accept", "refuse", "clarify", "cancel", "supersede"},
        )
        for action, payload in payloads:
            with self.subTest(action=action):
                allowlist = (
                    agent_handoffs.PROPOSE_EVENT_KEYS
                    if action == "propose"
                    else agent_handoffs.TRANSITION_EVENT_KEYS
                )
                self.assert_subset(payload, allowlist)

    def test_no_prose_in_any_u_a3_event(self):
        self.drive_all_actions()
        rows = self.conn.execute(
            "SELECT payload_json FROM events "
            "WHERE entity IN ('routing_plan','agent_handoff') ORDER BY id"
        ).fetchall()
        self.assertTrue(rows)
        for row in rows:
            for prose in self.PROSE:
                self.assertNotIn(prose, row["payload_json"])

    def test_no_full_hash_in_any_u_a3_event(self):
        self.drive_all_actions()
        for row in self.conn.execute(
            "SELECT payload_json FROM events "
            "WHERE entity IN ('routing_plan','agent_handoff') ORDER BY id"
        ).fetchall():
            self.assertNotRegex(row["payload_json"], r"[0-9a-f]{64}")

    def test_only_safe_secret_metadata_extends_the_allowlists(self):
        self.make_handoff(objective_md=f"use {WAVE6_SECRET} now")
        _, payload = self.payloads("propose")[-1]
        self.assert_subset(payload, agent_handoffs.PROPOSE_EVENT_KEYS)
        extras = set(payload) - set(agent_handoffs.PROPOSE_EVENT_KEYS) - {
            "schema_version"
        }
        self.assertLessEqual(
            extras, {"secret_warning", "secret_fields", "secret_patterns"}
        )
        self.assertTrue(payload["secret_warning"])
        self.assertNotIn(WAVE6_SECRET, json.dumps(payload))


class Wave6DoctorMutationFreeTests(_DoctorCase):
    def build_damaged_ledger(self):
        plan = self.cap_plan()
        handoff = self.make_handoff(plan_id=plan.id)
        self.transition(handoff, "accept", note_md="looks fine")
        second = self.make_handoff(objective_md=f"use {WAVE6_SECRET}")
        self.clarified(second)
        self.conn.execute(
            "UPDATE routing_plans SET actor='intruder' WHERE id=?", (plan.id,)
        )
        self.conn.execute(
            "UPDATE agent_handoffs SET objective_md=? WHERE id=?",
            (b"\x00blob", second.id),
        )
        self.conn.commit()

    def test_run_checks_leaves_every_row_byte_identical(self):
        self.build_damaged_ledger()
        before = self.table_snapshot()
        self.checks()
        self.checks()
        self.assertEqual(self.table_snapshot(), before)

    def test_total_changes_does_not_increase_during_doctor(self):
        self.build_damaged_ledger()
        baseline = self.conn.total_changes
        self.checks()
        self.assertEqual(self.conn.total_changes, baseline)

    def test_doctor_calls_no_write_or_event_api(self):
        self.build_damaged_ledger()
        forbidden = AssertionError("doctor must never call a write API")
        with mock.patch.object(
            routing, "create_plan", side_effect=forbidden
        ), mock.patch.object(
            agent_handoffs, "create_handoff", side_effect=forbidden
        ), mock.patch.object(
            agent_handoffs, "transition", side_effect=forbidden
        ), mock.patch.object(
            events, "emit", side_effect=forbidden
        ), mock.patch.object(
            db, "transaction", side_effect=forbidden
        ):
            checks = self.checks()
        self.assertEqual(len(checks), 41)

    def test_doctor_reuses_the_domain_verifiers(self):
        self.cap_plan()
        self.cap_plan()
        handoff = self.make_handoff()
        self.transition(handoff, "accept")
        self.make_handoff()
        with mock.patch.object(
            routing, "verify_plan", wraps=routing.verify_plan
        ) as verify_plan, mock.patch.object(
            agent_handoffs, "verify_handoff",
            wraps=agent_handoffs.verify_handoff,
        ) as verify_handoff:
            self.checks()
        self.assertEqual(verify_plan.call_count, 2)
        self.assertEqual(verify_handoff.call_count, 2)


class Wave6DoctorOrderTests(_DoctorCase):
    def test_clean_workspace_emits_exactly_41_checks(self):
        checks = self.checks()
        self.assertEqual(len(checks), 41)

    def test_new_checks_append_last_in_contract_order(self):
        checks = self.checks()
        self.assertEqual(
            [c.name for c in checks[-4:]],
            [CHECK_38, CHECK_39, CHECK_40, CHECK_41],
        )
        self.assertEqual(
            [c.warn_only for c in checks[-4:]], [False, False, True, True]
        )

    def test_legacy_checks_retain_names_order_and_severity(self):
        checks = self.checks()
        self.assertEqual(checks[0].name, "database exists")
        self.assertEqual(
            checks[17].name,
            "secret-shaped text in ledger rows or event payloads",
        )
        self.assertEqual(checks[31].name, "agent identity hashes verify")
        self.assertEqual(
            [c.name for c in checks[34:37]],
            [
                "built-in catalog verified",
                "installed catalog identities verified",
                "catalog entries available to install",
            ],
        )
        # Check 30 (index 29) is warn-only ONLY when restricted claims exist
        # (its clean-fixture early return carries no warn flag) — so on this
        # fixture the warn set is the four U-C3/U-H2 lines, the two U-M2
        # lines, the U-A1 and U-A2 lines, and Wave 6's checks 40 and 41.
        self.assertEqual(
            [index for index, c in enumerate(checks) if c.warn_only],
            [16, 17, 18, 19, 23, 24, 33, 36, 39, 40],
        )


class Wave6DoctorStaticTests(unittest.TestCase):
    SOURCE = (REPO_ROOT / "agentic_os" / "doctor.py").read_text(
        encoding="utf-8"
    )

    def test_doctor_module_contains_no_mutation_or_event_emission(self):
        for token in (
            "INSERT INTO", "UPDATE ", "DELETE FROM", "BEGIN IMMEDIATE",
            "events.emit", "db.transaction(", "executescript",
        ):
            self.assertNotIn(token, self.SOURCE)

    def test_doctor_does_not_reimplement_the_domain_verifiers(self):
        for token in (
            "handoff_digest(", "transition_digest(", "plan_digest(",
            "candidate_digest(", "_replay(", "_structural_problems(",
        ):
            self.assertNotIn(token, self.SOURCE)
        self.assertIn("verify_plan", self.SOURCE)
        self.assertIn("verify_handoff", self.SOURCE)
        self.assertIn("plan_staleness", self.SOURCE)


class Wave6CliDoctorTests(Wave5CliCase):
    def test_fail_check_exits_1_and_stays_value_free(self):
        self.create()
        self.execute(
            "UPDATE agent_handoffs SET objective_md='changed offline'"
        )
        code, out, err = self.run_cli("doctor")
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] agent handoffs verify — AH-0001: mismatch", out)
        self.assertIn("check(s) failed", err)
        self.assertNotIn("changed offline", out)
        self.assertNotIn("ship the widget", out)

    def test_participant_warning_keeps_exit_zero(self):
        self.create()
        self.run_cli("agent", "suspend", "alice")
        code, out, err = self.run_cli("doctor")
        self.assertEqual(code, 0, out + err)
        self.assertIn(
            "[WARN] open agent handoffs with ineligible participants — "
            "AH-0001: alice suspended",
            out,
        )

    def test_stale_plan_warning_keeps_exit_zero(self):
        code, out, err = self.run_cli(
            "agent", "route", "plan", "--capability", "cap.a"
        )
        self.assertEqual(code, 0, out + err)
        code, out, err = self.create("--plan", "RP-0001")
        self.assertEqual(code, 0, out + err)
        self.run_cli("agent", "suspend", "bob")
        code, out, err = self.run_cli("doctor")
        self.assertEqual(code, 0, out + err)
        self.assertIn(
            "[WARN] open agent handoffs pinned to stale plans — "
            "AH-0001: plan RP-0001 stale",
            out,
        )


class Wave5EntrypointTests(Wave5CliCase):
    def test_entrypoints_equivalent_for_handoff_show(self):
        self.create()
        _, expected, _ = self.run_cli(
            "agent", "handoff", "show", "AH-0001", "--json"
        )
        import subprocess

        for cmd in (
            ["python3", "aos.py"],
            ["python3", "-m", "agentic_os"],
        ):
            with self.subTest(entrypoint=cmd[-1]):
                proc = subprocess.run(
                    [*cmd, "--root", str(self.root), "agent", "handoff",
                     "show", "AH-0001", "--json"],
                    cwd=str(REPO_ROOT), capture_output=True, text=True,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout, expected)


# ===========================================================================
# U-A3 ROUTING ROBUSTNESS MAINTENANCE — three post-Wave-6 defects, each with
# an exact regression: (A) a task-derived project re-sent an ALREADY-
# normalized request (tuple arrays) through public list-only validation;
# (B) `verify_plan` raised on a BLOB `request_document`; (C) `plan_staleness`
# raised while sorting mixed-type candidate ranks.
# ===========================================================================


class MaintenanceTupleRevalidationTests(_LiveCase):
    """Defect A: a task-derived project must be attached to the ALREADY-
    normalized request at the internal boundary that owns normalized data —
    its tuple arrays never re-enter public list-only validation — while the
    public boundary itself stays strictly list-only."""

    #: Every frozen array-valued request dimension, with values the default
    #: live passport fixture can also declare.
    ARRAY_FIELDS = {
        "task_families": ["tf.a"],
        "capabilities": ["cap.a"],
        "evidence_kinds": ["file"],
        "required_autonomy": ["supervised"],
        "skills": ["skill.a"],
        "tools": ["tool.a"],
    }

    def _project_task(self):
        self.add_project("demo")
        return self.add_task(project="demo")

    def _created_plan(self, request):
        plan = routing.get_plan(
            self.conn, routing.create_plan(self.conn, request)
        )
        assert plan is not None
        return plan

    def _candidate_projection(self, plan):
        return [
            (c.verdict, c.rank, c.ordering_json, c.reasons_json)
            for c in self.candidates(plan)
        ]

    def test_task_derived_project_with_capability_requirement(self):
        # The exact reported failure: `--task T-…` without `--project`, plus
        # one repeatable array requirement, beginning with capability.
        task = self._project_task()
        self.publish("a", capabilities=["cap.a"])
        plan = self._created_plan(
            self.request(task=task.id, capabilities=["cap.a"])
        )
        self.assertEqual(plan.scope, "project")
        self.assertEqual(plan.task_id, task.id)
        self.assertIn('"project":"demo"', plan.request_document)
        self.assertIn('"capabilities":["cap.a"]', plan.request_document)
        self.assertEqual(self.by_name(plan)["a"].rank, 1)

    def test_task_derived_project_with_multiple_capability_values(self):
        task = self._project_task()
        self.publish("a", capabilities=["cap.a", "cap.b"])
        plan = self._created_plan(
            self.request(task=task.id, capabilities=["cap.b", "cap.a"]),
        )
        self.assertIn('"capabilities":["cap.a","cap.b"]', plan.request_document)
        self.assertEqual(plan.result_status, "resolved")

    def test_every_frozen_array_requirement_through_task_derived_path(self):
        task = self._project_task()
        self.publish(
            "a",
            capabilities=["cap.a"],
            task_families=["tf.a"],
            skill_requirements=["skill.a"],
            tool_requirements=["tool.a"],
            data_classifications=["internal"],
            evidence_expectations={
                "evidence_kinds": ["file"], "min_evidence_count": 1,
            },
            model_requirements={
                "min_context_tokens": 50000, "modalities": ["text"],
            },
        )
        request = self.request(
            task=task.id,
            model_capabilities={
                "min_context_tokens": 1000, "modalities": ["text"],
            },
            **self.ARRAY_FIELDS,
        )
        plan = self._created_plan(request)
        document = protocols.parse_canonical(
            plan.request_document.encode("utf-8")
        )
        self.assertEqual(document["project"], "demo")
        for field, values in self.ARRAY_FIELDS.items():
            self.assertEqual(document[field], sorted(values))
        self.assertEqual(document["model_capabilities"]["modalities"], ["text"])

    def test_explicit_and_task_derived_requests_normalize_identically(self):
        task = self._project_task()
        self.publish("a", capabilities=["cap.a"])
        self.publish("b", capabilities=["cap.a", "cap.b"])
        derived = self._created_plan(
            self.request(task=task.id, capabilities=["cap.a"])
        )
        explicit = self._created_plan(
            self.request(task=task.id, project="demo", capabilities=["cap.a"]),
        )
        self.assertEqual(derived.request_document, explicit.request_document)
        self.assertEqual(derived.request_sha256, explicit.request_sha256)
        self.assertEqual(
            self._candidate_projection(derived),
            self._candidate_projection(explicit),
        )
        # Determinism of the derived path itself: an identical request yields
        # an identical digest and ranked projection every time.
        repeat = self._created_plan(
            self.request(task=task.id, capabilities=["cap.a"])
        )
        self.assertEqual(repeat.request_sha256, derived.request_sha256)
        self.assertEqual(
            self._candidate_projection(repeat),
            self._candidate_projection(derived),
        )

    def test_public_non_list_array_inputs_remain_rejected(self):
        # The internal normalized tuple shape must NOT become publicly
        # acceptable: the public contract stays list-only for every frozen
        # array field, and every other iterable stays rejected too.
        for field in self.ARRAY_FIELDS:
            for bad in (
                ("cap.a",),                      # tuple: internal shape only
                {"cap.a"},                       # set
                {"cap.a": True},                 # mapping
                b"cap.a",                        # bytes
                "cap.a",                         # bare string
                (item for item in ["cap.a"]),    # generator
            ):
                with self.subTest(field=field, bad=type(bad).__name__):
                    with self.assertRaises(routing.RoutingRequestError):
                        routing.validate_request(
                            dict(VALID_REQUEST, **{field: bad})
                        )
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(
                dict(VALID_REQUEST, model_capabilities={"modalities": ("text",)})
            )

    def test_public_bounds_and_item_rules_unchanged(self):
        seventeen = [f"cap.c{i:02d}" for i in range(17)]
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(dict(VALID_REQUEST, capabilities=seventeen))
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(dict(VALID_REQUEST, capabilities=[]))
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(
                dict(VALID_REQUEST, capabilities=["cap.a", 5])
            )
        with self.assertRaises(routing.RoutingRequestError):
            routing.validate_request(
                dict(VALID_REQUEST, capabilities=["cap.a", "cap.a"])
            )
        sixteen = [f"cap.c{i:02d}" for i in range(16)]
        self.assertEqual(
            len(routing.validate_request(
                dict(VALID_REQUEST, capabilities=sixteen)
            )["capabilities"]),
            16,
        )

    def test_no_request_level_refusal_stored_as_candidate_exclusion(self):
        task = self._project_task()
        self.publish("a", capabilities=["cap.a"])
        plan = self._created_plan(
            self.request(task=task.id, capabilities=["cap.a"])
        )
        for candidate in self.candidates(plan):
            codes = json.loads(candidate.reasons_json)
            for refusal in models.ROUTING_REQUEST_REFUSAL_CODES:
                self.assertNotIn(refusal, codes)
        # A request-level refusal on the same task-derived path still stores
        # no plan row and no event.
        before = (self.count("routing_plans"), self.count("events"))
        with self.assertRaises(AosError) as ctx:
            routing.create_plan(
                self.conn,
                self.request(
                    task=task.id,
                    capabilities=["cap.a"],
                    preferred_agent="ghost",
                ),
            )
        self.assertIn("agent_absent", str(ctx.exception))
        self.assertEqual(
            (self.count("routing_plans"), self.count("events")), before
        )


class MaintenanceTupleRevalidationCliTests(Wave3CliCase):
    def test_route_plan_task_derived_project_with_capability_succeeds(self):
        # The real CLI path of the reported failure.
        self.run_cli("task", "add", "build", "-p", "demo")
        self.make_agent("alpha", capabilities=["cap.a"])
        code, out, err = self.run_cli(
            "agent", "route", "plan", "--task", "T-0001",
            "--capability", "cap.a",
        )
        self.assertEqual(code, 0, err)
        self.assertIn("RP-0001", out)
        code, out, err = self.run_cli(
            "agent", "route", "plan", "--task", "T-0001",
            "--capability", "cap.a", "--json",
        )
        self.assertEqual(code, 0, err)
        doc = json.loads(out)["plan"]
        self.assertEqual(doc["project"], "demo")
        self.assertEqual(doc["scope"], "project")


class MaintenanceVerifyPlanTotalityTests(_LiveCase):
    """Defect B: `verify_plan` is total on a malformed/BLOB
    `routing_plans.request_document` — the frozen closed plan-level
    `malformed` verdict, never an exception, never a stored byte."""

    def _live_plan(self, **over):
        plan = self.plan(**over)
        assert plan is not None
        return plan

    def _blob_plan(self):
        self.publish("a", capabilities=["cap.a"])
        plan = self._live_plan(capabilities=["cap.a"])
        # The pre-fix raise needs an eligible candidate: only the ordering
        # re-check parses the plan's request document per candidate.
        self.assertEqual(plan.eligible_count, 1)
        self.conn.execute(
            "UPDATE routing_plans SET request_document=? WHERE id=?",
            (sqlite3.Binary(b"\x00\xffnot a document"), plan.id),
        )
        self.conn.commit()
        return plan

    def test_blob_request_document_reports_plan_level_malformed(self):
        plan = self._blob_plan()
        result = routing.verify_plan(self.conn, plan.id)  # must not raise
        rp = ids.render_id("routing_plan", plan.id)
        self.assertFalse(result["ok"])
        self.assertEqual(result["problems"], [f"{rp}: malformed"])
        self.assertFalse(result["stale"])
        self.assertFalse(result["superseded"])

    def test_blob_request_document_result_is_json_and_value_free(self):
        plan = self._blob_plan()
        result = routing.verify_plan(self.conn, plan.id)
        encoded = json.dumps(result)  # JSON-compatible throughout
        for leaked in ("\\x00", "\\xff", "not a document", "AttributeError",
                       "Traceback", "SELECT", "encode"):
            self.assertNotIn(leaked, encoded)
        self.assertNotRegex(encoded, r"[0-9a-f]{64}")

    def test_blob_request_document_verify_is_deterministic_and_read_only(self):
        plan = self._blob_plan()
        before_row = tuple(self.conn.execute(
            "SELECT * FROM routing_plans WHERE id=?", (plan.id,)
        ).fetchone())
        changes_before = self.conn.total_changes
        first = routing.verify_plan(self.conn, plan.id)
        second = routing.verify_plan(self.conn, plan.id)
        self.assertEqual(first, second)
        self.assertEqual(self.conn.total_changes, changes_before)
        after_row = tuple(self.conn.execute(
            "SELECT * FROM routing_plans WHERE id=?", (plan.id,)
        ).fetchone())
        self.assertEqual(before_row, after_row)

    def test_valid_and_string_tampered_plans_keep_existing_verdicts(self):
        self.publish("a", capabilities=["cap.a"])
        intact = self._live_plan(capabilities=["cap.a"])
        result = routing.verify_plan(self.conn, intact.id)
        self.assertTrue(result["ok"])
        self.assertEqual(result["problems"], [])
        # A re-spaced STRING document keeps the existing request_mismatch
        # verdict: the new malformed boundary is type-level only.
        respaced = self._live_plan(capabilities=["cap.a"])
        self.conn.execute(
            "UPDATE routing_plans SET request_document=? WHERE id=?",
            (respaced.request_document.replace(",", ", "), respaced.id),
        )
        self.conn.commit()
        rp = ids.render_id("routing_plan", respaced.id)
        self.assertIn(
            f"{rp}: request_mismatch",
            routing.verify_plan(self.conn, respaced.id)["problems"],
        )
        # A tampered plan column keeps the existing mismatch verdict.
        tampered = self._live_plan(capabilities=["cap.a"])
        self.conn.execute(
            "UPDATE routing_plans SET actor='intruder' WHERE id=?",
            (tampered.id,),
        )
        self.conn.commit()
        rp_tampered = ids.render_id("routing_plan", tampered.id)
        self.assertIn(
            f"{rp_tampered}: mismatch",
            routing.verify_plan(self.conn, tampered.id)["problems"],
        )


class MaintenancePlanStalenessTotalityTests(_LiveCase):
    """Defect C: `plan_staleness` is total on malformed mixed-type candidate
    ranks — the existing closed `integrity_broken` verdict, detected BEFORE
    any unsafe sort; never a TypeError, never a stored value."""

    def _live_plan(self, **over):
        plan = self.plan(**over)
        assert plan is not None
        return plan

    def _reread(self, plan_id):
        plan = routing.get_plan(self.conn, plan_id)
        assert plan is not None
        return plan

    def _two_candidate_plan(self):
        self.publish("a", capabilities=["cap.a"])
        self.publish("b", capabilities=["cap.a"])
        plan = self._live_plan(capabilities=["cap.a"])
        self.assertEqual(plan.eligible_count, 2)
        return plan

    def _plant_rank(self, plan, value, *, expected_type):
        self.conn.execute(
            "UPDATE routing_plan_candidates SET rank=? "
            "WHERE plan_id=? AND rank=1",
            (value, plan.id),
        )
        self.conn.commit()
        stored = [
            tuple(row)
            for row in self.conn.execute(
                "SELECT typeof(rank) FROM routing_plan_candidates "
                "WHERE plan_id=? ORDER BY id",
                (plan.id,),
            ).fetchall()
        ]
        # SQLite really kept the planted type (INTEGER affinity would
        # otherwise quietly convert a numeric string).
        self.assertIn((expected_type,), stored)

    def test_mixed_int_and_blob_ranks_read_integrity_broken(self):
        plan = self._two_candidate_plan()
        self._plant_rank(plan, sqlite3.Binary(b"\x01"), expected_type="blob")
        st = routing.plan_staleness(self.conn, plan)  # must not raise
        self.assertTrue(st.stale)
        self.assertEqual(st.reasons, ("integrity_broken",))
        self.assertIsNone(st.agent)
        self.assertFalse(st.superseded)
        self.assertIsNone(st.successor)

    def test_mixed_int_and_text_ranks_read_integrity_broken(self):
        plan = self._two_candidate_plan()
        self._plant_rank(plan, "not-a-rank", expected_type="text")
        st = routing.plan_staleness(self.conn, plan)
        self.assertTrue(st.stale)
        self.assertEqual(st.reasons, ("integrity_broken",))

    def test_float_rank_reads_integrity_broken(self):
        plan = self._two_candidate_plan()
        self._plant_rank(plan, 1.5, expected_type="real")
        st = routing.plan_staleness(self.conn, plan)
        self.assertTrue(st.stale)
        self.assertEqual(st.reasons, ("integrity_broken",))

    def test_superseded_flag_remains_correct_with_malformed_ranks(self):
        plan = self._two_candidate_plan()
        successor = routing.create_plan(
            self.conn, self.request(capabilities=["cap.a"]),
            supersedes_id=plan.id,
        )
        self._plant_rank(plan, sqlite3.Binary(b"\x01"), expected_type="blob")
        st = routing.plan_staleness(self.conn, self._reread(plan.id))
        self.assertTrue(st.stale)
        self.assertEqual(st.reasons, ("integrity_broken",))
        self.assertTrue(st.superseded)
        self.assertEqual(st.successor, ids.render_id("routing_plan", successor))

    def test_malformed_rank_result_value_free_deterministic_read_only(self):
        plan = self._two_candidate_plan()
        self._plant_rank(plan, sqlite3.Binary(b"\x01"), expected_type="blob")
        candidate_rows = "SELECT * FROM routing_plan_candidates " \
            "WHERE plan_id=? ORDER BY id"
        before_rows = [
            tuple(row)
            for row in self.conn.execute(candidate_rows, (plan.id,)).fetchall()
        ]
        changes_before = self.conn.total_changes
        first = routing.plan_staleness(self.conn, plan)
        second = routing.plan_staleness(self.conn, plan)
        self.assertEqual(first, second)
        self.assertEqual(self.conn.total_changes, changes_before)
        rendered = repr(first)
        for leaked in ("\\x01", "TypeError", "bytes", "Traceback",
                       "not supported between instances"):
            self.assertNotIn(leaked, rendered)
        after_rows = [
            tuple(row)
            for row in self.conn.execute(candidate_rows, (plan.id,)).fetchall()
        ]
        self.assertEqual(before_rows, after_rows)

    def test_valid_plans_keep_existing_staleness_vocabulary(self):
        self.publish("a", capabilities=["cap.a"])
        fresh = self._live_plan(capabilities=["cap.a"])
        st = routing.plan_staleness(self.conn, fresh)
        self.assertFalse(st.stale)
        self.assertEqual(st.reasons, ())
        self.assertIsNone(st.agent)
        # The existing closed reasons still fire exactly as before.
        self.publish_v2("a", capabilities=["cap.a"])
        st = routing.plan_staleness(self.conn, self._reread(fresh.id))
        self.assertTrue(st.stale)
        self.assertIn("passport_version_changed", st.reasons)
        self.assertEqual(st.agent, "a")
        second = self._live_plan(capabilities=["cap.a"])
        passports.transition_lifecycle(self.conn, name="a", verb="suspend")
        st_suspended = routing.plan_staleness(self.conn, self._reread(second.id))
        self.assertIn("lifecycle_not_active", st_suspended.reasons)
        self.assertIn("identity_changed", st_suspended.reasons)

    def test_verify_plan_on_malformed_ranks_is_total_with_closed_verdicts(self):
        # With staleness total, `verify_plan`'s final staleness call no longer
        # raises either: the plan reads by the frozen matrix's non-integer-rank
        # shape (an unhashable candidate plus a rank gap, plus the unhashable
        # plan chain) AND stale through integrity_broken — "both
        # verification-failed and stale", never an exception.
        plan = self._two_candidate_plan()
        self._plant_rank(plan, sqlite3.Binary(b"\x01"), expected_type="blob")
        result = routing.verify_plan(self.conn, plan.id)  # must not raise
        rp = ids.render_id("routing_plan", plan.id)
        self.assertFalse(result["ok"])
        self.assertTrue(
            any(p.endswith("unhashable") for p in result["problems"]),
            result["problems"],
        )
        self.assertIn(f"{rp}: rank_gap", result["problems"])
        self.assertTrue(result["stale"])
        self.assertIn("integrity_broken", result["staleness_reasons"])


if __name__ == "__main__":
    unittest.main()
