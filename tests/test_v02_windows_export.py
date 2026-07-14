"""U-C4 Windows/Obsidian export — sync --export-to PATH [--dry-run].

Contract: agentic-os-v0.2-u-c4-windows-export-contract.md.

- U-C4.1 containment and destination resolution (existence-aware; symlink,
  traversal, source=destination, inside-repository refusals; the positive
  ancestor case).
- U-C4.2 dry run (purity, previews, byte totals, stale-state refusal).
- U-C4.3 ownership and adoption (PATH/AOS fully managed; preservation only
  outside AOS; destination edits never ingested).
- U-C4.4 whole-tree generation protocol (staging, validation, promotion,
  rollback, recovery; no test accepts a mixed-generation AOS).
- U-C4.5 copy-if-changed (zero mutation when identical; hardlink reuse with
  errno-gated fallback).
- U-C4.6 validation, determinism, Windows representability (UTF-16
  component units, reserved names, casefold collisions).
- U-C4.7 one-way / eventless / back-compat.
"""

from __future__ import annotations

import contextlib
import errno
import io
import os
import shlex
import shutil
import sqlite3
import stat
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

from agentic_os import cli, mirror_export, obsidian, utils
from agentic_os.utils import AosError

from weekend_harness import Night1BackCompatCase, WeekendTestCase


class ExportCase(Night1BackCompatCase):
    """Night-1 workspace + a destination vault root (with spaces)."""

    def setUp(self):
        super().setUp()
        self.source = self.aos_dir / obsidian.VAULT_DIRNAME / obsidian.AOS_SUBDIR
        self.dest_root = self.new_tmp_dir("vault root with spaces")
        self.dest_aos = self.dest_root / obsidian.AOS_SUBDIR
        self.staging = self.dest_root / mirror_export.STAGING_NAME
        self.previous = self.dest_root / mirror_export.PREVIOUS_NAME

    # -- helpers ----------------------------------------------------------

    def export(self, *extra: str, dest: Path | None = None) -> str:
        return self.aos(
            "sync", "--export-to", str(dest or self.dest_root), *extra
        )

    def export_fails(
        self, *extra: str, dest: Path | None = None
    ) -> tuple[int, str, str]:
        return self.aos_fails(
            "sync", "--export-to", str(dest or self.dest_root), *extra
        )

    def snapshot(self, root: Path) -> dict[str, bytes]:
        """Byte-level picture of everything under `root` (symlinks kept
        as such, directories as markers) — the dry-run-purity witness."""
        result: dict[str, bytes] = {}
        if not root.exists():
            return result
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root).as_posix()
            if path.is_symlink():
                result[rel] = b"<symlink>" + os.readlink(path).encode()
            elif path.is_file():
                result[rel] = path.read_bytes()
            else:
                result[rel] = b"<dir>"
        return result

    def stat_map(self, root: Path) -> dict[str, tuple[int, int]]:
        return {
            path.relative_to(root).as_posix(): (
                path.stat().st_ino,
                path.stat().st_mtime_ns,
            )
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }

    def source_hash(self) -> str:
        return utils.tree_hash(self.source)

    def assert_whole_generation(self, *allowed_hashes: str) -> None:
        """No test may accept a mixed-generation AOS: the authoritative
        tree must be exactly one known generation, or absent with complete
        known generations at the recovery positions."""
        if self.dest_aos.exists():
            self.assertIn(utils.tree_hash(self.dest_aos), set(allowed_hashes))
            return
        neighbors = {
            utils.tree_hash(path)
            for path in (self.previous, self.staging)
            if path.exists()
        }
        self.assertTrue(
            neighbors & set(allowed_hashes),
            f"AOS absent and no complete generation among neighbors "
            f"({neighbors} vs {allowed_hashes})",
        )

    def event_count(self) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        finally:
            conn.close()

    def fail_dest_fsync(self, on_call: int, exc: OSError):
        """Patch the module's pinned-destination fsync so the Nth
        durability fsync of the DESTINATION ROOT raises (staging-dir
        fsyncs go through _fsync_dir_fd and pass untouched) — the three
        durability points, deterministically. Every _fsync_dest_root call
        IS a destination-root fsync: the descriptor was identity-checked
        against PATH at open."""
        real = mirror_export._fsync_dest_root
        seen = {"n": 0}

        def wrapper(dest_fd):
            seen["n"] += 1
            if seen["n"] == on_call:
                raise exc
            return real(dest_fd)

        return mock.patch.object(mirror_export, "_fsync_dest_root", wrapper)

    @staticmethod
    def fail_on_call(real, n: int, exc: BaseException):
        seen = {"n": 0}

        def wrapper(*args, **kwargs):
            seen["n"] += 1
            if seen["n"] == n:
                raise exc
            return real(*args, **kwargs)

        return wrapper

    def require_case_sensitive_fs(self, base: Path) -> None:
        probe = base / "CaseProbe.tmp"
        probe.write_text("x")
        self.addCleanup(probe.unlink, missing_ok=True)
        if (base / "caseprobe.tmp").exists():
            self.skipTest("case-insensitive filesystem")

    def require_hardlinks(self, base: Path) -> None:
        src, dst = base / "linkprobe-a", base / "linkprobe-b"
        src.write_text("x")
        self.addCleanup(src.unlink, missing_ok=True)
        self.addCleanup(dst.unlink, missing_ok=True)
        try:
            os.link(src, dst)
        except OSError:
            self.skipTest("filesystem does not support hardlinks")


# ---------------------------------------------------------------------------
# U-C4.1 — containment and destination resolution


class TestContainment(ExportCase):
    def test_refuses_nonexistent_destination(self):
        code, out, err = self.export_fails(dest=self.dest_root / "missing")
        self.assertIn("does not exist", err)
        self.assertNotIn("Synced", out)

    def test_refuses_destination_that_is_a_file(self):
        target = self.dest_root / "afile"
        target.write_text("x")
        code, out, err = self.export_fails(dest=target)
        self.assertIn("is not a directory", err)

    def test_refuses_destination_inside_workspace(self):
        # AOS/STG/PREV do not exist yet: the refusal must come from the
        # normalized candidate-path check alone.
        inside = self.root / "exported"
        inside.mkdir()
        code, out, err = self.export_fails(dest=inside)
        self.assertIn("Refusing to export", err)
        self.assertIn("inside the live workspace", err)
        self.assertEqual(sorted(inside.iterdir()), [])

    def test_refuses_destination_whose_aos_is_the_source_mirror(self):
        code, out, err = self.export_fails(dest=self.aos_dir / "obsidian-vault")
        self.assertIn("is the source mirror", err)

    def test_refuses_destination_equal_to_aos_dir(self):
        code, out, err = self.export_fails(dest=self.aos_dir)
        self.assertIn("Refusing to export", err)

    def test_refuses_traversal_into_workspace(self):
        hop = self.root / "hop"
        hop.mkdir()
        code, out, err = self.export_fails(dest=Path(f"{hop}{os.sep}.."))
        self.assertIn("inside the live workspace", err)

    def test_refuses_path_symlink_into_workspace(self):
        link = self.new_tmp_dir("link-holder") / "link"
        link.symlink_to(self.root)
        code, out, err = self.export_fails(dest=link)
        self.assertIn("Refusing to export", err)
        self.assertIn("live workspace", err)

    def test_refuses_dest_aos_symlink(self):
        sentinel = self.new_tmp_dir("sentinel")
        (sentinel / "keep.md").write_text("keep\n")
        self.dest_aos.symlink_to(sentinel)
        code, out, err = self.export_fails()
        self.assertIn("is a symlink to", err)
        self.assertEqual((sentinel / "keep.md").read_text(), "keep\n")

    def test_refuses_workspace_planted_beneath_candidate(self):
        # The workspace lives under the destination's AOS candidate: the
        # contains-check must fire (before adoption or staleness).
        outer = self.new_tmp_dir("outer")
        ws = outer / "AOS" / "ws"
        ws.mkdir(parents=True)
        code, out, err = self.run_cli("--root", str(ws), "init")
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(
            "--root", str(ws), "sync", "--export-to", str(outer)
        )
        self.assertEqual(code, 1)
        self.assertIn("contains the", err)
        self.assertIn("export would delete it", err)

    def test_refuses_workspace_planted_beneath_previous_candidate(self):
        outer = self.new_tmp_dir("outer")
        ws = outer / mirror_export.PREVIOUS_NAME / "ws"
        ws.mkdir(parents=True)
        code, out, err = self.run_cli("--root", str(ws), "init")
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(
            "--root", str(ws), "sync", "--export-to", str(outer)
        )
        self.assertEqual(code, 1)
        self.assertIn("contains the", err)

    def test_allows_path_that_is_ancestor_of_the_workspace(self):
        # Mutation roots are checked, not PATH: an ancestor PATH whose
        # AOS/staging/previous are disjoint from the workspace is fine.
        outer = self.new_tmp_dir("outer")
        ws = outer / "ws"
        ws.mkdir()
        code, out, err = self.run_cli("--root", str(ws), "init")
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli(
            "--root", str(ws), "sync", "--export-to", str(outer)
        )
        self.assertEqual(code, 0, err)
        self.assertTrue((outer / "AOS" / "Home.md").is_file())

    def test_samestat_catches_lexically_different_alias(self):
        # A symlink alias of a protected root differs lexically but has the
        # same identity — the samestat branch must still refuse it.
        alias = self.new_tmp_dir("alias-holder") / "alias"
        alias.symlink_to(self.root)
        with self.assertRaises(AosError) as ctx:
            mirror_export._refuse_overlap("live workspace", self.root, alias)
        self.assertIn("live workspace", str(ctx.exception))

    def test_refusals_precede_all_local_work(self):
        # A containment refusal must fire before the mirror regenerates:
        # no "Synced" line on stdout.
        inside = self.root / "exported"
        inside.mkdir()
        code, out, err = self.export_fails(dest=inside)
        self.assertEqual(out, "")

    def test_adoption_refusal_precedes_all_local_work(self):
        # The full-ownership gate is decidable from destination state
        # alone, so it too must refuse before the mirror regenerates.
        self.export()
        (self.dest_aos / "My Note.md").write_text("mine\n")
        code, out, err = self.export_fails()
        self.assertIn("contains content not generated", err)
        self.assertEqual(out, "")

    def test_enclosing_repository_is_protected(self):
        # The workspace lives inside a git repo; a destination elsewhere in
        # that repo (outside the workspace) must still be refused.
        outer = self.new_tmp_dir("repo-outer")
        (outer / ".git").mkdir()
        ws = outer / "ws"
        ws.mkdir()
        code, out, err = self.run_cli("--root", str(ws), "init")
        self.assertEqual(code, 0, err)
        dest = outer / "vault"
        dest.mkdir()
        code, out, err = self.run_cli(
            "--root", str(ws), "sync", "--export-to", str(dest)
        )
        self.assertEqual(code, 1)
        self.assertIn("repository", err)

    @unittest.skipIf(os.geteuid() == 0, "permission tests need non-root")
    def test_unwritable_destination_refuses_cleanly(self):
        # mkdir(STG) failing with EACCES is a user-environment condition:
        # one-line refusal, exit 1 — never an exit-2 internal error.
        self.dest_root.chmod(0o555)
        self.addCleanup(self.dest_root.chmod, 0o755)
        code, out, err = self.export_fails()
        self.assertIn("could not create staging", err)
        self.assertIn("destination left untouched", err)
        self.assertFalse(self.dest_aos.exists())


# ---------------------------------------------------------------------------
# U-C4.2 — dry run


class TestDryRun(ExportCase):
    def test_dry_run_requires_export_to(self):
        code, out, err = self.aos_fails("sync", "--dry-run")
        self.assertIn("--dry-run requires --export-to", err)

    def test_dry_run_lists_creates_with_totals_and_destination(self):
        out = self.export("--dry-run")
        self.assertIn(f"Export destination: {self.dest_aos}", out)
        files = sorted(
            (p.relative_to(self.source).as_posix(), p.stat().st_size)
            for p in self.source.rglob("*")
            if p.is_file()
        )
        for rel, size in files:
            self.assertIn(f"create {rel} ({size} bytes)", out)
        total = sum(size for _, size in files)
        dirs = sorted(
            p.relative_to(self.source).as_posix()
            for p in self.source.rglob("*")
            if p.is_dir() and not p.name.startswith(".")
        )
        for rel in dirs:
            self.assertIn(f"create-dir {rel}/", out)
        self.assertIn(
            f"Dry run: {len(files)} file creates ({total} bytes), "
            "0 file updates (0 bytes), 0 file deletes (0 bytes), "
            f"{len(dirs)} directory creates, "
            "0 directory deletes, 0 unchanged files. "
            "Nothing was written.",
            out,
        )

    def test_dry_run_is_pure(self):
        before = self.snapshot(self.dest_root)
        self.export("--dry-run")
        self.assertEqual(self.snapshot(self.dest_root), before)
        self.assertFalse(self.dest_aos.exists())
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_dry_run_previews_update_and_delete(self):
        self.export()
        self.aos("task", "add", "Third task", "-p", "demo")
        stale = self.dest_aos / "Tasks" / "T-9999.md"
        stale.write_text("stale generated-shaped note\n")
        before = self.snapshot(self.dest_root)
        out = self.export("--dry-run")
        self.assertIn("update Home.md", out)
        self.assertIn(
            f"delete Tasks/T-9999.md ({stale.stat().st_size} bytes)", out
        )
        self.assertIn("Nothing was written.", out)
        self.assertEqual(self.snapshot(self.dest_root), before)

    def test_dry_run_zero_ops_when_identical(self):
        self.export()
        out = self.export("--dry-run")
        self.assertIn("destination already matches the source", out)
        self.assertIn("nothing to do", out)

    def test_dry_run_refuses_stale_staging(self):
        self.staging.mkdir()
        before = self.snapshot(self.dest_root)
        code, out, err = self.export_fails("--dry-run")
        self.assertIn("staging", err)
        self.assertIn("remove it and rerun", err)
        self.assertNotIn("Dry run:", out)
        self.assertNotIn("Synced", out)
        self.assertEqual(self.snapshot(self.dest_root), before)

    def test_dry_run_refuses_stale_previous_with_aos(self):
        self.export()
        self.previous.mkdir()
        before = self.snapshot(self.dest_root)
        code, out, err = self.export_fails("--dry-run")
        self.assertIn("previous generation", err)
        self.assertIn(f"remove {self.previous} and rerun", err)
        self.assertNotIn("Dry run:", out)
        self.assertEqual(self.snapshot(self.dest_root), before)

    def test_dry_run_refuses_previous_and_staging_without_aos(self):
        self.previous.mkdir()
        self.staging.mkdir()
        before = self.snapshot(self.dest_root)
        code, out, err = self.export_fails("--dry-run")
        self.assertIn("Refusing to export", err)
        self.assertNotIn("Dry run:", out)
        self.assertEqual(self.snapshot(self.dest_root), before)


# ---------------------------------------------------------------------------
# U-C4.3 — ownership, adoption, preservation, one-way


class TestOwnership(ExportCase):
    def test_refuses_hidden_config_inside_dest_aos(self):
        self.export()
        hidden = self.dest_aos / ".obsidian"
        hidden.mkdir()
        (hidden / "app.json").write_text("{}\n")
        code, out, err = self.export_fails()
        self.assertIn("contains content not generated by aos export", err)
        self.assertIn(".obsidian", err)
        self.assertIn("open PATH as the vault root", err)

    def test_refuses_user_note_inside_dest_aos(self):
        self.export()
        (self.dest_aos / "My Note.md").write_text("mine\n")
        code, out, err = self.export_fails()
        self.assertIn("My Note.md", err)

    def test_refuses_symlink_inside_dest_aos(self):
        self.export()
        sentinel = self.new_tmp_dir("sentinel")
        (sentinel / "keep.md").write_text("keep\n")
        (self.dest_aos / "Tasks" / "T-0009.md").symlink_to(
            sentinel / "keep.md"
        )
        code, out, err = self.export_fails()
        self.assertIn("contains content not generated", err)
        self.assertEqual((sentinel / "keep.md").read_text(), "keep\n")

    def test_refuses_case_variant_note(self):
        self.export()
        note = self.dest_aos / "Tasks" / "T-0001.md"
        note.rename(self.dest_aos / "Tasks" / "t-0001.md")
        code, out, err = self.export_fails()
        self.assertIn("t-0001.md", err)

    def test_refuses_directory_at_note_path(self):
        self.export()
        note = self.dest_aos / "Tasks" / "T-0001.md"
        note.unlink()
        note.mkdir()
        code, out, err = self.export_fails()
        self.assertIn("contains content not generated", err)

    def test_preserves_files_outside_aos(self):
        config = self.dest_root / ".obsidian"
        config.mkdir()
        (config / "app.json").write_text('{"theme":"moonstone"}\n')
        (self.dest_root / "my notes.md").write_text("user file\n")
        self.export()
        self.export()
        self.assertEqual(
            (config / "app.json").read_text(), '{"theme":"moonstone"}\n'
        )
        self.assertEqual(
            (self.dest_root / "my notes.md").read_text(), "user file\n"
        )

    def test_hidden_source_entries_are_not_exported(self):
        hidden = self.source / ".obsidian"
        hidden.mkdir()
        (hidden / "workspace.json").write_text("{}\n")
        self.addCleanup(shutil.rmtree, hidden, True)
        self.export()
        self.assertFalse((self.dest_aos / ".obsidian").exists())

    def test_destination_edits_are_never_ingested(self):
        self.export()
        note = self.dest_aos / "Tasks" / "T-0001.md"
        original = note.read_bytes()
        note.write_bytes(original + b"windows edit\n")
        events_before = self.event_count()
        out = self.export()
        self.assertIn("1 updated", out)
        self.assertEqual(note.read_bytes(), original)
        self.assertEqual(self.event_count(), events_before)
        self.assert_no_schema_drift()

    @unittest.skipIf(os.geteuid() == 0, "permission tests need non-root")
    def test_unlistable_dest_aos_subdir_refuses_adoption(self):
        # os.walk must not silently skip an unreadable subtree (that would
        # adopt — and later delete — content that was never inspected).
        self.export()
        locked = self.dest_aos / "Tasks"
        locked.chmod(0)
        self.addCleanup(locked.chmod, 0o755)
        code, out, err = self.export_fails()
        self.assertIn("cannot inspect", err)
        self.assertIn("Permission denied", err)

    @unittest.skipIf(os.geteuid() == 0, "permission tests need non-root")
    def test_unreadable_sibling_outside_aos_is_ignored(self):
        # Nothing outside the three mutation roots is ever enumerated: an
        # unreadable sibling directory cannot affect the export.
        private = self.dest_root / "private"
        private.mkdir()
        private.chmod(0)
        self.addCleanup(private.chmod, 0o755)
        out = self.export()
        self.assertIn("Exported to", out)

    def test_same_size_content_change_is_detected(self):
        # Change detection is size-then-byte: equal-size different bytes
        # must classify as update (a size-only comparison would miss it).
        self.export()
        note = self.dest_aos / "Tasks" / "T-0001.md"
        original = note.read_bytes()
        tampered = original.replace(b"Night-1", b"Night-2", 1)
        self.assertEqual(len(tampered), len(original))
        self.assertNotEqual(tampered, original)
        note.write_bytes(tampered)
        out = self.export()
        self.assertIn("1 updated", out)
        self.assertEqual(note.read_bytes(), original)

    def test_export_deletes_stale_generated_note(self):
        self.export()
        stale = self.dest_aos / "Tasks" / "T-9999.md"
        stale.write_text("stale generated-shaped note\n")
        out = self.export()
        self.assertIn("1 deleted", out)
        self.assertFalse(stale.exists())
        self.assertEqual(
            utils.tree_hash(self.dest_aos), self.source_hash()
        )


# ---------------------------------------------------------------------------
# U-C4.4 — whole-tree generation protocol: failure-recovery battery


