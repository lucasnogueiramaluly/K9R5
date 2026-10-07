# SPDX-License-Identifier: Apache-2.0
"""Small source, Git, patch, and executable provenance primitives for M4IA."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterable, Sequence
from pathlib import Path

from .fingerprint import file_digest, fingerprint, sha256_bytes


SOURCE_SUFFIXES = frozenset({
    ".S",
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".json",
    ".ld",
    ".py",
    ".s",
})


def source_files_under(path: Path | str) -> list[Path]:
    """Return deterministic source files under ``path`` using safe suffixes."""
    path = Path(path)
    if not path.exists():
        return []
    return sorted(
        candidate
        for candidate in path.rglob("*")
        if candidate.is_file() and candidate.suffix in SOURCE_SUFFIXES
    )


def _run_bytes(repo: Path, args: Sequence[str]) -> bytes:
    process = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return process.stdout


def _run_text(repo: Path, args: Sequence[str]) -> str:
    return _run_bytes(repo, args).decode("utf-8", errors="strict").strip()


def _untracked_manifest(repo: Path) -> list[dict]:
    raw = _run_bytes(repo, ["ls-files", "--others", "--exclude-standard", "-z"])
    names = [item.decode("utf-8") for item in raw.split(b"\0") if item]
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
    """Capture Git provenance, including dirty tracked and untracked content."""
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
    """Capture Git provenance or explicitly report absent Git metadata."""
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


def semantic_git_identity(snapshot: dict) -> dict:
    """Return causal Git fields, deliberately excluding name and remote URL."""
    if snapshot.get("available") is False:
        return {
            "available": False,
            "revision": None,
            "dirty": None,
            "diff_digest": None,
            "untracked_digest": None,
        }
    return {
        "available": True,
        "revision": snapshot.get("revision"),
        "dirty": snapshot.get("dirty"),
        "diff_digest": snapshot.get("diff_digest"),
        "untracked_digest": snapshot.get("untracked_digest"),
    }


def patch_digests(root: Path | str, paths: Iterable[Path | str]) -> list[dict]:
    """Digest patches relative to ``root``; reject paths outside that root."""
    root = Path(root).resolve()
    records = []
    for value in paths:
        path = Path(value)
        absolute = (path if path.is_absolute() else root / path).resolve()
        try:
            relative = absolute.relative_to(root)
        except ValueError as error:
            raise ValueError(f"patch is outside provenance root: {value}") from error
        records.append({"path": relative.as_posix(), "digest": file_digest(absolute)})
    return sorted(records, key=lambda item: item["path"])


def toolchain_snapshot(
    executable: Path | str,
    version_args: Sequence[str] = ("--version",),
) -> dict:
    """Capture executable basename, version output, and binary content digest."""
    executable = Path(executable).resolve()
    if not executable.is_file():
        raise FileNotFoundError(f"required executable is missing: {executable}")
    process = subprocess.run(
        [str(executable), *version_args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return {
        "executable": executable.name,
        "version": (process.stdout or process.stderr).strip(),
        "binary_digest": file_digest(executable),
    }


def binary_snapshot(executable: Path | str) -> dict:
    """Capture a binary identity without assuming it has a version command."""
    executable = Path(executable).resolve()
    if not executable.is_file():
        raise FileNotFoundError(f"required executable is missing: {executable}")
    return {
        "executable": executable.name,
        "binary_digest": file_digest(executable),
    }
