#
# Generator for the main-memory timing model. See dram.cpp for what the model
# does and dram_presets.py for the devices it can be.
#

import gvsoc.systree

from hetero import dram_presets


class Dram(gvsoc.systree.Component):
    """A real RAM device in front of a functional memory: every request is
    forwarded to the memory behind it, and the latency the master sees is the
    device's (banks, rows, refresh, bus) rather than a constant.

    Attributes
    ----------
    preset: str
        Device name, one of dram_presets.KINDS other than 'fixed'.
    overrides: dict
        Fields to replace after the preset is expanded (ps for timings), e.g.
        {'channels': 2, 'mapping': 'RoBaCoCh'}.
    stats: bool
        True to print a [HES-DRAM] counters line at the end of the simulation.
    """

    def __init__(self, parent: gvsoc.systree.Component, name: str, preset: str,
            overrides: dict = None, stats: bool = False):

        super().__init__(parent, name)

        self.add_sources(['hetero/dram.cpp'])

        self.params = dram_presets.params(preset, overrides)
        self.add_properties({'preset': preset, 'stats': stats, **self.params})

    def i_INPUT(self) -> gvsoc.systree.SlaveItf:
        """Master-facing port: the traffic that really reaches main memory."""
        return gvsoc.systree.SlaveItf(self, 'input', signature='io')

    def o_OUTPUT(self, itf: gvsoc.systree.SlaveItf):
        """Binds the port to the functional memory that holds the bytes."""
        self.itf_bind('output', itf, signature='io')
