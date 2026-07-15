# Agentic OS v0.2 U-H2 Evidence-Bearing Success Claims Contract

Date: 2026-07-15. Branch: `v0.2-u-h2-success-proof`. Baseline:
`8285ee6c216e2ab5cf11d5cb324d522bc5e071b5`.

This contract pins the whole U-H2 slice before any production change. It is
implemented exactly as written; nothing here is expanded during the pass.

## Mission

A structured claim of `success` must carry proof. U-H2 makes a dropfile that
declares `outcome: success` refuse ingest unless it carries at least one
acceptable evidence row, hardens every affected write boundary against blank
evidence refs and explicitly blank claims, and gives doctor a warn-only view
of successful ended runs that no acceptable evidence can be attributed to.
U-H2 enforces presence and structural non-blankness of evidence — never the
truth of what the evidence claims. No free-text success classification is
introduced anywhere: only the structured `outcome` field is ever judged.

## U-H2.1 Successful-dropfile ingest gate

A dropfile whose structured `outcome` is `success` must carry at least one
acceptable evidence row **in that same dropfile**. Pre-existing task evidence
does not satisfy the gate.

A row is acceptable when all of:

1. its kind is in the existing `EVIDENCE_KINDS` vocabulary;
2. its ref remains non-blank after the existing one-line collapse
   (`" ".join(value.split())` — Python whitespace semantics, so NBSP,
   U+3000 and all other Unicode whitespace count as whitespace);
3. its claim (always explicitly present in the dropfile bullet grammar)
   remains non-blank after the same collapse.

The gate does not semantically verify the evidence target. A note, URL,
test, commit, file, or command_output row is evidence per the existing
vocabulary; presence and non-blankness are the entire U-H2 judgment.

Gate position, pinned: **after** the existing size, UTF-8, syntax/parse,
task-exists, secret-scan, and duplicate checks; **before** the ingest
transaction opens. Duplicate detection therefore retains precedence: a file
already ingested before U-H2 reaches the duplicate refusal first.

Refusal, pinned:

- exit code 1 through the existing `AosError` path;
- stdout byte-empty;
- one bounded stderr diagnostic naming the task ID (validated/rendered
  `T-XXXX` form only) and the recovery rule: add at least one evidence row
  to the dropfile, or use the honest structured outcome `partial`, `fail`,
  or `unknown`;
- zero mutation: no evidence, run, handoff, event, or marker row — the gate
  runs before the transaction, so refusal leaves no partial state;
- no raw evidence ref, claim, summary, agent, question, or dropfile excerpt
  is ever echoed.

Because the gate runs pre-transaction on the parsed document, its acceptable
rows are re-judged by a standalone helper even though the U-H2.3 parser
already guarantees every parsed row is acceptable — the gate must not
silently weaken if parser guarantees ever shift.

## U-H2.2 Non-success outcomes

`partial`, `fail`, and `unknown` remain valid with an empty evidence
section. No outcome is added (`cancelled`, `refused`, etc. stay out).
Runs-ladder behavior at ingest is untouched: one open run for the task+agent
ends with the dropfile outcome; zero or multiple open runs still ingest
evidence and questions and end no run.

## U-H2.3 Dropfile parsing hardening

After the existing per-line strip and one-line collapse:

- an evidence ref that collapses to empty refuses as a malformed evidence
  line, naming the line number and the field (`evidence ref must not be
  blank`), never the value;
- an explicitly present evidence claim that collapses to empty refuses the
  same way (`evidence claim must not be blank`);
- Unicode whitespace (NBSP U+00A0, U+3000, and everything else Python's
  `str.split`/`str.strip` treat as whitespace) counts as whitespace.

