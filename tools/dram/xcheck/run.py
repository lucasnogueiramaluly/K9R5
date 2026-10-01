#!/usr/bin/env python3
"""Cross-check the hetero-sim DRAM model against reference simulators.

Needs the two references built by build_refs.sh (into /opt, or XCHECK_REFS):
either the hetero-dram-xcheck image (`make dram-xcheck`), or the hetero-sim
dev container after running build_refs.sh in it:

    tools/dram/xcheck/build_refs.sh /opt          # once, ~300 MB
    .venv/bin/python tools/dram/xcheck/run.py

For every device and every access pattern below, the same request stream goes
through the reference and through our engine (tools/dram/dram_replay), and the
read latencies are compared request by request.

  lpddr4, lpddr4x   DRAMSys, with the very memspec JSON our preset was taken
                    from, a FIFO controller (upstream fifo.json: FIFO
                    scheduler, oldest-first command mux) and all-bank refresh
                    that is never postponed.
                    Our engine runs with its write queue off to match: this
                    checks the device timing under strict ordering.
  lpddr5            Ramulator2 with the LPDDR5_6400 / LPDDR5_8Gb_x16 presets our
                    preset was taken from, all-bank refresh, open rows, and its
                    controller's write buffer -- which our preset's write queue
                    mirrors, so this checks the posted-write behaviour too.

Requests are one burst (32 bytes) each, the unit both references schedule,
and our engine runs with no controller latency of its own, so what is compared
is the DRAM timing and nothing else. Two kinds of pattern, two measures:

  latency     the DRAM is not saturated. Our engine gets the reference's own
              arrival time for every request, and the mean read latency is
              compared (plus how many reads agree within 5 ns).
  throughput  requests arrive faster than any DRAM serves them. Latency then
              only measures queue depth -- DRAMSys back-pressures its trace
              player at 8 requests, our replay queues without bound -- so the
              sustained read bandwidth from the original trace times is
              compared instead.

Acceptance: every pattern within TOLERANCE of the reference -- or, for a
latency pattern, within REFRESH_TOLERANCE once the reads that arrive around a
refresh are left out. Both references reorder the queue that piles up behind a
refresh (DRAMSys's FIFO is per bank, with an oldest-ready command mux;
Ramulator2 is FR-FCFS), letting row hits on open banks overtake older requests
still waiting for their ACT. Our engine fixes each latency when the request
arrives, so it cannot let a later request overtake; that one difference is
reported separately rather than averaged into the timing comparison. Exit
status 1 otherwise.
"""

import argparse
import json
import os
import random
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "targets"))

from hetero import dram_presets  # noqa: E402

# Where tools/dram/xcheck/build_refs.sh put the references.
REFS = Path(os.environ.get("XCHECK_REFS", "/opt"))
DRAMSYS = REFS / "DRAMSys"
RAMULATOR = REFS / "ramulator2"
TOLERANCE = 0.10
REFRESH_TOLERANCE = 0.05
# Reads arriving this close to a refresh falling due are "around" it.
REFRESH_WINDOW_PS = (-100_000, 1_000_000)
REQ_BYTES = 32

REFERENCE = {
    "lpddr4": ("dramsys", "JEDEC_8Gb_LPDDR4-3200_16bit.json"),
    "lpddr4x": ("dramsys", "JEDEC_1Gbx16_LPDDR4-4266.json"),
    "lpddr5": ("ramulator", None),
}

# Ramulator2's RoBaRaCoCh mapper, for a one-channel one-rank LPDDR5 part, is
# row | bank | bank group | column (MSB to LSB). Our preset interleaves bank
# groups below the column instead; for the comparison both must agree.
MAPPING_OVERRIDE = {"lpddr5": "RoBaBgCo"}


# --- address composition --------------------------------------------------

