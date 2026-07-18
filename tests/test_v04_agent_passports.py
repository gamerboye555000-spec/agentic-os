"""U-A1 Agent Passport v1 and the governed agent registry
(agentic-os-v0.4-u-a1-agent-passports-contract.md).

Three kinds of proof live here:

- MIGRATION proofs run against the real historical v3 fixture
  (tests/fixtures/v3_workspace.py), copied to a temp workspace, and drive the
  PRODUCTION registry.
- FROZEN-HISTORY proofs run the v2 fixture to target=3 and byte-compare what
  comes out against the frozen historical DDL, so a future edit to a live
  constant that would silently rewrite history fails loudly.
- REGISTRY proofs run against a fresh v4 workspace through the CLI:
  lifecycle, publication, import/export, discard, tamper/no-laundering,
  events, doctor, and recovery classification.

Nothing here touches a real ledger, resolves a declared requirement, or
executes anything a passport names.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fixtures.v2_workspace import build_v2_workspace
from fixtures.v3_workspace import (
    SECRET_NOTES,
    agents_contents,
    build_v3_workspace,
    table_contents,
)
from weekend_harness import run_cli

from agentic_os import backup, db, migrations, models, passports, protocols, utils

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Planted where a careless implementation would echo it back out (U-C3).
FAKE_SECRET = "sk-live-a1planted00000000000000000000000000000000"  # noqa: S105


def make_passport(**overrides) -> dict:
    """A valid beast.agent-passport/v1 document, sealed."""
    document = {
        "schema": "beast.agent-passport/v1",
        "protocol_version": 1,
        "content_hash_alg": protocols.CONTENT_HASH_ALG,
        "created_at": "2026-07-16T09:00:00Z",
        "issuer": "human",
        "agent": "specimen",
        "passport_version": 1,
        "agent_class": "custom",
        "agent_scope": {"level": "global"},
        "role": "test specimen",
        "mission": "exist for the tests",
        "autonomy": "declare_only",
        "escalation": "ask_human",
        "provenance": {"created_by": "human", "method": "create"},
    }
    document.update(overrides)
    document.pop("content_sha256", None)
    document["content_sha256"] = protocols.content_digest(document)
    return document


# ---------------------------------------------------------------------------
# Bases

class V3FixtureTestCase(unittest.TestCase):
    """A disposable copy of the historical v3 fixture workspace."""

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.mkdtemp(prefix="aos-a1-fixture-")
        cls._fixture_tmp = tmp
        cls._fixture_root = Path(tmp) / "v3"
        build_v3_workspace(cls._fixture_root)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._fixture_tmp, ignore_errors=True)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "ws"
        shutil.copytree(self._fixture_root, self.root, symlinks=True)
        self.aos_dir = self.root / utils.AOS_DIR_NAME
        self.db_path = self.aos_dir / utils.DB_FILENAME

    def aos(self, *argv: str) -> tuple[int, str, str]:
        return run_cli("--root", str(self.root), *argv)

    def query(self, sql: str, params=()) -> list[sqlite3.Row]:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def execute(self, sql: str, params=()) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute(sql, params)
        finally:
            conn.close()

    def version(self) -> str:
        return self.query(
            "SELECT value FROM meta WHERE key='schema_version'"
        )[0][0]

    def migrate(self) -> None:
        # Brings the v3 fixture fully up to date. U-A3 made the current
        # version 5, so a to-current apply now runs 3→4 then 4→5; the assertion
        # follows the one schema declaration rather than a frozen literal.
        code, _, err = self.aos("migrate", "apply")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.version(), db.SCHEMA_VERSION)


class V4WorkspaceTestCase(unittest.TestCase):
    """A fresh v4 workspace with one project."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.aos_dir = self.root / utils.AOS_DIR_NAME
        self.db_path = self.aos_dir / utils.DB_FILENAME
        self.ok("init")
        self.ok(
            "project", "add", "demo", "--name", "Demo", "--repo",
            str(self.repo),
        )

    def aos(self, *argv: str) -> tuple[int, str, str]:
        return run_cli("--root", str(self.root), *argv)

    def ok(self, *argv: str) -> str:
        code, out, err = self.aos(*argv)
        self.assertEqual(code, 0, f"{argv}: {err}")
        return out

    def fails(self, *argv: str) -> str:
        code, out, err = self.aos(*argv)
        self.assertEqual(code, 1, f"{argv} did not refuse: {out}")
        return err

    def query(self, sql: str, params=()) -> list[sqlite3.Row]:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            return conn.execute(sql, params).fetchall()
        finally:
            conn.close()

    def execute(self, sql: str, params=()) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute(sql, params)
        finally:
            conn.close()

    def published_agent(self, name: str = "codex") -> None:
        self.ok("agent", "create", name, "--role", "coder",
                "--mission", "write code")
        self.ok("agent", "passport", "publish", name)

    def write_next_version(self, name: str, version: int, **overrides) -> Path:
        exported = json.loads(self.ok("agent", "export", name))
        exported.update(overrides)
        exported["passport_version"] = version
        exported.pop("content_sha256", None)
        exported["content_sha256"] = protocols.content_digest(exported)
        path = self.root / f"{name}-v{version}.json"
        path.write_text(json.dumps(exported), encoding="utf-8")
        return path

    def agent_events(self) -> list[tuple[str, dict]]:
        return [
            (row["action"], json.loads(row["payload_json"]))
            for row in self.query(
                "SELECT action, payload_json FROM events "
                "WHERE entity='agent' ORDER BY id"
            )
        ]


# ---------------------------------------------------------------------------
# (1) Schema and registry shape

