"""U-A1 governed agent registry: identity/passport hashes, the
no-laundering gate, and the domain operation behind every `agent` CLI verb.

Contract: agentic-os-v0.4-u-a1-agent-passports-contract.md

The shape of the unit, in three sentences. The `agents` row is the canonical
IDENTITY (name, class, scope, lifecycle) and carries a record hash like every
governed row since U-M2; `agent_passports` rows are IMMUTABLE versioned
declarations, each storing the exact canonical bytes of a valid
beast.agent-passport/v1 artifact. Everything a passport declares is inert
stored text: no resolver, router, executor, credential field or approval
grant exists in this unit, and no code path consumes `autonomy` for
anything. Every authoritative agent write walks the no-laundering gate first
— a corrupted identity or history cannot receive a new version on top; the
only exits are restore-from-backup or deliberate repair, both outside normal
commands.

Three hash bindings, one per substitution attack (the U-M2/M3 record-hash
discipline applied again):
- the document's own content digest (U-X1) — content tamper;
- the passport ROW hash, binding document digest to agent_id/version/status
  — status, timestamp and reparent tamper;
- the identity hash, binding the current-passport pointer and lifecycle to
  the identity — pointer and lifecycle tamper.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

from . import db, events, ops, protocols, utils
from .models import (
    AGENT_CLASSES,
    AGENT_LIFECYCLE_ACTIVE,
    AGENT_LIFECYCLE_DRAFT,
    AGENT_LIFECYCLE_REVOKED,
    AGENT_PASSPORT_DRAFT,
    AGENT_PASSPORT_PUBLISHED,
    CATALOG_ISSUER,
    Agent,
    AgentPassport,
    hash_prefix,
    is_claim_hash,
    validate_catalog_agent_name,
    validate_new_agent_name,
)
from .utils import AosError

#: The registry schema this unit stores documents of. One identity, pinned:
#: a stored document that names any other schema is a gate/doctor failure.
PASSPORT_PROTOCOL = "beast.agent-passport/v1"

#: The record-hash payload schemas (house style: each payload names itself,
#: so a valid hash cannot be replayed as a different record kind).
AGENT_IDENTITY_SCHEMA = "aos.agent-identity/v1"
PASSPORT_RECORD_SCHEMA = "aos.agent-passport-record/v1"

#: Defaults for a CLI-authored draft. "unspecified" is the operator's own
#: pending declaration, made immutable only at publish — never a fabricated
#: fact about anyone else's agent.
DEFAULT_ROLE = "unspecified"
DEFAULT_MISSION = "unspecified"
DEFAULT_AUTONOMY = "declare_only"
DEFAULT_ESCALATION = "ask_human"
#: The issuer a CLI-authored document carries. `human` is already this
#: system's actor vocabulary; a system issuer identity is U-A2's to mint.
CLI_ISSUER = "human"

#: The lifecycle transition table (U-A1 §6). Keys are CLI verbs; values are
#: (legal source states, target state). `revoked` appears in NO source set:
#: it is terminal, and `restore` refuses it with a fixed reason.
LIFECYCLE_TRANSITIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "suspend": (("active",), "suspended"),
    "archive": (("active", "suspended"), "archived"),
    "restore": (("suspended", "archived"), "active"),
    "revoke": (("active", "suspended", "archived"), "revoked"),
}

#: Lifecycle verbs `protected=1` refuses (plus discard). `restore` is absent
#: on purpose: it only ever un-parks, and a protected agent cannot have been
#: parked in the first place.
_PROTECTED_REFUSED = ("suspend", "archive", "revoke")

#: The closed integrity verdict vocabulary, extending U-M2's four with the
#: three history conditions a single row cannot express.
INTEGRITY_VERDICTS = (
    "ok",
    "malformed",
    "mismatch",
    "unhashable",
    "history_gap",
    "draft_shape",
    "pointer_invalid",
)

#: The envelope + identity fields a `--from-file` fragment must NOT carry:
#: they are CLI-owned at create time, and a fragment that smuggled one in
#: would be two authors disagreeing inside one declaration.
_FRAGMENT_FORBIDDEN = frozenset(
    {
        "schema",
        "protocol_version",
        "content_hash_alg",
        "content_sha256",
        "created_at",
        "issuer",
        "agent",
        "passport_version",
        "agent_scope",
        "provenance",
    }
)

#: Free-text passport fields the warn-on-write scan covers, as
#: (document key, TRUSTED_FIELD_LABELS label). Array fields are joined with
#: newlines before scanning, like capabilities always were.
_SCANNED_TEXT_FIELDS = (
    ("role", "role"),
    ("mission", "mission"),
    ("limitations", "limitation"),
    ("approvals_required", "approval"),
    ("task_families", "task_family"),
)


class PassportHashError(AosError):
    """An agent record's stored fields cannot be hashed at all.

    The U-M2 ClaimHashError condition, for the two agent record kinds.
    Carries `agent #id` / `agent passport #id` and the FIELD NAME only —
    never the value, whatever it is.
    """


def _hash_refusal(entity: str, record_id, field: str, why: str) -> PassportHashError:
    noun = "Agent" if entity == "agent" else "Agent passport"
    hid = (
        f"#{record_id}"
        if isinstance(record_id, int) and not isinstance(record_id, bool)
        else "row"
    )
    return PassportHashError(
        f"{noun} {hid} cannot be hashed: its {field} {why}. "
        "The row is damaged or was edited outside Agentic OS; it was not "
        "changed. Run: python aos.py doctor"
    )


def _text_leaf(value, field: str, record_id, *, entity: str, optional: bool = False):
    """Bind a stored text field by its sha256 digest, never by its raw text
    (the M2.6/D-v0.3.40 rule, applied to the agent records)."""
    if value is None:
        if optional:
            return None
        raise _hash_refusal(entity, record_id, field, "is NULL")
    if not isinstance(value, str):
        raise _hash_refusal(entity, record_id, field, "is not text")
    return utils.sha256_text(value)


def _int_leaf(value, field: str, record_id, *, entity: str, optional: bool = False):
    if value is None:
        if optional:
            return None
        raise _hash_refusal(entity, record_id, field, "is NULL")
    # bool is an int subclass; a stored True must not read as protected=1.
    if not isinstance(value, int) or isinstance(value, bool):
        raise _hash_refusal(entity, record_id, field, "is not an integer")
    if not (protocols.INT_MIN <= value <= protocols.INT_MAX):
        raise _hash_refusal(entity, record_id, field, "is outside the supported range")
    return value


def _digest(payload: dict) -> str:
    return hashlib.sha256(protocols.serialize_canonical(payload)).hexdigest()


# ---------------------------------------------------------------------------
# Identity hash (agents.content_sha256)

def agent_identity_payload(agent: Agent) -> dict:
    """The exact identity hash payload. Every semantically authoritative
    field is bound — including the five inert legacy columns, each optional,
    so tampering with carried history breaks the hash exactly as tampering
    with a governed field does. Only content_sha256 itself is excluded
    (what gets hashed never contains the hash)."""
    aid = agent.id
    text = lambda v, f, **kw: _text_leaf(v, f, aid, entity="agent", **kw)  # noqa: E731
    integer = lambda v, f, **kw: _int_leaf(v, f, aid, entity="agent", **kw)  # noqa: E731
    return {
        "identity_schema": AGENT_IDENTITY_SCHEMA,
        "id": integer(agent.id, "id"),
        "project_id": integer(agent.project_id, "project_id", optional=True),
        "protected": integer(agent.protected, "protected"),
        "current_passport_version": integer(
            agent.current_passport_version,
            "current_passport_version",
            optional=True,
        ),
        "trust_level": integer(agent.trust_level, "trust_level", optional=True),
        "name_sha256": text(agent.name, "name"),
        "agent_class_sha256": text(agent.agent_class, "agent_class"),
        "scope_sha256": text(agent.scope, "scope"),
        "lifecycle_sha256": text(agent.lifecycle, "lifecycle"),
        "owner_sha256": text(agent.owner, "owner"),
        "origin_sha256": text(agent.origin, "origin"),
        "created_at_sha256": text(agent.created_at, "created_at"),
        "updated_at_sha256": text(agent.updated_at, "updated_at"),
        "kind_sha256": text(agent.kind, "kind", optional=True),
        "invoke_hint_sha256": text(agent.invoke_hint, "invoke_hint", optional=True),
        "capabilities_json_sha256": text(
            agent.capabilities_json, "capabilities_json", optional=True
        ),
        "notes_sha256": text(agent.notes, "notes", optional=True),
    }


def agent_identity_digest(agent: Agent) -> str:
    return _digest(agent_identity_payload(agent))


def agent_integrity(agent: Agent) -> str:
    """'ok' · 'malformed' · 'mismatch' · 'unhashable'. Never raises, never
    reveals a value — a damaged identity must be REPORTABLE."""
    if not is_claim_hash(agent.content_sha256):
        return "malformed"
    try:
        digest = agent_identity_digest(agent)
    except PassportHashError:
        return "unhashable"
    return "ok" if digest == agent.content_sha256 else "mismatch"


# ---------------------------------------------------------------------------
# Passport row hash (agent_passports.content_sha256)

def document_digest(document_text) -> str:
    """The stored document's own U-X1 content digest, RECOMPUTED from its
    body — never trusted from the content_sha256 field inside it, which is
    the thing an attacker would edit."""
    if not isinstance(document_text, str):
        raise _hash_refusal("agent_passport", None, "document", "is not text")
    return protocols.content_digest(
        protocols.parse_canonical(document_text.encode("utf-8"))
    )


def passport_record_payload(passport: AgentPassport) -> dict:
    pid = passport.id
    text = lambda v, f, **kw: _text_leaf(  # noqa: E731
        v, f, pid, entity="agent_passport", **kw
    )
    integer = lambda v, f, **kw: _int_leaf(  # noqa: E731
        v, f, pid, entity="agent_passport", **kw
    )
    try:
        doc_sha = document_digest(passport.document)
    except protocols.ProtocolError:
        # An unparseable document has no digest; the row hash over it is
        # therefore uncomputable. The document itself is reported by the
        # history check, value-free, as `malformed`.
        raise _hash_refusal(
            "agent_passport", pid, "document", "cannot be parsed"
        ) from None
    return {
        "record_schema": PASSPORT_RECORD_SCHEMA,
        "id": integer(passport.id, "id"),
        "agent_id": integer(passport.agent_id, "agent_id"),
        "version": integer(passport.version, "version"),
        "document_sha256": doc_sha,
        "status_sha256": text(passport.status, "status"),
        "created_at_sha256": text(passport.created_at, "created_at"),
        "published_at_sha256": text(
            passport.published_at, "published_at", optional=True
        ),
    }


def passport_record_digest(passport: AgentPassport) -> str:
    return _digest(passport_record_payload(passport))


def passport_integrity(passport: AgentPassport) -> str:
    if not is_claim_hash(passport.content_sha256):
        return "malformed"
    try:
        digest = passport_record_digest(passport)
    except PassportHashError:
        return "unhashable"
    return "ok" if digest == passport.content_sha256 else "mismatch"


# ---------------------------------------------------------------------------
# Reads

def get_agent(conn: sqlite3.Connection, name: str) -> Agent | None:
    row = conn.execute("SELECT * FROM agents WHERE name = ?", (name,)).fetchone()
    return Agent.from_row(row) if row else None


def list_passports(conn: sqlite3.Connection, agent_id: int) -> list[AgentPassport]:
    return [
        AgentPassport.from_row(row)
        for row in conn.execute(
            "SELECT * FROM agent_passports WHERE agent_id = ? ORDER BY version",
            (agent_id,),
        ).fetchall()
    ]


def get_passport(
    conn: sqlite3.Connection, agent_id: int, version: int
) -> AgentPassport | None:
    row = conn.execute(
        "SELECT * FROM agent_passports WHERE agent_id = ? AND version = ?",
        (agent_id, version),
    ).fetchone()
    return AgentPassport.from_row(row) if row else None


def _project_slug(conn: sqlite3.Connection, project_id) -> str | None:
    if project_id is None:
        return None
    project = ops.get_project(conn, project_id)
    return project.slug if project else None


def agent_public(conn: sqlite3.Connection, agent: Agent) -> dict:
    """The --json shape for `agent show` (show-class output: full hashes are
    permitted here and only here, per the M2.6 rule)."""
    public: dict = {
        "name": agent.name,
        "agent_class": agent.agent_class,
        "scope": agent.scope,
        "project": _project_slug(conn, agent.project_id),
        "lifecycle": agent.lifecycle,
        "protected": bool(agent.protected),
        "owner": agent.owner,
        "origin": agent.origin,
        "current_passport_version": agent.current_passport_version,
        "created_at": agent.created_at,
        "updated_at": agent.updated_at,
        "content_sha256": agent.content_sha256,
        "integrity": agent_integrity(agent),
        "passports": [
            {
                "version": passport.version,
                "status": passport.status,
                "created_at": passport.created_at,
                "published_at": passport.published_at,
                "content_sha256": passport.content_sha256,
                "integrity": passport_integrity(passport),
            }
            for passport in list_passports(conn, agent.id)
        ],
    }
    if agent.origin == "legacy":
        public["legacy"] = {
            "kind": agent.kind,
            "invoke_hint": agent.invoke_hint,
            "capabilities": agent.capabilities(),
            "trust_level": agent.trust_level,
            "notes": agent.notes,
        }
    return public


def list_agents(
    conn: sqlite3.Connection,
    *,
    include_all: bool = False,
    project_slug: str | None = None,
) -> list[dict]:
    """Rows for `agent list`. Archived and revoked agents are history and
    hidden by default; `--all` shows them. Suspended stays visible — it is a
    status flag, not an exit from the registry."""
    clauses, params = [], []
    if not include_all:
        clauses.append("lifecycle NOT IN ('archived', 'revoked')")
    if project_slug is not None:
        project = ops.get_project_by_slug(conn, project_slug)
        if project is None:
            raise AosError(
                f"No project '{project_slug}'. Run: python aos.py project add "
                f"{project_slug} --name ... --repo ..."
            )
        clauses.append("project_id = ?")
        params.append(project.id)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM agents{where} ORDER BY name", params
    ).fetchall()
    result = []
    for row in rows:
        agent = Agent.from_row(row)
        result.append(
            {
                "name": agent.name,
                "agent_class": agent.agent_class,
                "scope": agent.scope,
                "project": _project_slug(conn, agent.project_id),
                "lifecycle": agent.lifecycle,
                "origin": agent.origin,
                "current_passport_version": agent.current_passport_version,
            }
        )
    return result


def export_document(
    conn: sqlite3.Connection, name: str, version: int | None = None
) -> str:
    """The stored canonical document text for `agent export`.

    Default: the current published version. A draft is exported only via an
    explicit --version — it is the operator's own pending declaration, and
    the printed bytes are identical to what publish would freeze.
    """
    agent = _require_agent(conn, name)
    if version is None:
        if agent.current_passport_version is None:
            drafts = [
                p
                for p in list_passports(conn, agent.id)
                if p.status == AGENT_PASSPORT_DRAFT
            ]
            hint = (
                f" A draft exists: python aos.py agent export {name} "
                f"--version {drafts[0].version}"
                if drafts
                else ""
            )
            raise AosError(
                f"Agent '{name}' has no published passport.{hint}"
            )
        version = agent.current_passport_version
    passport = get_passport(conn, agent.id, version)
    if passport is None:
        raise AosError(
            f"Agent '{name}' has no passport version {version}. "
            f"Run: python aos.py agent passport history {name}"
        )
    if not isinstance(passport.document, str):
        raise AosError(
            f"Agent '{name}' passport v{version} document is damaged; "
            "refusing to export it. Run: python aos.py doctor"
        )
    return passport.document


# ---------------------------------------------------------------------------
# History verification + the no-laundering gate

def _document_problems(agent: Agent, passport: AgentPassport) -> list[str]:
    """Reason-coded problems with one stored document. Value-free: verdicts
    from the closed vocabulary, never document content."""
    if not isinstance(passport.document, str):
        return [f"v{passport.version}: document unhashable"]
    try:
        document = protocols.parse_canonical(passport.document.encode("utf-8"))
        entry = protocols.validate_document(document)
    except protocols.ProtocolError:
        return [f"v{passport.version}: document malformed"]
    problems = []
    if entry.identity != PASSPORT_PROTOCOL:
        problems.append(f"v{passport.version}: document mismatch")
        return problems
    if document.get("agent") != agent.name:
        problems.append(f"v{passport.version}: document mismatch")
    if document.get("passport_version") != passport.version:
        problems.append(f"v{passport.version}: document mismatch")
    return problems


def history_problems(conn: sqlite3.Connection, agent: Agent) -> list[str]:
    """Every structural problem with an agent's passport history, as bounded
    reason-coded strings (`v<N>: <verdict>` / bare verdicts). Empty means the
    history is intact. Shared by the write gate and doctor check 33."""
    problems: list[str] = []
    passports = list_passports(conn, agent.id)

    expected = 1
    for passport in passports:
        if passport.version != expected:
            problems.append("history_gap")
            break
        expected += 1

    drafts = [p for p in passports if p.status == AGENT_PASSPORT_DRAFT]
    if len(drafts) > 1:
        problems.append("draft_shape")
    elif drafts:
        draft = drafts[0]
        if draft.version != 1 or agent.lifecycle != AGENT_LIFECYCLE_DRAFT:
            problems.append("draft_shape")

    pointer = agent.current_passport_version
    if pointer is not None:
        target = next((p for p in passports if p.version == pointer), None)
        if target is None or target.status != AGENT_PASSPORT_PUBLISHED:
            problems.append("pointer_invalid")

    for passport in passports:
        verdict = passport_integrity(passport)
        if verdict != "ok":
            problems.append(f"v{passport.version}: {verdict}")
            continue
        problems.extend(_document_problems(agent, passport))
    return problems


def verify_before_write(conn: sqlite3.Connection, agent: Agent) -> None:
    """The no-laundering gate (U-A1 §9). Every authoritative agent write
    calls this first, inside its transaction: a corrupted identity or
    history CANNOT receive a new version, publication or lifecycle change on
    top — the mutation would quietly bless the tampering. Names the agent
    and closed reason codes only."""
    identity = agent_integrity(agent)
    problems = ([] if identity == "ok" else [f"identity {identity}"])
    problems += history_problems(conn, agent)
    if not problems:
        return
    raise AosError(
        f"Refusing to change agent '{agent.name}': "
        + "; ".join(problems[:5])
        + ". The record was edited outside Agentic OS or is damaged; "
        "writing it now would overwrite the hashes and hide that. Nothing "
        "was changed. Run: python aos.py doctor — then see RECOVERY.md."
    )


def _rehash_agent(conn: sqlite3.Connection, agent_id: int) -> None:
    """Recompute and store the identity hash. MUST run inside the same
    transaction as the change that made it necessary (the claim-rehash
    pattern)."""
    row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    digest = agent_identity_digest(Agent.from_row(row))
    conn.execute(
        "UPDATE agents SET content_sha256 = ? WHERE id = ?", (digest, agent_id)
    )


def _rehash_passport(conn: sqlite3.Connection, passport_id: int) -> None:
    row = conn.execute(
        "SELECT * FROM agent_passports WHERE id = ?", (passport_id,)
    ).fetchone()
    digest = passport_record_digest(AgentPassport.from_row(row))
    conn.execute(
        "UPDATE agent_passports SET content_sha256 = ? WHERE id = ?",
        (digest, passport_id),
    )


# ---------------------------------------------------------------------------
# Document authoring / acceptance

def _canonical_text(document: dict) -> str:
    """The exact storage form: canonical bytes, no trailing newline."""
    return protocols.serialize_canonical(document).decode("utf-8")


def _accept_document(document: dict) -> dict:
    """Registry-validate a passport document (structure, closed vocabularies,
    unknown-field refusal, cross-field scope rule, content hash). Everything
    in it is inert afterward: nothing is fetched, resolved or executed."""
    entry = protocols.validate_document(document)
    if entry.identity != PASSPORT_PROTOCOL:
        raise AosError(
            f"Expected a {PASSPORT_PROTOCOL} artifact, found "
            f"'{entry.identity}'. Nothing was changed."
        )
    return document


def _read_fragment(path) -> dict:
    """An inert JSON body fragment for `agent create --from-file`. Read under
    the U-X1 filesystem contract, parsed under its bounds, and refused if it
    tries to author a CLI-owned field."""
    fragment = protocols.parse_canonical(protocols.read_artifact_bytes(path))
    owned = sorted(set(fragment) & _FRAGMENT_FORBIDDEN)
    if owned:
        raise AosError(
            "--from-file fragment must not carry envelope or identity "
            f"field(s) the CLI authors: {', '.join(owned)}. Provide body "
            "declarations only (see: python aos.py protocol show "
            f"{PASSPORT_PROTOCOL})."
        )
    return fragment


def _sort_fragment_arrays(fragment: dict) -> dict:
    """CLI-authored documents write string arrays sorted, for determinism.
    Nothing is deduplicated — a repeated item stays repeated and is refused
    by uniqueItems, loudly."""
    sorted_fragment = {}
    for key, value in fragment.items():
        if isinstance(value, list) and all(isinstance(v, str) for v in value):
            sorted_fragment[key] = sorted(value)
        else:
            sorted_fragment[key] = value
    return sorted_fragment


def build_passport_document(
    *,
    agent_name: str,
    passport_version: int,
    agent_class: str,
    scope_level: str,
    project_slug: str | None,
    role: str,
    mission: str,
    method: str,
    fragment: dict | None = None,
) -> dict:
    """A CLI-authored draft document, validated before anything is stored."""
    agent_scope: dict = {"level": scope_level}
    if project_slug is not None:
        agent_scope["project"] = project_slug
    document: dict = dict(_sort_fragment_arrays(fragment or {}))
    document.update(
        {
            "schema": PASSPORT_PROTOCOL,
            "protocol_version": 1,
            "content_hash_alg": protocols.CONTENT_HASH_ALG,
            "created_at": utils.utc_now_iso(),
            "issuer": CLI_ISSUER,
            "agent": agent_name,
            "passport_version": passport_version,
            "agent_class": agent_class,
            "agent_scope": agent_scope,
            "role": role,
            "mission": mission,
            "provenance": {"created_by": "human", "method": method},
        }
    )
    document.setdefault("autonomy", DEFAULT_AUTONOMY)
    document.setdefault("escalation", DEFAULT_ESCALATION)
    document[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(document)
    return _accept_document(document)


def _scan_document_fields(document: dict, extra: list | None = None):
    """The warn-on-write secret scan over a passport's free-text fields
    (D-v0.2.15: the trusted boundary warns and marks, never blocks)."""
    fields: list[tuple[str, str | None]] = list(extra or [])
    for key, label in _SCANNED_TEXT_FIELDS:
        value = document.get(key)
        if isinstance(value, list):
            value = "\n".join(str(item) for item in value) or None
        fields.append((label, value if isinstance(value, str) else None))
    return ops._scan_trusted_write("agent", fields)


def _require_agent(conn: sqlite3.Connection, name: str) -> Agent:
    agent = get_agent(conn, name)
    if agent is None:
        raise AosError(f"No agent '{name}'. Run: python aos.py agent list")
    return agent


def _passport_prefix(document_text: str) -> str:
    """A bounded event-safe rendering of the stored document's digest."""
    try:
        return hash_prefix(document_digest(document_text))
    except (PassportHashError, protocols.ProtocolError):
        return "(none)"


