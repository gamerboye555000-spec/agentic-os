# Agentic OS v0.4 — U-E6 flight recorder, deterministic replay, and incident forensics (architecture contract)

Wave 0 architecture freeze. Branch `v0.4-u-e6-flight-recorder-replay`, worktree
`/home/daksh/Projects/agentic-os-u-e6`, baseline
`55e72c8c298dfb3c1577d0425faa31c31019f8f2` (= HEAD = `origin/main` =
`milestone/v0.4-u-e1-observability-foundation^{}`).

Architecture only. No production code, tests, DDL, migrations, fixtures, CLI
handlers, power entries, protocol schemas or README prose ship in this commit.
Exactly two repository paths are written: `DECISIONS.md` and this file.

---

## 0. Authority and scope

U-E6 is a new unit. It does not supersede any landed contract. Three landed
contracts and their decision series grant the authority U-E6 exercises:

* **U-W3 §1.1** — transition-policy version 2, `workflow_attempts`,
  `workflow_checkpoints`, compensation, restoration, and the retry/recovery
  boundary.
* **U-E1 §0.1** — the observability projection, its trace-root invariant, the
  four member exception for `work_spec_document.trace.*`, and the reservation
  of flight recording, deterministic replay, incident reconstruction,
  re-simulation, payload capture, time-travel query, and retention policy to
  U-E6 by name (D-v0.4.139).
* **U-W2.2 §4.2** — the store's judgment authority: existence, digest
  verification, history–snapshot agreement, compare-and-swap win, and nothing
  else.

U-E6 ships what those clauses reserved and nothing else.

---

## 1. Replay semantics — frozen definitions

The following terms are **mutually exclusive** and **exhaustively defined** for
this contract. No implementation may conflate them.

| Term | Meaning | Authoritative input | Output claim |
|------|---------|---------------------|--------------|
| **integrity verification** | Recomputes every digest in the ledger, compares stored digests to recomputed ones, and reports every divergence, unreadable row, and bound violation. | `workflows`, `workflow_events`, `workflow_commands`, `workflow_intents`, `workflow_receipts`, `workflow_facts`, `workflow_attempts`, `workflow_checkpoints`, `journal` — every row exactly as stored. | A verification report listing every `divergent`, `unreadable`, `truncated`, and `clock_inconsistent` finding. **Never** asserts "the workflow succeeded" or "the workflow failed". |
| **workflow history folding** | The pure reducer function `decide` applied sequentially to the accepted commands' `workflow_events` in `seq` order, producing the final snapshot. This is what `workflow_store._rebuild` already does. | `workflow_events` for a single workflow, in `seq` order. | The derived snapshot (state, revision, attempts_used, runtime_task_uuid, etc.). **Never** asserts what a runtime task did or what an external system observed. |
| **snapshot rebuild** | Materializing the snapshot at a specific `event_seq` or `checkpoint_seq` by folding events up to that sequence. | `workflow_events` up to a boundary sequence; optionally a checkpoint document for the `record_restore` path. | The snapshot at that boundary. **Never** claims the workflow *was* in that state at wall-clock time — only that the ledger *folds to* that state at that sequence. |
| **flight-record reconstruction** | Assembling a complete, self-contained record of one workflow execution from admission to terminal state (or current state), including every command, event, intent, receipt, fact, attempt, checkpoint, and the work spec document. | All eight workflow tables + `work_spec_document` + relevant `journal` rows for the workflow identity. | A **flight record bundle** (deterministic serialization, §8) that an operator can archive, transfer, and feed to deterministic replay. The bundle **contains no secrets** (§9) and **no model outputs** (§9). |
| **incident reconstruction** | A structured document that correlates the flight record with the observability projection, the verification report, and the operator's question (e.g., "why did this workflow enter `compensating`?"). | Flight record bundle + observability projection + verification report + operator-provided context (optional). | An incident reconstruction document that **cites evidence by row identity** (table, row_id, digest) and **never infers causation** the ledger does not support. |
| **deterministic replay** | Re-executing the pure reducer `decide` over a flight record's event sequence in an isolated environment, producing byte-identical snapshots at every step. The replay **executes no side effects**, **issues no intents**, **delivers no receipts**, **records no facts**, and **mutates no ledger**. | A flight record bundle (or a workflow_id + ledger read access). | A replay trace: the sequence of snapshots, the refusal reasons at each step (if any), and a boolean `byte_identical_to_ledger` per step. **Never** produces a new `workflow_id`, **never** writes to `aos.db`, **never** becomes execution. |
| **re-simulation** | Deterministic replay with **one or more controlled substitutions**: a different `work_spec_document` (same digest or different), a different `retry.max_attempts`, a different transition-policy version (v1 vs v2), or a synthetic receipt sequence. Every substitution is **explicitly declared** in the re-simulation request. | A flight record bundle + a substitution set. | A re-simulation trace, labeled with every substitution applied. **Never** claims the original workflow *would have* done anything; only that *under these substitutions* the reducer produces this trace. |
| **counterfactual / time-travel query** | A read-only query over the ledger or a flight record bundle that answers "what was the snapshot at sequence N?", "which commands were accepted between seq A and B?", "what would the snapshot be if event E were removed?" — where the "what would" is **explicitly re-simulation** under a declared substitution. | Ledger or flight record + query parameters. | A query result. **Never** mutates, **never** asserts historical authority for the counterfactual branch. |

