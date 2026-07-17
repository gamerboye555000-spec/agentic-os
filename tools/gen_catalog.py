#!/usr/bin/env python3
"""Author and verify the built-in specialist catalog — standard library only.

    python3 tools/gen_catalog.py            # verify (default: writes nothing)
    python3 tools/gen_catalog.py --check     # same, spelled explicitly
    python3 tools/gen_catalog.py --write     # normalize artifacts + project manifest.json

The twelve agentic_os/catalog/aos.*.v1.passport.json artifacts are AUTHORED
declarations: this tool never generates their role/mission/capability prose
from a hidden Python dictionary. It only (a) canonicalizes each authored
artifact to its exact on-disk bytes and recomputes its internal
content_sha256, and (b) projects agentic_os/catalog/manifest.json — a
deterministic index + digest map — from those artifacts plus the small
CATEGORY_MATURITY table below (index metadata the passport schema itself
cannot carry; U-A2 catalog contract §7). The passports remain the source of
truth; the manifest is a pure projection of them.

It lives in tools/ because every `agent catalog` leaf this wave ships is
read_only by classification and therefore cannot regenerate anything, and
because tools/ is outside the zipapp's package allowlist, so this writer
never ships inside aos.pyz.

See agentic-os-v0.4-u-a2-specialist-catalog-contract.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agentic_os import protocols, secretscan  # noqa: E402
from agentic_os.models import validate_catalog_agent_name  # noqa: E402
from agentic_os.passports import _SCANNED_TEXT_FIELDS, PASSPORT_PROTOCOL  # noqa: E402

CATALOG_DIRNAME = "catalog"
MANIFEST_FILENAME = "manifest.json"
MANIFEST_VERSION = 1
CATALOG_VERSION = 1
ISSUER = "aos.catalog"

CATALOG_DIR = REPO_ROOT / "agentic_os" / CATALOG_DIRNAME

#: Index metadata the passport schema itself cannot carry (I2 — the manifest
#: is an index, never a second declaration source): category and maturity per
#: entry, exactly the frozen twelve names from the contract (§4). This table
#: drives WHICH artifacts exist and their manifest placement; it supplies no
#: role/mission/capability prose — that lives only in the authored artifacts.
CATEGORY_MATURITY: dict[str, tuple[str, str]] = {
    "aos.architect": ("design", "stable"),
    "aos.planner": ("design", "stable"),
    "aos.builder": ("delivery", "stable"),
    "aos.verifier": ("assurance", "stable"),
    "aos.reviewer": ("assurance", "stable"),
    "aos.security-auditor": ("assurance", "stable"),
    "aos.debugger": ("operations", "stable"),
    "aos.release-engineer": ("operations", "stable"),
    "aos.researcher": ("knowledge", "stable"),
    "aos.curator": ("knowledge", "stable"),
    "aos.analyst": ("knowledge", "provisional"),
    "aos.technical-writer": ("knowledge", "stable"),
}
CATEGORIES = ("design", "delivery", "assurance", "operations", "knowledge")
MATURITIES = ("stable", "provisional")

#: U-A2 ships N=1 for every entry at this catalog version (D-v0.4.17); a
#: future upgrade adds a second authored file and a second entry here.
SHIPPED_VERSION = 1


class GenCatalogError(Exception):
    """A generation/verification failure. Diagnostics name conditions only,
    never a document value."""


def _artifact_path(agent: str, version: int) -> Path:
    return CATALOG_DIR / f"{agent}.v{version}.passport.json"


def _load_authored(agent: str, version: int) -> dict:
    path = _artifact_path(agent, version)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise GenCatalogError(f"{path.name}: cannot be read ({exc.__class__.__name__})") from None
    try:
        document = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        raise GenCatalogError(f"{path.name}: not valid UTF-8") from None
    except ValueError as exc:
        raise GenCatalogError(f"{path.name}: not well-formed JSON ({exc})") from None
    if not isinstance(document, dict):
        raise GenCatalogError(f"{path.name}: top-level value is not an object")
    return document


def _refuse_if_secret_shaped(agent: str, version: int, document: dict) -> None:
    """Fail-closed secret-shape refusal over the passport's free-text fields
    (D-v0.4.19): shipped content is reviewed content the project ships, not a
    trusted human's live keystrokes, so a hit here REFUSES rather than warns.
    """
    for key, label in _SCANNED_TEXT_FIELDS:
        value = document.get(key)
        if isinstance(value, list):
            value = "\n".join(str(item) for item in value)
        if isinstance(value, str) and secretscan.scan_secrets(value):
            raise GenCatalogError(f"{agent} v{version}: secret-shaped content in {label!r}")


def _canonicalize(agent: str, version: int, document: dict) -> dict:
    """Recompute content_sha256 over the authored body, then prove the
    result is a valid, correctly-bound catalog passport."""
    document = dict(document)
    document.pop(protocols.CONTENT_HASH_FIELD, None)
    document[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(document)

    try:
        entry = protocols.validate_document(document)
    except protocols.ProtocolError as exc:
        raise GenCatalogError(f"{agent} v{version}: {exc}") from None
    if entry.identity != PASSPORT_PROTOCOL:
        raise GenCatalogError(f"{agent} v{version}: not a {PASSPORT_PROTOCOL} artifact")

    checks = (
        ("agent", agent),
        ("passport_version", version),
        ("issuer", ISSUER),
        ("agent_class", "specialist"),
        ("agent_scope", {"level": "global"}),
        ("autonomy", "declare_only"),
    )
    for field, expected in checks:
        if document.get(field) != expected:
            raise GenCatalogError(
                f"{agent} v{version}: {field} must be {expected!r}, found "
                f"{document.get(field)!r}"
            )
    for forbidden in ("provider_compat", "limits"):
        if forbidden in document:
            raise GenCatalogError(f"{agent} v{version}: {forbidden!r} must be omitted")

    _refuse_if_secret_shaped(agent, version, document)
    return document


def canonical_artifacts() -> dict[str, bytes]:
    """relpath → exact file bytes for every authored passport, canonicalized."""
    artifacts: dict[str, bytes] = {}
    for agent, (category, maturity) in sorted(CATEGORY_MATURITY.items()):
        validate_catalog_agent_name(agent)
        if category not in CATEGORIES:
            raise GenCatalogError(f"{agent}: unknown category {category!r}")
        if maturity not in MATURITIES:
            raise GenCatalogError(f"{agent}: unknown maturity {maturity!r}")
        version = SHIPPED_VERSION
        document = _canonicalize(agent, version, _load_authored(agent, version))
        artifacts[_artifact_path(agent, version).name] = protocols.serialize_canonical_file_bytes(
            document
        )
    return artifacts


def build_manifest(artifacts: dict[str, bytes]) -> dict:
    entries = []
    for agent, (category, maturity) in sorted(CATEGORY_MATURITY.items()):
        version = SHIPPED_VERSION
        relpath = _artifact_path(agent, version).name
        document = protocols.parse_canonical(artifacts[relpath])
        entries.append(
            {
                "agent": agent,
                "category": category,
                "maturity": maturity,
                "versions": [
                    {
                        "document_sha256": protocols.content_digest(document),
                        "passport_version": version,
                        "path": relpath,
                    }
                ],
            }
        )
    manifest = {
        "canonical_json": protocols.CANONICAL_JSON,
        "catalog_version": CATALOG_VERSION,
        "content_hash_alg": protocols.CONTENT_HASH_ALG,
        "entries": entries,
        "issuer": ISSUER,
        "manifest_version": MANIFEST_VERSION,
    }
    manifest[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(manifest)
    return manifest


def expected_artifacts() -> dict[str, bytes]:
    """relpath → exact bytes for every file agentic_os/catalog/ must contain:
    the manifest plus every canonicalized passport artifact."""
    artifacts = canonical_artifacts()
    manifest = build_manifest(artifacts)
    out = {MANIFEST_FILENAME: protocols.serialize_canonical_file_bytes(manifest)}
    out.update(artifacts)
    return out


def verify(root: Path) -> list[str]:
    """Compare agentic_os/catalog/ to the expected projection, byte-for-byte.
    Also reports any *.json file the projection does not reference."""
    try:
        expected = expected_artifacts()
    except GenCatalogError as exc:
        return [str(exc)]

    problems: list[str] = []
    for relpath, data in sorted(expected.items()):
        path = root / relpath
        try:
            actual = path.read_bytes()
        except OSError:
            problems.append(f"{relpath}: missing or unreadable")
            continue
        if actual != data:
            problems.append(f"{relpath}: does not match the canonical projection")

    known = set(expected)
    if root.is_dir():
        for path in sorted(root.glob("*.json")):
            if path.name not in known:
                problems.append(f"{path.name}: not referenced by the generated projection")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gen_catalog",
        description="Canonicalize the built-in specialist catalog and project its manifest.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="normalize the passport artifacts and (re)write manifest.json "
        "(default: verify only, exit 1 on drift)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify only — the default; accepted explicitly for readable "
        "invocation in scripts/CI",
    )
    args = parser.parse_args(argv)
    if args.write and args.check:
        print("gen_catalog: pass exactly one of --write or --check", file=sys.stderr)
        return 2

    if not args.write:
        if not CATALOG_DIR.is_dir():
            print(f"gen_catalog: {CATALOG_DIR} is missing; run with --write", file=sys.stderr)
            return 1
        problems = verify(CATALOG_DIR)
        if problems:
            for problem in problems:
                print(f"gen_catalog: {problem}", file=sys.stderr)
            print("gen_catalog: run with --write to regenerate", file=sys.stderr)
            return 1
        print(
            f"{CATALOG_DIRNAME}/: {len(expected_artifacts())} artifact(s) match "
            "the canonical projection"
        )
        return 0

    try:
        artifacts = expected_artifacts()
    except GenCatalogError as exc:
        print(f"gen_catalog: {exc}", file=sys.stderr)
        return 1
    CATALOG_DIR.mkdir(parents=True, exist_ok=True)
    for relpath, data in sorted(artifacts.items()):
        path = CATALOG_DIR / relpath
        changed = not path.is_file() or path.read_bytes() != data
        if changed:
            path.write_bytes(data)
        print(f"{'wrote' if changed else 'unchanged'} {CATALOG_DIRNAME}/{relpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
