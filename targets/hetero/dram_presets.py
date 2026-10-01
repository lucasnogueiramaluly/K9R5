#
# Main-memory device presets for the DRAM timing model (hetero/dram_core.hpp).
#
# Pure Python with no GVSoC imports: the board generators, the pipeline and the
# cross-check tools (tools/dram/) all build their parameters from here, so the
# simulation and its validation can never disagree about what "lpddr4" means.
#
# Every preset is written the way its source writes it -- JEDEC timings in
# clock cycles, the clock period in ps -- and params() turns it into the flat
# picosecond dictionary the C++ engine reads (keys = hetero_dram::int_fields()).
#
# Sources:
#   lpddr4   DRAMSys memspec JEDEC_8Gb_LPDDR4-3200_16bit.json (shipped with
#            GVSoC under add_dramsyslib_patches/dramsys_configs/memspec/)
#   lpddr4x  DRAMSys memspec JEDEC_1Gbx16_LPDDR4-4266.json (same place); the
#            LPDDR4X I/O changes power, not timing, so LPDDR4X-4266 is the
#            LPDDR4-4266 speed bin
#   lpddr5   Ramulator2 LPDDR5_6400 / LPDDR5_8Gb_x16 presets
#            (python/ramulator/dram/lpddr5.py, JESD209-5C, BG mode, CKR 4:1)
#   hyperram Infineon HyperRAM 2.0 (S27KS0642 / S70KS1282) data sheets,
#            200 MHz, x8: tACC 35 ns = 7 clocks, fixed 2x latency default,
#            tCSM 4 us, tRWR 35 ns
#

import math

KINDS = ('fixed', 'lpddr4', 'lpddr4x', 'lpddr5', 'hyperram')

# The controller's write queue, in bursts: posted writes, drained when the DRAM
# is idle or in a batch above the high watermark. These are Ramulator2's
# controller defaults (32 entries, watermarks 0.8 / 0.2): drain once more than
# 25.6 are queued, stop below 6.4.
_WRITE_QUEUE = {'wq_depth': 32, 'wq_high': 25, 'wq_low': 7}


def _lpddr4(tck_ps, mtps, rows, t):
    """An LPDDR4 x16 single-channel die from a DRAMSys memspec (timings in tCK).

    tRTW is not a memspec field. It is the JEDEC read-to-write turnaround,
    RL + tDQSCK + BL/2 + RPST + 1 - WL, from the same table.

    A read's data comes later than RL after the command starts: an LPDDR4
    read is a two-part command (RD-1 then CAS-2, two clocks each) and RL
    counts from the end of it, and the data then lags by the DQS access time
    tDQSCK (3.75 ns at 3200). Both are in the read latency here, as in DRAMSys;
    the cross-check (tools/dram/xcheck) is what showed they were missing.
    """
    return {
        'kind': 'dram', 'tCK': tck_ps, 'mtps': mtps, 'mapping': 'RoBaCo',
        'channels': 1, 'ranks': 1, 'bankgroups': 1, 'banks': 8,
        'rows': rows, 'page_bytes': 1024 * 2, 'width_bits': 16, 'burst_length': 16,
        **_WRITE_QUEUE,
        'clk': {
            'tRCD': t['RCD'], 'tRP': t['RPpb'], 'tRPab': t['RPab'], 'tRAS': t['RAS'],
            'tRC': t['RCpb'], 'tRL': 4 + t['RL'] + t['DQSCK'], 'tWL': t['WL'],
            'tRRD_S': t['RRD'], 'tRRD_L': t['RRD'], 'tFAW': t['FAW'],
            'tCCD_S': t['CCD'], 'tCCD_L': t['CCD'],
            'tWTR_S': t['WTR'], 'tWTR_L': t['WTR'],
            'tRTW': t['RL'] + t['DQSCK'] + 16 // 2 + t['RPST'] + 1 - t['WL'],
            'tWR': t['WR'], 'tRTP': t['RTP'], 'tREFI': t['REFI'], 'tRFC': t['RFCab'],
        },
    }