**Non-goals (explicitly reserved or forbidden):**
- Cross-process timeline reconstruction (AOS never observed it).
- Model output reconstruction (U-E1 intentionally refuses to parse it; D-v0.4.137).
- External runtime task state reconstruction (private runtime plane; D-v0.4.103).
- Payload/body parsing beyond digests and byte lengths (D-v0.4.137).
- Any write path into `aos.db`.
- Any network collector, daemon, background watcher, or cloud telemetry service.

---

## 2. Capability census

### ALREADY LANDED (U-E6 reuses without modification)

| Capability | Source | Authority |
|------------|--------|-----------|
| `workflow_store._rebuild` — pure history folding | `workflow_store.py:_rebuild` | U-W2.2 |
| `workflow_engine.decide` — pure reducer | `workflow_engine.py:decide` | U-W2.1 |
| Checkpoint persistence (`workflow_checkpoints` table) | `db.py:WORKFLOW_CHECKPOINTS_DDL`, `workflow_store.py:_insert_checkpoint` | U-W3 |
| Attempt ledger (`workflow_attempts` table) | `db.py:WORKFLOW_ATTEMPTS_DDL`, `workflow_store.py` | U-W3 |
| Verification (`observability.verify`) — digest recomputation, divergence reporting | `observability.py:verify` | U-E1 |
| Observability projection (`project_workflow`, `project_metrics`, `project_journal`) | `observability.py` | U-E1 |
| Trace root identity (`trace.trace_id` from `work_spec_document`) | `observability.py:resolve_trace_root` | U-E1 |
| CLI leaves: `observe trace`, `observe metrics`, `observe verify`, `observe export` | `cli.py:cmd_observe_*` | U-E1 |
| Deep preflight bound checks (`bound_violations_for`) | `observability.py:bound_violations_for` | U-E1 |
| Journal projection (read-only) | `observability.py:project_journal` | U-E1 |

### PARTIALLY PRESENT (mechanisms exist but do not satisfy U-E6 semantics)

| Mechanism | Gap |
|-----------|-----|
| `workflow_store` replay status | Returns `replay` for duplicate commands but **does not** produce a replay trace, does not verify byte-identity, and does not support re-simulation. |
| Checkpoint documents | Stored verbatim with digest, but **no CLI or API** to retrieve, verify, or export a single checkpoint in isolation. |
| Flight record assembly | No code assembles all eight tables + work_spec + journal into a single self-contained bundle. |
| Deterministic serialization | `protocols.serialize_canonical` exists but no **flight-record-specific** envelope schema with version, integrity manifest, and secret-free guarantee. |
| Incident document generation | No code correlates flight record, observability, and verification into a structured incident report. |
| Re-simulation harness | No code accepts a substitution set and runs `decide` over a modified event sequence. |
| Time-travel query | No CLI or API for "snapshot at seq N" or "what if event E were removed". |

### ABSENT / RESERVED (U-E6 must add)

