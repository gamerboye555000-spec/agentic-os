"""U-X1 protocol spine: canonical JSON, content hashing, schema registry.

Contract: agentic-os-v0.3-u-x1-protocol-spine-contract.md

Everything here is INERT. This module parses bytes and compares them to a
schema. It never executes, imports, evals, resolves, fetches, opens or stats
anything an artifact *references* (D-v0.3.7). A `sha256` field inside a
WorkSpec is a declared reference, not an instruction to go hash a file.

The embedded definitions below are canonical (D-v0.3.2): aos.pyz is one file
with no data directory, so a registry living in protocols/*.json would make
the archive non-functional. The checked-in JSON under protocols/ is a
deterministic projection of these definitions (D-v0.3.3), verified
byte-for-byte — never a second editable source.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import MappingProxyType

from .models import EVIDENCE_KINDS, RUN_OUTCOMES
from .utils import AosError

# ---------------------------------------------------------------------------
# Names

CANONICAL_JSON = "aos-canonical-json/v1"
CONTENT_HASH_ALG = "aos-sha256-canonical/v1"
CONTENT_HASH_FIELD = "content_sha256"
REGISTRY_VERSION = 1

#: The projection's home, relative to the repository root.
ARTIFACT_DIRNAME = "protocols"
REGISTRY_FILENAME = "registry.json"

# ---------------------------------------------------------------------------
# Bounds (contract §2.4). Pinned, not tuned.

MAX_ARTIFACT_BYTES = 262144
MAX_DEPTH = 32
MAX_OBJECT_MEMBERS = 256
MAX_ARRAY_ITEMS = 256
MAX_STRING_CHARS = 8192

#: The integers that survive a round trip through an IEEE-754 double, i.e.
#: through a consumer whose JSON parser has no integer type (D-v0.3.5).
INT_MAX = 2**53 - 1
INT_MIN = -(2**53 - 1)

#: Refuse a numeric literal on its digit count before int() is ever called:
#: CPython's int-conversion limit (~4300 digits) is a crash, not a refusal.
_MAX_INT_LITERAL_CHARS = 24

#: A $defs cycle must refuse, not loop.
_MAX_REF_DEPTH = 8


# ---------------------------------------------------------------------------
# Errors (contract §6.3)

#: Closed reason vocabulary. Diagnostics are built ONLY from these codes, a
#: schema-safe path, and the fixed hint below — never from a field value, a
#: document excerpt, or an exception's text.
REASON_HINTS: dict[str, str] = {
    # Canonical JSON
    "invalid_utf8": "The file is not valid UTF-8.",
    "lone_surrogate": "A string contains an unpaired UTF-16 surrogate.",
    "bom_present": "The file starts with a byte-order mark; use UTF-8 without a BOM.",
    "duplicate_key": "An object repeats a key; keys must be unique.",
    "float_not_permitted": "Protocol v1 has no floating-point values; use an integer.",
    "non_finite_number": "NaN and Infinity are not JSON numbers.",
    "not_json": "The file is not well-formed JSON.",
    "trailing_content": "Content follows the top-level JSON value.",
    "not_an_object": "A protocol artifact's top-level value must be a JSON object.",
    "too_large": f"The document exceeds {MAX_ARTIFACT_BYTES} bytes.",
    "depth_exceeded": f"Nesting is deeper than {MAX_DEPTH} levels.",
    "too_many_members": f"An object has more than {MAX_OBJECT_MEMBERS} members.",
    "too_many_items": f"An array has more than {MAX_ARRAY_ITEMS} items.",
    "string_too_long": f"A string is longer than {MAX_STRING_CHARS} characters.",
    "integer_out_of_range": (
        f"An integer is outside the permitted range {INT_MIN}..{INT_MAX}."
    ),
    # Structure
    "unknown_field": "This object rejects fields the schema does not declare.",
    "missing_field": "A required field is absent.",
    "wrong_type": "The value has the wrong JSON type.",
    "pattern_mismatch": "The value does not match the required format.",
    "enum_mismatch": "The value is not one of the permitted values.",
    "const_mismatch": "The value is not the one permitted value.",
    "too_short": "The value is shorter than the minimum.",
    "too_long": "The value is longer than the maximum.",
    "not_unique": "The array repeats an item; items must be unique.",
    "out_of_range": "The integer is outside the permitted range.",
    # Identity / integrity
    "unknown_schema": "No such schema in the registry; see: aos protocol list",
    "unsupported_major": "This build does not support that major version.",
    "malformed_hash": "A content hash must be 64 lowercase hex characters.",
    "hash_mismatch": (
        "The content hash does not match the document body; it was modified "
        "after signing, or the hash was substituted."
    ),
    "unknown_hash_alg": f"The only known hashing version is {CONTENT_HASH_ALG}.",
    "expires_before_created": "expires_at is earlier than created_at.",
    "invalid_timestamp": "The timestamp is not a real UTC instant.",
    "version_identity_mismatch": (
        "protocol_version disagrees with the major version in the schema name."
    ),
    "binding_mismatch": "The artifact does not bind to the document it names.",
    # Filesystem
    "unsafe_input": "Only a regular file is accepted here.",
    "unreadable": "The file cannot be read.",
    "file_changed_during_read": "The file changed identity or size while being read.",
}


class ProtocolError(AosError):
    """One bounded, actionable, value-free line. Exits 1 through AosError.

    The message is assembled from a closed reason code, a schema-safe path and
    a fixed hint. No caller can smuggle a field value into it, because no
    caller passes free text.
    """

    def __init__(self, code: str, path: str = "/", *, where: str = "") -> None:
        if code not in REASON_HINTS:
            raise KeyError(f"undeclared protocol reason code: {code!r}")
        self.code = code
        self.path = path
        subject = f"{where} " if where else ""
        super().__init__(f"Refused {subject}[{code}] at {path}: {REASON_HINTS[code]}")


def _refuse(code: str, path: str = "/", *, where: str = "") -> ProtocolError:
    return ProtocolError(code, path, where=where)


# ---------------------------------------------------------------------------
# Canonical JSON v1 — serialization (contract §2)

def _assert_canonical_value(value, path: str = "/", depth: int = 1) -> None:
    """Refuse anything canonical JSON v1 cannot represent, before encoding.

    Guards the serializer's input as strictly as the parser guards its own,
    so an authored schema cannot introduce a float either.
    """
    if depth > MAX_DEPTH:
        raise _refuse("depth_exceeded", path)
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if not (INT_MIN <= value <= INT_MAX):
            raise _refuse("integer_out_of_range", path)
        return
    if isinstance(value, float):
        raise _refuse("float_not_permitted", path)
    if isinstance(value, str):
        _assert_canonical_string(value, path)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > MAX_ARRAY_ITEMS:
            raise _refuse("too_many_items", path)
        for index, item in enumerate(value):
            _assert_canonical_value(item, _join(path, str(index)), depth + 1)
        return
    if isinstance(value, dict):
        if len(value) > MAX_OBJECT_MEMBERS:
            raise _refuse("too_many_members", path)
        for key, item in value.items():
            if not isinstance(key, str):
                raise _refuse("wrong_type", path)
            _assert_canonical_string(key, path)
            _assert_canonical_value(item, _join(path, key), depth + 1)
        return
    raise _refuse("wrong_type", path)


def _assert_canonical_string(text: str, path: str) -> None:
    if len(text) > MAX_STRING_CHARS:
        raise _refuse("string_too_long", path)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        # The only way a Python str fails to encode is an unpaired surrogate.
        raise _refuse("lone_surrogate", path) from None


def serialize_canonical(value) -> bytes:
    """Canonical JSON v1 bytes: sorted keys, no whitespace, UTF-8, no newline.

    Key order is by Unicode code point — Python's native str ordering — which
    is what `sort_keys` does. This is NOT RFC 8785's UTF-16 code-unit order;
    the two differ for non-BMP keys and the divergence is declared rather than
    papered over (D-v0.3.11).
    """
    _assert_canonical_value(value)
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
        check_circular=True,
    ).encode("utf-8")


def serialize_canonical_file_bytes(value) -> bytes:
    """Canonical bytes plus the single trailing newline a file gets (§2.1).

    That newline is not part of the hashed body (§3.2).
    """
    return serialize_canonical(value) + b"\n"


def _join(path: str, segment: str) -> str:
    return f"/{segment}" if path == "/" else f"{path}/{segment}"


# ---------------------------------------------------------------------------
# Canonical JSON v1 — parsing (contract §2.2, §2.6)

def _scan_depth(text: str) -> None:
    """Refuse over-deep input BEFORE json.loads recurses into it.

    A linear, allocation-free pass over the characters. json.loads on deeply
    nested input exhausts the C stack, which is a crash (exit 2), not a
    refusal (exit 1) — so the bound has to be enforced ahead of it.
    """
    depth = 0
    in_string = False
    escaped = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
            if depth > MAX_DEPTH:
                raise _refuse("depth_exceeded")
        elif char in "}]":
            depth -= 1


def _object_pairs_hook(pairs):
    if len(pairs) > MAX_OBJECT_MEMBERS:
        raise _refuse("too_many_members")
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise _refuse("duplicate_key")
        seen.add(key)
    return dict(pairs)


def _parse_float_hook(literal: str):
    raise _refuse("float_not_permitted")


def _parse_int_hook(literal: str):
    if len(literal) > _MAX_INT_LITERAL_CHARS:
        raise _refuse("integer_out_of_range")
    value = int(literal)
    if not (INT_MIN <= value <= INT_MAX):
        raise _refuse("integer_out_of_range")
    return value


def _parse_constant_hook(name: str):
    raise _refuse("non_finite_number")


_JSON_WS = " \t\n\r"


def _walk_parsed(value, path: str = "/") -> None:
    """Bounds json's hooks cannot reach: array length, string length, and
    unpaired surrogates that arrived via a \\uD800-style escape."""
    if isinstance(value, str):
        _assert_canonical_string(value, path)
        return
    if isinstance(value, list):
        if len(value) > MAX_ARRAY_ITEMS:
            raise _refuse("too_many_items", path)
        for index, item in enumerate(value):
            _walk_parsed(item, _join(path, str(index)))
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_canonical_string(key, path)
            _walk_parsed(item, _join(path, key))


def parse_canonical(data: bytes) -> dict:
    """Bytes → a validated protocol document. Refuses per contract §2.2.

    Input need not already be canonical: a pretty-printed artifact is
    legitimate. Canonical form is how a document is *hashed*, not how it must
    be typed — that is exactly what makes the digest independent of layout.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("parse_canonical takes bytes")
    if len(data) > MAX_ARTIFACT_BYTES:
        raise _refuse("too_large")
    if data.startswith(b"\xef\xbb\xbf"):
        raise _refuse("bom_present")
    try:
        text = bytes(data).decode("utf-8", "strict")
    except UnicodeDecodeError:
        raise _refuse("invalid_utf8") from None

    _scan_depth(text)

    decoder = json.JSONDecoder(
        object_pairs_hook=_object_pairs_hook,
        parse_float=_parse_float_hook,
        parse_int=_parse_int_hook,
        parse_constant=_parse_constant_hook,
    )
    # raw_decode, not loads: it reports where the top-level value ENDS, which
    # is how trailing content earns its own reason code instead of hiding
    # inside a generic decode error. It does not skip leading whitespace.
    start = len(text) - len(text.lstrip(_JSON_WS))
    try:
        value, end = decoder.raw_decode(text, start)
    except ValueError:
        raise _refuse("not_json") from None
    if text[end:].strip(_JSON_WS):
        raise _refuse("trailing_content")
    if not isinstance(value, dict):
        raise _refuse("not_an_object")

    _walk_parsed(value)
    return value