class TestFailureRecovery(ExportCase):
    def setUp(self):
        super().setUp()
        self.export()
        self.old_hash = utils.tree_hash(self.dest_aos)
        self.aos("task", "add", "Mutation task", "-p", "demo")
        self.aos("sync")
        self.new_hash = self.source_hash()
        self.assertNotEqual(self.old_hash, self.new_hash)

    def test_staging_build_failure_leaves_destination_untouched(self):
        exc = OSError(errno.EIO, "injected staging failure")
        with mock.patch.object(
            mirror_export.shutil, "copyfileobj", side_effect=exc
        ):
            code, out, err = self.export_fails()
        self.assertIn("Export failed while staging", err)
        self.assertIn("destination left untouched", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_validation_failure_via_broken_wikilink(self):
        planted = self.source / "Tasks" / "T-9998.md"
        planted.write_text("[[NoSuchNote]]\n")
        self.addCleanup(planted.unlink, missing_ok=True)
        code, out, err = self.export_fails()
        self.assertIn("Export validation failed", err)
        self.assertIn("[[NoSuchNote]] does not resolve", err)
        self.assertIn("destination left untouched", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())

    def test_validation_failure_via_cr_bytes(self):
        # Bypass the LF-only writer before planning, driving the module
        # directly (the CLI's sync would heal the corruption): the corrupt
        # note differs from the destination, so staging copies it and the
        # CR validator must catch it before any destination mutation.
        note = self.source / "Tasks" / "T-0001.md"
        note.write_bytes(b"broken\r\nline\n")
        try:
            target = mirror_export.check_destination(
                self.aos_dir, str(self.dest_root)
            )
            plan = mirror_export.compute_plan(self.aos_dir, target)
            with self.assertRaises(AosError) as ctx:
                mirror_export.apply_plan(plan)
        finally:
            self.aos("sync")  # heal the source mirror
        self.assertIn("contains CR bytes", str(ctx.exception))
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())

    def test_validation_failure_when_source_changes_mid_export(self):
        real_build = mirror_export._build_staging

        def build_then_mutate(plan, staging_fd, dest_fd):
            linked = real_build(plan, staging_fd, dest_fd)
            (plan.source / "Tasks" / "T-0001.md").write_bytes(
                b"changed after staging\n"
            )
            return linked

        with mock.patch.object(
            mirror_export, "_build_staging", build_then_mutate
        ):
            code, out, err = self.export_fails()
        self.assertIn("staged tree does not match the source", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        self.aos("sync")  # heal the source mirror

    def test_move_aside_failure_leaves_destination_unchanged(self):
        flaky = self.fail_on_call(
            os.rename, 1, PermissionError(errno.EACCES, "locked")
        )
        with mock.patch.object(mirror_export.os, "rename", flaky):
            code, out, err = self.export_fails()
        self.assertIn("could not move the current generation aside", err)
        self.assertIn("destination unchanged", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_promotion_failure_rolls_back_to_previous(self):
        flaky = self.fail_on_call(
            os.rename, 2, PermissionError(errno.EACCES, "locked")
        )
        with mock.patch.object(mirror_export.os, "rename", flaky):
            code, out, err = self.export_fails()
        self.assertIn("Export failed during promotion", err)
        self.assertIn("previous generation was restored", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())
        self.assert_whole_generation(self.old_hash, self.new_hash)

    def test_failed_rollback_leaves_both_complete_generations(self):
        def explode(*args, **kwargs):
            raise PermissionError(errno.EACCES, "locked")

        flaky = self.fail_on_call_range(os.rename, {2, 3}, explode)
        with mock.patch.object(mirror_export.os, "rename", flaky):
            code, out, err = self.export_fails()
        # Recovery commands are shell-quoted (paths here contain spaces).
        self.assertIn(
            f"mv {shlex.quote(str(self.previous))} "
            f"{shlex.quote(str(self.dest_aos))}",
            err,
        )
        self.assertIn(
            f"mv {shlex.quote(str(self.staging))} "
            f"{shlex.quote(str(self.dest_aos))}",
            err,
        )
        self.assertFalse(self.dest_aos.exists())
        self.assertEqual(utils.tree_hash(self.previous), self.old_hash)
        self.assertEqual(utils.tree_hash(self.staging), self.new_hash)
        self.assert_whole_generation(self.old_hash, self.new_hash)
        # Follow the printed recovery: keep the new generation.
        self.staging.rename(self.dest_aos)
        shutil.rmtree(self.previous)
        out = self.export()
        self.assertIn("already matches the source", out)

    def fail_on_call_range(self, real, bad_calls: set[int], explode):
        seen = {"n": 0}

        def wrapper(*args, **kwargs):
            seen["n"] += 1
            if seen["n"] in bad_calls:
                return explode(*args, **kwargs)
            return real(*args, **kwargs)

        return wrapper

    def test_rollback_never_promotes_swapped_previous(self):
        # Sixth-pass R1: the rollback rename (PREV -> AOS) targets the
        # AUTHORITATIVE name, so its source needs the same identity proof
        # the move-aside and the cleanup already have. A racer that
        # substitutes PREV between the move-aside and the rollback must
        # never see its unvalidated tree renamed onto AOS: the rollback
        # must strand with the foreign tree retained at PREV, the
        # complete new generation kept at staging, and the true state
        # reported.
        stolen = self.dest_root / "stolen previous"
        real_rename = os.rename
        seen = {"n": 0}

        def racer_then_fail(*args, **kwargs):
            seen["n"] += 1
            if seen["n"] == 2:  # the promotion rename (STG -> AOS)
                real_rename(self.previous, stolen)
                self.previous.mkdir()
                (self.previous / "FOREIGN-MARKER.md").write_text(
                    "not the moved-aside generation\n"
                )
                raise PermissionError(errno.EACCES, "locked")
            return real_rename(*args, **kwargs)

        with mock.patch.object(mirror_export.os, "rename", racer_then_fail):
            code, out, err = self.export_fails()
        self.assertIn(
            "not provably the generation this export moved aside", err
        )
        # The foreign tree is retained at PREV byte for byte...
        self.assertEqual(
            (self.previous / "FOREIGN-MARKER.md").read_text(),
            "not the moved-aside generation\n",
        )
        # ...and never reaches the authoritative name.
        self.assertFalse(self.dest_aos.exists())
        # The validated new generation is kept at staging; the stolen
        # previous generation is intact where the racer left it.
        self.assertEqual(utils.tree_hash(self.staging), self.new_hash)
        self.assertEqual(utils.tree_hash(stolen), self.old_hash)
        self.assertIn(
            f"mv {shlex.quote(str(self.staging))} "
            f"{shlex.quote(str(self.dest_aos))}",
            err,
        )
        self.assert_whole_generation(self.old_hash, self.new_hash)

    def test_rollback_refuses_unpinned_previous_identity(self):
        # Sixth-pass R1: when the PREV identity could not be pinned right
        # after the move-aside, the rollback has no proof of what sits at
        # the previous name — renaming it onto the authoritative name
        # would promote content this run never verified. It must strand
        # with both complete generations at their named positions.
        real_open = mirror_export._open_dir_nofollow

        def unpinnable(name, dir_fd):
            if name == mirror_export.PREVIOUS_NAME:
                raise OSError(errno.EIO, "injected pin failure")
            return real_open(name, dir_fd)

        flaky = self.fail_on_call(
            os.rename, 2, PermissionError(errno.EACCES, "locked")
        )
        with mock.patch.object(
            mirror_export, "_open_dir_nofollow", unpinnable
        ), mock.patch.object(mirror_export.os, "rename", flaky):
            code, out, err = self.export_fails()
        self.assertIn(
            "not provably the generation this export moved aside", err
        )
        self.assertFalse(self.dest_aos.exists())
        self.assertEqual(utils.tree_hash(self.previous), self.old_hash)
        self.assertEqual(utils.tree_hash(self.staging), self.new_hash)
        # Both recovery commands, shell-quoted (paths contain spaces).
        self.assertIn(
            f"mv {shlex.quote(str(self.previous))} "
            f"{shlex.quote(str(self.dest_aos))}",
            err,
        )
        self.assertIn(
            f"mv {shlex.quote(str(self.staging))} "
            f"{shlex.quote(str(self.dest_aos))}",
            err,
        )
        self.assert_whole_generation(self.old_hash, self.new_hash)

    def test_recovery_instructions_after_move_aside_interruption(self):
        # Simulate the crash window between the two renames: complete PREV
        # + complete (validated) STG, no AOS.
        self.dest_aos.rename(self.previous)
        shutil.copytree(self.source, self.staging)
        code, out, err = self.export_fails()
        self.assertIn("Refusing to export", err)
        # Restore the old generation per the instructions, then converge.
        shutil.rmtree(self.staging)
        self.previous.rename(self.dest_aos)
        out = self.export()
        self.assertIn("Exported to", out)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)

    def test_recovery_after_promotion_interruption(self):
        # Simulate: promotion done, cleanup lost — new AOS + stale PREV.
        shutil.copytree(self.dest_aos, self.previous)
        code, out, err = self.export_fails()
        self.assertIn("previous generation", err)
        self.assertIn(f"remove {self.previous} and rerun", err)
        shutil.rmtree(self.previous)
        out = self.export()
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)

    def test_recovery_instructions_for_previous_without_aos(self):
        # PREV present, AOS missing, no staging: the refusal must carry the
        # rename-back instruction specifically.
        self.dest_aos.rename(self.previous)
        code, out, err = self.export_fails()
        self.assertIn(
            f"rename {self.previous} back to {self.dest_aos} first", err
        )
        self.previous.rename(self.dest_aos)
        out = self.export()
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)

    def test_staged_file_fsync_failure_is_fatal(self):
        # File fsync has NO skip set. Only the FIRST os.fsync call raises:
        # that is always a staged file's fsync (hardlinked files skip
        # fsync; directory fsyncs come after every file), so a swallowed
        # file-fsync failure cannot hide behind the fatal directory path.
        flaky = self.fail_on_call(os.fsync, 1, OSError(errno.EIO, "io"))
        with mock.patch.object(mirror_export.os, "fsync", flaky):
            code, out, err = self.export_fails()
        self.assertIn("Export failed while staging", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())

    def test_validation_rejects_invalid_utf8(self):
        note = self.source / "Tasks" / "T-0001.md"
        note.write_bytes(b"\xff\xfe broken\n")
        try:
            target = mirror_export.check_destination(
                self.aos_dir, str(self.dest_root)
            )
            plan = mirror_export.compute_plan(self.aos_dir, target)
            with self.assertRaises(AosError) as ctx:
                mirror_export.apply_plan(plan)
        finally:
            self.aos("sync")
        self.assertIn("not valid UTF-8", str(ctx.exception))
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())

    def test_validation_rejects_missing_trailing_newline(self):
        note = self.source / "Tasks" / "T-0001.md"
        note.write_bytes(b"no trailing newline")
        try:
            target = mirror_export.check_destination(
                self.aos_dir, str(self.dest_root)
            )
            plan = mirror_export.compute_plan(self.aos_dir, target)
            with self.assertRaises(AosError) as ctx:
                mirror_export.apply_plan(plan)
        finally:
            self.aos("sync")
        self.assertIn("missing trailing newline", str(ctx.exception))
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())

    def test_validation_catches_staged_dir_tamper(self):
        # The dir-set clause is load-bearing: a staged generation missing
        # an (empty) entity directory must fail validation.
        real_build = mirror_export._build_staging

        def build_then_drop_dir(plan, staging_fd, dest_fd):
            linked = real_build(plan, staging_fd, dest_fd)
            (plan.target.staging / "Reviews").rmdir()
            return linked

        with mock.patch.object(
            mirror_export, "_build_staging", build_then_drop_dir
        ):
            code, out, err = self.export_fails()
        self.assertIn("staged tree does not match the source", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())

    def test_recheck_catches_aos_symlink_swap_and_cleans_staging(self):
        # AOS swapped for a symlink between planning and promotion: the
        # pre-mutation recheck must refuse AND remove the disposable
        # staging so the rerun needs no manual cleanup.
        fresh_root = self.new_tmp_dir("recheck dest")
        sentinel = self.new_tmp_dir("sentinel")
        target = mirror_export.check_destination(
            self.aos_dir, str(fresh_root)
        )
        plan = mirror_export.compute_plan(self.aos_dir, target)
        (fresh_root / "AOS").symlink_to(sentinel)
        with self.assertRaises(AosError) as ctx:
            mirror_export.apply_plan(plan)
        self.assertIn("is a symlink to", str(ctx.exception))
        self.assertFalse(
            (fresh_root / mirror_export.STAGING_NAME).exists()
        )
        self.assertEqual(sorted(sentinel.iterdir()), [])

    @unittest.skipIf(os.geteuid() == 0, "permission tests need non-root")
    def test_source_permission_error_surfaces_cleanly(self):
        # A real POSIX error while planning surfaces verbatim inside a
        # one-line AosError (exit 1), never as an exit-2 internal error.
        # Driven at the module layer: through the CLI the same chmod would
        # fail sync's own regeneration first, which is not export code.
        target = mirror_export.check_destination(
            self.aos_dir, str(self.dest_root)
        )
        note = self.source / "Tasks" / "T-0001.md"
        note.chmod(0)
        self.addCleanup(note.chmod, 0o644)
        with self.assertRaises(AosError) as ctx:
            mirror_export.compute_plan(self.aos_dir, target)
        self.assertIn("cannot read", str(ctx.exception))
        self.assertIn("T-0001.md", str(ctx.exception))
        self.assertIn("Permission denied", str(ctx.exception))
        self.assertEqual(ctx.exception.exit_code, 1)
        note.chmod(0o644)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)

    def test_stale_staging_refusal_on_apply(self):
        self.staging.mkdir()
        code, out, err = self.export_fails()
        self.assertIn(f"staging {self.staging} already exists", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)

    def test_prev_cleanup_failure_warns_and_exits_zero(self):
        exc = OSError(errno.EACCES, "held open")
        with mock.patch.object(
            mirror_export, "_delete_children_pinned", side_effect=exc
        ):
            code, out, err = self.run_cli(
                "--root", str(self.root),
                "sync", "--export-to", str(self.dest_root),
            )
        self.assertEqual(code, 0, out + err)
        self.assertIn("WARN: could not remove previous generation", err)
        self.assertIn("Exported to", out)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)
        self.assertTrue(self.previous.exists())
        shutil.rmtree(self.previous)

    def test_keyboard_interrupt_leaves_complete_trees(self):
        flaky = self.fail_on_call(os.rename, 2, KeyboardInterrupt())
        with mock.patch.object(mirror_export.os, "rename", flaky):
            code, out, err = self.run_cli(
                "--root", str(self.root),
                "sync", "--export-to", str(self.dest_root),
            )
        self.assertEqual(code, 2)
        self.assertFalse(self.dest_aos.exists())
        self.assertEqual(utils.tree_hash(self.previous), self.old_hash)
        self.assertEqual(utils.tree_hash(self.staging), self.new_hash)
        self.assert_whole_generation(self.old_hash, self.new_hash)

    def test_fatal_fsync_after_move_aside_rolls_back(self):
        with self.fail_dest_fsync(1, OSError(errno.EIO, "io error")):
            code, out, err = self.export_fails()
        self.assertIn("could not confirm durability", err)
        self.assertIn("destination is unchanged", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_fatal_fsync_after_promotion_keeps_new_generation(self):
        with self.fail_dest_fsync(2, OSError(errno.EIO, "io error")):
            code, out, err = self.export_fails()
        self.assertIn("Export promoted but durability", err)
        self.assertIn(f"remove {self.previous} and rerun", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)
        self.assertEqual(utils.tree_hash(self.previous), self.old_hash)
        self.assertFalse(self.staging.exists())
        shutil.rmtree(self.previous)

    def test_fatal_fsync_after_cleanup_reports_and_exits_one(self):
        with self.fail_dest_fsync(3, OSError(errno.EIO, "io error")):
            code, out, err = self.export_fails()
        self.assertIn("may not survive a crash", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)
        self.assertFalse(self.previous.exists())

    def test_rollback_parent_fsync_is_required(self):
        # After a promotion failure, the PREV -> AOS rollback rename must
        # itself be made durable with a PATH fsync — a rollback that only
        # exists in the page cache is not a restoration.
        dest_fsyncs = []
        real_fsync = mirror_export._fsync_dest_root

        def spy(dest_fd):
            dest_fsyncs.append(dest_fd)
            return real_fsync(dest_fd)

        flaky = self.fail_on_call(
            os.rename, 2, PermissionError(errno.EACCES, "locked")
        )
        with mock.patch.object(mirror_export, "_fsync_dest_root", spy), \
                mock.patch.object(mirror_export.os, "rename", flaky):
            code, out, err = self.export_fails()
        self.assertIn("previous generation was restored", err)
        # Exactly two PATH fsyncs: after the move-aside rename and after
        # the rollback rename.
        self.assertEqual(len(dest_fsyncs), 2)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_rollback_fsync_failure_keeps_recoverable_complete_trees(self):
        # Promotion fails, the rollback rename succeeds, but the rollback
        # fsync fails: no durable-restoration claim may be made and the
        # complete new generation must NOT be discarded.
        flaky = self.fail_on_call(
            os.rename, 2, PermissionError(errno.EACCES, "locked")
        )
        with self.fail_dest_fsync(2, OSError(errno.EIO, "io error")), \
                mock.patch.object(mirror_export.os, "rename", flaky):
            code, out, err = self.export_fails()
        self.assertIn("rollback's durability could not be confirmed", err)
        self.assertNotIn("destination is unchanged", err)
        # Exact live state and the possible post-crash state are named.
        self.assertIn(f"new generation remains at {self.staging}", err)
        self.assertIn(f"the previous generation at {self.previous}", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertEqual(utils.tree_hash(self.staging), self.new_hash)
        self.assertFalse(self.previous.exists())
        self.assert_whole_generation(self.old_hash, self.new_hash)
        shutil.rmtree(self.staging)

    def test_staging_cleanup_failure_is_reported(self):
        # A validation failure whose staging cleanup ALSO fails must
        # report both: the original error and that STG remains and must be
        # removed before rerunning — never a blanket-ignored rmtree.
        planted = self.source / "Tasks" / "T-9998.md"
        planted.write_text("[[NoSuchNote]]\n")
        self.addCleanup(planted.unlink, missing_ok=True)
        rm_exc = OSError(errno.EACCES, "held open")
        with mock.patch.object(
            mirror_export, "_delete_children_pinned", side_effect=rm_exc
        ):
            code, out, err = self.export_fails()
        self.assertIn("Export validation failed", err)
        self.assertIn(f"staging {self.staging} could not be removed", err)
        self.assertIn("remove it before rerunning", err)
        self.assertTrue(self.staging.exists())
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        shutil.rmtree(self.staging)

    def test_recheck_cleanup_failure_is_reported(self):
        # Same reporting when the pre-promotion recheck refuses (late
        # destination change) and staging cleanup fails.
        target = mirror_export.check_destination(
            self.aos_dir, str(self.dest_root)
        )
        plan = mirror_export.compute_plan(self.aos_dir, target)
        late = self.dest_aos / "Tasks" / "T-9999.md"
        late.write_text("late\n")
        rm_exc = OSError(errno.EACCES, "held open")
        with mock.patch.object(
            mirror_export, "_delete_children_pinned", side_effect=rm_exc
        ):
            with self.assertRaises(AosError) as ctx:
                mirror_export.apply_plan(plan)
        msg = str(ctx.exception)
        self.assertIn("destination changed during export", msg)
        self.assertIn(f"staging {self.staging} could not be removed", msg)
        self.assertTrue(self.staging.exists())
        late.unlink()
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        shutil.rmtree(self.staging)

    def test_move_aside_cleanup_failure_is_reported(self):
        flaky = self.fail_on_call(
            os.rename, 1, PermissionError(errno.EACCES, "locked")
        )
        rm_exc = OSError(errno.EACCES, "held open")
        with mock.patch.object(mirror_export.os, "rename", flaky), \
                mock.patch.object(
                    mirror_export, "_delete_children_pinned",
                    side_effect=rm_exc,
                ):
            code, out, err = self.export_fails()
        self.assertIn("could not move the current generation aside", err)
        self.assertIn(f"staging {self.staging} could not be removed", err)
        self.assertTrue(self.staging.exists())
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        shutil.rmtree(self.staging)

    def test_recovery_commands_quote_paths_with_spaces(self):
        # The shared fixture's destination contains spaces: the printed
        # recovery commands must be shell-safe, not word-split bait.
        self.assertIn(" ", str(self.dest_root))

        def explode(*args, **kwargs):
            raise PermissionError(errno.EACCES, "locked")

        flaky = self.fail_on_call_range(os.rename, {2, 3}, explode)
        with mock.patch.object(mirror_export.os, "rename", flaky):
            code, out, err = self.export_fails()
        quoted_prev = shlex.quote(str(self.previous))
        quoted_stg = shlex.quote(str(self.staging))
        quoted_aos = shlex.quote(str(self.dest_aos))
        self.assertNotEqual(quoted_prev, str(self.previous))
        self.assertIn(f"mv {quoted_prev} {quoted_aos}", err)
        self.assertIn(f"mv {quoted_stg} {quoted_aos}", err)
        self.assertNotIn(f"mv {self.previous} {self.dest_aos}", err)
        # Follow the quoted recovery: keep the old generation.
        self.previous.rename(self.dest_aos)
        shutil.rmtree(self.staging)
        out = self.export()
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)


class TestFirstExportAtomicity(ExportCase):
    def test_first_export_promotion_failure_leaves_no_aos(self):
        flaky = self.fail_on_call(
            os.rename, 1, PermissionError(errno.EACCES, "locked")
        )
        with mock.patch.object(mirror_export.os, "rename", flaky):
            code, out, err = self.export_fails()
        self.assertIn(f"no {self.dest_aos} was created", err)
        self.assertIn("staged generation remains", err)
        self.assertFalse(self.dest_aos.exists())
        self.assertEqual(utils.tree_hash(self.staging), self.source_hash())
        shutil.rmtree(self.staging)
        out = self.export()
        self.assertEqual(utils.tree_hash(self.dest_aos), self.source_hash())

    def test_first_export_durability_failure_keeps_complete_aos(self):
        # The first-export PATH-fsync point: a fatal errno exits 1 but the
        # promoted generation is complete and current.
        with self.fail_dest_fsync(1, OSError(errno.EIO, "io error")):
            code, out, err = self.export_fails()
        self.assertIn("durability could not be confirmed", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.source_hash())
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())


# ---------------------------------------------------------------------------
# U-C4.5 — copy-if-changed