| Capability | Why not derivable from existing rows |
|------------|--------------------------------------|
| **Flight record bundle format** | No single artifact today contains: work_spec_document, all workflow tables for one workflow, relevant journal rows, and an integrity manifest — all secret-free. Existing exports (`observe export`) are observability projections, not flight records. |
| **Deterministic replay engine** | `decide` is pure but no harness runs it over a flight record bundle in isolation, verifies byte-identity at each step, and produces a replay trace without touching `aos.db`. |
| **Re-simulation harness** | No code accepts explicit substitutions and runs the reducer over them. |
| **Incident reconstruction document** | No code correlates evidence across tables by row identity and produces a structured report. |
| **Time-travel query CLI/API** | No surface for "snapshot at seq N" or counterfactual queries. |
| **Retention policy for flight records** | No mechanism to expire, archive, or purge flight record bundles; U-E1 explicitly has no retention policy (D-v0.4.133). |
| **Secret scanning for flight records** | Flight records must never contain secrets (prompts, goals, model outputs, checkpoint payloads). No secret scan runs on bundle creation. |

---

## 3. Threat and failure analysis

| Threat | U-E6 mitigation |
|--------|-----------------|
| Malformed/tampered historical rows | `verify` already recomputes every digest; flight record bundle includes integrity manifest; replay refuses on any divergence. |
| Missing rows | `verify` reports `unreadable`; flight record bundle lists every expected table and row count; replay fails closed if a required row is absent. |
| Duplicate rows/events | `verify` detects duplicate `content_sha256` or `seq`; replay processes events in `seq` order — duplicates produce a divergence at the second occurrence. |
| Impossible ordering | `seq` is PRIMARY KEY in `workflow_events`; `checkpoint_seq` is UNIQUE per attempt; replay follows `seq` order strictly. |
| Corrupted checkpoints | Checkpoint digest is recomputed on every read (`_checkpoint_row_payload`); restore eligibility requires recomputed digest match (D-v0.4.108). |
| Forged timestamps | `created_at` / `recorded_at` are stored as text; U-E1 treats them as opaque RFC3339 seconds; replay **never** uses wall-clock time. |
| Foreign/untrusted payloads | Flight record bundle **excludes** `report_document`, `workflow_intents.document`, `workflow_receipts.document`, `workflow_facts.document`, `workflow_checkpoints.document` bodies — only digests and byte lengths are included (D-v0.4.137). |
| Secret-bearing payloads | Bundle creation runs `secretscan` on every included byte; any secret scan hit **fails the bundle creation** (hard refusal). |
| Replay of side-effecting actions | Replay **never** issues intents, delivers receipts, records facts, or mutates ledger. It only runs `decide`. |
| Replay accidentally becoming execution | Replay runs in a **separate process** or **isolated function** with no database write access; the CLI verb is `replay` (not `submit`). |
| Model output treated as historical authority | Model outputs are **never in the flight record** (excluded by D-v0.4.137). Re-simulation substitutions are **declared**, not inferred. |
| Retention removing evidence | Flight record bundles are **explicit operator artifacts**; they are not subject to ledger retention. Ledger retention is unchanged. |
| Cross-process ordering claims | U-E6 **never** asserts cross-process ordering. The trace root is the work_spec `trace_id`; foreign traces are links only (D-v0.4.122). |
| U-E1 identifiers used as authority | Flight record selection is by **workflow_id** (integer primary key), never by `trace_id` or `span_id`. |
| Incident evidence whose source disappeared | Incident document cites **row identities and digests**; if the ledger row is later purged, the incident document still records what it cited. |
| Schema evolution and old-ledger replay | Flight record bundle includes `schema_version` and `protocol_version`; replay engine validates compatibility and refuses if the reducer cannot process the event vocabulary. |

---

## 4. Storage decision

**U-E6 requires NO new tables in `aos.db`.**

The flight record is a **derived, exportable artifact**, not a stored table. Every byte in a flight record bundle is reconstructible from the eight existing workflow tables + `work_spec_document` + relevant `journal` rows. Adding a `flight_records` table would:
- Duplicate data already authoritative in the ledger.
- Create a second write path (bundle creation) that must stay consistent with the ledger.
- Require its own retention policy, migration story, and integrity mechanism.

Instead, U-E6 introduces:

1. **A deterministic flight record bundle format** (`aos.flight-record/v1`) — a single JSON document (canonical serialization) containing:
   - `schema_version`: `"7"` (the ledger schema version at bundle creation)
   - `protocol_version`: `"1"` (the flight record protocol version)
   - `workflow_id`: integer
   - `work_spec_digest`: the `work_spec_sha256` from the workflow row (NOT the document body)
   - `workflow_events`: array of event rows (verbatim, with `content_sha256`)
   - `workflow_commands`: array of command rows
   - `workflow_intents`: array of intent rows (document **excluded**, only `content_sha256` and `payload_bytes`)
   - `workflow_receipts`: array of receipt rows (document **excluded**, only `receipt_sha256` and `content_sha256`)
   - `workflow_facts`: array of fact rows (document **excluded**, only `document_sha256` and `content_sha256`)
   - `workflow_attempts`: array of attempt rows
   - `workflow_checkpoints`: array of checkpoint rows (document **excluded**, only `document_sha256` and `payload_bytes`)
   - `journal_rows`: relevant journal rows for this workflow (action, entity, entity_id, row_id, payload members per §9.4)
   - `integrity_manifest`: object mapping `table_name` -> `{row_count, sha256_of_concatenated_content_sha256s}`
   - `created_at`: RFC3339 instant of bundle creation — **stored only in the wrapper metadata, not in the canonical replay payload** (§9.1)
   - `secret_scan`: `{scanned: true, findings: 0}` — hard requirement

2. **A replay engine** — a pure function `replay(flight_record_bundle, substitutions=[])` that:
   - Validates the bundle's integrity manifest.
   - Reads the `work_spec_digest`, fetches the `work_spec_document` from the ledger (or from the substitution set if provided), and validates it against the digest.
   - Runs `decide` sequentially over `workflow_events` in `seq` order.
   - At each step, compares the derived snapshot to the next event's `resulting_revision` (for accepted commands) or `expected_revision` (for refused commands).
   - Returns a replay trace: `{steps: [...], byte_identical: bool, divergence_at_seq: int | null}`.

3. **A re-simulation harness** — `resimulate(flight_record_bundle, substitutions)` where each substitution is one of:
   - `work_spec_document`: replacement (must pass secret scan AND match `work_spec_digest` unless `allow_digest_mismatch: true` is explicitly declared).
   - `retry.max_attempts`: integer override.
   - `transition_policy_version`: 1 or 2.
   - `synthetic_receipts`: array of receipt objects to inject at specific `seq` positions.
   - `removed_event_seq`: integer (removes that event from the sequence).
   Every substitution is recorded in the re-simulation trace output.

4. **An incident reconstruction document format** (`aos.incident-report/v1`) — a JSON document that:
   - References the flight record bundle by its content digest.
   - Includes the observability projection for the workflow.
   - Includes the verification report for the workflow.
   - Contains operator-provided context (optional, free-text, **never** parsed by AOS).
   - Contains a structured evidence index: every claim cites `table`, `row_id`, `content_sha256`.

5. **CLI surfaces** (minimal, read-only or derived_write, no new power modes):
   - `aos flight-record create WF-n --out FILE` — creates the bundle, runs secret scan, writes file. **Classified `derived_write`** (writes filesystem, never ledger).
   - `aos flight-record verify FILE` — verifies bundle integrity manifest. **Classified `read_only`**.
   - `aos replay FILE` — runs deterministic replay, prints replay trace. **Classified `read_only`**.
   - `aos replay FILE --resimulate SUBSTITUTION_FILE` — runs re-simulation. **Classified `read_only`** (reads substitution file, no ledger writes).
   - `aos incident create WF-n --out FILE` — creates incident reconstruction document. **Classified `derived_write`**.
   - `aos incident export WF-n --out DIR` — exports flight record + incident report + observability + verification as a directory bundle. **Classified `derived_write`**.

All surfaces are **read-only with respect to `aos.db`**. They write only operator-requested output files (`derived_write`).

---

## 5. Exact external boundary

### Public operator surfaces — exact command leaves

