import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SWEEP = ROOT / "pipeline" / "sweep" / "run.py"


def _tree():
    return ast.parse(SWEEP.read_text(), filename=str(SWEEP))


def _function(name):
    for node in _tree().body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"{SWEEP} has no function {name}")


class SweepPinTests(unittest.TestCase):

    def test_run_cell_accepts_pin(self):
        fn = _function("run_cell")
        args = [a.arg for a in fn.args.args]
        self.assertIn("pin", args)

    def test_run_hetero_command_forwards_pin(self):
        fn = _function("run_cell")
        found = False
        for node in ast.walk(fn):
            if not isinstance(node, ast.If):
                continue
            if not isinstance(node.test, ast.Name) or node.test.id != "pin":
                continue
            segment = ast.get_source_segment(SWEEP.read_text(), node) or ""
            if '"--pin"' in segment and "pin" in segment:
                found = True
                break
        self.assertTrue(found, "run_cell no longer forwards pin to run_hetero.py")

    def test_resolved_experiment_records_pin(self):
        fn = _function("run_cell")
        calls = [
            node for node in ast.walk(fn)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "ExperimentRequest"
        ]
        self.assertEqual(len(calls), 1)
        keywords = {kw.arg: kw.value for kw in calls[0].keywords if kw.arg}
        self.assertIn("pin", keywords)
        self.assertIsInstance(keywords["pin"], ast.Name)
        self.assertEqual(keywords["pin"].id, "pin")

    def test_cli_exposes_and_forwards_pin(self):
        text = SWEEP.read_text()
        self.assertIn(
            'ap.add_argument("--pin", choices=("cva6", "snitch", "spatz"), default=None',
            text,
        )
        self.assertIn("pin=args.pin", text)


if __name__ == "__main__":
    unittest.main()
