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
    EVIDENCE_KINDS,
    MEMORY_CONFIDENCES,
    MEMORY_EDGE_CONTRADICTS,
    MEMORY_EDGE_RELATIONS,
    MEMORY_EDGE_SYMMETRIC,
    MEMORY_KINDS,
    MEMORY_SCOPES,
    MEMORY_SENSITIVITIES,
    MEMORY_SENSITIVITY_DEFAULT,
    MEMORY_SENSITIVITY_RESTRICTED,
    MEMORY_SOURCE_KIND_EVIDENCE,
    MEMORY_SOURCE_KINDS,
    MEMORY_SOURCE_RELATIONS,
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
    MemoryEdge,
    MemoryItem,
    MemorySource,
    MemorySourceLink,
    Pack,
    Project,
    Run,
    Task,
    hash_prefix,
    is_claim_hash,
    sensitivity_rank,
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

    U-M3 adds sensitivity to the SAME predicate rather than filtering
    restricted claims somewhere downstream (M3.2). If this said "eligible" for
    a claim `memory_for_project` excludes, then `memory show`'s `retrieved:
    yes` would be a lie about the one question that view exists to answer, and
    the pin gate would happily pin a claim no pack will ever carry. One
    predicate, one answer.
    """
    if now is None:
        now = utils.utc_now_iso()
    return (
        item.status == MEMORY_STATUS_LIVE
        and item.superseded_by is None
        and item.sensitivity != MEMORY_SENSITIVITY_RESTRICTED
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

    U-M3 (M3.2): `restricted` claims are excluded HERE, at the one canonical
    inclusion predicate, rather than in the pack renderer. A renderer-level
    filter would hold only for the renderer that has it; every present and
    future caller of this function gets the exclusion for free, and there is
    no second place for it to be forgotten. Restricted claims are also skipped
    BEFORE the per-key dedupe below, so a restricted claim can never shadow
    the live claim it shares a key with — it must not be able to blank out
    context by being excluded from it.

    Hashes are NOT re-verified here (D-v0.3.21): integrity is enforced at
    write time and audited by doctor. A read path that refused would let one
    damaged row block every pack in the workspace, and one that silently
    dropped rows would be worse still.
    """
    now = utils.utc_now_iso()
    rows = conn.execute(
        "SELECT * FROM memory WHERE status = ? AND superseded_by IS NULL "
        "AND (valid_until IS NULL OR valid_until > ?) "
        "AND sensitivity <> ? "
        "AND (scope = 'global' OR (project_id IS NOT NULL AND project_id = ?)) "
        "ORDER BY id",
        (MEMORY_STATUS_LIVE, now, MEMORY_SENSITIVITY_RESTRICTED, project_id),
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


#: What a restricted claim's suppressed text fields render as, everywhere. One
#: fixed string, never derived from the value it replaces — a placeholder whose
#: length or shape tracked the original would leak the original (M3.2).
RESTRICTED_PLACEHOLDER = "(restricted)"


def memory_public(
    conn: sqlite3.Connection, item: MemoryItem, project_slug: str | None = None
) -> dict:
    """The public claim shape. Never raises on a damaged row: administrative
    listing must show an invalid claim, not hide it (M2.8).

    A `restricted` claim is shown as METADATA ONLY (M3.2): id, scope, project,
    kind, lifecycle, sensitivity, timestamps, counts and hash are all here —
    its key, value, source and evidence refs are not. Restricted claims are
    listed, never hidden: an operator must be able to see that a claim exists,
    and administrative visibility is not the same as putting text in front of
    an agent.
    """
    if project_slug is None and item.project_id is not None:
        project = get_project(conn, item.project_id)
        project_slug = project.slug if project else None
    evidence_ids = memory_evidence_ids(conn, item.id)
    restricted = item.sensitivity == MEMORY_SENSITIVITY_RESTRICTED
    return {
        "id": ids.render_id("memory", item.id),
        "scope": item.scope,
        "project": project_slug,
        "kind": item.kind,
        "key": RESTRICTED_PLACEHOLDER if restricted else item.key,
        "value_md": RESTRICTED_PLACEHOLDER if restricted else item.value_md,
        "source": RESTRICTED_PLACEHOLDER if restricted else item.source,
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
        "sensitivity": item.sensitivity,
        # Evidence REFS name ledger rows a reader could then go and read, so a
        # restricted claim shows how many it has and not which (M3.2).
        "evidence": (
            []
            if restricted
            else [ids.render_id("evidence", eid) for eid in evidence_ids]
        ),
        "evidence_count": len(evidence_ids),
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
#: collide with a v2 one. NOT a U-X1 registry identity — neither U-M2 nor
#: U-M3 registers a protocol schema, and neither changes one.
#:
#: U-M3 bumps this to /v3 because the payload gained `sensitivity_sha256`
#: (M3.6). That is exactly what a schema identity is for: every v2 claim's
#: hash is recomputed by the 2→3 migration, and no v2 digest can be mistaken
#: for a v3 one.
CLAIM_SCHEMA = "aos.memory-claim/v3"

#: The three U-M3 record identities (M3.6). Each starts at /v1: the tables are
#: new, so there is no earlier payload for them to be confused with.
SOURCE_SCHEMA = "aos.memory-source/v1"
SOURCE_LINK_SCHEMA = "aos.memory-source-link/v1"
EDGE_SCHEMA = "aos.memory-edge/v1"

#: Evidence links per claim, inherited from U-X1's array bound rather than
#: invented here. `link-evidence` refuses the 257th link BEFORE mutating.
MAX_EVIDENCE_LINKS_PER_CLAIM = protocols.MAX_ARRAY_ITEMS


#: What each hashable record is CALLED in a refusal. A source's damage must
#: not be reported as a claim's: an operator sent to `memory show M-0007` for
#: a broken MS-0007 loses more time than the diagnostic saved them.
_RECORD_NOUN = {
    "memory": "Memory",
    "memory_source": "Memory source",
    "memory_source_link": "Memory source link",
    "memory_edge": "Memory edge",
}


def _claim_refusal(
    record_id: object, field: str, why: str, entity: str = "memory"
) -> ClaimHashError:
    # A record whose own id is unreadable cannot be named by id — say so
    # rather than rendering something misleading.
    hid = (
        ids.render_id(entity, record_id)
        if isinstance(record_id, int) and not isinstance(record_id, bool)
        else f"a {entity.replace('_', ' ')} row"
    )
    return ClaimHashError(
        f"{_RECORD_NOUN[entity]} {hid} cannot be hashed: its {field} {why}. "
        "The row is damaged or was edited outside Agentic OS; it was not "
        "changed. Run: python aos.py doctor"
    )


def _text_leaf(
    value, field: str, memory_id, *, entity: str = "memory", optional: bool = False
):
    """Bind a stored text field by its sha256 digest, never by its raw text.

    Three reasons, all load-bearing (M2.6, extended by M3.6 / D-v0.3.40):
    U-X1's canonical JSON caps a string at MAX_STRING_CHARS, and neither
    `memory add --value` nor `memory source add --locator` has a length limit
    — so a real 20 KB legacy claim would otherwise be REFUSED BY ITS OWN
    MIGRATION. A tampered megabyte-long cell must stay reportable rather than
    blowing up the diagnostic that exists to report it. And no diagnostic ever
    needs the raw value. sha256(text) binds the text exactly; nothing about
    the binding is weaker.
    """
    if value is None:
        if optional:
            return None
        raise _claim_refusal(memory_id, field, "is NULL", entity)
    if not isinstance(value, str):
        raise _claim_refusal(memory_id, field, "is not text", entity)
    return utils.sha256_text(value)


def _int_leaf(
    value, field: str, memory_id, *, entity: str = "memory", optional: bool = False
):
    if value is None:
        if optional:
            return None
        raise _claim_refusal(memory_id, field, "is NULL", entity)
    # bool is an int subclass; a stored True must not read as pinned=1.
    if not isinstance(value, int) or isinstance(value, bool):
        raise _claim_refusal(memory_id, field, "is not an integer", entity)
    if not (protocols.INT_MIN <= value <= protocols.INT_MAX):
        raise _claim_refusal(
            memory_id, field, "is outside the supported range", entity
        )
    return value


def _leaves(entity: str, record_id):
    """Bind a record's identity once, so the payload builders below read as a
    list of FIELDS rather than a list of (field, entity, id) triples."""

    def text(value, field: str, *, optional: bool = False):
        return _text_leaf(
            value, field, record_id, entity=entity, optional=optional
        )

    def integer(value, field: str, *, optional: bool = False):
        return _int_leaf(
            value, field, record_id, entity=entity, optional=optional
        )

    return text, integer


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
        # U-M3: bound like every other authoritative field, so tampering with
        # a claim's sensitivity — the field that decides whether an agent ever
        # sees it — breaks its hash exactly as tampering with its value does.
        "sensitivity_sha256": _text_leaf(item.sensitivity, "sensitivity", item.id),
        "updated_at_sha256": _text_leaf(item.updated_at, "updated_at", item.id),
    }


def memory_claim_digest(item: MemoryItem, evidence_ids) -> str:
    """The claim's content_sha256: lowercase sha256 over the canonical JSON
    payload. Canonicalization is U-X1's, unmodified (D-v0.3.20)."""
    payload = memory_claim_payload(item, evidence_ids)
    return hashlib.sha256(protocols.serialize_canonical(payload)).hexdigest()


# ---------------------------------------------------------------------------
# The U-M3 graph record hashes (contract M3.6)
#
# Same three rules as the claim hash above, applied three more times: every
# text leaf is bound by its sha256 (D-v0.3.40), every payload names its own
# record schema, and the ONLY excluded field is content_sha256 itself.

def _digest(payload: dict) -> str:
    return hashlib.sha256(protocols.serialize_canonical(payload)).hexdigest()


def memory_source_payload(item: MemorySource) -> dict:
    """The exact source hash payload (M3.6).

    `evidence_id` and `locator_sha256` are BOTH bound, each nullable: that is
    what makes a target substitution — swapping an evidence source's row, or
    repointing a file source at another path — break the hash rather than pass
    for the same record.
    """
    text, integer = _leaves("memory_source", item.id)
    return {
        "source_schema": SOURCE_SCHEMA,
        "id": integer(item.id, "id"),
        "project_id": integer(item.project_id, "project_id", optional=True),
        "evidence_id": integer(item.evidence_id, "evidence_id", optional=True),
        "source_kind_sha256": text(item.source_kind, "source_kind"),
        "locator_sha256": text(item.locator, "locator", optional=True),
        "provenance_sha256": text(item.provenance, "provenance"),
        "sensitivity_sha256": text(item.sensitivity, "sensitivity"),
        "observed_at_sha256": text(item.observed_at, "observed_at"),
        "valid_from_sha256": text(item.valid_from, "valid_from", optional=True),
        "valid_until_sha256": text(item.valid_until, "valid_until", optional=True),
        "created_at_sha256": text(item.created_at, "created_at"),
    }


def memory_source_digest(item: MemorySource) -> str:
    return _digest(memory_source_payload(item))


def memory_source_link_payload(item: MemorySourceLink) -> dict:
    """The exact source-link hash payload (M3.6). Both endpoints and the
    relation are bound, so an endpoint or relation substitution cannot keep a
    valid-looking hash."""
    text, integer = _leaves("memory_source_link", item.id)
    return {
        "link_schema": SOURCE_LINK_SCHEMA,
        "id": integer(item.id, "id"),
        "memory_id": integer(item.memory_id, "memory_id"),
        "source_id": integer(item.source_id, "source_id"),
        "relation_sha256": text(item.relation, "relation"),
        "created_at_sha256": text(item.created_at, "created_at"),
    }


def memory_source_link_digest(item: MemorySourceLink) -> str:
    return _digest(memory_source_link_payload(item))


def memory_edge_payload(item: MemoryEdge) -> dict:
    """The exact edge hash payload (M3.6)."""
    text, integer = _leaves("memory_edge", item.id)
    return {
        "edge_schema": EDGE_SCHEMA,
        "id": integer(item.id, "id"),
        "from_memory_id": integer(item.from_memory_id, "from_memory_id"),
        "to_memory_id": integer(item.to_memory_id, "to_memory_id"),
        "relation_sha256": text(item.relation, "relation"),
        "valid_from_sha256": text(item.valid_from, "valid_from", optional=True),
        "valid_until_sha256": text(item.valid_until, "valid_until", optional=True),
        "created_at_sha256": text(item.created_at, "created_at"),
    }


def memory_edge_digest(item: MemoryEdge) -> str:
    return _digest(memory_edge_payload(item))


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
    sensitivity: str = MEMORY_SENSITIVITY_DEFAULT,
) -> MemoryItem:
    """Record a memory claim.

    Backward compatible by construction (M2.7, M3.2): a caller that passes
    none of the U-M2/U-M3 options gets exactly what it got before — a LIVE,
    UNPINNED, `internal` claim with the same fields, the same event action and
    the same id.
    """
    validate_enum(scope, MEMORY_SCOPES, "memory scope")
    validate_enum(kind, MEMORY_KINDS, "memory kind")
    validate_enum(confidence, MEMORY_CONFIDENCES, "memory confidence")
    validate_enum(sensitivity, MEMORY_SENSITIVITIES, "memory sensitivity")
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
    if pin and sensitivity == MEMORY_SENSITIVITY_RESTRICTED:
        # Same rule, the other reason a claim can be born unretrievable: a
        # restricted claim never enters a pack, so a pin on it orders nothing
        # (D-v0.3.33). Refusing here keeps `add` from creating the pinned-but-
        # ineligible state doctor would immediately warn about.
        raise AosError(
            "Refusing to pin a restricted claim: restricted claims never "
            "enter context packs, so a pin would order nothing. Pinning "
            "changes ordering only; it never overrides sensitivity. Nothing "
            "was written."
        )
    secret_meta, secret_warning = _scan_trusted_write(
        "memory", [("key", key), ("value", value), ("source", source)]
    )
    restricted = sensitivity == MEMORY_SENSITIVITY_RESTRICTED
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO memory (scope, project_id, kind, key, value_md, "
            "source, confidence, valid_from, valid_until, updated_at, "
            "status, pinned, sensitivity, content_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                sensitivity,
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
            # The `add` event has carried the key since v1 and still does —
            # UNLESS the claim is restricted (M3.2/M3.10). `aos log` and
            # `export events` are generated surfaces, and a restricted claim's
            # key must not reach one. Nothing changes for any other level, so
            # every existing claim's event is byte-identical to before.
            "key": RESTRICTED_PLACEHOLDER if restricted else key,
            "confidence": confidence,
            "valid_until": valid_until,
            "supersedes": (
                ids.render_id("memory", old.id) if old else None
            ),
            "status": MEMORY_STATUS_LIVE,
            "pinned": bool(pin),
            # A closed enum name, never the claim it describes (M3.10).
            "sensitivity": sensitivity,
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


# ---------------------------------------------------------------------------
# U-M3 memory graph (contract M3.2 - M3.8)
#
# Everything below records what a human typed and judges none of it. No edge
# is inferred, no contradiction is detected, no locator is opened, no relation
# triggers a workflow (D-v0.3.39, D-v0.3.47, D-v0.3.49).

#: Traversal bounds (M3.8a). Hard caps, not suggestions: `memory graph` is a
#: diagnostic, and a diagnostic that can print an unbounded ledger is a way to
#: lose a terminal, not a way to understand a claim.
MAX_GRAPH_DEPTH = 2
MAX_GRAPH_NODES = 64
MAX_GRAPH_EDGES = 128


def window_is_active(
    valid_from: str | None, valid_until: str | None, now: str | None = None
) -> bool:
    """THE temporal predicate for sources and edges (M3.7a).

    One definition, used by every command and by doctor, so "active" cannot
    mean two things in two places. `> now` matches U-M2's claim-expiry
    predicate exactly rather than approximately: a record whose window closed
    at this instant is closed.

    An expired record is INACTIVE, never gone: it stays queryable history. The
    ledger has no delete path and U-M3 does not add one.
    """
    if now is None:
        now = utils.utc_now_iso()
    if valid_from is not None and valid_from > now:
        return False
    return valid_until is None or valid_until > now


def get_memory_source(conn: sqlite3.Connection, source_id: int) -> MemorySource:
    row = conn.execute(
        "SELECT * FROM memory_sources WHERE id = ?", (source_id,)
    ).fetchone()
    if row is None:
        raise AosError(
            f"No memory source {ids.render_id('memory_source', source_id)}. "
            "Run: python aos.py memory source list"
        )
    return MemorySource.from_row(row)


def get_memory_edge(conn: sqlite3.Connection, edge_id: int) -> MemoryEdge:
    row = conn.execute(
        "SELECT * FROM memory_edges WHERE id = ?", (edge_id,)
    ).fetchone()
    if row is None:
        raise AosError(
            f"No memory edge {ids.render_id('memory_edge', edge_id)}. "
            "Run: python aos.py memory edge list"
        )
    return MemoryEdge.from_row(row)


def _record_integrity(stored_hash, compute) -> str:
    """'ok' · 'malformed' · 'mismatch' · 'unhashable' for any U-M3 record.

    Never raises and never reveals a value — the U-M2 claim_integrity rule
    (M2.6), factored out so all four record kinds answer the question the same
    way rather than four nearly-identical ways.
    """
    if not is_claim_hash(stored_hash):
        return "malformed"
    try:
        digest = compute()
    except ClaimHashError:
        return "unhashable"
    return "ok" if digest == stored_hash else "mismatch"


def source_integrity(item: MemorySource) -> str:
    return _record_integrity(
        item.content_sha256, lambda: memory_source_digest(item)
    )


def source_link_integrity(item: MemorySourceLink) -> str:
    return _record_integrity(
        item.content_sha256, lambda: memory_source_link_digest(item)
    )


def edge_integrity(item: MemoryEdge) -> str:
    return _record_integrity(
        item.content_sha256, lambda: memory_edge_digest(item)
    )


#: Why a record refuses to be mutated. Reason codes, not values (M3.6).
_INTEGRITY_REASON = {
    "malformed": "its content hash is not 64 lowercase hex characters",
    "mismatch": "its content hash does not match its stored fields",
    "unhashable": "its stored fields cannot be hashed",
}


def _verify_record(state: str, entity: str, record_id: int) -> None:
    """Refuse to touch a record whose stored hash does not verify (D-v0.3.41).

    Same gate as verify_claim, same reason: without it, any authoritative
    write would recompute the hash over whatever the row now says and LAUNDER
    tampering into a valid-looking record — the mutation would quietly certify
    the damage. The refusal names the id and a reason code, and nothing else.
    """
    if state == "ok":
        return
    hid = ids.render_id(entity, record_id)
    raise AosError(
        f"Refusing to use {_RECORD_NOUN[entity].lower()} {hid}: "
        f"{_INTEGRITY_REASON[state]}. The record was edited outside Agentic OS "
        "or is damaged; using it now would certify that. Nothing was changed. "
        "Run: python aos.py doctor"
    )


def verify_source(item: MemorySource) -> None:
    _verify_record(source_integrity(item), "memory_source", item.id)


def verify_edge(item: MemoryEdge) -> None:
    _verify_record(edge_integrity(item), "memory_edge", item.id)


# --- sensitivity (M3.2)

def classify_memory(
    conn: sqlite3.Connection, *, memory_id: int, level: str
) -> tuple[MemoryItem, bool]:
    """Raise a claim's sensitivity. Returns (claim, changed).

    Increases only (D-v0.3.50). Same-state is an idempotent no-op: no write,
    no rehash, no event — an audit journal that records non-events is one you
    stop trusting (the U-M2 pin rule). A DOWNGRADE refuses unchanged and says
    where that decision lives: reducing the protection on a claim is an
    authorization question, and U-M3 ships no authorization system to answer
    it with.
    """
    validate_enum(level, MEMORY_SENSITIVITIES, "memory sensitivity")
    item = get_memory(conn, memory_id)
    memory_hid = ids.render_id("memory", item.id)
    current = sensitivity_rank(item.sensitivity)
    target = sensitivity_rank(level)
    if target == current:
        return item, False
    if target < current:
        raise AosError(
            f"Refusing to down-classify memory {memory_hid} from "
            f"{item.sensitivity} to {level}: U-M3 raises classification only. "
            "Lowering it is an authorization decision and belongs to U-S6, "
            "which this build does not ship. Nothing was changed."
        )
    verify_claim(conn, item)
    now = utils.utc_now_iso()
    with db.transaction(conn):
        conn.execute(
            "UPDATE memory SET sensitivity = ?, updated_at = ? WHERE id = ?",
            (level, now, item.id),
        )
        # sensitivity is a BOUND field: the claim's hash must move in the same
        # transaction as its classification.
        digest = _rehash_claim(conn, item.id)
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="memory",
            entity_id=item.id,
            action="classify",
            payload={
                "memory": memory_hid,
                "from_sensitivity": item.sensitivity,
                "sensitivity": level,
                "hash_prefix": hash_prefix(digest),
            },
        )
    return get_memory(conn, item.id), True


# --- provenance sources (M3.3)

def memory_source_public(
    conn: sqlite3.Connection,
    item: MemorySource,
    project_slug: str | None = None,
    now: str | None = None,
) -> dict:
    """The public source shape: ADMINISTRATIVE METADATA ONLY (M3.8).

    Deliberately absent, and not by oversight: `locator` and `provenance`. A
    source exists to say "this claim came from somewhere"; naming that
    somewhere in a listing is how a URL with a token in it, or a path through
    someone's home directory, ends up on a terminal and in a scrollback
    buffer. The id is enough to correlate; the ledger holds the rest.

    An `evidence` source names its evidence ROW (E-XXXX). It never reads that
    row's claim, ref or body, and never opens a file it points at.
    """
    if project_slug is None and item.project_id is not None:
        project = get_project(conn, item.project_id)
        project_slug = project.slug if project else None
    return {
        "id": ids.render_id("memory_source", item.id),
        "project": project_slug,
        "kind": item.source_kind,
        "evidence": (
            ids.render_id("evidence", item.evidence_id)
            if item.evidence_id is not None
            else None
        ),
        "sensitivity": item.sensitivity,
        "observed_at": item.observed_at,
        "valid_from": item.valid_from,
        "valid_until": item.valid_until,
        "created_at": item.created_at,
        "active": window_is_active(item.valid_from, item.valid_until, now),
        "link_count": conn.execute(
            "SELECT COUNT(*) AS n FROM memory_source_links WHERE source_id = ?",
            (item.id,),
        ).fetchone()["n"],
        "hash_prefix": hash_prefix(item.content_sha256),
    }


def add_memory_source(
    conn: sqlite3.Connection,
    *,
    kind: str,
    project_slug: str | None = None,
    evidence_id: int | None = None,
    locator: str | None = None,
    provenance: str = "human",
    sensitivity: str = MEMORY_SENSITIVITY_DEFAULT,
    observed_at: str | None = None,
    valid_from: str | None = None,
    valid_until: str | None = None,
) -> MemorySource:
    """Record a provenance source.

    The structural rule (M3.3) is enforced here AND by a CHECK constraint:
    `evidence` sources carry an evidence id and no locator; every other kind
    carries a locator and no evidence id. Two boundaries, one rule — the CLI
    catches the operator's mistake with a readable message, the constraint
    catches everything else.

    The locator is never opened, fetched or executed (D-v0.3.47). It is a
    string this ledger agreed to remember.
    """
    validate_enum(kind, MEMORY_SOURCE_KINDS, "memory source kind")
    validate_enum(sensitivity, MEMORY_SENSITIVITIES, "memory sensitivity")
    validate_provenance(provenance)

    project = None
    if project_slug is not None:
        project = get_project_by_slug(conn, project_slug)
        if project is None:
            raise AosError(
                f"No project '{project_slug}'. Run: python aos.py project add "
                f"{project_slug} --name NAME --repo PATH"
            )

    if kind == MEMORY_SOURCE_KIND_EVIDENCE:
        if evidence_id is None:
            raise AosError(
                "A source of kind 'evidence' requires --evidence E-XXXX. "
                "Nothing was written."
            )
        if locator is not None:
            raise AosError(
                "A source of kind 'evidence' must not carry --locator: it "
                "names an evidence row, and copying that row's ref into a "
                "second place is how the two start disagreeing. Nothing was "
                "written."
            )
        # Existence only. This never reads the evidence row's claim, ref or
        # body, and never opens whatever it points at.
        get_evidence(conn, evidence_id)
    else:
        if evidence_id is not None:
            raise AosError(
                f"A source of kind {kind!r} must not carry --evidence; only "
                "kind 'evidence' names a ledger row. Nothing was written."
            )
        if locator is None or not locator.strip():
            raise AosError(
                f"A source of kind {kind!r} requires a non-empty --locator. "
                "Nothing was written."
            )
        locator = locator.strip()

    now = utils.utc_now_iso()
    observed_at = (
        utils.validate_instant(observed_at, "--observed-at")
        if observed_at is not None
        else now
    )
    if valid_from is not None:
        utils.validate_instant(valid_from, "--valid-from")
    if valid_until is not None:
        utils.validate_instant(valid_until, "--valid-until")
    if valid_from is not None and valid_until is not None and valid_from > valid_until:
        raise AosError(
            f"Refusing an inverted validity window: --valid-from {valid_from} "
            f"is after --valid-until {valid_until}. Nothing was written."
        )

    secret_meta, secret_warning = _scan_trusted_write(
        "memory source", [("locator", locator), ("provenance", provenance)]
    )
    project_id = project.id if project else None
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO memory_sources (project_id, source_kind, evidence_id, "
            "locator, provenance, sensitivity, observed_at, valid_from, "
            "valid_until, created_at, content_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                project_id,
                kind,
                evidence_id,
                locator,
                provenance,
                sensitivity,
                observed_at,
                valid_from,
                valid_until,
                now,
                _PENDING_HASH,
            ),
        )
        source_id = cursor.lastrowid
        digest = memory_source_digest(get_memory_source(conn, source_id))
        conn.execute(
            "UPDATE memory_sources SET content_sha256 = ? WHERE id = ?",
            (digest, source_id),
        )
        payload = {
            "source": ids.render_id("memory_source", source_id),
            "project": project.slug if project else None,
            # Closed enum names and ids only. The locator and the provenance
            # text are exactly what an event must never carry (M3.10).
            "kind": kind,
            "sensitivity": sensitivity,
            "evidence": (
                ids.render_id("evidence", evidence_id)
                if evidence_id is not None
                else None
            ),
            "observed_at": observed_at,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "hash_prefix": hash_prefix(digest),
        }
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="memory_source",
            entity_id=source_id,
            action="add",
            payload=payload,
        )
    _warn_secret(secret_warning)
    return get_memory_source(conn, source_id)


def list_memory_sources(
    conn: sqlite3.Connection,
    *,
    project_slug: str | None = None,
    kind: str | None = None,
    active_only: bool = False,
) -> list[dict]:
    """Every source, ascending by id. Metadata only (M3.8).

    Damaged rows are listed like any other: a source with a broken hash is
    exactly what an operator came here to find, so hiding it would defeat the
    listing. `memory source show` carries the integrity verdict.
    """
    clauses, params = [], []
    if kind is not None:
        validate_enum(kind, MEMORY_SOURCE_KINDS, "memory source kind")
        clauses.append("s.source_kind = ?")
        params.append(kind)
    if project_slug is not None:
        project = get_project_by_slug(conn, project_slug)
        if project is None:
            raise AosError(
                f"No project '{project_slug}'. Run: python aos.py project add "
                f"{project_slug} --name NAME --repo PATH"
            )
        clauses.append("s.project_id = ?")
        params.append(project.id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    now = utils.utc_now_iso()
    rows = conn.execute(
        f"SELECT s.*, p.slug AS project_slug FROM memory_sources s "
        f"LEFT JOIN projects p ON p.id = s.project_id {where} ORDER BY s.id",
        params,
    ).fetchall()
    docs = [
        memory_source_public(
            conn, MemorySource.from_row(row), row["project_slug"], now
        )
        for row in rows
    ]
    return [doc for doc in docs if doc["active"]] if active_only else docs


def show_memory_source(conn: sqlite3.Connection, source_id: int) -> dict:
    """One source, read-only: metadata plus an integrity verdict. Still no
    locator, no provenance, no evidence claim or ref, no file contents."""
    item = get_memory_source(conn, source_id)
    doc = memory_source_public(conn, item)
    doc["integrity"] = source_integrity(item)
    doc["links"] = [
        {
            "id": ids.render_id("memory_source_link", row["id"]),
            "memory": ids.render_id("memory", row["memory_id"]),
            "relation": row["relation"],
        }
        for row in conn.execute(
            "SELECT id, memory_id, relation FROM memory_source_links "
            "WHERE source_id = ? ORDER BY id",
            (source_id,),
        )
    ]
    return doc


# --- provenance links (M3.4)

def _check_source_link_compatible(
    conn: sqlite3.Connection, *, claim: MemoryItem, source: MemorySource
) -> None:
    """Project and sensitivity compatibility, checked BEFORE any mutation.

    Project rule (M3.3), stricter than U-M2's evidence rule on purpose: a
    GLOBAL source may back a global or a project claim, but a PROJECT source
    may back only claims in its own project — including not global ones. A
    project-scoped source attached to a global claim would make project
    provenance reachable from every project's context.

    Sensitivity rule (M3.4): a source may not be more sensitive than the claim
    it backs. Otherwise the link is a downgrade channel — a restricted source
    reachable by anyone who can see a public claim.
    """
    claim_hid = ids.render_id("memory", claim.id)
    source_hid = ids.render_id("memory_source", source.id)
    if source.project_id is not None and source.project_id != claim.project_id:
        source_project = get_project(conn, source.project_id)
        claim_project = (
            get_project(conn, claim.project_id)
            if claim.project_id is not None
            else None
        )
        raise AosError(
            f"Refusing to link source {source_hid} (project "
            f"'{source_project.slug if source_project else '?'}') to claim "
            f"{claim_hid} ("
            + (
                f"project '{claim_project.slug}'"
                if claim_project
                else "global scope"
            )
            + "): a project source may back only claims in the same project. "
            "Nothing was changed."
        )
    if sensitivity_rank(source.sensitivity) > sensitivity_rank(claim.sensitivity):
        raise AosError(
            f"Refusing to link source {source_hid} ({source.sensitivity}) to "
            f"claim {claim_hid} ({claim.sensitivity}): a source must not be "
            "more sensitive than the claim it backs, or the link becomes a way "
            "to reach the source through the claim. Raise the claim first: "
            f"python aos.py memory classify {claim_hid} {source.sensitivity} — "
            "nothing was changed."
        )


def link_memory_source(
    conn: sqlite3.Connection, *, memory_id: int, source_id: int, relation: str
) -> tuple[MemorySourceLink, bool]:
    """Link one source to one claim. Returns (link, changed).

    Idempotent on the logical link (memory, source, relation) — D-v0.3.35.
    Records provenance and nothing else: the claim's status, lifecycle, pin
    and hash are untouched. A source is evidence OF a claim, not an event IN
    its life.
    """
    validate_enum(relation, MEMORY_SOURCE_RELATIONS, "memory source relation")
    claim = get_memory(conn, memory_id)
    source = get_memory_source(conn, source_id)
    existing = conn.execute(
        "SELECT * FROM memory_source_links WHERE memory_id = ? AND "
        "source_id = ? AND relation = ?",
        (memory_id, source_id, relation),
    ).fetchone()
    if existing is not None:
        return MemorySourceLink.from_row(existing), False  # no write, no event
    # Both endpoints must be honest before a link certifies a relationship
    # between them (D-v0.3.41).
    verify_claim(conn, claim)
    verify_source(source)
    _check_source_link_compatible(conn, claim=claim, source=source)
    now = utils.utc_now_iso()
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO memory_source_links (memory_id, source_id, relation, "
            "created_at, content_sha256) VALUES (?, ?, ?, ?, ?)",
            (memory_id, source_id, relation, now, _PENDING_HASH),
        )
        link_id = cursor.lastrowid
        row = conn.execute(
            "SELECT * FROM memory_source_links WHERE id = ?", (link_id,)
        ).fetchone()
        digest = memory_source_link_digest(MemorySourceLink.from_row(row))
        conn.execute(
            "UPDATE memory_source_links SET content_sha256 = ? WHERE id = ?",
            (digest, link_id),
        )
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="memory_source_link",
            entity_id=link_id,
            action="add",
            payload={
                "link": ids.render_id("memory_source_link", link_id),
                "memory": ids.render_id("memory", memory_id),
                "source": ids.render_id("memory_source", source_id),
                "relation": relation,
                "active_source": window_is_active(
                    source.valid_from, source.valid_until, now
                ),
                "hash_prefix": hash_prefix(digest),
            },
        )
    row = conn.execute(
        "SELECT * FROM memory_source_links WHERE id = ?", (link_id,)
    ).fetchone()
    return MemorySourceLink.from_row(row), True


# --- claim relationships (M3.5)

def canonical_endpoints(
    from_memory_id: int, to_memory_id: int, relation: str
) -> tuple[int, int]:
    """Endpoint order for storage and lookup (D-v0.3.36).

    Symmetric relations put the LOWER id first, so A↔B and B↔A are one logical
    edge and a reverse duplicate collides with the UNIQUE constraint instead of
    quietly becoming a second row for the same fact. Directional relations are
    returned exactly as asked.
    """
    if relation in MEMORY_EDGE_SYMMETRIC and from_memory_id > to_memory_id:
        return to_memory_id, from_memory_id
    return from_memory_id, to_memory_id


def memory_edge_public(
    conn: sqlite3.Connection, item: MemoryEdge, now: str | None = None
) -> dict:
    """The public edge shape: ids, a relation, a window, an active flag.

    No claim key, value or source ever appears here — an edge listing is a map
    of what relates to what, not a way to read the claims it names (M3.8).
    """
    return {
        "id": ids.render_id("memory_edge", item.id),
        "from": ids.render_id("memory", item.from_memory_id),
        "to": ids.render_id("memory", item.to_memory_id),
        "relation": item.relation,
        "symmetric": item.relation in MEMORY_EDGE_SYMMETRIC,
        "valid_from": item.valid_from,
        "valid_until": item.valid_until,
        "created_at": item.created_at,
        "active": window_is_active(item.valid_from, item.valid_until, now),
        "hash_prefix": hash_prefix(item.content_sha256),
    }


def add_memory_edge(
    conn: sqlite3.Connection,
    *,
    from_memory_id: int,
    to_memory_id: int,
    relation: str,
    valid_from: str | None = None,
    valid_until: str | None = None,
) -> tuple[MemoryEdge, bool]:
    """Record a typed relationship between two claims. Returns (edge, changed).

    Descriptive only (D-v0.3.49): adding a `contradicts` edge does not
    quarantine, retire, contest or reorder anything. It records that a human
    said two claims disagree. Deciding which is true is not this unit's job —
    and an automation that decided it silently would be worse than the
    disagreement.
    """
    validate_enum(relation, MEMORY_EDGE_RELATIONS, "memory edge relation")
    if from_memory_id == to_memory_id:
        hid = ids.render_id("memory", from_memory_id)
        raise AosError(
            f"Refusing a self-edge on memory {hid}: a claim cannot relate to "
            "itself. Nothing was written."
        )
    source_claim = get_memory(conn, from_memory_id)
    target_claim = get_memory(conn, to_memory_id)
    if (
        source_claim.project_id is not None
        and target_claim.project_id is not None
        and source_claim.project_id != target_claim.project_id
    ):
        # Global↔project is fine — a global claim legitimately relates to a
        # project one. Project-A↔project-B is not: it would make one project's
        # graph reachable from another's.
        from_project = get_project(conn, source_claim.project_id)
        to_project = get_project(conn, target_claim.project_id)
        raise AosError(
            f"Refusing to relate memory {ids.render_id('memory', from_memory_id)} "
            f"(project '{from_project.slug if from_project else '?'}') to "
            f"{ids.render_id('memory', to_memory_id)} (project "
            f"'{to_project.slug if to_project else '?'}'): claims in different "
            "projects must not be linked. Nothing was written."
        )
    if valid_from is not None:
        utils.validate_instant(valid_from, "--valid-from")
    if valid_until is not None:
        utils.validate_instant(valid_until, "--valid-until")
    if valid_from is not None and valid_until is not None and valid_from > valid_until:
        raise AosError(
            f"Refusing an inverted validity window: --valid-from {valid_from} "
            f"is after --valid-until {valid_until}. Nothing was written."
        )

    left, right = canonical_endpoints(from_memory_id, to_memory_id, relation)
    existing = conn.execute(
        "SELECT * FROM memory_edges WHERE from_memory_id = ? AND "
        "to_memory_id = ? AND relation = ?",
        (left, right, relation),
    ).fetchone()
    if existing is not None:
        # Includes the reverse spelling of a symmetric edge: canonicalization
        # happened before this lookup, so `edge add B A --relation contradicts`
        # finds the A↔B row and writes nothing.
        return MemoryEdge.from_row(existing), False
    verify_claim(conn, source_claim)
    verify_claim(conn, target_claim)
    now = utils.utc_now_iso()
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO memory_edges (from_memory_id, to_memory_id, relation, "
            "valid_from, valid_until, created_at, content_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (left, right, relation, valid_from, valid_until, now, _PENDING_HASH),
        )
        edge_id = cursor.lastrowid
        digest = memory_edge_digest(get_memory_edge(conn, edge_id))
        conn.execute(
            "UPDATE memory_edges SET content_sha256 = ? WHERE id = ?",
            (digest, edge_id),
        )
        events.emit(
            conn,
            actor=ACTOR_HUMAN,
            entity="memory_edge",
            entity_id=edge_id,
            action="add",
            payload={
                "edge": ids.render_id("memory_edge", edge_id),
                "from": ids.render_id("memory", left),
                "to": ids.render_id("memory", right),
                "relation": relation,
                "canonicalized": (left, right) != (from_memory_id, to_memory_id),
                "valid_from": valid_from,
                "valid_until": valid_until,
                "active": window_is_active(valid_from, valid_until, now),
                "hash_prefix": hash_prefix(digest),
            },
        )
    return get_memory_edge(conn, edge_id), True


def _edge_project_clause(conn: sqlite3.Connection, project_slug: str):
    """`--project` on an edge listing means: either endpoint is in it.

    An edge is a statement about two claims, so it belongs to a project when
    either end does. The alternative — requiring both — would hide exactly the
    global↔project edges this schema goes out of its way to permit.
    """
    project = get_project_by_slug(conn, project_slug)
    if project is None:
        raise AosError(
            f"No project '{project_slug}'. Run: python aos.py project add "
            f"{project_slug} --name NAME --repo PATH"
        )
    return (
        "(EXISTS (SELECT 1 FROM memory m WHERE m.id = e.from_memory_id "
        "AND m.project_id = ?) OR EXISTS (SELECT 1 FROM memory m "
        "WHERE m.id = e.to_memory_id AND m.project_id = ?))",
        [project.id, project.id],
    )


def list_memory_edges(
    conn: sqlite3.Connection,
    *,
    relation: str | None = None,
    project_slug: str | None = None,
    active_only: bool = False,
) -> list[dict]:
    """Every edge, ascending by id. Read-only, deterministic, metadata only."""
    clauses, params = [], []
    if relation is not None:
        validate_enum(relation, MEMORY_EDGE_RELATIONS, "memory edge relation")
        clauses.append("e.relation = ?")
        params.append(relation)
    if project_slug is not None:
        clause, values = _edge_project_clause(conn, project_slug)
        clauses.append(clause)
        params += values
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    now = utils.utc_now_iso()
    docs = [
        memory_edge_public(conn, MemoryEdge.from_row(row), now)
        for row in conn.execute(
            f"SELECT e.* FROM memory_edges e {where} ORDER BY e.id", params
        ).fetchall()
    ]
    return [doc for doc in docs if doc["active"]] if active_only else docs


def list_contradictions(
    conn: sqlite3.Connection,
    *,
    project_slug: str | None = None,
    include_inactive: bool = False,
) -> list[dict]:
    """Active `contradicts` edges (M3.8).

    Reports; never judges. There is no verdict field to fill in, no winner, no
    resolution, and nothing here mutates a claim — deciding which of two
    claims is true is a human's job, and a tool that guessed would be believed
    (D-v0.3.38).

    Each row carries both claims' lifecycle and sensitivity metadata, so an
    operator can see at a glance that (say) one side is already retired —
    which is usually the whole answer — without either claim's text.
    """
    clauses = ["e.relation = ?"]
    params: list = [MEMORY_EDGE_CONTRADICTS]
    if project_slug is not None:
        clause, values = _edge_project_clause(conn, project_slug)
        clauses.append(clause)
        params += values
    now = utils.utc_now_iso()
    docs = []
    for row in conn.execute(
        f"SELECT e.* FROM memory_edges e WHERE {' AND '.join(clauses)} "
        "ORDER BY e.id",
        params,
    ).fetchall():
        edge = MemoryEdge.from_row(row)
        doc = memory_edge_public(conn, edge, now)
        if not doc["active"] and not include_inactive:
            continue
        doc["claims"] = [
            _graph_node(conn, mid, now)
            for mid in (edge.from_memory_id, edge.to_memory_id)
        ]
        docs.append(doc)
    return docs


# --- bounded traversal (M3.8)

def _graph_node(
    conn: sqlite3.Connection, memory_id: int, now: str, depth: int | None = None
) -> dict:
    """One claim as a graph NODE: identity and state, never content.

    A missing claim is reported as such rather than skipped: an edge pointing
    at nothing is a fact about the graph, and silently dropping it would make
    the damage invisible in the one view that could show it.
    """
    row = conn.execute(
        "SELECT m.*, p.slug AS project_slug FROM memory m "
        "LEFT JOIN projects p ON p.id = m.project_id WHERE m.id = ?",
        (memory_id,),
    ).fetchone()
    node = {"id": ids.render_id("memory", memory_id)}
    if depth is not None:
        node["depth"] = depth
    if row is None:
        node["missing"] = True
        return node
    item = MemoryItem.from_row(row)
    node.update(
        {
            "project": row["project_slug"],
            "scope": item.scope,
            "kind": item.kind,
            "status": item.status,
            "sensitivity": item.sensitivity,
            "pinned": bool(item.pinned),
            "live": claim_is_eligible(item, now),
        }
    )
    return node


def memory_graph(
    conn: sqlite3.Connection, *, memory_id: int, depth: int = 1
) -> dict:
    """A bounded, deterministic breadth-first neighbourhood (M3.8).

    Read-only in the strongest sense: it modifies nothing, heals nothing and
    infers nothing. A damaged edge is shown as it is stored.

    Determinism comes from processing the frontier in ascending memory id and
    each node's incident edges in ascending edge id, depth by depth — so the
    same database always yields the same document, including the same
    truncation point.

    Caps TRUNCATE rather than refuse (D-v0.3.42), and say so: an inspector
    that gives up on a large graph is useless exactly when it matters, and one
    that silently stops early reads as "that is the whole neighbourhood".
    """
    if depth not in range(1, MAX_GRAPH_DEPTH + 1):
        raise AosError(
            f"Invalid --depth {depth}. Allowed: "
            + "|".join(str(d) for d in range(1, MAX_GRAPH_DEPTH + 1))
        )
    get_memory(conn, memory_id)  # refuse an unknown start, before anything else
    now = utils.utc_now_iso()

    nodes: dict[int, int] = {memory_id: 0}
    edges: list[dict] = []
    seen_edges: set[int] = set()
    frontier = [memory_id]
    truncated = False

    for level in range(1, depth + 1):
        next_frontier: list[int] = []
        for node_id in sorted(frontier):
            if truncated:
                break
            for row in conn.execute(
                "SELECT * FROM memory_edges WHERE from_memory_id = ? "
                "OR to_memory_id = ? ORDER BY id",
                (node_id, node_id),
            ).fetchall():
                edge = MemoryEdge.from_row(row)
                if edge.id in seen_edges:
                    continue  # already reported from its other endpoint
                other = (
                    edge.to_memory_id
                    if edge.from_memory_id == node_id
                    else edge.from_memory_id
                )
                if other not in nodes and len(nodes) >= MAX_GRAPH_NODES:
                    # Drop the EDGE too: an edge to a node the document does
                    # not contain is not a smaller answer, it is a wrong one.
                    truncated = True
                    continue
                if len(seen_edges) >= MAX_GRAPH_EDGES:
                    truncated = True
                    break
                seen_edges.add(edge.id)
                doc = memory_edge_public(conn, edge, now)
                doc["direction"] = (
                    "out" if edge.from_memory_id == node_id else "in"
                )
                doc["depth"] = level
                edges.append(doc)
                if other not in nodes:
                    nodes[other] = level
                    next_frontier.append(other)
        frontier = next_frontier
        if truncated or not frontier:
            break

    return {
        "memory": ids.render_id("memory", memory_id),
        "depth": depth,
        "truncated": truncated,
        "limits": {"nodes": MAX_GRAPH_NODES, "edges": MAX_GRAPH_EDGES},
        "nodes": [
            _graph_node(conn, nid, now, level)
            for nid, level in sorted(nodes.items(), key=lambda kv: (kv[1], kv[0]))
        ],
        "edges": edges,
    }


def memory_graph_counts(conn: sqlite3.Connection, memory_id: int) -> dict:
    """Bounded active counts for one claim — the only graph fact packs and the
    mirror are allowed to show (M3.13). Counts, never neighbours: U-M3 does no
    graph expansion into context."""
    now = utils.utc_now_iso()
    sources = active = 0
    for row in conn.execute(
        "SELECT s.valid_from, s.valid_until FROM memory_source_links l "
        "JOIN memory_sources s ON s.id = l.source_id WHERE l.memory_id = ?",
        (memory_id,),
    ):
        sources += 1
        if window_is_active(row["valid_from"], row["valid_until"], now):
            active += 1
    edges = contradictions = 0
    for row in conn.execute(
        "SELECT relation, valid_from, valid_until FROM memory_edges "
        "WHERE from_memory_id = ? OR to_memory_id = ?",
        (memory_id, memory_id),
    ):
        if not window_is_active(row["valid_from"], row["valid_until"], now):
            continue
        edges += 1
        if row["relation"] == MEMORY_EDGE_CONTRADICTS:
            contradictions += 1
    return {
        "sources": sources,
        "active_sources": active,
        "active_edges": edges,
        "active_contradictions": contradictions,
    }


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
#
# U-A1 retired the ungoverned v3 writers (`add_agent`, `update_agent`): the
# governed verbs live in passports.py, which owns identity creation, the
# immutable passport history, lifecycle transitions and the no-laundering
# gate. This lookup stays here because domain code below (and passports.py
# itself) needs it without a dependency cycle.

def get_agent(conn: sqlite3.Connection, name: str) -> Agent | None:
    row = conn.execute(
        "SELECT * FROM agents WHERE name = ?", (name,)
    ).fetchone()
    return Agent.from_row(row) if row else None


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
