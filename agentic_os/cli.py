"""CLI: argparse wiring, exit codes, output.

Contract: exit 0 success · 1 user/domain error · 2 unexpected internal error.
Errors are ONE actionable line on stderr (traceback only with AOS_DEBUG=1).
Data goes to stdout; with --json, stdout is exactly one JSON document.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import traceback
from pathlib import Path

from . import db, ids, obsidian, ops, utils
from .utils import AosError


class _Parser(argparse.ArgumentParser):
    """argparse that reports usage errors as domain errors (exit 1, one line)."""

    def error(self, message):
        raise AosError(f"{message}. See: python aos.py --help")


def _resolve_aos_dir(args) -> Path:
    """Global --root (PATH/.agentic-os, no search) wins over cwd-upward
    discovery; without it, Night-1 discovery behavior is preserved exactly."""
    root = getattr(args, "global_root", None)
    if root is not None:
        return utils.aos_dir_for_root(Path(root).expanduser().resolve())
    return utils.require_aos_dir()


@contextlib.contextmanager
def _ledger(args):
    aos_dir = _resolve_aos_dir(args)
    conn = db.open_db(aos_dir)
    try:
        yield aos_dir, conn
    finally:
        conn.close()


def _print_json(obj) -> None:
    print(utils.json_dumps(obj))


def _dash(value) -> str:
    return "-" if value in (None, "") else str(value)


# ---------------------------------------------------------------------------
# Command handlers

def cmd_init(args) -> int:
    global_root = getattr(args, "global_root", None)
    if global_root is not None and args.root is not None:
        resolved_global = Path(global_root).expanduser().resolve()
        resolved_local = Path(args.root).expanduser().resolve()
        if resolved_global != resolved_local:
            raise AosError(
                f"Conflicting workspace roots: global --root {resolved_global} "
                f"vs init --root {resolved_local}. Pass one (or the same path)."
            )
    chosen = global_root if global_root is not None else args.root
    root = Path(chosen).expanduser().resolve() if chosen else Path.cwd()
    if not root.is_dir():
        raise AosError(f"Root is not an existing directory: {root}")
    aos_dir, created = ops.init_workspace(root)
    if created:
        print(f"Initialized Agentic OS workspace at {aos_dir}")
    else:
        print(
            f"Already initialized at {aos_dir} "
            f"(schema_version {db.SCHEMA_VERSION}); nothing to do."
        )
    return 0


def cmd_project_add(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        project, created = ops.add_project(
            conn, slug=args.slug, name=args.name, repo=args.repo
        )
        if created:
            print(f"Added project {project.slug} → {project.repo_path}")
        else:
            print(f"Project '{project.slug}' already exists; nothing changed.")
    return 0


def cmd_task_add(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        task = ops.add_task(
            conn,
            title=args.title,
            project_slug=args.project,
            kind=args.kind,
            acceptance=args.accept,
            priority=args.priority,
        )
        print(ids.render_id("task", task.id))
    return 0


def cmd_task_list(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        tasks = ops.list_tasks(
            conn, project_slug=args.project, status=args.status
        )
        if args.json:
            _print_json({"tasks": tasks})
            return 0
        if not tasks:
            print("(no tasks)")
            return 0
        for task in tasks:
            print(
                f"{task['id']:<8} {task['status']:<12} {task['kind']:<9} "
                f"p{task['priority']:<3} {_dash(task['project']):<16} "
                f"{task['title']}"
            )
    return 0


def cmd_task_show(args) -> int:
    task_id = ids.parse_id(args.id, "task")
    with _ledger(args) as (aos_dir, conn):
        detail = ops.show_task(conn, task_id)
        if args.json:
            _print_json(detail)
            return 0
        task = detail["task"]
        project = detail["project"]
        print(f"{task['id']}  {task['title']}")
        if project:
            print(f"project:  {project['slug']} ({project['name']})")
            print(f"repo:     {project['repo_path']}")
        else:
            print("project:  -")
        print(
            f"status:   {task['status']}   kind: {task['kind']}   "
            f"priority: {task['priority']}   assignee: {_dash(task['assignee'])}"
        )
        print(
            f"created:  {task['created_at']}   updated: {task['updated_at']}   "
            f"closed: {_dash(task['closed_at'])}"
        )
        print(f"acceptance: {_dash(task['acceptance_md'])}")
        print(f"spec:       {_dash(task['spec_md'])}")
        for heading, rows, line in (
            (
                "runs",
                detail["runs"],
                lambda r: f"  {r['id']}  {r['agent']}  {_dash(r['outcome'])}  "
                f"{r['started_at']} → {_dash(r['ended_at'])}  "
                f"anchor={_dash(r['anchor_commit'])}",
            ),
            (
                "decisions",
                detail["decisions"],
                lambda d: f"  {d['id']}  [{d['status']}] {d['title']}",
            ),
            (
                "evidence",
                detail["evidence"],
                lambda e: f"  {e['id']}  {e['kind']}  {e['ref']}  "
                f"claim={_dash(e['claim'])}  [{e['provenance']}]",
            ),
            (
                "handoffs",
                detail["handoffs"],
                lambda h: f"  {h['id']}  {h['from_agent']} → {h['to_agent']}  "
                f"accepted={_dash(h['accepted_at'])}",
            ),
        ):
            print(f"{heading}:")
            if rows:
                for row in rows:
                    print(line(row))
            else:
                print("  (none)")
    return 0


def cmd_status(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        summary = ops.status_summary(conn)
        if args.json:
            _print_json(summary)
            return 0
        print(f"projects:   {summary['projects']}")
        print(f"open tasks: {summary['open_tasks']}")

        def block(title: str, rows, line) -> None:
            print(f"{title}:")
            if rows:
                for row in rows:
                    print(line(row))
            else:
                print("  (none)")

        block(
            "recent tasks",
            summary["recent_tasks"],
            lambda t: f"  {t['id']}  {t['status']:<12} {t['title']}",
        )
        block(
            "tasks missing evidence",
            summary["tasks_missing_evidence"],
            lambda t: f"  {t['id']}  {t['status']:<12} {t['title']}",
        )
        block(
            "last runs",
            summary["last_runs"],
            lambda r: f"  {r['id']}  {r['task']}  {r['agent']}  "
            f"{_dash(r['outcome'])}  ended={_dash(r['ended_at'])}",
        )
    return 0


def cmd_in(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        task = ops.capture_inbox(conn, args.text)
        print(ids.render_id("task", task.id))
    return 0


def cmd_log(args) -> int:
    if args.task_id is not None and args.today:
        raise AosError("Use either a task id or --today, not both.")
    task_id = ids.parse_id(args.task_id, "task") if args.task_id is not None else None
    with _ledger(args) as (aos_dir, conn):
        entries = ops.log_events(conn, task_id=task_id, today=args.today)
        if args.json:
            _print_json({"events": entries})
            return 0
        if not entries:
            print("(no events)")
            return 0
        for event in entries:
            entity = event["entity"]
            if event["entity_id"] is not None:
                entity = f"{entity}#{event['entity_id']}"
            print(
                f"{event['id']:>5}  {event['ts']}  {event['actor']:<18} "
                f"{entity:<14} {event['action']}"
            )
    return 0


def cmd_pack_build(args) -> int:
    task_id = ids.parse_id(args.id, "task")
    with _ledger(args) as (aos_dir, conn):
        from . import pack

        result = pack.build_pack(
            conn,
            aos_dir,
            task_id=task_id,
            target=args.target,
            budget_kb=args.budget_kb,
        )
        for warning in result.get("warnings", []):
            print(warning, file=sys.stderr)
        print(result["path"])
    return 0


def cmd_run_start(args) -> int:
    task_id = ids.parse_id(args.id, "task")
    with _ledger(args) as (aos_dir, conn):
        run = ops.start_run(conn, task_id=task_id, agent=args.agent)
        print(ids.render_id("run", run.id))
    return 0


def cmd_run_end(args) -> int:
    run_id = ids.parse_id(args.id, "run")
    with _ledger(args) as (aos_dir, conn):
        run = ops.end_run(
            conn, run_id=run_id, outcome=args.outcome, summary=args.summary
        )
        print(f"{ids.render_id('run', run.id)} ended: {run.outcome}")
    return 0


def cmd_evidence_add(args) -> int:
    task_id = ids.parse_id(args.id, "task")
    with _ledger(args) as (aos_dir, conn):
        item = ops.add_evidence(
            conn,
            task_id=task_id,
            kind=args.kind,
            ref=args.ref,
            claim=args.claim,
            provenance=args.provenance,
        )
        print(ids.render_id("evidence", item.id))
    return 0


def cmd_done(args) -> int:
    task_id = ids.parse_id(args.id, "task")
    with _ledger(args) as (aos_dir, conn):
        task = ops.mark_done(conn, task_id=task_id, no_evidence=args.no_evidence)
        count = ops.evidence_count(conn, task.id)
        print(f"{ids.render_id('task', task.id)} done (evidence: {count})")
    return 0


def cmd_decision_add(args) -> int:
    task_id = ids.parse_id(args.task, "task") if args.task is not None else None
    with _ledger(args) as (aos_dir, conn):
        decision = ops.add_decision(
            conn,
            title=args.title,
            project_slug=args.project,
            decision=args.decision,
            alternatives=args.alternatives,
            task_id=task_id,
        )
        print(ids.render_id("decision", decision.id))
    return 0


def cmd_handoff_create(args) -> int:
    task_id = ids.parse_id(args.id, "task")
    with _ledger(args) as (aos_dir, conn):
        handoff = ops.create_handoff(
            conn,
            task_id=task_id,
            from_agent=args.from_agent,
            to_agent=args.to,
            state=args.state,
        )
        print(ids.render_id("handoff", handoff.id))
    return 0


def cmd_handoff_accept(args) -> int:
    handoff_id = ids.parse_id(args.id, "handoff")
    with _ledger(args) as (aos_dir, conn):
        handoff = ops.accept_handoff(conn, handoff_id=handoff_id)
        print(
            f"{ids.render_id('handoff', handoff.id)} accepted at "
            f"{handoff.accepted_at}"
        )
    return 0


def cmd_memory_add(args) -> int:
    supersedes_id = (
        ids.parse_id(args.supersedes, "memory")
        if args.supersedes is not None
        else None
    )
    with _ledger(args) as (aos_dir, conn):
        item = ops.add_memory(
            conn,
            scope=args.scope,
            project_slug=args.project,
            kind=args.kind,
            key=args.key,
            value=args.value,
            source=args.source,
            confidence=args.confidence,
            valid_until=args.valid_until,
            supersedes_id=supersedes_id,
        )
        print(ids.render_id("memory", item.id))
    return 0


def cmd_memory_list(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        items = ops.list_memory(
            conn, scope=args.scope, project_slug=args.project
        )
        if args.json:
            _print_json({"memories": items})
            return 0
        if not items:
            print("(no memory)")
            return 0
        for item in items:
            if item["superseded_by"]:
                state = f"superseded→{item['superseded_by']}"
            elif not item["live"]:
                state = f"retired {item['valid_until']}"
            else:
                state = "live"
            value_one_line = " ".join(item["value_md"].split())
            print(
                f"{item['id']:<8} {item['scope']:<8} "
                f"{_dash(item['project']):<16} {item['kind']:<11} "
                f"[{item['confidence']}] {state:<26} "
                f"{item['key']}: {value_one_line}"
            )
    return 0


def cmd_memory_retire(args) -> int:
    memory_id = ids.parse_id(args.id, "memory")
    with _ledger(args) as (aos_dir, conn):
        item = ops.retire_memory(conn, memory_id=memory_id)
        print(
            f"{ids.render_id('memory', item.id)} retired "
            f"(valid_until {item.valid_until})"
        )
    return 0


def cmd_search(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        from . import search

        doc = search.search(conn, args.query)
        if args.json:
            _print_json(doc)
            return 0
        print(f"backend: {doc['backend']}")
        if not doc["results"]:
            print("(no results)")
            return 0
        for result in doc["results"]:
            print(
                f"{result['type']:<9} {result['id']:<8} {result['snippet']}"
            )
    return 0


def cmd_review_build(args) -> int:
    date_str = args.date if args.date is not None else utils.utc_today()
    utils.validate_date(date_str, "--date")
    with _ledger(args) as (aos_dir, conn):
        from . import review

        path = review.build_review(conn, aos_dir, date_str)
        print(str(path))
    return 0


def cmd_export_events(args) -> int:
    if not args.jsonl:
        raise AosError("Only JSONL export is supported. Pass --jsonl.")
    with _ledger(args) as (aos_dir, conn):
        from . import export

        path, _count = export.export_events(conn, aos_dir, output=args.output)
        print(str(path))
    return 0


def cmd_snapshot(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        from . import export

        path = export.snapshot(conn, aos_dir)
        print(str(path))
    return 0


def cmd_sync(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        total, written = obsidian.sync_vault(conn, aos_dir)
        print(f"Synced {total} notes ({written} written, {total - written} unchanged).")
    return 0


def cmd_doctor(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        from . import doctor

        checks = doctor.run_checks(conn, aos_dir)
    failed = [c for c in checks if not c.ok]
    for check in checks:
        marker = "PASS" if check.ok else "FAIL"
        detail = f" — {check.detail}" if check.detail else ""
        print(f"[{marker}] {check.name}{detail}")
    if failed:
        print(f"{len(failed)} check(s) failed.", file=sys.stderr)
        return 1
    return 0


# ---------------------------------------------------------------------------
# Parser

def build_parser() -> _Parser:
    parser = _Parser(
        prog="aos",
        description="Agentic OS — local-first ledger + Obsidian mirror "
        "for coordinating AI agents.",
    )
    parser.add_argument(
        "--root",
        dest="global_root",
        metavar="PATH",
        default=None,
        help="workspace root: use PATH/.agentic-os instead of cwd-upward "
        "discovery (place before the command)",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)

    p_init = sub.add_parser("init", help="initialize the workspace")
    p_init.add_argument("--root", help="workspace root (default: current directory)")
    p_init.set_defaults(func=cmd_init)

    p_project = sub.add_parser("project", help="manage projects")
    project_sub = p_project.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )
    p_project_add = project_sub.add_parser("add", help="add a project")
    p_project_add.add_argument("slug")
    p_project_add.add_argument("--name", required=True)
    p_project_add.add_argument("--repo", required=True)
    p_project_add.set_defaults(func=cmd_project_add)

    p_task = sub.add_parser("task", help="manage tasks")
    task_sub = p_task.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )
    p_task_add = task_sub.add_parser("add", help="add a task")
    p_task_add.add_argument("title")
    p_task_add.add_argument("-p", "--project", required=True)
    p_task_add.add_argument("--kind", default="code")
    p_task_add.add_argument("--accept", default=None)
    p_task_add.add_argument("--priority", type=int, default=2)
    p_task_add.set_defaults(func=cmd_task_add)
    p_task_list = task_sub.add_parser("list", help="list tasks")
    p_task_list.add_argument("--project", default=None)
    p_task_list.add_argument("--status", default=None)
    p_task_list.add_argument("--json", action="store_true")
    p_task_list.set_defaults(func=cmd_task_list)
    p_task_show = task_sub.add_parser("show", help="show one task")
    p_task_show.add_argument("id")
    p_task_show.add_argument("--json", action="store_true")
    p_task_show.set_defaults(func=cmd_task_show)

    p_status = sub.add_parser("status", help="workspace overview")
    p_status.add_argument("--json", action="store_true")
    p_status.set_defaults(func=cmd_status)

    p_in = sub.add_parser("in", help="quick inbox capture")
    p_in.add_argument("text")
    p_in.set_defaults(func=cmd_in)

    p_pack = sub.add_parser("pack", help="context packs")
    pack_sub = p_pack.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )
    p_pack_build = pack_sub.add_parser("build", help="build a context pack")
    p_pack_build.add_argument("id")
    p_pack_build.add_argument("--for", dest="target", default="claude-code")
    p_pack_build.add_argument("--budget-kb", type=int, default=24)
    p_pack_build.set_defaults(func=cmd_pack_build)

    p_run = sub.add_parser("run", help="agent runs")
    run_sub = p_run.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )
    p_run_start = run_sub.add_parser("start", help="start a run")
    p_run_start.add_argument("id")
    p_run_start.add_argument("--agent", required=True)
    p_run_start.set_defaults(func=cmd_run_start)
    p_run_end = run_sub.add_parser("end", help="end a run")
    p_run_end.add_argument("id")
    p_run_end.add_argument("--outcome", required=True)
    p_run_end.add_argument("--summary", required=True)
    p_run_end.set_defaults(func=cmd_run_end)

    p_evidence = sub.add_parser("evidence", help="evidence records")
    evidence_sub = p_evidence.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )
    p_evidence_add = evidence_sub.add_parser("add", help="attach evidence to a task")
    p_evidence_add.add_argument("id")
    p_evidence_add.add_argument("--kind", required=True)
    p_evidence_add.add_argument("--ref", required=True)
    p_evidence_add.add_argument("--claim", default=None)
    p_evidence_add.add_argument("--provenance", default="human")
    p_evidence_add.set_defaults(func=cmd_evidence_add)

    p_decision = sub.add_parser("decision", help="decision records")
    decision_sub = p_decision.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )
    p_decision_add = decision_sub.add_parser(
        "add", help="record an accepted decision"
    )
    p_decision_add.add_argument("title")
    p_decision_add.add_argument("-p", "--project", required=True)
    p_decision_add.add_argument("--decision", required=True)
    p_decision_add.add_argument("--alternatives", default=None)
    p_decision_add.add_argument("--task", default=None)
    p_decision_add.set_defaults(func=cmd_decision_add)

    p_handoff = sub.add_parser("handoff", help="structured agent handoffs")
    handoff_sub = p_handoff.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )
    p_handoff_create = handoff_sub.add_parser(
        "create", help="hand a task from one agent to another"
    )
    p_handoff_create.add_argument("id")
    p_handoff_create.add_argument("--from", dest="from_agent", required=True)
    p_handoff_create.add_argument("--to", required=True)
    p_handoff_create.add_argument("--state", required=True)
    p_handoff_create.set_defaults(func=cmd_handoff_create)
    p_handoff_accept = handoff_sub.add_parser("accept", help="accept a handoff")
    p_handoff_accept.add_argument("id")
    p_handoff_accept.set_defaults(func=cmd_handoff_accept)

    p_memory = sub.add_parser("memory", help="scoped memory rows")
    memory_sub = p_memory.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )
    p_memory_add = memory_sub.add_parser("add", help="record a memory row")
    p_memory_add.add_argument("--scope", required=True)
    p_memory_add.add_argument("-p", "--project", default=None)
    p_memory_add.add_argument("--kind", required=True)
    p_memory_add.add_argument("--key", required=True)
    p_memory_add.add_argument("--value", required=True)
    p_memory_add.add_argument("--source", required=True)
    p_memory_add.add_argument("--confidence", required=True)
    p_memory_add.add_argument("--valid-until", dest="valid_until", default=None)
    p_memory_add.add_argument("--supersedes", default=None)
    p_memory_add.set_defaults(func=cmd_memory_add)
    p_memory_list = memory_sub.add_parser("list", help="list memory rows")
    p_memory_list.add_argument("--scope", default=None)
    p_memory_list.add_argument("-p", "--project", default=None)
    p_memory_list.add_argument("--json", action="store_true")
    p_memory_list.set_defaults(func=cmd_memory_list)
    p_memory_retire = memory_sub.add_parser(
        "retire", help="retire a memory row (sets valid_until to now)"
    )
    p_memory_retire.add_argument("id")
    p_memory_retire.set_defaults(func=cmd_memory_retire)

    p_done = sub.add_parser("done", help="close a task (requires evidence)")
    p_done.add_argument("id")
    p_done.add_argument("--no-evidence", action="store_true")
    p_done.set_defaults(func=cmd_done)

    p_search = sub.add_parser(
        "search", help="search tasks, decisions, evidence, handoffs, memory"
    )
    p_search.add_argument("query")
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(func=cmd_search)

    p_review = sub.add_parser("review", help="review notes")
    review_sub = p_review.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )
    p_review_build = review_sub.add_parser(
        "build", help="build (or refresh) the review note for a date"
    )
    p_review_build.add_argument(
        "--date", default=None, metavar="YYYY-MM-DD",
        help="review date (default: today, UTC)",
    )
    p_review_build.set_defaults(func=cmd_review_build)

    p_export = sub.add_parser("export", help="export ledger data")
    export_sub = p_export.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )
    p_export_events = export_sub.add_parser(
        "events", help="export the event journal as JSONL"
    )
    p_export_events.add_argument("--jsonl", action="store_true")
    p_export_events.add_argument("--output", default=None, metavar="PATH")
    p_export_events.set_defaults(func=cmd_export_events)

    p_snapshot = sub.add_parser(
        "snapshot", help="snapshot aos.db via the SQLite backup API"
    )
    p_snapshot.set_defaults(func=cmd_snapshot)

    p_sync = sub.add_parser("sync", help="regenerate the Obsidian mirror")
    p_sync.set_defaults(func=cmd_sync)

    p_log = sub.add_parser("log", help="event journal")
    p_log.add_argument("task_id", nargs="?", default=None)
    p_log.add_argument("--today", action="store_true")
    p_log.add_argument("--json", action="store_true")
    p_log.set_defaults(func=cmd_log)

    p_doctor = sub.add_parser("doctor", help="health checks")
    p_doctor.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        return args.func(args)
    except AosError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except SystemExit:
        raise
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 2
    except Exception as exc:  # unexpected internal error → exit 2
        if os.environ.get("AOS_DEBUG") == "1":
            traceback.print_exc()
        else:
            print(
                f"Internal error: {exc.__class__.__name__}: {exc} "
                "(set AOS_DEBUG=1 for a traceback)",
                file=sys.stderr,
            )
        return 2
