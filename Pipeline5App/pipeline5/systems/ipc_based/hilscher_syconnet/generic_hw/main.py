"""The hilscher_syconnet_generic_hw MAIN ROUTINE: two phases - 100 the I/O List validation, 700 the SYCON.net
hardware handoff (hw/sycon-stations, hw/sycon-modules, hw/sycon-device-types into `<output root>/
SyconNetProjectInterface`, the folder Sycon5App builds the SYCON.net project from). The chapters live in
pipeline5/systems/generic_hw.py (shared with the TIA type)."""
from __future__ import annotations

from pipeline5.systems import generic_hw

PHASES = generic_hw.phases("ph_hardware_sycon", "pb_open_sycon_handoff", "hardware")

HANDLERS = {
    "validation": generic_hw.run_validation,
    "hardware": generic_hw.run_hardware_sycon,
}