| Verb | Parser key | Arguments | Output | Power class | Recovery | Deep preflight | Eco |
|------|------------|-----------|--------|-------------|----------|----------------|-----|
| `aos flight-record create <WF-id> --out <file>` | `("flight-record", "create")` | workflow id, output file path | `aos.flight-record/v1` JSON | `DERIVED_WRITE` | BLOCKED | runs | deferred |
| `aos flight-record verify <file>` | `("flight-record", "verify")` | bundle file | verification report (stdout) | `READ_ONLY` | ALLOWED | runs | immediate |
| `aos replay <file>` | `("replay",)` | bundle file | replay trace (stdout) | `READ_ONLY` | ALLOWED | runs | immediate |
| `aos replay <file> --resimulate <subst-file>` | `("replay",)` with flag `--resimulate` | bundle file, substitution file | re-simulation trace (stdout) | `READ_ONLY` | ALLOWED | runs | immediate |
| `aos incident create <WF-id> --out <file>` | `("incident", "create")` | workflow id, output file | `aos.incident-report/v1` JSON | `DERIVED_WRITE` | BLOCKED | runs | deferred |
| `aos incident export <WF-id> --out <dir>` | `("incident", "export")` | workflow id, output directory | directory with flight record, incident report, observability, verification | `DERIVED_WRITE` | BLOCKED | runs | deferred |

**Command grammar notes:**
- `replay --resimulate` is a **flag on the same command leaf** `("replay",)`, not a separate subcommand. The power key is identical.
- `flight-record` and `incident` are two-level groups: `("flight-record", "create")`, `("flight-record", "verify")`, `("incident", "create")`, `("incident", "export")`.

### Non-surfaces (explicitly NOT added)

- No `aos flight-record list`, `aos flight-record delete`, `aos flight-record retain`.
- No daemon, watcher, background job, or scheduled bundle creation.
- No network endpoint, gRPC, HTTP, or cloud export.
- No `aos replay` that writes to `aos.db`.
- No `aos incident` that modifies ledger state.
- No new power modes or power entries beyond the six above.

---

## 6. Deterministic serialization rules

1. **Canonical JSON** — `protocols.serialize_canonical` (sorted keys, no whitespace, UTF-8).
2. **Array order** — every array in the bundle is ordered by the table's natural key:
   - `workflow_events`: by `seq` ascending.
   - `workflow_commands`: by `id` ascending.
   - `workflow_intents`: by `id` ascending.
   - `workflow_receipts`: by `id` ascending.
   - `workflow_facts`: by `id` ascending.
   - `workflow_attempts`: by `attempt_no` ascending.
   - `workflow_checkpoints`: by `checkpoint_seq` ascending.
   - `journal_rows`: by `row_id` ascending.
3. **Object member order** — sorted lexicographically by key (canonical JSON).
4. **Integer bounds** — all integers serialized as JSON numbers (no string encoding).
5. **Digest fields** — lower-case hex, no `0x` prefix.
6. **Timestamps** — RFC3339 second-precision, UTC, `Z` suffix.
7. **Protocol versioning** — top-level `protocol_version` string; a bundle with unknown `protocol_version` is refused by `verify` and `replay`.

---

## 7. Secret and privacy handling

**Flight record bundles MUST contain zero secrets.**

Creation pipeline:
1. Assemble bundle from ledger rows (including `work_spec_digest` only, NOT the document body).
2. Run `secretscan.scan(bytes)` on the **entire canonical JSON byte sequence**.
3. If `findings > 0`: **refuse bundle creation** with `secret_in_flight_record`, list finding types (not values).
4. Write bundle to file **only if scan passes**.

**Privacy / data-classification / hostile-content handling:**

- The `work_spec_document` is **NOT included verbatim** in the bundle. Only its digest (`work_spec_sha256`) is included in the canonical replay payload.
- The WorkSpec schema (`beast.work-spec/v1`) contains: `goal` (free-text up to 4096 chars), `acceptance_criteria` (array of strings), `constraints` (array of strings), `inputs` (declared references), `expected_result` (schema + evidence kinds), `policy_refs` (opaque refs), `retry` (max_attempts, deadline_at), plus `trace.*` and `data_classification`. **None of these fields are included in the canonical replay payload.**
- Replay **fetches the WorkSpec from the ledger by digest** at replay time (or from the substitution set for re-simulation). This ensures:
  - No privacy-sensitive project prose (goals, criteria, constraints) leaves the ledger in a flight record.
  - No hostile/instruction-shaped content in those fields can be exported.
  - The bundle remains portable — the WorkSpec is reconstructible from the ledger or the substitution.
- The **canonical replay payload** (the JSON that is integrity-manifested and byte-identical) contains ONLY:
  - `schema_version`, `protocol_version`, `workflow_id`, `work_spec_digest`
  - All eight workflow table rows (with document bodies excluded per D-v0.4.137)
  - `journal_rows` (closed vocabulary only)
  - `integrity_manifest`
