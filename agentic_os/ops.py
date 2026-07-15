"""Domain operations. Every mutating operation here writes its domain row(s)
AND an events row in the SAME transaction — if either fails, both roll back.

Events are emitted via the module object (``events.emit``) so tests can patch
the emit function and prove the rollback.
"""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from . import db, events, ids, obsidian, protocols, secretscan, utils
from .models import (
    AGENT_KINDS,
    EVIDENCE_KINDS,
    MEMORY_CONFIDENCES,
    MEMORY_KINDS,
    MEMORY_SCOPES,
    MEMORY_STATUS_LIVE,
    MEMORY_STATUS_RETIRED,
    MEMORY_STATUSES,
    RUN_OUTCOMES,
    TASK_KINDS,
    TASK_STATUSES,
    Agent,
    ClaimHashError,
    Decision,
    Evidence,
    Handoff,
    MemoryItem,
    Pack,
    Project,
    Run,
    Task,
    hash_prefix,
    is_claim_hash,
    validate_agent_name,
    validate_enum,
    validate_provenance,
    validate_slug,
)
from .utils import AosError

ACTOR_HUMAN = "human"

GIT_TIMEOUT_SECONDS = 5


# ---------------------------------------------------------------------------
# U-C3 warn-on-write (D-v0.2.15): the trusted human CLI boundary accepts
# secret-shaped text into the canonical domain row (the append-only ledger
# stays honest) but the human is warned on stderr and the mutation event
# carries safe metadata doctor can find later. The event payload itself
# never carries a matched value: events.emit redacts every secret-shaped
# string leaf via secretscan.redact_tree. Packs and dropfile ingest keep
# their hard refusals.

def _scan_trusted_write(
    entity: str, fields: list[tuple[str, str | None]]
) -> tuple[dict | None, str | None]:
    """Scan canonical human-supplied field values AFTER normal validation.

    Returns (event metadata, stderr warning line) — both None when nothing
    is secret-shaped. Both carry field and pattern NAMES only, never the
    matched value or anything derived from it.
    """
    unknown = sorted(
        {label for label, _ in fields} - secretscan.TRUSTED_FIELD_LABELS
    )
    if unknown:
        # Programming error, not user input: doctor reports event metadata
        # field names only from the fixed allowlist, so an unregistered
        # label would journal metadata doctor refuses to show.
        raise ValueError(
            "unregistered trusted-write field label(s): " + ", ".join(unknown)
        )
    findings = secretscan.scan_fields(fields)
    if not findings:
        return None, None
    field_names = [label for label, _ in findings]
    patterns = secretscan.merge_pattern_names(findings)
    metadata = {
        "secret_warning": True,
        "secret_fields": field_names,
        "secret_patterns": patterns,
    }
    warning = (
        f"WARNING: secret-shaped text in {entity} field(s) "
        f"{', '.join(field_names)} (patterns: {', '.join(patterns)}). "
        "The write succeeded and this text can reach context packs, the "
        "Obsidian mirror, and exports — if it is a real credential, rotate "
        "it and remove it from the ledger. doctor flags affected records."
    )
    return metadata, warning


def _warn_secret(warning: str | None) -> None:
    """Print AFTER the transaction commits: the warning must accompany a
    successful mutation, never a rolled-back one. stderr only, so stdout
    (including --json documents) stays byte-clean."""
    if warning:
        print(warning, file=sys.stderr)


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


def claim_is_eligible(item: MemoryItem, now: str | None = None) -> bool:
    """THE eligibility predicate for ordinary retrieval (U-M2, M2.7).

    One definition, used by packs, `memory show`/`list`'s `live` flag, the pin
    gate and doctor — so "what a normal command will feed an agent" can never
    mean two different things in two places.

    status=live only: proposed, contested, quarantined and retired claims stay
    out of every ordinary context pack. Expiry and supersession still apply on
    top — pinning is not on this list, because pinning is ordering, never
    permission.
    """
    if now is None:
        now = utils.utc_now_iso()
    return (
        item.status == MEMORY_STATUS_LIVE
        and item.superseded_by is None
        and (item.valid_until is None or item.valid_until > now)
    )


