"""The systems tree: platform -> toolchain -> system, plus the contract types and the catalog.

`system_contract` defines what a System IS; `catalog` is the one composition point that registers
them. Import surface for the GUI/project layers:

    from pipeline5.systems import catalog          # by_id() / catalog() / ALL_SYSTEMS
    from pipeline5.systems import system_contract  # System, SystemCapabilities, ...
"""
from pipeline5.systems import catalog, system_contract  # noqa: F401  (re-export)
