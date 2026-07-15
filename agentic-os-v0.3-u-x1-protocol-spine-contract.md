# Agentic OS v0.3 — U-X1: WorkSpec and Result Envelope protocol spine

Status: pinned before implementation. Baseline `dcecfee`, branch
`v0.3-u-x1-protocol-spine`.

This unit builds the local, versioned protocol spine that later Agentic OS and
runtime integration can vendor by digest. It defines inert artifacts and the
bounded, deterministic machinery that validates them. It connects to nothing.

---

## 0. Scope

### 0.1 In scope

- Agentic OS canonical JSON v1 (a named local format, not RFC 8785).
- One content-hash algorithm over canonical bytes.
- An embedded, immutable schema registry plus deterministic checked-in
  projections under `protocols/`.
- `beast.work-spec/v1`, `beast.result-envelope/v1`, `beast.interrupt/v1`.
- Shared identity, evidence and integrity structures.
- A bounded deterministic validator over a deliberately small schema subset.
- Read-only CLI inspection and validation.
- Script / module / zipapp byte parity.

### 0.2 Explicitly NOT in scope (deferred to later bounded units)

- Any AICompany connection or cross-repository vendoring.
- Invoking agents; executing work of any kind.
- Importing Result Envelopes into SQLite; replay; ledger mutation.
- memory-v2; agent/skill/tool manifests; remote replay.
- Networking, MCP/A2A, orchestration, autonomy, CI, releases.

### 0.3 Untouched by this unit

Database schema and `SCHEMA_VERSION`; the migration registry; memory tables,
commands and behavior; task/run/evidence mutation semantics; backup/restore;
the hook protocol; dropfile ingest; exports and mirror generation; runtime
power-mode semantics **except** classifying the five new protocol leaves;
AICompany.

---

## 1. Decisions

- **D-v0.3.1 — Agentic OS owns the initial protocol registry.** The registry
  ships in this repository, not in AICompany and not in a shared package. AOS is
  the system of record; the protocol spine is part of that record. Consumers
  vendor it by digest later; nothing in U-X1 reaches across a repository
  boundary.

- **D-v0.3.2 — The Python embedded definitions are canonical.** `aos.pyz` is one
  file with no data directory, so a registry that lived in `protocols/*.json`
  would make the zipapp non-functional. The embedded Python definitions in
  `agentic_os/protocols.py` are the single source of truth.

- **D-v0.3.3 — Checked-in JSON artifacts are deterministic projections.**
  `protocols/` exists so the schemas are reviewable in a diff and vendorable by
  a future consumer. It is a *projection*, never a second editable source:
  `protocol verify-registry` and a focused test compare it byte-for-byte against
  the embedded definitions. Editing `protocols/` without editing the Python
  fails both.

- **D-v0.3.4 — No general-purpose JSON Schema claim.** The validator supports an
  explicit, small, enumerated subset (§6.1). Every unsupported keyword is named
  (§6.2), and a keyword outside the supported set is refused *in the registry
  itself* at verification time. A partial implementation that silently ignores
  `oneOf` is worse than no claim at all, because it validates less than a reader
  believes it does.

- **D-v0.3.5 — No floats in protocol v1.** Floating point has no canonical
  decimal form that survives a round trip across languages, so a float field
  would make the content hash unstable by construction. Numbers are integers in
  the safe IEEE-754 range only (§2.5). Durations, budgets and sizes are integers
  in explicit units.

- **D-v0.3.6 — The content hash excludes exactly its own field.** The hash is
  computed over the canonical serialization of the document with the *top-level*
  `content_sha256` member removed, and nothing else removed (§3). No recursive
  self-hashing, no placeholder value, no field ordering dependence.

- **D-v0.3.7 — Protocol validation is inert and read-only.** Validation parses
  bytes and compares them to a schema. It never executes, imports, evals,
  resolves, fetches, opens or stats anything an artifact *references*. All five
  leaves are `read_only` in the U-E2 matrix and open no SQLite connection.

- **D-v0.3.8 — AICompany vendoring and cross-repository replay are deferred.**
  A Result Envelope is a report, not an instruction. Nothing in U-X1 marks a
  task done, ends a run, creates evidence or authorizes spend.

