"""U-H1: the Claude Code session bridge (Stop capture → SessionEnd publish)
and its trust-gated settings installer.

Two deterministic stages carry an agent's write-back from a Claude Code
session to the MANUAL dropfile ingest path — and no further:

* The **Stop** handler reads the official hook JSON from stdin, looks for
  exactly one fenced ``aos-dropfile`` envelope in ``last_assistant_message``
  (the only session text it ever sees — transcripts are never opened), and
  validates it with the SAME parser, size caps, and secret scanner the manual
  ingest path uses (``ingest.parse_dropfile`` / ``MAX_DROPFILE_BYTES`` /
  U-C3). A valid envelope is staged atomically — bound to the session id and
  a sha256 content digest — under ``.agentic-os/exports/hook-staging/``.
  At most one staged record exists per session; a later envelope in the same
  session replaces it (the last envelope before the session ends wins).
  No envelope, or a session outside any AOS workspace, is a clean exit-0
  no-op. The handler NEVER blocks the stop: stdout stays empty in every
  outcome (so no decision JSON can exist) and exit code 2 — the Stop-hook
  blocking signal — is never used; refusals are exit 1 diagnostics.

* The **SessionEnd** handler locates only its own session's staged record,
  re-validates it in full (format marker, session binding, digest, dropfile
  parse, size caps, secret scan), and publishes at most one protocol-valid
  dropfile under ``.agentic-os/exports/`` with a deterministic,
  collision-safe name that carries the dedupe digest. Publication is atomic
  (same-directory temp file + ``os.link``, which never overwrites) and
  idempotent: a duplicate/retry SessionEnd finds either no staged record
  (clean no-op) or identical already-published bytes (success, no second
  file). INGEST STAYS MANUAL: the ledger is never touched.

Hard prohibitions (tested): the handlers never run a subprocess, never open
SQLite or the ledger, never ingest, never start/end runs or change task
state, never call Git or the network, never execute or interpret envelope
text, never read ``transcript_path`` or any other workspace file, and never
write outside the exports/staging paths they own. Diagnostics go to stderr
only and never echo untrusted content — a bad envelope could be exactly the
secret-shaped text the scanner exists to keep off stderr.

Recovery rule (deterministic; drills in TROUBLESHOOTING.md): a staged record
is removed only after its publication has been verified — the fresh-publish
and identical-already-published cases; every refusal retains the staged
record byte-for-byte untouched, so a retry refuses identically until a human
inspects it. Honest limit: the pre-write inspections here are lstat/
O_NOFOLLOW checks, not the U-C4 descriptor-pinned depth — a same-directory
race inside the check-to-write window is documented, not defended.

The installer half (``plan_install`` / ``plan_uninstall`` / ``apply_plan`` /
``status``) edits the documented Claude Code user settings file
(``~/.claude/settings.json`` unless ``--settings`` overrides it): dry-run by
default with an exact deterministic diff, explicit confirmation plus a
timestamped backup before any rewrite, a same-directory temp file with
atomic replacement, validation of the JSON before and after, and
marker-based ownership (the ``aos_hooks.py`` runner token) so only the exact
AOS-owned Stop/SessionEnd entries are ever added, healed, or removed —
unrelated settings and hooks pass through the JSON round-trip untouched.
Compatibility is capability-based, not version-pinned: the handlers need a
Claude Code that provides Stop/SessionEnd command hooks with JSON on stdin
and ``last_assistant_message`` in the Stop input.
"""

from __future__ import annotations

import copy
import difflib
import json
import os
import re
import shlex
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import ingest, utils
from .utils import AosError

#: Fence language tag of the write-back envelope. The fenced content is
#: EXACTLY the dropfile format `adapters/*/PROTOCOL.md` publishes — one
#: schema, two transports (agent-written file, or hook-published envelope).
ENVELOPE_FENCE = "aos-dropfile"

