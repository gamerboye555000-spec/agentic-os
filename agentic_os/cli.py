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

from . import db, ids, obsidian, ops, power, utils
from .models import (
    AGENT_CLASSES,
    MEMORY_EDGE_RELATIONS,
    MEMORY_SENSITIVITIES,
    MEMORY_SENSITIVITY_DEFAULT,
    MEMORY_SENSITIVITY_RESTRICTED,
    MEMORY_SOURCE_KINDS,
    MEMORY_SOURCE_RELATIONS,
    MEMORY_STATUSES,
)
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
    # U-E2 eco: the one implicit, optional derived refresh in the baseline —
    # re-healing the mirror on an already-initialized workspace, while init
    # reports "nothing to do". Eco defers it and says so; `sync` regenerates
    # it on demand. A fresh workspace always heals (see ops.init_workspace).
    eco = power.mode_of(args) == power.ECO
    aos_dir, created = ops.init_workspace(root, refresh_mirror=not eco)
    if created:
        print(f"Initialized Agentic OS workspace at {aos_dir}")
    else:
        print(
            f"Already initialized at {aos_dir} "
            f"(schema_version {db.SCHEMA_VERSION}); nothing to do."
        )
        if eco:
            print(
                "eco: deferred the idempotent Obsidian mirror refresh. "
                "Regenerate it anytime: python aos.py sync"
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


def cmd_agent_create(args) -> int:
    from . import passports

    with _ledger(args) as (aos_dir, conn):
        agent, _passport = passports.create_agent(
            conn,
            name=args.name,
            agent_class=args.agent_class,
            project_slug=args.project,
            role=args.role,
            mission=args.mission,
            fragment_path=args.from_file,
        )
        if args.json:
            _print_json({"agent": passports.agent_public(conn, agent)})
            return 0
        print(
            f"Added agent {agent.name} ({agent.agent_class}, "
            f"{agent.lifecycle}) — publish: python aos.py agent passport "
            f"publish {agent.name}"
        )
    return 0


def cmd_agent_import(args) -> int:
    from . import passports

    with _ledger(args) as (aos_dir, conn):
        agent, _passport = passports.import_agent(conn, args.file)
        if args.json:
            _print_json({"agent": passports.agent_public(conn, agent)})
            return 0
        print(
            f"Imported agent {agent.name} ({agent.agent_class}, "
            f"{agent.lifecycle}) — publish: python aos.py agent passport "
            f"publish {agent.name}"
        )
    return 0


def cmd_agent_list(args) -> int:
    from . import passports

    with _ledger(args) as (aos_dir, conn):
        agents = passports.list_agents(
            conn, include_all=args.all, project_slug=args.project
        )
        if args.json:
            _print_json({"agents": agents})
            return 0
        if not agents:
            print("(no agents)")
            return 0
        for agent in agents:
            version = (
                f"v{agent['current_passport_version']}"
                if agent["current_passport_version"]
                else "-"
            )
            scope = (
                f"project:{agent['project']}"
                if agent["project"]
                else agent["scope"]
            )
            print(
                f"{agent['name']:<16} {agent['agent_class']:<10} "
                f"{scope:<16} {agent['lifecycle']:<10} {version:<6} "
                f"{agent['origin']}"
            )
    return 0


def cmd_agent_show(args) -> int:
    from . import passports
    from .models import hash_prefix

    with _ledger(args) as (aos_dir, conn):
        agent = passports.get_agent(conn, args.name)
        if agent is None:
            raise AosError(
                f"No agent '{args.name}'. Run: python aos.py agent list"
            )
        public = passports.agent_public(conn, agent)
        if args.json:
            _print_json({"agent": public})
            return 0
        print(f"{public['name']}  ({public['agent_class']}, {public['lifecycle']})")
        scope = public["scope"] + (
            f" ({public['project']})" if public["project"] else ""
        )
        print(f"scope:        {scope}")
        print(f"origin:       {public['origin']}")
        print(f"owner:        {public['owner']}")
        print(f"protected:    {'yes' if public['protected'] else 'no'}")
        version = public["current_passport_version"]
        print(f"passport:     {f'v{version}' if version else '(none published)'}")
        for passport in public["passports"]:
            marker = " *" if passport["version"] == version else ""
            print(
                f"  v{passport['version']}  {passport['status']:<10} "
                f"{passport['created_at']}  "
                f"{hash_prefix(passport['content_sha256'])}…{marker}"
            )
        print(f"created:      {public['created_at']}")
        print(f"updated:      {public['updated_at']}")
        print(f"integrity:    {public['integrity']}")
        print(f"hash:         {hash_prefix(public['content_sha256'])}…")
        legacy = public.get("legacy")
        if legacy:
            print("legacy (inert v3 history):")
            print(f"  kind:         {_dash(legacy['kind'])}")
            print(
                "  capabilities: "
                + (", ".join(legacy["capabilities"]) or "-")
            )
            print(f"  notes:        {_dash(legacy['notes'])}")
            print(f"  invoke hint:  {_dash(legacy['invoke_hint'])}")
            print(f"  trust level:  {_dash(legacy['trust_level'])}")
    return 0


def cmd_agent_export(args) -> int:
    from . import passports

    with _ledger(args) as (aos_dir, conn):
        document = passports.export_document(conn, args.name, args.version)
        # The stored canonical bytes plus one trailing newline — the
        # `protocol show` precedent: deterministic, byte-stable forever.
        sys.stdout.write(document + "\n")
    return 0


def cmd_agent_passport_publish(args) -> int:
    from . import passports

    with _ledger(args) as (aos_dir, conn):
        agent, passport = passports.publish_passport(
            conn, name=args.name, path=args.file
        )
        if args.json:
            _print_json({"agent": passports.agent_public(conn, agent)})
            return 0
        print(
            f"Published passport v{passport.version} for {agent.name} "
            f"({agent.lifecycle})"
        )
    return 0


def cmd_agent_passport_history(args) -> int:
    from . import passports
    from .models import hash_prefix

    with _ledger(args) as (aos_dir, conn):
        agent = passports.get_agent(conn, args.name)
        if agent is None:
            raise AosError(
                f"No agent '{args.name}'. Run: python aos.py agent list"
            )
        history = passports.list_passports(conn, agent.id)
        if args.json:
            _print_json(
                {
                    "agent": agent.name,
                    "current_passport_version": agent.current_passport_version,
                    "passports": [
                        {
                            "version": passport.version,
                            "status": passport.status,
                            "created_at": passport.created_at,
                            "published_at": passport.published_at,
                            "content_sha256": passport.content_sha256,
                            "integrity": passports.passport_integrity(passport),
                        }
                        for passport in history
                    ],
                }
            )
            return 0
        if not history:
            print("(no passports)")
            return 0
        for passport in history:
            marker = (
                " *"
                if passport.version == agent.current_passport_version
                else ""
            )
            print(
                f"v{passport.version}  {passport.status:<10} "
                f"created {passport.created_at}  published "
                f"{passport.published_at or '-':<20}  "
                f"{hash_prefix(passport.content_sha256)}…{marker}"
            )
    return 0


def cmd_agent_lifecycle(args) -> int:
    from . import passports

    with _ledger(args) as (aos_dir, conn):
        before = passports.get_agent(conn, args.name)
        from_state = before.lifecycle if before else "?"
        agent = passports.transition_lifecycle(
            conn, name=args.name, verb=args.subcommand
        )
        print(f"{agent.name}: {from_state} → {agent.lifecycle}")
    return 0


def cmd_agent_discard(args) -> int:
    from . import passports

    with _ledger(args) as (aos_dir, conn):
        passports.discard_agent(conn, name=args.name)
        print(f"Discarded draft agent {args.name}")
    return 0


# ---------------------------------------------------------------------------
# U-A2 built-in specialist catalog — five read-only leaves this wave.
#
# Every one of these is inert: `list`/`show`/`verify` parse bytes and compare
# them to the checked-in manifest (no SQLite, no workspace, no event —
# usable in recovery); `status`/`plan` additionally open the ledger
# READ-ONLY to report installed state. None of the five writes a row.
# `agent catalog install` does not exist in this build.

def cmd_agent_catalog_list(args) -> int:
    from . import catalog

    cat = catalog.catalog()
    if args.json:
        _print_json(
            {
                "catalog": {
                    "catalog_version": cat.catalog_version,
                    "manifest_sha256": cat.manifest_sha256,
                    "entries": [catalog.entry_public(e) for e in cat.entries],
                }
            }
        )
        return 0
    name_width = max(len(e.agent) for e in cat.entries)
    category_width = max(len(e.category) for e in cat.entries)
    for e in cat.entries:
        print(
            f"{e.agent:<{name_width}}  {e.category:<{category_width}}  "
            f"{e.maturity:<11}  v{e.latest.passport_version}"
        )
    print(f"{len(cat.entries)} entry(ies), catalog v{cat.catalog_version}")
    return 0


def cmd_agent_catalog_show(args) -> int:
    from . import catalog, passports, protocols

    modes = [
        name
        for name, flag in (
            ("--document", args.document),
            ("--fragment", args.fragment),
            ("--json", args.json),
        )
        if flag
    ]
    if len(modes) > 1:
        raise AosError(
            "Pass at most one of --document, --fragment, --json; got "
            + ", ".join(modes) + "."
        )

    entry = catalog.catalog().get(args.name)
    if entry is None:
        raise AosError(
            f"No catalog entry {args.name!r}. Run: python aos.py agent catalog list"
        )
    document, text = catalog.load_document(entry, entry.latest)

    if args.document:
        sys.stdout.write(text)
        return 0

    if args.fragment:
        fragment = {
            key: value
            for key, value in document.items()
            if key not in passports._FRAGMENT_FORBIDDEN
        }
        sys.stdout.write(protocols.serialize_canonical_file_bytes(fragment).decode("utf-8"))
        return 0

    if args.json:
        _print_json({"entry": catalog.entry_public(entry), "document": document})
        return 0

    evidence = document["evidence_expectations"]
    print(f"{entry.agent}  ({entry.category}, {entry.maturity})")
    print(f"role:                {document['role']}")
    print(f"escalation:          {document['escalation']}")
    print(
        "evidence:            "
        + ", ".join(evidence["evidence_kinds"])
        + f" (min {evidence['min_evidence_count']})"
    )
    print("task families:       " + (", ".join(document.get("task_families", ())) or "-"))
    print(
        "skill requirements:  "
        + (", ".join(document.get("skill_requirements", ())) or "-")
    )
    print(
        "tool requirements:   "
        + (", ".join(document.get("tool_requirements", ())) or "-")
    )
    for limitation in document.get("limitations", ()):
        print(f"limitation:          {limitation}")
    print(f"passport:            v{entry.latest.passport_version}")
    print(f"digest:              {entry.latest.document_sha256}")
    return 0


def cmd_agent_catalog_verify(args) -> int:
    from . import catalog

    problems = catalog.verify()
    if args.json:
        _print_json({"problems": problems})
        return 1 if problems else 0
    if not problems:
        cat = catalog.catalog()
        total_versions = sum(len(e.versions) for e in cat.entries)
        print(f"{len(cat.entries)} entry(ies), {total_versions} passport(s): OK")
        return 0
    for problem in problems:
        print(problem, file=sys.stderr)
    return 1


def cmd_agent_catalog_status(args) -> int:
    from . import catalog

    with _ledger(args) as (aos_dir, conn):
        rows = catalog.status(conn)
        if args.json:
            _print_json({"status": rows})
            return 0
        width = max(len(r["agent"]) for r in rows)
        for r in rows:
            installed = f"v{r['installed_version']}" if r["installed_version"] else "-"
            available = f"v{r['available_version']}"
            detail = f"  ({r['detail']})" if r["detail"] else ""
            print(
                f"{r['agent']:<{width}}  {r['state']:<13}  {installed:<6} "
                f"{available:<6}{detail}"
            )
        counts: dict[str, int] = {}
        for r in rows:
            counts[r["state"]] = counts.get(r["state"], 0) + 1
        summary = ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))
        print(f"{len(rows)} entry(ies): {summary}")
    return 0


