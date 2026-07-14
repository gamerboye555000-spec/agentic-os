"""One-way Windows/Obsidian export of the generated AOS/ mirror (U-C4).

`aos sync --export-to PATH [--dry-run]` projects the generated
`.agentic-os/obsidian-vault/AOS/` tree beneath a user-selected directory —
typically a Windows path mounted under WSL (`/mnt/c/...`). The export is
strictly one-way: destination edits are never ingested; the next export
replaces them.

Ownership: `PATH/AOS` is FULLY owned by Agentic OS and always holds one
complete generation, proven by the reserved empty ownership-sentinel
directory `PATH/AOS/.aos-export-owned` — filename shape alone is never
treated as proof of ownership (a human `Home.md` is not ours to delete).
`PATH/.aos-export-staging` holds the next generation while it is built and
validated; `PATH/.aos-export-previous` holds the last good generation during
promotion only; `PATH/.aos-export-cleanup-<pid>-<n>` names are reserved
single-use quarantine positions that exist only while a STG/PREV tree is
being deleted (a leftover one from an interrupted cleanup is detected and
refused on the next run). Nothing outside those reserved names is ever
created, modified, or deleted; beyond them the export reads only the NAMES
of PATH's direct children (to detect stale cleanup state), never their
contents — the user's vault config (`PATH/.obsidian/`) lives beside
`AOS/`, so Obsidian opens PATH as the vault root, never PATH/AOS.

Change detection is size-then-byte comparison, never mtime. The plan is
computed from a FRESH destination scan after the local mirror regenerates,
recorded as an exact base snapshot (existence, identity, directory set,
file set + sizes, length-framed content hash), and the destination must
still match that snapshot at the pre-promotion recheck — any concurrent
change to destination content or structure refuses rather than being
silently deleted by the whole-tree swap (metadata-only changes —
permissions, timestamps — are not part of the snapshot). The export is
EVENTLESS (extends D-P0.6/D-W7.1: derived views emit no ledger events).

Threat model: hostile filesystem state (symlinks, hardlink aliases,
case-insensitive DrvFS, concurrent writers) with a trusted local user.
Before the first mutation the apply pins the approved PATH itself: it is
opened O_RDONLY|O_DIRECTORY|O_NOFOLLOW, fstat'ed, required to match the
identity recorded in the plan, and that descriptor stays open for the
COMPLETE apply — staging creation, every AOS/STG/PREV rename, every
PATH-level fsync, cleanup, and the enforcement rescans of destination
and staging content are all descriptor-anchored (os.fwalk with dir_fd;
per-file O_NOFOLLOW opens with fstat identity checks), so a concurrently
replaced PATH is refused rather than written through or read around.
After the pin, PATH-derived pathnames are consulted only to verify the
pathname still reaches the pinned directory, to re-derive containment
refusals, and for an additive best-effort mount probe. The staging build
writes every file through pinned directory descriptors (O_NOFOLLOW dir
opens, O_EXCL file creation), so a same-user racer cannot swap a staging
subdirectory for a symlink and divert a staged write outside
PATH/AOS+STG+PREV — the swap is refused, not followed. The build's
payload-copy SOURCE side is equally descriptor-anchored: the source AOS
root is pinned (O_DIRECTORY|O_NOFOLLOW, identity-checked against the
plan) for the complete build, entity directories open O_NOFOLLOW relative
to it, the basename opens O_RDONLY|O_NOFOLLOW|O_NONBLOCK relative to the
entity descriptor, the opened descriptor must be a regular file with
exactly the identity the plan-time source scan recorded, the copy reads
only from that descriptor with pre/post fstat stability checks, and no
absolute source pathname is ever opened for a copy — a swapped source
entity directory or replaced source file refuses instead of redirecting
the read. Unchanged-file
hardlink reuse is likewise fully descriptor-anchored (PATH fd -> AOS fd
-> entity fd, all O_NOFOLLOW, with the source required to match the
identity the plan recorded and os.link called with src_dir_fd AND
dst_dir_fd, follow_symlinks=False) — the mutable PATH/AOS pathname is
never a link source. Every enforcement-critical content read goes
through one shared vetted reader: descriptor-relative
O_RDONLY|O_NOFOLLOW|O_NONBLOCK open, fstat of the opened descriptor,
regular file required, identity checked against the inspecting scan,
pre- and post-read fstat stability. Staging is discarded only after a
samestat identity proof against the pinned staging descriptor —
held open across every discard path so the inode number cannot be
recycled into a foreign directory — and recursive STG/PREV cleanup is
quarantine-based end to end (_rmtree_pinned): the root is pinned
O_DIRECTORY|O_NOFOLLOW and its recorded identity proven, device and
mount containment of the root and every descendant are checked, the
proven root is then ATOMICALLY renamed to a fresh single-use private
cleanup name (PATH/.aos-export-cleanup-…) and the captured entry
re-proven against the held descriptor, every child is likewise
quarantined (atomic same-directory rename to a private name), proven
against its inspected identity, and only then deleted — a captured
replacement is renamed back to its public name and the cleanup refuses.
No public (meaningful) name is ever passed to unlink or rmdir; anything
whose identity cannot be proven is retained byte-for-byte and reported.
HONEST LIMIT of that guarantee: POSIX offers no delete-by-descriptor
and no no-replace rename in the standard library, so two residues
remain — (1) an entry raced onto a just-verified single-use PRIVATE
quarantine name in the syscall gap before its unlink/rmdir is deleted
(for rmdir only if it is an empty directory); (2) a quarantine or
restore rename overwrites a TYPE-COMPATIBLE entry raced onto its
target name inside the freshness/absence-probe-to-rename gap: when
the entry being moved is a directory, only an empty directory can be
overwritten; when it is a regular file, a regular file or symlink
raced onto the name is overwritten — on the restore path that target
is the entry's PUBLIC (meaningful) name. Entries at meaningful names
outside those microsecond windows — the public root name and every
real child name — are never deleted without an identity proof. The verified AOS root is
descriptor-pinned at the recheck (before its content rescan) and held
through promotion: the move-aside guard and the PREV ownership proof
(recorded and descriptor-pinned immediately after the AOS-to-PREV
rename) both compare against that HELD descriptor, which inode-number
recycling cannot forge. The rollback rename (PREV back to AOS) is
guarded the same way: it runs only after a fresh lstat of the previous
name proves exactly that pinned identity — a never-pinned,
uninspectable, replaced, or vanished PREV is retained untouched and
the export strands with exact recovery commands rather than renaming
unvalidated content onto the authoritative name. Validation
returns an immutable snapshot of the complete staged generation, and the
final pre-promotion verification runs freshest-last: (1) a fresh SOURCE
scan and content hash against the snapshot FIRST, (2) the complete
DESTINATION structure/content/identity recheck next (which pins the
verified AOS root and records every entity directory's identity),
(3) the complete STAGING rescan and content hash LAST — including the
hardlink count and identity recheck, with the live side probed through
the held AOS-root descriptor and the recorded entity-directory
identities, never through a path with unresolved intermediate
components — followed only by the structural destination guard and the
promotion renames. After the final staging scan, the only remaining
syscalls before the renames are identity lstats (the live hardlink
probes, the structural guard, the move-aside guard): no content is
read or hashed after that scan, and no further verification pass
widens the exposure. Precisely stated, PER FILE: a staged file's
unobservable interval begins when the FINAL rescan has read that
file's bytes (earlier-scanned files carry the remainder of that scan
in their window) and ends at the promotion renames (a destination
CONTENT change after step 2 is within the accepted window — except
for intentionally hardlinked bytes, which the step-3 hash still
covers up to each file's read). Mounted or cross-device subtrees inside AOS/STG/PREV — and
inside the SOURCE mirror (per-entry st_dev against the source root plus
the additive mount probe, checked by every source scan before any copy
or hash) — are refused before adoption, validation, promotion, and
recursive cleanup, with the cleanup sweep descriptor-anchored to the
exact tree the delete would recurse into (a bind mount of the SAME
filesystem is indistinguishable from a plain directory with
standard-library stat checks — documented limitation). Inspection
errors are never read as absence: state probes distinguish ENOENT from
EIO/EACCES and fail closed. Contract:
agentic-os-v0.2-u-c4-windows-export-contract.md.
"""

from __future__ import annotations

import errno
import hashlib
import itertools
import os
import shlex
import shutil
import stat
import types
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import obsidian, utils
from .utils import AosError

STAGING_NAME = ".aos-export-staging"
PREVIOUS_NAME = ".aos-export-previous"
#: Reserved prefix for single-use private quarantine names: recursive
#: STG/PREV cleanup atomically renames the tree it is about to delete —
#: and every child within — to `<prefix><pid>-<n>` before any unlink or
#: rmdir, so no public (meaningful) name is ever deleted by name. The
#: names exist only while a cleanup is running; a leftover one marks an
#: interrupted cleanup and refuses the next export until inspected.
CLEANUP_PREFIX = ".aos-export-cleanup-"
#: Process-wide monotone counter feeding _fresh_quarantine_name: a name
#: is never reused within a process, so quarantines cannot collide with
#: each other by construction (the pid component separates processes).
_cleanup_seq = itertools.count()
#: Reserved empty directory inside PATH/AOS marking the tree as created by
#: aos export. An empty directory (not a file) so file-based tree hashes of
#: the generation are unchanged. Required for every repeat export; any
#: content inside it, or any other hidden entry beside it, refuses.
OWNER_SENTINEL_NAME = ".aos-export-owned"

#: os.link errnos meaning "hardlinks unsupported/forbidden here" (DrvFS/9P,
#: exFAT, some network mounts): fall back to copying the file. Any OTHER
#: errno (EIO, ...) aborts the export with the old generation intact —
#: never blanket-caught (contract errno policy).
LINK_FALLBACK_ERRNOS = frozenset({
    errno.EPERM, errno.EACCES, errno.EOPNOTSUPP, errno.ENOTSUP,
    errno.ENOSYS, errno.EXDEV, errno.EMLINK,
})

#: Directory-fsync errnos meaning "unsupported here" (9P/DrvFS commonly
#: reject directory fsync): skip. Any OTHER errno (EIO, ENOSPC, ...) is an
#: integrity failure and stays fatal (contract errno policy). File fsync
#: failures are always fatal — no skip set.
DIR_FSYNC_SKIP_ERRNOS = frozenset({
    errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS,
})

#: Win32 reserved device stems (the component up to its first dot, case-
#: insensitive, with or without a suffix: `aux`, `aux.md`, ...).
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{n}" for n in range(1, 10)}
    | {f"lpt{n}" for n in range(1, 10)}
)

_WINDOWS_ILLEGAL_CHARS = set('<>:"|?*\\')


# ---------------------------------------------------------------------------
# Destination resolution and containment (existence-aware)


@dataclass
class ExportTarget:
    """The resolved destination and the only three paths export may touch."""

    dest_root: Path      # user PATH, resolved strictly (must exist)
    dest_aos: Path       # PATH/AOS — the authoritative generation
    staging: Path        # PATH/.aos-export-staging
    previous: Path       # PATH/.aos-export-previous
    #: Identity of the resolved PATH at check time — a replaced PATH must
    #: refuse at planning and again at the pre-promotion recheck.
    dest_root_stat: os.stat_result
    #: (label, independently resolved path) — the paths export must never
    #: equal, enter, or contain.
    protected: list[tuple[str, Path]] = field(default_factory=list)
    #: Adoption inventory of the destination AOS. check_destination fills
    #: it as the refusal-first gate BEFORE the mirror regenerates;
    #: compute_plan re-fills it from a fresh scan AFTER — the plan is
    #: never built from a pre-sync snapshot.
    dest_files: list[tuple[str, int]] = field(default_factory=list)
    dest_dirs: list[str] = field(default_factory=list)
    dest_sentinel: bool = False
    dest_aos_stat: os.stat_result | None = None
    #: rel -> inspected identity from the same scan that produced
    #: dest_files. The plan's vetted destination reads and the staging
    #: build's hardlink-source checks prove they operate on exactly
    #: these inodes.
    dest_file_stats: dict[str, os.stat_result] = field(default_factory=dict)


def _exists_for_protection(path: Path) -> bool:
    """Existence probe for protected-root candidates that fails CLOSED:
    only a precise nonexistent result reads as absent. An uninspectable
    candidate (EACCES, EIO, a symlink loop, ...) is treated as EXISTING,
    so it STAYS protected and any real problem surfaces later as an
    actionable containment refusal — Path.exists() would instead either
    crash the command with an exit-2 internal error (EACCES/EIO
    propagate) or silently drop the protection (ELOOP reads as False)."""
    try:
        os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:
        return True
    return True


def protected_roots(aos_dir: Path) -> list[tuple[str, Path]]:
    """Most-specific first, each resolved independently: .agentic-os or the
    database may themselves be symlinks, so none is derivable from another
    after resolution. The live workspace is the LEXICAL parent of the
    .agentic-os path, resolved — with repo/.agentic-os symlinked elsewhere,
    resolve-then-parent would protect only the link target's parent and
    miss the repository the user actually works in."""
    workspace = aos_dir.parent.resolve()
    roots = [
        ("source mirror", obsidian.vault_aos_dir(aos_dir).resolve()),
        ("vault directory", (aos_dir / obsidian.VAULT_DIRNAME).resolve()),
        ("database directory", (aos_dir / utils.DB_FILENAME).resolve().parent),
        (".agentic-os directory", aos_dir.resolve()),
        ("live workspace", workspace),
    ]
    for candidate in (workspace, *workspace.parents):
        # A .git FILE counts too: git worktrees keep a pointer file.
        if _exists_for_protection(candidate / ".git"):
            roots.append(("repository", candidate.resolve()))
            break
    return [
        (label, path)
        for label, path in roots
        if _exists_for_protection(path)
    ]


def _lstat_or_absent(
    path, *, dir_fd: int | None = None, display=None
) -> os.stat_result | None:
    """State probe that never confuses CANNOT-INSPECT with ABSENT:
    FileNotFoundError means absent (None); every other OSError — EIO,
    EACCES, EPERM, ... — refuses with the cause. A state check that
    cannot run must fail closed, never report a clean absence (contract
    errno policy). `display` names the full path in the refusal when the
    probe itself is dir_fd-relative."""
    try:
        return os.lstat(path, dir_fd=dir_fd)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise AosError(
            f"Refusing to export: cannot inspect {display or path} "
            f"({exc}); fix the cause and rerun."
        )