class SchemaTests(V4WorkspaceTestCase):
    def test_fresh_init_is_version_five_with_both_agent_tables(self):
        self.assertEqual(
            self.query("SELECT value FROM meta WHERE key='schema_version'")[0][0],
            "5",
        )
        names = {
            r[0]
            for r in self.query(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertIn("agents", names)
        self.assertIn("agent_passports", names)

    def test_registry_is_exactly_the_four_steps_in_order(self):
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

    def test_no_index_was_added(self):
        # D-v0.3.45: UNIQUE constraints carry the implicit indexes; no
        # explicit CREATE INDEX exists anywhere in the schema.
        rows = self.query(
            "SELECT name, sql FROM sqlite_master WHERE type='index' "
            "AND tbl_name IN ('agents','agent_passports') AND sql IS NOT NULL"
        )
        self.assertEqual([tuple(r) for r in rows], [])


# ---------------------------------------------------------------------------
# (2) Migration 3 → 4

def _normalize_table_sql(sql: str) -> str:
    """Strip the ONE documented storage mechanic (D-v0.3.51): the rename
    quoting artifact. Everything else is compared verbatim."""
    return sql.replace('CREATE TABLE "', "CREATE TABLE ", 1).replace(
        '"(', "(", 1
    ) if sql.startswith('CREATE TABLE "') else sql


class MigrationTests(V3FixtureTestCase):
    def test_status_shows_the_pending_steps(self):
        # A v3 fixture had exactly one pending step at U-A1; U-A3 appended the
        # 4→5 step, so a to-current plan from v3 now lists both.
        report = migrations.status(self.db_path)
        self.assertEqual(report["current_version"], 3)
        self.assertEqual(
            [s["migration_id"] for s in report["plan"]],
            ["u-a1-agent-passports-v4", "u-a3-routing-handoffs-v5"],
        )

    def test_migration_preserves_everything_and_governs_nothing(self):
        before = table_contents(self.db_path)
        before_agents = agents_contents(self.db_path)

        self.migrate()

        after = table_contents(self.db_path)
        for table in before:
            if table in ("events", "meta"):
                continue  # events gain the migrate row; meta the version
            self.assertEqual(before[table], after[table], f"{table} changed")

        # The legacy columns, field for field — including the planted
        # secret-shaped notes, the direct-SQL invoke_hint and trust_level.
        self.assertEqual(before_agents, agents_contents(self.db_path))
        secret_row = [r for r in agents_contents(self.db_path) if r[1] == "legacy-bot"]
        self.assertEqual(secret_row[0][6], SECRET_NOTES)
        self.assertEqual(secret_row[0][5], 2)  # trust_level
        self.assertEqual(secret_row[0][3], "claude --agent legacy-bot")

        # Constant new facts; single clock reading; NO fabricated passports.
        rows = self.query("SELECT * FROM agents ORDER BY id")
        stamps = set()
        for row in rows:
            self.assertEqual(row["origin"], "legacy")
            self.assertEqual(row["lifecycle"], "active")
            self.assertEqual(row["agent_class"], "custom")
            self.assertEqual(row["scope"], "global")
            self.assertIsNone(row["project_id"])
            self.assertEqual(row["protected"], 0)
            self.assertEqual(row["owner"], "human")
            self.assertIsNone(row["current_passport_version"])
            self.assertEqual(row["created_at"], row["updated_at"])
            stamps.add(row["created_at"])
            agent = models.Agent.from_row(row)
            self.assertEqual(passports.agent_integrity(agent), "ok")
        self.assertEqual(len(stamps), 1)
        self.assertEqual(
            self.query("SELECT COUNT(*) FROM agent_passports")[0][0], 0
        )

    def test_migrated_and_fresh_agent_schema_are_identical(self):
        self.migrate()
        fresh_root = Path(tempfile.mkdtemp(prefix="aos-a1-fresh-"))
        self.addCleanup(shutil.rmtree, fresh_root, True)
        conn, _ = db.init_db(fresh_root / "aos.db")
        conn.close()

        def objects(path):
            conn = sqlite3.connect(path)
            try:
                return sorted(
                    (r[0], r[1], _normalize_table_sql(r[2]) if r[2] else None)
                    for r in conn.execute(
                        "SELECT type, name, sql FROM sqlite_master "
                        "WHERE name LIKE 'agent%'"
                    )
                )
            finally:
                conn.close()

        self.assertEqual(objects(self.db_path), objects(fresh_root / "aos.db"))

    def test_doctor_is_clean_on_the_migrated_fixture(self):
        self.migrate()
        code, out, err = self.aos("doctor")
        self.assertEqual(code, 0, err)
        # The migrated legacy agents surface on the WARN-only coverage line
        # (a fact, not a failure) and the planted secret on the sweep line.
        self.assertIn("[WARN] active agents without a published passport", out)
        self.assertNotIn(SECRET_NOTES, out)

    def test_legacy_agent_can_be_governed_by_publishing_a_passport(self):
        self.migrate()
        document = make_passport(
            agent="legacy-bot",
            provenance={"created_by": "human", "method": "publish"},
        )
        path = self.root / "legacy-bot-v1.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        code, out, err = self.aos(
            "agent", "passport", "publish", "legacy-bot", "--file", str(path)
        )
        self.assertEqual(code, 0, err)
        row = self.query(
            "SELECT current_passport_version, origin FROM agents "
            "WHERE name='legacy-bot'"
        )[0]
        self.assertEqual(tuple(row), (1, "legacy"))

    def test_trust_level_still_has_no_command_surface(self):
        # The column survives as inert history; no CLI verb reads, writes or
        # branches on it. Walk the LIVE parser: no agent leaf may declare a
        # trust option, and no writer module may consult the column outside
        # the carry/hash/display paths this unit declares.
        from agentic_os import cli as cli_module

        parser = cli_module.build_parser()
        agent_parser = None
        for action in parser._actions:
            if hasattr(action, "choices") and action.choices:
                agent_parser = action.choices.get("agent")
        self.assertIsNotNone(agent_parser)

        def walk(node):
            for action in node._actions:
                for option in action.option_strings:
                    self.assertNotIn("trust", option)
                if hasattr(action, "choices") and isinstance(
                    action.choices, dict
                ):
                    for child in action.choices.values():
                        walk(child)

        walk(agent_parser)

    # -- failure injection ---------------------------------------------------

    def _boom(self, conn):
        migrations._agent_passports_v4(conn)
        raise RuntimeError(f"planted failure {FAKE_SECRET}")

    def _failing_registry(self):
        return (
            migrations.Migration(3, 4, "u-a1-agent-passports-v4", self._boom),
        )

    def test_injected_failure_rolls_back_to_an_intact_v3(self):
        before = table_contents(self.db_path)
        before_agents = agents_contents(self.db_path)
        before_sql = self.query(
            "SELECT sql FROM sqlite_master WHERE name='agents'"
        )[0][0]

        with self.assertRaises(migrations.MigrationStepError) as caught:
            migrations.apply_migrations(
                self.aos_dir, registry=self._failing_registry(), latest=4
            )
        message = str(caught.exception)
        self.assertIn("RuntimeError", message)
        self.assertNotIn(FAKE_SECRET, message)  # class name only, never str(exc)

        self.assertEqual(self.version(), "3")
        self.assertEqual(before_agents, agents_contents(self.db_path))
        self.assertEqual(
            self.query("SELECT sql FROM sqlite_master WHERE name='agents'")[0][0],
            before_sql,
        )
        self.assertNotIn(
            "agent_passports",
            {r[0] for r in self.query(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )},
        )
        after = table_contents(self.db_path)
        self.assertEqual(before, after)
        self.assertEqual(
            self.query(
                "SELECT COUNT(*) FROM events WHERE entity='system' "
                "AND action='migrate'"
            )[0][0],
            0,
        )
        # The verified pre-migration snapshot is intact and adoptable.
        self.assertTrue(caught.exception.snapshot.is_file())

        # Corrected retry applies every remaining step exactly once — the
        # rolled-back 3→4 is not double-applied. To-current now spans two steps
        # (3→4 then the additive 4→5), so exactly two migrate events exist.
        self.migrate()
        self.assertEqual(
            self.query(
                "SELECT COUNT(*) FROM events WHERE entity='system' "
                "AND action='migrate'"
            )[0][0],
            2,
        )

    def test_damaged_legacy_row_refuses_safely_and_rolls_back(self):
        self.execute(
            "UPDATE agents SET notes = CAST(x'deadbeef' AS BLOB) WHERE id = 2"
        )
        before_agents = agents_contents(self.db_path)
        code, out, err = self.aos("migrate", "apply")
        self.assertEqual(code, 1)
        self.assertIn("PassportHashError", err)
        self.assertNotIn("deadbeef", err + out)
        self.assertEqual(self.version(), "3")
        self.assertEqual(before_agents, agents_contents(self.db_path))
        # Repair, then the corrected retry succeeds.
        self.execute("UPDATE agents SET notes = 'repaired' WHERE id = 2")
        self.migrate()


class FrozenHistoryTests(unittest.TestCase):
    """A 2→3 migration must still produce a TRUE v3 database — its inputs
    are live constants U-A1 leaves byte-identical, and this pins that."""

    def test_two_to_three_still_produces_the_historical_v3_schema(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve() / "v2"
        db_path = build_v2_workspace(root)
        result = migrations.apply_migrations(db_path.parent, target=3)
        self.assertEqual(result["current_version"], 3)
        conn = sqlite3.connect(db_path)
        try:
            agents_sql = _normalize_table_sql(
                conn.execute(
                    "SELECT sql FROM sqlite_master WHERE name='agents'"
                ).fetchone()[0]
            )
            memory_sql = _normalize_table_sql(
                conn.execute(
                    "SELECT sql FROM sqlite_master WHERE name='memory'"
                ).fetchone()[0]
            )
        finally:
            conn.close()
        self.assertEqual(
            agents_sql, migrations._V3_AGENTS_DDL.format(table="agents")
        )
        self.assertEqual(
            memory_sql, db.MEMORY_CLAIM_DDL.format(table=db.MEMORY_TABLE)
        )


# ---------------------------------------------------------------------------
# (3) Passport document validation

class PassportValidationTests(unittest.TestCase):
    def assertRefuses(self, code: str, callable_, *args):
        with self.assertRaises(protocols.ProtocolError) as caught:
            callable_(*args)
        self.assertEqual(caught.exception.code, code)

    def test_a_valid_passport_validates(self):
        entry = protocols.validate_document(make_passport())
        self.assertEqual(entry.identity, "beast.agent-passport/v1")

    def test_reduced_envelope_requires_no_task_fields(self):
        document = make_passport()
        for absent in ("aos_task_id", "trace", "idempotency_key", "audience",
                       "scope", "permitted_destinations"):
            self.assertNotIn(absent, document)

    def test_task_envelope_fields_are_unrepresentable(self):
        self.assertRefuses(
            "unknown_field",
            protocols.validate_document,
            make_passport(trace={"trace_id": "a" * 32,
                                 "correlation_id":
                                 "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"}),
        )

    def test_content_hash_must_match(self):
        document = make_passport()
        document["mission"] = "quietly changed"
        self.assertRefuses(
            "hash_mismatch", protocols.validate_document, document
        )

    def test_unknown_fields_refuse_at_top_level_and_nested(self):
        self.assertRefuses(
            "unknown_field", protocols.validate_document,
            make_passport(surprise="x"),
        )
        self.assertRefuses(
            "unknown_field", protocols.validate_document,
            make_passport(provenance={"created_by": "human",
                                      "method": "create", "extra": "x"}),
        )

    def test_credential_shaped_fields_are_unrepresentable(self):
        # No such property is declared, so an instance carrying one is an
        # unknown field — and the refusal path names the PARENT, never the
        # attacker's key.
        with self.assertRaises(protocols.ProtocolError) as caught:
            protocols.validate_document(make_passport(api_key="sk-x"))
        self.assertEqual(caught.exception.code, "unknown_field")
        self.assertNotIn("api_key", str(caught.exception))

    def test_scope_cross_field_rule(self):
        self.assertRefuses(
            "scope_level_mismatch", protocols.validate_document,
            make_passport(agent_scope={"level": "project"}),
        )
        self.assertRefuses(
            "scope_level_mismatch", protocols.validate_document,
            make_passport(agent_scope={"level": "global", "project": "demo"}),
        )
        protocols.validate_document(
            make_passport(agent_scope={"level": "project", "project": "demo"})
        )

    def test_enums_and_bounds_refuse_at_their_edges(self):
        self.assertRefuses(
            "enum_mismatch", protocols.validate_document,
            make_passport(autonomy="full"),
        )
        self.assertRefuses(
            "out_of_range", protocols.validate_document,
            make_passport(passport_version=0),
        )
        self.assertRefuses(
            "too_long", protocols.validate_document,
            make_passport(role="r" * 257),
        )
        self.assertRefuses(
            "too_long", protocols.validate_document,
            make_passport(limitations=[f"limit {i}" for i in range(33)]),
        )
        self.assertRefuses(
            "out_of_range", protocols.validate_document,
            make_passport(limits={"max_task_seconds": 604801}),
        )

    def test_arrays_refuse_duplicates(self):
        self.assertRefuses(
            "not_unique", protocols.validate_document,
            make_passport(capabilities=["code", "code"]),
        )

    def test_version_identity_rules(self):
        self.assertRefuses(
            "version_identity_mismatch", protocols.validate_document,
            make_passport(protocol_version=2),
        )

    def test_legacy_semantics_are_unchanged_by_the_guard(self):
        # The trace-id check still fires for the schemas that carry trace —
        # the presence guard changed nothing for them (spine suite pins the
        # rest; this is the U-A1-local regression).
        from test_v03_protocol_spine import work_spec

        with self.assertRaises(protocols.ProtocolError) as caught:
            protocols.validate_document(
                work_spec(trace={"trace_id": "0" * 32,
                                 "correlation_id":
                                 "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"})
            )
        self.assertEqual(caught.exception.path, "/trace/trace_id")


# ---------------------------------------------------------------------------
# (4) Registry semantics: create, publish, export, history, import

class RegistryTests(V4WorkspaceTestCase):
    def test_create_makes_a_draft_identity_with_a_draft_v1(self):
        out = self.ok("agent", "create", "codex", "--role", "coder",
                      "--mission", "write code")
        self.assertIn("Added agent codex (custom, draft)", out)
        row = self.query("SELECT * FROM agents WHERE name='codex'")[0]
        self.assertEqual(row["lifecycle"], "draft")
        self.assertEqual(row["origin"], "create")
        self.assertIsNone(row["current_passport_version"])
        passport = self.query("SELECT * FROM agent_passports")[0]
        self.assertEqual(
            (passport["version"], passport["status"]), (1, "draft")
        )
        self.assertIsNone(passport["published_at"])
        document = json.loads(passport["document"])
        self.assertEqual(document["agent"], "codex")
        self.assertEqual(document["passport_version"], 1)
        self.assertEqual(document["provenance"]["method"], "create")

    def test_duplicate_name_refuses_pointing_at_the_existing_agent(self):
        self.ok("agent", "create", "codex")
        err = self.fails("agent", "create", "codex")
        self.assertIn("already exists", err)

    def test_publish_activates_and_freezes_v1(self):
        self.published_agent()
        row = self.query("SELECT * FROM agents WHERE name='codex'")[0]
        self.assertEqual(row["lifecycle"], "active")
        self.assertEqual(row["current_passport_version"], 1)
        passport = self.query("SELECT * FROM agent_passports")[0]
        self.assertEqual(passport["status"], "published")
        self.assertIsNotNone(passport["published_at"])

    def test_publish_without_a_draft_refuses(self):
        self.published_agent()
        err = self.fails("agent", "passport", "publish", "codex")
        self.assertIn("no pending draft", err)

    def test_export_prints_stored_canonical_bytes_plus_newline(self):
        self.published_agent()
        code, out, err = self.aos("agent", "export", "codex")
        self.assertEqual(code, 0, err)
        stored = self.query(
            "SELECT document FROM agent_passports WHERE version=1"
        )[0][0]
        self.assertEqual(out, stored + "\n")
        # Byte-stable across invocations.
        self.assertEqual(out, self.aos("agent", "export", "codex")[1])

    def test_export_default_needs_a_published_version(self):
        self.ok("agent", "create", "codex")
        err = self.fails("agent", "export", "codex")
        self.assertIn("no published passport", err)
        self.assertIn("--version 1", err)  # the draft is reachable explicitly
        code, out, _ = self.aos("agent", "export", "codex", "--version", "1")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith('{"agent":"codex"'))

    def test_publish_next_version_from_file(self):
        self.published_agent()
        path = self.write_next_version("codex", 2, mission="write better code")
        self.ok("agent", "passport", "publish", "codex", "--file", str(path))
        row = self.query("SELECT * FROM agents WHERE name='codex'")[0]
        self.assertEqual(row["current_passport_version"], 2)
        versions = [
            tuple(r)
            for r in self.query(
                "SELECT version, status FROM agent_passports ORDER BY version"
            )
        ]
        self.assertEqual(versions, [(1, "published"), (2, "published")])
        # v1 is immutable history and still exportable.
        old = json.loads(self.ok("agent", "export", "codex", "--version", "1"))
        self.assertEqual(old["mission"], "write code")

    def test_publish_wrong_version_or_wrong_agent_refuses(self):
        self.published_agent()
        wrong_version = self.write_next_version("codex", 5)
        err = self.fails(
            "agent", "passport", "publish", "codex", "--file",
            str(wrong_version),
        )
        self.assertIn("next version for 'codex' is 2", err)

        other = self.write_next_version("codex", 2)
        document = json.loads(other.read_text())
        document["agent"] = "someone-else"
        document.pop("content_sha256")
        document["content_sha256"] = protocols.content_digest(document)
        other.write_text(json.dumps(document), encoding="utf-8")
        err = self.fails(
            "agent", "passport", "publish", "codex", "--file", str(other)
        )
        self.assertIn("declares agent 'someone-else'", err)

    def test_history_lists_every_version(self):
        self.published_agent()
        path = self.write_next_version("codex", 2)
        self.ok("agent", "passport", "publish", "codex", "--file", str(path))
        code, out, _ = self.aos("agent", "passport", "history", "codex", "--json")
        history = json.loads(out)
        self.assertEqual(
            [p["version"] for p in history["passports"]], [1, 2]
        )
        self.assertEqual(history["current_passport_version"], 2)
        self.assertTrue(
            all(p["integrity"] == "ok" for p in history["passports"])
        )

    def test_import_round_trip(self):
        self.published_agent()
        exported = json.loads(self.ok("agent", "export", "codex"))
        exported["agent"] = "codex-twin"
        exported.pop("content_sha256")
        exported["content_sha256"] = protocols.content_digest(exported)
        path = self.root / "twin.json"
        path.write_text(json.dumps(exported, indent=2), encoding="utf-8")

        out = self.ok("agent", "import", str(path))
        self.assertIn("Imported agent codex-twin (custom, draft)", out)
        row = self.query("SELECT * FROM agents WHERE name='codex-twin'")[0]
        self.assertEqual(row["origin"], "import")
        self.assertEqual(row["lifecycle"], "draft")
        self.ok("agent", "passport", "publish", "codex-twin")
        # export(import(F)) is canonical-equal to F.
        reexported = self.ok("agent", "export", "codex-twin")
        self.assertEqual(
            reexported.encode() ,
            protocols.serialize_canonical_file_bytes(exported),
        )

    def test_import_refusals(self):
        self.published_agent()
        # Same name refuses.
        same = self.root / "same.json"
        same.write_text(
            json.dumps(make_passport(agent="codex")), encoding="utf-8"
        )
        self.assertIn("already exists", self.fails("agent", "import", str(same)))
        # Version depth refuses.
        deep = self.root / "deep.json"
        deep.write_text(
            json.dumps(make_passport(agent="deep-agent", passport_version=3)),
            encoding="utf-8",
        )
        self.assertIn("passport_version 1", self.fails("agent", "import", str(deep)))
        # Hash mismatch refuses (protocol layer).
        broken = json.loads(same.read_text())
        broken["agent"] = "renamed"
        tampered = self.root / "tampered.json"
        tampered.write_text(json.dumps(broken), encoding="utf-8")
        self.assertIn("hash_mismatch", self.fails("agent", "import", str(tampered)))
        # Unresolvable project refuses.
        ghost = self.root / "ghost.json"
        ghost.write_text(
            json.dumps(
                make_passport(
                    agent="ghost",
                    agent_scope={"level": "project", "project": "missing"},
                )
            ),
            encoding="utf-8",
        )
        self.assertIn("No project 'missing'", self.fails("agent", "import", str(ghost)))
        # A symlink is refused as unsafe input (U-X1 filesystem contract).
        link = self.root / "link.json"
        link.symlink_to(same)
        self.assertIn("unsafe_input", self.fails("agent", "import", str(link)))

    def test_create_with_project_scope_and_fragment(self):
        fragment = self.root / "fragment.json"
        fragment.write_text(
            json.dumps(
                {
                    "capabilities": ["review", "code"],
                    "limits": {"max_task_seconds": 3600},
                }
            ),
            encoding="utf-8",
        )
        self.ok(
            "agent", "create", "scoped", "-p", "demo", "--class",
            "specialist", "--from-file", str(fragment),
        )
        row = self.query("SELECT * FROM agents WHERE name='scoped'")[0]
        self.assertEqual(row["scope"], "project")
        self.assertEqual(row["agent_class"], "specialist")
        document = json.loads(
            self.query("SELECT document FROM agent_passports")[0][0]
        )
        self.assertEqual(document["agent_scope"],
                         {"level": "project", "project": "demo"})
        # CLI-authored arrays are written sorted.
        self.assertEqual(document["capabilities"], ["code", "review"])

    def test_fragment_cannot_author_cli_owned_fields(self):
        fragment = self.root / "fragment.json"
        fragment.write_text(
            json.dumps({"issuer": "evil", "capabilities": ["x"]}),
            encoding="utf-8",
        )
        err = self.fails(
            "agent", "create", "sly", "--from-file", str(fragment)
        )
        self.assertIn("issuer", err)

    def test_missing_project_refuses(self):
        self.assertIn(
            "No project 'ghost'",
            self.fails("agent", "create", "x1", "-p", "ghost"),
        )


# ---------------------------------------------------------------------------
# (5) Lifecycle state machine

class LifecycleTests(V4WorkspaceTestCase):
    def test_every_legal_transition(self):
        self.published_agent("a1")
        self.assertIn("active → suspended", self.ok("agent", "suspend", "a1"))
        self.assertIn("suspended → active", self.ok("agent", "restore", "a1"))
        self.assertIn("active → archived", self.ok("agent", "archive", "a1"))
        self.assertIn("archived → active", self.ok("agent", "restore", "a1"))
        self.ok("agent", "suspend", "a1")
        self.assertIn("suspended → archived", self.ok("agent", "archive", "a1"))
        self.ok("agent", "restore", "a1")
        self.assertIn("active → revoked", self.ok("agent", "revoke", "a1"))

    def test_illegal_transitions_refuse_naming_the_state(self):
        self.published_agent("a1")
        err = self.fails("agent", "restore", "a1")  # active → restore
        self.assertIn("is active", err)
        self.ok("agent", "suspend", "a1")
        err = self.fails("agent", "suspend", "a1")  # same-state
        self.assertIn("is suspended", err)

    def test_revoked_is_terminal(self):
        self.published_agent("a1")
        self.ok("agent", "revoke", "a1")
        for verb in ("restore", "suspend", "archive", "revoke"):
            err = self.fails("agent", verb, "a1")
            self.assertIn("revocation is permanent", err)
        err = self.fails("agent", "passport", "publish", "a1")
        self.assertIn("revoked", err)

    def test_parked_agents_cannot_gain_versions(self):
        self.published_agent("a1")
        self.ok("agent", "suspend", "a1")
        path = self.write_next_version("a1", 2)
        err = self.fails(
            "agent", "passport", "publish", "a1", "--file", str(path)
        )
        self.assertIn("Restore it first", err)

    def test_draft_lifecycle_verbs_refuse(self):
        self.ok("agent", "create", "d1")
        for verb in ("suspend", "archive", "revoke"):
            err = self.fails("agent", verb, "d1")
            self.assertIn("is draft", err)

    def test_protected_refuses_park_and_discard(self):
        # No U-A1 command sets protected (minting is U-A2's bootstrap), so
        # the flag is planted the only way it can exist: direct SQL, with
        # the identity re-hashed the way U-A2 will do it.
        self.published_agent("guard")
        self.execute("UPDATE agents SET protected = 1 WHERE name='guard'")
        conn = db.connect(self.db_path)
        try:
            with conn:
                passports._rehash_agent(
                    conn,
                    conn.execute(
                        "SELECT id FROM agents WHERE name='guard'"
                    ).fetchone()[0],
                )
        finally:
            conn.close()
        for verb in ("suspend", "archive", "revoke"):
            err = self.fails("agent", verb, "guard")
            self.assertIn("protected_agent", err)

    def test_reserved_names_refuse_at_create_and_import(self):
        for name in ("governor", "planner", "builder", "verifier",
                     "security-sentinel", "aos.core", "beast.thing"):
            err = self.fails("agent", "create", name)
            self.assertIn("reserved", err)
        path = self.root / "reserved.json"
        path.write_text(
            json.dumps(make_passport(agent="governor")), encoding="utf-8"
        )
        self.assertIn("reserved", self.fails("agent", "import", str(path)))

    def test_archived_and_revoked_hide_from_default_list(self):
        self.published_agent("visible")
        self.published_agent("archived1")
        self.ok("agent", "archive", "archived1")
        self.published_agent("revoked1")
        self.ok("agent", "revoke", "revoked1")
        out = self.ok("agent", "list")
        self.assertIn("visible", out)
        self.assertNotIn("archived1", out)
        self.assertNotIn("revoked1", out)
        out = self.ok("agent", "list", "--all")
        self.assertIn("archived1", out)
        self.assertIn("revoked1", out)


# ---------------------------------------------------------------------------
# (6) Discard

class DiscardTests(V4WorkspaceTestCase):
    def test_legal_discard_removes_two_rows_and_journals(self):
        self.ok("agent", "create", "scratch")
        self.ok("agent", "discard", "scratch")
        self.assertEqual(self.query("SELECT COUNT(*) FROM agents")[0][0], 0)
        self.assertEqual(
            self.query("SELECT COUNT(*) FROM agent_passports")[0][0], 0
        )
        actions = [a for a, _ in self.agent_events()]
        self.assertEqual(actions, ["create", "discard"])
        # Second run: no such agent.
        self.assertIn("No agent", self.fails("agent", "discard", "scratch"))

    def test_published_agents_cannot_be_discarded(self):
        self.published_agent("kept")
        err = self.fails("agent", "discard", "kept")
        self.assertIn("only a never-published draft", err)

    def test_each_textual_reference_blocks_discard(self):
        self.ok("task", "add", "T", "-p", "demo")
        references = (
            ("runs", lambda: self.ok("run", "start", "T-0001", "--agent", "used-1")),
            ("handoffs", lambda: self.ok(
                "handoff", "create", "T-0001", "--from", "used-2",
                "--to", "other", "--state", "s")),
            ("handoffs", lambda: self.ok(
                "handoff", "create", "T-0001", "--from", "other2",
                "--to", "used-3", "--state", "s")),
            ("evidence", lambda: self.ok(
                "evidence", "add", "T-0001", "--kind", "note", "--ref", "r",
                "--claim", "c", "--provenance", "agent:used-4")),
            ("memory_sources", lambda: self.ok(
                "memory", "source", "add", "--kind", "file",
                "--locator", "f.txt", "--provenance", "agent:used-5")),
        )
        for index, (table, make_reference) in enumerate(references, 1):
            name = f"used-{index}"
            self.ok("agent", "create", name)
            make_reference()
            err = self.fails("agent", "discard", name)
            self.assertIn(table, err)
            self.assertIn("Archive or revoke", err)

    def test_legacy_agents_cannot_be_discarded(self):
        self.published_agent("fake-legacy")
        self.execute(
            "UPDATE agents SET origin='legacy' WHERE name='fake-legacy'"
        )
        conn = db.connect(self.db_path)
        try:
            with conn:
                passports._rehash_agent(
                    conn,
                    conn.execute(
                        "SELECT id FROM agents WHERE name='fake-legacy'"
                    ).fetchone()[0],
                )
        finally:
            conn.close()
        err = self.fails("agent", "discard", "fake-legacy")
        self.assertIn("legacy", err)


# ---------------------------------------------------------------------------
# (7) Tamper and no-laundering

class TamperTests(V4WorkspaceTestCase):
    def setUp(self):
        super().setUp()
        self.published_agent("victim")

    def _writes_refuse(self, expected: str):
        for argv in (
            ("agent", "suspend", "victim"),
            ("agent", "archive", "victim"),
            ("agent", "revoke", "victim"),
            ("agent", "passport", "publish", "victim"),
        ):
            with self.subTest(argv=argv):
                err = self.fails(*argv)
                self.assertIn("Refusing to change agent 'victim'", err)
                self.assertIn(expected, err)

    def test_document_tamper_refuses_writes_and_fails_doctor(self):
        self.execute(
            "UPDATE agent_passports SET document = replace(document, "
            "'write code', 'do crimes') WHERE version = 1"
        )
        self._writes_refuse("v1: mismatch")
        code, out, _ = self.aos("doctor")
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] agent passport history intact", out)
        self.assertNotIn("do crimes", out)
        # Reads still work, displaying the verdict.
        code, out, _ = self.aos("agent", "show", "victim", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(
            json.loads(out)["agent"]["passports"][0]["integrity"], "mismatch"
        )

    def test_status_tamper_refuses(self):
        self.execute(
            "UPDATE agent_passports SET status='draft', published_at=NULL "
            "WHERE version = 1"
        )
        self.fails("agent", "suspend", "victim")
        code, out, _ = self.aos("doctor")
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] agent passport history intact", out)

    def test_identity_tamper_refuses(self):
        self.execute("UPDATE agents SET lifecycle='suspended' WHERE name='victim'")
        err = self.fails("agent", "restore", "victim")
        self.assertIn("identity mismatch", err)
        code, out, _ = self.aos("doctor")
        self.assertEqual(code, 1)
        self.assertIn("[FAIL] agent identity hashes verify", out)

    def test_version_gap_refuses(self):
        path = self.write_next_version("victim", 2)
        self.ok("agent", "passport", "publish", "victim", "--file", str(path))
        self.execute("DELETE FROM agent_passports WHERE version = 1")
        self._writes_refuse("history_gap")

    def test_no_delete_path_exists_for_published_rows(self):
        # The only DELETE statements in passports.py target the discard
        # guards' single (draft, v1) row and its agent. Tamper-test style:
        # assert the module has no other DELETE.
        source = (REPO_ROOT / "agentic_os" / "passports.py").read_text()
        deletes = [
            line.strip()
            for line in source.splitlines()
            if "DELETE FROM" in line
        ]
        self.assertEqual(len(deletes), 2, deletes)
        self.assertIn("agent_passports WHERE id = ?", deletes[0])
        self.assertIn("agents WHERE id = ?", deletes[1])

    def test_recovery_gate_blocks_leaving_recovery_on_tamper(self):
        self.execute(
            "UPDATE agent_passports SET document = replace(document, "
            "'write code', 'x') WHERE version = 1"
        )
        self.ok("power", "set", "recovery")
        code, _, err = self.aos("power", "set", "standard")
        self.assertEqual(code, 1)
        self.assertIn("agent passport history intact", err)