def cmd_agent_catalog_plan(args) -> int:
    from . import catalog

    if args.all and args.names:
        raise AosError("Pass either NAME(s) or --all, not both.")
    if not args.all and not args.names:
        raise AosError("Pass at least one NAME, or --all.")
    names = None if args.all else list(args.names)

    with _ledger(args) as (aos_dir, conn):
        actions = catalog.plan(conn, names)
        if args.json:
            _print_json({"plan": actions})
            return 0
        width = max(len(a["agent"]) for a in actions)
        for a in actions:
            detail = f"  ({a['detail']})" if a["detail"] else ""
            print(f"{a['agent']:<{width}}  {a['action']:<8}{detail}")
    return 0


def cmd_agent_catalog_install(args) -> int:
    from . import catalog

    if args.all and args.names:
        raise AosError("Pass either NAME(s) or --all, not both.")
    if not args.all and not args.names:
        raise AosError("Pass at least one NAME, or --all.")
    names = None if args.all else list(args.names)

    with _ledger(args) as (aos_dir, conn):
        result = catalog.install(conn, names)
        if args.json:
            _print_json({"result": result})
            return 0
        if not result["changed"]:
            print(
                f"Nothing to do: {result['unchanged']} entry(ies) already "
                f"installed at catalog v{result['catalog_version']}."
            )
            return 0
        print(
            f"Installed {result['installed']} agent(s), upgraded "
            f"{result['upgraded']}, unchanged {result['unchanged']} "
            f"(catalog v{result['catalog_version']})."
        )
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
    evidence_ids = [
        ids.parse_id(value, "evidence") for value in (args.evidence or [])
    ]
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
            pin=args.pin,
            evidence_ids=evidence_ids,
            sensitivity=args.sensitivity,
        )
        print(ids.render_id("memory", item.id))
    return 0


def _memory_state(item: dict) -> str:
    """The one-word lifecycle summary the list has always shown, now leading
    with the curation status it is derived from."""
    if item["superseded_by"]:
        return f"{item['status']}→{item['superseded_by']}"
    if item["status"] != "live":
        return f"{item['status']} {_dash(item['valid_until'])}"
    if not item["live"]:
        # `live` is now the full eligibility answer, so a live claim can be
        # ineligible for two different reasons. Say which: a restricted claim
        # reported as `live·expired` would send its owner looking for an
        # expiry date that does not exist (M3.2).
        if item["sensitivity"] == MEMORY_SENSITIVITY_RESTRICTED:
            return "live·restricted"
        return f"live·expired {_dash(item['valid_until'])}"
    return "live"


def cmd_memory_list(args) -> int:
    pinned = True if args.pinned else (False if args.unpinned else None)
    with _ledger(args) as (aos_dir, conn):
        items = ops.list_memory(
            conn,
            scope=args.scope,
            project_slug=args.project,
            status=args.status,
            pinned=pinned,
        )
        if args.json:
            _print_json({"memories": items})
            return 0
        if not items:
            print("(no memory)")
            return 0
        for item in items:
            # ops.memory_public has already reduced a restricted claim to
            # metadata — key, value and source are the placeholder by the time
            # they reach here, so this line cannot print one by accident.
            value_one_line = " ".join(item["value_md"].split())
            print(
                f"{item['id']:<8} {'PIN' if item['pinned'] else '   '} "
                f"{item['scope']:<8} "
                f"{_dash(item['project']):<16} {item['kind']:<11} "
                f"[{item['confidence']}] {item['sensitivity']:<13} "
                f"{_memory_state(item):<26} "
                f"{item['key']}: {value_one_line}"
            )
    return 0


