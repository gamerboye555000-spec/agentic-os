# Agentic OS v0.4 — U-W2.3: workflow CLI, power policy, and docs (Wave 0 architecture freeze)

Architecture freeze only. Baseline `de10deaf181b99a05415370d65149b83685af979`
(U-W2.2 deterministic workflow store merged, ledger schema version `"6"`,
milestone `milestone/v0.4-u-w2-2-workflow-store`; HEAD, `origin/main`, and the
merge-base are this same commit). Branch `v0.4-u-w2-3-workflow-cli`; worktree
`/home/daksh/Projects/agentic-os-u-w2-3`; primary checkout
`/home/daksh/Projects/agentic-os`. Future PR title:
`feat(v0.4): U-W2.3 — workflow CLI, power policy, and docs`. Future commits:
exactly the two frozen by U-W2 amendment §A3.6. Future tag:
`milestone/v0.4-u-w2-3-workflow-cli`. Decisions: D-v0.4.97 – D-v0.4.102.

U-W2.3 is the human half of U-W2: one `aos workflow` command group over the
landed pure reducer and the landed store, thirteen leaves that carry an
operator's explicit decisions into the ledger and read them back out, thirteen
matching `power.COMMAND_POLICY` entries, one observability row for a refused
command, and one README section. It decides nothing the reducer has not already
decided, persists nothing the store has not already persisted, executes nothing,
retries nothing, delivers nothing, and grants nothing. **The implementation wave
chooses nothing:** every verb, argument, option, default, store call, output
byte, exit code, refusal shape, filename, test row and mutation is frozen below.

Extends and is subordinate to the landed U-W2 contract
(`agentic-os-v0.4-u-w2-workflow-state-engine-contract.md`), which froze §16's
thirteen leaves and named this slice in its §18, and which — as of this wave —
carries governed amendments A1, A2 and **A3**, the last appended by this wave
with the prior bytes byte-preserved as the file's exact prefix. **A3 is the
authority; this contract is the application, and may add nothing A3 does not
authorise.** References written `U-W2 §n` point at the landed U-W2 contract;
`U-W2 §A3.n` at amendment A3; `U-W2.2 §n` at the landed U-W2.2 contract;
`B1 §n` at its addendum B1; plain `§n` at this document.

*This contract is the audit surface for U-W2.3: an implementation behavior the
sections below do not license is a defect, whichever file it lives in.*

## 0. Scope

### 0.1 In scope (frozen here, implemented in the implementation commit)

- One new `workflow` command group in `agentic_os/cli.py` with exactly the
  thirteen U-W2 §16 leaves, their thirteen handlers, one shared write shell, and
  the refusal journal (§2–§7).
- Exactly thirteen new `power.COMMAND_POLICY` entries in `agentic_os/power.py`,
  split 9 `authoritative_write, ledger` / 3 `read_only` / 1 `derived_write`
  (§8).
- Exactly ten new `RecoveryTests.BLOCKED` rows plus their comment header in
  `tests/test_v02_power_modes.py`, authorised for this one delivery — and no
  other — by U-W2 amendment §A3.4.2 (§8.4).
- One new focused test module `tests/test_v04_workflow_cli.py`, rows C1–C26
  (§9).
- One new `README.md` unit section (§10).
- The three Wave-0 architecture documents (§11.3).

### 0.2 NOT in scope (mechanically absent, not merely discouraged)

- **No store or engine change.** `agentic_os/workflow_store.py` and
  `agentic_os/workflow_engine.py` are consumed byte-unchanged. U-W2.2 §8: "U-W2.3
  may add no function here; needing one is a replan trigger." Needing an engine
  change is likewise a replan.
- **`workflow_store.rebuild` is never called** (§5.10). Six of the seven landed
  public store functions are used; the seventh is deliberately unused.
- No schema change, no migration, no new table, column, CHECK or index; no
  `db.py`, `migrations.py`, `ids.py`, `models.py`, `events.py`, `ops.py`,
  `utils.py`, `protocols.py` or `protocols/**` edit.
- No new state, command, event, receipt kind, intent kind, refusal reason,
  matrix edge, transition-policy version, or record schema; no U-X1 registry
  change.
- No retry, checkpoint, resume or compensation surface (U-W3); no loop-health
  monitor (U-W4); no semantic interrupt kernel or approval revocation (U-W5); no
  durable-engine adoption (U-W6).
- No U-W2.R work: no queue, lease, worker, heartbeat, Postgres, DSN or adapter
  code. No network, socket, subprocess, MCP or A2A. No second database;
  agentic-os never opens the private runtime's database.
- No approval, policy, budget, capability, credential or power grant; the CLI
  cannot escalate a power mode, and `power set` remains the only mode writer.
- No packaging, `pyproject.toml`, CI workflow, or delivery-control change; no
  doctor change (U-W2 §17: workflow integrity lives in `workflow verify`); no
  Obsidian mirror rendering of workflow rows; no memory claim; no `.claude`
  content.
- No `--actor` anywhere; no `--json` on a write verb, on `verify`, or on
  `export-intents`; no pagination, no `--limit`, no `--all`.
- No interactive prompt or confirmation dialog; the repository has no such idiom
  and introducing one here would be an unlicensed behaviour (§7.6).
- No evidence import from a result envelope; that stays the human act
  `aos evidence add` (D-v0.3.8).
- No edit to any other worktree or repository.

### 0.3 Untouched

`agentic_os/workflow_engine.py`, `agentic_os/workflow_store.py`,
`agentic_os/workspecs.py`, `agentic_os/protocols.py`, `protocols/**`,
`agentic_os/db.py`, `agentic_os/migrations.py`, `agentic_os/ids.py`,
`agentic_os/models.py`, `agentic_os/events.py`, `agentic_os/ops.py`,
`agentic_os/utils.py`, `agentic_os/governance.py`, `agentic_os/passports.py`,
`agentic_os/catalog.py` and `agentic_os/catalog/*`, `agentic_os/routing.py`,
`agentic_os/agent_handoffs.py`, `agentic_os/secretscan.py`,
`agentic_os/doctor.py`, `agentic_os/hooks.py`, `agentic_os/ingest.py`,
`agentic_os/obsidian.py`, `agentic_os/backup.py`, `agentic_os/export.py`,
`agentic_os/mirror_export.py`, all delivery-control files
(`.github/workflows/ci.yml`, `tools/verify_ci_workflow.py`,
`tests/test_v04_delivery_gate.py`), `pyproject.toml`, every existing test and
fixture EXCEPT the single §8.4 edit to `tests/test_v02_power_modes.py`, and
every existing region of `agentic_os/cli.py`, `agentic_os/power.py` and
`README.md` outside the additions §2/§8/§10 name.

## 1. Decisions (index)

- **D-v0.4.97** — governed amendment A3 to the landed U-W2 contract: the closed
  eight-path U-W2.3 inventory; supersessions S1–S7; closures C-A…C-D; two
  ordered commits; no standing authority (U-W2 §A3.1–§A3.10).
- **D-v0.4.98** — the CLI surface: thirteen leaves under one `aos workflow`
  group, mapped onto SIX landed public store functions; `rebuild` deliberately
  never called; the CLI assembles the `aos.workflow-command/v1` envelope itself
  from public constants because U-W2.1 shipped no public record-builder; the
  workflow identity is normalised exactly once at the CLI edge to A2 §A2.2's
  canonical `"WF-" + str(ids.parse_id(text, "workflow"))`, and `ids.render_id`
  is never used for a workflow (§2–§5).
- **D-v0.4.99** — the refusal journal: `action = "workflow_command_refused"`,
  deliberately outside `workflow_engine.WORKFLOW_EVENTS`; `entity="workflow"`;
  `entity_id` the INTEGER identity or `None`; a payload of closed codes,
  validated identifiers, digests, bounded integers and the store's own bounded
  `diagnostics`; emitted on `refused` and `conflict` only, in its own
  transaction outside the one that declined the work; a `WorkflowStoreError` is
  never journaled (§6).
- **D-v0.4.100** — output and integrity scope: `show` and `list` carry the fixed
  B1 §B1.14 integrity-scope sentence in human mode and as `integrity_scope` in
  `--json`; `--json` exists on `show` and `list` only; `verify` exits 0 iff every
  report is `ok`; no stored document body, receipt reason message, approval ref,
  or evidence ref/claim is ever printed (§5, §7).
- **D-v0.4.101** — `export-intents` is `derived_write`, content-addressed and
  idempotent: the filename is computed by the CLI from the bytes it is about to
  write; creation is `O_EXCL|O_NOFOLLOW`; an existing file is byte-compared and
  reported `unchanged` or refused, never overwritten; an unreadable outbox row
  is reported and forces exit 1, never silently dropped (§5.13, §7.5).