class Layout:
    """Field widths and order of our mapping, to build addresses from fields."""

    def __init__(self, p):
        self.burst_bytes = p["width_bits"] // 8 * p["burst_length"]
        sizes = {"Ro": p["rows"], "Ra": p["ranks"], "Bg": p["bankgroups"], "Ba": p["banks"],
                 "Co": p["page_bytes"] // self.burst_bytes, "Ch": p["channels"]}
        m = p["mapping"]
        self.fields = [m[i:i + 2] for i in range(0, len(m), 2)]   # MSB first
        self.bits = {f: (sizes[f] - 1).bit_length() for f in self.fields}
        self.sizes = sizes

    def addr(self, **v):
        a = 0
        for f in self.fields:
            a = (a << self.bits[f]) | (v.get(f, 0) & ((1 << self.bits[f]) - 1))
        return a * self.burst_bytes

    def lsb_first(self):
        """[(field, first_bit, nbits)] above the burst offset, LSB first."""
        pos = self.burst_bytes.bit_length() - 1
        out = []
        for f in reversed(self.fields):
            out.append((f, pos, self.bits[f]))
            pos += self.bits[f]
        return out


# --- access patterns --------------------------------------------------------
#
# Each returns [(time_ns, is_write, addr)]. Gaps are chosen relative to a burst
# (5 ns LPDDR4-3200, 2.5 ns LPDDR5) so that some patterns leave the bus idle
# and others saturate it, and long enough in total (>= 20 us) to cross several
# refreshes.

def patterns(L, nbanks):
    """{name: (trace, measure)}; trace is [(time_ns, is_write, addr)]."""
    rnd = random.Random(1234)
    cols = L.sizes["Co"]

    def seq(n, gap):
        return [(i * gap, False, L.addr(Ro=i // (cols * nbanks), Ba=(i // cols) % nbanks, Co=i % cols))
                for i in range(n)]

    def split(i):
        # Flat bank index -> (bank group, bank) for a part with bank groups.
        bg = L.sizes["Bg"]
        return {"Bg": i % bg, "Ba": (i // bg) % L.sizes["Ba"]} if bg > 1 else {"Ba": i % L.sizes["Ba"]}

    def rotate(n, gap):
        # Each request a different bank, same row: an ACT per bank, then hits.
        return [(i * gap, False, L.addr(Ro=i // (nbanks * cols), Co=(i // nbanks) % cols, **split(i)))
                for i in range(n)]

    def alternate(trace):
        return [(t, i % 2 == 1, a) for i, (t, w, a) in enumerate(trace)]

    # Gaps are against a 2.5-5 ns burst (LPDDR5-6400 .. LPDDR4-3200); every
    # trace is long enough (>= 20 us) to cross several refreshes.
    return {
        # Mostly row hits, the bus half idle.
        "sequential": (seq(4000, 10), "latency"),
        # tRRD / tFAW for the first ACT of every bank, then hits.
        "bank_rotate": (rotate(2000, 12), "latency"),
        # Two rows of one bank, alternately: a row conflict every time.
        "row_conflict": ([(i * 100, False, L.addr(Ro=i % 2, Co=i % cols)) for i in range(400)], "latency"),
        # Random lines over 64 MiB: mostly misses and conflicts.
        "random": ([(i * 60, False, rnd.randrange(0, 64 << 20) & ~(REQ_BYTES - 1)) for i in range(1000)],
                   "latency"),
        # Every other request a write: a turnaround each way.
        "read_write": (alternate(seq(2000, 30)), "latency"),
        # Back to back, bus-bound.
        "stream": (seq(4000, 1), "throughput"),
        "bank_rotate_sat": (rotate(4000, 1), "throughput"),
        "read_write_sat": (alternate(seq(4000, 1)), "throughput"),
    }


# --- references --------------------------------------------------------------

def dramsys_mapping(L, p):
    am = {"BYTE_BIT": list(range((p["width_bits"] // 8 - 1).bit_length()))}
    col = list(range(len(am["BYTE_BIT"]), L.burst_bytes.bit_length() - 1))
    names = {"Co": "COLUMN_BIT", "Ro": "ROW_BIT", "Ba": "BANK_BIT", "Bg": "BANKGROUP_BIT",
             "Ra": "RANK_BIT", "Ch": "CHANNEL_BIT"}
    am["COLUMN_BIT"] = col
    for f, first, n in L.lsb_first():
        if n:
            am.setdefault(names[f], []).extend(range(first, first + n))
    return am


def run_dramsys(kind, memspec_file, L, p, trace, workdir):
    workdir.mkdir(parents=True, exist_ok=True)
    stl = workdir / "trace.stl"
    stl.write_text("".join(f"{t}:\t{'write' if w else 'read'}\t0x{a:x}\n" for t, w, a in trace))
    # Sub-configurations inlined: the objects inside each file, not the files.
    memspec = json.loads((DRAMSYS / "configs" / "memspec" / memspec_file).read_text())["memspec"]
    config = {"simulation": {
        "simulationid": f"xcheck-{kind}",
        "simconfig": {
            # A stop for safety: every pattern is done well inside 1 ms, and an
            # unfinished one would otherwise run on, refreshing, forever.
            "SimulationName": "xcheck", "SimulationTime": 1e-3, "Debug": False,
            "DatabaseRecording": True,
            "PowerAnalysis": False, "EnableWindowing": False, "WindowSize": 1000,
            "SimulationProgressBar": False, "AddressOffset": 0, "StoreMode": "NoStorage"},
        "memspec": memspec,
        "addressmapping": dramsys_mapping(L, p),
        "mcconfig": {
            # Upstream's fifo.json, refresh never postponed. (fifoStrict.json's
            # "Strict" command mux deadlocks at this DRAMSys commit: requests
            # are accepted and no command is ever issued.)
            "PagePolicy": "Open", "Scheduler": "Fifo", "SchedulerBuffer": "Bankwise",
            "RequestBufferSize": 8, "CmdMux": "Oldest", "RespQueue": "Fifo",
            "RefreshPolicy": "AllBank", "RefreshMaxPostponed": 0, "RefreshMaxPulledin": 0,
            "PowerDownPolicy": "NoPowerDown", "Arbiter": "Simple", "MaxActiveTransactions": 128},
        # The name is resolved against the resource directory (workdir).
        "tracesetup": [{"type": "player", "clkMhz": 1000, "dataLength": REQ_BYTES,
                        "name": stl.name}],
    }}
    cfg = workdir / "config.json"
    cfg.write_text(json.dumps(config, indent=1))
    for old in workdir.glob("*.tdb"):
        old.unlink()
    r = subprocess.run([str(DRAMSYS / "build" / "bin" / "DRAMSys"), str(cfg), str(workdir)],
                       cwd=workdir, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"DRAMSys failed:\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    dbs = list(workdir.glob("*.tdb"))
    if len(dbs) != 1:
        raise RuntimeError(f"expected one trace database in {workdir}, found {dbs}")
    tx = read_dramsys_db(dbs[0])
    # Our engine gets every transaction at the time DRAMSys's controller got it.
    entries = [(a, w, addr) for a, d, addr, w, *_ in tx]
    return entries, [(a, d) for a, d, addr, w, *_ in tx if not w]


def read_dramsys_db(path):
    """[(arrive_ps, done_ps, addr, is_write, acts, pres)] per transaction, by arrival.

    arrive is the BEGIN_REQ at the controller; done is the end of the data
    strobe of the transaction's RD/WR command.
    """
    db = sqlite3.connect(path)
    tx = {row[0]: row[1:] for row in db.execute(
        "SELECT ID, Address, Command FROM Transactions")}
    ph = {}
    for tid, name, begin, end, dbeg, dend in db.execute(
            "SELECT Transact, PhaseName, PhaseBegin, PhaseEnd, DataStrobeBegin, DataStrobeEnd FROM Phases"):
        ph.setdefault(tid, []).append((name, begin, end, dbeg, dend))
    out = []
    for tid, (addr, cmd) in sorted(tx.items()):
        phases = ph.get(tid, [])
        req = [b for n, b, e, db_, de in phases if n == "REQ"]
        data = [de for n, b, e, db_, de in phases if n in ("RD", "WR", "RDA", "WRA", "MWR", "MWRA")]
        if not req or not data:
            continue
        acts = sum(1 for n, *_ in phases if n == "ACT")
        pres = sum(1 for n, *_ in phases if n in ("PREPB", "PRE", "PREAB"))
        out.append((req[0], max(data), addr, cmd.upper().startswith("W"), acts, pres))
    return sorted(out)


def run_ramulator(driver, trace, workdir):
    workdir.mkdir(parents=True, exist_ok=True)
    cfg_py = workdir / "config.py"
    cfg_py.write_text("""
import ramulator
frontend = ramulator.frontend.External(clock_ratio=1)
dram = ramulator.dram.LPDDR5(org_preset="LPDDR5_8Gb_x16", timing_preset="LPDDR5_6400", rank=1)
ctrl = ramulator.controller.LPDDR5(
    dram=dram,
    scheduler=ramulator.scheduler.FRFCFS(),
    refresh_manager=ramulator.refresh_manager.AllBank(),
    row_policy=ramulator.row_policy.Open(),
    addr_mapper=ramulator.addr_mapper.RoBaRaCoCh(),
)
mem = ramulator.memory_system.GenericDRAM(
    clock_ratio=1, controllers=[ctrl],
    channel_mapper=ramulator.channel_mapper.CacheLineInterleave())
sim = ramulator.Simulation(frontend, mem)
""")
    cfg_yaml = workdir / "config.yaml"
    subprocess.run([sys.executable, "-m", "ramulator", "export", str(cfg_py), "-o", str(cfg_yaml)],
                   check=True, cwd=workdir,
                   env={"PYTHONPATH": str(RAMULATOR / "python"), "PATH": "/usr/bin:/bin"})
    tr = workdir / "trace.txt"
    tr.write_text("".join(f"{t * 1000} {'W' if w else 'R'} 0x{a:x}\n" for t, w, a in trace))
    r = subprocess.run([str(driver), str(cfg_yaml), str(tr)], capture_output=True, text=True,
                       env={"LD_LIBRARY_PATH": str(RAMULATOR)})
    if r.returncode != 0:
        raise RuntimeError(f"ramulator driver failed:\n{r.stderr[-2000:]}")
    reads = []
    for line in r.stdout.splitlines():
        if not line or not line[0].isdigit():
            continue
        a, d, addr = line.split()
        reads.append((int(a), int(d)))
    # Ramulator2 reports reads only (writes retire without a callback), so our
    # engine replays the original trace -- writes included -- not the report.
    entries = [(t * 1000, w, a) for t, w, a in trace]
    return entries, sorted(reads)


# --- ours --------------------------------------------------------------------

def run_ours(replay, params, entries, workdir):
    """Replay [(arrive_ps, is_write, addr)] through our engine.

    Returns [(arrive_ps, is_write, addr, latency_ps)] in arrival order, and the
    replay's summary line."""
    pj = workdir / "params.json"
    pj.write_text(json.dumps(params))
    stl = workdir / "ours.stl"
    stl.write_text("".join(f"{a}:\t{'write' if w else 'read'}\t0x{addr:x}\n"
                           for a, w, addr in sorted(entries)))
    r = subprocess.run([str(replay), str(pj), str(stl), "--clk-mhz", "1000000",
                        "--size", str(REQ_BYTES), "--per-request"],
                       capture_output=True, text=True, check=True)
    lats, summary = [], r.stdout.splitlines()[-1]
    for line in r.stdout.splitlines()[:-1]:
        t, cmd, addr, lat = line.split()
        lats.append((int(t), cmd == "write", int(addr, 16), int(lat)))
    return lats, summary


def build(out):
    bindir = out / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    replay = bindir / "dram_replay"
    subprocess.run(["g++", "-std=c++17", "-O2", "-o", str(replay),
                    str(ROOT / "tools" / "dram" / "dram_replay.cpp")], check=True)
    driver = bindir / "ramulator_driver"
    subprocess.run(["g++", "-std=c++20", "-O2", "-o", str(driver),
                    str(ROOT / "tools" / "dram" / "xcheck" / "ramulator_driver.cpp"),
                    f"-I{RAMULATOR / 'src'}", f"-I{RAMULATOR / 'ext' / 'yaml-cpp' / 'include'}",
                    f"-I{RAMULATOR / 'ext' / 'fmt' / 'include'}",
                    f"-L{RAMULATOR}", "-lramulator", f"-Wl,-rpath,{RAMULATOR}"], check=True)
    return replay, driver


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "work" / "dram_xcheck"))
    ap.add_argument("--kinds", default=",".join(REFERENCE))
    args = ap.parse_args()
    out = Path(args.out)
    replay, driver = build(out)

    report, bad = [], 0
    print(f"{'kind':8} {'pattern':16} {'measure':10} {'reads':>6} {'ref':>9} {'ours':>9} {'':5} "
          f"{'err':>7} {'no-ref':>8} {'<=5ns':>8}")
    for kind in args.kinds.split(","):
        ref_kind, memspec = REFERENCE[kind]
        overrides = {"ctrl_ps": 0, "granule": REQ_BYTES}
        if kind in MAPPING_OVERRIDE:
            overrides["mapping"] = MAPPING_OVERRIDE[kind]
        if ref_kind == "dramsys":
            overrides["wq_depth"] = 0
        p = dram_presets.params(kind, overrides)
        L = Layout(p)
        nbanks = p["banks"] * p["bankgroups"]
        for name, (trace, measure) in patterns(L, nbanks).items():
            wd = out / kind / name
            if ref_kind == "dramsys":
                entries, ref_reads = run_dramsys(kind, memspec, L, p, trace, wd)
            else:
                entries, ref_reads = run_ramulator(driver, trace, wd)

            if measure == "latency":
                ours, summary = run_ours(replay, p, entries, wd)
                # Pair the reads by arrival order: both sides saw the same sequence.
                our_reads = [o for o in ours if not o[1]]
                if len(our_reads) != len(ref_reads):
                    raise RuntimeError(f"{kind}/{name}: {len(ref_reads)} reference reads, "
                                       f"{len(our_reads)} of ours")
                pairs = [(d - a, o[3], a) for (a, d), o in zip(ref_reads, our_reads)]
                ref_v = sum(a for a, _, _ in pairs) / len(pairs) / 1000
                our_v = sum(b for _, b, _ in pairs) / len(pairs) / 1000
                close = sum(1 for a, b, _ in pairs if abs(a - b) <= 5000) / len(pairs)
                unit, n = "ns", len(pairs)
                # The same, without the reads that arrive around a refresh.
                refi = p["tREFI"]

                def near_refresh(t):
                    k = round(t / refi)
                    return k > 0 and REFRESH_WINDOW_PS[0] <= t - k * refi <= REFRESH_WINDOW_PS[1]
                calm = [(a, b) for a, b, t in pairs if not near_refresh(t)]
                calm_err = (sum(b for _, b in calm) - sum(a for a, _ in calm)) / sum(a for a, _ in calm)
            else:
                # Original trace times on both sides; bandwidth of the reads.
                ours, summary = run_ours(replay, p, [(t * 1000, w, a) for t, w, a in trace], wd)
                t0 = trace[0][0] * 1000
                reads = [o for o in ours if not o[1]]
                ref_v = len(ref_reads) * REQ_BYTES / (max(d for _, d in ref_reads) - t0) * 1000
                our_v = len(reads) * REQ_BYTES / (max(a + l for a, _, _, l in reads) - t0) * 1000
                close, unit, n, calm_err = None, "GB/s", len(reads), None

            err = (our_v - ref_v) / ref_v
            if abs(err) <= TOLERANCE:
                verdict = ""
            elif calm_err is not None and abs(calm_err) <= REFRESH_TOLERANCE:
                verdict = "   refresh-queue order (see above)"
            else:
                verdict = "   <-- outside tolerance"
                bad += 1
            print(f"{kind:8} {name:16} {measure:10} {n:>6} {ref_v:>9.2f} {our_v:>9.2f} {unit:5} "
                  f"{100 * err:>+6.1f}% {'' if calm_err is None else f'{100 * calm_err:+6.1f}%':>8} "
                  f"{'' if close is None else f'{100 * close:6.1f}%':>8}{verdict}")
            report.append({"kind": kind, "pattern": name, "measure": measure, "reference": ref_kind,
                           "reads": n, "ref": ref_v, "ours": our_v, "unit": unit, "rel_err": err,
                           "rel_err_outside_refresh": calm_err, "within_5ns": close,
                           "ours_summary": summary})
    (out / "report.json").write_text(json.dumps(report, indent=2))
    print(f"\nreport: {out / 'report.json'}")
    if bad:
        print(f"{bad} pattern(s) outside ±{100 * TOLERANCE:.0f}%")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
