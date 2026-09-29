# SPDX-License-Identifier: Apache-2.0
"""Read deterministic matrix-kernel arguments from Deeploy's bound parser state."""

from __future__ import annotations

from collections.abc import Mapping
from numbers import Integral


def _integer_constant(value):
    """Return an emitted integer constant, without coercing booleans/floats."""
    if isinstance(value, bool):
        return None
    if isinstance(value, Integral):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            return None
    return None


def emitted_kernel_arguments(layer, op):
    """Return constant MatMul/Gemm arguments from the selected Deeploy mapper.

    ``layer`` is Deeploy's ONNXLayer. The representation that survives parsing
    and is handed to the selected binding lives at
    ``layer.mapper.parser.operatorRepresentation``; the ONNXLayer itself does
    not own an ``operatorRepresentation`` attribute.

    Missing, dynamic, or non-integer evidence is intentionally omitted. The
    actual-implementation resolver will therefore keep the implementation
    unknown rather than infer it from placement alone.
    """
    if op not in {"MatMul", "Gemm"}:
        return None

    mapper = getattr(layer, "mapper", None)
    parser = getattr(mapper, "parser", None)
    representation = getattr(parser, "operatorRepresentation", None)
    if not isinstance(representation, Mapping):
        return {}

    keys = ("M", "N", "O")
    if op == "Gemm":
        keys += ("transA", "transB")

    arguments = {}
    for key in keys:
        value = _integer_constant(representation.get(key))
        if value is not None:
            arguments[key] = value
    return arguments
