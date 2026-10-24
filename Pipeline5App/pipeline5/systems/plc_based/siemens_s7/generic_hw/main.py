"""The siemens_tia_generic_hw MAIN ROUTINE: two phases - 100 the I/O List validation, 700 the TIA hardware
(the siemens_s7 build + the hw/stations, hw/modules, hw/device-types export into the OP5 workspace).
The chapters themselves live in pipeline5/systems/generic_hw.py (shared with the SYCON.net type)."""
from __future__ import annotations

from pipeline5.systems import generic_hw

PHASES = generic_hw.phases("ph_hardware", "pb_open_hardware", "hardware")

HANDLERS = {
    "validation": generic_hw.run_validation,
    "hardware": generic_hw.run_hardware_tia,
}
