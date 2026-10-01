/*
 * Unit tests of the DRAM timing engine (targets/hetero/dram_core.hpp).
 *
 * Every expected value below is worked out by hand from the JEDEC constraint
 * it exercises, on a parameter set with round numbers so the arithmetic can be
 * checked in a comment. `make dram-test` builds and runs this, then checks the
 * real presets with check_presets.py.
 */

#include "../../targets/hetero/dram_core.hpp"

#include <cstdio>
#include <cstdlib>
#include <string>

using hetero_dram::Engine;
using hetero_dram::Params;

static int failures = 0;

static void expect(const char *what, int64_t got, int64_t want)
{
    if (got != want)
    {
        printf("FAIL  %-48s got %lld, want %lld\n", what, (long long)got, (long long)want);
        failures++;
    }
    else
    {
        printf("ok    %-48s %lld\n", what, (long long)got);
    }
}

// tCK 1 ns, 2000 MT/s x16 BL16: a 32-byte burst takes 8 ns. One burst per
// access (granule 32), no controller latency, no refresh unless a test sets it.
// Address = row << 14 | bank << 11 | column << 5 | byte.
static Params base()
{
    Params p;
    p.kind = "dram";
    p.ctrl_ps = 0;
    p.granule = 32;
    p.banks = 8;
    p.rows = 1 << 16;
    p.page_bytes = 2048;
    p.width_bits = 16;
    p.burst_length = 16;
    p.mtps = 2000;
    p.mapping = "RoBaCo";
    p.tCK = 1000;
    p.tRCD = 10000; p.tRP = 10000; p.tRPab = 10000; p.tRAS = 30000; p.tRC = 40000;
    p.tRL = 15000; p.tWL = 8000;
    p.tRRD_S = 5000; p.tRRD_L = 5000; p.tFAW = 40000;
    p.tCCD_S = 8000; p.tCCD_L = 8000;
    p.tWTR_S = 6000; p.tWTR_L = 6000;
    p.tRTW = 20000; p.tWR = 12000; p.tRTP = 5000;
    p.tREFI = 0; p.tRFC = 0;
    return p;
}

static uint64_t at(int64_t row, int bank, int col)
{
    return ((uint64_t)row << 14) | ((uint64_t)bank << 11) | ((uint64_t)col << 5);
}

