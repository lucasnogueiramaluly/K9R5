import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.experiment.engine_catalog import META, build_catalog  # noqa: E402


def _simple_assignments(path: Path, wanted: set[str]) -> dict:
    """Evaluate only constants/names/dicts needed by the identity tables."""
    tree = ast.parse(path.read_text(), filename=str(path))
    env = {}

    def value(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name) and node.id in env:
            return env[node.id]
        if isinstance(node, ast.Dict):
            return {value(k): value(v) for k, v in zip(node.keys, node.values)}
        raise ValueError(f"unsupported expression in {path}: {ast.dump(node)}")

    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
            continue
        target = stmt.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if target.id in wanted:
            env[target.id] = value(stmt.value)

    missing = wanted - set(env)
    if missing:
        raise AssertionError(f"{path} is missing expected assignments: {sorted(missing)}")
    return env


def _engine_names() -> dict[int, str]:
    env = _simple_assignments(
        ROOT / "targets" / "hetero" / "system.py",
        {"ENGINE_HOST", "ENGINE_SNITCH", "ENGINE_SPATZ", "ENGINE_NAMES"},
    )
    return env["ENGINE_NAMES"]


def _engine_macros() -> dict[str, str]:
    env = _simple_assignments(
        ROOT / "pipeline" / "hetero_platform" / "progress.py",
        {"ENGINE_MACRO"},
    )
    return env["ENGINE_MACRO"]


class EngineCatalogTests(unittest.TestCase):

    def test_catalog_matches_architectural_engine_ids_and_names(self):
        names = _engine_names()
        rows = build_catalog(names, _engine_macros())
        self.assertEqual(
            {row["system_id"]: row["name"] for row in rows},
            names,
        )

    def test_catalog_matches_runtime_progress_macros(self):
        macros = _engine_macros()
        rows = build_catalog(_engine_names(), macros)
        by_name = {row["name"]: row for row in rows}
        self.assertEqual(set(by_name), set(macros))
        for name, macro in macros.items():
            self.assertEqual(by_name[name]["runtime_macro"], macro)

    def test_catalog_refuses_identity_drift(self):
        bad_names = dict(_engine_names())
        bad_names[max(bad_names) + 1] = "mystery"
        with self.assertRaises(RuntimeError):
            build_catalog(bad_names, _engine_macros())

    def test_ara_is_not_a_logical_engine(self):
        self.assertEqual(set(_engine_names().values()), {"cva6", "snitch", "spatz"})
        self.assertEqual(set(META), {"cva6", "snitch", "spatz"})
        self.assertNotIn("ara", META)
        self.assertEqual(META["cva6"].kind, "host")


if __name__ == "__main__":
    unittest.main()
