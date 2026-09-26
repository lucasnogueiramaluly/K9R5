#!/usr/bin/env python3
"""Read a sweep's JSONL and say what it found.

    python pipeline/sweep/report.py results/sweep/s1/sweep.jsonl

Three sections, in the order they should be trusted:

  1. Sensitivity -- which knobs moved cycles at all, against the baseline.
     This is the screening result, and it rests on nothing but measured cycles.
  2. Pareto front over (cycles, area, energy).
  3. Robustness -- how much of that front survives the area coefficients being
     wrong, which they are.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

# How far an area coefficient is assumed to be able to move. The coefficients
# in area.py are placeholders, so this is not a confidence interval -- it is a
# test of whether a conclusion depends on them at all.
PERTURB = 0.30


def load(path):
    return [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]


def cycles_of(row):
    for k in ("cycles_per_image", "cycles_per_clip", "cycles"):
        if row.get(k):
            return row[k]
    return None


def sensitivity(rows, model):
    """Per-knob effect on cycles, against the baseline of the same model.

    Returns the baseline cycles, the per-knob effects, and the baseline design
    itself -- the last so the table can show what each knob was moved *from*.
    A row reading "TCDM_SIZE 65536 +222%" does not say whether that is half the
    baseline or twice it.
    """
    mine = [r for r in rows if r["model"] == model and r["status"] == "ok"]
    base = next((r for r in mine if r["design_slug"] == "baseline"), None)
    if base is None:
        return None, [], {}
    b = cycles_of(base)

    effects = defaultdict(list)
    for r in mine:
        if r["design_slug"] == "baseline":
            continue
        diff = {k: v for k, v in r["design"].items()
                if v != base["design"].get(k)}
        if len(diff) != 1:
            continue                      # factorial point, not an OFAT one
        knob, value = next(iter(diff.items()))
        c = cycles_of(r)
        effects[knob].append((value, c, 100.0 * (c - b) / b))
    return (b, sorted(effects.items(), key=lambda kv: -max(abs(p[2]) for p in kv[1])),
            base["design"])


def pareto(points):
    """Non-dominated points. Each is (key, [objectives]), all minimised."""
    out = []
    for key, obj in points:
        dominated = any(
            all(o2 <= o1 for o1, o2 in zip(obj, other))
            and any(o2 < o1 for o1, o2 in zip(obj, other))
            for k2, other in points if k2 != key)
        if not dominated:
            out.append((key, obj))
    return out


def analyse(rows):
    """Everything the report says, as data.

    The text report below prints from this and `--json` dumps it, so a program
    reading a sweep (the GUI) and a person reading it see the same numbers.
    """
    ok = [r for r in rows if r["status"] == "ok"]
    other = [r for r in rows if r["status"] != "ok"]
    out = {
        "cells": len(rows), "ok": len(ok),
        "not_ok": [{"status": r["status"], "design_slug": r["design_slug"],
                    "model": r["model"], "reasons": r.get("reasons", [])}
                   for r in other],
        "sensitivity": [],
        "pareto": None,
        "robustness": None,
    }

    for model in sorted({r["model"] for r in ok}):
        base, eff, base_design = sensitivity(rows, model)
        if base is None:
            continue
        knobs = [{"knob": knob, "base_value": base_design.get(knob, "?"),
                  "points": [{"value": v, "cycles": c, "pct": pct}
                             for v, c, pct in sorted(pts)]}
                 for knob, pts in eff]
        flat = [k for k, pts in eff if all(abs(p[2]) < 0.05 for p in pts)]
        out["sensitivity"].append({"model": model, "base_cycles": base,
                                   "knobs": knobs, "flat": flat})

    # --- Pareto -------------------------------------------------------------
    have_area = [r for r in ok if r.get("area_au")]
    have_energy = [r for r in have_area if r.get("cache_dynamic_pj")]
    if not have_area:
        return out

    sourced = all(r.get("area_coefficients_sourced") for r in have_area)
    objectives = ("cycles", "area")
    pts = []
    for r in have_area:
        obj = [cycles_of(r), r["area_au"]]
        if have_energy and r.get("cache_dynamic_pj"):
            obj.append(r["cache_dynamic_pj"])
        pts.append((f"{r['design_slug']}|{r['model']}", obj))
    if have_energy and len(have_energy) == len(have_area):
        objectives = ("cycles", "area", "energy")

    front = pareto(pts)
    out["pareto"] = {
        "objectives": list(objectives),
        "points": len(pts),
        "front": [{"key": key, "objectives": obj}
                  for key, obj in sorted(front, key=lambda kv: kv[1][0])],
    }

    # --- Robustness ---------------------------------------------------------
    rob = {"perturb": PERTURB, "sourced": sourced}
    out["robustness"] = rob
    if sourced:
        return out
    # Scale the SRAM-heavy and logic-heavy halves in opposite directions: that
    # is the perturbation the front is most exposed to, because it changes the
    # balance between "more cache" and "more compute" rather than the total.
    sram_keys = ("icache", "dcache", "l2", "snitch_tcdm", "spatz_tcdm")
    stable = set(k for k, _ in front)
    for direction in (1, -1):
        moved = []
        for r in have_area:
            parts = r.get("area_breakdown") or {}
            adj = sum(v * (1 + direction * PERTURB) if k in sram_keys else v
                      for k, v in parts.items())
            obj = [cycles_of(r), adj]
            if len(objectives) == 3:
                obj.append(r["cache_dynamic_pj"])
            moved.append((f"{r['design_slug']}|{r['model']}", obj))
        stable &= set(k for k, _ in pareto(moved))

    rob["front"] = len(front)
    rob["stable"] = sorted(stable)
    rob["lost"] = sorted(set(k for k, _ in front) - stable)
    return out


def print_report(a):
    print(f"{a['cells']} cells: {a['ok']} ok, {len(a['not_ok'])} not\n")
    for r in a["not_ok"]:
        why = "; ".join(r["reasons"])[:120]
        print(f"  {r['status']:10} {r['design_slug'][:36]:36} {r['model']:8} {why}")
    if a["not_ok"]:
        print()

    for s in a["sensitivity"]:
        base = s["base_cycles"]
        print(f"=== {s['model']}: sensitivity (baseline {base:,} cycles) ===\n")
        # Base cycles repeat down the column, but keeping them on the row makes
        # a line self-contained: grepped, pasted or compared across models, it
        # still says what it was measured against.
        print(f"  {'knob':20} {'base':>10} {'value':>10} "
              f"{'base cycles':>13} {'cycles':>12} {'vs base':>9}")
        for k in s["knobs"]:
            for p in k["points"]:
                print(f"  {k['knob']:20} {k['base_value']:>10} {p['value']:>10} "
                      f"{base:>13,} {p['cycles']:>12,} {p['pct']:>+8.1f}%")
        if s["flat"]:
            print(f"\n  No measurable effect: {', '.join(s['flat'])}")
            print("  (A host vector knob does nothing on the scalar host -- those "
                  "need --host ara.)")
        print()

    # --- Pareto -------------------------------------------------------------
    if a["pareto"] is None:
        print("No area figures in these rows; skipping the Pareto pass.")
        return
    p = a["pareto"]
    print(f"=== Pareto front over {', '.join(p['objectives'])} "
          f"({len(p['front'])} of {p['points']} non-dominated) ===\n")
    for f in p["front"]:
        vals = "  ".join(f"{o:,.0f}" for o in f["objectives"])
        print(f"  {f['key'][:46]:46} {vals}")

    # --- Robustness ---------------------------------------------------------
    rob = a["robustness"]
    print(f"\n=== Robustness: area coefficients +/-{int(rob['perturb']*100)}% ===\n")
    if rob["sourced"]:
        print("  All area coefficients are sourced; the front above stands on "
              "measured figures.")
        return
    print(f"  {len(rob['stable'])} of {rob['front']} front members survive both perturbations.")
    if rob["lost"]:
        print("  Depend on the placeholder coefficients: "
              + ", ".join(k[:40] for k in rob["lost"]))
    print("\n  Area coefficients are PLACEHOLDERS (see pipeline/sweep/area.py).")
    print("  Treat the cycles column as the only measured objective here.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jsonl")
    ap.add_argument("--json", action="store_true",
                    help="print the analysis as one JSON object instead of text")
    args = ap.parse_args()
    a = analyse(load(args.jsonl))
    if args.json:
        print(json.dumps(a, indent=2))
    else:
        print_report(a)


if __name__ == "__main__":
    main()
