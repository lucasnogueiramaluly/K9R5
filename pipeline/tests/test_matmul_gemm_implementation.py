import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.experiment.matmul_gemm_implementation import (  # noqa: E402
    SNITCH_GENERIC, SNITCH_TUNED, SPATZ_GENERIC, SPATZ_TUNED,
    resolve_matmul_gemm_implementation,
)


class MatMulGemmImplementationTests(unittest.TestCase):

    def resolve(self, *args, **kwargs):
        return resolve_matmul_gemm_implementation(*args, **kwargs)

    def test_snitch_fallback_and_scalar_tail_conditions(self):
        self.assertEqual(self.resolve("snitch", "MatMul", 2, 3, 7)["implementation_id"],
                         SNITCH_GENERIC)
        self.assertEqual(self.resolve("snitch", "MatMul", 2, 3, 8)["implementation_id"],
                         SNITCH_TUNED)
        tail = self.resolve("snitch", "MatMul", 2, 3, 9)
        self.assertEqual(tail["implementation_id"], SNITCH_TUNED)
        self.assertEqual(tail["implementation_detail"],
                         "scalar_tail_for_remaining_output_columns")

    def test_spatz_transpose_and_unknown_conditions(self):
        self.assertEqual(self.resolve("spatz", "Gemm", 2, 3, 4, transA=1)["implementation_id"],
                         SPATZ_GENERIC)
        self.assertEqual(self.resolve("spatz", "Gemm", 2, 3, 4, transA=0, transB=0)["implementation_id"],
                         SPATZ_TUNED)
        unknown = self.resolve("spatz", "Gemm", None, 3, 4)
        self.assertIsNone(unknown["implementation_id"])
        self.assertIsNotNone(unknown["unknown_reason"])


if __name__ == "__main__":
    unittest.main()