# ---------------------------------------------------------------------------
# Writes (each: gate → domain rows → identity/row rehash → event, one
# transaction; warn-on-write scan output printed after commit)

def _insert_identity_and_draft(
    conn: sqlite3.Connection,
    *,
    name: str,
    agent_class: str,
    scope_level: str,
    project_id: int | None,
    origin: str,
    document: dict,
    secret_meta: dict | None,
) -> tuple[Agent, AgentPassport]:
    now = utils.utc_now_iso()
    document_text = _canonical_text(document)
    if len(document_text.encode("utf-8")) > protocols.MAX_ARTIFACT_BYTES:
        raise AosError(
            "Passport document exceeds the protocol size bound; nothing was "
            "changed."
        )
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO agents (name, agent_class, scope, project_id, "
            "lifecycle, protected, owner, origin, current_passport_version, "
            "created_at, updated_at, content_sha256) "
            "VALUES (?, ?, ?, ?, 'draft', 0, 'human', ?, NULL, ?, ?, '')",
            (name, agent_class, scope_level, project_id, origin, now, now),
        )
        agent_id = cursor.lastrowid
        passport_cursor = conn.execute(
            "INSERT INTO agent_passports (agent_id, version, status, "
            "created_at, published_at, document, content_sha256) "
            "VALUES (?, 1, 'draft', ?, NULL, ?, '')",
            (agent_id, now, document_text),
        )
        _rehash_passport(conn, passport_cursor.lastrowid)
        _rehash_agent(conn, agent_id)
        payload = {
            "agent": name,
            "agent_class": agent_class,
            "scope": scope_level,
            "origin": origin,
            "version": 1,
            "passport_sha256_prefix": _passport_prefix(document_text),
        }
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=ops.ACTOR_HUMAN,
            entity="agent",
            entity_id=agent_id,
            action=origin,
            payload=payload,
        )
    agent = get_agent(conn, name)
    return agent, get_passport(conn, agent.id, 1)


