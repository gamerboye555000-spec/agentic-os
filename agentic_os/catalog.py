"""U-A2 built-in specialist catalog: loader, verifier, read-only
installed-state/status/plan logic, and the explicit installer.

Contract: agentic-os-v0.4-u-a2-specialist-catalog-contract.md

Twelve inert `beast.agent-passport/v1` artifacts ship under
`agentic_os/catalog/`, indexed by a deterministic `manifest.json`. Every
declaration in them is INERT — nothing here reads `autonomy`,
`skill_requirements`, `tool_requirements` or `model_requirements` to grant
capability, spend, or execution; this module loads, verifies, reports
ledger-relative state, and installs when a human explicitly asks.

`install` is the ONLY writer in this unit and runs only from the explicit
`agent catalog install` leaf: no mode, no `init`, no `migrate apply`, no
`doctor` and no `sync` ever installs or upgrades an entry (U-A2 §2). It still
issues no INSERT/UPDATE/DELETE against `agents` or `agent_passports` itself —
every row is written through the two transaction-participating primitives in
`passports`, while this module owns the one transaction and the events, because
the rollback boundary must span the whole selected set (D-v0.4.18).
`installed_state`/`status`/`plan` only ever read existing rows.

Protection grants no execution or runtime authority: an installed identity is
a stored declaration and nothing reads `protected` for authorization.

Two read paths, two threat models, deliberately not merged: artifacts here
are read as PACKAGE RESOURCES (`importlib.resources`), never from the
current working directory and never fetched from a URL — the digest check
against the checked-in manifest is the integrity anchor, not filesystem
TOCTOU defenses (those govern `agent import FILE`'s untrusted user path in
`protocols.read_artifact_bytes`, unchanged and unrelated).

Loading is lazy and memoized: nothing here runs at package import time, and
the first successful load is cached for the process (`load_manifest`, an
`lru_cache`d function — tests that inject a corrupt or synthetic state call
`.cache_clear()` first, or exercise `_validate_manifest`/`load_document`
directly with synthetic data rather than through the cache).
"""

from __future__ import annotations

import functools
import importlib.resources
import re
import sqlite3
import stat
from dataclasses import dataclass
from pathlib import Path

from . import db, events, models, ops, passports, protocols, secretscan
from .utils import AosError

# ---------------------------------------------------------------------------
# Vocabulary

CATALOG_DIRNAME = "catalog"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_VERSION = 1
CATALOG_ISSUER = models.CATALOG_ISSUER
PASSPORT_PROTOCOL = passports.PASSPORT_PROTOCOL

CATEGORIES = ("design", "delivery", "assurance", "operations", "knowledge")
MATURITIES = ("stable", "provisional")

#: Sanity bounds on the manifest's own shape — domain-specific, on top of
#: (never a substitute for) protocols.parse_canonical's generic canonical-
#: JSON bounds (size, depth, member/item counts) already applied upstream.
MAX_ENTRIES = 64
MAX_VERSIONS_PER_ENTRY = 32

#: A catalog artifact's on-disk name is a pure function of identity:
#: `{agent}.v{n}.passport.json`. No '/', no '\\', no '..' can ever match —
#: the agent segment reuses AGENT_NAME_RE's charset (letters, digits, '.',
#: '_', '-'), so path traversal is refused by SHAPE, independent of the
#: manifest-entry binding check in _validate_manifest.
_PATH_RE = re.compile(
    r"^[a-z][a-z0-9._-]{0,63}\.v[1-9][0-9]{0,3}\.passport\.json\Z", re.ASCII
)
_HEX64_RE = re.compile(r"^[0-9a-f]{64}\Z", re.ASCII)

_MANIFEST_KEYS = frozenset(
    {
        "canonical_json",
        "catalog_version",
        "content_hash_alg",
        "content_sha256",
        "entries",
        "issuer",
        "manifest_version",
    }
)
_ENTRY_KEYS = frozenset({"agent", "category", "maturity", "versions"})
_VERSION_KEYS = frozenset({"document_sha256", "passport_version", "path"})

