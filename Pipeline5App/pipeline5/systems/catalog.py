"""THE system registry - explicit imports, one composition point (PL5 plan, coupling #9/risk #5).

A system becomes creatable by being imported here and listed in `ALL_SYSTEMS` - New-project dialog
availability is DERIVED from registry membership (`by_id(t) is not None`); PL4's hardcoded
`PROJECT_TYPES` True/False column is dead. `PLANNED` keeps the roadmap rows visible-greyed in the
dialog until their `system.py` lands (registering a system supersedes its PLANNED row).

Kernel modules must NOT import this (they receive a System object); the consumers are the
GUI/project layers. The grep-gate test enforces the direction.
"""
from __future__ import annotations

# Migration step 3 registers the first system:
# from pipeline5.systems.plc_based.siemens_s7.safety.system import SYSTEM as SIEMENS_S7_SAFETY
ALL_SYSTEMS: tuple = ()

# Roadmap rows (id, i18n name key) - shown greyed until their system.py is registered above.
PLANNED: tuple = (
    ("siemens_s7_safety", "sys_siemens_s7_safety"),
    ("intervalzero_rtx_sorter", "sys_intervalzero_rtx_sorter"),
    ("intervalzero_rtx_induction", "sys_intervalzero_rtx_induction"),
    ("intervalzero_rtx_plant", "sys_intervalzero_rtx_plant"),
)


def _validate() -> None:
    """Fail loudly at import on a duplicate system id - a silent shadow would be a config nightmare."""
    seen = set()
    for system in ALL_SYSTEMS:
        if system.id in seen:
            raise ValueError(f"duplicate system id in ALL_SYSTEMS: {system.id!r}")
        seen.add(system.id)


_validate()


def by_id(system_id: str):
    """The registered System for `system_id`, or None (an unknown/planned-only id is NOT an error
    here - the caller decides how to report; open_project raises pointedly, the dialog greys)."""
    for system in ALL_SYSTEMS:
        if system.id == system_id:
            return system
    return None


def catalog() -> tuple:
    """The New-project dialog rows: ((id, name_key, available), ...) - every registered system
    (available) followed by the PLANNED rows not yet registered (greyed), stable order."""
    rows = [(s.id, s.name_key, True) for s in ALL_SYSTEMS]
    registered = {s.id for s in ALL_SYSTEMS}
    rows.extend((pid, key, False) for pid, key in PLANNED if pid not in registered)
    return tuple(rows)
