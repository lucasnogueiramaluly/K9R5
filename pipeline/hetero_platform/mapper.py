# SPDX-License-Identifier: Apache-2.0
"""Choosing which core runs each node.

Deeploy's default EngineMapper takes the first engine that says it can execute
a node, which makes the answer depend on the order the engines happen to be
listed in. This one picks the cheapest, from a cost model seeded with the
per-core measurements this repository already has in results/.

The model is deliberately crude, because it only has to get the *ordering*
right, and the ordering is what the measurements establish:

    cost = offload_overhead(engine) + macs(node) / rate(engine, op)

`rate` is MACs per cycle, derived from results/: for each measured operator,
the MAC count of that benchmark divided by the cycles each core took. The
Snitch cluster's rate is the single-core Xssr/Xfrep rate multiplied by the
eight compute cores it splits the work over. `offload_overhead` is what a job
costs before any arithmetic happens -- mailbox write, doorbell, DMA staging,
completion -- measured by make mesh-test.

The overhead term is the part that matters: it is what stops a small node
being shipped to a cluster that would finish the arithmetic quickly and spend
ten times longer getting the data there and back.

Named operator rates and offload terms are measurements or arithmetic
consequences of them. `_default` is the documented conservative proxy for an
operator with no row and is never presented as that operator's measurement.
--pin overrides only compatible-node selection, not whole-graph execution.
"""

import json
import os
from pathlib import Path
from typing import Dict, Mapping, Optional

import onnx_graphsurgeon as gs

from Deeploy.DeeployTypes import DeploymentEngine
from Deeploy.EngineExtension.OptimizationPasses.TopologyOptimizationPasses.EngineColoringPasses import EngineMapper

from .engines import ClusterEngine, _all_fp32, working_set_bytes

# MACs per cycle, per engine and operator class.
#
# The two cluster rows are measured by `make mesh-test`, which runs exactly the
# configuration this model is predicting: eight compute cores, operands staged
# into TCDM, on the SoC. A rate is that benchmark's MAC count over its measured
# cycles, so it already carries the in-cluster overhead at that problem size;
# OFFLOAD_FIXED below covers the host-side round trip on top.
#
#   GEMM/MatMul  32x32x32          =  32,768 MACs
#   Conv2d       4x16x16 -> 8x3x3  =  56,448 MACs
#
# The cva6 row comes from results/, where the same shapes were measured on the
# standalone board.
#
# Both clusters have eight compute cores, so these are like-for-like. Spatz
# leads on all three because its kernels vectorize the output columns -- see
# runtime/spatz/kernels/gemm_fp32_rvv.c for why that matters so much.
#
# The ara row prices the same host with its Ara vector unit (--host ara): the
# cva6 row scaled by how many fewer cycles each benchmark took under
# `pipeline/run.py --cores cva6,ara` -- GEMM/Regular 1.65x and mymatmul 1.64x
# faster, Conv/Regular_2D_Bias 0.63x, because GCC gathers the convolution
# window and the vector unit issues a gather one element per burst.
RATES: Dict[str, Dict[str, float]] = {
    "cva6": {"Gemm": 0.067, "MatMul": 0.075, "Conv": 0.070, "_default": 0.070},
    "ara": {"Gemm": 0.111, "MatMul": 0.123, "Conv": 0.044, "_default": 0.044},
    "snitch": {"Gemm": 4.52, "MatMul": 4.07, "Conv": 0.59, "_default": 0.59},
    "spatz": {"Gemm": 11.91, "MatMul": 16.79, "Conv": 0.65, "_default": 0.65},
}

# Cycles a job costs before any arithmetic: the mailbox write, the doorbell,
# waking the control core, and the completion handshake. Charged per offload so
# a node too small to be worth shipping stays on the host.
OFFLOAD_FIXED = {"cva6": 0, "snitch": 1200, "spatz": 1200}

# Cycles per byte staged into TCDM and back, from the same measurements.
OFFLOAD_PER_BYTE = {"cva6": 0.0, "snitch": 0.10, "spatz": 0.10}

RATE_TABLE_PROVENANCE = {
    "kind": "committed_measurement_table",
    "source": "pipeline/hetero_platform/mapper.py",
}


