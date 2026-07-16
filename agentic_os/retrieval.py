"""U-M5 deterministic retrieval candidate + benchmark harness.

Contract: agentic-os-v0.3-u-m5-retrieval-evals-contract.md

This module measures retrieval. It does not perform it in production: nothing
here is called by `search.py`, `pack.py` or `ops.memory_for_project`, and no
command in this unit changes what any of them return (D-v0.3.52).

Four things live here, in this order:

1. The tokenizer (M5.2) — one definition, used for queries and claims alike.
2. The corpus (M5.3) and the eligibility predicate (M5.4) — one predicate,
   fed by a real ledger or by an embedded synthetic fixture.
3. The three candidates (M5.6) and bounded depth-1 graph expansion (M5.7).
4. The embedded benchmark datasets (M5.10), the metrics (M5.9), the promotion
   gate and the recommendation (M5.12).

Standard library only, and deliberately: no embedding, no vector store, no
model call, no network, no new dependency. U-M5 exists to decide whether any
of that is warranted; shipping it inside the unit that measures the need for
it would be assuming the answer.

Nothing here dereferences anything (M5.15). No `open()` of a locator, no URL
fetch, no subprocess, no artifact import. `socket`, `urllib`, `subprocess` and
`http` are not imported, and the tests prove the surface still works with
those primitives patched to raise.

Every number is an integer, an ordinal or a `fractions.Fraction`. No float is
constructed, compared, summed or serialized (D-v0.3.54) — including nDCG,
whose discount comes from a checked-in exact-rational table (D-v0.3.55).
"""

from __future__ import annotations

import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from fractions import Fraction
from pathlib import Path

from . import ids, models, ops, protocols, utils
from .models import (
    MEMORY_EDGE_CONTRADICTS,
    MEMORY_EDGE_RELATIONS,
    MEMORY_EDGE_SYMMETRIC,
    MEMORY_KINDS,
    MEMORY_SCOPES,
    MEMORY_SENSITIVITIES,
    MEMORY_SENSITIVITY_RESTRICTED,
    MEMORY_SOURCE_RELATIONS,
    MEMORY_STATUS_LIVE,
    MEMORY_STATUSES,
    MemoryItem,
)
from .utils import AosError

# ---------------------------------------------------------------------------
# Bounds (M5.11). Pinned, not tuned.
#
# The split is deliberate and is itself a decision: QUERY bounds refuse, and
# CORPUS/GRAPH bounds truncate-and-report (D-v0.3.63). The caller wrote the
# query and can fix it; the caller did not write the ledger and cannot.

MAX_QUERY_BYTES = 512
MAX_QUERY_CHARS = 256
MAX_QUERY_TOKENS = 32
MAX_CLAIM_TEXT_CHARS = 4096
MAX_POOL_CLAIMS = 500
MAX_RESULTS = 20
MAX_GRAPH_EDGES_SCANNED = 64
MAX_GRAPH_NODES_ADDED = 16
MAX_DATASET_CASES = 64
MAX_FIXTURE_CLAIMS = 64
MAX_FIXTURE_EDGES = 128
MAX_REPORT_BYTES = 262144
K_MIN = 1
K_MAX = 10

#: Depth 0 or 1. Depth 2 does not exist in U-M5 — `ops.MAX_GRAPH_DEPTH` is 2
#: for a different purpose (human inspection via `memory graph`), and reusing
#: it here would silently import that purpose into retrieval.
GRAPH_DEPTHS = (0, 1)

DATASET_VERSION = 1
REGISTRY_VERSION = 1
METRICS_VERSION = 1

#: The projection's home, relative to the repository root (D-v0.3.61).
BENCHMARK_DIRNAME = "retrieval_benchmarks"
REGISTRY_FILENAME = "registry.json"


# ---------------------------------------------------------------------------
# M5.2 Text normalization

#: 33 words, checked in, ASCII, sorted, never loaded from a file. Justified:
#: the lexical component scores distinct-token overlap, and without this an
#: English query's score would be dominated by the articles that appear in
#: every claim. Removing them is also what makes `retrieval query "the"` a
#: meaningful no_usable_tokens answer rather than a match against everything.
STOPWORDS = frozenset(
    (
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "for",
        "from", "has", "have", "how", "in", "into", "is", "it", "its",
        "of", "on", "or", "that", "the", "this", "to", "was", "were",
        "what", "when", "where", "which", "with",
    )
)

#: The one normalization form, named (M5.2). NFKC folds compatibility
#: variants — a fullwidth 'Ａ' and an 'A' are the same token — which is what a
#: human typing a query means, and it is a standard-library table rather than
#: a rule this codebase invented.
NORMALIZATION_FORM = "NFKC"


def _normalize(text: str) -> str:
    """NFKC + casefold. `casefold`, never `lower`: `lower` is subtly
    locale-shaped for a few code points and this must mean one thing on every
    machine that runs the benchmark."""
    return unicodedata.normalize(NORMALIZATION_FORM, text).casefold()


def _scan_tokens(normalized: str) -> list[str]:
    """Maximal runs of `isalnum() or '_'`; everything else separates.

    A hand-written scanner, NOT a regex — so catastrophic backtracking is
    impossible by construction rather than by review. `wrong-project` becomes
    two tokens, which is what a reader of the claim key means by it.
    """
    tokens: list[str] = []
    buf: list[str] = []
    for ch in normalized:
        if ch.isalnum() or ch == "_":
            buf.append(ch)
        elif buf:
            tokens.append("".join(buf))
            buf = []
    if buf:
        tokens.append("".join(buf))
    return tokens


def tokenize(text: str) -> tuple[str, ...]:
    """THE tokenizer. Queries and claim text go through this and nothing else,
    so a query token and a document token cannot be produced by two rules.

    Deduplicates preserving first occurrence: the order is the input's own,
    never a sort, so the token list is stable and explains itself. Reads only;
    its output never reaches a write, and no stored claim is transformed.
    """
    seen: dict[str, None] = {}
    for token in _scan_tokens(_normalize(text)):
        if token in STOPWORDS:
            continue
        seen[token] = None
    return tuple(seen)


def normalized_phrase(text: str) -> str:
    """The phrase form: NFKC + casefold + whitespace runs collapsed to one
    space. Stopwords are NOT removed — a phrase is a phrase."""
    return " ".join(_normalize(text).split())


def query_tokens(query: str) -> tuple[str, ...]:
    """Tokenize a QUERY, enforcing the three pinned bounds.

    All three refuse rather than truncate: a truncated query silently answers
    a different question than the one asked, and the caller has no way to
    know. Bytes and characters are both measured because neither bounds the
    other — 256 astral characters are 1024 bytes; 512 ASCII bytes are 512
    characters.

    The refusals name the bound and the measured size. Never the query.
    """
    size = len(query.encode("utf-8"))
    if size > MAX_QUERY_BYTES:
        raise AosError(
            f"Query is {size} bytes; the maximum is {MAX_QUERY_BYTES}. "
            "Nothing was searched. Ask a shorter question."
        )
    if len(query) > MAX_QUERY_CHARS:
        raise AosError(
            f"Query is {len(query)} characters; the maximum is "
            f"{MAX_QUERY_CHARS}. Nothing was searched. Ask a shorter question."
        )
    tokens = tokenize(query)
    if len(tokens) > MAX_QUERY_TOKENS:
        raise AosError(
            f"Query has {len(tokens)} distinct terms; the maximum is "
            f"{MAX_QUERY_TOKENS}. Nothing was searched. Ask a narrower "
            "question."
        )
    return tokens


# ---------------------------------------------------------------------------
# M5.3 The corpus

@dataclass(frozen=True)
class SourceWindow:
    """One claim↔source link, reduced to what ranking needs: the relation and
    the window. No locator, no provenance, no evidence ref — retrieval cannot
    leak what it never loaded."""

    relation: str
    valid_from: str | None
    valid_until: str | None


@dataclass(frozen=True)
class RetrievalEdge:
    id: int
    from_id: int
    to_id: int
    relation: str
    valid_from: str | None
    valid_until: str | None


@dataclass(frozen=True)
class RetrievalClaim:
    """A claim as retrieval sees it.

    `integrity` is `ops.claim_integrity()`'s answer for a database row, and
    the fixture's declared `hash_valid` for a synthetic one — a fixture claim
    is not a hashed row, so it declares the condition rather than faking its
    cause.
    """

    id: int
    scope: str
    project: str | None
    kind: str
    key: str
    value: str
    status: str
    pinned: bool
    sensitivity: str
    valid_from: str
    valid_until: str | None
    superseded_by: int | None
    integrity: str
    content_sha256: str
    sources: tuple[SourceWindow, ...] = ()

    @property
    def text(self) -> str:
        """Exactly the document `search.py` builds for a memory row:
        `key + "\\n" + value_md`. Same document, so the baseline candidate can
        be compared to the live backend at all (D-v0.3.53)."""
        return self.key + "\n" + self.value


@dataclass(frozen=True)
class Corpus:
    """Claims and edges, already bounded. Immutable: a retriever that could
    mutate its corpus would be one `retrieval query` away from a write."""

    claims: tuple[RetrievalClaim, ...]
    edges: tuple[RetrievalEdge, ...]
    truncation: tuple[tuple[str, int], ...] = ()


@dataclass
class _Prepared:
    """Per-claim derived text, computed once per retrieval."""

    tokens: dict[int, frozenset[str]] = field(default_factory=dict)
    key_tokens: dict[int, tuple[str, ...]] = field(default_factory=dict)
    phrase: dict[int, str] = field(default_factory=dict)
    text_truncated: int = 0


def _prepare(corpus: Corpus) -> _Prepared:
    prepared = _Prepared()
    for claim in corpus.claims:
        text = claim.text
        if len(text) > MAX_CLAIM_TEXT_CHARS:
            text = text[:MAX_CLAIM_TEXT_CHARS]
            prepared.text_truncated += 1
        prepared.tokens[claim.id] = frozenset(tokenize(text))
        prepared.key_tokens[claim.id] = tokenize(claim.key)
        prepared.phrase[claim.id] = normalized_phrase(text)
    return prepared