def memory_for_project(
    conn: sqlite3.Connection, project_id: int | None
) -> list[MemoryItem]:
    """Pack MEMORY inclusion rule: eligible claims only — scope=global plus
    the pinned project's scope; eligible means status='live' AND
    superseded_by IS NULL AND valid_until is NULL or in the future; the latest
    row (highest id) per (scope, project, key) wins.

    Order (M2.7): pinned eligible claims first, unpinned second, and inside
    each group the existing stable (scope, key, id) ordering — pinning changes
    the order and nothing else.

    Hashes are NOT re-verified here (D-v0.3.21): integrity is enforced at
    write time and audited by doctor. A read path that refused would let one
    damaged row block every pack in the workspace, and one that silently
    dropped rows would be worse still.
    """
    now = utils.utc_now_iso()
    rows = conn.execute(
        "SELECT * FROM memory WHERE status = ? AND superseded_by IS NULL "
        "AND (valid_until IS NULL OR valid_until > ?) "
        "AND (scope = 'global' OR (project_id IS NOT NULL AND project_id = ?)) "
        "ORDER BY id",
        (MEMORY_STATUS_LIVE, now, project_id),
    ).fetchall()
    latest: dict[tuple, MemoryItem] = {}
    for row in rows:
        item = MemoryItem.from_row(row)
        # Dedupe BEFORE ordering: which claim is current is a lifecycle
        # question, and a pin must not resurrect a stale row for its key.
        latest[(item.scope, item.project_id, item.key)] = item
    return sorted(
        latest.values(),
        key=lambda m: (0 if m.pinned else 1, m.scope, m.key, m.id),
    )


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
    """The public claim shape. Never raises on a damaged row: administrative
    listing must show an invalid claim, not hide it (M2.8)."""
    if project_slug is None and item.project_id is not None:
        project = get_project(conn, item.project_id)
        project_slug = project.slug if project else None
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
        "status": item.status,
        "pinned": bool(item.pinned),
        "evidence": [
            ids.render_id("evidence", eid)
            for eid in memory_evidence_ids(conn, item.id)
        ],
        "content_sha256": item.content_sha256,
        # `live` keeps its established name and now carries the full
        # eligibility answer: a caller asking "will an agent see this?" gets
        # the same yes/no the pack builder uses.
        "live": claim_is_eligible(item),
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


def init_workspace(root: Path, *, refresh_mirror: bool = True) -> tuple[Path, bool]:
    """Create (or heal) the .agentic-os workspace under `root`.

    Idempotent: re-running on the same schema version re-creates any missing
    folders/templates and changes nothing else.

    `refresh_mirror=False` (U-E2 eco) skips the idempotent mirror re-heal on
    an ALREADY-initialized workspace — the one piece of implicit, optional
    derived work in the baseline, and fully regenerable with `sync`. A
    freshly created workspace always heals regardless: a new workspace that
    has no mirror is not usable. Default True keeps every existing caller on
    the baseline path byte-for-byte.
    """
    aos_dir = root / utils.AOS_DIR_NAME
    conn, created = db.init_db(aos_dir / utils.DB_FILENAME)
    try:
        if created:
            initialize(conn, root)
        if created or refresh_mirror:
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
    # Slug and resolved repo path are human-selected and copied into event
    # and mirror surfaces, so they are scanned like the display name.
    secret_meta, secret_warning = _scan_trusted_write(
        "project",
        [("slug", slug), ("name", name), ("repo_path", str(repo_path))],
    )
    now = utils.utc_now_iso()
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO projects (slug, name, repo_path, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (slug, name, str(repo_path), now, now),
        )
        project_id = cursor.lastrowid
        payload = {"slug": slug, "name": name, "repo_path": str(repo_path)}
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="project",
            entity_id=project_id,
            action="add",
            payload=payload,
        )
    _warn_secret(secret_warning)
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
    secret_meta, secret_warning = _scan_trusted_write(
        "task",
        [("title", title), ("spec", spec), ("acceptance", acceptance)],
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
        payload = {
            "title": title,
            "project": project.slug,
            "kind": kind,
            "status": "ready",
            "priority": priority,
        }
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="task",
            entity_id=task_id,
            action="add",
            payload=payload,
        )
    _warn_secret(secret_warning)
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
    secret_meta, secret_warning = _scan_trusted_write(
        "task",
        [
            ("title", updates.get("title")),
            ("spec", updates.get("spec_md")),
            ("acceptance", updates.get("acceptance_md")),
        ],
    )
    now = utils.utc_now_iso()
    with db.transaction(conn):
        assignments = ", ".join(f"{column} = ?" for column in updates)
        conn.execute(
            f"UPDATE tasks SET {assignments}, updated_at = ? WHERE id = ?",
            (*updates.values(), now, task.id),
        )
        payload = {"task": task_hid, "changed": changed}
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="task",
            entity_id=task.id,
            action="edit",
            payload=payload,
        )
    _warn_secret(secret_warning)
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
    secret_meta, secret_warning = _scan_trusted_write(
        "decision",
        [
            ("title", title),
            ("decision", decision),
            ("alternatives", alternatives),
        ],
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
        payload = {
            "decision": ids.render_id("decision", decision_id),
            "title": title,
            "project": project.slug,
            "task": ids.render_id("task", task.id) if task else None,
            "status": "accepted",
        }
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="decision",
            entity_id=decision_id,
            action="add",
            payload=payload,
        )
    _warn_secret(secret_warning)
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
    secret_meta, secret_warning = _scan_trusted_write(
        "handoff",
        [
            ("from_agent", from_agent),
            ("to_agent", to_agent),
            ("state", state),
        ],
    )
    now = utils.utc_now_iso()
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO handoffs (task_id, from_agent, to_agent, state_md, "
            "created_at) VALUES (?, ?, ?, ?, ?)",
            (task.id, from_agent, to_agent, state, now),
        )
        handoff_id = cursor.lastrowid
        payload = {
            "handoff": ids.render_id("handoff", handoff_id),
            "task": ids.render_id("task", task.id),
            "from_agent": from_agent,
            "to_agent": to_agent,
        }
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="handoff",
            entity_id=handoff_id,
            action="create",
            payload=payload,
        )
    _warn_secret(secret_warning)
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


