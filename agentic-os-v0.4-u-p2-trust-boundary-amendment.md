# Agentic OS v0.4 — U-P2 trust-boundary amendment (Wave 0.5)

Unit: U-P2 — Continuous Integration and Protected Delivery Gate
Wave: 0.5 — trust-boundary replan (Wave 1 implementation untouched)
Branch: `v0.4-u-p2-delivery-gate`
Worktree: `/home/daksh/Projects/agentic-os-u-p2`
Amends: `agentic-os-v0.4-u-p2-delivery-gate-contract.md` (frozen 2026-07-22,
decisions D-v0.4.33 … D-v0.4.44)
Amendment baseline: `184ec247067c7d05c0eb3d56916450cff66218f9` — the commit
that froze the Wave 0 contract (= `origin/v0.4-u-p2-delivery-gate`)
Amendment frozen: 2026-07-22
Decisions: D-v0.4.45 … D-v0.4.50
Provenance: independent Wave 1 audit of the delivery-gate implementation;
finding accepted in full

This is a governed amendment, not a rewrite. It supersedes **only** the
conflicting security and enforcement claims enumerated in §3. Every other
clause of the original contract remains in force verbatim, and the original
contract file is not edited, deleted, or reworded — it stays byte-identical
history, under the same immutability rule U-P2 applied to U-P1's contract
(D-v0.4.33). Where this amendment and the original contract conflict, this
amendment is authoritative.

---

## 1. The audit finding this amendment resolves

The workflow (`.github/workflows/ci.yml`), the canonical verifier
(`tools/verify_ci_workflow.py`), and the verifier's tests
(`tests/test_v04_delivery_gate.py`) are all sourced from — and therefore all
modifiable on — the pull-request head that the four required checks
evaluate.

A repository writer can modify all three together in one pull request,
preserve the four public check names, and produce four green checks whose
semantics they chose themselves. Nothing inside the repository can prevent
this, because every enforcing byte is itself part of the modifiable head:
the verifier that guards the workflow can be edited in the same commit as
the workflow, and the tests that guard the verifier can be edited in the
same commit as the verifier.

The Wave 1 implementation is strong against accidental drift and honest
maintenance errors: an isolated edit to any one of the three files is caught
by the other two, and an ordinary failing test blocks the merge. What it is
not — and cannot be, from inside the head — is independent adversarial
tamper resistance. The original contract claimed more than this in §19, §16,
§17 and D-v0.4.43; those claims are corrected below. The implementation
itself is not discarded, weakened, or modified by this amendment: the checks
were right, the claim was wrong.

## 2. Adopted trust boundary (D-v0.4.45)

U-P2 v0.4 adopts the **solo-maintainer honest-authority boundary**.

This is a deliberate, explicit reduction of the security claim — not a
weakening of the implemented checks. Every check, pin, permission, timeout,
membership law, and assertion from the original contract continues to run
exactly as specified.

U-P2 v0.4 guarantees:

- exact, deterministic CI execution for the checked-in workflow;
- least-privilege GitHub Actions permissions;
- immutable action pins;
- full test and distribution-smoke checks;
- detection of accidental or isolated workflow drift;
- required checks that block ordinary failures;
- a reproducible and auditable delivery process for an honest maintainer.

U-P2 v0.4 does not guarantee:

- tamper resistance against a repository writer who co-edits the workflow,
  verifier, and tests;
- semantic immutability of a required check merely because its public name
  is unchanged;
- protection against a repository administrator who edits or bypasses
  rules;
- an external or base-controlled authority;
- independent approval by a second human;
- organization/enterprise required workflows;
- a trusted GitHub App or external status provider.

The actors inside the trusted zone are exactly: authorized repository
writers acting on delivery-control files, and repository administrators
acting on rulesets and settings. The enforced zone is everything the checks
can witness about an honest change: test failures, workflow and tooling
drift, environment motion, artifact contents, runtime bounds.

## 3. Exact supersession scope

### 3.1 Superseded claims