class TestCopyIfChanged(ExportCase):
    def test_identical_export_performs_zero_mutation(self):
        self.export()
        before_stats = self.stat_map(self.dest_root)
        rename_spy = mock.Mock(side_effect=os.rename)
        link_spy = mock.Mock(side_effect=os.link)
        copy_spy = mock.Mock(side_effect=shutil.copyfileobj)
        with mock.patch.object(mirror_export.os, "rename", rename_spy), \
                mock.patch.object(mirror_export.os, "link", link_spy), \
                mock.patch.object(
                    mirror_export.shutil, "copyfileobj", copy_spy
                ):
            out = self.export()
        self.assertIn("already matches the source", out)
        self.assertIn("nothing written", out)
        self.assertEqual(rename_spy.call_count, 0)
        self.assertEqual(link_spy.call_count, 0)
        self.assertEqual(copy_spy.call_count, 0)
        self.assertEqual(self.stat_map(self.dest_root), before_stats)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_hardlink_reuse_preserves_unchanged_inodes(self):
        self.require_hardlinks(self.dest_root)
        self.export()
        unchanged = self.dest_aos / "CONVENTIONS.md"
        before_ino = unchanged.stat().st_ino
        changed_before = (self.dest_aos / "Home.md").stat().st_ino
        self.aos("task", "add", "Another task", "-p", "demo")
        self.export()
        self.assertEqual(unchanged.stat().st_ino, before_ino)
        self.assertNotEqual(
            (self.dest_aos / "Home.md").stat().st_ino, changed_before
        )

    def test_hardlink_fallback_on_recognized_errno(self):
        self.export()
        self.aos("task", "add", "Another task", "-p", "demo")
        link_mock = mock.Mock(
            side_effect=OSError(errno.EPERM, "links not supported here")
        )
        with mock.patch.object(mirror_export.os, "link", link_mock):
            out = self.export()
        self.assertIn("Exported to", out)
        # The fallback actually fired: os.link was attempted, refused with
        # a recognized errno, and the export still converged bytewise.
        self.assertGreaterEqual(link_mock.call_count, 1)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.source_hash())

    def test_missing_entity_dir_is_recreated(self):
        # The empty-directory skeleton is part of the generation: a
        # pruned entity dir at the destination is not "already matches".
        self.export()
        (self.dest_aos / "Reviews").rmdir()
        out = self.export()
        self.assertIn("Exported to", out)
        self.assertNotIn("already matches", out)
        self.assertTrue((self.dest_aos / "Reviews").is_dir())

    def test_fatal_errno_on_link_aborts_with_old_generation(self):
        self.export()
        old_hash = utils.tree_hash(self.dest_aos)
        self.aos("task", "add", "Another task", "-p", "demo")
        exc = OSError(errno.EIO, "disk error")
        with mock.patch.object(
            mirror_export.os, "link", side_effect=exc
        ):
            code, out, err = self.export_fails()
        self.assertIn("Export failed while staging", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), old_hash)
        self.assertFalse(self.staging.exists())


# ---------------------------------------------------------------------------
# U-C4.6 — validation, determinism, Windows representability


class TestDeterminismAndPaths(ExportCase):
    def test_export_to_windows_drive_like_deep_unicode_path(self):
        base = self.new_tmp_dir("mnt")
        dest = (
            base / "c" / "Users" / "Some User" / "Documents"
            / "Üser Väult" / "nested" / "quite deeply" / "for a very long"
            / "destination path that would upset naive length checks"
        )
        dest.mkdir(parents=True)
        self.export(dest=dest)
        self.assertEqual(
            utils.tree_hash(dest / "AOS"), self.source_hash()
        )

    def test_unicode_note_content_round_trips(self):
        self.aos("task", "add", "Tâche unicode — 日本語 ✓", "-p", "demo")
        self.export()
        data = (self.dest_aos / "Tasks" / "T-0004.md").read_bytes()
        self.assertIn("Tâche unicode — 日本語 ✓".encode(), data)

    def test_deterministic_tree_hash_across_destinations(self):
        other_root = self.new_tmp_dir("second vault")
        self.export()
        self.export(dest=other_root)
        self.assertEqual(
            utils.tree_hash(self.dest_aos),
            utils.tree_hash(other_root / "AOS"),
        )
        self.assertEqual(utils.tree_hash(self.dest_aos), self.source_hash())

    def test_repeated_dry_run_output_is_identical(self):
        first = self.export("--dry-run")
        second = self.export("--dry-run")
        self.assertEqual(first, second)

    def test_case_fold_collision_in_source_refused(self):
        self.require_case_sensitive_fs(self.new_tmp_dir("case probe"))
        (self.source / "Agents" / "Alpha.md").write_text("stub\n")
        (self.source / "Agents" / "alpha.md").write_text("stub\n")
        code, out, err = self.export_fails()
        self.assertIn("Agents/Alpha.md", err)
        self.assertIn("Agents/alpha.md", err)
        self.assertIn("case-insensitive filesystem", err)

    def test_reserved_windows_name_refused(self):
        (self.source / "Agents" / "aux.md").write_text("stub\n")
        code, out, err = self.export_fails()
        self.assertIn("not representable on Windows", err)
        self.assertIn("reserved name 'aux'", err)

    def test_255_byte_component_exports_fine(self):
        name = "x" * 252 + ".md"
        self.assertEqual(len(name), 255)
        try:
            (self.source / "Agents" / name).write_text("stub\n")
        except OSError:
            self.skipTest("filesystem rejects 255-byte names")
        self.export()
        self.assertTrue((self.dest_aos / "Agents" / name).is_file())

    def test_unrecognized_source_entry_refused(self):
        planted = self.source / "Home.md:Zone.Identifier"
        planted.write_text("[ZoneTransfer]\n")
        code, out, err = self.export_fails()
        self.assertIn("source mirror contains unrecognized entry", err)
        self.assertIn("doctor", err)

    def test_symlink_loop_in_source_refused_without_hang(self):
        loop = self.source / "Tasks" / "loop"
        loop.symlink_to(self.source / "Tasks")
        self.addCleanup(loop.unlink, missing_ok=True)
        code, out, err = self.export_fails()
        self.assertIn("unrecognized entry", err)


class TestComponentValidator(ExportCase):
    """Unit-level pinning of the UTF-16 rule and the errno policy."""

    def test_utf16_units_count_code_units_not_bytes(self):
        self.assertEqual(mirror_export._utf16_units("abc"), 3)
        # Astral chars are surrogate pairs: 2 units each (4 UTF-8 bytes).
        self.assertEqual(mirror_export._utf16_units("\U0001f600"), 2)
        # BMP CJK: 1 unit each despite 3 UTF-8 bytes.
        self.assertEqual(mirror_export._utf16_units("一" * 200), 200)

    def test_component_length_rule_is_utf16_units(self):
        ok = mirror_export._windows_component_reason
        self.assertIsNone(ok("x" * 255))
        self.assertIn("UTF-16", ok("x" * 256))
        # 127 astral chars: 254 units (508 UTF-8 bytes) — allowed.
        self.assertIsNone(ok("\U0001f600" * 127))
        # 128 astral chars: 256 units — rejected.
        self.assertIn("UTF-16", ok("\U0001f600" * 128))
        # 200 BMP CJK chars: 200 units (600 UTF-8 bytes) — allowed.
        self.assertIsNone(ok("一" * 200))

    def test_reserved_illegal_and_trailing_rules(self):
        reason = mirror_export._windows_component_reason
        self.assertIn("reserved name", reason("aux"))
        self.assertIn("reserved name", reason("AUX.md"))
        self.assertIn("reserved name", reason("com7.tar.gz"))
        self.assertIsNone(reason("auxiliary.md"))
        self.assertIn("illegal character", reason("a<b.md"))
        self.assertIn("illegal character", reason("a:b.md"))
        self.assertIn("illegal character", reason("a\x1fb.md"))
        self.assertIn("trailing dot or space", reason("name."))
        self.assertIn("trailing dot or space", reason("name "))

    def test_errno_policy_sets_are_pinned(self):
        self.assertEqual(
            mirror_export.LINK_FALLBACK_ERRNOS,
            frozenset({
                errno.EPERM, errno.EACCES, errno.EOPNOTSUPP, errno.ENOTSUP,
                errno.ENOSYS, errno.EXDEV, errno.EMLINK,
            }),
        )
        self.assertEqual(
            mirror_export.DIR_FSYNC_SKIP_ERRNOS,
            frozenset({
                errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS,
            }),
        )

    def test_dir_fsync_skips_recognized_and_raises_fatal_errnos(self):
        target = self.new_tmp_dir("fsync-target")
        fd = os.open(target, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, fd)
        with mock.patch.object(
            mirror_export.os, "fsync",
            side_effect=OSError(errno.EINVAL, "unsupported"),
        ):
            mirror_export._fsync_dir_fd(fd)  # skipped, no raise
        with mock.patch.object(
            mirror_export.os, "fsync",
            side_effect=OSError(errno.EIO, "io error"),
        ):
            with self.assertRaises(OSError):
                mirror_export._fsync_dir_fd(fd)


# ---------------------------------------------------------------------------
# U-C4.7 — one-way / eventless / back-compat


class TestBackCompat(ExportCase):
    def test_plain_sync_output_unchanged_and_no_schema_drift(self):
        out = self.aos("sync")
        self.assertRegex(
            out, r"^Synced \d+ notes \(\d+ written, \d+ unchanged\)\.\n$"
        )
        self.assert_no_schema_drift()

    def test_export_is_eventless(self):
        before = self.event_count()
        self.export()
        self.export("--dry-run")
        self.export()
        self.assertEqual(self.event_count(), before)
        self.assert_no_schema_drift()

    def test_export_never_writes_outside_mutation_roots(self):
        marker = self.dest_root / "untouched dir"
        marker.mkdir()
        (marker / "file.txt").write_text("untouched\n")
        before_outside = {
            rel: data
            for rel, data in self.snapshot(self.dest_root).items()
            if not rel.startswith(("AOS", ".aos-export"))
        }
        self.export()
        after_outside = {
            rel: data
            for rel, data in self.snapshot(self.dest_root).items()
            if not rel.startswith(("AOS", ".aos-export"))
        }
        self.assertEqual(after_outside, before_outside)


# ---------------------------------------------------------------------------
# Review hardening — destination base snapshot and the full final recheck

#: The mandated refusal for any destination change detected between
#: planning and promotion (detail is appended in parentheses).
DEST_CHANGED_MSG = (
    "Refusing to export: destination changed during export; rerun to "
    "compute a fresh plan."
)


class MutatedExportCase(ExportCase):
    """Exported destination + changed source: the late-change fixture."""

    def setUp(self):
        super().setUp()
        self.export()
        self.old_hash = utils.tree_hash(self.dest_aos)
        self.aos("task", "add", "Late-change task", "-p", "demo")
        self.aos("sync")
        self.new_hash = self.source_hash()
        self.assertNotEqual(self.old_hash, self.new_hash)

    def plan(self):
        target = mirror_export.check_destination(
            self.aos_dir, str(self.dest_root)
        )
        return mirror_export.compute_plan(self.aos_dir, target)

    def apply_refuses_destination_changed(self, plan) -> AosError:
        with self.assertRaises(AosError) as ctx:
            mirror_export.apply_plan(plan)
        self.assertIn(DEST_CHANGED_MSG, str(ctx.exception))
        return ctx.exception


class TestDestinationSnapshot(MutatedExportCase):
    def test_plan_rescans_destination_after_adoption(self):
        # The plan must come from a FRESH destination scan: a generated-
        # shaped note added after check_destination's adoption inspection
        # (i.e. while the local mirror regenerates) must land in the plan
        # as an explicit delete, never vanish silently in the swap.
        target = mirror_export.check_destination(
            self.aos_dir, str(self.dest_root)
        )
        late = self.dest_aos / "Tasks" / "T-9999.md"
        late.write_text("added after adoption\n")
        plan = mirror_export.compute_plan(self.aos_dir, target)
        self.assertIn(
            ("Tasks/T-9999.md", late.stat().st_size), plan.deletes
        )

    def test_staging_appearing_before_planning_refuses(self):
        target = mirror_export.check_destination(
            self.aos_dir, str(self.dest_root)
        )
        self.staging.mkdir()
        with self.assertRaises(AosError) as ctx:
            mirror_export.compute_plan(self.aos_dir, target)
        self.assertIn("staging", str(ctx.exception))
        self.assertIn("already exists", str(ctx.exception))

    def test_late_destination_file_refuses_instead_of_silent_delete(self):
        plan = self.plan()
        late = self.dest_aos / "Tasks" / "T-9999.md"
        late.write_text("added after planning\n")
        self.apply_refuses_destination_changed(plan)
        self.assertEqual(late.read_text(), "added after planning\n")
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())
        # The documented recovery: the rerun computes a fresh plan that
        # SEES the file and deletes it deliberately (previewable).
        out = self.export()
        self.assertIn("Exported to", out)
        self.assertFalse(late.exists())
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)

    def test_late_destination_directory_refuses(self):
        # An UNRECOGNIZED late directory trips the adoption rescan; the
        # recheck maps that to the destination-changed refusal.
        plan = self.plan()
        intruder = self.dest_aos / "NotAnEntityDir"
        intruder.mkdir()
        self.apply_refuses_destination_changed(plan)
        self.assertTrue(intruder.is_dir())
        self.assertFalse(self.staging.exists())
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)

    def test_late_entity_directory_removal_refuses(self):
        # Removing an (adoptable, empty) entity directory after planning
        # leaves the rescan succeeding — only the base_dirs snapshot clause
        # catches it. This exercises the dir-set comparison directly, not
        # the adoption-refusal path test_late_destination_directory_refuses
        # rides.
        plan = self.plan()
        removed = self.dest_aos / "Reviews"
        self.assertEqual(sorted(os.listdir(removed)), [])  # empty in fixture
        removed.rmdir()
        exc = self.apply_refuses_destination_changed(plan)
        self.assertIn("directory set", str(exc))
        self.assertFalse(self.staging.exists())
        self.assertFalse((self.dest_aos / "Reviews").exists())

    def test_late_content_edit_refuses(self):
        # Same-size byte flip after planning: file set, sizes, dirs, and
        # sentinel all still match — only the recorded length-framed
        # content hash can catch it.
        plan = self.plan()
        note = self.dest_aos / "Home.md"
        data = bytearray(note.read_bytes())
        data[0] ^= 0x01
        note.write_bytes(bytes(data))
        self.apply_refuses_destination_changed(plan)
        self.assertFalse(self.staging.exists())
        self.assertEqual(note.read_bytes(), bytes(data))

    def test_late_sentinel_removal_refuses(self):
        # The sentinel is pruned from the file/dir inventories and invisible
        # to the content hash, so removing it after planning flips only the
        # base_sentinel snapshot dimension — its dedicated recheck clause is
        # the sole guard.
        plan = self.plan()
        (self.dest_aos / mirror_export.OWNER_SENTINEL_NAME).rmdir()
        exc = self.apply_refuses_destination_changed(plan)
        self.assertIn("ownership sentinel changed", str(exc))
        self.assertFalse(self.staging.exists())
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)

    def test_late_real_aos_replacement_refuses(self):
        # Byte-identical replacement DIRECTORY: only directory identity
        # distinguishes it — resolve-and-accept would promote over a tree
        # the plan never inspected.
        plan = self.plan()
        aside = self.new_tmp_dir("aside") / "AOS"
        self.dest_aos.rename(aside)
        shutil.copytree(aside, self.dest_aos)
        self.apply_refuses_destination_changed(plan)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())

    def test_late_aos_removal_refuses(self):
        # Removal after staging is built and validated: only the final
        # recheck can catch it (earlier removal fails the staging build).
        plan = self.plan()
        real_validate = mirror_export._validate_staging

        def validate_then_remove(*args):
            snapshot = real_validate(*args)
            shutil.rmtree(self.dest_aos)
            return snapshot

        with mock.patch.object(
            mirror_export, "_validate_staging", validate_then_remove
        ):
            with self.assertRaises(AosError) as ctx:
                mirror_export.apply_plan(plan)
        self.assertIn(DEST_CHANGED_MSG, str(ctx.exception))
        self.assertFalse(self.dest_aos.exists())
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_previous_appearing_after_plan_refuses(self):
        plan = self.plan()
        self.previous.mkdir()
        (self.previous / "foreign.txt").write_text("not ours\n")
        self.apply_refuses_destination_changed(plan)
        # The foreign PREV is never auto-cleaned; our staging is.
        self.assertEqual(
            (self.previous / "foreign.txt").read_text(), "not ours\n"
        )
        self.assertFalse(self.staging.exists())
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)

    def test_aos_appearing_after_first_export_planning_refuses(self):
        fresh_root = self.new_tmp_dir("fresh dest")
        target = mirror_export.check_destination(
            self.aos_dir, str(fresh_root)
        )
        plan = mirror_export.compute_plan(self.aos_dir, target)
        foreign = fresh_root / "AOS"
        foreign.mkdir()
        (foreign / "Home.md").write_text("someone else's\n")
        self.apply_refuses_destination_changed(plan)
        self.assertEqual(
            (foreign / "Home.md").read_text(), "someone else's\n"
        )
        self.assertFalse((fresh_root / mirror_export.STAGING_NAME).exists())

    def test_staging_root_replacement_refuses(self):
        plan = self.plan()
        real_validate = mirror_export._validate_staging

        def validate_then_swap(plan, *args):
            snapshot = real_validate(plan, *args)
            shutil.rmtree(plan.target.staging)
            plan.target.staging.mkdir()
            (plan.target.staging / "impostor.txt").write_text("not ours\n")
            return snapshot

        with mock.patch.object(
            mirror_export, "_validate_staging", validate_then_swap
        ):
            with self.assertRaises(AosError) as ctx:
                mirror_export.apply_plan(plan)
        self.assertIn(
            "removed or replaced during export", str(ctx.exception)
        )
        # The impostor is RETAINED: it is not provably ours to delete.
        self.assertEqual(
            (self.staging / "impostor.txt").read_text(), "not ours\n"
        )
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.previous.exists())
        shutil.rmtree(self.staging)


# ---------------------------------------------------------------------------
# Review hardening — ownership sentinel (provenance beyond filename shape)


class TestOwnershipSentinel(ExportCase):
    def sentinel(self) -> Path:
        return self.dest_aos / mirror_export.OWNER_SENTINEL_NAME

    def test_nonempty_generated_shaped_tree_without_owner_sentinel_refuses(
        self,
    ):
        # Filename shape is NOT proof of ownership: a human tree whose
        # names happen to look generated must never be adopted (and later
        # deleted wholesale by the swap).
        self.dest_aos.mkdir()
        (self.dest_aos / "Tasks").mkdir()
        (self.dest_aos / "Home.md").write_text("my own home note\n")
        (self.dest_aos / "Tasks" / "T-9999.md").write_text("my note\n")
        code, out, err = self.export_fails()
        self.assertIn("ownership sentinel", err)
        self.assertIn(mirror_export.OWNER_SENTINEL_NAME, err)
        self.assertEqual(out, "")  # refused before any local work
        self.assertEqual(
            (self.dest_aos / "Home.md").read_text(), "my own home note\n"
        )
        self.assertEqual(
            (self.dest_aos / "Tasks" / "T-9999.md").read_text(), "my note\n"
        )

    def test_owner_sentinel_created_and_required_on_repeat_export(self):
        self.export()
        sentinel = self.sentinel()
        self.assertTrue(sentinel.is_dir())
        self.assertFalse(sentinel.is_symlink())
        self.assertEqual(os.listdir(sentinel), [])
        # An identical repeat export accepts the sentinel (and nothing
        # else hidden) as proof of ownership.
        out = self.export()
        self.assertIn("already matches the source", out)
        # A changed export preserves the sentinel through the whole-tree
        # promotion.
        self.aos("task", "add", "Another task", "-p", "demo")
        out = self.export()
        self.assertIn("Exported to", out)
        self.assertTrue(sentinel.is_dir())
        self.assertEqual(os.listdir(sentinel), [])
        # Without the sentinel the same tree is no longer provably ours.
        sentinel.rmdir()
        code, out, err = self.export_fails()
        self.assertIn("ownership sentinel", err)
        self.assertEqual(out, "")
        # Restoring the exact sentinel restores adoption.
        sentinel.mkdir()
        out = self.export()
        self.assertIn("already matches the source", out)

    def test_sentinel_with_content_refuses(self):
        self.export()
        (self.sentinel() / "stray.txt").write_text("x\n")
        code, out, err = self.export_fails()
        self.assertIn("contains content not generated", err)
        self.assertIn(
            f"{mirror_export.OWNER_SENTINEL_NAME}/stray.txt", err
        )

    def test_sentinel_that_is_a_file_refuses(self):
        self.export()
        sentinel = self.sentinel()
        sentinel.rmdir()
        sentinel.write_text("not a directory\n")
        code, out, err = self.export_fails()
        self.assertIn("contains content not generated", err)

    def test_sentinel_that_is_a_symlink_refuses(self):
        self.export()
        sentinel = self.sentinel()
        sentinel.rmdir()
        sentinel.symlink_to(self.new_tmp_dir("elsewhere"))
        code, out, err = self.export_fails()
        self.assertIn("contains content not generated", err)

    def test_first_export_adopts_genuinely_empty_aos(self):
        self.dest_aos.mkdir()
        out = self.export()
        self.assertIn("Exported to", out)
        self.assertTrue(self.sentinel().is_dir())
        self.assertEqual(
            utils.tree_hash(self.dest_aos), self.source_hash()
        )

    def test_sentinel_not_counted_as_note_or_delete(self):
        self.export()
        out = self.export("--dry-run")
        self.assertIn("already matches the source", out)
        self.assertNotIn(mirror_export.OWNER_SENTINEL_NAME, out)


# ---------------------------------------------------------------------------
# Review hardening — lexical workspace protection with symlinked .agentic-os


