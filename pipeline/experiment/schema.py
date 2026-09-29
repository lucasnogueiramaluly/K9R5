"""Pure experiment-description types for the K9R5 workbench."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping


@dataclass(frozen=True)
class WorkloadSpec:
    path: str
    content_digest: str
    application: str | None
    opset: tuple[dict, ...]
    inputs: tuple[dict, ...]
    outputs: tuple[dict, ...]
    node_count: int
    op_counts: tuple[tuple[str, int], ...]
    initializer_count: int
    descriptors: Mapping[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "content_digest": self.content_digest,
            "application": self.application,
            "opset": [dict(x) for x in self.opset],
            "inputs": [dict(x) for x in self.inputs],
            "outputs": [dict(x) for x in self.outputs],
            "node_count": self.node_count,
            "op_counts": dict(self.op_counts),
            "initializer_count": self.initializer_count,
            "descriptors": dict(self.descriptors),
        }


@dataclass(frozen=True)
class ExperimentRequest:
    platform: str = "k9r5_current"
    workload: str = ""
    design_overrides: tuple[tuple[str, int], ...] = ()
    host: str = "cva6"
    mapping_strategy: str = "measured_rate_greedy"
    pin: str | None = None
    frontend: str | None = None
    serial: bool = False
    power: bool = False

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "ExperimentRequest":
        allowed = {
            "platform", "workload", "design_overrides", "host",
            "mapping_strategy", "pin", "frontend", "serial", "power",
        }
        unknown = set(data) - allowed
        if unknown:
            raise ValueError(f"unknown ExperimentRequest fields: {sorted(unknown)}")
        overrides = data.get("design_overrides", {})
        if not isinstance(overrides, Mapping):
            raise ValueError("design_overrides must be an object")
        pairs = []
        for key, value in overrides.items():
            if not isinstance(key, str):
                raise ValueError("design_overrides keys must be strings")
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"design override {key!r} must be an integer")
            pairs.append((key, value))
        kwargs = dict(data)
        kwargs["design_overrides"] = tuple(sorted(pairs))
        return cls(**kwargs)

    def overrides_dict(self) -> dict[str, int]:
        return dict(self.design_overrides)

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "workload": self.workload,
            "design_overrides": self.overrides_dict(),
            "host": self.host,
            "mapping_strategy": self.mapping_strategy,
            "pin": self.pin,
            "frontend": self.frontend,
            "serial": self.serial,
            "power": self.power,
        }


@dataclass(frozen=True)
class ResolvedExperiment:
    schema_version: int
    platform: str
    hardware: Mapping[str, object]
    resources: Mapping[str, object]
    host_profile: str
    simulator: Mapping[str, object]
    software: Mapping[str, object]
    workload: WorkloadSpec
    mapping: Mapping[str, object]
    execution: Mapping[str, object]

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "platform": self.platform,
            "hardware": dict(self.hardware),
            "resources": dict(self.resources),
            "host_profile": self.host_profile,
            "simulator": dict(self.simulator),
            "software": dict(self.software),
            "workload": self.workload.to_dict(),
            "mapping": dict(self.mapping),
            "execution": dict(self.execution),
        }
