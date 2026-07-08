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
    AGENT_KINDS,
    EVIDENCE_KINDS,
    MEMORY_CONFIDENCES,
    MEMORY_KINDS,
    MEMORY_SCOPES,
    RUN_OUTCOMES,
    TASK_KINDS,
    TASK_STATUSES,
    Agent,
    Decision,
    Evidence,
    Handoff,
    MemoryItem,
    Pack,
    Project,
    Run,
    Task,
    validate_agent_name,
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


def memory_for_project(
    conn: sqlite3.Connection, project_id: int | None
) -> list[MemoryItem]:
    """Pack MEMORY inclusion rule: live memory only — scope=global plus the
    pinned project's scope; live means valid_until is NULL or in the future
    AND superseded_by is NULL; the latest row (highest id) per
    (scope, project, key) wins; ordered by scope then key."""
    now = utils.utc_now_iso()
    rows = conn.execute(
        "SELECT * FROM memory WHERE superseded_by IS NULL "
        "AND (valid_until IS NULL OR valid_until > ?) "
        "AND (scope = 'global' OR (project_id IS NOT NULL AND project_id = ?)) "
        "ORDER BY id",
        (now, project_id),
    ).fetchall()
    latest: dict[tuple, MemoryItem] = {}
    for row in rows:
        item = MemoryItem.from_row(row)
        latest[(item.scope, item.project_id, item.key)] = item
    return sorted(latest.values(), key=lambda m: (m.scope, m.key, m.id))


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


def memory_public(
    conn: sqlite3.Connection, item: MemoryItem, project_slug: str | None = None
) -> dict:
    if project_slug is None and item.project_id is not None:
        project = get_project(conn, item.project_id)
        project_slug = project.slug if project else None
    live = item.superseded_by is None and (
        item.valid_until is None or item.valid_until > utils.utc_now_iso()
    )
    return {
        "id": ids.render_id("memory", item.id),
        "scope": item.scope,
        "project": project_slug,
        "kind": item.kind,
        "key": item.key,
        "value_md": item.value_md,
        "source": item.source,
        "confidence": item.confidence,
        "valid_from": item.valid_from,
        "valid_until": item.valid_until,
        "superseded_by": (
            ids.render_id("memory", item.superseded_by)
            if item.superseded_by
            else None
        ),
        "updated_at": item.updated_at,
        "live": live,
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
    spec: str | None = None,
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
            "acceptance_md, spec_md, created_at, updated_at) "
            "VALUES (?, ?, ?, 'ready', ?, ?, ?, ?, ?)",
            (project.id, title, kind, priority, acceptance, spec, now, now),
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


#: The only manual status moves; `done` stays exclusively `aos done`'s.
LEGAL_TASK_TRANSITIONS = (
    ("inbox", "ready"),
    ("ready", "in_progress"),
    ("in_progress", "ready"),
)

TASK_PRIORITY_RANGE = (1, 5)


def assign_task(
    conn: sqlite3.Connection, *, task_id: int, project_slug: str
) -> tuple[Task, bool]:
    """Assign a project to a task (or move a non-done task between
    projects). Status never changes here; `task status` owns transitions.
    Returns (task, changed) — same-project re-assign is a no-op, no event.
    """
    task = get_task(conn, task_id)
    task_hid = ids.render_id("task", task.id)
    if task.status == "done":
        raise AosError(
            f"Task {task_hid} is done; refusing to reassign a closed task."
        )
    project = get_project_by_slug(conn, project_slug)
    if project is None:
        raise AosError(
            f"No project '{project_slug}'. Run: python aos.py project add "
            f"{project_slug} --name NAME --repo PATH"
        )
    if task.project_id == project.id:
        return task, False
    from_project = None
    if task.project_id is not None:
        old = get_project(conn, task.project_id)
        from_project = old.slug if old else None
    now = utils.utc_now_iso()
    with db.transaction(conn):
        conn.execute(
            "UPDATE tasks SET project_id = ?, updated_at = ? WHERE id = ?",
            (project.id, now, task.id),
        )
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="task",
            entity_id=task.id,
            action="assign",
            payload={
                "task": task_hid,
                "project": project.slug,
                "from_project": from_project,
            },
        )
    return get_task(conn, task.id), True


