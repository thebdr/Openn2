"""Phase 400c - project the `interfaces` + `interface_elements` tables to `IF_<instance>.xlsx`.

`project(database)` writes one interface workbook per `interfaces` row: copy the MachineInterfaces
template, keep only the chosen machine sheet, retitle it to `IF_<instance>`, plug the Base Address / Base
Node / Index (Side rows, by header name) + replace `<index>` tokens, then lay the instance's
`interface_elements` onto the data table as the custom mirror block. Clean-room port of PL3's
`generate_one` / `_plug` / `_append_custom_rows`.

The elements are already mirrored + byte-laid-out (phase 400b); this projector only WRITES them - it adds
the BOOL-block padding (a full 2-byte block per script_type group: the real signals on the low bits, then
blank addressed rows for the engineer + a separator; a WORD = one row + a separator). openpyxl is fine
here (PL3 does the same): these IF_ files are documentation, not read back by a data_only reader except via
`insert_interface_sheets` (phase 400e). Output -> `config.interfaces_dir()` (NOT a BuilderData surface).
"""
from __future__ import annotations

import os
import shutil

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from pipeline4.core import config
from pipeline4.domain import interfaces

_INDEX_TOKEN = "<index>"


def _safe_name(text) -> str:
    bad = '\\/:*?"<>[]'
    return "".join("_" if ch in bad else ch for ch in str(text))[:31]


def _set_text(cell, value) -> None:
    """Write a string, forcing data_type='s' for a leading =/+/- so a tag/FLD isn't read as a formula."""
    s = "" if value is None else str(value)
    cell.value = s
    if s[:1] in ("=", "+", "-"):
        cell.data_type = "s"


def _coerce_int(value):
    s = "" if value is None else str(value).strip()
    if s in ("", "None"):
        return None
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return None


# --- the standard plug (Base Address / Node / Index, by header name) ----------------------------- #
def _header_index(ws, header_row: int = 1) -> dict:
    return {str(c.value).strip(): c.column for c in ws[header_row] if c.value not in (None, "")}


def _side_row(ws, side_c, value_c, side: int):
    if side_c:
        for r in range(2, ws.max_row + 1):
            if str(ws.cell(r, side_c).value).strip() in (str(side), f"{side}.0"):
                return r
        return None
    if side == 1 and value_c:
        for r in range(2, ws.max_row + 1):
            if ws.cell(r, value_c).value not in (None, ""):
                return r
    return None


def _plug(ws, base_address, node_side1, node_side2, index) -> None:
    """Plug the Side-1 base address + node, the Side-2 node (only when given), the Index (Side-1/Side-2
    rows only), and replace every <index> token. Side-1 base address only - the auto path leaves Side 2."""
    headers = _header_index(ws, 1)
    side_c = headers.get("Side")
    index_c = headers.get("Index")
    base_c = headers.get("Base Address")
    node_c = headers.get("Base Node")
    base_num = interfaces._to_int(base_address)
    n1 = interfaces._to_int(node_side1)
    n2 = interfaces._to_int(node_side2)

    if base_c and base_num is not None:
        r = _side_row(ws, side_c, base_c, 1)
        if r:
            ws.cell(r, base_c).value = base_num
    if node_c and n1 is not None:
        r = _side_row(ws, side_c, node_c, 1)
        if r:
            ws.cell(r, node_c).value = n1
    if node_c and n2 is not None:
        r = _side_row(ws, side_c, node_c, 2)
        if r:
            ws.cell(r, node_c).value = n2

    index = str(index or "").strip()
    if index_c and index:
        for side in (1, 2):
            r = _side_row(ws, side_c, index_c, side)
            if r:
                ws.cell(r, index_c).value = index
    if index:
        for row in ws.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and _INDEX_TOKEN in cell.value:
                    cell.value = cell.value.replace(_INDEX_TOKEN, index)


