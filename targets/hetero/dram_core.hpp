/*
 * Timing engine of the hetero-sim main-memory model (see dram.cpp).
 *
 * Plain C++17 with no GVSoC headers, so the same code that times a simulation
 * also runs in the stand-alone unit tests and the DRAMSys / Ramulator2
 * cross-check replay (tools/dram/). All times are in picoseconds.
 *
 * Two device families:
 *
 *   dram      LPDDR4 / LPDDR4X / LPDDR5. Channels x ranks x bank groups x
 *             banks, an open-page policy and an in-order controller. Each
 *             request is split into bursts; every burst activates, precharges
 *             and transfers under the JEDEC constraints listed in Params, on a
 *             data bus shared by its channel. All-bank refresh every tREFI.
 *
 *   hyperram  HyperBus RAM (HyperRAM 2.0). One shared bus, no banks: a
 *             command/address phase, a fixed initial latency, then data at
 *             two transfers per clock. Long transfers are split at tCSM.
 *
 * Writes either take their turn like reads (wq_depth 0, a strict in-order
 * controller) or are posted to a write queue (wq_depth > 0), the way LPDDR
 * controllers do it: a write is acknowledged once it is in the queue; queued
 * writes go to the DRAM when nothing else is waiting, or in a batch once more
 * than wq_high are queued, down to fewer than wq_low; a read that hits a queued
 * write is answered from the queue; a write to an already-queued burst merges
 * into it. Without the queue, the refill + dirty-eviction pairs an L2 sends
 * would pay a read-to-write and a write-to-read turnaround each.
 *
 * What is deliberately not modelled: reordering among reads (FR-FCFS), per-bank
 * refresh, power-down states, command-bus contention and the LPDDR5 two-part
 * ACT. The callers are caches that miss in order, so in-order reads are what
 * they would actually see; the rest are second-order.
 */

#pragma once

#include <algorithm>
#include <cstdint>
#include <deque>
#include <stdexcept>
#include <string>
#include <vector>

namespace hetero_dram
{

struct Params
{
    // "dram" or "hyperram".
    std::string kind = "dram";

    // Controller + PHY latency, half charged on the way in and half on the way
    // out, so it delays a request without throttling the DRAM behind it.
    int64_t ctrl_ps = 20000;

    // Requests are widened to whole aligned granules before they are timed:
    // a cache refill moves a full line even when the master asked for 8 bytes.
    int64_t granule = 64;

    // --- dram geometry ---
    int64_t channels = 1;
    int64_t ranks = 1;
    int64_t bankgroups = 1;
    int64_t banks = 8;            // per bank group
    int64_t rows = 65536;
    int64_t page_bytes = 2048;
    int64_t width_bits = 16;      // DQ width of one channel
    int64_t burst_length = 16;    // beats per burst
    int64_t mtps = 3200;      // data rate, mega-transfers per second
    // Address mapping, most significant field first. Fields: Ro (row), Ra
    // (rank), Bg (bank group), Ba (bank), Co (column, in bursts), Ch
    // (channel). The byte offset inside a burst is always the lowest bits.
    std::string mapping = "RoBaCo";

    // --- dram timings (ps) ---
    int64_t tCK = 625;
    int64_t tRCD = 0, tRP = 0, tRPab = 0, tRAS = 0, tRC = 0;
    int64_t tRL = 0, tWL = 0;
    int64_t tRRD_S = 0, tRRD_L = 0, tFAW = 0;
    int64_t tCCD_S = 0, tCCD_L = 0;
    int64_t tWTR_S = 0, tWTR_L = 0;
    int64_t tRTW = 0;          // read command to write command
    int64_t tRTW_L = 0;        // the same within a bank group (0: same as tRTW)
    int64_t tWR = 0, tRTP = 0;
    int64_t tREFI = 0, tRFC = 0;   // tREFI 0 disables refresh

    // --- dram write queue (bursts); depth 0 disables it ---
    int64_t wq_depth = 0;
    int64_t wq_high = 0;           // batch-drain once more than this are queued
    int64_t wq_low = 0;            // ... until fewer than this remain

