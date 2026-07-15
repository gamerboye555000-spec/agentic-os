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
            spec=args.spec,
        )
        print(ids.render_id("task", task.id))
    return 0


def cmd_task_assign(args) -> int:
    task_id = ids.parse_id(args.id, "task")
    with _ledger(args) as (aos_dir, conn):
        task, changed = ops.assign_task(
            conn, task_id=task_id, project_slug=args.project
        )
        task_hid = ids.render_id("task", task.id)
        if changed:
            print(f"{task_hid} assigned to project {args.project}")
        else:
            print(f"{task_hid} already in project {args.project}; nothing changed.")
    return 0


def cmd_task_edit(args) -> int:
    task_id = ids.parse_id(args.id, "task")
    with _ledger(args) as (aos_dir, conn):
        task, changed = ops.edit_task(
            conn,
            task_id=task_id,
            title=args.title,
            kind=args.kind,
            priority=args.priority,
            acceptance=args.accept,
            spec=args.spec,
        )
        print(f"{ids.render_id('task', task.id)} edited: {', '.join(changed)}")
    return 0


def cmd_task_status(args) -> int:
    task_id = ids.parse_id(args.id, "task")
    with _ledger(args) as (aos_dir, conn):
        task, from_status = ops.set_task_status(
            conn, task_id=task_id, status=args.status
        )
        print(
            f"{ids.render_id('task', task.id)} status: "
            f"{from_status} → {task.status}"
        )
    return 0


