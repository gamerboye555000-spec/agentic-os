"""Human-facing IDs: T-0001 tasks, R-0001 runs, D-0001 decisions,
E-0001 evidence, H-0001 handoffs, P-0001 packs.

Render: prefix + zero-padded integer, minimum width 4, growing naturally
past 9999. Parse: strict — correct prefix for the command (case-insensitive),
ASCII digits only; anything else is a domain error (exit code 1).
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
}

_ID_RE = re.compile(r"^([A-Za-z]+)-([0-9]+)$", re.ASCII)


def render_id(entity: str, n: int) -> str:
    return f"{PREFIXES[entity]}-{n:04d}"


def parse_id(text: str, entity: str) -> int:
    prefix = PREFIXES[entity]
    match = _ID_RE.match(text.strip())
    if not match or match.group(1).upper() != prefix:
        raise AosError(
            f"Invalid {entity} id {text.strip()!r}. Expected format: {prefix}-0001"
        )
    return int(match.group(2))