    // --- hyperram ---
    int64_t hb_ck_ps = 5000;       // bus clock period
    int64_t hb_ca_clks = 3;            // 48-bit command/address at DDR on 8 lines
    int64_t hb_lat_clks = 7;           // initial latency (tACC in clocks)
    int64_t hb_fixed_2x = 1;       // fixed double latency (the device default)
    int64_t hb_bus_bytes = 1;          // 1 for x8, 2 for x16
    int64_t hb_csm_ps = 4000000;   // max CS# low time
    int64_t hb_rwr_ps = 35000;     // CS# high between transactions (tRWR)
};

// Every numeric field by name, so the GVSoC wrapper, the unit tests and the
// cross-check replay all load a preset the same way (the generator in
// hetero/dram_presets.py emits exactly these keys).
inline const std::vector<std::pair<const char *, int64_t Params::*>> &int_fields()
{
    static const std::vector<std::pair<const char *, int64_t Params::*>> f = {
        {"ctrl_ps", &Params::ctrl_ps}, {"granule", &Params::granule},
        {"channels", &Params::channels}, {"ranks", &Params::ranks},
        {"bankgroups", &Params::bankgroups}, {"banks", &Params::banks},
        {"rows", &Params::rows}, {"page_bytes", &Params::page_bytes},
        {"width_bits", &Params::width_bits}, {"burst_length", &Params::burst_length},
        {"mtps", &Params::mtps}, {"tCK", &Params::tCK},
        {"tRCD", &Params::tRCD}, {"tRP", &Params::tRP}, {"tRPab", &Params::tRPab},
        {"tRAS", &Params::tRAS}, {"tRC", &Params::tRC},
        {"tRL", &Params::tRL}, {"tWL", &Params::tWL},
        {"tRRD_S", &Params::tRRD_S}, {"tRRD_L", &Params::tRRD_L}, {"tFAW", &Params::tFAW},
        {"tCCD_S", &Params::tCCD_S}, {"tCCD_L", &Params::tCCD_L},
        {"tWTR_S", &Params::tWTR_S}, {"tWTR_L", &Params::tWTR_L},
        {"tRTW", &Params::tRTW}, {"tRTW_L", &Params::tRTW_L},
        {"tWR", &Params::tWR}, {"tRTP", &Params::tRTP},
        {"tREFI", &Params::tREFI}, {"tRFC", &Params::tRFC},
        {"wq_depth", &Params::wq_depth}, {"wq_high", &Params::wq_high}, {"wq_low", &Params::wq_low},
        {"hb_ck_ps", &Params::hb_ck_ps}, {"hb_ca_clks", &Params::hb_ca_clks},
        {"hb_lat_clks", &Params::hb_lat_clks}, {"hb_fixed_2x", &Params::hb_fixed_2x},
        {"hb_bus_bytes", &Params::hb_bus_bytes}, {"hb_csm_ps", &Params::hb_csm_ps},
        {"hb_rwr_ps", &Params::hb_rwr_ps},
    };
    return f;
}

// The string fields, by name.
inline const std::vector<std::pair<const char *, std::string Params::*>> &str_fields()
{
    static const std::vector<std::pair<const char *, std::string Params::*>> f = {
        {"kind", &Params::kind}, {"mapping", &Params::mapping},
    };
    return f;
}

struct Stats
{
    uint64_t reads = 0;
    uint64_t writes = 0;
    uint64_t bursts = 0;
    uint64_t row_hits = 0;
    uint64_t row_misses = 0;     // bank was precharged
    uint64_t row_conflicts = 0;  // another row was open
    uint64_t refreshes = 0;
    uint64_t forwarded = 0;      // reads answered from the write queue
    uint64_t merged = 0;         // writes merged into a queued one
    int64_t busy_ps = 0;         // time the data bus spent transferring
};

class Engine
{
public:
    explicit Engine(const Params &p) : p(p)
    {
        if (p.kind == "hyperram")
        {
            this->hyperram = true;
            if (p.hb_ck_ps <= 0 || p.hb_bus_bytes <= 0 || p.granule <= 0)
                throw std::invalid_argument("hyperram: clock, bus width and granule must be positive");
            return;
        }
        if (p.kind != "dram")
            throw std::invalid_argument("unknown memory kind '" + p.kind + "'");

        this->burst_bytes = (int64_t)p.width_bits / 8 * p.burst_length;
        this->burst_ps = (int64_t)p.burst_length * 1000000 / p.mtps;
        this->align = std::max(p.granule, this->burst_bytes);

        check_pow2(p.channels, "channels");
        check_pow2(p.ranks, "ranks");
        check_pow2(p.bankgroups, "bankgroups");
        check_pow2(p.banks, "banks");
        check_pow2(p.rows, "rows");
        check_pow2(this->burst_bytes, "burst bytes (width_bits/8 * burst_length)");
        check_pow2(this->align, "granule");
        if (p.page_bytes % this->burst_bytes != 0)
            throw std::invalid_argument("page_bytes must be a multiple of the burst size");
        check_pow2(p.page_bytes / this->burst_bytes, "bursts per page");

        this->offset_bits = log2i(this->burst_bytes);
        parse_mapping();

        if (p.wq_depth < 0 || (p.wq_depth > 0 && !(0 < p.wq_low && p.wq_low <= p.wq_high && p.wq_high < p.wq_depth)))
            throw std::invalid_argument("write queue needs 0 < wq_low <= wq_high < wq_depth");

        this->chan.resize(p.channels);
        for (Channel &c : this->chan)
        {
            c.banks.resize((size_t)p.ranks * p.bankgroups * p.banks);
            c.next_refresh = p.tREFI;
            c.faw.resize(p.ranks);
        }
    }

