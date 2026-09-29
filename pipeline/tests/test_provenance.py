import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pipeline.experiment.provenance import (
    capture_run_provenance,
    git_snapshot,
    git_snapshot_optional,
    patch_digests,
)


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


class ProvenanceTests(unittest.TestCase):
    def make_repo(self, root):
        repo = Path(root)
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "test@example.invalid")
        git(repo, "config", "user.name", "K9R5 Test")
        (repo / "tracked.txt").write_text("baseline\n")
        git(repo, "add", "tracked.txt")
        git(repo, "commit", "-q", "-m", "baseline")
        return repo

    def test_clean_checkout_has_no_dirty_digests(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(tmp)
            snap = git_snapshot(repo, name="test")
            self.assertEqual(snap["revision"], git(repo, "rev-parse", "HEAD"))
            self.assertFalse(snap["dirty"])
            self.assertIsNone(snap["diff_digest"])
            self.assertIsNone(snap["untracked_digest"])

    def test_tracked_change_sets_diff_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(tmp)
            (repo / "tracked.txt").write_text("changed\n")
            snap = git_snapshot(repo)
            self.assertTrue(snap["dirty"])
            self.assertIsNotNone(snap["diff_digest"])
            self.assertIsNone(snap["untracked_digest"])

    def test_untracked_content_has_its_own_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(tmp)
            path = repo / "new.txt"
            path.write_text("one")
            first = git_snapshot(repo)
            path.write_text("two")
            second = git_snapshot(repo)
            self.assertTrue(first["dirty"])
            self.assertIsNone(first["diff_digest"])
            self.assertIsNotNone(first["untracked_digest"])
            self.assertNotEqual(first["untracked_digest"], second["untracked_digest"])

    def test_snapshot_does_not_depend_on_checkout_directory(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            repo_a = self.make_repo(a)
            clone = Path(b) / "clone"
            subprocess.run(["git", "clone", "-q", str(repo_a), str(clone)], check=True)
            git(clone, "remote", "remove", "origin")
            sa = git_snapshot(repo_a, name="same")
            sb = git_snapshot(clone, name="same")
            self.assertEqual(sa, sb)

    def test_optional_snapshot_marks_non_git_source_tree_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "source.c").write_text("int main(void) { return 0; }\n")
            snap = git_snapshot_optional(root, name="k9r5")
            self.assertFalse(snap["available"])
            self.assertEqual(snap["reason"], "git-metadata-unavailable")
            self.assertEqual(snap["name"], "k9r5")
            self.assertIsNone(snap["revision"])
            self.assertIsNone(snap["dirty"])

    def test_optional_snapshot_preserves_git_snapshot_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = self.make_repo(tmp)
            strict = git_snapshot(repo, name="test")
            optional = git_snapshot_optional(repo, name="test")
            self.assertTrue(optional.pop("available"))
            self.assertEqual(optional, strict)

    def test_patch_digests_are_relative_and_sorted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "z.patch").write_text("z")
            (root / "a.patch").write_text("a")
            records = patch_digests(root, ["z.patch", "a.patch"])
            self.assertEqual([r["path"] for r in records], ["a.patch", "z.patch"])
            self.assertTrue(all(r["digest"].startswith("sha256:") for r in records))

    def test_run_source_set_is_location_independent_and_excludes_docs(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            for root in (Path(a), Path(b)):
                (root / "pipeline/hetero_platform").mkdir(parents=True)
                (root / "runtime/mesh").mkdir(parents=True)
                (root / "targets/hetero").mkdir(parents=True)
                (root / "pipeline/run_hetero.py").write_text("run")
                (root / "pipeline/hetero_platform/mapper.py").write_text("mapper")
                (root / "runtime/mesh/cluster_main.c").write_text("cluster")
                (root / "targets/hetero/system.py").write_text("target")
                (root / "README.md").write_text("one")
            first = capture_run_provenance(a)
            (Path(a) / "README.md").write_text("two")
            unchanged = capture_run_provenance(a)
            (Path(a) / "runtime/mesh/cluster_main.c").write_text("changed")
            changed = capture_run_provenance(a)
            other = capture_run_provenance(b)
        self.assertEqual(first["source_set"]["digest"], unchanged["source_set"]["digest"])
        self.assertNotEqual(first["source_set"]["digest"], changed["source_set"]["digest"])
        self.assertEqual(first["source_set"]["digest"], other["source_set"]["digest"])
        self.assertFalse(first["k9r5"]["available"])


if __name__ == "__main__":
    unittest.main()
