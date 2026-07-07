"""Domain operations. Every mutating operation here writes its domain row(s)
AND an events row in the SAME transaction — if either fails, both roll back.

Events are emitted via the module object (``events.emit``) so tests can patch
the emit function and prove the rollback.
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path

from . import db, events, ids, obsidian, utils
from .models import (
    EVIDENCE_KINDS,
    RUN_OUTCOMES,
    TASK_KINDS,
    TASK_STATUSES,
    Decision,
    Evidence,
    Handoff,
    Pack,
    Project,
    Run,
    Task,
    validate_enum,
    validate_provenance,
    validate_slug,
)
from .utils import AosError

ACTOR_HUMAN = "human"

GIT_TIMEOUT_SECONDS = 5


# ---------------------------------------------------------------------------
# Lookups

def get_project_by_slug(conn: sqlite3.Connection, slug: str) -> Project | None:
    row = conn.execute("SELECT * FROM projects WHERE slug = ?", (slug,)).fetchone()
    return Project.from_row(row) if row else None


def get_project(conn: sqlite3.Connection, project_id: int) -> Project | None:
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return Project.from_row(row) if row else None


def get_task(conn: sqlite3.Connection, task_id: int) -> Task:
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise AosError(
            f"No task {ids.render_id('task', task_id)}. Run: python aos.py task list"
        )
    return Task.from_row(row)


def get_run(conn: sqlite3.Connection, run_id: int) -> Run:
    row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise AosError(
            f"No run {ids.render_id('run', run_id)}. Run: python aos.py status"
        )
    return Run.from_row(row)


def evidence_count(conn: sqlite3.Connection, task_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) AS n FROM evidence WHERE task_id = ?", (task_id,)
    ).fetchone()["n"]


def related_decisions(conn: sqlite3.Connection, task: Task) -> list[Decision]:
    """Decisions attached to the task, plus project-level decisions."""
    rows = conn.execute(
        "SELECT * FROM decisions WHERE task_id = ? "
        "OR (task_id IS NULL AND project_id IS NOT NULL AND project_id = ?) "
        "ORDER BY id",
        (task.id, task.project_id),
    ).fetchall()
    return [Decision.from_row(r) for r in rows]


def memory_for_project(conn: sqlite3.Connection, project_id: int | None) -> list:
    """Active memory: global scope plus the task's project scope."""
    rows = conn.execute(
        "SELECT * FROM memory WHERE superseded_by IS NULL "
        "AND (scope = 'global' OR (project_id IS NOT NULL AND project_id = ?)) "
        "ORDER BY id",
        (project_id,),
    ).fetchall()
    from .models import MemoryItem

    return [MemoryItem.from_row(r) for r in rows]


# ---------------------------------------------------------------------------
# Public dict shapes (human-facing ids; used by CLI text and --json output)

def task_public(
    conn: sqlite3.Connection, task: Task, project_slug: str | None = None
) -> dict:
    if project_slug is None and task.project_id is not None:
        project = get_project(conn, task.project_id)
        project_slug = project.slug if project else None
    return {
        "id": ids.render_id("task", task.id),
        "title": task.title,
        "project": project_slug,
        "status": task.status,
        "kind": task.kind,
        "priority": task.priority,
        "assignee": task.assignee,
        "acceptance_md": task.acceptance_md,
        "branch_hint": task.branch_hint,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "closed_at": task.closed_at,
        "evidence_count": evidence_count(conn, task.id),
    }


def run_public(run: Run) -> dict:
    return {
        "id": ids.render_id("run", run.id),
        "task": ids.render_id("task", run.task_id),
        "agent": run.agent,
        "pack": ids.render_id("pack", run.pack_id) if run.pack_id else None,
        "anchor_commit": run.anchor_commit,
        "started_at": run.started_at,
        "ended_at": run.ended_at,
        "outcome": run.outcome,
        "summary_md": run.summary_md,
    }


