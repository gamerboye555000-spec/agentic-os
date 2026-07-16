"""U-C3 secret warn-on-write + doctor sweep tests (D-v0.2.15, D-v0.2.21).

Three postures, one shared detector:
- pack/context egress: hard refusal (unchanged from baseline);
- untrusted dropfile ingest: atomic hard refusal (unchanged);
- trusted human CLI writes: accepted into the domain row, warned on
  stderr, safe metadata in the mutation event — whose payload never
  carries a matched value (redacted leaves) — findable later by doctor.
  The whole event record is covered: a credential-shaped but valid
  evidence provenance is redacted from events.actor too, and doctor also
  sweeps evidence.provenance, legacy raw event actors, and the
  tasks.assignee / tasks.branch_hint columns.

Every credential-shaped string below is a synthetic test fixture reserved
for these tests. No real credential appears anywhere, and no assertion
message can echo one: warnings, payload metadata, and doctor output are
proven to carry field/pattern NAMES only, and the failure diagnostics in
this module never interpolate a fixture or full captured output.
"""

from __future__ import annotations

import contextlib
import io
import json
import sqlite3
import unittest
from pathlib import Path
from unittest import mock

from weekend_harness import Night1BackCompatCase, WeekendOpsTestCase

from agentic_os import db, events, ingest, ops, pack, render, secretscan, utils

#: Synthetic, realistic-shaped fake credentials (tests only — never real).
FAKE_VALUE = "u3c3fakesecret42"
FAKE_ASSIGNMENT = f'password = "{FAKE_VALUE}"'
FAKE_SK = "sk-u3c3fakeA1b2C3d4E5f6"
FAKE_AWS = "AKIAFAKEU3C3FAKEU3C3"
FAKE_GHP = "ghp_" + "u3c3FAKE" * 4
#: A token-shaped string that also passes validate_slug (lowercase).
FAKE_SLUG = "sk-u3c3fakeslug00000"
#: A syntactically VALID evidence provenance (agent:<name> charset) whose
#: agent-name portion is credential-shaped — the U-C3 bypass regression.
FAKE_PROVENANCE = f"agent:{FAKE_GHP}"

#: Needles for no-echo checks. FAKE_VALUE is deliberately NOT
#: detector-positive on its own (a bare value has no credential shape) —
#: it is the strongest needle precisely because only the assignment form
#: around it is matched.
ALL_FAKES = (FAKE_VALUE, FAKE_SK, FAKE_AWS, FAKE_GHP, FAKE_SLUG)

#: The fixtures scan_secrets actually matches (redaction expectations).
DETECTABLE_FAKES = (FAKE_ASSIGNMENT, FAKE_SK, FAKE_AWS, FAKE_GHP, FAKE_SLUG)

REDACTED = secretscan.REDACTED_VALUE

REPO_ROOT = Path(__file__).resolve().parents[1]


class NoEchoAssertions:
    """Assertion helpers whose FAILURE diagnostics stay privacy-safe: no
    fake credential and no full captured output is ever interpolated into
    an assertion message (the U-C3 posture applies to test diagnostics
    too). Mixed into TestCase classes."""

    def assert_no_fakes(self, text: str, where: str) -> None:
        for index, fake in enumerate(ALL_FAKES):
            self.assertFalse(
                fake in text,
                f"fake credential #{index} echoed in {where}",
            )

    def assert_contains(self, text: str, needle: str, where: str) -> None:
        self.assertTrue(
            needle in text,
            f"expected {needle!r} in {where} (content withheld)",
        )

    def assert_equal_withheld(self, actual, expected, where: str) -> None:
        """Equality without unittest's diff — for values that may carry a
        fixture on the failing side."""
        self.assertTrue(actual == expected, f"{where} mismatch (values withheld)")

    def assert_redacted(self, payload: dict, key: str) -> None:
        self.assert_equal_withheld(
            payload.get(key), REDACTED, f"payload[{key!r}]"
        )


# ---------------------------------------------------------------------------
# U-C3.1 — one shared, side-effect-free detector


