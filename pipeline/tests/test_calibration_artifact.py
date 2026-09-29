import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.experiment.calibration_artifact import (  # noqa: E402
    KIND,
    SCHEMA_VERSION,
    cache_status,
    write_metadata,
)
from pipeline.experiment.fingerprint import fingerprint  # noqa: E402


class CalibrationArtifactTests(unittest.TestCase):
    def context(self, host="cva6", design=None):
        payload = {
            "schema_version": SCHEMA_VERSION,
            "protocol": "mesh_calib_v1",
            "host": host,
            "design": design or {"SPATZ_NB_LANES": 4},
        }
        return {
            "input": payload,
            "input_fingerprint": fingerprint(payload),
            "provenance": {"k9r5": {"revision": "abc"}},
        }

    def test_host_change_invalidates_input_identity(self):
        self.assertNotEqual(
            self.context("cva6")["input_fingerprint"],
            self.context("ara")["input_fingerprint"],
        )

    def test_design_change_invalidates_input_identity(self):
        a = self.context(design={"SPATZ_NB_LANES": 4})
        b = self.context(design={"SPATZ_NB_LANES": 8})
        self.assertNotEqual(a["input_fingerprint"], b["input_fingerprint"])

    def test_legacy_rates_without_metadata_are_not_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rates = root / "rates.json"
            rates.write_text("{}\n")
            ok, why = cache_status(rates, root / "calibration.json", "sha256:x")
            self.assertFalse(ok)
            self.assertEqual(why, "metadata-missing")

    def test_matching_metadata_and_rates_are_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rates = root / "rates.json"
            log = root / "calib.log"
            meta = root / "calibration.json"
            rates.write_text('{"RATES": {}}\n')
            log.write_text("raw calibration\n")
            ctx = self.context()
            write_metadata(meta, ctx, rates, log)
            ok, why = cache_status(rates, meta, ctx["input_fingerprint"])
            self.assertTrue(ok)
            self.assertEqual(why, "hit")

    def test_modified_rates_are_not_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rates = root / "rates.json"
            log = root / "calib.log"
            meta = root / "calibration.json"
            rates.write_text('{"RATES": {}}\n')
            log.write_text("raw calibration\n")
            ctx = self.context()
            write_metadata(meta, ctx, rates, log)
            rates.write_text('{"RATES": {"changed": true}}\n')
            ok, why = cache_status(rates, meta, ctx["input_fingerprint"])
            self.assertFalse(ok)
            self.assertEqual(why, "rates-digest-mismatch")

    def test_metadata_records_artifact_digests_and_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rates = root / "rates.json"
            log = root / "run" / "calib.log"
            log.parent.mkdir()
            meta = root / "calibration.json"
            rates.write_text("{}\n")
            log.write_text("log\n")
            write_metadata(meta, self.context(), rates, log)
            blob = json.loads(meta.read_text())
            self.assertEqual(blob["kind"], KIND)
            self.assertEqual(blob["schema_version"], SCHEMA_VERSION)
            self.assertTrue(blob["artifacts"]["rates"]["digest"].startswith("sha256:"))
            self.assertEqual(blob["artifacts"]["raw_log"]["path"], "run/calib.log")


if __name__ == "__main__":
    unittest.main()
