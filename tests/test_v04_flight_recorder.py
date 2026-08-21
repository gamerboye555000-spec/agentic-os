"""U-E6 flight recorder module (agentic-os-v0.4-u-e6-flight-recorder-replay-
contract.md §2, §4.1-§4.3, §6, §11, D-v0.4.137, D-v0.4.147, D-v0.4.148).

Covers `agentic_os.flight_recorder` directly: assemble covers the seven table
arrays plus the closed journal payload members, `create` scans the entire
canonical byte sequence and refuses any secret-shaped data (exit 3), `verify`
recomputes every row hash and manifest, and the adversarial rows plant
credential-shaped and control text as DATA and assert it stays data. The
hostile rows construct no exploit.

Every fixture here is TEST-LOCAL (sealed with the same domain digests the
U-W2.3 suite pins), and the workspace is driven through the REAL CLI by
subprocess, so the module under test never vouches for itself.
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

#: Planted where a careless builder would copy it. Never a real credential.
FAKE_SECRET = "AKIAIOSFODNN7EXAMPLE"  # noqa: S105
FAKE_SK = "sk-live-ue6planted0000000000000000000"  # noqa: S105


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
        "idempotency_key": "ue6fixture-0001",
        "aos_task_id": "T-0001",
        "data_classification": "internal",
        "permitted_destinations": ["aos-ledger", "local"],
        "work_spec_id": "11111111-1111-4111-8111-111111111111",
        "goal": "Carry the U-E6 flight recorder.",
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
        "idempotency_key": "ue6fixture-0002",
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
                "ref": "notes/ue6",
                "claim": "The flight recorder carried every closed member.",
                "provenance": "human",
            }
        ],
        "errors": [],
    }
    document.update(overrides)
    return _seal(document)


def checkpoint(artifact: dict, workflow_id: str, **overrides) -> dict:
    body = {
        "schema": "aos.workflow-checkpoint/v1",
        "checkpoint_id": _uuid_n(30),
        "workflow_id": workflow_id,
        "work_spec_sha256": _digest_of(artifact),
        "attempt_no": 1,
        "checkpoint_seq": 1,
        "runtime_task_uuid": RUNTIME_UUID,
        "payload": {"cursor": 12},
        "created_at": "2026-08-01T10:06:00Z",
    }
    body.update(overrides)
    return _seal(body)


# ---------------------------------------------------------------------------
# The workspace harness: a REAL initialized workspace driven through the REAL
# entrypoint by subprocess.

def _env() -> dict:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("AOS_DEBUG", None)
    return env


class Ledger:
    """One real initialized workspace, driven through the REAL CLI."""

    def __init__(self, root: Path, ok):
        self.root = root
        self.ok = ok
        self.artifact = work_spec()
        self.report = compile_report(self.artifact)
        self.digest = _digest_of(self.artifact)
        self.wf = _workflow_identity(self.digest)

    def write(self, name: str, document: dict) -> str:
        path = self.root / name
        path.write_bytes(protocols.serialize_canonical_file_bytes(document))
        return str(path)

    def admit(self):
        self.ok("workflow", "admit", self.write("ws.json", self.artifact),
                self.write("rep.json", self.report))

    def validate(self):
        self.ok("workflow", "validate", self.wf)

    def dispatch(self):
        self.ok("workflow", "dispatch", self.wf)

    def accept(self, seed: int = 901):
        self.ok("workflow", "receipt", self.wf, self.write("rcp-a.json",
                receipt("accepted", self.artifact, receipt_id=seed,
                        intent_id=_intent_id(self.digest, 1),
                        idempotency_key=_idempotency_key(self.digest, 1),
                        queue_route="default")))

    def start(self, seed: int = 902):
        self.ok("workflow", "receipt", self.wf, self.write("rcp-s.json",
                receipt("started", self.artifact, receipt_id=seed)))

    def succeed(self):
        self.ok("workflow", "result", self.wf,
                self.write("result.json", result_envelope(self.artifact)))

    def record_checkpoint(self, **overrides):
        self.ok("workflow", "checkpoint", self.wf,
                self.write("cp.json", checkpoint(self.artifact, self.wf,
                                                **overrides)))

    def to_running(self):
        self.admit()
        self.validate()
        self.dispatch()
        self.accept()
        self.start()

    def to_succeeded(self):
        self.to_running()
        self.succeed()


class FlightRecorderModuleTest(unittest.TestCase):
    """The module surface against a real workspace."""

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
        self.ok("task", "add", "carry the flight recorder", "-p", "demo")
        self.ledger = Ledger(self.root, run)

    def connect(self) -> sqlite3.Connection:
        conn = db.connect(self.db_path)
        self.addCleanup(conn.close)
        return conn

    def payload(self) -> dict:
        conn = self.connect()
        try:
            return flight_recorder.assemble(conn, self.ledger.wf)
        finally:
            conn.close()

    def test_assemble_covers_the_seven_table_arrays_and_journal(self):
        self.ledger.to_succeeded()
        payload = self.payload()
        self.assertEqual(payload["protocol_version"], "1")
        self.assertEqual(payload["schema_version"], db.SCHEMA_VERSION)
        self.assertEqual(payload["workflow_id"], self.ledger.wf)
        self.assertEqual(payload["work_spec_digest"], self.ledger.digest)
        events = payload["workflow_events"]
        self.assertEqual(
            [e["event"] for e in events],
            ["workflow_admitted", "workflow_validated", "dispatch_requested",
             "dispatch_accepted", "run_started", "workflow_succeeded"],
        )
        self.assertEqual(len(events), 6)
        self.assertEqual(len(payload["workflow_commands"]), 6)
        self.assertEqual(len(payload["workflow_intents"]), 1)
        self.assertEqual(len(payload["workflow_receipts"]), 2)
        self.assertEqual(len(payload["workflow_facts"]), 1)
        self.assertEqual(len(payload["workflow_attempts"]), 1)
        self.assertEqual(len(payload["workflow_checkpoints"]), 0)
        self.assertEqual(
            [j["action"] for j in payload["journal_rows"]],
            ["workflow_admitted", "workflow_validated", "dispatch_requested",
             "dispatch_accepted", "run_started", "workflow_succeeded"],
        )
        for table in (
            "workflow_events", "workflow_commands", "workflow_intents",
            "workflow_receipts", "workflow_facts", "workflow_attempts",
            "workflow_checkpoints", "journal_rows",
        ):
            self.assertIn(table, payload["integrity_manifest"])
            self.assertEqual(
                payload["integrity_manifest"][table]["row_count"],
                len(payload[table]),
            )
        for event in events:
            self.assertEqual(
                event["content_sha256"],
                protocols.content_digest(event),
            )

    def test_create_scans_seals_and_is_digest_idempotent(self):
        self.ledger.to_succeeded()
        conn = self.connect()
        try:
            payload, wrapper = flight_recorder.create(conn, self.ledger.wf)
        finally:
            conn.close()
        self.assertEqual(wrapper["secret_scan"], {"scanned": True,
                                                  "findings": 0})
        self.assertIn("created_at", wrapper)
        canonical = protocols.serialize_canonical(payload).decode("utf-8")
        self.assertEqual(flight_recorder.verify(payload)["findings"], [])
        # create twice → the canonical payload is identical (only the
        # wrapper's wall-clock created_at differs).
        conn = self.connect()
        try:
            again, _ = flight_recorder.create(conn, self.ledger.wf)
        finally:
            conn.close()
        self.assertEqual(protocols.serialize_canonical(again),
                         protocols.serialize_canonical(payload))

    def test_bundle_round_trip_through_write_and_read(self):
        self.ledger.to_succeeded()
        conn = self.connect()
        try:
            payload, wrapper = flight_recorder.create(conn, self.ledger.wf)
        finally:
            conn.close()
        bundle_path = self.root / "flight-record.json"
        flight_recorder.write_bundle(bundle_path, payload, wrapper)
        loaded = flight_recorder.read_bundle(bundle_path)
        self.assertEqual(loaded["workflow_id"], self.ledger.wf)
        self.assertEqual(
            protocols.serialize_canonical(loaded),
            protocols.serialize_canonical(payload),
        )

    def test_verify_reports_a_tampered_event_digest(self):
        self.ledger.to_succeeded()
        payload = copy.deepcopy(self.payload())
        payload["workflow_events"][2]["content_sha256"] = "0" * 64
        report = flight_recorder.verify(payload)
        self.assertFalse(report["ok"])
        self.assertIn("digest_divergent",
                      [f["kind"] for f in report["findings"]])
        self.assertIn("/workflow_events/3",
                      [f["where"] for f in report["findings"]])

    def test_verify_reports_a_tampered_manifest(self):
        self.ledger.to_succeeded()
        payload = copy.deepcopy(self.payload())
        payload["integrity_manifest"]["workflow_events"]["row_count"] += 1
        report = flight_recorder.verify(payload)
        self.assertIn("manifest_divergent",
                      [f["kind"] for f in report["findings"]])

    def test_verify_reports_a_deleted_event_row_as_seq_and_revision_gap(self):
        self.ledger.to_succeeded()
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute(
                f"DELETE FROM {db.WORKFLOW_EVENTS_TABLE} WHERE seq = 4"
            )
            conn.commit()
            payload = flight_recorder.assemble(conn, self.ledger.wf)
        finally:
            conn.close()
        self.assertEqual([e["seq"] for e in payload["workflow_events"]],
                         [1, 2, 3, 5, 6])
        report = flight_recorder.verify(payload)
        kinds = {f["kind"] for f in report["findings"]}
        self.assertIn("seq_gap", kinds)
        self.assertIn("revision_gap", kinds)

    def test_verify_reports_a_tampered_checkpoint_document_sha256(self):
        self.ledger.to_running()
        self.ledger.record_checkpoint()
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute(
                f"UPDATE {db.WORKFLOW_CHECKPOINTS_TABLE} SET "
                "document_sha256 = ?",
                ("0" * 64,),
            )
            conn.commit()
            payload = flight_recorder.assemble(conn, self.ledger.wf)
            report = flight_recorder.verify(payload)
        finally:
            conn.close()
        self.assertEqual(len(payload["workflow_checkpoints"]), 1)
        self.assertIn("digest_divergent",
                      [f["kind"] for f in report["findings"]])
        self.assertIn("/workflow_checkpoints/1",
                      [f["where"] for f in report["findings"]])

    def test_unknown_protocol_version_is_a_refusal(self):
        self.ledger.admit()
        payload = self.payload()
        payload["protocol_version"] = "2"
        with self.assertRaises(Exception) as caught:
            flight_recorder.verify(payload)
        self.assertEqual(getattr(caught.exception, "exit_code", None), 2)

    def test_secret_planted_in_a_journal_payload_member_refuses_create(self):
        self.ledger.to_succeeded()
        conn = self.connect()
        try:
            cur = conn.cursor()
            row_id = int(self.ledger.wf[3:])
            cur.execute(
                "UPDATE events SET payload_json = ? WHERE entity='workflow' "
                "AND entity_id=? AND action='workflow_admitted'",
                (json.dumps({"reason": f"token = {FAKE_SK}"}), row_id),
            )
            conn.commit()
            with self.assertRaises(Exception) as caught:
                flight_recorder.create(conn, self.ledger.wf)
            self.assertEqual(getattr(caught.exception, "exit_code", None), 3)
            message = str(caught.exception)
            self.assertIn("secret_in_flight_record", message)
            self.assertIn("sk-api-key", message)
            self.assertNotIn(FAKE_SK, message)
        finally:
            conn.close()

    def test_a_goal_secret_never_reaches_the_canonical_payload(self):
        self.ledger.artifact = work_spec(
            goal=f"Embed {FAKE_SECRET} in prose and keep it out of bundles."
        )
        self.ledger.report = compile_report(self.ledger.artifact)
        self.ledger.digest = _digest_of(self.ledger.artifact)
        self.ledger.wf = _workflow_identity(self.ledger.digest)
        self.ledger.admit()
        payload = self.payload()
        canonical = protocols.serialize_canonical(payload).decode("utf-8")
        self.assertNotIn(FAKE_SECRET, canonical)
        conn = self.connect()
        try:
            _, wrapper = flight_recorder.create(conn, self.ledger.wf)
        finally:
            conn.close()
        self.assertEqual(wrapper["secret_scan"]["findings"], 0)

    def test_missing_workflow_is_a_refusal(self):
        conn = self.connect()
        try:
            with self.assertRaises(Exception) as caught:
                flight_recorder.assemble(conn, "WF-1")
            self.assertEqual(getattr(caught.exception, "exit_code", None), 2)
        finally:
            conn.close()

    def test_foreign_ledger_rows_are_not_carried(self):
        self.ledger.admit()
        # A second, unrelated workflow must not leak into the first bundle.
        other = Ledger(self.root, self.ok)
        other.artifact = work_spec(work_spec_id="33333333-3333-4333-8333-"
                                               "333333333333")
        other.report = compile_report(other.artifact)
        other.digest = _digest_of(other.artifact)
        other.wf = _workflow_identity(other.digest)
        other.admit()
        payload = self.payload()
        self.assertEqual(len(payload["workflow_events"]), 1)
        self.assertEqual(payload["workflow_events"][0]["workflow_id"],
                         self.ledger.wf)


if __name__ == "__main__":
    unittest.main()