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

    def test_manifest_records_four_execution_sections_and_calibration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calibration, result = self.fixture(root)
            manifest = build_run_manifest(
                request={"design": {}, "host": "cva6"},
                resolved={"design_slug": "baseline"},
                actual={"mapping": {"nodes": []}},
                measured={"status": "ok", "cycles": 123},
                calibration_path=calibration,
                result_path=result,
                base_dir=root,
                source_root=root,
            )
            self.assertEqual(manifest["kind"], "k9r5.run")
            self.assertEqual(manifest["schema_version"], 2)
            self.assertEqual(set(("request", "resolved", "actual", "measured")),
                             {key for key in manifest if key in {"request", "resolved", "actual", "measured"}})
            self.assertEqual(manifest["measured"]["cycles"], 123)
            self.assertNotIn("cycles", manifest["actual"])
            self.assertEqual(manifest["calibration"]["input_fingerprint"], "sha256:calibration")
            self.assertEqual(manifest["artifacts"]["result"]["path"], "result.json")
            self.assertEqual(manifest["calibration_provenance"]["k9r5"]["available"], False)
            self.assertFalse(manifest["run_provenance"]["k9r5"]["available"])
            self.assertIn("digest", manifest["run_provenance"]["source_set"])
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
            a = build_run_manifest(actual={"mapping": {}}, measured={"cycles": 123}, **common)
            b = build_run_manifest(actual={"mapping": {}}, measured={"cycles": 456}, **common)
            self.assertNotEqual(a["run_fingerprint"], b["run_fingerprint"])

    def test_manifest_serialization_and_fingerprint_are_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calibration, result = self.fixture(root)
            kwargs = dict(
                request={"host": "cva6"}, resolved={"design_slug": "baseline"},
                actual={"mapping": {"nodes": []}}, measured={"cycles": 123},
                calibration_path=calibration, result_path=result, base_dir=root,
                source_root=root,
            )
            first = build_run_manifest(**kwargs)
            second = build_run_manifest(**kwargs)
        self.assertEqual(first, second)

    def test_selected_run_source_changes_identity_but_readme_does_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calibration, result = self.fixture(root)
            source = root / "pipeline" / "run_hetero.py"
            source.parent.mkdir()
            source.write_text("first source\n")
            (root / "README.md").write_text("first readme\n")
            kwargs = dict(
                request={}, resolved={}, actual={}, measured={},
                calibration_path=calibration, result_path=result, base_dir=root,
                source_root=root,
            )
            first = build_run_manifest(**kwargs)
            (root / "README.md").write_text("changed readme\n")
            readme_only = build_run_manifest(**kwargs)
            source.write_text("changed source\n")
            source_changed = build_run_manifest(**kwargs)
        self.assertEqual(first["run_fingerprint"], readme_only["run_fingerprint"])
        self.assertNotEqual(first["run_fingerprint"], source_changed["run_fingerprint"])

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
            self.assertEqual(manifest["actual"], {"mapping": actual["mapping"]})
            self.assertEqual(manifest["measured"], actual["result"])

    def test_legacy_actual_result_normalizes_to_single_measured_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            calibration, result = self.fixture(root)
            manifest = build_run_manifest(
                request={}, resolved={}, actual={"mapping": {}, "result": {"cycles": 3}},
                calibration_path=calibration, result_path=result, base_dir=root,
            )
            self.assertEqual(manifest["measured"], {"cycles": 3})
            self.assertNotIn("result", manifest["actual"])

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
