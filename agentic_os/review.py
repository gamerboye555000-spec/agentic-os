"""Review notes: generated reviews under AOS/Reviews/.

Three builds share one engine (same sections, same splice rules):
- daily   → Reviews/YYYY-MM-DD.md      (`review build [--date]`)
- weekly  → Reviews/YYYY-Www.md        (`review weekly [--date]`, ISO week)
- project → Reviews/project-<slug>.md  (`review project SLUG [--date]`)

Like sync, every build is a derived view of ledger state (plus the review
date): it mutates no ledger rows and emits no event (extends D-P0.6, see
D-W6.1). Everything ABOVE the "## Notes" line is regenerated; the "## Notes"
line and everything after it is preserved byte-for-byte — that region belongs
to the human, so it is spliced back verbatim (even CR bytes survive; the
LF-normalization rule applies to generated content only, D-W6.3).

All "recent"/"stale" windows are computed from the review date parameter —
the only wall-clock read is the default date, which comes from the single
clock utility.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from pathlib import Path

from . import ids, obsidian
from .utils import AosError

NOTES_HEADING = b"## Notes"
DEFAULT_TAIL = b"## Notes\n"

RECENT_DAYS = 7
STALE_MEMORY_DAYS = 30


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _notes_tail(data: bytes) -> bytes | None:
    """The preserved region: from the first line reading '## Notes' (any
    line ending) to EOF, byte-for-byte. None when no such line exists."""
    pos = 0
    while True:
        line_end = data.find(b"\n", pos)
        line = data[pos: line_end if line_end != -1 else len(data)]
        if line.rstrip(b"\r") == NOTES_HEADING:
            return data[pos:]
        if line_end == -1:
            return None
        pos = line_end + 1


def _section_block(heading: str, bullet_lines: list[str]) -> list[str]:
    return [f"## {heading}", ""] + (bullet_lines or ["*(none)*"]) + [""]


def _head_text(
    conn: sqlite3.Connection,
    *,
    title: str,
    date_str: str,
    recent_floor: str,
    date_ceiling: str,
    stale_floor: str,
    project_id: int | None = None,
) -> str:
    """Everything above '## Notes' — a pure function of DB state plus the
    window parameters. `project_id` filters every section to one project."""
    task_filter = "" if project_id is None else "AND t.project_id = ?"
    task_params: tuple = () if project_id is None else (project_id,)
    memory_filter = "" if project_id is None else "AND m.project_id = ?"

    slug_by_project_id = {
        row["id"]: row["slug"]
        for row in conn.execute("SELECT id, slug FROM projects")
    }

    attention = []
    for row in conn.execute(
        "SELECT t.id, t.title, "
        "NOT EXISTS (SELECT 1 FROM evidence e WHERE e.task_id = t.id) "
        "AS no_evidence, "
        "EXISTS (SELECT 1 FROM events ev WHERE ev.entity = 'task' "
        "AND ev.entity_id = t.id AND ev.action = 'done_override') "
        "AS overridden "
        f"FROM tasks t WHERE t.status = 'done' {task_filter} ORDER BY t.id",
        task_params,
    ):
        reasons = []
        if row["no_evidence"]:
            reasons.append("no evidence")
        if row["overridden"]:
            reasons.append("closed via --no-evidence override")
        if reasons:
            task_hid = ids.render_id("task", row["id"])
            attention.append(
                f"- [[{task_hid}]] {_one_line(row['title'])} — "
                + "; ".join(reasons)
            )

    open_tasks = [
        f"- [[{ids.render_id('task', row['id'])}]] {_one_line(row['title'])} "
        f"· {row['status']} · "
        f"{slug_by_project_id.get(row['project_id']) or '-'}"
        for row in conn.execute(
            "SELECT t.id, t.title, t.status, t.project_id FROM tasks t "
            f"WHERE t.status != 'done' {task_filter} ORDER BY t.id",
            task_params,
        )
    ]

    recent_evidence = [
        f"- [[{ids.render_id('evidence', row['id'])}]] {row['kind']} · "
        f"{_one_line(row['ref'])} · [[{ids.render_id('task', row['task_id'])}]]"
        for row in conn.execute(
            "SELECT e.id, e.task_id, e.kind, e.ref FROM evidence e "
            "JOIN tasks t ON t.id = e.task_id "
            f"WHERE e.created_at >= ? AND e.created_at <= ? {task_filter} "
            "ORDER BY e.id",
            (recent_floor, date_ceiling, *task_params),
        )
    ]

    stale_memory = []
    for row in conn.execute(
        "SELECT m.id, m.key, m.confidence, m.valid_until, m.updated_at "
        "FROM memory m "
        "WHERE ((m.valid_until IS NOT NULL "
        "AND substr(m.valid_until, 1, 10) <= ?) "
        "OR (m.valid_until IS NULL AND substr(m.updated_at, 1, 10) <= ?)) "
        f"{memory_filter} ORDER BY m.id",
        (date_str, stale_floor, *task_params),
    ):
        memory_hid = ids.render_id("memory", row["id"])
        if row["valid_until"] is not None:
            detail = f"valid_until {row['valid_until']} passed"
        else:
            detail = f"not updated since {row['updated_at']}"
        stale_memory.append(
            f"- [[{memory_hid}]] {_one_line(row['key'])} "
            f"· [{row['confidence']}] · {detail}"
        )

    recent_runs = [
        f"- [[{ids.render_id('run', row['id'])}]] {_one_line(row['agent'])} · "
        f"{row['outcome'] or 'open'} · [[{ids.render_id('task', row['task_id'])}]]"
        for row in conn.execute(
            "SELECT r.id, r.task_id, r.agent, r.outcome FROM runs r "
            "JOIN tasks t ON t.id = r.task_id "
            f"WHERE r.started_at >= ? AND r.started_at <= ? {task_filter} "
            "ORDER BY r.id",
            (recent_floor, date_ceiling, *task_params),
        )
    ]

    open_handoffs = [
        f"- [[{ids.render_id('handoff', row['id'])}]] "
        f"{_one_line(row['from_agent'])} → {_one_line(row['to_agent'])} "
        f"· [[{ids.render_id('task', row['task_id'])}]]"
        for row in conn.execute(
            "SELECT h.id, h.task_id, h.from_agent, h.to_agent FROM handoffs h "
            "JOIN tasks t ON t.id = h.task_id "
            f"WHERE h.accepted_at IS NULL {task_filter} ORDER BY h.id",
            task_params,
        )
    ]

    stale_in_progress = []
    for row in conn.execute(
        "SELECT t.id, t.title FROM tasks t "
        f"WHERE t.status = 'in_progress' {task_filter} ORDER BY t.id",
        task_params,
    ):
        has_open_run = conn.execute(
            "SELECT 1 FROM runs WHERE task_id = ? AND ended_at IS NULL "
            "LIMIT 1",
            (row["id"],),
        ).fetchone() is not None
        has_recent_activity = conn.execute(
            "SELECT 1 FROM runs WHERE task_id = ? AND "
            "((started_at >= ? AND started_at <= ?) "
            "OR (ended_at IS NOT NULL AND ended_at >= ? AND ended_at <= ?)) "
            "LIMIT 1",
            (
                row["id"],
                recent_floor, date_ceiling,
                recent_floor, date_ceiling,
            ),
        ).fetchone() is not None
        reasons = []
        if not has_open_run:
            reasons.append("no open run")
        if not has_recent_activity:
            reasons.append("no run activity in the window")
        if reasons:
            task_hid = ids.render_id("task", row["id"])
            stale_in_progress.append(
                f"- [[{task_hid}]] {_one_line(row['title'])} — "
                + "; ".join(reasons)
            )

    done_without_commit = [
        f"- [[{ids.render_id('task', row['id'])}]] {_one_line(row['title'])} "
        "— no commit evidence"
        for row in conn.execute(
            "SELECT t.id, t.title FROM tasks t "
            "WHERE t.status = 'done' AND t.kind = 'code' "
            "AND NOT EXISTS (SELECT 1 FROM evidence e "
            "WHERE e.task_id = t.id AND e.kind = 'commit') "
            f"{task_filter} ORDER BY t.id",
            task_params,
        )
    ]

    # Unlike "Stale memory" above (whose D-W6.2 quirk is pinned by existing
    # tests), refresh candidates are LIVE rows only: superseded and retired
    # rows need no refresh — their successors do.
    memory_refresh = [
        f"- [[{ids.render_id('memory', row['id'])}]] {_one_line(row['key'])} "
        f"· [{row['confidence']}] · not updated since {row['updated_at']}"
        for row in conn.execute(
            "SELECT m.id, m.key, m.confidence, m.updated_at FROM memory m "
            "WHERE m.superseded_by IS NULL "
            "AND (m.valid_until IS NULL OR substr(m.valid_until, 1, 10) > ?) "
            "AND substr(m.updated_at, 1, 10) <= ? "
            f"{memory_filter} ORDER BY m.id",
            (date_str, stale_floor, *task_params),
        )
    ]

    lines = [title, ""]
    lines += _section_block("Done tasks needing attention", attention)
    lines += _section_block("Open tasks", open_tasks)
    lines += _section_block("Recent evidence", recent_evidence)
    lines += _section_block("Stale memory", stale_memory)
    lines += _section_block("Recent runs", recent_runs)
    lines += _section_block("Open handoffs", open_handoffs)
    lines += _section_block("Stale in-progress tasks", stale_in_progress)
    lines += _section_block(
        "Code tasks done without commit evidence", done_without_commit
    )
    lines += _section_block("Memory needing refresh", memory_refresh)
    return "\n".join(lines) + "\n"


def _write_with_notes_tail(aos_dir: Path, filename: str, head: str) -> Path:
    reviews_dir = obsidian.vault_aos_dir(aos_dir) / "Reviews"
    path = reviews_dir / filename
    tail = None
    if path.is_file():
        tail = _notes_tail(path.read_bytes())
    if tail is None:
        tail = DEFAULT_TAIL
    new_bytes = head.encode("utf-8") + tail
    if not path.is_file() or path.read_bytes() != new_bytes:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(new_bytes)
    return path


def _daily_windows(date_str: str) -> tuple[str, str, str]:
    review_date = date.fromisoformat(date_str)
    recent_floor = (review_date - timedelta(days=RECENT_DAYS - 1)).isoformat()
    date_ceiling = date_str + "~"  # '~' > 'T', so any timestamp on date_str
    stale_floor = (review_date - timedelta(days=STALE_MEMORY_DAYS)).isoformat()
    return recent_floor, date_ceiling, stale_floor


def build_review(conn: sqlite3.Connection, aos_dir: Path, date_str: str) -> Path:
    recent_floor, date_ceiling, stale_floor = _daily_windows(date_str)
    head = _head_text(
        conn,
        title=f"# Review {date_str}",
        date_str=date_str,
        recent_floor=recent_floor,
        date_ceiling=date_ceiling,
        stale_floor=stale_floor,
    )
    return _write_with_notes_tail(aos_dir, f"{date_str}.md", head)


def build_weekly_review(
    conn: sqlite3.Connection, aos_dir: Path, date_str: str
) -> Path:
    """The ISO week (Mon–Sun) containing `date_str`; windows span the week
    and point-in-time sections are as of the week's end."""
    review_date = date.fromisoformat(date_str)
    iso = review_date.isocalendar()
    monday = review_date - timedelta(days=review_date.isoweekday() - 1)
    sunday = monday + timedelta(days=6)
    week_label = f"{iso.year}-W{iso.week:02d}"
    head = _head_text(
        conn,
        title=f"# Review week {week_label}",
        date_str=sunday.isoformat(),
        recent_floor=monday.isoformat(),
        date_ceiling=sunday.isoformat() + "~",
        stale_floor=(sunday - timedelta(days=STALE_MEMORY_DAYS)).isoformat(),
    )
    return _write_with_notes_tail(aos_dir, f"{week_label}.md", head)


def build_project_review(
    conn: sqlite3.Connection, aos_dir: Path, slug: str, date_str: str
) -> Path:
    row = conn.execute(
        "SELECT id FROM projects WHERE slug = ?", (slug,)
    ).fetchone()
    if row is None:
        raise AosError(
            f"No project '{slug}'. Run: python aos.py project add "
            f"{slug} --name NAME --repo PATH"
        )
    recent_floor, date_ceiling, stale_floor = _daily_windows(date_str)
    head = _head_text(
        conn,
        title=f"# Review {date_str} — project {slug}",
        date_str=date_str,
        recent_floor=recent_floor,
        date_ceiling=date_ceiling,
        stale_floor=stale_floor,
        project_id=row["id"],
    )
    return _write_with_notes_tail(aos_dir, f"project-{slug}.md", head)