_SCANNED_TEXT_FIELDS = passports._SCANNED_TEXT_FIELDS

#: Closed reason vocabulary (mirrors protocols.ProtocolError's shape):
#: diagnostics are built ONLY from these codes plus a name/path/field —
#: never a document value, a full hash, or raw exception text.
_REASON_HINTS: dict[str, str] = {
    "unsafe_path": "not a recognized catalog artifact name",
    "missing": "the artifact is missing or unreadable",
    "unsafe_object": "the path is not a regular file",
    "too_large": f"the artifact exceeds {protocols.MAX_ARTIFACT_BYTES} bytes",
    "malformed": "not valid UTF-8 canonical JSON",
    "not_canonical": "the stored bytes are not the canonical form plus one trailing newline",
    "manifest_closed_keys": "carries an unknown, missing, or malformed field",
    "manifest_bad_vocab": "names an unknown category, maturity, or protocol constant",
    "manifest_sort_order": "entries are not sorted by agent",
    "manifest_duplicate": "repeats an agent, path, or digest",
    "manifest_version_gap": "versions are not contiguous from 1",
    "manifest_path_mismatch": "an entry's stored path does not match its derived name",
    "manifest_bad_hash": "carries a malformed content hash",
    "manifest_bad_agent": "names an agent outside the catalog namespace",
    "manifest_digest_mismatch": "the manifest's self-digest does not match its body",
    "document_digest_mismatch": "the artifact's digest does not match the manifest",
    "document_invalid": "not a valid beast.agent-passport/v1 document",
    "document_binding_mismatch": "does not carry the catalog's bound field values",
    "secret_shaped": "contains secret-shaped content",
}


class CatalogError(AosError):
    """A bounded, actionable, value-free catalog problem.

    Never claims a self-digest prevents deliberate editing — it detects
    corruption and projection drift. Git review and the ledger↔artifact
    comparison in `installed_state` are the real provenance anchors.
    """

    def __init__(self, reason: str, where: str = "") -> None:
        if reason not in _REASON_HINTS:
            raise KeyError(f"undeclared catalog reason code: {reason!r}")
        self.reason = reason
        self.where = where
        subject = f"{where}: " if where else ""
        super().__init__(f"catalog: {subject}{_REASON_HINTS[reason]}")


# ---------------------------------------------------------------------------
# Shapes

@dataclass(frozen=True)
class CatalogVersion:
    passport_version: int
    path: str
    document_sha256: str


@dataclass(frozen=True)
class CatalogEntry:
    agent: str
    category: str
    maturity: str
    versions: tuple[CatalogVersion, ...]

    @property
    def latest(self) -> CatalogVersion:
        return max(self.versions, key=lambda v: v.passport_version)


@dataclass(frozen=True)
class Catalog:
    catalog_version: int
    manifest_version: int
    issuer: str
    manifest_sha256: str
    entries: tuple[CatalogEntry, ...]

    def get(self, name: str) -> CatalogEntry | None:
        for entry in self.entries:
            if entry.agent == name:
                return entry
        return None

    def names(self) -> list[str]:
        return [entry.agent for entry in self.entries]


# ---------------------------------------------------------------------------
# Package-resource reads (never the CWD, never a URL)

def _resource(relpath: str) -> bytes:
    """Read one shipped file under agentic_os/catalog/, bounded and safe."""
    if relpath != MANIFEST_FILENAME and not _PATH_RE.fullmatch(relpath):
        raise CatalogError("unsafe_path", relpath)

    traversable = importlib.resources.files("agentic_os") / CATALOG_DIRNAME / relpath

    # Belt-and-suspenders over the digest check (the total defense either
    # way): when the resource backend exposes a real filesystem path, apply
    # the same regular-file discipline every other read in this codebase
    # does. A zipapp member has no such object to inspect — skip, rather
    # than assume a pathlib-only method exists on every Traversable.
    if isinstance(traversable, Path):
        try:
            st = traversable.lstat()
        except OSError:
            raise CatalogError("missing", relpath) from None
        if not stat.S_ISREG(st.st_mode):
            raise CatalogError("unsafe_object", relpath)
        if st.st_size > protocols.MAX_ARTIFACT_BYTES:
            raise CatalogError("too_large", relpath)

    try:
        data = traversable.read_bytes()
    except OSError:
        raise CatalogError("missing", relpath) from None
    if len(data) > protocols.MAX_ARTIFACT_BYTES:
        raise CatalogError("too_large", relpath)
    return data


