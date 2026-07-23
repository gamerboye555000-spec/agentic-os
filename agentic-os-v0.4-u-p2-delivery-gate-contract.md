# Agentic OS v0.4 — U-P2 continuous integration and protected delivery gate contract

Unit: U-P2 — Continuous Integration and Protected Delivery Gate
Branch: `v0.4-u-p2-delivery-gate`
Worktree: `/home/daksh/Projects/agentic-os-u-p2`
Baseline: `ef66fd4297491a5856b6d2602da8e3994e5359bd` (= `origin/main`)
Milestone baseline: `milestone/v0.4-u-a3-routing-handoffs`
Contract frozen: 2026-07-22 (all mutable facts resolved from primary sources
on this date; none frozen from memory)
Decisions: D-v0.4.33 … D-v0.4.44

U-P2 changes how repository changes are validated and merged. It must not
change what Agentic OS does at runtime. This contract pins every degree of
freedom **before** any workflow implementation. A conflict between an
implementation and this contract is a defect in the implementation.

---

## 1. Verified baseline identity (Wave 0 preflight, 2026-07-22)

| Fact | Value | Evidence |
|---|---|---|
| Branch | `v0.4-u-p2-delivery-gate` | `git branch --show-current` |
| HEAD | `ef66fd4297491a5856b6d2602da8e3994e5359bd` | `git rev-parse HEAD` |
| `origin/main` | same SHA | `git rev-parse origin/main` |
| Worktree | clean, no staged/unstaged/untracked | `git status --short --branch` |
| Schema version | `"5"` | `agentic_os/db.py:20` |
| Doctor checks | 41 | live `init` + `doctor` in a disposable scratch workspace; 41 lines, all PASS, exit 0 |
| Test count | 2,275 | `unittest` loader `countTestCases()` over `tests/` (discovery only; suite not run in Wave 0) |
| Protocol registry | 4 schemas, artifacts byte-identical | `aos protocol verify-registry`, exit 0 |
| Projection verifier | verify-only default, exit 1 on drift | `python3 tools/gen_protocols.py --help` |
| Remote | `https://github.com/gamerboye555000-spec/agentic-os.git` | `git remote -v` |
| Repository visibility | public, owner type User | `GET /repos/...` API |
| Merge methods enabled | merge, squash, rebase; `delete_branch_on_merge: false` | `GET /repos/...` API |

Tracked `*prompt*.md` files at the repository root are historical v0.1 build
documents committed at baseline; they are not U-P2 task packs and are not the
"prompt pack in worktree" stop condition.

## 2. Delivery-state inventory (state vocabulary: ABSENT / RUNNING / FAILED / GREEN)

All three gates are **ABSENT**, confirmed against the live API on 2026-07-22 —
not merely unobserved:

- Workflows: `GET /repos/gamerboye555000-spec/agentic-os/actions/workflows` →
  `{"total_count":0,"workflows":[]}`; no `.github/` directory exists in the tree.
- Rulesets: `GET /repos/.../rulesets` → `[]`.
- Branch protection: `GET /repos/.../branches/main/protection` →
  HTTP 404 "Branch not protected".

Reports in this unit must never conflate ABSENT with GREEN.

## 3. U-P1 deferral provenance

`agentic-os-v0.2-u-p1-packaging-contract.md` §1 (Scope), verbatim:

> Out of scope (explicitly not done in this pass): **CI, release publishing,
> branch protection**, Docker, migrations, third-party runtime libraries,
> global installation, commits/pushes/tags, and any change to ledger
> semantics.

U-P2 closes exactly the first three deferred items minus release publishing,
which stays excluded (§17). U-P1 remains historically correct and is not
rewritten (D-v0.4.33).

## 4. Dependency reconciliation (why U-P2 precedes U-K1/U-T1/U-W1/U-A4)

- `agentic_os/protocols.py:1005` — passport skill/tool requirement strings:
  "U-A1 ships no resolver (deferred to U-K1/U-T1)". The resolvers do not exist.
- WorkSpec (`beast.work-spec/v1`) is an inert declaration: schema validation
  only, no permission grant, no execution (`agentic_os/protocols.py:830`).
- Therefore U-W1 requires U-K1 and U-T1; U-A4 requires U-W1. U-P2 has no
  feature dependency and closes the proven delivery gap first. Order after
  U-P2: U-K1/U-T1 (either order) → U-W1 → U-A4.

---

## 5. Frozen public check identities (D-v0.4.34)

```text
workflow-integrity
tests-python-3.12
tests-python-3.14
distribution-smoke-python-3.12
```