class TestSymlinkedWorkspaceProtection(WeekendTestCase):
    def test_symlinked_aos_dir_still_protects_lexical_workspace(self):
        # repo/.agentic-os is a symlink elsewhere: the repository the user
        # actually works in (containing .git) must still be protected —
        # resolve-then-parent would only protect the link target's parent.
        real_root = self.new_tmp_dir("real workspace")
        code, out, err = self.run_cli("--root", str(real_root), "init")
        self.assertEqual(code, 0, err)
        lexical_repo = self.new_tmp_dir("lexical repo")
        (lexical_repo / ".git").mkdir()
        lexical_root = lexical_repo / "ws"
        lexical_root.mkdir()
        (lexical_root / utils.AOS_DIR_NAME).symlink_to(
            real_root / utils.AOS_DIR_NAME
        )
        dest = lexical_repo / "vault"
        dest.mkdir()
        code, out, err = self.run_cli(
            "--root", str(lexical_root), "sync", "--export-to", str(dest)
        )
        self.assertEqual(code, 1, out + err)
        self.assertIn("Refusing to export", err)
        self.assertIn("repository", err)
        self.assertEqual(out, "")  # refused before any local work
        self.assertEqual(sorted(dest.iterdir()), [])

    def test_symlinked_aos_dir_protects_lexical_workspace_root(self):
        # Same shape without a .git: the lexical workspace root itself
        # must refuse.
        real_root = self.new_tmp_dir("real workspace")
        code, out, err = self.run_cli("--root", str(real_root), "init")
        self.assertEqual(code, 0, err)
        holder = self.new_tmp_dir("holder")
        lexical_root = holder / "ws"
        lexical_root.mkdir()
        (lexical_root / utils.AOS_DIR_NAME).symlink_to(
            real_root / utils.AOS_DIR_NAME
        )
        dest = lexical_root / "vault"
        dest.mkdir()
        code, out, err = self.run_cli(
            "--root", str(lexical_root), "sync", "--export-to", str(dest)
        )
        self.assertEqual(code, 1, out + err)
        self.assertIn("live workspace", err)
        self.assertEqual(sorted(dest.iterdir()), [])


class TestProtectedRootProbes(WeekendTestCase):
    def test_git_marker_symlink_loop_still_protects_repository(self):
        # A `.git` self-loop makes Path.exists() report False (ELOOP), so
        # a naive probe silently DROPS the repository protection and the
        # export writes inside the repo; an EACCES/EIO on the same probe
        # would instead crash as an exit-2 internal error. The
        # fail-closed probe treats the uninspectable marker as present,
        # so the containment refusal still fires before any local work.
        holder = self.new_tmp_dir("looped repo")
        ws = holder / "ws"
        ws.mkdir()
        code, out, err = self.run_cli("--root", str(ws), "init")
        self.assertEqual(code, 0, err)
        (holder / ".git").symlink_to(holder / ".git")
        dest = holder / "vault"
        dest.mkdir()
        code, out, err = self.run_cli(
            "--root", str(ws), "sync", "--export-to", str(dest)
        )
        self.assertEqual(code, 1, out + err)
        self.assertIn("Refusing to export", err)
        self.assertIn("repository", err)
        self.assertEqual(sorted(dest.iterdir()), [])


# ---------------------------------------------------------------------------
# Review hardening — destination hardlink aliasing


class TestHardlinkAlias(ExportCase):
    def test_destination_hardlink_alias_refuses(self):
        # A destination note hardlinked to a protected source note: byte-
        # identical, recognized shape, sentinel present — only the link
        # count reveals the bytes are shared with something outside AOS.
        self.export()
        victim = self.dest_aos / "Home.md"
        source_note = self.source / "Home.md"
        victim.unlink()
        try:
            os.link(source_note, victim)
        except OSError:
            self.skipTest("cross-tree hardlinks unsupported here")
        code, out, err = self.export_fails()
        self.assertIn("hardlinked file", err)
        self.assertIn("Home.md", err)
        self.assertEqual(out, "")  # refused before any local work/mutation
        # Neither side of the alias was touched.
        self.assertEqual(os.lstat(victim).st_nlink, 2)
        self.assertTrue(
            os.path.samestat(os.lstat(victim), os.lstat(source_note))
        )

    def test_internal_hardlink_alias_refuses(self):
        self.export()
        keeper = self.dest_aos / "Tasks" / "T-0001.md"
        alias = self.dest_aos / "Tasks" / "T-0002.md"
        alias.unlink()
        try:
            os.link(keeper, alias)
        except OSError:
            self.skipTest("hardlinks unsupported here")
        code, out, err = self.export_fails()
        self.assertIn("hardlinked file", err)


# ---------------------------------------------------------------------------
# Review hardening — staged-entry typing (lstat validation)


class TestStagedEntryValidation(MutatedExportCase):
    def test_staged_symlink_file_refuses(self):
        # A staged symlink to byte-identical content elsewhere: the size
        # and hash comparisons cannot see the difference — only the lstat
        # type check can (promotion would ship the link, not the bytes).
        decoy_dir = self.new_tmp_dir("decoy")
        real_build = mirror_export._build_staging

        def build_then_symlink_file(plan, staging_fd, dest_fd):
            linked = real_build(plan, staging_fd, dest_fd)
            victim = plan.target.staging / "Home.md"
            decoy = decoy_dir / "Home.md"
            shutil.copyfile(victim, decoy)
            victim.unlink()
            victim.symlink_to(decoy)
            return linked

        with mock.patch.object(
            mirror_export, "_build_staging", build_then_symlink_file
        ):
            code, out, err = self.export_fails()
        self.assertIn("Export validation failed", err)
        self.assertIn("not a regular file", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        self.assertTrue((decoy_dir / "Home.md").is_file())

    def test_staged_symlink_empty_entity_directory_refuses(self):
        # An empty entity directory swapped for a symlink to an (equally
        # empty) directory elsewhere: the directory-set comparison would
        # match through the link — only lstat typing catches it.
        empty_elsewhere = self.new_tmp_dir("empty-entity")
        real_build = mirror_export._build_staging

        def build_then_symlink_dir(plan, staging_fd, dest_fd):
            linked = real_build(plan, staging_fd, dest_fd)
            victim = plan.target.staging / "Reviews"
            victim.rmdir()  # empty in the Night-1 fixture
            victim.symlink_to(empty_elsewhere)
            return linked

        with mock.patch.object(
            mirror_export, "_build_staging", build_then_symlink_dir
        ):
            code, out, err = self.export_fails()
        self.assertIn("Export validation failed", err)
        self.assertIn("not a real directory", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())

    def test_staged_symlink_sentinel_refuses(self):
        elsewhere = self.new_tmp_dir("sentinel-elsewhere")
        real_build = mirror_export._build_staging

        def build_then_symlink_sentinel(plan, staging_fd, dest_fd):
            linked = real_build(plan, staging_fd, dest_fd)
            victim = plan.target.staging / mirror_export.OWNER_SENTINEL_NAME
            victim.rmdir()
            victim.symlink_to(elsewhere)
            return linked

        with mock.patch.object(
            mirror_export, "_build_staging", build_then_symlink_sentinel
        ):
            code, out, err = self.export_fails()
        self.assertIn("Export validation failed", err)
        self.assertIn("ownership sentinel", err)
        self.assertFalse(self.staging.exists())

    def test_staged_fifo_refuses(self):
        # Special files refuse by lstat type BEFORE any content read — a
        # staged FIFO must not hang validation.
        real_build = mirror_export._build_staging

        def build_then_fifo(plan, staging_fd, dest_fd):
            linked = real_build(plan, staging_fd, dest_fd)
            os.mkfifo(plan.target.staging / "Reviews" / "pipe.md")
            return linked

        with mock.patch.object(
            mirror_export, "_build_staging", build_then_fifo
        ):
            code, out, err = self.export_fails()
        self.assertIn("not a regular file", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())


# ---------------------------------------------------------------------------
# Review hardening — staging-build write anchoring (symlink-swap escape)


class TestStagingBuildAnchoring(MutatedExportCase):
    def test_entity_dir_symlink_swap_during_build_never_escapes(self):
        # A same-user racer swaps a just-created staging entity directory
        # for a symlink pointing OUTSIDE the mutation roots. Writes are
        # anchored to pinned directory descriptors (O_NOFOLLOW open, O_EXCL
        # create), so the swap is refused — no note file is ever created in
        # the symlink target, and the live destination is untouched.
        escape = self.new_tmp_dir("escape target")
        real_mkdir = os.mkdir

        def swapping_mkdir(path, *args, dir_fd=None, **kwargs):
            real_mkdir(path, *args, dir_fd=dir_fd, **kwargs)
            if path == "Tasks" and dir_fd is not None:
                # Between our mkdir and our O_NOFOLLOW open of the entity
                # dir, replace it with a symlink out of the tree.
                os.rmdir(path, dir_fd=dir_fd)
                os.symlink(str(escape), path, dir_fd=dir_fd)

        with mock.patch.object(mirror_export.os, "mkdir", swapping_mkdir):
            code, out, err = self.export_fails()
        # The build refused (ELOOP on the O_NOFOLLOW open); nothing escaped.
        self.assertEqual(sorted(escape.iterdir()), [])
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_note_at_swapped_name_is_not_clobbered(self):
        # O_EXCL means a symlink raced into a note's own target name is
        # never written through: the build fails rather than following it.
        outside = self.new_tmp_dir("outside") / "victim.md"
        outside.write_text("pre-existing outside content\n")
        real_copy = mirror_export._copy_into_staging
        state = {"done": False}

        def copy_then_plant(plan, source_fd, src_entity_fds, rel, name,
                            dir_fd):
            # Before the first real staged copy, plant a symlink at the next
            # note's name so the create must refuse it.
            if not state["done"] and name.endswith(".md"):
                state["done"] = True
                os.symlink(str(outside), name, dir_fd=dir_fd)
                # The real create now hits O_EXCL against the symlink.
            return real_copy(
                plan, source_fd, src_entity_fds, rel, name, dir_fd
            )

        with mock.patch.object(
            mirror_export, "_copy_into_staging", copy_then_plant
        ):
            code, out, err = self.export_fails()
        self.assertEqual(
            outside.read_text(), "pre-existing outside content\n"
        )
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())


# ---------------------------------------------------------------------------
# Review hardening — staged-hardlink tolerance (the samestat half of fix 8)


class TestStagingAliasTolerance(ExportCase):
    def test_staging_alias_only_requires_samestat_identity(self):
        base = self.new_tmp_dir("alias unit")
        real = base / "Tasks" / "T-0001.md"
        real.parent.mkdir()
        real.write_text("note\n")
        staging = base / mirror_export.STAGING_NAME
        (staging / "Tasks").mkdir(parents=True)
        rel = Path("Tasks/T-0001.md")

        staging_fd = os.open(staging, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, staging_fd)

        # nlink != 2 is never the single-staged-alias case.
        three = base / "third-link"
        os.link(real, staging / "Tasks" / "T-0001.md")  # the staged alias
        os.link(real, three)  # a THIRD, external link -> nlink 3
        self.addCleanup(three.unlink, missing_ok=True)
        self.assertEqual(os.lstat(real).st_nlink, 3)
        self.assertFalse(
            mirror_export._staging_alias_only(
                os.lstat(real), staging_fd, rel
            )
        )
        three.unlink()

        # No staging context at all (adoption scan): never tolerated —
        # asserted WHILE the file has nlink == 2 and a matching staged
        # alias exists, so only the staging_fd-is-None guard can refuse.
        self.assertEqual(os.lstat(real).st_nlink, 2)
        self.assertFalse(
            mirror_export._staging_alias_only(os.lstat(real), None, rel)
        )

        # nlink == 2 AND the second link IS the staged copy: tolerated.
        self.assertTrue(
            mirror_export._staging_alias_only(
                os.lstat(real), staging_fd, rel
            )
        )

    def test_staging_alias_probe_refuses_symlinked_entity_dir(self):
        # The staged-alias probe must not verify a hardlink through an
        # unresolved intermediate component: with the staging entity
        # directory swapped for a symlink that still leads to the staged
        # copy, the O_NOFOLLOW entity open refuses (ELOOP) and the alias
        # is NOT tolerated — even though a pathname probe would have
        # resolved to the very same inode.
        base = self.new_tmp_dir("alias symlink probe")
        real = base / "Tasks" / "T-0001.md"
        real.parent.mkdir()
        real.write_text("note\n")
        staging = base / mirror_export.STAGING_NAME
        moved = base / "moved-tasks"
        moved.mkdir()
        staging.mkdir()
        os.link(real, moved / "T-0001.md")  # the staged alias, moved out
        (staging / "Tasks").symlink_to(moved)
        staging_fd = os.open(staging, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, staging_fd)
        self.assertEqual(os.lstat(real).st_nlink, 2)
        self.assertFalse(
            mirror_export._staging_alias_only(
                os.lstat(real), staging_fd, Path("Tasks/T-0001.md")
            )
        )

    def test_staging_alias_only_rejects_foreign_second_link(self):
        # nlink == 2 but the second link is NOT the staged copy (the staged
        # path is an independent inode): samestat fails, so it is refused —
        # this is the discriminating case the tolerance must not wave
        # through.
        base = self.new_tmp_dir("alias foreign")
        real = base / "Tasks" / "T-0001.md"
        real.parent.mkdir()
        real.write_text("note\n")
        foreign = base / "foreign-link"
        os.link(real, foreign)  # external second link -> nlink 2
        self.addCleanup(foreign.unlink, missing_ok=True)
        staging = base / mirror_export.STAGING_NAME
        (staging / "Tasks").mkdir(parents=True)
        # Independent staged copy (different inode), same relpath.
        shutil.copyfile(real, staging / "Tasks" / "T-0001.md")
        staging_fd = os.open(staging, os.O_RDONLY | os.O_DIRECTORY)
        self.addCleanup(os.close, staging_fd)
        self.assertEqual(os.lstat(real).st_nlink, 2)
        self.assertFalse(
            mirror_export._staging_alias_only(
                os.lstat(real), staging_fd, Path("Tasks/T-0001.md")
            )
        )

    def test_late_external_hardlink_on_changed_file_refuses(self):
        # End-to-end: an external hardlink planted after planning on a
        # CHANGED file (staging COPIED it, so the staged inode differs) is a
        # nlink==2 file whose second link is foreign — the recheck's
        # samestat guard must refuse it, not tolerate it.
        self.export()  # first export so there is a generation to update
        self.aos("task", "add", "Changer", "-p", "demo")
        self.aos("sync")
        target = mirror_export.check_destination(
            self.aos_dir, str(self.dest_root)
        )
        plan = mirror_export.compute_plan(self.aos_dir, target)
        changed = self.dest_aos / "Home.md"  # Home.md updates every task add
        self.assertTrue(any(rel == "Home.md" for rel, _ in plan.updates))
        foreign = self.new_tmp_dir("foreign") / "alias"
        try:
            os.link(changed, foreign)
        except OSError:
            self.skipTest("cross-tree hardlinks unsupported here")
        with self.assertRaises(AosError) as ctx:
            mirror_export.apply_plan(plan)
        # The recheck rescan sees the foreign alias (nlink 2, not the staged
        # inode) and refuses via the destination-changed path.
        msg = str(ctx.exception)
        self.assertTrue(
            "hardlinked file" in msg or "destination changed" in msg, msg
        )
        self.assertFalse(self.staging.exists())


# ---------------------------------------------------------------------------
# Third corrective pass — F1: the destination is pinned before any write


class TestPinnedDestination(MutatedExportCase):
    def test_dest_root_replacement_before_apply_never_writes_outside(self):
        # PATH is renamed away and an impostor directory appears at the
        # same pathname between planning and apply. The apply pins PATH
        # by descriptor identity BEFORE its first mutation, so it must
        # refuse without creating a single entry in the impostor or in
        # the moved-away original.
        plan = self.plan()
        moved = self.new_tmp_dir("moved-away holder") / "original root"
        self.dest_root.rename(moved)
        self.dest_root.mkdir()
        impostor_before = self.snapshot(self.dest_root)
        moved_before = self.snapshot(moved)
        with self.assertRaises(AosError) as ctx:
            mirror_export.apply_plan(plan)
        self.assertIn(DEST_CHANGED_MSG, str(ctx.exception))
        self.assertEqual(self.snapshot(self.dest_root), impostor_before)
        self.assertEqual(self.snapshot(moved), moved_before)

    def test_staging_symlink_swap_between_mkdir_and_open_never_writes_outside(
        self,
    ):
        # A racer replaces the just-created staging directory with a
        # symlink out of the destination before the export opens it. The
        # O_NOFOLLOW open relative to the pinned PATH descriptor must
        # refuse (ELOOP) — nothing may appear in the symlink target, and
        # the racer's symlink is retained (it is not ours to delete).
        escape = self.new_tmp_dir("escape target")
        real_mkdir = os.mkdir

        def swapping_mkdir(path, *args, dir_fd=None, **kwargs):
            real_mkdir(path, *args, dir_fd=dir_fd, **kwargs)
            if path == mirror_export.STAGING_NAME and dir_fd is not None:
                os.rmdir(path, dir_fd=dir_fd)
                os.symlink(str(escape), path, dir_fd=dir_fd)

        with mock.patch.object(mirror_export.os, "mkdir", swapping_mkdir):
            code, out, err = self.export_fails()
        self.assertIn("replaced between creation and open", err)
        self.assertEqual(sorted(escape.iterdir()), [])
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.previous.exists())
        self.assertTrue(os.path.islink(self.staging))
        os.unlink(self.staging)

    def test_staging_root_open_uses_nofollow(self):
        # The staging-root open must carry O_NOFOLLOW | O_DIRECTORY and be
        # dir_fd-relative to the pinned destination descriptor — the exact
        # flags are what turns the mkdir/open race into a refusal.
        opened = []
        real_open = os.open

        def spy(path, flags, *args, **kwargs):
            if path == mirror_export.STAGING_NAME and (
                kwargs.get("dir_fd") is not None
            ):
                opened.append(flags)
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(mirror_export.os, "open", spy):
            out = self.export()
        self.assertIn("Exported to", out)
        self.assertTrue(opened)
        self.assertTrue(opened[0] & os.O_NOFOLLOW)
        self.assertTrue(opened[0] & os.O_DIRECTORY)

    def test_promotion_renames_are_fd_anchored(self):
        # PATH's pathname is swapped for a decoy INSIDE the accepted
        # window (after the final verification returns). The promotion
        # renames are dir_fd-relative to the pinned descriptor, so the
        # swap must not divert a single rename into the decoy: the export
        # completes inside the directory the user originally approved.
        plan = self.plan()
        moved = self.new_tmp_dir("moved during window") / "original root"
        real_verify = mirror_export._verify_staging_final

        def verify_then_swap(*args):
            real_verify(*args)
            self.dest_root.rename(moved)
            self.dest_root.mkdir()

        with mock.patch.object(
            mirror_export, "_verify_staging_final", verify_then_swap
        ):
            result = mirror_export.apply_plan(plan)
        self.assertIsNone(result.cleanup_warning)
        self.assertEqual(utils.tree_hash(moved / "AOS"), self.new_hash)
        self.assertEqual(sorted(self.dest_root.iterdir()), [])
        self.assertFalse((moved / mirror_export.STAGING_NAME).exists())
        self.assertFalse((moved / mirror_export.PREVIOUS_NAME).exists())

    def test_path_swap_after_recheck_refuses(self):
        # PATH replaced between the destination recheck and the end of
        # the staging verification: the structural guard at the end of
        # the final verification must refuse before any rename.
        plan = self.plan()
        moved = self.new_tmp_dir("swap holder") / "original root"
        real_recheck = mirror_export._recheck_target

        def recheck_then_swap(*args):
            result = real_recheck(*args)
            self.dest_root.rename(moved)
            self.dest_root.mkdir()
            return result

        with mock.patch.object(
            mirror_export, "_recheck_target", recheck_then_swap
        ):
            with self.assertRaises(AosError) as ctx:
                mirror_export.apply_plan(plan)
        self.assertIn(DEST_CHANGED_MSG, str(ctx.exception))
        # Refused before promotion: the pinned (moved) directory still
        # holds the old generation; the decoy stays empty; staging was
        # discarded from the pinned directory.
        self.assertEqual(utils.tree_hash(moved / "AOS"), self.old_hash)
        self.assertEqual(sorted(self.dest_root.iterdir()), [])
        self.assertFalse((moved / mirror_export.STAGING_NAME).exists())
        self.assertFalse((moved / mirror_export.PREVIOUS_NAME).exists())

    def test_staging_swap_during_build_is_retained(self):
        # Staging is swapped for a foreign directory while the export is
        # still building/validating: the failure path must NOT delete the
        # foreign tree — discarding requires identity proof against the
        # pinned staging descriptor.
        real_build = mirror_export._build_staging

        def build_then_swap(plan, staging_fd, dest_fd):
            linked = real_build(plan, staging_fd, dest_fd)
            shutil.rmtree(plan.target.staging)
            plan.target.staging.mkdir()
            (plan.target.staging / "impostor.txt").write_text("not ours\n")
            return linked

        with mock.patch.object(
            mirror_export, "_build_staging", build_then_swap
        ):
            code, out, err = self.export_fails()
        self.assertIn(
            "no longer the staging directory this run created", err
        )
        self.assertIn("NOT removed", err)
        self.assertEqual(
            (self.staging / "impostor.txt").read_text(), "not ours\n"
        )
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.previous.exists())
        shutil.rmtree(self.staging)


# ---------------------------------------------------------------------------
# Third corrective pass — F2: the complete staging generation is re-verified
# against the validated snapshot immediately before promotion