# ---------------------------------------------------------------------------
# Manifest

def _validate_manifest(doc: dict) -> Catalog:
    """Structure gate: closed keys, closed vocabulary, self-digest, sort
    order, version contiguity, path derivation, and no duplicate agent,
    path, or digest. Pure — never touches a file or a connection."""
    if not isinstance(doc, dict) or set(doc) != _MANIFEST_KEYS:
        raise CatalogError("manifest_closed_keys", MANIFEST_FILENAME)

    if doc.get("canonical_json") != protocols.CANONICAL_JSON:
        raise CatalogError("manifest_bad_vocab", "/canonical_json")
    if doc.get("content_hash_alg") != protocols.CONTENT_HASH_ALG:
        raise CatalogError("manifest_bad_vocab", "/content_hash_alg")
    if doc.get("issuer") != CATALOG_ISSUER:
        raise CatalogError("manifest_bad_vocab", "/issuer")
    if doc.get("manifest_version") != MANIFEST_VERSION:
        raise CatalogError("manifest_bad_vocab", "/manifest_version")

    catalog_version = doc.get("catalog_version")
    if type(catalog_version) is not int or not (1 <= catalog_version <= 999999):
        raise CatalogError("manifest_bad_vocab", "/catalog_version")

    # The hash's FORMAT is checked here (for a precise "malformed_hash"
    # diagnostic); its CORRECTNESS is checked only after full structural
    # validation below — mirroring protocols.validate_document's own order
    # (structure before content-hash correctness), so a structurally broken
    # manifest is reported for what it actually is, not merely "wrong hash".
    declared_digest = doc.get("content_sha256")
    if not isinstance(declared_digest, str) or not _HEX64_RE.fullmatch(declared_digest):
        raise CatalogError("manifest_bad_hash", "/content_sha256")

    entries_raw = doc.get("entries")
    if not isinstance(entries_raw, list) or not (1 <= len(entries_raw) <= MAX_ENTRIES):
        raise CatalogError("manifest_closed_keys", "/entries")

    entries: list[CatalogEntry] = []
    seen_agents: set[str] = set()
    seen_paths: set[str] = set()
    seen_digests: set[str] = set()
    previous_agent: str | None = None

    for raw_entry in entries_raw:
        if not isinstance(raw_entry, dict) or set(raw_entry) != _ENTRY_KEYS:
            raise CatalogError("manifest_closed_keys", "/entries[]")

        agent = raw_entry.get("agent")
        if not isinstance(agent, str):
            raise CatalogError("manifest_bad_agent", str(agent))
        try:
            models.validate_catalog_agent_name(agent)
        except AosError:
            raise CatalogError("manifest_bad_agent", agent) from None

        category = raw_entry.get("category")
        if category not in CATEGORIES:
            raise CatalogError("manifest_bad_vocab", f"{agent}/category")
        maturity = raw_entry.get("maturity")
        if maturity not in MATURITIES:
            raise CatalogError("manifest_bad_vocab", f"{agent}/maturity")

        if agent in seen_agents:
            raise CatalogError("manifest_duplicate", agent)
        if previous_agent is not None and agent <= previous_agent:
            raise CatalogError("manifest_sort_order", agent)
        seen_agents.add(agent)
        previous_agent = agent

        versions_raw = raw_entry.get("versions")
        if not isinstance(versions_raw, list) or not (
            1 <= len(versions_raw) <= MAX_VERSIONS_PER_ENTRY
        ):
            raise CatalogError("manifest_version_gap", agent)

        versions: list[CatalogVersion] = []
        expected_version = 1
        for raw_version in versions_raw:
            if not isinstance(raw_version, dict) or set(raw_version) != _VERSION_KEYS:
                raise CatalogError("manifest_closed_keys", f"{agent}/versions[]")

            passport_version = raw_version.get("passport_version")
            if type(passport_version) is not int or passport_version != expected_version:
                raise CatalogError("manifest_version_gap", agent)

            digest = raw_version.get("document_sha256")
            if not isinstance(digest, str) or not _HEX64_RE.fullmatch(digest):
                raise CatalogError("manifest_bad_hash", f"{agent} v{expected_version}")
            if digest in seen_digests:
                raise CatalogError("manifest_duplicate", f"{agent} v{expected_version}")

            path = raw_version.get("path")
            if not isinstance(path, str):
                raise CatalogError("manifest_closed_keys", f"{agent}/versions[]/path")
            expected_path = f"{agent}.v{passport_version}.passport.json"
            if path != expected_path:
                raise CatalogError("manifest_path_mismatch", agent)
            if path in seen_paths:
                raise CatalogError("manifest_duplicate", path)

            seen_paths.add(path)
            seen_digests.add(digest)
            versions.append(
                CatalogVersion(
                    passport_version=passport_version, path=path, document_sha256=digest
                )
            )
            expected_version += 1

        entries.append(
            CatalogEntry(
                agent=agent, category=category, maturity=maturity, versions=tuple(versions)
            )
        )

    # Correctness, now that structure is proven sound: recomputed over the
    # canonical body with only content_sha256 itself removed (U-X1 rule).
    if protocols.content_digest(doc) != declared_digest:
        raise CatalogError("manifest_digest_mismatch", MANIFEST_FILENAME)

    return Catalog(
        catalog_version=catalog_version,
        manifest_version=MANIFEST_VERSION,
        issuer=CATALOG_ISSUER,
        manifest_sha256=declared_digest,
        entries=tuple(entries),
    )