def get_evidence(conn: sqlite3.Connection, evidence_id: int) -> Evidence:
    row = conn.execute(
        "SELECT * FROM evidence WHERE id = ?", (evidence_id,)
    ).fetchone()
    if row is None:
        raise AosError(
            f"No evidence {ids.render_id('evidence', evidence_id)}. "
            "Run: python aos.py task show T-0001"
        )
    return Evidence.from_row(row)


# ---------------------------------------------------------------------------
# The memory claim hash (U-M2, contract M2.6)
#
# Lives here rather than in models.py because it needs U-X1's canonical
# serializer, and protocols.py imports models.py — the dependency can only
# run one way. It is still pure: no connection, no clock, no I/O.

#: Binds the payload SHAPE into the digest: a future payload revision cannot
#: collide with a v2 one. NOT a U-X1 registry identity — U-M2 registers no
#: protocol schema and changes none.
CLAIM_SCHEMA = "aos.memory-claim/v2"

#: Evidence links per claim, inherited from U-X1's array bound rather than
#: invented here. `link-evidence` refuses the 257th link BEFORE mutating.
MAX_EVIDENCE_LINKS_PER_CLAIM = protocols.MAX_ARRAY_ITEMS


def _claim_refusal(memory_id: object, field: str, why: str) -> ClaimHashError:
    hid = f"M-{memory_id:04d}" if isinstance(memory_id, int) else "a memory row"
    return ClaimHashError(
        f"Memory {hid} cannot be hashed: its {field} {why}. The row is "
        "damaged or was edited outside Agentic OS; it was not changed. "
        "Run: python aos.py doctor"
    )


def _text_leaf(value, field: str, memory_id, *, optional: bool = False):
    """Bind a stored text field by its sha256 digest, never by its raw text.

    Two reasons, both load-bearing (contract M2.6): U-X1's canonical JSON caps
    a string at MAX_STRING_CHARS, and `memory add --value` never had a length
    limit — so a real 20 KB legacy claim would otherwise be REFUSED BY ITS OWN
    MIGRATION. And a tampered megabyte-long cell must stay reportable rather
    than blowing up the diagnostic that exists to report it. sha256(text)
    binds the text exactly; nothing about the binding is weaker.
    """
    if value is None:
        if optional:
            return None
        raise _claim_refusal(memory_id, field, "is NULL")
    if not isinstance(value, str):
        raise _claim_refusal(memory_id, field, "is not text")
    return utils.sha256_text(value)


def _int_leaf(value, field: str, memory_id, *, optional: bool = False):
    if value is None:
        if optional:
            return None
        raise _claim_refusal(memory_id, field, "is NULL")
    # bool is an int subclass; a stored True must not read as pinned=1.
    if not isinstance(value, int) or isinstance(value, bool):
        raise _claim_refusal(memory_id, field, "is not an integer")
    if not (protocols.INT_MIN <= value <= protocols.INT_MAX):
        raise _claim_refusal(memory_id, field, "is outside the supported range")
    return value