- The **wrapper metadata** (`created_at`, `secret_scan` result) is written to the file **outside** the canonical payload. The file format is:
  ```json
  {
    "canonical_payload": { ... },     // integrity-manifested, byte-identical
    "wrapper": {                       // not integrity-manifested, not replayed
      "created_at": "2024-01-15T10:30:00Z",
      "secret_scan": {"scanned": true, "findings": 0}
    }
  }
  ```
- `verify` and `replay` read the `canonical_payload` only. The wrapper is ignored for integrity and replay purposes.

---

## 8. Integrity and provenance model

| Layer | Mechanism |
|-------|-----------|
| **Row-level** | Every stored row carries `content_sha256` (recomputed on every read). |
| **Table-level** | Integrity manifest: `sha256(concat(sorted(content_sha256)))` per table. |
| **Bundle-level (canonical payload)** | Bundle content digest = `sha256(canonical_json_bytes_of_canonical_payload)`. |
| **Provenance** | Canonical payload carries `schema_version`, `protocol_version`, `workflow_id`, `work_spec_digest`. Wrapper carries `created_at`, `secret_scan` result. |
| **Verification** | `flight-record verify` recomputes every `content_sha256`, verifies table manifests, verifies bundle digest of canonical payload. |
| **Replay** | Replay fetches `work_spec_document` by `work_spec_digest`, runs `decide` sequentially over `workflow_events` in `seq` order; any divergence from stored `resulting_revision` / `expected_revision` reported as `divergence_at_seq`. |

---

## 9. Retention behavior

- **Ledger retention**: Unchanged. U-W3 and U-E1 define no retention policy for workflow tables; U-E6 adds none.
- **Flight record bundles**: Operator-managed files. No automatic creation, no automatic deletion, no TTL.
- **Incident reports**: Operator-managed files. No automatic creation, no automatic deletion.
- **Replay/re-simulation traces**: Ephemeral stdout output unless operator redirects to file.

---

## 10. Backward compatibility

- Flight record bundles are **versioned** (`protocol_version`). A future `v2` bundle format can coexist; `verify` and `replay` will dispatch on version.
- Ledger schema version is recorded in the bundle (`schema_version`). If a future migration changes the ledger schema, old bundles remain valid **only if the current reducer can process their event vocabulary**.
- **No reducer version archive/loader exists.** The current reducer (`decide`) handles both policy v1 and v2 histories via the `policy_version` field in the snapshot. If a bundle's `schema_version` implies a vocabulary the current reducer cannot process (e.g., a future schema v8 with new event types), `replay` **refuses** with `reducer_vocabulary_mismatch`.
- No migration is required for U-E6. Schema version stays `"7"`.

---

## 11. Failure semantics

| Operation | Failure mode | Exit code |
|-----------|--------------|-----------|
| `flight-record create` | Workflow not found | 2 |
| `flight-record create` | Secret scan hit | 3 (no file written) |
| `flight-record create` | I/O error writing file | 4 |
| `flight-record verify` | Bundle integrity failure | 1 (report on stdout) |
| `flight-record verify` | Unknown protocol_version | 2 |
| `replay` | Bundle integrity failure | 1 |
| `replay` | Divergence at seq N | 0 (trace reports `divergence_at_seq: N`, `byte_identical: false`) |
| `replay` | Reducer refuses an event the ledger accepted | 0 (trace reports refusal reason) |
| `replay` | WorkSpec not found by digest | 2 |
| `resimulate` | Substitution file malformed | 2 |
| `resimulate` | Substitution produces invalid WorkSpec | 3 |
| `resimulate` | WorkSpec digest mismatch without `allow_digest_mismatch: true` | 3 |
| `incident create` | Workflow not found | 2 |
| `incident create` | Flight record creation fails | bubbles up |
| `incident export` | Directory not empty / not a directory | 2 |

**No operation ever mutates `aos.db`.**

---

## 12. Test strategy

### Mutation / adversarial test requirements (mandatory)

