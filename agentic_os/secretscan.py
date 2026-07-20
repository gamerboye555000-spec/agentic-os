"""One shared, side-effect-free secret detector (U-C3, D-v0.2.15).

Every boundary that judges text for credential shapes uses this module:
pack construction (hard refusal), untrusted dropfile ingest (atomic hard
refusal), trusted human CLI writes (warn on stderr, safe metadata in the
mutation event), and doctor's ledger sweep. One detector means one answer
to "is this secret-shaped?" everywhere.

Match results carry pattern NAMES and caller-supplied field labels only —
never the matched text, an excerpt, an offset, or any hash/fingerprint of
the value. Deterministic input yields deterministic, deduplicated names.

Event payloads get one more guarantee here: redact_tree replaces every
secret-shaped string leaf with the fixed REDACTED_VALUE placeholder, so a
matched value — including one accepted into a domain row by an earlier
warned write and copied forward as an identifier — can never be journaled.
events.emit applies the same redaction to the top-level actor column (a
syntactically valid evidence provenance can be credential-shaped), so the
no-value rule holds for the whole event record, not just the payload.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable

SECRET_PATTERNS = (
    ("pem-private-key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("aws-access-key-id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "github-token",
        re.compile(r"\b(?:ghp_|gho_|ghs_|github_pat_)[A-Za-z0-9_]{20,}"),
    ),
    ("sk-api-key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    (
        "credential-assignment",
        # Optional closing quote after the keyword catches the quoted-key
        # forms ("password": "...", 'api_key': '...') JSON/YAML/dicts use.
        re.compile(
            r"(?i)\b(?:password|passwd|secret|token|api_key|apikey)\b"
            r"[\"']?\s*[:=]\s*\S{8,}"
        ),
    ),
)

#: Every name scan_secrets can return, in canonical (detector) order —
#: the stable sort key for deduplicated cross-field pattern unions.
PATTERN_NAMES = tuple(name for name, _ in SECRET_PATTERNS) + (
    "high-entropy-near-keyword",
)

#: Canonical field labels the trusted-write scan is allowed to use
#: (ops._scan_trusted_write rejects any other label at write time).
#: Doctor accepts `secret_fields` event-metadata names only from this set,
#: so tampered metadata can never smuggle arbitrary text into its output.
TRUSTED_FIELD_LABELS = frozenset(
    {
        "acceptance",
        "agent",
        "alternatives",
        # U-A1 passport free-text declarations. role/mission are prose the
        # operator typed about an agent; a limitation, approval action or
        # task family is a short string — all reach the mirror and exports,
        # so all are scanned at the write boundary.
        "approval",
        "capabilities",
        "claim",
        # U-A3 governed handoff prose. objective/constraint are bounded human
        # descriptions of a delegation; handoff_note is a per-transition note
        # (deliberately NOT `note`, which would sit beside `notes` and invite
        # confusion). All three reach exports and the mirror, so all are
        # scanned at the trusted-write boundary.
        "constraint",
        "decision",
        "from_agent",
        "handoff_note",
        "key",
        "limitation",
        # U-M3 memory sources. A locator is a path, URL or command string the
        # operator asked the ledger to remember — exactly the shape that
        # carries a token in a query string.
        "locator",
        "mission",
        "name",
        "notes",
        "objective",
        "provenance",
        "reason",
        "ref",
        "repo_path",
        "role",
        "slug",
        "source",
        "spec",
        "state",
        "summary",
        "task_family",
        "title",
        "to_agent",
        "value",
    }
)

#: The one deterministic stand-in for a secret-shaped string leaf in an
#: event payload. A fixed sentence, deliberately: it carries nothing
#: derived from the value (no hash, excerpt, length, or offset) and is
#: itself negative under scan_secrets.
REDACTED_VALUE = "[secret-shaped value withheld]"

_ENTROPY_RUN = re.compile(r"[A-Za-z0-9+/=]{40,}")
_KEYWORD_NEARBY = re.compile(r"(?i)\b(?:key|secret|token)\b")
_HEX_ONLY = re.compile(r"^[0-9a-fA-F]+$")


def _shannon_entropy(text: str) -> float:
    counts = Counter(text)
    n = len(text)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def scan_secrets(text: str) -> list[str]:
    """Return the NAMES of matched secret patterns (never the matches)."""
    hits = []
    for name, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            hits.append(name)
    for match in _ENTROPY_RUN.finditer(text):
        run = match.group(0)
        threshold = 3.0 if _HEX_ONLY.match(run) else 4.0
        if _shannon_entropy(run) < threshold:
            continue
        window = text[max(0, match.start() - 40) : match.end() + 40]
        if _KEYWORD_NEARBY.search(window):
            hits.append("high-entropy-near-keyword")
            break
    return hits


def scan_fields(
    fields: Iterable[tuple[str, str | None]],
) -> list[tuple[str, list[str]]]:
    """Scan labeled field values; return [(label, pattern names)] for the
    fields with hits, in input order. None/empty values are skipped.
    Labels are the caller's safe field names — values never leave here."""
    findings = []
    for label, value in fields:
        if not value:
            continue
        hits = scan_secrets(value)
        if hits:
            findings.append((label, hits))
    return findings


def merge_pattern_names(findings: list[tuple[str, list[str]]]) -> list[str]:
    """Deduplicated union of pattern names across scan_fields findings,
    in canonical detector order (stable for identical input)."""
    seen = {name for _, hits in findings for name in hits}
    return [name for name in PATTERN_NAMES if name in seen]


def redact_tree(value):
    """Return `value` with every secret-shaped string leaf — nested
    lists/dicts included — replaced by REDACTED_VALUE. Benign strings and
    non-string leaves pass through unchanged, so an unaffected payload
    stays byte-identical. The input is never mutated."""
    if isinstance(value, str):
        return REDACTED_VALUE if scan_secrets(value) else value
    if isinstance(value, dict):
        return {key: redact_tree(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_tree(child) for child in value]
    return value
