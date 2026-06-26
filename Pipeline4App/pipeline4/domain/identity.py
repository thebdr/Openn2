"""Signal-type identity derivation - the `{canonical}` template interpolation + the names a staged row
gets. Clean-room port of PL3's identity, reading the resolved type from the row's **`type`** cell (PL4
persists the resolved type as an object, not PL3's ephemeral `_type`).

This first cut covers the staging-time, DOCUMENT-derived identity: the FLDs + the PLC tag name/table.
The registry-derived names (`name_in_db` / `datablocks` / `plc_binding`) and the diagnosis/interface
names land with their phases (520/600/400), where they're verified against PL3.
"""
from __future__ import annotations

import re

_TOKEN = re.compile(r"\{([A-Za-z0-9_]+)\}")


def interp(template, row) -> str:
    """Resolve a `{canonical}` template against the row; trim the outer whitespace (templates carry
    intentional inner spacing)."""
    return _TOKEN.sub(lambda m: str(row.get(m.group(1), "") or ""), template or "").strip()


def fld(row) -> str:
    """FUNCTIONAL UNIT + LOCATION + DEVICE, as written (the IoList device key). Staged as `iol_FLD`."""
    return (str(row.get("functional_unit") or "").strip()
            + str(row.get("location") or "").strip()
            + str(row.get("device") or "").strip())


def ce_fld(row) -> str:
    """The C&E-side FU+LOC+DEV (matrix cols J/K/L). Staged as `ce_FLD` ('' until the C&E enrichment ports)."""
    return (str(row.get("ce_functional_unit") or "").strip()
            + str(row.get("ce_location") or "").strip()
            + str(row.get("ce_device") or "").strip())


def combined_fld(row) -> str:
    """The device key with the C&E-side FLD appended ONLY when it differs (else just the I/O FLD).
    Staged as `combined_FLD`; the type templates use `{combined_FLD}`."""
    a, b = fld(row), ce_fld(row)
    return f"{a} {b}" if b and b != a else a


def _type_of(row) -> dict:
    return row.get("type") or {}


def is_io_signal(row) -> bool:
    """A taggable I/O point: a resolved non-interface type with an I/Q bit address."""
    t = _type_of(row)
    if not t or t.get("category") == "Interface":
        return False
    bit = str(row.get("bit") or "").strip().upper()
    return bit[:1] in ("I", "Q")


def tag_name(row) -> str:
    """PLC I/O tag name (the type's `tag_name` template); '' when the type isn't tagged on its own."""
    return interp(_type_of(row).get("tag_name", ""), row)


def tagtable(row) -> str:
    """PLC tag-table (Path): the type's `tagtable_name`, else the script_type."""
    t = _type_of(row)
    return (t.get("tagtable_name") or "").strip() or str(row.get("script_type") or "").strip()


def tag_comment(row) -> str:
    """The PLC tag comment (the type's `io_comment` template)."""
    return interp(_type_of(row).get("io_comment", ""), row)
