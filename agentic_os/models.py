"""Enums, dataclasses, and row conversion. Closed enums reject unknown values.

Depends on `utils` and nothing else in the package, deliberately: this is the
domain vocabulary every other module is built on (`protocols` imports it for
the evidence/run enums), so it can import none of them back. The U-M2 claim
HASH therefore lives in `ops` — it needs U-X1's canonical serializer — while
the vocabulary it is expressed in stays here.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, fields

from .utils import AosError

TASK_STATUSES = ("inbox", "ready", "in_progress", "done")
TASK_KINDS = ("code", "research", "writing", "ops")
EVIDENCE_KINDS = ("note", "file", "commit", "test", "url", "command_output")
RUN_OUTCOMES = ("success", "partial", "fail", "unknown")
PACK_TARGETS = ("claude-code", "codex", "gemini", "generic")
MEMORY_SCOPES = ("global", "project")
MEMORY_KINDS = ("preference", "fact", "constraint", "summary")
MEMORY_CONFIDENCES = ("confirmed", "single", "inferred", "assumed")
#: U-M2 curation status. Closed here AND by a CHECK constraint in the schema:
#: the domain boundary and the storage boundary agree, so neither a careless
#: caller nor a direct SQL writer can invent a status. `proposed`,
#: `contested` and `quarantined` are storable for the U-M4 workflow; U-M2
#: ships no command that produces them.
MEMORY_STATUSES = ("proposed", "live", "contested", "quarantined", "retired")
#: The only status ordinary retrieval will look at (M2.7).
MEMORY_STATUS_LIVE = "live"
MEMORY_STATUS_RETIRED = "retired"

#: U-M3 sensitivity (M3.2, D-v0.3.31). Closed here AND by a CHECK constraint,
#: like every other memory vocabulary. This tuple is ORDERED, and the order is
#: authoritative: it is what "classification increases only" and "a source's
#: sensitivity must not exceed its claim's" are expressed in. Reordering it
#: would silently redefine both rules, so it is never sorted or rebuilt.
MEMORY_SENSITIVITIES = ("public", "internal", "confidential", "restricted")
#: The default (D-v0.3.32): `public` is a deliberate act of publication, not
#: something a claim falls into by omission.
MEMORY_SENSITIVITY_DEFAULT = "internal"
#: The level excluded from every automatic context surface (M3.2).
MEMORY_SENSITIVITY_RESTRICTED = "restricted"

#: U-M3 provenance sources (M3.3). `evidence` is structurally different from
#: every other kind: it names a ledger row, not an inert external string.
MEMORY_SOURCE_KINDS = (
    "evidence",
    "file",
    "url",
    "command",
    "human",
    "agent",
    "artifact",
)
MEMORY_SOURCE_KIND_EVIDENCE = "evidence"

#: How a source relates to a claim (M3.4). Descriptive only: U-M3 records what
#: the operator asserts and judges none of it.
MEMORY_SOURCE_RELATIONS = ("supports", "disputes", "context", "derived_from")

#: How one claim relates to another (M3.5). Note the absence of a supersession
#: relation: `memory.superseded_by` is the canonical lifecycle mechanism and
#: U-M3 does not duplicate it as a graph edge (D-v0.3.37).
MEMORY_EDGE_RELATIONS = (
    "supports",
    "contradicts",
    "refines",
    "depends_on",
    "related",
)
#: Symmetric relations: A↔B and B↔A are ONE logical edge, canonicalized as
#: lower memory id first (D-v0.3.36). The rest preserve their direction.
MEMORY_EDGE_SYMMETRIC = ("contradicts", "related")
#: A contradiction IS an active edge with this relation — there is no second
#: table and no verdict column (D-v0.3.38).
MEMORY_EDGE_CONTRADICTS = "contradicts"

#: The LEGACY v3 agent vocabulary. No v4 writer produces a `kind`; doctor
#: still uses this tuple to describe history (a legacy row whose kind falls
#: outside it is reported, never rewritten).
AGENT_KINDS = ("local", "cloud", "human", "generic")

# ---------------------------------------------------------------------------
# U-A1 governed agent registry vocabulary. Closed here AND by CHECK
# constraints in the schema (the U-M2 rule): neither a careless caller nor a
# direct SQL writer can invent a class, scope, lifecycle, owner or origin.

AGENT_CLASSES = ("system", "specialist", "custom", "temporary")
AGENT_SCOPES = ("global", "project")
AGENT_LIFECYCLES = ("draft", "active", "suspended", "archived", "revoked")
AGENT_OWNERS = ("human", "system")
AGENT_ORIGINS = ("legacy", "create", "import")

AGENT_LIFECYCLE_DRAFT = "draft"
AGENT_LIFECYCLE_ACTIVE = "active"
#: Terminal: no command leaves `revoked`, ever.
AGENT_LIFECYCLE_REVOKED = "revoked"

AGENT_PASSPORT_STATUSES = ("draft", "published")
AGENT_PASSPORT_DRAFT = "draft"
AGENT_PASSPORT_PUBLISHED = "published"

#: Reserved agent namespace (U-A1 rule 9/36): a NAMESPACE refusal at
#: create/import, never a set of rows — no row exists until U-A2's bootstrap
#: mints the system agents. Frozen tuples: reservation is vocabulary, not
#: configuration.
RESERVED_AGENT_PREFIXES = ("aos.", "beast.")
RESERVED_AGENT_NAMES = (
    "governor",
    "planner",
    "builder",
    "verifier",
    "security-sentinel",
)

#: Bound for NEW agent names only (create/import). Historical rows are
#: carried verbatim by the 3→4 migration whatever their length; doctor
#: reports out-of-vocabulary names without renaming history.
MAX_AGENT_NAME_CHARS = 64

#: All user-input validators anchor with \Z, never $ (D-v0.2.3) — '$' admits
#: a trailing newline, letting e.g. $'proj\n' become a slug (and a mirror
#: filename) that no equality lookup will ever find again.
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*\Z", re.ASCII)
PROVENANCE_RE = re.compile(r"^(human|agent:[A-Za-z0-9._-]+)\Z", re.ASCII)
#: Registry names must be referenceable as `agent:<name>` provenance AND be
#: safe stable note filenames — so: provenance charset, leading alnum.
AGENT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\Z", re.ASCII)


def validate_enum(value: str, allowed: tuple[str, ...], what: str) -> str:
    if value not in allowed:
        raise AosError(f"Unknown {what} {value!r}. Allowed: {'|'.join(allowed)}")
    return value


def sensitivity_rank(level: str) -> int:
    """Where `level` sits on the public → restricted ladder (M3.2).

    Raises rather than returning a sentinel: a caller comparing an unknown
    level would silently get an ordering answer, and every rule built on this
    (classify-increases-only, source-not-above-claim) would quietly weaken.
    """
    try:
        return MEMORY_SENSITIVITIES.index(level)
    except ValueError:
        raise AosError(
            f"Unknown memory sensitivity {level!r}. Allowed: "
            + "|".join(MEMORY_SENSITIVITIES)
        )


def validate_slug(slug: str) -> str:
    if not SLUG_RE.match(slug):
        raise AosError(
            f"Invalid project slug {slug!r}. Use lowercase letters, digits, "
            "'.', '_' or '-' (must start with a letter or digit)."
        )
    return slug


def validate_provenance(value: str) -> str:
    if not PROVENANCE_RE.match(value):
        raise AosError(
            f"Invalid provenance {value!r}. Use 'human' or 'agent:<name>'."
        )
    return value


def validate_agent_name(name: str) -> str:
    if not AGENT_NAME_RE.match(name):
        raise AosError(
            f"Invalid agent name {name!r}. Use letters, digits, '.', '_' "
            "or '-' (must start with a letter or digit)."
        )
    return name


def validate_new_agent_name(name: str) -> str:
    """The NEW-name rules (U-A1): charset, 64-char bound, reserved namespace.

    Applied only where a name enters the registry (`agent create`/`agent
    import`) — historical rows keep whatever they carry, and are reported by
    doctor rather than judged here.
    """
    validate_agent_name(name)
    if len(name) > MAX_AGENT_NAME_CHARS:
        raise AosError(
            f"Invalid agent name: longer than {MAX_AGENT_NAME_CHARS} "
            "characters."
        )
    if name in RESERVED_AGENT_NAMES or any(
        name.startswith(prefix) for prefix in RESERVED_AGENT_PREFIXES
    ):
        raise AosError(
            f"Agent name {name!r} is reserved for system agents "
            "(reserved names: " + ", ".join(RESERVED_AGENT_NAMES) + "; "
            "reserved prefixes: " + ", ".join(RESERVED_AGENT_PREFIXES) + ")."
        )
    return name


class _Row:
    @classmethod
    def from_row(cls, row: sqlite3.Row):
        data = dict(row)
        return cls(**{f.name: data[f.name] for f in fields(cls)})

    def as_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass
class Project(_Row):
    id: int
    slug: str
    name: str
    repo_path: str
    status: str
    autonomy_level: int
    conventions_md: str | None
    created_at: str
    updated_at: str


@dataclass
class Task(_Row):
    id: int
    project_id: int | None
    parent_id: int | None
    title: str
    kind: str
    status: str
    priority: int
    assignee: str | None
    spec_md: str | None
    acceptance_md: str | None
    branch_hint: str | None
    created_at: str
    updated_at: str
    closed_at: str | None


@dataclass
class Run(_Row):
    id: int
    task_id: int
    agent: str
    pack_id: int | None
    anchor_commit: str | None
    started_at: str
    ended_at: str | None
    outcome: str | None
    summary_md: str | None
    transcript_path: str | None


@dataclass
class Decision(_Row):
    id: int
    project_id: int | None
    task_id: int | None
    title: str
    decision_md: str
    alternatives_md: str | None
    status: str
    supersedes_id: int | None
    decided_at: str


@dataclass
class Evidence(_Row):
    id: int
    task_id: int
    run_id: int | None
    claim: str | None
    kind: str
    ref: str
    sha256: str | None
    provenance: str
    created_at: str
    verified: int


@dataclass
class Handoff(_Row):
    id: int
    task_id: int
    from_agent: str
    to_agent: str
    state_md: str
    pack_id: int | None
    created_at: str
    accepted_at: str | None


@dataclass
class MemoryItem(_Row):
    """A v3 memory claim. Every v1 field keeps its v1 meaning (D-v0.3.15):
    `kind` is the closed claim type, `key` the stable claim key/subject,
    `value_md` the human-readable claim value. U-M2 added curation state and
    U-M3 adds sensitivity — neither is a new data model."""

    id: int
    scope: str
    project_id: int | None
    kind: str
    key: str
    value_md: str
    source: str
    confidence: str
    valid_from: str
    valid_until: str | None
    superseded_by: int | None
    updated_at: str
    status: str
    pinned: int
    sensitivity: str
    content_sha256: str


@dataclass
class MemorySource(_Row):
    """A normalized provenance record (U-M3, M3.3).

    Deliberately holds no text copied from what it references (D-v0.3.34): an
    `evidence` source carries `evidence_id` and nothing else about that row;
    every other kind carries an INERT `locator` string that no command in this
    system ever opens, fetches or executes (D-v0.3.47).
    """

    id: int
    project_id: int | None
    source_kind: str
    evidence_id: int | None
    locator: str | None
    provenance: str
    sensitivity: str
    observed_at: str
    valid_from: str | None
    valid_until: str | None
    created_at: str
    content_sha256: str


@dataclass
class MemorySourceLink(_Row):
    """A claim↔source link (U-M3, M3.4). Two ids, a relation, a timestamp and
    a hash — never a copy of the source's or the claim's text."""

    id: int
    memory_id: int
    source_id: int
    relation: str
    created_at: str
    content_sha256: str


@dataclass
class MemoryEdge(_Row):
    """A typed claim↔claim relationship (U-M3, M3.5).

    Descriptive only: an edge triggers no workflow, resolves nothing, and
    decides nothing. A `contradicts` edge records that a human said two claims
    disagree — not which one is true (D-v0.3.38).
    """

    id: int
    from_memory_id: int
    to_memory_id: int
    relation: str
    valid_from: str | None
    valid_until: str | None
    created_at: str
    content_sha256: str


@dataclass
class Pack(_Row):
    id: int
    task_id: int
    path: str
    token_estimate: int
    inputs_hash: str
    created_at: str


@dataclass
class Agent(_Row):
    """A v4 governed agent identity (U-A1).

    The five legacy fields (kind, invoke_hint, capabilities_json,
    trust_level, notes) are v3 history carried verbatim by the 3→4
    migration — permanently inert, NULL on every new row, and read by
    nothing that grants behavior.
    """

    id: int
    name: str
    agent_class: str
    scope: str
    project_id: int | None
    lifecycle: str
    protected: int
    owner: str
    origin: str
    current_passport_version: int | None
    created_at: str
    updated_at: str
    kind: str | None
    invoke_hint: str | None
    capabilities_json: str | None
    trust_level: int | None
    notes: str | None
    content_sha256: str

    def capabilities(self) -> list[str]:
        """Legacy capabilities_json as a list of strings; malformed/absent
        → []. Display-only, like every other legacy field."""
        import json

        if not self.capabilities_json:
            return []
        try:
            value = json.loads(self.capabilities_json)
        except ValueError:
            return []
        if not isinstance(value, list):
            return []
        return [str(item) for item in value]


@dataclass
class AgentPassport(_Row):
    """One immutable passport version (U-A1).

    `document` is the exact canonical text of a valid
    beast.agent-passport/v1 artifact; `content_sha256` is the ROW record
    hash (the document's own digest lives inside the document). A published
    row is never updated or deleted.
    """

    id: int
    agent_id: int
    version: int
    status: str
    created_at: str
    published_at: str | None
    document: str
    content_sha256: str


@dataclass
class Event(_Row):
    id: int
    ts: str
    actor: str
    entity: str
    entity_id: int | None
    action: str
    payload_json: str


# ---------------------------------------------------------------------------
# Memory record hash vocabulary (U-M2 M2.6; U-M3 M3.6). The hashes THEMSELVES
# are computed in ops: they need U-X1's canonical serializer, and protocols
# imports this module, so the dependency can only run one way.

#: A record hash is exactly 64 lowercase hex characters. Uppercase, blank,
#: truncated and "sha256:"-prefixed spellings are malformed, not equivalent.
#: One spelling rule for all four U-M3 record kinds (claim, source, link,
#: edge) — a hash is a hash, and a second rule would only be a second thing
#: to get wrong.
CLAIM_HASH_RE = re.compile(r"^[0-9a-f]{64}\Z", re.ASCII)

#: Shown when a hash must be named in human output: enough to correlate two
#: lines, never enough to reconstruct anything (M2.6 — hashes are never
#: printed in full outside `memory show`).
HASH_PREFIX_CHARS = 12


def is_claim_hash(value: object) -> bool:
    return isinstance(value, str) and bool(CLAIM_HASH_RE.match(value))


def hash_prefix(value: object) -> str:
    """A bounded, safe rendering of a hash for events and diagnostics."""
    if not isinstance(value, str):
        return "(none)"
    return value[:HASH_PREFIX_CHARS] if value else "(blank)"


class ClaimHashError(AosError):
    """A memory record's stored fields cannot be hashed at all.

    Distinct from a mismatch: the row holds something no honest write could
    have produced (a BLOB in a TEXT column, a non-integer pin). Carries the
    record id and the FIELD NAME only — never the value, whatever it is.

    Raised for all four U-M3 record kinds. The name is U-M2's and stays: the
    condition it describes is identical for a source, a link and an edge, and
    four exception classes for one condition would only make callers choose.
    """