@functools.lru_cache(maxsize=1)
def load_manifest() -> Catalog:
    """Parse + validate the shipped manifest. Lazy and memoized: nothing
    here runs at package import time. `load_manifest.cache_clear()` resets
    the cache (tests only — production never needs to)."""
    data = _resource(MANIFEST_FILENAME)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise CatalogError("malformed", MANIFEST_FILENAME) from None
    if not text.endswith("\n") or text.endswith("\n\n"):
        raise CatalogError("not_canonical", MANIFEST_FILENAME)
    body = text[:-1].encode("utf-8")

    try:
        document = protocols.parse_canonical(body)
    except protocols.ProtocolError:
        raise CatalogError("malformed", MANIFEST_FILENAME) from None
    if protocols.serialize_canonical(document) != body:
        raise CatalogError("not_canonical", MANIFEST_FILENAME)

    return _validate_manifest(document)


def catalog() -> Catalog:
    """The public memoized accessor."""
    return load_manifest()


# ---------------------------------------------------------------------------
# Artifacts

def _refuse_if_secret_shaped(agent: str, version: int, document: dict) -> None:
    """Fail-closed secret-shape refusal (D-v0.4.19): shipped content is
    reviewed content the project ships, not a trusted human's live
    keystrokes, so a hit here REFUSES rather than warns."""
    for key, label in _SCANNED_TEXT_FIELDS:
        value = document.get(key)
        if isinstance(value, list):
            value = "\n".join(str(item) for item in value)
        if isinstance(value, str) and secretscan.scan_secrets(value):
            raise CatalogError("secret_shaped", f"{agent} v{version}/{label}")


