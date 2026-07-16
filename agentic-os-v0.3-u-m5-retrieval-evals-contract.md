# Agentic OS v0.3 — U-M5: deterministic temporal and graph retrieval evaluations

Status: pinned before implementation.
Baseline: a27f591b5d0eda41b2badea28fd41b98184a4689 (U-M3, schema version 3).
Supersedes nothing. Extends U-M2 (memory claims), U-M3 (memory graph),
U-X1 (protocol spine / canonical JSON), U-E2 (power modes), U-C3 (secret
safety), U-P1 (packaging).

U-M5 adds a **candidate retriever** and a **benchmark harness**, and nothing
else. It answers one question with measurements instead of opinion: do
lexical, temporal, provenance and bounded graph signals retrieve better than
what this system does today, without leaking anything?

U-M5 changes no production retrieval path. `aos search`, `pack build` and
`ops.memory_for_project` behave at the end of this pass exactly as they did at
the baseline commit. Promotion is a separate, human decision informed by this
harness's report.

**No embeddings. No vector store. No model call. No network. No new
dependency. No schema change.**

---

## M5.0 Scope

### In scope

`agentic_os/retrieval.py`; a deterministic query tokenizer; a bounded
deterministic candidate retriever with depth-0 and depth-1 configurations;
explainable result metadata; checked-in synthetic benchmark datasets projected
to `retrieval_benchmarks/`; deterministic metrics; a promotion gate; a
deterministic recommendation; `aos retrieval benchmark list|show|run`; `aos
retrieval query`; one doctor registry check; command classification for every
new leaf; documentation.

### Explicitly NOT in scope (deferred, and refused if asked for)

- **Embeddings, vector stores, sqlite-vec, FAISS, pgvector, ANN indexes,
  learned weights, model calls, network access.** U-M5 exists to decide
  whether any of that is *warranted*; shipping it inside the unit that is
  supposed to measure the need for it would be assuming the answer.
- **U-M4**: memory proposal, approval, rejection, contest workflows.
- **U-M6**: Context Hydration Receipts.
- **Production adoption.** No command in this pass changes what `aos search`
  returns, what a pack contains, or any configuration file. `retrieval` is an
  inspection and evaluation surface.
- Agent, skill, tool or runtime integration; AICompany; remote execution.
- Automatic contradiction detection or inference of any kind.
- Graph visualization, dashboards, Canvas, Bases.

### Untouched (D-v0.3.52)

`db.SCHEMA_VERSION` stays `"3"`. No migration, no table, no index, no column.
U-X1 schema identities and the canonical JSON contract. `search.py` — not one
line. `pack.py` — not one line. `ops.memory_for_project`, `ops.claim_is_eligible`,
`ops.window_is_active`, `ops.memory_graph` — read and reused, never edited.
U-M2/U-M3 status, sensitivity, evidence-link and edge semantics. Hooks,
dropfile ingest, backup/restore, export containment, the agent registry,
networking.

---

## M5.1 Decisions

### D-v0.3.52 — U-M5 measures; it does not adopt.

The unit ships an explicit candidate retriever, datasets, a report and a gate.
It ships no switch. A pass that both proposed a retriever and wired it into
`pack build` would be a pass whose benchmark could never fail in a way anyone
acted on — the code would already be in production while the report was still
being read. Adoption is a human decision, taken after this report, in a later
unit. `benchmark run` prints a recommendation and changes nothing.

### D-v0.3.53 — The baseline is measured as it is, not rewritten to be easy.

`search.py` is not touched. The baseline candidate re-expresses the LIKE
backend's memory semantics over the shared corpus (M5.7), and a test proves it
returns the same memory result SET as the live `search.search()` for a matrix
of queries against a real workspace. Reimplementing rather than importing is
the only honest option available: `search.search()` needs a `sqlite3.Connection`
and returns rendered snippets, and the benchmark corpus is deliberately not a
database (D-v0.3.60). Reimplementing *and asserting equivalence* is a proof;
editing production so the benchmark can call it is a way of making the baseline
whatever the candidate needs it to be.

### D-v0.3.54 — Integers, ordinals and rationals. No float ever.

Every score component is an integer. The final sort key is a tuple of
integers. Metric values are computed as `fractions.Fraction` and rendered by
integer arithmetic to a fixed-width decimal STRING (M5.9). No `float` value is
constructed, compared, summed or serialized anywhere in this unit — including
nDCG, whose logarithmic discount comes from a checked-in exact-rational table
(D-v0.3.55). A benchmark whose digits depend on the platform's libm is not a
benchmark.

### D-v0.3.55 — nDCG's log2 discounts are a checked-in table, not `math.log2`.

`math.log2` is a libm call: correctly rounded on most platforms, not
guaranteed identical on all. `_LOG2_SCALED` pins log2(2)…log2(11) as integers
scaled by 10^12, written out as source literals, and the discount is the exact
rational `Fraction(10**12, _LOG2_SCALED[i])`. The table is a *definition* of
this metric, not an approximation of another one: two runs on two platforms
produce the same digits because they are computing the same rational number,
not because their libms happened to agree. A test compares the table to
`math.log2` on the local platform to catch a typo — that is the table checking
the transcription, not the transcription trusting the platform.

