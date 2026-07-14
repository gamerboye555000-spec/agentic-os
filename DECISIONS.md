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

- **D-v0.2.34 — Gate U-H1 result.** Focused suite
  (`tests/test_v02_hooks.py`) 67 green; full suite 670 green (603
  pre-existing, none weakened or deleted); `compileall` clean;
  `git diff --check` clean. Renderer and checked-in
  `adapters/claude-code/PROTOCOL.md` stay byte-identical (existing U-C3
  parity test now also covers the envelope section); codex/gemini/generic
  adapters unchanged.

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