- **D-v0.3.9 — v1 reserves no extension object.** The contract permits one
  bounded extension object; v1 declines it. Every schema rejects unknown
  top-level fields with no exceptions. An extension object in v1 would be an
  unvalidated pocket inside a signed body — forward compatibility is bought by
  minting `/v2`, which the registry is built to carry.

- **D-v0.3.10 — Existing vocabularies are reused exactly or not at all.** The
  Result Envelope `outcome` enum IS `models.RUN_OUTCOMES` and evidence `kind` IS
  `models.EVIDENCE_KINDS`, asserted by test against the production tuples rather
  than copied. Protocol-only concepts (data classification, permitted
  destinations, compensation state) get new closed vocabularies. No existing
  domain vocabulary is broadened.

- **D-v0.3.11 — Key ordering is by Unicode code point, and this is stated, not
  claimed as RFC 8785.** RFC 8785 sorts by UTF-16 code unit. The two orders
  differ for non-BMP keys. AOS sorts by code point because that is what Python's
  native string comparison does, and a hand-rolled UTF-16 re-implementation
  would be a correctness risk taken purely to earn a compliance badge this unit
  does not claim. Schema property names are ASCII, where the orders coincide.

- **D-v0.3.12 — Generation lives in `tools/`, never in the CLI.** The CLI is
  read-only by classification, so it cannot regenerate `protocols/`.
  `tools/gen_protocols.py` writes the projection, mirroring the existing
  `tools/build_zipapp.py` convention, and is excluded from the zipapp because
  `tools/` is not under the package allowlist.

- **D-v0.3.13 — Schema patterns anchor with `^…$` and are applied with
  `fullmatch`, a deliberate, narrow departure from D-v0.2.3.** The existing rule
  ("anchor with `\Z`, never `$`") exists because Python's `$` also matches
  *before* a trailing newline, so `^slug$` would accept `"proj\n"`. That hole is
  closed here by a different mechanism: `re.fullmatch` requires the pattern to
  consume the entire string, so `fullmatch(r"^abc$", "abc\n")` fails — `$`
  consumes nothing and the `\n` is left over. The reason to prefer `$` is that
  these patterns are *exported* in `protocols/*.schema.json` for future
  consumers, and `\Z` is not ECMA-262 — a JavaScript-side validator would read
  it as a literal `Z` and silently validate the wrong grammar. `^…$` means
  exactly fullmatch in ECMA-262. So: `$` in the artifact, `fullmatch` in the
  engine, D-v0.2.3's guarantee intact. The registry lint enforces the anchors,
  and a focused test proves the trailing-newline case still refuses.

---

## 2. Agentic OS canonical JSON v1

Name: **`aos-canonical-json/v1`**. This is a local format. It is *not* claimed
to be RFC 8785 / JCS compliant; §2.7 records the known divergences.

### 2.1 Encoding