1. Contract §19, the sentence: "The workflow-integrity job plus the
   verifier's mutation tests make gate-weakening edits
   (`pull_request_target`, secret use, permission elevation, test removal,
   pin loosening) fail the gate itself." Superseded by §4: such edits fail
   the gate when they occur in isolation; a simultaneous, self-consistent
   edit of workflow, verifier, and tests passes by construction.
2. Contract §19, the threat-map entry "frozen names + verifier + probe
   (check-name drift and workflow edits)". Superseded by §4 and §7: that
   mapping holds for accidental or isolated drift only; it is not a defense
   against a co-editing writer.
3. Contract §16/§17 and D-v0.4.43, wherever ruleset plus probe are
   characterized as enforcement evidence without qualification — including
   "configuration is never trusted on faith: the only accepted enforcement
   evidence is the probe". Superseded by §5 and §6: the ruleset is ordinary
   failure enforcement and accidental-change governance, and the probe
   evidences exactly that, nothing stronger.
4. Any reading of D-v0.4.34 (frozen public check identities) or D-v0.4.41
   (workflow-integrity verifier) under which a stable check name or a green
   `workflow-integrity` check attests unchanged check semantics. Superseded
   by §4 and §7: names are identities; conclusions are computed by
   head-controlled code.

### 3.2 Explicitly not superseded

Everything else in the original contract remains in force, including: the
four frozen check identities and the id/name split (§5); the frozen
workflow shape, triggers, permissions law, timeout and concurrency policy
(§6); the action allowlist and full-SHA pins (§7); the interpreter matrix
(§8); the build-tool policy (§9); the job specifications (§10); the
package-membership law (§11); the verifier mechanics, closed vocabulary,
and value-free diagnostics (§12); the test plan (§13); the file boundary
(§14); the Wave 3 documentation obligations (§15, extended by §10 below);
the ruleset shape including zero required approvals (§16); the bootstrap
order and probe procedure (§17); delivery metadata (§18); the
least-privilege-not-isolation statement and the accidental-drift threat
mappings (§19); stop conditions (§20); the out-of-scope list (§21). The §16
lockout note — the administrator is subject to the rules and the accepted
escape hatch is editing the ruleset itself — was already honest and stands.
§2's rule that ABSENT is never reported as GREEN stands everywhere.

## 4. Corrected security model (D-v0.4.46)

The enforceable statements, replacing the §19 overclaim:

- **Isolated or accidental drift is detected.** An edit to `ci.yml` alone
  fails the unmodified verifier; a verifier edit alone fails its unmodified
  tests; a removed or failing test fails the suite. This is real protection
  against the failure modes an honest maintainer actually produces: typos,
  drive-by edits, tool drift, forgotten pins.
- **Simultaneous workflow/verifier/test modification can self-consistently
  pass.** A writer who edits all three in one head controls every
  conclusion the required checks report. No arrangement of files inside the
  head can prevent this.
- **Public check names are identities, not semantic attestations.** A check
  name identifies which conclusion a rule waits for. It proves nothing
  about the meaning of the computation that produced the conclusion.
- **Branch rules enforce conclusions reported under those names.** The
  ruleset requires four names to conclude success on the latest head; it
  cannot see, and does not constrain, what computed those conclusions.
- **The current unit trusts authorized maintainers not to maliciously
  neuter the checks.** That trust is the boundary. In the current topology
  the writer set is exactly the solo maintainer.
- **Repository administrators can alter or bypass rules and remain outside
  this threat boundary.** Ruleset editing is settings access, outside
  ruleset scope; this was documented at freeze time and remains accepted.

## 5. Corrected ruleset model (D-v0.4.47)

The planned `main-delivery-gate` ruleset is kept exactly as frozen in
contract §16:

- pull request required;
- four required status checks (`workflow-integrity`, `tests-python-3.12`,
  `tests-python-3.14`, `distribution-smoke-python-3.12`);
- branch up to date before merging;
- force-push and deletion restrictions;
- conversation resolution required;
- normal merge commits only;
- zero required approvals in the solo topology.

Its correct classification is:

```text
ordinary failure enforcement and accidental-change governance
```