- These four strings are the **job `name:` values** and therefore the check
  names branch rules require. Once the ruleset depends on them, renaming any
  of them is a governed migration (ruleset + workflow + verifier + docs in one
  reviewed change), never a drive-by edit.
- GitHub job **ids** cannot contain `.` (ids allow only alphanumerics, `-`,
  `_`). Frozen job ids, mapped 1:1 to the names above:
  `workflow-integrity`, `tests-python-3-12`, `tests-python-3-14`,
  `distribution-smoke-python-3-12`. The public identity is the `name:`; the id
  is internal. The verifier checks both.
- No job matrix: a matrix would render names like `tests (3.12)` and surrender
  control of the frozen identities. Four independent explicit jobs.
- No `needs:` edges: all four jobs run on every trigger and report
  independently; merge requires all four GREEN regardless.

## 6. Frozen workflow shape

One workflow file: `.github/workflows/ci.yml`, workflow `name: ci`.

### 6.1 Triggers

```yaml
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
  workflow_dispatch:
```

`pull_request_target` is forbidden in any form, including in future edits —
enforced by the verifier (reason `pull_request_target`).

### 6.2 Global constraints

- Top-level `permissions:` block exactly:

  ```yaml
  permissions:
    contents: read
  ```

  No job-level `permissions:` blocks at all (an elevation and a redundant
  read-only block are both shape violations).
- Runner: `runs-on: ubuntu-24.04` on every job — the explicit immutable
  label, never the mutable `ubuntu-latest` alias (D-v0.4.39).
- Top-level `env: PYTHONDONTWRITEBYTECODE: "1"`.
- `defaults: run: shell: bash` (GitHub runs bash with `-e -o pipefail`);
  multi-line run steps begin with `set -euo pipefail`.
- Checkout always sets `persist-credentials: false`.
- Forbidden everywhere: secret contexts (`secrets.`), artifact upload/download
  actions, `continue-on-error`, `curl`/`wget` (no shell downloads), `sudo`,
  repository writes, branch/tag commands, caching, containers, services.
- Timeout on every job (§6.3). Concurrency policy (§6.4).

### 6.3 Timeout policy (D-v0.4.42)

```text
workflow-integrity              timeout-minutes: 10
tests-python-3.12               timeout-minutes: 30
tests-python-3.14               timeout-minutes: 30
distribution-smoke-python-3.12  timeout-minutes: 30
```

Basis, recorded with the evidence that exists:

```text
Known local final U-A3 full-suite runtime:
2,275 tests in 763.307 seconds (~12.72 minutes)
```

This is local hardware evidence, not GitHub-hosted-runner evidence. The
30-minute test-job timeout is approximately 2.35 times that local runtime;
the 10-minute integrity timeout remains separate. No hosted-runner CI duration
exists yet (no prior workflow ever ran), so the ceilings are deliberately
generous bounds against runaway jobs, not performance targets: the first live
U-P2 runs must record the actual hosted durations, any timeout change requires
a governed amendment, and a timeout must never be increased merely to hide a
hang. Tightening later from observed data is a normal governed change; raising
a ceiling is a red flag requiring investigation first.

### 6.4 Concurrency policy (D-v0.4.42)

```yaml
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' }}
```

PR runs for the same PR may be canceled when superseded. `main` runs use
`cancel-in-progress: false` (the expression evaluates to `false` for `push`
and `workflow_dispatch`). This does **not** guarantee a completed run for
every mainline commit: GitHub may still cancel an older *pending* run in the
same concurrency group when a newer `main` run is queued, and only the newest
queued `main` run is guaranteed to complete — so an intermediate main commit
may lack a completed run. A missing historical run can be re-created with
`workflow_dispatch` against the relevant commit or ref where GitHub permits.
U-P2 does not claim immutable CI evidence for every `main` commit, and never
claims queue preservation GitHub does not provide.

## 7. Frozen immutable action allowlist (D-v0.4.36)

Every `uses:` reference must be a repository on this closed allowlist pinned
to the exact full 40-hex commit SHA below. Release names may appear in
trailing comments only. `@main`, `@master`, `@vN`, and release-tag references
are forbidden in the executable field (verifier reasons `mutable_action_ref`,
`unapproved_action`).

| Action | Frozen release | Full commit SHA (executable pin) |
|---|---|---|
| `actions/checkout` | v7.0.1 (published 2026-07-20T15:10:05Z) | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `actions/setup-python` | v7.0.0 (published 2026-07-20T03:15:01Z) | `5fda3b95a4ea91299a34e894583c3862153e4b97` |

Canonical `uses:` lines:

```yaml
uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1        # v7.0.1
uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97    # v7.0.0
```

