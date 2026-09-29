import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.experiment.mapping_strategy_catalog import META, build_catalog  # noqa: E402


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def _top_level_names(tree: ast.Module) -> tuple[set[str], set[str]]:
    classes = set()
    functions = set()
    for stmt in tree.body:
        if isinstance(stmt, ast.ClassDef):
            classes.add(stmt.name)
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions.add(stmt.name)
    return classes, functions


def _called_function_names(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            names.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


class MappingStrategyCatalogTests(unittest.TestCase):

    def test_single_current_strategy_has_stable_identity(self):
        rows = build_catalog()
        self.assertEqual([row["id"] for row in rows], ["measured_rate_greedy"])
        self.assertNotIn("pin", META)
        self.assertEqual(rows[0]["decision_explanation"]["path"],
                         "mapping.nodes[].mapping_explanation")

    def test_strategy_points_to_current_mapper_and_factory(self):
        mapper_path = ROOT / "pipeline" / "hetero_platform" / "mapper.py"
        classes, functions = _top_level_names(_parse(mapper_path))
        meta = META["measured_rate_greedy"]
        self.assertIn(meta.implementation, classes)
        self.assertIn(meta.factory, functions)

    def test_current_mapper_exposes_measured_cost_inputs(self):
        mapper_path = ROOT / "pipeline" / "hetero_platform" / "mapper.py"
        tree = _parse(mapper_path)
        assigned = set()
        for stmt in tree.body:
            if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
                targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
                for target in targets:
                    if isinstance(target, ast.Name):
                        assigned.add(target.id)
        self.assertTrue(
            {"RATES", "OFFLOAD_FIXED", "OFFLOAD_PER_BYTE"} <= assigned,
            "current measured-rate/offload cost inputs drifted",
        )

    def test_generate_still_constructs_mapper_through_make_mapper(self):
        generate_path = ROOT / "pipeline" / "hetero_platform" / "generate.py"
        calls = _called_function_names(_parse(generate_path))
        self.assertIn("make_mapper", calls)


if __name__ == "__main__":
    unittest.main()
