"""U-E6 incident forensics CLI (agentic-os-v0.4-u-e6-flight-recorder-replay-
contract.md §5, §7, §11).

Drives the REAL `aos.py` entrypoint through the `incident create/export`
leaves: the report write, the four-file export into an EMPTY directory, the
empty-directory refusal, the missing-workflow refusal, the eco deferral and
the recovery block. Both leaves are DERIVED_WRITE with respect to aos.db.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from agentic_os import (  # noqa: E402
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
        "idempotency_key": "ue6icli-0001",
        "aos_task_id": "T-0001",
        "data_classification": "internal",
        "permitted_destinations": ["aos-ledger", "local"],
        "work_spec_id": "11111111-1111-4111-8111-111111111111",
        "goal": "Export the U-E6 incident bundle from the CLI.",
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
        "idempotency_key": "ue6icli-0002",
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
                "ref": "notes/ue6-icli",
                "claim": "The incident CLI exported the four-file bundle.",
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
        self.ok("task", "add", "carry the incident CLI", "-p", "demo")
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


class IncidentCliTest(CliCase):
    """The `incident create/export` leaves."""

    def test_create_writes_the_report(self):
        self.to_succeeded()
        out_path = self.root / "incident.json"
        out = self.ok("incident", "create", self.wf, "--out", str(out_path))
        self.assertIn("wrote incident report", out)
        self.assertTrue(out_path.is_file())
        document = json.loads(out_path.read_text())
        self.assertEqual(document["schema"], "aos.incident-report/v1")
        self.assertEqual(document["workflow_id"], self.wf)

    def test_export_writes_the_four_files_into_an_empty_dir(self):
        self.to_succeeded()
        out_dir = self.root / "outbox"
        out_dir.mkdir()
        out = self.ok("incident", "export", self.wf, "--out", str(out_dir))
        self.assertIn("4 file(s)", out)
        names = sorted(p.name for p in out_dir.iterdir())
        self.assertEqual(
            names,
            ["flight-record.json", "incident.json", "observability.json",
             "verification.json"],
        )
        self.assertEqual(
            json.loads((out_dir / "incident.json").read_text())["schema"],
            "aos.incident-report/v1",
        )

    def test_export_refuses_a_non_empty_directory(self):
        self.to_succeeded()
        out_dir = self.root / "outbox"
        out_dir.mkdir()
        (out_dir / "existing.txt").write_text("do not merge")
        err = self.refused("incident", "export", self.wf, "--out",
                           str(out_dir), code=2)
        self.assertIn("not empty", err)

    def test_export_refuses_a_file_path(self):
        self.to_succeeded()
        target = self.root / "not-a-dir"
        target.write_text("occupied")
        err = self.refused("incident", "export", self.wf, "--out",
                           str(target), code=2)
        self.assertIn("Not an existing directory", err)

    def test_create_for_a_missing_workflow_is_a_refusal(self):
        err = self.refused("incident", "create", "WF-1",
                           "--out", str(self.root / "x.json"), code=2)
        self.assertIn("No workflow", err)
        self.assertFalse((self.root / "x.json").exists())

    def test_eco_defers_both_leaves(self):
        self.to_succeeded()
        self.ok("power", "set", "eco")
        out_dir = self.root / "outbox"
        out_dir.mkdir()
        out = self.ok("incident", "create", self.wf,
                      "--out", str(self.root / "i.json"))
        self.assertIn("eco: skipped", out)
        out = self.ok("incident", "export", self.wf, "--out", str(out_dir))
        self.assertIn("eco: skipped", out)
        self.assertFalse((self.root / "i.json").exists())
        self.assertEqual(list(out_dir.iterdir()), [])

    def test_recovery_blocks_both_leaves(self):
        self.to_succeeded()
        self.ok("power", "set", "recovery")
        out_dir = self.root / "outbox"
        out_dir.mkdir()
        err = self.refused("incident", "create", self.wf,
                           "--out", str(self.root / "i.json"))
        self.assertIn("blocked in recovery", err)
        err = self.refused("incident", "export", self.wf, "--out",
                           str(out_dir))
        self.assertIn("blocked in recovery", err)
        self.assertFalse((self.root / "i.json").exists())
        self.assertEqual(list(out_dir.iterdir()), [])


if __name__ == "__main__":
    unittest.main()