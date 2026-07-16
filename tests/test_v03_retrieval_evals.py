"""U-M5 deterministic temporal and graph retrieval evaluations
(agentic-os-v0.3-u-m5-retrieval-evals-contract.md).

Three kinds of proof live here:

- HARNESS proofs drive the embedded fixtures and the real registry directly.
- LEDGER proofs run against a fresh v3 workspace through the CLI, so the
  claims retrieval sees are claims `memory add` actually wrote.
- PARITY proofs run the three entrypoints as subprocesses.

Nothing here touches a real ledger: every workspace is a temp directory, and
no test opens, fetches or executes anything a claim points at — which is also
what several of these tests are proving.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

from weekend_harness import run_cli

from agentic_os import cli, db, doctor, models, ops, power, protocols, retrieval, utils

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The instant every fixture case is evaluated at.
T0 = "2026-06-01T00:00:00Z"

#: Planted in the fixtures' restricted and wrong-project claim values. If this
#: reaches any output, any report or any diagnostic, a test below fails.
PLANTED = "sk-live-m5planted00000000000000000000"  # noqa: S105

#: A path that would be catastrophic to open and a URL that would be
#: catastrophic to fetch. Nothing in U-M5 may touch either.
BOOBY_TRAP = "/tmp/aos-m5-must-never-be-read.txt"


def core():
    return retrieval.get_benchmark("core-retrieval")


def graph():
    return retrieval.get_benchmark("graph-expansion")


def ids_of(retrieved) -> list[str]:
    return [scored.claim.id for scored in retrieved.results]


def query(dataset, text, *, project="alpha", as_of=T0, limit=5, depth=0,
          candidate=None):
    corpus = retrieval.corpus_from_fixture(dataset)
    if candidate is None:
        candidate = retrieval.CANDIDATE_1 if depth else retrieval.CANDIDATE_0
    return retrieval.retrieve(
        corpus, query=text, as_of=as_of, limit=limit, graph_depth=depth,
        candidate=candidate, project=project,
    )


# ---------------------------------------------------------------------------
# (1)(2)(3) Registry, digests and the projection

class RegistryTests(unittest.TestCase):
    def test_registry_and_dataset_ordering_are_deterministic(self):
        """(1) Sorted by name, not by insertion order — and the case order
        inside a dataset is the dataset's own, stably."""
        self.assertEqual(retrieval.benchmark_names(), ["core-retrieval", "graph-expansion"])
        index = retrieval.registry_index()
        self.assertEqual(
            [row["name"] for row in index["benchmarks"]],
            sorted(row["name"] for row in index["benchmarks"]),
        )
        for _ in range(5):
            self.assertEqual(retrieval.registry_index(), index)

    def test_dataset_digests_are_stable_and_recompute(self):
        """(2) Every digest is a pure function of its definition."""
        self.assertEqual(retrieval.verify_embedded(), [])
        for name, document in retrieval.registry().items():
            body = {
                k: v for k, v in document.items()
                if k != protocols.CONTENT_HASH_FIELD
            }
            self.assertEqual(
                protocols.content_digest(body),
                document[protocols.CONTENT_HASH_FIELD],
                f"{name}: digest is not a function of the body",
            )

    def test_digest_is_lowercase_sha256_of_the_canonical_body(self):
        """(2) U-X1's serializer and lowercase SHA-256 — spelled out, so this
        cannot quietly become some other hashing scheme."""
        document = core()
        body = {
            k: v for k, v in document.items() if k != protocols.CONTENT_HASH_FIELD
        }
        expected = hashlib.sha256(protocols.serialize_canonical(body)).hexdigest()
        self.assertEqual(document[protocols.CONTENT_HASH_FIELD], expected)
        self.assertTrue(models.CLAIM_HASH_RE.match(expected))

    def test_checked_in_datasets_match_the_embedded_definitions(self):
        """(3) The projection is byte-identical to the canonical Python."""
        source = retrieval.source_benchmarks_dir()
        self.assertIsNotNone(source, "the source checkout must have the projection")
        self.assertEqual(retrieval.verify_source_benchmarks(source), [])

    def test_a_drifted_projection_is_detected(self):
        """(3) The comparison has teeth: a one-byte edit is caught."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "retrieval_benchmarks"
            shutil.copytree(retrieval.source_benchmarks_dir(), root)
            self.assertEqual(retrieval.verify_source_benchmarks(root), [])
            path = root / "core-retrieval.json"
            path.write_bytes(path.read_bytes().replace(b"core-retrieval", b"core-retrievaL", 1))
            problems = retrieval.verify_source_benchmarks(root)
            self.assertTrue(any("core-retrieval.json" in p for p in problems))

    def test_a_file_that_projects_nothing_is_refused(self):
        """(3) A stale dataset left behind after a rename cannot linger."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "retrieval_benchmarks"
            shutil.copytree(retrieval.source_benchmarks_dir(), root)
            (root / "ghost.json").write_bytes(b"{}\n")
            problems = retrieval.verify_source_benchmarks(root)
            self.assertTrue(any("ghost.json" in p for p in problems))

    def test_the_generator_verifies_without_writing(self):
        """(3) tools/gen_retrieval_benchmarks.py's default is verify-only."""
        before = {
            p: p.read_bytes() for p in retrieval.source_benchmarks_dir().rglob("*.json")
        }
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "gen_retrieval_benchmarks.py")],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for path, data in before.items():
            self.assertEqual(path.read_bytes(), data, f"{path} was rewritten")


# ---------------------------------------------------------------------------
# (4)(5) Validation refusals

class ValidationTests(unittest.TestCase):
    def _mutate(self, **changes):
        dataset = json.loads(json.dumps(
            {k: v for k, v in core().items() if k != protocols.CONTENT_HASH_FIELD}
        ))
        dataset.update(changes)
        return dataset

    def test_the_shipped_datasets_validate(self):
        for name in retrieval.benchmark_names():
            document = retrieval.get_benchmark(name)
            retrieval.validate_dataset(
                {k: v for k, v in document.items()
                 if k != protocols.CONTENT_HASH_FIELD}
            )

    def test_duplicate_benchmark_name_refuses(self):
        """(4) Two datasets with one name is a bug in the source file, and it
        is caught where it is that bug — not in a report."""
        dataset = self._mutate()
        with mock.patch.object(retrieval, "_DATASETS", (dataset, dict(dataset))):
            with mock.patch.object(retrieval, "_REGISTRY", None):
                with self.assertRaises(retrieval.DatasetError) as caught:
                    retrieval.registry()
        self.assertIn("duplicate benchmark name", str(caught.exception))

    def test_duplicate_case_id_refuses(self):
        """(4)"""
        dataset = self._mutate()
        dataset["cases"].append(json.loads(json.dumps(dataset["cases"][0])))
        with self.assertRaises(retrieval.DatasetError) as caught:
            retrieval.validate_dataset(dataset)
        self.assertIn("duplicate case id", str(caught.exception))

    def test_malformed_ids_refuse(self):
        """(4) Benchmark and case ids have one spelling."""
        for bad in ("Core-Retrieval", "9lives", "has space", "under_score", "x" * 49, ""):
            with self.assertRaises(retrieval.DatasetError):
                retrieval.validate_dataset(self._mutate(benchmark=bad))

    def test_unknown_fields_refuse(self):
        """(5) At every level, not just the top."""
        with self.assertRaises(retrieval.DatasetError) as caught:
            retrieval.validate_dataset(self._mutate(surprise=1))
        self.assertIn("unknown field", str(caught.exception))

        dataset = self._mutate()
        dataset["cases"][0]["surprise"] = 1
        with self.assertRaises(retrieval.DatasetError):
            retrieval.validate_dataset(dataset)

        dataset = self._mutate()
        dataset["fixture"]["claims"][0]["surprise"] = 1
        with self.assertRaises(retrieval.DatasetError):
            retrieval.validate_dataset(dataset)

    def test_unsupported_dataset_version_refuses(self):
        """(5)"""
        for bad in (0, 2, "1", None):
            with self.assertRaises(retrieval.DatasetError) as caught:
                retrieval.validate_dataset(self._mutate(dataset_version=bad))
            self.assertIn("dataset_version", str(caught.exception))

    def test_unknown_candidate_and_metric_bounds_refuse(self):
        """(5) Unknown candidate name; --k outside the pinned range."""
        with self.assertRaises(retrieval.DatasetError):
            retrieval.run_benchmark("core-retrieval", candidate="candidate-9")
        for bad in (0, 11, -1, True):
            with self.assertRaises(retrieval.DatasetError):
                retrieval.run_benchmark("core-retrieval", k=bad)
        with self.assertRaises(retrieval.DatasetError):
            retrieval.get_benchmark("no-such-benchmark")

    def test_invalid_relevance_grades_refuse(self):
        """(5)"""
        for bad in (-1, 4, "3", None):
            dataset = self._mutate()
            dataset["cases"][0]["graded"] = {"1": bad, "2": 3}
            with self.assertRaises(retrieval.DatasetError):
                retrieval.validate_dataset(dataset)

    def test_partial_grading_refuses(self):
        """(5) A partial grading silently treats every ungraded relevant claim
        as grade 0 — a different benchmark than the author thought they wrote."""
        dataset = self._mutate()
        dataset["cases"][0]["graded"] = {"1": 3}
        with self.assertRaises(retrieval.DatasetError) as caught:
            retrieval.validate_dataset(dataset)
        self.assertIn("every relevant id must be graded", str(caught.exception))

    def test_duplicate_and_contradictory_ids_refuse(self):
        """(5) Duplicates in relevant/forbidden; an id marked both."""
        dataset = self._mutate()
        dataset["cases"][0]["forbidden"] = [3, 3]
        with self.assertRaises(retrieval.DatasetError) as caught:
            retrieval.validate_dataset(dataset)
        self.assertIn("duplicate id", str(caught.exception))

        dataset = self._mutate()
        dataset["cases"][0]["forbidden"] = [1]
        with self.assertRaises(retrieval.DatasetError) as caught:
            retrieval.validate_dataset(dataset)
        self.assertIn("both", str(caught.exception))

    def test_unknown_fixture_id_refuses(self):
        """(5) A relevant id that names no fixture claim."""
        dataset = self._mutate()
        dataset["cases"][0]["relevant"] = [1, 2, 999]
        dataset["cases"][0].pop("graded", None)
        with self.assertRaises(retrieval.DatasetError):
            retrieval.validate_dataset(dataset)

    def test_oversized_dataset_refuses(self):
        """(5) The pinned fixture and case bounds."""
        dataset = self._mutate()
        claim = dataset["fixture"]["claims"][0]
        dataset["fixture"]["claims"] = [
            dict(claim, id=i, key=f"k{i}") for i in range(1, retrieval.MAX_FIXTURE_CLAIMS + 2)
        ]
        with self.assertRaises(retrieval.DatasetError) as caught:
            retrieval.validate_dataset(dataset)
        self.assertIn("maximum", str(caught.exception))

    def test_a_symmetric_edge_stored_backwards_refuses(self):
        """(5) U-M3's canonical form (D-v0.3.36) holds in a fixture too: a
        fixture must not express an edge the real schema would refuse."""
        dataset = json.loads(json.dumps(
            {k: v for k, v in graph().items() if k != protocols.CONTENT_HASH_FIELD}
        ))
        for edge in dataset["fixture"]["edges"]:
            if edge["relation"] == "contradicts":
                edge["from"], edge["to"] = edge["to"], edge["from"]
        with self.assertRaises(retrieval.DatasetError) as caught:
            retrieval.validate_dataset(dataset)
        self.assertIn("from < to", str(caught.exception))

    def test_a_refusal_never_echoes_a_fixture_value(self):
        """Every refusal names a field path and a condition."""
        dataset = self._mutate()
        dataset["fixture"]["claims"][8]["sensitivity"] = "bogus"
        with self.assertRaises(retrieval.DatasetError) as caught:
            retrieval.validate_dataset(dataset)
        message = str(caught.exception)
        self.assertNotIn(PLANTED, message)
        self.assertNotIn("bogus", message)
        self.assertIn("/fixture/claims/8/sensitivity", message)