def memory_claim_payload(item: MemoryItem, evidence_ids) -> dict:
    """The exact hash payload (M2.6). Every semantically authoritative field
    of the claim is bound; only `content_sha256` itself is excluded, because
    what gets hashed must never contain the hash (the D-v0.3.6 rule).

    `id` is bound so a valid hash cannot be transplanted between rows;
    `updated_at` is bound because every write that touches it recomputes the
    hash in the same statement anyway.
    """
    linked: set[int] = set()
    for evidence_id in evidence_ids:
        checked = _int_leaf(evidence_id, "evidence link", item.id)
        if checked is None:  # unreachable: _int_leaf refuses NULL when required
            raise _claim_refusal(item.id, "evidence link", "is NULL")
        linked.add(checked)
    ids_sorted = sorted(linked)
    if len(ids_sorted) > MAX_EVIDENCE_LINKS_PER_CLAIM:
        raise _claim_refusal(
            item.id,
            "evidence links",
            f"number {len(ids_sorted)}, above the maximum of "
            f"{MAX_EVIDENCE_LINKS_PER_CLAIM}",
        )
    return {
        "claim_schema": CLAIM_SCHEMA,
        "id": _int_leaf(item.id, "id", item.id),
        "project_id": _int_leaf(item.project_id, "project_id", item.id, optional=True),
        "superseded_by": _int_leaf(
            item.superseded_by, "superseded_by", item.id, optional=True
        ),
        # The STORED value, verbatim: a tampered pinned=5 must produce a
        # different digest, not be quietly coerced to True and collide with 1.
        "pinned": _int_leaf(item.pinned, "pinned", item.id),
        "evidence_ids": ids_sorted,
        "scope_sha256": _text_leaf(item.scope, "scope", item.id),
        "kind_sha256": _text_leaf(item.kind, "kind", item.id),
        "key_sha256": _text_leaf(item.key, "key", item.id),
        "value_sha256": _text_leaf(item.value_md, "value_md", item.id),
        "source_sha256": _text_leaf(item.source, "source", item.id),
        "confidence_sha256": _text_leaf(item.confidence, "confidence", item.id),
        "valid_from_sha256": _text_leaf(item.valid_from, "valid_from", item.id),
        "valid_until_sha256": _text_leaf(
            item.valid_until, "valid_until", item.id, optional=True
        ),
        "status_sha256": _text_leaf(item.status, "status", item.id),
        "updated_at_sha256": _text_leaf(item.updated_at, "updated_at", item.id),
    }


def memory_claim_digest(item: MemoryItem, evidence_ids) -> str:
    """The claim's content_sha256: lowercase sha256 over the canonical JSON
    payload. Canonicalization is U-X1's, unmodified (D-v0.3.20)."""
    payload = memory_claim_payload(item, evidence_ids)
    return hashlib.sha256(protocols.serialize_canonical(payload)).hexdigest()


# ---------------------------------------------------------------------------
# Memory claim integrity (U-M2, M2.6)

def memory_evidence_ids(conn: sqlite3.Connection, memory_id: int) -> list[int]:
    """The claim's evidence links: ids only, ascending. Deterministic, and
    the only thing the hash binds about them."""
    return [
        row["evidence_id"]
        for row in conn.execute(
            "SELECT evidence_id FROM memory_evidence WHERE memory_id = ? "
            "ORDER BY evidence_id",
            (memory_id,),
        )
    ]


def claim_digest(conn: sqlite3.Connection, item: MemoryItem) -> str:
    """The hash this claim's current stored state should carry."""
    return memory_claim_digest(item, memory_evidence_ids(conn, item.id))


def claim_integrity(conn: sqlite3.Connection, item: MemoryItem) -> str:
    """'ok' · 'malformed' · 'mismatch' · 'unhashable'. Never raises, never
    reveals a value: a damaged claim must be REPORTABLE, which a diagnostic
    that crashes on it is not."""
    if not is_claim_hash(item.content_sha256):
        return "malformed"
    try:
        digest = claim_digest(conn, item)
    except ClaimHashError:
        return "unhashable"
    return "ok" if digest == item.content_sha256 else "mismatch"


def verify_claim(conn: sqlite3.Connection, item: MemoryItem) -> None:
    """Refuse to mutate a claim whose stored hash does not verify.

    Without this gate, any authoritative write would recompute the hash over
    whatever the row now says and LAUNDER a tampered claim into a
    valid-looking one — the mutation would quietly bless the tampering. The
    refusal names the id and nothing else: no key, value, source or hash.
    """
    state = claim_integrity(conn, item)
    if state == "ok":
        return
    hid = ids.render_id("memory", item.id)
    reason = {
        "malformed": "its content hash is not 64 lowercase hex characters",
        "mismatch": "its content hash does not match its stored fields",
        "unhashable": "its stored fields cannot be hashed",
    }[state]
    raise AosError(
        f"Refusing to change memory {hid}: {reason}. The claim was edited "
        "outside Agentic OS or is damaged; writing it now would overwrite the "
        "hash and hide that. Nothing was changed. Run: python aos.py doctor "
        f"— then inspect it: python aos.py memory show {hid}"
    )