class TestSharedDetector(NoEchoAssertions, unittest.TestCase):
    def test_pack_reexports_the_shared_detector(self):
        self.assertIs(pack.scan_secrets, secretscan.scan_secrets)
        self.assertIs(pack.SECRET_PATTERNS, secretscan.SECRET_PATTERNS)

    def test_ingest_uses_the_shared_module(self):
        self.assertIs(ingest.secretscan, secretscan)

    def test_baseline_patterns_preserved_by_name(self):
        cases = {
            "pem-private-key": "-----BEGIN RSA PRIVATE KEY-----\nabc",
            "aws-access-key-id": f"creds {FAKE_AWS} here",
            "github-token": f"use {FAKE_GHP}",
            "sk-api-key": FAKE_SK,
            "credential-assignment": FAKE_ASSIGNMENT,
        }
        for expected, text in cases.items():
            with self.subTest(expected=expected):
                self.assertIn(expected, secretscan.scan_secrets(text))
        entropy_run = "kJ8vQ2xNp7RmT4wZbC9dF6hLs3aYeGuVjD5nXqAiK1oB"
        self.assertIn(
            "high-entropy-near-keyword",
            secretscan.scan_secrets(f"deploy key: {entropy_run}"),
        )

    def test_benign_fixtures_stay_negative(self):
        benign = [
            "the token was refreshed and the password rotated",
            "password = short",
            "A" * 60 + " key material discussion",  # zero entropy
            "blob: kJ8vQ2xNp7RmT4wZbC9dF6hLs3aYeGuVjD5nXqAiK1oB",  # no keyword
            "Build auth flow with acceptance criteria",
            # A bare content hash (as stored in evidence/backup payloads)
            # has no keyword in scope and must not trip the sweep.
            "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
            "2026-07-12T00:00:00Z",
        ]
        for text in benign:
            with self.subTest(text=text[:30]):
                self.assertEqual(secretscan.scan_secrets(text), [])

    def test_scan_fields_keeps_labels_and_input_order(self):
        findings = secretscan.scan_fields(
            [
                ("title", FAKE_ASSIGNMENT),
                ("spec", None),
                ("acceptance", "benign text"),
                ("notes", FAKE_SK),
            ]
        )
        self.assertEqual([label for label, _ in findings], ["title", "notes"])
        self.assertEqual(findings[0][1], ["credential-assignment"])
        self.assertEqual(findings[1][1], ["sk-api-key"])

    def test_deterministic_and_deduplicated_pattern_names(self):
        text = f"{FAKE_SK} then {FAKE_SK} and {FAKE_ASSIGNMENT}"
        first = secretscan.scan_secrets(text)
        self.assertEqual(first, secretscan.scan_secrets(text))
        self.assertEqual(len(first), len(set(first)))
        self.assertEqual(
            first, [n for n in secretscan.PATTERN_NAMES if n in first]
        )

    def test_merge_pattern_names_uses_detector_order(self):
        findings = [
            ("b", ["credential-assignment"]),
            ("a", ["sk-api-key", "credential-assignment"]),
        ]
        self.assertEqual(
            secretscan.merge_pattern_names(findings),
            ["sk-api-key", "credential-assignment"],
        )
        self.assertEqual(secretscan.merge_pattern_names([]), [])

    def test_results_never_carry_the_matched_text(self):
        findings = secretscan.scan_fields([("title", FAKE_ASSIGNMENT)])
        self.assert_no_fakes(repr(findings), "scan_fields result")

    def test_redact_tree_replaces_only_matched_leaves(self):
        original = {
            "title": FAKE_ASSIGNMENT,
            "project": "demo",
            "priority": 2,
            "capabilities": ["benign cap", FAKE_SK, None],
            "nested": {"agent": FAKE_GHP, "kind": "cli", "flag": True},
        }
        redacted = secretscan.redact_tree(original)
        self.assert_no_fakes(json.dumps(redacted), "redacted tree")
        self.assert_equal_withheld(
            redacted,
            {
                "title": REDACTED,
                "project": "demo",
                "priority": 2,
                "capabilities": ["benign cap", REDACTED, None],
                "nested": {"agent": REDACTED, "kind": "cli", "flag": True},
            },
            "redacted tree",
        )
        # The input is untouched (the caller may still need the values).
        self.assert_equal_withheld(
            original["title"], FAKE_ASSIGNMENT, "original title"
        )
        self.assert_equal_withheld(
            original["capabilities"][1], FAKE_SK, "original capability"
        )

    def test_redact_tree_is_the_identity_on_benign_payloads(self):
        payload = {
            "title": "rotate the logs weekly",
            "priority": 2,
            "tags": ["ops", "weekly"],
            "note": None,
        }
        self.assertEqual(secretscan.redact_tree(payload), payload)

    def test_redacted_placeholder_is_itself_benign(self):
        # The placeholder must never re-trip the detector (doctor rescans
        # payload strings) and must carry nothing derived from the value.
        self.assertEqual(secretscan.scan_secrets(REDACTED), [])
        for index, fake in enumerate(DETECTABLE_FAKES):
            self.assert_equal_withheld(
                secretscan.redact_tree({"leaf": fake}),
                {"leaf": REDACTED},
                f"redacted leaf for detectable fixture #{index}",
            )

    def test_trusted_write_labels_must_come_from_the_allowlist(self):
        # Doctor only reports allowlisted field names, so ops refuses to
        # scan under an unregistered label (metadata doctor would drop).
        with self.assertRaises(ValueError) as ctx:
            ops._scan_trusted_write("task", [("mystery_label", "text")])
        self.assertIn("mystery_label", str(ctx.exception))


# ---------------------------------------------------------------------------
# U-C3.3 / U-C3.4 — trusted human writes warn, succeed, and journal safely


class WarnCase(NoEchoAssertions, Night1BackCompatCase):
    """Night-1 workspace + helpers to run a command and inspect the
    warning and the newest event payload. Failure diagnostics name only
    the command word and exit code — never argv or captured output, which
    carry the fake credentials."""

    def aos_warned(self, *argv: str) -> tuple[str, str]:
        code, out, err = self.run_cli("--root", str(self.root), *argv)
        self.assertEqual(
            code,
            0,
            f"aos {argv[0]} exited {code} (argv and output withheld)",
        )
        return out, err

    def aos_fails(self, *argv: str) -> tuple[int, str, str]:
        # Shadows the harness helper, whose diagnostic interpolates the
        # captured output — off-limits when the fixture is a fake secret.
        code, out, err = self.run_cli("--root", str(self.root), *argv)
        self.assertEqual(
            code,
            1,
            f"aos {argv[0]} exited {code}, expected 1 "
            "(argv and output withheld)",
        )
        return code, out, err

    def event_rows(self) -> list[sqlite3.Row]:
        conn = db.open_db(self.aos_dir)
        try:
            return conn.execute("SELECT * FROM events ORDER BY id").fetchall()
        finally:
            conn.close()

    def latest_payload(self, entity: str, action: str) -> dict:
        rows = [
            r
            for r in self.event_rows()
            if r["entity"] == entity and r["action"] == action
        ]
        self.assertTrue(rows, f"no {entity}/{action} event")
        return json.loads(rows[-1]["payload_json"])

    def assert_warning(
        self, err: str, entity: str, fields: list[str], patterns: list[str]
    ) -> None:
        where = "stderr warning"
        self.assert_contains(err, "WARNING: secret-shaped text", where)
        self.assert_contains(
            err, f"in {entity} field(s) {', '.join(fields)}", where
        )
        for pattern in patterns:
            self.assert_contains(err, pattern, where)
        self.assert_contains(err, "rotate", where)
        self.assert_no_fakes(err, where)

    def assert_metadata(
        self, payload: dict, fields: list[str], patterns: list[str]
    ) -> None:
        """Safe metadata present AND the complete serialized payload —
        every nested key and leaf — free of the fake credentials."""
        self.assert_no_fakes(json.dumps(payload), "event payload")
        self.assertIs(payload["secret_warning"], True)
        self.assertEqual(payload["secret_fields"], fields)
        self.assertEqual(payload["secret_patterns"], patterns)


