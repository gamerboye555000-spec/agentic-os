# DECISIONS — Agentic OS v0.4 U-P2 trust-boundary amendment (Wave 0.5)

This section continues the `D-v0.4.*` series for the U-P2 Wave 0.5
trust-boundary replan: adopting the solo-maintainer honest-authority boundary
in `agentic-os-v0.4-u-p2-trust-boundary-amendment.md` after the independent
Wave 1 audit found the delivery checks self-modifiable from a pull-request
head. Branch `v0.4-u-p2-delivery-gate` (2026-07-22), amendment baseline
`184ec247067c7d05c0eb3d56916450cff66218f9`; the three untracked Wave 1 files
remain byte-identical and unstaged, and no implementation changed. The
amendment supersedes only the conflicting security and enforcement claims of
the frozen Wave 0 contract — §19's enforcement sentence, the §16/§17
characterizations, D-v0.4.43's unqualified evidence language, and any
adversarial reading of D-v0.4.34/D-v0.4.41 — and the contract file itself is
not edited. Prepended per the established precedent (D-W0.4, reaffirmed in
D-v0.2.7, D-v0.4.4); everything below stays byte-identical.

## D-v0.4 decisions (U-P2, Wave 0.5 trust-boundary amendment)

- **D-v0.4.45 — U-P2 adopts the solo-maintainer honest-authority boundary:
  honest-maintainer protection, with no adversarial tamper-resistance
  claim.** The audit finding is accepted as correct: the workflow, the
  canonical verifier, and the verifier's tests are all sourced from and
  modifiable on the pull-request head, so a repository writer can modify all
  three together, preserve the four public check names, and produce four
  green checks. The response reduces the claim, never the checks — every
  pin, permission, timeout, membership law, and assertion stands. U-P2
  guarantees: deterministic CI execution of the checked-in workflow,
  least-privilege permissions, immutable action pins, full test and
  distribution-smoke checks, detection of accidental or isolated drift,
  required checks that block ordinary failures, and a reproducible,
  auditable delivery process for an honest maintainer. U-P2 does not
  guarantee: tamper resistance against a writer who co-edits workflow,
  verifier, and tests; semantic immutability of a same-named check;
  protection against a repository administrator; an external or
  base-controlled authority; second-human approval; organization/enterprise
  required workflows; or a trusted GitHub App / external status provider.
  Rejected: rewriting the frozen contract in place (amendments supersede;
  history stays byte-identical — the rule D-v0.4.33 applied to U-P1);
  discarding or "fixing" the Wave 1 implementation (the checks are correct;
  the claim was wrong).

- **D-v0.4.46 — Self-modifiable required checks are identities, not
  independent authority.** Branch rules match check runs by name and enforce
  the conclusions reported under those names; for `pull_request` events
  every reporting byte — workflow, verifier, and verifier tests alike —
  is sourced from the PR head. An unchanged name therefore proves nothing
  about unchanged semantics, and a green `workflow-integrity` proves only
  that the head's verifier accepted the head's workflow. Isolated or
  accidental drift is still detected — each of the three files is caught by
  the other two when edited alone — while a simultaneous self-consistent
  edit of all three passes by construction. The chain never leaves the head,
  so no Wave 2 refinement of the three files can close it; closing it
  requires an authority the head cannot modify (D-v0.4.48). This supersedes
  any reading of D-v0.4.34 or D-v0.4.41 under which frozen names or the
  verifier constitute independent enforcement. Rejected: treating the
  finding as a Wave 1 defect (self-attestation from modifiable content is
  structural, not a bug); silently keeping the stronger claim (an overclaim
  no probe can witness).

- **D-v0.4.47 — Solo topology: zero required approvals stand; code-owner
  review is deferred, not partially adopted.** The repository is public,
  owner type User, one active maintainer; pull-request authors cannot
  approve their own pull requests, so CODEOWNERS + required code-owner
  review would deadlock every owner-authored PR against a reviewer who does
  not exist. The `main-delivery-gate` ruleset keeps its frozen shape — pull
  request required, four required checks, branch up to date, force-push and
  deletion restrictions, conversation resolution, merge-commit only, zero
  required approvals — reclassified as ordinary failure enforcement and
  accidental-change governance, never independent tamper resistance.
  Rejected: requiring one approval now (permanent self-deadlock, or a
  rubber-stamp second account — both worse than the honest zero);
  `pull_request_target` as an improvised base authority (a privileged
  base-context workflow needs its own threat model and has no proven
  latest-head required-check semantics; the D-v0.4.35 ban stands).

- **D-v0.4.48 — External or base-controlled authority is trigger-gated
  future work, never hidden U-P2 scope.** Adversarial tamper resistance
  becomes a separate follow-on unit — its own contract, decisions, and
  proofs — when any one trigger is met. Trigger A, second trusted human:
  collaborator with write access; base-branch `.github/CODEOWNERS`
  protecting the workflows tree, the verifier, the delivery-gate tests, and
  the delivery contract/amendments; at least one required approval with
  code-owner review; stale-approval dismissal; approval by someone other
  than the most recent pusher; proof the author cannot self-satisfy the
  rule. Trigger B, organization/enterprise topology: the authority workflow
  placed outside the modifiable head, required through org/enterprise
  rulesets, verified to evaluate the latest PR commit, with proof a PR
  cannot replace or suppress it. Trigger C, trusted GitHub App or external
  check: a separately administered provider bound as the required-check
  source, evaluating the latest head, with isolated credentials and hosting;
  incident, key-rotation, availability, and recovery procedures; and proof a
  repository writer cannot forge the check. Rejected: building the App
  inside U-P2 (credentials, hosting, webhook, deployment, incident, and
  operator scope disproportionate to a delivery-gate unit); pre-implementing
  fragments of A/B/C now (a half-authority invites exactly the false trust
  this amendment removes).

- **D-v0.4.49 — Probe evidence is limited to ordinary failure
  enforcement.** The frozen failing-test probe proves exactly three things:
  a real failing test creates failed required checks on the exact probe
  head; the merge is blocked while those checks fail; the probe closes
  without merging. It does not prove that same-name check semantics are
  immutable, that a co-edited workflow cannot report green, or that an
  administrator cannot bypass or change the ruleset. D-v0.4.43's "the only
  accepted enforcement evidence is the probe" is qualified to: the only
  accepted evidence of ordinary failure enforcement. Every other D-v0.4.43
  element — bootstrap order, ruleset shape, probe procedure, close-unmerged
  discipline, ABSENT never reported as GREEN — stands. No malicious or
  same-name-neutering probe PR is created or merged in Wave 0.5 or later:
  the neutering case is analyzed on paper in the amendment (§7) because a
  live rehearsal against the real repository would prove nothing the
  analysis does not already establish. Rejected: a live neutering
  demonstration (an attack rehearsal normalized into repository history,
  with no governed value).

