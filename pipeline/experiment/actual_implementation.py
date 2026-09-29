"""Resolve source-grounded kernel implementation evidence for completed nodes."""

from __future__ import annotations

from typing import Mapping

EVIDENCE_TYPE = "deterministic_compiled_dispatch_and_runtime_evidence"
UNAVAILABLE_EVIDENCE_TYPE = "unavailable"

CVA6_GENERIC = "cva6.fp32.matmul_gemm.deeploy_generic"
SNITCH_TUNED = "snitch.fp32.matmul_gemm.ssr_frep"
SNITCH_GENERIC = "snitch.fp32.matmul_gemm.deeploy_generic_fallback"
SPATZ_TUNED = "spatz.fp32.matmul_gemm.rvv_tuned"
SPATZ_GENERIC = "spatz.fp32.matmul_gemm.deeploy_generic_fallback"


def _integer(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            return None
    return None


def _unknown(reason: str) -> dict:
    return {
        "implementation_id": None,
        "fallback_used": None,
        "fallback_from": None,
        "fallback_to": None,
        "fallback_reason": None,
        "implementation_detail": None,
        "evidence": {"type": UNAVAILABLE_EVIDENCE_TYPE, "reason": reason},
    }


def _known(implementation_id: str, *, fallback_used: bool,
           fallback_from: str | None = None, fallback_reason: str | None = None,
           implementation_detail: str | None = None) -> dict:
    return {
        "implementation_id": implementation_id,
        "fallback_used": fallback_used,
        "fallback_from": fallback_from,
        "fallback_to": implementation_id if fallback_used else None,
        "fallback_reason": fallback_reason,
        "implementation_detail": implementation_detail,
        "evidence": {
            "type": EVIDENCE_TYPE,
            "source": "completed runtime beacon plus generated offload arguments when required and compiled dispatch path",
        },
    }


def resolve_actual_implementation(node: Mapping[str, object]) -> dict:
    """Resolve one completed node without treating mapper placement as evidence.

    ``node`` must combine a runtime beacon's ``op``/``engine`` with the emitted
    offload arguments for that same generated node. Missing evidence stays
    unavailable rather than being inferred from the logical engine.
    """
    op = node.get("op")
    engine = node.get("engine")
    if op not in {"MatMul", "Gemm"}:
        return _unknown(f"no deterministic implementation rule for operator {op!r}")
    if engine == "cva6":
        return _known(CVA6_GENERIC, fallback_used=False)
    if engine not in {"snitch", "spatz"}:
        return _unknown(f"no deterministic implementation rule for engine {engine!r}")

    arguments = node.get("kernel_arguments")
    if not isinstance(arguments, Mapping):
        return _unknown("generated offload arguments are unavailable")
    m, n, o = (_integer(arguments.get(key)) for key in ("M", "N", "O"))
    if None in {m, n, o}:
        return _unknown("generated offload dimensions are incomplete or non-integer")

    if engine == "snitch":
        if m == 0 or n == 0:
            return _known(SNITCH_GENERIC, fallback_used=True,
                          fallback_from=SNITCH_TUNED,
                          fallback_reason="empty_input_dimension")
        if o < 8:
            return _known(SNITCH_GENERIC, fallback_used=True,
                          fallback_from=SNITCH_TUNED,
                          fallback_reason="output_columns_below_ssr_unroll")
        detail = "scalar_tail_for_remaining_output_columns" if o % 8 else None
        return _known(SNITCH_TUNED, fallback_used=False,
                      implementation_detail=detail)

    if m == 0 or n == 0 or o == 0:
        return _known(SPATZ_GENERIC, fallback_used=True,
                      fallback_from=SPATZ_TUNED,
                      fallback_reason="empty_dimension")
    if op == "Gemm":
        trans_a = _integer(arguments.get("transA"))
        trans_b = _integer(arguments.get("transB"))
        if trans_a is None or trans_b is None:
            return _unknown("generated GEMM transpose arguments are unavailable")
        if trans_a or trans_b:
            return _known(SPATZ_GENERIC, fallback_used=True,
                          fallback_from=SPATZ_TUNED,
                          fallback_reason="transposed_operand")
    return _known(SPATZ_TUNED, fallback_used=False)


def annotate_completed_nodes(mapping: Mapping[str, object], result: dict) -> None:
    """Attach implementation evidence to runtime-completed node records in place."""
    planned = mapping.get("nodes")
    if not isinstance(planned, list):
        planned = []
    by_index = {
        entry.get("index"): entry for entry in planned
        if isinstance(entry, Mapping) and isinstance(entry.get("index"), int)
    }
    annotated = []
    for runtime_node in result.get("nodes", []):
        node = dict(runtime_node)
        planned_node = by_index.get(node.get("node"))
        if planned_node is None:
            node["implementation"] = _unknown("generated node metadata is unavailable")
        elif (planned_node.get("op") != node.get("op")
              or planned_node.get("engine") != node.get("engine")):
            node["implementation"] = _unknown("generated metadata disagrees with runtime beacon")
        else:
            evidence = dict(planned_node)
            evidence.update(node)
            node["implementation"] = resolve_actual_implementation(evidence)
        annotated.append(node)
    result["nodes"] = annotated
