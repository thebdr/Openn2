"""Signal-type identity derivation - the `{canonical}` template interpolation + the names a staged row
gets. Clean-room port of PL3's identity, reading the resolved type from the row's **`type`** cell (PL4
persists the resolved type as an object, not PL3's ephemeral `_type`).

This first cut covers the staging-time, DOCUMENT-derived identity: the FLDs + the PLC tag name/table.
The registry-derived names (`name_in_db` / `datablocks` / `plc_binding`) and the diagnosis/interface
names land with their phases (520/600/400), where they're verified against PL3.
"""
from __future__ import annotations

from pipeline5.core import expr


def interp(template, row) -> str:
    """Resolve a native `{$canonical}` template against the row; trim the outer whitespace (templates carry
    intentional inner spacing). A hole may carry a Python format spec (`{$diag_cabinet:03d}`) - the
    diagnosis columns rely on it. DELEGATES to the unified `expr.render` (mode="empty": a missing field
    -> ""). Config templates are authored in native `{$token}` syntax."""
    return expr.render(template, row, mode="empty").strip()


def interp_keep(template, row) -> str:
    """Like `interp`, but LEAVE an unresolved hole intact as `{$token}` (a present-but-empty key still
    substitutes to '') - DELEGATES to `expr.render(mode="keep")`. Used for the two-stage interface_tagname
    fill at phase 400: stage 1 fills `{$tag_name}`/`{$db_element}`/`{$member}`/`{$direction}` and PRESERVES
    `{$interface_name}`/`{$interface_id}`; stage 2 (the per-interface generator) fills those."""
    return expr.render(template, row, mode="keep").strip()


def interface_tagname(row, template) -> str:
    """The interface tag name (Signal Name Side 1 base) for a signal: the type's `interface_tagname`
    `template` resolved against the row, KEEPING `{interface_name}`/`{interface_id}` for the generator.
    In PL4 `{tag_name}` resolves to the staged `name_in_tagtable` and `{db_element}` to the 520-written
    `name_in_db` (both relocated out of `signal_types`); '' when the type defines no template."""
    if not template:
        return ""
    ctx = dict(row)
    ctx["tag_name"] = str(row.get("name_in_tagtable") or "")
    ctx["db_element"] = str(row.get("name_in_db") or "")
    return interp_keep(template, ctx)


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
