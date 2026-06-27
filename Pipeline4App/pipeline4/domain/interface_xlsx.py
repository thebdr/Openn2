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

import datetime
import io
import os
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from copy import copy, deepcopy

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableColumn

from pipeline4.core import config
from pipeline4.domain import interfaces
from pipeline4.io import xlsx_edit

_INDEX_TOKEN = "<index>"
_MAIN_NS = xlsx_edit._MAIN   # the spreadsheetml main-namespace ET prefix (reuse the one canonical const)


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


# =================================================================================================== #
# Phase 400e - insert each IF_<instance> sheet into the I/O List, LOSSLESSLY
# =================================================================================================== #
# Clean-room port of PL3's interfaces.py insertion path. openpyxl writes the combined workbook (keeping
# every existing formula), then the existing formula cells' CACHED VALUES - which openpyxl drops on
# re-save - are patched back at the ZIP/XML level, so both the formulas and their values survive. The
# inserted IF_ sheets' `I/O Address Side 1` LET cache (also dropped, and base-stale at the source) is
# RE-SEEDED with the value computed in Python, so phase 510 reads correct addresses without Excel. Then
# xlsx_edit.freeze_arrays (400d) freezes any dynamic array openpyxl flattened in the I/O List's other
# sheets, avoiding the "overlapping array formula" corruption.

def _copy_sheet(src, dst, title) -> None:
    """Copy a generated interface sheet `src` into workbook `dst` as a new sheet `title`: values +
    formulas (the per-sheet table names are made unique and rewritten in the formulas), cell styles,
    column widths, merged cells, and the tables (re-created)."""
    suffix = re.sub(r"[^A-Za-z0-9_]", "_", title)
    renames = {nm: f"{nm}_{suffix}" for nm in list(src.tables)}     # unique table names in the iolist
    new = dst.create_sheet(title)
    for row in src.iter_rows():
        for cell in row:
            v = cell.value
            if v is None and not cell.has_style:
                continue
            if isinstance(v, str) and v.startswith("="):
                for old, newn in renames.items():
                    v = v.replace(old, newn)
            nc = new.cell(row=cell.row, column=cell.column, value=v)
            if cell.data_type == "s" and isinstance(v, str) and v[:1] in ("=", "+", "-"):
                nc.data_type = "s"
            if cell.has_style:
                nc.font = copy(cell.font)
                nc.fill = copy(cell.fill)
                nc.border = copy(cell.border)
                nc.alignment = copy(cell.alignment)
                nc.number_format = cell.number_format
    for letter, dim in src.column_dimensions.items():
        if dim.width:
            new.column_dimensions[letter].width = dim.width
    for mc in list(src.merged_cells.ranges):
        new.merge_cells(str(mc))
    for nm in list(src.tables):
        st = src.tables[nm]
        nt = Table(displayName=renames[nm], ref=st.ref)     # constructor sets name == displayName
        nt.headerRowCount = st.headerRowCount
        nt.totalsRowCount = st.totalsRowCount
        # Fresh columns with id + name ONLY. The source columns carry dataDxfId (indices into the
        # SOURCE workbook's differential-format records - out of range in the I/O List) and
        # calculatedColumnFormula (referencing the OLD table name); either makes Excel drop the whole
        # table. The cells keep their own copied/rewritten formulas, so addresses still compute.
        nt.tableColumns = [TableColumn(id=i + 1, name=col.name) for i, col in enumerate(st.tableColumns)]
        if st.tableStyleInfo is not None:
            nt.tableStyleInfo = deepcopy(st.tableStyleInfo)
        new.add_table(nt)


def _capture_formula_caches(zbytes) -> dict:
    """{sheet name -> {cell ref -> (t_attr, cached value text)}} for every formula cell carrying a
    cached value. openpyxl drops these on re-save, so they are restored afterwards (else data_only
    readers - staging/validation, e.g. Profinet IP/name - would see None)."""
    caches = {}
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        present = set(z.namelist())
        for nm, part in xlsx_edit._sheet_name_to_part(zbytes).items():
            if part not in present:
                continue
            cc = {}
            for c in ET.fromstring(z.read(part)).iter(_MAIN_NS + "c"):
                f, v = c.find(_MAIN_NS + "f"), c.find(_MAIN_NS + "v")
                if f is not None and v is not None and v.text is not None:
                    cc[c.get("r")] = (c.get("t"), v.text)
            if cc:
                caches[nm] = cc
    return caches


