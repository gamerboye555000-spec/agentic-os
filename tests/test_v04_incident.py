"""U-E6 incident forensics module (agentic-os-v0.4-u-e6-flight-recorder-
replay-contract.md §1, §4.4, §11, D-v0.4.151).

Covers `agentic_os.incident` directly: the `aos.incident-report/v1` document
shape, the evidence index across the seven workflow tables (never the operator
journal), the correlation-only discipline (the document never infers causation
the ledger does not support), and the four-file export into an EMPTY directory.
"""

from __future__ import annotations

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
    incident,
    protocols,
    utils,
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
        "idempotency_key": "ue6incident-0001",
        "aos_task_id": "T-0001",
        "data_classification": "internal",
        "permitted_destinations": ["aos-ledger", "local"],
        "work_spec_id": "11111111-1111-4111-8111-111111111111",
        "goal": "Reconstruct the U-E6 incident context.",
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
        "idempotency_key": "ue6incident-0002",
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
                "ref": "notes/ue6-incident",
                "claim": "The incident report cites evidence by row identity.",
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


class IncidentModuleTest(unittest.TestCase):
    """The incident module against a real workspace."""

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
        self.ok("task", "add", "carry incident forensics", "-p", "demo")
        self.artifact = work_spec()
        self.report = compile_report(self.artifact)
        self.digest = _digest_of(self.artifact)
        self.wf = _workflow_identity(self.digest)

    def write_doc(self, name: str, document: dict) -> str:
        path = self.root / name
        path.write_bytes(protocols.serialize_canonical_file_bytes(document))
        return str(path)

    def to_running(self):
        self.ok("workflow", "admit",
                self.write_doc("ws.json", self.artifact),
                self.write_doc("rep.json", self.report))
        self.ok("workflow", "validate", self.wf)
        self.ok("workflow", "dispatch", self.wf)
        self.ok("workflow", "receipt", self.wf, self.write_doc("a.json",
                    receipt("accepted", self.artifact, receipt_id=901,
                            intent_id=_intent_id(self.digest, 1),
                            idempotency_key=_idempotency_key(self.digest, 1),
                            queue_route="default")))
        self.ok("workflow", "receipt", self.wf, self.write_doc("s.json",
                    receipt("started", self.artifact, receipt_id=902)))

    def to_succeeded(self):
        self.to_running()
        self.ok("workflow", "result", self.wf,
                self.write_doc("r.json", result_envelope(self.artifact)))

    def connect(self) -> sqlite3.Connection:
        conn = db.connect(self.db_path)
        self.addCleanup(conn.close)
        return conn

    def report_document(self, context: str = "") -> dict:
        conn = self.connect()
        try:
            return incident.create_report(conn, self.wf, context)
        finally:
            conn.close()

    # -- the document --------------------------------------------------------

    def test_report_document_shape(self):
        self.to_succeeded()
        document = self.report_document()
        self.assertEqual(document["schema"], "aos.incident-report/v1")
        self.assertEqual(document["protocol_version"], "1")
        self.assertEqual(document["workflow_id"], self.wf)
        self.assertIn("flight_record_sha256", document)
        self.assertIn("observability", document)
        self.assertIn("verification", document)
        self.assertIn("evidence", document)
        self.assertIn("created_at", document)
        self.assertNotIn("context", document)

    def test_report_context_is_carried_when_declared(self):
        self.to_succeeded()
        document = self.report_document(
            "Investigate the missing receipt before the weekend."
        )
        self.assertEqual(
            document["context"],
            "Investigate the missing receipt before the weekend.",
        )

    def test_flight_record_sha256_is_the_canonical_bundle_digest(self):
        self.to_succeeded()
        conn = self.connect()
        try:
            payload = flight_recorder.assemble(conn, self.wf)
            expected = hashlib.sha256(
                protocols.serialize_canonical(payload)
            ).hexdigest()
        finally:
            conn.close()
        self.assertEqual(self.report_document()["flight_record_sha256"],
                         expected)

    def test_evidence_index_covers_the_tables_that_have_rows(self):
        self.to_succeeded()
        evidence = self.report_document()["evidence"]
        by_table = {}
        for entry in evidence:
            by_table.setdefault(entry["table"], []).append(entry)
            self.assertIsInstance(entry["row_id"], int)
            self.assertEqual(len(entry["content_sha256"]), 64)
        self.assertEqual(
            sorted(by_table),
            ["workflow_attempts", "workflow_commands", "workflow_events",
             "workflow_facts", "workflow_intents", "workflow_receipts"],
        )
        self.assertEqual(len(by_table["workflow_events"]), 6)
        self.assertEqual(len(by_table["workflow_commands"]), 6)
        self.assertEqual(len(by_table["workflow_intents"]), 1)
        self.assertEqual(len(by_table["workflow_receipts"]), 2)
        self.assertEqual(len(by_table["workflow_facts"]), 1)
        self.assertEqual(len(by_table["workflow_attempts"]), 1)
        # No checkpoint was recorded, so the (empty) table cites nothing.
        self.assertNotIn("workflow_checkpoints", by_table)

    def test_evidence_index_cites_checkpoints_when_one_exists(self):
        self.to_running()
        checkpoint_doc = {
            "schema": "aos.workflow-checkpoint/v1",
            "checkpoint_id": _uuid_n(30),
            "workflow_id": self.wf,
            "work_spec_sha256": self.digest,
            "attempt_no": 1,
            "checkpoint_seq": 1,
            "runtime_task_uuid": RUNTIME_UUID,
            "payload": {"cursor": 12},
            "created_at": "2026-08-01T10:06:00Z",
        }
        self.ok("workflow", "checkpoint", self.wf,
                self.write_doc("cp.json", _seal(checkpoint_doc)))
        evidence = self.report_document()["evidence"]
        by_table = {}
        for entry in evidence:
            by_table.setdefault(entry["table"], []).append(entry)
        self.assertEqual(len(by_table["workflow_checkpoints"]), 1)

    def test_observability_and_verification_are_projection_documents(self):
        self.to_succeeded()
        document = self.report_document()
        self.assertEqual(document["observability"]["workflow_id"], self.wf)
        self.assertIn("spans", document["observability"])
        self.assertIn("trace_root", document["observability"])
        verification = document["verification"]
        self.assertIn("workflows", verification)
        self.assertEqual(verification["workflows"][0]["workflow_id"], self.wf)

    # -- export ---------------------------------------------------------------

    def test_export_writes_exactly_the_four_files_into_an_empty_dir(self):
        self.to_succeeded()
        out = self.root / "outbox"
        out.mkdir()
        written = incident.export(self.connect(), self.wf, "", out)
        self.assertEqual(
            [name for name, _ in written],
            ["incident.json", "flight-record.json", "observability.json",
             "verification.json"],
        )
        for name, size in written:
            self.assertGreater(size, 0)
            self.assertTrue((out / name).is_file())
        # The flight record file is the bundle (canonical payload + wrapper).
        bundle = json.loads((out / "flight-record.json").read_text())
        self.assertIn("canonical_payload", bundle)
        self.assertIn("wrapper", bundle)
        self.assertEqual(
            bundle["canonical_payload"]["workflow_id"], self.wf
        )

    def test_export_refuses_a_non_directory(self):
        self.to_succeeded()
        target = self.root / "not-a-dir"
        target.write_text("occupied")
        with self.assertRaises(Exception) as caught:
            incident.export(self.connect(), self.wf, "", target)
        self.assertEqual(getattr(caught.exception, "exit_code", None), 2)

    def test_export_refuses_a_non_empty_directory(self):
        self.to_succeeded()
        out = self.root / "outbox"
        out.mkdir()
        (out / "existing.txt").write_text("do not merge")
        with self.assertRaises(Exception) as caught:
            incident.export(self.connect(), self.wf, "", out)
        self.assertEqual(getattr(caught.exception, "exit_code", None), 2)

    def test_write_report_refuses_an_io_error(self):
        self.to_succeeded()
        target = self.root / "occupied-dir"
        target.mkdir()
        with self.assertRaises(Exception) as caught:
            incident.write_report(target, self.report_document())
        self.assertEqual(getattr(caught.exception, "exit_code", None), 4)

    def test_create_report_for_a_missing_workflow_is_a_refusal(self):
        with self.assertRaises(Exception) as caught:
            self.report_document("WF-999")
        self.assertEqual(getattr(caught.exception, "exit_code", None), 2)


if __name__ == "__main__":
    unittest.main()