def _mutation_root(candidate: Path) -> Path:
    """A fixed direct child of the resolved PATH. Existing: lstat, refuse
    symlinks, resolve strictly. Nonexistent: the candidate itself (its
    parent is already resolved; the missing component is never followed).
    An UNINSPECTABLE candidate refuses — EIO here is not absence, and
    never an exit-2 internal error."""
    st = _lstat_or_absent(candidate)
    if st is None:
        return candidate
    if stat.S_ISLNK(st.st_mode):
        try:
            link_target = os.readlink(candidate)
        except OSError:
            link_target = "<unreadable target>"
        raise AosError(
            f"Refusing to export: {candidate} is a symlink to "
            f"{link_target}; replace it with a real directory."
        )
    try:
        return candidate.resolve(strict=True)
    except OSError as exc:
        raise AosError(
            f"Refusing to export: cannot resolve {candidate} ({exc}); "
            "fix the cause and rerun."
        )


def _stat_for_containment(path: Path):
    """None when the path (or a lexical ancestor) does not exist. Any
    OTHER stat failure refuses: a containment check that cannot run must
    fail closed, never silently pass (contract errno policy)."""
    try:
        return os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as exc:
        raise AosError(
            f"Refusing to export: cannot verify containment at {path} "
            f"({exc}); fix the cause and rerun."
        )


def _refuse_overlap(label: str, root: Path, probe: Path) -> None:
    """Equal / inside / contains — normalized paths always, samestat
    additionally when both sides exist (case-insensitive destination
    filesystems and aliased directories defeat string comparison)."""
    if probe == root:
        raise AosError(
            f"Refusing to export: {probe} is the {label} ({root}); "
            "choose an unrelated directory."
        )
    if root in probe.parents:
        raise AosError(
            f"Refusing to export: {probe} is inside the {label} ({root}); "
            "choose a directory outside it."
        )
    if probe in root.parents:
        raise AosError(
            f"Refusing to export: {probe} contains the {label} ({root}); "
            "export would delete it."
        )
    root_stat = _stat_for_containment(root)
    if root_stat is None:
        return
    probe_stat = _stat_for_containment(probe)
    if probe_stat is not None and os.path.samestat(probe_stat, root_stat):
        raise AosError(
            f"Refusing to export: {probe} is the {label} ({root}); "
            "choose an unrelated directory."
        )
    for ancestor in probe.parents:
        ancestor_stat = _stat_for_containment(ancestor)
        if ancestor_stat is not None and os.path.samestat(
            ancestor_stat, root_stat
        ):
            raise AosError(
                f"Refusing to export: {probe} is inside the {label} "
                f"({root}); choose a directory outside it."
            )
    if probe_stat is not None:
        for ancestor in root.parents:
            ancestor_stat = _stat_for_containment(ancestor)
            if ancestor_stat is not None and os.path.samestat(
                ancestor_stat, probe_stat
            ):
                raise AosError(
                    f"Refusing to export: {probe} contains the {label} "
                    f"({root}); export would delete it."
                )


def check_destination(aos_dir: Path, export_to: str) -> ExportTarget:
    raw = Path(export_to).expanduser()
    try:
        dest_root = raw.resolve(strict=True)
    except FileNotFoundError:
        raise AosError(
            f"Refusing to export: {raw} does not exist; create the "
            "destination directory first."
        )
    except OSError as exc:
        raise AosError(f"Refusing to export: cannot resolve {raw}: {exc}")
    try:
        root_stat = os.stat(dest_root)
    except OSError as exc:
        raise AosError(f"Refusing to export: cannot resolve {raw}: {exc}")
    if not stat.S_ISDIR(root_stat.st_mode):
        raise AosError(f"Refusing to export: {dest_root} is not a directory.")
    target = ExportTarget(
        dest_root=dest_root,
        dest_aos=_mutation_root(dest_root / obsidian.AOS_SUBDIR),
        staging=_mutation_root(dest_root / STAGING_NAME),
        previous=_mutation_root(dest_root / PREVIOUS_NAME),
        dest_root_stat=root_stat,
        protected=protected_roots(aos_dir),
    )
    _check_containment(target)
    _refuse_stale(target)
    _adopt_destination(target)
    return target


def _sentinel_refusal(dest_aos: Path) -> AosError:
    return AosError(
        f"Refusing to export: {dest_aos} exists but lacks the Agentic OS "
        f"ownership sentinel ({OWNER_SENTINEL_NAME}/), so aos export "
        "cannot prove it created this tree and will not replace it. Move "
        "or delete the existing directory and rerun. See TROUBLESHOOTING.md."
    )


def _adopt_destination(target: ExportTarget) -> None:
    """Full-ownership gate. Decidable from destination state alone, so it
    refuses before the mirror regenerates. A first export may adopt only
    an absent or genuinely empty AOS; anything else requires the exact
    ownership sentinel — recognized filename shapes alone are NOT proof
    the tree is ours to delete."""
    target.dest_files, target.dest_dirs = [], []
    target.dest_sentinel = False
    target.dest_aos_stat = None
    target.dest_file_stats = {}
    # _lstat_or_absent, not a bare lstat: an uninspectable AOS (EIO,
    # EACCES, ...) is an exit-1 refusal, never an exit-2 internal error.
    aos_stat = _lstat_or_absent(target.dest_aos)
    if aos_stat is None:
        return
    if not stat.S_ISDIR(aos_stat.st_mode):
        raise AosError(
            f"Refusing to export: {target.dest_aos} exists and is not "
            "a directory."
        )
    if aos_stat.st_dev != target.dest_root_stat.st_dev or os.path.ismount(
        target.dest_aos
    ):
        raise AosError(
            f"Refusing to export: {target.dest_aos} is a mount point or on "
            f"a different filesystem than {target.dest_root}; the export "
            "owns PATH/AOS through whole-tree renames, which cannot cross "
            "filesystems. Unmount it and rerun."
        )
    try:
        files, dirs, sentinel, file_stats = _scan_dest_aos(target.dest_aos)
    except AosError:
        raise
    except OSError as exc:
        # An uninspectable destination cannot be adopted: fail closed
        # rather than route never-vetted content into the swap.
        raise AosError(
            f"Refusing to export: cannot inspect {target.dest_aos} "
            f"({exc}); fix the cause and rerun."
        )
    if (files or dirs) and not sentinel:
        raise _sentinel_refusal(target.dest_aos)
    target.dest_aos_stat = aos_stat
    target.dest_files, target.dest_dirs = files, dirs
    target.dest_sentinel = sentinel
    target.dest_file_stats = file_stats


def _destination_changed(detail: str) -> AosError:
    return AosError(
        "Refusing to export: destination changed during export; rerun to "
        f"compute a fresh plan. (Detected: {detail}.)"
    )


def _refresh_destination(aos_dir: Path, target: ExportTarget) -> None:
    """Post-sync re-resolution: the mirror regenerated between
    check_destination and planning, so every destination fact is
    re-derived immediately before the plan is computed. The plan is built
    from the destination as it is NOW; the pre-promotion recheck then
    holds the destination to exactly this state."""
    try:
        root_stat = os.lstat(target.dest_root)
    except OSError as exc:
        raise _destination_changed(f"cannot stat {target.dest_root}: {exc}")
    if stat.S_ISLNK(root_stat.st_mode) or not os.path.samestat(
        root_stat, target.dest_root_stat
    ):
        raise _destination_changed(f"{target.dest_root} was replaced")
    target.dest_aos = _mutation_root(target.dest_root / obsidian.AOS_SUBDIR)
    target.staging = _mutation_root(target.dest_root / STAGING_NAME)
    target.previous = _mutation_root(target.dest_root / PREVIOUS_NAME)
    target.protected = protected_roots(aos_dir)
    _check_containment(target)
    _refuse_stale(target)
    _adopt_destination(target)


def _check_containment(target: ExportTarget) -> None:
    for label, root in target.protected:
        for probe in (target.dest_aos, target.staging, target.previous):
            _refuse_overlap(label, root, probe)


class _StagingCompromised(AosError):
    """Staging is missing or provably not the directory this run created:
    it must be RETAINED (never rmtree'd — it is not ours to delete)."""


class _CleanupRootAbsent(Exception):
    """_rmtree_pinned's cleanup root is GENUINELY absent under the pinned
    destination (the initial pin-open got ENOENT before any mutation).
    A dedicated type, not FileNotFoundError: Python maps errno.ENOENT to
    the FileNotFoundError subclass at OSError construction, so an
    interior ENOENT raised mid-deletion (a child raced away, a
    quarantined entry stolen) would be INDISTINGUISHABLE by exception
    type from clean absence — and interior failures leave a retained
    tree that MUST be reported, never read as \"nothing was there\"."""


def _recheck_target(
    plan: ExportPlan,
    staging_fd: int,
    staging_stat: os.stat_result,
    dest_fd: int,
    linked,
) -> tuple[bool, int | None, dict[str, os.stat_result]]:
    """Full destination recheck — step 2 of the final pre-promotion
    sequence (after the fresh source verification, before the final
    staging rescan). Returns (first_export, aos_fd, aos_dirs):
    first_export is True when there is no live AOS (matching the plan
    base); aos_fd is an OPEN O_DIRECTORY|O_NOFOLLOW descriptor on the
    verified live AOS root (None on a first export), opened BEFORE the
    content rescan and held by the caller through promotion and cleanup
    — the held descriptor keeps the AOS root inode alive, so its inode
    number cannot be recycled into a foreign directory and forge a later
    samestat proof (the move-aside guard and the PREV-cleanup ownership
    proof both chain to this descriptor's identity); aos_dirs maps each
    entity directory to the identity this rescan inspected (the final
    hardlink verification must reach live files through exactly these
    directories). Staging is verified FIRST: every other refusal here
    discards staging, which is only safe while staging is provably still
    the directory this run created and validated. STG and PREV are
    probed relative to the PINNED destination descriptor — never through
    a fresh resolution of PATH — and an inspection failure (EIO, EACCES,
    ...) refuses rather than reading as absence."""
    target = plan.target
    try:
        stg_stat = _lstat_or_absent(
            STAGING_NAME, dir_fd=dest_fd, display=target.staging
        )
    except AosError as exc:
        # Uninspectable staging is not provably ours: retain it.
        raise _StagingCompromised(
            f"{exc} Staging {target.staging} was left in place; remove it "
            "after fixing the cause, then rerun."
        )
    if (
        stg_stat is None
        or stat.S_ISLNK(stg_stat.st_mode)
        or not stat.S_ISDIR(stg_stat.st_mode)
        or not os.path.samestat(stg_stat, staging_stat)
    ):
        raise _StagingCompromised(
            f"Refusing to export: staging {target.staging} was removed or "
            f"replaced during export (concurrent process?); "
            f"{target.dest_aos} is unchanged. Ensure {target.staging} does "
            "not exist, then rerun."
        )
    try:
        root_stat = os.lstat(target.dest_root)
    except OSError as exc:
        raise _destination_changed(f"cannot stat {target.dest_root}: {exc}")
    if stat.S_ISLNK(root_stat.st_mode) or not os.path.samestat(
        root_stat, target.dest_root_stat
    ):
        raise _destination_changed(f"{target.dest_root} was replaced")
    if (
        _lstat_or_absent(
            PREVIOUS_NAME, dir_fd=dest_fd, display=target.previous
        )
        is not None
    ):
        raise _destination_changed(f"{target.previous} appeared")
    # Symlinks planted at AOS/PREV refuse inside _mutation_root.
    target.dest_aos = _mutation_root(target.dest_root / obsidian.AOS_SUBDIR)
    target.previous = _mutation_root(target.dest_root / PREVIOUS_NAME)
    _check_containment(target)
    try:
        live_stat = os.lstat(target.dest_aos)
    except FileNotFoundError:
        live_stat = None
    except OSError as exc:
        raise _destination_changed(f"cannot stat {target.dest_aos}: {exc}")
    if plan.base_exists != (live_stat is not None):
        raise _destination_changed(
            f"{target.dest_aos} appeared"
            if live_stat is not None
            else f"{target.dest_aos} disappeared"
        )
    if live_stat is None:
        return True, None, {}
    if not stat.S_ISDIR(live_stat.st_mode) or not os.path.samestat(
        live_stat, plan.base_stat
    ):
        raise _destination_changed(f"{target.dest_aos} was replaced")
    # Pin the verified AOS root BEFORE the content rescan: the content
    # comparison below then vouches for exactly this inode (a swap after
    # the pin is caught as a content/structure mismatch; a pre-pin swap
    # that still matches the base snapshot byte-for-byte is
    # indistinguishable from an unchanged destination by construction).
    try:
        aos_fd = _open_dir_nofollow(obsidian.AOS_SUBDIR, dest_fd)
    except OSError as exc:
        raise _destination_changed(f"cannot open {target.dest_aos}: {exc}")
    try:
        if not os.path.samestat(os.fstat(aos_fd), live_stat):
            raise _destination_changed(f"{target.dest_aos} was replaced")
        try:
            files, dirs, sentinel, live_hash, aos_dirs = (
                _rescan_dest_aos_pinned(target, dest_fd, linked, staging_fd)
            )
        except AosError:
            raise _destination_changed(
                f"unadoptable content appeared under {target.dest_aos}"
            )
        except OSError as exc:
            raise _destination_changed(
                f"cannot rescan {target.dest_aos}: {exc}"
            )
        if files != plan.base_files:
            raise _destination_changed(
                f"file set or sizes under {target.dest_aos} changed"
            )
        if dirs != plan.base_dirs:
            raise _destination_changed(
                f"directory set under {target.dest_aos} changed"
            )
        if sentinel != plan.base_sentinel:
            raise _destination_changed("the ownership sentinel changed")
        if live_hash != plan.base_hash:
            raise _destination_changed(
                f"file content under {target.dest_aos} changed"
            )
    except BaseException:
        os.close(aos_fd)
        raise
    return False, aos_fd, aos_dirs


# ---------------------------------------------------------------------------
# Source and destination scans (provenance, representability, adoption)


def _utf16_units(component: str) -> int:
    return len(component) + sum(1 for ch in component if ord(ch) > 0xFFFF)


def _windows_component_reason(component: str) -> str | None:
    stem = component.split(".", 1)[0]
    if stem.casefold() in _WINDOWS_RESERVED:
        return f"reserved name {stem.casefold()!r}"
    for ch in component:
        if ch in _WINDOWS_ILLEGAL_CHARS or ord(ch) < 0x20:
            return f"illegal character {ch!r}"
    if component.endswith(".") or component.endswith(" "):
        return "trailing dot or space"
    if _utf16_units(component) > 255:
        return "component longer than 255 UTF-16 code units"
    return None