# ---------------------------------------------------------------------------
# Content hash (contract §3)

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)


def content_digest(document: dict) -> str:
    """sha256 over the canonical body with ONLY the top-level content_sha256
    member removed (D-v0.3.6).

    A `content_sha256` key nested inside a sub-object is ordinary body content
    and stays in. There is no self-reference: what gets hashed never contains
    the hash.
    """
    body = {k: v for k, v in document.items() if k != CONTENT_HASH_FIELD}
    return hashlib.sha256(serialize_canonical(body)).hexdigest()


def _check_content_hash(document: dict, where: str) -> None:
    declared = document.get(CONTENT_HASH_FIELD)
    if content_digest(document) != declared:
        raise _refuse("hash_mismatch", f"/{CONTENT_HASH_FIELD}", where=where)


# ---------------------------------------------------------------------------
# Schema identity (contract §4.5)

_SCHEMA_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(\.[a-z0-9]+(-[a-z0-9]+)*)+$", re.ASCII)
_SCHEMA_VERSION_RE = re.compile(r"^v[1-9][0-9]*$", re.ASCII)

SUPPORTED_MAJORS = frozenset({1})
COMPAT_STATUSES = ("active", "deprecated")

REQUIRED_IDENTITIES = (
    "beast.interrupt/v1",
    "beast.result-envelope/v1",
    "beast.work-spec/v1",
)


