import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline" / "sweep"))

import design as design_mod  # noqa: E402
from pipeline.experiment.resource_summary import build_resource_summary  # noqa: E402


class ResourceSummaryTests(unittest.TestCase):

    def summary(self, overrides=None):
        return build_resource_summary(design_mod.resolve(overrides or {}))

    def test_baseline_distinguishes_modeled_compute_and_control_cores(self):
        resources = self.summary()
        self.assertEqual(resources["platform"]["total_modeled_cores"], 19)
        for name in ("snitch", "spatz"):
            cluster = resources["clusters"][name]
            self.assertEqual(cluster["modeled_cores"], 9)
            self.assertEqual(cluster["compute_cores"], 8)
            self.assertEqual(cluster["control_dma_cores"], 1)

    def test_cluster_core_knobs_change_only_their_cluster_summary(self):
        base = self.summary()
        snitch = self.summary({"SNITCH_NB_CORE": 17})
        spatz = self.summary({"SPATZ_NB_CORE": 17})
        self.assertEqual(snitch["clusters"]["snitch"]["compute_cores"], 16)
        self.assertEqual(snitch["clusters"]["spatz"], base["clusters"]["spatz"])
        self.assertEqual(spatz["clusters"]["spatz"]["compute_cores"], 16)
        self.assertEqual(spatz["clusters"]["snitch"], base["clusters"]["snitch"])

    def test_spatz_lanes_distinguish_modeled_and_useful_vector_resources(self):
        resources = self.summary({"SPATZ_NB_LANES": 8})
        vector = resources["clusters"]["spatz"]["spatz_vector"]
        self.assertEqual(vector["lanes_per_compute_core"], 8)
        self.assertEqual(vector["modeled_vector_lanes"], 72)
        self.assertEqual(vector["useful_vector_lanes"], 64)

    def test_tcdm_geometry_and_memory_path_are_source_grounded(self):
        resources = self.summary({"TCDM_SIZE": 0x40000})
        for name in ("snitch", "spatz"):
            tcdm = resources["clusters"][name]["tcdm"]
            self.assertEqual(tcdm["capacity_bytes"], 0x40000)
            self.assertEqual(tcdm["bank_count"], 32)
            self.assertEqual(tcdm["bank_size_bytes"], 0x2000)
        self.assertFalse(resources["clusters"]["snitch"]["memory_path"]["kernel_operand_staging_required"])
        self.assertTrue(resources["clusters"]["spatz"]["memory_path"]["kernel_operand_staging_required"])

    def test_summary_is_deterministic_and_does_not_invent_peak_or_area(self):
        first = self.summary()
        second = self.summary()
        self.assertEqual(first, second)
        encoded = repr(first).lower()
        self.assertNotIn("peak", encoded)
        self.assertNotIn("area", encoded)
        self.assertNotIn("power", encoded)
        self.assertNotIn("nominal_fp32_peak", first["clusters"]["spatz"])
        self.assertNotIn("fpu_count", first["clusters"]["snitch"])


if __name__ == "__main__":
    unittest.main()
