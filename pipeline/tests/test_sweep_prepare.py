import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SWEEP_DIR = ROOT / "pipeline" / "sweep"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SWEEP_DIR) not in sys.path:
    sys.path.insert(0, str(SWEEP_DIR))

spec = importlib.util.spec_from_file_location("k9r5_sweep_run_for_test", SWEEP_DIR / "run.py")
sweep_run = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(sweep_run)


class SweepPrepareTests(unittest.TestCase):
    def setUp(self):
        self.old_mesh = sweep_run.MESH
        self.old_python = sweep_run.PYTHON
        self.old_sh = sweep_run.sh

    def tearDown(self):
        sweep_run.MESH = self.old_mesh
        sweep_run.PYTHON = self.old_python
        sweep_run.sh = self.old_sh

    def _install_fake_header_generator(self):
        def fake_sh(cmd, **kwargs):
            out_dir = Path(cmd[cmd.index("--out-dir") + 1])
            (out_dir / "hes_system.h").write_text("generated\n")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        sweep_run.sh = fake_sh

    def test_prepare_replaces_stale_mesh_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source_mesh"
            source.mkdir()
            (source / "cluster_main.c").write_text("new source\n")
            (source / "current.h").write_text("present\n")

            cell = root / "design"
            dest = cell / "mesh"
            dest.mkdir(parents=True)
            (dest / "cluster_main.c").write_text("old source\n")
            (dest / "stale_only.h").write_text("must disappear\n")

            sweep_run.MESH = source
            sweep_run.PYTHON = Path("/fake/python")
            self._install_fake_header_generator()

            got = sweep_run.prepare({}, cell, {"HES_DESIGN": "unused"})

            self.assertEqual(got, dest)
            self.assertEqual((dest / "cluster_main.c").read_text(), "new source\n")
            self.assertTrue((dest / "current.h").is_file())
            self.assertFalse((dest / "stale_only.h").exists())
            self.assertEqual((dest / "hes_system.h").read_text(), "generated\n")

    def test_prepare_refreshes_again_when_source_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source_mesh"
            source.mkdir()
            tracked = source / "hes_host.c"
            tracked.write_text("version 1\n")

            cell = root / "design"

            sweep_run.MESH = source
            sweep_run.PYTHON = Path("/fake/python")
            self._install_fake_header_generator()

            sweep_run.prepare({}, cell, {"HES_DESIGN": "unused"})
            self.assertEqual((cell / "mesh" / "hes_host.c").read_text(), "version 1\n")

            tracked.write_text("version 2\n")
            sweep_run.prepare({}, cell, {"HES_DESIGN": "unused"})
            self.assertEqual((cell / "mesh" / "hes_host.c").read_text(), "version 2\n")


if __name__ == "__main__":
    unittest.main()