def _resolve_scope(
    conn: sqlite3.Connection, project_slug: str | None
) -> tuple[str, int | None]:
    """A project slug → (scope level, project id). The slug is resolved
    against THIS ledger's projects only, so a cross-project reference cannot
    exist. Scope is a filing statement — nothing in U-A1 reads it for
    authorization."""
    if project_slug is None:
        return "global", None
    project = ops.get_project_by_slug(conn, project_slug)
    if project is None:
        raise AosError(
            f"No project '{project_slug}'. Run: python aos.py project add "
            f"{project_slug} --name ... --repo ..."
        )
    return "project", project.id


def create_agent(
    conn: sqlite3.Connection,
    *,
    name: str,
    agent_class: str = "custom",
    project_slug: str | None = None,
    role: str | None = None,
    mission: str | None = None,
    fragment_path=None,
) -> tuple[Agent, AgentPassport]:
    """`agent create`: a DRAFT identity plus its draft v1 passport. Nothing
    is published — the identity becomes immutable history only at
    `agent passport publish`."""
    validate_new_agent_name(name)
    if agent_class not in AGENT_CLASSES:
        raise AosError(
            f"Unknown agent class {agent_class!r}. Allowed: "
            + "|".join(AGENT_CLASSES)
        )
    if get_agent(conn, name) is not None:
        raise AosError(
            f"Agent '{name}' already exists. "
            f"Run: python aos.py agent show {name}"
        )
    fragment = _read_fragment(fragment_path) if fragment_path is not None else {}
    # role/mission/agent_class may come from a flag or from the fragment, but
    # never both — two authors disagreeing inside one declaration is refused,
    # not resolved.
    for key, flag, given in (
        ("role", "--role", role is not None),
        ("mission", "--mission", mission is not None),
    ):
        if key in fragment and given:
            raise AosError(
                f"Pass {key} once: it is in the --from-file fragment AND as "
                f"{flag}. Nothing was changed."
            )
    if "agent_class" in fragment:
        fragment_class = fragment.pop("agent_class")
        if agent_class != "custom":
            raise AosError(
                "Pass agent_class once: it is in the --from-file fragment "
                "AND as --class. Nothing was changed."
            )
        agent_class = fragment_class
        if agent_class not in AGENT_CLASSES:
            raise AosError(
                "Unknown agent class in fragment. Allowed: "
                + "|".join(AGENT_CLASSES)
            )
    role = role if role is not None else fragment.pop("role", DEFAULT_ROLE)
    mission = (
        mission if mission is not None else fragment.pop("mission", DEFAULT_MISSION)
    )
    scope_level, project_id = _resolve_scope(conn, project_slug)
    document = build_passport_document(
        agent_name=name,
        passport_version=1,
        agent_class=agent_class,
        scope_level=scope_level,
        project_slug=project_slug,
        role=role,
        mission=mission,
        method="create",
        fragment=fragment,
    )
    secret_meta, secret_warning = _scan_document_fields(
        document, extra=[("name", name)]
    )
    agent, passport = _insert_identity_and_draft(
        conn,
        name=name,
        agent_class=agent_class,
        scope_level=scope_level,
        project_id=project_id,
        origin="create",
        document=document,
        secret_meta=secret_meta,
    )
    ops._warn_secret(secret_warning)
    return agent, passport


