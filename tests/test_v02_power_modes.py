"""U-E2 runtime power modes: eco / standard / deep / recovery.

Contract: agentic-os-v0.2-u-e2-power-modes-contract.md

These tests exercise the real production branches and then inspect the
resulting filesystem/ledger state. They never assert on generic error
wording, and they never assert that a refusal happened without also proving
that nothing was written.

Fixture reminder (Night-1 shape, from weekend_harness): project `demo`;
T-0001 done (note evidence); T-0002 ready in demo; T-0003 projectless inbox
capture.
"""

from __future__ import annotations

import os
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from weekend_harness import Night1BackCompatCase

from agentic_os import cli, db, migrations, obsidian, power, utils

REPO_ROOT = Path(__file__).resolve().parent.parent

#: A synthetic credential-shaped string. Never a real secret; it exists to be
#: planted and then proven ABSENT from every diagnostic surface.
PLANTED_SECRET = "password: hunter2-hunter2-hunter2"

#: The exact serialized form the contract pins.
EXPECTED_BYTES = {
    mode: ('{"version":1,"mode":"%s"}\n' % mode).encode("utf-8")
    for mode in power.MODES
}


class PowerCase(Night1BackCompatCase):
    """Night-1 workspace, driven via --root from an unrelated cwd."""

    def setUp(self):
        super().setUp()
        self.power_path = self.aos_dir / power.STATE_FILENAME
        self.home_md = (
            self.aos_dir / obsidian.VAULT_DIRNAME / "AOS" / "Home.md"
        )

    def clean_workspace(self) -> tuple[Path, Path]:
        """A freshly initialized workspace with NO tasks — the only shape
        that is genuinely warning-free.

        The Night-1 fixture is not: T-0001 is a done `code` task with note
        (not commit) evidence, which legitimately trips doctor's warn-only
        check 17. Suggestion priority 3/4 need a workspace with nothing to
        warn about, or they would prove nothing.
        """
        root = self.new_tmp_dir("clean")
        self.ok("--root", str(root), "init")
        return root, root / utils.AOS_DIR_NAME

    # -- state helpers ----------------------------------------------------

    def write_raw(self, text: str | bytes) -> None:
        """Plant a power.json byte-for-byte, bypassing the writer."""
        data = text.encode("utf-8") if isinstance(text, str) else text
        self.power_path.write_bytes(data)

    def state_bytes(self) -> bytes:
        return self.power_path.read_bytes()

    def assert_no_state_file(self) -> None:
        self.assertFalse(
            self.power_path.exists(),
            "a read-only command created power.json",
        )

    def assert_no_debris(self) -> None:
        debris = sorted(
            p.name
            for p in self.aos_dir.iterdir()
            if p.name.startswith(power._TMP_PREFIX)
        )
        self.assertEqual(debris, [], f"temporary debris left behind: {debris}")

    def set_mode_direct(self, mode: str) -> None:
        """Set the mode through the production writer, bypassing the doctor
        transition gate — for arranging a starting state."""
        power.write_state(self.aos_dir, mode)

    # -- ledger helpers ---------------------------------------------------

    def count(self, table: str) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        finally:
            conn.close()

    def row_counts(self) -> dict[str, int]:
        return {
            t: self.count(t)
            for t in ("tasks", "projects", "evidence", "runs", "events",
                      "handoffs", "memory", "decisions", "packs", "agents")
        }

    def corrupt_db_pages(self) -> None:
        """Corrupt a b-tree page body so the database still OPENS but
        PRAGMA integrity_check reports errors — real corruption, not a mock."""
        with open(self.db_path, "r+b") as fh:
            fh.seek(4096 + 8)
            fh.write(b"\xde\xad\xbe\xef" * 40)


# ---------------------------------------------------------------------------
# (1)(2)(3) State: default, round-trip, idempotence

class StateBasicsTests(PowerCase):
    def test_missing_file_means_standard_and_creates_nothing(self):
        """(1) Absence is a valid state, and no read-only command may end it."""
        state = power.read_state(self.aos_dir)
        self.assertEqual(state.mode, "standard")
        self.assertFalse(state.configured)
        self.assert_no_state_file()

        for argv in (
            ("power", "status"), ("power", "suggest"), ("doctor",),
            ("status",), ("task", "list"), ("log",), ("search", "demo"),
        ):
            with self.subTest(argv=argv):
                self.run_cli("--root", str(self.root), *argv)
                self.assert_no_state_file()

    def test_all_four_modes_round_trip(self):
        """(2) Every mode writes the pinned bytes and reads back."""
        for mode in power.MODES:
            with self.subTest(mode=mode):
                self.aos("power", "set", mode)
                self.assertEqual(self.state_bytes(), EXPECTED_BYTES[mode])
                state = power.read_state(self.aos_dir)
                self.assertEqual(state.mode, mode)
                self.assertTrue(state.configured)
                self.assert_no_debris()
                # Leaving recovery needs a clean doctor; the fixture is clean.
                if mode == "recovery":
                    self.aos("power", "set", "standard")

    def test_same_mode_set_is_byte_identical_no_op(self):
        """(3) An idempotent set must not rewrite the file at all."""
        self.aos("power", "set", "deep")
        before = self.state_bytes()
        stat_before = self.power_path.stat()

        out = self.aos("power", "set", "deep")

        self.assertIn("nothing changed", out)
        self.assertEqual(self.state_bytes(), before)
        after = self.power_path.stat()
        # Not rewritten: same inode and same mtime_ns. os.replace would
        # change the inode even when the bytes matched.
        self.assertEqual(after.st_ino, stat_before.st_ino)
        self.assertEqual(after.st_mtime_ns, stat_before.st_mtime_ns)
        self.assert_no_debris()

    def test_pinned_serialization_is_exactly_the_contract_form(self):
        self.assertEqual(
            power.serialize("standard"), b'{"version":1,"mode":"standard"}\n'
        )

    def test_absent_file_plus_set_standard_pins_it(self):
        """Absent + `set standard` is a real request to pin (contract 2.5):
        it creates the file, and pinning is observable in doctor."""
        self.assert_no_state_file()
        self.aos("power", "set", "standard")
        self.assertEqual(self.state_bytes(), EXPECTED_BYTES["standard"])
        self.assertTrue(power.read_state(self.aos_dir).configured)


# ---------------------------------------------------------------------------
# (4) Malformed state refuses

