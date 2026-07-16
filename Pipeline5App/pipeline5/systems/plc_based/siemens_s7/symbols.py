"""How Siemens spells a symbol - the TIA quoting rules, in one place.

Everywhere the pipeline stores a reference to a PLC object (the `plc_binding` column, the SCL
assignments, the coverage trace), Siemens syntax wraps each part in double quotes and joins DB and
member with a dot: `"03_FDBACK"."Door Alarm [ =S1+A-K1 ]"`. This module is the ONLY place that
knows that - a different controller registers a different SymbolFormatter and the kernel never
notices (PL4 coupling #1, resolved).

Where you meet it in the app:
  - the signals table's `plc_binding` column (written back by the datablocks chapter)
  - every DiagList `PLC_Binding` cell and OPC SCL channel
  - the coverage report's placement references
"""
from __future__ import annotations

import re

from pipeline5.systems.system_contract import SymbolFormatter

_BINDING = re.compile(r'"([^"]+)"\."([^"]+)"')   # the TIA-qualified "<db>"."<member>" shape


class TiaSymbols(SymbolFormatter):
    """The TIA notation: quote() wraps one name; binding() joins a quoted DB and member."""

    def binding(self, db: str, member: str) -> str:
        return f'"{db}"."{member}"'

    def quote(self, name: str) -> str:
        return f'"{name}"'

    def parse_binding(self, text: str):
        """The first "<db>"."<member>" in `text` -> (db, member), or None when there is none."""
        m = _BINDING.search(text or "")
        return (m.group(1), m.group(2)) if m else None

    def find_bindings(self, text: str):
        """Every (db, member) reference inside `text`, in order - the coverage trace scans
        builder cell blobs with this."""
        return [(m.group(1), m.group(2)) for m in _BINDING.finditer(text or "")]


SYMBOLS = TiaSymbols()
