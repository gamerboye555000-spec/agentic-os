#!/usr/bin/env python3
"""Write the checked-in protocols/ projection — standard library only.

    python3 tools/gen_protocols.py            # verify (default: writes nothing)
    python3 tools/gen_protocols.py --write    # regenerate the artifacts

The embedded definitions in agentic_os/protocols.py are canonical (D-v0.3.2).
This script only *projects* them onto disk (D-v0.3.3); it is never a second
source of truth, and a file it writes is a pure function of the Python. It
lives in tools/ because the CLI is read_only by classification and therefore
cannot regenerate anything (D-v0.3.12) — and because tools/ is outside the
zipapp's package allowlist, so this writer never ships inside aos.pyz.

See agentic-os-v0.3-u-x1-protocol-spine-contract.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agentic_os import protocols  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gen_protocols",
        description="Project the embedded protocol registry onto protocols/.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the artifacts (default: verify only, exit 1 on drift)",
    )
    args = parser.parse_args(argv)

    root = REPO_ROOT / protocols.ARTIFACT_DIRNAME
    artifacts = protocols.expected_source_artifacts()

    if not args.write:
        if not root.is_dir():
            print(f"gen_protocols: {root} is missing; run with --write", file=sys.stderr)
            return 1
        problems = protocols.verify_source_artifacts(root)
        if problems:
            for problem in problems:
                print(f"gen_protocols: {problem}", file=sys.stderr)
            print("gen_protocols: run with --write to regenerate", file=sys.stderr)
            return 1
        print(f"protocols/: {len(artifacts)} artifact(s) match the embedded definitions")
        return 0

    for relpath, data in sorted(artifacts.items()):
        path = root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        # Bytes, not text: the projection's exact newline handling is the
        # thing under test, so it must not pass through platform translation.
        changed = not path.is_file() or path.read_bytes() != data
        if changed:
            path.write_bytes(data)
        print(f"{'wrote' if changed else 'unchanged'} {protocols.ARTIFACT_DIRNAME}/{relpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