#: Opening fence at column 0, envelope body, closing fence at column 0.
#: Strict by design: an indented or unterminated fence is "no envelope".
_ENVELOPE_RE = re.compile(
    r"^```aos-dropfile[ \t]*\n(.*?)\n```[ \t]*$",
    re.MULTILINE | re.DOTALL,
)

#: Hook stdin is bounded like every other untrusted input (U-C1 posture).
#: Official Stop payloads carry one assistant message plus small metadata;
#: 16 MiB is far above any real payload and refuses runaway input whole.
MAX_HOOK_INPUT_BYTES = 16 * 1024 * 1024

#: A staged record is the envelope JSON-escaped plus fixed fields. Worst-case
#: JSON escaping multiplies content ~6x (control chars → \uXXXX), so this cap
#: can never refuse a record the Stop handler legitimately wrote.
MAX_STAGED_RECORD_BYTES = 8 * 1024 * 1024

#: Session ids land in staging filenames, so the charset is fence and
#: identity at once: no separators, no dots, no traversal. UUIDs pass.
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{7,127}\Z", re.ASCII)

#: Format marker of a staged record; anything else refuses publication.
STAGED_FORMAT = "aos-u-h1-staged/1"

#: The documented SessionEnd reason vocabulary. Anything else refuses —
#: capability-based compatibility means an unknown future reason is
#: surfaced, never guessed at.
SESSION_END_REASONS = ("clear", "logout", "prompt_input_exit", "other")

STAGING_DIR_NAME = "hook-staging"

# ---------------------------------------------------------------------------
# Runtime handlers (invoked by Claude Code via aos_hooks.py — never via aos)


class HookRefusal(Exception):
    """Runtime-handler refusal: one safe line on stderr, exit 1, no partial
    writes. Never exit 2 — for a Stop hook that is the blocking signal, and
    these handlers never block."""