def _check_representability(rels: list[str]) -> None:
    """Deterministic on all platforms — no filesystem sniffing. POSIX
    limits are NOT re-implemented here; the OS reports those itself."""
    by_casefold: dict[str, str] = {}
    for rel in rels:
        for component in rel.split("/"):
            reason = _windows_component_reason(component)
            if reason is not None:
                raise AosError(
                    f"Refusing to export: {rel} is not representable on "
                    f"Windows ({reason}); rename it and rerun sync."
                )
        folded = rel.casefold()
        other = by_casefold.setdefault(folded, rel)
        if other != rel:
            first, second = sorted((other, rel))
            raise AosError(
                f"Refusing to export: {first} and {second} collide on a "
                "case-insensitive filesystem; rename one agent and rerun sync."
            )


def _recognized_dir_rel(rel: Path) -> bool:
    return len(rel.parts) == 1 and rel.parts[0] in obsidian.ENTITY_DIRS


def _raise_walk_error(exc: OSError) -> None:
    """os.walk's default is to silently skip unreadable directories —
    a blanket OSError swallow the contract forbids: an unlistable subtree
    must refuse the scan, never truncate it."""
    raise exc


def _scan_source(
    source: Path,
) -> tuple[list[tuple[str, int]], list[str], dict[str, os.stat_result]]:
    """Inventory the generated mirror. Hidden entries are the user's
    (D-P5.2) and are not exported; anything non-regular or unrecognized
    refuses — this is what keeps the recognizer a sound provenance test
    for our own output at the destination. Every non-hidden entry's
    st_dev must equal the source root's (plus the additive mount probe
    for directories): a mounted or cross-device source subtree refuses
    here, BEFORE any copy or hash reads through it. Also returns each
    file's inspected identity so every later vetted read can prove it
    opened the inode this scan inspected."""
    files: list[tuple[str, int]] = []
    dirs: list[str] = []
    stats: dict[str, os.stat_result] = {}
    root_dev = os.lstat(source).st_dev
    for dirpath, dirnames, filenames in os.walk(
        source, followlinks=False, onerror=_raise_walk_error
    ):
        base = Path(dirpath)
        kept = []
        for name in sorted(dirnames):
            child = base / name
            rel = child.relative_to(source)
            if name.startswith("."):
                continue
            entry_stat = os.lstat(child)
            if entry_stat.st_dev != root_dev or _ismount_probe(child):
                raise _mount_refusal(source, rel)
            if stat.S_ISLNK(entry_stat.st_mode) or not (
                _recognized_dir_rel(rel)
            ):
                raise AosError(
                    "Refusing to export: source mirror contains "
                    f"unrecognized entry {rel.as_posix()}; "
                    "run: python aos.py doctor."
                )
            kept.append(name)
            dirs.append(rel.as_posix())
        dirnames[:] = kept
        for name in sorted(filenames):
            child = base / name
            rel = child.relative_to(source)
            if name.startswith("."):
                continue
            entry_stat = os.lstat(child)
            if entry_stat.st_dev != root_dev:
                raise _mount_refusal(source, rel)
            if not stat.S_ISREG(entry_stat.st_mode) or not (
                obsidian.recognized_note_rel(rel)
            ):
                raise AosError(
                    "Refusing to export: source mirror contains "
                    f"unrecognized entry {rel.as_posix()}; "
                    "run: python aos.py doctor."
                )
            files.append((rel.as_posix(), entry_stat.st_size))
            stats[rel.as_posix()] = entry_stat
    files.sort()
    dirs.sort()
    return files, dirs, stats


def _adoption_refusal(dest_aos: Path, rel: Path) -> AosError:
    return AosError(
        f"Refusing to export: {dest_aos} contains content not generated by "
        f"aos export ({rel.as_posix()}); PATH/AOS is fully managed — open "
        "PATH as the vault root and move other files out of AOS. "
        "See TROUBLESHOOTING.md."
    )


def _hardlink_refusal(dest_aos: Path, rel: Path, nlink: int) -> AosError:
    return AosError(
        f"Refusing to export: {dest_aos} contains a hardlinked file "
        f"({rel.as_posix()}: {nlink} links); PATH/AOS files must not be "
        "aliased outside the export — replace it with an independent copy "
        "and rerun. See TROUBLESHOOTING.md."
    )


def _mount_refusal(root: Path, rel: Path) -> AosError:
    return AosError(
        f"Refusing to export: {root} contains a mounted or cross-device "
        f"subtree ({rel.as_posix()}); the export never inspects, replaces, "
        "or deletes across a mount boundary — unmount it and rerun. "
        "See TROUBLESHOOTING.md."
    )


def _staging_alias_only(
    entry_stat: os.stat_result,
    staging_fd: int | None,
    rel: Path,
) -> bool:
    """True iff the file's single extra hardlink is this run's own staged
    copy — the one alias the pre-promotion rescan must tolerate. The
    staged entry is probed with NO unresolved intermediate component:
    the entity directory is opened O_DIRECTORY|O_NOFOLLOW relative to
    the pinned staging descriptor and the basename lstat'ed relative to
    that — never through a multi-component pathname that would follow a
    symlink raced into the staging tree. Any probe failure reads as
    'not the staged alias' (the caller then refuses the extra link)."""
    if staging_fd is None or entry_stat.st_nlink != 2:
        return False
    entity, base = _split_rel(rel.as_posix())
    entity_fd = None
    try:
        parent_fd = staging_fd
        if entity is not None:
            entity_fd = _open_dir_nofollow(entity, staging_fd)
            parent_fd = entity_fd
        stg_stat = os.lstat(base, dir_fd=parent_fd)
    except OSError:
        return False
    finally:
        if entity_fd is not None:
            os.close(entity_fd)
    return os.path.samestat(entry_stat, stg_stat)


def _scan_dest_aos(
    dest_aos: Path,
) -> tuple[
    list[tuple[str, int]], list[str], bool, dict[str, os.stat_result]
]:
    """Adoption gate + inventory (pathname-based: this is the pre-pin,
    refusal-first gate and the plan-time scan; the enforcement rescan
    before promotion is the descriptor-anchored _rescan_dest_aos_pinned).
    Also returns each file's inspected identity: the plan's vetted reads
    and the staging build's hardlink-source checks must prove they are
    operating on exactly the inodes this scan inspected.
    PATH/AOS is fully owned, so EVERY entry — hidden included — must be a
    regular, recognized, generated note or an entity directory, plus
    (alone among hidden entries, at the root) the empty ownership-sentinel
    directory. Anything else refuses adoption. Mounted or cross-device
    subtrees refuse before anything recurses into them (same-filesystem
    bind mounts are indistinguishable from plain directories with stdlib
    stat checks — documented limitation).

    Regular files must have link count 1: a pre-existing hardlink alias
    means the bytes are shared with something outside AOS, which full
    ownership cannot claim."""
    files: list[tuple[str, int]] = []
    dirs: list[str] = []
    stats: dict[str, os.stat_result] = {}
    has_sentinel = False
    root_dev = os.lstat(dest_aos).st_dev
    for dirpath, dirnames, filenames in os.walk(
        dest_aos, followlinks=False, onerror=_raise_walk_error
    ):
        base = Path(dirpath)
        kept = []
        for name in sorted(dirnames):
            child = base / name
            rel = child.relative_to(dest_aos)
            entry_stat = os.lstat(child)
            if entry_stat.st_dev != root_dev or _ismount_probe(child):
                raise _mount_refusal(dest_aos, rel)
            if name == OWNER_SENTINEL_NAME and len(rel.parts) == 1:
                if not stat.S_ISDIR(entry_stat.st_mode):
                    raise _adoption_refusal(dest_aos, rel)
                inside = sorted(os.listdir(child))
                if inside:
                    raise _adoption_refusal(dest_aos, rel / inside[0])
                has_sentinel = True
                continue  # pruned: excluded from dirs and note counts
            if (
                name.startswith(".")
                or stat.S_ISLNK(entry_stat.st_mode)
                or not _recognized_dir_rel(rel)
            ):
                raise _adoption_refusal(dest_aos, rel)
            kept.append(name)
            dirs.append(rel.as_posix())
        dirnames[:] = kept
        for name in sorted(filenames):
            child = base / name
            rel = child.relative_to(dest_aos)
            entry_stat = os.lstat(child)
            if entry_stat.st_dev != root_dev:
                raise _mount_refusal(dest_aos, rel)
            if (
                name.startswith(".")
                or not stat.S_ISREG(entry_stat.st_mode)
                or not obsidian.recognized_note_rel(rel)
            ):
                raise _adoption_refusal(dest_aos, rel)
            if entry_stat.st_nlink != 1:
                raise _hardlink_refusal(dest_aos, rel, entry_stat.st_nlink)
            files.append((rel.as_posix(), entry_stat.st_size))
            stats[rel.as_posix()] = entry_stat
    files.sort()
    dirs.sort()
    return files, dirs, has_sentinel, stats


def _rescan_dest_aos_pinned(
    target: ExportTarget, dest_fd: int, linked, staging_fd: int | None
) -> tuple[
    list[tuple[str, int]], list[str], bool, str, dict[str, os.stat_result]
]:
    """Descriptor-anchored pre-promotion rescan of the live AOS: the walk
    (os.fwalk with dir_fd), every lstat, and every content read run
    relative to the PINNED destination descriptor, so a concurrent
    pathname swap cannot divert what the base-snapshot comparison
    actually inspects. Applies the same full-ownership rules as
    _scan_dest_aos and returns the length-framed content hash of the
    bytes actually read plus each entity DIRECTORY's inspected identity
    (the final hardlink verification must reach the live files through
    exactly these directories). Exactly one extra hardlink is tolerated
    per file — the hardlink this run itself staged (proven through the
    pinned staging descriptor), and only for a rel the build RECORDED as
    intentionally linked; link count alone never implies ownership."""
    dest_aos = target.dest_aos
    top = obsidian.AOS_SUBDIR
    files: list[tuple[str, int]] = []
    dirs: list[str] = []
    dir_stats: dict[str, os.stat_result] = {}
    has_sentinel = False
    contents: list[tuple[str, bytes]] = []
    root_dev = os.lstat(top, dir_fd=dest_fd).st_dev
    for dirpath, dirnames, filenames, dirfd in os.fwalk(
        top, dir_fd=dest_fd, follow_symlinks=False, onerror=_raise_walk_error
    ):
        base_rel = "" if dirpath == top else dirpath[len(top) + 1 :]
        kept = []
        for name in sorted(dirnames):
            rel_str = f"{base_rel}/{name}" if base_rel else name
            rel = Path(rel_str)
            entry_stat = os.lstat(name, dir_fd=dirfd)
            if entry_stat.st_dev != root_dev or _ismount_probe(
                dest_aos / rel_str
            ):
                raise _mount_refusal(dest_aos, rel)
            if name == OWNER_SENTINEL_NAME and not base_rel:
                if not stat.S_ISDIR(entry_stat.st_mode):
                    raise _adoption_refusal(dest_aos, rel)
                sentinel_fd = _open_dir_nofollow(name, dirfd)
                try:
                    inside = sorted(os.listdir(sentinel_fd))
                finally:
                    os.close(sentinel_fd)
                if inside:
                    raise _adoption_refusal(dest_aos, rel / inside[0])
                has_sentinel = True
                continue  # pruned: excluded from dirs and note counts
            if (
                name.startswith(".")
                or stat.S_ISLNK(entry_stat.st_mode)
                or not _recognized_dir_rel(rel)
            ):
                raise _adoption_refusal(dest_aos, rel)
            kept.append(name)
            dirs.append(rel_str)
            dir_stats[rel_str] = entry_stat
        dirnames[:] = kept
        for name in sorted(filenames):
            rel_str = f"{base_rel}/{name}" if base_rel else name
            rel = Path(rel_str)
            entry_stat = os.lstat(name, dir_fd=dirfd)
            if entry_stat.st_dev != root_dev:
                raise _mount_refusal(dest_aos, rel)
            if (
                name.startswith(".")
                or not stat.S_ISREG(entry_stat.st_mode)
                or not obsidian.recognized_note_rel(rel)
            ):
                raise _adoption_refusal(dest_aos, rel)
            expected_link = linked is None or rel_str in linked
            if entry_stat.st_nlink != 1 and not (
                expected_link
                and _staging_alias_only(entry_stat, staging_fd, rel)
            ):
                raise _hardlink_refusal(dest_aos, rel, entry_stat.st_nlink)
            files.append((rel_str, entry_stat.st_size))
            contents.append(
                (rel_str, _read_vetted_file(name, dirfd, rel_str, entry_stat))
            )
    files.sort()
    dirs.sort()
    digest = hashlib.sha256()
    for rel_str, data in sorted(contents):
        _hash_entry(digest, rel_str, data)
    return files, dirs, has_sentinel, digest.hexdigest(), dir_stats


# ---------------------------------------------------------------------------
# Plan


@dataclass
class ExportPlan:
    target: ExportTarget
    source: Path
    creates: list[tuple[str, int]]    # (posix relpath, source bytes)
    updates: list[tuple[str, int]]    # (posix relpath, source bytes)
    deletes: list[tuple[str, int]]    # (posix relpath, destination bytes)
    unchanged: list[tuple[str, int]]  # (posix relpath, source bytes)
    source_dirs: list[str]
    dest_dirs: list[str]
    #: Exact destination base snapshot at plan time. The pre-promotion
    #: recheck requires the destination to still match it in full:
    #: existence, directory identity, directory set, file set with sizes,
    #: sentinel presence, and the length-framed content hash.
    base_exists: bool
    base_stat: os.stat_result | None
    base_files: list[tuple[str, int]]
    base_dirs: list[str]
    base_sentinel: bool
    base_hash: str | None
    #: rel -> destination identity inspected by the plan-time scan. The
    #: staging build may reuse an unchanged file by hardlink ONLY from
    #: an inode that still matches this record (C2).
    base_identity: dict[str, os.stat_result] = field(default_factory=dict)
    #: rel -> SOURCE identity inspected by the plan-time source scan.
    #: The staging build may copy ONLY from an inode that still matches
    #: this record, opened through the pinned source-root descriptor —
    #: never from a re-resolved source pathname (C8).
    source_identity: dict[str, os.stat_result] = field(default_factory=dict)
    #: Identity of the resolved source AOS root at plan time; the build
    #: pins the source root against it for the complete staging build.
    source_root_stat: os.stat_result | None = None

    @property
    def note_total(self) -> int:
        return len(self.creates) + len(self.updates) + len(self.unchanged)

    @property
    def dir_creates(self) -> list[str]:
        """Directories the export will create (sorted: source_dirs and
        dest_dirs are sorted inventories)."""
        dest = set(self.dest_dirs)
        return [rel for rel in self.source_dirs if rel not in dest]

    @property
    def dir_deletes(self) -> list[str]:
        """Directories the export will delete (sorted)."""
        src = set(self.source_dirs)
        return [rel for rel in self.dest_dirs if rel not in src]

    @property
    def is_noop(self) -> bool:
        return (
            not self.creates
            and not self.updates
            and not self.deletes
            and self.source_dirs == self.dest_dirs
        )


