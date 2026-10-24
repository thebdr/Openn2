"""The hilscher_syconnet_generic_hw System descriptor - a Hilscher SYCON.net PROFINET configuration, as a
plugin: the phases and handlers of pipeline5/systems/generic_hw.py, the handoff folder as its delivery tree,
no capabilities (no C&E, no diagnosis blocks), no symbols / builders / templates (nothing is generated for a
PLC). Registered in systems/catalog.py."""
from __future__ import annotations

from pipeline5.systems import generic_hw
from pipeline5.systems.ipc_based.hilscher_syconnet.generic_hw import main as _main
from pipeline5.systems.system_contract import BuilderRegistry, System, SystemCapabilities

SYSTEM = System(
    id="hilscher_syconnet_generic_hw",
    name_key="sys_hilscher_syconnet_generic_hw",
    taxonomy=("IPC_Based", "HilscherSYCONnet", "GenericHardware"),
    capabilities=SystemCapabilities(),
    phases=_main.PHASES,
    handlers=_main.HANDLERS,
    builders=BuilderRegistry(),
    output_layout=generic_hw.SYCON_LAYOUT,
)