- **D-v0.4.102** — the README edit is exactly one new unit section and no other
  region of `README.md`; the pre-existing stale global schema-version paragraph
  predates U-W2, is not U-W2.3's to repair, and is carried as a declared known
  limitation for a future documentation unit (§10, §13).

## 2. The command group

### 2.1 Registration (frozen)

```python
p_workflow = sub.add_parser(
    "workflow",
    help="local workflow instances (U-W2): admit, drive and inspect the "
         "deterministic workflow ledger. Records decisions and verified "
         "external facts; executes, schedules and grants nothing.",
)
workflow_sub = p_workflow.add_subparsers(
    dest="subcommand", metavar="SUBCOMMAND", required=True
)
```

TWO levels, so `power._PATH_DESTS = ("command", "subcommand", "subsubcommand")`
resolves the classification key to exactly `("workflow", <verb>)`. The group name
`workflow` collides with nothing: no existing top-level `workflow` command
exists, and the legacy `handoff` / `agent handoff` split is untouched. Every leaf
ends with `set_defaults(func=cmd_workflow_<verb>)`, the live convention.

### 2.2 The thirteen leaves, in §16 table order

```text
 1  workflow admit ARTIFACT_FILE REPORT_FILE
 2  workflow validate WF-n
 3  workflow request-approval WF-n
 4  workflow approve WF-n FACT_FILE
 5  workflow dispatch WF-n [--route SLUG]
 6  workflow revoke-dispatch WF-n
 7  workflow cancel WF-n
 8  workflow receipt WF-n RECEIPT_FILE
 9  workflow result WF-n ENVELOPE_FILE
10  workflow show WF-n [--json]
11  workflow list [--state S] [--json]
12  workflow verify [WF-n]
13  workflow export-intents DIR
```

That option surface is COMPLETE and CLOSED. `--route` on `dispatch`, `--json` on
`show` and `list`, and `--state` on `list` are the only options in the group. A
fourteenth leaf, a missing leaf, a renamed verb, or any other option is a defect.

### 2.3 Shared vocabulary helpers

```python
_WORKFLOW_INTEGRITY_NOTE = (
    "note: this verdict covers the snapshot and history; row hashes and stored "
    "receipt and fact bodies are checked only by `python aos.py workflow verify`."
)

def _workflow_state_choices() -> tuple[str, ...]:
    from . import workflow_engine
    return workflow_engine.WORKFLOW_STATES

def _workflow_identity(text: str) -> str:
    """The one accepted ID form family, normalised to A2 §A2.2's canonical
    spelling. `ids.render_id` is NEVER used for a workflow."""
    return "WF-" + str(ids.parse_id(text, "workflow"))

def _workflow_document(path) -> dict:
    from . import protocols
    return protocols.parse_canonical(protocols.read_artifact_bytes(path))
```

`_workflow_state_choices` is the live `_retrieval_candidate_choices` idiom: the
parser's `--state` choices ARE the engine's vocabulary, so a state cannot exist
that `--state` refuses, and `--state` cannot accept a state the engine does not
have. `_WORKFLOW_INTEGRITY_NOTE` is a single module-level constant, emitted
byte-identically by `show`, by `list`, and as the `integrity_scope` member of
both `--json` documents.

## 3. Identity: the one accepted form family (closure C-C)

Wherever `WF-n` appears, the accepted forms are exactly what
`ids.parse_id(text, "workflow")` accepts: optional surrounding whitespace, a
case-insensitive `WF`/`wf` prefix, and optional leading zeros. The value is
normalised ONCE, at the CLI edge, to

```text
"WF-" + str(ids.parse_id(text, "workflow"))
```

which is U-W2 §A2.2's frozen canonical representation. `WF-0`, `WF-`, `WF-1e3`, a
value above `ids.MAX_ID`, and any non-`WF` prefix are refused by `ids.parse_id`
with its own bounded `AosError` line: exit 1, nothing read, nothing written.