- UTF-8, no BOM. A leading U+FEFF is a refusal, not a stripped character.
- No insignificant whitespace: separators are exactly `,` and `:`.
- Object keys sorted ascending by Unicode code point (D-v0.3.11).
- Array order preserved exactly.
- Strings escape `"` and `\`; C0 controls use `\b \t \n \f \r` where defined and
  `\u00XX` otherwise. All other characters are emitted literally as UTF-8.
- A document written to a file ends with exactly one `\n`. That newline is NOT
  part of the hashed body (§3.2).

### 2.2 Refusals at parse

- Duplicate keys in any object.
- `NaN`, `Infinity`, `-Infinity`.
- Any floating-point value, including `1.0` and `1e2`.
- Any value that is not `null`, boolean, integer, string, array or object.
- Lone Unicode surrogates (in raw bytes or via `\uD800`-style escapes).
- Invalid UTF-8.
- Trailing content after the top-level value.
- A top-level value that is not an object.

### 2.3 No silent normalization

User strings are never trimmed, case-folded, Unicode-normalized or
newline-normalized. A string round-trips byte-identically. This is a hashing
requirement, not a preference: normalization would make two documents that a
human calls "the same" hash differently depending on which one was written.

### 2.4 Bounds

| Bound | Value | Enforced |
|---|---|---|
| Total artifact bytes | 262144 (256 KiB) | before parse |
| Nesting depth | 32 | before parse (byte pre-scan, §2.6) |
| Object members | 256 per object | during parse |
| Array items | 256 per array | during parse |
| String characters | 8192 (keys and values) | during parse |
| Integer | −(2⁵³−1) … 2⁵³−1 | during parse |

Depth counts the top-level object as depth 1.

### 2.5 Integer range

`-(2**53 - 1) <= n <= 2**53 - 1`. This is the range that survives a round trip
through an IEEE-754 double, i.e. through a consumer whose JSON parser has no
integer type. A value outside it is refused rather than silently rounded by
someone else's parser later.

### 2.6 Refusing before unbounded allocation or recursion

- **Bytes**: the size bound is checked before the bytes are decoded.
- **Depth**: a linear, allocation-free pre-scan over the raw bytes counts
  bracket depth outside of strings and refuses above 32 *before* `json.loads`
  recurses. `json.loads` on deeply nested input would otherwise exhaust the C
  stack, which is a crash (exit 2), not a refusal (exit 1).
- **Members/items/strings/integers**: enforced inside the parse hooks, as each
  container closes, not after a full document is materialized.

### 2.7 Known divergences from RFC 8785

1. Key ordering is by code point, not UTF-16 code unit (D-v0.3.11).
2. Floats are refused entirely; RFC 8785 specifies a float serialization.
3. Duplicate keys are refused; RFC 8785 defers to the JSON parser.
4. The top-level value must be an object.

---

## 3. Content hash

Name: **`aos-sha256-canonical/v1`**, carried in the required field
`content_hash_alg` as a `const`.

### 3.1 Algorithm

1. Parse the document under §2. Any refusal there ends it.
2. Remove **exactly** the top-level member `content_sha256`. Remove nothing
   else. A `content_sha256` key nested inside any sub-object is ordinary body
   content and is NOT removed.
3. Serialize the remaining document with §2 canonical rules → bytes.
4. `sha256(bytes)`, lowercase hex.

### 3.2 Exact included and excluded bytes

- **Included**: the complete canonical serialization of the document minus the
  top-level `content_sha256` member — every other field, including `schema`,
  `protocol_version`, `content_hash_alg`, all identity, all metadata, all
  payload.
- **Excluded**: the top-level `content_sha256` key and its value, and the single
  trailing newline of an exported file. Nothing else.

There is no self-reference: the body being hashed never contains the hash.

### 3.3 Detection duties

| Attack | Caught by |
|---|---|
| Changed payload | body bytes differ → digest mismatch |
| Changed schema identity | `schema` is in the body → mismatch |
| Changed metadata | metadata is in the body → mismatch |
| Removed field | required-field error, else body differs → mismatch |
| Substituted hash (a valid digest from another document) | mismatch |
| Malformed hash | `^[0-9a-f]{64}\Z` pattern refusal |
| Unknown hashing version | `content_hash_alg` const refusal |

### 3.4 Never hash referenced files

`sha256` fields inside an artifact are **declared** references. The validator
never opens, stats or hashes what they name. Hashing a path an untrusted
artifact chose is a read primitive handed to the artifact's author.

---

## 4. Schema registry

### 4.1 Shape

One immutable mapping in `agentic_os/protocols.py`. Each entry carries:

- exact schema name (`beast.work-spec`);
- major version (integer);
- canonical schema bytes (the deterministic §2 serialization);
- SHA-256 schema digest (lowercase hex over those bytes);
- compatibility status.

Schema identity is `"<name>/v<major>"`. Compatibility status vocabulary:
`("active", "deprecated")`. All three v1 schemas are `active`.

### 4.2 Contents

| Identity | Status |
|---|---|
| `beast.work-spec/v1` | active |
| `beast.result-envelope/v1` | active |
| `beast.interrupt/v1` | active |

### 4.3 Reusable structures

Carried as `$defs` inside each schema (§6.1 allows local `$ref` only), covering:
protocol identity; AOS task reference; runtime task reference; trace /
correlation / causation identity; idempotency key; issuer; audience; project or
tenant scope; timestamps; data classification; permitted destinations; evidence
reference with integrity hash; bounded error.

### 4.4 Registry refusals

Verified at import time and by `protocol verify-registry`:

- duplicate schema name;
- duplicate name/version pair;
- schema digest mismatch against the canonical bytes;
- missing schema (a required identity absent);
- unsupported major version;
- malformed schema name (§4.5);
- ambiguous aliasing (§4.6);
- mutable runtime registration (§4.7).

### 4.5 Name grammar

`^[a-z][a-z0-9]*(\.[a-z0-9]+(-[a-z0-9]+)*)+\Z` for the name;
`^v[1-9][0-9]*\Z` for the version segment. Identity is `name + "/" + version`.
`protocol show` requires the full identity: a bare name is refused, so no alias
can ever resolve to "whatever the newest major happens to be".

### 4.6 Ambiguous aliasing

Two entries alias if their identities differ but collide after ASCII case
folding. Refused. There is no alias table, no `latest`, no default-major
resolution — one identity, one entry.

### 4.7 No mutable runtime registration

There is no `register()`, no plugin hook, no environment variable and no
workspace path that adds a schema. Definitions are module-level literals frozen
at import. Schemas are never dynamically imported and never loaded from a
workspace: a workspace is untrusted input, and a registry loaded from one would
let a document supply the schema that approves it.

---

## 5. Schema design rules

Every schema in the registry:

- requires an exact schema identity (`schema` is a `const`);
- rejects unknown top-level fields (`additionalProperties: false`, no reserved
  extension object — D-v0.3.9);
- bounds every string and every collection;
- forbids secrets by structure (closed objects) and by naming (§5.2);
- carries `content_sha256`;
- carries `protocol_version` (an integer major that must equal the major in
  `schema` — §7.2);
- carries `created_at`;
- uses UTC RFC3339 timestamps with a literal `Z` (§5.1);
- validates `created_at <= expires_at` where expiry exists;
- carries `issuer`, `audience`, `scope`, `idempotency_key` and trace identity;
- distinguishes AOS task IDs from runtime task UUIDs (§5.3);
- uses evidence *references* and hashes, never embedded rows or dumps.

### 5.1 Timestamps

`^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$` — second precision,
UTC, literal `Z`. No offsets, no fractional seconds, no `z`. This is exactly the
shape `utils.utc_now_iso()` emits, so an AOS timestamp is a valid protocol
timestamp by construction. Semantically validated as a real instant.

### 5.2 Secret prohibition

Structural: every object is closed, so no key that is not named in the schema
can appear anywhere in the document.

Naming: a registry lint refuses any *schema property name* matching
`(?i)(secret|password|passwd|credential|api[_-]?key|access[_-]?key|private[_-]?key|token|bearer|session[_-]?id|env|environ)`.
The lint runs over the registry at verification time, so the prohibition is a
property of the schemas themselves and cannot be introduced by a future edit
that adds an `api_key` field.

Not claimed: content scanning. A `goal` string can contain any text a human
types. What is guaranteed is that validation diagnostics never echo field
values (§6.3), so a planted secret cannot leak *through this unit*.

### 5.3 Identity separation

- `aos_task_id` — `^T-[0-9]{1,19}$`. The ledger's human-facing id.
- `runtime_task_uuid` — lowercase canonical UUID, optional.

Distinct fields, disjoint grammars. A UUID in `aos_task_id` is refused; a `T-`
id in `runtime_task_uuid` is refused. They are different namespaces owned by
different systems, and one field carrying both would make provenance
unrecoverable at exactly the moment it matters.

**The protocol grammar is a strict narrowing of `ids.parse_id()`, not a copy.**
The ledger's parser is deliberately lenient at the CLI boundary: it upper-cases
the prefix and strips surrounding whitespace, so `t-0002`, `T-0002 ` and
`\tT-0002\n` all parse to task 2. The protocol refuses all three and accepts
only `T-0002`. That direction is the safe one: on a wire format every id must
have exactly one spelling, because two spellings of one id are two idempotency
keys, two correlation targets and two audit trails. Narrowing stays compatible
with the ledger (every id the protocol accepts, `parse_id` accepts identically);
broadening would not. A focused test pins both directions.

### 5.4 Identity grammars

| Field | Grammar |
|---|---|
| `trace_id` | 32 lowercase hex, not all zeros (W3C Trace Context) |
| `correlation_id` | lowercase canonical UUID |
| `causation_id` | lowercase canonical UUID, optional |
| `idempotency_key` | `^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$` |
| `issuer` | `^[a-z][a-z0-9._-]{2,63}$` |
| `audience` | array, 1–8 issuer-shaped strings |
| opaque versioned ref | `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}/v[1-9][0-9]{0,3}$` |

### 5.5 Closed protocol vocabularies

- `data_classification`: `public | internal | confidential | restricted`
- `permitted_destinations`: `local | aos-ledger | human-review | local-agent |
  cloud-agent` (array, 1–5, unique)
- `outcome`: **is** `models.RUN_OUTCOMES`
- evidence `kind`: **is** `models.EVIDENCE_KINDS`
- `compensation.state`: `not_required | pending | applied | failed`
- input `ref_kind`: `file | url | evidence | task | pack`

---

## 6. Validation engine

Standard library only. Deterministic. Bounded.

### 6.1 Supported subset — exhaustive

`type` (`object|array|string|integer|boolean|null`), `properties`, `required`,
`additionalProperties` (**only** the literal `false`), `enum`, `const`,
`pattern`, `minLength`, `maxLength`, `minItems`, `maxItems`, `uniqueItems`
(**only** the literal `true`), `minimum`, `maximum`, `items` (a single
subschema), `$defs`, `$ref` (**only** local `#/$defs/<name>`).