class MalformedStateTests(PowerCase):
    #: (label, raw bytes) — each must be refused, never repaired.
    CASES = (
        ("not json", "not json at all\n"),
        ("truncated json", '{"version":1,"mode":"eco"'),
        ("trailing data", '{"version":1,"mode":"eco"}{"version":1}\n'),
        ("trailing garbage", '{"version":1,"mode":"eco"} trailing\n'),
        ("duplicate keys", '{"version":1,"mode":"eco","mode":"recovery"}\n'),
        ("wrong version", '{"version":2,"mode":"eco"}\n'),
        ("version as bool", '{"version":true,"mode":"eco"}\n'),
        ("version as string", '{"version":"1","mode":"eco"}\n'),
        ("unknown mode", '{"version":1,"mode":"turbo"}\n'),
        ("non-string mode", '{"version":1,"mode":7}\n'),
        ("unknown field", '{"version":1,"mode":"eco","extra":1}\n'),
        ("missing mode", '{"version":1}\n'),
        ("missing version", '{"mode":"eco"}\n'),
        ("not an object", '["version",1]\n'),
        ("json null", "null\n"),
        ("empty file", ""),
    )

    def test_every_malformed_state_is_refused(self):
        """(4) read_state refuses and never rewrites the planted bytes."""
        for label, raw in self.CASES:
            with self.subTest(case=label):
                self.write_raw(raw)
                planted = self.state_bytes()
                with self.assertRaises(power.PowerStateError) as caught:
                    power.read_state(self.aos_dir)
                self.assertEqual(caught.exception.exit_code, 1)
                self.assertEqual(self.state_bytes(), planted)

    def test_oversized_file_refused_without_reading_it(self):
        self.write_raw("x" * (power.MAX_STATE_BYTES + 1))
        with self.assertRaises(power.PowerStateError):
            power.read_state(self.aos_dir)

    def test_invalid_utf8_refused(self):
        self.write_raw(b'{"version":1,"mode":"\xff\xfe"}\n')
        with self.assertRaises(power.PowerStateError):
            power.read_state(self.aos_dir)

    def test_malformed_state_refuses_every_transition_without_replacement(self):
        """A malformed state is never silently repaired — including by the
        very command that would otherwise overwrite it."""
        self.write_raw('{"version":9,"mode":"eco"}\n')
        planted = self.state_bytes()
        for mode in power.MODES:
            with self.subTest(mode=mode):
                code, out, err = self.run_cli(
                    "--root", str(self.root), "power", "set", mode
                )
                self.assertEqual(code, 1)
                self.assertEqual(out, "")
                self.assertEqual(self.state_bytes(), planted)

    def test_malformed_state_blocks_writes_but_not_reads(self):
        """Fail-closed on an unknown mode (contract 2.2): a malformed state
        could be hiding a configured 'recovery', so nothing that writes may
        proceed — but reads must, so the human can see and fix it."""
        self.write_raw("garbage\n")
        before = self.row_counts()

        for argv in (("task", "add", "x", "-p", "demo"), ("sync",),
                     ("snapshot",), ("in", "note")):
            with self.subTest(blocked=argv):
                code, out, err = self.run_cli(
                    "--root", str(self.root), *argv
                )
                self.assertEqual(code, 1)
                self.assertEqual(out, "", "stdout must stay empty")
        self.assertEqual(self.row_counts(), before)

        for argv in (("doctor",), ("power", "status"), ("status",)):
            with self.subTest(allowed=argv):
                code, _out, _err = self.run_cli(
                    "--root", str(self.root), *argv
                )
                # doctor and power status exit 1 by REPORTING the problem,
                # not by refusing to run. Their stdout carries the report.
                self.assertIn(code, (0, 1))


# ---------------------------------------------------------------------------
# (5) Unsafe state objects refuse, unchanged

class UnsafeStateObjectTests(PowerCase):
    def _assert_refused_unchanged(self, describe: str) -> None:
        with self.assertRaises(power.PowerStateError):
            power.read_state(self.aos_dir)
        with self.assertRaises(power.PowerStateError):
            power.write_state(self.aos_dir, "eco")
        self.assertTrue(
            os.path.lexists(self.power_path),
            f"{describe} was removed instead of refused",
        )

    def test_symlink_refused_and_never_followed(self):
        target = self.root / "elsewhere.json"
        target.write_bytes(EXPECTED_BYTES["deep"])
        self.power_path.symlink_to(target)

        self._assert_refused_unchanged("the symlink")
        # Still a symlink, and the target is untouched: never followed.
        self.assertTrue(self.power_path.is_symlink())
        self.assertEqual(target.read_bytes(), EXPECTED_BYTES["deep"])

    def test_directory_refused(self):
        self.power_path.mkdir()
        self._assert_refused_unchanged("the directory")
        self.assertTrue(self.power_path.is_dir())

    @unittest.skipUnless(hasattr(os, "mkfifo"), "no FIFO support")
    def test_fifo_refused(self):
        os.mkfifo(self.power_path)
        self._assert_refused_unchanged("the FIFO")
        self.assertTrue(stat.S_ISFIFO(os.lstat(self.power_path).st_mode))

    def test_socket_refused(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.addCleanup(sock.close)
        try:
            sock.bind(str(self.power_path))
        except OSError as exc:  # pragma: no cover - platform dependent
            self.skipTest(f"cannot bind a unix socket here: {exc}")
        self._assert_refused_unchanged("the socket")
        self.assertTrue(stat.S_ISSOCK(os.lstat(self.power_path).st_mode))

    def test_device_refused_at_the_classifier(self):
        """/dev/null is a character device: no root needed to prove the
        production classifier refuses one."""
        dev = Path("/dev/null")
        if not dev.exists() or not stat.S_ISCHR(os.lstat(dev).st_mode):
            self.skipTest("no character device available")
        with self.assertRaises(power.PowerStateError):
            power._inspect_state_object(dev)


# ---------------------------------------------------------------------------
# (6)(7) Atomicity and concurrency

class AtomicityTests(PowerCase):
    def test_failure_before_replace_preserves_previous_bytes(self):
        """(6) An injected os.replace failure must leave the old state and
        no debris."""
        self.set_mode_direct("deep")
        before = self.state_bytes()

        with mock.patch(
            "agentic_os.power.os.replace", side_effect=OSError(5, "injected")
        ):
            with self.assertRaises(power.PowerStateError):
                power.write_state(self.aos_dir, "eco")

        self.assertEqual(self.state_bytes(), before)
        self.assert_no_debris()

    def test_failure_after_temp_creation_leaves_no_debris(self):
        """(6) An injected fsync failure fires with the temp file already
        created — the finally must still clean it up."""
        self.set_mode_direct("standard")
        before = self.state_bytes()

        with mock.patch(
            "agentic_os.power.os.fsync", side_effect=OSError(5, "injected")
        ):
            with self.assertRaises(power.PowerStateError):
                power.write_state(self.aos_dir, "recovery")

        self.assertEqual(self.state_bytes(), before)
        self.assert_no_debris()

    def test_failure_with_no_previous_state_creates_no_file(self):
        self.assert_no_state_file()
        with mock.patch(
            "agentic_os.power.os.replace", side_effect=OSError(5, "injected")
        ):
            with self.assertRaises(power.PowerStateError):
                power.write_state(self.aos_dir, "eco")
        self.assert_no_state_file()
        self.assert_no_debris()

    def test_concurrent_sets_always_leave_one_valid_complete_state(self):
        """(7) os.replace is the serialization point: every writer renames an
        already-complete valid file, so no interleaving can produce mixed or
        malformed JSON."""
        modes = [m for m in power.MODES for _ in range(12)]
        barrier = threading.Barrier(len(modes))
        errors: list[BaseException] = []
        # Readers race the writers: a reader must never observe a partial
        # file (it would see it through read_state, which validates).
        observed: list[str] = []

        def writer(mode: str) -> None:
            try:
                barrier.wait()
                power.write_state(self.aos_dir, mode)
                observed.append(power.read_state(self.aos_dir).mode)
            except BaseException as exc:  # noqa: BLE001 - reported below
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(m,)) for m in modes]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"concurrent set raised: {errors[:3]}")
        # Every observation was one complete valid state...
        for mode in observed:
            self.assertIn(mode, power.MODES)
        # ...and the final file is exactly one of the requested states.
        final = power.read_state(self.aos_dir)
        self.assertIn(final.mode, power.MODES)
        self.assertEqual(self.state_bytes(), EXPECTED_BYTES[final.mode])
        self.assert_no_debris()

    def test_unsafe_object_replacement_never_occurs_under_concurrency(self):
        """A writer that finds an unsafe object refuses rather than racing to
        replace it."""
        self.power_path.mkdir()
        for mode in power.MODES:
            with self.assertRaises(power.PowerStateError):
                power.write_state(self.aos_dir, mode)
        self.assertTrue(self.power_path.is_dir())
        self.assert_no_debris()

    def test_read_only_commands_never_mutate_power_json(self):
        self.aos("power", "set", "deep")
        before = self.state_bytes()
        stat_before = self.power_path.stat()
        for argv in (
            ("power", "status"), ("power", "suggest"), ("doctor",),
            ("status",), ("task", "list"), ("task", "show", "T-0002"),
            ("memory", "list"), ("agent", "list"), ("log",),
            ("search", "demo"), ("migrate", "status"), ("migrate", "plan"),
        ):
            with self.subTest(argv=argv):
                self.run_cli("--root", str(self.root), *argv)
                self.assertEqual(self.state_bytes(), before)
                self.assertEqual(
                    self.power_path.stat().st_mtime_ns, stat_before.st_mtime_ns
                )