class TestPostValidationTamper(MutatedExportCase):
    def tamper_after_validation(self, tamper):
        real = mirror_export._validate_staging

        def wrapped(*args, **kwargs):
            snapshot = real(*args, **kwargs)
            tamper()
            return snapshot

        return mock.patch.object(mirror_export, "_validate_staging", wrapped)

    def assert_refused_untouched(self, err: str, fragment: str) -> None:
        self.assertIn(fragment, err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_post_validation_content_change_refuses(self):
        # Same-size byte flip in a staged file after validation passed:
        # only the snapshot's length-framed content hash can catch it.
        def tamper():
            victim = self.staging / "Home.md"
            data = bytearray(victim.read_bytes())
            data[0] ^= 0x01
            victim.write_bytes(bytes(data))

        with self.tamper_after_validation(tamper):
            code, out, err = self.export_fails()
        self.assert_refused_untouched(
            err, "staged generation changed after validation: file content"
        )

    def test_post_validation_sentinel_removal_refuses(self):
        def tamper():
            (self.staging / mirror_export.OWNER_SENTINEL_NAME).rmdir()

        with self.tamper_after_validation(tamper):
            code, out, err = self.export_fails()
        self.assert_refused_untouched(err, "ownership sentinel changed")

    def test_post_validation_extra_file_refuses(self):
        def tamper():
            (self.staging / "Tasks" / "T-7777.md").write_text("planted\n")

        with self.tamper_after_validation(tamper):
            code, out, err = self.export_fails()
        self.assert_refused_untouched(
            err,
            "staged generation changed after validation: the file set",
        )

    def test_post_validation_symlink_change_refuses(self):
        # A staged file swapped for a symlink to byte-identical content
        # elsewhere after validation: the lstat-typed rescan must refuse
        # before any content read.
        decoy_dir = self.new_tmp_dir("post-validation decoy")

        def tamper():
            victim = self.staging / "Home.md"
            decoy = decoy_dir / "Home.md"
            shutil.copyfile(victim, decoy)
            victim.unlink()
            victim.symlink_to(decoy)

        with self.tamper_after_validation(tamper):
            code, out, err = self.export_fails()
        self.assert_refused_untouched(err, "not a regular file")
        self.assertTrue((decoy_dir / "Home.md").is_file())

    def test_source_change_after_validation_refuses(self):
        # The final verification re-scans the SOURCE too: a mirror
        # regenerated between validation and promotion must refuse, not
        # silently promote the stale (already-validated) generation.
        def tamper():
            (self.source / "Home.md").write_bytes(
                b"# regenerated after validation\n"
            )

        with self.tamper_after_validation(tamper):
            code, out, err = self.export_fails()
        self.assertIn("staged tree does not match the source", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())
        self.aos("sync")  # heal the source mirror


# ---------------------------------------------------------------------------
# Third corrective pass — F3: staged hardlink relationships are constrained


class TestStagedHardlinkConstraints(MutatedExportCase):
    def build_then(self, after):
        real_build = mirror_export._build_staging

        def wrapped(plan, staging_fd, dest_fd):
            linked = real_build(plan, staging_fd, dest_fd)
            after(plan, linked.linked)
            return linked

        return mock.patch.object(mirror_export, "_build_staging", wrapped)

    def test_staged_external_hardlink_alias_refuses(self):
        # A foreign alias planted on a staged CREATED file (nlink 2, not
        # recorded as intentionally linked) must refuse validation.
        self.require_hardlinks(self.dest_root)
        outside = self.new_tmp_dir("alias holder")

        def plant(plan, linked):
            self.assertTrue(plan.creates)
            created_rel = plan.creates[0][0]
            self.assertNotIn(created_rel, linked)
            os.link(plan.target.staging / created_rel, outside / "alias")

        with self.build_then(plant):
            code, out, err = self.export_fails()
        self.assertIn("staged file has 2 hardlinks", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_staged_changed_file_external_hardlink_refuses(self):
        # Same for an UPDATED file: staging copied it, so any second link
        # is foreign by construction.
        self.require_hardlinks(self.dest_root)
        outside = self.new_tmp_dir("alias holder")

        def plant(plan, linked):
            self.assertIn("Home.md", {rel for rel, _ in plan.updates})
            self.assertNotIn("Home.md", linked)
            os.link(plan.target.staging / "Home.md", outside / "alias")

        with self.build_then(plant):
            code, out, err = self.export_fails()
        self.assertIn("Home.md: staged file has 2 hardlinks", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())

    def test_staged_unchanged_expected_hardlink_is_allowed(self):
        # The one legitimate nlink==2 case: an unchanged file the build
        # itself linked from the current generation. The export completes
        # and the unchanged inode is preserved.
        self.require_hardlinks(self.dest_root)
        unchanged = self.dest_aos / "CONVENTIONS.md"
        before_ino = unchanged.stat().st_ino
        out = self.export()
        self.assertIn("Exported to", out)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)
        self.assertEqual(
            (self.dest_aos / "CONVENTIONS.md").stat().st_ino, before_ino
        )

    def test_staged_unchanged_foreign_second_link_refuses(self):
        # Hardlinks "unsupported" (recognized errno) => unchanged files are
        # COPIED and must have nlink 1. A foreign second link on such a
        # staged copy is exactly what inferring ownership from link count
        # would wave through — the recorded-links check must refuse it.
        self.require_hardlinks(self.dest_root)
        outside = self.new_tmp_dir("foreign holder")

        def plant(plan, linked):
            self.assertEqual(linked, {})
            os.link(
                plan.target.staging / "CONVENTIONS.md", outside / "foreign"
            )

        real_build = mirror_export._build_staging

        def wrapped(plan, staging_fd, dest_fd):
            with mock.patch.object(
                mirror_export.os, "link",
                side_effect=OSError(errno.EPERM, "links unsupported"),
            ):
                linked = real_build(plan, staging_fd, dest_fd)
            plant(plan, linked.linked)
            return linked

        with mock.patch.object(mirror_export, "_build_staging", wrapped):
            code, out, err = self.export_fails()
        self.assertIn("CONVENTIONS.md: staged file has 2 hardlinks", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())

    def test_staged_linked_extra_alias_refuses(self):
        # An intentionally linked unchanged file gains a THIRD link: the
        # exact-count rule (2: destination + staged) must refuse. The
        # capability probe stays OUTSIDE the in-process CLI run — an
        # exception raised inside the seam would surface as an exit-2
        # internal error, not a skip.
        self.require_hardlinks(self.dest_root)
        outside = self.new_tmp_dir("third link holder")
        planted = {"done": False}
        real_build = mirror_export._build_staging

        def build_then_third_link(plan, staging_fd, dest_fd):
            linked = real_build(plan, staging_fd, dest_fd)
            if "CONVENTIONS.md" in linked.linked:
                os.link(
                    plan.target.staging / "CONVENTIONS.md",
                    outside / "third",
                )
                planted["done"] = True
            return linked

        with mock.patch.object(
            mirror_export, "_build_staging", build_then_third_link
        ):
            code, out, err = self.run_cli(
                "--root", str(self.root),
                "sync", "--export-to", str(self.dest_root),
            )
        if not planted["done"]:
            self.skipTest("hardlink reuse unsupported here")
        self.assertEqual(code, 1, out + err)
        self.assertIn("staged hardlink has 3 links", err)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())

    def test_staged_link_dest_replacement_after_validation_refuses(self):
        # An unchanged file's DESTINATION inode is replaced with a
        # byte-identical copy after validation: sizes, hashes, and the
        # recorded staged identity all still match — only the final
        # verification's samestat against the CURRENT AOS file catches
        # the broken hardlink relationship.
        self.require_hardlinks(self.dest_root)
        aside = self.dest_root / "aside copy"
        conv = self.dest_aos / "CONVENTIONS.md"
        real_validate = mirror_export._validate_staging

        def validate_then_replace_dest(*args):
            snapshot = real_validate(*args)
            if "CONVENTIONS.md" in snapshot.linked:
                conv.rename(aside)
                shutil.copyfile(aside, conv)
            return snapshot

        with mock.patch.object(
            mirror_export, "_validate_staging", validate_then_replace_dest
        ):
            code, out, err = self.run_cli(
                "--root", str(self.root),
                "sync", "--export-to", str(self.dest_root),
            )
        if not aside.exists():
            self.skipTest("hardlink reuse unsupported here")
        self.assertEqual(code, 1, out + err)
        self.assertIn(DEST_CHANGED_MSG, err)
        self.assertIn("was replaced", err)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())
        aside.unlink()


# ---------------------------------------------------------------------------
# Third corrective pass — F4: inspection errors are errors, not absence


class TestInspectionErrors(MutatedExportCase):
    def flaky_lstat(self, match):
        real = os.lstat

        def wrapper(path, *args, **kwargs):
            if match(path, kwargs):
                raise OSError(errno.EIO, "injected io error")
            return real(path, *args, **kwargs)

        return mock.patch.object(mirror_export.os, "lstat", wrapper)

    def test_staging_lstat_eio_fails_closed(self):
        # EIO probing STG during the initial stale-state check must refuse
        # naming the cause — never read as "absent" and proceed.
        before = self.snapshot(self.dest_root)
        with self.flaky_lstat(
            lambda path, kwargs: str(path).endswith(
                mirror_export.STAGING_NAME
            )
            and kwargs.get("dir_fd") is None
        ):
            code, out, err = self.export_fails()
        self.assertIn("cannot inspect", err)
        self.assertIn(mirror_export.STAGING_NAME, err)
        self.assertNotIn("already exists", err)
        self.assertEqual(out, "")  # refused before any local work
        self.assertEqual(self.snapshot(self.dest_root), before)

    def test_previous_lstat_eio_fails_closed(self):
        before = self.snapshot(self.dest_root)
        with self.flaky_lstat(
            lambda path, kwargs: str(path).endswith(
                mirror_export.PREVIOUS_NAME
            )
            and kwargs.get("dir_fd") is None
        ):
            code, out, err = self.export_fails()
        self.assertIn("cannot inspect", err)
        self.assertIn(mirror_export.PREVIOUS_NAME, err)
        self.assertEqual(out, "")
        self.assertEqual(self.snapshot(self.dest_root), before)

    def test_final_previous_lstat_eio_fails_closed(self):
        # EIO probing PREV at the final recheck (fd-relative) must refuse;
        # staging is still provably ours, so it is discarded as usual.
        plan = self.plan()
        with self.flaky_lstat(
            lambda path, kwargs: str(path) == mirror_export.PREVIOUS_NAME
            and kwargs.get("dir_fd") is not None
        ):
            with self.assertRaises(AosError) as ctx:
                mirror_export.apply_plan(plan)
        msg = str(ctx.exception)
        self.assertIn("cannot inspect", msg)
        self.assertIn(mirror_export.PREVIOUS_NAME, msg)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_recheck_staging_lstat_eio_retains_staging(self):
        # EIO probing STG at the final recheck: staging is no longer
        # provably ours, so the refusal must RETAIN it.
        plan = self.plan()
        with self.flaky_lstat(
            lambda path, kwargs: str(path) == mirror_export.STAGING_NAME
            and kwargs.get("dir_fd") is not None
        ):
            with self.assertRaises(AosError) as ctx:
                mirror_export.apply_plan(plan)
        msg = str(ctx.exception)
        self.assertIn("cannot inspect", msg)
        self.assertIn("left in place", msg)
        self.assertTrue(self.staging.is_dir())
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        shutil.rmtree(self.staging)

    def second_lstat_eio(self, suffix):
        """EIO on the SECOND pathname lstat of the matching path — the
        first is the mutation-root probe, the second is _refuse_stale's
        own stale-state probe."""
        real = os.lstat
        seen = {"n": 0}

        def wrapper(path, *args, **kwargs):
            if str(path).endswith(suffix) and kwargs.get("dir_fd") is None:
                seen["n"] += 1
                if seen["n"] == 2:
                    raise OSError(errno.EIO, "injected io error")
            return real(path, *args, **kwargs)

        return mock.patch.object(mirror_export.os, "lstat", wrapper)

    def test_stale_staging_check_lstat_eio_fails_closed(self):
        # The stale-state probe itself must fail closed: a lexists-style
        # regression would swallow the error and proceed with the export.
        before = self.snapshot(self.dest_root)
        with self.second_lstat_eio(mirror_export.STAGING_NAME):
            code, out, err = self.export_fails()
        self.assertIn("cannot inspect", err)
        self.assertIn(mirror_export.STAGING_NAME, err)
        self.assertEqual(out, "")
        self.assertEqual(self.snapshot(self.dest_root), before)

    def test_stale_previous_check_lstat_eio_fails_closed(self):
        before = self.snapshot(self.dest_root)
        with self.second_lstat_eio(mirror_export.PREVIOUS_NAME):
            code, out, err = self.export_fails()
        self.assertIn("cannot inspect", err)
        self.assertIn(mirror_export.PREVIOUS_NAME, err)
        self.assertEqual(out, "")
        self.assertEqual(self.snapshot(self.dest_root), before)


# ---------------------------------------------------------------------------
# Third corrective pass — F5: the ownership sentinel directory is fsynced


class TestSentinelDurability(ExportCase):
    def test_owner_sentinel_directory_is_fsynced(self):
        fsynced = []
        real = mirror_export._fsync_dir_fd

        def spy(fd):
            st = os.fstat(fd)
            fsynced.append((st.st_dev, st.st_ino))
            return real(fd)

        with mock.patch.object(mirror_export, "_fsync_dir_fd", spy):
            out = self.export()
        self.assertIn("Exported to", out)
        sentinel_stat = os.lstat(
            self.dest_aos / mirror_export.OWNER_SENTINEL_NAME
        )
        # Whole-tree promotion preserves the staged sentinel's inode: the
        # fsynced descriptor identity must match the live sentinel.
        self.assertIn(
            (sentinel_stat.st_dev, sentinel_stat.st_ino), fsynced
        )

    def test_sentinel_symlink_swap_between_mkdir_and_open_refuses(self):
        # The sentinel is reopened O_NOFOLLOW relative to the pinned
        # staging descriptor: a symlink raced into its name between mkdir
        # and open must refuse (ELOOP), never be followed.
        escape = self.new_tmp_dir("sentinel escape")
        real_mkdir = os.mkdir

        def swapping_mkdir(path, *args, dir_fd=None, **kwargs):
            real_mkdir(path, *args, dir_fd=dir_fd, **kwargs)
            if (
                path == mirror_export.OWNER_SENTINEL_NAME
                and dir_fd is not None
            ):
                os.rmdir(path, dir_fd=dir_fd)
                os.symlink(str(escape), path, dir_fd=dir_fd)

        with mock.patch.object(mirror_export.os, "mkdir", swapping_mkdir):
            code, out, err = self.export_fails()
        self.assertIn("Export failed while staging", err)
        self.assertEqual(sorted(escape.iterdir()), [])
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.dest_aos.exists())


# ---------------------------------------------------------------------------
# Third corrective pass — F6: mounted / cross-device subtrees refuse


class TestMountedSubtrees(ExportCase):
    def test_destination_mounted_subtree_refuses(self):
        self.export()
        planted = self.dest_aos / "Tasks"
        before = self.snapshot(self.dest_root)
        with mock.patch.object(
            mirror_export.os.path, "ismount",
            lambda path: Path(path) == planted,
        ):
            code, out, err = self.export_fails()
        self.assertIn("mounted or cross-device subtree", err)
        self.assertIn("Tasks", err)
        self.assertEqual(out, "")  # refused before any local work
        self.assertEqual(self.snapshot(self.dest_root), before)

    def test_staging_mounted_subtree_refuses(self):
        self.export()
        self.aos("task", "add", "Mount case", "-p", "demo")
        old_hash = utils.tree_hash(self.dest_aos)
        planted = self.staging / "Tasks"
        with mock.patch.object(
            mirror_export.os.path, "ismount",
            lambda path: Path(path) == planted,
        ):
            code, out, err = self.export_fails()
        self.assertIn("mounted or cross-device subtree inside staging", err)
        # The cleanup sweep also refuses to recurse a delete across the
        # mount boundary: staging is retained and the error says so.
        self.assertIn("could not be removed", err)
        self.assertTrue(self.staging.is_dir())
        self.assertEqual(utils.tree_hash(self.dest_aos), old_hash)
        self.assertFalse(self.previous.exists())
        shutil.rmtree(self.staging)

    def test_previous_cleanup_mounted_subtree_warns_and_retains(self):
        # A mount appearing inside PREV during the promotion window: the
        # cleanup sweep must refuse to recurse the delete across it. The
        # export itself succeeded, so this is the WARN path (exit 0) with
        # PREV retained.
        self.export()
        self.aos("task", "add", "Prev mount case", "-p", "demo")
        planted = self.previous / "Tasks"
        with mock.patch.object(
            mirror_export.os.path, "ismount",
            lambda path: Path(path) == planted,
        ):
            code, out, err = self.run_cli(
                "--root", str(self.root),
                "sync", "--export-to", str(self.dest_root),
            )
        self.assertEqual(code, 0, out + err)
        self.assertIn("WARN: could not remove previous generation", err)
        self.assertIn("mount boundary", err)
        self.assertIn("Exported to", out)
        self.assertTrue(self.previous.is_dir())
        self.assertEqual(utils.tree_hash(self.dest_aos), self.source_hash())
        shutil.rmtree(self.previous)

    def test_dest_aos_root_mount_refuses(self):
        # PATH/AOS itself being a mount point refuses before any local
        # work: the whole-tree promotion rename cannot cross filesystems.
        self.export()
        with mock.patch.object(
            mirror_export.os.path, "ismount",
            lambda path: Path(path) == self.dest_aos,
        ):
            code, out, err = self.export_fails()
        self.assertIn("is a mount point or on a different filesystem", err)
        self.assertEqual(out, "")


# ---------------------------------------------------------------------------
# Fourth corrective pass — C1: identity-safe descriptor-anchored cleanup


class TestCleanupIdentity(MutatedExportCase):
    FOREIGN = {
        "Keep/precious.txt": b"precious replacement bytes\n",
        "top.txt": b"top-level replacement bytes\n",
    }

    def plant_foreign(self, root: Path) -> None:
        root.mkdir()
        (root / "Keep").mkdir()
        for rel, data in self.FOREIGN.items():
            (root / rel).write_bytes(data)

    def assert_foreign_intact(self, root: Path) -> None:
        """Every file name present, every byte sequence unchanged."""
        found = {
            p.relative_to(root).as_posix(): p.read_bytes()
            for p in sorted(root.rglob("*"))
            if p.is_file()
        }
        self.assertEqual(found, self.FOREIGN)

    def test_staging_cleanup_root_substitution_never_deletes_replacement(
        self,
    ):
        # Staging is substituted with a foreign directory AFTER its
        # identity was verified (at creation) and BEFORE the failure-path
        # cleanup: the recursive delete must act only on the exact
        # directory whose identity was proven, so the replacement is
        # retained byte-for-byte.
        def substitute_then_fail(plan, *args):
            shutil.rmtree(plan.target.staging)
            self.plant_foreign(plan.target.staging)
            raise mirror_export._validation_failure("injected failure")

        with mock.patch.object(
            mirror_export, "_verify_staging_final", substitute_then_fail
        ):
            code, out, err = self.export_fails()
        self.assertIn(
            "no longer the staging directory this run created", err
        )
        self.assertIn("NOT removed", err)
        self.assert_foreign_intact(self.staging)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.previous.exists())
        shutil.rmtree(self.staging)

    def test_previous_cleanup_root_substitution_never_deletes_replacement(
        self,
    ):
        # PREV is substituted with a foreign directory between the
        # post-promotion fsync and the final cleanup: the recorded PREV
        # identity no longer matches, so the replacement is retained
        # byte-for-byte and reported (exit 0 with a WARN).
        real_fsync = mirror_export._fsync_dest_root
        calls = {"n": 0}

        def fsync_then_substitute(dest_fd):
            calls["n"] += 1
            real_fsync(dest_fd)
            if calls["n"] == 2:  # the fsync after STG -> AOS promotion
                shutil.rmtree(self.previous)
                self.plant_foreign(self.previous)

        with mock.patch.object(
            mirror_export, "_fsync_dest_root", fsync_then_substitute
        ):
            code, out, err = self.run_cli(
                "--root", str(self.root),
                "sync", "--export-to", str(self.dest_root),
            )
        self.assertEqual(code, 0, out + err)
        self.assertIn("WARN: could not remove previous generation", err)
        self.assertIn("retained", err)
        self.assertIn("Exported to", out)
        self.assert_foreign_intact(self.previous)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)
        shutil.rmtree(self.previous)

    def test_previous_identity_recorded_immediately_after_move_aside(self):
        # The identity the PREV cleanup is anchored to must be exactly
        # the AOS root directory that was moved aside — recorded at the
        # rename, not re-derived later from the mutable PREV pathname.
        aos_before = os.lstat(self.dest_aos)
        captured = {}
        real_rm = mirror_export._rmtree_pinned

        def spy(path, *, name, dir_fd, expected):
            if name == mirror_export.PREVIOUS_NAME:
                captured["expected"] = expected
            return real_rm(path, name=name, dir_fd=dir_fd, expected=expected)

        with mock.patch.object(mirror_export, "_rmtree_pinned", spy):
            out = self.export()
        self.assertIn("Exported to", out)
        self.assertTrue(
            os.path.samestat(captured["expected"], aos_before)
        )
        self.assertFalse(self.previous.exists())

    def test_cleanup_retains_unproven_root(self):
        # The identity pin right after the AOS -> PREV rename fails
        # (mocked EIO on the O_NOFOLLOW open): PREV ownership is
        # unproven, so cleanup must retain the complete tree and report
        # it — never guess. The recording open is the only
        # _open_dir_nofollow call against the PREV name.
        real_open = mirror_export._open_dir_nofollow

        def flaky_open(name, dir_fd):
            if name == mirror_export.PREVIOUS_NAME:
                raise OSError(errno.EIO, "injected io error")
            return real_open(name, dir_fd)

        with mock.patch.object(
            mirror_export, "_open_dir_nofollow", flaky_open
        ):
            code, out, err = self.run_cli(
                "--root", str(self.root),
                "sync", "--export-to", str(self.dest_root),
            )
        self.assertEqual(code, 0, out + err)
        self.assertIn("not provably", err)
        self.assertIn("NOT removed", err)
        self.assertTrue(self.previous.is_dir())
        self.assertEqual(utils.tree_hash(self.previous), self.old_hash)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)
        shutil.rmtree(self.previous)

    def test_cleanup_deletes_only_pinned_owned_tree(self):
        # The healthy path: the proven PREV tree is removed through the
        # pinned descriptor, nothing beside it is touched, and
        # shutil.rmtree is never used for it (C1: no pathname-based
        # recursive delete).
        bystander = self.dest_root / "bystander dir"
        bystander.mkdir()
        (bystander / "file.txt").write_text("untouched\n")
        with mock.patch.object(
            mirror_export.shutil, "rmtree",
            side_effect=AssertionError("shutil.rmtree used for cleanup"),
        ):
            code, out, err = self.run_cli(
                "--root", str(self.root),
                "sync", "--export-to", str(self.dest_root),
            )
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("WARN", err)
        self.assertFalse(self.previous.exists())
        self.assertFalse(self.staging.exists())
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)
        self.assertEqual((bystander / "file.txt").read_text(), "untouched\n")

    def test_pinned_aos_guard_refuses_recycled_inode_substitution(self):
        # The live AOS is destroyed and a foreign tree is planted at its
        # name INSIDE the accepted window (after the final verification,
        # before the move-aside). On tmpfs/ext4 the fresh directory often
        # recycles the freed inode NUMBER, which forges every
        # recorded-stat samestat proof — only the descriptor pinned at
        # the recheck (it keeps the real inode alive, so its number
        # cannot be reissued) can tell the trees apart. The move-aside
        # guard must refuse, the foreign tree must survive byte-for-byte,
        # and staging is discarded; nothing is ever renamed to PREV or
        # recursively deleted.
        real_verify = mirror_export._verify_staging_final

        def verify_then_substitute(*args):
            real_verify(*args)
            shutil.rmtree(self.dest_aos)
            self.plant_foreign(self.dest_aos)

        with mock.patch.object(
            mirror_export, "_verify_staging_final", verify_then_substitute
        ):
            code, out, err = self.export_fails()
        self.assertIn(DEST_CHANGED_MSG, err)
        self.assert_foreign_intact(self.dest_aos)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_rmtree_pinned_refuses_foreign_root_directly(self):
        # Unit check of the ownership proof: an expected identity that
        # does not match the directory at the name refuses before any
        # deletion, leaving the tree byte-for-byte intact.
        base = self.new_tmp_dir("rmtree unit")
        victim = base / "victim"
        self.plant_foreign(victim)
        other = base / "other"
        other.mkdir()
        dir_fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with self.assertRaises(OSError) as ctx:
                mirror_export._rmtree_pinned(
                    victim,
                    name="victim",
                    dir_fd=dir_fd,
                    expected=os.lstat(other),
                )
        finally:
            os.close(dir_fd)
        self.assertIn("no longer the directory", str(ctx.exception))
        self.assert_foreign_intact(victim)