def import_agent(conn: sqlite3.Connection, path) -> tuple[Agent, AgentPassport]:
    """`agent import FILE`: a valid beast.agent-passport/v1 artifact → a
    DRAFT identity + draft v1 passport. The file is bytes → dict → refusal or
    rows: no URL is fetched, no referenced path opened, no requirement
    resolved, nothing executed."""
    document = protocols.parse_canonical(protocols.read_artifact_bytes(path))
    _accept_document(document)
    name = document["agent"]
    validate_new_agent_name(name)
    if get_agent(conn, name) is not None:
        raise AosError(
            f"Agent '{name}' already exists. "
            f"Run: python aos.py agent show {name}"
        )
    if document["passport_version"] != 1:
        raise AosError(
            "An imported passport must declare passport_version 1 — an "
            f"imported history cannot pretend depth (found "
            f"{document['passport_version']}). Nothing was changed."
        )
    agent_scope = document["agent_scope"]
    project_slug = agent_scope.get("project")
    scope_level, project_id = _resolve_scope(conn, project_slug)
    if scope_level != agent_scope["level"]:
        # Unreachable: the schema's cross-field rule pins project presence
        # to the level. Kept as a refusal, not an assert — fail closed.
        raise AosError("Passport scope is inconsistent; nothing was changed.")
    secret_meta, secret_warning = _scan_document_fields(
        document, extra=[("name", name)]
    )
    agent, passport = _insert_identity_and_draft(
        conn,
        name=name,
        agent_class=document["agent_class"],
        scope_level=scope_level,
        project_id=project_id,
        origin="import",
        document=document,
        secret_meta=secret_meta,
    )
    ops._warn_secret(secret_warning)
    return agent, passport