def edit_task(
    conn: sqlite3.Connection,
    *,
    task_id: int,
    title: str | None = None,
    kind: str | None = None,
    priority: int | None = None,
    acceptance: str | None = None,
    spec: str | None = None,
) -> tuple[Task, list[str]]:
    """Edit an open task's fields. Done tasks are frozen — no exceptions.
    Returns (task, changed field names); the event payload carries the
    field NAMES only, never the values."""
    task = get_task(conn, task_id)
    task_hid = ids.render_id("task", task.id)
    if task.status == "done":
        raise AosError(
            f"Task {task_hid} is done; closed tasks are frozen — "
            "append evidence or decisions instead of editing."
        )
    updates: dict[str, object] = {}
    changed: list[str] = []
    if title is not None:
        title = title.strip()
        if not title:
            raise AosError("Task title must not be empty.")
        updates["title"] = title
        changed.append("title")
    if kind is not None:
        validate_enum(kind, TASK_KINDS, "task kind")
        updates["kind"] = kind
        changed.append("kind")
    if priority is not None:
        low, high = TASK_PRIORITY_RANGE
        if not low <= priority <= high:
            raise AosError(f"Task priority must be between {low} and {high}.")
        updates["priority"] = priority
        changed.append("priority")
    if acceptance is not None:
        if not acceptance.strip():
            raise AosError("--accept must not be empty.")
        updates["acceptance_md"] = acceptance
        changed.append("accept")
    if spec is not None:
        if not spec.strip():
            raise AosError("--spec must not be empty.")
        updates["spec_md"] = spec
        changed.append("spec")
    if not updates:
        raise AosError(
            "Nothing to edit: pass at least one of "
            "--title/--kind/--priority/--accept/--spec."
        )
    now = utils.utc_now_iso()
    with db.transaction(conn):
        assignments = ", ".join(f"{column} = ?" for column in updates)
        conn.execute(
            f"UPDATE tasks SET {assignments}, updated_at = ? WHERE id = ?",
            (*updates.values(), now, task.id),
        )
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="task",
            entity_id=task.id,
            action="edit",
            payload={"task": task_hid, "changed": changed},
        )
    return get_task(conn, task.id), changed


def set_task_status(
    conn: sqlite3.Connection, *, task_id: int, status: str
) -> tuple[Task, str]:
    """Manual status transition, legal moves only. Returns (task, from)."""
    validate_enum(status, TASK_STATUSES, "task status")
    task = get_task(conn, task_id)
    task_hid = ids.render_id("task", task.id)
    if status == "done":
        raise AosError(
            f"Refusing: 'done' requires evidence. Run: python aos.py done {task_hid}"
        )
    if task.status == "done":
        raise AosError(
            f"Task {task_hid} is done; closed tasks keep their status."
        )
    legal = ", ".join(f"{a}→{b}" for a, b in LEGAL_TASK_TRANSITIONS)
    if (task.status, status) not in LEGAL_TASK_TRANSITIONS:
        raise AosError(
            f"Illegal transition {task.status}→{status}. Legal: {legal}."
        )
    if task.status == "inbox" and task.project_id is None:
        raise AosError(
            f"Task {task_hid} has no project; assign a project first: "
            f"python aos.py task assign {task_hid} -p PROJECT"
        )
    now = utils.utc_now_iso()
    with db.transaction(conn):
        conn.execute(
            "UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, task.id),
        )
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="task",
            entity_id=task.id,
            action="status",
            payload={"task": task_hid, "from": task.status, "to": status},
        )
    return get_task(conn, task.id), task.status


def add_decision(
    conn: sqlite3.Connection,
    *,
    title: str,
    project_slug: str,
    decision: str,
    alternatives: str | None = None,
    task_id: int | None = None,
) -> Decision:
    title = title.strip()
    if not title:
        raise AosError("Decision title must not be empty.")
    if not decision or not decision.strip():
        raise AosError("Decision text (--decision) must not be empty.")
    project = get_project_by_slug(conn, project_slug)
    if project is None:
        raise AosError(
            f"No project '{project_slug}'. "
            f"Run: python aos.py project add {project_slug} --name NAME --repo PATH"
        )
    task = None
    if task_id is not None:
        task = get_task(conn, task_id)
        if task.project_id != project.id:
            raise AosError(
                f"Task {ids.render_id('task', task.id)} does not belong to "
                f"project '{project.slug}'; a decision's task and project "
                "must match."
            )
    now = utils.utc_now_iso()
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO decisions (project_id, task_id, title, decision_md, "
            "alternatives_md, status, decided_at) "
            "VALUES (?, ?, ?, ?, ?, 'accepted', ?)",
            (
                project.id,
                task.id if task else None,
                title,
                decision,
                alternatives,
                now,
            ),
        )
        decision_id = cursor.lastrowid
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="decision",
            entity_id=decision_id,
            action="add",
            payload={
                "decision": ids.render_id("decision", decision_id),
                "title": title,
                "project": project.slug,
                "task": ids.render_id("task", task.id) if task else None,
                "status": "accepted",
            },
        )
    row = conn.execute(
        "SELECT * FROM decisions WHERE id = ?", (decision_id,)
    ).fetchone()
    return Decision.from_row(row)


