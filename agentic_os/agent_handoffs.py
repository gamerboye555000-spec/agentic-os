"""U-A3 governed agent handoffs: creation, the append-only transition engine,
successor-created supersession, record hashes, the no-laundering verification
gate, reads and read-only verification.

Contract: agentic-os-v0.4-u-a3-routing-handoffs-contract.md §11-16, §19.

A governed handoff is a human-authored delegation *declaration* between two
logical agent identities. It records an objective, expected evidence,
participant passport pins and a human lifecycle decision, and may reference an
advisory routing plan. It grants no authority, executes nothing, schedules
nothing, authenticates no agent, installs nothing, and does not complete a
task. Every write is a human-invoked verb; the actor is always
`ops.ACTOR_HUMAN`.

Two write owners live here, each owning exactly one `db.transaction` boundary
whose first statement is `BEGIN IMMEDIATE` (write lock before the re-reads):

- `create_handoff` validates syntactically outside the transaction, re-reads
  every fact inside it, gates the participants/plan/predecessor, pins both
  passport facts, appends the successor as `proposed` with an empty transition
  chain via the `_PENDING_HASH` two-step (§12.3), and — when superseding —
  atomically transitions the predecessor to `superseded`.
- `transition` is the accept/refuse/clarify/cancel engine: it re-reads the
  handoff, runs the no-laundering gate, compare-and-swaps the state, appends
  one immutable transition row and moves the mutable
  `state`/`updated_at`/`content_sha256` projection together with exactly one
  event.

`get_handoff`, `get_transitions`, `list_handoffs`, `handoff_public`,
`verify_handoff` and `successor_id` are read-only: they never write, rehash,
repair or emit, and verification never raises on damaged storage.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import sys

from . import db, events, ids, models, ops, passports, protocols, routing, utils
from .models import Agent, AgentHandoff, AgentHandoffTransition
from .ops import _PENDING_HASH
from .utils import AosError

#: Record-hash payload schemas — each names itself, house style (§11/§12.3).
HANDOFF_RECORD_SCHEMA = "aos.agent-handoff/v1"
HANDOFF_TRANSITION_RECORD_SCHEMA = "aos.agent-handoff-transition/v1"

#: The one event entity and its six actions (§19). `propose` is emitted by
#: creation; the four explicit verbs and the successor-created `supersede`
#: name the transition actions.
HANDOFF_ENTITY = "agent_handoff"
HANDOFF_ACTION_PROPOSE = "propose"

#: The explicit transition verbs `transition` accepts. `supersede` is NOT here:
#: it happens only inside `create_handoff --supersedes` (§14, §17). Membership
#: map only — consulted by key, never by position.
_EXPLICIT_VERBS = ("accept", "refuse", "clarify", "cancel")

#: The complete legal `(from_state, to_state)` edge set — the 11 pairs derived
#: from `models.AGENT_HANDOFF_TRANSITIONS`, matched by membership. The four
#: illegal pairs over the two enums are storage-refused by the CHECKs in
#: `agent_handoff_transitions` (§11); this mirror is what replay checks against.
_LEGAL_TRANSITION_EDGES = frozenset(
    (source, target)
    for sources, target in models.AGENT_HANDOFF_TRANSITIONS.values()
    for source in sources
)

#: The closed handoff-integrity verdict vocabulary (§19, doctor 39). This order
#: IS the canonical reporting order for `verify_handoff` and the no-laundering
#: refusal. Bounded by construction — no free prose ever escapes verification.
HANDOFF_VERIFY_CODES = (
    "malformed",
    "mismatch",
    "unhashable",
    "chain_gap",
    "chain_illegal",
    "state_divergent",
    "pin_mismatch",
    "reason_missing",
    "supersession_incoherent",
)

#: The frozen propose event payload allowlist (§19), the
#: catalog.EVENT_PAYLOAD_KEYS idiom. Ids, agent names (redacted at emit like
#: every U-A1 event), integer versions, 12-char passport-digest prefixes, the
#: classification enum and the optional supersedes id only. No `decision_id`,
#: no objective/constraint prose, no full hash. Secret metadata keys may also
#: appear, exactly as on every event.
PROPOSE_EVENT_KEYS = (
    "handoff",
    "task",
    "plan",
    "from_agent",
    "to_agent",
    "from_version",
    "to_version",
    "from_passport_sha256_prefix",
    "to_passport_sha256_prefix",
    "data_classification",
    "supersedes",
)

#: The frozen transition event payload allowlist (§19): ids, the sequence, the
#: two states and the optional closed reason code only. Never the note prose.
TRANSITION_EVENT_KEYS = (
    "handoff",
    "task",
    "seq",
    "from_state",
    "to_state",
    "reason_code",
)

#: Prose bounds (§13, §14). Objective mirrors the passport `mission` bound;
#: constraints share it; a transition note is half that.
_MAX_OBJECTIVE_CHARS = 4096
_MAX_CONSTRAINTS_CHARS = 4096
_MAX_NOTE_CHARS = 2048
_MIN_EVIDENCE_COUNT = 0
_MAX_EVIDENCE_COUNT = 32

DEFAULT_DATA_CLASSIFICATION = "internal"


class HandoffHashError(AosError):
    """A stored handoff/transition row cannot be hashed at all — a BLOB in a
    TEXT column, a non-integer id, a NULL where the record requires text.
    Distinct from a mismatch: the row holds something no honest write could
    have produced. Carries the field name only, never the value."""


# ---------------------------------------------------------------------------
# Record-hash construction (§12.3). Text fields bind by sha256 leaf, ints bind
# directly, content_sha256 is always excluded — the M2.6 discipline applied to
# the handoff records, exactly as routing applies it to plans.

def _digest(payload: dict) -> str:
    return hashlib.sha256(protocols.serialize_canonical(payload)).hexdigest()


def _req_int(value, field: str):
    if not isinstance(value, int) or isinstance(value, bool):
        raise HandoffHashError(f"handoff record {field} is not an integer")
    return value


def _opt_int(value, field: str):
    return None if value is None else _req_int(value, field)


def _req_text(value, field: str):
    if not isinstance(value, str):
        raise HandoffHashError(f"handoff record {field} is not text")
    return utils.sha256_text(value)


def _opt_text(value, field: str):
    return None if value is None else _req_text(value, field)


def handoff_payload(handoff: AgentHandoff, transition_chain: list[str]) -> dict:
    """The exact `aos.agent-handoff/v1` payload (§12.3). Binds every non-hash
    column plus the ordered chain of RECOMPUTED transition digests (`seq`
    order); excludes `content_sha256`."""
    return {
        "record_schema": HANDOFF_RECORD_SCHEMA,
        "id": _req_int(handoff.id, "id"),
        "task_id": _req_int(handoff.task_id, "task_id"),
        "plan_id": _opt_int(handoff.plan_id, "plan_id"),
        "from_agent_id": _req_int(handoff.from_agent_id, "from_agent_id"),
        "to_agent_id": _req_int(handoff.to_agent_id, "to_agent_id"),
        "min_evidence_count": _req_int(
            handoff.min_evidence_count, "min_evidence_count"
        ),
        "decision_id": _opt_int(handoff.decision_id, "decision_id"),
        "from_passport_version": _req_int(
            handoff.from_passport_version, "from_passport_version"
        ),
        "to_passport_version": _req_int(
            handoff.to_passport_version, "to_passport_version"
        ),
        "supersedes_id": _opt_int(handoff.supersedes_id, "supersedes_id"),
        "actor_sha256": _req_text(handoff.actor, "actor"),
        "objective_md_sha256": _req_text(handoff.objective_md, "objective_md"),
        "expected_evidence_json_sha256": _req_text(
            handoff.expected_evidence_json, "expected_evidence_json"
        ),
        "constraints_md_sha256": _opt_text(handoff.constraints_md, "constraints_md"),
        "data_classification_sha256": _req_text(
            handoff.data_classification, "data_classification"
        ),
        "from_passport_sha256_sha256": _req_text(
            handoff.from_passport_sha256, "from_passport_sha256"
        ),
        "to_passport_sha256_sha256": _req_text(
            handoff.to_passport_sha256, "to_passport_sha256"
        ),
        "state_sha256": _req_text(handoff.state, "state"),
        "created_at_sha256": _req_text(handoff.created_at, "created_at"),
        "updated_at_sha256": _req_text(handoff.updated_at, "updated_at"),
        "transition_chain": list(transition_chain),
    }


def handoff_digest(handoff: AgentHandoff, transition_chain: list[str]) -> str:
    return _digest(handoff_payload(handoff, transition_chain))


def transition_payload(transition: AgentHandoffTransition) -> dict:
    """The exact `aos.agent-handoff-transition/v1` payload (§12.3). Binds every
    non-hash column; excludes `content_sha256`."""
    return {
        "record_schema": HANDOFF_TRANSITION_RECORD_SCHEMA,
        "id": _req_int(transition.id, "id"),
        "handoff_id": _req_int(transition.handoff_id, "handoff_id"),
        "seq": _req_int(transition.seq, "seq"),
        "from_state_sha256": _req_text(transition.from_state, "from_state"),
        "to_state_sha256": _req_text(transition.to_state, "to_state"),
        "actor_sha256": _req_text(transition.actor, "actor"),
        "reason_code_sha256": _opt_text(transition.reason_code, "reason_code"),
        "note_md_sha256": _opt_text(transition.note_md, "note_md"),
        "created_at_sha256": _req_text(transition.created_at, "created_at"),
    }


def transition_digest(transition: AgentHandoffTransition) -> str:
    return _digest(transition_payload(transition))


# ---------------------------------------------------------------------------
# Reads (§17). Never write, rehash, repair or emit.

def get_handoff(conn, handoff_id: int) -> AgentHandoff | None:
    row = conn.execute(
        "SELECT * FROM agent_handoffs WHERE id = ?", (handoff_id,)
    ).fetchone()
    return AgentHandoff.from_row(row) if row else None


def get_transitions(conn, handoff_id: int) -> list[AgentHandoffTransition]:
    """Every transition of a handoff, ordered by `seq` ascending — the domain's
    own ordering and the canonical chain order (§12.3)."""
    return [
        AgentHandoffTransition.from_row(row)
        for row in conn.execute(
            "SELECT * FROM agent_handoff_transitions WHERE handoff_id = ? "
            "ORDER BY seq",
            (handoff_id,),
        ).fetchall()
    ]


def _get_transition(conn, transition_id: int) -> AgentHandoffTransition:
    row = conn.execute(
        "SELECT * FROM agent_handoff_transitions WHERE id = ?", (transition_id,)
    ).fetchone()
    return AgentHandoffTransition.from_row(row)


def successor_id(conn, handoff_id: int) -> int | None:
    """The id of the one handoff that names `handoff_id` in `supersedes_id`, or
    None. `UNIQUE(supersedes_id)` makes the successor at most one — supersession
    chains are linear (§10, §14)."""
    row = conn.execute(
        "SELECT id FROM agent_handoffs WHERE supersedes_id = ?", (handoff_id,)
    ).fetchone()
    return row["id"] if row else None


def _agent_name(conn, agent_id: int) -> str:
    row = conn.execute(
        "SELECT name FROM agents WHERE id = ?", (agent_id,)
    ).fetchone()
    return row["name"] if row else f"agent #{agent_id}"


def _transition_chain(conn, handoff_id: int) -> list[str]:
    return [transition_digest(t) for t in get_transitions(conn, handoff_id)]


def _parse_evidence(text) -> list:
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        return []
    return value if isinstance(value, list) else []


# ---------------------------------------------------------------------------
# The no-laundering verification (§12.3, §19). Recompute every hash from
# columns, build the parent chain from the RECOMPUTED child digests so a
# tampered stored transition hash cannot launder itself into a valid chain,
# replay the transition history, and check supersession coherence.

def _replay(transitions: list[AgentHandoffTransition]) -> tuple[list[str], str]:
    """Replay the transition history from `proposed`. Returns
    `(problems, terminal_state)`: the closed replay codes and the state the
    chain ends in (`proposed` for an empty chain)."""
    problems: list[str] = []
    prev_to: str | None = None
    for index, transition in enumerate(transitions):
        if transition.seq != index + 1:
            problems.append("chain_gap")
        expected_from = "proposed" if index == 0 else prev_to
        if transition.from_state != expected_from:
            problems.append("chain_illegal")
        if (transition.from_state, transition.to_state) not in _LEGAL_TRANSITION_EDGES:
            problems.append("chain_illegal")
        if (
            transition.to_state in ("refused", "clarification_required")
            and not transition.reason_code
        ):
            problems.append("reason_missing")
        prev_to = transition.to_state
    terminal = transitions[-1].to_state if transitions else "proposed"
    return problems, terminal


def _pin_problems(conn, handoff: AgentHandoff) -> list[str]:
    """Whether both pinned passport rows still exist and their recomputed
    document digests still equal the stored pins (`pin_mismatch`), and whether
    a stored `supersedes_id` resolves (`supersession_incoherent`)."""
    problems: list[str] = []
    for agent_id, version, pin in (
        (handoff.from_agent_id, handoff.from_passport_version, handoff.from_passport_sha256),
        (handoff.to_agent_id, handoff.to_passport_version, handoff.to_passport_sha256),
    ):
        passport = passports.get_passport(conn, agent_id, version)
        if passport is None:
            problems.append("pin_mismatch")
            continue
        try:
            if passports.document_digest(passport.document) != pin:
                problems.append("pin_mismatch")
        except (passports.PassportHashError, protocols.ProtocolError):
            problems.append("pin_mismatch")
    if handoff.supersedes_id is not None and get_handoff(conn, handoff.supersedes_id) is None:
        problems.append("supersession_incoherent")
    return problems


def _structural_problems(
    conn, handoff: AgentHandoff, transitions: list[AgentHandoffTransition], *, check_pins: bool
) -> list[str]:
    """Every integrity problem with one handoff and its transition history, as
    closed verdict codes in canonical order. `check_pins` adds the read-time
    pin/reference checks (`verify_handoff`); the write gate omits them, because
    closing a record must stay possible after a participant moved (§14)."""
    problems: list[str] = []

    if not models.is_claim_hash(handoff.content_sha256):
        problems.append("malformed")

    recomputed: list[str] = []
    child_broken = False
    for transition in transitions:
        if not models.is_claim_hash(transition.content_sha256):
            problems.append("malformed")
            child_broken = True
            continue
        try:
            digest = transition_digest(transition)
        except HandoffHashError:
            problems.append("unhashable")
            child_broken = True
            continue
        recomputed.append(digest)
        if digest != transition.content_sha256:
            problems.append("mismatch")

    # Build the parent hash over the RECOMPUTED child digests, never the stored
    # ones — a tampered transition hash must not launder itself into the chain.
    if child_broken:
        problems.append("unhashable")
    elif models.is_claim_hash(handoff.content_sha256):
        try:
            if handoff_digest(handoff, recomputed) != handoff.content_sha256:
                problems.append("mismatch")
        except HandoffHashError:
            problems.append("unhashable")

    replay_problems, terminal = _replay(transitions)
    problems.extend(replay_problems)
    if handoff.state != terminal:
        problems.append("state_divergent")

    if (handoff.state == "superseded") != (successor_id(conn, handoff.id) is not None):
        problems.append("supersession_incoherent")

    if check_pins:
        problems.extend(_pin_problems(conn, handoff))

    seen = set(problems)
    return [code for code in HANDOFF_VERIFY_CODES if code in seen]


def _require_intact(conn, handoff: AgentHandoff) -> None:
    """The no-laundering write gate (§12.3 step 5): a handoff whose row hash or
    transition chain does not verify CANNOT receive a new transition on top —
    the write would launder the tamper. Refuses with the U-A1 message shape;
    never repairs, normalizes, overwrites or rehashes."""
    problems = _structural_problems(
        conn, handoff, get_transitions(conn, handoff.id), check_pins=False
    )
    if not problems:
        return
    ah = ids.render_id("agent_handoff", handoff.id)
    raise AosError(
        f"Refusing to change handoff {ah}: "
        + "; ".join(problems[:5])
        + ". The record was edited outside Agentic OS or is damaged; writing "
        "it now would overwrite the hashes and hide that. Nothing was changed. "
        "Run: python aos.py doctor — then see RECOVERY.md."
    )


def verify_handoff(conn, handoff_id: int) -> dict:
    """Verify one handoff and its transitions. Returns a bounded, value-free
    report: `ok` and a list of closed `problems`. Never raises on a damaged
    row, never writes, never rehashes (§ reads_and_verification)."""
    ah = ids.render_id("agent_handoff", handoff_id)
    row = conn.execute(
        "SELECT * FROM agent_handoffs WHERE id = ?", (handoff_id,)
    ).fetchone()
    if row is None:
        return {"handoff": ah, "ok": False, "problems": [f"{ah}: not_found"]}
    try:
        handoff = AgentHandoff.from_row(row)
        transitions = get_transitions(conn, handoff_id)
    except (TypeError, ValueError, KeyError):
        return {"handoff": ah, "ok": False, "problems": [f"{ah}: malformed"]}
    problems = _structural_problems(conn, handoff, transitions, check_pins=True)
    return {
        "handoff": ah,
        "ok": not problems,
        "problems": [f"{ah}: {code}" for code in problems],
    }


# ---------------------------------------------------------------------------
# Creation gates (§13). Each re-reads its fact inside the caller's
# BEGIN IMMEDIATE transaction and refuses without writing anything.

def _gate_participant(conn, name: str, role: str):
    """Re-read one participant and require it valid for creation, then pin and
    independently recompute its passport facts. No ownership, protection,
    system, catalog-origin or maturity advantage — the uniform §13 gate."""
    agent = passports.get_agent(conn, name)
    if agent is None:
        raise AosError(
            f"No agent '{name}' ({role}). Nothing was changed. "
            "Run: python aos.py agent list"
        )
    if agent.lifecycle != models.AGENT_LIFECYCLE_ACTIVE:
        raise AosError(
            f"Agent '{name}' ({role}) is {agent.lifecycle}; a handoff "
            "participant must be active at creation. Nothing was changed."
        )
    if agent.current_passport_version is None:
        raise AosError(
            f"Agent '{name}' ({role}) has no current published passport and "
            "cannot participate in a handoff. Nothing was changed."
        )
    if passports.agent_integrity(agent) != "ok" or passports.history_problems(conn, agent):
        raise AosError(
            f"Refusing to create a handoff with '{name}' ({role}): its "
            "identity or passport history is damaged. Nothing was changed. "
            "Run: python aos.py doctor — then see RECOVERY.md."
        )
    passport = passports.get_passport(conn, agent.id, agent.current_passport_version)
    if passport is None:
        raise AosError(
            f"Agent '{name}' ({role}) is missing its current passport row. "
            "Nothing was changed. Run: python aos.py doctor."
        )
    try:
        digest = passports.document_digest(passport.document)
    except (passports.PassportHashError, protocols.ProtocolError):
        raise AosError(
            f"Agent '{name}' ({role}) has an unhashable passport document. "
            "Nothing was changed. Run: python aos.py doctor."
        )
    return agent, agent.current_passport_version, digest, passport


def _gate_plan(conn, plan_id: int, task_id: int, recipient_id: int) -> None:
    """The optional advisory routing-plan gate (§13, §16). The plan must be
    intact, not stale, not superseded; its task must be NULL or equal the
    handoff's; and the recipient must be one of its *eligible* candidates. The
    sender need not be a candidate, and the plan is never read as authority."""
    rp = ids.render_id("routing_plan", plan_id)
    plan = routing.get_plan(conn, plan_id)
    if plan is None:
        raise AosError(
            f"No routing plan {rp} to reference. Nothing was changed. "
            "Run: python aos.py agent route list"
        )
    if not routing.verify_plan(conn, plan_id)["ok"]:
        raise AosError(
            f"Routing plan {rp} fails integrity verification and cannot back a "
            f"handoff. Nothing was changed. Run: python aos.py agent route "
            f"verify {rp} — then see RECOVERY.md."
        )
    staleness = routing.plan_staleness(conn, plan)
    if staleness.stale:
        who = staleness.agent or "an eligible agent"
        raise AosError(
            f"Routing plan {rp} is stale: agent '{who}' has changed since the "
            "plan was created. The plan remains inspectable history; nothing "
            "was changed. Create a fresh plan: python aos.py agent route plan ..."
        )
    if staleness.superseded:
        raise AosError(
            f"Routing plan {rp} has been superseded by {staleness.successor}; "
            "a superseded plan cannot back a handoff. Nothing was changed."
        )
    if plan.task_id is not None and plan.task_id != task_id:
        raise AosError(
            f"Routing plan {rp} is scoped to task "
            f"{ids.render_id('task', plan.task_id)}, not "
            f"{ids.render_id('task', task_id)}. Nothing was changed."
        )
    eligible = any(
        candidate.agent_id == recipient_id and candidate.verdict == "eligible"
        for candidate in routing.get_candidates(conn, plan_id)
    )
    if not eligible:
        raise AosError(
            f"The recipient is not an eligible candidate of routing plan {rp}; "
            "choose an eligible recipient or omit --plan. Nothing was changed."
        )


def _gate_supersede(conn, supersedes_id: int) -> AgentHandoff:
    """Re-read the predecessor (§16): it must exist, have no successor yet,
    verify intact, and be in a legal supersede source state
    (`proposed`/`clarification_required`/`accepted`). Terminal predecessors
    (`refused`/`cancelled`/`superseded`) refuse on this compare-and-swap."""
    ah = ids.render_id("agent_handoff", supersedes_id)
    predecessor = get_handoff(conn, supersedes_id)
    if predecessor is None:
        raise AosError(
            f"No handoff {ah} to supersede. Nothing was changed. "
            "Run: python aos.py agent handoff list"
        )
    existing = successor_id(conn, supersedes_id)
    if existing is not None:
        raise AosError(
            f"Handoff {ah} is already superseded by "
            f"{ids.render_id('agent_handoff', existing)}. Nothing was changed."
        )
    _require_intact(conn, predecessor)
    sources = models.AGENT_HANDOFF_TRANSITIONS["supersede"][0]
    if predecessor.state not in sources:
        raise AosError(
            f"Cannot supersede handoff {ah}: it is {predecessor.state}. "
            f"Legal from: {', '.join(sources)}. Nothing was changed."
        )
    return predecessor


def _require_current_participants(conn, handoff: AgentHandoff) -> None:
    """The accept-only current-pin gate (§12.3 step 7, §14). BOTH participants
    must still exist, be active, be integrity- and history-clean, and carry the
    exact pinned passport version and recomputed document digest. Accepting
    against a moved declaration refuses with the §10-style message; every other
    verb deliberately skips this so closing a record stays possible."""
    ah = ids.render_id("agent_handoff", handoff.id)
    for agent_id, pinned_version, pinned_digest in (
        (handoff.from_agent_id, handoff.from_passport_version, handoff.from_passport_sha256),
        (handoff.to_agent_id, handoff.to_passport_version, handoff.to_passport_sha256),
    ):
        row = conn.execute(
            "SELECT * FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()
        if row is None:
            raise _accept_moved(ah, f"agent #{agent_id}", "no longer exists")
        agent = Agent.from_row(row)
        if agent.lifecycle != models.AGENT_LIFECYCLE_ACTIVE:
            raise _accept_moved(ah, agent.name, f"is {agent.lifecycle}")
        if passports.agent_integrity(agent) != "ok" or passports.history_problems(conn, agent):
            raise _accept_moved(ah, agent.name, "has a damaged identity or history")
        if agent.current_passport_version != pinned_version:
            raise _accept_moved(
                ah,
                agent.name,
                f"changed since the handoff was created (pinned "
                f"v{pinned_version}, now v{agent.current_passport_version})",
            )
        passport = passports.get_passport(conn, agent_id, pinned_version)
        if passport is None:
            raise _accept_moved(ah, agent.name, "no longer has its pinned passport")
        try:
            digest = passports.document_digest(passport.document)
        except (passports.PassportHashError, protocols.ProtocolError):
            digest = None
        if digest != pinned_digest:
            raise _accept_moved(ah, agent.name, "pinned passport has changed")


def _accept_moved(ah: str, who: str, why: str) -> AosError:
    return AosError(
        f"Cannot accept handoff {ah}: participant '{who}' {why}. The handoff "
        "remains inspectable; nothing was changed. Re-create it against the "
        "current passports if the delegation still stands."
    )


# ---------------------------------------------------------------------------
# Syntactic validation (§13, §14). Runs OUTSIDE the transaction (D-v0.4.18).

def _validate_objective(value) -> str:
    if not isinstance(value, str):
        raise AosError("Handoff --objective must be text.")
    if not (1 <= len(value) <= _MAX_OBJECTIVE_CHARS):
        raise AosError(
            f"Handoff objective must be 1..{_MAX_OBJECTIVE_CHARS} characters."
        )
    return value


def _validate_constraints(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AosError("Handoff --constraints must be text.")
    if len(value) > _MAX_CONSTRAINTS_CHARS:
        raise AosError(
            f"Handoff constraints must be at most {_MAX_CONSTRAINTS_CHARS} "
            "characters."
        )
    return value


def _validate_expected_evidence(value) -> str:
    """Zero or more `models.EVIDENCE_KINDS`, duplicates refused, code-point
    sorted, stored as a canonical JSON array (empty allowed)."""
    if isinstance(value, str):
        raise AosError("Handoff expected evidence must be a list of evidence kinds.")
    items = list(value)
    seen: set[str] = set()
    for item in items:
        if item not in models.EVIDENCE_KINDS:
            raise AosError(
                f"Unknown evidence kind {item!r}. Allowed: "
                + "|".join(models.EVIDENCE_KINDS)
            )
        if item in seen:
            raise AosError(f"Handoff expected evidence contains a duplicate: {item!r}.")
        seen.add(item)
    return protocols.serialize_canonical(sorted(items)).decode("utf-8")


def _validate_min_evidence(value) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise AosError("Handoff --min-evidence must be an integer.")
    if not (_MIN_EVIDENCE_COUNT <= value <= _MAX_EVIDENCE_COUNT):
        raise AosError(
            f"Handoff min evidence count must be between {_MIN_EVIDENCE_COUNT} "
            f"and {_MAX_EVIDENCE_COUNT}."
        )
    return value


def _validate_classification(value) -> str:
    if value not in models.MEMORY_SENSITIVITIES:
        raise AosError(
            f"Unknown data classification {value!r}. Allowed: "
            + "|".join(models.MEMORY_SENSITIVITIES)
        )
    return value


def _validate_reason(verb: str, reason_code) -> str | None:
    """`refuse`/`clarify` require a closed reason code; `accept`/`cancel`
    reject a supplied one — the frozen contract permits none there (§14)."""
    if verb in ("refuse", "clarify"):
        if reason_code is None:
            raise AosError(
                f"'{verb}' requires --reason CODE. Allowed: "
                + "|".join(models.HANDOFF_REASON_CODES)
            )
        if reason_code not in models.HANDOFF_REASON_CODES:
            raise AosError(
                f"Unknown handoff reason code {reason_code!r}. Allowed: "
                + "|".join(models.HANDOFF_REASON_CODES)
            )
        return reason_code
    if reason_code is not None:
        raise AosError(f"'{verb}' does not take a --reason. Nothing was changed.")
    return None


def _validate_note(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AosError("Handoff --note must be text.")
    if len(value) > _MAX_NOTE_CHARS:
        raise AosError(
            f"Handoff note must be at most {_MAX_NOTE_CHARS} characters."
        )
    return value


def _classification_advisory(recipient_passport, data_classification: str, to_name: str) -> str | None:
    """The one-line advisory (§13, §15): if the recipient's pinned passport does
    not declare the handoff classification, expose it — never blocking, never
    stored, never in events, never altering eligibility."""
    try:
        document = protocols.parse_canonical(
            recipient_passport.document.encode("utf-8")
        )
    except (protocols.ProtocolError, UnicodeError):
        return None
    declared = document.get("data_classifications")
    if isinstance(declared, list) and data_classification in declared:
        return None
    return (
        f"ADVISORY: recipient '{to_name}' does not declare data classification "
        f"'{data_classification}' in its passport. This is advisory only — the "
        "handoff was created, routing stays advisory, and nothing was blocked."
    )


# ---------------------------------------------------------------------------
# The shared append primitive (§12.3). Insert one immutable transition with the
# _PENDING_HASH two-step, finalize its hash immediately, then move the mutable
# handoff projection (state/updated_at/content_sha256) together in ONE update
# whose digest is computed over the INTENDED new state — so no intermediate
# "state moved but hash didn't" row exists, even inside the transaction.

def _append_transition(
    conn, *, handoff: AgentHandoff, to_state: str, reason_code, note_md, actor: str, now: str
) -> int:
    seq = conn.execute(
        "SELECT COALESCE(MAX(seq), 0) + 1 FROM agent_handoff_transitions "
        "WHERE handoff_id = ?",
        (handoff.id,),
    ).fetchone()[0]
    transition_id = conn.execute(
        "INSERT INTO agent_handoff_transitions (handoff_id, seq, from_state, "
        "to_state, actor, reason_code, note_md, created_at, content_sha256) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (handoff.id, seq, handoff.state, to_state, actor, reason_code, note_md, now, _PENDING_HASH),
    ).lastrowid
    conn.execute(
        "UPDATE agent_handoff_transitions SET content_sha256 = ? WHERE id = ?",
        (transition_digest(_get_transition(conn, transition_id)), transition_id),
    )
    chain = _transition_chain(conn, handoff.id)
    projected = dataclasses.replace(handoff, state=to_state, updated_at=now)
    conn.execute(
        "UPDATE agent_handoffs SET state = ?, updated_at = ?, content_sha256 = ? "
        "WHERE id = ?",
        (to_state, now, handoff_digest(projected, chain), handoff.id),
    )
    return seq


def _emit_transition_event(
    conn, *, actor: str, handoff: AgentHandoff, action: str, seq: int,
    from_state: str, to_state: str, reason_code, secret_meta: dict | None
) -> None:
    payload = {
        "handoff": ids.render_id("agent_handoff", handoff.id),
        "task": ids.render_id("task", handoff.task_id),
        "seq": seq,
        "from_state": from_state,
        "to_state": to_state,
        "reason_code": reason_code,
    }
    if secret_meta:
        payload.update(secret_meta)
    events.emit(
        conn,
        actor=actor,
        entity=HANDOFF_ENTITY,
        entity_id=handoff.id,
        action=action,
        payload=payload,
    )


# ---------------------------------------------------------------------------
# Creation (§13, §16). One owner, one transaction boundary.

def create_handoff(
    conn,
    *,
    task_id: int,
    from_agent: str,
    to_agent: str,
    objective_md: str,
    plan_id: int | None = None,
    expected_evidence=(),
    min_evidence_count: int = 0,
    constraints_md: str | None = None,
    data_classification: str = DEFAULT_DATA_CLASSIFICATION,
    decision_id: int | None = None,
    supersedes_id: int | None = None,
    actor: str = ops.ACTOR_HUMAN,
) -> int:
    """Create one governed handoff and return its id (§13, §16).

    Validates syntactically outside the ONE `db.transaction` boundary, then
    inside `BEGIN IMMEDIATE`: re-reads the task (must exist, not `done`) and the
    optional decision; gates and pins both participants; validates the optional
    routing plan; resolves the optional predecessor; scans the objective and
    constraints; when superseding, appends the predecessor's `superseded`
    transition; inserts the successor as `proposed` with an empty transition
    chain via the `_PENDING_HASH` two-step; finalizes its hash; emits one
    `propose` event and, when superseding, one `supersede` event. Any exception
    rolls the whole boundary back — no rows, no events, no `_PENDING_HASH`
    survivor.
    """
    objective_md = _validate_objective(objective_md)
    constraints_md = _validate_constraints(constraints_md)
    evidence_json = _validate_expected_evidence(expected_evidence)
    min_evidence_count = _validate_min_evidence(min_evidence_count)
    data_classification = _validate_classification(data_classification)
    if from_agent == to_agent:
        raise AosError(
            "A handoff's sender and recipient must be different agents. "
            "Nothing was changed."
        )

    now = utils.utc_now_iso()
    warning: str | None = None
    advisory: str | None = None
    with db.transaction(conn):
        conn.execute("BEGIN IMMEDIATE")

        task = ops.get_task(conn, task_id)
        if task.status == "done":
            raise AosError(
                f"Task {ids.render_id('task', task.id)} is done; a handoff "
                "cannot delegate a task that is already closed. Nothing was "
                "changed."
            )

        if decision_id is not None and conn.execute(
            "SELECT 1 FROM decisions WHERE id = ?", (decision_id,)
        ).fetchone() is None:
            raise AosError(
                f"No decision {ids.render_id('decision', decision_id)} to "
                "reference. Nothing was changed."
            )

        sender, from_version, from_digest, _ = _gate_participant(
            conn, from_agent, "sender"
        )
        recipient, to_version, to_digest, recipient_passport = _gate_participant(
            conn, to_agent, "recipient"
        )
        if sender.id == recipient.id:
            raise AosError(
                "A handoff's sender and recipient must be different agents. "
                "Nothing was changed."
            )

        if plan_id is not None:
            _gate_plan(conn, plan_id, task.id, recipient.id)

        predecessor = None
        if supersedes_id is not None:
            predecessor = _gate_supersede(conn, supersedes_id)

        secret_meta, warning = ops._scan_trusted_write(
            "agent_handoff",
            [("objective", objective_md), ("constraint", constraints_md)],
        )
        advisory = _classification_advisory(
            recipient_passport, data_classification, recipient.name
        )

        supersede_event: tuple[AgentHandoff, str, int] | None = None
        if predecessor is not None:
            pred_from_state = predecessor.state
            pred_seq = _append_transition(
                conn,
                handoff=predecessor,
                to_state="superseded",
                reason_code=None,
                note_md=None,
                actor=actor,
                now=now,
            )
            supersede_event = (predecessor, pred_from_state, pred_seq)

        handoff_id = conn.execute(
            "INSERT INTO agent_handoffs (task_id, plan_id, from_agent_id, "
            "to_agent_id, actor, objective_md, expected_evidence_json, "
            "min_evidence_count, constraints_md, data_classification, "
            "decision_id, from_passport_version, from_passport_sha256, "
            "to_passport_version, to_passport_sha256, state, supersedes_id, "
            "created_at, updated_at, content_sha256) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                task.id,
                plan_id,
                sender.id,
                recipient.id,
                actor,
                objective_md,
                evidence_json,
                min_evidence_count,
                constraints_md,
                data_classification,
                decision_id,
                from_version,
                from_digest,
                to_version,
                to_digest,
                "proposed",
                supersedes_id,
                now,
                now,
                _PENDING_HASH,
            ),
        ).lastrowid

        handoff = get_handoff(conn, handoff_id)
        conn.execute(
            "UPDATE agent_handoffs SET content_sha256 = ? WHERE id = ?",
            (handoff_digest(handoff, []), handoff_id),
        )

        payload = {
            "handoff": ids.render_id("agent_handoff", handoff_id),
            "task": ids.render_id("task", task.id),
            "plan": ids.render_id("routing_plan", plan_id) if plan_id is not None else None,
            "from_agent": sender.name,
            "to_agent": recipient.name,
            "from_version": from_version,
            "to_version": to_version,
            "from_passport_sha256_prefix": models.hash_prefix(from_digest),
            "to_passport_sha256_prefix": models.hash_prefix(to_digest),
            "data_classification": data_classification,
            "supersedes": (
                ids.render_id("agent_handoff", supersedes_id)
                if supersedes_id is not None
                else None
            ),
        }
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=actor,
            entity=HANDOFF_ENTITY,
            entity_id=handoff_id,
            action=HANDOFF_ACTION_PROPOSE,
            payload=payload,
        )

        if supersede_event is not None:
            pred, pred_from_state, pred_seq = supersede_event
            _emit_transition_event(
                conn,
                actor=actor,
                handoff=pred,
                action="supersede",
                seq=pred_seq,
                from_state=pred_from_state,
                to_state="superseded",
                reason_code=None,
                secret_meta=None,
            )

    ops._warn_secret(warning)
    if advisory:
        print(advisory, file=sys.stderr)
    return handoff_id


# ---------------------------------------------------------------------------
# The transition engine (§14, §16). One owner, one transaction boundary; the
# four explicit verbs. `supersede` is internal to creation and never reachable
# here (there is no standalone supersede verb).

def transition(
    conn,
    handoff_id: int,
    verb: str,
    *,
    reason_code: str | None = None,
    note_md: str | None = None,
    actor: str = ops.ACTOR_HUMAN,
) -> None:
    """Apply one explicit lifecycle verb (`accept`/`refuse`/`clarify`/`cancel`)
    to a handoff (§14, §16).

    Validates the verb/reason/note outside the ONE `db.transaction` boundary,
    then inside `BEGIN IMMEDIATE`: re-reads the handoff, runs the no-laundering
    gate, compare-and-swaps the current state against the verb's legal sources
    (naming the state on refusal), runs the accept-only current-pin gate,
    appends one immutable transition, moves the `state`/`updated_at`/
    `content_sha256` projection in one update, and emits exactly one event. A
    repeat of a verb whose target already holds refuses ("already <state>")
    rather than silently succeeding.
    """
    if verb not in _EXPLICIT_VERBS:
        raise AosError(
            f"Unknown handoff verb {verb!r}. Allowed: {'|'.join(_EXPLICIT_VERBS)}"
        )
    sources, target = models.AGENT_HANDOFF_TRANSITIONS[verb]
    reason_code = _validate_reason(verb, reason_code)
    note_md = _validate_note(note_md)

    now = utils.utc_now_iso()
    warning: str | None = None
    with db.transaction(conn):
        conn.execute("BEGIN IMMEDIATE")

        handoff = get_handoff(conn, handoff_id)
        ah = ids.render_id("agent_handoff", handoff_id)
        if handoff is None:
            raise AosError(
                f"No handoff {ah}. Nothing was changed. "
                "Run: python aos.py agent handoff list"
            )

        _require_intact(conn, handoff)

        if handoff.state == target:
            raise AosError(
                f"Handoff {ah} is already {target}; nothing was changed."
            )
        if handoff.state not in sources:
            raise AosError(
                f"Cannot {verb} handoff {ah}: it is {handoff.state}. "
                f"Legal from: {', '.join(sources)}. Nothing was changed."
            )

        if verb == "accept":
            _require_current_participants(conn, handoff)

        secret_meta, warning = ops._scan_trusted_write(
            "agent_handoff", [("handoff_note", note_md)]
        )

        from_state = handoff.state
        seq = _append_transition(
            conn,
            handoff=handoff,
            to_state=target,
            reason_code=reason_code,
            note_md=note_md,
            actor=actor,
            now=now,
        )
        _emit_transition_event(
            conn,
            actor=actor,
            handoff=handoff,
            action=verb,
            seq=seq,
            from_state=from_state,
            to_state=target,
            reason_code=reason_code,
            secret_meta=secret_meta,
        )

    ops._warn_secret(warning)


# ---------------------------------------------------------------------------
# List and show projections (§17, §15). `list` placeholders restricted prose;
# `show` is administrative (full hashes, full prose, M2.6/M3.2 precedent).

def list_handoffs(conn, *, task_id: int | None = None, state: str | None = None) -> list[dict]:
    """Every handoff newest-first (§17), optionally filtered by task and/or
    state: id, task, from→to, state, created_at, classification, and an
    objective preview that a `restricted` row renders as
    `ops.RESTRICTED_PLACEHOLDER`."""
    clauses: list[str] = []
    params: list = []
    if task_id is not None:
        clauses.append("task_id = ?")
        params.append(task_id)
    if state is not None:
        clauses.append("state = ?")
        params.append(state)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM agent_handoffs{where} ORDER BY id DESC", params
    ).fetchall()
    listing = []
    for row in rows:
        handoff = AgentHandoff.from_row(row)
        restricted = handoff.data_classification == "restricted"
        listing.append(
            {
                "handoff": ids.render_id("agent_handoff", handoff.id),
                "task": ids.render_id("task", handoff.task_id),
                "from_agent": _agent_name(conn, handoff.from_agent_id),
                "to_agent": _agent_name(conn, handoff.to_agent_id),
                "state": handoff.state,
                "data_classification": handoff.data_classification,
                "objective": (
                    ops.RESTRICTED_PLACEHOLDER if restricted else handoff.objective_md
                ),
                "created_at": handoff.created_at,
            }
        )
    return listing


def handoff_public(conn, handoff: AgentHandoff) -> dict:
    """The complete `handoff show`/`--json` projection: the full record, the
    ordered transition history, and the read-only integrity verdict. Show-class,
    so full hashes and full prose appear even for a `restricted` handoff
    (administrative visibility, M3.2 precedent)."""
    verify = verify_handoff(conn, handoff.id)
    successor = successor_id(conn, handoff.id)
    return {
        "handoff": ids.render_id("agent_handoff", handoff.id),
        "task": ids.render_id("task", handoff.task_id),
        "plan": (
            ids.render_id("routing_plan", handoff.plan_id)
            if handoff.plan_id is not None
            else None
        ),
        "from_agent": _agent_name(conn, handoff.from_agent_id),
        "to_agent": _agent_name(conn, handoff.to_agent_id),
        "actor": handoff.actor,
        "objective": handoff.objective_md,
        "expected_evidence": _parse_evidence(handoff.expected_evidence_json),
        "min_evidence_count": handoff.min_evidence_count,
        "constraints": handoff.constraints_md,
        "data_classification": handoff.data_classification,
        "decision": (
            ids.render_id("decision", handoff.decision_id)
            if handoff.decision_id is not None
            else None
        ),
        "from_passport_version": handoff.from_passport_version,
        "from_passport_sha256": handoff.from_passport_sha256,
        "to_passport_version": handoff.to_passport_version,
        "to_passport_sha256": handoff.to_passport_sha256,
        "state": handoff.state,
        "supersedes": (
            ids.render_id("agent_handoff", handoff.supersedes_id)
            if handoff.supersedes_id is not None
            else None
        ),
        "superseded_by": (
            ids.render_id("agent_handoff", successor)
            if successor is not None
            else None
        ),
        "created_at": handoff.created_at,
        "updated_at": handoff.updated_at,
        "content_sha256": handoff.content_sha256,
        "integrity_ok": verify["ok"],
        "integrity_problems": verify["problems"],
        "transitions": [
            {
                "seq": transition.seq,
                "from_state": transition.from_state,
                "to_state": transition.to_state,
                "actor": transition.actor,
                "reason_code": transition.reason_code,
                "note": transition.note_md,
                "created_at": transition.created_at,
                "content_sha256": transition.content_sha256,
            }
            for transition in get_transitions(conn, handoff.id)
        ],
    }