class TestTrustedWritesWarnAndSucceed(WarnCase):
    def test_project_name_warns(self):
        out, err = self.aos_warned(
            "project", "add", "leaky", "--name", f"Name {FAKE_ASSIGNMENT}",
            "--repo", str(self.repo),
        )
        self.assertIn("Added project leaky", out)
        self.assert_warning(err, "project", ["name"], ["credential-assignment"])
        payload = self.latest_payload("project", "add")
        self.assert_metadata(payload, ["name"], ["credential-assignment"])
        # The matched leaf is the placeholder; the safe siblings survive.
        self.assert_redacted(payload, "name")
        self.assertEqual(payload["slug"], "leaky")
        self.assertEqual(payload["repo_path"], str(self.repo))

    def test_token_shaped_project_slug_warns_and_never_reaches_the_event(self):
        out, err = self.aos_warned(
            "project", "add", FAKE_SLUG, "--name", "Leaky by slug",
            "--repo", str(self.repo),
        )
        self.assert_warning(err, "project", ["slug"], ["sk-api-key"])
        payload = self.latest_payload("project", "add")
        self.assert_metadata(payload, ["slug"], ["sk-api-key"])
        self.assert_redacted(payload, "slug")
        self.assertEqual(payload["name"], "Leaky by slug")
        # The canonical domain row keeps the accepted slug verbatim.
        conn = db.open_db(self.aos_dir)
        try:
            slugs = [
                r["slug"]
                for r in conn.execute("SELECT slug FROM projects").fetchall()
            ]
        finally:
            conn.close()
        self.assertTrue(
            FAKE_SLUG in slugs,
            "accepted slug missing from domain rows (values withheld)",
        )

    def test_secret_shaped_repo_path_warns_and_never_reaches_the_event(self):
        secret_repo = self.root / f"repo-{FAKE_SK}"
        secret_repo.mkdir()
        out, err = self.aos_warned(
            "project", "add", "leakypath", "--name", "Leaky by path",
            "--repo", str(secret_repo),
        )
        self.assertIn("Added project leakypath", out)
        self.assert_warning(err, "project", ["repo_path"], ["sk-api-key"])
        payload = self.latest_payload("project", "add")
        self.assert_metadata(payload, ["repo_path"], ["sk-api-key"])
        self.assert_redacted(payload, "repo_path")
        self.assertEqual(payload["slug"], "leakypath")

    def test_task_add_title_and_spec_warn_with_stable_dedup(self):
        events_before = len(self.event_rows())
        out, err = self.aos_warned(
            "task", "add", f"Title {FAKE_ASSIGNMENT}", "-p", "demo",
            "--spec", f"spec {FAKE_SK}",
        )
        # stdout contract intact: exactly the new task id.
        self.assertEqual(out, "T-0004\n")
        # Exactly one mutation event was appended — atomic, no second event.
        self.assertEqual(len(self.event_rows()), events_before + 1)
        self.assert_warning(
            err, "task", ["title", "spec"],
            ["sk-api-key", "credential-assignment"],
        )
        payload = self.latest_payload("task", "add")
        self.assert_metadata(
            payload, ["title", "spec"], ["sk-api-key", "credential-assignment"]
        )
        # Matched leaf redacted; the safe payload values are preserved.
        self.assert_redacted(payload, "title")
        self.assertEqual(payload["project"], "demo")
        self.assertEqual(payload["status"], "ready")
        # The domain write itself is untouched: the value landed verbatim.
        conn = db.open_db(self.aos_dir)
        try:
            row = conn.execute(
                "SELECT title, spec_md FROM tasks WHERE id = 4"
            ).fetchone()
        finally:
            conn.close()
        self.assert_equal_withheld(
            row["title"], f"Title {FAKE_ASSIGNMENT}", "domain title"
        )
        self.assert_equal_withheld(
            row["spec_md"], f"spec {FAKE_SK}", "domain spec"
        )

    def test_task_edit_acceptance_warns_and_payload_has_no_value(self):
        out, err = self.aos_warned(
            "task", "edit", "T-0002", "--accept", FAKE_ASSIGNMENT
        )
        self.assertIn("T-0002 edited: accept", out)
        self.assert_warning(err, "task", ["acceptance"], ["credential-assignment"])
        payload = self.latest_payload("task", "edit")
        # The edit event journals names only — with the metadata added, the
        # whole payload still carries no trace of the value.
        self.assert_metadata(
            payload, ["acceptance"], ["credential-assignment"]
        )
        self.assertEqual(payload["changed"], ["accept"])

    def test_inbox_capture_warns(self):
        out, err = self.aos_warned("in", f"thought {FAKE_ASSIGNMENT}")
        self.assertEqual(out, "T-0004\n")
        self.assert_warning(err, "task", ["title"], ["credential-assignment"])
        payload = self.latest_payload("task", "add")
        self.assert_metadata(payload, ["title"], ["credential-assignment"])
        self.assert_redacted(payload, "title")
        self.assertEqual(payload["via"], "in")

    def test_run_start_agent_and_run_end_summary_warn(self):
        out, err = self.aos_warned(
            "run", "start", "T-0002", "--agent", FAKE_SK
        )
        self.assertEqual(out, "R-0002\n")
        self.assert_warning(err, "run", ["agent"], ["sk-api-key"])
        payload = self.latest_payload("run", "start")
        self.assert_metadata(payload, ["agent"], ["sk-api-key"])
        self.assert_redacted(payload, "agent")
        self.assertEqual(payload["task"], "T-0002")
        out, err = self.aos_warned(
            "run", "end", "R-0002", "--outcome", "partial",
            "--summary", f"found {FAKE_ASSIGNMENT}",
        )
        self.assertIn("R-0002 ended: partial", out)
        self.assert_warning(err, "run", ["summary"], ["credential-assignment"])
        payload = self.latest_payload("run", "end")
        # run end journals task/outcome only — no value in the payload.
        self.assert_metadata(
            payload, ["summary"], ["credential-assignment"]
        )
        self.assertEqual(payload["outcome"], "partial")

    def test_decision_fields_warn(self):
        out, err = self.aos_warned(
            "decision", "add", f"Rotate {FAKE_AWS} now", "-p", "demo",
            "--decision", f"decided {FAKE_ASSIGNMENT}",
            "--alternatives", f"alt {FAKE_SK}",
        )
        self.assertEqual(out, "D-0001\n")
        self.assert_warning(
            err, "decision", ["title", "decision", "alternatives"],
            ["aws-access-key-id", "sk-api-key", "credential-assignment"],
        )
        payload = self.latest_payload("decision", "add")
        self.assert_metadata(
            payload,
            ["title", "decision", "alternatives"],
            ["aws-access-key-id", "sk-api-key", "credential-assignment"],
        )
        self.assert_redacted(payload, "title")
        self.assertEqual(payload["project"], "demo")

    def test_evidence_ref_and_claim_warn(self):
        out, err = self.aos_warned(
            "evidence", "add", "T-0002", "--kind", "note",
            "--ref", f"ref {FAKE_AWS}", "--claim", f"claim {FAKE_ASSIGNMENT}",
        )
        self.assertEqual(out, "E-0002\n")
        self.assert_warning(
            err, "evidence", ["ref", "claim"],
            ["aws-access-key-id", "credential-assignment"],
        )
        payload = self.latest_payload("evidence", "add")
        self.assert_metadata(
            payload,
            ["ref", "claim"], ["aws-access-key-id", "credential-assignment"],
        )
        self.assert_redacted(payload, "ref")
        self.assert_redacted(payload, "claim")
        self.assertEqual(payload["task"], "T-0002")

    def test_secret_shaped_evidence_provenance_warns_and_redacts_actor(self):
        # PROVENANCE_RE accepts agent:<name> with a token-shaped name, and
        # add_evidence passes provenance straight through as events.actor —
        # the write must succeed, keep the canonical row honest, warn once,
        # and leave NO trace of the value in the event record (payload OR
        # actor, which gets the same fixed placeholder).
        events_before = len(self.event_rows())
        out, err = self.aos_warned(
            "evidence", "add", "T-0002", "--kind", "note",
            "--ref", "benign ref", "--claim", "benign claim",
            "--provenance", FAKE_PROVENANCE,
        )
        self.assertEqual(out, "E-0002\n")
        # One normal mutation event, no second event.
        self.assertEqual(len(self.event_rows()), events_before + 1)
        self.assert_warning(err, "evidence", ["provenance"], ["github-token"])
        payload = self.latest_payload("evidence", "add")
        self.assert_metadata(payload, ["provenance"], ["github-token"])
        # Benign payload siblings survive verbatim.
        self.assertEqual(payload["ref"], "benign ref")
        self.assertEqual(payload["claim"], "benign claim")
        self.assertEqual(payload["task"], "T-0002")
        # The event actor is the fixed placeholder; no actor column in the
        # whole journal carries a fixture.
        rows = self.event_rows()
        self.assert_equal_withheld(rows[-1]["actor"], REDACTED, "event actor")
        self.assert_no_fakes(
            "\n".join(row["actor"] for row in rows), "events.actor column"
        )
        # The canonical evidence row keeps the trusted value byte-for-byte.
        conn = db.open_db(self.aos_dir)
        try:
            row = conn.execute(
                "SELECT provenance FROM evidence WHERE id = 2"
            ).fetchone()
        finally:
            conn.close()
        self.assert_equal_withheld(
            row["provenance"], FAKE_PROVENANCE, "evidence provenance row"
        )

    def test_benign_evidence_provenance_stays_verbatim_in_events_actor(self):
        out, err = self.aos_warned(
            "evidence", "add", "T-0002", "--kind", "note",
            "--ref", "benign ref", "--claim", "benign claim",
            "--provenance", "agent:codex",
        )
        self.assertEqual(out, "E-0002\n")
        self.assertEqual(err, "")
        payload = self.latest_payload("evidence", "add")
        self.assertNotIn("secret_warning", payload)
        self.assertNotIn("secret_fields", payload)
        self.assertNotIn("secret_patterns", payload)
        rows = self.event_rows()
        # Byte-for-byte: the supplied provenance and every pre-existing
        # human actor are stored exactly as written.
        self.assertEqual(rows[-1]["actor"], "agent:codex")
        self.assertEqual(
            {row["actor"] for row in rows[:-1]}, {"human"}
        )

    def test_export_and_log_json_omit_warned_provenance_everywhere(self):
        self.aos_warned(
            "evidence", "add", "T-0002", "--kind", "note",
            "--ref", "benign ref", "--claim", "benign claim",
            "--provenance", FAKE_PROVENANCE,
        )
        code, out, err = self.run_cli("--root", str(self.root), "log", "--json")
        self.assertEqual(code, 0)
        self.assert_no_fakes(out, "log --json stdout")
        doc = json.loads(out)
        entry = [
            e for e in doc["events"]
            if e["entity"] == "evidence" and e["action"] == "add"
        ][-1]
        self.assert_equal_withheld(entry["actor"], REDACTED, "log actor")
        export_path = self.root / "events-export.jsonl"
        code, out, err = self.run_cli(
            "--root", str(self.root), "export", "events", "--jsonl",
            "--output", str(export_path),
        )
        self.assertEqual(code, 0)
        exported = export_path.read_text(encoding="utf-8")
        self.assert_no_fakes(exported, "export events JSONL")
        last = json.loads(exported.strip().splitlines()[-1])
        self.assert_equal_withheld(last["actor"], REDACTED, "exported actor")
        exported_payload = json.loads(last["payload_json"])
        self.assert_metadata(
            exported_payload, ["provenance"], ["github-token"]
        )

    def test_handoff_agents_and_state_warn(self):
        out, err = self.aos_warned(
            "handoff", "create", "T-0002", "--from", FAKE_GHP,
            "--to", "codex", "--state", f"state {FAKE_ASSIGNMENT}",
        )
        self.assertEqual(out, "H-0001\n")
        self.assert_warning(
            err, "handoff", ["from_agent", "state"],
            ["github-token", "credential-assignment"],
        )
        payload = self.latest_payload("handoff", "create")
        self.assert_metadata(
            payload,
            ["from_agent", "state"], ["github-token", "credential-assignment"],
        )
        self.assert_redacted(payload, "from_agent")
        self.assertEqual(payload["to_agent"], "codex")

    def test_memory_key_and_value_warn(self):
        out, err = self.aos_warned(
            "memory", "add", "--scope", "global", "--kind", "fact",
            "--key", f"deploy {FAKE_AWS}", "--value", f"value {FAKE_ASSIGNMENT}",
            "--source", "human", "--confidence", "confirmed",
        )
        self.assertEqual(out, "M-0001\n")
        self.assert_warning(
            err, "memory", ["key", "value"],
            ["aws-access-key-id", "credential-assignment"],
        )
        payload = self.latest_payload("memory", "add")
        self.assert_metadata(
            payload,
            ["key", "value"], ["aws-access-key-id", "credential-assignment"],
        )
        self.assert_redacted(payload, "key")
        self.assertEqual(payload["scope"], "global")
        self.assertEqual(payload["confidence"], "confirmed")

    def test_agent_registry_fields_warn(self):
        out, err = self.aos_warned(
            "agent", "add", "codex", "--notes", f"notes {FAKE_ASSIGNMENT}",
            "--capability", f"cap {FAKE_SK}", "--capability", "review docs",
        )
        self.assertIn("Added agent codex", out)
        self.assert_warning(
            err, "agent", ["notes", "capabilities"],
            ["sk-api-key", "credential-assignment"],
        )
        payload = self.latest_payload("agent", "add")
        self.assert_metadata(
            payload,
            ["notes", "capabilities"], ["sk-api-key", "credential-assignment"],
        )
        # Nested list redaction: the matched element is replaced in place,
        # its benign sibling survives.
        self.assert_equal_withheld(
            payload["capabilities"], [REDACTED, "review docs"], "capabilities"
        )
        out, err = self.aos_warned(
            "agent", "update", "codex", "--notes", f"new {FAKE_ASSIGNMENT}"
        )
        self.assert_warning(err, "agent", ["notes"], ["credential-assignment"])
        payload = self.latest_payload("agent", "update")
        self.assert_metadata(payload, ["notes"], ["credential-assignment"])
        self.assertEqual(payload["agent"], "codex")

    def test_token_shaped_agent_name_warns(self):
        out, err = self.aos_warned("agent", "add", FAKE_GHP)
        self.assert_warning(err, "agent", ["name"], ["github-token"])
        payload = self.latest_payload("agent", "add")
        self.assert_metadata(payload, ["name"], ["github-token"])
        self.assert_redacted(payload, "agent")

    def test_agent_update_never_copies_a_secret_shaped_name_forward(self):
        # A secret-shaped identifier accepted by an earlier warned write
        # must not resurface in a later event payload (D-v0.2.21).
        self.aos_warned("agent", "add", FAKE_GHP)
        out, err = self.aos_warned(
            "agent", "update", FAKE_GHP, "--notes", "perfectly benign note"
        )
        self.assert_warning(err, "agent", ["name"], ["github-token"])
        payload = self.latest_payload("agent", "update")
        self.assert_metadata(payload, ["name"], ["github-token"])
        self.assert_redacted(payload, "agent")
        self.assertEqual(payload["changed"], ["notes"])

    def test_done_override_reason_warns_and_marks_the_override_event(self):
        events_before = len(self.event_rows())
        out, err = self.aos_warned(
            "done", "T-0002", "--no-evidence",
            "--reason", f"contains {FAKE_ASSIGNMENT}",
        )
        self.assertIn("T-0002 done", out)
        # Pre-existing override design: done + done_override, nothing more.
        self.assertEqual(len(self.event_rows()), events_before + 2)
        self.assert_warning(err, "task", ["reason"], ["credential-assignment"])
        payload = self.latest_payload("task", "done_override")
        self.assert_metadata(payload, ["reason"], ["credential-assignment"])
        self.assert_redacted(payload, "reason")
        self.assertEqual(payload["via"], "--no-evidence")
        # The plain done event stays exactly as before — no metadata.
        self.assertNotIn(
            "secret_warning", self.latest_payload("task", "done")
        )

    def test_benign_writes_stay_silent_and_keep_baseline_payloads(self):
        out, err = self.aos_warned(
            "task", "add", "Perfectly ordinary title", "-p", "demo",
            "--spec", "rotate the logs weekly",
        )
        self.assertEqual(out, "T-0004\n")
        self.assertEqual(err, "")
        # Unaffected payloads keep their exact baseline keys AND values —
        # no metadata, no placeholder, nothing reshaped.
        self.assertEqual(
            self.latest_payload("task", "add"),
            {
                "schema_version": 1,
                "title": "Perfectly ordinary title",
                "project": "demo",
                "kind": "code",
                "status": "ready",
                "priority": 2,
            },
        )
        out, err = self.aos_warned("task", "status", "T-0004", "in_progress")
        self.assertEqual(err, "")
        self.assertEqual(
            self.latest_payload("task", "status"),
            {
                "schema_version": 1,
                "task": "T-0004",
                "from": "ready",
                "to": "in_progress",
            },
        )

    def test_json_stdout_stays_parseable_after_warned_writes(self):
        self.aos_warned(
            "task", "add", f"Title {FAKE_ASSIGNMENT}", "-p", "demo"
        )
        code, out, err = self.run_cli(
            "--root", str(self.root), "task", "list", "--json"
        )
        self.assertEqual(code, 0)
        doc = json.loads(out)  # stdout is exactly one JSON document
        titles = [t["title"] for t in doc["tasks"]]
        # The user-requested readback reflects the canonical row (policy:
        # rows keep accepted values; only warnings/events/doctor redact).
        self.assertTrue(
            f"Title {FAKE_ASSIGNMENT}" in titles,
            "warned title missing from task list --json (content withheld)",
        )
        code, out, err = self.run_cli(
            "--root", str(self.root), "log", "--json"
        )
        self.assertEqual(code, 0)
        # The event payloads inside the log readback are the redacted ones.
        self.assert_no_fakes(out, "log --json stdout")
        json.loads(out)

    def test_rejected_command_writes_nothing_and_never_warns(self):
        # Malformed command (empty title after strip) with a secret in a
        # field: refused, no event, no misleading warning.
        events_before = len(self.event_rows())
        code, out, err = self.run_cli(
            "--root", str(self.root),
            "task", "add", "   ", "-p", "demo", "--spec", FAKE_ASSIGNMENT,
        )
        self.assertEqual(code, 1)
        self.assertFalse(
            "WARNING" in err, "rejected write warned (stderr withheld)"
        )
        self.assertEqual(len(self.event_rows()), events_before)

    def test_failure_diagnostics_withhold_fixtures_and_output(self):
        # The no-echo posture extends to this module's own assertion
        # failures: probe each helper's failure path and prove the raised
        # message interpolates neither a fake credential nor captured
        # output (which would carry one).
        probe = f"probe {FAKE_ASSIGNMENT} {FAKE_SK} {FAKE_AWS} {FAKE_GHP}"
        with self.assertRaises(AssertionError) as ctx:
            self.assert_no_fakes(probe, "probe text")
        self.assert_no_fakes(str(ctx.exception), "assert_no_fakes diagnostic")
        with self.assertRaises(AssertionError) as ctx:
            self.assert_contains(probe, "needle that is absent", "probe text")
        self.assert_no_fakes(str(ctx.exception), "assert_contains diagnostic")
        with self.assertRaises(AssertionError) as ctx:
            self.aos_warned(
                "task", "add", "   ", "-p", "demo", "--spec", FAKE_ASSIGNMENT
            )
        self.assert_no_fakes(str(ctx.exception), "aos_warned diagnostic")
        with self.assertRaises(AssertionError) as ctx:
            self.aos_fails("task", "list")  # exits 0, helper expects 1
        self.assert_no_fakes(str(ctx.exception), "aos_fails diagnostic")
        self.assertNotIn("task list", str(ctx.exception))  # no output echo