def load_document(entry: CatalogEntry, version: CatalogVersion) -> tuple[dict, str]:
    """One artifact → its validated document and exact stored text (the
    file's bytes, trailing newline included — what `catalog show --document`
    prints verbatim)."""
    data = _resource(version.path)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise CatalogError("malformed", version.path) from None
    if not text.endswith("\n") or text.endswith("\n\n"):
        raise CatalogError("not_canonical", version.path)
    body = text[:-1].encode("utf-8")

    try:
        document = protocols.parse_canonical(body)
    except protocols.ProtocolError:
        raise CatalogError("malformed", version.path) from None
    if protocols.serialize_canonical(document) != body:
        raise CatalogError("not_canonical", version.path)

    try:
        schema_entry = protocols.validate_document(document)
    except protocols.ProtocolError:
        raise CatalogError("document_invalid", version.path) from None
    if schema_entry.identity != PASSPORT_PROTOCOL:
        raise CatalogError("document_invalid", version.path)

    digest = protocols.content_digest(document)
    if digest != version.document_sha256:
        raise CatalogError(
            "document_digest_mismatch", f"{entry.agent} v{version.passport_version}"
        )

    bindings = (
        ("agent", entry.agent),
        ("passport_version", version.passport_version),
        ("issuer", CATALOG_ISSUER),
        ("agent_class", "specialist"),
        ("agent_scope", {"level": "global"}),
        ("autonomy", "declare_only"),
    )
    for field, expected in bindings:
        if document.get(field) != expected:
            raise CatalogError(
                "document_binding_mismatch",
                f"{entry.agent} v{version.passport_version}/{field}",
            )

    _refuse_if_secret_shaped(entry.agent, version.passport_version, document)
    return document, text


def _extra_artifacts(known: set[str]) -> list[str]:
    """Extra unreferenced artifact detection — only when the package-
    resource backend supports directory listing (a real filesystem checkout
    always does; kept conditional per the loader contract for any backend
    that does not)."""
    try:
        directory = importlib.resources.files("agentic_os") / CATALOG_DIRNAME
        children = list(directory.iterdir())
    except (OSError, NotADirectoryError, AttributeError, TypeError):
        return []
    extra = sorted(
        child.name
        for child in children
        if child.name.endswith(".json") and child.name not in known
    )
    return [f"{name}: not referenced by the catalog manifest" for name in extra]


def verify() -> list[str]:
    """A full, non-raising sweep over the manifest and every artifact.

    Returns bounded problem strings; never raises and never mutates. Doctor
    reuses this in a later wave, which is why it reports rather than
    crashes on a corrupt catalog."""
    try:
        cat = load_manifest()
    except CatalogError as exc:
        return [str(exc)]

    problems: list[str] = []
    known = {MANIFEST_FILENAME}
    for entry in cat.entries:
        for version in entry.versions:
            known.add(version.path)
            try:
                load_document(entry, version)
            except CatalogError as exc:
                problems.append(str(exc))
    problems.extend(_extra_artifacts(known))
    return problems


def entry_public(entry: CatalogEntry) -> dict:
    """The JSON/text shape for `catalog list`/`catalog show` (show-class
    output: full hashes are permitted here, per the M2.6 rule)."""
    latest = entry.latest
    return {
        "agent": entry.agent,
        "category": entry.category,
        "maturity": entry.maturity,
        "passport_version": latest.passport_version,
        "document_sha256": latest.document_sha256,
        "versions": [
            {"passport_version": v.passport_version, "document_sha256": v.document_sha256}
            for v in sorted(entry.versions, key=lambda v: v.passport_version)
        ],
    }


# ---------------------------------------------------------------------------
# Read-only installed state (no row is ever modified; no event is emitted)

#: The closed, deterministic state vocabulary (read_only_state_model).
STATES = ("not_installed", "installed", "upgradable", "blocked", "diverged", "tampered")