def evidence_public(item: Evidence) -> dict:
    return {
        "id": ids.render_id("evidence", item.id),
        "task": ids.render_id("task", item.task_id),
        "run": ids.render_id("run", item.run_id) if item.run_id else None,
        "kind": item.kind,
        "ref": item.ref,
        "claim": item.claim,
        "sha256": item.sha256,
        "provenance": item.provenance,
        "verified": bool(item.verified),
        "created_at": item.created_at,
    }


def decision_public(item: Decision) -> dict:
    return {
        "id": ids.render_id("decision", item.id),
        "title": item.title,
        "status": item.status,
        "decision_md": item.decision_md,
        "decided_at": item.decided_at,
    }


def handoff_public(item: Handoff) -> dict:
    return {
        "id": ids.render_id("handoff", item.id),
        "task": ids.render_id("task", item.task_id),
        "from_agent": item.from_agent,
        "to_agent": item.to_agent,
        "created_at": item.created_at,
        "accepted_at": item.accepted_at,
    }


def event_public(row: sqlite3.Row) -> dict:
    import json

    return {
        "id": row["id"],
        "ts": row["ts"],
        "actor": row["actor"],
        "entity": row["entity"],
        "entity_id": row["entity_id"],
        "action": row["action"],
        "payload": json.loads(row["payload_json"]),
    }


# ---------------------------------------------------------------------------
# Mutations

def initialize(conn: sqlite3.Connection, root: Path) -> None:
    """First-time ledger bootstrap: schema_version + init event, one transaction."""
    with db.transaction(conn):
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
            (db.SCHEMA_VERSION,),
        )
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="system",
            entity_id=None,
            action="init",
            payload={"root": str(root)},
        )


def init_workspace(root: Path) -> tuple[Path, bool]:
    """Create (or heal) the .agentic-os workspace under `root`.

    Idempotent: re-running on the same schema version re-creates any missing
    folders/templates and changes nothing else.
    """
    aos_dir = root / utils.AOS_DIR_NAME
    conn, created = db.init_db(aos_dir / utils.DB_FILENAME)
    try:
        if created:
            initialize(conn, root)
        obsidian.ensure_layout(aos_dir)
        obsidian.write_adapter_templates(aos_dir)
        obsidian.write_home_and_conventions(conn, aos_dir)
    finally:
        conn.close()
    return aos_dir, created


def add_project(
    conn: sqlite3.Connection, *, slug: str, name: str, repo: str
) -> tuple[Project, bool]:
    validate_slug(slug)
    existing = get_project_by_slug(conn, slug)
    if existing is not None:
        return existing, False
    repo_path = Path(repo).expanduser().resolve()
    if not repo_path.is_dir():
        raise AosError(f"Repo path is not an existing directory: {repo_path}")
    now = utils.utc_now_iso()
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO projects (slug, name, repo_path, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (slug, name, str(repo_path), now, now),
        )
        project_id = cursor.lastrowid
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="project",
            entity_id=project_id,
            action="add",
            payload={"slug": slug, "name": name, "repo_path": str(repo_path)},
        )
    return get_project(conn, project_id), True


def add_task(
    conn: sqlite3.Connection,
    *,
    title: str,
    project_slug: str,
    kind: str = "code",
    acceptance: str | None = None,
    priority: int = 2,
) -> Task:
    title = title.strip()
    if not title:
        raise AosError("Task title must not be empty.")
    validate_enum(kind, TASK_KINDS, "task kind")
    project = get_project_by_slug(conn, project_slug)
    if project is None:
        raise AosError(
            f"No project '{project_slug}'. "
            f"Run: python aos.py project add {project_slug} --name NAME --repo PATH"
        )
    now = utils.utc_now_iso()
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO tasks (project_id, title, kind, status, priority, "
            "acceptance_md, created_at, updated_at) "
            "VALUES (?, ?, ?, 'ready', ?, ?, ?, ?)",
            (project.id, title, kind, priority, acceptance, now, now),
        )
        task_id = cursor.lastrowid
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="task",
            entity_id=task_id,
            action="add",
            payload={
                "title": title,
                "project": project.slug,
                "kind": kind,
                "status": "ready",
                "priority": priority,
            },
        )
    return get_task(conn, task_id)


