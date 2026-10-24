"""The siemens_tia_generic_hw System descriptor - a Siemens TIA Portal hardware configuration, as a plugin:
the Siemens symbol notation and delivery tree (the hw/* tables land in the OP5 workspace exactly as the safety
system's), the phases and handlers of pipeline5/systems/generic_hw.py, no capabilities (no C&E, no diagnosis
blocks), no builders, no templates. Registered in systems/catalog.py."""
from __future__ import annotations

from pipeline5.systems.plc_based.siemens_s7.generic_hw import main as _main
from pipeline5.systems.plc_based.siemens_s7.output_layout import LAYOUT
from pipeline5.systems.plc_based.siemens_s7.symbols import SYMBOLS
from pipeline5.systems.system_contract import BuilderRegistry, System, SystemCapabilities

SYSTEM = System(
    id="siemens_tia_generic_hw",
    name_key="sys_siemens_tia_generic_hw",
    taxonomy=("PLC_Based", "SiemensS7", "GenericHardware"),
    capabilities=SystemCapabilities(),
    phases=_main.PHASES,
    handlers=_main.HANDLERS,
    symbols=SYMBOLS,
    builders=BuilderRegistry(),
    output_layout=LAYOUT,
)