def publish_passport(
    conn: sqlite3.Connection, *, name: str, path=None
) -> tuple[Agent, AgentPassport]:
    """`agent passport publish NAME [--file F]`.

    Without --file: publish the pending v1 draft (draft agent → active).
    With --file: accept a new declaration as version N+1 on an ACTIVE agent.
    Suspended, archived and revoked agents cannot gain versions — restore
    first; that a parked identity cannot quietly accumulate history is the
    point.
    """
    agent = _require_agent(conn, name)
    if agent.lifecycle == AGENT_LIFECYCLE_REVOKED:
        raise AosError(
            f"Agent '{name}' is revoked; revocation is permanent and it "
            "cannot gain passport versions."
        )
    if agent.lifecycle not in (AGENT_LIFECYCLE_DRAFT, AGENT_LIFECYCLE_ACTIVE):
        # A parked identity cannot quietly accumulate history: restoring it
        # first is the deliberate act that prevents laundering.
        raise AosError(
            f"Agent '{name}' is {agent.lifecycle}; a passport cannot be "
            "published for it. Restore it first: python aos.py agent "
            f"restore {name}"
        )
    verify_before_write(conn, agent)
    # A catalog identity's history is exclusively the catalog's (U-A2 §11).
    # Grafting a user-published version onto it would produce an ambiguous,
    # permanently un-upgradable half-ours/half-yours history, so this refuses
    # BEFORE the user's file is read, validated or stored — nothing about the
    # input can influence the outcome. The test is owner == 'system', NOT
    # `protected`: protection refuses lifecycle verbs for audit-critical
    # identities and says nothing about who authors a declaration, and a
    # human-owned protected agent must keep publishing exactly as it always
    # has.
    if agent.owner == "system":
        raise AosError(
            f"Agent '{name}' is catalog-managed (owner: system); its passport "
            "history is the built-in catalog's and cannot receive a published "
            "version from a file. Nothing was changed. To derive your own "
            "customized variant instead:\n"
            f"  python aos.py agent catalog show {name} --fragment > fragment.json\n"
            "  python aos.py agent create NEWNAME --from-file fragment.json"
        )
    now = utils.utc_now_iso()

    if path is None:
        drafts = [
            p
            for p in list_passports(conn, agent.id)
            if p.status == AGENT_PASSPORT_DRAFT
        ]
        if not drafts:
            raise AosError(
                f"Agent '{name}' has no pending draft to publish. Publish a "
                "new declaration from a file: python aos.py agent passport "
                f"publish {name} --file passport.json"
            )
        draft = drafts[0]
        secret_meta, secret_warning = _scan_document_fields(
            json.loads(draft.document), extra=[("name", name)]
        )
        from_lifecycle = agent.lifecycle
        with db.transaction(conn):
            conn.execute(
                "UPDATE agent_passports SET status = 'published', "
                "published_at = ? WHERE id = ?",
                (now, draft.id),
            )
            _rehash_passport(conn, draft.id)
            conn.execute(
                "UPDATE agents SET lifecycle = 'active', "
                "current_passport_version = ?, updated_at = ? WHERE id = ?",
                (draft.version, now, agent.id),
            )
            _rehash_agent(conn, agent.id)
            payload = {
                "agent": name,
                "version": draft.version,
                "passport_sha256_prefix": _passport_prefix(draft.document),
                "from_lifecycle": from_lifecycle,
                "to_lifecycle": AGENT_LIFECYCLE_ACTIVE,
            }
            if secret_meta:
                payload.update(secret_meta)
            events.emit(
                conn,
                actor=ops.ACTOR_HUMAN,
                entity="agent",
                entity_id=agent.id,
                action="publish",
                payload=payload,
            )
        ops._warn_secret(secret_warning)
        refreshed = get_agent(conn, name)
        return refreshed, get_passport(conn, refreshed.id, draft.version)

    # --file: version N+1 on an active agent.
    if agent.lifecycle == AGENT_LIFECYCLE_DRAFT:
        raise AosError(
            f"Agent '{name}' is a draft with a pending v1 passport. Publish "
            f"it first (python aos.py agent passport publish {name}) or "
            f"discard the draft (python aos.py agent discard {name})."
        )
    document = protocols.parse_canonical(protocols.read_artifact_bytes(path))
    _accept_document(document)
    if document["agent"] != name:
        raise AosError(
            f"The passport file declares agent '{document['agent']}', not "
            f"'{name}'. Nothing was changed."
        )
    versions = [p.version for p in list_passports(conn, agent.id)]
    next_version = (max(versions) if versions else 0) + 1
    if document["passport_version"] != next_version:
        raise AosError(
            f"The passport file declares passport_version "
            f"{document['passport_version']}; the next version for "
            f"'{name}' is {next_version}. Nothing was changed."
        )
    agent_scope = document["agent_scope"]
    scope_level, project_id = _resolve_scope(conn, agent_scope.get("project"))
    if scope_level != agent_scope["level"]:
        raise AosError("Passport scope is inconsistent; nothing was changed.")
    document_text = _canonical_text(document)
    secret_meta, secret_warning = _scan_document_fields(
        document, extra=[("name", name)]
    )
    from_lifecycle = agent.lifecycle
    with db.transaction(conn):
        cursor = conn.execute(
            "INSERT INTO agent_passports (agent_id, version, status, "
            "created_at, published_at, document, content_sha256) "
            "VALUES (?, ?, 'published', ?, ?, ?, '')",
            (agent.id, next_version, now, now, document_text),
        )
        _rehash_passport(conn, cursor.lastrowid)
        conn.execute(
            "UPDATE agents SET agent_class = ?, scope = ?, project_id = ?, "
            "current_passport_version = ?, updated_at = ? WHERE id = ?",
            (
                document["agent_class"],
                scope_level,
                project_id,
                next_version,
                now,
                agent.id,
            ),
        )
        _rehash_agent(conn, agent.id)
        payload = {
            "agent": name,
            "version": next_version,
            "passport_sha256_prefix": _passport_prefix(document_text),
            "from_lifecycle": from_lifecycle,
            "to_lifecycle": agent.lifecycle,
        }
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=ops.ACTOR_HUMAN,
            entity="agent",
            entity_id=agent.id,
            action="publish",
            payload=payload,
        )
    ops._warn_secret(secret_warning)
    refreshed = get_agent(conn, name)
    return refreshed, get_passport(conn, refreshed.id, next_version)


