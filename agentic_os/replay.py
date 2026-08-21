"""U-E6 deterministic replay and re-simulation.

Contract: agentic-os-v0.4-u-e6-flight-recorder-replay-contract.md §1, §4.2-§4.3,
§8, §11.

Deterministic replay re-executes the pure reducer over a flight record's event
sequence in isolation: it NEVER issues intents, delivers receipts, records
facts, mutates a ledger, mints a workflow id, or executes anything. It produces
a replay trace with a per-step `byte_identical` boolean and a
`divergence_at_seq` when the folded snapshot disagrees with a stored command's
`expected_revision` / `resulting_revision`.

Replay is fold-based by construction (U-E6 §1: workflow history folding IS
"the pure reducer `decide` applied sequentially to the accepted commands'
`workflow_events`"). Command bodies are NOT stored in the ledger — only their
digests — so `decide` cannot literally be re-invoked per event; the folded
snapshot's revisions are compared against the stored command revision pair,
which is exactly the ledger's own acceptance evidence.

The WorkSpec document is fetched from the ledger by digest (or from the
substitution set in re-simulation) and validated against `work_spec_digest`,
so no project prose ever needs to ride in a bundle.

Failure semantics (§11): bundle integrity failure = exit 1; unknown
protocol_version / WorkSpec not found / reducer vocabulary mismatch /
malformed substitution = exit 2; substitution producing an invalid WorkSpec or
a digest mismatch without `allow_digest_mismatch: true` = exit 3. Divergence
and reducer refusal are REPORTED, not failed: the trace carries them and the
process exits 0.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from . import db, flight_recorder, protocols, workflow_engine
from .utils import AosError

WORK_SPEC_SCHEMA = "beast.work-spec/v1"

_ALLOWED_SUBSTITUTIONS = frozenset({
    "work_spec_document",
    "retry_max_attempts",
    "transition_policy_version",
    "synthetic_receipts",
    "removed_event_seq",
    "allow_digest_mismatch",
})


def _refusal(message: str, exit_code: int) -> AosError:
    error = AosError(message)
    error.exit_code = exit_code
    return error


def read_substitutions(path: Path) -> dict:
    """Load and shape-check a substitution file. Malformed → exit 2."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise _refusal(
            f"Could not read substitution file {path}: "
            f"{exc.__class__.__name__}.", 2
        )
    try:
        document = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise _refusal(
            f"Substitution file {path} is not valid JSON.", 2
        )
    if not isinstance(document, dict):
        raise _refusal(
            "The substitution file must be a JSON object.", 2
        )
    unknown = set(document) - _ALLOWED_SUBSTITUTIONS
    if unknown:
        raise _refusal(
            f"Unknown substitution key(s): {', '.join(sorted(unknown))}. "
            "Declared substitutions: "
            "work_spec_document, retry_max_attempts, "
            "transition_policy_version, synthetic_receipts, "
            "removed_event_seq, allow_digest_mismatch.", 2
        )
    return document


def _work_spec_document(
    payload: dict, substitutions: dict, conn: sqlite3.Connection | None,
) -> tuple[dict, bool]:
    """The WorkSpec for replay: from the substitution set when declared, else
    from the ledger by digest. Validates it against `work_spec_digest`.

    Returns (document, is_substituted). A mismatch without
    `allow_digest_mismatch: true` refuses with exit 3; an unknown digest on
    the ledger refuses with exit 2.
    """
    work_spec_digest = payload["work_spec_digest"]
    declared = substitutions.get("work_spec_document")
    if declared is not None:
        if not isinstance(declared, dict):
            raise _refusal(
                "substitution work_spec_document must be a JSON object.", 2
            )
        digest = protocols.content_digest(declared)
        if digest != work_spec_digest and not substitutions.get(
            "allow_digest_mismatch"
        ):
            raise _refusal(
                "Substitution WorkSpec digest does not match the flight "
                "record's work_spec_digest. Declare "
                '"allow_digest_mismatch": true to proceed, or use the '
                "recorded WorkSpec.", 3
            )
        return declared, True

    if conn is None:
        raise _refusal(
            "The WorkSpec is not in the substitution set and no ledger is "
            "available to fetch it by digest.", 2
        )
    row = conn.execute(
        "SELECT work_spec_document FROM workflows WHERE work_spec_sha256 = ?",
        (work_spec_digest,),
    ).fetchone()
    if row is None:
        raise _refusal(
            f"No WorkSpec on the ledger with digest {work_spec_digest}. "
            "The flight record cannot be replayed without it.", 2
        )
    document = json.loads(row[0])
    if protocols.content_digest(document) != work_spec_digest:
        raise _refusal(
            "The ledger WorkSpec does not match its digest; the ledger is "
            "corrupt. Run: python aos.py workflow verify", 2
        )
    return document, False