# ---------------------------------------------------------------------------
# (8) Command classification coverage

class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.leaves = set(power.iter_command_paths(cli.build_parser()))

    def test_every_cli_leaf_has_exactly_one_classification(self):
        """(8) Walks the LIVE argparse tree: a new command cannot slip past
        by being forgotten in the table."""
        unclassified = sorted(self.leaves - set(power.COMMAND_POLICY))
        self.assertEqual(
            unclassified, [],
            f"unclassified CLI leaf/leaves: {unclassified}. Add each to "
            "power.COMMAND_POLICY — classification is never inferred.",
        )

    def test_no_classification_entry_without_a_command(self):
        """The table must not rot: an entry for a removed command would be a
        silent lie about coverage."""
        orphans = sorted(set(power.COMMAND_POLICY) - self.leaves)
        self.assertEqual(orphans, [], f"stale classification entries: {orphans}")

    def test_every_classification_is_a_known_kind(self):
        for path, policy in sorted(power.COMMAND_POLICY.items()):
            with self.subTest(path=path):
                self.assertIn(policy.kind, power.KINDS)

    def test_the_tree_walk_actually_finds_the_commands(self):
        """Guards the guard: a walk that silently returned {} would make
        the coverage test vacuous."""
        self.assertGreater(len(self.leaves), 40)
        for expected in (("task", "add"), ("power", "set"), ("doctor",),
                         ("sync",), ("init",)):
            self.assertIn(expected, self.leaves)

    def test_ledger_flag_only_on_authoritative_writes(self):
        for path, policy in sorted(power.COMMAND_POLICY.items()):
            if policy.ledger:
                with self.subTest(path=path):
                    self.assertEqual(policy.kind, power.AUTHORITATIVE_WRITE)

    def test_unclassified_path_fails_closed(self):
        policy = power.policy_for(("no", "such", "command"))
        self.assertEqual(policy.kind, power.AUTHORITATIVE_WRITE)
        self.assertTrue(policy.ledger)


# ---------------------------------------------------------------------------
# (9)(10) eco and standard

class EcoTests(PowerCase):
    def test_eco_permits_authoritative_writes_and_explicit_derived(self):
        """(9) eco defers only implicit optional work — never what the human
        explicitly asked for."""
        self.aos("power", "set", "eco")
        before = self.count("tasks")

        self.aos("task", "add", "eco task", "-p", "demo")
        self.assertEqual(self.count("tasks"), before + 1)
        # Explicit derived work stays available.
        self.aos("sync")
        self.aos("review", "build")
        self.aos("export", "events", "--jsonl")
        # And explicitly requested backups are never deferred.
        self.aos("backup", "create")

    def test_eco_defers_only_the_idempotent_mirror_reheal(self):
        """(9) The one implicit/optional derived site in the baseline."""
        home = self.home_md
        self.assertTrue(home.is_file())
        self.aos("power", "set", "eco")
        home.unlink()

        out = self.aos("init", "--root", str(self.root))

        self.assertIn("eco:", out)
        self.assertFalse(home.is_file(), "eco did not defer the re-heal")
        # Deferred, not lost: the explicit command regenerates it.
        self.aos("sync")
        self.assertTrue(home.is_file())

    def test_eco_never_defers_the_heal_for_a_fresh_workspace(self):
        """A new workspace must be usable, so created=True always heals."""
        fresh = self.new_tmp_dir("fresh")
        self.ok("--root", str(fresh), "init")
        self.assertTrue(
            (fresh / utils.AOS_DIR_NAME / obsidian.VAULT_DIRNAME / "AOS"
             / "Home.md").is_file()
        )


class StandardBaselineTests(PowerCase):
    def test_standard_preserves_the_init_reheal_baseline(self):
        """(10) Standard heals exactly as the baseline did."""
        home = self.home_md
        self.aos("power", "set", "standard")
        home.unlink()
        out = self.aos("init", "--root", str(self.root))
        self.assertNotIn("eco:", out)
        self.assertTrue(home.is_file(), "standard must still re-heal")

    def test_default_mode_preserves_the_init_reheal_baseline(self):
        """(10)(25) With NO power.json at all — the pure baseline path."""
        self.assert_no_state_file()
        home = self.home_md
        home.unlink()
        self.aos("init", "--root", str(self.root))
        self.assertTrue(home.is_file())
        self.assert_no_state_file()

    def test_standard_adds_no_preflight_and_no_automatic_doctor(self):
        """(10) A standard authoritative write prints exactly what it always
        printed: no preflight line, no doctor report."""
        self.aos("power", "set", "standard")
        out = self.aos("task", "add", "plain", "-p", "demo")
        self.assertEqual(out, "T-0004\n")


