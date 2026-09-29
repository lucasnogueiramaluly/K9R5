import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.experiment.host_profile_catalog import META, build_catalog  # noqa: E402


def _host_targets() -> dict[str, str]:
    """Read HOSTS = {name: (image, target)} without importing the build tool."""
    path = ROOT / "pipeline" / "build_mesh.py"
    tree = ast.parse(path.read_text(), filename=str(path))

    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
            continue
        target = stmt.targets[0]
        if not isinstance(target, ast.Name) or target.id != "HOSTS":
            continue
        if not isinstance(stmt.value, ast.Dict):
            raise AssertionError("pipeline/build_mesh.py::HOSTS is no longer a dict literal")

        out = {}
        for key_node, value_node in zip(stmt.value.keys, stmt.value.values):
            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                raise AssertionError("HOSTS profile names must be string literals")
            if not isinstance(value_node, ast.Tuple) or len(value_node.elts) != 2:
                raise AssertionError("HOSTS values must remain (image, target) tuples")
            target_node = value_node.elts[1]
            if not isinstance(target_node, ast.Constant) or not isinstance(target_node.value, str):
                raise AssertionError("HOSTS target names must be string literals")
            out[key_node.value] = target_node.value
        return out

    raise AssertionError("pipeline/build_mesh.py does not define HOSTS")


class HostProfileCatalogTests(unittest.TestCase):

    def test_catalog_matches_build_mesh_host_profiles(self):
        targets = _host_targets()
        rows = build_catalog(targets)
        self.assertEqual(
            {row["name"]: row["target"] for row in rows},
            targets,
        )

    def test_cva6_and_ara_share_one_logical_engine(self):
        rows = {row["name"]: row for row in build_catalog(_host_targets())}
        self.assertEqual(rows["cva6"]["logical_engine"], "cva6")
        self.assertEqual(rows["ara"]["logical_engine"], "cva6")

    def test_profiles_preserve_scalar_vs_vector_distinction(self):
        rows = {row["name"]: row for row in build_catalog(_host_targets())}
        self.assertFalse(rows["cva6"]["vector"])
        self.assertTrue(rows["ara"]["vector"])
        self.assertEqual(rows["cva6"]["target"], "hetero_soc")
        self.assertEqual(rows["ara"]["target"], "hetero_ara")

    def test_catalog_refuses_host_profile_drift(self):
        bad = dict(_host_targets())
        bad["future_host"] = "hetero_future"
        with self.assertRaises(RuntimeError):
            build_catalog(bad)


if __name__ == "__main__":
    unittest.main()