def cmd_memory_show(args) -> int:
    memory_id = ids.parse_id(args.id, "memory")
    with _ledger(args) as (aos_dir, conn):
        doc = ops.show_memory(conn, memory_id)
        if args.json:
            _print_json(doc)
            return 0
        print(f"{doc['id']} {doc['key']}")
        print(f"  status:     {doc['status']}")
        print(f"  pinned:     {'yes' if doc['pinned'] else 'no'}")
        print(f"  sensitive:  {doc['sensitivity']}")
        print(f"  retrieved:  {'yes' if doc['live'] else 'no'} (normal packs)")
        print(f"  scope:      {doc['scope']}")
        print(f"  project:    {_dash(doc['project'])}")
        print(f"  kind:       {doc['kind']}")
        print(f"  confidence: {doc['confidence']}")
        print(f"  source:     {doc['source']}")
        print(f"  valid:      {doc['valid_from']} → {_dash(doc['valid_until'])}")
        print(f"  superseded: {_dash(doc['superseded_by'])}")
        print(f"  updated:    {doc['updated_at']}")
        # Evidence is named by id only: `memory show` never reads an evidence
        # row's claim or ref, and never opens a file it points at (M2.8).
        print(f"  evidence:   {', '.join(doc['evidence']) or '-'}")
        print(f"  hash:       {doc['content_sha256']} ({doc['integrity']})")
        print()
        print(doc["value_md"].rstrip())
    return 0


def cmd_memory_pin(args) -> int:
    memory_id = ids.parse_id(args.id, "memory")
    pinned = args.pinned_state
    with _ledger(args) as (aos_dir, conn):
        item, changed = ops.set_memory_pin(
            conn, memory_id=memory_id, pinned=pinned
        )
        hid = ids.render_id("memory", item.id)
        word = "pinned" if pinned else "unpinned"
        if changed:
            print(f"{hid} {word}")
        else:
            print(f"{hid} is already {word}; nothing changed.")
    return 0


def cmd_memory_link_evidence(args) -> int:
    memory_id = ids.parse_id(args.id, "memory")
    evidence_id = ids.parse_id(args.evidence_id, "evidence")
    with _ledger(args) as (aos_dir, conn):
        item, changed = ops.link_memory_evidence(
            conn, memory_id=memory_id, evidence_id=evidence_id
        )
        hid = ids.render_id("memory", item.id)
        ehid = ids.render_id("evidence", evidence_id)
        if changed:
            count = len(ops.memory_evidence_ids(conn, item.id))
            print(f"{hid} ← {ehid} ({count} evidence link(s))")
        else:
            print(f"{hid} is already linked to {ehid}; nothing changed.")
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


# ---------------------------------------------------------------------------
# U-M3 memory graph (contract M3.8)
#
# Every command below prints ids, closed enum names, timestamps, counts and
# bounded hash prefixes. None prints a claim key or value, a source locator or
# provenance, or an evidence ref — and none opens, fetches or executes
# anything a source points at (D-v0.3.47).

def cmd_memory_classify(args) -> int:
    memory_id = ids.parse_id(args.id, "memory")
    with _ledger(args) as (aos_dir, conn):
        item, changed = ops.classify_memory(
            conn, memory_id=memory_id, level=args.level
        )
        hid = ids.render_id("memory", item.id)
        if changed:
            print(f"{hid} classified {item.sensitivity}")
        else:
            print(
                f"{hid} is already {item.sensitivity}; nothing changed."
            )
    return 0


def cmd_memory_source_add(args) -> int:
    evidence_id = (
        ids.parse_id(args.evidence, "evidence")
        if args.evidence is not None
        else None
    )
    with _ledger(args) as (aos_dir, conn):
        item = ops.add_memory_source(
            conn,
            kind=args.kind,
            project_slug=args.project,
            evidence_id=evidence_id,
            locator=args.locator,
            provenance=args.provenance,
            sensitivity=args.sensitivity,
            observed_at=args.observed_at,
            valid_from=args.valid_from,
            valid_until=args.valid_until,
        )
        print(ids.render_id("memory_source", item.id))
    return 0


def _source_line(doc: dict) -> str:
    return (
        f"{doc['id']:<9} {doc['kind']:<9} {_dash(doc['project']):<16} "
        f"{doc['sensitivity']:<13} {'active' if doc['active'] else 'expired':<8} "
        f"{doc['observed_at']:<21} {doc['link_count']} link(s)  "
        f"{doc['hash_prefix']}…"
    )