class TestWarnedWriteAtomicity(WeekendOpsTestCase):
    """A warned write is still one transaction: forced event failure rolls
    back the row AND suppresses the warning (a warning must never describe
    a write that did not happen)."""

    def test_failed_emit_rolls_back_and_stays_silent(self):
        ops.add_project(
            self.conn, slug="demo", name="Demo", repo=str(self.repo)
        )
        tasks_before = self.row_count("tasks")
        events_before = self.event_count()
        stderr = io.StringIO()
        with mock.patch.object(
            events, "emit", side_effect=RuntimeError("forced failure")
        ):
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(RuntimeError):
                    ops.add_task(
                        self.conn,
                        title=f"Doomed {FAKE_ASSIGNMENT}",
                        project_slug="demo",
                    )
        self.assertEqual(self.row_count("tasks"), tasks_before)
        self.assertEqual(self.event_count(), events_before)
        self.assertEqual(stderr.getvalue(), "")


# ---------------------------------------------------------------------------
# U-C3.2 — the hard egress refusals stay atomic and silent about the value


class TestEgressRefusalsPreserved(WarnCase):
    def test_pack_refusal_leaves_no_row_no_file_no_echo(self):
        self.aos_warned("task", "edit", "T-0002", "--accept", FAKE_ASSIGNMENT)
        conn = db.open_db(self.aos_dir)
        try:
            packs_before = conn.execute(
                "SELECT COUNT(*) AS n FROM packs"
            ).fetchone()["n"]
        finally:
            conn.close()
        code, out, err = self.aos_fails("pack", "build", "T-0002")
        self.assert_contains(err, "Refusing to build pack", "pack refusal")
        self.assert_contains(err, "credential-assignment", "pack refusal")
        self.assert_contains(err, "ACCEPTANCE", "pack refusal")
        self.assert_no_fakes(out + err, "pack refusal output")
        conn = db.open_db(self.aos_dir)
        try:
            packs_after = conn.execute(
                "SELECT COUNT(*) AS n FROM packs"
            ).fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(packs_after, packs_before)
        self.assertFalse(
            (self.aos_dir / "packs" / "T-0002-claude-code.md").exists()
        )

    def test_dropfile_refusal_writes_no_rows_marker_or_event(self):
        dropfile = self.root / "drop.md"
        dropfile.write_text(
            "# AOS DROPFILE\n"
            "task: T-0002\n"
            "agent: claude-code\n"
            "outcome: partial\n"
            f"summary: leaked {FAKE_ASSIGNMENT}\n"
            "\n"
            "## evidence\n"
            "- kind: note | ref: some ref | claim: some claim\n"
            "\n"
            "## open questions\n"
            "- next step?\n",
            encoding="utf-8",
        )
        conn = db.open_db(self.aos_dir)
        try:
            counts_before = {
                table: conn.execute(
                    f"SELECT COUNT(*) AS n FROM {table}"
                ).fetchone()["n"]
                for table in ("evidence", "handoffs", "runs", "events")
            }
        finally:
            conn.close()
        code, out, err = self.aos_fails("ingest", "dropfile", str(dropfile))
        self.assert_contains(err, "Refusing to ingest dropfile", "ingest refusal")
        self.assert_contains(err, "credential-assignment", "ingest refusal")
        self.assert_no_fakes(out + err, "ingest refusal output")
        conn = db.open_db(self.aos_dir)
        try:
            for table, before in counts_before.items():
                self.assertEqual(
                    conn.execute(
                        f"SELECT COUNT(*) AS n FROM {table}"
                    ).fetchone()["n"],
                    before,
                    table,
                )
            # No dedupe marker: no dropfile_ingest event exists at all.
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM events "
                    "WHERE action = 'dropfile_ingest'"
                ).fetchone()["n"],
                0,
            )
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# U-C3.5 — doctor sweep


