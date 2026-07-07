"""Obsidian vault: layout, static notes, Home dashboard. (The full entity
mirror sync is added in the sync phase.)

Everything generated lives under .agentic-os/obsidian-vault/AOS/ — sync never
writes outside it and never deletes or renames.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import ids, render, utils
from .models import Decision, Evidence, Handoff, MemoryItem, Project, Run, Task

VAULT_DIRNAME = "obsidian-vault"
AOS_SUBDIR = "AOS"
ENTITY_DIRS = (
    "Projects",
    "Tasks",
    "Runs",
    "Decisions",
    "Evidence",
    "Handoffs",
    "Reviews",
    "Memory",
)
WORKSPACE_DIRS = ("packs", "exports", "adapters")


def vault_aos_dir(aos_dir: Path) -> Path:
    return aos_dir / VAULT_DIRNAME / AOS_SUBDIR


def ensure_layout(aos_dir: Path) -> None:
    for name in WORKSPACE_DIRS:
        (aos_dir / name).mkdir(parents=True, exist_ok=True)
    aos_root = vault_aos_dir(aos_dir)
    aos_root.mkdir(parents=True, exist_ok=True)
    for name in ENTITY_DIRS:
        (aos_root / name).mkdir(exist_ok=True)


def _home_inputs(conn: sqlite3.Connection) -> tuple[list[dict], list[dict], list[dict]]:
    projects = [
        dict(row)
        for row in conn.execute(
            "SELECT slug, name, status FROM projects ORDER BY slug"
        ).fetchall()
    ]
    open_tasks = [
        dict(row)
        for row in conn.execute(
            "SELECT t.id, t.title, t.status, p.slug AS project_slug "
            "FROM tasks t LEFT JOIN projects p ON p.id = t.project_id "
            "WHERE t.status != 'done' ORDER BY t.id"
        ).fetchall()
    ]
    recent_tasks = [
        dict(row)
        for row in conn.execute(
            "SELECT t.id, t.title, t.status, p.slug AS project_slug "
            "FROM tasks t LEFT JOIN projects p ON p.id = t.project_id "
            "ORDER BY t.id DESC LIMIT 10"
        ).fetchall()
    ]
    return projects, open_tasks, recent_tasks


def write_home_and_conventions(conn: sqlite3.Connection, aos_dir: Path) -> int:
    """Write AOS/Home.md and AOS/CONVENTIONS.md; returns files (re)written."""
    aos_root = vault_aos_dir(aos_dir)
    written = 0
    projects, open_tasks, recent_tasks = _home_inputs(conn)
    if utils.write_text_lf_if_changed(
        aos_root / "Home.md", render.home_md(projects, open_tasks, recent_tasks)
    ):
        written += 1
    if utils.write_text_lf_if_changed(
        aos_root / "CONVENTIONS.md", render.CONVENTIONS_MD
    ):
        written += 1
    return written


def write_adapter_templates(aos_dir: Path) -> None:
    for name, content in render.adapter_templates().items():
        utils.write_text_lf_if_changed(
            aos_dir / "adapters" / name / "PROTOCOL.md", content
        )


# ---------------------------------------------------------------------------
# Full mirror sync: one-way, idempotent, contained in AOS/, never deletes
# or renames. Entities iterate in ascending id order for stable output.

def _rows(conn: sqlite3.Connection, sql: str, params=()) -> list[sqlite3.Row]:
    return conn.execute(sql, params).fetchall()


def sync_vault(conn: sqlite3.Connection, aos_dir: Path) -> tuple[int, int]:
    """Regenerate the mirror. Returns (total notes, notes (re)written)."""
    ensure_layout(aos_dir)
    aos_root = vault_aos_dir(aos_dir)
    total = 0
    written = 0

    def emit_note(path: Path, content: str) -> None:
        nonlocal total, written
        total += 1
        if utils.write_text_lf_if_changed(path, content):
            written += 1

    slug_by_project_id = {
        row["id"]: row["slug"]
        for row in _rows(conn, "SELECT id, slug FROM projects")
    }

    for row in _rows(conn, "SELECT * FROM projects ORDER BY id"):
        project = Project.from_row(row)
        tasks = [
            dict(t)
            for t in _rows(
                conn,
                "SELECT id, title, status FROM tasks WHERE project_id = ? "
                "ORDER BY id",
                (project.id,),
            )
        ]
        emit_note(
            aos_root / "Projects" / f"{project.slug}.md",
            render.project_note(project, tasks),
        )

    for row in _rows(conn, "SELECT * FROM tasks ORDER BY id"):
        task = Task.from_row(row)
        runs = [
            Run.from_row(r)
            for r in _rows(
                conn, "SELECT * FROM runs WHERE task_id = ? ORDER BY id", (task.id,)
            )
        ]
        decisions = [
            Decision.from_row(r)
            for r in _rows(
                conn,
                "SELECT * FROM decisions WHERE task_id = ? "
                "OR (task_id IS NULL AND project_id IS NOT NULL "
                "AND project_id = ?) ORDER BY id",
                (task.id, task.project_id),
            )
        ]
        evidence = [
            Evidence.from_row(r)
            for r in _rows(
                conn,
                "SELECT * FROM evidence WHERE task_id = ? ORDER BY id",
                (task.id,),
            )
        ]
        handoffs = [
            Handoff.from_row(r)
            for r in _rows(
                conn,
                "SELECT * FROM handoffs WHERE task_id = ? ORDER BY id",
                (task.id,),
            )
        ]
        emit_note(
            aos_root / "Tasks" / f"{ids.render_id('task', task.id)}.md",
            render.task_note(
                task,
                slug_by_project_id.get(task.project_id),
                runs,
                decisions,
                evidence,
                handoffs,
                len(evidence),
            ),
        )

    for row in _rows(conn, "SELECT * FROM runs ORDER BY id"):
        run = Run.from_row(row)
        emit_note(
            aos_root / "Runs" / f"{ids.render_id('run', run.id)}.md",
            render.run_note(run),
        )

    for row in _rows(conn, "SELECT * FROM decisions ORDER BY id"):
        decision = Decision.from_row(row)
        if decision.task_id is not None:
            task_ids = [decision.task_id]
        elif decision.project_id is not None:
            # Project-scoped decision: link back to the same tasks whose
            # notes link it (bidirectional wikilinks).
            task_ids = [
                r["id"]
                for r in _rows(
                    conn,
                    "SELECT id FROM tasks WHERE project_id = ? ORDER BY id",
                    (decision.project_id,),
                )
            ]
        else:
            task_ids = []
        emit_note(
            aos_root / "Decisions" / f"{ids.render_id('decision', decision.id)}.md",
            render.decision_note(
                decision, slug_by_project_id.get(decision.project_id), task_ids
            ),
        )

    for row in _rows(conn, "SELECT * FROM evidence ORDER BY id"):
        item = Evidence.from_row(row)
        emit_note(
            aos_root / "Evidence" / f"{ids.render_id('evidence', item.id)}.md",
            render.evidence_note(item),
        )

    for row in _rows(conn, "SELECT * FROM handoffs ORDER BY id"):
        handoff = Handoff.from_row(row)
        emit_note(
            aos_root / "Handoffs" / f"{ids.render_id('handoff', handoff.id)}.md",
            render.handoff_note(handoff),
        )

    for row in _rows(conn, "SELECT * FROM memory ORDER BY id"):
        item = MemoryItem.from_row(row)
        emit_note(
            aos_root / "Memory" / f"{ids.render_id('memory', item.id)}.md",
            render.memory_note(item, slug_by_project_id.get(item.project_id)),
        )

    written += write_home_and_conventions(conn, aos_dir)
    total += 2  # Home.md + CONVENTIONS.md
    return total, written
