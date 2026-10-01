/*
 * Main-memory timing model for the hetero-sim boards: a real RAM device
 * (LPDDR4, LPDDR4X, LPDDR5 or HyperRAM) in front of the functional memory.
 *
 * Like the timing cache, this component holds no data. Every request is
 * forwarded verbatim to the memory behind it, so the bytes are always the
 * memory's; what this model owns is the latency. The device behaviour -- banks,
 * open rows, refresh, bus turnarounds, the HyperBus latency -- lives in
 * dram_core.hpp, which is plain C++ so that the unit tests and the DRAMSys /
 * Ramulator2 cross-check run the very same code (tools/dram/).
 *
 * Time is kept in picoseconds inside the engine and converted to cycles of
 * this component's clock on the way out, so a device keeps its real speed
 * whatever the core clock is: what changes with FREQUENCY is how many core
 * cycles a DRAM access costs, which is the point.
 *
 * Debug requests (the loader, gdb, and the hits the timing caches forward only
 * to fetch bytes) are passed through untimed and leave the device state alone.
 * They are not accesses the hardware performed, and letting them advance the
 * bank and bus cursors would push those cursors ahead of simulated time -- the
 * same failure the router bandwidth limiter had (see deps/patches/
 * gvsoc-core-vector-host-ara.patch).
 */

#include <vp/vp.hpp>
#include <vp/itf/io.hpp>
#include <vp/debug_mem.hpp>

#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>

#include "dram_core.hpp"

class Dram : public vp::Component, public vp::DebugMemIf
{

public:
    Dram(vp::ComponentConf &config);

    void stop() override;

    // Transparent to backdoor accesses, as the timing cache is: the data lives
    // behind this component (see TimingCache::debug_mem_access).
    vp::DebugMemIf *debug_mem_if() override { return this; }
    int debug_mem_access(uint64_t addr, uint8_t *data, uint64_t size,
        bool is_write) override;
    void debug_mem_regions(std::vector<vp::DebugMemRegion> &regions,
        uint64_t local_base, uint64_t window_size, uint64_t entry_base,
        int depth) override;

private:
    static vp::IoReqStatus req(vp::Block *__this, vp::IoReq *req);

    vp::DebugMemIf *next_level_backdoor();
    vp::DebugMemIf *backdoor = NULL;
    bool backdoor_resolved = false;

    vp::Trace trace;
    vp::IoSlave input_itf;
    vp::IoMaster output_itf;

    std::string kind_name;
    hetero_dram::Engine *engine = NULL;
    bool stats;
    uint64_t nb_latency_cycles = 0;
};

vp::DebugMemIf *Dram::next_level_backdoor()
{
    if (!this->backdoor_resolved)
    {
        this->backdoor_resolved = true;
        std::vector<vp::SlavePort *> finals = this->output_itf.get_final_ports();
        if (!finals.empty() && finals[0]->get_owner() != nullptr)
        {
            this->backdoor = finals[0]->get_owner()->debug_mem_if();
        }
    }
    return this->backdoor;
}

int Dram::debug_mem_access(uint64_t addr, uint8_t *data, uint64_t size, bool is_write)
{
    vp::DebugMemIf *next = this->next_level_backdoor();
    if (next == NULL)
    {
        return -1;
    }
    return next->debug_mem_access(addr, data, size, is_write);
}

void Dram::debug_mem_regions(std::vector<vp::DebugMemRegion> &regions,
    uint64_t local_base, uint64_t window_size, uint64_t entry_base, int depth)
{
    vp::DebugMemIf *next = this->next_level_backdoor();
    if (next != NULL)
    {
        next->debug_mem_regions(regions, local_base, window_size, entry_base, depth + 1);
    }
}

Dram::Dram(vp::ComponentConf &config)
    : vp::Component(config)
{
    this->traces.new_trace("trace", &this->trace, vp::DEBUG);

    this->input_itf.set_req_meth(&Dram::req);
    this->new_slave_port("input", &this->input_itf);
    this->new_master_port("output", &this->output_itf);

    js::Config *conf = this->get_js_config();
    this->stats = conf->get_child_bool("stats");
    this->kind_name = conf->get_child_str("preset");

    // The generator (hetero/dram.py) always passes every field, so a missing
    // one means the two sides were built from different versions: refuse to
    // run on a silently defaulted timing.
    hetero_dram::Params p;
    for (auto &f : hetero_dram::int_fields())
    {
        js::Config *v = conf->get(f.first);
        if (v == NULL)
        {
            this->trace.fatal("Missing DRAM parameter '%s'\n", f.first);
        }
        p.*(f.second) = v->get_int();
    }
    for (auto &f : hetero_dram::str_fields())
    {
        js::Config *v = conf->get(f.first);
        if (v == NULL)
        {
            this->trace.fatal("Missing DRAM parameter '%s'\n", f.first);
        }
        p.*(f.second) = v->get_str();
    }

    try
    {
        this->engine = new hetero_dram::Engine(p);
    }
    catch (const std::exception &e)
    {
        this->trace.fatal("Invalid DRAM configuration (%s): %s\n", this->kind_name.c_str(), e.what());
    }
}

vp::IoReqStatus Dram::req(vp::Block *__this, vp::IoReq *req)
{
    Dram *_this = (Dram *)__this;

    vp::IoReqStatus status = _this->output_itf.req_forward(req);

    if (req->is_debug() || status == vp::IO_REQ_INVALID)
    {
        return status;
    }

    // The functional memory behind this model answers synchronously; the
    // latency below replaces whatever it reported. An asynchronous answer
    // would need its own response path, which nothing here needs yet.
    if (status != vp::IO_REQ_OK)
    {
        _this->trace.fatal("The memory behind the DRAM model answered asynchronously\n");
        return status;
    }

    int64_t period = _this->clock.get_period();
    int64_t now = _this->clock.get_cycles() * period;
    int64_t done = _this->engine->access(now, req->get_addr(), req->get_size(), req->get_is_write());
    int64_t latency = (done - now + period - 1) / period;

    _this->nb_latency_cycles += latency;
    _this->trace.msg(vp::Trace::LEVEL_TRACE,
                     "Access (addr: 0x%llx, size: 0x%llx, is_write: %d, latency: %lld)\n",
                     (unsigned long long)req->get_addr(), (unsigned long long)req->get_size(),
                     req->get_is_write(), (long long)latency);

    req->set_exact_latency(latency);
    return vp::IO_REQ_OK;
}

void Dram::stop()
{
    if (this->stats)
    {
        const hetero_dram::Stats &s = this->engine->stats();
        printf("[HES-DRAM] mem=%s kind=%s reads=%llu writes=%llu bursts=%llu row_hits=%llu "
               "row_misses=%llu row_conflicts=%llu refreshes=%llu busy_ns=%.3f latency_cycles=%llu\n",
               this->get_path().c_str(), this->kind_name.c_str(),
               (unsigned long long)s.reads, (unsigned long long)s.writes,
               (unsigned long long)s.bursts, (unsigned long long)s.row_hits,
               (unsigned long long)s.row_misses, (unsigned long long)s.row_conflicts,
               (unsigned long long)s.refreshes, s.busy_ps / 1000.0,
               (unsigned long long)this->nb_latency_cycles);
        fflush(stdout);
    }
}

extern "C" vp::Component *gv_new(vp::ComponentConf &config)
{
    return new Dram(config);
}