Grammar note, pinned for honesty: the parser strips each line before the
evidence-bullet regex runs, so a claim made only of whitespace is
right-stripped off the line and the bullet no longer matches the
`- kind: K | ref: R | claim: C` shape — such a row refuses at that same
line as a malformed evidence line (the shape diagnostic), which is the
intended evidence-line branch. The in-parser claim-blank branch additionally
guards the collapsed value so the rule stays explicit if the grammar ever
changes. Blank refs, by contrast, can survive the strip inside the line
(`ref: <spaces>|`, NBSP-only, U+3000-only) and reach the dedicated
ref-blank branch, which the tests prove byte-exactly.

The parser stays linear: no new regex, no backtracking-heavy construct —
two emptiness checks on already-captured groups.

## U-H2.4 Trusted CLI evidence writes

In `ops.add_evidence`:

- a ref that is empty or whitespace-only (Python `str.strip`, Unicode
  semantics) refuses with exit 1 before any mutation or event emission;
- an explicitly supplied claim that is empty or whitespace-only refuses the
  same way (the diagnostic says to omit `--claim` instead);
- `claim=None` (omitted `--claim`) remains legal;
- existing evidence-git resolution and file-kind sha256 hashing behavior is
  unchanged for non-blank refs; the blank-ref refusal fires before the
  file-existence check, so a blank `--ref` on `--kind file` now names the
  blank ref rather than "file not found";
- `evidence git` inherits the same guard through `add_evidence` (a
  git-derived ref is a full commit sha and can never be blank; a supplied
  blank `--claim` refuses).

## U-H2.5 Direct run endings

`run end --outcome success` remains accepted with no immediate evidence
check and no warning. Its CLI surface, stderr, stdout, summary semantics,
and event shape are byte-for-byte untouched. Recovery from a hook/dropfile
refusal therefore stays available to the human.

## U-H2.6 Doctor: success-run attribution warning

A new warn-only doctor check flags ended runs with outcome `success` that
lack acceptable evidence attributable to the run.

Evidence E is attributable to run R when all of:

1. `E.task_id == R.task_id`;
2. `E.ref` is non-blank after Python whitespace normalization;
3. `E.created_at >= R.started_at` (ISO-Z strings, fixed second-precision
   format, compared as strings — the single-clock format makes string
   order time order);
4. when a next run exists for the same task, `E.created_at` is strictly
   earlier than that next run's `started_at`.

The next run of R is the earliest run of the same task strictly later than
R in the total order `(started_at, id)`.

This creates the run-bounded recovery window, pinned:

- evidence created during the run counts;
- evidence added after a successful end still counts until the next run of
  that task starts (post-hoc healing window);
