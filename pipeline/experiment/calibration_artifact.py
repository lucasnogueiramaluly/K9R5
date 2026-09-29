"""Identity, provenance and cache validation for K9R5 calibration artifacts.

`rates.json` stays in its existing format so the mapper remains backward
compatible.  A sidecar `calibration.json` records what produced that table and
is required before a cached table may be reused.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .fingerprint import file_digest, file_set_digest, fingerprint
from .provenance import (
    git_snapshot,
    git_snapshot_optional,
    patch_digests,
    toolchain_snapshot,
)

SCHEMA_VERSION = 1
KIND = "k9r5.calibration"
PROTOCOL_ID = "mesh_calib_v1"

_SOURCE_SUFFIXES = {".c", ".h", ".S", ".s", ".ld", ".py", ".json"}


def _git_identity(snapshot: dict) -> dict:
    """Fields of a Git snapshot that affect source identity.

    The remote URL is provenance, not semantics: changing github.com syntax or
    cloning from a mirror must not invalidate an otherwise identical artifact.
    """
    return {
        "revision": snapshot["revision"],
        "dirty": snapshot["dirty"],
        "diff_digest": snapshot["diff_digest"],
        "untracked_digest": snapshot["untracked_digest"],
    }


def _files_under(path: Path) -> list[Path]:
    if not path.exists():
        return []
    return sorted(
        p for p in path.rglob("*")
        if p.is_file() and p.suffix in _SOURCE_SUFFIXES
    )


def calibration_source_files(root: Path | str) -> list[Path]:
    """K9R5 sources that can change the calibration result.

    Documentation and unrelated application code are intentionally excluded:
    changing README text should not invalidate a measured cost table.
    """
    root = Path(root).resolve()
    explicit = [
        root / "pipeline" / "build_mesh.py",
        root / "pipeline" / "gen_system_header.py",
        root / "pipeline" / "sweep" / "calibrate.py",
        root / "pipeline" / "sweep" / "design.py",
        root / "pipeline" / "sweep" / "run.py",
        root / "pipeline" / "experiment" / "calibration_artifact.py",
        root / "runtime" / "tests" / "mesh_calib.c",
    ]
    trees = [
        root / "runtime" / "mesh",
        root / "runtime" / "common",
        root / "runtime" / "snitch",
        root / "runtime" / "spatz",
        root / "targets" / "hetero",
    ]
    paths = [p for p in explicit if p.is_file()]
    for tree in trees:
        paths.extend(_files_under(tree))
    # A file may be named explicitly and also live under a selected tree.
    return sorted(set(paths))


def _dependency_snapshot(path: Path, name: str) -> dict:
    if not path.is_dir():
        raise FileNotFoundError(f"required dependency checkout is missing: {path}")
    return git_snapshot(path, name=name)


def capture_calibration_context(root: Path | str, design: dict, host: str) -> dict:
    """Capture current calibration inputs and full source provenance."""
    root = Path(root).resolve()
    if host not in ("cva6", "ara"):
        raise ValueError(f"unsupported calibration host: {host}")

    deeploy = _dependency_snapshot(root / "deps" / "deeploy", "deeploy")
    gvsoc = _dependency_snapshot(root / "deps" / "gvsoc", "gvsoc")
    gvsoc_core = _dependency_snapshot(root / "deps" / "gvsoc" / "core", "gvsoc-core")

    patches = sorted((root / "deps" / "patches").glob("gvsoc-core-*.patch"))
    gcc = root / "toolchains" / "xpack-riscv-none-elf-gcc-15.2.0-1" / "bin" / "riscv-none-elf-gcc"
    simulator = root / "deps" / "gvsoc" / "install" / "bin" / "gvsoc"

    if not gcc.is_file():
        raise FileNotFoundError(f"required toolchain executable is missing: {gcc}")
    if not simulator.is_file():
        raise FileNotFoundError(f"required simulator executable is missing: {simulator}")

    sources = calibration_source_files(root)
    inputs = {
        "schema_version": SCHEMA_VERSION,
        "protocol": PROTOCOL_ID,
        "host": host,
        "simulator_target": "hetero_ara" if host == "ara" else "hetero_soc",
        "design": design,
        "k9r5_calibration_sources": file_set_digest(root, sources),
        "dependencies": {
            "deeploy": _git_identity(deeploy),
            "gvsoc": _git_identity(gvsoc),
            "gvsoc_core": _git_identity(gvsoc_core),
        },
        "patches": patch_digests(root, patches),
        "toolchain": toolchain_snapshot(gcc),
        "simulator_binary_digest": file_digest(simulator),
    }

    return {
        "input": inputs,
        "input_fingerprint": fingerprint(inputs),
        "provenance": {
            "k9r5": git_snapshot_optional(root, name="k9r5"),
            "deeploy": deeploy,
            "gvsoc": gvsoc,
            "gvsoc_core": gvsoc_core,
        },
    }


def cache_status(rates_path: Path | str, metadata_path: Path | str,
                 input_fingerprint: str) -> tuple[bool, str]:
    """Whether an existing rates table is valid for the current inputs."""
    rates_path = Path(rates_path)
    metadata_path = Path(metadata_path)

    if not rates_path.is_file():
        return False, "rates-missing"
    if not metadata_path.is_file():
        return False, "metadata-missing"

    try:
        metadata = json.loads(metadata_path.read_text())
    except (OSError, ValueError):
        return False, "metadata-invalid"

    if metadata.get("schema_version") != SCHEMA_VERSION:
        return False, "schema-mismatch"
    if metadata.get("kind") != KIND:
        return False, "kind-mismatch"
    if metadata.get("input_fingerprint") != input_fingerprint:
        return False, "input-mismatch"

    rates = metadata.get("artifacts", {}).get("rates", {})
    if rates.get("digest") != file_digest(rates_path):
        return False, "rates-digest-mismatch"

    return True, "hit"


def _relative_artifact(base: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.name


def write_metadata(metadata_path: Path | str, context: dict,
                   rates_path: Path | str, log_path: Path | str) -> Path:
    """Write the sidecar only after a successful calibration."""
    metadata_path = Path(metadata_path)
    rates_path = Path(rates_path)
    log_path = Path(log_path)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    blob = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "protocol": PROTOCOL_ID,
        "input_fingerprint": context["input_fingerprint"],
        "input": context["input"],
        "provenance": context["provenance"],
        "artifacts": {
            "rates": {
                "path": _relative_artifact(metadata_path.parent, rates_path),
                "digest": file_digest(rates_path),
            },
            "raw_log": {
                "path": _relative_artifact(metadata_path.parent, log_path),
                "digest": file_digest(log_path),
            },
        },
    }
    metadata_path.write_text(json.dumps(blob, indent=2, sort_keys=True) + "\n")
    return metadata_path
