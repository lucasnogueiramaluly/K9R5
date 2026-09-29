"""Derived, descriptive resources for a resolved K9R5 design.

This module does not configure the simulator. The operational sources remain
``targets/hetero/system.py`` and ``targets/hetero/soc.py``; the constants below
document invariants that those sources assert while constructing the current
legacy GVSoC target.
"""

from __future__ import annotations

from typing import Mapping


TCDM_SUPERBANKS = 4
TCDM_BANKS_PER_SUPERBANK = 8
TCDM_BANK_COUNT = TCDM_SUPERBANKS * TCDM_BANKS_PER_SUPERBANK


def _cluster_summary(
    *,
    modeled_cores: int,
    tcdm_size_bytes: int,
    staging_required: bool,
) -> dict:
    """Resources shared by the two current cluster constructions."""
    compute_cores = modeled_cores - 1
    return {
        "modeled_cores": modeled_cores,
        "compute_cores": compute_cores,
        "control_dma_cores": 1,
        "tcdm": {
            "capacity_bytes": tcdm_size_bytes,
            "bank_count": TCDM_BANK_COUNT,
            "superbanks": TCDM_SUPERBANKS,
            "banks_per_superbank": TCDM_BANKS_PER_SUPERBANK,
            "bank_size_bytes": tcdm_size_bytes // TCDM_BANK_COUNT,
        },
        "memory_path": {
            "kernel_operand_staging_required": staging_required,
            "cluster_dma_to_main_memory": "wide_axi",
        },
    }


def build_resource_summary(design: Mapping[str, int]) -> dict:
    """Describe resources implied by an already validated resolved design.

    Values are calculated from the resolved design passed by the existing
    resolver. This is descriptive metadata, not a second source of hardware
    configuration or a claim about measured throughput.
    """
    tcdm_size = design["TCDM_SIZE"]
    snitch = _cluster_summary(
        modeled_cores=design["SNITCH_NB_CORE"],
        tcdm_size_bytes=tcdm_size,
        staging_required=False,
    )
    spatz = _cluster_summary(
        modeled_cores=design["SPATZ_NB_CORE"],
        tcdm_size_bytes=tcdm_size,
        staging_required=True,
    )
    spatz_compute = spatz["compute_cores"]
    spatz_lanes = design["SPATZ_NB_LANES"]
    spatz["spatz_vector"] = {
        "lanes_per_modeled_core": spatz_lanes,
        "lanes_per_compute_core": spatz_lanes,
        "modeled_vpu_cores": spatz["modeled_cores"],
        "useful_vpu_cores": spatz_compute,
        "modeled_vector_lanes": spatz["modeled_cores"] * spatz_lanes,
        "useful_vector_lanes": spatz_compute * spatz_lanes,
    }
    spatz["memory_path"]["wide_axi_width_bytes_per_cycle"] = design["WIDE_AXI_WIDTH"]

    return {
        "schema_version": 1,
        "platform": {
            "host_modeled_cores": 1,
            "cluster_modeled_cores": snitch["modeled_cores"] + spatz["modeled_cores"],
            "total_modeled_cores": 1 + snitch["modeled_cores"] + spatz["modeled_cores"],
        },
        "clusters": {
            "snitch": snitch,
            "spatz": spatz,
        },
    }
