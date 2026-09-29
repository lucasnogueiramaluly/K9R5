import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

import gui_query  # noqa: E402


def _model(path: Path) -> Path:
    a = helper.make_tensor_value_info("A", TensorProto.FLOAT, [2, 3])
    y = helper.make_tensor_value_info("Y", TensorProto.FLOAT, [2, 4])
    b = numpy_helper.from_array(np.ones((3, 4), dtype=np.float32), name="B")
    node = helper.make_node("MatMul", ["A", "B"], ["Y"])
    graph = helper.make_graph([node], "g", [a], [y], [b])
    onnx.save(helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)]), path)
    return path


class GuiExperimentInterfaceTests(unittest.TestCase):
    def test_experiment_schema_exposes_current_surfaces(self):
        out = gui_query.cmd_experiment_schema(SimpleNamespace())
        self.assertIn("parameters", out)
        self.assertEqual({x["name"] for x in out["engines"]}, {"cva6", "snitch", "spatz"})
        self.assertEqual({x["name"] for x in out["host_profiles"]}, {"cva6", "ara"})
        self.assertEqual({x["id"] for x in out["mapping_strategies"]}, {"measured_rate_greedy"})
        self.assertEqual(out["presets"], ["k9r5_current"])

    def test_resolve_experiment_command_returns_resolved_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            model = _model(tmp / "network.onnx")
            request = tmp / "request.json"
            request.write_text(json.dumps({
                "workload": str(model),
                "design_overrides": {"SPATZ_NB_LANES": 8},
                "host": "ara",
            }))
            out = gui_query.cmd_resolve_experiment(SimpleNamespace(request=str(request)))

        self.assertEqual(out["platform"], "k9r5_current")
        self.assertEqual(out["hardware"]["design"]["SPATZ_NB_LANES"], 8)
        self.assertEqual(out["host_profile"], "ara")
        self.assertEqual(out["simulator"]["target"], "hetero_ara")
        self.assertEqual(out["mapping"]["strategy"], "measured_rate_greedy")
        self.assertEqual(out["workload"]["path"], str(model))
        self.assertEqual(out["resources"]["clusters"]["spatz"]["spatz_vector"]["useful_vector_lanes"], 64)


if __name__ == "__main__":
    unittest.main()
