"""U-E2 runtime power modes: eco · standard · deep · recovery.

Contract: agentic-os-v0.2-u-e2-power-modes-contract.md

Power modes govern LOCAL CLI EXECUTION POLICY for one workspace. They never
choose an LLM, call a model, start a daemon, execute background work, or
grant autonomy. `power suggest` is deterministic and advisory; only a human
running `power set` changes the configured mode.

Two things live here, deliberately together:

1. The authoritative mode state — a small operational sidecar at
   `.agentic-os/power.json`, NOT the SQLite schema or meta table (D-v0.2.51).
   Recovery control must stay reachable when the database is unopenable,
   version-mismatched, or corrupt; storing the mode in the ledger would make
   the control depend on the thing it exists to recover. Nothing here calls
   db.open_db() for that reason.

2. The canonical command classification — one table keyed by argparse path,
   covering every CLI leaf. Mode policy is enforced once, in dispatch(), so
   individual command implementations carry no mode checks.

Everything printed from here names check names, fixed signal categories,
command paths, and bounded counts. Never a stored value, a row, SQL, a
secret, a raw path, or arbitrary exception text.
"""

from __future__ import annotations

import errno
import json
import os
import sqlite3
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import db, utils
from .utils import AosError

# ---------------------------------------------------------------------------
# Modes and state format

ECO = "eco"
STANDARD = "standard"
DEEP = "deep"
RECOVERY = "recovery"

#: The four modes, in canonical (matrix) order.
MODES = (ECO, STANDARD, DEEP, RECOVERY)

#: Absence of power.json means this. Absence is a valid, expected state.
DEFAULT_MODE = STANDARD

STATE_FILENAME = "power.json"
STATE_VERSION = 1

#: A power state is two short keys. Anything larger is not our file and is
#: refused before it is read into memory.
MAX_STATE_BYTES = 4096

#: The exact key set. Missing or unknown fields are refused, never ignored.
STATE_KEYS = frozenset({"version", "mode"})

_TMP_PREFIX = ".power-"
_TMP_SUFFIX = ".tmp"

#: Directory fsync is a durability hint, not a correctness requirement: the
#: rename already landed. These errnos mean "this platform/filesystem does
#: not support it" — anything else is a real failure and propagates.
_DIR_FSYNC_TOLERATED = frozenset(
    code
    for code in (
        getattr(errno, name, None)
        for name in ("EINVAL", "EACCES", "EPERM", "ENOSYS", "ENOTSUP", "EOPNOTSUPP", "EBADF")
    )
    if code is not None
)


def _errno_name(exc: OSError) -> str:
    """A safe, bounded name for an OS failure: the errno symbol, never the
    OS's message text (which can carry a path) and never the exception's
    internals."""
    code = exc.errno
    if code is None:
        return "OSError"
    return errno.errorcode.get(code, "OSError")


class PowerStateError(AosError):
    """Malformed or unsafe power state.

    Names the failing condition only — never the file's content, never a
    raw path. Exits 1 through the existing AosError path.
    """


# ---------------------------------------------------------------------------
# Command classification

READ_ONLY = "read_only"
DERIVED_WRITE = "derived_write"
RECOVERY_SAFE = "recovery_safe"
AUTHORITATIVE_WRITE = "authoritative_write"

#: The four classes. Every CLI leaf gets exactly one.
KINDS = (READ_ONLY, DERIVED_WRITE, RECOVERY_SAFE, AUTHORITATIVE_WRITE)

#: What recovery lets through. Everything else is refused before dispatch.
RECOVERY_ALLOWED_KINDS = frozenset({READ_ONLY, RECOVERY_SAFE})


@dataclass(frozen=True)
class CommandPolicy:
    """One CLI leaf's classification.

    `ledger` marks a command that touches the authoritative SQLite ledger.
    Deep preflight/post-verification apply only to authoritative_write
    commands with ledger=True, so `init` and `hooks install` — which write
    durable state but touch no existing ledger — get no pointless preflight.
    """

    kind: str
    ledger: bool = False


def _p(kind: str, *, ledger: bool = False) -> CommandPolicy:
    return CommandPolicy(kind, ledger)


