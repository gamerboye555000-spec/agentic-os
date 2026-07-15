#!/usr/bin/env python3
"""Build the standalone `aos.pyz` zipapp — standard library only.

    python3 tools/build_zipapp.py
    python3 tools/build_zipapp.py --output PATH

The archive carries the agentic_os runtime package plus a root __main__.py
copied verbatim from agentic_os/__main__.py, so every entrypoint runs the one
canonical CLI. See agentic-os-v0.2-u-p1-packaging-contract.md.
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import sys
import tempfile
import zipapp
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_NAME = "agentic_os"
DEFAULT_OUTPUT = REPO_ROOT / "dist" / "aos.pyz"
INTERPRETER = "/usr/bin/env python3"
ARCHIVE_MODE = 0o755


class BuildError(Exception):
    """A build failure. Diagnostics name paths and conditions only."""


def runtime_sources(package_dir: Path) -> list[Path]:
    """The archive allowlist: package .py sources, minus __pycache__.

    Allowlist, not denylist: everything the archive must exclude (.git,
    .agentic-os, tests, *.pyc, ledger DBs, backups, exports, credentials,
    docs) is excluded because it is not a .py file under the package — not
    because it was named. A denylist can be defeated by a new file with an
    unanticipated name.
    """
    return sorted(
        p
        for p in package_dir.rglob("*.py")
        if p.is_file() and "__pycache__" not in p.relative_to(package_dir).parts
    )


def _stage_tree(package_dir: Path, stage_root: Path) -> None:
    entrypoint = package_dir / "__main__.py"
    if not entrypoint.is_file():
        raise BuildError(f"missing module entrypoint: {entrypoint}")

    sources = runtime_sources(package_dir)
    if not sources:
        raise BuildError(f"no runtime sources found under {package_dir}")

    for src in sources:
        dest = stage_root / PACKAGE_NAME / src.relative_to(package_dir)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)

    # Archive root entrypoint == module entrypoint, byte for byte.
    shutil.copyfile(entrypoint, stage_root / "__main__.py")


def _object_kind(mode: int) -> str:
    if stat.S_ISDIR(mode):
        return "a directory"
    if stat.S_ISFIFO(mode):
        return "a FIFO"
    if stat.S_ISSOCK(mode):
        return "a socket"
    if stat.S_ISBLK(mode):
        return "a block device"
    if stat.S_ISCHR(mode):
        return "a character device"
    return "not a regular file"


def check_output_path(output: Path) -> None:
    """Refuse any existing output object that is not a regular file.

    lstat, never stat: a symlink must be seen as a symlink rather than
    followed to whatever it points at. Fail-closed — the existing object is
    left exactly as found.
    """
    try:
        st = os.lstat(output)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise BuildError(f"cannot inspect output path {output}: {exc.strerror}") from exc

    if stat.S_ISLNK(st.st_mode):
        raise BuildError(f"refusing to replace a symlink: {output}")
    if not stat.S_ISREG(st.st_mode):
        raise BuildError(
            f"refusing to replace output path ({_object_kind(st.st_mode)}): {output}"
        )


def build(output: Path, repo_root: Path = REPO_ROOT) -> Path:
    """Build the archive, replacing `output` only on complete success."""
    output = Path(output).expanduser()
    if not output.is_absolute():
        output = Path.cwd() / output
    # Resolve the parent only. Resolving the final component would follow a
    # symlink there and defeat check_output_path.
    output = output.parent.resolve() / output.name

    package_dir = Path(repo_root) / PACKAGE_NAME
    if not (package_dir / "__init__.py").is_file():
        raise BuildError(f"not a source checkout: {package_dir} is not a package")

    check_output_path(output)

    try:
        output.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BuildError(
            f"cannot create output directory {output.parent}: {exc.strerror}"
        ) from exc

    tmp_path: Path | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="aos-zipapp-") as stage_dir:
            stage_root = Path(stage_dir)
            _stage_tree(package_dir, stage_root)

            # Temp archive lands beside the destination so the final rename is
            # atomic (same filesystem). The destination is never opened for
            # writing, so a failure cannot corrupt or truncate it.
            fd, tmp_name = tempfile.mkstemp(
                prefix=".aos-pyz-", suffix=".tmp", dir=output.parent
            )
            os.close(fd)
            tmp_path = Path(tmp_name)

            zipapp.create_archive(stage_root, target=tmp_path, interpreter=INTERPRETER)
            os.chmod(tmp_path, ARCHIVE_MODE)

        os.replace(tmp_path, output)
        tmp_path = None
    except OSError as exc:
        raise BuildError(f"build failed: {exc}") from exc
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass

    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="build_zipapp",
        description="Build the standalone aos.pyz zipapp (standard library only).",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="PATH",
        help=f"archive path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args(argv)

    try:
        built = build(Path(args.output) if args.output else DEFAULT_OUTPUT)
    except BuildError as exc:
        print(f"build_zipapp: {exc}", file=sys.stderr)
        return 1
    print(f"Built {built}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