Provenance (retrieved 2026-07-22, two independent primary-source signals per
pin, both in agreement):

- `actions/checkout` v7.0.1: (a) `git ls-remote
  https://github.com/actions/checkout.git refs/tags/v7.0.1` →
  `3d3c42e5…` (lightweight tag → commit); (b) GitHub REST
  `git/ref/tags/v7.0.1` → `{"type":"commit","sha":"3d3c42e5…"}`;
  release identity from `releases/latest`. The `v7` major line's headline
  change is *blocking fork-PR checkout under `pull_request_target` /
  `workflow_run`* (actions/checkout#2454) — a hardening irrelevant here
  because `pull_request_target` is banned outright.
- `actions/setup-python` v7.0.0: (a) `git ls-remote … refs/tags/v7.0.0` →
  `5fda3b95…`; (b) REST `git/ref/tags/v7.0.0` → same commit; release
  identity from `releases/latest`.

Re-verification duty: Wave 1 re-resolves both tag→SHA mappings before writing
`ci.yml`; a mismatch with this table is a stop condition (possible tag
retarget), not a silent update.

## 8. Frozen interpreter matrix (D-v0.4.37)

- **Floor: Python 3.12** — `pyproject.toml` `requires-python = ">=3.12"`;
  currently in *security* status upstream. The floor is a repository
  compatibility promise and does not move in U-P2.
- **Current stable feature line: Python 3.14** — resolved 2026-07-22 from two
  official sources in agreement: python.org/downloads (latest stable release
  3.14.6, 2026-06-10; "3.14 bugfix" is the current stable branch) and
  devguide.python.org/versions (3.14 status `bugfix`, first release
  2025-10-07; 3.15 is `prerelease`, due 2026-10-01).
- `setup-python` inputs are the feature-line strings `"3.12"` and `"3.14"`
  (latest available patch of each line); every job prints the exact resolved
  patch (`python3 -VV`) so the runtime is recorded per run, per the plan:
  lines are frozen, patches are logged.
- Python 3.15 adoption (after its stable release) is a future governed change
  to workflow + verifier + ruleset + docs; nothing in U-P2 anticipates it.

## 9. Frozen CI-only build-tool policy (D-v0.4.38)

Runtime dependencies remain `[]` — U-P2 adds none. The distribution-smoke job
(only) installs exact-pinned build-time tools:

```bash
python3 -m pip install pip==26.1.2
python3 -m pip install build==1.5.0 setuptools==83.0.0 packaging==26.2 pyproject_hooks==1.2.0
python3 -m pip freeze   # logged: the complete resolved tool environment
```

| Tool | Frozen version | Primary-source signals (2026-07-22, in agreement) |
|---|---|---|
| pip | 26.1.2 | PyPI JSON `info.version`; pypa/pip newest tag `26.1.2` |
| build | **1.5.0** | PyPI JSON `info.version` 1.5.0; pypa/build GitHub release 1.5.1 (2026-07-09) exists but **is yanked on PyPI** — 1.5.0 is the newest non-yanked release; pinning a yanked release is forbidden |
| setuptools | 83.0.0 | PyPI JSON; pypa/setuptools tag `v83.0.0`; satisfies the build-backend floor `setuptools>=68` |
| packaging | 26.2 | PyPI JSON; pypa/packaging tag `26.2` (dependency of `build`) |
| pyproject_hooks | 1.2.0 | PyPI JSON; pypa/pyproject-hooks tag `v1.2.0` (dependency of `build`) |

- **Build isolation is disabled**: `python -m build --wheel --no-isolation`.
  The backend (`setuptools==83.0.0`) is exact-pinned in the environment, so
  the build is deterministic; isolation would re-resolve the backend from the
  network at build time, which is exactly the drift this unit exists to
  prevent.
- The `wheel` package is **deliberately not installed**: setuptools ≥ 70.1
  provides native `bdist_wheel`. (Resolved-for-the-record current version:
  wheel 0.47.0.) If Wave 1's smoke disproves this, adding `wheel==0.47.0` is
  a recorded contract amendment, not a silent install.
- No hash-pinning (`--require-hashes`) in U-P2: version pins are the frozen
  policy per plan; artifact-hash pinning is explicitly deferred to a future
  supply-chain unit.
- All transitive content is logged via `pip freeze`; an unexpected package in
  that log is investigated, not ignored.

## 10. Frozen job specifications

### 10.1 `workflow-integrity` (job id `workflow-integrity`)

1. checkout (pinned, `persist-credentials: false`);
2. setup-python (pinned, `python-version: "3.12"`);
3. `python3 -VV && python3 -m pip --version && uname -a`;
4. `python3 tools/verify_ci_workflow.py` — exit 0 required.

### 10.2 `tests-python-3.12` (job id `tests-python-3-12`) and `tests-python-3.14` (job id `tests-python-3-14`)

Identical steps; only the `python-version` input differs (`"3.12"` / `"3.14"`):

1. checkout (pinned, `persist-credentials: false`);
2. setup-python (pinned);
3. `python3 -VV && python3 -m pip --version && uname -a`;
4. compile: `python3 -m compileall -q agentic_os tests tools aos.py aos_hooks.py`;
5. full suite: `python3 -m unittest discover -s tests`;
6. protocol projection: `python3 tools/gen_protocols.py` (verify-only default;
   exit 1 on drift);
7. clean tree: `git diff --exit-code` and
   `test -z "$(git status --porcelain)"` (no modifications, no untracked
   debris — `PYTHONDONTWRITEBYTECODE=1` is global, so no bytecode appears).

The compile set is deliberately broader than the historical local gate
(adds `tools` and `aos_hooks.py`); this exact command becomes the documented
local-equivalent command in Wave 3 so CI and docs never diverge.

A 3.14 failure is not skippable: it is either a bounded runtime-neutral
correction (its own governed decision) or a separately planned blocker — the
job is never weakened to pass (per plan §10).

### 10.3 `distribution-smoke-python-3.12` (job id `distribution-smoke-python-3-12`)

The wheel and zipapp final artifacts and the disposable smoke workspaces live
under `$RUNNER_TEMP` (outside the checkout); smoke commands run from outside
the repository with `PYTHONPATH` unset. One caveat is explicit: `python3 -m
build --wheel --no-isolation` may create `build/` and `agentic_os.egg-info/`
**inside the checkout**. Those are build intermediates, gitignored at baseline
(`build/`, `*.egg-info/`), and are never permitted wheel members except the
built wheel's legitimate `.dist-info` metadata. Because ignored residue is
invisible to `git status --porcelain`, cleanliness cannot rely on porcelain
alone: the job checks those exact known paths, removes exactly them in a
bounded cleanup step (never `git clean`), and re-checks that they are absent;
source files must remain byte-identical.

1. checkout (pinned, `persist-credentials: false`);
2. setup-python (pinned, `"3.12"`);
3. print versions (as above);
4. install pinned build tools; `pip freeze` (§9);
5. wheel build: `python3 -m build --wheel --no-isolation --outdir "$RUNNER_TEMP/dist"`;
6. wheel membership assertion (§11.1);
7. venv install + console-script smoke: `python3 -m venv "$RUNNER_TEMP/venv"`;
   `pip install --no-deps "$RUNNER_TEMP"/dist/agentic_os-*.whl`; then, from
   `$RUNNER_TEMP`: `aos --help`; `mkdir -p "$RUNNER_TEMP/ws-wheel"` (explicit
   `--root` requires an existing directory); `aos --root
   "$RUNNER_TEMP/ws-wheel" init`, `status`, `doctor`; `aos protocol
   verify-registry` — all exit 0;
8. zipapp build: `python3 tools/build_zipapp.py --output "$RUNNER_TEMP/aos.pyz"`;
9. zipapp membership assertion (§11.2);
10. zipapp smoke from `$RUNNER_TEMP`: `python3 aos.pyz --help`;
    `mkdir -p "$RUNNER_TEMP/ws-zipapp"` (explicit `--root` requires an
    existing directory); `--root "$RUNNER_TEMP/ws-zipapp" init`, `status`,
    `doctor`; `protocol verify-registry` — all exit 0;
11. entrypoint equivalence: `--help` stdout byte-identical across console
    script, `python3 -m agentic_os`, and the zipapp (guaranteed by the pinned
    `prog="aos"`, D-U-P1-01/02 — asserted, not assumed);
12. build-intermediate cleanup (bounded, never `git clean`): assert the only
    ignored residue present is the known set `build/` and
    `agentic_os.egg-info/`, remove exactly those two paths, then assert both
    are absent — the known paths are checked before and after cleanup, and any
    unexpected ignored residue fails the job;
13. clean tree: `git diff --exit-code` (tracked source byte-identical) and
    `test -z "$(git status --porcelain)"`.

The `mkdir -p` before each `init` is deliberate: `aos --root <dir>` requires
an existing directory, so creating the workspace root explicitly makes the
smoke prove that precondition rather than weakening it.

Known, unchanged limitation: `hooks install`/`status`/`uninstall` are
unsupported from the zipapp (D-U-P1-11); the smoke does not exercise them.

## 11. Frozen package-membership law

### 11.1 Wheel

Every archive member path must match one of:

- `agentic_os/**/*.py`
- `agentic_os/catalog/manifest.json`
- `agentic_os/catalog/<agent>.v<n>.passport.json` (the 12 checked-in passports)
- `agentic_os-*.dist-info/**` (metadata)

and the catalog JSON set must byte-match the source tree's
`agentic_os/catalog/*.json` (13 files at baseline).

### 11.2 Zipapp

Every archive member path must match one of:

- top-level `__main__.py` (byte-identical to `agentic_os/__main__.py`,
  D-U-P1-02)
- `agentic_os/**/*.py`
- `agentic_os/catalog/manifest.json` and the passport files (individually
  validated by the builder, never a broad sweep — D-v0.4.14)

### 11.3 Universal prohibitions (both artifacts)

No member may match: `tests/`, `.git*`, `.agentic-os`, `__pycache__`, `*.pyc`,
`*.db`, `*.sqlite*`, backup/export/vault/credential/cache content,
`aos_hooks.py`, repository metadata, prompt packs, or any repository `*.md`
(dist-info metadata excepted). The check asserts membership against the
allowlists above — a new unexpected name fails closed.

## 12. Frozen workflow-integrity verifier (D-v0.4.41)

File: `tools/verify_ci_workflow.py`. Standard library only; it opens no
sockets, spawns no subprocess, and mutates nothing; total on malformed bytes
(a hostile or corrupt file
yields findings, never a traceback). It enforces the one frozen canonical
workflow contract by **canonical byte-grammar recognition**: it is not a
general YAML parser or a general Actions linter, and it does not search for
banned substrings — it affirmatively recognizes the full frozen workflow
shape, accepting `.github/workflows/ci.yml` only when every byte and construct
belongs to the single frozen canonical grammar, and failing closed with
`unexpected_workflow_shape` on any unrecognized construct (§12.4).

### 12.1 Interface

```bash
python3 tools/verify_ci_workflow.py
python3 tools/verify_ci_workflow.py --workflow .github/workflows/ci.yml
```

- Default target: `.github/workflows/ci.yml` relative to the repository root.
- Exit 0 **only** with zero findings; exit 1 with findings (one per line on
  stdout); exit 2 for usage errors.
- Diagnostics are **value-free and bounded**: each line is a reason code from
  the closed vocabulary, optionally followed by a locus drawn from a closed
  set (a frozen job id, a frozen trigger name, or `line:<n>`). No arbitrary
  workflow content is ever echoed.
- Ordering is deterministic: findings sorted by (reason code, locus).

### 12.2 Closed reason vocabulary (frozen; 20 codes)

```text
missing_workflow
invalid_utf8
crlf_present
mutable_action_ref
unapproved_action
credential_persistence
write_permission
pull_request_target
secret_reference
continue_on_error
missing_timeout
missing_required_job
missing_required_trigger
missing_python_line
missing_full_suite
missing_distribution_smoke
artifact_upload
shell_download
unexpected_workflow_shape
internal_error
```

`unexpected_workflow_shape` is the closed catch-all for canonical-shape
violations that have no dedicated code (e.g. wrong runner label, missing
concurrency block, a job-level `permissions:` block that is not a write
grant, a job matrix). `internal_error` is the twentieth code and is not a
workflow-shape verdict — it is the verifier's own fail-closed guard (§12.5).
New reason codes require a governed vocabulary change.

### 12.3 Enforced checks

All external `uses:` refs are full 40-hex SHAs on the §7 allowlist; every
checkout sets `persist-credentials: false`; top-level permissions are exactly
`contents: read` and no job-level permissions exist; no `pull_request_target`;
no `secrets.` expression; no write permission anywhere; no
`continue-on-error`; every job has `timeout-minutes`; all four frozen job
ids/names exist; all three frozen triggers exist; both Python feature lines
(`3.12`, `3.14`) exist; the full-suite command exists in both test jobs; the
distribution-smoke commands exist; no artifact upload/download action; no
`curl`/`wget`; file is UTF-8 with LF line endings only.

### 12.4 Canonical byte-grammar (frozen)

Acceptance is affirmative recognition of one deterministic representation, not
the absence of banned substrings. The frozen representation is: UTF-8; LF line
endings only; no BOM; exact key ordering wherever the verifier depends on
ordering; the exact frozen job ids and `name:` values (§5); the exact allowed
steps and command blocks (§10); and the exact action allowlist with full SHAs
(§7). Every construct below is non-canonical and refused — as
`unexpected_workflow_shape` unless a more specific §12.2 code applies:

```text
anchors
aliases
custom tags
duplicate keys
document start/end markers
multiple YAML documents
flow-style mappings or sequences
quoted or escaped mapping keys
alternate boolean spellings
job-level permissions
local actions
reusable workflows
multiline/folded `uses:`
unexpected block scalars
unknown jobs, steps, keys, or ordering
shell indirection that replaces frozen commands
```

Because the whole shape must be recognized, a construct the grammar does not
name cannot pass as "merely not banned"; it is unrecognized, and unrecognized
fails closed.

### 12.5 Internal failure behavior (`internal_error`)

A top-level exception guard wraps the entire run. Any unexpected internal
failure yields exactly one finding, `internal_error`, and exits 1 — one fixed,
value-free diagnostic, with no traceback, no exception message, and no file
content echoed. It participates in the same deterministic `(reason, locus)`
ordering as every other finding. The verifier therefore stays total: an
internal crash can neither be mistaken for a pass nor be turned into an output
channel.

## 13. Frozen test plan

New focused module: `tests/test_v04_delivery_gate.py` (Wave 1). Minimum
mutation coverage — every §12.2 reason proven reachable, plus: canonical
workflow passes; deterministic multi-finding ordering; diagnostics proven
value-free (a poisoned workflow's arbitrary strings never appear in output);
verifier is non-mutating (byte-identical input file after run); each of the
26 mutation cases from the plan §16 list; and a mutation test for every
non-canonical construct class in §12.4 (anchors, aliases, custom tags,
duplicate keys, document markers, multi-document streams, flow-style
collections, quoted or escaped keys, alternate boolean spellings, job-level
permissions, local actions, reusable workflows, multiline/folded `uses:`,
unexpected block scalars, unknown jobs/steps/keys/ordering, and shell
indirection replacing a frozen command), each proven to fail closed, plus the
`internal_error` guard proven to exit 1 value-free.

Focused existing suites (module names confirmed against the live tree):
`tests.test_v02_packaging`, `tests.test_v03_protocol_spine`, `tests.test_cli`,
plus new `tests.test_v04_delivery_gate`.

Final local gate (Wave 4, and documented in Wave 3):

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q agentic_os tests tools aos.py aos_hooks.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
python3 tools/gen_protocols.py
python3 tools/verify_ci_workflow.py
git diff --check
git status --short --branch
```

plus wheel/install/console-script and zipapp smoke in disposable directories.

Pyright: baseline captured before Wave 1 edits; zero unexplained new
production diagnostics; test-file diagnostics reported separately; global
config never changed to hide findings.

## 14. Frozen file boundary (D-v0.4.44)

```text
Wave 0:  agentic-os-v0.4-u-p2-delivery-gate-contract.md   new       (this file)
         DECISIONS.md                                     modified  (U-P2 section only)
Wave 1:  .github/workflows/ci.yml                         new
         tools/verify_ci_workflow.py                      new
         tests/test_v04_delivery_gate.py                  new
Wave 2:  refinements strictly within the three Wave 1 files
Wave 3:  README.md                                        modified
         CONTRIBUTING.md                                  new       (confirmed absent at baseline)
         TROUBLESHOOTING.md                               modified
```

Nothing else. In particular `agentic_os/**`, `aos.py`, `aos_hooks.py`,
`pyproject.toml`, `protocols/**`, `tools/gen_protocols.py`,
`tools/build_zipapp.py`, `tools/gen_catalog.py`,
`tools/gen_retrieval_benchmarks.py`, schema/migration code, and every
existing test module are untouchable. A production module entering the diff
is a stop condition; a pre-existing supported-entrypoint defect exposed by CI
becomes a separate maintenance unit, never a fix-forward inside U-P2.

## 15. Frozen documentation obligations (Wave 3)

- **README.md**: supported Python lines (3.12 floor, 3.14 stable); the exact
  local-equivalent commands from §13; check-state vocabulary
  (ABSENT / RUNNING / FAILED / GREEN) and what each means for trust; pointer
  to CONTRIBUTING.md; explicit statement that no release publishing exists.
- **CONTRIBUTING.md** (new): contract-first worktree flow; focused tests per
  wave; the full local gate; the four required remote checks by exact name;
  no direct pushes to `main`; prompt packs live outside the repository
  (`/home/daksh/Projects/agentic-os-designs/prompts/`); generated-data
  exclusions; branch/tag naming conventions; merge-tree parity expectation;
  post-merge cleanup from the primary `main` worktree.
- **TROUBLESHOOTING.md**: entries for — no checks appeared; immutable action
  pin invalid; Python-line compatibility failure; distribution smoke fails
  while unit tests pass; branch-rule/check-name mismatch; GitHub or network
  outage (infrastructure failure ≠ code failure; never weaken the gate);
  local pass vs. remote fail; checkout modified by generated files; ABSENT
  checks vs. GREEN checks.
- Every documented command is verified verbatim against the actual CLI and
  workflow before commit. Docs document only behavior the workflow proves.

## 16. Frozen branch ruleset (operator action, post-merge) (D-v0.4.43)

Repository ruleset, created manually after the U-P2 merge:

```text
Name:            main-delivery-gate
Target:          default branch (main)
Enforcement:     Active
Bypass list:     empty (the administrator is subject to the rules)
Rules:
  - Restrict deletions
  - Block force pushes
  - Require a pull request before merging
      required approvals: 0        (single active maintainer; no unavailable
                                    external approval requirement)
      require conversation resolution: enabled
      allowed merge methods: merge commit only
  - Require status checks to pass before merging
      required checks (exactly, from the GitHub Actions source):
        workflow-integrity
        tests-python-3.12
        tests-python-3.14
        distribution-smoke-python-3.12
      require branch up to date before merging: enabled
Not enabled:     linear history, signed commits, deployments, code scanning
No auto-merge.
```

Availability basis (2026-07-22): repository is public; GitHub Free provides
the full feature set on public repositories (paid tiers extend these features
to private repositories), and the live rulesets endpoint answered normally
for this repository. Regardless, configuration is never trusted on faith:
Proof C (§17) is the enforcement evidence. If the ruleset cannot be created
or does not block the probe, that is a stop condition — protection is never
weakened, and "workflow exists" is never reported as "protected".

Lockout note: with an empty bypass list the administrator's escape hatch is
editing the ruleset itself (settings access is outside ruleset scope); this
is accepted and documented rather than pre-weakened.

## 17. Frozen bootstrap and enforcement-proof procedure (D-v0.4.43)

Bootstrap order (workflow must exist on `main` before rules can require its
checks):

1. add workflow on the U-P2 branch;
2. open the U-P2 PR;
3. observe all four checks run on the exact pushed head (Proof A);
4. all four GREEN required before merge;
5. merge U-P2 (normal merge commit);
6. configure the `main` ruleset per §16;
7. open the disposable failing probe PR;
8. prove merge is blocked (Proof C);
9. close the probe unmerged; delete the probe branch;
10. record evidence.

Failing probe (Proof B + C), frozen:

- Branch: `probe/u-p2-required-check`, from post-merge `main`.
- Change: one new file `tests/test_probe_delivery_gate.py` containing a
  single deliberately failing test (`self.fail(...)`); no other change. This
  turns both `tests-python-3.12` and `tests-python-3.14` red — a real
  failure-sensitivity proof, not YAML inspection.
- Commit message: `probe: deliberately failing delivery-gate probe (do not merge)`.
- PR title: `probe(v0.4): U-P2 failing required-check probe — do not merge`.
- Evidence: checks observed FAILED on the exact probe head; merge blocked
  (API `mergeable_state: blocked` plus the UI state); PR closed **unmerged**;
  branch deleted; all recorded in the final report.
- The probe file never touches `main`; protection is never disabled or
  weakened to complete any proof.

## 18. Frozen delivery metadata (D-v0.4.44)

```text
Commit sequence (one per wave, conventional):
  docs: freeze U-P2 protected delivery contract
  ci: add immutable read-only validation workflow
  test: verify U-P2 workflow and distribution gates
  docs: document protected Agentic OS contribution flow

PR title:     ci(v0.4): U-P2 — add protected deterministic delivery gates
Merge mode:   normal merge commit (repository convention, API-confirmed enabled)
Milestone:    milestone/v0.4-u-p2-delivery-gate  (annotated tag, created on
              the merge commit after post-merge verification; never renamed
              after push)
```

There are 19 existing `milestone/*` tags at the Wave 0 baseline: 13 annotated
and 6 lightweight. U-P2 deliberately uses an annotated milestone tag,
following the newer annotated convention; historical tags are not rewritten.

Post-merge verification (from the primary `main` worktree
`/home/daksh/Projects/agentic-os`, never the feature worktree):

- fetch; confirm `origin/main` is the merge commit;
- tree equality: `git rev-parse origin/main^{tree}` equals
  `git rev-parse <feature-head>^{tree}` (byte-identical content — a merge
  commit with no concurrent mainline motion must not change the tree);
- final full suite + doctor on merged `main` (2,275 tests, 41 checks, schema
  5 — counts unchanged by U-P2);
- ruleset activation (§16), probe (§17), tag, then worktree/branch cleanup;
- network steps are retry-explicit and never mutate first; an outage stops
  cleanly, it never downgrades a gate.

## 19. Security model (frozen)

This is least-privilege, not isolation, stated precisely. No repository
secrets are exposed to jobs; the workflow receives a read-only `GITHUB_TOKEN`
(`contents: read`); `persist-credentials: false` on every checkout keeps that
token out of on-disk Git configuration; the token is not explicitly passed to
test shell steps; the pinned actions may internally receive the read-only
token where they require it. No artifact-upload action is configured. But
GitHub-hosted runners retain outbound network access and U-P2 provides no
egress sandbox, so the `curl`/`wget` ban is canonical workflow-shape hygiene,
not a network isolation control — untrusted PR code can transmit anything it
can read from the runner. Beyond least privilege the gate provides: immutable
action code (full-SHA pins on a two-entry allowlist), exact-pinned build
tools, bounded runtimes, and a mandatory clean-tree assertion. The
workflow-integrity job plus the verifier's mutation tests make
gate-weakening edits (`pull_request_target`, secret use, permission
elevation, test removal, pin loosening) fail the gate itself. Threats §12 of
the plan map onto: immutable pins (tag retargeting), `persist-credentials:
false` (credential persistence), read-only token + no `pull_request_target`
(write-token exposure), pinned tools + `--no-isolation` (build drift), no
upload + `$RUNNER_TEMP` roots + membership law (artifact leakage), timeouts
(unbounded runtime), no `continue-on-error` (hidden failure), frozen names +
verifier + probe (check-name drift and workflow edits), clean-tree assertion
(unnoticed generated files).

## 20. Stop conditions (frozen)

Stop — do not fix forward; re-plan — when any of: baseline or remote differs
from §1; tree dirty at a wave boundary; U-P2 task pack appears inside the
worktree; an action pin cannot be re-verified from primary sources or
mismatches §7; the stable Python line becomes ambiguous; the workflow would
need a secret or write permission; smoke requires a runtime change; a
production module enters the diff; a schema/migration change appears; the
test count drops unexplained below 2,275; remote check names differ from §5;
the ruleset cannot require the checks; the failing probe can merge; the
verifier echoes workflow values; build output enters Git; an audit modifies
the tree.

## 21. Explicitly out of scope (unchanged from plan)

Runtime/CLI behavior, schema/migrations, doctor count, protocols, U-K1, U-T1,
U-W1, U-A4, CodeQL/Dependabot, release publishing (no PyPI, no GitHub
Release, no signing, no SBOM, no containers), coverage thresholds, caching,
artifact upload/retention, scheduled workflows, external services, secrets,
auto-merge/auto-tag/auto-delete, and any historical U-P1 rewrite.

## 22. Decision index

D-v0.4.33 U-P2 unit identity — closes U-P1's explicitly deferred gate
D-v0.4.34 stable public check identities (four frozen names; id/name split)
D-v0.4.35 least-privilege workflow law (read-only, secretless, credential-free)
D-v0.4.36 immutable two-entry action allowlist with frozen full-SHA pins
D-v0.4.37 interpreter matrix: 3.12 floor + 3.14 stable line, patches logged
D-v0.4.38 exact-pinned CI-only build tools; isolation disabled; yanked build 1.5.1 rejected
D-v0.4.39 runner pinned to explicit ubuntu-24.04 label
D-v0.4.40 no artifact upload; disposable $RUNNER_TEMP roots; clean-tree assertion
D-v0.4.41 stdlib workflow-integrity verifier: canonical byte-grammar, closed 20-reason vocabulary
D-v0.4.42 timeout ceilings and ref-scoped concurrency with PR-only cancellation
D-v0.4.43 bootstrap sequence, main-delivery-gate ruleset, failing-probe proof
D-v0.4.44 delivery metadata and exact file boundary

## 23. Residual ambiguities carried into implementation

1. **Ruleset enforceability on this free-plan public repository** is
  supported by documentation and a live API read, but only Proof C
  demonstrates it. If enforcement fails, U-P2 stops at §16 with the workflow
  merged but the unit incomplete — never reported as protected.
2. **actions/checkout v7 / setup-python v7 are 2 days old** at freeze time.
  SHA-pinning removes the supply-chain concern; a functional regression
  discovered in Wave 1 forces a governed re-pin decision (documented SHA
  change), not an ad-hoc downgrade.
3. **Timeout ceilings rest on local, not hosted-runner, evidence** — the known
  local U-A3 full-suite runtime (§6.3) — until the first live runs provide
  hosted data (§6.3 records the tightening path).
4. **The `wheel`-omission claim** (setuptools-native `bdist_wheel`) is proven
  or disproven by the first Wave 1 smoke run; the amendment path is §9.