# ---------------------------------------------------------------------------
# (11)(12)(13)(14) deep

class DeepPreflightTests(PowerCase):
    def test_deep_preflight_blocks_authoritative_write_on_integrity_failure(self):
        """(11) Real page corruption, not a mock."""
        self.aos("power", "set", "deep")
        self.corrupt_db_pages()

        code, out, err = self.run_cli(
            "--root", str(self.root), "task", "add", "nope", "-p", "demo"
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "", "stdout must stay empty on a refusal")
        self.assertIn("Nothing was written", err)

    def test_deep_preflight_blocks_authoritative_write_on_secret_sweep(self):
        """(12) A warned trusted write plants a secret-shaped value in a
        canonical row; deep then refuses the NEXT authoritative write."""
        self.run_cli(
            "--root", str(self.root), "task", "edit", "T-0002",
            "--accept", PLANTED_SECRET,
        )
        self.aos("power", "set", "deep")  # secret sweep is warn-only: allowed
        before = self.row_counts()

        code, out, err = self.run_cli(
            "--root", str(self.root), "task", "add", "nope", "-p", "demo"
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("secret sweep", err)
        self.assertEqual(self.row_counts(), before, "refusal wrote something")

    def test_deep_diagnostics_echo_no_planted_values(self):
        """(13) The refusal names the check and a count — never the value."""
        self.run_cli(
            "--root", str(self.root), "task", "edit", "T-0002",
            "--accept", PLANTED_SECRET,
        )
        self.aos("power", "set", "deep")
        _code, out, err = self.run_cli(
            "--root", str(self.root), "task", "add", "nope", "-p", "demo"
        )
        for surface, text in (("stdout", out), ("stderr", err)):
            with self.subTest(surface=surface):
                self.assertNotIn("hunter2", text)
                self.assertNotIn(PLANTED_SECRET, text)
                # No SQL, no row content, no exception internals.
                self.assertNotIn("SELECT", text)
                self.assertNotIn("Traceback", text)
        # A count, and only a count — the number itself is not asserted
        # exactly (the sweep legitimately finds the row AND the event
        # metadata); what matters is that it is a count, not content.
        self.assertRegex(err, r"ledger secret sweep \(\d+ finding\(s\)\)")

    def test_deep_preflight_skips_read_only_and_derived_commands(self):
        """(11) Corruption that refuses an authoritative write must NOT add a
        preflight to commands that do not touch authoritative data."""
        self.aos("power", "set", "deep")
        self.aos("power", "status")
        self.aos("power", "suggest")
        # A derived_write command gets no deep preflight gate of its own.
        ctx_kinds = {
            power.COMMAND_POLICY[("sync",)].kind,
            power.COMMAND_POLICY[("task", "list")].kind,
        }
        self.assertEqual(ctx_kinds, {power.DERIVED_WRITE, power.READ_ONLY})

    def test_deep_post_verification_reports_committed_but_unhealthy(self):
        """(14) A warned trusted write is the real committed-but-unhealthy
        case: the preflight is clean, the write COMMITS the secret-shaped
        value, and post-verification then finds it."""
        self.aos("power", "set", "deep")
        before = self.count("tasks")

        code, out, err = self.run_cli(
            "--root", str(self.root), "task", "edit", "T-0002",
            "--accept", PLANTED_SECRET,
        )

        self.assertEqual(code, 1)
        # The write really did commit — this is the honesty requirement.
        conn = sqlite3.connect(self.db_path)
        try:
            stored = conn.execute(
                "SELECT acceptance_md FROM tasks WHERE id = 2"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(stored, PLANTED_SECRET)
        # It says so, and never claims a rollback.
        self.assertIn("COMMITTED", err)
        self.assertIn("was NOT", err)
        self.assertIn("power set recovery", err)
        for lie in ("rolled back the", "reverted", "undone"):
            self.assertNotIn(lie, err)
        # And it did not echo the value it is warning about.
        self.assertNotIn("hunter2", err)
        self.assertNotIn("hunter2", out)
        # No destructive automatic rollback of anything else.
        self.assertEqual(self.count("tasks"), before)

    def test_deep_allows_a_clean_authoritative_write(self):
        self.aos("power", "set", "deep")
        out = self.aos("task", "add", "clean", "-p", "demo")
        self.assertEqual(out, "T-0004\n")


# ---------------------------------------------------------------------------
# (15)(16) recovery

class RecoveryTests(PowerCase):
    #: (command path, argv) for every authoritative/derived mutation. The
    #: arguments WOULD otherwise succeed against the fixture, so a refusal
    #: proves the gate blocked it — not that the command failed for its own
    #: reasons. `SELF` is substituted with the workspace root.
    BLOCKED = (
        (("task", "add"), ("task", "add", "x", "-p", "demo")),
        (("task", "edit"), ("task", "edit", "T-0002", "--title", "renamed")),
        (("task", "status"), ("task", "status", "T-0002", "doing")),
        (("task", "assign"), ("task", "assign", "T-0003", "-p", "demo")),
        (("project", "add"),
         ("project", "add", "other", "--name", "O", "--repo", "SELF")),
        (("in",), ("in", "captured note")),
        (("run", "start"), ("run", "start", "T-0002", "--agent", "claude-code")),
        (("run", "end"),
         ("run", "end", "R-0001", "--outcome", "success", "--summary", "s")),
        (("evidence", "add"),
         ("evidence", "add", "T-0002", "--kind", "note", "--ref", "r")),
        (("evidence", "git"), ("evidence", "git", "T-0002", "HEAD")),
        (("decision", "add"),
         ("decision", "add", "D", "-p", "demo", "--decision", "x")),
        (("handoff", "create"),
         ("handoff", "create", "T-0002", "--from", "a", "--to", "b",
          "--state", "s")),
        (("handoff", "accept"), ("handoff", "accept", "H-0001")),
        (("memory", "add"),
         ("memory", "add", "--scope", "global", "--kind", "fact", "--key", "k",
          "--value", "v", "--source", "human", "--confidence", "high")),
        (("memory", "retire"), ("memory", "retire", "M-0001")),
        # U-M2 curation writes: each mutates a claim, its hash and an event.
        (("memory", "pin"), ("memory", "pin", "M-0001")),
        (("memory", "unpin"), ("memory", "unpin", "M-0001")),
        (("memory", "link-evidence"),
         ("memory", "link-evidence", "M-0001", "E-0001")),
        # U-M3 graph writes: each mutates a canonical row, its integrity hash
        # and an event in one transaction.
        (("memory", "classify"), ("memory", "classify", "M-0001", "restricted")),
        (("memory", "source", "add"),
         ("memory", "source", "add", "--kind", "url", "--locator", "https://x.test")),
        (("memory", "source", "link"),
         ("memory", "source", "link", "M-0001", "MS-0001", "--relation", "supports")),
        (("memory", "edge", "add"),
         ("memory", "edge", "add", "M-0001", "M-0002", "--relation", "related")),
        # U-A1 governed agent writes: identity/passport rows + their hashes
        # + an event in one transaction each.
        (("agent", "create"), ("agent", "create", "newbot")),
        (("agent", "import"), ("agent", "import", "nonexistent.json")),
        (("agent", "passport", "publish"),
         ("agent", "passport", "publish", "newbot")),
        (("agent", "suspend"), ("agent", "suspend", "newbot")),
        (("agent", "archive"), ("agent", "archive", "newbot")),
        (("agent", "restore"), ("agent", "restore", "newbot")),
        (("agent", "revoke"), ("agent", "revoke", "newbot")),
        (("agent", "discard"), ("agent", "discard", "newbot")),
        (("ingest", "dropfile"), ("ingest", "dropfile", "SELF")),
        (("done",), ("done", "T-0002", "--no-evidence", "--reason", "because")),
        (("pack", "build"), ("pack", "build", "T-0002")),
        (("snapshot",), ("snapshot",)),
        (("backup", "create"), ("backup", "create")),
        (("sync",), ("sync",)),
        (("export", "events"), ("export", "events", "--jsonl")),
        (("review", "build"), ("review", "build")),
        (("review", "weekly"), ("review", "weekly")),
        (("review", "project"), ("review", "project", "demo")),
        (("migrate", "apply"), ("migrate", "apply")),
        (("hooks", "install"), ("hooks", "install", "--apply")),
        (("hooks", "uninstall"), ("hooks", "uninstall", "--apply")),
        (("init",), ("init", "--root", "SELF")),
    )

    def test_recovery_blocks_every_authoritative_and_derived_mutation(self):
        """(15) Blocked BEFORE the command runs: stdout empty, ledger and
        mirror byte-identical."""
        self.aos("power", "set", "recovery")
        rows_before = self.row_counts()
        mirror_before = utils.tree_hash(self.aos_dir / obsidian.VAULT_DIRNAME)

        for path, argv in self.BLOCKED:
            argv = tuple(str(self.root) if a == "SELF" else a for a in argv)
            with self.subTest(command=" ".join(path)):
                code, out, err = self.run_cli("--root", str(self.root), *argv)
                self.assertEqual(code, 1, f"{path} was not refused")
                self.assertEqual(out, "", f"{path} wrote to stdout")
                self.assertIn("recovery mode", err)
                # The refusal identifies the blocked command path itself.
                self.assertIn(f"`{' '.join(path)}`", err)

        self.assertEqual(self.row_counts(), rows_before, "recovery mutated rows")
        self.assertEqual(
            utils.tree_hash(self.aos_dir / obsidian.VAULT_DIRNAME), mirror_before,
            "recovery regenerated the mirror",
        )

    def test_every_blockable_command_is_covered_by_the_block_list(self):
        """Guards the guard: BLOCKED must cover EVERY non-recovery-safe leaf,
        or the test above proves less than it claims."""
        leaves = set(power.iter_command_paths(cli.build_parser()))
        should_block = {
            p for p in leaves
            if power.COMMAND_POLICY[p].kind not in power.RECOVERY_ALLOWED_KINDS
        }
        covered = {path for path, _argv in self.BLOCKED}
        self.assertEqual(
            sorted(should_block - covered), [],
            "these blockable commands are untested in recovery",
        )
        self.assertEqual(
            sorted(covered - should_block), [],
            "these covered commands are not actually blockable",
        )

    def test_recovery_refusal_echoes_nothing_sensitive(self):
        """(15) The refusal names the command path and the mode — nothing
        from the payload the human just typed."""
        self.aos("power", "set", "recovery")
        code, out, err = self.run_cli(
            "--root", str(self.root), "task", "add", PLANTED_SECRET,
            "-p", "demo",
        )
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertNotIn("hunter2", err)
        self.assertNotIn(PLANTED_SECRET, err)
        self.assertNotIn("Traceback", err)
        self.assertIn("task add", err)
        self.assertIn("recovery", err)

    def test_recovery_allows_read_only_and_recovery_safe_commands(self):
        """(16)"""
        self.aos("backup", "create")
        backups = sorted((self.aos_dir / "backups").glob("*.db"))
        self.assertTrue(backups)
        self.aos("power", "set", "recovery")

        for argv in (
            ("power", "status"), ("power", "suggest"), ("doctor",),
            ("status",), ("task", "list"), ("task", "show", "T-0001"),
            ("memory", "list"), ("agent", "list"),
            ("log",), ("search", "demo"), ("hooks", "status"),
            ("migrate", "status"), ("migrate", "plan"),
            ("backup", "verify", str(backups[0])),
        ):
            with self.subTest(argv=argv):
                code, _out, err = self.run_cli("--root", str(self.root), *argv)
                self.assertEqual(code, 0, f"{argv} was refused: {err}")

    def test_recovery_allows_restore_to_a_distinct_new_path(self):
        """(16) U-C2's restore never overwrites the live database."""
        self.aos("backup", "create")
        backup = sorted((self.aos_dir / "backups").glob("*.db"))[0]
        self.aos("power", "set", "recovery")
        target = self.new_tmp_dir("restored") / "recovered.db"
        live_before = self.db_path.read_bytes()

        self.aos("backup", "restore", str(backup), "--to", str(target))

        self.assertTrue(target.is_file())
        self.assertEqual(self.db_path.read_bytes(), live_before)

    def test_idempotent_power_set_recovery_allowed_in_recovery(self):
        """(16)"""
        self.aos("power", "set", "recovery")
        before = self.state_bytes()
        out = self.aos("power", "set", "recovery")
        self.assertIn("nothing changed", out)
        self.assertEqual(self.state_bytes(), before)


class RecoveryTransitionTests(PowerCase):
    def test_set_recovery_works_while_doctor_has_hard_failures(self):
        """(17) The whole point: recovery control cannot depend on the health
        of the thing it recovers."""
        self.corrupt_db_pages()
        self.assertTrue(power.hard_doctor_failures(self.aos_dir))

        out = self.aos("power", "set", "recovery")

        self.assertIn("recovery", out)
        self.assertEqual(self.state_bytes(), EXPECTED_BYTES["recovery"])

    def test_set_recovery_works_when_the_database_cannot_be_opened(self):
        """(17) Even a totally unreadable ledger. `power` never calls
        db.open_db, so the schema gate cannot lock the human out."""
        self.db_path.write_bytes(b"this is not a database at all")
        self.aos("power", "set", "recovery")
        self.assertEqual(self.state_bytes(), EXPECTED_BYTES["recovery"])

    def test_set_recovery_works_on_an_unsupported_schema_version(self):
        """(17) A version-mismatched database hard-stops every normal
        command; recovery must still be reachable."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("UPDATE meta SET value='999' WHERE key='schema_version'")
            conn.commit()
        finally:
            conn.close()
        self.aos("power", "set", "recovery")
        self.assertEqual(self.state_bytes(), EXPECTED_BYTES["recovery"])

    def test_leaving_recovery_refuses_until_hard_checks_pass(self):
        """(18)"""
        self.aos("power", "set", "recovery")
        self.corrupt_db_pages()

        for mode in ("eco", "standard", "deep"):
            with self.subTest(mode=mode):
                code, out, err = self.run_cli(
                    "--root", str(self.root), "power", "set", mode
                )
                self.assertEqual(code, 1)
                self.assertEqual(out, "")
                self.assertIn("doctor", err)
                self.assertEqual(
                    self.state_bytes(), EXPECTED_BYTES["recovery"],
                    "a refused transition changed the state",
                )

    def test_leaving_recovery_succeeds_once_the_workspace_is_healthy(self):
        """(18) The gate opens — it does not merely never open."""
        self.aos("power", "set", "recovery")
        self.assertEqual(power.hard_doctor_failures(self.aos_dir), [])
        self.aos("power", "set", "standard")
        self.assertEqual(self.state_bytes(), EXPECTED_BYTES["standard"])

    def test_warn_only_checks_never_block_a_transition(self):
        """(18) Only HARD checks gate the transition."""
        self.run_cli(
            "--root", str(self.root), "task", "edit", "T-0002",
            "--accept", PLANTED_SECRET,
        )  # trips the warn-only secret sweep
        self.aos("power", "set", "recovery")
        self.aos("power", "set", "standard")
        self.assertEqual(self.state_bytes(), EXPECTED_BYTES["standard"])


# ---------------------------------------------------------------------------
# (19) Doctor integration

class DoctorIntegrationTests(PowerCase):
    def power_line(self, out: str) -> str:
        lines = [l for l in out.splitlines() if "runtime power state" in l]
        self.assertEqual(len(lines), 1, f"expected one power line in:\n{out}")
        return lines[0]

    def test_doctor_reports_the_default_state(self):
        """(19)"""
        self.assert_no_state_file()
        line = self.power_line(self.aos("doctor"))
        self.assertTrue(line.startswith("[PASS]"))
        self.assertIn("standard (default", line)
        self.assert_no_state_file()

    def test_doctor_reports_each_configured_mode(self):
        """(19)"""
        for mode in power.MODES:
            with self.subTest(mode=mode):
                self.set_mode_direct(mode)
                line = self.power_line(self.aos("doctor"))
                self.assertTrue(line.startswith("[PASS]"))
                self.assertIn(f"{mode} (configured", line)

    def test_doctor_reports_recovery_degradation(self):
        """(19)"""
        self.set_mode_direct("recovery")
        line = self.power_line(self.aos("doctor"))
        self.assertIn("authoritative writes blocked", line)

    def test_doctor_reports_malformed_state_and_does_not_crash(self):
        """(19) Doctor must stay RUNNABLE on a malformed file — reporting is
        the whole point, since a malformed state refuses every transition."""
        self.write_raw('{"version":1,"mode":"turbo"}\n')
        code, out, err = self.run_cli("--root", str(self.root), "doctor")
        self.assertEqual(code, 1)
        line = self.power_line(out)
        self.assertTrue(line.startswith("[FAIL]"))
        self.assertIn("malformed or unsafe", line)
        self.assertNotIn("Traceback", err)
        self.assertNotIn("Internal error", err)

    def test_doctor_never_prints_raw_json_or_the_path(self):
        """(19)"""
        self.set_mode_direct("deep")
        line = self.power_line(self.aos("doctor"))
        self.assertNotIn('{"version"', line)
        self.assertNotIn(str(self.aos_dir), line)

    def test_doctor_check_count_is_thirty_four(self):
        """(25) 20 → 21 → 25 → 30 → 31: the mandated power check joined the
        set at U-E2, then U-M2's four memory-claim checks, then U-M3's five
        memory-graph checks, then U-M5's one retrieval-benchmark registry
        check (the D-W8.1 pattern — the pin moves UP with a mandated new
        check)."""
        out = self.aos("doctor")
        self.assertEqual(len([l for l in out.strip().splitlines() if l]), 34)

    def test_doctor_still_passes_cleanly_on_the_baseline_fixture(self):
        """(25) The new checks do not disturb the ones already there."""
        out = self.aos("doctor")
        self.assertEqual(out.count("[FAIL]"), 0)


# ---------------------------------------------------------------------------
# (20)(21)(22) Deterministic suggestion

class SuggestionTests(PowerCase):
    def suggestion(self) -> str:
        return power.suggest(self.aos_dir)["mode"]

    def test_priority_1_hard_failure_suggests_recovery(self):
        """(20)"""
        self.corrupt_db_pages()
        self.assertEqual(self.suggestion(), "recovery")

    def test_priority_2_warning_suggests_deep(self):
        """(20) No hard failure, but a warn-only check trips."""
        self.run_cli(
            "--root", str(self.root), "task", "edit", "T-0002",
            "--accept", PLANTED_SECRET,
        )
        result = power.suggest(self.aos_dir)
        self.assertEqual(result["mode"], "deep")
        self.assertEqual(result["signal"], "doctor warning")

    def test_priority_3_active_run_suggests_standard(self):
        """(20) Clean, but there is live ledger work.

        Uses a genuinely warning-free workspace: the Night-1 fixture always
        trips warn-only check 17, which would mask priority 3 behind
        priority 2 and make this test prove nothing.
        """
        root, aos_dir = self.clean_workspace()
        self.assertEqual(power.suggest(aos_dir)["mode"], "eco")  # idle first

        self.ok("--root", str(root), "project", "add", "p",
                "--name", "P", "--repo", str(root))
        self.ok("--root", str(root), "task", "add", "t", "-p", "p")
        self.ok("--root", str(root), "run", "start", "T-0001",
                "--agent", "claude-code")

        result = power.suggest(aos_dir)
        self.assertEqual(result["mode"], "standard")
        self.assertEqual(result["signal"], "active ledger work")
        self.assertEqual(result["count"], 1)

    def test_priority_4_clean_and_idle_suggests_eco(self):
        """(20)"""
        _root, aos_dir = self.clean_workspace()
        result = power.suggest(aos_dir)
        self.assertEqual(result["mode"], "eco")
        self.assertEqual(result["signal"], "clean and idle")
        self.assertEqual(result["count"], 0)

    def test_hard_failure_outranks_a_warning_and_an_active_run(self):
        """(20) Priority is a strict order, not a blend."""
        self.aos("run", "start", "T-0002", "--agent", "claude-code")
        self.run_cli(
            "--root", str(self.root), "task", "edit", "T-0002",
            "--accept", PLANTED_SECRET,
        )
        self.corrupt_db_pages()
        self.assertEqual(self.suggestion(), "recovery")

    def test_warning_outranks_an_active_run(self):
        """(20) An active run alone would say standard; a warning wins."""
        root, aos_dir = self.clean_workspace()
        self.ok("--root", str(root), "project", "add", "p",
                "--name", "P", "--repo", str(root))
        self.ok("--root", str(root), "task", "add", "t", "-p", "p")
        self.ok("--root", str(root), "run", "start", "T-0001",
                "--agent", "claude-code")
        self.assertEqual(power.suggest(aos_dir)["mode"], "standard")

        self.run_cli("--root", str(root), "task", "edit", "T-0001",
                     "--accept", PLANTED_SECRET)

        self.assertEqual(power.suggest(aos_dir)["mode"], "deep")

    def test_suggestion_is_deterministic(self):
        first = power.suggest(self.aos_dir)
        for _ in range(3):
            self.assertEqual(power.suggest(self.aos_dir), first)

    def test_suggest_never_writes_power_json(self):
        """(21)"""
        self.assert_no_state_file()
        for _ in range(3):
            self.aos("power", "suggest")
        self.assert_no_state_file()

        self.set_mode_direct("recovery")
        before = self.state_bytes()
        stat_before = self.power_path.stat()
        self.aos("power", "suggest")
        self.assertEqual(self.state_bytes(), before)
        self.assertEqual(
            self.power_path.stat().st_mtime_ns, stat_before.st_mtime_ns
        )

    def test_suggest_never_switches_the_mode(self):
        """(21) Advisory only — the file and the effective mode are untouched
        even when the suggestion differs from the current mode."""
        self.set_mode_direct("recovery")
        suggested = power.suggest(self.aos_dir)["mode"]
        self.assertNotEqual(suggested, "recovery", "test would be vacuous")
        self.assertEqual(power.read_state(self.aos_dir).mode, "recovery")

    def test_suggest_echoes_no_titles_summaries_evidence_or_paths(self):
        """(22)"""
        self.run_cli(
            "--root", str(self.root), "task", "edit", "T-0002",
            "--accept", PLANTED_SECRET,
        )
        self.aos("run", "start", "T-0002", "--agent", "claude-code")
        out = self.aos("power", "suggest")

        self.assertNotIn("hunter2", out)
        self.assertNotIn(PLANTED_SECRET, out)
        for leak in (str(self.root), str(self.aos_dir), "aos.db", "demo",
                     "T-0001", "T-0002", "claude-code"):
            with self.subTest(leak=leak):
                self.assertNotIn(leak, out)

    def test_suggest_output_is_bounded_and_fixed_shape(self):
        """(22) Signal category + bounded count + one advisory line."""
        out = self.aos("power", "suggest")
        lines = out.strip().splitlines()
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("suggestion: "))
        self.assertTrue(lines[1].startswith("signal:"))
        self.assertIn("Advice only", lines[2])

    def test_suggest_signal_vocabulary_is_fixed(self):
        """(22) Every signal is a fixed phrase — never free text."""
        allowed = {
            "hard doctor failure", "doctor warning", "active ledger work",
            "clean and idle", "doctor could not complete",
        }
        self.assertIn(power.suggest(self.aos_dir)["signal"], allowed)
        self.corrupt_db_pages()
        self.assertIn(power.suggest(self.aos_dir)["signal"], allowed)


# ---------------------------------------------------------------------------
# Degradation matrix output

class MatrixOutputTests(PowerCase):
    def test_status_prints_all_four_modes_and_marks_the_active_one(self):
        self.aos("power", "set", "deep")
        out = self.aos("power", "status")
        for mode in power.MODES:
            self.assertIn(mode, out)
        active = [l for l in out.splitlines() if l.startswith("*")]
        self.assertEqual(len(active), 1)
        self.assertIn("deep", active[0])

    def test_matrix_is_stable_and_not_terminal_width_dependent(self):
        first = power.matrix_lines("eco")
        for width in ("40", "200", "1"):
            with mock.patch.dict(os.environ, {"COLUMNS": width}):
                self.assertEqual(power.matrix_lines("eco"), first)

    def test_matrix_says_auto_switch_is_never_yes(self):
        for mode in power.MODES:
            with self.subTest(mode=mode):
                self.assertEqual(power.MATRIX[mode][-1], "no")

    def test_matrix_covers_every_documented_dimension(self):
        self.assertEqual(len(power.MATRIX_COLUMNS), 6)
        for mode in power.MODES:
            self.assertEqual(len(power.MATRIX[mode]), len(power.MATRIX_COLUMNS))

    def test_status_reports_default_vs_configured(self):
        self.assertIn("(default)", self.aos("power", "status"))
        self.aos("power", "set", "eco")
        self.assertIn("(configured)", self.aos("power", "status"))

    def test_status_reports_a_malformed_state_without_raw_content(self):
        self.write_raw('{"version":1,"mode":"turbo","leak":"' +
                       PLANTED_SECRET + '"}\n')
        code, out, err = self.run_cli("--root", str(self.root), "power", "status")
        self.assertEqual(code, 1)
        self.assertIn("unknown", out)
        self.assertNotIn("hunter2", out + err)
        self.assertNotIn('{"version"', out + err)


# ---------------------------------------------------------------------------
# (23)(24) Entrypoint parity and zipapp

def _clean_env(**overrides) -> dict:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update(overrides)
    return env


class EntrypointParityTests(unittest.TestCase):
    """(23)(24) script / module / zipapp agree, and the archive is clean."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "aos_build_zipapp_e2", REPO_ROOT / "tools" / "build_zipapp.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls._tmp = tempfile.TemporaryDirectory()
        cls.outside = Path(cls._tmp.name).resolve()
        cls.archive = module.build(cls.outside / "aos.pyz")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.workspace = Path(tmp.name).resolve()

    def _run(self, entrypoint: str, workspace: Path, argv):
        """One command through one entrypoint, with PYTHONPATH cleared. The
        zipapp always runs from OUTSIDE the repository."""
        base = ["--root", str(workspace)]
        if entrypoint == "script":
            cmd, cwd = [sys.executable, str(REPO_ROOT / "aos.py")], REPO_ROOT
        elif entrypoint == "module":
            cmd, cwd = [sys.executable, "-m", "agentic_os"], REPO_ROOT
        else:
            cmd, cwd = [sys.executable, str(self.archive)], self.outside
        return subprocess.run(
            [*cmd, *base, *argv], cwd=str(cwd), env=_clean_env(),
            capture_output=True, text=True, timeout=120,
        )

    def assert_parity(self, argv, arrange=()) -> subprocess.CompletedProcess:
        """Run `argv` through all three entrypoints and require identical
        exit code, stdout and stderr.

        Each entrypoint gets its OWN freshly arranged workspace: `power set`
        is stateful, so running the three against one shared workspace would
        compare a first set against two idempotent no-ops and prove nothing.
        """
        results = {}
        for entrypoint in ("script", "module", "zipapp"):
            workspace = Path(
                tempfile.mkdtemp(dir=self.workspace, prefix=f"{entrypoint}-")
            )
            init = self._run(entrypoint, workspace, ["init"])
            self.assertEqual(init.returncode, 0, init.stderr)
            for pre in arrange:
                step = self._run(entrypoint, workspace, pre)
                self.assertEqual(step.returncode, 0, step.stderr)
            results[entrypoint] = self._run(entrypoint, workspace, argv)

        script = results["script"]
        for name in ("module", "zipapp"):
            other = results[name]
            with self.subTest(entrypoint=name, argv=list(argv)):
                self.assertEqual(other.returncode, script.returncode,
                                 f"{argv}: exit code differs\n{other.stderr}")
                self.assertEqual(other.stdout, script.stdout,
                                 f"{argv}: stdout differs")
                self.assertEqual(other.stderr, script.stderr,
                                 f"{argv}: stderr differs")
        return script

    def test_power_status_matches_across_entrypoints(self):
        """(23)(24)"""
        result = self.assert_parity(["power", "status"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("runtime power mode: standard (default)", result.stdout)

    def test_power_suggest_matches_across_entrypoints(self):
        """(23)(24)"""
        result = self.assert_parity(["power", "suggest"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("suggestion: eco", result.stdout)

    def test_power_set_matches_across_entrypoints(self):
        """(23)(24) Both the changing set and the idempotent no-op."""
        first = self.assert_parity(["power", "set", "eco"])
        self.assertIn("standard → eco", first.stdout)

        again = self.assert_parity(
            ["power", "set", "eco"], arrange=[["power", "set", "eco"]]
        )
        self.assertIn("nothing changed", again.stdout)

    def test_recovery_refusal_matches_across_entrypoints(self):
        """(23)(24) The safety-critical path: a refusal must be identical
        everywhere, or the zipapp is not the same tool."""
        refusal = self.assert_parity(
            ["task", "add", "x", "-p", "demo"],
            arrange=[["power", "set", "recovery"]],
        )
        self.assertEqual(refusal.returncode, 1)
        self.assertEqual(refusal.stdout, "")
        self.assertIn("blocked in recovery mode", refusal.stderr)

    def test_zipapp_carries_the_power_module(self):
        """(24) The U-P1 allowlist is `*.py` under the package, so power.py
        rides along automatically — no builder change."""
        import zipfile

        with zipfile.ZipFile(self.archive) as zf:
            names = set(zf.namelist())
        self.assertIn("agentic_os/power.py", names)

    def test_zipapp_embeds_no_workspace_database_or_state(self):
        """(24)"""
        import zipfile

        with zipfile.ZipFile(self.archive) as zf:
            names = zf.namelist()
        for name in names:
            with self.subTest(member=name):
                self.assertTrue(
                    name == "__main__.py" or name.startswith("agentic_os/"),
                    f"unexpected archive member: {name}",
                )
                self.assertFalse(name.endswith(".db"))
                self.assertFalse(name.endswith(".json"))
                self.assertNotIn("power.json", name)
                self.assertNotIn(".agentic-os", name)
                self.assertNotIn("tests/", name)

    def test_zipapp_runs_outside_the_repo_with_pythonpath_cleared(self):
        """(24)"""
        env = _clean_env()
        self.assertNotIn("PYTHONPATH", env)
        init = subprocess.run(
            [sys.executable, str(self.archive), "--root", str(self.workspace),
             "init"],
            cwd=str(self.outside), env=env, capture_output=True, text=True,
            timeout=120,
        )
        self.assertEqual(init.returncode, 0, init.stderr)
        result = subprocess.run(
            [sys.executable, str(self.archive), "--root", str(self.workspace),
             "power", "set", "recovery"],
            cwd=str(self.outside), env=env, capture_output=True, text=True,
            timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        state = (self.workspace / ".agentic-os" / "power.json").read_bytes()
        self.assertEqual(state, EXPECTED_BYTES["recovery"])


# ---------------------------------------------------------------------------
# (25) Exclusions preserved

class ExclusionTests(PowerCase):
    def test_power_never_touches_the_schema(self):
        """(25) No schema drift, no new table, no meta row."""
        for mode in power.MODES:
            self.set_mode_direct(mode)
            self.aos("doctor")
        self.assert_no_schema_drift()

        conn = sqlite3.connect(self.db_path)
        try:
            metas = {
                r[0] for r in conn.execute("SELECT key FROM meta").fetchall()
            }
            tables = {
                r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            conn.close()
        for key in metas:
            self.assertNotIn("power", key.lower())
        for table in tables:
            self.assertNotIn("power", table.lower())

    def test_schema_version_is_whatever_the_one_declaration_says(self):
        """(25) U-E2 changed no schema, and must not. U-M2 owns the version:
        this pins that power modes follow it rather than declaring their own.
        """
        self.assertEqual(db.SCHEMA_VERSION, "4")
        self.assertEqual(migrations.LATEST_VERSION, int(db.SCHEMA_VERSION))

    def test_power_state_lives_beside_the_ledger_not_inside_it(self):
        self.set_mode_direct("deep")
        self.assertEqual(
            power.state_path(self.aos_dir), self.aos_dir / "power.json"
        )
        self.assertTrue((self.aos_dir / "power.json").is_file())

    def test_power_set_emits_no_ledger_event(self):
        """(25)(D-1) Deliberate: `power set` must work when the database
        cannot be opened, which is exactly when recovery is set."""
        before = self.count("events")
        for mode in ("eco", "deep", "recovery"):
            self.run_cli("--root", str(self.root), "power", "set", mode)
        self.assertEqual(self.count("events"), before)

    def test_no_lock_file_or_daemon_is_introduced(self):
        """(25) os.replace is the serialization point (contract 2.4)."""
        self.aos("power", "set", "eco")
        leftovers = sorted(
            p.name for p in self.aos_dir.iterdir()
            if "lock" in p.name.lower()
        )
        self.assertEqual(leftovers, [])

    def test_power_commands_never_call_open_db(self):
        """(25) The schema-version gate must never reach recovery control."""
        with mock.patch.object(
            db, "open_db", side_effect=AssertionError("open_db was called")
        ):
            self.aos("power", "status")
            self.aos("power", "set", "recovery")


if __name__ == "__main__":
    unittest.main()