def corpus_from_db(conn: sqlite3.Connection) -> Corpus:
    """Read a bounded pool from a real v3 ledger. SELECT only.

    NO predicate is applied in SQL — not even the project clause. Two reasons,
    both load-bearing:

    - The BASELINE candidate must see what `aos search` sees, and `aos search`
      has no project filter at all. A corpus pre-filtered by project would
      make the baseline look safe by construction and the whole measurement a
      lie (D-v0.3.53).
    - One eligibility implementation (M5.4), in Python, exercised identically
      by this corpus and by the fixture corpus — instead of a SQL rule and a
      Python rule that must be kept in agreement forever.

    Over the pool cap: the first MAX_POOL_CLAIMS by ascending id, and the
    truncation is reported rather than absorbed (D-v0.3.63).
    """
    rows = conn.execute(
        "SELECT m.*, p.slug AS project_slug FROM memory m "
        "LEFT JOIN projects p ON p.id = m.project_id "
        "ORDER BY m.id LIMIT ?",
        (MAX_POOL_CLAIMS + 1,),
    ).fetchall()
    truncation: list[tuple[str, int]] = []
    if len(rows) > MAX_POOL_CLAIMS:
        rows = rows[:MAX_POOL_CLAIMS]
        truncation.append(("pool", 1))

    kept = {row["id"] for row in rows}
    sources: dict[int, list[SourceWindow]] = {}
    for row in conn.execute(
        "SELECT l.memory_id AS mid, l.relation AS relation, "
        "s.valid_from AS valid_from, s.valid_until AS valid_until "
        "FROM memory_source_links l "
        "JOIN memory_sources s ON s.id = l.source_id "
        "ORDER BY l.id"
    ):
        if row["mid"] not in kept:
            continue
        sources.setdefault(row["mid"], []).append(
            SourceWindow(row["relation"], row["valid_from"], row["valid_until"])
        )

    claims: list[RetrievalClaim] = []
    for row in rows:
        item = MemoryItem.from_row(row)
        claims.append(
            RetrievalClaim(
                id=item.id,
                scope=item.scope,
                project=row["project_slug"],
                kind=item.kind,
                key=item.key,
                value=item.value_md,
                status=item.status,
                pinned=bool(item.pinned),
                sensitivity=item.sensitivity,
                valid_from=item.valid_from,
                valid_until=item.valid_until,
                superseded_by=item.superseded_by,
                # The one place U-M5 asks about integrity, and it asks the
                # existing U-M2/U-M3 function rather than re-deriving the
                # answer (M5.3).
                integrity=ops.claim_integrity(conn, item),
                content_sha256=item.content_sha256,
                sources=tuple(sources.get(item.id, ())),
            )
        )

    edges: list[RetrievalEdge] = []
    for row in conn.execute("SELECT * FROM memory_edges ORDER BY id"):
        if row["from_memory_id"] not in kept or row["to_memory_id"] not in kept:
            continue  # an edge to a claim outside the pool is not traversable
        edges.append(
            RetrievalEdge(
                id=row["id"],
                from_id=row["from_memory_id"],
                to_id=row["to_memory_id"],
                relation=row["relation"],
                valid_from=row["valid_from"],
                valid_until=row["valid_until"],
            )
        )

    return Corpus(tuple(claims), tuple(edges), tuple(truncation))


# ---------------------------------------------------------------------------
# M5.4 Eligibility

ELIGIBILITY_OK = "ok"

#: The closed reason vocabulary, in EVALUATION ORDER. The order is
#: authoritative: the first failing reason is the answer, so a restricted
#: retired claim reports `status`, deterministically, forever.
ELIGIBILITY_REASONS = (
    ELIGIBILITY_OK,
    "status",
    "superseded",
    "restricted",
    "temporal",
    "hash",
    "project",
)


def eligibility(claim: RetrievalClaim, as_of: str, project: str | None) -> str:
    """THE retrieval eligibility predicate (M5.4, D-v0.3.56).

    Strictly stricter than `ops.claim_is_eligible`, in one direction only:
    everything this calls eligible, the pack builder would also carry. The
    first four conditions are `claim_is_eligible`'s, spelled the same way and
    reusing `ops.window_is_active` for the window. The last three are what
    retrieval adds:

    - `hash`: `memory_for_project` deliberately does not re-verify (D-v0.3.21
      — one damaged row must not block every pack in the workspace).
      Retrieval can afford to be stricter because its pool is bounded and its
      exclusions are counted and reported: a dropped claim shows up as a
      reason code, not as silence.
    - `temporal` also covers `valid_from`: `claim_is_eligible` checks expiry
      only, and a claim whose window has not opened is not a fact about the
      requested instant.
    - `project`: global, or the requested project. Without a project, only
      `scope=global` — exactly `memory_for_project(conn, None)`.

    Pinning is NOT here. Pinning is ranking, never permission (U-M2's rule).
    """
    if claim.status != MEMORY_STATUS_LIVE:
        return "status"
    if claim.superseded_by is not None:
        return "superseded"
    if claim.sensitivity == MEMORY_SENSITIVITY_RESTRICTED:
        return "restricted"
    if not ops.window_is_active(claim.valid_from, claim.valid_until, as_of):
        return "temporal"
    if claim.integrity != "ok":
        return "hash"
    if claim.scope == "project" and (project is None or claim.project != project):
        return "project"
    return ELIGIBILITY_OK


def eligible_claims(
    corpus: Corpus, as_of: str, project: str | None
) -> tuple[RetrievalClaim, ...]:
    """Eligible claims, deduped to the latest per (scope, project, key).

    The dedupe is `memory_for_project`'s existing rule, reused rather than
    re-invented, so the candidate can never surface a stale row for a key the
    pack would not show. It runs BEFORE scoring and BEFORE expansion: a graph
    neighbour that is a shadowed row is not a neighbour.
    """
    latest: dict[tuple[str, str | None, str], RetrievalClaim] = {}
    for claim in corpus.claims:
        if eligibility(claim, as_of, project) != ELIGIBILITY_OK:
            continue
        key = (claim.scope, claim.project, claim.key)
        current = latest.get(key)
        if current is None or claim.id > current.id:
            latest[key] = claim
    return tuple(sorted(latest.values(), key=lambda c: c.id))


# ---------------------------------------------------------------------------
# M5.5 Scoring — integers only (D-v0.3.54)

W_LEXICAL_PER_TOKEN = 10
W_PHRASE = 25
W_KEY_EXACT = 40
W_KEY_PER_TOKEN = 5
W_PINNED = 8
W_PROJECT_SCOPE = 6
W_SUPPORT_PER_SOURCE = 4
W_DISPUTE_PER_SOURCE = -6
W_GRAPH_PER_EDGE = 2
W_CONTRADICTION_PER_EDGE = -3

#: Provenance and graph signals are capped at three occurrences. A claim with
#: thirty supporting sources is not ten times better evidenced than one with
#: three; it is a claim someone linked a lot. The cap is what stops link count
#: from becoming the ranking.
MAX_COUNTED_SOURCES = 3
MAX_COUNTED_EDGES = 3

#: (max age in days, points). Buckets, not a curve: a curve needs division,
#: division needs a rational or a float, and freshness does not deserve either.
FRESHNESS_BUCKETS = ((30, 12), (90, 8), (365, 4))

COMPONENT_NAMES = (
    "lexical", "phrase", "key", "pinned", "scope",
    "freshness", "supported", "disputed", "graph", "contradicted",
)

#: The closed reason vocabulary for a result (M5.8). Reason CODES, never text
#: derived from a claim.
RESULT_REASONS = (
    "all_tokens", "phrase", "key_exact", "key_overlap", "pinned",
    "project_scope", "fresh", "supported", "disputed", "graph_supported",
    "contradicted", "graph_expanded",
)

ORIGIN_PRIMARY = "primary"
ORIGIN_EXPANDED = "expanded"
_ORIGIN_ORDINAL = {ORIGIN_PRIMARY: 0, ORIGIN_EXPANDED: 1}


def _age_days(valid_from: str, as_of: str) -> int | None:
    """Whole UTC days between two instants, by calendar date.

    `[:10]` handles both spellings U-M3 pinned (`YYYY-MM-DD` and
    `YYYY-MM-DDTHH:MM:SSZ`) without normalizing either into the other, and
    keeps the arithmetic integral: two `date` objects subtract to a
    `timedelta` whose `.days` is an int. A value that is neither spelling
    scores no freshness rather than raising — freshness is a ranking nicety,
    and a damaged timestamp is doctor's problem, not this query's.
    """
    try:
        start = date.fromisoformat(valid_from[:10])
        end = date.fromisoformat(as_of[:10])
    except (ValueError, TypeError):
        return None
    return (end - start).days


def _freshness(valid_from: str, as_of: str) -> int:
    age = _age_days(valid_from, as_of)
    if age is None or age < 0:
        return 0
    for limit, points in FRESHNESS_BUCKETS:
        if age <= limit:
            return points
    return 0


def _active_sources(claim: RetrievalClaim, as_of: str, relation: str) -> int:
    return sum(
        1
        for source in claim.sources
        if source.relation == relation
        and ops.window_is_active(source.valid_from, source.valid_until, as_of)
    )


def _incident_edges(
    corpus: Corpus, memory_id: int, as_of: str
) -> list[RetrievalEdge]:
    """Active edges touching a claim, in ascending edge id — the one traversal
    order, shared by scoring and expansion so neither can drift."""
    return [
        edge
        for edge in corpus.edges
        if (edge.from_id == memory_id or edge.to_id == memory_id)
        and ops.window_is_active(edge.valid_from, edge.valid_until, as_of)
    ]


def _graph_counts(
    corpus: Corpus, claim: RetrievalClaim, as_of: str, eligible: frozenset[int]
) -> tuple[int, int]:
    """(inbound active supports, active contradictions) — both bounded by the
    corpus and both requiring the OTHER endpoint to be eligible.

    Support is inbound only: `X supports Y` says something about Y, not about
    X. Contradiction is symmetric by U-M3's storage rule (D-v0.3.36), so
    either endpoint counts it.

    Requiring the other endpoint to be eligible is the same rule as everything
    else here: a retired claim's opinion about a live one is not a signal
    retrieval acts on.
    """
    supports = contradictions = 0
    for edge in _incident_edges(corpus, claim.id, as_of):
        other = edge.to_id if edge.from_id == claim.id else edge.from_id
        if other not in eligible:
            continue
        if edge.relation == "supports" and edge.to_id == claim.id:
            supports += 1
        elif edge.relation == MEMORY_EDGE_CONTRADICTS:
            contradictions += 1
    return supports, contradictions


@dataclass(frozen=True)
class Scored:
    claim: RetrievalClaim
    components: tuple[tuple[str, int], ...]
    total: int
    origin: str
    reasons: tuple[str, ...]
    supporting: int
    disputing: int
    contradictions: int
    graph_origin: tuple[tuple[str, str], ...] | None

    @property
    def sort_key(self) -> tuple[int, int, int]:
        """(origin ordinal, -total, memory id) — three integers, ascending.

        The origin ordinal first is D-v0.3.57: every expanded result ranks
        below every primary one, so "a graph neighbour must not outrank a
        strong direct lexical match" is true by construction rather than by
        weight-tuning. The tie-break ends with the numeric memory id, always.
        """
        return (_ORIGIN_ORDINAL[self.origin], -self.total, self.claim.id)


def score_claim(
    corpus: Corpus,
    claim: RetrievalClaim,
    *,
    tokens: frozenset[str],
    key_tokens: tuple[str, ...],
    phrase: str,
    query: tuple[str, ...],
    query_phrase: str,
    as_of: str,
    eligible: frozenset[int],
    origin: str,
    graph_origin: tuple[tuple[str, str], ...] | None = None,
) -> Scored:
    """One claim's score. Every component is an integer; the weights live in
    the module constants above and nowhere else (M5.5)."""
    query_set = frozenset(query)
    overlap = len(query_set & tokens)
    key_set = frozenset(key_tokens)

    lexical = W_LEXICAL_PER_TOKEN * overlap
    phrase_score = W_PHRASE if query_phrase and query_phrase in phrase else 0

    key_exact = bool(query) and key_tokens == query
    if key_exact:
        key_score = W_KEY_EXACT
    else:
        key_score = W_KEY_PER_TOKEN * len(query_set & key_set)

    pinned = W_PINNED if claim.pinned else 0
    scope = W_PROJECT_SCOPE if claim.scope == "project" else 0
    freshness = _freshness(claim.valid_from, as_of)

    supporting = _active_sources(claim, as_of, "supports")
    disputing = _active_sources(claim, as_of, "disputes")
    supported = W_SUPPORT_PER_SOURCE * min(supporting, MAX_COUNTED_SOURCES)
    disputed = W_DISPUTE_PER_SOURCE * min(disputing, MAX_COUNTED_SOURCES)

    graph_supports, contradictions = _graph_counts(corpus, claim, as_of, eligible)
    graph = W_GRAPH_PER_EDGE * min(graph_supports, MAX_COUNTED_EDGES)
    contradicted = W_CONTRADICTION_PER_EDGE * min(contradictions, MAX_COUNTED_EDGES)

    components = (
        ("lexical", lexical),
        ("phrase", phrase_score),
        ("key", key_score),
        ("pinned", pinned),
        ("scope", scope),
        ("freshness", freshness),
        ("supported", supported),
        ("disputed", disputed),
        ("graph", graph),
        ("contradicted", contradicted),
    )

    reasons: list[str] = []
    if query and query_set <= tokens:
        reasons.append("all_tokens")
    if phrase_score:
        reasons.append("phrase")
    if key_exact:
        reasons.append("key_exact")
    elif key_score:
        reasons.append("key_overlap")
    if pinned:
        reasons.append("pinned")
    if scope:
        reasons.append("project_scope")
    if freshness:
        reasons.append("fresh")
    if supported:
        reasons.append("supported")
    if disputed:
        reasons.append("disputed")
    if graph:
        reasons.append("graph_supported")
    if contradicted:
        reasons.append("contradicted")
    if origin == ORIGIN_EXPANDED:
        reasons.append("graph_expanded")

    return Scored(
        claim=claim,
        components=components,
        total=sum(value for _, value in components),
        origin=origin,
        reasons=tuple(sorted(reasons)),
        supporting=supporting,
        disputing=disputing,
        contradictions=contradictions,
        graph_origin=graph_origin,
    )