    // Completion time of an access arriving at now_ps. A read completes when
    // its last byte is back; a write when it is in the write queue, or, with
    // no queue, when its last byte has been written.
    int64_t access(int64_t now_ps, uint64_t addr, uint64_t size, bool is_write)
    {
        if (size == 0) size = 1;
        if (is_write) this->st.writes++; else this->st.reads++;

        if (this->hyperram)
            return this->access_hyperram(now_ps, addr, size, is_write);

        uint64_t first = addr & ~(uint64_t)(this->align - 1);
        uint64_t last = (addr + size - 1) | (uint64_t)(this->align - 1);

        int64_t arrive = now_ps + this->p.ctrl_ps / 2;
        int64_t done = arrive;
        for (uint64_t a = first; a < last; a += this->burst_bytes)
        {
            if (this->p.wq_depth > 0)
                done = std::max(done, this->queued(arrive, a, is_write));
            else
                done = std::max(done, this->burst(arrive, a, is_write));
        }
        return done + (this->p.ctrl_ps - this->p.ctrl_ps / 2);
    }

    // Unloaded read of one granule from a precharged bank: what a cache miss
    // costs when nothing else is going on. The board generator computes the
    // same figure for the headers; the unit tests keep the two in step.
    int64_t nominal_read_ps() const
    {
        Engine fresh(this->p);
        return fresh.access(0, 0, (uint64_t)this->p.granule, false);
    }

    const Stats &stats() const { return this->st; }
    int64_t get_burst_ps() const { return this->burst_ps; }
    int64_t get_burst_bytes() const { return this->burst_bytes; }

    // Decoded coordinates of a burst address, for tests and traces.
    struct Coord { int ch, ra, bg, ba; int64_t row, col; };
    Coord decode(uint64_t addr) const
    {
        Coord c{0, 0, 0, 0, 0, 0};
        uint64_t a = addr >> this->offset_bits;
        for (auto it = this->fields.rbegin(); it != this->fields.rend(); ++it)
        {
            uint64_t v = a & ((1ULL << it->bits) - 1);
            a >>= it->bits;
            switch (it->id)
            {
                case 'h': c.ch = (int)v; break;
                case 'a': c.ra = (int)v; break;
                case 'g': c.bg = (int)v; break;
                case 'b': c.ba = (int)v; break;
                case 'r': c.row = (int64_t)v; break;
                case 'c': c.col = (int64_t)v; break;
            }
        }
        return c;
    }

private:
    struct Bank
    {
        int64_t open_row = -1;
        int64_t act = INT64_MIN / 4;   // last ACTIVATE
        int64_t act_ok = 0;            // earliest next ACTIVATE (refresh, tRP)
        int64_t pre_ok = 0;            // earliest PRECHARGE (tRTP, tWR)
    };

    struct Channel
    {
        std::vector<Bank> banks;
        int64_t order = 0;             // first command of the previous burst
        int64_t bus_free = 0;
        int64_t last_col = INT64_MIN / 4;
        int last_col_rank = -1, last_col_bg = -1;
        bool last_was_write = false;
        int64_t last_write_end = INT64_MIN / 4;
        int64_t last_act = INT64_MIN / 4;
        int last_act_rank = -1, last_act_bg = -1;
        std::vector<std::deque<int64_t>> faw;   // per rank, last 4 ACTs
        int64_t next_refresh = 0;
    };