def cmd_task_list(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        tasks = ops.list_tasks(
            conn,
            project_slug=args.project,
            status=args.status,
            kind=args.kind,
            missing_evidence=args.missing_evidence,
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


def cmd_agent_add(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        agent = ops.add_agent(
            conn,
            name=args.name,
            kind=args.kind,
            notes=args.notes,
            capabilities=args.capability,
        )
        print(f"Added agent {agent.name} ({agent.kind})")
    return 0


def cmd_agent_update(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        agent, changed = ops.update_agent(
            conn,
            name=args.name,
            notes=args.notes,
            capabilities=args.capability,
        )
        print(f"{agent.name} updated: {', '.join(changed)}")
    return 0


def cmd_agent_list(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        agents = ops.list_agents(conn)
        if args.json:
            _print_json({"agents": agents})
            return 0
        if not agents:
            print("(no agents)")
            return 0
        for agent in agents:
            capabilities = ",".join(agent["capabilities"]) or "-"
            notes = " ".join(agent["notes"].split()) if agent["notes"] else "-"
            print(
                f"{agent['name']:<16} {agent['kind']:<8} "
                f"{capabilities:<24} {notes}"
            )
    return 0


def cmd_agent_show(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        agent = ops.get_agent(conn, args.name)
        if agent is None:
            raise AosError(
                f"No agent '{args.name}'. Run: python aos.py agent list"
            )
        public = ops.agent_public(agent)
        if args.json:
            _print_json({"agent": public})
            return 0
        print(f"{public['name']}  ({public['kind']})")
        print(
            "capabilities: "
            + (", ".join(public["capabilities"]) or "-")
        )
        print(f"notes:        {_dash(public['notes'])}")
        print(f"invoke hint:  {_dash(public['invoke_hint'])}")
        print(f"trust level:  {public['trust_level']}")
    return 0


def cmd_evidence_git(args) -> int:
    task_id = ids.parse_id(args.id, "task")
    with _ledger(args) as (aos_dir, conn):
        item = ops.add_git_evidence(
            conn,
            task_id=task_id,
            commit=args.commit,
            repo=args.repo,
            claim=args.claim,
        )
        claim = " ".join(item.claim.split()) if item.claim else "-"
        print(
            f"{ids.render_id('evidence', item.id)} commit {item.ref[:12]} "
            f"— {claim}"
        )
    return 0


def cmd_ingest_dropfile(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        from . import ingest

        result = ingest.ingest_dropfile(
            conn, Path(args.path).expanduser()
        )
        print(
            f"Ingested dropfile for {result['task']} from {result['agent']} "
            f"(outcome: {result['outcome']})"
        )
        if result["evidence"]:
            print(f"evidence: {', '.join(result['evidence'])}")
        else:
            print("evidence: (none)")
        if result["run_ended"]:
            print(f"run ended: {result['run_ended']} → {result['outcome']}")
        else:
            print(
                f"runs: {result['open_runs']} open for {result['agent']} — "
                "no run created or ended"
            )
        if result["handoff"]:
            print(f"open questions → handoff {result['handoff']} (to generic)")
    return 0


def cmd_done(args) -> int:
    task_id = ids.parse_id(args.id, "task")
    with _ledger(args) as (aos_dir, conn):
        task = ops.mark_done(
            conn,
            task_id=task_id,
            no_evidence=args.no_evidence,
            reason=args.reason,
        )
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


def cmd_review_weekly(args) -> int:
    date_str = args.date if args.date is not None else utils.utc_today()
    utils.validate_date(date_str, "--date")
    with _ledger(args) as (aos_dir, conn):
        from . import review

        path = review.build_weekly_review(conn, aos_dir, date_str)
        print(str(path))
    return 0


def cmd_review_project(args) -> int:
    date_str = args.date if args.date is not None else utils.utc_today()
    utils.validate_date(date_str, "--date")
    with _ledger(args) as (aos_dir, conn):
        from . import review

        path = review.build_project_review(conn, aos_dir, args.slug, date_str)
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


def cmd_backup_create(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        from . import backup

        result = backup.create_backup(conn, aos_dir)
        print(str(result["path"]))
        print(f"manifest: {result['manifest_path']}")
    return 0


def cmd_backup_verify(args) -> int:
    # Deliberately no _ledger: verifying a backup must work when the live
    # workspace is damaged or absent (that is what backups are for).
    from . import backup

    checks = backup.verify_backup(Path(args.path).expanduser().resolve())
    for check in checks:
        marker = "PASS" if check.ok else "FAIL"
        detail = f" — {check.detail}" if check.detail else ""
        print(f"[{marker}] {check.name}{detail}")
    failed = [check for check in checks if not check.ok]
    if failed:
        print(
            f"Backup verification failed: {failed[0].name}. "
            "Do not restore from this copy.",
            file=sys.stderr,
        )
        return 1
    return 0


def cmd_backup_restore(args) -> int:
    # Deliberately no _ledger: restore must work without a live workspace.
    from . import backup

    target = backup.restore_backup(
        Path(args.path).expanduser().resolve(),
        Path(args.to).expanduser().resolve(),
    )
    print(str(target))
    print(
        "Verified against its manifest before the copy. Adopting it as the "
        "live ledger is your move — see RECOVERY.md for the drill."
    )
    return 0


def _migrate_db_path(args) -> Path:
    """The live ledger path for a migrate subcommand.

    Deliberately not `_ledger`: db.open_db() refuses any version !=
    SCHEMA_VERSION, and a database pending migration is by definition at a
    lower version — the gate migration must be able to walk through. The
    gate stays in force for every other command.
    """
    return _resolve_aos_dir(args) / utils.DB_FILENAME


def cmd_migrate_status(args) -> int:
    from . import migrations

    report = migrations.status(_migrate_db_path(args))
    if args.json:
        _print_json(report)
        return 0
    print(f"database:        {report['db_path']}")
    print(f"schema version:  {report['current_version']}")
    print(f"build supports:  {report['latest_version']}")
    if report["pending"]:
        print(f"pending:         yes ({len(report['plan'])} migration(s))")
        print("Run: python aos.py migrate plan")
    else:
        print("pending:         no — the database is up to date")
    return 0


def cmd_migrate_plan(args) -> int:
    from . import migrations

    report = migrations.plan_report(_migrate_db_path(args), target=args.target)
    if args.json:
        _print_json(report)
        return 0
    print(f"database:        {report['db_path']}")
    print(f"schema version:  {report['current_version']}")
    print(f"target version:  {report['target_version']}")
    if not report["steps"]:
        print("No migrations pending. Nothing would run.")
        return 0
    print(f"{len(report['steps'])} migration(s) would run, in order:")
    for step in report["steps"]:
        print(f"  {step['from']} → {step['to']}  {step['migration_id']}")
    print(
        "A verified snapshot is taken before the first change. "
        "Run: python aos.py migrate apply"
    )
    return 0


def cmd_migrate_apply(args) -> int:
    from . import migrations

    aos_dir = _resolve_aos_dir(args)
    try:
        result = migrations.apply_migrations(aos_dir, target=args.target)
    except migrations.MigrationStepError as exc:
        # Partial advancement is the one failure a human must be told how to
        # get out of; everything else left the database untouched.
        lines = [str(exc)]
        if exc.applied:
            last = exc.applied[-1]
            lines.append(
                f"The database is PARTIALLY ADVANCED: {len(exc.applied)} "
                f"migration(s) committed, and it is now at version "
                f"{last['to']}. This is a real state, not a broken one — "
                "`migrate status` reports it, and a corrected retry resumes "
                "from there without replaying committed steps."
            )
        if exc.snapshot is not None:
            lines.append(
                migrations.restore_hint(
                    exc.snapshot, aos_dir / utils.DB_FILENAME
                )
            )
        raise AosError("\n".join(lines))
    if not result["migrated"]:
        print(
            f"No migrations pending (schema version "
            f"{result['current_version']}); nothing to do."
        )
        print("No snapshot was taken and no event was written.")
        return 0
    print(f"Snapshot: {result['snapshot']}")
    for step in result["applied"]:
        print(f"  applied {step['from']} → {step['to']}  {step['migration_id']}")
    print(f"Schema version is now {result['current_version']}.")
    return 0


def cmd_sync(args) -> int:
    export_to = getattr(args, "export_to", None)
    if getattr(args, "dry_run", False) and export_to is None:
        raise AosError("--dry-run requires --export-to. See: python aos.py --help")
    with _ledger(args) as (aos_dir, conn):
        if export_to is not None:
            from . import mirror_export

            # Refusals fire before any local work; stale destination state
            # refuses in dry-run too (no plan against an ambiguous
            # authoritative generation).
            target = mirror_export.check_destination(aos_dir, export_to)
        total, written = obsidian.sync_vault(conn, aos_dir)
        print(f"Synced {total} notes ({written} written, {total - written} unchanged).")
        if export_to is None:
            return 0
        plan = mirror_export.compute_plan(aos_dir, target)
        if args.dry_run:
            _print_export_dry_run(plan)
        else:
            _apply_export(plan)
    return 0


def _export_byte_totals(plan) -> tuple[int, int, int]:
    return (
        sum(size for _, size in plan.creates),
        sum(size for _, size in plan.updates),
        sum(size for _, size in plan.deletes),
    )


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _print_export_dry_run(plan) -> None:
    print(f"Export destination: {plan.target.dest_aos}")
    if plan.is_noop:
        print(
            f"Dry run: destination already matches the source "
            f"({plan.note_total} notes); nothing to do."
        )
        return
    # Deterministic order: file operations by verb (each list is sorted
    # by relpath), then directory operations (sorted). A directory-only
    # plan is non-noop, so it always shows its create-dir/delete-dir
    # lines — never zero visible operations.
    for verb, entries in (
        ("create", plan.creates),
        ("update", plan.updates),
        ("delete", plan.deletes),
    ):
        for rel, size in entries:
            print(f"{verb} {rel} ({size} bytes)")
    for rel in plan.dir_creates:
        print(f"create-dir {rel}/")
    for rel in plan.dir_deletes:
        print(f"delete-dir {rel}/")
    create_bytes, update_bytes, delete_bytes = _export_byte_totals(plan)
    print(
        f"Dry run: {_count(len(plan.creates), 'file create')} "
        f"({create_bytes} bytes), "
        f"{_count(len(plan.updates), 'file update')} "
        f"({update_bytes} bytes), "
        f"{_count(len(plan.deletes), 'file delete')} "
        f"({delete_bytes} bytes), "
        f"{_count(len(plan.dir_creates), 'directory create')}, "
        f"{_count(len(plan.dir_deletes), 'directory delete')}, "
        f"{_count(len(plan.unchanged), 'unchanged file')}. "
        "Nothing was written."
    )


def _apply_export(plan) -> None:
    from . import mirror_export

    if plan.is_noop:
        print(
            f"Destination {plan.target.dest_aos} already matches the source "
            f"({plan.note_total} notes); nothing written."
        )
        return
    result = mirror_export.apply_plan(plan)
    print(
        f"Exported to {plan.target.dest_aos}: "
        f"{result.created_files} created, "
        f"{result.updated_files} updated, "
        f"{result.deleted_files} deleted, "
        f"{result.unchanged_files} unchanged "
        f"({result.unchanged_hardlinked_files} hardlinked, "
        f"{result.unchanged_fallback_copied_files} copied) "
        f"({result.payload_bytes_written} bytes written)."
    )
    if result.cleanup_warning is not None:
        print(result.cleanup_warning, file=sys.stderr)


def _hooks_settings_path(args) -> Path:
    from . import hooks

    if args.settings is not None:
        # expanduser only — no resolve(): a symlinked settings path must
        # still LOOK like a symlink to the installer's refusal check.
        return Path(args.settings).expanduser()
    return hooks.default_settings_path()


def _hooks_mode(args) -> bool:
    """True = apply. Dry-run is the default posture; passing both is an
    error rather than a guess."""
    if args.dry_run and args.apply:
        raise AosError("Pass --dry-run or --apply, not both.")
    return args.apply


def _print_settings_plan(plan, verb: str) -> None:
    if not plan.changed:
        print(f"Nothing to {verb}: {plan.path} already matches; no changes.")
        return
    for line in plan.diff_lines():
        print(line, end="" if line.endswith("\n") else "\n")
    print(f"Dry run: nothing was changed. Re-run with --apply to {verb}.")


def _confirm_settings_rewrite(path: Path) -> None:
    try:
        reply = input(
            f"Rewrite {path}? A timestamped backup is written first. "
            "Type 'yes' to proceed: "
        )
    except EOFError:
        reply = ""
    if reply.strip() != "yes":
        raise AosError("Not confirmed; nothing was changed.")


def _apply_settings_plan(plan, done_message: str) -> int:
    from . import hooks

    for line in plan.diff_lines():
        print(line, end="" if line.endswith("\n") else "\n")
    _confirm_settings_rewrite(plan.path)
    backup = hooks.apply_plan(plan)
    if backup is not None:
        print(f"backup: {backup}")
        print(f"Restore anytime: cp '{backup}' '{plan.path}'")
    print(done_message)
    return 0


def cmd_hooks_install(args) -> int:
    from . import hooks

    apply = _hooks_mode(args)
    path = _hooks_settings_path(args)
    plan = hooks.plan_install(path)
    if not apply:
        _print_settings_plan(plan, "install")
        return 0
    if not plan.changed:
        print(f"AOS hooks already installed in {path}; nothing to do.")
        return 0
    return _apply_settings_plan(
        plan,
        f"Installed AOS Stop/SessionEnd hooks into {path} "
        f"(version {hooks.HOOK_PROTOCOL_VERSION}, "
        f"digest {hooks.install_digest()[:16]}). "
        "Sessions publish write-back dropfiles; ingest stays manual.",
    )


def cmd_hooks_status(args) -> int:
    from . import hooks

    path = _hooks_settings_path(args)
    info = hooks.status(path)
    print(f"settings: {info['settings']}")
    print(f"state: {info['state']}")
    if info["state"] == "installed":
        print(f"version: {info['version']}")
        print(f"digest: {info['digest']}")
    elif info["state"] == "drifted":
        print(
            "AOS-owned hook entries differ from what this checkout "
            "installs. Preview the fix: python aos.py hooks install --dry-run"
        )
    return 0


def cmd_hooks_uninstall(args) -> int:
    from . import hooks

    apply = _hooks_mode(args)
    path = _hooks_settings_path(args)
    plan = hooks.plan_uninstall(path)
    if not apply:
        _print_settings_plan(plan, "uninstall")
        return 0
    if not plan.changed:
        print(f"No AOS-owned hooks in {path}; nothing to do.")
        return 0
    return _apply_settings_plan(
        plan,
        f"Removed the AOS-owned Stop/SessionEnd hooks from {path}. "
        "Unrelated settings and hooks were preserved.",
    )


def cmd_doctor(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        from . import doctor

        checks = doctor.run_checks(conn, aos_dir)
    failed = [c for c in checks if not c.ok and not c.warn_only]
    for check in checks:
        if check.ok:
            marker = "PASS"
        elif check.warn_only:
            marker = "WARN"
        else:
            marker = "FAIL"
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
    p_task_add.add_argument("--spec", default=None)
    p_task_add.add_argument("--priority", type=int, default=2)
    p_task_add.set_defaults(func=cmd_task_add)
    p_task_assign = task_sub.add_parser(
        "assign", help="assign a task to a project"
    )
    p_task_assign.add_argument("id")
    p_task_assign.add_argument("-p", "--project", required=True)
    p_task_assign.set_defaults(func=cmd_task_assign)
    p_task_edit = task_sub.add_parser("edit", help="edit an open task's fields")
    p_task_edit.add_argument("id")
    p_task_edit.add_argument("--title", default=None)
    p_task_edit.add_argument("--accept", default=None)
    p_task_edit.add_argument("--spec", default=None)
    p_task_edit.add_argument("--kind", default=None)
    p_task_edit.add_argument("--priority", type=int, default=None)
    p_task_edit.set_defaults(func=cmd_task_edit)
    p_task_status = task_sub.add_parser(
        "status", help="change task status (safe transitions only)"
    )
    p_task_status.add_argument("id")
    p_task_status.add_argument("status")
    p_task_status.set_defaults(func=cmd_task_status)
    p_task_list = task_sub.add_parser("list", help="list tasks")
    p_task_list.add_argument("--project", default=None)
    p_task_list.add_argument("--status", default=None)
    p_task_list.add_argument("--kind", default=None)
    p_task_list.add_argument(
        "--missing-evidence", dest="missing_evidence", action="store_true"
    )
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
    p_evidence_git = evidence_sub.add_parser(
        "git", help="attach verified commit evidence via read-only git"
    )
    p_evidence_git.add_argument("id")
    p_evidence_git.add_argument("commit")
    p_evidence_git.add_argument("--repo", default=None)
    p_evidence_git.add_argument("--claim", default=None)
    p_evidence_git.set_defaults(func=cmd_evidence_git)

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

    p_agent = sub.add_parser(
        "agent", help="agent registry (records only; never executes agents)"
    )
    agent_sub = p_agent.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )
    p_agent_add = agent_sub.add_parser("add", help="register an agent")
    p_agent_add.add_argument("name")
    p_agent_add.add_argument("--kind", default="generic")
    p_agent_add.add_argument("--notes", default=None)
    p_agent_add.add_argument(
        "--capability", action="append", default=None, metavar="TEXT"
    )
    p_agent_add.set_defaults(func=cmd_agent_add)
    p_agent_update = agent_sub.add_parser(
        "update", help="update a registered agent"
    )
    p_agent_update.add_argument("name")
    p_agent_update.add_argument("--notes", default=None)
    p_agent_update.add_argument(
        "--capability", action="append", default=None, metavar="TEXT"
    )
    p_agent_update.set_defaults(func=cmd_agent_update)
    p_agent_list = agent_sub.add_parser("list", help="list registered agents")
    p_agent_list.add_argument("--json", action="store_true")
    p_agent_list.set_defaults(func=cmd_agent_list)
    p_agent_show = agent_sub.add_parser("show", help="show one agent")
    p_agent_show.add_argument("name")
    p_agent_show.add_argument("--json", action="store_true")
    p_agent_show.set_defaults(func=cmd_agent_show)

    p_ingest = sub.add_parser("ingest", help="ingest agent write-back artifacts")
    ingest_sub = p_ingest.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )
    p_ingest_dropfile = ingest_sub.add_parser(
        "dropfile", help="ingest an agent dropfile (evidence + open questions)"
    )
    p_ingest_dropfile.add_argument("path")
    p_ingest_dropfile.set_defaults(func=cmd_ingest_dropfile)

    p_done = sub.add_parser("done", help="close a task (requires evidence)")
    p_done.add_argument("id")
    p_done.add_argument(
        "--no-evidence", action="store_true",
        help="close without evidence (requires --reason; journaled)",
    )
    p_done.add_argument(
        "--reason", default=None, metavar="TEXT",
        help="justification for --no-evidence, stored in the override event",
    )
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
    p_review_weekly = review_sub.add_parser(
        "weekly", help="build the review note for an ISO week"
    )
    p_review_weekly.add_argument(
        "--date", default=None, metavar="YYYY-MM-DD",
        help="any date inside the week (default: today, UTC)",
    )
    p_review_weekly.set_defaults(func=cmd_review_weekly)
    p_review_project = review_sub.add_parser(
        "project", help="build the review note for one project"
    )
    p_review_project.add_argument("slug")
    p_review_project.add_argument(
        "--date", default=None, metavar="YYYY-MM-DD",
        help="review date (default: today, UTC)",
    )
    p_review_project.set_defaults(func=cmd_review_project)

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

    p_backup = sub.add_parser(
        "backup", help="verifiable backups: create, verify, restore "
        "(drill in RECOVERY.md)"
    )
    backup_sub = p_backup.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )
    p_backup_create = backup_sub.add_parser(
        "create",
        help="write a manifest-carrying backup via the SQLite backup API",
    )
    p_backup_create.set_defaults(func=cmd_backup_create)
    p_backup_verify = backup_sub.add_parser(
        "verify",
        help="verify a backup against its manifest and PRAGMA "
        "integrity_check (works without a workspace)",
    )
    p_backup_verify.add_argument("path")
    p_backup_verify.set_defaults(func=cmd_backup_verify)
    p_backup_restore = backup_sub.add_parser(
        "restore",
        help="copy a verified backup to a NEW database path "
        "(never overwrites; no overwrite flag)",
    )
    p_backup_restore.add_argument("path")
    p_backup_restore.add_argument(
        "--to", required=True, metavar="NEW_DB_PATH",
        help="target database file path; must not exist yet",
    )
    p_backup_restore.set_defaults(func=cmd_backup_restore)

    p_migrate = sub.add_parser(
        "migrate",
        help="schema migrations (U-M1): status / plan / apply. Nothing else "
        "ever migrates — normal commands refuse an unsupported version "
        "rather than silently changing your database.",
    )
    migrate_sub = p_migrate.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )

    p_migrate_status = migrate_sub.add_parser(
        "status",
        help="report current/supported schema version and whether "
        "migrations are pending (read-only)",
    )
    p_migrate_status.add_argument("--json", action="store_true")
    p_migrate_status.set_defaults(func=cmd_migrate_status)

    p_migrate_plan = migrate_sub.add_parser(
        "plan",
        help="print the ordered version transitions that would run "
        "(read-only; writes nothing)",
    )
    p_migrate_plan.add_argument(
        "--target", type=int, default=None, metavar="N",
        help="stop at version N (must be supported and not below current)",
    )
    p_migrate_plan.add_argument("--json", action="store_true")
    p_migrate_plan.set_defaults(func=cmd_migrate_plan)

    p_migrate_apply = migrate_sub.add_parser(
        "apply",
        help="run pending migrations, taking a verified snapshot before the "
        "first change (no-op when nothing is pending)",
    )
    p_migrate_apply.add_argument(
        "--target", type=int, default=None, metavar="N",
        help="stop at version N (must be supported and not below current)",
    )
    p_migrate_apply.set_defaults(func=cmd_migrate_apply)

    p_sync = sub.add_parser("sync", help="regenerate the Obsidian mirror")
    p_sync.add_argument(
        "--export-to", metavar="PATH", default=None,
        help="one-way export of the generated AOS/ mirror to PATH/AOS "
        "(PATH is the Obsidian vault root; destination edits are never "
        "ingested)",
    )
    p_sync.add_argument(
        "--dry-run", action="store_true",
        help="with --export-to: preview create/update/delete and byte "
        "totals without touching the destination (the local mirror is "
        "still regenerated — that is what sync means)",
    )
    p_sync.set_defaults(func=cmd_sync)

    p_log = sub.add_parser("log", help="event journal")
    p_log.add_argument("task_id", nargs="?", default=None)
    p_log.add_argument("--today", action="store_true")
    p_log.add_argument("--json", action="store_true")
    p_log.set_defaults(func=cmd_log)

    p_doctor = sub.add_parser("doctor", help="health checks")
    p_doctor.set_defaults(func=cmd_doctor)

    p_hooks = sub.add_parser(
        "hooks",
        help="Claude Code session hooks (U-H1): previewable, reversible "
        "install into Claude settings",
    )
    hooks_sub = p_hooks.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )

    def _hooks_common(p) -> None:
        p.add_argument(
            "--settings", default=None, metavar="PATH",
            help="Claude settings file (default: ~/.claude/settings.json)",
        )

    p_hooks_install = hooks_sub.add_parser(
        "install",
        help="merge the AOS Stop/SessionEnd handlers into Claude settings "
        "(dry-run unless --apply)",
    )
    p_hooks_install.add_argument("--dry-run", action="store_true")
    p_hooks_install.add_argument(
        "--apply", action="store_true",
        help="write the change (asks for confirmation; backs up first)",
    )
    _hooks_common(p_hooks_install)
    p_hooks_install.set_defaults(func=cmd_hooks_install)

    p_hooks_status = hooks_sub.add_parser(
        "status", help="report absent / installed (version, digest) / drifted"
    )
    _hooks_common(p_hooks_status)
    p_hooks_status.set_defaults(func=cmd_hooks_status)

    p_hooks_uninstall = hooks_sub.add_parser(
        "uninstall",
        help="remove only the AOS-owned handlers (dry-run unless --apply)",
    )
    p_hooks_uninstall.add_argument("--dry-run", action="store_true")
    p_hooks_uninstall.add_argument(
        "--apply", action="store_true",
        help="write the change (asks for confirmation; backs up first)",
    )
    _hooks_common(p_hooks_uninstall)
    p_hooks_uninstall.set_defaults(func=cmd_hooks_uninstall)

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