def transition_lifecycle(
    conn: sqlite3.Connection, *, name: str, verb: str
) -> Agent:
    """`agent suspend/archive/restore/revoke` — the state machine (U-A1 §6).
    Same-state and illegal transitions are refusals naming the current
    state, never silent no-ops (house style)."""
    sources, target = LIFECYCLE_TRANSITIONS[verb]
    agent = _require_agent(conn, name)
    if agent.lifecycle == AGENT_LIFECYCLE_REVOKED:
        raise AosError(
            f"Agent '{name}' is revoked; revocation is permanent and no "
            "command leaves it. The identity and its history remain on "
            "record."
        )
    if agent.protected and verb in _PROTECTED_REFUSED:
        raise AosError(
            f"Agent '{name}' is protected (protected_agent): "
            f"'{verb}' is refused for audit-critical identities. Nothing "
            "was changed."
        )
    if agent.lifecycle not in sources:
        raise AosError(
            f"Agent '{name}' is {agent.lifecycle}; '{verb}' applies only "
            f"to: {', '.join(sources)}. Nothing was changed."
        )
    verify_before_write(conn, agent)
    secret_meta, secret_warning = ops._scan_trusted_write(
        "agent", [("name", name)]
    )
    now = utils.utc_now_iso()
    with db.transaction(conn):
        conn.execute(
            "UPDATE agents SET lifecycle = ?, updated_at = ? WHERE id = ?",
            (target, now, agent.id),
        )
        _rehash_agent(conn, agent.id)
        payload = {
            "agent": name,
            "from_lifecycle": agent.lifecycle,
            "to_lifecycle": target,
        }
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=ops.ACTOR_HUMAN,
            entity="agent",
            entity_id=agent.id,
            action=verb,
            payload=payload,
        )
    ops._warn_secret(secret_warning)
    return get_agent(conn, name)


