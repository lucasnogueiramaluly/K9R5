"""Read current K9R5 operational identity tables without importing heavy backends."""

from __future__ import annotations
import ast
from pathlib import Path

from .engine_catalog import build_catalog as build_engine_catalog
from .host_profile_catalog import build_catalog as build_host_profile_catalog
from .kernel_implementation_catalog import build_catalog as build_kernel_implementation_catalog


def _simple_assignments(path: Path, wanted: set[str]) -> dict:
    tree = ast.parse(path.read_text(), filename=str(path))
    env = {}

    def value(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name) and node.id in env:
            return env[node.id]
        if isinstance(node, ast.Dict):
            return {value(k): value(v) for k, v in zip(node.keys, node.values)}
        raise ValueError(f"unsupported expression in {path}: {ast.dump(node)}")

    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
            continue
        target = stmt.targets[0]
        if isinstance(target, ast.Name) and target.id in wanted:
            env[target.id] = value(stmt.value)

    missing = wanted - set(env)
    if missing:
        raise RuntimeError(f"{path} is missing expected assignments: {sorted(missing)}")
    return env


def current_engine_catalog(root: Path | str) -> list[dict]:
    root = Path(root)
    names = _simple_assignments(
        root / "targets" / "hetero" / "system.py",
        {"ENGINE_HOST", "ENGINE_SNITCH", "ENGINE_SPATZ", "ENGINE_NAMES"},
    )["ENGINE_NAMES"]
    macros = _simple_assignments(
        root / "pipeline" / "hetero_platform" / "progress.py",
        {"ENGINE_MACRO"},
    )["ENGINE_MACRO"]
    return build_engine_catalog(names, macros)


def _host_targets(path: Path) -> dict[str, str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
            continue
        target = stmt.targets[0]
        if not isinstance(target, ast.Name) or target.id != "HOSTS":
            continue
        if not isinstance(stmt.value, ast.Dict):
            raise RuntimeError("pipeline/build_mesh.py::HOSTS is no longer a dict literal")
        out = {}
        for key_node, value_node in zip(stmt.value.keys, stmt.value.values):
            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                raise RuntimeError("HOSTS profile names must remain string literals")
            if not isinstance(value_node, ast.Tuple) or len(value_node.elts) != 2:
                raise RuntimeError("HOSTS values must remain (image, target) tuples")
            target_node = value_node.elts[1]
            if not isinstance(target_node, ast.Constant) or not isinstance(target_node.value, str):
                raise RuntimeError("HOSTS target names must remain string literals")
            out[key_node.value] = target_node.value
        return out
    raise RuntimeError("pipeline/build_mesh.py does not define HOSTS")


def current_host_profile_catalog(root: Path | str) -> dict[str, dict]:
    root = Path(root)
    rows = build_host_profile_catalog(_host_targets(root / "pipeline" / "build_mesh.py"))
    return {row["name"]: row for row in rows}


def current_kernel_implementation_catalog(root: Path | str) -> list[dict]:
    return build_kernel_implementation_catalog(root)