def get_handoff(conn: sqlite3.Connection, handoff_id: int) -> Handoff:
    row = conn.execute(
        "SELECT * FROM handoffs WHERE id = ?", (handoff_id,)
    ).fetchone()
    if row is None:
        raise AosError(
            f"No handoff {ids.render_id('handoff', handoff_id)}. "
            "Run: python aos.py log"
        )
    return Handoff.from_row(row)


def create_handoff(
    conn: sqlite3.Connection,
    *,
    task_id: int,
    from_agent: str,
    to_agent: str,
    state: str,
) -> Handoff:
    from_agent = from_agent.strip()
    to_agent = to_agent.strip()
    if not from_agent or not to_agent:
        raise AosError("Handoff --from and --to agent names must not be empty.")
    if not state or not state.strip():
        raise AosError("Handoff state (--state) must not be empty.")
    task = get_task(conn, task_id)
    now = utils.utc_now_iso()
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO handoffs (task_id, from_agent, to_agent, state_md, "
            "created_at) VALUES (?, ?, ?, ?, ?)",
            (task.id, from_agent, to_agent, state, now),
        )
        handoff_id = cursor.lastrowid
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="handoff",
            entity_id=handoff_id,
            action="create",
            payload={
                "handoff": ids.render_id("handoff", handoff_id),
                "task": ids.render_id("task", task.id),
                "from_agent": from_agent,
                "to_agent": to_agent,
            },
        )
    return get_handoff(conn, handoff_id)


def accept_handoff(conn: sqlite3.Connection, *, handoff_id: int) -> Handoff:
    handoff = get_handoff(conn, handoff_id)
    handoff_hid = ids.render_id("handoff", handoff.id)
    if handoff.accepted_at is not None:
        raise AosError(
            f"Handoff {handoff_hid} was already accepted at {handoff.accepted_at}."
        )
    now = utils.utc_now_iso()
    with db.transaction(conn):
        conn.execute(
            "UPDATE handoffs SET accepted_at = ? WHERE id = ?", (now, handoff.id)
        )
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="handoff",
            entity_id=handoff.id,
            action="accept",
            payload={
                "handoff": handoff_hid,
                "task": ids.render_id("task", handoff.task_id),
                "accepted_at": now,
            },
        )
    return get_handoff(conn, handoff.id)


def get_memory(conn: sqlite3.Connection, memory_id: int) -> MemoryItem:
    row = conn.execute(
        "SELECT * FROM memory WHERE id = ?", (memory_id,)
    ).fetchone()
    if row is None:
        raise AosError(
            f"No memory {ids.render_id('memory', memory_id)}. "
            "Run: python aos.py memory list"
        )
    return MemoryItem.from_row(row)


