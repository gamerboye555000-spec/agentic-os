# Contributing to Agentic OS

This is the contribution flow for the Agentic OS repository under the U-P2
delivery gate: one frozen CI workflow, four public checks, and the
solo-maintainer honest-authority trust boundary stated first because every
other rule reads differently without it. "Protected delivery" throughout
this document means exactly **ordinary failure enforcement and
accidental-change governance** — nothing stronger.

## Delivery-control trust boundary

Agentic OS operates under the **solo-maintainer honest-authority boundary**
(trust-boundary amendment, D-v0.4.45). Read these six facts together; any
stronger reading is wrong:

1. **The delivery controls are repository-hosted and self-modifiable.** The
   workflow, its canonical verifier, and the verifier's tests are stored in
   this repository — `.github/workflows/ci.yml`,
   `tools/verify_ci_workflow.py`, and `tests/test_v04_delivery_gate.py` —
   so a repository writer can modify all three together in one pull request.
2. **What they protect is honest development**: ordinary failure enforcement
   (a real failing check blocks a merge), deterministic delivery, and
   detection of accidental or isolated drift — an edit to one control file
   alone is caught by the other two.
3. **They are not an external or independently administered security
   authority.** Every enforcing byte is part of the pull-request head being
   evaluated.
4. **A required check name by itself does not prove that the check's
   semantics are unchanged.** Names are identities; the conclusions reported
   under them are computed by head-controlled code.
5. **Changes to the delivery-control files require exceptional manual
   review** — the exact requirements are in "Delivery-control changes"
   below.
6. **Future independent authority is deferred and trigger-gated.**
   Adversarial tamper resistance becomes its own governed unit when a
   trigger is met: a second trusted reviewer plus CODEOWNERS and required
   review; an organization/enterprise required workflow outside the
   modifiable PR head; or a separately administered GitHub App or external
   status provider. Nothing from those triggers is partially implemented
   today.

## Repository workflow

- **Contract first.** Every unit of work freezes its contract — scope, file
  boundary, decisions — before implementation, in its own worktree; the
  implementation then has no degrees of freedom the contract did not pin.
  Frozen contracts are history: later amendments supersede them, and the
  original files are never rewritten.
- **One unit, one branch.** Branches are named `v<version>-u-<unit>-<slug>`
  (this unit: `v0.4-u-p2-delivery-gate`). Milestones are annotated
  `milestone/<branch-name>` tags created on the merge commit after
  post-merge verification.
- **No direct pushes to `main`.** Changes reach `main` through a pull
  request. When the planned ruleset is active this is enforced by GitHub;
  it is the project rule either way.
- **Store prompt and task packs outside the repository**, in a
  maintainer-selected external directory. A prompt or task pack copied into
  the worktree is a stop condition.
- **Generated data never enters Git.** `.agentic-os/` workspaces, `dist/`,
  `*.pyz`, `build/`, `*.egg-info/`, exports, backups, and ledger databases
  stay out of the tree; the build residue the wheel build may create is
  gitignored and bounded (see TROUBLESHOOTING.md, "Clean-tree failures").

## Before opening a pull request

