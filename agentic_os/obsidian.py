"""Obsidian vault: layout, static notes, Home dashboard. (The full entity
mirror sync is added in the sync phase.)

Everything generated lives under .agentic-os/obsidian-vault/AOS/ — sync never
writes outside it and never deletes or renames.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path, PurePath

from . import ids, render, utils
from .models import (
    MEMORY_SENSITIVITY_RESTRICTED,
    Agent,
    Decision,
    Evidence,
    Handoff,
    MemoryItem,
    Project,
    Run,
    Task,
)

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
    "Agents",
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


def _home_counts(conn: sqlite3.Connection) -> dict:
    def count(sql: str) -> int:
        return conn.execute(sql).fetchone()[0]

    return {
        "projects": count("SELECT COUNT(*) FROM projects"),
        "open_tasks": count("SELECT COUNT(*) FROM tasks WHERE status != 'done'"),
        "inbox_tasks": count("SELECT COUNT(*) FROM tasks WHERE status = 'inbox'"),
        "ready_tasks": count("SELECT COUNT(*) FROM tasks WHERE status = 'ready'"),
        "in_progress_tasks": count(
            "SELECT COUNT(*) FROM tasks WHERE status = 'in_progress'"
        ),
        "done_tasks": count("SELECT COUNT(*) FROM tasks WHERE status = 'done'"),
        "open_runs": count("SELECT COUNT(*) FROM runs WHERE ended_at IS NULL"),
        "open_handoffs": count(
            "SELECT COUNT(*) FROM handoffs WHERE accepted_at IS NULL"
        ),
        "decisions": count("SELECT COUNT(*) FROM decisions"),
        "evidence": count("SELECT COUNT(*) FROM evidence"),
        "memory": count("SELECT COUNT(*) FROM memory"),
        "agents": count("SELECT COUNT(*) FROM agents"),
    }


#: Top-level generated index notes (filename stems double as wikilinks).
INDEX_NOTES = tuple(name for name, _ in render.INDEX_NOTE_DESCRIPTIONS)


# ---------------------------------------------------------------------------
# Shared generated-layout rules. Public: consumed by doctor's containment
# checks and by the U-C4 mirror export's adoption/provenance gates — the
# single definition of "a file sync itself generates".

#: Generated wikilink shape ([[stem]] with optional |alias / #heading).
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")

#: Note stems are filesystem-derived input; \Z anchors, never $ (D-v0.2.3) —
#: a newline-bearing filename must not pass the containment check.
NOTE_STEM_PATTERNS = {
    "Tasks": re.compile(r"^T-[0-9]{4,}\Z"),
    "Runs": re.compile(r"^R-[0-9]{4,}\Z"),
    "Decisions": re.compile(r"^D-[0-9]{4,}\Z"),
    "Evidence": re.compile(r"^E-[0-9]{4,}\Z"),
    "Handoffs": re.compile(r"^H-[0-9]{4,}\Z"),
    "Memory": re.compile(r"^M-[0-9]{4,}\Z"),
    "Projects": re.compile(r"^[a-z0-9][a-z0-9._-]*\Z", re.ASCII),
    # Daily YYYY-MM-DD · weekly YYYY-Www · per-project project-<slug>.
    "Reviews": re.compile(
        r"^([0-9]{4}-[0-9]{2}-[0-9]{2}"
        r"|[0-9]{4}-W[0-9]{2}"
        r"|project-[a-z0-9][a-z0-9._-]*)\Z",
        re.ASCII,
    ),
    "Agents": re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\Z", re.ASCII),
}


def is_hidden_rel(path: Path, base: Path) -> bool:
    """True when any component of `path` below `base` starts with '.'
    (e.g. the .obsidian folder Obsidian creates at the vault root).
    Hidden entries are the user's, not sync's (D-P5.2)."""
    return any(part.startswith(".") for part in path.relative_to(base).parts)


def recognized_note_rel(rel: PurePath) -> bool:
    """True when `rel` (relative to the AOS/ mirror root) names a note that
    sync itself generates: a fixed top-level note, or <EntityDir>/<stem>.md
    with that entity's stem shape."""
    if len(rel.parts) == 1:
        allowed = ("Home.md", "CONVENTIONS.md") + tuple(
            f"{name}.md" for name in INDEX_NOTES
        )
        return rel.parts[0] in allowed
    if len(rel.parts) == 2:
        pattern = NOTE_STEM_PATTERNS.get(rel.parts[0])
        return (
            pattern is not None
            and rel.suffix == ".md"
            and pattern.match(rel.stem) is not None
        )
    return False