def _validate_substitutions(substitutions: dict) -> None:
    """Shape-check every declared substitution. Malformed → exit 2."""
    if "retry_max_attempts" in substitutions:
        value = substitutions["retry_max_attempts"]
        if not isinstance(value, int) or isinstance(value, bool):
            raise _refusal(
                "substitution retry_max_attempts must be an integer.", 2
            )
        if not 1 <= value <= 10:
            raise _refusal(
                "substitution retry_max_attempts must be between 1 and 10.", 2
            )
    if "transition_policy_version" in substitutions:
        value = substitutions["transition_policy_version"]
        if value not in (1, 2):
            raise _refusal(
                "substitution transition_policy_version must be 1 or 2.", 2
            )
    if "removed_event_seq" in substitutions:
        value = substitutions["removed_event_seq"]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise _refusal(
                "substitution removed_event_seq must be a positive integer.", 2
            )
    if "synthetic_receipts" in substitutions:
        value = substitutions["synthetic_receipts"]
        if not isinstance(value, list) or not all(
            isinstance(item, dict) for item in value
        ):
            raise _refusal(
                "substitution synthetic_receipts must be an array of receipt "
                "objects.", 2
            )
    if "allow_digest_mismatch" in substitutions:
        if not isinstance(substitutions["allow_digest_mismatch"], bool):
            raise _refusal(
                "substitution allow_digest_mismatch must be a boolean.", 2
            )


def _reduce_events(payload: dict, substitutions: dict) -> tuple[list, list]:
    """Apply `removed_event_seq` to the event sequence. Returns (events,
    applied_substitutions) where applied is the list of declared substitutions
    actually exercised on the sequence.

    Removal renumbers the surviving events to a dense sequence — both `seq`
    and `revision`, since the reducer folds a history that is dense in both
    (a gap in either would be read as corruption) — and re-seals each
    surviving event (its `content_sha256` recomputed), because the reducer
    verifies every record's digest. The removal is a DECLARED counterfactual,
    so the renumbered, re-sealed sequence is exactly the trace content — no
    claim is made about the original ledger or its digests.
    """
    events = [
        dict(event) for event in (payload.get("workflow_events") or [])
    ]
    applied = []
    removed = substitutions.get("removed_event_seq")
    if removed is not None:
        kept = [e for e in events if e.get("seq") != removed]
        if len(kept) == len(events):
            raise _refusal(
                f"removed_event_seq {removed} is not present in the event "
                "sequence.", 2
            )
        for index, event in enumerate(kept, start=1):
            event["seq"] = index
            event["revision"] = index
            event["content_sha256"] = protocols.content_digest(event)
        events = kept
        applied.append({"kind": "removed_event_seq", "seq": removed})
    return events, applied


def _attempt_budget_of(document: dict, override) -> int:
    """The budget rule the reducer uses (§6.1): the WorkSpec's own
    `retry.max_attempts`, defaulting to 1. `override` is the declared
    re-simulation substitution when present."""
    if override is not None:
        return override
    retry = document.get("retry") if isinstance(document.get("retry"), dict) \
        else {}
    return retry.get("max_attempts", 1)