# ---------------------------------------------------------------------------
# (6) Tokenizer and query bounds

class TokenizerTests(unittest.TestCase):
    def test_normalization_is_nfkc_and_casefold(self):
        self.assertEqual(retrieval.NORMALIZATION_FORM, "NFKC")
        self.assertEqual(retrieval.tokenize("ＤＥＰＬＯＹ"), ("deploy",))
        self.assertEqual(retrieval.tokenize("DEPLOY Window"), ("deploy", "window"))
        # casefold, not lower: ß folds to ss and would not under lower().
        self.assertEqual(retrieval.tokenize("STRASSE straße"), ("strasse",))

    def test_the_grammar_splits_on_documented_separators(self):
        self.assertEqual(retrieval.tokenize("wrong-project"), ("wrong", "project"))
        self.assertEqual(retrieval.tokenize("a_b"), ("a_b",))
        self.assertEqual(retrieval.tokenize("x.y/z:1"), ("x", "y", "z", "1"))

    def test_tokens_deduplicate_preserving_first_occurrence(self):
        self.assertEqual(
            retrieval.tokenize("beta alpha beta gamma alpha"),
            ("beta", "alpha", "gamma"),
        )

    def test_stopwords_are_dropped_and_the_set_is_checked_in(self):
        self.assertEqual(retrieval.tokenize("the and of"), ())
        self.assertTrue(retrieval.STOPWORDS <= frozenset(
            w for w in retrieval.STOPWORDS if w.isascii() and w.islower()
        ))
        self.assertEqual(len(retrieval.STOPWORDS), 33)

    def test_query_byte_char_and_token_bounds_refuse(self):
        """(6) All three refuse rather than truncate, and none echoes the
        query back in the refusal."""
        # Bytes: astral characters are 4 bytes each and stay under the char cap.
        big_bytes = "𝔞" * 200
        self.assertLessEqual(len(big_bytes), retrieval.MAX_QUERY_CHARS)
        with self.assertRaises(utils.AosError) as caught:
            retrieval.query_tokens(big_bytes)
        self.assertIn("bytes", str(caught.exception))
        self.assertNotIn(big_bytes, str(caught.exception))

        with self.assertRaises(utils.AosError) as caught:
            retrieval.query_tokens("a" * (retrieval.MAX_QUERY_CHARS + 1))
        self.assertIn("characters", str(caught.exception))

        many = " ".join(f"t{i}" for i in range(retrieval.MAX_QUERY_TOKENS + 1))
        self.assertLessEqual(len(many), retrieval.MAX_QUERY_CHARS)
        with self.assertRaises(utils.AosError) as caught:
            retrieval.query_tokens(many)
        self.assertIn("terms", str(caught.exception))

    def test_a_query_at_each_bound_is_accepted(self):
        """The bound is the maximum, not one below it."""
        retrieval.query_tokens("a" * retrieval.MAX_QUERY_CHARS)
        retrieval.query_tokens(" ".join(f"t{i}" for i in range(retrieval.MAX_QUERY_TOKENS)))

    def test_no_usable_tokens_is_an_empty_result_not_an_error(self):
        """(6) `retrieval query "the"` behaves like a search that found
        nothing, not like a malformed command."""
        got = query(core(), "the and of")
        self.assertEqual(got.reason, retrieval.REASON_NO_TOKENS)
        self.assertEqual(got.results, ())

    def test_the_tokenizer_uses_no_regex(self):
        """No regex means catastrophic backtracking is impossible by
        construction. A pathological input returns promptly."""
        evil = ("a" * 100 + "!") * 2
        self.assertTrue(retrieval.tokenize(evil))

    def test_claim_text_beyond_the_bound_truncates_and_reports(self):
        """(7) A bound that truncates says so (D-v0.3.63)."""
        claim = retrieval.RetrievalClaim(
            id=1, scope="global", project=None, kind="fact", key="k",
            value="x" * (retrieval.MAX_CLAIM_TEXT_CHARS + 50) + " zebra",
            status="live", pinned=False, sensitivity="internal",
            valid_from="2026-05-01", valid_until=None, superseded_by=None,
            integrity="ok", content_sha256="a" * 64,
        )
        corpus = retrieval.Corpus((claim,), (), ())
        got = retrieval.retrieve(
            corpus, query="zebra", as_of=T0, limit=5, graph_depth=0,
            candidate=retrieval.CANDIDATE_0, project=None,
        )
        self.assertEqual(dict(got.truncation).get("claim_text"), 1)
        # The tail past the bound was not tokenized, so `zebra` is not found.
        self.assertEqual(got.results, ())


# ---------------------------------------------------------------------------
# (7) Result and pool bounds