PRESETS = {
    'lpddr4': _lpddr4(625, 3200, 65536, {
        'RCD': 29, 'RPpb': 29, 'RPab': 34, 'RAS': 68, 'RCpb': 97, 'RL': 28, 'WL': 14,
        'RRD': 16, 'FAW': 64, 'CCD': 8, 'WTR': 16, 'DQSCK': 6, 'RPST': 0,
        'WR': 29, 'RTP': 12, 'REFI': 6246, 'RFCab': 448}),

    'lpddr4x': _lpddr4(469, 4266, 131072, {
        'RCD': 39, 'RPpb': 39, 'RPab': 45, 'RAS': 90, 'RCpb': 129, 'RL': 36, 'WL': 18,
        'RRD': 22, 'FAW': 86, 'CCD': 8, 'WTR': 22, 'DQSCK': 4, 'RPST': 0,
        'WR': 39, 'RTP': 17, 'REFI': 8341, 'RFCab': 812}),

    # 16 banks as 4 bank groups of 4. Ramulator2 gives the bank-group-mode
    # tRRD (5 ns) and tFAW (20 ns) in ns; the nCK values below are theirs
    # rounded up, as Ramulator2 does. A BL16 burst on x16 is 32 bytes in
    # nBL_min = 2 CK (2.5 ns). The bank group is the lowest field of the
    # mapping, so the two bursts of a cache line land in different groups and
    # stream at tCCD_S rather than stalling on tCCD_L -- the reason bank-group
    # mode exists.
    #
    # The rest follows Ramulator2's constraint table, translated to this
    # engine's terms (its column command is the CAS that opens a RD/WR):
    #   - a CAS (WCK sync) command goes one clock before every RD/WR, so data
    #     comes nCL + 1 / nCWL + 1 after it;
    #   - write to read is nCWL + BL/n + nWTR from the WR, with BL/n_max
    #     (4 CK) within a bank group and BL/n_min (2 CK) across; the engine
    #     counts from the end of the write data (+1 for the CAS, + BL/n_min),
    #     so tWTR_L = nWTRL + 2 - 1 and tWTR_S = nWTRS - 1;
    #   - read to write is nCL + BL/n + 2 - nCWL, n_max within a group (14 CK),
    #     n_min across (12 CK);
    #   - write recovery to PRE is nCWL + nBL_min + 1 + nWR (the engine adds
    #     the +1 itself).
    'lpddr5': {
        'kind': 'dram', 'tCK': 1250, 'mtps': 6400, 'mapping': 'RoBaCoBg',
        'channels': 1, 'ranks': 1, 'bankgroups': 4, 'banks': 4,
        'rows': 1 << 15, 'page_bytes': 1024 * 2, 'width_bits': 16, 'burst_length': 16,
        **_WRITE_QUEUE,
        'clk': {
            'tRCD': 15, 'tRP': 15, 'tRPab': 17, 'tRAS': 34, 'tRC': 49,
            'tRL': 17 + 1, 'tWL': 9 + 1,
            'tRRD_S': 4, 'tRRD_L': 4, 'tFAW': 16,
            'tCCD_S': 2, 'tCCD_L': 4,
            'tWTR_S': 5 - 1, 'tWTR_L': 10 + 2 - 1,
            'tRTW': 17 + 2 + 2 - 9, 'tRTW_L': 17 + 4 + 2 - 9,
            'tWR': 28, 'tRTP': 6,
            'tREFI': 3_906_000 // 1250, 'tRFC': math.ceil(210_000 / 1250),
        },
    },

    'hyperram': {
        'kind': 'hyperram',
        'hb_ck_ps': 5000, 'hb_ca_clks': 3, 'hb_lat_clks': 7, 'hb_fixed_2x': 1,
        'hb_bus_bytes': 1, 'hb_csm_ps': 4_000_000, 'hb_rwr_ps': 35_000,
    },
}

