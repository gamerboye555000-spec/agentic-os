"""U-E6 flight recorder CLI (agentic-os-v0.4-u-e6-flight-recorder-replay-
contract.md §5, §7, §11).

Drives the REAL `aos.py` entrypoint through the `flight-record create/verify`
leaves: bundle write and verify exit codes, the eco deferral, the recovery
block, and the adversarial rows (tampered bundle, secret-shaped journal data,
missing workflow). stdout must stay byte-clean on every refusal.
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
    power,
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
FAKE_SK = "sk-live-ue6cliplanted00000000000000000"  # noqa: S105


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
        "idempotency_key": "ue6cli-0001",
        "aos_task_id": "T-0001",
        "data_classification": "internal",
        "permitted_destinations": ["aos-ledger", "local"],
        "work_spec_id": "11111111-1111-4111-8111-111111111111",
        "goal": "Drive the flight recorder from the CLI.",
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
        "idempotency_key": "ue6cli-0002",
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
                "ref": "notes/ue6-cli",
                "claim": "The flight recorder CLI carried every frozen verb.",
                "provenance": "human",
            }
        ],
        "errors": [],
    }
    document.update(overrides)
    return _seal(document)


def _env() -> dict:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(REPO_ROOT)
    env.pop("AOS_DEBUG", None)
    return env


class CliCase(unittest.TestCase):
    """One initialized workspace driven through the REAL entrypoint."""

    maxDiff = None

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.aos_dir = self.root / utils.AOS_DIR_NAME
        self.db_path = self.aos_dir / utils.DB_FILENAME
        self.ok("init")
        self.ok("project", "add", "demo", "--name", "Demo",
                "--repo", str(self.root))
        self.ok("task", "add", "carry the flight recorder CLI", "-p", "demo")
        self.artifact = work_spec()
        self.report = compile_report(self.artifact)
        self.digest = _digest_of(self.artifact)
        self.wf = _workflow_identity(self.digest)

    def run_cli(self, *argv):
        return subprocess.run(
            [sys.executable, str(REPO_ROOT / "aos.py"), "--root",
             str(self.root), *argv],
            cwd=str(REPO_ROOT), env=_env(), capture_output=True,
            text=True, timeout=180,
        )

    def ok(self, *argv):
        result = self.run_cli(*argv)
        self.assertEqual(result.returncode, 0,
                         f"{argv} failed ({result.returncode}): {result.stderr}")
        return result.stdout

    def refused(self, *argv, code=1):
        result = self.run_cli(*argv)
        self.assertEqual(result.returncode, code,
                         f"{argv} exit {result.returncode}, expected {code}: "
                         f"{result.stdout!r} {result.stderr!r}")
        self.assertEqual(result.stdout, "",
                         f"{argv} wrote to stdout on a refusal")
        return result.stderr

    def write_doc(self, name: str, document: dict) -> str:
        path = self.root / name
        path.write_bytes(protocols.serialize_canonical_file_bytes(document))
        return str(path)

    def connect(self) -> sqlite3.Connection:
        conn = db.connect(self.db_path)
        self.addCleanup(conn.close)
        return conn

    def to_succeeded(self):
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
        self.ok("workflow", "result", self.wf,
                self.write_doc("r.json", result_envelope(self.artifact)))

    def create_bundle(self) -> Path:
        bundle_path = self.root / "flight-record.json"
        self.ok("flight-record", "create", self.wf,
                "--out", str(bundle_path))
        self.assertTrue(bundle_path.is_file())
        return bundle_path


class FlightRecordCliTest(CliCase):
    """The `flight-record create/verify` leaves."""

    def test_create_writes_a_bundle_and_reports_the_digest(self):
        self.to_succeeded()
        bundle_path = self.create_bundle()
        out = self.ok("flight-record", "verify", str(bundle_path))
        self.assertIn("OK", out)
        self.assertIn(self.wf, out)
        bundle = json.loads(bundle_path.read_text())
        self.assertIn("canonical_payload", bundle)
        self.assertIn("wrapper", bundle)
        self.assertEqual(bundle["wrapper"]["secret_scan"]["findings"], 0)

    def test_verify_reports_findings_on_a_tampered_bundle(self):
        self.to_succeeded()
        bundle_path = self.create_bundle()
        bundle = json.loads(bundle_path.read_text())
        bundle["canonical_payload"]["workflow_events"][2]["content_sha256"] = \
            "0" * 64
        bundle_path.write_text(json.dumps(bundle))
        result = self.run_cli("flight-record", "verify", str(bundle_path))
        self.assertEqual(result.returncode, 1)
        self.assertIn("digest_divergent", result.stdout)
        self.assertIn("workflow_events", result.stdout)
        self.assertIn("failed verification", result.stdout)

    def test_create_for_a_missing_workflow_is_a_refusal(self):
        err = self.refused("flight-record", "create", "WF-1",
                           "--out", str(self.root / "x.json"), code=2)
        self.assertIn("No workflow", err)

    def test_create_refuses_secret_shaped_journal_data(self):
        self.to_succeeded()
        conn = self.connect()
        row_id = int(self.wf[3:])
        conn.execute(
            "UPDATE events SET payload_json = ? WHERE entity='workflow' "
            "AND entity_id=? AND action='workflow_admitted'",
            (json.dumps({"reason": f"token = {FAKE_SK}"}), row_id),
        )
        conn.commit()
        err = self.refused("flight-record", "create", self.wf,
                           "--out", str(self.root / "x.json"), code=3)
        self.assertIn("secret_in_flight_record", err)
        self.assertNotIn(FAKE_SK, err)
        self.assertFalse((self.root / "x.json").exists())

    def test_eco_defers_create_and_verify_still_works(self):
        self.to_succeeded()
        bundle_path = self.root / "fr.json"
        self.ok("power", "set", "eco")
        out = self.ok("flight-record", "create", self.wf,
                      "--out", str(bundle_path))
        self.assertIn("eco: skipped", out)
        self.assertFalse(bundle_path.exists())
        # Verify is read-only: eco does not touch it.
        self.ok("power", "set", "standard")
        self.ok("flight-record", "verify", str(self.create_bundle()))

    def test_recovery_blocks_create_but_allows_verify(self):
        self.to_succeeded()
        bundle_path = self.create_bundle()
        self.ok("power", "set", "recovery")
        err = self.refused("flight-record", "create", self.wf,
                           "--out", str(self.root / "x.json"))
        self.assertIn("blocked in recovery", err)
        self.assertFalse((self.root / "x.json").exists())
        self.ok("flight-record", "verify", str(bundle_path))


if __name__ == "__main__":
    unittest.main()