def main(argv: list[str], stdin_bytes: bytes | None = None) -> int:
    """Entry point for aos_hooks.py. stdout is NEVER written (a Stop hook's
    stdout can carry decision JSON; an always-empty stdout cannot)."""
    if argv == ["stop"]:
        stage = "stop"
    elif argv == ["session-end"]:
        stage = "session-end"
    else:
        print("usage: aos_hooks.py stop|session-end", file=sys.stderr)
        return 1
    try:
        data = _read_input(stdin_bytes)
        if stage == "stop":
            return _run_stop(data)
        return _run_session_end(data)
    except HookRefusal as exc:
        print(f"aos-hook[{stage}]: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # never blocking, never echoing content
        if os.environ.get("AOS_DEBUG") == "1":
            import traceback

            traceback.print_exc()
        print(
            f"aos-hook[{stage}]: internal error "
            f"({exc.__class__.__name__}); nothing was written.",
            file=sys.stderr,
        )
        return 1


def _read_input(stdin_bytes: bytes | None) -> dict:
    if stdin_bytes is None:
        stdin_bytes = bytes(sys.stdin.buffer.read(MAX_HOOK_INPUT_BYTES + 1))
    if len(stdin_bytes) > MAX_HOOK_INPUT_BYTES:
        raise HookRefusal(
            f"hook input exceeds the {MAX_HOOK_INPUT_BYTES}-byte cap; "
            "nothing was written."
        )
    try:
        data = json.loads(stdin_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise HookRefusal("hook input is not a UTF-8 JSON object.")
    if not isinstance(data, dict):
        raise HookRefusal("hook input is not a JSON object.")
    return data


def _validated_session_id(data: dict) -> str:
    session_id = data.get("session_id")
    if not isinstance(session_id, str) or not _SESSION_ID_RE.match(session_id):
        # The value is untrusted and would become a filename — refuse
        # without echoing it.
        raise HookRefusal(
            "session_id is missing or not a safe identifier "
            "([A-Za-z0-9-], 8-128 chars); nothing was written."
        )
    return session_id


def _find_workspace(data: dict) -> Path | None:
    cwd = data.get("cwd")
    if not isinstance(cwd, str):
        raise HookRefusal("cwd is missing or not a string; nothing was written.")
    path = Path(cwd)
    if not path.is_dir():
        return None
    return utils.find_aos_dir(path)


def _extract_envelope(message: str) -> str | None:
    """Exactly one fenced aos-dropfile block, or None when there is none.
    Two or more refuse: with one staged record per session, publishing an
    arbitrary winner would silently drop the others."""
    normalized = message.replace("\r\n", "\n").replace("\r", "\n")
    blocks = _ENVELOPE_RE.findall(normalized)
    if not blocks:
        return None
    if len(blocks) > 1:
        raise HookRefusal(
            f"found {len(blocks)} {ENVELOPE_FENCE} envelopes in the final "
            "message (exactly one is required); nothing was staged."
        )
    return blocks[0] + "\n"


def _validate_envelope(envelope: str) -> dict:
    """The manual-ingest validators, applied before a byte is staged or
    published: U-C1 size cap, the strict dropfile parser, the U-C3 scanner."""
    raw = envelope.encode("utf-8")
    if len(raw) > ingest.MAX_DROPFILE_BYTES:
        raise HookRefusal(
            f"envelope is {len(raw)} bytes "
            f"(max {ingest.MAX_DROPFILE_BYTES}); nothing was staged."
        )
    try:
        doc = ingest.parse_dropfile(envelope)
    except AosError as exc:
        # parse errors name line NUMBERS and expected shapes only — safe.
        raise HookRefusal(f"envelope is not a valid dropfile: {exc}")
    findings = ingest.secret_findings(doc)
    if findings:
        raise HookRefusal(
            "secret-shaped content detected in the envelope — "
            + "; ".join(findings)
            + ". Nothing was staged or published."
        )
    return doc


def _owned_dir_state(path: Path) -> str:
    """'absent' or 'dir'. A symlink or non-directory at an owned name — or
    an inspection error other than 'absent' — refuses; nothing is ever read
    or written through a path component the workspace does not really own."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return "absent"
    except OSError as exc:
        raise HookRefusal(
            f"cannot inspect {path} "
            f"({exc.__class__.__name__}); nothing was written."
        )
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        raise HookRefusal(
            f"{path} is not a real directory (symlink or non-directory); "
            "refusing to touch it."
        )
    return "dir"


def _require_owned_dir(path: Path, create: bool) -> None:
    """`path` must be a real (non-symlink) directory; optionally create it."""
    if _owned_dir_state(path) == "dir":
        return
    if not create:
        raise HookRefusal(f"{path} does not exist; nothing was written.")
    try:
        os.mkdir(path)
    except FileExistsError:
        _require_owned_dir(path, create=False)
    except OSError as exc:
        raise HookRefusal(
            f"cannot create {path} "
            f"({exc.__class__.__name__}); nothing was written."
        )


def _read_regular_file(path: Path, cap: int, what: str) -> bytes:
    """Read an owned file without following a symlink at the final
    component; anything but a small regular file refuses."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise HookRefusal(
            f"cannot open {what} ({exc.__class__.__name__}); "
            "nothing was written."
        )
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise HookRefusal(f"{what} is not a regular file; refusing.")
        if st.st_size > cap:
            raise HookRefusal(
                f"{what} exceeds the {cap}-byte cap; refusing."
            )
        with os.fdopen(fd, "rb") as fh:
            fd = -1
            data = fh.read(cap + 1)
    finally:
        if fd != -1:
            os.close(fd)
    if len(data) > cap:
        raise HookRefusal(f"{what} exceeds the {cap}-byte cap; refusing.")
    return data


def _fsync_dir(path: Path) -> None:
    """Best-effort directory fsync (some filesystems reject it; the write
    itself has already been fsynced)."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _atomic_write(directory: Path, final: Path, data: bytes, *, replace: bool) -> None:
    """Same-directory temp file + fsync, then os.replace (replace=True) or
    os.link (replace=False — never overwrites; FileExistsError propagates).
    Any failure removes the temp file: no partial file ever sits at a
    meaningful name."""
    fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=".aos-hook-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if replace:
            os.replace(tmp, final)
        else:
            os.link(tmp, final)
            os.unlink(tmp)
        _fsync_dir(directory)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _staged_path(aos_dir: Path, session_id: str) -> Path:
    return aos_dir / "exports" / STAGING_DIR_NAME / f"stop-{session_id}.json"


def _staged_record_bytes(session_id: str, envelope: str) -> bytes:
    record = {
        "format": STAGED_FORMAT,
        "session_id": session_id,
        "envelope_sha256": utils.sha256_text(envelope),
        "envelope": envelope,
    }
    return (
        json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")


def _run_stop(data: dict) -> int:
    if data.get("hook_event_name") != "Stop":
        raise HookRefusal(
            "expected a Stop event (official hook_event_name mismatch); "
            "nothing was staged."
        )
    session_id = _validated_session_id(data)
    message = data.get("last_assistant_message")
    if message is None:
        return 0  # no final message — nothing to look at
    if not isinstance(message, str):
        raise HookRefusal(
            "last_assistant_message is not a string; nothing was staged."
        )
    aos_dir = _find_workspace(data)
    if aos_dir is None:
        return 0  # not an AOS workspace — the hook has no business here
    envelope = _extract_envelope(message)
    if envelope is None:
        return 0  # clean no-op: sessions without a write-back are normal
    doc = _validate_envelope(envelope)

    exports = aos_dir / "exports"
    _require_owned_dir(exports, create=True)
    staging = exports / STAGING_DIR_NAME
    _require_owned_dir(staging, create=True)
    staged = _staged_path(aos_dir, session_id)
    record = _staged_record_bytes(session_id, envelope)
    try:
        st = os.lstat(staged)
    except FileNotFoundError:
        st = None
    except OSError as exc:
        raise HookRefusal(
            f"cannot inspect the staged record "
            f"({exc.__class__.__name__}); nothing was staged."
        )
    if st is not None and not stat.S_ISREG(st.st_mode):
        raise HookRefusal(
            "an entry that is not a regular file sits at the staging name; "
            "refusing to replace it."
        )
    if st is not None and _read_regular_file(
        staged, MAX_STAGED_RECORD_BYTES, "the staged record"
    ) == record:
        print(
            f"aos-hook[stop]: write-back for {doc['task']} already staged "
            "(identical envelope); SessionEnd publishes it.",
            file=sys.stderr,
        )
        return 0
    try:
        # replace=True: at most one staged record per session, latest wins.
        _atomic_write(staging, staged, record, replace=True)
    except OSError as exc:
        raise HookRefusal(
            f"could not stage the envelope "
            f"({exc.__class__.__name__}); no partial record was left."
        )
    print(
        f"aos-hook[stop]: staged write-back envelope for {doc['task']} "
        f"(agent {doc['agent']}, sha256 "
        f"{utils.sha256_text(envelope)[:12]}); SessionEnd publishes it.",
        file=sys.stderr,
    )
    return 0


def dropfile_name(doc: dict, session_id: str, digest: str) -> str:
    """Deterministic, collision-safe published name. Every component is
    validated (task/agent by the dropfile parser, session id by charset) and
    the digest is the dedupe identity — the same sha256 ingest records."""
    return (
        f"dropfile-{doc['task']}-{doc['agent']}-hook-"
        f"{session_id[:8]}-{digest[:12]}.md"
    )


def _run_session_end(data: dict) -> int:
    if data.get("hook_event_name") != "SessionEnd":
        raise HookRefusal(
            "expected a SessionEnd event (official hook_event_name "
            "mismatch); nothing was published."
        )
    reason = data.get("reason")
    if not isinstance(reason, str) or reason not in SESSION_END_REASONS:
        raise HookRefusal(
            "unsupported SessionEnd reason (documented values: "
            + "|".join(SESSION_END_REASONS)
            + "); nothing was published."
        )
    session_id = _validated_session_id(data)
    aos_dir = _find_workspace(data)
    if aos_dir is None:
        return 0
    # The owned directories are checked BEFORE the staged path is even
    # stat'ed — a symlinked exports/ or hook-staging/ must not be traversed.
    exports = aos_dir / "exports"
    if _owned_dir_state(exports) == "absent":
        return 0  # nothing was ever staged — clean no-op
    if _owned_dir_state(exports / STAGING_DIR_NAME) == "absent":
        return 0
    staged = _staged_path(aos_dir, session_id)
    try:
        st = os.lstat(staged)
    except FileNotFoundError:
        return 0  # nothing staged for this session — clean no-op
    except OSError as exc:
        raise HookRefusal(
            f"cannot inspect the staged record "
            f"({exc.__class__.__name__}); nothing was published."
        )
    if not stat.S_ISREG(st.st_mode):
        raise HookRefusal(
            "the staged record is not a regular file; refusing to publish. "
            f"Inspect and remove it manually: {staged}"
        )

    raw = _read_regular_file(staged, MAX_STAGED_RECORD_BYTES, "the staged record")
    try:
        record = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise HookRefusal(
            "the staged record is not valid JSON; refusing to publish. "
            f"Inspect and remove it manually: {staged}"
        )
    if not isinstance(record, dict) or record.get("format") != STAGED_FORMAT:
        raise HookRefusal(
            "the staged record does not carry the expected format marker "
            f"({STAGED_FORMAT}); refusing to publish. Inspect and remove "
            f"it manually: {staged}"
        )
    if record.get("session_id") != session_id:
        raise HookRefusal(
            "the staged record is not bound to this session; refusing to "
            f"publish. Inspect and remove it manually: {staged}"
        )
    envelope = record.get("envelope")
    if not isinstance(envelope, str):
        raise HookRefusal(
            "the staged record has no envelope text; refusing to publish. "
            f"Inspect and remove it manually: {staged}"
        )
    digest = utils.sha256_text(envelope)
    if record.get("envelope_sha256") != digest:
        raise HookRefusal(
            "the staged record's content digest does not match its "
            "envelope (replaced or corrupted); refusing to publish. "
            f"Inspect and remove it manually: {staged}"
        )
    # Full re-validation immediately before publication: the staged file
    # sat on disk between the two hooks and is treated as untrusted again.
    doc = _validate_envelope(envelope)

    final = exports / dropfile_name(doc, session_id, digest)
    payload = envelope.encode("utf-8")

    published = _publish(exports, final, payload)
    if published == "identical":
        _remove_staged(staged)
        print(
            f"aos-hook[session-end]: dropfile already published "
            f"(identical bytes): {final}",
            file=sys.stderr,
        )
        return 0
    _remove_staged(staged)
    print(
        f"aos-hook[session-end]: published {final} (sha256 {digest[:12]}). "
        f"Ingest stays manual: python aos.py ingest dropfile {final}",
        file=sys.stderr,
    )
    return 0


def _publish(exports: Path, final: Path, payload: bytes) -> str:
    """Atomic no-overwrite publication. Returns 'written' or 'identical'
    (idempotent retry); anything else refuses with the staging retained."""

    def existing_matches() -> bool:
        try:
            st = os.lstat(final)
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise HookRefusal(
                f"cannot inspect the existing dropfile "
                f"({exc.__class__.__name__}); nothing was published."
            )
        if not stat.S_ISREG(st.st_mode):
            raise HookRefusal(
                "an entry that is not a regular file sits at the dropfile "
                f"name; refusing to publish. Inspect it manually: {final}"
            )
        if _read_regular_file(
            final, ingest.MAX_DROPFILE_BYTES, "the existing dropfile"
        ) != payload:
            raise HookRefusal(
                "a different file already exists at the deterministic "
                "dropfile name; refusing to overwrite it. The staged "
                f"record was retained. Inspect: {final}"
            )
        return True

    if existing_matches():
        return "identical"
    try:
        _atomic_write(exports, final, payload, replace=False)
    except FileExistsError:
        # Raced by a concurrent retry: accept only the identical outcome.
        if existing_matches():
            return "identical"
        raise HookRefusal(
            "the dropfile name was taken mid-publication; refusing. "
            f"The staged record was retained. Inspect: {final}"
        )
    except OSError as exc:
        raise HookRefusal(
            f"could not publish the dropfile "
            f"({exc.__class__.__name__}); no partial file was left and "
            "the staged record was retained."
        )
    return "written"


def _remove_staged(staged: Path) -> None:
    """Post-publication staging removal. Publication is already durable, so
    a failure here WARNs (the stale record will no-op or refuse loudly on
    retry — never double-publish, thanks to the deterministic name)."""
    try:
        os.unlink(staged)
    except OSError as exc:
        print(
            f"aos-hook[session-end]: WARN: published, but the staged record "
            f"could not be removed ({exc.__class__.__name__}); remove it "
            f"manually: {staged}",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Installer (CLI side: aos hooks install/status/uninstall)

HOOK_PROTOCOL_VERSION = "u-h1/1"
HOOK_EVENTS = ("Stop", "SessionEnd")

#: Ownership marker: an entry is AOS-owned iff its command carries the
#: runner filename. Deterministic and documented — do not name your own
#: hooks after it.
RUNNER_FILENAME = "aos_hooks.py"

_EVENT_ARGS = {"Stop": "stop", "SessionEnd": "session-end"}


def default_runner_path() -> Path:
    """The aos_hooks.py that ships beside aos.py in this checkout."""
    return Path(__file__).resolve().parent.parent / RUNNER_FILENAME


def default_settings_path() -> Path:
    """The documented Claude Code user settings file."""
    return Path.home() / ".claude" / "settings.json"


def hook_command(event: str, runner: Path | None = None) -> str:
    runner = runner if runner is not None else default_runner_path()
    return f"python3 {shlex.quote(str(runner))} {_EVENT_ARGS[event]}"


def owned_entry(event: str, runner: Path | None = None) -> dict:
    return {"type": "command", "command": hook_command(event, runner)}


def is_owned(entry) -> bool:
    return (
        isinstance(entry, dict)
        and entry.get("type") == "command"
        and isinstance(entry.get("command"), str)
        and RUNNER_FILENAME in entry["command"]
    )


def install_digest(runner: Path | None = None) -> str:
    """sha256 over the exact handlers this checkout installs — the
    'installed digest/version' status line and drift reference."""
    doc = {
        "version": HOOK_PROTOCOL_VERSION,
        "Stop": hook_command("Stop", runner),
        "SessionEnd": hook_command("SessionEnd", runner),
    }
    return utils.sha256_text(json.dumps(doc, sort_keys=True))


def _validate_settings_shape(doc, path: Path) -> None:
    """Refuse unsupported structures before ANY mutation. Only the parts we
    would touch are validated; unrelated keys/events pass through the JSON
    round-trip untouched."""
    if not isinstance(doc, dict):
        raise AosError(
            f"Unsupported settings structure in {path}: the root is not a "
            "JSON object. Nothing was changed."
        )
    hooks = doc.get("hooks")
    if hooks is None:
        return
    if not isinstance(hooks, dict):
        raise AosError(
            f"Unsupported settings structure in {path}: 'hooks' is not a "
            "JSON object. Nothing was changed."
        )
    for event in HOOK_EVENTS:
        groups = hooks.get(event)
        if groups is None:
            continue
        if not isinstance(groups, list):
            raise AosError(
                f"Unsupported settings structure in {path}: "
                f"hooks.{event} is not a list. Nothing was changed."
            )
        for group in groups:
            if not isinstance(group, dict):
                raise AosError(
                    f"Unsupported settings structure in {path}: an entry "
                    f"under hooks.{event} is not an object. "
                    "Nothing was changed."
                )
            entries = group.get("hooks")
            if entries is not None and not isinstance(entries, list):
                raise AosError(
                    f"Unsupported settings structure in {path}: a "
                    f"hooks.{event} group's 'hooks' is not a list. "
                    "Nothing was changed."
                )


def _load_settings(path: Path) -> tuple[dict, bytes | None]:
    """Parse and validate the existing settings. Returns (document,
    original bytes) — ({}, None) when the file does not exist."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return {}, None
    except OSError as exc:
        raise AosError(
            f"Cannot inspect settings file {path} "
            f"({exc.__class__.__name__}). Nothing was changed."
        )
    if stat.S_ISLNK(st.st_mode):
        raise AosError(
            f"Settings path {path} is a symlink; refusing to modify it. "
            "Point --settings at the real file. Nothing was changed."
        )
    if not stat.S_ISREG(st.st_mode):
        raise AosError(
            f"Settings path {path} is not a regular file. "
            "Nothing was changed."
        )
    raw = path.read_bytes()
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise AosError(
            f"Settings file {path} is not valid UTF-8 JSON; fix or move it "
            "first. Nothing was changed."
        )
    _validate_settings_shape(doc, path)
    return doc, raw


def _strip_owned(groups: list) -> bool:
    """Remove AOS-owned command hooks from `groups` in place. A group left
    with an empty hook list — and nothing but a matcher besides — is
    dropped; anything else the user put there is preserved."""
    changed = False
    for group in list(groups):
        entries = group.get("hooks")
        if not isinstance(entries, list):
            continue
        kept = [entry for entry in entries if not is_owned(entry)]
        if len(kept) == len(entries):
            continue
        changed = True
        if kept:
            group["hooks"] = kept
        elif set(group.keys()) <= {"hooks", "matcher"}:
            groups.remove(group)
        else:
            group["hooks"] = []
    return changed


def merged_settings(doc: dict, runner: Path | None = None) -> dict:
    """The install result: exactly one AOS-owned group per event, appended
    last; pre-existing AOS-owned entries (drifted or duplicated) are
    removed first, so repeated install converges. The input is not
    mutated."""
    new = copy.deepcopy(doc)
    hooks = new.setdefault("hooks", {})
    for event in HOOK_EVENTS:
        groups = hooks.get(event)
        if not isinstance(groups, list):
            groups = []
            hooks[event] = groups
        _strip_owned(groups)
        groups.append({"hooks": [owned_entry(event, runner)]})
    return new


def uninstalled_settings(doc: dict) -> dict:
    """The uninstall result: only AOS-owned entries removed; an event array
    our removal emptied is dropped, and the 'hooks' object is dropped only
    if it was not empty before (byte-semantic preservation elsewhere)."""
    new = copy.deepcopy(doc)
    hooks = new.get("hooks")
    if not isinstance(hooks, dict):
        return new
    for event in HOOK_EVENTS:
        groups = hooks.get(event)
        if not isinstance(groups, list):
            continue
        if _strip_owned(groups) and not groups:
            del hooks[event]
    if not hooks and doc.get("hooks"):
        del new["hooks"]
    return new


def render_settings(doc: dict) -> str:
    return json.dumps(doc, indent=2, ensure_ascii=False) + "\n"


@dataclass
class SettingsPlan:
    path: Path
    original: bytes | None  # None: file absent
    old_doc: dict
    new_doc: dict

    @property
    def changed(self) -> bool:
        """Semantic idempotency: a file already carrying exactly the merged
        document needs no rewrite — even if its formatting differs."""
        if self.original is None:
            return self.old_doc != self.new_doc or bool(self.new_doc)
        return self.old_doc != self.new_doc

    @property
    def new_text(self) -> str:
        return render_settings(self.new_doc)

    def diff_lines(self) -> list[str]:
        old_text = (
            self.original.decode("utf-8") if self.original is not None else ""
        )
        return list(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                self.new_text.splitlines(keepends=True),
                fromfile=(
                    str(self.path)
                    if self.original is not None
                    else f"{self.path} (absent)"
                ),
                tofile=f"{self.path} (planned)",
            )
        )