def _refuse_stale(target: ExportTarget) -> None:
    # _lstat_or_absent, not lexists: an uninspectable STG/PREV (EIO,
    # EACCES, ...) refuses instead of reading as a clean absence.
    if _lstat_or_absent(target.staging) is not None:
        raise AosError(
            f"Refusing to export: staging {target.staging} already exists "
            "(interrupted or concurrent export); if no other export is "
            "running, remove it and rerun."
        )
    if _lstat_or_absent(target.previous) is not None:
        raise AosError(
            f"Refusing to export: previous generation {target.previous} "
            f"exists from an interrupted export. If {target.dest_aos} "
            f"exists, remove {target.previous} and rerun; if "
            f"{target.dest_aos} is missing, rename {target.previous} back "
            f"to {target.dest_aos} first. See TROUBLESHOOTING.md."
        )
    # A leftover quarantine name marks an interrupted cleanup: the tree
    # that was being deleted (or a retained replacement) may still sit
    # there. Names only — the listing never reads any child's content —
    # and an unlistable PATH fails closed like every other state probe.
    try:
        entries = os.listdir(target.dest_root)
    except OSError as exc:
        raise AosError(
            f"Refusing to export: cannot inspect {target.dest_root} "
            f"({exc}); fix the cause and rerun."
        )
    stale = sorted(e for e in entries if e.startswith(CLEANUP_PREFIX))
    if stale:
        raise AosError(
            f"Refusing to export: leftover cleanup entry "
            f"{target.dest_root / stale[0]} exists from an interrupted "
            "export cleanup; inspect it (it may hold a retained tree), "
            "remove it, and rerun. See TROUBLESHOOTING.md."
        )


def compute_plan(aos_dir: Path, target: ExportTarget) -> ExportPlan:
    try:
        return _compute_plan(aos_dir, target)
    except AosError:
        raise
    except OSError as exc:
        # Planning is read-only; a real OS error (unreadable note, vanished
        # tree) surfaces verbatim inside the one-line refusal.
        raise AosError(
            f"Export failed while planning ({exc}); destination untouched. "
            "Fix the cause and rerun."
        )


def _compute_plan(aos_dir: Path, target: ExportTarget) -> ExportPlan:
    # check_destination's inventory predates the mirror regeneration (its
    # gate must refuse before any local work); the plan itself is built
    # from a FRESH destination scan, so nothing that appeared meanwhile
    # can be missing from the plan and silently swept by the swap.
    _refresh_destination(aos_dir, target)
    source = obsidian.vault_aos_dir(aos_dir).resolve()
    source_root_stat = os.stat(source)
    src_files, src_dirs, src_stats = _scan_source(source)
    _check_representability(
        [rel for rel, _ in src_files] + list(src_dirs)
    )
    dst_files, dst_dirs = target.dest_files, target.dest_dirs
    src_sizes = dict(src_files)
    dst_sizes = dict(dst_files)
    # Read each destination file at most ONCE: the same bytes feed both the
    # size-then-byte change comparison and the base-snapshot content hash
    # (the recheck's plan-time expected value), instead of reading the tree
    # twice per run. Every read is a vetted descriptor-relative read (C4)
    # proven against the identity the adoption scan inspected — an entry
    # swapped between scan and read refuses instead of feeding external or
    # non-regular content into the plan.
    base_exists = target.dest_aos_stat is not None
    dst_bytes: dict[str, bytes] = {}
    base_hash = None
    base_identity = dict(target.dest_file_stats)
    if base_exists:
        digest = hashlib.sha256()
        dest_fd = _open_tree_root_pinned(
            target.dest_aos, target.dest_aos_stat
        )
        try:
            for rel, _ in dst_files:
                data = _read_rel_vetted(
                    dest_fd, rel, target.dest_aos, base_identity[rel]
                )
                dst_bytes[rel] = data
                _hash_entry(digest, rel, data)
        finally:
            os.close(dest_fd)
        base_hash = digest.hexdigest()
    creates, updates, unchanged = [], [], []
    source_fd = _open_tree_root_pinned(source, source_root_stat)
    try:
        for rel, size in src_files:
            if rel not in dst_sizes:
                creates.append((rel, size))
            elif size != dst_sizes[rel] or (
                _read_rel_vetted(source_fd, rel, source, src_stats[rel])
                != dst_bytes[rel]
            ):
                updates.append((rel, size))
            else:
                unchanged.append((rel, size))
    finally:
        os.close(source_fd)
    deletes = [
        (rel, size) for rel, size in dst_files if rel not in src_sizes
    ]
    return ExportPlan(
        target=target,
        source=source,
        creates=creates,
        updates=updates,
        deletes=deletes,
        unchanged=unchanged,
        source_dirs=src_dirs,
        dest_dirs=dst_dirs,
        base_exists=base_exists,
        base_stat=target.dest_aos_stat,
        base_files=list(dst_files),
        base_dirs=list(dst_dirs),
        base_sentinel=target.dest_sentinel,
        base_hash=base_hash,
        base_identity=base_identity,
        source_identity=dict(src_stats),
        source_root_stat=source_root_stat,
    )


# ---------------------------------------------------------------------------
# Staging build, validation, promotion


def _fsync_dest_root(dest_fd: int) -> None:
    """PATH-level durability point: fsync the PINNED destination-root
    descriptor (same skip policy as every directory fsync). Every PATH
    fsync goes through here — the descriptor the apply opened and
    identity-checked is what gets synced, never a fresh resolution of the
    PATH pathname."""
    _fsync_dir_fd(dest_fd)


def _fsync_dir_fd(fd: int) -> None:
    """fsync an already-open directory descriptor with the contract's
    skip policy: recognized unsupported-operation errnos are skipped
    (9P/DrvFS reject directory fsync); anything else propagates as an
    integrity failure."""
    try:
        os.fsync(fd)
    except OSError as exc:
        if exc.errno in DIR_FSYNC_SKIP_ERRNOS:
            return
        raise


def _open_dir_nofollow(name: str, dir_fd: int) -> int:
    """Open a child directory relative to `dir_fd` WITHOUT following a
    symlink at the final component. A racer that swaps a just-created
    staging subdirectory for a symlink is rejected here (ELOOP) instead of
    being followed out of the staging tree."""
    return os.open(
        name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd
    )


def _ismount_probe(path: Path) -> bool:
    """Additive best-effort pathname mount-point probe. The authoritative
    mount detection is the descriptor-anchored st_dev comparison beside
    every call site; this probe can only ADD refusals, so an error
    inspecting the pathname reads as 'no extra evidence', never as
    clearance."""
    try:
        return os.path.ismount(path)
    except OSError:
        return False


def _read_vetted_file(
    name: str, dirfd: int, rel, expect: os.stat_result | None = None
) -> bytes:
    """THE shared vetted reader for every enforcement-critical file read
    (plan comparison, base-snapshot hashing, source scanning/hashing,
    staging and destination rescans). Opens `name` relative to its pinned
    directory descriptor with O_RDONLY plus O_NOFOLLOW and O_NONBLOCK
    where available, fstats the OPENED descriptor, requires a regular
    file, requires identity equality with `expect` when the caller
    inspected the entry beforehand, reads only from the descriptor, and
    re-fstats after the read: an entry raced into the name (a symlink
    would divert the read; a FIFO would hang a plain open), a wrong
    inode, or a file whose size changed while being read all refuse with
    an actionable error instead of feeding unvetted bytes onward."""
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        fd = os.open(name, flags, dir_fd=dirfd)
    except FileNotFoundError:
        raise AosError(
            f"Refusing to export: {rel} disappeared while being read; "
            "rerun."
        )
    except OSError as exc:
        raise AosError(
            f"Refusing to export: cannot read {rel} ({exc}); fix the "
            "cause and rerun."
        )
    try:
        pre_stat = os.fstat(fd)
        if not stat.S_ISREG(pre_stat.st_mode) or (
            expect is not None and not os.path.samestat(pre_stat, expect)
        ):
            raise AosError(
                f"Refusing to export: {rel} changed while being read; "
                "rerun."
            )
        chunks = []
        while True:
            chunk = os.read(fd, 1 << 16)
            if not chunk:
                break
            chunks.append(chunk)
        data = b"".join(chunks)
        post_stat = os.fstat(fd)
        if (
            not stat.S_ISREG(post_stat.st_mode)
            or not os.path.samestat(post_stat, pre_stat)
            or post_stat.st_size != pre_stat.st_size
            or len(data) != pre_stat.st_size
        ):
            raise AosError(
                f"Refusing to export: {rel} changed while being read; "
                "rerun."
            )
        return data
    finally:
        os.close(fd)


def _open_tree_root_pinned(
    path: Path, expect: os.stat_result | None = None
) -> int:
    """Pin a tree root for enforcement-critical reads: O_RDONLY plus
    O_DIRECTORY and O_NOFOLLOW where available, with an optional fstat
    identity check against the stat recorded when the tree was
    inspected. Every read then happens relative to this descriptor —
    never through a fresh resolution of the mutable pathname."""
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise AosError(
            f"Refusing to export: cannot open {path} ({exc}); fix the "
            "cause and rerun."
        )
    try:
        if expect is not None and not os.path.samestat(
            os.fstat(fd), expect
        ):
            raise AosError(
                f"Refusing to export: {path} was replaced during export; "
                "rerun."
            )
    except BaseException:
        os.close(fd)
        raise
    return fd


def _read_rel_vetted(
    root_fd: int,
    rel: str,
    display_root: Path,
    expect: os.stat_result | None = None,
) -> bytes:
    """Vetted read of a note relpath (depth bounded at two by the
    recognizer) relative to a pinned tree-root descriptor: the entity
    directory is opened O_DIRECTORY|O_NOFOLLOW relative to the root and
    the file relative to that — the mutable pathname is never reopened,
    so a swapped entity directory refuses (ELOOP) instead of diverting
    the read."""
    entity, base = _split_rel(rel)
    if entity is None:
        return _read_vetted_file(base, root_fd, display_root / rel, expect)
    try:
        entity_fd = _open_dir_nofollow(entity, root_fd)
    except OSError as exc:
        raise AosError(
            f"Refusing to export: cannot open {display_root / entity} "
            f"({exc}); fix the cause and rerun."
        )
    try:
        return _read_vetted_file(
            base, entity_fd, display_root / rel, expect
        )
    finally:
        os.close(entity_fd)


def _hash_source_tree(
    source: Path,
    src_files: list[tuple[str, int]],
    src_stats: dict[str, os.stat_result],
) -> str:
    """Length-framed content hash of the source mirror, read entirely
    through a pinned source-root descriptor with per-file identity
    checks against the scan that produced `src_files` (C4: source
    verification never uses pathname reads)."""
    digest = hashlib.sha256()
    source_fd = _open_tree_root_pinned(source)
    try:
        for rel, _ in src_files:
            _hash_entry(
                digest,
                rel,
                _read_rel_vetted(source_fd, rel, source, src_stats[rel]),
            )
    finally:
        os.close(source_fd)
    return digest.hexdigest()


def _open_copy_source_dir(
    entity: str | None,
    source_fd: int,
    src_entity_fds: dict[str, int],
    source: Path,
) -> int:
    """Descriptor chain for payload-copy source opens (C8), the source-
    side analogue of _open_link_source_dir: the pinned source-root
    descriptor -> entity directory opened O_DIRECTORY|O_NOFOLLOW
    relative to it (cached per entity for the build; the caller closes
    them). The mutable source pathname is never re-resolved, so a
    symlink raced into an entity component refuses (ELOOP) instead of
    redirecting the read outside the source mirror."""
    if entity is None:
        return source_fd
    if entity not in src_entity_fds:
        try:
            src_entity_fds[entity] = _open_dir_nofollow(entity, source_fd)
        except OSError as exc:
            raise AosError(
                f"Refusing to export: cannot open {source / entity} "
                f"without following symlinks ({exc}); rerun sync."
            )
    return src_entity_fds[entity]


def _copy_into_staging(
    plan: ExportPlan,
    source_fd: int,
    src_entity_fds: dict[str, int],
    rel: str,
    name: str,
    dir_fd: int,
) -> int:
    """Copy the source note `rel` to `name` inside the directory `dir_fd`
    refers to, reading ONLY through the pinned source-root descriptor
    (C8): the entity directory opens O_DIRECTORY|O_NOFOLLOW relative to
    `source_fd`, the basename opens O_RDONLY|O_NOFOLLOW|O_NONBLOCK
    (where available) relative to that, and the opened descriptor must
    be a regular file with exactly the identity the plan-time source
    scan recorded — a symlink, FIFO, or replacement inode raced into ANY
    component refuses instead of diverting or BLOCKING the read (a plain
    open of a writer-less FIFO hangs forever); no absolute source
    pathname is ever opened. The source is fstat-checked again after the
    copy (identity and size stability). O_CREAT|O_EXCL|O_NOFOLLOW plus
    the directory descriptor pin the write to the real staged directory:
    a symlink raced into `name`'s place fails (EEXIST) rather than
    redirecting the bytes elsewhere. Returns the payload size actually
    written (fstat of the flushed and fsynced staged file), never a size
    inferred from the plan."""
    display = plan.source / rel
    entity, base = _split_rel(rel)
    src_dir_fd = _open_copy_source_dir(
        entity, source_fd, src_entity_fds, plan.source
    )
    expect = plan.source_identity.get(rel)
    src_flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    src_fd = os.open(base, src_flags, dir_fd=src_dir_fd)
    try:
        # os.fdopen does NOT close the descriptor it was handed when it
        # fails (e.g. IsADirectoryError for a directory raced onto the
        # note's name — an O_RDONLY open of a directory succeeds).
        src_fh = os.fdopen(src_fd, "rb")
    except BaseException:
        os.close(src_fd)
        raise
    with src_fh:
        pre_stat = os.fstat(src_fh.fileno())
        if (
            not stat.S_ISREG(pre_stat.st_mode)
            or expect is None
            or not os.path.samestat(pre_stat, expect)
        ):
            raise AosError(
                f"Refusing to export: {display} changed while being "
                "copied; rerun."
            )
        dst_fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o644,
            dir_fd=dir_fd,
        )
        with os.fdopen(dst_fd, "wb") as dst_fh:
            shutil.copyfileobj(src_fh, dst_fh)
            dst_fh.flush()
            os.fsync(dst_fh.fileno())
            written = os.fstat(dst_fh.fileno()).st_size
        post_stat = os.fstat(src_fh.fileno())
        if (
            not stat.S_ISREG(post_stat.st_mode)
            or not os.path.samestat(post_stat, pre_stat)
            or post_stat.st_size != pre_stat.st_size
            or written != pre_stat.st_size
        ):
            raise AosError(
                f"Refusing to export: {display} changed while being "
                "copied; rerun."
            )
        return written