**Why normalisation is mandatory, not cosmetic.** The store's READERS accept
every spelling `ids.parse_id` accepts, while `submit`'s envelope gate is the
strict `workflow_engine._WORKFLOW_ID_RE = ^WF-[0-9]{1,19}$`. An un-normalised
zero-padded or lower-cased argument would therefore succeed on `show` and refuse
`command_malformed` at `/workflow_id` on every write verb — the same identity
behaving differently on two leaves of one group. Normalising once at the edge
closes that, and it is exactly the licensed purpose of the `WF` prefix
(U-W2.2 §5.1: `ids.PREFIXES["workflow"] = "WF"` exists "so `ids.parse_id`
accepts a human-typed identity at the U-W2.3 CLI, and for no other reason").

**`ids.render_id` is never used for a workflow.** It zero-pads to width 4 and
would produce `WF-0007` where the engine minted `WF-7`, breaking every event
digest (U-W2.2 §5.1, §20 row S3).

## 4. The command envelope (closure C-B)

U-W2.1 shipped no public record-builder — `workflow_engine`'s only public
functions are `decide`, `fold` and `verify_history` — so the CLI assembles the
`aos.workflow-command/v1` record itself. This is licensed: U-W2 §6 defines the
envelope, `workflow_engine.COMMAND_SOURCES` contains `"cli"` precisely so the
CLI can be its source, and §16 calls the CLI "a convenience wrapper".

```python
def _workflow_command(name, workflow_id, expected_revision, payload) -> dict:
    from . import protocols, workflow_engine
    document = {
        "schema": workflow_engine.WORKFLOW_COMMAND_SCHEMA,
        "command": name,
        "command_id": str(uuid.uuid4()),
        "expected_revision": expected_revision,
        "actor": "human",
        "source": "cli",
        "created_at": utils.utc_now_iso(),
        "payload": payload,
    }
    if workflow_id is not None:      # absent exactly on admit_work_spec
        document["workflow_id"] = workflow_id
    document[protocols.CONTENT_HASH_FIELD] = protocols.content_digest(document)
    return document
```

Frozen field choices and their reasons:

| Field | Value | Reason |
| --- | --- | --- |
| `schema` | `workflow_engine.WORKFLOW_COMMAND_SCHEMA` | the constant, never a literal (the U-W2.2 §20 row S24 idiom) |
| `command` | the store verb name (§5) | one of `workflow_engine.WORKFLOW_COMMANDS` |
| `command_id` | `str(uuid.uuid4())` | matches `protocols.UUID_PATTERN`; a FRESH identity per invocation, so re-running a verb is a NEW command and not a forced replay |
| `workflow_id` | the normalised identity; ABSENT exactly on `admit` | U-W2 §6 |
| `expected_revision` | the live read (§5.1); `0` on `admit` | U-W2 §16 as superseded by A3 S6 |
| `actor` | the constant `"human"` | matches `protocols.PROVENANCE_PATTERN`; §16 grants no `--actor`, and the CLI is only ever run by a human |
| `source` | the constant `"cli"` | `workflow_engine.COMMAND_SOURCES[0]`; NEVER `"runtime_adapter"`, so the ledger's account of who submitted a command stays truthful even when the payload came from the runtime |
| `created_at` | `utils.utc_now_iso()` | accepted by `workflow_engine._is_real_instant` |
| `trace` | **OMITTED** | optional in §6; the CLI mints no trace it did not receive (U-W2 §22's runtime-trace limitation) |
| `payload` | the verb's closed object (§5) | matches `workflow_engine._PAYLOAD_KEYS` |
| `content_sha256` | `protocols.content_digest(body)` | RECOMPUTED over the body, never copied and never trusted from input |

Payload key sets, per verb, exactly as `_PAYLOAD_KEYS` freezes them:

```text
admit_work_spec       {"work_spec_document": <doc>, "report_document": <doc>}
validate              {}
request_approval      {}
record_approval       {"approval_document": <doc>}
request_dispatch      {} or {"queue_route": SLUG}
revoke_dispatch       {}
request_cancel        {}
record_queue_receipt  {"receipt_document": <doc>}
record_result         {"result_document": <doc>}
```

## 5. The thirteen commands

Common to all thirteen: success exit code `0`; every domain refusal exit code
`1`; `2` is reserved for `main()`'s unexpected-internal-error path and is never
a designed U-W2.3 outcome. Every file argument is read with
`protocols.read_artifact_bytes` and parsed with `protocols.parse_canonical`
(§7.4). The CLI performs NO validation of its own on any document: inventing a
pre-check would create a second, competing gate that could disagree with the
reducer.

### 5.1 The shared write shell (the nine state-changing verbs)

```text
1  with _ledger(args) as (aos_dir, conn):
2      wid = _workflow_identity(args.id)          # every write verb except admit
3      payload = <verb-specific; files via _workflow_document>
4      expected = 0                               # admit
          record = workflow_store.read_workflow(conn, wid)
          expected = record.revision if record is not None else 0
5      document = _workflow_command(name, wid, expected, payload)
6      outcome = workflow_store.submit(conn, document)
7      accepted | replay -> print the §5.2 block on stdout;                return 0
       refused  | conflict -> _journal_workflow_refusal(conn, …);
                              print str(outcome.refusal) on stderr;        return 1
```

Step 4 is A3 S6's frozen shape: the live revision is read with `read_workflow`
IMMEDIATELY BEFORE `submit`, and the compare-and-swap runs inside `submit`'s
single `BEGIN IMMEDIATE` transaction — the only transaction the landed U-W2.2
boundary permits. A writer that advances the revision in between makes the
command refuse `revision_mismatch` and write nothing. A `None` record (the
workflow does not exist) yields `expected = 0`, and `submit` refuses
`workflow_unknown` — the CLI does not pre-empt that judgment.

`_ledger` is the landed contextmanager: it resolves the workspace (global
`--root` wins over cwd-upward discovery), opens the ledger through `db.open_db`
(which applies the schema-version gate), and closes it in `finally`. The CLI
constructs no database path and opens no second database.

### 5.2 Accepted / replay human output (frozen, byte-exact)

```text
WF-<n>  <status>  rev <revision>  <state>
  seq <k>  <event>  <from> -> <to>                   # one line per appended event
  intent <intent_id>  (<kind>, route <slug>)         # only when outcome.intent
  run: python aos.py workflow export-intents DIR     # only when outcome.intent
  (duplicate command; nothing changed)               # only when status == "replay"
```

- `<status>` is `accepted` or `replay`, verbatim from `StoreOutcome.status`.
- `<revision>` is `outcome.revision`.
- `<state>` is `outcome.snapshot["state"]` when the snapshot is present, else
  the state read back with `read_workflow`; `-` when neither is available.
- Event lines are `outcome.events` in `seq` order; `-` renders a null
  `from_state` / `to_state` (the live `cli._dash` helper).
- The intent lines appear exactly when `outcome.intent is not None`, which
  `StoreOutcome`'s invariant restricts to `status == "accepted"`.
- No document body, no receipt `reason.message`, no `approval_ref`, and no
  evidence `ref`/`claim` appears on any of these lines — none of those values is
  reachable from `StoreOutcome.events` or from the fields read above.

### 5.3 Refusal output (frozen, byte-exact)

Exactly ONE line on **stderr**, BYTE-EQUAL to `str(outcome.refusal)`, then exit
1. **Nothing on stdout.** The CLI adds no prefix, no suffix, and no interpolated
value: the store already builds the house-format bounded, value-free line from a
closed code, a schema-safe path and a fixed hint, e.g.

```text
Refused workflow [workflow_terminal] at /state: The workflow reached a terminal state; terminal states accept no command.
```

**The per-verb reason lists in §5.4–§5.12 are the CHARACTERISTIC reasons, not a
closed set.** Every mutating verb may additionally refuse `revision_mismatch`
(U-W2 §10, U-W2.2 §12.2) and any of the four integrity verdicts —
`history_corrupt`, `history_unknown_event`, `policy_version_unsupported`,
`snapshot_divergence` — on a workflow that fails the §7.2 write gate, including
on a REPLAY (B1 §B1.8). The implementation branches on `outcome.status`, NEVER on
`outcome.reason`, so no code path depends on the enumeration.

### 5.4 `workflow admit ARTIFACT_FILE REPORT_FILE`

```text
purpose        admit a compiled WorkSpec and its bound compile report; CREATES
               the instance and its derived WF-<n> identity
state-changing yes                      options none         accepted ids none
store call     submit(admit_work_spec)  payload {work_spec_document, report_document}
expected_rev   0 (a semantic assertion; admission has no row to read)
stdout         the §5.2 block; the identity appears here for the first time
stderr         one line, str(outcome.refusal)
exit           0 accepted/replay · 1 refusal/conflict/infrastructure
characteristic admission_artifact_invalid | admission_report_malformed |
  refusals     admission_report_unbound | admission_status_blocking |
               admission_registry_mismatch | admission_task_unknown |
               admission_task_closed | workflow_exists | payload_malformed |
               command_conflict (status conflict)
duplicates     identical envelope -> replay; same command_id with different
               bytes -> conflict; the same WorkSpec digest under a NEW
               command_id -> refused workflow_exists
redaction      no document body is ever printed
example        python aos.py workflow admit ./ws.json ./report.json
negative       a report bound to a different artifact -> exit 1,
               "Refused workflow [admission_report_unbound] at …"
```

### 5.5 `workflow validate WF-n`

```text
store call     submit(validate)              payload {}
preconditions  state == compiled
characteristic illegal_transition | workflow_terminal | workflow_unknown
duplicates     a second validate refuses illegal_transition
example        python aos.py workflow validate WF-1194901586542713359
negative       on a succeeded workflow -> "Refused workflow [workflow_terminal] at /state: …"
```

### 5.6 `workflow request-approval WF-n`

```text
store call     submit(request_approval)      payload {}
preconditions  state == validated, approval required and unsatisfied
characteristic approval_not_required | approval_already_satisfied |
               illegal_transition
duplicates     a second request refuses illegal_transition
example        python aos.py workflow request-approval WF-1194901586542713359
```

### 5.7 `workflow approve WF-n FACT_FILE`

```text
arguments      WF-n, FACT_FILE (an aos.workflow-approval-fact/v1 document)
store call     submit(record_approval)       payload {approval_document}
preconditions  awaiting_approval (scope admission) or waiting_approval (scope runtime)
characteristic approval_fact_malformed | approval_fact_unbound |
               approval_already_satisfied | approval_not_required
duplicates     an identical fact replays as a no-op at the store's fact table; a
               second admission-scope fact after satisfaction refuses
               approval_already_satisfied
redaction      the approval_ref is never printed
example        python aos.py workflow approve WF-1194901586542713359 ./approval.json
```

U-W2 records an approval somebody else issued; it judges no approver's
authority, and no field anywhere in this unit states "approval granted" as
U-W2's own claim.

### 5.8 `workflow dispatch WF-n [--route SLUG]`

```text
options        --route SLUG    default: the option is OMITTED from the payload
                               and workflow_engine applies its own default
                               "default". help: "queue route slug (default: default)"
store call     submit(request_dispatch)  payload {} or {"queue_route": SLUG}
preconditions  state == validated, approval satisfied, no dispatch pending
emits          a dispatch intent -> the §5.2 intent lines
characteristic approval_pending | dispatch_already_pending | illegal_transition |
               payload_malformed (a slug outside COMPONENT_ID_PATTERN)
duplicates     a second dispatch refuses dispatch_already_pending
example        python aos.py workflow dispatch WF-1194901586542713359 --route default
```

The CLI never derives an intent id, an idempotency key, or a workflow identity
itself; all three come from the engine through the store.

### 5.9 `workflow revoke-dispatch WF-n`

```text
store call     submit(revoke_dispatch)       payload {}
preconditions  state == validated, dispatch pending
characteristic dispatch_not_pending
duplicates     a second revoke refuses dispatch_not_pending
honesty        the README states U-W2 §22: revocation before observed acceptance
               is ADVISORY and cannot un-enqueue a row the queue already
               committed
example        python aos.py workflow revoke-dispatch WF-1194901586542713359
```

### 5.10 `workflow cancel WF-n`

```text
store call     submit(request_cancel)        payload {}
preconditions  any nonterminal state except compensating
behavior       pre-dispatch: terminal workflow_cancelled (+ dispatch_revoked when
               an intent is outstanding)
               post-dispatch: cancel_requested only; the state does NOT change
characteristic cancel_already_pending | workflow_terminal | illegal_transition
duplicates     a second post-dispatch cancel refuses cancel_already_pending
honesty        the README states U-W2 §22: post-dispatch cancellation is DORMANT
               — the live runtime has no cancellation status, so the `cancelled`
               receipt kind is unreachable after dispatch today
example        python aos.py workflow cancel WF-1194901586542713359
```

### 5.11 `workflow receipt WF-n RECEIPT_FILE`

```text
arguments      WF-n, RECEIPT_FILE (an aos.workflow-queue-receipt/v1 document)
store call     submit(record_queue_receipt)  payload {receipt_document}
characteristic receipt_malformed | receipt_unbound | receipt_out_of_order |
               receipt_superseded | runtime_uuid_mismatch |
               approval_fact_missing | workflow_terminal |
               receipt_conflict (status conflict)
duplicates     an identical receipt_id + digest replays with the ORIGINAL events
               even after the workflow advanced (U-W2.2 §9.3); a different digest
               is conflict
redaction      the receipt's reason.message is never printed
example        python aos.py workflow receipt WF-1194901586542713359 ./receipt-accepted.json
```

### 5.12 `workflow result WF-n ENVELOPE_FILE`

```text
arguments      WF-n, ENVELOPE_FILE (a beast.result-envelope/v1 document)
store call     submit(record_result)         payload {result_document}
preconditions  state == running
characteristic result_malformed | result_unbound | result_inconsistent |
               result_attempt_exceeded | result_outcome_inconclusive |
               evidence_insufficient
diagnostics    evidence_insufficient carries {required, counted,
               discounted_kind, discounted_blank} — counts only. The CLI prints
               NONE of it (the refusal line is the store's) and journals it
               verbatim as bounded integers.
redaction      no evidence ref or claim is ever printed
example        python aos.py workflow result WF-1194901586542713359 ./result.json
```

### 5.13 `workflow show WF-n [--json]`

```text
state-changing no; issues no INSERT/UPDATE/DELETE and opens no transaction
store calls    read_workflow(conn, wid) + read_history(conn, wid)
               rebuild() is NEVER called
not-found      read_workflow returns None -> AosError, exit 1:
               "No workflow WF-<n>. Run: python aos.py workflow list"
exit           0 whenever the row exists — INCLUDING when integrity != "ok"
               (U-W2.2 §15.3: read paths stay total; verify carries the verdict)
```

**`rebuild` is never called, and that is a security boundary, not a preference.**
`RebuildResult.snapshot` embeds `work_spec_document` and `report_document`
VERBATIM, so calling it would put untrusted stored bodies on a surface `show`
prints. `StoreOutcome.snapshot` is read for its `state` member only and is never
emitted.

Human stdout, exactly:

```text
WF-<n>  <state>  rev <r>  policy <p>
task:            <int>
compile status:  <valid|warning|requires_external_authority>
approval:        <required|not required>
work spec:       <sha256>
report:          <sha256>
snapshot:        <sha256>
registry:        <int>
dispatch intent: <uuid|->
cancel intent:   <uuid|->
runtime task:    <uuid|->
queue route:     <slug|->
created:         <instant>
updated:         <instant>
content:         <sha256>
integrity:       <STORE_INTEGRITY member>
history:         <N> event(s)  [integrity <verdict>]  [unreadable seq <k>]
  <seq>  <event>  <from> -> <to>  rev <r>  <actor>  <created_at>  <event sha256>
<the _WORKFLOW_INTEGRITY_NOTE line>
```

The bracketed history qualifiers appear only when the history's integrity is not
`ok` and when `unreadable_seq` is not `None`, respectively. The note line is
B1 §B1.14's explicit, named U-W2.3 obligation and is not optional.

`--json` stdout — exactly ONE document, through `cli._print_json` →
`utils.json_dumps` (`indent=2, ensure_ascii=False`, insertion key order):

```json
{
  "workflow": { "<all twenty WorkflowRecord fields, in dataclass order>": … },
  "history": { "integrity": "…", "unreadable_seq": null, "events": [ … ] },
  "integrity_scope": "<the same fixed sentence>"
}
```

The reconstituted `aos.workflow-event/v1` records are emitted whole: U-W2 §7
closes their payloads to enum members, validated identifiers, bounded integers
and digests. Events are in `seq` ascending order. Neither surface can reach a
document body, a receipt `reason.message`, an `approval_ref`, or an evidence
`ref`/`claim`.

### 5.14 `workflow list [--state S] [--json]`

```text
state-changing no
store call     list_workflows(conn, state=args.state)
options        --state S   choices = workflow_engine.WORKFLOW_STATES (13 members);
                           an unknown value is refused by argparse via
                           _Parser.error -> AosError -> exit 1, BEFORE any query
               --json
ordering       workflows.id ASC (the store's declared full scan)
empty          "(no workflows)" on stdout, exit 0
exit           0 whenever the parse succeeded
```

Human stdout, one line per workflow, then the note:

```text
WF-<n>  <state>  rev <r>  <compile_status>  <integrity>
<the _WORKFLOW_INTEGRITY_NOTE line>
```

`--json`: `{"workflows": [ <record>, … ], "integrity_scope": "<the fixed sentence>"}`.
The note line and the `integrity_scope` member are emitted even when the list is
empty, because the caveat is about the VERDICT's scope, not about the rows.

### 5.15 `workflow verify [WF-n]`

```text
state-changing no; writes NOTHING, ever (U-W2.2 §15.4, §20 row S16)
arguments      WF-n optional      options none (§16 grants no --json here)
store call     verify(conn, wid) or verify(conn, None)
ordering       one report per workflow, ordered by workflows.id
exit           0 iff every report has integrity == "ok"; 1 if any is not
not-found      an EXPLICIT WF-n that yields () (B1 C1: no report is fabricated
               for a workflow that does not exist) -> AosError, exit 1:
               "No workflow WF-<n>. Run: python aos.py workflow list"
empty (no arg) "(no workflows)" on stdout, exit 0
```

Stdout when every report is ok: one `WF-<n>: OK` line per report.
Stderr when any report is not ok:

```text
WF-<n>: <integrity> at <where>
  divergent fields: <a, b, …>            # only when non-empty
  divergent rows: <(table, id), …>       # only when non-empty
<N> workflow(s) failed verification
```

`where == "/rows"` is B1 C2's fixed token for a rows-only divergence and is
printed verbatim; it is never a table name, a row id, or a value. The `(table,
id)` pairs are `VerifyReport.divergent_rows`, whose table names are the six
frozen `db.*_TABLE` constants and whose ids are integers.

### 5.16 `workflow export-intents DIR` (closure C-D)

```text
state-changing no ledger row, no event; writes FILES only (derived_write)
arguments      DIR    options none
store call     list_outstanding_intents(conn)   (no workflow filter; §16 grants none)
ordering       workflow_intents.id ASC (emission order)
empty          "(no outstanding intents)" on stdout, exit 0
```

```text
DIR            must ALREADY exist and be a directory. The CLI does not create
               it and does not create parents: writing records into a directory
               presupposes the directory. A missing or non-directory DIR refuses
               with a bounded line naming only protocols.safe_name(DIR).
filename       f"{intent_kind}-{protocols.content_digest(document)}.json"
               matches ^(dispatch|cancel)-[0-9a-f]{64}\.json$ BY CONSTRUCTION —
               intent_kind is a closed two-member vocabulary and the digest is
               64 lowercase hex — so NO BYTE of any stored document can
               influence the name, and traversal, absolute paths, NUL bytes,
               drive prefixes and ".." segments are structurally unrepresentable
address        the digest is computed by the CLI from the bytes it is about to
               write (content_digest(view.document)), never read from the stored
               content_sha256 column, so a tampered column cannot redirect a write
bytes          protocols.serialize_canonical_file_bytes(document)
create         os.open(target, O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW, 0o644)
exists         reopen O_RDONLY|O_NOFOLLOW; fstat: regular file of exactly the
               expected size; read and byte-compare. Identical -> "unchanged".
               Different, or not a regular file -> refuse, naming only the safe
               basename. A content-addressed name whose bytes differ is a
               foreign or tampered file and is NEVER overwritten or truncated.
unreadable row IntentView.readable is False -> one stderr line per row and exit
               1 AFTER the readable rows are written; never silently dropped
exit           0 when every listed row was readable and was written or unchanged;
               1 on a missing/non-directory DIR, on a byte mismatch at a
               content-addressed name, or on any unreadable outbox row
```

Stdout:

```text
written    dispatch-<sha256>.json
unchanged  cancel-<sha256>.json
<N> intent(s): <W> written, <U> unchanged
```

Stderr when applicable:

```text
unreadable outbox row <intent_id> (status <status>)
<N> unreadable outbox row(s); nothing was written for them
```

Declared, from U-W2.2 §16.2: a cancel intent can remain `outstanding` forever on
two path classes, so re-export keeps listing it. That is a truthful "the queue
may still need to be told", not a leak, and re-export is idempotent by content
address. The README says so.

### 5.17 Store-function mapping (complete)

| Leaf | Store function(s) | State-changing |
| --- | --- | --- |
| `admit` | `submit(admit_work_spec)` | yes |
| `validate` | `read_workflow` → `submit(validate)` | yes |
| `request-approval` | `read_workflow` → `submit(request_approval)` | yes |
| `approve` | `read_workflow` → `submit(record_approval)` | yes |
| `dispatch` | `read_workflow` → `submit(request_dispatch)` | yes |
| `revoke-dispatch` | `read_workflow` → `submit(revoke_dispatch)` | yes |
| `cancel` | `read_workflow` → `submit(request_cancel)` | yes |
| `receipt` | `read_workflow` → `submit(record_queue_receipt)` | yes |
| `result` | `read_workflow` → `submit(record_result)` | yes |
| `show` | `read_workflow` + `read_history` | no |
| `list` | `list_workflows` | no |
| `verify` | `verify` | no |
| `export-intents` | `list_outstanding_intents` | no ledger effect |
| — | `rebuild` — **deliberately never called** | — |

**SIX distinct store functions are used; `rebuild` is the seventh and is
deliberately unused.** No new store function is required, so U-W2.2 §8's replan
trigger does not fire.

### 5.18 Complete exit-code table

| Situation | Code | Stream |
| --- | --- | --- |
| accepted / replay | 0 | stdout |
| successful `show` / `list` / `verify` (all ok) / `export-intents` (complete) | 0 | stdout |
| `list` / `verify` / `export-intents` with nothing to report | 0 | stdout |
| any `StoreOutcome` refused or conflict | 1 | stderr (one line) |
| `WorkflowStoreError` (the three infrastructure codes) | 1 | stderr (one line) |
| `ids.parse_id` failure on a `WF-n` argument | 1 | stderr (one line) |
| `ProtocolError` from a file read or a canonical parse | 1 | stderr (one line) |
| argparse usage error; unknown `--state` value | 1 | stderr (one line) |
| `show` / `verify WF-n` not found | 1 | stderr (one line) |
| `verify` with any non-ok report | 1 | stderr (problem lines) |
| `export-intents` bad DIR / byte mismatch / unreadable row | 1 | stderr |
| power refusal (recovery block, deep preflight) | 1 | stderr, before dispatch |
| unexpected internal error | 2 | stderr |

Exit 2 is never a designed U-W2.3 outcome.

## 6. The refusal journal (closure C-A)

U-W2 §8 assigns the row to the CLI shell; U-W2.2 §9.4 and D-v0.4.87 place it
deliberately OUTSIDE the transaction that declined the work and state that until
U-W2.3 ships "a refusal leaves no trace in `aos.db` at all". Its shape is frozen
here:

```python
def _journal_workflow_refusal(conn, verb, document, outcome) -> None:
    from . import events
    workflow_id = outcome.workflow_id
    with db.transaction(conn):
        events.emit(
            conn,
            actor="human",
            entity="workflow",
            entity_id=(ids.parse_id(workflow_id, "workflow")
                       if workflow_id else None),
            action="workflow_command_refused",
            payload={
                "workflow_id": workflow_id,
                "command": verb,
                "command_id": outcome.command_id,
                "command_sha256": document[protocols.CONTENT_HASH_FIELD],
                "status": outcome.status,
                "reason": outcome.reason,
                "where": outcome.where,
                "expected_revision": document["expected_revision"],
                "revision": outcome.revision,
                "diagnostics": outcome.diagnostics,
            },
        )
```

Frozen rules:

- **`action = "workflow_command_refused"` is deliberately OUTSIDE
  `workflow_engine.WORKFLOW_EVENTS`.** U-W2 §8: "the workflow history records
  accepted transitions only." A journal row whose `action` were one of the
  seventeen event names could be mistaken for a transition that never happened.
- **`entity_id` is the INTEGER `workflows.id`**, matching the store's own
  `_journal`, or `None` when no identity exists (an `admit` refusal, or an
  envelope whose identity could not be read). Never a rendered string.
- Emitted on `refused` and `conflict` ONLY. Never on `accepted` — the store
  already journals one row per appended event — and never on `replay`, because
  nothing was declined.
- A `WorkflowStoreError` raised out of `submit` is **NOT** journaled. It is an
  infrastructure fact about the ledger, not a fact about a workflow
  (U-W2.2 §8.4), and a workflow-scoped row for it would state something untrue.
- Its own `db.transaction`, outside the one that declined the work, so a
  journalled refusal can never be rolled back with the work it declined.
- Every payload member is a closed code, a validated identifier, a digest, a
  bounded integer, or the store's own bounded `diagnostics`. There is no
  free-text member at all. `events.emit` additionally passes both the actor and
  the payload through `secretscan.redact_tree`, so redaction is a second line of
  defence rather than the only one.
- No workflow event row is appended: `workflow_events` is the store's table and
  a refusal appends nothing to it.

## 7. Safety obligations

### 7.1 Untrusted stored text stays data

Every document reaching U-W2.3 is untrusted cross-boundary input (U-W2 §3). The
CLI is a shell and adds no interpretation of its own.

- It never renders a stored WorkSpec, compile report, approval fact, receipt or
  result-envelope BODY to stdout or stderr, in either output mode.
- `show` renders only `WorkflowRecord` fields — enums, integers, digests,
  instants, UUIDs, a validated route slug — and reconstituted
  `aos.workflow-event/v1` records, whose payloads U-W2 §7 closes to "enum
  members, validated identifiers, bounded integers, and digests only".
- No stored string is ever concatenated into a refusal message (§5.3).
- Stored text never becomes a filename, a path segment, a shell word, an import,
  or a tool input. The only CLI-constructed filename is §5.16's.
- Because no stored free text is printed, no ESC, CSI, BEL, CR, bidi override or
  other C0 control byte from an untrusted document can reach a terminal. Every
  human line is a fixed format string over closed vocabularies, digests,
  integers and pattern-validated identifiers.

### 7.2 stdout / stderr separation

```text
stdout   data only: the accepted/replay report, show, list, verify OK lines,
         export-intents file lines, and the single --json document
stderr   errors and verdict problems only: the one-line refusal, verify problem
         lines, unreadable-outbox lines, and every AosError from main()
```

A refused write verb writes NOTHING to stdout. With `--json`, stdout is exactly
one JSON document and nothing else. A refusal is exit 1 with empty stdout, so
`aos workflow validate WF-x && next` and `set -e` pipelines fail closed, and a
caller that reads only stdout can never mistake a refusal for a success.

### 7.3 Bounded, value-free messages

The refusal line is `str(outcome.refusal)` verbatim; `WorkflowStoreError`
messages are the store's own three fixed hints. The only CLI-authored messages
are the two not-found lines and the `export-intents` refusals; each names a
validated identifier (`WF-<n>` after `ids.parse_id`) or
`protocols.safe_name(path)`, plus a fixed `Run: python aos.py …` hint — the live
`cmd_agent_route_show` idiom. No raw exception or traceback appears in normal
output; `main()` prints a traceback only under `AOS_DEBUG=1`.

### 7.4 Untrusted file inputs (five arguments)

Every file argument — ARTIFACT, REPORT, FACT, RECEIPT, ENVELOPE — is read with
`protocols.read_artifact_bytes(path)`, the §9 discipline U-W2 §16 names
explicitly: `lstat` rather than `stat`, regular files only, the 256 KiB bound
applied BEFORE the read, `O_NOFOLLOW`, the descriptor re-checked against the
`lstat` result so a file swapped between check and read is refused, and one byte
read past the bound so a file that grew is refused rather than allowed to
exhaust memory. The bytes are then parsed with `protocols.parse_canonical`,
which enforces the artifact, depth, member, array, string and integer bounds, BOM
rejection and duplicate-key rejection.

`protocols.load_artifact_file` / registry validation is deliberately NOT used,
because three of the five inputs (`aos.work-spec-compile-report/v1`,
`aos.workflow-approval-fact/v1`, `aos.workflow-queue-receipt/v1`) are
deliberately not U-X1 registry identities (U-W2 §13.4) and registry validation
would refuse them. Uniform `read_artifact_bytes` + `parse_canonical` defers ALL
schema judgment to the reducer, which is exactly where U-W2 §9 puts it. A
`ProtocolError` from either call is an `AosError`: exit 1, one bounded stderr
line naming only `protocols.safe_name(path)` — never the path, never an excerpt.

### 7.5 The only filesystem write

`export-intents` is the only leaf that writes a file; its complete discipline is
§5.16. It writes; it never reads a receipt back from DIR. The two directions are
separate commands with separate arguments, so one command can never both publish
and ingest. The exported dispatch record embeds the full canonical WorkSpec by
design (U-W2 §13.1) — that is a file handed to the adapter, never rendered.

### 7.6 Destructive actions, confirmation, idempotency

- **No U-W2.3 leaf deletes anything.** The store has no DELETE path for any
  workflow row (U-W2.2 §5.1 "Retention: permanent") and the CLI adds none;
  `export-intents` never removes or truncates a file.
- **No destructive command hides behind a read.** `show`, `list` and `verify`
  issue no INSERT/UPDATE/DELETE and open no transaction.
- **No leaf prompts, and none needs to.** Every state change is explicitly named
  by the operator, additive and append-only, refused rather than merged when it
  conflicts, and already gated by `power` — recovery blocks all ten mutating
  leaves before dispatch and deep preflights the nine ledger writers. The
  repository has no interactive-prompt idiom for a ledger write and introducing
  one here would be an unlicensed behaviour. The irreversible-looking verbs are
  honest about their limits instead: `cancel` after dispatch only records a
  request, and the README says so.
- **Idempotency, per verb.** The nine write verbs mint a fresh `command_id` per
  invocation, so re-running is a NEW command, deterministically refused when the
  state no longer permits it. Exact-duplicate replay is reachable only when the
  identical envelope is delivered twice, and renders as `replay` plus
  `(duplicate command; nothing changed)`. `admit` on the same WorkSpec digest
  refuses `workflow_exists`. `export-intents` is idempotent by content address.
  `show`, `list`, `verify` are pure reads.
- **No leaf retries, sleeps, loops, or re-issues a command.** U-W3 owns retry.

### 7.7 SQL, process, network and privilege

The CLI issues NO SQL of its own: every read and write goes through
`workflow_store`'s public functions and `events.emit`. There is therefore no
dynamic SQL, no user-selected table name, and no interpolation anywhere in
U-W2.3. It spawns no subprocess, opens no socket, resolves no URL, imports
nothing dynamically, and executes nothing from any document. It opens the ledger
only through `cli._ledger` and never a second database. It grants nothing and
adds no mode check of its own; `power.dispatch` remains the one place policy is
applied.

## 8. Power policy

### 8.1 The thirteen entries (verbatim)

Appended to `power.COMMAND_POLICY` as ONE contiguous comment-headed block, after
the U-A3 governed-handoff block and before `("ingest", "dropfile")`, matching
the file's existing unit-grouped layout.

```python
    ("workflow", "admit"):            _p(AUTHORITATIVE_WRITE, ledger=True),
    ("workflow", "validate"):         _p(AUTHORITATIVE_WRITE, ledger=True),
    ("workflow", "request-approval"): _p(AUTHORITATIVE_WRITE, ledger=True),
    ("workflow", "approve"):          _p(AUTHORITATIVE_WRITE, ledger=True),
    ("workflow", "dispatch"):         _p(AUTHORITATIVE_WRITE, ledger=True),
    ("workflow", "revoke-dispatch"):  _p(AUTHORITATIVE_WRITE, ledger=True),
    ("workflow", "cancel"):           _p(AUTHORITATIVE_WRITE, ledger=True),
    ("workflow", "receipt"):          _p(AUTHORITATIVE_WRITE, ledger=True),
    ("workflow", "result"):           _p(AUTHORITATIVE_WRITE, ledger=True),
    ("workflow", "show"):             _p(READ_ONLY),
    ("workflow", "list"):             _p(READ_ONLY),
    ("workflow", "verify"):           _p(READ_ONLY),
    ("workflow", "export-intents"):   _p(DERIVED_WRITE),
```

**9 `authoritative_write, ledger=True` · 3 `read_only` · 1 `derived_write`.
Sum 13.** `ledger=True` on exactly the nine and on nothing else, which is what
`test_ledger_flag_only_on_authoritative_writes` requires.

### 8.2 Why each class, read out of the implementation

- The nine writers each submit one command through `workflow_store.submit`,
  which writes workflow rows, the append-only history and one AOS journal row
  per appended event in a single transaction — authoritative by the same
  mechanical rule as every entry above them. They also write one observability
  `events` row when the store REFUSES (§6), which is U-W2.3's own obligation and
  does not change the classification.
- `show`, `list` and `verify` read rows and recompute digests; none writes, so
  all three are `read_only` and usable in recovery — inspecting a damaged or
  contested workflow is exactly what recovery is for.
- `export-intents` writes no ledger row and emits no event, but it does write
  files that hand work to the runtime, so it is `derived_write` and is therefore
  BLOCKED in recovery: a damaged workspace must not dispatch. `DERIVED_WRITE` is
  blockable because `RECOVERY_ALLOWED_KINDS` is
  `frozenset({READ_ONLY, RECOVERY_SAFE})`, which the existing `("sync",)`,
  `("export","events")` and `("review","build")` rows already demonstrate.

### 8.3 Degradation

| Mode | Effect on the thirteen |
| --- | --- |
| `standard` | all thirteen run |
| `eco` | all thirteen run immediately — eco defers only implicit optional work, never an explicit operator request |
| `deep` | the nine `authoritative_write, ledger` leaves get the `deep_check` preflight before any write and post-verification after a 0 exit; the three reads and `export-intents` are unaffected |
| `recovery` | **TEN blocked before dispatch** (the nine writers + `export-intents`): exit 1, stdout empty, ledger and mirror byte-identical; **THREE permitted** (`show`, `list`, `verify`) |

### 8.4 The forced mechanical test edit

Authorised by U-W2 amendment §A3.4.2, for this one delivery and no other: ONE
contiguous insertion of exactly ten `RecoveryTests.BLOCKED` rows plus their
comment header into `tests/test_v02_power_modes.py`, placed **after the U-A3
governed-handoff rows (the row ending `("agent","handoff","cancel")`) and before
the `(("ingest","dropfile"), …)` row**, and nothing else in that file.

```python
        # U-W2.3 local workflow writers: each submits one command through
        # workflow_store.submit, writing workflow rows, history and journal in
        # one transaction. `export-intents` writes files that hand work to the
        # runtime. The three read-only leaves (show/list/verify) stay available
        # in recovery and are NOT listed here.
        (("workflow", "admit"), ("workflow", "admit", "SELF", "SELF")),
        (("workflow", "validate"), ("workflow", "validate", "WF-1")),
        (("workflow", "request-approval"), ("workflow", "request-approval", "WF-1")),
        (("workflow", "approve"), ("workflow", "approve", "WF-1", "SELF")),
        (("workflow", "dispatch"), ("workflow", "dispatch", "WF-1")),
        (("workflow", "revoke-dispatch"), ("workflow", "revoke-dispatch", "WF-1")),
        (("workflow", "cancel"), ("workflow", "cancel", "WF-1")),
        (("workflow", "receipt"), ("workflow", "receipt", "WF-1", "SELF")),
        (("workflow", "result"), ("workflow", "result", "WF-1", "SELF")),
        (("workflow", "export-intents"), ("workflow", "export-intents", "SELF")),
```

The argv values only have to reach the power gate, which fires BEFORE
`args.func` runs, so no workflow fixture is needed — the shape the existing
`(("agent","import"), ("agent","import","nonexistent.json"))` row already uses.
`SELF` is the file's existing workspace-root substitution token. **No assertion
is added or changed, no method is renamed, no test is deleted, skipped or
weakened, and no other line of that file is touched.**

Measured at this baseline, with the thirteen leaves and thirteen entries in
place: `should_block - covered` is exactly these ten, and `covered -
should_block` is empty. If either measurement differs at implementation time,
that is a stop condition, not a licence to adjust the list.

## 9. Test matrix (frozen)

`tests/test_v04_workflow_cli.py`, rows C1–C26. Focused command for every row:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_workflow_cli
```

U-W2 §19 rows 21–22 are the FLOOR, not the ceiling: a CLI that never journals a
refusal, that re-exports non-idempotently, that omits the B1 §B1.14 caveat, that
hardcodes `expected_revision = 0`, or that sets `source = "runtime_adapter"`
passes rows 21–22 as written and fails here.

Conventions, from the live tree: subprocess invocation through
`[sys.executable, str(REPO_ROOT / "aos.py"), "--root", str(root), *argv]` with
`PYTHONDONTWRITEBYTECODE=1` and `PYTHONPATH` set; parser and policy assertions
in-process via `cli.build_parser()` / `power.iter_command_paths`; canonical
fixtures built with a local `_seal()` helper mirroring
`protocols.content_digest`.

| # | Row | Test class :: name | Independent expected-value source | Defect it kills |
| --- | --- | --- | --- | --- |
| C1 | the parser exposes exactly the thirteen §16 leaves | `ParserTests::test_parser_exposes_exactly_the_thirteen_workflow_leaves` | the §16 table, hand-transcribed into a module constant, not read from `cli` | a fourteenth leaf, a missing leaf, a renamed verb |
| C2 | every leaf carries its frozen power class | `ParserTests::test_the_thirteen_leaves_have_the_contracted_kinds` | the §16 Policy column, hand-transcribed | M-15 |
| C3 | the option surface is exactly §16's | `ParserTests::test_only_the_frozen_options_exist` | the §16 table | an added `--actor`, `--json` on a write verb, `--json` on `verify`, `--limit` |
| C4 | one accepted ID family across all thirteen | `ParserTests::test_workflow_identity_normalisation` | `ids.parse_id` semantics asserted directly | M-05, M-06 |
| C5 | `--state` choices are the engine's vocabulary | `ParserTests::test_state_choices_are_the_engine_vocabulary` | `workflow_engine.WORKFLOW_STATES`, member by member | a hardcoded state list that drifts from the engine |
| C6 | the envelope is exactly §6, including field VALUES | `EnvelopeTests::test_command_envelope_matches_the_frozen_field_table` | `workflow_engine._COMMAND_KEYS` / `_PAYLOAD_KEYS` read as data; `actor == "human"` and `source == "cli"` asserted as values | M-01, M-02, M-03, and an `actor` other than `"human"` |
| C7 | `expected_revision` is read live and the CAS fails closed | `WriteTests::test_expected_revision_is_read_live_and_cas_fails_closed` | the revision from `read_workflow` before and after a simulated concurrent writer | M-13 |
| C8 | a refusal is exit 1, one stderr line, empty stdout | `RefusalTests::test_refusal_is_one_bounded_line_on_stderr` | `str(StoreOutcome.refusal)` computed independently in-process | M-14 |
| C9 | the refusal journal | `RefusalTests::test_refusal_writes_one_observability_event_and_no_history_row` | the `events` table read directly; `workflow_engine.WORKFLOW_EVENTS`; `entity_id` asserted an INTEGER equal to `ids.parse_id(wid)`; a `WorkflowStoreError` path asserted to write NO row | M-04, plus a rendered-string `entity_id` and a journaled `WorkflowStoreError` |
| C10 | human and JSON output are canonical and value-safe | `OutputTests::test_show_and_list_human_and_json` | the `WorkflowRecord` / `HistoryView` field lists read from the dataclasses | a missing field, a non-deterministic key order, more than one JSON document on stdout |
| C11 | power modes degrade the thirteen per their frozen classes | `PowerTests::test_recovery_blocks_ten_and_permits_three` **and** the live `tests/test_v02_power_modes.py::RecoveryTests::test_every_blockable_command_is_covered_by_the_block_list` | `power.RECOVERY_ALLOWED_KINDS` evaluated against the live parser | M-15, M-16 |
| C12 | the B1 §B1.14 read-verdict caveat is stated | `OutputTests::test_show_and_list_state_the_integrity_scope` | B1 §B1.14's obligation, transcribed as a module constant | M-08 |
| C13 | `list` ordering, `--state` filter, empty case | `OutputTests::test_list_ordering_filter_and_empty` | `workflows.id` read directly by SQL | unordered output, a silently ignored `--state` value, a non-zero exit on empty |
| C14 | `verify` exit codes and B1 C1 not-found | `VerifyTests::test_verify_exit_codes_and_c1_not_found` | `VerifyReport.integrity` in-process; B1 C1's frozen empty tuple | M-11 |
| C15 | `export-intents` is idempotent and content-addressed | `ExportTests::test_export_is_idempotent_and_content_addressed` | `protocols.content_digest` recomputed in the test | M-09, M-10, M-12 |
| C16 | no raw exception escapes any leaf | `HostileTests::test_no_raw_exception_escapes_any_leaf` | the tampered corpus of U-W2.2 §20 row S17, replayed through the CLI | a raw `sqlite3`/`Protocol`/`Key`/`Type`/`Value`/`Attribute` error reaching stderr; any exit 2 |
| C17 | reads change no byte of the database | `ReadOnlyTests::test_reads_change_no_byte_of_the_database` | byte comparison of the whole `aos.db` file before and after | M-07 |
| C18 | no stored document body reaches stdout or stderr | `HostileTests::test_no_document_body_reaches_stdout_or_stderr` | the planted `goal`, receipt `reason.message`, `approval_ref` and evidence `ref`/`claim` | M-07 |
| C19 | instruction-bearing and control text is inert | `HostileTests::test_instruction_bearing_and_control_text_is_inert` | planted ESC, CR, BEL, a bidi override and an instruction string | any C0 control other than newline in stdout or stderr; a decision that differs from the benign-text run |
| C20 | secret-shaped values never surface | `HostileTests::test_secret_shaped_values_never_surface` | a planted AKIA key, a private-key header and a bearer token | any occurrence in stdout, stderr, an `events` row, or a JSON document |
| C21 | every README example runs | `ReadmeTests::test_every_readme_workflow_example_runs` | the fenced bash blocks parsed out of the new README section of the real `README.md` | a documented flag that does not exist; a documented example that exits non-zero |
| C22 | the new region has no forbidden surface | `ExclusionTests::test_the_workflow_cli_region_has_no_forbidden_surface` | AST scan of the new `cli.py` region | `subprocess`, `socket`, `os.system`, `eval`, `exec`, `compile`, `__import__`, `importlib`, a `while` loop, a sleep, a recursive submit, a second `sqlite3.connect`, any `.claude` or private-runtime path |
| C23 | the task plane is unchanged | `CompatibilityTests::test_task_plane_is_unchanged` | `ops.mark_done` behaviour asserted directly | a workflow command that mutates tasks or runs; `mark_done` accepting zero evidence |
| C24 | no workflow command touches `tasks` or `runs` | `CompatibilityTests::test_no_workflow_command_touches_tasks_or_runs` | full before/after row comparison of both tables | any write outside the six workflow tables plus `events` |
| C25 | entrypoint help equivalence and membership | `DistributionTests::test_entrypoint_help_equivalence_and_membership` | `aos.py --help` vs `python -m agentic_os --help` vs the zipapp | a `workflow` group visible from one entrypoint only |
| C26 | no private-runtime or future-unit surface | `ExclusionTests::test_no_private_runtime_or_future_unit_surface` | grep over the new region for runtime, queue and future-unit tokens | any queue, retry, monitor or interrupt surface in U-W2.3 |

Rows C23–C26 assert about files U-W2.3 does not change; they live in the new
module and add no assertion to any existing file.

Every one of the thirteen leaves appears in at least C1, C2, C3 and C21; the nine
writers additionally in C6, C8 and C9; every leaf taking a `WF-n` argument in C4.

### 9.1 Frozen mutations

Each must be applied on the final candidate bytes, proven killed by its named
row, and restored in a `finally` with the touched file's hash proven to return
exactly.

```text
M-01  command_id reused across invocations instead of a fresh uuid4    -> C6, C7
M-02  created_at from a constant instead of utils.utc_now_iso()        -> C6
M-03  source set to "runtime_adapter" instead of "cli"                 -> C6
M-04  the refusal journal emitted on accepted or replay too            -> C9
M-05  ids.render_id used to render a workflow identity                 -> C4, C10
M-06  the raw WF argument forwarded to submit unnormalised             -> C4
M-07  show implemented with rebuild() instead of read_workflow
      + read_history                                                    -> C17, C18
M-08  the B1.14 integrity-scope note dropped from show and list        -> C12
M-09  export filename derived from intent_id or the row hash           -> C15
M-10  export overwriting a content-addressed name whose bytes differ   -> C15
M-11  verify exiting 0 when a report is not ok                         -> C14
M-12  an unreadable outbox row silently skipped                        -> C15
M-13  expected_revision hardcoded to 0 on a non-admit verb             -> C7
M-14  the refusal line augmented with a CLI-authored suffix            -> C8
M-15  export-intents classified read_only, or a writer classified
      derived_write                                                     -> C2, C11
M-16  the ten RecoveryTests.BLOCKED rows omitted                       -> C11
```

The consolidated discrimination campaign additionally exercises, without minting
new mutation identities: the parser leaf set and option surface; every option
default; every human and JSON field; the stdout/stderr split; every exit code;
ID normalisation; the store-function mapping; journal ordering; power class,
recovery and deep behaviour; the safe artifact read; export naming and
idempotence; the `rebuild` prohibition; one README example; an `actor` other
than `"human"`; a journaled `WorkflowStoreError`; and a rendered-string
`entity_id`.

## 10. README

Exactly ONE new section, and no other region of `README.md`. Title:
**`## Deterministic workflow engine and workflow CLI (U-W2)`**. Placement: after
`## Deterministic WorkSpec compiler (U-W1)` and before `## Weekend commands`.

It must carry: what the unit is and what it deliberately does not do; that the
wave-1 transport is explicit file exchange with no network and no queue; the
integrity-scope caveat (B1 §B1.14); the boundaries U-W2.R / U-W3 / U-W4 / U-W5 /
U-W6 and the no-shared-database rule; the five declared limitations (post-dispatch
cancellation is dormant; revocation before observed acceptance is advisory; a
WorkSpec may declare zero required evidence; cancel intents can remain
outstanding forever; three receipt kinds have no live source); and pointers to
the two frozen contract files.

### 10.1 The three frozen bash blocks

Exactly these command lines, in exactly this order. `WF-…` is the documented
placeholder for the derived identity; row C21 substitutes the fixture's real
identity, files and directory and requires exit 0 from every line.

```text
BLOCK 1 — the full journey
  python aos.py workflow admit ./ws.json ./report.json
  python aos.py workflow validate WF-…
  python aos.py workflow request-approval WF-…
  python aos.py workflow approve WF-… ./approval.json
  python aos.py workflow dispatch WF-… --route default
  python aos.py workflow export-intents ./outbox
  python aos.py workflow receipt WF-… ./receipt-accepted.json
  python aos.py workflow receipt WF-… ./receipt-started.json
  python aos.py workflow result WF-… ./result.json

BLOCK 2 — the two withdrawal verbs, each with its U-W2 §22 honesty note
  python aos.py workflow revoke-dispatch WF-…
  python aos.py workflow cancel WF-…

BLOCK 3 — the reads
  python aos.py workflow show WF-…
  python aos.py workflow show WF-… --json
  python aos.py workflow list
  python aos.py workflow list --state succeeded
  python aos.py workflow list --json
  python aos.py workflow verify WF-…
  python aos.py workflow verify
```

All thirteen leaves appear. No other `python aos.py` line may appear in the
section.

### 10.2 What the README does NOT touch

`README.md`'s pre-existing global schema-version paragraph is NOT edited. It was
introduced at `d06df1b` (U-A1) and was already false after U-A3 shipped schema 5,
before U-W2 existed; U-W2 §18 scopes `README.md` to "one new unit section", word
for word; and U-W2 §A3.9 records the rejection. The new section makes no global
current-version claim, so U-W2.3 introduces no contradiction. Editing any other
region of `README.md` is a stop condition.

## 11. Exact implementation paths

The tables below are EXHAUSTIVE — the closed eight-path inventory U-W2 amendment
§A3.4 authorises. A path outside them appearing in the implementation wave is
`FAIL — REPLAN REQUIRED`, and nothing here is standing authority for any later
wave or unit (U-W2 §A3.5).

### 11.1 Implementation (4)

| # | Path | New/modified | Exact responsibility |
| --- | --- | --- | --- |
| 1 | `agentic_os/cli.py` | modified | one `workflow` group, thirteen handlers, the shared write shell, the refusal journal, and the three §2.3 helpers — and no other region |
| 2 | `agentic_os/power.py` | modified | exactly thirteen `COMMAND_POLICY` entries as one contiguous block; no existing entry, kind, constant or helper changes |
| 3 | `README.md` | modified | exactly one new unit section (§10) |
| 4 | `tests/test_v04_workflow_cli.py` | NEW | the §9 matrix, rows C1–C26 |

### 11.2 Mechanical test edit (1)

| # | Path | Kind | Exact edit |
| --- | --- | --- | --- |
| 5 | `tests/test_v02_power_modes.py` | test | §8.4's one contiguous insertion of ten `RecoveryTests.BLOCKED` rows plus their comment header, at the named position, and nothing else |

### 11.3 Architecture documents (3)

| # | Path | Kind | Exact responsibility |
| --- | --- | --- | --- |
| 6 | `DECISIONS.md` | modified | the prepended U-W2.3 Wave 0 section, D-v0.4.97 … D-v0.4.102; everything below the prepend stays byte-identical |
| 7 | `agentic-os-v0.4-u-w2-workflow-state-engine-contract.md` | modified | U-W2 governed amendment A3, appended; bytes 1–147,457 preserved as the exact prefix |
| 8 | `agentic-os-v0.4-u-w2-3-workflow-cli-contract.md` | NEW | this contract |

### 11.4 Paths deliberately NOT changed, with the reason

| Path | Why not |
| --- | --- |
| `agentic_os/workflow_engine.py`, `agentic_os/workflow_store.py` | consumed byte-unchanged; any need to edit either is a replan (U-W2.2 §8, §19.4) |
| `agentic_os/ids.py` | `PREFIXES["workflow"] = "WF"` already landed, registered for exactly this CLI |
| `agentic_os/db.py`, `migrations.py`, `models.py`, `events.py`, `ops.py`, `utils.py` | no schema, migration, vocabulary or journal-framework change; `events.emit` is called unchanged |
| `agentic_os/protocols.py`, `protocols/**` | no protocol change; the CLI calls existing public functions only |
| `agentic_os/doctor.py` | U-W2 §17: workflow integrity lives in `workflow verify` |
| `pyproject.toml` | `packages = ["agentic_os"]` already includes the module; no dependency, no package data |
| `.github/workflows/ci.yml`, `tools/verify_ci_workflow.py`, `tests/test_v04_delivery_gate.py` | CI runs `unittest discover` and `compileall`; a new test module is discovered without an edit |
| every other existing test and fixture | unchanged; A1's eleven-file licence is spent and A3 authorises exactly one file for exactly one class |

### 11.5 Delivery

- Branch `v0.4-u-w2-3-workflow-cli`; worktree
  `/home/daksh/Projects/agentic-os-u-w2-3`; base
  `de10deaf181b99a05415370d65149b83685af979`.
- PR title `feat(v0.4): U-W2.3 — workflow CLI, power policy, and docs`; tag
  `milestone/v0.4-u-w2-3-workflow-cli` at the merge commit, after the merge,
  never before.
- Exactly TWO ordered commits inside the one U-W2.3 PR, through the U-P2 gate:

  ```text
  1  docs(v0.4): adopt U-W2 path amendment A3 and freeze U-W2.3 CLI architecture
     exactly paths 6-8
  2  feat(v0.4): U-W2.3 — workflow CLI, power policy, and docs
     exactly paths 1-5
  ```

  No implementation path is staged before the documentation commit exists (the
  U-P2 D-v0.4.50 landing model, applied a third time).
- Landing: PR, the four required checks (`workflow-integrity`,
  `tests-python-3.12`, `tests-python-3.14`, `distribution-smoke-python-3.12`)
  green on the exact pushed head, branch up to date, merge commit only, no
  auto-merge, conversation resolution required, empty bypass list.
- Wave 0 itself stages nothing beyond paths 6–8 and pushes nothing.

## 12. Verification (implementation wave)

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q agentic_os tests tools aos.py aos_hooks.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_workflow_cli
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v02_power_modes
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_workflow_store
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_workflow_engine
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
python3 tools/gen_protocols.py
python3 tools/verify_ci_workflow.py
git diff --check
```

## 13. Known limitations (declared, not discovered later)

- **The landed U-W2 §18 path table for this slice was incomplete**, exactly as it
  was for U-W2.2. §16's thirteen frozen leaves mechanically force ten rows in an
  existing test file that §0.3 and §19 row 22 declare untouched. The
  contradiction is resolved by U-W2 governed amendment A3, appended to the landed
  contract with its prior bytes byte-preserved as the exact prefix; this
  contract's §11 restates the amended closed inventory and adds nothing to it.
- **§16's "inside the same transaction as the CAS" was unimplementable** against
  the landed U-W2.2 boundary and is superseded by A3 S6. The CLI's read is
  immediately before `submit`; the CAS is inside `submit`'s single transaction; a
  concurrent advance refuses `revision_mismatch` and writes nothing. The window
  between the read and the submit is real and is closed by refusal, not by a
  lock the CLI cannot take.
- **`README.md`'s pre-existing global schema-version paragraph stays stale.** It
  predates U-W2, is not U-W2.3's to repair under §18's one-new-section scope, and
  is named here as work for a future documentation unit (§10.2, U-W2 §A3.9).
- **Post-dispatch cancellation is dormant** (U-W2 §22). `workflow cancel` on a
  post-dispatch workflow records `cancel_requested` and a cancel intent and
  nothing more; the `cancelled` receipt kind and terminal state are unreachable
  after dispatch until the private runtime grows a cancellation status.
- **Revocation before observed acceptance is advisory** (U-W2 §22).
  `workflow revoke-dispatch` and a pre-dispatch `workflow cancel` cannot
  un-enqueue a row the queue already committed; a human reconciles.
- **A WorkSpec may declare zero required evidence** (U-W2 §5.3, §12.2, §22), so
  `workflow result` can carry such a workflow to `succeeded` with no evidence —
  by the author's digest-bound declaration, not by any CLI override, and without
  the journaled reason the task plane's `--no-evidence` demands.
- **Cancel intents can remain `outstanding` forever** (U-W2.2 §16.2), so
  `workflow export-intents` will keep listing them. Re-export is idempotent by
  content address, so that is a truthful "the queue may still need to be told",
  not a leak.
- **Three receipt kinds have no live source** (U-W2 §22): `waiting_input`,
  `paused` and `cancelled`. `workflow receipt` accepts them because the reducer
  does; nothing in the live runtime produces them today.
- **The read verdict is narrower than `verify`'s** (B1 §B1.14). `workflow show`
  and `workflow list` report the snapshot-and-history verdict; row hashes and
  stored receipt and fact bodies are checked only by `workflow verify`. The CLI
  says so on every read, which is this contract's discharge of that obligation.
- **A refusal journal row can itself fail on a damaged ledger.** The journal
  write is its own transaction outside the declining one, so a failure there is
  an `AosError` from `events.emit`'s own path and exits 1 without a workflow row
  having been written. The declined command is unaffected; the observability row
  is simply absent, which is the same state that held before U-W2.3 shipped.
- **`workflow verify` is O(total rows) on a large ledger.** It rebuilds every
  workflow and recomputes every row hash. That is the store's declared cost
  (U-W2.2 §22), surfaced here because the CLI is where a human meets it.
- **The task check remains admission-time only** (U-W2 §22, U-W2.2 §17.2). A
  human may close a task while its workflow is `running`; U-W2.3 neither
  prevents nor detects it.

*This contract, together with U-W2 amendment A3, is the audit surface for
U-W2.3: an implementation behavior neither licenses is a defect, whichever file
it lives in.*
