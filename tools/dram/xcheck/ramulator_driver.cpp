/*
 * Timestamped trace driver for Ramulator2, used as the LPDDR5 reference in
 * the DRAM model cross-check (run.py). Ramulator2's own trace front-ends issue
 * as fast as the controller accepts; this one injects each request at its own
 * time through the External front-end -- the same entry point GVSoC's
 * memory.ramulator wrapper uses -- so the two models see identical arrivals.
 *
 *   ramulator_driver CONFIG.yaml TRACE
 *
 * TRACE lines: "<time_ps> R|W 0x<addr>". Output, one line per read:
 * "<arrive_ps> <done_ps> 0x<addr>", done being the cycle Ramulator2 completes
 * the request (its depart: last data beat back). Writes are injected as load
 * but not reported -- Ramulator2 retires them without a completion callback.
 */

#include <ramulator/base/config.h>
#include <ramulator/base/factory.h>
#include <ramulator/base/request.h>
#include <ramulator/frontend/i_frontend.h>
#include <ramulator/memory_system/i_memory_system.h>

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <fstream>
#include <sstream>
#include <string>

struct Entry { int64_t t_ps; bool write; uint64_t addr; };

int main(int argc, char **argv)
{
    if (argc != 3)
    {
        fprintf(stderr, "usage: %s CONFIG.yaml TRACE\n", argv[0]);
        return 2;
    }

    auto config = Ramulator::Config::parse_config_file(argv[1]);
    Ramulator::IFrontEnd *frontend = Ramulator::Factory::create_frontend(config);
    Ramulator::IMemorySystem *mem = Ramulator::Factory::create_memory_system(config);
    frontend->connect_memory_system(mem);
    mem->connect_frontend(frontend);

    // One memory-system tick is one DRAM command clock.
    double tck_ps = mem->get_tCK() * 1000.0;

    std::deque<Entry> pending;
    std::ifstream f(argv[2]);
    std::string line;
    while (std::getline(f, line))
    {
        if (line.empty() || line[0] == '#') continue;
        std::istringstream ls(line);
        Entry e;
        std::string rw, addr;
        ls >> e.t_ps >> rw >> addr;
        e.write = rw == "W";
        e.addr = strtoull(addr.c_str(), nullptr, 0);
        pending.push_back(e);
    }

    size_t outstanding = 0;
    int64_t clk = 0;
    while (!pending.empty() || outstanding > 0)
    {
        // Inject everything due by this clock, in order; a refused request
        // (controller buffer full) is retried next clock, as GVSoC would.
        while (!pending.empty() && pending.front().t_ps <= (int64_t)(clk * tck_ps))
        {
            Entry e = pending.front();
            bool ok;
            if (e.write)
            {
                ok = frontend->receive_external_requests(Ramulator::Request::Type::Write, e.addr, 0,
                    [](Ramulator::Request &) {}, 32);
            }
            else
            {
                int64_t arrive = e.t_ps;
                uint64_t addr = e.addr;
                ok = frontend->receive_external_requests(Ramulator::Request::Type::Read, e.addr, 0,
                    [arrive, addr, tck_ps, &outstanding](Ramulator::Request &r) {
                        printf("%lld %lld 0x%llx\n", (long long)arrive,
                               (long long)std::llround(r.depart * tck_ps),
                               (unsigned long long)addr);
                        outstanding--;
                    }, 32);
                if (ok) outstanding++;
            }
            if (!ok) break;
            pending.pop_front();
        }
        mem->tick();
        clk++;
        if (clk > (int64_t)1e9) { fprintf(stderr, "runaway simulation\n"); return 1; }
    }

    frontend->finalize();
    mem->finalize();
    return 0;
}
