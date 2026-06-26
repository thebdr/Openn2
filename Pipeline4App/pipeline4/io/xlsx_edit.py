"""xlsx_edit.py - THE single primitive for modifying an .xlsx, surgically (ported from PL3, verbatim
behavior - it is architecture-independent: pure ZIP + regex XML surgery, no openpyxl on write).

openpyxl is unusable for our edits: a `load_workbook` -> `save` round-trip FLATTENS dynamic-array /
spill formulas (it keeps the array master AND emits literal "slave" cells inside the same range, which
Excel rejects as an "overlapping array formula" / corrupt file) and drops formula caches. This module
instead edits ONLY the worksheet parts that change, INSIDE the original zip, and copies every other
part BYTE-FOR-BYTE - so shared/array formulas, formula caches, tables and styles in untouched parts
survive because they are never touched. Cell edits are a regex rewrite of the existing `<c>` element
(the approach the corruption diagnosis verified produces valid XML). The ARRAY GUARD strips an array
master whose range an edit writes into, so the app can OWN a column with no master+literal overlap left
behind.

Because it never re-serialises the whole workbook, openpyxl's formula-cache drop never happens, so
there is nothing to restore. `set_cells` is the pure per-sheet engine; `edit_workbook` is the zip-level
orchestrator (atomic temp + os.replace); `freeze_arrays` is the post-process the openpyxl-based
phase-400 interface-sheet insert (400e) still calls.
"""
from __future__ import annotations
import io
import os
import re
import zipfile
import xml.etree.ElementTree as ET

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

_COL = re.compile(r"^([A-Z]+)(\d+)$")


