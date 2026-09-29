import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.experiment.kernel_implementation_catalog import build_catalog  # noqa: E402


class KernelImplementationCatalogTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rows = build_catalog(ROOT)
        cls.by_id = {row["id"]: row for row in cls.rows}

    def test_stable_current_implementation_ids(self):
        self.assertEqual(
            [row["id"] for row in self.rows],
            [
                "cva6.fp32.matmul_gemm.deeploy_generic",
                "snitch.fp32.matmul_gemm.ssr_frep",
                "snitch.fp32.matmul_gemm.deeploy_generic_fallback",
                "spatz.fp32.matmul_gemm.rvv_tuned",
                "spatz.fp32.matmul_gemm.deeploy_generic_fallback",
            ],
        )

    def test_snitch_and_spatz_entries_describe_current_symbols_and_sources(self):
        for implementation_id in (
            "snitch.fp32.matmul_gemm.ssr_frep",
            "spatz.fp32.matmul_gemm.rvv_tuned",
        ):
            row = self.by_id[implementation_id]
            self.assertEqual(row["operators"], ["MatMul", "Gemm"])
            self.assertEqual(row["build_selection"]["selector"], "-D<symbol>=<symbol>_generic")
            source = ROOT / row["source_file"]
            self.assertTrue(source.is_file())
            text = source.read_text()
            for symbol in row["symbols"]:
                self.assertIn(f"{symbol}(", text)

    def test_known_fallback_relationships_and_conditions_are_explicit(self):
        snitch = self.by_id["snitch.fp32.matmul_gemm.ssr_frep"]
        spatz = self.by_id["spatz.fp32.matmul_gemm.rvv_tuned"]
        self.assertEqual(snitch["fallback_id"], "snitch.fp32.matmul_gemm.deeploy_generic_fallback")
        self.assertEqual(spatz["fallback_id"], "spatz.fp32.matmul_gemm.deeploy_generic_fallback")
        self.assertIn("O >= 8", snitch["compatibility_conditions"]["optimized_entry"])
        self.assertIn("transA == 0", spatz["compatibility_conditions"]["gemm_optimized_entry"])

    def test_generic_source_file_and_compatibility_stay_unknown_when_unavailable(self):
        generic = self.by_id["cva6.fp32.matmul_gemm.deeploy_generic"]
        self.assertIsNone(generic["source_file"])
        self.assertIsNone(generic["compatibility_conditions"])
        self.assertEqual(generic["source_tree"], "deps/deeploy/TargetLibraries/Generic/src")

    def test_catalog_is_deterministic_and_refuses_first_party_source_drift(self):
        self.assertEqual(self.rows, build_catalog(ROOT))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "source is missing"):
                build_catalog(Path(tmp))


if __name__ == "__main__":
    unittest.main()