`title` and `description` are permitted and ignored as annotations.

Semantics that differ from JSON Schema, stated rather than glossed:

- `pattern` uses **fullmatch** semantics with `re.ASCII`, not `search`. Every
  pattern in the registry is additionally required to be `^…$`-anchored
  (D-v0.3.13), so the exported artifact carries the same grammar an ECMA-262
  validator would read.
- `minimum`/`maximum` apply to integers only (there are no floats).
- `$ref` resolves only within the same schema document and is bounded to 8
  levels of expansion, so a `$defs` cycle refuses instead of looping.
- A missing `type` is a registry lint error, not an "any" wildcard.

### 6.2 Unsupported keywords — exhaustive, and refused in the registry

`anyOf`, `oneOf`, `allOf`, `not`, `if`, `then`, `else`, `patternProperties`,
`dependentSchemas`, `dependentRequired`, `propertyNames`, `contains`,
`minContains`, `maxContains`, `prefixItems`, `unevaluatedProperties`,
`unevaluatedItems`, `format`, `multipleOf`, `exclusiveMinimum`,
`exclusiveMaximum`, `number`, `$id`, `$schema`, `$anchor`, `$dynamicRef`,
`$recursiveRef`, remote/absolute `$ref`, `default`, `examples`, `readOnly`,
`writeOnly`, `deprecated`, `contentEncoding`, `contentMediaType`.

