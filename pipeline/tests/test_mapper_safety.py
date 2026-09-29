import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.tests.test_mapping_explanation import (  # noqa: E402
    FakeCluster,
    FakeEngine,
    FakeNode,
    load_mapper,
)


class MapperSafetyTests(unittest.TestCase):

    def setUp(self):
        self.mapper_mod, self.saved, self.names = load_mapper()

    def tearDown(self):
        for name in self.names:
            prior = self.saved[name]
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior

    def mapper(self, engines, pin=None):
        return self.mapper_mod.CostEngineMapper(engines, pin=pin)

    @staticmethod
    def node(*, op="MatMul", left=(2, 3), right=(3, 8), output=(2, 8), attrs=None):
        node = FakeNode(op=op)
        node.inputs[0].shape = list(left)
        node.inputs[1].shape = list(right)
        node.outputs[0].shape = list(output)
        node.attrs = dict(attrs or {})
        return node

    def test_unknown_shape_has_no_fabricated_mac_cost_or_selection(self):
        engines = {"cva6": FakeEngine("cva6"), "spatz": FakeCluster("spatz")}
        mapper = self.mapper(engines)
        node = self.node(left=(None, 3), output=(None, 8))
        self.assertIsNone(self.mapper_mod.node_macs(node))
        self.assertIsNone(mapper.mapNodeToEngine(node, None))
        rows = {row["engine"]: row for row in mapper.explanations[-1]["candidates"]}
        self.assertEqual(rows["cva6"]["cost"]["reason"], "shape_derived_macs_unavailable")
        self.assertEqual(mapper.explanations[-1]["selection_rule"],
                         "no_compatible_engine_with_safe_cost")

    def test_unknown_engine_and_missing_operator_rate_cannot_borrow_cva6(self):
        node = self.node()
        unknown = FakeEngine("future_engine")
        mapper = self.mapper({"future_engine": unknown})
        self.assertIsNone(mapper.cost(unknown, node))
        self.assertEqual(mapper.cost_breakdown(unknown, node)["reason"],
                         "missing_engine_rate_row")
        old = self.mapper_mod.RATES["spatz"]
        try:
            self.mapper_mod.RATES["spatz"] = {}
            spatz = FakeCluster("spatz")
            mapper = self.mapper({"spatz": spatz})
            self.assertIsNone(mapper.mapNodeToEngine(node, None))
            self.assertEqual(mapper.explanations[-1]["candidates"][0]["cost"]["reason"],
                             "missing_or_invalid_operator_rate")
        finally:
            self.mapper_mod.RATES["spatz"] = old

    def test_documented_default_proxy_remains_explicit_not_measured(self):
        mapper = self.mapper({"cva6": FakeEngine("cva6")})
        cost = mapper.cost_breakdown(mapper.engineDict["cva6"], self.node(op="Add"))
        self.assertTrue(cost["evaluated"])
        self.assertEqual(cost["rate_key"], "_default")
        self.assertEqual(cost["rate_key_source"],
                         "documented_default_proxy_not_measured_for_operator")

    def test_deterministic_snitch_and_spatz_fallbacks_have_no_tuned_cost(self):
        snitch = self.mapper({"snitch": FakeCluster("snitch")})
        small = self.node(right=(3, 7), output=(2, 7))
        cost = snitch.cost_breakdown(snitch.engineDict["snitch"], small)
        self.assertFalse(cost["evaluated"])
        self.assertEqual(cost["fallback_reason"], "output_columns_below_ssr_unroll")
        scalar_tail = self.node(right=(3, 9), output=(2, 9))
        self.assertTrue(snitch.cost_breakdown(snitch.engineDict["snitch"], scalar_tail)["evaluated"])

        spatz = self.mapper({"spatz": FakeCluster("spatz")})
        transposed = self.node(op="Gemm", attrs={"transA": 1, "transB": 0})
        cost = spatz.cost_breakdown(spatz.engineDict["spatz"], transposed)
        self.assertFalse(cost["evaluated"])
        self.assertEqual(cost["fallback_reason"], "transposed_operand")
        empty = self.node(left=(0, 3), right=(3, 8), output=(0, 8))
        self.assertEqual(spatz.cost_breakdown(spatz.engineDict["spatz"], empty)["fallback_reason"],
                         "empty_dimension")

    def test_pin_keeps_compatible_node_semantics_but_exposes_unsafe_cost(self):
        engines = {"cva6": FakeEngine("cva6"), "snitch": FakeCluster("snitch")}
        mapper = self.mapper(engines, pin="snitch")
        small = self.node(right=(3, 7), output=(2, 7))
        self.assertIs(mapper.mapNodeToEngine(small, None), engines["snitch"])
        row = next(row for row in mapper.explanations[-1]["candidates"]
                   if row["engine"] == "snitch")
        self.assertEqual(row["cost"]["reason"],
                         "deterministic_generic_fallback_has_no_generic_rate")
        self.assertEqual(mapper.explanations[-1]["pin_semantics"],
                         "compatible_node_preference_not_whole_graph")

    def test_valid_static_mapping_keeps_prior_selection(self):
        engines = {
            "cva6": FakeEngine("cva6"),
            "snitch": FakeCluster("snitch"),
            "spatz": FakeCluster("spatz"),
        }
        mapper = self.mapper(engines)
        self.assertIs(mapper.mapNodeToEngine(self.node(left=(32, 32), right=(32, 32), output=(32, 32)), None), engines["spatz"])

    def test_pin_is_documented_as_compatible_node_not_whole_graph(self):
        for path in (
            ROOT / "pipeline" / "hetero_platform" / "generate.py",
            ROOT / "pipeline" / "run_hetero.py",
            ROOT / "pipeline" / "sweep" / "run.py",
        ):
            self.assertIn("whole-graph", path.read_text())
        resolve = (ROOT / "pipeline" / "experiment" / "resolve.py").read_text()
        self.assertIn("compatible_node_preference_not_whole_graph", resolve)

    def test_cluster_source_refuses_unknown_working_set(self):
        source = (ROOT / "pipeline" / "hetero_platform" / "engines.py").read_text()
        tree = ast.parse(source)
        self.assertIn("return size is not None and size <= self.tcdm_budget", source)
        self.assertTrue(any(isinstance(node, ast.FunctionDef) and node.name == "working_set_bytes"
                            for node in tree.body))


if __name__ == "__main__":
    unittest.main()
