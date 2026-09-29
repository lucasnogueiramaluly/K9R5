"""Minimal per-run manifest for reproducible K9R5 sweep cells."""

from __future__ import annotations

import json
from pathlib import Path

from .fingerprint import file_digest, fingerprint

SCHEMA_VERSION = 1
KIND = "k9r5.run"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise RuntimeError(f"cannot read JSON artifact {path}: {exc}") from exc


def build_run_manifest(
    *,
    request: dict,
    resolved: dict,
    actual: dict,
    calibration_path: Path | str,
    result_path: Path | str,
    base_dir: Path | str | None = None,
) -> dict:
    """Build a compact manifest without changing execution behavior."""
    calibration_path = Path(calibration_path)
    result_path = Path(result_path)
    calibration = _read_json(calibration_path)

    if calibration.get("kind") != "k9r5.calibration":
        raise RuntimeError(f"unexpected calibration artifact kind: {calibration.get('kind')!r}")
    if not calibration.get("input_fingerprint"):
        raise RuntimeError("calibration artifact has no input_fingerprint")

    base = Path(base_dir) if base_dir is not None else result_path.parent

    def rel(path: Path) -> str:
        try:
            return path.resolve().relative_to(base.resolve()).as_posix()
        except ValueError:
            return path.name

    result_digest = file_digest(result_path)
    calibration_digest = file_digest(calibration_path)

    identity = {
        "request": request,
        "resolved": resolved,
        "actual": actual,
        "calibration_input_fingerprint": calibration["input_fingerprint"],
        "calibration_metadata_digest": calibration_digest,
        "result_digest": result_digest,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "run_fingerprint": fingerprint(identity),
        "request": request,
        "resolved": resolved,
        "actual": actual,
        "calibration": {
            "path": rel(calibration_path),
            "input_fingerprint": calibration["input_fingerprint"],
            "metadata_digest": calibration_digest,
        },
        "provenance": calibration.get("provenance", {}),
        "artifacts": {
            "result": {
                "path": rel(result_path),
                "digest": result_digest,
            }
        },
    }


def write_run_manifest(
    path: Path | str,
    *,
    request: dict,
    resolved: dict,
    actual: dict,
    calibration_path: Path | str,
    result_path: Path | str,
    base_dir: Path | str | None = None,
) -> dict:
    path = Path(path)
    manifest = build_run_manifest(
        request=request,
        resolved=resolved,
        actual=actual,
        calibration_path=calibration_path,
        result_path=result_path,
        base_dir=base_dir,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
