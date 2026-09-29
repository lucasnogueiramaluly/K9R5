"""Resolve source-grounded kernel implementation evidence for completed nodes."""

from __future__ import annotations

from typing import Mapping

from .matmul_gemm_implementation import (
    CVA6_GENERIC, SNITCH_GENERIC, SNITCH_TUNED, SPATZ_GENERIC, SPATZ_TUNED,
    resolve_matmul_gemm_implementation,
)

EVIDENCE_TYPE = "deterministic_compiled_dispatch_and_runtime_evidence"
UNAVAILABLE_EVIDENCE_TYPE = "unavailable"

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
    if engine == "spatz" and op == "Gemm" and (
            "transA" not in arguments or "transB" not in arguments):
        return _unknown("generated GEMM transpose arguments are unavailable")
    resolved = resolve_matmul_gemm_implementation(
        engine, op, arguments.get("M"), arguments.get("N"), arguments.get("O"),
        transA=arguments.get("transA", 0), transB=arguments.get("transB", 0),
    )
    if resolved["implementation_id"] is None:
        return _unknown(resolved["unknown_reason"])
    return _known(
        resolved["implementation_id"],
        fallback_used=resolved["fallback_used"],
        fallback_from=resolved["fallback_from"],
        fallback_reason=resolved["fallback_reason"],
        implementation_detail=resolved["implementation_detail"],
    )


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