class TestDoctorSecretSweep(WarnCase):
    CHECK = "secret-shaped text in ledger rows or event payloads"

    def doctor(self) -> tuple[int, str, str]:
        return self.run_cli("--root", str(self.root), "doctor")

    def doctor_ok(self) -> str:
        code, out, err = self.doctor()
        self.assertEqual(code, 0, f"doctor exited {code} (output withheld)")
        self.assert_no_fakes(out + err, "doctor output")
        return out

    def sweep_line(self, out: str) -> str:
        lines = [l for l in out.splitlines() if self.CHECK in l]
        self.assertEqual(
            len(lines), 1, "expected exactly one sweep line (output withheld)"
        )
        return lines[0]

    def insert_event(self, payload: dict, actor: str = "human") -> int:
        """Write an event row via raw SQL — bypassing events.emit and its
        redaction — to simulate a legacy pre-U-C3 payload/actor or a
        tampered row. Doctor must stay safe on what emit would never
        write."""
        conn = db.open_db(self.aos_dir)
        try:
            with db.transaction(conn):
                cursor = conn.execute(
                    "INSERT INTO events (ts, actor, entity, entity_id, "
                    "action, payload_json) VALUES (?, ?, 'task', 2, "
                    "'tamper_test', ?)",
                    (utils.utc_now_iso(), actor, json.dumps(payload)),
                )
                return cursor.lastrowid
        finally:
            conn.close()

    def seed_sql(self, statement: str, params: tuple) -> None:
        """Direct SQL seeding for canonical columns that have no CLI write
        path yet (tasks.assignee / tasks.branch_hint) or need isolating
        after a warned write (evidence.provenance)."""
        conn = db.open_db(self.aos_dir)
        try:
            with db.transaction(conn):
                conn.execute(statement, params)
        finally:
            conn.close()

    def test_clean_workspace_sweep_passes(self):
        out = self.doctor_ok()
        self.assertTrue(self.sweep_line(out).startswith("[PASS]"))
        # 18 → 20 → 21 → 25 → 30 → 31: the two U-H2 warn-only checks, the
        # U-E2 runtime power state check, U-M2's four memory-claim checks,
        # U-M3's five memory-graph checks, then U-M5's retrieval benchmark
        # registry check joined the mandated set (D-W8.1 pattern — the pin
        # moves UP with mandated new checks).
        self.assertEqual(
            len([l for l in out.strip().splitlines() if l]), 31
        )

    def test_domain_row_finding_names_id_field_pattern_only(self):
        self.aos_warned("task", "edit", "T-0002", "--accept", FAKE_ASSIGNMENT)
        out = self.doctor_ok()  # WARN, never FAIL
        line = self.sweep_line(out)
        self.assertTrue(line.startswith("[WARN]"))
        self.assert_contains(
            line, "task T-0002 acceptance: credential-assignment", "sweep line"
        )

    def test_event_metadata_finding_names_event_id_only(self):
        # The override reason lives ONLY in the done_override payload, and
        # the payload leaf is redacted at emit time — so this finding can
        # come only from the event's safe U-C3 metadata.
        self.aos_warned(
            "done", "T-0002", "--no-evidence",
            "--reason", f"holds {FAKE_ASSIGNMENT}",
        )
        self.assert_redacted(
            self.latest_payload("task", "done_override"), "reason"
        )
        out = self.doctor_ok()
        line = self.sweep_line(out)
        self.assertTrue(line.startswith("[WARN]"))
        self.assert_contains(line, "event #", "sweep line")
        self.assert_contains(
            line, "reason: credential-assignment", "sweep line"
        )

    def test_metadata_only_historical_event_stays_visible(self):
        # Warned write, then the domain row is edited back to benign text:
        # the only remaining trace is the add event's safe metadata (its
        # payload leaf is the placeholder). Doctor must still report it.
        self.aos_warned(
            "task", "add", f"Title {FAKE_ASSIGNMENT}", "-p", "demo"
        )
        self.assert_redacted(self.latest_payload("task", "add"), "title")
        self.aos_warned("task", "edit", "T-0004", "--title", "benign title")
        out = self.doctor_ok()
        line = self.sweep_line(out)
        self.assertTrue(line.startswith("[WARN]"))
        self.assert_contains(line, "event #", "sweep line")
        self.assert_contains(
            line, "title: credential-assignment", "sweep line"
        )
        # No domain row carries the value any more — the metadata finding
        # is the whole report; T-0004 itself is clean.
        self.assertNotIn("task T-0004", line)

    def test_malformed_metadata_is_ignored_and_never_echoed(self):
        # Rows events.emit would never write: doctor must not report
        # unknown names, must not crash on wrong types, and must never
        # echo a stored string — not even one hiding inside the metadata
        # lists or in a payload key position.
        self.insert_event(
            {
                "secret_warning": True,
                "secret_fields": ["nonexistent-field", 42, {"x": 1}],
                "secret_patterns": ["fabricated-pattern", None],
            }
        )
        self.insert_event(
            {
                "secret_warning": "yes",
                "secret_fields": "title",
                "secret_patterns": "credential-assignment",
            }
        )
        tampered_id = self.insert_event(
            {
                "secret_warning": True,
                "secret_fields": [FAKE_GHP],
                "secret_patterns": ["github-token"],
            }
        )
        key_smuggle_id = self.insert_event({FAKE_GHP: FAKE_ASSIGNMENT})
        out = self.doctor_ok()
        line = self.sweep_line(out)
        self.assertNotIn("nonexistent-field", out)
        self.assertNotIn("fabricated-pattern", out)
        # The two smuggling rows still surface — through the raw leaf scan
        # and a sanitized label, never through the tampered names.
        self.assert_contains(
            line,
            f"event #{tampered_id} secret_fields: github-token",
            "sweep line",
        )
        self.assert_contains(
            line,
            f"event #{key_smuggle_id} payload: credential-assignment",
            "sweep line",
        )

    def test_legacy_raw_event_payload_still_detected(self):
        # A pre-redaction event (value still in the payload) keeps its
        # baseline visibility via the raw string scan.
        legacy_id = self.insert_event(
            {"schema_version": 1, "task": "T-0002", "reason": FAKE_ASSIGNMENT}
        )
        # An event written by the pre-redaction implementation can carry
        # BOTH the raw value and the safe metadata: the metadata read and
        # the raw scan then agree, and the finding dedupes to one line.
        both_id = self.insert_event(
            {
                "schema_version": 1,
                "task": "T-0002",
                "reason": FAKE_ASSIGNMENT,
                "secret_warning": True,
                "secret_fields": ["reason"],
                "secret_patterns": ["credential-assignment"],
            }
        )
        out = self.doctor_ok()
        line = self.sweep_line(out)
        self.assertTrue(line.startswith("[WARN]"))
        self.assert_contains(
            line,
            f"event #{legacy_id} reason: credential-assignment",
            "sweep line",
        )
        self.assertEqual(
            line.count(f"event #{both_id} reason: credential-assignment"), 1
        )

    def test_evidence_provenance_finding_names_public_id_only(self):
        self.aos_warned(
            "evidence", "add", "T-0002", "--kind", "note",
            "--ref", "benign ref", "--claim", "benign claim",
            "--provenance", FAKE_PROVENANCE,
        )
        out = self.doctor_ok()
        line = self.sweep_line(out)
        self.assertTrue(line.startswith("[WARN]"))
        # The domain row is reported by evidence public ID + field +
        # canonical pattern name only.
        self.assert_contains(
            line, "evidence E-0002 provenance: github-token", "sweep line"
        )

    def test_provenance_event_stays_visible_after_row_cleanup(self):
        # Warned provenance write, then the domain row is cleaned back to
        # a benign value: the event actor is the placeholder and the
        # payload leaf never held the value, so the ONLY remaining trace
        # is the add event's safe metadata. Doctor must still report it.
        self.aos_warned(
            "evidence", "add", "T-0002", "--kind", "note",
            "--ref", "benign ref", "--claim", "benign claim",
            "--provenance", FAKE_PROVENANCE,
        )
        self.seed_sql(
            "UPDATE evidence SET provenance = 'human' WHERE id = 2", ()
        )
        out = self.doctor_ok()
        line = self.sweep_line(out)
        self.assertTrue(line.startswith("[WARN]"))
        self.assert_contains(line, "event #", "sweep line")
        self.assert_contains(
            line, "provenance: github-token", "sweep line"
        )
        # No domain row carries the value any more — the metadata finding
        # is the whole report.
        self.assertNotIn("evidence E-0002", line)

    def test_legacy_raw_event_actor_detected_without_echo(self):
        # A directly seeded pre-redaction event whose actor column still
        # holds the raw value: reported as event #ID actor: PATTERN under
        # the fixed safe label, never the stored text.
        legacy_id = self.insert_event(
            {"schema_version": 1, "task": "T-0002"}, actor=FAKE_PROVENANCE
        )
        out = self.doctor_ok()
        line = self.sweep_line(out)
        self.assertTrue(line.startswith("[WARN]"))
        self.assert_contains(
            line, f"event #{legacy_id} actor: github-token", "sweep line"
        )

    def test_seeded_assignee_and_branch_hint_are_findable(self):
        # No CLI write path exists for these columns, but assignee is
        # rendered in task frontmatter and branch_hint enters pack
        # REPO & BRANCH content — the sweep must cover them.
        self.seed_sql(
            "UPDATE tasks SET assignee = ?, branch_hint = ? WHERE id = 2",
            (FAKE_SK, f"feature/{FAKE_GHP}"),
        )
        out = self.doctor_ok()
        line = self.sweep_line(out)
        self.assertTrue(line.startswith("[WARN]"))
        self.assert_contains(
            line, "task T-0002 assignee: sk-api-key", "sweep line"
        )
        self.assert_contains(
            line, "task T-0002 branch_hint: github-token", "sweep line"
        )

    def test_benign_assignee_branch_hint_and_actors_stay_clean(self):
        self.seed_sql(
            "UPDATE tasks SET assignee = ?, branch_hint = ? WHERE id = 2",
            ("claude-code", "feature/night-1"),
        )
        self.insert_event(
            {"schema_version": 1, "task": "T-0002"}, actor="agent:codex"
        )
        out = self.doctor_ok()
        self.assertTrue(self.sweep_line(out).startswith("[PASS]"))

    def test_many_findings_are_bounded_and_privacy_safe(self):
        for index in range(12):
            self.aos_warned("in", f"idea {index} {FAKE_ASSIGNMENT}")
        out = self.doctor_ok()
        line = self.sweep_line(out)
        self.assertTrue(line.startswith("[WARN]"))
        # 12 task rows + 12 add-event metadata findings = 24; 10 shown.
        self.assertEqual(line.count("credential-assignment"), 10)
        self.assert_contains(line, "(+14 more)", "sweep line")

    def test_secret_shaped_agent_name_is_never_echoed_as_identifier(self):
        # The name field is itself scanned, so agents (and projects) are
        # identified by row id — a token-shaped name must not leak through
        # the identifier of its own finding.
        self.aos_warned("agent", "add", FAKE_GHP)
        out = self.doctor_ok()
        line = self.sweep_line(out)
        self.assertTrue(line.startswith("[WARN]"))
        self.assert_contains(line, "agent #1 name: github-token", "sweep line")

    def test_secret_shaped_project_slug_and_repo_path_are_findable(self):
        secret_repo = self.root / f"repo-{FAKE_SK}"
        secret_repo.mkdir()
        self.aos_warned(
            "project", "add", FAKE_SLUG, "--name", "Leaky",
            "--repo", str(secret_repo),
        )
        out = self.doctor_ok()
        line = self.sweep_line(out)
        self.assertTrue(line.startswith("[WARN]"))
        # Domain findings use the ROW id (never the slug) as identifier.
        self.assert_contains(line, "project #2 slug: sk-api-key", "sweep line")
        self.assert_contains(
            line, "project #2 repo_path: sk-api-key", "sweep line"
        )

    def test_sweep_never_fails_the_run_and_existing_checks_unchanged(self):
        self.aos_warned("in", f"idea {FAKE_ASSIGNMENT}")
        out = self.doctor_ok()
        self.assertNotIn("[FAIL]", out)
        self.assertIn("[PASS] database integrity_check passes", out)


# ---------------------------------------------------------------------------
# U-C3.6 — generated guidance stays in lockstep with the renderer


class TestAdapterGuidance(unittest.TestCase):
    def test_checked_in_adapters_are_byte_identical_to_renderer(self):
        for name in render.ADAPTER_NAMES:
            with self.subTest(adapter=name):
                disk = (
                    REPO_ROOT / "adapters" / name / "PROTOCOL.md"
                ).read_text(encoding="utf-8")
                self.assertEqual(disk, render.adapter_protocol_md(name))

    def test_protocol_states_the_secret_postures(self):
        for name in render.ADAPTER_NAMES:
            text = render.adapter_protocol_md(name)
            self.assertIn("Never write secret values into the ledger", text)
            self.assertIn("Packs refuse to build", text)
            self.assertIn("dropfile ingest refuses the whole file", text)
            self.assertIn("warns", text)


if __name__ == "__main__":
    unittest.main()