not independent tamper resistance. The ruleset makes an honest maintainer's
failing change unmergeable and makes process shortcuts — direct push, force
push, branch deletion, stale head, unresolved review threads — impossible
in ordinary operation. It does not constrain what a co-editing writer's
checks mean (§4), and it binds no one with settings access (§4). Where
contract §16 says "workflow exists" is never reported as "protected", the
word *protected* now means exactly this classification and nothing
stronger.

## 6. Corrected probe model (D-v0.4.49)

The frozen U-P2 acceptance probe (contract §17) proves:

- a real failing test creates failed required checks on the exact probe
  head;
- the merge is blocked while those checks fail;
- the probe closes without merging.

It does not prove:

- that same-name check semantics are immutable;
- that a co-edited workflow cannot report green;
- that an administrator cannot bypass or change the ruleset.

D-v0.4.43's sentence "the only accepted enforcement evidence is the probe"
is qualified accordingly: the probe is the only accepted evidence of
*ordinary failure enforcement* — it witnesses that the ruleset blocks a red
head — and it is evidence of nothing beyond that. No malicious or
same-name-neutering probe PR is created or merged during Wave 0.5 or any
later wave: §7 analyzes that case on paper, because rehearsing it live
against the real repository would demonstrate nothing the analysis does not
already establish while normalizing an attack pattern in the repository's
own history.

## 7. Same-name neutering analysis (why it is outside the v0.4 boundary)

The mechanics, end to end:

1. GitHub required-status rules match check runs by name. The four frozen
   names are job `name:` values reported by GitHub Actions.
2. For `pull_request` events, the workflow content that produces those
   check runs is sourced from the pull request's own side of the merge —
   the PR controls the executable content of `.github/workflows/ci.yml`.
3. The `workflow-integrity` check exists to constrain that content — but
   `tools/verify_ci_workflow.py` is sourced from the same head. A PR that
   edits the workflow can edit the verifier in the same commit.
4. The verifier's tests exist to constrain the verifier — but
   `tests/test_v04_delivery_gate.py` is sourced from the same head. The
   same PR edits them too.
5. A writer therefore replaces all three with a self-consistent set that
   keeps the four job `name:` values and reports success. All four required
   checks conclude green on the latest head; branch-up-to-date is
   satisfiable by updating the branch; zero approvals are required; the
   merge proceeds.

The chain never leaves the pull-request head: every layer that could refuse
the change is itself part of the change. Self-attestation from modifiable
content is not authority. This is structural, not an implementation bug —
no Wave 2 refinement of the three files can close it, because any
replacement file is subject to the same co-edit. Closing it requires an
authority the head cannot modify: a second human whose review is mandatory
(Trigger A), a workflow required from outside the repository (Trigger B),
or a separately administered check provider (Trigger C).

Why this is outside the v0.4 boundary rather than a defect to fix now: the
only writer in the current topology is the solo maintainer, so the attacker
this vector requires is the same person the boundary already names as the
trusted authority. A repository-level control cannot defend a repository
against its own sole administrator — the administrator can edit the ruleset
itself (contract §16, lockout note). Declaring the vector outside the
boundary is the honest statement of what this topology can enforce;
claiming otherwise was the defect, and it is what this amendment removes.

## 8. Why this boundary is selected now

Topology facts, verified at freeze time (contract §1): the repository is
public, owner type User, operated as a solo-builder project with one active
maintainer.

- **CODEOWNERS + required code-owner review** requires a second trusted
  reviewer, because pull-request authors cannot approve their own pull
  requests. With one human, every owner-authored PR — that is, every PR —
  would deadlock against a reviewer who does not exist. Deferred to
  Trigger A.
- **Organization/enterprise required workflows** place the authority
  workflow outside the modifiable head, but they are not a repository-level
  feature available to the current personal-repository topology. Deferred
  to Trigger B.
- **A trusted GitHub App or external check service** would add credentials,
  hosting, webhook, deployment, incident, key-rotation, availability, and
  operator scope that is disproportionate to a delivery-gate unit and must
  be designed as its own unit. Deferred to Trigger C.
- **`pull_request_target` is not adopted as an improvised substitute.** A
  privileged base-context workflow requires a separate threat model and
  cannot be assumed to satisfy latest-head required-check semantics without
  a live proof. The existing outright ban (D-v0.4.35, verifier reason
  `pull_request_target`) stands unchanged.

