# DECISIONS — Agentic OS two-week scope PLANNING run

This section (`D-2W-P.*`) journals the planning pass executed per
`agentic-os-two-week-scope-prompt.md` on branch `two-week-scope` (2026-07-07).
It is a planning journal only — no source or tests were touched; the build
journal for the implementation phase (`D-2W-A.*` etc.) comes later, under its
own contract. Prepended above the Weekend section per that section's own
precedent (D-W0.4); everything below stays byte-identical.

## D-2W-P decisions

- **D-2W-P.1 — Baseline gate results.** Branch `two-week-scope`; HEAD `01ee04a`
  ("docs: add two-week scope planning contract"), a descendant of `85d3793`
  (= tag `milestone/weekend-mvp`; `milestone/night-1` = `59da161`, both
  verified via `git show-ref`). Working tree clean, nothing staged, no
  untracked files (the contract was pre-committed). No `*Zone.Identifier`
  junk files existed (nothing to delete). Python 3.12.3. Baseline suite:
  **162 tests, OK** (expected 162). `.agentic-os/` did not exist at start;
  it was created during this run exclusively via the aos CLI (dogfood
  bootstrap mandated by the contract).
- **D-2W-P.2 — Weekend final report handled as absent.** No
  `docs/reports/weekend-final-report.md` (or any report file) exists in the
  repo. Per the contract, the Weekend "Known limitations" and "Deferred
  features" lists were reconstructed ONLY from README.md ("Status" section)
  and this file's D-W/D-P entries; no conversation record was assumed. The
  plan states this explicitly (plan §2.1).
- **D-2W-P.3 — Reconciliation verdicts.** The two-week phase is re-anchored
  to Weekend debt (§11 MVP-stage items the Weekend build deferred: dropfile
  ingest F-C7, git evidence ingest F-G1, agent registry F-C8) plus task
  lifecycle UX (D-P0.21), instead of research §11's 2-week list (ledger
  decision D-0001). All ten §12 un-defer triggers were checked: none has
  fired; all ten deferrals stand. The §11-vs-§12 conflict on F-B10 (listed in
  the 2-week stage AND deferred with a trigger) is resolved in §12's favor —
  the trigger ("one-way mirror proven idempotent for 2+ weeks of daily use")
  is unfired. Counts: 13 planned items, all traced; of the 11 §11 2-week
  items, 9 dropped with reasons + triggers, 2 adapted (F-E10 → goldens,
  F-G5 → soft warning + review section, because a hard refusal would break
  the Night-1 back-compat fixture).
- **D-2W-P.4 — Capacity model.** 17.5 h of core items + 1 h final gate =
  18.5 h planned against the contract's 20–25 h budget; slack stated per
  endpoint (7.5% / 18% / 26%); ordered 9 h stretch pool intentionally exceeds
  maximum slack (tail lands only on under-run). Cut line if capacity halves:
  task assign/edit/status + dropfile ingest (10.5 h); everything else falls
  out, D first, then C, then B2.
- **D-2W-P.5 — Dogfood loop record and friction.** Fresh workspace: `init`,
  `project add agentic-os`, task **T-0001** ("Two-week scope plan", kind
  research), pack `packs/T-0001-claude-code.md`, run **R-0001**, scoping
  decisions **D-0001..D-0003** via `decision add`, evidence **E-0001** (this
  plan file, kind file) attached at close, run ended success, T-0001 done,
  sync + doctor clean. **T-0002** (`in` capture noting the dropfile dead-end)
  is deliberately left open and projectless: it is live evidence for Phase A
  (no command can assign or triage it — D-P0.21 verified against the current
  CLI). Friction harvested into the plan (§2.6): stranded inbox capture; no
  `--spec` flag anywhere; dropfile fallback advertised by every pack with no
  reader; research-kind pack suggesting `--kind test` evidence and a branch
  convention; `in` defaulting captures to kind=code.
- **D-2W-P.6 — Adversarial verification of the plan.** Four independent
  reviewers (contract compliance · fact-check against evidence files and
  code · implementation feasibility against the mapped tests/pins · internal
  consistency), each instructed to refute the draft. 19 findings; all
  addressed. The two blockers were sequencing gaps this journal and the
  closed dogfood loop now resolve (D-2W-P entries cited before being written;
  evidence cited before being attached). Substantive fixes adopted: A1 gains
  a done-guard (assign could otherwise reopen a closed projectless task); the
  A1/A3 projectless-ready ordering trap is pinned; B2's acceptance criterion
  was untestable as written (D-P4.1 forbids git repos in tests) → mocked-
  boundary strategy with manual final-gate verification (D-P7.2b pattern);
  dropfile dedupe meta-key distinguished from the D-W5.1 eventless precedent
  (written in-transaction); dropfile event payload carries outcome/one-lined
  summary; agent names validated against the provenance charset; D1 sections
  placed after `## Recent runs` to respect a pinned content slice; stretch
  arithmetic, trigger-wording ("in substance", not verbatim), F-C7 scope
  ("ingest half"), and test-count projections corrected. Final self-scores
  all ≥ 8 (plan, end).

# DECISIONS — Agentic OS Weekend MVP build

This section (`D-W*`) records every simplification, interpretation, and
deviation made while executing `agentic-os-weekend-mvp-build-prompt.md` (the
Weekend contract) on branch `weekend-mvp`. The contract asks for the Weekend
plan "up front", so this section sits above the Night-1 journal; nothing below
the Night-1 heading is ever rewritten (append-only holds at the entry level).
Format: `D-W<phase>.<n>`.

## Weekend plan (D-W0) — mapped to phase gates