    struct Field { char id; int bits; };

    static int log2i(int64_t v)
    {
        int b = 0;
        while ((1LL << b) < v) b++;
        return b;
    }

    static void check_pow2(int64_t v, const char *what)
    {
        if (v <= 0 || (v & (v - 1)) != 0)
            throw std::invalid_argument(std::string(what) + " must be a power of two");
    }

    void parse_mapping()
    {
        const std::string &m = this->p.mapping;
        if (m.size() % 2 != 0)
            throw std::invalid_argument("mapping '" + m + "' must be a sequence of 2-letter fields");
        bool seen[6] = {false, false, false, false, false, false};
        const char *names[6] = {"Ro", "Ra", "Bg", "Ba", "Co", "Ch"};
        const char ids[6] = {'r', 'a', 'g', 'b', 'c', 'h'};
        int64_t sizes[6] = {this->p.rows, this->p.ranks, this->p.bankgroups, this->p.banks,
                            this->p.page_bytes / this->burst_bytes, this->p.channels};
        for (size_t i = 0; i < m.size(); i += 2)
        {
            std::string tok = m.substr(i, 2);
            int k = -1;
            for (int j = 0; j < 6; j++)
                if (tok == names[j]) k = j;
            if (k < 0 || seen[k])
                throw std::invalid_argument("mapping '" + m + "': bad or repeated field '" + tok + "'");
            seen[k] = true;
            this->fields.push_back({ids[k], log2i(sizes[k])});
        }
        for (int j = 0; j < 6; j++)
            if (!seen[j] && sizes[j] > 1)
                throw std::invalid_argument("mapping '" + m + "' lacks field " + names[j]);
    }

    // Process every refresh due by `t` on channel `c`.
    void refresh(Channel &c, int64_t t)
    {
        if (this->p.tREFI <= 0) return;
        while (c.next_refresh <= t)
        {
            int64_t r = c.next_refresh;
            int64_t start = std::max(r, c.bus_free);
            bool any_open = false;
            for (Bank &b : c.banks)
            {
                if (b.open_row >= 0)
                {
                    any_open = true;
                    start = std::max({start, b.act + this->p.tRAS, b.pre_ok});
                }
                start = std::max(start, b.act_ok);
            }
            if (any_open) start += this->p.tRPab;
            int64_t end = start + this->p.tRFC;
            for (Bank &b : c.banks)
            {
                b.open_row = -1;
                b.act_ok = std::max(b.act_ok, end);
            }
            this->st.refreshes++;
            c.next_refresh += this->p.tREFI;

            // After one refresh every bank is closed and idle, so any further
            // refreshes that ended before `t` change nothing but the count.
            // Skip them in one step: an idle stretch must not cost a loop
            // iteration per 4 us of simulated time.
            if (c.next_refresh + this->p.tRFC <= t && end <= c.next_refresh)
            {
                int64_t n = (t - this->p.tRFC - c.next_refresh) / this->p.tREFI;
                if (n > 0)
                {
                    this->st.refreshes += (uint64_t)n;
                    c.next_refresh += n * this->p.tREFI;
                    int64_t last_end = c.next_refresh - this->p.tREFI + this->p.tRFC;
                    for (Bank &b : c.banks) b.act_ok = std::max(b.act_ok, last_end);
                }
            }
        }
    }

    // One burst through the write queue. Returns when a read's data is back,
    // or when a write has been accepted into the queue.
    int64_t queued(int64_t arrive, uint64_t addr, bool w)
    {
        this->drain_idle(arrive);

        for (const QueuedWrite &q : this->wq)
        {
            if (q.addr == addr)
            {
                if (w)
                {
                    this->st.merged++;
                    return arrive;
                }
                this->st.forwarded++;
                return arrive + this->p.tCK;
            }
        }
        if (!w)
            return this->burst(arrive, addr, false);

        // A full queue holds the write back until the oldest write on its way
        // out has left it -- that is when the master's write is accepted.
        int64_t t = arrive;
        this->retire(t);
        while ((int64_t)(this->wq.size() + this->leaving.size()) >= this->p.wq_depth)
        {
            if (this->leaving.empty())
                this->issue_oldest(t);
            t = std::max(t, this->leaving.front());
            this->leaving.pop_front();
        }
        this->wq.push_back({t, addr});
        if ((int64_t)this->wq.size() > this->p.wq_high)
        {
            while ((int64_t)this->wq.size() >= this->p.wq_low)
                this->issue_oldest(t);
        }
        return t;
    }

