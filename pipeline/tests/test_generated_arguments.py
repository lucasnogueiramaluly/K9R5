import unittest

from pipeline.experiment.generated_arguments import emitted_kernel_arguments


class _Parser:
    def __init__(self, representation):
        self.operatorRepresentation = representation


class _Mapper:
    def __init__(self, representation):
        self.parser = _Parser(representation)


class _Layer:
    def __init__(self, representation):
        self.mapper = _Mapper(representation)


class GeneratedKernelArgumentsTests(unittest.TestCase):

    def test_matmul_reads_selected_parser_representation(self):
        layer = _Layer({
            "M": 32, "N": 64, "O": 16,
            "A": "input", "B": "weights", "data_out": "output",
        })
        self.assertEqual(
            emitted_kernel_arguments(layer, "MatMul"),
            {"M": 32, "N": 64, "O": 16},
        )

    def test_gemm_keeps_transpose_dispatch_arguments(self):
        layer = _Layer({
            "M": 16, "N": 64, "O": 32,
            "transA": 0, "transB": 1,
        })
        self.assertEqual(
            emitted_kernel_arguments(layer, "Gemm"),
            {"M": 16, "N": 64, "O": 32, "transA": 0, "transB": 1},
        )

    def test_missing_or_non_integer_evidence_is_not_invented(self):
        layer = _Layer({"M": 2, "N": "dynamic", "O": 8, "transA": False})
        self.assertEqual(
            emitted_kernel_arguments(layer, "Gemm"),
            {"M": 2, "O": 8},
        )

    def test_unsupported_operator_has_no_kernel_argument_contract(self):
        self.assertIsNone(emitted_kernel_arguments(_Layer({"M": 1}), "Conv"))


if __name__ == "__main__":
    unittest.main()