- [ ] **P0** Baseline gate (branch/HEAD/tree/python/suite) + this plan.
- [ ] **P1** Global `--root` + discovery pinned by test first + Night-1-shaped
      workspace fixture (init → project → task → pack → run → evidence → done
      → sync) that later phases reuse for back-compat proofs.
- [ ] **P2** `decision add` ops + CLI (+ task show / pack DECISIONS / sync
      already wired in Night-1 — proven by tests, not rebuilt).
- [ ] **P3** `handoff create|accept` ops + CLI (+ pack PRIOR RUNS & HANDOFF
      STATE / task show / sync proofs; double-accept exit 1).
- [ ] **P4** `memory add|list|retire` (+ `--supersedes`) + M- prefix in ids.py
      + pack MEMORY live-only inclusion rule + Memory notes in sync.
- [ ] **P5** `search` (FTS5 detect at runtime, LIKE fallback force-tested,
      watermark rebuild from source tables, `--json`).
- [ ] **P6** `review build` (+ `## Notes` byte-for-byte preservation +
      idempotency; eventless).
- [ ] **P7** `export events --jsonl` + `snapshot` (backup API, never raw file
      copy; event-only audit record after the file is written).
- [ ] **P8** Doctor hardening (schema_version · status vocabulary ·
      done-evidence/override · handoff/decision/memory/pack referential and
      file checks) + corrupted-workspace failure tests.
- [ ] **P9** README + DECISIONS + full validation + Weekend smoke + FINAL
      GATE + FINAL REPORT.

Rule per gate (unchanged from Night-1): that phase's tests written AND the
full suite green before moving on; test count never shrinks.

## W0 decisions

- **D-W0.1 — Baseline gate results.** Branch `weekend-mvp`; HEAD is exactly
  `59da161` ("feat: add Agentic OS night-1 MVP"); `python3 --version` =
  3.12.3; baseline suite green: **89 tests, OK** (this is the P0 count).
  Working tree: no modified tracked files, nothing staged; the only untracked
  file is the Weekend contract itself
  (`agentic-os-weekend-mvp-build-prompt.md`) — it is this run's input,
  recorded here and left unstaged. A Windows→WSL copy artifact
  (`agentic-os-weekend-mvp-build-prompt.md:Zone.Identifier`) was deleted
  before any check ran. `.agentic-os/` is gitignored and absent from status.
- **D-W0.2 — Research files re-read as data only; refusals renewed.**
  Rejected again (per contract + D-P0.1): pytest (stdlib unittest only),
  PyYAML (stdlib only), any `--allow-secret` override (packs refuse, full
  stop), the research schema's 8-value task status enum (vocabulary stays
  `inbox|ready|in_progress|done`), `generated_at` in pack headers or note
  bodies (no wall-clock in generated files), and contentless FTS tables with
  write triggers (the contract prescribes a derived index with a
  `fts_event_watermark` staleness rebuild instead — triggers would be schema
  surface on core tables).
- **D-W0.3 — New modules.** Weekend code lands in three new cohesive modules
  — `agentic_os/search.py`, `agentic_os/review.py`, `agentic_os/export.py` —
  plus targeted extensions to `ops.py`, `cli.py`, `ids.py`, `models.py`,
  `render.py`, `obsidian.py`, `doctor.py`. The Night-1 module list was that
  contract's scope, not a cap on this one. New tests live in
  `tests/test_weekend_core.py` and `tests/test_weekend_views.py` (plus a
  shared fixture helper); existing test files are only ever extended.
- **D-W0.4 — DECISIONS.md structure.** This Weekend section is prepended
  above the Night-1 journal per the contract's "up front"; every historical
  Night-1 entry below stays byte-identical. New D-W entries append to this
  section as phases complete.

## W1 decisions

- **D-W1.1 — Explicit `--root` never searches.** Global `--root PATH` means
  exactly `PATH/.agentic-os`; there is no upward walk from PATH. Uninitialized
  PATH → exit 1 with a remedy that names the flag
  (`Not initialized at PATH. Run: python aos.py --root PATH init`). Without
  `--root`, discovery is byte-for-byte the Night-1 behavior (cwd-upward walk,
  pinned by TestDiscoveryPinned before the parser was touched).
- **D-W1.2 — Separate argparse dests.** The global option stores to
  `global_root`; `init --root` keeps its own `root` dest. argparse subparsers
  re-apply their own defaults after the main parser runs, so sharing one dest
  would let the subparser's `None` default silently clobber a global value.
  `cmd_init` reconciles the two (differ → exit 1; equal or single → proceed).
- **D-W1.3 — Back-compat harness design.** The fixture builds a
  Night-1-shaped workspace using ONLY Night-1 commands under cwd discovery
  (init → project → task ×2 → pack → run → evidence → done → in → sync),
  then every back-compat test drives it purely via `--root` from an unrelated
  cwd. "No migration / no drift" is proven against `sqlite_master`: the
  CREATE TABLE SQL of all 11 core tables must be identical before and after
  Weekend commands run.
- **D-W1.4 — Gate P1 result.** 101 tests green (89 baseline + 12: discovery
  pins ×4, global-root semantics ×6, Night-1 fixture shape + Night-1 commands
  via --root with schema-drift oracle).

## W2 decisions

- **D-W2.1 — `decision add` semantics.** Status is always `'accepted'`
  (Night-1 schema default; no proposal workflow in Weekend scope);
  `decided_at` comes from the single clock utility. `--task` must belong to
  the `-p` project — a mismatch (including project-less inbox tasks) exits 1,
  keeping `related_decisions`' task/project scoping coherent. Empty title or
  `--decision` text exits 1. One event `(decision, add)` per D-P0.5 with
  payload {decision, title, project, task, status}. Task show, the pack
  DECISIONS section, and `Decisions/D-*.md` sync were already wired in
  Night-1 (D-P0.7); P2 proves them with CLI-created rows instead of
  rebuilding them.
