import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.experiment.run_manifest import build_run_manifest, write_run_manifest  # noqa: E402


class RunManifestTests(unittest.TestCase):
    def fixture(self, root: Path):
        calibration = root / "calibration.json"
        result = root / "result.json"
        calibration.write_text(json.dumps({
            "schema_version": 1,
            "kind": "k9r5.calibration",
            "input_fingerprint": "sha256:calibration",
            "provenance": {"k9r5": {"available": False}},
        }) + "\n")
        result.write_text(json.dumps({
            "mapping": {"nodes": [{"node": "x", "engine": "spatz"}]},
            "result": {"status": "ok", "cycles": 123},
        }) + "\n")
        return calibration, result

    def test_manifest_records_request_resolved_actual_and_calibration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calibration, result = self.fixture(root)
            manifest = build_run_manifest(
                request={"design": {}, "host": "cva6"},
                resolved={"design_slug": "baseline"},
                actual={"status": "ok", "mapping": {"nodes": []}},
                calibration_path=calibration,
                result_path=result,
                base_dir=root,
            )
            self.assertEqual(manifest["kind"], "k9r5.run")
            self.assertEqual(manifest["calibration"]["input_fingerprint"], "sha256:calibration")
            self.assertEqual(manifest["artifacts"]["result"]["path"], "result.json")
            self.assertEqual(manifest["provenance"]["k9r5"]["available"], False)
            self.assertTrue(manifest["run_fingerprint"].startswith("sha256:"))

    def test_actual_execution_changes_run_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calibration, result = self.fixture(root)
            common = dict(
                request={"design": {}, "host": "cva6"},
                resolved={"design_slug": "baseline"},
                calibration_path=calibration,
                result_path=result,
                base_dir=root,
            )
            a = build_run_manifest(actual={"status": "ok", "cycles": 123}, **common)
            b = build_run_manifest(actual={"status": "ok", "cycles": 456}, **common)
            self.assertNotEqual(a["run_fingerprint"], b["run_fingerprint"])

    def test_actual_mapping_and_implementation_evidence_are_serialized(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calibration, result = self.fixture(root)
            actual = {
                "mapping": {"nodes": [{
                    "mapping_explanation": {
                        "strategy": "measured_rate_greedy",
                        "selected_engine": "spatz",
                    },
                }]},
                "result": {"nodes": [{
                    "node": 0,
                    "implementation": {
                        "implementation_id": "spatz.fp32.matmul_gemm.rvv_tuned",
                        "fallback_used": False,
                        "evidence": {
                            "type": "deterministic_compiled_dispatch_and_runtime_evidence",
                        },
                    },
                }]},
            }
            manifest = build_run_manifest(
                request={"design": {}, "host": "cva6"},
                resolved={"design_slug": "baseline"}, actual=actual,
                calibration_path=calibration, result_path=result, base_dir=root,
            )
            self.assertEqual(manifest["actual"], actual)

    def test_writer_emits_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calibration, result = self.fixture(root)
            out = root / "manifest.json"
            written = write_run_manifest(
                out,
                request={"model": "Regular"},
                resolved={"design_slug": "baseline"},
                actual={"status": "ok"},
                calibration_path=calibration,
                result_path=result,
                base_dir=root,
            )
            self.assertEqual(json.loads(out.read_text()), written)


if __name__ == "__main__":
    unittest.main()