# ---------------------------------------------------------------------------
# (8) Events

class EventPayloadTests(V4WorkspaceTestCase):
    ALLOWED_KEYS = {
        "schema_version", "agent", "agent_class", "scope", "origin",
        "version", "passport_sha256_prefix", "from_lifecycle",
        "to_lifecycle", "secret_warning", "secret_fields", "secret_patterns",
    }

    def test_payloads_carry_only_the_allowlist(self):
        self.published_agent("codex")
        path = self.write_next_version("codex", 2)
        self.ok("agent", "passport", "publish", "codex", "--file", str(path))
        self.ok("agent", "suspend", "codex")
        self.ok("agent", "restore", "codex")
        self.ok("agent", "archive", "codex")
        self.ok("agent", "restore", "codex")
        self.ok("agent", "revoke", "codex")
        self.ok("agent", "create", "scratch")
        self.ok("agent", "discard", "scratch")

        events = self.agent_events()
        self.assertEqual(
            [action for action, _ in events],
            ["create", "publish", "publish", "suspend", "restore",
             "archive", "restore", "revoke", "create", "discard"],
        )
        for action, payload in events:
            with self.subTest(action=action):
                self.assertLessEqual(set(payload), self.ALLOWED_KEYS)
                text = json.dumps(payload)
                self.assertNotIn("write code", text)  # no mission text
                self.assertNotIn("coder", text)  # no role text
                # Never a full hash: any 64-hex run would be one.
                import re
                self.assertIsNone(re.search(r"[0-9a-f]{64}", text))

    def test_secret_shaped_fields_warn_and_mark_but_never_journal(self):
        code, out, err = self.aos(
            "agent", "create", "leaky", "--mission",
            f"use {FAKE_SECRET} to log in",
        )
        self.assertEqual(code, 0)
        self.assertIn("WARNING: secret-shaped text", err)
        self.assertIn("mission", err)
        self.assertNotIn(FAKE_SECRET, err)
        # The canonical document keeps the accepted value; the event doesn't.
        document = self.query("SELECT document FROM agent_passports")[0][0]
        self.assertIn(FAKE_SECRET, document)
        _, payload = self.agent_events()[-1]
        self.assertEqual(payload.get("secret_warning"), True)
        self.assertIn("mission", payload.get("secret_fields", []))
        self.assertNotIn(FAKE_SECRET, json.dumps(payload))
        # And doctor's sweep finds it, value-free, by id + version.
        code, out, _ = self.aos("doctor")
        self.assertIn("passport v1 mission", out)
        self.assertNotIn(FAKE_SECRET, out)


