import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline" / "sweep"))

import design as design_mod  # noqa: E402
from pipeline.experiment.resolve import resolve_experiment  # noqa: E402
from pipeline.experiment.schema import ExperimentRequest  # noqa: E402

HOST_PROFILES = {
    "cva6": {"target": "hetero_soc", "logical_engine": "cva6", "vector": False},
    "ara": {"target": "hetero_ara", "logical_engine": "cva6", "vector": True},
}


def _model(path: Path) -> Path:
    a = helper.make_tensor_value_info("A", TensorProto.FLOAT, [2, 3])
    y = helper.make_tensor_value_info("Y", TensorProto.FLOAT, [2, 4])
    b = numpy_helper.from_array(np.ones((3, 4), dtype=np.float32), name="B")
    node = helper.make_node("MatMul", ["A", "B"], ["Y"])
    graph = helper.make_graph([node], "g", [a], [y], [b])
    onnx.save(helper.make_model(graph, opset_imports=[helper.make_opsetid("", 13)]), path)
    return path


class ResolveExperimentTests(unittest.TestCase):
    def resolve(self, request, model):
        return resolve_experiment(
            request,
            design_api=design_mod,
            host_profiles=HOST_PROFILES,
            workload_path=model,
        )

    def test_current_platform_resolves_current_design_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _model(Path(tmp) / "network.onnx")
            resolved = self.resolve(ExperimentRequest(workload=str(model)), model)
        self.assertEqual(resolved.platform, "k9r5_current")
        self.assertEqual(resolved.hardware["design"], design_mod.DEFAULTS)
        self.assertEqual(resolved.hardware["design_slug"], "baseline")
        self.assertEqual(resolved.host_profile, "cva6")
        self.assertEqual(resolved.simulator["target"], "hetero_soc")
        self.assertEqual(resolved.mapping["strategy"], "measured_rate_greedy")
        self.assertEqual(resolved.resources["clusters"]["snitch"]["compute_cores"], 8)
        self.assertEqual(resolved.resources["clusters"]["spatz"]["spatz_vector"]["useful_vector_lanes"], 32)

    def test_override_changes_resolved_hardware_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _model(Path(tmp) / "network.onnx")
            base = self.resolve(ExperimentRequest(workload=str(model)), model)
            changed = self.resolve(
                ExperimentRequest(workload=str(model), design_overrides=(("SPATZ_NB_LANES", 8),)),
                model,
            )
        self.assertEqual(changed.hardware["design"]["SPATZ_NB_LANES"], 8)
        self.assertNotEqual(base.hardware["fingerprint"], changed.hardware["fingerprint"])

    def test_unknown_knob_is_rejected_by_existing_design_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _model(Path(tmp) / "network.onnx")
            with self.assertRaisesRegex(ValueError, "unknown design keys"):
                self.resolve(
                    ExperimentRequest(workload=str(model), design_overrides=(("NOT_A_KNOB", 1),)),
                    model,
                )

    def test_invalid_design_is_rejected_by_existing_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _model(Path(tmp) / "network.onnx")
            with self.assertRaisesRegex(ValueError, "invalid design"):
                self.resolve(
                    ExperimentRequest(workload=str(model), design_overrides=(("SPATZ_NB_LANES", 3),)),
                    model,
                )

    def test_unknown_host_strategy_and_pin_are_explicit_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = _model(Path(tmp) / "network.onnx")
            with self.subTest("host"):
                with self.assertRaisesRegex(ValueError, "unknown host profile"):
                    self.resolve(ExperimentRequest(workload=str(model), host="future"), model)
            with self.subTest("strategy"):
                with self.assertRaisesRegex(ValueError, "unknown mapping strategy"):
                    self.resolve(ExperimentRequest(workload=str(model), mapping_strategy="future"), model)
            with self.subTest("pin"):
                with self.assertRaisesRegex(ValueError, "unknown pinned engine"):
                    self.resolve(ExperimentRequest(workload=str(model), pin="ara"), model)


if __name__ == "__main__":
    unittest.main()
