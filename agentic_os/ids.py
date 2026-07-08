"""Human-facing IDs: T-0001 tasks, R-0001 runs, D-0001 decisions,
E-0001 evidence, H-0001 handoffs, P-0001 packs, M-0001 memory.

Render: prefix + zero-padded integer, minimum width 4, growing naturally
past 9999. Parse: strict — correct prefix for the command (case-insensitive),
ASCII digits only, value between 1 and MAX_ID; anything else is a domain
error (exit code 1) refused before any DB lookup.
"""

from __future__ import annotations

import re

from .utils import AosError

PREFIXES = {
    "task": "T",
    "run": "R",
    "decision": "D",
    "evidence": "E",
    "handoff": "H",
    "pack": "P",
    "memory": "M",
}

#: Upper bound for parsed ids (D-v0.2.2): SQLite INTEGER is a signed 64-bit
#: value, so no row can ever carry an id above 2**63-1 — bigger ids used to
#: overflow the bind and exit 2. Magnitude is judged after stripping leading
#: zeros (zero-padding stays legal, as ever); the digit-length pre-check
#: keeps CPython's int-conversion limit (~4300 digits) unreachable.
MAX_ID = 2**63 - 1
_MAX_ID_DIGITS = len(str(MAX_ID))

_ID_RE = re.compile(r"^([A-Za-z]+)-([0-9]+)\Z", re.ASCII)


def render_id(entity: str, n: int) -> str:
    return f"{PREFIXES[entity]}-{n:04d}"


def parse_id(text: str, entity: str) -> int:
    prefix = PREFIXES[entity]
    cleaned = text.strip()
    match = _ID_RE.match(cleaned)
    if not match or match.group(1).upper() != prefix:
        raise AosError(
            f"Invalid {entity} id {cleaned!r}. Expected format: {prefix}-0001"
        )
    digits = match.group(2).lstrip("0")
    if not digits:
        raise AosError(
            f"Invalid {entity} id {cleaned!r}: ids start at {prefix}-0001."
        )
    if len(digits) > _MAX_ID_DIGITS or int(digits) > MAX_ID:
        raise AosError(
            f"Invalid {entity} id: the numeric part exceeds the maximum "
            f"({prefix}-{MAX_ID})."
        )
    return int(digits)