def installed_state(conn: sqlite3.Connection, entry: CatalogEntry) -> dict:
    """One entry's state relative to this ledger. Ownership requires ALL
    THREE of owner='system', issuer='aos.catalog', and a digest match — name
    alone never proves catalog ownership. Read-only: no row is modified, no
    event is emitted."""
    available_version = entry.latest.passport_version

    def _state(state: str, *, installed_version: int | None = None, detail: str | None = None) -> dict:
        return {
            "agent": entry.agent,
            "state": state,
            "installed_version": installed_version,
            "available_version": available_version,
            "detail": detail,
        }

    agent = passports.get_agent(conn, entry.agent)
    if agent is None:
        return _state("not_installed")

    # Name alone proves nothing: a non-system identity occupying the name is
    # a collision, never adopted.
    if agent.owner != "system":
        return _state("blocked", detail=f"name owned by a {agent.origin} identity")

    identity_verdict = passports.agent_integrity(agent)
    if identity_verdict != "ok":
        return _state(
            "tampered",
            installed_version=agent.current_passport_version,
            detail=f"identity {identity_verdict}",
        )
    history = passports.history_problems(conn, agent)
    if history:
        return _state(
            "tampered", installed_version=agent.current_passport_version, detail=history[0]
        )
    if (
        agent.agent_class != "specialist"
        or agent.protected != 1
        or agent.lifecycle != models.AGENT_LIFECYCLE_ACTIVE
    ):
        return _state(
            "tampered",
            installed_version=agent.current_passport_version,
            detail="provenance incoherent",
        )

    published = sorted(
        (
            p
            for p in passports.list_passports(conn, agent.id)
            if p.status == models.AGENT_PASSPORT_PUBLISHED
        ),
        key=lambda p: p.version,
    )
    if not published:
        return _state("tampered", detail="no published passport")

    max_installed = published[-1].version
    if agent.current_passport_version != max_installed:
        return _state(
            "tampered", installed_version=agent.current_passport_version, detail="pointer stale"
        )

    catalog_by_version = {v.passport_version: v for v in entry.versions}
    shared_upper = min(max_installed, available_version)
    for p in published:
        if p.version > shared_upper:
            break
        catalog_version = catalog_by_version.get(p.version)
        if catalog_version is None:
            return _state(
                "diverged",
                installed_version=max_installed,
                detail="installed history does not match the catalog",
            )
        try:
            document = protocols.parse_canonical(p.document.encode("utf-8"))
        except protocols.ProtocolError:
            return _state(
                "tampered", installed_version=max_installed, detail="document malformed"
            )
        if document.get("issuer") != CATALOG_ISSUER:
            return _state(
                "diverged",
                installed_version=max_installed,
                detail="installed history does not match the catalog",
            )
        if protocols.content_digest(document) != catalog_version.document_sha256:
            return _state(
                "diverged",
                installed_version=max_installed,
                detail="installed history does not match the catalog",
            )

    if max_installed > available_version:
        return _state(
            "diverged",
            installed_version=max_installed,
            detail="installed history does not match the catalog",
        )
    if max_installed == available_version:
        return _state("installed", installed_version=max_installed)
    return _state("upgradable", installed_version=max_installed)


def status(conn: sqlite3.Connection) -> list[dict]:
    """Every catalog entry's deterministic state. Read-only."""
    return [installed_state(conn, entry) for entry in catalog().entries]


def plan(conn: sqlite3.Connection, names: list[str] | None) -> list[dict]:
    """Ordered install/upgrade/noop/refuse actions for `names` (or every
    entry, when `names` is None — the `--all` case). Read-only: proposes
    actions from `installed_state`; writes nothing.

    Raises AosError on an unknown name — a plain user-facing refusal, not a
    CatalogError (which is reserved for catalog artifact integrity)."""
    cat = catalog()
    if names is None:
        selected = list(cat.entries)
    else:
        selected = []
        for name in names:
            entry = cat.get(name)
            if entry is None:
                raise AosError(
                    f"No catalog entry {name!r}. Run: python aos.py agent catalog list"
                )
            selected.append(entry)

    actions = []
    for entry in selected:
        state = installed_state(conn, entry)
        kind = state["state"]
        action = {"not_installed": "install", "upgradable": "upgrade", "installed": "noop"}.get(
            kind, "refuse"
        )
        actions.append(
            {
                "agent": entry.agent,
                "action": action,
                "state": kind,
                "detail": state["detail"],
            }
        )
    return actions