    // Send queued writes to the DRAM while it would otherwise sit idle, that
    // is, before `t`, when the next request arrives. A write goes only if its
    // command would issue before then: one that would still be waiting -- for
    // a turnaround, say -- stays queued, and that request goes first.
    void drain_idle(int64_t t)
    {
        while (!this->wq.empty())
        {
            const QueuedWrite &q = this->wq.front();
            Channel &c = this->chan[this->decode(q.addr).ch];
            int64_t start = std::max(q.arrive, c.order);
            if (start >= t)
                break;
            this->refresh(c, start);
            if (this->plan(start, q.addr, true).col >= t)
                break;
            this->issue_oldest(start);
        }
    }

    void issue_oldest(int64_t t)
    {
        QueuedWrite q = this->wq.front();
        this->wq.pop_front();
        this->leaving.push_back(this->burst(std::max(t, q.arrive), q.addr, true));
    }

    // Forget writes whose data has left the queue by `t`.
    void retire(int64_t t)
    {
        while (!this->leaving.empty() && this->leaving.front() <= t)
            this->leaving.pop_front();
    }

    // The command times one burst would get, worked out without touching any
    // state. Split from commit() so that refresh can ask whether a burst would
    // run into it, and the write queue whether a write would issue before the
    // next request arrives.
    struct Plan
    {
        Coord k;
        size_t bank;
        int kind;          // 0 row hit, 1 row miss (bank precharged), 2 row conflict
        int64_t act;       // ACTIVATE, when kind != 0
        int64_t first_cmd; // first command the burst issues (PRE, ACT or RD/WR)
        int64_t col;       // the RD/WR command
        int64_t end;       // last data beat
    };

    Plan plan(int64_t t, uint64_t addr, bool w) const
    {
        const Params &P = this->p;
        Plan pl;
        pl.k = this->decode(addr);
        const Coord &k = pl.k;
        const Channel &c = this->chan[k.ch];
        pl.bank = ((size_t)k.ra * P.bankgroups + k.bg) * P.banks + k.ba;
        const Bank &b = c.banks[pl.bank];

        if (b.open_row == k.row)
        {
            pl.kind = 0;
            pl.act = b.act;
            pl.col = std::max(t, b.act + P.tRCD);
            pl.first_cmd = pl.col;
        }
        else
        {
            int64_t act;
            if (b.open_row >= 0)
            {
                pl.kind = 2;
                int64_t pre = std::max({t, b.act + P.tRAS, b.pre_ok});
                act = pre + P.tRP;
                pl.first_cmd = pre;
            }
            else
            {
                pl.kind = 1;
                act = t;
                pl.first_cmd = -1;
            }
            act = std::max({act, b.act_ok, b.act + P.tRC});
            if (c.last_act_rank == k.ra)
                act = std::max(act, c.last_act + (c.last_act_bg == k.bg ? P.tRRD_L : P.tRRD_S));
            const std::deque<int64_t> &faw = c.faw[k.ra];
            if (faw.size() == 4) act = std::max(act, faw.front() + P.tFAW);
            if (pl.first_cmd < 0) pl.first_cmd = act;
            pl.act = act;
            pl.col = act + P.tRCD;
        }

        // Column command: ordering, bank-group spacing and bus turnarounds.
        bool same_bg = c.last_col_rank == k.ra && c.last_col_bg == k.bg;
        int64_t col = std::max(pl.col, c.last_col + (same_bg ? P.tCCD_L : P.tCCD_S));
        if (!w && c.last_was_write)
            col = std::max(col, c.last_write_end + (same_bg ? P.tWTR_L : P.tWTR_S));
        if (w && !c.last_was_write)
            col = std::max(col, c.last_col + (same_bg && P.tRTW_L ? P.tRTW_L : P.tRTW));

        int64_t lat = w ? P.tWL : P.tRL;
        int64_t data = std::max(col + lat, c.bus_free);
        pl.col = data - lat;
        pl.end = data + this->burst_ps;
        return pl;
    }