# ---------------------------------------------------------------------------
# (9) Doctor

class DoctorTests(V4WorkspaceTestCase):
    def test_doctor_emits_exactly_37_checks(self):
        # U-A2 adds three built-in catalog checks (35-37) after the
        # existing 34; this fixture never installs the catalog, so all
        # three stay [PASS].
        code, out, err = self.aos("doctor")
        self.assertEqual(code, 0, err)
        lines = [
            line for line in out.splitlines()
            if line.startswith(("[PASS]", "[FAIL]", "[WARN]"))
        ]
        self.assertEqual(len(lines), 37)
        self.assertIn("agent identity hashes verify", lines[31])
        self.assertIn("agent passport history intact", lines[32])
        self.assertIn("active agents without a published passport", lines[33])

    def test_check_13_validates_the_governed_shape(self):
        # scope='project' with an unresolvable project passes the storage
        # CHECK (which only pins NULL-ness) but must fail check 13.
        self.published_agent("codex")
        self.execute(
            "UPDATE agents SET scope='project', project_id = 999 "
            "WHERE name='codex'"
        )
        code, out, _ = self.aos("doctor")
        self.assertEqual(code, 1)
        self.assertIn("project does not resolve", out)

    def test_blob_rows_are_reported_safely(self):
        self.published_agent("codex")
        self.execute(
            "UPDATE agents SET name = CAST(x'deadbeef' AS BLOB) WHERE id = 1"
        )
        code, out, _ = self.aos("doctor")
        self.assertEqual(code, 1)
        self.assertIn("agent #1", out)
        self.assertNotIn("deadbeef", out)

    def test_coverage_warning_never_affects_exit(self):
        # An active agent without a passport is only reachable by tamper or
        # migration; plant the migration-shaped state.
        self.published_agent("codex")
        self.execute(
            "UPDATE agents SET current_passport_version = NULL, "
            "origin = 'legacy' WHERE name='codex'"
        )
        self.execute("DELETE FROM agent_passports")
        conn = db.connect(self.db_path)
        try:
            with conn:
                passports._rehash_agent(conn, 1)
        finally:
            conn.close()
        code, out, _ = self.aos("doctor")
        self.assertEqual(code, 0)
        self.assertIn(
            "[WARN] active agents without a published passport", out
        )