#: THE canonical degradation matrix input: every CLI leaf, keyed by its
#: argparse path tuple. Classification is by what a command WRITES, read out
#: of the implementation — never inferred from its name or help prose.
#:
#: The rule, applied mechanically: a command that writes any row to aos.db —
#: including an audit event — is authoritative_write. Writing a derived
#: artifact does not soften that. `backup create` and `snapshot` land here
#: because both emit a ledger event (contract D-2).
COMMAND_POLICY: dict[tuple[str, ...], CommandPolicy] = {
    # Workspace creation: writes the database and mirror; no existing ledger.
    ("init",): _p(AUTHORITATIVE_WRITE),

    # Ledger row writers.
    ("project", "add"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("task", "add"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("task", "assign"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("task", "edit"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("task", "status"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("in",): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("run", "start"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("run", "end"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("evidence", "add"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("evidence", "git"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("decision", "add"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("handoff", "create"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("handoff", "accept"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("memory", "add"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("memory", "retire"): _p(AUTHORITATIVE_WRITE, ledger=True),
    # U-M2 curation writes: each changes a memory row, its claim hash and an
    # event in one transaction — authoritative by the same mechanical rule.
    ("memory", "pin"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("memory", "unpin"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("memory", "link-evidence"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("agent", "add"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("agent", "update"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("ingest", "dropfile"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("done",): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("migrate", "apply"): _p(AUTHORITATIVE_WRITE, ledger=True),
    # Writes a packs row + event alongside the pack file.
    ("pack", "build"): _p(AUTHORITATIVE_WRITE, ledger=True),
    # Both write a file AND emit their audit event (contract D-2).
    ("snapshot",): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("backup", "create"): _p(AUTHORITATIVE_WRITE, ledger=True),
    # Durable state outside the ledger: the human's Claude settings.json.
    ("hooks", "install"): _p(AUTHORITATIVE_WRITE),
    ("hooks", "uninstall"): _p(AUTHORITATIVE_WRITE),

    # Regenerable artifacts outside the ledger; no rows, no events.
    ("sync",): _p(DERIVED_WRITE),
    ("export", "events"): _p(DERIVED_WRITE),
    ("review", "build"): _p(DERIVED_WRITE),
    ("review", "weekly"): _p(DERIVED_WRITE),
    ("review", "project"): _p(DERIVED_WRITE),

    # Reads only.
    ("status",): _p(READ_ONLY),
    ("log",): _p(READ_ONLY),
    ("search",): _p(READ_ONLY),
    ("doctor",): _p(READ_ONLY),
    ("task", "list"): _p(READ_ONLY),
    ("task", "show"): _p(READ_ONLY),
    ("memory", "list"): _p(READ_ONLY),
    ("memory", "show"): _p(READ_ONLY),
    ("agent", "list"): _p(READ_ONLY),
    ("agent", "show"): _p(READ_ONLY),
    ("hooks", "status"): _p(READ_ONLY),
    ("migrate", "status"): _p(READ_ONLY),
    ("migrate", "plan"): _p(READ_ONLY),
    ("power", "status"): _p(READ_ONLY),
    ("power", "suggest"): _p(READ_ONLY),
    # U-X1 protocol spine. Inert by construction: each parses bytes and
    # compares them to an embedded schema. No SQLite, no power.json, no
    # workspace state, no events, no execution of artifact content.
    ("protocol", "list"): _p(READ_ONLY),
    ("protocol", "show"): _p(READ_ONLY),
    ("protocol", "validate"): _p(READ_ONLY),
    ("protocol", "digest"): _p(READ_ONLY),
    ("protocol", "verify-registry"): _p(READ_ONLY),

    # Explicitly safe under recovery: never mutates the live ledger.
    # backup verify reads a backup copy; backup restore writes a distinct
    # NEW path and never overwrites the live database (U-C2). power set is
    # the recovery control itself — it enforces its own transition gate.
    ("backup", "verify"): _p(RECOVERY_SAFE),
    ("backup", "restore"): _p(RECOVERY_SAFE),
    ("power", "set"): _p(RECOVERY_SAFE),
}


def iter_command_paths(parser) -> list[tuple[str, ...]]:
    """Every leaf command path in a live argparse tree, sorted.

    Walks the real parser rather than a hand-kept list, so a new command
    cannot slip past the classification test by being forgotten here.
    """
    import argparse

    def walk(node, prefix: tuple[str, ...]):
        subs = [
            action
            for action in node._actions
            if isinstance(action, argparse._SubParsersAction)
        ]
        if not subs:
            yield prefix
            return
        for action in subs:
            for name, child in action.choices.items():
                yield from walk(child, prefix + (name,))

    return sorted(walk(parser, ()))


def command_path(args) -> tuple[str, ...]:
    """The classification key for a parsed argparse namespace."""
    command = getattr(args, "command", None)
    if command is None:
        return ()
    sub = getattr(args, "subcommand", None)
    return (command,) if sub is None else (command, sub)


def policy_for(path: tuple[str, ...]) -> CommandPolicy:
    policy = COMMAND_POLICY.get(path)
    if policy is None:
        # Fail closed: an unclassified command is treated as the most
        # dangerous thing it could be. The classification test makes this
        # unreachable in a released build.
        return _p(AUTHORITATIVE_WRITE, ledger=True)
    return policy


# ---------------------------------------------------------------------------
# State: read

@dataclass(frozen=True)
class PowerState:
    mode: str
    #: True = read from power.json; False = the missing-file default.
    configured: bool


def state_path(aos_dir: Path) -> Path:
    return aos_dir / STATE_FILENAME


def _object_kind(mode: int) -> str:
    """A safe noun for a non-regular object — no path, no content."""
    if stat.S_ISLNK(mode):
        return "a symlink"
    if stat.S_ISDIR(mode):
        return "a directory"
    if stat.S_ISFIFO(mode):
        return "a FIFO"
    if stat.S_ISSOCK(mode):
        return "a socket"
    if stat.S_ISBLK(mode):
        return "a block device"
    if stat.S_ISCHR(mode):
        return "a character device"
    return "not a regular file"


def _refuse(condition: str) -> PowerStateError:
    """One shape for every state refusal: the condition, then the one safe
    way out. Deliberately never echoes the file's bytes or its full path —
    `.agentic-os/power.json` is the fixed, safe way to name it."""
    return PowerStateError(
        f"The runtime power state (.agentic-os/{STATE_FILENAME}) is "
        f"unusable: {condition}. It is not repaired automatically and no "
        "mode transition is possible while it stands. Inspect it, then "
        f"delete it (absence means '{DEFAULT_MODE}') and re-set the mode: "
        "python aos.py power set standard"
    )


def _inspect_state_object(path: Path) -> bool:
    """Refuse any unsafe existing object; return True when a regular file is
    present, False when absent.

    lstat, never stat: a symlink must be SEEN as a symlink rather than
    followed to whatever it points at. Fail-closed — the existing object is
    left exactly as found.
    """
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise _refuse(f"it cannot be inspected ({_errno_name(exc)})")
    if not stat.S_ISREG(st.st_mode) or stat.S_ISLNK(st.st_mode):
        raise _refuse(f"the path is {_object_kind(st.st_mode)}")
    if st.st_size > MAX_STATE_BYTES:
        raise _refuse(f"it is larger than the {MAX_STATE_BYTES}-byte bound")
    return True


def _no_duplicate_keys(pairs):
    keys = [key for key, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate key")
    return dict(pairs)


def read_state(aos_dir: Path) -> PowerState:
    """The configured power state, or the default when the file is absent.

    Raises PowerStateError on anything malformed or unsafe. Never creates,
    repairs, or rewrites the file.
    """
    path = state_path(aos_dir)
    if not _inspect_state_object(path):
        return PowerState(DEFAULT_MODE, configured=False)

    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise _refuse(f"it cannot be read ({_errno_name(exc)})")
    if len(raw) > MAX_STATE_BYTES:
        raise _refuse(f"it is larger than the {MAX_STATE_BYTES}-byte bound")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _refuse("it is not valid UTF-8")
    try:
        # object_pairs_hook rejects duplicate keys, which json.loads would
        # otherwise silently resolve last-wins. Trailing data is rejected by
        # json.loads itself.
        document = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except ValueError:
        raise _refuse("it is not one well-formed JSON document with unique keys")

    if not isinstance(document, dict):
        raise _refuse("the document is not a JSON object")
    keys = set(document)
    if keys != STATE_KEYS:
        unknown = sorted(keys - STATE_KEYS)
        missing = sorted(STATE_KEYS - keys)
        if unknown:
            # Key NAMES are echoed, values never are. A key name is a
            # structural fact about our own format, not stored content.
            raise _refuse(f"it carries unknown field(s): {', '.join(unknown)}")
        raise _refuse(f"it is missing required field(s): {', '.join(missing)}")

    version = document["version"]
    # `type(...) is int`, not isinstance: bool is a subclass of int, and
    # {"version": true} must not read as version 1.
    if type(version) is not int or version != STATE_VERSION:
        raise _refuse(f"its version is not {STATE_VERSION}")

    mode = document["mode"]
    if not isinstance(mode, str):
        raise _refuse("its mode is not a string")
    if mode not in MODES:
        # The mode value is echoed only after it fails the fixed vocabulary
        # check, and only through repr of a bounded slice — it can never be
        # a secret we would print, and naming it is what makes the error
        # actionable. Bounded so an adversarial file cannot flood stderr.
        raise _refuse(f"its mode {mode[:32]!r} is not one of: {', '.join(MODES)}")
    return PowerState(mode, configured=True)


def effective_mode(aos_dir: Path | None) -> str:
    """Best-effort mode for reporting. Never raises; a malformed state reads
    as the default here because the caller has already been told about it."""
    if aos_dir is None:
        return DEFAULT_MODE
    try:
        return read_state(aos_dir).mode
    except PowerStateError:
        return DEFAULT_MODE


# ---------------------------------------------------------------------------
# State: write

def _fsync_dir(directory: Path) -> None:
    """fsync the parent directory so the rename itself is durable.

    Best-effort over a fixed errno allowlist: platforms that cannot fsync a
    directory are not a failure (the replace already landed). A real I/O
    error still propagates.
    """
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError as exc:
        if exc.errno in _DIR_FSYNC_TOLERATED:
            return
        raise
    try:
        os.fsync(fd)
    except OSError as exc:
        if exc.errno not in _DIR_FSYNC_TOLERATED:
            raise
    finally:
        os.close(fd)


def serialize(mode: str) -> bytes:
    """The exact on-disk bytes: compact, fixed key order, newline-terminated.

    dict insertion order is the serialization order, so this is byte-stable:
    {"version":1,"mode":"<mode>"}\\n
    """
    document = json.dumps(
        {"version": STATE_VERSION, "mode": mode},
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return (document + "\n").encode("utf-8")


def write_state(aos_dir: Path, mode: str) -> None:
    """Atomically replace power.json with a complete valid state.

    Same-directory temp file → fsync → os.replace → parent fsync. The
    destination is never opened for writing, so a failure at any step leaves
    the previous bytes exactly as they were, and the temp file is unlinked in
    a finally — no partial file, no debris.

    os.replace is the serialization point for concurrent writers: each one
    renames one already-complete, already-valid file, so the result is always
    exactly one valid state, never mixed or malformed JSON.
    """
    if mode not in MODES:
        raise AosError(f"Unknown power mode {mode!r}. Modes: {', '.join(MODES)}")
    path = state_path(aos_dir)
    _inspect_state_object(path)  # refuse an unsafe destination, unchanged

    payload = serialize(mode)
    tmp: Path | None = None
    try:
        fd, name = tempfile.mkstemp(
            prefix=_TMP_PREFIX, suffix=_TMP_SUFFIX, dir=aos_dir
        )
        tmp = Path(name)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
        tmp = None
    except OSError as exc:
        raise PowerStateError(
            f"Could not write the runtime power state "
            f"({_errno_name(exc)}). The previous "
            "state is unchanged."
        )
    finally:
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass
    _fsync_dir(aos_dir)


# ---------------------------------------------------------------------------
# Doctor-derived signals (lazy import: doctor imports this module)

def _doctor_checks(aos_dir: Path):
    """Run doctor's checks against the workspace, or None when the database
    cannot be read at all.

    db.connect, not db.open_db: open_db refuses any schema_version != the
    build's, and a version-mismatched database must surface as doctor check 7
    FAILING (a hard failure → suggest recovery, and no transition out of
    recovery) rather than as an exception. That is exactly the state in which
    a human needs recovery control to keep working.
    """
    from . import doctor

    db_path = aos_dir / utils.DB_FILENAME
    if not db_path.is_file():
        return None
    try:
        conn = db.connect(db_path)
    except sqlite3.Error:
        return None
    try:
        return doctor.run_checks(conn, aos_dir)
    except (sqlite3.Error, OSError):
        return None
    finally:
        conn.close()


def hard_doctor_failures(aos_dir: Path) -> list[str]:
    """Names of the failing hard checks (warn-only never counts).

    Fail-closed: a database that cannot be read at all is a hard failure, so
    leaving recovery is impossible until the ledger is healthy.
    """
    checks = _doctor_checks(aos_dir)
    if checks is None:
        return ["doctor could not complete"]
    return [c.name for c in checks if not c.ok and not c.warn_only]


def active_run_count(aos_dir: Path) -> int:
    """Runs still open. Counts rows; never reads their content."""
    db_path = aos_dir / utils.DB_FILENAME
    if not db_path.is_file():
        return 0
    try:
        conn = db.connect(db_path)
    except sqlite3.Error:
        return 0
    try:
        row = conn.execute(
            "SELECT COUNT(*) FROM runs WHERE ended_at IS NULL"
        ).fetchone()
        return int(row[0])
    except sqlite3.Error:
        return 0
    finally:
        conn.close()


def suggest(aos_dir: Path) -> dict:
    """The deterministic advisory suggestion. Reads only; writes nothing.

    Fixed priority — no model call, no scoring model, no natural-language
    heuristic, no environment telemetry, no CPU/RAM probing:

      1. any hard doctor failure          → recovery
      2. else any doctor warning          → deep
      3. else any active ledger work      → standard
      4. else clean and idle              → eco

    The result carries a fixed signal category and a bounded count. It never
    carries ledger content, titles, summaries, refs, claims, secrets, or paths.
    """
    checks = _doctor_checks(aos_dir)
    if checks is None:
        return {
            "mode": RECOVERY,
            "signal": "doctor could not complete",
            "count": 0,
        }
    failures = [c for c in checks if not c.ok and not c.warn_only]
    if failures:
        return {
            "mode": RECOVERY,
            "signal": "hard doctor failure",
            "count": len(failures),
        }
    warnings = [c for c in checks if not c.ok and c.warn_only]
    if warnings:
        return {
            "mode": DEEP,
            "signal": "doctor warning",
            "count": len(warnings),
        }
    active = active_run_count(aos_dir)
    if active:
        return {"mode": STANDARD, "signal": "active ledger work", "count": active}
    return {"mode": ECO, "signal": "clean and idle", "count": 0}


# ---------------------------------------------------------------------------
# Deep preflight / post-verification

def deep_check(aos_dir: Path) -> list[str]:
    """The bounded read-only deep check: integrity + the U-C3 secret sweep.

    Returns CHECK NAMES with counts — never a row value, database content,
    SQL, a secret, exception internals, or unbounded data. The human is
    pointed at `doctor` for the (already bounded and already safe) detail.
    """
    from . import doctor

    problems: list[str] = []
    db_path = aos_dir / utils.DB_FILENAME
    if not db_path.is_file():
        return ["database is not present"]
    try:
        conn = db.connect(db_path)
    except sqlite3.Error:
        return ["database is not openable"]
    try:
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        except sqlite3.DatabaseError:
            integrity = None
        if integrity != "ok":
            problems.append("database integrity_check")
        try:
            findings = doctor.secret_sweep_findings(conn)
        except sqlite3.DatabaseError:
            problems.append("ledger secret sweep (could not complete)")
        else:
            if findings:
                problems.append(f"ledger secret sweep ({len(findings)} finding(s))")
    finally:
        conn.close()
    return problems


# ---------------------------------------------------------------------------
# Transitions

def set_mode(aos_dir: Path, mode: str) -> dict:
    """Apply a human-requested mode. Returns {"mode", "changed", "previous"}.

    - recovery is always available while the workspace and the state path are
      safely inspectable — including while doctor reports hard failures, and
      including when the database cannot be opened at all. It never consults
      the ledger.
    - eco/standard/deep require every hard doctor check to pass.
    - a malformed/unsafe existing state refuses every transition, without
      replacement and without silent repair (read_state raises).
    """
    if mode not in MODES:
        raise AosError(f"Unknown power mode {mode!r}. Modes: {', '.join(MODES)}")

    current = read_state(aos_dir)

    # Idempotent no-op: only when the file EXISTS and already holds `mode`.
    # An absent file plus `power set standard` is a real request to pin the
    # mode — pinning is observable (doctor then reports it as configured).
    if current.configured and current.mode == mode:
        return {"mode": mode, "changed": False, "previous": current.mode}

    if mode != RECOVERY:
        failures = hard_doctor_failures(aos_dir)
        if failures:
            shown = ", ".join(failures[:5])
            extra = len(failures) - 5
            if extra > 0:
                shown += f" (+{extra} more)"
            raise AosError(
                f"Refused: entering '{mode}' requires every hard doctor check "
                f"to pass; {len(failures)} still fail: {shown}. The mode is "
                f"unchanged ({current.mode}). Run `python aos.py doctor`, fix "
                "what it reports, then retry. To keep working meanwhile: "
                "python aos.py power set recovery"
            )

    write_state(aos_dir, mode)
    return {"mode": mode, "changed": True, "previous": current.mode}


# ---------------------------------------------------------------------------
# Degradation matrix

#: The effective policy for every mode, in canonical order. Fixed strings and
#: fixed widths: no terminal-width-dependent formatting, stable for docs and
#: tests. Automatic mode switching is "no" in every mode, by construction.
MATRIX_COLUMNS = (
    "authoritative-writes",
    "explicit-derived",
    "implicit-derived",
    "deep-preflight",
    "recovery-utilities",
    "auto-switch",
)

MATRIX: dict[str, tuple[str, ...]] = {
    ECO:      ("allow",  "allow", "defer", "no",  "allow", "no"),
    STANDARD: ("allow",  "allow", "run",   "no",  "allow", "no"),
    DEEP:     ("verify", "allow", "run",   "yes", "allow", "no"),
    RECOVERY: ("block",  "block", "block", "no",  "allow", "no"),
}


def matrix_lines(active: str | None) -> list[str]:
    """The stable degradation matrix. `active` marks one row with '*'."""
    widths = [max(len(col), 8) for col in MATRIX_COLUMNS]
    mode_width = max(len(m) for m in MODES)

    def row(marker: str, mode: str, cells) -> str:
        parts = [f"{cell:<{w}}" for cell, w in zip(cells, widths)]
        return f"{marker} {mode:<{mode_width}}  " + "  ".join(parts)

    lines = [row(" ", "mode", MATRIX_COLUMNS).rstrip()]
    for mode in MODES:
        marker = "*" if mode == active else " "
        lines.append(row(marker, mode, MATRIX[mode]).rstrip())
    lines.append("(* = active mode · auto-switch is never yes: only a human "
                 "changes the mode)")
    return lines


# ---------------------------------------------------------------------------
# Dispatch gate

@dataclass
class Context:
    """What the gate resolved for this invocation."""

    path: tuple[str, ...]
    policy: CommandPolicy
    aos_dir: Path | None
    mode: str
    configured: bool
    #: The state problem, when a read_only/recovery_safe command was allowed
    #: to proceed so it could REPORT the problem (doctor, power status).
    state_error: PowerStateError | None = None
    deep_verify: bool = False


#: Where the gate stashes its Context on the parsed namespace, so the one
#: mandated eco site (init) can read the mode without re-resolving it.
CONTEXT_ATTR = "_power_context"


def context_of(args) -> Context | None:
    return getattr(args, CONTEXT_ATTR, None)


def mode_of(args) -> str:
    ctx = context_of(args)
    return ctx.mode if ctx is not None else DEFAULT_MODE


def workspace_for(args) -> Path | None:
    """Best-effort, NON-raising: the initialized workspace whose power state
    governs this invocation, or None when none is in scope.

    Mirrors cli._resolve_aos_dir's precedence (global --root wins over
    cwd-upward discovery) and additionally honors `init --root`, so `init`
    against an existing workspace is governed by that workspace's state.
    Returning None (no workspace) means the default mode and no gating —
    there is no authoritative ledger to protect yet.
    """
    root = getattr(args, "global_root", None)
    if root is None:
        root = getattr(args, "root", None)
    if root is not None:
        aos_dir = Path(root).expanduser().resolve() / utils.AOS_DIR_NAME
    else:
        found = utils.find_aos_dir()
        if found is not None:
            return found
        aos_dir = Path.cwd() / utils.AOS_DIR_NAME
    return aos_dir if (aos_dir / utils.DB_FILENAME).is_file() else None


def _render_path(path: tuple[str, ...]) -> str:
    return " ".join(path) if path else "(none)"


def enforce(args) -> Context:
    """Resolve the mode and apply it, BEFORE the command runs.

    Every refusal here fires before dispatch, so stdout stays empty and no
    mutation can have happened.
    """
    path = command_path(args)
    policy = policy_for(path)
    aos_dir = workspace_for(args)

    if aos_dir is None:
        ctx = Context(path, policy, None, DEFAULT_MODE, configured=False)
        setattr(args, CONTEXT_ATTR, ctx)
        return ctx

    try:
        state = read_state(aos_dir)
    except PowerStateError as exc:
        # Fail closed on the unknown mode: a malformed state could be hiding
        # a configured 'recovery', so nothing that writes may proceed. Reads
        # and recovery-safe commands DO proceed — that is how the human sees
        # the problem (doctor check 21, power status) and gets out of it.
        if policy.kind not in RECOVERY_ALLOWED_KINDS:
            raise
        ctx = Context(
            path, policy, aos_dir, DEFAULT_MODE, configured=False, state_error=exc
        )
        setattr(args, CONTEXT_ATTR, ctx)
        return ctx

    ctx = Context(path, policy, aos_dir, state.mode, state.configured)
    setattr(args, CONTEXT_ATTR, ctx)

    if state.mode == RECOVERY and policy.kind not in RECOVERY_ALLOWED_KINDS:
        raise AosError(
            f"Refused: `{_render_path(path)}` is blocked in recovery mode "
            f"({policy.kind}). Recovery allows read-only and recovery-safe "
            "commands only, so a damaged workspace cannot be written to by "
            "accident. Nothing was changed. Run `python aos.py doctor`, fix "
            "what it reports, then leave recovery: "
            "python aos.py power set standard"
        )

    if state.mode == DEEP and policy.kind == AUTHORITATIVE_WRITE and policy.ledger:
        problems = deep_check(aos_dir)
        if problems:
            raise AosError(
                f"Refused: deep mode's preflight found "
                f"{'; '.join(problems)} before `{_render_path(path)}` wrote "
                "anything. Nothing was written. Run `python aos.py doctor` "
                "for the full report, or `python aos.py power set recovery` "
                "to keep working read-only meanwhile."
            )
        ctx.deep_verify = True

    return ctx


def verify_after(ctx: Context) -> None:
    """Deep post-verification, AFTER a successful authoritative write.

    Honest by construction: the command committed. This reports that it
    committed and that verification failed. It never claims a rollback and
    never performs one — an automatic destructive rollback of a committed,
    journaled write is exactly the behavior this system exists to prevent.
    """
    if not ctx.deep_verify or ctx.aos_dir is None:
        return
    problems = deep_check(ctx.aos_dir)
    if not problems:
        return
    raise AosError(
        f"`{_render_path(ctx.path)}` COMMITTED, and deep verification then "
        f"FAILED: {'; '.join(problems)}. The change is committed and was NOT "
        "rolled back — nothing here undoes a journaled write. Enter recovery "
        "before doing anything else: python aos.py power set recovery — then "
        "run `python aos.py doctor` and see RECOVERY.md."
    )


def dispatch(args):
    """The one place mode policy is applied around a command.

    Individual command implementations carry no mode checks; the single
    mandated exception is `init`, which reads ctx.mode to honor eco's one
    deferral site (the idempotent mirror re-heal).
    """
    ctx = enforce(args)
    code = args.func(args)
    if code == 0:
        verify_after(ctx)
    return code