# ---------------------------------------------------------------------------
# Fourth corrective pass — C2: descriptor-anchored hardlink source


class TestPinnedHardlinkSource(MutatedExportCase):
    def test_hardlink_reuse_source_is_descriptor_anchored(self):
        # Every os.link the build issues must be fully fd-anchored:
        # relative source name + src_dir_fd, relative destination name +
        # dst_dir_fd, follow_symlinks=False. No absolute pathname source.
        self.require_hardlinks(self.dest_root)
        calls = []
        real_link = os.link

        def spy(src, dst, *args, **kwargs):
            calls.append((str(src), str(dst), dict(kwargs)))
            return real_link(src, dst, *args, **kwargs)

        with mock.patch.object(mirror_export.os, "link", spy):
            out = self.export()
        self.assertIn("Exported to", out)
        export_calls = [
            c for c in calls if c[2].get("dst_dir_fd") is not None
        ]
        self.assertTrue(export_calls)
        for src, dst, kwargs in export_calls:
            self.assertIsNotNone(kwargs.get("src_dir_fd"), (src, kwargs))
            self.assertIs(kwargs.get("follow_symlinks"), False)
            self.assertFalse(os.path.isabs(src))
            self.assertNotIn("/", src)

    def swap_path_during_build(self):
        """Replace PATH with a byte-identical impostor right before the
        staging build, capturing the impostor's link counts immediately
        after the build ran. Returns (observed dict, refusal exception,
        moved-away original root)."""
        self.require_hardlinks(self.dest_root)
        plan = self.plan()
        self.assertTrue(plan.unchanged)
        moved = self.new_tmp_dir("moved holder") / "original root"
        observed = {}
        real_build = mirror_export._build_staging

        def swap_then_build(plan, staging_fd, dest_fd):
            self.dest_root.rename(moved)
            self.dest_root.mkdir()
            shutil.copytree(moved / "AOS", self.dest_root / "AOS")
            observed["impostor_before"] = self.snapshot(self.dest_root)
            build = real_build(plan, staging_fd, dest_fd)
            observed["nlinks_after_build"] = {
                p.relative_to(self.dest_root).as_posix():
                    os.lstat(p).st_nlink
                for p in sorted(self.dest_root.rglob("*"))
                if p.is_file()
            }
            observed["linked"] = dict(build.linked)
            return build

        with mock.patch.object(
            mirror_export, "_build_staging", swap_then_build
        ):
            with self.assertRaises(AosError) as ctx:
                mirror_export.apply_plan(plan)
        return observed, ctx.exception, moved

    def test_path_replacement_during_hardlink_build_does_not_link_replacement(
        self,
    ):
        # PATH is replaced by a byte-identical impostor while staging is
        # built: hardlink reuse must source through the PINNED descriptor
        # chain (never target.dest_aos / rel), so the impostor's inodes
        # are never linked — its link counts stay 1 even while the staged
        # links exist — and the export refuses at the recheck.
        observed, exc, moved = self.swap_path_during_build()
        self.assertIn(DEST_CHANGED_MSG, str(exc))
        self.assertTrue(observed["linked"])  # reuse actually happened
        for rel, nlink in observed["nlinks_after_build"].items():
            self.assertEqual(nlink, 1, rel)
        # The pinned original kept its generation; staging was discarded
        # from the pinned directory, not from the impostor.
        self.assertEqual(utils.tree_hash(moved / "AOS"), self.old_hash)
        self.assertFalse((moved / mirror_export.STAGING_NAME).exists())

    def test_replacement_path_link_count_is_unchanged(self):
        # After the refused export, the replacement PATH is byte-for-byte
        # and link-count identical to the moment it was planted.
        observed, exc, moved = self.swap_path_during_build()
        self.assertEqual(
            self.snapshot(self.dest_root), observed["impostor_before"]
        )
        for p in sorted(self.dest_root.rglob("*")):
            if p.is_file():
                self.assertEqual(os.lstat(p).st_nlink, 1, p)

    def test_reused_source_identity_mismatch_refuses(self):
        # An unchanged destination file is replaced with a byte-identical
        # copy (new inode) after planning: content comparison cannot see
        # it — only the recorded plan-time identity can. Hardlink reuse
        # must refuse rather than link an inode the plan never inspected.
        plan = self.plan()
        rel = plan.unchanged[0][0]
        victim = self.dest_aos / rel
        data = victim.read_bytes()
        replacement = victim.with_name("replacement.tmp")
        replacement.write_bytes(data)
        os.replace(replacement, victim)  # same bytes, different inode
        with self.assertRaises(AosError) as ctx:
            mirror_export.apply_plan(plan)
        msg = str(ctx.exception)
        self.assertIn(DEST_CHANGED_MSG, msg)
        self.assertIn("no longer the file the plan inspected", msg)
        self.assertEqual(victim.read_bytes(), data)
        self.assertEqual(os.lstat(victim).st_nlink, 1)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_source_entity_symlink_swap_during_link_refuses(self):
        # The source file is swapped for a symlink between the identity
        # check and the link call: follow_symlinks=False links the
        # symlink itself, and the post-link identity verification must
        # refuse — the symlink target never gains a link.
        self.require_hardlinks(self.dest_root)
        plan = self.plan()
        entity_rels = [rel for rel, _ in plan.unchanged if "/" in rel]
        self.assertTrue(entity_rels)
        victim_rel = entity_rels[0]
        victim = self.dest_aos / victim_rel
        decoy = self.new_tmp_dir("link decoy") / "decoy.md"
        shutil.copyfile(victim, decoy)
        base = victim.name
        real_link = os.link
        swapped = {"done": False}

        def swap_then_link(src, dst, *args, **kwargs):
            if (
                not swapped["done"]
                and str(src) == base
                and kwargs.get("src_dir_fd") is not None
            ):
                swapped["done"] = True
                victim.unlink()
                victim.symlink_to(decoy)
            return real_link(src, dst, *args, **kwargs)

        with mock.patch.object(mirror_export.os, "link", swap_then_link):
            with self.assertRaises(AosError) as ctx:
                mirror_export.apply_plan(plan)
        self.assertTrue(swapped["done"])
        msg = str(ctx.exception)
        self.assertIn(DEST_CHANGED_MSG, msg)
        self.assertEqual(os.lstat(decoy).st_nlink, 1)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())


# ---------------------------------------------------------------------------
# Fourth corrective pass — C3: cleanup-root device and mount checks


class TestCleanupRootContainment(MutatedExportCase):
    def doctored_dest_fstat(self, state):
        """os.fstat wrapper that, once `state['dest_id']` is set, reports
        the pinned destination descriptor on a DIFFERENT device (mocked
        cross-device condition — a real second filesystem would need
        privileged mounts)."""
        real_fstat = os.fstat

        def doctored(fd):
            st = real_fstat(fd)
            if state.get("dest_id") is not None and os.path.samestat(
                st, state["dest_id"]
            ):
                return os.stat_result((
                    st.st_mode, st.st_ino, st.st_dev + 1, st.st_nlink,
                    st.st_uid, st.st_gid, st.st_size,
                    st.st_atime, st.st_mtime, st.st_ctime,
                ))
            return st

        return mock.patch.object(mirror_export.os, "fstat", doctored)

    def test_staging_cleanup_root_cross_device_refuses(self):
        # The staging cleanup root fstats as cross-device (mocked): the
        # recursive delete must refuse and retain the complete tree.
        state = {"dest_id": None}
        real_fstat = os.fstat

        def fail_after_arming(plan, staging_fd, staging_stat, snapshot,
                              dest_fd, *args):
            state["dest_id"] = real_fstat(dest_fd)
            raise mirror_export._validation_failure("injected failure")

        with mock.patch.object(
            mirror_export, "_verify_staging_final", fail_after_arming
        ), self.doctored_dest_fstat(state):
            code, out, err = self.export_fails()
        self.assertIn("injected failure", err)
        self.assertIn("could not be removed", err)
        self.assertIn("different filesystem", err)
        self.assertTrue(self.staging.is_dir())
        self.assertEqual(utils.tree_hash(self.staging), self.new_hash)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        shutil.rmtree(self.staging)

    def test_previous_cleanup_root_cross_device_refuses(self):
        # Same for PREV on the success path: cross-device root (mocked)
        # means WARN + retain, never a recursive delete across devices.
        state = {"dest_id": None}
        real_fstat = os.fstat
        real_fsync = mirror_export._fsync_dest_root
        calls = {"n": 0}

        def fsync_then_arm(dest_fd):
            calls["n"] += 1
            real_fsync(dest_fd)
            if calls["n"] == 2:  # after STG -> AOS promotion
                state["dest_id"] = real_fstat(dest_fd)

        with mock.patch.object(
            mirror_export, "_fsync_dest_root", fsync_then_arm
        ), self.doctored_dest_fstat(state):
            code, out, err = self.run_cli(
                "--root", str(self.root),
                "sync", "--export-to", str(self.dest_root),
            )
        self.assertEqual(code, 0, out + err)
        self.assertIn("WARN: could not remove previous generation", err)
        self.assertIn("different filesystem", err)
        self.assertTrue(self.previous.is_dir())
        self.assertEqual(utils.tree_hash(self.previous), self.old_hash)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)
        shutil.rmtree(self.previous)

    def test_staging_cleanup_root_mount_refuses(self):
        # The staging root itself reports as a mount point (mocked): the
        # cleanup must refuse before deleting anything beneath it.
        def fail_verify(*args):
            raise mirror_export._validation_failure("injected failure")

        with mock.patch.object(
            mirror_export, "_verify_staging_final", fail_verify
        ), mock.patch.object(
            mirror_export.os.path, "ismount",
            lambda path: Path(path) == self.staging,
        ):
            code, out, err = self.export_fails()
        self.assertIn("could not be removed", err)
        self.assertIn("mount boundary", err)
        self.assertTrue(self.staging.is_dir())
        self.assertEqual(utils.tree_hash(self.staging), self.new_hash)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        shutil.rmtree(self.staging)

    def test_previous_cleanup_root_mount_refuses(self):
        # PREV itself reports as a mount point (mocked): WARN + retain.
        with mock.patch.object(
            mirror_export.os.path, "ismount",
            lambda path: Path(path) == self.previous,
        ):
            code, out, err = self.run_cli(
                "--root", str(self.root),
                "sync", "--export-to", str(self.dest_root),
            )
        self.assertEqual(code, 0, out + err)
        self.assertIn("WARN: could not remove previous generation", err)
        self.assertIn("mount boundary", err)
        self.assertTrue(self.previous.is_dir())
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)
        shutil.rmtree(self.previous)

    def test_cleanup_root_mount_contents_are_untouched(self):
        # Nothing beneath a rejected cleanup root may be modified: the
        # retained PREV is byte-for-byte the pre-export generation.
        before = self.snapshot(self.dest_aos)
        with mock.patch.object(
            mirror_export.os.path, "ismount",
            lambda path: Path(path) == self.previous,
        ):
            code, out, err = self.run_cli(
                "--root", str(self.root),
                "sync", "--export-to", str(self.dest_root),
            )
        self.assertEqual(code, 0, out + err)
        self.assertIn("WARN", err)
        self.assertEqual(self.snapshot(self.previous), before)
        shutil.rmtree(self.previous)


# ---------------------------------------------------------------------------
# Fourth corrective pass — C4: vetted regular-file reads


class TestVettedReads(MutatedExportCase):
    def scan_dest_then(self, n: int, tamper):
        """Run the real destination scan; after the Nth call, tamper."""
        real_scan = mirror_export._scan_dest_aos
        calls = {"n": 0}

        def wrapped(dest_aos):
            result = real_scan(dest_aos)
            calls["n"] += 1
            if calls["n"] == n:
                tamper()
            return result

        return mock.patch.object(mirror_export, "_scan_dest_aos", wrapped)

    def scan_source_then(self, n: int, tamper):
        real_scan = mirror_export._scan_source
        calls = {"n": 0}

        def wrapped(source):
            result = real_scan(source)
            calls["n"] += 1
            if calls["n"] == n:
                tamper()
            return result

        return mock.patch.object(mirror_export, "_scan_source", wrapped)

    def test_plan_destination_symlink_swap_refuses_without_external_read(
        self,
    ):
        # A destination note is swapped for a symlink to byte-identical
        # external content between the plan-time scan and the plan-time
        # read: O_NOFOLLOW refuses (no external bytes are read, so the
        # swap cannot silently pass as "unchanged").
        victim = self.dest_aos / "Home.md"
        outside = self.new_tmp_dir("outside") / "external.md"
        outside.write_bytes(victim.read_bytes())

        def swap():
            victim.unlink()
            victim.symlink_to(outside)

        # Call 1 is check_destination's gate; call 2 is the fresh
        # plan-time scan whose reads the vetted reader protects.
        with self.scan_dest_then(2, swap):
            with self.assertRaises(AosError) as ctx:
                self.plan()
        self.assertIn("cannot read", str(ctx.exception))
        self.assertIn("Home.md", str(ctx.exception))
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_plan_destination_fifo_swap_refuses_without_blocking(self):
        # Same swap with a FIFO: O_NONBLOCK + the S_ISREG fstat check
        # refuse without hanging (this test TERMINATING is the proof).
        victim = self.dest_aos / "Home.md"

        def swap():
            victim.unlink()
            os.mkfifo(victim)

        with self.scan_dest_then(2, swap):
            with self.assertRaises(AosError) as ctx:
                self.plan()
        self.assertIn("changed while being read", str(ctx.exception))
        self.assertFalse(self.staging.exists())

    def test_plan_source_symlink_swap_refuses_without_external_read(self):
        # A SOURCE note is swapped for a symlink between the source scan
        # and the plan's comparison read: the vetted read refuses instead
        # of comparing external bytes into the plan.
        victim = self.source / "CONVENTIONS.md"
        outside = self.new_tmp_dir("outside src") / "external.md"
        outside.write_bytes(victim.read_bytes())

        def swap():
            victim.unlink()
            victim.symlink_to(outside)

        with self.scan_source_then(1, swap):
            with self.assertRaises(AosError) as ctx:
                self.plan()
        self.assertIn("cannot read", str(ctx.exception))
        self.assertIn("CONVENTIONS.md", str(ctx.exception))
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)

    def test_final_source_fifo_swap_refuses_without_blocking(self):
        # The source is swapped for a FIFO between the final source scan
        # and the final verification's content read: refuse, terminate,
        # discard staging, destination untouched.
        victim = self.source / "CONVENTIONS.md"

        def swap():
            victim.unlink()
            os.mkfifo(victim)

        plan_holder = {}

        def run():
            plan_holder["plan"] = self.plan()  # scan call 1
            mirror_export.apply_plan(plan_holder["plan"])  # calls 2 and 3

        with self.scan_source_then(3, swap):
            with self.assertRaises(AosError) as ctx:
                run()
        self.assertIn("changed while being read", str(ctx.exception))
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_build_copy_source_fifo_swap_refuses_without_blocking(self):
        # A source note the plan marked changed is swapped for a FIFO
        # between planning and the staging build's payload copy: the
        # copy's vetted source open (O_NONBLOCK + S_ISREG fstat) must
        # refuse without hanging — a plain open of a writer-less FIFO
        # blocks forever. Staging is discarded; destination untouched.
        plan = self.plan()
        self.assertIn("Home.md", {rel for rel, _ in plan.updates})
        victim = self.source / "Home.md"
        victim.unlink()
        os.mkfifo(victim)
        with self.assertRaises(AosError) as ctx:
            mirror_export.apply_plan(plan)
        self.assertIn("changed while being copied", str(ctx.exception))
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_vetted_read_identity_change_refuses(self):
        # Unit check: the reader refuses when the opened inode is not the
        # identity the caller inspected (byte-identical replacement).
        base = self.new_tmp_dir("vet unit")
        note = base / "note.md"
        note.write_bytes(b"payload\n")
        expect = os.lstat(note)
        replacement = base / "replacement.md"
        replacement.write_bytes(b"payload\n")
        os.replace(replacement, note)  # same bytes, different inode
        dir_fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with self.assertRaises(AosError) as ctx:
                mirror_export._read_vetted_file(
                    "note.md", dir_fd, note, expect
                )
        finally:
            os.close(dir_fd)
        self.assertIn("changed while being read", str(ctx.exception))

    def test_enforcement_reads_do_not_use_path_read_bytes(self):
        # Planning and the complete apply must never read enforcement-
        # critical content through Path.read_bytes: a full changed export
        # succeeds with it forbidden.
        target = mirror_export.check_destination(
            self.aos_dir, str(self.dest_root)
        )
        forbidden = mock.Mock(
            side_effect=AssertionError(
                "Path.read_bytes used in an enforcement-critical read"
            )
        )
        with mock.patch.object(Path, "read_bytes", forbidden):
            plan = mirror_export.compute_plan(self.aos_dir, target)
            result = mirror_export.apply_plan(plan)
        self.assertIsNone(result.cleanup_warning)
        self.assertEqual(forbidden.call_count, 0)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)


# ---------------------------------------------------------------------------
# Fourth corrective pass — C5: actual execution statistics