def _split_rel(rel: str) -> tuple[str | None, str]:
    """(entity dir, filename) for a note relpath. Top-level notes
    (`Home.md`, index notes) have no entity dir — they live at the staging
    root. The recognizer bounds depth at two, so there is never a deeper
    split."""
    entity, sep, base = rel.partition("/")
    return (entity, base) if sep else (None, rel)


@dataclass
class _BuildStats:
    """What the staging build ACTUALLY did (C5): per-file outcomes and
    payload bytes measured at the write, never inferred from the plan.
    `linked` maps each rel INTENTIONALLY reused by hardlink to the
    (st_dev, st_ino) identity of the staged link — validation must never
    infer link ownership from link count alone."""

    linked: dict[str, tuple[int, int]] = field(default_factory=dict)
    created_files: int = 0
    updated_files: int = 0
    unchanged_hardlinked_files: int = 0
    unchanged_fallback_copied_files: int = 0
    payload_bytes_written: int = 0


def _open_link_source_dir(
    entity: str | None, dest_fd: int, aos_state: dict, dest_aos: Path
) -> int:
    """Descriptor chain for hardlink-source opens (C2): PATH's pinned
    descriptor -> AOS opened O_DIRECTORY|O_NOFOLLOW relative to it ->
    entity directory opened O_DIRECTORY|O_NOFOLLOW relative to AOS.
    Descriptors are cached in `aos_state` for the build and closed by
    _close_link_source_dirs; the mutable PATH pathname is never
    re-resolved. A symlink raced into any component refuses (ELOOP)."""
    try:
        if "aos_fd" not in aos_state:
            aos_state["aos_fd"] = _open_dir_nofollow(
                obsidian.AOS_SUBDIR, dest_fd
            )
        if entity is None:
            return aos_state["aos_fd"]
        entity_fds = aos_state.setdefault("entity_fds", {})
        if entity not in entity_fds:
            entity_fds[entity] = _open_dir_nofollow(
                entity, aos_state["aos_fd"]
            )
        return entity_fds[entity]
    except OSError as exc:
        raise _destination_changed(
            f"cannot open {dest_aos if entity is None else dest_aos / entity}"
            f" for hardlink reuse: {exc}"
        )


def _close_link_source_dirs(aos_state: dict) -> None:
    for fd in aos_state.pop("entity_fds", {}).values():
        os.close(fd)
    if "aos_fd" in aos_state:
        os.close(aos_state.pop("aos_fd"))


def _build_staging(
    plan: ExportPlan, staging_fd: int, dest_fd: int
) -> _BuildStats:
    """Assemble the complete next generation inside the (fresh) staging
    directory: the ownership sentinel, then hardlink unchanged destination
    files and copy changed/new files from the source. Deleted files are
    simply not staged. Returns the _BuildStats record of what was
    actually done.

    Every entity directory is created relative to the pinned staging-root
    descriptor and immediately reopened O_NOFOLLOW into its own descriptor;
    every file is created relative to that descriptor. A concurrent
    same-user process therefore cannot swap a staging subdirectory for a
    symlink and divert a staged write outside PATH/AOS+STG+PREV — the
    swap is refused at open (ELOOP) or file-create (EEXIST), never
    followed. This closes the one build-phase escape the recheck cannot
    see (it runs only after the build completes).

    Hardlink reuse is fully descriptor-anchored (C2): the source is
    opened through the pinned destination descriptor (PATH fd -> AOS fd
    -> entity fd, each O_DIRECTORY|O_NOFOLLOW), the source file must be
    a regular file whose identity equals the one the plan-time scan
    recorded, os.link runs with src_dir_fd AND dst_dir_fd and
    follow_symlinks=False, and the staged link is verified to be that
    exact inode afterwards. The mutable PATH/AOS/rel pathname is never
    used as the link source, so a replaced PATH can never have a file's
    link count changed by this build.

    Payload copies are equally anchored on the SOURCE side (C8): the
    source AOS root is pinned here — O_DIRECTORY|O_NOFOLLOW, identity-
    checked against the plan's recorded source-root identity — and held
    for the COMPLETE build; every copy (creates, updates, AND unchanged
    fallback copies when hardlinks are unsupported) reads through that
    descriptor chain with per-file identity proofs. A replaced source
    root or a symlink-swapped source entity directory refuses instead
    of feeding external bytes into staging.

    Durability order (all under the directory-fsync skip policy): every
    copied file is flushed+fsynced at write; then the staging root, the
    ownership-sentinel directory, and every entity directory are fsynced
    through their own pinned descriptors."""
    target = plan.target
    source_fd = _open_tree_root_pinned(plan.source, plan.source_root_stat)
    src_entity_fds: dict[str, int] = {}
    try:
        os.mkdir(OWNER_SENTINEL_NAME, dir_fd=staging_fd)
        sentinel_fd = _open_dir_nofollow(OWNER_SENTINEL_NAME, staging_fd)
    except BaseException:
        for fd in src_entity_fds.values():
            os.close(fd)
        os.close(source_fd)
        raise
    entity_fds: dict[str, int] = {}
    stats = _BuildStats()
    creates = {rel for rel, _ in plan.creates}
    updates = {rel for rel, _ in plan.updates}
    changed = creates | updates
    aos_state: dict = {}
    try:
        for rel in plan.source_dirs:
            os.mkdir(rel, dir_fd=staging_fd)
            entity_fds[rel] = _open_dir_nofollow(rel, staging_fd)
        links_supported = True
        for rel, _ in sorted(plan.creates + plan.updates + plan.unchanged):
            entity, base = _split_rel(rel)
            dir_fd = entity_fds[entity] if entity is not None else staging_fd
            if rel not in changed and links_supported:
                src_dir_fd = _open_link_source_dir(
                    entity, dest_fd, aos_state, target.dest_aos
                )
                expected = plan.base_identity.get(rel)
                src_stat = _lstat_or_absent(
                    base, dir_fd=src_dir_fd, display=target.dest_aos / rel
                )
                if (
                    expected is None
                    or src_stat is None
                    or not stat.S_ISREG(src_stat.st_mode)
                    or not os.path.samestat(src_stat, expected)
                ):
                    raise _destination_changed(
                        f"{target.dest_aos / rel} is no longer the file "
                        "the plan inspected; hardlink reuse refused"
                    )
                try:
                    os.link(
                        base,
                        base,
                        src_dir_fd=src_dir_fd,
                        dst_dir_fd=dir_fd,
                        follow_symlinks=False,
                    )
                except OSError as exc:
                    if exc.errno not in LINK_FALLBACK_ERRNOS:
                        raise
                    links_supported = False
                else:
                    # Identity AND type: a swap between the check and the
                    # link can hand the freed inode NUMBER to a new entry
                    # (inode recycling), so samestat alone is not proof.
                    link_stat = os.lstat(base, dir_fd=dir_fd)
                    if not stat.S_ISREG(
                        link_stat.st_mode
                    ) or not os.path.samestat(link_stat, expected):
                        raise _destination_changed(
                            f"{target.dest_aos / rel} was replaced while "
                            "being reused by hardlink"
                        )
                    stats.linked[rel] = (link_stat.st_dev, link_stat.st_ino)
                    stats.unchanged_hardlinked_files += 1
                    continue
            written = _copy_into_staging(
                plan, source_fd, src_entity_fds, rel, base, dir_fd
            )
            stats.payload_bytes_written += written
            if rel in creates:
                stats.created_files += 1
            elif rel in updates:
                stats.updated_files += 1
            else:
                stats.unchanged_fallback_copied_files += 1
        _fsync_dir_fd(staging_fd)
        _fsync_dir_fd(sentinel_fd)
        for fd in entity_fds.values():
            _fsync_dir_fd(fd)
    finally:
        _close_link_source_dirs(aos_state)
        for fd in src_entity_fds.values():
            os.close(fd)
        os.close(source_fd)
        os.close(sentinel_fd)
        for fd in entity_fds.values():
            os.close(fd)
    return stats


def _scan_staging(
    staging_fd: int, display: Path
) -> tuple[list[tuple[str, os.stat_result, bytes]], list[str], bool]:
    """Descriptor-anchored staging inventory: the walk (os.fwalk with
    dir_fd), every lstat, and every content read are relative to the
    PINNED staging descriptor, so a concurrent pathname swap cannot
    divert what validation or the final verification actually inspects.
    Every entry must be a real directory or a regular file — symlinks
    and special files refuse before any content read (a staged symlink
    would smuggle out-of-tree content through promotion even when the
    linked bytes compare equal). Cross-device subtrees refuse via the
    descriptor-anchored st_dev comparison (authoritative); the additive
    pathname mount probe can only ADD refusals. Same-filesystem bind
    mounts are indistinguishable from plain directories with stdlib stat
    checks — documented limitation. `display` names entries in messages
    and feeds the additive probe only."""
    files: list[tuple[str, os.stat_result, bytes]] = []
    dirs: list[str] = []
    has_sentinel = False
    root_dev = os.fstat(staging_fd).st_dev
    for dirpath, dirnames, filenames, dirfd in os.fwalk(
        ".",
        dir_fd=staging_fd,
        follow_symlinks=False,
        onerror=_raise_walk_error,
    ):
        base_rel = "" if dirpath == "." else dirpath[2:]
        kept = []
        for name in sorted(dirnames):
            rel = f"{base_rel}/{name}" if base_rel else name
            entry_stat = os.lstat(name, dir_fd=dirfd)
            if entry_stat.st_dev != root_dev or _ismount_probe(
                display / rel
            ):
                raise _validation_failure(
                    f"{rel}: mounted or cross-device subtree inside staging"
                )
            if name == OWNER_SENTINEL_NAME and not base_rel:
                if not stat.S_ISDIR(entry_stat.st_mode):
                    raise _validation_failure(
                        f"{rel}: ownership sentinel is not a real directory"
                    )
                sentinel_fd = _open_dir_nofollow(name, dirfd)
                try:
                    sentinel_entries = os.listdir(sentinel_fd)
                finally:
                    os.close(sentinel_fd)
                if sentinel_entries:
                    raise _validation_failure(
                        f"{rel}: ownership sentinel is not empty"
                    )
                has_sentinel = True
                continue
            if not stat.S_ISDIR(entry_stat.st_mode):
                raise _validation_failure(
                    f"{rel}: staged entry is not a real directory"
                )
            kept.append(name)
            dirs.append(rel)
        dirnames[:] = kept
        for name in sorted(filenames):
            rel = f"{base_rel}/{name}" if base_rel else name
            entry_stat = os.lstat(name, dir_fd=dirfd)
            if entry_stat.st_dev != root_dev:
                raise _validation_failure(
                    f"{rel}: mounted or cross-device subtree inside staging"
                )
            if not stat.S_ISREG(entry_stat.st_mode):
                raise _validation_failure(
                    f"{rel}: staged entry is not a regular file"
                )
            files.append(
                (rel, entry_stat, _read_vetted_file(name, dirfd, rel, entry_stat))
            )
    files.sort(key=lambda item: item[0])
    dirs.sort()
    return files, dirs, has_sentinel


def _validation_failure(detail: str) -> AosError:
    return AosError(
        f"Export validation failed ({detail}); destination left untouched. "
        "Fix the cause and rerun."
    )


_TREE_MISMATCH = "staged tree does not match the source (changed during export)"


@dataclass(frozen=True)
class StagingSnapshot:
    """Immutable record of the staged generation exactly as validated.
    The final pre-promotion verification requires the complete rescan of
    staging (and a fresh source scan) to equal it — promotion may only
    ever ship the bytes and relationships this snapshot blessed. `linked`
    maps each intentionally hardlinked rel to the (st_dev, st_ino)
    identity captured when the build created the link."""

    root_stat: os.stat_result
    sentinel: bool
    dirs: tuple[str, ...]
    files: tuple[tuple[str, int], ...]  # (posix relpath, size)
    content_hash: str
    linked: types.MappingProxyType


def _live_link_stat(
    target: ExportTarget,
    rel: str,
    aos_fd: int,
    aos_dirs: dict[str, os.stat_result],
    entity_fds: dict[str, int],
) -> os.stat_result | None:
    """lstat of the CURRENT AOS file for an intentionally linked rel,
    reached with NO unresolved intermediate component: the entity
    directory opens O_DIRECTORY|O_NOFOLLOW relative to the HELD verified
    AOS-root descriptor, must carry exactly the identity the pinned
    destination rescan recorded (cached per entity; the caller closes
    them), and the basename is lstat'ed relative to that descriptor —
    "AOS/<entity>/<file>" pathnames, whose intermediate components would
    follow a planted symlink, are never used. A moved-aside entity
    directory with a symlink back to it therefore refuses (ELOOP or
    identity mismatch) instead of verifying the hardlink through the
    external alias. Returns None when the file is absent; an
    uninspectable file refuses via _lstat_or_absent."""
    entity, base = _split_rel(rel)
    if entity is None:
        parent_fd = aos_fd
    else:
        if entity not in entity_fds:
            expected_dir = aos_dirs.get(entity)
            if expected_dir is None:
                raise _destination_changed(
                    f"{target.dest_aos / entity} was not part of the "
                    "verified destination"
                )
            try:
                fd = _open_dir_nofollow(entity, aos_fd)
            except FileNotFoundError:
                raise _destination_changed(
                    f"{target.dest_aos / entity} disappeared"
                )
            except OSError as exc:
                raise _destination_changed(
                    f"cannot open {target.dest_aos / entity} without "
                    f"following symlinks ({exc})"
                )
            try:
                if not os.path.samestat(os.fstat(fd), expected_dir):
                    raise _destination_changed(
                        f"{target.dest_aos / entity} was replaced"
                    )
            except BaseException:
                os.close(fd)
                raise
            entity_fds[entity] = fd
        parent_fd = entity_fds[entity]
    return _lstat_or_absent(
        base, dir_fd=parent_fd, display=target.dest_aos / rel
    )