def _index_note_contents(conn: sqlite3.Connection, aos_root: Path) -> dict[str, str]:
    slug_by_project_id = {
        row["id"]: row["slug"]
        for row in conn.execute("SELECT id, slug FROM projects")
    }

    def task_bullet(row) -> str:
        project = slug_by_project_id.get(row["project_id"]) or "-"
        title = " ".join(row["title"].split())
        return (
            f"- [[{ids.render_id('task', row['id'])}]] {title} "
            f"· {row['status']} · {project}"
        )

    open_tasks = [
        task_bullet(row)
        for row in conn.execute(
            "SELECT id, title, status, project_id FROM tasks "
            "WHERE status != 'done' ORDER BY id"
        )
    ]
    done_tasks = [
        task_bullet(row)
        for row in conn.execute(
            "SELECT id, title, status, project_id FROM tasks "
            "WHERE status = 'done' ORDER BY id"
        )
    ]

    def one(text: str | None) -> str:
        return " ".join(text.split()) if text else "-"

    decisions = [
        f"- [[{ids.render_id('decision', row['id'])}]] [{row['status']}] "
        f"{one(row['title'])}"
        for row in conn.execute(
            "SELECT id, title, status FROM decisions ORDER BY id"
        )
    ]
    evidence = [
        f"- [[{ids.render_id('evidence', row['id'])}]] {row['kind']} · "
        f"{one(row['ref'])} · [[{ids.render_id('task', row['task_id'])}]]"
        for row in conn.execute(
            "SELECT id, task_id, kind, ref FROM evidence ORDER BY id"
        )
    ]
    handoffs = [
        f"- [[{ids.render_id('handoff', row['id'])}]] {one(row['from_agent'])} "
        f"→ {one(row['to_agent'])} · [[{ids.render_id('task', row['task_id'])}]] "
        f"· {'accepted' if row['accepted_at'] else 'open'}"
        for row in conn.execute(
            "SELECT id, task_id, from_agent, to_agent, accepted_at "
            "FROM handoffs ORDER BY id"
        )
    ]
    memory = []
    for row in conn.execute(
        "SELECT m.id, m.key, m.scope, m.confidence, m.valid_until, "
        "m.superseded_by, m.status, m.pinned, m.sensitivity, "
        "(SELECT COUNT(*) FROM memory_evidence me WHERE me.memory_id = m.id) "
        "AS evidence_count "
        "FROM memory m ORDER BY m.id"
    ):
        # The index is a body projection too — a restricted claim's key must
        # not reach it any more than its note (M3.13).
        restricted = row["sensitivity"] == MEMORY_SENSITIVITY_RESTRICTED
        label = f"({MEMORY_SENSITIVITY_RESTRICTED})" if restricted else one(row["key"])
        bullet = (
            f"- [[{ids.render_id('memory', row['id'])}]] {label} "
            f"· {row['scope']} · [{row['confidence']}] · {row['status']}"
        )
        if row["pinned"]:
            bullet += " · pinned"
        if row["evidence_count"]:
            bullet += f" · {row['evidence_count']} evidence"
        if row["superseded_by"]:
            bullet += (
                f" · superseded by "
                f"[[{ids.render_id('memory', row['superseded_by'])}]]"
            )
        if row["valid_until"]:
            bullet += f" · valid until {row['valid_until']}"
        memory.append(bullet)
    agents = [
        f"- [[{row['name']}]] {row['agent_class']} · {row['lifecycle']}"
        for row in conn.execute(
            "SELECT name, agent_class, lifecycle FROM agents ORDER BY name"
        )
    ]
    reviews_dir = aos_root / "Reviews"
    reviews = [
        f"- [[{path.stem}]]"
        for path in sorted(reviews_dir.glob("*.md"))
        if reviews_dir.is_dir() and not path.name.startswith(".")
    ]

    return {
        "Tasks": render.index_note(
            "Tasks index",
            [("Open", open_tasks), ("Done", done_tasks)],
        ),
        "Decisions": render.index_note("Decisions index", [("All", decisions)]),
        "Evidence": render.index_note("Evidence index", [("All", evidence)]),
        "Handoffs": render.index_note("Handoffs index", [("All", handoffs)]),
        "Memory": render.index_note("Memory index", [("All", memory)]),
        "Agents": render.index_note("Agents index", [("All", agents)]),
        "Reviews": render.index_note("Reviews index", [("All", reviews)]),
    }


def write_home_and_conventions(conn: sqlite3.Connection, aos_dir: Path) -> int:
    """Write AOS/Home.md, AOS/CONVENTIONS.md, and the top-level index notes;
    returns files (re)written."""
    aos_root = vault_aos_dir(aos_dir)
    written = 0
    projects, open_tasks, recent_tasks = _home_inputs(conn)
    if utils.write_text_lf_if_changed(
        aos_root / "Home.md",
        render.home_md(
            projects, open_tasks, recent_tasks, _home_counts(conn)
        ),
    ):
        written += 1
    if utils.write_text_lf_if_changed(
        aos_root / "CONVENTIONS.md", render.CONVENTIONS_MD
    ):
        written += 1
    for name, content in _index_note_contents(conn, aos_root).items():
        if utils.write_text_lf_if_changed(aos_root / f"{name}.md", content):
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

    from . import ops  # local: ops imports this module, so the graph stays acyclic

    evidence_by_memory: dict[int, list[int]] = {}
    for row in _rows(
        conn,
        "SELECT memory_id, evidence_id FROM memory_evidence "
        "ORDER BY memory_id, evidence_id",
    ):
        evidence_by_memory.setdefault(row["memory_id"], []).append(
            row["evidence_id"]
        )

    for row in _rows(conn, "SELECT * FROM memory ORDER BY id"):
        item = MemoryItem.from_row(row)
        emit_note(
            aos_root / "Memory" / f"{ids.render_id('memory', item.id)}.md",
            render.memory_note(
                item,
                slug_by_project_id.get(item.project_id),
                evidence_by_memory.get(item.id, []),
                # Bounded COUNTS, never neighbours (M3.13): the mirror says
                # how much provenance a claim has, and the ledger says what it
                # is. No source locator or provenance text reaches a note.
                ops.memory_graph_counts(conn, item.id),
            ),
        )

    for row in _rows(conn, "SELECT * FROM agents ORDER BY name"):
        agent = Agent.from_row(row)
        emit_note(
            aos_root / "Agents" / f"{agent.name}.md",
            render.agent_note(agent, agent.capabilities()),
        )

    written += write_home_and_conventions(conn, aos_dir)
    total += 2 + len(INDEX_NOTES)  # Home.md + CONVENTIONS.md + index notes
    return total, written