class RegistryError(AosError):
    """A broken registry. Names the failing condition; never a value."""


def split_identity(identity: str) -> tuple[str, int]:
    """'beast.work-spec/v1' → ('beast.work-spec', 1). Strict; no aliases."""
    if not isinstance(identity, str) or identity.count("/") != 1:
        raise _refuse("unknown_schema", "/schema")
    name, version = identity.split("/", 1)
    if not _SCHEMA_NAME_RE.fullmatch(name) or not _SCHEMA_VERSION_RE.fullmatch(version):
        raise _refuse("unknown_schema", "/schema")
    return name, int(version[1:])


def make_identity(name: str, major: int) -> str:
    return f"{name}/v{major}"


# ---------------------------------------------------------------------------
# Supported / unsupported schema keywords (contract §6.1, §6.2)

SUPPORTED_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "additionalProperties",
        "enum",
        "const",
        "pattern",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minimum",
        "maximum",
        "items",
        "$defs",
        "$ref",
        "title",
        "description",
    }
)

#: Named, not ignored. A registry schema using any of these fails
#: verification, so the registry can never drift into relying on a keyword
#: this validator does not honor (D-v0.3.4).
UNSUPPORTED_KEYWORDS = (
    "$anchor",
    "$dynamicRef",
    "$id",
    "$recursiveRef",
    "$schema",
    "allOf",
    "anyOf",
    "contains",
    "contentEncoding",
    "contentMediaType",
    "default",
    "dependentRequired",
    "dependentSchemas",
    "deprecated",
    "else",
    "examples",
    "exclusiveMaximum",
    "exclusiveMinimum",
    "format",
    "if",
    "maxContains",
    "minContains",
    "multipleOf",
    "not",
    "oneOf",
    "patternProperties",
    "prefixItems",
    "propertyNames",
    "readOnly",
    "then",
    "unevaluatedItems",
    "unevaluatedProperties",
    "writeOnly",
)

SUPPORTED_TYPES = frozenset({"object", "array", "string", "integer", "boolean", "null"})

#: Segment-based on purpose: 'evidence' must not trip on 'env', but
#: 'env_vars', 'api_key' and 'session-id' must (contract §5.2).
_SECRET_NAME_RE = re.compile(
    r"(?i)(^|[._-])("
    r"secret|secrets|password|passwd|pwd|credential|credentials|"
    r"api_?key|apikey|access_?key|private_?key|token|bearer|auth|"
    r"session_?id|env|environ|environment|dsn|conn_?str|connection_?string"
    r")([._-]|$)"
)

_REF_PREFIX = "#/$defs/"


def _lint_schema(schema: dict, name: str) -> None:
    """Refuse a registry schema this engine cannot honor exactly."""
    defs = schema.get("$defs", {})
    if not isinstance(defs, dict):
        raise RegistryError(f"schema {name}: $defs must be an object")
    _lint_subschema(schema, name, defs, root=True)
    for def_name, sub in sorted(defs.items()):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", def_name):
            raise RegistryError(f"schema {name}: malformed $defs name {def_name!r}")
        _lint_subschema(sub, name, defs, root=False)