- evidence belonging to a later run cannot heal the earlier run;
- evidence created before the run never counts;
- when two sequential runs share one second-precision `started_at`, the
  boundary is conservative: evidence at that shared timestamp does not
  heal the earlier run once the later run exists (the strict `<` bound
  makes the earlier run's window empty in that case).

Pinned exclusions: `evidence.run_id` is NOT populated (it stays a dormant
schema column); no schema change; no new evidence-linking CLI.

The warning:

- identifies run IDs only (`R-XXXX`);
- shows the total offender count and at most the first 10 IDs
  (`(+N more)` beyond that);
- never prints evidence refs, claims, summaries, agent values, or any
  ledger excerpt;
- is warn-only: doctor exit stays 0 when all hard checks pass.

## U-H2.7 Doctor: legacy blank-ref evidence warning

A second, separate warn-only check lists existing evidence rows whose ref
is blank after normalization (legacy rows admitted through the pre-U-H2
regex hole). It identifies only bounded `E-XXXX` IDs plus the total count
(first 10, then `(+N more)`). Legacy rows are never rewritten or deleted.
`mark_done` and the done gate are unchanged: such rows still count for the
done evidence gate exactly as before.

## U-H2.8 Generated protocol

The renderer-owned dropfile protocol gains one concise rule directly under
the dropfile format block:

> A dropfile with `outcome: success` must list at least one non-blank
> evidence row; ingest refuses a success dropfile whose evidence section
> is empty. `partial`, `fail`, and `unknown` remain valid with no
> evidence.

The rule lives in the SHARED dropfile section of `render.adapter_protocol_md`
because the ingest gate judges dropfiles from every adapter, and the
checked-in `adapters/claude-code/PROTOCOL.md` is regenerated byte-identical
to the renderer output. Consequence, reported as a boundary deviation: the
existing all-adapters parity invariant (test_v02_hooks/test_v02_secret_safety)
requires the codex, gemini, and generic `PROTOCOL.md` files to be
regenerated too — leaving them stale would either fail the suite or document
a false contract. A focused U-H2 parity test additionally pins the
claude-code file and the presence of the rule.

## U-H2.9 U-H1 stays transport-only

The Stop/SessionEnd hooks are not modified. A structurally valid success
envelope with an EMPTY evidence section still stages and publishes
(D-v0.2.29 unchanged); U-H2 refuses it at ingest. A blank-ref evidence row,
however, is now structurally malformed per the shared parser, so the hook
refuses to stage it — that is parser parity (the hook has always refused
exactly what the parser refuses), not a new hook policy.

## Explicit exclusions

- No semantic verification of evidence targets; no truth judgment.
- No free-text classification: words like "success", "passed", "complete",
  "done" in summaries, claims, questions, or notes trigger nothing.
- No new outcomes; no change to `RUN_OUTCOMES`.
- No change to `hooks.py`, `aos_hooks.py`, `db.py`, `models.py`, `cli.py`,
  `secretscan.py`, `mark_done`, packaging, CI, migration, memory,
  orchestration, MCP/A2A, autonomy, export, backup, search, review, or
  AICompany surfaces.
- No `evidence.run_id` population, no schema change, no new CLI.
- No evidence content is ever executed or passed to a subprocess.

## Known pre-pinned test-boundary deviations

The frozen policy necessarily moves four existing pins; each is the minimal
mandated edit, reported in the final report:

1. `tests/test_v02_hooks.py::test_scenario_5_duplicate_retry_never_double_publishes`
   ingests a success/empty-evidence dropfile expecting exit 0 — U-H2 makes
   exactly that refuse. The scenario's identity (duplicate/retry publish +
   ledger dedupe) is preserved by giving its body one evidence row.
2. Three doctor line-count pins (`test_cli.py`, `test_weekend_views.py`,
   `test_v02_secret_safety.py`) assert exactly 18 output lines; the two
   mandated warn-only checks move the pin to 20 (each test documents the
   D-W8.1 "pin moves up with mandated new checks" pattern in place).

Plus the U-H2.8 consequence: `adapters/{codex,gemini,generic}/PROTOCOL.md`
are regenerated to preserve the byte-parity invariant.

## Tests

One new file, `tests/test_v02_success_proof.py`, covering exactly the
mission's regression matrix: the ingest success gate (atomic refusal, empty
stdout, no-echo diagnostic, duplicate precedence, corrected retry,
non-success outcomes, zero/multiple open-run behavior), byte-exact parser
fixtures (padded blank ref, NBSP-only ref, U+3000-only ref, explicitly
blank claim, valid Unicode row) proving the exact branch reached, CLI
evidence refusals (atomic, Unicode-aware, claim-omission legality, file/git
behavior preserved), the doctor run-window predicate (before/during/after,
same-second boundaries, shared-timestamp conservatism, non-success and open
runs unflagged, blank-ref evidence proving nothing, >10 bounding, hostile
values never echoed, exit 0), the legacy blank-ref check, and the
non-regression set (hook still publishes success/empty which ingest then
refuses atomically; renderer/protocol parity; no free-text classification;
no subprocess sees evidence content; mark_done/override unchanged).

## Validation

Exactly the mission's commands: the focused suite, the U-H1 hook suite, the
full discovery run, `compileall`, `git diff --check`, and the status/diff
reports. No dogfood smoke in this pass; the human runs the single
independent smoke after review.