- **D-W2.2 — Gate P2 result.** 109 tests green (task-scoped decision flows
  through task show → pack → synced note with bidirectional wikilinks;
  project-scoped decision appears on all project tasks; event payload;
  unknown project / cross-project task / malformed id / empty text
  refusals; ops-layer atomicity; sequence test and pre-init guard extended).

## W3 decisions

- **D-W3.1 — Handoff semantics.** `handoff create` is allowed on any existing
  task regardless of status, including done (a handoff can document state
  after closure; the contract sets no status rule and the sequence test
  exercises a done task). `--from`/`--to` must be non-empty after strip and
  may be equal (no rule against a self-handoff); `--state` must be non-empty.
  `accept` is one-shot: an already-accepted handoff exits 1 naming the
  original `accepted_at`. Events: `(handoff, create)` and `(handoff, accept)`.
  Task show, the pack PRIOR RUNS & HANDOFF STATE section, and
  `Handoffs/H-*.md` sync were Night-1 wiring (D-P0.7), proven here with
  CLI-created rows.
- **D-W3.2 — Gate P3 result.** 117 tests green (create flows through task
  show → pack → synced note; accept + double-accept exit 1; missing task /
  malformed and missing ids / empty state refusals; secret scan fires on
  handoff state naming PRIOR RUNS & HANDOFF STATE without echoing; create and
  accept atomicity — accept's rollback asserts accepted_at stays NULL;
  sequence test and pre-init guard extended).

## W4 decisions

- **D-W4.1 — `valid_until` semantics.** `--valid-until YYYY-MM-DD` is strict
  (regex + real-calendar-date check). A date-only value expires at UTC
  midnight STARTING that date; liveness is a plain string comparison against
  the full-ISO clock value (`"YYYY-MM-DD" < "YYYY-MM-DDT…"` makes that
  correct). `retire` sets `valid_until` to the full-ISO now; "already
  retired" means valid_until is non-NULL and `<= now` — a row with a future
  valid_until can still be retired early.
- **D-W4.2 — Supersede rules.** `--supersedes M-XXXX`: the old row must exist
  and must not already be superseded (chains stay linear; re-superseding
  exits 1 naming the existing successor). No cross-field matching is enforced
  (a supersede may change key/scope — the pack rule is per-key anyway). Both
  `retire` and the supersede pointer-set refresh the mutated row's
  `updated_at` (uniform rule: any row mutation refreshes it). Supersede is
  part of the single `(memory, add)` event; its payload carries
  `"supersedes"` — one operation, one event, per D-P0.5.
- **D-W4.3 — Pack inclusion rule lives in `ops.memory_for_project`.** Same
  entry point Night-1's pack compiler already called, now implementing the
  contract rule: live rows only (superseded_by IS NULL AND valid_until NULL
  or future), scope=global plus the pinned project, latest row (highest id)
  per (scope, project, key) wins, ordered scope then key (`'global'` sorts
  before `'project'`, so global rows lead). Pack content therefore depends on
  liveness AT BUILD TIME; an expiry flips the section content → different
  inputs_hash → new pack row, consistent with D-P0.16/D-P0.19 (no wall-clock
  value is ever WRITTEN into the pack).
- **D-W4.4 — `memory list` carries a computed `live` flag.** JSON/CLI
  convenience derived from the clock at query time; never written to
  generated files. Retired/superseded rows always stay in the listing with
  their valid_until / superseded_by visible.
- **D-W4.5 — Gate P4 result.** 129 tests green (add/list/retire/supersede
  incl. all enum/format refusals; retired rows never vanish from list;
  retired/superseded/expired excluded from packs while latest-per-key wins
  and global precedes project; secret scan via memory value names MEMORY and
  never echoes; Memory notes sync with [[project]] and [[M-XXXX]] supersede
  links; add/supersede/retire atomicity incl. pointer rollback; sequence test
  and pre-init guard extended).

## W5 decisions

- **D-W5.1 — The FTS index is derived state, not schema.** One virtual table
  `search_index(entity UNINDEXED, entity_id UNINDEXED, title UNINDEXED,
  body)` created with `CREATE VIRTUAL TABLE IF NOT EXISTS`, where `body`
  concatenates exactly the contract's searchable fields per entity. It is
  rebuilt from the source tables (DELETE + repopulate) whenever the meta
  watermark `fts_event_watermark` ≠ current `MAX(events.id)` OR the table is
  missing — so it is safe to DROP at any time. This is NOT a schema change:
  schema_version stays "1", Night-1 databases open unmodified, and the meta
  watermark row is data, not schema. (Recorded per the contract's explicit
  instruction.)
- **D-W5.2 — Search is EVENTLESS (extends D-P0.6).** The index rebuild and
  watermark write mutate derived state only. Emitting an event per search
  would bump `MAX(events.id)` and make the index permanently stale — the
  derived-view rule is load-bearing here, not just aesthetic.
- **D-W5.3 — Query semantics.** FTS5: every whitespace-separated term is
  double-quoted (phrase token) so user text can never reach the FTS parser
  as syntax; terms are implicitly ANDed; a query FTS still cannot parse
  exits 1. LIKE fallback: case-insensitive substring conjunction (AND of
  `LIKE '%term%'`) evaluated over the SAME document set the index holds,
  with simple deterministic ordering (entity type, then ascending id).
  Known semantic gap, documented: FTS matches whole tokens, LIKE matches
  substrings — membership parity holds (and is tested) for whole-word
  queries.
