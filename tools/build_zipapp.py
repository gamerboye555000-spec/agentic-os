#!/usr/bin/env python3
"""Build the standalone `aos.pyz` zipapp — standard library only.

    python3 tools/build_zipapp.py
    python3 tools/build_zipapp.py --output PATH

The archive carries the agentic_os runtime package plus a root __main__.py
copied verbatim from agentic_os/__main__.py, so every entrypoint runs the one
canonical CLI. See agentic-os-v0.2-u-p1-packaging-contract.md.

U-A2 adds the built-in specialist catalog's data files to the archive: the
checked-in manifest plus exactly the passport artifacts it references —
never a broad `catalog/*.json` sweep (D-v0.4.14). The manifest and every
referenced passport are independently re-verified here (canonical bytes,
digests, identity bindings) before anything is allowed into the archive, so
a corrupted or tampered artifact fails the BUILD rather than being silently
dropped or silently shipped stale. This module stays standard-library-only
and never imports `agentic_os` itself — the canonical-JSON and digest rules
below are intentionally small, self-contained duplicates of the same rules
in `agentic_os/protocols.py` and `agentic_os/catalog.py`, not a shared import.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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

# ---------------------------------------------------------------------------
# Catalog data allowlist (U-A2, D-v0.4.14) — small, deliberate duplicates of
# agentic_os/protocols.py's and agentic_os/catalog.py's constants and
# canonical-JSON rules. Duplicated, not imported: the builder must remain
# runnable with the standard library alone and must never import the
# package it is packaging.

CATALOG_DIRNAME = "catalog"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_VERSION = 1
CATALOG_ISSUER = "aos.catalog"
CANONICAL_JSON = "aos-canonical-json/v1"
CONTENT_HASH_ALG = "aos-sha256-canonical/v1"
CONTENT_HASH_FIELD = "content_sha256"

#: Mirrors protocols.MAX_ARTIFACT_BYTES — a bound on any single catalog
#: artifact, applied before the file is ever parsed.
MAX_ARTIFACT_BYTES = 262144
MAX_ENTRIES = 64
MAX_VERSIONS_PER_ENTRY = 32

#: A catalog artifact's on-disk name is a pure function of identity, exactly
#: as in catalog.py: '/' and '\\' cannot appear in the allowed charset, and
#: a full match against the DERIVED "{agent}.v{n}.passport.json" name (checked
#: below) makes a traversal or absolute path structurally unreachable.
_PASSPORT_PATH_RE = re.compile(
    r"^[a-z][a-z0-9._-]{0,63}\.v[1-9][0-9]{0,3}\.passport\.json\Z", re.ASCII
)
_HEX64_RE = re.compile(r"^[0-9a-f]{64}\Z", re.ASCII)

_MANIFEST_KEYS = frozenset(
    {
        "canonical_json",
        "catalog_version",
        "content_hash_alg",
        "content_sha256",
        "entries",
        "issuer",
        "manifest_version",
    }
)
_ENTRY_KEYS = frozenset({"agent", "category", "maturity", "versions"})
_VERSION_KEYS = frozenset({"document_sha256", "passport_version", "path"})


class BuildError(Exception):
    """A build failure. Diagnostics name paths and conditions only."""


def _canonical_bytes(value) -> bytes:
    """Duplicates protocols.serialize_canonical's exact byte rule: sorted
    keys, no whitespace, UTF-8, no trailing newline, no NaN/Infinity."""
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _content_digest(document: dict) -> str:
    """Duplicates protocols.content_digest: sha256 over the canonical body
    with only the top-level content_sha256 member removed. NEVER a raw
    file-byte digest — that would let a merely re-formatted (still
    semantically identical) artifact spuriously fail, or a substituted body
    with a stale hash spuriously pass."""
    body = {k: v for k, v in document.items() if k != CONTENT_HASH_FIELD}
    return hashlib.sha256(_canonical_bytes(body)).hexdigest()


def _dup_key_pairs_hook(pairs):
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise BuildError(f"catalog artifact repeats JSON key {key!r}")
        seen.add(key)
    return dict(pairs)


def _read_regular_file(path: Path, *, what: str) -> bytes:
    """Bounded, symlink-refusing read of one checked-in catalog artifact."""
    try:
        st = path.lstat()
    except OSError as exc:
        raise BuildError(f"missing {what}: {path.name}") from exc
    if stat.S_ISLNK(st.st_mode):
        raise BuildError(f"refusing a symlinked {what}: {path.name}")
    if not stat.S_ISREG(st.st_mode):
        raise BuildError(f"refusing a non-regular {what}: {path.name}")
    if st.st_size > MAX_ARTIFACT_BYTES:
        raise BuildError(f"{what} exceeds {MAX_ARTIFACT_BYTES} bytes: {path.name}")
    data = path.read_bytes()
    if len(data) > MAX_ARTIFACT_BYTES:
        raise BuildError(f"{what} exceeds {MAX_ARTIFACT_BYTES} bytes: {path.name}")
    return data


def _load_canonical_document(path: Path, data: bytes, *, what: str) -> dict:
    """Bytes -> a validated canonical-JSON object: valid UTF-8, exactly the
    canonical bytes plus one trailing newline, well-formed JSON with no
    duplicate key, and a top-level JSON object."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BuildError(f"{what} is not valid UTF-8: {path.name}") from exc
    if not text.endswith("\n") or text.endswith("\n\n"):
        raise BuildError(
            f"{what} is not canonical (missing or extra trailing newline): {path.name}"
        )
    body_text = text[:-1]
    try:
        document = json.loads(body_text, object_pairs_hook=_dup_key_pairs_hook)
    except ValueError as exc:
        raise BuildError(f"{what} is not valid JSON: {path.name}") from exc
    if not isinstance(document, dict):
        raise BuildError(f"{what} is not a JSON object: {path.name}")
    if _canonical_bytes(document) != body_text.encode("utf-8"):
        raise BuildError(f"{what} is not canonical JSON: {path.name}")
    return document