    void commit(const Plan &pl, bool w)
    {
        const Params &P = this->p;
        const Coord &k = pl.k;
        Channel &c = this->chan[k.ch];
        Bank &b = c.banks[pl.bank];

        if (pl.kind == 0)
        {
            this->st.row_hits++;
        }
        else
        {
            if (pl.kind == 2) this->st.row_conflicts++; else this->st.row_misses++;
            std::deque<int64_t> &faw = c.faw[k.ra];
            if (faw.size() == 4) faw.pop_front();
            faw.push_back(pl.act);
            c.last_act = pl.act;
            c.last_act_rank = k.ra;
            c.last_act_bg = k.bg;
            b.open_row = k.row;
            b.act = pl.act;
        }

        c.bus_free = pl.end;
        c.last_col = pl.col;
        c.last_col_rank = k.ra;
        c.last_col_bg = k.bg;
        c.last_was_write = w;
        if (w) c.last_write_end = pl.end;
        c.order = std::min(pl.first_cmd, pl.col);
        b.pre_ok = std::max(b.pre_ok, w ? pl.end + P.tCK + P.tWR : pl.col + P.tRTP);

        this->st.bursts++;
        this->st.busy_ps += this->burst_ps;
    }

    // Plan, let any refresh the burst would run into go first, commit.
    int64_t burst(int64_t arrive, uint64_t addr, bool w)
    {
        Channel &c = this->chan[this->decode(addr).ch];
        int64_t t = std::max(arrive, c.order);
        this->refresh(c, t);
        Plan pl = this->plan(t, addr, w);
        // A refresh that falls due before the burst's column command is
        // scheduled first: a controller does not start an access it would
        // have to interrupt.
        while (this->p.tREFI > 0 && pl.col >= c.next_refresh)
        {
            this->refresh(c, pl.col);
            pl = this->plan(t, addr, w);
        }
        this->commit(pl, w);
        return pl.end;
    }

    int64_t access_hyperram(int64_t now_ps, uint64_t addr, uint64_t size, bool is_write)
    {
        (void)is_write;
        const Params &P = this->p;
        uint64_t first = addr & ~(uint64_t)(P.granule - 1);
        uint64_t last = (addr + size - 1) | (uint64_t)(P.granule - 1);
        int64_t bytes = (int64_t)(last - first + 1);

        int64_t bytes_per_clk = 2 * (int64_t)P.hb_bus_bytes;
        int64_t lat = (int64_t)P.hb_lat_clks * (P.hb_fixed_2x ? 2 : 1);
        int64_t overhead = P.hb_ca_clks + lat;
        // Largest transfer that keeps CS# low for at most tCSM.
        int64_t max_clks = P.hb_csm_ps / P.hb_ck_ps - overhead;
        int64_t max_chunk = std::max<int64_t>(bytes_per_clk, max_clks * bytes_per_clk);

        int64_t t = std::max(now_ps + P.ctrl_ps / 2, this->hb_free);
        int64_t end = t;
        while (bytes > 0)
        {
            int64_t chunk = std::min(bytes, max_chunk);
            int64_t data_clks = (chunk + bytes_per_clk - 1) / bytes_per_clk;
            end = t + (overhead + data_clks) * P.hb_ck_ps;
            this->st.bursts++;
            this->st.busy_ps += data_clks * P.hb_ck_ps;
            bytes -= chunk;
            t = end + P.hb_rwr_ps;
        }
        this->hb_free = end + P.hb_rwr_ps;
        return end + (P.ctrl_ps - P.ctrl_ps / 2);
    }

    Params p;
    Stats st;
    bool hyperram = false;

    // dram
    int64_t burst_bytes = 0;
    int64_t burst_ps = 0;
    int64_t align = 0;
    int offset_bits = 0;
    std::vector<Field> fields;     // most significant first
    std::vector<Channel> chan;

    // dram write queue: bursts waiting, and the data-end times of those sent
    // to the DRAM but still occupying their slot
    struct QueuedWrite { int64_t arrive; uint64_t addr; };
    std::deque<QueuedWrite> wq;
    std::deque<int64_t> leaving;

    // hyperram
    int64_t hb_free = 0;
};

} // namespace hetero_dram