def capture_inbox(conn: sqlite3.Connection, text: str) -> Task:
    text = text.strip()
    if not text:
        raise AosError("Nothing to capture: text must not be empty.")
    now = utils.utc_now_iso()
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO tasks (project_id, title, status, created_at, updated_at) "
            "VALUES (NULL, ?, 'inbox', ?, ?)",
            (text, now, now),
        )
        task_id = cursor.lastrowid
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="task",
            entity_id=task_id,
            action="add",
            payload={"title": text, "status": "inbox", "via": "in"},
        )
    return get_task(conn, task_id)


def _git_anchor(repo_path: Path) -> tuple[str | None, str | None]:
    """Read-only git HEAD lookup. Returns (anchor_commit, degradation_note).

    Never raises: no git, not a repo, no commits, timeout — all degrade to
    (None, note).
    """
    if not repo_path.is_dir():
        return None, f"repo path missing: {repo_path}"
    git = shutil.which("git")
    if git is None:
        return None, "git executable not found"
    try:
        probe = subprocess.run(
            [git, "rev-parse", "--is-inside-work-tree"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
        if probe.returncode != 0 or probe.stdout.strip() != "true":
            return None, "not inside a git work tree"
        head = subprocess.run(
            [git, "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
        if head.returncode != 0:
            return None, "git rev-parse HEAD failed (repo may have no commits)"
        return head.stdout.strip(), None
    except (OSError, subprocess.TimeoutExpired) as exc:
        return None, f"git unavailable ({exc.__class__.__name__})"


def start_run(conn: sqlite3.Connection, *, task_id: int, agent: str) -> Run:
    agent = agent.strip()
    if not agent:
        raise AosError("Agent name must not be empty.")
    task = get_task(conn, task_id)
    task_hid = ids.render_id("task", task.id)
    if task.status == "done":
        raise AosError(
            f"Task {task_hid} is done; cannot start a run on a closed task."
        )
    anchor, note = None, None
    if task.project_id is not None:
        project = get_project(conn, task.project_id)
        anchor, note = _git_anchor(Path(project.repo_path))
    else:
        note = "task has no project; no repo to anchor"
    now = utils.utc_now_iso()
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO runs (task_id, agent, anchor_commit, started_at) "
            "VALUES (?, ?, ?, ?)",
            (task.id, agent, anchor, now),
        )
        run_id = cursor.lastrowid
        conn.execute(
            "UPDATE tasks SET status = 'in_progress', updated_at = ? WHERE id = ?",
            (now, task.id),
        )
        payload = {
            "task": task_hid,
            "agent": agent,
            "anchor_commit": anchor,
            "task_status": {"from": task.status, "to": "in_progress"},
        }
        if note:
            payload["note"] = note
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="run",
            entity_id=run_id,
            action="start",
            payload=payload,
        )
    return get_run(conn, run_id)


def end_run(
    conn: sqlite3.Connection, *, run_id: int, outcome: str, summary: str
) -> Run:
    validate_enum(outcome, RUN_OUTCOMES, "run outcome")
    run = get_run(conn, run_id)
    run_hid = ids.render_id("run", run.id)
    if run.ended_at is not None:
        raise AosError(f"Run {run_hid} already ended at {run.ended_at}.")
    now = utils.utc_now_iso()
    with db.transaction(conn):
        conn.execute(
            "UPDATE runs SET ended_at = ?, outcome = ?, summary_md = ? WHERE id = ?",
            (now, outcome, summary, run.id),
        )
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="run",
            entity_id=run.id,
            action="end",
            payload={
                "task": ids.render_id("task", run.task_id),
                "outcome": outcome,
            },
        )
    return get_run(conn, run.id)


def add_evidence(
    conn: sqlite3.Connection,
    *,
    task_id: int,
    kind: str,
    ref: str,
    claim: str | None = None,
    provenance: str = "human",
) -> Evidence:
    validate_enum(kind, EVIDENCE_KINDS, "evidence kind")
    validate_provenance(provenance)
    task = get_task(conn, task_id)
    sha = None
    if kind == "file":
        file_path = Path(ref).expanduser()
        if not file_path.is_file():
            raise AosError(f"Evidence file not found: {ref}")
        sha = utils.sha256_file(file_path)
    now = utils.utc_now_iso()
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO evidence (task_id, claim, kind, ref, sha256, provenance, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (task.id, claim, kind, ref, sha, provenance, now),
        )
        evidence_id = cursor.lastrowid
        events.emit(
            conn,
            actor=provenance,
            entity="evidence",
            entity_id=evidence_id,
            action="add",
            payload={
                "task": ids.render_id("task", task.id),
                "kind": kind,
                "ref": ref,
                "claim": claim,
                "sha256": sha,
            },
        )
    row = conn.execute(
        "SELECT * FROM evidence WHERE id = ?", (evidence_id,)
    ).fetchone()
    return Evidence.from_row(row)


def mark_done(
    conn: sqlite3.Connection, *, task_id: int, no_evidence: bool = False
) -> Task:
    task = get_task(conn, task_id)
    task_hid = ids.render_id("task", task.id)
    if task.status == "done":
        raise AosError(f"Task {task_hid} is already done.")
    count = evidence_count(conn, task.id)
    override = False
    if count == 0:
        if not no_evidence:
            raise AosError(
                f"Task {task_hid} has no evidence; refusing to close. Add some: "
                f'python aos.py evidence add {task_hid} --kind note --ref "..." '
                "(or pass --no-evidence to override)"
            )
        override = True
    now = utils.utc_now_iso()
    with db.transaction(conn):
        conn.execute(
            "UPDATE tasks SET status = 'done', closed_at = ?, updated_at = ? "
            "WHERE id = ?",
            (now, now, task.id),
        )
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="task",
            entity_id=task.id,
            action="done",
            payload={
                "task": task_hid,
                "from_status": task.status,
                "evidence_count": count,
                "override": override,
            },
        )
        if override:
            events.emit(
                conn,
                actor=ACTOR_HUMAN,
                entity="task",
                entity_id=task.id,
                action="done_override",
                payload={"task": task_hid, "reason": "--no-evidence"},
            )
    return get_task(conn, task.id)