#: (table label, SQL, param builder) — every place a historical reference to
#: an agent — textual or by id — can live. Discard is legal only when all are
#: zero: a referenced identity is history, and history is archived or
#: revoked, never deleted. The `routing_plan_candidates` entry is name-joined
#: (U-A3 §21, MINOR-6): that table keys agents by id, but the join makes it
#: reachable through the existing name-only call signature (`lambda n: (n,)`)
#: without changing it — so a draft agent that appears as an `excluded`
#: candidate earns the normal historical-reference refusal instead of a raw
#: foreign-key IntegrityError.
_REFERENCE_QUERIES = (
    ("runs", "SELECT COUNT(*) FROM runs WHERE agent = ?", lambda n: (n,)),
    (
        "handoffs",
        "SELECT COUNT(*) FROM handoffs WHERE from_agent = ? OR to_agent = ?",
        lambda n: (n, n),
    ),
    (
        "evidence",
        "SELECT COUNT(*) FROM evidence WHERE provenance = ?",
        lambda n: (f"agent:{n}",),
    ),
    (
        "memory_sources",
        "SELECT COUNT(*) FROM memory_sources WHERE provenance = ?",
        lambda n: (f"agent:{n}",),
    ),
    (
        "routing_plan_candidates",
        "SELECT COUNT(*) FROM routing_plan_candidates c "
        "JOIN agents a ON a.id = c.agent_id WHERE a.name = ?",
        lambda n: (n,),
    ),
)


def discard_agent(conn: sqlite3.Connection, *, name: str) -> None:
    """`agent discard`: remove a never-used DRAFT (identity + its one draft
    passport). The only DELETE path in the system, and every guard below is
    what keeps it from ever deleting history. The discard event itself
    preserves the audit trail of the identity's existence."""
    agent = _require_agent(conn, name)
    if agent.origin not in ("create", "import"):
        raise AosError(
            f"Agent '{name}' is a migrated legacy identity and cannot be "
            "discarded. Archive it (python aos.py agent archive) or revoke "
            f"it (python aos.py agent revoke {name}) instead."
        )
    if agent.protected:
        raise AosError(
            f"Agent '{name}' is protected (protected_agent): discard is "
            "refused. Nothing was changed."
        )
    if agent.lifecycle != AGENT_LIFECYCLE_DRAFT:
        raise AosError(
            f"Agent '{name}' is {agent.lifecycle}; only a never-published "
            "draft can be discarded. Archive it (python aos.py agent "
            f"archive {name}) or revoke it (python aos.py agent revoke "
            f"{name}) instead."
        )
    if agent.current_passport_version is not None:
        raise AosError(
            f"Agent '{name}' has a published passport and cannot be "
            "discarded. Archive or revoke it instead."
        )
    passports = list_passports(conn, agent.id)
    if len(passports) != 1 or passports[0].version != 1 or (
        passports[0].status != AGENT_PASSPORT_DRAFT
    ):
        raise AosError(
            f"Agent '{name}' has passport history beyond a single pending "
            "draft and cannot be discarded. Archive or revoke it instead."
        )
    for label, sql, params in _REFERENCE_QUERIES:
        count = conn.execute(sql, params(name)).fetchone()[0]
        if count:
            raise AosError(
                f"Agent '{name}' is referenced by {count} {label} row(s) "
                "and cannot be discarded — historical references are never "
                "rewritten. Archive or revoke it instead."
            )
    verify_before_write(conn, agent)
    secret_meta, secret_warning = ops._scan_trusted_write(
        "agent", [("name", name)]
    )
    with db.transaction(conn):
        conn.execute(
            "DELETE FROM agent_passports WHERE id = ?", (passports[0].id,)
        )
        conn.execute("DELETE FROM agents WHERE id = ?", (agent.id,))
        payload = {"agent": name, "origin": agent.origin, "version": 1}
        if secret_meta:
            payload.update(secret_meta)
        events.emit(
            conn,
            actor=ops.ACTOR_HUMAN,
            entity="agent",
            entity_id=agent.id,
            action="discard",
            payload=payload,
        )
    ops._warn_secret(secret_warning)


# ---------------------------------------------------------------------------
# U-A2 catalog write primitives — TRANSACTION PARTICIPANTS
#
# The only passport writers in this module that do NOT own a transaction and
# do NOT emit an event. `catalog.install` owns exactly one boundary around
# the whole operation and emits one event per changed entry inside it.
#
# Why participants rather than self-contained writes (D-v0.4.18): db's
# transaction helper is `with conn:`, which COMMITS when it exits — so a
# nested one commits early. A primitive that opened its own would silently
# split `install --all`'s single rollback boundary into per-entry commits and
# produce exactly the partially-installed catalog §9 forbids. They therefore
# open nothing, commit nothing and roll back nothing; the caller's boundary is
# the only one, and `_require_caller_transaction` proves it is already open.
#
# These are NOT a general alternate passport API. They exist for one caller,
# so `install` can reuse U-A1's validation, hashing and no-laundering gate
# without nesting. Every ordinary human write above still owns its own
# transaction, unchanged.

#: The class every catalog identity carries. A catalog entry declares a
#: specialist role; nothing else is installable through this path.
CATALOG_AGENT_CLASS = "specialist"

#: The field values a catalog document is REQUIRED to bind, beyond its
#: agent/passport_version identity pair. Each is hash-bound inside the
#: document, so a document that disagrees with the catalog's provenance
#: cannot be stored under catalog ownership.
_CATALOG_BINDINGS: tuple[tuple[str, object], ...] = (
    ("issuer", CATALOG_ISSUER),
    ("agent_class", CATALOG_AGENT_CLASS),
    ("agent_scope", {"level": "global"}),
    ("autonomy", DEFAULT_AUTONOMY),
)


def _require_caller_transaction(conn: sqlite3.Connection, primitive: str) -> None:
    """Prove the caller's transaction is already OPEN.

    A programming error, not a user condition: it means a caller wrote rows
    outside the one boundary that would roll them back. Raised as RuntimeError
    (not AosError) so it surfaces as an internal failure (exit 2), never as a
    refusal a human could act on.

    `in_transaction` is only True once a statement has actually opened the
    transaction, so this REQUIRES the caller to have materially begun it (the
    `BEGIN IMMEDIATE` in catalog.install) rather than merely entered a `with`
    block — which is the stronger property, and the one that makes an
    in-transaction re-read atomic against another writer.
    """
    if not conn.in_transaction:
        raise RuntimeError(
            f"{primitive}() is a transaction participant and must be called "
            "inside the caller's already-open transaction: it opens, commits "
            "and rolls back nothing (D-v0.4.18)."
        )


