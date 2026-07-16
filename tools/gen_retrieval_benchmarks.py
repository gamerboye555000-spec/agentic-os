#!/usr/bin/env python3
"""Write the checked-in retrieval_benchmarks/ projection — standard library only.

    python3 tools/gen_retrieval_benchmarks.py            # verify (writes nothing)
    python3 tools/gen_retrieval_benchmarks.py --write    # regenerate

The embedded definitions in agentic_os/retrieval.py are canonical (D-v0.3.61).
This script only *projects* them onto disk; it is never a second source of
truth, and a file it writes is a pure function of the Python. It lives in
tools/ because every `aos retrieval` leaf is read_only by classification and
therefore cannot regenerate anything — and because tools/ is outside the
zipapp's package allowlist, so this writer never ships inside aos.pyz.

Deliberately the same shape as tools/gen_protocols.py: two projections of two
embedded registries, one mechanic. See
agentic-os-v0.3-u-m5-retrieval-evals-contract.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agentic_os import retrieval  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gen_retrieval_benchmarks",
        description="Project the embedded benchmark registry onto "
        "retrieval_benchmarks/.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the artifacts (default: verify only, exit 1 on drift)",
    )
    args = parser.parse_args(argv)

    root = REPO_ROOT / retrieval.BENCHMARK_DIRNAME
    artifacts = retrieval.expected_source_artifacts()

    if not args.write:
        if not root.is_dir():
            print(
                f"gen_retrieval_benchmarks: {root} is missing; run with --write",
                file=sys.stderr,
            )
            return 1
        problems = retrieval.verify_embedded() + retrieval.verify_source_benchmarks(root)
        if problems:
            for problem in problems:
                print(f"gen_retrieval_benchmarks: {problem}", file=sys.stderr)
            print(
                "gen_retrieval_benchmarks: run with --write to regenerate",
                file=sys.stderr,
            )
            return 1
        print(
            f"retrieval_benchmarks/: {len(artifacts)} artifact(s) match the "
            "embedded definitions"
        )
        return 0

    for relpath, data in sorted(artifacts.items()):
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        # Bytes, not text: the projection's exact newline handling is the
        # canonical serializer's, and a text-mode write would let the
        # platform have an opinion about it.
        path.write_bytes(data)
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