# ---------------------------------------------------------------------------
# Queries for CLI read commands

def list_tasks(
    conn: sqlite3.Connection,
    *,
    project_slug: str | None = None,
    status: str | None = None,
) -> list[dict]:
    clauses, params = [], []
    if project_slug is not None:
        project = get_project_by_slug(conn, project_slug)
        if project is None:
            raise AosError(
                f"No project '{project_slug}'. Run: python aos.py project add "
                f"{project_slug} --name NAME --repo PATH"
            )
        clauses.append("t.project_id = ?")
        params.append(project.id)
    if status is not None:
        validate_enum(status, TASK_STATUSES, "task status")
        clauses.append("t.status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT t.*, p.slug AS project_slug FROM tasks t "
        f"LEFT JOIN projects p ON p.id = t.project_id {where} ORDER BY t.id",
        params,
    ).fetchall()
    return [
        task_public(conn, Task.from_row(row), row["project_slug"])
        for row in rows
    ]


def show_task(conn: sqlite3.Connection, task_id: int) -> dict:
    task = get_task(conn, task_id)
    project = get_project(conn, task.project_id) if task.project_id else None
    runs = [
        Run.from_row(r)
        for r in conn.execute(
            "SELECT * FROM runs WHERE task_id = ? ORDER BY id", (task.id,)
        ).fetchall()
    ]
    evidence_items = [
        Evidence.from_row(r)
        for r in conn.execute(
            "SELECT * FROM evidence WHERE task_id = ? ORDER BY id", (task.id,)
        ).fetchall()
    ]
    handoffs = [
        Handoff.from_row(r)
        for r in conn.execute(
            "SELECT * FROM handoffs WHERE task_id = ? ORDER BY id", (task.id,)
        ).fetchall()
    ]
    decisions = related_decisions(conn, task)
    detail = task_public(conn, task, project.slug if project else None)
    detail["spec_md"] = task.spec_md
    return {
        "task": detail,
        "project": (
            {
                "slug": project.slug,
                "name": project.name,
                "repo_path": project.repo_path,
                "status": project.status,
                "autonomy_level": project.autonomy_level,
            }
            if project
            else None
        ),
        "runs": [run_public(r) for r in runs],
        "decisions": [decision_public(d) for d in decisions],
        "evidence": [evidence_public(e) for e in evidence_items],
        "handoffs": [handoff_public(h) for h in handoffs],
    }


