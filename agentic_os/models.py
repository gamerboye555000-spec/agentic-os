"""Enums, dataclasses, and row conversion. Closed enums reject unknown values."""

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
AGENT_KINDS = ("local", "cloud", "human", "generic")

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
    id: int
    name: str
    kind: str
    invoke_hint: str | None
    capabilities_json: str | None
    trust_level: int
    notes: str | None

    def capabilities(self) -> list[str]:
        """capabilities_json as a list of strings; malformed/absent → []."""
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
class Event(_Row):
    id: int
    ts: str
    actor: str
    entity: str
    entity_id: int | None
    action: str
    payload_json: str
