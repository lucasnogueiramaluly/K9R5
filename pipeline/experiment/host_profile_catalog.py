"""Descriptive catalog for K9R5 host hardware/software profiles.

This module is metadata only. It does not choose the host, build images,
select simulator targets, or change mapping behavior.

Operational ownership remains in pipeline/build_mesh.py::HOSTS.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Mapping


@dataclass(frozen=True)
class HostProfileMeta:
    label: str
    logical_engine: str
    vector: bool
    description: str


META: dict[str, HostProfileMeta] = {
    "cva6": HostProfileMeta(
        label="Scalar CVA6 host",
        logical_engine="cva6",
        vector=False,
        description="Scalar CVA6 orchestrator used by hetero_soc.",
    ),
    "ara": HostProfileMeta(
        label="CVA6 + Ara host",
        logical_engine="cva6",
        vector=True,
        description=(
            "The same logical CVA6 host engine with Ara/RVV vector execution, "
            "used by hetero_ara."
        ),
    ),
}


def build_catalog(host_targets: Mapping[str, str]) -> list[dict]:
    """Merge descriptive metadata with current build-mesh host targets."""
    operational = set(host_targets)
    metadata = set(META)

    if operational != metadata:
        raise RuntimeError(
            "host-profile metadata drift against pipeline/build_mesh.py::HOSTS: "
            f"operational_only={sorted(operational - metadata)}, "
            f"metadata_only={sorted(metadata - operational)}"
        )

    rows = []
    for name in sorted(host_targets):
        rows.append({
            "name": name,
            **asdict(META[name]),
            "target": host_targets[name],
            "operational_source": "pipeline/build_mesh.py::HOSTS",
        })
    return rows
