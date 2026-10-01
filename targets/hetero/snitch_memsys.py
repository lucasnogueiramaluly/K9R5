#
# Retuning of the Snitch/Spatz board memory system.
#
# GVSoC builds both boards from the same Soc class, which hardcodes
#
#     hbm_latency = 0 if arch.use_spatz else 100
#
# The zero is deliberate upstream — the Spatz RTL benchmarks it ships with run
# against a zero-latency memory — but it means instruction fetches that miss
# the cluster instruction cache refill from HBM for free, which is the one
# place the Spatz simulation has no memory delay at all.
#
# Rather than fork the ~90-line Soc to change one argument, the mapping is
# retuned on the built tree, before the configuration is generated. A real
# main-memory device (memsys.DRAM_KIND) is spliced in the same way.
#

from pulp.chips.snitch.snitch import SnitchBoard

from hetero import memsys

# Base address of the HBM window in the Snitch/Spatz address map
# (SnitchArch.Chip.Soc.hbm).
HBM_BASE = 0x8000_0000


def retune_hbm(board, latency: int):
    """Set the latency of the HBM mapping of `board`'s wide AXI router.

    Raises if the board does not look the way this code expects, so that a
    GVSoC update that moves the mapping is a loud failure rather than a
    simulation that silently keeps the old latency.
    """
    axi = board.get_component('chip/soc/wide_axi')
    mappings = axi.get_property('mappings')

    hbm = [mapping for mapping in mappings.values() if mapping['base'] == HBM_BASE]
    if len(hbm) != 1:
        raise RuntimeError(
            f"expected exactly one mapping at 0x{HBM_BASE:x} on chip/soc/wide_axi, "
            f"found {len(hbm)} — the GVSoC Snitch board layout changed")

    hbm[0]['latency'] = latency


def insert_dram(board):
    """Put the main-memory device between `board`'s chip and its HBM.

    The stock board binds chip.hbm straight to the memory; that binding is
    rewired to chip.hbm -> device -> memory. The board clock is also moved to
    memsys.FREQUENCY: GVSoC hardcodes 10 MHz there, at which a device timed in
    nanoseconds would cost a single cycle per access.
    """
    dram_ctrl = memsys.make_main_memory(board)
    mem = board.get_component('mem')
    chip = board.get_component('chip')

    hbm = [b for b in board.bindings
           if b[0] is chip and b[1] == 'hbm' and b[2] is mem and b[3] == 'input']
    if len(hbm) != 1:
        raise RuntimeError(
            "expected exactly one chip.hbm -> mem.input binding on the Snitch board, "
            f"found {len(hbm)} -- the GVSoC Snitch board layout changed")
    hbm[0][2] = dram_ctrl
    board.bind(dram_ctrl, 'output', mem, 'input')
    board.bind(board.get_component('clock'), 'out', dram_ctrl, 'clock')

    board.get_component('clock').add_properties({'frequency': memsys.FREQUENCY})


class SnitchRealBoard(SnitchBoard):
    """Snitch board whose HBM answers at the memory system's DRAM latency, or
    through the main-memory device when memsys.DRAM_KIND names one."""

    def __init__(self, parent, name: str, parser, options, spatz=False):
        super().__init__(parent, name, parser, options, spatz=spatz)

        if memsys.DRAM_KIND == 'fixed':
            retune_hbm(self, memsys.DRAM_LATENCY)
        else:
            retune_hbm(self, 0)
            insert_dram(self)


class SpatzRealBoard(SnitchRealBoard):
    """Spatz board whose HBM answers at the memory system's DRAM latency."""

    def __init__(self, parent, name: str, parser, options):
        super().__init__(parent, name, parser, options, spatz=True)