def add_memory(
    conn: sqlite3.Connection,
    *,
    scope: str,
    project_slug: str | None = None,
    kind: str,
    key: str,
    value: str,
    source: str,
    confidence: str,
    valid_until: str | None = None,
    supersedes_id: int | None = None,
) -> MemoryItem:
    validate_enum(scope, MEMORY_SCOPES, "memory scope")
    validate_enum(kind, MEMORY_KINDS, "memory kind")
    validate_enum(confidence, MEMORY_CONFIDENCES, "memory confidence")
    key = key.strip()
    if not key:
        raise AosError("Memory --key must not be empty.")
    if not value or not value.strip():
        raise AosError("Memory --value must not be empty.")
    source = source.strip()
    if not source:
        raise AosError("Memory --source must not be empty.")
    project = None
    if scope == "project":
        if not project_slug:
            raise AosError("--project is required when --scope is 'project'.")
        project = get_project_by_slug(conn, project_slug)
        if project is None:
            raise AosError(
                f"No project '{project_slug}'. Run: python aos.py project add "
                f"{project_slug} --name NAME --repo PATH"
            )
    elif project_slug is not None:
        raise AosError("--project only applies when --scope is 'project'.")
    if valid_until is not None:
        utils.validate_date(valid_until, "--valid-until")
    old = None
    if supersedes_id is not None:
        old = get_memory(conn, supersedes_id)
        if old.superseded_by is not None:
            raise AosError(
                f"Memory {ids.render_id('memory', old.id)} is already "
                f"superseded by {ids.render_id('memory', old.superseded_by)}."
            )
    now = utils.utc_now_iso()
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO memory (scope, project_id, kind, key, value_md, "
            "source, confidence, valid_from, valid_until, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                scope,
                project.id if project else None,
                kind,
                key,
                value,
                source,
                confidence,
                now,
                valid_until,
                now,
            ),
        )
        memory_id = cursor.lastrowid
        if old is not None:
            conn.execute(
                "UPDATE memory SET superseded_by = ?, updated_at = ? "
                "WHERE id = ?",
                (memory_id, now, old.id),
            )
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="memory",
            entity_id=memory_id,
            action="add",
            payload={
                "memory": ids.render_id("memory", memory_id),
                "scope": scope,
                "project": project.slug if project else None,
                "kind": kind,
                "key": key,
                "confidence": confidence,
                "valid_until": valid_until,
                "supersedes": (
                    ids.render_id("memory", old.id) if old else None
                ),
            },
        )
    return get_memory(conn, memory_id)


def list_memory(
    conn: sqlite3.Connection,
    *,
    scope: str | None = None,
    project_slug: str | None = None,
) -> list[dict]:
    """Every row, including retired and superseded ones — memory never
    silently disappears; retired rows carry their valid_until."""
    clauses, params = [], []
    if scope is not None:
        validate_enum(scope, MEMORY_SCOPES, "memory scope")
        clauses.append("m.scope = ?")
        params.append(scope)
    if project_slug is not None:
        project = get_project_by_slug(conn, project_slug)
        if project is None:
            raise AosError(
                f"No project '{project_slug}'. Run: python aos.py project add "
                f"{project_slug} --name NAME --repo PATH"
            )
        clauses.append("m.project_id = ?")
        params.append(project.id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT m.*, p.slug AS project_slug FROM memory m "
        f"LEFT JOIN projects p ON p.id = m.project_id {where} ORDER BY m.id",
        params,
    ).fetchall()
    return [
        memory_public(conn, MemoryItem.from_row(row), row["project_slug"])
        for row in rows
    ]