### D-v0.3.56 — Eligibility is one predicate, strictly stricter than the pack's.

`retrieval.eligibility()` returns a reason code from a closed set. It applies
U-M2/U-M3's lifecycle rules with the SAME spelling `ops.claim_is_eligible`
uses (status=live, unsuperseded, not restricted, unexpired), and adds three
things ordinary pack inclusion does not need:

1. **hash validity** — a claim whose stored hash does not verify is not
   retrievable. `ops.memory_for_project` deliberately does not re-verify
   (D-v0.3.21: one damaged row must not block every pack in the workspace).
   Retrieval can afford to be stricter because its pool is bounded and its
   exclusions are counted and reported: a dropped claim shows up in the report
   as a reason code, not as silence.
2. **`valid_from <= as-of`** — via `ops.window_is_active`, the existing
   predicate. `claim_is_eligible` checks expiry only; a claim whose window has
   not opened yet is not a fact about the requested instant.
3. **project compatibility** — global, or the requested project. Without
   `--project`, only `scope=global` is eligible, exactly as
   `memory_for_project(conn, None)` behaves.

A test proves the implication holds in the direction that matters:
`retrieval_eligible(c, t)` ⟹ `ops.claim_is_eligible(c, t)`. U-M5 can refuse
what the pack would carry; it can never carry what the pack would refuse.

### D-v0.3.57 — Every expanded result ranks below every primary result.

The sort key's first element is the origin ordinal (`0` primary, `1`
expanded). This makes "a graph neighbour must not outrank a strong direct
lexical match" true by construction rather than by weight-tuning, and it makes
the property testable with one assertion instead of a tournament of fixtures.
Expansion in U-M5 is a **recall instrument**: it appends to the tail, it never
reorders the head. If a later unit wants interleaved ranking, it will have
this report to argue from.

### D-v0.3.58 — A primary hit is conjunctive; a graph neighbour needs one token.

Primary inclusion requires **every** query token to appear in the claim —
the semantics both live search backends already have (FTS5 ANDs its terms;
the LIKE fallback requires each term as a substring). Expansion's documented
minimum relevance signal is **at least one** query token in the neighbour.
That gap is the whole point of expansion: a claim that partially matches and
is connected by an active edge to a full match is exactly the recall a lexical
retriever loses. A neighbour with **zero** query tokens is graph noise and is
never included, whatever its degree.

### D-v0.3.59 — Disputes and contradictions rank; they never judge and never exclude.

An active `disputes` source link and an active `contradicts` edge each
subtract a bounded, pinned number of points. Neither makes a claim ineligible,
neither hides it, neither resolves anything. U-M3 pinned that a contradiction
records that a human said two claims disagree, not which one is true
(D-v0.3.38); a retriever that dropped a contradicted claim would be answering
that question by omission. The result metadata carries the counts so the
reader can see the disagreement and decide.

### D-v0.3.60 — The benchmark corpus is memory, never a database.

`benchmark run` builds its corpus from the embedded fixture definitions in
Python and never opens `aos.db`. This is what makes "creates no database rows,
files, ledger events or workspace state" a structural fact rather than a
promise: there is no connection to write through. It also makes the run
byte-identical inside a workspace, outside one, in recovery mode, and inside
`aos.pyz`. `retrieval query` is the surface that reads a real ledger, and it
only reads.

### D-v0.3.61 — The embedded datasets are canonical; `retrieval_benchmarks/` is a projection.

Exactly the U-X1 mechanic (D-v0.3.2/D-v0.3.3), for exactly the U-X1 reason:
`aos.pyz` carries `.py` files and nothing else, so a JSON file could not be
the source of truth without either breaking the zipapp or widening its
allowlist. The Python definitions in `agentic_os/retrieval.py` are the one
editable registry; `tools/gen_retrieval_benchmarks.py --write` projects them;
`doctor` and the focused tests verify the projection byte-for-byte. There is
no second editable registry, and `tools/` is outside the package allowlist so
the writer never ships.

### D-v0.3.62 — `baseline` is reported, never gated.

`benchmark run`'s exit code is driven by validation plus the promotion gate of
the **candidates** evaluated (`candidate-0`, `candidate-1`). `baseline` is the
measured reference: it is what production does today, it cannot be "promoted",
and gating it would make `--candidate all` exit 1 forever the moment the
baseline was measured to leak — which is the finding, not a malfunction. The
baseline's gate verdict and every one of its leakage counters ARE printed, at
full severity, in the report. Nothing is hidden; one number is simply not
wired to the exit code.

### D-v0.3.63 — Truncation is reported, never silent, and never averaged.

Every bound in M5.11 truncates deterministically and increments a named
counter that appears in the report next to the metric it affected. Leakage
counters are integer sums over cases and are never divided by anything: an
average is how a leak in one case out of forty disappears.