def _check_staged_links(
    target: ExportTarget,
    stg_files: list[tuple[str, os.stat_result, bytes]],
    linked,
    *,
    against_live_aos: bool,
    aos_fd: int | None = None,
    aos_dirs: dict[str, os.stat_result] | None = None,
) -> None:
    """Hardlink-relationship invariant for every staged regular file:
    created, updated, and copied-unchanged files must have st_nlink == 1
    (a foreign alias would stay connected to the promoted generation);
    intentionally linked unchanged files must have st_nlink == 2 and the
    exact identity the build recorded — and, at the final verification
    (`against_live_aos`), still alias the corresponding CURRENT AOS
    file, which must itself carry no third link. The live side is probed
    through the HELD verified AOS-root descriptor and the entity-
    directory identities the pinned destination rescan recorded
    (_live_link_stat) — never through a pathname with unresolved
    intermediate components, so no external hardlink alias can survive
    promotion behind a symlinked entity directory. A staged-side
    violation is a validation failure; a live AOS file that vanished,
    was replaced, or gained an alias is a DESTINATION change (staging is
    intact — rerun computes a fresh plan). Ownership is proven by the
    build's own record, never inferred from link count."""
    staged_rels = {rel for rel, _, _ in stg_files}
    for rel in linked:
        if rel not in staged_rels:
            raise _validation_failure(
                f"{rel}: intentionally hardlinked file is missing from "
                "staging"
            )
    if against_live_aos and linked and aos_fd is None:
        raise _destination_changed(f"{target.dest_aos} disappeared")
    entity_fds: dict[str, int] = {}
    try:
        for rel, entry_stat, _ in stg_files:
            expected = linked.get(rel)
            if expected is None:
                if entry_stat.st_nlink != 1:
                    raise _validation_failure(
                        f"{rel}: staged file has {entry_stat.st_nlink} "
                        "hardlinks (expected 1); a foreign alias would stay "
                        "connected after promotion"
                    )
                continue
            if entry_stat.st_nlink != 2:
                raise _validation_failure(
                    f"{rel}: staged hardlink has {entry_stat.st_nlink} links "
                    "(expected exactly 2: the destination file and the "
                    "staged link)"
                )
            if (entry_stat.st_dev, entry_stat.st_ino) != expected:
                raise _validation_failure(
                    f"{rel}: staged hardlink identity changed during export"
                )
            if against_live_aos:
                live_stat = _live_link_stat(
                    target, rel, aos_fd, aos_dirs or {}, entity_fds
                )
                if live_stat is None:
                    raise _destination_changed(
                        f"{target.dest_aos / rel} disappeared"
                    )
                if not os.path.samestat(entry_stat, live_stat):
                    raise _destination_changed(
                        f"{target.dest_aos / rel} was replaced"
                    )
                if live_stat.st_nlink != 2:
                    raise _destination_changed(
                        f"{target.dest_aos / rel} was aliased outside "
                        "the export"
                    )
    finally:
        for fd in entity_fds.values():
            os.close(fd)


def _validate_staging(
    plan: ExportPlan,
    staging_fd: int,
    staging_stat: os.stat_result,
    linked: dict[str, tuple[int, int]],
) -> StagingSnapshot:
    """The staged generation must be byte-faithful to the source as it is
    NOW (a fresh re-scan — catches a mirror regenerated mid-copy), carry
    the ownership sentinel, satisfy the hardlink-relationship invariant,
    and satisfy the mirror invariants: UTF-8, LF-only, trailing newline,
    wikilinks resolving within the staged tree. The staging side is read
    entirely through the pinned staging descriptor. Returns the immutable
    StagingSnapshot the final pre-promotion verification re-checks."""
    stg_files, stg_dirs, stg_sentinel = _scan_staging(
        staging_fd, plan.target.staging
    )
    if not stg_sentinel:
        raise _validation_failure(
            f"staged tree lacks the ownership sentinel {OWNER_SENTINEL_NAME}"
        )
    _check_staged_links(
        plan.target, stg_files, linked, against_live_aos=False
    )
    src_files, src_dirs, src_stats = _scan_source(plan.source)
    if [(rel, st.st_size) for rel, st, _ in stg_files] != src_files or (
        stg_dirs != src_dirs
    ):
        raise _validation_failure(_TREE_MISMATCH)
    stems = {PurePosixPath(rel).stem for rel, _, _ in stg_files}
    staged_hash = hashlib.sha256()
    for rel, _, data in stg_files:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise _validation_failure(f"{rel}: not valid UTF-8")
        if b"\r" in data:
            raise _validation_failure(f"{rel}: contains CR bytes")
        if not data.endswith(b"\n"):
            raise _validation_failure(f"{rel}: missing trailing newline")
        for match in obsidian.WIKILINK_RE.finditer(text):
            link = match.group(1).strip()
            if link not in stems:
                raise _validation_failure(
                    f"{rel}: wikilink [[{link}]] does not resolve inside "
                    "the export"
                )
        _hash_entry(staged_hash, rel, data)
    source_hash = _hash_source_tree(plan.source, src_files, src_stats)
    if staged_hash.hexdigest() != source_hash:
        raise _validation_failure(_TREE_MISMATCH)
    return StagingSnapshot(
        root_stat=staging_stat,
        sentinel=stg_sentinel,
        dirs=tuple(stg_dirs),
        files=tuple((rel, st.st_size) for rel, st, _ in stg_files),
        content_hash=staged_hash.hexdigest(),
        linked=types.MappingProxyType(dict(linked)),
    )


def _verify_source_final(plan: ExportPlan, snapshot: StagingSnapshot) -> None:
    """Fresh SOURCE verification — step 1 of the final pre-promotion
    sequence, deliberately FIRST (C7): the source cannot be mutated
    through a staged hardlink, so its verification is the one a live
    destination write cannot invalidate after the fact; running it
    before the destination recheck and the final staging rescan keeps
    the staging content hash the LAST content verification before the
    renames. The current source must still be exactly the generation the
    snapshot blessed — a mirror regenerated after validation refuses."""
    src_files, src_dirs, src_stats = _scan_source(plan.source)
    if tuple(src_dirs) != snapshot.dirs or (
        tuple(src_files) != snapshot.files
    ):
        raise _validation_failure(_TREE_MISMATCH)
    source_hash = _hash_source_tree(plan.source, src_files, src_stats)
    if source_hash != snapshot.content_hash:
        raise _validation_failure(_TREE_MISMATCH)


def _verify_staging_final(
    plan: ExportPlan,
    staging_fd: int,
    staging_stat: os.stat_result,
    snapshot: StagingSnapshot,
    dest_fd: int,
    aos_fd: int | None,
    aos_dirs: dict[str, os.stat_result],
) -> None:
    """Complete re-verification of the staged generation immediately
    before the promotion renames — step 3, the LAST of the final
    sequence (fresh source verification first, full destination recheck
    second, this complete staging rescan third; C7): rescan the ENTIRE
    staging tree through the pinned staging descriptor and require exact
    equality with the validated snapshot (root identity, sentinel,
    directory set, file set with sizes, entry types, content hash, and
    the hardlink counts and identities — the live side probed through
    the HELD verified AOS-root descriptor and the recorded entity-
    directory identities, never through a pathname with unresolved
    intermediate components). It ends with a structural destination
    guard (PATH pathname identity, AOS root identity, PREV absence).
    After this function's staging scan, nothing reads or hashes content
    again: the only syscalls left before the renames are identity
    lstats (the live hardlink probes, the structural guard, the
    move-aside guard). The unobservable interval for STAGING content is
    therefore PER FILE: it begins when this rescan has read that file's
    bytes — the scan reads files in order, so earlier-scanned files
    carry the remainder of the scan in their window — and ends at the
    renames; no later pass widens it. A destination CONTENT change
    after the recheck is within the accepted window — except through
    intentionally hardlinked bytes, which this rescan's hash still
    covers up to each file's read."""
    target = plan.target
    try:
        stg_stat = _lstat_or_absent(
            STAGING_NAME, dir_fd=dest_fd, display=target.staging
        )
    except AosError as exc:
        raise _StagingCompromised(
            f"{exc} Staging {target.staging} was left in place; remove it "
            "after fixing the cause, then rerun."
        )
    if (
        stg_stat is None
        or stat.S_ISLNK(stg_stat.st_mode)
        or not stat.S_ISDIR(stg_stat.st_mode)
        or not os.path.samestat(stg_stat, staging_stat)
        or not os.path.samestat(stg_stat, snapshot.root_stat)
    ):
        raise _StagingCompromised(
            f"Refusing to export: staging {target.staging} was removed or "
            f"replaced during export (concurrent process?); "
            f"{target.dest_aos} is unchanged. Ensure {target.staging} does "
            "not exist, then rerun."
        )
    stg_files, stg_dirs, stg_sentinel = _scan_staging(
        staging_fd, target.staging
    )
    if stg_sentinel != snapshot.sentinel:
        raise _validation_failure(
            "staged generation changed after validation: the ownership "
            "sentinel changed"
        )
    if tuple(stg_dirs) != snapshot.dirs:
        raise _validation_failure(
            "staged generation changed after validation: the directory "
            "set changed"
        )
    if tuple((rel, st.st_size) for rel, st, _ in stg_files) != snapshot.files:
        raise _validation_failure(
            "staged generation changed after validation: the file set or "
            "file sizes changed"
        )
    _check_staged_links(
        target,
        stg_files,
        snapshot.linked,
        against_live_aos=True,
        aos_fd=aos_fd,
        aos_dirs=aos_dirs,
    )
    staged_hash = hashlib.sha256()
    for rel, _, data in stg_files:
        _hash_entry(staged_hash, rel, data)
    if staged_hash.hexdigest() != snapshot.content_hash:
        raise _validation_failure(
            "staged generation changed after validation: file content "
            "changed"
        )
    # Structural destination guard AFTER the final staging verification:
    # the pathname must still reach the pinned PATH, PREV must still be
    # absent, and the AOS root must still be the plan's base directory.
    # Identity lstats only — no content is read after the final hash.
    try:
        root_stat = os.lstat(target.dest_root)
    except OSError as exc:
        raise _destination_changed(f"cannot stat {target.dest_root}: {exc}")
    if stat.S_ISLNK(root_stat.st_mode) or not os.path.samestat(
        root_stat, target.dest_root_stat
    ):
        raise _destination_changed(f"{target.dest_root} was replaced")
    if (
        _lstat_or_absent(
            PREVIOUS_NAME, dir_fd=dest_fd, display=target.previous
        )
        is not None
    ):
        raise _destination_changed(f"{target.previous} appeared")
    live_stat = _lstat_or_absent(
        obsidian.AOS_SUBDIR, dir_fd=dest_fd, display=target.dest_aos
    )
    if plan.base_exists:
        if live_stat is None or not os.path.samestat(
            live_stat, plan.base_stat
        ):
            raise _destination_changed(f"{target.dest_aos} was replaced")
    elif live_stat is not None:
        raise _destination_changed(f"{target.dest_aos} appeared")


def _hash_entry(digest, rel: str, data: bytes) -> None:
    """Length-framed entry hash: without the size, bytes could migrate
    between adjacent files in the concatenated stream and still collide."""
    digest.update(rel.encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(len(data)).encode("ascii"))
    digest.update(b"\0")
    digest.update(data)


def _mounted_subtree_pinned(root_fd: int, display: Path) -> Path | None:
    """First mounted or cross-device entry beneath the PINNED cleanup
    root descriptor, else None. The walk and every lstat are anchored to
    `root_fd` (os.fwalk with dir_fd) so the sweep inspects exactly the
    tree the descriptor-relative delete would recurse into — the mutable
    root pathname is never reopened; the additive pathname mount probe
    (via `display`) can only ADD refusals. Standard-library limitation:
    a bind mount of the SAME filesystem has the same st_dev and is
    invisible to os.path.ismount, so it cannot be distinguished portably
    from a plain directory. Raises OSError when the tree cannot be
    inspected — never inspected means never deleted."""
    root_dev = os.fstat(root_fd).st_dev
    for dirpath, dirnames, filenames, dirfd in os.fwalk(
        ".", dir_fd=root_fd, follow_symlinks=False, onerror=_raise_walk_error
    ):
        base_rel = "" if dirpath == "." else dirpath[2:]
        for entry in dirnames:
            rel = f"{base_rel}/{entry}" if base_rel else entry
            entry_stat = os.lstat(entry, dir_fd=dirfd)
            if entry_stat.st_dev != root_dev or _ismount_probe(
                display / rel
            ):
                return display / rel
        for entry in filenames:
            rel = f"{base_rel}/{entry}" if base_rel else entry
            if os.lstat(entry, dir_fd=dirfd).st_dev != root_dev:
                return display / rel
    return None


def _fresh_quarantine_name(dir_fd: int, display_dir: Path) -> str:
    """A private single-use cleanup name (CLEANUP_PREFIX + pid + a
    process-wide monotone counter) that is currently free inside the
    directory `dir_fd` refers to. The freshness probe narrows — but
    cannot close — the window in which a racer occupies the chosen name
    before the quarantine rename (the standard library exposes no
    no-replace rename): a TYPE-COMPATIBLE entry raced onto it in that
    gap is overwritten by the rename — an empty directory when a
    directory is being quarantined, a regular file or symlink when a
    regular file is; an incompatible occupant makes the rename fail
    loudly. An uninspectable candidate name is skipped, never reused."""
    for _ in range(64):
        name = f"{CLEANUP_PREFIX}{os.getpid()}-{next(_cleanup_seq)}"
        try:
            os.lstat(name, dir_fd=dir_fd)
        except FileNotFoundError:
            return name
        except OSError:
            continue
    raise OSError(
        errno.EEXIST,
        f"cannot find a free cleanup name under {display_dir}",
        str(display_dir),
    )