def _rehash_claim(conn: sqlite3.Connection, memory_id: int) -> str:
    """Recompute and store the claim hash. MUST be called inside the same
    transaction as the change that made it necessary (M2.6)."""
    digest = claim_digest(conn, get_memory(conn, memory_id))
    conn.execute(
        "UPDATE memory SET content_sha256 = ? WHERE id = ?", (digest, memory_id)
    )
    return digest


#: The hash a brand-new claim carries between its INSERT and its hash UPDATE,
#: microseconds later inside the same transaction. The claim hash binds the
#: row id, and the id is only known after the INSERT — so the two-step is
#: unavoidable. It is invisible: no other connection can observe an open
#: transaction, and a placeholder that somehow survived would be caught by
#: doctor's malformed-hash check rather than passing as a real hash.
_PENDING_HASH = ""


def _evidence_project_id(conn: sqlite3.Connection, item: Evidence) -> int | None:
    row = conn.execute(
        "SELECT project_id FROM tasks WHERE id = ?", (item.task_id,)
    ).fetchone()
    return row["project_id"] if row else None


def _resolve_evidence_links(
    conn: sqlite3.Connection,
    *,
    memory_project_id: int | None,
    evidence_ids: list[int],
) -> list[int]:
    """Validate and normalize requested links BEFORE any mutation.

    Deterministic: de-duplicated and sorted, so `--evidence E-2 --evidence E-1
    --evidence E-2` and `--evidence E-1 --evidence E-2` produce identical rows
    and an identical hash.
    """
    wanted = sorted(set(evidence_ids))
    if len(wanted) > MAX_EVIDENCE_LINKS_PER_CLAIM:
        raise AosError(
            f"Refusing to link {len(wanted)} evidence rows to one claim; the "
            f"maximum is {MAX_EVIDENCE_LINKS_PER_CLAIM}."
        )
    for evidence_id in wanted:
        evidence = get_evidence(conn, evidence_id)
        _check_link_compatible(
            conn, memory_project_id=memory_project_id, evidence=evidence
        )
    return wanted


def _check_link_compatible(
    conn: sqlite3.Connection,
    *,
    memory_project_id: int | None,
    evidence: Evidence,
) -> None:
    """Cross-project linkage rule (M2.8).

    Incompatible means BOTH sides name a project and the projects differ. A
    NULL on either side is compatible on purpose: a global-scope claim
    legitimately cites project evidence, and a projectless inbox task's
    evidence has no project to disagree with.
    """
    evidence_project_id = _evidence_project_id(conn, evidence)
    if (
        memory_project_id is None
        or evidence_project_id is None
        or memory_project_id == evidence_project_id
    ):
        return
    memory_project = get_project(conn, memory_project_id)
    evidence_project = get_project(conn, evidence_project_id)
    raise AosError(
        f"Refusing to link evidence {ids.render_id('evidence', evidence.id)} "
        f"(project '{evidence_project.slug if evidence_project else '?'}') to "
        f"a memory claim in project "
        f"'{memory_project.slug if memory_project else '?'}': a claim and its "
        "evidence must not name different projects. Nothing was changed."
    )


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
    pin: bool = False,
    evidence_ids: list[int] | None = None,
) -> MemoryItem:
    """Record a memory claim.

    Backward compatible by construction (M2.7): a caller that passes none of
    the U-M2 options gets exactly what it got before — a LIVE, UNPINNED claim
    with the same fields, the same event action and the same id.
    """
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
        # The superseded claim is about to be retired and re-hashed. Refuse
        # to touch it if its current hash does not verify (M2.6).
        verify_claim(conn, old)
    project_id = project.id if project else None
    links = _resolve_evidence_links(
        conn,
        memory_project_id=project_id,
        evidence_ids=list(evidence_ids or []),
    )
    now = utils.utc_now_iso()
    if pin and valid_until is not None and not (valid_until > now):
        # Pinning is ordering among ELIGIBLE claims; a claim born already
        # expired can never be retrieved, so pinning it would be a lie.
        raise AosError(
            "Refusing to pin a claim that is already expired "
            f"(--valid-until {valid_until}). Nothing was written."
        )
    secret_meta, secret_warning = _scan_trusted_write(
        "memory", [("key", key), ("value", value), ("source", source)]
    )
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO memory (scope, project_id, kind, key, value_md, "
            "source, confidence, valid_from, valid_until, updated_at, "
            "status, pinned, content_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                scope,
                project_id,
                kind,
                key,
                value,
                source,
                confidence,
                now,
                valid_until,
                now,
                MEMORY_STATUS_LIVE,
                1 if pin else 0,
                _PENDING_HASH,
            ),
        )
        memory_id = cursor.lastrowid
        for evidence_id in links:
            conn.execute(
                "INSERT INTO memory_evidence (memory_id, evidence_id, "
                "created_at) VALUES (?, ?, ?)",
                (memory_id, evidence_id, now),
            )
        if old is not None:
            conn.execute(
                "UPDATE memory SET superseded_by = ?, status = ?, "
                "updated_at = ? WHERE id = ?",
                (memory_id, MEMORY_STATUS_RETIRED, now, old.id),
            )
            # Its superseded_by and status are BOUND fields: the superseded
            # claim's hash must move in the same transaction as its state.
            _rehash_claim(conn, old.id)
        digest = _rehash_claim(conn, memory_id)
        payload = {
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
            "status": MEMORY_STATUS_LIVE,
            "pinned": bool(pin),
            "evidence": [ids.render_id("evidence", e) for e in links],
            "hash_prefix": hash_prefix(digest),
        }
        if old is not None:
            payload["supersedes_status"] = MEMORY_STATUS_RETIRED
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="memory",
            entity_id=memory_id,
            action="add",
            payload=payload,
        )
    _warn_secret(secret_warning)
    return get_memory(conn, memory_id)


