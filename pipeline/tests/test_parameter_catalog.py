import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline" / "sweep"))

import design as design_mod  # noqa: E402
from pipeline.experiment.parameter_catalog import META, build_catalog  # noqa: E402


def load_sweep_run():
    path = ROOT / "pipeline" / "sweep" / "run.py"
    spec = importlib.util.spec_from_file_location("k9r5_sweep_run_for_catalog_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ParameterCatalogTests(unittest.TestCase):

    def test_catalog_covers_exactly_supported_design_knobs(self):
        self.assertEqual(set(META), set(design_mod.DEFAULTS))

    def test_operational_values_are_derived_not_redeclared(self):
        sweep_run = load_sweep_run()
        catalog = build_catalog(
            design_mod.DEFAULTS,
            design_mod.BUILD_TIME,
            sweep_run.OFAT,
        )
        by_name = {entry["name"]: entry for entry in catalog}
        for name, value in design_mod.DEFAULTS.items():
            self.assertEqual(by_name[name]["default"], value)
            self.assertEqual(
                by_name[name]["build_time"],
                name in design_mod.BUILD_TIME,
            )
            self.assertEqual(
                by_name[name]["screening_values"],
                list(sweep_run.OFAT.get(name, ())),
            )

    def test_catalog_refuses_metadata_drift(self):
        bad = dict(design_mod.DEFAULTS)
        bad["NEW_UNDOCUMENTED_KNOB"] = 1
        with self.assertRaises(RuntimeError):
            build_catalog(bad, design_mod.BUILD_TIME, {})

    def test_catalog_describes_units_and_groups(self):
        catalog = build_catalog(design_mod.DEFAULTS, design_mod.BUILD_TIME, {})
        by_name = {entry["name"]: entry for entry in catalog}
        self.assertEqual(by_name["SPATZ_VLEN"]["unit"], "bits")
        self.assertEqual(by_name["TCDM_SIZE"]["unit"], "bytes")
        self.assertEqual(by_name["WIDE_AXI_WIDTH"]["unit"], "bytes")
        self.assertEqual(by_name["SNITCH_NB_CORE"]["group"], "cluster_shape")


if __name__ == "__main__":
    unittest.main()