### D-v0.3.64 — `--show-key` shows a key, and only for claims already eligible.

Human output defaults to metadata only. The one administrative content flag
prints the claim `key` — never `value_md`, never a source locator, never
provenance text, never an evidence ref. It is consistent with `memory show`,
which prints key AND value unredacted for exactly this population, because
every result is eligible by construction and `restricted` is an eligibility
exclusion: a restricted claim cannot reach the renderer to be redacted by it.
The flag shows strictly less than the command that already exists.

---

## M5.2 Text normalization

One tokenizer. `retrieval.tokenize(text) -> tuple[str, ...]`.

### Pipeline (in order)

1. **NFKC** via `unicodedata.normalize("NFKC", text)` — a named standard-library
   normalization form, pinned by name.
2. **`str.casefold()`** — locale-independent by definition, unlike `str.lower()`
   on a few code points and unlike any stemmer.
3. **Scan**, character by character. **No regex is used anywhere in the
   tokenizer**, so catastrophic backtracking is impossible by construction
   rather than by review. A token is a maximal run of characters for which
   `ch.isalnum() or ch == "_"` is true. Every other character is a separator.
   `wrong-project` → `wrong`, `project`.
4. **Stopword removal** — the pinned `STOPWORDS` frozenset below. Justified:
   the lexical component scores distinct-token overlap, and without this an
   English query's score would be dominated by the articles every claim
   contains. Checked in, ASCII, sorted, 33 words, never loaded from a file.
5. **Deduplicate**, preserving first occurrence. Order is the query's own.

```
STOPWORDS = a an and are as at be but by for from has have how in into is it
            its of on or that the this to was were what when where which with
```

Claim text is tokenized by the SAME function. One definition; a query token
and a document token cannot be produced by two different rules.

### It must not

Stem; use locale-sensitive case rules; load a language model; read an external
dictionary; transform stored claim content (tokenization is read-only and its
output never reaches a write); print a token, a claim value or a locator in
any diagnostic.

### Bounds (all three REFUSE; none truncates)

| Bound | Value | Measured on |
|---|---|---|
| `MAX_QUERY_BYTES` | 512 | `len(query.encode("utf-8"))`, raw input |
| `MAX_QUERY_CHARS` | 256 | `len(query)`, raw input |
| `MAX_QUERY_TOKENS` | 32 | deduped, stopword-free token count |

Refuse, not truncate: a truncated query silently answers a different question
than the one asked, and the caller has no way to know. Bytes and chars are
both measured because neither bounds the other — 256 astral characters are
1024 bytes, and 512 ASCII bytes are 512 characters.

### Empty token set

A query that normalizes to zero tokens (whitespace, punctuation, only
stopwords) is **not an error**. It returns an empty result list with
`reason: "no_usable_tokens"`. Refusing would make `retrieval query "the"` an
error where `aos search` returns nothing; returning everything would be worse.

### Phrase

`normalized_phrase(text)` = NFKC + casefold + collapse whitespace runs to one
`U+0020` + strip. The phrase component tests `query_phrase in claim_phrase`
(Python substring, no regex). Stopwords are NOT removed for the phrase form —
a phrase is a phrase.

---

## M5.3 The corpus

`retrieval.Corpus` is an immutable in-memory structure: claims, edges, and
per-claim provenance-link windows. Two loaders, one consumer.

| Loader | Source | Used by |
|---|---|---|
| `corpus_from_db(conn, project_slug)` | bounded SQL over a real v3 ledger | `retrieval query` |
| `corpus_from_fixture(dataset)` | embedded synthetic definitions | `benchmark run` |

`RetrievalClaim` fields: `id`, `scope`, `project`, `kind`, `key`, `text`
(`key` + `"\n"` + `value_md`), `status`, `pinned`, `sensitivity`, `valid_from`,
`valid_until`, `superseded_by`, `integrity`, `content_sha256`, `sources`
(tuple of `(relation, valid_from, valid_until)`).

`integrity` is `ops.claim_integrity()`'s answer for a DB claim, and the
fixture's declared `hash_valid` for a synthetic one — a fixture claim is not a
hashed row, so it declares the condition instead of faking the cause.

### Pool

`SELECT * FROM memory ORDER BY id LIMIT MAX_POOL_CLAIMS + 1`. **No predicate
is applied in SQL — not even the project clause.** Two reasons, both
load-bearing:

- The BASELINE must see what `aos search` sees, and `aos search` has no project
  filter at all. A corpus pre-filtered by project would make the baseline look
  safe by construction and the whole measurement a lie (D-v0.3.53).
- One eligibility implementation (M5.4), in Python, exercised identically by
  the DB corpus and the fixture corpus — instead of a SQL rule and a Python
  rule that must be kept in agreement forever. It is also what lets the fixture
  contain the wrong-project and restricted claims the tests must prove are
  excluded.

Over the pool cap → `truncation.pool` and the first `MAX_POOL_CLAIMS` by
ascending id.

### Latest-per-key