These are not "ignored". A registry schema containing any of them fails
verification, so the registry cannot drift into using a keyword the validator
does not honor.

### 6.3 Error discipline

Every validation error exits through `AosError` (exit 1) as **one bounded line**
containing:

- a schema-safe field path (`/evidence/3/kind`) built from schema-declared
  property names and array indices only;
- a reason code from a closed vocabulary;
- no field values, no document excerpts, no secrets, no arbitrary exception
  text, no absolute paths (a file is named by basename only).

Errors are deterministically ordered: document order for structure, then
schema-declared property order — never dict iteration order or set order. When
several errors exist, the first in that order is reported.

Reason codes (closed): `invalid_utf8`, `lone_surrogate`, `bom_present`,
`duplicate_key`, `float_not_permitted`, `non_finite_number`, `not_json`,
`trailing_content`, `not_an_object`, `too_large`, `depth_exceeded`,
`too_many_members`, `too_many_items`, `string_too_long`, `integer_out_of_range`,
`unknown_field`, `missing_field`, `wrong_type`, `pattern_mismatch`,
`enum_mismatch`, `const_mismatch`, `too_short`, `too_long`, `not_unique`,
`out_of_range`, `unknown_schema`, `unsupported_major`, `malformed_hash`,
`hash_mismatch`, `unknown_hash_alg`, `expires_before_created`,
`invalid_timestamp`, `version_identity_mismatch`, `binding_mismatch`,
`unsafe_input`, `unreadable`, `file_changed_during_read`.

### 6.4 Name grammar of the schema-safe field path

A path is `/` for the document root, otherwise `/` plus segments joined by `/`,
where each segment is a schema-declared property name or a decimal array index.
Segments are never taken from the *document* — an unknown field is reported at
its parent's path with the `unknown_field` code, never by echoing the attacker's
chosen key back onto the terminal.