def _lint_subschema(schema, name: str, defs: dict, *, root: bool) -> None:
    if not isinstance(schema, dict):
        raise RegistryError(f"schema {name}: a subschema must be an object")

    for keyword in sorted(schema):
        if keyword in UNSUPPORTED_KEYWORDS:
            raise RegistryError(
                f"schema {name}: keyword {keyword!r} is outside the supported "
                "subset; see the U-X1 contract §6.2"
            )
        if keyword not in SUPPORTED_KEYWORDS:
            raise RegistryError(f"schema {name}: unknown keyword {keyword!r}")

    if "$ref" in schema:
        extra = set(schema) - {"$ref", "description", "title"}
        if extra:
            raise RegistryError(
                f"schema {name}: $ref must stand alone (found {sorted(extra)})"
            )
        target = schema["$ref"]
        if not isinstance(target, str) or not target.startswith(_REF_PREFIX):
            raise RegistryError(
                f"schema {name}: only local '{_REF_PREFIX}<name>' refs are supported"
            )
        if target[len(_REF_PREFIX) :] not in defs:
            raise RegistryError(f"schema {name}: dangling $ref {target!r}")
        return

    if "$defs" in schema and not root:
        raise RegistryError(f"schema {name}: $defs is permitted at the root only")

    kind = schema.get("type")
    if kind is None:
        raise RegistryError(
            f"schema {name}: every subschema needs an explicit 'type' — a "
            "missing type is not an 'any' wildcard here"
        )
    if kind not in SUPPORTED_TYPES:
        raise RegistryError(f"schema {name}: unsupported type {kind!r}")

    if "additionalProperties" in schema and schema["additionalProperties"] is not False:
        raise RegistryError(
            f"schema {name}: additionalProperties supports the literal false only"
        )
    if "uniqueItems" in schema and schema["uniqueItems"] is not True:
        raise RegistryError(
            f"schema {name}: uniqueItems supports the literal true only"
        )

    if "pattern" in schema:
        pattern = schema["pattern"]
        if not isinstance(pattern, str):
            raise RegistryError(f"schema {name}: pattern must be a string")
        if not (pattern.startswith("^") and pattern.endswith("$")):
            raise RegistryError(
                f"schema {name}: pattern {pattern!r} must be ^…$-anchored "
                "(D-v0.3.13)"
            )
        try:
            re.compile(pattern, re.ASCII)
        except re.error:
            raise RegistryError(f"schema {name}: uncompilable pattern") from None

    if kind == "object":
        if schema.get("additionalProperties") is not False:
            raise RegistryError(
                f"schema {name}: every object must set additionalProperties=false"
            )
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise RegistryError(f"schema {name}: properties must be an object")
        for prop in properties:
            if _SECRET_NAME_RE.search(prop):
                raise RegistryError(
                    f"schema {name}: property {prop!r} is a credential-shaped "
                    "name; protocol artifacts carry no secrets (contract §5.2)"
                )
        for required in schema.get("required", ()):
            if required not in properties:
                raise RegistryError(
                    f"schema {name}: required {required!r} is not a declared property"
                )
        for sub in properties.values():
            _lint_subschema(sub, name, defs, root=False)

    if kind == "array":
        if "items" not in schema:
            raise RegistryError(f"schema {name}: an array must declare items")
        _lint_subschema(schema["items"], name, defs, root=False)


# ---------------------------------------------------------------------------
# Reusable structures (contract §4.3, §5.4, §5.5)

DATA_CLASSIFICATIONS = ("public", "internal", "confidential", "restricted")
PERMITTED_DESTINATIONS = (
    "local",
    "aos-ledger",
    "human-review",
    "local-agent",
    "cloud-agent",
)
COMPENSATION_STATES = ("not_required", "pending", "applied", "failed")
INPUT_REF_KINDS = ("file", "url", "evidence", "task", "pack")
INTERRUPT_KINDS = (
    "pause",
    "question",
    "approval_request",
    "cancellation_request",
    "resume_instruction",
)
INTERRUPT_SUBJECTS = ("beast.work-spec/v1", "beast.result-envelope/v1")

RFC3339_PATTERN = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
TRACE_ID_PATTERN = r"^[0-9a-f]{32}$"
AOS_TASK_ID_PATTERN = r"^T-[0-9]{1,19}$"
IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$"
ISSUER_PATTERN = r"^[a-z][a-z0-9._-]{2,63}$"
OPAQUE_REF_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}/v[1-9][0-9]{0,3}$"
PROJECT_SCOPE_PATTERN = r"^[a-z0-9][a-z0-9._-]{0,63}$"
PROVENANCE_PATTERN = r"^(human|agent:[A-Za-z0-9._-]{1,63})$"
ERROR_CODE_PATTERN = r"^[a-z][a-z0-9_]{2,63}$"
CAPABILITY_PATTERN = r"^[a-z][a-z0-9._-]{1,63}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


def _string(*, min_len=1, max_len=256, pattern=None, description=None) -> dict:
    node: dict = {"type": "string", "minLength": min_len, "maxLength": max_len}
    if pattern is not None:
        node["pattern"] = pattern
    if description is not None:
        node["description"] = description
    return node


def _enum(values, *, description=None) -> dict:
    node: dict = {"type": "string", "enum": list(values)}
    if description is not None:
        node["description"] = description
    return node


def _array(items, *, min_items=0, max_items=MAX_ARRAY_ITEMS, unique=True) -> dict:
    node: dict = {
        "type": "array",
        "items": items,
        "minItems": min_items,
        "maxItems": max_items,
    }
    if unique:
        node["uniqueItems"] = True
    return node


def _ref(name: str) -> dict:
    return {"$ref": f"{_REF_PREFIX}{name}"}


def _common_defs() -> dict:
    """The shared structures, duplicated into each schema on purpose: a
    vendored schema must be self-contained, and $ref is local-only."""
    return {
        "Timestamp": _string(
            min_len=20,
            max_len=20,
            pattern=RFC3339_PATTERN,
            description="UTC RFC3339, second precision, literal Z.",
        ),
        "Uuid": _string(min_len=36, max_len=36, pattern=UUID_PATTERN),
        "Sha256": _string(min_len=64, max_len=64, pattern=SHA256_PATTERN),
        "AosTaskId": _string(
            min_len=3,
            max_len=21,
            pattern=AOS_TASK_ID_PATTERN,
            description="The AOS ledger's human-facing task id, e.g. T-0001. "
            "Never a runtime UUID.",
        ),
        "Issuer": _string(min_len=3, max_len=64, pattern=ISSUER_PATTERN),
        "OpaqueRef": _string(
            min_len=3,
            max_len=132,
            pattern=OPAQUE_REF_PATTERN,
            description="An opaque versioned reference to a record owned by "
            "another system. Never dereferenced here.",
        ),
        "Trace": {
            "type": "object",
            "additionalProperties": False,
            "required": ["trace_id", "correlation_id"],
            "properties": {
                "trace_id": _string(
                    min_len=32,
                    max_len=32,
                    pattern=TRACE_ID_PATTERN,
                    description="W3C Trace Context trace-id; not all zeros.",
                ),
                "correlation_id": _ref("Uuid"),
                "causation_id": _ref("Uuid"),
            },
        },
        "Scope": {
            "type": "object",
            "additionalProperties": False,
            "required": ["project"],
            "properties": {
                "project": _string(
                    min_len=1,
                    max_len=64,
                    pattern=PROJECT_SCOPE_PATTERN,
                    description="An AOS project slug (a bounded narrowing of "
                    "models.SLUG_RE).",
                ),
                "tenant": _string(min_len=1, max_len=64, pattern=PROJECT_SCOPE_PATTERN),
            },
        },
        "EvidenceRef": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "ref", "claim", "provenance"],
            "properties": {
                "kind": _enum(
                    EVIDENCE_KINDS, description="IS models.EVIDENCE_KINDS (D-v0.3.10)."
                ),
                "ref": _string(min_len=1, max_len=1024),
                "sha256": _ref("Sha256"),
                "claim": _string(min_len=1, max_len=1024),
                "provenance": _string(
                    min_len=5, max_len=70, pattern=PROVENANCE_PATTERN
                ),
            },
        },
        "BoundedError": {
            "type": "object",
            "additionalProperties": False,
            "required": ["code", "message", "retryable"],
            "properties": {
                "code": _string(min_len=3, max_len=64, pattern=ERROR_CODE_PATTERN),
                "message": _string(min_len=1, max_len=512),
                "retryable": {"type": "boolean"},
            },
        },
    }


