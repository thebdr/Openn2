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


def interp_keep(template: str, row) -> str:
    """Like interp, but LEAVE a {token} intact when the row has no such key (a present-but-empty key
    still substitutes to ''). Used to resolve interface_tagname at staging while preserving the
    per-interface {interface_name}/{interface_id} tokens for the generator to fill."""
    def sub(m):
        key = m.group(1)
        if key in row:
            v = row.get(key)
            return "" if v is None else str(v)
        return m.group(0)
    return _TOKEN.sub(sub, template or "").strip()


def interface_tagname(row) -> str:
    """Staging-side interface tag name: the type's `interface_tagname` template resolved against the
    row (+ the nested {tag_name}), KEEPING {interface_name}/{interface_id} as tokens for the interface
    generator to fill per interface. '' when the type defines none."""
    t = row.get("_type") or {}
    tpl = t.get("interface_tagname", "")
    if not tpl:
        return ""
    ctx = dict(row)
    ctx["tag_name"] = interp(t.get("tag_name", ""), row)
    return interp_keep(tpl, ctx)


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


def plc_binding(row) -> str:
    """TIA-qualified reference for a signal: `"<leftmost db>"."<member>"` when it is a DB member,
    else `"<tag>"`, else ''. The Pipeline2 `outputs.plc_binding` shape; shared by interface mirroring
    (phase 400) and the diagnosis generators (phase 600). Reads the staged `name_in_db`/`datablocks`/
    `name_in_tagtable` when present, else recomputes from the type."""
    member = (row.get("name_in_db") or member_name(row) or "").strip()
    if member:
        dbs = [d.strip() for d in str(row.get("datablocks") or "").split("|") if d.strip()]
        if not dbs:
            dbs = [d for d in ((row.get("_type") or {}).get("db_names") or []) if d]
        db = dbs[0] if dbs else ""
        return f'"{db}"."{member}"' if db else f'"{member}"'
    tag = (row.get("name_in_tagtable") or tag_name(row) or "").strip()
    return f'"{tag}"' if tag else ""


def logical_address(bit) -> str:
    """TIA logical address: %-prefixed (I20.0 -> %I20.0)."""
    b = str(bit or "").strip()
    return ("%" + b) if b[:1].upper() in ("I", "Q") else b