# ---------------------------------------------------------------------------
# Installation — the ONE writer in this unit (U-A2 §9)
#
# This module still issues no INSERT/UPDATE/DELETE against `agents` or
# `agent_passports`: every row is written by the two transaction-participating
# primitives in `passports`, and every read below is a SELECT. What this
# module owns is the TRANSACTION and the EVENT, because the rollback boundary
# has to span the whole selected set (D-v0.4.18) and only the caller can know
# what "the whole set" is.

#: The exact event payload key set (U-A2 §14). Frozen here so the payload is
#: built from a closed vocabulary rather than accumulated: no diagnostic,
#: count, path, reason or full digest can drift in later.
EVENT_PAYLOAD_KEYS = (
    "agent",
    "catalog_version",
    "manifest_sha256_prefix",
    "passport_sha256_prefix",
    "version",
    "from_version",
    "from_lifecycle",
    "to_lifecycle",
    "result",
)

ACTION_INSTALL = "catalog_install"
ACTION_UPGRADE = "catalog_upgrade"


def _select(cat: Catalog, names: list[str] | None) -> list[CatalogEntry]:
    """The selected entries, deduplicated and in MANIFEST order.

    Manifest order is installation order (U-A2 §7): CLI argument order is a
    human's typing, not a fact about the catalog, so two invocations naming
    the same entries in different orders must write identical rows in an
    identical sequence. Duplicates collapse to one entry — asking twice is
    not asking for two identities. An unknown name refuses here, before the
    caller reaches any mutation.
    """
    if names is None:
        return list(cat.entries)
    requested: set[str] = set()
    for name in names:
        if cat.get(name) is None:
            raise AosError(
                f"No catalog entry {name!r}. Nothing was changed. "
                "Run: python aos.py agent catalog list"
            )
        requested.add(name)
    return [entry for entry in cat.entries if entry.agent in requested]


def _document_text(entry: CatalogEntry, version: CatalogVersion) -> str:
    """One verified artifact → its exact canonical STORAGE form.

    `load_document` re-verifies the digest, the protocol and the catalog's
    bound fields on every read, so a tampered artifact cannot reach a row
    through here. The stored form is the canonical bytes WITHOUT the
    artifact file's trailing newline — identical to what every other passport
    row in the ledger carries.
    """
    document, _text = load_document(entry, version)
    return protocols.serialize_canonical(document).decode("utf-8")


def _versions(entry: CatalogEntry) -> list[CatalogVersion]:
    return sorted(entry.versions, key=lambda v: v.passport_version)


def _refuse_plan(actions: list[dict]) -> None:
    """One blocked entry refuses the WHOLE request (U-A2 §9).

    Never a best-effort partial install: 'I installed nine of the twelve you
    asked for' is a state nobody requested and no later command can describe.
    Reasons come from the closed state/detail vocabulary — never a stored
    value, a path, or exception text.
    """
    refusals = [a for a in actions if a["action"] == "refuse"]
    if not refusals:
        return
    first = refusals[0]
    detail = f" ({first['detail']})" if first["detail"] else ""
    scope = (
        f" {len(refusals)} of {len(actions)} selected entries are blocked."
        if len(refusals) > 1
        else ""
    )
    raise AosError(
        f"Catalog entry '{first['agent']}' is {first['state']}{detail}; "
        f"refusing the whole request.{scope} Nothing was changed. "
        "Run: python aos.py agent catalog status"
    )