# ---------------------------------------------------------------------------
# (10) Classification, recovery, parity

class ClassificationTests(V4WorkspaceTestCase):
    def test_reads_work_in_recovery_and_writes_are_blocked(self):
        self.published_agent("codex")
        self.ok("power", "set", "recovery")
        self.ok("agent", "list")
        self.ok("agent", "show", "codex")
        self.ok("agent", "export", "codex")
        self.ok("agent", "passport", "history", "codex")
        for argv in (
            ("agent", "create", "x2"),
            ("agent", "suspend", "codex"),
            ("agent", "passport", "publish", "codex"),
            ("agent", "discard", "codex"),
        ):
            code, out, err = self.aos(*argv)
            self.assertEqual(code, 1)
            self.assertEqual(out, "")
            self.assertIn("recovery mode", err)

    def test_deep_mode_preflight_wraps_agent_writes(self):
        # Deep is silent when clean; prove the preflight FIRES by giving the
        # sweep a finding — the write is then refused before it mutates.
        self.ok("power", "set", "deep")
        self.ok("agent", "create", "deepbot")  # clean preflight passes
        # The plant itself COMMITS and then fails deep post-verification
        # (exit 1, honestly reported) — exactly the state the next write's
        # preflight must refuse on.
        code, _, err = self.aos(
            "task", "add", f"password = {FAKE_SECRET}", "-p", "demo"
        )
        self.assertEqual(code, 1)
        self.assertIn("COMMITTED", err)
        code, out, err = self.aos("agent", "create", "deepbot2")
        self.assertEqual(code, 1)
        self.assertIn("deep mode's preflight", err)
        self.assertIn("secret sweep", err)
        self.assertEqual(
            self.query("SELECT COUNT(*) FROM agents WHERE name='deepbot2'")[0][0],
            0,
        )

    def test_script_and_module_entrypoints_print_identical_bytes(self):
        self.published_agent("codex")
        for argv in (
            ("agent", "list"),
            ("agent", "show", "codex"),
            ("agent", "export", "codex"),
        ):
            with self.subTest(argv=argv):
                script = subprocess.run(
                    [sys.executable, str(REPO_ROOT / "aos.py"),
                     "--root", str(self.root), *argv],
                    capture_output=True, text=True, cwd=self.root,
                )
                module = subprocess.run(
                    [sys.executable, "-m", "agentic_os",
                     "--root", str(self.root), *argv],
                    capture_output=True, text=True, cwd=REPO_ROOT,
                )
                self.assertEqual(script.returncode, 0, script.stderr)
                self.assertEqual(module.returncode, 0, module.stderr)
                self.assertEqual(script.stdout, module.stdout)


if __name__ == "__main__":
    unittest.main()