def _envelope_properties() -> dict:
    """The identity/integrity fields every artifact carries (contract §7)."""
    return {
        "protocol_version": {
            "type": "integer",
            "minimum": 1,
            "maximum": 999,
            "description": "The major version; must equal the major in `schema`.",
        },
        "content_hash_alg": {"type": "string", "const": CONTENT_HASH_ALG},
        "content_sha256": _ref("Sha256"),
        "created_at": _ref("Timestamp"),
        "expires_at": _ref("Timestamp"),
        "issuer": _ref("Issuer"),
        "audience": _array(_ref("Issuer"), min_items=1, max_items=8),
        "scope": _ref("Scope"),
        "trace": _ref("Trace"),
        "idempotency_key": _string(
            min_len=8, max_len=128, pattern=IDEMPOTENCY_KEY_PATTERN
        ),
        "aos_task_id": _ref("AosTaskId"),
        "runtime_task_uuid": {
            "$ref": f"{_REF_PREFIX}Uuid",
            "description": "The runtime's own task UUID. A different namespace "
            "from aos_task_id, owned by a different system.",
        },
        "data_classification": _enum(DATA_CLASSIFICATIONS),
        "permitted_destinations": _array(
            _enum(PERMITTED_DESTINATIONS), min_items=1, max_items=5
        ),
    }


_ENVELOPE_REQUIRED = [
    "schema",
    "protocol_version",
    "content_hash_alg",
    "content_sha256",
    "created_at",
    "issuer",
    "audience",
    "scope",
    "trace",
    "idempotency_key",
    "aos_task_id",
    "data_classification",
    "permitted_destinations",
]


def _artifact_schema(identity: str, *, title: str, description: str,
                     properties: dict, required: list[str]) -> dict:
    node = {
        "title": title,
        "description": description,
        "type": "object",
        "additionalProperties": False,
        "required": _ENVELOPE_REQUIRED + required,
        "properties": {
            "schema": {"type": "string", "const": identity},
            **_envelope_properties(),
            **properties,
        },
        "$defs": _common_defs(),
    }
    return node


# ---------------------------------------------------------------------------
# beast.work-spec/v1 (contract §7.1)

_WORK_SPEC_V1 = _artifact_schema(
    "beast.work-spec/v1",
    title="WorkSpec v1",
    description=(
        "An inert declaration of requested work. It carries no executable "
        "field, no credential, no environment map and no approval boolean — "
        "these are unrepresentable, not merely discouraged. Nothing here "
        "grants permission to execute."
    ),
    properties={
        "work_spec_id": _ref("Uuid"),
        "goal": _string(min_len=1, max_len=4096),
        "acceptance_criteria": _array(
            _string(min_len=1, max_len=1024), min_items=1, max_items=32
        ),
        "constraints": _array(
            _string(min_len=1, max_len=1024), min_items=0, max_items=32
        ),
        "required_capabilities": _array(
            _string(min_len=2, max_len=64, pattern=CAPABILITY_PATTERN),
            min_items=0,
            max_items=16,
        ),
        "inputs": _array(
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["ref_kind", "ref"],
                "properties": {
                    "ref_kind": _enum(INPUT_REF_KINDS),
                    "ref": _string(min_len=1, max_len=1024),
                    "sha256": _ref("Sha256"),
                    "note": _string(min_len=1, max_len=512),
                },
                "description": "A DECLARED reference. Validation never opens, "
                "stats, fetches or hashes what it names.",
            },
            min_items=0,
            max_items=32,
        ),
        "expected_result": {
            "type": "object",
            "additionalProperties": False,
            "required": ["result_schema", "evidence_kinds", "min_evidence_count"],
            "properties": {
                "result_schema": {"type": "string", "const": "beast.result-envelope/v1"},
                "evidence_kinds": _array(
                    _enum(EVIDENCE_KINDS), min_items=1, max_items=len(EVIDENCE_KINDS)
                ),
                "min_evidence_count": {"type": "integer", "minimum": 0, "maximum": 32},
            },
        },
        "policy_refs": {
            "type": "object",
            "additionalProperties": False,
            "required": [],
            "properties": {
                "policy_ref": _ref("OpaqueRef"),
                "approval_ref": {
                    "$ref": f"{_REF_PREFIX}OpaqueRef",
                    "description": "A reference to an approval record owned by "
                    "another system. NOT a claim that approval was granted; "
                    "this protocol has no field that can make that claim.",
                },
                "budget_ref": _ref("OpaqueRef"),
            },
        },
        "retry": {
            "type": "object",
            "additionalProperties": False,
            "required": ["max_attempts"],
            "properties": {
                "max_attempts": {"type": "integer", "minimum": 1, "maximum": 10},
                "deadline_at": _ref("Timestamp"),
            },
        },
    },
    required=["work_spec_id", "goal", "acceptance_criteria", "expected_result"],
)


# ---------------------------------------------------------------------------
# beast.result-envelope/v1 (contract §7.2)