def _colnum(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n


def _split(ref: str) -> tuple:
    m = _COL.match(ref)
    return m.group(1), int(m.group(2))


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# --------------------------------------------------------------------------------------------- #
# the per-sheet engine: rewrite chosen cells in one worksheet's XML, preserving everything else
# --------------------------------------------------------------------------------------------- #
_ARRAY_MASTER = re.compile(r'<c\s+r="([A-Z]+\d+)"[^>]*>\s*<f\b[^>]*\bt="array"[^>]*\bref="([^"]+)"', re.DOTALL)


def _in_range(ref: str, rng: str) -> bool:
    a, b = (rng.split(":", 1) + [rng])[:2] if ":" in rng else (rng, rng)
    (ca, ra), (cb, rb) = _split(a), _split(b)
    cc, rr = _split(ref)
    lo, hi = sorted((_colnum(ca), _colnum(cb)))
    rlo, rhi = sorted((ra, rb))
    return lo <= _colnum(cc) <= hi and rlo <= rr <= rhi


def _style_of(cell_xml: str) -> str:
    m = re.search(r'\bs="(\d+)"', cell_xml or "")
    return m.group(1) if m else ""


def _freeze_array_range(xml: str, rng: str) -> str:
    """MATERIALIZE an array formula: drop the formula from EVERY cell in `rng` (the master + any CSE
    slaves) while KEEPING each cell's cached <v>, so the whole spill becomes static values - no data is
    lost and no master+literal overlap remains. Also strips the dynamic-array cell-metadata refs
    (cm=/vm=) that would dangle once the formula is gone. The original formula survives in the pre-edit
    backup; the caller logs a WARNING naming the master cell + range."""
    a, b = (rng.split(":", 1) + [rng])[:2] if ":" in rng else (rng, rng)
    (lc, lr), (hc, hr) = _split(a), _split(b)
    lo, hi = sorted((_colnum(lc), _colnum(hc)))
    rlo, rhi = sorted((lr, hr))
    cellpat = re.compile(r'<c\s+r="([A-Z]+\d+)"(?:\s[^/>]*)?\s*(?:/>|>.*?</c>)', re.DOTALL)

    def repl(m):
        cell = m.group(0)
        cc, rr = _split(m.group(1))
        if not (lo <= _colnum(cc) <= hi and rlo <= rr <= rhi) or "<f" not in cell:
            return cell
        cell = re.sub(r"<f\b.*?</f>|<f\b[^>]*/>", "", cell, count=1, flags=re.DOTALL)   # drop the formula
        return re.sub(r'\s(?:cm|vm)="[^"]*"', "", cell)                                  # drop dynamic-array meta
    return cellpat.sub(repl, xml)


def set_cells(sheet_xml: str, edits: dict) -> tuple:
    """Return (new_xml, materialized) where `materialized` = [(master_ref, range), ...] for any array
    formula FROZEN to its cached values to make room for an edit. Each {cell_ref: value} edit is applied
    as an inline string (an int/float as a NUMERIC cell - e.g. the DiagnosisBlocks Count; ""/None as a
    BLANK cell that reads None and clears any stale value), preserving the cell's existing style;
    cells/rows that don't exist are inserted in order."""
    # 1. an edit that lands in an array's spill range freezes the WHOLE array to its cached values first
    #    (keeps every spilled value; the formula stays in the backup) - so no master+literal overlap.
    materialized = []
    for mref, rng in _ARRAY_MASTER.findall(sheet_xml):
        if any(_in_range(e, rng) for e in edits):
            sheet_xml = _freeze_array_range(sheet_xml, rng)
            materialized.append((mref, rng))

    # 2. apply each edit: replace an existing <c r=..> verbatim, else insert it in the right place
    for ref, value in edits.items():
        cell_pat = re.compile(r'<c\s+r="' + re.escape(ref) + r'"(?:\s[^/>]*)?\s*(?:/>|>.*?</c>)', re.DOTALL)
        existing = cell_pat.search(sheet_xml)
        style = _style_of(existing.group(0)) if existing else ""
        s_attr = f' s="{style}"' if style else ""
        if value is None or value == "":
            new_cell = f'<c r="{ref}"{s_attr}/>'                  # a blank cell (reads None; clears a stale value)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            new_cell = f'<c r="{ref}"{s_attr}><v>{value}</v></c>'
        else:
            new_cell = f'<c r="{ref}"{s_attr} t="inlineStr"><is><t xml:space="preserve">{_esc(value)}</t></is></c>'
        if existing:
            sheet_xml = sheet_xml[:existing.start()] + new_cell + sheet_xml[existing.end():]
        else:
            sheet_xml = _insert_cell(sheet_xml, ref, new_cell)
    return sheet_xml, materialized


def _insert_cell(xml: str, ref: str, new_cell: str) -> str:
    """Insert `new_cell` into its <row>, keeping cells column-sorted; create the <row> (row-sorted) if
    absent. Best-effort: if the sheetData layout is unexpected, append the row before </sheetData>."""
    col, rownum = _split(ref)
    target_col = _colnum(col)
    row_pat = re.compile(r'(<row\s+r="' + str(rownum) + r'"(?:\s[^>]*)?>)(.*?)(</row>)', re.DOTALL)
    rm = row_pat.search(xml)
    if rm:
        body = rm.group(2)
        # find the first existing cell whose column is greater than ours -> insert before it
        ins_at = len(body)
        for cm in re.finditer(r'<c\s+r="([A-Z]+)\d+"', body):
            if _colnum(cm.group(1)) > target_col:
                ins_at = cm.start()
                break
        new_body = body[:ins_at] + new_cell + body[ins_at:]
        return xml[:rm.start()] + rm.group(1) + new_body + rm.group(3) + xml[rm.end():]
    # no such row: create it, inserted before the first row with a greater r (else before </sheetData>)
    new_row = f'<row r="{rownum}">{new_cell}</row>'
    ins_at = None
    for rm2 in re.finditer(r'<row\s+r="(\d+)"', xml):
        if int(rm2.group(1)) > rownum:
            ins_at = rm2.start()
            break
    if ins_at is None:
        return re.sub(r'</sheetData>', new_row + "</sheetData>", xml, count=1)
    return xml[:ins_at] + new_row + xml[ins_at:]


# --------------------------------------------------------------------------------------------- #
# the zip-level orchestrator
# --------------------------------------------------------------------------------------------- #
def _sheet_name_to_part(zbytes) -> dict:
    out = {}
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rid = {r.get("Id"): r.get("Target")
               for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        sheets = wb.find(_MAIN + "sheets")
        for sh in (sheets if sheets is not None else []):
            t = rid.get(sh.get(_REL + "id"), "")
            out[sh.get("name")] = (t.lstrip("/") if t.startswith("/")
                                   else t if t.startswith("xl/") else "xl/" + t)
    return out


def _num_to_col(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


_WS_CT = "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
_WS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"


# A clickable cell is rendered as a hyperlink (blue + underlined) via a rich-text RUN on the inline string
# - no styles.xml font/cellXf is needed, so a regenerated sheet never accumulates orphan styles.
_LINK_RPR = '<rPr><u/><color rgb="FF0563C1"/></rPr>'


def _cell_xml(ref: str, val, link: bool = False) -> str:
    """One worksheet <c> for `val`: bool/str -> an INLINE STRING (so a leading '='/'+'/'-' stays TEXT,
    not a formula), int/float -> a numeric <v>, None/"" -> "" (the cell is skipped). When `link`, the
    inline string is a rich-text run styled like a hyperlink (blue + underlined)."""
    if val is None or val == "":
        return ""
    if link:
        sp = ' xml:space="preserve"' if str(val) != str(val).strip() else ""
        return f'<c r="{ref}" t="inlineStr"><is><r>{_LINK_RPR}<t{sp}>{_esc(val)}</t></r></is></c>'
    if isinstance(val, bool):
        return f'<c r="{ref}" t="inlineStr"><is><t>{_esc(val)}</t></is></c>'
    if isinstance(val, (int, float)):
        return f'<c r="{ref}"><v>{val}</v></c>'
    sp = ' xml:space="preserve"' if str(val) != str(val).strip() else ""
    return f'<c r="{ref}" t="inlineStr"><is><t{sp}>{_esc(val)}</t></is></c>'


def build_row_xml(row_num: int, values: list, link_refs=None) -> str:
    """A worksheet <row r=row_num> with one cell per non-blank value (1-based columns). A cell whose ref is
    in `link_refs` is rendered like a hyperlink (blue + underlined)."""
    link_refs = link_refs or ()
    cells = []
    for ci, v in enumerate(values, 1):
        ref = f"{_num_to_col(ci)}{row_num}"
        cells.append(_cell_xml(ref, v, link=ref in link_refs))
    return f'<row r="{row_num}">{"".join(cells)}</row>'


def build_sheet_xml(rows: list, hyperlinks: list | None = None) -> str:
    """A fresh worksheet XML for a grid (`rows` = list of row lists). int/float -> a numeric cell;
    everything else -> an INLINE STRING (so a leading '='/'+'/'-' is text, not a formula). `hyperlinks`
    = [(cell_ref, location, display)] for internal links (e.g. 'NET SAFETY 50'!K23) - each linked cell is
    rendered blue + underlined. Mirrors the full structure Excel writes (dimension/sheetViews/
    sheetFormatPr/pageMargins) - a bare <sheetData>-only worksheet makes Excel report the workbook corrupt."""
    link_refs = {ref for ref, _, _ in hyperlinks} if hyperlinks else set()
    maxc = 1
    for row in rows:
        for ci, val in enumerate(row, 1):
            if not (val is None or val == ""):
                maxc = max(maxc, ci)
    body = "".join(build_row_xml(ri, row, link_refs) for ri, row in enumerate(rows, 1))
    dim = f"A1:{_num_to_col(maxc)}{max(1, len(rows))}"
    hl = ""
    if hyperlinks:
        items = "".join(f'<hyperlink ref="{ref}" location="{_esc(loc)}" display="{_esc(disp)}"/>'
                        for ref, loc, disp in hyperlinks)
        hl = f"<hyperlinks>{items}</hyperlinks>"
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<dimension ref="{dim}"/>'
            '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
            '<sheetFormatPr defaultRowHeight="15"/>'
            f'<sheetData>{body}</sheetData>{hl}'
            '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
            '</worksheet>')


def append_to_sheet(sheet_xml: str, rows: list) -> str:
    """Append `rows` (value-lists) as new <row> elements AFTER the last existing row, BYTE-PRESERVING
    every existing row (no existing <row>/<c> is matched or rewritten - so a hand-edited cell / style /
    stale value survives). Row numbers continue from the current max (or 1 for an empty sheet); the block
    is spliced before </sheetData> (a self-closing <sheetData/> is expanded). Best-effort grows the
    <dimension> (cosmetic - Excel recomputes the used range on open)."""
    if not rows:
        return sheet_xml
    nums = [int(m.group(1)) for m in re.finditer(r'<row\s+r="(\d+)"', sheet_xml)]
    start = (max(nums) + 1) if nums else 1
    block = "".join(build_row_xml(start + i, r) for i, r in enumerate(rows))
    if "</sheetData>" in sheet_xml:
        xml = sheet_xml.replace("</sheetData>", block + "</sheetData>", 1)
    else:
        xml = re.sub(r"<sheetData\s*/>", "<sheetData>" + block + "</sheetData>", sheet_xml, count=1)
    return _grow_dimension(xml, start + len(rows) - 1, max((len(r) for r in rows), default=1))


def _grow_dimension(xml: str, last_row: int, ncols: int) -> str:
    """Widen the single <dimension ref="A1:..">  to include (last_row, ncols). Cosmetic + best-effort:
    returns xml unchanged if there is no plain `A1:XY` dimension."""
    m = re.search(r'<dimension ref="([A-Z]+\d+):([A-Z]+)(\d+)"/>', xml)
    if not m:
        return xml
    c2 = max(_colnum(m.group(2)), ncols)
    r2 = max(int(m.group(3)), last_row)
    new = f'<dimension ref="{m.group(1)}:{_num_to_col(c2)}{r2}"/>'
    return xml[:m.start()] + new + xml[m.end():]


def _remove_sheet(wbxml, relsxml, ctxml, name, part):
    """Unregister a sheet by `name`: drop its <sheet> (+ its r:id rel) and its content-type Override."""
    m = re.search(r'<sheet\b[^>]*\bname="' + re.escape(name) + r'"[^>]*/>', wbxml)
    if not m:
        return wbxml, relsxml, ctxml
    rid = re.search(r'r:id="([^"]+)"', m.group(0))
    wbxml = wbxml[:m.start()] + wbxml[m.end():]
    if rid:
        relsxml = re.sub(r'<Relationship\b[^>]*\bId="' + re.escape(rid.group(1)) + r'"[^>]*/>', "", relsxml, count=1)
    ctxml = re.sub(r'<Override\b[^>]*\bPartName="/' + re.escape(part) + r'"[^>]*/>', "", ctxml, count=1)
    return wbxml, relsxml, ctxml


def _register_sheet(existing_parts, wbxml, relsxml, ctxml, name):
    """Add a new worksheet `name`: pick a free part + rId + sheetId, insert into workbook.xml (<sheets>),
    workbook.xml.rels and [Content_Types].xml. Returns (part, wbxml, relsxml, ctxml)."""
    n = 1
    while f"xl/worksheets/sheet{n}.xml" in existing_parts:
        n += 1
    part = f"xl/worksheets/sheet{n}.xml"
    rids = [int(i[3:]) for i in re.findall(r'Id="(rId\d+)"', relsxml)]
    rid = f"rId{(max(rids) + 1) if rids else 1}"
    sids = [int(s) for s in re.findall(r'sheetId="(\d+)"', wbxml)]
    sid = (max(sids) + 1) if sids else 1
    sheet_el = '<sheet name="' + _esc(name) + '" sheetId="' + str(sid) + '" r:id="' + rid + '"/>'
    rel_el = '<Relationship Id="' + rid + '" Type="' + _WS_REL + '" Target="worksheets/sheet' + str(n) + '.xml"/>'
    ct_el = '<Override PartName="/' + part + '" ContentType="' + _WS_CT + '"/>'
    wbxml = wbxml.replace("</sheets>", sheet_el + "</sheets>", 1)
    relsxml = relsxml.replace("</Relationships>", rel_el + "</Relationships>", 1)
    ctxml = ctxml.replace("</Types>", ct_el + "</Types>", 1)
    return part, wbxml, relsxml, ctxml


def freeze_arrays(path: str, *, dest: str | None = None) -> list:
    """Post-process an openpyxl-saved .xlsx (the openpyxl-based writers - e.g. phase 400's interface-
    sheet insert - that CAN'T avoid the flatten): FREEZE every array formula in place (remove the master
    <f>, keeping its + the spill cells' cached values), so an openpyxl-flattened dynamic array (a master
    + literal slaves) becomes static values with NO overlapping-array corruption; and DROP a stale
    xl/calcChain.xml. Atomic (temp + os.replace). Returns the (sheet, master_ref, range) frozen (WARN
    log)."""
    dest = dest or path
    with open(path, "rb") as f:
        data = f.read()
    part_to_name = {p: n for n, p in _sheet_name_to_part(data).items()}
    repl, frozen = {}, []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        present = set(z.namelist())
        for part in present:
            if not (part.startswith("xl/worksheets/") and part.endswith(".xml")):
                continue
            xml = z.read(part).decode("utf-8")
            masters = _ARRAY_MASTER.findall(xml)
            if not masters:
                continue
            for mref, rng in masters:
                xml = _freeze_array_range(xml, rng)
                frozen.append((part_to_name.get(part, part), mref, rng))
            repl[part] = xml.encode("utf-8")
        deleted = set()
        if "xl/calcChain.xml" in present:
            deleted.add("xl/calcChain.xml")
            repl["xl/_rels/workbook.xml.rels"] = re.sub(
                r'<Relationship\b[^>]*calcChain\.xml[^>]*/>', "",
                z.read("xl/_rels/workbook.xml.rels").decode("utf-8"), count=1).encode("utf-8")
            repl["[Content_Types].xml"] = re.sub(
                r'<Override\b[^>]*PartName="/xl/calcChain\.xml"[^>]*/>', "",
                z.read("[Content_Types].xml").decode("utf-8"), count=1).encode("utf-8")
        if not (repl or deleted):
            return frozen
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for it in z.infolist():
                if it.filename in deleted:
                    continue
                zout.writestr(it, repl.get(it.filename) or z.read(it.filename))
    tmp = dest + ".tmp_freeze"
    with open(tmp, "wb") as f:
        f.write(out.getvalue())
    os.replace(tmp, dest)
    return frozen


def edit_workbook(path: str, *, cell_edits: dict | None = None, new_sheets: list | None = None,
                  delete_sheets: list | None = None, append_rows: dict | None = None,
                  dest: str | None = None) -> list:
    """THE primitive that modifies an .xlsx. `cell_edits` = {sheet_name: {cell_ref: value}} surgically
    rewrites cells (freezing any array spill it lands in); `new_sheets` = [{name, rows, hyperlinks?}]
    adds/replaces whole app-owned sheets (e.g. _UnresolvedIndex / interface sheets); `append_rows` =
    {sheet_name: [row, ...]} APPENDS value rows to an existing sheet, byte-preserving its current rows
    (e.g. DiagnosisBlocks: add only the cabinets not already present); `delete_sheets` = [names] drops
    legacy sheets. ONLY the affected/added/removed parts change - every other part (incl. dynamic-array
    sheets the populator doesn't touch) is byte-copied. `new_sheets` and `append_rows` for the SAME sheet
    are mutually exclusive (append is skipped). Atomic (temp + os.replace); `dest` defaults to in-place.
    Returns the (sheet, master_ref, range) of any array frozen to its cached values (caller logs a WARN);
    [] if nothing changed."""
    cell_edits = cell_edits or {}
    new_sheets = new_sheets or []
    delete_sheets = list(delete_sheets or [])
    append_rows = append_rows or {}
    if not (cell_edits or new_sheets or delete_sheets or append_rows):
        return []
    dest = dest or path
    with open(path, "rb") as f:
        data = f.read()
    name_to_part = _sheet_name_to_part(data)
    materialized = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        repl = {}
        for sheet_name, edits in cell_edits.items():            # 1. surgical cell edits
            part = name_to_part.get(sheet_name)
            if part and edits:
                new_xml, mats = set_cells(z.read(part).decode("utf-8"), edits)
                repl[part] = new_xml.encode("utf-8")
                materialized += [(sheet_name, m, r) for (m, r) in mats]

        added = {}                                              # 2. add/replace/delete whole sheets
        wbxml = z.read("xl/workbook.xml").decode("utf-8")
        relsxml = z.read("xl/_rels/workbook.xml.rels").decode("utf-8")
        ctxml = z.read("[Content_Types].xml").decode("utf-8")
        deleted = set()
        present = set(z.namelist())
        bookkeeping = False
        # ALWAYS drop xl/calcChain.xml. Any edit can add/remove/change a formula cell (a fill overwrites
        # a formula with a value; a regenerated sheet drops its formulas), and a STALE calcChain (listing
        # a formula cell that no longer exists) makes Excel report the workbook CORRUPT. Excel rebuilds
        # the chain on open - this is exactly why openpyxl drops it on every save.
        if "xl/calcChain.xml" in present:
            deleted.add("xl/calcChain.xml")
            relsxml = re.sub(r'<Relationship\b[^>]*calcChain\.xml[^>]*/>', "", relsxml, count=1)
            ctxml = re.sub(r'<Override\b[^>]*PartName="/xl/calcChain\.xml"[^>]*/>', "", ctxml, count=1)
            bookkeeping = True
        for dn in delete_sheets:
            if dn in name_to_part:
                wbxml, relsxml, ctxml = _remove_sheet(wbxml, relsxml, ctxml, dn, name_to_part[dn])
                deleted.add(name_to_part[dn])
                bookkeeping = True
        for spec in new_sheets:
            xml = build_sheet_xml(spec["rows"], spec.get("hyperlinks")).encode("utf-8")
            part = name_to_part.get(spec["name"])
            if part and part not in deleted:
                repl[part] = xml                                # replace an existing app-owned sheet
            else:
                part, wbxml, relsxml, ctxml = _register_sheet(present | set(added), wbxml, relsxml, ctxml, spec["name"])
                added[part] = xml
                bookkeeping = True

        new_names = {s["name"] for s in new_sheets}             # 3. append rows to an existing sheet
        for sheet_name, rows in append_rows.items():            #    (byte-preserving its current rows)
            part = name_to_part.get(sheet_name)
            if not part or part in deleted or sheet_name in new_names or not rows:
                continue
            base = repl[part].decode("utf-8") if part in repl else z.read(part).decode("utf-8")
            repl[part] = append_to_sheet(base, rows).encode("utf-8")
        if bookkeeping:
            repl["xl/workbook.xml"] = wbxml.encode("utf-8")
            repl["xl/_rels/workbook.xml.rels"] = relsxml.encode("utf-8")
            repl["[Content_Types].xml"] = ctxml.encode("utf-8")
        if not (repl or added):
            return materialized

        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for it in z.infolist():
                if it.filename in deleted:
                    continue
                zout.writestr(it, repl.get(it.filename) or z.read(it.filename))
            for part, content in added.items():
                zout.writestr(part, content)
    tmp = dest + ".tmp_edit"
    with open(tmp, "wb") as f:
        f.write(out.getvalue())
    os.replace(tmp, dest)
    return materialized