1. **Tampered bundle** — modify one `content_sha256` in a valid bundle; `verify` must detect; `replay` must refuse.
2. **Secret in WorkSpec** — inject a secret-shaped string into a WorkSpec `goal` field; ledger admits it (warn); `flight-record create` must refuse (scans canonical payload, which contains only digest; but test verifies scanner runs).
3. **Secret in journal** — inject a secret into a journal row payload; `create` must refuse (journal payload members are closed vocabulary; this tests the scanner).
4. **Missing row** — delete a `workflow_events` row; `create` must include the gap in the manifest (row count mismatch) or refuse.
5. **Replay divergence** — construct a bundle where `decide` produces a different `resulting_revision` than stored; `replay` must report `divergence_at_seq`.
6. **Re-simulation substitution** — replace `work_spec_document` with one that has different `retry.max_attempts`; trace must show the substitution and the different attempt budget.
7. **Counterfactual removal** — remove a `dispatch_accepted` event; re-simulation must show the workflow never entered `running`.
8. **Protocol version unknown** — create a bundle with `protocol_version: "999"`; `verify` and `replay` must refuse.
9. **Schema version mismatch** — create a bundle with `schema_version: "6"` against a v7 ledger; `replay` must refuse (reducer vocabulary mismatch).
10. **Corrupted checkpoint** — tamper `workflow_checkpoints.document_sha256`; `verify` must detect; `replay` (which doesn't use checkpoints directly) must still verify the events.

### Property tests

- `replay(flight_record_create(WF))` always produces `byte_identical: true` for a verified ledger.
- `flight_record_create` is idempotent on the **canonical payload**: two consecutive creates for the same unchanged workflow produce byte-identical `canonical_payload` (wrapper `created_at` differs, which is allowed).
- `verify(bundle)` on a bundle produced by `create` always passes.
- Re-simulation with empty substitution set equals deterministic replay.

---

## 13. Documentation requirements

1. **Architecture contract** — this file.
2. **DECISIONS.md** — D-v0.4.144 through D-v0.4.161 (see below).
3. **CLI help text** — `aos flight-record --help`, `aos replay --help`, `aos incident --help`.
4. **Protocol artifacts** — `protocols/aos.flight-record.v1.json`, `protocols/aos.incident-report.v1.json` (added to registry).
5. **TROUBLESHOOTING.md** entries for: secret scan failure, bundle verification failure, replay divergence, re-simulation substitution error, WorkSpec digest mismatch.
6. **README.md** — one paragraph in the observability/replay section.

---

## 14. Exact candidate repository path boundary

U-E6 writes **exactly these new paths** (architecture freeze — no implementation yet):

```
/home/daksh/Projects/agentic-os-u-e6/DECISIONS.md                    (amended)
/home/daksh/Projects/agentic-os-u-e6/agentic-os-v0.4-u-e6-flight-recorder-replay-contract.md  (this file)
```

**No other paths.** Implementation wave will add **exactly these 14 paths**:

```
/home/daksh/Projects/agentic-os-u-e6/agentic_os/flight_recorder.py           (new module)
/home/daksh/Projects/agentic-os-u-e6/agentic_os/replay.py                    (new module)
/home/daksh/Projects/agentic-os-u-e6/agentic_os/incident.py                  (new module)
/home/daksh/Projects/agentic-os-u-e6/agentic_os/protocols/aos.flight-record.v1.json     (new protocol artifact)
/home/daksh/Projects/agentic-os-u-e6/agentic_os/protocols/aos.incident-report.v1.json   (new protocol artifact)
/home/daksh/Projects/agentic-os-u-e6/tests/test_v04_flight_recorder.py
/home/daksh/Projects/agentic-os-u-e6/tests/test_v04_replay.py
/home/daksh/Projects/agentic-os-u-e6/tests/test_v04_incident.py
/home/daksh/Projects/agentic-os-u-e6/tests/test_v04_flight_recorder_cli.py
/home/daksh/Projects/agentic-os-u-e6/tests/test_v04_replay_cli.py
/home/daksh/Projects/agentic-os-u-e6/tests/test_v04_incident_cli.py
/home/daksh/Projects/agentic-os-u-e6/TROUBLESHOOTING.md                      (amended)
/home/daksh/Projects/agentic-os-u-e6/agentic_os/cli.py                         (amended — CLI wiring carrier)
/home/daksh/Projects/agentic-os-u-e6/agentic_os/power.py                        (amended — power-classification carrier)
```

---

## 15. Unresolved questions (governed replan if any)

None at freeze. All design decisions are explicit above. If implementation discovers a contradiction, a governed replan (amendment A1) will be required per U-E1 precedent.

---

## 16. Decision series (to be appended to DECISIONS.md)

The following decisions will be recorded in `DECISIONS.md` under a new section "DECISIONS — Agentic OS v0.4 U-E6 flight recorder, deterministic replay, and incident forensics (Wave 0)":

- **D-v0.4.144** — U-E6 authority derives from U-W3 §1.1, U-E1 §0.1 (D-v0.4.139), and U-W2.2 §4.2; it supersedes nothing.
- **D-v0.4.145** — Replay semantics are eight mutually exclusive definitions (integrity verification, workflow history folding, snapshot rebuild, flight-record reconstruction, incident reconstruction, deterministic replay, re-simulation, counterfactual/time-travel query); no implementation may conflate them.
- **D-v0.4.146** — U-E6 requires no new tables in `aos.db`; the flight record is a derived export artifact (`aos.flight-record/v1`).
- **D-v0.4.147** — Flight record bundles exclude all document bodies (`workflow_intents.document`, `workflow_receipts.document`, `workflow_facts.document`, `workflow_checkpoints.document`, `report_document`) per D-v0.4.137; only digests and byte lengths are included.
- **D-v0.4.148** — Flight record bundles must pass `secretscan` with zero findings on the canonical payload; any hit refuses bundle creation with `secret_in_flight_record`.
- **D-v0.4.149** — Deterministic replay runs `decide` over the flight record's event sequence in isolation; never issues intents, delivers receipts, records facts, or mutates `aos.db`; produces a replay trace with per-step `byte_identical` boolean.
- **D-v0.4.150** — Re-simulation accepts explicit, declared substitutions; every substitution is recorded in the output trace.
- **D-v0.4.151** — Incident reconstruction documents cite evidence by row identity (table, row_id, content_sha256); they never infer causation the ledger does not support.
- **D-v0.4.152** — CLI surfaces are exactly six command leaves with power classifications as specified in §5; `replay --resimulate` is a flag on `("replay",)`; `flight-record` and `incident` are two-level groups; no new power modes.
- **D-v0.4.153** — Canonical JSON serialization rules: sorted keys, array order by natural key, integer bounds as numbers, digests as lower-case hex, timestamps as RFC3339 UTC.
- **D-v0.4.154** — Integrity model: row-level `content_sha256`, table-level manifest (sha256 of concatenated sorted row digests), bundle-level content digest of canonical payload; `verify` recomputes all three.
- **D-v0.4.155** — Retention: ledger unchanged; flight record bundles and incident reports are operator-managed files with no automatic lifecycle.
- **D-v0.4.156** — Backward compatibility: bundles carry `protocol_version` and `schema_version`; unknown versions are refused; old bundles replayable only if current reducer supports their vocabulary; no reducer archive exists; no migration required for U-E6.
- **D-v0.4.157** — Failure semantics: no operation mutates `aos.db`; divergence in replay is reported not refused; secret scan failure refuses creation; WorkSpec digest mismatch in re-simulation refuses unless explicitly allowed.
- **D-v0.4.158** — Test strategy requires ten specific mutation/adversarial tests plus property tests for idempotence (canonical payload), verification round-trip, and replay fidelity.
- **D-v0.4.159** — Protocol artifacts `aos.flight-record/v1` and `aos.incident-report/v1` are added to the registry; no existing protocol is modified.
- **D-v0.4.160** — Determinism rule: the **canonical payload** (the integrity-manifested JSON) is byte-identical across repeated creates of the same unchanged workflow. The wrapper (`created_at`, `secret_scan`) is explicitly excluded from the canonical payload and may differ.
- **D-v0.4.161** — Repository path boundary: exactly two files written in this freeze (`DECISIONS.md` and this contract); implementation adds exactly fourteen authorized implementation paths (three modules, `cli.py`, `power.py`, two protocols, six test modules, one TROUBLESHOOTING amendment).
- **D-v0.4.162** — `cli.py` and `power.py` were omitted from the frozen implementation inventory; they are now explicitly authorized **solely** as CLI-wiring and power-classification carrier paths for the six CLI leaves and their `READ_ONLY` / `DERIVED_WRITE` classifications. This amendment adds no other implementation path and changes no other U-E6 semantic decision.

---

*End of architecture contract. This freeze writes no implementation.*