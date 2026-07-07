"""Shared Weekend test harness (not itself a test module).

Provides the in-process CLI runner, a temp-workspace base class, and the
Night-1-shaped workspace fixture (init → project → task → pack → run →
evidence → done → sync) that every Weekend phase reuses to prove its new
command works on a Night-1 database with no migration.
"""

from __future__ import annotations

import contextlib
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path

from agentic_os import cli, db, ops, utils

#: The Night-1 core tables. Weekend code must never alter their SQL.
CORE_TABLES = (
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


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def core_schema(db_path: Path) -> dict[str, str]:
    """The CREATE SQL of every Night-1 core table, straight from
    sqlite_master — the ground truth for "no schema drift"."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'table' "
            "AND name IN ({})".format(",".join("?" * len(CORE_TABLES))),
            CORE_TABLES,
        ).fetchall()
    finally:
        conn.close()
    return {name: sql for name, sql in rows}


class WeekendTestCase(unittest.TestCase):
    """Temp workspace helpers. Does NOT change cwd unless a test opts in."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.repo = self.root / "repo with spaces"
        self.repo.mkdir()
        self.aos_dir = self.root / utils.AOS_DIR_NAME

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        return run_cli(*argv)

    def ok(self, *argv: str) -> str:
        code, out, err = run_cli(*argv)
        self.assertEqual(code, 0, f"{argv} failed: {err or out}")
        return out

    def chdir(self, path: Path) -> None:
        cm = contextlib.chdir(path)
        cm.__enter__()
        self.addCleanup(lambda: cm.__exit__(None, None, None))

    def new_tmp_dir(self, name: str = "other") -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name).resolve() / name
        path.mkdir()
        return path


class Night1BackCompatCase(WeekendTestCase):
    """Base for back-compat proofs: a Night-1-shaped workspace built with
    ONLY Night-1 commands, then driven purely via --root from an unrelated
    cwd (the smoke-test class of mistake the contract calls out)."""

    def setUp(self):
        super().setUp()
        build_night1_workspace(self, self.root, self.repo)
        self.db_path = self.aos_dir / utils.DB_FILENAME
        self.baseline_schema = core_schema(self.db_path)
        self.chdir(self.new_tmp_dir("unrelated-cwd"))

    def aos(self, *argv: str) -> str:
        return self.ok("--root", str(self.root), *argv)

    def aos_fails(self, *argv: str) -> tuple[int, str, str]:
        code, out, err = self.run_cli("--root", str(self.root), *argv)
        self.assertEqual(code, 1, f"{argv} expected exit 1, got {code}: {out}{err}")
        return code, out, err

    def assert_no_schema_drift(self):
        self.assertEqual(core_schema(self.db_path), self.baseline_schema)


class WeekendOpsTestCase(unittest.TestCase):
    """Ops-layer base: temp workspace with an initialized ledger connection
    (no CLI involved) — for atomicity and event-invariant tests."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.repo = self.root / "repo with spaces"
        self.repo.mkdir()
        self.conn, created = db.init_db(
            self.root / utils.AOS_DIR_NAME / utils.DB_FILENAME
        )
        self.addCleanup(self.conn.close)
        if created:
            ops.initialize(self.conn, self.root)

    def row_count(self, table: str) -> int:
        return self.conn.execute(
            f"SELECT COUNT(*) AS n FROM {table}"
        ).fetchone()["n"]

    def event_count(self) -> int:
        return self.row_count("events")


def build_night1_workspace(case: WeekendTestCase, root: Path, repo: Path) -> None:
    """Create a Night-1-shaped workspace under `root`, exactly as a Night-1
    user would: cwd-based discovery, Night-1 commands only.

    Leaves behind: project `demo`, done task T-0001 (with pack P-0001, run
    R-0001, evidence E-0001), open task T-0002, inbox task T-0003, and a
    synced mirror.
    """
    with contextlib.chdir(root):
        case.ok("init")
        case.ok("project", "add", "demo", "--name", "Demo", "--repo", str(repo))
        case.ok(
            "task", "add", "Night-1 task", "-p", "demo",
            "--accept", "pack + evidence flow works",
        )
        case.ok("task", "add", "Second task", "-p", "demo")
        case.ok("pack", "build", "T-0001", "--for", "claude-code")
        case.ok("run", "start", "T-0001", "--agent", "claude-code")
        case.ok(
            "evidence", "add", "T-0001", "--kind", "note",
            "--ref", "night-1 proof", "--claim", "it works",
        )
        case.ok(
            "run", "end", "R-0001", "--outcome", "success", "--summary", "ok",
        )
        case.ok("done", "T-0001")
        case.ok("in", "inbox thought")
        case.ok("sync")
