"""The siemens_s7_safety System descriptor - Siemens PLC functional-safety logic, as a plugin.

This is the object the kernel receives wherever behavior differs per target system: the symbol
notation, the emit-kind writers (ALL of them - csv included), the builder registry the 800 engine
runs, the template inventory, and the capability flags that gate shared phases. Registering it in
`systems/catalog.py` is what flips the New-project row available - no other wiring exists.

Registration order matters and is deliberate: SYSTEM is constructed first, then `block_builders`
is imported at the BOTTOM of this module - its `@builds` decorators write into `SYSTEM.builders`
(the classic plugin composition; a fresh import of this module is always fully registered).

Still arriving: phases/handlers (the GUI projection, step 5); config_root (the per-system config
tier, this step's config-regroup leg).
"""
from __future__ import annotations

from pipeline5.systems.plc_based.siemens_s7 import creation_info_csv as _creation_csv
from pipeline5.systems.plc_based.siemens_s7 import fc_xml_emitter as _fc_xml
from pipeline5.systems.plc_based.siemens_s7 import scl_emitter as _scl
from pipeline5.systems.plc_based.siemens_s7 import template_scanner as _templates
from pipeline5.systems.plc_based.siemens_s7.output_layout import LAYOUT
from pipeline5.systems.plc_based.siemens_s7.symbols import SYMBOLS
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


SYSTEM = System(
    id="siemens_s7_safety",
    name_key="sys_siemens_s7_safety",
    taxonomy=("PLC_Based", "SiemensS7", "Safety"),
    capabilities=SystemCapabilities(needs_ce_matrix=True, needs_diagnosis_blocks=True),
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
    config_root="",   # the per-system config tier arrives with the step-4 config regroup
)

# Registration (deliberately LAST - see the module docstring): the builders decorate themselves
# into SYSTEM.builders on import.
from pipeline5.systems.plc_based.siemens_s7.safety import block_builders  # noqa: E402,F401
