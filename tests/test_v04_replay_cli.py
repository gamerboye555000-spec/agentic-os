"""U-E6 replay CLI (agentic-os-v0.4-u-e6-flight-recorder-replay-contract.md
§5, §7, §11).

Drives the REAL `aos.py` entrypoint through the `replay` leaf (a single-level
command with `--resimulate` as a flag on the same leaf): the byte-identical
trace, re-simulation declarations, the counterfactual removal, and the
exit-code contract for malformed substitution files and tampered bundles.
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
        "idempotency_key": "ue6rcli-0001",
        "aos_task_id": "T-0001",
        "data_classification": "internal",
        "permitted_destinations": ["aos-ledger", "local"],
        "work_spec_id": "11111111-1111-4111-8111-111111111111",
        "goal": "Replay the U-E6 history from the CLI.",
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
        "idempotency_key": "ue6rcli-0002",
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
                "ref": "notes/ue6-rcli",
                "claim": "The replay CLI printed the identical trace.",
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
        self.ok("task", "add", "carry the replay CLI", "-p", "demo")
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

    def write_doc(self, name: str, document: dict) -> str:
        path = self.root / name
        path.write_bytes(protocols.serialize_canonical_file_bytes(document))
        return str(path)

    def to_dispatched(self):
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

    def to_succeeded(self):
        self.to_dispatched()
        self.ok("workflow", "receipt", self.wf, self.write_doc("s.json",
                    receipt("started", self.artifact, receipt_id=902)))
        self.ok("workflow", "result", self.wf,
                self.write_doc("r.json", result_envelope(self.artifact)))

    def create_bundle(self) -> Path:
        bundle_path = self.root / "flight-record.json"
        self.ok("flight-record", "create", self.wf, "--out",
                str(bundle_path))
        return bundle_path


class ReplayCliTest(CliCase):
    """The `replay` leaf."""

    def test_replay_of_a_happy_path_bundle_is_byte_identical(self):
        self.to_succeeded()
        out = self.ok("replay", str(self.create_bundle()))
        self.assertIn("byte_identical True", out)
        self.assertIn("final_state succeeded", out)
        self.assertIn("workflow_succeeded", out)

    def test_replay_reports_divergence_on_a_revision_that_cannot_fold(self):
        self.to_dispatched()
        bundle_path = self.create_bundle()
        out = self.ok("replay", str(bundle_path))
        self.assertIn("byte_identical True", out)
        self.assertIn("final_state scheduled", out)

    def test_resimulate_retry_max_attempts_appears_in_the_trace(self):
        self.to_succeeded()
        substitutions = self.root / "subst.json"
        substitutions.write_text(json.dumps({"retry_max_attempts": 3}))
        out = self.ok("replay", str(self.create_bundle()),
                      "--resimulate", str(substitutions))
        self.assertIn("attempt_budget 3", out)
        self.assertIn("declared substitution: "
                      "{'kind': 'retry_max_attempts', 'value': 3}", out)

    def test_resimulate_removed_event_seq_never_reaches_running(self):
        self.to_dispatched()
        substitutions = self.root / "subst.json"
        substitutions.write_text(json.dumps({"removed_event_seq": 4}))
        out = self.ok("replay", str(self.create_bundle()),
                      "--resimulate", str(substitutions))
        self.assertIn("final_state validated", out)
        self.assertIn("substitution applied: "
                      "{'kind': 'removed_event_seq', 'seq': 4}", out)

    def test_malformed_substitution_file_is_a_refusal(self):
        self.to_succeeded()
        substitutions = self.root / "subst.json"
        substitutions.write_text(json.dumps({"bogus_key": 1}))
        result = self.run_cli("replay", str(self.create_bundle()),
                              "--resimulate", str(substitutions))
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("Unknown substitution key", result.stderr)

    def test_replay_of_a_tampered_bundle_refuses(self):
        self.to_succeeded()
        bundle_path = self.create_bundle()
        import json as _json

        bundle = _json.loads(bundle_path.read_text())
        bundle["canonical_payload"]["workflow_events"][2]["content_sha256"] = \
            "0" * 64
        bundle_path.write_text(_json.dumps(bundle))
        result = self.run_cli("replay", str(bundle_path))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("integrity verification", result.stderr)


if __name__ == "__main__":
    unittest.main()