## 9. Future upgrade triggers (D-v0.4.48)

Adversarial tamper resistance becomes a separate follow-on unit — with its
own contract, decisions, and proofs — when any one of these conditions is
met. None of this is hidden U-P2 scope, and none of it is partially
implemented now.

### Trigger A — second trusted human reviewer

- invite a second trusted collaborator with write access;
- create base-branch `.github/CODEOWNERS`;
- protect:
  - `.github/CODEOWNERS`;
  - `.github/workflows/**`;
  - `tools/verify_ci_workflow.py`;
  - `tests/test_v04_delivery_gate.py`;
  - the delivery contract/amendments;
- require at least one approval;
- require code-owner review;
- dismiss stale approvals;
- require approval from someone other than the most recent pusher;
- prove the PR author cannot self-satisfy the rule.

### Trigger B — organization/enterprise required workflow

- move or mirror the repository into a qualifying organization/enterprise
  topology;
- place the authority workflow outside the modifiable repository head;
- require it through organization/enterprise rulesets;
- verify it evaluates the latest PR commit;
- prove a PR cannot replace or suppress the authority.

### Trigger C — trusted GitHub App or external check

- build or adopt a separately administered GitHub App/check provider;
- bind the required check to that specific App source;
- evaluate the latest PR head;
- isolate credentials and hosting;
- add incident, key-rotation, availability, and recovery procedures;
- prove a repository writer cannot forge the check.

## 10. Wave 3 documentation obligations (extends contract §15)

Wave 3 must state the trust boundary prominently — not in a footnote — in:

```text
README.md
CONTRIBUTING.md
TROUBLESHOOTING.md
```

Required wording concepts, in addition to everything contract §15 already
requires:

- the required checks are self-hosted in the repository;
- they protect honest development and catch accidental drift;
- they are not an external security authority;
- a check name alone does not prove unchanged check semantics;
- changes to delivery-control files (`.github/workflows/ci.yml`,
  `tools/verify_ci_workflow.py`, `tests/test_v04_delivery_gate.py`) require
  exceptional manual review;
- the future independent-authority triggers (§9) exist and are deferred.

## 11. U-P2 acceptance criteria under this boundary

U-P2 may complete without a second reviewer or external service only when
all of the following hold:

- the honest-maintainer boundary is frozen (this amendment);
- no adversarial claim remains anywhere in the unit's documentation;
- the workflow, verifier, and tests pass independent technical audit under
  that boundary;
- the failing-test probe proves ordinary merge blocking (§6);
- the documentation exposes the limitation (§10);
- no external-authority feature is falsely claimed.

## 12. Wave 0.5 file boundary and byte-identity record

Wave 0.5 touches exactly two files:

```text
DECISIONS.md                                      modified (section prepended)
agentic-os-v0.4-u-p2-trust-boundary-amendment.md  new      (this file)
```

The three Wave 1 files remain byte-identical and unstaged; their SHA-256
hashes at amendment time, equal to their audited Wave 1 values:

```text
68ee25e3b817e760430e99bb0920511dc0465359ec5619ff9bf5f05b8696501d  .github/workflows/ci.yml
f52d239f1d0d47f0e8db59649a7f013e1eba1048fde8bd42ed2efa94315fadee  tools/verify_ci_workflow.py
1f9a33aa67ae283ce16514640fbb01a9f258e64a77b7c6820292b374ad314cf5  tests/test_v04_delivery_gate.py
```

No production, packaging, protocol, schema, or documentation implementation
changed; nothing was staged, committed, pushed, tagged, or altered in
GitHub settings during Wave 0.5.

## 13. Wave 0.5 landing sequence (D-v0.4.50)

The independent Wave 0.5 audit that produced this amendment also fixes the
order in which the remaining U-P2 work lands. The following sequencing is
normative and frozen:

1. Wave 0.5 lands first as one documentation-only commit containing only:
   - DECISIONS.md
   - agentic-os-v0.4-u-p2-trust-boundary-amendment.md