def install(conn: sqlite3.Connection, names: list[str] | None) -> dict:
    """Install and/or upgrade the selected catalog entries. One transaction.

    The shape, in order:

    1. verify the complete built-in catalog (D-v0.4.19: a defect in shipped
       content refuses before any write, it does not warn afterward);
    2. select, in manifest order;
    3. plan, read-only;
    4. refuse every blocked/diverged/tampered/unknown selection;
    5. return WITHOUT opening a transaction when everything is a no-op;
    6. otherwise open exactly one transaction, re-read every fact inside it,
       write, and emit one event per changed entry.

    Every foreseeable refusal therefore costs zero writes, and any failure
    inside the transaction rolls back every identity, passport, pointer, hash
    and event this operation would have written.
    """
    problems = verify()
    if problems:
        raise AosError(
            "The built-in catalog does not verify, so nothing was installed: "
            f"{problems[0]} Run: python aos.py agent catalog verify"
        )

    cat = catalog()
    selected = _select(cat, names)
    actions = plan(conn, [entry.agent for entry in selected])
    _refuse_plan(actions)

    #: The exact preflight facts each write is predicated on. Re-derived
    #: inside the transaction and compared whole: a discrepancy in ANY field
    #: (history, pointer, lifecycle, owner, protection, class, scope, digest
    #: verdict) aborts the complete operation rather than writing against a
    #: fact that has since stopped being true.
    planned_state = {entry.agent: installed_state(conn, entry) for entry in selected}
    by_name = {entry.agent: entry for entry in selected}
    todo = [
        (by_name[a["agent"]], a)
        for a in actions
        if a["action"] in ("install", "upgrade")
    ]
    unchanged = len(actions) - len(todo)

    result = {
        "changed": False,
        "installed": 0,
        "upgraded": 0,
        "unchanged": unchanged,
        "catalog_version": cat.catalog_version,
    }
    if not todo:
        # A true no-op (U-A2 §9): no transaction, no row, no rehash, no
        # updated_at, no event. Reinstalling what is already installed is a
        # question, and a question does not get to touch the ledger.
        return result

    with db.transaction(conn):
        # Take the write lock BEFORE the re-reads below, so the
        # re-read-then-write pair is atomic against any other writer: with a
        # deferred transaction the reads would run against a snapshot the
        # first INSERT could only then discover was stale. This also makes
        # the transaction materially open, which is what lets the passport
        # primitives PROVE (not assume) they are participating in it.
        conn.execute("BEGIN IMMEDIATE")
        for entry, action in todo:
            current = installed_state(conn, entry)
            if current != planned_state[entry.agent]:
                raise AosError(
                    f"Catalog entry '{entry.agent}' changed while the install "
                    f"was preparing to write it (planned {action['state']}, "
                    f"found {current['state']}); the whole operation was "
                    "rolled back and nothing was changed. "
                    "Run: python aos.py agent catalog status"
                )

            versions = _versions(entry)
            if action["action"] == "install":
                # A fresh install replays the COMPLETE shipped history, so it
                # converges byte-for-byte with an upgrade chain (D-v0.4.17).
                agent = passports.create_catalog_identity(
                    conn,
                    name=entry.agent,
                    agent_class=passports.CATALOG_AGENT_CLASS,
                    documents=[
                        (v.passport_version, _document_text(entry, v)) for v in versions
                    ],
                )
                from_version = None
                from_lifecycle = None
                new_version = versions[-1]
                result["installed"] += 1
                outcome = "installed"
            else:
                agent = passports.get_agent(conn, entry.agent)
                from_version = current["installed_version"]
                from_lifecycle = agent.lifecycle
                # The state model proved the installed history is an exact
                # contiguous prefix of the catalog's, so the missing suffix is
                # simply everything above it. Each append re-proves it anyway.
                missing = [v for v in versions if v.passport_version > from_version]
                for version in missing:
                    agent = passports.append_catalog_version(
                        conn,
                        agent=agent,
                        version=version.passport_version,
                        document_text=_document_text(entry, version),
                    )
                new_version = missing[-1]
                result["upgraded"] += 1
                outcome = "upgraded"

            events.emit(
                conn,
                actor=ops.ACTOR_HUMAN,
                entity="agent",
                entity_id=agent.id,
                action=ACTION_INSTALL if outcome == "installed" else ACTION_UPGRADE,
                payload={
                    "agent": entry.agent,
                    "catalog_version": cat.catalog_version,
                    "manifest_sha256_prefix": models.hash_prefix(cat.manifest_sha256),
                    "passport_sha256_prefix": models.hash_prefix(
                        new_version.document_sha256
                    ),
                    "version": new_version.passport_version,
                    "from_version": from_version,
                    "from_lifecycle": from_lifecycle,
                    "to_lifecycle": agent.lifecycle,
                    "result": outcome,
                },
            )

    result["changed"] = True
    return result