# ---------------------------------------------------------------------------
# M5.6 / M5.7 The candidates

BASELINE = "baseline"
CANDIDATE_0 = "candidate-0"
CANDIDATE_1 = "candidate-1"
CANDIDATES = (BASELINE, CANDIDATE_0, CANDIDATE_1)
CANDIDATE_CHOICES = CANDIDATES + ("all",)

#: The candidates under PROMOTION. `baseline` is the measured reference: it is
#: what production does today, it cannot be "promoted", and gating it would
#: make `--candidate all` exit 1 forever the moment the baseline was measured
#: to leak — which is the finding, not a malfunction (D-v0.3.62).
PROMOTABLE = (CANDIDATE_0, CANDIDATE_1)

REASON_OK = "ok"
REASON_NO_TOKENS = "no_usable_tokens"


def _baseline_hits(corpus: Corpus, query: str, limit: int) -> list[RetrievalClaim]:
    """The live LIKE backend's memory semantics, over the shared corpus.

    Faithful to `search._like_search`, deliberately line for line: whitespace
    split of the RAW query (no tokenizer — the baseline does not have one),
    conjunctive case-insensitive substring over `key + "\\n" + value_md`, and
    source order (ascending id). NO eligibility filter: `aos search` surfaces
    historical claims on purpose, and pretending otherwise would be measuring
    a baseline nobody runs (D-v0.3.53).

    Ascending id is the LIKE fallback's order, not FTS5's `rank`. FTS5's
    ordering is a property of the SQLite build, and a benchmark whose ranking
    depends on which SQLite the runner happens to have is not a benchmark. The
    fidelity test compares result SETS against whichever backend is live —
    the part that is backend-independent.
    """
    terms = query.split()
    if not terms:
        return []
    hits: list[RetrievalClaim] = []
    for claim in sorted(corpus.claims, key=lambda c: c.id):
        lowered = claim.text.lower()
        if all(term.lower() in lowered for term in terms):
            hits.append(claim)
    return hits[:limit]


def _baseline_result(claim: RetrievalClaim, as_of: str) -> Scored:
    """A baseline hit, wearing the same shape as a candidate result.

    All components zero: the baseline HAS no components — it matched or it did
    not. Reporting a fabricated score for it would be inventing a ranking
    signal the production code does not have.
    """
    return Scored(
        claim=claim,
        components=tuple((name, 0) for name in COMPONENT_NAMES),
        total=0,
        origin=ORIGIN_PRIMARY,
        reasons=("all_tokens",),
        supporting=_active_sources(claim, as_of, "supports"),
        disputing=_active_sources(claim, as_of, "disputes"),
        contradictions=0,
        graph_origin=None,
    )


def _direction(edge: RetrievalEdge, anchor_id: int) -> str:
    """`symmetric` for the relations U-M3 canonicalizes as one logical edge
    (D-v0.3.36); otherwise the direction the anchor sees. A symmetric edge
    reports that it HAS no direction rather than inventing one from the
    storage order its endpoints happened to be canonicalized into."""
    if edge.relation in MEMORY_EDGE_SYMMETRIC:
        return "symmetric"
    return "out" if edge.from_id == anchor_id else "in"


@dataclass(frozen=True)
class Retrieved:
    """One retrieval's outcome, before rendering.

    The benchmark computes its leakage counters from `results[i].claim` —
    the claim itself, not the rendered document. A counter that read the
    retriever's own output would only ever confirm what the retriever chose
    to say about itself (M5.9).
    """

    results: tuple[Scored, ...]
    truncation: tuple[tuple[str, int], ...]
    reason: str
    matched: int
    as_of: str

    def document(self) -> dict:
        return _document(
            list(self.results),
            dict(self.truncation),
            self.reason,
            self.matched,
            self.as_of,
        )


def retrieve(
    corpus: Corpus,
    *,
    query: str,
    as_of: str,
    limit: int,
    graph_depth: int,
    candidate: str,
    project: str | None = None,
) -> Retrieved:
    """THE candidate retriever. Read-only, bounded, deterministic.

    Renders (via `Retrieved.document()`) a document of safe metadata: never a
    claim value, a locator, provenance text, an evidence ref, a full hash or
    the query itself.
    """
    if candidate not in CANDIDATES:
        raise AosError(
            f"Unknown candidate {candidate!r}. Allowed: " + "|".join(CANDIDATES)
        )
    if graph_depth not in GRAPH_DEPTHS:
        raise AosError(
            f"Invalid graph depth {graph_depth}. Allowed: "
            + "|".join(str(d) for d in GRAPH_DEPTHS)
        )
    if not (1 <= limit <= MAX_RESULTS):
        raise AosError(
            f"Invalid limit {limit}. Allowed: 1..{MAX_RESULTS}."
        )
    utils.validate_instant(as_of, "as-of")

    truncation: dict[str, int] = dict(corpus.truncation)

    if candidate == BASELINE:
        # Bounds still apply: the baseline is measured under the same query
        # limits as the candidates, or the comparison is not one.
        query_tokens(query)
        all_hits = _baseline_hits(corpus, query, MAX_POOL_CLAIMS)
        results = [_baseline_result(claim, as_of) for claim in all_hits[:limit]]
        return _done(results, truncation, REASON_OK, len(all_hits), as_of)

    tokens = query_tokens(query)
    if not tokens:
        # Not an error: `retrieval query "the"` must behave like a search that
        # found nothing, not like a malformed command (M5.2).
        return _done([], truncation, REASON_NO_TOKENS, 0, as_of)

    prepared = _prepare(corpus)
    if prepared.text_truncated:
        truncation["claim_text"] = prepared.text_truncated

    eligible = eligible_claims(corpus, as_of, project)
    eligible_ids = frozenset(claim.id for claim in eligible)
    query_set = frozenset(tokens)
    phrase = normalized_phrase(query)

    def _score(claim, origin, graph_origin=None):
        return score_claim(
            corpus,
            claim,
            tokens=prepared.tokens[claim.id],
            key_tokens=prepared.key_tokens[claim.id],
            phrase=prepared.phrase[claim.id],
            query=tokens,
            query_phrase=phrase,
            as_of=as_of,
            eligible=eligible_ids,
            origin=origin,
            graph_origin=graph_origin,
        )

    # Primary: conjunctive, exactly like both live backends (D-v0.3.58).
    primaries = [
        _score(claim, ORIGIN_PRIMARY)
        for claim in eligible
        if query_set <= prepared.tokens[claim.id]
    ]
    primaries.sort(key=lambda s: s.sort_key)

    expanded: list[Scored] = []
    if graph_depth == 1:
        expanded = _expand(
            corpus,
            primaries=primaries,
            eligible=eligible,
            prepared=prepared,
            query_set=query_set,
            as_of=as_of,
            score=_score,
            truncation=truncation,
        )

    results = primaries + sorted(expanded, key=lambda s: s.sort_key)
    return _done(results[:limit], truncation, REASON_OK, len(results), as_of)


def _done(
    results: list[Scored],
    truncation: dict[str, int],
    reason: str,
    matched: int,
    as_of: str,
) -> Retrieved:
    return Retrieved(
        results=tuple(results),
        truncation=tuple((k, truncation[k]) for k in sorted(truncation)),
        reason=reason,
        matched=matched,
        as_of=as_of,
    )


def _expand(
    corpus: Corpus,
    *,
    primaries: list[Scored],
    eligible: tuple[RetrievalClaim, ...],
    prepared: _Prepared,
    query_set: frozenset[str],
    as_of: str,
    score,
    truncation: dict[str, int],
) -> list[Scored]:
    """Bounded depth-1 expansion (M5.7).

    Determinism comes from a total order: primaries in final rank order, each
    one's incident edges in ascending edge id. Caps stop the loop at a
    deterministic point and report themselves; they never refuse the query
    (D-v0.3.63).

    Every exclusion below goes through the SAME `eligibility` predicate that
    excluded these claims as primaries. There is no second, weaker gate on the
    expansion path — which is the only reason "restricted claims never leak"
    can be one proof rather than two.
    """
    by_id = {claim.id: claim for claim in eligible}
    seen = {result.claim.id for result in primaries}
    out: list[Scored] = []
    scanned = 0

    for anchor in primaries:
        if scanned >= MAX_GRAPH_EDGES_SCANNED or len(out) >= MAX_GRAPH_NODES_ADDED:
            break
        for edge in sorted(
            _incident_edges(corpus, anchor.claim.id, as_of), key=lambda e: e.id
        ):
            if scanned >= MAX_GRAPH_EDGES_SCANNED:
                truncation["graph_edges"] = 1
                break
            scanned += 1
            other = edge.to_id if edge.from_id == anchor.claim.id else edge.from_id
            if other in seen:
                continue
            neighbour = by_id.get(other)
            if neighbour is None:
                continue  # ineligible, shadowed, or outside the pool
            # The documented minimum relevance signal (D-v0.3.58). Zero query
            # tokens is graph noise, whatever its degree.
            if not (query_set & prepared.tokens[other]):
                continue
            if len(out) >= MAX_GRAPH_NODES_ADDED:
                truncation["graph_nodes"] = 1
                break
            seen.add(other)
            out.append(
                score(
                    neighbour,
                    ORIGIN_EXPANDED,
                    (
                        ("via", ids.render_id("memory", anchor.claim.id)),
                        ("edge", ids.render_id("memory_edge", edge.id)),
                        ("relation", edge.relation),
                        ("direction", _direction(edge, anchor.claim.id)),
                    ),
                )
            )
    return out