def _fold_trace(events: list, work_spec_document: dict, substitutions: dict,
                substituted: bool, commands: list) -> dict:
    """Fold the event sequence step by step and compare against the stored
    command revision pairs. Returns the trace (never raises for divergence or
    reducer refusal — those are trace content)."""
    events = sorted(events, key=lambda e: e["seq"])
    if not events:
        raise _refusal(
            "The flight record has an empty event sequence; a workflow has at "
            "least one event. Bundle integrity is at fault.", 1
        )
    # A removed event renumbers the sequence, so the stored command revision
    # pairs no longer apply: the cross-check is disabled for a declared
    # counterfactual sequence.
    check_commands = substitutions.get("removed_event_seq") is None

    # Per-step folded snapshots.
    steps = []
    folded_revisions = {}
    refusal = None
    for index, event in enumerate(events, start=1):
        try:
            snapshot = workflow_engine.fold(events[:index])
        except workflow_engine.WorkflowRefusal as exc:
            refusal = {
                "reason": exc.reason,
                "where": exc.where or "/",
            }
            break
        folded_revisions[event["seq"]] = snapshot["revision"]
        expected_state = event.get("to_state") or event.get("from_state")
        steps.append({
            "seq": event["seq"],
            "event": event["event"],
            "from_state": event.get("from_state"),
            "to_state": event.get("to_state"),
            "revision": event["revision"],
            "byte_identical": (
                snapshot["revision"] == event["revision"]
                and snapshot["state"] == expected_state
            ),
        })

    divergence_at_seq = None
    if refusal is None and check_commands:
        # Cross-check the stored command revision pairs against the folded
        # sequence: each accepted command's expected/resulting revisions must
        # be exactly what the fold produces at its event boundaries.
        for command in sorted(commands, key=lambda c: c["id"]):
            first = command["event_seq_first"]
            last = command["event_seq_last"]
            expected = folded_revisions.get(first - 1)
            resulting = folded_revisions.get(last)
            if first == 1:
                if command["expected_revision"] != 0:
                    divergence_at_seq = first
                    break
            elif expected != command["expected_revision"]:
                divergence_at_seq = first
                break
            if resulting != command["resulting_revision"]:
                divergence_at_seq = last
                break

    last = steps[-1] if steps else None
    final_state = None
    final_revision = None
    if last is not None:
        try:
            snapshot = workflow_engine.fold(events)
            final_state = snapshot["state"]
            final_revision = snapshot["revision"]
        except workflow_engine.WorkflowRefusal as exc:
            refusal = {
                "reason": exc.reason,
                "where": exc.where or "/",
            }

    # Re-simulation: report the declared attempt budget per dispatch event.
    override = substitutions.get("retry_max_attempts")
    for step in steps:
        if step["event"] == "dispatch_requested":
            step["attempt_budget"] = _attempt_budget_of(
                work_spec_document, override
            )

    return {
        "steps": steps,
        "byte_identical": refusal is None and divergence_at_seq is None,
        "divergence_at_seq": divergence_at_seq,
        "refusal": refusal,
        "final_state": final_state,
        "final_revision": final_revision,
    }


def replay(
    payload: dict, conn: sqlite3.Connection, substitutions: dict | None = None,
) -> dict:
    """Run deterministic replay (or, with substitutions, re-simulation)."""
    flight_recorder._require_protocol(payload)
    if payload.get("schema_version") != db.SCHEMA_VERSION:
        raise _refusal(
            f"The flight record's schema_version {payload.get('schema_version')!r} "
            f"implies a vocabulary the reducer cannot process (this build is "
            f"{db.SCHEMA_VERSION!r}). reducer_vocabulary_mismatch.", 2
        )
    if substitutions is None:
        substitutions = {}

    report = flight_recorder.verify(payload)
    if not report["ok"]:
        raise _refusal(
            "The flight record failed integrity verification; replay refuses. "
            f"{len(report['findings'])} finding(s).", 1
        )

    _validate_substitutions(substitutions)
    work_spec_document, substituted = _work_spec_document(
        payload, substitutions, conn
    )

    events, applied = _reduce_events(payload, substitutions)
    trace = _fold_trace(
        events, work_spec_document, substitutions, substituted,
        payload.get("workflow_commands") or [],
    )

    trace["workflow_id"] = payload["workflow_id"]
    trace["work_spec_digest"] = payload["work_spec_digest"]
    trace["substitutions"] = applied

    declared = [
        {"kind": key, "value": value}
        for key, value in substitutions.items()
        if key != "allow_digest_mismatch" and key != "removed_event_seq"
    ]
    if substitutions.get("allow_digest_mismatch"):
        declared.append({"kind": "allow_digest_mismatch", "value": True})
    trace["declared_substitutions"] = declared
    return trace