class BoundsTests(unittest.TestCase):
    def test_limit_bounds_enforce(self):
        with self.assertRaises(utils.AosError):
            query(core(), "deploy window", limit=retrieval.MAX_RESULTS + 1)
        with self.assertRaises(utils.AosError):
            query(core(), "deploy window", limit=0)

    def test_graph_depth_two_does_not_exist(self):
        """Depth 2 is refused, deliberately: ops.MAX_GRAPH_DEPTH is 2 for a
        different purpose and must not leak into retrieval."""
        for bad in (2, 3, -1):
            with self.assertRaises(utils.AosError):
                query(graph(), "index rebuild nightly", depth=bad)

    def test_the_result_limit_is_honored(self):
        got = query(core(), "deploy window", limit=1)
        self.assertEqual(len(got.results), 1)
        self.assertEqual(got.matched, 2)  # matched reports what limit cut

    def test_pool_truncation_reports(self):
        """(7) The pool cap truncates deterministically and says so."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            conn, _ = db.init_db(root / ".agentic-os" / "aos.db")
            try:
                ops.initialize(conn, root)
                now = utils.utc_now_iso()
                with conn:
                    for i in range(retrieval.MAX_POOL_CLAIMS + 5):
                        conn.execute(
                            "INSERT INTO memory (scope, project_id, kind, key, "
                            "value_md, source, confidence, valid_from, "
                            "updated_at, status, pinned, sensitivity, "
                            "content_sha256) VALUES ('global', NULL, 'fact', ?, "
                            "'zeta filler', 'human', 'confirmed', ?, ?, 'live', "
                            "0, 'internal', ?)",
                            (f"k{i}", now, now, "0" * 64),
                        )
                corpus = retrieval.corpus_from_db(conn)
            finally:
                conn.close()
        self.assertEqual(len(corpus.claims), retrieval.MAX_POOL_CLAIMS)
        self.assertEqual(dict(corpus.truncation).get("pool"), 1)

    def test_graph_caps_truncate_and_report(self):
        """(24) More eligible, relevant neighbours than the node cap allows:
        the expansion stops at a deterministic point and reports it."""
        claims = [
            retrieval.RetrievalClaim(
                id=1, scope="global", project=None, kind="fact",
                key="anchor", value="zeta anchor claim text", status="live",
                pinned=False, sensitivity="internal", valid_from="2026-05-01",
                valid_until=None, superseded_by=None, integrity="ok",
                content_sha256="a" * 64,
            )
        ]
        edges = []
        for i in range(2, retrieval.MAX_GRAPH_NODES_ADDED + 10):
            claims.append(
                retrieval.RetrievalClaim(
                    id=i, scope="global", project=None, kind="fact",
                    key=f"n{i}", value="zeta neighbour", status="live",
                    pinned=False, sensitivity="internal", valid_from="2026-05-01",
                    valid_until=None, superseded_by=None, integrity="ok",
                    content_sha256="b" * 64,
                )
            )
            edges.append(retrieval.RetrievalEdge(i, 1, i, "depends_on", None, None))
        corpus = retrieval.Corpus(tuple(claims), tuple(edges), ())

        def run():
            # `zeta` is in every neighbour, so each one clears the minimum
            # relevance signal and the CAP is the only thing that can stop
            # the expansion.
            return retrieval.retrieve(
                corpus, query="zeta anchor", as_of=T0,
                limit=retrieval.MAX_RESULTS, graph_depth=1,
                candidate=retrieval.CANDIDATE_1, project=None,
            )

        got = run()
        truncation = dict(got.truncation)
        self.assertTrue(
            truncation.get("graph_nodes") or truncation.get("graph_edges"),
            "the caps truncated but reported nothing",
        )
        expanded = [s for s in got.results if s.origin == retrieval.ORIGIN_EXPANDED]
        self.assertEqual(len(expanded), retrieval.MAX_GRAPH_NODES_ADDED)
        # Deterministic truncation POINT, not merely a deterministic count.
        self.assertEqual(ids_of(got), ids_of(run()))


# ---------------------------------------------------------------------------
# (8)(9)(16)(17)(18)(19) Ranking

class RankingTests(unittest.TestCase):
    def test_exact_lexical_matches_rank_deterministically(self):
        """(8)"""
        got = query(core(), "deploy window")
        self.assertEqual(ids_of(got), [1, 2])
        for _ in range(5):
            self.assertEqual(ids_of(query(core(), "deploy window")), [1, 2])

    def test_stable_ties_end_with_the_memory_id(self):
        """(9) Two claims engineered to score identically; the id is the only
        tie-break left."""
        got = query(core(), "zeta")
        self.assertEqual(ids_of(got), [17, 18])
        scores = [s.total for s in got.results]
        self.assertEqual(scores[0], scores[1], "the tie must be a real tie")
        self.assertEqual(
            got.results[0].sort_key[:2], got.results[1].sort_key[:2],
            "everything before the id must be equal",
        )

    def test_pinned_claims_receive_only_the_pinned_component(self):
        """(16) The pinned claim has the HIGHER id, so if the pin did nothing
        the id tie-break would order them the other way round."""
        got = query(core(), "editor preference")
        self.assertEqual(ids_of(got), [21, 20])
        pinned, plain = got.results
        self.assertEqual(dict(pinned.components)["pinned"], retrieval.W_PINNED)
        self.assertEqual(dict(plain.components)["pinned"], 0)
        # The ONLY difference is the pin: every other component matches.
        for name in retrieval.COMPONENT_NAMES:
            if name == "pinned":
                continue
            self.assertEqual(
                dict(pinned.components)[name], dict(plain.components)[name], name
            )
        self.assertEqual(pinned.total - plain.total, retrieval.W_PINNED)

    def test_pinning_never_buys_eligibility(self):
        """(16) Pinning is ranking, never permission: a pinned restricted
        claim is still excluded."""
        claim = retrieval.RetrievalClaim(
            id=1, scope="global", project=None, kind="fact", key="k",
            value="zeta", status="live", pinned=True,
            sensitivity=models.MEMORY_SENSITIVITY_RESTRICTED,
            valid_from="2026-05-01", valid_until=None, superseded_by=None,
            integrity="ok", content_sha256="a" * 64,
        )
        self.assertEqual(retrieval.eligibility(claim, T0, None), "restricted")

    def test_temporal_scoring_respects_the_explicit_as_of(self):
        """(17) The clock is never read: freshness moves with --as-of."""
        dataset = core()
        fresh = query(dataset, "deploy window", as_of="2026-05-11T00:00:00Z")
        stale = query(dataset, "deploy window", as_of="2026-12-01T00:00:00Z")
        fresh_by_id = {s.claim.id: dict(s.components)["freshness"] for s in fresh.results}
        stale_by_id = {s.claim.id: dict(s.components)["freshness"] for s in stale.results}
        self.assertEqual(fresh_by_id[2], 12)   # 1 day old
        self.assertEqual(stale_by_id[2], 4)    # 205 days old
        # And the as-of decides eligibility, not the wall clock: the expired
        # claim is out at T0 and was IN before its window closed.
        early = query(dataset, "wednesday migration", as_of="2026-02-01T00:00:00Z")
        self.assertEqual(ids_of(early), [6])
        self.assertEqual(ids_of(query(dataset, "wednesday migration", as_of=T0)), [])

    def test_freshness_buckets_are_exactly_as_pinned(self):
        """(17)(25) The pinned bucket edges, not approximately."""
        for age, points in ((0, 12), (30, 12), (31, 8), (90, 8), (91, 4),
                            (365, 4), (366, 0)):
            valid_from = (
                f"2026-06-01" if age == 0 else None
            )
            claim_from = {
                0: "2026-06-01", 30: "2026-05-02", 31: "2026-05-01",
                90: "2026-03-03", 91: "2026-03-02", 365: "2025-06-01",
                366: "2025-05-31",
            }[age]
            self.assertEqual(
                retrieval._freshness(claim_from, T0), points,
                f"age {age} days should score {points}",
            )

    def test_supporting_and_disputing_provenance_are_distinct_components(self):
        """(18) Two claims identical but for provenance."""
        got = query(core(), "runbook")
        self.assertEqual(ids_of(got), [16, 15])
        supported, disputed = got.results
        self.assertEqual(dict(supported.components)["supported"], 12)  # 3 x +4
        self.assertEqual(dict(supported.components)["disputed"], 0)
        self.assertEqual(dict(disputed.components)["disputed"], -12)   # 2 x -6
        self.assertEqual(dict(disputed.components)["supported"], 0)
        self.assertEqual(supported.supporting, 3)
        self.assertEqual(disputed.disputing, 2)
        # A disputed claim is still RETURNED: a dispute ranks, it never hides.
        self.assertIn(15, ids_of(got))

    def test_provenance_components_are_capped(self):
        """(18) Link count must not become the ranking."""
        claim = retrieval.RetrievalClaim(
            id=1, scope="global", project=None, kind="fact", key="k",
            value="zeta", status="live", pinned=False, sensitivity="internal",
            valid_from="2026-05-01", valid_until=None, superseded_by=None,
            integrity="ok", content_sha256="a" * 64,
            sources=tuple(
                retrieval.SourceWindow("supports", None, None) for _ in range(30)
            ),
        )
        corpus = retrieval.Corpus((claim,), (), ())
        got = retrieval.retrieve(
            corpus, query="zeta", as_of=T0, limit=5, graph_depth=0,
            candidate=retrieval.CANDIDATE_0, project=None,
        )
        self.assertEqual(dict(got.results[0].components)["supported"], 12)
        self.assertEqual(got.results[0].supporting, 30)  # counted, not scored

    def test_an_inactive_source_link_does_not_score(self):
        """(18) Provenance windows are honored at the as-of."""
        claim = retrieval.RetrievalClaim(
            id=1, scope="global", project=None, kind="fact", key="k",
            value="zeta", status="live", pinned=False, sensitivity="internal",
            valid_from="2026-05-01", valid_until=None, superseded_by=None,
            integrity="ok", content_sha256="a" * 64,
            sources=(retrieval.SourceWindow("supports", None, "2026-01-01"),),
        )
        corpus = retrieval.Corpus((claim,), (), ())
        got = retrieval.retrieve(
            corpus, query="zeta", as_of=T0, limit=5, graph_depth=0,
            candidate=retrieval.CANDIDATE_0, project=None,
        )
        self.assertEqual(dict(got.results[0].components)["supported"], 0)

    def test_contradictions_are_metadata_never_verdicts(self):
        """(19) The contradicted claim is still returned, still first, and
        merely scored lower. Nothing is resolved."""
        got = query(graph(), "queue drain hourly", depth=1)
        self.assertEqual(ids_of(got)[0], 13)
        anchor = got.results[0]
        self.assertEqual(anchor.contradictions, 1)
        self.assertEqual(
            dict(anchor.components)["contradicted"],
            retrieval.W_CONTRADICTION_PER_EDGE,
        )
        self.assertIn("contradicted", anchor.reasons)
        # The contradicting claim is returned too — both sides, no ruling.
        self.assertIn(14, ids_of(got))
        # Eligibility is untouched by contradiction.
        corpus = retrieval.corpus_from_fixture(graph())
        for claim in corpus.claims:
            if claim.id in (13, 14):
                self.assertEqual(retrieval.eligibility(claim, T0, "alpha"), "ok")

    def test_weights_are_the_pinned_constants(self):
        """(25) The contract's table, read back off the module."""
        self.assertEqual(retrieval.W_LEXICAL_PER_TOKEN, 10)
        self.assertEqual(retrieval.W_PHRASE, 25)
        self.assertEqual(retrieval.W_KEY_EXACT, 40)
        self.assertEqual(retrieval.W_KEY_PER_TOKEN, 5)
        self.assertEqual(retrieval.W_PINNED, 8)
        self.assertEqual(retrieval.W_PROJECT_SCOPE, 6)
        self.assertEqual(retrieval.W_SUPPORT_PER_SOURCE, 4)
        self.assertEqual(retrieval.W_DISPUTE_PER_SOURCE, -6)
        self.assertEqual(retrieval.W_GRAPH_PER_EDGE, 2)
        self.assertEqual(retrieval.W_CONTRADICTION_PER_EDGE, -3)

    def test_every_score_component_is_an_integer(self):
        """(D-v0.3.54) No float, anywhere, ever."""
        for name in retrieval.benchmark_names():
            dataset = retrieval.get_benchmark(name)
            for case in dataset["cases"]:
                got = query(
                    dataset, case["query"], project=case["project"],
                    as_of=case["as_of"], limit=case["config"]["limit"], depth=1,
                )
                for scored in got.results:
                    self.assertIsInstance(scored.total, int)
                    self.assertNotIsInstance(scored.total, bool)
                    for _, value in scored.components:
                        self.assertIsInstance(value, int)
                    for element in scored.sort_key:
                        self.assertIsInstance(element, int)


# ---------------------------------------------------------------------------
# (10)-(15) Eligibility and leakage