def _document(
    results: list[Scored],
    truncation: dict[str, int],
    reason: str,
    full: int,
    as_of: str,
) -> dict:
    """The result document (M5.8). Metadata, reason codes, ids and counts.

    `temporal_active` is recomputed here rather than inferred from
    eligibility: for a candidate every result is active by construction, but
    the BASELINE has no eligibility rule at all, and reporting `true` for an
    expired baseline hit because "results are active" would be the metadata
    lying about exactly the leak the report exists to count.
    """
    return {
        "reason": reason,
        "returned": len(results),
        "matched": full,
        "truncation": {k: truncation[k] for k in sorted(truncation)},
        "results": [
            {
                "memory": ids.render_id("memory", scored.claim.id),
                "rank": rank,
                "origin": scored.origin,
                "score": scored.total,
                "components": dict(scored.components),
                "reasons": list(scored.reasons),
                "scope": scored.claim.scope,
                "project": scored.claim.project,
                "status": scored.claim.status,
                "sensitivity": scored.claim.sensitivity,
                "pinned": scored.claim.pinned,
                "temporal_active": ops.window_is_active(
                    scored.claim.valid_from, scored.claim.valid_until, as_of
                ),
                "supporting_sources": scored.supporting,
                "disputing_sources": scored.disputing,
                "contradictions": scored.contradictions,
                "graph_origin": (
                    dict(scored.graph_origin) if scored.graph_origin else None
                ),
                "hash_prefix": models.hash_prefix(scored.claim.content_sha256),
                # A superseded claim's STATUS is still `live` — supersession
                # is a pointer, not a status (U-M2). Without this bool the
                # metadata would show `status: live` for a claim the pack
                # builder would refuse, and a reader would have no way to see
                # the lifecycle leak the counters are reporting.
                "superseded": scored.claim.superseded_by is not None,
                "integrity": scored.claim.integrity,
            }
            for rank, scored in enumerate(results, start=1)
        ],
    }


# ---------------------------------------------------------------------------
# M5.9 Metrics — Fractions in, fixed-width decimal STRINGS out (D-v0.3.54)

#: log2(2) … log2(11), scaled by 10^12, written out as source literals.
#:
#: `math.log2` is a libm call: correctly rounded on most platforms, not
#: guaranteed identical on all. This table is a DEFINITION of this metric, not
#: an approximation of another one — two runs on two platforms agree because
#: they compute the same rational number, not because their libms happened to
#: (D-v0.3.55). A test compares it to `math.log2` on the local platform to
#: catch a transcription typo; that is the table checking the transcription,
#: not the transcription trusting the platform.
#:
#: Indexed by 1-based rank; K_MAX = 10 is why it stops at log2(11).
_LOG2_SCALE = 10**12
_LOG2_SCALED = (
    0,                # unused: there is no rank 0
    1000000000000,    # log2(2)
    1584962500721,    # log2(3)
    2000000000000,    # log2(4)
    2321928094887,    # log2(5)
    2584962500721,    # log2(6)
    2807354922058,    # log2(7)
    3000000000000,    # log2(8)
    3169925001442,    # log2(9)
    3321928094887,    # log2(10)
    3459431618637,    # log2(11)
)

DECIMALS = 4
_DECIMAL_SCALE = 10**DECIMALS

MAX_GRADE = 3


def _discount(rank: int) -> Fraction:
    """1 / log2(rank + 1), exactly, as a rational."""
    return Fraction(_LOG2_SCALE, _LOG2_SCALED[rank])


def render_fraction(value: Fraction | None) -> str | None:
    """A Fraction as a fixed 4-decimal string, ROUND_HALF_UP, by integer
    arithmetic only.

    A STRING, not a JSON number: a JSON number is a float to almost every
    consumer, and D-v0.3.54 says no float — not in this process, and not in
    the one that reads the report either.
    """
    if value is None:
        return None
    num, den = value.numerator, value.denominator
    negative = num < 0
    digits = (abs(num) * _DECIMAL_SCALE * 2 + den) // (den * 2)
    text = f"{digits // _DECIMAL_SCALE}.{digits % _DECIMAL_SCALE:0{DECIMALS}d}"
    return f"-{text}" if negative and digits else text


def render_delta(value: Fraction | None) -> str | None:
    """A signed delta. `+0.0000` and `-0.0000` both read as "no change"; the
    sign is kept because a reader scanning a delta column for `+` should not
    have to know that zero has no sign."""
    if value is None:
        return None
    text = render_fraction(value)
    return text if text.startswith("-") else f"+{text}"


#: Every leakage class, in report order. Names, and only names, appear in
#: output — never the claim that triggered one.
LEAKAGE_CLASSES = (
    "forbidden_results",
    "wrong_project_leaks",
    "restricted_leaks",
    "lifecycle_leaks",
    "hash_invalid_included",
)

#: What a case may declare it EXERCISES. Documentation, never permission: a
#: probe never licenses a leak, and any actual leakage fails the gate (M5.12).
LEAKAGE_PROBES = (
    "forbidden",
    "graph_noise",
    "hash_invalid",
    "lifecycle",
    "none",
    "restricted",
    "wrong_project",
)


def _case_leakage(
    results: tuple[Scored, ...], forbidden: frozenset[int], case_project, as_of: str
) -> dict[str, int]:
    """The five counters for one case, computed from the CLAIMS themselves.

    Structural, not declarative: a leak is counted because the claim IS
    restricted / wrong-project / retired, not because the dataset author
    remembered to list its id in `forbidden`. An author's omission cannot
    hide a leak, which is the only way this number is worth printing.
    """
    counts = {name: 0 for name in LEAKAGE_CLASSES}
    for scored in results:
        claim = scored.claim
        if claim.id in forbidden:
            counts["forbidden_results"] += 1
        if claim.scope == "project" and claim.project != case_project:
            counts["wrong_project_leaks"] += 1
        if claim.sensitivity == MEMORY_SENSITIVITY_RESTRICTED:
            counts["restricted_leaks"] += 1
        if (
            claim.status != MEMORY_STATUS_LIVE
            or claim.superseded_by is not None
            or not ops.window_is_active(claim.valid_from, claim.valid_until, as_of)
        ):
            counts["lifecycle_leaks"] += 1
        if claim.integrity != "ok":
            counts["hash_invalid_included"] += 1
    return counts


@dataclass(frozen=True)
class CaseMetrics:
    case: str
    returned: int
    hit_at_k: Fraction | None
    precision_at_k: Fraction | None
    recall_at_k: Fraction | None
    mrr: Fraction | None
    ndcg_at_k: Fraction | None
    leakage: tuple[tuple[str, int], ...]
    truncated: bool


def case_metrics(
    *,
    case: str,
    result_ids: list[int],
    returned: int,
    relevant: frozenset[int],
    graded: dict[int, int] | None,
    leakage: dict[str, int],
    truncated: bool,
    k: int,
) -> CaseMetrics:
    """One case's metrics, exactly as M5.9 pins them.

    `None` where a metric is undefined rather than a made-up zero: recall over
    an empty relevant set is 0/0, and reporting that as 0.0000 would drag
    every "there is no right answer here" case into the mean as a failure.
    `None` is excluded from aggregates, and the aggregate reports how many
    cases contributed.
    """
    ranked = result_ids[:k]
    found = [rid for rid in ranked if rid in relevant]

    hit = Fraction(1) if found else Fraction(0)
    metrics = {
        "hit_at_k": hit if relevant else None,
        "precision_at_k": Fraction(len(found), len(ranked)) if ranked else None,
        "recall_at_k": (
            Fraction(len(found), len(relevant)) if relevant else None
        ),
    }

    mrr: Fraction | None = None
    if relevant:
        mrr = Fraction(0)
        for rank, rid in enumerate(ranked, start=1):
            if rid in relevant:
                mrr = Fraction(1, rank)
                break

    ndcg: Fraction | None = None
    if graded:
        dcg = sum(
            (Fraction(2 ** graded.get(rid, 0) - 1) * _discount(rank)
             for rank, rid in enumerate(ranked, start=1)),
            Fraction(0),
        )
        ideal_grades = sorted(graded.values(), reverse=True)[:k]
        idcg = sum(
            (Fraction(2**grade - 1) * _discount(rank)
             for rank, grade in enumerate(ideal_grades, start=1)),
            Fraction(0),
        )
        ndcg = None if idcg == 0 else dcg / idcg

    return CaseMetrics(
        case=case,
        returned=returned,
        hit_at_k=metrics["hit_at_k"],
        precision_at_k=metrics["precision_at_k"],
        recall_at_k=metrics["recall_at_k"],
        mrr=mrr,
        ndcg_at_k=ndcg,
        leakage=tuple((name, leakage[name]) for name in LEAKAGE_CLASSES),
        truncated=truncated,
    )


AGGREGATE_METRICS = ("hit_at_k", "precision_at_k", "recall_at_k", "mrr", "ndcg_at_k")


def _mean(values: list[Fraction]) -> Fraction | None:
    if not values:
        return None
    return sum(values, Fraction(0)) / len(values)


# ---------------------------------------------------------------------------
# M5.10 Benchmark datasets — CANONICAL (D-v0.3.61)
#
# These Python literals are the one editable registry. `retrieval_benchmarks/`
# is a projection of them, written by tools/gen_retrieval_benchmarks.py and
# verified byte-for-byte by doctor and the focused tests. Exactly the U-X1
# mechanic (D-v0.3.2/D-v0.3.3), for exactly the U-X1 reason: aos.pyz carries
# .py files and nothing else, so a JSON file could not be the source of truth
# without either breaking the zipapp or widening its allowlist.
#
# Everything below is SYNTHETIC. Two invented projects, invented keys,
# invented values. No real project name, secret, path, evidence ref, URL or
# memory body is here or may ever be added.

#: Planted in the values of a restricted claim and a wrong-project claim, in
#: both fixtures, precisely because a careless implementation would print it.
#: Secret-SHAPED (it matches secretscan's `sk-api-key`), and worthless: it is
#: a literal in a public source file. If this string appears in any output,
#: any report or any diagnostic, a test fails.
_PLANTED = "sk-live-m5planted00000000000000000000"  # noqa: S105


def _fc(
    cid,
    scope,
    project,
    key,
    value,
    *,
    kind="fact",
    status="live",
    pinned=False,
    sensitivity="internal",
    valid_from,
    valid_until=None,
    superseded_by=None,
    hash_valid=True,
    sources=(),
):
    """One synthetic fixture claim. A constructor, not a second format: it
    returns exactly the dict the validator checks and the projection writes,
    so there is no shape here that the checked-in JSON does not have."""
    return {
        "id": cid,
        "scope": scope,
        "project": project,
        "kind": kind,
        "key": key,
        "value": value,
        "status": status,
        "pinned": pinned,
        "sensitivity": sensitivity,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "superseded_by": superseded_by,
        "hash_valid": hash_valid,
        "sources": [
            {"relation": rel, "valid_from": vf, "valid_until": vu}
            for rel, vf, vu in sources
        ],
    }


def _fe(eid, from_id, to_id, relation, *, valid_from=None, valid_until=None):
    """One synthetic fixture edge. Symmetric relations must satisfy
    `from < to` — U-M3's storage canonicalization (D-v0.3.36) holds in the
    fixture too, so a fixture cannot express an edge the real schema would
    refuse. The validator enforces it."""
    return {
        "id": eid,
        "from": from_id,
        "to": to_id,
        "relation": relation,
        "valid_from": valid_from,
        "valid_until": valid_until,
    }


def _case(
    name,
    query,
    project,
    *,
    as_of,
    limit=5,
    relevant=(),
    graded=None,
    forbidden=(),
    probes=("none",),
    rationale,
):
    case = {
        "case": name,
        "query": query,
        "project": project,
        "as_of": as_of,
        "config": {"limit": limit},
        "relevant": list(relevant),
        "forbidden": list(forbidden),
        "leakage_probes": list(probes),
        "rationale": rationale,
    }
    if graded is not None:
        case["graded"] = {str(k): v for k, v in sorted(graded.items())}
    return case


_T0 = "2026-06-01T00:00:00Z"