def retire_memory(conn: sqlite3.Connection, *, memory_id: int) -> MemoryItem:
    item = get_memory(conn, memory_id)
    memory_hid = ids.render_id("memory", item.id)
    now = utils.utc_now_iso()
    if item.valid_until is not None and item.valid_until <= now:
        raise AosError(
            f"Memory {memory_hid} is already retired "
            f"(valid_until {item.valid_until})."
        )
    with db.transaction(conn):
        conn.execute(
            "UPDATE memory SET valid_until = ?, updated_at = ? WHERE id = ?",
            (now, now, item.id),
        )
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="memory",
            entity_id=item.id,
            action="retire",
            payload={"memory": memory_hid, "valid_until": now},
        )
    return get_memory(conn, item.id)


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
    # Lifecycle gate (D-v0.2.4): runs consume the ready→in_progress
    # transition, so inbox (untriaged) and in_progress (already running)
    # tasks must go through `task status` first.
    if task.status != "ready":
        raise AosError(
            f"Task {task_hid} is {task.status}; only ready tasks can start "
            f"a run. Run: python aos.py task status {task_hid} ready"
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
    extra_payload: dict | None = None,
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
        payload = {
            "task": ids.render_id("task", task.id),
            "kind": kind,
            "ref": ref,
            "claim": claim,
            "sha256": sha,
        }
        if extra_payload:
            payload.update(extra_payload)
        events.emit(
            conn,
            actor=provenance,
            entity="evidence",
            entity_id=evidence_id,
            action="add",
            payload=payload,
        )
    row = conn.execute(
        "SELECT * FROM evidence WHERE id = ?", (evidence_id,)
    ).fetchone()
    return Evidence.from_row(row)


def _run_git(git: str, repo_path: Path, *args: str) -> subprocess.CompletedProcess:
    """Read-only git query: list-form args, timeout, output captured.

    errors='replace' — git output is arbitrary bytes (commit subjects,
    i18n.logOutputEncoding re-encoding); a strict decode would crash a
    valid ingest with exit 2 instead of degrading gracefully."""
    return subprocess.run(
        [git, *args],
        cwd=repo_path,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=GIT_TIMEOUT_SECONDS,
    )


def add_git_evidence(
    conn: sqlite3.Connection,
    *,
    task_id: int,
    commit: str,
    repo: str | None = None,
    claim: str | None = None,
) -> Evidence:
    """Verified commit evidence: resolve `commit` in the task's project repo
    (or --repo) via read-only git, store the FULL sha as the ref, and default
    the claim to the commit subject. Unknown commit / no repo → exit 1."""
    task = get_task(conn, task_id)
    task_hid = ids.render_id("task", task.id)
    if repo is not None:
        repo_path = Path(repo).expanduser().resolve()
    elif task.project_id is not None:
        project = get_project(conn, task.project_id)
        repo_path = Path(project.repo_path)
    else:
        raise AosError(
            f"Task {task_hid} has no project; pass --repo PATH to name the "
            "git repository."
        )
    if not repo_path.is_dir():
        raise AosError(f"Repo path is not an existing directory: {repo_path}")
    commit = commit.strip()
    if not commit or commit.startswith("-"):
        raise AosError(
            "Invalid commit ref: must be a non-empty ref that does not "
            "start with '-'."
        )
    git = shutil.which("git")
    if git is None:
        raise AosError("git executable not found; cannot verify the commit.")
    try:
        probe = _run_git(git, repo_path, "rev-parse", "--is-inside-work-tree")
        if probe.returncode != 0 or probe.stdout.strip() != "true":
            raise AosError(f"Not a git repository: {repo_path}")
        resolved = _run_git(
            git, repo_path, "rev-parse", "--verify", "--quiet",
            f"{commit}^{{commit}}",
        )
        if resolved.returncode != 0 or not resolved.stdout.strip():
            raise AosError(
                f"Unknown commit {commit!r} in {repo_path}. "
                f"Check: git -C {repo_path} log --oneline"
            )
        sha = resolved.stdout.strip()
        subject = None
        subject_proc = _run_git(git, repo_path, "show", "-s", "--format=%s", sha)
        if subject_proc.returncode == 0 and subject_proc.stdout.strip():
            subject = " ".join(subject_proc.stdout.split())[:200]
        diffstat = None
        stat_proc = _run_git(git, repo_path, "show", "--stat", "--format=", sha)
        if stat_proc.returncode == 0:
            stat_lines = [
                line.strip() for line in stat_proc.stdout.splitlines()
                if line.strip()
            ]
            if stat_lines:
                diffstat = stat_lines[-1][:200]
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AosError(
            f"git unavailable ({exc.__class__.__name__}); "
            "cannot verify the commit."
        )
    return add_evidence(
        conn,
        task_id=task.id,
        kind="commit",
        ref=sha,
        claim=claim if claim is not None else subject,
        extra_payload={
            "repo": str(repo_path),
            "subject": subject,
            "diffstat": diffstat,
            "via": "git",
        },
    )


def mark_done(
    conn: sqlite3.Connection,
    *,
    task_id: int,
    no_evidence: bool = False,
    reason: str | None = None,
) -> Task:
    task = get_task(conn, task_id)
    task_hid = ids.render_id("task", task.id)
    if task.status == "done":
        raise AosError(f"Task {task_hid} is already done.")
    # Override policy (D-v0.2.5): closing without evidence is journaled and
    # must say why; a reason without the override flag is flag misuse, and
    # so is the override flag when evidence actually exists.
    reason = reason.strip() if reason is not None else None
    if reason is not None and not no_evidence:
        raise AosError(
            "--reason only applies with --no-evidence; an evidence-gated "
            "done needs no justification."
        )
    if no_evidence and not reason:
        raise AosError(
            f"done --no-evidence requires --reason TEXT saying why "
            f"{task_hid} closes without evidence; the reason is journaled."
        )
    count = evidence_count(conn, task.id)
    if no_evidence and count > 0:
        raise AosError(
            f"Task {task_hid} has {count} evidence row(s); --no-evidence "
            f"does not apply. Run: python aos.py done {task_hid}"
        )
    override = False
    if count == 0:
        if not no_evidence:
            raise AosError(
                f"Task {task_hid} has no evidence; refusing to close. Add some: "
                f'python aos.py evidence add {task_hid} --kind note --ref "..." '
                "(or pass --no-evidence --reason TEXT to override)"
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
                payload={
                    "task": task_hid,
                    "reason": reason,
                    "via": "--no-evidence",
                },
            )
    return get_task(conn, task.id)


# ---------------------------------------------------------------------------
# Agent registry (registry only — Agentic OS never executes agents)

def get_agent(conn: sqlite3.Connection, name: str) -> Agent | None:
    row = conn.execute(
        "SELECT * FROM agents WHERE name = ?", (name,)
    ).fetchone()
    return Agent.from_row(row) if row else None


def agent_public(agent: Agent) -> dict:
    return {
        "name": agent.name,
        "kind": agent.kind,
        "capabilities": agent.capabilities(),
        "notes": agent.notes,
        "invoke_hint": agent.invoke_hint,
        "trust_level": agent.trust_level,
    }


def _clean_capabilities(capabilities: list[str] | None) -> list[str]:
    cleaned = []
    for capability in capabilities or []:
        capability = " ".join(capability.split())
        if not capability:
            raise AosError("--capability values must not be empty.")
        cleaned.append(capability)
    return cleaned


def add_agent(
    conn: sqlite3.Connection,
    *,
    name: str,
    kind: str = "generic",
    notes: str | None = None,
    capabilities: list[str] | None = None,
) -> Agent:
    validate_agent_name(name)
    validate_enum(kind, AGENT_KINDS, "agent kind")
    caps = _clean_capabilities(capabilities)
    if get_agent(conn, name) is not None:
        raise AosError(
            f"Agent '{name}' already exists. "
            f"Run: python aos.py agent update {name}"
        )
    import json

    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO agents (name, kind, capabilities_json, notes) "
            "VALUES (?, ?, ?, ?)",
            (name, kind, json.dumps(caps), notes),
        )
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="agent",
            entity_id=cursor.lastrowid,
            action="add",
            payload={"agent": name, "kind": kind, "capabilities": caps},
        )
    return get_agent(conn, name)


