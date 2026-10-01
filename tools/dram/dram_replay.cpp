/*
 * Replay a memory trace through the DRAM timing engine, outside GVSoC.
 *
 *   dram_replay PARAMS.json --nominal
 *       Print the unloaded one-granule read latency (ps). check_presets.py
 *       compares it with the Python mirror in hetero/dram_presets.py.
 *
 *   dram_replay PARAMS.json TRACE.stl --clk-mhz F --size N [--per-request]
 *       Replay a DRAMSys "STL" trace (lines "<cycle>:\tread|write\t0x<addr>",
 *       cycles at F MHz, every request N bytes) and print a summary. Requests
 *       are issued at their timestamps, open loop, as the DRAMSys trace player
 *       issues them, so the two can be compared directly.
 *
 * PARAMS.json is a flat dump of hetero/dram_presets.params(kind).
 */

#include "params_io.hpp"

#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>

using namespace hetero_dram;

int main(int argc, char **argv)
{
    if (argc < 3)
    {
        fprintf(stderr, "usage: %s PARAMS.json --nominal | TRACE.stl --clk-mhz F --size N [--per-request]\n", argv[0]);
        return 2;
    }

    try
    {
        Params p = load_params(argv[1]);
        Engine e(p);

        if (strcmp(argv[2], "--nominal") == 0)
        {
            printf("%lld\n", (long long)e.nominal_read_ps());
            return 0;
        }

        double clk_mhz = 0;
        uint64_t size = 64;
        bool per_request = false;
        for (int i = 3; i < argc; i++)
        {
            if (!strcmp(argv[i], "--clk-mhz") && i + 1 < argc) clk_mhz = atof(argv[++i]);
            else if (!strcmp(argv[i], "--size") && i + 1 < argc) size = strtoull(argv[++i], nullptr, 0);
            else if (!strcmp(argv[i], "--per-request")) per_request = true;
            else { fprintf(stderr, "unknown argument %s\n", argv[i]); return 2; }
        }
        if (clk_mhz <= 0) { fprintf(stderr, "--clk-mhz is required\n"); return 2; }

        std::ifstream f(argv[2]);
        if (!f) { fprintf(stderr, "cannot open %s\n", argv[2]); return 2; }

        std::string line;
        uint64_t n = 0;
        int64_t sum_lat = 0, max_lat = 0, first = -1, last_done = 0;
        while (std::getline(f, line))
        {
            if (line.empty() || line[0] == '#') continue;
            std::istringstream ls(line);
            std::string ts, cmd, addr;
            ls >> ts >> cmd >> addr;
            if (!ts.empty() && ts.back() == ':') ts.pop_back();
            int64_t t = (int64_t)(std::stod(ts) * 1e6 / clk_mhz + 0.5);
            bool w = cmd == "write";
            int64_t done = e.access(t, strtoull(addr.c_str(), nullptr, 0), size, w);
            int64_t lat = done - t;
            if (per_request) printf("%lld %s %s %lld\n", (long long)t, cmd.c_str(), addr.c_str(), (long long)lat);
            if (first < 0) first = t;
            sum_lat += lat;
            max_lat = std::max(max_lat, lat);
            last_done = std::max(last_done, done);
            n++;
        }

        const Stats &s = e.stats();
        double span_ns = (last_done - first) / 1000.0;
        printf("requests=%llu mean_latency_ns=%.3f max_latency_ns=%.3f span_ns=%.3f "
               "bandwidth_gbps=%.3f row_hits=%llu row_misses=%llu row_conflicts=%llu refreshes=%llu\n",
               (unsigned long long)n, n ? sum_lat / 1000.0 / n : 0.0, max_lat / 1000.0, span_ns,
               span_ns > 0 ? n * size / span_ns : 0.0,
               (unsigned long long)s.row_hits, (unsigned long long)s.row_misses,
               (unsigned long long)s.row_conflicts, (unsigned long long)s.refreshes);
    }
    catch (const std::exception &ex)
    {
        fprintf(stderr, "error: %s\n", ex.what());
        return 1;
    }
    return 0;
}