def list_memory(
    conn: sqlite3.Connection,
    *,
    scope: str | None = None,
    project_slug: str | None = None,
    status: str | None = None,
    pinned: bool | None = None,
) -> list[dict]:
    """Every row, including retired and superseded ones — memory never
    silently disappears; retired rows carry their valid_until.

    Administrative listing shows INVALID rows too (M2.8): a claim with a
    broken hash or an unknown status is exactly what an operator came here to
    find, so it is listed with its status like any other.
    """
    clauses, params = [], []
    if scope is not None:
        validate_enum(scope, MEMORY_SCOPES, "memory scope")
        clauses.append("m.scope = ?")
        params.append(scope)
    if status is not None:
        validate_enum(status, MEMORY_STATUSES, "memory status")
        clauses.append("m.status = ?")
        params.append(status)
    if pinned is not None:
        clauses.append("m.pinned = ?")
        params.append(1 if pinned else 0)
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
    """Retire a claim: status='retired' plus the existing valid_until=now.

    The row and its evidence links stay exactly where they are — retiring is
    a curation decision, not a delete.
    """
    item = get_memory(conn, memory_id)
    memory_hid = ids.render_id("memory", item.id)
    now = utils.utc_now_iso()
    if item.status == MEMORY_STATUS_RETIRED:
        if item.valid_until is not None:
            detail = f"valid_until {item.valid_until}"
        elif item.superseded_by is not None:
            detail = f"superseded by {ids.render_id('memory', item.superseded_by)}"
        else:
            detail = "status retired"
        raise AosError(f"Memory {memory_hid} is already retired ({detail}).")
    if item.valid_until is not None and item.valid_until <= now:
        # Preserved v1 behavior: a claim already past its validity is already
        # retired as far as retrieval is concerned, whatever its status says.
        raise AosError(
            f"Memory {memory_hid} is already retired "
            f"(valid_until {item.valid_until})."
        )
    verify_claim(conn, item)
    with db.transaction(conn):
        conn.execute(
            "UPDATE memory SET status = ?, valid_until = ?, updated_at = ? "
            "WHERE id = ?",
            (MEMORY_STATUS_RETIRED, now, now, item.id),
        )
        digest = _rehash_claim(conn, item.id)
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="memory",
            entity_id=item.id,
            action="retire",
            payload={
                "memory": memory_hid,
                "valid_until": now,
                "from_status": item.status,
                "status": MEMORY_STATUS_RETIRED,
                "hash_prefix": hash_prefix(digest),
            },
        )
    return get_memory(conn, item.id)


