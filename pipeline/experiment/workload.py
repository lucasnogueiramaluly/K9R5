"""Shared static ONNX workload inspection for experiment tooling and gui_query."""

from __future__ import annotations

from pathlib import Path

from .fingerprint import file_digest
from .schema import WorkloadSpec


def _product(shape):
    if shape is None:
        return None
    out = 1
    for dim in shape:
        if not isinstance(dim, int) or dim <= 0:
            return None
        out *= dim
    return out


def resolve_workload_path(path: Path | str, roots=()) -> Path:
    """Resolve a workload spelling using explicit search roots, without mutation."""
    p = Path(path)
    if p.is_absolute():
        return p
    candidates = [Path.cwd() / p]
    candidates.extend(Path(root) / p for root in roots)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return p


def inspect_workload(model_path: Path | str, application: str | None = None) -> WorkloadSpec:
    import numpy as np
    import onnx
    from onnx import numpy_helper

    model_path = Path(model_path)
    if model_path.is_dir():
        model_path = model_path / "network.onnx"
    if not model_path.is_file():
        raise FileNotFoundError(f"workload model not found: {model_path}")

    model = onnx.load(str(model_path))
    original_graph = model.graph
    try:
        graph = onnx.shape_inference.infer_shapes(model).graph
    except Exception:
        graph = original_graph

    initializer_names = {i.name for i in original_graph.initializer}

    def vi_tensor(vi):
        t = vi.type.tensor_type
        dims = [d.dim_value if d.HasField("dim_value") else (d.dim_param or "?")
                for d in t.shape.dim]
        return {
            "name": vi.name,
            "dtype": onnx.TensorProto.DataType.Name(t.elem_type).lower(),
            "shape": dims,
        }

    inputs = tuple(vi_tensor(i) for i in original_graph.input if i.name not in initializer_names)
    outputs = tuple(vi_tensor(o) for o in original_graph.output)

    op_counts = {}
    for node in original_graph.node:
        op_counts[node.op_type] = op_counts.get(node.op_type, 0) + 1

    tensor_meta = {}

    def register_vi(vi):
        t = vi.type.tensor_type
        shape = []
        for d in t.shape.dim:
            shape.append(int(d.dim_value) if d.HasField("dim_value") and d.dim_value > 0 else None)
        tensor_meta[vi.name] = (tuple(shape), int(t.elem_type))

    for seq in (graph.input, graph.value_info, graph.output):
        for vi in seq:
            register_vi(vi)
    for init in original_graph.initializer:
        tensor_meta[init.name] = (tuple(int(d) for d in init.dims), int(init.data_type))

    def tensor_bytes(name):
        meta = tensor_meta.get(name)
        if meta is None:
            return None
        shape, elem_type = meta
        elems = _product(shape)
        if elems is None:
            return None
        try:
            dtype = np.dtype(onnx.helper.tensor_dtype_to_np_dtype(elem_type))
        except Exception:
            return None
        return int(elems * dtype.itemsize)

    known_tensor_bytes = {}
    unknown_tensors = []
    for name in sorted(tensor_meta):
        size = tensor_bytes(name)
        if size is None:
            unknown_tensors.append(name)
        else:
            known_tensor_bytes[name] = size

    working_sets = {}
    unknown_working_set_nodes = []
    for index, node in enumerate(original_graph.node):
        names = {n for n in (*node.input, *node.output) if n}
        sizes = [tensor_bytes(n) for n in names]
        if any(size is None for size in sizes):
            unknown_working_set_nodes.append(index)
        else:
            working_sets[index] = sum(sizes)
    max_working_set = max(working_sets.values()) if working_sets else None

    def shape_of(name):
        meta = tensor_meta.get(name)
        if meta is None:
            return None
        shape, _ = meta
        return shape if _product(shape) is not None else None

    covered_ops = {"MatMul", "Gemm", "Conv"}
    mac_total = 0
    mac_known_nodes = []
    mac_unknown_nodes = []

    for index, node in enumerate(original_graph.node):
        if node.op_type not in covered_ops:
            continue
        estimate = None
        out_shape = shape_of(node.output[0]) if node.output else None
        out_elems = _product(out_shape)

        if node.op_type == "MatMul" and len(node.input) >= 2 and out_elems is not None:
            a = shape_of(node.input[0])
            if a is not None and len(a) >= 1:
                estimate = out_elems * a[-1]
        elif node.op_type == "Gemm" and len(node.input) >= 2 and out_elems is not None:
            a = shape_of(node.input[0])
            attrs = {attr.name: onnx.helper.get_attribute_value(attr) for attr in node.attribute}
            trans_a = int(attrs.get("transA", 0))
            if a is not None and len(a) >= 2:
                estimate = out_elems * (a[-2] if trans_a else a[-1])
        elif node.op_type == "Conv" and len(node.input) >= 2 and out_elems is not None:
            w = shape_of(node.input[1])
            if w is not None and len(w) >= 2:
                taps = _product(w[1:])
                if taps is not None:
                    estimate = out_elems * taps

        if estimate is None:
            mac_unknown_nodes.append(index)
        else:
            mac_total += int(estimate)
            mac_known_nodes.append(index)

    init_elems = 0
    init_zeros = 0
    for init in original_graph.initializer:
        arr = numpy_helper.to_array(init)
        init_elems += int(arr.size)
        init_zeros += int(np.count_nonzero(arr == 0))

    static_known_bytes = sum(known_tensor_bytes.values())
    static_complete = not unknown_tensors
    mac_complete = not mac_unknown_nodes
    theoretical_ai = None
    if static_complete and mac_complete and static_known_bytes > 0 and mac_known_nodes:
        theoretical_ai = mac_total / static_known_bytes

    descriptors = {
        "estimated_macs": {
            "value": mac_total,
            "covered_ops": sorted(covered_ops),
            "known_nodes": mac_known_nodes,
            "unknown_nodes": mac_unknown_nodes,
            "complete_for_covered_ops": mac_complete,
            "method": "static-shape formulas; unsupported ops are not assigned zero",
        },
        "static_tensor_bytes": {
            "known_bytes": static_known_bytes,
            "known_tensors": len(known_tensor_bytes),
            "unknown_tensors": unknown_tensors,
            "complete": static_complete,
            "method": "unique graph tensors counted once",
        },
        "working_set": {
            "max_static_node_bytes": max_working_set,
            "known_nodes": sorted(working_sets),
            "unknown_nodes": unknown_working_set_nodes,
            "method": "unique node inputs+outputs; not measured memory traffic",
        },
        "theoretical_arithmetic_intensity": {
            "mac_per_byte": theoretical_ai,
            "method": "estimated covered-op MACs / unique static graph tensor bytes",
            "is_measured": False,
        },
        "initializer_sparsity": {
            "zero_fraction": (init_zeros / init_elems) if init_elems else None,
            "zero_elements": init_zeros,
            "elements": init_elems,
            "scope": "ONNX initializers only; no claim of hardware sparsity support",
        },
    }

    return WorkloadSpec(
        path=str(model_path),
        content_digest=file_digest(model_path),
        application=application,
        opset=tuple({"domain": o.domain or "ai.onnx", "version": o.version}
                    for o in model.opset_import),
        inputs=inputs,
        outputs=outputs,
        node_count=len(original_graph.node),
        op_counts=tuple(sorted(op_counts.items())),
        initializer_count=len(initializer_names),
        descriptors=descriptors,
    )


def workload_to_legacy_inspect(spec: WorkloadSpec) -> dict:
    out = {
        "path": spec.path,
        "opset": [dict(x) for x in spec.opset],
        "inputs": [dict(x) for x in spec.inputs],
        "outputs": [dict(x) for x in spec.outputs],
        "nodes": spec.node_count,
        "op_types": dict(sorted(spec.op_counts, key=lambda kv: -kv[1])),
        "initializers": spec.initializer_count,
    }
    if spec.application is not None:
        out["app"] = spec.application
    return out
