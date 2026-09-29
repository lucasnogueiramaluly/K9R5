"""Descriptive catalog for K9R5 logical execution engines.

This module is metadata only. It does not own engine IDs, runtime macros,
capability rules, mapping policy, or execution behavior.

Operational sources remain:
  - targets/hetero/system.py for engine IDs/names
  - pipeline/hetero_platform/progress.py for runtime engine macros
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping


@dataclass(frozen=True)
class EngineMeta:
    label: str
    kind: str
    deployment_engine: str
    description: str


META: dict[str, EngineMeta] = {
    "cva6": EngineMeta(
        label="CVA6 host",
        kind="host",
        deployment_engine="Cva6HostEngine",
        description=(
            "Logical host engine. The scalar CVA6 and CVA6+Ara boards are "
            "hardware/host profiles of this same logical engine."
        ),
    ),
    "snitch": EngineMeta(
        label="Snitch cluster",
        kind="cluster",
        deployment_engine="SnitchClusterEngine",
        description="Snitch cluster offload engine.",
    ),
    "spatz": EngineMeta(
        label="Spatz cluster",
        kind="cluster",
        deployment_engine="SpatzClusterEngine",
        description="Spatz/RVV cluster offload engine.",
    ),
}


def build_catalog(
    engine_names: Mapping[int, str],
    runtime_macros: Mapping[str, str],
) -> list[dict]:
    """Merge descriptive metadata with the current operational identities.

    Refuse drift rather than silently inventing/dropping an engine.
    """
    ids_by_name = {name: system_id for system_id, name in engine_names.items()}
    if len(ids_by_name) != len(engine_names):
        raise RuntimeError("architectural engine names are not unique")

    metadata_names = set(META)
    architectural_names = set(ids_by_name)
    runtime_names = set(runtime_macros)

    if architectural_names != metadata_names:
        raise RuntimeError(
            "engine metadata drift against targets/hetero/system.py: "
            f"architecture_only={sorted(architectural_names - metadata_names)}, "
            f"metadata_only={sorted(metadata_names - architectural_names)}"
        )

    if runtime_names != metadata_names:
        raise RuntimeError(
            "engine metadata drift against pipeline/hetero_platform/progress.py: "
            f"runtime_only={sorted(runtime_names - metadata_names)}, "
            f"metadata_only={sorted(metadata_names - runtime_names)}"
        )

    rows = []
    for system_id, name in sorted(engine_names.items()):
        rows.append({
            "name": name,
            "system_id": system_id,
            **asdict(META[name]),
            "runtime_macro": runtime_macros[name],
            "architectural_source": "targets/hetero/system.py",
            "runtime_macro_source": "pipeline/hetero_platform/progress.py",
        })
    return rows