def _validate_manifest_structure(document: dict) -> None:
    """The 18-point manifest allowlist gate (D-v0.4.14): closed keys, closed
    vocabulary, self-digest, sort order, version contiguity, path
    derivation/safety, and no duplicate agent, path, or digest."""
    if not isinstance(document, dict) or set(document) != _MANIFEST_KEYS:
        raise BuildError("catalog manifest: unexpected or missing top-level field")
    if document.get("canonical_json") != CANONICAL_JSON:
        raise BuildError("catalog manifest: bad canonical_json")
    if document.get("content_hash_alg") != CONTENT_HASH_ALG:
        raise BuildError("catalog manifest: bad content_hash_alg")
    if document.get("issuer") != CATALOG_ISSUER:
        raise BuildError("catalog manifest: bad issuer")
    if document.get("manifest_version") != MANIFEST_VERSION:
        raise BuildError("catalog manifest: bad manifest_version")

    catalog_version = document.get("catalog_version")
    if type(catalog_version) is not int or not (1 <= catalog_version <= 999999):
        raise BuildError("catalog manifest: bad catalog_version")

    declared_digest = document.get("content_sha256")
    if not isinstance(declared_digest, str) or not _HEX64_RE.fullmatch(declared_digest):
        raise BuildError("catalog manifest: malformed content_sha256")

    entries = document.get("entries")
    if not isinstance(entries, list) or not (1 <= len(entries) <= MAX_ENTRIES):
        raise BuildError("catalog manifest: bad entries array")

    seen_agents: set[str] = set()
    seen_paths: set[str] = set()
    seen_digests: set[str] = set()
    previous_agent: str | None = None

    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != _ENTRY_KEYS:
            raise BuildError("catalog manifest: malformed entry")

        agent = entry.get("agent")
        if not isinstance(agent, str) or not agent.startswith("aos."):
            raise BuildError("catalog manifest: entry outside the catalog namespace")
        if agent in seen_agents:
            raise BuildError(f"catalog manifest: duplicate agent {agent!r}")
        if previous_agent is not None and agent <= previous_agent:
            raise BuildError("catalog manifest: entries are not sorted by agent")
        seen_agents.add(agent)
        previous_agent = agent

        versions = entry.get("versions")
        if not isinstance(versions, list) or not (1 <= len(versions) <= MAX_VERSIONS_PER_ENTRY):
            raise BuildError(f"catalog manifest: bad versions array for {agent!r}")

        expected_version = 1
        for version in versions:
            if not isinstance(version, dict) or set(version) != _VERSION_KEYS:
                raise BuildError(f"catalog manifest: malformed version entry for {agent!r}")

            passport_version = version.get("passport_version")
            if type(passport_version) is not int or passport_version != expected_version:
                raise BuildError(f"catalog manifest: version gap for {agent!r}")

            digest = version.get("document_sha256")
            if not isinstance(digest, str) or not _HEX64_RE.fullmatch(digest):
                raise BuildError(
                    f"catalog manifest: malformed document_sha256 for {agent!r} v{expected_version}"
                )
            if digest in seen_digests:
                raise BuildError(
                    f"catalog manifest: duplicate document digest for {agent!r} v{expected_version}"
                )

            path = version.get("path")
            expected_path = f"{agent}.v{passport_version}.passport.json"
            if (
                not isinstance(path, str)
                or path != expected_path
                or not _PASSPORT_PATH_RE.fullmatch(path)
            ):
                raise BuildError(
                    f"catalog manifest: unsafe or mismatched path for {agent!r} v{expected_version}"
                )
            if path in seen_paths:
                raise BuildError(f"catalog manifest: duplicate path {path!r}")

            seen_paths.add(path)
            seen_digests.add(digest)
            expected_version += 1

    # Correctness, only after every structural rule above holds.
    if _content_digest(document) != declared_digest:
        raise BuildError("catalog manifest: self-digest does not match its body")