def update_agent(
    conn: sqlite3.Connection,
    *,
    name: str,
    notes: str | None = None,
    capabilities: list[str] | None = None,
) -> tuple[Agent, list[str]]:
    agent = get_agent(conn, name)
    if agent is None:
        raise AosError(
            f"No agent '{name}'. Run: python aos.py agent add {name}"
        )
    import json

    updates: dict[str, object] = {}
    changed: list[str] = []
    if notes is not None:
        if not notes.strip():
            raise AosError("--notes must not be empty.")
        updates["notes"] = notes
        changed.append("notes")
    if capabilities is not None:
        updates["capabilities_json"] = json.dumps(
            _clean_capabilities(capabilities)
        )
        changed.append("capabilities")
    if not updates:
        raise AosError(
            "Nothing to update: pass at least one of --notes/--capability."
        )
    with db.transaction(conn):
        assignments = ", ".join(f"{column} = ?" for column in updates)
        conn.execute(
            f"UPDATE agents SET {assignments} WHERE id = ?",
            (*updates.values(), agent.id),
        )
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="agent",
            entity_id=agent.id,
            action="update",
            payload={"agent": name, "changed": changed},
        )
    return get_agent(conn, name), changed


def list_agents(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM agents ORDER BY name").fetchall()
    return [agent_public(Agent.from_row(row)) for row in rows]


# ---------------------------------------------------------------------------
# Queries for CLI read commands

def list_tasks(
    conn: sqlite3.Connection,
    *,
    project_slug: str | None = None,
    status: str | None = None,
    kind: str | None = None,
    missing_evidence: bool = False,
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
    if kind is not None:
        validate_enum(kind, TASK_KINDS, "task kind")
        clauses.append("t.kind = ?")
        params.append(kind)
    if missing_evidence:
        clauses.append(
            "NOT EXISTS (SELECT 1 FROM evidence e WHERE e.task_id = t.id)"
        )
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
