"""Cheap regression tests for heterogeneous image selection."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pipeline"))

import build_mesh  # noqa: E402


class BuildTestHostSelectionTests(unittest.TestCase):

    def _images_built_for(self, host):
        images = []

        def fake_build(image, sources, out_dir, **kwargs):
            images.append(image)
            return Path(out_dir) / f"{image.name}.elf"

        with patch.object(build_mesh, "build", side_effect=fake_build):
            build_mesh.build_test(
                "mesh_calib",
                Path("/tmp/k9r5-build-test"),
                cluster_src=build_mesh.MESH / "cluster_main.c",
                host_extra=[build_mesh.MESH / "hes_host.c"],
                host=host,
            )
        return images

    def test_scalar_calibration_build_uses_scalar_host(self):
        images = self._images_built_for("cva6")
        self.assertIs(images[0], build_mesh.HOST)

    def test_ara_calibration_build_uses_vector_host(self):
        images = self._images_built_for("ara")
        self.assertIs(images[0], build_mesh.HOST_ARA)


if __name__ == "__main__":
    unittest.main()