#: Benchmark 1 of 2. Lexical, temporal, scope, lifecycle, provenance and
#: privacy — everything that does not need an edge. Its fixture has NO edges,
#: which is also how candidate-1 is proven to be a no-op without them.
_CORE = {
    "benchmark": "core-retrieval",
    "dataset_version": DATASET_VERSION,
    "description": (
        "Lexical, temporal, scope, lifecycle and provenance retrieval over a "
        "synthetic two-project ledger with planted leakage bait."
    ),
    "thresholds": {"min_hit_rate": "0.7500", "min_mrr": "0.5000"},
    "fixture": {
        "projects": ["alpha", "beta"],
        "claims": [
            _fc(1, "global", None, "deploy-window",
                "Deploys land in the Tuesday deploy window.",
                valid_from="2026-05-01", sources=(("supports", None, None),)),
            _fc(2, "project", "alpha", "alpha-deploy-window",
                "Alpha uses a Thursday deploy window for release traffic.",
                kind="constraint", pinned=True, valid_from="2026-05-10",
                sources=(("supports", None, None), ("supports", None, None))),
            _fc(3, "project", "beta", "beta-deploy-window",
                "Beta uses a Monday deploy window for release traffic.",
                kind="constraint", valid_from="2026-05-10"),
            _fc(4, "project", "alpha", "alpha-retry-policy",
                "Retry policy for alpha jobs is three attempts.",
                valid_from="2026-04-01"),
            _fc(5, "global", None, "review-cadence",
                "Weekly review cadence lands on Friday.",
                kind="preference", sensitivity="public",
                valid_from="2026-01-05"),
            # Expired: its window closed before the as-of.
            _fc(6, "project", "alpha", "alpha-migration-window",
                "Alpha deploy window was Wednesday during the migration.",
                valid_from="2026-01-01", valid_until="2026-04-01"),
            # Superseded by claim 2. Status is still `live` — supersession is
            # a pointer, not a status.
            _fc(7, "project", "alpha", "alpha-old-deploy-window",
                "Alpha deploy window is Wednesday.",
                valid_from="2026-03-01", superseded_by=2),
            _fc(8, "project", "alpha", "alpha-retired-window",
                "Alpha deploy window on Thursday, retired note.",
                status="retired", valid_from="2026-02-01"),
            # The adversarial pair (9, 10): both key-match and phrase-match
            # the `thursday deploy window` query EXACTLY — a far stronger
            # lexical signal than the permitted answer (claim 2, which key
            # matches only partially). One is restricted, one is the wrong
            # project. Both must stay out, and the planted token must never
            # be printed.
            _fc(9, "project", "alpha", "thursday-deploy-window",
                f"Thursday deploy window rota for alpha with token {_PLANTED}.",
                sensitivity="restricted", valid_from="2026-05-12"),
            _fc(10, "project", "beta", "thursday-deploy-window",
                f"Thursday deploy window rota for beta with token {_PLANTED}.",
                valid_from="2026-05-12"),
            _fc(11, "project", "alpha", "alpha-tampered-window",
                "Alpha deploy window Thursday, tampered row.",
                valid_from="2026-05-13", hash_valid=False),
            _fc(12, "project", "alpha", "alpha-proposed-window",
                "Alpha deploy window Thursday, proposed.",
                status="proposed", valid_from="2026-05-14"),
            _fc(13, "project", "alpha", "alpha-contested-window",
                "Alpha deploy window Thursday, contested.",
                status="contested", valid_from="2026-05-14"),
            _fc(14, "project", "alpha", "alpha-quarantined-window",
                "Alpha deploy window Thursday, quarantined.",
                status="quarantined", valid_from="2026-05-14"),
            # 15 vs 16: identical shape, opposite provenance. The only score
            # difference between them is `disputed` vs `supported`.
            _fc(15, "project", "alpha", "alpha-disputed-runbook",
                "Runbook for the alpha deploy is in the ops guide.",
                valid_from="2026-05-02",
                sources=(("disputes", None, None), ("disputes", None, None))),
            _fc(16, "project", "alpha", "alpha-supported-runbook",
                "Runbook for the alpha deploy is in the release guide.",
                valid_from="2026-05-02",
                sources=(("supports", None, None), ("supports", None, None),
                         ("supports", None, None))),
            # 17 vs 18: engineered to score IDENTICALLY on the `zeta` query,
            # so the only thing that can order them is the memory id.
            _fc(17, "global", None, "tie-marker-one",
                "Ambiguous zeta marker.", valid_from="2026-05-20"),
            _fc(18, "global", None, "tie-marker-two",
                "Ambiguous zeta marker.", valid_from="2026-05-20"),
            _fc(19, "project", "alpha", "alpha-shipping-cadence",
                "Shipping cadence for alpha follows the weekly release train.",
                valid_from="2026-04-20"),
            # 20 vs 21: identical but for the pin — and the PINNED one has the
            # HIGHER id, so if the pin component did nothing, the id
            # tie-break would order them the other way round.
            _fc(20, "project", "alpha", "alpha-editor-plain",
                "Editor preference for alpha is spaces.",
                kind="preference", valid_from="2026-05-05"),
            _fc(21, "project", "alpha", "alpha-editor-pinned",
                "Editor preference for alpha is spaces as well.",
                kind="preference", pinned=True, valid_from="2026-05-05"),
        ],
        "edges": [],
    },
    "cases": [
        _case("exact-lexical-match", "deploy window", "alpha", as_of=_T0,
              relevant=(1, 2), graded={1: 3, 2: 3},
              forbidden=(3, 6, 7, 8, 9, 10, 11, 12, 13, 14),
              probes=("wrong_project", "restricted", "lifecycle",
                      "hash_invalid"),
              rationale="Both tokens present; one global and one project "
                        "claim are permitted and ten ineligible claims match "
                        "the same words."),
        _case("paraphrase-term-overlap", "weekly cadence", "alpha", as_of=_T0,
              relevant=(5, 19), graded={5: 2, 19: 3},
              rationale="Same terms, different order and wording, no shared "
                        "phrase: overlap alone must find both without an "
                        "embedding."),
        _case("global-scope-only", "deploy window", None, as_of=_T0,
              relevant=(1,), graded={1: 3},
              forbidden=(2, 3, 6, 7, 8, 9, 10, 11, 12, 13, 14),
              probes=("wrong_project", "restricted", "lifecycle",
                      "hash_invalid"),
              rationale="No project requested: only global claims are "
                        "eligible, including alpha's own."),
        _case("wrong-project-near-duplicate", "monday deploy window", "alpha",
              as_of=_T0, forbidden=(3,), probes=("wrong_project",),
              rationale="Only beta's near-duplicate matches all three tokens; "
                        "the right answer for alpha is nothing at all."),
        _case("pinned-versus-unpinned", "editor preference", "alpha",
              as_of=_T0, relevant=(20, 21), graded={20: 2, 21: 3},
              rationale="Identical claims but for the pin; the pinned one has "
                        "the higher id, so id order cannot be what ranks it "
                        "first."),
        _case("current-versus-expired", "wednesday migration", "alpha",
              as_of=_T0, forbidden=(6,), probes=("lifecycle",),
              rationale="The only lexical match expired two months before the "
                        "as-of."),
        _case("adversarial-stronger-forbidden-match", "thursday deploy window",
              "alpha", as_of=_T0, relevant=(2,), graded={2: 3},
              forbidden=(8, 9, 10, 11, 12, 13, 14),
              probes=("restricted", "wrong_project", "lifecycle",
                      "hash_invalid"),
              rationale="The restricted claim and the beta claim both match "
                        "the query EXACTLY on key and phrase; the permitted "
                        "answer matches more weakly. Strength must not buy "
                        "eligibility."),
        _case("restricted-exclusion", "rota token", "alpha", as_of=_T0,
              forbidden=(9, 10), probes=("restricted", "wrong_project"),
              rationale="Both matches carry a planted secret-shaped value: "
                        "one restricted, one wrong-project. Nothing is the "
                        "right answer."),
        _case("supported-versus-disputed", "runbook", "alpha", as_of=_T0,
              relevant=(15, 16), graded={15: 1, 16: 3},
              rationale="Two claims, identical but for provenance; the "
                        "supported one must outrank the disputed one, and the "
                        "disputed one must still be returned."),
        _case("superseded-excluded", "wednesday deploy window", "alpha",
              as_of=_T0, forbidden=(6, 7), probes=("lifecycle",),
              rationale="One expired and one superseded claim match; both are "
                        "status=live, and both must stay out."),
        _case("hash-invalid-excluded", "tampered row", "alpha", as_of=_T0,
              forbidden=(11,), probes=("hash_invalid",),
              rationale="The only match is a claim whose stored hash does not "
                        "verify."),
        _case("deterministic-ties", "zeta", "alpha", as_of=_T0,
              relevant=(17, 18), graded={17: 2, 18: 2},
              rationale="Two claims engineered to score identically; the "
                        "memory id is the only tie-break left."),
        _case("no-relevant-result", "quokka sunset", "alpha", as_of=_T0,
              rationale="Nothing matches. The right answer is an empty list, "
                        "not the closest thing available."),
        _case("no-usable-tokens", "the and of", "alpha", as_of=_T0,
              rationale="Every term is a stopword: no usable tokens, an empty "
                        "result, and not an error."),
    ],
}

