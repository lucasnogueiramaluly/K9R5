#!/usr/bin/env python3
"""Check every DRAM preset against the C++ engine and print what it means.

For each kind in hetero/dram_presets.py: build the parameter dict, let the
engine (via dram_replay --nominal) time an unloaded line read, and require it to
equal the Python mirror nominal_read_ps(), which is what the board generator
writes into HES_DRAM_LATENCY. Then print the resulting latency in core cycles
and the peak bandwidth, so a preset change is visible at a glance.

    python tools/dram/check_presets.py BUILD_DIR/dram_replay [--freq HZ]
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'targets'))

from hetero import dram_presets  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('replay', help='path to the built dram_replay')
    ap.add_argument('--freq', type=float, default=1e9, help='core clock, Hz')
    args = ap.parse_args()

    period_ps = 1e12 / args.freq
    bad = 0
    print(f"{'kind':10} {'nominal ns':>11} {'cycles':>7} {'peak GB/s':>10}  check")
    for kind in dram_presets.KINDS:
        if kind == 'fixed':
            continue
        p = dram_presets.params(kind)
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump(p, f)
        out = subprocess.run([args.replay, f.name, '--nominal'], check=True,
                             capture_output=True, text=True).stdout
        Path(f.name).unlink()
        engine = int(out.strip())
        mirror = dram_presets.nominal_read_ps(p)
        ok = engine == mirror
        bad += not ok
        cycles = -(-mirror // int(period_ps))
        print(f"{kind:10} {mirror / 1000:11.3f} {cycles:7d} "
              f"{dram_presets.peak_bytes_per_ns(p):10.2f}  "
              f"{'ok' if ok else f'MISMATCH (engine {engine} ps, python {mirror} ps)'}")
    if bad:
        print(f"{bad} preset(s) disagree between the engine and dram_presets.py")
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