_RESULT_ENVELOPE_V1 = _artifact_schema(
    "beast.result-envelope/v1",
    title="Result Envelope v1",
    description=(
        "An inert proof-carrying report about work, bound to the exact "
        "WorkSpec content hash. It does not mark a task done, end a run, "
        "create evidence, authorize spend, claim approval, mutate SQLite or "
        "trigger execution. Import and replay are deferred (D-v0.3.8)."
    ),
    properties={
        "result_id": _ref("Uuid"),
        "work_spec_id": _ref("Uuid"),
        "work_spec_sha256": {
            "$ref": f"{_REF_PREFIX}Sha256",
            "description": "The exact content hash of the WorkSpec this reports on.",
        },
        "outcome": _enum(
            RUN_OUTCOMES, description="IS models.RUN_OUTCOMES (D-v0.3.10)."
        ),
        "retryable": {"type": "boolean"},
        "attempt": {"type": "integer", "minimum": 1, "maximum": 10},
        "evidence": _array(_ref("EvidenceRef"), min_items=0, max_items=32),
        "errors": _array(_ref("BoundedError"), min_items=0, max_items=8),
        "compensation": {
            "type": "object",
            "additionalProperties": False,
            "required": ["state"],
            "properties": {
                "state": _enum(COMPENSATION_STATES),
                "ref": _ref("OpaqueRef"),
            },
        },
    },
    required=[
        "result_id",
        "work_spec_id",
        "work_spec_sha256",
        "outcome",
        "retryable",
        "attempt",
        "evidence",
        "errors",
    ],
)


# ---------------------------------------------------------------------------
# beast.interrupt/v1 (contract §7.3)

_INTERRUPT_V1 = _artifact_schema(
    "beast.interrupt/v1",
    title="Interrupt v1",
    description=(
        "An inert boundary artifact that REQUESTS a pause, question, "
        "approval, cancellation or resume. It executes none of them: an "
        "approval_request asks, it never answers."
    ),
    properties={
        "interrupt_id": _ref("Uuid"),
        "subject_schema": _enum(INTERRUPT_SUBJECTS),
        "subject_sha256": {
            "$ref": f"{_REF_PREFIX}Sha256",
            "description": "The exact content hash of the bound artifact.",
        },
        "kind": _enum(INTERRUPT_KINDS),
        "reason": _string(min_len=1, max_len=2048),
        "resume_instruction_ref": _ref("OpaqueRef"),
    },
    required=["interrupt_id", "subject_schema", "subject_sha256", "kind", "reason"],
)


# ---------------------------------------------------------------------------
# Registry (contract §4)

@dataclass(frozen=True)
class SchemaEntry:
    name: str
    major: int
    status: str
    schema: dict
    canonical_bytes: bytes
    digest: str

    @property
    def identity(self) -> str:
        return make_identity(self.name, self.major)

    @property
    def artifact_relpath(self) -> str:
        return f"{self.name}/v{self.major}.schema.json"


#: The definitions. Module-level literals frozen at import: there is no
#: register(), no plugin hook, no environment variable and no workspace path
#: that adds a schema (contract §4.7). A workspace is untrusted input, and a
#: registry loaded from one would let a document supply the schema that
#: approves it.
_DEFINITIONS: tuple[tuple[str, int, str, dict], ...] = (
    ("beast.work-spec", 1, "active", _WORK_SPEC_V1),
    ("beast.result-envelope", 1, "active", _RESULT_ENVELOPE_V1),
    ("beast.interrupt", 1, "active", _INTERRUPT_V1),
)


def build_registry(definitions) -> MappingProxyType:
    """Validate definitions and freeze them into an immutable mapping.

    Every refusal in contract §4.4 lives here, so the same checks that guard
    the shipped registry are the ones a test can drive with a broken one.
    """
    entries: dict[str, SchemaEntry] = {}
    by_name: dict[str, set[int]] = {}
    folded: dict[str, str] = {}

    for name, major, status, schema in definitions:
        if not _SCHEMA_NAME_RE.fullmatch(name):
            raise RegistryError(f"malformed schema name {name!r}")
        if not isinstance(major, int) or isinstance(major, bool) or major < 1:
            raise RegistryError(f"malformed major version for {name!r}")
        if major not in SUPPORTED_MAJORS:
            raise RegistryError(
                f"unsupported major version v{major} for {name!r}; this build "
                f"supports {sorted(SUPPORTED_MAJORS)}"
            )
        if status not in COMPAT_STATUSES:
            raise RegistryError(f"unknown compatibility status for {name!r}")

        identity = make_identity(name, major)
        if identity in entries:
            raise RegistryError(f"duplicate name/version pair {identity!r}")
        if major in by_name.get(name, set()):
            raise RegistryError(f"duplicate schema name {name!r}")

        # Ambiguous aliasing: two identities that differ only by case would
        # both answer to the same human reference. There is no alias table,
        # no 'latest', no default-major resolution — one identity, one entry.
        fold = identity.casefold()
        if fold in folded:
            raise RegistryError(
                f"ambiguous aliasing: {identity!r} collides with {folded[fold]!r}"
            )
        folded[fold] = identity

        _lint_schema(schema, identity)
        if schema.get("properties", {}).get("schema", {}).get("const") != identity:
            raise RegistryError(f"schema {identity!r} does not pin its own identity")

        canonical = serialize_canonical(schema)
        entries[identity] = SchemaEntry(
            name=name,
            major=major,
            status=status,
            schema=schema,
            canonical_bytes=canonical,
            digest=hashlib.sha256(canonical).hexdigest(),
        )
        by_name.setdefault(name, set()).add(major)

    for identity in REQUIRED_IDENTITIES:
        if identity not in entries:
            raise RegistryError(f"missing schema {identity!r}")

    return MappingProxyType({k: entries[k] for k in sorted(entries)})


#: Immutable. MappingProxyType refuses assignment, so a caller cannot swap in
#: a schema at runtime.
REGISTRY = build_registry(_DEFINITIONS)