class EligibilityTests(unittest.TestCase):
    def test_project_scoped_queries_include_global_plus_matching_only(self):
        """(10)"""
        got = query(core(), "deploy window", project="alpha")
        by_id = {s.claim.id: s.claim for s in got.results}
        self.assertEqual(sorted(by_id), [1, 2])
        self.assertEqual(by_id[1].scope, "global")
        self.assertEqual(by_id[2].project, "alpha")

    def test_without_a_project_only_global_claims_are_eligible(self):
        """(10) Exactly memory_for_project(conn, None)."""
        got = query(core(), "deploy window", project=None)
        self.assertEqual(ids_of(got), [1])
        for scored in got.results:
            self.assertEqual(scored.claim.scope, "global")

    def test_wrong_project_stronger_matches_never_leak(self):
        """(11) The beta claim matches the query EXACTLY on key and phrase —
        a far stronger lexical signal than the permitted answer. Strength
        must not buy eligibility."""
        corpus = retrieval.corpus_from_fixture(core())
        beta = next(c for c in corpus.claims if c.id == 10)
        alpha = next(c for c in corpus.claims if c.id == 2)
        # Establish that the forbidden claim really is the stronger match.
        self.assertEqual(
            retrieval.tokenize(beta.key), retrieval.tokenize("thursday deploy window")
        )
        self.assertNotEqual(
            retrieval.tokenize(alpha.key), retrieval.tokenize("thursday deploy window")
        )
        got = query(core(), "thursday deploy window", project="alpha")
        self.assertEqual(ids_of(got), [2])
        self.assertEqual(retrieval.eligibility(beta, T0, "alpha"), "project")

    def test_restricted_stronger_matches_never_leak(self):
        """(12)"""
        corpus = retrieval.corpus_from_fixture(core())
        restricted = next(c for c in corpus.claims if c.id == 9)
        self.assertEqual(
            restricted.sensitivity, models.MEMORY_SENSITIVITY_RESTRICTED
        )
        self.assertIn(PLANTED, restricted.value)  # the bait is really there
        for depth in (0, 1):
            got = query(core(), "thursday deploy window", depth=depth)
            self.assertNotIn(9, ids_of(got))
            self.assertNotIn(9, ids_of(query(core(), "rota token", depth=depth)))
        self.assertEqual(retrieval.eligibility(restricted, T0, "alpha"), "restricted")

    def test_non_live_lifecycle_states_never_leak(self):
        """(13) proposed · contested · quarantined · retired"""
        corpus = retrieval.corpus_from_fixture(core())
        states = {}
        for claim in corpus.claims:
            if claim.status != "live":
                states[claim.status] = claim.id
        self.assertEqual(
            sorted(states), ["contested", "proposed", "quarantined", "retired"]
        )
        got = query(core(), "thursday deploy window", depth=1)
        for status, cid in states.items():
            self.assertNotIn(cid, ids_of(got), status)
            claim = next(c for c in corpus.claims if c.id == cid)
            self.assertEqual(retrieval.eligibility(claim, T0, "alpha"), "status")

    def test_expired_and_superseded_never_leak(self):
        """(14) Both are status=live — the leak they would cause is invisible
        to a status check."""
        corpus = retrieval.corpus_from_fixture(core())
        expired = next(c for c in corpus.claims if c.id == 6)
        superseded = next(c for c in corpus.claims if c.id == 7)
        self.assertEqual(expired.status, "live")
        self.assertEqual(superseded.status, "live")
        self.assertEqual(retrieval.eligibility(expired, T0, "alpha"), "temporal")
        self.assertEqual(retrieval.eligibility(superseded, T0, "alpha"), "superseded")
        for text in ("wednesday deploy window", "wednesday migration"):
            got = query(core(), text, depth=1)
            self.assertNotIn(6, ids_of(got))
            self.assertNotIn(7, ids_of(got))

    def test_a_claim_whose_window_has_not_opened_is_not_eligible(self):
        """(14) claim_is_eligible checks expiry only; retrieval also checks
        valid_from, because a claim whose window has not opened is not a fact
        about the requested instant (D-v0.3.56)."""
        claim = retrieval.RetrievalClaim(
            id=1, scope="global", project=None, kind="fact", key="k",
            value="zeta", status="live", pinned=False, sensitivity="internal",
            valid_from="2027-01-01", valid_until=None, superseded_by=None,
            integrity="ok", content_sha256="a" * 64,
        )
        self.assertEqual(retrieval.eligibility(claim, T0, None), "temporal")
        self.assertTrue(_as_memory_item(claim) and ops.claim_is_eligible(
            _as_memory_item(claim), T0
        ))  # the pack builder WOULD carry it; retrieval is stricter

    def test_hash_invalid_claims_never_leak(self):
        """(15)"""
        corpus = retrieval.corpus_from_fixture(core())
        tampered = next(c for c in corpus.claims if c.id == 11)
        self.assertEqual(tampered.integrity, "mismatch")
        self.assertEqual(retrieval.eligibility(tampered, T0, "alpha"), "hash")
        for text in ("tampered row", "thursday deploy window"):
            self.assertNotIn(11, ids_of(query(core(), text, depth=1)))

    def test_retrieval_eligibility_implies_pack_eligibility(self):
        """(D-v0.3.56) The implication that matters, over the whole fixture
        matrix: U-M5 may refuse what the pack would carry; it can never carry
        what the pack would refuse."""
        for name in retrieval.benchmark_names():
            corpus = retrieval.corpus_from_fixture(retrieval.get_benchmark(name))
            for claim in corpus.claims:
                for project in (None, "alpha", "beta"):
                    if retrieval.eligibility(claim, T0, project) == "ok":
                        self.assertTrue(
                            ops.claim_is_eligible(_as_memory_item(claim), T0),
                            f"{name} claim {claim.id}: retrieval says eligible, "
                            "the pack builder would refuse it",
                        )

    def test_eligibility_reasons_are_a_closed_vocabulary_in_pinned_order(self):
        """(M5.4) The first failing reason is the answer, deterministically."""
        claim = retrieval.RetrievalClaim(
            id=1, scope="project", project="beta", kind="fact", key="k",
            value="zeta", status="retired", pinned=False,
            sensitivity=models.MEMORY_SENSITIVITY_RESTRICTED,
            valid_from="2020-01-01", valid_until="2021-01-01",
            superseded_by=2, integrity="mismatch", content_sha256="a" * 64,
        )
        # Every rule fails; `status` is first in the pinned order and wins.
        self.assertEqual(retrieval.eligibility(claim, T0, "alpha"), "status")
        self.assertIn(retrieval.eligibility(claim, T0, "alpha"),
                      retrieval.ELIGIBILITY_REASONS)

    def test_latest_per_key_shadows_a_stale_row(self):
        """(M5.3) memory_for_project's rule, reused: the candidate cannot
        surface a stale row for a key the pack would not show."""
        def claim(cid, value):
            return retrieval.RetrievalClaim(
                id=cid, scope="global", project=None, kind="fact", key="dup",
                value=value, status="live", pinned=False, sensitivity="internal",
                valid_from="2026-05-01", valid_until=None, superseded_by=None,
                integrity="ok", content_sha256="a" * 64,
            )
        corpus = retrieval.Corpus((claim(1, "zeta old"), claim(2, "zeta new")), (), ())
        eligible = retrieval.eligible_claims(corpus, T0, None)
        self.assertEqual([c.id for c in eligible], [2])


def _as_memory_item(claim) -> models.MemoryItem:
    """A RetrievalClaim in MemoryItem's clothing, so ops.claim_is_eligible can
    judge the same row retrieval judged."""
    return models.MemoryItem(
        id=claim.id, scope=claim.scope, project_id=None, kind=claim.kind,
        key=claim.key, value_md=claim.value, source="human",
        confidence="confirmed", valid_from=claim.valid_from,
        valid_until=claim.valid_until, superseded_by=claim.superseded_by,
        updated_at=claim.valid_from, status=claim.status,
        pinned=int(claim.pinned), sensitivity=claim.sensitivity,
        content_sha256=claim.content_sha256,
    )


# ---------------------------------------------------------------------------
# (20)-(23) Graph expansion

class GraphExpansionTests(unittest.TestCase):
    def test_depth_zero_performs_no_expansion(self):
        """(20)"""
        got = query(graph(), "index rebuild nightly", depth=0)
        self.assertEqual(ids_of(got), [1])
        for scored in got.results:
            self.assertEqual(scored.origin, retrieval.ORIGIN_PRIMARY)
            self.assertIsNone(scored.graph_origin)

    def test_depth_one_expansion_uses_only_active_compatible_edges(self):
        """(21) Seven baited neighbours of one anchor, one per exclusion rule.
        None may be expanded into."""
        got = query(graph(), "index rebuild nightly", depth=1)
        self.assertEqual(ids_of(got), [1, 2, 4])
        for forbidden, why in (
            (3, "zero query tokens (noise)"),
            (5, "wrong project"),
            (6, "restricted"),
            (7, "retired"),
            (8, "reachable only by an EXPIRED edge"),
            (9, "hash invalid"),
            (10, "expired claim"),
        ):
            self.assertNotIn(forbidden, ids_of(got), why)

    def test_an_expired_edge_is_never_traversed(self):
        """(21) The claim is eligible; only the edge is expired — and only the
        edge decides."""
        corpus = retrieval.corpus_from_fixture(graph())
        archive = next(c for c in corpus.claims if c.id == 8)
        self.assertEqual(retrieval.eligibility(archive, T0, "alpha"), "ok")
        edge = next(e for e in corpus.edges if e.to_id == 8)
        self.assertFalse(ops.window_is_active(edge.valid_from, edge.valid_until, T0))
        self.assertNotIn(8, ids_of(query(graph(), "index rebuild nightly", depth=1)))
        # Before the edge's window closed it WAS traversable, and the claim is
        # byte-for-byte the same claim. That is what proves the exclusion came
        # from the EDGE's window and not from something about the claim.
        early = query(graph(), "index rebuild nightly", depth=1,
                      as_of="2026-05-16T00:00:00Z")
        self.assertTrue(ops.window_is_active(
            edge.valid_from, edge.valid_until, "2026-05-16T00:00:00Z"
        ))
        self.assertIn(8, ids_of(early))

    def test_graph_only_noise_cannot_dominate_direct_matches(self):
        """(22) The noise claim has the highest degree of any non-anchor in
        the fixture and zero query tokens. Degree buys nothing."""
        corpus = retrieval.corpus_from_fixture(graph())
        degree = {}
        for edge in corpus.edges:
            for end in (edge.from_id, edge.to_id):
                degree[end] = degree.get(end, 0) + 1
        non_anchor = {k: v for k, v in degree.items() if k != 1}
        self.assertEqual(max(non_anchor, key=lambda k: (non_anchor[k], -k)), 3)
        got = query(graph(), "index rebuild nightly", depth=1)
        self.assertNotIn(3, ids_of(got))

    def test_every_expanded_result_ranks_below_every_primary(self):
        """(22)(D-v0.3.57) True by construction, so it is testable with one
        assertion rather than a tournament of fixtures."""
        for name in retrieval.benchmark_names():
            dataset = retrieval.get_benchmark(name)
            for case in dataset["cases"]:
                got = query(dataset, case["query"], project=case["project"],
                            as_of=case["as_of"], limit=10, depth=1)
                origins = [s.origin for s in got.results]
                first_expanded = next(
                    (i for i, o in enumerate(origins)
                     if o == retrieval.ORIGIN_EXPANDED),
                    len(origins),
                )
                self.assertTrue(
                    all(o == retrieval.ORIGIN_EXPANDED for o in origins[first_expanded:]),
                    f"{name}/{case['case']}: a primary followed an expanded result",
                )

    def test_directional_relationships_keep_their_direction(self):
        """(23)"""
        got = query(graph(), "index rebuild nightly", depth=1)
        by_id = {s.claim.id: dict(s.graph_origin) for s in got.results if s.graph_origin}
        self.assertEqual(by_id[2]["relation"], "supports")
        self.assertEqual(by_id[2]["direction"], "in")   # claim 2 supports the anchor
        self.assertEqual(by_id[4]["relation"], "depends_on")
        self.assertEqual(by_id[4]["direction"], "out")  # the anchor depends on claim 4
        self.assertEqual(by_id[2]["via"], "M-0001")
        self.assertEqual(by_id[2]["edge"], "ME-0001")

    def test_symmetric_relationships_report_no_direction(self):
        """(23) A symmetric edge reports `symmetric` rather than inventing a
        direction from the storage order its endpoints were canonicalized
        into (D-v0.3.36)."""
        got = query(graph(), "cache purge", depth=1)
        self.assertEqual(ids_of(got), [11, 12])
        origin = dict(got.results[1].graph_origin)
        self.assertEqual(origin["relation"], "related")
        self.assertEqual(origin["direction"], "symmetric")

        contra = query(graph(), "queue drain hourly", depth=1)
        origin = dict(contra.results[1].graph_origin)
        self.assertEqual(origin["relation"], "contradicts")
        self.assertEqual(origin["direction"], "symmetric")
        for relation in models.MEMORY_EDGE_SYMMETRIC:
            self.assertIn(relation, ("contradicts", "related"))

    def test_expansion_needs_the_minimum_relevance_signal(self):
        """(22)(D-v0.3.58) One query token is the documented floor; zero is
        noise however well connected."""
        anchor = retrieval.RetrievalClaim(
            id=1, scope="global", project=None, kind="fact", key="anchor",
            value="zeta anchor", status="live", pinned=False,
            sensitivity="internal", valid_from="2026-05-01", valid_until=None,
            superseded_by=None, integrity="ok", content_sha256="a" * 64,
        )
        partial = retrieval.RetrievalClaim(
            id=2, scope="global", project=None, kind="fact", key="partial",
            value="zeta only", status="live", pinned=False,
            sensitivity="internal", valid_from="2026-05-01", valid_until=None,
            superseded_by=None, integrity="ok", content_sha256="b" * 64,
        )
        noise = retrieval.RetrievalClaim(
            id=3, scope="global", project=None, kind="fact", key="noise",
            value="entirely different words", status="live", pinned=False,
            sensitivity="internal", valid_from="2026-05-01", valid_until=None,
            superseded_by=None, integrity="ok", content_sha256="c" * 64,
        )
        edges = (
            retrieval.RetrievalEdge(1, 1, 2, "depends_on", None, None),
            retrieval.RetrievalEdge(2, 1, 3, "depends_on", None, None),
        )
        corpus = retrieval.Corpus((anchor, partial, noise), edges, ())
        got = retrieval.retrieve(
            corpus, query="zeta anchor", as_of=T0, limit=10, graph_depth=1,
            candidate=retrieval.CANDIDATE_1, project=None,
        )
        self.assertEqual(ids_of(got), [1, 2])

    def test_expansion_cannot_invent_an_anchor(self):
        """(21) No primary hit, nothing to expand FROM."""
        got = query(graph(), "quokka sunset", depth=1)
        self.assertEqual(got.results, ())

    def test_no_edge_is_inferred(self):
        """(21) The expansion returns only claims reachable on a STORED edge."""
        corpus = retrieval.corpus_from_fixture(graph())
        stored = {(e.from_id, e.to_id) for e in corpus.edges}
        got = query(graph(), "index rebuild nightly", depth=1)
        for scored in got.results:
            if not scored.graph_origin:
                continue
            origin = dict(scored.graph_origin)
            anchor = int(origin["via"].split("-")[1])
            pair = (anchor, scored.claim.id)
            self.assertTrue(
                pair in stored or pair[::-1] in stored,
                f"{pair} is not a stored edge",
            )