# What the engine assumes when a preset leaves a field out (Params defaults).
_DEFAULTS = {
    'kind': 'dram', 'mapping': 'RoBaCo', 'ctrl_ps': 20000, 'granule': 64,
    'channels': 1, 'ranks': 1, 'bankgroups': 1, 'banks': 8, 'rows': 65536,
    'page_bytes': 2048, 'width_bits': 16, 'burst_length': 16, 'mtps': 3200,
    'tCK': 625, 'tRCD': 0, 'tRP': 0, 'tRPab': 0, 'tRAS': 0, 'tRC': 0, 'tRL': 0,
    'tWL': 0, 'tRRD_S': 0, 'tRRD_L': 0, 'tFAW': 0, 'tCCD_S': 0, 'tCCD_L': 0,
    'tWTR_S': 0, 'tWTR_L': 0, 'tRTW': 0, 'tRTW_L': 0, 'tWR': 0, 'tRTP': 0, 'tREFI': 0, 'tRFC': 0,
    'wq_depth': 0, 'wq_high': 0, 'wq_low': 0,
    'hb_ck_ps': 5000, 'hb_ca_clks': 3, 'hb_lat_clks': 7, 'hb_fixed_2x': 1,
    'hb_bus_bytes': 1, 'hb_csm_ps': 4_000_000, 'hb_rwr_ps': 35_000,
}

# Keys a caller may override on top of a preset (everything the engine reads).
FIELDS = tuple(_DEFAULTS)


def params(kind, overrides=None):
    """The flat parameter dict (ps, ints) the C++ engine reads for `kind`.

    `overrides` replaces fields after the preset is expanded, so a timing given
    there is in ps like the result, not in clocks.
    """
    if kind not in PRESETS:
        raise ValueError(f"unknown DRAM kind {kind!r}; choose one of "
                         f"{', '.join(k for k in KINDS if k != 'fixed')}")
    preset = dict(PRESETS[kind])
    clk = preset.pop('clk', {})
    out = dict(_DEFAULTS)
    out.update(preset)
    for name, cycles in clk.items():
        out[name] = cycles * preset['tCK']
    for name, value in (overrides or {}).items():
        if name not in _DEFAULTS:
            raise ValueError(f"unknown DRAM parameter {name!r}")
        out[name] = value
    return out


def nominal_read_ps(p):
    """Unloaded read of one granule from a precharged bank (or an idle
    HyperBus), in ps. Mirrors Engine::nominal_read_ps(); the unit tests check
    that the two agree for every preset."""
    if p['kind'] == 'hyperram':
        per_clk = 2 * p['hb_bus_bytes']
        lat = p['hb_lat_clks'] * (2 if p['hb_fixed_2x'] else 1)
        clks = p['hb_ca_clks'] + lat + -(-p['granule'] // per_clk)
        return p['ctrl_ps'] + clks * p['hb_ck_ps']
    burst_bytes = p['width_bits'] // 8 * p['burst_length']
    burst_ps = p['burst_length'] * 1_000_000 // p['mtps']
    nb = max(1, max(p['granule'], burst_bytes) // burst_bytes)
    # First burst: ACT, tRCD, RL, transfer. The rest stream behind it, one
    # column-to-column gap apart, or one burst apart when the bus is the limit.
    # With the bank group as the lowest mapping field each burst opens a row in
    # the next group: the gap is then tRRD_S / tCCD_S. Otherwise they are row
    # hits in the same bank, tCCD_L apart.
    if p['bankgroups'] > 1 and p['mapping'].endswith('Bg'):
        gap = max(burst_ps, p['tCCD_S'], p['tRRD_S'])
    else:
        gap = max(burst_ps, p['tCCD_L'])
    return p['ctrl_ps'] + p['tRCD'] + p['tRL'] + burst_ps + (nb - 1) * gap


def peak_bytes_per_ns(p):
    """Peak data-bus bandwidth of one channel, bytes per ns."""
    if p['kind'] == 'hyperram':
        return 2 * p['hb_bus_bytes'] * 1000 / p['hb_ck_ps']
    return p['width_bits'] / 8 * p['mtps'] / 1000 * p['channels']