- **D-W5.4 — Ranking and snippets.** FTS5 orders by bm25 (`ORDER BY rank`)
  with (entity, entity_id) tie-breaks for determinism; snippets come from
  `snippet()` (FTS5) or a deterministic ±40-char window around the first
  term hit (LIKE), both collapsed to one line.
- **D-W5.5 — Gate P5 result.** 138 tests green (all five entity types found
  with correct ID prefixes; text output = backend line + one line per hit;
  forced-fallback path; fts5↔like membership parity incl. a multi-term and
  a no-hit query; watermark write + rebuild-on-new-events; DROP-and-search
  recovery; eventless; empty-query and no-results behavior; pre-init guard).

## W6 decisions

- **D-W6.1 — `review build` is EVENTLESS.** It regenerates a derived view of
  ledger state (like sync — extends D-P0.6): no ledger rows mutate, no event
  is emitted, and idempotency ("two builds with no data change → identical
  file") holds strictly. Recorded per the contract's explicit instruction.
- **D-W6.2 — Review windows.** "Recently added" evidence/runs = a 7-day
  window ending on the review date (`[date-6, date]`, ISO-prefix
  comparisons; the upper bound uses `date + "~"` since `'~' > 'T'`). Stale
  memory = `valid_until[:10] <= date`, or valid_until NULL and
  `updated_at[:10] <= date-30d`. Every window derives from the date
  parameter; the default date is `utc_today()` from the single clock — no
  other wall-clock read. Superseded rows are NOT specially excluded from the
  stale list (the contract's definition doesn't exclude them; noted as a
  limitation).
- **D-W6.3 — Notes preservation is raw-bytes.** The preserved region starts
  at the first line reading `## Notes` (tolerating a CR on that line) and is
  spliced back verbatim — CR bytes and a missing trailing newline in the
  user's region survive, because the contract's byte-for-byte rule overrides
  the LF/trailing-newline rule for that user-owned region (generated head
  stays LF-clean). If the heading was deleted, a fresh `## Notes\n` tail is
  appended.
- **D-W6.4 — Review bullets use wikilinks.** They resolve once the mirror is
  synced; the expected order is review build → sync → doctor (exactly the
  Weekend smoke's order). Doctor treats `Reviews/YYYY-MM-DD.md` as a
  generated kind and checks its links like any other note.
- **D-W6.5 — Gate P6 result.** 145 tests green. One red run on the way was a
  test-side scenario error, not production code: the test plants an
  unevidenced done via SQL (to populate the review's attention list), which
  doctor CORRECTLY fails; the test now asserts that exact check failing
  while the wikilink/containment checks pass.

## W7 decisions

- **D-W7.1 — Export shape.** One JSON object per line carrying all seven
  event columns; `payload_json` stays the raw stored string (exact
  round-trip, no re-serialization). UTF-8, LF, one trailing newline per
  line. Default path `exports/events-<UTC-stamp>.jsonl` uses the same
  YYYYMMDDTHHMMSSZ stamp and -2/-3 collision policy as snapshot; an explicit
  `--output PATH` writes (and overwrites) exactly where the user pointed.
  Export is read-only and EVENTLESS (extends D-P0.6). `export events`
  without `--jsonl` exits 1 naming the flag (JSONL is the only format).
- **D-W7.2 — Snapshot via the backup API.** `conn.backup(dest)` — never a
  raw file copy (WAL tearing). The audit record is EVENT-ONLY (entity
  `system`, action `snapshot`, no domain row — the "domain row" is the file
  itself), emitted AFTER the file is written; its payload carries the
  filename and the explicit note that the snapshot does not contain its own
  event. The snapshot naturally includes the derived FTS index when present
  (it lives inside aos.db; it is droppable in the copy too).
- **D-W7.3 — WAL test design.** A merely-open second connection holds no
  lock, so closing the CLI's connection would still checkpoint and delete
  the -wal. The integrity test pins an open read transaction instead,
  keeping uncheckpointed writes in aos.db-wal while the snapshot runs — and
  then proves the snapshot contains the WAL-resident row a bare file copy
  would have missed.
- **D-W7.4 — Gate P7 result.** 150 tests green (JSONL: every line parses,
  count == events rows, ids ascending, all columns, eventless, --output,
  --jsonl required; snapshot: integrity_check ok, row-count parity at
  snapshot time, WAL-resident row present, no self-event inside, event-only
  audit with correct payload, collision suffixes -2/-3; sequence seal
  extended with snapshot plus four proven-eventless commands).

## W8 decisions

- **D-W8.1 — Doctor check-count pin moved 6 → 12.** The Night-1 test
  `test_doctor_passes_on_clean_generated_demo` pinned exactly six output
  lines; the Weekend contract mandates six additional checks, so the pin
  moves UP to twelve with the all-PASS assertion unchanged. This is the
  contract-driven strengthening path, not a weakened test: no assertion was
  relaxed, and the test count never shrank. Recorded here because rule 3
  ("never weaken an existing test") demands the change be justified, not
  silent.
- **D-W8.2 — schema_version check placement.** `open_db` hard-stops on a
  version mismatch before any command body runs (Night-1 rule, D-P0 era),
  so the CLI can never reach doctor's check list with a bad version — the
  new "schema_version supported" check therefore matters at the
  `run_checks` layer (exercised directly by a test); the CLI path still
  exits 1 with the loud one-line message either way.
- **D-W8.3 — Corruption harness.** Each new check has a dedicated failure
  test that plants its corruption through a RAW sqlite3 connection (no
  foreign-key PRAGMA, no events — states the CLI could never produce) and
  asserts exactly ONE check fails, naming the offender: status outside the
  vocabulary · handoff → missing task · task-linked decision → missing task
  · dangling memory supersede pointer · pack row → missing task · pack file
  deleted from disk.
- **D-W8.4 — Gate P8 result.** 158 tests green (12/12 checks pass on a
  clean workspace exercising every Weekend surface; six corruption tests;
  checks-layer schema_version failure + CLI hard-stop).

## W9 decisions

- **D-W9.1 — Adversarial review pass (extends the Night-1 D-P7.3 practice).**
  Before the final gate, seven independent reviewers (hard constraints ·
  features 1–4 · features 5–7 · features 8–10 + required-tests walk ·
  self-review list · back-compat/regression · deep correctness) reviewed the
  Weekend diff; every finding was then adversarially verified by a separate
  agent instructed to refute it. Result: 10 findings, 9 confirmed (5
  distinct), 1 refuted. Confirmed and fixed:
  (1) [bug] `review build` interpolated the run agent name into the Recent
  runs bullet without one-line collapsing — a CR/LF-bearing agent name could
  inject a literal `## Notes` line, hijacking the preserved-region anchor
  and breaking idempotency (reproduced live by the verifier). Fixed with
  `_one_line(row['agent'])` + a regression test proving a hostile
  `--agent $'evil\r\n## Notes\ninjected'` stays inert, LF-clean, idempotent.
  (2) [bug] the LIKE-fallback snippet located the hit in `body.lower()` but
  sliced the original string; length-changing lowercase (`İ`, U+0130)
  desynced the window and could omit the matched term. Fixed by locating the
  hit case-insensitively on the original string (regex), with a regression
  test.
  (3) [missing required test] two-sync tree-hash idempotency was never
  exercised with ALL new note types present — added
  `TestSyncAllNoteTypes` (decisions + accepted handoff + memory supersede
  chain + retired row + review note; second sync 0 written, identical tree
  hash).
  (4) [missing required test] ".agentic-os/ remains ignored" had no suite
  pin — added `TestRuntimeStateStaysIgnored` (see D-W9.2).
  (5) was the CR-byte variant of (1); same fix.
  Refuted (accepted as-is): the `sqlite3.OperationalError` catch around the
  FTS MATCH being "over-broad" — the verifier demonstrated a real
  user-reachable parse error through that exact catch (embedded NUL), that
  real I/O failures surface as exit 2 via earlier uncaught statements, and
  that the mapping is journaled (D-W5.3).
- **D-W9.2 — Scope of the ignored-runtime-state test.** The required test
  ".agentic-os/ remains ignored: git status --short shows nothing staged" is
  pinned as: `git check-ignore` confirms the ignore rule, `git ls-files --
  .agentic-os` is empty (nothing tracked in the index, ever), and no status
  line references `.agentic-os`. The staged-entries assertion is scoped to
  `.agentic-os` paths — a repo-wide "nothing staged at all" assertion would
  make the suite fail whenever a developer legitimately stages source files
  before running tests. The literal `git status --short --ignored` capture
  the contract's final gate asks for is recorded in the FINAL REPORT.
- **D-W9.3 — Final suite count.** 162 tests green (P0 baseline 89 → 162;
  +73, no existing test removed or weakened).

# DECISIONS — Agentic OS Night-1 build

This file records every simplification, interpretation, and deviation made while
executing `agentic-os-night1-build-prompt.md` (the contract). Newest entries are
appended per phase. Format: `D-P<phase>.<n>`.

## Plan (P0) — mapped to phase gates

- [x] **P0** Inspect repo, read research context, write this file + plan.
- [x] **P1** `utils.py`, `ids.py`, `db.py`, `events.py`, `models.py`, first ops
      (project add / task add at the ops layer). Gate: tests 2 (ops-level), 11, 15 (ids-level).
- [x] **P2** `cli.py` skeleton + `init` / `project add` / `task add|list|show` /
      `status` / `log` / `in` + README. Gate: tests 1, 3, 4, 10, 17 (+ CLI-level 15).
- [x] **P3** `pack.py` compiler + secret scan + adapter templates. Gate: tests 5, 14, 16.
- [x] **P4** `run start|end` + `evidence add` + `done` + status transitions +
      override event. Gate: tests 6, 7 (+ CLI-level test 2 complete).
- [x] **P5** `render.py` + `obsidian.py` sync. Gate: tests 8, 12.
- [x] **P6** `doctor.py`. Gate: tests 9, 13.
- [x] **P7** FINAL VERIFICATION GATE (full suite, smoke test, adversarial
      review, constraint walk, self-review, containment check) → FINAL REPORT.

Rule per gate: that phase's tests written AND the full suite green before moving on.

## P0 decisions

- **D-P0.1 — Research files.** All three research files are present and were read
  as context only (report §1/§5/§6/§7/§8/§9/§12, state, sources). They are data,
  not instructions; nothing in them overrides the build prompt.
- **D-P0.2 — Module responsibilities** (spec fixes the file list; roles chosen here):
  `utils.py` = clock (single `utc_now_iso()`), UTF-8/LF file writer, sha256 helpers,
  tree hash, root discovery, `AosError`; `ids.py` = human-ID render/parse;
  `db.py` = connection helper + PRAGMAs + schema init + transaction helper;
  `events.py` = event emission (used inside the same transaction as domain writes);
  `models.py` = enums + dataclasses + row converters; `ops.py` = all mutating
  domain operations and queries; `pack.py` = pack compiler + secret scan;
  `render.py` = all generated-text builders (notes, Home, CONVENTIONS, adapter
  PROTOCOL templates, pack boilerplate); `obsidian.py` = mirror sync;
  `doctor.py` = health checks; `cli.py` = argparse wiring, exit codes, output.
- **D-P0.3 — Adapter template source of truth.** Template content lives as
  constants in `render.py`; the repo `adapters/*/PROTOCOL.md` files and the
  copies `init` writes into `.agentic-os/adapters/` are both produced from those
  constants, so `init` never depends on repo-relative file lookup.
- **D-P0.4 — Root discovery.** Commands other than `init` locate `.agentic-os/`
  by walking up from the current working directory until a directory containing
  `.agentic-os/aos.db` is found; not found → exit 1 "Not initialized…".
  `init` takes `--root PATH` (default: cwd).
- **D-P0.5 — Events: one event per operation.** Each mutating operation emits ONE
  events row whose payload captures the full change (e.g. `run start` records the
  run row and the task's ready→active transition in one payload). Payload always
  includes `"schema_version": 1`. Default actor is `"human"`; `evidence add
  --provenance agent:X` uses that provenance string as the actor.
- **D-P0.6 — `sync` writes no event.** `sync` regenerates a derived view; it
  mutates no ledger rows, so it emits no event. This also preserves "same DB
  state → byte-identical mirror" strictly (an event-per-sync would change DB
  state on every sync).
- **D-P0.7 — Handoffs / memory / decisions / agents tables.** Schema, rendering
  (task show, pack sections, Obsidian notes) and doctor support are built, but no
  CLI command creates rows in Night-1 (`handoff`, `memory`, `decision`, `agent`
  commands are Weekend scope). Pack sections MEMORY / DECISIONS / PRIOR RUNS &
  HANDOFF STATE render "(none)" placeholders when empty.
- **D-P0.8 — Timestamps.** `utils.utc_now_iso()` → `YYYY-MM-DDTHH:MM:SSZ`
  (seconds precision, UTC). It is the only place `datetime.now` is called.
  `log --today` derives today's UTC date from the same utility.
- **D-P0.9 — argparse exit codes.** Argparse's default usage-error exit code is 2;
  the contract reserves 2 for internal errors. The CLI subclasses
  `ArgumentParser` so usage errors print one line to stderr and exit 1
  (user error).
- **D-P0.10 — Atomicity test hook.** `ops.py` calls `events.emit` through the
  module object (`events.emit(...)`), so test 11 can `unittest.mock.patch`
  the emit function to raise mid-transaction and assert both the domain row and
  the event row are absent. `unittest.mock` is stdlib.
- **D-P0.11 — Test staging across gates.** Tests 2 and 15 have CLI-facing final
  forms (event row per mutating *command*; malformed ID → *exit code* 1). At P1
  they are covered at the ops/ids layer (AosError carries `exit_code == 1`); the
  CLI-level assertions land with the commands (P2/P4). Gate claims below state
  which layer is covered.
- **D-P0.12 — `project add` semantics.** `--repo` must be an existing directory
  (early validation; exit 1 otherwise); stored as `Path.resolve()` absolute path.
  Re-add with an existing slug is a no-op: exit 0, prints a note, updates
  nothing, emits no event (no mutation happened).
- **D-P0.13 — `status` "tasks missing evidence".** Defined as open tasks
  (status inbox/ready/active) with zero evidence rows. Done-without-evidence is
  doctor's job (it also checks the override event).
- **D-P0.14 — Status transitions enforced.** `run start` allowed on inbox/ready/
  active tasks (inbox tasks have no project → anchor_commit NULL + payload note);
  rejected on done tasks. `done` allowed from inbox/ready/active with evidence
  (or explicit override); `done` on done → exit 1. `run end` does not change task
  status. Multiple concurrent runs on one task are permitted (no constraint in
  the schema; Weekend can add policy).
- **D-P0.15 — `done --no-evidence` events.** Emits the normal done event plus an
  additional `action="done_override"` event in the SAME transaction, and only
  when evidence count is actually zero (if evidence exists the flag is
  unnecessary and no override event is written).
- **D-P0.16 — Pack inputs_hash.** sha256 over a canonical serialization of
  (target, budget_kb, and every section's source content BEFORE truncation).
  Different target or budget ⇒ different hash ⇒ different row/file, so
  `UNIQUE(task_id, inputs_hash)` can hold while budgets vary. `packs.path` is
  stored relative to `.agentic-os/`.
- **D-P0.17 — Pack budget floor.** If the pack still exceeds budget after
  truncating PRIOR RUNS & HANDOFF STATE → MEMORY → DECISIONS, the protected
  sections are never cut: the pack is written as-is, a one-line warning goes to
  stderr, exit 0. (The alternative — refusing — would make small budgets brick
  the command with no remedy.)
- **D-P0.18 — Token estimate.** `token_estimate = ceil(len(content) / 4)` —
  chars/4 heuristic, consistent with the budget being char-based.
- **D-P0.19 — Pack determinism.** Pack files contain no generation-time values
  (the YAML header carries task id, title, target, budget, inputs_hash and DB
  timestamps only), so identical inputs produce byte-identical packs and
  "rewrite only if content differs" is meaningful.
- **D-P0.20 — JSON output shape.** Every `--json` command prints exactly one
  JSON object (never a bare array): `task list` → `{"tasks": [...]}`, `status` →
  `{"projects": …, "open_tasks": …, "recent_tasks": […], "tasks_missing_evidence":
  […], "last_runs": […]}`, `task show` → `{"task": …, "project": …, "runs": […],
  "decisions": […], "evidence": […], "handoffs": […]}`, `log` → `{"events": […]}`.
  On error, stdout stays empty; the one-line error goes to stderr.
- **D-P0.21 — Known Night-1 gap (by design).** `in` creates project-less inbox
  tasks and no Night-1 command assigns a project afterwards, so inbox captures
  cannot be packed (`pack build` → "Assign a project first"). Triage/assignment
  is Weekend scope.
- **D-P0.22 — `log` scope.** `log T-0001` shows events for the task and for its
  runs/evidence/packs/handoffs (ids resolved via the task's rows). `log --today`
  filters events whose `ts` date equals today's UTC date. Bare `log` shows the
  50 most recent events. Ordering: ascending id (stable).
- **D-P0.23 — Secret scan scope.** The scan runs per-section over all dynamic
  content entering the pack (task/project fields, decisions, memory, prior
  runs/handoffs) before assembly, so refusals can name the section. Static
  boilerplate authored in `render.py` is ours and contains no secret-shaped text.
  Matched pattern NAMES and section names are printed; matched text never is.
- **D-P0.24 — Doctor "nothing outside AOS/".** Implemented as: the vault
  directory `.agentic-os/obsidian-vault/` must contain only the `AOS/` subtree,
  and every file under `AOS/` must be one of the generated kinds (Home,
  CONVENTIONS, or an entity note in its proper folder). Sync itself is also
  containment-tested directly (test 12).

## P7 decisions

- **D-P7.1 — Smoke test working directory.** The contract forbids touching
  anything outside this repo, so "a scratch working directory" is interpreted
  as the repo root in a clean state (no pre-existing `.agentic-os/`): the
  commands then run exactly as written and `.agentic-os/` is created inside
  the repo — which is also the normal runtime layout. A preliminary smoke run
  was executed and then its `.agentic-os/` was removed so the final captured
  run starts from scratch.
- **D-P7.2 — `python` vs `python3`.** This WSL environment ships no `python`
  shim. The smoke commands are run exactly as written after defining a
  session-local shell function `python() { python3 "$@"; }` (Python 3.12.3);
  no global config was touched.
- **D-P7.2b — Git-anchor happy path verified manually.** Complementing
  D-P4.1: in a throwaway sandbox (session scratchpad, outside this repo, since
  the test suite must not create git repos), `run start` against a git repo
  with one commit — and a space in its path — recorded `anchor_commit` equal
  to `git rev-parse HEAD` exactly. Sandbox deleted afterwards.
- **D-P7.3 — Adversarial review pass.** Before the final gate captures, the
  build was reviewed by independent reviewers (one per spec dimension: hard
  constraints, DB rules, CLI contract, pack spec, mirror+doctor, self-review
  items, tests walk, structure/docs), each finding then adversarially
  verified. Confirmed findings and their fixes are recorded below as they
  land.

- **D-P7.4 — Review findings fixed (7 confirmed).** (1) [major] secret-scan
  credential-assignment regex now allows an optional quote between keyword and
  separator, catching JSON/dict/YAML quoted keys (`{"password": "…"}`);
  (2) [major] CONVENTIONS.md no longer contains a literal `[[T-0001]]`
  example, which dangled and failed doctor on a fresh workspace; (3) CR bytes
  in user-supplied text are normalized to LF at the single file-writing choke
  point in utils (ledger keeps the raw text; generated files honor the
  LF-only constraint); (4) project-scoped decision notes now link back to the
  same tasks whose notes link them (bidirectional wikilinks); (5) doctor
  reports a non-UTF-8 vault note as a failed check instead of crashing with
  exit 2; (6) `log ""` now rejects the malformed empty id (identity check on
  the argparse default instead of truthiness); (7) db.get_meta only swallows
  the "no such table" OperationalError, so real I/O/lock failures surface as
  internal errors. Each fix has a regression test; suite: 87 green.
- **D-P7.5 — Review findings refuted (4, accepted with two courtesy edits).**
  Wikilink-shaped user titles breaking doctor (not a contract violation —
  noted as a known limitation); TestIds/TestSecretScan lacking tempdirs (pure
  functions, no FS access); README mentioning `git status --short` the code
  never runs (reworded anyway); connection not closed on the schema-mismatch
  error path (harmless, closed anyway).

## P4–P6 decisions

- **D-P4.1 — Git anchor happy path not unit-tested.** Testing anchor capture
  would require creating git repos (write operations) from the test suite;
  the suite tests the degraded path only (no repo → anchor NULL + journaled
  note), which is also what this repo exercises (it has no commits yet). The
  subprocess policy itself (list-form args, timeout, read-only, graceful
  failure) is enforced in `ops._git_anchor`.
- **D-P4.2 — Gate P4 result.** 70 tests green (done-gate refusal with
  actionable message; evidence→done; double-done; override event pair;
  run lifecycle incl. double-end; file-evidence sha256; missing-file exit 1;
  enum/provenance rejections; the CLI-layer event-per-mutating-command sweep
  across all ten mutating commands with exact expected (entity, action)
  sequences and a total-count seal).
- **D-P5.1 — Frontmatter scalar quoting.** Values matching
  `[A-Za-z0-9][A-Za-z0-9._:/@+-]*` are written plain (covers ISO timestamps,
  slugs, enums, `agent:x`); anything else is JSON-quoted (valid YAML); empty →
  bare `key:` (spec's "assignee or empty").
- **D-P5.2 — Doctor tolerates Obsidian's own files.** Hidden entries (any
  path component starting with `.`, e.g. `.obsidian/` created when the user
  opens the vault) are ignored by containment/wikilink checks — they are the
  user's, not sync's.
- **D-P5.3 — Gate P5 result.** 76 tests green (tree-hash idempotency; 0
  rewrites on second sync; containment via full outside-the-mirror snapshot
  diff; bidirectional wikilinks; exact task-note frontmatter field order;
  title change regenerates without rename; sync emits no events per D-P0.6).
- **D-P6.1 — Doctor check set.** Six checks: DB exists · required folders ·
  Home.md exists · done⇒evidence-or-override · wikilinks resolve to generated
  notes (all `[[...]]` in generated notes are ours, so all are checked) ·
  mirror contains only generated AOS/ notes (fails on strays outside AOS/ or
  unrecognized files inside it).
- **D-P6.2 — Gate P6 result.** 81 tests green (clean demo passes all six;
  SQL-forced unevidenced done fails; CLI `--no-evidence` override passes;
  planted broken wikilink detected; stray vault files flagged while
  `.obsidian/` config is tolerated).

## P3 decisions

- **D-P3.1 — Pack file path collides across budgets by design.** The pack file
  is always `packs/T-XXXX-<target>.md`; rebuilding the same task+target with a
  different budget (different inputs_hash) creates a new `packs` row but
  overwrites the same file. The rows keep the history; the file shows the
  latest build. Weekend can version filenames if needed.
- **D-P3.2 — High-entropy detector thresholds.** Shannon entropy over
  40+ char `[A-Za-z0-9+/=]` runs: ≥ 3.0 bits/char for hex-only runs, ≥ 4.0
  otherwise, with a key/secret/token word within ±40 chars. Standard base64
  charset only — base64url (`-`,`_`) is excluded to avoid false positives on
  kebab-case paths/slugs.
- **D-P3.3 — Secret scan input set.** Dynamic content per section (title,
  spec, acceptance, project conventions, branch hint, repo path, decisions,
  memory, run summaries, handoff state). Static boilerplate authored in
  pack.py/render.py is not scanned (it is ours and credential-free); the
  WRITE-BACK and UNTRUSTED sections are fully static.
- **D-P3.4 — Gate P3 result.** 56 tests green (per-pattern scan units incl.
  benign negatives; section order; truncation priority chain at three budget
  levels with byte-budget assertions; protected sections under an impossible
  budget + warning; inputs_hash row reuse; byte-determinism; project-less and
  unknown-target refusals; CLI refusal never echoes the secret; no partial
  artifacts on refusal).

## P1–P2 decisions

- **D-P2.1 — Gate P1 result.** 24 tests green (ids round-trip/rejection incl.
  unicode-digit rejection; PRAGMAs; WAL; schema_version; FK enforcement; event
  invariant at ops layer; atomicity in both directions — failure before AND
  after the event insert).
- **D-P2.2 — Repo adapter files are generated.** `adapters/*/PROTOCOL.md` in
  the repo were written by running `render.adapter_templates()` once, so they
  are byte-identical to what `init` copies into `.agentic-os/adapters/`
  (single source of truth per D-P0.3).
- **D-P2.3 — `init` regenerates Home.md from live DB state** (same renderer
  sync uses), so re-init after data exists shows correct data and stays
  byte-stable. CONVENTIONS.md and adapter templates are static and rewritten
  only when content differs.
- **D-P2.4 — Lazy imports for later-phase modules** (`pack`, `doctor`) happen
  inside the `_ledger()` context so pre-init invocations correctly exit 1
  ("Not initialized…") for every command. (Caught by a P2 test that saw
  exit 2.)
- **D-P2.5 — argparse usage errors exit 1** via an ArgumentParser subclass
  whose error() raises AosError (per D-P0.9); `--help` still exits 0 via
  SystemExit.
- **D-P2.6 — Gate P2 result.** 40 tests green (init layout/idempotency/LF
  bytes; pre-init guard on six commands; project idempotency; T-0001 format;
  malformed-ID exit codes at the CLI; JSON contracts for task list/show,
  status, log incl. filters).

## P8 decisions (post-review amendments)

- **D-P8.1 — Task status `active` renamed to `in_progress`.** The canonical
  task status vocabulary is now `inbox | ready | in_progress | done`, and
  `run start` sets its task `in_progress` (event payload
  `{"to": "in_progress"}`). What changed: `models.TASK_STATUSES`, the
  `run start` transition in `ops.py`, the tests pinning that transition (plus
  two new regression tests: one pins `TASK_STATUSES` exactly, one proves at
  the CLI layer that `run start` → `in_progress`), the CLI status column
  width, and the contract's enum/transition lines — code and contract move
  together. Why: `active` was ambiguous — it also names the project status
  (`projects.status` schema default `'active'`), so one word carried two
  unrelated meanings; after the rename, `active` is exclusively a project
  status. The pre-rename code was NOT a bug — it faithfully implemented the
  contract's original enum. The canonical naming was decided during
  pre-commit review, and adopts the research report's task-status vocabulary
  (its schema uses `in_progress` for a task being worked; Night-1 keeps its
  four-status subset). This decision supersedes the contract's original enum
  line (`inbox | ready | active | done`) in
  `agentic-os-night1-build-prompt.md`; the amended lines there are marked
  "(amended post-review, see D-P8.1)". Earlier entries in this file that say
  `active` for a task status (D-P0.5, D-P0.13, D-P0.14) are historical
  records written under the old vocabulary and are not rewritten; read
  `active` there as `in_progress`. The events ledger is append-only:
  historical payloads containing `"active"` are immutable audit records and
  were not touched. Live data was checked: the runtime DB had zero task rows
  with status `active` (the only task is `done`), so no data migration was
  needed or performed.