def _quarantine_entry(name: str, dir_fd: int, public: Path) -> str:
    """Atomically move the entry at `name` to a fresh private cleanup
    name inside the same directory and return that name. The rename
    captures WHATEVER sits at `name` at that instant — possibly a
    replacement raced in after the caller's inspection — so the caller
    must prove the captured identity before deleting anything, and must
    restore (never delete) a captured mismatch."""
    qname = _fresh_quarantine_name(dir_fd, public.parent)
    try:
        os.rename(name, qname, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
    except OSError as exc:
        raise OSError(
            exc.errno if exc.errno is not None else errno.EIO,
            f"cannot quarantine {public} for cleanup ({exc}); it was "
            "retained",
            str(public),
        )
    return qname


def _restore_quarantined(qname: str, name: str, dir_fd: int, public: Path
                         ) -> str:
    """Best-effort return of a quarantined entry to its public name.
    Returns '' when the entry is back at `public`, else a sentence
    fragment naming where it was left. Never overwrites a DETECTED
    occupant: if anything sits at the public name at the absence probe,
    the entry stays quarantined and is reported. Residue (documented):
    a type-compatible entry raced onto the public name inside the
    probe-to-rename gap is overwritten by the restore rename — for a
    file being restored that means a regular file or symlink at a
    MEANINGFUL name; the standard library has no no-replace rename to
    close this."""
    quarantined = public.parent / qname
    try:
        os.lstat(name, dir_fd=dir_fd)
    except FileNotFoundError:
        try:
            os.rename(qname, name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            return ""
        except OSError as exc:
            return f"; it was left at {quarantined} ({exc})"
    except OSError as exc:
        return (
            f"; it was left at {quarantined} (cannot inspect "
            f"{public}: {exc})"
        )
    return f"; {public} was reoccupied, so it was left at {quarantined}"


def _delete_quarantined(
    qname: str,
    name: str,
    dir_fd: int,
    proven: os.stat_result,
    public: Path,
) -> None:
    """Last-instant verified deletion of a quarantined entry: re-lstat
    the single-use private quarantine name, require exactly the proven
    identity, then unlink/rmdir THAT name — never the public one. A
    mismatching quarantine is NEVER deleted (the replacement stays at
    the quarantine name and is reported); a deletion failure on the
    proven entry restores it toward its public name and reports.
    Deletion by name is the one operation POSIX cannot make conditional
    on identity, so the lstat-to-delete gap on the private name is the
    irreducible check-then-name residue — for rmdir it can lose only an
    empty directory raced onto a name that never existed before this
    cleanup."""
    quarantined = public.parent / qname
    final_stat = os.lstat(qname, dir_fd=dir_fd)
    if not os.path.samestat(final_stat, proven):
        raise OSError(
            errno.EBUSY,
            f"{public} was replaced during cleanup; the replacement was "
            f"retained at {quarantined} — inspect and remove it manually",
            str(public),
        )
    try:
        if stat.S_ISDIR(proven.st_mode):
            os.rmdir(qname, dir_fd=dir_fd)
        else:
            os.unlink(qname, dir_fd=dir_fd)
    except OSError as exc:
        note = _restore_quarantined(qname, name, dir_fd, public)
        raise OSError(
            exc.errno if exc.errno is not None else errno.EIO,
            f"cannot remove {public} ({exc}); it was retained{note}",
            str(public),
        ) from None


def _delete_children_pinned(dir_fd: int, root_dev: int, display: Path) -> None:
    """Bottom-up removal of everything beneath an already-pinned (and
    already root-quarantined) directory descriptor, entirely through
    descriptor-relative operations. Every child is deleted quarantine-
    first: the inspected child name is atomically renamed to a fresh
    private cleanup name in the same directory — capturing whatever sits
    at the name at that instant — and the captured entry must prove the
    inspected identity before anything is deleted; a captured
    replacement is renamed back to its public name and the cleanup
    refuses (EBUSY), so a substitution immediately before an unlink or
    rmdir never deletes the replacement. Directories are additionally
    opened O_DIRECTORY|O_NOFOLLOW from their quarantine name,
    fstat-proven, and refused on device transitions (EXDEV); a failure
    inside a quarantined subtree restores that subtree toward its public
    name before propagating. No public name is ever passed to unlink or
    rmdir; the private-name residue is documented in
    _delete_quarantined."""
    for name in sorted(os.listdir(dir_fd)):
        public = display / name
        entry_stat = os.lstat(name, dir_fd=dir_fd)
        qname = _quarantine_entry(name, dir_fd, public)
        q_stat = os.lstat(qname, dir_fd=dir_fd)
        if not os.path.samestat(q_stat, entry_stat):
            note = _restore_quarantined(qname, name, dir_fd, public)
            raise OSError(
                errno.EBUSY,
                f"{public} was replaced during cleanup; the replacement "
                f"was retained{note}",
                str(public),
            )
        if stat.S_ISDIR(entry_stat.st_mode):
            try:
                child_fd = _open_dir_nofollow(qname, dir_fd)
            except OSError:
                note = _restore_quarantined(qname, name, dir_fd, public)
                raise OSError(
                    errno.EBUSY,
                    f"{public} was replaced during cleanup; the "
                    f"replacement was retained{note}",
                    str(public),
                ) from None
            try:
                try:
                    child_stat = os.fstat(child_fd)
                    if not os.path.samestat(child_stat, entry_stat):
                        raise OSError(
                            errno.EBUSY,
                            f"{public} was replaced during cleanup; it "
                            "was retained",
                            str(public),
                        )
                    if child_stat.st_dev != root_dev:
                        raise OSError(
                            errno.EXDEV,
                            f"refusing to remove across a mount boundary: "
                            f"{public} is a mounted or cross-device "
                            "subtree; unmount it first",
                            str(public),
                        )
                    _delete_children_pinned(child_fd, root_dev, public)
                except BaseException as caught:
                    # A failed intermediate restore changes where the
                    # deeper error's retained entries actually sit —
                    # report it, never discard the note.
                    note = _restore_quarantined(qname, name, dir_fd, public)
                    if note and isinstance(caught, OSError):
                        raise OSError(
                            caught.errno
                            if caught.errno is not None
                            else errno.EIO,
                            f"{caught.strerror if caught.strerror else caught}"
                            f"{note}",
                            str(public),
                        ) from None
                    raise
                # child_fd stays open across the verified rmdir: the
                # held descriptor keeps the inode alive, so its number
                # cannot be recycled into a forged samestat proof.
                _delete_quarantined(qname, name, dir_fd, entry_stat, public)
            finally:
                os.close(child_fd)
        else:
            _delete_quarantined(qname, name, dir_fd, entry_stat, public)


def _rmtree_pinned(
    path: Path, *, name: str, dir_fd: int, expected: os.stat_result
) -> None:
    """Identity-proven recursive delete for STG/PREV only (C1 + C3 + Q1):

    1. PIN: open `name` O_RDONLY|O_DIRECTORY|O_NOFOLLOW relative to the
       pinned destination descriptor — never through a fresh resolution
       of PATH — and fstat the descriptor, which stays open until the
       final rmdir (the held inode cannot be recycled into a forged
       samestat proof).
    2. PROVE: the pinned identity must equal `expected`, the identity
       this run recorded when IT created (staging) or moved aside
       (previous) the directory. Anything else is retained untouched: a
       directory substituted at the name is provably not ours to delete.
    3. CONTAIN: the pinned root must be on the destination's device
       (fstat vs the pinned PATH descriptor's st_dev), must not itself
       be a mount point (additive probe), and every descendant is swept
       for device or mount transitions through the pinned descriptor —
       all before the first mutation; a rejected root is not modified.
    4. QUARANTINE: the proven root is ATOMICALLY renamed to a fresh
       private single-use cleanup name (CLEANUP_PREFIX…) relative to the
       pinned destination descriptor, and the entry captured at that
       name is re-proven against the held descriptor's identity: a root
       substituted between the proof and the rename is captured,
       detected, renamed back to the public name, and never deleted.
       From here on no deletion ever names the public STG/PREV entry.
    5. DELETE: children are removed bottom-up through per-child
       quarantine-then-prove (see _delete_children_pinned); a failure
       restores the root (and the in-flight subtree) toward its public
       name before propagating, so recovery instructions stay valid.
    6. FINAL: the (now empty) quarantined root is re-proven by lstat of
       the private name and removed with os.rmdir on that name; a
       mismatching entry at the private name is never deleted.

    Raises _CleanupRootAbsent only when the entry is genuinely absent
    under the pinned destination (the initial pin-open, before any
    mutation — an interior ENOENT mid-deletion means interference and
    surfaces as a reported OSError instead, because Python's errno
    mapping would otherwise make it indistinguishable from clean
    absence); every other failure raises OSError with the exact reason
    and the exact retained location (callers retain the tree and
    report). A RecursionError from a hostile deeply-nested tree is
    converted to a reported OSError with the tree retained — never an
    unhandled internal error that would mask the original failure."""
    try:
        root_fd = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=dir_fd,
        )
    except FileNotFoundError:
        raise _CleanupRootAbsent(str(path)) from None
    except OSError as exc:
        raise OSError(
            exc.errno if exc.errno is not None else errno.EIO,
            f"cannot pin {path} for cleanup ({exc}); it was retained",
            str(path),
        )
    try:
        root_stat = os.fstat(root_fd)
        if not os.path.samestat(root_stat, expected):
            raise OSError(
                errno.EBUSY,
                f"{path} is no longer the directory this export owned; "
                "it was retained — inspect and remove it manually",
                str(path),
            )
        dest_stat = os.fstat(dir_fd)
        if root_stat.st_dev != dest_stat.st_dev:
            raise OSError(
                errno.EXDEV,
                f"refusing to remove {path}: it is on a different "
                "filesystem than the destination root (mount boundary); "
                "unmount it first",
                str(path),
            )
        if _ismount_probe(path):
            raise OSError(
                errno.EXDEV,
                f"refusing to remove {path}: it is a mount point "
                "(mount boundary); unmount it first",
                str(path),
            )
        try:
            offender = _mounted_subtree_pinned(root_fd, path)
        except RecursionError:
            raise OSError(
                errno.EIO,
                f"{path} is nested too deeply to verify and delete "
                "safely (possible interference); it was retained",
                str(path),
            ) from None
        except OSError as exc:
            raise OSError(
                exc.errno if exc.errno is not None else errno.EIO,
                f"cannot verify {path} is free of mounted subtrees ({exc})",
                str(path),
            )
        if offender is not None:
            raise OSError(
                errno.EXDEV,
                f"refusing to remove across a mount boundary: {offender} "
                "is a mounted or cross-device subtree; unmount it first",
                str(path),
            )
        qname = _quarantine_entry(name, dir_fd, path)
        q_stat = os.lstat(qname, dir_fd=dir_fd)
        if not os.path.samestat(q_stat, root_stat):
            note = _restore_quarantined(qname, name, dir_fd, path)
            raise OSError(
                errno.EBUSY,
                f"{path} was replaced during cleanup; the replacement "
                f"was retained{note}",
                str(path),
            )
        try:
            _delete_children_pinned(root_fd, root_stat.st_dev, path)
        except RecursionError:
            _restore_quarantined(qname, name, dir_fd, path)
            raise OSError(
                errno.EIO,
                f"{path} is nested too deeply to delete safely "
                "(possible interference); it was retained",
                str(path),
            ) from None
        except OSError as exc:
            note = _restore_quarantined(qname, name, dir_fd, path)
            if note:
                raise OSError(
                    exc.errno if exc.errno is not None else errno.EIO,
                    f"{exc.strerror if exc.strerror else exc}{note}",
                    str(path),
                ) from None
            raise
        except BaseException:
            _restore_quarantined(qname, name, dir_fd, path)
            raise
        # root_fd stays open across the verified final rmdir: the held
        # inode cannot be recycled into a forged samestat proof.
        _delete_quarantined(qname, name, dir_fd, root_stat, path)
    finally:
        os.close(root_fd)


def _discard_staging(
    target: ExportTarget,
    failure: AosError,
    dest_fd: int,
    staging_stat: os.stat_result,
) -> AosError:
    """Remove the disposable staging tree and hand back the failure to
    raise — but ONLY when the entry at the staging name is provably
    still the directory this run created (samestat against the pinned
    staging descriptor's identity); anything else is RETAINED and
    reported (it is not ours to delete). A cleanup failure must never
    mask the original error NOR pass silently (a leftover STG refuses
    the next run): the returned error then reports both."""
    try:
        stg_stat = os.lstat(STAGING_NAME, dir_fd=dest_fd)
    except FileNotFoundError:
        return failure
    except OSError as exc:
        return AosError(
            f"{failure} Additionally, staging {target.staging} could not "
            f"be inspected before cleanup ({exc}); if it still exists, "
            "remove it before rerunning."
        )
    if not os.path.samestat(stg_stat, staging_stat):
        return AosError(
            f"{failure} Additionally, {target.staging} is no longer the "
            "staging directory this run created, so it was NOT removed; "
            "inspect it, remove it, and rerun."
        )
    try:
        _rmtree_pinned(
            target.staging,
            name=STAGING_NAME,
            dir_fd=dest_fd,
            expected=staging_stat,
        )
    except _CleanupRootAbsent:
        return failure
    except OSError as exc:
        # Includes interior ENOENT (a child raced away mid-delete): the
        # tree was retained (restored or at its cleanup name) and MUST
        # be reported — errno mapping makes such an exception a
        # FileNotFoundError, which must never read as clean absence.
        return AosError(
            f"{failure} Additionally, staging {target.staging} could not "
            f"be removed ({exc}); remove it before rerunning."
        )
    return failure


def _strand_unproven_previous(target: ExportTarget, detail: str) -> AosError:
    aos_q = shlex.quote(str(target.dest_aos))
    return AosError(
        f"Export interrupted: {target.dest_aos} is missing and "
        f"{target.previous} is not provably the generation this export "
        f"moved aside ({detail}), so it was NOT renamed back; it was "
        f"retained untouched. The complete new generation is at "
        f"{target.staging}. Inspect {target.previous}, then run: "
        f"mv {shlex.quote(str(target.previous))} {aos_q} (keep old) or "
        f"mv {shlex.quote(str(target.staging))} {aos_q} (promote new), "
        "remove the other, and rerun. See TROUBLESHOOTING.md."
    )


def _rollback_or_strand(
    target: ExportTarget, dest_fd: int, prev_stat: os.stat_result | None
) -> None:
    """Restore PREV to the authoritative name AND fsync PATH so the
    restoration is durable — both relative to the pinned destination
    descriptor. The rollback rename targets the AUTHORITATIVE name, so
    its SOURCE needs the same identity proof the move-aside and the
    cleanup already have (sixth pass, R1): the entry at the previous
    name must be the exact directory this run moved aside — a fresh
    lstat proven against the identity pinned immediately after the
    move-aside (the held PREV descriptor keeps that inode alive, so the
    proof cannot be forged by inode recycling). A never-pinned,
    uninspectable, replaced, or vanished PREV strands instead of being
    renamed: the entry is retained untouched, staging is kept, and the
    exact state with shell-quoted recovery commands is printed —
    renaming an unproven tree onto the authoritative name would promote
    content this run never validated. The guard-lstat-to-rename gap is
    the same irreducible residue as the move-aside guard's. Raises —
    keeping the complete staging tree — when the rollback is refused as
    above, when the rollback rename fails (both generations remain,
    with exact shell-quoted recovery commands), or when the rollback
    fsync fails (the restoration is live but not durably proven, so no
    complete tree may be discarded)."""
    aos_q = shlex.quote(str(target.dest_aos))
    if prev_stat is None:
        raise _strand_unproven_previous(
            target, "its identity could not be pinned after the move-aside"
        )
    try:
        guard = os.lstat(PREVIOUS_NAME, dir_fd=dest_fd)
    except FileNotFoundError:
        # Genuinely absent (F4: only ENOENT reads as absence): nothing
        # to restore, nothing retained — no instruction to inspect or
        # remove a nonexistent tree.
        raise AosError(
            f"Export interrupted: {target.dest_aos} is missing and "
            f"{target.previous} disappeared before the rollback "
            f"(concurrent process?). The complete new generation is at "
            f"{target.staging}. Run: "
            f"mv {shlex.quote(str(target.staging))} {aos_q} (promote new) "
            f"— or restore your previous generation to {target.dest_aos} "
            "yourself — then rerun. See TROUBLESHOOTING.md."
        )
    except OSError as exc:
        raise _strand_unproven_previous(target, f"cannot inspect it: {exc}")
    if not os.path.samestat(guard, prev_stat):
        raise _strand_unproven_previous(
            target, "it was replaced during the export"
        )
    try:
        os.rename(
            PREVIOUS_NAME,
            obsidian.AOS_SUBDIR,
            src_dir_fd=dest_fd,
            dst_dir_fd=dest_fd,
        )
    except OSError:
        raise AosError(
            f"Export interrupted: {target.dest_aos} is missing. The "
            f"complete previous generation is at {target.previous}; the "
            f"complete new generation is at {target.staging}. Run: "
            f"mv {shlex.quote(str(target.previous))} {aos_q} (keep old) or "
            f"mv {shlex.quote(str(target.staging))} {aos_q} (promote new), "
            "remove the other, and rerun. See TROUBLESHOOTING.md."
        )
    try:
        _fsync_dest_root(dest_fd)
    except OSError as exc:
        raise AosError(
            f"Export failed: the previous generation was moved back to "
            f"{target.dest_aos}, but the rollback's durability could not "
            f"be confirmed ({exc}). Live state: {target.dest_aos} holds "
            f"the previous generation; the complete new generation remains "
            f"at {target.staging}. After a crash the rollback may be lost, "
            f"leaving {target.dest_aos} missing and the previous "
            f"generation at {target.previous} (recovery drill in "
            f"TROUBLESHOOTING.md). Verify {target.dest_aos}, remove "
            f"{target.staging}, and rerun."
        )


def _open_dest_root(target: ExportTarget) -> int:
    """Pin the approved destination before the first mutation: open PATH
    O_RDONLY|O_DIRECTORY|O_NOFOLLOW (where available), fstat it, and
    require identity equality with the destination identity recorded in
    the plan. The descriptor stays open for the COMPLETE apply — staging
    creation, renames, fsyncs, and cleanup are all dir_fd-relative to it,
    so a concurrently replaced PATH is refused, never written through."""
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        fd = os.open(target.dest_root, flags)
    except OSError as exc:
        raise _destination_changed(f"cannot open {target.dest_root}: {exc}")
    try:
        if not os.path.samestat(os.fstat(fd), target.dest_root_stat):
            raise _destination_changed(f"{target.dest_root} was replaced")
    except BaseException:
        os.close(fd)
        raise
    return fd


@dataclass(frozen=True)
class ApplyResult:
    """Immutable record of what apply_plan ACTUALLY did (C5), measured
    during execution — never inferred from the plan's intended
    operations. Byte-counting rules: a payload copy or newly written
    file contributes its actual written size (fstat of the staged file);
    an unchanged file copied because hardlinks are unsupported
    contributes its full byte size; creating a hardlink contributes
    zero payload bytes."""

    created_files: int
    updated_files: int
    deleted_files: int
    unchanged_files: int
    unchanged_hardlinked_files: int
    unchanged_fallback_copied_files: int
    payload_bytes_written: int
    #: Warning line for the CLI to print (exit stays 0) when only the
    #: PREV cleanup failed or PREV was retained; None otherwise.
    cleanup_warning: str | None


def apply_plan(plan: ExportPlan) -> ApplyResult:
    """Pin PATH → build → validate → recheck → final staging verification
    → promote → clean up. Returns the immutable ApplyResult of the
    observed execution (including the PREV-cleanup warning, if any);
    every failure raises AosError with the exact on-disk state."""
    dest_fd = _open_dest_root(plan.target)
    try:
        return _apply_pinned(plan, dest_fd)
    finally:
        os.close(dest_fd)


def _apply_pinned(plan: ExportPlan, dest_fd: int) -> ApplyResult:
    target = plan.target
    try:
        os.mkdir(STAGING_NAME, dir_fd=dest_fd)
    except FileExistsError:
        raise AosError(
            f"Refusing to export: staging {target.staging} already exists "
            "(interrupted or concurrent export); if no other export is "
            "running, remove it and rerun."
        )
    except OSError as exc:
        raise AosError(
            f"Export failed: could not create staging {target.staging} "
            f"({exc}); destination left untouched. Fix the cause and rerun."
        )
    try:
        # An open descriptor on the staging directory pins its inode for
        # the COMPLETE apply: a concurrent rmtree+mkdir can otherwise
        # recreate the SAME inode number (inode recycling) and slip a
        # foreign tree past a samestat-based identity recheck — holding
        # the descriptor keeps the inode alive, so its number cannot be
        # reissued while any discard path still needs the proof. Opened
        # O_NOFOLLOW relative to the pinned PATH descriptor: a symlink
        # raced into the staging name between mkdir and open is refused
        # (ELOOP), never followed — and the failure RETAINS whatever now
        # sits at the name (it is not ours to delete).
        staging_fd = _open_dir_nofollow(STAGING_NAME, dest_fd)
    except OSError as exc:
        raise _StagingCompromised(
            f"Refusing to export: staging {target.staging} was replaced "
            f"between creation and open (concurrent process?); "
            f"{target.dest_aos} is unchanged. Remove whatever now sits at "
            f"{target.staging} and rerun. (Open failed: {exc}.)"
        )
    try:
        return _promote_pinned(plan, dest_fd, staging_fd)
    finally:
        os.close(staging_fd)


def _promote_pinned(
    plan: ExportPlan, dest_fd: int, staging_fd: int
) -> ApplyResult:
    """Build, verify, promote, and clean up while BOTH the destination
    and the staging descriptors stay open (apply_plan/_apply_pinned own
    their lifetimes). The verified live AOS root is additionally pinned
    by the recheck (aos_fd) and held through promotion and cleanup: the
    move-aside guard and the PREV ownership proof compare against the
    HELD descriptor's identity, which inode recycling cannot forge."""
    target = plan.target
    staging_stat = os.fstat(staging_fd)
    aos_fd = None
    try:
        try:
            build = _build_staging(plan, staging_fd, dest_fd)
            snapshot = _validate_staging(
                plan, staging_fd, staging_stat, build.linked
            )
            # C7 ordering — freshest verification LAST: the source
            # (unreachable through staged hardlinks) is re-verified
            # first, the destination content/structure/identity next,
            # and the complete staging rescan with its content hash
            # runs last, immediately before the renames.
            _verify_source_final(plan, snapshot)
            first_export, aos_fd, aos_dirs = _recheck_target(
                plan, staging_fd, staging_stat, dest_fd, snapshot.linked
            )
            _verify_staging_final(
                plan, staging_fd, staging_stat, snapshot, dest_fd,
                aos_fd, aos_dirs,
            )
        except _StagingCompromised:
            # Staging is missing, uninspectable, or not ours any more:
            # never delete it.
            raise
        except AosError as exc:
            raise _discard_staging(
                target, exc, dest_fd, staging_stat
            ) from None
        except (OSError, RecursionError) as exc:
            # RecursionError: a hostile deeply-nested tree raced into a
            # scanned position must surface as the exit-1 refusal (with
            # staging discarded or retained-and-reported), never as an
            # unhandled internal error.
            raise _discard_staging(target, AosError(
                f"Export failed while staging ({exc}); destination left "
                "untouched. Fix the cause and rerun."
            ), dest_fd, staging_stat) from None
        return _finish_promotion(
            plan, dest_fd, staging_stat, build, first_export, aos_fd
        )
    finally:
        if aos_fd is not None:
            os.close(aos_fd)


def _finish_promotion(
    plan: ExportPlan,
    dest_fd: int,
    staging_stat: os.stat_result,
    build: _BuildStats,
    first_export: bool,
    aos_fd: int | None,
) -> ApplyResult:
    """Promotion renames, PREV cleanup, and the observed ApplyResult.
    Runs with the destination, staging, and (non-first-export) AOS-root
    descriptors held open by the callers."""
    target = plan.target

    def result(cleanup_warning: str | None) -> ApplyResult:
        return ApplyResult(
            created_files=build.created_files,
            updated_files=build.updated_files,
            deleted_files=len(plan.deletes),
            unchanged_files=(
                build.unchanged_hardlinked_files
                + build.unchanged_fallback_copied_files
            ),
            unchanged_hardlinked_files=build.unchanged_hardlinked_files,
            unchanged_fallback_copied_files=(
                build.unchanged_fallback_copied_files
            ),
            payload_bytes_written=build.payload_bytes_written,
            cleanup_warning=cleanup_warning,
        )

    if first_export:
        try:
            os.rename(
                STAGING_NAME,
                obsidian.AOS_SUBDIR,
                src_dir_fd=dest_fd,
                dst_dir_fd=dest_fd,
            )
        except OSError as exc:
            raise AosError(
                f"Export failed during promotion ({exc}); no "
                f"{target.dest_aos} was created and the complete staged "
                f"generation remains at {target.staging}; remove it and "
                "rerun."
            )
        try:
            _fsync_dest_root(dest_fd)
        except OSError as exc:
            raise AosError(
                "Export promoted but durability could not be confirmed "
                f"({exc}); {target.dest_aos} is current. Verify it before "
                "relying on this export."
            )
        return result(None)

    # C1: the AOS root was pinned at the recheck AFTER the full content
    # verification; require the name still to reach that exact held
    # inode immediately before the move-aside. A foreign directory
    # substituted at the name — even one landing on a recycled inode
    # number — cannot match, because the held descriptor keeps the real
    # inode alive.
    aos_pinned = os.fstat(aos_fd)
    try:
        live_now = _lstat_or_absent(
            obsidian.AOS_SUBDIR, dir_fd=dest_fd, display=target.dest_aos
        )
    except AosError as exc:
        raise _discard_staging(target, exc, dest_fd, staging_stat)
    if live_now is None or not os.path.samestat(live_now, aos_pinned):
        raise _discard_staging(
            target,
            _destination_changed(f"{target.dest_aos} was replaced"),
            dest_fd,
            staging_stat,
        )
    try:
        os.rename(
            obsidian.AOS_SUBDIR,
            PREVIOUS_NAME,
            src_dir_fd=dest_fd,
            dst_dir_fd=dest_fd,
        )
    except OSError as exc:
        raise _discard_staging(target, AosError(
            f"Export failed: could not move the current generation aside "
            f"({exc}); destination unchanged. Close Obsidian (or wait for "
            "antivirus) and rerun."
        ), dest_fd, staging_stat)
    # C1: record and PIN the PREV identity IMMEDIATELY after the
    # move-aside. The open descriptor keeps the inode alive, so its
    # number cannot be recycled into a foreign directory; the proof
    # chains to the identity of the AOS root descriptor pinned at the
    # recheck and held across the rename. If the entry now at PREV is
    # not that exact directory — or cannot be opened/inspected — its
    # identity is unproven and the final cleanup retains it.
    prev_fd = None
    try:
        try:
            prev_fd = _open_dir_nofollow(PREVIOUS_NAME, dest_fd)
        except OSError:
            prev_fd = None
        prev_stat = None
        if prev_fd is not None:
            try:
                prev_probe = os.fstat(prev_fd)
            except OSError:
                prev_probe = None
            if prev_probe is not None and os.path.samestat(
                prev_probe, aos_pinned
            ):
                prev_stat = prev_probe
        try:
            _fsync_dest_root(dest_fd)
        except OSError as exc:
            # Raises when staging must be kept (rollback refused/failed).
            _rollback_or_strand(target, dest_fd, prev_stat)
            raise _discard_staging(target, AosError(
                "Export failed: could not confirm durability after moving "
                f"the current generation aside ({exc}); the previous "
                "generation was restored and the destination is unchanged. "
                "Rerun after resolving the cause."
            ), dest_fd, staging_stat)
        try:
            os.rename(
                STAGING_NAME,
                obsidian.AOS_SUBDIR,
                src_dir_fd=dest_fd,
                dst_dir_fd=dest_fd,
            )
        except OSError as exc:
            # Raises when staging must be kept (rollback refused/failed).
            _rollback_or_strand(target, dest_fd, prev_stat)
            raise _discard_staging(target, AosError(
                f"Export failed during promotion ({exc}); the previous "
                "generation was restored and the destination is unchanged. "
                "Rerun after resolving the cause."
            ), dest_fd, staging_stat)
        try:
            _fsync_dest_root(dest_fd)
        except OSError as exc:
            raise AosError(
                "Export promoted but durability could not be confirmed "
                f"({exc}); {target.dest_aos} is current and the previous "
                f"generation remains at {target.previous}. Verify, then "
                f"remove {target.previous} and rerun."
            )
        if prev_stat is None:
            # Identity unproven (C1): whatever sits at PREV is retained
            # byte-for-byte and reported — not provably ours to delete.
            return result(
                f"WARN: {target.previous} is not provably the generation "
                "this export moved aside, so it was NOT removed; the "
                "export completed. Inspect it and remove it manually "
                "before the next export."
            )
        try:
            _rmtree_pinned(
                target.previous,
                name=PREVIOUS_NAME,
                dir_fd=dest_fd,
                expected=prev_stat,
            )
        except _CleanupRootAbsent:
            # Genuinely gone before cleanup reached it: a concurrent
            # process deleted it. Nothing is retained, so no removal
            # instruction — but the interference is worth flagging.
            return result(
                f"WARN: previous generation {target.previous} disappeared "
                "during cleanup (concurrent process?); nothing needed "
                "removal and the export completed. Check that no other "
                "tool is modifying the destination."
            )
        except OSError as exc:
            return result(
                f"WARN: could not remove previous generation "
                f"{target.previous} ({exc}); the export completed. Remove "
                "it manually before the next export."
            )
    finally:
        if prev_fd is not None:
            os.close(prev_fd)
    try:
        _fsync_dest_root(dest_fd)
    except OSError as exc:
        raise AosError(
            f"Export completed and {target.dest_aos} is current, but "
            f"removal of {target.previous} may not survive a crash ({exc}); "
            f"if {target.previous} reappears after a reboot, remove it and "
            "rerun."
        )
    return result(None)