2. No Wave 1 file may be staged or committed before the Wave 0.5 commit exists.

3. After the Wave 0.5 commit:
   - the three Wave 1 files receive a renewed independent technical audit under
     the honest-maintainer boundary;
   - only a PASS, or corrected-and-re-audited PASS, permits Wave 1 staging.

4. Wave 2 and Wave 3 remain blocked until:
   - Wave 0.5 is committed;
   - the renewed Wave 1 audit passes;
   - Wave 1 is committed.

5. Ruleset activation and the failing-test probe remain post-workflow-bootstrap
   activities.

6. U-K1, U-T1, U-W1, and U-A4 remain blocked until U-P2 is fully merged and
   closed.

## 14. Extended commit sequence (D-v0.4.50, extends D-v0.4.44)

Contract §18 (D-v0.4.44) froze a four-item, one-per-wave commit sequence. This
amendment extends that sequence — it does not erase or replace the historical
four-item record — by inserting exactly one Wave 0.5 commit at position 2,
between the Wave 0 commit and the Wave 1 commit. The frozen Wave 0.5 commit
message:

```text
docs: adopt U-P2 solo-maintainer trust boundary
```

The complete, ordered five-commit sequence is therefore:

```text
1. docs: freeze U-P2 protected delivery contract (Wave 0)
2. docs: adopt U-P2 solo-maintainer trust boundary (Wave 0.5 — inserted)
3. ci: add immutable read-only validation workflow (Wave 1)
4. test: verify U-P2 workflow and distribution gates (Wave 2)
5. docs: document protected Agentic OS contribution flow (Wave 3)
```

The four original messages (positions 1, 3, 4, and 5) are preserved verbatim
from D-v0.4.44; only the position-2 Wave 0.5 message is new. Any claim that the
complete U-P2 history is four commits no longer holds — with Wave 0.5 it is
five ordered commits. D-v0.4.44 stays byte-identical frozen history; this
section and D-v0.4.50 carry the extension.

## 15. Extended file and delivery boundary (D-v0.4.50, extends D-v0.4.44)

Contract §14 (file boundary) and §18 (D-v0.4.44, frozen delivery metadata)
fixed the U-P2 wave/file table. This amendment extends that boundary to
explicitly include Wave 0.5. The complete, extended wave/file table:

### Wave 0

```text
DECISIONS.md
agentic-os-v0.4-u-p2-delivery-gate-contract.md
```

### Wave 0.5

```text
DECISIONS.md
agentic-os-v0.4-u-p2-trust-boundary-amendment.md
```

### Wave 1

```text
.github/workflows/ci.yml
tools/verify_ci_workflow.py
tests/test_v04_delivery_gate.py
```

### Wave 2

Remains within the exact Wave 1 implementation files unless a separately
audited contract amendment authorizes more.

### Wave 3

```text
README.md
CONTRIBUTING.md
TROUBLESHOOTING.md
```

Precisely:

- the original contract's "nothing else" boundary applied to its original
  Wave 0/1/2/3 wave table;
- Wave 0.5 is a governed extension created by the independent audit finding,
  not a reinterpretation of the original table;
- this amendment adds exactly two authorized Wave 0.5 paths — `DECISIONS.md`
  and `agentic-os-v0.4-u-p2-trust-boundary-amendment.md` — and exactly one
  commit;
- no production, packaging, protocol, schema, migration, or unrelated
  documentation file is authorized by this extension;
- the original contract remains historical and byte-identical, and D-v0.4.44
  is extended by D-v0.4.50, never reworded.

## 16. Decision index (added by this amendment)

D-v0.4.45 solo-maintainer honest-authority boundary; claims reduced, checks unchanged
D-v0.4.46 self-modifiable required checks are identity, not independent authority
D-v0.4.47 solo topology keeps zero approvals; code-owner review deferred to Trigger A
D-v0.4.48 external or base-controlled authority is trigger-gated future work
D-v0.4.49 probe evidence is limited to ordinary failure enforcement
D-v0.4.50 Wave 0.5 landing sequence, commit-sequence extension, and file/delivery-boundary extension; D-v0.4.44 extended, not rewritten
