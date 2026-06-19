"""Signal-type identity derivation — the `{canonical}` template interpolation + the names a staged
row gets (DB member, PLC tag, tag-table, diagnosis description). Shared by staging (phase 300) and
the signal/diagnosis generators (phases 500/600). Clean-room port of Pipeline2's outputs helpers.
"""
from __future__ import annotations
import re

_TOKEN = re.compile(r"\{([A-Za-z0-9_]+)\}")


def fld(row) -> str:
    """FUNCTIONAL UNIT + LOCATION + DEVICE, as written (the device key used everywhere)."""
    return (str(row.get("functional_unit") or "").strip()
            + str(row.get("location") or "").strip()
            + str(row.get("device") or "").strip())


def interp(template: str, row) -> str:
    """Resolve a signal-type `{canonical}` template against the row; trim outer whitespace
    (templates carry intentional inner spacing)."""
    return _TOKEN.sub(lambda m: str(row.get(m.group(1), "") or ""), template or "").strip()


def _tpl(row, key: str) -> str:
    return (row.get("_type") or {}).get(key, "")


def is_io_signal(row) -> bool:
    """A taggable I/O point: a resolved non-interface type with an I/Q bit address."""
    t = row.get("_type")
    if not t or t.get("category") == "Interface":
        return False
    bit = str(row.get("bit") or "").strip().upper()
    return bit[:1] in ("I", "Q")


def tag_name(row) -> str:
    """PLC I/O tag name (the type's `tag_name` template); '' when the type isn't tagged on its own."""
    return interp(_tpl(row, "tag_name"), row)


def tag_comment(row) -> str:
    return interp(_tpl(row, "io_comment"), row)


def diag_desc(row) -> str:
    return interp(_tpl(row, "diag_desc"), row)


def tagtable(row) -> str:
    """PLC tag-table (Path): the type's tagtable_name, else the script_type."""
    t = row.get("_type") or {}
    return (t.get("tagtable_name") or "").strip() or str(row.get("script_type") or "").strip()


def member_name(row) -> str:
    """DB member name (the type's `db_element` template), or '' if the type is not DB-backed."""
    t = row.get("_type") or {}
    if t.get("db_kind") not in ("db", "safe_db"):
        return ""
    return interp(t.get("db_element", ""), row)


def logical_address(bit) -> str:
    """TIA logical address: %-prefixed (I20.0 -> %I20.0)."""
    b = str(bit or "").strip()
    return ("%" + b) if b[:1].upper() in ("I", "Q") else b