def cmd_memory_source_list(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        docs = ops.list_memory_sources(
            conn,
            project_slug=args.project,
            kind=args.kind,
            active_only=args.active_only,
        )
        if args.json:
            _print_json({"sources": docs})
            return 0
        if not docs:
            print("(no memory sources)")
            return 0
        for doc in docs:
            print(_source_line(doc))
    return 0


def cmd_memory_source_show(args) -> int:
    source_id = ids.parse_id(args.id, "memory_source")
    with _ledger(args) as (aos_dir, conn):
        doc = ops.show_memory_source(conn, source_id)
        if args.json:
            _print_json(doc)
            return 0
        print(f"{doc['id']} {doc['kind']}")
        print(f"  project:     {_dash(doc['project'])}")
        print(f"  sensitivity: {doc['sensitivity']}")
        # The evidence ROW is named. Its claim, ref and body are not read, and
        # neither is anything it points at (M3.8).
        print(f"  evidence:    {_dash(doc['evidence'])}")
        print(f"  observed:    {doc['observed_at']}")
        print(f"  valid:       {_dash(doc['valid_from'])} → {_dash(doc['valid_until'])}")
        print(f"  active:      {'yes' if doc['active'] else 'no'}")
        print(f"  created:     {doc['created_at']}")
        print(f"  hash:        {doc['hash_prefix']}… ({doc['integrity']})")
        if doc["links"]:
            print("  links:")
            for link in doc["links"]:
                print(f"    {link['id']} {link['relation']:<12} {link['memory']}")
        else:
            print("  links:       -")
        # No locator and no provenance line, by contract. The source's
        # identity is its id; what it points at stays in the ledger.
    return 0


def cmd_memory_source_link(args) -> int:
    memory_id = ids.parse_id(args.id, "memory")
    source_id = ids.parse_id(args.source_id, "memory_source")
    with _ledger(args) as (aos_dir, conn):
        link, changed = ops.link_memory_source(
            conn, memory_id=memory_id, source_id=source_id, relation=args.relation
        )
        mhid = ids.render_id("memory", memory_id)
        shid = ids.render_id("memory_source", source_id)
        if changed:
            print(
                f"{ids.render_id('memory_source_link', link.id)} "
                f"{mhid} ←{link.relation}— {shid}"
            )
        else:
            print(
                f"{mhid} is already linked to {shid} as '{link.relation}'; "
                "nothing changed."
            )
    return 0


def cmd_memory_edge_add(args) -> int:
    from_id = ids.parse_id(args.from_id, "memory")
    to_id = ids.parse_id(args.to_id, "memory")
    with _ledger(args) as (aos_dir, conn):
        edge, changed = ops.add_memory_edge(
            conn,
            from_memory_id=from_id,
            to_memory_id=to_id,
            relation=args.relation,
            valid_from=args.valid_from,
            valid_until=args.valid_until,
        )
        hid = ids.render_id("memory_edge", edge.id)
        arrow = (
            f"{ids.render_id('memory', edge.from_memory_id)} "
            f"—{edge.relation}→ {ids.render_id('memory', edge.to_memory_id)}"
        )
        if changed:
            print(f"{hid} {arrow}")
        else:
            print(f"{hid} already records {arrow}; nothing changed.")
    return 0


def _edge_line(doc: dict) -> str:
    return (
        f"{doc['id']:<9} {doc['from']:<8} {doc['relation']:<11} {doc['to']:<8} "
        f"{'active' if doc['active'] else 'expired':<8} "
        f"{doc['created_at']:<21} {doc['hash_prefix']}…"
    )


def cmd_memory_edge_list(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        docs = ops.list_memory_edges(
            conn,
            relation=args.relation,
            project_slug=args.project,
            active_only=args.active_only,
        )
        if args.json:
            _print_json({"edges": docs})
            return 0
        if not docs:
            print("(no memory edges)")
            return 0
        for doc in docs:
            print(_edge_line(doc))
    return 0


def _node_line(node: dict) -> str:
    if node.get("missing"):
        return f"  {node['id']:<8} depth {node['depth']}  (missing claim)"
    return (
        f"  {node['id']:<8} depth {node['depth']}  {node['status']:<11} "
        f"{node['sensitivity']:<13} {'live' if node['live'] else 'not retrieved':<14}"
        f"{'PIN' if node['pinned'] else ''}"
    )


def cmd_memory_graph(args) -> int:
    memory_id = ids.parse_id(args.id, "memory")
    with _ledger(args) as (aos_dir, conn):
        doc = ops.memory_graph(conn, memory_id=memory_id, depth=args.depth)
        if args.json:
            _print_json(doc)
            return 0
        print(f"{doc['memory']} neighbourhood (depth {doc['depth']})")
        print()
        print("nodes:")
        for node in doc["nodes"]:
            print(_node_line(node))
        print()
        print("edges:")
        if not doc["edges"]:
            print("  (none)")
        for edge in doc["edges"]:
            print(
                f"  {edge['id']:<9} {edge['from']:<8} {edge['relation']:<11} "
                f"{edge['to']:<8} {edge['direction']:<4} depth {edge['depth']}  "
                f"{'active' if edge['active'] else 'expired'}"
            )
        if doc["truncated"]:
            # Bounded AND honest about it: a silent stop reads as "that is the
            # whole neighbourhood" (D-v0.3.42).
            print()
            print(
                f"(truncated at the traversal caps: "
                f"{doc['limits']['nodes']} nodes / {doc['limits']['edges']} "
                "edges. This is a bounded view, not the whole graph.)"
            )
    return 0


def cmd_memory_contradictions(args) -> int:
    with _ledger(args) as (aos_dir, conn):
        docs = ops.list_contradictions(
            conn, project_slug=args.project, include_inactive=args.all
        )
        if args.json:
            _print_json({"contradictions": docs})
            return 0
        if not docs:
            scope = "" if args.all else "active "
            print(f"(no {scope}contradictions)")
            return 0
        for doc in docs:
            print(
                f"{doc['id']:<9} {doc['claims'][0]['id']} ⇄ "
                f"{doc['claims'][1]['id']}  "
                f"{'active' if doc['active'] else 'expired'}"
            )
            for claim in doc["claims"]:
                if claim.get("missing"):
                    print(f"    {claim['id']:<8} (missing claim)")
                    continue
                print(
                    f"    {claim['id']:<8} {claim['status']:<11} "
                    f"{claim['sensitivity']:<13} "
                    f"{'retrieved' if claim['live'] else 'not retrieved'}"
                )
        # Deliberately no verdict line: this command reports that two claims
        # were declared to disagree. Which one is true is a human's call, and
        # a tool that guessed here would be believed (D-v0.3.38).
    return 0


# ---------------------------------------------------------------------------
# U-M5 retrieval evaluation (contract M5.13)
#
# Four read_only leaves. `benchmark *` opens no database at all — it evaluates
# embedded synthetic fixtures in memory (D-v0.3.60) — and `retrieval query`
# issues SELECT only. None of them changes what `aos search` or `pack build`
# returns: U-M5 measures retrieval, it does not adopt it (D-v0.3.52).

def cmd_retrieval_benchmark_list(args) -> int:
    from . import retrieval

    index = retrieval.registry_index()
    if args.json:
        _print_json(index)
        return 0
    for row in index["benchmarks"]:
        print(
            f"{row['name']:<18} v{row['dataset_version']}  "
            f"{row['cases']:>2} case(s)  {row['fixture_claims']:>2} claim(s)  "
            f"{row['fixture_edges']:>2} edge(s)  {row['sha256']}"
        )
    print(f"registry {index['content_sha256']}")
    return 0


def cmd_retrieval_benchmark_show(args) -> int:
    from . import retrieval

    dataset = retrieval.get_benchmark(args.name)
    # Metadata and case IDs only. The synthetic fixture bodies are not here
    # and there is no flag that puts them here: retrieval_benchmarks/<name>.json
    # is the checked-in, digest-verified place to read a fixture (M5.13).
    doc = {
        "benchmark": dataset["benchmark"],
        "dataset_version": dataset["dataset_version"],
        "description": dataset["description"],
        "thresholds": dataset["thresholds"],
        "fixture_claims": len(dataset["fixture"]["claims"]),
        "fixture_edges": len(dataset["fixture"]["edges"]),
        "projects": list(dataset["fixture"]["projects"]),
        "cases": [case["case"] for case in dataset["cases"]],
        "content_sha256": dataset["content_sha256"],
    }
    if args.json:
        _print_json(doc)
        return 0
    print(f"{doc['benchmark']}  v{doc['dataset_version']}  {doc['content_sha256']}")
    print(f"  {doc['description']}")
    print(
        f"  fixture: {doc['fixture_claims']} claim(s), {doc['fixture_edges']} "
        f"edge(s), project(s): {', '.join(doc['projects'])}"
    )
    print(
        f"  thresholds: min_hit_rate {doc['thresholds']['min_hit_rate']} · "
        f"min_mrr {doc['thresholds']['min_mrr']}"
    )
    print("  cases:")
    for case in doc["cases"]:
        print(f"    {case}")
    return 0


def _print_benchmark_report(report: dict) -> None:
    print(
        f"{report['benchmark']}  v{report['dataset_version']}  k={report['k']}  "
        f"{report['dataset_sha256']}"
    )
    header = (
        f"{'candidate':<12} {'hit':>7} {'prec':>7} {'rec':>7} {'mrr':>7} "
        f"{'ndcg':>7} {'avg':>6}  gate"
    )
    print()
    print(header)
    for name, doc in report["candidates"].items():
        agg = doc["aggregate"]
        gate = doc["gate"]
        # `baseline` is the measured reference and is never gated for
        # promotion (D-v0.3.62) — the column says so rather than showing a
        # verdict nobody can act on.
        verdict = "n/a (reference)" if name == "baseline" else (
            "PASS" if gate["gate"] else "FAIL"
        )
        print(
            f"{name:<12} {_dash(agg['hit_at_k']):>7} "
            f"{_dash(agg['precision_at_k']):>7} {_dash(agg['recall_at_k']):>7} "
            f"{_dash(agg['mrr']):>7} {_dash(agg['ndcg_at_k']):>7} "
            f"{_dash(doc['avg_results']):>6}  {verdict}"
        )

    print()
    print("leakage (any non-zero is an automatic gate failure):")
    for name, doc in report["candidates"].items():
        counters = doc["counters"]
        print(
            f"  {name:<12} "
            + " · ".join(
                f"{cls.replace('_', ' ')} {counters[cls]}"
                for cls in ("forbidden_results", "wrong_project_leaks",
                            "restricted_leaks", "lifecycle_leaks",
                            "hash_invalid_included")
            )
            + f" · truncations {counters['truncations']}"
        )

    if report["deltas"]:
        print()
        print("delta vs baseline:")
        for name, delta in report["deltas"].items():
            print(
                f"  {name:<12} hit {_dash(delta['hit_at_k'])} · "
                f"prec {_dash(delta['precision_at_k'])} · "
                f"rec {_dash(delta['recall_at_k'])} · "
                f"mrr {_dash(delta['mrr'])} · ndcg {_dash(delta['ndcg_at_k'])}"
            )

    print()
    rec = report["recommendation"]
    print(f"recommendation: {rec['recommendation']} ({rec['reason']})")
    print(
        "(advisory: nothing here changes packs, `aos search`, or any "
        "configuration. Adoption is a human decision.)"
    )


def cmd_retrieval_benchmark_run(args) -> int:
    from . import retrieval

    report = retrieval.run_benchmark(args.name, candidate=args.candidate, k=args.k)
    if args.json:
        _print_json(report)
    else:
        _print_benchmark_report(report)
    if report["passed"]:
        return 0
    # The report still went to stdout — the report IS the finding. One
    # actionable line on stderr, exit 1 (M5.13).
    failed = [
        name
        for name in report["gated_candidates"]
        if not report["candidates"][name]["gate"]["gate"]
    ]
    print(
        f"Promotion gate FAILED for {', '.join(failed)} on "
        f"{report['benchmark']}. The full report is on stdout. Any leakage "
        "counter above zero fails the gate regardless of relevance.",
        file=sys.stderr,
    )
    return 1


def cmd_retrieval_query(args) -> int:
    from . import retrieval

    as_of = args.as_of or utils.utc_now_iso()
    utils.validate_instant(as_of, "--as-of")
    with _ledger(args) as (aos_dir, conn):
        corpus = retrieval.corpus_from_db(conn)
        retrieved = retrieval.retrieve(
            corpus,
            query=args.query,
            as_of=as_of,
            limit=args.limit,
            graph_depth=args.graph_depth,
            candidate=retrieval.CANDIDATE_1 if args.graph_depth else retrieval.CANDIDATE_0,
            project=args.project,
        )
        doc = retrieved.document()
        doc["as_of"] = as_of
        doc["project"] = args.project
        doc["graph_depth"] = args.graph_depth
        if args.show_key:
            # The one administrative content flag (D-v0.3.64): the claim KEY,
            # for claims that are eligible by construction — never value_md,
            # a locator, provenance text or an evidence ref. Strictly less
            # than `memory show` prints for exactly this population.
            keys = {claim.id: claim.key for claim in corpus.claims}
            for result, scored in zip(doc["results"], retrieved.results):
                result["key"] = keys[scored.claim.id]
        if args.json:
            _print_json(doc)
            return 0
        if doc["reason"] == retrieval.REASON_NO_TOKENS:
            print(
                "(no usable terms: every word was a stopword or punctuation. "
                "Nothing was searched.)"
            )
            return 0
        if not doc["results"]:
            print("(no results)")
            return 0
        for result in doc["results"]:
            line = (
                f"{result['rank']:>2}. {result['memory']:<8} "
                f"score {result['score']:>4}  {result['origin']:<8} "
                f"{result['scope']:<7} {_dash(result['project']):<10} "
                f"{result['sensitivity']:<12} "
                f"{'pinned' if result['pinned'] else '-':<6} "
                f"{result['hash_prefix']}"
            )
            if args.show_key:
                line += f"  {result['key']}"
            print(line)
            print(f"      reasons: {', '.join(result['reasons'])}")
            # Only the components that MOVED the score: a row of ten zeros is
            # noise, and the full component set is one --json away.
            moved = " ".join(
                f"{name}={value}"
                for name, value in result["components"].items()
                if value
            )
            print(f"      components: {moved or '(none)'}")
            origin = result["graph_origin"]
            if origin:
                print(
                    f"      via {origin['via']} on {origin['edge']} "
                    f"({origin['relation']}, {origin['direction']})"
                )
            if result["contradictions"]:
                # A count, never a verdict (D-v0.3.59).
                print(
                    f"      contradicted by {result['contradictions']} active "
                    "edge(s) — recorded disagreement, not a ruling"
                )
        if doc["truncation"]:
            print()
            print(
                "(truncated: "
                + ", ".join(f"{k}" for k in doc["truncation"])
                + ". This is a bounded view.)"
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


# ---------------------------------------------------------------------------
# Power modes (U-E2)
#
# These three deliberately resolve the workspace WITHOUT db.open_db(): the
# schema-version gate would make recovery control unreachable on exactly the
# databases that need it. `power status` needs no database at all.

def cmd_power_status(args) -> int:
    aos_dir = _resolve_aos_dir(args)
    try:
        state = power.read_state(aos_dir)
    except power.PowerStateError as exc:
        # Reporting the problem IS this command's job, so it prints rather
        # than raising — but it still exits 1: the state is not usable.
        print("runtime power mode: unknown — malformed or unsafe configuration")
        for line in power.matrix_lines(None):
            print(line)
        print(str(exc), file=sys.stderr)
        return 1
    source = "configured" if state.configured else "default"
    print(f"runtime power mode: {state.mode} ({source})")
    for line in power.matrix_lines(state.mode):
        print(line)
    return 0


def cmd_power_suggest(args) -> int:
    aos_dir = _resolve_aos_dir(args)
    result = power.suggest(aos_dir)
    print(f"suggestion: {result['mode']}")
    print(f"signal:     {result['signal']} ({result['count']})")
    print(
        "Advice only — nothing was changed. Only you change the mode: "
        f"python aos.py power set {result['mode']}"
    )
    return 0


def cmd_power_set(args) -> int:
    aos_dir = _resolve_aos_dir(args)
    result = power.set_mode(aos_dir, args.mode)
    if not result["changed"]:
        print(f"Already in '{result['mode']}'; nothing changed.")
        return 0
    print(f"Power mode: {result['previous']} → {result['mode']}")
    if result["mode"] == power.RECOVERY:
        print(
            "Authoritative and derived writes are now refused. Read-only and "
            "recovery-safe commands still work. Leaving recovery requires "
            "every hard doctor check to pass."
        )
    return 0


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
# Protocol spine (U-X1) — five read-only leaves.
#
# Every one of these is inert: it parses bytes and compares them to an
# embedded schema. None opens SQLite, creates power.json or workspace state,
# emits an event, or requires an initialized workspace — so none of them uses
# _ledger() or _resolve_aos_dir(). None follows a reference found inside an
# artifact (D-v0.3.7).

def cmd_protocol_list(args) -> int:
    from . import protocols

    entries = protocols.list_entries()
    if args.json:
        _print_json(
            [
                {
                    "schema": entry.identity,
                    "name": entry.name,
                    "major": entry.major,
                    "status": entry.status,
                    "sha256": entry.digest,
                }
                for entry in entries
            ]
        )
        return 0
    width = max(len(entry.name) for entry in entries)
    for entry in entries:
        print(
            f"{entry.name:<{width}}  v{entry.major}  {entry.status:<10}  "
            f"{entry.digest}"
        )
    return 0


def cmd_protocol_show(args) -> int:
    from . import protocols

    entry = protocols.get_entry(args.schema)
    # The exact canonical representation, byte-identical to the checked-in
    # protocols/<name>/v<major>.schema.json.
    sys.stdout.write(entry.canonical_bytes.decode("utf-8") + "\n")
    return 0


def cmd_protocol_validate(args) -> int:
    from . import protocols

    document, entry = protocols.load_artifact_file(args.file)
    # Success prints the identity and the verified digest — nothing else from
    # the document reaches stdout.
    print(f"{entry.identity} {document[protocols.CONTENT_HASH_FIELD]}")
    return 0


def cmd_protocol_digest(args) -> int:
    from . import protocols

    document = protocols.parse_canonical(protocols.read_artifact_bytes(args.file))
    # The source file is read and never rewritten.
    print(protocols.content_digest(document))
    return 0


def cmd_protocol_verify_registry(args) -> int:
    from . import protocols

    problems = protocols.verify_registry_digests()
    entries = protocols.list_entries()
    print(f"embedded registry: {len(entries)} schema(s)")
    for entry in entries:
        print(f"  {entry.identity}  {entry.status}  {entry.digest}")

    source = protocols.source_artifacts_dir()
    if source is None:
        # A zipapp legitimately has no protocols/ directory (D-v0.3.2).
        # Failing here would train people to ignore this command.
        print(
            "checked-in artifacts: comparison unavailable — no source checkout "
            "(expected when running from aos.pyz; the embedded registry above "
            "is the canonical definition)"
        )
    else:
        source_problems = protocols.verify_source_artifacts(source)
        problems += source_problems
        if source_problems:
            print(f"checked-in artifacts: {len(source_problems)} problem(s)")
        else:
            print("checked-in artifacts: match the embedded definitions byte-for-byte")

    if problems:
        print(
            "Registry verification failed: " + "; ".join(problems) + ". Regenerate "
            "with: python3 tools/gen_protocols.py",
            file=sys.stderr,
        )
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

    p_memory = sub.add_parser("memory", help="scoped memory claims")
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
    p_memory_add.add_argument(
        "--sensitivity",
        choices=list(MEMORY_SENSITIVITIES),
        default=MEMORY_SENSITIVITY_DEFAULT,
        help="claim sensitivity (default: internal). 'restricted' claims "
        "never enter context packs, search snippets or mirror bodies.",
    )
    p_memory_add.add_argument(
        "--pin", action="store_true",
        help="pin the new claim (ordering only; refused if it would already "
        "be ineligible for retrieval)",
    )
    p_memory_add.add_argument(
        "--evidence", action="append", metavar="EVIDENCE_ID", default=None,
        help="link an evidence row to the claim (repeatable; order and "
        "duplicates do not matter)",
    )
    p_memory_add.set_defaults(func=cmd_memory_add)
    p_memory_list = memory_sub.add_parser(
        "list", help="list memory claims (history included, by design)"
    )
    p_memory_list.add_argument("--scope", default=None)
    p_memory_list.add_argument("-p", "--project", default=None)
    p_memory_list.add_argument(
        "--status", default=None, choices=list(MEMORY_STATUSES),
        help="show only claims with this curation status",
    )
    p_memory_pin_filter = p_memory_list.add_mutually_exclusive_group()
    p_memory_pin_filter.add_argument(
        "--pinned", action="store_true", help="show only pinned claims"
    )
    p_memory_pin_filter.add_argument(
        "--unpinned", action="store_true", help="show only unpinned claims"
    )
    p_memory_list.add_argument("--json", action="store_true")
    p_memory_list.set_defaults(func=cmd_memory_list)
    p_memory_show = memory_sub.add_parser(
        "show",
        help="show one claim: status, pin state, hash, evidence ids "
        "(read-only)",
    )
    p_memory_show.add_argument("id", metavar="MEMORY_ID")
    p_memory_show.add_argument("--json", action="store_true")
    p_memory_show.set_defaults(func=cmd_memory_show)
    p_memory_pin = memory_sub.add_parser(
        "pin",
        help="pin a live claim so it leads the pack MEMORY section "
        "(ordering only)",
    )
    p_memory_pin.add_argument("id", metavar="MEMORY_ID")
    p_memory_pin.set_defaults(func=cmd_memory_pin, pinned_state=True)
    p_memory_unpin = memory_sub.add_parser("unpin", help="remove a claim's pin")
    p_memory_unpin.add_argument("id", metavar="MEMORY_ID")
    p_memory_unpin.set_defaults(func=cmd_memory_pin, pinned_state=False)
    p_memory_link = memory_sub.add_parser(
        "link-evidence", help="link an evidence row to a memory claim"
    )
    p_memory_link.add_argument("id", metavar="MEMORY_ID")
    p_memory_link.add_argument("evidence_id", metavar="EVIDENCE_ID")
    p_memory_link.set_defaults(func=cmd_memory_link_evidence)
    p_memory_retire = memory_sub.add_parser(
        "retire",
        help="retire a memory claim (status=retired; sets valid_until to now)",
    )
    p_memory_retire.add_argument("id")
    p_memory_retire.set_defaults(func=cmd_memory_retire)

    # --- U-M3 memory graph (contract M3.8)

    p_memory_classify = memory_sub.add_parser(
        "classify",
        help="raise a claim's sensitivity (increases only; U-S6 owns "
        "down-classification)",
    )
    p_memory_classify.add_argument("id", metavar="MEMORY_ID")
    p_memory_classify.add_argument(
        "level", metavar="LEVEL", choices=list(MEMORY_SENSITIVITIES)
    )
    p_memory_classify.set_defaults(func=cmd_memory_classify)

    p_memory_source = memory_sub.add_parser(
        "source", help="normalized provenance sources for memory claims"
    )
    source_sub = p_memory_source.add_subparsers(
        dest="subsubcommand", metavar="SUBCOMMAND", required=True
    )
    p_source_add = source_sub.add_parser(
        "add",
        help="record a provenance source (references are inert: never "
        "opened, fetched or executed)",
    )
    p_source_add.add_argument(
        "--kind", required=True, choices=list(MEMORY_SOURCE_KINDS)
    )
    p_source_add.add_argument("-p", "--project", default=None)
    p_source_add.add_argument(
        "--evidence", default=None,
        help="required for --kind evidence, forbidden otherwise",
    )
    p_source_add.add_argument(
        "--locator", default=None,
        help="required for every kind except evidence, forbidden for it",
    )
    p_source_add.add_argument("--provenance", default="human")
    p_source_add.add_argument(
        "--sensitivity",
        choices=list(MEMORY_SENSITIVITIES),
        default=MEMORY_SENSITIVITY_DEFAULT,
    )
    p_source_add.add_argument("--observed-at", dest="observed_at", default=None)
    p_source_add.add_argument("--valid-from", dest="valid_from", default=None)
    p_source_add.add_argument("--valid-until", dest="valid_until", default=None)
    p_source_add.set_defaults(func=cmd_memory_source_add)

    p_source_list = source_sub.add_parser(
        "list", help="list provenance sources (metadata only)"
    )
    p_source_list.add_argument("-p", "--project", default=None)
    p_source_list.add_argument("--kind", default=None)
    p_source_list.add_argument(
        "--active-only", dest="active_only", action="store_true"
    )
    p_source_list.add_argument("--json", action="store_true")
    p_source_list.set_defaults(func=cmd_memory_source_list)

    p_source_show = source_sub.add_parser(
        "show",
        help="one source's metadata and integrity verdict (never its "
        "locator or provenance)",
    )
    p_source_show.add_argument("id", metavar="SOURCE_ID")
    p_source_show.add_argument("--json", action="store_true")
    p_source_show.set_defaults(func=cmd_memory_source_show)

    p_source_link = source_sub.add_parser(
        "link", help="link a source to a memory claim"
    )
    p_source_link.add_argument("id", metavar="MEMORY_ID")
    p_source_link.add_argument("source_id", metavar="SOURCE_ID")
    p_source_link.add_argument(
        "--relation", required=True, choices=list(MEMORY_SOURCE_RELATIONS)
    )
    p_source_link.set_defaults(func=cmd_memory_source_link)

    p_memory_edge = memory_sub.add_parser(
        "edge", help="typed relationships between memory claims"
    )
    edge_sub = p_memory_edge.add_subparsers(
        dest="subsubcommand", metavar="SUBCOMMAND", required=True
    )
    p_edge_add = edge_sub.add_parser(
        "add",
        help="record a relationship (descriptive only: triggers no workflow "
        "and decides nothing)",
    )
    p_edge_add.add_argument("from_id", metavar="FROM_MEMORY_ID")
    p_edge_add.add_argument("to_id", metavar="TO_MEMORY_ID")
    p_edge_add.add_argument(
        "--relation", required=True, choices=list(MEMORY_EDGE_RELATIONS)
    )
    p_edge_add.add_argument("--valid-from", dest="valid_from", default=None)
    p_edge_add.add_argument("--valid-until", dest="valid_until", default=None)
    p_edge_add.set_defaults(func=cmd_memory_edge_add)

    p_edge_list = edge_sub.add_parser("list", help="list memory relationships")
    p_edge_list.add_argument("--relation", default=None)
    p_edge_list.add_argument("-p", "--project", default=None)
    p_edge_list.add_argument(
        "--active-only", dest="active_only", action="store_true"
    )
    p_edge_list.add_argument("--json", action="store_true")
    p_edge_list.set_defaults(func=cmd_memory_edge_list)

    p_memory_graph = memory_sub.add_parser(
        "graph",
        help="a bounded, read-only neighbourhood of one claim (ids and "
        "relations only)",
    )
    p_memory_graph.add_argument("id", metavar="MEMORY_ID")
    p_memory_graph.add_argument(
        "--depth",
        type=int,
        default=1,
        choices=list(range(1, ops.MAX_GRAPH_DEPTH + 1)),
    )
    p_memory_graph.add_argument("--json", action="store_true")
    p_memory_graph.set_defaults(func=cmd_memory_graph)

    p_memory_contra = memory_sub.add_parser(
        "contradictions",
        help="list declared contradictions (reports; never decides which "
        "claim is true)",
    )
    p_memory_contra.add_argument("-p", "--project", default=None)
    p_memory_contra.add_argument(
        "--all", action="store_true",
        help="include expired contradiction edges (default: active only)",
    )
    p_memory_contra.add_argument("--json", action="store_true")
    p_memory_contra.set_defaults(func=cmd_memory_contradictions)

    # U-A1 governed agent registry. Records and declarations only: nothing
    # here executes, routes, schedules or authorizes an agent.
    p_agent = sub.add_parser(
        "agent", help="governed agent registry (records only; never "
        "executes agents)"
    )
    agent_sub = p_agent.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )
    p_agent_create = agent_sub.add_parser(
        "create", help="register a DRAFT agent identity with a draft v1 "
        "passport (immutable only at publish)"
    )
    p_agent_create.add_argument("name")
    p_agent_create.add_argument(
        "--class", dest="agent_class", default="custom",
        choices=list(AGENT_CLASSES),
    )
    p_agent_create.add_argument(
        "-p", "--project", default=None, metavar="SLUG",
        help="file the agent under a project (scope=project)",
    )
    p_agent_create.add_argument("--role", default=None, metavar="TEXT")
    p_agent_create.add_argument("--mission", default=None, metavar="TEXT")
    p_agent_create.add_argument(
        "--from-file", dest="from_file", default=None, metavar="FILE",
        help="inert JSON fragment of passport body declarations "
        "(capabilities, task_families, limits, …)",
    )
    p_agent_create.add_argument("--json", action="store_true")
    p_agent_create.set_defaults(func=cmd_agent_create)

    p_agent_import = agent_sub.add_parser(
        "import", help="import a beast.agent-passport/v1 artifact as a "
        "DRAFT identity (the file is inert: nothing it names is opened, "
        "fetched or executed)"
    )
    p_agent_import.add_argument("file", metavar="FILE")
    p_agent_import.add_argument("--json", action="store_true")
    p_agent_import.set_defaults(func=cmd_agent_import)

    p_agent_list = agent_sub.add_parser("list", help="list registered agents")
    p_agent_list.add_argument(
        "--all", action="store_true",
        help="include archived and revoked agents",
    )
    p_agent_list.add_argument("-p", "--project", default=None, metavar="SLUG")
    p_agent_list.add_argument("--json", action="store_true")
    p_agent_list.set_defaults(func=cmd_agent_list)

    p_agent_show = agent_sub.add_parser("show", help="show one agent")
    p_agent_show.add_argument("name")
    p_agent_show.add_argument("--json", action="store_true")
    p_agent_show.set_defaults(func=cmd_agent_show)

    p_agent_export = agent_sub.add_parser(
        "export", help="print a passport's stored canonical document "
        "(default: the current published version)"
    )
    p_agent_export.add_argument("name")
    p_agent_export.add_argument(
        "--version", type=int, default=None, metavar="N",
        help="a specific version; the only way to export a draft",
    )
    p_agent_export.set_defaults(func=cmd_agent_export)

    p_agent_passport = agent_sub.add_parser(
        "passport", help="passport versions (immutable once published)"
    )
    passport_sub = p_agent_passport.add_subparsers(
        dest="subsubcommand", metavar="SUBCOMMAND", required=True
    )
    p_passport_publish = passport_sub.add_parser(
        "publish", help="publish the pending draft (or, with --file, a new "
        "version N+1)"
    )
    p_passport_publish.add_argument("name")
    p_passport_publish.add_argument(
        "--file", default=None, metavar="FILE",
        help="a beast.agent-passport/v1 artifact declaring the next version",
    )
    p_passport_publish.add_argument("--json", action="store_true")
    p_passport_publish.set_defaults(func=cmd_agent_passport_publish)
    p_passport_history = passport_sub.add_parser(
        "history", help="list an agent's passport versions"
    )
    p_passport_history.add_argument("name")
    p_passport_history.add_argument("--json", action="store_true")
    p_passport_history.set_defaults(func=cmd_agent_passport_history)

    for verb, help_text in (
        ("suspend", "declare an active agent parked (reversible)"),
        ("archive", "move an agent to history (restorable)"),
        ("restore", "return a suspended/archived agent to active"),
        ("revoke", "permanently distrust an agent (terminal, journaled)"),
    ):
        p_verb = agent_sub.add_parser(verb, help=help_text)
        p_verb.add_argument("name")
        p_verb.set_defaults(func=cmd_agent_lifecycle)

    p_agent_discard = agent_sub.add_parser(
        "discard", help="remove a never-published, never-referenced DRAFT "
        "(the discard event preserves the audit trail)"
    )
    p_agent_discard.add_argument("name")
    p_agent_discard.set_defaults(func=cmd_agent_discard)

    # U-A2 built-in specialist catalog. Five read-only leaves this wave;
    # `install` does not exist yet.
    p_agent_catalog = agent_sub.add_parser(
        "catalog", help="the built-in specialist catalog (inert "
        "declarations; read-only in this build)"
    )
    catalog_sub = p_agent_catalog.add_subparsers(
        dest="subsubcommand", metavar="SUBCOMMAND", required=True
    )
    p_catalog_list = catalog_sub.add_parser(
        "list", help="list the built-in catalog's entries"
    )
    p_catalog_list.add_argument("--json", action="store_true")
    p_catalog_list.set_defaults(func=cmd_agent_catalog_list)

    p_catalog_show = catalog_sub.add_parser(
        "show", help="show one catalog entry's declaration"
    )
    p_catalog_show.add_argument("name")
    p_catalog_show.add_argument(
        "--document", action="store_true",
        help="print the exact stored canonical artifact",
    )
    p_catalog_show.add_argument(
        "--fragment", action="store_true",
        help="print the document minus CLI-owned envelope fields, ready "
        "for `agent create --from-file`",
    )
    p_catalog_show.add_argument("--json", action="store_true")
    p_catalog_show.set_defaults(func=cmd_agent_catalog_show)

    p_catalog_verify = catalog_sub.add_parser(
        "verify", help="verify the built-in catalog's manifest and artifacts"
    )
    p_catalog_verify.add_argument("--json", action="store_true")
    p_catalog_verify.set_defaults(func=cmd_agent_catalog_verify)

    p_catalog_status = catalog_sub.add_parser(
        "status", help="this workspace's installed-state for every catalog "
        "entry"
    )
    p_catalog_status.add_argument("--json", action="store_true")
    p_catalog_status.set_defaults(func=cmd_agent_catalog_status)

    p_catalog_plan = catalog_sub.add_parser(
        "plan", help="install/upgrade/noop/refuse actions, without writing "
        "anything"
    )
    p_catalog_plan.add_argument("names", nargs="*", metavar="NAME")
    p_catalog_plan.add_argument("--all", action="store_true")
    p_catalog_plan.add_argument("--json", action="store_true")
    p_catalog_plan.set_defaults(func=cmd_agent_catalog_plan)

    p_catalog_install = catalog_sub.add_parser(
        "install", help="install (or upgrade) catalog entries into this "
        "workspace — the only command that writes a catalog row"
    )
    p_catalog_install.add_argument("names", nargs="*", metavar="NAME")
    p_catalog_install.add_argument("--all", action="store_true")
    p_catalog_install.add_argument("--json", action="store_true")
    p_catalog_install.set_defaults(func=cmd_agent_catalog_install)

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

    p_power = sub.add_parser(
        "power",
        help="runtime power modes (U-E2): eco / standard / deep / recovery. "
        "Local execution policy only — never picks a model, runs anything in "
        "the background, or switches mode on its own.",
    )
    power_sub = p_power.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )
    p_power_status = power_sub.add_parser(
        "status",
        help="print the current mode and the degradation matrix (read-only; "
        "never creates power.json)",
    )
    p_power_status.set_defaults(func=cmd_power_status)
    p_power_suggest = power_sub.add_parser(
        "suggest",
        help="print a deterministic, advisory mode suggestion (read-only; "
        "never switches the mode)",
    )
    p_power_suggest.set_defaults(func=cmd_power_suggest)
    p_power_set = power_sub.add_parser(
        "set",
        help="set the mode (the only command that writes power.json). "
        "recovery is always available; leaving it needs a clean doctor.",
    )
    p_power_set.add_argument("mode", choices=list(power.MODES))
    p_power_set.set_defaults(func=cmd_power_set)

    p_protocol = sub.add_parser(
        "protocol",
        help="protocol spine (U-X1): inspect and validate inert WorkSpec / "
        "Result Envelope / Interrupt artifacts (read-only)",
    )
    protocol_sub = p_protocol.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )

    p_protocol_list = protocol_sub.add_parser(
        "list",
        help="list registered schemas with their digests (no workspace or "
        "database required)",
    )
    p_protocol_list.add_argument("--json", action="store_true")
    p_protocol_list.set_defaults(func=cmd_protocol_list)

    p_protocol_show = protocol_sub.add_parser(
        "show", help="print one schema's exact canonical representation"
    )
    p_protocol_show.add_argument(
        "schema", metavar="SCHEMA", help="full identity, e.g. beast.work-spec/v1"
    )
    p_protocol_show.set_defaults(func=cmd_protocol_show)

    p_protocol_validate = protocol_sub.add_parser(
        "validate",
        help="validate an artifact's syntax, bounds, identity, content hash "
        "and cross-field invariants (never executes or imports it)",
    )
    p_protocol_validate.add_argument("file", metavar="FILE")
    p_protocol_validate.set_defaults(func=cmd_protocol_validate)

    p_protocol_digest = protocol_sub.add_parser(
        "digest",
        help="print an artifact's canonical content digest (never rewrites "
        "the source file)",
    )
    p_protocol_digest.add_argument("file", metavar="FILE")
    p_protocol_digest.set_defaults(func=cmd_protocol_digest)

    p_protocol_verify = protocol_sub.add_parser(
        "verify-registry",
        help="verify the embedded registry, and the checked-in protocols/ "
        "artifacts when running from a source checkout",
    )
    p_protocol_verify.set_defaults(func=cmd_protocol_verify_registry)

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

    # U-M5 retrieval evaluation (M5.13). Four read_only leaves; none of them
    # changes what `aos search` or `pack build` returns (D-v0.3.52).
    p_retrieval = sub.add_parser(
        "retrieval",
        help="evaluate candidate memory retrieval (measurement only; changes "
        "no pack and no search)",
    )
    retrieval_sub = p_retrieval.add_subparsers(
        dest="subcommand", metavar="SUBCOMMAND", required=True
    )

    p_benchmark = retrieval_sub.add_parser(
        "benchmark", help="deterministic retrieval benchmarks"
    )
    benchmark_sub = p_benchmark.add_subparsers(
        dest="subsubcommand", metavar="SUBCOMMAND", required=True
    )

    p_bench_list = benchmark_sub.add_parser(
        "list", help="list benchmarks with versions, counts and digests"
    )
    p_bench_list.add_argument("--json", action="store_true")
    p_bench_list.set_defaults(func=cmd_retrieval_benchmark_list)

    p_bench_show = benchmark_sub.add_parser(
        "show", help="show one benchmark's metadata and case ids"
    )
    p_bench_show.add_argument("name")
    p_bench_show.add_argument("--json", action="store_true")
    p_bench_show.set_defaults(func=cmd_retrieval_benchmark_show)

    p_bench_run = benchmark_sub.add_parser(
        "run", help="evaluate candidates against a benchmark (read-only)"
    )
    p_bench_run.add_argument("name")
    p_bench_run.add_argument("--json", action="store_true")
    p_bench_run.add_argument(
        "--candidate",
        default="all",
        choices=list(_retrieval_candidate_choices()),
        help="which retriever(s) to evaluate (default: all)",
    )
    p_bench_run.add_argument(
        "--k",
        type=int,
        default=5,
        metavar="N",
        help="metric cutoff, 1..10 (default: 5)",
    )
    p_bench_run.set_defaults(func=cmd_retrieval_benchmark_run)

    p_query = retrieval_sub.add_parser(
        "query", help="run the candidate retriever against this workspace"
    )
    p_query.add_argument("query")
    p_query.add_argument("--project", default=None, metavar="SLUG")
    p_query.add_argument(
        "--as-of", dest="as_of", default=None, metavar="TS",
        help="evaluate temporal validity at this instant (default: now)",
    )
    p_query.add_argument("--limit", type=int, default=5, metavar="N")
    p_query.add_argument(
        "--graph-depth", dest="graph_depth", type=int, default=0, choices=[0, 1],
        help="0 = lexical/temporal only; 1 = bounded expansion over active edges",
    )
    p_query.add_argument("--json", action="store_true")
    p_query.add_argument(
        "--show-key", dest="show_key", action="store_true",
        help="also print each result's claim key (eligible claims only; never "
        "the value, a locator, provenance or an evidence ref)",
    )
    p_query.set_defaults(func=cmd_retrieval_query)

    return parser


def _retrieval_candidate_choices() -> tuple[str, ...]:
    """Imported lazily and via the module, so the parser's choices ARE the
    retriever's vocabulary — a new candidate cannot exist that `--candidate`
    refuses, and vice versa."""
    from . import retrieval

    return retrieval.CANDIDATE_CHOICES


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:]) if argv is None else list(argv)
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        # U-E2: the ONE place runtime power policy is applied. Recovery
        # refusals and deep preflights fire before args.func runs, so stdout
        # stays empty and no mutation can have happened; deep
        # post-verification runs after a successful authoritative write.
        return power.dispatch(args)
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