int main()
{
    {
        Engine e(base());
        // Closed bank: ACT 0, RD at tRCD 10, data at +RL 25, done +8 = 33 ns.
        expect("closed-row read", e.access(0, at(0, 0, 0), 32, false), 33000);
        // Same row later: RD at once, 15 + 8 = 23 ns after arrival.
        expect("row-hit read", e.access(100000, at(0, 0, 1), 32, false) - 100000, 23000);
        // Other row: PRE now, ACT +10, RD +10, data +15, +8 = 43 ns.
        expect("row-conflict read", e.access(200000, at(1, 0, 0), 32, false) - 200000, 43000);
        expect("  row hits", e.stats().row_hits, 1);
        expect("  row misses", e.stats().row_misses, 1);
        expect("  row conflicts", e.stats().row_conflicts, 1);
    }
    {
        Engine e(base());
        e.access(0, at(0, 0, 0), 32, false);
        // Bank 1: ACT at tRRD 5, RD at max(15, tCCD after 10 = 18); data at
        // max(18 + 15, bus free 33) = 33, done 41.
        expect("second bank, tRRD + tCCD + bus", e.access(0, at(0, 1, 0), 32, false), 41000);
    }
    {
        Engine e(base());
        int64_t end = 0;
        for (int b = 0; b < 5; b++) end = e.access(0, at(0, b, 0), 32, false);
        // ACTs at 0, 5, 10, 15; the fifth waits for tFAW after the first (40).
        // RD 50, data 65 (bus free at 57), done 73. Without tFAW it would be 65.
        expect("five ACTs, tFAW", end, 73000);
    }
    {
        Engine e(base());
        // WR: ACT 0, WR 10, data 18..26. RD same row: tCCD gives 18, tWTR after
        // the write data gives 26 + 6 = 32; data 47, done 55.
        expect("write", e.access(0, at(0, 0, 0), 32, true), 26000);
        expect("read after write, tWTR", e.access(0, at(0, 0, 1), 32, false), 55000);
    }
    {
        Engine e(base());
        // RD at 10 (done 33). WR same row: tRTW from the RD gives 30; data
        // max(38, 33) = 38, done 46.
        e.access(0, at(0, 0, 0), 32, false);
        expect("write after read, tRTW", e.access(0, at(0, 0, 1), 32, true), 46000);
    }
    {
        Params p = base();
        p.tREFI = 100000;
        p.tRFC = 50000;
        Engine e(p);
        // Refresh at 100 needs no precharge (all closed) and ends at 150; a
        // read arriving at 120 activates at 150, done 183.
        expect("read blocked by refresh", e.access(120000, at(0, 0, 0), 32, false), 183000);
    }
    {
        Params p = base();
        p.tREFI = 100000;
        p.tRFC = 50000;
        Engine e(p);
        // Arriving at 95, the read would ACT at 95 and RD at 105 -- across the
        // refresh due at 100. The refresh goes first (100..150): ACT 150, RD
        // 160, done 183.
        expect("refresh due mid-burst goes first", e.access(95000, at(0, 0, 0), 32, false), 183000);
    }
    {
        Params p = base();
        p.tREFI = 100000;
        p.tRFC = 50000;
        Engine e(p);
        e.access(0, at(0, 0, 0), 32, false);
        // The refresh at 100 first precharges the open row (tRPab: starts
        // 110, ends 160) and closes it, so the next access is a miss: ACT
        // 160, RD 170, done 193.
        expect("refresh closes open rows", e.access(120000, at(0, 0, 1), 32, false), 193000);
        expect("  refreshes", e.stats().refreshes, 1);
        expect("  row misses", e.stats().row_misses, 2);
    }
    {
        Params p = base();
        p.tREFI = 100000;
        p.tRFC = 50000;
        Engine e(p);
        // A long idle stretch: refreshes at 100, 200, ..., 10000 (100 of them)
        // are all accounted for, and the last one (ending 10050) delays the read.
        expect("idle refreshes, last blocks", e.access(10020000, at(0, 0, 0), 32, false) - 10020000, 63000);
        expect("  refresh count over idle", e.stats().refreshes, 100);
    }
    {
        Params p = base();
        p.ctrl_ps = 20000;
        p.granule = 64;
        Engine e(p);
        // An 8-byte read inside a 64-byte line moves both 32-byte bursts:
        // 10 in, ACT 10, RD 20 and 28, data 35..43 and 43..51, 10 out = 61.
        expect("granule widening + ctrl latency", e.access(0, 0x28, 8, false), 61000);
        expect("  bursts", e.stats().bursts, 2);
        expect("nominal == unloaded access", e.nominal_read_ps(), 61000);
    }
    {
        Params p = base();
        p.bankgroups = 4;
        p.banks = 4;
        p.mapping = "RoBaCoBg";
        Engine e(p);
        // Byte bits 0-4, bank group 5-6, column 7-12, bank 13-14, row above.
        Engine::Coord c = e.decode((3ULL << 15) | (2ULL << 13) | (5ULL << 7) | (1ULL << 5));
        expect("decode bank group", c.bg, 1);
        expect("decode column", c.col, 5);
        expect("decode bank", c.ba, 2);
        expect("decode row", c.row, 3);
    }
    {
        Params p = base();
        p.wq_depth = 4; p.wq_high = 2; p.wq_low = 1;
        Engine e(p);
        // Posted: the write is accepted at once. It goes to the DRAM while the
        // DRAM is idle (ACT 0, WR 10, data 18..26), so a read long after is a
        // plain row hit: 23 ns.
        expect("wq: write posted", e.access(0, at(0, 0, 0), 32, true), 0);
        expect("wq: idle drain, later read hits", e.access(100000, at(0, 0, 1), 32, false) - 100000, 23000);
    }
    {
        Params p = base();
        p.wq_depth = 4; p.wq_high = 2; p.wq_low = 1;
        Engine e(p);
        // RD at 10 (done 33). A write queued at 10 could not issue before
        // 30 (tRTW), so when the next read arrives at 20 the write is still
        // waiting and the read goes first: RD 20, data 35..43. Draining the
        // write first would have pushed the read to 75.
        e.access(0, at(0, 0, 0), 32, false);
        e.access(10000, at(0, 0, 1), 32, true);
        expect("wq: read overtakes a write still waiting", e.access(20000, at(0, 0, 2), 32, false), 43000);
    }
    {
        Params p = base();
        p.wq_depth = 4; p.wq_high = 2; p.wq_low = 1;
        Engine e(p);
        e.access(0, at(0, 0, 0), 32, true);
        // Same burst, same instant: answered from the queue in one tCK; a
        // second write to it merges.
        expect("wq: read forwarded from queue", e.access(0, at(0, 0, 0), 32, false), 1000);
        e.access(0, at(0, 0, 0), 32, true);
        expect("  merged writes", e.stats().merged, 1);
        expect("  forwarded reads", e.stats().forwarded, 1);
    }
    {
        Params p = base();
        p.wq_depth = 4; p.wq_high = 2; p.wq_low = 1;
        Engine e(p);
        // Three writes at once cross the high watermark: all three drain in a
        // batch (data 18..26, 26..34, 34..42). A read then waits for tWTR
        // after the last one: RD at 48, data 63..71.
        for (int c = 0; c < 3; c++) e.access(0, at(0, 0, c), 32, true);
        expect("wq: batch drain above high watermark", e.stats().bursts, 3);
        expect("wq: read after the batch, tWTR", e.access(0, at(0, 0, 5), 32, false), 71000);
    }
    {
        Params p = base();
        p.wq_depth = 4; p.wq_high = 3; p.wq_low = 1;
        Engine e(p);
        // Four writes fill the queue and drain (data ends 26, 34, 42, 50); a
        // fifth finds every slot still occupied and is accepted only when the
        // first one's data has left, at 26.
        for (int c = 0; c < 4; c++) e.access(0, at(0, 0, c), 32, true);
        expect("wq: full queue holds the write back", e.access(0, at(0, 0, 4), 32, true), 26000);
    }
    {
        Params p;
        p.kind = "hyperram";
        p.ctrl_ps = 0;
        p.granule = 64;
        Engine e(p);
        // 3 CA + 2 x 7 latency + 64 B / 2 B per clock = 49 clocks at 5 ns.
        expect("hyperram line read", e.access(0, 0, 64, false), 245000);
        // The next transaction waits for the bus plus tRWR (35 ns).
        expect("hyperram back to back", e.access(0, 64, 64, false), 525000);
    }
    {
        Params p;
        p.kind = "hyperram";
        p.ctrl_ps = 0;
        p.granule = 64;
        Engine e(p);
        // tCSM 4 us = 800 clocks: 17 overhead leaves 783 data clocks, 1566 B.
        // 4096 B -> 1566 + 1566 + 964: 800 + 800 + 499 clocks, two tRWR gaps.
        expect("hyperram tCSM split", e.access(0, 0, 4096, false), 10565000);
        expect("  transactions", e.stats().bursts, 3);
    }

    if (failures)
    {
        printf("%d failure(s)\n", failures);
        return 1;
    }
    printf("all DRAM engine tests passed\n");
    return 0;
}