After eligibility, the corpus keeps the highest `id` per
`(scope, project, key)` — `memory_for_project`'s existing rule, reused rather
than re-invented, so the candidate can never surface a stale row for a key the
pack would not show. Shadowed rows are dropped before scoring AND before
expansion; a graph neighbour that is a shadowed row is not a neighbour.

---

## M5.4 Eligibility

`eligibility(claim, as_of, project) -> str`, one closed reason vocabulary:

```
ELIGIBLE_OK        = "ok"
"status"           status != live                   (proposed|contested|quarantined|retired)
"superseded"       superseded_by is not None
"restricted"       sensitivity == restricted
"temporal"         not ops.window_is_active(valid_from, valid_until, as_of)
"hash"             integrity != "ok"
"project"          scope == project and project != requested   (or no project requested)
```

Evaluated in exactly that order; the first failing reason is the answer. A
claim is retrievable iff the answer is `"ok"`. Pinned status is NOT on this
list: pinning is ranking, never permission (U-M2's rule, reaffirmed).

---

## M5.5 Scoring

Every component is an integer. Weights are pinned here and nowhere else.

Let `Q` = deduped query tokens, `C` = claim-text tokens, `K` = claim-`key`
tokens, `n = |Q ∩ C|`, `t` = as-of.

| # | Component | Weight | Definition |
|---|---|---|---|
| 1 | `lexical` | **10** each | `10 × n` |
| 2 | `phrase` | **25** | `25` if `normalized_phrase(query) in normalized_phrase(claim.text)` else `0` |
| 3 | `key` | **40** / **5** each | `40` if `tokenize(claim.key) == Q` (TOKENS, not the raw phrase — keys are hyphenated slugs and `deploy-window` must equal the query `deploy window`), else `5 × |Q ∩ K|` |
| 4 | `pinned` | **8** | `8` if `claim.pinned` else `0` |
| 5 | `scope` | **6** | `6` if `claim.scope == "project"` else `0` (project-specific beats global when both match) |
| 6 | `freshness` | **12/8/4/0** | age = `t` − `claim.valid_from` in whole UTC days: `≤30 → 12`, `≤90 → 8`, `≤365 → 4`, else `0` |
| 7 | `supported` | **+4** each | `4 × min(active supports links, 3)` → max `12` |
| 8 | `disputed` | **−6** each | `−6 × min(active disputes links, 3)` → min `−18` |
| 9 | `graph` | **+2** each | `2 × min(INBOUND active `supports` edges from another ELIGIBLE claim, 3)` → max `6`. Inbound only: `X supports Y` says something about Y, not about X. |
| 10 | `contradicted` | **−3** each | `−3 × min(active `contradicts` edges whose OTHER endpoint is an ELIGIBLE claim, 3)` → min `−9`. Symmetric, so either endpoint counts it. |

Both require the other endpoint to be eligible, for the same reason as every
other rule here: a retired claim's opinion about a live one is not a signal
retrieval acts on. Component 9 reads edges at BOTH depths — it is a bounded
count on a hit, not expansion, and it introduces no result.

`total = Σ components`. Components are reported individually; the total is
never the only number shown (M5.6).

Weight rationale, pinned so a later reader is not reverse-engineering it: a
key equality (40) beats a phrase hit (25) beats four token overlaps (40 —
deliberately equal to key equality, because four distinct query terms in a
claim IS as strong a signal). Pin (8) and scope (6) are tie-breakers between
otherwise comparable claims, both smaller than one token of overlap (10), so
neither can promote a weaker match over a stronger one. Provenance moves a
claim by at most ±18 — under two tokens — because provenance is evidence about
a claim, not evidence that it answers this query. Graph and contradiction
signals are the smallest of all, capped at +6 and −9.

Ages use `date.fromisoformat(value[:10])` on both spellings U-M3 pinned
(`YYYY-MM-DD` and `YYYY-MM-DDTHH:MM:SSZ`), so the arithmetic is integer days
between two calendar dates. `t` is the requested as-of, never the wall clock.

### Sort key

```
(origin_ordinal, -total, memory_id)     ascending
origin_ordinal: 0 = primary, 1 = expanded          (D-v0.3.57)
```

Every element is an integer. Ties end with the numeric memory ID, always.

---

## M5.6 Candidates

| Name | Rule |
|---|---|
| `baseline` | Faithful LIKE-backend memory semantics: conjunctive case-insensitive substring of each whitespace-split raw query term over `key + "\n" + value_md`; **no eligibility filter**; ascending memory id; first `limit`. |
| `candidate-0` | Eligibility (M5.4) + latest-per-key + conjunctive primaries (D-v0.3.58) + scoring (M5.5) + sort key. **Graph depth 0: no edge is read for expansion.** |
| `candidate-1` | `candidate-0` plus depth-1 expansion (M5.7). |

The baseline reproduces the LIKE fallback's ordering (ascending id), not
FTS5's `rank`. FTS5's ordering is a property of the SQLite build, and a
benchmark whose ranking depends on which SQLite the runner happens to have is
not a benchmark. The fidelity test compares result SETS against whichever
backend is live, which is the part that is backend-independent.

The baseline's `restricted` handling is the live one: the hit is returned; its
text is suppressed. U-M5 never prints claim text for the baseline at all, so
suppression is structural — and the hit itself is exactly the restricted
leakage the report counts.

---

## M5.7 Graph expansion

Explicit, optional, depth 0 or 1. **Depth 2 does not exist in U-M5** —
`--graph-depth` accepts `0|1` and `candidate-1` is depth 1. Nothing here calls
`ops.memory_graph`, whose `MAX_GRAPH_DEPTH = 2` serves a different purpose
(human inspection).

Depth 0: no edge row is read for expansion. (Component 9 reads `supports`
edges for SCORING at both depths — that is a bounded count on a primary hit,
not expansion, and it introduces no result.)

Depth 1, in order:

1. Iterate primary hits **in final rank order**.
2. For each, its incident edges (`from_memory_id = p OR to_memory_id = p`) in
   **ascending edge id**.
3. Skip the edge unless `ops.window_is_active(edge.valid_from, edge.valid_until, as_of)` — **only active edges**.
4. The neighbour must be **eligible** (M5.4) and present in the latest-per-key
   corpus. Restricted, historical, expired, superseded, hash-invalid and
   wrong-project claims are excluded by the same predicate that excludes them
   as primaries — there is no second, weaker gate on the expansion path.
5. Skip a neighbour already returned as a primary or already expanded.
6. **Minimum relevance signal**: `|Q ∩ C_neighbour| ≥ 1`. Zero → excluded,
   whatever its degree (D-v0.3.58).
7. Score it exactly as a primary (M5.5), with `origin_ordinal = 1`.
8. Record `graph_origin`: `{via, edge, relation, direction}`.
   `direction` is `"symmetric"` for `contradicts`/`related`
   (`models.MEMORY_EDGE_SYMMETRIC`), else `"out"` when the primary is the
   edge's `from`, `"in"` when it is the `to`. Directional edges keep their
   direction; symmetric ones report that they have none.

No edge is inferred. `contradicts` expands like any other relation and is
marked as what it is — it resolves nothing (D-v0.3.59).

### Caps

| Bound | Value | On exceed |
|---|---|---|
| `MAX_GRAPH_EDGES_SCANNED` | 64 | stop, `truncation.graph_edges = 1` |
| `MAX_GRAPH_NODES_ADDED` | 16 | stop, `truncation.graph_nodes = 1` |

Truncation stops the expansion loop at a deterministic point (the order in
steps 1–2 is total), reports itself, and never refuses the query.

---

## M5.8 Result shape

One result, all fields deterministic:

```
memory            "M-0007"
rank              1-based integer
origin            "primary" | "expanded"
score             integer total
components        {lexical, phrase, key, pinned, scope, freshness,
                   supported, disputed, graph, contradicted}   integers
reasons           sorted subset of the closed vocabulary:
                  all_tokens · phrase · key_exact · key_overlap · pinned ·
                  project_scope · fresh · supported · disputed ·
                  graph_supported · contradicted · graph_expanded
scope             "global" | "project"
project           slug | null
status            claim status
superseded        bool — a superseded claim's STATUS is still `live`
                  (supersession is a pointer, not a status), so without this
                  the metadata would show `status: live` for a claim the pack
                  builder would refuse
integrity         "ok" | "malformed" | "mismatch" | "unhashable"
sensitivity       claim sensitivity
pinned            bool
temporal_active   bool
supporting_sources  int      disputing_sources  int
contradictions    int
graph_origin      {via, edge, relation, direction} | null
hash_prefix       models.hash_prefix(content_sha256)   — 12 chars (M2.6)
key               present ONLY with --show-key         (D-v0.3.64)
```

### Never, in any output, under any flag

`value_md` · source locator · provenance text · evidence ref · evidence claim
· a full hash · restricted content · an arbitrary SQLite value · a query
token · a stopword list dump. Diagnostics name reason codes, ids, counts and
enum members.

---

## M5.9 Metrics

`METRICS_VERSION = 1`. `R` = returned ids truncated to `k`, `G` = relevant,
`F` = forbidden.

| Metric | Formula | Empty behavior |
|---|---|---|
| `hit_at_k` | `1` if `|R ∩ G| > 0` else `0` | `null` when `G = ∅` |
| `precision_at_k` | `|R ∩ G| / |R|` | `null` when `R = ∅` |
| `recall_at_k` | `|R ∩ G| / |G|` | `null` when `G = ∅` |
| `mrr` | `1 / rank of first r ∈ R ∩ G`; `0` if none | `null` when `G = ∅` |
| `ndcg_at_k` | `DCG/IDCG`, `DCG = Σᵢ (2^gradeᵢ − 1) × Fraction(10¹², _LOG2_SCALED[i])`, IDCG over grades sorted descending, truncated to `k` | `null` when the case declares no `graded`; `null` when `IDCG = 0` |

`null` is excluded from aggregates. Every aggregate reports the `n` of cases
that contributed, so a mean over 3 of 17 cases cannot read as a mean over 17.

### Counters — integer sums over cases, never averaged (D-v0.3.63)

```
forbidden_results       Σ |R ∩ F|
wrong_project_leaks     Σ |{r ∈ R : r.scope = project ∧ r.project ≠ case.project}|
restricted_leaks        Σ |{r ∈ R : r.sensitivity = restricted}|
lifecycle_leaks         Σ |{r ∈ R : status ≠ live ∨ superseded ∨ ¬window_active(as_of)}|
hash_invalid_included   Σ |{r ∈ R : integrity ≠ "ok"}|
truncations             Σ 1 per case with any truncation counter set
```

Plus `avg_results` = mean `|R_full|` (before the `k` cutoff) — a relevance
convenience, and the ONE mean that touches result counts. No leakage class has
a mean.

### Rendering

`fractions.Fraction` throughout; rendered to a **4-decimal STRING** by integer
arithmetic, ROUND_HALF_UP:

```
digits = (|num| × 20000 + den) // (2 × den)      # over 10^4, half-up
```

Strings, not JSON numbers: a JSON number is a float to almost every consumer,
and D-v0.3.54 says no float. `"0.6667"`. `null` stays `null`.

---

## M5.10 Datasets, registry, digests

### Canonical source

Python literals in `agentic_os/retrieval.py`. Projected to
`retrieval_benchmarks/registry.json` and `retrieval_benchmarks/<name>.json` by
`tools/gen_retrieval_benchmarks.py --write` (D-v0.3.61). Serialization is
U-X1's `protocols.serialize_canonical_file_bytes`; digests are
`protocols.content_digest` — lowercase SHA-256 over the canonical body with
the top-level `content_sha256` removed.

### Dataset

```
dataset_version   1        (DATASET_VERSION; any other value refuses)
benchmark         name, ^[a-z][a-z0-9-]*$, ≤ 48 chars
description       ≤ 200 chars
thresholds        {min_hit_rate, min_mrr}   4-decimal strings
fixture           {projects: [slug…], claims: [FixtureClaim…], edges: [FixtureEdge…]}
cases             [Case…]
content_sha256    lowercase sha256
```

`FixtureClaim`: `id` (1..MAX_FIXTURE_CLAIMS), `scope`, `project`, `kind`,
`key`, `value`, `status`, `pinned`, `sensitivity`, `valid_from`,
`valid_until`, `superseded_by`, `hash_valid`, `sources`
(`[{relation, valid_from, valid_until}]`).

`FixtureEdge`: `id`, `from`, `to`, `relation`, `valid_from`, `valid_until`.
Symmetric relations must satisfy `from < to` — U-M3's storage canonicalization
(D-v0.3.36) holds in the fixture too, so a fixture cannot express an edge the
real schema would refuse.

`Case`: `case` (`^[a-z][a-z0-9-]*$`, ≤ 48), `query`, `project` (slug|null),
`as_of` (U-M3 instant), `config` `{limit: 1..MAX_RESULTS}`, `relevant` `[int]`,
`graded` `{str(id): 0..3}` | absent, `forbidden` `[int]`,
`leakage_probes` `[class…]`, `rationale` (≤ 200 chars).

`config.limit` is the retriever's limit for the case; `--k` is the metric
cutoff. Two bounded knobs, one job each, neither derived from the other.

`leakage_probes` names the classes a case is **designed to exercise**
(`wrong_project`, `restricted`, `lifecycle`, `hash_invalid`, `forbidden`,
`graph_noise`, `none`). It is documentation, never permission: a probe never
licenses a leak, and any actual leakage fails the gate (M5.12).

### Registry

```
registry_version  1
benchmarks        [{name, dataset_version, cases, fixture_claims, sha256}]  sorted by name
content_sha256
```

### Refusals (all `AosError`, exit 1, nothing written)

duplicate benchmark name · duplicate case id within a benchmark · malformed
benchmark/case id · unknown candidate name · unknown metric version ·
unsupported `dataset_version`/`registry_version` · relevance grade outside
0..3 · a grade for an id not in `relevant` · `relevant` incomplete when
`graded` is present · duplicate id in `relevant` or `forbidden` · an id in
both `relevant` and `forbidden` · an id that is not a fixture claim · an
unknown field in any object · a fixture over `MAX_FIXTURE_CLAIMS` · a dataset
over `MAX_DATASET_CASES` · a projected file that does not match the embedded
definition byte-for-byte · a `retrieval_benchmarks/*.json` that projects
nothing.

**These are explicit, hand-written validators over a closed field set. U-M5
claims no general JSON Schema support** and registers no U-X1 schema
identity — U-X1's registry is untouched (M5.0).

---

## M5.11 Bounds

| Bound | Value | On exceed |
|---|---|---|
| `MAX_QUERY_BYTES` | 512 | refuse |
| `MAX_QUERY_CHARS` | 256 | refuse |
| `MAX_QUERY_TOKENS` | 32 | refuse |
| `MAX_CLAIM_TEXT_CHARS` | 4096 | tokenize the first 4096, `truncation.claim_text += 1` |
| `MAX_POOL_CLAIMS` | 500 | first 500 by id, `truncation.pool = 1` |
| `MAX_RESULTS` | 20 | `--limit` refuses above it |
| `MAX_GRAPH_EDGES_SCANNED` | 64 | stop, report |
| `MAX_GRAPH_NODES_ADDED` | 16 | stop, report |
| `MAX_DATASET_CASES` | 64 | refuse |
| `MAX_FIXTURE_CLAIMS` | 64 | refuse |
| `MAX_FIXTURE_EDGES` | 128 | refuse |
| `MAX_REPORT_BYTES` | 262144 | refuse to print; exit 1 naming the bound |
| `K_MIN` / `K_MAX` | 1 / 10 | `--k` refuses outside |

Query bounds refuse; corpus/graph bounds truncate and report (D-v0.3.63).
Reason: the caller wrote the query and can fix it; the caller did not write
the ledger and cannot.

---

## M5.12 Promotion gate

Per candidate, all of:

```
safety_ok      forbidden_results == 0 ∧ wrong_project_leaks == 0 ∧
               restricted_leaks == 0 ∧ lifecycle_leaks == 0 ∧
               hash_invalid_included == 0
bounds_ok      ∀ cases: |R_full| ≤ config.limit ∧ graph nodes ≤ MAX_GRAPH_NODES_ADDED
               ∧ graph edges ≤ MAX_GRAPH_EDGES_SCANNED
thresholds_ok  hit_rate ≥ thresholds.min_hit_rate ∧ mrr ≥ thresholds.min_mrr
               (per benchmark, compared as Fractions)
no_regression  hit_rate ≥ baseline.hit_rate ∧ mrr ≥ baseline.mrr
               ∧ ndcg_at_k ≥ baseline.ndcg_at_k
               (per benchmark; null when baseline was not evaluated)
replay_ok      the evaluation is executed twice and the canonical report
               digests are equal
gate           safety_ok ∧ bounds_ok ∧ thresholds_ok ∧ no_regression ∧ replay_ok
```

**Any** forbidden, wrong-project, restricted, lifecycle or hash-invalid
inclusion fails the gate, whatever the aggregate relevance says. There is no
weighting between safety and relevance: one is a bug, the other is a score.

`baseline` is evaluated and reported, never gated (D-v0.3.62).

### Recommendation — a function of gates, not of prose

Let `A(c) = (hit_rate, mrr, ndcg_at_k)` over the run's benchmark aggregate,
compared as Fractions; a `null` on either side of a pair is skipped.

```
candidate-1 gate ∧ A(c1) ≥ A(c0) componentwise
                 ∧ strictly greater on at least one          → "promote candidate-1"
else candidate-0 gate                                        → "promote candidate-0"
else baseline evaluated ∧ no candidate gate passed           → "keep baseline"
else                                                         → "insufficient evidence"
```

`ndcg_at_k` is in the triple deliberately: it is the only aggregate that
notices when expansion buys recall, and a rule that ignored it could never
recommend `candidate-1` at all. It also penalizes an irrelevant result in the
top-k, so the rule cannot be gamed by returning more.

Computed only for `--candidate all`; any narrower run reports `insufficient
evidence` with `reason: partial_evaluation`. Advisory. No command acts on it.

---

## M5.13 CLI

```
aos retrieval benchmark list [--json]
aos retrieval benchmark show NAME [--json]
aos retrieval benchmark run  NAME [--json] [--candidate baseline|candidate-0|candidate-1|all] [--k 1..10]
aos retrieval query QUERY [--project SLUG] [--as-of TS] [--limit N] [--graph-depth 0|1] [--json] [--show-key]
```

Defaults: `--candidate all`, `--k 5`, `--limit 5`, `--graph-depth 0`,
`--as-of` = `utils.utc_now_iso()`.

| Leaf | Behavior |
|---|---|
| `benchmark list` | Names, `dataset_version`, case counts, fixture-claim counts, content digests. Sorted by name. No workspace needed. |
| `benchmark show` | Metadata, thresholds and **case IDs only**. No query, no fixture body, no synthetic value. There is no fixture-detail mode in U-M5: `retrieval_benchmarks/<name>.json` is the checked-in, digest-verified place to read a fixture. |
| `benchmark run` | Validates, evaluates, replays, gates. Opens no database, writes no file, emits no event, creates no workspace state (D-v0.3.60). Runs identically inside and outside a workspace. |
| `retrieval query` | Requires an initialized v3 workspace. Read-only: no claim, hash, graph row, pack, mirror, index, FTS table or watermark is written. Honors recovery. |

### Exit codes and streams

`benchmark run`: **0** iff validation passed AND every **candidate**
(`candidate-0`/`candidate-1`) evaluated passed its gate. Otherwise **1**, with
the complete report still on stdout — the report IS the finding — and ONE
actionable line on stderr. With `--json`, stdout is exactly one JSON document
in both cases. A validation refusal (M5.10) is an `AosError`: exit 1, stderr
only, **stdout byte-empty**. Same shape as `protocol verify-registry`.

Everything else: 0 success · 1 domain error · 2 internal.

### Classification (M5.14)

All four leaves are `power.READ_ONLY`:

```
("retrieval", "benchmark", "list")  READ_ONLY
("retrieval", "benchmark", "show")  READ_ONLY
("retrieval", "benchmark", "run")   READ_ONLY
("retrieval", "query")              READ_ONLY
```

Read-only by *implementation*, read out of the code as the matrix requires:
`benchmark *` touches no connection at all; `query` issues `SELECT` only.
Recovery therefore permits all four. **No retrieval command creates
`power.json`** — none writes power state, and `power.read_state` only reads.

---

## M5.14 Doctor

**One** check, appended after the U-M3 lines (check 31): *"retrieval
benchmark registry verified"*.

- Recomputes every embedded dataset's canonical bytes and digest (always).
- In a source checkout, compares `retrieval_benchmarks/` byte-for-byte and
  FAILS on drift — unlike U-X1, U-M5 ships no `verify-registry` command, so
  without this line a drifted projection is invisible outside the test suite.
- Inside `aos.pyz`, where no `retrieval_benchmarks/` exists, it verifies the
  embedded canonical definitions and **passes** — a check that fails for
  running the supported artifact is a check people learn to ignore
  (D-v0.3.2).
- **The PASSING detail is a function of the embedded definitions ALONE**
  (`"N benchmark(s), M case(s)"`). Doctor's stdout is an entrypoint-parity
  surface: a script and `aos.pyz` must print the same bytes, and a detail that
  said *"3 artifacts compared"* in a checkout and *"nothing to compare"* in the
  archive would make one true sentence out of two different doctors. The
  comparison still happens where a checkout exists, and drift still FAILS —
  that comparison just cannot be what the healthy line says. This is the one
  place U-M5's doctor line differs from `protocol verify-registry`, which is a
  standalone command and therefore free to describe its own environment.
- **Never runs a benchmark.** Doctor is a health check, not a CI job.

---

## M5.15 Privacy and safety

Proven, not asserted:

- Retrieval never returns wrong-project, restricted, non-live, expired,
  superseded or hash-invalid claims — one predicate (M5.4), the fixture
  corpus contains all six, and the counters are zero.
- No diagnostic, result, report or doctor line echoes a planted secret-shaped
  value, a source locator, provenance text or an evidence ref. The fixtures
  plant secret-shaped values in restricted and wrong-project claim bodies
  precisely so a careless implementation would print them.
- **Nothing is dereferenced.** No `open()` of a locator, no URL fetch, no
  subprocess, no artifact import, no network. `retrieval.py` imports no
  `socket`, `urllib`, `subprocess` or `http` module. Proven by patching
  `open`, `socket.socket` and `subprocess.run` to raise and running the whole
  surface: retrieval is unaffected because it never calls them.
- Datasets are synthetic. No real project name, secret, path, evidence ref,
  URL or memory body. Fixture projects are `alpha`/`beta`; keys and values are
  invented.

---

## M5.16 Parity

`python3 aos.py`, `python3 -m agentic_os` and `python3 dist/aos.pyz` produce
identical stdout and identical exit codes for: `benchmark list`,
`benchmark show`, `benchmark run` (pass), `benchmark run` (gate failure),
`retrieval query`, and every `--json` document. The zipapp works outside the
checkout with `PYTHONPATH` cleared, carrying its datasets as Python
(D-v0.3.61). The archive gains `agentic_os/retrieval.py` and nothing else: no
database, workspace, snapshot, backup, real claim, vault file or repository
file — the existing `.py`-under-package allowlist already guarantees it, and
no packaging change is made.

---

## M5.17 Decision index

| ID | Decision |
|---|---|
| D-v0.3.52 | U-M5 measures; it does not adopt. |
| D-v0.3.53 | The baseline is measured as it is, not rewritten to be easy. |
| D-v0.3.54 | Integers, ordinals and rationals. No float ever. |
| D-v0.3.55 | nDCG's log2 discounts are a checked-in table, not `math.log2`. |
| D-v0.3.56 | Eligibility is one predicate, strictly stricter than the pack's. |
| D-v0.3.57 | Every expanded result ranks below every primary result. |
| D-v0.3.58 | A primary hit is conjunctive; a graph neighbour needs one token. |
| D-v0.3.59 | Disputes and contradictions rank; they never judge and never exclude. |
| D-v0.3.60 | The benchmark corpus is memory, never a database. |
| D-v0.3.61 | The embedded datasets are canonical; `retrieval_benchmarks/` is a projection. |
| D-v0.3.62 | `baseline` is reported, never gated. |
| D-v0.3.63 | Truncation is reported, never silent, and never averaged. |
| D-v0.3.64 | `--show-key` shows a key, and only for claims already eligible. |