def _accept_catalog_document(name: str, version: int, document_text: str) -> dict:
    """One catalog document → its validated dict, or a refusal.

    Walks the same `_accept_document` path `agent import` uses (D-v0.4.19: no
    catalog-specific reader is invented), then proves the document binds to
    the identity and provenance it is about to be stored under. Pure: no row
    is read or written here, so every caller can run it before its first
    INSERT.
    """
    if not isinstance(document_text, str):
        raise AosError(
            f"Catalog passport for '{name}' v{version} is not text; nothing "
            "was changed."
        )
    try:
        document = protocols.parse_canonical(document_text.encode("utf-8"))
    except protocols.ProtocolError:
        raise AosError(
            f"Catalog passport for '{name}' v{version} is not canonical JSON; "
            "nothing was changed."
        ) from None
    _accept_document(document)
    if _canonical_text(document) != document_text:
        raise AosError(
            f"Catalog passport for '{name}' v{version} is not in canonical "
            "storage form; nothing was changed."
        )
    if len(document_text.encode("utf-8")) > protocols.MAX_ARTIFACT_BYTES:
        raise AosError(
            f"Catalog passport for '{name}' v{version} exceeds the protocol "
            "size bound; nothing was changed."
        )
    for field, expected in (
        ("agent", name),
        ("passport_version", version),
    ) + _CATALOG_BINDINGS:
        if document.get(field) != expected:
            raise AosError(
                f"Catalog passport for '{name}' v{version} does not carry the "
                f"catalog's bound {field}; nothing was changed."
            )
    return document


def create_catalog_identity(
    conn: sqlite3.Connection,
    *,
    name: str,
    agent_class: str,
    documents,
) -> Agent:
    """Materialize one catalog identity and its COMPLETE published history.

    `documents` is an ordered sequence of (version, canonical document text)
    starting at 1 and contiguous — a fresh install replays the whole shipped
    history (D-v0.4.17), so it converges byte-for-byte with an upgrade chain
    to the same catalog version.

    Every validation completes before the first INSERT: a refusal here costs
    zero writes even though the caller's transaction would have rolled them
    back anyway.
    """
    _require_caller_transaction(conn, "create_catalog_identity")
    validate_catalog_agent_name(name)
    if agent_class != CATALOG_AGENT_CLASS:
        raise AosError(
            f"A catalog identity is always '{CATALOG_AGENT_CLASS}', not "
            f"{agent_class!r}. Nothing was changed."
        )
    if get_agent(conn, name) is not None:
        raise AosError(
            f"Agent '{name}' already exists and is not created again. "
            f"Run: python aos.py agent show {name}"
        )
    ordered = list(documents)
    if not ordered:
        raise AosError(
            f"Catalog entry '{name}' ships no passport version; nothing was "
            "changed."
        )

    accepted: list[tuple[int, str]] = []
    for expected_version, (version, document_text) in enumerate(ordered, start=1):
        if version != expected_version:
            raise AosError(
                f"Catalog history for '{name}' must be contiguous from v1; "
                "nothing was changed."
            )
        _accept_catalog_document(name, version, document_text)
        accepted.append((version, document_text))

    # Ownership, provenance and protection are set HERE and only here — the
    # three-way binding (owner + hash-bound issuer + digest match) that
    # `catalog.installed_state` re-derives is what proves catalog ownership
    # later; the name never does (D-v0.4.15).
    now = utils.utc_now_iso()
    cursor = conn.execute(
        "INSERT INTO agents (name, agent_class, scope, project_id, lifecycle, "
        "protected, owner, origin, current_passport_version, created_at, "
        "updated_at, content_sha256) "
        "VALUES (?, ?, 'global', NULL, 'active', 1, 'system', 'import', NULL, "
        "?, ?, '')",
        (name, CATALOG_AGENT_CLASS, now, now),
    )
    agent_id = cursor.lastrowid
    # The pointer starts NULL and is set after the rows it names exist: the
    # agents→agent_passports composite FK would refuse it in the other order.
    for version, document_text in accepted:
        passport_cursor = conn.execute(
            "INSERT INTO agent_passports (agent_id, version, status, "
            "created_at, published_at, document, content_sha256) "
            "VALUES (?, ?, 'published', ?, ?, ?, '')",
            (agent_id, version, now, now, document_text),
        )
        _rehash_passport(conn, passport_cursor.lastrowid)
    conn.execute(
        "UPDATE agents SET current_passport_version = ?, updated_at = ? "
        "WHERE id = ?",
        (accepted[-1][0], now, agent_id),
    )
    _rehash_agent(conn, agent_id)
    return get_agent(conn, name)


def append_catalog_version(
    conn: sqlite3.Connection,
    *,
    agent: Agent,
    version: int,
    document_text: str,
) -> Agent:
    """Append ONE immutable published version to a catalog identity.

    Strictly additive: no existing published row is updated or deleted, ever
    (U-A2 §9). Only the identity's pointer and hash move.
    """
    _require_caller_transaction(conn, "append_catalog_version")
    # The no-laundering gate first: a corrupted identity or history cannot
    # receive a new version on top, catalog-owned or not.
    verify_before_write(conn, agent)
    if (
        agent.owner != "system"
        or agent.protected != 1
        or agent.lifecycle != AGENT_LIFECYCLE_ACTIVE
        or agent.agent_class != CATALOG_AGENT_CLASS
        or agent.scope != "global"
        or agent.project_id is not None
    ):
        raise AosError(
            f"Agent '{agent.name}' is not a catalog-managed identity and "
            "cannot receive a catalog version. Nothing was changed."
        )

    history = list_passports(conn, agent.id)
    published = [p for p in history if p.status == AGENT_PASSPORT_PUBLISHED]
    if not published or len(published) != len(history):
        raise AosError(
            f"Agent '{agent.name}' does not carry a complete published "
            "catalog history. Nothing was changed."
        )
    max_installed = max(p.version for p in published)
    if agent.current_passport_version != max_installed:
        raise AosError(
            f"Agent '{agent.name}' has an incoherent current-passport "
            "pointer. Nothing was changed. Run: python aos.py doctor"
        )
    if version != max_installed + 1:
        raise AosError(
            f"Catalog version v{version} does not append to '{agent.name}': "
            f"the next version is v{max_installed + 1}. Nothing was changed."
        )
    _accept_catalog_document(agent.name, version, document_text)

    now = utils.utc_now_iso()
    cursor = conn.execute(
        "INSERT INTO agent_passports (agent_id, version, status, created_at, "
        "published_at, document, content_sha256) "
        "VALUES (?, ?, 'published', ?, ?, ?, '')",
        (agent.id, version, now, now, document_text),
    )
    _rehash_passport(conn, cursor.lastrowid)
    conn.execute(
        "UPDATE agents SET current_passport_version = ?, updated_at = ? "
        "WHERE id = ?",
        (version, now, agent.id),
    )
    _rehash_agent(conn, agent.id)
    return get_agent(conn, agent.name)