def list_entries() -> list[SchemaEntry]:
    """Every entry, ordered by identity. Stable across runs and platforms."""
    return [REGISTRY[k] for k in sorted(REGISTRY)]


def get_entry(identity: str) -> SchemaEntry:
    """Look up by FULL identity. A bare name is refused, so no alias can ever
    resolve to 'whatever the newest major happens to be'."""
    name, major = split_identity(identity)
    entry = REGISTRY.get(make_identity(name, major))
    if entry is not None:
        return entry
    known = {e.name for e in list_entries()}
    if name in known:
        raise _refuse("unsupported_major", "/schema")
    raise _refuse("unknown_schema", "/schema")


def verify_registry_digests() -> list[str]:
    """Recompute every entry's canonical bytes and digest from its definition."""
    problems = []
    for entry in list_entries():
        canonical = serialize_canonical(entry.schema)
        if canonical != entry.canonical_bytes:
            problems.append(f"{entry.identity}: canonical bytes drifted")
        if hashlib.sha256(canonical).hexdigest() != entry.digest:
            problems.append(f"{entry.identity}: schema digest mismatch")
    return problems


# ---------------------------------------------------------------------------
# Validation engine (contract §6)

def _type_ok(value, kind: str) -> bool:
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "null":
        return value is None
    return False


def _resolve(schema: dict, defs: dict) -> dict:
    """Follow local $refs, bounded — a $defs cycle refuses instead of looping."""
    seen = 0
    while "$ref" in schema:
        seen += 1
        if seen > _MAX_REF_DEPTH:
            raise RegistryError("schema $ref expansion exceeded its bound")
        schema = defs[schema["$ref"][len(_REF_PREFIX) :]]
    return schema


def validate_instance(value, schema: dict, defs: dict, path: str, where: str) -> None:
    """Structural validation over the supported subset only (contract §6.1).

    Fails at the FIRST error in a deterministic traversal: document order for
    unknown fields, then schema-declared order for everything else. Never dict
    iteration order, never set order.
    """
    schema = _resolve(schema, defs)
    kind = schema["type"]
    if not _type_ok(value, kind):
        raise _refuse("wrong_type", path, where=where)

    if "const" in schema and value != schema["const"]:
        raise _refuse("const_mismatch", path, where=where)
    if "enum" in schema and value not in schema["enum"]:
        raise _refuse("enum_mismatch", path, where=where)

    if kind == "string":
        if "minLength" in schema and len(value) < schema["minLength"]:
            raise _refuse("too_short", path, where=where)
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise _refuse("too_long", path, where=where)
        if "pattern" in schema and not re.compile(
            schema["pattern"], re.ASCII
        ).fullmatch(value):
            # fullmatch, not search: `^…$` in Python's re would otherwise
            # still admit a trailing newline (D-v0.2.3, D-v0.3.13).
            raise _refuse("pattern_mismatch", path, where=where)
        return

    if kind == "integer":
        if "minimum" in schema and value < schema["minimum"]:
            raise _refuse("out_of_range", path, where=where)
        if "maximum" in schema and value > schema["maximum"]:
            raise _refuse("out_of_range", path, where=where)
        return

    if kind == "array":
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise _refuse("too_short", path, where=where)
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise _refuse("too_long", path, where=where)
        if schema.get("uniqueItems") is True:
            seen: list[bytes] = []
            for item in value:
                key = serialize_canonical(item)
                if key in seen:
                    raise _refuse("not_unique", path, where=where)
                seen.append(key)
        for index, item in enumerate(value):
            validate_instance(
                item, schema["items"], defs, _join(path, str(index)), where
            )
        return

    if kind == "object":
        properties = schema.get("properties", {})
        # Document order: the parse hook preserves it.
        for key in value:
            if key not in properties:
                # The path names the PARENT, never the attacker's key.
                raise _refuse("unknown_field", path, where=where)
        for required in schema.get("required", ()):
            if required not in value:
                raise _refuse("missing_field", _join(path, required), where=where)
        for prop, subschema in properties.items():
            if prop in value:
                validate_instance(
                    value[prop], subschema, defs, _join(path, prop), where
                )
        return


def _parse_instant(text: str, path: str, where: str) -> datetime:
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise _refuse("invalid_timestamp", path, where=where) from None


def _check_semantics(document: dict, entry: SchemaEntry) -> None:
    """The cross-field invariants a schema cannot express (contract §7.4)."""
    where = entry.identity

    if document["protocol_version"] != entry.major:
        raise _refuse("version_identity_mismatch", "/protocol_version", where=where)

    created = _parse_instant(document["created_at"], "/created_at", where)
    if "expires_at" in document:
        expires = _parse_instant(document["expires_at"], "/expires_at", where)
        if expires < created:
            raise _refuse("expires_before_created", "/expires_at", where=where)
    deadline = document.get("retry", {}).get("deadline_at")
    if deadline is not None:
        _parse_instant(deadline, "/retry/deadline_at", where)

    if document["trace"]["trace_id"] == "0" * 32:
        raise _refuse("pattern_mismatch", "/trace/trace_id", where=where)

    _check_content_hash(document, where)


def validate_document(document: dict) -> SchemaEntry:
    """A parsed document → its registry entry, or a bounded refusal.

    Order is chosen for actionability: identity first (nothing else can be
    checked without knowing the schema), then the two integrity fields that
    have their own precise reason codes, then structure, then semantics.
    """
    if not isinstance(document, dict):
        raise _refuse("not_an_object")
    if "schema" not in document:
        raise _refuse("missing_field", "/schema")
    entry = get_entry(document["schema"])
    where = entry.identity

    # Ahead of structural validation, so these report `unknown_hash_alg` and
    # `malformed_hash` rather than a generic const/pattern mismatch.
    if document.get("content_hash_alg") != CONTENT_HASH_ALG:
        raise _refuse("unknown_hash_alg", "/content_hash_alg", where=where)
    declared = document.get(CONTENT_HASH_FIELD)
    if not isinstance(declared, str) or not _HEX64_RE.fullmatch(declared):
        raise _refuse("malformed_hash", f"/{CONTENT_HASH_FIELD}", where=where)

    validate_instance(document, entry.schema, entry.schema["$defs"], "/", where)
    _check_semantics(document, entry)
    return entry


