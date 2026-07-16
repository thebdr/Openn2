"""The siemens_s7_safety System descriptor - Siemens PLC functional-safety logic, as a plugin.

This is the object the kernel receives wherever behavior differs per target system: the symbol
notation, the emit-kind writers, the capability flags that gate shared phases. Registering it in
`systems/catalog.py` is what flips the New-project row available - no other wiring exists.

TRANSITIONAL notes (each burns down at its step):
  - emitters wrap the writers still living in the phases' _siemens_s7/ quarantines (step 4 moves
    them here); the "csv" CreationInfo writer stays internal to the build engine until step 4.
  - builders proxies the module-global registry (instance-based conversion lands at step 4).
  - phases/handlers arrive with the GUI projection (step 5).
"""
from __future__ import annotations

from pipeline5.phases.software_blocks import builder_registry as _module_registry
from pipeline5.phases.software_blocks._siemens_s7 import scl_emit as _scl_emit
from pipeline5.phases.software_blocks._siemens_s7 import xml_emit as _xml_emit
from pipeline5.systems.plc_based.siemens_s7.output_layout import LAYOUT
from pipeline5.systems.plc_based.siemens_s7.symbols import SYMBOLS
from pipeline5.systems.system_contract import BuilderRegistry, System, SystemCapabilities


class _ModuleRegistryProxy(BuilderRegistry):
    """TRANSITIONAL: presents the module-global builder registry through the instance API, so the
    descriptor is complete while the @builds decorators still write to the module (step 4 flips
    the direction: builders will register into SYSTEM.builders and the module global dies)."""

    def builds(self, name: str, emit: str = "csv"):
        return _module_registry.builds(name, emit)

    def registry(self) -> dict:
        return _module_registry.registry()

    def emit_kind(self, name: str) -> str:
        return _module_registry.emit_kind(name)


def _emit_scl(block, table, ctx):
    """emit='scl': a ready SCL FUNCTION source shipped to ImportReady (no CreationInfo CSV)."""
    return _scl_emit.write_scl(block["name"], table, ctx["import_dir"])


def _emit_fc_xml(block, table, ctx):
    """emit='fc_xml'/'fdback_xml': a ready SW.Blocks.FC XML shipped to ImportReady (no CSV)."""
    return _xml_emit.write_fc_xml(block["name"], table, block["template_ref"], ctx["import_dir"])


SYSTEM = System(
    id="siemens_s7_safety",
    name_key="sys_siemens_s7_safety",
    taxonomy=("PLC_Based", "SiemensS7", "Safety"),
    capabilities=SystemCapabilities(needs_ce_matrix=True, needs_diagnosis_blocks=True),
    symbols=SYMBOLS,
    emitters={
        # "csv" (the CreationInfo default) is written by the build engine itself until step 4.
        "scl": _emit_scl,
        "fc_xml": _emit_fc_xml,
        "fdback_xml": _emit_fc_xml,
    },
    builders=_ModuleRegistryProxy(),
    output_layout=LAYOUT,
    config_root="",   # the per-system config tier arrives with the step-4 regroup
)