def load_catalog_manifest(catalog_dir: Path) -> dict:
    """Read and fully validate agentic_os/catalog/manifest.json — the
    allowlist's own source of truth."""
    manifest_path = catalog_dir / MANIFEST_FILENAME
    data = _read_regular_file(manifest_path, what="catalog manifest")
    document = _load_canonical_document(manifest_path, data, what="catalog manifest")
    _validate_manifest_structure(document)
    return document


def _validate_passport(path: Path, *, agent: str, version: dict) -> None:
    """The 12-point passport gate (D-v0.4.14): regular file, bounded size,
    canonical UTF-8 JSON with no duplicate key, a lowercase-64-hex internal
    content_sha256 that recomputes correctly AND matches the manifest's
    document_sha256 for this version, and an agent/passport_version binding
    that matches the manifest entry. A tampered internal content_sha256, a
    tampered body, or a mismatched binding all fail the BUILD."""
    data = _read_regular_file(path, what="catalog passport")
    document = _load_canonical_document(path, data, what="catalog passport")

    internal_digest = document.get(CONTENT_HASH_FIELD)
    if not isinstance(internal_digest, str) or not _HEX64_RE.fullmatch(internal_digest):
        raise BuildError(f"catalog passport: malformed content_sha256: {path.name}")

    recomputed = _content_digest(document)
    if recomputed != internal_digest:
        raise BuildError(f"catalog passport: content_sha256 does not match its body: {path.name}")
    if recomputed != version["document_sha256"]:
        raise BuildError(f"catalog passport: digest does not match the manifest: {path.name}")

    if (
        document.get("agent") != agent
        or document.get("passport_version") != version["passport_version"]
    ):
        raise BuildError(f"catalog passport: agent/version binding mismatch: {path.name}")


def catalog_resources(package_dir: Path) -> list[Path]:
    """The manifest-driven catalog allowlist: the manifest itself plus
    exactly the passport paths its entries reference — nothing more. An
    unreferenced file under agentic_os/catalog/ (e.g. a stray
    credentials.json) is excluded by construction, never by name. Every
    referenced artifact is independently re-verified before being allowed
    into the return list, so a corrupt or tampered artifact fails the build
    rather than silently being dropped or silently shipped stale.
    """
    catalog_dir = package_dir / CATALOG_DIRNAME
    manifest = load_catalog_manifest(catalog_dir)

    resources = [catalog_dir / MANIFEST_FILENAME]
    for entry in manifest["entries"]:
        agent = entry["agent"]
        for version in entry["versions"]:
            passport_path = catalog_dir / version["path"]
            _validate_passport(passport_path, agent=agent, version=version)
            resources.append(passport_path)
    return resources


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

    # The built-in catalog's data files (U-A2): the manifest plus exactly
    # the passport artifacts it references, each independently re-verified
    # by catalog_resources() before it is allowed here.
    for resource in catalog_resources(package_dir):
        dest = stage_root / PACKAGE_NAME / resource.relative_to(package_dir)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(resource, dest)


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