---

## 7. Artifacts

All three carry the common envelope: `schema`, `protocol_version`,
`content_hash_alg`, `content_sha256`, `created_at`, `expires_at?`, `issuer`,
`audience`, `scope`, `trace`, `idempotency_key`, `aos_task_id`,
`runtime_task_uuid?`, `data_classification`, `permitted_destinations`.

### 7.1 `beast.work-spec/v1` — an inert declaration of requested work

Adds: `work_spec_id` (UUID); `goal` (1–4096); `acceptance_criteria` (1–32
bounded strings); `constraints` (0–32); `required_capabilities` (0–16);
`inputs` (0–32 declared references: `ref_kind`, `ref`, `sha256?`, `note?`);
`expected_result` (`evidence_kinds`, `min_evidence_count`, `result_schema`
const); `policy_refs` (`policy_ref?`, `approval_ref?`, `budget_ref?` — opaque
versioned references); `retry` (`max_attempts` 1–10, `deadline_at?`).

**Must not contain, and structurally cannot** (every object is closed, so these
are unrepresentable rather than merely discouraged): executable Python or shell
fields; database connection strings; credentials; arbitrary environment-variable
maps; approval booleans that claim authorization; embedded files or database
dumps; implicit permission to execute.

`policy_refs.approval_ref` is an opaque *reference* to an approval record owned
by another system. It is not a claim that approval was granted. There is no
`approved: true` in this protocol, in any artifact, by design.

Validation never executes or imports content.

### 7.2 `beast.result-envelope/v1` — an inert proof-carrying report

Adds: `result_id` (UUID); `work_spec_sha256` (64 hex — **binds to the exact
WorkSpec content hash**); `work_spec_id` (UUID); `outcome`
(`models.RUN_OUTCOMES`); `retryable` (bool); `attempt` (1–10); `evidence` (0–32
references: `kind` from `models.EVIDENCE_KINDS`, `ref`, `sha256?`, `claim`,
`provenance`); `errors` (0–8 bounded errors: `code`, `message` ≤512,
`retryable`); `compensation?` (`state`, `ref?`).

**A Result Envelope does not**: mark an AOS task done; end a run; create
evidence; authorize spend; claim approval; mutate SQLite; trigger execution. It
is a report *about* work, produced by a party whose claims are not yet trusted.
Import and replay into the ledger are explicitly deferred (D-v0.3.8).

Binding is verified by `protocols.verify_binding(envelope, work_spec)`, a
pure-Python comparison of two already-parsed documents. `protocol validate FILE`
sees one file and therefore checks binding *structurally* only — it cannot
confirm a hash it was not given. That limit is stated, not implied.

### 7.3 `beast.interrupt/v1` — an inert boundary artifact

Adds: `interrupt_id` (UUID); `subject_schema` (const-restricted to
`beast.work-spec/v1` or `beast.result-envelope/v1`); `subject_sha256` (64 hex —
**binds to an exact artifact hash**); `kind` (`pause | question |
approval_request | cancellation_request | resume_instruction`); `reason`
(1–2048); `resume_instruction_ref?` (opaque versioned reference).

It represents a request. It does not execute cancellation, approval or
resumption. An `approval_request` asks; it never answers.

### 7.4 Cross-field semantic invariants

1. `content_sha256` verifies against the recomputed body digest (§3).
2. `content_hash_alg` is the known algorithm.
3. The major in `schema` equals `protocol_version`.
4. `created_at` and `expires_at` are real instants; `created_at <= expires_at`.
5. `retry.deadline_at`, when present, is a real instant.
6. `trace_id` is not all zeros.
7. `aos_task_id` and `runtime_task_uuid` stay in their own grammars (§5.3).

---

## 8. CLI

Five read-only leaves under the canonical parser:

| Command | Behavior |
|---|---|
| `aos protocol list` | stable ordered identity, major, digest, status. No workspace, no database. `--json` available. |
| `aos protocol show SCHEMA` | the exact canonical checked-in schema representation, byte-identical to `protocols/<name>/v<major>.schema.json`. Full identity required. |
| `aos protocol validate FILE` | syntax, bounds, schema identity, content hash, semantic invariants. Success prints only `<identity> <digest>`. Failure leaves stdout empty. |
| `aos protocol digest FILE` | parses and validates bounded JSON, prints the canonical content digest. Never rewrites the source. |
| `aos protocol verify-registry` | verifies embedded definitions; also compares checked-in artifacts when running from a source checkout. |