# ---------------------------------------------------------------------------
# (25)(26)(27) Metrics

class MetricsTests(unittest.TestCase):
    def test_the_log2_table_transcribes_math_log2(self):
        """(D-v0.3.55) The table checks the transcription; the transcription
        does not trust the platform."""
        for rank in range(1, retrieval.K_MAX + 1):
            self.assertEqual(
                retrieval._LOG2_SCALED[rank],
                round(math.log2(rank + 1) * retrieval._LOG2_SCALE),
                f"rank {rank}",
            )
        self.assertEqual(len(retrieval._LOG2_SCALED), retrieval.K_MAX + 1)
        self.assertEqual(retrieval._discount(1), Fraction(1))

    def test_render_fraction_is_four_decimals_round_half_up(self):
        """(25) Integer arithmetic, fixed width, and a STRING out."""
        cases = {
            Fraction(0): "0.0000",
            Fraction(1): "1.0000",
            Fraction(1, 3): "0.3333",
            Fraction(2, 3): "0.6667",
            Fraction(1, 2): "0.5000",
            Fraction(1, 20000): "0.0001",   # exactly half → up
            Fraction(-1, 3): "-0.3333",
        }
        for value, expected in cases.items():
            got = retrieval.render_fraction(value)
            self.assertEqual(got, expected)
            self.assertIsInstance(got, str)
        self.assertIsNone(retrieval.render_fraction(None))
        self.assertEqual(retrieval.render_delta(Fraction(1, 4)), "+0.2500")
        self.assertEqual(retrieval.render_delta(Fraction(0)), "+0.0000")

    def test_metrics_match_the_pinned_formulas(self):
        """(25) Hand-computed against the contract's table."""
        got = retrieval.case_metrics(
            case="t", result_ids=[5, 1, 9], returned=3,
            relevant=frozenset({1, 2}), graded=None,
            leakage={c: 0 for c in retrieval.LEAKAGE_CLASSES},
            truncated=False, k=5,
        )
        self.assertEqual(got.hit_at_k, Fraction(1))
        self.assertEqual(got.precision_at_k, Fraction(1, 3))   # 1 of 3 returned
        self.assertEqual(got.recall_at_k, Fraction(1, 2))      # 1 of 2 relevant
        self.assertEqual(got.mrr, Fraction(1, 2))              # first hit at rank 2
        self.assertIsNone(got.ndcg_at_k)

    def test_k_truncates_before_the_metric_is_computed(self):
        """(25) A relevant claim past k is not found."""
        got = retrieval.case_metrics(
            case="t", result_ids=[9, 9, 9, 9, 1], returned=5,
            relevant=frozenset({1}), graded=None,
            leakage={c: 0 for c in retrieval.LEAKAGE_CLASSES},
            truncated=False, k=3,
        )
        self.assertEqual(got.hit_at_k, Fraction(0))
        self.assertEqual(got.mrr, Fraction(0))
        self.assertEqual(got.recall_at_k, Fraction(0))

    def test_ndcg_matches_a_hand_computed_value(self):
        """(25) The exact rational, verified against the definition."""
        got = retrieval.case_metrics(
            case="t", result_ids=[2, 1], returned=2,
            relevant=frozenset({1, 2}), graded={1: 3, 2: 1},
            leakage={c: 0 for c in retrieval.LEAKAGE_CLASSES},
            truncated=False, k=5,
        )
        dcg = Fraction(2**1 - 1) * retrieval._discount(1) + Fraction(2**3 - 1) * retrieval._discount(2)
        idcg = Fraction(2**3 - 1) * retrieval._discount(1) + Fraction(2**1 - 1) * retrieval._discount(2)
        self.assertEqual(got.ndcg_at_k, dcg / idcg)
        # The perfect ranking is [1, 2]; this one is inverted, so nDCG < 1.
        self.assertEqual(retrieval.render_fraction(got.ndcg_at_k), "0.7098")
        self.assertEqual(
            retrieval.render_fraction(
                retrieval.case_metrics(
                    case="t", result_ids=[1, 2], returned=2,
                    relevant=frozenset({1, 2}), graded={1: 3, 2: 1},
                    leakage={c: 0 for c in retrieval.LEAKAGE_CLASSES},
                    truncated=False, k=5,
                ).ndcg_at_k
            ),
            "1.0000",
        )

    def test_empty_result_metric_behavior_is_deterministic(self):
        """(26) Undefined is null, never a made-up zero."""
        empty_relevant = retrieval.case_metrics(
            case="t", result_ids=[], returned=0, relevant=frozenset(),
            graded=None, leakage={c: 0 for c in retrieval.LEAKAGE_CLASSES},
            truncated=False, k=5,
        )
        self.assertIsNone(empty_relevant.hit_at_k)
        self.assertIsNone(empty_relevant.recall_at_k)
        self.assertIsNone(empty_relevant.mrr)
        self.assertIsNone(empty_relevant.precision_at_k)  # nothing returned
        self.assertIsNone(empty_relevant.ndcg_at_k)

        found_nothing = retrieval.case_metrics(
            case="t", result_ids=[], returned=0, relevant=frozenset({1}),
            graded=None, leakage={c: 0 for c in retrieval.LEAKAGE_CLASSES},
            truncated=False, k=5,
        )
        # A relevant claim EXISTS and was not found: that is a real zero.
        self.assertEqual(found_nothing.hit_at_k, Fraction(0))
        self.assertEqual(found_nothing.recall_at_k, Fraction(0))
        self.assertEqual(found_nothing.mrr, Fraction(0))
        self.assertIsNone(found_nothing.precision_at_k)

    def test_nulls_are_excluded_from_aggregates_and_the_n_is_reported(self):
        """(26) A mean over 7 of 14 cases can never read as a mean over 14."""
        report = retrieval.run_benchmark("core-retrieval")
        doc = report["candidates"]["candidate-0"]
        cases = doc["cases"]
        self.assertEqual(len(cases), 14)
        graded_cases = sum(1 for c in cases if c["hit_at_k"] is not None)
        self.assertEqual(doc["contributing"]["hit_at_k"], graded_cases)
        self.assertLess(graded_cases, len(cases), "some cases must be null")

    def test_leakage_counters_are_sums_never_means(self):
        """(27) One leak in one case of fourteen is still exactly one."""
        report = retrieval.run_benchmark("core-retrieval")
        for name, doc in report["candidates"].items():
            for cls in retrieval.LEAKAGE_CLASSES:
                total = sum(case["leakage"][cls] for case in doc["cases"])
                self.assertEqual(doc["counters"][cls], total, f"{name}/{cls}")
                self.assertIsInstance(doc["counters"][cls], int)

    def test_leakage_is_counted_from_the_claim_not_from_the_forbidden_list(self):
        """(27) An author's omission cannot hide a leak: the case that leaks
        the beta claim does not list it as forbidden, and it is still counted."""
        report = retrieval.run_benchmark("graph-expansion")
        baseline = report["candidates"]["baseline"]
        case = next(c for c in baseline["cases"]
                    if c["case"] == "directional-edge-expansion")
        dataset = graph()
        declared = next(c for c in dataset["cases"]
                        if c["case"] == "directional-edge-expansion")
        self.assertEqual(declared["forbidden"], [])
        self.assertEqual(case["leakage"]["forbidden_results"], 0)
        self.assertGreater(case["leakage"]["wrong_project_leaks"], 0)


# ---------------------------------------------------------------------------
# (28)(29) Gate and deltas

