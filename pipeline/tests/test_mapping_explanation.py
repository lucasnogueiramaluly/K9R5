import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAPPER_PATH = ROOT / "pipeline" / "hetero_platform" / "mapper.py"


class FakeEngine:
    def __init__(self, name, compatible=True, mapping=None):
        self.name = name
        self.compatible = compatible
        self.Mapping = mapping or {"MatMul": object(), "Gemm": object(), "Conv": object()}

    def canExecute(self, _node):
        return self.compatible


class FakeCluster(FakeEngine):
    def __init__(self, name, compatible=True, enabled=True, budget=4096, mapping=None):
        super().__init__(name, compatible, mapping)
        self.enabled = enabled
        self.tcdm_budget = budget


class FakeNode:
    def __init__(self, name="node", op="MatMul", fp32=True, bytes_staged=48):
        self.name = name
        self.op = op
        self.fp32 = fp32
        self.bytes_staged = bytes_staged
        self.inputs = [types.SimpleNamespace(shape=[2, 3]),
                       types.SimpleNamespace(shape=[3, 8])]
        self.outputs = [types.SimpleNamespace(shape=[2, 8])]
        self.attrs = {}


def load_mapper():
    names = [
        "onnx_graphsurgeon", "Deeploy", "Deeploy.DeeployTypes",
        "Deeploy.EngineExtension",
        "Deeploy.EngineExtension.OptimizationPasses",
        "Deeploy.EngineExtension.OptimizationPasses.TopologyOptimizationPasses",
        "Deeploy.EngineExtension.OptimizationPasses.TopologyOptimizationPasses.EngineColoringPasses",
        "pipeline.hetero_platform.engines",
        "pipeline.hetero_platform.mapper_mapping_explanation_test",
    ]
    saved = {name: sys.modules.get(name) for name in names}
    gs = types.ModuleType("onnx_graphsurgeon")
    gs.Node = object
    gs.Graph = object
    types_mod = types.ModuleType("Deeploy.DeeployTypes")
    types_mod.DeploymentEngine = object
    mapper_mod = types.ModuleType(
        "Deeploy.EngineExtension.OptimizationPasses.TopologyOptimizationPasses.EngineColoringPasses"
    )

    class EngineMapper:
        def __init__(self, engine_dict):
            self.engineDict = engine_dict

    mapper_mod.EngineMapper = EngineMapper
    engines = types.ModuleType("pipeline.hetero_platform.engines")
    engines.ClusterEngine = FakeCluster
    engines.working_set_bytes = lambda node: node.bytes_staged
    engines._all_fp32 = lambda node: node.fp32
    sys.modules.update({
        "onnx_graphsurgeon": gs,
        "Deeploy": types.ModuleType("Deeploy"),
        "Deeploy.DeeployTypes": types_mod,
        "Deeploy.EngineExtension": types.ModuleType("Deeploy.EngineExtension"),
        "Deeploy.EngineExtension.OptimizationPasses": types.ModuleType("Deeploy.EngineExtension.OptimizationPasses"),
        "Deeploy.EngineExtension.OptimizationPasses.TopologyOptimizationPasses": types.ModuleType("Deeploy.EngineExtension.OptimizationPasses.TopologyOptimizationPasses"),
        mapper_mod.__name__: mapper_mod,
        engines.__name__: engines,
    })
    spec = importlib.util.spec_from_file_location(
        "pipeline.hetero_platform.mapper_mapping_explanation_test", MAPPER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module, saved, names


class MappingExplanationTests(unittest.TestCase):

    def setUp(self):
        self.mapper_mod, self.saved, self.names = load_mapper()

    def tearDown(self):
        for name in self.names:
            prior = self.saved[name]
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior

    def mapper(self, pin=None):
        engines = {
            "cva6": FakeEngine("cva6"),
            "snitch": FakeCluster("snitch"),
            "spatz": FakeCluster("spatz"),
        }
        return self.mapper_mod.CostEngineMapper(engines, pin=pin), engines

    def test_auto_selection_is_unchanged_and_explained(self):
        mapper, engines = self.mapper()
        node = FakeNode()
        expected = min((engine for engine in engines.values()
                        if mapper.cost(engine, node) is not None),
                       key=lambda engine: mapper.cost(engine, node))
        self.assertIs(mapper.mapNodeToEngine(node, None), expected)
        explanation = mapper.explanations[-1]
        self.assertEqual(explanation["strategy"], "measured_rate_greedy")
        self.assertEqual(explanation["selected_engine"], expected.name)
        self.assertEqual(len(explanation["candidates"]), 3)
        spatz = next(row for row in explanation["candidates"] if row["engine"] == "spatz")
        self.assertTrue(spatz["compatible"])
        self.assertEqual(spatz["cost"]["rate_key"], "MatMul")
        self.assertEqual(spatz["cost"]["rate_row"]["kind"], "engine_rate_row")
        self.assertIsNotNone(spatz["cost"]["transfer_offload_cycles"])

    def test_pin_filters_compatible_candidates_without_changing_pin_selection(self):
        mapper, engines = self.mapper(pin="snitch")
        self.assertIs(mapper.mapNodeToEngine(FakeNode(), None), engines["snitch"])
        rows = {row["engine"]: row for row in mapper.explanations[-1]["candidates"]}
        self.assertTrue(rows["snitch"]["candidate_after_pin"])
        self.assertEqual(rows["snitch"]["pin_influence"], "retained_by_pin")
        self.assertFalse(rows["spatz"]["candidate_after_pin"])
        self.assertEqual(rows["spatz"]["pin_influence"], "filtered_by_pin")
        self.assertFalse(rows["snitch"]["cost"]["evaluated"])
        self.assertEqual(mapper.explanations[-1]["selected_cost_cycles"], None)

    def test_incompatible_pin_leaves_compatible_candidates_for_cost_selection(self):
        mapper, engines = self.mapper(pin="snitch")
        engines["snitch"].compatible = False
        node = FakeNode()
        expected = min((engine for engine in (engines["cva6"], engines["spatz"])
                        if mapper.cost(engine, node) is not None),
                       key=lambda engine: mapper.cost(engine, node))
        self.assertIs(mapper.mapNodeToEngine(node, None), expected)
        rows = {row["engine"]: row for row in mapper.explanations[-1]["candidates"]}
        self.assertTrue(rows["spatz"]["candidate_after_pin"])
        self.assertEqual(rows["spatz"]["pin_influence"], "pin_not_applied")
        self.assertTrue(rows["spatz"]["cost"]["evaluated"])

    def test_incompatible_and_default_rate_cases_remain_explicit(self):
        mapper, engines = self.mapper()
        engines["snitch"].compatible = False
        node = FakeNode(op="Add", fp32=False)
        mapper.mapNodeToEngine(node, None)
        rows = {row["engine"]: row for row in mapper.explanations[-1]["candidates"]}
        self.assertFalse(rows["snitch"]["compatible"])
        self.assertEqual(rows["snitch"]["exclusion_reason"], "operator_not_in_cluster_mapping")
        self.assertFalse(rows["snitch"]["cost"]["evaluated"])
        self.assertEqual(rows["cva6"]["cost"]["rate_key"], "_default")
        self.assertEqual(rows["cva6"]["cost"]["rate_key_source"],
                         "documented_default_proxy_not_measured_for_operator")

    def test_no_compatible_engine_keeps_selection_and_cost_unknown(self):
        mapper, engines = self.mapper()
        for engine in engines.values():
            engine.compatible = False
        self.assertIsNone(mapper.mapNodeToEngine(FakeNode(), None))
        explanation = mapper.explanations[-1]
        self.assertIsNone(explanation["selected_engine"])
        self.assertEqual(explanation["selection_rule"], "no_compatible_engine")
        self.assertTrue(all(not row["cost"]["evaluated"]
                            for row in explanation["candidates"]))

    def test_calibration_metadata_is_referenced_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rates = root / "rates.json"
            rates.write_text("{}\n")
            (root / "calibration.json").write_text(json.dumps({
                "kind": "k9r5.calibration", "input_fingerprint": "sha256:input",
                "artifacts": {"rates": {"digest": "sha256:rates"}},
            }))
            provenance = self.mapper_mod._rate_table_provenance(rates)
        self.assertEqual(provenance["kind"], "calibration_artifact")
        self.assertEqual(provenance["calibration_input_fingerprint"], "sha256:input")

    def test_explanation_serialization_is_deterministic(self):
        mapper, _engines = self.mapper()
        mapper.mapNodeToEngine(FakeNode(), None)
        self.assertEqual(
            json.dumps(mapper.explanations, sort_keys=True),
            json.dumps(mapper.explanations, sort_keys=True),
        )


if __name__ == "__main__":
    unittest.main()