def plan_install(path: Path, runner: Path | None = None) -> SettingsPlan:
    doc, raw = _load_settings(path)
    return SettingsPlan(
        path=path, original=raw, old_doc=doc, new_doc=merged_settings(doc, runner)
    )


def plan_uninstall(path: Path) -> SettingsPlan:
    doc, raw = _load_settings(path)
    return SettingsPlan(
        path=path, original=raw, old_doc=doc, new_doc=uninstalled_settings(doc)
    )


def _backup_path(path: Path) -> Path:
    stamp = utils.utc_now_iso().replace(":", "").replace("-", "")
    candidate = path.with_name(f"{path.name}.aos-backup-{stamp}")
    counter = 1
    while candidate.exists():
        counter += 1
        candidate = path.with_name(f"{path.name}.aos-backup-{stamp}-{counter}")
    return candidate


def apply_plan(plan: SettingsPlan) -> Path | None:
    """Back up, validate, and atomically replace. Returns the backup path
    (None when the file did not exist). Assumes plan.changed."""
    parent = plan.path.parent
    if not parent.is_dir():
        raise AosError(
            f"Settings directory {parent} does not exist; create it first "
            "(is Claude Code set up?). Nothing was changed."
        )
    new_text = plan.new_text
    # Validate the exact bytes that will land before anything is touched.
    reparsed = json.loads(new_text)
    _validate_settings_shape(reparsed, plan.path)
    if reparsed != plan.new_doc:
        raise AosError(
            "Internal consistency check failed rendering the new settings; "
            "nothing was changed."
        )

    backup = None
    if plan.original is not None:
        backup = _backup_path(plan.path)
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(plan.original)
                fh.flush()
                os.fsync(fh.fileno())
        except BaseException:
            try:
                os.unlink(backup)
            except OSError:
                pass
            raise

    fd, tmp_name = tempfile.mkstemp(
        dir=parent, prefix=".aos-settings-", suffix=".tmp"
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(new_text.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        if plan.original is not None:
            os.chmod(tmp, stat.S_IMODE(os.lstat(plan.path).st_mode))
        else:
            os.chmod(tmp, 0o600)
        os.replace(tmp, plan.path)
        _fsync_dir(parent)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return backup


def status(path: Path, runner: Path | None = None) -> dict:
    """absent | installed | drifted, judged over every AOS-owned entry in
    the two event arrays against exactly what this checkout installs."""
    doc, _ = _load_settings(path)
    raw_hooks = doc.get("hooks")
    hooks: dict = raw_hooks if isinstance(raw_hooks, dict) else {}
    owned: dict[str, list[str]] = {}
    for event in HOOK_EVENTS:
        commands = []
        groups = hooks.get(event)
        if isinstance(groups, list):
            for group in groups:
                entries = group.get("hooks")
                if not isinstance(entries, list):
                    continue
                commands += [
                    entry["command"] for entry in entries if is_owned(entry)
                ]
        owned[event] = commands
    expected = {event: [hook_command(event, runner)] for event in HOOK_EVENTS}
    if not any(owned.values()):
        state = "absent"
    elif owned == expected:
        state = "installed"
    else:
        state = "drifted"
    return {
        "state": state,
        "settings": str(path),
        "version": HOOK_PROTOCOL_VERSION,
        "digest": install_digest(runner),
        "owned": owned,
    }
