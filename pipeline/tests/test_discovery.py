import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.experiment.discovery import current_engine_catalog, current_host_profile_catalog  # noqa: E402


class DiscoveryTests(unittest.TestCase):
    def test_engine_discovery_reads_operational_sources(self):
        rows = current_engine_catalog(ROOT)
        self.assertEqual(
            {row["system_id"]: row["name"] for row in rows},
            {0: "cva6", 1: "snitch", 2: "spatz"},
        )

    def test_host_profile_discovery_reads_build_mesh_targets(self):
        profiles = current_host_profile_catalog(ROOT)
        self.assertEqual(set(profiles), {"cva6", "ara"})
        self.assertEqual(profiles["cva6"]["target"], "hetero_soc")
        self.assertEqual(profiles["ara"]["target"], "hetero_ara")
        self.assertEqual(profiles["ara"]["logical_engine"], "cva6")


if __name__ == "__main__":
    unittest.main()