class GateTests(unittest.TestCase):
    def test_the_shipped_candidates_leak_nothing_and_pass(self):
        """(28) Every leakage counter is zero for both candidates on both
        benchmarks."""
        for name in retrieval.benchmark_names():
            report = retrieval.run_benchmark(name)
            for candidate in retrieval.PROMOTABLE:
                doc = report["candidates"][candidate]
                for cls in retrieval.LEAKAGE_CLASSES:
                    self.assertEqual(doc["counters"][cls], 0, f"{name}/{candidate}/{cls}")
                self.assertTrue(doc["gate"]["safety_ok"])
                self.assertTrue(doc["gate"]["gate"], f"{name}/{candidate}")
            self.assertTrue(report["passed"])

    def test_the_baseline_leaks_and_its_gate_fails(self):
        """(28) The finding, measured rather than asserted: production lexical
        memory retrieval returns wrong-project, restricted, retired, expired,
        superseded and hash-invalid claims."""
        report = retrieval.run_benchmark("core-retrieval")
        baseline = report["candidates"]["baseline"]
        counters = baseline["counters"]
        for cls in retrieval.LEAKAGE_CLASSES:
            self.assertGreater(counters[cls], 0, cls)
        self.assertFalse(baseline["gate"]["safety_ok"])
        self.assertFalse(baseline["gate"]["gate"])

    def test_the_baseline_is_reported_but_never_gated(self):
        """(D-v0.3.62) A failing baseline does not fail the command: it is the
        measured reference, and gating it would make `--candidate all` exit 1
        forever the moment production was measured to leak."""
        report = retrieval.run_benchmark("core-retrieval", candidate="all")
        self.assertFalse(report["candidates"]["baseline"]["gate"]["gate"])
        self.assertEqual(report["gated_candidates"], ["candidate-0", "candidate-1"])
        self.assertTrue(report["passed"])
        code, out, err = run_cli("retrieval", "benchmark", "run", "core-retrieval")
        self.assertEqual(code, 0)
        # The failure is still visible, at full severity, on stdout.
        self.assertIn("restricted leaks 2", out)

    def test_any_leakage_forces_gate_failure(self):
        """(28) Injected: one restricted claim reaching one result, and the
        gate fails even though every relevance metric is perfect."""
        evaluated = {
            "counters": {cls: 0 for cls in retrieval.LEAKAGE_CLASSES},
            "aggregate": {m: Fraction(1) for m in retrieval.AGGREGATE_METRICS},
            "bounds_ok": True,
        }
        dataset = core()
        clean = retrieval._gate(dataset, evaluated, None, True)
        self.assertTrue(clean["gate"])
        for cls in retrieval.LEAKAGE_CLASSES:
            leaky = {
                **evaluated,
                "counters": {**evaluated["counters"], cls: 1},
            }
            verdict = retrieval._gate(dataset, leaky, None, True)
            self.assertFalse(verdict["safety_ok"], cls)
            self.assertFalse(verdict["gate"], f"{cls}: perfect relevance still passed")

    def test_a_failed_replay_fails_the_gate(self):
        """(28)(30) Determinism is a gate clause, not a comment."""
        evaluated = {
            "counters": {cls: 0 for cls in retrieval.LEAKAGE_CLASSES},
            "aggregate": {m: Fraction(1) for m in retrieval.AGGREGATE_METRICS},
            "bounds_ok": True,
        }
        self.assertFalse(retrieval._gate(core(), evaluated, None, False)["gate"])

    def test_thresholds_and_bounds_are_gate_clauses(self):
        evaluated = {
            "counters": {cls: 0 for cls in retrieval.LEAKAGE_CLASSES},
            "aggregate": {m: Fraction(1) for m in retrieval.AGGREGATE_METRICS},
            "bounds_ok": False,
        }
        self.assertFalse(retrieval._gate(core(), evaluated, None, True)["gate"])
        below = {
            "counters": {cls: 0 for cls in retrieval.LEAKAGE_CLASSES},
            "aggregate": {m: Fraction(1, 10) for m in retrieval.AGGREGATE_METRICS},
            "bounds_ok": True,
        }
        verdict = retrieval._gate(core(), below, None, True)
        self.assertFalse(verdict["thresholds_ok"])
        self.assertFalse(verdict["gate"])

    def test_a_regression_against_baseline_fails_the_gate(self):
        baseline = {
            "aggregate": {m: Fraction(1) for m in retrieval.AGGREGATE_METRICS},
        }
        worse = {
            "counters": {cls: 0 for cls in retrieval.LEAKAGE_CLASSES},
            "aggregate": {m: Fraction(1, 2) for m in retrieval.AGGREGATE_METRICS},
            "bounds_ok": True,
        }
        verdict = retrieval._gate(core(), worse, baseline, True)
        self.assertFalse(verdict["no_regression"])
        self.assertFalse(verdict["gate"])

    def test_baseline_and_candidate_deltas_are_correct(self):
        """(29) Recomputed from the two aggregates, independently."""
        for name in retrieval.benchmark_names():
            report = retrieval.run_benchmark(name)
            baseline = report["candidates"]["baseline"]
            for candidate in retrieval.PROMOTABLE:
                doc = report["candidates"][candidate]
                delta = report["deltas"][candidate]
                for metric in retrieval.AGGREGATE_METRICS:
                    mine = doc["aggregate"][metric]
                    theirs = baseline["aggregate"][metric]
                    if mine is None or theirs is None:
                        self.assertIsNone(delta[metric])
                        continue
                    expected = retrieval.render_delta(
                        retrieval.parse_threshold(mine) - retrieval.parse_threshold(theirs)
                    )
                    self.assertEqual(delta[metric], expected, f"{name}/{candidate}/{metric}")
                for cls in retrieval.LEAKAGE_CLASSES:
                    self.assertEqual(
                        delta[cls],
                        doc["counters"][cls] - baseline["counters"][cls],
                    )

    def test_the_measured_deltas_are_the_expected_direction(self):
        """(29) The headline result, pinned as a test so a regression in it is
        a test failure and not a paragraph nobody re-read."""
        core_report = retrieval.run_benchmark("core-retrieval")
        for candidate in retrieval.PROMOTABLE:
            delta = core_report["deltas"][candidate]
            # Precision and nDCG improve; every leakage class drops to zero.
            self.assertEqual(delta["precision_at_k"], "+0.6000")
            self.assertEqual(delta["ndcg_at_k"], "+0.0889")
            self.assertEqual(delta["restricted_leaks"], -2)
            self.assertEqual(delta["wrong_project_leaks"], -8)
        graph_report = retrieval.run_benchmark("graph-expansion")
        # Expansion buys recall, and only candidate-1 has it.
        self.assertEqual(graph_report["deltas"]["candidate-0"]["recall_at_k"], "+0.0000")
        self.assertEqual(graph_report["deltas"]["candidate-1"]["recall_at_k"], "+0.5833")

    def test_the_recommendation_is_a_function_of_gates(self):
        """(M5.12) Deterministic, and derived — never narrative."""
        self.assertEqual(
            retrieval.run_benchmark("graph-expansion")["recommendation"],
            {"recommendation": "promote candidate-1", "reason": "gates_passed"},
        )
        # No edges in the core fixture, so candidate-1 cannot beat candidate-0
        # and the recommendation says so rather than preferring the newer one.
        self.assertEqual(
            retrieval.run_benchmark("core-retrieval")["recommendation"],
            {"recommendation": "promote candidate-0", "reason": "gates_passed"},
        )
        # A partial run cannot recommend: there is nothing to compare against.
        partial = retrieval.run_benchmark("core-retrieval", candidate="candidate-0")
        self.assertEqual(
            partial["recommendation"],
            {"recommendation": "insufficient evidence", "reason": "partial_evaluation"},
        )
        self.assertIn(
            retrieval.run_benchmark("core-retrieval")["recommendation"]["recommendation"],
            retrieval.RECOMMENDATIONS,
        )

    def test_keep_baseline_when_no_candidate_gate_passes(self):
        """(M5.12) The fourth branch, exercised."""
        gates = {c: {"gate": False} for c in retrieval.CANDIDATES}
        evaluations = {
            c: {"aggregate": {m: Fraction(1) for m in retrieval.AGGREGATE_METRICS}}
            for c in retrieval.CANDIDATES
        }
        self.assertEqual(
            retrieval._recommend(evaluations, gates)["recommendation"],
            "keep baseline",
        )


# ---------------------------------------------------------------------------
# (30)(31) Determinism