def _rate_table_provenance(path: Path) -> dict:
    """Describe an externally loaded table without claiming it was measured."""
    provenance = {"kind": "external_rate_table", "rates_path": str(path)}
    metadata_path = path.with_name("calibration.json")
    try:
        metadata = json.loads(metadata_path.read_text())
    except (OSError, ValueError):
        return provenance
    if (metadata.get("kind") == "k9r5.calibration"
            and metadata.get("input_fingerprint")):
        provenance.update({
            "kind": "calibration_artifact",
            "calibration_path": str(metadata_path),
            "calibration_input_fingerprint": metadata["input_fingerprint"],
            "rates_digest": metadata.get("artifacts", {}).get("rates", {}).get("digest"),
        })
    return provenance


# A design-space sweep changes the very hardware these numbers measure, so a
# swept design would otherwise be mapped by another machine's arithmetic -- a
# 16-lane Spatz kept being handed work at a 4-lane Spatz's prices. Each design
# point re-measures the whole table with runtime/tests/mesh_calib.c and points
# HES_RATES at the result; see pipeline/sweep/calibrate.py.
#
# Unset, the committed tables above are used unchanged, so nothing about the
# existing pipeline moves.
def _load_measured_tables() -> None:
    global RATE_TABLE_PROVENANCE
    path = os.environ.get("HES_RATES")
    if not path:
        return
    blob = json.loads(Path(path).read_text())
    for name, table in (("RATES", RATES), ("OFFLOAD_FIXED", OFFLOAD_FIXED),
                        ("OFFLOAD_PER_BYTE", OFFLOAD_PER_BYTE)):
        measured = blob.get(name)
        if measured is None:
            raise RuntimeError(f"{path} has no {name} -- it is not a table "
                               "produced by pipeline/sweep/calibrate.py")
        # Replace rather than merge: a partial table would silently mix two
        # machines' measurements, which is the whole failure this avoids. The
        # host row is the exception -- it is named for the board (cva6/ara) and
        # the calibration only ever measures the one it ran on.
        if not isinstance(measured, dict):
            raise RuntimeError(f"{path} has a non-object {name} table")
        table.clear()
        table.update(measured)
    RATE_TABLE_PROVENANCE = _rate_table_provenance(Path(path))


_load_measured_tables()


def _static_shape(tensor):
    shape = getattr(tensor, "shape", None)
    if not shape or any(not isinstance(dimension, int) for dimension in shape):
        return None
    return list(shape)


def node_macs(node: gs.Node) -> float | None:
    """Current MAC estimate, or None when the needed shape is unknown."""
    output = _static_shape(node.outputs[0]) if node.outputs else None
    if output is None:
        return None
    output_elements = 1
    for dimension in output:
        output_elements *= dimension
    if node.op in ("Gemm", "MatMul"):
        if len(node.inputs) < 2:
            return None
        left = _static_shape(node.inputs[0])
        return output_elements * left[-1] if left else None
    if node.op == "Conv":
        if len(node.inputs) < 2:
            return None
        weights = _static_shape(node.inputs[1])
        if weights is None:
            return None
        taps = 1
        for dimension in weights[1:]:
            taps *= dimension
        return output_elements * taps
    return float(output_elements)


def deterministic_generic_fallback(engine_name: str, node: gs.Node) -> str | None:
    """Known whole-kernel fallbacks that cannot use a tuned rate safely."""
    if engine_name not in {"snitch", "spatz"} or node.op not in {"MatMul", "Gemm"}:
        return None
    if len(node.inputs) < 2:
        return None
    left = _static_shape(node.inputs[0])
    right = _static_shape(node.inputs[1])
    if left is None or right is None or len(left) < 2 or len(right) < 2:
        return None
    attributes = getattr(node, "attrs", {})
    if not isinstance(attributes, Mapping):
        return None
    trans_a = attributes.get("transA", 0) if node.op == "Gemm" else 0
    trans_b = attributes.get("transB", 0) if node.op == "Gemm" else 0
    if (not isinstance(trans_a, int) or isinstance(trans_a, bool)
            or not isinstance(trans_b, int) or isinstance(trans_b, bool)):
        return None
    m = left[-1] if trans_a else left[-2]
    n = left[-2] if trans_a else left[-1]
    o = right[-2] if trans_b else right[-1]
    if engine_name == "snitch":
        if m == 0 or n == 0:
            return "empty_input_dimension"
        if o < 8:
            return "output_columns_below_ssr_unroll"
        return None
    if m == 0 or n == 0 or o == 0:
        return "empty_dimension"
    if node.op == "Gemm" and (trans_a or trans_b):
        return "transposed_operand"
    return None