def status_summary(conn: sqlite3.Connection) -> dict:
    project_count = conn.execute(
        "SELECT COUNT(*) AS n FROM projects"
    ).fetchone()["n"]
    open_count = conn.execute(
        "SELECT COUNT(*) AS n FROM tasks WHERE status != 'done'"
    ).fetchone()["n"]
    recent_rows = conn.execute(
        "SELECT t.*, p.slug AS project_slug FROM tasks t "
        "LEFT JOIN projects p ON p.id = t.project_id ORDER BY t.id DESC LIMIT 10"
    ).fetchall()
    missing_rows = conn.execute(
        "SELECT t.*, p.slug AS project_slug FROM tasks t "
        "LEFT JOIN projects p ON p.id = t.project_id "
        "WHERE t.status != 'done' AND NOT EXISTS "
        "(SELECT 1 FROM evidence e WHERE e.task_id = t.id) ORDER BY t.id"
    ).fetchall()
    run_rows = conn.execute(
        "SELECT * FROM runs ORDER BY id DESC LIMIT 5"
    ).fetchall()
    return {
        "projects": project_count,
        "open_tasks": open_count,
        "recent_tasks": [
            task_public(conn, Task.from_row(r), r["project_slug"])
            for r in recent_rows
        ],
        "tasks_missing_evidence": [
            task_public(conn, Task.from_row(r), r["project_slug"])
            for r in missing_rows
        ],
        "last_runs": [run_public(Run.from_row(r)) for r in run_rows],
    }


def log_events(
    conn: sqlite3.Connection,
    *,
    task_id: int | None = None,
    today: bool = False,
    limit: int = 50,
) -> list[dict]:
    if task_id is not None:
        task = get_task(conn, task_id)  # validates existence
        run_ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM runs WHERE task_id = ?", (task.id,)
            ).fetchall()
        ]
        evidence_ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM evidence WHERE task_id = ?", (task.id,)
            ).fetchall()
        ]
        pack_ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM packs WHERE task_id = ?", (task.id,)
            ).fetchall()
        ]
        handoff_ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM handoffs WHERE task_id = ?", (task.id,)
            ).fetchall()
        ]
        clauses = ["(entity = 'task' AND entity_id = ?)"]
        params: list = [task.id]
        for entity, id_list in (
            ("run", run_ids),
            ("evidence", evidence_ids),
            ("pack", pack_ids),
            ("handoff", handoff_ids),
        ):
            if id_list:
                marks = ",".join("?" * len(id_list))
                clauses.append(f"(entity = '{entity}' AND entity_id IN ({marks}))")
                params.extend(id_list)
        rows = conn.execute(
            f"SELECT * FROM events WHERE {' OR '.join(clauses)} ORDER BY id",
            params,
        ).fetchall()
    elif today:
        rows = conn.execute(
            "SELECT * FROM events WHERE ts LIKE ? ORDER BY id",
            (utils.utc_today() + "%",),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        rows = list(reversed(rows))
    return [event_public(r) for r in rows]
