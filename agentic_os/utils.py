"""Shared low-level helpers: clock, hashing, file writing, root discovery.

`utc_now_iso()` is the ONLY place in the codebase that reads the wall clock.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

AOS_DIR_NAME = ".agentic-os"
DB_FILENAME = "aos.db"


class AosError(Exception):
    """User/domain error: one actionable line on stderr, exit code 1."""

    exit_code = 1


def utc_now_iso() -> str:
    """Current UTC time as ISO-8601 with Z suffix, e.g. 2026-07-07T21:04:00Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_today() -> str:
    """Current UTC date (YYYY-MM-DD), derived from the single clock."""
    return utc_now_iso()[:10]


_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}\Z", re.ASCII)


def validate_date(text: str, what: str) -> str:
    """Strict YYYY-MM-DD; must be a real calendar date."""
    if not _DATE_RE.match(text):
        raise AosError(f"Invalid {what} {text!r}. Expected format: YYYY-MM-DD")
    try:
        date.fromisoformat(text)
    except ValueError:
        raise AosError(f"Invalid {what} {text!r}: not a real calendar date.")
    return text


def json_dumps(obj) -> str:
    """Canonical JSON for stdout: readable, UTF-8, stable key order as built."""
    return json.dumps(obj, indent=2, ensure_ascii=False)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize_lf(text: str) -> str:
    """CR bytes in user-supplied field values must never reach generated
    files (the LF-only guarantee covers content, not just line endings we
    add ourselves)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def write_text_lf(path: Path, text: str) -> None:
    """Write UTF-8 text with LF newlines and a trailing final newline."""
    text = _normalize_lf(text)
    if not text.endswith("\n"):
        text += "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def write_text_lf_if_changed(path: Path, text: str) -> bool:
    """write_text_lf, but skip the write when the bytes would be identical.

    Returns True when the file was (re)written.
    """
    text = _normalize_lf(text)
    if not text.endswith("\n"):
        text += "\n"
    new_bytes = text.encode("utf-8")
    if path.is_file() and path.read_bytes() == new_bytes:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(new_bytes)
    return True


def tree_hash(root: Path) -> str:
    """sha256 over the sorted sequence of (posix relpath + "\\0" + file bytes)."""
    h = hashlib.sha256()
    entries = sorted(
        (p.relative_to(root).as_posix(), p) for p in root.rglob("*") if p.is_file()
    )
    for rel, path in entries:
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
    return h.hexdigest()


def find_aos_dir(start: Path | None = None) -> Path | None:
    """Walk up from `start` (default: cwd) to the nearest initialized workspace."""
    cur = (start or Path.cwd()).resolve()
    for candidate in (cur, *cur.parents):
        aos_dir = candidate / AOS_DIR_NAME
        if (aos_dir / DB_FILENAME).is_file():
            return aos_dir
    return None


def require_aos_dir(start: Path | None = None) -> Path:
    aos_dir = find_aos_dir(start)
    if aos_dir is None:
        raise AosError("Not initialized. Run: python aos.py init")
    return aos_dir


def aos_dir_for_root(root: Path) -> Path:
    """Explicit --root PATH: the workspace is PATH/.agentic-os exactly —
    no upward search. Explicit always beats discovery."""
    aos_dir = root / AOS_DIR_NAME
    if not (aos_dir / DB_FILENAME).is_file():
        raise AosError(
            f"Not initialized at {root}. Run: python aos.py --root {root} init"
        )
    return aos_dir