class CostEngineMapper(EngineMapper):
    """Pick the engine whose modelled cost for the node is lowest.

    `pin` forces every node the named engine can execute onto it, which is what
    the mapped-versus-pinned comparison uses.

    `host` is the orchestrator the board carries -- the scalar CVA6, or the
    same core with an Ara vector unit -- and picks the rates the host engine is
    priced at. The engine is called cva6 on both boards, but the two cores run
    the same node at very different speeds, so pricing the vector host at the
    scalar rates would offload work it does faster in place.
    """

    def __init__(self, engineDict: Dict[str, DeploymentEngine],
                 pin: Optional[str] = None, host: str = "cva6") -> None:
        super().__init__(engineDict)
        self.pin = pin
        self.host = host
        self.decisions = []  #: (node name, op, engine, cost) for the report
        self.explanations = []

    def cost_breakdown(self, engine: DeploymentEngine, node: gs.Node) -> dict:
        """Return a safe current-model cost, or explicit unavailability."""
        fallback_reason = deterministic_generic_fallback(engine.name, node)
        if fallback_reason is not None:
            return {
                "evaluated": False,
                "reason": "deterministic_generic_fallback_has_no_generic_rate",
                "fallback_reason": fallback_reason,
            }
        if engine.name == "cva6":
            rates = RATES.get(self.host)
            table_source = {"kind": "host_profile", "host": self.host}
            missing_reason = "missing_host_rate_row"
        else:
            rates = RATES.get(engine.name)
            table_source = {"kind": "engine_rate_row", "engine": engine.name}
            missing_reason = "missing_engine_rate_row"
        if not isinstance(rates, dict):
            return {"evaluated": False, "reason": missing_reason,
                    "rate_row": table_source}
        rate_key = node.op if node.op in rates else "_default"
        rate = rates.get(rate_key)
        if not isinstance(rate, (int, float)) or isinstance(rate, bool) or rate <= 0:
            return {"evaluated": False, "reason": "missing_or_invalid_operator_rate",
                    "rate_key": rate_key, "rate_table": dict(RATE_TABLE_PROVENANCE),
                    "rate_row": table_source}
        macs = node_macs(node)
        if macs is None:
            return {"evaluated": False, "reason": "shape_derived_macs_unavailable",
                    "rate_key": rate_key, "rate_table": dict(RATE_TABLE_PROVENANCE),
                    "rate_row": table_source}
        fixed = 0
        bytes_staged = None
        per_byte = 0.0
        if isinstance(engine, ClusterEngine):
            bytes_staged = working_set_bytes(node)
            if bytes_staged is None:
                return {"evaluated": False, "reason": "working_set_bytes_unavailable"}
            if engine.name not in OFFLOAD_FIXED or engine.name not in OFFLOAD_PER_BYTE:
                return {"evaluated": False, "reason": "missing_cluster_offload_cost"}
            fixed = OFFLOAD_FIXED[engine.name]
            per_byte = OFFLOAD_PER_BYTE[engine.name]
        transfer = per_byte * bytes_staged if bytes_staged is not None else 0.0
        return {
            "evaluated": True,
            "macs": macs,
            "macs_source": "node_macs_current_mapper_estimate",
            "rate_macs_per_cycle": rate,
            "rate_key": rate_key,
            "rate_key_source": ("operator_rate" if rate_key == node.op
                                else "documented_default_proxy_not_measured_for_operator"),
            "rate_table": dict(RATE_TABLE_PROVENANCE),
            "rate_row": table_source,
            "fixed_offload_cycles": fixed,
            "fixed_offload_source": ("explicit_table_entry" if isinstance(engine, ClusterEngine)
                                       else "host_does_not_offload"),
            "working_set_bytes": bytes_staged,
            "per_byte_offload_cycles": per_byte if bytes_staged is not None else None,
            "transfer_offload_cycles": transfer if bytes_staged is not None else None,
            "total_estimated_cycles": macs / rate + fixed + transfer,
        }

    @staticmethod
    def _incompatibility_reason(engine: DeploymentEngine, node: gs.Node) -> str:
        if isinstance(engine, ClusterEngine):
            if not engine.enabled:
                return "cluster_engine_disabled"
            if node.op not in engine.Mapping:
                return "operator_not_in_cluster_mapping"
            if not _all_fp32(node):
                return "node_not_fp32"
            size = working_set_bytes(node)
            if size is None:
                return "working_set_bytes_unavailable"
            if size > engine.tcdm_budget:
                return "working_set_exceeds_tcdm_budget"
        if node.op not in engine.Mapping:
            return "operator_not_in_engine_mapping"
        return "engine_can_execute_returned_false"

    def _record_explanation(self, node: gs.Node, candidates, selected,
                            selected_cost, pin_selected: bool,
                            cost_details: dict | None = None) -> None:
        entries = []
        for engine in self.engineDict.values():
            compatible = engine in candidates
            retained = compatible and (not pin_selected or engine.name == self.pin)
            if compatible and cost_details is not None:
                cost = cost_details.get(engine.name, {
                    "evaluated": False, "reason": "cost_not_evaluated"})
            elif compatible and pin_selected:
                pin_cost = self.cost_breakdown(engine, node)
                cost = (pin_cost if not pin_cost.get("evaluated") else {
                    "evaluated": False,
                    "reason": "pin_selected_compatible_engine",
                    "availability": "safe_cost_not_used_for_selection",
                })
            else:
                cost = {"evaluated": False, "reason": "engine_incompatible"}
            if not compatible:
                pin_influence = ("pinned_engine_incompatible" if engine.name == self.pin
                                 else "incompatible_before_pin")
            elif self.pin is None:
                pin_influence = "not_requested"
            elif pin_selected and engine.name == self.pin:
                pin_influence = "retained_by_pin"
            elif pin_selected:
                pin_influence = "filtered_by_pin"
            else:
                pin_influence = "pin_not_applied"
            entries.append({
                "engine": engine.name,
                "compatible": compatible,
                "candidate_before_pin": compatible,
                "candidate_after_pin": retained,
                "exclusion_reason": None if compatible else self._incompatibility_reason(engine, node),
                "pin_influence": pin_influence,
                "cost": cost,
            })
        no_safe_cost = selected is None and bool(candidates)
        self.explanations.append({
            "strategy": "measured_rate_greedy",
            "node": node.name,
            "operator": node.op,
            "pin": self.pin,
            "pin_semantics": "compatible_node_preference_not_whole_graph",
            "candidates": entries,
            "selected_engine": selected.name if selected is not None else None,
            "selected_cost_cycles": selected_cost,
            "selection_rule": (
                "select_pinned_engine_when_compatible" if pin_selected else
                "minimum_total_estimated_cycles_among_compatible_engines; "
                "Python_min_preserves_engine_dictionary_order_on_exact_ties"
            ) if selected is not None else (
                "no_compatible_engine_with_safe_cost" if no_safe_cost
                else "no_compatible_engine"),
        })

    def cost(self, engine: DeploymentEngine, node: gs.Node) -> float | None:
        breakdown = self.cost_breakdown(engine, node)
        return breakdown["total_estimated_cycles"] if breakdown.get("evaluated") else None

    def mapNodeToEngine(self, node: gs.Node, graph: gs.Graph) -> Optional[DeploymentEngine]:
        _ = graph
        candidates = [engine for engine in self.engineDict.values() if engine.canExecute(node)]
        if not candidates:
            self._record_explanation(node, candidates, None, None, False)
            return None
        if self.pin is not None:
            pinned = self.engineDict.get(self.pin)
            if pinned is not None and pinned in candidates:
                self.decisions.append((node.name, node.op, pinned.name, None))
                self._record_explanation(node, candidates, pinned, None, True)
                return pinned
        cost_details = {engine.name: self.cost_breakdown(engine, node) for engine in candidates}
        priced = [(engine, details["total_estimated_cycles"])
                  for engine, details in ((engine, cost_details[engine.name]) for engine in candidates)
                  if details.get("evaluated")]
        if not priced:
            self._record_explanation(node, candidates, None, None, False, cost_details)
            return None
        best, best_cost = min(priced, key=lambda item: item[1])
        self.decisions.append((node.name, node.op, best.name, best_cost))
        self._record_explanation(node, candidates, best, best_cost, False, cost_details)
        return best


def make_mapper(pin: Optional[str] = None, host: str = "cva6"):
    """A CostEngineMapper factory the deployer can instantiate."""

    class _Mapper(CostEngineMapper):

        def __init__(self, engineDict):
            super().__init__(engineDict, pin = pin, host = host)
            _Mapper.last_instance = self

    _Mapper.last_instance = None
    return _Mapper
