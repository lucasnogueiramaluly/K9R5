import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.experiment.fingerprint import fingerprint  # noqa: E402
from pipeline.experiment.provenance import (  # noqa: E402
    SOURCE_SUFFIXES,
    git_snapshot,
    git_snapshot_optional,
    patch_digests,
    semantic_git_identity,
    source_files_under,
    toolchain_snapshot,
)


class ProvenanceTests(unittest.TestCase):
    def _git(self, root, *args):
        return subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()

    def _repository(self, root):
        self._git(root, "init", "-q")
        self._git(root, "config", "user.email", "m4ia-test@example.invalid")
        self._git(root, "config", "user.name", "M4IA Test")
        (root / "model.cpp").write_text("int model = 1;\n")
        self._git(root, "add", "model.cpp")
        self._git(root, "commit", "-q", "-m", "fixture")

    def test_git_snapshot_represents_dirty_tracked_and_untracked_source_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._repository(root)
            clean = git_snapshot(root, name="fixture")
            self.assertFalse(clean["dirty"])
            self.assertIsNone(clean["diff_digest"])
            self.assertIsNone(clean["untracked_digest"])

            (root / "model.cpp").write_text("int model = 2;\n")
            (root / "new.hpp").write_text("#pragma once\n")
            dirty = git_snapshot(root, name="fixture")
            self.assertTrue(dirty["dirty"])
            self.assertTrue(dirty["diff_digest"].startswith("sha256:"))
            self.assertTrue(dirty["untracked_digest"].startswith("sha256:"))

    def test_remote_url_is_provenance_not_semantic_identity(self):
        base = {
            "available": True,
            "name": "dependency",
            "repository": "https://example.invalid/upstream.git",
            "revision": "abc123",
            "dirty": False,
            "diff_digest": None,
            "untracked_digest": None,
        }
        mirror = dict(base, repository="ssh://mirror.invalid/dependency.git")
        self.assertEqual(semantic_git_identity(base), semantic_git_identity(mirror))
        self.assertEqual(
            fingerprint(semantic_git_identity(base)),
            fingerprint(semantic_git_identity(mirror)),
        )

    def test_optional_git_snapshot_reports_missing_metadata_explicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            snapshot = git_snapshot_optional(tmp, name="runtime-copy")
        self.assertFalse(snapshot["available"])
        self.assertEqual(snapshot["reason"], "git-metadata-unavailable")
        self.assertIsNone(snapshot["revision"])

    def test_source_suffixes_cover_current_and_common_cpp_spellings(self):
        self.assertTrue({".cpp", ".hpp", ".cc", ".cxx", ".hh"} <= SOURCE_SUFFIXES)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wanted = ["dram.cpp", "dram_core.hpp", "other.cc", "more.cxx", "last.hh"]
            for name in wanted:
                (root / name).write_text(name)
            (root / "README.md").write_text("not causal source")
            self.assertEqual(
                [path.name for path in source_files_under(root)],
                sorted(wanted),
            )

    def test_patch_digests_are_deterministic_and_root_relative(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b.patch").write_text("b\n")
            (root / "a.patch").write_text("a\n")
            forward = patch_digests(root, [root / "b.patch", root / "a.patch"])
            reverse = patch_digests(root, [root / "a.patch", root / "b.patch"])
            self.assertEqual(forward, reverse)
            self.assertEqual([item["path"] for item in forward], ["a.patch", "b.patch"])

    def test_toolchain_snapshot_captures_version_and_binary_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            executable = Path(tmp) / "compiler"
            executable.write_text("#!/bin/sh\nprintf 'fixture compiler 1.0\\n'\n")
            executable.chmod(executable.stat().st_mode | 0o111)
            snapshot = toolchain_snapshot(executable)
            self.assertEqual(snapshot["executable"], "compiler")
            self.assertEqual(snapshot["version"], "fixture compiler 1.0")
            self.assertTrue(snapshot["binary_digest"].startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
