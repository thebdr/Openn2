"""The siemens_s7_safety System descriptor - Siemens PLC functional-safety logic, as a plugin.

This is the object the kernel receives wherever behavior differs per target system: the symbol
notation, the emit-kind writers (ALL of them - csv included), the builder registry the 800 engine
runs, the template inventory, the capability flags that gate shared phases, and - since step 5 -
the WHOLE GUI projection: `phases` (the phase bar + Run-all plan) and `handlers` (the run_* dispatch
table), both authored in `main.py` (this system's main routine). Registering it in
`systems/catalog.py` is what flips the New-project row available - no other wiring exists.

Registration order matters and is deliberate: SYSTEM is constructed first, then `block_builders`
is imported at the BOTTOM of this module - its `@builds` decorators write into `SYSTEM.builders`
(the classic plugin composition; a fresh import of this module is always fully registered).
"""
from __future__ import annotations

import os

from pipeline5.systems.plc_based.siemens_s7 import creation_info_csv as _creation_csv
from pipeline5.systems.plc_based.siemens_s7 import fc_xml_emitter as _fc_xml
from pipeline5.systems.plc_based.siemens_s7 import scl_emitter as _scl
from pipeline5.systems.plc_based.siemens_s7 import template_scanner as _templates
from pipeline5.systems.plc_based.siemens_s7.output_layout import LAYOUT
from pipeline5.systems.plc_based.siemens_s7.symbols import SYMBOLS
from pipeline5.systems.plc_based.siemens_s7.safety import main as _main
from pipeline5.systems.system_contract import BuilderRegistry, System, SystemCapabilities


def _emit_scl(block, table, ctx):
    """emit='scl': a ready SCL FUNCTION source shipped to ImportReady (no CreationInfo CSV)."""
    return _scl.write_scl(block["name"], table, ctx["import_dir"])


def _emit_fc(kind):
    """emit='fc_xml'/'fdback_xml': a ready SW.Blocks.FC XML shipped to ImportReady (no CSV)."""
    def write(block, table, ctx):
        return _fc_xml.write_fc_xml(block["name"], table, block["template_ref"],
                                    ctx["import_dir"], kind)
    return write


def _diag_config_dir() -> str:
    """The 640 open target: the folder ACTUALLY supplying this system's diagnosis config - resolved
    through the 4-tier walk (a project override opens the project's folder, else this package's)."""
    from pipeline5.config import resolver
    path = resolver.find(os.path.join("diagnosis", "type_diagnosis.csv"))
    return os.path.dirname(path) if path else ""


SYSTEM = System(
    id="siemens_s7_safety",
    name_key="sys_siemens_s7_safety",
    taxonomy=("PLC_Based", "SiemensS7", "Safety"),
    capabilities=SystemCapabilities(needs_ce_matrix=True, needs_diagnosis_blocks=True),
    phases=_main.PHASES,
    handlers=_main.HANDLERS,
    open_targets={"diag_config": _diag_config_dir},
    symbols=SYMBOLS,
    emitters={
        "csv": _creation_csv.write,
        "scl": _emit_scl,
        "fc_xml": _emit_fc("fc_xml"),
        "fdback_xml": _emit_fc("fdback_xml"),
    },
    builders=BuilderRegistry(),
    templates=_templates,
    output_layout=LAYOUT,
    config_root=os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_project"),
)

# Registration (deliberately LAST - see the module docstring): the builders decorate themselves
# into SYSTEM.builders on import.
from pipeline5.systems.plc_based.siemens_s7.safety import block_builders  # noqa: E402,F401
