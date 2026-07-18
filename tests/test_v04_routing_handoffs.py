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

import dataclasses
import hashlib
import inspect
import itertools
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fixtures.v3_workspace import build_v3_workspace, table_contents

from agentic_os import db, ids, migrations, models, passports, protocols
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


if __name__ == "__main__":
    unittest.main()
