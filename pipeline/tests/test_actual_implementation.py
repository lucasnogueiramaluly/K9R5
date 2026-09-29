import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.experiment.actual_implementation import (  # noqa: E402
    CVA6_GENERIC, EVIDENCE_TYPE, SNITCH_GENERIC, SNITCH_TUNED, SPATZ_GENERIC,
    SPATZ_TUNED, annotate_completed_nodes, resolve_actual_implementation,
)
from pipeline.experiment.kernel_implementation_catalog import build_catalog  # noqa: E402


class ActualImplementationTests(unittest.TestCase):

    def resolve(self, engine, op="MatMul", **arguments):
        return resolve_actual_implementation({
            "engine": engine, "op": op, "kernel_arguments": arguments,
        })

    def test_reported_ids_are_catalog_ids(self):
        catalog_ids = {row["id"] for row in build_catalog(ROOT)}
        for implementation_id in (CVA6_GENERIC, SNITCH_TUNED, SNITCH_GENERIC,
                                  SPATZ_TUNED, SPATZ_GENERIC):
            self.assertIn(implementation_id, catalog_ids)

    def test_cva6_completed_matmul_has_compiled_generic_identity(self):
        implementation = resolve_actual_implementation({
            "engine": "cva6", "op": "MatMul",
        })
        self.assertEqual(implementation["implementation_id"], CVA6_GENERIC)
        self.assertFalse(implementation["fallback_used"])
        self.assertEqual(implementation["evidence"]["type"], EVIDENCE_TYPE)

    def test_snitch_tuned_path_and_scalar_tail_are_distinguished(self):
        tuned = self.resolve("snitch", M=2, N=3, O=8)
        gemm = self.resolve("snitch", "Gemm", M=2, N=3, O=8,
                            transA=0, transB=0)
        scalar_tail = self.resolve("snitch", M=2, N=3, O=9)
        self.assertEqual(tuned["implementation_id"], SNITCH_TUNED)
        self.assertFalse(tuned["fallback_used"])
        self.assertEqual(gemm["implementation_id"], SNITCH_TUNED)
        self.assertFalse(gemm["fallback_used"])
        self.assertEqual(scalar_tail["implementation_id"], SNITCH_TUNED)
        self.assertFalse(scalar_tail["fallback_used"])
        self.assertEqual(scalar_tail["implementation_detail"],
                         "scalar_tail_for_remaining_output_columns")

    def test_snitch_source_fallback_conditions_are_reported(self):
        small_output = self.resolve("snitch", M=2, N=3, O=7)
        empty_input = self.resolve("snitch", M=0, N=3, O=8)
        self.assertEqual(small_output["implementation_id"], SNITCH_GENERIC)
        self.assertTrue(small_output["fallback_used"])
        self.assertEqual(small_output["fallback_from"], SNITCH_TUNED)
        self.assertEqual(small_output["fallback_to"], SNITCH_GENERIC)
        self.assertEqual(small_output["fallback_reason"],
                         "output_columns_below_ssr_unroll")
        self.assertEqual(empty_input["fallback_reason"], "empty_input_dimension")

    def test_spatz_tuned_and_source_fallback_paths_are_reported(self):
        matmul = self.resolve("spatz", M=2, N=3, O=4)
        gemm = self.resolve("spatz", "Gemm", M=2, N=3, O=4,
                            transA=0, transB=0)
        transpose = self.resolve("spatz", "Gemm", M=2, N=3, O=4,
                                 transA=1, transB=0)
        empty = self.resolve("spatz", M=2, N=0, O=4)
        self.assertEqual(matmul["implementation_id"], SPATZ_TUNED)
        self.assertEqual(gemm["implementation_id"], SPATZ_TUNED)
        self.assertFalse(gemm["fallback_used"])
        self.assertEqual(transpose["implementation_id"], SPATZ_GENERIC)
        self.assertEqual(transpose["fallback_from"], SPATZ_TUNED)
        self.assertEqual(transpose["fallback_to"], SPATZ_GENERIC)
        self.assertEqual(transpose["fallback_reason"], "transposed_operand")
        self.assertEqual(empty["fallback_reason"], "empty_dimension")

    def test_missing_or_unsupported_evidence_stays_unknown(self):
        missing = resolve_actual_implementation({"engine": "spatz", "op": "MatMul"})
        unsupported = self.resolve("spatz", "Conv", M=2, N=3, O=4)
        incomplete_gemm = self.resolve("spatz", "Gemm", M=2, N=3, O=4)
        for implementation in (missing, unsupported, incomplete_gemm):
            self.assertIsNone(implementation["implementation_id"])
            self.assertIsNone(implementation["fallback_used"])
            self.assertEqual(implementation["evidence"]["type"], "unavailable")

    def test_completed_beacons_are_joined_by_generated_runtime_index(self):
        mapping = {"nodes": [{
            "index": 4, "node": "gemm_0", "op": "Gemm", "engine": "spatz",
            "kernel_arguments": {"M": 2, "N": 3, "O": 4,
                                 "transA": 0, "transB": 0},
        }]}
        result = {"nodes": [{
            "node": 4, "op": "Gemm", "engine": "spatz", "cycles": 99,
        }]}
        annotate_completed_nodes(mapping, result)
        actual = result["nodes"][0]
        self.assertEqual(actual["cycles"], 99)
        self.assertEqual(actual["implementation"]["implementation_id"], SPATZ_TUNED)

    def test_disagreeing_generated_and_runtime_records_stay_unknown(self):
        mapping = {"nodes": [{
            "index": 0, "node": "matmul_0", "op": "MatMul", "engine": "spatz",
            "kernel_arguments": {"M": 2, "N": 3, "O": 4},
        }]}
        result = {"nodes": [{
            "node": 0, "op": "MatMul", "engine": "snitch", "cycles": 1,
        }]}
        annotate_completed_nodes(mapping, result)
        implementation = result["nodes"][0]["implementation"]
        self.assertIsNone(implementation["implementation_id"])
        self.assertEqual(implementation["evidence"]["type"], "unavailable")


if __name__ == "__main__":
    unittest.main()