def _patch_formula_cache(xml: str, ref: str, t, value: str) -> str:
    """Set a single formula cell's cached value (+ its result-type t) in an openpyxl-written worksheet
    XML string. openpyxl usually emits an empty <v/> for a formula cell, but a copied formula cell may
    carry none at all - so REPLACE an existing <v>...</v>/<v/> when present, else APPEND one after the
    <f> (used both to restore the I/O List's own caches and to seed the inserted IF_ address values)."""
    esc = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    pat = re.compile(r'(<c r="' + re.escape(ref) + r'")([^>]*)(>)(.*?)(</c>)', re.DOTALL)

    def repl(m):
        attrs = re.sub(r'\s+t="[^"]*"', "", m.group(2))
        if t:
            attrs += f' t="{t}"'
        body = m.group(4)
        if re.search(r"<v\s*/>|<v>.*?</v>", body, re.DOTALL):
            body = re.sub(r"<v\s*/>|<v>.*?</v>", f"<v>{esc}</v>", body, count=1)
        else:
            body += f"<v>{esc}</v>"
        return m.group(1) + attrs + m.group(3) + body + m.group(5)

    return pat.sub(repl, xml, count=1)


# --- Interface I/O Address Side 1: compute the LET's value in Python (Excel-independent) ----------------
# Each inserted IF_ sheet carries an `_xlfn.LET` "I/O Address Side 1" formula whose Excel cache openpyxl
# drops (so phase 510 reads None and skips the tag). The value can't be PRESERVED from the source either:
# the LET reads the Side-1 Base Address that phase 400 plugs in, so the template's cache is a stale
# placeholder base. So we MIRROR the LET from plain row data and SEED a correct cache on insert.
_ADDR_HEADERS = ("Data Type", "Direction </>", "I/O Offset Byte", "I/O Bit",
                 "I/O Address Side 1", "Base Address", "Input Format")
_NUMREF = re.compile(r"^=([A-Z]+\d+)([+-]\d+)?$")


def _addr_int(v):
    """int from a cell that may be None, 12, '12', or a float-read '12.0'; None when not numeric."""
    s = str(v if v is not None else "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    return int(s) if s.lstrip("-").isdigit() else None


def _resolve_num(ws, ref: str, memo: dict):
    """Resolve a numeric IF_ cell that is a literal OR one of the table's two simple offset/bit chain
    formulas (=K3 / =L3+1). int, or None when it is non-numeric / the formula shape is unknown."""
    if ref in memo:
        return memo[ref]
    memo[ref] = None                                       # cycle guard
    cell = ws[ref]
    v = cell.value
    if cell.data_type == "f" or (isinstance(v, str) and v.startswith("=")):
        m = _NUMREF.match(str(v).replace(" ", ""))
        base = _resolve_num(ws, m.group(1), memo) if m else None
        val = None if base is None else base + (int(m.group(2)) if m.group(2) else 0)
    else:
        val = _addr_int(v)
    memo[ref] = val
    return val


def _interface_address_caches(if_path) -> dict:
    """{cell ref -> ('str', address)} for an inserted IF_ sheet's `I/O Address Side 1` LET cells, each
    computed from the row's offset/bit/direction + the Side-1 base & format (the LET's $AH$2 / $AI$2) -
    so the sheet carries a CORRECT cached address WITHOUT Excel. {} when the table headers can't be
    resolved (phase 510 then degrades to its unresolved-address WARN). Blank separator rows yield ''."""
    wb = load_workbook(if_path)
    try:
        ws = wb[wb.sheetnames[0]]
        hdr = {str(ws.cell(1, c).value or "").strip(): c for c in range(1, ws.max_column + 1)}
        if any(h not in hdr for h in _ADDR_HEADERS):
            return {}
        addr_col = get_column_letter(hdr["I/O Address Side 1"])
        off_col, bit_col = get_column_letter(hdr["I/O Offset Byte"]), get_column_letter(hdr["I/O Bit"])
        c_dir, c_dt = hdr["Direction </>"], hdr["Data Type"]
        memo = {}
        base = _resolve_num(ws, f'{get_column_letter(hdr["Base Address"])}2', memo)   # the absolute $AH$2
        isynt = ws.cell(2, hdr["Input Format"]).value                                 # the absolute $AI$2
        if base is None or not isynt:
            return {}
        out = {}
        for r in range(2, ws.max_row + 1):
            if ws.cell(r, hdr["I/O Address Side 1"]).data_type != "f":                # only the LET cells
                continue
            a = interfaces.io_address_side1(isynt, base, ws.cell(r, c_dir).value, ws.cell(r, c_dt).value,
                                            _resolve_num(ws, f"{off_col}{r}", memo),
                                            _resolve_num(ws, f"{bit_col}{r}", memo))
            if a:
                out[f"{addr_col}{r}"] = ("str", a)
        return out
    finally:
        wb.close()


def insert_sheets_into_iolist(iolist_path, sheets) -> list:
    """Insert each (title, if_path) interface sheet into the I/O List ONLY if a sheet of that name is
    not already present, LOSSLESSLY. openpyxl writes the combined workbook (keeping every existing
    formula), then the existing formula cells' CACHED VALUES - which openpyxl drops on re-save - are
    patched back from the original, so both the formulas and their values survive. ONE atomic save (the
    caller backs the I/O List up first). Returns per-interface action strings."""
    with open(iolist_path, "rb") as fh:
        caches = _capture_formula_caches(fh.read())

    dst = load_workbook(iolist_path)               # data_only=False -> keep the existing formulas
    actions, changed, inserted = [], False, []
    for title, if_path in sheets:
        if title in dst.sheetnames:
            actions.append(f"{title}: already present in the I/O List - skipped")
            continue
        src_wb = load_workbook(if_path)
        _copy_sheet(src_wb[src_wb.sheetnames[0]], dst, title)
        src_wb.close()
        inserted.append((title, if_path))
        actions.append(f"{title}: inserted into the I/O List")
        changed = True
    if not changed:
        dst.close()
        return actions

    tmp = iolist_path + ".tmp_insert.xlsx"
    try:
        dst.save(tmp)
        dst.close()
        with open(tmp, "rb") as fh:
            data = fh.read()
        tparts = xlsx_edit._sheet_name_to_part(data)
        # restore the original I/O List's formula caches AND seed each inserted IF_ sheet's I/O Address
        # Side 1 (computed base+offset; openpyxl dropped the LET cache and the source cache is base-stale)
        to_patch = {nm: dict(cc) for nm, cc in caches.items()}
        for title, if_path in inserted:
            seeded = _interface_address_caches(if_path)
            if seeded:
                to_patch.setdefault(title, {}).update(seeded)
                actions.append(f"{title}: seeded {len(seeded)} I/O Address Side 1 value(s) (Excel-independent)")
        repl = {}
        for nm, cc in to_patch.items():
            part = tparts.get(nm)
            if not part:
                continue
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                xml = z.read(part).decode("utf-8")
            for ref, (t, v) in cc.items():
                xml = _patch_formula_cache(xml, ref, t, v)
            repl[part] = xml.encode("utf-8")
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(data)) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for it in zin.infolist():
                zout.writestr(it, repl.get(it.filename) or zin.read(it.filename))
        with open(tmp, "wb") as fh:
            fh.write(out.getvalue())
        os.replace(tmp, iolist_path)
        # openpyxl's save FLATTENS any dynamic array in the I/O List's other sheets into a master +
        # literal slaves (an "overlapping array formula" Excel reports as corrupt). Post-process with the
        # surgical writer (400d): freeze every such array to its cached values (+ drop a stale calcChain).
        for sheet_name, master, rng in xlsx_edit.freeze_arrays(iolist_path):
            actions.append(f"[WARN] froze legacy array {sheet_name}!{master} (spill {rng}) to its cached "
                           "values to avoid corruption (the original formula is in the backup)")
    except (OSError, ET.ParseError, zipfile.BadZipFile) as e:
        try:
            dst.close()
        except Exception:  # noqa: BLE001
            pass
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        actions.append(f"save failed ({e}) - I/O List left unchanged (restore from the .bak if needed)")
    return actions