def set_memory_pin(
    conn: sqlite3.Connection, *, memory_id: int, pinned: bool
) -> tuple[MemoryItem, bool]:
    """Pin or unpin a claim. Returns (claim, changed).

    Idempotent: setting the state a claim already has writes nothing,
    recomputes nothing and emits NO event — an audit journal that records
    non-events is a journal you stop trusting.
    """
    item = get_memory(conn, memory_id)
    memory_hid = ids.render_id("memory", item.id)
    if bool(item.pinned) == pinned:
        return item, False
    verify_claim(conn, item)
    if pinned and not claim_is_eligible(item):
        # Pin is ordering among eligible claims, never a way to force an
        # ineligible one into context (M2.7).
        raise AosError(
            f"Refusing to pin memory {memory_hid}: it is not eligible for "
            f"normal retrieval (status {item.status}"
            + (
                f", superseded by "
                f"{ids.render_id('memory', item.superseded_by)}"
                if item.superseded_by
                else ""
            )
            + (
                f", valid_until {item.valid_until}"
                if item.valid_until is not None
                and item.valid_until <= utils.utc_now_iso()
                else ""
            )
            + "). Pinning changes ordering only; it never overrides lifecycle "
            "or safety state. Nothing was changed."
        )
    now = utils.utc_now_iso()
    with db.transaction(conn):
        conn.execute(
            "UPDATE memory SET pinned = ?, updated_at = ? WHERE id = ?",
            (1 if pinned else 0, now, item.id),
        )
        digest = _rehash_claim(conn, item.id)
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="memory",
            entity_id=item.id,
            action="pin" if pinned else "unpin",
            payload={
                "memory": memory_hid,
                "pinned": pinned,
                "from_pinned": bool(item.pinned),
                "hash_prefix": hash_prefix(digest),
            },
        )
    return get_memory(conn, item.id), True


def link_memory_evidence(
    conn: sqlite3.Connection, *, memory_id: int, evidence_id: int
) -> tuple[MemoryItem, bool]:
    """Link one evidence row to one claim. Returns (claim, changed).

    The link is normalized: the row carries two ids and a timestamp, never a
    copy of the evidence's claim, ref or body (M2.2).
    """
    item = get_memory(conn, memory_id)
    evidence = get_evidence(conn, evidence_id)
    memory_hid = ids.render_id("memory", item.id)
    existing = memory_evidence_ids(conn, item.id)
    if evidence_id in existing:
        return item, False  # idempotent no-op: no write, no event
    verify_claim(conn, item)
    _check_link_compatible(
        conn, memory_project_id=item.project_id, evidence=evidence
    )
    if len(existing) + 1 > MAX_EVIDENCE_LINKS_PER_CLAIM:
        raise AosError(
            f"Refusing to link more evidence to memory {memory_hid}: it "
            f"already carries {len(existing)} links, the maximum. Nothing "
            "was changed."
        )
    now = utils.utc_now_iso()
    with db.transaction(conn):
        conn.execute(
            "INSERT INTO memory_evidence (memory_id, evidence_id, created_at) "
            "VALUES (?, ?, ?)",
            (item.id, evidence_id, now),
        )
        conn.execute(
            "UPDATE memory SET updated_at = ? WHERE id = ?", (now, item.id)
        )
        digest = _rehash_claim(conn, item.id)
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="memory",
            entity_id=item.id,
            action="link_evidence",
            payload={
                "memory": memory_hid,
                "evidence": ids.render_id("evidence", evidence_id),
                "evidence_count": len(existing) + 1,
                "hash_prefix": hash_prefix(digest),
            },
        )
    return get_memory(conn, item.id), True


def show_memory(conn: sqlite3.Connection, memory_id: int) -> dict:
    """One claim, read-only: fields, curation status, pin state, hash,
    evidence IDs and an integrity verdict.

    Evidence appears as E-XXXX ids only. This command never reads an
    evidence row's claim, ref, or any file it points at (M2.8).
    """
    item = get_memory(conn, memory_id)
    doc = memory_public(conn, item)
    doc["integrity"] = claim_integrity(conn, item)
    return doc


def capture_inbox(conn: sqlite3.Connection, text: str) -> Task:
    text = text.strip()
    if not text:
        raise AosError("Nothing to capture: text must not be empty.")
    secret_meta, secret_warning = _scan_trusted_write(
        "task", [("title", text)]
    )
    now = utils.utc_now_iso()
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO tasks (project_id, title, status, created_at, updated_at) "
            "VALUES (NULL, ?, 'inbox', ?, ?)",
            (text, now, now),
        )
        task_id = cursor.lastrowid
        payload = {"title": text, "status": "inbox", "via": "in"}
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="task",
            entity_id=task_id,
            action="add",
            payload=payload,
        )
    _warn_secret(secret_warning)
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
    secret_meta, secret_warning = _scan_trusted_write(
        "run", [("agent", agent)]
    )
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
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="run",
            entity_id=run_id,
            action="start",
            payload=payload,
        )
    _warn_secret(secret_warning)
    return get_run(conn, run_id)