# --- the custom mirror block (the interface_elements, with the BOOL-block padding) --------------- #
def _append_custom_rows(ws, elements) -> None:
    found = interfaces._find_data_table(ws)
    if not found:
        return
    name, c1, r1, c2, r2, hdr = found
    table = ws.tables[name]
    s1c, s2c = hdr.get("I/O Address Side 1"), hdr.get("I/O Address Side 2")
    f1 = f2 = None
    for r in range(r1 + 1, r2 + 1):                       # the address LET formula, copied per new row
        v = ws.cell(r, s1c).value if s1c else None
        if isinstance(v, str) and v.startswith("="):
            f1 = v
            f2 = ws.cell(r, s2c).value if s2c else None
            break

    def _put(r, key, value, text=False):
        col = hdr.get(key)
        if not col:
            return
        if text:
            _set_text(ws.cell(r, col), value)
        else:
            ws.cell(r, col).value = value

    def _write(r, *, category, dt, direction, offset, bit, name_, expr, desc, fu, loc, dev, dc, swp, db):
        _put(r, "Category", category, text=True)
        _put(r, "Description", desc, text=True)
        _put(r, "Functional Unit", fu, text=True)
        _put(r, "Location", loc, text=True)
        _put(r, "Device", dev, text=True)
        _put(r, "Data Type", dt)
        _put(r, "Direction </>", ">" if direction == "Q" else "<")
        if offset is not None:
            _put(r, "I/O Offset Byte", offset)
        if bit is not None:
            _put(r, "I/O Bit", bit)
        _put(r, "Signal Name Side 1", name_, text=True)
        _put(r, "Expression Side 1", expr, text=True)
        if s1c and f1 is not None:
            ws.cell(r, s1c).value = f1
        if s2c and f2 is not None:
            ws.cell(r, s2c).value = f2
        if dc:
            _put(r, "diag_cabinet", dc)
        if swp:
            _put(r, "swp_cabinet", swp)
        if db:
            _put(r, "diag_bit", db)

    blocks = []                                            # group by direction (Q then I) then category
    for direction in ("Q", "I"):
        seen = {}
        for e in elements:
            if e.get("direction") != direction:
                continue
            cat = e.get("category")
            if cat not in seen:
                seen[cat] = []
                blocks.append((direction, cat, seen[cat]))
            seen[cat].append(e)

    def _f(e, key):
        return e.get(key) or ""

    row = last = r2
    for direction, cat, g in blocks:
        if (g[0].get("data_type") or "BOOL") == "WORD":
            for e in g:                                    # one row + a blank separator per word
                row += 1
                last = row
                _write(row, category=cat, dt="WORD", direction=direction, offset=_coerce_int(e.get("offset_byte")),
                       bit=None, name_=_f(e, "signal_name"), expr=_f(e, "expression"), desc=_f(e, "description"),
                       fu=_f(e, "functional_unit"), loc=_f(e, "location"), dev=_f(e, "device"),
                       dc=_f(e, "diag_cabinet"), swp=_f(e, "swp_cabinet"), db=_f(e, "diag_bit"))
                row += 1
        else:                                              # full 2-byte BOOL block (used + blank) + separator
            start = _coerce_int(g[0].get("offset_byte"))
            for b in range(((len(g) + 15) // 16) * 16):
                row += 1
                last = row
                if b < len(g):
                    e = g[b]
                    _write(row, category=cat, dt="BOOL", direction=direction, offset=start + b // 8, bit=b % 8,
                           name_=_f(e, "signal_name"), expr=_f(e, "expression"), desc=_f(e, "description"),
                           fu=_f(e, "functional_unit"), loc=_f(e, "location"), dev=_f(e, "device"),
                           dc=_f(e, "diag_cabinet"), swp=_f(e, "swp_cabinet"), db=_f(e, "diag_bit"))
                else:
                    _write(row, category=cat, dt="BOOL", direction=direction, offset=start + b // 8, bit=b % 8,
                           name_="", expr="", desc="", fu="", loc="", dev="", dc="", swp="", db="")
            row += 1

    if last > r2:
        newref = f"{get_column_letter(c1)}{r1}:{get_column_letter(c2)}{last}"
        table.ref = newref
        if table.autoFilter:
            table.autoFilter.ref = newref


def project(database, template_path: str | None = None, out_dir: str | None = None) -> dict:
    """Write one `IF_<instance>.xlsx` per `interfaces` row from the template + its `interface_elements`.
    Returns {'created': [paths]}. Defaults to the MachineInterfaces template + `config.interfaces_dir()`."""
    template_path = template_path or config.INTERFACE_TEMPLATE
    out_dir = out_dir or config.interfaces_dir()
    os.makedirs(out_dir, exist_ok=True)
    by_iface: dict = {}
    for e in database["interface_elements"]:
        by_iface.setdefault(e["interface"], []).append(e)

    created = []
    for inst in database["interfaces"]:
        instance = inst["instance"]
        chosen = inst["template_sheet"]
        target = os.path.join(out_dir, f"IF_{_safe_name(instance)}.xlsx")
        shutil.copyfile(template_path, target)
        wb = load_workbook(target)
        try:
            if chosen not in wb.sheetnames:
                chosen = wb.sheetnames[0]
            for sheet in list(wb.sheetnames):
                if sheet != chosen:
                    del wb[sheet]
            ws = wb[chosen]
            ws.title = _safe_name(instance)
            _plug(ws, inst.get("base_address"), inst.get("base_node"), "", inst.get("interface_id"))
            _append_custom_rows(ws, by_iface.get(instance, []))
            wb.save(target)
        finally:
            wb.close()
        created.append(target)
    return {"created": created}