class TestApplyResultStatistics(MutatedExportCase):
    def test_apply_result_counts_hardlinked_unchanged_files(self):
        self.require_hardlinks(self.dest_root)
        plan = self.plan()
        self.assertTrue(plan.unchanged)
        result = mirror_export.apply_plan(plan)
        self.assertEqual(result.created_files, len(plan.creates))
        self.assertEqual(result.updated_files, len(plan.updates))
        self.assertEqual(result.deleted_files, len(plan.deletes))
        self.assertEqual(
            result.unchanged_hardlinked_files, len(plan.unchanged)
        )
        self.assertEqual(result.unchanged_fallback_copied_files, 0)
        self.assertEqual(result.unchanged_files, len(plan.unchanged))
        self.assertIsNone(result.cleanup_warning)

    def test_apply_result_counts_fallback_copied_unchanged_files(self):
        # Hardlinks report unsupported (mocked recognized errno): every
        # unchanged file is fallback-copied and counted as such.
        plan = self.plan()
        self.assertTrue(plan.unchanged)
        with mock.patch.object(
            mirror_export.os, "link",
            side_effect=OSError(errno.EPERM, "links not supported here"),
        ):
            result = mirror_export.apply_plan(plan)
        self.assertEqual(result.unchanged_hardlinked_files, 0)
        self.assertEqual(
            result.unchanged_fallback_copied_files, len(plan.unchanged)
        )
        self.assertEqual(result.unchanged_files, len(plan.unchanged))
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)

    def test_bytes_written_excludes_hardlink_payload(self):
        # With hardlink reuse, payload bytes are exactly the created +
        # updated file sizes: a hardlink contributes zero payload bytes.
        self.require_hardlinks(self.dest_root)
        plan = self.plan()
        self.assertTrue(plan.unchanged)
        result = mirror_export.apply_plan(plan)
        self.assertEqual(result.unchanged_hardlinked_files, len(plan.unchanged))
        self.assertEqual(
            result.payload_bytes_written,
            sum(size for _, size in plan.creates + plan.updates),
        )

    def test_bytes_written_includes_unchanged_fallback_copy_bytes(self):
        # With hardlinks unsupported (mocked), every unchanged fallback
        # copy contributes its full byte size to the payload.
        plan = self.plan()
        self.assertTrue(plan.unchanged)
        with mock.patch.object(
            mirror_export.os, "link",
            side_effect=OSError(errno.EPERM, "links not supported here"),
        ):
            result = mirror_export.apply_plan(plan)
        self.assertEqual(
            result.payload_bytes_written,
            sum(
                size
                for _, size in plan.creates + plan.updates + plan.unchanged
            ),
        )

    def test_cli_uses_apply_result_bytes_written(self):
        # The CLI's byte count must come from ApplyResult (actual I/O),
        # not from the plan's creates+updates: with hardlinks unsupported
        # (mocked), the unchanged fallback copies must be included.
        plan = self.plan()
        self.assertTrue(plan.unchanged)
        expected_total = sum(
            size for _, size in plan.creates + plan.updates + plan.unchanged
        )
        plan_only_total = sum(
            size for _, size in plan.creates + plan.updates
        )
        self.assertNotEqual(expected_total, plan_only_total)
        with mock.patch.object(
            mirror_export.os, "link",
            side_effect=OSError(errno.EPERM, "links not supported here"),
        ):
            out = self.export()
        self.assertIn(f"({expected_total} bytes written).", out)
        self.assertIn(
            f"(0 hardlinked, {len(plan.unchanged)} copied)", out
        )


# ---------------------------------------------------------------------------
# Fourth corrective pass — C6: visible directory-only dry-run operations


class TestDirectoryDryRun(ExportCase):
    def render_dry_run(self, plan) -> str:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli._print_export_dry_run(plan)
        return buf.getvalue()

    def test_dry_run_prints_directory_only_create(self):
        self.export()
        (self.dest_aos / "Reviews").rmdir()  # empty in the fixture
        notes = len([
            p for p in self.source.rglob("*")
            if p.is_file() and not p.name.startswith(".")
        ])
        out = self.export("--dry-run")
        self.assertIn("create-dir Reviews/", out)
        self.assertNotIn("nothing to do", out)
        self.assertIn(
            "Dry run: 0 file creates (0 bytes), 0 file updates (0 bytes), "
            "0 file deletes (0 bytes), 1 directory create, "
            f"0 directory deletes, {notes} unchanged files. "
            "Nothing was written.",
            out,
        )

    def test_dry_run_prints_directory_only_delete(self):
        # The generated mirror always contains every entity directory, so
        # a directory-only delete is exercised at the module layer: the
        # source loses an (empty) entity directory after the sync.
        self.export()
        source_reviews = self.source / "Reviews"
        self.assertEqual(sorted(os.listdir(source_reviews)), [])
        source_reviews.rmdir()
        target = mirror_export.check_destination(
            self.aos_dir, str(self.dest_root)
        )
        plan = mirror_export.compute_plan(self.aos_dir, target)
        self.assertEqual(plan.dir_deletes, ["Reviews"])
        self.assertFalse(plan.is_noop)
        out = self.render_dry_run(plan)
        self.assertIn("delete-dir Reviews/", out)
        self.assertIn("1 directory delete,", out)
        self.assertNotIn("nothing to do", out)

    def test_dry_run_directory_operations_are_sorted(self):
        # Deterministic ordering, unit-checked against a synthetic plan:
        # create-dir lines sorted, then delete-dir lines sorted.
        plan = mirror_export.ExportPlan(
            target=types.SimpleNamespace(dest_aos=Path("/dest/AOS")),
            source=Path("/src"),
            creates=[],
            updates=[],
            deletes=[],
            unchanged=[("Home.md", 10)],
            source_dirs=["Agents", "Reviews"],
            dest_dirs=["Memory", "Obsolete"],
            base_exists=True,
            base_stat=None,
            base_files=[("Home.md", 10)],
            base_dirs=["Memory", "Obsolete"],
            base_sentinel=True,
            base_hash=None,
        )
        self.assertEqual(plan.dir_creates, ["Agents", "Reviews"])
        self.assertEqual(plan.dir_deletes, ["Memory", "Obsolete"])
        out = self.render_dry_run(plan)
        positions = [
            out.index("create-dir Agents/"),
            out.index("create-dir Reviews/"),
            out.index("delete-dir Memory/"),
            out.index("delete-dir Obsolete/"),
        ]
        self.assertEqual(positions, sorted(positions))
        self.assertIn(
            "2 directory creates, 2 directory deletes, 1 unchanged file",
            out,
        )

    def test_dry_run_file_and_directory_summary_is_unambiguous(self):
        # Mixed file + directory plan: the summary names files and
        # directories separately with their own counts.
        self.export()
        (self.dest_aos / "Reviews").rmdir()
        stale = self.dest_aos / "Tasks" / "T-9999.md"
        stale.write_text("stale generated-shaped note\n")
        notes = len([
            p for p in self.source.rglob("*")
            if p.is_file() and not p.name.startswith(".")
        ])
        out = self.export("--dry-run")
        self.assertIn(f"delete Tasks/T-9999.md ({stale.stat().st_size} bytes)", out)
        self.assertIn("create-dir Reviews/", out)
        self.assertIn(
            "Dry run: 0 file creates (0 bytes), 0 file updates (0 bytes), "
            f"1 file delete ({stale.stat().st_size} bytes), "
            "1 directory create, 0 directory deletes, "
            f"{notes} unchanged files. Nothing was written.",
            out,
        )


# ---------------------------------------------------------------------------
# Fifth corrective pass — Q1: quarantine-based cleanup deletion
#
# Deletion is never check-then-name against a meaningful name: every entry
# is atomically renamed to a fresh single-use private quarantine name,
# proven against the inspected identity, and only then deleted; a captured
# or raced-in replacement is retained (restored where possible), never
# deleted.


class TestQuarantineCleanup(MutatedExportCase):
    REPLACEMENT = b"replacement bytes that must survive cleanup\n"

    def fail_verify(self):
        def boom(*args):
            raise mirror_export._validation_failure("injected failure")

        return mock.patch.object(mirror_export, "_verify_staging_final", boom)

    def plant_file_at(self, dir_fd: int, target_name: str) -> None:
        """Racer move: atomically install a replacement FILE at
        `target_name` inside the directory `dir_fd` refers to (clobbering
        whatever the export owned there — that is the racer's deletion,
        not the export's)."""
        tmp = ".racer-tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644,
                     dir_fd=dir_fd)
        try:
            os.write(fd, self.REPLACEMENT)
        finally:
            os.close(fd)
        os.rename(tmp, target_name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)

    def plant_dir_at(self, dir_fd: int, target_name: str) -> None:
        """Racer move: atomically install a replacement DIRECTORY (with
        one marker file) at `target_name` — legal onto an empty
        directory, which is exactly what sits at a quarantine name right
        before its rmdir."""
        tmpd = ".racer-tmp-dir"
        os.mkdir(tmpd, dir_fd=dir_fd)
        dfd = os.open(tmpd, os.O_RDONLY | os.O_DIRECTORY, dir_fd=dir_fd)
        try:
            ffd = os.open("marker.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                          0o644, dir_fd=dfd)
            try:
                os.write(ffd, self.REPLACEMENT)
            finally:
                os.close(ffd)
        finally:
            os.close(dfd)
        os.rename(tmpd, target_name, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)

    def swap_before_delete(self, match, plant):
        """Patch the verified-deletion seam: right before the victim's
        final verification-and-delete, install a replacement at its
        quarantine name — the last defensible instant before unlink or
        rmdir."""
        real_delete = mirror_export._delete_quarantined
        planted = {}

        def swap_then_delete(qname, name, dir_fd, proven, public):
            if not planted and match(public, proven):
                plant(dir_fd, qname)
                planted["qname"] = qname
                planted["public"] = public
            return real_delete(qname, name, dir_fd, proven, public)

        return planted, mock.patch.object(
            mirror_export, "_delete_quarantined", swap_then_delete
        )

    def test_cleanup_file_swap_immediately_before_unlink_retains_replacement(
        self,
    ):
        # A replacement FILE lands at the victim's quarantine name at the
        # last instant before the unlink: the re-proof must refuse, the
        # replacement must survive byte-for-byte at exactly the name it
        # was planted under, and the export must report the retention.
        planted, seam = self.swap_before_delete(
            lambda public, proven: public.name == "Home.md"
            and not stat.S_ISDIR(proven.st_mode),
            self.plant_file_at,
        )
        with self.fail_verify(), seam:
            code, out, err = self.export_fails()
        self.assertTrue(planted)
        self.assertIn("was replaced during cleanup", err)
        self.assertIn("retained", err)
        self.assertIn("could not be removed", err)
        # The refusal restored the staging root to its public name; the
        # replacement still sits at the exact quarantine name it was
        # planted under, bytes intact — and the refusal REPORTS that
        # exact retained location.
        survivor = self.staging / planted["qname"]
        self.assertIn(str(survivor), err)
        self.assertEqual(survivor.read_bytes(), self.REPLACEMENT)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.previous.exists())
        shutil.rmtree(self.staging)

    def test_cleanup_directory_swap_immediately_before_rmdir_retains_replacement(
        self,
    ):
        # Same at the last instant before a subdirectory's rmdir: the
        # racer replaces the emptied, quarantined entity directory with a
        # NONEMPTY replacement directory. The re-proof must refuse and
        # the replacement (directory + marker bytes) must survive.
        planted, seam = self.swap_before_delete(
            lambda public, proven: public.name == "Tasks"
            and stat.S_ISDIR(proven.st_mode),
            self.plant_dir_at,
        )
        with self.fail_verify(), seam:
            code, out, err = self.export_fails()
        self.assertTrue(planted)
        self.assertIn("was replaced during cleanup", err)
        self.assertIn("retained", err)
        survivor = self.staging / planted["qname"]
        self.assertIn(str(survivor), err)  # exact retained location
        self.assertTrue(survivor.is_dir())
        self.assertEqual(
            (survivor / "marker.txt").read_bytes(), self.REPLACEMENT
        )
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.previous.exists())
        shutil.rmtree(self.staging)

    def test_cleanup_root_swap_immediately_before_final_rmdir_retains_replacement(
        self,
    ):
        # The STG root itself: after every child is gone, a replacement
        # directory lands at the root's quarantine name right before the
        # final rmdir. The re-proof must refuse; the replacement is
        # retained at the quarantine name (PATH level) byte-for-byte, and
        # the NEXT run refuses on the leftover cleanup entry until it is
        # inspected and removed — in dry-run too.
        planted, seam = self.swap_before_delete(
            lambda public, proven: Path(public) == self.staging
            and stat.S_ISDIR(proven.st_mode),
            self.plant_dir_at,
        )
        with self.fail_verify(), seam:
            code, out, err = self.export_fails()
        self.assertTrue(planted)
        self.assertIn("was replaced during cleanup", err)
        self.assertIn("retained", err)
        survivor = self.dest_root / planted["qname"]
        self.assertIn(str(survivor), err)  # exact retained location
        self.assertTrue(survivor.is_dir())
        self.assertEqual(
            (survivor / "marker.txt").read_bytes(), self.REPLACEMENT
        )
        self.assertFalse(self.staging.exists())
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        # Stale-quarantine detection: both modes refuse on the leftover.
        code2, out2, err2 = self.export_fails()
        self.assertIn("leftover cleanup entry", err2)
        code3, out3, err3 = self.export_fails("--dry-run")
        self.assertIn("leftover cleanup entry", err3)
        shutil.rmtree(survivor)
        out4 = self.export()
        self.assertIn("Exported to", out4)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)

    def test_cleanup_root_final_swap_does_not_report_success(self):
        # The same final-instant root swap on the SUCCESS path (PREV
        # cleanup after promotion): the cleanup must not report success —
        # the WARN names the replacement and its retained location, the
        # replacement survives byte-for-byte, and the promoted generation
        # is intact.
        planted, seam = self.swap_before_delete(
            lambda public, proven: Path(public) == self.previous
            and stat.S_ISDIR(proven.st_mode),
            self.plant_dir_at,
        )
        with seam:
            code, out, err = self.run_cli(
                "--root", str(self.root),
                "sync", "--export-to", str(self.dest_root),
            )
        self.assertTrue(planted)
        self.assertEqual(code, 0, out + err)
        self.assertIn("WARN: could not remove previous generation", err)
        self.assertIn("was replaced during cleanup", err)
        self.assertIn("retained", err)
        survivor = self.dest_root / planted["qname"]
        self.assertIn(str(survivor), err)  # exact retained location
        self.assertEqual(
            (survivor / "marker.txt").read_bytes(), self.REPLACEMENT
        )
        self.assertFalse(self.previous.exists())
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)
        shutil.rmtree(survivor)

    def test_quarantine_identity_mismatch_is_never_deleted(self):
        # The PUBLIC child name is swapped between the cleanup's lstat
        # classification and the atomic quarantine rename: the rename
        # CAPTURES the replacement, the identity proof refuses, and the
        # replacement is restored to its public name byte-for-byte —
        # a mismatching quarantine is never deleted.
        real_q = mirror_export._quarantine_entry
        planted = {}

        def swap_then_quarantine(name, dir_fd, public):
            if not planted and public.name == "Home.md":
                self.plant_file_at(dir_fd, name)
                planted["public"] = public
            return real_q(name, dir_fd, public)

        with self.fail_verify(), mock.patch.object(
            mirror_export, "_quarantine_entry", swap_then_quarantine
        ):
            code, out, err = self.export_fails()
        self.assertTrue(planted)
        self.assertIn("was replaced during cleanup", err)
        self.assertIn("retained", err)
        # Restored to the public name inside the retained staging root.
        self.assertEqual(
            (self.staging / "Home.md").read_bytes(), self.REPLACEMENT
        )
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.previous.exists())
        shutil.rmtree(self.staging)

    def test_cleanup_interior_enoent_is_reported_not_absent(self):
        # A child vanishes between the cleanup's directory listing and
        # its lstat (raced away by a concurrent process): the resulting
        # ENOENT must surface as a "could not be removed" retention
        # report — Python maps errno.ENOENT to FileNotFoundError, and a
        # type-based swallow would misread the retained tree as
        # "staging genuinely absent" and report nothing.
        real_listdir = os.listdir
        injected = {}

        def phantom_listdir(arg):
            result = real_listdir(arg)
            if (
                isinstance(arg, int)
                and not injected
                and mirror_export.OWNER_SENTINEL_NAME in result
            ):
                injected["done"] = True
                # '!' sorts before every real child: the phantom is hit
                # first, so nothing of ours is deleted before the race.
                return ["!phantom-vanished.md"] + list(result)
            return result

        with self.fail_verify(), mock.patch.object(
            mirror_export.os, "listdir", phantom_listdir
        ):
            code, out, err = self.export_fails()
        self.assertTrue(injected)
        self.assertIn("injected failure", err)
        self.assertIn("could not be removed", err)
        self.assertTrue(self.staging.is_dir())
        self.assertEqual(utils.tree_hash(self.staging), self.new_hash)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        shutil.rmtree(self.staging)

    def test_prev_vanished_before_cleanup_warns_accurately(self):
        # PREV is deleted by a concurrent process after promotion but
        # before this run's cleanup reaches it: exit 0 with a WARN that
        # names the disappearance — never an instruction to remove a
        # tree that does not exist.
        real_fsync = mirror_export._fsync_dest_root
        calls = {"n": 0}

        def fsync_then_vanish(dest_fd):
            calls["n"] += 1
            real_fsync(dest_fd)
            if calls["n"] == 2:  # the fsync after STG -> AOS promotion
                shutil.rmtree(self.previous)

        with mock.patch.object(
            mirror_export, "_fsync_dest_root", fsync_then_vanish
        ):
            code, out, err = self.run_cli(
                "--root", str(self.root),
                "sync", "--export-to", str(self.dest_root),
            )
        self.assertEqual(code, 0, out + err)
        self.assertIn("disappeared during cleanup", err)
        self.assertNotIn("Remove it manually", err)
        self.assertFalse(self.previous.exists())
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)

    def test_cleanup_deep_tree_refuses_without_internal_error(self):
        # A hostile process nests directories deeper than the Python
        # recursion limit inside staging after validation: cleanup must
        # surface the exit-1 refusal with the tree retained and the
        # original failure preserved — never an exit-2 RecursionError
        # that masks it.
        def deepen_then_fail(*args):
            deep = self.staging
            for _ in range(sys.getrecursionlimit() + 200):
                deep = deep / "d"
                os.mkdir(deep)
            raise mirror_export._validation_failure("injected failure")

        with mock.patch.object(
            mirror_export, "_verify_staging_final", deepen_then_fail
        ):
            code, out, err = self.export_fails()
        self.assertIn("injected failure", err)
        self.assertIn("could not be removed", err)
        self.assertIn("nested too deeply", err)
        self.assertTrue(self.staging.is_dir())
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        limit = sys.getrecursionlimit()
        sys.setrecursionlimit(limit + 5000)
        try:
            shutil.rmtree(self.staging)
        finally:
            sys.setrecursionlimit(limit)

    def test_healthy_cleanup_leaves_no_quarantine_names(self):
        # The quarantine machinery is invisible on the healthy path: no
        # reserved cleanup name survives anywhere under PATH after a
        # successful export, and no meaningful name was ever passed to
        # unlink or rmdir.
        deleted_names = []
        real_unlink, real_rmdir = os.unlink, os.rmdir

        def spy_unlink(name, *args, **kwargs):
            if kwargs.get("dir_fd") is not None:
                deleted_names.append(str(name))
            return real_unlink(name, *args, **kwargs)

        def spy_rmdir(name, *args, **kwargs):
            if kwargs.get("dir_fd") is not None:
                deleted_names.append(str(name))
            return real_rmdir(name, *args, **kwargs)

        with mock.patch.object(mirror_export.os, "unlink", spy_unlink), \
                mock.patch.object(mirror_export.os, "rmdir", spy_rmdir):
            out = self.export()
        self.assertIn("Exported to", out)
        self.assertTrue(deleted_names)  # PREV cleanup ran
        for name in deleted_names:
            self.assertTrue(
                name.startswith(mirror_export.CLEANUP_PREFIX),
                f"deletion named a non-quarantine entry: {name}",
            )
        leftovers = [
            p for p in self.dest_root.rglob(
                f"{mirror_export.CLEANUP_PREFIX}*"
            )
        ]
        self.assertEqual(leftovers, [])
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)


# ---------------------------------------------------------------------------
# Fifth corrective pass — Q2: payload-copy source is descriptor-anchored