- **D-v0.4.50 — Wave 0.5 landing sequence, commit-sequence extension, and
  file/delivery-boundary extension; D-v0.4.44 extended, not rewritten.** The
  independent audit that produced this amendment also fixes the order in which
  the remaining U-P2 work lands, and extends the frozen delivery metadata of
  D-v0.4.44 without touching it. Landing sequence, frozen normative: Wave 0.5
  lands first as one documentation-only commit containing exactly `DECISIONS.md`
  and `agentic-os-v0.4-u-p2-trust-boundary-amendment.md`; no Wave 1 file is
  staged or committed before that Wave 0.5 commit exists; after it, the three
  Wave 1 files receive a renewed independent technical audit under the
  honest-maintainer boundary (D-v0.4.45), and only a PASS — or a
  corrected-and-re-audited PASS — permits Wave 1 staging; Wave 2 and Wave 3
  remain blocked until Wave 0.5 is committed, the renewed Wave 1 audit passes,
  and Wave 1 is committed; ruleset activation and the failing-test probe remain
  post-workflow-bootstrap activities (D-v0.4.43, as qualified by D-v0.4.49);
  and U-K1, U-T1, U-W1, and U-A4 remain blocked until U-P2 is fully merged and
  closed. Commit sequence: D-v0.4.44's four-item, one-per-wave sequence is
  extended — not replaced — by inserting exactly one Wave 0.5 commit, `docs:
  adopt U-P2 solo-maintainer trust boundary`, at position 2, between Wave 0's
  `docs: freeze U-P2 protected delivery contract` and Wave 1's `ci: add
  immutable read-only validation workflow`; the other three original messages
  are preserved verbatim, giving five ordered commits, and the claim that the
  complete U-P2 history is four commits no longer holds. File and delivery
  boundary: D-v0.4.44's "nothing else" boundary applied to its original
  Wave 0/1/2/3 table; this decision adds exactly one governed wave — Wave 0.5 —
  authorizing exactly two paths (`DECISIONS.md`,
  `agentic-os-v0.4-u-p2-trust-boundary-amendment.md`) and one commit, and no
  production, packaging, protocol, schema, migration, or unrelated
  documentation file. The amendment (§13, §14, §15) carries the extended
  sequencing and boundary; D-v0.4.44 and the original contract stay
  byte-identical history, neither reworded nor erased. Rejected: rewriting
  D-v0.4.44 in place (frozen Wave 0 history — amendments supersede, history
  stays byte-identical, per D-v0.4.33/D-v0.4.45); folding Wave 0.5 into the
  Wave 1 commit (the audit finding is a governed documentation change that must
  land and be independently visible before any Wave 1 file is staged); staging
  any Wave 1 file now (the renewed audit gate has not run).

# DECISIONS — Agentic OS v0.4 U-P2 continuous integration and protected delivery gate

This section continues the `D-v0.4.*` series for the U-P2 Wave 0
contract-freeze pass: freezing the delivery-gate architecture of
`agentic-os-v0.4-u-p2-delivery-gate-contract.md` on branch
`v0.4-u-p2-delivery-gate` (2026-07-22), from baseline
`ef66fd4297491a5856b6d2602da8e3994e5359bd`. All mutable facts below were
resolved from primary sources on 2026-07-22 and cross-checked against two
independent signals; none were frozen from memory. Prepended per the
established precedent (D-W0.4, reaffirmed in D-v0.2.7, D-v0.4.4); everything
below stays byte-identical.

## D-v0.4 decisions (U-P2, Wave 0 contract freeze)

- **D-v0.4.33 — U-P2 is a new unit that closes U-P1's explicitly deferred
  delivery gap.** The U-P1 contract's scope section reads, verbatim: "Out of
  scope (explicitly not done in this pass): CI, release publishing, branch
  protection, …". U-P2 closes CI and branch protection; release publishing
  stays excluded (no PyPI, no GitHub Release, no signing, no SBOM, no
  containers, no auto-tagging). U-P1 remains a historically correct,
  unmodified record. Rejected: amending U-P1 (frozen contracts are immutable
  history); starting U-A4 first — `agentic_os/protocols.py:1005` records
  that passport skill/tool requirement resolvers are deferred to U-K1/U-T1,
  so U-A4 would build on contracts that do not exist. The dependency-safe
  sequence after U-P2 is U-K1/U-T1 (either order) → U-W1 → U-A4.
  **Non-goal**: no runtime, schema, protocol, CLI, power, or doctor change —
  the doctor count (41), test count (2,275) and schema version (5) verified
  at baseline must be identical after U-P2.

- **D-v0.4.34 — Four stable public check identities, with an explicit job
  id / job name split.** The frozen required-check names are
  `workflow-integrity`, `tests-python-3.12`, `tests-python-3.14`,
  `distribution-smoke-python-3.12`. GitHub job ids cannot contain `.`
  (alphanumerics, `-`, `_` only), so the dotted public names are carried by
  the jobs' `name:` values — which is what required-status-check rules match
  — while the ids use hyphens (`tests-python-3-12`, …). Once the ruleset
  depends on these names, any rename is a governed migration touching
  ruleset, workflow, verifier and docs in one reviewed change. Rejected: a
  Python-version job matrix (renders `tests (3.12)`-style names, surrendering
  the frozen identities); `needs:` chaining (a failed early job leaves later
  required checks skipped rather than independently reported — four
  independent jobs report four independent truths on every run).

- **D-v0.4.35 — Least-privilege workflow law.** Exactly one top-level
  `permissions: contents: read` block; job-level `permissions:` blocks are
  forbidden entirely (an elevation is a violation, and a "redundant
  read-only" block is shape noise the verifier would have to special-case —
  both are refused). No secret contexts, no `pull_request_target` in any
  form, `persist-credentials: false` on every checkout, no artifact
  upload/download, no `continue-on-error`, no `curl`/`wget`, no `sudo`, no
  repository writes, no branch/tag commands. This is least-privilege, not
  isolation: no repository secrets are exposed to jobs; the workflow
  receives a read-only `GITHUB_TOKEN`; `persist-credentials: false` keeps
  that token out of on-disk Git configuration; the token is not explicitly
  passed to test shell steps; the pinned actions may internally receive the
  read-only token where they require it. GitHub-hosted runners retain
  outbound network access and U-P2 provides no egress sandbox, so the
  `curl`/`wget` ban is canonical workflow-shape hygiene, not a network
  isolation control — untrusted PR code can transmit anything it can read
  from the runner, and no artifact-upload action is configured. Stating
  these limits honestly does not weaken the least-privilege law.

- **D-v0.4.36 — Immutable two-entry action allowlist with frozen full-SHA
  pins.** Every `uses:` reference must be one of exactly:
  `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` (v7.0.1,
  published 2026-07-20) and
  `actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97` (v7.0.0,
  published 2026-07-20). Release names may appear in comments only; `@vN`,
  `@main`, and release-tag refs are forbidden in the executable field.
  Provenance: each tag→SHA mapping was resolved on 2026-07-22 via two
  independent primary-source signals in agreement — `git ls-remote` against
  the official repository and the GitHub REST `git/ref/tags/…` object —
  with release identity from the official releases endpoint. Wave 1
  re-resolves both mappings before writing `ci.yml`; any mismatch is a stop
  condition (possible tag retarget), never a silent update. checkout v7's
  headline change (blocking fork-PR checkout under `pull_request_target`) is
  hardening that cannot affect a workflow where `pull_request_target` is
  banned outright.

- **D-v0.4.37 — Interpreter matrix: 3.12 floor plus 3.14 current stable
  line; lines frozen, patches logged.** Resolved 2026-07-22 from two official
  sources in agreement: python.org/downloads (latest stable 3.14.6,
  2026-06-10) and devguide.python.org/versions (3.14 status `bugfix`; 3.15
  `prerelease` due 2026-10-01; 3.12 `security`). `setup-python` receives the
  feature-line strings `"3.12"` and `"3.14"`; every job prints `python3 -VV`
  so the exact resolved patch is recorded per run. Rejected: pinning exact
  patch versions (CI would test a stale patch instead of the line users
  install, and patch churn would require constant governed edits); adding
  3.13 (neither the floor nor the current stable line). Python 3.15 adoption
  after its stable release is a future governed change.

- **D-v0.4.38 — Exact-pinned CI-only build tools, build isolation disabled,
  yanked release refused.** The distribution-smoke job installs exactly
  `pip==26.1.2`, `build==1.5.0`, `setuptools==83.0.0`, `packaging==26.2`,
  `pyproject_hooks==1.2.0`, then logs `pip freeze`, then builds with
  `python -m build --wheel --no-isolation` so the exact-pinned backend is
  the one that builds (isolation would re-resolve setuptools from the
  network at build time — precisely the drift this unit exists to prevent).
  The cross-check rule earned its keep immediately: pypa/build's newest
  GitHub release is 1.5.1 (2026-07-09), but 1.5.1 **is yanked on PyPI**, so
  1.5.0 — the newest non-yanked release — is frozen instead; pinning a
  yanked release is forbidden. The `wheel` package is deliberately not
  installed (setuptools ≥ 70.1 provides native `bdist_wheel`; current wheel
  0.47.0 recorded for reference); if Wave 1's smoke disproves this, adding
  `wheel==0.47.0` is a recorded amendment. Runtime dependencies remain
  `[]`. **Deferred**: `--require-hashes` artifact-hash pinning, to a future
  supply-chain unit.

- **D-v0.4.39 — Runner pinned to the explicit `ubuntu-24.04` label.**
  `ubuntu-latest` is a mutable alias (it retargets when GitHub promotes a
  new LTS image) and is forbidden for the same reason mutable action tags
  are. Verified 2026-07-22 from the official actions/runner-images source:
  `ubuntu-latest` currently maps to 24.04; `ubuntu-26.04` exists but is
  preview (no Actions SLA) and is rejected; arm and slim variants rejected
  (the gate proves the supported x64 environment). Moving to a newer image
  is a governed change.

- **D-v0.4.40 — No artifact upload; disposable `$RUNNER_TEMP` roots;
  fail-closed membership law; clean-tree assertion.** CI uploads nothing —
  no database, vault, workspace, log, coverage, wheel, or zipapp artifact
  ever leaves the runner. The wheel and zipapp final artifacts and the
  disposable smoke workspaces live under `$RUNNER_TEMP`, outside the
  checkout, with `PYTHONPATH` unset and smoke commands run from outside the
  repository; but `python -m build --wheel --no-isolation` may create
  `build/` and `agentic_os.egg-info/` inside the checkout — build
  intermediates, gitignored at baseline (`build/`, `*.egg-info/`), never
  permitted wheel members except the built wheel's legitimate `.dist-info`
  metadata. Because ignored residue is invisible to `git status
  --porcelain`, cleanliness cannot rely on porcelain alone: the smoke job
  removes exactly those known intermediates in a bounded cleanup step (never
  `git clean`) and asserts their absence, checking the known paths both
  before and after cleanup; unexpected ignored residue is still a failure
  and source files must stay byte-identical. Wheel and zipapp membership are
  asserted against allowlists (wheel: `agentic_os/**/*.py`,
  `agentic_os/catalog/*.json`, dist-info; zipapp: root `__main__.py`,
  `agentic_os/**/*.py`, the individually-validated catalog files per
  D-v0.4.14) so an unexpected new name fails closed; no ledger, backup,
  vault, credential, cache, repo-metadata, prompt-pack, or test content can
  ship. Every job ends by asserting `git diff --exit-code` and an empty
  `git status --porcelain`, and the smoke job additionally asserts the known
  build intermediates are absent.

- **D-v0.4.41 — A stdlib-only workflow-integrity verifier enforcing a frozen
  canonical byte-grammar, with a closed 20-reason vocabulary.**
  `tools/verify_ci_workflow.py` enforces the one frozen canonical workflow
  contract by canonical byte-grammar recognition, not substring scanning: it
  is deliberately not a general YAML parser or Actions linter, and it
  affirmatively recognizes the full frozen workflow shape rather than
  searching for banned substrings, so `.github/workflows/ci.yml` is accepted
  only when every byte and construct belongs to the single frozen canonical
  grammar and any unrecognized construct fails closed with
  `unexpected_workflow_shape`. The frozen representation fixes one
  deterministic form — UTF-8, LF only, no BOM, exact key ordering where the
  verifier depends on ordering, exact job ids and `name:` values, exact
  allowed steps and command blocks, and the exact action allowlist with full
  SHAs — and classifies as non-canonical and refusing every YAML anchor,
  alias, custom tag, duplicate key, document start/end marker,
  multiple-document stream, flow-style mapping or sequence, quoted or escaped
  mapping key, alternate boolean spelling, job-level `permissions:` block,
  local action, reusable workflow, multiline/folded `uses:`, unexpected block
  scalar, unknown job/step/key/ordering, and shell indirection that replaces
  a frozen command. Interface: default target `.github/workflows/ci.yml`,
  `--workflow PATH` override; exit 0 only with zero findings, 1 with findings,
  2 on usage error; one finding per line, deterministically ordered by
  (reason, locus). Diagnostics are value-free and bounded: a reason code from
  the closed vocabulary (`missing_workflow`, `invalid_utf8`, `crlf_present`,
  `mutable_action_ref`, `unapproved_action`, `credential_persistence`,
  `write_permission`, `pull_request_target`, `secret_reference`,
  `continue_on_error`, `missing_timeout`, `missing_required_job`,
  `missing_required_trigger`, `missing_python_line`, `missing_full_suite`,
  `missing_distribution_smoke`, `artifact_upload`, `shell_download`,
  `unexpected_workflow_shape`, `internal_error`) plus at most a closed-set
  locus (frozen job id, frozen trigger name, or `line:<n>`); arbitrary
  workflow content is never echoed, so a hostile workflow cannot use the
  verifier as an output channel, and malformed bytes yield findings, never
  tracebacks. `internal_error` is the twentieth code: a top-level exception
  guard wraps the whole run so any unexpected internal failure exits 1 with
  one fixed, value-free diagnostic — no traceback, no exception message, and
  no file content echoed — ordered deterministically with the other findings.
  Rejected: a third-party linter (violates the zero-dependency law and imports
  someone else's policy); free-text diagnostics (a leak channel and an
  unstable test surface). Tests must prove every reason reachable and the
  output value-free, and Wave 1 must add a mutation test for every bypass
  class named above.

- **D-v0.4.42 — Bounded timeout ceilings and ref-scoped concurrency with
  PR-only cancellation.** `timeout-minutes`: 10 for `workflow-integrity`, 30
  for each remaining job. Timeout basis, recorded with the evidence that does
  exist: the known local final U-A3 full-suite runtime is 2,275 tests in
  763.307 seconds (~12.72 minutes). That is local hardware evidence, not
  GitHub-hosted-runner evidence; the 30-minute test-job ceiling is
  approximately 2.35 times that local runtime, and the 10-minute integrity
  ceiling remains separate. No hosted-runner CI duration exists yet (no prior
  workflow ever ran), so the ceilings are deliberately generous runaway
  bounds, not performance targets: the first live U-P2 runs must record the
  actual hosted durations, any timeout change requires a governed amendment,
  and a timeout must never be increased merely to hide a hang. Tightening from
  observed data is a normal governed change; raising a ceiling is a red flag
  requiring investigation first. Concurrency: `group: ci-${{ github.ref }}`
  with `cancel-in-progress: ${{ github.event_name == 'pull_request' }}`. PR
  runs for the same PR may be canceled when superseded; `main` runs use
  `cancel-in-progress: false`. This does not guarantee a completed run for
  every mainline commit: GitHub may still cancel an older *pending* run in the
  same concurrency group when a newer `main` run is queued, and only the
  newest queued `main` run is guaranteed to complete, so an intermediate main
  commit may lack a completed run. A missing historical run can be re-created
  with `workflow_dispatch` against the relevant commit or ref where GitHub
  permits. U-P2 therefore does not claim immutable CI evidence for every
  `main` commit, and never claims queue preservation GitHub does not provide.

- **D-v0.4.43 — Bootstrap sequence, `main-delivery-gate` ruleset, and the
  failing-probe enforcement proof.** Order is fixed: workflow merges first
  (checks must exist before rules can require them), then the operator
  creates repository ruleset `main-delivery-gate` targeting `main`:
  enforcement Active; bypass list empty (the administrator is subject to the
  rules; the accepted escape hatch is editing the ruleset itself, which is
  documented rather than pre-weakened); restrict deletions; block force
  pushes; require a pull request (0 required approvals — one active
  maintainer, no unavailable external approver; conversation resolution
  required; merge-commit only); require the four frozen checks with
  branch-up-to-date. Availability was triangulated on 2026-07-22 (public
  repository; GitHub Free provides the full feature set on public
  repositories; the live rulesets endpoint answers normally) — but
  configuration is never trusted on faith: the only accepted enforcement
  evidence is the probe. Frozen probe: branch `probe/u-p2-required-check`
  from post-merge `main`; a single new deliberately-failing test file
  `tests/test_probe_delivery_gate.py`; PR titled
  `probe(v0.4): U-P2 failing required-check probe — do not merge`; observe
  both test checks FAILED on the exact probe head and merge blocked; close
  unmerged; delete the branch; record the evidence. Protection is never
  weakened to complete a proof, and ABSENT is never reported as GREEN.

- **D-v0.4.44 — Frozen delivery metadata and exact file boundary.** PR
  title: `ci(v0.4): U-P2 — add protected deterministic delivery gates`;
  merge mode: normal merge commit (repository convention, API-confirmed
  enabled); milestone: annotated tag `milestone/v0.4-u-p2-delivery-gate` on
  the merge commit after post-merge tree-equality verification
  (`origin/main^{tree}` must equal the feature head's tree); never renamed
  after push. There are 19 existing `milestone/*` tags at the Wave 0
  baseline: 13 annotated and 6 lightweight; U-P2 deliberately uses an
  annotated milestone tag, following the newer annotated convention, and
  historical tags are not rewritten. File
  boundary: Wave 0 touches exactly this contract and DECISIONS.md; Wave 1
  adds exactly `.github/workflows/ci.yml`, `tools/verify_ci_workflow.py`,
  `tests/test_v04_delivery_gate.py`; Wave 2 refines only those three; Wave 3
  touches exactly `README.md`, `CONTRIBUTING.md` (new — confirmed absent at
  baseline), `TROUBLESHOOTING.md`. Every other path — all of `agentic_os/`,
  `aos.py`, `aos_hooks.py`, `pyproject.toml`, `protocols/`, the existing
  tools and tests, schema and migrations — is untouchable; a production
  module entering the diff is a stop condition, and a pre-existing
  entrypoint defect exposed by CI becomes a separate maintenance unit, never
  a fix-forward inside U-P2.

# DECISIONS — Agentic OS v0.4 U-A3 governed agent routing and handoff contracts

This section begins the continuation of the `D-v0.4.*` series for the U-A3
Wave 0 contract-freeze pass: reconciling the approved design
(`U-A3-routing-handoffs-design.md`) with the independent audit
(`U-A3-routing-handoffs-audit.md`, verdict ADOPT WITH REQUIRED CORRECTIONS —
3 blockers, 6 majors, 9 minors) into
`agentic-os-v0.4-u-a3-routing-handoffs-contract.md`, on branch
`v0.4-u-a3-routing-handoffs` (2026-07-17). Prepended per the established
precedent (D-W0.4, reaffirmed in D-v0.2.7, D-v0.4.4); everything below stays
byte-identical.

## D-v0.4 decisions (U-A3, Wave 0 contract freeze)

- **D-v0.4.21 — Distinct governed agent-handoff tables, separate from
  legacy `handoffs`.** `agent_handoffs` + `agent_handoff_transitions` are
  new tables, not an extension of the existing free-text `handoffs` table.
  The legacy table's `from_agent`/`to_agent` are unvalidated free text,
  carry no CHECK, no hash, and a mutable `accepted_at` — none of which its
  historical rows could satisfy under governed rules without the migration
  fabricating identities and pins for names that were never validated,
  which D-v0.4.4 already forbids. Rejected: extending the legacy table
  (fabrication); canonical artifacts with no relational state (loses FK
  integrity, SQLite's compare-and-swap concurrency, and the backup/snapshot
  perimeter). The legacy table, its two CLI leaves, its events, its mirror
  notes and its `H` id prefix stay byte-identical — D-v0.4.20 reserved this
  ground for U-A3 explicitly, and this decision is how that reservation is
  spent. **Deferred**: any future unification of the two handoff concepts.
  **Non-goal**: no migration path from a legacy handoff row to a governed
  one is provided or implied.

- **D-v0.4.22 — Schema v5: four additive tables, zero new protocols, DDL
  hardened past the original design.** `routing_plans`,
  `routing_plan_candidates`, `agent_handoffs`, `agent_handoff_transitions`
  are added under migration `u-a3-routing-handoffs-v5` (4→5), built from
  the same `{table}`-parameterized DDL constants a fresh `init` composes
  (D-v0.3.42), so fresh and migrated schemas are byte-identical for these
  four tables. Every table carries constraints no existing table could
  express: `routing_plan_candidates` gains a composite
  `FOREIGN KEY(agent_id, passport_version) REFERENCES
  agent_passports(agent_id, version)` — without it, an eligible candidate
  could pin a passport version that does not exist or belongs to another
  agent, and nothing would refuse it until doctor caught it after the fact;
  `routing_plans` gains two additional `result_status` CHECKs so
  `resolved`/`unresolved`/`no_eligible_candidates` are all biconditional in
  `(eligible_count, unresolved_count)`, closing a hole where a plan could
  claim `no_eligible_candidates` while genuinely unresolved candidates
  existed; both `routing_plans` and `agent_handoffs` gain
  `CHECK (supersedes_id IS NULL OR supersedes_id < id)`, making every self-
  and n-cycle structurally impossible, since rowids only increase and
  neither table has a DELETE path; `agent_handoff_transitions` gains
  `CHECK (from_state <> 'accepted' OR to_state IN ('cancelled','superseded'))`,
  closing the two illegal edges (`accepted→refused`,
  `accepted→clarification_required`) the enum CHECKs alone left
  representable. Precedent for all four: `MEMORY_EDGES_DDL` and
  `MEMORY_SOURCES_DDL` already establish that a domain rule the application
  enforces should also be unstorable by raw SQL wherever a CHECK can
  express it; doctor remains the backstop only for what SQLite genuinely
  cannot express (sequence contiguity, chain replay, cross-row
  equivalence). No new U-X1 protocol identity is introduced: routing
  requests, plans, handoffs and transitions are workspace-local records
  pinned to local ids and digests that cannot travel between workspaces, so
  there is no interoperability surface to justify one — `protocols.py` and
  every protocol artifact stay byte-identical. **Deferred**: a
  cross-workspace handoff-exchange protocol (`beast.agent-handoff/vN`) if a
  future unit ever needs one. **Non-goal**: no index is added in this pass
  (D-v0.4.28).

- **D-v0.4.23 — Autonomy is unordered membership, never a ladder.**
  `AGENT_AUTONOMY_LEVELS = ("declare_only","suggest","supervised","scoped")`
  is a closed, **unordered** vocabulary; the routing request's
  `required_autonomy` field is an array of 1..4 unique values matched
  against the agent's declared passport `autonomy` by set membership only,
  producing `autonomy_mismatch` on a miss. No `autonomy_rank` function is
  written, and none may be. This reverses an `autonomy_ceiling` (a single
  value compared by rank ≤) considered during Wave 0 review and rejected:
  U-A1 published `autonomy` as an inert declaration ("nothing in U-A1 reads
  it"), so ranking it now would retroactively redefine every value already
  stored in every published passport; `supervised` and `scoped` name
  orthogonal properties (supervision presence vs. scope boundedness) with
  no forced order, so a ceiling would have to guess an answer for the one
  comparison that matters most; and a rank is rank inference over a
  declaration — exactly what this same request schema refuses one field
  over, for `data_classification` (D-v0.4.32). Precedent for the
  unordered-and-say-so shape: `MEMORY_SENSITIVITIES` carries an explicit
  authoritative-order warrant because its order is load-bearing;
  `AGENT_AUTONOMY_LEVELS` carries the deliberate inverse comment because
  its order is not. **Deferred**: an autonomy ladder remains possible in a
  future unit, but only with its own decision record and its own evidence
  that the levels are genuinely comparable — evidence that does not exist
  today. **Non-goal**: U-A3 does not read, write, or reinterpret any
  previously published passport's `autonomy` value; existing declarations
  are unaffected.

- **D-v0.4.24 — `decision_id` is a rationale reference, not an approval.**
  `agent_handoffs.decision_id` is an optional FK to `decisions(id)`, read
  only as a pointer to the architecture-decision record that explains *why*
  a delegation was declared. It is not an approval, not authorization, not
  consent, not a grant, not a policy decision, and not an execution
  permission, and no U-A3 code reads it as a condition for allowing any
  operation — a handoff with `decision_id` NULL and one with `decision_id`
  set behave identically on every verb. This is forced by what `decisions`
  actually is: an ADR table (`title`, `decision_md`, `alternatives_md`,
  `status`, `decided_at`) with no approver column, no subject, no grant, no
  scope, and no foreign keys at all; `status` carries no CHECK constraint
  and is hardcoded to `'accepted'` by its one writer (`ops.add_decision`),
  and no CLI verb ever changes it. Describing a pointer into that table as
  an "approval reference" — language considered during Wave 0 review and
  rejected — would have manufactured an authorization primitive the system
  does not have, inviting a future orchestration unit to gate execution on
  `decision_id IS NOT NULL` over a column that is, in truth, unconstrained
  free text defaulted to `accepted`. **Agentic OS currently has no governed
  approval primitive for these handoffs**, and this decision records that
  fact rather than papering over it. **Deferred**: any future unit that
  wants real approval semantics must build a dedicated approval primitive
  and must not repurpose `decision_id` to mean one. **Non-goal**: this
  decision does not change the `decisions` table, `ops.add_decision`, or
  any existing consumer of a `decisions` row.

- **D-v0.4.25 — Routing-plan post-commit immutability, built on the
  `_PENDING_HASH` precedent.** `routing_plans` and `routing_plan_candidates`
  rows are immutable after commit — no command reaches them with an UPDATE
  or DELETE once their creating transaction has closed. Within that one
  creating transaction only, the parent plan row is inserted with
  `content_sha256=_PENDING_HASH` (the empty string), each candidate row is
  inserted the same way, each candidate's hash is finalized by an UPDATE
  immediately after its insert (needed because a record hash binds its own
  row id, which SQLite only assigns at INSERT), the ordered chain of
  recomputed candidate digests is built by `routing_plan_candidates.id`
  ascending, and the plan's own hash is finalized last, over that chain.
  This is the exact `_PENDING_HASH` two-step already established for
  memory claims (`ops.py`: "the id is only known after the INSERT — so the
  two-step is unavoidable … invisible: no other connection can observe an
  open transaction"), applied to routing for the first time. No digest
  input ever includes a `content_sha256` column, so the construction is
  acyclic: plan-id → candidate rows → candidate digests → plan hash. A
  `_PENDING_HASH` value that survived a crash does not have the 64-hex-
  character shape a real hash has, and is reported as `malformed` by
  doctor and by `route verify`, never mistaken for a real one.
  **Deferred**: nothing — this is the complete, permanent hash-construction
  rule for both tables. **Non-goal**: this decision does not create any
  UPDATE path reachable from a normal command after commit; the
  hash-finalization UPDATEs are internal to `routing.create_plan` alone.

- **D-v0.4.26 — A handoff is an append-only transition history plus a
  mutable, hash-coupled current-state projection.**
  `agent_handoff_transitions` rows are immutable and append-only; on
  `agent_handoffs`, every column is likewise immutable except `state`,
  `updated_at` and `content_sha256`, which move together — always in the
  same transaction as the transition row that justifies them, always with
  exactly one event — and never otherwise. A freshly created handoff has
  zero transition rows, `state='proposed'`, and a hash bound over an empty
  chain; every subsequent verb appends exactly one transition row
  (chain-ordered by `seq`, not by row id) and recomputes the projection
  over the intended new state in one UPDATE, so no intermediate "state
  moved but hash didn't" row can exist even inside the transaction. The
  projection is fully derivable by replaying the chain from `proposed`; it
  is stored because it is what compare-and-swap reads and what `list`
  filters on, and doctor 39 is what proves the stored projection and the
  replayed history agree. This is chosen over deriving `state` purely from
  the event log (events are audit projections, deliberately not
  authoritative) and over one immutable successor row per transition
  (which reintroduces a moving-pointer integrity problem at higher cost
  than the composite-FK pattern already solves for passports).
  **Deferred**: nothing about the shape; a future unit may add a
  `completed` state to this same machine once it has execution-outcome
  facts to bind it to. **Non-goal**: this decision does not make any
  `agent_handoffs` column other than the three named ones mutable.

- **D-v0.4.27 — Supersession is expressed only at successor creation;
  plans derive it, handoffs also store it.** `supersedes_id` on both
  `routing_plans` and `agent_handoffs` is written only when a successor is
  created and is never updated afterward; `UNIQUE(supersedes_id)` permits
  at most one successor per row, making every chain linear;
  `CHECK (supersedes_id IS NULL OR supersedes_id < id)` makes every
  self-supersession and every longer cycle structurally impossible, because
  rowids only increase and neither table has a DELETE path, so an honest
  successor always has the larger id. There is no standalone supersede
  mutation on either table. The two tables are asymmetric on purpose: a
  routing plan has no lifecycle, so "superseded" is purely a derived fact
  about it (a successor exists), and deriving it is both cheaper and
  strictly stronger than storing a fact that could drift; a handoff has a
  lifecycle, and `superseded` must be a terminal state the same `state`
  column and compare-and-swap logic already read, reached through the same
  append-only transition history as every other terminal state — so it is
  both derived (a successor names it) and stored (the state column says
  so), and doctor 39 is what keeps the two readings honest via a
  `supersession_incoherent` verdict on divergence. **Deferred**: nothing;
  the asymmetry is permanent, not a placeholder. **Non-goal**: no
  `agent handoff supersede` or `agent route select`-style standalone leaf
  exists; supersession is reachable only through `create --supersedes`.

- **D-v0.4.28 — No indexes on the four U-A3 tables; three scan paths
  accepted by measurement, not by imitation.** `routing_plans`,
  `routing_plan_candidates`, `agent_handoffs` and
  `agent_handoff_transitions` carry no `CREATE INDEX`, continuing
  D-v0.3.45's rule. The UNIQUE constraints already supply the implicit
  indexes for every plan-scoped and handoff-scoped lookup: candidates by
  plan, candidates by plan and rank, transitions by handoff and sequence,
  and successor lookup by `supersedes_id` on both tables. Three paths are
  left as full scans, each accepted on its own evidence:
  `routing_plan_candidates` by `agent_id`, reached only by the `agent
  discard` guard, a rare interactive command on a draft identity whose
  parent DELETE forces the same child-table scan for foreign-key
  enforcement regardless of whether an index exists; `agent_handoffs` by
  task/state/plan, a human-authored table bounded by operator effort at
  hundreds of rows; and doctor checks 38 through 41, which walk every plan
  and handoff by design regardless of any index. Should the first path
  ever measurably matter, `CREATE INDEX routing_plan_candidates(agent_id)`
  is named as the answer and is additive — it is **not** added in this
  pass. **Deferred**: that one index, pending measured evidence.
  **Non-goal**: this decision does not claim the three scans are free at
  unbounded scale, only that they are bounded by realistic ledger sizes
  today.

- **D-v0.4.29 — The 3→4 migration step keeps building from the live agent
  DDL at v5; the freeze obligation transfers, guarded by a test.**
  `migrations.py`'s `_agent_passports_v4` step docstring records that a
  frozen copy of the v4 agent DDL "becomes v5's obligation" once v4 stops
  being current — and U-A3 is the unit that makes v4 historical. This
  obligation is deferred, deliberately and once, rather than discharged
  now: U-A3 changes neither `AGENTS_DDL`, `AGENT_PASSPORTS_DDL`, nor
  `agent_identity_payload`, so the live constants the 3→4 step builds from
  are still the genuine v4 constants, and no drift materializes. The
  precedent for deferring is the 2→3 step, which still builds from the
  live memory-claim DDL today, at v4 — this codebase has historically
  frozen a migration step's DDL only when a later change would actually
  cause it to drift (U-M3's DDL change forced 1→2 to freeze; U-A1's
  agents-table change forced the v3 step to freeze), not mechanically at
  every version bump. The obligation therefore transfers unchanged to the
  first future unit that edits `AGENTS_DDL`, `AGENT_PASSPORTS_DDL`, or
  `agent_identity_payload`, which must freeze the v4-named copies of those
  symbols before it edits any of them. A guard test — byte-comparing
  `db.AGENTS_DDL` and `db.AGENT_PASSPORTS_DDL` against literals frozen at
  this baseline (`80b7e82577cbed19aa1823934df44ae09a644ac5`), and pinning
  the sorted key list of `passports.agent_identity_payload` for a fixed
  agent — converts the silent trap the bare deferral would otherwise be
  into a loud one: its failure is the signal that this decision's
  obligation has come due. **Deferred**: the freeze itself, to whichever
  future unit trips the guard test. **Non-goal**: this decision does not
  touch any historical migration step body; U-A3's own migration step is
  purely additive and reads no existing table.

- **D-v0.4.30 — No `route select` leaf; no `completed` handoff state.**
  U-A3 ships no `agent route select` command and no `completed` value in
  the handoff state vocabulary. A selection that grants nothing and
  executes nothing is, in substance, already a delegation declaration —
  and U-A3 has that record: the handoff, which references a plan and names
  a recipient. A second record for the same fact would be duplicate state
  with its own divergence risk, and the plan is honestly finished doing its
  job — presenting an ordered, explainable, pinned candidate list — the
  moment a human reads it; "which one did the human pick" belongs to
  whatever declares the delegation. Completion is refused for a different
  reason: `completed` asserts that work was executed and verified, which is
  an execution-outcome fact, and U-A3 ships no runs or evidence binding
  that could make such a claim honestly. Both rejections keep the unit's
  advisory boundary exact: nothing in the schema can be read as "and then
  this happened." **Deferred**: a `completed` state, with its own evidence
  binding, is explicitly left to a future orchestration unit that has runs
  and evidence to point at; that unit may also revisit whether a
  lightweight selection record is still unnecessary once real orchestration
  exists. **Non-goal**: `agent handoff accept` is not, and must never be
  read as, a stand-in for completion — it executes nothing.

- **D-v0.4.31 — `agent_absent` and `catalog_not_installed` are
  request-level refusal codes, never candidate reasons.**
  `ROUTING_REQUEST_REFUSAL_CODES = ("agent_absent", "catalog_not_installed")`
  is a vocabulary disjoint from `ROUTING_REASON_CODES`. Both codes describe
  `preferred_agent` naming something that has no `agents` row — an
  unregistered name, or an uninstalled catalog entry — and
  `routing_plan_candidates.agent_id` is `NOT NULL` with a foreign key into
  `agents(id)`, so no candidate row can ever carry either code: the schema
  itself proves the vocabulary split is not stylistic. A request that
  trips either refusal creates zero rows and zero events; `agent route
  plan` exits 1 and prints a message naming the resolution path (`agent
  catalog install` for the uninstalled-catalog case), and nothing is
  installed as a side effect of the refusal. Filing the two codes alongside
  genuine candidate reasons, as considered during Wave 0 review and
  rejected, would let doctor 38 and `route verify` accept a stored
  `reasons_json` value that no honest write could ever produce, silently
  widening the set of "valid-looking" damage those checks would fail to
  catch. **Deferred**: nothing; the split is permanent and the two
  vocabularies must remain disjoint by test. **Non-goal**: this decision
  does not change how `preferred_agent` resolution behaves, only how its
  two failure codes are classified and validated.

- **D-v0.4.32 — `required_data_classification` is exact-set membership
  against a passport's declared classifications, never a ceiling.** The
  routing request's classification field is named `required_data_classification`
  and is evaluated as membership only: the requested level must be an
  element of the agent's declared `data_classifications` set, including
  the case where the agent declared no set at all, else
  `data_classification_mismatch`; the diagnostic's `declared: false` flag
  distinguishes the two failure shapes. The name avoids a byte-identical
  collision with the passport's own, unrelated envelope-level
  `data_classification` field (the classification of the passport document
  itself, not of anything the agent handles), and the word "ceiling" names
  nothing in this contract: a ceiling implies a rank comparison, and this
  gate's own justification is "membership, not rank inference: declarations
  are not extrapolated" — the identical principle D-v0.4.23 applies to
  autonomy. The vocabulary itself is not new: it is `models.MEMORY_SENSITIVITIES`,
  reused by value and pinned equal as a set, by test, to both
  `protocols.DATA_CLASSIFICATIONS` and the passport schema's own
  `data_classifications` item enum, since `models.py` cannot import
  `protocols` and no single-definition fix exists across that boundary.
  The handoff's own `data_classification` column (on `agent_handoffs`,
  distinct from the request field) keeps its name and its meaning
  unchanged: the declared classification of the data involved in a
  delegation, enforced only as vocabulary, an advisory unstored warning at
  creation, and `RESTRICTED_PLACEHOLDER` privacy in list output — never a
  clearance and never an authority grant. **Deferred**: nothing;
  membership is the permanent semantics for this dimension. **Non-goal**:
  this decision does not add a `missing_data_classification` code — the
  existing `data_classification_mismatch` code already covers both the
  "declared without this value" and "declared nothing" cases via the
  `declared` diagnostic flag.

# DECISIONS — Agentic OS v0.4 U-A1 agent passports

This section begins the `D-v0.4.*` series for the U-A1 pass executed per
`agentic-os-v0.4-u-a1-agent-passports-contract.md` on branch
`v0.4-u-a1-agent-passports` (2026-07-16). Prepended per the established
precedent (D-W0.4, reaffirmed in D-v0.2.7); everything below stays
byte-identical.

## D-v0.4 decisions (U-A1)

- **D-v0.4.1 — One canonical identity table, rebuilt in place.** `agents`
  keeps its name and becomes the governed identity table; a second table
  would have left two authorities answering to `FROM agents`. The rebuild
  follows the D-v0.3.43 recipe a third time: `{table}`-parameterized DDL
  constants in `db.py`, shared by fresh init and the 3→4 step, so a migrated
  schema and a fresh one are identical by construction. The current-passport
  pointer is a composite FOREIGN KEY `(id, current_passport_version) →
  agent_passports(agent_id, version)`: a pointer can never name another
  agent's passport or a missing version, and NULL (draft/legacy) disables
  the check by SQLite's rule rather than by convention.

- **D-v0.4.2 — Create publishes nothing; publish freezes everything.**
  `agent create`/`agent import` produce a DRAFT identity plus a draft v1
  passport — the operator's own pending declaration, discardable, editable
  only by discarding and recreating. `agent passport publish` is the single
  moment a declaration becomes immutable history and the identity becomes
  `active`. This is how "published passports are immutable" and "a draft
  that was never used can be discarded" coexist without exceptions.

- **D-v0.4.3 — Three hash bindings, one per substitution attack.** The
  document's own U-X1 content digest breaks on content tamper; the passport
  ROW hash (binding the recomputed document digest to agent_id + version +
  status + timestamps) breaks on status/reparent tamper; the identity hash
  (binding lifecycle, pointer, and the five inert legacy fields) breaks on
  pointer/lifecycle tamper. Every authoritative agent write walks the
  no-laundering gate first — identity hash, every row hash, every document,
  contiguity 1..N, draft shape, pointer resolution — so a corrupted history
  cannot receive a new version on top. The only exits are restore-from-backup
  or deliberate repair, both outside normal commands (the U-M2 verify_claim
  posture, applied to identities).

- **D-v0.4.4 — The migration synthesizes no passports.** 3→4 carries every
  v3 field verbatim — `kind` outside today's vocabulary, `capabilities_json`
  that does not parse, secret-shaped `notes`, all of it — into permanently
  inert legacy columns, and creates `agent_passports` EMPTY. Parsing
  `capabilities_json` or mapping `trust_level` into declarations would put a
  guess into the ledger wearing the same clothes as a fact (the D-v0.3.44
  rule). A legacy agent has no current passport until a human publishes one;
  doctor's WARN-only coverage line says so without calling history an error.
  The new facts are constants plus ONE clock reading, and `origin='legacy'`
  is what makes the stamped timestamps honest.

- **D-v0.4.5 — Legacy agents migrate to `active`, not to a sixth state.**
  They were live, referenceable identities the moment before the migration;
  `origin='legacy'` plus a NULL pointer already distinguishes the ungoverned
  population permanently. A dedicated `legacy` lifecycle state would force a
  mass adoption ceremony on upgrade day and complicate every transition
  table for nothing the origin column doesn't say.

- **D-v0.4.6 — Reservation is a namespace rule, not a set of rows.**
  `governor`, `planner`, `builder`, `verifier`, `security-sentinel` and the
  `aos.`/`beast.` prefixes are refused at create/import from frozen tuples in
  `models.py`. No row exists until U-A2's bootstrap mints the system agents —
  a reserved row created today would be U-A1 guessing U-A2's shape. For the
  same reason `protected` ships as a column with refusal semantics and
  doctor coverage but NO setter: marking noise as protected is exactly what
  an operator flag would invite, and minting protected system identities is
  U-A2's job.

- **D-v0.4.7 — `revoked` is terminal, and parked identities cannot gain
  versions.** No command leaves `revoked`, ever — permanent distrust with
  the full history retained. `publish` requires draft or active: letting a
  suspended or archived agent quietly accumulate declarations would launder
  a parked identity back into circulation without the deliberate `restore`.
  Same-state transitions are refusals naming the current state, never
  silent no-ops.

- **D-v0.4.8 — Discard is the system's only DELETE, and it cannot delete
  history.** Legal only for a draft with exactly one (draft, v1) passport,
  origin create/import, unprotected, pointer NULL, and ZERO textual
  references anywhere (`runs.agent`, `handoffs.from_agent/to_agent`,
  `evidence.provenance`, `memory_sources.provenance`). Everything else is
  pointed at archive/revoke. The discard event itself survives, so even a
  discarded draft's existence stays journaled.

- **D-v0.4.9 — A passport is not a task message.** The schema carries a
  REDUCED envelope — no `aos_task_id`, no `trace`, no `idempotency_key`, no
  `audience`, no `permitted_destinations` — because requiring them would
  force fabricated data into every declaration. `_check_semantics` guards
  its field-specific checks on PRESENCE rather than schema identity, so the
  three task-message schemas (which require those fields structurally) keep
  byte-identical behavior, proven by regression.

- **D-v0.4.10 — Everything a passport declares is inert.** `autonomy` is a
  stored enum no code path reads; skill/tool requirements and provider
  compatibility are pattern-bounded strings with no resolver (U-K1/U-T1);
  `approvals_required` declares what needs approval and cannot grant one;
  credential-shaped property names are unrepresentable (the registry lint
  refuses the schema; instances refuse as unknown_field). Import is bytes →
  dict → refusal-or-rows: nothing an artifact names is opened, fetched,
  resolved or executed. Signing is deferred to U-S5/U-Q1 — the digest and
  provenance fields are the substrate a signature will later cover, and no
  field pretends to be one today.

- **D-v0.4.11 — `agent add`/`agent update` retired, not aliased.** A
  deprecated alias would have kept a second, ungoverned write path into the
  legacy columns alive — the exact thing this unit exists to end. In-place
  mutation of capability text is incompatible with immutable versioned
  declarations; the muscle-memory cost is bounded and the fixtures now seed
  historical rows through frozen v1/v2/v3 replica writers, exactly as the
  memory fixtures already did.

- **D-v0.4.12 — Version 3 is history now, and history is pinned by bytes.**
  The v3 `agents` DDL is frozen verbatim in `migrations._V3_AGENTS_DDL`
  (fixtures build from it, so fixture and migration agree about v3 by
  construction), and a regression test migrates the v2 fixture to target 3
  and byte-compares both the memory DDL and the agents DDL in sqlite_master
  against the expected text — so a future edit to the live constants that
  would silently rewrite what 2→3 produces fails loudly. The 3→4 step uses
  the LIVE v4 constants (correct while 4 is current; the frozen copy becomes
  v5's obligation — the established trade).

- **D-v0.4.13 — Doctor gained exactly three checks, and the sweep followed
  the text.** Check 13 validates the governed v4 shape (still reporting the
  legacy hazards it always reported); 32/33 verify identity hashes and
  passport histories with the same closed verdict vocabulary the gate
  refuses on — both FAIL, both feed the recovery gate, so a tampered
  registry blocks leaving recovery; 34 is WARN-only coverage. The U-C3
  sweep now scans stored passport documents leaf-by-leaf under
  `agent #id passport vN` labels, because role and mission are exactly the
  prose an operator pastes a credential into. Diagnostics stay
  name-or-`agent #id`, verdicts and counts — never a value.

- **D-v0.4.14 — Packaging: the zipapp allowlist becomes manifest-driven, not
  broadened by pattern.** D-v0.3.61 declined a `*.json` branch precisely
  because a denylist-shaped widening can be defeated by an unanticipated new
  file; U-A2 needs JSON passports in the archive anyway, so the allowlist is
  strengthened instead of loosened: the builder reads
  `agentic_os/catalog/manifest.json` and archives exactly that file plus the
  passport paths its entries reference, verifying each referenced artifact's
  digest before archiving it. A schema (D-v0.3.2) is hashed externally and
  is code; a passport is hashed internally (`content_sha256` is a required,
  checked field) and is authored content, so embedding it as a Python
  literal would make verification circular — the rejected fallback. An
  unreferenced `agentic_os/catalog/*.json` stays excluded by construction, a
  tampered referenced artifact fails the build outright, and
  `test_v02_packaging.py`'s `.py`-only pin moves to reflect the new rule.
  Signing (U-S5/U-Q1) will cover these same referenced artifacts later; this
  decision only establishes what ships.

- **D-v0.4.15 — Catalog provenance is `owner='system'` + `issuer` +
  digest match, with no schema change.** `agents.owner` already permits
  `'system'` and no U-A1 writer has ever emitted it — D-v0.4.6 reserved the
  pairing for this unit. Bound together with the hash-bound passport
  `issuer='aos.catalog'` and a recomputed-digest match against the
  checked-in manifest, the three independent bindings make forged catalog
  authenticity structurally impossible without inventing a fourth. Adding an
  `origin='catalog'` value to `origin`'s CHECK was rejected: it would force
  a table rebuild and a schema v5 bump for a fact the existing fields
  already carry more strongly, and an import of a checked-in artifact is a
  truthful `import` regardless of who authored the artifact. Name is used
  only for lookup and collision refusal, never as the ownership test.

- **D-v0.4.16 — The catalog reuses the existing `aos.` reservation; zero
  new names are reserved.** `RESERVED_AGENT_PREFIXES` has refused `aos.*` at
  create/import since U-A1 shipped (D-v0.4.6), so the catalog's namespace
  and the user's namespace are structurally disjoint — no catalog write can
  land on a user name, and no user write can land on a catalog name, by
  construction rather than by a new check. The bare reserved names
  (`governor`, `planner`, `builder`, `verifier`, `security-sentinel`) stay
  row-less on purpose: the catalog lives entirely at `aos.*`, and `governor`
  specifically is never minted, because no policy engine, router, or
  scheduler exists for it to have authority over. Name comparison is exact
  bytes — no case folding, no Unicode normalization, no aliases — so a
  lookalike name is simply a different, non-colliding, non-catalog name.

- **D-v0.4.17 — The catalog ships every passport version, never only the
  latest.** A passport's `passport_version` is hash-bound and must equal its
  row's version, so a catalog that shipped only "the newest" per role could
  never reconstruct a gap-free history on a fresh install. Synthesizing a
  plausible intermediate version to close that gap was rejected on the same
  ground D-v0.4.4 already established for the 3→4 migration: a guess does
  not get to wear history's clothes. Shipping versions 1..N for all twelve
  entries (N=1 at this unit's ship date) means a fresh install and an
  upgrade-chain converge on byte-identical documents and identical version
  numbers, and the manifest's version-list shape needs no change at the
  first future upgrade.

- **D-v0.4.18 — `agent catalog install --all` is one transaction, not
  one per entry.** Empirical verification showed `db.transaction()` commits
  early when nested, so the two new row-writing primitives
  (`create_catalog_identity`, `append_catalog_version`) are written as
  transaction participants that never open their own, and `catalog.py` owns
  the single rollback boundary around the whole `--all` operation.
  Per-entry transactions were rejected: a partially installed catalog is a
  state nobody requested and no command can describe, every realistic
  refusal (collision, divergence, tamper) is already detected during
  verify-then-plan before the transaction opens, and twelve entries at
  roughly two rows each is too small to need splitting. Consequently every
  foreseeable refusal costs zero writes, every fact is re-read inside the
  transaction against TOCTOU, and one failing entry rolls back the entire
  operation with the refusal naming the entry that blocked it.

- **D-v0.4.19 — Shipped catalog artifacts are fail-closed on secret shape,
  not warn-on-write.** D-v0.2.15's warn-on-write posture governs the
  trusted human CLI boundary: a human typed it, so the ledger stays honest
  and the human is warned rather than blocked. A checked-in catalog artifact
  is not user input — it is reviewed content the project ships — so a
  secret-shaped string appearing in one is a defect, not a user's choice.
  Reusing warn-on-write for catalog content was rejected because it would
  let a defect in reviewed, shipped content reach the ledger and only be
  flagged afterward, exactly the laundering U-C3 exists to prevent for less
  trusted input. `catalog.verify()` therefore FAILs and `install` refuses
  before any write. No catalog-specific reader is invented: every byte still
  passes through the same `parse_canonical` + `validate_document` path
  `agent import` uses, so catalog install events stay unconditionally clean.

- **D-v0.4.20 — No handoff graph or dependency block in U-A2.** A
  preferred-inbound/outbound-handoff field on a passport, or a `dependencies`
  block in the manifest, would encode a routing structure — exactly the
  router this unit's non-goals forbid building. A manifest `dependencies`
  list expressing install ordering was rejected on its own terms too:
  passports are inert with no inter-entry dependency, installation order is
  already manifest order, and a separate ordering field would be duplicate
  state carrying no meaning. Where a boundary is genuinely part of a role's
  own limit, it is prose in that role's `mission`/`limitations` field, never
  a structured, machine-followed one. Routing and handoff graphs remain
  explicitly assigned to a future unit (U-A3), which starts from a clean
  slate rather than an informally-encoded graph it would have to honor or
  break.

# DECISIONS — Agentic OS v0.3 U-M5 retrieval evaluations

This section continues the `D-v0.3.*` series for the U-M5 pass executed per
`agentic-os-v0.3-u-m5-retrieval-evals-contract.md` on branch
`v0.3-u-m5-retrieval-evals` (2026-07-16). Prepended per the established
precedent (D-W0.4, reaffirmed in D-v0.2.7); everything below stays
byte-identical.

## D-v0.3 decisions (U-M5)

- **D-v0.3.52 — U-M5 measures; it does not adopt.** The unit ships an explicit
  candidate retriever, datasets, a report and a gate. It ships no switch.
  `search.py` and `pack.py` were not modified — not one line, verified by a
  test that diffs them against the baseline commit. A pass that both proposed a
  retriever and wired it into `pack build` would be a pass whose benchmark
  could never fail in a way anyone acted on: the code would already be in
  production while the report was still being read. `benchmark run` prints a
  recommendation and changes nothing. Adoption is a human decision, taken after
  this report, in a later unit.

- **D-v0.3.53 — The baseline is measured as it is, not rewritten to be easy.**
  The baseline candidate re-expresses the LIKE backend's memory semantics over
  the shared corpus, and a test proves it returns the same memory result SET as
  the live `search.search()` for a matrix of queries against a real workspace.
  Reimplementing rather than importing was the only honest option available:
  `search.search()` needs a `sqlite3.Connection` and returns rendered snippets,
  and the benchmark corpus is deliberately not a database (D-v0.3.60).
  Reimplementing *and asserting equivalence* is a proof; editing production so
  the benchmark can call it is a way of making the baseline whatever the
  candidate needs it to be. The baseline reproduces the LIKE fallback's
  ascending-id order rather than FTS5's `rank`, because a benchmark whose
  ranking depends on which SQLite the runner happens to have is not a
  benchmark; the fidelity test compares SETS, which is the backend-independent
  part.

- **D-v0.3.54 — Integers, ordinals and rationals. No float ever.** Every score
  component is an integer, the sort key is a tuple of three integers, and every
  metric is a `fractions.Fraction` rendered by integer arithmetic to a
  fixed-width decimal STRING. Strings and not JSON numbers, because a JSON
  number is a float to almost every consumer — the no-float rule has to survive
  the reader too, not just the writer. A test re-parses the real `--json`
  stdout with a hook that rejects every float literal. A benchmark whose digits
  depend on the platform's libm is not a benchmark.

- **D-v0.3.55 — nDCG's log2 discounts are a checked-in table, not
  `math.log2`.** `math.log2` is a libm call: correctly rounded on most
  platforms, not guaranteed identical on all. `_LOG2_SCALED` pins log2(2) …
  log2(11) as integers scaled by 10^12, written out as source literals, and the
  discount is the exact rational `Fraction(10**12, _LOG2_SCALED[i])`. The table
  is a *definition* of this metric, not an approximation of another one: two
  runs on two platforms agree because they compute the same rational number,
  not because their libms happened to. A test compares the table to
  `math.log2` on the local platform to catch a transcription typo — that is the
  table checking the transcription, not the transcription trusting the
  platform. (Two of the eleven values were mistranscribed by hand on the first
  attempt; the test caught both, which is the argument for the test.)

- **D-v0.3.56 — Eligibility is one predicate, strictly stricter than the
  pack's.** `retrieval.eligibility()` returns a reason code from a closed,
  ORDERED set, applies U-M2/U-M3's lifecycle rules with the same spelling
  `ops.claim_is_eligible` uses, and reuses `ops.window_is_active` for the
  window. It adds three things ordinary pack inclusion does not need:
  hash validity (`memory_for_project` deliberately does not re-verify —
  D-v0.3.21: one damaged row must not block every pack; retrieval can afford to
  be stricter because its pool is bounded and its exclusions are counted and
  reported), `valid_from <= as-of` (a claim whose window has not opened is not
  a fact about the requested instant), and project compatibility. A test proves
  the implication that matters over the whole fixture matrix:
  `retrieval_eligible(c, t)` ⟹ `ops.claim_is_eligible(c, t)`. U-M5 can refuse
  what the pack would carry; it can never carry what the pack would refuse.

- **D-v0.3.57 — Every expanded result ranks below every primary result.** The
  sort key's first element is the origin ordinal. This makes "a graph neighbour
  must not outrank a strong direct lexical match" true by construction rather
  than by weight-tuning, and it makes the property testable with one assertion
  instead of a tournament of fixtures. Expansion in U-M5 is a **recall
  instrument**: it appends to the tail, it never reorders the head. If a later
  unit wants interleaved ranking, it will have this report to argue from.

- **D-v0.3.58 — A primary hit is conjunctive; a graph neighbour needs one
  token.** Primary inclusion requires every query token — the semantics both
  live backends already have (FTS5 ANDs its terms; the LIKE fallback requires
  each as a substring). Expansion's documented minimum relevance signal is at
  least one token. That gap is the whole point of expansion: a claim that
  partially matches and is connected by an active edge to a full match is
  exactly the recall a lexical retriever loses. A neighbour with zero query
  tokens is graph noise and is never included, whatever its degree — the
  graph-expansion fixture's noise claim has the highest degree of any
  non-anchor in it, and a test asserts that fact before asserting its
  exclusion.

- **D-v0.3.59 — Disputes and contradictions rank; they never judge and never
  exclude.** An active `disputes` source link and an active `contradicts` edge
  each subtract a bounded, pinned number of points. Neither makes a claim
  ineligible, neither hides it, neither resolves anything. U-M3 pinned that a
  contradiction records that a human said two claims disagree, not which one is
  true (D-v0.3.38); a retriever that dropped a contradicted claim would be
  answering that question by omission. Provenance and graph signals are capped
  at three occurrences each, so link count cannot become the ranking.

- **D-v0.3.60 — The benchmark corpus is memory, never a database.**
  `benchmark run` builds its corpus from the embedded fixture definitions and
  never opens `aos.db`. This is what makes "creates no database rows, files,
  ledger events or workspace state" a structural fact rather than a promise:
  there is no connection to write through, proven by a test that patches
  `db.open_db` to raise and watches the run succeed anyway. It also makes the
  run byte-identical inside a workspace, outside one, in recovery mode, and
  inside `aos.pyz`. `retrieval query` is the surface that reads a real ledger,
  and it only reads — it does not even touch the derived FTS index or its
  watermark, which `search` legitimately does.

- **D-v0.3.61 — The embedded datasets are canonical; `retrieval_benchmarks/`
  is a projection.** Exactly the U-X1 mechanic (D-v0.3.2/D-v0.3.3), for exactly
  the U-X1 reason: `aos.pyz` carries `.py` files and nothing else, so a JSON
  file could not be the source of truth without either breaking the zipapp or
  widening its allowlist. The Python definitions are the one editable registry;
  `tools/gen_retrieval_benchmarks.py --write` projects them; doctor and the
  tests verify byte-for-byte. There is no second editable registry, and
  `tools/` is outside the package allowlist so the writer never ships. No
  packaging change was needed or made — the existing `.py`-under-package
  allowlist already excludes the JSON by construction.

- **D-v0.3.62 — `baseline` is reported, never gated.** `benchmark run`'s exit
  code is driven by validation plus the promotion gate of the CANDIDATES.
  `baseline` is the measured reference: it is what production does today, it
  cannot be "promoted", and gating it would make `--candidate all` exit 1
  forever the moment the baseline was measured to leak — which is the finding,
  not a malfunction. And it does leak: on the core benchmark the baseline
  returns 8 wrong-project, 2 restricted, 8 lifecycle and 2 hash-invalid
  results. Every one of those numbers is printed, at full severity. One number
  is simply not wired to the exit code.

- **D-v0.3.63 — Truncation is reported, never silent, and never averaged.**
  Every bound truncates deterministically and increments a named counter that
  appears next to the metric it affected. Leakage counters are integer sums
  over cases and are never divided by anything: an average is how a leak in one
  case out of forty disappears. The counters are also computed from the CLAIMS
  themselves rather than from the case's `forbidden` list — a leak is counted
  because the claim IS restricted, not because the dataset author remembered to
  list its id. An author's omission cannot hide a leak, which is the only way
  the number is worth printing.

- **D-v0.3.64 — `--show-key` shows a key, and only for claims already
  eligible.** Human output defaults to metadata only. The one administrative
  content flag prints the claim `key` — never `value_md`, a source locator,
  provenance text or an evidence ref. It is consistent with `memory show`,
  which prints key AND value unredacted for exactly this population, because
  every result is eligible by construction and `restricted` is an eligibility
  exclusion: a restricted claim cannot reach the renderer to be redacted by it.
  The flag shows strictly less than the command that already exists, and the
  protection is structural rather than a redaction pass that could be forgotten.

# DECISIONS — Agentic OS v0.2 U-P1 packaging run

This section continues the `D-v0.2.*` series for the U-P1 pass executed per
`agentic-os-v0.2-u-p1-packaging-contract.md` on branch `v0.2-u-p1-packaging`
(2026-07-15). Prepended per the established precedent (D-W0.4, reaffirmed in
D-v0.2.7); everything below stays byte-identical.

## D-v0.2 decisions (U-P1)

- **D-v0.2.40 — One canonical CLI, shared by every entrypoint.**
  `agentic_os.cli.main(argv=None) -> int` is the single implementation of the
  argparse tree, command dispatch, exit-code mapping, and exception handling.
  All three entrypoints — `aos.py`, `agentic_os/__main__.py` (`python3 -m
  agentic_os`), and the zipapp's archive-root `__main__.py` — are three-line
  shims that call it and `sys.exit()` its return value. No entrypoint may
  restate a flag, a subcommand, or a dispatch rule: a second parser would be a
  second product, silently drifting from the first. What this pass did NOT
  have to change is the load-bearing part: `build_parser()` already pins
  `prog="aos"`, so usage/help text derives from the pinned prog rather than
  `sys.argv[0]`, and `--help` is byte-identical across all three entrypoints by
  construction — no `cli.py` change was needed, and none was made. `aos.py` was
  already a thin shim at baseline and was likewise not modified. Verified, not
  assumed: `python3 aos.py --help`, `python3 -m agentic_os --help`, and
  `python3 dist/aos.pyz --help` produce identical stdout and identical exit
  codes, and a domain error (`status` outside a workspace) exits 1 with
  byte-empty stdout from all three.

- **D-v0.2.41 — The archive entrypoint is the module entrypoint, verbatim.**
  The builder copies `agentic_os/__main__.py` byte-for-byte to the archive root
  as `__main__.py` rather than generating a third shim. This makes D-v0.2.40
  mechanically true instead of a convention maintained by hand — there is no
  third copy to drift — and a test asserts the byte-identity of both archive
  members against the on-disk file. The cost is one constraint, documented in
  the file itself: `agentic_os/__main__.py` must use the absolute import `from
  agentic_os.cli import main`, never a relative `from .cli import main`, so the
  same bytes are valid both inside the package (under `-m`) and at the archive
  root (where there is no parent package). Corollary:
  `zipapp.create_archive(main=...)` is deliberately NOT used — its generated
  stub calls `fn()` and discards the return value, which would force exit code 0
  for every command and silently break the exit-code contract (D-P0.9). The
  shim is explicit precisely so exit codes survive.

- **D-v0.2.42 — Zero runtime dependencies, stated and tested.**
  `aos.pyz` runs on a stock Python 3.12 with nothing outside the standard
  library. `pyproject.toml` declares `dependencies = []` (asserted by test, as
  is the absence of optional runtime extras), `requires-python = ">=3.12"`, and
  an `aos` console script bound to `agentic_os.cli:main` — the same canonical
  CLI, so an installed copy cannot behave differently. The builder is itself
  stdlib-only (`zipapp`, `pathlib`, `shutil`, `tempfile`, `os`, `stat`,
  `argparse`, `sys`; a test asserts every top-level import is in
  `sys.stdlib_module_names`). `setuptools` under `[build-system] requires` is a
  build-time requirement and is not a runtime dependency; it is the only one.
  Nothing was installed globally in this pass.

- **D-v0.2.43 — The archive carries the runtime package only, by allowlist.**
  Archive membership is exactly: `agentic_os/**/*.py` (excluding any path with
  a `__pycache__` component) plus the root `__main__.py`. This is an allowlist
  by construction, not a denylist of bad names. Every required exclusion —
  `.git`, `.agentic-os`, `tests/`, `__pycache__`, `*.pyc`, ledger and backup
  DBs, exports, local settings, credentials, `*.md` doc trees, `adapters/`,
  `research/`, `aos_hooks.py` — follows because those are either not under the
  package, or not `.py`, or under `__pycache__`. The reason is the failure
  mode: a denylist is defeated by any new file whose name nobody anticipated,
  and the thing being shipped is a file that may be copied to other machines. A
  user's ledger, vault, backup, or credential embedded in a distributed archive
  is not a cosmetic defect. Proven adversarially rather than by inspecting a
  clean tree: a synthetic contaminated source tree (containing `.env`,
  `credentials.json`, `aos.db`, a `.agentic-os/` ledger with backups, `.pyc`
  files, `__pycache__/`, `tests/`, `.git/`, docs) builds an archive whose member
  list is exactly the four legitimate `.py` files and whose concatenated bytes
  contain no `sk-live-SECRET`, no `SQLite format 3`, no ledger and no backup
  content. `[tool.setuptools] packages = ["agentic_os"]` applies the same
  explicit-allowlist posture to the sdist/wheel path instead of auto-discovery.

- **D-v0.2.44 — Output safety: `lstat`, and fail-closed refusal.**
  The builder refuses any existing output object that is not a regular file —
  symlink, directory, FIFO, socket, block/char device — exiting nonzero with
  one concise diagnostic and leaving the object exactly as found. The check
  uses `os.lstat`, never `os.stat`, and `build()` resolves only the output's
  *parent*, never its final component: resolving the final component would
  follow a symlink and defeat the check. A symlink is therefore refused even
  when it points at a regular file — writing through a link into a target the
  user did not name is the exact accident this prevents. Tested per object
  kind, each asserting the object survives unchanged (symlink still a symlink
  pointing at the same target, with the target's bytes intact; directory still
  holding its contents; FIFO still a FIFO; socket still a socket). Diagnostics
  name paths and conditions only — a test writes a secret into a refused
  directory and asserts the one-line diagnostic contains neither the secret nor
  a traceback. An existing *regular* file is a legal destination and is
  replaced only on success (D-v0.2.45).

- **D-v0.2.45 — Atomic replacement: the destination is never opened for
  writing.** The archive is staged in a `TemporaryDirectory` outside the source
  tree, written to a temp file *in the destination's parent* (same filesystem,
  so the rename is atomic), chmod'd `0o755`, and only then `os.replace`d over
  the destination. Because the destination is never opened for writing, a
  failure at any earlier step cannot truncate or corrupt it — there is no
  partial-write window to reason about. Consequences, each tested by injecting
  a real failure into the production branch and then inspecting the filesystem
  (not by matching error text): an existing valid archive survives a failed
  rebuild byte-identically, with mode intact and still a valid zipapp; a failed
  first build leaves no destination at all; a staging failure leaves the prior
  archive intact; and the temp file is removed in a `finally`, so no
  `.aos-pyz-*.tmp` debris survives either path. The builder does not modify the
  source tree (tested: package `.py` mtimes are unchanged across a build) —
  only the requested artifact and its short-lived sibling temp file.

- **D-v0.2.46 — Generated artifacts are not committed.**
  `dist/`, `build/`, `*.pyz`, and `*.egg-info/` are gitignored, and `aos.pyz`
  is not committed. A committed binary is a second copy of the runtime that
  goes stale silently the moment source changes, and reviewing it is not
  possible. The archive is reproducible from source with one stdlib-only
  command; that is the distribution story, and rebuilding is documented in
  README and TROUBLESHOOTING.

- **D-v0.2.47 — Packaging changes reach behavior, not semantics.**
  U-P1 adds ways to *reach* the CLI and changes nothing about what it *does*:
  database schema, CLI commands and flags, hook behavior, dropfile behavior,
  evidence rules, backup/export behavior, doctor semantics, migration behavior,
  and AICompany are untouched. `agentic_os/cli.py` was not modified (no
  incompatibility required it) and `aos.py` was not modified (already a thin
  shim). Evidence beyond the new tests: the pre-existing 736-test suite passes
  unchanged, and the archive's `doctor` reports the same 20 checks PASS on a
  fresh `init` as the script entrypoint does. Root resolution was verified to
  be entrypoint-independent at baseline — `--root PATH`, else cwd-upward
  discovery from `Path.cwd()`; it never consults `__file__` or `sys.argv[0]` —
  which is why the archive works from any directory, outside the repository,
  with `PYTHONPATH` cleared.

- **D-v0.2.48 — Known limitation: `hooks install` is unsupported from the
  archive; not fixed here.** `hooks.default_runner_path()` resolves the hook
  runner as `Path(__file__).resolve().parent.parent / "aos_hooks.py"` — the
  `aos_hooks.py` that ships beside `aos.py` in a checkout. Inside a zipapp,
  `__file__` is a path within the archive, so that resolves to
  `<...>/aos.pyz/aos_hooks.py`, which does not exist; there is no `--runner`
  override flag. So `hooks install` / `hooks status` / `hooks uninstall` are
  not supported from `aos.pyz` — manage hooks from a source checkout. Left
  unfixed deliberately: `aos_hooks.py` is not part of the `agentic_os` runtime
  package, so shipping it would violate D-v0.2.43; a Claude Code settings hook
  must point at a stable on-disk script path, which a zipapp's interior path is
  not, so shipping it would not actually help; and fixing it means changing
  `hooks.py`, which this pass forbids absent an incompatibility blocking a
  shared entrypoint. This blocks one command from one entrypoint — it does not
  block the shared entrypoint. The required archive paths are unaffected:
  `init`, `status`, and `doctor` never call `default_runner_path()` (it is
  reached only from the hooks install/status/uninstall handlers). Documented in
  README and TROUBLESHOOTING rather than papered over.

- **D-v0.2.49 — CI and release publication remain deferred.**
  No GitHub Actions, no release publishing, no branch-protection automation, no
  Docker, no global installation, and no third-party runtime library was added.
  U-P1 delivers the build and the entrypoints; publishing them is a separate
  decision with separate consequences (registry namespace, signing, versioning
  cadence) and is out of scope for this pass.

- **D-v0.2.50 — Gate U-P1 result.** 40 focused tests green
  (`tests/test_v02_packaging.py`), 776 green across the full suite (736
  pre-existing, unchanged; 736 + 40 = 776). Covered: module delegation to the canonical CLI via
  `runpy` with `main()` patched (proving both delegation and exit-code
  propagation); module/script `--help` and error-path stdout/stderr/exit-code
  equality; archive validity (regular file, execute bit, `#!/usr/bin/env
  python3`, `is_zipfile`); archive `--help` outside the repository with
  `PYTHONPATH` cleared, asserted equal to the script's, with a probe proving
  the checkout is genuinely absent from `sys.path`; archive and module
  `init`/`status`/`doctor` in disposable workspaces (doctor: every line
  `[PASS]`, exit 0); shebang execution; exact archive membership; adversarial
  exclusion from a contaminated tree; failure atomicity and destination
  preservation; per-kind unsafe-output refusals; custom and relative output
  paths; pyproject metadata; and `aos.py` behavior unchanged.

# DECISIONS — Agentic OS v0.2 U-H2 evidence-bearing success claims run

This section continues the `D-v0.2.*` series for the U-H2 pass executed per
`agentic-os-v0.2-u-h2-success-proof-contract.md` on branch
`v0.2-u-h2-success-proof` (2026-07-15). Prepended per the established
precedent (D-W0.4, reaffirmed in D-v0.2.7); everything below stays
byte-identical.

## D-v0.2 decisions (U-H2)

- **D-v0.2.35 — Success-dropfile ingest gate: in-file proof, after every
  other check, before the transaction.** A dropfile whose structured
  `outcome` is `success` must carry at least one acceptable evidence row
  in that same file — pre-existing task evidence never satisfies the gate.
  Acceptable means: vocabulary kind, ref non-blank after the one-line
  collapse (Python whitespace semantics, so NBSP/U+3000 count), and the
  explicitly present claim non-blank after the same collapse; the target
  of the evidence is never verified — U-H2 enforces presence and
  structural non-blankness, not truth, and no free-text classification
  exists anywhere (only the structured outcome field is judged). The gate
  runs after size, UTF-8, parse, task, secret-scan, and duplicate checks
  (a file ingested before U-H2 reaches the duplicate refusal first) and
  before the ingest transaction opens, so refusal is trivially atomic:
  exit 1 via `AosError`, stdout byte-empty, one bounded stderr diagnostic
  naming only the validated task ID and the recovery rule (add evidence,
  or use the honest `partial`/`fail`/`unknown`), zero rows and zero
  events written, and no model-controlled value echoed. `partial`,
  `fail`, and `unknown` remain valid with an empty evidence section; no
  outcome is added. The U-H1/U-H2 boundary, pinned: the hooks stay
  transport-only — a structurally valid success envelope with an EMPTY
  evidence section still stages and publishes exactly as D-v0.2.29
  records — and the gate refuses that file at ingest, where the ledger is
  actually written. (A blank-ref evidence row, by contrast, is now
  structurally malformed per the shared parser, so the hook refuses to
  stage it — parser parity, unchanged posture, not new hook policy.)

- **D-v0.2.36 — The evidence-only slice of D-v0.2.20.** U-H2 takes
  exactly the evidence items of the approved-for-later hardening list:
  post-collapse dropfile evidence validation (a ref or claim that
  collapses to empty refuses as a malformed evidence line, named by line
  number and field, never by value — with the honest grammar note that a
  whitespace-only claim is right-stripped off the line and refuses as an
  evidence-line shape mismatch at the same line, since strip and collapse
  share Python's Unicode whitespace definition) and non-blank evidence
  refs/claims at the trusted CLI write (`ops.add_evidence` refuses a
  whitespace-only ref, and a whitespace-only explicitly supplied claim,
  before any lookup, hashing, mutation, or event; `claim=None` stays
  legal; file-sha256 and evidence-git behavior is unchanged for non-blank
  values). The rest of D-v0.2.20 (priority bounds, task text, agent-name
  grammar, run summaries) remains deferred. Legacy blank-ref rows
  admitted through the pre-U-H2 regex hole are surfaced by a new
  warn-only doctor line naming bounded `E-XXXX` IDs and counts only —
  they are never rewritten or deleted, and `mark_done`/the done gate
  still count them exactly as before.

- **D-v0.2.37 — Run-bounded recovery window; `evidence.run_id` stays
  dormant.** Doctor gains a warn-only check for ended runs with outcome
  `success` that no acceptable evidence is attributable to. Evidence is
  attributable to run R when: same `task_id`; ref non-blank after
  normalization; `created_at >= R.started_at`; and, when a next run
  exists for the task (the earliest strictly later run in the
  `(started_at, id)` total order), `created_at` strictly earlier than
  that next run's `started_at`. So: evidence during the run counts;
  evidence added after a successful end still counts until the next run
  starts (the recovery window); evidence belonging to a later run cannot
  heal an earlier one; evidence created before the run never counts; and
  two sequential runs sharing one second-precision `started_at` are
  judged conservatively — the earlier run's window is empty, so
  shared-timestamp evidence never heals it. Deliberately rejected
  alternatives: populating `evidence.run_id` (a schema-semantics change
  and a new write path U-H2 does not need), any schema change, and a new
  evidence-linking CLI. The warning names run IDs only — total count plus
  at most the first 10 (`(+N more)`) — never a ref, claim, summary, or
  agent value, and stays warn-only (doctor exit 0 when hard checks pass).

- **D-v0.2.38 — Direct run endings and `mark_done` stay untouched.**
  `run end --outcome success` remains accepted with no evidence check and
  no warning — CLI surface, stdout, stderr, summary semantics, and event
  shape are byte-identical to pre-U-H2. It is the documented human
  recovery path after a gate refusal (the human verifies, records
  evidence via the CLI, and ends the run honestly), and doctor's
  D-v0.2.37 window is the audit that closes the loop afterwards.
  `mark_done` and the done-override flow (D-v0.2.5) are unchanged.

- **D-v0.2.39 — Gate U-H2 result.** Focused suite
  (`tests/test_v02_success_proof.py`) 42 green; U-H1 hook suite 91 green
  (unchanged count); full suite 736 green (694 pre-existing, none
  weakened or deleted); `compileall` clean; `git diff --check` clean.
  Renderer and all four checked-in `adapters/*/PROTOCOL.md` stay
  byte-identical; the one concise success rule lives in the SHARED
  dropfile section (the gate judges every adapter's dropfiles), so the
  codex/gemini/generic protocols were regenerated alongside claude-code —
  a reported deviation from the expected file list, forced by the
  existing all-adapters parity invariant. Four existing test pins moved,
  each the minimal mandated edit, also reported: the U-H1 dogfood
  scenario 5 body gained one evidence row (its identity is duplicate/
  retry + dedupe; the old success/empty ingest-accepts assertion is
  exactly what U-H2 forbids, and the refusal is pinned in the U-H2
  suite), and three doctor line-count pins moved 18 → 20 under the
  D-W8.1 "pin moves up with mandated new checks" pattern
  (test_cli, test_weekend_views, test_v02_secret_safety).

# DECISIONS — Agentic OS v0.2 U-H1 SessionEnd hook + installer run

This section continues the `D-v0.2.*` series for the U-H1 pass executed per
`agentic-os-v0.2-u-h1-sessionend-hook-contract.md` on branch
`v0.2-u-h1-sessionend-hook` (2026-07-14). Prepended per the established
precedent (D-W0.4, reaffirmed in D-v0.2.7); everything below stays
byte-identical.

## D-v0.2 decisions (U-H1)

- **D-v0.2.28 — Two-stage bridge: Stop captures the official
  `last_assistant_message` only; SessionEnd publishes.** The Stop hook is
  the only stage that sees session text, and it sees exactly one field of
  the official hook JSON — never the transcript. `transcript_path`
  (supplied to SessionEnd) is metadata and is never opened, so the bridge
  has zero dependency on the transcript JSONL format and cannot break when
  that format changes. Splitting capture from publication buys three
  things: the envelope is validated while the session is still alive (the
  agent sees the refusal diagnostic on its own Stop and can correct
  itself in the next turn — latest envelope wins); publication happens
  exactly once per session at a well-defined lifecycle point with a
  documented `reason` vocabulary (`clear|logout|prompt_input_exit|other`;
  anything else refuses rather than guesses); and a crashed session
  leaves an inert staged record instead of a half-published dropfile.
  The Stop handler never blocks: stdout stays empty in every outcome (no
  decision JSON can exist on an empty stream) and exit 2 — the Stop-hook
  blocking signal — is never used; refusals are exit-1 diagnostics.
  Compatibility is capability-based (Stop/SessionEnd command hooks, JSON
  on stdin, `last_assistant_message` present); no Claude Code minimum
  version is invented anywhere.

- **D-v0.2.29 — The envelope IS the dropfile protocol; one schema, two
  transports.** The write-back envelope is a fenced ```` ```aos-dropfile ````
  block (both fences at column 0) whose content is byte-for-byte the
  existing dropfile format. The hook reuses `ingest.parse_dropfile`, the
  U-C1 `MAX_DROPFILE_BYTES` cap, and the U-C3 detector via the new shared
  `ingest.secret_findings` (extracted from `_scan_for_secrets`, same
  behavior) — no competing schema, no new validators, and every field the
  manual path supports (task, agent, outcome, summary, evidence rows,
  open questions) flows through unchanged. U-H2 is explicitly NOT smuggled
  in: a success outcome with zero evidence rows stages and publishes.
  Exactly one envelope per message; two or more refuse (with one staged
  record per session, picking a winner would silently drop the rest). An
  unterminated or indented fence is "no envelope" (silent no-op), as is a
  session outside any initialized workspace — the hooks are safe to
  install user-wide. Hook stdin itself is capped (16 MiB) in the U-C1
  bounded-input posture. Diagnostics name conditions, counts, and line
  numbers, never untrusted values — a session id, reason string, or
  envelope value is never echoed.

- **D-v0.2.30 — Staging/publication identity and the deterministic
  recovery rule.** The staged record
  (`exports/hook-staging/stop-<session>.json`) binds a format marker
  (`aos-u-h1-staged/1`), the session id (charset-fenced
  `[A-Za-z0-9-]{8,128}` — it becomes a filename component, so the fence is
  also the traversal guard), the envelope text, and its sha256. SessionEnd
  re-validates ALL of it immediately before publication (marker, binding,
  digest, size caps, parse, secret scan): a tampered, replaced,
  secret-bearing, or malformed record refuses with the record retained;
  only ENOENT reads as absence — any other inspection error refuses
  (U-C4's fail-closed lesson). The published name
  `dropfile-<task>-<agent>-hook-<session8>-<sha12>.md` is deterministic
  and carries the dedupe identity: the sha256 of the published bytes is
  exactly the hash `ingest` journals for its own dedupe, closing the loop
  end-to-end. Publication is a same-directory temp file + `os.link`
  (never overwrites) + temp unlink; retries converge — identical bytes at
  the name are idempotent success, different bytes refuse. Recovery rule,
  pinned: a staged record is removed ONLY after verified publication
  (fresh or identical); every refusal retains it byte-for-byte; a
  post-publication removal failure warns at exit 0 (the deterministic
  name makes the leftover harmless). Stale records from crashed sessions
  are inert and documented as safe to delete or salvage by hand. Honest
  limit, stated: owned-path checks are lstat/O_NOFOLLOW (symlinked
  `exports/`/`hook-staging/` and non-regular files refuse before any read
  or write), not the U-C4 descriptor-pinned depth — a same-directory race
  inside the check-to-write window is documented, not defended.

- **D-v0.2.31 — Hook handlers run via a dedicated root runner, not the
  CLI; the prohibition list is structural.** Claude Code invokes
  `python3 <checkout>/aos_hooks.py stop|session-end` — a thin sibling of
  `aos.py` that imports `agentic_os.hooks` (script-directory sys.path,
  works from any hook cwd). The handlers therefore reuse the package's
  validators without ever invoking the `aos` CLI, and the module's runtime
  path contains no subprocess, SQLite, git, or network call to misuse —
  the test suite additionally hard-patches `subprocess.*`, `os.system`,
  `sqlite3.connect`, and `socket.socket` to prove none is reached, records
  every file open to prove nothing under the workspace outside
  `exports/` is read (transcript included), and pins stdout-empty across
  all outcomes.

- **D-v0.2.32 — Installer: documented user settings file, dry-run
  default, marker-based ownership, semantic idempotency.** Target is the
  documented Claude Code user settings file `~/.claude/settings.json`
  (`--settings PATH` overrides; tests and the build never touch the real
  one). Dry-run is the default posture and prints the exact deterministic
  unified diff; `--apply` demands a typed `yes`, writes a byte-exact
  collision-suffixed backup (`settings.json.aos-backup-<stamp>`,
  documented restore: `cp <backup> <settings>`), validates the exact
  resulting bytes, and lands via same-directory temp file + fsync +
  atomic `os.replace` with the original file mode preserved (0600 fresh).
  Ownership is the `aos_hooks.py` token in a command entry: install heals
  to exactly one AOS-owned group per event (appended last), uninstall
  removes only owned entries and drops only containers its own removal
  emptied; unrelated settings, events, and hooks survive semantically via
  the JSON round-trip (a reformat of an untouched file never happens —
  idempotency is judged on the parsed document, so an already-merged file
  is never rewritten). Unsupported shapes (non-object root, non-list
  event arrays, non-object groups, non-list group hooks), invalid JSON,
  symlinked/irregular settings paths, and missing parent directories all
  refuse with zero mutation. `status` reports
  absent/installed(version+digest)/drifted, where the digest is the
  sha256 over the exact expected handler commands and protocol version
  `u-h1/1`. The installer opens no ledger and records no evidence — the
  human records merge evidence per repo convention.

- **D-v0.2.33 — Accelerated dogfood gate.** Instead of five repetitive
  manual sessions: an automated five-scenario matrix (normal success,
  failure outcome, no envelope/no evidence, secret-shaped refusal,
  duplicate/retry) driven against a REAL initialized workspace all the
  way through manual `ingest dropfile` of the published file — plus ONE
  real live smoke (hooks installed into a disposable settings file, one
  real Claude Code session, manual ingest) to be performed by the human
  before merge. The matrix also proves the ledger's own sha256 dedupe
  refuses a second ingest of the same published bytes.

- **D-v0.2.34 — Gate U-H1 result (audit-corrected 2026-07-15).** Focused
  suite (`tests/test_v02_hooks.py`) 91 green; full suite 694 green (603
  pre-existing, none weakened or deleted); `compileall` clean;
  `git diff --check` clean. Audit correction, history preserved: this
  entry originally recorded 67 focused / 670 full, but the branch as
  shipped before the 2026-07-15 bounded corrective pass actually carried
  70 focused / 673 full; the totals above add that pass's 21 regression
  tests (superseded-staging invalidation, linear envelope scanner with
  end-of-message fence rule, bounded published-name components, agent
  secret-shape scan shared with manual ingest, settings lost-update
  guard, exact-command hook ownership, `"hooks": null` refusal,
  SessionEnd workspace-gate-before-reason ordering, unpaired-surrogate
  refusals on both validation paths, and uniform staged-record recovery
  pointers — including the retargeted uninspectable-staging test).
  Renderer and checked-in `adapters/claude-code/PROTOCOL.md` stay
  byte-identical (existing U-C3 parity test now also covers the envelope
  section); codex/gemini/generic adapters unchanged.

# DECISIONS — Agentic OS v0.2 U-C4 Windows read-only export run

This section continues the `D-v0.2.*` series for the U-C4 pass executed per
`agentic-os-v0.2-u-c4-windows-export-contract.md` on branch
`v0.2-u-c4-windows-export` (2026-07-13). Prepended per the established
precedent (D-W0.4, reaffirmed in D-v0.2.7); everything below stays
byte-identical.

## D-v0.2 decisions (U-C4)

- **D-v0.2.27 — U-C4 sixth corrective pass (rollback identity guard R1,
  2026-07-14).** A sixth review confirmed one remaining defect of the
  fourth/fifth passes' own class: the rollback rename (`PREV → AOS`) —
  reached when the post-move-aside fsync or the promotion rename
  fails — renamed whatever sat at the previous name onto the
  AUTHORITATIVE name with no identity proof, although the run already
  held the PREV identity pinned right after the move-aside. A racer
  substituting PREV inside the promotion window therefore had its
  never-validated tree promoted to `PATH/AOS`, the validated staging
  was then discarded, and the failure reported "the previous
  generation was restored and the destination is unchanged" — false on
  every count (witnessed on the production path before the fix).
  Corrected minimally (R1): both rollback sites pass the pinned PREV
  identity, and the rollback rename runs only after a fresh
  fd-relative lstat of the previous name proves exactly that identity
  (the held PREV descriptor keeps the inode alive, so the proof cannot
  be forged by inode recycling). A never-pinned, uninspectable (only
  ENOENT reads as absence, per F4), or replaced PREV refuses the
  rollback: the entry is retained untouched, the complete staged
  generation is kept, and the export strands with the exact live state
  and shell-quoted `mv` recovery commands; a vanished PREV strands
  without instructing inspection of a nonexistent tree. Residue,
  stated honestly: the guard-lstat-to-rename gap is the same
  irreducible window as the move-aside guard's. Two regression tests
  pin the mechanism, each written first and watched fail against the
  unguarded rename (focused suite 213, full suite 603 green).

- **D-v0.2.26 — U-C4 fifth corrective pass (race-condition corrections
  Q1–Q5, 2026-07-14).** A fifth review confirmed five race-condition
  defects in the uncommitted U-C4 code; all five are corrected without
  widening scope, each pinned by regression tests proven to fail against
  the surgically reverted mechanism (28 new tests; focused suite 211,
  full suite 601 green). A multi-agent adversarial re-review of the
  corrections then confirmed and closed five further defects in the new
  code itself — an interior cleanup ENOENT masquerading as "staging
  genuinely absent" (Python maps errno.ENOENT to FileNotFoundError at
  construction, so absence is now signalled by a dedicated exception
  raised only by the pre-mutation pin-open), a spurious removal WARN for
  a PREV that had already vanished, a source-descriptor leak on the
  os.fdopen failure path (a directory raced onto a note's name), a
  RecursionError from a hostile deeply-nested tree escaping as an
  exit-2 internal error that masked the original failure, and
  replacement-retention messages omitting the exact retained quarantine
  location — plus documentation overclaims (the rename-overwrite
  residue also covers regular files, the staging-content window is per
  file, child quarantine names nest inside their parent directory) and
  test-soundness gaps (the file-level source device check was untested,
  one alias assertion was tautological, hardlink skip guards were
  unreachable). Where an earlier claim was too strong, it is narrowed
  honestly rather than kept. Policies pinned:
  (a) *Quarantine-based cleanup (Q1, amends C1).* The fourth pass still
  deleted by NAME (lstat-classify then `unlink(name)`/`rmdir(name)`),
  so a replacement raced in between classification and deletion was
  deleted — that claim is retracted. Cleanup now never names a
  meaningful entry for deletion: the identity-proven ROOT is ATOMICALLY
  renamed to a fresh single-use private cleanup name at PATH level
  (`PATH/.aos-export-cleanup-<pid>-<n>`); every CHILD is atomically
  renamed to a `.aos-export-cleanup-<pid>-<n>` name INSIDE ITS OWN
  parent directory (nested within the quarantined tree, never a direct
  child of PATH); each captured entry is re-proven against the
  inspected identity (roots against the HELD descriptor), a captured
  mismatch is restored to its public name and the cleanup refuses, and
  the final unlink/rmdir targets only the just-re-proven private name.
  Failures restore the in-flight subtree and root toward their public
  names (a failed intermediate restore is itself reported, never
  silently discarded); only the initial pin-open's ENOENT reads as
  "genuinely absent" (a dedicated exception type — errno mapping makes
  an interior ENOENT a FileNotFoundError, which must surface as a
  reported retention instead), a RecursionError from a hostile
  deeply-nested tree becomes a reported retention rather than an
  internal error, and a PREV that vanished before cleanup warns
  accurately without instructing removal of a nonexistent tree. The
  reserved PATH-level cleanup names join the mutation roots; a leftover
  one (interrupted cleanup) is detected by a names-only listing of PATH
  and refuses the next run in both modes. NARROWED GUARANTEE: stdlib
  has no delete-by-descriptor and no no-replace rename, so an entry
  raced onto a just-verified single-use PRIVATE name in the
  pre-deletion syscall gap (for rmdir: only an empty directory), or a
  TYPE-COMPATIBLE entry raced onto a probe-fresh quarantine/restore
  target name before the rename (an empty directory for a directory
  move; a regular file or symlink for a file move — on the restore path
  that target is the entry's PUBLIC name), remains deletable — entries
  at meaningful names outside those windows are never deleted without
  an identity proof.
  (b) *Descriptor-anchored copy source (Q2, amends C4).* The build's
  payload copy opened an absolute source pathname (O_NOFOLLOW protects
  only the final component; a swapped source entity directory could
  redirect the read). The plan now records per-file source identities
  and the source-root identity; the build pins the source root for its
  complete run; every copy (creates, updates, unchanged fallback) opens
  entity dirs O_DIRECTORY|O_NOFOLLOW relative to the pin, the basename
  O_RDONLY|O_NOFOLLOW|O_NONBLOCK relative to the entity descriptor,
  requires S_ISREG + samestat with the plan record, copies only from
  the descriptor, and re-fstats after the copy. No absolute source open
  remains in the copy path (regression-forbidden).
  (c) *Final hardlink check without intermediate symlinks (Q3, amends
  F3).* The live side of the final hardlink verification was probed via
  "AOS/<rel>" under the destination descriptor — intermediate
  components followed symlinks, so a moved entity directory plus a
  symlink back to it passed samestat while retaining an external alias
  into the promoted generation. The held aos_fd now flows into the
  final verification; entity directories open O_DIRECTORY|O_NOFOLLOW
  relative to it and must carry exactly the identity the pinned rescan
  recorded; basenames are lstat'ed fd-relative; the live file must
  samestat the staged link AND have st_nlink == 2. The staged-alias
  tolerance probe is anchored the same way under the staging
  descriptor.
  (d) *Freshest-last final verification (Q4, amends F2).* A live
  destination write through a staged hardlink could mutate staged bytes
  after they were hashed while source verification still ran. Order is
  now: fresh source scan+hash FIRST, complete destination recheck
  second, complete staging rescan + content hash LAST (hardlink counts
  and identities re-checked in that last scan), then only identity
  lstats (structural guard, move-aside guard) and the renames — no
  content is read or hashed after the final staging scan, and the
  documented unobservable window is per file: from that file's read in
  the final rescan to the renames.
  (e) *Source mount containment (Q5).* Every source scan compares each
  non-hidden entry's st_dev with the source root (plus the additive
  mount probe for directories) and refuses mounted or cross-device
  source subtrees before any copy or hash; the same-filesystem
  bind-mount limitation of F6 applies unchanged.
- **D-v0.2.25 — U-C4 fourth corrective pass (reliability corrections
  C1–C6, 2026-07-14).** A fourth review confirmed six implementation
  defects in the uncommitted U-C4 code; all six are corrected without
  widening scope, each pinned by deterministic regression tests (31 new
  tests; full suite 570 green). Policies pinned:
  (a) *Identity-safe cleanup (C1).* Recursive STG/PREV cleanup runs
  through `_rmtree_pinned`: pin the root `O_RDONLY|O_DIRECTORY|
  O_NOFOLLOW` relative to the pinned PATH descriptor → prove the pinned
  identity equals the identity THIS run recorded (staging at creation;
  PREV pinned by an open descriptor taken immediately after the
  AOS→PREV rename, chained to the verified AOS root identity) → apply
  the C3 containment checks → delete children bottom-up with
  descriptor-relative operations only → re-check the named root before
  the final `os.rmdir`. `shutil.rmtree` is never used on STG or PREV,
  and the mutable root pathname is never reopened for deletion. The
  identity chain is descriptor-pinned end to end: staging (held from
  creation across every discard path), the verified AOS root (pinned at
  the recheck BEFORE its content rescan and held through promotion —
  the move-aside guard and the PREV proof compare against this held
  descriptor), and PREV (pinned immediately after the move-aside, held
  until cleanup). An open descriptor keeps the inode alive, so a freed
  inode number cannot be recycled into a foreign directory and defeat a
  samestat proof (observed live on tmpfs during this pass — tests and
  an adversarial reproduction caught recorded-stat versions deleting a
  substituted tree; both closed by the held-descriptor chain). Any root
  whose identity cannot be proven is retained byte-for-byte and
  reported (exit-0 WARN for PREV after successful promotion).
  (b) *Pinned hardlink source (C2).* Unchanged-file reuse links through
  the descriptor chain PATH-fd → AOS fd → entity fd (each
  O_DIRECTORY|O_NOFOLLOW), requires the source to be a regular file
  whose identity equals the plan-time record (`ExportPlan.
  base_identity`), calls `os.link(src, dst, src_dir_fd=…, dst_dir_fd=…,
  follow_symlinks=False)`, and verifies the staged link's type AND
  identity afterwards. `target.dest_aos / rel` is forbidden as a link
  source; a replacement PATH never has a link count changed.
  (c) *Cleanup-root containment (C3).* Before any deletion the pinned
  cleanup root must sit on the pinned destination's device, must not be
  a mount point (additive probe), and every descendant is swept for
  device/mount transitions through the pinned descriptor; a rejected
  root is retained with nothing beneath it modified. Same-filesystem
  bind mounts stay a documented stdlib limitation.
  (d) *Vetted reads (C4).* One shared reader (`_read_vetted_file`)
  performs every enforcement-critical read: descriptor-relative
  O_RDONLY|O_NOFOLLOW|O_NONBLOCK open, fstat of the opened descriptor,
  S_ISREG required, samestat against the inspected identity when
  provided, pre- and post-read fstat with identity/size stability, and
  actionable AosError refusals. Used for plan comparison, base-snapshot
  hashing, source scanning/hashing, and final source verification;
  `Path.read_bytes` is regression-forbidden for these. The build's
  payload-copy source open carries the same O_NOFOLLOW|O_NONBLOCK +
  S_ISREG vetting (a FIFO raced into a source note cannot block the
  copy), and the protected-root existence probe fails closed (an
  uninspectable candidate stays protected; EACCES/EIO surface as exit-1
  refusals, never exit-2 internal errors; an ELOOP no longer silently
  drops repository protection) — both found by this pass's adversarial
  review.
  (e) *Actual execution statistics (C5).* `apply_plan` returns a frozen
  `ApplyResult` (created/updated/deleted/unchanged, hardlinked vs
  fallback-copied unchanged, `payload_bytes_written`, `cleanup_warning`)
  measured during execution — copies report the fstat'ed size of the
  flushed staged file, hardlinks contribute zero bytes, fallback copies
  count in full; the CLI prints exclusively from it.
  (f) *Directory-visible dry-run (C6).* `ExportPlan.dir_creates` /
  `dir_deletes` are deterministic sorted differences; dry-run prints
  `create-dir REL/` / `delete-dir REL/` lines and a summary that counts
  files and directories separately, so a directory-only plan never
  shows zero visible operations.
- **D-v0.2.24 — U-C4 third corrective pass (filesystem-consistency
  findings F1–F6).** A third review confirmed six local
  filesystem-consistency issues in the uncommitted U-C4 implementation;
  all six are fixed without widening scope, each with regression tests
  proven to fail against the uncorrected mechanism. An adversarial
  multi-lens re-review of the fix itself then confirmed a further round
  of pathname/descriptor divergences and untested clauses; those are
  folded in below and each is pinned by a mutation-verified test.
  Policies pinned:
  (a) *Pinned destination descriptor (F1).* Before its first mutation the
  apply opens PATH `O_RDONLY|O_DIRECTORY|O_NOFOLLOW` (where available),
  fstats it, and requires identity equality with the destination identity
  recorded in the plan; the descriptor stays open for the COMPLETE apply.
  Staging is created and opened (O_NOFOLLOW) relative to it, every
  AOS/STG/PREV rename passes `src_dir_fd`/`dst_dir_fd`, every PATH-level
  durability fsync syncs the pinned descriptor itself, STG/PREV cleanup
  deletes fd-relative, and the enforcement rescans of destination and
  staging content walk and read descriptor-anchored (`os.fwalk` with
  `dir_fd`; per-file O_NOFOLLOW+O_NONBLOCK opens with an fstat samestat
  against the vetted lstat). After the pin, PATH-derived pathnames are
  consulted only to verify the pathname still reaches the pinned
  directory, to re-derive containment refusals, and for an additive
  best-effort mount probe — never for a mutation, an enforcement read,
  or a cleanup. Staging is discarded only after a samestat identity
  proof against the pinned staging descriptor; anything else at the
  staging name is RETAINED and reported. A replaced PATH, or a staging
  entry swapped between mkdir and open, refuses before any generated
  entry can appear outside the originally approved destination.
  (b) *Complete staged-generation re-verification (F2).* Validation
  returns an immutable `StagingSnapshot` (root identity, sentinel state,
  directory set, file set with sizes, length-framed content hash, entry
  types enforced by the scan, recorded hardlink relationships).
  Immediately before promotion — after the destination recheck — the
  ENTIRE staging generation is rescanned through the pinned staging
  descriptor and must equal the snapshot and a fresh source scan exactly;
  any stable post-validation change (bytes, file or directory add/remove,
  sentinel, symlink or special entry, root identity, hardlink
  relationship) refuses. The verification ends with a structural
  destination guard (PATH pathname identity, AOS root identity, PREV
  absence), so the unobservable interval for staging content and
  destination structure begins after it returns and ends at the
  promotion rename. Precisely stated limits: a destination CONTENT
  change during the staging verification itself is within the accepted
  window (the full content recheck runs immediately before it), and
  metadata-only destination changes (permissions, timestamps) are never
  part of the base snapshot.
  (c) *Constrained staged hardlinks (F3).* The build RECORDS which
  unchanged rels it intentionally hardlinked (with the staged link's
  device/inode identity); ownership is never inferred from link count.
  Validation and the final verification require st_nlink == 1 for every
  created, updated, or copied-unchanged staged file, and for every
  recorded link exactly st_nlink == 2 with the recorded identity — plus,
  at the final verification, `os.path.samestat` against the corresponding
  CURRENT AOS file. Any extra link, wrong identity, or missing expected
  source refuses; the pre-promotion destination rescan tolerates the
  staged alias only for rels the build recorded.
  (d) *Inspection errors are errors (F4).* One explicit `_lstat_or_absent`
  helper replaces `os.path.lexists` for the initial STG/PREV stale checks,
  the mutation-root probes, and the final PREV/STG verification:
  FileNotFoundError means absent; every other OSError (EIO, EACCES,
  EPERM, ...) produces an actionable refusal naming the path and cause.
  An uninspectable STG at the final recheck is additionally RETAINED —
  it is no longer provably ours.
  (e) *Sentinel durability (F5).* The ownership-sentinel directory is
  opened O_NOFOLLOW relative to the pinned staging descriptor and fsynced
  under the existing directory-fsync errno policy. Durability order:
  staged file writes (flush+fsync) → staging root → sentinel → entity
  directories → the PATH-level rename fsyncs.
  (f) *Mount containment (F6).* Mounted or cross-device subtrees inside
  AOS or STG refuse before adoption, validation, or promotion (per-entry
  st_dev vs the root device, plus `os.path.ismount` for directories; the
  AOS root itself must sit on PATH's filesystem), and every recursive
  STG/PREV cleanup sweeps for mount boundaries first — never inspected
  means never deleted. The sweep is descriptor-anchored (`os.fwalk` with
  `dir_fd`), so it inspects exactly the tree the fd-relative delete
  would recurse into; the pathname `os.path.ismount` probe is
  additive-only (its errors read as "no extra evidence", never as
  clearance). Documented limitation, stated wherever the claim
  appears: a bind mount of the SAME filesystem has the same st_dev and is
  invisible to `os.path.ismount`, so the standard library cannot
  distinguish it from a plain directory; cross-device mounts are the
  enforced class.
- **D-v0.2.23 — U-C4 post-review hardening.** Independent review of the
  D-v0.2.22 implementation confirmed four blockers and five hardening
  gaps; all nine are fixed without widening U-C4 scope. Policies pinned:
  (a) *Fresh plan + destination base snapshot.* check_destination's
  adoption inspection stays the refusal-first gate before any local work,
  but the plan is computed from a FRESH destination scan taken after the
  mirror regenerates (dry-run prints from that fresh state), and
  `ExportPlan` records an exact base snapshot — AOS existence and
  directory identity, directory set, file set with sizes, sentinel
  presence, and a length-framed content hash (relpath + NUL + length +
  NUL + bytes per file, sha256). The pre-promotion recheck rescans and
  requires an exact match; any addition, deletion, content edit,
  directory change, root replacement, or identity change exits 1 with
  "Refusing to export: destination changed during export; rerun to
  compute a fresh plan." — a late destination file can no longer be
  silently swept by the whole-tree swap (the rerun's fresh plan SEES it
  as an explicit, previewable delete).
  (b) *Ownership sentinel.* Recognized filename shape is NOT proof of
  ownership (a human `Home.md` or `Tasks/T-9999.md` is not ours to
  delete). `PATH/AOS/.aos-export-owned` — one exact reserved EMPTY
  internal directory, invisible to file-based tree hashes — is created in
  staging, required by validation, preserved through promotion, excluded
  from note counts and comparisons, and demanded on every repeat export.
  First exports adopt only an absent or genuinely empty AOS; a nonempty
  AOS without the exact sentinel, any content inside it, or any other
  hidden entry refuses.
  (c) *Lexical workspace derivation.* The live workspace and the upward
  `.git` search derive from `aos_dir.parent.resolve()` (lexical parent,
  then resolve), never `aos_dir.resolve().parent`: with `repo/.agentic-os`
  symlinked elsewhere the latter protected only the link target's parent
  and permitted `repo/AOS` as an export root. The `.agentic-os` target,
  database parent, vault, and source mirror stay independently resolved
  and protected.
  (d) *Complete final recheck with a pinned staging identity.* The
  recheck re-lstats AOS, STG, and PREV (symlinks refuse for all three),
  confirms `PATH` identity, requires PREV absent, repeats containment,
  and holds AOS to the base snapshot — never resolve-and-accept of a
  replacement real directory. STG must be the same real directory this
  run created, verified via an O_DIRECTORY descriptor held open since
  mkdir: the open descriptor pins the inode, closing the rmtree+mkdir
  inode-reuse hole that defeats a samestat-only check. The STG check runs
  first — staging is only discarded while provably ours; a removed or
  replaced STG is RETAINED with instructions. The post-recheck/pre-rename
  interval remains the only accepted TOCTOU exclusion.
  (e) *Rollback durability.* `rename(PREV, AOS)` is followed by a PATH
  fsync. If the rollback fsync fails, no durable-restoration claim is
  made and the complete staging tree is NOT discarded: the error reports
  the exact live state (AOS = previous generation, new generation at STG)
  and the possible post-crash state (AOS missing, previous generation at
  PREV — the existing drill row).
  (f) *Reported staging cleanup.* No `ignore_errors=True`: a failed
  staging cleanup appends "staging … could not be removed …; remove it
  before rerunning" to the original error instead of masking either.
  (g) *Shell-quoted recovery commands.* Every emitted `mv` recovery path
  goes through `shlex.quote` (destination paths routinely contain
  spaces).
  (h) *Hardlink-alias refusal.* Adopted regular destination files must
  have link count 1 — an alias means the bytes are shared with something
  outside AOS, which full ownership cannot claim (and staging's own
  `os.link` reuse would propagate the alias into every future
  generation). During the pre-promotion rescan exactly one extra link per
  file is tolerated: this run's own staged hardlink, verified by
  samestat against the staged path.
  (i) *lstat-typed staging validation.* Every staged entry is lstat'ed;
  only real directories and regular files pass — staged symlinks (even to
  byte-identical content) and special files refuse before any content
  read (a FIFO must not hang validation).
  (j) *Descriptor-anchored staging build (self-review addendum).* An
  adversarial re-review found one build-phase escape the post-build
  recheck could not catch: a same-user racer swapping a just-created,
  still-empty staging entity directory for a symlink, so the subsequent
  O_EXCL note writes land outside AOS/STG/PREV. Closed by building every
  file through pinned directory descriptors — entity dirs created relative
  to the pinned STG-root fd and reopened O_NOFOLLOW; files created relative
  to those fds (O_CREAT|O_EXCL, `os.link` with `dst_dir_fd`) — so a raced
  symlink swap is refused (ELOOP/EEXIST), never followed. The same review
  also collapsed the plan's destination reads to one per file (the bytes
  feed both change-detection and the base-snapshot hash) and corrected the
  contract's tree-hash formula to record the length framing the code
  already used.
- **D-v0.2.22 — U-C4 implementation policies.** Baseline gate: branch
  `v0.2-u-c4-windows-export`, HEAD `70aac05`, clean tree, 390 tests OK.
  `aos sync --export-to PATH [--dry-run]` lands in
  `agentic_os/mirror_export.py`; policies pinned during implementation:
  (a) *Whole-tree generation swap, never per-file live replacement.* The
  destination `PATH/AOS` always holds one complete generation: the next
  generation is built and validated in `PATH/.aos-export-staging`, the
  current one moves aside to `PATH/.aos-export-previous`, staging is
  renamed in, and PREV is removed only after durability is confirmed.
  A failed promotion rolls back to PREV; a failed rollback leaves both
  complete generations with exact `mv` recovery commands. Per-file
  replacement of a live tree was REJECTED: an interruption would leave a
  mixed-generation mirror, which the contract forbids outright. The
  update path has a two-rename window with no `PATH/AOS`; the first
  export is a single atomic rename.
  (b) *Full ownership of `PATH/AOS`.* Nothing inside it is preserved —
  adoption refuses any hidden, symlinked, non-regular, or unrecognized
  entry (the doctor note-recognizer doubles as the provenance test, and
  the export refuses to ship anything the recognizer would not
  re-accept). Preservation applies only outside the three mutation roots;
  docs direct Obsidian at PATH as the vault root, never PATH/AOS.
  (c) *Copy-if-changed.* An identical source (file set, bytes, dir set)
  performs zero mutation — no staging, no rename, no write. Changed
  exports hardlink unchanged destination files into staging and copy only
  changed/new files; `os.link` falls back to copying ONLY on the
  recognized unsupported-link errnos {EPERM, EACCES, EOPNOTSUPP/ENOTSUP,
  ENOSYS, EXDEV, EMLINK} — any other errno (EIO, …) aborts with the old
  generation intact. Change detection is size-then-byte, never mtime.
  (d) *Existence-aware mutation-root containment.* Only the three
  mutation roots are checked (PATH may be an ancestor of the repository):
  PATH resolves strictly first; each root, when present, is lstat'ed
  (symlink ⇒ refusal) and strictly resolved, and when absent its
  candidate is the resolved parent plus the fixed child name. Overlap
  with the independently resolved protected set (workspace, .agentic-os,
  db parent, vault, source mirror, enclosing git root — a `.git` file
  counts, for worktrees) uses normalized equal/inside/contains always
  plus `os.path.samestat` whenever both sides exist; the checks repeat
  immediately before promotion.
  (e) *Durability.* Staged copied files are flushed+fsynced; staged
  directories and PATH (after each rename and after PREV cleanup) are
  fsynced with directory-fsync failures skipped ONLY for {EINVAL,
  ENOTSUP/EOPNOTSUPP, ENOSYS} (9P/DrvFS reject directory fsync); any
  other errno is fatal and lands in the documented recovery state for
  that phase. File-fsync failures are always fatal.
  (f) *Stale state refuses in dry-run too.* Existing staging or previous
  directories mean an interrupted or concurrent export — both modes exit
  1 with the recovery instructions and compute no plan; nothing is ever
  auto-cleaned (it could be a live run's staging or the only last-good
  copy).
  (g) *Windows representability, deterministic on all platforms.*
  Refusals for reserved device stems, illegal characters, control
  characters, trailing dot/space, source casefold collisions (mixed-case
  agent names are the only generated source), and components above 255
  UTF-16 code units — the accurate NTFS limit; no invented total-path
  limit, and source-side POSIX limits surface as the real OS error.
  (h) *Boundaries.* The export is EVENTLESS (extends D-P0.6/D-W7.1);
  nonexistent PATH refuses (typo protection); `sync --export-to`
  regenerates the local mirror first in both modes — dry-run purity
  protects the destination only.
  (i) *Shared rules extraction.* The note-recognizer, hidden-entry rule,
  and wikilink regex moved from doctor privates to public
  `obsidian.recognized_note_rel` / `obsidian.is_hidden_rel` /
  `obsidian.WIKILINK_RE` (doctor keeps thin aliases), so doctor and the
  export consume one definition of "a file sync generates".

# DECISIONS — Agentic OS v0.2 U-C3 secret warn-on-write run

This section continues the `D-v0.2.*` series for the U-C3 pass executed per
`agentic-os-v0.2-u-c3-secret-safety-contract.md` on branch
`v0.2-u-c3-secret-safety` (2026-07-12). D-v0.2.15 remains the behavioral
decision; this section records only the implementation policies the build
surfaced. Prepended per the established precedent (D-W0.4, reaffirmed in
D-v0.2.7); everything below stays byte-identical.

## D-v0.2 decisions (U-C3)

- **D-v0.2.21 — U-C3 implementation policies.** Baseline gate: branch
  `v0.2-u-c3-secret-safety`, HEAD `410289f`, clean tree, 336 tests OK,
  doctor 17/17 on a fresh workspace. The detector moved verbatim to
  `agentic_os/secretscan.py` (side-effect-free; `pack.scan_secrets` and
  `pack.SECRET_PATTERNS` stay as re-exports because pack was its
  historical home). Policies pinned during implementation:
  (a) *Metadata keys, sparsity, and payload redaction.* An affected
  successful mutation's normal event payload gains `secret_warning`
  (true), `secret_fields` (canonical field labels, input order), and
  `secret_patterns` (detector order, deduplicated) — and never the
  matched value: every event payload passes `secretscan.redact_tree`
  inside `events.emit`, replacing each secret-shaped string leaf (nested
  lists/dicts included) with the one fixed placeholder
  `secretscan.REDACTED_VALUE` — no hash, fingerprint, preview, excerpt,
  or offset. The emit choke point also keeps a previously accepted
  secret-shaped identifier (an agent name on `agent update`, a project
  slug or repo path copied forward) out of every later event, and applies
  the same fixed placeholder to the top-level `events.actor` column: a
  syntactically valid `agent:<name>` evidence provenance can be
  credential-shaped and flows directly into the actor, so no matched
  value may remain anywhere in the event record — payload OR actor —
  while benign actors are stored byte-identical. The canonical domain
  row keeps the accepted value (the ledger stays honest). Redaction is
  the identity on benign strings and the metadata keys are absent on
  unaffected writes, so every pre-U-C3 payload shape AND value stays
  byte-identical. No second event. Scan labels are enforced against the
  fixed `secretscan.TRUSTED_FIELD_LABELS` allowlist; `project add` scans
  the validated slug, display name, and resolved repo path,
  `agent update` re-scans the reused name, and `evidence add` scans ref,
  claim, and the validated provenance — a trusted mirror/export-bearing
  field (rendered in the evidence note, passed as the event actor).
  (b) *Warn after commit.* The stderr WARNING prints only after the
  mutation's transaction commits — a rolled-back write must never warn,
  and a warned write is always a real one. One line per command, fields
  and pattern names only, value never repeated.
  (c) *Override reason included.* `done --no-evidence --reason` stores the
  reason verbatim in the `done_override` payload, so the reason is scanned
  and that payload (the one carrying the text) gets the safe metadata —
  the minimum-coverage list did not name it, but an unscanned journaled
  free-text field would be a hole in the sweep.
  (d) *Doctor sweep shape.* One warn-only check (#18) scans the canonical
  text columns of projects/tasks/runs/decisions/evidence/handoffs/memory/
  agents — including `slug`, `repo_path`, `conventions_md`,
  `invoke_hint`, evidence `provenance`, and the task `assignee` and
  `branch_hint` columns (rendered task frontmatter and pack REPO & BRANCH
  content), which have no CLI write path yet or arrive validated but are
  pack/mirror-bearing. Legacy raw `events.actor` values are raw-scanned
  with the shared detector and reported as `event #id` under the fixed
  safe label `actor` with canonical pattern names only; post-U-C3 events
  never hold a matched actor (emit redacts it), so their visibility comes
  from the safe metadata. Event payloads are covered two ways: doctor
  reads well-formed U-C3 metadata (`secret_warning` is `true` plus
  list-typed `secret_fields`/`secret_patterns`) so redacted historical
  events stay visible, accepting field names only from
  `secretscan.TRUSTED_FIELD_LABELS` and pattern names only from
  `secretscan.PATTERN_NAMES` — malformed or tampered metadata is ignored,
  never echoed — and still raw-scans every legacy payload string value,
  each string individually so a JSON key (`key`, `token_estimate`) can
  never lend keyword context to a neighboring value. A payload key is
  echoed as a finding label only when it looks like one of our snake_case
  keys and is itself negative under the detector; anything else reports
  as `payload`. Findings name entity + public ID (or `event #id`) + field
  + pattern names; distinct findings are deduplicated deterministically
  in first-seen order and display is bounded to 10 findings plus a
  `(+N more)` count. Projects and agents are identified by ROW id
  (`project #1`, `agent #1`), never slug or name: those fields are
  themselves scanned, and a secret-shaped one must not be echoed as the
  identifier of another field's finding. Domain hits normally also appear
  as event-metadata hits (the add event marks the same fields): accepted
  as honest double visibility, not deduplicated across sources. Doctor's
  exit semantics are unchanged.
  (e) *Value-echo policy scope.* Canonical domain rows retain accepted
  trusted-human values, and ordinary user-requested ledger readbacks
  (`task list`/`show`, `log`, `--json` documents) and the generated
  mirror may reflect them. Warnings, event payloads, the event actor
  column, doctor findings, U-C3 refusal/exception text, and this unit's
  test failure diagnostics never echo a matched value. Context packs and
  untrusted dropfile ingest
  keep their atomic hard refusals. This is a targeted no-echo rule at the
  listed surfaces, not general output redaction.

# DECISIONS — Agentic OS v0.2 release-readiness audit

This section records the 2026-07-11 continuation audit across the public
`agentic-os` control plane and private `ai-company-runtime` execution plane.
It prepends new decisions without changing the historical sections below.

## D-v0.2 decisions (release readiness)

- **D-v0.2.14 — Two repositories, one artifact boundary.** `agentic-os`
  remains the local governance/memory ledger (SQLite); `ai-company-runtime`
  remains the operational execution plane (Postgres). They will not share or
  synchronize tables. Future integration uses a versioned result envelope
  carrying AOS/runtime task references, evidence hashes, and trace/correlation/
  causation ids. This prevents two mutable sources of truth while preserving
  end-to-end auditability.
- **D-v0.2.15 — Warn-on-write secret posture (U-C3).** U-C3 preserves
  the existing hard refusals for pack construction and untrusted dropfile
  ingest. Trusted human CLI writes to mirror-bearing project/task/run/decision/
  evidence/handoff/memory/agent fields remain non-blocking; an affected
  successful mutation will print a warning and store pattern/field names only
  in its normal event. Doctor will report identifiers and safe metadata only,
  never matching values. Rationale: do not silently falsify the append-only
  record, but make exposure visible and actionable.
- **D-v0.2.16 — Success claims require proof (approved later U-H2
  unit).** A separate U-H2 contract will require a dropfile declaring
  `outcome: success` to carry evidence or be refused atomically. Direct run
  endings will remain available for honest/manual recovery, while doctor will
  warn when a successful run has no evidence created inside its run window.
  This behavior is not part of the U-C2 baseline or the U-C3 implementation.
- **D-v0.2.17 — Distribution boundary approved for later U-P1.**
  A separate U-P1 unit may add `pyproject.toml`, an `aos` console script,
  `python -m agentic_os`, build metadata, version `0.2.0`, and a Python 3.12
  floor. None of that packaging behavior is present in the verified U-C2
  baseline or included in U-C3.
- **D-v0.2.18 — GitHub delivery gate approved for later U-P1.**
  A separate delivery unit will add PR/push CI for supported Python versions,
  including unittest, compile, wheel, installed-entrypoint, fresh-init, and
  doctor smoke gates with official actions pinned to immutable full commit
  SHAs. Branch protection and reviewed-PR requirements remain human repository
  settings. No CI implementation is claimed by this audit.
- **D-v0.2.19 — Blueprint authority without roadmap erasure.** The canonical
  near-term sequence remains the user's existing plan: U-C1 input hardening →
  U-C2 backup/verify/restore → U-C3 secret warn-on-write + doctor sweep → U-C4
  Windows Obsidian export → U-H1 SessionEnd dropfile hook + trust-gated
  installer. U-C1 and U-C2 are complete, so U-C3 is next. The broader
  `AGENTIC_OS_BLUEPRINT.md` extends that spine with cross-repository architecture
  and later milestones; it does not supersede, reorder, or erase it. Older
  research and two-week documents remain evidence/history, while newer explicit
  decisions may amend individual items without silently rewriting the sequence.
- **D-v0.2.20 — Proof and identifier hardening approved for a later
  bounded unit.** A separate contract may enforce priority 1–5, non-blank
  optional task text, non-blank evidence refs/claims, safe agent-name grammar,
  non-blank run summaries, and post-collapse dropfile evidence validation.
  These changes are not present in the verified U-C2 baseline and are excluded
  from U-C3.

# DECISIONS — Agentic OS v0.2 U-C2 backup/verify/restore run

This section continues the `D-v0.2.*` series for the U-C2 pass executed per
`agentic-os-v0.2-u-c2-backup-restore-contract.md` on branch
`v0.2-u-c2-backup-restore` (2026-07-08). That contract wins over the
two-week plan and the v2 research report where they differ. Prepended above
the earlier sections per the established precedent (D-W0.4, reaffirmed in
D-v0.2.7); everything below stays byte-identical.

## D-v0.2 decisions (U-C2)

- **D-v0.2.8 — U-C2 baseline gate results.** Branch
  `v0.2-u-c2-backup-restore`; HEAD `1ed30a3` ("docs: add v0.2 U-C2 backup
  restore contract"). Working tree clean. Python 3.12.3. Baseline suite:
  **300 tests, OK**; doctor: **17/17 PASS** (incl. the warn-only check).
  `CLAUDE.md` in the contract's read-first list still does not exist —
  recorded, nothing to read. Behavior pinned by prototype before writing
  code: a single flipped bit in a backup copy passes
  `PRAGMA integrity_check` (SQLite pages carry no checksums) but fails a
  sha256; a zeroed page or truncation makes `integrity_check` *raise*
  `sqlite3.DatabaseError` rather than return a row; and a plain read-only
  open of a WAL-marked backup file creates `-shm`/`-wal` droppings beside
  it, which `immutable=1` prevents. These three facts shaped U-C2.2–U-C2.3.
- **D-v0.2.9 — Backup format and location (U-C2.1).** `backup create`
  writes `backups/aos-backup-<UTCSTAMP>Z.db` inside the workspace via the
  sqlite3 backup API (`conn.backup`, the D-W7.2 rule — never a raw copy of
  a live WAL database), then a sibling manifest, then emits one
  `system/backup_create` event carrying the sha256/size/paths — event
  after files, so a backup never contains its own event (the `snapshot`
  precedent). Name collisions bump `-2, -3, …` pair-aware (a lone stale
  manifest also blocks its stem). The `backups/` folder is created lazily
  on first use and deliberately NOT added to the required workspace layout
  (`obsidian.WORKSPACE_DIRS`) — adding it would fail doctor's
  required-folders check on every existing workspace, breaking Night-1
  back-compat for a folder most workspaces won't have yet. `create`
  refuses (exit 1, before any write) when the live database fails
  `PRAGMA integrity_check`: a nightly `backup create` must be a health
  check, not a machine for archiving corruption. No `--output` override
  and no retention policy in v0.2 (noted as limitations; RECOVERY.md tells
  humans to copy the pair off-machine).
- **D-v0.2.10 — Manifest fields (U-C2.2).** Sibling file
  `<stem>.manifest.json` (the pair moves together; verify refuses a lone
  backup): `aos_backup_manifest` (format version, `1`), `created_at`
  (UTC-Z, single clock), `source_db_path`, `schema_version` (read from the
  source meta table), `size_bytes`, `sha256` (of the backup db file), and
  `tool` (`agentic-os <version> (aos.py backup create)` — the contract's
  "where practical" label). JSON via the canonical `utils.json_dumps` +
  `write_text_lf` (LF-only guarantee). Unknown extra keys are tolerated on
  read (forward compat); an unknown `aos_backup_manifest` value is refused.
  Field types are validated on verify (sha256 must be 64 lowercase hex —
  `\Z`-anchored per D-v0.2.3; `size_bytes` a non-negative non-bool int).
- **D-v0.2.11 — Verify semantics (U-C2.3).** `backup verify PATH` runs
  eight ordered checks and stops at the first failure (each later check
  assumes the earlier ones): file exists · manifest exists · manifest
  well-formed · size matches · sha256 matches · opens as SQLite ·
  schema_version supported (backup ↔ manifest ↔ build) ·
  `PRAGMA integrity_check` passes (its `DatabaseError` raise is caught and
  reported as the check's failure). Output is doctor-style `[PASS]`/
  `[FAIL]` lines, exit 1 + a one-line stderr verdict on failure. Both hash
  and structure checks are load-bearing per D-v0.2.8, and each has a test
  the other cannot pass (bit-flip vs zeroed-page-with-regenerated-
  manifest). Verify (and restore) deliberately never open the live ledger
  and are eventless (extends D-P0.6): recovery tooling must work exactly
  when the workspace is damaged or absent, so unlike every other
  later-phase command they do not go through `_ledger` and work pre-init
  (a deliberate, journaled exception to the D-P2.4 pattern). The backup is
  opened `mode=ro&immutable=1` with a percent-encoded URI (`%`, `#`,
  spaces in paths covered by test), so verifying cannot write anything —
  pinned by a directory-snapshot test.
- **D-v0.2.12 — Restore overwrite policy (U-C2.4).** `backup restore PATH
  --to NEW_DB_PATH` targets a database file path (restore-into-a-fresh-root
  is documented in RECOVERY.md as db-restore + the drill, since a db alone
  is not a workspace). It verifies the backup first (a corrupt backup
  refuses before any write, naming the failed check), creates the target
  with `open(..., "xb")` — an atomic, TOCTOU-free refusal of any existing
  file/directory including the live `aos.db`, with **no overwrite flag by
  design** (the contract's preferred v0.2 behavior; pinned by a test that
  `--force`/`--overwrite` are unrecognized) — streams the copy with an
  in-flight sha256, and on any post-copy mismatch removes the partial file.
  A byte copy is correct here (unlike create) because the source is a cold
  verified file, and it makes the restored file provably bit-identical to
  the manifest. Adopting the restored db as the live ledger is the human's
  manual `mv`, mirroring human-controlled git; RECOVERY.md's drill has the
  human move the damaged db (and its `-wal`/`-shm`) aside first.
- **D-v0.2.13 — Adversarial review round.** Before final validation, a
  five-lens review (correctness, contract compliance, test integrity, docs
  accuracy, adversarial bypass) with two independent refuters per finding
  ran over the diff. Confirmed and fixed: a mid-copy `OSError` during
  restore left a partial target file that blocked its own retry with a
  misleading overwrite refusal and leaked as exit 2 (now unlinked +
  refused as a one-line exit-1 error, pinned failing-then-passing); this
  run's first DECISIONS.md edit deleted the U-C1 section's H1 heading —
  not a pure prepend (restored; `git diff` now shows zero deleted lines);
  no test could distinguish backup-API creation from a raw live-file copy
  — a `shutil.copyfile` mutant survived all 333 tests (now killed by a
  WAL-discriminator test: `wal_autocheckpoint=0`, committed marker row
  living only in `-wal`, raw main-file copy proven blind to it, backup
  proven to contain it); verify's supported-by-this-build schema branch
  was unexercised — deleting it survived the suite (now killed by a test
  where backup db and manifest AGREE on schema `999`); RECOVERY.md
  overstated the exit-1 refusal of `backup create` on corruption (gross
  corruption dies in the workspace open with a database error before the
  guard — reworded). Also hardened from technically-true-but-refuted
  findings: manifest format check is now type-strict (JSON `true`/`1.0`
  no longer pass as format 1 via Python's `True == 1`; pinned by tests)
  and RECOVERY.md's inspection step no longer assumes a `sqlite3` CLI
  this machine doesn't have (stdlib `python3 -c` one-liner). Refuted, no
  change (recorded as known limitations): a write-locked live db makes
  `backup create` exit 2 after writing a valid-but-unjournaled backup
  pair (busy_timeout makes this a >5s-contention corner; the pair is
  harmless and verifiable); empty `--to` resolves to cwd and refuses with
  a literal-but-safe message; verify blesses any structurally-valid
  schema-1 SQLite file with a consistent manifest (verify proves
  integrity and provenance-by-hash, not ledger-shape — matches the
  contract's check list exactly).

# DECISIONS — Agentic OS v0.2 U-C1 input-hardening run

This section (`D-v0.2.*`) journals the U-C1 pass executed per
`agentic-os-v0.2-u-c1-hardening-contract.md` on branch
`v0.2-u-c1-input-hardening` (2026-07-08). That contract wins over the
two-week plan and the v2 research report where they differ. Prepended above
the earlier sections per the established precedent (D-W0.4); everything
below stays byte-identical.

## D-v0.2 decisions

- **D-v0.2.1 — P0 baseline gate results.** Branch
  `v0.2-u-c1-input-hardening`; HEAD `5dc5971` ("docs: add v0.2 U-C1
  hardening contract"). Working tree clean (ignored: `.agentic-os/`,
  `__pycache__/`). Python 3.12.3. Baseline suite: **256 tests, OK**;
  doctor: **17/17 PASS** (incl. the warn-only check). The contract's
  read-first list names `CLAUDE.md`, which does not exist in this repo —
  recorded here, nothing to read. Pre-fix defects reproduced live before
  any edit: `T-0000` reached the DB lookup; a 32-digit id exited 2
  (`OverflowError` on the SQLite bind, W-1); a 5000-digit id exited 2
  (CPython int-conversion limit — a failure mode the research report did
  not list); `project add $'proj\n'` succeeded, writing a newline-bearing
  slug (W-2's INFERRED exploit, now CONFIRMED end-to-end).
- **D-v0.2.2 — ID maximum (U-C1.1).** `ids.MAX_ID = 2**63 - 1`, the SQLite
  INTEGER (signed 64-bit) bound already used by the dropfile parser — no
  row can ever carry a bigger rowid, so anything above it is refused
  *before* any DB lookup, as are zero-equivalent ids (`T-0`, `T-0000`, …;
  ids start at 1). Magnitude is judged after stripping leading zeros, so
  zero-padding stays legal (as it always was) at any length; a digit-length
  pre-check on the stripped digits (`> 19` refuses without converting)
  keeps CPython's ~4300-digit int-conversion limit unreachable. The
  over-maximum message does not echo the oversized input back. Round-trip
  behavior for all real ids (1…MAX_ID) is unchanged.
- **D-v0.2.3 — Strict validator anchors (U-C1.2).** Every regex that
  validates user/filesystem input now anchors with `\Z`, never `$` (which
  admits a trailing newline): `ids._ID_RE`, `models.SLUG_RE`,
  `models.PROVENANCE_RE`, `utils._DATE_RE`, `ingest._TASK_RE`,
  `ingest._AGENT_RE`, all nine `doctor._NOTE_PATTERNS`, and
  `render._PLAIN_SAFE` (with `$`, a trailing-newline value was written
  *plain* into note frontmatter — mirror corruption, found during this
  run's audit; `models.AGENT_NAME_RE` already used `\Z`). Audited and
  deliberately left on `$`: per-line parsers whose input is split on
  newlines first and so cannot contain one (`ingest._EVIDENCE_BULLET_RE`,
  `doctor._FRONTMATTER_LINE`) and `pack._HEX_ONLY` (input pre-filtered to
  `[A-Za-z0-9+/=]` runs) — behaviorally identical there, and the diff
  stays surgical. `parse_id` still strips *surrounding* whitespace by
  design (pinned by an existing test); `\Z` guards the match itself.
- **D-v0.2.4 — Run-start lifecycle policy (U-C1.3).** `run start` requires
  task status `ready`, consuming the legal `ready→in_progress` transition;
  `inbox` (untriaged), `in_progress` (already running), and `done` tasks
  refuse (done keeps its specific closed-task message). The refusal names
  the fix (`task status T-XXXX ready`) and writes no rows and no events.
  Two existing tests used the closed loophole as *setup* and were re-routed
  without weakening their assertions: the projectless-in_progress assign
  test now forces the legacy state via raw SQL (this class's established
  pattern for unreachable states), and the multiple-open-runs ingest test
  reaches two open runs via the legal ladder (start → status ready →
  start). A projectless run-start is now impossible via the CLI (ready
  implies a project); the ops-layer degradation note for legacy projectless
  rows remains.
- **D-v0.2.5 — no-evidence reason policy (U-C1.4).** `done --no-evidence`
  without `--reason TEXT` (or with a blank reason) refuses; with a reason
  it closes and journals the text in the `done_override` event payload as
  `{"task", "reason": TEXT, "via": "--no-evidence"}` (formerly the payload
  carried the constant `"reason": "--no-evidence"`; no test pinned it).
  `--reason` without `--no-evidence` is flag misuse and refuses, and so is
  `--no-evidence` on a task that turns out to have evidence (previously the
  flag was silently ignored and the reason silently discarded; now the
  refusal names the plain `done` command to run instead). Evidence-gated
  done is byte-for-byte unchanged. Four existing test call sites that
  passed the bare flag gained a reason argument; their assertions are
  untouched.
- **D-v0.2.6 — Dropfile ingest caps (U-C1.5).** `MAX_DROPFILE_BYTES` = 1
  MiB (checked via `stat` before the file is read, then re-checked on the
  bytes actually read — the writer is an untrusted agent process that may
  still be appending between stat and read), `MAX_EVIDENCE_ROWS` = 200,
  `MAX_QUESTIONS` = 100 (checked during parsing, naming the first line
  beyond the cap) — the research report §10 values. Refusals exit 1 before
  the write transaction opens, so no partial rows ever land, and a refused
  file records no ingest event (dedupe behavior intact). Boundary behavior
  pinned: exactly-at-cap ingests. The parser's task-id bound now also
  refuses `T-0000` and applies the D-v0.2.2 magnitude rule (leading zeros
  stripped, digit-length checked before `int()`), reusing `ids.MAX_ID` and
  keeping the pinned "task id out of range" message.
- **D-v0.2.7 — Adversarial review round.** Before final validation, a
  four-lens review (correctness, contract compliance, test integrity,
  remaining bypasses) with two independent refuters per finding ran over
  the diff. Confirmed-and-fixed: `--no-evidence` with existing evidence
  silently discarded the reason (now refuses, D-v0.2.5); byte cap was
  stat-only (now re-checked on read, D-v0.2.6); zero-padded >19-digit ids
  refused with a wrong message (now magnitude-based, D-v0.2.2); D-v0.2.x
  code-comment cross-references were off by one (renumbered); two anchor
  tests didn't discriminate pre/post fix (regex-level assertions added);
  ingest no-partial-write assertions now also count the tasks and
  decisions tables the contract names. Refuted (no change): DECISIONS.md
  prepend-not-append (follows the file's own D-W0.4 precedent; old
  sections byte-identical), and a claimed second open run on T-0005
  (factually false — R-0003 was ended before R-0004 started).

# DECISIONS — Agentic OS complete-today BUILD run

This section (`D-C.*`) journals the build pass executed per
`agentic-os-complete-today-build-prompt.md` on branch `two-week-scope`
(2026-07-07). That contract WINS over the two-week plan where they differ;
the plan stays detail authority elsewhere. Prepended above the planning
section per the established precedent (D-W0.4); everything below stays
byte-identical.

## D-C decisions

- **D-C.1 — P0 baseline gate results.** Branch `two-week-scope`; HEAD
  `114c882` ("docs: add complete-today build contract"), a descendant of
  `85d3793`. Working tree clean; the only ignored entry is `.agentic-os/`
  (runtime state). No `*Zone.Identifier` junk existed (nothing to delete).
  Python 3.12.3. Baseline suite: **162 tests, OK** (matches the expected
  162+). Dogfood loop opened in this repo's ledger before any edit:
  task **T-0003** ("Complete-today build", kind code, project agentic-os),
  run **R-0002** (agent claude-code) — actual IDs, not assumed.
- **D-C.2 — Contract-over-plan reconciliations (the contract wins).**
  (1) `task assign` may MOVE a non-done task between projects (plan §3.1
  refused moves). (2) `task assign` does NOT auto-promote `inbox→ready`
  (plan A1 promoted): the contract's own smoke test runs `task status
  T-0001 ready` immediately after assign — auto-promotion would make that
  a `ready→ready` illegal transition and fail the smoke. Status changes
  belong exclusively to `task status`. (3) `task edit` priority range is
  1–5 (plan said 0–9). (4) Dropfile dedupe: sha256 recorded in the ingest
  EVENT payload and duplicates REFUSED with exit 1 (plan: meta-key +
  no-op exit 0). (5) Dropfile runs ladder: exactly one open run for the
  task+agent is ended with the dropfile outcome (plan/D-0003: never
  auto-end — superseded by this contract's pinned ladder). (6) P3 is a NEW
  command `evidence git T-# COMMIT [--repo] [--claim]`; `evidence add
  --kind commit` keeps its Night-1 store-as-is behavior (plan B2 wanted
  validation inside `evidence add`). (7) Agent kinds are
  `local|cloud|human|generic` with repeatable `--capability` and generated
  `AOS/Agents/<name>.md` notes (plan C1: `cli|api|ide|other`, CSV flag, no
  vault notes). (8) `review weekly` ships (the plan deferred it).
- **D-C.3 — `task assign` semantics.** Same-project re-assign is a no-op:
  exit 0, prints a note, no event (mirrors `project add` idempotency,
  D-P0.12). Done tasks refuse (terminal). Event `(task, assign)` payload:
  {task, project, from_project} — from_project is null for a first assign.
- **D-C.4 — `task edit` details.** Editable set is closed: title, kind,
  priority, accept, spec. `task add --spec` included (plan A2 bundles it
  into the same item; no contract conflict — the `add` event payload is
  unchanged). Event payload lists the changed field NAMES only, in the
  fixed order title/kind/priority/accept/spec; "changed" means "provided"
  (values are not compared — the ledger journals intent, values live in
  the row). Empty values refuse: clearing a field is out of scope.
- **D-C.5 — `task status` refusal precedence.** (1) target `done` → points
  at `python aos.py done X` (the evidence gate is sacred), (2) source is
  done → frozen, (3) transition legality (legal set named), (4) projectless
  `inbox→ready` → "assign a project first" naming `task assign`.
- **D-C.6 — `task list` filters.** `--kind` (validated) and
  `--missing-evidence` (zero evidence rows, any status, composable with
  `--status`/`--project`). `--assignee` skipped per the contract's "unless
  trivially supported": `tasks.assignee` is write-never, so the filter
  would be dead surface over an always-NULL column.
- **D-C.7 — Dropfile parser strictness.** Exact `# AOS DROPFILE` header;
  `task:`/`agent:`/`outcome:`/`summary:` in that order; both `## evidence`
  and `## open questions` headings required (each may have zero bullets);
  blank lines are skipped between elements; CRLF files are normalized for
  parsing (the dedupe hash is over the RAW bytes); a bare CR inside a value
  splits the line and is refused (injection defense, D-W9.1 lineage); every
  stored value is one-line-collapsed. Malformed errors name the line
  NUMBER, never the content — a bad line could be exactly the secret-shaped
  text the scanner keeps off stderr.
- **D-C.8 — Dropfile evidence never touches the filesystem.** `kind: file`
  rows from a dropfile store sha256 NULL: an untrusted path is never
  opened, unlike CLI `evidence add --kind file` which hashes a file the
  human named. Deliberate asymmetry, journaled here.
- **D-C.9 — Dropfile event grain.** All rows in ONE transaction: per-row
  `(evidence, add)` events, the ladder's `(run, end)` when it fires, the
  open-questions `(handoff, create)`, then one `(system, dropfile_ingest)`
  sealing event carrying {file, sha256, task, agent, outcome, one-lined
  truncated summary, evidence ids, run_ended, open_runs, handoff}. Actor
  for every one of them is `agent:<name>` (the provenance-actor rule
  extended). An empty open-questions list creates no handoff. Ingest is
  allowed on done tasks — evidence-after-close matches `evidence add`.
- **D-C.10 — `evidence git` details.** Repo defaults to the task's project
  repo; `--repo` overrides; projectless without `--repo` refuses. Refs
  starting with '-' refuse before git runs (option-smuggling guard).
  Read-only queries only (`rev-parse --is-inside-work-tree`, `rev-parse
  --verify <ref>^{commit}`, `show -s --format=%s`, `show --stat
  --format=`), list-form args, 5 s timeout, graceful exit 1 on missing
  git/non-repo/unknown commit/timeout. Full sha stored as ref; claim
  defaults to the commit subject; subject/diffstat captured best-effort
  (truncated to 200 chars) into the event payload via the existing
  `add_evidence` path (optional extra_payload). Tests use temp git repos —
  the contract's P3 gate explicitly authorizes this, superseding D-P4.1
  for this command only. `evidence git` is NOT in the central event-sweep
  seal (keeping that test git-independent); its event is proven in its own
  test class.
- **D-C.11 — Agent registry semantics.** Default kind `generic`. Names
  validated against `^[A-Za-z0-9][A-Za-z0-9._-]*$` — the `agent:<name>`
  provenance charset plus a leading alnum so names are safe, stable note
  filenames (no hidden files, no path tricks). Capabilities stored as a
  JSON array in the existing `capabilities_json` column (`[]` when none);
  `agent update --capability` REPLACES the whole list. No `--trust-level`
  and no `--invoke-hint` surface anywhere: trust stays 0 (autonomy is
  earned via the ladder, never set by hand).
- **D-C.12 — Review engine decisions.** The four new sections land AFTER
  `## Recent runs` (the plan's D1 placement — an existing test pins the
  earlier content slices). "Stale in-progress" = `in_progress` AND (no
  open run OR no run started/ended inside the recent window), reasons
  joined. "Memory needing refresh" = LIVE rows (not superseded, not
  retired at the review date) not updated for 30 days — the D-W6.2 quirk
  (superseded rows in "Stale memory") is deliberately preserved there
  under its regression pin and fixed only in the new section. `review
  weekly` = ISO week Mon–Sun containing `--date`, filename `YYYY-Www.md`,
  windows span the week, point-in-time sections as of the week's end.
  `review project` = `Reviews/project-<slug>.md`, every section filtered
  to the project (global-scope memory excluded — not project-tied); takes
  the same optional `--date` as `build` (determinism for tests; the
  contract names `--date` only for weekly, adding it to project is a
  strict superset). All three builds share one engine and the byte-exact
  `## Notes` splice; all are eventless (D-P0.6/D-W6.1 lineage).
- **D-C.13 — Index notes.** Exactly the seven the contract lists (Tasks,
  Decisions, Evidence, Handoffs, Memory, Agents, Reviews) as top-level
  `AOS/<Name>.md` notes — stable wikilink stems, no frontmatter (like
  Home). Projects/Runs have no index (not in the contract's list). The
  Reviews index derives from the `Reviews/` directory listing — reviews
  live on disk, not in the DB — which keeps sync deterministic and
  idempotent for a given workspace state. Memory index shows superseded/
  valid_until as stored facts, never computed liveness (no clock in the
  mirror). Doctor's containment allowlist gains the seven filenames.
- **D-C.14 — Doctor pins moved 12 → 17 (D-W8.1 pattern, both sites).**
  Four new checks (agent rows well-formed · dropfile ingest events carry
  their sha256 · entity-note frontmatter parses · PRAGMA integrity_check)
  plus one WARN-ONLY line (code tasks done without commit evidence) that
  prints `[WARN]` and never affects the exit code. The weekend pin test
  was renamed `..._passes_all_checks` with the move documented inline; no
  assertion was weakened — the all-green requirement now also accepts the
  expected `[WARN]` line, which the Night-1 fixture legitimately triggers
  (its code task closed with note evidence). The frontmatter check covers
  the eight entity folders only (Reviews/Home/CONVENTIONS/index notes have
  no frontmatter by design); non-UTF-8 stays check 5's finding. No
  deliberate-corruption test for integrity_check: flipping page bytes
  deterministically without also breaking `open_db`'s meta read is not
  reliable across SQLite builds — the check's clean pass is pinned and its
  failure path is a one-line comparison. Every other new check has a
  corruption test asserting exactly one failure.
- **D-C.15 — Adversarial review pass (D-P7.3/D-W9.1 practice continued).**
  Seven independent dimension reviewers (hard constraints · P1 lifecycle ·
  P2 dropfile-as-adversary · P3+P4 · P5+P6 · P7+weakened-test scan · deep
  correctness) reviewed the full working diff; every finding was then
  attacked by three separate refutation agents (correctness / reproduce-it
  / spec-reading lenses, majority rules). Result: 3 findings, 3 confirmed
  (each reproduced live by all three verifiers), 0 refuted. Fixed with
  regression tests: (1) `AGENT_NAME_RE` anchored with `$`, which matches
  before a string-final newline — `agent add $'codex\n'` passed validation
  and wrote an unrecoverable `Agents/codex\n.md` mirror note; fixed with
  `\Z` (doctor check 13 shares the regex and is fixed with it), test pins
  the trailing-newline refusal. (2) `_run_git` decoded git output as
  strict UTF-8, so a commit subject re-encoded via i18n.logOutputEncoding
  crashed `evidence git` with exit 2 on a perfectly valid commit; fixed
  with errors='replace' (graceful degradation), test commits a non-ASCII
  subject under latin1 output encoding. (3) a dropfile task id above
  SQLite's INTEGER bound slipped past `_TASK_RE` into an OverflowError
  exit 2 — untrusted input reaching the internal-error path; fixed with a
  range check in the parser ("task id out of range", exit 1), test pins
  it. The same overflow via CLI-typed ids (e.g. `task show T-<25 nines>`)
  predates this build and is recorded as a known limitation, not churned
  here.
- **D-C.16 — Final gate results.** Recorded after the FINAL VERIFICATION
  GATE: suite 162 → 256 (all green; 254 at the P7 gate + 2 new regression
  tests and 1 extended refusal matrix from the adversarial review pass),
  smoke green including the deliberate duplicate
  refusal, repo doctor clean, nothing staged/committed/pushed. Dogfood
  loop closed: evidence attached to T-0003, run R-0002 ended success,
  T-0003 done, sync + doctor clean. Exact outputs live in the FINAL
  REPORT.

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

## U-M1 decisions (migration kit, T-0011)

Contract: `agentic-os-v0.2-u-m1-migration-contract.md`. U-M1 ships the
migration framework and **zero production migrations**. Appended without
rewriting prior entries.

- **D-v0.2.30 — The migration kit ships before the first migration.**
  `agentic_os/migrations.py` lands with `MIGRATIONS = ()` and
  `LATEST_VERSION == 1`, unchanged from `db.SCHEMA_VERSION`. Why: a schema
  change and the machinery to survive it are two different risks, and
  landing them together means the first migration is also the first test of
  every guarantee protecting it. U-M2 (memory v2) is blocked until U-M1
  merges, and adds exactly one step to the registry plus the matching
  `SCHEMA_VERSION` bump.

- **D-v0.2.31 — `LATEST_VERSION` is derived, never re-declared.**
  `LATEST_VERSION = int(db.SCHEMA_VERSION)`. A second literal would let the
  registry and the schema drift apart — a build could then support a version
  it cannot write, or write one it will not migrate. A guard test pins both
  the derivation and today's values (`1`, `()`), so raising either is a
  deliberate, visible act.

- **D-v0.2.32 — The version lives in `meta.schema_version`, and U-M1 did not
  move it.** The task brief called for a `schema_version` *table*; no such
  table exists — the version is one TEXT row in the generic `meta` key/value
  table, written by `ops.initialize()`. Introducing a table would itself be
  a schema change, which is precisely what U-M1 must not do. The brief's
  refusal cases were mapped onto the real storage (contract M1.1). The
  reader fetches ALL matching rows rather than `LIMIT 1`, so a `meta` table
  rebuilt without its primary key cannot smuggle an ambiguous version past
  the check.

- **D-v0.2.33 — Version parsing is canonical-strict.** A value parses only
  if `value == str(int(value))` and is non-negative: `"1"` yes; `"01"`,
  `" 1"`, `"+1"`, `"1.0"`, `"1_0"`, `"0x1"` no. Why: `int()` alone accepts
  the whole second list, which turns a corrupted cell into a plausible
  version and then migrates from the wrong place. Refusing is cheap;
  migrating from a misread version is unrecoverable.

- **D-v0.2.34 — `migrate` reads the ledger itself instead of `db.open_db()`.**
  `open_db` refuses any version != `SCHEMA_VERSION`, so a database *pending
  migration* — by definition at a lower version — cannot be opened through
  it. The version gate is the door migration must walk through. The gate is
  NOT relaxed for anyone else: `db.open_db` is untouched, every normal
  command still refuses exactly as before, and a test pins that. This is the
  mechanism behind "normal commands never auto-migrate": migration lives
  behind one explicit command and nothing else calls it.

- **D-v0.2.35 — `status`/`plan` read through `PRAGMA query_only=ON`, not URI
  `mode=ro`.** Measured, not assumed (contract M1.3): a `mode=ro` open of a
  WAL database creates `-shm`/`-wal` and **cannot remove them on close**,
  leaving lock artifacts behind forever; a plain read-write open checkpoints
  a dirty `-wal` on close, changing `aos.db`'s bytes. A read-write handle
  with `query_only=ON` does neither — SQLite itself rejects writes, reads
  still resolve through the `-wal` (no stale version), close does not
  checkpoint, and a quiescent workspace is left exactly as found.
  `immutable=1` was rejected outright: it would ignore the `-wal` and return
  a stale version — the exact hazard the stale-state rules exist to prevent.
  It remains correct in `backup.py`, where the file genuinely is immutable.

- **D-v0.2.36 — The write lock is held on one connection; the snapshot is
  sourced from a second.** `conn.backup(dest)` **hangs forever** when `conn`
  holds its own open `BEGIN IMMEDIATE`: `backup_step` returns `SQLITE_BUSY`
  against the connection's own write transaction and CPython retries on an
  unbounded sleep loop. So the literal reading of "lock, then snapshot"
  deadlocks. Instead the lock holder stays open while a second reader
  connection sources the snapshot — under WAL a reader is not blocked, and
  because the holder has written nothing it observes exactly the committed
  pre-migration state. This is *stronger* than releasing the lock to
  snapshot and re-taking it: no writer can commit between the snapshot and
  the first step, so the snapshot is provably the pre-migration state.

- **D-v0.2.37 — The pre-migration snapshot emits no `backup_create` event.**
  Emitting one requires a commit, which would release the write lock taken
  moments earlier and reopen the race it exists to close. `backup.py` was
  split instead: `write_backup_pair()` (files + manifest, no event) is the
  eventless half, and `create_backup()` is now that plus the existing event —
  `backup create` behavior is byte-identical to baseline. The snapshot's
  identity is recorded inside the `system/migrate` event, committed
  atomically with the step it protects. This extends U-C2's own rule (a
  backup never contains its own event) rather than contradicting it. A
  migration that fails before any step commits leaves a verified snapshot
  with no event referencing it; that is the safe outcome, and the failure
  message names the file.

- **D-v0.2.38 — `verify_backup` gained `expected_schema_version`.**
  It previously hard-failed unless a backup's version equalled
  `db.SCHEMA_VERSION`. The moment U-M2 ships (`SCHEMA_VERSION = "2"`), a
  *correct* pre-migration snapshot of a v1 database would fail that check
  and `migrate apply` would refuse to proceed — the framework would deadlock
  on the first real migration it was built for. The snapshot is now verified
  against the version it was actually taken at. Default `None` keeps the
  current meaning ("can this build use this backup?") and the current
  diagnostic string exactly, so U-C2 is unchanged. Today `current ==
  SCHEMA_VERSION == "1"`, so this is a no-op in production and is proved by
  direct test — it is not dead code, it is the one line that makes U-M2
  possible.

- **D-v0.2.39 — A no-op apply never opens the database read-write.** With
  nothing pending, `apply` returns after the `query_only` pre-flight. Why:
  "not one byte changed" should be true by construction, not by being
  careful with a handle that could write. A test spies on `db.connect` and
  pins exactly one (read-only) open.

- **D-v0.2.40 — Rollback across committed steps is restore, never
  automatic.** A failed step rolls back completely (its schema change,
  version bump, and event die together) and no later step runs. If an
  earlier step already committed, the database is reported PARTIALLY
  ADVANCED — a real, consistent state — with the exact `backup restore`
  command for the pre-migration snapshot. No automatic destructive rollback
  is attempted: un-applying a committed schema change programmatically is
  guesswork, and doing it automatically would silently bypass the snapshot
  taken to protect the user. A corrected retry resumes from the version
  actually committed and never replays completed steps.

- **D-v0.2.41 — Migration diagnostics print an exception's class, never its
  text.** A step body's `str(exc)` can embed SQL and row values; the
  diagnostic carries only the failed transition, the safe migration id, the
  exception class name, and the snapshot's relative path. Likewise the
  `system/migrate` payload carries exactly `{from, to, migration_id,
  snapshot}` with `snapshot` **relative** to the workspace — never an
  absolute, user-identifying path — and still passes through
  `events.emit`'s `secretscan.redact_tree` choke point (U-C3).

- **D-v0.2.42 — A malformed version is a database value, so it is redacted
  before it is quoted.** Found by a test, not by review: the first draft
  echoed the raw value (`schema_version 'sk-live-…' is not an integer`),
  which would print a secret-shaped cell straight to the terminal. Malformed
  versions now go through `secretscan.redact_tree` and are length-bounded,
  so a corrupted megabyte-long cell cannot become the error message either.

- **D-v0.2.43 — The v1 fixture is a builder, not a committed `.db`.**
  `tests/fixtures/v1_workspace.py` builds a real historical v1 workspace
  through production CLI commands only — never raw INSERTs — so it cannot
  drift from what v1 code actually writes, and it carries representative
  rows in every table (all four task statuses, runs, packs, evidence,
  decisions, handoffs, memory, agents, 20 events). A committed binary would
  be unstable across sqlite versions and page layouts, would bake in
  wall-clock timestamps from `utils.utc_now_iso()`, and would sit in the
  tree as exactly the kind of file the packaging allowlist exists to keep
  out of `aos.pyz`.

- **D-v0.2.44 — Synthetic registries are injectable, and test-only.**
  `plan_migrations`/`apply_migrations` accept `registry` + `latest` so tests
  can prove v1→v2 and multi-step behavior without a production schema
  change. Production callers pass neither, so the empty registry always
  applies; the CLI never threads them through. Synthetic steps must never
  become production migrations — D-v0.2.30's guard test is what enforces it.

- **D-v0.2.45 — The version `UPDATE` asserts it matched exactly one row.**
  An `UPDATE` matching zero rows succeeds silently in SQLite. A step whose
  own body removed or duplicated the `meta.schema_version` row would then
  commit a `system/migrate` event announcing a bump that never happened, and
  the ledger would lie about its own shape — the one thing the version row
  exists to prevent. The step fails and rolls back instead. Unreachable
  today (`read_schema_version` runs immediately before, in the same
  transaction); the assertion is what keeps it unreachable once real
  migrations exist.

- **D-v0.2.46 — One documented deviation from the one-line error rule.**
  `cli.py`'s contract is "errors are ONE actionable line on stderr", and
  every other `AosError` in the tree obeys it — including every other
  migration refusal. The PARTIALLY ADVANCED message is the single exception:
  it carries the state explanation plus a copy-pasteable `backup restore …
  --to …` command. Folding a command the user must run at the worst possible
  moment into a prose line would make the error that most needs clarity the
  hardest to act on. The rule's intent (no tracebacks, no walls of text for
  ordinary failures) holds: the message is bounded, fixed-shape, and carries
  no SQL, row values, or secrets.

- **D-v0.2.51 — The runtime power mode lives in an operational sidecar, not
  the schema or `meta`.** `.agentic-os/power.json` is a small file beside the
  ledger, deliberately outside it. Recovery control must be reachable when the
  database is unopenable, version-mismatched, or corrupt — that is precisely
  when a human reaches for `power set recovery`. Storing the mode in `meta`
  would make the control depend on the very thing it exists to recover:
  `db.open_db` refuses any `schema_version` other than the build's, so a
  version-mismatched database would lock the human out of the escape hatch. No
  `power` command calls `open_db`, no schema version changed, and no migration
  was registered.

- **D-v0.2.52 — A missing `power.json` means `standard`, and reading it never
  creates it.** Absence is a valid, expected state, not an error and not a
  first-run initialization step. `status`, `suggest`, `doctor`, and every other
  read-only command leave the workspace byte-identical; only `power set`
  creates or replaces the file. The alternative — writing a default on first
  read — would make every read-only command a writer, and would silently take
  a position (`configured standard`) the human never took.

- **D-v0.2.53 — Command classification is an explicit allowlist, walked and
  enforced by a test.** Every CLI leaf is classified `read_only`,
  `derived_write`, `recovery_safe`, or `authoritative_write` in one table in
  `power.py`, keyed by its argparse path. Mutability is never inferred from a
  command's name or help prose — `backup create` sounds read-ish and writes an
  event; `review build` sounds derived and is. A test walks the LIVE argparse
  tree and fails on any unclassified leaf and on any stale entry, so a new
  command cannot inherit a permissive default by being forgotten. An
  unclassified path fails closed to `authoritative_write` at runtime.

- **D-v0.2.54 — Suggestions never auto-apply.** `power suggest` prints advice
  and exits; it never writes `power.json`, and no command switches modes on its
  own. The degradation matrix reports `auto-switch: no` for all four modes, by
  construction. A system that quietly downgraded itself into `recovery`, or
  quietly left it, would make the mode a thing that happens to the human rather
  than a thing the human decides — and leaving `recovery` is exactly the
  decision that must not be automatic.

- **D-v0.2.55 — Recovery is fail-closed for authoritative and derived change.**
  Only `read_only` and `recovery_safe` commands run. The refusal fires in
  `power.dispatch` BEFORE `args.func`, so stdout stays empty and no partial
  mutation is possible; it names the command path and the mode, and echoes no
  payload, row, secret, path, or exception text. Entering recovery works while
  doctor has hard failures (and while the database cannot be opened at all);
  leaving it requires every hard check to pass. Warn-only checks never gate a
  transition — a warning is not a reason to trap someone in recovery.

- **D-v0.2.56 — Deep verifies around authoritative writes and never rolls
  back.** Before each authoritative ledger write, a bounded read-only preflight
  runs `PRAGMA integrity_check` and the existing U-C3 secret sweep through the
  same primitives doctor uses; a hard failure refuses the write before anything
  is written. After a successful write the same checks re-run, and on failure
  the command reports — honestly — that it ALREADY COMMITTED and that
  verification failed, recommends recovery, and exits 1. It never claims a
  rollback and never performs one: automatically undoing a committed, journaled
  write is the opposite of what an append-only system of record is for.
  Diagnostics name check names and counts only; `doctor` remains the place that
  shows the (already bounded, already value-free) detail.

- **D-v0.2.57 — No model calls, no host-resource heuristics.** The suggestion
  is a fixed four-step priority over signals the system already computes:
  hard doctor failure → `recovery`; warning → `deep`; active runs → `standard`;
  clean and idle → `eco`. No LLM call, no scoring model, no natural-language
  heuristic over ledger content, no CPU/RAM/battery probing, no environment
  telemetry. Identical ledger state yields an identical suggestion, and the
  output carries a fixed signal phrase plus a bounded count — never a title,
  summary, ref, claim, path, or secret. "Power mode" here means local execution
  policy; it never chooses a model or starts anything.

- **D-v0.2.58 — U-E1 pack effort tiers stay separate and deferred.** Context
  packs keep their own `--for` / `--budget-kb` knobs. Runtime power modes govern
  CLI execution policy for a workspace; pack effort tiers govern what goes into
  one artifact. Fusing the two vocabularies because both say "power" would tie
  an unrelated future decision to this one.

- **D-v0.2.59 — `power set` emits no ledger event.** Every other mutation in
  this tree journals one. This cannot: it must work when the database is
  unopenable, which is exactly when `recovery` is set — emitting an event would
  reintroduce the dependency D-v0.2.51 exists to remove. The cost is real and
  accepted: mode changes have no audit trail. `doctor` and `power status` report
  the CURRENT mode and whether it was configured, so the state is always
  visible even though its history is not.

- **D-v0.2.60 — `backup create` and `snapshot` are blocked in recovery.** Both
  write their file and then emit a ledger audit event inside `db.transaction`,
  so both mutate the live database and fail the "reads without mutating" test
  that would have made them recovery-safe. `backup verify` and `backup restore`
  remain available — they never touch the live ledger, and restore writes a
  distinct NEW path (U-C2). `backup.write_backup_pair()` is eventless but has
  no CLI surface; exposing one to soften this would be scope creep, and the
  honest answer is that a recovery-mode backup is not currently available.

- **D-v0.2.61 — Eco defers exactly one site, and none was invented.** An audit
  of every command path found one piece of implicit, optional derived work in
  the baseline: `init` re-heals the Obsidian mirror on an ALREADY-initialized
  workspace while reporting "nothing to do". Eco defers that and says so;
  `sync` regenerates it. Everything else the mirror/review/pack code does is
  explicitly requested by the human, and a freshly created workspace always
  heals (a new workspace with no mirror is not usable). Inventing automatic
  refresh work purely so eco could visibly differ from standard would have made
  the system do MORE by default in order to advertise doing less.

- **D-v0.2.62 — A malformed power state fails closed for writers and open for
  readers.** A power state that does not parse means the mode is UNKNOWN, and
  an unknown mode could be hiding a configured `recovery` — so
  `authoritative_write` and `derived_write` commands refuse. `read_only` and
  `recovery_safe` commands proceed, because reporting the problem is how the
  human sees it: `doctor` FAILs its power line rather than crashing, and
  `power status` prints it. Nothing repairs the file automatically — silent
  repair would resolve an ambiguity in the writer's favor. The documented way
  out is manual: delete it (absence means `standard`) and re-set the mode.

- **D-v0.2.63 — No lock file; `os.replace` is the serialization point.**
  `power set MODE` is an absolute assignment, not a read-modify-write delta, so
  concurrent setters cannot interleave: each writes a complete, already-valid
  temp file and atomically renames it, and the result is always exactly one
  valid state. A lock file would add its own staleness, its own symlink
  surface, and its own recovery story to protect an operation that is already
  atomic. One bounded consequence is documented rather than papered over: an
  idempotent no-op reports the state it observed, and a concurrent set may land
  after it — the file is still one complete valid state.

## v0.3 — U-X1: WorkSpec and Result Envelope protocol spine

- **D-v0.3.1 — Agentic OS owns the initial protocol registry.** The registry
  ships in this repository, not in AICompany and not in a shared package. AOS is
  the system of record, and the protocol spine is part of that record. Consumers
  vendor it by digest later; nothing in U-X1 reaches across a repository
  boundary. Building the registry where the first consumer happens to live would
  have made the second consumer a fork.

- **D-v0.3.2 — The Python embedded definitions are canonical.** `aos.pyz` is one
  file with no data directory, so a registry that lived in `protocols/*.json`
  would make the zipapp non-functional the moment it left the checkout. The
  embedded definitions in `agentic_os/protocols.py` are the single source of
  truth, and `agentic_os/protocols.py` enters the archive through the existing
  U-P1 allowlist with no packaging change at all — the allowlist design working
  as intended.

- **D-v0.3.3 — Checked-in JSON artifacts are deterministic projections.**
  `protocols/` exists so the schemas are reviewable in a diff and vendorable by a
  future consumer. It is a projection, never a second editable source:
  `protocol verify-registry` and a focused test compare it byte-for-byte against
  the embedded definitions, and `verify_source_artifacts` additionally refuses a
  stray `.json` under `protocols/` that projects no embedded schema. Editing
  `protocols/` without editing the Python fails both.

- **D-v0.3.4 — No general-purpose JSON Schema claim.** The validator supports an
  explicit, small, enumerated subset, and every unsupported keyword is named. The
  registry lint refuses a schema that uses any of them, so the guarantee is
  structural rather than aspirational: the registry cannot drift into relying on
  a keyword the engine silently ignores. A partial implementation that quietly
  skips `oneOf` is worse than no claim at all, because it validates less than a
  reader believes it does.

- **D-v0.3.5 — No floats in protocol v1.** Floating point has no canonical
  decimal form that survives a round trip across languages, so a float field
  would make the content hash unstable by construction. Numbers are integers in
  the IEEE-754 safe range (±(2⁵³−1)) — the range that survives a consumer whose
  JSON parser has no integer type. Durations, budgets and sizes are integers in
  explicit units.

- **D-v0.3.6 — The content hash excludes exactly its own field.** The digest is
  computed over the canonical serialization of the document with the *top-level*
  `content_sha256` member removed and nothing else removed. A `content_sha256`
  nested inside a sub-object is ordinary body content and stays in. No recursive
  self-hashing, no placeholder value, no ordering dependence: what gets hashed
  never contains the hash.

- **D-v0.3.7 — Protocol validation is inert and read-only.** Validation parses
  bytes and compares them to a schema. It never executes, imports, evals,
  resolves, fetches, opens or stats anything an artifact *references*. A `sha256`
  inside a WorkSpec is a declared reference, and the validator does not go hash
  the file it names — hashing a path an untrusted artifact chose is a read
  primitive handed to the artifact's author. All five leaves are `read_only` and
  open no SQLite connection.

- **D-v0.3.8 — AICompany vendoring and cross-repository replay are deferred.** A
  Result Envelope is a report produced by a party whose claims are not yet
  trusted, not an instruction. Nothing in U-X1 marks a task done, ends a run,
  creates evidence or authorizes spend. Import and replay are a later bounded
  unit, and the honest place to draw that line is before the ledger, not inside
  it.

- **D-v0.3.9 — v1 reserves no extension object.** The unit's brief permitted one
  bounded extension object; v1 declines it. Every schema rejects unknown
  top-level fields with no exceptions. An extension object would be an
  unvalidated pocket inside a signed body — the one region of the document where
  "we bound everything" stops being true. Forward compatibility is bought by
  minting `/v2`, which the registry is already built to carry.

- **D-v0.3.10 — Existing vocabularies are reused exactly, or not at all.** The
  Result Envelope `outcome` enum IS `models.RUN_OUTCOMES` and evidence `kind` IS
  `models.EVIDENCE_KINDS` — asserted by test against the production tuples rather
  than copied, so the two cannot drift apart silently. Protocol-only concepts
  (data classification, permitted destinations, compensation state) get new
  closed vocabularies. No existing domain vocabulary is broadened.

- **D-v0.3.11 — Key ordering is by Unicode code point, and that is stated rather
  than dressed up as RFC 8785.** RFC 8785 sorts by UTF-16 code unit; the two
  orders differ for non-BMP keys. AOS sorts by code point because that is what
  Python's native string comparison already does, and hand-rolling a UTF-16
  re-implementation would be a correctness risk taken purely to earn a compliance
  badge this unit does not claim. The format is named `aos-canonical-json/v1`,
  and all four known divergences from RFC 8785 are written down.

- **D-v0.3.12 — Generation lives in `tools/`, never in the CLI.** The CLI is
  read-only by classification, so it cannot regenerate `protocols/`.
  `tools/gen_protocols.py` writes the projection (and verifies it by default,
  writing only with `--write`), mirroring the existing `tools/build_zipapp.py`
  convention. It is excluded from the zipapp for free, because `tools/` is not
  under the package allowlist.

- **D-v0.3.13 — Schema patterns anchor with `^…$` and are applied with
  `fullmatch`: a deliberate, narrow departure from D-v0.2.3.** The existing rule
  ("anchor with `\Z`, never `$`") exists because Python's `$` also matches
  *before* a trailing newline, so `^slug$` would accept `"proj\n"`. That hole is
  closed here by a different mechanism: `re.fullmatch` requires the pattern to
  consume the whole string, so `fullmatch(r"^abc$", "abc\n")` fails — `$` consumes
  nothing and the `\n` is left over. The reason to prefer `$` is that these
  patterns are *exported* in `protocols/*.schema.json` for future consumers, and
  `\Z` is not ECMA-262: a JavaScript-side validator would read it as a literal
  `Z` and silently enforce the wrong grammar. `^…$` means exactly fullmatch in
  ECMA-262. So: `$` in the artifact, `fullmatch` in the engine, D-v0.2.3's
  guarantee intact, and a focused test pinning the trailing-newline refusal.

- **D-v0.3.14 — The protocol id grammar is a strict narrowing of the ledger's
  parser, not a copy of it.** `ids.parse_id()` is deliberately lenient at the CLI
  boundary: it upper-cases the prefix and strips surrounding whitespace, so
  `t-0002`, `T-0002 ` and `\tT-0002\n` all mean task 2 to a human typing at a
  terminal. The protocol accepts only `T-0002`. Leniency is right for a human
  boundary and wrong for a wire format, where two spellings of one id are two
  idempotency keys, two correlation targets and two audit trails. Narrowing stays
  compatible (every id the protocol accepts, `parse_id` accepts identically);
  broadening would not have.

- **D-v0.3.15 — U-M2 is key/value claim storage, not a graph.** `kind` stays
  the closed claim type, `key` the stable claim key/subject, `value_md` the
  human-readable claim value. The temptation at a "typed memory" unit is to
  generalize into subject/predicate/object and call it future-proofing; that
  would rewrite every reader (packs, search, mirror, doctor) and every v1 row's
  meaning in the same breath as the first production migration. Two risky
  changes at once is how a migration eats a ledger. Graph relationships are
  U-M3, on top of a claim table that already carries curation, integrity and
  evidence.

- **D-v0.3.16 — Schema version 2 is the first production U-M1 migration, and
  U-M2 adds no migration machinery.** The registry stayed empty at U-M1 exactly
  so this step could be the first thing it carried. U-M2 supplies a
  `Migration.apply` callable and nothing else: validation, the write lock, the
  version re-read under it, the snapshot, its verification as v1, the version
  bump and the `system/migrate` event are all U-M1's, untouched. A schema change
  that brings its own safety net is a schema change whose safety net has never
  been tested.

- **D-v0.3.17 — Legacy curation is derived from what v1 already knew, never
  inferred from text.** A superseded row → `retired`; an expired row →
  `retired`; everything else → `live`; everything unpinned; no evidence links
  invented. The expiry test is the *existing* live predicate verbatim, so a row
  v1 already kept out of packs is exactly a row v2 calls retired — the
  migration changes what the ledger can express, not what it says. Guessing
  `proposed` or `contested` from a claim's wording would be inventing curation
  history no human performed.

- **D-v0.3.18 — Pinned never overrides lifecycle or safety; it is a sort key.**
  A pinned claim must still be live, unexpired and unsuperseded to be
  retrieved, and `pin` refuses anything that is not. The alternative — pin as
  "always include" — makes pinning a second, competing lifecycle that quietly
  outranks retirement, which is precisely the bug where an agent keeps being
  told a thing the human retired six months ago.

- **D-v0.3.19 — Evidence uses normalized links, not copied evidence text.**
  `memory_evidence` is two ids and a timestamp. Copying an evidence claim or
  ref into the link would duplicate content that can be edited on one side and
  not the other, and would put evidence text — the thing U-C3 works to keep out
  of derived surfaces — into a second table with its own privacy story. Links
  are also why the claim hash binds evidence by *id*: the claim commits to
  which evidence backs it, not to a snapshot of what that evidence said.

  One consequence, accepted deliberately: the pre-existing `memory/add` event
  keeps its `key` field. The blanket "events carry no key" rule is right for
  every event U-M2 adds (`pin`, `unpin`, `link_evidence` carry ids,
  transitions, counts and a hash prefix — nothing else), but removing `key`
  from `add` would break the U-C3 warn-on-write behavior this unit is required
  to preserve. That field is already governed: `events.emit` redacts every
  secret-shaped string through `secretscan.redact_tree`, and the U-C3 metadata
  records what was withheld.

- **D-v0.3.20 — Claim hashes reuse U-X1 canonicalization, with every stored
  text field bound as a SHA-256 digest rather than as raw text.** The structure
  is canonical JSON v1 (`protocols.serialize_canonical`); U-M2 defines no
  competing canonicalization. But the leaves are digests, for two measured
  reasons. First, U-X1 caps a canonical string at `MAX_STRING_CHARS` (8192) and
  `memory add --value` has never had a length limit — a real 20 KB pasted claim
  would be *refused by its own migration*, breaking the one guarantee the
  legacy mapping must keep. Relaxing the protocol bound to fit a database row
  would be modifying the protocol spine to suit its first consumer. Second, a
  damaged row must stay reportable: with digest leaves, no stored value of any
  length or shape can trip a bound, so `doctor` prints one bounded line instead
  of dying inside the serializer that was supposed to help it. `sha256(text)`
  binds the text exactly; the binding is Merkle-shaped, not weaker.

  The payload also binds `id` (so a valid hash cannot be transplanted onto
  another row) and `updated_at` (every write that touches it recomputes the
  hash anyway). Only `content_sha256` itself is excluded — what gets hashed
  never contains the hash (D-v0.3.6).

- **D-v0.3.21 — Normal retrieval includes live claims only; hashes are
  enforced at write time and audited by doctor, not re-verified on read.**
  Packs filter on lifecycle (`status='live'`, unexpired, unsuperseded) with
  plain SQL. Verifying hashes on the read path sounds stricter but buys a worse
  system: it either drops a claim silently (context vanishes with no
  explanation — the worst outcome available) or refuses the whole pack, letting
  one damaged row block every pack in the workspace. Instead, *every*
  authoritative write against an existing claim verifies the stored hash first
  and refuses on mismatch — so a tampered claim can never be laundered into a
  valid-looking one by a later pin or retire — and doctor reports the damage by
  id. Integrity is enforced where it can be acted on.

- **D-v0.3.22 — Status is curation; expiry is time. They are independent
  axes.** A live claim crosses its own `valid_until` with no write at all, and
  `--valid-until` accepts a past date, so "expired but not retired" is honestly
  reachable and doctor reports it as a WARNING, never a failure. A check that
  turns red because a day passed is a broken check. The same reasoning makes
  "pinned but ineligible" (pin, then retire) a warning: reachable, harmless,
  and worth saying out loud.

- **D-v0.3.23 — The 1 → 2 step rebuilds the memory table instead of
  `ALTER TABLE ADD COLUMN`.** `ADD COLUMN` cannot add `content_sha256 TEXT NOT
  NULL` without a non-NULL default, and a `DEFAULT ''` would leave every future
  insert able to store a hashless claim: a migrated database would be
  permanently weaker than a freshly initialized one, and the difference would
  be invisible until it mattered. A rebuild from the one shared DDL constant
  (`db.MEMORY_CLAIM_DDL`) makes a migrated table identical to a born-v2 table,
  and routes every mapped row through the new CHECK constraints — so the
  migration cannot commit a value the schema forbids.

- **D-v0.3.24 — U-M3 (graph) and U-M4 (curation workflow) remain deferred.**
  U-M2 ships the storage those units need — `proposed`/`contested`/
  `quarantined` are storable, evidence links are normalized, every claim is
  hashed — and none of their behavior: no approve, reject, contest, quarantine,
  automatic promotion, contradiction detection, distillation, or agent memory
  writer. Storage that anticipates a workflow is cheap; a workflow invented
  ahead of its unit is a design nobody reviewed.

## U-M3 — provenance, temporal, relationship and contradiction memory graph

Contract: `agentic-os-v0.3-u-m3-memory-graph-contract.md`. Schema version 3.

- **D-v0.3.31 — Sensitivity is a closed, ORDERED vocabulary:
  `public < internal < confidential < restricted`.** The order is not
  cosmetic; it is what "classification increases only" and "a source must not
  be more sensitive than the claim it backs" are expressed in. Both a CHECK
  constraint and the domain enum enforce membership, so neither a careless
  caller nor a direct SQL writer can invent a level.

- **D-v0.3.32 — Sensitivity defaults to `internal`, and `restricted` is the
  only level excluded from automatic context.** `public` is a deliberate act
  of publication, not something a claim falls into by omission. Public,
  internal and confidential claims keep exactly the pack, search and mirror
  behavior they had; restricted claims never enter a context pack, a search
  snippet, a generated summary or a mirror body. Administrative surfaces still
  LIST them — metadata only, never their key, value, source or evidence refs.
  This is a safe local baseline, not the U-S6 authorization system.

- **D-v0.3.33 — The exclusion lives in the eligibility predicate, not in the
  renderers.** `ops.claim_is_eligible` and `ops.memory_for_project` both learned
  about `restricted`, so `memory show`'s "retrieved: yes", the pin gate and the
  pack builder cannot disagree about who sees what. A filter added at the pack
  renderer would hold only for that renderer, and the next caller would
  reopen the hole without noticing. Pinning still never overrides sensitivity:
  it is ordering among eligible claims, and it always was.

- **D-v0.3.34 — A source row copies no text from what it references.** An
  `evidence` source carries an evidence id and nothing else about that row —
  not its claim, ref, sha or body. Every other kind carries an inert `locator`.
  A structural CHECK enforces the split at the storage boundary as well as in
  `ops`, so a row that copied a ref into `locator` cannot exist.

- **D-v0.3.35 — Contradictions are typed edges, not a second table and not a
  verdict.** A contradiction IS an active `contradicts` edge. There is no
  resolution column, no winner, and no truth decision anywhere in U-M3:
  `memory contradictions` reports that a human declared two claims to
  disagree, shows both claims' lifecycle and sensitivity, and stops. Nothing
  is ever inferred — not from keys, values, dates, sources or models. A tool
  that guessed here would be believed.

- **D-v0.3.36 — Graph relations are descriptive and trigger no workflow.**
  Adding a `contradicts` edge does not quarantine, retire, contest or reorder
  anything. `memory.superseded_by` remains the one lifecycle supersession
  mechanism and is deliberately NOT duplicated as a graph relation — two
  mechanisms for one truth is how a ledger starts disagreeing with itself.

- **D-v0.3.37 — Symmetric relations canonicalize their endpoints (lower id
  first).** `contradicts` and `related` are symmetric, so A↔B and B↔A are one
  logical edge; the endpoints are ordered before every lookup and insert, and
  a CHECK pins the canonical form in storage. A reverse duplicate therefore
  collides with the UNIQUE constraint instead of quietly becoming a second row
  for the same fact.

- **D-v0.3.38 — Every graph reference is inert.** No command follows a file
  locator, resolves a URL, executes a command string, reads an evidence ref,
  or opens an artifact path. They are strings the ledger agreed to remember.
  This is what keeps the graph inspection commands genuinely read-only rather
  than read-mostly.

- **D-v0.3.39 — SQLite graph records are canonical; graph engines are
  derived.** The three tables are ledger data with integrity hashes, not a
  disposable visual index. Any external graph engine, visualization or index
  is rebuildable from them and carries no truth of its own.

- **D-v0.3.40 — Traversal caps truncate deterministically and say so.**
  `memory graph` is bounded at depth 2, 64 nodes and 128 edges. It truncates
  rather than refusing — an inspector that gives up on a large graph is
  useless exactly when it matters — and reports `truncated`, because a silent
  stop reads as "that is the whole neighbourhood".

- **D-v0.3.41 — A shipped migration is history and gets frozen in place.**
  U-M2 wrote the 1→2 step against the shared `db.MEMORY_CLAIM_DDL` so a
  migrated table could not drift from a fresh one. That was right while v2 was
  current and stopped being right the moment v3 existed: a shared constant
  follows the schema FORWARD, so 1→2 would have built a v3-shaped table,
  stamped `schema_version = 2` on it, and hashed its claims under the v3
  payload — and U-M1's guarantee that a failure inside 2→3 leaves a valid v2
  database would have been false, because there would never have been one. The
  v2 DDL and the v2 claim-hash payload are now frozen copies in
  `migrations.py`. The cost is one duplication per schema version; each step
  now leaves a database that genuinely is what it says it is.

- **D-v0.3.42 — The 2→3 step rebuilds the memory table, and the migration
  connection runs with `foreign_keys=OFF` plus a `foreign_key_check` before
  every commit.** The rebuild is D-v0.3.23's reasoning applied again: building
  from the one fresh-v3 DDL constant is what makes a migrated table and a
  born-v3 table the same table. But `memory_evidence` now holds foreign keys
  into `memory`, so DROPping the old table is an instant violation.
  `PRAGMA foreign_keys=OFF` inside a transaction is a silent no-op, and
  `PRAGMA defer_foreign_keys=ON` looks like the subtler answer and is not one
  — it counts the violations the DROP causes and never decrements them when
  the RENAME puts the table back, so the COMMIT fails anyway (measured, not
  assumed). So the pragma is set before the transaction opens, and the
  compensating control is strictly broader than what was switched off: EVERY
  step, present and future, is followed by a `foreign_key_check` over the whole
  database inside its own transaction, before its commit. Per-statement
  enforcement would have refused the legal intermediate state; this refuses any
  illegal final one.

- **D-v0.3.43 — No provenance is invented during migration.** The three graph
  tables come out of 2→3 EMPTY, and every migrated claim becomes `internal` by
  constant, never by inspecting its text. A v2 claim has no recorded
  provenance; deriving one from `memory.source` or from linked evidence would
  put a guess into the ledger wearing the same clothes as a fact. Existing
  evidence links survive untouched — the step does not address that table at
  all.

- **D-v0.3.44 — Doctor's restricted-in-context check warns, never fails.** A
  pack built BEFORE a claim was classified restricted legitimately contains
  it: the operator did nothing wrong and no invariant was violated at the
  time. It is still a real leak on disk worth surfacing, and `pack build` /
  `sync` regenerate it away. Same rule as D-v0.3.22 — a check that turns red
  because history happened is a broken check.

- **D-v0.3.45 — No explicit indexes are added.** This schema has never carried
  a `CREATE INDEX`; every hot column is scanned. The graph tables follow that
  established design rather than introducing a new one: the UNIQUE constraints
  already provide the implicit indexes the traversal's outbound lookups use,
  the caps bound every traversal, and a personal ledger lacks the row count
  that would make this matter. Fewer objects also means fewer things the
  migration must replicate exactly — fresh/upgrade identity is preserved by
  construction rather than by vigilance.

- **D-v0.3.46 — Classification increases only; downgrades and authorization
  policy belong to U-S6.** `memory classify` raises a claim's sensitivity,
  treats same-state as a no-op that writes nothing and emits no event, and
  REFUSES to lower one. Reducing the protection on a claim is an authorization
  decision, and U-M3 ships no authorization system to answer it with.

- **D-v0.3.47 — U-M4 (workflow), U-M5 (retrieval evaluation) and U-M6
  (receipts) remain deferred.** U-M3 ships the graph those units need and none
  of their behavior: no proposal/approve/reject/contest, no automatic
  contradiction detection, no automatic source extraction, no interviews, no
  embeddings or vector retrieval, no graph ranking, no Context Hydration
  Receipts, and no agent-written memory. Packs do no graph expansion at all.
  Storage that anticipates a workflow is cheap; a workflow invented ahead of
  its unit is a design nobody reviewed.