def end_run(
    conn: sqlite3.Connection, *, run_id: int, outcome: str, summary: str
) -> Run:
    validate_enum(outcome, RUN_OUTCOMES, "run outcome")
    run = get_run(conn, run_id)
    run_hid = ids.render_id("run", run.id)
    if run.ended_at is not None:
        raise AosError(f"Run {run_hid} already ended at {run.ended_at}.")
    secret_meta, secret_warning = _scan_trusted_write(
        "run", [("summary", summary)]
    )
    now = utils.utc_now_iso()
    with db.transaction(conn):
        conn.execute(
            "UPDATE runs SET ended_at = ?, outcome = ?, summary_md = ? WHERE id = ?",
            (now, outcome, summary, run.id),
        )
        payload = {
            "task": ids.render_id("task", run.task_id),
            "outcome": outcome,
        }
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="run",
            entity_id=run.id,
            action="end",
            payload=payload,
        )
    _warn_secret(secret_warning)
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
    # U-H2 (D-v0.2.36): a blank ref proves nothing and a blank supplied
    # claim asserts nothing — both refuse before any lookup, hashing,
    # mutation, or event. Python str.strip() judges blankness, so NBSP /
    # U+3000 padding counts as whitespace. claim=None (omitted) stays legal.
    if not ref.strip():
        raise AosError("Evidence --ref must not be blank.")
    if claim is not None and not claim.strip():
        raise AosError(
            "Evidence --claim must not be blank when supplied; "
            "omit --claim entirely instead."
        )
    task = get_task(conn, task_id)
    sha = None
    if kind == "file":
        file_path = Path(ref).expanduser()
        if not file_path.is_file():
            raise AosError(f"Evidence file not found: {ref}")
        sha = utils.sha256_file(file_path)
    # Provenance is validated (human | agent:<name>) but the agent-name
    # charset admits token-shaped values, so it is scanned like ref/claim.
    # The canonical evidence row keeps the trusted value; events.emit
    # redacts the secret-shaped actor it would otherwise journal verbatim.
    secret_meta, secret_warning = _scan_trusted_write(
        "evidence",
        [("ref", ref), ("claim", claim), ("provenance", provenance)],
    )
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
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=provenance,
            entity="evidence",
            entity_id=evidence_id,
            action="add",
            payload=payload,
        )
    _warn_secret(secret_warning)
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
    secret_meta, secret_warning = (None, None)
    if override:
        # The override reason is stored verbatim in the done_override
        # payload (D-v0.2.5), so it is scanned like any other trusted write.
        secret_meta, secret_warning = _scan_trusted_write(
            "task", [("reason", reason)]
        )
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
            payload = {
                "task": task_hid,
                "reason": reason,
                "via": "--no-evidence",
            }
            if secret_meta:
                payload.update(secret_meta)
            events.emit(
                conn,
                actor=ACTOR_HUMAN,
                entity="task",
                entity_id=task.id,
                action="done_override",
                payload=payload,
            )
    _warn_secret(secret_warning)
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

    secret_meta, secret_warning = _scan_trusted_write(
        "agent",
        [
            ("name", name),
            ("notes", notes),
            ("capabilities", "\n".join(caps) if caps else None),
        ],
    )
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO agents (name, kind, capabilities_json, notes) "
            "VALUES (?, ?, ?, ?)",
            (name, kind, json.dumps(caps), notes),
        )
        payload = {"agent": name, "kind": kind, "capabilities": caps}
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="agent",
            entity_id=cursor.lastrowid,
            action="add",
            payload=payload,
        )
    _warn_secret(secret_warning)
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
    caps = None
    if notes is not None:
        if not notes.strip():
            raise AosError("--notes must not be empty.")
        updates["notes"] = notes
        changed.append("notes")
    if capabilities is not None:
        caps = _clean_capabilities(capabilities)
        updates["capabilities_json"] = json.dumps(caps)
        changed.append("capabilities")
    if not updates:
        raise AosError(
            "Nothing to update: pass at least one of --notes/--capability."
        )
    # The (pre-existing) name is scanned too: a secret-shaped identifier
    # accepted by an earlier warned write must mark — and be redacted
    # from — every later event payload it would be copied into.
    secret_meta, secret_warning = _scan_trusted_write(
        "agent",
        [
            ("name", name),
            ("notes", notes),
            ("capabilities", "\n".join(caps) if caps else None),
        ],
    )
    with db.transaction(conn):
        assignments = ", ".join(f"{column} = ?" for column in updates)
        conn.execute(
            f"UPDATE agents SET {assignments} WHERE id = ?",
            (*updates.values(), agent.id),
        )
        payload = {"agent": name, "changed": changed}
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="agent",
            entity_id=agent.id,
            action="update",
            payload=payload,
        )
    _warn_secret(secret_warning)
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