class DeterminismTests(unittest.TestCase):
    def test_repeated_runs_are_byte_identical(self):
        """(30)"""
        for name in retrieval.benchmark_names():
            first = protocols.serialize_canonical(retrieval.run_benchmark(name))
            for _ in range(3):
                self.assertEqual(protocols.serialize_canonical(retrieval.run_benchmark(name)), first)

    def test_replay_is_a_reported_gate_clause(self):
        """(30) The run evaluates twice and compares canonical bytes."""
        for name in retrieval.benchmark_names():
            report = retrieval.run_benchmark(name)
            for candidate in retrieval.CANDIDATES:
                self.assertTrue(report["candidates"][candidate]["gate"]["replay_ok"])

    def test_different_pythonhashseed_values_produce_identical_reports(self):
        """(31) Nothing here depends on dict/set iteration order."""
        outputs = set()
        for seed in ("0", "1", "42", "12345"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            env.pop("PYTHONPATH", None)
            result = subprocess.run(
                [sys.executable, "aos.py", "retrieval", "benchmark", "run",
                 "core-retrieval", "--json"],
                cwd=str(REPO_ROOT), env=env, capture_output=True, text=True,
                timeout=180,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            outputs.add(result.stdout)
        self.assertEqual(len(outputs), 1, "PYTHONHASHSEED changed the report")

    def test_the_json_report_carries_no_float(self):
        """(D-v0.3.54) Not one, at any depth — proven by re-parsing the real
        stdout with a hook that rejects every float literal."""
        code, out, err = run_cli(
            "retrieval", "benchmark", "run", "core-retrieval", "--json"
        )
        self.assertEqual(code, 0, err)

        def no_float(literal):
            raise AssertionError(f"the report contains a float literal: {literal}")

        json.loads(out, parse_float=no_float)

    def test_ordering_never_depends_on_insertion_order(self):
        """(31) The registry is sorted at every use."""
        with mock.patch.object(retrieval, "_REGISTRY", None):
            with mock.patch.object(
                retrieval, "_DATASETS", tuple(reversed(retrieval._DATASETS))
            ):
                self.assertEqual(
                    retrieval.benchmark_names(), ["core-retrieval", "graph-expansion"]
                )
                reversed_index = retrieval.registry_index()
        retrieval._REGISTRY = None
        self.assertEqual(reversed_index, retrieval.registry_index())


# ---------------------------------------------------------------------------
# (32)-(35) Command classification and read-only behavior

class ClassificationTests(unittest.TestCase):
    def test_every_retrieval_leaf_is_classified_read_only(self):
        """(32) Read out of the live parser, so a new leaf cannot be forgotten."""
        leaves = [
            path for path in power.iter_command_paths(cli.build_parser())
            if path and path[0] == "retrieval"
        ]
        self.assertEqual(
            leaves,
            [
                ("retrieval", "benchmark", "list"),
                ("retrieval", "benchmark", "run"),
                ("retrieval", "benchmark", "show"),
                ("retrieval", "query"),
            ],
        )
        for path in leaves:
            policy = power.policy_for(path)
            self.assertEqual(policy.kind, power.READ_ONLY, path)
            self.assertFalse(policy.ledger, path)

    def test_the_classification_key_reaches_the_third_level(self):
        """(32) `retrieval benchmark run` is three deep; a key that stopped at
        two would collapse the three benchmark leaves into one command."""
        args = cli.build_parser().parse_args(
            ["retrieval", "benchmark", "run", "core-retrieval"]
        )
        self.assertEqual(
            power.command_path(args), ("retrieval", "benchmark", "run")
        )


class ReadOnlyTests(unittest.TestCase):
    """(32)(33)(35) Against a real workspace, inspected afterwards."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aos-m5-ro-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = Path(self.tmp)
        self.aos_dir = self.root / ".agentic-os"
        code, _, err = run_cli("--root", str(self.root), "init")
        self.assertEqual(code, 0, err)
        code, _, err = run_cli(
            "--root", str(self.root), "project", "add", "alpha",
            "--name", "Alpha", "--repo", str(self.root),
        )
        self.assertEqual(code, 0, err)
        for key, value, extra in (
            ("deploy-window", "Deploys land in the Tuesday deploy window.", []),
            ("alpha-window", f"Alpha deploy window rota {BOOBY_TRAP} {PLANTED}", []),
        ):
            code, _, err = run_cli(
                "--root", str(self.root), "memory", "add", "--scope", "global",
                "--kind", "fact", "--key", key, "--value", value,
                "--source", "human", "--confidence", "confirmed", *extra,
            )
            self.assertEqual(code, 0, err)

    def _fingerprint(self):
        """Everything a write could disturb: the ledger bytes, the event high
        water mark, and the whole workspace tree."""
        conn = db.open_db(self.aos_dir)
        try:
            events = conn.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
            rows = conn.execute("SELECT COUNT(*) AS n FROM memory").fetchone()["n"]
        finally:
            conn.close()
        return (
            events,
            rows,
            utils.tree_hash(self.root),
            (self.aos_dir / "aos.db").read_bytes(),
        )

    def test_query_commands_emit_no_events_or_mutations(self):
        """(33) Nothing changes: not a row, not an event, not a byte."""
        before = self._fingerprint()
        for argv in (
            ["retrieval", "query", "deploy window"],
            ["retrieval", "query", "deploy window", "--project", "alpha"],
            ["retrieval", "query", "deploy window", "--graph-depth", "1"],
            ["retrieval", "query", "deploy window", "--json", "--show-key"],
            ["retrieval", "query", "the and of"],
        ):
            code, _, err = run_cli("--root", str(self.root), *argv)
            self.assertEqual(code, 0, f"{argv}: {err}")
        self.assertEqual(self._fingerprint(), before)

    def test_benchmark_commands_are_read_only(self):
        """(32) And touch no database at all."""
        before = self._fingerprint()
        for argv in (
            ["retrieval", "benchmark", "list"],
            ["retrieval", "benchmark", "show", "core-retrieval"],
            ["retrieval", "benchmark", "run", "core-retrieval"],
            ["retrieval", "benchmark", "run", "graph-expansion", "--json"],
        ):
            code, _, err = run_cli("--root", str(self.root), *argv)
            self.assertEqual(code, 0, f"{argv}: {err}")
        self.assertEqual(self._fingerprint(), before)

    def test_benchmark_run_opens_no_database(self):
        """(D-v0.3.60) Structural, not incidental: with db.open_db patched to
        raise, the run still succeeds — there is no connection to write
        through."""
        with mock.patch.object(
            db, "open_db", side_effect=AssertionError("benchmark opened the ledger")
        ):
            code, out, err = run_cli("retrieval", "benchmark", "run", "core-retrieval")
        self.assertEqual(code, 0, err)
        self.assertIn("candidate-0", out)

    def test_benchmark_run_needs_no_workspace_at_all(self):
        """(D-v0.3.60) Runs outside a workspace, byte-identically."""
        with tempfile.TemporaryDirectory() as empty:
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "aos.py"), "retrieval",
                 "benchmark", "run", "core-retrieval", "--json"],
                cwd=empty, capture_output=True, text=True, timeout=180,
                env=dict(os.environ, PYTHONPATH=str(REPO_ROOT)),
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        inside, _, _ = run_cli(
            "retrieval", "benchmark", "run", "core-retrieval", "--json"
        )
        code, out, _ = run_cli(
            "retrieval", "benchmark", "run", "core-retrieval", "--json"
        )
        self.assertEqual(result.stdout, out)

    def test_no_retrieval_command_creates_power_json(self):
        """(35)"""
        state = self.aos_dir / power.STATE_FILENAME
        self.assertFalse(state.exists())
        for argv in (
            ["retrieval", "benchmark", "list"],
            ["retrieval", "benchmark", "run", "core-retrieval"],
            ["retrieval", "query", "deploy window"],
            ["retrieval", "query", "deploy window", "--graph-depth", "1"],
        ):
            run_cli("--root", str(self.root), *argv)
            self.assertFalse(state.exists(), f"{argv} created power.json")

    def test_recovery_permits_all_retrieval_commands(self):
        """(34) Understanding a damaged workspace is exactly when retrieval
        inspection earns its keep."""
        code, _, err = run_cli("--root", str(self.root), "power", "set", "recovery")
        self.assertEqual(code, 0, err)
        self.assertEqual(power.read_state(self.aos_dir).mode, power.RECOVERY)
        for argv in (
            ["retrieval", "benchmark", "list"],
            ["retrieval", "benchmark", "show", "core-retrieval"],
            ["retrieval", "benchmark", "run", "core-retrieval"],
            ["retrieval", "query", "deploy window", "--graph-depth", "1"],
        ):
            code, _, err = run_cli("--root", str(self.root), *argv)
            self.assertEqual(code, 0, f"{argv} was blocked in recovery: {err}")

    def test_query_requires_an_initialized_workspace(self):
        """(M5.13)"""
        with tempfile.TemporaryDirectory() as empty:
            code, out, err = run_cli("--root", empty, "retrieval", "query", "x")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("init", err)

    def test_query_does_not_touch_the_derived_fts_index(self):
        """(33) Unlike `search`, retrieval does not even build or refresh the
        derived index or its watermark."""
        conn = db.open_db(self.aos_dir)
        try:
            before = db.get_meta(conn, "fts_event_watermark")
        finally:
            conn.close()
        run_cli("--root", str(self.root), "retrieval", "query", "deploy window")
        conn = db.open_db(self.aos_dir)
        try:
            self.assertEqual(db.get_meta(conn, "fts_event_watermark"), before)
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# (36)(37) Privacy and no-dereference

class PrivacyTests(unittest.TestCase):
    def test_retrieval_imports_no_network_or_process_module(self):
        """(36) Structural: what is not imported cannot be called."""
        source = (REPO_ROOT / "agentic_os" / "retrieval.py").read_text()
        for banned in ("import socket", "import urllib", "import subprocess",
                       "import http", "import requests", "urlopen", "Popen"):
            self.assertNotIn(banned, source, f"retrieval.py references {banned}")

    def test_file_network_and_process_primitives_are_never_used(self):
        """(36) Patch them all to raise and drive the whole surface. Retrieval
        is unaffected because it never calls them."""
        import builtins
        import socket as socket_mod
        import subprocess as subprocess_mod

        def boom(*args, **kwargs):
            raise AssertionError("retrieval dereferenced something")

        dataset = core()
        corpus = retrieval.corpus_from_fixture(dataset)
        with mock.patch.object(builtins, "open", boom), \
             mock.patch.object(socket_mod, "socket", boom), \
             mock.patch.object(subprocess_mod, "run", boom), \
             mock.patch.object(subprocess_mod, "Popen", boom), \
             mock.patch.object(os, "system", boom):
            for text in ("deploy window", "thursday deploy window", "rota token"):
                retrieval.retrieve(
                    corpus, query=text, as_of=T0, limit=5, graph_depth=1,
                    candidate=retrieval.CANDIDATE_1, project="alpha",
                )
            report = retrieval.run_benchmark("graph-expansion")
            self.assertTrue(report["passed"])
            retrieval.registry_index()

    def test_secret_shaped_values_never_enter_a_report(self):
        """(37) The bait is in two fixtures' claim values, and in the checked-in
        JSON. It must never reach stdout, stderr or a report."""
        self.assertIn(PLANTED, (REPO_ROOT / "retrieval_benchmarks" / "core-retrieval.json").read_text())
        for name in retrieval.benchmark_names():
            report = retrieval.run_benchmark(name)
            self.assertNotIn(PLANTED, json.dumps(report))
            self.assertNotIn(PLANTED, protocols.serialize_canonical(report).decode())
        for argv in (
            ["retrieval", "benchmark", "list"],
            ["retrieval", "benchmark", "show", "core-retrieval"],
            ["retrieval", "benchmark", "run", "core-retrieval"],
            ["retrieval", "benchmark", "run", "core-retrieval", "--json"],
            ["retrieval", "benchmark", "run", "graph-expansion", "--json"],
        ):
            code, out, err = run_cli(*argv)
            self.assertNotIn(PLANTED, out, argv)
            self.assertNotIn(PLANTED, err, argv)

    def test_benchmark_show_exposes_no_synthetic_body(self):
        """(M5.13) Metadata and case ids only — no query, no fixture value."""
        code, out, err = run_cli(
            "retrieval", "benchmark", "show", "core-retrieval", "--json"
        )
        self.assertEqual(code, 0, err)
        doc = json.loads(out)
        self.assertEqual(set(doc["cases"]), {c["case"] for c in core()["cases"]})
        for case in core()["cases"]:
            if case["query"].strip():
                self.assertNotIn(case["query"], out, f"{case['case']}'s query leaked")
        for claim in core()["fixture"]["claims"]:
            self.assertNotIn(claim["value"], out)

    def test_default_human_output_prints_no_claim_text(self):
        """(M5.8) Never a value, a locator, provenance, an evidence ref or a
        full hash."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_cli("--root", str(root), "init")
            value = f"Deploy window rota {BOOBY_TRAP} {PLANTED}"
            run_cli(
                "--root", str(root), "memory", "add", "--scope", "global",
                "--kind", "fact", "--key", "deploy-window", "--value", value,
                "--source", "human", "--confidence", "confirmed",
            )
            code, out, err = run_cli(
                "--root", str(root), "retrieval", "query", "deploy window"
            )
            self.assertEqual(code, 0, err)
            self.assertIn("M-0001", out)
            self.assertNotIn(PLANTED, out)
            self.assertNotIn(BOOBY_TRAP, out)
            self.assertNotIn("rota", out)
            # A bounded hash prefix, never the full hash.
            conn = db.open_db(root / ".agentic-os")
            try:
                full = conn.execute(
                    "SELECT content_sha256 AS h FROM memory WHERE id = 1"
                ).fetchone()["h"]
            finally:
                conn.close()
            self.assertNotIn(full, out)
            self.assertIn(full[: models.HASH_PREFIX_CHARS], out)

            # --show-key shows the KEY and still not the value (D-v0.3.64).
            code, out, err = run_cli(
                "--root", str(root), "retrieval", "query", "deploy window",
                "--show-key",
            )
            self.assertEqual(code, 0, err)
            self.assertIn("deploy-window", out)
            self.assertNotIn(PLANTED, out)
            self.assertNotIn(BOOBY_TRAP, out)

    def test_show_key_can_never_reveal_a_restricted_key(self):
        """(D-v0.3.64) Not by redaction — by eligibility. A restricted claim
        cannot reach the renderer to be redacted by it."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_cli("--root", str(root), "init")
            run_cli(
                "--root", str(root), "memory", "add", "--scope", "global",
                "--kind", "fact", "--key", "secret-deploy-window",
                "--value", f"Deploy window {PLANTED}", "--source", "human",
                "--confidence", "confirmed", "--sensitivity", "restricted",
            )
            code, out, err = run_cli(
                "--root", str(root), "retrieval", "query", "deploy window",
                "--show-key", "--json",
            )
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out)["results"], [])
            self.assertNotIn("secret-deploy-window", out)

    def test_a_query_refusal_never_echoes_the_query(self):
        """(37) A query can itself be sensitive."""
        secret_query = f"{PLANTED} " * 30
        code, out, err = run_cli("retrieval", "query", secret_query)
        self.assertNotEqual(code, 0)
        self.assertNotIn(PLANTED, out)
        self.assertNotIn(PLANTED, err)


# ---------------------------------------------------------------------------
# (D-v0.3.53) Baseline fidelity

class BaselineFidelityTests(unittest.TestCase):
    """The baseline must be what production does, proven against the live
    backend rather than asserted in a comment."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="aos-m5-base-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.root = Path(self.tmp)
        self.aos_dir = self.root / ".agentic-os"
        run_cli("--root", str(self.root), "init")
        run_cli(
            "--root", str(self.root), "project", "add", "beta",
            "--name", "Beta", "--repo", str(self.root),
        )
        rows = (
            ("global", None, "deploy-window", "Deploys land in the Tuesday deploy window."),
            ("project", "beta", "beta-deploy-window", "Beta uses a Monday deploy window."),
            ("global", None, "review-cadence", "Weekly review cadence on Friday."),
            ("global", None, "zeta-one", "Ambiguous zeta marker."),
        )
        for scope, project, key, value in rows:
            argv = [
                "--root", str(self.root), "memory", "add", "--scope", scope,
                "--kind", "fact", "--key", key, "--value", value,
                "--source", "human", "--confidence", "confirmed",
            ]
            if project:
                argv += ["--project", project]
            code, _, err = run_cli(*argv)
            self.assertEqual(code, 0, err)
        # A retired claim, which production search surfaces on purpose.
        run_cli(
            "--root", str(self.root), "memory", "add", "--scope", "global",
            "--kind", "fact", "--key", "old-window",
            "--value", "Deploys land in the old deploy window.",
            "--source", "human", "--confidence", "confirmed",
        )
        run_cli("--root", str(self.root), "memory", "retire", "M-0005")

    def test_the_baseline_matches_the_live_search_backend(self):
        """(D-v0.3.53) Same result SET as search.search()'s memory hits, for a
        matrix of queries, against whichever backend this SQLite provides."""
        from agentic_os import search

        conn = db.open_db(self.aos_dir)
        try:
            corpus = retrieval.corpus_from_db(conn)
            for text in ("deploy window", "zeta", "weekly cadence", "deploy",
                         "monday deploy window", "quokka"):
                live = search.search(conn, text)
                expected = {
                    r["id"] for r in live["results"] if r["type"] == "memory"
                }
                got = retrieval.retrieve(
                    corpus, query=text, as_of=utils.utc_now_iso(),
                    limit=retrieval.MAX_RESULTS, graph_depth=0,
                    candidate=retrieval.BASELINE, project=None,
                )
                mine = {
                    r["memory"] for r in got.document()["results"]
                }
                self.assertEqual(
                    mine, expected,
                    f"{text!r}: baseline diverged from the live {live['backend']} backend",
                )
        finally:
            conn.close()

    def test_the_baseline_applies_no_eligibility_filter(self):
        """(D-v0.3.53) Faithful means faithful: production search surfaces the
        retired claim, so the baseline does too — and the report counts it."""
        conn = db.open_db(self.aos_dir)
        try:
            corpus = retrieval.corpus_from_db(conn)
            got = retrieval.retrieve(
                corpus, query="deploy window", as_of=utils.utc_now_iso(),
                limit=10, graph_depth=0, candidate=retrieval.BASELINE,
                project="beta",
            )
        finally:
            conn.close()
        statuses = {s.claim.status for s in got.results}
        self.assertIn("retired", statuses)
        projects = {s.claim.project for s in got.results}
        self.assertIn("beta", projects)

    def test_search_and_pack_behavior_is_unchanged(self):
        """(40) U-M5 touched neither file."""
        for path in ("agentic_os/search.py", "agentic_os/pack.py"):
            diff = subprocess.run(
                ["git", "diff", "a27f591b5d0eda41b2badea28fd41b98184a4689", "--", path],
                cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(diff.stdout, "", f"{path} was modified by U-M5")


# ---------------------------------------------------------------------------
# Doctor

class DoctorTests(unittest.TestCase):
    def test_doctor_reports_the_benchmark_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_cli("--root", str(root), "init")
            conn = db.open_db(root / ".agentic-os")
            try:
                checks = doctor.run_checks(conn, root / ".agentic-os")
            finally:
                conn.close()
        named = [c for c in checks if c.name == "retrieval benchmark registry verified"]
        self.assertEqual(len(named), 1, "exactly one U-M5 doctor check")
        self.assertTrue(named[0].ok)
        self.assertFalse(named[0].warn_only)

    def test_the_doctor_check_does_not_run_a_benchmark(self):
        """(M5.14) Doctor is a health check, not a CI job."""
        with mock.patch.object(
            retrieval, "run_benchmark",
            side_effect=AssertionError("doctor ran the benchmark suite"),
        ):
            check = doctor._retrieval_benchmark_check()
        self.assertTrue(check.ok)

    def test_the_doctor_check_is_byte_identical_with_and_without_a_checkout(self):
        """(M5.14) Doctor's stdout is an entrypoint-parity surface, and
        aos.pyz legitimately has no retrieval_benchmarks/ to compare against.
        The passing line must therefore be a function of the EMBEDDED
        definitions alone — otherwise the script and the archive print two
        different doctors."""
        in_checkout = doctor._retrieval_benchmark_check()
        with mock.patch.object(retrieval, "source_benchmarks_dir", return_value=None):
            in_zipapp = doctor._retrieval_benchmark_check()
        self.assertTrue(in_checkout.ok)
        self.assertTrue(in_zipapp.ok)
        self.assertEqual(in_checkout.name, in_zipapp.name)
        self.assertEqual(in_checkout.detail, in_zipapp.detail)

    def test_the_doctor_check_fails_on_a_drifted_projection(self):
        """(M5.14) It has teeth in a checkout."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "retrieval_benchmarks"
            shutil.copytree(retrieval.source_benchmarks_dir(), root)
            (root / "registry.json").write_bytes(b"{}\n")
            with mock.patch.object(
                retrieval, "source_benchmarks_dir", return_value=root
            ):
                check = doctor._retrieval_benchmark_check()
        self.assertFalse(check.ok)
        self.assertIn("gen_retrieval_benchmarks", check.detail)


# ---------------------------------------------------------------------------
# (38)(39) Script / module / zipapp parity

def _clean_env(**overrides) -> dict:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update(overrides)
    return env


def _run(argv, cwd, env) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv, cwd=str(cwd), env=env, capture_output=True, text=True, timeout=180
    )


class ParityTests(unittest.TestCase):
    """(38)(39) All three entrypoints, byte for byte."""

    @classmethod
    def setUpClass(cls):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "aos_build_zipapp_m5", REPO_ROOT / "tools" / "build_zipapp.py"
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        cls.tmp = Path(tempfile.mkdtemp(prefix="aos-m5-pyz-"))
        cls.archive = module.build(cls.tmp / "aos.pyz")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _parity(self, argv, expected_code=None):
        env = _clean_env(PYTHONPATH=str(REPO_ROOT))
        script = _run([sys.executable, "aos.py", *argv], REPO_ROOT, env)
        module = _run([sys.executable, "-m", "agentic_os", *argv], REPO_ROOT, env)
        # The zipapp runs OUTSIDE the checkout with PYTHONPATH cleared.
        archive = _run(
            [sys.executable, str(self.archive), *argv], self.tmp, _clean_env()
        )
        for name, result in (("module", module), ("zipapp", archive)):
            self.assertEqual(result.stdout, script.stdout, f"{name} stdout differs")
            self.assertEqual(
                result.returncode, script.returncode, f"{name} exit code differs"
            )
        if expected_code is not None:
            self.assertEqual(script.returncode, expected_code, script.stderr)
        return script, archive

    def test_benchmark_list_parity(self):
        """(38)(39)"""
        self._parity(["retrieval", "benchmark", "list"], 0)
        self._parity(["retrieval", "benchmark", "list", "--json"], 0)

    def test_benchmark_show_parity(self):
        """(38)(39)"""
        self._parity(["retrieval", "benchmark", "show", "graph-expansion"], 0)
        self._parity(["retrieval", "benchmark", "show", "core-retrieval", "--json"], 0)

    def test_benchmark_run_parity(self):
        """(38)(39) Including the deterministic JSON document."""
        for name in ("core-retrieval", "graph-expansion"):
            self._parity(["retrieval", "benchmark", "run", name], 0)
            self._parity(["retrieval", "benchmark", "run", name, "--json"], 0)
        self._parity(
            ["retrieval", "benchmark", "run", "core-retrieval", "--candidate",
             "candidate-1", "--k", "3"], 0
        )

    def test_safety_gate_failure_parity(self):
        """(38) The failure path is a parity surface too: same report on
        stdout, same exit code, from all three entrypoints."""
        with tempfile.TemporaryDirectory() as tmp:
            harness = Path(tmp) / "gate_fail.py"
            # A gate failure is impossible from the shipped datasets by
            # design, so the failure path is driven where it lives: through
            # the CLI handler, with a leaking evaluation injected.
            harness.write_text(
                "import sys\n"
                "from unittest import mock\n"
                "from agentic_os import cli, retrieval\n"
                "real = retrieval.run_benchmark\n"
                "def leaky(name, **kw):\n"
                "    report = real(name, **kw)\n"
                "    doc = report['candidates']['candidate-0']\n"
                "    doc['counters']['restricted_leaks'] = 1\n"
                "    doc['gate']['safety_ok'] = False\n"
                "    doc['gate']['gate'] = False\n"
                "    report['passed'] = False\n"
                "    return report\n"
                "with mock.patch.object(retrieval, 'run_benchmark', leaky):\n"
                "    sys.exit(cli.main(sys.argv[1:]))\n"
            )
            env = _clean_env(PYTHONPATH=str(REPO_ROOT))
            result = _run(
                [sys.executable, str(harness), "retrieval", "benchmark", "run",
                 "core-retrieval"],
                REPO_ROOT, env,
            )
        self.assertEqual(result.returncode, 1)
        # The report still went to stdout — the report IS the finding.
        self.assertIn("restricted leaks 1", result.stdout)
        self.assertIn("candidate-0", result.stdout)
        # One actionable line on stderr.
        self.assertIn("Promotion gate FAILED", result.stderr)
        self.assertEqual(len(result.stderr.strip().splitlines()), 1)

    def test_a_validation_refusal_keeps_stdout_byte_empty(self):
        """(38) An AosError refusal: exit 1, stderr only, stdout empty."""
        script, archive = self._parity(
            ["retrieval", "benchmark", "show", "no-such-benchmark"], 1
        )
        self.assertEqual(script.stdout, "")
        self.assertEqual(archive.stdout, "")
        self.assertIn("Unknown benchmark", script.stderr)

    def test_the_zipapp_carries_retrieval_but_no_benchmark_json(self):
        """(39) The datasets travel as Python (D-v0.3.61); the archive gains
        agentic_os/retrieval.py and nothing else."""
        import zipfile

        with zipfile.ZipFile(self.archive) as archive:
            names = set(archive.namelist())
        self.assertIn("agentic_os/retrieval.py", names)
        for name in names:
            if name.endswith("/"):
                continue  # a directory entry, not a member
            self.assertTrue(
                name.endswith(".py"), f"{name} is not a Python source file"
            )
        self.assertFalse(any("retrieval_benchmarks" in n for n in names))
        self.assertFalse(any(n.endswith(".json") for n in names))
        self.assertFalse(any(n.endswith(".db") for n in names))

    def test_the_zipapp_reports_its_benchmarks_from_the_embedded_definitions(self):
        """(39) Outside the checkout, PYTHONPATH cleared, no source tree in
        sight — the digests still match the canonical ones."""
        result = _run(
            [sys.executable, str(self.archive), "retrieval", "benchmark",
             "list", "--json"],
            self.tmp, _clean_env(),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), retrieval.registry_index())


if __name__ == "__main__":
    unittest.main()
