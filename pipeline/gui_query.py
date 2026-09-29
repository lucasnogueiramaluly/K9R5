#!/usr/bin/env python3
"""Answer the questions a front-end asks about this checkout, as JSON.

    python pipeline/gui_query.py env
    python pipeline/gui_query.py ops
    python pipeline/gui_query.py inspect ops/mnist
    python pipeline/gui_query.py knobs
    python pipeline/gui_query.py validate designs.json

The GUI (gui/) runs the pipeline through its CLIs, natively or inside the
Docker image, and cannot import Python. Rather than re-implement the design
rules, the op discovery or the ONNX parsing in Rust -- and drift from them --
it asks here. Every subcommand is a thin wrapper over the module that owns the
answer, and prints exactly one JSON document on stdout.
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "sweep"))

from common import (APPS, DEEPLOY_TEST, GVSOC, PYTHON, ROOT, TC,  # noqa: E402
                    detect_app)
import design as design_mod  # noqa: E402
from experiment.discovery import (current_engine_catalog, current_host_profile_catalog,
                                  current_kernel_implementation_catalog)  # noqa: E402
from experiment.mapping_strategy_catalog import build_catalog as build_mapping_catalog  # noqa: E402
from experiment.parameter_catalog import build_catalog  # noqa: E402
from experiment.resolve import resolve_experiment  # noqa: E402
from experiment.schema import ExperimentRequest  # noqa: E402
from experiment.workload import (  # noqa: E402
    inspect_workload, resolve_workload_path, workload_to_legacy_inspect,
)


def cmd_env(_args):
    """What this checkout can run: the pieces setup.sh provides."""
    parts = {
        "venv": PYTHON,
        "gvsoc": GVSOC,
        "deeploy": DEEPLOY_TEST / "generateNetwork.py",
        "toolchain": TC,
    }
    return {
        "root": str(ROOT),
        "python": sys.version.split()[0],
        "have": {k: p.exists() for k, p in parts.items()},
        "ready": all(p.exists() for p in parts.values()),
        "build_key": design_mod.build_key({}),
    }


def _op_entry(path: Path, arg: str, source: str):
    app, _ = detect_app(path)
    return {"name": path.name, "arg": arg, "source": source, "app": app,
            "has_inputs": (path / "inputs.npz").is_file(),
            "has_outputs": (path / "outputs.npz").is_file()}


def cmd_ops(_args):
    """Every op directory the drivers accept, workspace ops first.

    `arg` is what to pass to run.py / run_hetero.py / sweep/run.py -- relative
    to the repository root, so it means the same inside and outside Docker.
    """
    ops = []
    base = ROOT / "ops"
    if base.is_dir():
        for d in sorted(base.iterdir()):
            if d.name.startswith(".") or not (d / "network.onnx").is_file():
                continue
            ops.append(_op_entry(d, f"ops/{d.name}", "workspace"))
    tests = DEEPLOY_TEST / "Tests"
    if tests.is_dir():
        for onnx in sorted(tests.rglob("network.onnx")):
            d = onnx.parent
            rel = d.relative_to(DEEPLOY_TEST)
            e = _op_entry(d, str(rel.as_posix()), "deeploy")
            e["name"] = str(d.relative_to(tests).as_posix())
            ops.append(e)
    return {"ops": ops, "apps": sorted(APPS)}


def cmd_inspect(args):
    """Inputs, outputs and node types of an op directory or an .onnx file."""
    p = resolve_workload_path(args.path, roots=(ROOT, DEEPLOY_TEST))
    model_path = p / "network.onnx" if p.is_dir() else p
    app = None
    if p.is_dir():
        app, _ = detect_app(p)
    return workload_to_legacy_inspect(
        inspect_workload(model_path, application=app)
    )


def cmd_knobs(_args):
    """The sweep's design space: every knob, its baseline and the OFAT grid."""
    # Loaded by path: pipeline/run.py and pipeline/sweep/run.py share a module
    # name, and which one `import run` finds depends on sys.path order.
    import importlib.util
    spec = importlib.util.spec_from_file_location("sweep_run", HERE / "sweep" / "run.py")
    sweep_run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sweep_run)
    return {
        "defaults": design_mod.DEFAULTS,
        "build_time": list(design_mod.BUILD_TIME),
        "ofat": sweep_run.OFAT,
        "parameters": build_catalog(
            design_mod.DEFAULTS,
            design_mod.BUILD_TIME,
            sweep_run.OFAT,
        ),
        "build_key": design_mod.build_key({}),
    }


def cmd_experiment_schema(_args):
    """Current experiment-facing metadata, derived from operational sources."""
    knobs = cmd_knobs(_args)
    return {
        "parameters": knobs["parameters"],
        "engines": current_engine_catalog(ROOT),
        "host_profiles": list(current_host_profile_catalog(ROOT).values()),
        "mapping_strategies": build_mapping_catalog(),
        "kernel_implementations": current_kernel_implementation_catalog(ROOT),
        "presets": ["k9r5_current"],
    }


def cmd_resolve_experiment(args):
    """Resolve one JSON ExperimentRequest without building or running anything."""
    data = json.loads(Path(args.request).read_text())
    request = ExperimentRequest.from_dict(data)
    p = resolve_workload_path(request.workload, roots=(ROOT, DEEPLOY_TEST))
    app = None
    if p.is_dir():
        app, _ = detect_app(p)
    return resolve_experiment(
        request,
        design_api=design_mod,
        host_profiles=current_host_profile_catalog(ROOT),
        workload_path=p,
        application=app,
    ).to_dict()


def cmd_validate(args):
    """Per design point: its slug, resolved values, and why it cannot be built.

    `needs_build` is the same test sweep/run.py refuses on: a build-time knob
    (VLEN) whose GVSoC build is not the one installed.
    """
    data = json.loads(Path(args.designs).read_text())
    have = design_mod.build_key({})
    out = []
    for d in data:
        try:
            key = design_mod.build_key(d)
            out.append({"design": d, "slug": design_mod.slug(d),
                        "resolved": design_mod.resolve(d),
                        "reasons": design_mod.validate(d),
                        "build_key": key, "needs_build": key != have})
        except ValueError as exc:
            out.append({"design": d, "slug": None, "resolved": None,
                        "reasons": [str(exc)], "build_key": None,
                        "needs_build": False})
    return {"designs": out, "build_key": have}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("env").set_defaults(fn=cmd_env)
    sub.add_parser("ops").set_defaults(fn=cmd_ops)
    p = sub.add_parser("inspect")
    p.add_argument("path", help="op directory or .onnx file")
    p.set_defaults(fn=cmd_inspect)
    sub.add_parser("knobs").set_defaults(fn=cmd_knobs)
    sub.add_parser("experiment-schema").set_defaults(fn=cmd_experiment_schema)
    p = sub.add_parser("resolve-experiment")
    p.add_argument("request", help="JSON ExperimentRequest file")
    p.set_defaults(fn=cmd_resolve_experiment)
    p = sub.add_parser("validate")
    p.add_argument("designs", help="JSON list of partial designs")
    p.set_defaults(fn=cmd_validate)
    args = ap.parse_args()
    try:
        result = args.fn(args)
    except Exception as exc:  # noqa: BLE001
        # Still one JSON document, so the caller never has to parse a traceback.
        print(json.dumps({"error": f"{type(exc).__name__}: {exc}"}))
        sys.exit(1)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