`verify-registry` inside a standalone zipapp verifies the embedded registry and
reports clearly that source-artifact comparison is unavailable. It does **not**
fail merely because a source checkout is absent — a zipapp legitimately has no
`protocols/` directory, and failing there would train people to ignore it.

### 8.1 Classification and isolation

All five are `read_only` in the U-E2 `COMMAND_POLICY` matrix. None opens SQLite,
creates `power.json`, creates temporary workspace state, emits ledger events or
requires an initialized workspace.

---

## 9. Filesystem safety

For every `FILE` input:

- `os.lstat` first — a symlink is seen as a symlink, never followed. Symlink,
  directory, FIFO, socket, block/character device and every other non-regular
  object is refused.
- Size is bounded *before* reading (§2.4).
- Opened with `O_NOFOLLOW` where the platform provides it; the open descriptor
  is `fstat`ed and its device/inode/size compared against the `lstat` result, so
  a file swapped between check and read is refused rather than read. At most
  `MAX+1` bytes are read, so a file that grows during the read is refused rather
  than exhausting memory.
- The input is never overwritten; no adjacent output file is ever created.
- References *inside* the artifact are never followed (§3.4).

Diagnostics name a file by **basename only**. An absolute path is a fact about
the human's machine, and it goes in no error line this unit emits.

---

## 10. Package and zipapp

`agentic_os/protocols.py` is a `.py` file under the package, so the existing
`runtime_sources()` allowlist in `tools/build_zipapp.py` includes it
automatically. **No packaging change is required**, which is the allowlist
design working as intended.

The checked-in `protocols/*.json` files are NOT in the archive and are not
needed for `list` / `show` / `validate` / `digest` (D-v0.3.2). No tests,
fixtures, workspaces, databases, backups or unrelated files enter the archive.

Proven: `aos.pyz` outside the repository with `PYTHONPATH` cleared lists
schemas, shows a schema, validates a valid artifact, rejects a tampered
artifact, and computes digests identical to the script and module entrypoints.

---

## 11. File boundary

New:
- `agentic-os-v0.3-u-x1-protocol-spine-contract.md`
- `agentic_os/protocols.py`
- `protocols/registry.json`
- `protocols/beast.work-spec/v1.schema.json`
- `protocols/beast.result-envelope/v1.schema.json`
- `protocols/beast.interrupt/v1.schema.json`
- `tests/test_v03_protocol_spine.py`
- `tools/gen_protocols.py` — **deviation from the expected-files list**,
  justified by D-v0.3.12: the projection needs a writer, and the CLI is
  read-only by classification.

Modified:
- `agentic_os/cli.py` (parser + five handlers)
- `agentic_os/power.py` (five classification entries)
- `README.md`, `TROUBLESHOOTING.md`, `DECISIONS.md`

No packaging test is modified: archive membership is already proven by the
existing allowlist test, and `protocols.py` needs no exception.

---

## 12. Verification

- Registry holds exactly the three required v1 schemas; ordering and digests
  stable; checked-in files match embedded definitions byte-for-byte.
- Canonical ordering/whitespace deterministic; duplicate keys, floats, NaN,
  Infinity, invalid UTF-8 and lone surrogates refuse; every bound enforces.
- Unknown schema, unsupported major, unknown field, missing field refuse;
  timestamp and identity invariants enforce; AOS and runtime identities distinct.
- Valid WorkSpec verifies; Result Envelope binds to the exact WorkSpec hash;
  Interrupt binds to an exact artifact hash.
- Payload/metadata tampering, hash substitution and malformed hashes refuse.
- Validation executes nothing and follows no reference.
- Unsafe input objects refuse; diagnostics echo no planted secret or value.
- All five leaves classified `read_only`; no SQLite, no workspace, no
  `power.json`.
- Script/module/zipapp outputs and exit codes match; zipapp works outside the
  checkout with `PYTHONPATH` cleared.
- The existing 953 tests and all U-E2 behavior keep passing.
