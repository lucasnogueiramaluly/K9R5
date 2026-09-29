"""Source and tool provenance primitives for K9R5."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterable, Sequence

from .fingerprint import file_digest, fingerprint, sha256_bytes


def _run_bytes(repo: Path, args: Sequence[str]) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.stdout


def _run_text(repo: Path, args: Sequence[str]) -> str:
    return _run_bytes(repo, args).decode("utf-8", errors="strict").strip()


def _untracked_manifest(repo: Path) -> list[dict]:
    raw = _run_bytes(repo, ["ls-files", "--others", "--exclude-standard", "-z"])
    names = [p.decode("utf-8") for p in raw.split(b"\0") if p]
    records = []
    for name in sorted(names):
        path = repo / name
        if path.is_symlink():
            payload = ("symlink\0" + os.readlink(path)).encode("utf-8")
            digest = sha256_bytes(payload)
            kind = "symlink"
        elif path.is_file():
            digest = file_digest(path)
            kind = "file"
        else:
            digest = fingerprint({"kind": "other"})
            kind = "other"
        records.append({"path": Path(name).as_posix(), "kind": kind, "digest": digest})
    return records


def git_snapshot(repo: Path | str, name: str | None = None) -> dict:
    repo = Path(repo).resolve()
    revision = _run_text(repo, ["rev-parse", "HEAD"])
    try:
        repository = _run_text(repo, ["config", "--get", "remote.origin.url"]) or None
    except subprocess.CalledProcessError:
        repository = None
    tracked_diff = _run_bytes(repo, ["diff", "--binary", "HEAD", "--", "."])
    untracked = _untracked_manifest(repo)
    return {
        "name": name or repo.name,
        "repository": repository,
        "revision": revision,
        "dirty": bool(tracked_diff or untracked),
        "diff_digest": sha256_bytes(tracked_diff) if tracked_diff else None,
        "untracked_digest": fingerprint(untracked) if untracked else None,
    }


def git_snapshot_optional(repo: Path | str, name: str | None = None) -> dict:
    """Capture Git provenance when metadata is available.

    Runtime containers may intentionally contain the exact K9R5 source tree
    without its `.git` directory. That must not make an otherwise reproducible
    experiment impossible: causal source identity is tracked separately by file
    digests. Dependency checkouts that participate in the calibration
    fingerprint continue to use strict `git_snapshot()`.
    """
    repo = Path(repo).resolve()
    try:
        snapshot = git_snapshot(repo, name=name)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {
            "name": name or repo.name,
            "available": False,
            "reason": "git-metadata-unavailable",
            "repository": None,
            "revision": None,
            "dirty": None,
            "diff_digest": None,
            "untracked_digest": None,
        }
    return {"available": True, **snapshot}


def patch_digests(root: Path | str, paths: Iterable[Path | str]) -> list[dict]:
    root = Path(root).resolve()
    records = []
    for value in paths:
        path = Path(value)
        absolute = path if path.is_absolute() else root / path
        absolute = absolute.resolve()
        try:
            relative = absolute.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"patch is outside provenance root: {value}") from exc
        records.append({"path": relative.as_posix(), "digest": file_digest(absolute)})
    records.sort(key=lambda item: item["path"])
    return records


def toolchain_snapshot(executable: Path | str,
                       version_args: Sequence[str] = ("--version",)) -> dict:
    executable = Path(executable).resolve()
    proc = subprocess.run(
        [str(executable), *version_args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    version = (proc.stdout or proc.stderr).strip()
    return {
        "executable": executable.name,
        "version": version,
        "binary_digest": file_digest(executable),
    }