def validate_bytes(data: bytes) -> tuple[dict, SchemaEntry]:
    document = parse_canonical(data)
    return document, validate_document(document)


def verify_binding(artifact: dict, referent: dict) -> None:
    """Prove an artifact binds to the exact document it names.

    Both documents must already be valid. The referent's digest is recomputed
    from its body — never trusted from its own content_sha256 field, which is
    the thing an attacker would edit.
    """
    identity = artifact.get("schema")
    if identity == "beast.result-envelope/v1":
        declared = artifact["work_spec_sha256"]
        expected_schemas = ("beast.work-spec/v1",)
        field = "/work_spec_sha256"
    elif identity == "beast.interrupt/v1":
        declared = artifact["subject_sha256"]
        expected_schemas = (artifact["subject_schema"],)
        field = "/subject_sha256"
    else:
        raise _refuse("binding_mismatch", "/schema")

    where = identity
    if referent.get("schema") not in expected_schemas:
        raise _refuse("binding_mismatch", field, where=where)
    if content_digest(referent) != declared:
        raise _refuse("binding_mismatch", field, where=where)
    # A matching hash with a mismatched id would mean two documents disagree
    # about which WorkSpec they are; refuse rather than pick one.
    if identity == "beast.result-envelope/v1":
        if artifact.get("work_spec_id") != referent.get("work_spec_id"):
            raise _refuse("binding_mismatch", "/work_spec_id", where=where)


# ---------------------------------------------------------------------------
# Filesystem safety (contract §9)

def _object_kind(mode: int) -> str:
    if stat.S_ISLNK(mode):
        return "a symlink"
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


def safe_name(path) -> str:
    """A basename for diagnostics. An absolute path is a fact about the
    human's machine and goes in no error line this unit emits."""
    return Path(path).name or "<file>"


def read_artifact_bytes(path) -> bytes:
    """Read a FILE input under contract §9. Never writes; never follows.

    lstat, never stat: a symlink must be SEEN as a symlink rather than
    followed to whatever it points at. The size bound is applied before the
    read, and the open descriptor is re-checked against the lstat result so a
    file swapped between check and read is refused rather than read.
    """
    path = Path(path)
    name = safe_name(path)
    try:
        st = os.lstat(path)
    except OSError:
        raise _refuse("unreadable", "/", where=name) from None

    if not stat.S_ISREG(st.st_mode):
        raise _refuse("unsafe_input", "/", where=f"{name} ({_object_kind(st.st_mode)})")
    if st.st_size > MAX_ARTIFACT_BYTES:
        raise _refuse("too_large", "/", where=name)

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        raise _refuse("unreadable", "/", where=name) from None
    try:
        fst = os.fstat(fd)
        if (
            not stat.S_ISREG(fst.st_mode)
            or (fst.st_dev, fst.st_ino) != (st.st_dev, st.st_ino)
            or fst.st_size != st.st_size
        ):
            raise _refuse("file_changed_during_read", "/", where=name)
        chunks: list[bytes] = []
        total = 0
        while total <= MAX_ARTIFACT_BYTES:
            # One byte past the bound: a file that GREW since lstat is
            # refused rather than allowed to exhaust memory.
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
    except OSError:
        raise _refuse("unreadable", "/", where=name) from None
    finally:
        os.close(fd)

    data = b"".join(chunks)
    if len(data) > MAX_ARTIFACT_BYTES:
        raise _refuse("too_large", "/", where=name)
    return data


def load_artifact_file(path) -> tuple[dict, SchemaEntry]:
    return validate_bytes(read_artifact_bytes(path))


# ---------------------------------------------------------------------------
# The checked-in projection (contract §4, D-v0.3.3)

def registry_index() -> dict:
    """The deterministic content of protocols/registry.json."""
    return {
        "canonical_json": CANONICAL_JSON,
        "content_hash_alg": CONTENT_HASH_ALG,
        "registry_version": REGISTRY_VERSION,
        "schemas": [
            {
                "identity": entry.identity,
                "name": entry.name,
                "major": entry.major,
                "status": entry.status,
                "sha256": entry.digest,
                "path": entry.artifact_relpath,
            }
            for entry in list_entries()
        ],
    }


def source_artifacts_dir() -> Path | None:
    """The checked-in protocols/ directory, or None when there is no source
    checkout — which is the normal case inside aos.pyz (D-v0.3.2)."""
    candidate = Path(__file__).resolve().parent.parent / ARTIFACT_DIRNAME
    try:
        return candidate if candidate.is_dir() else None
    except OSError:
        return None


def expected_source_artifacts() -> dict[str, bytes]:
    """relpath → exact bytes. The projection is a pure function of the
    embedded definitions, so a drifted checkout cannot hide."""
    artifacts = {REGISTRY_FILENAME: serialize_canonical_file_bytes(registry_index())}
    for entry in list_entries():
        artifacts[entry.artifact_relpath] = entry.canonical_bytes + b"\n"
    return artifacts


def verify_source_artifacts(root: Path) -> list[str]:
    """Compare protocols/ to the embedded definitions, byte-for-byte."""
    problems = []
    for relpath, expected in sorted(expected_source_artifacts().items()):
        path = root / relpath
        try:
            actual = path.read_bytes()
        except OSError:
            problems.append(f"{relpath}: missing or unreadable")
            continue
        if actual != expected:
            problems.append(f"{relpath}: does not match the embedded definition")
    known = set(expected_source_artifacts())
    for path in sorted(root.rglob("*.json")):
        relpath = path.relative_to(root).as_posix()
        if relpath not in known:
            problems.append(f"{relpath}: not a projection of any embedded schema")
    return problems
