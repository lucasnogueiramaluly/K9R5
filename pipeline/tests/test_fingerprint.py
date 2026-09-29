import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.experiment.fingerprint import canonical_json_bytes, file_set_digest, fingerprint


class FingerprintTests(unittest.TestCase):
    def test_dict_order_does_not_change_fingerprint(self):
        a = {"hardware": {"lanes": 4, "vlen": 512}, "host": "cva6"}
        b = {"host": "cva6", "hardware": {"vlen": 512, "lanes": 4}}
        self.assertEqual(fingerprint(a), fingerprint(b))

    def test_sequence_order_does_change_fingerprint(self):
        self.assertNotEqual(fingerprint([1, 2, 3]), fingerprint([3, 2, 1]))

    def test_set_order_is_canonicalized(self):
        self.assertEqual(fingerprint({"x": {3, 1, 2}}), fingerprint({"x": {2, 3, 1}}))

    def test_non_finite_float_is_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaises(ValueError):
                canonical_json_bytes({"value": value})

    def test_file_set_is_independent_of_input_order_and_root_location(self):
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            first = Path(first)
            second = Path(second)
            for root in (first, second):
                (root / "a.txt").write_text("alpha")
                (root / "sub").mkdir()
                (root / "sub" / "b.txt").write_text("beta")
            d1 = file_set_digest(first, ["a.txt", "sub/b.txt"])
            d2 = file_set_digest(first, ["sub/b.txt", "a.txt"])
            d3 = file_set_digest(second, ["a.txt", "sub/b.txt"])
            self.assertEqual(d1, d2)
            self.assertEqual(d1, d3)

    def test_unselected_file_does_not_change_selected_file_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "selected.txt").write_text("same")
            (root / "README.md").write_text("version one")
            before = file_set_digest(root, ["selected.txt"])
            (root / "README.md").write_text("version two")
            after = file_set_digest(root, ["selected.txt"])
            self.assertEqual(before, after)

    def test_selected_file_change_invalidates_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "selected.txt"
            path.write_text("one")
            before = file_set_digest(root, ["selected.txt"])
            path.write_text("two")
            after = file_set_digest(root, ["selected.txt"])
            self.assertNotEqual(before, after)


if __name__ == "__main__":
    unittest.main()