#: Benchmark 2 of 2. Everything that needs an edge: directional expansion,
#: symmetric expansion, contradiction metadata, and noise.
_GRAPH = {
    "benchmark": "graph-expansion",
    "dataset_version": DATASET_VERSION,
    "description": (
        "Bounded depth-1 expansion over active edges: direction, symmetry, "
        "contradiction metadata and high-degree noise."
    ),
    "thresholds": {"min_hit_rate": "0.7500", "min_mrr": "0.5000"},
    "fixture": {
        "projects": ["alpha", "beta"],
        "claims": [
            # The anchor: the only full lexical match for `index rebuild
            # nightly`.
            _fc(1, "project", "alpha", "alpha-index-rebuild",
                "Index rebuild for alpha runs nightly.",
                valid_from="2026-05-15"),
            # Reachable only by expansion: one query token, inbound supports.
            _fc(2, "project", "alpha", "alpha-rebuild-runbook",
                "Rebuild steps are documented in the ops runbook.",
                valid_from="2026-05-15"),
            # The noise. ZERO query tokens and the highest degree of any
            # non-anchor claim in this fixture (edges 3, 4, 5). It must never
            # appear, however well connected it is.
            _fc(3, "project", "alpha", "alpha-kitchen-noise",
                "Unrelated marker about the office kitchen.",
                valid_from="2026-05-15"),
            # Reachable only by expansion: one query token, outbound
            # depends_on.
            _fc(4, "project", "alpha", "alpha-storage-depends",
                "Rebuild depends on the alpha storage tier.",
                valid_from="2026-05-15"),
            # Six baited neighbours of the anchor, one per exclusion rule.
            _fc(5, "project", "beta", "beta-index-rebuild",
                "Index rebuild for beta runs nightly.",
                valid_from="2026-05-15"),
            _fc(6, "project", "alpha", "alpha-restricted-rebuild",
                f"Rebuild rota for alpha with token {_PLANTED}.",
                sensitivity="restricted", valid_from="2026-05-15"),
            _fc(7, "project", "alpha", "alpha-retired-rebuild",
                "Rebuild for alpha, retired note.",
                status="retired", valid_from="2026-05-15"),
            # Eligible, and edged to the anchor by an EXPIRED edge: the claim
            # is fine, the edge is not, and only the edge decides.
            _fc(8, "project", "alpha", "alpha-archive-rebuild",
                "Rebuild archive for alpha.", valid_from="2026-05-15"),
            _fc(9, "project", "alpha", "alpha-tampered-rebuild",
                "Rebuild tampered for alpha.",
                valid_from="2026-05-15", hash_valid=False),
            _fc(10, "project", "alpha", "alpha-expired-rebuild",
                "Rebuild for alpha during the old migration.",
                valid_from="2026-01-01", valid_until="2026-04-01"),
            # The symmetric `related` pair.
            _fc(11, "project", "alpha", "alpha-cache-purge",
                "Cache purge for alpha runs nightly.",
                valid_from="2026-05-15"),
            _fc(12, "project", "alpha", "alpha-purge-history",
                "Purge history is archived monthly.",
                valid_from="2026-05-15"),
            # The symmetric `contradicts` pair.
            _fc(13, "project", "alpha", "alpha-queue-drain",
                "Queue drain for alpha runs hourly.",
                valid_from="2026-05-15"),
            _fc(14, "project", "alpha", "alpha-drain-dispute",
                "Drain for alpha is not hourly.",
                valid_from="2026-05-15"),
        ],
        "edges": [
            _fe(1, 2, 1, "supports"),
            _fe(2, 1, 4, "depends_on"),
            _fe(3, 1, 3, "related"),
            _fe(4, 2, 3, "related"),
            _fe(5, 3, 4, "related"),
            _fe(6, 1, 5, "related"),
            _fe(7, 1, 6, "related"),
            _fe(8, 1, 7, "related"),
            # An EXPIRED edge to a perfectly eligible claim. Its window
            # deliberately OVERLAPS claim 8's validity and then closes before
            # the as-of: at 2026-05-16 this edge carried claim 8 into the
            # results, and at 2026-06-01 it does not. That overlap is what
            # makes "only the edge decides" provable — an edge that was never
            # active while its target was valid would prove nothing about
            # which of the two the exclusion came from.
            _fe(9, 1, 8, "related", valid_until="2026-05-20"),
            _fe(10, 1, 9, "related"),
            _fe(11, 1, 10, "related"),
            _fe(12, 11, 12, "related"),
            _fe(13, 13, 14, "contradicts"),
        ],
    },
    "cases": [
        _case("directional-edge-expansion", "index rebuild nightly", "alpha",
              as_of=_T0, relevant=(1, 2, 4), graded={1: 3, 2: 2, 4: 1},
              rationale="One primary anchor; claim 2 arrives on an INBOUND "
                        "supports edge and claim 4 on an OUTBOUND depends_on "
                        "edge. Both keep their direction."),
        _case("symmetric-edge-expansion", "cache purge", "alpha", as_of=_T0,
              relevant=(11, 12), graded={11: 3, 12: 2},
              rationale="A `related` edge is one logical edge with no "
                        "direction; the neighbour reports `symmetric` rather "
                        "than the storage order it was canonicalized into."),
        _case("contradiction-metadata", "queue drain hourly", "alpha",
              as_of=_T0, relevant=(13, 14), graded={13: 3, 14: 1},
              rationale="A contradicts edge expands like any other and "
                        "resolves nothing: the contradicted anchor is still "
                        "returned, still first, and merely scored lower."),
        _case("graph-noise-excluded", "index rebuild nightly", "alpha",
              as_of=_T0, relevant=(1, 2, 4), graded={1: 3, 2: 2, 4: 1},
              forbidden=(3, 5, 6, 7, 8, 9, 10),
              probes=("graph_noise", "wrong_project", "restricted",
                      "lifecycle", "hash_invalid"),
              rationale="Seven baited neighbours of the same anchor: zero "
                        "query tokens, wrong project, restricted, retired, an "
                        "expired edge, an invalid hash, an expired claim. "
                        "None may be expanded into."),
        _case("graph-no-relevant-result", "quokka sunset", "alpha", as_of=_T0,
              rationale="No primary hit, so there is nothing to expand FROM: "
                        "expansion cannot invent an anchor."),
    ],
}

#: THE registry. Sorted by name at every use, never by insertion order.
_DATASETS: tuple[dict, ...] = (_CORE, _GRAPH)


# ---------------------------------------------------------------------------
# M5.10 Validation
#
# Explicit, hand-written validators over a closed field set. U-M5 claims NO
# general JSON Schema support and registers no U-X1 schema identity: U-X1's
# registry is untouched. Everything below names a field path and a condition;
# nothing echoes a value.

_NAME_RE_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-")
MAX_NAME_CHARS = 48
MAX_DESCRIPTION_CHARS = 200

_CLAIM_FIELDS = frozenset(
    {"id", "scope", "project", "kind", "key", "value", "status", "pinned",
     "sensitivity", "valid_from", "valid_until", "superseded_by", "hash_valid",
     "sources"}
)
_SOURCE_FIELDS = frozenset({"relation", "valid_from", "valid_until"})
_EDGE_FIELDS = frozenset({"id", "from", "to", "relation", "valid_from", "valid_until"})
_CASE_FIELDS = frozenset(
    {"case", "query", "project", "as_of", "config", "relevant", "graded",
     "forbidden", "leakage_probes", "rationale"}
)
_DATASET_FIELDS = frozenset(
    {"benchmark", "dataset_version", "description", "thresholds", "fixture",
     "cases"}
)
_FIXTURE_FIELDS = frozenset({"projects", "claims", "edges"})
_THRESHOLD_FIELDS = frozenset({"min_hit_rate", "min_mrr"})
_CONFIG_FIELDS = frozenset({"limit"})


class DatasetError(AosError):
    """A malformed benchmark definition. Names the field path and the
    condition; never a value, and never the fixture text it is complaining
    about."""


def _refuse(where: str, problem: str) -> DatasetError:
    return DatasetError(
        f"Benchmark definition refused at {where}: {problem}. Nothing was "
        "evaluated. Regenerate with: python3 tools/gen_retrieval_benchmarks.py"
    )


def _check_fields(obj, allowed: frozenset[str], where: str) -> None:
    if not isinstance(obj, dict):
        raise _refuse(where, "expected an object")
    unknown = sorted(set(obj) - allowed)
    if unknown:
        raise _refuse(where, f"unknown field(s) {', '.join(unknown)}")


