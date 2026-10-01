#
# hetero_models: a build-only target that makes GVSoC compile the models the
# real boards instantiate only under some design choices.
#
# GVSoC compiles a Python-described model (add_sources) only when a target it
# builds instantiates it, and names the result after its sources -- so one
# module serves every target that uses the model at run time. The main-memory
# device (hetero/dram.cpp) appears in the boards only when memsys.DRAM_KIND is
# not 'fixed', which is not the default, so without this target it would never
# be built and `--dram lpddr4` would fail to load it. Nothing runs this target.
#

import gvsoc.runner as gvsoc
import gvsoc.systree as st
import memory.memory as memory
from vp.clock_domain import Clock_domain

from hetero.dram import Dram


class ModelsBoard(st.Component):

    def __init__(self, parent, name, parser, options):
        super().__init__(parent, name, options=options)

        clock = Clock_domain(self, 'clock', frequency=1_000_000_000)
        dram_ctrl = Dram(self, 'dram_ctrl', 'lpddr4')
        mem = memory.Memory(self, 'mem', size=0x1000, width_log2=-1)

        dram_ctrl.o_OUTPUT(mem.i_INPUT())
        self.bind(clock, 'out', dram_ctrl, 'clock')
        self.bind(clock, 'out', mem, 'clock')


class Target(gvsoc.Target):

    gapy_description = "Build-only: compiles the optional hetero-sim models (not runnable)"

    def __init__(self, parser, options):
        super().__init__(parser, options, model=ModelsBoard)