Run the focused U-P2 validation set, exactly:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v04_delivery_gate
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v02_packaging
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_v03_protocol_spine
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -v tests.test_cli
python3 tools/verify_ci_workflow.py
git diff --check
git status --porcelain --untracked-files=all
```

The hosted workflow is broader than this list: `tests-python-3.12` and
`tests-python-3.14` run **full unittest discovery**
(`python3 -m unittest discover -s tests`) on Python 3.12 and Python 3.14,
after compiling every source tree and before verifying the protocol
projection and asserting a clean working tree. The commands above are the
focused U-P2 validation set — fast, and centered on the delivery gate
itself. Run the full local gate (README, "Protected delivery (CI)") before
opening the pull request, and see TROUBLESHOOTING.md ("Protected delivery
gate (U-P2)") when a check fails.

## Pull-request expectations

- The pull request targets `main`.
- The branch must be current with `main` when the ruleset is active
  ("require branch up to date before merging").
- All four checks must pass when they are configured as required checks:
  `workflow-integrity`, `tests-python-3.12`, `tests-python-3.14`, and
  `distribution-smoke-python-3.12`.
- Unresolved review conversations must be resolved when that setting is
  active.
- The merge method is a normal merge commit under the frozen plan — no
  squash merges, no rebase merges.
- Zero required approvals is intentional for the current solo-maintainer
  topology: there is one active maintainer, and a pull-request author
  cannot approve their own pull request, so a required approval would
  deadlock every PR against a reviewer who does not exist.
- Zero approvals is not equivalent to independent review. Nothing about the
  topology creates a second reviewer.

Do not treat any of these repository settings as active on the basis of
this document alone: ruleset state is live GitHub configuration, verified
during the later live-acceptance phase, never a property of repository
files.

After a merge, the expectation is **tree parity**: a merge commit with no
concurrent mainline motion must leave `origin/main^{tree}` equal to the
feature head's tree. Post-merge verification, the milestone tag, and
worktree/branch cleanup all run from the primary `main` worktree, never
from the feature worktree.

## Delivery-control changes

The three delivery-control files are:

```text
.github/workflows/ci.yml
tools/verify_ci_workflow.py
tests/test_v04_delivery_gate.py
```

A change touching any of them requires all of the following:

- an **explicit rationale** — what changes, and why the gate is better for
  it;
- a **byte-exact canonical verifier update** whenever workflow bytes
  change: the frozen representation embedded in
  `tools/verify_ci_workflow.py` must be regenerated to match the new
  `ci.yml` byte-for-byte, in the same change;
- **direct mutation-test updates** in `tests/test_v04_delivery_gate.py`
  covering the new shape — never deletions that hollow out the coverage;
- a **focused audit** of the changed files;
- **exceptional manual review** — these files are the gate, so routine
  review is not enough, and a green run is not a substitute: both sides of
  the check are repository-controlled;
- **no semantic reliance on a stable check name**: keeping a name is
  identity continuity, not evidence that the check still means the same
  thing;
- **no `pull_request_target` improvisation**, in any form — the trigger is
  banned outright and the verifier refuses it;
- **no action-pin, permission, trigger, runner, timeout, check-name, or
  build-pin change** without a separately governed amendment.

## Commit and sequencing model

U-P2 itself landed under a frozen five-commit sequence — recorded here as
historical and project-governance context, one commit per wave:

```text
docs: freeze U-P2 protected delivery contract
docs: adopt U-P2 solo-maintainer trust boundary
ci: add immutable read-only validation workflow
test: verify U-P2 workflow and distribution gates
docs: document protected Agentic OS contribution flow
```

The word "immutable" in the Wave 1 subject is historical commit text: it
described the read-only, SHA-pinned shape of that workflow when the commit
was written, and it does not override the later trust-boundary amendment —
the delivery controls are repository-hosted and self-modifiable, exactly as
stated at the top of this document.

## Merge and bootstrap

The documented order of the remaining U-P2 delivery steps:

1. The documentation commit lands before any live repository-setting
   activation.
2. After the branch content is pushed, live acceptance verifies that all
   four checks run — and conclude GREEN — on the exact pushed head.
3. Ruleset activation (the planned `main-delivery-gate` ruleset requiring
   the four checks on `main`) and the failing-test probe are later,
   separately controlled steps. The workflow must exist on `main` first,
   because rules can only require checks that exist.
4. The probe — a disposable pull request carrying one deliberately failing
   test — demonstrates **ordinary failure blocking only**: FAILED required
   checks on the exact probe head, a blocked merge, and a close without
   merging.
5. It does not prove semantic immutability or administrator resistance —
   see the trust boundary at the top of this document.

Whether the ruleset or the probe has actually run is live GitHub state;
confirm it there, never from this file.