def _check_name(value, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise _refuse(where, "expected a non-empty string")
    if len(value) > MAX_NAME_CHARS:
        raise _refuse(where, f"longer than {MAX_NAME_CHARS} characters")
    if value[0] not in "abcdefghijklmnopqrstuvwxyz":
        raise _refuse(where, "must start with a lowercase letter")
    if not set(value) <= _NAME_RE_CHARS:
        raise _refuse(where, "may contain lowercase letters, digits and '-' only")
    return value


def _check_ids(values, fixture_ids: frozenset[int], where: str) -> frozenset[int]:
    if not isinstance(values, list):
        raise _refuse(where, "expected an array")
    seen: set[int] = set()
    for value in values:
        if not isinstance(value, int) or isinstance(value, bool):
            raise _refuse(where, "expected integer fixture claim ids")
        if value in seen:
            raise _refuse(where, f"duplicate id {value}")
        if value not in fixture_ids:
            raise _refuse(where, f"id {value} is not a fixture claim")
        seen.add(value)
    return frozenset(seen)


def validate_dataset(dataset: dict) -> None:
    """Every refusal M5.10 pins, in one pass. Raises DatasetError; the caller
    that catches nothing exits 1 with stdout byte-empty."""
    _check_fields(dataset, _DATASET_FIELDS, "/")
    for required in sorted(_DATASET_FIELDS - {"description"}):
        if required not in dataset:
            raise _refuse("/", f"missing field {required}")

    _check_name(dataset.get("benchmark"), "/benchmark")
    if dataset.get("dataset_version") != DATASET_VERSION:
        raise _refuse(
            "/dataset_version",
            f"unsupported version; this build supports {DATASET_VERSION}",
        )
    description = dataset.get("description", "")
    if not isinstance(description, str) or len(description) > MAX_DESCRIPTION_CHARS:
        raise _refuse(
            "/description", f"expected a string of at most {MAX_DESCRIPTION_CHARS} characters"
        )

    _check_fields(dataset["thresholds"], _THRESHOLD_FIELDS, "/thresholds")
    for name in sorted(_THRESHOLD_FIELDS):
        if name not in dataset["thresholds"]:
            raise _refuse("/thresholds", f"missing field {name}")
        if parse_threshold(dataset["thresholds"][name]) is None:
            raise _refuse(
                f"/thresholds/{name}",
                f"expected a {DECIMALS}-decimal string between 0.0000 and 1.0000",
            )

    fixture = dataset["fixture"]
    _check_fields(fixture, _FIXTURE_FIELDS, "/fixture")
    for name in sorted(_FIXTURE_FIELDS):
        if name not in fixture:
            raise _refuse("/fixture", f"missing field {name}")

    projects = fixture["projects"]
    if not isinstance(projects, list) or len(projects) != len(set(projects)):
        raise _refuse("/fixture/projects", "expected an array of distinct slugs")
    for index, slug in enumerate(projects):
        if not isinstance(slug, str) or not models.SLUG_RE.match(slug):
            raise _refuse(f"/fixture/projects/{index}", "not a valid project slug")
    known_projects = frozenset(projects)

    claims = fixture["claims"]
    if not isinstance(claims, list):
        raise _refuse("/fixture/claims", "expected an array")
    if len(claims) > MAX_FIXTURE_CLAIMS:
        raise _refuse(
            "/fixture/claims",
            f"{len(claims)} claims; the maximum is {MAX_FIXTURE_CLAIMS}",
        )
    seen_ids: set[int] = set()
    for index, claim in enumerate(claims):
        where = f"/fixture/claims/{index}"
        _check_fields(claim, _CLAIM_FIELDS, where)
        for name in sorted(_CLAIM_FIELDS):
            if name not in claim:
                raise _refuse(where, f"missing field {name}")
        cid = claim["id"]
        if not isinstance(cid, int) or isinstance(cid, bool):
            raise _refuse(f"{where}/id", "expected an integer")
        if not (1 <= cid <= MAX_FIXTURE_CLAIMS):
            raise _refuse(f"{where}/id", f"outside 1..{MAX_FIXTURE_CLAIMS}")
        if cid in seen_ids:
            raise _refuse(f"{where}/id", f"duplicate claim id {cid}")
        seen_ids.add(cid)
        if claim["scope"] not in MEMORY_SCOPES:
            raise _refuse(f"{where}/scope", "not a known memory scope")
        if claim["scope"] == "project":
            if claim["project"] not in known_projects:
                raise _refuse(f"{where}/project", "not a fixture project")
        elif claim["project"] is not None:
            raise _refuse(f"{where}/project", "a global claim has no project")
        if claim["kind"] not in MEMORY_KINDS:
            raise _refuse(f"{where}/kind", "not a known memory kind")
        if claim["status"] not in MEMORY_STATUSES:
            raise _refuse(f"{where}/status", "not a known memory status")
        if claim["sensitivity"] not in MEMORY_SENSITIVITIES:
            raise _refuse(f"{where}/sensitivity", "not a known sensitivity")
        for flag in ("pinned", "hash_valid"):
            if not isinstance(claim[flag], bool):
                raise _refuse(f"{where}/{flag}", "expected a boolean")
        for field_name in ("key", "value"):
            if not isinstance(claim[field_name], str) or not claim[field_name]:
                raise _refuse(f"{where}/{field_name}", "expected a non-empty string")
        utils.validate_instant(claim["valid_from"], f"{where}/valid_from")
        if claim["valid_until"] is not None:
            utils.validate_instant(claim["valid_until"], f"{where}/valid_until")
        if claim["superseded_by"] is not None and not isinstance(
            claim["superseded_by"], int
        ):
            raise _refuse(f"{where}/superseded_by", "expected an integer or null")
        if not isinstance(claim["sources"], list):
            raise _refuse(f"{where}/sources", "expected an array")
        for sindex, source in enumerate(claim["sources"]):
            swhere = f"{where}/sources/{sindex}"
            _check_fields(source, _SOURCE_FIELDS, swhere)
            for name in sorted(_SOURCE_FIELDS):
                if name not in source:
                    raise _refuse(swhere, f"missing field {name}")
            if source["relation"] not in MEMORY_SOURCE_RELATIONS:
                raise _refuse(f"{swhere}/relation", "not a known source relation")

    fixture_ids = frozenset(seen_ids)
    for index, claim in enumerate(claims):
        target = claim["superseded_by"]
        if target is not None and target not in fixture_ids:
            raise _refuse(
                f"/fixture/claims/{index}/superseded_by",
                "points at a claim the fixture does not define",
            )

    edges = fixture["edges"]
    if not isinstance(edges, list):
        raise _refuse("/fixture/edges", "expected an array")
    if len(edges) > MAX_FIXTURE_EDGES:
        raise _refuse(
            "/fixture/edges", f"{len(edges)} edges; the maximum is {MAX_FIXTURE_EDGES}"
        )
    seen_edges: set[int] = set()
    for index, edge in enumerate(edges):
        where = f"/fixture/edges/{index}"
        _check_fields(edge, _EDGE_FIELDS, where)
        for name in sorted(_EDGE_FIELDS):
            if name not in edge:
                raise _refuse(where, f"missing field {name}")
        eid = edge["id"]
        if not isinstance(eid, int) or isinstance(eid, bool) or eid < 1:
            raise _refuse(f"{where}/id", "expected a positive integer")
        if eid in seen_edges:
            raise _refuse(f"{where}/id", f"duplicate edge id {eid}")
        seen_edges.add(eid)
        for end in ("from", "to"):
            if edge[end] not in fixture_ids:
                raise _refuse(f"{where}/{end}", "not a fixture claim")
        if edge["from"] == edge["to"]:
            raise _refuse(where, "a claim cannot relate to itself")
        if edge["relation"] not in MEMORY_EDGE_RELATIONS:
            raise _refuse(f"{where}/relation", "not a known edge relation")
        # U-M3's storage canonicalization holds here too (D-v0.3.36): a
        # fixture must not be able to express an edge the real schema refuses.
        if edge["relation"] in MEMORY_EDGE_SYMMETRIC and edge["from"] >= edge["to"]:
            raise _refuse(
                where, "a symmetric relation must be stored with from < to"
            )
        for name in ("valid_from", "valid_until"):
            if edge[name] is not None:
                utils.validate_instant(edge[name], f"{where}/{name}")

    cases = dataset["cases"]
    if not isinstance(cases, list) or not cases:
        raise _refuse("/cases", "expected a non-empty array")
    if len(cases) > MAX_DATASET_CASES:
        raise _refuse("/cases", f"{len(cases)} cases; the maximum is {MAX_DATASET_CASES}")
    seen_cases: set[str] = set()
    for index, case in enumerate(cases):
        where = f"/cases/{index}"
        _check_fields(case, _CASE_FIELDS, where)
        for name in sorted(_CASE_FIELDS - {"graded"}):
            if name not in case:
                raise _refuse(where, f"missing field {name}")
        name = _check_name(case["case"], f"{where}/case")
        if name in seen_cases:
            raise _refuse(f"{where}/case", f"duplicate case id {name}")
        seen_cases.add(name)
        if not isinstance(case["query"], str):
            raise _refuse(f"{where}/query", "expected a string")
        if case["project"] is not None and case["project"] not in known_projects:
            raise _refuse(f"{where}/project", "not a fixture project")
        utils.validate_instant(case["as_of"], f"{where}/as_of")
        _check_fields(case["config"], _CONFIG_FIELDS, f"{where}/config")
        limit = case["config"].get("limit")
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise _refuse(f"{where}/config/limit", "expected an integer")
        if not (1 <= limit <= MAX_RESULTS):
            raise _refuse(f"{where}/config/limit", f"outside 1..{MAX_RESULTS}")
        relevant = _check_ids(case["relevant"], fixture_ids, f"{where}/relevant")
        forbidden = _check_ids(case["forbidden"], fixture_ids, f"{where}/forbidden")
        both = sorted(relevant & forbidden)
        if both:
            raise _refuse(
                where,
                f"id(s) {', '.join(str(i) for i in both)} are marked both "
                "relevant and forbidden",
            )
        if "graded" in case:
            graded = case["graded"]
            if not isinstance(graded, dict):
                raise _refuse(f"{where}/graded", "expected an object")
            keys: set[int] = set()
            for raw, grade in graded.items():
                if not isinstance(raw, str) or not raw.isdigit():
                    raise _refuse(f"{where}/graded", "keys must be integer strings")
                gid = int(raw)
                if gid not in relevant:
                    raise _refuse(
                        f"{where}/graded/{raw}", "graded id is not in relevant"
                    )
                if not isinstance(grade, int) or isinstance(grade, bool):
                    raise _refuse(f"{where}/graded/{raw}", "expected an integer grade")
                if not (0 <= grade <= MAX_GRADE):
                    raise _refuse(f"{where}/graded/{raw}", f"outside 0..{MAX_GRADE}")
                keys.add(gid)
            # All-or-nothing: a partial grading silently treats every ungraded
            # relevant claim as grade 0, which is a different benchmark than
            # the one the author thought they wrote.
            if keys != set(relevant):
                raise _refuse(
                    f"{where}/graded",
                    "every relevant id must be graded when grades are present",
                )
        probes = case["leakage_probes"]
        if not isinstance(probes, list) or not probes:
            raise _refuse(f"{where}/leakage_probes", "expected a non-empty array")
        for probe in probes:
            if probe not in LEAKAGE_PROBES:
                raise _refuse(f"{where}/leakage_probes", "not a known leakage probe")
        rationale = case["rationale"]
        if not isinstance(rationale, str) or not rationale:
            raise _refuse(f"{where}/rationale", "expected a non-empty string")
        if len(rationale) > MAX_DESCRIPTION_CHARS:
            raise _refuse(
                f"{where}/rationale", f"longer than {MAX_DESCRIPTION_CHARS} characters"
            )


def parse_threshold(text) -> Fraction | None:
    """A pinned 4-decimal threshold string as an exact Fraction, or None when
    it is not one. Strings in, Fractions out: no float touches a gate."""
    if not isinstance(text, str):
        return None
    whole, _, frac = text.partition(".")
    if not whole.isdigit() or len(frac) != DECIMALS or not frac.isdigit():
        return None
    value = Fraction(int(whole) * _DECIMAL_SCALE + int(frac), _DECIMAL_SCALE)
    return value if 0 <= value <= 1 else None


# ---------------------------------------------------------------------------
# Registry, digests and projection (M5.10, D-v0.3.61)

def _dataset_document(dataset: dict) -> dict:
    """A dataset plus its content digest — U-X1's canonical serialization and
    lowercase SHA-256, reused rather than reinvented (M5.10)."""
    body = dict(dataset)
    body.pop(protocols.CONTENT_HASH_FIELD, None)
    document = dict(body)
    document[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(body)
    return document


def _build_registry() -> dict[str, dict]:
    """Validate every embedded dataset once, at import-adjacent call time, and
    refuse a duplicate NAME here — where it is a bug in this file, not a
    surprise in a report."""
    registry: dict[str, dict] = {}
    for dataset in _DATASETS:
        validate_dataset(dataset)
        name = dataset["benchmark"]
        if name in registry:
            raise _refuse("/benchmark", f"duplicate benchmark name {name}")
        registry[name] = _dataset_document(dataset)
    return registry


_REGISTRY: dict[str, dict] | None = None


def registry() -> dict[str, dict]:
    """name → dataset document. Built once per process, then immutable in
    practice; every consumer sorts by name rather than trusting insertion
    order."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY


def benchmark_names() -> list[str]:
    return sorted(registry())


def get_benchmark(name: str) -> dict:
    """Look up by exact name. An unknown name is refused with the list of
    known ones — the list is two entries long and printing it costs nothing."""
    known = registry()
    if name not in known:
        raise DatasetError(
            f"Unknown benchmark {name!r}. Known: {', '.join(sorted(known))}. "
            "Run: python aos.py retrieval benchmark list"
        )
    return known[name]


def registry_index() -> dict:
    """The registry document: one row per benchmark, sorted by name."""
    body = {
        "registry_version": REGISTRY_VERSION,
        "metrics_version": METRICS_VERSION,
        "benchmarks": [
            {
                "name": name,
                "dataset_version": document["dataset_version"],
                "cases": len(document["cases"]),
                "fixture_claims": len(document["fixture"]["claims"]),
                "fixture_edges": len(document["fixture"]["edges"]),
                "sha256": document[protocols.CONTENT_HASH_FIELD],
            }
            for name, document in sorted(registry().items())
        ],
    }
    document = dict(body)
    document[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(body)
    return document


def expected_source_artifacts() -> dict[str, bytes]:
    """relpath → exact bytes. The projection is a pure function of the
    embedded definitions, so a drifted checkout cannot hide."""
    artifacts = {
        REGISTRY_FILENAME: protocols.serialize_canonical_file_bytes(registry_index())
    }
    for name, document in sorted(registry().items()):
        artifacts[f"{name}.json"] = protocols.serialize_canonical_file_bytes(document)
    return artifacts


def source_benchmarks_dir() -> Path | None:
    """The checked-in retrieval_benchmarks/ directory, or None when there is
    no source checkout — the normal case inside aos.pyz (D-v0.3.2)."""
    candidate = Path(__file__).resolve().parent.parent / BENCHMARK_DIRNAME
    try:
        return candidate if candidate.is_dir() else None
    except OSError:
        return None


def verify_embedded() -> list[str]:
    """Recompute every embedded digest from its definition."""
    problems = []
    for name, document in sorted(registry().items()):
        body = {k: v for k, v in document.items() if k != protocols.CONTENT_HASH_FIELD}
        if protocols.content_digest(body) != document[protocols.CONTENT_HASH_FIELD]:
            problems.append(f"{name}: dataset digest mismatch")
    index = registry_index()
    body = {k: v for k, v in index.items() if k != protocols.CONTENT_HASH_FIELD}
    if protocols.content_digest(body) != index[protocols.CONTENT_HASH_FIELD]:
        problems.append(f"{REGISTRY_FILENAME}: registry digest mismatch")
    return problems


def verify_source_benchmarks(root: Path) -> list[str]:
    """Compare retrieval_benchmarks/ to the embedded definitions, byte for
    byte — and refuse a file that projects nothing, so a stale dataset cannot
    linger after its definition was renamed away."""
    problems = []
    expected = expected_source_artifacts()
    for relpath, want in sorted(expected.items()):
        try:
            got = (root / relpath).read_bytes()
        except OSError:
            problems.append(f"{relpath}: missing or unreadable")
            continue
        if got != want:
            problems.append(f"{relpath}: does not match the embedded definition")
    for path in sorted(root.rglob("*.json")):
        relpath = path.relative_to(root).as_posix()
        if relpath not in expected:
            problems.append(f"{relpath}: not a projection of any embedded benchmark")
    return problems


# ---------------------------------------------------------------------------
# The fixture corpus (D-v0.3.60)

def corpus_from_fixture(dataset: dict) -> Corpus:
    """Build the corpus from an embedded fixture. No database is opened —
    there is no connection to write through, which is what makes "creates no
    database rows, files, ledger events or workspace state" a structural fact
    rather than a promise."""
    fixture = dataset["fixture"]
    claims = tuple(
        RetrievalClaim(
            id=claim["id"],
            scope=claim["scope"],
            project=claim["project"],
            kind=claim["kind"],
            key=claim["key"],
            value=claim["value"],
            status=claim["status"],
            pinned=claim["pinned"],
            sensitivity=claim["sensitivity"],
            valid_from=claim["valid_from"],
            valid_until=claim["valid_until"],
            superseded_by=claim["superseded_by"],
            # A fixture claim is not a hashed row, so it DECLARES the
            # condition rather than faking its cause. `mismatch` is the
            # condition a tampered row is in; `ok` is every other claim's.
            integrity="ok" if claim["hash_valid"] else "mismatch",
            content_sha256=_fixture_hash(dataset["benchmark"], claim),
            sources=tuple(
                SourceWindow(s["relation"], s["valid_from"], s["valid_until"])
                for s in claim["sources"]
            ),
        )
        for claim in sorted(fixture["claims"], key=lambda c: c["id"])
    )
    edges = tuple(
        RetrievalEdge(
            id=edge["id"],
            from_id=edge["from"],
            to_id=edge["to"],
            relation=edge["relation"],
            valid_from=edge["valid_from"],
            valid_until=edge["valid_until"],
        )
        for edge in sorted(fixture["edges"], key=lambda e: e["id"])
    )
    return Corpus(claims, edges, ())


def _fixture_hash(benchmark: str, claim: dict) -> str:
    """A synthetic claim's `content_sha256`, so `hash_prefix` has something
    real and STABLE to print.

    It is a digest of the fixture's own canonical definition, not of a ledger
    row: this is a benchmark fixture, and pretending its hash was produced by
    `ops.memory_claim_digest` would be inventing a provenance it does not
    have. It is deterministic, which is all the report needs from it.
    """
    return protocols.content_digest({"benchmark": benchmark, "claim": claim})


# ---------------------------------------------------------------------------
# M5.12 Evaluation, gate and recommendation

REPORT_VERSION = 1


def _evaluate_candidate(dataset: dict, candidate: str, k: int) -> dict:
    """One candidate over one benchmark. Pure: same inputs, same document."""
    corpus = corpus_from_fixture(dataset)
    cases: list[CaseMetrics] = []
    bounds_ok = True

    for case in dataset["cases"]:
        limit = case["config"]["limit"]
        depth = 1 if candidate == CANDIDATE_1 else 0
        retrieved = retrieve(
            corpus,
            query=case["query"],
            as_of=case["as_of"],
            limit=limit,
            graph_depth=depth,
            candidate=candidate,
            project=case["project"],
        )
        result_ids = [scored.claim.id for scored in retrieved.results]
        if len(retrieved.results) > limit:
            bounds_ok = False
        graded = (
            {int(key): value for key, value in case["graded"].items()}
            if "graded" in case
            else None
        )
        cases.append(
            case_metrics(
                case=case["case"],
                result_ids=result_ids,
                returned=len(retrieved.results),
                relevant=frozenset(case["relevant"]),
                graded=graded,
                leakage=_case_leakage(
                    retrieved.results,
                    frozenset(case["forbidden"]),
                    case["project"],
                    case["as_of"],
                ),
                truncated=bool(retrieved.truncation),
                k=k,
            )
        )

    aggregate = {
        name: _mean([
            value
            for value in (getattr(case, name) for case in cases)
            if value is not None
        ])
        for name in AGGREGATE_METRICS
    }
    contributing = {
        name: sum(1 for case in cases if getattr(case, name) is not None)
        for name in AGGREGATE_METRICS
    }
    counters = {
        cls: sum(dict(case.leakage)[cls] for case in cases)
        for cls in LEAKAGE_CLASSES
    }
    counters["truncations"] = sum(1 for case in cases if case.truncated)

    return {
        "cases": cases,
        "aggregate": aggregate,
        "contributing": contributing,
        "counters": counters,
        "avg_results": _mean([Fraction(case.returned) for case in cases]),
        "bounds_ok": bounds_ok,
    }


def _gate(
    dataset: dict, evaluated: dict, baseline: dict | None, replay_ok: bool
) -> dict:
    """The promotion gate (M5.12). Every clause is a boolean over integers and
    Fractions; there is no weighting between safety and relevance, because one
    is a bug and the other is a score."""
    counters = evaluated["counters"]
    safety_ok = all(counters[cls] == 0 for cls in LEAKAGE_CLASSES)

    thresholds = dataset["thresholds"]
    aggregate = evaluated["aggregate"]
    thresholds_ok = True
    for metric, name in (("hit_at_k", "min_hit_rate"), ("mrr", "min_mrr")):
        floor = parse_threshold(thresholds[name])
        value = aggregate[metric]
        if value is None or floor is None or value < floor:
            thresholds_ok = False

    no_regression: bool | None = None
    if baseline is not None:
        no_regression = True
        for metric in ("hit_at_k", "mrr", "ndcg_at_k"):
            mine, theirs = aggregate[metric], baseline["aggregate"][metric]
            if theirs is None:
                continue
            if mine is None or mine < theirs:
                no_regression = False

    gate = (
        safety_ok
        and evaluated["bounds_ok"]
        and thresholds_ok
        and replay_ok
        and (no_regression is not False)
    )
    return {
        "safety_ok": safety_ok,
        "bounds_ok": evaluated["bounds_ok"],
        "thresholds_ok": thresholds_ok,
        "no_regression": no_regression,
        "replay_ok": replay_ok,
        "gate": gate,
    }


RECOMMENDATIONS = (
    "promote candidate-1",
    "promote candidate-0",
    "keep baseline",
    "insufficient evidence",
)


def _recommend(evaluations: dict, gates: dict) -> dict:
    """A function of gates, not of prose (M5.12). Advisory: no command acts on
    it, and nothing in this unit changes production configuration."""
    if set(evaluations) != set(CANDIDATES):
        return {
            "recommendation": "insufficient evidence",
            "reason": "partial_evaluation",
        }

    def triple(name):
        agg = evaluations[name]["aggregate"]
        return [agg[m] for m in ("hit_at_k", "mrr", "ndcg_at_k")]

    c0, c1 = triple(CANDIDATE_0), triple(CANDIDATE_1)
    comparable = [
        (a, b) for a, b in zip(c1, c0) if a is not None and b is not None
    ]
    if (
        gates[CANDIDATE_1]["gate"]
        and comparable
        and all(a >= b for a, b in comparable)
        and any(a > b for a, b in comparable)
    ):
        return {"recommendation": "promote candidate-1", "reason": "gates_passed"}
    if gates[CANDIDATE_0]["gate"]:
        return {"recommendation": "promote candidate-0", "reason": "gates_passed"}
    return {"recommendation": "keep baseline", "reason": "no_candidate_gate_passed"}


def _render_case(case: CaseMetrics) -> dict:
    doc = {"case": case.case, "returned": case.returned, "truncated": case.truncated}
    for name in AGGREGATE_METRICS:
        doc[name] = render_fraction(getattr(case, name))
    doc["leakage"] = dict(case.leakage)
    return doc


def _render_candidate(evaluated: dict, gate: dict | None) -> dict:
    return {
        "aggregate": {
            name: render_fraction(evaluated["aggregate"][name])
            for name in AGGREGATE_METRICS
        },
        # How many cases each mean is over, so a mean of 7 of 14 cases can
        # never read as a mean of 14 (M5.9).
        "contributing": dict(evaluated["contributing"]),
        "avg_results": render_fraction(evaluated["avg_results"]),
        "counters": dict(evaluated["counters"]),
        "gate": gate,
        "cases": [_render_case(case) for case in evaluated["cases"]],
    }


def _deltas(evaluated: dict, baseline: dict) -> dict:
    out = {}
    for name in AGGREGATE_METRICS:
        mine, theirs = evaluated["aggregate"][name], baseline["aggregate"][name]
        out[name] = (
            render_delta(mine - theirs)
            if mine is not None and theirs is not None
            else None
        )
    for cls in LEAKAGE_CLASSES:
        out[cls] = evaluated["counters"][cls] - baseline["counters"][cls]
    return out


def run_benchmark(name: str, *, candidate: str = "all", k: int = 5) -> dict:
    """Validate → evaluate → replay → gate → recommend. The whole report.

    Opens no database, writes no file, emits no event and creates no workspace
    state (D-v0.3.60). Runs identically inside a workspace, outside one, in
    recovery mode, and inside aos.pyz.
    """
    if candidate not in CANDIDATE_CHOICES:
        raise DatasetError(
            f"Unknown candidate {candidate!r}. Allowed: "
            + "|".join(CANDIDATE_CHOICES)
        )
    if not isinstance(k, int) or isinstance(k, bool) or not (K_MIN <= k <= K_MAX):
        raise DatasetError(f"Invalid --k {k}. Allowed: {K_MIN}..{K_MAX}.")

    dataset = get_benchmark(name)
    validate_dataset(
        {key: value for key, value in dataset.items()
         if key != protocols.CONTENT_HASH_FIELD}
    )
    wanted = list(CANDIDATES) if candidate == "all" else [candidate]

    evaluations = {c: _evaluate_candidate(dataset, c, k) for c in wanted}

    # Replay: evaluate a SECOND time and compare the canonical bytes. Cheap
    # (in memory, no I/O) and it proves the property the gate claims rather
    # than asserting it — a report that says "deterministic" because the code
    # was written carefully is a report that says nothing.
    replay = {c: _evaluate_candidate(dataset, c, k) for c in wanted}
    replay_ok = {
        c: protocols.serialize_canonical(_render_candidate(evaluations[c], None))
        == protocols.serialize_canonical(_render_candidate(replay[c], None))
        for c in wanted
    }

    baseline = evaluations.get(BASELINE)
    gates = {
        c: _gate(dataset, evaluations[c], baseline if c != BASELINE else None,
                 replay_ok[c])
        for c in wanted
    }

    report = {
        "report_version": REPORT_VERSION,
        "metrics_version": METRICS_VERSION,
        "benchmark": name,
        "dataset_version": dataset["dataset_version"],
        "dataset_sha256": dataset[protocols.CONTENT_HASH_FIELD],
        "k": k,
        "candidates": {
            c: _render_candidate(evaluations[c], gates[c]) for c in wanted
        },
        "deltas": {
            c: _deltas(evaluations[c], baseline)
            for c in wanted
            if c != BASELINE and baseline is not None
        },
        "recommendation": _recommend(evaluations, gates),
        # The exit code's input, spelled out rather than left for the reader
        # to derive: `baseline` is reported and never gated (D-v0.3.62).
        "gated_candidates": [c for c in wanted if c in PROMOTABLE],
        "passed": all(gates[c]["gate"] for c in wanted if c in PROMOTABLE),
    }
    document = protocols.serialize_canonical(report)
    if len(document) > MAX_REPORT_BYTES:
        raise DatasetError(
            f"The report is {len(document)} bytes; the maximum is "
            f"{MAX_REPORT_BYTES}. Nothing was printed. Narrow the run with "
            "--candidate."
        )
    return report