def insert_interface_sheets(database, *, iolist_path: str | None = None, out_dir: str | None = None) -> list:
    """400e entry point: insert each projected `IF_<instance>.xlsx` (in `out_dir`, default
    `config.interfaces_dir()`) as a sheet named `IF_<instance>` into the I/O List, if not already present.
    A timestamped `.bak` of the I/O List is taken first. `iolist_path` defaults to the configured I/O List.
    Returns a list of action strings ([] + a note when there is nothing to insert / no I/O List)."""
    out_dir = out_dir or config.interfaces_dir()
    if iolist_path is None:
        iolist_path = config.load_params().get("iolist_path")
    if not iolist_path or not os.path.exists(iolist_path):
        return [f"no I/O List to insert into ({iolist_path!r}) - skipped"]

    sheets = []   # (sheet title, IF path) - the IF_ prefix keeps them clear of the NET SAFETY sheets
    for inst in database["interfaces"]:               #   staging/validation match, and gives 510 a stable find-by prefix
        instance = inst["instance"]
        if_path = os.path.join(out_dir, f"IF_{_safe_name(instance)}.xlsx")
        if os.path.exists(if_path):
            sheets.append((_safe_name(f"IF_{instance}"), if_path))
    if not sheets:
        return ["no projected IF_*.xlsx found to insert - run the projection first"]

    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{iolist_path}.bak_{stamp}.xlsx"
    try:
        shutil.copyfile(iolist_path, bak)
    except OSError as e:
        return [f"I/O List backup failed ({e}); sheet insertion skipped"]
    return [f"backed up the I/O List -> {os.path.basename(bak)}"] + insert_sheets_into_iolist(iolist_path, sheets)