class TestPinnedCopySource(MutatedExportCase):
    def entity_rel(self, plan) -> str:
        """A planned create/update that lives inside an entity dir."""
        rels = [
            rel for rel, _ in plan.creates + plan.updates if "/" in rel
        ]
        self.assertTrue(rels)
        return rels[0]

    def spy_absolute_opens(self, record: list):
        real_open = os.open

        def spy(path, *args, **kwargs):
            if isinstance(path, (str, Path)) and os.path.isabs(str(path)):
                record.append(str(path))
            return real_open(path, *args, **kwargs)

        return mock.patch.object(mirror_export.os, "open", spy)

    def test_copy_source_entity_symlink_swap_never_reads_external_file(self):
        # The source entity directory is swapped for a symlink to an
        # external directory between planning and the staging build: the
        # O_NOFOLLOW entity open under the pinned source root must refuse
        # (ELOOP) — the external file is never opened, its bytes are
        # never read, and the destination is untouched.
        plan = self.plan()
        rel = self.entity_rel(plan)
        entity = rel.split("/", 1)[0]
        external = self.new_tmp_dir("external entity")
        moved = self.new_tmp_dir("moved holder") / "entity-original"
        shutil.copytree(self.source / entity, external / entity)
        (self.source / entity).rename(moved)
        (self.source / entity).symlink_to(external / entity)
        self.addCleanup(self.aos, "sync")  # heal the source mirror
        opened = []
        with self.spy_absolute_opens(opened):
            with self.assertRaises(AosError) as ctx:
                mirror_export.apply_plan(plan)
        msg = str(ctx.exception)
        self.assertIn("cannot open", msg)
        self.assertIn("without following symlinks", msg)
        self.assertIn(entity, msg)
        # No absolute open reached inside the external tree, the moved
        # original, or the source mirror (only the source-root pin and
        # destination-side paths are absolute).
        for path in opened:
            self.assertFalse(path.startswith(str(external) + os.sep), path)
            self.assertFalse(path.startswith(str(moved) + os.sep), path)
            self.assertFalse(path.startswith(str(self.source) + os.sep),
                             path)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())
        os.unlink(self.source / entity)
        moved.rename(self.source / entity)

    def test_copy_source_root_replacement_refuses(self):
        # The complete source AOS root is replaced by a byte-identical
        # impostor between planning and the build: the build's pin
        # (fstat identity against the plan's recorded source root) must
        # refuse before a single byte is copied.
        plan = self.plan()
        moved = self.new_tmp_dir("moved source holder") / "source-original"
        self.source.rename(moved)
        shutil.copytree(moved, self.source)
        self.addCleanup(self.aos, "sync")  # heal the source mirror
        with self.assertRaises(AosError) as ctx:
            mirror_export.apply_plan(plan)
        msg = str(ctx.exception)
        self.assertIn("was replaced during export", msg)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_copy_source_regular_replacement_identity_mismatch_refuses(self):
        # A source note in the plan is replaced with a byte-identical
        # copy (new inode) between planning and the build: content
        # comparison cannot see it — only the recorded plan-time source
        # identity can. The copy must refuse rather than read an inode
        # the plan never inspected.
        plan = self.plan()
        rel = self.entity_rel(plan)
        victim = self.source / rel
        data = victim.read_bytes()
        replacement = victim.with_name("replacement.tmp")
        replacement.write_bytes(data)
        os.replace(replacement, victim)  # same bytes, different inode
        self.addCleanup(self.aos, "sync")  # heal the source mirror
        with self.assertRaises(AosError) as ctx:
            mirror_export.apply_plan(plan)
        self.assertIn("changed while being copied", str(ctx.exception))
        self.assertIn(rel, str(ctx.exception))
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_fallback_copy_uses_pinned_source_descriptor(self):
        # Hardlinks "unsupported" (recognized errno): every unchanged
        # file is COPIED — and those fallback copies must flow through
        # the same pinned source-descriptor path as creates and updates:
        # relative basenames only, and no absolute open anywhere inside
        # the source mirror.
        plan = self.plan()
        self.assertTrue(plan.unchanged)
        copied = []
        real_copy = mirror_export._copy_into_staging

        def spy_copy(p, source_fd, src_entity_fds, rel, name, dir_fd):
            copied.append((rel, name, source_fd))
            return real_copy(p, source_fd, src_entity_fds, rel, name, dir_fd)

        opened = []
        with mock.patch.object(
            mirror_export.os, "link",
            side_effect=OSError(errno.EPERM, "links unsupported"),
        ), mock.patch.object(
            mirror_export, "_copy_into_staging", spy_copy
        ), self.spy_absolute_opens(opened):
            result = mirror_export.apply_plan(plan)
        self.assertEqual(
            result.unchanged_fallback_copied_files, len(plan.unchanged)
        )
        self.assertEqual(
            len(copied),
            len(plan.creates) + len(plan.updates) + len(plan.unchanged),
        )
        source_root_fds = set()
        for rel, name, source_fd in copied:
            self.assertFalse(os.path.isabs(name), (rel, name))
            self.assertNotIn("/", name, (rel, name))
            source_root_fds.add(source_fd)
        self.assertEqual(len(source_root_fds), 1)  # ONE pin, held throughout
        for path in opened:
            self.assertFalse(
                path.startswith(str(self.source) + os.sep),
                f"absolute source open during the build: {path}",
            )
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)

    def test_copy_source_directory_swap_does_not_leak_descriptor(self):
        # A DIRECTORY raced onto a changed source note's name: the
        # O_RDONLY|O_NOFOLLOW open of a directory SUCCEEDS (only write
        # opens get EISDIR) and os.fdopen then refuses without closing
        # the descriptor it was handed — the copy path must close it on
        # that failure path too.
        plan = self.plan()
        rel = self.entity_rel(plan)
        victim = self.source / rel
        base = victim.name
        victim.unlink()
        victim.mkdir()
        self.addCleanup(self.aos, "sync")  # heal the source mirror
        opened, closed = [], []
        real_open, real_close = os.open, os.close

        def spy_open(path, *args, **kwargs):
            fd = real_open(path, *args, **kwargs)
            if path == base and kwargs.get("dir_fd") is not None:
                opened.append(fd)
            return fd

        def spy_close(fd):
            closed.append(fd)
            return real_close(fd)

        with mock.patch.object(mirror_export.os, "open", spy_open), \
                mock.patch.object(mirror_export.os, "close", spy_close):
            with self.assertRaises(AosError) as ctx:
                mirror_export.apply_plan(plan)
        self.assertIn("Export failed while staging", str(ctx.exception))
        self.assertTrue(opened)
        for fd in opened:
            self.assertIn(fd, closed, "source descriptor leaked")
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        victim.rmdir()

    def test_external_source_bytes_never_enter_staging(self):
        # Entity-symlink swap where the external tree holds DIFFERENT
        # bytes: capture the complete staging content at the moment of
        # discard and prove no staged file ever contained the external
        # bytes.
        plan = self.plan()
        rel = self.entity_rel(plan)
        entity = rel.split("/", 1)[0]
        external_bytes = b"EXTERNAL BYTES that must never be staged\n"
        external = self.new_tmp_dir("external diff") / entity
        external.mkdir()
        for child in (self.source / entity).iterdir():
            (external / child.name).write_bytes(external_bytes)
        moved = self.new_tmp_dir("moved holder") / "entity-original"
        (self.source / entity).rename(moved)
        (self.source / entity).symlink_to(external)
        self.addCleanup(self.aos, "sync")  # heal the source mirror
        captured = {}
        real_discard = mirror_export._discard_staging

        def spy_discard(target, failure, dest_fd, staging_stat):
            captured["staging"] = self.snapshot(self.staging)
            return real_discard(target, failure, dest_fd, staging_stat)

        with mock.patch.object(
            mirror_export, "_discard_staging", spy_discard
        ):
            with self.assertRaises(AosError):
                mirror_export.apply_plan(plan)
        self.assertIn("staging", captured)
        self.assertNotIn(
            external_bytes, set(captured["staging"].values())
        )
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())
        os.unlink(self.source / entity)
        moved.rename(self.source / entity)


# ---------------------------------------------------------------------------
# Fifth corrective pass — Q3: the final hardlink check never follows an
# intermediate symlink


class TestFinalHardlinkAnchoring(MutatedExportCase):
    def capture_linked(self, store: dict):
        real_validate = mirror_export._validate_staging

        def spy(*args):
            snapshot = real_validate(*args)
            store["linked"] = dict(snapshot.linked)
            return snapshot

        return mock.patch.object(mirror_export, "_validate_staging", spy)

    def swap_entity_after_recheck(self, moved: Path):
        """Attack inside the post-recheck window: move AOS/Tasks out and
        plant a symlink back to it — the pathname AOS/Tasks/<file> still
        resolves to the very same inodes."""
        real_recheck = mirror_export._recheck_target

        def recheck_then_swap(*args):
            result = real_recheck(*args)
            (self.dest_aos / "Tasks").rename(moved)
            (self.dest_aos / "Tasks").symlink_to(moved)
            return result

        return mock.patch.object(
            mirror_export, "_recheck_target", recheck_then_swap
        )

    def run_entity_symlink_attack(self):
        self.require_hardlinks(self.dest_root)
        moved = self.new_tmp_dir("moved entity holder") / "Tasks-moved"
        store = {}
        with self.capture_linked(store), self.swap_entity_after_recheck(
            moved
        ):
            code, out, err = self.run_cli(
                "--root", str(self.root),
                "sync", "--export-to", str(self.dest_root),
            )
        # Skip BEFORE asserting the exit code: on a legal link-fallback
        # filesystem nothing is hardlinked and the attack is not this
        # mechanism's to catch — that must surface as a SKIP, not a FAIL.
        if not any(rel.startswith("Tasks/") for rel in store.get(
            "linked", {}
        )):
            self.skipTest("hardlink reuse unsupported here")
        self.assertEqual(code, 1, out + err)
        return moved, err

    def test_final_hardlink_check_rejects_entity_symlink(self):
        # A moved entity directory plus a symlink back to it: every
        # pathname probe would resolve to the SAME inode and pass
        # samestat — only the O_NOFOLLOW entity open under the held AOS
        # descriptor can refuse. No promotion may happen.
        moved, err = self.run_entity_symlink_attack()
        self.assertIn(DEST_CHANGED_MSG, err)
        self.assertIn("without following symlinks", err)
        self.assertTrue((self.dest_aos / "Tasks").is_symlink())
        self.assertTrue((moved / "T-0001.md").is_file())
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_moved_entity_directory_cannot_remain_external_alias(self):
        # The point of the refusal: had promotion proceeded, the moved
        # directory would keep hardlink aliases into the promoted
        # generation. After the refusal discards staging, every file in
        # the moved directory is back to link count 1 — no staged alias
        # survives anywhere.
        moved, err = self.run_entity_symlink_attack()
        self.assertIn(DEST_CHANGED_MSG, err)
        for child in sorted(moved.iterdir()):
            if child.is_file():
                self.assertEqual(os.lstat(child).st_nlink, 1, child)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_final_hardlink_check_uses_held_aos_descriptor(self):
        # The live side of the final hardlink verification must receive
        # the HELD AOS-root descriptor pinned at the recheck (fstat
        # identity equals the pre-export AOS root), and no fd-relative
        # probe anywhere in the apply may name a multi-component path
        # (an intermediate component would follow symlinks).
        self.require_hardlinks(self.dest_root)
        aos_before = os.lstat(self.dest_aos)
        seen = {}
        real_check = mirror_export._check_staged_links

        def spy_check(target, stg_files, linked, *, against_live_aos,
                      aos_fd=None, aos_dirs=None):
            if against_live_aos:
                seen["aos_fd"] = aos_fd
                seen["identity"] = (
                    os.fstat(aos_fd) if aos_fd is not None else None
                )
                seen["aos_dirs"] = dict(aos_dirs or {})
            return real_check(
                target, stg_files, linked,
                against_live_aos=against_live_aos,
                aos_fd=aos_fd, aos_dirs=aos_dirs,
            )

        multi_component = []
        real_lstat = os.lstat

        def spy_lstat(path, *args, **kwargs):
            if kwargs.get("dir_fd") is not None and "/" in str(path):
                multi_component.append(str(path))
            return real_lstat(path, *args, **kwargs)

        with mock.patch.object(
            mirror_export, "_check_staged_links", spy_check
        ), mock.patch.object(mirror_export.os, "lstat", spy_lstat):
            plan = self.plan()
            mirror_export.apply_plan(plan)
        self.assertIsNotNone(seen.get("aos_fd"))
        self.assertTrue(os.path.samestat(seen["identity"], aos_before))
        # The recorded entity-directory identities came from the pinned
        # rescan of the verified AOS root.
        self.assertIn("Tasks", seen["aos_dirs"])
        self.assertEqual(multi_component, [])
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)

    def test_external_alias_cannot_modify_promoted_generation(self):
        # End-to-end: the alias attack refuses; after healing, a clean
        # export promotes a generation in which EVERY file has link
        # count 1 — so no external write can reach promoted bytes.
        moved, err = self.run_entity_symlink_attack()
        self.assertIn(DEST_CHANGED_MSG, err)
        # Heal: drop the symlink, restore an independent copy, keep the
        # attacker's directory around as their external handle.
        os.unlink(self.dest_aos / "Tasks")
        shutil.copytree(moved, self.dest_aos / "Tasks")
        out = self.export()
        self.assertIn("Exported to", out)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)
        promoted = [
            p for p in sorted(self.dest_aos.rglob("*")) if p.is_file()
        ]
        self.assertTrue(promoted)
        for path in promoted:
            self.assertEqual(os.lstat(path).st_nlink, 1, path)
        # The attacker writes through their retained external handle:
        # not a single promoted byte may change.
        before = self.snapshot(self.dest_aos)
        for child in sorted(moved.iterdir()):
            if child.is_file():
                child.write_bytes(b"attacker scribbles\n")
        self.assertEqual(self.snapshot(self.dest_aos), before)


# ---------------------------------------------------------------------------
# Fifth corrective pass — Q4: final verification ordering (source first,
# destination next, the complete staging scan and hash LAST)


class TestFinalVerificationOrdering(MutatedExportCase):
    def test_live_write_during_final_source_hash_is_caught(self):
        # A live destination write lands WHILE the final source
        # verification is still running (the old ordering hashed staging
        # before it — through a staged hardlink the write would have
        # shipped silently). With staging verified last, the write is
        # caught before promotion.
        self.require_hardlinks(self.dest_root)
        calls = {"n": 0}
        real_hash = mirror_export._hash_source_tree

        def write_during_final_source_hash(source, src_files, src_stats):
            calls["n"] += 1
            if calls["n"] == 2:  # call 1 = validation; call 2 = final
                victim = self.dest_aos / "CONVENTIONS.md"
                data = bytearray(victim.read_bytes())
                data[0] ^= 0x01
                victim.write_bytes(bytes(data))
            return real_hash(source, src_files, src_stats)

        with mock.patch.object(
            mirror_export, "_hash_source_tree",
            write_during_final_source_hash,
        ):
            code, out, err = self.export_fails()
        self.assertEqual(calls["n"], 2)
        self.assertIn(DEST_CHANGED_MSG, err)
        self.assertIn("file content", err)
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def test_staged_hardlink_changed_after_first_hash_is_caught(self):
        # The staged bytes of an intentionally hardlinked file are
        # mutated through the DESTINATION pathname after the destination
        # recheck already passed: only the LAST staging content hash can
        # catch it before the rename ships the mutation.
        self.require_hardlinks(self.dest_root)
        store = {}
        real_validate = mirror_export._validate_staging

        def capture_linked(*args):
            snapshot = real_validate(*args)
            store["linked"] = dict(snapshot.linked)
            return snapshot

        real_recheck = mirror_export._recheck_target

        def recheck_then_write(*args):
            result = real_recheck(*args)
            victim = self.dest_aos / "CONVENTIONS.md"
            data = bytearray(victim.read_bytes())
            data[0] ^= 0x01
            victim.write_bytes(bytes(data))
            return result

        with mock.patch.object(
            mirror_export, "_validate_staging", capture_linked
        ), mock.patch.object(
            mirror_export, "_recheck_target", recheck_then_write
        ):
            code, out, err = self.run_cli(
                "--root", str(self.root),
                "sync", "--export-to", str(self.dest_root),
            )
        # Skip before asserting the exit code: without a staged hardlink
        # the destination write cannot reach staging at all.
        if "CONVENTIONS.md" not in store.get("linked", {}):
            self.skipTest("hardlink reuse unsupported here")
        self.assertEqual(code, 1, out + err)
        self.assertIn(
            "staged generation changed after validation: file content",
            err,
        )
        self.assertFalse(self.staging.exists())
        self.assertFalse(self.previous.exists())

    def instrumented_export(self):
        """Run a full module-layer export with the content-bearing scans
        and the renames recorded as an ordered event log."""
        events = []

        def wrap(name, real):
            def wrapper(*args, **kwargs):
                events.append(name)
                result = real(*args, **kwargs)
                events.append(f"{name}_done")
                return result

            return wrapper

        plan = self.plan()
        with mock.patch.object(
            mirror_export, "_scan_source",
            wrap("scan_source", mirror_export._scan_source),
        ), mock.patch.object(
            mirror_export, "_hash_source_tree",
            wrap("hash_source", mirror_export._hash_source_tree),
        ), mock.patch.object(
            mirror_export, "_rescan_dest_aos_pinned",
            wrap("rescan_dest", mirror_export._rescan_dest_aos_pinned),
        ), mock.patch.object(
            mirror_export, "_scan_staging",
            wrap("scan_staging", mirror_export._scan_staging),
        ), mock.patch.object(
            mirror_export, "_read_vetted_file",
            wrap("read", mirror_export._read_vetted_file),
        ), mock.patch.object(
            mirror_export.os, "rename",
            wrap("rename", os.rename),
        ):
            result = mirror_export.apply_plan(plan)
        self.assertIsNotNone(result)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.new_hash)
        return events

    def test_final_staging_hash_is_last_content_verification(self):
        # Ordering of the final sequence: source verification, then the
        # destination content rescan, then the staging scan whose bytes
        # feed the final hash — and no content verification of any kind
        # after it, before the first promotion rename.
        events = self.instrumented_export()
        first_rename = events.index("rename")
        last_hash_source = max(
            i for i, e in enumerate(events) if e == "hash_source_done"
        )
        last_rescan = max(
            i for i, e in enumerate(events) if e == "rescan_dest_done"
        )
        last_scan_staging = max(
            i for i, e in enumerate(events) if e == "scan_staging_done"
        )
        self.assertLess(last_hash_source, last_rescan)
        self.assertLess(last_rescan, last_scan_staging)
        self.assertLess(last_scan_staging, first_rename)
        content = {"scan_source", "hash_source", "rescan_dest",
                   "scan_staging", "read"}
        between = [
            e for e in events[last_scan_staging + 1:first_rename]
            if e in content
        ]
        self.assertEqual(between, [])

    def test_no_long_post_hash_verification_window(self):
        # The window between the final staging content read and the
        # promotion rename contains ZERO content reads: identity lstats
        # only. Every vetted read in the whole apply precedes the first
        # rename.
        events = self.instrumented_export()
        first_rename = events.index("rename")
        last_scan_staging = max(
            i for i, e in enumerate(events) if e == "scan_staging_done"
        )
        read_indexes = [i for i, e in enumerate(events) if e == "read"]
        self.assertTrue(read_indexes)
        self.assertTrue(all(i < first_rename for i in read_indexes))
        self.assertTrue(all(i < last_scan_staging for i in read_indexes))


# ---------------------------------------------------------------------------
# Fifth corrective pass — Q5: source mount containment


class TestSourceMountContainment(MutatedExportCase):
    def doctored_source_lstat(self, victim: Path):
        real_lstat = os.lstat

        def doctored(path, *args, **kwargs):
            st = real_lstat(path, *args, **kwargs)
            if kwargs.get("dir_fd") is None and Path(path) == victim:
                return os.stat_result((
                    st.st_mode, st.st_ino, st.st_dev + 1, st.st_nlink,
                    st.st_uid, st.st_gid, st.st_size,
                    st.st_atime, st.st_mtime, st.st_ctime,
                ))
            return st

        return mock.patch.object(mirror_export.os, "lstat", doctored)

    def test_source_entity_cross_device_refuses(self):
        # A source entity directory reports a different st_dev than the
        # pinned source root (mocked cross-device condition): the source
        # scan must refuse before anything is copied or hashed.
        target = mirror_export.check_destination(
            self.aos_dir, str(self.dest_root)
        )
        with self.doctored_source_lstat(self.source / "Tasks"):
            with self.assertRaises(AosError) as ctx:
                mirror_export.compute_plan(self.aos_dir, target)
        msg = str(ctx.exception)
        self.assertIn("mounted or cross-device subtree", msg)
        self.assertIn("Tasks", msg)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())

    def test_source_file_cross_device_refuses(self):
        # The FILE branch of the source device check: a single source
        # NOTE reports a different st_dev (a bind-mounted single file is
        # legal on Linux) while its entity directory is clean — only the
        # per-file comparison can refuse it.
        target = mirror_export.check_destination(
            self.aos_dir, str(self.dest_root)
        )
        victim = self.source / "Tasks" / "T-0001.md"
        self.assertTrue(victim.is_file())
        with self.doctored_source_lstat(victim):
            with self.assertRaises(AosError) as ctx:
                mirror_export.compute_plan(self.aos_dir, target)
        msg = str(ctx.exception)
        self.assertIn("mounted or cross-device subtree", msg)
        self.assertIn("T-0001.md", msg)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
        self.assertFalse(self.staging.exists())

    def test_source_entity_mount_refuses(self):
        # The additive mount probe: the entity directory reports as a
        # mount point (same device). Refuse, name the offender.
        target = mirror_export.check_destination(
            self.aos_dir, str(self.dest_root)
        )
        victim = self.source / "Tasks"
        with mock.patch.object(
            mirror_export.os.path, "ismount",
            lambda path: Path(path) == victim,
        ):
            with self.assertRaises(AosError) as ctx:
                mirror_export.compute_plan(self.aos_dir, target)
        msg = str(ctx.exception)
        self.assertIn("mounted or cross-device subtree", msg)
        self.assertIn("Tasks", msg)
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)

    def test_source_mount_content_is_never_read(self):
        # The mount refusal fires inside the source SCAN — before any
        # vetted read, any copy, and any hash: not a single byte of the
        # mounted subtree (or anything else) is read once the offender
        # is seen.
        target = mirror_export.check_destination(
            self.aos_dir, str(self.dest_root)
        )
        victim = self.source / "Tasks"
        reads = []
        real_read = mirror_export._read_vetted_file

        def spy_read(name, dirfd, rel, expect=None):
            reads.append(str(rel))
            return real_read(name, dirfd, rel, expect)

        opened = []
        real_open = os.open

        def spy_open(path, *args, **kwargs):
            if isinstance(path, (str, Path)) and str(path).startswith(
                str(victim) + os.sep
            ):
                opened.append(str(path))
            return real_open(path, *args, **kwargs)

        with mock.patch.object(
            mirror_export.os.path, "ismount",
            lambda path: Path(path) == victim,
        ), mock.patch.object(
            mirror_export, "_read_vetted_file", spy_read
        ), mock.patch.object(mirror_export.os, "open", spy_open):
            with self.assertRaises(AosError) as ctx:
                mirror_export.compute_plan(self.aos_dir, target)
        self.assertIn("mounted or cross-device subtree", str(ctx.exception))
        self.assertEqual(reads, [])
        self.assertEqual(opened, [])
        self.assertEqual(utils.tree_hash(self.dest_aos), self.old_hash)
