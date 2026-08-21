"""U-E6 deterministic replay module (agentic-os-v0.4-u-e6-flight-recorder-
replay-contract.md §1, §4.2-§4.3, §8, §11).

Covers `agentic_os.replay` directly: fold-based replay over a real workflow's
flight record, the byte-identical cross-check against stored command revision
pairs, divergence reporting, re-simulation substitutions (retry_max_attempts,
removed_event_seq counterfactuals, work_spec_document, allow_digest_mismatch),
and the exit-code contract. Replay NEVER mutates aos.db; every hostile row here
reads a flight record and asserts the trace or the refusal.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agentic_os import (  # noqa: E402
    db,
    flight_recorder,
    protocols,
    replay,
    utils,
    workflow_store,
)

RUNTIME_UUID = "9f8e7d6c-5b4a-4392-8180-7f6e5d4c3b2a"
WORK_SPEC_SCHEMA_SHA256 = (
    "07ac96ba08a1579bbd681ab4087156e9d8facf849f3348e0e494658f3acceab9"
)
SNAPSHOT_SHA256 = "a" * 64
TRACE = {
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "correlation_id": "0f1e2d3c-4b5a-4998-8877-665544332211",
}


# ---------------------------------------------------------------------------
# Test-local canonical JSON, digests and derivations (independent pins).

def _canon(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")


def _digest_of(document: dict) -> str:
    body = {k: v for k, v in document.items() if k != "content_sha256"}
    return hashlib.sha256(_canon(body)).hexdigest()


def _seal(document: dict) -> dict:
    body = {k: v for k, v in document.items() if k != "content_sha256"}
    body["content_sha256"] = _digest_of(body)
    return body


def _tagged(tag: bytes, material: bytes) -> bytes:
    return hashlib.sha256(tag + b"\0" + material).digest()


def _uuid8(digest: bytes) -> str:
    raw = bytearray(digest[:16])
    raw[6] = (raw[6] & 0x0F) | 0x80
    raw[8] = (raw[8] & 0x3F) | 0x80
    text = raw.hex()
    return f"{text[0:8]}-{text[8:12]}-{text[12:16]}-{text[16:20]}-{text[20:32]}"


def _intent_id(work_spec_sha256: str, intent_seq: int) -> str:
    material = f"{work_spec_sha256}:{intent_seq}".encode("utf-8")
    return _uuid8(_tagged(b"aos-workflow-intent/v1", material))


def _idempotency_key(work_spec_sha256: str, intent_seq: int) -> str:
    material = f"{work_spec_sha256}:{intent_seq}".encode("utf-8")
    return "wfd-" + _tagged(b"aos-workflow-dispatch-idem/v1", material).hex()[:40]


def _workflow_identity(work_spec_sha256: str) -> str:
    digest = _tagged(
        b"aos-workflow-identity/v1", work_spec_sha256.encode("utf-8")
    )
    return "WF-" + str(int.from_bytes(digest[:8], "big") >> 1 or 1)


def _uuid_n(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


def work_spec(**overrides) -> dict:
    document = {
        "schema": "beast.work-spec/v1",
        "protocol_version": 1,
        "content_hash_alg": "aos-sha256-canonical/v1",
        "created_at": "2026-08-01T09:00:00Z",
        "issuer": "aos.local",
        "audience": ["runtime.local"],
        "scope": {"project": "demo"},
        "trace": dict(TRACE),
        "idempotency_key": "ue6replay-0001",
        "aos_task_id": "T-0001",
        "data_classification": "internal",
        "permitted_destinations": ["aos-ledger", "local"],
        "work_spec_id": "11111111-1111-4111-8111-111111111111",
        "goal": "Replay the U-E6 history deterministically.",
        "acceptance_criteria": ["Focused tests pass"],
        "expected_result": {
            "result_schema": "beast.result-envelope/v1",
            "evidence_kinds": ["note"],
            "min_evidence_count": 1,
        },
    }
    document.update(overrides)
    return _seal(document)


def compile_report(artifact: dict, **overrides) -> dict:
    report = {
        "schema": "aos.work-spec-compile-report/v1",
        "algorithm_version": "aos-workspec-compile/v1",
        "status": "valid",
        "work_spec_id": artifact["work_spec_id"],
        "work_spec_sha256": _digest_of(artifact),
        "findings": [],
        "resolutions": [],
        "provenance": {"/goal": "explicit"},
        "defaults_applied": [],
        "registry_state": {
            "registry_version": 1,
            "work_spec_schema_sha256": WORK_SPEC_SCHEMA_SHA256,
            "snapshot_sha256": SNAPSHOT_SHA256,
        },
    }
    report.update(overrides)
    return _seal(report)


def receipt(kind: str, artifact: dict, *, receipt_id: int | str = 900,
            intent_id: str | None = None, idempotency_key: str | None = None,
            queue_route: str | None = None, **overrides) -> dict:
    document: dict = {
        "schema": "aos.workflow-queue-receipt/v1",
        "receipt_kind": kind,
        "receipt_id": receipt_id if isinstance(receipt_id, str)
        else _uuid_n(receipt_id),
        "workflow_id": _workflow_identity(_digest_of(artifact)),
        "work_spec_sha256": _digest_of(artifact),
        "reported_at": "2026-08-01T10:05:00Z",
        "runtime_task_uuid": RUNTIME_UUID,
    }
    if intent_id is not None:
        document["intent_id"] = intent_id
    if idempotency_key is not None:
        document["idempotency_key"] = idempotency_key
    if queue_route is not None:
        document["queue_route"] = queue_route
    document.update(overrides)
    return _seal(document)


def result_envelope(artifact: dict, **overrides) -> dict:
    document = {
        "schema": "beast.result-envelope/v1",
        "protocol_version": 1,
        "content_hash_alg": "aos-sha256-canonical/v1",
        "created_at": "2026-08-01T10:10:00Z",
        "issuer": "runtime.local",
        "audience": ["aos.local"],
        "scope": {"project": "demo"},
        "trace": dict(TRACE),
        "idempotency_key": "ue6replay-0002",
        "aos_task_id": "T-0001",
        "data_classification": "internal",
        "permitted_destinations": ["aos-ledger", "local"],
        "result_id": "22222222-2222-4222-8222-222222222222",
        "work_spec_id": artifact["work_spec_id"],
        "work_spec_sha256": _digest_of(artifact),
        "outcome": "success",
        "retryable": False,
        "attempt": 1,
        "evidence": [
            {
                "kind": "note",
                "ref": "notes/ue6-replay",
                "claim": "Replay produced the identical trace.",
                "provenance": "human",
            }
        ],
        "errors": [],
    }
    document.update(overrides)
    return _seal(document)


# ---------------------------------------------------------------------------
# The workspace harness.

def _env() -> dict:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("AOS_DEBUG", None)
    return env


class ReplayModuleTest(unittest.TestCase):
    """Replay against a real workspace's flight record."""

    maxDiff = None

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.aos_dir = self.root / utils.AOS_DIR_NAME
        self.db_path = self.aos_dir / utils.DB_FILENAME

        def run(*argv):
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "aos.py"), "--root",
                 str(self.root), *argv],
                cwd=str(REPO_ROOT), env=_env(), capture_output=True,
                text=True, timeout=180,
            )
            self.assertEqual(result.returncode, 0,
                             f"{argv} failed ({result.returncode}): "
                             f"{result.stderr}")
            return result.stdout

        self.ok = run
        self.ok("init")
        self.ok("project", "add", "demo", "--name", "Demo",
                "--repo", str(self.root))
        self.ok("task", "add", "carry deterministic replay", "-p", "demo")
        self.artifact = work_spec()
        self.report = compile_report(self.artifact)
        self.digest = _digest_of(self.artifact)
        self.wf = _workflow_identity(self.digest)

    def write_doc(self, name: str, document: dict) -> str:
        path = self.root / name
        path.write_bytes(protocols.serialize_canonical_file_bytes(document))
        return str(path)

    def ok_cli(self, *argv):
        return self.ok(*argv)

    def admit(self):
        self.ok_cli("workflow", "admit",
                    self.write_doc("ws.json", self.artifact),
                    self.write_doc("rep.json", self.report))

    def connect(self) -> sqlite3.Connection:
        conn = db.connect(self.db_path)
        self.addCleanup(conn.close)
        return conn

    def to_succeeded(self):
        self.admit()
        self.ok_cli("workflow", "validate", self.wf)
        self.ok_cli("workflow", "dispatch", self.wf)
        self.ok_cli("workflow", "receipt", self.wf, self.write_doc("a.json",
                    receipt("accepted", self.artifact, receipt_id=901,
                            intent_id=_intent_id(self.digest, 1),
                            idempotency_key=_idempotency_key(self.digest, 1),
                            queue_route="default")))
        self.ok_cli("workflow", "receipt", self.wf, self.write_doc("s.json",
                    receipt("started", self.artifact, receipt_id=902)))
        self.ok_cli("workflow", "result", self.wf,
                    self.write_doc("r.json", result_envelope(self.artifact)))

    def to_dispatched(self):
        self.admit()
        self.ok_cli("workflow", "validate", self.wf)
        self.ok_cli("workflow", "dispatch", self.wf)
        self.ok_cli("workflow", "receipt", self.wf, self.write_doc("a.json",
                    receipt("accepted", self.artifact, receipt_id=901,
                            intent_id=_intent_id(self.digest, 1),
                            idempotency_key=_idempotency_key(self.digest, 1),
                            queue_route="default")))

    def payload(self) -> dict:
        conn = self.connect()
        try:
            return flight_recorder.assemble(conn, self.wf)
        finally:
            conn.close()

    def replay(self, payload: dict, substitutions: dict | None = None):
        conn = self.connect()
        try:
            return replay.replay(payload, conn, substitutions)
        finally:
            conn.close()

    # -- happy path ---------------------------------------------------------

    def test_happy_path_is_fully_byte_identical(self):
        self.to_succeeded()
        trace = self.replay(self.payload())
        self.assertTrue(trace["byte_identical"])
        self.assertIsNone(trace["divergence_at_seq"])
        self.assertIsNone(trace["refusal"])
        self.assertEqual(trace["final_state"], "succeeded")
        self.assertEqual(trace["workflow_id"], self.wf)
        self.assertEqual(trace["work_spec_digest"], self.digest)
        self.assertEqual(trace["substitutions"], [])
        self.assertEqual(trace["declared_substitutions"], [])
        for step in trace["steps"]:
            self.assertTrue(step["byte_identical"], step["event"])
        self.assertEqual(
            [s["event"] for s in trace["steps"]],
            ["workflow_admitted", "workflow_validated", "dispatch_requested",
             "dispatch_accepted", "run_started", "workflow_succeeded"],
        )

    def test_empty_substitutions_equals_no_substitutions(self):
        self.to_succeeded()
        payload = self.payload()
        plain = self.replay(payload)
        empty = self.replay(payload, {})
        self.assertEqual(plain["final_state"], empty["final_state"])
        self.assertEqual(plain["byte_identical"], empty["byte_identical"])
        self.assertEqual(plain["steps"], empty["steps"])

    # -- divergence ---------------------------------------------------------

    def test_divergence_is_reported_when_command_revisions_disagree(self):
        self.to_succeeded()
        payload = copy.deepcopy(self.payload())
        command = payload["workflow_commands"][1]  # the validate command
        self.assertEqual(command["command"], "validate")
        command["expected_revision"] = command["expected_revision"] + 1
        command["content_sha256"] = flight_recorder._row_digest_from(
            workflow_store._command_row_payload, command,
            flight_recorder._COMMAND_COLUMNS,
        )
        payload["integrity_manifest"]["workflow_commands"] = \
            flight_recorder._manifest_for("workflow_commands",
                                          payload["workflow_commands"])
        self.assertEqual(flight_recorder.verify(payload)["findings"], [])
        trace = self.replay(payload)
        self.assertFalse(trace["byte_identical"])
        self.assertEqual(trace["divergence_at_seq"], command["event_seq_first"])
        self.assertEqual(trace["final_state"], "succeeded")

    # -- re-simulation substitutions ----------------------------------------

    def test_retry_max_attempts_override_is_declared_and_applied(self):
        self.to_succeeded()
        trace = self.replay(self.payload(), {"retry_max_attempts": 3})
        self.assertTrue(trace["byte_identical"])
        self.assertEqual(trace["final_state"], "succeeded")
        dispatch_steps = [s for s in trace["steps"]
                          if s["event"] == "dispatch_requested"]
        self.assertEqual(len(dispatch_steps), 1)
        self.assertEqual(dispatch_steps[0]["attempt_budget"], 3)
        self.assertIn({"kind": "retry_max_attempts", "value": 3},
                      trace["declared_substitutions"])

    def test_removed_event_seq_counterfactual_never_reaches_running(self):
        # A workflow whose ledger ends at dispatch_accepted (state scheduled).
        self.to_dispatched()
        payload = self.payload()
        self.assertEqual([e["event"] for e in payload["workflow_events"]],
                         ["workflow_admitted", "workflow_validated",
                          "dispatch_requested", "dispatch_accepted"])
        trace = self.replay(payload, {"removed_event_seq": 4})
        self.assertTrue(trace["byte_identical"])
        self.assertIsNone(trace["divergence_at_seq"])
        self.assertEqual(trace["final_state"], "validated")
        self.assertEqual(
            [s["event"] for s in trace["steps"]],
            ["workflow_admitted", "workflow_validated", "dispatch_requested"],
        )
        states = {s["to_state"] for s in trace["steps"]} | {
            s["from_state"] for s in trace["steps"]
        }
        self.assertNotIn("running", states)
        self.assertNotIn("scheduled", states)
        self.assertIn({"kind": "removed_event_seq", "seq": 4},
                      trace["substitutions"])
        # The renumbered sequence is dense in both seq and revision.
        self.assertEqual([s["seq"] for s in trace["steps"]], [1, 2, 3])
        self.assertEqual([s["revision"] for s in trace["steps"]], [1, 2, 3])

    def test_removed_event_seq_not_present_is_a_refusal(self):
        self.to_dispatched()
        payload = self.payload()
        with self.assertRaises(Exception) as caught:
            self.replay(payload, {"removed_event_seq": 9})
        self.assertEqual(getattr(caught.exception, "exit_code", None), 2)

    def test_work_spec_document_substitution_without_allow_is_a_refusal(self):
        self.to_succeeded()
        other = work_spec(goal="A DIFFERENT goal; digest no longer matches.")
        with self.assertRaises(Exception) as caught:
            self.replay(self.payload(),
                        {"work_spec_document": other})
        self.assertEqual(getattr(caught.exception, "exit_code", None), 3)
        self.assertIn("work_spec_digest", str(caught.exception))

    def test_work_spec_document_substitution_with_allow_proceeds(self):
        self.to_succeeded()
        other = work_spec(goal="A DIFFERENT goal; digest no longer matches.")
        trace = self.replay(
            self.payload(),
            {"work_spec_document": other, "allow_digest_mismatch": True},
        )
        self.assertEqual(trace["final_state"], "succeeded")
        self.assertIn(
            {"kind": "allow_digest_mismatch", "value": True},
            trace["declared_substitutions"],
        )

    # -- failure semantics ---------------------------------------------------

    def test_unknown_protocol_version_is_a_refusal(self):
        self.to_succeeded()
        payload = self.payload()
        payload["protocol_version"] = "2"
        with self.assertRaises(Exception) as caught:
            self.replay(payload)
        self.assertEqual(getattr(caught.exception, "exit_code", None), 2)

    def test_schema_version_mismatch_is_a_refusal(self):
        self.to_succeeded()
        payload = self.payload()
        payload["schema_version"] = "99"
        with self.assertRaises(Exception) as caught:
            self.replay(payload)
        self.assertEqual(getattr(caught.exception, "exit_code", None), 2)
        self.assertIn("reducer_vocabulary_mismatch", str(caught.exception))

    def test_tampered_bundle_refuses_integrity(self):
        self.to_succeeded()
        payload = self.payload()
        payload["workflow_events"][2]["content_sha256"] = "0" * 64
        with self.assertRaises(Exception) as caught:
            self.replay(payload)
        self.assertEqual(getattr(caught.exception, "exit_code", None), 1)

    def test_empty_event_sequence_refuses(self):
        self.to_succeeded()
        payload = copy.deepcopy(self.payload())
        payload["workflow_events"] = []
        payload["integrity_manifest"]["workflow_events"] = \
            flight_recorder._manifest_for("workflow_events", [])
        self.assertEqual(flight_recorder.verify(payload)["findings"], [])
        with self.assertRaises(Exception) as caught:
            self.replay(payload)
        self.assertEqual(getattr(caught.exception, "exit_code", None), 1)

    # -- substitution file shape checks --------------------------------------

    def test_read_substitutions_rejects_unknown_keys(self):
        path = self.root / "subst.json"
        path.write_text(json.dumps({"bogus_key": 1}))
        with self.assertRaises(Exception) as caught:
            replay.read_substitutions(path)
        self.assertEqual(getattr(caught.exception, "exit_code", None), 2)
        self.assertIn("Unknown substitution key", str(caught.exception))

    def test_read_substitutions_rejects_non_object(self):
        path = self.root / "subst.json"
        path.write_text(json.dumps([1, 2]))
        with self.assertRaises(Exception) as caught:
            replay.read_substitutions(path)
        self.assertEqual(getattr(caught.exception, "exit_code", None), 2)

    def test_malformed_retry_override_is_a_refusal(self):
        self.to_succeeded()
        with self.assertRaises(Exception) as caught:
            self.replay(self.payload(), {"retry_max_attempts": 0})
        self.assertEqual(getattr(caught.exception, "exit_code", None), 2)
        with self.assertRaises(Exception) as caught:
            self.replay(self.payload(), {"retry_max_attempts": "3"})
        self.assertEqual(getattr(caught.exception, "exit_code", None), 2)


if __name__ == "__main__":
    unittest.main()