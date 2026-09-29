import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.experiment.workload import inspect_workload, workload_to_legacy_inspect  # noqa: E402


def _write_matmul(path: Path, dynamic: bool = False) -> Path:
    a_shape = [None, 3] if dynamic else [2, 3]
    y_shape = [None, 4] if dynamic else [2, 4]
    a = helper.make_tensor_value_info("A", TensorProto.FLOAT, a_shape)
    y = helper.make_tensor_value_info("Y", TensorProto.FLOAT, y_shape)
    weights = np.array([[0, 1, 0, 1], [0, 1, 0, 1], [0, 1, 0, 1]], dtype=np.float32)
    b = numpy_helper.from_array(weights, name="B")
    node = helper.make_node("MatMul", ["A", "B"], ["Y"], name="matmul")
    graph = helper.make_graph([node], "g", [a], [y], [b])
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)])
    onnx.save(model, path)
    return path


class WorkloadSpecTests(unittest.TestCase):
    def test_static_matmul_has_safe_research_descriptors(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = inspect_workload(_write_matmul(Path(tmp) / "network.onnx"))
        d = spec.descriptors
        self.assertEqual(d["estimated_macs"]["value"], 24)
        self.assertTrue(d["estimated_macs"]["complete_for_covered_ops"])
        self.assertEqual(d["static_tensor_bytes"]["known_bytes"], 104)
        self.assertTrue(d["static_tensor_bytes"]["complete"])
        self.assertEqual(d["working_set"]["max_static_node_bytes"], 104)
        self.assertAlmostEqual(d["theoretical_arithmetic_intensity"]["mac_per_byte"], 24 / 104)

    def test_dynamic_shape_stays_unknown_instead_of_zero_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = inspect_workload(_write_matmul(Path(tmp) / "network.onnx", dynamic=True))
        d = spec.descriptors
        self.assertFalse(d["static_tensor_bytes"]["complete"])
        self.assertGreater(len(d["static_tensor_bytes"]["unknown_tensors"]), 0)
        self.assertEqual(d["working_set"]["unknown_nodes"], [0])
        self.assertIsNone(d["working_set"]["max_static_node_bytes"])
        self.assertEqual(d["estimated_macs"]["unknown_nodes"], [0])
        self.assertIsNone(d["theoretical_arithmetic_intensity"]["mac_per_byte"])

    def test_initializer_sparsity_is_descriptive_not_capability(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = inspect_workload(_write_matmul(Path(tmp) / "network.onnx"))
        s = spec.descriptors["initializer_sparsity"]
        self.assertEqual(s["elements"], 12)
        self.assertEqual(s["zero_elements"], 6)
        self.assertAlmostEqual(s["zero_fraction"], 0.5)
        self.assertIn("no claim", s["scope"])

    def test_legacy_gui_inspect_surface_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            spec = inspect_workload(_write_matmul(Path(tmp) / "network.onnx"), application="demo")
        legacy = workload_to_legacy_inspect(spec)
        self.assertEqual(
            set(legacy),
            {"path", "opset", "inputs", "outputs", "nodes", "op_types", "initializers", "app"},
        )
        self.assertEqual(legacy["nodes"], 1)
        self.assertEqual(legacy["op_types"], {"MatMul": 1})
        self.assertEqual(legacy["app"], "demo")


if __name__ == "__main__":
    unittest.main()
